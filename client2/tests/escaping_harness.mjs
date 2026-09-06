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

// -- tranche 3: where a value CAME FROM, and the selected-cell panel --------------------
// 🔴 TWO DIFFERENT TREATMENTS, AND THE REASON IS MEASURED, NOT ASSUMED. `main.js` imports
//    ag-grid's CSS so node cannot load it, and its two source rows were lifted into
//    `source_rows.js` to be importable. `ui.js` HAS no such import — checked by importing it —
//    so its template was escaped in place and the harness runs the real `updateSelectedCellUI`.
//    Extracting it anyway would have created a module for no reason the measurement supports.
console.log('\n-- the source rows, and the selected-cell panel ------------------------');
const srcRows = await import('../src/source_rows.js');

const baseSrc = srcRows.sourceRowHtml('excel', { value: 42, updated_by: 'kim', timestamp: null }, { isPinned: false });
const hostSrc = srcRows.sourceRowHtml(CELL_BREAK, { value: BREAKOUT, updated_by: ATTR_BREAK, timestamp: null }, { isPinned: false });
ok(opens(baseSrc, 'td') === opens(hostSrc, 'td'), 'F1 a hostile source name opens no extra cell');
ok(opens(baseSrc, 'span') === opens(hostSrc, 'span') && !hostSrc.includes('<script'),
  'F2 ... and a hostile value opens no element of its own');
// 🔴 THE ATTRIBUTE POSITION AGAIN. `updated_by` lands inside `title="…"`, which is where the
//    quote-only drift found in tranche one was unsafe while reading as correct.
ok(!/title="Updated by x" onmouseover=/.test(hostSrc), 'F3 updated_by cannot close the title attribute');
ok(baseSrc.includes('excel') && baseSrc.includes('kim') && baseSrc.includes('>42<'),
  'F4 CONTROL: benign name, author and value all still reach the row');

const baseAll = srcRows.sourceRowAllHtml('excel', ['a', 'a'], { isPinnedAll: true });
const hostAll = srcRows.sourceRowAllHtml(BREAKOUT, [CELL_BREAK], { isPinnedAll: true });
ok(opens(baseAll, 'td') === opens(hostAll, 'td') && opens(baseAll, 'span') === opens(hostAll, 'span'),
  'G1 the selection row is closed the same way');
ok(srcRows.sourceRowAllHtml('excel', ['a', 'b'], { isPinnedAll: false }).includes('Multiple Values (2 types)'),
  'G2 CONTROL: the distinct-count sentence is still built and not escaped away');

// -- the real ui.js function, driven through a DOM stub ----------------------------------
// 🔴 `elements` reads `document.getElementById` through LAZY getters, so the stub only has to
//    exist when the function is CALLED. That is what makes scoring the real function possible
//    here without a browser, and it is why this one did not need extracting.
const slot = { innerHTML: '' };
globalThis.document = { getElementById: () => slot };
const { state } = await import('../src/state.js');
const { updateSelectedCellUI } = await import('../src/ui.js');

state.currentVirtualColumns = [{ name: 'joined', right_table: BREAKOUT }];
state.selectedCell = { rowId: CELL_BREAK, colId: 'joined', value: '<script>alert(1)</script>' };
updateSelectedCellUI();
const panel = slot.innerHTML;
ok(!panel.includes('<script'), 'U1 a scripted cell value is not a script element');
ok(opens(panel, 'div') === 4, `U2 the panel opens exactly its own four divs (saw ${opens(panel, 'div')})`);
ok(opens(panel, 'td') === 0, 'U3 a row id carrying a cell break opens no cell');
ok(!panel.includes(BREAKOUT), 'U4 a hostile join table name does not arrive as markup');

state.selectedCell = { rowId: 'r1', colId: 'qty', value: null };
state.currentVirtualColumns = [];
updateSelectedCellUI();
ok(slot.innerHTML.includes('NULL'), 'U5 CONTROL: an absent value still reads NULL, not empty');
state.selectedCell = { rowId: 'r1', colId: 'qty', value: 0 };
updateSelectedCellUI();
ok(/<code>0<\/code>/.test(slot.innerHTML), 'U6 CONTROL: zero survives as zero, not as NULL');

