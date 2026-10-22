# Deck runtime reference

Everything the runtime in `assets/deck-template.html` understands. The runtime block
(between `<!-- DECK-RUNTIME:BEGIN -->` and `<!-- DECK-RUNTIME:END -->`) is copied verbatim
into every deck; you only write sections 1–5 of the template. The runtime contains no design:
it fixes `.slide` at 1280 × 720 px and reads all colors from the deck's tokens.

## Contents
1. The variables block
2. Types and formats
3. Markup attributes (values, widths, tables, charts)
4. Derived values and custom rendering
5. CSS hooks
6. Slide layout and printing
7. What the user's data file looks like
8. The viewer: Edit data, Import, Export, Check

---

## 1. The variables block

```html
<script type="application/json" id="deck-vars">
{
  "deck": "q3-account-review",      // stable id; the data file is checked against it
  "version": "3",                    // bump when variables change
  "locale": "de-DE",                 // all number/date formatting uses this, never the browser's locale
  "currency": "EUR",                 // optional default for "currency" types without a code
  "vars": {
    "client.name":   { "type": "text",           "label": "Client legal name", "value": "Example Corp" },
    "q3.revenue":    { "type": "currency:EUR:0", "label": "Revenue Q3",        "value": 1250000 },
    "top_accounts":  { "type": "rows", "label": "Top accounts",
                       "fields": { "name": "text", "revenue": "currency:EUR:0", "share": "percent:1" },
                       "value": [ { "name": "Account A", "revenue": 420000, "share": 0.21 } ] }
  }
}
</script>
```

- Must be strict JSON (no comments — the comments above are only for this reference).
- `label` is what the user sees in the exported data template, so write it for them:
  say what the value is and, where useful, its unit ("Headcount, FTE at quarter end").
- `"sampleCheck": false` (optional): count a value as filled in even when it equals the sample.
  By default a value equal to the sample stays marked "sample", which catches an exported
  template that was imported without being filled in.
- The first key segment groups fields in the **Edit data** form (`client.*`, `rev.*`), so
  choose prefixes that make sensible groups for the user.
- Keys: lowercase, dotted, neutral (`client.name`, `kpi.nps`, `contract.end_date`).
  Never encode anything real in a key — keys travel with the dummy file.

## 2. Types and formats

A type is `kind[:options]`. Options in any order: digits (`0`, `1`, `2`), a currency code
(`EUR`, `USD`), `+` (always show the sign), or a style word.

| Type | Value in JSON | Example output (en-GB) |
|---|---|---|
| `text` | `"Example Corp"` | Example Corp |
| `number`, `number:1` | `1234.56` | 1,234.56 / 1,234.6 |
| `integer` | `1234` | 1,234 |
| `percent`, `percent:1`, `percent:1:+` | `0.125` (fraction!) | 13% / 12.5% / +12.5% |
| `currency:EUR`, `currency:EUR:0` | `1250000` | €1,250,000.00 / €1,250,000 |
| `currency:EUR:compact`, `currency:EUR:compact:1` | `1250000` | €1.3M / €1.3M |
| `compact`, `compact:1` | `48200` | 48K / 48.2K |
| `date`, `date:long`, `date:short`, `date:month`, `date:month-short`, `date:year` | `"2026-03-31"` | 31 Mar 2026 / 31 March 2026 / 31/03/2026 / March 2026 / Mar 2026 / 2026 |
| `rows` | list of objects, see `fields` | rendered by `data-rows` / charts |

Numbers must be plain JSON numbers: no quotes, units or thousands separators. This is
what makes the replacement deterministic — `"1.000"` could mean one or one thousand,
so the import rejects it and keeps the sample value.

Any element can override the display format with `data-format="…"` (the value's type is
still used for validation).

## 3. Markup attributes

All value-bearing elements are **empty** in the source. The runtime fills them on every
render; the lint script fails if they contain text.

### Single values
```html
<span data-var="client.name"></span>
<span data-var="q3.revenue" data-format="currency:EUR:compact"></span>
<span class="signed" data-var="q3.growth"></span>   <!-- deck CSS can color it via .is-pos / .is-neg -->
```

### Bars / progress widths
`data-width="key"` / `data-height="key"` sets width/height to value × 100 % (clamped 0–1).
Use a percent-type variable or a derived share.
```html
<div class="bar-track"><div class="bar-fill" data-width="target.attainment"></div></div>  <!-- classes styled in deck-layout -->
```

