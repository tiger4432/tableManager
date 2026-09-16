// disabled_reason — 꺼진 컨트롤은 «자기 자리»에서 왜인지 말한다. (C-120 + C-119 발견 ②)
// Run: node client2/tests/disabled_reason_harness.mjs
//
// 🔴 이 라운드가 왜 있나. 총괄이 메인 그리드를 열어 쟀습니다: 소급 배너의 버튼 둘이 꺼져
//    있는데 `title` 이 «빈 문자열»이었습니다. 바로 옆 버튼 셋은 「뷰 — 읽기 전용」을 답니다.
//    제가 다섯 화면을 훑으니 같은 물음(「왜 못 누르나」)에 답하는 자리가 «넷»이었습니다 —
//    `title` · 옆 문구 · «다른 패널» · «없음». 기준 ④ 그대로입니다.
//
// 🔴 그래서 이 파일의 «주 단언»은 자리마다의 문장이 아니라 «성질»입니다:
//       「이 화면에 꺼진 컨트롤이 있으면, 그 컨트롤이 자기 자리에서 왜인지 말한다」
//    문장을 하나씩 세면 다섯째 컨트롤이 생기는 날 그 자리만 빠집니다 — 그리고 «없음»이
//    제일 고르기 쉽습니다(아무것도 안 적으면 되니까). 성질로 재면 새 컨트롤이 이 안으로
//    «저절로» 들어옵니다.
//
// 🔴 대조군이 절반입니다. 「꺼졌으면 말한다」만 재면 «영원히 켜 두는» 코드가 만점을 받고,
//    「사유가 붙는다」만 재면 켜진 버튼에도 사유가 남는 코드가 만점을 받습니다. 둘 다 잽니다.
//
// 주어 넷, «전부 import» 합니다 — 잘라쓰기 0:
//    disabled_reason.js         좌석 그 자체
//    redo_banner.js             C-120 의 그 배너
//    rnd_board/walk_box_panel.js  「걷기」 — 사유가 «다른 패널»에 있던 자리
//    walk/main.js               「날리기」 — 사유가 «옆 드롭다운»에 간접으로 있던 자리
// ⚠️ `write_guard.js` 는 여기서 안 잽니다 — 그 정본은 «옮긴» 것이고 그 화면의 단언은
//    `grid_view_readonly_harness` 에 있습니다. 두 하니스가 같은 것을 두 방식으로 재면
//    그 둘이 갈라집니다.

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const SEAT = path.join(SRC, 'disabled_reason.js');
const REDO = path.join(SRC, 'redo_banner.js');
const WALKBOX = path.join(SRC, 'rnd_board', 'walk_box_panel.js');
const WALKPAGE = path.join(SRC, 'walk', 'main.js');

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name, saw) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else {
    fail++; failedNames.push(name);
    if (!quiet) console.log(`  BAD  ${name}${saw === undefined ? '' : `  -- ${JSON.stringify(saw)}`}`);
  }
  return !!cond;
}

const doc = makeDoc('light');
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
};
globalThis.requestAnimationFrame = (fn) => fn();

const walk = (node, out = []) => {
  out.push(node);
  for (const kid of node.children || []) walk(kid, out);
  return out;
};
const titleOf = (n) => (n.attrs && n.attrs.title) || '';
/** 🔴 이 술어가 이 파일입니다: «꺼졌는데 말이 없는» 컨트롤. 비어 있어야 합니다. */
const mute = (root) => walk(root).filter((n) => n.disabled === true && !titleOf(n));
/** 그 반대편: «켜졌는데 사유가 남아 있는» 컨트롤. 고친 척이 아니라 고친 것임을 재는 자리. */
const stale = (root) => walk(root).filter((n) => n.disabled === false && titleOf(n)
                                                 && n.dataset && n.dataset.titleWas === '');
const settle = () => new Promise((r) => setTimeout(r, 0));

