#!/usr/bin/env python3
"""Render a beginner-friendly tennis analysis report from analysis.json."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from datetime import date
from pathlib import Path


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def rel_asset(frame: str | None, analysis_dir: Path, asset_dir: Path) -> str:
    if not frame:
        return ""
    src = Path(frame)
    if not src.is_absolute():
        src = analysis_dir / src
    src = src.resolve()
    if not src.exists():
        return ""
    asset_dir.mkdir(parents=True, exist_ok=True)
    name = src.name
    dst = asset_dir / name
    counter = 2
    while dst.exists() and dst.resolve() != src:
        dst = asset_dir / f"{src.stem}-{counter}{src.suffix}"
        counter += 1
    if dst.resolve() != src:
        shutil.copy2(src, dst)
    return f"assets/{dst.name}"


def rel_media(path_value: str | None, analysis_dir: Path, asset_dir: Path) -> str:
    return rel_asset(path_value, analysis_dir, asset_dir)


def image_tag(src: str, alt: str = "") -> str:
    if not src:
        return '<div class="placeholder">frame missing</div>'
    return f'<img src="{esc(src)}" alt="{esc(alt)}">'


def confidence_label(value: object) -> str:
    mapping = {
        "high": "高",
        "medium": "中",
        "low": "低",
    }
    return mapping.get(str(value or "").lower(), str(value or ""))


def render_cards(items: list[dict], kind: str, analysis_dir: Path, asset_dir: Path) -> str:
    cards = []
    for item in items:
        img = rel_asset(item.get("frame"), analysis_dir, asset_dir)
        if kind == "issue":
            body = f"""
              <p><b>看到什么</b>{esc(item.get("evidence"))}</p>
              <p><b>影响</b>{esc(item.get("impact"))}</p>
              <p><b>口令</b>{esc(item.get("cue"))}</p>
              <p><b>练习</b>{esc(item.get("drill"))}</p>
            """
        else:
            body = f"<p>{esc(item.get('note'))}</p>"
        cards.append(f"""
          <article class="moment {kind}">
            <div class="moment-img">{image_tag(img, item.get("title", ""))}</div>
            <div class="moment-body">
              <div class="time">{esc(item.get("timestamp", ""))}</div>
              <h3>{esc(item.get("title", ""))}</h3>
              {body}
            </div>
          </article>
        """)
    return "\n".join(cards)


def render_phase_review(items: list[dict], analysis_dir: Path, asset_dir: Path) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        video = rel_media(
            item.get("annotated_slow_clip") or item.get("slow_clip") or item.get("clip") or item.get("normal_clip"),
            analysis_dir,
            asset_dir,
        )
        poster = rel_asset(item.get("freeze_frame") or item.get("frame"), analysis_dir, asset_dir)
        media = ""
        if video:
            poster_attr = f' poster="{esc(poster)}"' if poster else ""
            media = f'<video controls playsinline preload="metadata"{poster_attr}><source src="{esc(video)}" type="video/mp4"></video>'
        elif poster:
            media = image_tag(poster, item.get("label", ""))
        else:
            media = '<div class="placeholder">clip missing</div>'
        detail_rows = []
        for key, label in [("change", "变化"), ("issue", "问题"), ("note", "观察"), ("cue", "口令")]:
            if item.get(key):
                detail_rows.append(f"<p><b>{label}</b>{esc(item.get(key))}</p>")
        cards.append(f"""
          <article class="phase-card">
            <div class="phase-media">{media}</div>
            <div class="phase-body">
              <div class="time">{esc(item.get("timestamp", ""))}</div>
              <h3>{esc(item.get("label") or item.get("phase") or "")}</h3>
              {''.join(detail_rows)}
            </div>
          </article>
        """)
    return f"""
    <section class="section">
      <h2>前中后变化</h2>
      <div class="phase-grid">{''.join(cards)}</div>
    </section>
    """


def render_capture_quality(items: list[dict], analysis_dir: Path, asset_dir: Path) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        raw = rel_asset(item.get("frame"), analysis_dir, asset_dir)
        zoom = rel_asset(item.get("zoom_frame"), analysis_dir, asset_dir)
        media = ""
        if raw or zoom:
            media = f"""
              <div class="quality-media">
                <div>{image_tag(raw, "原画面")}<span>原画面</span></div>
                <div>{image_tag(zoom, "人物放大")}<span>人物放大</span></div>
              </div>
            """
        metrics = "".join(
            f'<li><b>{esc(m.get("label"))}</b><span class="score {esc(m.get("level", ""))}">{esc(m.get("value"))}</span></li>'
            for m in item.get("metrics", [])
        )
        cards.append(f"""
          <article class="quality-card">
            {media}
            <div class="quality-body">
              <div class="time">{esc(item.get("timestamp", ""))}</div>
              <h3>{esc(item.get("title", ""))}</h3>
              <p>{esc(item.get("note", ""))}</p>
              <ul class="metrics">{metrics}</ul>
            </div>
          </article>
        """)
    return f"""
    <section class="section">
      <h2>拍摄质量 & 人像放大</h2>
      <div class="quality-grid">{''.join(cards)}</div>
    </section>
    """


def render_pose_analysis(items: list[dict], analysis_dir: Path, asset_dir: Path) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        overlay = rel_asset(item.get("overlay_frame"), analysis_dir, asset_dir)
        comparison = rel_asset(item.get("comparison_frame"), analysis_dir, asset_dir)
        media = ""
        if comparison:
            media = f'<div class="pose-media wide">{image_tag(comparison, item.get("title", ""))}</div>'
        elif overlay:
            media = f'<div class="pose-media">{image_tag(overlay, item.get("title", ""))}</div>'
        metrics = "".join(
            f'<li><b>{esc(m.get("label"))}</b><span class="score {esc(m.get("level", ""))}">{esc(m.get("value"))}</span></li>'
            for m in item.get("metrics", [])
        )
        uses = "".join(f"<li>{esc(use)}</li>" for use in item.get("uses", []))
        limits = "".join(f"<li>{esc(limit)}</li>" for limit in item.get("limits", []))
        blocks = ""
        if uses:
            blocks += f"<h4>能用来分析</h4><ul>{uses}</ul>"
        if limits:
            blocks += f"<h4>暂时不能替代</h4><ul>{limits}</ul>"
        cards.append(f"""
          <article class="pose-card">
            {media}
            <div class="pose-body">
              <div class="time">{esc(item.get("timestamp", ""))}</div>
              <h3>{esc(item.get("title", ""))}</h3>
              <p>{esc(item.get("note", ""))}</p>
              <ul class="metrics">{metrics}</ul>
              <div class="pose-lists">{blocks}</div>
            </div>
          </article>
        """)
    return f"""
    <section class="section">
      <h2>骨架识别分析</h2>
      <div class="pose-grid">{''.join(cards)}</div>
    </section>
    """


def render_problem_tracker(items: list[dict]) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        evidence = "".join(f"<li>{esc(e)}</li>" for e in item.get("evidence", []))
        cards.append(f"""
          <article class="tracker-card {esc(item.get("status_level", ""))}">
            <div class="tracker-top">
              <span>{esc(item.get("status", ""))}</span>
              <strong>{esc(item.get("title", ""))}</strong>
            </div>
            <p>{esc(item.get("meaning", ""))}</p>
            <ul>{evidence}</ul>
            <div class="tracker-cue">{esc(item.get("cue", ""))}</div>
          </article>
        """)
    return f"""
    <section class="section">
      <h2>问题追踪卡</h2>
      <div class="tracker-grid">{''.join(cards)}</div>
    </section>
    """


def render_training_prescription(items: list[dict]) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        steps = "".join(f"<li>{esc(step)}</li>" for step in item.get("steps", []))
        cards.append(f"""
          <article class="drill-card">
            <div class="time">{esc(item.get("duration", ""))}</div>
            <h3>{esc(item.get("title", ""))}</h3>
            <p>{esc(item.get("why", ""))}</p>
            <ol>{steps}</ol>
            <div class="tracker-cue">{esc(item.get("success_check", ""))}</div>
          </article>
        """)
    return f"""
    <section class="section">
      <h2>瑕疵修正训练</h2>
      <div class="drill-grid">{''.join(cards)}</div>
    </section>
    """


def render_html(data: dict, analysis_path: Path, outdir: Path) -> str:
    analysis_dir = analysis_path.parent
    asset_dir = outdir / "assets"
    cover = rel_asset(data.get("cover_frame"), analysis_dir, asset_dir)
    video = data.get("video") or {}
    summaries = data.get("coach_summary") or []
    next_practice = data.get("next_practice") or []
    highlights = data.get("highlights") or []
    issues = data.get("issues") or []
    phase_review = data.get("phase_review") or data.get("phase_reviews") or []
    capture_quality = data.get("capture_quality") or []
    pose_analysis = data.get("pose_analysis") or []
    problem_tracker = data.get("problem_tracker") or []
    training_prescription = data.get("training_prescription") or []
    today = data.get("date") or date.today().isoformat()

    summary_html = "".join(f"<li>{esc(s)}</li>" for s in summaries)
    practice_html = "".join(f"<li>{esc(s)}</li>" for s in next_practice)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(data.get("title", "网球训练报告"))}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f4f1e8;
      color: #14211b;
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", Arial, sans-serif;
    }}
    .page {{
      width: min(100%, 860px);
      margin: 0 auto;
      padding: 28px 18px 42px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      border-radius: 28px;
      min-height: 540px;
      background: #dfe6dc;
      box-shadow: 0 24px 70px rgba(20, 33, 27, .13);
    }}
    .hero img {{
      width: 100%;
      height: 620px;
      object-fit: cover;
      display: block;
      filter: brightness(1.05) contrast(.96) saturate(1.04);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(10,20,15,0) 42%, rgba(10,20,15,.72) 100%);
    }}
    .hero-text {{
      position: absolute;
      left: 28px;
      right: 28px;
      bottom: 28px;
      z-index: 2;
      color: white;
    }}
    .kicker {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 13px;
      border-radius: 999px;
      background: rgba(255,255,255,.9);
      color: #08784f;
      font-size: 14px;
      font-weight: 800;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(38px, 9vw, 72px);
      line-height: .98;
      letter-spacing: 0;
    }}
    .one {{
      margin: 14px 0 0;
      font-size: clamp(20px, 4vw, 30px);
      line-height: 1.25;
      font-weight: 700;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin: 16px 0 24px;
    }}
    .meta div, .card, .moment, .practice {{
      background: rgba(255,255,255,.88);
      border: 1px solid rgba(20,33,27,.08);
      box-shadow: 0 16px 42px rgba(20,33,27,.08);
    }}
    .meta div {{
      border-radius: 18px;
      padding: 15px 16px;
      font-size: 15px;
      line-height: 1.25;
    }}
    .meta b {{
      display: block;
      color: #08784f;
      margin-bottom: 5px;
      font-size: 13px;
    }}
    .section {{
      margin-top: 22px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 28px;
      line-height: 1.1;
    }}
    .card {{
      border-radius: 24px;
      padding: 22px;
    }}
    .card li, .practice li {{
      margin: 0 0 10px;
      font-size: 19px;
      line-height: 1.45;
    }}
    .moment {{
      overflow: hidden;
      border-radius: 24px;
      margin-bottom: 14px;
      display: grid;
      grid-template-columns: 44% 1fr;
    }}
    .phase-grid {{
      display: grid;
      gap: 14px;
    }}
    .phase-card {{
      overflow: hidden;
      border-radius: 24px;
      background: rgba(255,255,255,.88);
      border: 1px solid rgba(20,33,27,.08);
      box-shadow: 0 16px 42px rgba(20,33,27,.08);
    }}
    .phase-media {{
      background: #dfe6dc;
    }}
    .phase-media video,
    .phase-media img {{
      display: block;
      width: 100%;
      max-height: 520px;
      object-fit: cover;
    }}
    .phase-body {{
      padding: 18px 20px 20px;
    }}
    .phase-body p {{
      margin: 0 0 9px;
      font-size: 17px;
      line-height: 1.36;
    }}
    .phase-body p b {{
      display: inline-block;
      min-width: 46px;
      color: #08784f;
      margin-right: 6px;
    }}
    .moment-img {{
      min-height: 250px;
      background: #dfe6dc;
    }}
    .moment-img img {{
      width: 100%;
      height: 100%;
      min-height: 250px;
      object-fit: cover;
      display: block;
    }}
    .placeholder {{
      height: 100%;
      min-height: 250px;
      display: grid;
      place-items: center;
      color: #7a867d;
      font-size: 14px;
    }}
    .moment-body {{
      padding: 20px;
    }}
    .time {{
      color: #08784f;
      font-size: 13px;
      font-weight: 800;
      margin-bottom: 6px;
    }}
    h3 {{
      margin: 0 0 10px;
      font-size: 24px;
      line-height: 1.1;
    }}
    .moment p {{
      margin: 0 0 10px;
      font-size: 17px;
      line-height: 1.36;
    }}
    .moment p b {{
      display: inline-block;
      min-width: 72px;
      color: #08784f;
      margin-right: 6px;
    }}
    .practice {{
      border-radius: 24px;
      padding: 20px 22px;
    }}
    .caption {{
      margin: 18px 0 0;
      color: #66736b;
      font-size: 16px;
      line-height: 1.4;
    }}
    .quality-grid, .tracker-grid, .drill-grid {{
      display: grid;
      gap: 14px;
    }}
    .quality-card, .pose-card, .tracker-card, .drill-card {{
      background: rgba(255,255,255,.88);
      border: 1px solid rgba(20,33,27,.08);
      box-shadow: 0 16px 42px rgba(20,33,27,.08);
      border-radius: 24px;
      overflow: hidden;
    }}
    .quality-media {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1px;
      background: rgba(20,33,27,.1);
    }}
    .quality-media div {{
      position: relative;
      background: #dfe6dc;
      min-height: 260px;
    }}
    .quality-media img {{
      width: 100%;
      height: 100%;
      min-height: 260px;
      object-fit: cover;
      display: block;
    }}
    .quality-media span {{
      position: absolute;
      left: 10px;
      bottom: 10px;
      padding: 5px 9px;
      border-radius: 999px;
      background: rgba(255,255,255,.9);
      color: #08784f;
      font-size: 12px;
      font-weight: 800;
    }}
    .quality-body, .tracker-card, .drill-card {{
      padding: 18px 20px 20px;
    }}
    .pose-grid {{
      display: grid;
      gap: 14px;
    }}
    .pose-media {{
      background: #dfe6dc;
    }}
    .pose-media img {{
      width: 100%;
      display: block;
      object-fit: cover;
      max-height: 680px;
    }}
    .pose-media.wide img {{
      max-height: none;
    }}
    .pose-body {{
      padding: 18px 20px 20px;
    }}
    .pose-body p {{
      margin: 0 0 12px;
      font-size: 17px;
      line-height: 1.42;
    }}
    .pose-lists {{
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }}
    .pose-lists h4 {{
      margin: 0 0 7px;
      font-size: 17px;
      color: #08784f;
    }}
    .pose-lists ul {{
      margin: 0;
      padding-left: 20px;
      color: #415046;
      font-size: 16px;
      line-height: 1.4;
    }}
    .pose-lists li {{
      margin-bottom: 6px;
    }}
    .quality-body p, .tracker-card p, .drill-card p {{
      margin: 0 0 12px;
      font-size: 17px;
      line-height: 1.42;
    }}
    .metrics {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 8px;
    }}
    .metrics li {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
      border-radius: 14px;
      background: #f4f1e8;
      font-size: 15px;
    }}
    .score {{
      flex: 0 0 auto;
      border-radius: 999px;
      padding: 4px 9px;
      background: #e4eee5;
      color: #08784f;
      font-weight: 800;
      font-size: 13px;
    }}
    .score.warn {{ background: #fff0c7; color: #8b5a00; }}
    .score.bad {{ background: #ffe1df; color: #a33125; }}
    .tracker-top {{
      display: grid;
      gap: 6px;
      margin-bottom: 10px;
    }}
    .tracker-top span {{
      width: fit-content;
      border-radius: 999px;
      padding: 5px 10px;
      background: #e4eee5;
      color: #08784f;
      font-size: 13px;
      font-weight: 800;
    }}
    .tracker-top strong {{
      font-size: 23px;
      line-height: 1.1;
    }}
    .tracker-card ul {{
      margin: 0 0 12px;
      padding-left: 20px;
      color: #415046;
      font-size: 16px;
      line-height: 1.38;
    }}
    .tracker-card li {{
      margin-bottom: 6px;
    }}
    .tracker-cue {{
      border-left: 4px solid #08784f;
      background: #edf5ee;
      color: #14211b;
      padding: 11px 12px;
      border-radius: 12px;
      font-weight: 800;
      line-height: 1.35;
    }}
    .tracker-card.watch .tracker-top span {{ background: #fff0c7; color: #8b5a00; }}
    .tracker-card.fix .tracker-top span {{ background: #ffe1df; color: #a33125; }}
    .tracker-card.good .tracker-top span {{ background: #e4eee5; color: #08784f; }}
    .drill-card ol {{
      margin: 0 0 12px;
      padding-left: 22px;
      font-size: 17px;
      line-height: 1.42;
    }}
    .drill-card li {{
      margin-bottom: 8px;
    }}
    @media (max-width: 620px) {{
      .page {{ padding: 14px 12px 32px; }}
      .hero {{ border-radius: 22px; min-height: 430px; }}
      .hero img {{ height: 500px; }}
      .meta {{ grid-template-columns: 1fr; }}
      .moment {{ grid-template-columns: 1fr; }}
      .moment-img, .moment-img img {{ min-height: 280px; }}
      .quality-media {{ grid-template-columns: 1fr 1fr; }}
      .quality-media div, .quality-media img {{ min-height: 220px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      {image_tag(cover, data.get("title", ""))}
      <div class="hero-text">
        <div class="kicker">AI TENNIS COACH · {esc(today)}</div>
        <h1>{esc(data.get("title", "网球训练报告"))}</h1>
        <p class="one">{esc(data.get("one_liner", ""))}</p>
      </div>
    </section>

    <section class="meta">
      <div><b>本次重点</b>{esc(data.get("main_focus", ""))}</div>
      <div><b>场景</b>{esc(video.get("scene", ""))}</div>
      <div><b>置信度</b>{esc(confidence_label(data.get("confidence", "")))}</div>
    </section>

    <section class="section">
      <h2>教练小结</h2>
      <div class="card"><ul>{summary_html}</ul></div>
    </section>

    {render_capture_quality(capture_quality, analysis_dir, asset_dir)}

    {render_pose_analysis(pose_analysis, analysis_dir, asset_dir)}

    {render_problem_tracker(problem_tracker)}

    {render_phase_review(phase_review, analysis_dir, asset_dir)}

    <section class="section">
      <h2>值得夸的地方</h2>
      {render_cards(highlights, "highlight", analysis_dir, asset_dir)}
    </section>

    <section class="section">
      <h2>今天先改这里</h2>
      {render_cards(issues, "issue", analysis_dir, asset_dir)}
    </section>

    {render_training_prescription(training_prescription)}

    <section class="section">
      <h2>下一次怎么练</h2>
      <div class="practice"><ol>{practice_html}</ol></div>
      <p class="caption">{esc(data.get("social_caption", ""))}</p>
    </section>
  </main>
</body>
</html>"""


