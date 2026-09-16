// absence_on_refusal — 거절이면 화면이 「없습니다」를 «말하지 않는다». (C-121)
// Run: node client2/tests/absence_on_refusal_harness.mjs
//
// 🔴 이 라운드가 왜 있나. 한 화면에 「요청 실패 (401)」과 「선언 · 0개 · 표시할 정의가
//    없습니다」가 «나란히» 서 있었습니다. 운영자는 둘 중 무엇을 믿습니까. 「거절 + 0 을 같이
//    그리는 것」이 「0 만 그리는 것」보다 나쁩니다 — 후자는 틀렸고, 전자는 «자기모순»입니다.
//
// 🔴 이 하니스가 재는 세 줄 — 모집단의 «모든» 자리에서, 거절일 때:
//       ① 거절을 «이름 댄다»   ② 수를 «안 그린다»   ③ 「없습니다」를 «말하지 않는다»
//    그리고 대조군: «진짜 0» 이면 셋 다 반대여야 합니다. ③ 만 재면 「전부 숨기기」가
//    만점을 받습니다 — 그래서 대조군이 이 파일의 절반입니다.
//
// 🔴 `textContent` 로 재지 않습니다. 그것은 `display:none` 글자도 «그대로» 싣고, 바로 그
//    대리를 성질로 읽어서 제가 지난 라운드에 «틀린 헤드라인»을 올렸습니다. 여기서
//    「화면이 하는 말」은 `display:none` / `visibility:hidden` 을 뺀 «보이는 노드»뿐입니다.
//
// 🔴 종류를 묻는 좌석은 «하나»입니다 — `countWithAbsence({unread})`. 자리마다
//    `if (!state.error)` 를 적는 것이 「문 가르기」이고, 그러면 여섯째가 생기는 날 그 자리만
//    다른 답을 냅니다. 그래서 변이 M2/M4 가 그 «한 좌석»을 겨눕니다.
//
// 주어는 둘이고 «둘 다 import 됩니다» — 잘라쓰기 없음:
//    ontology_explorer_view.js  `renderOntologyExplorer` 를 export 합니다
//    admin.js                   export 가 0 이라 프로브가 «원본 전문 + 접근자»를 붙입니다.
//                               `probe_hooks.mjs` 가 `.css` 를 빈 모듈로 풀어 주므로
//                               이 파일은 오늘 node 가 «import 합니다» (C-95).

import path from 'node:path';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc } from './lib/board_dom.mjs';
import { initialExplorerState } from '../src/ontology_explorer_store.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const ADMIN = path.join(SRC, 'admin.js');
const VIEW = path.join(SRC, 'ontology_explorer_view.js');
const ADMIN_HTML = path.join(HERE, '..', 'admin.html');

// 서버가 실제로 그 화면에 보내는 문장. 이 하니스가 지어낸 낱말이 아닙니다.
const REFUSAL = '요청 실패 (401)';

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

