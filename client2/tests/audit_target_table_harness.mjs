// audit_target_table_harness — WHICH TABLE DID THIS TRANSACTION TOUCH, AND DO WE ACTUALLY KNOW.
//
// The audit panel's group line is a transaction, and a transaction can touch several tables. The
// row used to print `group.logs[0].table_name` for summary rows and nothing at all for single
// ones, which is two different faults in one cell: a representative picked out of an unordered
// set, and a missing fact.
//
// 🔴 THE PART THAT IS EASY TO GET WRONG. `/audit_logs/recent` does not send the group's logs --
// it sends a SAMPLE of them. Measured against the live route on 2026-08-31: of 100 groups, 98
// carried exactly one log while `total_count` said 128, 132, 768, 1000. So "count the distinct
// tables in `group.logs`" is not a fix for the representative problem, it is the same problem
// with arithmetic on top: one sampled row, called a set. Anything this function says about a
// sampled group has to be a LOWER BOUND, never a claim about the whole.
//
// Every check is paired with a mutant. Two controls must escape, or the checks are reading the
// source text rather than the behaviour.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'timeline.js');
const SOURCE = readFileSync(SRC, 'utf8').replace(/\r\n/g, '\n');

let passed = 0;
let failed = 0;

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

function ok(cond, what, saw) {
  if (cond) { passed++; console.log(`  ok   ${what}`); return; }
  failed++;
  console.log(`  FAIL ${what}${saw === undefined ? '' : `  -- saw ${JSON.stringify(saw)}`}`);
}

// Slice the one function out. Anchored on its signature and its closing brace at column 0, so a
// rename or a move makes this stop rather than silently score a different function.
function slice(src) {
  const start = src.indexOf('export function auditTargetTable(group) {');
  if (start === -1) return null;
  const end = src.indexOf('\n}\n', start);
  if (end === -1) return null;
  return src.slice(start, end + 3).replace('export function', 'function');
}

function load(src) {
  const body = slice(src);
  if (body === null) return null;
  const sandbox = { Array, Number, Set, String, JSON };
  vm.createContext(sandbox);
  vm.runInContext(`${body}\nglobalThis.__f = auditTargetTable;`, sandbox);
  return sandbox.__f;
}

const f = load(SOURCE);
if (!f) die('auditTargetTable could not be sliced out of timeline.js -- it was renamed or moved.');

const log = (table) => ({ table_name: table, row_id: 'r', column_name: 'c' });
const group = (tables, total) => ({ logs: tables.map(log), total_count: total });

console.log('\n── A. what we hold IS the whole group ──────────────────────────────');
{
  // total_count matches the logs in hand, so the answer is a fact about the transaction.
  ok(f(group(['dt_log'], 1)) === 'dt_log',
    'A1 one table, fully known: its name, and nothing else', f(group(['dt_log'], 1)));
  ok(f(group(['dt_log', 'dt_log', 'dt_log'], 3)) === 'dt_log',
    'A2 the same table three times is still one table', f(group(['dt_log', 'dt_log', 'dt_log'], 3)));
  // 🔴 THE DISCRIMINATING PAIR for the representative bug: A2 and A3 have the same first log
  // and the same length. Only the SET differs, so a rule that reads `logs[0]` gives the same
  // answer for both and cannot be told apart by A2 alone.
  ok(f(group(['dt_log', 'dt_inventory', 'lot_event'], 3)) === 'dt_log +2',
    'A3 three tables say so, with the count', f(group(['dt_log', 'dt_inventory', 'lot_event'], 3)));
  ok(f(group(['dt_log', 'dt_inventory'], 2)) === 'dt_log +1',
    'A4 two tables is +1, not +2 -- the number is the OTHERS, not the total',
    f(group(['dt_log', 'dt_inventory'], 2)));
}

