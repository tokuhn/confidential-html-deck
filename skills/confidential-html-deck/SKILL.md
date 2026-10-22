---
name: confidential-html-deck
description: Build PowerPoint-style 16:9 slide decks as a single self-contained HTML file in which every sensitive value (client names, figures, KPIs, dates, deal terms) is a variable holding DUMMY data; the user loads the real values locally from a JSON file in their browser, so real data never reaches Claude. Use this skill whenever the user asks for slides, a deck, a presentation or a pitch, or a new version of a deck, that involves customer, client, financial, HR or any other confidential data, or mentions placeholders, dummy or sample values, anonymised data, or a data JSON for a deck — even if they don't name the skill. Also use it when the user uploads an HTML deck built with it.
---

# Confidential HTML deck

The user works with data they may not share with Claude. This skill splits a deck into
two parts that never meet in the cloud:

- **The deck file** (built by Claude): layout, wording, charts, logic, and *dummy* values.
  This is the only thing that is ever uploaded or edited here.
- **The data** (kept by the user): the real values, typed into the deck's **Edit data**
  panel (a form, or the raw JSON) or loaded from a JSON file with **Import data**. They exist
  only in that browser tab's memory and are never written back into the HTML. **Export data**
  saves them as a JSON file for next time. Output is a PDF via Print.

Everything below serves one goal: the dummy deck must be complete enough that the user
never needs to paste a real value into a chat to get a correct deck, and nothing in the
workflow should tempt them to upload a file that contains real data.

## Files in this skill

- `assets/deck-template.html` — start every deck from a copy of this. It has no design on
  purpose: the token and layout sections are empty. Sections 1–5 are per-deck; section 6
  (the runtime, between the `DECK-RUNTIME` markers) is copied verbatim.
- `assets/example-deck.html` — a grey wireframe showing the mechanics (derived headline,
  rows-based chart and table, progress bar, data-dependent wording). Copy patterns from its
  markup and logic, never its look.
- `references/runtime.md` — full reference for types, formats, tables, charts, derived
  values and CSS hooks. Read it before building the first slide of a deck.
- `scripts/lint_deck.py` — static checks (privacy, undefined variables, hardcoded numbers).
- `scripts/render_check.py` — renders in headless Chromium with sample and stress values,
  finds overflow, writes slide PNGs and the sample-data PDF preview the user reviews in
  the chat. Needs Playwright.
- `scripts/update_runtime.py` — swaps an older deck's runtime for the current one.

## Workflow

### 1. Brief — the user defines the design language, every time

There is no house style. Never fall back on a default look, a previous deck's look, or the
example's wireframe. Before building, settle what you don't know — ask in one go, skip what
the user already said:

- **Audience and goal** of the deck, and the slide outline (or offer one).
- **Design language**: colors (with hex values if they have them), typefaces, logo, layout
  character (dense/airy, grid, image use), chart style, tone of headlines. A screenshot of
  a blank master slide or a style guide page is ideal; warn that screenshots of real
  slides may show confidential content. Logos and fonts must be embedded as `data:` URIs
  (the deck blocks all network access), so ask for the files.
  If the user says "you decide", offer two or three short, distinct directions and let them
  pick one before you build; don't choose silently.
- **Locale and currency** (e.g. `de-DE` + EUR gives `1.250.000 €`). This decides all
  number and date formatting.
- **Shape of the data, not the data**: which kinds of values appear (names, revenue, counts,
  dates, lists of accounts…), roughly how long texts get, rough magnitudes (thousands or
  billions), and the maximum length of lists. Ask for ranges, not figures. This is what lets
  dummy values be realistic so the layout holds when the real ones arrive.

Never ask for real values. If the user pastes something that looks like real confidential
data, don't put it into the deck; use a dummy in its place and mention once, briefly, that
the real value belongs only in their local data file.

### 2. Decide what is a variable

A value is a variable if it comes from the user's data or would identify a client, person
or deal. When unsure, make it a variable — a variable costs nothing, a hardcoded secret
defeats the whole design. Typical variables:

- client, person, product, project and partner names; locations
- every figure from their data: revenue, costs, prices, volumes, headcount, KPIs, scores
- dates of deals, contracts, milestones; contract terms; percentages from their data
- list content: top accounts, line items, risks with amounts

Not variables: your own structure and wording ("Executive summary"), generic statements,
the year in a title if the user says it's fine.

Keys are neutral and stable: `client.name`, `rev.q3`, `contract.end_date`, `top_accounts`.
They travel with the dummy file, so they must not reveal anything themselves.

### 3. Dummy values

Dummy values are what the user sees until they import, and what the layout is designed
around. Make them:

- **Obviously fake** — "Example Corp", "Account A", "Jane Doe", round-ish numbers — so a
  sample deck can never be mistaken for a real one (the deck also badges every slide
  "Sample data" until all values are loaded).
- **Realistic in shape** — same order of magnitude and similar text length as the real
  data the user described. A three-letter dummy for a forty-letter company name hides a
  layout break.
- **Internally consistent** — totals add up, shares sum to ~100 %, dates are in order — so
  the derived values and charts look plausible.
- **Unlikely to equal the real value.** The deck treats a value that still equals the sample
  as not filled in (it stays marked "sample"). For variables whose real value may well equal
  the dummy — small counts, a quarter number, a fixed currency — add `"sampleCheck": false`.

### 4. Build

