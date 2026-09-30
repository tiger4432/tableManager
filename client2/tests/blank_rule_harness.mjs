/**
 * The screen's one blank rule (lead a5720d9d8): `isBlank` in src/absent.js.
 *
 *   C  the contract's scalar rows answer the same (contracts/blank_predicate/vectors.json corpus and
 *      whitespace_class) - the data's blank rule is the server's, and on a scalar the screen agrees
 *   R  the rule's other lines: a list is blank when every member is ([] and [''] too), a plain object
 *      with no key is blank, 0 · false · NaN are values
 *   S  the seats that fold into it ask it, not a copy of their own (the same function)
 *
 * Run: node client2/tests/blank_rule_harness.mjs
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const ABSENT_JS = path.join(SRC, 'absent.js');
const VECTORS = JSON.parse(readFileSync(path.join(HERE, '..', '..', 'contracts', 'blank_predicate', 'vectors.json'), 'utf8'));
const CASES = VECTORS.corpus.cases;
const SPACE_CLASS = VECTORS.whitespace_class.codepoints;
// U+FEFF: JS trim drops it, the server's strip keeps it.
const BOM = 65279;

const valueOf = (input) => (input.type === 'null' ? null
  : input.type === 'text' ? String.fromCodePoint(...input.cp) : input.value);

let ran = 0;
let failedList = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failedList.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

function suite(isBlank) {
  console.log('\n-- C. the contract\'s scalar rows --');
  const wrong = CASES.filter((c) => isBlank(valueOf(c.input)) !== c.blank).map((c) => c.id);
  ok('C1 every corpus row answers as the contract says (else the screen and the data disagree on a scalar)',
    CASES.length > 0 && wrong.length === 0, `${CASES.length} rows, wrong: ${wrong.join(',')}`);
  const spaces = SPACE_CLASS.filter((cp) => !isBlank(String.fromCodePoint(cp)));
  ok('C2 each of the server\'s whitespace codepoints alone is blank, and U+FEFF alone is a value',
    SPACE_CLASS.length > 0 && spaces.length === 0 && isBlank(String.fromCodePoint(BOM)) === false,
    `${SPACE_CLASS.length} codepoints, not blank: ${spaces.join(',')}, U+FEFF blank: ${isBlank(String.fromCodePoint(BOM))}`);

  console.log('\n-- R. the rule beyond scalars --');
  const LINES = [[[], true], [[''], true], [[' ', null], true], [['x'], false], [['', 'x'], false],
    [{}, true], [{ a: 1 }, false], [0, false], [false, false], [NaN, false], [new Date(0), false]];
  eq('R1 a list is blank when every member is, a plain object with no key is blank, 0 false NaN and a Date are values',
    LINES.map(([v]) => isBlank(v)).join('|'), LINES.map(([, want]) => want).join('|'));
  return { ran, failed: failedList.slice() };
}

// The probe hands `mutate` the source with LF newlines already.
const load = async (mutate) => (await loadWithProbe(ABSENT_JS, mutate ? { mutate } : {})).module;

const main = async () => {
  console.log('== baseline ==');
  const absent = await import('../src/absent.js');
  const base = suite(absent.isBlank);
  console.log('\n-- S. the seats that fold into it --');
  // The probe copy imports ../absent.js from the real file, so the rule is the very same function object.
  const seat = async (rel) => (await loadWithProbe(path.join(SRC, rel), { expose: ['isBlank'] })).probe.isBlank;
  const skeleton = await seat('ontology_skeleton.js');
  const excel = await seat(path.join('map2', 'excel_io.js'));
  ok('S1 ontology_skeleton and map2/excel_io ask the one rule (the same function, not a copy)',
    skeleton === absent.isBlank && excel === absent.isBlank, `skeleton ${skeleton === absent.isBlank}, excel_io ${excel === absent.isBlank}`);
  base.ran = ran;
  base.failed = failedList.slice();
  const BASE_NAMES = NAMES.filter((n) => !n.startsWith('S1'));
  console.log(`\n${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
  const baseRan = ran;
  const MUTANTS = [
    { name: 'js-trim-for-the-server-space', catches: ['C1', 'C2'],
      from: "return [...value].every((ch) => SPACE.has(ch.codePointAt(0)));", to: "return value.trim() === '';" },
    { name: 'a-list-of-blanks-holds-something', catches: ['R1'],
      from: 'if (Array.isArray(value)) return value.every(isBlank);', to: 'if (Array.isArray(value)) return value.length === 0;' },
    { name: 'an-empty-object-is-a-value', catches: ['R1'],
      from: '    return Object.keys(value).length === 0;', to: '    return false;' },
    { name: 'zero-is-blank', catches: ['R1'],
      from: '  return false;\n}\n\n/** ', to: '  return !value;\n}\n\n/** ' },
  ];
  const { wrong } = await scoreMutants(MUTANTS, async (m) => {
    const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
    let mod;
    try { mod = await load(swap); } catch (err) { console.error(`HARNESS FAILURE: ${err.message}`); process.exit(2); }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { suite(mod.isBlank); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: baseRan - 1, baselineNames: BASE_NAMES,
       title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
  console.log(`\nASSERTIONS ${baseRan} ${base.failed.length}`);
  process.exit(wrong ? 1 : 0);
};

main();
