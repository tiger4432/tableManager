// Gate 4 (log-shaped push target) -- harness for `client2/src/push_columns.js`.
// Run: node client2/tests/push_gate_harness.mjs   (no node_modules, no vm, no source slicing)
//
// Fixtures are the REAL served schema shapes (GET /tables/{t}/schema on the
// isolated :8081 env, 2026-07-28): display_columns + the appended system tail.
//
// 🔴 IT `import`s ITS TARGET. It used to read `map_editor.js` as text, cut three declarations
//    out of it with a brace matcher, and run them in a `vm` sandbox -- because that is the
//    only way to execute a function that reads module globals. These three read none, so the
//    slicing was never buying anything except a veto over ever moving them: the extraction
//    anchors (`const PUSH_SYSTEM_COLUMNS = `, `function getUnprotectedPushColumns(`) made the
//    SHAPE of a declaration in another file load-bearing for this one.
//
// 🔴 THE MUTATION SWEEP IS UNCONDITIONAL AND ITS VERDICTS ARE COUNTED AS ASSERTIONS. Both
//    halves are deliberate. `frame_declaration_harness.mjs` puts its sweep behind `--mutate`,
//    the gate runs every harness BARE, and on 2026-08-05 that corpus was found to have been
//    dead for an unknown time on a stale anchor with the build green throughout. A sweep that
//    only runs when someone remembers a flag is a sweep nobody runs; a sweep whose verdicts
//    are not in the `ASSERTIONS` line can die without moving a number the gate watches. Here
//    each mutant and each control is one assertion, so a corpus that stops being applied sinks
//    `ran` under the recorded floor and BLOCKS.
//
// 🔴 AN ANCHOR THAT DOES NOT MATCH IS A HARNESS DEFECT, NOT A CAUGHT MUTANT. `apply` throwing
//    is exit 2 (nothing was measured), never a kill -- otherwise a corpus of stale anchors
//    reports a perfect score having executed nothing.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as LIVE from '../src/push_columns.js';

const MODULE_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'push_columns.js');
const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

// What the server actually appends to every table's columns. The three graph-sync names
// were removed from `main.py`'s `system_cols` on 2026-08-31, so a fixture still carrying
// them would test a server that no longer exists.
const SYS_TAIL = ['created_at', 'updated_at'];

// ---- served schema fixtures ----
const dtLog = {
  columns: ['dt_id', 'eventtime', 'tape_lot', 'tape_slot', 'tx', 'ty',
            'core_lot', 'core_slot', 'cx', 'cy', 'dt_eqp', ...SYS_TAIL],
  business_key: 'dt_id', composite_key_source: [],
  // the near-miss scenario: a site declares map keys so the log can be VIEWED as a map
  map_key_columns: ['tape_lot', 'tape_slot']
};
const bondingMap = {
  columns: ['pkg_id', 'base', 'x', 'y', 'leg', ...SYS_TAIL],
  business_key: 'pkg_id', composite_key_source: ['base', 'x', 'y'],
  map_key_columns: ['base']
};
const dtMap = {
  columns: ['cell_key', 'lot', 'slot', 'x', 'y', 'val', ...SYS_TAIL],
  business_key: 'cell_key', composite_key_source: ['lot', 'slot', 'x', 'y'],
  map_key_columns: ['lot', 'slot']
};
const qaOvlTxy = {
  columns: ['chip_key', 'lot', 'slot', 'tx', 'ty', 'val', ...SYS_TAIL],
  business_key: 'chip_key', composite_key_source: ['lot', 'slot', 'tx', 'ty'],
  map_key_columns: ['lot', 'slot']
};
const edsFailMap = {
  columns: ['chip_key', 'lot', 'slot', 'x', 'y', 'val', 'metro_eqp', ...SYS_TAIL],
  business_key: 'chip_key', composite_key_source: ['lot', 'slot', 'x', 'y'],
  map_key_columns: ['lot', 'slot']
};

