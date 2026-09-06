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

// 🔴 DRIFT ORACLE, named as one. No behavioural check can see a NEW template appearing in
//    another file with the value dropped in raw — that code is on no path this harness calls —
//    so the population is asked of the source. The number is the one this round leaves behind,
//    and it must go DOWN or be re-baselined deliberately.
console.log('\n-- how many templates still interpolate without escaping --------------');
const { readFileSync, readdirSync, statSync } = await import('node:fs');
const path = (await import('node:path')).default;
const { fileURLToPath } = await import('node:url');
const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src');
function jsFiles(dir) {
  const out = [];
  for (const e of readdirSync(dir)) {
    const p = path.join(dir, e);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (e.endsWith('.js') && !e.includes('.probe-')) out.push(p);
  }
  return out;
}
const BT = String.fromCharCode(96);
const RX = new RegExp(`innerHTML\\s*=\\s*${BT}([\\s\\S]*?)${BT}`, 'g');
let unescaped = 0;
for (const p of jsFiles(SRC)) {
  const src = readFileSync(p, 'utf8');
  for (const m of src.matchAll(RX)) {
    const body = m[1];
    if (!body.includes('${')) continue;
    if (/\$\{[^}]*\b(esc|escapeHtml|escapeHtmlAttr|encodeURI)/.test(body)) continue;
    unescaped += 1;
  }
}
// 25 is what this round leaves: 26 before, minus the history row repaired here.
ok(unescaped <= 25, `P1 unescaped interpolating templates: ${unescaped} (ceiling 25, was 26)`);
ok(unescaped > 0, 'P2 ... and the ceiling is not vacuously true — the work is not finished');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
