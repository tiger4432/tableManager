#!/usr/bin/env node
//
// Run every harness under `client2/tests/`, and fail the build on the ones that are supposed
// to be green.
//
// WHY THIS EXISTS. `client2/tests/` held 15 harnesses and nothing ran 14 of them: only
// `value_suggest_keys_harness.mjs` had a package.json script. The sibling gate
// (`check_contracts.mjs`) covers `contracts/*/client_harness.mjs` and stops at that directory.
// The cost of the gap is measured, not hypothetical: `da8f390` added one module global to
// `getGridCellObject` and killed `company_roundtrip_harness.mjs` and
// `copy_header_count_harness.mjs` outright ― the build stayed green for a full round, and by
// the time anyone looked, `copy_header_count_harness.mjs` had accumulated three more
// independent breakages (`ae2811c`'s `notchMarkCell`, the tsv.js import move, and two
// mutation anchors that stopped matching). A harness nobody runs is a comment.
//
// DISCOVERY, NOT A LIST. Harnesses are found by scanning `client2/tests/*.mjs`, the same way
// `check_contracts.mjs` scans `contracts/`. A hardcoded roster would recreate the exact defect
// this closes: harness #16 lands, nobody adds it here, and it is dead on arrival.
//
// KNOWN_RED IS A DEBT LIST, NOT A SKIP LIST. Harnesses that are red TODAY are still executed
// and still reported as failing ― they just do not fail the build, because wedging the build
// on pre-existing red is not a gate, it is an outage. Every entry carries a reason and must be
// removed the moment it goes green (the runner says so out loud when that happens). A silent
// skip would be the same defect as no gate at all.
//
// EXIT CODE IS THE VERDICT; `ASSERTIONS <ran> <failed>` IS THE EVIDENCE. Exit code alone
// cannot tell "red with N assertions" from "red with 0 assertions": a harness that crashes
// before asserting anything looks exactly like one that ran and failed, and this week that
// disguise hid 3 dead harnesses as known debt. So every harness prints one machine line,
// `ASSERTIONS <ran> <failed>`, sourced from ITS OWN counters (this runner never counts
// check marks or re-scores prose -- the harness's summary is the only scorer). The runner
// reads that line and blocks when:
//   - a harness exits 0 without the line, or with ran=0, or with failed>0 (a green verdict
//     that measured nothing, or that contradicts its own count, proves nothing);
//   - a KNOWN_RED harness runs fewer assertions than its recorded expectation (it stopped
//     asserting -- that is death, not debt), or fails more than recorded (the debt grew).
// A missing line on a KNOWN_RED entry recorded as ran: 0 is tolerated: that entry already
// says out loud that the harness dies before measuring anything.

