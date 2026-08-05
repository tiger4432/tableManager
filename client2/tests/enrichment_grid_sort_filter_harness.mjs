// Harness - both enrichment panels are AG-Grid, sort and filter IN THE BROWSER, and the
// screen says so whenever what is on it is a subset.
// Run: node client2/tests/enrichment_grid_sort_filter_harness.mjs
//
// WHY THIS EXISTS [2026-08-05, product owner ruling: "reference view results and the work
// list should both be AG-Grid so filtering and sorting work", then "do the filtering and
// sorting client-side - there are only a handful of reference views and a partial fetch does
// not happen"].
//
//   G1  ONE SPELLING FOR BOTH PANELS. Two grids on one screen behaving differently is its
//       own trap. The sort/filter discipline is declared once and BOTH panels spread the
//       same object; a second, parallel configuration is the defect this scores.
//   G2  SORTING AND FILTERING ARE ACTUALLY ON, with floating filters, on both.
//   G3  NUMBERS ORDER AS NUMBERS. Neither panel has a `/schema` to type its columns, so a
//       lexical comparator would answer "the largest" with whichever value starts with 9.
//   G4  A BLANK IS NOT THE SMALLEST VALUE. Ascending, blanks land last - the key-less rows
//       `partitionQueueRows` deliberately pushed to the back must not scatter back through.
//   G5  THE REFERENCE VIEW'S COLUMNS COME FROM THE RESPONSE, never from a declaration: the
//       operator writes the SQL. Duplicate labels and dotted labels must survive, so the
//       field is the POSITION and the label is the header only.
//   G6  AND ITS ROWS ARE THE SERVED ROWS.
//   G7  A SUBSET SAYS IT IS ONE. The worklist buffer is capped (`pageLimit`) while the
//       server reports the whole queue in `total`; when those differ the count on screen
//       carries both. When they do not differ it says nothing extra - a tag that is always
//       there is a tag nobody reads.
//   G8  A FILTERED VIEW SAYS IT IS ONE, on both panels, and only while a filter hides rows.
//   G9  A FILTER THAT HIDES EVERYTHING IS NOT AN EMPTY QUEUE. The overlay must never claim
//       the work is done because the operator's own filter hid it.
//   G10 THE REFILL BOUNDARY IS A ROW-DATA COORDINATE. `applyTransaction`'s `addIndex`
//       indexes row data, not the displayed order; once a sort or filter exists the two
//       diverge and a displayed index inserts refilled rows in the wrong place.
//   G11 THE BUFFER SIZE IGNORES THE FILTER. Reading `getDisplayedRowCount()` as "how many
//       rows do I hold" turns "hidden by my filter" into "does not exist".
//   G12 A COLUMN-SET CHANGE DROPS THE PREVIOUS VIEW'S SORT AND FILTER. Carrying a filter
//       from one operator-authored view onto another shows an unexplained empty result.
//
// EVERY CHECK IS PAIRED WITH A MUTANT, and the suite FAILS if a defect still passes -
// a check that cannot fail proves nothing. Two CONTROLS must ESCAPE; if a control is
// caught, some check is reading source text instead of behaviour.
//
// Exit codes: 0 = green | 1 = a check failed or a defect escaped | 2 = harness failure.
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'enrichment.js');

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

if (!existsSync(SRC_PATH)) die(`no source at ${SRC_PATH}`);
const PRISTINE = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

// ── Extraction: anchored at a real declaration, never at a bare name ─────────────
function sliceBalanced(src, startIdx, open, close) {
  const i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === open) depth++;
    else if (src[j] === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}