// ═══════════════════════════════════════════════════════════════════════════════
// THE SUITE, as a function of the module under test. That signature is what makes the
// mutation sweep possible without a second copy of the expectations: the baseline and every
// mutant are scored by the SAME code against the SAME fixtures.
// ═══════════════════════════════════════════════════════════════════════════════
function run(M, { quiet = false } = {}) {
  const { PUSH_SYSTEM_COLUMNS, getUnprotectedPushColumns, logShapedPushDecision } = M;
  let pass = 0; const failures = [];
  const check = (name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { pass++; if (!quiet) console.log(`  ok   ${name}`); }
    else {
      failures.push(name);
      if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
    }
  };
  const say = (s) => { if (!quiet) console.log(s); };

  say('[1] dt_log (declared binding tx/ty/core_lot) -> refuse, exact column list');
  check('dt_log extras', getUnprotectedPushColumns(dtLog, 'tx', 'ty', 'core_lot'),
    ['dt_id', 'eventtime', 'core_slot', 'cx', 'cy', 'dt_eqp']);

  say('[2] fixture axis is ALIVE: dt_id is a non-composite business key');
  // If dt_id ever became covered without a composite source, the gate would go blind
  // to identity destruction - assert the axis explicitly.
  check('dt_id flagged', getUnprotectedPushColumns(dtLog, 'tx', 'ty', 'core_lot').includes('dt_id'), true);

  say('[3] bonding_map (composite pkg_id = base_x_y) -> pass');
  check('bonding_map extras', getUnprotectedPushColumns(bondingMap, 'x', 'y', 'leg'), []);

  say('[4] composite exemption is actually EXERCISED by fixture [3]');
  // pkg_id is NOT in the covered set by name - only the composite derivation saves it.
  // (Guards against a future "simplification" that drops the exemption and starts
  // refusing every standard map table - the bonding_map caution.)
  const naiveCovered = new Set([...bondingMap.map_key_columns, 'x', 'y', 'leg', ...PUSH_SYSTEM_COLUMNS]);
  check('pkg_id not naively covered', naiveCovered.has('pkg_id'), false);

  say('[5] dt_map / qa_ovl_txy (tx/ty bound) -> pass');
  check('dt_map extras', getUnprotectedPushColumns(dtMap, 'x', 'y', 'val'), []);
  check('qa_ovl_txy extras', getUnprotectedPushColumns(qaOvlTxy, 'tx', 'ty', 'val'), []);

  say('[6] composite key NOT derivable when a source column is uncovered');
  // same table but user binds val to a source column's sibling such that a composite
  // source (slot) is not covered -> chip_key itself must be flagged too.
  const partial = { ...qaOvlTxy, map_key_columns: ['lot'] };
  check('partial-key extras', getUnprotectedPushColumns(partial, 'tx', 'ty', 'val'),
    ['chip_key', 'slot']);

  say('[7] eds_fail_map (metro_eqp measurement column) -> refuse, names metro_eqp');
  // Deliberate: an ingested measurement map with extra data columns is exactly the
  // hazard class - pushing the editor grid into it would NULL metro_eqp on all rows.
  check('eds_fail_map extras', getUnprotectedPushColumns(edsFailMap, 'x', 'y', 'val'), ['metro_eqp']);

  say('[8] degenerate schema -> no crash, empty answer');
  check('null schema', getUnprotectedPushColumns(null, 'x', 'y', 'val'), []);
  check('empty schema', getUnprotectedPushColumns({}, 'x', 'y', 'val'), []);

  say('[9] map_push_ok declaration -> confirm instead of block (same extras)');
  // The site-declared exception: R&D manual-measurement overwrite into a declared
  // table downgrades the hard refusal to ONE loss-acknowledging confirm.
  const edsDeclared = { ...edsFailMap, map_push_ok: true };
  check('declared eds_fail_map mode', logShapedPushDecision(edsDeclared, 'x', 'y', 'val'),
    { mode: 'confirm', extras: ['metro_eqp'] });

  say('[10] undeclared / falsy / non-boolean declarations still BLOCK');
  check('undeclared dt_log', logShapedPushDecision(dtLog, 'tx', 'ty', 'core_lot').mode, 'block');
  check('map_push_ok:false', logShapedPushDecision({ ...edsFailMap, map_push_ok: false }, 'x', 'y', 'val').mode, 'block');
  // strict === true: a config typo like "true" (string) must not unlock destruction
  check('map_push_ok:"true" string', logShapedPushDecision({ ...edsFailMap, map_push_ok: 'true' }, 'x', 'y', 'val').mode, 'block');

  say('[11] declaration is inert on clean map tables (no stray confirm)');
  check('declared bonding_map stays clean',
    logShapedPushDecision({ ...bondingMap, map_push_ok: true }, 'x', 'y', 'leg').mode, 'clean');

  // [12] THE ROSTER IS THE UNION OF THE TWO SERVER LISTS, named member by member. A count
  //      would stay green while a member was swapped, and a member is what protects a column.
  say('[12] the system roster, member by member');
  check('PUSH_SYSTEM_COLUMNS members', [...PUSH_SYSTEM_COLUMNS].sort(),
    ['business_key_val', 'created_at', 'grid_metadata', 'id',
     'row_id', 'updated_at', 'updated_by'].sort());

  return { pass, failures, compared: pass + failures.length };
}

