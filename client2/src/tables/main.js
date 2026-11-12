// THE TABLES PAGE (owner 11-06, lead L1; the walk from table to table owner 11-11): the first table opened from the grid
// with its narrowing (its «Tables» button, handoff.js) or by its address and a search; its rows marked + and − (Shift),
// each sign walked to the next table and on (chain.js - one reach a hop, the rows kept as server markings), and the last
// table's + rows and − rows compared in one table (axis_compare.js). The page places the parts; each draws in its own div.
import '../tokens.css';
import '../base.css';
import '../spotfire.css';
import '../testbed/testbed.css';
import './tables.css';
import { API_BASE } from '../config.js';
import { MarkingStore, SIGN, nextName, labelOf } from '../rnd_board/marking_store.js';
import { fetchDeclaration } from '../rnd_board/api.js';
import { withWorld } from '../world.js';
import { handoffRead } from './handoff.js';
import { TableBox, PAGE_ROWS } from './table_box.js';
import { rowNodeId, rowOfNodeId, routesBetween, routeWords, keepRows, reachRows, rowsOf } from './chain.js';
import { AxisCompare, SIDE_WORDS } from './axis_compare.js';

const doc = document;
const from = doc.getElementById('tables-from');
const mount = doc.getElementById('tables-board');
const picker = doc.getElementById('tables-table');
const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };

const asked = handoffRead(window.localStorage, window.location.search);
const markings = new MarkingStore();
const fetchImpl = (url, init) => window.fetch(url, init);
const deps = { fetch: fetchImpl, apiBase: API_BASE, world: asked.world };
const SIGNS = [SIGN.CASE, SIGN.CONTROL];

const sayEl = el('p', 'tables-say');
const stepsEl = el('div', 'tables-steps');
const compareEl = el('div', 'tables-compare-host');
compareEl.hidden = true;
mount.replaceChildren(sayEl, stepsEl, compareEl);

/**
 * THE QUERY (lead 11-11: what the person picked, in one object - kept as a declaration one day): the first table and its
 * narrowing, its marked rows [[row id, sign]], the hops {type, follow, to}, the compare's picks. The page is drawn from
 * it (`run`); everything else here is what the server answered for it.
 */
let query = null;
/** What the server answered for the query: a step a table - the first its marking name, a hop's its sides
 *  {sign, name, kept: server marking id | null, from, to, capped}. */
let chain = [];
/** The marks the hops were walked from - another set and «Walk again» shows. */
let walkedMarks = '[]';
let asking = 0;
/** The first step's column (drawn once a query) and the next-table bar (under the last step). */
let firstColumn = null;
let barEl = null;
let unwatchMarks = null;
let tables = [];
let declaration = null;

const compare = new AxisCompare(compareEl, { doc, onPick: ({ axes, columns, only }) => Object.assign(query, { axes, columns, only }) });
const countText = (n) => Number(n || 0).toLocaleString('en-US');
const startName = () => chain[0].name;
const marksNow = () => markings.entries(startName()).map(([id, sign]) => [rowOfNodeId(id).rowId, sign]);

/** Every name and server marking the answer holds let go. */
function dropChain() {
  for (const step of chain) {
    for (const name of [step.name, ...(step.sides || []).map((s) => s.name)].filter(Boolean)) markings.clear(name, { drop: true });
    for (const id of step.kept || []) fetchImpl(`${API_BASE}/markings/${encodeURIComponent(id)}`, { method: 'DELETE' }).catch(() => {});
  }
  chain = [];
}

function boxIn(column, table, extra) {
  const host = el('div', 'tables-step__box');
  column.append(host);
  const box = new TableBox(host, { doc, fetch: fetchImpl, apiBase: API_BASE, table, world: asked.world, ...extra });
  box.open();
  return box;
}

