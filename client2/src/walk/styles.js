// 걷기 폼의 «겉모양». 부품과 «같이» 다닙니다.
//
// 🔴 총괄 판정 2026-09-06: 「스타일은 부품과 같이 다닙니다 — 부품이 자기 것을 «가지고»
//    앉습니다. 정본 하나 · 호스트는 «아무것도 안 챙깁니다».」
//    사유는 기준 ④(같은 기능에 두 경로 없음)입니다: 겉모양을 «호스트의 스타일시트»에
//    걸면 호스트가 하나 늘 때마다 「그 CSS 를 챙겨 넣기」를 «기억»해야 하고, 안 챙기면
//    부품이 «맨몸»으로 뜹니다 — 오류 없이. 실물이 이미 있습니다: `rb-walkbox*` 14개
//    클래스에 대한 규칙이 저장소 전체에 «0» 건이고, 그래서 두 화면이 맨몸입니다.
//
// ⚠️ 그래서 `import './walk.css'` 가 «아닙니다». 모듈 최상단에서 CSS 를 import 하면
//    node 가 그 파일을 못 읽어 «import 문 자체»가 죽고, 그러면 이 모듈을 재는 하니스가
//    파일을 «텍스트로 잘라» 재는 수밖에 없습니다 (소유자 상설: 「잘라쓰기 절대금지」).
//    주입은 `boot()` 안에서 일어나므로 모듈을 그냥 import 하는 것은 DOM 을 안 건드립니다.
//
// ⛔ 테마 협상 · 호스트별 변형 «없습니다». 소유자가 「지금 고려할 필요 없다」고 하셨습니다.
//    색은 `tokens.css` 의 변수를 읽고, 없으면 뒤의 기본값으로 떨어집니다 — 그래서 토큰이
//    없는 호스트에서도 «읽을 수는» 있습니다.

/** 한 문서에 한 번만 넣기 위한 표지. 같은 페이지에 폼이 둘이어도 규칙은 한 벌입니다. */
const STAMP = 'data-wk-styles';

