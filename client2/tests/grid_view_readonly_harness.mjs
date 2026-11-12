/**
 * grid_view_readonly -- a table the catalogue calls a VIEW offers no write control, and a cell
 * with no layering marker draws no badge.
 *
 * WHY THIS EXISTS (C-84). The main grid made every stored column editable (`editable: !isSystem`)
 * and the three write funnels guarded per COLUMN only, so on a relation the server serves as a
 * view the operator could open an editor, paste, clear or bulk-fill and meet the server's refusal in
 * the cell. The catalogue now says which it is (`/tables/<n>/schema.kind`, S-187), so the client
 * can stop offering the write instead of discovering it is refused.
 *
 * ⚠️ S-224 (2026-09-13) made every one of those six routes answer 422 WITH THE REASON in
 *    `detail` (the cell-update route moved 400 -> 422). Nothing here asserts a status code --
 *    what G scores is that the reason REACHES THE SCREEN rather than being folded away.
 *
 * WHAT IT SCORES:
 *   P  the predicate: only the word 'view' is a view. '' (old server / not yet read) is NOT
 *   A  the wire: `loadSchema` records `kind`, and only when the server sent a string
 *   B  edit entry: on a view every column is `editable: false`; on a table nothing changed
 *   C  the three write funnels (paste, clear, bulk fill) issue NO write on a view -- and DO
 *      issue one on a table, so C is not vacuous -- and each says why on screen
 *   D  a cell carrying no marker draws no badge, and a cell carrying one still does
 *   E  the two source rows draw no pin/delete when the caller says the table is not writable
 *   F  the FOURTH funnel (C-102 ①): 「행 추가」 writes nothing on a view, says why in the same one
 *      spelling, still writes on a table -- and the control itself stops being clickable
 *   G  a refusal is the SERVER's sentence (C-102 ②), and a `detail` that is not one does not
 *      become 「[object Object]」 on the screen
 *   R  a refused READ is an answer, not an exception (C-105): the page's data fetch draws the
 *      server's sentence, empties the grid, and says 「not counted」 rather than 「0」; a STOPPED read
 *      (503, its sentence in `detail.message`, 87dfa71d7) toasts that sentence, keeps the column filter, asks once;
 *      the row jump's refusal is worded by the same seat (J)
 *   W  the row delete WAITS VISIBLY (a0ae05b60): its button off with a reason, the seconds
 *      counted, no second request, the rows removed on the answer, the server's refusal + next step
 *   L  a ledger receipt line (43a738d58) shows its transaction's rows and stops — no row jump; one
 *      with no transaction says why; any other line still jumps to its row
 *   N  the cells a save's answer did not write (lead 10-29): paste, clear, fill, edit and Apply each toast the
 *      server's `dropped.said` as it wrote it, the cells and columns when it sent none, nothing when nothing dropped
 *   V  a number column's value as it was given (lead 10-29 ㄷ): paste, pasted table, edit and the cell's setter send the
 *      text (1e999 · NaN · 1,234 · -0) without stopping, a blank as no value, Infinity as its text (`cellToSend`)
 *   S  ONE RULE (C-107): every write control on this screen is armed from the same answer, the
 *      four funnels ask that same answer, and the table says what it is in its own header
 *
 * 🔴 NOT INFERRED FROM THE DATA SHAPE. A view cell is `{value}` only -- and so is a page of an
 *    ordinary table nobody has overwritten. Reading the shape would turn a healthy table
 *    read-only, which is a proxy standing in for a property. The answer comes off the catalogue.
 *
 * 🔴 SIX SEATS, ONE PREDICATE, ONE FIXTURE. That is the point of the gate: the same staged
 *    schema is asked at every seat, because a per-seat answer is how two spellings of one rule
 *    start to diverge (criterion ④).
 *
 * IT IMPORTS ITS SUBJECTS. Mutants are whole modules (`lib/probe.mjs`); one file is swapped per
 * run and the rest stay real, which is also why a `state.js` mutant is scored through P (its copy
 * carries its own state object and the real modules cannot see it).
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import path from 'node:path';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const FILE = (name) => path.join(SRC, name);

// ── the DOM the modules touch, whole enough to be believed ──────────────────────────────
const nodes = new Map();
function fakeNode(id) {
  return {
    id, innerHTML: '', textContent: '', value: '', checked: false,
    style: {}, dataset: {},
    // 🔴 `toggle` 이 «없으면» 그것을 부르는 코드가 던집니다 — 그리고 그 던짐은 대개 바깥
    //    `catch` 가 먹어서 «조용합니다»(실측: `setMatchCount` 때문에 `fetchData` 의 개수
    //    이후가 성공 경로에서도 한 번도 안 돌았습니다). 브라우저가 하는 대로: 넣고·빼고·
    //    «지금 상태»를 답합니다.
    classList: {
      _s: new Set(),
      add(...names) { for (const x of names) this._s.add(x); },
      remove(...names) { for (const x of names) this._s.delete(x); },
      contains(name) { return this._s.has(name); },
      toggle(name, on) {
        const want = on === undefined ? !this._s.has(name) : !!on;
        if (want) this._s.add(name); else this._s.delete(name);
        return want;
      },
    },
    children: [],
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, removeEventListener() {},
    querySelector: () => null, querySelectorAll: () => [],
    // 🔴 C-102. 속성을 «듭니다». 종전에는 쓰기가 무음이고 읽기가 언제나 null 이라 「버튼이
    //    사유를 단다」를 잴 수 없었고, `removeAttribute` 는 아예 «없어서» 그것을 부르는
    //    부품이 하니스에서만 던집니다 — 스텁에 없는 철자는 재는 것이 아니라 막는 것입니다.
    attrs: {},
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    removeAttribute(k) { delete this.attrs[String(k)]; },
    hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)); },
    focus() {}, blur() {}, remove() {}, insertAdjacentHTML() {},
  };
}
const listeners = new Map();
// 🔴 A WINDOW, BECAUSE `switchTable` STARTS BY WRITING TO ONE (`window.currentTable`, which the
//    desktop wrapper reads). Without it that function died on its SECOND line, so every seat in
//    this file was scored by calling `loadSchema` directly -- which cannot see WHEN something is
//    called. `location` rides along because `config.js` and `state.js` read it when it exists,
//    and each mutant re-imports its copy.
globalThis.window = {
  currentTable: null,
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
};
globalThis.document = {
  hidden: false, activeElement: null, body: fakeNode('body'),
  getElementById: (id) => {
    if (!nodes.has(id)) nodes.set(id, fakeNode(id));
    return nodes.get(id);
  },
  // A toast paints its words into the child it finds by class (utils.js paintToast); null here kept every toast empty.
  createElement: () => {
    const n = fakeNode('created');
    n.querySelector = (sel) => (String(sel).startsWith('.')
      ? n.children.find((c) => String(c.className || '').split(/\s+/).includes(String(sel).slice(1))) || null : null);
    return n;
  },
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener: (type, fn) => {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(fn);
  },
  removeEventListener() {},
};
const log = () => document.getElementById('performance-log');
const toastTexts = () => document.getElementById('toast-container').children
  .map((el) => (el.children.find((c) => c.className === 'toast-body') || {}).textContent);
// Each run's stopped sentence is its own, so a toast an earlier run left up cannot answer for this one.
let stopRun = 0;

// ── the wire, measured 2026-09-13 on the live box (PID 43720) ───────────────────────────
//    `/tables/ledger_events/schema` -> `kind: "view"`; `/tables/dt_log/schema` -> `"table"`.
const COLUMNS = ['id', 'qty', 'note', 'created_at', 'updated_at'];
const schemaBody = (kind) => {
  const body = {
    table_name: 't', columns: COLUMNS.slice(),
    column_types: { id: 'string', qty: 'number', note: 'string' },
    business_key: 'id', composite_key_source: [],
    virtual_columns: [], join_resolved_columns: [],
  };
  if (kind !== undefined) body.kind = kind;
  return body;
};
const rowData = () => ({
  row_id: 'R0', created_at: null, updated_at: null,
  data: { id: { value: 'R0' }, qty: { value: 1 }, note: { value: 'x' } },
});

// ── the fetch spy: every write is counted, every read answers the staged schema ──────────
let staged = schemaBody('view');
let writes = [];
// C-102 ②. 서버가 «거절»할 때 무엇이 화면에 서는가 — S-224 뒤 뷰 쓰기는 여섯 라우트 전부
// 422 + `detail` 문장이다. `null` 이면 종전대로 전부 성공한다.
let refusal = null;
// C-105. 읽기도 거절됩니다 — 실경로에서 잡힌 것이 그것입니다(`/data` 가 422 로 이름을 대고
// 거절). `/schema` 는 건드리지 않습니다: 그 읽기가 먼저 성공해야 표가 서기 때문입니다.
let readRefusal = null;
globalThis.fetch = async (url, opts = {}) => {
  const method = String(opts.method || 'GET').toUpperCase();
  if (method !== 'GET') writes.push({ url: String(url), method });
  if (method === 'GET' && readRefusal && String(url).includes('/data?')) {
    return {
      ok: false, status: readRefusal.status,
      json: async () => readRefusal.body, text: async () => JSON.stringify(readRefusal.body),
    };
  }
  if (method !== 'GET' && refusal) {
    return {
      ok: false, status: refusal.status,
      json: async () => refusal.body, text: async () => JSON.stringify(refusal.body),
    };
  }
  return {
    ok: true, status: 200,
    json: async () => (String(url).endsWith('/schema') ? staged : { data: [], total: 0 }),
    text: async () => '',
  };
};

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

const REAL = {
  state: await import('../src/state.js'),
  guard: await import('../src/write_guard.js'),
  api: await import('../src/api.js'),
  refusal: await import('../src/refusal.js'),
  grid: await import('../src/grid.js'),
  clipboard: await import('../src/clipboard.js'),
  ui: await import('../src/ui.js'),
  rows: await import('../src/source_rows.js'),
  timeline: await import('../src/timeline.js'),
  ws: await import('../src/websocket.js'),
  keys: await import('../src/rows_key.js'),
};
const realState = REAL.state.state;

/** Stage a table of the given kind through the REAL `loadSchema`, and hand back the grid api. */
async function stageThrough(api, kind) {
  staged = schemaBody(kind);
  realState.currentTable = 't';
  realState.pageCache = new Map();
  await api.loadSchema('t');
  realState.selectedCellsMap = { '0_note': { rowIndex: 0, colId: 'note' } };
  realState.dragStartCell = null;
  realState.dragEndCell = null;
  realState.txModeActive = false;
  realState.pendingTxEdits = {};
  realState.visibleColIndexMap = Object.fromEntries(COLUMNS.map((c, i) => [c, i]));
  realState.smartPasteArmedUntil = 0;
  realState.gridApi = {
    getFocusedCell: () => null,
    getColumnState: () => COLUMNS.map((c) => ({ colId: c, hide: false })),
    getColumns: () => COLUMNS.map((c) => ({ getColId: () => c })),
    getDisplayedRowAtIndex: (i) => (i === 0 ? { data: rowData(), id: 'R0' } : null),
    getRowNode: () => ({ data: rowData() }),
    getSelectedNodes: () => [],
    applyTransaction() {}, refreshCells() {}, setGridOption() {}, redrawRows() {},
    forEachNode() {}, getDisplayedRowCount: () => 1, ensureIndexVisible() {},
    getEditingCells: () => [], stopEditing() {}, getColumn: () => null,
    applyColumnState() {}, setFilterModel() {}, getFilterModel: () => ({}),
    onFilterChanged() {}, refreshHeader() {}, getGridOption: () => undefined,
  };
  return realState;
}

