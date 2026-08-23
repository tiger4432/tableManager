/**
 * rnd_board — 마킹 «교집합» 채점 (공사7)
 *
 * WHAT THIS SCORES, in the Lead PM's words:
 *   A  marking:1 ∩ marking:2 -> marking:3, and the SIGN is part of the agreement
 *   B  the names are ARGUMENTS -- a third, fourth, fifth marking costs zero lines
 *   C  the sources are read, never written
 *   D  it can be taken down (a shell that reseats must not leak a subscription)
 *
 * 🔴 THE SIGN RULE IS THE POINT. Two names holding one node with OPPOSITE signs is a
 *    contradiction, not a hit: 「여기서 났다」 and 「봤는데 안 났다」 are different sentences and
 *    folding them would make the contrast lie. A3/A4 score that it stays out AND stays
 *    countable, because a contradiction that is silently dropped is indistinguishable from
 *    a node nobody marked.
 *
 * 🔴 EVERY ASSERTION IS WOKEN BY A MUTANT, and a mutation whose anchor has rotted STOPS the
 *    run instead of reading as a pass (this repo shipped that disguise twice).
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BOARD_DIR = path.join(HERE, '..', 'src', 'rnd_board');
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

async function loadModules(mutate = {}) {
  const read = (file) => {
    const text = readFileSync(path.join(BOARD_DIR, file), 'utf8');
    const fn = mutate[file];
    const out = fn ? fn(text) : text;
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    return out;
  };
  const storeUrl = dataUrl(read('marking_store.js'));
  const interUrl = dataUrl(read('marking_intersection.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const store = await import(storeUrl);
  const inter = await import(interUrl);
  return { store, inter };
}

async function suite(mods) {
  const { store: S, inter } = mods;
  const { MarkingStore, SIGN } = S;
  const { intersectMarkings } = inter;
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const ok = (name, cond, detail) => {
    ran.push(name);
    if (!cond) failures.push(detail ? `${name}: ${detail}` : name);
  };

  // ── A. THE INTERSECTION, SIGN INCLUDED ───────────────────────────────────────
  {
    const s = new MarkingStore();
    s.set('marking:1', 'both-case', SIGN.CASE);
    s.set('marking:2', 'both-case', SIGN.CASE);
    s.set('marking:1', 'only-one', SIGN.CASE);
    s.set('marking:1', 'disputed', SIGN.CASE);
    s.set('marking:2', 'disputed', SIGN.CONTROL);
    s.set('marking:1', 'both-control', SIGN.CONTROL);
    s.set('marking:2', 'both-control', SIGN.CONTROL);
    const join = intersectMarkings(s, { sources: ['marking:1', 'marking:2'], target: 'marking:3' });

    eq('A1 a node both names hold with the same sign enters, with that sign',
      s.signOf('marking:3', 'both-case'), SIGN.CASE);
    eq('A2 a node only one name holds does not enter',
      s.signOf('marking:3', 'only-one'), SIGN.ABSENT);
    // 🔴 THE RULING: opposite signs are a CONTRADICTION, not an intersection.
    eq('A3 a node the two names disagree about does not enter',
      s.signOf('marking:3', 'disputed'), SIGN.ABSENT);
    eq('A4 ... and it is countable, not silently dropped', join.conflicts(), ['disputed']);
    eq('A5 the control sign intersects too, and stays control',
      s.signOf('marking:3', 'both-control'), SIGN.CONTROL);
    eq('A6 the target holds exactly the agreements', s.count('marking:3'), 2);

    // It is LIVE: a later write moves the target with nobody calling refresh.
    s.set('marking:2', 'only-one', SIGN.CASE);
    eq('A7 a later agreement arrives on its own', s.signOf('marking:3', 'only-one'), SIGN.CASE);
    s.set('marking:1', 'both-case', SIGN.ABSENT);
    eq('A8 a node that leaves one source leaves the target',
      s.signOf('marking:3', 'both-case'), SIGN.ABSENT);
    // A part subscribed to the derived name is what makes this worth having.
    let heard = 0;
    s.subscribe('marking:3', () => { heard += 1; });
    s.set('marking:2', 'late', SIGN.CASE);
    eq('A9 a source write that changes nothing does not wake the target', heard, 0);
    s.set('marking:1', 'late', SIGN.CASE);
    ok('A10 a subscriber on the derived name hears the change', heard > 0, `heard ${heard}`);
    join.stop();
  }

  // ── B. THE NAMES ARE DATA ────────────────────────────────────────────────────
  {
    const s = new MarkingStore();
    // Names this file has never seen, and three of them: no branch above knows these exist.
    s.set('ctx:alpha', 'n1', SIGN.CASE);
    s.set('ctx:beta', 'n1', SIGN.CASE);
    s.set('ctx:gamma', 'n1', SIGN.CASE);
    s.set('ctx:alpha', 'n2', SIGN.CASE);
    s.set('ctx:beta', 'n2', SIGN.CASE);
    const join = intersectMarkings(s,
      { sources: ['ctx:alpha', 'ctx:beta', 'ctx:gamma'], target: 'ctx:all' });
    eq('B1 an unseen pair of names works with no code change',
      s.signOf('ctx:all', 'n1'), SIGN.CASE);
    eq('B2 three sources means all three, not any two',
      s.signOf('ctx:all', 'n2'), SIGN.ABSENT);
    eq('B3 the derived name holds only the full agreement', s.count('ctx:all'), 1);
    join.stop();
  }

  // ── C. THE SOURCES ARE READ, NEVER WRITTEN ───────────────────────────────────
  {
    const s = new MarkingStore();
    s.set('m:a', 'x', SIGN.CASE);
    s.set('m:b', 'x', SIGN.CASE);
    s.set('m:b', 'y', SIGN.CONTROL);
    const join = intersectMarkings(s, { sources: ['m:a', 'm:b'], target: 'm:out' });
    eq('C1 the first source is untouched', s.entries('m:a').length, 1);
    eq('C2 the second source is untouched', s.entries('m:b').length, 2);
    join.stop();
  }

  // ── D. IT CAN BE TAKEN DOWN ──────────────────────────────────────────────────
  {
    const s = new MarkingStore();
    s.set('d:1', 'n', SIGN.CASE);
    const join = intersectMarkings(s, { sources: ['d:1', 'd:2'], target: 'd:out' });
    join.stop();
    s.set('d:2', 'n', SIGN.CASE);
    eq('D1 a stopped intersection stops following', s.signOf('d:out', 'n'), SIGN.ABSENT);
    join.refresh();
    eq('D2 ... and refresh still works by hand', s.signOf('d:out', 'n'), SIGN.CASE);
  }

  // ── E. IT REFUSES A SPEC IT CANNOT HONOUR ────────────────────────────────────
  {
    const s = new MarkingStore();
    let threw = false;
    try { intersectMarkings(s, { sources: ['one'], target: 'out' }); } catch (e) { threw = true; }
    ok('E1 one source is not an intersection and says so', threw);
  }

  return { ran, failures };
}

const MUTANTS = [
  { id: 'M1', what: 'the intersection is computed as a UNION (a missing name counts as agreement)',
    catches: 'A2',
    mutate: { 'marking_intersection.js': (s) => s.replace(
      'if (otherSign === SIGN.ABSENT) { agreed = false; break; }',
      'if (otherSign === SIGN.ABSENT) { continue; }') } },
  { id: 'M2', what: 'the sign is ignored, so a contradiction is counted as a hit',
    catches: 'A3',
    mutate: { 'marking_intersection.js': (s) => s.replace(
      'if (otherSign !== sign) { agreed = false; contradicted = true; break; }',
      'if (otherSign !== sign) { contradicted = true; }') } },
  { id: 'M3', what: 'the names are hardcoded instead of taken from the spec',
    catches: 'B1',
    mutate: { 'marking_intersection.js': (s) => s.replace(
      'const [first, ...rest] = sources;',
      "const [first, ...rest] = ['marking:1', 'marking:2'];") } },
  { id: 'M4', what: 'a node that leaves a source is left behind in the target',
    catches: 'A8',
    mutate: { 'marking_intersection.js': (s) => s.replace(
      'if (wanted.get(nodeId) !== sign) store.set(target, nodeId, SIGN.ABSENT);',
      'if (false) store.set(target, nodeId, SIGN.ABSENT);') } },
  { id: 'M5', what: 'contradictions are dropped instead of counted',
    catches: 'A4',
    mutate: { 'marking_intersection.js': (s) => s.replace(
      'conflicts = disagreed;', 'conflicts = [];') } },
  { id: 'M6', what: 'it computes once and never subscribes',
    catches: 'A7',
    mutate: { 'marking_intersection.js': (s) => s.replace(
      'const unsubscribes = sources.map((name) => store.subscribe(name, refresh));',
      'const unsubscribes = sources.map(() => () => {});') } },
];

const result = await suite(await loadModules());
console.log('-- rnd_board marking intersection -----------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

let escaped = 0;
console.log('\n-- defect mutants (each must be CAUGHT by its named line) -----------');
for (const m of MUTANTS) {
  let out;
  try {
    out = await suite(await loadModules(m.mutate));
  } catch (e) {
    escaped += 1;
    console.log(`  INERT   ${m.id} ${m.what}  -- ${String(e.message).slice(0, 60)}`);
    continue;
  }
  const hit = out.failures.some((f) => f.startsWith(m.catches));
  if (hit) console.log(`  caught  ${m.id} ${m.what}  (${m.catches})`);
  else { escaped += 1; console.log(`  ESCAPED ${m.id} ${m.what}  -- ${m.catches} stayed green`); }
}

const total = result.ran.length + MUTANTS.length;
const failed = result.failures.length + escaped;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; ` +
  `${MUTANTS.length - escaped}/${MUTANTS.length} defects caught, ${escaped} escaped.`);
console.log(`ASSERTIONS ${total} ${failed}`);
if (failed) process.exitCode = 1;
