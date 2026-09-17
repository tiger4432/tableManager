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

/** 두 목록이 같은가 — 문구를 짚는 것이 아니라 «서버가 준 값»이 그대로 섰는지. */
function eqTexts(got, want, name) {
  ok(JSON.stringify(got) === JSON.stringify(want), `${name} ${JSON.stringify(got)}`);
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

// ⚠️ A FIXTURE, NOT A COPY OF THE DECLARATION. What is scored here is the TEMPLATE: a registry
// that declares these things must behave this way. That the CHAIN registry declares them is
// scored where it can only be true end to end -- `chain_rule_user_path_harness` drives the
// real `chain_rule_panel.js` through the real page.
const CHAIN_SPEC_EXTRA = { addLabel: '규칙 추가', choiceList: 'mappers', refList: 'tables' };

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

  // ── I: reference cells choose from a catalogue, and still take anything (C-101 ②) ──
  // 🔴 Measured 2026-09-13 in `server/chain_skeleton.json`: SEVEN leaves carry `hint: 'ref'` and
  //    every one of them carries NO section. The explorer asks `context.declared(node.section)`
  //    for those, this context answered `[]`, and so seven table names were typed by hand.
  // ⚠️ NO NEW CONTROL. The explorer already draws a `datalist` -- searchable, still an input, and
  //    a name the catalogue never heard of stays exactly as typed with no mark on it. What was
  //    missing was the list, not the control, and that distinction is the whole of this fix.
  const refs = makePanel(M, SPEC, { lists: { tables: ['lot_event', 'lot_slot_wafer'] } });
  refs.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'lot_event' }));
  const refBox = walk(refs.host).find((n2) => n2.attrs && n2.attrs['data-value'] === 'trigger_table');
  const refList = walk(refs.host).find((n2) => n2.tagName === 'DATALIST');
  const offered = refList ? refList.children.map((o) => o.value) : [];
  ok(Boolean(refBox) && refBox.tagName === 'INPUT' && Boolean(refBox.attrs.list),
    `I1 a reference cell offers a list -- [${refBox ? refBox.tagName : 'no box'}, list=${refBox ? refBox.attrs.list : '-'}]`);
  ok(offered.includes('lot_event') && offered.includes('lot_slot_wafer'),
    `I2 ... and the list is the catalogue it was handed -- [${offered.join(',')}]`);
  // 🔴 A NAME THE CATALOGUE DOES NOT HOLD IS KEPT AS TYPED, AND NOTHING ON THE SCREEN OBJECTS.
  //    The server judges a table name; a screen that refused one would refuse a table added
  //    between this read and the save.
  if (refBox) { refBox.value = 'a_table_nobody_declared'; refBox.dispatch('change', {}); }
  let refDoc = null;
  try { refDoc = JSON.parse((byCls(refs.host, 'chain-rule-raw')[0] || {}).value || 'null'); }
  catch (e) { refDoc = null; }
  ok(refDoc && refDoc.trigger_table === 'a_table_nobody_declared',
    'I3 a typed name outside the catalogue reaches the document unchanged');
  ok(byCls(refs.host, 'chain-rule-field-refusal').length === 0,
    'I4 ... and carries no refusal mark -- the server judges a table name, not this screen');
  // ⚠️ A CATALOGUE NEVER READ DRAWS NO LIST, AND THAT IS NOT 「there are none」. For a SUGGESTION
  //    the two states share a pixel on purpose: an absent suggestion claims nothing. A closed
  //    list is the opposite case and `closedListChoice` keeps those four states apart (F1-F3).
  const noCat = makePanel(M, SPEC);
  noCat.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'lot_event' }));
  const noCatBox = walk(noCat.host).find((n2) => n2.attrs && n2.attrs['data-value'] === 'trigger_table');
  ok(Boolean(noCatBox) && !noCatBox.attrs.list && noCatBox.tagName === 'INPUT',
    'I5 an unread catalogue leaves the cell typable with no list -- a suggestion absent claims nothing');
  // 🔴 AND THE SKELETON WINS WHEN IT NAMES ITS OWN. A grammar whose cells draw from different
  //    catalogues is not this grammar today, and the day it is, one list answering for all of
  //    them would offer table names where zones belong -- with nothing erroring.
  const SECTIONED = { skeleton_version: 1, root: { kind: 'record', fields: [
    { key: 'decoy_alpha', required: true, node: { kind: 'leaf', hint: 'ref', section: 'zones' } }] } };
  const sect = makePanel(M, { listKey: 'rules', nameKey: 'name', cls: 'chain-rule',
                              formRoot: (p) => (p && p.skeleton && p.skeleton.root) || null,
                              refList: 'tables' },
                         { lists: { tables: ['lot_event'], zones: ['Asia/Seoul'] } });
  sect.panel.render(payloadFor(SECTIONED, { decoy_alpha: 'Asia/Seoul' }));
  const sectList = walk(sect.host).find((n2) => n2.tagName === 'DATALIST');
  const sectOffered = sectList ? sectList.children.map((o) => o.value) : [];
  ok(sectOffered.includes('Asia/Seoul') && !sectOffered.includes('lot_event'),
    `I6 a leaf that names its own section gets THAT list -- [${sectOffered.join(',')}]`);

  // ── J: one dropdown writes either spelling, and says which one is held (C-101 ③) ───
  // 🔴 Measured on the server (`chain_bindings.mapper_cells` / `mapper_resolvable`): `mapper`
  //    resolves ONLY through the registry, so a file function cannot be named in that cell --
  //    it is two cells or nothing. That is why one choice has to write two cells, and why
  //    putting a token in `mapper` would make the document lie to every other reader.
  const MEMBERS = [
    { value: 'build_dt_map', group: '등록 이름' },
    { value: 'mappers.lot:build_rows', label: 'mappers.lot · build_rows', group: '파일 함수' },
  ];
  const SPLIT = (value) => {
    const at = String(value).lastIndexOf(':');
    return at <= 0 ? null : { mapper: null, mapper_module: String(value).slice(0, at),
                              mapper_function: String(value).slice(at + 1) };
  };
  const JOIN = (doc) => (doc.mapper || (doc.mapper_module && doc.mapper_function
    ? `${doc.mapper_module}:${doc.mapper_function}` : ''));
  const TWO_SPELLINGS = {
    ...SPEC,
    firstScreen: ['mapper'],
    oneOf: [{ one: ['mapper'], other: ['mapper_module', 'mapper_function'], list: 'mappers',
              split: SPLIT, join: JOIN }],
  };
  const pick = (host) => walk(host).find(
    (n2) => n2.attrs && n2.attrs['data-value'] === 'mapper' && n2.tagName === 'SELECT');
  const docOf = (host) => {
    try { return JSON.parse((byCls(host, 'chain-rule-raw')[0] || {}).value || 'null'); }
    catch (e) { return null; }
  };

  const two = makePanel(M, TWO_SPELLINGS, { lists: { mappers: MEMBERS } });
  two.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 't' }));
  const chooser = pick(two.host);
  const chooserGroups = chooser
    ? (chooser.children || []).filter((c) => c.tagName === 'OPTGROUP')
      .map((g) => g.getAttribute('label')) : [];
  ok(Boolean(chooser) && chooserGroups.length === 2,
    `J1 the mapper cell is a dropdown of two groups [${chooserGroups.join(',')}]`);
  if (chooser) { chooser.value = 'mappers.lot:build_rows'; chooser.dispatch('change', {}); }
  const afterPick = docOf(two.host) || {};
  ok(afterPick.mapper_module === 'mappers.lot' && afterPick.mapper_function === 'build_rows',
    `J2 choosing a file function fills BOTH cells (${JSON.stringify([afterPick.mapper_module, afterPick.mapper_function])})`);
  ok(!('mapper' in afterPick),
    'J3 ... and clears the one-cell spelling, because that cell means 「a registered name」');
  const chooser2 = pick(two.host);
  if (chooser2) { chooser2.value = 'build_dt_map'; chooser2.dispatch('change', {}); }
  const afterName = docOf(two.host) || {};
  ok(afterName.mapper === 'build_dt_map',
    `J4 choosing a registered name writes that one cell (${JSON.stringify(afterName.mapper)})`);
  // 🔴 AND THE CONTROL SAYS WHAT THE RULE HOLDS. A rule written with the two cells left this
  //    dropdown EMPTY while the rule did name a mapper -- one response carrying two states.
  const held2 = makePanel(M, TWO_SPELLINGS, { lists: { mappers: MEMBERS } });
  held2.panel.render(payloadFor(SKELETON, { name: 'alpha', mapper_module: 'mappers.lot',
                                            mapper_function: 'build_rows' }));
  const shown2 = pick(held2.host);
  const chosen2 = shown2
    ? (shown2.children || []).flatMap((c) => (c.tagName === 'OPTGROUP' ? c.children : [c]))
      .filter((o) => o.selected).map((o) => o.value) : [];
  ok(chosen2.length === 1 && chosen2[0] === 'mappers.lot:build_rows',
    `J5 a rule spelled in two cells shows its mapper in the dropdown [${chosen2.join(',')}]`);
  // 🔴 AND THE DROPDOWN IS ON THE FIRST SCREEN FOR THAT RULE. It is the only place the mapper
  //    can be CHANGED now, so hiding it behind 「고급」 is hiding the control, not a duplicate.
  const advanced = byCls(held2.host, 'chain-rule-advanced')[0];
  const hidden = advanced ? (advanced.children || []).map((c) => (c.attrs || {})['data-path']) : [];
  ok(hidden.indexOf('mapper') === -1,
    `J6 ... and that dropdown is not folded away [${hidden.filter(Boolean).slice(0, 6).join(',')}]`);
  // 🔴 RULING 511 (owner: the chain-rule form is still the old shape). The dropdown being
  //    on the first screen is only half of it -- the two cells the rule is WRITTEN in were
  //    there too, because `value !== undefined` was tested without the `hidden` guard. Three
  //    cells for one fact, and the operator has to ask which of them to fill.
  ok(hidden.indexOf('mapper_module') !== -1 && hidden.indexOf('mapper_function') !== -1,
    `J6-b ... and the two cells it is WRITTEN in are folded, so one fact keeps one cell`
    + ` [${hidden.filter(Boolean).slice(0, 8).join(',')}]`);
  // ── lines OUTSIDE the list: 「here but not choosable」 ────────────────────────────
  const noted = makePanel(M, TWO_SPELLINGS, { lists: { mappers: MEMBERS },
    notes: [{ kind: 'other', text: 'mappers.rf · not a chain mapper' },
             { kind: 'refused', text: 'mappers.x · ImportError' }] });
  noted.panel.render(payloadFor(SKELETON, { name: 'alpha' }));
  const lines = byCls(noted.host, 'chain-rule-list-note');
  eqTexts(lines.map((l) => l.textContent),
    ['mappers.rf · not a chain mapper', 'mappers.x · ImportError'],
    'J7 what is here but not choosable gets one line each, in the server`s words');
  ok(lines.length === 2 && lines[0].attrs['data-note'] === 'other'
    && lines[1].attrs['data-note'] === 'refused',
    'J8 ... and each line says which of the two it is, as a value not a sentence');
  ok(byCls(two.host, 'chain-rule-list-note').length === 0,
    'J9 no such cells means no lines at all -- an empty row would claim there are none');

  // ── K: the unsaved document is VISIBLE, defensible and reversible (C-106) ─────────
  // 🔴 C-101 stopped the timer from swapping a form being edited -- and said nothing about it.
  //    An invisible guard is, to the operator, no guard: they do not know there is anything to
  //    save. Seven things follow from that, and this section scores them.
  const store = () => {
    const held = new Map();
    return {
      getItem: (k) => (held.has(k) ? held.get(k) : null),
      setItem: (k, v) => held.set(k, String(v)),
      removeItem: (k) => held.delete(k),
      _map: held,
    };
  };
  const typeInto = (host, at, value) => {
    const box = walk(host).find((n2) => n2.attrs && n2.attrs['data-value'] === at
      && ['INPUT', 'SELECT', 'TEXTAREA'].includes(n2.tagName));
    if (!box) return false;
    box.value = value;
    box.dispatch('change', {});
    return true;
  };
  const doc2 = (host) => {
    try { return JSON.parse((byCls(host, 'chain-rule-raw')[0] || {}).value || 'null'); }
    catch (e) { return null; }
  };

  const shelf = store();
  const saves3 = [];
  const k = makePanel(M, SPEC, { storage: shelf, onSave: (p) => saves3.push(p) });
  k.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  ok(byCls(k.host, 'chain-rule-unsaved').length === 0,
    'K1 a document straight from the server carries no 「unsaved」 mark');
  typeInto(k.host, 'trigger_table', 'typed');
  k.panel.render(k.panel._payload, {});
  const mark = byCls(k.host, 'chain-rule-unsaved')[0];
  ok(Boolean(mark) && mark.attrs['data-unsaved'] === 'edited',
    `K2 one edit and the screen says so [${mark ? mark.textContent : 'no mark'}]`);
  // 🔴 Ctrl+S IS THE SAVE BUTTON, not a second one: the same body, reached another way.
  k.panel.root.dispatch('keydown', { key: 's', ctrlKey: true, preventDefault() {} });
  ok(saves3.length === 1 && JSON.parse(saves3[0].raw).trigger_table === 'typed',
    `K3 Ctrl+S saves the edited document (${saves3.length} save(s))`);
  // ⚠️ And it is the ONLY shortcut: a bare 「s」 typed into a box must not save.
  k.panel.root.dispatch('keydown', { key: 's', preventDefault() {} });
  ok(saves3.length === 1, 'K4 ... and a plain 「s」 does not');

  // ── ② leaving a document with unsaved text asks first ────────────────────────────
  const opened = [];
  let asked = 0;
  const no = makePanel(M, SPEC, { storage: store(), confirm: () => { asked += 1; return false; },
                                  onOpen: (name) => opened.push(name) });
  no.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  typeInto(no.host, 'trigger_table', 'typed');
  no.panel.render(no.panel._payload, {});
  const noPicker = byCls(no.host, 'chain-rule-picker')[0];
  noPicker.value = 'beta';
  noPicker.dispatch('change', { target: { value: 'beta' } });
  ok(asked === 1 && opened.length === 0,
    `K5 leaving an unsaved document asks, and 「no」 stays put (asked ${asked}, opened ${opened.length})`);
  ok(noPicker.value === 'alpha',
    `K6 ... and the picker goes back to what is actually open [${noPicker.value}]`);
  const yes = makePanel(M, SPEC, { storage: store(), confirm: () => true,
                                   onOpen: (name) => opened.push(name) });
  yes.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  typeInto(yes.host, 'trigger_table', 'typed');
  yes.panel.render(yes.panel._payload, {});
  const yesPicker = byCls(yes.host, 'chain-rule-picker')[0];
  yesPicker.dispatch('change', { target: { value: 'beta' } });
  ok(opened.length === 1 && opened[0] === 'beta', 'K7 ... and 「yes」 opens the other one');
  let askedClean = 0;
  const clean = makePanel(M, SPEC, { storage: store(), confirm: () => { askedClean += 1; return true; },
                                     onOpen: () => {} });
  clean.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  byCls(clean.host, 'chain-rule-picker')[0].dispatch('change', { target: { value: 'beta' } });
  ok(askedClean === 0, 'K8 a document with nothing unsaved asks nothing -- a question with one answer is noise');

  // ── ③ putting it back ────────────────────────────────────────────────────────────
  const undoBtn = walk(k.host).find((n2) => n2.attrs && n2.attrs['data-action'] === 'undo-chain-rule');
  ok(Boolean(undoBtn), 'K9 an unsaved document offers a way back to the served one');
  if (undoBtn) undoBtn.dispatch('click', {});
  ok((doc2(k.host) || {}).trigger_table === 'before',
    `K10 ... and taking it puts the SERVER's document back [${(doc2(k.host) || {}).trigger_table}]`);
  ok(byCls(k.host, 'chain-rule-unsaved').length === 0, 'K11 ... and the mark goes with it');

  // ── ④ the draft outlives the page ────────────────────────────────────────────────
  const kept = store();
  const before2 = makePanel(M, SPEC, { storage: kept });
  before2.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  typeInto(before2.host, 'trigger_table', 'survives');
  const after = makePanel(M, SPEC, { storage: kept });   // a new page, the same browser
  after.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  ok((doc2(after.host) || {}).trigger_table === 'survives',
    `K12 a draft survives the page it was typed on [${(doc2(after.host) || {}).trigger_table}]`);
  const restoredMark = byCls(after.host, 'chain-rule-unsaved')[0];
  ok(Boolean(restoredMark) && restoredMark.attrs['data-unsaved'] === 'restored',
    `K13 ... and says it was RESTORED -- text that comes back silently reads as the server's`);
  // 🔴 저장이 답하면 보관도 끝입니다 — 안 지우면 다음에 연 사람이 «이미 저장된» 글자를
  //    「미저장」으로 봅니다.
  after.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'stored' }),
                     { saved: { name: 'alpha', rules: ['alpha', 'beta'], backup: '/b' } });
  const reopened = makePanel(M, SPEC, { storage: kept });
  reopened.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'stored' }));
  ok((doc2(reopened.host) || {}).trigger_table === 'stored'
     && byCls(reopened.host, 'chain-rule-unsaved').length === 0,
    'K14 once the save answers, the kept draft is gone with it');
  // ⚠️ 보관을 못 쓰는 환경(프라이빗 모드)에서도 화면은 그대로 돕니다.
  const noStore = makePanel(M, SPEC, { storage: null });
  noStore.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  ok(typeInto(noStore.host, 'trigger_table', 'x') && (doc2(noStore.host) || {}).trigger_table === 'x',
    'K15 a browser that keeps nothing still edits normally');

  // ── ⑤ choosing a mapper brings the parameters it declares ────────────────────────
  const WITH_PARAMS = [
    { value: 'named', label: 'named', group: '등록 이름',
      fill: { 'params.retry': '', 'params.batch': '' } },
  ];
  const p6 = makePanel(M, { ...SPEC, firstScreen: ['mapper'] },
                       { storage: store(), lists: { mappers: WITH_PARAMS } });
  p6.panel.render(payloadFor(SKELETON, { name: 'alpha', params: { retry: '3' } }));
  typeInto(p6.host, 'mapper', 'named');
  const withParams = doc2(p6.host) || {};
  ok(withParams.params && withParams.params.batch === '',
    `K16 choosing a mapper brings the parameters it declares [${JSON.stringify(withParams.params)}]`);
  ok(withParams.params && withParams.params.retry === '3',
    'K17 ... and does not overwrite one the document already holds -- choosing is not erasing');

  // ── ⑥ the lines sit under the cell they are about ────────────────────────────────
  // ⚠️ 어느 칸 밑인지는 «선언»이 답합니다(목록을 든 `oneOf` 그룹의 첫 철자) — 실제 체인
  //    등록부가 그 선언을 갖고 있고, 이 픽스처도 그것을 답니다.
  const under = makePanel(M, { ...SPEC, oneOf: [{ one: ['mapper'], other: [], list: 'mappers' }] }, {
    storage: store(), lists: { mappers: [{ value: 'a', group: 'g' }, { value: 'b', group: 'g' }] },
    notes: [{ kind: 'refused', text: 'mappers.x · ImportError' }] });
  under.panel.render(payloadFor(SKELETON, { name: 'alpha' }));
  const cell = walk(under.host).find((n2) => (n2.attrs || {})['data-path'] === 'mapper');
  ok(Boolean(cell) && byCls(cell, 'chain-rule-list-note').length === 1,
    'K18 what is here but not choosable reads UNDER the cell it is about');

  // 🔴 총괄의 물음(2026-09-13 21:52): 새 규칙 초안을 「취소」한 뒤에도 화면에 무언가 남는가.
  //    낱말 「수정」은 이 패널의 것이 «아니었습니다»(admin.html 의 상시 단계 칩 — 측정: 이
  //    파일의 소스에 그 낱말이 0). 그런데 그 물음이 «진짜 하나»를 열었습니다: 취소는 버리는
  //    것인데 보관은 남아서, 다음 [+ 규칙 추가] 가 지난번에 버린 글자로 열립니다.
  const shelf2 = store();
  const cancelled = makePanel(M, SPEC, { storage: shelf2 });
  cancelled.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 'before' }));
  const addCtl = walk(cancelled.host).find((n2) => (n2.attrs || {})['data-action'] === 'add-chain-rule');
  if (addCtl) addCtl.dispatch('click', {});
  typeInto(cancelled.host, 'name', 'half_typed');
  const cancelCtl = walk(cancelled.host).find(
    (n2) => (n2.attrs || {})['data-action'] === 'cancel-chain-rule');
  ok(Boolean(cancelCtl), 'K19 a new rule being written offers a cancel');
  if (cancelCtl) cancelCtl.dispatch('click', {});
  ok(byCls(cancelled.host, 'chain-rule-unsaved').length === 0,
    'K20 cancelling leaves no unsaved mark on the screen');
  const addAgain = walk(cancelled.host).find((n2) => (n2.attrs || {})['data-action'] === 'add-chain-rule');
  if (addAgain) addAgain.dispatch('click', {});
  const reopenedName = walk(cancelled.host).find(
    (n2) => (n2.attrs || {})['data-value'] === 'name' && n2.tagName === 'INPUT');
  ok(Boolean(reopenedName) && reopenedName.value === '',
    `K21 ... and the NEXT new rule starts empty, not from what was thrown away [${reopenedName ? reopenedName.value : 'no box'}]`);
  ok(byCls(cancelled.host, 'chain-rule-unsaved').length === 0,
    'K22 ... with nothing calling it 「restored」 -- the operator discarded it');

  // ═══ U. C-111 — 「셋 중 하나」는 스켈레톤이 말하고 폼이 «따라» 그린다 (판정 407·411) ═══
  //
  // 🔴 이 절이 재는 것은 «폼이 문법을 안 짓는다»입니다. 새 칸을 그리려고 손으로 그린 입력이
  //    하나라도 생기면 그 단계는 실패입니다(계획 §9.2) — 그래서 U6 이 모든 입력의 주소가
  //    스켈레톤의 키에서 나왔는지 셉니다.
  // ⚠️ 여기 쓰는 스켈레톤은 «서버가 낸 것»입니다(`server/chain_skeleton.json` 의 `unified_root`).
  //    사본을 두면 서버가 가지를 하나 더 낸 날 이 절이 «조용히» 옛 모양을 재게 됩니다.
  const UNI = SKELETON.unified_root;
  const UNI_SPEC = { ...SPEC,
    formRoot: (p) => (p && p.grammar === 'unified'
      ? (p.skeleton || {}).unified_root : (p.skeleton || {}).root) || null,
    grammarOf: (p) => (p && typeof p.grammar === 'string' ? p.grammar : '') };
  const uniPayload = (declaration) => payloadFor(SKELETON, declaration, { grammar: 'unified' });
  const JOINED = { name: 'alpha', on: { table: 'dt_left' },
                   derive: { kind: 'join', join: { right_table: 'dt_right' } },
                   into: { table: 'dt_left' } };

  const u = makePanel(M, UNI_SPEC);
  u.panel.render(uniPayload(JOINED));
  const uniPaths = new Set(paths(u.host));
  ok(uniPaths.has('derive') && uniPaths.has('into') && uniPaths.has('on'),
    'U1 a unified rule draws the unified root, not the flat one');
  ok(!uniPaths.has('trigger_table') && !uniPaths.has('mapper_module'),
    'U2 ... and none of the flat cells come with it');
  // 🔴 고른 가지 «만». 셋을 다 펼치면 운영자가 「무엇을 적어야 하나」를 못 고릅니다(§9.3 ①).
  const deriveDrawn = [...uniPaths].filter((p) => p.startsWith('derive.'));
  ok(deriveDrawn.length > 0 && deriveDrawn.every((p) => p.startsWith('derive.join.')),
    `U3 only the CHOSEN branch is drawn [${[...uniPaths].filter((p) => p.startsWith('derive')).join('|')}]`);
  // 🔴 판정 411: 가지의 노드는 «가지 키 밑»에 삽니다 — 선언이 그 모양이기 때문입니다.
  ok(uniPaths.has('derive.join.right_table'),
    `U4 ... at the branch KEY, which is where the declaration puts it`);
  const pickers = attrOf(u.host, 'data-action').filter(
    (el) => el.attrs['data-action'] === 'edit-shape-branch');
  ok(pickers.length === 2, `U5 one picker per 「pick one」, no more [${pickers.length}]`);
  const options = (el) => walk(el).filter((k) => k.tagName === 'OPTION')
    .map((k) => (k.attrs || {}).value ?? k.textContent);
  ok(options(pickers[0]).join(',') === 'join,decide,mapper',
    `U6 the options are the BRANCH KEYS, in the server's order [${options(pickers[0]).join(',')}]`);
  // 🔴 안 고른 자리는 «비어 있는 것이 아니라 모르는 것»입니다 — 가지를 안 그립니다.
  const u2 = makePanel(M, UNI_SPEC);
  u2.panel.render(uniPayload({ name: 'alpha', on: { table: 'dt_left' } }));
  const bare = new Set(paths(u2.host));
  ok(bare.has('derive') && ![...bare].some((p) => p.startsWith('derive.')),
    `U7 nothing chosen draws no branch at all [${[...bare].filter((p) => p.startsWith('derive')).join('|')}]`);
  // 🔴 «손그림 입력 0» — 폼의 모든 컨트롤이 스켈레톤의 키에서 나온 주소를 답니다.
  // ⚠️ «폼 안»만 섭니다 — 머리의 규칙 고르개는 폼의 칸이 아니고 스켈레톤의 주소를 안 달았습니다.
  //    그것까지 세면 「손그림 1」이 되지만, 그건 이 단언이 묻는 것이 아닙니다.
  const formBox = byCls(u.host, 'chain-rule-form')[0] || u.host;
  const controls = walk(formBox).filter((el) => el.tagName === 'INPUT' || el.tagName === 'SELECT');
  const addressed = controls.filter((el) => (el.attrs || {})['data-value']);
  ok(controls.length > 0 && controls.length === addressed.length,
    `U8 every control in the form carries a skeleton address [${addressed.length}/${controls.length}]`);
  // 🔴 그리고 옛 평면 규칙은 «오늘 그대로»입니다 (무회귀).
  const u3 = makePanel(M, UNI_SPEC);
  u3.panel.render(payloadFor(SKELETON, { name: 'alpha', trigger_table: 't' }, { grammar: 'flat' }));
  const flat = new Set(paths(u3.host));
  ok(flat.has('trigger_table') && !flat.has('derive'),
    'U9 a flat rule still draws the flat root');
  ok(byCls(u3.host, 'chain-rule-grammar').length === 1
    && byCls(u3.host, 'chain-rule-grammar')[0].textContent === 'flat',
    `U10 the screen says which grammar this rule is in`);
  // 🔴 고르는 것은 «짐을 갈아 끼우는» 일입니다: 고른 가지 하나만 남고 나머지는 사라집니다.
  //    둘이 남으면 로더가 둘 중 하나를 고르게 되고, 그 고르기는 화면이 안 보여 준 판정입니다.
  //    ⚠️ 적혀 있던 `kind` 는 «고른 것과 맞춰» 지킵니다 — 지우지도, 없던 것을 만들지도 않습니다.
  const u4 = makePanel(M, UNI_SPEC);
  u4.panel.render(uniPayload(JOINED));
  const branchPicker = attrOf(u4.host, 'data-action').find(
    (el) => el.attrs['data-action'] === 'edit-shape-branch'
      && el.attrs['data-value'] === 'derive');
  if (branchPicker) {
    branchPicker.value = 'mapper';
    branchPicker.dispatch('change', {});
  }
  let wroteDoc = {};
  const rawBox = byCls(u4.host, 'chain-rule-raw')[0];
  try { wroteDoc = JSON.parse((rawBox && rawBox.value) || '{}'); } catch (e) { wroteDoc = {}; }
  const derive = wroteDoc.derive || {};
  ok(Object.prototype.hasOwnProperty.call(derive, 'mapper')
    && !Object.prototype.hasOwnProperty.call(derive, 'join')
    && derive.kind === 'mapper',
    `U11 picking a branch leaves exactly that branch [${JSON.stringify(derive)}]`);

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the real module -------------------------------------------------');
suite(await import('../src/raw_registry_panel.js'));

