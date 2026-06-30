# Tennis Video Coach Report

A shareable Codex skill for turning tennis practice videos into coach-style reports.

It can extract key frames, split long videos into candidate rally or practice clips, create a Chinese-first rally viewer, generate slow-motion swing clips, add optional pose/skeleton overlays, and render a portable HTML/PNG/PDF report.

## What It Does

- Extracts representative frames and contact sheets from a tennis video
- Splits long videos into candidate clips with `shot`, `practice`, `rally`, or `auto` mode
- Generates a rally viewer with speed controls, favorites, and clip downloads
- Compiles selected clips into one highlight video
- Creates slow-motion swing clips for early, middle, and late moments
- Adds MediaPipe pose overlays when the player is visible enough
- Renders a coaching report as HTML, mobile PNG, and PDF

## Requirements

Install command-line tools:

```bash
brew install ffmpeg
```

Install Python dependencies in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r tennis-video-coach-report/references/requirements.txt
.venv/bin/python -m playwright install chromium
```

`ffmpeg` and `ffprobe` are required. Playwright is only needed for PNG/PDF export.

## Install As A Codex Skill

Clone this repository, then copy or symlink the skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/tennis-video-coach-report" ~/.codex/skills/tennis-video-coach-report
```

Restart Codex if it does not discover the skill immediately.

## Quick Start

Ask Codex:

```text
Use tennis-video-coach-report to analyze /path/to/my-tennis-video.mov.
Split useful clips, add slow-motion moments, and generate HTML, PNG, and PDF reports.
```

The skill creates a local run folder and keeps generated files inside it. It does not update private journals, cloud documents, remote docs, or training ledgers.

## Useful Script Commands

Extract frames:

```bash
python3 tennis-video-coach-report/scripts/extract_tennis_frames.py /path/to/video.mov --outdir ./runs/demo
```

Split candidate rallies or practice clips:

```bash
python3 tennis-video-coach-report/scripts/split_rallies.py /path/to/video.mov --outdir ./runs/demo/rally_review --mode auto
```

Create slow-motion clips:

```bash
python3 tennis-video-coach-report/scripts/make_swing_clips.py /path/to/video.mov --outdir ./runs/demo/swing_clips \
  --event "early|12.50|Early|preparation is late|turn earlier" \
  --event "middle|38.20|Middle|contact is cramped|leave more space" \
  --event "late|63.80|Late|finish is incomplete|finish across the body"
```

Render a report:

```bash
python3 tennis-video-coach-report/scripts/render_tennis_report.py ./runs/demo/analysis.json --outdir ./runs/demo/report --pdf --png
```

Compile favorite clips after choosing IDs in the rally viewer:

```bash
python3 tennis-video-coach-report/scripts/compile_rallies.py ./runs/demo/rally_review/rally_index.json --ids 1,3,5 --out ./runs/demo/selected-rallies.mp4
```

## Outputs

Typical outputs include:

- `rally_review/rally_viewer.html`
- `rally_review/rallies/*.mp4`
- `contact_sheets/*.jpg`
- `candidate_frames/*.jpg`
- `generated_assets/*pose*.jpg`
- `swing_clips/*/swing_slow_annotated.mp4`
- `analysis.json`
- `report/index.html`
- `report/tennis-report-mobile.png`
- `report/tennis-report.pdf`

## Notes

This is a coaching-assist workflow, not a professional biomechanics system. Automatic rally splitting and pose estimation are useful evidence layers, but they should be reviewed by a human before making strong technical conclusions.

## License

MIT
