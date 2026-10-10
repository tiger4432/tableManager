/**
 * 걷기 «페이지»가 표를 자기가 짓지 않는다 — 그려진 것이 `walkTableView` 의 답이다.
 *
 *   node client2/tests/walk_table_harness.mjs
 *
 * WHY THIS EXISTS (C-72). C-70 moved the sectioning and the columns into `derive.js` so the two
 * walk tables could not drift, and the SEARCH BOX half was scored on screen. The PAGE half was
 * not: its call sat inside `boot()`, so 「it calls that function」 rested on 「its own copy is
 * deleted」 and nothing would redden the day somebody put a copy back. I reported that the page
 * could not be stood up — that was WRONG. `boot(doc, host, deps)` takes an injected `doc`, and
 * the file's own footer says why: 「bare node 로 이 모듈을 읽어도 DOM 을 안 건드려야 하니스가
 * 붙을 수 있습니다」. The place to measure already existed; C-72 made the half importable
 * (`table_view.js`) so the comparison has something to compare AGAINST.
 *
 * 🔴 WHAT IT ASSERTS IS AN EQUALITY, NOT A LOOK. Every head, every column label, every cell and
 *    its two classes are compared to what `walkTableView` returns for the same input — order
 *    included. A renderer that draws something reasonable but does not ask is red.
 *
 * 🔴 THE MUTANT THE RULING ASKED FOR IS M1: the renderer names its own columns again. It leaves
 *    the row count and the section count untouched, which is why counting could never find it.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { walkTableView } from '../src/walk/table_view.js';
import { SIGN } from '../src/rnd_board/marking_store.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'walk', 'main.js');
const LF = String.fromCharCode(10);

// ── the smallest document `boot()` actually needs ────────────────────────────────────────
// Measured, not guessed: `createElement` · `append` · `textContent` · `className` ·
// `setAttribute` · `addEventListener` · `value` · `checked` · `type`, plus a `head` for
// `ensureWalkStyles`. Nothing else is touched, which is what makes this cheap.
function makeDoc() {
  const make = (tag) => option(tag, {
    tagName: tag, children: [], attrs: {}, listeners: {},
    className: '', value: '', checked: false, type: '', _text: '',
    append(...cs) { cs.forEach((c) => this.children.push(c)); },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  return { createElement: make, head: make('head') };
}
// The browser's rule for an <option>: with no value of its own it is worth its TEXT. A stub where every
// value starts as '' cannot see the type placeholder becoming a type (lead b417e2ad8), so it keeps the rule.
function option(tag, node) {
  if (tag !== 'option') return node;
  delete node.value;
  return Object.defineProperty(node, 'value', {
    get() { return this._value !== undefined ? this._value : this.textContent; },
    set(v) { this._value = String(v); },
  });
}

const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const byClass = (host, cls) => walkAll(host).filter((e) => (e.className || '') === cls);
const byTag = (host, tag) => walkAll(host).filter((e) => e.tagName === tag);
// The view's own cells: the table's check column (lead 53050a4ec) is the page's, not the view's.
const viewCells = (host, tag) => byTag(host, tag).filter((e) => e.className !== 'wk-check');
const settle = async () => { for (let i = 0; i < 8; i += 1) await Promise.resolve(); };

// ── fixtures ─────────────────────────────────────────────────────────────────────────────
// 🔴 MIXED TYPES AND A QUALIFIER, because a single-type answer with no qualifiers is one a
//    hard-coded renderer draws correctly. `x: 0` is here on purpose too: 「없음」 and 「0」 have
//    to stay different glyphs, and that decision moved with the half being scored.
const DECL = {
  ok: true,
  entities: [
    { type: 'die@1', keys: ['mat_id', 'x', 'y'] },
    { type: 'wafer@1', keys: ['wafer'] },
  ],
  predicates: [{ name: 'inspected@1', subjects: ['wafer@1'], object: {} }],
};
const RESULT = {
  nodes: [
    { id: 'n:1', type: 'die@1', label: 'D-1', depth: 1, keys: { mat_id: 'M-1', x: 0, y: 12 } },
    { id: 'n:2', type: 'die@1', label: 'D-2', depth: 2, keys: { mat_id: 'M-2', x: 3 } },
    { id: 'n:3', type: 'wafer@1', label: 'W-1', depth: 0, keys: { wafer: 'SYN-1' } },
  ],
  edges: [{ id: 'e:1', source: 'n:3', target: 'n:1', predicate: 'inspected', qualifiers: { gate: 7 } }],
};

// Two + starts and one −; a die reached from + only, one from − only, one from both. The answer's reach is the server's.
const SIGNED = {
  nodes: [
    { id: 's:a', type: 'wafer@1', label: 'A', depth: 0, keys: { wafer: 'A' } },
    { id: 's:c', type: 'wafer@1', label: 'C', depth: 0, keys: { wafer: 'C' } },
    { id: 's:b', type: 'wafer@1', label: 'B', depth: 0, keys: { wafer: 'B' } },
    { id: 'd:1', type: 'die@1', label: 'D-1', depth: 1, keys: { mat_id: 'M-1' } },
    { id: 'd:2', type: 'die@1', label: 'D-2', depth: 1, keys: { mat_id: 'M-2' } },
    { id: 'd:3', type: 'die@1', label: 'D-3', depth: 2, keys: { mat_id: 'M-3' } },
    { id: 'd:4', type: 'die@1', label: 'D-4', depth: 1, keys: { mat_id: 'M-4' } },
  ],
  edges: [{ id: 'e:a3', source: 's:a', target: 'd:3', predicate: 'inspected', qualifiers: { gate: 7 } },
    { id: 'e:b3', source: 's:b', target: 'd:3', predicate: 'inspected', qualifiers: { gate: 9 } },
    { id: 'e:a4', source: 's:a', target: 'd:4', predicate: 'inspected', qualifiers: { gate: 1 } },
    { id: 'e:c4', source: 's:c', target: 'd:4', predicate: 'inspected', qualifiers: { gate: 2 } }],
  propagation: { ranked: [{ id: 'd:1', reach: [2, 0] }, { id: 'd:2', reach: [0, 1] }, { id: 'd:3', reach: [1, 1] },
    { id: 'd:4', reach: [2, 0] }] },
};
const SIGNED_STARTS = { positive: ['s:a', 's:c'], negative: ['s:b'] };
const GATE_IN = 'inspected (in) · gate';
const ALL = 'd:1,d:2,d:3,d:4,s:a,s:b,s:c';

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

/** Stand the page up and hand back its host, with the walk answered from a fixture. */
async function render(mod, result = RESULT) {
  const doc = makeDoc();
  const host = doc.createElement('div');
  const handle = mod.boot(doc, host, {
    apiBase: '',
    // 🔴 The declaration comes through the SAME door the product uses. Writing it into
    //    `state.decl` would skip whatever the loader does to it.
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }),
  });
  await settle();
  handle.state.type = 'die@1';
  handle.state.run = 'done';
  handle.state.result = result;
  handle.render();
  return { host, handle };
}

