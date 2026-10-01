// TABLE CONFIG — 표 등록이 제품 «안»으로 들어왔는지, 그리고 그 자리가 거짓말을 안 하는지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). No DOM and no CSS
// at module scope, so it imports in node as it stands.
//
// 🔴 THE TWO THIS FILE EXISTS FOR:
//   ① `base` SURVIVES THE ROUND TRIP. The save sends back the fingerprint the open handed
//      over; drop it and two operators editing the same file silently erase each other,
//      which is the guard the server made part of the ruling.
//   ② A REFUSAL KEEPS THE SERVER'S WORDS. Five codes, each with its own sentence and
//      address; this screen writes none of them and translates none of them.
//
// Run: node client2/tests/table_config_panel_harness.mjs
import { tableConfigView, TableConfigPanel } from '../src/table_config_panel.js';
import { ABSENT } from '../src/absent.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null), _text: '', value: '',
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    addEventListener(type, fn) { (this._on ||= {})[type] = fn; },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: t => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (host, cls) => walk(host)
  .filter(n => String(n.className || '').split(/\s+/).includes(cls));
const byTag = (host, tag) => walk(host).filter(n => n.tagName === tag);

const PAYLOAD = {
  config_path: '/data/config/table_config.json',
  base: 'sha256:abc',
  tables: ['lot_event', 'wafer_map_metadata'],
  error: null,
  editable_unit: 'table',
  table: 'lot_event',
  declaration: { key_columns: ['lot'] },
  raw: '{\n  "key_columns": ["lot"]\n}',
};

// ═══ ① the fingerprint survives ════════════════════════════════════════════════════
console.log('\n[1] the base a save must hand back');
{
  const v = tableConfigView(PAYLOAD);
  eq('the view carries the fingerprint', v.base, 'sha256:abc');
  const doc = makeDoc();
  const host = doc.createElement('div');
  let sent = null;
  new TableConfigPanel(host, { doc, onSave: (p) => { sent = p; } }).render(PAYLOAD);
  const root = byClass(host, 'table-config-panel')[0];
  eq('and hangs it where the save can read it', root.getAttribute('data-base'), 'sha256:abc');
  eq('...beside the table it belongs to', root.getAttribute('data-table'), 'lot_event');
  // 🔴 the round trip: press save, and what leaves must be the fingerprint that arrived
  byClass(host, 'table-config-save')[0]._on.click();
  eq('a save sends back the SAME fingerprint', sent && sent.base, 'sha256:abc');
  eq('...for the same table', sent && sent.table, 'lot_event');
  ok('...and the text the operator has, not a re-serialisation',
    sent && sent.raw === PAYLOAD.raw, JSON.stringify(sent && sent.raw));
}

// ═══ ② a refusal keeps the server's words ══════════════════════════════════════════
console.log('\n[2] five refusals, none of them written here');
{
  for (const [code, path, message] of [
    ['stale_base', 'base', '이 파일이 열어 본 뒤에 바뀌었습니다. 다시 열어 확인한 뒤 저장하십시오'],
    ['declaration_not_object', 'tables.lot_event', '표 등록은 JSON 객체여야 합니다'],
    ['table_name_required', 'table', '저장할 표 이름이 없습니다'],
  ]) {
    const doc = makeDoc();
    const host = doc.createElement('div');
    new TableConfigPanel(host, { doc }).render(PAYLOAD, { refusal: { code, path, message } });
    const box = byClass(host, 'table-config-refusal')[0];
    ok(`${code} keeps its code`, box && box.getAttribute('data-code') === code);
    ok(`${code} keeps its address`, box && box.textContent.includes(path));
    ok(`${code} keeps the server's sentence, verbatim`, box && box.textContent.includes(message));
  }
  // ⚠️ an absent field draws no element rather than an empty one
  const doc = makeDoc();
  const host = doc.createElement('div');
  new TableConfigPanel(host, { doc }).render(PAYLOAD, { refusal: { message: 'x' } });
  eq('a refusal with no code draws no code line', byClass(host, 'table-config-refusal-code').length, 0);
  eq('...and no path line', byClass(host, 'table-config-refusal-path').length, 0);
  ok('...but the sentence is still there', host.textContent.includes('x'));
  // and no refusal at all draws no box
  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new TableConfigPanel(host2, { doc: doc2 }).render(PAYLOAD);
  eq('no refusal, no box', byClass(host2, 'table-config-refusal').length, 0);
}