// -- mutants ---------------------------------------------------------------------------
const DEFECTS = [
  // C-111. 「셋 중 하나」의 «패널 쪽» 절반 — 고르기가 문서에 닿는 자리와 문법 낱말.
  // ⚠️ 렌더러 쪽 절반(고른 가지만 그린다 · 가지 키 밑에 그린다)은 여기서 변이를 못 겁니다:
  //    이 하니스는 한 번에 «모듈 하나»만 갈아 끼우고, 폼을 그리는 것은 `ontology_explorer_view.js`
  //    입니다. 그 주장들은 U3·U4·U7 이 «진짜 모듈»로 채점합니다 — 과장하지 않고 적어 둡니다.
  ['picking a branch keeps the old one, so the document names two',
    s => s.replace('            const oneOfNode = shapeAt(root, splitBundlePath(String(path)),',
                   '            Object.assign(next2, kept);\n'
                   + '            const oneOfNode = shapeAt(root, splitBundlePath(String(path)),')],
  ['the branch picker writes nothing at all',
    s => s.replace("          if (action === 'edit-shape-branch') {", '          if (false) {')],
  ['the screen stops saying which grammar the rule is in',
    s => s.replace('    if (grammar) {', '    if (false) {')],
  ['the form is drawn from a list of its own instead of the skeleton',
    s => s.replace('    const root = spec.formRoot ? spec.formRoot(payload) : null;',
                   "    const root = spec.formRoot ? { kind: 'record', fields: ["
                   + "{ key: 'trigger_table', node: { kind: 'leaf', hint: 'free' } }] } : null;")],
  // Re-aimed by C-95 at the same claim: the name the person typed must win over the one that
  // was open. The cell it is typed into moved into the form, so this is where that now decides.
  ['the add control saves the name that was already open',
    // Re-aimed by C-106 ①: the save body became `runSave` (shared with Ctrl+S), so it sits
    // one level out. Same claim, same C3.
    s => s.replace('      if (formOwnsName) {', '      if (false) {')],
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
    // Re-aimed by C-101 ③: the write became a LOOP over the cells the registry named, so the
    // same misreading now lives on the value returned inside it. Same claim, same D2.
    s => s.replace('            const written = writeShapeAtPath(updated, at, val);\n'
                   + '            if (written === null) return;\n'
                   + '            updated = written;',
                   '            writeShapeAtPath(updated, at, val);')],
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
    s => s.replace('let drafted = this.draft !== null && this.draftOf === key ? this.draft : null;',
                   'let drafted = null;')],
  ['the part passes the stored background flag back in, so a fold after the tab opens does nothing',
    s => s.replace('this.render(this._payload, { ...this._opts, background: false });',
                   'this.render(this._payload, this._opts);')],
  ['a draft outlives the document it belongs to, so old text returns after a save',
    s => s.replace('    if (opts.saved) this._forget();', '')],
  // 🔴 C-101 ②. The owner's second sentence: 「테이블이랑 맵퍼 설정은 리스트 좀 나오게해」.
  ['the reference cells lose their catalogue, so every table name is typed by hand',
    s => s.replace('    declared: (section) => named(section || refList),', '    declared: () => [],')],
  ['one list answers for every reference cell, whatever section the skeleton named',
    s => s.replace('named(section || refList)', 'named(refList)')],
  // 🔴 C-101 ③. Five ways one choice stops writing what the operator chose.
  ['the registry`s translation is ignored, so a file function writes the wrong cell',
    s => s.replace('        const spread = group.split(value);', '        const spread = null;')],
  ['the one-cell spelling is left behind, so the document names a mapper twice',
    s => s.replace('            if (val === null) {', '            if (false) {')],
  ['the dropdown cannot say what a two-cell rule holds',
    s => s.replace('        return group.join(held && typeof held === \'object\' ? held : {});',
                   '        return \'\';')],
  ['the only control that can change the mapper is folded behind 「고급」',
    s => s.replace('      const useOne = (Array.isArray(list) && list.length) ? true',
                   '      const useOne = false ? true')],
  ['what is here but not choosable is never drawn, so 「why is my file missing」 has no answer',
    s => s.replace('    if (!this.notes.length || !box || !box.querySelector) return;',
                   '    if (true) return;')],
  // 🔴 C-106. Nine ways the unsaved document stops being visible, defensible or reversible.
  ['the unsaved mark is never drawn',
    s => s.replace('    if (drafted !== null) {\n      const mark', '    if (false) {\n      const mark')],
  ['the shortcut is not the save button but nothing at all',
    s => s.replace("        if (key !== 's' || !(event.ctrlKey || event.metaKey)) return;",
                   '        if (true) return;')],
  ['any key saves, so typing an s in a box writes the file',
    s => s.replace("        if (key !== 's' || !(event.ctrlKey || event.metaKey)) return;",
                   "        if (key !== 's') return;")],
  ['leaving an unsaved document asks nothing',
    s => s.replace('        if (drafted !== null && !this.ask(LEAVE_UNSAVED)) {',
                   '        if (false) {')],
  ['the answer to the question is ignored',
    s => s.replace('        if (drafted !== null && !this.ask(LEAVE_UNSAVED)) {',
                   '        if (drafted !== null && !this.ask(LEAVE_UNSAVED) && false) {')],
  ['the way back does not actually drop the draft',
    s => s.replace('        undo.addEventListener(\'click\', () => { this._forget(); this._again(); });',
                   '        undo.addEventListener(\'click\', () => { this._again(); });')],
  ['a kept draft is never read back, so a refresh loses it again',
    s => s.replace('      const held = this._stored(key);', '      const held = null;')],
  ['a saved document leaves its draft in the browser',
    s => s.replace('    try { this.store.removeItem(this._slot(was)); } catch (e) { /* noqa */ }', '')],
  ['choosing a mapper overwrites parameters the document already holds',
    s => s.replace('        if (getAtPath(held, splitBundlePath(at)) === undefined) extra.push([at, fill[at]]);',
                   '        extra.push([at, fill[at]]);')],
  ['the lines drift back to the end of the form',
    s => s.replace("    const host = (at && box.querySelector(`[data-path=\"${at}\"]`)) || box;",
                   '    const host = box;')],
  ['cancelling a new rule leaves its draft in the browser',
    s => s.replace('          if (this.newMode) this._forget();\n', '')],
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