### Tables and repeated blocks (`rows` variables)
The host element contains one `<template>`; each row clones it.
```html
<table>
  <thead><tr><th>#</th><th>Account</th><th class="num">Revenue</th></tr></thead>
  <tbody data-rows="top_accounts" data-sort="-revenue" data-max="5">
    <template><tr><td data-index></td><td data-field="name"></td><td class="num" data-field="revenue"></td></tr></template>
  </tbody>
</table>
```
- `data-sort="field"` ascending, `"-field"` descending. `data-max="5"` limits rows — always
  set it when the real list could be longer than the space allows.
- `data-field-width="share"` inside the template sets a width from a 0–1 field.
- Works for any element (`<ul data-rows>` + `<template><li>…</li></template>`, cards, etc.).

### Charts (static SVG drawn by the runtime, no libraries)
The chart fills its element, so give the element an explicit width and height in the deck's layout CSS.
```html
<!-- from single variables; labels are literal (or JSON array for labels containing commas) -->
<div class="chart" data-chart="bar" data-series="rev.q1,rev.q2,rev.q3,rev.q4" data-labels="Q1,Q2,Q3,Q4" data-highlight="last"></div>

<!-- several series: groups separated by | -->
<div class="chart" data-chart="line" data-series="a.q1,a.q2,a.q3|b.q1,b.q2,b.q3" data-labels="Q1,Q2,Q3" data-series-names="Plan,Actual"></div>

<!-- from a rows variable -->
<div class="chart" style="height:300px" data-chart="hbar" data-chart-rows="top_accounts"
     data-label-field="name" data-value-field="revenue" data-sort="-revenue" data-max="6" data-highlight="first"></div>
```
| Attribute | Meaning |
|---|---|
| `data-chart` | `bar` (vertical, grouped if several series), `hbar` (horizontal, first series), `line` |
| `data-series` | variable keys, `,` within a series, `\|` between series |
| `data-labels` / `data-label-vars` | literal category labels / variables whose values are the labels (e.g. sensitive product names) |
| `data-chart-rows`, `data-label-field`, `data-value-field` | rows-variable source; `data-value-field` may list several fields for several series |
| `data-series-names` | legend names (legend appears with ≥ 2 series) |
| `data-format` | value-label format (defaults to the first variable's type) |
| `data-highlight` | `last`, `first` or a 1-based index: that bar in `--accent`, others `--chart-muted` |
| `data-zero="true"` | line chart y-axis starts at 0 |
| `data-label-width="0.35"` | hbar: share of width reserved for labels (default 0.3) |
| `data-sort`, `data-max` | as for tables |

Font size and family of chart text = the element's. Chart styling tokens (all optional, grey
fallbacks if unset — so always set them from the brief):

| Token | Used for | Falls back to |
|---|---|---|
| `--chart-1` … `--chart-6` | series colors | greys |
| `--chart-highlight` | `data-highlight` bar | `--accent` |
| `--chart-muted` | non-highlighted bars | `#ccc` |
| `--chart-text` | value labels, hbar labels | `--ink` |
| `--chart-label` | category labels, legend | `--ink-soft` |
| `--chart-axis` | baseline / zero line | `--rule` |
| `--chart-radius` | bar corner radius (e.g. `3px`) | `0` |
| `--chart-value-weight` | weight of value labels | `600` |
| `--chart-line-width` | line chart stroke | `2.5` |

Long category labels are shortened with "…" to fit (full text in a tooltip).

For any other chart form, draw it in `afterRender` (section 4).

## 4. Derived values and custom rendering

Every number that follows from other numbers is derived, so it stays right with real data:
totals, differences, growth, shares, averages, rankings, and also wording that depends on
the data ("grew"/"declined").

```html
<script id="deck-logic">
const DECK_LOGIC = {
  derived: {
    "q3.growth":   { type: "percent:1:+", label: "Growth vs Q2", calc: v => v["q3.revenue"] / v["q2.revenue"] - 1 },
    "q3.trend":    { type: "text", calc: v => v["q3.revenue"] >= v["q2.revenue"] ? "grew" : "declined" },
    "top.total":   { type: "currency:EUR:0", calc: v => v["top_accounts"].reduce((s, r) => s + r.revenue, 0) },
    "top.with_share": { type: "rows", fields: { name: "text", revenue: "currency:EUR:0", share: "percent:1" },
      calc: v => { const t = v["top_accounts"].reduce((s, r) => s + r.revenue, 0);
                   return v["top_accounts"].map(r => ({ ...r, share: t ? r.revenue / t : 0 })); } },
  },
  afterRender(values, api) {
    // Optional. values: frozen copy of all values. api.format(value, type), api.isDummy(key).
    // Use textContent / setAttribute only, never innerHTML with values.
  },
};
</script>
```
- Derived entries are computed in order, so later ones can use earlier ones.
- The calc receives a read-only view; reading an unknown key or returning NaN/Infinity
  (e.g. division by zero) shows ⚠ on the slide and an error in **Check** instead of a wrong number.