// ═══ ③ the names are offered, not memorised ════════════════════════════════════════
console.log('\n[3] the operator chooses rather than remembers');
{
  const doc = makeDoc();
  const host = doc.createElement('div');
  let opened = null;
  new TableConfigPanel(host, { doc, onOpen: (t) => { opened = t; } }).render(PAYLOAD);
  const picker = byClass(host, 'table-config-picker')[0];
  eq('every declared table is offered', byTag(picker, 'OPTION').map(o => o.textContent),
    ['lot_event', 'wafer_map_metadata']);
  eq('the open one is marked', byTag(picker, 'OPTION')
    .filter(o => o.getAttribute('selected')).map(o => o.textContent), ['lot_event']);
  picker._on.change({ target: { value: 'wafer_map_metadata' } });
  eq('picking one asks for it by name', opened, 'wafer_map_metadata');
  eq('the count is the number offered', tableConfigView(PAYLOAD).count, '2');
}

// ═══ ④ 「못 읽었다」 is not 「없다」 ═════════════════════════════════════════════════
console.log('\n[4] unreadable is not empty');
{
  const broken = tableConfigView({ config_path: '/x', error: 'JSONDecodeError: line 3', tables: [] });
  eq('an unreadable file is not available', broken.available, false);
  ok('...and says what the server said', /JSONDecodeError/.test(broken.reason), broken.reason);
  eq('...and its count is a dash, not 0', broken.count, ABSENT);
  // the other half: a file that WAS read and holds nothing
  const emptyRead = tableConfigView({ config_path: '/x', error: null, tables: [] });
  eq('a readable empty file IS available', emptyRead.available, true);
  eq('...and counts 0', emptyRead.count, '0');
  ok('the two are different states', broken.available !== emptyRead.available);

  const doc = makeDoc();
  const host = doc.createElement('div');
  new TableConfigPanel(host, { doc }).render(null, { unavailable: 'HTTP 401' });
  ok('a failed fetch says so', /HTTP 401/.test(host.textContent));
  eq('...and offers no picker', byClass(host, 'table-config-picker').length, 0);
  eq('...and no save', byClass(host, 'table-config-save').length, 0);
}

// ═══ ⑤ 조립식 ══════════════════════════════════════════════════════════════════════
console.log('\n[5] two panels on one page');
{
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  const p1 = new TableConfigPanel(h1, { doc });
  const p2 = new TableConfigPanel(h2, { doc });
  p1.render(PAYLOAD);
  p2.render({ ...PAYLOAD, table: 'wafer_map_metadata', base: 'sha256:zzz' });
  eq('the first keeps its own fingerprint',
    byClass(h1, 'table-config-panel')[0].getAttribute('data-base'), 'sha256:abc');
  eq('the second keeps its own',
    byClass(h2, 'table-config-panel')[0].getAttribute('data-base'), 'sha256:zzz');
  p1.render(PAYLOAD);
  eq('a re-render replaces rather than appends', byClass(h1, 'table-config-save').length, 1);
}

// ═══ ⑥-⑨ paste columns from a sheet (lead f382dacfb) ══════════════════════════════════
//
// 🔴 THE PANEL IS BUILT AS `TableConfigPanel` BUILDS IT: the template with this registry's
//    declaration (`super(mount, deps, TABLE_REGISTRY)` and nothing else), so a mutated template
//    or a mutated registry is the thing scored - a probe stub cannot stand in for a class.
const PASTE_PAYLOAD = {
  ...PAYLOAD,
  declaration: { __comment: 'c', column_types: { lot: 'string', gone: 'number', qty: 'string' },
                 display_columns: ['lot', 'gone', 'qty'], business_key: 'lot' },
  raw: '{"__comment":"c","column_types":{"lot":"string","gone":"number","qty":"string"},'
    + '"display_columns":["lot","gone","qty"],"business_key":"lot"}',
};
const CHAIN_PAYLOAD = { config_path: '/x/chain_rules.json', base: 'sha256:c', rules: ['r1'], error: null,
  name: 'r1', declaration: { name: 'r1' }, raw: '{"name":"r1"}' };
