// WALK WIRE — 폼의 값이 «전선»에 실제로 실리는가.
//
// 🔴 이 하니스가 재는 것은 «반환»이 아니라 «요청»입니다. 그 구별이 이 파일의 존재 이유입니다:
//    `createWalkBoxWalk` 은 `spec.hops` 를 «받아 놓고» 안 꺼내던 함수입니다. 부르는 쪽은
//    hops 를 실었고(`walk_box_panel.js:230`), 화면은 「경로 A · 3홉」이라 썼고, 전선에는
//    hops 가 «없어서» 서버 기본값 12 가 걸었습니다. 반환만 재는 시험은 그 상태에서
//    «전부 초록»입니다 — 노드가 오긴 오니까요.
//    => 능력은 «요청»에서 확인합니다. 「그 함수가 있나」가 아니라 「무엇이 이 이음매를 지나가나」.
//
// 🔴 그리고 «안 준 것은 안 간다»도 같은 무게로 잽니다. 안 실으면 서버 기본값이 답하고,
//    그것이 「이 값을 안 골랐다」의 정직한 표현입니다. 여기서 기본값을 지어내면 기본값의
//    저자가 둘이 되고, 서버가 그 값을 바꾸는 날 화면만 옛 값을 씁니다.
//
// ⚠️ 잘라쓰기 «아닙니다» — 대상 모듈을 그대로 import 합니다 (`api.js` 는 node 에서 열립니다).
//
// Run: node client2/tests/walk_wire_harness.mjs
import { createWalkBoxWalk, entitySeedId } from '../src/rnd_board/api.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}`); console.log(`        got  ${g}`); console.log(`        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

/** 요청을 «붙잡는» fetch. 이 하니스의 계기입니다. */
function recorder(reply) {
  const seen = [];
  const fetchImpl = async (url) => {
    seen.push(String(url));
    return reply || { ok: true, json: async () => ({ nodes: [], edges: [] }) };
  };
  const params = () => new URL(seen[seen.length - 1], 'http://x').searchParams;
  return { seen, fetchImpl, params };
}

const FULL = {
  type: 'wafer@1', keys: { wafer_id: 'W-1' }, follow: ['inspected@1', 'observed@1'],
  direction: 'outgoing', hops: 3, node_limit: 120,
};
/** 🔴 R&D 보드가 «실제로» 만드는 모양입니다 (`walk_box_panel.js:217-230`). 지어낸 것이 아닙니다. */
const PANEL = { type: 'wafer@1', keys: { wafer_id: 'W-1' }, follow: ['inspected@1'], hops: 3 };

// ═══ ① 계기가 «눈이 멀지» 않았는지 ═══════════════════════════════════════════════════
//
// 🔴 요청을 하나도 못 잡는 계기는 그 아래 단언 전부를 «공허하게 참»으로 만듭니다.
console.log('\n[1] the recorder actually catches a request');
{
  const r = recorder();
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('exactly one request went out', r.seen.length, 1);
  ok('and it went to the walk route', r.seen[0].includes('/api/ledger/subgraph?'), r.seen[0]);
  eq('the call reports success', res.ok, true);
}

// ═══ ② 다섯이 «전선»에 있다 ═══════════════════════════════════════════════════════════
console.log('\n[2] all five arguments reach the wire');
{
  const r = recorder();
  await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  const q = r.params();
  // 씨앗은 «두 칸»(타입 + 키)이 하나의 id 로 접힙니다. 철자를 다시 쓰지 않고 «그 함수»에 묻습니다 —
  // 여기에 base64 를 손으로 적으면 인코딩이 바뀌는 날 이 하니스가 옛 철자를 초록으로 지킵니다.
  eq('seed id is the declared encoding', q.get('id'), entitySeedId(FULL.type, FULL.keys));
  eq('direction is on the wire', q.get('direction'), 'outgoing');
  eq('hops is on the wire', q.get('hops'), '3');
  eq('node_limit is on the wire', q.get('node_limit'), '120');
  // follow 는 «여럿»입니다. `get` 하나만 재면 둘째가 사라져도 초록입니다.
  eq('every follow is on the wire, bare', q.getAll('follow'), ['inspected', 'observed']);
}

// ═══ ③ 🔴 안 준 것은 «안 간다» — 「고르지 않음」과 「0 을 골랐음」은 다릅니다 ══════════
console.log('\n[3] what the caller did not choose does not go');
{
  const r = recorder();
  await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(PANEL);
  const q = r.params();
  eq('direction is absent when unchosen', q.has('direction'), false);
  eq('node_limit is absent when unchosen', q.has('node_limit'), false);
  // 🔴 THE DEFECT THIS FILE WAS WRITTEN FOR: the panel supplies hops and it now travels.
  eq('but the hops the panel DID choose travels', q.get('hops'), '3');
}
{
  const r = recorder();
  await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })({ type: 'wafer@1', keys: {} });
  eq('with nothing chosen, only the seed goes', [...r.params().keys()], ['id']);
}

