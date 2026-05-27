#!/usr/bin/env python3
"""Split long tennis videos into candidate rally clips and a review viewer."""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit("OpenCV and NumPy are required: python3 -m pip install opencv-python numpy") from exc


def require_bin(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


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


def parse_crop(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [float(part.strip()) for part in raw.split(",")]
    if len(parts) != 4:
        raise SystemExit("--crop must be x1,y1,x2,y2 normalized values between 0 and 1")
    if not all(0 <= part <= 1 for part in parts):
        raise SystemExit("--crop uses normalized values only, for example 0.05,0.2,0.95,0.95")
    x1, y1, x2, y2 = parts
    if x2 <= x1 or y2 <= y1:
        raise SystemExit("--crop resolved to an empty region")
    return x1, y1, x2, y2


def crop_frame(frame: np.ndarray, crop: tuple[float, float, float, float] | None) -> np.ndarray:
    if crop is None:
        return frame
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = crop
    return frame[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)]


def motion_samples(video: Path, sample_fps: float, crop: tuple[float, float, float, float] | None, max_width: int) -> list[dict]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {video}")
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / source_fps if source_fps else 0
    step = max(1, int(round(source_fps / sample_fps)))
    samples: list[dict] = []
    previous: np.ndarray | None = None
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index % step != 0:
            index += 1
            continue
        timestamp = index / source_fps if source_fps else 0
        roi = crop_frame(frame, crop)
        h, w = roi.shape[:2]
        if w > max_width:
            ratio = max_width / w
            roi = cv2.resize(roi, (max_width, max(2, int(h * ratio))))
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)
        score = 0.0
        if previous is not None:
            diff = cv2.absdiff(gray, previous)
            score = float(np.mean(diff))
        samples.append({"time": round(timestamp, 3), "motion": round(score, 4)})
        previous = gray
        index += 1
    cap.release()
    if duration and samples and samples[-1]["time"] < duration:
        samples.append({"time": round(duration, 3), "motion": 0.0})
    return samples


def smooth(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    window = max(1, window)
    radius = window // 2
    smoothed = []
    for idx in range(len(values)):
        start = max(0, idx - radius)
        end = min(len(values), idx + radius + 1)
        smoothed.append(float(np.mean(values[start:end])))
    return smoothed


def auto_threshold(values: list[float], sensitivity: float) -> float:
    positive = np.array([value for value in values if value > 0], dtype=float)
    if positive.size == 0:
        return 0.0
    p50 = float(np.percentile(positive, 50))
    p90 = float(np.percentile(positive, 90))
    sensitivity = min(0.95, max(0.05, sensitivity))
    return p50 + (p90 - p50) * (1.0 - sensitivity)


def intervals_from_activity(
    samples: list[dict],
    active: list[bool],
    duration: float,
    min_duration: float,
    merge_gap: float,
    pad: float,
) -> list[tuple[float, float]]:
    raw: list[tuple[float, float]] = []
    start: float | None = None
    last_time = 0.0
    for row, is_active in zip(samples, active):
        time = float(row["time"])
        last_time = time
        if is_active and start is None:
            start = time
        elif not is_active and start is not None:
            raw.append((start, time))
            start = None
    if start is not None:
        raw.append((start, last_time or duration))

    merged: list[tuple[float, float]] = []
    for start, end in raw:
        if not merged or start - merged[-1][1] > merge_gap:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], end)

    padded = []
    for start, end in merged:
        start = max(0.0, start - pad)
        end = min(duration, end + pad)
        if end - start >= min_duration:
            padded.append((round(start, 3), round(end, 3)))
    return padded


def timestamp_label(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:05.2f}"


def make_clip(video: Path, start: float, end: float, outpath: Path, max_width: int) -> None:
    duration = max(0.1, end - start)
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


