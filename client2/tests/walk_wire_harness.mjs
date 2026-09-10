// WALK WIRE — 폼의 값이 «전선»에 실제로 실리는가.
//
// 🔴 이 하니스가 재는 것은 «반환»이 아니라 «요청»입니다. 그 구별이 이 파일의 존재 이유입니다:
//    `createWalkBoxWalk` 은 `spec.hops` 를 «받아 놓고» 안 꺼내던 함수입니다. 부르는 쪽은
//    hops 를 실었고(`walk_box_panel.js:238`), 화면은 「경로 A · 3홉」이라 썼고, 전선에는
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
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createWalkBoxWalk, entitySeedId, fetchSubgraph } from '../src/rnd_board/api.js';
import { loadWithProbe } from './lib/probe.mjs';

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
/** 🔴 R&D 보드가 «실제로» 만드는 모양입니다 (`walk_box_panel.js:225-243`). 지어낸 것이 아닙니다. */
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

// ═══ ③-bis C-51 — 구간 «둘», 그리고 빈 칸은 «안 간다» ═══════════════════════════════
//
// 🔴 AN EMPTY DATE BOX IS 「구간 없음」, NOT 「1970」. Sent empty, the server refuses it
//    CORRECTLY (422 `interval_not_iso8601`) and the screen draws 「고장」 over a box the
//    operator simply did not fill. The budget arguments already obey this rule; the
//    interval joins them rather than growing its own.
console.log('\n[3-bis] the interval, and the empty box that is not one');
{
  const r = recorder();
  await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(
    { ...PANEL, since: '2026-09-01', until: '2026-09-08' });
  const q = r.params();
  eq('since is on the wire', q.get('since'), '2026-09-01');
  eq('until is on the wire', q.get('until'), '2026-09-08');
}
{
  // 🔴 ONE END IS A LEGAL QUESTION. `[since, ∞)` is the ordinary 「이후로」, and a screen
  //    that required both would make the common case unaskable.
  const r = recorder();
  await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })({ ...PANEL, since: '2026-09-01' });
  const q = r.params();
  eq('one end alone still travels', q.get('since'), '2026-09-01');
  eq('...and the other stays absent', q.has('until'), false);
}
{
  const r = recorder();
  await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })({ ...PANEL, since: '', until: '' });
  const q = r.params();
  ok('empty boxes send NOTHING — not an empty value',
    !q.has('since') && !q.has('until'), [...q.keys()].join(','));
}
{
  // 🔴 THE SAME RULE ON THE OTHER BUILDER. This route has TWO request builders in this file
  //    (`fetchSubgraph` for the board's seats, `createWalkBoxWalk` for the walk box) and
  //    criterion ④ is 「둘이 갈라질 수 있나」 -- so the seat path is measured too.
  const r = recorder();
  await fetchSubgraph({ apiBase: '', fetchImpl: r.fetchImpl, nodeId: 'ledger-entity:v1:x',
                        since: '2026-09-01', until: '2026-09-08' });
  const q = r.params();
  eq('the seat builder carries since too', q.get('since'), '2026-09-01');
  eq('...and until', q.get('until'), '2026-09-08');
  const r2 = recorder();
  await fetchSubgraph({ apiBase: '', fetchImpl: r2.fetchImpl, nodeId: 'ledger-entity:v1:x',
                        since: '', until: '' });
  ok('...and drops the empty ones, like the other builder',
    !r2.params().has('since') && !r2.params().has('until'));
}

