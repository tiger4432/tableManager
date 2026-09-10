/**
 * 🏷️ C-59 / S-92 — 시험 실행이 «어느 행»을 읽었나. 대상을 IMPORT 해서 잽니다.
 *
 * 🔴 픽스처는 «계약 벡터»입니다 — `contracts/test_run_rows/vectors.json`, 라이브에서 뜬 것.
 *    그리고 그 벡터를 «다시 뜬 것»이 이 라운드에서 하나를 잡았습니다: 지시는 `values` 를
 *    표본의 «형제 칸»으로 적었는데 실제 응답은 «`row_key` 안»입니다. 형제로 읽었으면 그
 *    갈래가 영원히 안 돌면서 «오류도 안 났을» 것입니다.
 *
 * 🔴 두 case 의 «열이 다릅니다»(dt_job·dt_cell_key·created_at / event_time·row_id) — 그것이
 *    「열을 하드코딩하지 않는다」의 판별식입니다. 한 case 만으로는 상수 표도 통과합니다.
 *
 * Run: node client2/tests/test_run_rows_harness.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { testRunRows, MARK_COLUMN, KIND_FIELD } from '../src/refusal_cell.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const V = JSON.parse(readFileSync(
  join(HERE, '..', '..', 'contracts', 'test_run_rows', 'vectors.json'), 'utf8')).cases;

let ran = 0;
let failed = 0;
const ok = (name, cond, detail = '') => {
  ran += 1;
  if (cond) console.log(`  PASS ${name}`);
  else { failed += 1; console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

const cols = (t) => t.columns.map((c) => c.key).join(',');
const reads = (t) => t.rows.filter((r) => r[KIND_FIELD] === 'read');
const refusals = (t) => t.rows.filter((r) => r[KIND_FIELD] === 'refused');

console.log('\n[1] the columns come from the sample, not from this file');
{
  const a = testRunRows(V.passed_with_rows);
  const b = testRunRows(V.passed_with_a_refusal);
  eq('one declaration\'s columns', `${MARK_COLUMN},dt_job,dt_cell_key,created_at`, cols(a));
  // 🔴 THE DISCRIMINANT: a different declaration reads different columns. A hard-coded table
  //    passes the first assertion and dies here.
  eq('...and another\'s are different', `${MARK_COLUMN},event_time,row_id`, cols(b));
  eq('the label is the column name, untranslated', 'dt_job',
    a.columns.find((c) => c.key === 'dt_job').label);
  eq('the first column is the mark slot and carries no label', '',
    a.columns[0].label);
}

console.log('\n[2] the rows that were read');
{
  const a = testRunRows(V.passed_with_rows);
  eq('every sampled row is a row', V.passed_with_rows.rows_sample.length, reads(a).length);
  eq('...carrying the value the server sent', V.passed_with_rows.rows_sample[0].dt_job,
    reads(a)[0].dt_job);
  eq('...and nothing in the mark slot', '', reads(a)[0][MARK_COLUMN]);
}

console.log('\n[3] a refusal is a row of the SAME table');
{
  const b = testRunRows(V.passed_with_a_refusal);
  eq('the refusal joins the rows', 1, refusals(b).length);
  eq('...under the read rows, not before them', 'refused', b.rows[b.rows.length - 1][KIND_FIELD]);
  const r = refusals(b)[0];
  ok('the mark names the reason and where it was', r[MARK_COLUMN].includes('no_identity')
    && r[MARK_COLUMN].includes('event_frame[0]'), r[MARK_COLUMN]);
  // 🔴 `values` LIVES INSIDE `row_key`. Read as a sibling of the sample it would never be
  //    found, the row would draw blank cells, and nothing would error.
  const sent = V.passed_with_a_refusal.refused.samples[0].row_key.values;
  eq('the key values fill the SAME columns as the read rows', sent.row_id, r.row_id);
  eq('...all of them', sent.event_time, r.event_time);
}

console.log('\n[4] what is NOT drawn');
{
  // ⛔ A refusal that does not point at a row is not a row. It is already named in the
  //    sample list above the table; putting it here would point at a place it never named.
  const noKey = testRunRows({ ...V.passed_with_a_refusal,
    refused: { count: 1, reasons: {}, samples: [{ reason: 'undeclared_subject_type' }] } });
  eq('a refusal with no row_key draws no row', 0, refusals(noKey).length);
  ok('...while the read rows are untouched', reads(noKey).length === 3, String(reads(noKey).length));
  // ⚠️ `values` is OPTIONAL: a refusal that points at a row but carries no values still draws,
  //    with its cells blank -- 「어느 행인지는 안다, 값은 안 왔다」.
  const noValues = testRunRows({ ...V.passed_with_a_refusal,
    refused: { count: 1, reasons: {},
      samples: [{ reason: 'no_identity', row_key: { frame: 'event_frame', position: 2 } }] } });
  eq('a refusal without values still draws its row', 1, refusals(noValues).length);
  eq('...with empty cells rather than invented ones', '', refusals(noValues)[0].row_id);
  ok('...and still says where', refusals(noValues)[0][MARK_COLUMN].includes('event_frame[2]'),
    refusals(noValues)[0][MARK_COLUMN]);
}

console.log('\n[5] no sample, no table');
{
  // 🔴 An empty table with the right headers would claim 「읽은 행이 0」 about a run that
  //    never sent a sample -- the same collapse as a blank standing in for 「안 쟀다」.
  eq('a run with no rows_sample yields no columns', 0, testRunRows({ rows_read: 5 }).columns.length);
  eq('...and no rows', 0, testRunRows({ rows_read: 5 }).rows.length);
  eq('a garbage sample is not a table', 0, testRunRows({ rows_sample: 'nope' }).columns.length);
  eq('nothing at all is safe', 0, testRunRows(null).columns.length);
}

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