// ── ① 좌석 그 자체 ────────────────────────────────────────────────────────────────────
function seatSuite(setDisabledReason) {
  const btn = () => {
    const b = doc.createElement('button');
    return b;
  };
  const a = btn();
  setDisabledReason(a, '행을 고르십시오');
  ok(a.disabled === true && titleOf(a) === '행을 고르십시오',
     'S1 사유를 주면 «끄고» 그 자리에 적는다', [a.disabled, titleOf(a)]);
  setDisabledReason(a, '');
  ok(a.disabled === false && titleOf(a) === '',
     'S2 사유가 없으면 «켜고» 자기가 적은 말을 «거둔다»', [a.disabled, titleOf(a)]);

  // 🔴 마크업이 «이미» 자기 말을 달고 있는 버튼이 있습니다(`title="Add Row"`). 덮어쓰기만
  //    하면 다시 켜졌을 때 그 버튼이 말을 «잃습니다» — C-107 이 그래서 기억을 답니다.
  const b = btn();
  b.setAttribute('title', 'Add Row');
  setDisabledReason(b, '뷰 — 읽기 전용');
  ok(titleOf(b) === '뷰 — 읽기 전용', 'S3 원래 말이 있어도 사유가 «먼저» 선다', titleOf(b));
  setDisabledReason(b, '');
  ok(b.disabled === false && titleOf(b) === 'Add Row',
     'S4 켜지면 «원래 말»이 돌아온다', [b.disabled, titleOf(b)]);
  setDisabledReason(b, '뷰 — 읽기 전용');
  setDisabledReason(b, '');
  ok(titleOf(b) === 'Add Row', 'S5 두 번 껐다 켜도 원래 말이 안 닳는다', titleOf(b));

  // ⚠️ 계측기는 자기가 진단하는 것을 죽일 수 없습니다(상설). 없는 것·모자란 스텁에 대고
  //    던지면 그 화면의 단언이 «한 줄도» 안 돕니다.
  let threw = false;
  try { setDisabledReason(null, '왜'); } catch (e) { threw = true; }
  ok(!threw, 'S6 없는 컨트롤에 대고 던지지 않는다');
  threw = false;
  try { setDisabledReason({ dataset: {} }, '왜'); } catch (e) { threw = true; }
  ok(!threw, 'S7 `getAttribute` 가 없는 스텁에도 던지지 않는다');
}

// ── ② 소급 배너 — C-120 그 자체 ──────────────────────────────────────────────────────
const SOURCES = [{ relation: 'dt_log', source: 'dt_log_src', scope_columns: ['lot_id'] }];
const ROW = { row_id: 'r1', data: { lot_id: { value: 'L1' } } };
const readValue = (row, col) => {
  const cell = row && row.data ? row.data[col] : undefined;
  if (cell && typeof cell === 'object' && 'value' in cell) return cell.value;
  return row ? row[col] : undefined;
};
function redoSuite(RedoBanner) {
  const seat = (rows) => {
    const host = doc.createElement('div');
    const part = new RedoBanner(host, {
      doc, sources: SOURCES, getSelection: () => rows, readValue, businessKey: 'lot_id',
      handOff: () => {},
    });
    part.setRelation('dt_log');
    part.render();
    return host;
  };
  const off = seat([]);
  const btns = walk(off).filter((n) => String(n.className || '').includes('redo-banner__btn'));
  ok(btns.length === 2 && btns.every((b) => b.disabled === true),
     'R1 행이 없으면 버튼 둘이 꺼진다', btns.map((b) => b.disabled));
  ok(mute(off).length === 0, 'R2 그리고 «말 없이» 꺼진 컨트롤이 하나도 없다', mute(off).length);
  ok(btns.every((b) => titleOf(b) === '행을 고르십시오'),
     'R3 사유는 「행을 고르십시오」 — 다음 행동 한 줄', btns.map(titleOf));
  const on = seat([ROW]);
  const live = walk(on).filter((n) => String(n.className || '').includes('redo-banner__btn'));
  ok(live.every((b) => b.disabled === false && titleOf(b) === ''),
     'R4 행을 고르면 켜지고 «사유도 사라진다»', live.map((b) => [b.disabled, titleOf(b)]));
  ok(stale(on).length === 0, 'R5 켜진 채 사유가 남은 컨트롤이 없다', stale(on).length);
}