- A derived value counts as sample data if any input is still sample data.
- Derived values can be used everywhere a variable can (`data-var`, charts, `data-rows`).

## 5. CSS hooks

| Selector | Set when |
|---|---|
| `.is-pos`, `.is-neg` | numeric value > 0 / < 0 (on `data-var` and `data-field` elements). Style e.g. `.is-neg.signed { color: var(--neg) }` |
| `.is-dummy` | the element shows a sample value; outlined in red when the user has loaded a partial data file |
| `.var-error` | undefined variable or failed calculation |
| `html[data-deck-state="sample" \| "partial" \| "real"]` | overall state; the "Sample data" badge on each slide disappears only in `real` |
| `.slide-num`, `.slide-count` | filled with the slide number / total |

## 6. Slide layout and printing

- Each slide is `<section class="slide">` inside `<main id="deck">`, designed at exactly
  1280 × 720 px (= 13.333 × 7.5 in, PowerPoint 16:9). The runtime wraps and scales it for
  the screen; print uses `@page { size: 1280px 720px }`, so **Print → Save as PDF** gives one
  page per slide at the right size with no settings to change ("Background graphics" is
  forced on via `print-color-adjust`).
- Content must fit inside the slide; `.slide` has `overflow: hidden`. The render check
  reports anything that spills.
- Fonts: no web fonts can load (network is blocked). Use system font stacks, or embed a font
  the user provides as a `data:` URI in an `@font-face` rule.
- Images (logos): embed as `data:` URIs. Remote URLs are blocked.
- Keyboard: `F` present, arrows/space/PageUp/PageDown navigate, `Esc` exits.

## 7. What the user's data file looks like

**Export data** produces it (as a template while only sample values are shown):

```json
{
  "deck": "q3-account-review",
  "version": "3",
  "values": {
    "client.name": "Example Corp",
    "q3.revenue": 1250000,
    "top_accounts": [ { "name": "Account A", "revenue": 420000, "share": 0.21 } ]
  },
  "_help": { "client.name": "Client legal name — text", "q3.revenue": "Revenue Q3 — plain number, no units or separators" }
}
```
On import: keys starting with `_` are ignored; a flat object without `values` also works;
invalid values are rejected one by one (sample value kept, error listed); missing keys keep
their sample value and are outlined; unknown keys are kept and re-exported, so one master
data file survives deck versions that drop a variable.

## 8. The viewer: Edit data, Import, Export, Check

The runtime adds a dark, compact viewer interface (toolbar, side panel, popover) on a dotted
canvas with labelled slide frames. It is part of the runtime, identical in every deck, never
printed, and not restyled per deck — the deck's design lives only inside the slides.

- **Toolbar**: deck title, data status (sample / partly yours / yours), Edit data, Import, Check,
  light/dark switch, Present, Export, PDF.
- **Light / dark mode** applies to the viewer only, never to the slides. It follows the system
  setting until the user picks one with the sun/moon button; that choice is the only thing the
  runtime stores in the browser (`localStorage` key `deck-viewer-theme`).

- **Edit data** opens a side panel. *Fields* tab: one input per variable, grouped by key
  prefix into collapsible sections that start collapsed (each shows how many of its values are
  the user's own; the filter box opens sections with matches); fields are labelled with `label`; numbers are typed plainly (`1250000.5`; percentages also as
  `12.5%`), dates with a date picker, `rows` variables as a small table with add/remove row.
  Each field shows *sample* / *yours* / *invalid*, a formatted preview and a reset button.
  Slides update while typing. *JSON* tab: the same data as JSON text to edit or paste, with
  Apply/Revert; problems are listed inline.
- **Import data** / drag-and-drop a `.json` file: replaces the current values (asks first if
  there are edits that weren't exported).
- **Export data**: downloads the current values with `_help` descriptions —
  `<deck>-data-template.json` while only sample values are shown, else `<deck>-data.json`.
- Edits not yet exported trigger the browser's "leave page?" warning.
- **Check**: missing, invalid, still-sample and unused values; undefined variables; failed
  calculations.
- **Present** (`F`) and **PDF** (warns if sample values would be printed).

Nothing typed or imported is written to the file, browser storage or the network; the only
stored item is the viewer's light/dark preference.