async function suite(mod) {
  const { host } = await render(mod);
  const view = walkTableView(RESULT, DECL.entities);

  console.log(`${LF}-- the page draws the view's answer, not its own --`);
  eq('V1 one section head per section, worded by the view',
    byClass(host, 'wk-sechead').map((e) => e.textContent).join(' | '),
    view.sections.map((s) => s.heading).join(' | '));
  eq('V2 the column labels are the view\'s, in the view\'s order',
    viewCells(host, 'th').map((e) => e.textContent).join(','),
    view.sections.flatMap((s) => s.columns.map((c) => c.name)).join(','));
  eq('V3 every cell is the view\'s text, in the view\'s order',
    viewCells(host, 'td').map((e) => e.textContent).join('|'),
    view.sections.flatMap((s) => s.rows.flatMap((r) => r.cells.map((c) => c.text))).join('|'));
  // 🔴 0 IS A VALUE. `x: 0` in the fixture is the discriminant: a renderer using `v || ''`
  //    draws it as the same blank an absent key gets, and the row then lies about the die.
  ok('V4 a zero is drawn as 0 and an absent key as a blank, not as the same glyph',
    viewCells(host, 'td').map((e) => e.textContent).includes('0')
      && viewCells(host, 'td').map((e) => e.textContent).includes(''),
    viewCells(host, 'td').map((e) => e.textContent).join('|'));
  eq('V5 the numeric class follows the view\'s reading of each cell',
    viewCells(host, 'td').map((e) => (e.className === 'wk-num' ? 1 : 0)).join(''),
    view.sections.flatMap((s) => s.rows.flatMap((r) => r.cells.map(
      (c) => (c.numeric && c.kind !== 'id' ? 1 : 0)))).join(''));
  eq('V6 the id cell keeps its own class rather than the numeric one',
    viewCells(host, 'td').filter((e) => e.className === 'wk-id').length,
    view.sections.reduce((n, s) => n + s.rows.length, 0));

  console.log(`${LF}-- the cap is a number the screen SAYS --`);
  const many = { nodes: Array.from({ length: 203 }, (_, i) => (
    { id: `m:${i}`, type: 'die@1', label: `L${i}`, keys: {} })), edges: [] };
  const { host: capped } = await render(mod, many);
  const capView = walkTableView(many, DECL.entities);
  // ⚠️ THE PAGE HAS OTHER NOTES. Scoping by class alone caught the form's two and made
  //    「no note」 unfalsifiable; the cap note is the one that says so.
  const capNotes = (h) => byClass(h, 'wk-note').map((e) => e.textContent)
    .filter((t) => t.includes('not drawn'));
  eq('C1 over the cap the view hides exactly what did not fit', capView.hidden, 3);
  eq('C2 and the screen prints THAT number',
    capNotes(capped).join(' / '), '3 more not drawn');
  ok('C3 the total is not what is printed, since 203 would read as all of it being hidden',
    !capNotes(capped).some((t) => t.includes('203')), capNotes(capped).join(' / '));
  const { host: exact } = await render(mod, { nodes: RESULT.nodes, edges: [] });
  eq('C4 under the cap there is no cap note -- the absence is the answer',
    capNotes(exact).length, 0);

  console.log(`${LF}-- signed starts and checks, the board's way (lead 10-09) --`);
  {
    const DECLS = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] }],
      predicates: [{ name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } }] };
    const asked = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (u.includes('/subgraph')) asked.push(u);
      return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? RESULT : DECLS) };
    } });
    await settle();
    const go = () => walkAll(host).find((e) => e.className === 'wk-go');
    const click = (e, event = {}) => { for (const fn of (e && e.listeners.click) || []) fn(event); };
    const query = (u) => new URLSearchParams((u || '').split('?')[1] || '');
    // The starts go in the baskets (lead bc63378e5): A by Positive's +, B by Negative's +, then Walk.
    const basket = (sign) => walkAll(host).find((e) => e.attrs && e.attrs['data-sign'] === sign && e.className.startsWith('wk-basket'));
    const plus = (sign) => click(walkAll(basket(sign) || { children: [] }).find((e) => e.className === 'wk-basketadd'));
    handle.state.type = 'wafer@1';
    handle.state.keys = { wafer: 'A' };
    plus('+');
    handle.state.keys = { wafer: 'B' };
    plus('−');
    click(go());
    await settle();
    const starts = handle.graph.markings.entries('walk-start');
    const q = query(asked[asked.length - 1]);
    ok('S1 the baskets are the starts - A in Positive as +, B in Negative as -; Walk asks both',
      starts.length === 2 && starts[0][1] === SIGN.CASE && starts[1][1] === SIGN.CONTROL
        && q.getAll('positive').join() === starts[0][0] && q.getAll('negative').join() === starts[1][0],
      JSON.stringify({ starts, q: q.toString().slice(0, 200) }));
    const said = ['+', '−'].map((sign) => walkAll(basket(sign) || { children: [] })
      .filter((e) => e.className === 'wk-basketlabel').map((e) => e.textContent).join());
    ok('S2 each basket names its starts', JSON.stringify(said) === JSON.stringify(['A', 'B']), JSON.stringify(said));
    const box = (id) => walkAll(host).find((e) => e.attrs && e.attrs['data-row'] === id);
    click(box('n:1'), { shiftKey: true });
    click(box('n:2'));
    const row1 = walkAll(host).find((e) => e.tagName === 'tr' && e.children.includes(walkAll(host).find((c) => c.className === 'wk-check' && c.children.includes(box('n:1')))));
    ok('S3 a Shift click checks a row as a control, drawn as one; a click checks it as +',
      handle.graph.markings.signOf('walk-2', 'n:1') === SIGN.CONTROL && handle.graph.markings.signOf('walk-2', 'n:2') === SIGN.CASE
        && Boolean(row1) && row1.className === 'is-control' && box('n:1').checked === true,
      JSON.stringify(handle.graph.markings.entries('walk-2')));
    const before = asked.length;
    click(walkAll(host).find((e) => e.className === 'wk-next-edge'));
    await settle();
    const n = query(asked[before]);
    ok('S4 Next walks on from the + rows with the - rows as negative',
      asked.length === before + 1 && n.getAll('positive').join() === 'n:2' && n.getAll('negative').join() === 'n:1',
      n.toString().slice(0, 200));
  }

  console.log(`${LF}-- the type placeholder is no type (lead b417e2ad8) --`);
  {
    const asked = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '',
      fetchImpl: async (url) => { asked.push(String(url)); return { ok: true, status: 200, json: async () => DECL }; } });
    await settle();
    // The page's own control, as the browser drives it: the select takes the picked option's value.
    const pick = (at) => {
      const sel = byClass(host, 'wk-select')[0];
      if (!sel) return;
      sel.value = at(sel.children).value;
      for (const fn of sel.listeners.change || []) fn();
    };
    pick((opts) => opts.find((o) => o.value === 'die@1'));
    await settle();
    const subjects = () => asked.filter((u) => u.includes('/key-values')).length;
    const onType = subjects();
    pick((opts) => opts[0]);
    await settle();
    const go = byClass(host, 'wk-go')[0];
    ok('P1 picking the placeholder again: no type, Run is off, no subject list is asked',
      onType === 1 && handle.state.type === '' && go && go.disabled === true && subjects() === onType,
      `${onType} ${JSON.stringify(handle.state.type)} ${go && go.disabled} ${subjects()}`);
  }

  console.log(`${LF}-- a walk may start from a node that only appears as an object (29cee1d47) --`);
  {
    // Shapes and classes from the shipped sample: recipe@1 is a static object-only type, defect@1
    // an object-only type that is not static, die@1 on both sides.
    const DECL2 = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] },
        { type: 'recipe@1', keys: ['recipe'], class: ['static'] }, { type: 'defect@1', keys: ['defect'] },
        { type: 'note@1', keys: ['note'] }],
      predicates: [
        { name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } },
        { name: 'processed_with@1', subjects: ['wafer@1'], object: { types: ['recipe@1'] } },
        { name: 'observed@1', subjects: ['die@1'], object: { types: ['defect@1'] } }] };
    const stand = async (keyValues) => {
      const doc = makeDoc();
      const host = doc.createElement('div');
      mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => ({ ok: true, status: 200,
        json: async () => (String(url).includes('/key-values') ? keyValues : DECL2) }) });
      await settle();
      const sel = byClass(host, 'wk-select')[0];
      return { host, pick: async (type) => {
        sel.value = type;
        for (const fn of sel.listeners.change || []) fn();
        await settle();
      } };
    };
    const follow = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-follow'] !== undefined)
      .map((e) => e.attrs['data-follow']).join(',');
    const notes = (h) => byClass(h, 'wk-note').map((e) => e.textContent).join(' / ');

    const listed = await stand({ nodes: [{ keys: { recipe: 'R-1' }, count: 3 }], scanned: 1,
      scan_truncated: false, values_truncated: false });
    await listed.pick('recipe@1');
    // The box (lead bccbdd601), focused as the browser does: its rows are the server's nodes, keys and count.
    const boxIn = walkAll(listed.host).find((e) => e.attrs && e.attrs.role === 'combobox');
    for (const fn of (boxIn && boxIn.listeners.focus) || []) fn({});
    const offered = byClass(listed.host, 'wk-searchitem').map((e) => e.children.map((c) => c.textContent).join(' '));
    ok('F2 the seed field is Pick a node and its box, focused, offers the node the server listed',
      walkAll(listed.host).some((e) => e.className === 'wk-label' && e.textContent === 'Pick a node')
        && offered.includes('R-1 3 atoms'), offered.join(' | '));
    // 🔴 EVERY DECLARED PREDICATE, WHATEVER THE TYPE (owner 10-06, lead bf3653401) — the walk filters, not the list.
    const ALL = DECL2.predicates.map((p) => p.name).join(',');
    eq('F6 static recipe@1 draws every declared predicate', follow(listed.host), ALL);
    await listed.pick('note@1');
    eq('F7 a type no predicate touches still draws every declared predicate', follow(listed.host), ALL);
    await listed.pick('defect@1');
    eq('F1 defect@1 draws every declared predicate, those that do not touch it too',
      follow(listed.host), ALL);
    // 🔴 A TYPE CHANGE KEEPS EVERY TICK (lead 10-06, reversing 10-02): every box is drawn, so no tick is hidden.
    //    The frozen R&D box still drops what does not touch the new type (its harness, H3).
    const tick = (h, name) => {
      const row = walkAll(h).find((e) => e.attrs && e.attrs['data-follow'] === name);
      const cb = row && row.children.find((c) => c.tagName === 'input');
      for (const fn of (cb && cb.listeners.change) || []) fn();
    };
    const ticked = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-follow'] !== undefined
      && e.children.some((c) => c.tagName === 'input' && c.checked)).map((e) => e.attrs['data-follow']).join(',');
    await listed.pick('die@1');
    tick(listed.host, 'inspected@1');
    const before = ticked(listed.host);
    await listed.pick('recipe@1');
    const dropped = ticked(listed.host);
    tick(listed.host, 'processed_with@1');
    await listed.pick('wafer@1');
    ok('F8 changing the type keeps every tick, those that do not touch the new type too',
      before === 'inspected@1' && dropped === 'inspected@1' && ticked(listed.host) === 'inspected@1,processed_with@1',
      `${before} / ${dropped} / ${ticked(listed.host)}`);
    await listed.pick('die@1');
    // The page half of the board harness's old B8 (lead 10-06): every declared type, every declared predicate.
    const apart = [];
    for (const { type } of DECL2.entities) {
      await listed.pick(type);
      if (follow(listed.host) !== ALL) apart.push(`${type}: ${follow(listed.host)}`);
    }
    ok('F9 every declared type draws every declared predicate', apart.length === 0, apart.join(' ; '));
    await listed.pick('die@1');
    eq('F3 die@1 draws every declared predicate, in declaration order',
      follow(listed.host), 'inspected@1,processed_with@1,observed@1');

    const empty = await stand({ nodes: [], scanned: 0, scan_truncated: false, values_truncated: false });
    await empty.pick('recipe@1');
    ok('F4 read and empty says there is no node of the type',
      notes(empty.host).includes('No node of this type in the ledger'), notes(empty.host));
    const cut = await stand({ nodes: [], scanned: 1001, scan_truncated: true, values_truncated: false });
    await cut.pick('recipe@1');
    ok('F5 not read to the end says how many nodes were read',
      notes(cut.host).includes('Not every node read (up to 1001)'), notes(cut.host));
  }

  console.log(`${LF}-- the table walks on from its checked rows along a declared edge (lead 53050a4ec) --`);
  {
    // A predicate within a type (bonded_to die -> die) as well as across: the list is the declaration's, both kinds.
    const DECL3 = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] }],
      predicates: [
        { name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } },
        { name: 'bonded_to@1', subjects: ['die@1'], object: { types: ['die@1'] } }] };
    const START = { nodes: [
      { id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' } },
      { id: 'n:2', type: 'die@1', label: 'D-2', keys: { mat_id: 'M-2' } }], edges: [] };
    const STEP = { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' } },
      { id: 'n:4', type: 'die@1', label: 'D-4', keys: { mat_id: 'M-4' } }],
    edges: [{ id: 'e:4', source: 'n:1', target: 'n:4', predicate: 'bonded_to@1' }], truncated: null };
    const asked = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (u.includes('/subgraph')) asked.push(u);
      return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? STEP : DECL3) };
    } });
    await settle();
    handle.state.type = 'die@1';
    handle.state.asked = { type: 'die@1', keys: { mat_id: 'M-1' } };
    handle.state.run = 'done';
    handle.state.result = START;
    handle.render();
    const edges = (h) => walkAll(h).filter((e) => e.className === 'wk-next-edge');
    const press = (e) => { for (const fn of (e && e.listeners.click) || []) fn(); };
    const tick = (h, id) => {
      const cb = walkAll(h).find((e) => e.attrs && e.attrs['data-row'] === id);
      for (const fn of (cb && cb.listeners.click) || []) fn({});
    };
    const steps = (h) => walkAll(h).filter((e) => /^wk-step( is-on)?$/.test(e.className || ''));
    const rowsShown = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-row']).map((e) => e.attrs['data-row']);
    eq('N1 the Next of the die section is the declaration\'s edges one step from die@1, both kinds',
      edges(host).map((e) => e.textContent).join(' | '), 'inspected@1 → wafer@1 | bonded_to@1 → die@1');
    press(edges(host)[1]);
    await settle();
    ok('N2 nothing checked: every edge is off with its reason, and a press asks nothing',
      edges(host).length === 2 && edges(host).every((e) => e.disabled === true && e.attrs.title === 'Check rows first')
        && asked.length === 0, `${edges(host).map((e) => e.disabled)} ${asked.length}`);
    tick(host, 'n:1');
    const marked = handle.graph.markings.signOf('walk-2', 'n:1');
    ok('N3 a checked row is the page\'s marking the graph reads (walk-2), and the edges come on',
      marked === SIGN.CASE && edges(host).every((e) => e.disabled === false), String(marked));
    press(edges(host).find((e) => e.textContent === 'bonded_to@1 → die@1'));
    await settle();
    const q = new URLSearchParams((asked[0] || '').split('?')[1] || '');
    ok('N4 a press walks one step from the checked row alone, along that edge to its type',
      asked.length === 1 && q.getAll('positive').join() === 'n:1' && q.getAll('follow').join() === 'bonded_to@1'
        && q.getAll('collect').join() === 'die@1' && q.get('hops') === '1' && q.get('direction') === 'both',
      asked[0]);
    ok('N5 the step stacks: Step 2 lit, and the table is that step\'s answer',
      steps(host).length === 2 && steps(host)[1].className === 'wk-step is-on'
        && steps(host)[1].textContent === 'Step 2 · bonded_to@1 → die@1' && rowsShown(host).join() === 'n:1,n:4',
      `${steps(host).map((s) => s.textContent)} ${rowsShown(host)}`);
    tick(host, 'n:4');
    press(edges(host).find((e) => e.textContent === 'bonded_to@1 → die@1'));
    await settle();
    const third = steps(host).length;
    press(steps(host)[0]);
    ok('N6 a second step stacks a third; Step 1 shows the first table again and the chain stays',
      third === 3 && steps(host).length === 3 && steps(host)[0].className === 'wk-step is-on'
        && rowsShown(host).join() === 'n:1,n:2', `${third} ${rowsShown(host)}`);
    handle.state.view = 'table';
    handle.state.keys = { mat_id: 'M-1' };
    handle.baskets.add(SIGN.CASE);
    void handle.fire();
    await settle();
    ok('N7 a new start clears the steps and what their checks wrote',
      steps(host).length === 0 && handle.graph.markings.count('walk-2') === 0 && handle.state.steps.length === 0,
      `${steps(host).length} ${handle.graph.markings.count('walk-2')}`);

    // A predicate whose subject and object are one type, on real server answers (capture_walk_bundles.py): the
    // server answers each direction as it was asked, so a Next that walks one way only brings one side (lead 11e5ea207).
    const SAME = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'walk_step_same_type.json'), 'utf8'));
    const sameAsked = [];
    const sameHost = doc.createElement('div');
    const same = mod.boot(doc, sameHost, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (!u.includes('/subgraph')) return { ok: true, status: 200, json: async () => SAME._declaration };
      sameAsked.push(u);
      const body = SAME._answers[new URLSearchParams(u.split('?')[1] || '').get('direction')];
      return body ? { ok: true, status: 200, json: async () => body } : { ok: false, status: 422, json: async () => ({}) };
    } });
    await settle();
    const startNode = SAME._answers.both.nodes.find((n) => n.id === SAME._start.id);
    same.state.type = SAME._start.type;
    same.state.asked = { type: SAME._start.type, keys: { ...SAME._start.keys } };
    same.state.run = 'done';
    same.state.result = { nodes: [startNode], edges: [] };
    same.render();
    tick(sameHost, SAME._start.id);
    press(edges(sameHost).find((e) => e.textContent === `${SAME._predicate} → ${SAME._start.type}`));
    await settle();
    const sideOf = (d) => new Set(SAME._answers[d].nodes.map((n) => n.id).filter((id) => id !== SAME._start.id));
    const [outSide, inSide] = [sideOf('outgoing'), sideOf('incoming')];
    const sameRows = rowsShown(sameHost);
    ok('N8 a same-type predicate: the Next brings both sides - what it leads to and what leads to it',
      [...outSide].some((id) => !inSide.has(id)) && [...inSide].some((id) => !outSide.has(id))
        && sameAsked.length === 1 && JSON.stringify([...sameRows].sort())
          === JSON.stringify([SAME._start.id, ...outSide, ...inSide].sort()),
      `${sameAsked.length} ${sameRows.length} out ${outSide.size} in ${inSide.size}`);
  }
  // ── the page: side by side when the walk had a - start (lead 5cf5c3401, the mockup) ──
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    handle.state.type = 'wafer@1';
    handle.state.asked = { type: 'wafer@1', keys: {}, ...SIGNED_STARTS };
    handle.state.run = 'done';
    handle.state.result = SIGNED;
    handle.render();
    const has = (e, cls) => String(e.className || '').split(/\s+/).includes(cls);
    const heads = walkAll(host).filter((e) => has(e, 'wk-sidehead')).map((e) => e.textContent);
    const missing = walkAll(host).filter((e) => e.tagName === 'td' && has(e, 'wk-missing')).length;
    const secs = walkAll(host).filter((e) => e.className === 'wk-sec');
    const nextFirst = secs.length > 0 && secs.every((sec) => {
      const next = sec.children.findIndex((c) => c.className === 'wk-next');
      return next >= 0 && next < sec.children.findIndex((c) => has(c, 'wk-table'));
    });
    ok('Z9 the page: a table a type, a band a group with its starts and rows, missing in red, Next above',
      JSON.stringify(heads) === JSON.stringify(['Positive · 2 starts · 2 rows', 'Negative · 1 start · 1 row',
        'Positive · 2 starts · 3 rows', 'Negative · 1 start · 2 rows']) && missing === 6 && nextFirst,
      `${JSON.stringify(heads)} ${missing} ${nextFirst}`);
    const views = walkAll(host).filter((e) => e.attrs && e.attrs['data-view']).map((e) => e.attrs['data-view']);
    const compared = walkAll(host).filter((e) => /(^| )cmp-/.test(e.className || '')).length;
    ok('Z10 no way to Compare: the views are Table and Graph, nothing of it drawn',
      views.join() === 'table,graph' && compared === 0, `${views} ${compared}`);
    const dieSec = () => walkAll(host).filter((e) => e.className === 'wk-sec')
      .find((sec) => sec.children[0] && /^die/.test(sec.children[0].textContent)) || { children: [] };
    const table = () => walkAll(dieSec()).find((e) => has(e, 'wk-sides')) || { children: [] };
    const headRow = () => (walkAll(table()).filter((e) => e.tagName === 'tr')[1] || { children: [] }).children
      .filter((c) => c.className !== 'wk-check').map((c) => c.textContent);
    const rowOf = (id) => walkAll(table()).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === id);
    const tds = (id) => ((rowOf(id) || { children: [] }).children).filter((c) => c.className !== 'wk-check')
      .map((c) => (c.children.find((k) => k.className === 'wk-centrelabel') || c).textContent);
    ok('Z13 two groups: the + columns, the node in the centre, the − columns, then delta',
      JSON.stringify([headRow(), tds('d:3')]) === JSON.stringify([[GATE_IN, 'mat_id', GATE_IN, 'Δ'], ['7', 'M-3', '9', '−2']]),
      JSON.stringify([headRow(), tds('d:3')]));
    const copy = walkAll(rowOf('d:3') || { children: [] }).find((e) => e.className === 'wk-copyid');
    ok('Z16 the id is behind a press in the centre, not a column', Boolean(copy) && copy.attrs['data-id'] === 'd:3'
      && !headRow().includes('id'), JSON.stringify(headRow()));
    const press = (value) => {
      const b = walkAll(host).find((e) => e.attrs && e.attrs['data-rows'] === value);
      for (const fn of (b && b.listeners.click) || []) fn({});
    };
    const shown = () => walkAll(host).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']).sort().join();
    press('differs');
    const differs = shown();
    press('missing');
    const missed = shown();
    press('all');
    ok('Z14 All rows · Differs · Missing: the rows the groups differ on, the rows one missed, then every row',
      JSON.stringify([differs, missed, shown()]) === JSON.stringify([ALL, 'd:1,d:2,d:4,s:a,s:b,s:c', ALL]), JSON.stringify([differs, missed]));
    // + Column on the die section: the route in, then the far wafer's key - a column each group, + reversed.
    const addOn = walkAll(dieSec()).find((e) => e.tagName === 'button' && e.textContent === '+ Column');
    for (const fn of (addOn && addOn.listeners.click) || []) fn({});
    const pick = (n, test) => {
      const sel = walkAll(dieSec()).filter((e) => e.tagName === 'select')[n];
      const opt = sel && sel.children.find((o) => test(o.textContent));
      if (!opt) return false;
      sel.value = opt.value;
      for (const fn of sel.listeners.change || []) fn({});
      return true;
    };
    const route = pick(0, (t) => t.startsWith('inspected (in) → '));
    const value = route && pick(1, (t) => t === 'key · wafer');
    const ADDED = 'inspected (in) → wafer@1 · wafer';
    ok('Z15 + Column: a route the rows take, then what its end holds - a column each group, the + side reversed',
      JSON.stringify([route, value, headRow(), tds('d:3')]) === JSON.stringify([true, true,
        [ADDED, GATE_IN, 'mat_id', GATE_IN, ADDED, 'Δ'], ['A', '7', 'M-3', '9', 'B', '−2']]),
      JSON.stringify([route, value, headRow(), tds('d:3')]));
  }
}

