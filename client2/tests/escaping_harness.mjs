// C-14. Does a value carrying markup come back out as markup?
//
// 🔴 THE ASSERTION IS ABOUT THE OUTPUT, NOT ABOUT THE CALL. "escapeHtml was called" is a claim
//    about the code; "a `<script>` in a table name does not reach the DOM as an element" is a
//    claim about the screen, and only the second one stays true when someone rewrites the
//    template. So every check here feeds a hostile string in and reads what came out.
//
// 🔴 WHY THIS EXISTS AT ALL. Measured 2026-09-06: 28 innerHTML templates interpolate values and
//    2 escape. The same escape function existed three times, none exported, and the three were
//    NOT the same - `map2/excel_io.js` escaped `& < >` and left quotes alone, which is the
//    difference between safe and unsafe inside an attribute. One author now; the other two call
//    it.
// ⚠️ This file scores the canonical function and the first repaired surface (the history
//    timeline, which reflects operator-typed cell values straight back). The remaining
//    templates are counted in the report, not silently implied to be done.
import { escapeHtml } from '../src/utils.js';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}

// The shapes that actually break a template, not a generic "xss string".
const HOSTILE = [
  ['a tag', '<script>alert(1)</script>'],
  ['an attribute break', 'x" onerror="alert(1)'],
  ['a single-quoted break', "x' onerror='alert(1)"],
  ['an entity that must not double-escape into a lie', 'a & b'],
  ['a closing tag mid-value', 'done</span><span class="val-new">not done'],
];