console.log('\n── B. what we hold is a SAMPLE ─────────────────────────────────────');
{
  // This is the live shape: one log, total_count in the hundreds.
  const partial = group(['dt_log'], 128);
  ok(f(partial) === 'dt_log …',
    'B1 a sampled group does not claim to be one table', f(partial));
  // 🔴 THE ONE THIS FILE EXISTS FOR. Without the marker B1 and A1 render IDENTICALLY, and the
  // panel then says "this transaction touched dt_log" about 128 rows it never saw.
  ok(f(partial) !== f(group(['dt_log'], 1)),
    'B2 ... and it does not render the same as a group we really do know');
  ok(f({ logs: [log('dt_log'), log('dt_inventory')], total_count: 900 }) === 'dt_log +1 …',
    'B3 a sample that already proves several says both: the lower bound and that there is more',
    f({ logs: [log('dt_log'), log('dt_inventory')], total_count: 900 }));
}

console.log('\n── C. the empty and broken shapes ──────────────────────────────────');
{
  ok(f({ logs: [], total_count: 0 }) === '', 'C1 no logs is the empty string, not "undefined"',
    f({ logs: [], total_count: 0 }));
  ok(f(null) === '', 'C2 no group at all is the same empty, not a crash', f(null));
  ok(f({ logs: [{ row_id: 'r' }], total_count: 1 }) === '',
    'C3 a log with no table name contributes nothing rather than a blank entry',
    f({ logs: [{ row_id: 'r' }], total_count: 1 }));
  ok(f({ logs: [log('dt_log'), { row_id: 'r' }], total_count: 2 }) === 'dt_log',
    'C4 ... and it does not inflate the count of the ones that do have a name',
    f({ logs: [log('dt_log'), { row_id: 'r' }], total_count: 2 }));
  // `total_count` missing: NaN loses every `<`, so the group reads as complete rather than
  // as a sample of unknown size. There is no fallback value -- adding one changed nothing.
  ok(f({ logs: [log('dt_log')] }) === 'dt_log',
    'C5 a group with no total_count is read as complete, not as an endless sample',
    f({ logs: [log('dt_log')] }));
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

const DEFECTS = [
  ['the first log is taken as the representative',
    swap('  const names = [...new Set(logs.map((log) => log && log.table_name).filter(Boolean))];',
      '  const names = logs.length ? [logs[0].table_name].filter(Boolean) : [];')],
  ['a sampled group claims to be the whole transaction',
    swap('  const sampled = logs.length < total;', '  const sampled = false;')],
  ['the count includes the table that is already named',
    swap('names.length > 1 ? ` +${names.length - 1}` : \'\'',
      'names.length > 1 ? ` +${names.length}` : \'\'')],
  ['several tables are silently collapsed to the first',
    swap('names.length > 1 ? ` +${names.length - 1}` : \'\'', "''")],
  ['a log with no table name still takes a slot',
    swap('.filter(Boolean))]', ')]')],
];

const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bnames\b/g, 'tableNames')],
  ['comments stripped', (src) => src.split('\n')
    .filter((line) => !line.trim().startsWith('//') && !line.trim().startsWith('*')
      && !line.trim().startsWith('/*'))
    .join('\n')],
];

function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ──────────────────────────────────`);
  let caught = 0;
  for (const [name, mutate] of list) {
    const g = load(mutate(SOURCE));
    if (!g) { console.log(`  INERT  ${name} -- the slice stopped matching`); failed++; continue; }
    let bad = false;
    try {
      // Re-run the checks that matter against the mutant. A mutant that throws counts as caught
      // only because it cannot answer -- so the throw is recorded as such rather than hidden.
      bad = g(group(['dt_log', 'dt_inventory', 'lot_event'], 3)) !== 'dt_log +2'
        || g(group(['dt_log'], 128)) !== 'dt_log …'
        || g(group(['dt_log', 'dt_inventory'], 2)) !== 'dt_log +1'
        || g({ logs: [log('dt_log'), { row_id: 'r' }], total_count: 2 }) !== 'dt_log'
        || g({ logs: [log('dt_log')] }) !== 'dt_log';
    } catch (e) {
      bad = true;
    }
    if (bad === mustCatch) {
      caught++;
      console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`);
    } else {
      failed++;
      console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`);
    }
  }
  return caught;
}

const caught = score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = score(CONTROLS, false, 'control mutants (each must ESCAPE)');

console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
