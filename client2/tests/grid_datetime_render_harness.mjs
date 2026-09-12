/**
 * grid_datetime_render -- the grid's time cells are DRAWN in the viewer's zone and their VALUE
 * stays the string the server served.
 *
 * WHY THIS EXISTS (C-85, owner's own grid). `ledger_events.occurred_at` printed
 * `2026-05-12 15:00:00+00:00`. Measured: `buildColumnDefs` had no datetime branch at all -- the
 * value getter shapes `number` and passes everything else through -- so the UTC digits landed in
 * the cell as if they were the reader's wall clock. C-77 fixed three OTHER screens; this grid was
 * outside that list.
 *
 * WHAT IT SCORES:
 *   A  the two spellings of ONE instant are drawn IDENTICALLY (the offset is honoured, not cut)
 *   B  the VALUE is the served string -- the editor seeds from it and the copy carries it
 *   C  the same one function draws the editable column and the read-only join column
 *   D  nothing is invented: an empty cell stays empty, an unreadable value keeps its own text
 *
 * 🔴 B IS MEASURED ON THE REAL COPY ROUTE, not by reading grid.js. `clipboard.js`'s
 *    `getRangeSelectedTSV` is driven with a stubbed AG-Grid api, so "the copy is the original"
 *    is an observation of the function the operator's Ctrl+C reaches.
 *
 * 🔴 EVERY ASSERTION IS WOKEN BY A MUTANT, and the sweep is ZONE-INDEPENDENT: it never asserts a
 *    literal local spelling (that would pass only on the machine that wrote it). It asserts that
 *    two spellings agree, that the painted text carries no offset, and that it equals what
 *    `server_time.js` itself returns.
 *
 * IT IMPORTS ITS SUBJECT -- whole-module mutants via `lib/probe.mjs`. Nothing is sliced.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

// `clipboard.js` reads `elements.copyHeaderToggle`, and `dom.js` resolves that through
// `document.getElementById`. A getter, so importing is safe -- but the copy route CALLS it.
//
// 🔴 THE STUB HAS TO BE WHOLE ENOUGH TO BE BELIEVED. `utils.js` (pulled in by clipboard.js)
//    guards its listener with `typeof document !== 'undefined'` and then calls
//    `document.addEventListener` -- a stub carrying only the one method this harness wants turns
//    that guard from skipped into a TypeError, which is the failure its own comment records.
//    `window` is deliberately left undefined: its guard then skips, as it does today.
if (typeof globalThis.document === 'undefined') {
  globalThis.document = {
    hidden: false,
    addEventListener() {}, removeEventListener() {},
    getElementById: () => null, querySelector: () => null,
  };
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_PATH = path.join(HERE, '..', 'src', 'grid.js');

const { state } = await import('../src/state.js');
const { localStamp } = await import('../src/server_time.js');
const { getRangeSelectedTSV } = await import('../src/clipboard.js');

// 🔴 THE SHAPE THE ROUTE ACTUALLY SENDS, measured 2026-09-13 on
//    `/tables/ledger_events/data`: a SPACE separator and a `+00:00` offset, and
//    `column_types.occurred_at === 'datetime'` while `created_at`/`updated_at` are NOT typed at
//    all -- they ride the row envelope. Both have to be covered or half the times stay raw.
const SERVED = '2026-08-01 15:28:47+00:00';
const SAME_Z = '2026-08-01T15:28:47Z';
const UNREADABLE = 'not a time at all';

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

/** One table's worth of `/schema`, staged on the shared state object the grid reads. */
function stage() {
  state.currentTable = 'ledger_events';
  state.currentColumns = ['id', 'occurred_at', 'qty', 'note', 'created_at', 'updated_at'];
  state.currentColumnTypes = { id: 'string', occurred_at: 'datetime', qty: 'number', note: 'string' };
  state.currentBusinessKey = 'id';
  state.currentCompositeKeySources = [];
  state.currentVirtualColumns = [
    { name: 'right_seen_at', type: 'datetime', editable: false,
      right_table: 'dt_job', rule: 'r1', unresolved_label: '미상' },
    { name: 'right_qty', type: 'number', editable: false,
      right_table: 'dt_job', rule: 'r1', unresolved_label: '미상' },
  ];
  state.currentJoinResolvedColumns = [];
  state.pendingTxEdits = {};
  state.selectedCellsMap = {};
  state.dragStartCell = null;
  state.dragEndCell = null;
  state.txModeActive = false;
}

