/**
 * COLUMN WORDS — the CLIENT half, scored against `vectors.json`.
 *
 *   node contracts/column_words/client_harness.mjs
 *
 * Exit codes: 0 = the client words and stacks columns as the contract says · 1 = divergence(s) · 2 = harness failure
 *
 * Read-only. The subject is client2/src/tables/column_words.js (`columnWords`, `stackColumns`) - the one place a column's
 * ontology word is made (D 11-12: the function lives in the client alone; the vectors are D's).
 *
 * 🔴 A DECOY SOURCE RIDES IN EVERY CASE: another table with the same column names bound to another entity. A lookup that
 *    read every source's rows would put the decoy's word on the case's columns and fail visibly.
 * 🔴 A CASE'S ROWS ARE SPLIT OVER TWO SOURCES OF ITS TABLE - a table two sources read is one table's words.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SUBJECT = join(HERE, '..', '..', 'client2', 'src', 'tables', 'column_words.js');

let pass = 0;
const failures = [];
const same = (name, got, want) => {
  const g = JSON.stringify(got);
  const w = JSON.stringify(want);
  if (g === w) { pass += 1; console.log(`  PASS ${name}`); } else { failures.push(name); console.log(`  FAIL ${name} — got ${g}, want ${w}`); }
};

let vectors;
let words;
try {
  vectors = JSON.parse(readFileSync(join(HERE, 'vectors.json'), 'utf8'));
  words = await import(pathToFileURL(SUBJECT).href);
} catch (e) {
  console.error(`column_words: could not load its own subject — ${e && e.message}`);
  process.exit(2);
}
const CASES = vectors.cases || [];
const STACKS = vectors.stacks || [];
if (!CASES.length || !STACKS.length) {
  console.error('column_words: the vectors carry no cases or no stacks. An empty scan is not a passing contract.');
  process.exit(2);
}
if (typeof words.columnWords !== 'function' || typeof words.stackColumns !== 'function') {
  console.error('column_words: columnWords / stackColumns are gone from client2/src/tables/column_words.js. That is the finding.');
  process.exit(1);
}

for (const c of CASES) {
  const decoy = { relation: `${c.table}_decoy`, columns: c.table_columns.map((column) => ({ column, entity: 'decoy@1', role: 'key', name: 'decoy' })) };
  const half = Math.ceil(c.rows.length / 2);
  const sources = [decoy, { relation: c.table, columns: c.rows.slice(0, half) }, { relation: c.table, columns: c.rows.slice(half) }];
  const got = words.columnWords(sources, c.table, c.table_columns);
  // every column of the table worded, in the table's order, none more
  same(`${c.name} · the columns`, Object.keys(got), c.table_columns);
  for (const column of c.table_columns) same(`${c.name} · ${column}`, got[column], c.words[column]);
}
for (const s of STACKS) {
  same(`stack · ${s.name}`, words.stackColumns(s.tables, s.table_columns), s.columns);
}

console.log(`\ncolumn_words: ${pass} passed, ${failures.length} failed`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length ? 1 : 0);
