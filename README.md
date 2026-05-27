# Tennis Video Coach Report

A shareable Codex skill for turning tennis practice videos into coach-style reports with rally segmentation, clip review/download, favorite-rally compilation, optional skeleton overlays, slow-motion swing clips, and HTML/PNG/PDF exports.

## Install

Copy the skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R tennis-video-coach-report ~/.codex/skills/
```

Restart Codex, then ask:

```text
Use tennis-video-coach-report to analyze this tennis practice video and generate an HTML, PNG, and PDF report with skeleton key frames.
```

For long continuous videos:

```text
Use tennis-video-coach-report to split this long tennis video into rallies, create a rally viewer, and compile my favorite rallies into one video.
```

## Requirements

- `ffmpeg` and `ffprobe`
- Python packages listed in `tennis-video-coach-report/references/requirements.txt`

For an isolated Python environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r tennis-video-coach-report/references/requirements.txt
.venv/bin/python -m playwright install chromium
```

## Notes

This public version only creates local report artifacts. It does not sync to private diaries, cloud docs, or training ledgers.

## Rally Workflow

The rally splitter creates:

- `rally_review/rally_viewer.html`
- `rally_review/rally_index.json`
- `rally_review/rallies/*.mp4`
- `rally_review/posters/*.jpg`

After reviewing and favoriting clips, compile selected IDs:

```bash
python3 tennis-video-coach-report/scripts/compile_rallies.py rally_review/rally_index.json --ids 1,3,5 --out selected-rallies.mp4
```
