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

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
