---
name: ui-design-system
description: The one visual system for every client2 screen, measured from the ledger declaration window (client2/src/ontology_explorer.css); the declaration UI and the visual parts on its Spotfire standard (§9, client2/src/spotfire.css). Load before writing or reviewing any HTML/CSS/DOM-rendering JS. Owner 2026-09-11 「디자인 스킬 하나 만들어라. 원장 선언 창 css 기준으로」.
---

# UI design system — the ledger declaration window is the canon

Owner (2026-09-11): 「제발 ui 만들 때 마진 좀 넣어」 · 「고리 너무 커」 · 「체인 그래프를 줄여」 · 「디자인 스킬 하나 만들어라. 원장 선언 창 css 기준으로」.

**Canon file: `client2/src/ontology_explorer.css`.** Its header comment states the system; the rules below were MEASURED from that file on 2026-09-11 (values, not paraphrase). If this page and the file disagree, the file wins — fix this page, not the file.

Read this before touching any screen. Then open the canon file for the exact rule you are about to apply — this page tells you WHICH rule exists; the file is the value.

## 0. Quality comes from defaults, not diligence
Owner (2026-09-26): 「ui 이렇게 글씨 마진없이 쓰지 말랬지. 박스 기본 마진 아예 고정 스타일로 박아」 · 「클라 세션이 만드는 ui 스타일이 기본적으로 너무 구려」.
```
box      the box owns the space inside it - one padding rule for every box body. A part writes no outer margin/padding
base     table · input/select · button · stat number · empty line · form row · meta line are styled ONCE in the base layer.
         A part with zero CSS already looks right; a part's CSS adds only what is its own
sample   one sample page renders every base element. A screen is composed from it.
         Need an element the sample lacks -> add it to the base layer and the sample FIRST, then use it
```
- A defect seen on one screen is fixed in the base layer, not on that screen - fixed on the screen, the next screen repeats it (the margin defect was fixed part by part and came back).
- The Design System document is drawn FROM the sample page. Code is the source; the document is its picture, and the round that changes the base layer redraws it.

## 1. Colour — the `--oe-*` roles, zero literals
```
--oe-bg        = var(--bg-inset)      --oe-surface   = var(--bg-surface)   --oe-surface-2 = var(--bg-header)
--oe-text      = var(--text)          --oe-muted     = var(--text-dim)     --oe-line      = var(--border)
--oe-accent    = var(--accent)        --oe-accent-soft = var(--accent-weak)
--oe-ok        = var(--success)       --oe-warn      = var(--warning)      --oe-danger    = var(--danger)
```
- The `--oe-*` roles in the canon's `:root` are the ONLY colour vocabulary, and they point at `tokens.css`. A hex or `rgb()` in a component is a defect, and so is a name nothing defines — a fallback on it is drawn in both themes (lead 3ea218524; the token harness counts it).
- States are MIXES of a role, never a fixed grey (a fixed grey dies in one of the two themes):
  hover `--oe-tint-hover` (text 7%) · press `--oe-tint-press` (14%) · row `--oe-tint-row` (4%) · accent hover `--oe-tint-accent-hover` (10%) · accent press `--oe-tint-accent-press` (18%) · label ink 70% · th ink 60% · meta ink 50%.
- Theme follows the site toggle (`:root[data-theme=…]` + `color-scheme`), not the OS. Both halves live in `tokens.css`; never define a colour that exists in only one theme.

## 2. Type
```
heading   "Barlow Condensed" 600 · line-height 1.12 · letter-spacing -0.015em
body      "Barlow" 400 · 15px / 1.55
mono      identifiers · JSON · keys   (--oe-font-mono)
scale     h1 42 · h2 32 · h3 25 · h4 20 · h5 16 · h6 13 uppercase 0.08em
parts     card title 17 · button 14 · label 12 · tag/refusal 11 · meta 12 (was 10 — owner 09-27)
tokens    --fs-h1 … --fs-h6 · --fs-title · --fs-body · --fs-button · --fs-label · --fs-tag · --fs-meta (tokens.css — these twelve, no thirteenth)
```
- Every face has a system fallback; sizes are px and land even if the webfont is blocked.
- A part states its own size only from the `parts` row. A table header at h3 size is the defect the owner called 「고리 너무 커」.