import { readHarness, RUN_BUFFER } from './read_harness.mjs';
import { changedFiles, harnessesToRun, norm, scanCovers, sourceDirs } from './module_reach.mjs';
import { NOT_A_HARNESS, KNOWN_RED, FLOORS, CEILINGS, SCANS } from './harness_floors.mjs';
import { readdirSync, existsSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { isProbeArtifact } from '../tests/lib/probe.mjs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const TESTS_DIR = path.join(REPO_ROOT, 'client2', 'tests');

// 🔴 THE EXIT CODE IS THE GATE, AND REMOVING IT IS NOT THE SAME AS MARKING SOMETHING RED.
//    On 2026-08-09 this line lost its `process.exit(1)` so the candidate-axis migration could
//    land, and the cost was measured over the following week: a clean exit proved nothing, so
//    every lane had to hand the Lead PM `✓`/`✗` lines by hand, and 794 assertions that had
//    stopped executing were carried as debt rather than noticed as death. A disabled gate leaves
//    NOTHING TO GREP FOR and reads, from the outside, exactly like a gate that runs.
//
//    `KNOWN_RED` is the marker that exists for this. An entry there is still RUN and still
//    REPORTED and still does not block -- that is the whole design (see the debt-list note
//    below) -- so a migration in flight has a way to say so out loud, in one place, per harness,
//    with a reason attached. Reaching for the exit code instead trades a per-harness statement
//    for a silence covering all of them.
const fail = msg => { console.error(`\n✗ ${msg}\n`); process.exit(1); };

// ── known-red MEMBERS, not just the count ───────────────────────────────────────
// WHY THIS EXISTS, MEASURED. `failed <= known.failed` is a count check, and a count is a
// proxy for the claim "no NEW failure appeared". On 2026-08-06 a refactor added one failure
// to `valid_die_frame_adoption_harness` (`F6/C/adoption-would-have-moved-every-coordinate`,
// a negative control that had gone inert) and took the harness 41 -> 42. The recorded debt
// happened to say 42, so the count check passed and the regression shipped. It was found
// days later by hand-diffing failure names.
//
// 🔴 A DEBT LIST MUST NOT BE A PLACE DEFECTS CAN HIDE. Pin the MEMBERS. A name that is not
//    on the list blocks, whatever the total is; a name on the list that has gone is reported
//    so somebody re-baselines. This is the same rule this repository keeps relearning under
//    other names -- pin the members, not the count.
//
// EXTRACTION IS VALIDATED, NOT TRUSTED. The harnesses print failures in two shapes, and this
// runner never re-scores prose (the harness's own `ASSERTIONS` line is the only scorer). So
// the extracted name count is CROSS-CHECKED against the harness's own `failed` number: if
// they disagree, the parse is unreliable and the runner says so and blocks rather than
// pinning a set it cannot read. That refusal is the honest outcome -- a half-parsed set would
// silently stop protecting the entries it could not read.
//
// ⚠️ TWO ENTRIES CANNOT BE NAME-PINNED AND THAT IS RECORDED, NOT WORKED AROUND.
//    `reposition_regime_probe` and `split_registry_harness` throw before asserting: measured
//    2026-08-06, both emit ZERO failure lines. There are no members to pin, `ran: 0` is the
//    whole of what can be checked, and they are marked `namesUnavailable` so the gap is
//    visible in the output instead of looking like a pin that passes.
function failureNamesOf(stdout) {
  const out = [];
  for (const line of (stdout || '').split(/\r?\n/)) {
    let m = /^\s*(?:✗|x)\s+(.+)$/.exec(line);
    if (!m) m = /^\s*FAIL\s+(.+)$/.exec(line);
    if (!m) continue;
    const n = m[1].split(':')[0].trim();
    if (!n || /^baseline$/i.test(n)) continue;       // the harness's own summary line
    out.push(n);
  }
  return [...new Set(out)];
}

function knownRedNameVerdict(name, known, run, counts) {
  if (known.namesUnavailable) return { blocked: false, message: '' };
  if (!Array.isArray(known.failures)) {
    return { blocked: true, message: `This entry has no \`failures\` list, so only its count `
      + `is protected and a swapped failure would pass. Add the member list.` };
  }
  const seen = failureNamesOf(run.stdout);
  if (seen.length !== counts.failed) {
    return { blocked: true, message: `parsed ${seen.length} failure name(s) but the harness `
      + `reports ${counts.failed} ― the extraction is unreliable here, so the member pin is `
      + `NOT protecting this entry. Fix the parse or mark the entry \`namesUnavailable\` with `
      + `a reason; do not leave it looking pinned.` };
  }
  const pinned = new Set(known.failures);
  const added = seen.filter(n => !pinned.has(n));
  if (added.length > 0) {
    return { blocked: true, message: `NEW failure(s) not on the recorded list:\n    ― `
      + added.join('\n    ― ') + `\n    A new failure inside an existing red count is exactly `
      + `what this check exists to catch. Fix it, or re-triage the entry deliberately.` };
  }
  return { blocked: false, message: '', gone: [...pinned].filter(n => !seen.includes(n)) };
}

const doubleBooked = [...FLOORS.keys()].filter(n => KNOWN_RED.has(n));
if (doubleBooked.length > 0) {
  fail(`${doubleBooked.join(', ')} appear(s) in BOTH \`FLOORS\` and \`KNOWN_RED\`. A harness's `
     + `floor must live in exactly one place ― two copies drift, and the looser one wins by `
     + `accident. Keep the floor on the KNOWN_RED entry while it is debt; move it to FLOORS `
     + `when it goes green.`);
}

if (!existsSync(TESTS_DIR)) {
  fail(`no \`client2/tests/\` directory at ${TESTS_DIR}. If the harnesses moved, update this `
     + `runner ― an empty scan must never pass as "all harnesses green".`);
}

const harnesses = readdirSync(TESTS_DIR, { withFileTypes: true })
  .filter(d => d.isFile() && d.name.endsWith('.mjs'))
  .map(d => d.name)
  .filter(n => !NOT_A_HARNESS.has(n))
  .sort((a, b) => a.localeCompare(b));

// Named out loud on every run. A file that is skipped silently is a file nobody remembers
// exists, and the next person to read `tests/` cannot tell "deliberately not gated" from
// "forgotten".
for (const [name, why] of NOT_A_HARNESS) {
  if (!existsSync(path.join(TESTS_DIR, name))) {
    fail(`\`NOT_A_HARNESS\` names \`${name}\`, which is not in \`client2/tests/\`. `
      + 'Either it was deleted and this entry should go with it, or it was renamed and the '
      + 'entry now skips nothing.');
  }
  console.log(`  · skipped (not a harness) ${name} — ${why}`);
}

// ── C-35 ③-0: THE ONE PATH THAT COULD STAY SILENT ────────────────────────────
//
// 🔴 The sweep above is a `readdirSync` and it is NOT recursive, so a `.mjs` in a SUBFOLDER
//    of `client2/tests/` never runs and nothing says so. Today that is `lib/`, `fixtures/`
//    and `oracle/` — libraries, correctly not run, and every one is imported by a harness.
//    But a standalone harness dropped into one of those folders would be invisible forever,
//    and 「a guard goes wrong the day it becomes reachable」 is exactly this shape.
//
// This is the RECURSIVE half of the `NOT_A_HARNESS` rule above: a file that is not run has
// to be accounted for OUT LOUD. Here the account is 「something imports it」 — that is what
// makes it a library rather than a forgotten harness.
{
  const subFiles = [];
  for (const d of readdirSync(TESTS_DIR, { withFileTypes: true })) {
    if (!d.isDirectory()) continue;
    const dir = path.join(TESTS_DIR, d.name);
    for (const g of readdirSync(dir, { withFileTypes: true })) {
      if (g.isFile() && g.name.endsWith(".mjs")) subFiles.push(`${d.name}/${g.name}`);
    }
  }
  // Who imports what. Read the gated harnesses AND the subfolder files themselves, because a
  // library may be used only by another library.
  const readers = [
    ...harnesses.map((n) => path.join(TESTS_DIR, n)),
    ...subFiles.map((rel) => path.join(TESTS_DIR, rel)),
  ];
  const corpus = readers.map((fp) => {
    try { return readFileSync(fp, "utf8"); } catch { return ""; }
  });
  const orphans = subFiles.filter((rel) => {
    const base = path.basename(rel);
    const self = path.join(TESTS_DIR, rel);
    return !corpus.some((text, i) => readers[i] !== self && text.includes(base));
  });
  if (orphans.length) {
    fail(`these sit in a SUBFOLDER of \`client2/tests/\`, so this gate never runs them, and `
      + `nothing imports them either: ${orphans.join(", ")}. A harness there would be `
      + `invisible forever. Either something should import it (it is a library) or it belongs `
      + `beside the other harnesses (it is a harness).`);
  }
  console.log(`  · subfolder .mjs accounted for: ${subFiles.length} (every one imported)`);
}

if (harnesses.length === 0) {
  fail(`\`client2/tests/\` holds no \`*.mjs\`. Either every harness was deleted or the layout `
     + `changed ― both need a human, neither is a passing build.`);
}

// ── THE THIRD STATE: "cannot be measured in THIS tree" ────────────────────────
// A harness that needs an installed package (today only the undeclared-identifier check,
// via `rolldown/parseAst`) cannot run in a git worktree, because worktrees get no
// `node_modules`. Reporting that as BLOCKING is not strict, it is BLIND: every worktree
// lane then starts red before touching anything, so the gate number cannot move no matter
// what that lane breaks, and a real regression hides behind the pre-existing red.
//
// So it gets its own verdict -- not green, not red. UNAVAILABLE is claimable ONLY when the
// dependency store is demonstrably absent AND the failure is specifically module
// resolution. If `node_modules` exists and a harness still cannot resolve an import, that
// is a real breakage and stays BLOCKING: this escape hatch must never widen into one a
// broken harness can climb through.
const HAS_NODE_MODULES = existsSync(path.join(REPO_ROOT, 'client2', 'node_modules'));
const UNRESOLVED_IMPORT_RE = /ERR_MODULE_NOT_FOUND|Cannot find package|Cannot find module/;
// What package.json declares and this checkout has not installed (a tree made before cytoscape came, 10-06): the
// blocking and unmeasured lines name them, because the fix is one command and the harness's own error does not say it.
const PACKAGE = JSON.parse(readFileSync(path.join(REPO_ROOT, 'client2', 'package.json'), 'utf8'));
const NOT_INSTALLED = Object.keys({ ...PACKAGE.dependencies, ...PACKAGE.devDependencies })
  .filter(n => !existsSync(path.join(REPO_ROOT, 'client2', 'node_modules', n, 'package.json')));
const INSTALL = NOT_INSTALLED.length > 0
  ? `client2/node_modules lacks ${NOT_INSTALLED.join(', ')} (declared in client2/package.json): run \`npm ci\` once in client2. `
  : '';

const blocking = [];
const unavailable = [];
// The runner could not read what a harness said (read_harness.mjs): no verdict - not a red one, as UNAVAILABLE is not.
const unread = [];
const stillRed = [];
const recovered = [];
const rose = [];        // ran above its recorded floor ― re-baseline when convenient
const unfloored = [];   // discovered but never baselined ― cannot have regressed yet
const shrank = [];      // came in UNDER its ceiling ― good; re-baseline when convenient

// 🔴 C-67: THE PRODUCT TREE CARRIES NO PROBE ARTIFACT, AND THAT IS ASSERTED, NOT ASSUMED.
//    Probe copies used to be written beside their subject in `client2/src`, where every harness
//    that WALKS that tree could list one and then read it after its owner deleted it. That is
//    not hypothetical: three gate runs out of four went red on files nobody had touched, a
//    different harness each time. They now live in `client2/.tmp/probe/…` (gitignored, mirrored
//    so the resolve hook can recover the original directory), and this check is what makes the
//    move a GUARANTEE rather than a habit -- if anything ever writes one back into `src`, the
//    build says so instead of a harness dying at random weeks later.
// ⚠️ The predicate is `isProbeArtifact` from the probe itself, so "what is an artifact" cannot
//    drift between the thing that writes them and the thing that forbids them here.
{
  const srcRoot = path.join(REPO_ROOT, 'client2', 'src');
  const strays = [];
  const walk = (dir) => {
    let entries = [];
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else if (isProbeArtifact(e.name)) strays.push(path.relative(REPO_ROOT, full));
    }
  };
  walk(srcRoot);
  if (strays.length > 0) {
    fail(`${strays.length} probe artifact(s) are sitting in client2/src: ${strays.join(', ')}. `
      + `They belong in client2/.tmp/probe/. A copy in the product tree is visible to every `
      + `harness that walks src, and one that is deleted mid-walk reddens an unrelated harness `
      + `at random ― which is exactly how this build spent an afternoon.`);
  }
}