const row = () => ({
  row_id: 'r1',
  created_at: SERVED,
  updated_at: SERVED,
  data: {
    id: { value: 'r1' },
    occurred_at: { value: SERVED },
    qty: { value: 7 },
    note: { value: 'x' },
    right_seen_at: { value: SERVED },
    right_qty: { value: 3 },
  },
});

const draw = (def, value) => def.valueFormatter({ value, data: row(), colDef: def });

function suite(M) {
  const before = { pass, fail };
  stage();
  const defs = new Map(M.buildColumnDefs().map((d) => [d.field, d]));
  const dt = defs.get('occurred_at');
  const ro = defs.get('right_seen_at');

  // ── A: one instant, one drawing ──────────────────────────────────────────────────────
  ok(!!dt && typeof dt.valueFormatter === 'function',
    'A1 a declared `datetime` column has a formatter at all -- this is what was missing');
  if (dt && typeof dt.valueFormatter === 'function') {
    const shownServed = draw(dt, SERVED);
    const shownZ = draw(dt, SAME_Z);
    ok(shownServed === shownZ,
      `A2 two spellings of ONE instant are drawn the same -- served [${shownServed}] vs Z [${shownZ}]`);
    ok(!/[+-]\d\d:\d\d$/.test(String(shownServed)) && !/Z$/.test(String(shownServed)),
      `A3 the offset never reaches the cell -- drawn [${shownServed}]`);
    ok(String(shownServed) !== SERVED,
      'A4 the drawn text is not the served string -- something was actually converted');
    ok(String(shownServed) === localStamp(SERVED),
      'A5 the drawing is `server_time.js`s answer, not a second parse in the grid');
  } else {
    ok(false, 'A2 two spellings of ONE instant are drawn the same');
    ok(false, 'A3 the offset never reaches the cell');
    ok(false, 'A4 the drawn text is not the served string');
    ok(false, 'A5 the drawing is `server_time.js`s answer');
  }

  // ── B: the value is the original, on the routes that carry it ────────────────────────
  ok(!!dt && dt.valueGetter({ data: row(), node: { rowIndex: 0 } }) === SERVED,
    'B1 the VALUE is the served string -- the editor seeds from this, not from the drawing');

  state.selectedCellsMap = { '0_occurred_at': { rowIndex: 0, colId: 'occurred_at' } };
  state.gridApi = {
    getColumnState: () => state.currentColumns.map((c) => ({ colId: c, hide: false })),
    getDisplayedRowAtIndex: (i) => (i === 0 ? { data: row() } : null),
    getFocusedCell: () => null,
  };
  const copied = getRangeSelectedTSV();
  state.gridApi = null;
  state.selectedCellsMap = {};
  ok(copied === SERVED,
    `B2 the COPIED value is the original offset ISO -- got [${copied}]`);

  // ── C: one function for both seats ───────────────────────────────────────────────────
  ok(!!ro && typeof ro.valueFormatter === 'function' && ro.editable === false,
    'C1 the read-only join column declared `datetime` also has a formatter');
  ok(!!ro && !!dt && ro.valueFormatter === dt.valueFormatter,
    'C2 it is the SAME function object -- the two seats cannot drift into two spellings');
  ok(!!defs.get('created_at') && typeof defs.get('created_at').valueFormatter === 'function',
    'C3 the envelope times are covered too -- they are not in `column_types` and would stay raw');
  ok(!!defs.get('updated_at') && typeof defs.get('updated_at').valueFormatter === 'function',
    'C4 ... both of them');

  // ── D: nothing invented on a column that is not a time, nothing invented in a gap ────
  ok(!!defs.get('note') && defs.get('note').valueFormatter === undefined,
    'D1 a `string` column gets no time formatter');
  ok(!!defs.get('qty') && defs.get('qty').valueFormatter === undefined,
    'D2 a `number` column keeps its own display rule and gets no time formatter');
  ok(!!defs.get('right_qty') && defs.get('right_qty').valueFormatter === undefined,
    'D3 a read-only `number` join column likewise');
  if (dt && typeof dt.valueFormatter === 'function') {
    ok(draw(dt, '') === '' && draw(dt, null) === null,
      'D4 an empty time cell stays EMPTY -- the dash is not painted into a blank cell');
    ok(draw(dt, UNREADABLE) === UNREADABLE,
      'D5 an unreadable value keeps its own text -- absence and unreadable stay different');
  } else {
    ok(false, 'D4 an empty time cell stays EMPTY');
    ok(false, 'D5 an unreadable value keeps its own text');
  }

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the real module -------------------------------------------------');
const REAL = await import('../src/grid.js');
suite(REAL);

// -- mutants ---------------------------------------------------------------------------
const DEFECTS = [
  ['the formatter is not installed on the stored column',
    s => s.replace('      valueFormatter: isTimeColumn(col, colType) ? timeCellFormatter : undefined,\n', '')],
  ['the local spelling becomes the VALUE (the one the editor sends back)',
    s => s.replace('        return colType === \'number\' ? numericDisplayValue(val) : val;',
                   '        return colType === \'number\' ? numericDisplayValue(val)\n'
                   + '          : (isTimeColumn(col, colType) ? timeCellFormatter({ value: val }) : val);')],
  ['the offset is CUT instead of converted',
    s => s.replace('  const shown = localStamp(val);\n  return shown === NO_TIME ? val : shown;',
                   '  return String(val).slice(0, 19);')],
  ['the read-only seat grows its own formatter',
    s => s.replace('      valueFormatter: isTime ? timeCellFormatter : undefined,',
                   '      valueFormatter: isTime ? ((p) => localStamp(p.value)) : undefined,')],
  // 🔴 ONE MUTANT FOR BOTH D4 AND D5, because one line answers both. The first cut of this
  //    sweep had a second mutant that deleted an `if (val === '' ...) return val;` guard, and it
  //    ESCAPED -- `localStamp('')` is already `NO_TIME`, so the fallback returned the same
  //    answer and the guard was unreachable as behaviour. The guard is gone rather than the
  //    mutant: scoring a branch nobody takes is how a harness reports coverage it does not have.
  ['the envelope times drop out of the predicate',
    s => s.replace("const SYSTEM_TIME_COLUMNS = Object.freeze(['created_at', 'updated_at']);",
                   'const SYSTEM_TIME_COLUMNS = Object.freeze([]);')],
  ['an unreadable value is painted as the dash',
    s => s.replace('  return shown === NO_TIME ? val : shown;', '  return shown;')],
];
const CONTROLS = [
  ['a local rename inside the formatter', s => s
    .replace('function timeCellFormatter(params) {\n  const val = params ? params.value : undefined;',
             'function timeCellFormatter(params) {\n  const raw = params ? params.value : undefined;\n  const val = raw;')],
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
];

async function scoreMutant(mutate, tag) {
  try {
    return suite((await loadWithProbe(SRC_PATH, { mutate, tag })).module);
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
for (const [name, mutate] of DEFECTS) {
  const r = await scoreMutant(mutate, 'gridtime');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  const r = await scoreMutant(mutate, 'gridtimec');
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
