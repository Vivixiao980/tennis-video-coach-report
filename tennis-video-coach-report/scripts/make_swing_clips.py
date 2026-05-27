#!/usr/bin/env python3
"""Create phase-based slow-motion tennis swing clips with freeze annotations."""

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
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc


PHASE_LABELS = {
    "early": "前段",
    "front": "前段",
    "start": "前段",
    "middle": "中段",
    "mid": "中段",
    "late": "后段",
    "back": "后段",
    "end": "后段",
}


@dataclass
class Event:
    phase: str
    timestamp: float
    label: str
    note: str
    cue: str = ""
    start: float | None = None
    end: float | None = None
    focus: list[float] | None = None
    arrow: list[float] | None = None


def require_bin(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(video: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    return float(subprocess.check_output(cmd, text=True).strip())


def font_path() -> str:
    for path in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]:
        if Path(path).exists():
            return path
    return ""


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def parse_event(raw: str) -> Event:
    # Format: phase|timestamp|label|note|cue
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) < 2:
        raise ValueError("--event format: phase|timestamp|label|note|cue")
    phase = parts[0] or "middle"
    timestamp = float(parts[1])
    label = parts[2] if len(parts) > 2 and parts[2] else PHASE_LABELS.get(phase.lower(), phase)
    note = parts[3] if len(parts) > 3 and parts[3] else "这一拍适合停下来观察。"
    cue = parts[4] if len(parts) > 4 else ""
    return Event(phase=phase, timestamp=timestamp, label=label, note=note, cue=cue)


def events_from_json(path: Path) -> list[Event]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("phase_review") or data.get("phase_reviews") or []
    events: list[Event] = []
    for row in rows:
        phase = str(row.get("phase") or row.get("id") or "middle")
        timestamp = float(row.get("timestamp") or row.get("contact_timestamp") or 0)
        label = str(row.get("label") or PHASE_LABELS.get(phase.lower(), phase))
        note = str(row.get("note") or row.get("summary") or row.get("issue") or "这一拍适合停下来观察。")
        cue = str(row.get("cue") or "")
        start = float(row["clip_start"]) if row.get("clip_start") is not None else None
        end = float(row["clip_end"]) if row.get("clip_end") is not None else None
        focus = row.get("focus")
        arrow = row.get("arrow")
        events.append(Event(phase=phase, timestamp=timestamp, label=label, note=note, cue=cue, start=start, end=end, focus=focus, arrow=arrow))
    return events


def default_events(duration: float) -> list[Event]:
    return [
        Event("early", duration * 0.18, "前段", "先看刚开始时的准备节奏。", "球一出来，先转肩。"),
        Event("middle", duration * 0.50, "中段", "再看中段有没有变松或出现新习惯。", "先找位置，再挥拍。"),
        Event("late", duration * 0.82, "后段", "最后看后段疲劳后动作有没有走样。", "打完让拍子自然过去。"),
    ]


def safe_name(value: str) -> str:
    keep = []
    for ch in value.lower():
        if ch.isalnum() or ch in "-_":
            keep.append(ch)
        elif ch.isspace():
            keep.append("-")
    return "".join(keep).strip("-") or "phase"


def clip_bounds(event: Event, duration: float, pre: float, post: float) -> tuple[float, float]:
    start = event.start if event.start is not None else event.timestamp - pre
    end = event.end if event.end is not None else event.timestamp + post
    start = max(0.0, min(start, duration))
    end = max(start + 0.25, min(end, duration))
    return start, end


def extract_frame(video: Path, timestamp: float, outpath: Path, max_width: int) -> None:
    vf = f"scale='min({max_width},iw)':-2"
    run([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        vf,
        "-q:v",
        "2",
        str(outpath),
    ])