/** The next-table bar under the last step: the table, the path (picked when more than one), Open. */
function nextBar(column) {
  const bar = el('div', 'tables-next');
  barEl = bar;
  const label = el('label', 'tables-box__label', 'Next table');
  const table = el('select', 'ctl-small');
  table.id = `tables-next-${chain.length}`;
  label.htmlFor = table.id;
  table.append(...['', ...tables].map((t) => { const o = el('option', '', t || 'Pick a table'); o.value = t; return o; }));
  const path = el('span', 'tables-next__path');
  const open = el('button', 'btn btn-primary ctl-small', 'Open');
  open.type = 'button';
  let route = null;
  open.disabled = !route;
  const say = el('span', 'tables-next__say');
  table.addEventListener('change', () => {
    const routes = table.value && declaration ? routesBetween(declaration, chain[chain.length - 1].table, table.value) : [];
    route = routes.length === 1 ? routes[0] : null;
    say.textContent = table.value && !routes.length ? (declaration && declaration.sources ? 'No path between these tables' : 'Declaration unread') : '';
    if (routes.length > 1) {
      const pick = el('select', 'ctl-small');
      pick.append(el('option', '', `Pick a path (${routes.length})`), ...routes.map((r, k) => { const o = el('option', '', routeWords(r)); o.value = String(k); return o; }));
      pick.firstChild.value = '';
      pick.addEventListener('change', () => { route = pick.value === '' ? null : routes[Number(pick.value)]; open.disabled = !route; });
      path.replaceChildren(pick);
    } else path.replaceChildren(route ? el('span', 'tables-next__route', routeWords(route)) : '');
    open.disabled = !route;
  });
  open.addEventListener('click', () => {
    open.disabled = true;
    query.hops.push({ type: route.type, follow: route.follow, to: table.value });
    walk(chain.length);
  });
  bar.append(label, table, path, open, say);
  column.append(bar);
}

/** The first step: its box, and «Walk again» when its marks are not the ones the hops were walked from. */
function drawFirst() {
  firstColumn = el('div', 'tables-step');
  if (firstBox && firstBox.unsubscribe) firstBox.unsubscribe();
  firstBox = boxIn(firstColumn, chain[0].table, { narrowing: query.narrowing, markings, writes: startName(), title: labelOf(startName()) });
  const bar = el('div', 'tables-next');
  const again = el('button', 'btn ctl-small', 'Walk again');
  again.type = 'button';
  againShow = () => { bar.hidden = !query.hops.length || JSON.stringify(marksNow()) === walkedMarks; };
  again.addEventListener('click', () => walk(1));
  if (unwatchMarks) unwatchMarks();
  unwatchMarks = markings.subscribe(startName(), () => { query.marks = marksNow(); againShow(); });
  bar.append(again);
  againShow();
  firstColumn.append(bar);
}
let againShow = () => {};
let firstBox = null;

/** The steps past the first drawn again, the next-table bar under the last. */
function drawChain() {
  if (barEl) barEl.remove();
  stepsEl.replaceChildren(firstColumn);
  chain.forEach((step, k) => {
    let column = firstColumn;
    if (k > 0) {
      column = el('div', 'tables-step');
      stepsEl.append(column);
      const hop = query.hops[k - 1];
      for (const side of step.sides) {
        const title = `${labelOf(side.name)} ${SIDE_WORDS[side.sign]} · ${countText(side.from)} → ${countText(side.to)}${side.capped ? '+' : ''} rows · ${routeWords(hop)}`;
        if (side.kept) boxIn(column, step.table, { marking: side.kept, title });
        else column.append(el('div', 'tables-step__none', `${title} · no rows`));
      }
    }
    if (k === chain.length - 1) nextBar(column);
  });
  againShow();
}

/** The query's hops from hop `k` (1: the first) walked - a sign at a time, each hop one reach - the chain past it
 *  dropped first; the steps and the compare drawn. A refusal: its sentence said, the query's hops cut to where the chain
 *  stood. */