// ═══ ④ 응답을 «버리지» 않는다 ═════════════════════════════════════════════════════════
//
// ⚠️ 「엣지 0」과 「엣지 칸이 없음」은 다릅니다. 앞은 답이고 뒤는 «모름»입니다.
// 🔴 그리고 `walk` 는 «그 버그를 들킬 수 있는 값»입니다 — 서버가 실제로 몇 홉을 걸었는지가
//    거기 있습니다. 요청과 같은 자리에서 같이 버려지면 어긋남을 볼 방법이 사라집니다.
console.log('\n[4] the response is not thrown away');
{
  const reply = { ok: true, json: async () => ({
    nodes: [{ id: 'n1', type: 'wafer', label: 'W-1', extra: 'narrowed away' }],
    edges: [{ predicate: 'inspected', from: 'n1', to: 'n2', qualifiers: { step: 7 } }],
    truncated: { nodes: 400 },
    walk: { hops_requested: 3, hops_reached: 2 },
  }) };
  const r = recorder(reply);
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('edges come back', res.edges.length, 1);
  // 🔴 엣지의 «모양»을 안 줄인다 — 술어 이름이 사라지면 「무엇을 타고 왔나」가 사라집니다.
  eq('and the predicate survives', res.edges[0].predicate, 'inspected');
  eq('and its qualifiers survive', res.edges[0].qualifiers, { step: 7 });
  eq('nodes are still narrowed to the three the screen draws',
    Object.keys(res.nodes[0]), ['id', 'type', 'label']);
  eq('truncation is carried, not swallowed', res.truncated, { nodes: 400 });
  eq('and the walk block that can catch the hops mismatch survives',
    res.walk, { hops_requested: 3, hops_reached: 2 });
}
{
  const r = recorder({ ok: true, json: async () => ({ nodes: [] }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  // 서버가 그 칸을 «안 보낸» 경우에도 화면이 `.length` 로 죽지 않아야 합니다.
  eq('a response with no edges key yields an empty list, not undefined', res.edges, []);
  eq('and no truncation reads as null, not as a truncation', res.truncated, null);
  eq('and an absent walk block is null, not an invented one', res.walk, null);
}

// ═══ ④-bis 🔴 「잘렸다」는 `truncated` 가 «있다»가 아니라 `reason` 이 «있다»입니다 ══════
//
// 서버는 `truncated` 를 «매번» 보냅니다 — 안 잘렸을 때도 객체가 오고 `reason` 만 null 입니다
// (`ledger_subgraph.py:1244-1249`). 그래서 존재로 읽으면 «모든» 걷기가 「절단됨」이 됩니다.
console.log('\n[4-bis] truncation is a reason, not a key');
{
  const clean = { depth: false, nodes: false, edges: false, claims: false, actions: false,
                  reason: null };
  const r = recorder({ ok: true, json: async () => ({ nodes: [], edges: [], truncated: clean }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('an untruncated walk still carries the block', res.truncated, clean);
  eq('...but is NOT reported as cut', res.cut, false);
}
{
  const cut = { depth: false, nodes: true, edges: false, claims: false, actions: false,
                reason: 'nodes' };
  const r = recorder({ ok: true, json: async () => ({ nodes: [], edges: [], truncated: cut }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('a truncated walk IS reported as cut', res.cut, true);
}

// ═══ ④-ter 「닿은 것이 없다」와 「실패했다」는 다른 답입니다 ══════════════════════════
console.log('\n[4-ter] an empty answer is an answer, not a failure');
{
  const r = recorder({ ok: true, json: async () => ({
    state: 'empty', nodes: [], edges: [],
    message: '선택한 노드에 연결된 원장 증거가 없습니다' }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('the walk succeeded', res.ok, true);
  eq('and it says it is empty', res.state, 'empty');
  // 🔴 사유를 «서버의 말»로 나릅니다. 화면이 자기 문장을 지으면 같은 부재가 두 화면에서
  //    다르게 읽히고, 그때 「없음」과 「못 물어봄」이 같은 픽셀이 됩니다.
  eq('...with the server sentence, not one the screen invented',
    res.message, '선택한 노드에 연결된 원장 증거가 없습니다');
}

// ═══ ⑤ 실패는 «사유»를 들고 온다 — 빈 화면 금지 ═════════════════════════════════════
console.log('\n[5] a refusal carries its reason');
{
  const r = recorder({ ok: false, status: 422,
    json: async () => ({ detail: { message: 'follow 에 없는 술어' } }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('the call is refused', res.ok, false);
  eq('and the server sentence is the one shown', res.message, 'follow 에 없는 술어');
}
{
  // 🔴 실측 422: FastAPI 는 `detail` 을 «배열»로 보냅니다. 읽는 쪽이 `detail.message` 하나만
  //    보던 동안 사유는 «전선에 있고 화면에 없었습니다». 낱말을 여기 적지 않고 «돌면서» 폅니다.
  const r = recorder({ ok: false, status: 422, json: async () => ({ detail: [
    { type: 'less_than_equal', loc: ['query', 'hops'],
      msg: 'Input should be less than or equal to 40', ctx: { le: 40 } }] }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('a validation array is unfolded, not swallowed into a status code',
    res.message, 'hops · Input should be less than or equal to 40');
  ok('...and the status-only fallback is NOT what is shown',
    !/^걷지 못했습니다/.test(res.message), res.message);
}
{
  const r = recorder({ ok: false, status: 422, json: async () => ({ detail: [
    { loc: ['query', 'hops'], msg: 'too big' },
    { loc: ['query', 'node_limit'], msg: 'too small' }] }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  // 둘째가 사라지면 운영자가 한 번 더 거절당합니다. 「첫 사유만」은 사유의 절반입니다.
  eq('every refused field is named, not just the first',
    res.message, 'hops · too big / node_limit · too small');
}
{
  const r = recorder({ ok: false, status: 500, json: async () => { throw new Error('not json'); } });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  ok('a body-less failure still names the status', /500/.test(res.message), res.message);
}
{
  const fetchImpl = async () => { throw new Error('ECONNREFUSED'); };
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl })(FULL);
  eq('a dead server is refused, not thrown', res.ok, false);
  ok('and it says so', /ECONNREFUSED/.test(res.message), res.message);
}
{
  const r = recorder();
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })({ keys: {} });
  eq('no seed type means no request at all', r.seen.length, 0);
  eq('and the caller is told why', res.ok, false);
  ok('...in a sentence, not an empty string', res.message.length > 0, res.message);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
