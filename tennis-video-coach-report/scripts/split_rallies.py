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


MODE_PRESETS = {
    "shot": {
        "sample_fps": 1.8,
        "sensitivity": 0.62,
        "smooth_seconds": 0.9,
        "min_duration": 2.0,
        "merge_gap": 1.4,
        "pad": 0.45,
    },
    "practice": {
        "sample_fps": 1.5,
        "sensitivity": 0.58,
        "smooth_seconds": 1.2,
        "min_duration": 2.5,
        "merge_gap": 4.5,
        "pad": 0.8,
    },
    "rally": {
        "sample_fps": 2.0,
        "sensitivity": 0.52,
        "smooth_seconds": 1.4,
        "min_duration": 4.0,
        "merge_gap": 3.0,
        "pad": 0.8,
    },
}

MODE_LABELS = {
    "shot": "逐拍模式",
    "practice": "练习小段模式",
    "rally": "Rally 回合模式",
}

MODE_PREFIXES = {
    "shot": "逐拍片段",
    "practice": "练习小段",
    "rally": "回合",
}


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


def mode_settings(args: argparse.Namespace, mode: str) -> dict:
    settings = MODE_PRESETS[mode].copy()
    for key in ("sample_fps", "sensitivity", "smooth_seconds", "min_duration", "merge_gap", "pad"):
        value = getattr(args, key)
        if value is not None:
            settings[key] = value
    return settings


def classify_mode(intervals: list[tuple[float, float]], duration: float, requested_mode: str) -> tuple[str, str]:
    if requested_mode != "auto":
        return requested_mode, "手动选择该模式。"
    if not intervals or duration <= 0:
        return "practice", "片段数量不足，先按练习小段模式处理。"

    durations = [end - start for start, end in intervals]
    median_duration = float(np.median(np.array(durations, dtype=float)))
    clips_per_minute = len(intervals) / max(duration / 60.0, 0.01)
    if median_duration <= 5.5 and clips_per_minute >= 4.0:
        return "shot", "检测到短片段很密集，更适合逐拍检查。"
    if median_duration <= 12.0 and clips_per_minute >= 1.6:
        return "practice", "检测到连续练习片段，保留相邻动作方便看节奏变化。"
    return "rally", "检测到片段间隔更像真实对打回合，按 Rally 回合处理。"


def analyze_motion(
    video: Path,
    metadata: dict,
    crop: tuple[float, float, float, float] | None,
    settings: dict,
    manual_threshold: float | None,
) -> tuple[list[dict], list[tuple[float, float]], float]:
    samples = motion_samples(video, settings["sample_fps"], crop, max_width=360)
    raw_values = [row["motion"] for row in samples]
    window = max(1, int(round(settings["smooth_seconds"] * settings["sample_fps"])))
    smooth_values = smooth(raw_values, window)
    threshold = manual_threshold if manual_threshold is not None else auto_threshold(smooth_values, settings["sensitivity"])
    for row, value in zip(samples, smooth_values):
        row["motion_smooth"] = round(value, 4)
        row["active"] = bool(value >= threshold and value > 0)
    active = [bool(row["active"]) for row in samples]
    intervals = intervals_from_activity(
        samples,
        active,
        float(metadata["duration_seconds"]),
        settings["min_duration"],
        settings["merge_gap"],
        settings["pad"],
    )
    return samples, intervals, threshold


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


def build_rallies(video: Path, outdir: Path, intervals: list[tuple[float, float]], max_width: int, mode: str) -> list[dict]:
    rally_dir = outdir / "rallies"
    poster_dir = outdir / "posters"
    rally_dir.mkdir(parents=True, exist_ok=True)
    poster_dir.mkdir(parents=True, exist_ok=True)
    for old in list(rally_dir.glob("rally_*.mp4")) + list(poster_dir.glob("rally_*.jpg")):
        old.unlink()
    rows = []
    label_prefix = MODE_PREFIXES.get(mode, "片段")
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
            "label": f"{label_prefix} {idx:03d}",
            "time_label": f"{timestamp_label(start)} - {timestamp_label(end)}",
            "clip": rel(clip, outdir),
            "poster": rel(poster, outdir),
        })
    return rows