// ═══ baseline ═══════════════════════════════════════════════════════════════════════════
const first = await loadWithProbe(SRC, {});
await suite(first.module);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${ran} assertions, `
  + `${failures.length} failure(s)`);
failures.forEach((f) => console.log(`   x ${f}`));
// ── Q: several edges into one node keep every value (lead 10-09, demo ①: the cell said the last edge's alone) ──
const TWO = {
  nodes: [
    { id: 'q:1', type: 'die@1', label: 'D-1', depth: 1, keys: { mat_id: 'M-1' } },
    { id: 'q:a', type: 'wafer@1', label: 'W-1', depth: 0, keys: { wafer: 'A' } },
    { id: 'q:b', type: 'wafer@1', label: 'W-2', depth: 0, keys: { wafer: 'B' } },
  ],
  edges: [
    { id: 'q:e1', source: 'q:a', target: 'q:1', predicate: 'inspected', qualifiers: { gate: 7 } },
    { id: 'q:e2', source: 'q:b', target: 'q:1', predicate: 'inspected', qualifiers: { gate: 9 } },
  ],
};
const gateCell = (TV, answer) => {
  const die = TV.walkTableView(answer, DECL.entities, DECL.predicates).sections.find((s) => s.type === 'die@1');
  const at = die.columns.findIndex((c) => c.kind === 'qualifier' && c.key === 'inspected · gate');
  return at >= 0 ? die.rows[0].cells[at] : { text: null, numeric: null };
};
const qualifierSuite = (TV) => {
  const two = gateCell(TV, TWO);
  ok('Q1 two edges into one node: the cell says both values and whose', two.text === '2 edges · 7 (W-1) · 9 (W-2)', two.text);
  const one = gateCell(TV, RESULT);
  ok('Q2 one edge: the value as it came, a number', one.text === '7' && one.numeric === true, JSON.stringify(one));
};
// The suite's own count: a mutant of main.js runs the suite alone, so its shrink is measured against this.
const suiteRan = ran;
// ── the walk table side by side as the formula (lead 5cf5c3401; the signs by the server's reach) ──
const rowIds = (table) => table.sections.flatMap((sec) => sec.rows.map((r) => r.id)).sort().join(',');
const sideSuite = (TV) => {
  const view = (starts, result = SIGNED, added) => TV.walkTableView(result, DECL.entities, DECL.predicates, undefined, starts, added);
  // A row's cell in one group under one head, as drawn: missing in brackets.
  const cell = (table, type, id, head, group) => {
    const sec = table.sections.find((x) => x.type === type);
    const at = sec ? sec.heads.indexOf(head) : -1;
    const row = sec && sec.rows.find((r) => r.id === id);
    const got = row && at >= 0 ? row.byGroup[group][at] : null;
    return got ? (got.missing ? `[${got.text}]` : got.text) : null;
  };
  const plain = view({ positive: ['s:a', 's:c'], negative: [] });
  ok('Z1 no - start: the one table it always was, every node in it, no group', plain.groups === null
    && plain.sections.every((x) => !x.groups) && rowIds(plain) === ALL, `${JSON.stringify(plain.groups)} ${rowIds(plain)}`);
  const two = view(SIGNED_STARTS);
  ok('Z2 a node a row: one row whichever groups reached it', rowIds(two) === ALL
    && two.sections.every((x) => new Set(x.rows.map((r) => r.id)).size === x.rows.length), rowIds(two));
  ok('Z3 reached by one group only: the other says missing',
    cell(two, 'die@1', 'd:1', GATE_IN, 1) === '[missing]' && cell(two, 'die@1', 'd:2', GATE_IN, 0) === '[missing]',
    `${cell(two, 'die@1', 'd:1', GATE_IN, 1)} | ${cell(two, 'die@1', 'd:2', GATE_IN, 0)}`);
  ok('Z4 reached but no value says so, not missing',
    cell(two, 'die@1', 'd:1', GATE_IN, 0) === TV.EMPTY && cell(two, 'die@1', 'd:2', GATE_IN, 1) === TV.EMPTY,
    `${cell(two, 'die@1', 'd:1', GATE_IN, 0)} | ${cell(two, 'die@1', 'd:2', GATE_IN, 1)}`);
  ok('Z5 a cell reads its group\'s edges only: the node both reached says each group\'s own value',
    cell(two, 'die@1', 'd:3', GATE_IN, 0) === '7' && cell(two, 'die@1', 'd:3', GATE_IN, 1) === '9',
    `${cell(two, 'die@1', 'd:3', GATE_IN, 0)} | ${cell(two, 'die@1', 'd:3', GATE_IN, 1)}`);
  ok('Z6 several edges in one group: every value, none overwritten', cell(two, 'die@1', 'd:4', GATE_IN, 0) === '2 values · 1 · 2',
    cell(two, 'die@1', 'd:4', GATE_IN, 0));
  const blind = view(SIGNED_STARTS, { ...SIGNED, propagation: null });
  ok('Z7 an answer that ranks nothing: one table, said to be both signs', blind.groups === null && blind.unsplit === true
    && rowIds(blind) === ALL, `${JSON.stringify(blind.groups)} ${blind.unsplit}`);
  const bare = view(SIGNED_STARTS, { ...SIGNED, edges: SIGNED.edges.map(({ qualifiers, ...e }) => e) });
  const bareDie = bare.sections.find((x) => x.type === 'die@1') || { heads: [], rows: [] };
  const d3 = bareDie.rows.find((r) => r.id === 'd:3') || { byGroup: [[], []] };
  const d1 = bareDie.rows.find((r) => r.id === 'd:1') || { byGroup: [[], []] };
  ok('Z8 a type with no column: how each group reached it - its last predicate and steps; missing where it did not',
    JSON.stringify([bareDie.heads, d3.byGroup.map((g) => g.map((c) => c.text)), d1.byGroup[1].map((c) => c.missing)])
      === JSON.stringify([['via', 'depth'], [['inspected', '1'], ['inspected', '1']], [true, true]]),
    JSON.stringify([bareDie.heads, d3.byGroup, d1.byGroup[1]]));
  const die = two.sections.find((x) => x.type === 'die@1') || { groups: [], heads: [], centreHeads: [], deltaHeads: [], rows: [] };
  const wafer = two.sections.find((x) => x.type === 'wafer@1') || { heads: [] };
  ok('Z11 an edge attribute\'s head: its predicate, «(in)» when taken in, and its name',
    JSON.stringify([die.heads, wafer.heads]) === JSON.stringify([[GATE_IN], ['inspected · gate']]), JSON.stringify([die.heads, wafer.heads]));
  ok('Z12 delta where both groups say one number: the first less the second; its head once',
    JSON.stringify([die.deltaHeads, die.rows.map((r) => r.deltas.map((d) => d.text).join())])
      === JSON.stringify([[TV.DELTA], ['', '', '−2', '']]), JSON.stringify([die.deltaHeads, die.rows.map((r) => r.deltas)]));
  ok('Z17 the node\'s own columns - the keys its rows carry - once in the centre, read off the row',
    JSON.stringify([die.centreHeads, (die.rows.find((r) => r.id === 'd:3') || { centre: [] }).centre.map((c) => c.text)])
      === JSON.stringify([['mat_id'], ['M-3']]), JSON.stringify(die.centreHeads));
  ok('Z20 a band a group: its starts and its rows', JSON.stringify(die.groups) === JSON.stringify([
    { sign: '+', starts: 2, count: 3 }, { sign: '−', starts: 1, count: 2 }]), JSON.stringify(die.groups));
  const added = new Map([['die@1', [{ steps: [{ predicate: 'inspected', direction: 'incoming' }], value: { on: 'key', name: 'wafer' },
    words: ['inspected (in) → wafer@1', 'wafer'] }]]]);
  const more = view(SIGNED_STARTS, SIGNED, added);
  ok('Z18 an added column: its route\'s far node, a column of each group',
    cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 0) === 'A' && cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 1) === 'B',
    `${cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 0)} ${cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 1)}`);
  ok('Z19 words: several values past the cap, and a difference without its float tail',
    JSON.stringify([TV.cellWords({ missing: false, values: [1, 2], more: true }).text, TV.deltaWords(0.22 - 0.3305), TV.deltaWords(19.5)])
      === JSON.stringify(['2+ values · 1 · 2', '−0.1105', '+19.5']), TV.deltaWords(0.22 - 0.3305));
};
qualifierSuite(await import('../src/walk/table_view.js'));
sideSuite(await import('../src/walk/table_view.js'));
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline with Q: ${ran} assertions`);
const base = { ran, names: NAMES.slice(), failed: failures.length };