const SHEET = (...rows) => rows.map((r) => r.join('\t')).join('\n');

async function pasteSuite(m) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  const read = (rows, held = null) => m.columnsFromPaste(rows, held);
  const panel = (deps = {}) => {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const p = new m.Panel(host, { doc, storage: null, ...deps }, m.TABLE_REGISTRY);
    return { host, p };
  };
  const pasteInto = (host, text) => {
    const sink = byClass(host, 'table-config-paste')[0];
    if (sink && sink._on && sink._on.paste) {
      sink._on.paste({ clipboardData: { getData: () => text }, preventDefault() {} });
    }
    return Boolean(sink);
  };
  const rawOf = (host) => { try { return JSON.parse(byClass(host, 'table-config-raw')[0].value); } catch (e) { return null; } };
  const lines = (host, cls) => byClass(host, cls).map((n) => n.textContent);

  console.log('\n[6] a sheet read into columns');
  {
    const two = read([['lot', 'qty', 'at'], ['string', 'number', 'datetime']]);
    say('A1 two rows: column_types and display_columns in the pasted order, no key',
      JSON.stringify(two.next && two.next.column_types) === '{"lot":"string","qty":"number","at":"datetime"}'
        && JSON.stringify(two.next.display_columns) === '["lot","qty","at"]'
        && !('business_key' in two.next) && !('composite_key_source' in two.next), JSON.stringify(two));
    const one = read([['lot', 'qty'], ['string', 'number'], ['key', '']]);
    say('A2 one key -> business_key', one.next && one.next.business_key === 'lot'
      && !('composite_key_source' in one.next), JSON.stringify(one.next));
    const many = read([['lot', 'qty', 'slot'], ['string', 'number', 'string'], ['key', '', 'key']]);
    say('A3 two keys -> composite_key_source, left to right', JSON.stringify(many.next && many.next.composite_key_source)
      === '["lot","slot"]' && !('business_key' in many.next), JSON.stringify(many.next));
    const bad = [
      [read([['lot', 'qty'], ['string', 'num']]), 'column 2 (qty): unknown type num'],
      [read([['lot', '', 'x'], ['string', 'number', 'string']]), 'column 2: no name'],
      [read([['lot', 'qty', 'lot'], ['string', 'number', 'string']]), 'column 3 (lot): name repeated'],
      [read([['lot', 'qty'], ['string', 'number'], ['yes', '']]), 'column 1 (lot): yes is not key'],
    ];
    say('A4 an unknown type, a blank name, a repeat and a word other than key are refused by name',
      bad.every(([got, want]) => got.next === null && got.refused.includes(want)),
      JSON.stringify(bad.map(([got]) => got.refused)));
    const held = { __comment: 'c', column_types: { old: 'string' }, display_columns: ['old'],
      business_key: 'old', map_key_columns: ['x'] };
    const swap = read([['lot', 'qty'], ['string', 'number']], held);
    say('A5 an existing table: the columns are replaced whole, other fields and (no key row) the key stay',
      swap.next && JSON.stringify(Object.keys(swap.next.column_types)) === '["lot","qty"]'
        && swap.next.__comment === 'c' && JSON.stringify(swap.next.map_key_columns) === '["x"]'
        && swap.next.business_key === 'old', JSON.stringify(swap.next));
    const blankMarks = read([['lot', 'qty'], ['string', 'number'], ['', '']], held);
    say('A6 a key row with nothing marked is no key row', blankMarks.next && blankMarks.next.business_key === 'old',
      JSON.stringify(blankMarks.next));
    const empty = read([], held);
    say('A7 nothing pasted is refused - it would write no columns over every column', empty.next === null
      && JSON.stringify(empty.refused) === '["Nothing pasted"]', JSON.stringify(empty));
    const cased = read([['lot', 'qty', 'at'], ['String', 'NUMBER', 'DateTime'], ['KEY', '', '']]);
    say('A8 type and key words in any case are read, and written as the server spells them',
      cased.next && JSON.stringify(cased.next.column_types) === '{"lot":"string","qty":"number","at":"datetime"}'
        && cased.next.business_key === 'lot', JSON.stringify(cased));
  }

  console.log('\n[7] what a save changes, said before it');
  {
    say('B1 a table that does not exist yet has nothing to lose', m.columnChanges(null, { column_types: { a: 'string' } }).length === 0);
    const got = m.columnChanges(
      { column_types: { lot: 'string', gone: 'number', qty: 'string' }, business_key: 'lot' },
      { column_types: { lot: 'string', qty: 'number' }, composite_key_source: ['lot', 'qty'] });
    say('B2 dropped, retyped, the key, and the rows\' identity',
      JSON.stringify(got) === JSON.stringify(['Dropped · gone', 'Type · qty · string → number',
        'Key · lot → lot + qty', 'Existing rows change identity']), JSON.stringify(got));
    const spelling = m.columnChanges({ business_key: 'k', composite_key_source: ['a', 'b'] },
      { composite_key_source: ['a', 'b'] });
    say('B3 a key spelling that keeps the same identity says the key, not the identity',
      JSON.stringify(spelling) === JSON.stringify(['Key · k (a + b) → a + b']), JSON.stringify(spelling));
  }

  console.log('\n[8] the panel');
  {
    const { host, p } = panel();
    p.render(PASTE_PAYLOAD);
    const drawn = pasteInto(host, SHEET([' lot ', ' qty'], ['string ', 'number']) + '\n\n');
    const doc1 = rawOf(host);
    say('C1 the paste box reads the sheet through the grid\'s reader (padded cells, a blank line)',
      drawn && doc1 && JSON.stringify(doc1.column_types) === '{"lot":"string","qty":"number"}'
        && byClass(host, 'table-config-unsaved').length === 1, JSON.stringify(doc1));

    const asked = [];
    let sent = null;
    const { host: h2, p: p2 } = panel({ confirm: (text) => { asked.push(text); return false; }, onSave: (s) => { sent = s; } });
    p2.render(PASTE_PAYLOAD);
    pasteInto(h2, SHEET(['lot', 'qty'], ['string', 'number'], ['', 'key']));
    const shown = lines(h2, 'table-config-paste-change');
    say('C2 before saving, the screen says what goes: the dropped column, the type, the key, the identity',
      JSON.stringify(shown) === JSON.stringify(['Dropped · gone', 'Type · qty · string → number',
        'Key · lot → qty', 'Existing rows change identity']), JSON.stringify(shown));
    byClass(h2, 'table-config-save')[0]._on.click();
    say('C3 Save asks first, with those lines, and a No sends nothing',
      asked.length === 1 && asked[0].includes('Dropped · gone') && sent === null, JSON.stringify({ asked, sent }));

    let sent2 = null;
    const { host: h3, p: p3 } = panel({ confirm: () => true, onSave: (s) => { sent2 = s; } });
    p3.render(PASTE_PAYLOAD);
    pasteInto(h3, SHEET(['lot', 'qty'], ['string', 'number'], ['', 'key']));
    byClass(h3, 'table-config-save')[0]._on.click();
    let saved = null;
    try { saved = JSON.parse(sent2 && sent2.raw); } catch (e) { saved = null; }
    say('C4 a Yes saves through the one save, the table replaced whole',
      saved && JSON.stringify(saved.column_types) === '{"lot":"string","qty":"number"}'
        && saved.business_key === 'qty' && saved.__comment === 'c' && sent2.table === 'lot_event', JSON.stringify(sent2));

    const { host: h4, p: p4 } = panel();
    p4.render(PASTE_PAYLOAD);
    pasteInto(h4, SHEET(['lot', 'qty'], ['string', 'integer']));
    const refusedLines = lines(h4, 'table-config-paste-refused');
    say('C5 a refused paste says why and leaves the document as the server has it',
      JSON.stringify(refusedLines) === JSON.stringify(['column 2 (qty): unknown type integer'])
        && byClass(h4, 'table-config-unsaved').length === 0
        && JSON.stringify(rawOf(h4)) === JSON.stringify(PASTE_PAYLOAD.declaration), JSON.stringify(refusedLines));

    const asked6 = [];
    let sent6 = null;
    const { host: h6, p: p6 } = panel({ confirm: (t) => { asked6.push(t); return true; }, onSave: (s) => { sent6 = s; },
      onOpen: () => {} });
    p6.render(PASTE_PAYLOAD);
    byClass(h6, 'table-config-add')[0]._on.click();
    p6.render({ ...PASTE_PAYLOAD, table: undefined, declaration: undefined, raw: undefined }, { forNew: true });
    pasteInto(h6, SHEET(['wafer', 'at'], ['string', 'datetime'], ['key', '']));
    const nameBox = byClass(h6, 'table-config-new-name')[0];
    if (nameBox) nameBox.value = 'new_table';
    byClass(h6, 'table-config-save')[0]._on.click();
    let saved6 = null;
    try { saved6 = JSON.parse(sent6 && sent6.raw); } catch (e) { saved6 = null; }
    say('C6 a new table: the paste fills it, nothing is asked, and it saves under its name',
      asked6.length === 0 && sent6 && sent6.table === 'new_table' && saved6
        && JSON.stringify(saved6.display_columns) === '["wafer","at"]' && saved6.business_key === 'wafer',
      JSON.stringify({ asked6, sent6 }));

    const { host: h7, p: p7 } = panel();
    p7.render(PASTE_PAYLOAD, { saved: { name: 'lot_event', count: 1, backup: 'b.bak' } });
    pasteInto(h7, SHEET(['lot', 'qty'], ['string', 'number']));
    say('C7 a paste right after a save is kept, not dropped with the save\'s line',
      byClass(h7, 'table-config-unsaved').length === 1
        && JSON.stringify(Object.keys((rawOf(h7) || {}).column_types || {})) === '["lot","qty"]');

    const { host: h8, p: p8 } = panel();
    p8.render(PASTE_PAYLOAD);
    pasteInto(h8, SHEET(['lot', 'qty'], ['string', 'number']));
    p8.render(PASTE_PAYLOAD, { refusal: { code: 'stale_base', path: 'base', message: 'Reopen it, check, then save' } });
    const refusal = byClass(h8, 'table-config-refusal')[0];
    say('C8 the server\'s refusal of that save stands in its own words, the pasted text still there',
      refusal && refusal.textContent.includes('Reopen it, check, then save')
        && JSON.stringify(Object.keys((rawOf(h8) || {}).column_types || {})) === '["lot","qty"]');

    // 🔴 THE DATA GUARD KEPT BY RULING (lead c6a8c069c, ba5e1eaad): an empty paste must not reach the
    //    document. The lead's mutation deleting it stayed green - nothing measured it.
    const asked9 = [];
    let sent9 = null;
    const { host: h9, p: p9 } = panel({ confirm: (t) => { asked9.push(t); return true; }, onSave: (s) => { sent9 = s; } });
    p9.render(PASTE_PAYLOAD);
    pasteInto(h9, '\n\n');
    const refused9 = lines(h9, 'table-config-paste-refused');
    byClass(h9, 'table-config-save')[0]._on.click();
    let sent9doc = null;
    try { sent9doc = JSON.parse(sent9 && sent9.raw); } catch (e) { sent9doc = null; }
    say('C9 an empty paste: the refusal line, the document as the server has it, and a Save after it sends every column, asking nothing',
      JSON.stringify(refused9) === '["Nothing pasted"]' && byClass(h9, 'table-config-unsaved').length === 0
        && JSON.stringify(rawOf(h9)) === JSON.stringify(PASTE_PAYLOAD.declaration) && asked9.length === 0
        && JSON.stringify(sent9doc) === JSON.stringify(PASTE_PAYLOAD.declaration),
      JSON.stringify({ refused9, asked9, sent9doc }));
  }

  console.log('\n[9] the chain rules screen is not touched');
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    new m.Panel(host, { doc, storage: null }, m.CHAIN_RULE_REGISTRY).render(CHAIN_PAYLOAD);
    const { host: tableHost, p } = panel();
    p.render(PASTE_PAYLOAD);
    const pasteNodes = (h) => walk(h).filter((n) => /-paste/.test(String(n.className || ''))).length;
    say('D1 the chain registry draws no paste box (the table one does)',
      pasteNodes(host) === 0 && pasteNodes(tableHost) > 0, `${pasteNodes(host)} ${pasteNodes(tableHost)}`);
  }
  return { ran: names.length, names, failures: fails };
}

