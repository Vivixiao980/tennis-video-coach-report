# Tennis Report JSON Schema

Create `analysis.json` in the run folder, then render it with `scripts/render_tennis_report.py`.

## Minimal Schema

```json
{
  "title": "网球训练报告：正手慢半拍",
  "date": "2026-05-22",
  "player": "Player",
  "video": {
    "path": "/absolute/path/to/video.mov",
    "duration": "46.4s",
    "scene": "小场正手 / 发球机练习"
  },
  "one_liner": "问题不在不会发力，而是准备动作晚了半拍。",
  "main_focus": "提前转肩",
  "confidence": "medium",
  "cover_frame": "candidate_frames/candidate_03_t038.50.jpg",
  "coach_summary": [
    "球已经出来了，但拍子还没到右后方，所以你会感觉自己被球追着打。",
    "随挥比准备动作更好，说明身体已经愿意跟着球拍过去。"
  ],
  "capture_quality": [
    {
      "title": "近机位：适合看上半身和随挥",
      "timestamp": "IMG_0525 · 34.25s",
      "frame": "IMG_0525/candidate_frames/candidate_05_t034.25.jpg",
      "zoom_frame": "generated_assets/zoom_issue_recovery.jpg",
      "note": "人物占画面比例够大，能看清拍子、身体朝向和结束姿态。",
      "metrics": [
        {"label": "人物大小", "value": "好", "level": "good"},
        {"label": "拍面可见", "value": "中", "level": "warn"},
        {"label": "回位判断", "value": "好", "level": "good"}
      ]
    }
  ],
  "pose_analysis": [
    {
      "timestamp": "38.50s",
      "title": "骨架识别：反手侧身与下肢支撑",
      "overlay_frame": "generated_assets/pose_demo_full.jpg",
      "comparison_frame": "generated_assets/pose_demo_side_by_side.jpg",
      "note": "用姿态估计识别肩、肘、手腕、髋、膝、脚踝等关键点，作为动作观察的辅助证据。",
      "metrics": [
        {"label": "识别点位", "value": "32 个可见点", "level": "good"},
        {"label": "适合分析", "value": "姿态 / 距离 / 重心", "level": "good"},
        {"label": "不适合单独判断", "value": "拍面角度", "level": "warn"}
      ],
      "uses": [
        "看准备时肩膀和髋部有没有侧过去。",
        "看手肘、手腕和身体之间的距离，判断是不是容易被球挤到。",
        "看膝盖弯曲和前后脚支撑，判断是否蹲住到击球后。"
      ],
      "limits": [
        "不能直接看清拍面角度。",
        "单摄像头只能近似判断身体旋转，不能当成精确 3D 角度测量。"
      ]
    }
  ],
  "problem_tracker": [
    {
      "title": "打完回中慢半拍",
      "status": "连续出现",
      "status_level": "fix",
      "meaning": "不是单拍不会打，而是每拍之间的连接慢。",
      "evidence": [
        "IMG_0523：随挥完整，但打完后有小停顿。",
        "IMG_0525：近机位能看到结束姿态停留。"
      ],
      "cue": "打完，回中，拍面回身前。"
    }
  ],
  "phase_review": [
    {
      "phase": "early",
      "label": "前段",
      "timestamp": "6.00s",
      "clip_start": "4.75s",
      "clip_end": "7.75s",
      "normal_clip": "swing_clips/early-前段/swing_normal.mp4",
      "annotated_slow_clip": "swing_clips/early-前段/swing_slow_annotated.mp4",
      "freeze_frame": "swing_clips/early-前段/freeze_annotated.jpg",
      "focus": [0.36, 0.52, 0.18, 0.22],
      "arrow": [0.66, 0.38, 0.42, 0.50],
      "change": "刚开始这一拍比较用手找球，准备动作还没有提前完成。",
      "issue": "球来之后才开始把拍子带到右后方，时间会被压缩。",
      "cue": "球一出来，先转肩。"
    },
    {
      "phase": "middle",
      "label": "中段",
      "timestamp": "18.50s",
      "annotated_slow_clip": "swing_clips/middle-中段/swing_slow_annotated.mp4",
      "freeze_frame": "swing_clips/middle-中段/freeze_annotated.jpg",
      "change": "中段开始能提前一点点，但还不是每一拍都有。",
      "cue": "拍子先回家，再等球。"
    },
    {
      "phase": "late",
      "label": "后段",
      "timestamp": "38.50s",
      "annotated_slow_clip": "swing_clips/late-后段/swing_slow_annotated.mp4",
      "freeze_frame": "swing_clips/late-后段/freeze_annotated.jpg",
      "change": "后段随挥更放松，但脚下有一点站住。",
      "cue": "打完让拍子自然过去。"
    }
  ],
  "highlights": [
    {
      "title": "随挥完整",
      "frame": "frames_4fps/frame_0155.jpg",
      "timestamp": "38.50s",
      "note": "这拍身体跟过去了，不是只用手挡球。"
    }
  ],
  "issues": [
    {
      "title": "准备动作晚了半拍",
      "frame": "frames_4fps/frame_0106.jpg",
      "timestamp": "26.25s",
      "evidence": "球已经接近身体，拍子还在找位置。",
      "impact": "击球时间被压缩，容易变成临时拉拍、手臂硬推。",
      "cue": "球一出来，先转肩。",
      "drill": "发球机慢速 30 球，只检查拍子是否提前到右后方，不追求大力。"
    }
  ],
  "next_practice": [
    "慢速 30 球：只练出球就转肩。",
    "每 10 球停一次，看拍子有没有先到右后方。",
    "先稳定节奏，再加力量。"
  ],
  "training_prescription": [
    {
      "title": "回中反射",
      "duration": "3 分钟 / 20 球",
      "why": "修正打完停住看球的习惯。",
      "steps": [
        "每打一拍，嘴里默念“回中”。",
        "拍子回到肚脐前方，脚做一个很小的调整步。",
        "不追求打深，只看下一拍前有没有准备好。"
      ],
      "success_check": "成功标准：打完 1 秒内，拍面已经回到身前。"
    }
  ],
  "social_poster": "generated_assets/tennis_diary_poster_3x4.png",
  "social_caption": "今天抓到一个小问题：正手慢半拍。不是不会打，是准备晚了。"
}
```

