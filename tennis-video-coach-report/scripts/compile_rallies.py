#!/usr/bin/env python3
"""Compile selected rally clips into one continuous MP4."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def require_bin(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def parse_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.append(int(part))
    return ids


def ids_from_favorites(path: Path) -> list[int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [int(value) for value in data]
    for key in ("ids", "favorites", "rallies", "selected"):
        if key in data:
            return [int(value) for value in data[key]]
    raise SystemExit("Favorites file must be a JSON list or contain ids/favorites/rallies/selected.")


def selected_clips(index_path: Path, ids: list[int]) -> list[Path]:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    root = index_path.parent
    by_id = {int(row["id"]): row for row in data.get("rallies", [])}
    clips = []
    missing = []
    for rally_id in ids:
        row = by_id.get(rally_id)
        if not row:
            missing.append(rally_id)
            continue
        clip = root / row["clip"]
        if not clip.exists():
            raise SystemExit(f"Clip file missing for rally {rally_id}: {clip}")
        clips.append(clip)
    if missing:
        raise SystemExit(f"Rally IDs not found: {missing}")
    if not clips:
        raise SystemExit("No clips selected.")
    return clips


def concat_copy(clips: list[Path], outpath: Path) -> None:
    concat_file = outpath.with_suffix(".concat.txt")
    concat_file.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
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


def concat_reencode(clips: list[Path], outpath: Path) -> None:
    concat_file = outpath.with_suffix(".concat.txt")
    concat_file.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
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
        "-vf",
        "fps=30,format=yuv420p",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile selected rally clips into one MP4.")
    parser.add_argument("rally_index", type=Path)
    parser.add_argument("--ids", help="Comma-separated rally IDs, for example 1,3,5.")
    parser.add_argument("--favorites-file", type=Path, help="JSON list or object containing selected rally IDs.")
    parser.add_argument("--out", type=Path, default=Path("selected-rallies.mp4"))
    parser.add_argument("--reencode", action="store_true", help="Force re-encoding instead of stream copy.")
    args = parser.parse_args()

    require_bin("ffmpeg")
    index_path = args.rally_index.expanduser().resolve()
    if not index_path.exists():
        raise SystemExit(f"Rally index not found: {index_path}")
    ids = parse_ids(args.ids)
    if args.favorites_file:
        ids.extend(ids_from_favorites(args.favorites_file.expanduser().resolve()))
    ids = list(dict.fromkeys(ids))
    clips = selected_clips(index_path, ids)
    outpath = args.out.expanduser()
    if not outpath.is_absolute():
        outpath = index_path.parent / outpath
    outpath.parent.mkdir(parents=True, exist_ok=True)

    if args.reencode:
        concat_reencode(clips, outpath)
    else:
        try:
            concat_copy(clips, outpath)
        except subprocess.CalledProcessError:
            print("Stream-copy concat failed; retrying with re-encode.", file=sys.stderr)
            concat_reencode(clips, outpath)
    print(json.dumps({
        "out": str(outpath),
        "ids": ids,
        "clips": len(clips),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
