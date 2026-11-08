// WHAT REACHES THE SCREEN CHECKER — the harness runner's pick and the checker's --touched give one answer (lead 11-08):
// a change that picks screen_layout_harness runs at least one screen. Before, a guide md picked it (its text names
// table_config.md) and its --touched ran nothing - «ran 0», a blocking red on every guide edit.
//
// The subject is imported whole; the pages' modules come from one real vite build, the runner's reach from
// harnessesToRun itself. What is scored:
//   R1 a guide md only - the page that names it runs (admin.html names table_config.md)
//   R2 the guide list only (server/admin/help_guides.json, which the checker reads and no page names) - every screen
//   R3 a file in the checker's SCANS cell that no page reaches (client2/.gitignore) - every screen
//   R4 every tracked file the runner picks the checker for runs a screen - none is narrowed to nothing
//   R5 a landed commit measured again (check_harnesses --commit, D 11-08): narrowed by that commit's files - 287b194d4
//      (table_config.md among them) runs admin.html, whatever this tree holds
//   R6 no commit: the files changed since this tree left origin/main, as before
// Running a screen for a guide md keeps the two answers one; it does not measure the md (the checker draws the guide
// from its own text and help_guides.json).
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../scripts/module_reach.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLIENT = path.resolve(HERE, '..');
const SRC_PATH = path.join(CLIENT, 'scripts', 'module_reach.mjs');
const CHECKER = 'screen_layout_harness.mjs';
const LANDED = '287b194d4';   // access: a row of an edit_by table deleted - it changed docs/guide/config/table_config.md
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

const { top, tracked, byBase } = BASELINE.trackedFiles(CLIENT);
const at = (rel) => BASELINE.norm(`${top}/${rel}`);

// The pages' modules, as the checker's own build bundles them (vite.config.js's pages).
const reached = new Map();
const { build } = await import('vite');
const out = mkdtempSync(path.join(tmpdir(), 'module-reach-harness-'));
try {
  await build({ root: CLIENT, configFile: path.join(CLIENT, 'vite.config.js'), logLevel: 'silent',
    build: { outDir: out, emptyOutDir: true, write: false }, plugins: [BASELINE.reachPlugin(reached)] });
} finally {
  rmSync(out, { recursive: true, force: true });
}
const graph = new Map([...reached].filter(([id]) => id.endsWith('.html')).map(([id, ids]) => [path.posix.basename(id), ids]));
if (graph.size < 5) die(`the build gave ${graph.size} pages - the checker's pages did not build`);

// The runner's pick, from the runner itself: what it says the checker reaches, and its SCANS cell.
const scopes = BASELINE.scansOf(CHECKER);
if (!scopes) die(`${CHECKER} has no SCANS cell - R3 asks nothing`);
const runner = await BASELINE.harnessesToRun({ client: CLIENT, tests: HERE, harnesses: [CHECKER], changed: [],
  scans: new Map([[CHECKER, scopes]]) });
const runnerReach = runner.reach.get(CHECKER);
if (!runnerReach || runnerReach.size < 10) die(`the runner gave the checker ${runnerReach ? runnerReach.size : 'no'} reach`);
const picks = (f) => runnerReach.has(f) || Boolean(scopes && BASELINE.scanCovers(scopes, top, f, 'file'));