console.log('-- the canonical escaper ---------------------------------------------');
for (const [what, raw] of HOSTILE) {
  const out = escapeHtml(raw);
  ok(!/[<>]/.test(out), `E: ${what} — no raw angle bracket survives`);
  ok(!/["']/.test(out), `E: ${what} — no raw quote survives`);
}
ok(escapeHtml('a & b') === 'a &amp; b', 'E: the ampersand is escaped once, not twice');
// 🔴 null must not print the word "null" — one of the three copies already did this and the
//    other two did not, which is how a copy drifts.
ok(escapeHtml(null) === '' && escapeHtml(undefined) === '',
  'E: an absent value is empty, not the word "null"');
ok(escapeHtml(0) === '0', 'E: zero survives as zero, not as empty');

// -- the repaired surface, read out of a real DOM ----------------------------------------
// The template is exercised through the DOM rather than by grepping the source, because the
// question is what the browser ends up holding.
console.log('\n-- the history row, rendered ------------------------------------------');
function renderRow(log) {
  // The same shape the file builds, restricted to the interpolations under test. Kept here
  // rather than importing `timeline.js`, which pulls the whole page graph; the assertion is
  // about escapeHtml's effect on these fields, and the file's own template is scored by the
  // drift check below.
  return `<span class="user-tag">${escapeHtml(log.updated_by)}</span>`
    + `<span class="change-field">${escapeHtml(log.column_name)}</span>`
    + `<div class="tx-tag" data-tx-id="${escapeHtml(log.transaction_id)}"></div>`;
}
const html = renderRow({
  updated_by: '<script>alert(1)</script>',
  column_name: 'done</span><span class="val-new">not done',
  transaction_id: 'x" onclick="alert(1)',
});
ok(!html.includes('<script>'), 'H1 a scripted author name is not a script element');
ok(html.split('<span').length === 3, 'H2 a value cannot open a span of its own');
ok(!/data-tx-id="x" onclick=/.test(html), 'H3 a value cannot break out of an attribute');

// -- tranche 2: the admin list rows that print SERVER-SUPPLIED NAMES ---------------------
// 🔴 THESE ARE THE REAL FUNCTIONS, imported. Last round's history-row check rendered a replica
//    of the template inside this file, which scores `escapeHtml` but NOT the screen — a replica
//    is a second author and drifts away from its subject silently. `admin_rows.js` exists so
//    this round does not have to do that: the harness runs exactly what `admin.js` runs.
console.log('\n-- the admin rows, as the screen builds them --------------------------');
const rows = await import('../src/admin_rows.js');

/** How many elements of one name the markup opens. A value that escapes its cell raises this. */
const opens = (html, tag) => html.split(`<${tag}`).length - 1;

// 🔴 THE CONTROL AGAINST A VACUOUS ASSERTION. If the payload could not break the template even
//    unescaped, "it did not break" proves nothing. So the payloads are checked for the
//    characters that do the breaking BEFORE they are used as evidence.
// ⚠️ THE PAYLOAD MUST OPEN THE ELEMENT THE ASSERTION COUNTS. Measured while writing this: the
//    first draft counted `<td>`/`<div>` while feeding a payload that opens a `<span>`, so the
//    row survived the escaping-removed mutant — the check was reading a tag the attack never
//    touched. That is why `CELL_BREAK` exists and why the mutant is run, not assumed.
const BREAKOUT = '</span><span class="badge">pwned';
const CELL_BREAK = '</td><td>injected';
const ATTR_BREAK = 'x" onmouseover="alert(1)';
ok(/[<>]/.test(BREAKOUT), 'C1 the breakout payload really does carry a tag — else A* are vacuous');
ok(/["]/.test(ATTR_BREAK), 'C2 the attribute payload really does carry a quote');
ok(CELL_BREAK.includes('<td'), 'C2b the cell payload really does open a cell');

// Baselines from a benign payload. The assertion is "the count did not MOVE", which is what
// distinguishes escaping from a template that happens to render nothing at all.
const benignFile = { id: 7, filename: 'lot.csv', table_name: 'wafer', status: 'SUCCESS', retry_count: 0, created_at: '2026-09-07' };
const baseFile = rows.fileLogRowHtml(benignFile, { withStatus: true, timeStr: '09-07 01:00' });
const hostFile = rows.fileLogRowHtml(
  { ...benignFile, filename: CELL_BREAK, table_name: BREAKOUT, status: '<script>alert(1)</script>' },
  { withStatus: true, timeStr: '09-07 01:00' });
ok(opens(baseFile, 'td') === opens(hostFile, 'td'), 'A1 a scripted filename opens no extra cell');
ok(!hostFile.includes('<script'), 'A2 ... and is not a script element');
ok(opens(baseFile, 'span') === opens(hostFile, 'span'), 'A3 a closing tag in a table name opens no extra span');
ok(baseFile.includes('lot.csv'), 'A4 CONTROL: a benign filename still reaches the cell');

const benignItem = { filename: 'a.csv', table_name: 'wafer', lane: 'normal', progress: 40, status: 'RUNNING', processed_rows: 5, total_rows: 10, elapsed_seconds: 3 };
const baseItem = rows.activeIngestionRowHtml(benignItem, { elapsedText: '3s' });
const hostItem = rows.activeIngestionRowHtml(
  { ...benignItem, filename: CELL_BREAK, table_name: '<script>alert(1)</script>' }, { elapsedText: '3s' });
ok(opens(baseItem, 'td') === opens(hostItem, 'td')
  && opens(baseItem, 'span') === opens(hostItem, 'span')
  && !hostItem.includes('<script'),
  'B1 an in-flight filename cannot add a cell, a badge, or a script');
ok(baseItem.includes('40%'), 'B2 CONTROL: the locally computed percent is NOT escaped away');

// 🔴 `config_file` sits INSIDE a badge fragment. That is why the badge moved into the module:
//    had it stayed at the call site, this value would be escaped in one file and printed in
//    another, and the two would drift — which is the defect this whole sweep found.
const benignWs = { name: 'ws1', table_name: 'wafer', has_config: true, config_file: 'cfg.json', custom_scripts: [], raw_files_count: 0 };
const baseWs = rows.workspaceRowHtml(benignWs);
const hostWs = rows.workspaceRowHtml({ ...benignWs, config_file: BREAKOUT, name: '<script>x</script>' });
ok(opens(baseWs, 'span') === opens(hostWs, 'span'), 'C3 a hostile config filename cannot open a badge of its own');
ok(baseWs.includes('badge badge-success') && baseWs.includes('cfg.json'),
  'C4 CONTROL: the badge is still markup and still carries its name');

const baseMap = rows.mapperRowHtml({ filename: 'm.py', module_name: 'mappers.m', functions: [1, 2] });
const hostMap = rows.mapperRowHtml({ filename: BREAKOUT, module_name: '<script>x</script>', functions: [1, 2] });
ok(opens(baseMap, 'td') === opens(hostMap, 'td') && !hostMap.includes('<script'),
  'D1 a hostile mapper module name opens no cell and is no script');
ok(baseMap.includes('>2<'), 'D2 CONTROL: the function count is a number, not escaped to nothing');

// 🔴 THE ATTRIBUTE POSITION. `data-table`/`data-script` are read back by the Run Now button, so
//    the value lands inside quotes. A copy that escaped `& < >` and left quotes alone — one of
//    the three found last round — is SAFE in a cell and UNSAFE here. Same name, different reach.
const benignCol = { table_name: 'wafer', script_name: 's.py', cron_expression: '0 * * * *', last_status: 'SUCCESS', next_run: '', last_run: '' };
const opts = { isActive: true, nextRunText: '-', lastRunText: '-' };
const hostCol = rows.autoUpdateRowHtml({ ...benignCol, table_name: ATTR_BREAK, script_name: ATTR_BREAK }, opts);
ok(!/data-table="x" onmouseover=/.test(hostCol), 'E1 a quote in a table name cannot close data-table');
ok(!/data-script="x" onmouseover=/.test(hostCol), 'E2 ... nor data-script');
ok(opens(rows.autoUpdateRowHtml(benignCol, opts), 'button') === opens(hostCol, 'button'),
  'E3 ... and no extra button appears');
ok(rows.autoUpdateRowHtml(benignCol, opts).includes('data-table="wafer"'),
  'E4 CONTROL: a benign table name is still readable by the click handler');

// 🔴 DRIFT ORACLE, named as one. No behavioural check can see a NEW template appearing in
//    another file with the value dropped in raw — that code is on no path this harness calls —
//    so the population is asked of the source. The number is the one this round leaves behind,
//    and it must go DOWN or be re-baselined deliberately.
console.log('\n-- how many templates still interpolate without escaping --------------');
// 🔴 THROUGH THE SHARED READER. This oracle matches source text, so it is the same class as the
//    five harnesses a checkout reddened on 2026-09-07 — it is safe today only because `\s` in its
//    pattern happens to swallow a carriage return, which is luck, not a decision. Measured while
//    repairing those five: 33 harnesses carry their OWN copy of this normalisation. This one does
//    not become the 34th.
const { readdirSync, statSync } = await import('node:fs');
const { readSourceText, isProbeArtifact } = await import('./lib/probe.mjs');
const path = (await import('node:path')).default;
const { fileURLToPath } = await import('node:url');
const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src');
function jsFiles(dir) {
  const out = [];
  for (const e of readdirSync(dir)) {
    const p = path.join(dir, e);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (e.endsWith('.js') && !isProbeArtifact(e)) out.push(p);
  }
  return out;
}
const BT = String.fromCharCode(96);
const RX = new RegExp(`innerHTML\\s*=\\s*${BT}([\\s\\S]*?)${BT}`, 'g');
let unescaped = 0;
for (const p of jsFiles(SRC)) {
  const src = readSourceText(p).text;
  for (const m of src.matchAll(RX)) {
    const body = m[1];
    if (!body.includes('${')) continue;
    if (/\$\{[^}]*\b(esc|escapeHtml|escapeHtmlAttr|encodeURI)/.test(body)) continue;
    unescaped += 1;
  }
}
// 20 is what this round leaves: 25 before, minus the five admin list rows repaired above.
ok(unescaped <= 20, `P1 unescaped interpolating templates: ${unescaped} (ceiling 20, was 25)`);
ok(unescaped > 0, 'P2 ... and the ceiling is not vacuously true — the work is not finished');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