/** Run one funnel and report how many writes it issued. */
async function countWrites(run) {
  writes = [];
  log().textContent = '';
  try { await run(); } catch (e) { /* a funnel may walk further than this stub goes */ }
  return { writes: writes.filter((w) => w.method !== 'GET').length, note: log().textContent };
}

function pasteEvent(text) {
  return {
    preventDefault() {}, stopPropagation() {},
    clipboardData: { getData: () => text, items: [], files: [] },
  };
}

async function funnelRuns(M, kind) {
  await stageThrough(M.api, kind);
  listeners.clear();
  M.clipboard.setupClipboardHandlers();
  const onPaste = (listeners.get('paste') || [])[0];
  const paste = onPaste
    ? await countWrites(() => onPaste(pasteEvent('9')))
    : { writes: -1, note: 'NO PASTE LISTENER' };

  await stageThrough(M.api, kind);
  const clear = await countWrites(() => M.clipboard.clearSelectedCells());

  await stageThrough(M.api, kind);
  const fill = await countWrites(() => M.ui.applyValueToSelectedRange('9'));
  return { paste, clear, fill };
}

async function suite(M) {
  const before = { pass, fail };

  // ── P: the predicate itself, on the state object of the module under test ─────────────
  const S = M.state;
  S.state.currentTableKind = 'view';
  ok(S.tableIsView() === true, 'P1 the word `view` is a view');
  S.state.currentTableKind = 'table';
  ok(S.tableIsView() === false, 'P2 a table is not');
  S.state.currentTableKind = '';
  ok(S.tableIsView() === false,
    'P3 NOT ANNOUNCED is not a view -- an old server must not make a table read-only');

  // ── A: the wire ──────────────────────────────────────────────────────────────────────
  await stageThrough(M.api, 'view');
  ok(realState.currentTableKind === 'view', 'A1 loadSchema records the served kind');
  await stageThrough(M.api, 'table');
  ok(realState.currentTableKind === 'table', 'A2 ... including `table`');
  await stageThrough(M.api, undefined);
  ok(realState.currentTableKind === '',
    'A3 a schema with no `kind` leaves it empty, not undefined and not a view');
  await stageThrough(M.api, { not: 'a string' });
  ok(realState.currentTableKind === '',
    'A4 a non-string `kind` is refused -- only a string the server spelled counts');

  // ── B: edit entry ────────────────────────────────────────────────────────────────────
  await stageThrough(M.api, 'view');
  const viewDefs = M.grid.buildColumnDefs().filter((d) => d.field);
  ok(viewDefs.length > 0 && viewDefs.every((d) => d.editable === false),
    `B1 on a view EVERY column is editable:false -- ${viewDefs.filter(d => d.editable !== false).length} were not`);
  await stageThrough(M.api, 'table');
  const tableDefs = M.grid.buildColumnDefs().filter((d) => d.field);
  const systemish = ['created_at', 'updated_at', 'row_id', 'id', 'updated_by'];
  ok(tableDefs.some((d) => !systemish.includes(d.field) && d.editable === true),
    'B2 on a table the data columns are still editable -- no regression');
  ok(tableDefs.filter((d) => systemish.includes(d.field)).every((d) => d.editable === false),
    'B3 ... and a system column stays read-only, as before');
  // ROW_ID alone gets the column filter (owner 10-02, lead e67ef53f3). The staged schema carries
  // every system column here, so each one is asked.
  const shownColumns = realState.currentColumns;
  realState.currentColumns = [...COLUMNS, 'row_id', 'updated_by'];
  const sysDefs = Object.fromEntries(M.grid.buildColumnDefs().filter((d) => d.field).map((d) => [d.field, d]));
  realState.currentColumns = shownColumns;
  ok(sysDefs.row_id && (sysDefs.row_id.filter || {}).name === 'ValueFilter' && sysDefs.row_id.filterParams.kind === 'text'
    && sysDefs.row_id.floatingFilter === true
    && sysDefs.row_id.editable === false,
    `B4 ROW_ID has the text filter under its head, and stays read-only [${JSON.stringify(sysDefs.row_id && [(sysDefs.row_id.filter || {}).name, sysDefs.row_id.filterParams && sysDefs.row_id.filterParams.kind, sysDefs.row_id.floatingFilter, sysDefs.row_id.editable])}]`);
  const closed = ['created_at', 'updated_at', 'id', 'updated_by'].filter((c) => sysDefs[c]);
  ok(closed.length === 4 && closed.every((c) => sysDefs[c].filter === false && sysDefs[c].floatingFilter === false),
    `B5 ... and the other system columns still have none [${closed.map((c) => `${c}:${sysDefs[c].filter}`).join(' ')}]`);
  {
    const asked = [];
    const savedB = globalThis.fetch;
    globalThis.fetch = (url, opts) => { asked.push(String(url)); return savedB(url, opts); };
    const model = { row_id: { filterType: 'text', type: 'startsWith', filter: '01a0fb' } };
    const savedModel = realState.gridApi.getFilterModel;
    realState.gridApi.getFilterModel = () => model;
    try { await M.api.fetchData(true); } finally {
      realState.gridApi.getFilterModel = savedModel;
      globalThis.fetch = savedB;
    }
    const page = asked.find((u) => u.includes('/tables/t/data?'));
    const sent = page ? new URL(page, 'http://box').searchParams.get('filters') : null;
    ok(sent === JSON.stringify(model),
      `B6 a ROW_ID filter rides the page read as the grid's narrowing, unchanged [${sent}]`);
  }

  // ── C: the three write funnels ────────────────────────────────────────────────────────
  const onView = await funnelRuns(M, 'view');
  ok(onView.paste.writes === 0, `C1 a paste into a view writes nothing -- ${onView.paste.writes} request(s)`);
  ok(onView.clear.writes === 0, `C2 delete-to-clear writes nothing -- ${onView.clear.writes} request(s)`);
  ok(onView.fill.writes === 0, `C3 bulk fill writes nothing -- ${onView.fill.writes} request(s)`);
  const NOTE = REAL.state.VIEW_READ_ONLY_NOTE;
  ok(onView.paste.note === NOTE && onView.clear.note === NOTE && onView.fill.note === NOTE,
    'C4 each refusal says WHY, in one spelling -- a silent no-op is a failure with no subtitle');

  const onTable = await funnelRuns(M, 'table');
  ok(onTable.paste.writes > 0, `C5 the same paste on a TABLE does write -- ${onTable.paste.writes} request(s)`);
  ok(onTable.clear.writes > 0, `C6 ... and so does the clear -- ${onTable.clear.writes} request(s)`);
  ok(onTable.fill.writes > 0, `C7 ... and the bulk fill -- ${onTable.fill.writes} request(s)`);

  // ── D: no marker, no badge ───────────────────────────────────────────────────────────
  await stageThrough(M.api, 'view');
  const noteDef = M.grid.buildColumnDefs().find((d) => d.field === 'note');
  const rules = (noteDef && noteDef.cellClassRules) || {};
  const paintNames = Object.keys(rules).filter((k) => k !== 'custom-range-selected');
  const bare = { data: { row_id: 'R0', data: { note: { value: 'x' } } }, node: { rowIndex: 0 } };
  ok(paintNames.length > 0 && paintNames.every((k) => rules[k](bare) !== true),
    `D1 a cell with no marker draws no badge -- rules [${paintNames.join(', ')}]`);
  // a staged edit is the marker - a person's overwrite has no built-in paint since the colour rules every table has
  // (on the state the grid imports - a mutated state.js copy is not the grid's)
  const pending = realState.pendingTxEdits;
  realState.pendingTxEdits = { R0_note: { value: 'y' } };
  ok(paintNames.some((k) => rules[k](bare) === true),
    'D2 a cell that DOES carry a marker (a staged edit) still draws one -- D1 is not vacuous');
  realState.pendingTxEdits = pending;

  // ── E: the source rows ───────────────────────────────────────────────────────────────
  const hasBtns = (html) => /class="[^"]*pin-btn/.test(html) || /class="[^"]*del-btn/.test(html);
  ok(!hasBtns(M.rows.sourceRowHtml('excel', { value: 1 }, { isPinned: false, writable: false })),
    'E1 one cell`s row draws no pin/delete when the table is not writable');
  ok(hasBtns(M.rows.sourceRowHtml('excel', { value: 1 }, { isPinned: false, writable: true })),
    'E2 ... and draws both when it is');
  ok(!hasBtns(M.rows.sourceRowAllHtml('excel', ['a'], { isPinnedAll: false, writable: false })),
    'E3 the selection`s row likewise');
  ok(hasBtns(M.rows.sourceRowAllHtml('excel', ['a'], { isPinnedAll: false, writable: true })),
    'E4 ... and likewise draws both when writable');
  ok(!hasBtns(M.rows.sourceRowHtml('excel', { value: 1 }, { isPinned: false })),
    'E5 a caller that says NOTHING gets no write control -- the quiet half is the safe one');

  // ── F: the fourth funnel (C-102 ①) ───────────────────────────────────────────────────
  // 🔴 THE OWNER HIT THIS ONE: [행 추가] on a view, and the request went to the server (500 in
  //    the console, 「Create failed」 and nothing else). Measured: `tableIsView()` had SIX
  //    consumers and this button was not one of them -- the catalogue's `kind` was on the wire
  //    the whole time (A1-A4 above), so nothing was missing except the question.
  await stageThrough(M.api, 'view');
  const addOnView = await countWrites(() => M.api.addRows(1));
  ok(addOnView.writes === 0,
    `F1 adding a row to a view writes nothing -- ${addOnView.writes} request(s)`);
  ok(addOnView.note === NOTE,
    `F2 ... and says why, in the SAME one spelling as the other three [${addOnView.note}]`);
  await stageThrough(M.api, 'table');
  const addOnTable = await countWrites(() => M.api.addRows(1));
  ok(addOnTable.writes > 0,
    `F3 the same call on a TABLE does write -- F1 is not vacuous (${addOnTable.writes})`);
  // 🔴 AND THE VISIBLE HALF. A refusal the operator meets AFTER clicking is a refusal they
  //    earned by being offered the control; the button stops being clickable when the table
  //    the page just loaded is a view.
  const addBtn = document.getElementById('add-row-btn');
  addBtn.disabled = false;
  staged = schemaBody('view');
  realState.currentTable = 't';
  // ⚠️ `switchTable` walks further than this stub goes (grid, history, badges). What is scored
  //    is that the guard runs BEFORE any of that -- so a throw further down must not hide it.
  try { await M.api.switchTable('t'); } catch (e) { /* the stub ends before the grid does */ }
  ok(addBtn.disabled === true, 'F4 loading a view disables the add control');
  ok(addBtn.getAttribute('title') === NOTE,
    `F5 ... and carries the reason with it [${addBtn.getAttribute('title')}]`);
  addBtn.disabled = true;
  staged = schemaBody('table');
  try { await M.api.switchTable('t'); } catch (e) { /* as above */ }
  ok(addBtn.disabled === false, 'F6 ... and loading a table gives it back -- F4 is not vacuous');
  // 🔴 AND THE GUARD ITSELF, CALLED DIRECTLY. F4-F6 go through the REAL `ui.js` whatever module
  //    this run mutated -- that is how this file is built (one copy swapped, the rest real) --
  //    so a defect inside the guard is only visible through its own module, exactly as the
  //    bulk-fill funnel above is scored.
  realState.currentTableKind = 'view';
  addBtn.disabled = false;
  // 마크업이 이미 다는 말. index.html 의 `title="Add Row"` 그대로입니다.
  addBtn.setAttribute('title', 'Add Row');
  delete addBtn.dataset.titleWas;
  M.guard.applyWriteGuards();
  ok(addBtn.disabled === true && addBtn.getAttribute('title') === NOTE,
    `F7 the guard disables the control and names the reason [${addBtn.getAttribute('title')}]`);
  realState.currentTableKind = 'table';
  M.guard.applyWriteGuards();
  ok(addBtn.disabled === false && addBtn.getAttribute('title') === 'Add Row',
    `F8 ... and gives it back on a table WITH the markup's own words [${addBtn.getAttribute('title')}]`);

  // ── S: one rule for every write control, and the table says what it is (C-107) ───────
  // 🔴 C-84 covered six seats ONE AT A TIME and C-102 found the seventh by watching the owner
  //    click it. The judgement was already single (`tableIsView`); what was copied five times
  //    was ASKING it. A list in one place is what stops an eighth from being forgotten.
  const CONTROLS = ['add-row-btn', 'delete-row-btn', 'tx-apply-btn',
                    'ingest-file-btn', 'folder-upload-btn'];
  const controls = () => CONTROLS.map((id) => document.getElementById(id));
  realState.currentTableKind = 'view';
  for (const btn of controls()) { btn.disabled = false; delete btn.dataset.titleWas; }
  M.guard.applyWriteGuards();
  const locked = controls().filter((b) => b.disabled === true).length;
  ok(locked === CONTROLS.length,
    `S1 every write control on this screen is locked on a view (${locked}/${CONTROLS.length})`);
  ok(controls().every((b) => b.getAttribute('title') === NOTE),
    'S2 ... each carrying the same one reason');
  // 🔴 AND THE TABLE SAYS SO BEFORE ANYTHING IS CLICKED. Until now 「this is a view」 was only
  //    discoverable by trying to write; a locked control with no visible reason is a puzzle.
  const kindBadge = document.getElementById('table-kind');
  ok(kindBadge.textContent === NOTE && kindBadge.hidden === false,
    `S3 the header says what the table is [${kindBadge.textContent}]`);
  realState.currentTableKind = 'table';
  M.guard.applyWriteGuards();
  const free = controls().filter((b) => b.disabled === false).length;
  ok(free === CONTROLS.length, `S4 ... and a table gives all of them back (${free}/${CONTROLS.length})`);
  ok(kindBadge.hidden === true && kindBadge.textContent === '',
    'S5 ... with no badge, because an ordinary table is not news');
  // ⚠️ 「모름」은 거절이 아닙니다 — 옛 서버가 `kind` 를 안 보내면 멀쩡한 표가 잠기면 안 됩니다.
  realState.currentTableKind = '';
  M.guard.applyWriteGuards();
  ok(controls().every((b) => b.disabled === false) && kindBadge.hidden === true,
    'S6 a server that never said which is not a refusal -- P3 of the predicate, at the controls');
  // 🔴 그리고 «규칙의 함수» 자체. 이 파일은 한 번에 모듈 «하나»만 갈아 끼우므로(머리글),
  //    진짜 깔때기들은 언제나 진짜 규칙을 import 합니다 — 규칙 안의 결함은 여기서만 보입니다.
  //    C1~C7 이 「넷이 같이 움직인다」를 행동으로 이미 재고, 이 둘은 그 답이 «어디서» 나오는지를 잽니다.
  realState.currentTableKind = 'view';
  log().textContent = '';
  const refused = M.guard.refuseWrite();
  ok(refused === true && log().textContent === NOTE,
    `S7 the rule refuses and SAYS why, in one place [${log().textContent}]`);
  realState.currentTableKind = 'table';
  log().textContent = '';
  ok(M.guard.refuseWrite() === false && log().textContent === '',
    'S8 ... and on a table it refuses nothing and says nothing');

  // ── G: the refusal is the SERVER's sentence (C-102 ②) ────────────────────────────────
  // 🔴 `api.js` already reads `detail` where a cell edit is refused (:528). This one funnel
  //    folded every answer into 「Create failed」, so the owner's 500 arrived with no 「what」
  //    and no 「why」 -- and S-224 has since made every view write a 422 that CARRIES the why.
  await stageThrough(M.api, 'table');
  const SENTENCE = 'read-only relation: a view cannot be written through';
  refusal = { status: 422, body: { detail: SENTENCE } };
  const refusedRun = await countWrites(() => M.api.addRows(1));
  ok(refusedRun.note === SENTENCE,
    `G1 the refusal on screen is the SERVER's sentence [${refusedRun.note}]`);
  // ⚠️ FastAPI's own 422 carries a LIST in `detail`. Drawing it unchecked is how a screen
  //    says 「[object Object]」 to an operator.
  refusal = { status: 422, body: { detail: [{ loc: ['query', 'count'], msg: 'x' }] } };
  const listy = await countWrites(() => M.api.addRows(1));
  ok(!String(listy.note).includes('object Object') && String(listy.note).includes('422'),
    `G2 a detail that is not a sentence names the status instead [${listy.note}]`);
  refusal = null;
  // The seat itself (src/refusal.js - moved out of api.js so the Tables page reads it without the grid). G1 and G2 go
  // through api.js and the real seat; these ask the module under test, so the seat's own mutants are scored here.
  const said = (status, body) => M.refusal.refusalText({ status, json: async () => body }, 'Read failed');
  ok(await said(422, { detail: SENTENCE }) === SENTENCE, 'G3 the seat answers the server\'s sentence');
  ok(await said(422, { detail: [{ msg: 'x' }] }) === 'Read failed (HTTP 422)', 'G4 a detail that is not a sentence names the status');
  ok(await said(503, { detail: { reason: 'grid_read_stopped', message: 'Stopped after 10 s' } }) === 'Stopped after 10 s',
    'G5 a stopped read\'s message is its sentence');

  // ── R: a refused READ is an answer (C-105) ───────────────────────────────────────────
  // 🔴 CAUGHT ON THE REAL PAGE (lead, 2026-09-13): `/tables/bonding_core_lot/data` answers 422
  //    NAMING the reason -- no row_id and no usable business key, so a page read has no total
  //    order -- and the grid threw `Cannot read properties of undefined (reading 'length')`
  //    because it read `result.data` off the refusal. The screen said 「Data fetch failed」.
  await stageThrough(M.api, 'table');
  const rowsSet = [];
  realState.gridApi.setGridOption = (key, value) => { if (key === 'rowData') rowsSet.push(value); };
  const SAYS = 'bonding_core_lot: no row_id and no usable business_key -- declare one';
  readRefusal = { status: 422, body: { detail: SAYS } };
  log().textContent = '';
  let threw = null;
  try { await M.api.fetchData(true); } catch (e) { threw = e && e.message; }
  ok(threw === null, `R1 a refused read does not throw [${threw}]`);
  ok(log().textContent === SAYS,
    `R2 ... and the server's sentence is what the screen says [${log().textContent}]`);
  ok(rowsSet.length > 0 && Array.isArray(rowsSet[rowsSet.length - 1])
     && rowsSet[rowsSet.length - 1].length === 0,
    `R3 ... and the grid is emptied, so the previous table's rows are not read as this one's`);
  // ⚠️ 「0 건」 is a MEASUREMENT and this read never counted anything. `match_count` keeps those
  //    apart on purpose, and a refusal is the clearest case of 「not counted」 there is.
  // ⚠️ `total-rows`, not `total-rows-count` -- the id is `dom.js`'s, and reading the wrong
  //    one made this assertion measure an element nothing ever writes to.
  const counted = document.getElementById('total-rows').textContent;
  ok(counted.includes('…') && !counted.includes('0'),
    `R4 ... and the count says 「not counted」, not 「0」 [${counted}]`);
  // 🔴 NOT VACUOUS: the same call on an answer that carries rows still renders them.
  readRefusal = null;
  rowsSet.length = 0;
  await M.api.fetchData(true);
  ok(rowsSet.length > 0 && Array.isArray(rowsSet[rowsSet.length - 1]),
    'R5 a read that is NOT refused still puts rows in the grid');
  // 🔴 87dfa71d7. A read past grid_read_timeout_seconds answers 503 with its sentence in `detail.message` (the body
  //    implementer A sends, adae5832a); the screen said 「Data fetch failed (HTTP 503)」. The read is the one the page
  //    sends - a column filter; the page has no #global-search, so q never leaves it.
  const STOPPED = `Read stopped after ${++stopRun} s - the limit is grid_read_timeout_seconds in the ingestion settings`;
  const FILTER = { b_wy: { filterType: 'text', type: 'contains', filter: '12' } };
  const savedModel = realState.gridApi.getFilterModel;
  const savedSetModel = realState.gridApi.setFilterModel;
  let filterSets = 0;
  realState.gridApi.getFilterModel = () => FILTER;
  realState.gridApi.setFilterModel = () => { filterSets += 1; };
  const dataReads = [];
  const savedR = globalThis.fetch;
  globalThis.fetch = (url, opts) => { if (String(url).includes('/data?')) dataReads.push(String(url)); return savedR(url, opts); };
  try {
    readRefusal = { status: 503, body: { detail: { reason: 'grid_read_stopped', seconds: stopRun, message: STOPPED } } };
    await M.api.fetchData(true);
    ok(toastTexts().includes(STOPPED) && log().textContent === STOPPED,
      `R6 a stopped read: the toast and the status line say the server's sentence [${toastTexts().slice(-1)} | ${log().textContent}]`);
    ok(filterSets === 0 && realState.gridApi.getFilterModel() === FILTER, `R7 ... the typed column filter stays [${filterSets}]`);
    ok(dataReads.length === 1 && dataReads[0].includes('filters='), `R8 ... and the read is asked once, not again [${dataReads.length}]`);
    readRefusal = { status: 500, body: null };
    await M.api.fetchData(true);
    ok(log().textContent === 'Data fetch failed (HTTP 500)'
      && toastTexts().some((t) => String(t).startsWith('Data fetch failed (HTTP 500)')),
      `R9 another status with no sentence keeps today's words [${log().textContent}]`);
    // Lead, after 6f34a1320: every grid process busy past grid_wait_seconds answers 503 grid_pool_busy - the same seat.
    const BUSY = `Every grid process stayed busy for ${++stopRun} s - try again, or raise grid_processes in ingestion_settings.json`;
    readRefusal = { status: 503, body: { detail: { reason: 'grid_pool_busy', message: BUSY } } };
    await M.api.fetchData(true);
    ok(toastTexts().includes(BUSY) && log().textContent === BUSY,
      `R10 a grid pool busy past its wait: the toast and the status line say the server's sentence [${log().textContent}]`);
  } finally {
    globalThis.fetch = savedR;
    readRefusal = null;
    realState.gridApi.getFilterModel = savedModel;
    realState.gridApi.setFilterModel = savedSetModel;
  }
  // ── J: the row jump's refusal through the same seat (lead 10-13 ⓑ) - it read `detail` itself ──
  try {
    readRefusal = { status: 422, body: { detail: 'jump refused under a header sort' } };
    log().textContent = '';
    await M.timeline.navigatorStep3({ row_id: 'R0' });
    ok(log().textContent === 'jump refused under a header sort', `J1 a refused jump says the server's sentence [${log().textContent}]`);
    readRefusal = { status: 503, body: { detail: { reason: 'grid_read_stopped', seconds: 10, message: STOPPED } } };
    await M.timeline.navigatorStep3({ row_id: 'R0' });
    ok(log().textContent === STOPPED, `J2 ... a stopped jump read says the stopped sentence [${log().textContent}]`);
    readRefusal = { status: 500, body: null };
    await M.timeline.navigatorStep3({ row_id: 'R0' });
    ok(log().textContent === '❌ Jump refused (HTTP 500)', `J3 ... and one with no sentence names the status as before [${log().textContent}]`);
  } finally {
    readRefusal = null;
    M.timeline.releaseNavigationGuard('');
  }

  // ── K: the grid's count (ㄱ-1: implementer A 67e5e9ccd, lead 10-13) - asked again while the server counts, Load All,
  //    the export's refusal, the row jump, a live row. The clock and the timers are the harness's.
  {
    const savedK = { fetch: globalThis.fetch, setTimeout: globalThis.setTimeout, now: Date.now };
    const AT = '2026-10-13T07:00:00+00:00';
    let now = 5000000;
    let later = [];
    let countAnswers = [];
    let asked = [];
    const answer = (body, status = 200) => ({ ok: status < 400, status, json: async () => body, text: async () => JSON.stringify(body) });
    Date.now = () => now;
    globalThis.setTimeout = (fn, ms) => { later.push({ fn, ms }); return later.length; };
    globalThis.fetch = async (url) => {
      const u = String(url);
      asked.push(u);
      if (u.endsWith('/schema')) return answer(staged);
      if (u.includes('/data/count')) return answer(countAnswers.length > 1 ? countAnswers.shift() : countAnswers[0]);
      if (u.includes('target_row_id=')) return answer({ data: [rowData()], total: null, count: { total: null, capped: false, counted_at: null, count_seconds: null, counting: true }, target_offset: 0, calculated_skip: 0 });
      return answer({ data: [rowData()], total: null });
    };
    const counts = () => asked.filter((u) => u.includes('/data/count')).length;
    const runLater = async () => { const due = later; later = []; for (const x of due) x.fn(); await new Promise((r) => savedK.setTimeout(r, 0)); };
    const line = () => document.getElementById('total-rows').textContent;
    try {
      await stageThrough(M.api, 'table');
      const COUNTING = { table_name: 't', total: null, capped: false, counted_at: null, count_seconds: null, counting: true };
      const COUNTED = { table_name: 't', total: 4012334, capped: false, counted_at: AT, count_seconds: 1.6, counting: false };
      countAnswers = [COUNTING, COUNTING, COUNTED];
      asked = [];
      await M.api.fetchData(true);
      await new Promise((r) => savedK.setTimeout(r, 0));
      const first = [counts(), later.map((x) => x.ms), line()];
      now += 3000; await runLater();
      now += 3000; await runLater();
      ok(first[0] === 1 && JSON.stringify(first[1]) === '[3000]' && first[2] === 'Counting rows…' && counts() === 3
        && line().startsWith('4,012,334 rows · ') && later.length === 0,
        `K1 the server still counting: asked again every 3 s, and the count drawn when it comes; then asked no more [${JSON.stringify(first)} ${counts()} ${line()} ${later.length}]`);
      // The question changes under it: the next ask is not sent.
      countAnswers = [COUNTING];
      asked = [];
      await M.api.fetchData(true);
      await new Promise((r) => savedK.setTimeout(r, 0));
      realState.currentTable = 'another';
      now += 3000; await runLater();
      ok(counts() === 1 && later.length === 0, `K2 ... the table changed meanwhile: not asked again [${counts()} ${later.length}]`);
      realState.currentTable = 't';
      // Two minutes at most: past them the line stays and nothing more is asked.
      asked = [];
      later = [];
      await M.api.fetchData(true);
      await new Promise((r) => savedK.setTimeout(r, 0));
      for (let i = 0; i < 60 && later.length; i += 1) { now += 3000; await runLater(); }
      ok(counts() === 41 && later.length === 0 && line() === 'Counting rows…',
        `K3 ... and asked for two minutes at most - 0 s to 120 s, 3 s apart, 41 asks, then the line stays [${counts()} ${later.length} ${line()}]`);
      // Load All: the end is a short chunk; only the first chunk is counted.
      const chunks = [[1, 2], [3, 4], [5]];
      const loads = [];
      globalThis.fetch = async (url) => {
        loads.push(String(url));
        const c = chunks[loads.length - 1] || [];
        return answer({ data: c, total: loads.length === 1 ? 10000 : null,
          ...(loads.length === 1 ? { count: { total: 10000, capped: true, counted_at: AT, count_seconds: 0.05, counting: false } } : {}) });
      };
      globalThis.setTimeout = savedK.setTimeout;
      const progress = [];
      const all = await M.api.fetchAllRows('/tables/t/data', 'order_by=row_id&order_desc=false', 2, (n, known) => progress.push([n, known]));
      ok(all.rows.length === 5 && loads.length === 3 && !loads[0].includes('defer_total') && loads.slice(1).every((u) => u.includes('defer_total=true'))
        && JSON.stringify(progress) === '[[2,null],[4,null],[5,null]]' && all.count.capped === true,
        `K4 Load All past 10,000+: every chunk until a short one; the first counted, the rest ask no count; no percent [${all.rows.length} ${JSON.stringify(loads.map((u) => u.includes('defer_total')))} ${JSON.stringify(progress)}]`);
      loads.length = 0;
      chunks.splice(0, 3, [1, 2], [3]);
      globalThis.fetch = async (url) => { loads.push(String(url)); const c = chunks[loads.length - 1] || []; return answer({ data: c, total: loads.length === 1 ? 3 : null }); };
      const exact = [];
      await M.api.fetchAllRows('/tables/t/data', 'q', 2, (n, known) => exact.push([n, known]));
      ok(JSON.stringify(exact) === '[[2,3],[3,3]]', `K5 ... an exact count gives the percent its total [${JSON.stringify(exact)}]`);
      // Load All pressed on page 5 (lead ba39f4ef7): every row from the first on the grid - «1 - N», not «4001 - …».
      realState.viewMode = 'pagination';
      realState.currentSkip = 4000;
      const drawn = [];
      const savedSet = realState.gridApi.setGridOption;
      const savedCount = realState.gridApi.getDisplayedRowCount;
      realState.gridApi.setGridOption = (k, v) => { if (k === 'rowData') drawn.push(v.length); };
      realState.gridApi.getDisplayedRowCount = () => 3;
      M.api.showAllRows([rowData(), rowData(), rowData()]);
      realState.gridApi.setGridOption = savedSet;
      realState.gridApi.getDisplayedRowCount = savedCount;
      const range = document.getElementById('exposed-rows').textContent;
      ok(range === '1 - 3' && realState.currentSkip === 0 && JSON.stringify(drawn) === '[3]' && realState.allDataLoaded === true,
        `K9 Load All from page 5: the grid holds every row from the first and says 1 - 3 [${range} ${realState.currentSkip} ${JSON.stringify(drawn)}]`);
      // The export's refusal: the server's sentence through the one refusal seat.
      const OVER = 'More than 1,000,000 rows match - over the export cap. No CSV is cut short: narrow the search or the filter.';
      globalThis.fetch = async () => answer({ detail: OVER }, 413);
      const refused = await M.api.openExport('/tables/t/export?x=1');
      globalThis.fetch = async () => answer({});
      const opened = await M.api.openExport('/tables/t/export?x=1');
      ok(refused.refused === OVER && !refused.res && Boolean(opened.res) && !opened.refused,
        `K6 the export past its cap says the server's sentence; an export that opens hands its response on [${JSON.stringify(refused)}]`);
      // The row jump on a table the server has not counted: asked the grid's way.
      globalThis.setTimeout = (fn, ms) => { later.push({ fn, ms }); return later.length; };
      later = [];
      asked = [];
      countAnswers = [COUNTED];
      globalThis.fetch = async (url) => {
        const u = String(url);
        asked.push(u);
        if (u.includes('/data/count')) return answer(COUNTED);
        if (u.includes('target_row_id=')) return answer({ data: [rowData()], total: null, count: COUNTING, target_offset: 0, calculated_skip: 0 });
        return answer({ data: [rowData()], total: null });
      };
      realState.pageCache = new Map();
      await M.timeline.navigatorStep3({ row_id: 'R0' });
      await new Promise((r) => savedK.setTimeout(r, 0));
      ok(counts() === 1 && line().startsWith('4,012,334 rows'), `K7 a row jump onto an uncounted table asks the count the grid's way [${counts()} ${line()}]`);
      // A live row: an exact cached count moves, a 10,000+ one does not.
      realState.pageCache = new Map([[0, { data: [], count: { total: 7, capped: false, countedAt: AT } }], [50, { data: [], count: { total: 10000, capped: true } }]]);
      M.ui.updatePageCacheOnUpsert([{ row_id: 'NEW', data: {} }]);
      M.ui.updatePageCacheOnDelete(['GONE']);
      const moved = [...realState.pageCache.values()].map((e) => e.count.total);
      M.ui.updatePageCacheOnUpsert([{ row_id: 'NEW2', data: {} }]);
      const moved2 = [...realState.pageCache.values()].map((e) => e.count.total);
      ok(JSON.stringify(moved) === '[7,10000]' && JSON.stringify(moved2) === '[8,10000]',
        `K8 a live row moves an exact cached count, not a 10,000+ one [${JSON.stringify([moved, moved2])}]`);
      // Next and Prev by key (lead e570dcda5, server key_page): after=<the shown page's last row>, before=<its first>,
      // skip beside it; a page-number jump and a page with nothing cached go by skip alone.
      const pageOf = (tag) => [{ ...rowData(), row_id: `${tag}-first` }, { ...rowData(), row_id: `${tag}-last` }];
      const reads = [];
      globalThis.fetch = async (url) => {
        const u = new URL(String(url), 'http://x');
        if (!u.pathname.endsWith('/data')) return answer(COUNTED);
        const skip = Number(u.searchParams.get('skip'));
        reads.push([skip, u.searchParams.get('after'), u.searchParams.get('before')]);
        return answer({ data: pageOf(`p${skip / 1000}`), total: null });
      };
      realState.pageCache = new Map();
      realState.viewMode = 'pagination';
      await M.api.fetchData(true);
      await M.api.nextPage();
      await M.api.nextPage();
      realState.pageCache.delete(1000);
      await M.api.prevPage();
      realState.currentSkip = 4000;
      await M.api.fetchData(false);
      realState.pageCache = new Map();
      await M.api.nextPage();
      ok(JSON.stringify(reads) === JSON.stringify([[0, null, null], [1000, 'p0-last', null], [2000, 'p1-last', null],
        [1000, null, 'p2-first'], [4000, null, null], [5000, null, null]]),
        `K13 Next asks after the shown page's last row, Prev before its first, skip beside it; a page jump and an uncached page by skip alone [${JSON.stringify(reads)}]`);
      // The two sequential readers by key too (lead 11-13: OFFSET 1.86 M sorted the table on disk): the infinite view's
      // next page after the last read's last row and Load All's next chunk after the rows so far, skip beside each as the server's way back; the writers of a chunk asked at its own
      // URL, key and all.
      reads.length = 0;
      realState.viewMode = 'infinite';
      realState.isLoadingMore = false;
      await M.api.fetchData(true);
      for (let i = 0; i < 2; i += 1) {
        realState.hasMoreData = true;   // a two-row page reads as the end; the scroll is asked on regardless
        M.grid.appendNextRows();
        await new Promise((r) => savedK.setTimeout(r, 0));
      }
      realState.hasMoreData = true;
      await M.api.nextPage();   // the step itself, in the module under test (grid.js above imports the real one)
      const scrolled = reads.slice();
      reads.length = 0;
      const chunkOf = (skip) => [{ ...rowData(), row_id: `c${skip}-a` }, { ...rowData(), row_id: `c${skip}-b` }].slice(0, skip >= 4 ? 1 : 2);
      const chunkUrls = [];
      globalThis.fetch = async (url) => {
        chunkUrls.push(String(url));
        const u = new URL(String(url), 'http://x');
        const skip = Number(u.searchParams.get('skip'));
        reads.push([skip, u.searchParams.get('after')]);
        return answer({ data: chunkOf(skip), total: skip ? null : 5, looks: skip === 2 ? { updating: true } : null });
      };
      const heldTimer = globalThis.setTimeout;
      globalThis.setTimeout = savedK.setTimeout;   // Load All yields a frame between chunks
      const loaded = await M.api.fetchAllRows('/tables/t/data', 'order_by=row_id&order_desc=false', 2, () => {});
      globalThis.setTimeout = heldTimer;
      const writerUrl = loaded.writers[0] && new URL(loaded.writers[0].url, 'http://x');
      realState.viewMode = 'pagination';
      ok(JSON.stringify(scrolled) === JSON.stringify([[0, null, null], [1000, 'p0-last', null], [2000, 'p1-last', null], [3000, 'p2-last', null]])
        && JSON.stringify(reads) === JSON.stringify([[0, null], [2, 'c0-b'], [4, 'c2-b']]) && loaded.rows.length === 5
        && !!writerUrl && loaded.writers[0].skip === 2 && writerUrl.searchParams.get('after') === 'c0-b',
        `K14 the infinite view's next page after the last read's last row, Load All's next chunk after the rows so far, skip beside; a chunk's writers at its own URL [${JSON.stringify([scrolled, reads, loaded.writers])}]`);
      // A pivot group's long rows read before a delete, 1,000 a read to the end - each read after the last row read.
      const heldView = realState.pivotView;
      realState.pivotView = { column: 'itemid', value: 'value', keys: ['lot', 'wafer'], items: ['a'] };
      const longs = (n, from) => Array.from({ length: n }, (_, k) => ({ row_id: `g${from + k}`, data: { lot: { value: 'L1' }, wafer: { value: 'W1' } } }));
      reads.length = 0;
      globalThis.fetch = async (url) => {
        const u = new URL(String(url), 'http://x');
        const skip = Number(u.searchParams.get('skip'));
        reads.push([skip, u.searchParams.get('after')]);
        return answer({ data: skip ? longs(1, 1000) : longs(1000, 0), total: null });
      };
      const groupIds = await M.api.groupLongIds([{ data: { data: { lot: { value: 'L1' }, wafer: { value: 'W1' } } } }]);
      realState.pivotView = heldView;
      ok(JSON.stringify(reads) === JSON.stringify([[0, null], [1000, 'g999']]) && groupIds.length === 1001,
        `K15 a pivot group's rows before a delete: the next read after the last row read, skip beside [${JSON.stringify(reads)} ${groupIds.length}]`);
      // the one key every reader asks (rows_key.js): the last row going on, the first going back, none without row_id
      const keyed = [M.keys.rowsKey([{ row_id: 'a' }, { row_id: 'b' }], 'after'), M.keys.rowsKey([{ row_id: 'a' }, { row_id: 'b' }], 'before'),
        M.keys.rowsKey([{ lot: 'L1' }], 'after'), M.keys.rowsKey([], 'after')];
      ok(JSON.stringify(keyed) === JSON.stringify([{ after: 'b' }, { before: 'a' }, null, null]),
        `K16 the key: after the last row, before the first, none without a row_id or a row [${JSON.stringify(keyed)}]`);
      // A count the server could not make (lead 0fd18ae19 6): its `failed` field, or a refused /data/count, is said -
      // not «Counting rows…» for ever - and not asked again by the screen (the server keeps the pace).
      let countReply = () => answer(COUNTED);
      globalThis.fetch = async (url) => {
        const u = String(url);
        asked.push(u);
        if (u.includes('/data/count')) return countReply();
        return answer({ data: [rowData()], total: null });
      };
      const FAILED = { table_name: 't', total: null, capped: false, counted_at: null, count_seconds: null, counting: false,
        failed: { reason: 'count stopped after 10 s', at: AT } };
      countReply = () => answer(FAILED);
      realState.pageCache = new Map();
      asked = []; later = [];
      await M.api.fetchData(true);
      await new Promise((r) => savedK.setTimeout(r, 0));
      ok(line() === 'Count failed (count stopped after 10 s)' && counts() === 1 && later.length === 0,
        `K10 the server's failed count: «Count failed (<reason>)», asked no more [${line()} ${counts()} ${later.length}]`);
      const lines = [];
      for (const reply of [() => answer({ detail: { reason: 'grid_read_stopped', seconds: 10, message: 'Filter stopped after 10 s' } }, 503),
        () => ({ ok: false, status: 500, json: async () => { throw new SyntaxError('not JSON'); } })]) {
        countReply = reply;
        realState.pageCache = new Map();
        await M.api.fetchData(true);
        await new Promise((r) => savedK.setTimeout(r, 0));
        lines.push(line());
      }
      ok(JSON.stringify(lines) === JSON.stringify(['Count failed (Filter stopped after 10 s)', 'Count failed (HTTP 500)']),
        `K11 a refused count: the server's sentence, else its status [${JSON.stringify(lines)}]`);
      // batch_refresh_required (lead 0fd18ae19 7): the page cache is dropped and the count asked again with it.
      countReply = () => answer(COUNTED);
      asked = [];
      M.ws.handleWebSocketMessage({ event: 'batch_refresh_required', table_name: 't' });
      await new Promise((r) => savedK.setTimeout(r, 0));
      ok(counts() === 1 && line().startsWith('4,012,334 rows') && realState.pageCache.size === 0,
        `K12 a batch refresh asks the count again [${counts()} ${line()} ${realState.pageCache.size}]`);
    } finally {
      globalThis.fetch = savedK.fetch;
      globalThis.setTimeout = savedK.setTimeout;
      Date.now = savedK.now;
      realState.currentTable = 't';
      realState.pageCache = new Map();
      M.timeline.releaseNavigationGuard('');
    }
  }
  realState.gridApi.setGridOption = () => {};

  // ── W: the row delete waits VISIBLY (a0ae05b60, owner 「ㄱ, 한 1만행」) ─────────────────
  // The clock and the interval are the harness's, so 「12 s」 is a value it set, not one it hoped for.
  await stageThrough(M.api, 'table');
  M.guard.applyWriteGuards();
  const delBtn = document.getElementById('delete-row-btn');
  const ROWS = ['R1', 'R2', 'R3'];
  let present = new Set(ROWS);
  let removed = [];
  realState.gridApi.getSelectedNodes = () => ROWS.map((id) => ({ data: { row_id: id } }));
  realState.gridApi.getRowNode = (id) => (present.has(id) ? { data: { row_id: id } } : null);
  realState.gridApi.applyTransaction = (tx) => {
    for (const r of (tx && tx.remove) || []) { removed.push(r.row_id); present.delete(r.row_id); }
    return {};
  };
  const saved = { now: Date.now, set: globalThis.setInterval, clear: globalThis.clearInterval,
    fetch: globalThis.fetch, confirm: globalThis.confirm };
  let now = 1000000;
  let ticks = [];
  let cleared = 0;
  Date.now = () => now;
  globalThis.setInterval = (fn) => { ticks.push(fn); return ticks.length; };
  globalThis.clearInterval = () => { cleared += 1; };
  globalThis.confirm = () => true;
  let reply = null;
  let deletes = 0;
  // 🔴 EVERY waiting request is held and released together. A mutant that lets a second delete out
  //    must not hang this file — it must show up as a count.
  const held = [];
  const release = () => { while (held.length) held.shift()(); };
  globalThis.fetch = async (url, opts) => {
    if (!String(url).includes('/rows/batch_delete')) return saved.fetch(url, opts);
    deletes += 1;
    await new Promise((r) => { held.push(r); });
    if (reply instanceof Error) throw reply;
    return reply;
  };
  const settleW = async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); };
  try {
    reply = { ok: true, status: 200, json: async () => ({ deleted_count: 3 }) };
    const running = M.api.deleteSelectedRows();
    await settleW();
    ok(delBtn.disabled === true && delBtn.getAttribute('title') === 'Deleting…',
      `W1 while the delete runs, its button is off and says so [${delBtn.disabled} ${delBtn.getAttribute('title')}]`);
    now += 12000;
    for (const fn of ticks) fn();
    ok(log().textContent === 'Deleting 3 rows · 12 s',
      `W2 ... and the status line counts the seconds [${log().textContent}]`);
    const again = M.api.deleteSelectedRows();
    await settleW();
    ok(deletes === 1, `W3 a second press while one runs sends nothing — the menu calls the same funnel [${deletes}]`);
    release();
    await running;
    await again;
    ok(removed.join(',') === 'R1,R2,R3', `W4 when it answers, those rows leave the grid [${removed}]`);
    ok(delBtn.disabled === false && cleared >= 1 && log().textContent === 'Deleted 3 rows · 12 s',
      `W5 ... the button is back, the clock stopped, and the line says what and how long [${log().textContent}]`);
    // the broadcast took R1 and R2 first: only R3 is removed here, so no id is removed twice
    present = new Set(['R3']); removed = []; ticks = [];
    const second = M.api.deleteSelectedRows();
    await settleW(); release(); await second;
    ok(removed.join(',') === 'R3', `W6 rows the broadcast already took are not removed again [${removed}]`);
    // a refusal: the server's sentence, then what to do — and nothing leaves the grid
    present = new Set(ROWS); removed = []; ticks = [];
    reply = { ok: false, status: 422, json: async () => ({ detail: 'read-only relation: a view cannot be written through' }) };
    const third = M.api.deleteSelectedRows();
    await settleW(); release(); await third;
    ok(log().textContent === 'read-only relation: a view cannot be written through — reload the table to see which rows remain',
      `W7 a refusal shows the server's sentence and the next step [${log().textContent}]`);
    ok(removed.length === 0 && delBtn.disabled === false,
      `W8 ... the rows stay, and the button comes back [${removed} ${delBtn.disabled}]`);
    reply = new Error('connection reset');
    const fourth = M.api.deleteSelectedRows();
    await settleW(); release(); await fourth;
    ok(log().textContent === 'Delete request did not reach the server (network) — reload the table to see which rows remain',
      `W9 a request that never reached the server says so [${log().textContent}]`);
  } finally {
    Date.now = saved.now; globalThis.setInterval = saved.set; globalThis.clearInterval = saved.clear;
    globalThis.fetch = saved.fetch; globalThis.confirm = saved.confirm;
    realState.isDeletingRows = false;
  }

  // ── L: a ledger receipt line shows its transaction's rows and stops (43a738d58) ────────────
  // The logs are the contract's own (`contracts/ledger_receipt/vectors.json`, live shapes): a single
  // line hands its log over, a grouped line hands `group.logs[0]` — the same object here.
  const RECEIPT = JSON.parse(readFileSync(path.join(HERE, '..', '..', 'contracts', 'ledger_receipt',
    'vectors.json'), 'utf8')).cases;
  const followed = { ...RECEIPT.followed_success.logs[0], table_name: 't' };
  const backfill = { ...RECEIPT.unfollowed_backfill.logs[0], table_name: 't' };
  const reads = [];
  const savedL = { fetch: globalThis.fetch, timeout: globalThis.setTimeout };
  globalThis.fetch = (url, opts) => {
    if (String((opts && opts.method) || 'GET').toUpperCase() === 'GET') reads.push(String(url));
    return savedL.fetch(url, opts);
  };
  try {
    await stageThrough(M.api, 'table');
    realState.isNavigating = false;
    // A full page: the grid holds pageLimit rows of a transaction that changed more (lead 8bc1bd530).
    const onePage = realState.gridApi.getDisplayedRowCount;
    realState.gridApi.getDisplayedRowCount = () => 1000;
    await M.timeline.navigateToLog(followed);
    realState.gridApi.getDisplayedRowCount = onePage;
    const asked = reads.filter((u) => u.includes('/tables/t/data?'));
    ok(asked.some((u) => u.includes(`transaction_id=${encodeURIComponent(followed.transaction_id)}`))
      && realState.currentTransactionId === followed.transaction_id,
      `L1 a receipt with a transaction reads that transaction's rows [${asked.join(' | ')}]`);
    ok(realState.isNavigating === false && !log().textContent.includes('Navigating')
      && log().textContent === `Ledger batch · t · transaction ${String(followed.transaction_id).slice(0, 8)}`,
      `L2 ... and stops there: no row jump, the line names the transaction and no page count [${log().textContent}]`);
    // ⚠️ `switchTable` walks further than this stub goes (as in S): what is scored is that the
    //    receipt switches to its table FIRST. The transaction read after it is L1's.
    try { await M.timeline.navigateToLog({ ...followed, table_name: 'u' }); } catch (e) { /* the stub ends before the grid does */ }
    ok(realState.currentTable === 'u', `L3 a receipt of another table switches to it first [${realState.currentTable}]`);
    await stageThrough(M.api, 'table');
    reads.length = 0;
    await M.timeline.navigateToLog(backfill);
    ok(reads.length === 0 && realState.isNavigating === false
      && log().textContent === 'Ledger batch · t · no transaction to show — a backfill or retroactive batch',
      `L4 a receipt with no transaction (backfill) reads nothing and says why [${log().textContent}]`);
    await M.timeline.navigateToLog({ ...backfill, transaction_id: 'no_tid' });
    ok(reads.length === 0 && log().textContent.includes('no transaction to show'),
      `L5 ... and the grouped line's no_tid bucket says the same [${log().textContent}]`);
    // A refused read: the line keeps the server's sentence rather than claiming rows it never showed.
    await stageThrough(M.api, 'table');
    readRefusal = { status: 422, body: { detail: 't: no row_id and no usable business_key -- declare one' } };
    await M.timeline.navigateToLog(followed);
    readRefusal = null;
    ok(log().textContent === 't: no row_id and no usable business_key -- declare one',
      `L7 a refused read keeps the server's sentence on the line [${log().textContent}]`);
    // 🔴 A line of any other kind is unchanged: it starts the row jump. Its timers are held here.
    globalThis.setTimeout = () => 0;
    await M.timeline.navigateToLog({ ...followed, column_name: 'qty', row_id: 'R0' });
    ok(realState.isNavigating === true && log().textContent.startsWith('🔍 Navigating to t:R0'),
      `L6 a cell change line still jumps to its row [${log().textContent}]`);
  } finally {
    globalThis.fetch = savedL.fetch; globalThis.setTimeout = savedL.timeout;
    M.timeline.releaseNavigationGuard('');
  }

  // ── N (lead 10-29): the cells a save's answer says were not written - the server's sentence, at every grid save ──
  {
    const savedN = globalThis.fetch;
    const said = `Next: fix the values their columns' types do not take - the rest of each row was written. Not written: value_refused qty=1 (first 'abc') over 1 row(s). #${++stopRun}`;
    let dropped = null;
    // the page's own read (fetchData) after a save - not Apply's read of its staged rows, which names them
    let pageReads = 0;
    globalThis.fetch = async (url, opts = {}) => {
      if (String(opts.method || 'GET').toUpperCase() === 'PUT') {
        const body = { status: 'success', change_count: 0, ...(dropped ? { dropped } : {}) };
        return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
      }
      // Apply's own read of its staged rows: the row as it was staged, so nothing conflicts
      if (String(url).includes('filters=')) return { ok: true, status: 200, json: async () => ({ data: [rowData()], total: null }), text: async () => '' };
      if (String(url).includes('/data?skip=')) pageReads += 1;
      return savedN(url, opts);
    };
    const lines = { paste: 'Pasted · 0 cells updated', clear: 'Cleared cells in', fill: 'Updated range cells in',
      edit: 'Saved in', apply: 'Applied batch updates in' };
    const saves = {
      paste: async () => { await stageThrough(M.api, 'table'); listeners.clear(); M.clipboard.setupClipboardHandlers(); await (listeners.get('paste') || [])[0](pasteEvent('9')); },
      clear: async () => { await stageThrough(M.api, 'table'); await M.clipboard.clearSelectedCells(); },
      fill: async () => { await stageThrough(M.api, 'table'); await M.ui.applyValueToSelectedRange('9'); },
      edit: async () => { await stageThrough(M.api, 'table'); const row = rowData(); row.data.note.value = 'y'; await M.api.handleCellEdit({ data: row, colDef: { field: 'note' }, newValue: 'y', oldValue: 'x' }); },
      apply: async () => {
        await stageThrough(M.api, 'table');
        realState.pendingTxEdits = { R0_note: { rowId: 'R0', colId: 'note', newValue: 'y', oldValue: 'x', data: rowData(), conflict: null } };
        await M.api.applyPendingEdits();
      },
    };
    const toastsAfter = async (run) => {
      const before = toastTexts().length;
      try { await run(); } catch (e) { /* a save may walk further than this stub goes */ }
      return toastTexts().slice(before);
    };
    try {
      dropped = { cells: 1, rows: 1, columns: ['qty'], by_reason: { value_refused: 1 }, said };
      for (const [name, run] of Object.entries(saves)) {
        pageReads = 0;
        const got = await toastsAfter(run);
        ok(got.includes(said), `N1 ${name}: the server's sentence is the toast, as it wrote it [${got.join(' | ')}]`);
        // the cell not written drawn as the server holds it: the page read again, and the save's own line kept on top
        ok(pageReads === 1 && log().textContent.startsWith(lines[name]),
          `N4 ${name}: the page read again once, its line kept [${pageReads} reads · ${log().textContent}]`);
      }
      dropped = { cells: 2, rows: 1, columns: ['created_by', 'row_kind'], by_reason: { system_column: 2 } };
      const plain = await toastsAfter(saves.edit);
      ok(plain.includes('Not written: 2 cells · created_by, row_kind'),
        `N2 no sentence sent: the cells and their columns only [${plain.join(' | ')}]`);
      dropped = null;
      pageReads = 0;
      const none = await toastsAfter(saves.edit);
      ok(!none.some((t) => String(t).startsWith('Not written') || String(t).includes(said)),
        `N3 nothing dropped: nothing said [${none.join(' | ')}]`);
      ok(pageReads === 0, `N5 nothing dropped: no page read [${pageReads}]`);
      await toastsAfter(saves.paste);
      ok(log().textContent === 'Pasted · 0 cells updated',
        `N6 a paste counts the cells the server changed, not the rows sent - none says 0 [${log().textContent}]`);
    } finally {
      globalThis.fetch = savedN;
      realState.pendingTxEdits = {};
    }
  }

  // ── V (lead 10-29 ㄷ): a number column's value goes as it was given - the page neither turns it into a number nor
  //    stops the write; a blank is no value; a number JSON cannot carry goes as its text ──
  {
    const savedV = globalThis.fetch;
    let sent = [];
    globalThis.fetch = async (url, opts = {}) => {
      if (String(opts.method || 'GET').toUpperCase() === 'PUT') {
        for (const u of JSON.parse(opts.body).updates) sent.push(u.updates);
        return { ok: true, status: 200, json: async () => ({ status: 'success', change_count: 0 }), text: async () => '' };
      }
      return savedV(url, opts);
    };
    const onQty = async () => {
      await stageThrough(M.api, 'table');
      realState.selectedCellsMap = { '0_qty': { rowIndex: 0, colId: 'qty' } };
    };
    const paste = async (text) => {
      sent = [];
      await onQty();
      listeners.clear();
      M.clipboard.setupClipboardHandlers();
      try { await (listeners.get('paste') || [])[0](pasteEvent(text)); } catch (e) { /* as above */ }
      return sent.map((u) => u.qty);
    };
    try {
      const typed = {};
      for (const text of ['1e999', 'NaN', '1,234', '-0']) typed[text] = await paste(text);
      ok(Object.entries(typed).every(([text, got]) => got.length === 1 && got[0] === text),
        `V1 a paste into a number column sends what was pasted, as text - 1e999 · NaN · 1,234 · -0 [${JSON.stringify(typed)}]`);
      // (a paste of a blank alone is dropped by the reader before any cell - a blank cell rides in a row)
      ok((await paste(' \tz')).length === 1 && sent[0].qty === null && sent[0].note === 'z',
        `V2 a blank cell pasted is no value [${JSON.stringify(sent)}]`);
      sent = [];
      await onQty();
      listeners.clear();
      M.clipboard.setupClipboardHandlers();
      try { await (listeners.get('paste') || [])[0](pasteEvent('1,234\tz')); } catch (e) { /* as above */ }
      ok(sent.length === 1 && sent[0].qty === '1,234' && sent[0].note === 'z',
        `V3 a table pasted sends its number cells as text too [${JSON.stringify(sent)}]`);
      sent = [];
      await onQty();
      // as AG Grid edits: the parser, the setter on the row, then the change event with the valueGetter's read of it
      const qty = M.grid.buildColumnDefs().find((d) => d.field === 'qty');
      const typedEdit = async (text, reread) => {
        const row = rowData();
        qty.valueSetter({ data: row, newValue: qty.valueParser ? qty.valueParser({ newValue: text, oldValue: 1 }) : text });
        sent = [];
        await onQty();
        try { await M.api.handleCellEdit({ data: row, colDef: { field: 'qty' }, newValue: reread, oldValue: 1 }); } catch (e) { /* as above */ }
        return sent.length === 1 ? sent[0].qty : `sent ${sent.length}`;
      };
      const edited = [await typedEdit('1e999', Infinity), await typedEdit('0x10', 16), await typedEdit('007', 7)];
      ok(JSON.stringify(edited) === JSON.stringify(['1e999', '0x10', '007']),
        `V4 an edit sends the text the cell took, not the grid's number read of it - 1e999 · 0x10 · 007 [${JSON.stringify(edited)}]`);
      const abc = await typedEdit('abc', 'abc');
      ok(abc === 'abc', `V5 an edit's text goes as typed [${JSON.stringify(abc)}]`);
      const row = rowData();
      const took = [Infinity, '1,234', ''].map((v) => (qty.valueSetter({ data: row, newValue: v }), row.data.qty.value));
      const parsed = ['1e999', '-0', '007'].map((v) => (qty.valueParser ? qty.valueParser({ newValue: v, oldValue: 5 }) : 'no parser'));
      ok(JSON.stringify(parsed) === JSON.stringify(['1e999', '-0', '007']),
        `V9 the text box's text reaches the cell as typed - no number parsing on the way [${JSON.stringify(parsed)}]`);
      ok(qty.cellEditor === 'agTextCellEditor',
        `V8 a number column is edited in a text box - the number box handed 1e999 and letters over as a blank (owner 10-31) [${qty.cellEditor}]`);
      ok(took[0] === 'Infinity' && took[1] === '1,234' && took[2] === null,
        `V6 the cell takes the editor's value the same way - Infinity as text, text as typed, blank none [${JSON.stringify(took)}]`);
      // the one rule, asked of its own module (a write_guard.js copy is not what the real funnels import)
      const send = (col, v) => M.guard.cellToSend(col, v);
      const rule = [send('qty', '  '), send('qty', Infinity), send('qty', NaN), send('qty', '1,234'), send('qty', 5), send('note', '')];
      ok(JSON.stringify(rule) === JSON.stringify([null, 'Infinity', 'NaN', '1,234', 5, '']),
        `V7 cellToSend: a number column's blank none, Infinity · NaN their text, text and numbers as given, a text column's blank as given [${JSON.stringify(rule)}]`);
    } finally {
      globalThis.fetch = savedV;
    }
  }

  // ── O: the offscreen badge is written only when its count moves (lead 10-09: it runs on every scroll frame) ──
  {
    const savedApi = realState.gridApi;
    const savedNode = nodes.get('offscreen-cols');
    const node = fakeNode('offscreen-cols');
    let writes = 0;
    let said = '';
    let title = '';
    Object.defineProperty(node, 'textContent', { get: () => said, set: (v) => { writes += 1; said = v; } });
    Object.defineProperty(node, 'title', { get: () => title, set: (v) => { writes += 1; title = v; } });
    node.style = new Proxy({}, { set: (t, k, v) => { writes += 1; t[k] = v; return true; } });
    nodes.set('offscreen-cols', node);
    document.getElementById('grid-filter-bar');
    // Ten columns of 100 px; the view's right edge decides how many are past it.
    let right = 300;
    const cols = Array.from({ length: 10 }, (_, i) => ({ getPinned: () => null, getLeft: () => i * 100, getActualWidth: () => 100 }));
    realState.gridApi = { getHorizontalPixelRange: () => ({ left: 0, right }), getAllDisplayedColumns: () => cols };
    try {
      M.grid.updateOffscreenIndicator();
      ok(writes > 0 && said.includes('7'), `O1 the badge says the columns past the right edge [${said}]`);
      writes = 0;
      M.grid.updateOffscreenIndicator();
      M.grid.updateOffscreenIndicator();
      ok(writes === 0, `O2 the same count again writes nothing to the page [${writes} writes]`);
      right = 500;
      M.grid.updateOffscreenIndicator();
      ok(writes > 0 && said.includes('5'), `O3 a new count is written [${said}]`);
    } finally {
      realState.gridApi = savedApi;
      if (savedNode) nodes.set('offscreen-cols', savedNode); else nodes.delete('offscreen-cols');
    }
  }

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the real modules ------------------------------------------------');
await suite(REAL);

