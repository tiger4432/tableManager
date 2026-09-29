/**
 * chain_list_edit -- the chain window's lists open, and their items can be edited, added and
 * removed, through the SAME writers the ledger explorer uses.
 *
 * WHY THIS EXISTS. 09-24, the owner's Chrome, after the skeleton learned lists: `derive.join.on`
 * and `take` drew as 「접힘 · 2/3」 and did not open when clicked, and `+ pair` did nothing. The
 * renderer draws a fold toggle, `+`, a named `+` and `−` on every map; only the explorer had
 * anything behind them. The chain panel listened for `change` alone.
 *
 * WHAT IT SCORES (the real ChainRulePanel, the SHIPPED skeleton, the click path):
 *   C  a folded list opens on its toggle and shows its items as inputs (the Lead's gate ㉢)
 *   D  editing one item keeps the list a LIST in the raw text (㉣)
 *   E  `+` adds an item and opens it; `−` removes it; the folds survive the redraw (㉤)
 *   N  a named `+` on a name-keyed map adds the member under the name typed
 *   A  the shared writer refuses to write over a value that is not a list -- the explorer's `+`
 *      used to replace `"on": "lot_event"` with `[<empty>]`
 *   W  one word in a list of WORDS is its one member: `+` keeps it, edit writes `["new"]`,
 *      `-` leaves `[]`
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc, makeNode, walk } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PANEL = path.join(HERE, '..', 'src', 'raw_registry_panel.js');
const PATHS = path.join(HERE, '..', 'src', 'ontology_path.js');
const SKELETON = JSON.parse(readFileSync(
  path.join(HERE, '..', '..', 'server', 'chain_skeleton.json'), 'utf8'));

const doc = makeDoc('light');
globalThis.document = doc;

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

const cls = (n) => String(n.className || '').split(/\s+/);
const payloadFor = (declaration) => ({
  config_path: '/box/chain_rules.json', base: 'fp', rules: [declaration.name], error: null,
  editable_unit: 'rule', name: declaration.name, declaration,
  raw: JSON.stringify(declaration, null, 2), enabled: true, skeleton: SKELETON, grammar: 'unified',
});
// The chain registry's own spec, read from the module that ships it.
const { CHAIN_RULE_REGISTRY } = await import('../src/chain_rule_panel.js');

function mountPanel(M, declaration, storage = null) {
  const host = makeNode(doc, 'div');
  const panel = new M.RawRegistryPanel(host, { doc, storage }, CHAIN_RULE_REGISTRY);
  panel.render(payloadFor(declaration));
  const find = (pred) => walk(host).find(pred);
  const btn = (action, value) => find((n) => n.attrs && n.attrs['data-action'] === action
    && n.attrs['data-value'] === value);
  const click = (action, value) => { const b = btn(action, value); if (b) b.dispatch('click'); return !!b; };
  const boxAt = (p) => find((n) => cls(n).includes('oe-node') && n.attrs && n.attrs['data-path'] === p);
  const inputAt = (p) => { const b = boxAt(p); return b ? walk(b).find((n) => n.tagName === 'INPUT') : null; };
  const raw = () => {
    const area = find((n) => n.tagName === 'TEXTAREA');
    try { return JSON.parse(area.value); } catch (e) { return null; }
  };
  return { host, panel, btn, click, boxAt, inputAt, raw, find };
}

const memStore = () => ({ m: new Map(), getItem(k) { return this.m.has(k) ? this.m.get(k) : null; },
  setItem(k, v) { this.m.set(k, String(v)); }, removeItem(k) { this.m.delete(k); } });

const JOIN = { name: 'r_join', on: { table: 't_a' },
  derive: { join: { right_table: 't_b', on: [{ left: 'c1', right: 'c2' }], take: ['c3', 'c4'] } },
  into: { table: 't_a' }, key: { unique: true } };
const DECIDE = { name: 'r_decide', on: { table: 't_a' },
  derive: { decide: { key: ['c1'], fields: ['c2'], aggregations: {} } }, into: { table: 't_b' } };

function suite(M) {
  const before = { pass, fail };
  const p = mountPanel(M, JOIN);
  const on = () => (((p.raw() || {}).derive || {}).join || {}).on;

  // C -- the fold opens, and the items are inputs
  ok(!p.inputAt('derive.join.on[0].left'), 'C0 before: the pair list is folded -- its items are not drawn');
  ok(p.click('toggle-field', 'derive.join.on') && Boolean(p.boxAt('derive.join.on[0]')),
    'C1 its toggle opens it: the item row is drawn');
  // [총괄 09-24] ONE click: an index-list item follows its list open, so no second toggle here --
  //    pressing `on[0]` now would CLOSE it.
  const l0 = p.inputAt('derive.join.on[0].left'); const r0 = p.inputAt('derive.join.on[0].right');
  ok(l0 && r0 && l0.value === 'c1' && r0.value === 'c2',
    `C2 ONE click shows the pair's left=c1 right=c2 as inputs [${l0 && l0.value} / ${r0 && r0.value}]`);
  p.click('toggle-field', 'derive.join.take');
  const t0 = p.inputAt('derive.join.take[0]'); const t1 = p.inputAt('derive.join.take[1]');
  ok(t0 && t1 && t0.value === 'c3' && t1.value === 'c4',
    `C3 the column list shows its two items [${t0 && t0.value} / ${t1 && t1.value}]`);
  const flag = p.inputAt('key.unique');
  ok(flag && flag.type === 'checkbox' && flag.checked === true, 'C4 key.unique is a ticked checkbox');

  // D -- editing one item keeps a list a list
  // The input AS IT STANDS ON SCREEN now, not the one grabbed before `take` opened: D scores the
  // write. Whether a redraw keeps that node is `chain_rule_form` N1's question, not this one's.
  const l0now = p.inputAt('derive.join.on[0].left');
  if (l0now) { l0now.value = 'c9'; l0now.dispatch('change'); }
  ok(Array.isArray(on()) && on().length === 1 && on()[0].left === 'c9' && on()[0].right === 'c2',
    `D1 editing on[0].left writes into the LIST, not over it [${JSON.stringify(on())}]`);

  // E -- add, remove, and the folds survive
  ok(p.click('form-append', 'derive.join.on') && Array.isArray(on()) && on().length === 2,
    `E1 "+ item" adds a second pair [${JSON.stringify(on())}]`);
  ok(Boolean(p.inputAt('derive.join.on[1].left')), 'E2 ...and what it added is open');
  ok(p.click('form-remove', 'derive.join.on[1]') && Array.isArray(on()) && on().length === 1,
    `E3 "-" removes it [${JSON.stringify(on())}]`);
  ok(Boolean(p.inputAt('derive.join.on[0].left')), 'E4 the lists opened by hand stay open through the redraw');

  // F -- + then - brings the document back, and nothing is left to "restore" (총괄 09-24)
  const store = memStore();
  const f = mountPanel(M, JOIN, store);
  const slot = `assy.draft.${CHAIN_RULE_REGISTRY.cls}.${JOIN.name}`;
  f.click('toggle-field', 'derive.join.on');
  f.click('form-append', 'derive.join.on');
  ok(store.getItem(slot) !== null, 'F0 a real change is kept as a draft (canary: the store is wired)');
  f.click('form-remove', 'derive.join.on[1]');
  ok(store.getItem(slot) === null && f.panel.draft === null,
    'F1 + then - brings the document back, and no draft is left to be offered as a restore');

  // N -- a named + on a name-keyed map
  const q = mountPanel(M, DECIDE);
  // An EMPTY map opens by itself (its `+` is the only thing in it), so the toggle would close it.
  const nameBox = () => walk(q.host).find((n) => cls(n).includes('oe-form-new-id')
    && n.attrs && n.attrs['data-for'] === 'derive.decide.aggregations');
  if (!nameBox()) q.click('toggle-field', 'derive.decide.aggregations');
  const named = nameBox();
  if (named) named.value = 'n_rows';
  const aggs = () => ((((q.raw() || {}).derive || {}).decide || {}).aggregations);
  ok(named && q.click('form-name', 'derive.decide.aggregations')
     && aggs() && Object.prototype.hasOwnProperty.call(aggs(), 'n_rows'),
    `N1 a named "+" adds the member under the name typed [${JSON.stringify(aggs())}]`);
  // The map was open only because it was EMPTY; once it holds a member that rule stops holding
  // it open, so the add itself must open it -- and the member, which is named, not numbered.
  ok(Boolean(q.boxAt('derive.decide.aggregations.n_rows')),
    'N2 ...and the map it landed in stays open, with the new member drawn');

  return { pass: pass - before.pass, fail: fail - before.fail };
}

function suitePaths(P) {
  const before = { pass, fail };
  const LIST = { kind: 'map', keyed_by: 'index', member: 'item', of: { kind: 'leaf', hint: 'free' } };
  // `derive.join.on` is a list of PAIRS; a word held there is not one of its members.
  const PAIRS = { kind: 'map', keyed_by: 'index', member: 'pair',
    of: { kind: 'record', fields: [{ key: 'left', node: { kind: 'leaf', hint: 'free' } }] } };
  const held = { derive: { join: { on: 'lot_event' } } };
  ok(P.addMember(held, 'derive.join.on', PAIRS, {}) === null && held.derive.join.on === 'lot_event',
    'A1 the shared writer refuses to write a list of pairs over a string held there');
  const grown = P.addMember({ a: ['x'] }, 'a', LIST, {});
  ok(grown && JSON.stringify(grown.document.a) === '["x",""]' && grown.born === 'a[1]',
    'A2 ...and appends to a list that is one');

  // W -- one word in a list of words is its one member: `+`, edit and `-` keep that reading
  const word = { class: 'Lot' };
  const added = P.addMember(word, 'class', LIST, {});
  ok(added && JSON.stringify(added.document.class) === '["Lot",""]' && added.born === 'class[1]',
    `W1 "+" on a one-word list keeps the word and appends [${added && JSON.stringify(added.document.class)}]`);
  const edited = P.writeShapeAtPath(word, 'class[0]', 'Wafer');
  ok(edited && JSON.stringify(edited.class) === '["Wafer"]',
    `W2 editing the one member writes a one-item list [${edited && JSON.stringify(edited.class)}]`);
  const removed = P.deleteAtPath(word, P.splitBundlePath('class[0]'));
  ok(removed && JSON.stringify(removed.class) === '[]' && word.class === 'Lot',
    `W3 "-" on the one member leaves an empty list; the input is untouched [${removed && JSON.stringify(removed.class)}]`);
  const listed = P.writeShapeAtPath({ class: ['a', 'b', 'c'] }, 'class[1]', 'B');
  ok(listed && JSON.stringify(listed.class) === '["a","B","c"]',
    'W4 a list that is one is written in place, not lifted');
  return { pass: pass - before.pass, fail: fail - before.fail };
}

// -- base --------------------------------------------------------------------------------
const base0 = { pass, fail };
suite(await import('../src/raw_registry_panel.js'));
suitePaths(await import('../src/ontology_path.js'));
const base = { pass: pass - base0.pass, fail: fail - base0.fail };

// -- mutants -----------------------------------------------------------------------------
const DEFECTS = [
  [PANEL, suite, 'the chain panel stops receiving clicks on its form, as before 09-24',
    (s) => s.replace("        box.addEventListener('click', act);", '')],
  [PANEL, suite, 'the form context is handed an empty fold record, as it used to be',
    (s) => s.replace('spec, value, this._formFold.expandedFields),', 'spec, value, {}),')],
  [PANEL, suite, 'what "+" added is not opened',
    (s) => s.replace("type: 'FIELD_TOGGLED', paths: [path, added.born], open: true,",
                     "type: 'FIELD_TOGGLED', paths: [], open: true,")],
  [PANEL, suite, 'a draft equal to the server document is kept, and offered as a restore',
    (s) => s.replace("    if (base && base.key === String(key || '') && sameDocument(text, base.raw)) {",
                     '    if (false) {')],
  [PATHS, suitePaths, 'the shared writer writes over a value that is not a list',
    (s) => s.replace('  if (!valueFits(node, held)) return null;\n', '')],
  [PATHS, suitePaths, '"+" reads the held word as no list, so the word is lost',
    (s) => s.replace('const held = asList(node, getAtPath(', 'const held = ((n, v) => v)(node, getAtPath(')],
  [PATHS, suitePaths, 'an index step into a word is not lifted, so edit and "-" do nothing',
    (s) => s.replace('    next = setAtPath(next, steps.slice(0, depth), [held]) || next;\n', '')],
];
const CONTROLS = [
  [PANEL, suite, 'a local rename', (s) => s.replace(/\bheld3\b/g, 'parsed3')],
  [PANEL, suite, 'comments stripped',
    (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

async function scoreMutant(target, run, mutate, tag) {
  try {
    return run((await loadWithProbe(target, { mutate, tag })).module);
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
for (const [target, run, name, mutate] of DEFECTS) {
  const r = await scoreMutant(target, run, mutate, 'listedit');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}
let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [target, run, name, mutate] of CONTROLS) {
  const r = await scoreMutant(target, run, mutate, 'listeditc');
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