// ── the world both subjects wake up in ────────────────────────────────────────────────
const doc = makeDoc('light');
globalThis.document = doc;
globalThis.window = {
  // 5173 이 아닙니다: 그 포트는 `admin.js` 를 절대 API base 로 바꿉니다.
  location: { port: '', origin: 'http://box', href: 'http://box/admin.html', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
};
globalThis.localStorage = globalThis.window.localStorage;
globalThis.requestAnimationFrame = (fn) => fn();
globalThis.fetch = async () => ({
  ok: false, status: 401, json: async () => null, text: async () => '', clone() { return this; },
});
if (!globalThis.navigator.clipboard) {
  Object.defineProperty(globalThis.navigator, 'clipboard',
                        { value: { writeText: async () => {} }, configurable: true });
}

// ── 「화면이 하는 말」 ──────────────────────────────────────────────────────────────────
// 🔴 이 함수가 이 파일의 계측기입니다. `textContent` 와 «다른 답»을 내는 것이 요점이고,
//    다른 답을 내는 경우가 정확히 `markSectionUnread` 가 만드는 경우입니다.
const visibleText = (node) => {
  if (!node) return '';
  const st = node.style;
  if (st && (st.display === 'none' || st.visibility === 'hidden')) return '';
  return [node._text || '', ...(node.children || []).map(visibleText)]
    .join(' ').replace(/\s+/g, ' ').trim();
};
const walk = (node, out = []) => {
  out.push(node);
  for (const kid of node.children || []) walk(kid, out);
  return out;
};

// ── 주어 하나: 온톨로지 탐색기 ────────────────────────────────────────────────────────
const KINDS = { authorable_kinds: [{ id: 'entity' }, { id: 'predicate' }] };
const draw = (render, over) => {
  const root = doc.createElement('div');
  render(root, { ...initialExplorerState, ...over });
  return root;
};

function explorerSuite(render) {
  const refused = draw(render, { error: REFUSAL });
  const refusedText = visibleText(refused);
  ok(refusedText.includes(REFUSAL), 'A1 거절을 «이름 댄다» (①)');
  ok(refusedText.includes('선언 · —'), 'A2 선언 수는 「—」 — 수를 안 그린다 (②)');
  ok(!refusedText.includes('선언 · 0개'), 'A3 「선언 · 0개」를 안 그린다');
  ok(!refusedText.includes('표시할 정의가 없습니다'), 'A4 작업 영역이 「없다」고 안 한다 (③)');
  ok(refusedText.includes('이 정의를 사용하는 곳 · —'), 'A5 사용처 수도 「—」 (②)');
  ok(!refusedText.includes('이 정의를 사용하는 곳 · 0'), 'A6 사용처를 「0」으로 안 그린다');
  ok(!refusedText.includes('상위 참조가 없습니다'), 'A7 사용처가 「없다」고 안 한다 (③)');
  // 🔴 ③ 을 «성질»로. 문장을 하나씩 세면 일곱째 문장이 생기는 날 그 자리만 빠집니다.
  ok(!refusedText.includes('없습니다'), 'A8 거절된 화면에 「없습니다」가 «한 번도» 안 나온다');

  const refusedSearch = visibleText(draw(render, { error: REFUSAL, query: 'lot' }));
  ok(!refusedSearch.includes('일치하는 정의가 없습니다'),
     'A9 「일치하는 것이 없다」는 «찾아봤다»는 뜻 — 못 읽었으면 안 한다');

  const refusedKinds = draw(render, { error: REFUSAL, authoringSchema: KINDS });
  const noneNodes = walk(refusedKinds).filter((n) => (n._text || '').trim() === 'None defined');
  ok(noneNodes.length === 0,
     `A10 층 목록이 살아 있어도 층마다 「None defined」를 안 한다 (본 수 ${noneNodes.length})`);

  // ── 대조군: «진짜 0». ③ 만 재면 「전부 숨기기」가 만점입니다 ─────────────────────────
  const zero = visibleText(draw(render, {}));
  ok(zero.includes('선언 · 0개'), 'B1 진짜 0 이면 「선언 · 0개」가 나온다');
  ok(zero.includes('표시할 정의가 없습니다'), 'B2 진짜 0 이면 작업 영역이 그렇게 말한다');
  ok(zero.includes('이 정의를 사용하는 곳 · 0'), 'B3 진짜 0 이면 사용처가 「0」이다');
  ok(zero.includes('상위 참조가 없습니다'), 'B4 진짜 0 이면 사용처가 그렇게 말한다');
  ok(!zero.includes(REFUSAL), 'B5 안 거절됐으면 거절 문구가 없다');
  const zeroSearch = visibleText(draw(render, { query: 'lot' }));
  ok(zeroSearch.includes('일치하는 정의가 없습니다'), 'B6 진짜 0 이면 검색이 그렇게 말한다');
  const zeroKinds = draw(render, { authoringSchema: KINDS });
  const zeroNone = walk(zeroKinds).filter((n) => (n._text || '').trim() === 'None defined');
  ok(zeroNone.length === KINDS.authorable_kinds.length,
     `B7 진짜 0 이면 층마다 「None defined」 (${zeroNone.length}/${KINDS.authorable_kinds.length})`);
}

// ── 주어 둘: 어드민 ───────────────────────────────────────────────────────────────────
// 🔴 모집단을 «손으로 적지 않습니다». `admin.html` 이 가진 빈 상태 블록이 모집단이고,
//    아홉째가 생기는 날 이 줄이 빨개집니다. 제가 지난 라운드에 총괄의 「일곱」을 받아
//    적었다가 여덟째(`linkedFailLogs`)를 놓칠 뻔했습니다 — 세지 않은 수는 하한도 아닙니다.
const ADMIN_MARKUP = readFileSync(ADMIN_HTML, 'utf8');
const HTML_EMPTY_IDS = [...ADMIN_MARKUP.matchAll(/id="([a-z0-9-]+-empty)"/g)]
  .map((m) => m[1]).sort();
// 🔴 그리고 그 블록이 «실제로 하는 말»도 마크업에서 읽습니다. 문장을 여기서 지어내면
//    「거절 뒤에 «없습니다»가 안 보인다」가 «제 픽스처에 대한» 참이 됩니다 — 범례가
//    단언을 공허하게 만드는 바로 그 부류입니다. 여덟 중 하나라도 문장을 못 읽으면
//    C4a 가 그것을 먼저 말합니다.
const EMPTY_TEXT = new Map(
  [...ADMIN_MARKUP.matchAll(/id="([a-z0-9-]+-empty)"[\s\S]{0,400}?class="empty-text">([^<]*)</g)]
    .map((m) => [m[1], m[2].trim()]));
// ⚠️ 하나만 뺍니다. 「진단 대상을 아직 안 골랐다」는 «거절»이 아니라 UNPICKED 이고,
//    그 자리에는 못 읽은 것이 없습니다 — 사용자가 아직 안 찍은 것입니다.
const UNPICKED_EMPTY = 'diagnostics-empty';

function adminSuite(probe) {
  const map = probe.SECTION_EMPTY_STATE;
  const markSectionUnread = probe.markSectionUnread;
  const expected = HTML_EMPTY_IDS.filter((id) => id !== UNPICKED_EMPTY);
  ok(typeof markSectionUnread === 'function', 'C0 admin.js 가 import 되고 그 좌석에 닿는다');
  ok(JSON.stringify(Object.values(map || {}).sort()) === JSON.stringify(expected),
     `C1 모집단이 admin.html 과 «같다» (${Object.values(map || {}).length}/${expected.length})`);
  ok((map || {})['enrichment-rule-count'] === 'enrichment-empty',
     'C2 여덟째(enrichment)도 같은 좌석을 지난다 — 토큰이 필요 없다는 것은 못 읽을 일이 없다는 뜻이 아니다');

  // 한 번 읽혀서 「없습니다」가 «뜬 뒤» 다음 갱신이 거절되는 순간을 만듭니다.
  doc.body.children.length = 0;
  const seats = Object.entries(map || {}).map(([countId, emptyId]) => {
    const badge = doc.createElement('span');
    badge.setAttribute('id', countId);
    badge.textContent = '0';
    const block = doc.createElement('div');
    block.setAttribute('id', emptyId);
    block.textContent = EMPTY_TEXT.get(emptyId) || '';
    block.style.display = 'flex';
    doc.body.appendChild(badge);
    doc.body.appendChild(block);
    return { countId, emptyId, badge, block, text: EMPTY_TEXT.get(emptyId) || '' };
  });
  // 짝이 «아닌» 블록 하나. 거두는 것이 자기 짝뿐임을 재는 자리입니다.
  const neighbour = doc.createElement('div');
  neighbour.setAttribute('id', UNPICKED_EMPTY);
  neighbour.style.display = 'flex';
  doc.body.appendChild(neighbour);

  for (const seat of seats) markSectionUnread(seat.countId);

  for (const seat of seats) {
    ok(seat.badge.textContent === '—', `C 수 ${seat.countId} 가 「—」다 (②)`);
    ok(seat.block.style.display === 'none', `C 빈 상태 ${seat.emptyId} 가 «같이» 거둬진다 (③)`);
  }
  ok(neighbour.style.display === 'flex',
     'C3 짝이 아닌 빈 상태는 «안» 거둔다 — 전부 숨기는 것은 고친 것이 아니다');
  // 🔴 성질로. 문장을 하나씩 세면 아홉째 문장이 생기는 날 그 자리만 빠집니다.
  ok(seats.every((s) => s.text),
     `C4a 여덟 블록이 «전부» 자기 문장을 들고 앉았다 — 아니면 아래가 공허하다 `
     + `(${seats.filter((s) => s.text).length}/${seats.length})`);
  const shown = visibleText(doc.body);
  const leaked = seats.filter((s) => s.text && shown.includes(s.text)).map((s) => s.emptyId);
  ok(leaked.length === 0,
     `C4 거절 뒤 화면에 남은 빈 상태 문장 ${leaked.length}건 (${leaked.join(' ') || '없음'})`);
}

// ── 채점 ──────────────────────────────────────────────────────────────────────────────
const loadView = (tag, mutate) => loadWithProbe(VIEW, { tag, mutate });
const loadAdmin = (tag, mutate) => loadWithProbe(ADMIN, {
  tag, mutate, expose: ['markSectionUnread', 'SECTION_EMPTY_STATE'],
});

async function suite(view, admin) {
  const before = { pass, fail };
  explorerSuite(view.module.renderOntologyExplorer);
  adminSuite(admin.probe);
  return { pass: pass - before.pass, fail: fail - before.fail };
}

// 🔴 변이는 «판별식이 되는 입력»입니다. 각각이 «자기가 이름 댄 검사»에 걸려야 합니다 —
//    던져서 빨개지는 것은 잡힌 것이 아니라 «구멍»입니다.
const VIEW_DEFECTS = [
  ['M1 선언 수가 unread 를 안 묻는다 -> A2/A3',
   (s) => s.replace("countWithAbsence({ value: listed.length, unread: state.error || '' })",
                    'countWithAbsence({ value: listed.length })')],
  ['M2 좌석이 「못 읽음」을 무시한다 -> A4/A7/A9/A10',
   (s) => s.replace('  if (!cell.read || Number(count) !== 0) return;',
                    '  if (Number(count) !== 0) return;')],
  ['M3 사용처 수가 unread 를 안 묻는다 -> A5/A6',
   (s) => s.replace("countWithAbsence({ value: state.usedByTotal, unread: state.error || '' })",
                    'countWithAbsence({ value: state.usedByTotal })')],
  ['M4 좌석이 «전부» 숨긴다 -> B2/B4/B6/B7 (대조군이 잡는다)',
   (s) => s.replace('  if (!cell.read || Number(count) !== 0) return;', '  return;')],
  ['M5 검색 자리만 사유를 안 넘긴다 -> A9',
   (s) => s.replace('appendEmptyLine(nav, state.items.length, state.error,',
                    "appendEmptyLine(nav, state.items.length, '',")],
  ['M6 층 자리만 사유를 안 넘긴다 -> A10',
   (s) => s.replace('appendEmptyLine(group, items.length, state.error,',
                    "appendEmptyLine(group, items.length, '',")],
  ['M7 사용처 문장만 사유를 안 넘긴다 -> A7/A8',
   (s) => s.replace('appendEmptyLine(usageList, 0, state.error,',
                    "appendEmptyLine(usageList, 0, '',")],
  ['M8 작업 영역만 사유를 안 넘긴다 -> A4/A8',
   (s) => s.replace('appendEmptyLine(workspace, 0, state.error,',
                    "appendEmptyLine(workspace, 0, '',")],
];
const ADMIN_DEFECTS = [
  ['M9 수만 거두고 「없습니다」는 세워 둔다 -> C 빈 상태/C4',
   (s) => s.replace("  if (el) el.style.display = 'none';", "  if (el) el.style.display = '';")],
  ['M10 여덟째가 목록에서 빠진다 -> C1/C2',
   (s) => s.replace("  'enrichment-rule-count': 'enrichment-empty',\n", '')],
  ['M11 「못 읽음」의 철자가 0 이 된다 -> C 수/C4',
   (s) => s.replace("const UNREAD = '—';", "const UNREAD = '0';")],
];
const VIEW_CONTROLS = [
  ['주석 한 낱말 (뜻이 같다)',
   (s) => s.replace('여섯째가 생기는 날', '일곱째가 생기는 날')],
];
const ADMIN_CONTROLS = [
  ['주석 한 낱말 (뜻이 같다)',
   (s) => s.replace('여덟째가 빠집니다', '아홉째가 빠집니다')],
];

console.log('-- absence_on_refusal (C-121) --------------------------------------');
let tag = 0;
const viewBase = await loadView(`v${tag += 1}`);
const adminBase = await loadAdmin(`a${tag += 1}`);
const base = await suite(viewBase, adminBase);

const caught = [], escaped = [];
let controlsCaught = 0;
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [name, mutate] of VIEW_DEFECTS) {
  quiet = true;
  const delta = await suite(await loadView(`v${tag += 1}`, mutate), adminBase);
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
for (const [name, mutate] of ADMIN_DEFECTS) {
  quiet = true;
  const delta = await suite(viewBase, await loadAdmin(`a${tag += 1}`, mutate));
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of VIEW_CONTROLS) {
  quiet = true;
  const delta = await suite(await loadView(`v${tag += 1}`, mutate), adminBase);
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} view ${name}`);
}
for (const [name, mutate] of ADMIN_CONTROLS) {
  quiet = true;
  const delta = await suite(viewBase, await loadAdmin(`a${tag += 1}`, mutate));
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} admin ${name}`);
}

const DEFECTS = VIEW_DEFECTS.length + ADMIN_DEFECTS.length;
const CONTROLS = VIEW_CONTROLS.length + ADMIN_CONTROLS.length;
const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.pass} passed, ${base.fail} failed; ${caught.length}/${DEFECTS} defects caught, `
  + `${escaped.length} escaped; ${CONTROLS - controlsCaught}/${CONTROLS} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
if (base.fail) console.log('FAILED: ' + failedNames.slice(0, base.fail).join(' | '));
if (base.fail || badScore) process.exitCode = 1;
