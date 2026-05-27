#!/usr/bin/env python3
"""Extract review frames and contact sheets from a tennis practice video."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat
except ImportError as exc:
    raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc


@dataclass
class FrameRecord:
    path: Path
    timestamp: float
    brightness: float = 0.0
    sharpness: float = 0.0
    score: float = 0.0


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def require_bin(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}")


def ffprobe(video: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video),
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    duration = float(data.get("format", {}).get("duration") or stream.get("duration") or 0)
    fps_text = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    try:
        num, den = fps_text.split("/")
        fps = float(num) / float(den) if float(den) else 0
    except Exception:
        fps = 0
    return {
        "path": str(video),
        "duration_seconds": round(duration, 3),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": round(fps, 3),
        "codec": stream.get("codec_name"),
        "format": data.get("format", {}).get("format_name"),
    }


def extract_frames(video: Path, outdir: Path, fps: float, label: str, max_width: int) -> list[FrameRecord]:
    frame_dir = outdir / f"frames_{label}"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for old in frame_dir.glob("frame_*.jpg"):
        old.unlink()
    pattern = frame_dir / "frame_%04d.jpg"
    vf = f"fps={fps},scale='min({max_width},iw)':-2"
    run([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-vf",
        vf,
        "-q:v",
        "2",
        str(pattern),
    ])
    records = []
    for idx, path in enumerate(sorted(frame_dir.glob("frame_*.jpg")), start=1):
        records.append(FrameRecord(path=path, timestamp=(idx - 1) / fps))
    return records


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def measure_frame(record: FrameRecord) -> FrameRecord:
    with Image.open(record.path) as im:
        gray = im.convert("L")
        stat = ImageStat.Stat(gray)
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        record.brightness = stat.mean[0]
        record.sharpness = edge_stat.var[0]
        brightness_penalty = abs(record.brightness - 142) * 1.8
        record.score = record.sharpness - brightness_penalty
    return record


def make_contact_sheet(records: list[FrameRecord], outpath: Path, columns: int = 5, thumb_w: int = 300) -> None:
    if not records:
        return
    font = load_font(22)
    label_h = 34
    margin = 10
    max_jpeg_dim = 65000
    thumbs = []
    for rec in records:
        with Image.open(rec.path) as im:
            im = im.convert("RGB")
            ratio = thumb_w / im.width
            thumb_h = int(im.height * ratio)
            thumb = im.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            thumbs.append((rec, thumb))
    thumb_h = max(t.height for _, t in thumbs)
    rows = math.ceil(len(thumbs) / columns)
    sheet_h = rows * (thumb_h + label_h) + (rows + 1) * margin
    if sheet_h > max_jpeg_dim:
        rows_per_sheet = max(1, (max_jpeg_dim - margin) // (thumb_h + label_h + margin))
        records_per_sheet = max(columns, rows_per_sheet * columns)
        for part, start in enumerate(range(0, len(records), records_per_sheet), start=1):
            part_path = outpath.with_name(f"{outpath.stem}_part_{part:02d}{outpath.suffix}")
            make_contact_sheet(records[start:start + records_per_sheet], part_path, columns=columns, thumb_w=thumb_w)
        return
    sheet = Image.new(
        "RGB",
        (columns * thumb_w + (columns + 1) * margin, sheet_h),
        (246, 244, 236),
    )
    draw = ImageDraw.Draw(sheet)
    for idx, (rec, thumb) in enumerate(thumbs):
        row, col = divmod(idx, columns)
        x = margin + col * (thumb_w + margin)
        y = margin + row * (thumb_h + label_h + margin)
        sheet.paste(thumb, (x, y + label_h))
        label = f"{rec.timestamp:05.2f}s  {rec.path.name}"
        draw.rounded_rectangle((x, y, x + thumb_w, y + label_h - 3), radius=8, fill=(20, 32, 26))
        draw.text((x + 8, y + 5), label, fill=(255, 255, 255), font=font)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(outpath, quality=92)


def choose_candidates(records: list[FrameRecord], outdir: Path, limit: int, min_gap: float) -> list[dict]:
    measured = [measure_frame(r) for r in records]
    measured.sort(key=lambda r: r.score, reverse=True)
    picked: list[FrameRecord] = []
    for rec in measured:
        if all(abs(rec.timestamp - other.timestamp) >= min_gap for other in picked):
            picked.append(rec)
        if len(picked) >= limit:
            break
    picked.sort(key=lambda r: r.timestamp)
    candidate_dir = outdir / "candidate_frames"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for old in candidate_dir.glob("candidate_*.jpg"):
        old.unlink()
    rows = []
    for idx, rec in enumerate(picked, start=1):
        dst = candidate_dir / f"candidate_{idx:02d}_t{rec.timestamp:06.2f}.jpg"
        shutil.copy2(rec.path, dst)
        rows.append({
            "path": str(dst.relative_to(outdir)),
            "source_frame": str(rec.path.relative_to(outdir)),
            "timestamp": round(rec.timestamp, 2),
            "brightness": round(rec.brightness, 2),
            "sharpness": round(rec.sharpness, 2),
            "score": round(rec.score, 2),
        })
    return rows


def write_index(outdir: Path, metadata: dict, sample: list[FrameRecord], dense: list[FrameRecord], candidates: list[dict]) -> None:
    contact_sheets = [
        str(path.relative_to(outdir))
        for path in sorted((outdir / "contact_sheets").glob("*.jpg"))
    ]
    payload = {
        "metadata": metadata,
        "frames": {
            "sample_1fps": [
                {"path": str(r.path.relative_to(outdir)), "timestamp": round(r.timestamp, 2)}
                for r in sample
            ],
            "dense_4fps": [
                {"path": str(r.path.relative_to(outdir)), "timestamp": round(r.timestamp, 2)}
                for r in dense
            ],
            "candidates": candidates,
        },
        "contact_sheets": contact_sheets,
    }
    (outdir / "frame_index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract tennis video frames for AI coach review.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--sample-fps", type=float, default=1.0)
    parser.add_argument("--dense-fps", type=float, default=4.0)
    parser.add_argument("--max-width", type=int, default=1080)
    parser.add_argument("--candidates", type=int, default=18)
    args = parser.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")
    video = args.video.expanduser().resolve()
    if not video.exists():
        raise SystemExit(f"Video not found: {video}")
    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    metadata = ffprobe(video)
    (outdir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    sample = extract_frames(video, outdir, args.sample_fps, "1fps", args.max_width)
    dense = extract_frames(video, outdir, args.dense_fps, "4fps", args.max_width)

    sheet_dir = outdir / "contact_sheets"
    make_contact_sheet(sample, sheet_dir / "sample_1fps.jpg", columns=5, thumb_w=260)
    chunk_size = 40
    for part, start in enumerate(range(0, len(dense), chunk_size), start=1):
        make_contact_sheet(dense[start:start + chunk_size], sheet_dir / f"dense_4fps_part_{part:02d}.jpg", columns=5, thumb_w=260)

    candidates = choose_candidates(dense, outdir, args.candidates, min_gap=0.9)
    write_index(outdir, metadata, sample, dense, candidates)
    print(json.dumps({
        "outdir": str(outdir),
        "metadata": metadata,
        "sample_frames": len(sample),
        "dense_frames": len(dense),
        "candidates": len(candidates),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
