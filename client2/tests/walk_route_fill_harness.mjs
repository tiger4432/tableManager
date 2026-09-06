// 「경로를 누르면 follow 가 채워진다」 — and the two ways it silently did not.
//
// WHY THIS EXISTS. Measured live 2026-09-06: clicking a derived route filled `hops` and ticked
// NOTHING. Two independent causes, and neither was visible to any check that existed:
//   ① the derivation speaks bare names (`observed`) and the checkboxes carry the declared
//      spelling (`observed@1`), so no name matched;
//   ② the second-hop predicate had no checkbox at all, because the list only offers predicates
//      whose subject is the START type — `observed` belongs to `die`.
// The import test and the request test were both GREEN through all of it: the wire was correct
// and only the screen was wrong. So this scores the screen's own decisions.
//
// IT IMPORTS ITS SUBJECT. Those decisions were closures inside `boot()`, reachable only by
// standing up a DOM; they now live in `src/walk/derive.js` and this file imports the same two
// functions the screen calls. Mutants are whole modules from `lib/probe.mjs`.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'walk', 'derive.js');

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
}

// The declaration's own spelling, and a route as `pathsBetween` actually returns it.
// 🔴 These are the LIVE shapes, not invented ones: the walk screen's follow boxes read
//    `inspected@1 · measures@1 · processed_with@1 · register@1` for a `wafer@1` seed, and the
//    two-hop route to `defect` is `[inspected, observed]`.
const DECLARED = ['inspected@1', 'measures@1', 'processed_with@1', 'register@1', 'observed@1',
  'of_kind@1', 'bonded_from@1'];
const FROM_WAFER = ['inspected@1', 'measures@1', 'processed_with@1', 'register@1'];
const ROUTE_2HOP = ['inspected', 'observed'];
const ROUTE_3HOP = ['measures', 'leads_to', 'of_kind'];

// 🔴 The served declaration's own shape, measured 2026-09-06: three entities carry
//    `class: "static"` and the other six carry NO class field at all. The absence is the point,
//    so it is written as absence rather than as `class: null`.
const ENTITIES = [
  { type: 'defect_kind@1' , class: 'static' }, { type: 'quantity@1', class: 'static' },
  { type: 'recipe@1', class: 'static' },
  { type: 'defect@1' }, { type: 'die@1' }, { type: 'dtjob@1' },
  { type: 'lot@1' }, { type: 'lot_slot@1' }, { type: 'wafer@1' },
];
// Routes as `pathsBetween` returns them; the first is the one measured live to answer with the
// seed alone (1 node, 0 under a collect) while `wafer>die>defect` answered with 121.
const ROUTES = [
  { hops: 3, follow: ['measures', 'leads_to', 'of_kind'],
    chain: ['wafer', 'quantity', 'defect_kind', 'defect'] },
  { hops: 2, follow: ['inspected', 'observed'], chain: ['wafer', 'die', 'defect'] },
  { hops: 1, follow: ['leads_to'], chain: ['defect_kind', 'quantity'] },
  { hops: 1, follow: ['measures'], chain: ['quantity', 'die'] },
];

