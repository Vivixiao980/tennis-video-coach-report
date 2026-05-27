---
name: tennis-video-coach-report
description: Create shareable tennis practice video analysis reports. Use when a user provides tennis video files or key frames and asks for AI tennis coaching, beginner-friendly technique review, skeleton/pose overlays, slow-motion swing clips, contact sheets, HTML reports, mobile PNG reports, or PDF reports. This public skill generates standalone local artifacts only; it does not update private diaries, cloud documents, remote docs, or training ledgers.
---

# Tennis Video Coach Report

## Overview

Turn a tennis practice video into a portable coaching package: extracted frames, contact sheets, selected key moments, optional MediaPipe skeleton overlays, early/middle/late slow-motion clips, and a mobile-friendly HTML/PNG/PDF report.

This is the public/shareable version. Keep all outputs in the requested output folder or a new local run folder. Do not write to private diary systems, cloud documents, or user-specific paths unless the user explicitly asks.

## Dependencies

Required command-line tools: `ffmpeg`, `ffprobe`.

Python packages used by scripts: see `references/requirements.txt`.

When dependencies are missing, prefer an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r <skill-root>/references/requirements.txt
.venv/bin/python -m playwright install chromium
```

Use the active Python if the packages already exist. Do not install globally unless the user asks.

## Workflow

1. Resolve the video file.
   - Prefer a path the user provided.
   - If the user says the video was uploaded but gives no path, search recent `.mov`, `.mp4`, `.m4v` files in `~/Downloads`, `~/Desktop`, and the current workspace.
   - Keep the original video untouched.

2. Create a run folder.
   - Default: `<cwd>/tennis-video-analysis/<YYYY-MM-DD>-<video-stem>-<YYYYMMDD-HHMMSS>/`.
   - Store all derived files inside that folder: frames, contact sheets, pose overlays, clips, `analysis.json`, and report exports.

3. Extract frames and contact sheets.
   - Run:
     ```bash
     python3 <skill-root>/scripts/extract_tennis_frames.py <video> --outdir <run-folder>
     ```
   - Review `contact_sheets/` and `candidate_frames/`.
   - Pick 4-8 evidence moments: cover, ready/preparation, contact or near-contact, follow-through, main issue, and one positive frame.
   - Do not write a strong diagnosis before choosing the exact frame or clip that supports it.

4. Add skeleton overlays when useful.
   - Use skeletons for visible full-body or half-body frames. Prefer a frame where the player is not heavily occluded.
   - If multiple people are visible, crop around the player:
     ```bash
     python3 <skill-root>/scripts/pose_overlay.py <key-frame.jpg> --outdir <run-folder>/generated_assets --crop x1,y1,x2,y2 --timestamp "38.50s" --title "Pose skeleton demo"
     ```
   - The script writes full-frame overlay, crop overlay, comparison image, and JSON metadata.
   - Put the resulting paths in `analysis.json` under `pose_analysis`.

5. Create slow-motion phase clips when requested or useful.
   - Use early/middle/late representative swings, preferably selected from contact sheets rather than raw thirds.
   - Run:
     ```bash
     python3 <skill-root>/scripts/make_swing_clips.py <video> --outdir <run-folder>/swing_clips \
       --event "early|31.75|Early|issue note|next cue" \
       --event "middle|147.25|Middle|issue note|next cue" \
       --event "late|280.75|Late|issue note|next cue"
     ```
   - Merge `swing_clips/swing_clips.json` phase paths into `analysis.json`.

6. Write `analysis.json`.
   - Follow `references/report-schema.md`.
   - Read `references/analysis-checklist.md` before writing coaching claims.
   - Use plain coaching language. For beginners, choose one primary bottleneck and at most two secondary issues.
   - Include:
     - title, date, player, video metadata, confidence
     - one-liner and main focus
     - coach summary
     - capture quality
     - optional `pose_analysis`
     - phase review
     - highlights
     - issues
     - next practice
     - training prescription

7. Render the report.
   - Run:
     ```bash
     python3 <skill-root>/scripts/render_tennis_report.py <run-folder>/analysis.json --outdir <run-folder>/report --pdf --png
     ```
   - If Playwright is unavailable, still deliver HTML and explain that PDF/PNG export was skipped.

## Pose Analysis Guidance

Skeleton overlays are good evidence for:

- shoulder/hip orientation during preparation
- elbow/wrist distance from the body
- whether the player is cramped at contact
- knee bend and lower-body support
- whether the player stands up too early
- finish position and follow-through completeness
- long-term comparison of the same movement pattern

Skeleton overlays are not enough for:

- exact racket face angle
- exact contact moment
- ball speed, spin, or trajectory
- precise 3D hip/shoulder rotation
- injury or medical diagnosis

State uncertainty when the player is small, blurred, occluded, or partly outside the frame. Treat pose output as an evidence layer, not the whole analysis.

## Output Standard

Deliver these files when feasible:

- `metadata.json`
- `frame_index.json`
- `contact_sheets/*.jpg`
- `candidate_frames/*.jpg`
- `generated_assets/*pose*.jpg` when pose is enabled
- `swing_clips/*/swing_slow_annotated.mp4` when slow motion is enabled
- `swing_clips/*/freeze_annotated.jpg`
- `analysis.json`
- `report/index.html`
- `report/tennis-report-mobile.png`
- `report/tennis-report.pdf`

In the final response, link the HTML report, PNG, PDF, and 2-4 representative visual assets using absolute paths.

## Boundaries

- Do not update user-specific training ledgers, private cloud folders, docs, Notion, Google Drive, or any remote destination.
- Do not include private user names, paths, API tokens, or document IDs in this public skill.
- Do not overdiagnose. One actionable correction beats a long fault list.
- Do not shame the player. Use concrete, friendly coaching language.
