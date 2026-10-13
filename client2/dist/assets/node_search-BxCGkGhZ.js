import{d as e,n as t}from"./tokens-JNgYoaf9.js";import{a as n}from"./absent-o9jpRT19.js";import{f as r,i,t as a}from"./disabled_reason-BP_E0n0W.js";import{t as o}from"./grid_image_column-B3uDJH4b.js";import{Q as s}from"./panel-DQRGKBJM.js";var c=`data-wk-styles`,l=`
/* The walk page's type, heights and spaces (lead 34d91c09d 8, 18da45b73; owner «간격 정리 넣어»): letters 13 (a line
   beside, the result tables - lead 10-11 W 12), 14 (body), 16 (titles); a control 44 high, a small one in a cell 28; every space a --space-* token.
   The screen gate asks all three of every element on the page. */
:root { --wk-fs-line: 13px; --wk-fs-body: 14px; --wk-fs-title: 16px; --wk-h: 44px; --wk-h-small: 28px;
  /* One face for the page; the mono only for ids and ways (lead 10-11 W 3). */
  --wk-font: 'IBM Plex Sans', 'Outfit', system-ui, sans-serif; --wk-mono: 'IBM Plex Mono', var(--font-mono, ui-monospace), monospace; }
.wk-bar, .wk-main { font-family: var(--wk-font); }
.wk-form { display: flex; flex-direction: column; gap: var(--space-3);
  font-family: var(--wk-font); font-size: var(--wk-fs-body); color: var(--text, #111); }
.wk-field { display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-2) var(--space-3);
  background: var(--bg-panel, transparent); border: 1px solid var(--border, #d4d4d8);
  border-radius: 8px; }
.wk-label { font-size: var(--wk-fs-line); letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--text-dim, #71717a); }
.wk-note { font-size: var(--wk-fs-line); color: var(--text-dim, #71717a); }

.wk-select, .wk-input, .wk-go, label.wk-check { min-height: var(--wk-h); box-sizing: border-box;
  font: inherit; }
.wk-select, .wk-input { width: 100%; padding: 0 var(--space-2); color: var(--text, #111);
  background: var(--bg-surface); border: 1px solid var(--border, #d4d4d8); border-radius: 6px; }
.wk-keyrow { display: flex; align-items: center; gap: var(--space-2); min-height: var(--wk-h); }
.wk-keyname { flex: none; width: 8.5em; font-family: var(--wk-font);
  font-size: var(--wk-fs-line); color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
label.wk-check { display: flex; align-items: center; gap: var(--space-2); padding: 0 var(--space-1); border-radius: 6px;
  font-family: var(--wk-font); font-size: var(--wk-fs-line); }
label.wk-check.is-on { background: var(--accent-weak); }
.wk-check input[type="checkbox"] { width: 22px; height: 22px; flex: none; margin: 0; }
/* 🔴 고르는 목록은 «폭»을 씁니다. 높이 44 는 손가락이라 그대로이고, 한 줄에 하나씩 세우는
   것만 그만둡니다 — 실측(480px 틀): 폼 1,623px 중 1,214px 가 체크박스 23줄이었습니다.
   🔴 칸은 «자기 이름만큼» 자랍니다(flex 0 1 auto) — 고정 폭으로 나누면 긴 이름이 잘리고,
   잘린 이름은 읽을 방법이 없습니다(이 폼에 hover 가 없습니다 — 휴대폰입니다). 최소 9.5em 은
   손가락이 옆 칸을 안 누르게 하는 바닥이고, 화면보다 긴 이름만 마지막 수단으로 잘립니다. */
.wk-checks { display: flex; flex-flow: row wrap; gap: var(--space-1) var(--space-2); }
label.wk-check { flex: 0 1 auto; min-width: 9.5em; max-width: 100%; }
label.wk-check > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* The sentence bar (lead 10-11 W A): one line in doing order - From · collect · through · in · Limits · Walk - over the
   result. Its chips one height (28), the dropdowns hang under their chip. */
.wk-bar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border); background: var(--bg-surface); font-size: var(--wk-fs-body); color: var(--text, #111); }
.wk-barword { color: var(--text-dim); font-size: var(--wk-fs-line); }
.wk-barpart, .wk-baskets, .wk-basketlist, .wk-basket { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-barpop { position: relative; }
.wk-barchip { list-style: none; display: inline-flex; align-items: center; height: var(--wk-h-small); padding: 0 var(--space-3);
  border: 1px solid var(--border-strong); border-radius: 999px; font-size: var(--wk-fs-line); white-space: nowrap; cursor: pointer; }
.wk-barchip::-webkit-details-marker { display: none; }
.wk-barpop[open] > .wk-barchip { border-color: var(--accent); color: var(--accent); background: var(--accent-weak); }
.wk-barpopbody { position: absolute; z-index: 5; top: calc(100% + var(--space-1)); left: 0; width: 380px; max-width: calc(100vw - var(--space-6));
  max-height: 70vh; overflow-y: auto; box-sizing: border-box; display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-3);
  background: var(--bg-surface); border: 1px solid var(--border-strong); border-radius: 8px; box-shadow: var(--shadow-pop); }
.wk-barpop:not([open]) > .wk-barpopbody { display: none; }
/* One that would run off the page's right edge hangs from its chip's right instead (the page script sets is-end). */
.wk-barpop.is-end > .wk-barpopbody { left: auto; right: 0; }
.wk-barpopbody .wk-field { gap: var(--space-2); padding: 0; background: transparent; border: 0; }
.wk-bar .wk-chip, .wk-bar .wk-add { min-height: var(--wk-h-small); padding: 0 var(--space-3); font-size: var(--wk-fs-line); }
/* Closed, collect's + shows only «+»; its list still names every type. */
.wk-bar .wk-add { width: 4.5em; }
.wk-bar > .wk-go { width: auto; min-height: var(--wk-h-small); height: var(--wk-h-small); margin-left: auto; padding: 0 var(--space-5); }
.wk-main { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; min-height: 0;
  overflow: auto; padding: var(--space-4) var(--space-5); }
.wk-mainhead { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3) var(--space-4); }
.wk-title { font-size: var(--wk-fs-title); font-weight: 600; overflow-wrap: anywhere; }
/* A name above its control: key, step and pick cells. */
.wk-cell { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.wk-cell > .wk-keyname { width: auto; }
.wk-cell-row { flex-direction: row; align-items: center; gap: var(--space-3); }
.wk-cell-row > .wk-keyname { flex: none; width: 4.5em; }
.wk-keys, .wk-steps { display: grid; gap: var(--space-2); }
.wk-keys { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.wk-steps { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.wk-sub { display: flex; flex-direction: column; gap: var(--space-1); }
/* PICK A NODE (lead bccbdd601): the box, then the nodes that start with what is typed - in the rail's flow, scrolling
   inside itself past ten rows. */
.wk-search { display: flex; flex-direction: column; gap: var(--space-1); }
.wk-search [hidden] { display: none; }
.wk-searchlist { display: flex; flex-direction: column; max-height: 440px; overflow-y: auto;
  background: var(--bg-surface); border: 1px solid var(--border); }
.wk-searchitem { display: flex; align-items: center; gap: var(--space-2); min-height: var(--wk-h); padding: 0 var(--space-3);
  cursor: pointer; }
.wk-searchitem + .wk-searchitem { border-top: 1px solid var(--border); }
.wk-searchitem:hover { background: color-mix(in srgb, var(--text) 7%, transparent); }
.wk-searchitem.is-active { background: var(--accent-weak); }
.wk-searchkey { min-width: 0; font-family: var(--wk-font); overflow-wrap: anywhere; }
.wk-searchcount { flex: none; margin-left: auto; font-variant-numeric: tabular-nums; color: var(--text-dim); }
/* Collect: the picked types are chips (× takes one out); the rest are behind one + Type dropdown. */
.wk-chips { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.wk-chip, .wk-add { min-height: var(--wk-h); padding: 0 var(--space-4); border-radius: 999px; font: inherit;
  font-size: var(--wk-fs-body); cursor: pointer; }
.wk-chip { color: var(--accent); background: var(--accent-weak); border: 1px solid var(--accent); }
.wk-add { color: var(--text-dim); background: var(--bg-surface); border: 1px dashed var(--border-strong); }
.wk-routes-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); }
.wk-route { display: flex; flex-direction: column; gap: var(--space-2); margin: 0 0 var(--space-2);
  padding: var(--space-2); border: 1px solid var(--border); border-radius: 8px; }
.wk-route.is-on { border-color: var(--accent); background: var(--accent-weak); }

.wk-go { width: 100%; padding: 0 var(--space-4); border: 0; border-radius: 8px;
  background: var(--accent, #2563eb); color: var(--accent-contrast); font-weight: 600; }
.wk-go[disabled] { opacity: 0.45; }

/* The result: its lines, then its sections - on the head's left edge, no box of its own (lead 10-11 W S5). */
.wk-result { display: flex; flex-direction: column; gap: var(--space-2); }
/* Sections spaced by their box, none by its own margin (lead 10-11 W S2). */
.wk-secs { display: flex; flex-direction: column; gap: var(--space-5); }
.wk-counts { font-weight: 600; }
/* 경로 — 누를 수 있는 것이므로 button 이고, 그래서 키보드로도 닿습니다. A control's height, its chain and its hops a
   line each, cut at the row's end with the whole in its title (lead 18da45b73: 53 and 88 px rows); a press puts the
   whole route in the form above. */
/* A route a line, read whole (owner 10-12: a walked way runs five hops) - it wraps in the popover rather than cut. */
.wk-path { display: grid; grid-template-columns: minmax(0, 1fr); width: 100%;
  text-align: left; min-height: var(--wk-h); padding: var(--space-2) var(--space-3); margin: 0; align-content: center;
  border: 0; border-radius: 6px; cursor: pointer;
  background: transparent; color: inherit; font: inherit; }
.wk-path:hover { background: var(--accent-weak); }
.wk-pathchain { min-width: 0; line-height: 1.25; overflow-wrap: anywhere; font-size: var(--wk-fs-body); }
/* A route's self-loops, as chips under its row: off by default (lead 5d5b8d750). */
.wk-loops { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-loopchip { min-height: var(--wk-h); padding: 0 var(--space-4); border-radius: 999px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-surface); color: var(--text-dim, #71717a);
  font: inherit; font-size: var(--wk-fs-line); }
.wk-loopchip.is-on { border-color: var(--accent, #2563eb); color: var(--text, #111); font-weight: 600; }
/* 타입 분포 — 「무엇이 몇 개 왔나」. 물어본 타입은 표시가 다릅니다. */
.wk-dist { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin: var(--space-2) 0; }
.wk-distlabel { font-size: var(--wk-fs-line); color: var(--text-dim, #71717a); }
.wk-distchip { display: inline-flex; gap: var(--space-1); padding: var(--space-1) var(--space-2); border-radius: 999px;
  border: 1px solid var(--border); font-size: var(--wk-fs-line); }
.wk-distchip.is-asked { border-color: var(--accent, #2563eb); font-weight: 600; }
/* 결과 표. 구획마다 «자기 키 컬럼»이라 표가 여럿입니다. */
/* A section stacks its parts - head, Next, + Column, the table - by one gap (lead 348310aee: they touched, 0 px). */
.wk-sec { display: flex; flex-direction: column; gap: var(--space-2); }
/* Who gave a value, under it (lead 99ed68cb7 C, W 11): the node that gave it and its way from its side's starts - a way,
   so the mono face (lead 10-11 W 3). */
.wk-src { font-family: var(--wk-mono); font-size: var(--wk-fs-line); color: var(--text-dim, #71717a); white-space: nowrap; }
/* A section's toolbar, one line (lead 10-11 W): its name · Wide | Long · Table | Trend · Columns · Copy · the rows. One
   height for every press in it: a view chooser segmented, an action a small button (W 2). */
.wk-secbar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-seg { display: inline-flex; border: 1px solid var(--border); }
.wk-segb { height: var(--wk-h-small); padding: 0 var(--space-3); font: inherit; font-size: var(--wk-fs-line); color: var(--text);
  background: var(--bg-surface); border: 0; border-left: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.wk-segb:first-child { border-left: 0; }
.wk-segb.is-on { background: var(--accent); color: var(--accent-contrast); font-weight: 600; }
.wk-segb[disabled] { opacity: 0.45; cursor: not-allowed; }
.wk-act { height: var(--wk-h-small); padding: 0 var(--space-3); font: inherit; font-size: var(--wk-fs-line); color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.wk-act.is-on { border-color: var(--accent); color: var(--accent); }
/* «Reaches only» on is filled, as a segment on is: beside All rows · Differs · Missing it says at a glance what narrows. */
.wk-reachonly.is-on { background: var(--accent); color: var(--accent-contrast); border-color: var(--accent); font-weight: 600; }
.wk-secviews, .wk-copybar, .wk-colmenu { display: inline-flex; align-items: center; gap: var(--space-2); }
.wk-secbar .wk-select { width: auto; max-width: 100%; min-height: var(--wk-h-small); height: var(--wk-h-small); font-size: var(--wk-fs-line); }
/* Long's Value and a trend's column: as wide as a name, not as their longest choice - the toolbar stays one line. */
.wk-secbar .wk-longname, .wk-secbar .wk-trendcol { max-width: 20ch; }
/* Columns · k of n: its list under it (lead 10-11 W, addendum 8: a group a line). */
.wk-colmenu { position: relative; }
.wk-pop { position: absolute; z-index: 3; top: calc(100% + var(--space-1)); left: 0; min-width: 272px; max-height: 360px; overflow: auto;
  display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-2) var(--space-3); background: var(--bg-surface);
  border: 1px solid var(--border-strong); box-shadow: var(--shadow-pop); }
.wk-popacts { display: flex; gap: var(--space-2); }
.wk-popcheck { display: flex; align-items: center; gap: var(--space-2); min-height: var(--wk-h-small); font-size: var(--wk-fs-line);
  white-space: nowrap; }
/* A value, a «+N» tag beside it (lead 10-11 W 4): a row two lines - its value and its source; the tag and the copy icon
   keep their press height inside the value line's cap. */
.wk-valline { display: flex; align-items: center; gap: var(--space-1); max-height: var(--space-5); }
.wk-table td.wk-num .wk-valline { justify-content: flex-end; }
.wk-tag { height: var(--wk-h-small); padding: 0 var(--space-1); font: inherit; font-size: var(--wk-fs-line); color: var(--accent);
  background: none; border: 0; border-radius: 0; cursor: pointer; }
.wk-tag.is-on { font-weight: 600; }
/* A cell's records under its row (lead 10-11 W): the lines Long draws for it. */
.wk-table tr.wk-drawer > td { background: var(--bg-inset); white-space: normal; }
.wk-records { display: grid; grid-template-columns: repeat(auto-fill, minmax(272px, 1fr)); gap: var(--space-1) var(--space-4); }
.wk-recordshead { grid-column: 1 / -1; font-size: var(--wk-fs-line); font-weight: 600; color: var(--text-dim); }
.wk-record { display: flex; flex-direction: column; min-width: 0; }
.wk-record .wk-src { white-space: normal; overflow-wrap: anywhere; }
/* Wide's heads (lead 10-11 W): a group - its step and far end - over its columns, the value's name, each sign and Δ. */
.wk-wide th.wk-stephead { text-align: left; }
.wk-wide th.wk-stephead > span { display: block; max-width: 100%; line-height: 1.25; }
/* Over a fixed-width column the far end reads first and the way under it, each one line cut (owner 10-12 «m..»). */
.wk-headfar, .wk-headvia { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-headvia { color: var(--text-dim); font-size: var(--wk-fs-line); }
.wk-headtext > * + * { margin-top: var(--space-1); }
/* Its «▸ N» a size up from the head's letters: a press among them, not one more word. */
.wk-wide th.wk-stephead > .wk-tag { font-size: var(--wk-fs-body); }
.wk-wide th.wk-sidehead, .wk-wide th.wk-leafhead { text-align: center; }
.wk-long th.wk-plus, .wk-long td.wk-plus { color: var(--wk-plus); }
.wk-long th.wk-minus, .wk-long td.wk-minus { color: var(--wk-minus); }
/* Which walk reached a row (lead 99ed68cb7 D): a stripe at the cell's left and a light ground - A + B green, B alone red;
   A alone none. The three counts above the table say the same. */
.wk-reached { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); font-size: var(--wk-fs-line); }
.wk-reachedside { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-reachedn { padding: 0 var(--space-2); }
.wk-reachedn.is-ctl-ab { box-shadow: inset 3px 0 0 var(--success); background: var(--success-weak); }
.wk-reachedn.is-ctl-b { box-shadow: inset 3px 0 0 var(--danger); background: var(--danger-weak); }
.wk-sechead { font-weight: 700; font-size: var(--wk-fs-title); margin: 0; }
/* The checked rows, one line stuck to the result's foot (W addendum 3): it takes its own room, so it never covers the last row. */
.wk-marked { position: sticky; bottom: 0; z-index: 2; display: flex; flex-direction: column; gap: var(--space-2);
  padding: var(--space-2) var(--space-3); background: var(--bg-surface); border-top: 1px solid var(--border);
  max-height: 88px; overflow-y: auto; }
.wk-markedrow { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-markedword { color: var(--text-dim); font-size: var(--wk-fs-line); line-height: var(--wk-h-small); }
/* The judgment's counts are read, not glanced at (lead 10-12): body size and colour. */
.wk-reachtally { color: var(--text); font-size: var(--wk-fs-body); line-height: var(--wk-h-small); }
.wk-marked .wk-chip { min-height: var(--wk-h-small); padding: 0 var(--space-3); font-size: var(--wk-fs-line); }
.wk-next-edge { height: var(--wk-h-small); padding: 0 var(--space-3); border: 1px solid var(--border); border-radius: 999px;
  background: var(--bg-surface); color: var(--text); font: inherit; font-size: var(--wk-fs-line); cursor: pointer; }
.wk-next-edge:disabled { color: var(--text-dim, #71717a); cursor: not-allowed; }
/* A Walk on's route and its two presses, New step and Add here; the walks merged into a step, each its × (lead 10-11 W
   addendum 5). */
.wk-next-route { display: inline-flex; align-items: center; gap: var(--space-1); margin-right: var(--space-2); }
.wk-next-words { font-size: var(--wk-fs-line); }
.wk-adds { display: flex; flex-wrap: wrap; gap: var(--space-2); font-size: var(--wk-fs-line); }
.wk-addchip { display: inline-flex; align-items: center; gap: var(--space-1); padding: 0 var(--space-2); border-radius: 999px;
  color: var(--accent); background: var(--accent-weak); border: 1px solid var(--accent); }
.wk-trunc > .wk-more { margin-left: var(--space-2); font-family: var(--wk-font); }
/* The steps walked; a press shows that step's table, the shown one lit. */
.wk-steps { display: flex; flex-direction: column; gap: var(--space-2); margin: var(--space-2) 0; }
.wk-steprow { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.wk-step { min-height: var(--wk-h); padding: 0 var(--space-4); font: inherit; font-size: var(--wk-fs-line); color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.wk-step.is-on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.wk-step[aria-current="step"] { background: var(--accent-weak); }
/* A row's check: the rail's follow label rules are label.wk-check - a cell took them (flex, 9.5em) and the table's
   first column stood 124 px wide (lead 34d91c09d review). */
.wk-table th.wk-check, .wk-table td.wk-check { height: var(--wk-h); padding-top: 0; padding-bottom: 0; }
/* A control row and a control start: the board's control look (board.css .is-marked-control). */
.wk-table tr.is-control td { background: var(--bg-inset); }
.wk-table tr.is-control td.wk-check { box-shadow: inset 2px 0 0 var(--text-muted); }
/* Start baskets (lead bc63378e5) in the bar (lead 10-11 W A): + chips vs − chips, each sign and its count first; the adds
   in «+ Add start». */
.wk-basketsign { font-weight: 700; color: var(--wk-plus); }
.wk-basket.is-control .wk-basketsign { color: var(--wk-minus); }
.wk-basketcount { font-variant-numeric: tabular-nums; font-size: var(--wk-fs-line); color: var(--text-dim); }
.wk-vs { color: var(--text-dim); font-size: var(--wk-fs-line); }
.wk-basketrow { display: inline-flex; align-items: center; gap: var(--space-1); height: var(--wk-h-small); box-sizing: border-box;
  padding: 0 var(--space-1) 0 var(--space-3); border-radius: 999px; font-size: var(--wk-fs-line);
  border: 1px solid var(--wk-plus); background: color-mix(in srgb, var(--wk-plus) 10%, var(--bg-surface)); }
.wk-basket.is-control .wk-basketrow { border-color: var(--wk-minus); background: color-mix(in srgb, var(--wk-minus) 10%, var(--bg-surface)); }
.wk-basketlabel { min-width: 0; max-width: 24ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-basketremove { flex: none; height: var(--wk-h-small); padding: 0 var(--space-1); font: inherit; color: var(--text-dim);
  background: none; border: 0; cursor: pointer; }
.wk-adders { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-basketadd { min-height: var(--wk-h-small); padding: 0 var(--space-4); font: inherit; font-size: var(--wk-fs-line); font-weight: 600;
  color: var(--accent); background: var(--bg-surface); border: 1px solid var(--border-strong); border-radius: 999px; cursor: pointer; }
.wk-basketadd[data-sign="+"] { color: var(--wk-plus); border-color: var(--wk-plus); }
.wk-basketadd[data-sign="−"] { color: var(--wk-minus); border-color: var(--wk-minus); }
.wk-basketadd[disabled] { opacity: 0.45; cursor: not-allowed; }
.wk-throughacts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-throughacts > .wk-input { flex: 1 1 8em; width: auto; min-height: var(--wk-h-small); height: var(--wk-h-small); }
/* Fixed columns (owner 10-12): each <col> its width from the answer (main.js fixedColumns) - sorting, filtering, checking
   or scrolling moves none; a cell that does not fit is cut, its whole in its title. width 0: the table is its columns'
   sum, its box scrolls sideways. */
.wk-tablebox { overflow-x: auto; }
.wk-table { table-layout: fixed; width: 0; border-collapse: collapse; font-size: var(--wk-fs-line); white-space: nowrap; }
.wk-table th, .wk-table td { border-bottom: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis;
  padding: var(--space-1) var(--space-2); text-align: left; vertical-align: top; }
.wk-table .wk-val, .wk-table .wk-centrelabel, .wk-table .wk-src { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.wk-table .wk-valline > .wk-tag, .wk-table .wk-valline > .wk-copyid { flex: none; }
/* A value as Copy gives it (owner 10-12: the cell hid spaces Copy had) - its spaces drawn, one line, cut, whole in its title. */
.wk-valline > .wk-val, .wk-valline > .wk-centrelabel, .wk-long td { white-space: pre; }
/* A head's «▾» at its right edge, out of the words' way: a long head is cut, its filter stays. */
.wk-table th.wk-sortable { padding-right: var(--space-6); }
.wk-table th > .wk-colfilter { position: absolute; top: var(--space-1); right: 0; }
.wk-table th { font-weight: 600; font-size: var(--wk-fs-line); color: var(--text-dim, #71717a); position: sticky; top: 0;
  background: var(--bg-surface); }
/* 숫자는 «자릿수»로 섭니다 — x·y 가 세로로 안 맞으면 좌표를 못 읽습니다. */
.wk-table td.wk-num { text-align: right; font-variant-numeric: tabular-nums; }
/* Side by side (lead 3375edd9b): a band per sign above its columns, the − band in the control look; a side that did
   not reach the node says missing in red. */
.wk-table th.wk-sidehead { white-space: normal; overflow-wrap: break-word; }
.wk-table td.wk-missing { color: var(--danger); }
/* A sign a colour (lead 34d91c09d 4): + orange, − teal - a band over its columns, a light tint in its cells, the trend's
   dots - from tokens set in both themes. Solid mixes: the heads stick over the rows. */
.wk-sides, .wk-long, .wk-trend, .wk-bar { --wk-plus: var(--orange); --wk-minus: var(--info); }
.wk-sides th.wk-sidehead.wk-plus { color: var(--wk-plus); background: color-mix(in srgb, var(--wk-plus) 16%, var(--bg-surface));
  box-shadow: inset 0 -3px 0 var(--wk-plus); }
.wk-sides th.wk-sidehead.wk-minus { color: var(--wk-minus); background: color-mix(in srgb, var(--wk-minus) 16%, var(--bg-surface));
  box-shadow: inset 0 -3px 0 var(--wk-minus); }
/* A side that did not reach the node: one cell across its columns (34d91c09d 3). */
.wk-sides td.wk-missing { text-align: center; }
/* The formula's table, two groups (lead 5cf5c3401, the mockup): the node in the centre between its two sides, each side
   tinted its sign's colour, Δ at the right. */
/* The node is the axis (34d91c09d 5): its own ground and weight between the two sides. */
.wk-sides th.wk-centre, .wk-sides td.wk-centre { border-left: 1px solid var(--border-strong); border-right: 1px solid var(--border-strong);
  background: color-mix(in srgb, var(--text) 8%, var(--bg-surface)); color: var(--text); font-weight: 600; }
.wk-sides td.wk-plus { background: color-mix(in srgb, var(--wk-plus) 7%, var(--bg-surface)); }
.wk-sides td.wk-minus { background: color-mix(in srgb, var(--wk-minus) 7%, var(--bg-surface)); }
/* After the sides' bands, so a cell B reached wears the legend's colour, not its side's. */
.wk-table td.is-ctl-ab { box-shadow: inset 3px 0 0 var(--success); background: var(--success-weak); }
.wk-table td.is-ctl-b { box-shadow: inset 3px 0 0 var(--danger); background: var(--danger-weak); }
.wk-sides td.wk-delta { color: var(--text-dim); }
/* Δ beside the node (34d91c09d (나)): a line closes the axis before the − side. */
.wk-sides th.wk-delta, .wk-sides td.wk-delta { border-right: 1px solid var(--border-strong); }
.wk-centrelabel { font-family: var(--wk-font); }
/* The id behind an icon, shown with its row (34d91c09d 5). */
.wk-copyid { height: var(--wk-h-small); width: var(--wk-h-small); display: inline-flex; align-items: center; justify-content: center;
  margin-left: var(--space-2); padding: 0; color: var(--text-dim); vertical-align: middle;
  background: none; border: 0; border-radius: 0; cursor: pointer; opacity: 0; }
.wk-sides tr:hover .wk-copyid, .wk-copyid:focus-visible, .wk-copyid.is-done { opacity: 1; }
.wk-copyid.is-done { color: var(--accent); }
.wk-copyicon { position: relative; display: block; width: 13px; height: 13px; }
.wk-copyicon::before, .wk-copyicon::after { content: ''; position: absolute; width: 8px; height: 8px; border: 1.5px solid currentColor; }
.wk-copyicon::before { left: 0; top: 0; }
.wk-copyicon::after { right: 0; bottom: 0; }
.wk-addcol { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
/* A section's filter seat (lead 10-11 W addendum 7): the search box and All rows · Differs · Missing - one filter - at the
   toolbar's end; a column filter set a chip under it (× takes it off), the one open in the same line. */
.wk-filterseat { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin-left: auto; }
.wk-secbar .wk-find, .wk-filteredit .wk-filterfield { width: 20ch; min-height: var(--wk-h-small); height: var(--wk-h-small);
  font-size: var(--wk-fs-line); }
.wk-filteredit .wk-filterfield[type="number"] { width: 12ch; }
.wk-filters { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-filterchip { height: var(--wk-h-small); padding: 0 var(--space-3); font: inherit; font-size: var(--wk-fs-line); color: var(--accent);
  background: var(--accent-weak); border: 1px solid var(--accent); border-radius: 999px; cursor: pointer; }
.wk-filteredit { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3);
  padding: var(--space-2) var(--space-3); border: 1px solid var(--border); background: var(--bg-surface); }
/* A head sorts when pressed - its arrow its order; its «▾» opens the column's filter, lit while one is set. */
.wk-table th.wk-sortable { cursor: pointer; }
.wk-table th.wk-sortable:hover { color: var(--text); }
.wk-colfilter { margin-left: var(--space-1); padding: 0 var(--space-1); font: inherit; font-size: var(--wk-fs-body); height: var(--wk-h-small); line-height: inherit;
  color: var(--text-dim); background: none; border: 0; border-radius: 0; cursor: pointer; }
.wk-colfilter::after { content: '\\25BE'; }
.wk-table th.is-asc > .wk-colfilter::before { content: '\\2191'; margin-right: var(--space-1); color: var(--accent); }
.wk-table th.is-desc > .wk-colfilter::before { content: '\\2193'; margin-right: var(--space-1); color: var(--accent); }
.wk-colfilter:hover, .wk-colfilter.is-on { color: var(--accent); }
/* Split by (lead 10-11 W addendum 2 ⑭): a series a colour of the category palette. */
.wk-trend-head .wk-trendsplit { width: auto; min-height: var(--wk-h-small); height: var(--wk-h-small); font-size: var(--wk-fs-line); }
.wk-tp.is-s1 { fill: var(--cat-1); } .wk-tp.is-s2 { fill: var(--cat-2); } .wk-tp.is-s3 { fill: var(--cat-3); }
.wk-tp.is-s4 { fill: var(--cat-4); } .wk-tp.is-s5 { fill: var(--cat-5); } .wk-tp.is-s6 { fill: var(--cat-6); }
.wk-tp.is-s7 { fill: var(--cat-7); } .wk-tp.is-s8 { fill: var(--cat-8); } .wk-tp.is-s9 { fill: var(--cat-9); }
/* A value cell opens its column's trend (lead f984ab01d). */
.wk-sides td.wk-pick { cursor: pointer; }
.wk-sides td.wk-pick:hover { outline: 2px solid var(--accent); outline-offset: -2px; }
/* The trend: numbers on a value axis, words in lanes; a colour a group, other rows faint, the walked points ringed. */
.wk-trend { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--border); }
.wk-trend-head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); }
.wk-trend-title { font-family: var(--wk-font); font-weight: 600; overflow-wrap: anywhere; }
.wk-trend-acts { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-left: auto; }
.wk-trend-svg { display: block; width: 100%; height: auto; }
.wk-trend-grid { stroke: var(--border); stroke-width: 1; }
.wk-trend-word { fill: var(--text-dim); font-size: var(--wk-fs-line); font-family: var(--font-mono, ui-monospace, monospace); }
.wk-trend-word.is-others { font-style: italic; }
.wk-trend-t0 { stroke: var(--text); stroke-width: 1; stroke-dasharray: 4 4; }
.wk-tp.is-g0 { fill: var(--wk-plus); }
.wk-tp.is-g1 { fill: var(--wk-minus); }
/* A walked point off the axis, at its edge in its group's colour (lead 10-10). */
.wk-trend-edge { font-size: var(--wk-fs-line); font-family: var(--font-mono, ui-monospace, monospace); fill: var(--text-dim); }
.wk-trend-edge.is-g0 { fill: var(--wk-plus); }
.wk-trend-edge.is-g1 { fill: var(--wk-minus); }
.wk-tp.is-other { fill: var(--text-dim); fill-opacity: 0.35; }
.wk-tp.is-walked { stroke: var(--text); stroke-width: 1.5; }
.wk-trend-legend { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); font-size: var(--wk-fs-line); color: var(--text-dim); }
.wk-trend-key { display: inline-flex; align-items: center; gap: var(--space-1); }
.wk-addcol > .wk-select { width: auto; max-width: 100%; }
/* id 는 길고 «마지막»입니다. 읽는 것이 아니라 «집는» 칸이라 폭을 안 뺏습니다. */
.wk-table td.wk-id { font-family: var(--font-mono, ui-monospace, monospace); font-size: var(--wk-fs-line);
  color: var(--text-dim, #71717a); max-width: 22ch; overflow: hidden; text-overflow: ellipsis; }
.wk-walk, .wk-trunc { font-family: 'JetBrains Mono', monospace; font-size: var(--wk-fs-line); }
.wk-walk { color: var(--text-dim, #71717a); }
.wk-trunc { color: var(--warning); }
/* The continuation's line (owner 10-12): read, so the body's size and colour; its More ▸ beside the words. */
.wk-reachline { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); font-size: var(--wk-fs-body); color: var(--text); }
.wk-fail { color: var(--danger, #dc2626); font-size: var(--wk-fs-body); }
.wk-row { display: flex; gap: var(--space-2); align-items: baseline; padding: var(--space-1) 0;
  border-top: 1px solid var(--border, #d4d4d8); font-size: var(--wk-fs-line); }
.wk-rowtype { flex: none; width: 7.5em; font-family: 'JetBrains Mono', monospace;
  font-size: var(--wk-fs-line); color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-rowlabel { overflow-wrap: anywhere; }

/* Table | Graph — which view of the walk the page shows (lead c9bf53033). */
.wk-views { display: flex; gap: var(--space-2); }
.wk-view { min-height: var(--wk-h); padding: 0 var(--space-4); font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.wk-view.is-on { border-color: var(--accent); color: var(--accent); font-weight: 600; }

/* Subgraph viewer. Corners 0, hairlines, colours from the roles in tokens.css only. A type's colour is a
   palette token (--cat-1..9 in tokens.css, TYPE_COLOURS of them) by its declaration index. A declaration
   with more types than tokens repeats a colour; the legend names them. */
.sg-view { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border); background: var(--bg-surface); color: var(--text); }
/* The graph takes the height the window leaves (owner 10-07, lead d78bf28bd): the result column, the part and its
   picture each grow into what is left. A phone scrolls the page (layout A), so there the result column is the
   screen's height and the picture fills the screen below its bar once scrolled to. */
.wk-graph { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.wk-graph > .sg-view { flex: 1 1 auto; min-height: 0; }
@media (max-width: 760px) {
  .wk-main:has(> .wk-graph) { box-sizing: border-box; height: 100vh; height: 100dvh; }
}
/* Above the picture (owner 10-07, lead d78bf28bd): the picked node's facts beside the lines and the tools, in one row
   of a fixed height - a pick, or a node with more facts, never moves the picture. Each cell scrolls inside itself.
   A phone stacks them: the facts cell keeps its height, the lines take theirs. */
.sg-top { flex: none; display: grid; grid-template-columns: minmax(0, 3fr) minmax(272px, 2fr);
  grid-template-rows: 163.2px; gap: var(--space-3); }
.sg-factslot { position: relative; min-width: 0; border: 1px solid var(--border); background: var(--bg-surface); }
.sg-factslot > .sg-facts { position: absolute; inset: 0; }
.sg-head { display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; min-height: 0; overflow: auto; }
.sg-status { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-1) var(--space-3); }
@media (max-width: 760px) {
  .sg-top { grid-template-columns: minmax(0, 1fr); grid-template-rows: 163.2px auto; }
}
.sg-counts { font-weight: 600; }
.sg-note { font-size: var(--wk-fs-line); color: var(--text-dim); }
.sg-fail { color: var(--danger); }
.sg-trunc { font-family: 'JetBrains Mono', monospace; font-size: var(--wk-fs-line); color: var(--warning); }
.sg-type-0 { --sg-c: var(--cat-1); }
.sg-type-1 { --sg-c: var(--cat-2); }
.sg-type-2 { --sg-c: var(--cat-3); }
.sg-type-3 { --sg-c: var(--cat-4); }
.sg-type-4 { --sg-c: var(--cat-5); }
.sg-type-5 { --sg-c: var(--cat-6); }
.sg-type-6 { --sg-c: var(--cat-7); }
.sg-type-7 { --sg-c: var(--cat-8); }
.sg-type-8 { --sg-c: var(--cat-9); }
.sg-legend { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.sg-chip, .sg-endkey { display: inline-flex; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; font-size: var(--wk-fs-line); }
/* The ring's legend (lead 10-11 G-2 ⑦), dashed as the ring is. */
.sg-endkey { border-style: dashed; border-color: var(--text); }
.sg-swatch { width: 10.2px; height: 10.2px; border-radius: 50%; background: var(--sg-c); }
.sg-swatch.is-static { border-radius: 0; }
/* The picture: Cytoscape draws into the height left (no fixed height); it pans and zooms inside it (lead 5e1d9e372).
   The floor keeps a picture on a very short window; the result column scrolls then. */
.sg-canvas-wrap { position: relative; flex: 1 1 auto; min-height: 240px; border: 1px solid var(--border);
  background: var(--bg-inset); overflow: hidden; }
.sg-canvas-wrap.is-empty { display: none; }
.sg-canvas { position: absolute; inset: 0; }
.sg-acts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.sg-tool { min-height: var(--wk-h); padding: 0 var(--space-4); font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
/* What a lump holds, ticked open (lead 03bc94b6b): beside the lump, inside the picture's box. */
/* The Paths box (lead 55f854fc5, placement 가): at the picture's top right, scrolling inside itself. */
.sg-paths { position: absolute; z-index: 1; top: var(--space-2); right: var(--space-2); width: 340px;
  max-width: calc(100% - var(--space-4)); max-height: calc(100% - var(--space-4)); overflow: auto; display: flex;
  flex-direction: column; gap: var(--space-2); padding: var(--space-3); background: var(--bg-surface);
  border: 1px solid var(--border-strong); box-shadow: var(--shadow-pop); }
.sg-paths[hidden] { display: none; }
.sg-paths-head { font-weight: 600; overflow-wrap: anywhere; }
.sg-paths-edges { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-3); }
.sg-paths-edge { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--wk-h-small);
  font-size: var(--wk-fs-line); }
.sg-paths-kinds { display: flex; flex-direction: column; gap: var(--space-1); }
.sg-paths-kind { display: flex; align-items: center; gap: var(--space-2); min-height: var(--wk-h); padding: var(--space-1) var(--space-3);
  font: inherit; text-align: left; color: var(--text); background: var(--bg-surface); border: 1px solid var(--border);
  border-radius: 0; cursor: pointer; }
.sg-paths-kind.is-on { color: var(--accent); background: var(--accent-weak); border-color: var(--accent); }
.sg-paths-words { min-width: 0; overflow-wrap: anywhere; font-size: var(--wk-fs-line); }
.sg-paths-count { flex: none; margin-left: auto; font-variant-numeric: tabular-nums; color: var(--text-dim); }
.sg-pick { position: absolute; z-index: 2; width: 272px; max-width: calc(100% - var(--space-4)); display: flex;
  flex-direction: column; background: var(--bg-surface); border: 1px solid var(--border-strong);
  box-shadow: var(--shadow-pop); }
.sg-pick-head { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--border); font-weight: 600; }
.sg-pick-sub { font-weight: 400; font-size: var(--wk-fs-line); color: var(--text-dim); }
.sg-pick-filter { margin: var(--space-2) var(--space-3) 0; min-height: var(--wk-h); padding: 0 var(--space-2); font: inherit;
  color: var(--text); background: var(--bg-inset); border: 1px solid var(--border); border-radius: 0; }
.sg-pick-list { max-height: 240px; overflow: auto; padding: var(--space-1) 0; }
.sg-pick-row { display: flex; align-items: center; gap: var(--space-2); min-height: var(--wk-h); padding: 0 var(--space-3);
  cursor: pointer; }
.sg-pick-row[hidden] { display: none; }
.sg-pick-row.is-lit { font-weight: 600; box-shadow: inset 2px 0 0 var(--accent); }
.sg-pick-row:hover { background: color-mix(in srgb, var(--text) 7%, transparent); }
.sg-pick-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sg-pick-n { margin-left: auto; color: var(--text-dim); font-variant-numeric: tabular-nums; }
/* A big lump's window (lead df11f9e81): a branch's nodes under its row, unfolded by its ▸. */
.sg-pick-members { display: flex; flex-direction: column; padding-left: var(--space-5); }
.sg-pick-members[hidden] { display: none; }
.sg-pick-behind { margin-left: auto; color: var(--text-dim); font-size: var(--wk-fs-line); font-variant-numeric: tabular-nums; }
.sg-pick-row.is-loading { opacity: 0.6; }
.sg-pick-view, .sg-pick-unfold { min-height: var(--wk-h-small); padding: 0 var(--space-2); }
.sg-pick-foot { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--border); }
.sg-pick-all { display: inline-flex; align-items: center; gap: var(--space-1); margin-right: auto; color: var(--text-dim); }
.sg-continue { min-height: var(--wk-h); padding: 0 var(--space-4); font: inherit; color: var(--accent-contrast);
  background: var(--accent); border: 1px solid var(--accent); border-radius: 0; cursor: pointer; }
.sg-continue[disabled] { opacity: 0.5; cursor: not-allowed; }
/* The picked node's facts stay in sight (lead 9dc2a5695 ①): in their cell above the picture, with a scroll of
   their own, Mark and Fold first. Nothing picked draws nothing; the cell keeps its place. */
.sg-facts { display: flex; flex-direction: column; gap: var(--space-1); overflow: auto; padding: var(--space-3);
  background: var(--bg-surface); }
.sg-facts:empty { display: none; }
.sg-facts-acts { display: flex; flex-wrap: wrap; gap: var(--space-2); }
/* Mark (into the marking Continue walks) and Fold branches / Unfold (lead 43a738d58 ③) - their own presses. */
.sg-mark, .sg-fold, .sg-walkon { min-height: var(--wk-h); padding: 0 var(--space-4); font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.sg-mark.is-on { color: var(--accent); background: var(--accent-weak); border-color: var(--accent); font-weight: 600; }
.sg-mark[disabled] { opacity: 0.5; cursor: not-allowed; }
.sg-facts-head { font-weight: 600; }
/* A lump in the info box (lead 10-08): what it is, and its one press - the lump as a step of the page's table (10-11). */
.sg-lv-open { min-height: var(--wk-h); padding: 0 var(--space-3); }
.sg-fact { font-family: 'JetBrains Mono', monospace; font-size: var(--wk-fs-line); overflow-wrap: anywhere; }
/* Which world says an edge or an attribute, when the walk reads several (leads 99032248f, ee0f66e7b, 4e1e49fe9):
   one row per world under it, its chip first, then what that world says. */
.sg-fact--world { padding-left: var(--space-4); color: var(--text-muted); }
.sg-world { display: inline-block; margin-right: var(--space-2); padding: 0 var(--space-1); border: 1px solid var(--border);
  font-family: var(--font-sans); font-size: var(--wk-fs-line); color: var(--text); }
`;function u(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${c}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(c,``),t.textContent=l,(e.head||e.documentElement).appendChild(t),!0}function d(e){let t=new Map((e&&e.nodes||[]).map(e=>[e.id,e])),n=new Map,r=new Map;for(let t of e&&e.edges||[])n.has(t.source)||n.set(t.source,[]),n.get(t.source).push(t),r.has(t.target)||r.set(t.target,[]),r.get(t.target).push(t);return{nodes:t,out:n,into:r}}function f(e,t){let n=e&&e.propagation&&e.propagation.ranked;return Array.isArray(n)?t.map((e,t)=>({name:e.name,starts:[...e.starts],inside:new Set([...e.starts,...n.filter(e=>Number((e.reach||[])[t])>0).map(e=>e.id)])})):null}var p=(e,t)=>t===`incoming`?e.source:e.target;function m(e,t,n){let r=e.nodes.get(t.node)||{};if(n.on===`label`)return{value:r.label||t.node,when:t.edge};if(n.on===`key`)return{value:(r.keys||{})[n.name],when:t.edge};if(n.on===`edge`)return{value:t.edge?(t.edge.qualifiers||{})[n.name]:void 0,when:t.edge,image:!!t.edge&&(t.edge.column_types||{})[n.name]===`image`};let i=(r.attributes||{})[n.name],a=((r.attributes_by_world||{})[n.name]||[]).find(e=>e&&h(e.value,i))||null;return{value:i,when:a,image:!!a&&a.column_type===`image`}}var h=(e,t)=>JSON.stringify(e)===JSON.stringify(t),g=e=>e.value.on===`edge`||e.value.on===`node`;function _(e,t,n,r,i=50){let a=v(e,t,n,r,i);return{missing:a.missing,values:a.reads.map(e=>e.value),nodes:a.reads.map(e=>e.giver),more:a.more,images:a.reads.map(e=>!!e.image)}}function v(e,t,r,i,a=50){if(!t.has(r))return{missing:!0,reads:[],more:!1};let{ends:o,more:s}=T(e,t,[r],i.steps,a,i);return{missing:!1,reads:o.map(t=>({...m(e,t,i.value),edge:t.edge,node:t.node,giver:i.value.on===`edge`&&t.edge?t.edge.source:t.node})).filter(e=>!n(e.value)),more:s}}function y(e,t,r){let{on:i,name:a}=t.value,s=i===`edge`?r.edge&&r.edge.records:i===`node`?((e.nodes.get(r.node)||{}).records||{})[a]:null;return!Array.isArray(s)||!s.length?[{...r,point:C(t,r.edge),record:r.edge||r.node}]:s.map(e=>({...r,when:e,record:e.claim_id??e,point:C(t,e),...i===`edge`?{value:(e.qualifiers||{})[a],image:(e.column_types||{})[a]===o}:{value:e.value,image:e.column_type===o}})).filter(e=>!n(e.value))}var b=e=>JSON.stringify([e.steps,e.end||null,e.endTypes||null,e.value]),x=e=>JSON.stringify([e.steps,e.end||null,e.endTypes||null]),S=e=>typeof e==`boolean`?e?`✓`:`✗`:Array.isArray(e)?e.join(` · `):String(e),C=(e,t)=>e.value.on===`edge`&&t?Object.entries(t.qualifiers||{}).filter(([t,r])=>t!==e.value.name&&!n(r)):[],w=e=>e.map(([e,t])=>`${e} ${S(t)}`).join(` · `);function T(e,t,n,r,i,a=null){let o=a&&a.end,s=a&&a.endTypes,c=n.map(e=>({node:e,edge:null})),l=!1;for(let[n,a]of r.entries()){let u=[];for(let d of c){let c=(a.direction===`incoming`?e.into:e.out).get(d.node)||[];for(let d of c){let c=p(d,a.direction);if(!(d.predicate!==a.predicate||t&&!t.has(c))&&!(n===r.length-1&&(o&&c!==o||s&&!s.includes((e.nodes.get(c)||{}).type||``)))){if(u.length>=i){l=!0;break}u.push({node:p(d,a.direction),edge:d})}}}c=u}return{ends:c,more:l}}function E(e,t,n=3,r=60){let i=[],a=[{steps:[],ends:new Set(t)}];for(let t=0;t<n&&i.length<r;t+=1){let t=[];for(let n of a){let a=new Map;for(let t of n.ends)for(let[n,r]of[[`outgoing`,e.out.get(t)],[`incoming`,e.into.get(t)]])for(let e of r||[]){let t=`${e.predicate}\u0000${n}`;a.has(t)||a.set(t,{step:{predicate:e.predicate,direction:n},ends:new Set}),a.get(t).ends.add(p(e,n))}for(let{step:o,ends:s}of[...a.values()].sort((e,t)=>e.step.predicate<t.step.predicate?-1:1)){if(i.length>=r)break;let a={steps:[...n.steps,o],ends:s,words:[...n.words||[],M(o,D(e,s).join(` / `))]};i.push(a),t.push(a)}}a=t}return i.map(({steps:t,words:n,ends:r})=>({steps:t,words:n,to:D(e,r)}))}var D=(e,t)=>[...new Set([...t].map(t=>(e.nodes.get(t)||{}).type).filter(Boolean))].sort();function O(e,t,n){let{ends:r}=T(e,null,t,n,1e3),i={edge:new Set,key:new Set,node:new Set};for(let t of r){for(let e of Object.keys(t.edge&&t.edge.qualifiers||{}))i.edge.add(e);let n=e.nodes.get(t.node)||{};for(let e of Object.keys(n.keys||{}))i.key.add(e);for(let e of Object.keys(n.attributes||{}))i.node.add(e)}return[...[...i.edge].sort().map(e=>({on:`edge`,name:e})),...[...i.key].sort().map(e=>({on:`key`,name:e})),...[...i.node].sort().map(e=>({on:`node`,name:e})),...r.length?[{on:`label`,name:`name`}]:[]]}function k(e){if(typeof e==`number`)return Number.isFinite(e)?e:null;if(typeof e!=`string`||!e.trim())return null;let t=Number(e);return Number.isFinite(t)?t:null}var A=e=>e&&!e.missing&&e.values.length===1?k(e.values[0]):null;function ee(e){let t=new Set(e.filter(e=>!n(e)).map(e=>k(e)===null?typeof e==`boolean`?`boolean`:`string`:`number`));return t.size?t.size===1?[...t][0]:`mixed`:`empty`}function j(e){if(e.length!==2)return null;let[t,n]=e.map(A);return t===null||n===null?null:t-n}var M=(e,t=``)=>`${e.predicate} ${e.direction===`incoming`?`←`:`→`}${t?` ${t}`:``}`;function N(e,t,r=[],i=()=>!1){let a=n=>[...new Set(t.flatMap(t=>Object.keys((e.nodes.get(t)||{})[n]||{})))],o=a(`keys`),s=[...[...r.filter(e=>o.includes(e)),...o.filter(e=>!r.includes(e)).sort()].map(e=>({steps:[],value:{on:`key`,name:e},words:[e]})),...a(`attributes`).sort().map(e=>({steps:[],value:{on:`node`,name:e},words:[e]}))],c=new Map;for(let r of t)for(let[t,a]of[[`outgoing`,e.out.get(r)],[`incoming`,e.into.get(r)]])for(let r of a||[]){let a=Object.keys(r.qualifiers||{}).filter(e=>!n(r.qualifiers[e]));if(!a.length)continue;let o=p(r,t),s=(e.nodes.get(o)||{}).type||``,l=i(s)?o:null,u=`${r.predicate}\u0000${t}\u0000${l===null?`type\u0000${s}`:l}`;c.has(u)||c.set(u,{predicate:r.predicate,direction:t,end:l,type:s,far:l===null?s:(e.nodes.get(o)||{}).label||o,names:new Set});for(let e of a)c.get(u).names.add(e)}let l=(e,t)=>e<t?-1:+(e>t),u=[...c.values()].sort((e,t)=>l(e.predicate,t.predicate)||l(t.direction,e.direction)||l(e.far,t.far));for(let e of u){let t=[{predicate:e.predicate,direction:e.direction}],n=e.end===null?{endTypes:[e.type]}:{end:e.end};for(let r of[...e.names].sort())s.push({steps:t,...n,value:{on:`edge`,name:r},words:[M(e,e.far),r]})}return s}function P(e,t,n,r,i=50){return n.map(n=>{let a=r.map(r=>t.map(t=>_(e,t.inside,n,r,i))),o=(e,t)=>e.missing===t.missing&&(e.missing||h(e.values,t.values)),s=t.map(e=>e.inside.has(n));return{id:n,cells:a,deltas:a.map(j),missing:s.some(e=>!e),differs:s.some(e=>e!==s[0])||a.some(e=>e.some(t=>!o(t,e[0])))}})}var F=`others`,I=1e3,L=e=>{let t=e&&Date.parse(e.occurred_at);return Number.isFinite(t)?t:null},R=(e,t)=>e&&(e.claim_id||e.id)||t;function z(e,t,n,r){return t.flatMap((t,i)=>v(e,t.inside,n,r).reads.map(e=>({t:L(e.when),value:e.value,group:i,walked:!0,key:R(e.edge,`${i}:${e.node}`),node:e.node,giver:e.giver,claim:e.when&&e.when.claim_id||``,point:C(r,e.edge)})))}function B(e,t,n){return t.flatMap(t=>z(e.index,e.groups,t,n).map(e=>({...e,row:t})))}function V(e,t,r,i,a=new Set){return(e&&e.edges||[]).map(e=>{let n=e.source===r?e.target:e.source,o=t.findIndex(e=>e.inside.has(n)),s=R(e,e.id);return{t:L(e),value:(e.qualifiers||{})[i.value.name],group:o>=0?o:null,walked:a.has(s),key:s,node:n,giver:e.source,claim:e.claim_id||``,point:C(i,e)}}).filter(e=>!n(e.value)&&(!i.end||r===i.end||e.node===i.end))}function H(t,r,i){return{head:[`time`,`value`,`side`,`node`,`claim_id`],rows:t.map(t=>[t.t===null||t.t===void 0?``:e(new Date(t.t).toISOString()),n(t.value)?``:S(t.value),t.group===null||t.group===void 0?``:r[t.group]||``,i(t),t.claim||``])}}function U(e,t,n){let r=n.steps.length===1&&n.value.on===`edge`?n.steps[0]:null;if(!r)return null;if(e.length===1)return{id:e[0],predicate:r.predicate,direction:r.direction};let i=[...new Set(t.map(e=>e.node))];return i.length===1?{id:i[0],predicate:r.predicate,direction:r.direction===`incoming`?`outgoing`:`incoming`}:null}function W(e,t){let n=new Set(e.map(e=>e.key));return[...e,...t.filter(e=>!n.has(e.key))]}var G=e=>k(e)!==null;function K(e){let t=e&&e.page&&e.page.window,n=t?[Date.parse(t.from),Date.parse(t.to)]:[];return n.length&&n.every(Number.isFinite)?n:null}function q(e,t){let n=[...(t.windows||[]).flat(),...e.filter(e=>e.walked&&e.group===t.group).map(e=>e.t)],r=n.length?n:e.map(e=>e.t);return r.length?[Math.min(...r),Math.max(...r)]:null}var J=e=>[...new Set(e.flatMap(e=>(e.point||[]).map(([e])=>e)))].sort();function Y(e,t=8,n={}){let r=q(e.filter(e=>e.t!==null),n),i=e.filter(e=>e.t!==null&&e.t>=r[0]&&e.t<=r[1]),a=[];for(let t of e.filter(e=>e.t!==null&&(e.t<r[0]||e.t>r[1]))){let e=t.t<r[0],n=a.find(n=>n.group===t.group&&n.before===e);n?(n.n+=1,(e?t.t>n.t:t.t<n.t)&&(n.t=t.t)):a.push({group:t.group,before:e,t:t.t,n:1})}let o=e=>{let t=(e.point||[]).find(([e])=>e===n.split);return t?S(t[1]):``},s=n.split?[...new Set(i.map(o).filter(Boolean))].sort((e,t)=>e.localeCompare(t,void 0,{numeric:!0})).slice(0,9):null,c=e=>s&&s.includes(o(e))?s.indexOf(o(e)):null,l=i.filter(e=>G(e.value)).map(e=>({...e,value:k(e.value),series:c(e)})),u=i.filter(e=>!G(e.value)).map(e=>({...e,word:S(e.value),series:c(e)})),d=new Map;for(let e of u)d.set(e.word,(d.get(e.word)||0)+1);let f=[...d].sort((e,t)=>t[1]-e[1]||(e[0]<t[0]?-1:1)).map(([e])=>e),p=new Set(f.slice(0,t)),m=l.map(e=>e.value);return{numbers:l,words:u.map(e=>({...e,lane:p.has(e.word)?e.word:F})),lanes:[...f.slice(0,t),...f.length>t?[F]:[]],t:i.length?r:null,v:m.length?[Math.min(...m),Math.max(...m)]:null,untimed:e.filter(e=>e.t===null).length,outside:a,series:s}}function X(e,t,n){let r=e.filter(e=>e.walked&&e.t!==null&&(n===void 0||e.group===n)).map(e=>e.t);if(r.length)return Math.max(...r);let i=Date.parse(t);return Number.isFinite(i)?i:null}var Z=Object.freeze({positive:`Positive`,negative:`Negative`,addStart:`+ Add start`,vs:`vs`,remove:`×`,noPick:`Pick a node first`,noStart:`Add a start to Positive first`,unheld:`0 atoms · not in the ledger`}),Q=class{constructor(e,n={}){this.doc=n.doc||e.ownerDocument,this.markings=n.markings,this.name=n.name,this.picked=n.picked||(()=>null),this.known=new Map,this.root=this._el(`span`,`wk-baskets`),this.list=this._el(`span`,`wk-basketlist`),this.pop=this._el(`details`,`wk-barpop`);let r=this._el(`div`,`wk-barpopbody`);this.adders=this._el(`div`,`wk-adders`),n.pick&&r.append(n.pick),r.append(this.adders);let i=this._el(`summary`,`wk-barchip`,Z.addStart);this.pop.append(i,r),this.root.append(this.list,this.pop),this.place=()=>{this.pop.open&&t(r,i,{align:`left`,gap:3.4})},this.pop.addEventListener&&this.pop.addEventListener(`toggle`,this.place),e.appendChild(this.root),this.unsubscribe=this.markings.subscribe(this.name,()=>this.render()),this.render()}describe(e){return this.known.get(e)||null}add(e,t=this.picked()){t&&(this.known.set(t.id,{label:t.label,type:t.type,keys:{...t.keys||{}}}),this.markings.set(this.name,t.id,e))}remove(e){this.markings.set(this.name,e,s.ABSENT)}_el(e,t,n){let r=this.doc.createElement(e);return t&&(r.className=t),n!==void 0&&(r.textContent=n),r}render(){this.list.textContent=``,this.adders.textContent=``;let e=this.markings.entries(this.name),t=this.picked();for(let[n,r,i]of[[s.CASE,Z.positive,`+`],[s.CONTROL,Z.negative,`−`]]){let o=e.filter(([,e])=>e===n).map(([e])=>e);n===s.CONTROL&&this.list.append(this._el(`span`,`wk-vs`,Z.vs));let c=this._el(`span`,`wk-basket`+(n===s.CONTROL?` is-control`:``));c.setAttribute(`data-sign`,i),c.title=r,c.append(this._el(`span`,`wk-basketsign`,i),this._el(`span`,`wk-basketcount`,String(o.length)));for(let e of o){let t=this.describe(e)||{},n=this._el(`span`,`wk-basketrow`);n.setAttribute(`data-start`,e),n.title=t.type||``,n.append(this._el(`span`,`wk-basketlabel`,t.label||e));let r=this._el(`button`,`wk-basketremove`,Z.remove);r.type=`button`,r.setAttribute(`aria-label`,`Remove ${t.label||e}`),r.addEventListener(`click`,()=>this.remove(e)),n.append(r),c.append(n)}this.list.append(c);let l=this._el(`button`,`wk-basketadd`,`${i} ${r}`);l.type=`button`,l.setAttribute(`data-sign`,i),l.setAttribute(`aria-label`,`Add the picked node to ${r}`),a(l,t?``:Z.noPick),l.addEventListener(`click`,()=>this.add(n)),this.adders.append(l)}t&&t.unheld&&this.adders.append(this._el(`div`,`wk-note wk-unheld`,Z.unheld)),this.place()}},$=Object.freeze({hint:`First letters`,none:e=>`No node starts with ${e} · + Add takes it as typed`,empty:`No node of this type in the ledger`,scanCut:e=>`Not every node read (up to ${e})`,more:e=>`${r(e,`node`)} shown · not all · type more`,failed:e=>`Node list · ${e}`}),te=Object.freeze({insensitive:`First letters · any case`,exact:`First letters · exact case`}),ne=class{constructor(e,t={}){this.doc=t.doc||e.ownerDocument,this.ask=t.ask,this.onType=t.onType||(()=>{}),this.onPick=t.onPick||(()=>{}),this.onAnswer=t.onAnswer||(()=>{}),this.delay=t.delay===void 0?250:t.delay,this.axis=null,this.state=`idle`,this.answer=null,this.asked=``,this.active=-1,this.isOpen=!1,this.seq=0,this.timer=null,this.root=this._el(`div`,`wk-search`),this.cell=this._el(`label`,`wk-cell`),this.name=this._el(`span`,`wk-keyname`),this.input=this._el(`input`,`wk-input`),this.input.type=`text`,this.input.setAttribute(`role`,`combobox`),this.input.setAttribute(`aria-autocomplete`,`list`),this.cell.append(this.name,this.input),this.list=this._el(`div`,`wk-searchlist`),this.list.setAttribute(`role`,`listbox`),this.note=this._el(`div`,`wk-note`),this.root.append(this.cell,this.list,this.note),e.appendChild(this.root),this.input.addEventListener(`input`,()=>{this.onType(this.input.value),this.isOpen=!0,clearTimeout(this.timer),this.timer=setTimeout(()=>{this._ask(this.input.value)},this.delay)});let n=()=>{this.isOpen=!0,this._draw()};this.input.addEventListener(`focus`,n),this.input.addEventListener(`click`,n),this.input.addEventListener(`blur`,()=>{this.isOpen=!1,this._draw()}),this.input.addEventListener(`keydown`,e=>this._key(e)),this._draw()}_el(e,t,n){let r=this.doc.createElement(e);return t&&(r.className=t),n!==void 0&&(r.textContent=n),r}async open(){clearTimeout(this.timer),this.axis=null,this.answer=null,this.asked=``,this.input.value=``,this.state=`loading`,this._draw();let e=await this._ask(``);return e?(this.axis=e.ok&&e.prefixAxis||null,this.state=`ready`,this._draw(),e):null}setText(e){let t=e==null?``:String(e);this.input.value!==t&&(this.input.value=t)}async _ask(e){let t=++this.seq,r=n(e)?``:String(e).trim(),i=await this.ask(r);return t===this.seq?(this.answer=i,this.asked=r,this.active=-1,this._draw(),this.onAnswer(),i):null}holdsNone(e){let t=this.answer,r=n(e)?``:String(e).trim();return!this.axis||!r||r!==this.asked||!t||!t.ok||t.valuesTruncated||t.scanTruncated?!1:!this._nodes().some(e=>String((e.keys||{})[this.axis])===r)}_nodes(){return this.answer&&this.answer.ok&&this.answer.nodes||[]}_pick(e){let t=this._nodes()[e];t&&(this.isOpen=!1,this.active=-1,this._draw(),this.onPick(t))}_key(e){let t=this._nodes().length;if(e.key===`ArrowDown`||e.key===`ArrowUp`){if(!t)return;e.preventDefault(),this.isOpen=!0,this.active=e.key===`ArrowDown`?Math.min(this.active+1,t-1):Math.max(this.active-1,0),this._draw()}else if(e.key===`Enter`){let r=n(this.input.value)?``:String(this.input.value).trim();if(!this.isOpen||!t||r!==this.asked)return;e.preventDefault(),this._pick(this.active>=0?this.active:0)}else e.key===`Escape`&&(this.isOpen=!1,this._draw())}_draw(){let e=this.answer,t=e&&e.ok&&!e.prefixAxis&&e.prefixRefusal;this.cell.hidden=this.state===`loading`||!!t,this.name.textContent=this.axis||``,this.input.placeholder=te[e&&e.prefixCase]||$.hint,this.input.setAttribute(`aria-expanded`,String(this.isOpen&&this._nodes().length>0)),this.list.textContent=``,this.note.textContent=``;let n=``;if(this.state===`loading`)n=i;else if(t)n=t;else if(e&&!e.ok)n=$.failed(e.message);else if(e&&!this._nodes().length&&!this.asked)n=e.scanTruncated?$.scanCut(e.scanned):$.empty;else if(e&&this.isOpen){let t=this._nodes();t.forEach((e,t)=>{let n=this._el(`div`,`wk-searchitem`+(t===this.active?` is-active`:``));n.setAttribute(`role`,`option`),n.setAttribute(`aria-selected`,String(t===this.active)),n.setAttribute(`data-index`,String(t)),n.append(this._el(`span`,`wk-searchkey`,Object.values(e.keys||{}).map(e=>String(e)).join(` · `))),e.count&&n.append(this._el(`span`,`wk-searchcount`,r(e.count,`atom`))),n.addEventListener(`mousedown`,e=>{e.preventDefault(),this._pick(t)}),this.list.append(n)}),t.length?e.valuesTruncated&&(n=$.more(t.length)):n=$.none(this.asked)}this.list.hidden=!this.list.children.length,this.note.textContent=n,this.note.hidden=!n}};export{P as A,k as C,E as D,y as E,u as F,S as M,O as N,g as O,T as P,d as S,v as T,_,I as a,x as b,V as c,J as d,L as f,K as g,X as h,F as i,ee as j,M as k,H as l,z as m,Z as n,W as o,Y as p,Q as r,U as s,ne as t,B as u,b as v,w,f as x,N as y};