// 🔴 ONE RULE (lead c4ccdeec3): a harness that reads --mutate runs here WITH it. Mutants kept behind
//    a flag the gate never passed never ran here, and their anchors died with nobody seeing (10-06).
//    The same for --control (lead 10-09: subgraph_view_harness's unmutated subsets).
// --touched (owner 10-24, lead): the screen checker's base and mutants on the screens this tree touched; the whole
//    round runs at night, outside this gate.
const FLAGS = ['--mutate', '--control', '--touched'];
const flagsOf = (name) => {
  const text = readFileSync(path.join(TESTS_DIR, name), 'utf8');
  return FLAGS.filter((f) => text.includes(`process.argv.includes('${f}')`));
};

// Only the harnesses this change reaches (lead 10-27 «ㄴ»): the files changed since this tree left origin/main against
// what each harness reaches - module_reach.mjs, the graph the screen checker's --touched reads. --all runs every
// harness; --commit <rev> takes one commit's files; --dry-run says the list and stops.
const ALL = process.argv.includes('--all');
const commitAt = process.argv.indexOf('--commit');
const COMMIT = commitAt > 0 ? process.argv[commitAt + 1] : null;
const CLIENT_DIR = path.join(REPO_ROOT, 'client2');
const changed = ALL ? null : changedFiles(CLIENT_DIR, COMMIT);
const plan = ALL ? { run: harnesses, notRun: [], why: '--all' }
  : !changed.length ? { run: [], notRun: harnesses, why: null }
  : await harnessesToRun({ client: CLIENT_DIR, tests: TESTS_DIR, harnesses, changed, commit: COMMIT, scans: SCANS });
