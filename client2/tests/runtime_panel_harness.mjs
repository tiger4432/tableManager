/**
 * 런타임 패널 — 아홉 고리가 «값»으로 그려지고, 없는 것이 0 으로 그려지지 않는다.
 *
 *   node client2/tests/runtime_panel_harness.mjs
 *
 * WHY (C-74, owner 2026-09-11 「뭔지도 모르는 게 뒤에서 계속 도네」). Nine loops run behind
 * this product and no screen said what any of them last did. `/health` publishes a VERDICT;
 * this table publishes VALUES, and the two must not stand in for each other.
 *
 * 🔴 THE DEFECT THIS SCORES AGAINST IS SILENT BY CONSTRUCTION. A loop that never reported a
 *    lap and a loop whose last lap took 0 s are different facts; drawn with the same glyph the
 *    table reproduces the silence it exists to end. Every absence assertion here is that one.
 * ⚠️ NOT SCORED, AND WHY: the screen itself. `/runtime` is admin-gated and I do not enter
 *    tokens, so nobody in this lane can open it — the owner sees it after pulling. What is
 *    scored is the module the screen is made of.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'runtime_panel.js');
const LF = String.fromCharCode(10);

// ── the smallest document the panel needs ────────────────────────────────────────────────
function makeDoc() {
  const make = (tag) => ({
    tagName: tag, children: [], attrs: {}, style: {}, className: '', _text: '',
    appendChild(c) { this.children.push(c); return c; },
    append(...cs) { cs.forEach((c) => this.appendChild(c)); },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  return { createElement: make };
}
const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const byTag = (root, tag) => walkAll(root).filter((e) => e.tagName === tag);

// 🔴 THE SHAPE THE ROUTE ACTUALLY SENDS (`server/runtime_loops.py`), not an invented one:
//    nine entries in the route's own order, keys OMITTED rather than nulled, `web` carrying
//    no lap at all, `chain` carrying a depth, `postgres` answering with a state.
const PAYLOAD = {
  generated_at: 1757600000.0,
  loops: [
    { loop: 'web', process: 'web', board: '1', alive: true },
    { loop: 'watcher', process: 'watcher', board: '2', alive: true,
      last_age_seconds: 3, last_seconds: 0, knob: 'config/ingestion_settings.json' },
    { loop: 'chain', process: 'chain', board: '3', alive: true,
      last_age_seconds: 1, last_seconds: 12, depth: 0, knob: 'config/chain_rules.json' },
    { loop: 'outbox_purge', process: 'chain', board: '3-a', alive: true,
      last_age_seconds: 44, knob: 'config/chain_rules.json' },
    { loop: 'listen', process: 'chain', board: '3-b', alive: true,
      last_age_seconds: 2, reconnects: 0 },
    { loop: 'ledger_followup', process: 'chain', board: '4', alive: true,
      last_age_seconds: 9, last_seconds: 2, pace: 200, knob: 'config/pacing.json' },
    { loop: 'ledger_census', process: 'chain', board: '5', alive: false,
      knob: 'config/pacing.json' },
    { loop: 'scheduler', process: 'scheduler', board: '6', alive: true,
      last_age_seconds: 17, last_seconds: 1, knob: 'config/auto_update.json' },
    { loop: 'postgres', process: 'postgres', board: '7', alive: true, state: 'idle',
      knob: 'server/scripts/tune_layer_tables.py' },
  ],
};

let ran = 0;
const NAMES = [];
let failures = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failures.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

function suite(mod) {
  const { RuntimePanel, runtimeView, ALIVE } = mod;
  const ABSENT = mod.ABSENT || '—';
  const doc = makeDoc();
  const mount = doc.createElement('div');
  const panel = new RuntimePanel(mount, { doc });
  panel.render(PAYLOAD);

  const bodyRows = byTag(mount, 'tr').filter((tr) => byTag(tr, 'td').length);
  const cell = (rowIndex, key) => (byTag(bodyRows[rowIndex] || { children: [] }, 'td')
    .find((td) => td.getAttribute('data-col') === key) || {}).textContent;

  console.log(`${LF}-- nine loops, in the order the answer carried them --`);
  eq('R1 one row per loop the response carried', bodyRows.length, 9);
  eq('R2 ...in the response\'s order, not one written down here',
    bodyRows.map((_, i) => cell(i, 'loop')).join(','),
    PAYLOAD.loops.map((l) => l.loop).join(','));
  // 🔴 A TENTH LOOP MUST APPEAR WITHOUT AN EDIT. A hard-coded list of nine would hide exactly
  //    the thing this panel exists to show -- something running that nobody named.
  {
    const extra = { generated_at: 1, loops: [...PAYLOAD.loops, { loop: 'tenth', process: 'x' }] };
    eq('R3 a loop this file never heard of is drawn too', runtimeView(extra).rows.length, 10);
  }

  console.log(`${LF}-- absence is absence, and 0 is a value --`);
  // `chain` reports depth 0 and `outbox_purge` reports no depth at all. Same column, and the
  // whole point is that they must not look alike.
  eq('A1 a measured zero is drawn as 0', cell(2, 'depth'), '0');
  eq('A2 ...and a depth that never came is the absent glyph', cell(3, 'depth'), ABSENT);
  eq('A3 a lap of 0 s is 0s, not blank', cell(1, 'seconds'), '0s');
  eq('A4 ...and a loop with no lap at all is the absent glyph', cell(0, 'age'), ABSENT);
  eq('A5 the absent glyph carries no unit -- 「—s」 would be a value nobody measured',
    cell(6, 'seconds'), ABSENT);
  eq('A6 a knob nobody declared is absent, not an empty cell', cell(4, 'knob'), ABSENT);

  console.log(`${LF}-- alive is THREE states --`);
  eq('V1 alive true is the filled mark', cell(0, 'alive'), ALIVE.YES);
  eq('V2 alive false is the hollow mark', cell(6, 'alive'), ALIVE.NO);
  // 🔴 `null` IS NOT `false`. postgres answers `{alive: null}` from boot; drawing that hollow
  //    would report a database as down.
  eq('V3 alive unknown is neither mark', runtimeView({ loops: [{ loop: 'x', alive: null }] })
    .rows[0].alive, ALIVE.UNKNOWN);

  console.log(`${LF}-- a read that failed is not an empty list --`);
  eq('U1 no payload reads as unread', runtimeView(null).state, 'unread');
  eq('U2 ...and unread draws no rows rather than inventing them',
    runtimeView(null).rows.length, 0);
  eq('U3 a payload with loops reads as ready', runtimeView(PAYLOAD).state, 'ready');
  // 「못 읽음」 and 「고리 0개」 must not be the same pixel either.
  eq('U4 an answer carrying an empty list is READY, not unread',
    runtimeView({ loops: [] }).state, 'ready');
}

const first = await loadWithProbe(SRC, {});
suite(first.module);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${ran} assertions, `
  + `${failures.length} failure(s)`);
failures.forEach((f) => console.log(`   x ${f}`));
const base = { ran, names: NAMES.slice(), failed: failures.length };

const MUTANTS = [
  { id: 'M1', what: 'a missing number is drawn as 0',
    catches: 'A2 ...and a depth that never came',
    from: '    depth: countText(entry.depth),',
    to: '    depth: String(Number(entry.depth) || 0),' },
  { id: 'M2', what: 'the unit is glued on before the absence test',
    catches: 'A5 the absent glyph carries no unit',
    from: '  return isCount(value) ? `${Number(value)}s` : ABSENT;',
    to: '  return `${isCount(value) ? Number(value) : ABSENT}s`;' },
  { id: 'M3', what: 'unknown aliveness is drawn as dead',
    catches: 'V3 alive unknown is neither mark',
    from: '  if (value === false) return ALIVE.NO;',
    to: '  if (!value) return ALIVE.NO;' },
  { id: 'M4', what: 'a failed read is folded into an empty list',
    catches: 'U1 no payload reads as unread',
    from: '  if (!loops) return { state: \'unread\', rows: [] };',
    to: '  if (!loops) return { state: \'ready\', rows: [] };' },
  { id: 'M5', what: 'the rows come from a list written down here',
    catches: 'R3 a loop this file never heard of',
    from: '  return { state: \'ready\', rows: loops.map(rowOf) };',
    to: '  return { state: \'ready\', rows: loops.slice(0, 9).map(rowOf) };' },
  // 🔴 CONTROL: a comment cannot change an answer.
  { id: 'M6', what: 'CONTROL: a comment line is removed', control: true,
    from: '/** 살았나 — 세 상태입니다. 「모른다」를 ○ 로 그리면 죽은 것으로 읽힙니다. */',
    to: '/** */' },
];

const runMutant = async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(SRC, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  suite(loaded.module);
  return { ran, names: NAMES.slice(), failures: failures.slice() };
};

const defects = await scoreMutants(MUTANTS.filter((m) => !m.control), runMutant,
  { baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== defect mutants (each must be CAUGHT by the check it names) ==` });
const controls = await scoreMutants(MUTANTS.filter((m) => m.control), runMutant,
  { mustCatch: false, baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== controls (each must wake NOTHING) ==` });

const scored = MUTANTS.length - defects.wrong - controls.wrong;
console.log(`${LF}  ${scored}/${MUTANTS.length} scored as intended.`);
const failed = base.failed + (MUTANTS.length - scored);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