// ═══ mutants ════════════════════════════════════════════════════════════════════════════
const MUTANTS = [
  { id: 'NZ1', what: 'the page draws no band a group', catches: 'Z9',
    from: '    thead.append(band, head);', to: '    thead.append(head);' },
  { id: 'NZ2', what: 'the Next row gone from above its table', catches: 'Z9',
    from: '      // Next above its table, once (lead 3375edd9b).\n      if (checks) sec.append(nextRow(at, section, checks));\n', to: '' },
  { id: 'NZ3', what: 'the Compare view back', catches: 'Z10',
    from: "    for (const [name, word] of [['table', 'Table'], ['graph', 'Graph']]) {",
    to: "    for (const [name, word] of [['table', 'Table'], ['graph', 'Graph'], ['compare', 'Compare']]) {" },
  { id: 'NZ4', what: 'the + side not reversed', catches: 'Z15',
    from: '      const heads = pair && i === 0 ? [...section.heads].reverse() : section.heads;', to: '      const heads = section.heads;' },
  { id: 'NZ5', what: 'the node first, not in the centre', catches: 'Z13',
    from: '    if (pair) { side(section.groups[0], 0); centre(); side(section.groups[1], 1); } else { centre(); section.groups.forEach(side); }',
    to: '    { centre(); section.groups.forEach(side); }' },
  { id: 'NZ6', what: 'the filter draws every row', catches: 'Z14',
    from: "(state.rowFilter === 'differs' ? row.differs : row.missing)", to: 'true' },
  // 🔴 THE ONE THE RULING ASKED FOR: a copy put back. Same sections, same rows, same counts.
  { id: 'M1', what: 'the renderer names its own columns again',
    catches: 'V2 the column labels',
    from: "      for (const column of section.columns) hr.append(el(doc, 'th', '', column.name));",
    to: "      for (const name of ['\\uae4a\\uc774', '\\ub77c\\ubca8', 'id'])"
      + " hr.append(el(doc, 'th', '', name));" },
  // 🔴 THIS SLOT HELD AN EQUIVALENT MUTANT, AND THE HARNESS SAID SO. It was `cell.text || ''`,
  //    meant to collapse 0 into a blank -- but `cell.text` is already a STRING and '0' is
  //    truthy, so it changed nothing and ESCAPED. The rule it aimed at (0 is a value, absent is
  //    a blank) moved into `table_view.valueText` with the half being scored, and the renderer
  //    no longer HAS a raw value to collapse. Re-anchored rather than chased with a weaker
  //    assertion: the cells drawn in the wrong order. Same count, nothing thrown.
  { id: 'M2', what: 'the cells are drawn in the wrong order',
    catches: 'V3 every cell is the view',
    from: '        for (const cell of row.cells) {',
    to: '        for (const cell of [...row.cells].reverse()) {' },
  { id: 'M3', what: 'the numeric class is dropped',
    catches: 'V5 the numeric class',
    from: "          const td = el(doc, 'td', cell.numeric ? 'wk-num' : '', cell.text);",
    to: "          const td = el(doc, 'td', '', cell.text);" },
  { id: 'M4', what: 'the cap note prints the total instead of what was hidden',
    catches: 'C3 the total is not what is printed',
    from: '      box.append(el(doc, \'div\', \'wk-note\', `${view.hidden} more not drawn`));',
    to: '      box.append(el(doc, \'div\', \'wk-note\', `${view.shown + view.hidden} more not drawn`));' },
  { id: 'M6', what: 'the type placeholder carries its text as its value again',
    catches: 'P1 picking the placeholder',
    from: "    none.value = '';\n", to: '' },
  // ── 29cee1d47 ────────────────────────────────────────────────────────────────────────
  { id: 'M7', what: 'the list is drawn from what touches the start type again, as before 10-06',
    catches: 'F1 defect@1',
    from: '  const followOptions = () => followChoices(allPredicates(), allPredicates(), state.follow);',
    to: '  const followOptions = () => followChoices(declaredPredicates().filter((p) => !state.type'
      + ' || (p.subjects || []).includes(state.type) || ((p.object || {}).types || []).includes(state.type))'
      + '.map((p) => p.name), allPredicates(), state.follow);' },
  { id: 'M11', what: 'a type change drops the ticks again',
    catches: 'F8 changing the type',
    from: '        Object.entries(state.keys).filter(([k]) => allowedKeys.has(k)));',
    to: '        Object.entries(state.keys).filter(([k]) => allowedKeys.has(k))); state.follow = new Set();' },
  { id: 'M8', what: 'a type picked opens no box',
    catches: 'F2 the seed field',
    from: '      void openSearch();\n', to: '' },
  // M9 (an empty list read as not read to the end) is the search box's now: node_search_harness NS5.
  // ── lead 53050a4ec: the table's continue ────────────────────────────────────────────────
  // The board's markingIntent on the walk page (lead 10-09).
  { id: 'SM2', what: 'the table walks the form\'s subject alone, not the starts', catches: 'S1',
    from: '    const asked = { ...spec(), ...(one ? { type: one.type, keys: { ...one.keys } } : {}), ...(signed ? starts : {}) };', to: '    const asked = spec();' },
  { id: 'SM3', what: 'a check takes no sign from Shift', catches: 'S3',
    from: "markings.toggle(checks, id, markingIntent(event).sign); render(); });", to: "markings.toggle(checks, id, SIGN.CASE); render(); });" },
  { id: 'SM4', what: 'Next drops the - rows', catches: 'S4',
    from: 'stepAlong({ positive: seeds.positive, negative: seeds.negative,', to: 'stepAlong({ positive: seeds.positive,' },
  { id: 'NM1', what: 'the Next walks from every row of the section, not the checked ones', catches: 'N2',
    from: '    const seeds = seedsOf(section.rows.map((row) => [row.id, markings.signOf(checks, row.id)]));',
    to: '    const seeds = { positive: section.rows.map((row) => row.id), negative: [] };' },
  { id: 'NM2', what: 'a press with nothing checked still asks', catches: 'N2',
    from: "      go.addEventListener('click', () => { if (seeds.positive.length) void walkOn(at, seeds, route); });",
    to: "      go.addEventListener('click', () => { void walkOn(at, seeds, route); });" },
  { id: 'NM3', what: 'the next step builds its own walk instead of the one step', catches: 'N4',
    from: '    const asked = stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to });',
    to: '    const asked = { positive: seeds.positive, follow: [route.predicate] };' },
  // stepAlong's own default ('both') is imported by main.js and not swapped by this loader; the call site stands in.
  { id: 'NM7', what: 'the Next walks one way only', catches: 'N8',
    from: '    const asked = stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to });',
    to: "    const asked = stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to, direction: 'outgoing' });" },
  { id: 'NM4', what: 'the checks are kept apart from the graph\'s marking', catches: 'N3',
    from: "  const checksOf = (at) => GRAPH_CHAIN[at + 1] || '';", to: '  const checksOf = (at) => `table-${at}`;' },
  { id: 'NM5', what: 'a new start keeps the steps', catches: 'N7',
    from: '    state.steps = []; state.at = 0;\n', to: '' },
  { id: 'NM6', what: 'a step pressed does not go back', catches: 'N6',
    from: "      b.addEventListener('click', () => { state.at = i; render(); });",
    to: "      b.addEventListener('click', () => { render(); });" },
  // 🔴 CONTROL: a comment cannot change an answer. If this reddens something, the harness is
  //    reading text rather than behaviour.
  { id: 'M5', what: 'CONTROL: a comment line is removed', control: true,
    from: '// 🔴 C-72. 표의 «결정»은 전부 여기 있고 이 파일에는 DOM 쓰기만 남습니다.',
    to: '//' },
];