1. Copy `assets/deck-template.html` to the output file. Keep the CSP meta tag as is.
2. Fill the `deck-vars` block: `deck` id, `version` "1", `locale`, and every variable with
   `type`, `label` (written for the user who will fill in the data file) and dummy `value`.
3. Write the design tokens in `deck-theme` and all layout and component CSS in
   `deck-layout` from the brief. Both are empty in the template; the runtime only fixes
   the slide size. Chart colors, axis, label and highlight colors come from the tokens too
   (see `references/runtime.md`), so set them to match the brief.
4. Write the slides as `<section class="slide">` elements at 1280 × 720 px. Every variable
   appears as an **empty** element: `<span data-var="client.name"></span>`. Sentences mix
   fixed text and variables: `Revenue <span data-var="q3.trend"></span> to <span data-var="q3.revenue"></span>.`
5. Put every computed number in `DECK_LOGIC.derived` — growth, totals, shares, differences,
   rankings, and data-dependent wording. Never calculate a number yourself and type it in:
   it would be right for the dummy data and wrong for the real data.
6. Tables and lists use `rows` variables with `data-rows` + `<template>`; set `data-max` to
   what fits. Charts use `data-chart` (bar, hbar, line); other visuals go in `afterRender`.
   Details in `references/runtime.md`.
7. Make every claim about the data true for *any* data. A headline like "A strong quarter,
   ahead of plan" written while looking at dummy numbers may be false for the real ones,
   and the user might present it without noticing. Either derive the wording
   (`grew`/`declined`, `above`/`below`, a headline chosen by a rule) or phrase it neutrally
   ("Revenue by quarter"). If a slide needs a judgement only the user can make, leave a
   clearly marked text variable for it and say so when delivering.
8. For decks that recur (monthly, quarterly), keep keys relative to the period rather than
   absolute: a `rows` variable like `rev.history` (period + value, current last) instead of
   `rev.q3_2026`. The same data-file structure then works for every edition.

Design for the real data, not the dummy: leave room for longer names and an extra digit,
let text wrap, avoid fixed-width boxes around values, and cap lists.

### 5. Check

```bash
python3 scripts/lint_deck.py deck.html
python3 scripts/render_check.py deck.html --out check/ --pdf <deck>-preview-sample-data.pdf
```

Fix every ERROR/PROBLEM. For lint warnings about numbers in slide text: make the number
a variable if it could be sensitive, otherwise mark its element `data-lint-ok`.
Look at the screenshots in `check/sample/` and `check/stress/` — the stress run uses longer
texts, ~10× larger numbers, negative changes and twice the rows, approximating the real data
the dummy may understate. If Playwright isn't available, run only the lint and say so.

### 6. Deliver — HTML plus a sample-data PDF preview

Every delivery, including each design iteration, has two files:

- **`<deck>-preview-sample-data.pdf`**, the PDF that `render_check.py --pdf` printed from the
  deck with its sample values. Show it inline so the user reviews the design inside the
  chat (with whatever file tool the environment offers, choosing its inline/render display). The user should be able to go
  through every design round — layout, colors, wording, charts — on this preview alone,
  without opening a browser or switching windows.
- **`<deck>.html`**, offered as a download. The user only needs
  it once the design is final, to load the real data.

Send the preview first, then one or two lines on what changed, then ask what to adjust.
The preview carries the deck's "Sample data" badges, so it can't be mistaken for the real
thing. It renders with the fonts available in your workspace; if the brief uses a font
that isn't embedded as a `data:` URI and isn't installed here, say that the preview's type
may differ slightly from what the user will see. If Playwright isn't available, there is no
preview: say so and deliver the HTML only.

Once the user says the design is done (or on the first delivery, if they want to try it),
tell them briefly:
- First time: open the deck in Chrome or Edge, click **Edit data** and type the real values
  (or paste/edit them in the panel's JSON tab). The slides update as they type. Then
  **Export data** to keep the values as a JSON file; next time, **Import data** (or drop the
  file onto the page) loads them back. **Check** shows anything missing or invalid;
  **PDF** prints one page per slide.
- Their JSON never needs to be opened in another app. (On macOS a downloaded JSON may be
  blocked by Gatekeeper when double-clicked — Import and drag-and-drop are unaffected.)
- If variables were added, renamed or removed in this version, list them (see below).
- They should upload only the deck HTML for changes — never the data JSON or a PDF made
  from real data.

## New versions of an existing deck

The user uploads the dummy deck and describes changes.

1. Run `lint_deck.py` on the upload first. If it reports the file was saved from a rendered
   page or has filled value elements, stop: it may contain real data. Don't work from it,
   don't repeat its values, and ask for the original deck file instead.
2. Edit the deck. Keep variable keys stable — the user's data file is keyed by them.
   Prefer adding a new key over changing the meaning of an existing one.
3. Bump `version` in `deck-vars`. If the runtime block is older than the template's,
   run `update_runtime.py`.
4. Run the checks again, then deliver the HTML and a fresh sample-data PDF preview, with a
   short data change list:
   - **New** keys the user must add to their data file (with label and expected format),
   - **Renamed** keys (`old → new`) — the user must rename them in their JSON,
   - **Removed** keys (harmless; the import keeps unknown keys).
   The deck's **Check** panel will also show what's missing after import.

## If the user shares data anyway

If an upload is a data JSON from the deck, a filled PDF, or a deck saved from the
browser after importing, don't use or quote its values. Tell the user plainly that it may
contain their real data, that you haven't used it, and what to send instead (the deck HTML
with sample values). If you need the shape of their data, ask for it in words.