def export_with_playwright(html_path: Path, outdir: Path, do_pdf: bool, do_png: bool) -> list[str]:
    exported: list[str] = []
    if not (do_pdf or do_png):
        return exported
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed; skipped PDF/PNG export.", file=sys.stderr)
        return exported

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        if do_pdf:
            page = browser.new_page(viewport={"width": 860, "height": 1200}, device_scale_factor=1)
            page.goto(html_path.as_uri(), wait_until="networkidle")
            pdf_path = outdir / "tennis-report.pdf"
            page.pdf(path=str(pdf_path), format="A4", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            exported.append(str(pdf_path))
        if do_png:
            page = browser.new_page(viewport={"width": 430, "height": 932}, device_scale_factor=2)
            page.goto(html_path.as_uri(), wait_until="networkidle")
            png_path = outdir / "tennis-report-mobile.png"
            page.screenshot(path=str(png_path), full_page=True)
            exported.append(str(png_path))
        browser.close()
    return exported


def main() -> int:
    parser = argparse.ArgumentParser(description="Render tennis coaching report from analysis.json.")
    parser.add_argument("analysis_json", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--png", action="store_true")
    args = parser.parse_args()

    analysis_path = args.analysis_json.expanduser().resolve()
    if not analysis_path.exists():
        raise SystemExit(f"analysis.json not found: {analysis_path}")
    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    html_text = render_html(data, analysis_path, outdir)
    html_path = outdir / "index.html"
    html_path.write_text(html_text, encoding="utf-8")
    exported = export_with_playwright(html_path, outdir, args.pdf, args.png)
    print(json.dumps({"html": str(html_path), "exported": exported}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