if (changed && !changed.length) console.log('  · 0 changed files - nothing to run');
else if (plan.why) console.log(`  · every harness runs - ${plan.why}`);
else console.log(`  · ${changed.length} changed file(s), ${plan.run.length} of ${harnesses.length} harnesses reach one`
  + (plan.notRun.length ? ` - not run, no changed file in their reach: ${plan.notRun.join(', ')}` : ''));
if (process.argv.includes('--dry-run')) {
  for (const name of plan.run) console.log(`  run ${name}`);
  process.exit(0);
}

// A harness with a SCANS cell runs watched (scan_watch.mjs); a source folder it lists outside the cell is red.
const SOURCE_DIRS = sourceDirs(REPO_ROOT);
const WATCH = `--import="${pathToFileURL(path.join(HERE, 'scan_watch.mjs')).href}"`;
const watched = (name) => {
  const out = path.join(tmpdir(), `scan-watch-${process.pid}-${name}.txt`);
  rmSync(out, { force: true });
  const env = { NODE_OPTIONS: process.env.NODE_OPTIONS, SCAN_WATCH_OUT: process.env.SCAN_WATCH_OUT };
  process.env.NODE_OPTIONS = [env.NODE_OPTIONS, WATCH].filter(Boolean).join(' ');
  process.env.SCAN_WATCH_OUT = out;
  try {
    return { run: readHarness(path.join(TESTS_DIR, name), flagsOf(name), REPO_ROOT), out };
  } finally {
    for (const [k, v] of Object.entries(env)) if (v === undefined) delete process.env[k]; else process.env[k] = v;
  }
};
const listedOutside = (name, out) => {
  const lines = existsSync(out) ? readFileSync(out, 'utf8').split('\n').filter(Boolean) : [];
  rmSync(out, { force: true });
  return [...new Set(lines.map((l) => { const [dir, deep] = l.split('\t'); return { dir: norm(dir), kind: deep ? 'tree' : 'dir' }; })
    .filter(({ dir, kind }) => SOURCE_DIRS.has(dir) && !scanCovers(SCANS.get(name), REPO_ROOT, dir, kind))
    .map(({ dir, kind }) => `${path.posix.relative(norm(REPO_ROOT), dir)}${kind === 'tree' ? '/**' : ''}`))];
};

