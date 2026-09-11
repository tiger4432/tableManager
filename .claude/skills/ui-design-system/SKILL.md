---
name: ui-design-system
description: The one visual system for every client2 screen, measured from the ledger declaration window (client2/src/ontology_explorer.css). Load before writing or reviewing any HTML/CSS/DOM-rendering JS. Owner 2026-09-11 「디자인 스킬 하나 만들어라. 원장 선언 창 css 기준으로」.
---

# UI design system — the ledger declaration window is the canon

Owner (2026-09-11): 「제발 ui 만들 때 마진 좀 넣어」 · 「고리 너무 커」 · 「체인 그래프를 줄여」 · 「디자인 스킬 하나 만들어라. 원장 선언 창 css 기준으로」.

**Canon file: `client2/src/ontology_explorer.css`.** Its header comment states the system; the rules below were MEASURED from that file on 2026-09-11 (values, not paraphrase). If this page and the file disagree, the file wins — fix this page, not the file.

Read this before touching any screen. Then open the canon file for the exact rule you are about to apply — this page tells you WHICH rule exists; the file is the value.

## 1. Colour — ten roles, zero literals
```
--oe-bg        = var(--bg-inset)      --oe-surface   = var(--bg-surface)   --oe-surface-2 = var(--bg-header)
--oe-text      = var(--text)          --oe-muted     = var(--text-dim)     --oe-line      = var(--border)
--oe-accent    = var(--accent)        --oe-accent-soft = var(--accent-weak)
--oe-ok        = var(--success)       --oe-warn      = var(--warning)
```
- The ten `--oe-*` roles are the ONLY colour vocabulary, and they point at `tokens.css`. A hex or `rgb()` in a component is a defect.
- States are MIXES of a role, never a fixed grey (a fixed grey dies in one of the two themes):
  hover `--oe-tint-hover` (text 7%) · press `--oe-tint-press` (14%) · row `--oe-tint-row` (4%) · accent hover `--oe-tint-accent-hover` (10%) · accent press `--oe-tint-accent-press` (18%) · label ink 70% · th ink 60% · meta ink 50%.
- Theme follows the site toggle (`:root[data-theme=…]` + `color-scheme`), not the OS. Both halves live in `tokens.css`; never define a colour that exists in only one theme.

## 2. Type
```
heading   "Barlow Condensed" 600 · line-height 1.12 · letter-spacing -0.015em
body      "Barlow" 400 · 15px / 1.55
mono      identifiers · JSON · keys   (--oe-font-mono)
scale     h1 42 · h2 32 · h3 25 · h4 20 · h5 16 · h6 13 uppercase 0.08em
parts     card title 17 · button 14 · label 12 · tag/refusal 11 · meta 10
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
- Every part has space BETWEEN it and its neighbours and INSIDE it before its border. Nothing — table header, first/last column, SVG, card body — touches a line. Test: in a screenshot, if glyphs touch a border the part is not finished.
- Pick a grid value; do not write another px. ⚠️ Measured 2026-09-11: `tokens.css` carries NO spacing tokens yet — the grid lives as literals in the canon file. C-80 lands `--space-*` tokens on this grid; once they exist, use the token, never the literal.

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

## How to apply — every UI round
1. Open the canon file for the rule you need (grep the value); copy the RULE, not the number from memory.
2. New value needed? First measure whether the canon already has it. If not, add ONE token to `tokens.css` (or the canon's `:root` block for `--oe-*`) and use it — never a local literal.
3. Gate in the harness: bounding box of every table/SVG/card body is ≥ one grid step inside its container; font sizes in the part come from §2; no colour literal in the diff (`git grep -nE "#[0-9a-f]{3,6}|rgb\(" -- <changed files>` returns 0 new lines).
4. The lead opens the screen and looks at the PICTURE, not the checklist, before the round closes.
