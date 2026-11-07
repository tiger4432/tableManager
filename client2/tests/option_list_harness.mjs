// OPTION LIST — the one list of options under a box (lead 11-07: the walk's node search, a cell's value suggestions and the
// formula popover draw theirs through it), scored.
//
// The subject is imported whole. What is scored:
//   L1 the rows: listbox · option, what was typed bold, the rest after it, a side word at the right
//   L2 the lit row: the one asked for, aria-selected on it alone; none asked, none lit
//   L3 ↑↓: one row on, held to the first and the last; none lit yet, the first
//   L4 a press picks its row, and the press does not take the box's focus (preventDefault)
//   L5 a new list replaces the old; cleared, no rows and none lit
//   L6 two lists on one page: moving, picking and clearing one leaves the other as it was
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { fileURLToPath } from 'node:url';
import { makeDoc, byClass } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/option_list.js';

const SRC_PATH = fileURLToPath(new URL('../src/option_list.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

const ITEMS = [{ head: 'Da', rest: 'te', side: 'Date(value)' }, { head: 'Da', rest: 'tePart', side: 'DatePart(part, value)' },
  { rest: 'Day' }];
function mount(M) {
  const doc = makeDoc('light');
  const box = doc.createElement('div');
  doc.body.appendChild(box);
  const picked = [];
  const list = new M.OptionList(box, { doc, onPick: (i) => picked.push(i) });
  return { doc, box, list, picked };
}
const rows = (box) => byClass(box, 'option-list__row');
const lit = (box) => rows(box).map((r, i) => (r.getAttribute('aria-selected') === 'true' ? i : -1)).filter((i) => i >= 0);
const texts = (box) => rows(box).map((r) => r.textContent);
const press = (row) => row.dispatch('mousedown', { preventDefault() { this.defaultPrevented = true; } });

/** The questions, asked of a (possibly mutated) module: the failures' names. */
function verdict(M) {
  const bad = [];
  const check = (name, cond) => { if (!cond) bad.push(name); };
  const a = mount(M);
  a.list.show(ITEMS, 1);
  const r = rows(a.box);
  check('L1', a.box.getAttribute('role') === 'listbox' && r.length === 3 && r.every((x) => x.getAttribute('role') === 'option')
    && byClass(r[1], 'option-list__text')[0].children[0].tagName === 'B' && byClass(r[1], 'option-list__text')[0].children[0].textContent === 'Da'
    && texts(a.box)[1] === 'DatePartDatePart(part, value)' && byClass(r[1], 'option-list__side')[0].textContent === 'DatePart(part, value)'
    && byClass(r[2], 'option-list__side').length === 0 && texts(a.box)[2] === 'Day');
  check('L2', JSON.stringify(lit(a.box)) === '[1]' && a.list.active === 1);
  const n = mount(M);
  n.list.show(ITEMS);
  check('L2', lit(n.box).length === 0 && n.list.active === -1);
  n.list.move(1);
  const first = lit(n.box)[0];
  n.list.move(-1);
  check('L3', first === 0 && JSON.stringify(lit(n.box)) === '[0]');
  a.list.move(1);
  a.list.move(1);
  check('L3', JSON.stringify(lit(a.box)) === '[2]' && a.list.active === 2);
  check('L2', lit(a.box).length === 1);
  const e = press(rows(a.box)[0]);
  check('L4', JSON.stringify(a.picked) === '[0]' && e.defaultPrevented === true);
  a.list.show(ITEMS.slice(0, 1), 0);
  check('L5', rows(a.box).length === 1 && JSON.stringify(lit(a.box)) === '[0]');
  a.list.clear();
  check('L5', rows(a.box).length === 0 && a.list.active === -1 && a.list.size === 0);
  const one = mount(M);
  const two = mount(M);
  one.list.show(ITEMS, 0);
  two.list.show(ITEMS, 0);
  one.list.move(1);
  press(rows(one.box)[2]);
  one.list.clear();
  check('L6', rows(two.box).length === 3 && JSON.stringify(lit(two.box)) === '[0]' && two.list.active === 0
    && two.picked.length === 0 && JSON.stringify(one.picked) === '[2]');
  return bad;
}

console.log('\n-- the list, as built --');
const base = verdict(BASELINE);
for (const name of ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']) ok(name, !base.includes(name), base);
if (base.length) die('the scorer already fails on the UNMUTATED module');

const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['L1', 'what was typed not bold', swap("text.appendChild(this.el('b', '', item.head));", "text.appendChild(this.el('span', '', item.head));")],
  ['L2', 'the old lit row stays lit', swap("this.rows.forEach((row, i) => { if (i !== index) lit(row, false); });", '')],
  ['L3', 'past the last row the list runs out', swap('this.light(Math.min(this.rows.length - 1, Math.max(0, this.active + step)));',
    'this.light(Math.max(0, this.active + step));')],
  ['L4', 'a press takes the focus from the box', swap("if (e && e.preventDefault) e.preventDefault(); ", '')],
  ['L5', 'a new list is drawn under the old', swap("    this.root.textContent = '';\n", '')],
  ['L6', 'the lists share their rows', (src) => swap('    this.rows = [];\n    this.active = -1;\n    if (', '    this.rows = SHARED;\n    this.active = -1;\n    if (')(src)
    .replace('export class OptionList {', 'const SHARED = [];\nexport class OptionList {')
    .replace('    this.rows = items.map(', '    this.rows.length = 0; this.rows.push(...items.map(').replace('      return row;\n    });\n', '      return row;\n    }));\n')],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\blit\b/g, 'mark')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')],
];
console.log('\n-- defect mutants (each caught by its line) --');
let caught = 0;
for (const [line, name, mutate] of DEFECTS) {
  const M = (await loadWithProbe(SRC_PATH, { mutate, tag: 'optionlist' })).module;
  let bad;
  try { bad = verdict(M); } catch (e) { bad = [line, String(e && e.message)]; }
  if (bad.includes(line)) { caught++; console.log(`  caught  ${line} ${name}`); }
  else { failed++; console.log(`  ESCAPED ${line} ${name}  saw: ${JSON.stringify(bad)}`); }
}
console.log('\n-- controls (each wakes nothing) --');
let escaped = 0;
for (const [name, mutate] of CONTROLS) {
  const bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'optionlist' })).module);
  if (!bad.length) { escaped++; console.log(`  escaped ${name}`); }
  else { failed++; console.log(`  CAUGHT  ${name}  <- wrong: ${JSON.stringify(bad)}`); }
}
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; ${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed + DEFECTS.length + CONTROLS.length} ${failed}`);
if (failed) process.exit(1);