for (const name of plan.run) {
  const { run, out } = SCANS.has(name) ? watched(name)
    : { run: readHarness(path.join(TESTS_DIR, name), flagsOf(name), REPO_ROOT), out: null };
  const outside = out ? listedOutside(name, out) : [];
  if (outside.length) {
    blocking.push({ name, run: run || {} });
    console.log(`✗ ${name}  [BLOCKING] it listed ${outside.join(', ')} - outside its SCANS cell `
      + `(${SCANS.get(name).join(', ') || 'none'}) in harness_floors.mjs, so a change there would not run it. Widen the cell.`);
    continue;
  }
  if (!run) {
    unread.push(name);
    console.log(`? ${name}  [NO VERDICT] instrument: its output ran past the runner's ${RUN_BUFFER / 1048576} MiB `
      + 'buffer, so its ASSERTIONS line was never read. Not counted as passing or failing - run it alone to read it.');
    continue;
  }
  const ok = run.status === 0;
  const known = KNOWN_RED.get(name);

  // The harness's own count line; last occurrence wins. Never counted here, only read.
  let counts = null;
  for (const m of (run.stdout || '').matchAll(/^ASSERTIONS (\d+) (\d+)\s*$/gm))
    counts = { ran: +m[1], failed: +m[2] };
  const said = counts ? `ran ${counts.ran}, failed ${counts.failed}` : 'no ASSERTIONS line';

  // 🔴 A RED VERDICT WITH ZERO FAILED ASSERTIONS IS ITS OWN STATE, AND `failed` CANNOT SAY IT.
  //    `failed` carries the ASSERTION counter and nothing else. A harness that scores a mutation
  //    corpus adds its escapes and its caught controls to the EXIT CODE on a separate line
  //    (`retroactive_view_harness.mjs`: `bad = base.fail + escapedNames.length + controlsCaught`,
  //    while the ASSERTIONS line prints `base.fail`). So the one case that machine exists to
  //    catch -- an assertion that stayed green while its subject changed -- surfaces on a RED
  //    line reading `failed 0`, which is exactly the crash disguise the header above says this
  //    line exists to strip, running backwards. Measured 2026-09-06: the summary of a caught
  //    escape was `✗ <name>  [BLOCKING] (ran 318, failed 0)`.
  //
  //    THIS RE-SCORES NOTHING. `ran` and `failed` still come only from the harness's own
  //    counters, and the CAUSE is deliberately not named here: naming it would mean reading the
  //    escaped mutant's name out of stderr, and the contract above closes that for a reason that
  //    is still true. What is stated is only what the two signals the runner ALREADY holds
  //    disagree about -- the exit code says red, the count says nothing failed -- which is true
  //    whatever produced it (an escaped mutant, a caught control, a `die()` after the summary, a
  //    crash on the way out). The harness's own output is dumped in full below and says which.
  //
  //    IT GOES ON BOTH RED BRANCHES. Putting it only on the blocking one would leave two paths
  //    describing the same state differently, which is the owner's criterion ④ -- and this file
  //    is the instrument the rest of that criterion is measured with.
  const beyondCount = (!ok && counts && counts.ran > 0 && counts.failed === 0)
    ? ' ― every assertion it counted PASSED, so the red verdict came from scoring this count '
      + 'does not carry; its own output below says which'
    : '';
  // A narrowed run (its «narrowed:» line) scores the screens it touched - the whole run's floor is not its floor.
  const narrowed = /^narrowed: (?!every screen)/m.test(run.stdout || '');
  const floor = narrowed ? undefined : FLOORS.get(name);

  // Floor bookkeeping runs BEFORE the ceiling verdict below, which can `continue`. A harness
  // that breached its ceiling is still a harness whose coverage we want recorded.
  if (floor === undefined && !known && !narrowed) unfloored.push(name);
  if (floor !== undefined && counts && counts.ran > floor) rose.push({ name, was: floor, now: counts.ran });

  // Checked before the ceiling: a harness that could not load did not report a ceiling
  // either, and blaming it for the missing number would be the same blindness twice.
  if (!ok && !counts && !HAS_NODE_MODULES && UNRESOLVED_IMPORT_RE.test(run.stderr || '')) {
    unavailable.push(name);
    // Naming the ceiling is not decoration. The ceiling rides on THIS harness's output, so
    // an unavailable harness is also an unenforced ceiling ― and a ceiling that quietly
    // stops enforcing is how a lane adds module state, sees green, and hits a wall at merge.
    // "Unmeasured" has to say WHAT went unmeasured.
    const lostCeil = CEILINGS.get(name);
    console.log(`? ${name}  [UNAVAILABLE in this tree] needs an installed package and `
      + `client2/node_modules is absent (worktrees do not get one). NOT counted as passing `
      + `― whatever it scores is simply unmeasured here. Re-run it in the main checkout `
      + `before merging this branch.`
      + (lostCeil ? `\n    ⚠ AND THE CEILING RODE ON IT: \`${lostCeil.key} <= ${lostCeil.max}\` `
          + `(${lostCeil.what}) is NOT enforced in this tree. You can add ${lostCeil.what} here `
          + `and still see a green gate; the main checkout will refuse it.` : ''));
    continue;
  }

  // ── the ceiling, if this harness carries one ──────────────────────────────────
  // Read exactly like the ASSERTIONS line: the harness counts, the runner only compares.
  const ceil = CEILINGS.get(name);
  let ceilBreach = null;
  if (ceil) {
    let measured = null;
    for (const m of (run.stdout || '').matchAll(new RegExp(`^${ceil.key} (\\d+)\\s*$`, 'gm')))
      measured = +m[1];
    if (measured === null) {
      // A ceiling whose number stopped arriving is not a pass. It is a gate that went quiet,
      // which is exactly how this directory once went 14/15 unrun.
      ceilBreach = `[BLOCKING] no \`${ceil.key} <n>\` line ― it is ceilinged at <= ${ceil.max} `
        + `(${ceil.what}) and stopped reporting. A silent ceiling is not a ceiling.`;
    } else if (measured > ceil.max) {
      ceilBreach = `[BLOCKING] ${ceil.key} ${measured}, but the ceiling is <= ${ceil.max} `
        + `(${ceil.what}). This number is meant to fall, never rise. Take the new state out, `
        + `or pass it as an argument instead of declaring it at module scope. Raising the `
        + `ceiling to go green is the same lie as lowering a floor.`;
    } else if (measured < ceil.max) {
      shrank.push({ name, was: ceil.max, now: measured, what: ceil.what });
    }
  }
  if (ceilBreach) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  ${ceilBreach}`);
    continue;
  }

  if (ok && (!counts || counts.ran === 0 || counts.failed > 0)) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] exit 0 but ${said} ― a green verdict that measured `
      + `nothing (or contradicts its own count) proves nothing`);
  } else if (floor !== undefined && counts && counts.ran < floor) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded floor is ran >= ${floor} ― it `
      + `is scoring less than it used to. If assertions were deliberately removed or a `
      + `re-pointed harness now covers less, say so and lower the floor on purpose; passing `
      + `while quietly scoring less is the failure this floor exists to make visible`);
  } else if (floor !== undefined && !counts) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but it is baselined at ran >= ${floor} ― it `
      + `used to assert and now measures nothing`);
  } else if (known && counts && counts.ran < known.ran) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded expectation is ran >= `
      + `${known.ran} ― it stopped asserting, which is death, not debt`);
  } else if (!ok && known && counts && counts.failed > known.failed) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded debt is failed <= `
      + `${known.failed} ― the debt grew; fix the regression or re-triage the entry`);
  } else if (!ok && known && counts && knownRedNameVerdict(name, known, run, counts).blocked) {
    const v = knownRedNameVerdict(name, known, run, counts);
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said} ― the COUNT is within its recorded debt but the `
      + `MEMBERS are not. ${v.message}`);
  } else if (!ok && known && !counts && known.ran > 0) {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] ${said}, but the recorded expectation is ran >= `
      + `${known.ran} ― it used to assert and now crashes before measuring anything`);
  } else if (ok && known) {
    recovered.push(name);
    console.log(`✓ ${name}  (${said}; was on the known-red list ― remove it)`);
  } else if (ok) {
    const up = (floor !== undefined && counts && counts.ran > floor) ? `; floor ${floor}, +${counts.ran - floor}` : '';
    console.log(`✓ ${name}  (${said}${up})`);
  } else if (known) {
    stillRed.push(name);
    console.log(`✗ ${name}  [known red] (${said})${beyondCount} ${known.why}`);
  } else {
    blocking.push({ name, run });
    console.log(`✗ ${name}  [BLOCKING] (${said})${beyondCount}`);
  }
}