// 🔴 44 는 «손가락»입니다. 이 폼에서 누를 수 있는 것은 전부 이 밑에 걸립니다 —
//    셀렉트 · 입력 · 버튼 · follow 라벨. 재는 것은 «닿는 넓이»이지 글자 크기가 아닙니다.
export const WALK_CSS = `
.wk-form { display: flex; flex-direction: column; gap: 10px;
  font-family: 'Outfit', system-ui, sans-serif; font-size: 15px; color: var(--text, #111); }
.wk-field { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px;
  background: var(--bg-panel, transparent); border: 1px solid var(--border, #d4d4d8);
  border-radius: 8px; }
.wk-label { font-size: 0.72rem; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--text-dim, #71717a); }
.wk-note { font-size: 0.78rem; color: var(--text-dim, #71717a); }

.wk-select, .wk-input, .wk-go, .wk-check { min-height: 44px; box-sizing: border-box;
  font: inherit; }
.wk-select, .wk-input { width: 100%; padding: 0 8px; color: var(--text, #111);
  background: var(--bg-surface); border: 1px solid var(--border, #d4d4d8); border-radius: 6px; }
.wk-keyrow { display: flex; align-items: center; gap: 8px; min-height: 44px; }
.wk-keyname { flex: none; width: 8.5em; font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-check { display: flex; align-items: center; gap: 8px; padding: 0 4px; border-radius: 6px;
  font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.wk-check.is-on { background: var(--accent-weak); }
.wk-check input[type="checkbox"] { width: 22px; height: 22px; flex: none; }
/* 🔴 고르는 목록은 «폭»을 씁니다. 높이 44 는 손가락이라 그대로이고, 한 줄에 하나씩 세우는
   것만 그만둡니다 — 실측(480px 틀): 폼 1,623px 중 1,214px 가 체크박스 23줄이었습니다.
   🔴 칸은 «자기 이름만큼» 자랍니다(flex 0 1 auto) — 고정 폭으로 나누면 긴 이름이 잘리고,
   잘린 이름은 읽을 방법이 없습니다(이 폼에 hover 가 없습니다 — 휴대폰입니다). 최소 9.5em 은
   손가락이 옆 칸을 안 누르게 하는 바닥이고, 화면보다 긴 이름만 마지막 수단으로 잘립니다. */
.wk-checks { display: flex; flex-flow: row wrap; gap: var(--space-1) var(--space-2); }
.wk-check { flex: 0 1 auto; min-width: 9.5em; max-width: 100%; }
.wk-check > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Layout A (lead 2b5819e1d): the form is a rail, the result its own part. The page seats the two;
   each scrolls inside itself, and Walk stays in the rail's foot. */
.wk-rail { display: flex; flex-direction: column; min-height: 0; background: var(--bg-surface);
  border-right: 1px solid var(--border); }
.wk-rail > .wk-form { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: var(--space-4);
  gap: var(--space-5); }
/* In the rail a section is a heading and its controls, not a boxed card (the layout A mockup). */
.wk-rail .wk-field { gap: var(--space-2); padding: 0; background: transparent; border: 0; }
.wk-rail-foot { flex: none; padding: var(--space-3) var(--space-4); border-top: 1px solid var(--border);
  background: var(--bg-surface); }
.wk-main { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; min-height: 0;
  overflow: auto; padding: var(--space-4) var(--space-5); }
.wk-mainhead { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3) var(--space-4); }
.wk-title { font-size: 17px; font-weight: 600; overflow-wrap: anywhere; }
.wk-mainhead > .wk-views { margin-left: auto; }
/* A name above its control: key, step and pick cells. */
.wk-cell { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.wk-cell > .wk-keyname { width: auto; }
.wk-cell-row { flex-direction: row; align-items: center; gap: var(--space-3); }
.wk-cell-row > .wk-keyname { flex: none; width: 4.5em; }
.wk-keys, .wk-steps { display: grid; gap: var(--space-2); }
.wk-keys { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.wk-steps { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.wk-sub { display: flex; flex-direction: column; gap: var(--space-1); }
/* Collect: the picked types are chips (× takes one out); the rest are behind one + Type dropdown. */
.wk-chips { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.wk-chip, .wk-add { min-height: 44px; padding: 0 var(--space-4); border-radius: 999px; font: inherit;
  font-size: 14px; cursor: pointer; }
.wk-chip { color: var(--accent); background: var(--accent-weak); border: 1px solid var(--accent); }
.wk-add { color: var(--text-dim); background: var(--bg-surface); border: 1px dashed var(--border-strong); }
.wk-routes-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); }
.wk-route { display: flex; flex-direction: column; gap: var(--space-2); margin: 0 0 var(--space-2);
  padding: var(--space-2); border: 1px solid var(--border); border-radius: 8px; }
.wk-route.is-on { border-color: var(--accent); background: var(--accent-weak); }

.wk-go { width: 100%; border: 0; border-radius: 8px;
  background: var(--accent, #2563eb); color: var(--accent-contrast); font-weight: 600; }
.wk-go[disabled] { opacity: 0.45; }

.wk-result { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px;
  background: var(--bg-panel, transparent); border: 1px solid var(--border, #d4d4d8);
  border-radius: 8px; }
.wk-counts { font-weight: 600; }
/* 경로 — 누를 수 있는 것이므로 button 이고, 그래서 키보드로도 닿습니다. */
.wk-path { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; width: 100%;
  text-align: left; min-height: 44px; padding: 8px 10px; margin: 0;
  border: 0; border-radius: 6px; cursor: pointer;
  background: transparent; color: inherit; font: inherit; }
.wk-path:hover { background: var(--accent-weak); }
.wk-pathto { font-weight: 700; grid-row: 1 / span 2; align-self: center; }
.wk-pathchain { font-size: 0.86rem; }
.wk-pathmeta { font-size: 0.78rem; color: var(--text-dim, #71717a); }
/* A route's self-loops, as chips under its row: off by default (lead 5d5b8d750). */
.wk-loops { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-loopchip { min-height: 44px; padding: 0 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-surface); color: var(--text-dim, #71717a);
  font: inherit; font-size: 0.82rem; }
.wk-loopchip.is-on { border-color: var(--accent, #2563eb); color: var(--text, #111); font-weight: 600; }
/* 타입 분포 — 「무엇이 몇 개 왔나」. 물어본 타입은 표시가 다릅니다. */
.wk-dist { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0; }
.wk-distlabel { font-size: 0.78rem; color: var(--text-dim, #71717a); }
.wk-distchip { display: inline-flex; gap: 4px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--border); font-size: 0.82rem; }
.wk-distchip.is-asked { border-color: var(--accent, #2563eb); font-weight: 600; }
/* 결과 표. 구획마다 «자기 키 컬럼»이라 표가 여럿입니다. */
.wk-sec { margin: 10px 0 14px; }
.wk-sechead { font-weight: 700; font-size: 0.86rem; margin: 0 0 4px; }
/* A section's Next: the declared edges one step on, walked from its checked rows (lead 53050a4ec). */
.wk-next { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin: 6.8px 0 0; }
.wk-next-edge { min-height: 44px; padding: 0 12px; border: 1px solid var(--border); border-radius: 0;
  background: var(--bg-surface); color: var(--text); font: inherit; font-size: 0.82rem; cursor: pointer; }
.wk-next-edge:disabled { color: var(--text-dim, #71717a); cursor: not-allowed; }
/* The steps walked; a press shows that step's table, the shown one lit. */
.wk-steps { display: flex; flex-wrap: wrap; gap: 6.8px; margin: 6.8px 0; }
.wk-step { min-height: 44px; padding: 0 13.6px; font: inherit; font-size: 0.82rem; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.wk-step.is-on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.wk-table th.wk-check, .wk-table td.wk-check { width: 1%; }
/* A control row and a control start: the board's control look (board.css .is-marked-control). */
.wk-table tr.is-control td { background: var(--bg-inset); }
.wk-table tr.is-control td.wk-check { box-shadow: inset 2px 0 0 var(--text-muted); }
.wk-starts { display: flex; flex-flow: row wrap; align-items: baseline; gap: var(--space-1) var(--space-2); }
.wk-start { font-family: var(--font-mono); }
.wk-start.is-control { color: var(--text-muted); }
.wk-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; display: block;
  overflow-x: auto; white-space: nowrap; }
.wk-table th, .wk-table td { border-bottom: 1px solid var(--border);
  padding: 5px 8px; text-align: left; }
.wk-table th { font-weight: 600; color: var(--text-dim, #71717a); position: sticky; top: 0;
  background: var(--bg-surface); }
/* 숫자는 «자릿수»로 섭니다 — x·y 가 세로로 안 맞으면 좌표를 못 읽습니다. */
.wk-table td.wk-num { text-align: right; font-variant-numeric: tabular-nums; }
/* id 는 길고 «마지막»입니다. 읽는 것이 아니라 «집는» 칸이라 폭을 안 뺏습니다. */
.wk-table td.wk-id { font-family: var(--font-mono, ui-monospace, monospace); font-size: 0.74rem;
  color: var(--text-dim, #71717a); max-width: 22ch; overflow: hidden; text-overflow: ellipsis; }
.wk-walk, .wk-trunc { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
.wk-walk { color: var(--text-dim, #71717a); }
.wk-trunc { color: var(--warning); }
.wk-fail { color: var(--danger, #dc2626); font-size: 0.86rem; }
.wk-row { display: flex; gap: 8px; align-items: baseline; padding: 3px 0;
  border-top: 1px solid var(--border, #d4d4d8); font-size: 0.82rem; }
.wk-rowtype { flex: none; width: 7.5em; font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem; color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-rowlabel { overflow-wrap: anywhere; }

/* Table | Graph | Compare — which view of the walk the page shows (lead c9bf53033, 10-09). */
.wk-views { display: flex; gap: 6.8px; }
.wk-view { min-height: 44px; padding: 0 13.6px; font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.wk-view.is-on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
/* Compare: the walk table's own rules (a row one line, the table scrolls inside itself), so a whose is never cut. */
.cmp-view { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
.cmp-picks { display: flex; flex-flow: row wrap; align-items: flex-end; gap: var(--space-3); }
.cmp-pick { display: flex; flex-direction: column; gap: var(--space-1); flex: 1 1 12em; min-width: 0; }
.cmp-go { flex: none; width: auto; padding: 0 var(--space-5); }
.cmp-heading { font-weight: 600; overflow-wrap: anywhere; }
.wk-table td.cmp-missing { color: var(--danger); }

/* Subgraph viewer. Corners 0, hairlines, colours from the roles in tokens.css only. A type's colour is a
   palette token (--cat-1..9 in tokens.css, TYPE_COLOURS of them) by its declaration index. A declaration
   with more types than tokens repeats a colour; the legend names them. */
.sg-view { display: flex; flex-direction: column; gap: 6.8px; padding: 10.2px 13.6px;
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
.sg-head { display: flex; flex-direction: column; gap: 6.8px; min-width: 0; min-height: 0; overflow: auto; }
.sg-status { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-1) var(--space-3); }
@media (max-width: 760px) {
  .sg-top { grid-template-columns: minmax(0, 1fr); grid-template-rows: 163.2px auto; }
}
.sg-counts { font-weight: 600; }
.sg-note { font-size: var(--fs-meta); color: var(--text-dim); }
.sg-fail { color: var(--danger); }
.sg-trunc { font-family: 'JetBrains Mono', monospace; font-size: var(--fs-meta); color: var(--warning); }
.sg-type-0 { --sg-c: var(--cat-1); }
.sg-type-1 { --sg-c: var(--cat-2); }
.sg-type-2 { --sg-c: var(--cat-3); }
.sg-type-3 { --sg-c: var(--cat-4); }
.sg-type-4 { --sg-c: var(--cat-5); }
.sg-type-5 { --sg-c: var(--cat-6); }
.sg-type-6 { --sg-c: var(--cat-7); }
.sg-type-7 { --sg-c: var(--cat-8); }
.sg-type-8 { --sg-c: var(--cat-9); }
.sg-legend { display: flex; flex-wrap: wrap; gap: 6.8px; }
.sg-chip { display: inline-flex; align-items: center; gap: 6.8px; padding: 3.4px 6.8px;
  border: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; font-size: var(--fs-label); }
.sg-swatch { width: 10.2px; height: 10.2px; border-radius: 50%; background: var(--sg-c); }
.sg-swatch.is-static { border-radius: 0; }
/* The picture: Cytoscape draws into the height left (no fixed height); it pans and zooms inside it (lead 5e1d9e372).
   The floor keeps a picture on a very short window; the result column scrolls then. */
.sg-canvas-wrap { position: relative; flex: 1 1 auto; min-height: 240px; border: 1px solid var(--border);
  background: var(--bg-inset); overflow: hidden; }
.sg-canvas-wrap.is-empty { display: none; }
.sg-canvas { position: absolute; inset: 0; }
.sg-acts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.sg-tool { min-height: 44px; padding: 0 var(--space-4); font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
/* What a lump holds, ticked open (lead 03bc94b6b): beside the lump, inside the picture's box. */
.sg-pick { position: absolute; z-index: 2; width: 272px; max-width: calc(100% - 13.6px); display: flex;
  flex-direction: column; background: var(--bg-surface); border: 1px solid var(--border-strong);
  box-shadow: var(--shadow-pop); }
.sg-pick-head { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--border); font-weight: 600; }
.sg-pick-sub { font-weight: 400; font-size: var(--fs-meta); color: var(--text-dim); }
.sg-pick-filter { margin: var(--space-2) var(--space-3) 0; min-height: 36px; padding: 0 var(--space-2); font: inherit;
  color: var(--text); background: var(--bg-inset); border: 1px solid var(--border); border-radius: 0; }
.sg-pick-list { max-height: 240px; overflow: auto; padding: var(--space-1) 0; }
.sg-pick-row { display: flex; align-items: center; gap: var(--space-2); min-height: 36px; padding: 0 var(--space-3);
  cursor: pointer; }
.sg-pick-row[hidden] { display: none; }
.sg-pick-row.is-lit { font-weight: 600; box-shadow: inset 2px 0 0 var(--accent); }
.sg-pick-row:hover { background: color-mix(in srgb, var(--text) 7%, transparent); }
.sg-pick-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sg-pick-n { margin-left: auto; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.sg-pick-view { min-height: 28px; padding: 0 var(--space-2); }
.sg-pick-foot { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--border); }
.sg-pick-all { display: inline-flex; align-items: center; gap: var(--space-1); margin-right: auto; color: var(--text-dim); }
.sg-continue { min-height: 44px; padding: 0 13.6px; font: inherit; color: var(--accent-contrast);
  background: var(--accent); border: 1px solid var(--accent); border-radius: 0; cursor: pointer; }
.sg-continue[disabled] { opacity: 0.5; cursor: not-allowed; }
/* The picked node's facts stay in sight (lead 9dc2a5695 ①): in their cell above the picture, with a scroll of
   their own, Mark and Fold first. Nothing picked draws nothing; the cell keeps its place. */
.sg-facts { display: flex; flex-direction: column; gap: 3.4px; overflow: auto; padding: var(--space-3);
  background: var(--bg-surface); }
.sg-facts:empty { display: none; }
.sg-facts-acts { display: flex; flex-wrap: wrap; gap: var(--space-2); }
/* Mark (into the marking Continue walks) and Fold branches / Unfold (lead 43a738d58 ③) - their own presses. */
.sg-mark, .sg-fold { min-height: 44px; padding: 0 var(--space-4); font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.sg-mark.is-on { color: var(--accent); background: var(--accent-weak); border-color: var(--accent); font-weight: 600; }
.sg-mark[disabled] { opacity: 0.5; cursor: not-allowed; }
.sg-facts-head { font-weight: 600; }
/* A lump in the info box (lead 10-08): what it is, its switch and its y on one line, its counts, then the table or the
   points. The box keeps its height and scrolls inside itself. */
.sg-lv-kind { min-height: 36px; padding: 0 var(--space-3); }
.sg-lv-kind[aria-pressed="true"] { color: var(--accent); background: var(--accent-weak); border-color: var(--accent);
  font-weight: 600; }
.sg-lv-y { min-height: 36px; padding: 0 var(--space-2); font: inherit; color: var(--text); background: var(--bg-inset);
  border: 1px solid var(--border); border-radius: 0; }
.sg-lv-choice { display: inline-flex; align-items: center; gap: var(--space-2); }
.sg-lv-word { font-size: var(--fs-meta); color: var(--text-dim); }
.sg-lv-meta { font-size: var(--fs-meta); color: var(--text-dim); font-variant-numeric: tabular-nums; }
.sg-lv-plot { display: block; width: 100%; height: 80px; flex: none; }
.sg-fact { font-family: 'JetBrains Mono', monospace; font-size: var(--fs-label); overflow-wrap: anywhere; }
/* Which world says an edge or an attribute, when the walk reads several (leads 99032248f, ee0f66e7b, 4e1e49fe9):
   one row per world under it, its chip first, then what that world says. */
.sg-fact--world { padding-left: var(--space-4); color: var(--text-muted); }
.sg-world { display: inline-block; margin-right: var(--space-2); padding: 0 var(--space-1); border: 1px solid var(--border);
  font-family: var(--font-sans); font-size: var(--fs-tag); color: var(--text); }
`;

/**
 * 규칙을 그 문서에 «한 번» 넣습니다. 이미 있으면 아무것도 하지 않습니다.
 * @param {Document} doc
 * @returns {boolean} 이번 호출이 실제로 넣었나 (둘째 호출은 false)
 */
export function ensureWalkStyles(doc) {
  if (!doc || typeof doc.createElement !== 'function') return false;
  if (doc.querySelector && doc.querySelector(`style[${STAMP}]`)) return false;
  const style = doc.createElement('style');
  style.setAttribute(STAMP, '');
  style.textContent = WALK_CSS;
  (doc.head || doc.documentElement).appendChild(style);
  return true;
}
