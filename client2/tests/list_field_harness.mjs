// LIST FIELD - the base layer's box that takes a list (lead 11-11): how it reads a list, what it says, and the box itself.
// Run: node client2/tests/list_field_harness.mjs
//
//   L1 a list: lines, commas and tabs; trimmed, empty dropped, each once; a number column's numbers as numbers
//   L2 its count line: «1 value» / «N values», the repeats dropped said; none, nothing
//   B1 the box opens on its values one a line, and says how many; set again, no change told
//   B2 typed: the values read, the count and the repeats said, the caller told the values
//   B3 a caller's words for the count (the grid filter's «equals any»); its rows
//   B4 set to none: empty, «0 values», the caller not told
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, byClass } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'list_field.js');
const setInput = (el, v) => { el.value = v; el.dispatch('input'); };

async function suite(m) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };

  eq('L1 a list: lines, commas and tabs; trimmed, empty dropped, each once; a number column\'s numbers as numbers',
    [m.listValues('a\nb, a\tc\r\n\n'), m.listValues('1, 2.5, x', 'number'), m.listValues(null), m.listValues('L1,L2,L1,L1')],
    [{ values: ['a', 'b', 'c'], duplicates: 1 }, { values: [1, 2.5, 'x'], duplicates: 0 }, { values: [], duplicates: 0 },
      { values: ['L1', 'L2'], duplicates: 2 }]);
  eq('L2 the count line: one value, many, the repeats dropped said; none',
    [m.listCountWords(['a'], 0), m.listCountWords(['a', 'b'], 1), m.listCountWords([], 2), m.listCountWords(Array(1200).fill('x'), 0)],
    [['1 value', ''], ['2 values', '1 duplicate removed'], ['0 values', '2 duplicates removed'], ['1,200 values', '']]);

  const doc = makeDoc('light');
  const mount = doc.createElement('div');
  const told = [];
  const f = new m.ListField(mount, { doc, values: ['L1', 'L2'], onChange: (values) => told.push(values) });
  const box = byClass(mount, 'list-field__box')[0];
  const count = byClass(mount, 'list-field__count')[0];
  const line = byClass(mount, 'list-field__line')[0];
  eq('B1 the box opens on its values one a line, says how many; told nothing; its class and rows',
    [box && box.value, count && count.textContent, told.length, mount.classList.contains('list-field'), box && box.rows],
    ['L1\nL2', '2 values', 0, true, 5]);
  setInput(box, 'L3\nL4, L3\tL5');
  eq('B2 typed: the values read, the count and the repeats said, the caller told them',
    [f.values(), count.textContent, line.children[1].textContent, told], [['L3', 'L4', 'L5'], '3 values', '1 duplicate removed', [['L3', 'L4', 'L5']]]);
  f.setValues([]);
  eq('B4 set to none: empty, «0 values», the caller not told', [box.value, count.textContent, line.children[1].textContent, told.length], ['', '0 values', '', 1]);
  const m2 = doc.createElement('div');
  const g = new m.ListField(m2, { doc, kind: 'number', rows: 9, say: (n) => `${n} · equals any` });
  setInput(byClass(m2, 'list-field__box')[0], '3\n4');
  eq('B3 a caller\'s words for the count; its rows; a number field\'s values as numbers',
    [byClass(m2, 'list-field__count')[0].textContent, byClass(m2, 'list-field__box')[0].rows, g.values()], ['2 values · equals any', 9, [3, 4]]);
  return { ran: ran.length, names: ran, failures };
}

const real = await import('../src/list_field.js');
const base = await suite(real);
console.log('-- list field -------------------------------------------------------');
for (const name of base.names) console.log(`  ${base.failures.some((f) => f.startsWith(name + ':')) ? 'FAIL' : 'PASS'} ${name}`);
base.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { id: 'LM1', what: 'a list not made unique', catches: ['L1'], mutate: swap('if (seen.has(word)) { duplicates += 1; continue; }', '') },
  { id: 'LM2', what: 'commas not read as a break', catches: ['L1'], mutate: swap('.split(/[\\r\\n\\t,]+/)', '.split(/[\\r\\n\\t]+/)') },
  { id: 'LM3', what: 'one value said «1 values»', catches: ['L2'], mutate: swap("value${values.length === 1 ? '' : 's'}", 'values') },
  { id: 'LM4', what: 'the caller not told what was typed', catches: ['B2'], mutate: swap(' this.onChange(this.values()); ', ' ') },
  { id: 'LM5', what: 'its values opened on one line', catches: ['B1'], mutate: swap(".map(String).join('\\n')", ".map(String).join(',')") },
  { id: 'LM6', what: 'the caller\'s words for the count dropped', catches: ['B3'], mutate: swap('this.count.textContent = this.say(count);', 'this.count.textContent = count;') },
];
console.log('');
const { wrong } = await scoreMutants(MUTANTS, async (mu) => suite((await loadWithProbe(SUBJECT, { mutate: mu.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '-- defect mutants (each must be CAUGHT by its named line) -----------' });
const failed = base.failures.length + wrong;
console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed; ${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
