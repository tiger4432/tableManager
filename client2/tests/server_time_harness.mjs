/**
 * 서버 시각 — 같은 순간의 «두 철자»가 같은 글자로 그려진다.
 *
 *   node client2/tests/server_time_harness.mjs
 *
 * WHY (C-77 / S-182 ⓐ, 판정 289). The server now sends offset-bearing ISO. Three screens were
 * SLICING that string, and a slice drops the offset — UTC digits then print as if they were
 * local, nine hours out for a KST operator, with nothing raised. One of those sites carried a
 * comment saying 「타임존 재해석 없음」, which was TRUE while the server sent naive strings and
 * became false the day it stopped.
 *
 * 🔴 EVERY ASSERTION HERE IS ZONE-INDEPENDENT. Pinning a literal wall clock would make this file
 *    pass or fail by the runner's TZ rather than by the code — the measuring stick would carry
 *    the answer. So what is asserted is that two spellings of ONE instant agree, and that two
 *    DIFFERENT instants disagree.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'server_time.js');
const LF = String.fromCharCode(10);

// 🔴 THE SHAPE THE ROUTE ACTUALLY SENDS, measured 2026-09-11 on
//    `/tables/dt_job_attribution/data`: a SPACE separator and a `+00:00` offset.
const SERVED = '2026-08-01 15:28:47+00:00';
const SAME_Z = '2026-08-01T15:28:47Z';
const SAME_T = '2026-08-01T15:28:47+00:00';
// The same wall clock in a different zone is a DIFFERENT instant — nine hours earlier.
const OTHER = '2026-08-01T15:28:47+09:00';

let ran = 0;
const NAMES = [];
let failures = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failures.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

function suite(mod) {
  const { parseServerInstant, localStamp, localMinute, localShort, NO_TIME } = mod;
  // 🔴 A PARSE THAT RETURNED NOTHING MUST BE SCORED, NOT THROWN ON. Reading `.getTime()`
  //    straight off the result killed the run under M2 (INERT) and the remaining assertions
  //    went unmeasured -- a mutant that throws is a hole, not a catch.
  const ms = (v) => { const at = parseServerInstant(v); return at ? at.getTime() : NaN; };

  console.log(`${LF}-- one instant, three spellings, one rendering --`);
  eq('T1 the served form and ...Z render the same', localStamp(SERVED), localStamp(SAME_Z));
  eq('T2 the served form and ...+00:00 render the same', localStamp(SERVED), localStamp(SAME_T));
  eq('T3 the minute form agrees too', localMinute(SERVED), localMinute(SAME_Z));
  eq('T4 the short form agrees too', localShort(SERVED), localShort(SAME_Z));
  // 🔴 AND THE PARSE IS THE SAME INSTANT, not merely the same text.
  eq('T5 ...because they parse to one instant', ms(SERVED), ms(SAME_Z));

  console.log(`${LF}-- the offset is READ, not dropped --`);
  // 🔴 THE DISCRIMINANT. If the offset were stripped, these two would render identically,
  //    and every assertion above would still pass. This is the one that fails when it is.
  ok('O1 the same wall clock in another zone is a DIFFERENT instant',
    localStamp(SERVED) !== localStamp(OTHER), `${localStamp(SERVED)} vs ${localStamp(OTHER)}`);
  eq('O2 ...by exactly nine hours', (ms(SERVED) - ms(OTHER)) / 3600000, 9);

  console.log(`${LF}-- the space separator is normalised, because only T is guaranteed --`);
  ok('N1 the served space form parses at all', parseServerInstant(SERVED) !== null);
  eq('N2 ...to the same instant as its T twin', ms(SERVED), ms(SAME_T));

  console.log(`${LF}-- absence is not a rendering --`);
  eq('A1 null has no time', localStamp(null), NO_TIME);
  eq('A2 an empty string has no time', localStamp(''), NO_TIME);
  eq('A3 unparseable text has no time', localStamp('not a date'), NO_TIME);
  eq('A4 ...and the parse says so rather than inventing an epoch',
    parseServerInstant('not a date'), null);
  // 🔴 「Invalid Date」 IS A STRING THAT REACHES THE SCREEN. That is the defect class this
  //    guard exists for, and it is why the parse returns null instead of a bad Date.
  ok('A5 no rendering ever contains the words Invalid Date',
    ![localStamp('x'), localMinute('x'), localShort('x')].some((s) => s.includes('Invalid')));
}

const first = await loadWithProbe(SRC, {});
suite(first.module);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${ran} assertions, `
  + `${failures.length} failure(s)`);
failures.forEach((f) => console.log(`   x ${f}`));
const base = { ran, names: NAMES.slice(), failed: failures.length };

const MUTANTS = [
  // 🔴 THE DEFECT THIS ROUND FIXED, put back: drop the offset before parsing. Every same-instant
  //    assertion stays green under it — only the zone discriminant goes red.
  { id: 'M1', what: 'the offset is stripped before parsing',
    catches: 'O1 the same wall clock in another zone',
    from: '  const normalised = text.replace(/^(\\d{4}-\\d{2}-\\d{2}) /, \'$1T\');',
    to: '  const normalised = text.replace(/^(\\d{4}-\\d{2}-\\d{2}) /, \'$1T\')'
      + '.replace(/(Z|[+-]\\d{2}:?\\d{2})$/, \'\');' },
  // 🔴 THIS SLOT HELD AN EQUIVALENT MUTANT AND THE HARNESS SAID SO. It was 「leave the space
  //    for the engine to guess」 -- and V8 guesses right, so nothing here could tell the two
  //    apart. The space-to-T normalisation defends engines this runner cannot run (the spec
  //    guarantees only the T form), so it is UNFALSIFIABLE in node and is named as such rather
  //    than covered by a weaker assertion. Re-anchored to the property that DOES survive an
  //    engine change: whatever the normalisation produces must still parse.
  { id: 'M2', what: 'the normalisation eats the separator instead of replacing it',
    catches: 'N1 the served space form parses at all',
    from: '  const normalised = text.replace(/^(\\d{4}-\\d{2}-\\d{2}) /, \'$1T\');',
    to: '  const normalised = text.replace(/^(\\d{4}-\\d{2}-\\d{2}) /, \'$1\');' },
  { id: 'M3', what: 'an unparseable string becomes an epoch instead of nothing',
    catches: 'A4 ...and the parse says so',
    from: '  return Number.isNaN(at.getTime()) ? null : at;',
    to: '  return Number.isNaN(at.getTime()) ? new Date(0) : at;' },
  { id: 'M4', what: 'a naive string is given a Z the server never sent',
    catches: 'O2 ...by exactly nine hours',
    from: '  const at = new Date(normalised);',
    to: '  const at = new Date(/[Z+]/.test(normalised) ? normalised.replace(/[+-]\\d{2}:?\\d{2}$/, \'Z\') : normalised);' },
  { id: 'M5', what: 'CONTROL: a comment line is removed', control: true,
    from: '/** 「그릴 것이 없다」 — 이 파일이 짓는 유일한 글자. 값이 아니다. */',
    to: '/** */' },
];

const runMutant = async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(SRC, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  suite(loaded.module);
  return { ran, names: NAMES.slice(), failures: failures.slice() };
};

const defects = await scoreMutants(MUTANTS.filter((m) => !m.control), runMutant,
  { baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== defect mutants (each must be CAUGHT by the check it names) ==` });
const controls = await scoreMutants(MUTANTS.filter((m) => m.control), runMutant,
  { mustCatch: false, baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== controls (each must wake NOTHING) ==` });

const scored = MUTANTS.length - defects.wrong - controls.wrong;
console.log(`${LF}  ${scored}/${MUTANTS.length} scored as intended.`);
const failed = base.failed + (MUTANTS.length - scored);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