// -- mutants ---------------------------------------------------------------------------
// Each names the FILE it edits; the rest of the bundle stays real.
const DEFECTS = [
  ['api.js: the infinite view\'s next page goes by skip alone (OFFSET however deep)', 'api',
    s => s.replace("  if (state.viewMode === 'infinite') return side === 'after' ? state.readAfter : null;", "  if (state.viewMode === 'infinite') return null;")],
  ['grid.js: the scroll\'s next page is its own read again, by skip', 'grid',
    s => s.replace('  nextPage();   // Next', '  state.currentSkip += pageLimit; fetchData(false);   // Next')],
  ['api.js: Load All\'s chunks go by skip alone', 'api',
    s => s.replace("read(rows.length, true, rowsKey(rows, 'after'))", 'read(rows.length, true)')],
  ['api.js: a pivot group\'s next read by skip alone', 'api',
    s => s.replace("      key = rowsKey(rows, 'after');", '')],
  ['api.js: a chunk\'s writers asked without its key', 'api',
    s => s.replace('writers.push({ url, skip })', 'writers.push({ url: `${baseUrl}?skip=${skip}&limit=${chunkLimit}&${queryParams}`, skip })')],
  ['grid.js: the offscreen badge is written on every scroll frame again', 'grid',
    s => s.replace("  if (badge && badge.dataset.count !== String(count)) {", '  if (badge) {')],
  ['state.js: any announced kind counts as a view', 'state',
    s => s.replace("  return state.currentTableKind === 'view';", '  return !!state.currentTableKind;')],
  ['api.js: the kind is taken without checking it is a string', 'api',
    s => s.replace("    state.currentTableKind = typeof data.kind === 'string' ? data.kind : '';",
                   "    state.currentTableKind = data.kind || '';")],
  ['api.js: the kind is not recorded at all', 'api',
    s => s.replace("    state.currentTableKind = typeof data.kind === 'string' ? data.kind : '';\n", '')],
  ['grid.js: edit entry is offered on a view again', 'grid',
    s => s.replace('      editable: !isSystem && !viewTable && ', '      editable: !isSystem && ')],
  ['clipboard.js: the paste guard is gone', 'clipboard',
    s => s.replace('    if (refuseWrite()) { e.preventDefault(); return; }\n', '')],
  ['clipboard.js: the clear guard is gone', 'clipboard',
    s => s.replace('  if (refuseWrite()) return;\n', '')],
  ['ui.js: the bulk-fill guard is gone', 'ui',
    s => s.replace('  if (refuseWrite()) return;\n', '')],
  // Re-keyed by C-107: the refusal's SENTENCE is written in one place now, so this is where
  // a silent no-op would be made -- and it would silence all four funnels at once.
  ['the refusal is silent, in every funnel at once', 'guard',
    s => s.replace('  if (el) el.textContent = why;\n', '')],
  // 🔴 THE CLAIM OF THIS ROUND, AS ONE MUTANT: one rule feeds every seat. Break the rule and
  //    the paste, the clear, the bulk fill, the add AND the controls all go wrong together.
  // ⚠️ NAMED FOR WHAT IT ACTUALLY BREAKS HERE. The funnels import the REAL rule (one module is
  //    swapped per run), so what this mutant reddens is the controls, the badge and S7 -- the
  //    funnels moving together is scored by C1-C7 on the real modules instead.
  ['the rule stops refusing, so no control is armed and nothing says why', 'guard',
    s => s.replace("  return tableIsView() ? VIEW_READ_ONLY_NOTE : '';", "  return '';")],
  ['the control list loses a seat, which is how the seventh went missing', 'guard',
    s => s.replace("  'addRowBtn', 'addItemBtn', 'deleteRowBtn', 'txApplyBtn',", "  'addItemBtn', 'deleteRowBtn', 'txApplyBtn',")],
  ['the table never says what it is', 'guard',
    s => s.replace('  badge.textContent = why;\n  badge.hidden = !why;', '')],
  // 🔴 C-105. The read path, which is where the owner's 422 arrived as an exception.
  ['api.js: a refused read is read as a page of rows again', 'api',
    s => s.replace('    if (!res.ok) {\n      showReadRefusal(', '    if (false) {\n      showReadRefusal(')],
  ['api.js: the refused read claims it counted zero', 'api',
    s => s.replace('  setMatchCount(elements.totalRowsCount, null);',
                   '  setMatchCount(elements.totalRowsCount, 0);')],
  ['api.js: the refused read leaves the previous table`s rows on screen', 'api',
    s => s.replace("  if (state.gridApi) state.gridApi.setGridOption('rowData', []);\n", '')],
  // 🔴 C-102. Four ways the owner's click gets back to the server, or its answer gets lost.
  ['api.js: the add-row funnel is unguarded again', 'api',
    s => s.replace(/(export async function addRows[\s\S]*?)  if \(refuseWrite\(\)\) return;\n/, '$1')],
  ['api.js: the controls are never told the table changed', 'api',
    s => s.replace('  applyWriteGuards();\n', '')],
  // ⚰️ C-120. TWO MUTANTS MOVED, THEY DID NOT DIE. 「the guard eats the words the markup
  //    already wrote」 and 「the controls are told, and stay clickable anyway」 both aimed at the
  //    loop body inside `applyWriteGuards`, and that body is now `disabled_reason.setDisabledReason`
  //    -- one seat, because the redo banner and two walk buttons ask a DIFFERENT question
  //    (「is a row/type chosen」) and were answering it four different ways, none of them here.
  //    Their claims are scored in `disabled_reason_harness.mjs` as M3 (the markup's own words
  //    are forgotten) and M4 (a reason that does not disable). Mutating the seat FROM HERE would
  //    not bite: `write_guard.js` imports the real module, not this harness's copy.
  // 🔴 WHAT STAYS HERE IS WHAT STAYED IN THIS FILE: that the list of controls is complete
  //    ('the control list loses a seat') and that the page tells them at all
  //    ('api.js: the controls are never told the table changed'). The assertions below are
  //    unchanged and still run through the seat, so a broken seat still reddens this harness --
  //    it is the MUTANTS that moved to the file that can now mutate it.
  ['refusal.js: the server`s sentence is folded into one of ours', 'refusal',
    // Re-aimed by C-105: the sentence is built in ONE place now (`refusalText`), shared with the
    // READ path -- so this is where folding it away happens. Same claim, same G1.
    s => s.replace('  return said || `', '  return false || `')],
  ['refusal.js: a detail that is not a sentence is drawn anyway', 'refusal',
    s => s.replace("  const said = typeof detail === 'string' ? detail", "  const said = detail && !detail.message ? String(detail)")],
  // 🔴 87dfa71d7. The stopped read (503, detail.message).
  ['refusal.js: a stopped read`s sentence is not read', 'refusal',
    s => s.replace("    : (detail && typeof detail.message === 'string' ? detail.message : '');", "    : '';")],
  ['api.js: a refused read drops the typed column filter', 'api',
    s => s.replace('function showReadRefusal(why) {\n', 'function showReadRefusal(why) {\n  if (state.gridApi) state.gridApi.setFilterModel(null);\n')],
  ['timeline.js: the jump words its own refusal again', 'timeline',
    s => s.replace("      releaseNavigationGuard(await refusalText(res, '❌ Jump refused'), jump);", "      releaseNavigationGuard('❌ Jump refused', jump);")],
  ['api.js: a refused read is asked again', 'api',
    s => s.replace("      showReadRefusal(await refusalText(res, 'Data fetch failed'));\n", "      showReadRefusal(await refusalText(res, 'Data fetch failed'));\n      await gridFetch(url);\n")],
  ['source_rows.js: a caller that omits the flag gets the controls', 'rows',
    s => s.replace('  const actions = writable\n', '  const actions = writable !== false\n')],
  // ── W (a0ae05b60): the row delete's wait ────────────────────────────────────────────
  ['api.js: the delete button stays clickable while it runs', 'api',
    s => s.replace("  setDisabledReason(elements.deleteRowBtn, 'Deleting…');\n", '')],
  ['api.js: the wait has no clock', 'api',
    s => s.replace("`Deleting ${unitText(rowIds.length, 'row')} · ${seconds()} s`", "`Deleting ${unitText(rowIds.length, 'row')}`")],
  ['api.js: a second delete goes out while one runs', 'api',
    s => s.replace('  if (!state.gridApi || state.isDeletingRows) return;', '  if (!state.gridApi) return;')],
  ['api.js: the rows wait for the broadcast', 'api',
    s => s.replace("      if (left.length) state.gridApi.applyTransaction({ remove: left.map((rowId) => ({ row_id: rowId })) });\n", '')],
  ['api.js: rows the broadcast took are removed again', 'api',
    s => s.replace('      const left = rowIds.filter((rowId) => state.gridApi.getRowNode(rowId));', '      const left = rowIds;')],
  ['api.js: the delete button stays off after the answer', 'api',
    s => s.replace('    setDisabledReason(elements.deleteRowBtn, writeRefusal());\n', '')],
  ['api.js: the delete refusal is ours, not the server`s', 'api',
    s => s.replace("      refused = await refusalText(res, 'Delete failed');", "      refused = 'Delete failed';")],
  ['api.js: a delete refusal leaves no next step', 'api',
    s => s.replace('  const line = `${refused} — reload the table to see which rows remain`;', '  const line = refused;')],
  ['api.js: the in-flight mark is never cleared, so delete locks after one run', 'api',
    s => s.replace('    state.isDeletingRows = false;\n', '')],
  // ── K (ㄱ-1, lead 10-13): the grid's count ──────────────────────────────────────────────
  ['api.js: a count the server is still making is never asked again', 'api',
    s => s.replace('      if (body.counting === true && Date.now() - since < RECOUNT_ASK_FOR_MS) {', '      if (false) {')],
  ['api.js: asked again for another question too', 'api',
    s => s.replace('if (mine === countGeneration && table === state.currentTable && world === state.gridWorld) fillMatchCount(params, table, since);', 'fillMatchCount(params, table, since);')],
  ['api.js: asked again for ever', 'api',
    s => s.replace('      if (body.counting === true && Date.now() - since < RECOUNT_ASK_FOR_MS) {', '      if (body.counting === true) {')],
  ['api.js: each ask starts the two minutes again', 'api',
    s => s.replace('fillMatchCount(params, table, since);\n        }, RECOUNT_ASK_MS);', 'fillMatchCount(params, table);\n        }, RECOUNT_ASK_MS);')],
  ['api.js: Load All ends at the count again', 'api',
    s => s.replace('  while (last === chunkLimit) {', '  while (rows.length < (exact || 0)) {')],
  ['api.js: Load All keeps the page place - «4001 - 4003» for every row from the first', 'api',
    s => s.replace('  state.hasMoreData = false;\n  state.currentSkip = 0;\n', '  state.hasMoreData = false;\n')],
  ['api.js: Load All counts every chunk', 'api',
    s => s.replace("const chunk = rowsOf(await read(rows.length, true, rowsKey(rows, 'after')));", "const chunk = rowsOf(await read(rows.length, false, rowsKey(rows, 'after')));")],
  ['api.js: Load All says a percent against 10,000+', 'api',
    s => s.replace('const exact = count.total !== null && !count.capped ? count.total : null;', 'const exact = count.total;')],
  ['api.js: the export refusal is today\'s generic line', 'api',
    s => s.replace('{ refused: await refusalText(res, EXPORT_FAILED) }', '{ refused: EXPORT_FAILED }')],
  ['api.js: a failed count stays «Counting rows…»', 'api',
    s => s.replace('    if (count.failed) {\n      setMatchCount(elements.totalRowsCount, count);\n      return;\n    }\n', '')],
  ['api.js: a refused count is swallowed again', 'api',
    s => s.replace("const body = res.ok ? await res.json() : { failed: { reason: (await refusalSaid(res)) || `HTTP ${res.status}` } };",
      'if (!res.ok) return;\n    const body = await res.json();')],
  ['api.js: a refused count drops the server\'s sentence', 'api',
    s => s.replace('{ failed: { reason: (await refusalSaid(res)) || ', '{ failed: { reason: ')],
  ['websocket.js: a batch refresh asks no count', 'ws',
    s => s.replace('    state.pageCache.clear();\n    askMatchCount();\n', '    state.pageCache.clear();\n')],
  ['api.js: Next and Prev ask by skip alone again (OFFSET however deep - the code before)', 'api',
    s => s.replace('  if (key) url += `&${new URLSearchParams(key)}`;\n', '')],
  ['rows_key.js: Next asks after the page\'s first row', 'keys',
    s => s.replace("  const row = side === 'after' ? rows[rows.length - 1] : rows[0];", '  const row = rows[0];')],
  ['api.js: the key is read after the page moved - the page it lands on, not the one shown', 'api',
    s => s.replace("  const key = pageKey('after');\n  state.currentSkip += pageLimit;", "  state.currentSkip += pageLimit;\n  const key = pageKey('after');")],
  ['timeline.js: a row jump onto an uncounted table never asks', 'timeline',
    s => s.replace('    if (count.total === null) askMatchCount();\n', '')],
  ['ui.js: a live row does not move the cached count', 'ui',
    s => s.replace('        cached.count = shiftCount(cached.count, 1);\n', '')],
  // ── L (43a738d58): a ledger receipt line ────────────────────────────────────────────────
  ['timeline.js: a receipt jumps to its row again', 'timeline',
    s => s.replace('  if (log && log.column_name === LEDGER_BATCH_COLUMN) return openLedgerReceipt(log);\n', '')],
  ['timeline.js: a backfill receipt is filtered by a transaction it does not have', 'timeline',
    s => s.replace('  if (!tx || tx === NO_TRANSACTION_BUCKET) {', '  if (false) {')],
  ['timeline.js: the no_tid bucket is read as a transaction', 'timeline',
    s => s.replace('  if (!tx || tx === NO_TRANSACTION_BUCKET) {', '  if (!tx) {')],
  ['timeline.js: a receipt of another table stays on this one', 'timeline',
    s => s.replace('    if (!(await switchTable(log.table_name))) return;\n  }\n  // Only on screen', '  }\n  // Only on screen')],
  ['timeline.js: the line claims rows a refused read never showed', 'timeline',
    s => s.replace('  if (await setTransactionFilter(tx)) {', '  if (await setTransactionFilter(tx) || true) {')],
  // ── N (lead 10-29): every grid save says what its answer did not write ──────
  ['clipboard.js: a paste says nothing of the cells not written', 'clipboard', s => s.replace(/\n {8}const notWritten = sayNotWritten\(result\);/, '\n        const notWritten = null;')],
  ['clipboard.js: a clear says nothing of the cells not written', 'clipboard', s => s.replace(/\n {6}const notWritten = sayNotWritten\(result\);/, '\n      const notWritten = null;')],
  ['ui.js: a fill says nothing of the cells not written', 'ui', s => s.replace(/\n {6}const notWritten = sayNotWritten\(result\);/, '\n      const notWritten = null;')],
  ['api.js: an edit says nothing of the cells not written', 'api', s => s.replace(/\n {6}const notWritten = sayNotWritten\(result\);/, '\n      const notWritten = null;')],
  ['api.js: an Apply says nothing of the cells not written', 'api', s => s.replace(/\n {4}const notWritten = sayNotWritten\(result\);/, '\n    const notWritten = null;')],
  ['clipboard.js: a cell not written stays drawn as sent - no page read', 'clipboard', s => s.replaceAll('pivotShown() || notWritten', 'pivotShown()')],
  ['ui.js: a filled cell not written stays drawn as sent', 'ui', s => s.replace('pivotShown() || notWritten', 'pivotShown()')],
  ['api.js: an edited or applied cell not written stays drawn as sent', 'api', s => s.replaceAll('pivotShown() || notWritten', 'pivotShown()')],
  ['clipboard.js: the page read takes the paste`s line', 'clipboard', s => s.replace('await fetchData(false); elements.performanceLog.textContent = pasted; return;', 'await fetchData(false); return;')],
  ['clipboard.js: a paste counts the rows sent again', 'clipboard', s => s.replace('Number(result.change_count) || 0', 'batchUpdates.length')],
  ['api.js: the server`s sentence is passed over for the counts', 'api',
    s => s.replace("typeof dropped.said === 'string' && dropped.said ? dropped.said", 'false ? dropped.said')],
  ['api.js: the counts name no column', 'api', s => s.replace(" · ${[].concat(dropped.columns || []).join(', ')}", '')],
  // ── V (lead 10-29 ㄷ): a number column's value as it was given ─────────────
  // the single value's line comes first in the file, the table's last
  ['clipboard.js: a paste turns the value into a number again', 'clipboard',
    s => s.replace('updates[colId] = cellToSend(colId, val);', 'updates[colId] = cellToSend(colId, Number(val));')],
  ['clipboard.js: a pasted table turns its values into numbers again', 'clipboard', s => {
    const at = s.lastIndexOf('updates[colId] = cellToSend(colId, val);');
    return at < 0 ? s : `${s.slice(0, at)}updates[colId] = cellToSend(colId, Number(val));${s.slice(at + 'updates[colId] = cellToSend(colId, val);'.length)}`;
  }],
  ['grid.js: the cell takes the editor`s value raw', 'grid', s => s.replace('const finalVal = cellToSend(col, params.newValue);', 'const finalVal = params.newValue;')],
  ['write_guard.js: a number JSON cannot carry goes as a number', 'guard', s => s.replace("typeof value === 'number' && !Number.isFinite(value) ? String(value) : value", 'value')],
  ['grid.js: the typed text is parsed as a number on the way', 'grid', s => s.replace('colDef.valueParser = (params) => params.newValue;', 'colDef.valueParser = (params) => Number(params.newValue);')],
  ['grid.js: a number column is edited in the number box again', 'grid', s => s.replace("colDef.cellEditor = 'agTextCellEditor';", "colDef.cellEditor = 'agNumberCellEditor';")],
  ['api.js: an edit sends the grid`s number read, not what the cell took', 'api', s => s.replace('const finalValue = data.data[colId].value;', 'const finalValue = newValue;')],
  ['write_guard.js: a number column`s blank goes as typed', 'guard', s => s.replace('&& isBlank(value)) return null;', '&& value === undefined) return null;')],
  // ⚠️ NOT HERE: 「fetchData stops returning true」. `timeline.js` reaches `fetchData` through the REAL
  //    `ui.js`, which imports the real `api.js`, so an `api.js` copy swapped in by this file never
  //    reaches that path and the mutant escapes by construction (measured). L2 still runs through the
  //    real chain, so a broken return reddens L2 on the real modules.
];
const CONTROLS = [
  ['grid.js: a local rename', 'grid',
    s => s.replace('  const viewTable = Boolean(writeRefusal());', '  const isAView = Boolean(writeRefusal());')
          .replace('      editable: !isSystem && !viewTable && ', '      editable: !isSystem && !isAView && ')],
  ['state.js: comments stripped', 'state',
    s => s.split('\n').filter(l => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

const FILES = { state: 'state.js', api: 'api.js', refusal: 'refusal.js', grid: 'grid.js', clipboard: 'clipboard.js',
                ui: 'ui.js', rows: 'source_rows.js', guard: 'write_guard.js', timeline: 'timeline.js', ws: 'websocket.js', keys: 'rows_key.js' };

async function scoreMutant(key, mutate, tag) {
  try {
    const mod = (await loadWithProbe(FILE(FILES[key]), { mutate, tag })).module;
    const bundle = { ...REAL, [key]: mod };
    return await suite(bundle);
  } catch (e) {
    const m = String(e && e.message);
    if (/did not mutate|unchanged/.test(m)) {
      quiet = false;
      console.error(`\nan anchor no longer matches: ${m}`);
      process.exit(2);
    }
    return { pass: 0, fail: 1 };
  }
}

const base = { pass, fail };
failedNames.length = 0;

quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, key, mutate] of DEFECTS) {
  const r = await scoreMutant(key, mutate, 'viewro');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, key, mutate] of CONTROLS) {
  const r = await scoreMutant(key, mutate, 'viewroc');
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name}  <- a check is reading source text`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${failedNames.join('\n  ')}`);
if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);

const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escapedNames.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