async function walk(k) {
  const ticket = (asking += 1);
  sayEl.textContent = 'Reaching…';
  for (const step of chain.splice(k)) {
    for (const s of step.sides) markings.clear(s.name, { drop: true });
    for (const id of step.kept) fetchImpl(`${API_BASE}/markings/${encodeURIComponent(id)}`, { method: 'DELETE' }).catch(() => {});
  }
  try {
    for (let at = k; at <= query.hops.length; at += 1) {
      const hop = query.hops[at - 1];
      const last = chain[at - 1];
      const sides = [];
      const kept = [];
      for (const sign of SIGNS) {
        let marking = null;
        let fromCount = 0;
        if (at === 1) {
          const ids = query.marks.filter(([, s]) => s === sign).map(([id]) => id);
          fromCount = ids.length;
          if (ids.length) { marking = (await keepRows(deps, last.table, ids)).id; kept.push(marking); }
        } else {
          const side = last.sides.find((s) => s.sign === sign);
          marking = side.kept;
          fromCount = side.to;
        }
        const reached = marking ? await reachRows(deps, marking, hop, hop.to) : { rows: [], count: { capped: false } };
        const name = nextName(markings);
        markings.replace(name, reached.rows.map((id) => [rowNodeId(hop.to, id), sign]));
        const held = reached.rows.length ? (await keepRows(deps, hop.to, reached.rows)).id : null;
        if (held) kept.push(held);
        sides.push({ sign, name, kept: held, from: fromCount, to: reached.rows.length, capped: Boolean(reached.count && reached.count.capped) });
      }
      if (ticket !== asking) return null;
      chain.push({ table: hop.to, sides, kept });
    }
    walkedMarks = JSON.stringify(query.marks);
  } catch (err) {
    if (ticket !== asking) return;
    query.hops.length = chain.length - 1;
    sayEl.textContent = err.message;
    drawChain();
    return;
  }
  sayEl.textContent = '';
  drawChain();
  await readCompare(ticket);
}

/** The last step's + and − rows into the compare, as flat rows of the table's columns, with the query's picks. */
async function readCompare(ticket) {
  compareEl.hidden = chain.length < 2;
  if (chain.length < 2) return;
  const step = chain[chain.length - 1];
  const schemaRes = await fetchImpl(`${API_BASE}/tables/${encodeURIComponent(step.table)}/schema`);
  const schema = schemaRes.ok ? await schemaRes.json() : { columns: [] };
  const columns = (schema.columns || []).filter((c) => c !== 'row_id');
  const types = schema.column_types || {};
  const kinds = Object.fromEntries(columns.map((c) => [c, types[c] === 'number' ? 'number' : 'text']));
  const flat = (row) => Object.fromEntries(columns.map((c) => [c, row.data && row.data[c] ? row.data[c].value : (row[c] ?? null)]));
  const sides = [];
  // every row of each side - the compare folds them all
  for (const side of step.sides) sides.push({ sign: side.sign, rows: side.kept ? (await rowsOf({ ...deps, world: asked.world }, step.table, side.kept, PAGE_ROWS)).map(flat) : [] });
  if (ticket !== asking) return;
  compare.show({ title: step.table, sides, columns, kinds, axes: query.axes, shown: query.columns, only: query.only });
}

/** The page drawn from a query: its first table with its marks, then its hops walked. */
async function run(q) {
  dropChain();
  asking += 1;
  query = q;
  const name = nextName(markings);
  markings.replace(name, q.marks.map(([id, sign]) => [rowNodeId(q.table, id), sign]));
  chain = [{ table: q.table, name, sides: [], kept: [] }];
  walkedMarks = JSON.stringify(q.marks);
  compareEl.hidden = true;
  sayEl.textContent = '';
  drawFirst();
  drawChain();
  if (q.hops.length) await walk(1);
}

const queryFor = (table, narrowing = '') => ({ table, narrowing, marks: [], hops: [], axes: [], columns: [], only: false });

async function start() {
  const res = await window.fetch(`${API_BASE}/tables`);
  tables = res.ok ? ((await res.json()).tables || []) : [];
  declaration = await fetchDeclaration({ apiBase: API_BASE, fetchImpl: withWorld(fetchImpl, () => asked.world) });
  if (!declaration.ok) declaration = null;
  picker.replaceChildren(...['', ...tables].map((t) => {
    const o = doc.createElement('option');
    o.value = t;
    o.textContent = t || 'Pick a table';
    return o;
  }));
  picker.addEventListener('change', () => {
    if (!picker.value) return;
    window.history.replaceState(null, '', `?table=${encodeURIComponent(picker.value)}`);
    from.hidden = true;
    run(queryFor(picker.value));
  });
  if (asked.table && tables.includes(asked.table)) {
    picker.value = asked.table;
    from.hidden = !asked.handed;
    run(queryFor(asked.table, asked.narrowing));
  }
}

start();