// ═══════════════════════════════════════════════════════════════════════════════
// BASELINE
// ═══════════════════════════════════════════════════════════════════════════════
const base = run(LIVE);
console.log(`\n[baseline] ${base.pass} passed, ${base.failures.length} failed`);

// ═══════════════════════════════════════════════════════════════════════════════
// MUTATION SWEEP -- in-memory variants of the module, imported as `data:` URLs. The file on
// disk is never written, so there is no stale artefact to forget to revert and no CRLF hazard
// (every anchor below matches `\n`, and the source is normalised once, here).
// ═══════════════════════════════════════════════════════════════════════════════
let SRC;
try { SRC = readFileSync(MODULE_PATH, 'utf8').replace(/\r\n/g, '\n'); }
catch (e) { die(`cannot read ${MODULE_PATH} -- ${e && e.message}`); }

const swap = (name, from, to) => ({
  name,
  apply: (s) => {
    if (!s.includes(from)) throw new Error(`anchor not found: ${from}`);
    const n = s.split(from).length - 1;
    if (n !== 1) throw new Error(`anchor is not unique (${n} matches): ${from}`);
    return s.split(from).join(to);
  },
});

const MUTANTS = [
  // ── the covered set. Each of these makes the gate protect something it must not, which is
  //    the direction that DESTROYS data: an over-covered column is a column the refusal stops
  //    naming, so the push proceeds and the column comes back NULL.
  swap('M1 the map-key scope is not covered (a legitimate map table starts refusing)',
    '...(Array.isArray(schema && schema.map_key_columns) ? schema.map_key_columns : []),',
    ''),
  swap('M2 the bound value column is covered by accident of position (x/y only)',
    '    xCol, yCol, valCol,\n', '    xCol, yCol,\n'),
  swap('M3 the server roster is not consulted at all',
    '    ...PUSH_SYSTEM_COLUMNS\n', ''),
  swap('M4 grid_metadata drops out of the roster',
    "  'grid_metadata'\n", "  'row_id'\n"),
  swap('M5 business_key_val drops out of the roster',
    "'updated_by', 'business_key_val',", "'updated_by',"),
  // ── the composite exemption, both directions. It is the one rule with a precondition, and
  //    both halves of that precondition have their own mutant.
  swap('M6 the business key is exempted UNCONDITIONALLY (dt_id stops being flagged)',
    'if (bk && src.length > 0 && src.every(c => covered.has(c))) covered.add(bk);',
    'if (bk) covered.add(bk);'),
  swap('M7 an EMPTY composite source counts as a derivation',
    'if (bk && src.length > 0 && src.every(c => covered.has(c)))',
    'if (bk && src.every(c => covered.has(c)))'),
  swap('M8 a PARTLY covered composite source still exempts the key',
    'src.every(c => covered.has(c))', 'src.some(c => covered.has(c))'),
  swap('M9 the exemption is dropped entirely (every standard map table starts refusing)',
    'if (bk && src.length > 0 && src.every(c => covered.has(c))) covered.add(bk);', ''),
  // ── the answer itself
  swap('M10 the filter is inverted (only protected columns are reported)',
    'return cols.filter(c => !covered.has(c));', 'return cols.filter(c => covered.has(c));'),
  swap('M11 a degenerate schema throws instead of answering empty',
    'const cols = Array.isArray(schema && schema.columns) ? schema.columns : [];',
    'const cols = schema.columns;'),
  // ── the three modes. `block` vs `confirm` is the difference between a refusal and one
  //    click, and `clean` vs `confirm` is the difference between no friction and a question
  //    on every push of a perfectly ordinary map.
  swap('M12 extras downgrade to a confirm without any declaration',
    "return { mode: (schema && schema.map_push_ok === true) ? 'confirm' : 'block', extras };",
    "return { mode: 'confirm', extras };"),
  swap('M13 the declaration is read loosely (the string "true" unlocks destruction)',
    'schema.map_push_ok === true', 'schema.map_push_ok'),
  swap('M14 a clean table still asks (the declaration stops being inert)',
    "if (extras.length === 0) return { mode: 'clean', extras };", ''),
  swap('M15 the decision reports a mode without the columns it is about',
    "return { mode: (schema && schema.map_push_ok === true) ? 'confirm' : 'block', extras };",
    "return { mode: (schema && schema.map_push_ok === true) ? 'confirm' : 'block', extras: [] };"),
  // ── the two-spellings mutant: the decision stops asking the roster function and re-derives.
  //    This is the shape the codebase is organised to prevent, so it gets a mutant of its own.
  swap('M16 the decision re-derives the extras instead of asking the one function',
    'const extras = getUnprotectedPushColumns(schema, xCol, yCol, valCol);',
    'const extras = (Array.isArray(schema && schema.columns) ? schema.columns : [])\n'
    + '    .filter(c => c !== xCol && c !== yCol && c !== valCol);'),
  // ── CONTROLS: these must ESCAPE. If one is caught, an assertion above is reading source
  //    text rather than executing behaviour.
  swap('CONTROL a comment change must NOT be caught',
    '// [Gate 4] Which of the target', '// [Gate 4] WHICH of the target'),
  swap('CONTROL renaming a local must NOT be caught',
    'const bk = schema && schema.business_key;', 'const businessKey = schema && schema.business_key;'),
];
// The second control renames a local, so its remaining uses have to move with it or the
// mutant is a syntax error (which would "die" for the wrong reason and look like a kill).
MUTANTS[MUTANTS.length - 1].apply = (s) => {
  if (!s.includes('const bk = schema && schema.business_key;')) throw new Error('anchor not found: bk');
  return s.split('const bk = schema && schema.business_key;').join('const businessKey = schema && schema.business_key;')
          .split('if (bk && src.length > 0').join('if (businessKey && src.length > 0')
          .split('covered.add(bk);').join('covered.add(businessKey);');
};