// -- tranche 4: the audit timeline, which reflects what an operator typed ----------------
// 🔴 THE REAL EXPORTED FUNCTIONS, driven through a DOM stub. `timeline.js` imports cleanly, so
//    like `ui.js` it is scored in place rather than carved up. What makes this surface matter:
//    `formatVal` does NOT escape — it returns `String(v)` — so the old and new cell values
//    reached the DOM raw, which is the same shape as the history row repaired in tranche one,
//    on the row beside it.
// ⚠️ Escaping is applied AT THE INTERPOLATION, because `timeline.js:224` already does exactly
//    that. Putting it inside `formatVal` would make the formatter a second escaping author and
//    double-escape the site that already wraps it.
console.log('\n-- the audit timeline, as the screen builds it ------------------------');
function stubEl() {
  const el = {
    className: '', innerHTML: '', textContent: '', dataset: {}, children: [],
    classList: { add() {}, remove() {}, contains: () => false },
    style: {}, addEventListener() {},
    // 🔴 PERMISSIVE ONLY WHERE IT CANNOT SOFTEN THE ASSERTION. The real function looks up
    //    `.timeline-card` to bind a click, and returning null there kills it before it returns.
    //    Every assertion below reads `innerHTML`, which is already set by then, so handing back
    //    an element lets the subject finish without deciding anything the test measures.
    querySelector: () => stubEl(),
    appendChild(c) { el.children.push(c); return c; },
  };
  return el;
}
globalThis.document = { getElementById: () => slot, createElement: () => stubEl() };
const tl = await import('../src/timeline.js');

const benignLog = {
  updated_by: 'kim', table_name: 'wafer', column_name: 'qty', business_key: 'BK-1',
  row_id: 'abcdef1234', old_value: '1', new_value: '2', source_name: 'user',
  timestamp: '2026-09-07T01:00:00Z',
};
const baseItem2 = tl.createGlobalTimelineItemDom({ transaction_id: 't1', total_count: 1, logs: [benignLog] });
const hostItem2 = tl.createGlobalTimelineItemDom({
  transaction_id: 't1', total_count: 1,
  logs: [{ ...benignLog, updated_by: ATTR_BREAK, column_name: BREAKOUT, new_value: '<script>alert(1)</script>', business_key: CELL_BREAK }],
});
ok(baseItem2 && hostItem2, 'T0 both rows were actually built — else the rest is vacuous');
ok(!hostItem2.innerHTML.includes('<script'), 'T1 a scripted cell value is not a script element');
ok(opens(baseItem2.innerHTML, 'span') === opens(hostItem2.innerHTML, 'span'),
  'T2 a hostile column name opens no extra span');
ok(opens(baseItem2.innerHTML, 'td') === 0 && opens(hostItem2.innerHTML, 'td') === 0,
  'T3 a business key carrying a cell break opens no cell');
// 🔴 `displayTitle` lands inside `title="…"`, and it is BUILT from updated_by — so an attribute
//    break in the author name reaches an attribute by way of a composed string.
ok(!/title="[^"]*" onmouseover=/.test(hostItem2.innerHTML), 'T4 the composed title cannot close its attribute');
ok(baseItem2.innerHTML.includes('kim') && baseItem2.innerHTML.includes('qty'),
  'T5 CONTROL: a benign author and column still reach the row');
ok(baseItem2.innerHTML.includes('kind-overwrite') || baseItem2.innerHTML.includes('audit-pill'),
  'T6 CONTROL: the locally decided kind pill is still markup');

const subBox = stubEl();
tl.renderSubDetails(subBox, [{ ...benignLog, column_name: BREAKOUT, new_value: CELL_BREAK }]);
// ⚠️ The rows are nested inside a `ul` the function builds, so reading only the container's
//    direct children returned empty markup and the count assertion read 0 — a pass shaped like
//    a failure. Walk the tree instead of guessing the depth.
const allHtml = (el) => [el.innerHTML || '', ...el.children.flatMap(allHtml)].join('');
const subHtml = allHtml(subBox);
ok(subHtml.length > 0, 'T7 a sub-detail row was actually built and its markup was found');
ok(!subHtml.includes('<td') && opens(subHtml, 'span') === 2,
  `T8 a sub-detail label opens only its own two spans (saw ${opens(subHtml, 'span')})`);

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
// 15 is what this round leaves: 17 before, minus the audit row and its sub-detail line.
ok(unescaped <= 15, `P1 unescaped interpolating templates: ${unescaped} (ceiling 15, was 17)`);
ok(unescaped > 0, 'P2 ... and the ceiling is not vacuously true — the work is not finished');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