function suite(M) {
  const before = { pass, fail };

  const filled = M.followFromRoute(DECLARED, ROUTE_2HOP);
  ok(filled.length === 2, 'F1 a two-hop route fills TWO predicates, not zero');
  ok(filled.includes('inspected@1') && filled.includes('observed@1'),
    'F2 ... and they are the DECLARED spellings, matched on the bare name');

  // 🔴 The control for F1/F2: a route naming something the declaration does not have must fill
  //    nothing. Without it, a function that returned every declared name would pass both above.
  ok(M.followFromRoute(DECLARED, ['not_a_predicate']).length === 0,
    'F3 a predicate the declaration does not carry fills nothing');
  ok(M.followFromRoute(DECLARED, []).length === 0, 'F4 an empty route fills nothing');

  // A three-hop route whose middle predicate is undeclared here: the two that exist still land.
  ok(M.followFromRoute(DECLARED, ROUTE_3HOP).join() === 'measures@1,of_kind@1',
    'F5 a longer route fills every hop the declaration knows');

  const shown = M.followChoices(FROM_WAFER, DECLARED, new Set(filled));
  ok(shown.includes('observed@1'),
    'C1 a later-hop predicate that is SELECTED becomes visible, though it does not start here');
  ok(FROM_WAFER.every((n) => shown.includes(n)),
    'C2 ... and the start-type options all stay — the filter is widened, not replaced');
  ok(new Set(shown).size === shown.length, 'C3 ... with no duplicate row for the overlap');

  // 🔴 The control for C1: nothing selected must not widen the list. Otherwise "show the
  //    selected too" and "show everything" are the same function and C1 proves nothing.
  ok(M.followChoices(FROM_WAFER, DECLARED, new Set()).join() === FROM_WAFER.join(),
    'C4 with nothing selected the list is exactly the start-type set');

  ok(M.bareName('observed@1') === 'observed' && M.bareName('observed') === 'observed',
    'B1 the version suffix is dropped, and a bare name survives unchanged');

  // 🔴 THE STATIC FILTER. The walk refuses a static -> not-static step, so offering one is
  //    offering a route that answers with the seed alone. The server's predicate is
  //    `class === 'static'` and a type with NO class is dynamic to it, so these entities carry
  //    the live shape: three with the class, the rest with the field absent entirely.
  const stat = M.staticTypes(ENTITIES);
  ok(stat.has('defect_kind') && stat.has('quantity') && stat.has('recipe') && stat.size === 3,
    'S1 exactly the types declaring class static are static');
  ok(!stat.has('wafer') && !stat.has('defect'),
    'S2 a type with NO class is not static — that is the walk\'s own rule, not an unknown');

  const kept = M.keepWalkableRoutes(ENTITIES, ROUTES);
  const names = kept.map((r) => r.chain.join('>'));
  ok(!names.includes('wafer>quantity>defect_kind>defect'),
    'S3 a route with a static -> not-static step is dropped');
  ok(names.includes('wafer>die>defect'),
    'S4 ... and a route that never leaves a static type is untouched');
  ok(names.includes('defect_kind>quantity'),
    'S5 static -> static stays — the mechanism chain is what defect_kind exists to answer');
  ok(!names.includes('quantity>die'),
    'S6 a static step INTO a type with no class is dropped, which is the corrected rule');
  // 🔴 The control for S3/S6: with nothing declared static, nothing may be dropped. Without it,
  //    a filter that returned [] would satisfy every "is dropped" assertion above.
  ok(M.keepWalkableRoutes([], ROUTES).length === ROUTES.length,
    'S7 with no static types declared, every route survives');

  // 🔴 THE RESULT TABLE'S COLUMNS. The gate the ruling asked for is "add a key to the
  //    declaration and the column follows, without editing code" - so the declaration is the
  //    only thing that moves between T1 and T3.
  const DIE = [{ type: 'die@1', keys: ['mat_id', 'x', 'y', 'mat_type'] },
    { type: 'wafer@1', keys: ['wafer'] }];
  ok(M.tableColumns(DIE, 'die', []).join(',') === '깊이,mat_id,x,y,mat_type,라벨,id',
    'T1 the columns are depth, the declared keys in order, label, then id');
  ok(M.tableColumns(DIE, 'wafer', []).join(',') === '깊이,wafer,라벨,id',
    'T2 a different type brings its OWN keys, which is why sections are per type');
  const GREW = [{ type: 'die@1', keys: ['mat_id', 'x', 'y', 'mat_type', 'lot'] }];
  ok(M.tableColumns(GREW, 'die', []).includes('lot'),
    'T3 a key added to the declaration adds a column, with no edit here');
  ok(M.tableColumns(DIE, 'die', ['gate', 'unit']).join(',')
    === '깊이,mat_id,x,y,mat_type,gate,unit,라벨,id',
    'T4 qualifiers that arrived become columns too, after the keys');
  // 🔴 The control: a type the declaration does not carry must not invent identity columns.
  ok(M.tableColumns(DIE, 'unknown_type', []).join(',') === '깊이,라벨,id',
    'T5 an undeclared type gets no key columns rather than borrowed ones');
  ok(M.tableColumns(DIE, 'die@1', []).includes('mat_id'),
    'T6 the version suffix does not hide the declaration from the lookup');

  // ── S-13: 「잘렸다」 옆의 「«얼마»에서」 ─────────────────────────────────────────
  // 🔴 화면은 `truncated` 를 읽어 절단을 «말할 수» 있었는데 `limits` 를 안 읽어 예산을
  //    «못 말했습니다». 그러면 「많아서 잘렸다」와 「상한이 낮아서 잘렸다」가 같아 보입니다.
  ok(M.cutBudgets(['nodes'], { nodes: 400, max_hops: 12 }).join(',') === 'nodes 400',
    'U1 a cut axis carries the budget it was cut at');
  // 🔴 이름이 «다릅니다» — `limits` 에는 `depth` 가 없고 `max_hops` 가 있습니다.
  //    그대로 찾으면 «언제나 없음»이 되어 조용히 축 이름만 그리던 때로 돌아갑니다.
  ok(M.cutBudgets(['depth'], { nodes: 400, max_hops: 12 }).join(',') === 'depth 12',
    'U2 depth reads its budget from max_hops, which is spelled differently');
  // ⚠️ 없는 예산을 «지어내지» 않습니다. 옛 서버는 `limits` 를 안 보냅니다.
  ok(M.cutBudgets(['nodes', 'edges'], null).join(',') === 'nodes,edges',
    'U3 an older server without limits still names the axes, and invents no number');
  ok(M.cutBudgets(['nodes'], { nodes: null }).join(',') === 'nodes',
    'U4 a null budget is not drawn as a budget');
  ok(M.cutBudgets([], { nodes: 400 }).length === 0,
    'U5 CONTROL: nothing cut yields nothing — the budget alone is not a truncation');

  return { fail: fail - before.fail };
}