const runMutant = async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(SRC, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  await suite(loaded.module);
  // 🔴 THE FIELD IS `failures`. Returning it as `failed` made every defect ESCAPE while the
  //    assertion it named was visibly red two lines above — the scorer reads one name, and
  //    a missing one is indistinguishable from 「nothing failed」.
  return { ran, names: NAMES.slice(), failures: failures.slice() };
};

const defects = await scoreMutants(MUTANTS.filter((m) => !m.control), runMutant,
  { baselineRan: suiteRan, baselineNames: base.names,
    title: `${LF}== defect mutants (each must be CAUGHT by the check it names) ==` });
const controls = await scoreMutants(MUTANTS.filter((m) => m.control), runMutant,
  { mustCatch: false, baselineRan: suiteRan, baselineNames: base.names,
    title: `${LF}== controls (each must wake NOTHING) ==` });

// table_view.js's own: the fold of several edges into one node.
const TV_SRC = path.join(HERE, '..', 'src', 'walk', 'table_view.js');
const TV_MUTANTS = [
  { id: 'ZM1', what: 'the rows only those the first group reached', catches: 'Z2',
    from: '  const members = nodes.filter((n) => groups.some((g) => g.inside.has(n.id)));',
    to: '  const members = nodes.filter((n) => groups[0].inside.has(n.id));' },
  { id: 'ZM2', what: 'the node\'s own columns a group\'s, not the centre\'s', catches: 'Z17',
    from: '    const centre = all.filter((c) => !c.steps.length);\n    const columns = all.filter((c) => c.steps.length);',
    to: '    const centre = [];\n    const columns = all;' },
  { id: 'ZM3', what: 'groups even without a - start', catches: 'Z1 ',
    from: '  const groups = negative.length\n    ? groupsOf(', to: '  const groups = true\n    ? groupsOf(' },
  { id: 'ZM4', what: 'no delta column', catches: 'Z12',
    from: '  const deltas = groups.length === 2 ? columns.map', to: '  const deltas = false ? columns.map' },
  { id: 'ZM5', what: 'reached but no value drawn missing', catches: 'Z4',
    from: '  if (!values.length) return { text: EMPTY };', to: '  if (!values.length) return { text: MISSING, missing: true };' },
  { id: 'ZM6', what: 'several values: the first alone', catches: 'Z6',
    from: '  if (values.length === 1 && !cell.more)', to: '  if (values.length >= 1 && !cell.more)' },
  { id: 'ZM7', what: 'a type with no column draws no cell a group', catches: 'Z8',
    from: ": ['via', 'depth'];", to: ": [];" },
  { id: 'ZM8', what: 'an added column dropped', catches: 'Z18',
    from: ', ...(added.get(type) || [])];', to: '];' },
  { id: 'ZM9', what: 'a difference keeps its float tail', catches: 'Z19',
    from: '  const n = Number(delta.toPrecision(10));', to: '  const n = delta;' },
  { id: 'QM1', what: 'several edges into one node: the last edge\'s value wins again', catches: 'Q1',
    from: "      said[name] = list.length === 1 ? list[0].value\n", to: "      said[name] = list.length >= 1 ? list[list.length - 1].value\n" },
];
const tv = await scoreMutants(TV_MUTANTS, async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(TV_SRC, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  qualifierSuite(loaded.module);
  sideSuite(loaded.module);
  return { ran, names: NAMES.slice(), failures: failures.slice() };
}, { baselineNames: base.names, title: `${LF}== table_view mutants (each must be CAUGHT by the check it names) ==` });

const all = MUTANTS.length + TV_MUTANTS.length;
const scored = all - defects.wrong - controls.wrong - tv.wrong;
console.log(`${LF}  ${scored}/${all} scored as intended.`);
const failed = base.failed + (all - scored);
console.log(`ASSERTIONS ${base.ran + all} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