function fn(src, name) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in enrichment.js - renamed or reshaped.`);
  const body = sliceBalanced(src, m.index, '{', '}');
  if (!body) die(`unbalanced braces for ${name}`);
  return body.replace(/^export\s+/, '');
}
// The shared kernel is a CONST, and it is sliced rather than stubbed on purpose: the whole
// point of G1 is that this object is real and that both panels use THIS one.
function constObj(src, name) {
  const m = new RegExp(`const\\s+${name}\\s*=\\s*\\{`).exec(src);
  if (!m) die(`const ${name} not found in enrichment.js - renamed or reshaped.`);
  const body = sliceBalanced(src, m.index, '{', '}');
  if (!body) die(`unbalanced braces for ${name}`);
  return `${body};`;
}

const SLICED = [
  'compareCells', 'cellVal', 'hasDecisionKeys',
  'buildColumnDefs', 'rebuildGrid',
  'blankKeyBoundaryIndex', 'bufferRowCount', 'worklistCountText',
  'refreshWorklistCounts', 'updateWorklistOverlay',
  'refColumnDefs', 'renderRefTable', 'updateRefMeta', 'showRefStatus', 'hideRefStatus',
];

const RULE = {
  name: 'eqp_product_frame_attribution',
  derived_table: 'dt_enriched',
  decision_key: ['dt_eqp', 'product'],
  target_fields: ['core_frame'],
  list_columns: ['dt_job'],
};

const row = (id, dtEqp, product) => ({
  row_id: id,
  data: {
    dt_eqp: { value: dtEqp, is_overwrite: false, priority_source: 'pipeline_parser' },
    product: { value: product, is_overwrite: false, priority_source: 'pipeline_parser' },
    dt_job: { value: 'J1', is_overwrite: false, priority_source: 'pipeline_parser' },
    core_frame: { value: null, is_overwrite: false, priority_source: null },
  },
});

// ── A document small enough to read, large enough to run the real renderers ─────
function mkEl(tag) {
  const e = {
    tagName: tag, id: '', textContent: '', className: '', title: '',
    style: {}, dataset: {}, children: [],
    appendChild(c) { e.children.push(c); return c; },
    addEventListener() {},
    querySelectorAll() { return []; },
    classList: { toggle() {}, add() {}, remove() {} },
  };
  Object.defineProperty(e, 'innerHTML', {
    get() { return ''; },
    set(v) { if (v === '') e.children.length = 0; },
  });
  return e;
}

// A grid stub that models the ONE distinction this suite is about: the rows it HOLDS versus
// the rows it SHOWS. `hidden` is a set of row-data indices the "filter" is hiding.
function mkGrid(container, options) {
  const g = {
    container,
    options,
    columnDefs: options.columnDefs || [],
    rows: (options.rowData || []).slice(),
    hidden: new Set(),
    filterModelSet: 0,
    columnStateReset: 0,
    columnDefsSet: 0,
    displayed() { return g.rows.filter((_, i) => !g.hidden.has(i)); },
    getDisplayedRowCount() { return g.displayed().length; },
    getDisplayedRowAtIndex(i) {
      const d = g.displayed()[i];
      return d === undefined ? null : { data: d };
    },
    forEachNode(cb) { g.rows.forEach(d => cb({ data: d })); },
    getRowNode() { return null; },
    setGridOption(k, v) {
      if (k === 'columnDefs') { g.columnDefs = v; g.columnDefsSet++; }
      if (k === 'rowData') g.rows = (v || []).slice();
    },
    setFilterModel() { g.filterModelSet++; },
    applyColumnState() { g.columnStateReset++; },
    destroy() {},
  };
  return g;
}

function build(src) {
  const parts = [
    constObj(src, 'GRID_SORT_FILTER_DEFAULTS'),
    constObj(src, 'GRID_SHARED_OPTIONS'),
    ...SLICED.map(n => fn(src, n)),
  ].join('\n\n');

  const els = new Map();
  const el = (id) => {
    if (!els.has(id)) { const e = mkEl('div'); e.id = id; els.set(id, e); }
    return els.get(id);
  };
  const document = { createElement: (tag) => mkEl(tag) };

  const grids = [];
  const createGrid = (container, options) => {
    const g = mkGrid(container, options);
    grids.push(g);
    return g;
  };

  const S = {
    rule: RULE, gridApi: null, totalBlank: 0,
    refGridApi: null, refColSignature: null, refRowCount: 0, refMs: '0',
  };

  // eslint-disable-next-line no-new-func
  const make = new Function(
    'el', 'S', 'document', 'createGrid', 'renderDetail', 'updateHeaderStats',
    `${parts}\nreturn {${SLICED.join(', ')}};`);
  const api = make(el, S, document, createGrid, () => {}, () => {});
  return { api, S, el, els, grids };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let quiet = false;
function suite(src) {
  let pass = 0, fail = 0; const failed = [];
  const check = (name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { pass++; return; }
    fail++; failed.push(name);
    if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  };

  // ---- G1/G2: one kernel, spread by BOTH panels ---------------------------------
  {
    let ctx;
    try { ctx = build(src); } catch (e) { return { pass, fail: fail + 1, failed: [`build threw: ${e && e.message}`] }; }
    const { api, S, grids } = ctx;

    api.rebuildGrid(RULE);
    const worklist = grids[0] && grids[0].options.defaultColDef;

    S.refGridApi = null;
    api.renderRefTable({ columns: ['a'], rows: [['x']], ms: '0' });
    const reference = grids[1] && grids[1].options.defaultColDef;

    const kernel = (d) => (d ? {
      sortable: d.sortable, filter: d.filter,
      floatingFilter: d.floatingFilter, resizable: d.resizable,
      hasComparator: typeof d.comparator === 'function',
    } : null);

    // The empty-result sentence is a GRID-level option and must also be one spelling: AG-Grid
    // has no suppression for its no-matching-rows overlay, so the only way both panels say
    // the same thing is that both are given the same text.
    const locale = (g) => (g && g.options.localeText) || null;
    check('G1 both panels name an empty filter result the same way',
      [locale(grids[0]), locale(grids[1])],
      [{ noMatchingRows: '필터 결과 없음' }, { noMatchingRows: '필터 결과 없음' }]);
    check('G1 and share the theme rather than each picking one',
      [grids[0].options.theme, grids[1].options.theme], ['legacy', 'legacy']);

    check('G2 the worklist sorts, filters and floats its filters', kernel(worklist), {
      sortable: true, filter: 'agTextColumnFilter',
      floatingFilter: true, resizable: true, hasComparator: true,
    });
    check('G1 the reference view is given the SAME discipline, not a parallel one',
      kernel(reference), kernel(worklist));
    check('G1 and literally the same comparator function',
      worklist && reference && worklist.comparator === reference.comparator, true);
    check('G2 the worklist stays read-only (editing is the conveyor\'s job)',
      worklist && worklist.editable, false);
  }

  // ---- G3/G4: ordering ----------------------------------------------------------
  {
    const { api } = build(src);
    const c = api.compareCells;
    check('G3 9 comes before 10', c('9', '10'), -1);
    check('G3 and 10 after 9', c('10', '9'), 1);
    check('G3 equal numbers spelled differently tie', c('7', '7.0'), 0);
    check('G3 real numbers still order', c(2, 11), -1);
    check('G3 text still orders as text', c('apple', 'banana'), -1);
    check('G4 a blank sorts after a value', c('', 'A'), 1);
    check('G4 null sorts after a value', c(null, 'A'), 1);
    check('G4 whitespace is blank too', c('   ', 'A'), 1);
    check('G4 two blanks tie', c('', null), 0);
    check('G4 a value sorts before a blank', c('A', ''), -1);
    // Sorting a real column end to end: text order would put '10' between '1' and '9'.
    const sorted = ['9', '10', '1', '', '100'].slice().sort(c);
    check('G3/G4 a whole column orders numerically with blanks last',
      sorted, ['1', '9', '10', '100', '']);
  }

  // ---- G5/G6: the reference view's columns come from the response ----------------
  {
    const { api, S, grids } = build(src);
    // Operator SQL really can do this: two columns labelled the same, and a label with a dot
    // (AG-Grid reads a dotted `field` as a property path).
    const payload = { columns: ['a.b', 'x', 'x'], rows: [[1, 'p', 'q'], [2, 'r', 's']], ms: '7' };
    S.refGridApi = null;
    api.renderRefTable(payload);
    const g = grids[0];

    check('G5 one column def per served column', g.columnDefs.length, 3);
    check('G5 the served labels are the headers, verbatim',
      g.columnDefs.map(d => d.headerName), ['a.b', 'x', 'x']);
    check('G5 fields are positions, so duplicate labels do not collide',
      g.columnDefs.map(d => d.field), ['c0', 'c1', 'c2']);
    check('G5 each column reads its own position out of the row',
      g.columnDefs.map(d => d.valueGetter({ data: [1, 'p', 'q'] })), [1, 'p', 'q']);
    check('G6 the served rows are what the grid holds', g.rows, payload.rows);
    check('G6 nothing is dropped on the way in', g.getDisplayedRowCount(), 2);
  }

  // ---- G7: the worklist count discloses a subset, and only then ------------------
  {
    const { api, S, grids } = build(src);
    api.rebuildGrid(RULE);
    S.gridApi = grids[0];
    S.gridApi.rows = Array.from({ length: 50 }, (_, i) => row(i + 1, 'E', 'P'));

    S.totalBlank = 1284;
    check('G7 a capped buffer names the whole set',
      api.worklistCountText(), '버퍼 50 / 전체 1,284건');

    S.totalBlank = 50;
    check('G7 a complete buffer says nothing extra',
      api.worklistCountText(), '버퍼 50건');

    S.totalBlank = 0; // stale/optimistic total must never read as "more buffer than exists"
    check('G7 a total below the buffer is not announced as truncation',
      api.worklistCountText(), '버퍼 50건');
  }

  // ---- G8: the filtered count appears only while a filter hides rows -------------
  {
    const { api, S, grids } = build(src);
    api.rebuildGrid(RULE);
    S.gridApi = grids[0];
    S.gridApi.rows = Array.from({ length: 50 }, (_, i) => row(i + 1, 'E', 'P'));
    S.totalBlank = 1284;

    check('G8 no filter, no filter count',
      api.worklistCountText(), '버퍼 50 / 전체 1,284건');

    for (let i = 12; i < 50; i++) S.gridApi.hidden.add(i);
    check('G8 a filter names what it left showing',
      api.worklistCountText(), '필터 12 · 버퍼 50 / 전체 1,284건');
  }

  // ---- G9: a filter that hides everything is not an empty queue ------------------
  {
    const { api, S, el, grids } = build(src);
    api.rebuildGrid(RULE);
    S.gridApi = grids[0];
    S.gridApi.rows = [row(1, 'E', 'P'), row(2, 'E', 'P'), row(3, 'E', 'P'), row(4, 'E', 'P')];
    S.totalBlank = 0; // the exact state that used to print the celebration
    S.gridApi.rows.forEach((_, i) => S.gridApi.hidden.add(i));

    api.updateWorklistOverlay();
    // The panel overlay STANDS DOWN: the grid's own '필터 결과 없음' is already in that space
    // (`GRID_SHARED_OPTIONS.localeText`, shared with the reference panel) and the count lives
    // in the meta line. What it must never do is cover that with a claim about the queue.
    check('G9 the panel overlay stands down for a filter',
      el('worklist-overlay').style.display, 'none');
    check('G9 it does not celebrate work that is merely hidden',
      el('worklist-overlay-text').textContent.includes('처리되었습니다'), false);
    check('G9 nor does it call a filtered view an empty list',
      el('worklist-overlay-text').textContent.includes('표시할 항목이 없습니다'), false);
    check('G9 and the count still says what is held',
      api.worklistCountText(), '필터 0 · 버퍼 4건');

    // Unhide: still nothing to overlay.
    S.gridApi.hidden.clear();
    api.updateWorklistOverlay();
    check('G9 clearing the filter leaves the overlay down',
      el('worklist-overlay').style.display, 'none');

    // A genuinely empty buffer still celebrates.
    S.gridApi.rows = [];
    api.updateWorklistOverlay();
    check('G9 an actually empty queue still says so',
      el('worklist-overlay-text').textContent, '모든 결손이 처리되었습니다!');
  }

  // ---- G10/G11: row-data coordinates, not displayed ones -------------------------
  {
    const { api, S, grids } = build(src);
    api.rebuildGrid(RULE);
    S.gridApi = grids[0];
    // Row-data order is what `partitionQueueRows` produced: keyed first, key-less last.
    S.gridApi.rows = [row(1, 'E', 'P'), row(2, 'E', 'P'), row(3, 'E', ''), row(4, '', '')];
    // A filter hides both keyed rows, so displayed order starts at the key-less block.
    S.gridApi.hidden.add(0);
    S.gridApi.hidden.add(1);

    check('G10 the boundary is the row-data index, not the displayed one',
      api.blankKeyBoundaryIndex(), 2);
    check('G11 the buffer size ignores the filter', api.bufferRowCount(), 4);
    check('G11 and the displayed count still reports the filtered view',
      S.gridApi.getDisplayedRowCount(), 2);

    // No key-less rows at all -> the boundary is the end of the ROW DATA (append).
    S.gridApi.rows = [row(1, 'E', 'P'), row(2, 'E', 'P'), row(3, 'E', 'P')];
    S.gridApi.hidden.clear();
    S.gridApi.hidden.add(0);
    check('G10 with no key-less rows the boundary is the buffer end',
      api.blankKeyBoundaryIndex(), 3);
  }

  // ---- G8/G12 on the reference panel --------------------------------------------
  {
    const { api, S, el, grids } = build(src);
    S.refGridApi = null;
    api.renderRefTable({ columns: ['a', 'b'], rows: [[1, 2], [3, 4], [5, 6]], ms: '11' });
    const g = grids[0];
    S.refGridApi = g;

    check('G8 an unfiltered reference view says nothing about filtering',
      el('reference-meta').textContent, '3건 · 11ms');

    g.hidden.add(1); g.hidden.add(2);
    api.updateRefMeta();
    check('G8 a filtered reference view names what it left showing',
      el('reference-meta').textContent, '필터 1 · 3건 · 11ms');

    // Same columns, new row (the operator moved down the worklist): the view they chose stays.
    g.hidden.clear();
    const beforeFilterResets = g.filterModelSet;
    api.renderRefTable({ columns: ['a', 'b'], rows: [[9, 9]], ms: '4' });
    check('G12 moving to another row in the SAME view keeps their sort and filter',
      g.filterModelSet, beforeFilterResets);
    check('G12 and the new rows are in', g.rows, [[9, 9]]);

    // Different columns = a different question. The old filter cannot apply to it.
    api.renderRefTable({ columns: ['z'], rows: [['v']], ms: '4' });
    check('G12 a different column set drops the previous filter',
      g.filterModelSet, beforeFilterResets + 1);
    check('G12 and the previous sort', g.columnStateReset >= 1, true);
    check('G12 and the columns are replaced by the served ones',
      g.columnDefs.map(d => d.headerName), ['z']);
  }

  return { pass, fail, failed };
}

// ── Defects that must be CAUGHT ─────────────────────────────────────────────────
const DEFECTS = [
  ['the reference panel gets its own parallel grid configuration',
    s => s.replace('defaultColDef: { ...GRID_SORT_FILTER_DEFAULTS },',
                   'defaultColDef: { sortable: true, filter: true, resizable: true },')],
  ['sorting is switched back off on the worklist',
    s => s.replace('  sortable: true,\n  filter: \'agTextColumnFilter\',',
                   '  sortable: false,\n  filter: false,')],
  ['floating filters are dropped',
    s => s.replace('  floatingFilter: true,\n  resizable: true,',
                   '  resizable: true,')],
  ['numbers fall back to lexical order',
    s => s.replace('  if (!Number.isNaN(an) && !Number.isNaN(bn)) return an < bn ? -1 : (an > bn ? 1 : 0);',
                   '')],
  ['blanks sort as the smallest value',
    s => s.replace('if (aBlank || bBlank) return (aBlank && bBlank) ? 0 : (aBlank ? 1 : -1);',
                   'if (aBlank || bBlank) return (aBlank && bBlank) ? 0 : (aBlank ? -1 : 1);')],
  ['reference columns are keyed by label, so duplicates collapse',
    s => s.replace('    field: `c${i}`,', '    field: String(name),')],
  ['the subset is never disclosed',
    s => s.replace('  const body = buffered < total', '  const body = buffered < 0')],
  ['the subset tag is always on, even when nothing was cut',
    s => s.replace('  const body = buffered < total', '  const body = buffered <= total')],
  ['the filtered count is announced even with no filter',
    s => s.replace('const head = shown !== buffered ? `필터 ${shown.toLocaleString()} · ` : \'\';',
                   'const head = `필터 ${shown.toLocaleString()} · `;')],
  ['the buffer size is read off the filtered view',
    s => s.replace('  const total = Math.max(S.totalBlank, buffered);',
                   '  const total = Math.max(S.totalBlank, shown);\n  buffered = shown;')
          .replace('  const buffered = bufferRowCount();\n  const shown',
                   '  let buffered = bufferRowCount();\n  const shown')],
  ['the overlay counts the filtered view, so a filter reads as an empty queue',
    s => s.replace('  const count = bufferRowCount();\n  const shown = S.gridApi ? S.gridApi.getDisplayedRowCount() : 0;',
                   '  const count = S.gridApi ? S.gridApi.getDisplayedRowCount() : 0;\n  const shown = count;')],
  ['the reference panel picks its own empty-result wording',
    s => s.replace('      ...GRID_SHARED_OPTIONS,\n      columnDefs: defs,',
                   '      theme: \'legacy\',\n      columnDefs: defs,')],
  ['the empty-result sentence reverts to the AG-Grid English default',
    s => s.replace('  localeText: { noMatchingRows: \'필터 결과 없음\' },', '')],
  ['the refill boundary goes back to displayed order',
    s => s.replace('  let idx = 0, boundary = -1;\n  S.gridApi.forEachNode((node) => {\n'
                   + '    if (boundary < 0 && node && node.data && !hasDecisionKeys(node.data, S.rule)) boundary = idx;\n'
                   + '    idx++;\n  });\n  return boundary < 0 ? idx : boundary;',
                   '  const count = S.gridApi.getDisplayedRowCount();\n'
                   + '  for (let i = 0; i < count; i++) {\n'
                   + '    const node = S.gridApi.getDisplayedRowAtIndex(i);\n'
                   + '    if (node && node.data && !hasDecisionKeys(node.data, S.rule)) return i;\n'
                   + '  }\n  return count;')],
  ['a new column set inherits the previous view\'s filter',
    s => s.replace('      S.refGridApi.setFilterModel(null);', '')],
  ['every row change wipes the operator\'s filter',
    s => s.replace('    if (signature !== S.refColSignature) {', '    if (true) {')],
  ['the reference meta stops counting what came back',
    s => s.replace('  const total = S.refRowCount;', '  const total = S.refGridApi ? S.refGridApi.getDisplayedRowCount() : 0;')],
];

// ── Controls that must ESCAPE (else a check is reading source text) ─────────────
const CONTROLS = [
  ['local rename inside worklistCountText',
    s => s.replace(/\bbuffered\b/g, 'held')],
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
];

const base = suite(PRISTINE);
if (base.fail) console.error(`\nbaseline failures:\n  ${base.failed.join('\n  ')}`);

quiet = true;
let caught = 0; const escaped = [];
for (const [name, mutate] of DEFECTS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) die(`defect "${name}" changed nothing - its anchor no longer matches. `
    + `An inert mutant is a check that cannot fail.`);
  let r;
  try { r = suite(mutated); } catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) caught++; else escaped.push(name);
}
let controlsCaught = 0; const controlsCaughtNames = [];
for (const [name, mutate] of CONTROLS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) die(`control "${name}" changed nothing - it proves nothing.`);
  let r;
  try { r = suite(mutated); } catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) { controlsCaught++; controlsCaughtNames.push(`${name} (${r.failed[0]})`); }
}
quiet = false;

if (escaped.length) console.error(`\ndefects that escaped:\n  ${escaped.join('\n  ')}`);
if (controlsCaughtNames.length) {
  console.error(`\ncontrols that were caught (a check is reading source text):\n  `
    + controlsCaughtNames.join('\n  '));
}

const bad = base.fail + escaped.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} `
  + `controls escaped.`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