def annotate_frame(raw: Path, outpath: Path, event: Event) -> None:
    im = Image.open(raw).convert("RGB")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = im.size
    title_font = load_font(max(34, int(w * 0.045)), bold=True)
    body_font = load_font(max(24, int(w * 0.031)))
    small_font = load_font(max(20, int(w * 0.026)), bold=True)

    # Soft bottom readability band.
    band_h = int(h * 0.28)
    for y in range(band_h):
        alpha = int(190 * (y / max(1, band_h - 1)))
        draw.line((0, h - band_h + y, w, h - band_h + y), fill=(8, 18, 13, alpha))

    # Top phase pill.
    pill_text = f"{event.label} · 定格观察"
    pill_box = draw.textbbox((0, 0), pill_text, font=small_font)
    pill_w = pill_box[2] - pill_box[0] + 36
    pill_h = pill_box[3] - pill_box[1] + 22
    draw.rounded_rectangle((32, 30, 32 + pill_w, 30 + pill_h), radius=pill_h // 2, fill=(255, 255, 255, 230))
    draw.text((50, 40), pill_text, fill=(8, 120, 79, 255), font=small_font)

    width = max(4, w // 150)
    if event.focus and len(event.focus) == 4:
        # Normalized [cx, cy, rx, ry], only draw when explicitly supplied.
        cx, cy, rx, ry = event.focus
        cx_i, cy_i = int(w * cx), int(h * cy)
        rx_i, ry_i = int(w * rx), int(h * ry)
        draw.ellipse((cx_i - rx_i, cy_i - ry_i, cx_i + rx_i, cy_i + ry_i), outline=(255, 255, 255, 215), width=max(4, w // 160))
    if event.arrow and len(event.arrow) == 4:
        # Normalized [x1, y1, x2, y2], only draw when explicitly supplied.
        ax1, ay1, ax2, ay2 = event.arrow
        x1, y1, x2, y2 = int(w * ax1), int(h * ay1), int(w * ax2), int(h * ay2)
        draw.line((x1, y1, x2, y2), fill=(255, 255, 255, 230), width=width)
        angle = math.atan2(y2 - y1, x2 - x1)
        head = max(22, int(w * 0.04))
        for delta in (math.pi * 0.82, -math.pi * 0.82):
            hx = x2 + int(math.cos(angle + delta) * head)
            hy = y2 + int(math.sin(angle + delta) * head)
            draw.line((x2, y2, hx, hy), fill=(255, 255, 255, 230), width=width)
    draw.line((int(w * 0.08), int(h * 0.76), int(w * 0.80), int(h * 0.78)), fill=(217, 255, 50, 245), width=max(5, w // 130))

    title = event.note
    cue = event.cue or "看准备、击球点和随挥有没有连起来。"
    x = 36
    y = h - band_h + 38
    draw.text((x, y), title, fill=(255, 255, 255, 255), font=title_font)
    draw.text((x, y + int(h * 0.085)), f"下次口令：{cue}", fill=(255, 255, 255, 238), font=body_font)

    out = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    out.save(outpath, quality=94)


def make_video_piece(video: Path, start: float, duration: float, outpath: Path, speed: float, max_width: int) -> bool:
    if duration <= 0.06:
        return False
    factor = 1.0 / speed
    vf = f"setpts={factor:.6f}*PTS,scale='min({max_width},iw)':-2,fps=30,format=yuv420p"
    run([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(video),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        str(outpath),
    ])
    return True


def make_raw_clip(video: Path, start: float, duration: float, outpath: Path, max_width: int) -> None:
    vf = f"scale='min({max_width},iw)':-2,fps=30,format=yuv420p"
    run([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(video),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        str(outpath),
    ])


def make_freeze_clip(image: Path, duration: float, outpath: Path, max_width: int) -> None:
    vf = f"scale='min({max_width},iw)':-2,fps=30,format=yuv420p"
    run([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-loop",
        "1",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(image),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-movflags",
        "+faststart",
        str(outpath),
    ])


def concat_videos(parts: list[Path], outpath: Path) -> None:
    concat_file = outpath.with_suffix(".concat.txt")
    concat_file.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
    run([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(outpath),
    ])


def output_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def process_event(video: Path, event: Event, duration: float, outdir: Path, path_root: Path, pre: float, post: float, speed: float, freeze: float, max_width: int) -> dict:
    phase_dir = outdir / f"{safe_name(event.phase)}-{event.label}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    start, end = clip_bounds(event, duration, pre, post)
    contact = max(start, min(event.timestamp, end))
    clip_duration = end - start

    raw_frame = phase_dir / "freeze_raw.jpg"
    annotated_frame = phase_dir / "freeze_annotated.jpg"
    extract_frame(video, contact, raw_frame, max_width)
    annotate_frame(raw_frame, annotated_frame, event)

    raw_clip = phase_dir / "swing_normal.mp4"
    make_raw_clip(video, start, clip_duration, raw_clip, max_width)

    parts: list[Path] = []
    before = phase_dir / "part_before_slow.mp4"
    if make_video_piece(video, start, contact - start, before, speed, max_width):
        parts.append(before)
    freeze_clip = phase_dir / "part_freeze.mp4"
    make_freeze_clip(annotated_frame, freeze, freeze_clip, max_width)
    parts.append(freeze_clip)
    after = phase_dir / "part_after_slow.mp4"
    if make_video_piece(video, contact, end - contact, after, speed, max_width):
        parts.append(after)

    annotated_clip = phase_dir / "swing_slow_annotated.mp4"
    concat_videos(parts, annotated_clip)

    return {
        "phase": event.phase,
        "label": event.label,
        "timestamp": round(contact, 3),
        "clip_start": round(start, 3),
        "clip_end": round(end, 3),
        "note": event.note,
        "cue": event.cue,
        "focus": event.focus,
        "arrow": event.arrow,
        "normal_clip": output_path(raw_clip, path_root),
        "annotated_slow_clip": output_path(annotated_clip, path_root),
        "freeze_frame": output_path(annotated_frame, path_root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create early/middle/late swing slow-motion clips with freeze annotations.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--event", action="append", default=[], help="phase|timestamp|label|note|cue. Repeat for early/middle/late.")
    parser.add_argument("--events-json", type=Path, help="Read phase_review items from analysis.json.")
    parser.add_argument("--pre", type=float, default=1.25, help="Seconds before contact timestamp.")
    parser.add_argument("--post", type=float, default=1.75, help="Seconds after contact timestamp.")
    parser.add_argument("--speed", type=float, default=0.5, help="Playback speed for slow-motion parts. 0.5 means half speed.")
    parser.add_argument("--freeze", type=float, default=0.9, help="Freeze duration in seconds.")
    parser.add_argument("--max-width", type=int, default=1080)
    parser.add_argument("--path-root", type=Path, help="Root for paths written to swing_clips.json. Default: parent of --outdir.")
    args = parser.parse_args()

    if args.speed <= 0:
        raise SystemExit("--speed must be positive")
    require_bin("ffmpeg")
    require_bin("ffprobe")

    video = args.video.expanduser().resolve()
    if not video.exists():
        raise SystemExit(f"Video not found: {video}")
    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    path_root = args.path_root.expanduser().resolve() if args.path_root else outdir.parent
    duration = ffprobe_duration(video)

    events: list[Event] = []
    if args.events_json:
        events.extend(events_from_json(args.events_json.expanduser().resolve()))
    for raw in args.event:
        events.append(parse_event(raw))
    if not events:
        events = default_events(duration)

    rows = [
        process_event(video, event, duration, outdir, path_root, args.pre, args.post, args.speed, args.freeze, args.max_width)
        for event in events
    ]
    payload = {
        "video": str(video),
        "duration_seconds": round(duration, 3),
        "slow_motion_speed": args.speed,
        "freeze_seconds": args.freeze,
        "phase_review": rows,
    }
    index = outdir / "swing_clips.json"
    index.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"outdir": str(outdir), "index": str(index), "clips": len(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
