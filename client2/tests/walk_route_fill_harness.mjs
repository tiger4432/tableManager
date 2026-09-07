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
  const colNames = (cols) => cols.map((c) => c.name).join(',');
  const DIE = [{ type: 'die@1', keys: ['mat_id', 'x', 'y', 'mat_type'] },
    { type: 'wafer@1', keys: ['wafer'] }];
  ok(colNames(M.tableColumns(DIE, 'die', [])) === '깊이,mat_id,x,y,mat_type,라벨,id',
    'T1 the columns are depth, the declared keys in order, label, then id');
  ok(colNames(M.tableColumns(DIE, 'wafer', [])) === '깊이,wafer,라벨,id',
    'T2 a different type brings its OWN keys, which is why sections are per type');
  const GREW = [{ type: 'die@1', keys: ['mat_id', 'x', 'y', 'mat_type', 'lot'] }];
  ok(colNames(M.tableColumns(GREW, 'die', [])).includes('lot'),
    'T3 a key added to the declaration adds a column, with no edit here');
  ok(colNames(M.tableColumns(DIE, 'die', ['gate', 'unit']))
    === '깊이,mat_id,x,y,mat_type,gate,unit,라벨,id',
    'T4 qualifiers that arrived become columns too, after the keys');
  // 🔴 The control: a type the declaration does not carry must not invent identity columns.
  ok(colNames(M.tableColumns(DIE, 'unknown_type', [])) === '깊이,라벨,id',
    'T5 an undeclared type gets no key columns rather than borrowed ones');
  ok(colNames(M.tableColumns(DIE, 'die@1', [])).includes('mat_id'),
    'T6 the version suffix does not hide the declaration from the lookup');

  // ── 판정 130-C ㉡: the layout has ONE author ────────────────────────────────────
  // 🔴 THE DEFECT THIS CLOSES WAS NOT IN THIS FILE. `main.js` re-derived the identity
  //    columns out of the name list by arithmetic — `cols.slice(1, cols.length - 2 -
  //    qualNames.length)` — which is right while there are exactly two groups and wrong
  //    the day there are three. It fails SILENTLY, and worse: the wrong rendering (an
  //    empty attribute cell) is also the CORRECT rendering for an attribute the walk never
  //    reached, so no pixel gives it away.
  //
  // ⚠️ THE ATTRIBUTE FIXTURE IS HAND-HELD. `/declaration` publishes {type, keys, class}
  //    today (server/ledger_trace_router.py), so nothing on the live wire carries
  //    `attributes` yet. This is the shape S-52 will publish, written out here so the
  //    layout can be scored BEFORE it lands rather than after it breaks.
  const WITH_ATTRS = [{ type: 'die@1', keys: ['mat_id', 'x'], attributes: ['grade', 'lot'] }];
  ok(colNames(M.tableColumns(WITH_ATTRS, 'die', ['gate']))
    === '깊이,mat_id,x,gate,grade,lot,충돌,라벨,id',
    'T7 declared attributes are columns of their own, after the qualifiers and before 라벨');
  ok(M.tableColumns(WITH_ATTRS, 'die', ['gate']).map((c) => c.kind).join(',')
    === 'depth,key,key,qualifier,attribute,attribute,conflicts,label,id',
    'T8 every column says WHERE it reads from — that is what removes the arithmetic');
  // 🔴 THE SHAPE FOLLOWS THE DECLARATION, NOT THE ANSWER. If the disagreement column only
  //    appeared once some node disagreed, the same walk would draw two different tables and
  //    an operator would never learn that the question is asked at all.
  ok(M.tableColumns(DIE, 'die', []).every((c) => c.kind !== 'conflicts'),
    'T10 a type declaring no attributes gets no disagreement column either');
  // 🔴 THE BYTE-IDENTICAL GATE. Today's declaration carries no `attributes`, so the drawn
  //    table must be exactly what it was. T1-T6 are that gate; this states it as one line.
  ok(colNames(M.tableColumns(DIE, 'die', ['gate'])) === '깊이,mat_id,x,y,mat_type,gate,라벨,id'
    && M.tableColumns(DIE, 'die', ['gate']).every((c) => c.kind !== 'attribute'),
    'T9 a declaration without attributes leaves the table exactly as it is');

  // ── the other half of the same decision: where a column READS ───────────────────
  // 🔴 THE DISCRIMINATING NODE. `keys` and `attributes` hold DIFFERENT names here, so a
  //    column that reads the wrong map comes back empty rather than coincidentally right —
  //    which is exactly what the arithmetic did.
  const NODE = { depth: 2, keys: { mat_id: 'M1', x: 3 }, attributes: { grade: 'A' },
    label: 'die 1', id: 'ledger-entity:v1:die@1:M1' };
  const QUALS = { gate: 7 };
  const at = (kind, key) => M.cellSource({ kind, key }, NODE, QUALS);
  ok(at('depth') === 2, 'V1 depth reads the node depth');
  ok(at('key', 'mat_id') === 'M1', 'V2 a key column reads the identity map');
  ok(at('qualifier', 'gate') === 7, 'V3 a qualifier column reads what the edge carried');
  ok(at('attribute', 'grade') === 'A', 'V4 an attribute column reads the ATTRIBUTE map');
  ok(at('key', 'grade') === undefined && at('attribute', 'mat_id') === undefined,
    'V5 and neither map answers for the other — the two are not interchangeable');
  ok(at('label') === 'die 1' && at('id') === 'ledger-entity:v1:die@1:M1',
    'V6 label and id read themselves');
  // ⚠️ RAW, NOT TEXT. 「the walk never reached this」 must survive as `undefined` so the
  //    caller can tell it from a value; inventing 「」 here would decide that in the wrong file.
  ok(M.cellSource({ kind: 'attribute', key: 'lot' }, NODE, QUALS) === undefined,
    'V7 a declared attribute with no value stays undefined rather than becoming a string');
  ok(M.cellSource({ kind: 'key', key: 'mat_id' }, null, null) === undefined,
    'V8 CONTROL: a missing node yields nothing rather than throwing');

  // ── the disagreement count: three server states, and only one of them says anything ──
  const conflicts = (v) => M.cellSource({ kind: 'conflicts' },
    v === undefined ? { attributes: {} } : { attributes: {}, attribute_conflicts: v }, {});
  ok(conflicts(2) === 2, 'W1 N names holding differing values is drawn as the NUMBER');
  ok(conflicts(0) === undefined,
    'W2 zero says nothing — a 0 in front of an operator means 「nothing is wrong」, a sentence');
  ok(conflicts(undefined) === undefined,
    'W3 no key at all — the walk reached no registration — says nothing either');
  // 🔴 AND THE ROW STILL SPLITS THOSE TWO, one column to the left. Without this the harness
  //    would be blessing a screen where 「없음」 and 「안 닿음」 are the same pixels.
  const REACHED = { attributes: { grade: 'A' }, attribute_conflicts: 0 };
  const UNREACHED = {};
  ok(M.cellSource({ kind: 'attribute', key: 'grade' }, REACHED, {}) === 'A'
    && M.cellSource({ kind: 'attribute', key: 'grade' }, UNREACHED, {}) === undefined,
    'W4 agreed-on and never-reached are still told apart by the attribute cells');
  ok(conflicts(-1) === undefined && M.cellSource({ kind: 'conflicts' },
    { attribute_conflicts: 'two' }, {}) === undefined,
    'W5 CONTROL: a number that cannot be a count is not drawn as one');

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
    (s) => s.replace(
      "    ...(qualifierNames || []).map((key) => ({ name: key, kind: 'qualifier', key })),\n",
      '')],
  // 🔴 판정 130-C ㉡. THIS IS THE ARITHMETIC, EXPRESSED AS WHAT IT DID. `main.js` used to
  //    split the identity columns out by position, which put the attribute columns on the
  //    identity side — so their values were looked up in `keys` and every one came back
  //    empty, with no error and no distinguishable pixel. The mutant makes this file say
  //    the same wrong thing, and the hand-held attribute fixture is what reddens.
  ['the attribute columns are labelled identity, which is what the arithmetic did',
    (s) => s.replace("    ...attributes.map((key) => ({ name: key, kind: 'attribute', key })),",
      "    ...attributes.map((key) => ({ name: key, kind: 'key', key })),")],
  ['the attribute columns move ahead of the qualifiers, so the order stops being one answer',
    (s) => s.replace(
      "    ...(qualifierNames || []).map((key) => ({ name: key, kind: 'qualifier', key })),\n"
      + "    ...attributes.map((key) => ({ name: key, kind: 'attribute', key })),",
      "    ...attributes.map((key) => ({ name: key, kind: 'attribute', key })),\n"
      + "    ...(qualifierNames || []).map((key) => ({ name: key, kind: 'qualifier', key })),")],
  ['an attribute cell reads the identity map, so a declared attribute is always empty',
    (s) => s.replace("    case 'attribute': return (n.attributes || {})[column.key];",
      "    case 'attribute': return (n.keys || {})[column.key];")],
  ['the attribute names stop coming from the declaration',
    (s) => s.replace('  const attributes = (found && found.attributes) || [];',
      '  const attributes = [];')],
  ['the disagreement column appears for every type, so today\'s table stops being unchanged',
    (s) => s.replace("    ...(attributes.length ? [{ name: '충돌', kind: 'conflicts' }] : []),",
      "    { name: '충돌', kind: 'conflicts' },")],
  ['the disagreement column moves behind the label, away from what it is about',
    (s) => s.replace("    ...(attributes.length ? [{ name: '충돌', kind: 'conflicts' }] : []),\n"
      + "    { name: '라벨', kind: 'label' },",
    "    { name: '라벨', kind: 'label' },\n"
      + "    ...(attributes.length ? [{ name: '충돌', kind: 'conflicts' }] : []),")],
  ['a measured zero is drawn as 0, which tells the operator nothing is wrong',
    (s) => s.replace('      return Number.isFinite(count) && count > 0 ? count : undefined;',
      '      return count;')],
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