const gated = harnesses.length - KNOWN_RED.size;
console.log(`\n${harnesses.length} harnesses ― ${gated} gated, ${KNOWN_RED.size} on the known-red `
  + `debt list (${stillRed.length} still red, ${recovered.length} recovered`
  + `${plan.notRun.some((n) => KNOWN_RED.has(n)) ? `, ${plan.notRun.filter((n) => KNOWN_RED.has(n)).length} not run` : ''})`
  + (unavailable.length > 0 ? `, ${unavailable.length} UNMEASURED in this tree` : '')
  + (unread.length > 0 ? `, ${unread.length} with NO VERDICT (output past the buffer)` : '')
  + (plan.notRun.length > 0 ? `, ${plan.notRun.length} not run (no changed file in their reach)` : '') + `.`);

if (recovered.length > 0) {
  console.log(`\n! ${recovered.length} harness(es) on the known-red list now PASS. Take them off `
    + `the list in client2/scripts/harness_floors.mjs so they start gating:\n  `
    + recovered.join('\n  ') + '\n');
}

// Rises never block ― see the FLOORS note. They are reported so the floors get refreshed
// eventually: an un-refreshed floor still catches a total collapse, but it stops catching
// the loss of everything added since it was recorded.
if (rose.length > 0) {
  console.log(`\n! ${rose.length} harness(es) now run MORE assertions than their recorded floor. `
    + `Not a failure ― raise the floors in FLOORS when convenient so the new coverage is also `
    + `protected:\n  `
    + rose.map(r => `${r.name}: floor ${r.was} -> ran ${r.now}`).join('\n  ') + '\n');
}

