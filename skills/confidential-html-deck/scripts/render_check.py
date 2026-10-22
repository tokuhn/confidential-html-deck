#!/usr/bin/env python3
"""Render a deck in headless Chromium and check it the way a user would see it.

Usage:  python3 render_check.py path/to/deck.html [--out DIR] [--pdf PREVIEW.pdf] [--no-stress] [--data stress.json]

Does, with the deck's sample values and again with generated "stress" values
(longer texts, ~10x larger numbers, negative changes, more table rows):
  - collects console errors, page errors and any network request (there must be none)
  - reads the runtime's own check (undefined variables, failed calculations)
  - finds content that overflows its slide or its box
  - writes one PNG per slide (DIR/sample/slide-01.png, DIR/stress/…)
  - prints the deck WITH SAMPLE DATA to a PDF (--pdf path, default DIR/deck.pdf): the
    preview to show the user while iterating on the design
Exit code 1 if anything is wrong. Needs: pip install playwright && playwright install chromium
"""
import json
import re
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright is not installed (pip install playwright && python -m playwright install chromium)")

OVERFLOW_JS = r"""
() => {
  const out = [];
  document.querySelectorAll('.slide').forEach((slide, si) => {
    const sr = slide.getBoundingClientRect();
    const scale = sr.width / 1280;
    const tol = 1.5 * scale;
    slide.querySelectorAll('*').forEach(el => {
      if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg' && el.tagName.toLowerCase() !== 'text') return;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.position === 'fixed') return;
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) return;
      const label = (el.dataset && (el.dataset.var || el.dataset.field || el.dataset.chart)) || (el.textContent || '').trim().slice(0, 40);
      if (r.right > sr.right + tol || r.bottom > sr.bottom + tol || r.left < sr.left - tol || r.top < sr.top - tol) {
        // only report the outermost offender
        const p = el.parentElement;
        const pr = p && p !== slide ? p.getBoundingClientRect() : null;
        if (!pr || !(pr.right > sr.right + tol || pr.bottom > sr.bottom + tol || pr.left < sr.left - tol || pr.top < sr.top - tol))
          out.push({ slide: si + 1, kind: 'outside slide', what: el.tagName.toLowerCase() + ' ' + label });
      }
      if (el.tagName.toLowerCase() !== 'svg' && !el.closest('svg') && el.children.length === 0 && el.textContent.trim()) {
        if (el.scrollWidth > el.clientWidth + 2 && cs.overflowX !== 'visible' && el.clientWidth > 0)
          out.push({ slide: si + 1, kind: 'text clipped horizontally', what: label });
      }
      if (!el.closest('svg') && el !== slide && ['hidden', 'clip', 'auto', 'scroll'].includes(cs.overflowY) && el.scrollHeight > el.clientHeight + 2 && el.clientHeight > 0)
        out.push({ slide: si + 1, kind: 'content clipped vertically', what: el.tagName.toLowerCase() + ' ' + label });
    });
    // text nodes wider than their block parent (wrapping disabled, long words)
    slide.querySelectorAll('[data-var], [data-field]').forEach(el => {
      const p = el.parentElement; if (!p) return;
      const r = el.getBoundingClientRect(), pr = p.getBoundingClientRect();
      if (r.right > pr.right + tol && getComputedStyle(p).overflowX === 'visible')
        out.push({ slide: si + 1, kind: 'value wider than its box', what: el.dataset.var || el.dataset.field });
    });
    // charts: svg text outside the chart box
    slide.querySelectorAll('[data-chart]').forEach(ch => {
      const cr = ch.getBoundingClientRect();
      ch.querySelectorAll('svg text').forEach(t => {
        const r = t.getBoundingClientRect();
        if (r.left < cr.left - 6 * scale || r.right > cr.right + 6 * scale || r.top < cr.top - 6 * scale || r.bottom > cr.bottom + 6 * scale)
          out.push({ slide: si + 1, kind: 'chart label outside chart box', what: ch.dataset.chart + ': ' + t.textContent.slice(0, 30) });
      });
    });
  });
  const seen = new Set();
  return out.filter(o => { const k = JSON.stringify(o); if (seen.has(k)) return false; seen.add(k); return true; });
}
"""