{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const { fileURLToPath } = await import('node:url');
  const pathMod = await import('node:path');
  const HERE = pathMod.dirname(fileURLToPath(import.meta.url));
  const REGISTRY = pathMod.join(HERE, '..', 'src', 'table_config_panel.js');
  const TEMPLATE = pathMod.join(HERE, '..', 'src', 'raw_registry_panel.js');
  const registry = await import('../src/table_config_panel.js');
  const template = await import('../src/raw_registry_panel.js');
  const chain = await import('../src/chain_rule_panel.js');
  const real = { ...registry, Panel: template.RawRegistryPanel, CHAIN_RULE_REGISTRY: chain.CHAIN_RULE_REGISTRY };
  const base = await pasteSuite(real);
  pass += base.ran - base.failures.length;
  failures.push(...base.failures);
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const R = (id, what, catches, from, to) => ({ id, what, catches, file: REGISTRY, from, to });
  const T = (id, what, catches, from, to) => ({ id, what, catches, file: TEMPLATE, from, to });
  const MUTANTS = [
    R('P1', 'composite keys are written right to left', 'A3',
      '    else next.composite_key_source = keys;\n', '    else next.composite_key_source = keys.slice().reverse();\n'),
    R('P2', 'one key is written as a composite', 'A2',
      '    if (keys.length === 1) [next.business_key] = keys;\n', '    if (false) [next.business_key] = keys;\n'),
    R('P3', 'an unknown type is accepted', 'A4',
      '    if (!COLUMN_TYPES.includes(word(types[i]))) refused.push(', '    if (false) refused.push('),
    R('P4', 'a repeated name is accepted', 'A4',
      '    if (seen.has(name)) refused.push(', '    if (false) refused.push('),
    R('P5', 'no key row still rewrites the key', 'A5',
      '  if (keyRow) {\n', '  if (true) {\n'),
    R('P6', 'a dropped column is not said', 'B2',
      '  if (dropped.length) lines.push(', '  if (false) lines.push('),
    R('P7', 'a key spelling is said as an identity change', 'B3',
      '  if (identityOf(before) !== identityOf(now)) lines.push(', '  if (keyText(before) !== keyText(now)) lines.push('),
    R('P8', 'the table registry declares no paste', 'C1',
      '  paste: Object.freeze({ read: columnsFromPaste, changes: columnChanges }),\n', ''),
    T('P9', 'Save does not ask', 'C3',
      "        if (lines.length && !this.ask([...lines, 'Save?'].join('\\n'))) return;\n", ''),
    T('P10', 'every registry draws a paste box', 'D1',
      '    if (spec.paste && picked) this._drawPaste(key, payload);\n', '    if (picked) this._drawPaste(key, payload);\n'),
    T('P11', 'the paste is read by a private split, not the grid\'s reader', 'C1',
      "parseTsv(String(text || ''), { trimCells: true, dropBlankLines: true })",
      "String(text || '').split('\\n').map((line) => line.split('\\t'))"),
    T('P12', 'the paste redraw keeps the last save\'s line', 'C7',
      '    this.render(this._payload, { ...this._opts, background: false, saved: null });\n', '    this._again();\n'),
    T('P13', 'what a save changes is worked out against the draft', 'C2',
      '    const before = this.newMode ? null : (payload && payload.declaration);\n',
      "    const before = this.newMode ? null : JSON.parse(this.draft || 'null');\n"),
    R('P14', 'the empty-paste guard is gone (lead ba5e1eaad)', 'A7',
      "  if (!width) return { next: null, refused: ['Nothing pasted'] };\n", ''),
    R('P15', 'a type is written as typed, not as the server spells it', 'A8',
      '[name, word(types[i])]', '[name, String(types[i])]'),
    R('P16', 'a type or key word is read in lower case only', 'A8',
      "String(cell).toLowerCase());", 'String(cell));'),
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => {
    const loaded = (await loadWithProbe(mu.file, { mutate: (t) => swap(t, mu.from, mu.to) })).module;
    const mods = mu.file === REGISTRY ? { ...real, ...loaded } : { ...real, Panel: loaded.RawRegistryPanel };
    const quiet = console.log;
    console.log = () => {};
    try { return await pasteSuite(mods); } finally { console.log = quiet; }
  }, { baselineRan: base.ran, baselineNames: base.names,
       title: '\n  [6-9] mutants - each must be caught by the check it names.' });
  pass += MUTANTS.length - scored.wrong;
  for (let i = 0; i < scored.wrong; i += 1) failures.push(`paste mutant verdict ${i + 1}`);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
