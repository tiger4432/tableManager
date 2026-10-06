/**
 * skeleton_value_fit -- a value the skeleton's node cannot hold is SHOWN, never drawn as an
 * empty box, and no control is offered over it.
 *
 * WHY THIS EXISTS. Owner 09-22: 「선언 불러오면 join 같은 신규 선언 제대로 반영이 안되는듯」,
 * 09-24: 「며칠째 안되는거니? … 당장 고쳐 1순위」. The chain window opened a unified rule with its
 * pair list, column list and booleans as EMPTY text boxes: the leaf control showed only strings
 * and numbers, an index map showed only arrays, and everything else vanished. The Lead counted
 * 9 such cells on the box's own rules. Typing into one of those boxes would have written a string
 * over the list it was hiding.
 *
 * WHAT IT SCORES (the form, through the module that draws it):
 *   U  a leaf holding a list / record / wrong scalar shows the value and offers no control
 *   M  an index map or a record holding the wrong shape shows the value -- no empty `+` door
 *   N  ⛔ NOT INFERRED: a list at a leaf is not drawn as a list. The skeleton says what a cell
 *      is; the value is only checked against it
 *   K  what already fit is drawn exactly as before (input, checkbox, members + door)
 *   W  a word in a list of WORDS is that list's one member: a box holding it, its `-`, the door
 *   R  read mode spells a list and a record as their JSON, not `a,b` / `[object Object]`
 *   P  the real chain panel with the SHIPPED skeleton: no cell that holds a value is drawn
 *      blank. It says nothing about which shape the server declares, so it holds before and
 *      after the skeleton learns lists -- that half is the application lane's
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc, makeNode, walk } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VIEW = path.join(HERE, '..', 'src', 'ontology_explorer_view.js');
const SKELETON = JSON.parse(readFileSync(
  path.join(HERE, '..', '..', 'server', 'chain_skeleton.json'), 'utf8'));

const doc = makeDoc('light');
// The form builds with the GLOBAL document (`h` in the view); the panel builds with `deps.doc`.
globalThis.document = doc;

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

// A skeleton whose names exist nowhere in the product: the form must be reading the node.
const LEAF = { kind: 'leaf', hint: 'free' };
const LIST = { kind: 'map', keyed_by: 'index', member: 'item', of: LEAF };
// The owner's `"on": "lot_event"` sits in a list of PAIRS -- a word there is still a misfit.
const PAIRS = { kind: 'map', keyed_by: 'index', member: 'pair',
  of: { kind: 'record', fields: [{ key: 'x', node: LEAF }] } };
const FIXTURE = {
  kind: 'record',
  fields: [
    { key: 'decoy_text', node: LEAF },
    { key: 'decoy_flag', node: { kind: 'leaf', hint: 'flag' } },
    { key: 'decoy_pick', node: { kind: 'leaf', hint: 'choice', list: 'decoys' } },
    { key: 'decoy_list', node: PAIRS },
    { key: 'decoy_rec', node: { kind: 'record', fields: [{ key: 'x', node: LEAF }] } },
    { key: 'fit_text', node: LEAF },
    { key: 'fit_flag', node: { kind: 'leaf', hint: 'flag' } },
    { key: 'fit_list', node: LIST },
    { key: 'word_list', node: LIST },
    { key: 'three_list', node: LIST },
    { key: 'empty_list', node: LIST },
  ],
};
const HELD = {
  decoy_text: ['a', 'b'],
  decoy_flag: 'yes',
  decoy_pick: { k: 1 },
  decoy_list: 'lot_event',
  decoy_rec: 'zzz',
  fit_text: 'ok',
  fit_flag: true,
  fit_list: ['p', 'q'],
  word_list: 'Lot',
  three_list: ['a', 'b', 'c'],
  empty_list: [],
};
const UNFIT = ['decoy_text', 'decoy_flag', 'decoy_pick', 'decoy_list', 'decoy_rec'];

// The contract `raw_registry_panel.formContext` meets: a screen with no plan, so every leaf
// goes to the control the skeleton draws.
const context = (readOnly) => ({
  schema: { decoys: ['one', 'two'] }, readOnly, planRow: () => null, planLoaded: true,
  plannedMembers: () => [], covering: () => null, deref: (node) => node, declared: () => [],
  heldChoice: () => '', rolesNear: () => [], usedElsewhere: () => [], renderRow: () => null,
  suggest: (row) => row, hot: [], expanded: {}, absolute: (at) => at,
});

const cls = (n) => String(n.className || '').split(/\s+/);
const boxAt = (root, at) => walk(root).find(
  (n) => cls(n).includes('oe-node') && n.attrs && n.attrs['data-path'] === at);
const controlsIn = (box) => walk(box).filter(
  (n) => n.tagName === 'INPUT' || n.tagName === 'SELECT' || n.tagName === 'TEXTAREA');
const shownIn = (box) => {
  const span = walk(box).find((n) => cls(n).includes('oe-value'));
  return span ? String(span.textContent) : null;
};
const doorsIn = (box) => walk(box).filter((n) => cls(n).includes('oe-form-add'));
const nestedIn = (box) => walk(box).slice(1).filter((n) => cls(n).includes('oe-node'));

function suite(M) {
  const before = { pass, fail };
  const form = M.renderSkeletonForm(context(false), FIXTURE, '', HELD, 0, 'decoy');
  const at = (p) => boxAt(form, p) || makeNode(doc, 'div');

  // U -- a leaf that cannot hold its value shows it and offers nothing to type into
  ok(controlsIn(at('decoy_text')).length === 0 && shownIn(at('decoy_text')) === '["a","b"]',
    `U1 a list at a text leaf is shown as its JSON, with no text box [${shownIn(at('decoy_text'))}]`);
  ok(controlsIn(at('decoy_flag')).length === 0 && shownIn(at('decoy_flag')) === 'yes',
    `U2 a string at a flag leaf is shown, with no checkbox [${shownIn(at('decoy_flag'))}]`);
  ok(controlsIn(at('decoy_pick')).length === 0 && shownIn(at('decoy_pick')) === '{"k":1}',
    `U3 a record at a choice leaf is shown, with no dropdown [${shownIn(at('decoy_pick'))}]`);
  ok(walk(at('decoy_text')).some((n) => n.attrs && n.attrs['data-unfit'] === 'true'),
    'U4 the shown value is marked as one the form could not hold');

  // M -- a branch holding the wrong shape shows the value instead of an empty branch
  ok(shownIn(at('decoy_list')) === 'lot_event' && doorsIn(at('decoy_list')).length === 0,
    `M1 a string where the skeleton says list of records is shown, and no "+ pair" door hides it `
    + `[${shownIn(at('decoy_list'))}, doors=${doorsIn(at('decoy_list')).length}]`);
  ok(shownIn(at('decoy_rec')) === 'zzz' && nestedIn(at('decoy_rec')).length === 0,
    `M2 a string where the skeleton says record is shown, and no empty fields are drawn over it`);

  // N -- the value never decides what the cell is
  ok(doorsIn(at('decoy_text')).length === 0 && nestedIn(at('decoy_text')).length === 0,
    'N1 a list at a LEAF is not drawn as a list: no members, no door');

  // K -- what fit is unchanged
  const fitInput = controlsIn(at('fit_text'))[0];
  ok(fitInput && fitInput.value === 'ok', `K1 a string at a text leaf is still a text box holding it`);
  const fitFlag = controlsIn(at('fit_flag'))[0];
  ok(fitFlag && fitFlag.type === 'checkbox' && fitFlag.checked === true,
    'K2 a boolean at a flag leaf is still a ticked checkbox');
  ok(boxAt(form, 'fit_list[0]') && boxAt(form, 'fit_list[1]') && doorsIn(at('fit_list')).length === 1,
    'K3 a list at a list node still draws its members and its "+ item" door');

  // '' is absence, not a wrong shape: it must not become a blank span where a control belongs
  const blankHeld = { fit_flag: '', fit_list: '' };
  const blankForm = M.renderSkeletonForm(context(false), FIXTURE, '', blankHeld, 0, 'decoy');
  const blankFlag = controlsIn(boxAt(blankForm, 'fit_flag') || makeNode(doc, 'div'))[0];
  ok(blankFlag && blankFlag.type === 'checkbox' && blankFlag.checked === false
     && doorsIn(boxAt(blankForm, 'fit_list') || makeNode(doc, 'div')).length === 1,
    "K4 '' at a flag is an unticked box and '' at a list is its empty door -- absence, not a misfit");

  // W -- one word in a list of words is that list's one member (owner: 「선언창도 다 지원하게해」)
  const removesIn = (box) => walk(box).filter((n) => cls(n).includes('oe-form-remove'));
  const inputAt = (p) => controlsIn(boxAt(form, p) || makeNode(doc, 'div'))[0];
  ok(inputAt('word_list[0]') && inputAt('word_list[0]').value === 'Lot'
     && !boxAt(form, 'word_list[1]') && removesIn(at('word_list')).length === 1
     && doorsIn(at('word_list')).length === 1,
    `W1 a word at a list of words draws ONE member holding the word, its "-" and the "+" door `
    + `[${inputAt('word_list[0]') && inputAt('word_list[0]').value}]`);
  ok(['a', 'b', 'c'].every((word, i) => inputAt(`three_list[${i}]`)
       && inputAt(`three_list[${i}]`).value === word)
     && !boxAt(form, 'three_list[3]') && removesIn(at('three_list')).length === 3,
    'W2 a list of three draws three members, each holding its own word');
  ok(!boxAt(form, 'empty_list[0]') && controlsIn(at('empty_list')).length === 0
     && doorsIn(at('empty_list')).length === 1,
    'W3 an empty list draws no member and no box -- only its "+" door');

  // every unfit path together: nothing typeable over a value the form cannot hold
  const typeable = UNFIT.flatMap((p) => controlsIn(at(p)));
  ok(typeable.length === 0, `U5 no control is offered over any of the ${UNFIT.length} unfit values`);

  // R -- read mode spells what it shows
  const read = M.renderSkeletonForm(context(true), FIXTURE, '', HELD, 0, 'decoy');
  const rAt = (p) => boxAt(read, p) || makeNode(doc, 'div');
  ok(shownIn(rAt('decoy_text')) === '["a","b"]',
    `R1 read mode spells a list as JSON, not a,b [${shownIn(rAt('decoy_text'))}]`);
  ok(shownIn(rAt('decoy_pick')) === '{"k":1}',
    `R2 read mode spells a record as JSON, not [object Object] [${shownIn(rAt('decoy_pick'))}]`);
  ok(shownIn(rAt('decoy_list')) === 'lot_event',
    'R3 read mode shows a string held where the skeleton says list of records');
  ok(shownIn(rAt('word_list[0]')) === 'Lot' && !boxAt(read, 'word_list[1]'),
    `R4 read mode shows a word in a list of words as its one member [${shownIn(rAt('word_list[0]'))}]`);

  // V -- a oneOf picked by the value's shape (lead 068c904a6 ②): the picker says the branch the
  //      value's shape is in, and that branch is drawn at the cell's OWN path -- no branch key.
  const SHAPED = { kind: 'record', fields: [{ key: 'typ', node: { kind: 'oneOf', hint: 'choice', pick: 'shape',
    branches: { word: LEAF, from_col: { kind: 'record', fields: [{ key: 'via', node: LEAF }, { key: 'col', node: LEAF }] } },
    empty: { word: '', from_col: { via: 'column', col: '' } } } }] };
  const drawShaped = (value) => M.renderSkeletonForm(context(false), SHAPED, '', value === undefined ? {} : { typ: value }, 0, 's');
  const pickerOf = (root) => walk(root).find((n) => n.tagName === 'SELECT' && n.dataset && n.dataset.action === 'edit-shape-branch');
  const pickedIn = (root) => (pickerOf(root) ? (walk(pickerOf(root)).find((o) => o.tagName === 'OPTION' && o.selected) || {}).value : null);
  const inputOf = (root, p) => walk(root).find((n) => n.tagName === 'INPUT' && n.dataset && n.dataset.value === p);
  const word = drawShaped('lot');
  ok(pickedIn(word) === 'word' && inputOf(word, 'typ') && inputOf(word, 'typ').value === 'lot',
    `V1 a word: the picker says word, and the word's box at the cell's own path holds it [${pickedIn(word)}]`);
  const rec = drawShaped({ via: 'column', col: 'c1' });
  ok(pickedIn(rec) === 'from_col' && inputOf(rec, 'typ.col') && inputOf(rec, 'typ.col').value === 'c1'
     && !inputOf(rec, 'typ.from_col.col'),
    `V2 a mapping: the picker says the record branch, its fields at typ.col, no branch key on the path [${pickedIn(rec)}]`);
  const none = drawShaped(undefined);
  ok(pickedIn(none) === 'word' && inputOf(none, 'typ') && inputOf(none, 'typ').value === '',
    'V3 nothing yet: the word branch, empty -- the cell as it was before it had a second branch');
  const odd = drawShaped(['x']);
  ok(!pickerOf(odd) && controlsIn(odd).length === 0 && walk(odd).some((n) => cls(n).includes('oe-value')
     && String(n.textContent) === '["x"]'),
    'V4 a value of neither shape is shown as the value, with no picker and nothing to type over it');

  return { pass: pass - before.pass, fail: fail - before.fail };
}

// P -- the real chain panel, the shipped skeleton, declarations shaped like the box's rules.
function panelCensus(ChainRulePanel) {
  const RULES = [
    // on.columns and the top-level reads were added to the application lane's list round
    // (39f990b21): filled here so the census counts them before and after the skeleton learns them.
    { grammar: 'unified', declaration: { name: 'r_join', on: { table: 't_a', columns: ['c_a', 'c_b'] },
      reads: ['t_a', 't_b'],
      derive: { join: { right_table: 't_b', on: [{ left: 'c1', right: 'c1' }], take: ['c2', 'c3'] } },
      into: { table: 't_a' }, key: { unique: true } } },
    { grammar: 'unified', declaration: { name: 'r_decide', enabled: true, on: { table: 't_a' },
      derive: { decide: { key: ['c1'], fields: ['c2', 'c3'],
        reference_views: [{ label: 'v', query: 'q' }], auto_confirm: true, alignment: true } },
      into: { table: 't_b' } } },
    { grammar: 'unified', declaration: { name: 'r_string_in_list', enabled: false,
      derive: { join: { right_table: 't_a', on: 't_a', take: 't_a' } }, into: { table: 't_a' } } },
    { grammar: 'flat', declaration: { name: 'r_flat', trigger_table: 't_a',
      reference: { table: 't_c', map_id_template: '{x}' } } },
  ];
  const dig = (value, at) => {
    let cur = value;
    for (const part of at.match(/[^.[\]]+/g) || []) {
      if (cur == null) return undefined;
      cur = cur[/^\d+$/.test(part) ? Number(part) : part];
    }
    return cur;
  };
  let held = 0; const blank = []; let threw = null;
  for (const rule of RULES) {
    const host = makeNode(doc, 'div');
    try {
      new ChainRulePanel(host, { doc }).render({
        config_path: '/box/chain_rules.json', base: 'fp', rules: [rule.declaration.name],
        error: null, editable_unit: 'rule', name: rule.declaration.name,
        declaration: rule.declaration, raw: JSON.stringify(rule.declaration, null, 2),
        enabled: rule.declaration.enabled !== false, skeleton: SKELETON, grammar: rule.grammar,
      });
    } catch (e) { threw = `${rule.declaration.name}: ${e.message}`; continue; }
    for (const box of walk(host)) {
      if (!cls(box).includes('oe-node') || !box.attrs || box.attrs['data-path'] == null) continue;
      if (nestedIn(box).length) continue;
      const at = box.attrs['data-path'];
      const value = dig(rule.declaration, at);
      if (value === undefined || value === null || value === '') continue;
      held++;
      const nodes = walk(box);
      const input = nodes.find((n) => n.tagName === 'INPUT' && !cls(n).includes('oe-form-new-id'));
      const drawn = input ? (input.type === 'checkbox' ? String(input.checked === true) === String(value)
                                                     : String(input.value ?? '') !== '')
        : nodes.some((n) => n.tagName === 'SELECT' || cls(n).includes('oe-node-folded')
                           || (cls(n).includes('oe-value') && String(n.textContent) !== ''));
      if (!drawn) blank.push(`${rule.declaration.name}:${at}`);
    }
  }
  ok(threw === null, `P1 the real chain panel draws all four rules without throwing [${threw || 'none'}]`);
  ok(held > 0, `P2 the census saw cells that hold a value (canary) [${held}]`);
  ok(blank.length === 0, `P3 no cell that holds a value is drawn blank [${blank.join(' ') || 'none'}]`);
}

// -- base --------------------------------------------------------------------------------
const base0 = { pass, fail };
suite(await import('../src/ontology_explorer_view.js'));
panelCensus((await import('../src/chain_rule_panel.js')).ChainRulePanel);
const base = { pass: pass - base0.pass, fail: fail - base0.fail };

// -- mutants -----------------------------------------------------------------------------
const DEFECTS = [
  // V -- lead 068c904a6 ②
  ['a shape-picked oneOf is read by branch key, so a word opens no branch',
    (s) => s.replace('  const chosen = shaped ? shapeBranch(node, value, context.deref)',
                     '  const chosen = false ? shapeBranch(node, value, context.deref)')],
  ['the picked branch is drawn under its key, so its fields write typ.from_col.col',
    (s) => s.replace('    const at = shaped ? path : `${path}.${chosen}`;', '    const at = `${path}.${chosen}`;')],
  ['the branch is handed the value under its key, so the word box is empty',
    (s) => s.replace('    const own = shaped ? value : held[chosen];', '    const own = held[chosen];')],
  ['a value of neither shape gets a picker and no value',
    (s) => s.replace('  if (shaped && !shapeBranch(node, value, context.deref) && !isBlank(value)) {', '  if (false) {')],
  ['a leaf opens its control over a value it cannot hold',
    (s) => s.replace('  if (!valueFits(node, value)) {', '  if (false) {')],
  ['a branch holding the wrong shape is drawn as an empty branch',
    (s) => s.replace('  if (!valueFits(shape, value)) {', '  if (false) {')],
  ['read mode spells a list and a record with String() again',
    (s) => s.replace("    return h('span', 'oe-value', spelledValue(value));",
                     "    return h('span', 'oe-value', String(value));")],
  ['an unfit value is spelled with String(), so a record reads [object Object]',
    (s) => s.replace('  return JSON.stringify(value);', '  return String(value);')],
  ['a member row indexes the word itself, so "Lot" reads "L"',
    (s) => s.replace('(asList(node, value) || [])[key]', '(value || [])[key]')],
];
const CONTROLS = [
  ['a local rename', (s) => s.replace(/\bspelledValue\b/g, 'heldAsText')],
  ['comments stripped', (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

async function scoreMutant(mutate, tag) {
  try {
    return suite((await loadWithProbe(VIEW, { mutate, tag })).module);
  } catch (e) {
    const m = String(e && e.message);
    if (/did not mutate|unchanged/.test(m)) {
      quiet = false;
      console.error(`\nan anchor no longer matches: ${m}`);
      process.exit(2);
    }
    return { pass: 0, fail: 1 };
  }
}

const baseFailed = [...failedNames];
quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, mutate] of DEFECTS) {
  const r = await scoreMutant(mutate, 'valuefit');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}
let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  const r = await scoreMutant(mutate, 'valuefitc');
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name}  <- a check is reading source text`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${baseFailed.join('\n  ')}`);
if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);
const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escapedNames.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
