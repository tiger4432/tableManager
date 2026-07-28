// Mock harness - map_editor.js Gate 4 (log-shaped push target) verification.
// Target: PUSH_SYSTEM_COLUMNS / getUnprotectedPushColumns
// Run: node client2/tests/push_gate_harness.mjs  (no node_modules - vm sandbox)
//
// Fixtures are the REAL served schema shapes (GET /tables/{t}/schema on the
// isolated :8081 env, 2026-07-28): display_columns + the appended system tail.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const SRC_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'map_editor.js');
const src = readFileSync(SRC_PATH, 'utf8');

function extractFunction(name) {
  const re = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = re.exec(src);
  if (!m) throw new Error(`function ${name} not found`);
  let i = src.indexOf('{', m.index);
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === '{') depth++;
    else if (ch === '}') { depth--; if (depth === 0) return src.slice(m.index, j + 1); }
  }
  throw new Error(`unbalanced braces for ${name}`);
}
function extractConst(name) {
  const re = new RegExp(`const\\s+${name}\\s*=`);
  const m = re.exec(src);
  if (!m) throw new Error(`const ${name} not found`);
  let depth = 0;
  for (let j = m.index; j < src.length; j++) {
    const ch = src[j];
    if (ch === '[' || ch === '{') depth++;
    else if (ch === ']' || ch === '}') depth--;
    else if (ch === ';' && depth === 0) return src.slice(m.index, j + 1);
  }
  throw new Error(`no terminator for ${name}`);
}

const ctx = {};
vm.createContext(ctx);
vm.runInContext([
  extractConst('PUSH_SYSTEM_COLUMNS'),
  extractFunction('getUnprotectedPushColumns'),
  extractFunction('logShapedPushDecision'),
  'globalThis.__h = { PUSH_SYSTEM_COLUMNS, getUnprotectedPushColumns, logShapedPushDecision };'
].join('\n\n'), ctx);
const { PUSH_SYSTEM_COLUMNS, getUnprotectedPushColumns, logShapedPushDecision } = ctx.__h;

let pass = 0, fail = 0;
function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; console.log(`  ok   ${name}`); }
  else { fail++; console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`); }
}

const SYS_TAIL = ['created_at', 'updated_at', 'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'];

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

console.log('[1] dt_log (declared binding tx/ty/core_lot) -> refuse, exact column list');
check('dt_log extras', getUnprotectedPushColumns(dtLog, 'tx', 'ty', 'core_lot'),
  ['dt_id', 'eventtime', 'core_slot', 'cx', 'cy', 'dt_eqp']);

console.log('[2] fixture axis is ALIVE: dt_id is a non-composite business key');
// If dt_id ever became covered without a composite source, the gate would go blind
// to identity destruction - assert the axis explicitly.
check('dt_id flagged', getUnprotectedPushColumns(dtLog, 'tx', 'ty', 'core_lot').includes('dt_id'), true);

console.log('[3] bonding_map (composite pkg_id = base_x_y) -> pass');
check('bonding_map extras', getUnprotectedPushColumns(bondingMap, 'x', 'y', 'leg'), []);

console.log('[4] composite exemption is actually EXERCISED by fixture [3]');
// pkg_id is NOT in the covered set by name - only the composite derivation saves it.
// (Guards against a future "simplification" that drops the exemption and starts
// refusing every standard map table - the bonding_map caution.)
const naiveCovered = new Set([...bondingMap.map_key_columns, 'x', 'y', 'leg', ...PUSH_SYSTEM_COLUMNS]);
check('pkg_id not naively covered', naiveCovered.has('pkg_id'), false);

console.log('[5] dt_map / qa_ovl_txy (tx/ty bound) -> pass');
check('dt_map extras', getUnprotectedPushColumns(dtMap, 'x', 'y', 'val'), []);
check('qa_ovl_txy extras', getUnprotectedPushColumns(qaOvlTxy, 'tx', 'ty', 'val'), []);

console.log('[6] composite key NOT derivable when a source column is uncovered');
// same table but user binds val to a source column's sibling such that a composite
// source (slot) is not covered -> chip_key itself must be flagged too.
const partial = { ...qaOvlTxy, map_key_columns: ['lot'] };
check('partial-key extras', getUnprotectedPushColumns(partial, 'tx', 'ty', 'val'),
  ['chip_key', 'slot']);

console.log('[7] eds_fail_map (metro_eqp measurement column) -> refuse, names metro_eqp');
// Deliberate: an ingested measurement map with extra data columns is exactly the
// hazard class - pushing the editor grid into it would NULL metro_eqp on all rows.
check('eds_fail_map extras', getUnprotectedPushColumns(edsFailMap, 'x', 'y', 'val'), ['metro_eqp']);

console.log('[8] degenerate schema -> no crash, empty answer');
check('null schema', getUnprotectedPushColumns(null, 'x', 'y', 'val'), []);
check('empty schema', getUnprotectedPushColumns({}, 'x', 'y', 'val'), []);

console.log('[9] map_push_ok declaration -> confirm instead of block (same extras)');
// The site-declared exception: R&D manual-measurement overwrite into a declared
// table downgrades the hard refusal to ONE loss-acknowledging confirm.
const edsDeclared = { ...edsFailMap, map_push_ok: true };
check('declared eds_fail_map mode', logShapedPushDecision(edsDeclared, 'x', 'y', 'val'),
  { mode: 'confirm', extras: ['metro_eqp'] });

console.log('[10] undeclared / falsy / non-boolean declarations still BLOCK');
check('undeclared dt_log', logShapedPushDecision(dtLog, 'tx', 'ty', 'core_lot').mode, 'block');
check('map_push_ok:false', logShapedPushDecision({ ...edsFailMap, map_push_ok: false }, 'x', 'y', 'val').mode, 'block');
// strict === true: a config typo like "true" (string) must not unlock destruction
check('map_push_ok:"true" string', logShapedPushDecision({ ...edsFailMap, map_push_ok: 'true' }, 'x', 'y', 'val').mode, 'block');

console.log('[11] declaration is inert on clean map tables (no stray confirm)');
check('declared bonding_map stays clean',
  logShapedPushDecision({ ...bondingMap, map_push_ok: true }, 'x', 'y', 'leg').mode, 'clean');

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