// ═══ ④-ter C-51 — 「안 물었다」와 「물었고 0」 ══════════════════════════════════════
//
// 🔴 THE SERVER KEEPS THESE APART ON PURPOSE (WALK.md 「구간 걷기」): no interval asked ->
//    the key is NOT PRESENT; asked and nothing fell outside -> `0`. Collapsed, the screen
//    tells an operator who asked nothing that nothing was excluded.
console.log('\n[4-ter] the excluded count: absent is not zero');
{
  const walkWith = async (truncated) => {
    const r = recorder({ ok: true, json: async () => ({ nodes: [], edges: [], truncated }) });
    return createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(PANEL);
  };
  eq('a measured zero is a zero', (await walkWith({ interval_excluded: 0 })).intervalExcluded, 0);
  eq('a real count is the count', (await walkWith({ interval_excluded: 37 })).intervalExcluded, 37);
  // 🔴 THE DISCRIMINANT: same shape, key removed. `0` and `null` must not be one pixel.
  eq('no interval asked leaves NO number', (await walkWith({ nodes: true })).intervalExcluded, null);
  eq('...and so does a response with no truncated at all',
    (await walkWith(null)).intervalExcluded, null);
  ok('the two are different values',
    (await walkWith({ interval_excluded: 0 })).intervalExcluded
      !== (await walkWith({ nodes: true })).intervalExcluded);
  eq('a non-numeric value is not read as a count',
    (await walkWith({ interval_excluded: 'lots' })).intervalExcluded, null);
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
    generated_at: '2026-09-07T04:40:00Z',
    limits: { nodes: 400, edges: 2000, max_hops: 12 },
  }) };
  const r = recorder(reply);
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('edges come back', res.edges.length, 1);
  // 🔴 엣지의 «모양»을 안 줄인다 — 술어 이름이 사라지면 「무엇을 타고 왔나」가 사라집니다.
  eq('and the predicate survives', res.edges[0].predicate, 'inspected');
  eq('and its qualifiers survive', res.edges[0].qualifiers, { step: 7 });
  // 🔴 THIS ASSERTION WAS INVERTED ON 2026-09-08, AND IT HAD BEEN HOLDING THE DEFECT IN PLACE.
  //    It read 「nodes carry what the table draws, and nothing more」 and its reason was 「a
  //    field nobody draws is a field nobody has to keep true」 — which sounds right and is
  //    backwards: the client cannot know what nobody draws YET. The narrowing dropped `keys`
  //    and `depth` until 09-06 and `attributes`/`attribute_conflicts` until 09-08, both times
  //    silently, and both times this line went green on the repaired list — one field wider,
  //    same defect, waiting for the next field. C-40 ③: the node rides through WHOLE.
  // ⚠️ The narrowing's own justification is refuted three lines above: `edges` were never
  //    narrowed, for a reason that applies word for word to nodes.
  eq('an unknown field survives, because the client cannot know what nobody draws YET',
    res.nodes[0].extra, 'narrowed away');
  eq('...and the node arrives whole', Object.keys(res.nodes[0]).sort(),
    ['extra', 'id', 'label', 'type']);
  eq('truncation is carried, not swallowed', res.truncated, { nodes: 400 });
  eq('and the walk block that can catch the hops mismatch survives',
    res.walk, { hops_requested: 3, hops_reached: 2 });
  // 🔴 S-13: 「이 답이 «언제» 것인가」. 서버가 줄곧 보냈고 읽는 자리가 «0» 이었습니다
  //    (실측: 소스 0 · 번들 0). 새로 고치지 않은 화면은 오래된 수를 «현재형»으로 말합니다.
  eq('the answer says WHEN it was taken', res.generatedAt, '2026-09-07T04:40:00Z');
  // 🔴 S-13: 「«얼마»에서 잘렸나」. 축 이름만으로는 「많아서」와 「상한이 낮아서」가 같아 보입니다.
  eq('and it carries the budgets it was cut at',
    res.limits, { nodes: 400, edges: 2000, max_hops: 12 });
}
{
  // ⚠️ 없으면 «지어내지» 않습니다 — 옛 서버는 이 칸을 안 보낼 수 있고, 그때 화면은
  //    「기준」 줄을 «안 그립니다». 「지금」으로 채우면 그게 «거짓 기준 시각»입니다.
  const r = recorder({ ok: true, json: async () => ({ nodes: [], edges: [] }) });
  const res = await createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(FULL);
  eq('an older server that omits it yields null, never a made-up now', res.generatedAt, null);
  eq('and an omitted limits block is null, not an invented budget', res.limits, null);
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

// ═══ ⑨ 개명 — 옛 키가 «조용히 지나가지» 않는지 ══════════════════════════════════════
//
// 🔴 `collect` 는 이 클라에서 «LEGACY_ROUTES 표의 행 이름»(라우트 선택자)이었고, 전선이 그
//    낱말을 «원장의 낱말»(도메인 노드 타입)로 가져갑니다. 그래서 클라 쪽 키가 `legacyRoute` 로
//    비켰습니다 — 사라질 쪽이 이름을 내줍니다.
// 🔴 이 절이 재는 것은 «개명»이 아니라 «옛 키의 운명»입니다. 이름만 바꾸면 옛 키는 `...rest` 로
//    흘러 `fetchSubgraph` 의 고정 인자 목록에서 «조용히 버려지고», 옛 방식으로 쓴 좌석이
//    아무 말 없이 «다른 질문»을 묻습니다. 그래서 «거절»이어야 하고, 거절이 실재하는지는
//    「요청이 안 나갔다」로만 증명됩니다 — 요청을 재는 이 하니스가 그 자리인 이유입니다.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const API_PATH = path.join(HERE, '..', 'src', 'rnd_board', 'api.js');
const SEED = { value: entitySeedId('wafer', { wafer: 'W-1' }) };

async function renameSuite(M) {
  const before = failures.length;

  const r1 = recorder();
  let threw = null;
  await M.createWalk({ apiBase: '', fetchImpl: r1.fetchImpl })({ legacyRoute: 'candidate', start: SEED })
    .catch((e) => { threw = e; });
  ok('R1 the new key still reaches the table and asks', r1.seen.length === 1 && !threw,
    `seen=${r1.seen.length} threw=${threw && threw.message}`);

  const r2 = recorder();
  let refusal = null;
  await M.createWalk({ apiBase: '', fetchImpl: r2.fetchImpl })({ collect: 'candidate', start: SEED })
    .then(() => {}, (e) => { refusal = e; });
  ok('R2 the OLD key is refused', Boolean(refusal), 'it resolved instead');
  ok('R3 ... and NOTHING went to the wire', r2.seen.length === 0,
    `${r2.seen.length} request(s) left anyway: ${r2.seen[0] || ''}`);
  ok('R4 ... and the refusal names the key to use instead',
    Boolean(refusal) && /legacyRoute/.test(String(refusal.message)),
    String(refusal && refusal.message));

  return { failed: failures.length - before };
}

console.log('\n[9] the renamed axis, and the fate of the old key');
await renameSuite(await import('../src/rnd_board/api.js'));

// ═══ ⑩ 「잘렸나」 — `depth` 는 «물은 것»일 때 절단이 아닙니다 ═══════════════════════════
//
// 🔴 실측 2026-09-06, 라이브: `depth: true` 는 「홉 상한이 이 걸음을 멈췄다」입니다.
//      hops=2 · 넉넉한 예산  -> 2/2 도달, depth TRUE   (물은 만큼 갔고 더 있다)
//      hops 안 줌(기본 12)   -> 3/12 도달, depth FALSE (그래프가 먼저 끝났다)
//      hops=2 · 좁은 예산    -> 1/2 도달, depth FALSE · nodes TRUE (예산이 잘랐다)
//    그래서 «고른 사람»이 있으면 depth 는 답이고, 서버 기본값이 정했으면 «안 고른 절단»입니다.
//    응답은 그 둘을 구별 못 합니다(`hops_requested: 12` 가 양쪽에서 똑같습니다) -- 요청을
//    «짓는 자리»만 압니다. 그 한 사실을 넘기는 것이 이 절이 재는 것입니다.
// 🔴 왜 이 하니스인가: 이것도 «요청이 결정하는» 값입니다. 반환만 보면 두 경우가 같아 보입니다.
const T = (over) => ({ depth: false, nodes: false, edges: false, claims: false, actions: false,
  reason: null, ...over });
const BODY = (truncated) => ({ ok: true, json: async () => ({ nodes: [], edges: [], truncated }) });

async function cutOf(M, spec, truncated) {
  const r = recorder(BODY(truncated));
  return M.createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(
    { type: 'wafer@1', keys: { wafer: 'W-1' }, ...spec });
}

async function truncationSuite(M) {
  const before = failures.length;

  const asked = await cutOf(M, { hops: 2 }, T({ depth: true, reason: 'depth' }));
  ok('D1 asking for 2 hops and getting 2 is NOT a truncation', asked.cut === false,
    `cut=${asked.cut} axes=${JSON.stringify(asked.truncatedAxes)}`);
  ok('D2 ... and no axis is named, so the screen has nothing to print',
    Array.isArray(asked.truncatedAxes) && asked.truncatedAxes.length === 0,
    JSON.stringify(asked.truncatedAxes));

  // 🔴 반대 팔. 이게 없으면 「언제나 false」를 내는 함수가 D1·D2 를 통과합니다.
  const budget = await cutOf(M, { hops: 2 }, T({ nodes: true, reason: 'nodes' }));
  ok('D3 a real budget cut IS a truncation, even with hops chosen', budget.cut === true,
    `cut=${budget.cut}`);
  ok('D4 ... and it names the axis that was cut, not the reason string',
    JSON.stringify(budget.truncatedAxes) === '["nodes"]', JSON.stringify(budget.truncatedAxes));

  // 🔴 두 번째 반대 팔: 아무도 안 골랐으면 depth 는 «안 고른 절단»입니다.
  const notAsked = await cutOf(M, {}, T({ depth: true, reason: 'depth' }));
  ok('D5 depth IS a truncation when the caller never chose the hop count', notAsked.cut === true,
    `cut=${notAsked.cut}`);

  const clean = await cutOf(M, { hops: 2 }, T({}));
  ok('D6 an untouched walk reports no cut', clean.cut === false, `cut=${clean.cut}`);

  return { failed: failures.length - before };
}

// 🔴 C-51. THE INTERVAL, ON BOTH SIDES OF THE CALL: what goes out, and how the number that
//    comes back is read. Scored against a MUTATED module below, so each of these has to be
//    the assertion that reddens rather than a sentence beside one that does.
async function intervalSuite(M) {
  const before = failures.length;
  const wire = async (spec) => {
    const r = recorder(BODY(T({})));
    await M.createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(
      { type: 'wafer@1', keys: { wafer: 'W-1' }, ...spec });
    return r.params();
  };
  const both = await wire({ since: '2026-09-01', until: '2026-09-08' });
  ok('I1 both ends travel', both.get('since') === '2026-09-01' && both.get('until') === '2026-09-08',
    `${both.get('since')} / ${both.get('until')}`);
  // 🔴 THE OTHER ARM. Without it, a builder that ALWAYS sets both would pass I1.
  const none = await wire({ since: '', until: '' });
  ok('I2 empty boxes are not an interval — nothing goes',
    !none.has('since') && !none.has('until'), [...none.keys()].join(','));

  const excluded = async (truncated) =>
    (await cutOf(M, {}, truncated)).intervalExcluded;
  ok('I3 a measured zero survives as zero', (await excluded(T({ interval_excluded: 0 }))) === 0);
  ok('I4 a real count survives', (await excluded(T({ interval_excluded: 37 }))) === 37);
  // 🔴 THE DISCRIMINANT of this block: absent must NOT become 0, and 0 must not become absent.
  ok('I5 an unasked interval leaves no number at all',
    (await excluded(T({}))) === null, String(await excluded(T({}))));
  // 🔴 `Number(null)` IS 0 AND FINITE, so a value-only check turns 「말 안 함」 into a
  //    measured zero. This is the assertion the re-anchored mutant reddens.
  ok('I6 a null count is 「말 안 함」, not a measured zero',
    (await excluded(T({ interval_excluded: null }))) === null,
    String(await excluded(T({ interval_excluded: null }))));
  return { failed: failures.length - before };
}

// 🔴 C-52. 거절이 «어느 칸의 무슨 값» 때문인지. 모듈 안쪽 함수가 아니라 «부르는 쪽에
//    닿는 문장»으로 잽니다 — 그것이 화면이 읽는 값입니다.
async function refusalSuite(M) {
  const before = failures.length;
  const said = async (status, body) => {
    const r = recorder({ ok: false, status, json: async () => body });
    const got = await M.createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(
      { type: 'wafer@1', keys: { wafer: 'W-1' } });
    return got.message;
  };
  // 🔴 THE TWO THE SERVER ACTUALLY SENDS (S-98), and they must not be one sentence.
  const notIso = await said(422, { detail: { reason: 'interval_not_iso8601',
                                             argument: 'since', value: '2026-13-01' } });
  const empty = await said(422, { detail: { reason: 'interval_empty' } });
  ok('F1 the reason is the server\'s word, untranslated', /interval_not_iso8601/.test(notIso), notIso);
  ok('F2 ...and it says WHICH argument and WHAT value', /since=2026-13-01/.test(notIso), notIso);
  ok('F3 a reason with no argument is just the reason', empty === 'interval_empty', empty);
  // 🔴 THE DISCRIMINANT: before this arm both of these read 「걷지 못했습니다 (422)」.
  ok('F4 the two 422s are DIFFERENT sentences', notIso !== empty, `${notIso} / ${empty}`);

  // ⚠️ 기존 팔 «셋» 무회귀 — 새 팔이 그 앞을 가로채면 오늘 도는 화면의 문장이 바뀝니다.
  ok('F5 a server message still wins',
    (await said(400, { detail: { message: '이 씨앗은 없습니다' } })) === '이 씨앗은 없습니다');
  ok('F6 a FastAPI validation array still reads as before',
    (await said(422, { detail: [{ loc: ['query', 'hops'], msg: 'not an integer' }] }))
      === 'hops · not an integer');
  ok('F7 a bare string detail still reads as before',
    (await said(500, { detail: 'boom' })) === 'boom');
  ok('F8 and a body with nothing usable still falls back to the status',
    (await said(503, {})) === '걷지 못했습니다 (503)');
  return { failed: failures.length - before };
}

// 🔴 C-53. 「생성기가 «하나»인가」 — 성질로 잽니다, 이름으로가 아니라.
//    한 라우트에 URLSearchParams 가 둘이면 인자가 하나 늘 때 «한쪽에만» 실리는 날이 오고,
//    그때 두 화면이 다른 질문을 보내면서 «오류는 안 납니다». 그래서 이 묶음이 재는 것은
//    「걷기 상자가 만든 URL 이 정본 생성기의 URL «과 같은가»」입니다 — 둘째 생성기가
//    돌아오는 순간 빨개지고, 정본에 인자를 더하면 «둘 다» 초록으로 따라옵니다.
async function oneBuilderSuite(M) {
  const before = failures.length;
  const urlOfSpec = async (spec) => {
    const r = recorder();
    await M.createWalkBoxWalk({ apiBase: '', fetchImpl: r.fetchImpl })(spec);
    return r.seen[0];
  };
  const urlOfSeat = async (params) => {
    const r = recorder();
    await M.fetchSubgraph({ apiBase: '', fetchImpl: r.fetchImpl, ...params });
    return r.seen[0];
  };
  const seed = M.entitySeedId('wafer@1', { wafer_id: 'W-1' });

  const boxUrl = await urlOfSpec({ ...PANEL, since: '2026-09-01', collect: ['defect@1'] });
  const seatUrl = await urlOfSeat({ nodeId: seed, follow: ['inspected@1'],
                                    collect: ['defect@1'], hops: 3, since: '2026-09-01' });
  ok('G1 the walk box URL IS the canonical builder\'s URL — no second builder',
    boxUrl === seatUrl, `\n        box  ${boxUrl}\n        seat ${seatUrl}`);

  // 🔴 THE PAYOFF, MEASURED: `collect` and the bare-name rule now live in ONE place, so both
  //    callers carry them. Before C-53 only the walk box stripped `@1`, and a seat that
  //    declared `inspected@1` was answered 422 with 「서버가 거절」 and nothing else.
  ok('G2 the version suffix is stripped for BOTH callers',
    /follow=inspected(&|$)/.test(boxUrl) && /follow=inspected(&|$)/.test(seatUrl),
    `${boxUrl} | ${seatUrl}`);
  ok('G3 ...and so is `collect`, which only one of them used to know',
    /collect=defect(&|$)/.test(boxUrl) && /collect=defect(&|$)/.test(seatUrl));

  // ⚠️ 「0 은 안 싣는다」는 걷기 상자의 «화면 규칙»이고, 좌석은 0 을 «값으로» 보냅니다.
  //    합치면서 한쪽 규칙이 조용히 이기면 그것이 「축과 값을 같이 죽이는」 자리입니다.
  const zeros = await urlOfSpec({ type: 'wafer@1', keys: { wafer_id: 'W-1' }, hops: 0, node_limit: 0 });
  ok('G4 the panel still drops its zeros', !/hops=0/.test(zeros) && !/node_limit=0/.test(zeros), zeros);
  const seatZero = await urlOfSeat({ nodeId: seed, hops: 0 });
  ok('G5 ...while the seat still sends one, because there they mean different things',
    /hops=0/.test(seatZero), seatZero);
  return { failed: failures.length - before };
}

console.log('\n[10] what counts as a truncation');
await truncationSuite(await import('../src/rnd_board/api.js'));
console.log('\n[10-bis] the interval, out and back');
await intervalSuite(await import('../src/rnd_board/api.js'));
console.log('\n[10-ter] a refusal says which argument and what value');
await refusalSuite(await import('../src/rnd_board/api.js'));
console.log('\n[10-quater] one route, one request builder');
await oneBuilderSuite(await import('../src/rnd_board/api.js'));

const base = { pass, failed: failures.length };

const RENAME_DEFECTS = [
  ['the refusal is deleted, so the old key is silently forwarded',
    (src) => src.replace(/ {4}if \(rest\.collect !== undefined\) \{[\s\S]*?\n {4}\}\n/, '')],
];
// Gate 3 of the 23:05 ruling: splitting the judgement apart again must turn D1 red.
const TRUNCATION_DEFECTS = [
  ['depth counts as a cut again, so a satisfied question reads as truncated',
    (src) => src.replace("    .filter((key) => raw[key] === true && !(key === 'depth' && hopsChosen));",
      '    .filter((key) => raw[key] === true);')],
  ['the caller stops passing what it knows, so the judgement loses its one input',
    (src) => src.replace(
      '  const hopsChosen = !!(options && options.hopsChosen);', '  const hopsChosen = false;')],
  ['the cut goes back to reading the reason string',
    (src) => src.replace('        cut: !!(cutAxes && cutAxes.length),',
      '        cut: !!(truncated && truncated.reason),')],
  ['nothing is ever a cut, which would satisfy the first two assertions alone',
    (src) => src.replace("    .filter((key) => raw[key] === true && !(key === 'depth' && hopsChosen));",
      '    .filter(() => false);')],
];
// C-51. 🔴 THE INTERVAL'S FOUR WAYS TO GO WRONG, and each is a live shape rather than a
//    typo: an empty box that travels (the server then refuses a question nobody asked), an
//    end that is silently dropped, an absent count read as zero, and a zero read as absent.
const INTERVAL_DEFECTS = [
  ['an empty date box travels, so the server refuses a question nobody asked',
  // 🔴 C-53 RE-ANCHORED, AND THE MOVE IS THE POINT: these used to have a twin inside
  //    `createWalkBoxWalk` and the anchors had to name one of TWO places. There is one now,
  //    so one mutation reaches both callers — which is the property C-53 bought.
    (src) => src.replace("  if (since) query.set('since', String(since));\n"
      + "  if (until) query.set('until', String(until));",
    "  if (since !== undefined) query.set('since', String(since));\n"
      + "  if (until !== undefined) query.set('until', String(until));")],
  ['one end is dropped, so [since, until) silently becomes [since, ∞)',
    (src) => src.replace("  if (until) query.set('until', String(until));", '')],
  // 🔴 RE-ANCHORED. The first version of this mutant deleted a `hasOwnProperty` guard and
  //    ESCAPED — an absent key is `undefined`, which the number check already rejects, so
  //    the guard changed no answer and was dead code. Chasing it with a vacuous assertion
  //    would have been the wrong repair; the SOURCE lost the dead line, and the mutant now
  //    aims at the live decider. What that decider actually prevents is `Number(null) === 0`
  //    quietly promoting 「말 안 함」 to 「물었고 제외 없음」.
  ['the value is read by coercion, so a null count becomes a measured zero',
    (src) => src.replace("  return typeof n === 'number' && Number.isFinite(n) ? n : null;",
      '  return Number.isFinite(Number(n)) ? Number(n) : null;')],
  ['a measured zero becomes absent, so 「제외 없음」 stops being said at all',
    (src) => src.replace("  return typeof n === 'number' && Number.isFinite(n) ? n : null;",
      "  return typeof n === 'number' && Number.isFinite(n) && n !== 0 ? n : null;")],
];
// C-52. 🔴 세 가지 잃는 방식: 팔이 통째로 없어지거나, 사유만 남고 «자리»가 사라지거나,
//    새 팔이 «기존 팔 앞»을 가로채 오늘 도는 문장을 바꾸거나.
const REFUSAL_DEFECTS = [
  ['the named arm goes away, so the two 422s collapse into one sentence again',
    (src) => src.replace(/ {2}if \(detail && typeof detail === 'object' && !Array\.isArray\(detail\)\n[\s\S]*?\n {2}\}\n/, '')],
  ['the reason survives but the address does not, so 「어느 칸」 is lost',
    (src) => src.replace("    return where ? `${detail.reason} · ${where}` : String(detail.reason);",
      '    return String(detail.reason);')],
  ['the new arm jumps the queue, so a server message stops winning',
    (src) => src.replace("  if (detail && typeof detail.message === 'string') return detail.message;\n",
      '')],
];
// C-53. 🔴 「생성기가 하나」가 «성질»로 서 있는지: 정본에서 규칙을 빼면 «두 호출자»가
//    같이 빨개져야 합니다. 한쪽만 빨개지면 그때 생성기가 둘로 돌아온 것입니다.
const ONE_BUILDER_DEFECTS = [
  ['the canonical builder forgets `collect`, and BOTH callers must lose it together',
    (src) => src.replace(
      "  for (const t of Array.isArray(collect) ? collect : []) query.append('collect', String(t).split('@')[0]);",
      '')],
  ['the bare-name rule is dropped, so a declared `inspected@1` reaches the route as-is',
    (src) => src.replace(
      "  for (const p of Array.isArray(follow) ? follow : []) query.append('follow', String(p).split('@')[0]);",
      "  for (const p of Array.isArray(follow) ? follow : []) query.append('follow', p);")],
  // 🔴 「걷기 상자가 자기 질문을 다시 짓는다」의 대역: 정본을 지나되 «자기만» 인자를 하나
  //    더 실어 보냅니다. 그 순간 두 URL 이 갈라지고, 그것이 둘째 생성기가 하는 일 그대로입니다.
  ['the walk box adds an argument of its own, so the two URLs part again',
    (src) => src.replace('        nodeId: entitySeedId(type, keys),',
      "        nodeId: entitySeedId(type, keys), positive: ['x'],")],
];
const RENAME_CONTROLS = [
  ['comments stripped', (src) => src.split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n')],
];

let caught = 0; const wrong = [];
console.log('\n[9-bis] mutants (defects CAUGHT, controls ESCAPE)');
async function score(name, mutate, tag) {
  try { return await renameSuite((await loadWithProbe(API_PATH, { mutate, tag })).module); }
  catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      console.error(`  anchor GONE: ${name} — ${e.message}`);
      process.exit(2);
    }
    return { failed: 1 };
  }
}
for (const [name, mutate] of RENAME_DEFECTS) {
  const r = await score(name, mutate, 'rn');
  if (r.failed > 0) { caught++; console.log(`  caught  ${name}`); }
  else { wrong.push(name); console.log(`  ESCAPED ${name}`); }
}
for (const [name, mutate] of TRUNCATION_DEFECTS) {
  let r;
  try { r = await truncationSuite((await loadWithProbe(API_PATH, { mutate, tag: 'tr' })).module); }
  catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
    }
    r = { failed: 1 };
  }
  if (r.failed > 0) { caught++; console.log(`  caught  ${name}`); }
  else { wrong.push(name); console.log(`  ESCAPED ${name}`); }
}
for (const [name, mutate] of INTERVAL_DEFECTS) {
  let r;
  try { r = await intervalSuite((await loadWithProbe(API_PATH, { mutate, tag: 'iv' })).module); }
  catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
    }
    r = { failed: 1 };
  }
  if (r.failed > 0) { caught++; console.log(`  caught  ${name}`); }
  else { wrong.push(name); console.log(`  ESCAPED ${name}`); }
}
for (const [name, mutate] of REFUSAL_DEFECTS) {
  let r;
  try { r = await refusalSuite((await loadWithProbe(API_PATH, { mutate, tag: 'rf' })).module); }
  catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
    }
    r = { failed: 1 };
  }
  if (r.failed > 0) { caught++; console.log(`  caught  ${name}`); }
  else { wrong.push(name); console.log(`  ESCAPED ${name}`); }
}
for (const [name, mutate] of ONE_BUILDER_DEFECTS) {
  let r;
  try { r = await oneBuilderSuite((await loadWithProbe(API_PATH, { mutate, tag: 'ob' })).module); }
  catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
    }
    r = { failed: 1 };
  }
  if (r.failed > 0) { caught++; console.log(`  caught  ${name}`); }
  else { wrong.push(name); console.log(`  ESCAPED ${name}`); }
}
for (const [name, mutate] of RENAME_CONTROLS) {
  const r = await score(name, mutate, 'rnc');
  if (r.failed === 0) console.log(`  escaped ${name}`);
  else { wrong.push(`control caught: ${name}`); console.log(`  CAUGHT  ${name} <- control caught`); }
}
// 변이가 만든 실패는 «대상의» 실패가 아닙니다. 보고되는 수는 실물 run 의 것입니다.
pass = base.pass;
failures.length = base.failed;

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`MUTANTS ${caught}/${RENAME_DEFECTS.length + TRUNCATION_DEFECTS.length + INTERVAL_DEFECTS.length + REFUSAL_DEFECTS.length + ONE_BUILDER_DEFECTS.length} caught, ${wrong.length} wrong`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 && wrong.length === 0 ? 0 : 1);