def viewer_orientation(metadata: dict, rallies: list[dict], outdir: Path) -> str:
    for rally in rallies[:3]:
        poster_path = outdir / str(rally.get("poster", ""))
        if not poster_path.exists():
            continue
        image = cv2.imread(str(poster_path))
        if image is None:
            continue
        height, width = image.shape[:2]
        if height and width:
            return "portrait" if height > width else "landscape"
    return "portrait" if int(metadata.get("height") or 0) > int(metadata.get("width") or 0) else "landscape"


def write_viewer(outdir: Path, index_name: str, rallies: list[dict], mode: str, mode_reason: str, source_orientation: str = "landscape") -> Path:
    cards = []
    mode_label = html.escape(MODE_LABELS.get(mode, mode))
    escaped_reason = html.escape(mode_reason)
    empty_text = "还没有检测到合适片段。可以换一个模式，或调高灵敏度再试一次。"
    is_portrait_source = source_orientation == "portrait"
    for rally in rallies:
        clip = html.escape(rally["clip"])
        poster = html.escape(rally["poster"])
        label = html.escape(rally["label"])
        time_label = html.escape(rally["time_label"])
        duration = html.escape(f"{rally['duration']:.1f}s")
        card_class = "card portrait" if is_portrait_source else "card"
        cards.append(f"""
        <article class="{card_class}" data-id="{rally['id']}">
          <div class="top">
            <label class="favorite-label"><input type="checkbox" class="favorite" data-id="{rally['id']}"> ⭐ 收藏</label>
            <span>⏱ {time_label} · {duration}</span>
          </div>
          <video controls playsinline preload="metadata" poster="{poster}">
            <source src="{clip}" type="video/mp4">
          </video>
          <div class="body">
            <h2>{label}</h2>
            <div class="speeds">
              <button data-speed="0.5">🐢 0.5x</button>
              <button data-speed="0.75">慢速 0.75x</button>
              <button data-speed="1">🎾 正常</button>
              <button data-speed="1.25">轻快 1.25x</button>
              <button data-speed="1.5">⚡ 1.5x</button>
              <button data-speed="2">冲刺 2x</button>
            </div>
            <a class="download" href="{clip}" download>⬇ 下载片段</a>
          </div>
        </article>
        """)
    cards_html = ''.join(cards) if cards else f'<p class="empty">{empty_text}</p>'
    grid_class = "grid portrait-heavy" if is_portrait_source else "grid"
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>网球片段浏览器</title>
  <style>
    * {{ box-sizing: border-box; }}
    :root {{
      --ink: #18241c;
      --muted: #6a746c;
      --green: #13865a;
      --green-soft: #e8f5eb;
      --pink: #f37a9d;
      --pink-soft: #fff0f4;
      --sun: #f7c948;
      --paper: #fffdf8;
      --line: rgba(24, 36, 28, .12);
    }}
    body {{
      margin: 0;
      background: #fff8ef;
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    }}
    main {{ width: min(100%, 1100px); margin: 0 auto; padding: 22px 12px 40px; }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      margin: -22px -12px 18px;
      padding: 16px;
      background: rgba(255, 248, 239, .95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--line);
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
    .logo {{
      position: relative;
      width: 52px;
      height: 52px;
      display: inline-grid;
      place-items: center;
      border: 2px solid rgba(19, 134, 90, .22);
      border-radius: 50%;
      background: var(--paper);
      font-size: 27px;
      box-shadow: 0 8px 18px rgba(24, 36, 28, .08);
      flex: 0 0 auto;
    }}
    .logo::after {{
      content: "🎾";
      position: absolute;
      right: -7px;
      bottom: -7px;
      width: 25px;
      height: 25px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: var(--paper);
      border: 1px solid rgba(19, 134, 90, .2);
      font-size: 17px;
    }}
    h1 {{ margin: 0; font-size: clamp(27px, 5vw, 38px); line-height: 1.08; letter-spacing: 0; }}
    .hint {{ margin: 0; color: var(--muted); line-height: 1.55; font-size: 15px; }}
    .mode-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 32px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--paper);
      color: var(--ink);
      font-size: 13px;
      font-weight: 800;
    }}
    .pill strong {{ color: var(--green); }}
    .selected {{
      margin-top: 12px;
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 8px;
      background: var(--paper);
      border: 1px solid var(--line);
    }}
    .selected strong {{ color: var(--green); }}
    code {{ white-space: pre-wrap; word-break: break-word; color: #465047; font-size: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap: 16px; }}
    .grid.portrait-heavy {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      max-width: 920px;
      margin: 0 auto;
      gap: 14px;
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 12px 28px rgba(24, 36, 28, .08);
    }}
    .top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      font-size: 13px;
      color: var(--muted);
    }}
    .favorite-label {{ color: var(--green); font-weight: 900; white-space: nowrap; }}
    input[type="checkbox"] {{ accent-color: var(--pink); }}
    video {{ display: block; width: 100%; background: #dfe6dc; aspect-ratio: 16 / 9; object-fit: contain; }}
    .card.portrait video {{
      aspect-ratio: 9 / 16;
      max-height: min(78vh, 760px);
    }}
    .card.portrait .top {{
      display: grid;
      justify-content: stretch;
      gap: 4px;
      line-height: 1.25;
    }}
    .card.portrait .body {{ padding: 11px; }}
    .card.portrait h2 {{ font-size: 17px; }}
    .card.portrait .speeds {{ gap: 6px; }}
    .card.portrait button, .card.portrait .download {{
      padding: 7px 9px;
      font-size: 12px;
    }}
    .body {{ padding: 14px; }}
    h2 {{ margin: 0 0 10px; font-size: 20px; line-height: 1.2; letter-spacing: 0; }}
    .speeds {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
    button, .download {{
      border: 1px solid rgba(19, 134, 90, .16);
      border-radius: 999px;
      padding: 8px 11px;
      background: var(--green-soft);
      color: var(--green);
      font-weight: 800;
      text-decoration: none;
      cursor: pointer;
      font-size: 13px;
    }}
    button:hover, .download:hover {{ background: var(--pink-soft); color: #ba365d; border-color: rgba(243, 122, 157, .28); }}
    .download {{ display: inline-flex; }}
    .empty {{
      grid-column: 1 / -1;
      margin: 0;
      padding: 24px;
      border: 1px dashed rgba(19, 134, 90, .35);
      border-radius: 8px;
      background: var(--paper);
      color: var(--muted);
      text-align: center;
    }}
    footer {{
      padding: 28px 0 4px;
      text-align: center;
      color: var(--muted);
      font-size: 14px;
    }}
    @media (max-width: 520px) {{
      main {{ padding-left: 8px; padding-right: 8px; }}
      header {{ margin-left: -8px; margin-right: -8px; padding-left: 12px; padding-right: 12px; }}
      .grid {{ grid-template-columns: 1fr; gap: 14px; }}
      .grid.portrait-heavy {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
      .card.portrait video {{ max-height: 76vh; }}
      .top {{ align-items: flex-start; }}
      .card.portrait .top {{ padding: 8px; font-size: 12px; }}
      .card.portrait .body {{ padding: 9px; }}
      .card.portrait h2 {{ font-size: 16px; margin-bottom: 8px; }}
      .card.portrait .speeds {{ gap: 5px; margin-bottom: 8px; }}
      .card.portrait button, .card.portrait .download {{ padding: 6px 7px; font-size: 11px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="brand">
        <span class="logo" aria-hidden="true">👩🏻‍🦰</span>
        <div>
          <h1>网球片段浏览器</h1>
          <p class="hint">查看系统自动拆出的候选片段，支持慢放、加速、收藏、下载，也可以把喜欢的片段合成一条精选视频。</p>
        </div>
      </div>
      <div class="mode-row">
        <span class="pill">🎬 当前模式：<strong>{mode_label}</strong></span>
        <span class="pill">🧠 判断依据：{escaped_reason}</span>
        <span class="pill">🎾 片段数：<strong>{len(rallies)}</strong></span>
      </div>
      <div class="selected">
        <strong>已收藏片段：<span id="selected">还没有收藏</span></strong>
        <code id="command">收藏几个片段后，可以把这里的命令交给 Codex 合成精选视频。</code>
      </div>
    </header>
    <section class="{grid_class}">
      {cards_html}
    </section>
    <footer>Made with Tennis Video Coach Report</footer>
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
      selectedEl.textContent = ids.length ? ids.join(",") : "还没有收藏";
      commandEl.textContent = ids.length
        ? `python3 <skill-root>/scripts/compile_rallies.py {html.escape(index_name)} --ids ${{ids.join(",")}} --out selected-rallies.mp4`
        : "收藏几个片段后，可以把这里的命令交给 Codex 合成精选视频。";
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
    parser.add_argument("--mode", choices=["auto", "shot", "practice", "rally"], default="auto", help="auto guesses the best review format; shot/practice/rally force a format.")
    parser.add_argument("--sample-fps", type=float)
    parser.add_argument("--sensitivity", type=float, help="0.05-0.95; higher finds more/lower-motion rallies.")
    parser.add_argument("--threshold", type=float, help="Manual motion threshold. Use when auto split is too strict or loose.")
    parser.add_argument("--smooth-seconds", type=float)
    parser.add_argument("--min-duration", type=float)
    parser.add_argument("--merge-gap", type=float)
    parser.add_argument("--pad", type=float)
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
    manual_threshold = float(args.threshold) if args.threshold is not None else None
    initial_mode = "practice" if args.mode == "auto" else args.mode
    settings = mode_settings(args, initial_mode)
    samples, intervals, threshold = analyze_motion(video, metadata, crop, settings, manual_threshold)
    detected_mode, mode_reason = classify_mode(intervals, float(metadata["duration_seconds"]), args.mode)
    if args.mode == "auto" and detected_mode != initial_mode:
        settings = mode_settings(args, detected_mode)
        samples, intervals, threshold = analyze_motion(video, metadata, crop, settings, manual_threshold)
        mode_reason = f"{mode_reason} 已按该模式参数重新拆分。"

    rallies = build_rallies(video, outdir, intervals, args.max_width, detected_mode)
    index_path = outdir / "rally_index.json"
    payload = {
        "video": metadata,
        "settings": {
            "requested_mode": args.mode,
            "mode": detected_mode,
            "mode_label": MODE_LABELS.get(detected_mode, detected_mode),
            "mode_reason": mode_reason,
            "sample_fps": settings["sample_fps"],
            "sensitivity": settings["sensitivity"],
            "threshold": round(threshold, 4),
            "smooth_seconds": settings["smooth_seconds"],
            "min_duration": settings["min_duration"],
            "merge_gap": settings["merge_gap"],
            "pad": settings["pad"],
            "crop": crop,
        },
        "samples": samples,
        "rallies": rallies,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    source_orientation = viewer_orientation(metadata, rallies, outdir)
    viewer = write_viewer(outdir, index_path.name, rallies, detected_mode, mode_reason, source_orientation)
    print(json.dumps({
        "outdir": str(outdir),
        "index": str(index_path),
        "viewer": str(viewer),
        "rallies": len(rallies),
        "requested_mode": args.mode,
        "mode": detected_mode,
        "threshold": round(threshold, 4),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