def stress_values(spec):
    """Deterministic worst-case-ish values: longer text, bigger numbers, flipped signs on percentages."""
    def text(v):
        v = str(v)
        target = max(len(v) + 6, int(len(v) * 1.7))
        out = v
        filler = ["International", "Holding", "Services", "Group", "Solutions", "Partners"]
        i = 0
        while len(out) < target:
            out += " " + filler[i % len(filler)]
            i += 1
        return out

    def one(v, t):
        k = str(t).split(":")[0]
        if k == "text":
            return text(v)
        if k in ("number", "integer", "currency", "compact"):
            return round(v * 9.7, 2) if isinstance(v, float) else int(v * 9.7) if isinstance(v, int) else v
        if k == "percent":
            return -abs(v) * 1.8 if v else -0.123
        return v

    values = {}
    for key, d in (spec.get("vars") or {}).items():
        t, v = d.get("type", "text"), d.get("value")
        if str(t).startswith("rows") and isinstance(v, list):
            fields = d.get("fields") or {}
            rows = [{f: one(r.get(f), ft) for f, ft in fields.items()} | {k2: r[k2] for k2 in r if k2 not in fields} for r in v]
            values[key] = rows + [dict(r) for r in rows]  # twice as many rows
        else:
            values[key] = one(v, t)
    return values


def run(page, label, out_dir, data=None):
    problems = []
    if data is not None:
        page.evaluate("t => DeckRuntime.importText(t, 'stress.json')", json.dumps({"values": data}))
        page.wait_for_timeout(150)
    issues = page.evaluate("() => DeckRuntime.issues()")
    for lvl, msg in issues["render"] + issues["import"]:
        if lvl == "error":
            problems.append(f"[{label}] check: " + re.sub(r"<[^>]+>", "", msg))
    for o in page.evaluate(OVERFLOW_JS):
        problems.append(f"[{label}] slide {o['slide']}: {o['kind']} — {o['what']}")
    d = out_dir / label
    d.mkdir(parents=True, exist_ok=True)
    frames = page.query_selector_all("#deck > .slide-frame")
    for i, f in enumerate(frames, 1):
        f.screenshot(path=str(d / f"slide-{i:02d}.png"))
    return problems, len(frames)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    deck = Path(args[0]).resolve()
    out_dir = Path(args[args.index("--out") + 1]) if "--out" in args else deck.parent / (deck.stem + "-check")
    pdf_path = Path(args[args.index("--pdf") + 1]) if "--pdf" in args else out_dir / "deck.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = deck.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="deck-vars">(.*?)</script>', src, re.S)
    spec = json.loads(m.group(1)) if m else {}
    if "--data" in args:
        stress = json.loads(Path(args[args.index("--data") + 1]).read_text(encoding="utf-8"))
        stress = stress.get("values", stress)
    else:
        stress = stress_values(spec)

    problems, requests, console = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1)
        page.on("request", lambda r: requests.append(r.url) if not r.url.startswith(("file:", "data:", "blob:", "about:")) else None)
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in ("error",) else None)
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.goto(deck.as_uri())
        page.wait_for_timeout(300)
        pr, n = run(page, "sample", out_dir)
        problems += pr
        page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        if "--no-stress" not in args:
            pr, _ = run(page, "stress", out_dir, stress)
            problems += pr
        browser.close()

    try:
        from pypdf import PdfReader
        pages = len(PdfReader(str(pdf_path)).pages)
        if pages != n:
            problems.append(f"PDF has {pages} pages for {n} slides (a slide spills onto a second page)")
    except Exception:
        pages = "?"

    problems += [f"console {c}" for c in console]
    problems += [f"NETWORK REQUEST (must not happen): {u}" for u in requests]
    print(f"Deck: {deck.name} · {n} slides · PDF pages: {pages}")
    print(f"Screenshots: {out_dir}")
    print(f"Sample-data PDF preview: {pdf_path}")
    for pr in problems:
        print("PROBLEM  " + pr)
    if not problems:
        print("OK       no problems with sample or stress values")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
