#!/usr/bin/env node
// screen_layout_harness's verdict outlives its cleanup (lead 10-13): run on one entry with every 'screens-' folder
// removal throwing EBUSY (lib/fail_folder_removal.mjs, preloaded), it still prints its ASSERTIONS line, before any
// cleanup line, says each folder it could not remove in one line, and exits with its verdict's code.
// Measured 10-13 on the testbed tree: an EBUSY thrown in the 1.5 s removal timer between two mutants ended a 3200 s
// run before that line - 30 of 33 mutants run, no verdict.
//   node client2/tests/screen_layout_cleanup_harness.mjs
import { spawnSync } from 'node:child_process';
import { writeFileSync, rmSync, existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { readSourceText } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, 'screen_layout_harness.mjs');
const FAULT = pathToFileURL(path.join(HERE, 'lib', 'fail_folder_removal.mjs')).href;
const ENTRY = 'sample.html';

// The temp folders a run made - a crashed run never names its build folder (lead 10-22 ㄴ: the source is built per run).
const temps = () => new Set(readdirSync(tmpdir()).filter((n) => n.startsWith('screens-')).map((n) => path.join(tmpdir(), n)));

function run(file) {
  const before = temps();
  const r = spawnSync(process.execPath, ['--import', FAULT, file, '--only', ENTRY], { encoding: 'utf8', timeout: 300000 });
  const lines = `${r.stdout || ''}\n${r.stderr || ''}`.split(/\r?\n/);
  const verdictAt = lines.findIndex((l) => /^ASSERTIONS \d+ \d+$/.test(l));
  const verdict = verdictAt < 0 ? null : lines[verdictAt].split(' ').slice(1).map(Number);
  const notRemoved = lines.map((l, i) => [l, i]).filter(([l]) => /folder not removed: /.test(l));
  // The folders the fault kept, from the lines that say them or from the EBUSY a crashed run died on.
  const kept = new Set([...notRemoved.map(([l]) => l.replace(/^\S+ folder not removed: /, '').replace(/ \S+$/, '')),
    ...lines.flatMap((l) => [...l.matchAll(/rmdir '([^']*screens-[^']*)'/g)].map((m) => m[1])),
    ...[...temps()].filter((d) => !before.has(d))]);
  return { code: r.status, verdict, verdictAt, notRemoved, kept };
}

const cells = (r) => [
  ['C1 every folder removal throwing EBUSY: the ASSERTIONS line is still printed, before any cleanup line',
    r.verdict !== null && r.notRemoved.length > 0 && r.notRemoved.every(([, i]) => i > r.verdictAt)],
  ['C2 each profile folder (and the source build: «build») it could not remove is said in one line - «profile folder not removed: <path> EBUSY»',
    r.notRemoved.length > 0 && r.notRemoved.every(([l]) => /^(profile|build) folder not removed: \S*screens-\S+ EBUSY$/.test(l))],
  ['C3 the failed removals change nothing: the exit code is the verdict\'s',
    r.verdict !== null && r.code === (r.verdict[1] > 0 ? 1 : 0)],
];

// The folders the fault kept are this run's own: removed here, for real.
function sweep(r) {
  for (const dir of r.kept) {
    try { if (existsSync(dir)) rmSync(dir, { recursive: true, force: true }); } catch { /* left in %TEMP% */ }
  }
}

const TEXT = readSourceText(SUBJECT).text;   // the one reader (LF) - the anchors below are written with \n
const swap = (from, to) => {
  if (!TEXT.includes(from)) {
    console.error(`HARNESS FAILURE: mutation anchor stopped matching: ${JSON.stringify(from.slice(0, 80))}`);
    console.log('ASSERTIONS 0 1');
    process.exit(2);
  }
  return TEXT.replace(from, to);
};
const DEFECTS = [
  ['D1 the folders removed before the verdict line, uncaught (the code before) -> C1', 'C1',
    () => swap("console.log(`ASSERTIONS ${ran} ${failed}`);\nawait sleep(1500);   // the last Chrome's children let go of its profile\n"
      + "for (const dir of folders) removeFolder(dir, 'profile');\n",
    "await sleep(1500);\nfor (const dir of folders) rmSync(dir, { recursive: true, force: true });\nconsole.log(`ASSERTIONS ${ran} ${failed}`);\n")],
  ['D2 a removal that fails is not caught -> C3', 'C3',
    () => swap("  try { rmSync(dir, { recursive: true, force: true }); } catch (err) { console.log(`${what} folder not removed: ${dir} ${err.code || err.message}`); }",
      '  rmSync(dir, { recursive: true, force: true });')],
];

let pass = 0;
let fail = 0;
const failed = [];
console.log('-- screen_layout cleanup (lead 10-13) -------------------------------');
const base = run(SUBJECT);
sweep(base);
for (const [name, ok] of cells(base)) {
  console.log(`  ${ok ? 'OK ' : 'BAD'}  ${name}`);
  if (ok) pass += 1; else { fail += 1; failed.push(name); }
}
if (!base.verdict) console.log(`  (the run printed no ASSERTIONS line; exit ${base.code})`);

console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
let escaped = 0;
for (const [name, names, make] of DEFECTS) {
  // Beside the subject so its relative paths hold; the probe infix and this pid name it (lib/probe.mjs isProbeArtifact),
  // so one left by a crash is a stray the gate reports.
  const copy = path.join(HERE, `screen_layout_harness.__probe__.p${process.pid}_cleanup.mjs`);
  let r;
  try {
    writeFileSync(copy, make());
    r = run(copy);
  } finally {
    rmSync(copy, { force: true });
  }
  sweep(r);
  const caught = cells(r).some(([n, ok]) => n.startsWith(names) && !ok);
  if (!caught) escaped += 1;
  console.log(`  ${caught ? 'caught ' : 'ESCAPED'} ${name}`);
}

console.log('');
console.log(`${pass} passed, ${fail} failed; ${DEFECTS.length - escaped}/${DEFECTS.length} defects caught.`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
if (fail) console.log(`FAILED: ${failed.join(' | ')}`);
if (fail || escaped) process.exitCode = 1;