// ── ③ R&D 보드의 「걷기」 — 사유가 «다른 패널»에 있던 자리 ────────────────────────────
const DECL = {
  ok: true,
  entities: [{ type: 'die@1', keys: ['die_id'] }, { type: 'wafer@1', keys: ['wafer_id'] }],
  predicates: [{ name: 'bonded_from', subjects: ['die@1'], objects: ['die@1'] }],
};
/** 같은 선언, 전선이 «응답 본문»으로 받는 모양. `ok` 는 HTTP 쪽 말이라 본문에 없습니다. */
const DECL_BODY = { entities: DECL.entities, predicates: DECL.predicates, collect: [] };
async function walkBoxSuite(WalkBoxPanel) {
  const seat = async (type) => {
    const host = doc.createElement('div');
    const part = new WalkBoxPanel(host, {
      doc, reads: 'marking:1', writes: 'marking:2',
      loadDeclaration: () => Promise.resolve(DECL),
      walk: () => Promise.resolve({ ok: true, nodes: [] }),
    });
    part.mount();
    await settle();
    if (type) { part.setType(type); await settle(); }
    return host;
  };
  const off = await seat(null);
  const go = walk(off).find((n) => String(n.className || '').includes('rb-walkbox-go'));
  ok(Boolean(go) && go.disabled === true, 'W1 타입이 없으면 「걷기」가 꺼진다', go && go.disabled);
  ok(Boolean(go) && titleOf(go) === '시작 타입을 고르십시오',
     'W2 그리고 «자기 자리»에서 무엇이 필요한지 말한다', go && titleOf(go));
  ok(mute(off).length === 0, 'W3 말 없이 꺼진 컨트롤이 하나도 없다',
     mute(off).map((n) => n.className));
  const on = await seat('die@1');
  const live = walk(on).find((n) => String(n.className || '').includes('rb-walkbox-go'));
  ok(Boolean(live) && live.disabled === false && titleOf(live) === '',
     'W4 타입을 고르면 켜지고 사유도 사라진다', live && [live.disabled, titleOf(live)]);
}

// ── ④ 걷기 페이지의 「날리기」 — 사유가 «옆 드롭다운»에 간접으로 있던 자리 ──────────────
async function walkPageSuite(boot) {
  const host = doc.createElement('div');
  // 🔴 선언이 «와야» 폼이 그려집니다. 못 읽은 화면은 실패 줄과 「다시」만 그리고, 그 화면에는
  //    「날리기」가 «없습니다» — 그걸로 재면 이 단언은 공허합니다(처음에 그렇게 썼고, 단언
  //    둘이 조용히 빨개져서 잡았습니다). 무대는 「선언은 읽혔는데 타입을 아직 안 골랐다」입니다.
  boot(doc, host, {
    apiBase: '',
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL_BODY,
                              text: async () => JSON.stringify(DECL_BODY) }),
  });
  await settle();
  await settle();
  const go = walk(host).find((n) => (n.textContent || '') === '날리기');
  ok(Boolean(go) && go.disabled === true, 'K1 타입이 없으면 「날리기」가 꺼진다', go && go.disabled);
  ok(Boolean(go) && titleOf(go) === '노드 타입을 먼저 고르십시오',
     'K2 그리고 «둘 중 어느 것»을 기다리는지 말한다', go && titleOf(go));
  ok(mute(host).length === 0, 'K3 말 없이 꺼진 컨트롤이 하나도 없다',
     mute(host).map((n) => n.className));
}

// ── 채점 ──────────────────────────────────────────────────────────────────────────────
const load = (file, tag, mutate) => loadWithProbe(file, { tag, mutate });

async function suite(seat, redo, box, page) {
  const before = { pass, fail };
  seatSuite(seat.module.setDisabledReason);
  redoSuite(redo.module.RedoBanner);
  await walkBoxSuite(box.module.WalkBoxPanel);
  await walkPageSuite(page.module.boot);
  return { pass: pass - before.pass, fail: fail - before.fail };
}