console.log('-- the screen\'s two decisions ---------------------------------------');
suite(await import('../src/walk/derive.js'));

const base = { pass, fail };
failedNames.length = 0;

// -- mutants -----------------------------------------------------------------------------
// ③ of the Lead's gate: deleting the filling line must turn ① red.
const DEFECTS = [
  ['the spellings are compared directly again, so nothing is ticked',
    (s) => s.replace('  const wanted = new Set((routeFollow || []).map(bareName));\n'
      + '  return (declaredNames || []).filter((name) => wanted.has(bareName(name)));',
    '  const wanted = new Set(routeFollow || []);\n'
      + '  return (declaredNames || []).filter((name) => wanted.has(name));')],
  ['the fill returns nothing at all',
    (s) => s.replace('  return (declaredNames || []).filter((name) => wanted.has(bareName(name)));',
      '  return [];')],
  ['the later-hop predicate stops being shown',
    (s) => s.replace('  return [...new Set([...(fromStartType || []), ...extra])];',
      '  return [...(fromStartType || [])];')],
  ['the column list stops asking the declaration and hardcodes what it saw once',
    (s) => s.replace('  const declared = (found && found.keys) || [];',
      "  const declared = ['mat_id', 'x', 'y', 'mat_type'];")],
  ['the columns stop carrying the qualifiers that arrived',
    (s) => s.replace("  return ['깊이', ...declared, ...(qualifierNames || []), '라벨', 'id'];",
      "  return ['깊이', ...declared, '라벨', 'id'];")],
  ['the list widens to everything instead of to what is selected',
    (s) => s.replace('  const extra = (declaredNames || []).filter((name) => picked.has(name));',
      '  const extra = (declaredNames || []);')],
  // Gate ④ of the 22:00 ruling: deleting the filtering line must turn the first assertion red.
  ['the refused routes are offered again',
    (s) => s.replace('      if (statics.has(here) && !statics.has(next)) return false;', '')],
  ['a type with no class counts as static, so the corrected rule is undone',
    (s) => s.replace(".filter((e) => e && e.class === 'static')",
      ".filter((e) => !e || e.class !== 'dynamic')")],
  ['the filter drops any route that TOUCHES a static type, killing the mechanism chain',
    (s) => s.replace('      if (statics.has(here) && !statics.has(next)) return false;',
      '      if (statics.has(here) || statics.has(next)) return false;')],
];
const CONTROLS = [
  ['a local rename', (s) => s.replace('  const wanted = new Set((routeFollow || []).map(bareName));',
    '  const want = new Set((routeFollow || []).map(bareName));')
    .replace('  return (declaredNames || []).filter((name) => wanted.has(bareName(name)));',
      '  return (declaredNames || []).filter((name) => want.has(bareName(name)));')],
  ['comments stripped', (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

quiet = true;
let caught = 0; const escaped = [];
async function score(name, mutate, tag) {
  try { return suite((await loadWithProbe(SRC, { mutate, tag })).module); }
  catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      quiet = false; console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
    }
    return { fail: 1 };
  }
}
console.log('\n-- defect mutants (each must be CAUGHT) ------------------------------');
for (const [name, mutate] of DEFECTS) {
  const r = await score(name, mutate, 'wkfill');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escaped.push(name); console.log(`  ESCAPED ${name}`); }
}
console.log('\n-- control mutants (each must ESCAPE) --------------------------------');
for (const [name, mutate] of CONTROLS) {
  const r = await score(name, mutate, 'wkfillc');
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { escaped.push(`control caught: ${name}`); console.log(`  CAUGHT  ${name} <- control caught`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${failedNames.join('\n  ')}`);
if (escaped.length) console.error(`\nwrong verdicts:\n  ${escaped.join('\n  ')}`);

console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught; ${CONTROLS.length - escaped.filter((e) => e.startsWith('control')).length}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(base.fail === 0 && escaped.length === 0 ? 0 : 1);
