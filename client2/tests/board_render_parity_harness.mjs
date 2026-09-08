/**
 * 🏷️ C-45 게이트 — 「레코드를 통째로 실어도 화면 텍스트가 «같은가»」. 논증이 아니라 잽니다.
 *
 * 🔴 THE ARGUMENT WAS NOT THE MEASUREMENT, AND THE LEAD WAS RIGHT TO SAY SO. C-45 reasoned that
 *    extra keys reach no pixel because `table_part` renders declared columns and nothing walks
 *    the view models' keys. That reasoning is sound and it is still reasoning: it holds only
 *    while every panel keeps behaving that way, and the thing it is about — rendered text — was
 *    never compared. So this file renders the board TWICE, once with the records riding whole
 *    and once with the narrowing put back, and diffs what a person would read.
 *
 * 🔴 AND IT CARRIES ITS OWN CONTROL. If the narrowed build and the whole build produced the
 *    same VIEW MODELS, a zero diff would prove nothing at all — the run would be comparing a
 *    thing with itself. So the models are compared too, and they must DIFFER.
 *
 * Run:  node client2/tests/board_render_parity_harness.mjs
 */
import { loadBoardModules } from './lib/board_modules.mjs';
import { makeDoc, makeObserver, flush, walk } from './lib/board_dom.mjs';

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};

// 🔴 THE NARROWING, PUT BACK. These are the six lines C-45 added — one per site where a server
//    record was being rebuilt from a field list. Removing them is the BEFORE state, and the
//    harness refuses to run if any of them is missing: an anchor that no longer matches would
//    make this compare today's build with itself and call it parity.
const SPREADS = ['\n    ...cell,', '\n      ...c,', ' ...e,', '\n        ...ev,',
  '\n          ...h,', ' ...k,'];
const narrow = (src) => {
  let out = src;
  for (const s of SPREADS) {
    if (!out.includes(s)) throw new Error(`spread anchor GONE: ${JSON.stringify(s)}`);
    out = out.replace(s, s.startsWith('\n') ? '' : ' ');
  }
  return out;
};

// The response every panel is handed. 🔴 EVERY RECORD CARRIES A FIELD THE CLIENT DOES NOT
// NAME (`server_only_*`): that is what the narrowing used to throw away, and without it the
// two builds would be identical and this harness would be measuring nothing.
const CELL = (x, y) => ({ x, y, n: 1, color_role: 'found', node_id: `n:${x}:${y}`,
  server_only_cell: 'kept' });
const BODY = {
  ok: true, state: 'ready',
  // 🔴 `projectionModel` LOOKS UP AN AXIS, so the body carries `projections[]` rather than one
  //    projection — a fixture of the wrong shape returns 「axis_not_served」 and the comparison
  //    would have been between two absences.
  projections: [{ axis: 'bond', frame: { grid: { cols: 3, rows: 3 } },
    cells: [CELL(0, 0), CELL(1, 0), CELL(2, 1)] }],
  components: [{ component_id: 'c1', entity_id: 'e1', core: { lineage: null }, bonding: null,
    resolution_state: 'resolved', transfer_events: [],
    upstream_process: { evidence_ids: [{ step: 'WAFER_SORT', occurred_at: '2026-09-01',
      server_only_step: 'kept' }] },
    server_only_component: 'kept' }],
  summary: {}, core_types: [],
  rows: [{ id: 'r1', incomparable: false,
    evidence: [{ seed: 's1', sign: '+', server_only_evidence: 'kept',
      hops: [{ id: 'h1', node_kind: 'defect', label: 'H', ref: null,
        server_only_hop: 'kept' }] }] }],
  selectable_finding_kinds: [{ id: 'void', label: 'void', active: true,
    server_only_kind: 'kept' }],
  nodes: [], edges: [], truncated: null, generated_at: '2026-09-08T00:00:00Z',
};
const stubFetch = async () => ({
  ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(BODY)),
});

/** Mount the declared BOARD and hand back what a person would read. */
async function renderBoard(mods) {
  const doc = makeDoc('light');
  const host = doc.createElement('div');
  const markings = new mods.store.MarkingStore();
  const observe = makeObserver();
  const bound = mods.main.bindLoaders(mods.main.BOARD,
    { apiBase: '', fetchImpl: stubFetch, dpr: 1 });
  const shell = new mods.shell.GridShell(host, {
    doc, markings, parts: mods.main.PARTS, observeSize: observe,
  });
  shell.render(bound);
  await flush(); await flush();
  observe.fireAll(400, 300);
  await flush(); await flush();
  return { seats: shell.panels.size, text: walk(host).map((n) => n._text || '').join('') };
}

console.log('-- the board, rendered twice ----------------------------------------');
const whole = await loadBoardModules();
const narrowed = await loadBoardModules({ 'api.js': narrow });

// ══ ① 두 빌드가 «정말 다른가» — 아니면 아래 비교가 공허합니다 ═════════════════════════
{
  const a = whole.api.projectionModel(BODY, 'bond');
  const b = narrowed.api.projectionModel(BODY, 'bond');
  const keysOf = (m) => Object.keys(((m && m.cells) || [])[0] || {}).sort().join(',');
  ok('A1 the whole build keeps the field the client never names',
    keysOf(a).includes('server_only_cell'), keysOf(a));
  ok('A2 ...and the narrowed build drops it — so the two builds ARE different',
    !keysOf(b).includes('server_only_cell'), keysOf(b));
}

// ══ ② 그리고 «화면 텍스트»는 같아야 합니다 ══════════════════════════════════════════
const A = await renderBoard(whole);
const B = await renderBoard(narrowed);
ok(`B1 the board seated its declared panels (${A.seats})`,
  A.seats > 0 && A.seats === B.seats, `${A.seats} vs ${B.seats}`);
ok('B2 every rendered string is identical, whole vs narrowed', A.text === B.text,
  (() => {
    const x = A.text.split('');
    const y = B.text.split('');
    for (let i = 0; i < Math.max(x.length, y.length); i += 1) {
      if (x[i] !== y[i]) return `first difference at #${i}: ${JSON.stringify(x[i])} vs ${JSON.stringify(y[i])}`;
    }
    return `lengths ${x.length} vs ${y.length}`;
  })());
// ⚠️ CONTROL: a comparison of two empty strings is also 「identical」. The board has to have
//    drawn something, or B2 passes on a screen that never rendered.
ok(`B3 CONTROL: the board actually drew text (${A.text.trim().length} chars)`,
  A.text.trim().length > 0, `${A.text.trim().length} chars`);

console.log(`\n${failures.length === 0 ? '✓' : '✗'} ${pass} passed, ${failures.length} failed`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
