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
  background: var(--bg, #fff); border: 1px solid var(--border, #d4d4d8); border-radius: 6px; }
.wk-keyrow { display: flex; align-items: center; gap: 8px; min-height: 44px; }
.wk-keyname { flex: none; width: 8.5em; font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-check { display: flex; align-items: center; gap: 8px; padding: 0 4px; border-radius: 6px;
  font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.wk-check.is-on { background: var(--accent-soft, rgba(37, 99, 235, 0.10)); }
.wk-check input[type="checkbox"] { width: 22px; height: 22px; flex: none; }

.wk-go { width: 100%; border: 0; border-radius: 8px;
  background: var(--accent, #2563eb); color: #fff; font-weight: 600; }
.wk-go[disabled] { opacity: 0.45; }

.wk-result { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px;
  background: var(--bg-panel, transparent); border: 1px solid var(--border, #d4d4d8);
  border-radius: 8px; }
.wk-counts { font-weight: 600; }
/* 경로 — 누를 수 있는 것이므로 button 이고, 그래서 키보드로도 닿습니다. */
.wk-path { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; width: 100%;
  text-align: left; min-height: 44px; padding: 8px 10px; margin: 0 0 6px;
  border: 1px solid var(--line, #e4e4e7); border-radius: 6px; cursor: pointer;
  background: var(--surface, #fff); color: inherit; font: inherit; }
.wk-path:hover { background: var(--accent-soft, rgba(37, 99, 235, 0.10)); }
.wk-pathto { font-weight: 700; grid-row: 1 / span 2; align-self: center; }
.wk-pathchain { font-size: 0.86rem; }
.wk-pathmeta { font-size: 0.78rem; color: var(--text-dim, #71717a); }
/* 타입 분포 — 「무엇이 몇 개 왔나」. 물어본 타입은 표시가 다릅니다. */
.wk-dist { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0; }
.wk-distlabel { font-size: 0.78rem; color: var(--text-dim, #71717a); }
.wk-distchip { display: inline-flex; gap: 4px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--line, #e4e4e7); font-size: 0.82rem; }
.wk-distchip.is-asked { border-color: var(--accent, #2563eb); font-weight: 600; }
/* 결과 표. 구획마다 «자기 키 컬럼»이라 표가 여럿입니다. */
.wk-sec { margin: 10px 0 14px; }
.wk-sechead { font-weight: 700; font-size: 0.86rem; margin: 0 0 4px; }
.wk-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; display: block;
  overflow-x: auto; white-space: nowrap; }
.wk-table th, .wk-table td { border-bottom: 1px solid var(--line, #e4e4e7);
  padding: 5px 8px; text-align: left; }
.wk-table th { font-weight: 600; color: var(--text-dim, #71717a); position: sticky; top: 0;
  background: var(--surface, #fff); }
/* 숫자는 «자릿수»로 섭니다 — x·y 가 세로로 안 맞으면 좌표를 못 읽습니다. */
.wk-table td.wk-num { text-align: right; font-variant-numeric: tabular-nums; }
/* id 는 길고 «마지막»입니다. 읽는 것이 아니라 «집는» 칸이라 폭을 안 뺏습니다. */
.wk-table td.wk-id { font-family: var(--font-mono, ui-monospace, monospace); font-size: 0.74rem;
  color: var(--text-dim, #71717a); max-width: 22ch; overflow: hidden; text-overflow: ellipsis; }
.wk-walk, .wk-trunc { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
.wk-walk { color: var(--text-dim, #71717a); }
.wk-trunc { color: var(--warn, #b45309); }
.wk-fail { color: var(--danger, #dc2626); font-size: 0.86rem; }
.wk-row { display: flex; gap: 8px; align-items: baseline; padding: 3px 0;
  border-top: 1px solid var(--border, #d4d4d8); font-size: 0.82rem; }
.wk-rowtype { flex: none; width: 7.5em; font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem; color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-rowlabel { overflow-wrap: anywhere; }
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