def make_poster(video: Path, timestamp: float, outpath: Path, max_width: int) -> None:
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


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def build_rallies(video: Path, outdir: Path, intervals: list[tuple[float, float]], max_width: int) -> list[dict]:
    rally_dir = outdir / "rallies"
    poster_dir = outdir / "posters"
    rally_dir.mkdir(parents=True, exist_ok=True)
    poster_dir.mkdir(parents=True, exist_ok=True)
    for old in list(rally_dir.glob("rally_*.mp4")) + list(poster_dir.glob("rally_*.jpg")):
        old.unlink()
    rows = []
    for idx, (start, end) in enumerate(intervals, start=1):
        stem = f"rally_{idx:03d}_t{int(start):06d}-{int(end):06d}"
        clip = rally_dir / f"{stem}.mp4"
        poster = poster_dir / f"{stem}.jpg"
        make_clip(video, start, end, clip, max_width)
        make_poster(video, (start + end) / 2, poster, max_width)
        rows.append({
            "id": idx,
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "label": f"Rally {idx:03d}",
            "time_label": f"{timestamp_label(start)} - {timestamp_label(end)}",
            "clip": rel(clip, outdir),
            "poster": rel(poster, outdir),
        })
    return rows


def write_viewer(outdir: Path, index_name: str, rallies: list[dict]) -> Path:
    cards = []
    for rally in rallies:
        clip = html.escape(rally["clip"])
        poster = html.escape(rally["poster"])
        label = html.escape(rally["label"])
        time_label = html.escape(rally["time_label"])
        duration = html.escape(f"{rally['duration']:.1f}s")
        cards.append(f"""
        <article class="card" data-id="{rally['id']}">
          <div class="top">
            <label><input type="checkbox" class="favorite" data-id="{rally['id']}"> Favorite</label>
            <span>{time_label} · {duration}</span>
          </div>
          <video controls playsinline preload="metadata" poster="{poster}">
            <source src="{clip}" type="video/mp4">
          </video>
          <div class="body">
            <h2>{label}</h2>
            <div class="speeds">
              <button data-speed="0.5">0.5x</button>
              <button data-speed="0.75">0.75x</button>
              <button data-speed="1">1x</button>
              <button data-speed="1.25">1.25x</button>
              <button data-speed="1.5">1.5x</button>
              <button data-speed="2">2x</button>
            </div>
            <a class="download" href="{clip}" download>Download clip</a>
          </div>
        </article>
        """)
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tennis Rally Review</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f5f2ea;
      color: #132019;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ width: min(100%, 1080px); margin: 0 auto; padding: 24px 16px 48px; }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      margin: -24px -16px 20px;
      padding: 18px 16px;
      background: rgba(245, 242, 234, .94);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(19, 32, 25, .1);
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; line-height: 1.05; }}
    .hint {{ margin: 0; color: #56635b; line-height: 1.42; }}
    .selected {{
      margin-top: 12px;
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 14px;
      background: #fff;
      border: 1px solid rgba(19, 32, 25, .1);
    }}
    code {{ white-space: pre-wrap; word-break: break-word; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .card {{
      background: #fff;
      border: 1px solid rgba(19, 32, 25, .1);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 14px 36px rgba(19, 32, 25, .08);
    }}
    .top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      font-size: 13px;
      color: #56635b;
    }}
    .top label {{ color: #08784f; font-weight: 800; }}
    video {{ display: block; width: 100%; background: #dfe6dc; }}
    .body {{ padding: 14px; }}
    h2 {{ margin: 0 0 10px; font-size: 22px; }}
    .speeds {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
    button, .download {{
      border: 0;
      border-radius: 999px;
      padding: 8px 11px;
      background: #e7f0e8;
      color: #08784f;
      font-weight: 800;
      text-decoration: none;
      cursor: pointer;
    }}
    .download {{ display: inline-flex; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Tennis Rally Review</h1>
      <p class="hint">Review candidate rallies, play at different speeds, download clips, and favorite the clips you want to compile.</p>
      <div class="selected">
        <strong>Selected rally IDs: <span id="selected">none</span></strong>
        <code id="command">Pick favorites to generate a compile command.</code>
      </div>
    </header>
    <section class="grid">
      {''.join(cards)}
    </section>
  </main>
  <script>
    const storageKey = "tennis-rally-favorites:{html.escape(index_name)}";
    const selectedEl = document.getElementById("selected");
    const commandEl = document.getElementById("command");
    const boxes = [...document.querySelectorAll(".favorite")];
    function getFavorites() {{
      try {{ return JSON.parse(localStorage.getItem(storageKey) || "[]"); }}
      catch {{ return []; }}
    }}
    function setFavorites(ids) {{
      localStorage.setItem(storageKey, JSON.stringify(ids));
      renderFavorites();
    }}
    function renderFavorites() {{
      const ids = getFavorites().sort((a, b) => a - b);
      selectedEl.textContent = ids.length ? ids.join(",") : "none";
      commandEl.textContent = ids.length
        ? `python3 <skill-root>/scripts/compile_rallies.py {html.escape(index_name)} --ids ${{ids.join(",")}} --out selected-rallies.mp4`
        : "Pick favorites to generate a compile command.";
      boxes.forEach(box => box.checked = ids.includes(Number(box.dataset.id)));
    }}
    boxes.forEach(box => box.addEventListener("change", () => {{
      const id = Number(box.dataset.id);
      const ids = new Set(getFavorites());
      box.checked ? ids.add(id) : ids.delete(id);
      setFavorites([...ids]);
    }}));
    document.querySelectorAll("button[data-speed]").forEach(button => {{
      button.addEventListener("click", () => {{
        const video = button.closest(".card").querySelector("video");
        video.playbackRate = Number(button.dataset.speed);
        video.play();
      }});
    }});
    renderFavorites();
  </script>
</body>
</html>
"""
    viewer = outdir / "rally_viewer.html"
    viewer.write_text(html_text, encoding="utf-8")
    return viewer


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a long tennis video into candidate rally clips.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--sensitivity", type=float, default=0.55, help="0.05-0.95; higher finds more/lower-motion rallies.")
    parser.add_argument("--threshold", type=float, help="Manual motion threshold. Use when auto split is too strict or loose.")
    parser.add_argument("--smooth-seconds", type=float, default=1.25)
    parser.add_argument("--min-duration", type=float, default=3.0)
    parser.add_argument("--merge-gap", type=float, default=2.0)
    parser.add_argument("--pad", type=float, default=0.6)
    parser.add_argument("--crop", help="Optional normalized detection crop x1,y1,x2,y2.")
    parser.add_argument("--max-width", type=int, default=1080)
    args = parser.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")
    video = args.video.expanduser().resolve()
    if not video.exists():
        raise SystemExit(f"Video not found: {video}")
    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    metadata = ffprobe(video)
    crop = parse_crop(args.crop)
    samples = motion_samples(video, args.sample_fps, crop, max_width=360)
    raw_values = [row["motion"] for row in samples]
    window = max(1, int(round(args.smooth_seconds * args.sample_fps)))
    smooth_values = smooth(raw_values, window)
    threshold = float(args.threshold) if args.threshold is not None else auto_threshold(smooth_values, args.sensitivity)
    for row, value in zip(samples, smooth_values):
        row["motion_smooth"] = round(value, 4)
        row["active"] = bool(value >= threshold and value > 0)
    active = [bool(row["active"]) for row in samples]
    intervals = intervals_from_activity(
        samples,
        active,
        float(metadata["duration_seconds"]),
        args.min_duration,
        args.merge_gap,
        args.pad,
    )
    rallies = build_rallies(video, outdir, intervals, args.max_width)
    index_path = outdir / "rally_index.json"
    payload = {
        "video": metadata,
        "settings": {
            "sample_fps": args.sample_fps,
            "sensitivity": args.sensitivity,
            "threshold": round(threshold, 4),
            "smooth_seconds": args.smooth_seconds,
            "min_duration": args.min_duration,
            "merge_gap": args.merge_gap,
            "pad": args.pad,
            "crop": crop,
        },
        "samples": samples,
        "rallies": rallies,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    viewer = write_viewer(outdir, index_path.name, rallies)
    print(json.dumps({
        "outdir": str(outdir),
        "index": str(index_path),
        "viewer": str(viewer),
        "rallies": len(rallies),
        "threshold": round(threshold, 4),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