// The ceiling's mirror of the block above, and it must stay a note for the same reason: this
// number is meant to fall, so falling can never be a failure. It is reported because an
// un-refreshed ceiling still catches a doubling but stops catching the re-accumulation of
// everything that was cleared since it was recorded.
if (shrank.length > 0) {
  console.log(`\n! ${shrank.length} harness(es) came in UNDER their ceiling ― that is the `
    + `direction this number is supposed to move. Not a failure. Lower the ceiling in `
    + `CEILINGS when convenient so the ground gained is also held:\n  `
    + shrank.map(s => `${s.name}: ceiling ${s.was} -> ${s.now} (${s.what})`).join('\n  ') + '\n');
}

// A harness with no floor cannot have regressed (there is nothing to compare), so this is a
// note, not a failure ― making it blocking would mean adding a harness breaks the build,
// which is how people learn not to add harnesses.
if (unfloored.length > 0) {
  console.log(`\n! ${unfloored.length} harness(es) have no recorded floor and are NOT protected `
    + `against silently scoring less. Add them to FLOORS with the count they report today:\n  `
    + unfloored.join('\n  ') + '\n');
}

if (blocking.length > 0) {
  // Print each failing harness's own output. Its job is to say WHICH assertion failed and with
  // what values; re-summarising it here would lose exactly that.
  for (const b of blocking) {
    console.error(`\n──────── ${b.name} ────────`);
    process.stdout.write(b.run.stdout || '');
    process.stderr.write(b.run.stderr || '');
    if (b.run.error) console.error(String(b.run.error));
  }
  fail(`${INSTALL}${blocking.length} harness(es) that were green went red: `
     + `${blocking.map(b => b.name).join(', ')}. Fix the code, or ― if the contract is what `
     + `changed ― take it to the Lead PM. Adding it to KNOWN_RED to get a green build is how `
     + `this directory went 14/15 unrun in the first place.`);
}

// The unavailable set is stated HERE rather than only next to each harness, because this
// last line is the one people quote. "Every gated harness is green" would be a false
// summary of a run where something was never measured at all.
if (unread.length > 0) {
  console.log(`? ${unread.length} gave NO VERDICT: the runner could not read its output (${unread.join(', ')}). `
    + 'Not green and not red for those; run each alone and read its ASSERTIONS line.');
}
if (unavailable.length > 0) {
  console.log(`✓ every gated harness that COULD run in this tree is green ― but `
    + `${unavailable.length} was not measured here (${unavailable.join(', ')}). This is not a `
    + `green build for those; run the gate in the main checkout before merging. ${INSTALL}\n`);
} else if (unread.length > 0) {
  console.log(`✓ every gated harness whose verdict was read is green ― ${unread.length} gave none (above).\n`);
} else if (plan.notRun.length > 0) {
  console.log(`✓ every gated harness that ran is green ― ${plan.notRun.length} not run, no changed file in their reach (above).\n`);
} else {
  console.log(`✓ every gated harness is green.\n`);
}