## Field Notes

- `confidence`: use `high`, `medium`, or `low`.
- `cover_frame`: choose a good-looking frame, not necessarily the problem frame.
- `highlights`: 1-3 items.
- `issues`: 1-3 items, but prefer one main issue for beginners.
- `phase_review`: optional but required when the user asks for early/middle/late comparison or slow-motion clips.
- `phase_review[].annotated_slow_clip`: use the output from `scripts/make_swing_clips.py`.
- `phase_review[].change`: describe the phase-to-phase difference, not just a static flaw.
- `phase_review[].focus`: optional normalized `[cx, cy, rx, ry]` for a circle. Only include after inspecting the freeze frame.
- `phase_review[].arrow`: optional normalized `[x1, y1, x2, y2]` for an arrow. Only include after inspecting the freeze frame.
- Paths may be absolute or relative to `analysis.json`.
- Keep `cue` short enough to remember while playing.
- `capture_quality`: optional shooting-quality review. Use this to tell the user which videos are fit for detailed technique and which are only fit for rhythm/positioning.
- `capture_quality[].zoom_frame`: optional crop-assisted close-up. A zoom crop helps the user see the player, but do not pretend it creates evidence that was absent from the original frame.
- `capture_quality[].metrics[].level`: use `good`, `warn`, or `bad`.
- `pose_analysis`: optional pose/skeleton review. Use this when key frames have real pose-estimation overlays.
- `pose_analysis[].overlay_frame`: full-frame skeleton overlay.
- `pose_analysis[].comparison_frame`: optional original-vs-overlay or crop-vs-overlay comparison image.
- `pose_analysis[].uses`: concrete movement questions the skeleton can help answer.
- `pose_analysis[].limits`: uncertainty boundaries; never use skeleton overlays as proof for racket face angle, ball contact, or precise 3D rotation unless those are separately measured.
- `problem_tracker`: optional long-term issue cards. Use `fix` for the main issue, `watch` for occasional/secondary flaws, and `good` for improving strengths.
- `training_prescription`: optional short practice plan for visible flaws. Keep drills tiny and measurable.
- `social_poster`: optional 3:4 image for sharing.
