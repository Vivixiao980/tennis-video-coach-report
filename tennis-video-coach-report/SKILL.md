---
name: tennis-video-coach-report
description: Create shareable tennis practice video analysis reports. Use when a user provides tennis video files or key frames and asks for AI tennis coaching, beginner-friendly technique review, automatic rally segmentation, rally review/download, compiling favorite rallies into one video, skeleton/pose overlays, slow-motion swing clips, contact sheets, HTML reports, mobile PNG reports, or PDF reports. This public skill generates standalone local artifacts only; it does not update private diaries, cloud documents, remote docs, or training ledgers.
---

# Tennis Video Coach Report

## Overview

Turn a tennis practice video into a portable coaching package: rally clips, a rally review viewer, extracted frames, contact sheets, selected key moments, optional MediaPipe skeleton overlays, early/middle/late slow-motion clips, and a mobile-friendly HTML/PNG/PDF report.

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

4. Split long videos into candidate rallies when requested.
   - Use this when the user has long continuous footage and wants to review rallies, save clips, or build a highlight video.
   - Choose a review mode:
     - `--mode auto`: default. Detects whether the footage looks like dense shots, practice chunks, or real rallies.
     - `--mode shot`: short 2-6 second clips for checking individual swings.
     - `--mode practice`: grouped practice chunks for coach feeding, ball-machine sessions, and repeated drills.
     - `--mode rally`: longer active-play intervals for true point/rally review.
   - Run:
     ```bash
     python3 <skill-root>/scripts/split_rallies.py <video> --outdir <run-folder>/rally_review --mode auto
     ```
   - If the user wants two browsing styles, generate both:
     ```bash
     python3 <skill-root>/scripts/split_rallies.py <video> --outdir <run-folder>/rally_review_shots --mode shot
     python3 <skill-root>/scripts/split_rallies.py <video> --outdir <run-folder>/rally_review_practice --mode practice
     ```
   - If the camera includes irrelevant motion outside the court, use a normalized crop:
     ```bash
     python3 <skill-root>/scripts/split_rallies.py <video> --outdir <run-folder>/rally_review --crop 0.05,0.20,0.95,0.95
     ```
   - Open `rally_review/rally_viewer.html`. The viewer is Chinese-first and supports favorites, playback speed buttons, and individual clip downloads.
   - If segmentation is too strict or too loose, rerun with `--sensitivity` or `--threshold`.
   - Treat automatic rally splits as candidates. Ask the user to confirm or name favorite IDs before compiling.

5. Compile favorite rallies when the user chooses clips.
   - Run:
     ```bash
     python3 <skill-root>/scripts/compile_rallies.py <run-folder>/rally_review/rally_index.json --ids 1,3,5 --out selected-rallies.mp4
     ```
   - Preserve the user's chosen order when provided.
   - If stream-copy concat fails, the script falls back to re-encoding.

6. Add skeleton overlays when useful.
   - Use skeletons for visible full-body or half-body frames. Prefer a frame where the player is not heavily occluded.
   - If multiple people are visible, crop around the player:
     ```bash
     python3 <skill-root>/scripts/pose_overlay.py <key-frame.jpg> --outdir <run-folder>/generated_assets --crop x1,y1,x2,y2 --timestamp "38.50s" --title "Pose skeleton demo"
     ```
   - The script writes full-frame overlay, crop overlay, comparison image, and JSON metadata.
   - Put the resulting paths in `analysis.json` under `pose_analysis`.

7. Create slow-motion phase clips when requested or useful.
   - Use early/middle/late representative swings, preferably selected from contact sheets rather than raw thirds.
   - Run:
     ```bash
     python3 <skill-root>/scripts/make_swing_clips.py <video> --outdir <run-folder>/swing_clips \
       --event "early|31.75|Early|issue note|next cue" \
       --event "middle|147.25|Middle|issue note|next cue" \
       --event "late|280.75|Late|issue note|next cue"
     ```
   - Merge `swing_clips/swing_clips.json` phase paths into `analysis.json`.

8. Write `analysis.json`.
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

9. Render the report.
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

## Rally Segmentation Guidance

The rally splitter uses motion changes to find candidate active-play intervals. It is useful for quickly reviewing long videos, but it is not a perfect tennis rules engine.

Good uses:

- isolate likely rally clips from long continuous footage
- review each clip at 0.5x, 0.75x, 1x, 1.25x, 1.5x, or 2x speed
- download individual rallies
- favorite clips and compile a highlight reel
- hand off chosen rally IDs into deeper technical analysis

Mode guidance:

- `shot` mode is best when the user wants one swing or one ball at a time.
- `practice` mode is best for lessons, coach feeding, and ball-machine sessions where several shots belong together.
- `rally` mode is best for match play or true point construction.
- `auto` mode should be the default, but keep a manual override available because camera movement, ball pickup, or coach movement can confuse motion-only detection.

Limitations:

- false positives can happen during camera movement, ball pickup, or coach movement
- false negatives can happen when the player is small or motion is subtle
- one real rally can be split into two if there is a long pause in the middle
- two nearby rallies can merge if the between-rally pause is short

Prefer a manual review step before final compilation. For important videos, do not delete the original long video or the unselected candidate clips.

## Output Standard

Deliver these files when feasible:

- `rally_review/rally_index.json` when rally splitting is requested
- `rally_review/rally_viewer.html`
- `rally_review/rallies/*.mp4`
- `selected-rallies.mp4` when favorite rallies are compiled
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
