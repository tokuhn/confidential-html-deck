#!/usr/bin/env python3
"""Static checks for a confidential HTML deck (stdlib only).

Usage:  python3 lint_deck.py path/to/deck.html [--template path/to/deck-template.html]

Errors (exit code 1):
  - no / weakened Content-Security-Policy, external resources or network code
  - deck-vars block missing, invalid JSON, or a value that does not match its type
  - a slide references a variable that is not defined
  - data-var / data-field elements that already contain text, or a data-deck-rendered
    attribute: the file was saved from a rendered browser page and may hold real data
  - runtime block missing or not identical to the template's runtime
Warnings:
  - numbers in slide text outside data-var elements (possible hardcoded sensitive values)
  - variables that are defined but never used, missing labels, innerHTML in deck logic
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

KINDS = {"text", "number", "integer", "percent", "currency", "compact", "date", "rows"}
NUMERIC = {"number", "integer", "percent", "currency", "compact"}
REF_ATTRS = ("data-var", "data-width", "data-height", "data-rows", "data-chart-rows")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
NUM_RE = re.compile(
    r"(?:[€$£¥]\s?\d)|(?:\d\s?[€$£¥%])|(?:\d[\d.,']*\d\s?(?:k|K|m|M|bn|Mio|Mrd|Tsd)\b)|(?:\b\d{1,3}(?:[.,']\d{3})+\b)|(?:\b\d+[.,]\d+\b)|(?:\b\d{4,}\b)"
)
YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def kind_of(t):
    return str(t or "text").split(":")[0]


def validate(value, t, fields=None):
    k = kind_of(t)
    if k == "text":
        return None if isinstance(value, str) else "expected a string"
    if k == "date":
        return None if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else 'expected "YYYY-MM-DD"'
    if k in NUMERIC:
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) else "expected a number"
    if k == "rows":
        if not isinstance(value, list):
            return "expected a list of row objects"
        if not fields:
            return 'rows variables need a "fields" object, e.g. {"name": "text", "revenue": "currency:EUR:0"}'
        for i, row in enumerate(value):
            if not isinstance(row, dict):
                return f"row {i + 1} is not an object"
            for f, ft in fields.items():
                if f not in row:
                    return f'row {i + 1} is missing field "{f}"'
                e = validate(row[f], ft)
                if e:
                    return f'row {i + 1}, field "{f}": {e}'
        return None
    return f'unknown type "{t}"'


class Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # (tag, attrs)
        self.refs = []           # (attr, key)
        self.filled = []         # data-var/data-field elements with text
        self.slide_text = []     # (text, context)
        self.scripts = {}        # id -> text
        self.styles = []
        self.attrs_all = []
        self.root_attrs = {}
        self.cur_script = None
        self.in_style = False
        self.template_depth = 0
        self.slides = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.attrs_all.append((tag, a))
        if tag == "html":
            self.root_attrs = a
        if tag == "section" and "slide" in (a.get("class") or "").split():
            self.slides += 1
        for attr in REF_ATTRS:
            if attr in a and a[attr]:
                self.refs.append((attr, a[attr].strip()))
        if a.get("data-series"):
            for g in a["data-series"].split("|"):
                for k in g.split(","):
                    if k.strip():
                        self.refs.append(("data-series", k.strip()))
        if a.get("data-label-vars"):
            for k in a["data-label-vars"].split(","):
                if k.strip():
                    self.refs.append(("data-label-vars", k.strip()))
        if tag == "template":
            self.template_depth += 1
        if tag == "script":
            self.cur_script = [a.get("id") or f"script{len(self.scripts)}", a.get("type", ""), ""]
        if tag == "style":
            self.in_style = True
        if tag not in VOID:
            self.stack.append((tag, a))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag == "script" and self.cur_script:
            self.scripts[self.cur_script[0]] = self.cur_script[2]
            self.cur_script = None
        if tag == "style":
            self.in_style = False
        if tag == "template":
            self.template_depth = max(0, self.template_depth - 1)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.cur_script is not None:
            self.cur_script[2] += data
            return
        if self.in_style:
            self.styles.append(data)
            return
        if not data.strip():
            return
        holders = [a for _, a in self.stack if "data-var" in a or "data-field" in a or "data-index" in a]
        if holders:
            self.filled.append((holders[-1].get("data-var") or holders[-1].get("data-field") or "data-index", data.strip()[:60]))
            return
        in_slide = any("slide" in (a.get("class") or "").split() for t, a in self.stack if t == "section")
        if in_slide and self.template_depth == 0:
            if any("data-lint-ok" in a or "data-chart" in a for _, a in self.stack):
                return
            self.slide_text.append(data.strip())


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    path = Path(args[0])
    tpl = Path(args[args.index("--template") + 1]) if "--template" in args else Path(__file__).resolve().parent.parent / "assets" / "deck-template.html"
    src = path.read_text(encoding="utf-8")
    errors, warns = [], []

    s = Scan()
    s.feed(src)

    # 1. Network isolation
    m = re.search(r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]+content=(["\'])(.*?)\1', src, re.I | re.S)
    if not m:
        errors.append("Content-Security-Policy meta tag is missing (it guarantees the deck makes no network requests).")
    else:
        csp = m.group(2)
        for need in ("default-src 'none'", "connect-src 'none'"):
            if need not in csp:
                errors.append(f"CSP is missing {need}")
        if re.search(r"https?:|\*", csp):
            errors.append("CSP allows remote origins; it must stay local-only.")
    for tag, a in s.attrs_all:
        for attr in ("src", "href", "action", "poster", "srcset", "data"):
            v = (a.get(attr) or "").strip()
            if re.match(r"^(https?:)?//", v, re.I):
                errors.append(f"External resource <{tag} {attr}=\"{v[:80]}\">: embed it (data: URI) or remove it.")
    css = "\n".join(s.styles)
    if re.search(r"@import|url\(\s*['\"]?(https?:)?//", css, re.I):
        errors.append("CSS loads an external resource (@import or remote url()).")
    for sid, body in s.scripts.items():
        if sid == "deck-runtime" or sid == "deck-vars":
            continue
        if re.search(r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts)\b|\bimport\s*\(", body):
            errors.append(f"Script #{sid} contains network code.")
        if re.search(r"\b(localStorage|sessionStorage|indexedDB|document\.cookie)\b", body):
            errors.append(f"Script #{sid} uses browser storage; real values must stay in memory only.")
        if re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML", body):
            warns.append(f"Script #{sid} writes HTML; use textContent for values.")

    # 2. Saved-from-browser detection
    if "data-deck-rendered" in s.root_attrs or "data-deck-state" in s.root_attrs:
        errors.append("The <html> element carries data-deck-rendered/data-deck-state: this file was saved from a rendered browser page and MAY CONTAIN REAL DATA. Do not use it; ask for the original deck file.")
    if s.filled:
        sample = ", ".join(f"{k}='{t}'" for k, t in s.filled[:5])
        errors.append(f"{len(s.filled)} data-var/data-field element(s) already contain text ({sample}). Either a value was typed in by hand or the file was saved from a rendered page and MAY CONTAIN REAL DATA. These elements must be empty in the source.")
    if re.search(r"data-rendered-(row|chart)", src.split("<!-- DECK-RUNTIME:BEGIN -->")[0]):
        errors.append("Rendered rows/charts found in the slide markup: the file was saved from a rendered page and MAY CONTAIN REAL DATA.")

    # 3. Variables
    defs, derived = {}, set()
    raw = s.scripts.get("deck-vars")
    if raw is None:
        errors.append('No <script type="application/json" id="deck-vars"> block.')
    else:
        try:
            spec = json.loads(raw)
            for f in ("deck", "version", "locale"):
                if not spec.get(f):
                    warns.append(f'deck-vars has no "{f}".')
            defs = spec.get("vars") or {}
            for k, d in defs.items():
                if not re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)*", k):
                    warns.append(f'Variable key "{k}": use neutral lowercase dotted keys like "client.name".')
                if not isinstance(d, dict) or "value" not in d or "type" not in d:
                    errors.append(f'Variable "{k}" needs "type" and "value".')
                    continue
                if kind_of(d["type"]) not in KINDS:
                    errors.append(f'Variable "{k}": unknown type "{d["type"]}".')
                    continue
                e = validate(d["value"], d["type"], d.get("fields"))
                if e:
                    errors.append(f'Variable "{k}": sample value invalid ({e}).')
                if not d.get("label"):
                    warns.append(f'Variable "{k}" has no "label" (shown to the user in the data template).')
        except json.JSONDecodeError as e:
            errors.append(f"deck-vars is not valid JSON: {e}")
    logic = s.scripts.get("deck-logic", "")
    dm = re.search(r"derived\s*:\s*\{", logic)
    if dm:
        derived = set(re.findall(r"[\"']([A-Za-z0-9_.\-]+)[\"']\s*:\s*\{", logic[dm.end():]))
    known = set(defs) | derived
    used = set()
    for attr, k in s.refs:
        used.add(k)
        if k not in known:
            errors.append(f'{attr}="{k}" refers to an undefined variable.')
    for k in defs:
        if k not in used and f'"{k}"' not in logic and f"'{k}'" not in logic:
            warns.append(f'Variable "{k}" is defined but not used anywhere.')

    # 4. Hardcoded numbers in slide text
    hits = []
    for t in s.slide_text:
        for mm in NUM_RE.finditer(t):
            tok = mm.group(0)
            if YEAR_RE.match(tok.strip()):
                continue
            hits.append(f"'{tok.strip()}' in \"{t[:70]}\"")
    if hits:
        warns.append(f"{len(hits)} number(s) typed directly into slide text. If any is sensitive, make it a variable; "
                     f"otherwise add data-lint-ok to its element: " + "; ".join(hits[:8]) + (" …" if len(hits) > 8 else ""))

    # 5. Runtime identical to template
    def runtime(text):
        mm = re.search(r"<!-- DECK-RUNTIME:BEGIN -->.*?<!-- DECK-RUNTIME:END -->", text, re.S)
        return mm.group(0) if mm else None
    rt = runtime(src)
    if rt is None:
        errors.append("DECK-RUNTIME block (between the BEGIN/END markers) is missing.")
    elif tpl.exists():
        trt = runtime(tpl.read_text(encoding="utf-8"))
        if trt and trt != rt:
            errors.append(f"Runtime block differs from {tpl.name}. Copy it verbatim (or run update_runtime.py).")

    if s.slides == 0:
        errors.append('No <section class="slide"> found.')

    print(f"Deck: {path.name} · {s.slides} slides · {len(defs)} variables · {len(derived)} derived")
    for e in errors:
        print("ERROR  " + e)
    for w in warns:
        print("WARN   " + w)
    if not errors and not warns:
        print("OK     no issues")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
