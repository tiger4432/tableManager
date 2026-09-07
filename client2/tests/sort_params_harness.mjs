/**
 * 🔢 A-6 — the sort that goes on the wire, scored by IMPORTING the module that spells it.
 *
 * WHAT THIS EXISTS FOR. `order_by`/`order_desc` were written out by hand in TWO places
 * (`api.fetchData` and `timeline.navigatorStep3`), both as
 * `${sortLatest ? 'updated_at' : 'row_id'}` — one decision, two copies. A header sort now
 * changes that answer, and the day the two copies disagree the grid shows one order while a
 * row jump computes its offset in another: a wrong scroll position with nothing on screen
 * saying so. `grid.sortParams` is the single spelling and this file scores it.
 *
 * 🔴 THE TWO OLD ANSWERS ARE PINNED AS LITERALS, and that is the point of A1/A2. The whole
 *    round is "add a third case without moving the other two", and a harness that recomputed
 *    the expectation from the same expression could not see them move.
 *
 * Run:  node client2/tests/sort_params_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const GRID_PATH = join(HERE, '..', 'src', 'grid.js');

let pass = 0;
const failures = [];
function ok(name, cond, detail = '') {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
}
function eq(name, expected, actual) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  ok(name, a === e, `expected ${e}, got ${a}`);
}

// ── the browser the module expects ────────────────────────────────────────────────────────
// 🔴 `elements.sortLatestToggle` is a GETTER over `document.getElementById`, so the toggle is
//    staged by answering that call — not by assigning a property the product never reads.
const toggle = { checked: false };
function installDom() {
  globalThis.window = {
    location: { port: '', origin: '', protocol: 'http:', host: '', search: '' },
    addEventListener() {}, removeEventListener() {}, devicePixelRatio: 1,
  };
  globalThis.document = {
    getElementById: (id) => (id === 'sort-latest-toggle' ? toggle : null),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {}, removeEventListener() {},
    createElement: () => ({ style: {}, classList: { add() {}, remove() {} },
                            appendChild() {}, setAttribute() {} }),
  };
  globalThis.performance = { now: () => 0 };
}

async function score(mutate) {
  pass = 0; failures.length = 0;
  installDom();
  toggle.checked = false;

  // The subject is loaded through the shared helper so a mutation reaches THE CODE THAT RUNS.
  // Nothing is sliced: the whole file is copied, accessors are appended, and the copy is
  // asserted to begin with the original's bytes.
  const { probe } = await loadWithProbe(GRID_PATH, {
    expose: ['sortParams', 'sortQueryTail', 'holdsWholeTable'],
    mutate,
    tag: 'sortparams',
  });
  // `state` is a singleton this harness and the subject share -- the probe copy sits beside
  // the original, so its `./state.js` is the same module instance imported here.
  const { state } = await import('../src/state.js');

  // ══ the two answers that must not move ══════════════════════════════════════════════
  state.serverSort = null;
  toggle.checked = false;
  eq('A1 no header sort, 최신순 off -> row_id ascending, the pre-A-6 spelling',
     '&order_by=row_id&order_desc=false', probe.sortQueryTail());
  toggle.checked = true;
  eq('A2 no header sort, 최신순 on -> updated_at descending, the pre-A-6 spelling',
     '&order_by=updated_at&order_desc=true', probe.sortQueryTail());

  // ══ the third case, which is the round ══════════════════════════════════════════════
  state.serverSort = { colId: 'dt_lot', desc: true };
  eq('A3 a header sort names ITS column, not the toggle\'s',
     '&order_by=dt_lot&order_desc=true', probe.sortQueryTail());
  // 🔴 THE TOGGLE IS ON IN A3 AND A4. If the header sort merely ADDED a parameter, or if the
  //    toggle still won, these would read `updated_at` — so this pins WHICH ONE ANSWERS, not
  //    merely that both are readable.
  state.serverSort = { colId: 'dt_lot', desc: false };
  eq('A4 ...and its DIRECTION, with the toggle still on',
     '&order_by=dt_lot&order_desc=false', probe.sortQueryTail());

  // A swap-proof check: the pair must not be readable in either order by accident.
  state.serverSort = { colId: 'order_desc', desc: true };
  ok('A5 a column named like the other parameter is still carried as the COLUMN',
     probe.sortQueryTail() === '&order_by=order_desc&order_desc=true',
     probe.sortQueryTail());

  // ══ the name on the wire is a NAME ══════════════════════════════════════════════════
  state.serverSort = { colId: 'a&b=c', desc: false };
  ok('A6 the column name is encoded, so it cannot become a second parameter',
     probe.sortQueryTail() === '&order_by=a%26b%3Dc&order_desc=false',
     probe.sortQueryTail());

  // ══ the structured form and the query tail cannot disagree ══════════════════════════
  state.serverSort = { colId: 'event_time', desc: true };
  const p = probe.sortParams();
  eq('A7 sortParams and sortQueryTail answer with the same column',
     `&order_by=${p.orderBy}&order_desc=${p.orderDesc}`, probe.sortQueryTail());
  ok('A8 ...and orderDesc is a boolean, not the string a caller would interpolate',
     typeof p.orderDesc === 'boolean', typeof p.orderDesc);

  // ══ a truthy-but-empty column may not be sent as an order ═══════════════════════════
  state.serverSort = null;
  toggle.checked = false;
  ok('A9 with no header sort the answer is never blank',
     probe.sortParams().orderBy === 'row_id');

  // ══ WHO ANSWERS THE SORT: the grid, or the table ════════════════════════════════════
  // 🔴 THIS BLOCK EXISTS BECAUSE THE FIRST VERSION GOT IT WRONG AND THE BROWSER CAUGHT IT.
  //    The predicate was `state.allDataLoaded` alone, and that flag is set by the 「Load All」
  //    button and nothing else — so a 907-row table, complete in its first page, fired two
  //    requests for rows it already held. An unmeasured predicate is what let that through.
  const holds = (patch) => {
    Object.assign(state, patch);
    return probe.holdsWholeTable();
  };
  ok('B1 「Load All」 -> the grid holds the table',
     holds({ allDataLoaded: true, hasMoreData: false, viewMode: 'pagination', currentSkip: 0 }) === true);
  ok('B2 a short first page IS the whole table, even without that flag',
     holds({ allDataLoaded: false, hasMoreData: false, viewMode: 'pagination', currentSkip: 0 }) === true);
  ok('B3 ...but the LAST page of many is not — it is also "no more data"',
     holds({ allDataLoaded: false, hasMoreData: false, viewMode: 'pagination', currentSkip: 33939 }) === false);
  ok('B4 a full first page of many is not the table',
     holds({ allDataLoaded: false, hasMoreData: true, viewMode: 'pagination', currentSkip: 0 }) === false);
  ok('B5 infinite scrolling that reached the end holds everything, at any skip',
     holds({ allDataLoaded: false, hasMoreData: false, viewMode: 'infinite', currentSkip: 33939 }) === true);
  ok('B6 ...and infinite scrolling that has not is still partial',
     holds({ allDataLoaded: false, hasMoreData: true, viewMode: 'infinite', currentSkip: 2000 }) === false);

  state.serverSort = null;
  state.allDataLoaded = false;
  state.hasMoreData = true;
  state.viewMode = 'pagination';
  state.currentSkip = 0;
  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

// ── Mutations ─────────────────────────────────────────────────────────────────────────────
// Each must turn this harness RED. The anchors are the shipped text; a mutant that does not
// apply is refused by `loadWithProbe` (exit 2), never scored as a pass.
const MUTATIONS = [
  ['M1 the header sort is ignored and the toggle answers again',
   s => s.replace('  if (state.serverSort) {\n    return { orderBy: state.serverSort.colId, orderDesc: !!state.serverSort.desc };\n  }',
                  '  if (false) {\n    return { orderBy: state.serverSort.colId, orderDesc: !!state.serverSort.desc };\n  }')],
  ['M2 the direction is dropped and every header sort ascends',
   s => s.replace('orderDesc: !!state.serverSort.desc', 'orderDesc: false')],
  ['M3 the column name stops being encoded',
   s => s.replace('&order_by=${encodeURIComponent(orderBy)}&order_desc=${orderDesc}',
                  '&order_by=${orderBy}&order_desc=${orderDesc}')],
  ['M4 the toggle\'s two answers are swapped',
   s => s.replace("orderBy: sortLatest ? 'updated_at' : 'row_id'",
                  "orderBy: sortLatest ? 'row_id' : 'updated_at'")],
  // 🔴 THE DEFECT THIS ROUND SHIPPED AND THE BROWSER CAUGHT, put back verbatim.
  ['M5 「holds the whole table」 goes back to reading the Load-All flag alone',
   s => s.replace('  if (state.allDataLoaded) return true;\n  if (state.hasMoreData) return false;\n  return state.viewMode === \'infinite\' || state.currentSkip === 0;',
                  '  return state.allDataLoaded;')],
  ['M6 the last page of many is mistaken for the whole table',
   s => s.replace("return state.viewMode === 'infinite' || state.currentSkip === 0;",
                  'return true;')],
];

if (process.argv.includes('--mutate')) {
  console.log('\n── MUTATIONS (each must turn the harness RED) ──');
  let caught = 0;
  const green = [];
  for (const [name, apply] of MUTATIONS) {
    let r;
    try { r = await score(apply); }
    catch (e) { console.log(`  ~ ${name} -> harness THREW (${e && e.message})`); caught++; continue; }
    if (r.failures.length === 0) { console.log(`  ✗ ${name} -> STILL GREEN`); green.push(name); continue; }
    caught++;
    console.log(`  ✓ ${name} -> ${r.failures.length} failure(s): ${r.failures.sort().join(' ')}`);
  }
  console.log(`\nmutations: ${caught}/${MUTATIONS.length} caught (${MUTATIONS.length} declared)`);
  if (green.length) { console.log(`  ✗ undetected: ${green.join(' | ')}`); process.exit(1); }
}

process.exit(base.failures.length === 0 ? 0 : 1);