/** The questions, asked of a (possibly mutated) module: the failures' names, and what each saw. */
function verdict(M) {
  const bad = [];
  const saw = {};
  const check = (name, cond, what) => { if (!cond) { bad.push(name); saw[name] = what; } };
  const pages = new Map([...graph].map(([entry, ids]) => [entry, M.pageReach(ids, byBase)]));
  const { reach: own } = M.textReach({ file: path.join(HERE, CHECKER), tests: HERE, top, tracked, byBase, scopes: M.scansOf(CHECKER) });
  const screens = (rel) => M.screensTouched({ pages, changed: [at(rel)], own });
  const guide = screens('docs/guide/config/table_config.md');
  check('R1', Array.isArray(guide) && guide.includes('admin.html'), guide);
  const list = screens('server/admin/help_guides.json');
  check('R2', list === null, list);
  const ignore = screens('client2/.gitignore');
  check('R3', ignore === null, ignore);
  const picked = tracked.filter(picks);
  const none = picked.filter((f) => { const s = M.screensTouched({ pages, changed: [f], own }); return s !== null && !s.length; });
  check('R4', picked.length > 100 && !none.length, { picked: picked.length, narrowedToNothing: none.slice(0, 5) });
  const touched = (commit) => M.touchedScreens({ client: CLIENT, commit, graph, checker: path.join(HERE, CHECKER) });
  const landed = touched(LANDED);
  const landedFiles = BASELINE.changedFiles(CLIENT, LANDED);
  check('R5', landedFiles.length > 0 && Array.isArray(landed) && landed.includes('admin.html')
    && JSON.stringify(landed) === JSON.stringify(M.screensTouched({ pages, changed: landedFiles, own })), landed);
  const tree = touched(null);
  check('R6', JSON.stringify(tree) === JSON.stringify(M.screensTouched({ pages, changed: BASELINE.changedFiles(CLIENT), own })), tree);
  return { bad, saw };
}

console.log('-- the real module --');
const real = verdict(BASELINE);
for (const line of ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']) ok(line, !real.bad.includes(line), real.saw[line]);
// The runner's own sides of R2 and R3: it picks the checker for them (else they would ask nothing).
ok('R2 the runner picks the checker for the guide list', picks(at('server/admin/help_guides.json')));
ok('R3 the runner picks the checker for client2/.gitignore', picks(at('client2/.gitignore')));

const swap = (from, to) => (src) => { if (!src.includes(from)) die(`mutant anchor gone: ${from.slice(0, 60)}`); return src.replace(from, to); };
const DEFECTS = [
  ['R1', 'a page reaches only its modules', swap('  const reach = new Set(ids);\n  for (const id of ids) {', '  const reach = new Set(ids);\n  for (const id of []) {')],
  ['R2', 'a change only the checker reaches runs nothing', swap('  if (!picked.length && changed.some((f) => own.has(f))) return null;\n', '')],
  ['R5', 'the checker narrows by this tree, not the runner\'s commit', swap('  const changed = changedFiles(client, commit);\n  const {', '  const changed = changedFiles(client);\n  const {')],
  ['R3', 'the checker\'s own reach leaves its SCANS cell out', swap("  if (scopes) for (const f of tracked) if (scanCovers(scopes, top, f, 'file')) reach.add(f);\n  return { own, reach };",
    '  return { own, reach };')],
];
const CONTROLS = [
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')],
];
console.log('\n-- defect mutants (each caught by its line) --');
let caught = 0;
for (const [line, name, mutate] of DEFECTS) {
  const M = (await loadWithProbe(SRC_PATH, { mutate, tag: 'modulereach' })).module;
  let bad;
  try { bad = verdict(M).bad; } catch (e) { bad = [line, String(e && e.message)]; }
  if (bad.includes(line)) { caught++; console.log(`  caught  ${line} ${name}`); }
  else { failed++; console.log(`  ESCAPED ${line} ${name}  saw: ${JSON.stringify(bad)}`); }
}
console.log('\n-- controls (each wakes nothing) --');
let escaped = 0;
for (const [name, mutate] of CONTROLS) {
  const { bad } = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'modulereach' })).module);
  if (!bad.length) { escaped++; console.log(`  escaped ${name}`); }
  else { failed++; console.log(`  CAUGHT  ${name}  <- wrong: ${JSON.stringify(bad)}`); }
}
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; ${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed + DEFECTS.length + CONTROLS.length} ${failed}`);
if (failed) process.exit(1);