const SEAT_DEFECTS = [
  ['M1 좌석이 끄기만 하고 «말을 안 한다» -> S1',
   (s) => s.replace("    if (el.setAttribute) el.setAttribute('title', reason);", '')],
  ['M2 좌석이 켜면서 사유를 «안 거둔다» -> S2',
   (s) => s.replace("  } else if (el.removeAttribute) {\n    el.removeAttribute('title');\n  }",
                    '  }')],
  ['M3 좌석이 «원래 말»을 기억하지 않는다 -> S4/S5',
   (s) => s.replace("    el.dataset.titleWas = (el.getAttribute && el.getAttribute('title')) || '';",
                    "    el.dataset.titleWas = '';")],
  ['M4 좌석이 사유가 있어도 «안 끈다» -> S1',
   (s) => s.replace('  el.disabled = Boolean(reason);', '  el.disabled = false;')],
  ['M5 좌석이 없는 컨트롤에 던진다 -> S6',
   (s) => s.replace('  if (!el) return;', '')],
];
const PART_DEFECTS = [
  ['M6 배너가 «말 없이» 끈다 (오늘의 결함 그대로) -> R2/R3', REDO,
   (s) => s.replace("    setDisabledReason(btn, enabled ? '' : NEEDS_A_ROW);",
                    '    btn.disabled = !enabled;')],
  ['M7 배너가 켜진 버튼에도 사유를 남긴다 -> R4', REDO,
   (s) => s.replace("    setDisabledReason(btn, enabled ? '' : NEEDS_A_ROW);",
                    '    setDisabledReason(btn, NEEDS_A_ROW);')],
  ['M8 「걷기」가 말 없이 꺼진다 -> W1/W2', WALKBOX,
   (s) => s.replace("    setDisabledReason(btn, this.nodeType ? '' : PICK_START_TYPE);",
                    "    if (!this.nodeType) btn.setAttribute('disabled', 'disabled');")],
  ['M9 「날리기」가 말 없이 꺼진다 -> K2/K3', WALKPAGE,
   (s) => s.replace("    setDisabledReason(go, state.run === 'running'\n      ? RUNNING\n"
                    + "      : (state.type ? '' : PICK_TYPE_FIRST));",
                    "    go.disabled = !state.type || state.run === 'running';")],
];
const CONTROLS = [
  ['좌석의 주석 한 낱말', SEAT, (s) => s.replace('넷»이었습니다', '다섯»이었습니다')],
  ['배너의 주석 한 낱말', REDO, (s) => s.replace('빈 문자열', '빈 글자')],
];

console.log('-- disabled_reason (C-120 + C-119 finding 2) -----------------------');
let tag = 0;
const nx = () => `d${tag += 1}`;
const seatBase = await load(SEAT, nx());
const redoBase = await load(REDO, nx());
const boxBase = await load(WALKBOX, nx());
const pageBase = await load(WALKPAGE, nx());
const base = await suite(seatBase, redoBase, boxBase, pageBase);

const caught = [], escaped = [];
let controlsCaught = 0;
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [name, mutate] of SEAT_DEFECTS) {
  quiet = true;
  const delta = await suite(await load(SEAT, nx(), mutate), redoBase, boxBase, pageBase);
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
for (const [name, file, mutate] of PART_DEFECTS) {
  quiet = true;
  const hit = await load(file, nx(), mutate);
  const delta = await suite(seatBase,
                            file === REDO ? hit : redoBase,
                            file === WALKBOX ? hit : boxBase,
                            file === WALKPAGE ? hit : pageBase);
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, file, mutate] of CONTROLS) {
  quiet = true;
  const hit = await load(file, nx(), mutate);
  const delta = await suite(file === SEAT ? hit : seatBase,
                            file === REDO ? hit : redoBase,
                            boxBase, pageBase);
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} ${name}`);
}

const DEFECTS = SEAT_DEFECTS.length + PART_DEFECTS.length;
const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.pass} passed, ${base.fail} failed; ${caught.length}/${DEFECTS} defects caught, `
  + `${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
if (base.fail) console.log('FAILED: ' + failedNames.slice(0, base.fail).join(' | '));
if (base.fail || badScore) process.exitCode = 1;