console.log('\n── mutation sweep (each verdict is one assertion) ──────────────────');
let sweepPass = 0; const sweepFail = [];
for (const m of MUTANTS) {
  const isControl = m.name.startsWith('CONTROL');
  let src;
  try { src = m.apply(SRC); }
  catch (e) {
    die(`mutant "${m.name}" could not be applied: ${e.message}. `
      + `An unapplied mutant is not a caught mutant.`);
  }
  if (src === SRC) die(`mutant "${m.name}" produced text identical to the source. `
    + `A no-op mutant scores whatever the baseline scores.`);

  // 🔴 LOADING IS SEPARATED FROM RUNNING, and only the second one may score. A mutant that
  //    does not PARSE never executed a single assertion, so counting its failure as a kill
  //    would be the unapplied-mutant disguise wearing a different hat -- a corpus of syntax
  //    errors would report a perfect sweep. Only a throw from the code under test is a kill.
  let mod;
  try {
    const url = 'data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64');
    mod = await import(url);
  } catch (e) {
    die(`mutant "${m.name}" does not load: ${String(e && e.message).slice(0, 200)}. `
      + `A mutant that never parsed ran no assertions and killed nothing.`);
  }

  let killed, detail = '';
  try {
    const out = run(mod, { quiet: true });
    killed = out.failures.length > 0;
    detail = killed ? `${out.failures.length} failure(s), first: ${out.failures[0]}` : '';
    // A mutant that scored fewer assertions than the baseline crashed its way to a verdict.
    if (out.compared < base.compared) detail += ` [ran ${out.compared} of ${base.compared}]`;
  } catch (e) {
    killed = true;
    detail = `threw from the code under test: ${String(e && e.message).slice(0, 110)}`;
  }
  const asExpected = (killed !== isControl);
  if (asExpected) { sweepPass++; console.log(`  ok   ${killed ? 'CAUGHT  ' : 'ESCAPED '} ${m.name}`); }
  else {
    sweepFail.push(m.name);
    console.log(`  FAIL ${killed ? 'CAUGHT  ' : 'SURVIVED'} ${m.name}  <- ${isControl
      ? 'a control was caught: an assertion above is reading source text, not behaviour'
      : 'a defect mutant survived: the assertion that should catch it is inert'}`);
  }
  if (detail) console.log(`         ${detail}`);
}

const ran = base.compared + MUTANTS.length;
const failed = base.failures.length + sweepFail.length;
console.log(`\n${ran - failed} passed, ${failed} failed  `
  + `(${base.compared} behaviour + ${MUTANTS.length} mutation verdicts)`);
base.failures.forEach(f => console.log(`   x ${f}`));
sweepFail.forEach(f => console.log(`   x mutant ${f}`));
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed ? 1 : 0);