## 3. Space — the 3.4 grid, and margins are not optional
```
grid      3.4 · 6.8 · 10.2 · 13.6 · 20.4 · 27.2   (px)
topbar    padding 10.2 13.6 · gap 10.2
panel     padding 13.6 10.2
row       padding 6.8 · gap 6.8 · list rows 7 12 (mockup figures, kept as stated)
```
- Every part has space BETWEEN it and its neighbours and INSIDE it before its border - the box gives it (§0), not the part. Nothing — table header, first/last column, SVG, card body — touches a line. Test: in a screenshot, if glyphs touch a border the part is not finished.
- Pick a grid value; do not write another px. The scale lives in `tokens.css` as `--space-1..6` = 3.4 · 6.8 · 10.2 · 13.6 · 20.4 · 27.2 (landed C-80, 2026-09-11) — use the token, never the literal. ⚠️ The canon file still spells these as literals: it predates the tokens and is where the values came from, so a difference there is history, not a second scale.
- Two more values landed with them, for the same reason (a number two places spell can diverge): `--fs-label` (table and card labels) and `--graph-max-height` (the cap a drawing's box enforces, §5).

## 4. Edges and surfaces
- **Corner radius 0. Everywhere.** Cards and dialogs are transparent + a 1px hairline `var(--oe-line)`; an accent-bordered box is `1px solid var(--oe-accent)` on transparent.
- Section titles: h6 style (13px uppercase 0.08em) with 3.4/6.8 padding. Empty sections say so in one line — a bare heading reads as broken.
- Focus: `:focus` silent, `:focus-visible` = 2px accent ring, `outline-offset: 2px`.
- Popovers hang below their row (surface bg, shadow `0 8px 24px rgb(0 0 0/.18)`); they are not part of the target.

## 5. Size of a part on a page
- A part never grows past its viewport share. Tables scroll inside their box; an SVG (graph, map) has a height cap from a token and scales to width inside it (`preserveAspectRatio`), with pan/scroll inside the box. `width:100%; height:auto` on a viewBox that grows with node count is the defect the owner called 「체인 그래프를 줄여」.
- Numbers in columns: `font-variant-numeric: tabular-nums`, right-aligned; one row per item, one line high.

## 6. Words on the screen
- 「설명 문구 주저리주저리 금지」: labels, units, reference time, refusal reason + next action. No feature prose, no subtitle repeating the title. Symbols and short nouns over sentences.
- Refusal sentences are the SERVER's; render `detail` verbatim.

## 7. Assembly (조립식) — see CLAUDE.md UI 상설
- A part is a class with its own div, receives its mount and deps, holds no module state; two instances on one page must not interfere. Layout (grid placement, order) lives OUTSIDE the part in the page.

## 8. 화면 커밋 관문 — the screen gate (lead 1343e5cca, owner 10-09 「이런 잘림 같은 ui 요소는 사전에 차단하면 안 됨?」)
```
checker  client2/tests/screen_layout_harness.mjs - the runner calls it with --mutate; a finding blocks the landing
         every html entry in client2/dist, in real Chrome at 1920x950, 1536x864 and 1280x720, driven through its states (filters, a row picked,
         the queues' nine states, a long table name, the side panel narrowed, each header panel opened)
         clip · overflow · panel under its button · [object ...] / undefined / NaN · a button boxed out of its line ·
         a long text cell past three lines while a short column beside it is half empty ·
         a word broken between two of its letters
         answers come from client2/tests/fixtures/screens_answers.json.gz - a GET it lacks is red: capture_screens.py
a cut made on purpose  data-clip-ok on that element (it and what is under it). Never a list inside the checker
a break made on purpose data-wrap-ok (a long id that must wrap); a word or a name is otherwise never broken - its
                       column is as wide as its longest word (lead 10-09)
a table's columns      a short cell (a time, a count, a state word, an id) carries cell-fit - as wide as its words, one line;
                       the long text cells take the rest. No hand px widths on columns (owner 10-09)
a new screen or state   a step in the checker's DRIVE, in the same commit as the screen
report   every screen commit's report carries one line: «크롬 MCP 로 연 화면 · 크기 · 본 것» - Claude in Chrome, the
         built page, opened by hand. Without it the lead does not merge, and the lead opens the same screen first
```

## 9. 스팟파이어 표준 — the Spotfire standard (owner 10-13 「선언 ui 같은 거는 스팟파이어 표준으로 스킬이랑 css 부품, 디자인 규격 만들어서 계속 써」, lead b72a0ea4f)
The one system, widened - not a second one. §0's rules hold (base layer once · sample page first · document drawn from it).
```
when     the declaration UI and the visual parts: a visual part and its kinds · its properties and filters panels · the
         slot picker · the Sheet · the R&D board's parts. Other screens (the grid · admin · walk) stay on the canon above
         until the owner says otherwise; the ledger declaration window is read as this standard's when it is next rebuilt
source   measured on the owner's Spotfire (task/SPOTFIRE_SCATTER_REFERENCE.md §11)
files    tokens   client2/src/tokens.css  --sf-*  - both themes' blocks and the shared one; nothing else defines a Spotfire value
         parts    client2/src/spotfire.css      - the base layer, once; `.sf` on a screen's root gives the face, text, ground
         canvas   client2/src/testbed/palette.js - only reads the tokens (paletteOf), read again each time a part draws
         sample   client2/sample.html «Spotfire standard» - every part below, both themes
```
```
part     .sf-part (.is-active) · .sf-part__title · .sf-part__t · .sf-part__meta · .sf-part__body · .sf-say
pill     .sf-pill (.sf-pill--v) · .sf-pill__caret · .sf-plus · .sf-note        border and caret on the part's hover, always in a panel
legend   .sf-legend · __ttl · __row · __v (.is-dim) · __plain · __ico · __name
table    .sf-table (a grid: __col · __row · __corner · __total · td.is-marked) · .sf-table--rows (a striped list: .is-num ·
         .is-id · .is-member · tr.is-hub · __toggle)
status   .sf-status                                                       panel   .sf-panel · __h - light in both themes
props    .sf-props__name · __tabs (.is-on) · __sec · __h · __line · __lab · __sel · __cond · __x · __add
filter   .sf-filter · __h · __range · __num · __v · __n
popover  .sf-pop-host · .sf-pop · __col · __lab · __it (.is-on) · __n · __hr · __reds · __red (.is-on) · __why
button   .sf-btn
```
```
sizes    text 12/15 Roboto · title 19/23 Roboto Light, its text 16 from the part's top and 20 from its left · tabs 13 Medium ·
         pill 21 high, radius 100 · cell 18 high (a row 19 with its line), inset 2 · 8 · 1 · 1 (top right bottom left) ·
         a list row 19 · legend 150 wide, a value line 20, its icon 14 · part padding 12 · between parts 2 · status bar 32 ·
         the active line 2 drawn over the part's edge - it takes no room
colours  dark ground #2A2A2A / page #232323 · marked cell #00A650 white bold · the seven category colours fill / line - all
         as --sf-* tokens; a part writes none
```
- One class of specificity, not the base layer's zero: on a page that loads base.css too, its element rules never win, whatever order the sheets load in. A part that is a button, a field, a table or a cell says every property base.css sets on those (height, letter-spacing, centring, uppercase heads, cell padding, full width).
- A screen's own layout (its grid, a kind's trays) is the screen's CSS, more specific than the part (its container class with the part's) - the test bed's `testbed.css` is the example.
- Don't: a `--tb-*` or any second name for a Spotfire value · a colour or a Spotfire size written in a part · a canvas colour as a JS constant (the canvas reads `paletteOf`) · a part added to a screen before the sample draws it.
- Gate: `testbed_harness` T22 (no colour in spotfire.css · testbed.css) · T25 (the tokens hold §11's values; every token the canvas reads defined) · T26 (the palette read off a document; the build's short hex mixed as its long one) · `css_token_definition` · `screen_layout` (the sample's section and the test bed, both themes) · before/after shots of a screen moved onto it, pixel by pixel, beside the Spotfire screen with the spacings measured.

## How to apply — every UI round
```
1 mockup   a new screen or a layout change -> draw it first on the Design canvas (Artifact type "Design", the project's
           Design System attached). Put the link in the report; the lead takes it to the owner; build after the OK.
           A fix inside an existing layout -> no mockup
2 build    compose from the base elements (§0). Values: open the canon for the rule (grep the value), copy the RULE.
           A new value -> ONE token in tokens.css (or the canon's :root for --oe-*), never a local literal
3 look     open the screen yourself at 1280 and 375 wide - the built bundle (check its hash). Shoot before and after
4 review   hand the shots to the ui-designer agent for DEFECTS only: glyph on a line · double margin · off-scale size ·
           edges out of line · crowding. Fix, shoot once more
5 report   before/after side by side (+ the mockup when there was one), and the harness gate:
           every table/SVG/card body >= one grid step inside its box · sizes from §2 ·
           no colour literal in the diff (git grep -nE "#[0-9a-f]{3,6}|rgb\(" -- <changed files> -> 0 new lines)
```
The lead opens the screen and looks at the PICTURE, not the checklist, before the round closes.
