#!/usr/bin/env python3
"""Create pose/skeleton overlays for tennis key frames."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

try:
    import cv2
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
except ImportError as exc:
    raise SystemExit(
        "Missing pose dependencies. Install with: "
        "python3 -m pip install mediapipe opencv-python numpy"
    ) from exc


DEFAULT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
)

CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
]
FOCUS_JOINTS = {13, 14, 15, 16, 23, 24, 25, 26, 27, 28}


def parse_crop(raw: str | None, width: int, height: int) -> tuple[int, int, int, int]:
    if not raw:
        return 0, 0, width, height
    parts = [float(p.strip()) for p in raw.split(",")]
    if len(parts) != 4:
        raise SystemExit("--crop must be x1,y1,x2,y2")
    if all(0 <= p <= 1 for p in parts):
        x1, y1, x2, y2 = parts
        return int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height)
    x1, y1, x2, y2 = [int(round(p)) for p in parts]
    x1, x2 = sorted((max(0, x1), min(width, x2)))
    y1, y2 = sorted((max(0, y1), min(height, y2)))
    if x2 <= x1 or y2 <= y1:
        raise SystemExit("--crop resolved to an empty region")
    return x1, y1, x2, y2


def ensure_model(path: Path) -> Path:
    if path.exists() and path.stat().st_size > 1024:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading MediaPipe pose model to {path}", file=sys.stderr)
    urllib.request.urlretrieve(DEFAULT_MODEL_URL, path)
    return path


def detect_pose(crop_bgr: np.ndarray, model_path: Path, confidence: float):
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_rgb)
    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=confidence,
        min_pose_presence_confidence=confidence,
        min_tracking_confidence=confidence,
    )
    with vision.PoseLandmarker.create_from_options(options) as detector:
        result = detector.detect(image)
    if not result.pose_landmarks:
        raise SystemExit("No pose detected. Try a clearer frame or pass --crop around the player.")
    return result.pose_landmarks[0]


def landmark_points(landmarks, crop_shape: tuple[int, int], offset: tuple[int, int]):
    crop_h, crop_w = crop_shape
    ox, oy = offset
    crop_pts = []
    full_pts = []
    for lm in landmarks:
        x = int(lm.x * crop_w)
        y = int(lm.y * crop_h)
        visibility = float(getattr(lm, "visibility", 1.0) or 0.0)
        presence = float(getattr(lm, "presence", 1.0) or 0.0)
        confidence = min(max(visibility, 0.0), max(presence, 0.0)) if presence else visibility
        crop_pts.append((x, y, confidence))
        full_pts.append((ox + x, oy + y, confidence))
    return crop_pts, full_pts


def draw_pose(canvas: np.ndarray, points, threshold: float, scale: float = 1.0) -> None:
    line_color = (0, 255, 190)
    point_color = (255, 80, 40)
    focus_color = (0, 120, 255)
    weak_color = (130, 130, 130)
    for a, b in CONNECTIONS:
        xa, ya, va = points[a]
        xb, yb, vb = points[b]
        if va >= threshold and vb >= threshold:
            cv2.line(canvas, (xa, ya), (xb, yb), line_color, max(2, int(4 * scale)), cv2.LINE_AA)
    for idx, (x, y, value) in enumerate(points):
        if value >= threshold:
            color = focus_color if idx in FOCUS_JOINTS else point_color
            radius = max(3, int((8 if idx in FOCUS_JOINTS else 6) * scale))
            cv2.circle(canvas, (x, y), radius, color, -1, cv2.LINE_AA)
            cv2.circle(canvas, (x, y), radius + 2, (255, 255, 255), max(1, int(scale)), cv2.LINE_AA)
        elif value >= threshold * 0.5:
            cv2.circle(canvas, (x, y), max(2, int(4 * scale)), weak_color, -1, cv2.LINE_AA)


def label_panel(canvas: np.ndarray, title: str, subtitle: str) -> None:
    bg = (18, 26, 31)
    white = (245, 250, 250)
    muted = (210, 230, 230)
    w = canvas.shape[1]
    panel_w = min(w - 42, 760)
    cv2.rectangle(canvas, (24, 28), (24 + panel_w, 128), bg, -1, cv2.LINE_AA)
    cv2.putText(canvas, title[:60], (44, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.86, white, 2, cv2.LINE_AA)
    cv2.putText(canvas, subtitle[:80], (44, 106), cv2.FONT_HERSHEY_SIMPLEX, 0.52, muted, 1, cv2.LINE_AA)


def write_outputs(
    source: Path,
    outdir: Path,
    crop: tuple[int, int, int, int],
    crop_points,
    full_points,
    threshold: float,
    title: str,
    subtitle: str,
) -> dict:
    img_bgr = cv2.imread(str(source))
    x1, y1, x2, y2 = crop
    crop_bgr = img_bgr[y1:y2, x1:x2].copy()
    stem = source.stem
    outdir.mkdir(parents=True, exist_ok=True)

    full_overlay = img_bgr.copy()
    if crop != (0, 0, img_bgr.shape[1], img_bgr.shape[0]):
        cv2.rectangle(full_overlay, (x1, y1), (x2, y2), (0, 255, 190), 3, cv2.LINE_AA)
    draw_pose(full_overlay, full_points, threshold, scale=1.0)
    label_panel(full_overlay, title, subtitle)
    full_path = outdir / f"{stem}_pose_overlay.jpg"
    cv2.imwrite(str(full_path), full_overlay, [cv2.IMWRITE_JPEG_QUALITY, 94])

    crop_overlay = crop_bgr.copy()
    draw_pose(crop_overlay, crop_points, threshold, scale=1.15)
    label_panel(crop_overlay, "Zoomed pose overlay", "Best for joint-level review")
    crop_path = outdir / f"{stem}_pose_crop.jpg"
    cv2.imwrite(str(crop_path), crop_overlay, [cv2.IMWRITE_JPEG_QUALITY, 94])

    left = crop_bgr.copy()
    label_panel(left, "Original crop", "Compare with skeleton overlay")
    sep = np.full((left.shape[0], 18, 3), 245, dtype=np.uint8)
    side = np.concatenate([left, sep, crop_overlay], axis=1)
    side_path = outdir / f"{stem}_pose_comparison.jpg"
    cv2.imwrite(str(side_path), side, [cv2.IMWRITE_JPEG_QUALITY, 94])

    return {
        "source": str(source),
        "overlay_frame": str(full_path),
        "crop_frame": str(crop_path),
        "comparison_frame": str(side_path),
        "visible_landmarks": sum(1 for _, _, value in crop_points if value >= threshold),
        "crop": [x1, y1, x2, y2],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a MediaPipe skeleton overlay for a tennis key frame.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--crop", help="Optional crop as x1,y1,x2,y2 pixels or normalized 0-1 values.")
    parser.add_argument("--model", type=Path, default=Path.home() / ".cache/tennis-video-coach-report/pose_landmarker_full.task")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--title", default="Pose skeleton demo")
    parser.add_argument("--timestamp", default="")
    args = parser.parse_args()

    image = args.image.expanduser().resolve()
    if not image.exists():
        raise SystemExit(f"Image not found: {image}")
    img_bgr = cv2.imread(str(image))
    if img_bgr is None:
        raise SystemExit(f"Could not read image: {image}")
    height, width = img_bgr.shape[:2]
    crop = parse_crop(args.crop, width, height)
    x1, y1, x2, y2 = crop
    crop_bgr = img_bgr[y1:y2, x1:x2].copy()

    model_path = ensure_model(args.model.expanduser().resolve())
    landmarks = detect_pose(crop_bgr, model_path, args.confidence)
    crop_points, full_points = landmark_points(landmarks, crop_bgr.shape[:2], (x1, y1))
    subtitle = "MediaPipe Pose"
    if args.timestamp:
        subtitle = f"{args.timestamp} | {subtitle}"
    result = write_outputs(
        image,
        args.outdir.expanduser().resolve(),
        crop,
        crop_points,
        full_points,
        args.confidence,
        args.title,
        subtitle,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
