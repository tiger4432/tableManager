/**
 * declaration_form -- form D's renderer (lead f3639d4a2, owner 10-20): one renderer for the table, chain and ledger
 * declarations, its branches chosen by the skeleton's shape and never by which declaration.
 *
 * WHAT IT SCORES, each suite through the module it names (a mutant is one module, so it is scored by that one's suite):
 *   V  the view: a list of words is chips; a list of leaf records and a name -> word map are tables, a gated record
 *      list keeps the tree; a folded record says its cells and its count; datalist ids carry the form's prefix; a
 *      column cell says its table
 *   A  ontology_path: the adder's words split on commas, line breaks and tabs; switchGated takes the shut branch's
 *      values out of the document and brings them back on return
 *   S  ontology_skeleton: a required choice of one is born filled; refNames reads table_from, then sections
 *   P  the panel: two forms on one screen do not interfere; a skeleton cell added draws with no code; raw -> form ->
 *      raw gives the same document; a gate switched and switched back restores what was typed; a refused cell inside
 *      a fold opens; Enter and a paste at an adder add, and the adder empties; + row is born with a choice of one
 * The fixture skeleton uses no word of any declaration: the renderer must not know one.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc, makeNode, walk } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const FILES = {
  view: path.join(SRC, 'ontology_explorer_view.js'),
  path: path.join(SRC, 'ontology_path.js'),
  skel: path.join(SRC, 'ontology_skeleton.js'),
  panel: path.join(SRC, 'raw_registry_panel.js'),
};

const doc = makeDoc('light');
globalThis.document = doc;
// The adder's Enter and paste go in through `closest` and `click` (adderInput), and a fold counts its rows with
// `childElementCount` - spellings the shared stub does not have. They are added on THIS harness's nodes only - the shared stub's thirty-nine other users stay as they are.
const matchesSel = (n, sel) => {
  const c = /^\.([A-Za-z0-9_-]+)$/.exec(sel);
  if (c) return String(n.className || '').split(/\s+/).includes(c[1]);
  const a = /^\[([A-Za-z0-9_-]+)="(.*)"\]$/.exec(sel);
  return Boolean(a && n.attrs && n.attrs[a[1]] === a[2]);
};
const withDom = (n) => {
  n.closest = function closest(sel) { for (let at = this; at; at = at.parentNode) if (at.attrs && matchesSel(at, sel)) return at; return null; };
  n.click = function click() { return this.dispatch('click', {}); };
  Object.defineProperty(n, 'childElementCount', { get() { return this.children.length; } });
  return n;
};
doc.createElement = (tag) => withDom(makeNode(doc, tag));
doc.createElementNS = (_ns, tag) => withDom(makeNode(doc, tag));

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

const LEAF = { kind: 'leaf', hint: 'free' };
const RECORD_LIST = (fields) => ({ kind: 'map', keyed_by: 'index', member: 'row', of: { kind: 'record', fields } });
const FIX = { skeleton_version: 1, root: { kind: 'record', fields: [
  { key: 'name', required: true, node: LEAF },
  { key: 'words', required: false, node: { kind: 'map', keyed_by: 'index', member: 'word',
    of: { kind: 'leaf', hint: 'ref', section: 'names' } } },
  { key: 'rows', required: false, node: RECORD_LIST([
    { key: 'a', required: true, node: LEAF },
    { key: 'pick', required: true, node: { kind: 'leaf', hint: 'choice', list: 'ones' } }]) },
  { key: 'gated_rows', required: false, node: RECORD_LIST([
    { key: 'mode', required: true, node: { kind: 'leaf', hint: 'choice', list: 'modes' } },
    { key: 'left', required: true, when: { field: 'mode', is: 'l' }, node: LEAF }]) },
  { key: 'pairs', required: false, node: { kind: 'map', keyed_by: 'name', member: 'key', of: LEAF } },
  { key: 'gate', required: false, node: { kind: 'record', fields: [
    { key: 'mode', required: true, node: { kind: 'leaf', hint: 'choice', list: 'modes' } },
    { key: 'left', required: true, when: { field: 'mode', is: 'l' }, node: LEAF },
    { key: 'right', required: true, when: { field: 'mode', is: 'r' }, node: LEAF }] } },
  { key: 'deep', required: false, node: { kind: 'map', keyed_by: 'name', member: 'item', of: { kind: 'record', fields: [
    { key: 'x', required: true, node: LEAF }, { key: 'y', required: false, node: LEAF }] } } },
  { key: 'tab', required: false, node: LEAF },
  { key: 'col', required: false, node: { kind: 'leaf', hint: 'ref', table_from: ['tab'] } },
] } };
const LISTS = { names: ['n1', 'n2'], ones: ['only'], modes: ['l', 'r'],
  table_columns: { T: { columns: { c1: 'string', c2: 'number' } } } };
const DOC = { name: 'alpha', words: ['n1'], rows: [{ a: 'x', pick: 'only' }], gated_rows: [{ mode: 'l', left: 'L' }],
  pairs: { k: 'v' }, gate: { mode: 'l', left: 'L' }, deep: { k1: { x: 'v' } }, tab: 'T', col: 'c1' };
const copy = (v) => JSON.parse(JSON.stringify(v));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const cls = (n) => String(n.className || '').split(/\s+/);
const has = (n, c) => cls(n).includes(c);
const attr = (n, k) => (n.attrs || {})[k];
const boxAt = (root, at) => walk(root).find((n) => has(n, 'oe-node') && attr(n, 'data-path') === at);
const chipsIn = (box) => walk(box || makeNode(doc, 'div')).filter((n) => has(n, 'chip')).map((n) => String(n.textContent));

// ── V: the view, drawn through renderSkeletonForm with a context of its own ──────────────────────────────────────
function viewContext(M, over = {}) {
  return {
    schema: LISTS, readOnly: false, planRow: () => null, planLoaded: true, plannedMembers: () => [], covering: () => null,
    deref: (node) => node, refOf: (node) => M.skel.refNames(LISTS, LISTS.table_columns, node, DOC),
    heldChoice: () => '', rolesNear: () => [], usedElsewhere: () => [], renderRow: () => null, suggest: (row) => row,
    hot: [], expanded: {}, absolute: (at) => at, listPrefix: 'pfx', ...over,
  };
}

function viewSuite(M) {
  const form = M.view.renderSkeletonForm(viewContext(M), FIX.root, '', DOC, 0, 'alpha');
  const words = boxAt(form, 'words');
  ok(same(chipsIn(words), ['n1']) && walk(words || makeNode(doc, 'div')).some((n) => has(n, 'oe-form-adder')),
    `V1 a list of words is its chips and an adder [${chipsIn(words)}]`);
  const tableIn = (at) => walk(boxAt(form, at) || makeNode(doc, 'div')).find((n) => n.tagName === 'TABLE');
  const heads = (t) => (t ? walk(t).filter((n) => n.tagName === 'TH').map((n) => String(n.textContent)).filter(Boolean) : []);
  ok(same(heads(tableIn('rows')), ['a', 'pick']),
    `V2 a list of records whose cells are leaves is a table, a column per field [${heads(tableIn('rows'))}]`);
  ok(!tableIn('gated_rows') && Boolean(boxAt(form, 'gated_rows[0]')),
    'V3 a list of records with a gated cell keeps the tree (its gate decides which cells stand)');
  ok(same(heads(tableIn('pairs')), ['key', 'Value']),
    `V4 a name -> word map is a Name | Value table [${heads(tableIn('pairs'))}]`);
  const k1 = boxAt(form, 'deep.k1');
  const row = k1 ? k1.children[0] : null;
  const caret = row ? walk(row).find((n) => attr(n, 'data-action') === 'toggle-field') : null;
  const said = row ? walk(row).find((n) => has(n, 'oe-node-summary')) : null;
  ok(caret && attr(caret, 'aria-expanded') === 'false' && attr(caret, 'aria-label') === 'Open k1'
     && said && String(said.textContent) === 'x v · 2',
    `V5 a folded record is a caret and «cells · count» [${caret && attr(caret, 'aria-label')} | ${said && said.textContent}]`);
  const ids = walk(form).filter((n) => n.tagName === 'DATALIST').map((n) => attr(n, 'id'));
  ok(ids.length > 0 && ids.every((id) => String(id).startsWith('pfx-dl-')),
    `V6 every datalist id carries the form's prefix [${ids.join(' ')}]`);
  const table = walk(boxAt(form, 'col') || makeNode(doc, 'div')).find((n) => has(n, 'oe-form-column__table'));
  ok(table && String(table.textContent) === 'T.', `V7 a column cell says its table before its box [${table && table.textContent}]`);
  // Every control in a tree row's value cell is the one value box (lead 10-21): a one-of's picker, a choice, a word.
  const BOXED = { kind: 'record', fields: [
    { key: 'word', required: true, node: LEAF },
    { key: 'pick', required: true, node: { kind: 'leaf', hint: 'choice', list: 'modes' } },
    { key: 'shape', required: true, node: { kind: 'oneOf', hint: 'choice', branches: { l: LEAF, r: { kind: 'record', fields: [{ key: 'z', required: true, node: LEAF }] } } } }] };
  const bform = M.view.renderSkeletonForm(viewContext(M), BOXED, '', { word: 'w', pick: 'l', shape: { r: { z: 'q' } } }, 0, 'b');
  const controls = walk(bform).filter((n) => has(n, 'oe-node-value')).flatMap((c) => c.children)
    .filter((n) => n.tagName === 'SELECT' || n.tagName === 'INPUT' || has(n, 'oe-form-suggested'))
    .map((n) => (has(n, 'oe-form-suggested') ? n.children.find((k) => k.tagName === 'INPUT') : n));
  ok(controls.length >= 4 && controls.every((n) => n && has(n, 'oe-box')),
    `V10 every control in a row's value cell is the value box [${controls.map((n) => (n ? `${n.tagName}:${has(n, 'oe-box')}` : '-')).join(' ')}]`);
  const folded = M.view.renderAuthoringRow({ path: 'p', label: 'P', state: 'answered', tier: 'constrained_input',
    value: ['run_uid', 'lot'], refusals: [], candidates: null }, [], null, true);
  const shown = walk(folded).filter((n) => has(n, 'oe-folded-value')).map((n) => String(n.textContent));
  ok(same(shown, ['run_uid, lot']), `V8 a plan row's folded list reads as its words in its one box, not its JSON [${shown}]`);
}

// ── A: ontology_path ─────────────────────────────────────────────────────────────────────────────────────────────
function pathSuite(M) {
  const words = FIX.root.fields.find((f) => f.key === 'words').node;
  const added = M.path.addMember({ words: ['n1'] }, 'words', words, {}, 'a, b\nc\td');
  ok(added && same(added.document.words, ['n1', 'a', 'b', 'c', 'd']) && added.born === 'words[4]',
    `A1 the adder's words split on commas, line breaks and tabs [${added && JSON.stringify(added.document.words)}]`);
  const blank = M.path.addMember({ words: [] }, 'words', words, {}, '');
  ok(blank && same(blank.document.words, ['']), 'A2 nothing typed appends one empty member, as before');
  const step = (before, at, value, stash) => {
    const after = M.path.writeShapeAtPath(before, at, value);
    return M.path.switchGated(before, after, at, FIX.root, {}, stash);
  };
  const r = step({ gate: { mode: 'l', left: 'L' } }, 'gate.mode', 'r', {});
  const typed = step(r.document, 'gate.right', 'R', r.stash);
  const back = step(typed.document, 'gate.mode', 'l', typed.stash);
  const again = step(back.document, 'gate.mode', 'r', back.stash);
  ok(same(r.document.gate, { mode: 'r' }) && same(back.document.gate, { mode: 'l', left: 'L' })
     && same(again.document.gate, { mode: 'r', right: 'R' }),
    `A3 a gate switched holds only its branch, and switched back restores what was typed `
    + `[${JSON.stringify([r.document.gate, back.document.gate, again.document.gate])}]`);
  const stash = { kept: 1 };
  const plain = step({ name: 'a' }, 'name', 'b', stash);
  ok(plain.stash === stash && plain.document.name === 'b', 'A4 a leaf nothing is gated on moves nothing');
}

// ── S: ontology_skeleton ─────────────────────────────────────────────────────────────────────────────────────────
function skelSuite(M) {
  const row = FIX.root.fields.find((f) => f.key === 'rows').node.of;
  const optional = { kind: 'record', fields: [{ key: 'pick', required: false, node: { kind: 'leaf', hint: 'choice', list: 'ones' } }] };
  ok(same(M.skel.emptyOf(row, {}, 0, LISTS), { pick: 'only' }) && same(M.skel.emptyOf(row, {}), {})
     && same(M.skel.emptyOf(optional, {}, 0, LISTS), {}),
    `S1 a required choice of one is born filled; unread lists, or an optional cell, leave it absent `
    + `[${JSON.stringify(M.skel.emptyOf(row, {}, 0, LISTS))}]`);
  const col = M.skel.refNames(LISTS, LISTS.table_columns, { kind: 'leaf', hint: 'ref', table_from: ['nope', 'tab'] }, DOC);
  const names = M.skel.refNames(LISTS, LISTS.table_columns, { kind: 'leaf', hint: 'ref', section: 'names' }, DOC);
  ok(col.table === 'T' && same(col.names, ['c1', 'c2']) && same(names, { table: '', names: ['n1', 'n2'] }),
    `S2 refNames: the first table_from holding a value names the table; else the section [${JSON.stringify([col, names])}]`);
}

// ── P: the panel, as the table and chain windows seat it ─────────────────────────────────────────────────────────
const SPEC = { listKey: 'rules', nameKey: 'name', cls: 'decl', formRoot: (p) => (p && p.skeleton && p.skeleton.root) || null };
const payloadFor = (skeleton, declaration, extra = {}) => ({
  config_path: '/box/x.json', base: 'fp-1', rules: ['alpha'], error: null, editable_unit: 'rule', name: 'alpha',
  declaration, raw: JSON.stringify(declaration, null, 2), enabled: true, skeleton, ...extra });

function panelOf(M, skeleton, declaration, opts = {}) {
  const host = makeNode(doc, 'div');
  const panel = new M.panel.RawRegistryPanel(host, { doc, lists: LISTS }, SPEC);
  panel.render(payloadFor(skeleton, declaration), opts);
  const area = () => walk(host).find((n) => has(n, 'decl-raw'));
  const held = () => { try { return JSON.parse(area().value); } catch (e) { return null; } };
  const control = (at) => walk(host).find((n) => (n.tagName === 'INPUT' || n.tagName === 'SELECT')
    && (attr(n, 'data-value') === at || attr(n, 'data-path') === at) && attr(n, 'data-action'));
  const set = (at, value) => { const c = control(at); if (c) { c.value = value; c.dispatch('change', {}); } return Boolean(c); };
  return { host, panel, area, held, control, set };
}

function panelSuite(M) {
  // two forms on one screen
  const a = panelOf(M, FIX, copy(DOC));
  const b = panelOf(M, FIX, copy(DOC));
  a.set('name', 'changed');
  const lists = (p) => walk(p.host).filter((n) => n.tagName === 'DATALIST').map((n) => attr(n, 'id'));
  ok(a.held().name === 'changed' && b.held().name === 'alpha'
     && lists(a).length > 0 && lists(a).every((id) => !lists(b).includes(id)),
    `P1 two forms on one screen: an edit in one leaves the other, and their lists are their own [${lists(a)[0]} / ${lists(b)[0]}]`);

  // a skeleton cell added is drawn with no code
  const MORE = copy(FIX);
  MORE.root.fields.push({ key: 'more_words', required: false, node: { kind: 'map', keyed_by: 'index', member: 'w', of: LEAF } },
    { key: 'more_rows', required: false, node: RECORD_LIST([{ key: 'p', required: true, node: LEAF }]) });
  const more = panelOf(M, MORE, { ...copy(DOC), more_words: ['e'], more_rows: [{ p: 'q' }] });
  ok(same(chipsIn(boxAt(more.host, 'more_words')), ['e'])
     && walk(boxAt(more.host, 'more_rows') || makeNode(doc, 'div')).some((n) => n.tagName === 'TABLE'),
    'P2 a cell added to the skeleton is drawn - its chips, its table - with no line of screen code');

  // raw -> form -> raw
  const t = panelOf(M, FIX, copy(DOC));
  for (const c of walk(t.host).filter((n) => ['edit-shape', 'edit-shape-flag'].includes(attr(n, 'data-action')))) {
    c.dispatch('change', {});
  }
  const text = { ...copy(DOC), name: 'from_text' };
  t.area().value = JSON.stringify(text, null, 2);
  t.area().dispatch('input', {});
  ok(same(t.held(), text) && t.control('name') && t.control('name').value === 'from_text',
    `P3 raw -> form -> raw: every cell committed as it stands changes nothing, and the text drives the form `
    + `[${t.control('name') && t.control('name').value}]`);

  // a gate switched and switched back
  const g = panelOf(M, FIX, copy(DOC));
  g.set('gate.mode', 'r');
  const shut = copy(g.held().gate);
  g.set('gate.right', 'R');
  g.set('gate.mode', 'l');
  const back = copy(g.held().gate);
  g.set('gate.mode', 'r');
  ok(same(shut, { mode: 'r' }) && same(back, { mode: 'l', left: 'L' }) && same(g.held().gate, { mode: 'r', right: 'R' }),
    `P4 a gate switched saves only its branch; switched back, what was typed there returns [${JSON.stringify([shut, back, g.held().gate])}]`);

  // a refused cell inside a fold opens
  const r = panelOf(M, FIX, copy(DOC), { refusal: { code: 'bad_x', path: 'rules.alpha.deep.k1.x', message: 'no' } });
  const k1 = boxAt(r.host, 'deep.k1');
  const caret = k1 ? walk(k1.children[0]).find((n) => attr(n, 'data-action') === 'toggle-field') : null;
  ok(caret && attr(caret, 'aria-expanded') === 'true' && walk(k1).some((n) => has(n, 'decl-field-refusal')),
    'P5 a refused cell inside a folded member opens it, and its mark stands beside it');
  const lineOf = (tag) => tag && tag.parentNode && tag.parentNode.parentNode;
  const line = lineOf(walk(r.host).find((n) => has(n, 'decl-field-refusal')));
  const kin = line && line.parentNode ? line.parentNode.children : [];
  ok(line && has(line, 'oe-node-row') && has(line, 'is-refusal') && kin.indexOf(line) > 0 && has(kin[kin.indexOf(line) - 1], 'oe-node-row'),
    'P9 the refusal is a row of its own, right under its cell\'s row (lead 10-21 ③)');
  const again = { name: 'alpha', refusal: { code: 'bad_x', path: 'rules.alpha.deep.k1.x', message: 'no' } };
  r.panel._markShort(r.panel._formBox, again, []);
  r.panel._markShort(r.panel._formBox, again, []);
  const lines = walk(r.host).filter((n) => has(n, 'is-refusal'));
  ok(lines.length === 1 && lines.every((n) => walk(n).some((t) => has(t, 'decl-field-refusal'))),
    `P10 marked again, the old refusal goes with its row - no empty line is left [${lines.length}]`);

  // Enter and a paste at an adder
  const w = panelOf(M, FIX, copy(DOC));
  const adder = () => walk(w.host).find((n) => has(n, 'oe-form-new-id') && attr(n, 'data-for') === 'words');
  adder().value = 'n2';
  adder().dispatch('change', {});
  const afterEnter = copy(w.held().words);
  adder().dispatch('paste', { clipboardData: { getData: () => 'a, b\nc' }, preventDefault() {} });
  ok(same(afterEnter, ['n1', 'n2']) && same(w.held().words, ['n1', 'n2', 'a', 'b', 'c']) && adder().value === '',
    `P6 Enter adds the word, a paste adds each of its words, and the adder empties [${JSON.stringify(w.held().words)}]`);

  // + row is born with a choice of one
  const plus = walk(w.host).find((n) => attr(n, 'data-action') === 'form-append' && attr(n, 'data-value') === 'rows');
  if (plus) plus.dispatch('click', {});
  const rows = w.held().rows || [];
  ok(rows.length === 2 && same(rows[1], { pick: 'only' }), `P7 + row is born holding the choice of one [${JSON.stringify(rows)}]`);

  // the head says Unsaved as the text moves, not on the next draw
  const u = panelOf(M, FIX, copy(DOC));
  const marks = () => walk(u.host).filter((n) => has(n, 'decl-unsaved')).length;
  const clean = marks();
  u.set('name', 'edited');
  const edited = marks();
  u.set('name', 'alpha');
  ok(clean === 0 && edited === 1 && marks() === 0,
    `P8 one edit and the head says Unsaved; edited back to the server's text, it no longer does [${clean} ${edited} ${marks()}]`);
}

async function score(which, mutate, tag) {
  const M = {};
  try {
    for (const [key, file] of Object.entries(FILES)) {
      M[key] = key === which && mutate ? (await loadWithProbe(file, { mutate, tag })).module : await import(pathToFileURL(file).href);
    }
  } catch (e) {
    if (/unchanged/.test(String(e && e.message))) { console.error(`\nan anchor no longer matches: ${e.message}`); process.exit(2); }
    return { pass: 0, fail: 1 };
  }
  const before = { pass, fail };
  const suites = { view: viewSuite, path: pathSuite, skel: skelSuite, panel: panelSuite };
  try {
    for (const [key, run] of Object.entries(suites)) if (!which || key === which) run(M);
  } catch (e) {
    if (!quiet) console.log(`  BAD  threw: ${e && e.stack}`);
    fail++;
  }
  return { pass: pass - before.pass, fail: fail - before.fail };
}

const DEFECTS = [
  ['view', 'a list of words is drawn as member rows again',
    (s) => s.replace('  if (isChipList(context, shape) && !context.planRow(path)) {', '  if (false) {')
      .replace('  if (isChipList(context, node) && valueFits(node, value)) return renderChips', '  if (false) return renderChips')],
  ['view', 'a gated list of records is drawn as a table',
    (s) => s.replace("      return !field.when && shape && shape.kind === 'leaf';", "      return shape && shape.kind === 'leaf';")],
  ['view', 'two forms share one datalist id', (s) => s.replace("${context.listPrefix || 'oe'}-dl-", 'oe-dl-')],
  ['view', 'a folded record drops its count',
    (s) => s.replace("  return words.length ? `${words.join(' · ')} · ${count}` : '';", "  return words.join(' · ');")],
  ['view', "a one-of's picker stretches on its own class again",
    (s) => s.replace("      h, { action: 'edit-shape-branch', path, label: name, cls: 'oe-box' }),", "      h, { action: 'edit-shape-branch', path, label: name }),")],
  ['view', 'a word box sized by its own class again',
    (s) => s.replace("  const input = h('input', 'oe-field-input oe-box');\n  // 🔴 A NUMBER", "  const input = h('input', 'oe-field-input');\n  // 🔴 A NUMBER")],
  ['view', 'a column cell hides its table', (s) => s.replace('  if (!table) return control;', '  return control;')],
  ['view', "a plan row's folded list is its JSON again",
    (s) => s.replace("words ? words.map(String).join(', ')", 'words ? JSON.stringify(words)')],
  ['path', "the adder's words go in as one member", (s) => s.replace('.split(/[,\\n\\t]/)', '.split(/\\u0000/)')],
  ['path', 'a switched gate forgets what was typed', (s) => s.replace('      kept[at] = record[field.key];\n', '')],
  ['path', 'a switched gate keeps the shut branch in the document', (s) => s.replace('      delete record[field.key];\n', '')],
  ['skel', 'a choice of one is left for the person',
    (s) => s.replace("  return shape && shape.hint === 'choice' && shape.list && lists ? onlyMember(lists[shape.list]) : undefined;",
      '  return undefined;')],
  ['panel', 'two panels of a registry share list ids',
    (s) => s.replace('    this._listPrefix = `${spec.cls}-${Math.random().toString(36).slice(2, 8)}`;', '    this._listPrefix = spec.cls;')],
  ['panel', 'the refusal back inside its cell\'s value column',
    (s) => s.replace("  if (own) node.insertBefore(lineRow(Number(own.dataset.depth) || 0, tag, 'is-refusal'), own.nextSibling || null);\n  else node.appendChild(tag);",
      '  (slot || node).appendChild(tag);')],
  ['panel', 'marked again, the old refusal leaves its empty line',
    (s) => s.replace("      const gone = line && ` ${line.className || ''} `.includes(' is-refusal ') ? line : tag;", '      const gone = tag;')],
  ['panel', 'a refused cell stays folded shut',
    (s) => s.replace('[refusedAt(view, spec), ...missingRequired(root, value, this._defs)].filter(Boolean)', '[]')],
  ['panel', 'a paste at an adder is a plain paste', (s) => s.replace("        box.addEventListener('paste', adderInput);\n", '')],
  ['panel', 'the adder keeps what it took', (s) => s.replace("          if (typed) typed.value = '';\n", '')],
  ['panel', 'the panel never switches a gate', (s) => s.replace('          updated = switched.document;\n', '')],
  ['panel', 'the head says Unsaved only on the next draw', (s) => s.replace('    this.draftOf = String(key || \'\');\n    this._sayUnsaved();\n', '    this.draftOf = String(key || \'\');\n')],
  ['panel', 'a + row is born without the lists', (s) => s.replace("named ? named.value : '', this.lists);", "named ? named.value : '');")],
];
const CONTROLS = [
  ['panel', 'a local rename', (s) => s.replace(/\bheld2\b/g, 'parsedDoc')],
  ['view', 'a local rename', (s) => s.replace(/\bfoldSummary\b/g, 'whatItHolds')],
  ['panel', 'comments stripped', (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

const base = await score(null, null, 'declform');
const baseFailed = [...failedNames];
quiet = true;
let caught = 0; const escaped = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [which, name, mutate] of DEFECTS) {
  const r = await score(which, mutate, 'declform');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escaped.push(name); console.log(`  ESCAPED ${name}`); }
}
let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [which, name, mutate] of CONTROLS) {
  const r = await score(which, mutate, 'declformc');
  if (r.fail === 0) console.log(`  escaped ${name} (${which})`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name} (${which})  <- a check is reading source text`); }
}
quiet = false;
if (base.fail) console.error(`\nfailed:\n  ${baseFailed.join('\n  ')}`);
if (escaped.length) console.error(`\ndefects that escaped:\n  ${escaped.join('\n  ')}`);
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects caught, ${escaped.length} escaped; `
  + `${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(base.fail + escaped.length + controlsCaught ? 1 : 0);
