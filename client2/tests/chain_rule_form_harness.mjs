/**
 * chain_rule_form -- the chain tab can ADD a rule it did not have, and every field it draws
 * comes from the skeleton the SERVER served.
 *
 * WHY THIS EXISTS (C-86). Owner: 「규칙 등록 영역에 규칙을 추가할 수가 없어」 -- the picker only
 * held names the file already had, so a rule could be edited and never created, while the server
 * had accepted a new name all along (`save_chain_rule_raw`: a new rule lands ARMED BUT OFF).
 * And the one editor was a raw JSON box, so the operator had to know the 23 routing keys by heart.
 *
 * WHAT IT SCORES:
 *   A  the field set is the SKELETON's leaf set -- drift 0, measured against the shipped file
 *   B  a DECOY skeleton is drawn verbatim: the client authors no field name, so invented keys
 *      appear and the real ones do not. This is the assertion that cannot be faked by luck
 *   C  add -> name -> save sends ONE payload shape, through the SAME save the picker uses,
 *      and its document is the EMPTY one rather than the rule that happened to be open
 *   D  one document, two editors: a form edit rewrites the raw text, and save sends that text
 *   E  a refusal the server ADDRESSED to a field is marked at that field, by code, no sentence
 *   F  three states on a closed list: a list nobody served reads as UNREAD, never as 「none」
 *   G  assembly: two panels on one page, different registries, no interference
 *
 * 🔴 THE FORM IS NOT NEW CODE. It is `renderSkeletonForm` from the explorer, fed a context whose
 *    plan callbacks all answer empty -- the same thing `renderReadTree` does. A second
 *    hand-written form would be a screen that stopped coming from the declaration, which is the
 *    defect this round exists to remove.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc, makeNode, walk } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const PANEL = path.join(SRC, 'raw_registry_panel.js');

// 🔴 THE SHIPPED SKELETON, NOT A COPY OF IT. `server/chain_skeleton.json` is generated from
//    `chain_bindings.routing_keys()` and a server test counts the two against each other, so
//    reading it here means a routing key added on the server reddens this harness -- which is
//    the whole claim of C-86 (2): the client authors none of these names.
const SKELETON = JSON.parse(readFileSync(
  path.join(HERE, '..', '..', 'server', 'chain_skeleton.json'), 'utf8'));

// A skeleton whose keys exist NOWHERE in this product. If the form draws these, the form is
// reading the document it was handed; if it draws `trigger_table`, something here knows a name
// it should not.
const DECOY = {
  skeleton_version: 1,
  root: {
    kind: 'record',
    fields: [
      { key: 'decoy_alpha', required: true, node: { kind: 'leaf', hint: 'free' } },
      { key: 'decoy_flag', required: false, node: { kind: 'leaf', hint: 'flag' } },
      { key: 'decoy_pick', required: false, node: { kind: 'leaf', hint: 'choice' } },
    ],
  },
};

const doc = makeDoc('light');
// `renderSkeletonForm` builds with the GLOBAL document (see `h` in ontology_explorer_view.js),
// while the panel builds with `deps.doc`. Pointing both at one stub is what makes the tree one
// tree -- two documents here would silently produce two unrelated trees.
globalThis.document = doc;

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

const leafKeys = (skeleton) => (skeleton.root.fields || [])
  .filter((f) => f.node && f.node.kind === 'leaf').map((f) => f.key);

const payloadFor = (skeleton, declaration, extra = {}) => ({
  config_path: '/box/chain_rules.json',
  base: 'fp-1',
  rules: ['alpha', 'beta'],
  error: null,
  editable_unit: 'rule',
  name: 'alpha',
  declaration,
  raw: JSON.stringify(declaration, null, 2),
  enabled: true,
  skeleton,
  ...extra,
});

const CHAIN_SPEC_EXTRA = { addLabel: '규칙 추가', choiceList: 'mappers' };

function mount() {
  const host = makeNode(doc, 'div');
  host.querySelector = (sel) => walk(host).find((n) => matches(n, sel)) || null;
  return host;
}
// The stub has no selector engine; these two forms are all this harness uses.
function matches(node, sel) {
  const cls = /^\.([A-Za-z0-9_-]+)$/.exec(sel);
  if (cls) return String(node.className || '').split(/\s+/).includes(cls[1]);
  const attr = /^\[data-path="(.*)"\]$/.exec(sel);
  if (attr) return node.attrs && node.attrs['data-path'] === attr[1];
  return false;
}
const paths = (root) => walk(root).map((n) => (n.attrs || {})['data-path']).filter((v) => v != null);
const byCls = (root, cls) => walk(root).filter(
  (n) => String(n.className || '').split(/\s+/).includes(cls));
const attrOf = (root, key) => walk(root).filter((n) => n.attrs && n.attrs[key] != null);

function makePanel(M, spec, deps = {}) {
  const host = mount();
  // every node the panel or the form creates gets the selector the stub lacks
  const panel = new M.RawRegistryPanel(host, { doc, ...deps }, spec);
  return { host, panel };
}

function suite(M) {
  const before = { pass, fail };
  const SPEC = { listKey: 'rules', nameKey: 'name', cls: 'chain-rule',
                 formRoot: (p) => (p && p.skeleton && p.skeleton.root) || null, ...CHAIN_SPEC_EXTRA };

  // ── A: the field set is the skeleton's ────────────────────────────────────────────
  const a = makePanel(M, SPEC);
  a.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 't' }));
  const drawn = new Set(paths(a.host).filter((p) => p && !p.includes('.')));
  const wanted = leafKeys(SKELETON);
  const missing = wanted.filter((k) => !drawn.has(k));
  const invented = [...drawn].filter((k) => !wanted.includes(k)
    && !(SKELETON.root.fields || []).some((f) => f.key === k));
  ok(wanted.length > 10 && missing.length === 0,
    `A1 every skeleton leaf is drawn -- ${wanted.length} keys, missing [${missing.join(', ')}]`);
  ok(invented.length === 0, `A2 nothing is drawn that the skeleton did not name -- [${invented.join(', ')}]`);

  // ── B: the decoy ─────────────────────────────────────────────────────────────────
  const b = makePanel(M, SPEC);
  b.panel.render(payloadFor(DECOY, { decoy_alpha: 'x' }));
  const decoyPaths = new Set(paths(b.host));
  ok(['decoy_alpha', 'decoy_flag', 'decoy_pick'].every((k) => decoyPaths.has(k)),
    'B1 a skeleton of invented keys is drawn verbatim');
  ok(!decoyPaths.has('trigger_table') && !decoyPaths.has('mapper'),
    'B2 ... and no real routing key appears -- the client authors no field name');

  // ── C: add a rule that did not exist ──────────────────────────────────────────────
  const saves = [];
  const c = makePanel(M, SPEC, { onSave: (p) => saves.push(p) });
  c.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 't', mapper: 'm' }));
  const addBtn = byCls(c.host, 'chain-rule-add')[0];
  ok(!!addBtn, 'C1 a registry that declares the word draws the add control');
  if (addBtn) addBtn.dispatch('click', {});
  // 🔴 C-95. ONE PLACE TO TYPE THE NAME, and that place is the form's own `name` cell. The
  //    second box beside the form was drawn WHILE the form drew `name` too, so the screen held
  //    two name fields and could not say which one the save would read (measured 2026-09-13).
  //    The claim is unchanged -- adding a rule asks for a name, and the save carries THAT name.
  const asideBox = attrOf(c.host, 'data-new-name')[0];
  const nameBox = walk(c.host).find((x) => x.attrs && x.attrs['data-value'] === 'name');
  ok(!asideBox && !!nameBox,
     'C2 adding asks for a name in ONE place -- the form`s own cell, not a second box beside it');
  if (nameBox) {
    nameBox.value = 'gamma';
    nameBox.dispatch('change', { target: nameBox });
  }
  const saveBtn = byCls(c.host, 'chain-rule-save')[0];
  if (saveBtn) saveBtn.dispatch('click', {});
  const sent = saves[saves.length - 1] || {};
  ok(sent.name === 'gamma', `C3 save carries the TYPED name -- got [${sent.name}]`);
  ok(sent.base === 'fp-1', 'C4 ... and the base fingerprint it was handed, unchanged');
  let sentDoc = null;
  try { sentDoc = JSON.parse(sent.raw || 'null'); } catch (e) { sentDoc = null; }
  ok(sentDoc && typeof sentDoc === 'object' && !sentDoc.trigger_table,
    'C5 ... and an EMPTY document, not the rule that happened to be open');
  // 🔴 C-95. The picker says WHICH rule is on the screen. It used to keep showing the rule that
  //    was open while a new one was being written, so the one control that answers 「what am I
  //    looking at」 answered wrong -- and it is the control a person checks before saving.
  const shown = byCls(c.host, 'chain-rule-picker')[0];
  const marked = shown ? shown.children.filter((o) => o.getAttribute('selected')) : [];
  ok(marked.length === 1 && marked[0].value === M.NEW_NAME,
     `C6 while a new rule is being written the picker says so -- [${marked.map((o) => o.value).join(',')}]`);

  // ── C-95-b: a response with NO name is 「nothing picked」, not 「this one, blank」 ─────
  const h = makePanel(M, SPEC);
  const opening = payloadFor(SKELETON, { name: 'alpha' });
  delete opening.name;
  delete opening.declaration;
  delete opening.raw;
  delete opening.enabled;
  h.panel.render(opening);
  const openPicker = byCls(h.host, 'chain-rule-picker')[0];
  const openMarked = openPicker ? openPicker.children.filter((o) => o.getAttribute('selected')) : [];
  ok(openMarked.length === 1 && openMarked[0].value === M.PICK_NAME,
     `C7 a response with no name says 「nothing picked」 -- [${openMarked.map((o) => o.value).join(',')}]`);
  ok(byCls(h.host, 'chain-rule-form').length === 0 && byCls(h.host, 'chain-rule-raw').length === 0,
     'C8 ... and draws no editor, because an empty document under a live save button is not kindness');
  ok(byCls(h.host, 'chain-rule-save').length === 0,
     'C9 ... and no save either -- a button that can only be refused is a question sent to the server');

  // ── D: one document, two editors ─────────────────────────────────────────────────
  const saves2 = [];
  const d = makePanel(M, SPEC, { onSave: (p) => saves2.push(p) });
  d.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  const area = byCls(d.host, 'chain-rule-raw')[0];
  const field = walk(d.host).find((n) => n.attrs && n.attrs['data-value'] === 'trigger_table');
  ok(!!field, 'D1 a leaf carries the write address the explorer already uses');
  if (field) {
    field.value = 'after';
    field.dispatch('change', {});
  }
  let afterEdit = null;
  try { afterEdit = JSON.parse(area.value || 'null'); } catch (e) { afterEdit = null; }
  ok(afterEdit && afterEdit.trigger_table === 'after',
    'D2 a FORM edit rewrites the raw document -- the two cannot hold different answers');
  byCls(d.host, 'chain-rule-save')[0].dispatch('click', {});
  ok((saves2[saves2.length - 1] || {}).raw === area.value,
    'D3 save sends the raw text -- one document reaches the server, not two');

  // ── E: the refusal is marked where the server addressed it ───────────────────────
  const e = makePanel(M, SPEC);
  e.panel.render(payloadFor(SKELETON, { name: 'alpha', mapper: 'nope' }), {
    refusal: { code: 'mapper_not_registered', path: 'rules.alpha.mapper', message: 'x: y' },
  });
  const marks = attrOf(e.host, 'data-refused');
  ok(marks.length === 1 && marks[0].attrs['data-refused'] === 'mapper',
    `E1 the refused FIELD is marked -- ${marks.length} mark(s)`);
  ok(marks.length === 1 && marks[0].textContent === 'mapper_not_registered',
    'E2 ... with the server`s CODE, not a sentence of ours');
  const e2 = makePanel(M, SPEC);
  e2.panel.render(payloadFor(SKELETON, { name: 'alpha' }), {
    refusal: { code: 'stale_base', path: 'rules.alpha', message: 'x' },
  });
  ok(attrOf(e2.host, 'data-refused').length === 0,
    'E3 a refusal about the WHOLE rule marks no field -- it has no field to mark');

  // ── F: a list nobody served is UNREAD, not empty ─────────────────────────────────
  const f = makePanel(M, SPEC);
  f.panel.render(payloadFor(SKELETON, { name: 'alpha' }));
  const choiceHost = walk(f.host).find((n) => (n.attrs || {})['data-path'] === 'mapper');
  const choiceText = choiceHost ? String(choiceHost.textContent || '') : '';
  ok(choiceHost && !/없음/.test(choiceText),
    `F1 an unserved closed list does not claim there are none -- [${choiceText.slice(0, 40)}]`);
  const f2 = makePanel(M, SPEC, { lists: { mappers: ['alpha_mapper', 'beta_mapper'] } });
  f2.panel.render(payloadFor(SKELETON, { name: 'alpha' }));
  const picker = walk(f2.host).filter((n) => n.tagName === 'SELECT'
    && (n.attrs || {})['data-value'] === 'mapper');
  ok(picker.length === 1,
    `F2 a served list becomes a picker on the field the skeleton marked -- ${picker.length}`);
  // 🔴 THE THIRD STATE, AND THE ONE THIS BOX IS ACTUALLY IN (S-207: `registered` is EMPTY here,
  //    because the owner's one live mapper is refused). 「read it, there are none」 is a VALUE and
  //    must not look like 「never asked」 -- the operator who sees the second goes looking for a
  //    network problem that is not there.
  const f3 = makePanel(M, SPEC, { lists: { mappers: [] } });
  f3.panel.render(payloadFor(SKELETON, { name: 'alpha' }));
  const emptyHost = walk(f3.host).find((n) => (n.attrs || {})['data-path'] === 'mapper');
  const emptyText = emptyHost ? String(emptyHost.textContent || '') : '';
  ok(emptyText !== '' && emptyText !== choiceText,
    `F3 a list that WAS read and holds nothing reads differently from one never read `
    + `-- none [${emptyText.slice(0, 30)}] vs unread [${choiceText.slice(0, 30)}]`);

  // ── G: no skeleton, no form; and two panels do not interfere ─────────────────────
  const g = makePanel(M, { listKey: 'tables', nameKey: 'table', cls: 'table-config' });
  g.panel.render({ config_path: '/p', base: 'b', tables: ['t1'], name: '', table: 't1',
                   raw: '{}', error: null });
  ok(byCls(g.host, 'table-config-form').length === 0,
    'G1 a registry whose route serves no skeleton keeps today`s screen -- no form');
  ok(byCls(g.host, 'table-config-add').length === 0,
    'G2 ... and no add control, because that registry declared no word for it');
  const h1 = makePanel(M, SPEC);
  const h2 = makePanel(M, SPEC);
  h1.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'one' }));
  h2.panel.render(payloadFor(DECOY, { decoy_alpha: 'two' }));
  const h1Paths = new Set(paths(h1.host));
  ok(h1Paths.has('trigger_table') && !h1Paths.has('decoy_alpha'),
    'G3 two panels on one page keep their own documents');

  // ── H: the part owns what is open and what is unsaved (C-101 ①) ───────────────────
  // 🔴 THE OWNER'S SENTENCE: 「체인 규칙 설정 쓰다가 지혼자 새로고침되서 초기화되는데?」. The page
  //    re-reads every 30 seconds WITHOUT a name, so that response carries a list and no
  //    document -- drawing it does not make the boxes stale, it takes the editor AWAY.
  const clock = makePanel(M, SPEC);
  clock.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  const clockField = walk(clock.host).find((n) => n.attrs && n.attrs['data-value'] === 'trigger_table');
  if (clockField) { clockField.value = 'typed'; clockField.dispatch('change', {}); }
  const listOnly = payloadFor(SKELETON, { name: 'alpha' });
  delete listOnly.name;
  delete listOnly.declaration;
  delete listOnly.raw;
  delete listOnly.enabled;
  listOnly.rules = ['alpha', 'beta', 'gamma'];
  clock.panel.render(listOnly, { background: true });
  const stillThere = walk(clock.host).find((n) => n.attrs && n.attrs['data-value'] === 'trigger_table');
  ok(Boolean(stillThere) && stillThere.value === 'typed',
    `H1 a background read does not swap out a document being edited -- [${stillThere ? stillThere.value : 'the form is GONE'}]`);
  const clockPicker = byCls(clock.host, 'chain-rule-picker')[0];
  const clockNames = clockPicker ? clockPicker.children.map((o) => o.value) : [];
  ok(clockNames.includes('gamma'),
    `H2 ... while the LIST it went for does refresh -- that is what the read was for [${clockNames.join(',')}]`);
  ok(clockNames.indexOf(M.PICK_NAME) === -1,
    'H3 ... and refreshing the list does not put 「nothing picked」 over an open rule');
  // 🔴 THE SAME LOSS THROUGH A CLICK, AND NO TIMER NEEDED. Folding 「원본」 redraws the panel from
  //    the response it is holding, so before C-101 ① one fold threw away everything typed.
  const fold = byCls(clock.host, 'chain-rule-raw-fold')[0];
  if (fold) fold.dispatch('click', {});
  const afterFold = walk(clock.host).find((n) => n.attrs && n.attrs['data-value'] === 'trigger_table');
  ok(Boolean(fold) && Boolean(afterFold) && afterFold.value === 'typed',
    `H4 the part's OWN redraw keeps the unsaved document too -- [${afterFold ? afterFold.value : 'no field'}]`);
  // 🔴 AND A DRAFT ENDS WHERE ITS DOCUMENT DOES. The answer to a save IS the document now; a
  //    draft that outlived it would put the old text back with nothing on the screen saying so.
  clock.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'stored' }),
                     { saved: { name: 'alpha', rules: ['alpha', 'beta'], backup: '/box/bak' } });
  const afterSave = walk(clock.host).find((n) => n.attrs && n.attrs['data-value'] === 'trigger_table');
  ok(Boolean(afterSave) && afterSave.value === 'stored',
    `H5 once the save answers, the served document wins -- [${afterSave ? afterSave.value : 'no field'}]`);
  // ⚠️ NOTHING OPEN MEANS NOTHING TO PROTECT -- the tab's first read is a background one, and a
  //    guard that refused it would open the tab on an empty panel.
  const first = makePanel(M, SPEC);
  first.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'served' }),
                     { background: true });
  ok(byCls(first.host, 'chain-rule-form').length === 1,
    'H6 a background read with nothing open still draws -- that is how the tab opens');
  // 🔴 AND A PERSON PRESSING A BUTTON IS NOT THE CLOCK. The panel redraws itself from the
  //    response it stored; if it passed that response's background flag back in, every fold
  //    after the tab opened would be a button that does nothing.
  const reFold = byCls(first.host, 'chain-rule-raw-fold')[0];
  if (reFold) reFold.dispatch('click', {});
  const reArea = byCls(first.host, 'chain-rule-raw')[0];
  ok(Boolean(reFold) && Boolean(reArea) && reArea.hidden !== true,
    'H7 a fold pressed after a background read still opens');

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the real module -------------------------------------------------');
suite(await import('../src/raw_registry_panel.js'));

// -- mutants ---------------------------------------------------------------------------
const DEFECTS = [
  ['the form is drawn from a list of its own instead of the skeleton',
    s => s.replace('    const root = spec.formRoot ? spec.formRoot(payload) : null;',
                   "    const root = spec.formRoot ? { kind: 'record', fields: ["
                   + "{ key: 'trigger_table', node: { kind: 'leaf', hint: 'free' } }] } : null;")],
  // Re-aimed by C-95 at the same claim: the name the person typed must win over the one that
  // was open. The cell it is typed into moved into the form, so this is where that now decides.
  ['the add control saves the name that was already open',
    s => s.replace('        if (formOwnsName) {', '        if (false) {')],
  // Re-aimed by C-101 ①: the options are built in ONE place now (`_options`), so the claim
  // 「the picker says WHICH document is on the screen」 is decided there. Same claim, same C6.
  ['the picker keeps showing the rule that was open while a new one is written',
    s => s.replace('if (this.newMode && this.spec.addLabel) opt(NEW_NAME, true);',
                   'if (false) opt(NEW_NAME, true);')],
  // C-95-b. Without the placeholder the browser picks the first option for the screen, and the
  // screen then names a rule it has never read -- with empty boxes beside the name.
  ['a response with no name still names the first rule in the list',
    s => s.replace('else if (!open) opt(PICK_NAME, true);', 'else if (false) opt(PICK_NAME, true);')],
  ['an editor is drawn for a rule nobody picked',
    s => s.replace('    const picked = this.newMode || Boolean(view.name);',
                   '    const picked = true;')],
  ['the save button stands on a screen with no document',
    s => s.replace('    if (picked || !root) head.appendChild(save);', '    head.appendChild(save);')],
  ['a new rule starts from the rule that was open',
    s => s.replace('      let held = this.newMode\n'
                   + '        ? (emptyOf(root, (payload.skeleton || {}).defs) || {})\n',
                   '      let held = this.newMode\n        ? (payload.declaration || {})\n')],
  ['a form edit no longer reaches the document that is saved',
    s => s.replace('          area.value = JSON.stringify(updated, null, 2);\n', '')],
  // 🔴 THE TRAP THIS ROUND FELL INTO, KEPT AS A MUTANT. `setAtPath`/`writeShapeAtPath` return a
  //    NEW document; reading them as in-place writers silently throws the edit away, and the
  //    screen looks like a form that does nothing. It cost D2 one debug round.
  ['the writer is read as mutating in place, so the edit is thrown away',
    s => s.replace('          const updated = writeShapeAtPath(held2, String(path), next);\n'
                   + '          if (updated === null) return;\n'
                   + '          area.value = JSON.stringify(updated, null, 2);\n'
                   + '          this._keep(key, area.value);\n'
                   + '          draw(updated);',
                   '          writeShapeAtPath(held2, String(path), next);\n'
                   + '          area.value = JSON.stringify(held2, null, 2);\n'
                   + '          this._keep(key, area.value);\n'
                   + '          draw(held2);')],
  ['the refused field is not marked',
    s => s.replace('        markRefusedField(box, view, spec);\n', '')],
  ['the mark carries a sentence instead of the code',
    s => s.replace('  tag.textContent = refusal.code || \'\';',
                   '  tag.textContent = refusal.message || \'\';')],
  // 🔴 E3's mutant would have been 「delete the empty-address guard」, and it ESCAPED: the
  //    prefix ends in a dot, so a whole-rule address never reaches that line, and an empty
  //    address matches no field anyway. The guard is gone rather than the assertion -- scoring
  //    a branch nobody takes reports coverage this harness does not have. Same finding as C-85.
  ['a refusal that names no field is pinned to one anyway',
    s => s.replace('  if (!refusal.path.startsWith(prefix)) return null;',
                   '  const loose = !refusal.path.startsWith(prefix);')
          .replace('  const at = refusal.path.slice(prefix.length);',
                   "  const at = loose ? 'name' : refusal.path.slice(prefix.length);")],
  ['the registry`s closed list is ignored, so the field claims there are none',
    s => s.replace('      if (shape && shape.kind === \'leaf\' && shape.hint === \'choice\' && !shape.list && choiceList) {',
                   '      if (false) {')],
  ['an unread list is folded into an empty one, so 「never asked」 reads as 「there are none」',
    s => s.replace("    this.lists = deps.lists || {};", "    this.lists = deps.lists || { mappers: [] };")],
  // 🔴 C-101 ①. Four ways this screen reset itself while somebody was typing.
  ['a background read is drawn over the document being edited',
    s => s.replace('if (opts.background && this.open) {', 'if (false) {')],
  ['the unsaved document is dropped, so any redraw rebuilds from the response',
    s => s.replace('const drafted = this.draft !== null && this.draftOf === key ? this.draft : null;',
                   'const drafted = null;')],
  ['the part passes the stored background flag back in, so a fold after the tab opens does nothing',
    s => s.replace('this.render(this._payload, { ...this._opts, background: false });',
                   'this.render(this._payload, this._opts);')],
  ['a draft outlives the document it belongs to, so old text returns after a save',
    s => s.replace('if (opts.saved || (this.draft !== null && this.draftOf !== key)) this._forget();', '')],
  ['the add control is drawn for a registry that declared no word for it',
    s => s.replace('    if (spec.addLabel) {', '    if (true) {')],
];
const CONTROLS = [
  ['a local rename', s => s.replace(/\bconst held2\b/g, 'const parsedDoc')
                           .replace(/\bheld2\b/g, 'parsedDoc')],
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

async function scoreMutant(mutate, tag) {
  try {
    return suite((await loadWithProbe(PANEL, { mutate, tag })).module);
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

const base = { pass, fail };
failedNames.length = 0;

quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, mutate] of DEFECTS) {
  const r = await scoreMutant(mutate, 'chainform');
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  const r = await scoreMutant(mutate, 'chainformc');
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name}  <- a check is reading source text`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${failedNames.join('\n  ')}`);
if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);

const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escapedNames.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
