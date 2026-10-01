/**
 * table_config_user_path -- the table registry walked through `admin.js` ITSELF (lead a2c41fed3):
 * open the tab -> + Add table -> a name box -> paste a sheet -> save; and a picked table as today.
 *
 * WHY THIS EXISTS. `table_config_panel_harness` scores the PANEL and hands it `{forNew: true}`
 * directly, so it went green while the page's own wiring dropped that flag: the table registry's
 * `onOpen` passed the name only, the Add answer came back as a nameless background read, and the
 * template's guard (bb0a488e2) would not draw it. On the screen + Add table opened nothing.
 * The subject here is the PAGE: what it asks for, what it hands the panel, what it sends back.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { NEW_NAME, PICK_NAME } from '../src/raw_registry_panel.js';
import { makeDoc, flush } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ADMIN = path.join(HERE, '..', 'src', 'admin.js');

const TABLES = ['lot_event', 'wafer_map_metadata'];
const DECL = { column_types: { lot: 'string', qty: 'number' }, display_columns: ['lot', 'qty'], business_key: 'lot' };
const SHEET = 'wafer\tat\nstring\tdatetime\nkey\t';

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

// ── the world `admin.js` wakes up in (as chain_rule_user_path builds it) ───────────────────
const doc = makeDoc('light');
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/admin.html', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
};
globalThis.localStorage = globalThis.window.localStorage;
if (!globalThis.navigator.clipboard) {
  Object.defineProperty(globalThis.navigator, 'clipboard',
                        { value: { writeText: async () => {} }, configurable: true });
}

/** Every request the page makes. The registry answers from DECL; a save answers as saved. */
const calls = [];
const isRegistry = (call) => call.url.split('?')[0].endsWith('/admin/tables/config/raw');
const askedTable = (call) => {
  const q = call.url.split('?')[1] || '';
  for (const pair of q.split('&')) {
    const [key, value] = pair.split('=');
    if (key === 'table') return decodeURIComponent(value || '');
  }
  return '';
};
const rawView = (table) => ({
  config_path: '/box/table_config.json', base: 'fp-1', tables: TABLES, error: null, editable_unit: 'table',
  ...(table ? { table, declaration: DECL, raw: JSON.stringify(DECL, null, 2) } : {}),
});
globalThis.fetch = async (url, init) => {
  const call = { url: String(url), method: (init && init.method) || 'GET',
                 body: init && init.body ? JSON.parse(init.body) : null };
  calls.push(call);
  let a = { status: 404, body: null };
  if (call.url.split('?')[0].endsWith('/admin/ledger/relations')) a = { status: 200, body: { missing_relations: [] } };
  else if (isRegistry(call)) {
    a = call.method === 'POST'
      ? { status: 200, body: { table: call.body.table, count: 1, backup: 'box.bak' } }
      : { status: 200, body: rawView(askedTable(call)) };
  }
  return {
    ok: a.status >= 200 && a.status < 300,
    status: a.status,
    json: async () => a.body,
    clone() { return this; },
    text: async () => JSON.stringify(a.body),
  };
};

let mount = null;
const panelRoot = () => (mount && mount.children[0]) || null;
const all = (root, out = []) => {
  if (!root) return out;
  out.push(root);
  for (const kid of root.children || []) all(kid, out);
  return out;
};
const byAttr = (key, value) => all(panelRoot()).find(
  (el) => el.attrs && el.attrs[key] != null && (value === undefined || el.attrs[key] === value)) || null;
const byCls = (cls) => all(panelRoot()).find(
  (el) => String(el.className || '').split(/\s+/).includes(cls)) || null;
// A mutant must fail the walk, not throw it: a missing control reads as a failed assertion.
const press = (action) => {
  const btn = byAttr('data-action', action);
  if (btn) btn.dispatch('click', {});
  return Boolean(btn);
};
const chosen = () => {
  const picker = byAttr('data-picker');
  const on = picker ? picker.children.filter((o) => o.getAttribute('selected')) : [];
  return on.length === 1 ? on[0].value : `${on.length} selected`;
};
const chosenWord = () => {
  const picker = byAttr('data-picker');
  const on = picker ? picker.children.filter((o) => o.getAttribute('selected')) : [];
  return on.length === 1 ? on[0].textContent : '';
};
const offOf = (cls) => { const el = byCls(cls); return el ? Boolean(el.disabled) : 'missing'; };
const settle = async () => { await flush(); await flush(); await flush(); };
const reads = () => calls.filter((c) => c.method === 'GET' && isRegistry(c));
const posts = () => calls.filter((c) => c.method === 'POST' && isRegistry(c));

const loadAdmin = (tag, mutate) => loadWithProbe(ADMIN, { tag, mutate, expose: ['refreshTableConfig'] });

function freshPage() {
  doc.body.children.length = 0;
  const m = doc.createElement('div');
  m.setAttribute('id', 'table-config-mount');
  doc.body.appendChild(m);
  const c = doc.createElement('span');
  c.setAttribute('id', 'table-config-count');
  doc.body.appendChild(c);
  mount = m;
}

async function suite(probe) {
  const before = { pass, fail };
  freshPage();
  const refreshTableConfig = probe.probe.refreshTableConfig;
  ok(typeof refreshTableConfig === 'function', 'A admin.js imports, and its table seating code is reachable');

  // ── A. the tab opens: nothing picked ───────────────────────────────────────────────────
  calls.length = 0;
  await refreshTableConfig();
  await settle();
  ok(Boolean(panelRoot()) && chosen() === PICK_NAME, `A the panel is seated, nothing picked (${chosen()})`);

  // ── B. + Add table from the first screen ───────────────────────────────────────────────
  calls.length = 0;
  ok(press('add-table-config'), 'B the add control is there');
  await settle();
  ok(reads().length === 1 && askedTable(reads()[0]) === '',
     `B Add asks once, naming no table (${reads().map((c) => c.url).join(' ')})`);
  ok(Boolean(byAttr('data-new-name')), 'B a name box stands');
  ok(chosen() === NEW_NAME && chosenWord() === '(new table)',
     `B the picker marks a new name, in the table registry's word (${chosen()} / ${chosenWord()})`);
  const added = ['table-config-paste', 'table-config-copy', 'table-config-save', 'table-config-raw'].map(offOf);
  ok(JSON.stringify(added) === '[false,false,false,false]', `B paste, Copy, Save and the raw box are on (${added})`);

  // ── C. paste a sheet, name it, save: the body carries the name and no from ─────────────
  const sink = byCls('table-config-paste');
  if (sink) sink.dispatch('paste', { clipboardData: { getData: () => SHEET }, preventDefault() {} });
  await settle();
  let pasted = null;
  try { pasted = JSON.parse((byCls('table-config-raw') || {}).value || 'null'); } catch (e) { pasted = null; }
  ok(Boolean(pasted) && JSON.stringify(Object.keys(pasted.column_types || {})) === '["wafer","at"]'
     && pasted.business_key === 'wafer', `C the paste is the document (${JSON.stringify(pasted)})`);
  const nameBox = byAttr('data-new-name');
  if (nameBox) nameBox.value = 'new_table';
  calls.length = 0;
  ok(press('save-table-config'), 'C the save control is there');
  await settle();
  const sent = posts()[0] || null;
  ok(posts().length === 1 && sent.body.table === 'new_table' && sent.body.base === 'fp-1'
     && JSON.stringify(Object.keys((sent.body.declaration || {}).column_types || {})) === '["wafer","at"]',
     `C one save: the typed name, the base, the pasted columns (${sent ? JSON.stringify(sent.body) : 'no save'})`);
  ok(Boolean(sent) && !('from' in sent.body), `C and no from - a new table opened nothing (${sent ? Object.keys(sent.body) : '-'})`);

  // ── D. a picked table, as today (same page: admin.js holds one panel on the mount it first found) ──
  calls.length = 0;
  const picker = byAttr('data-picker');
  if (picker) picker.dispatch('change', { target: { value: 'lot_event' } });
  await settle();
  ok(reads().length === 1 && askedTable(reads()[0]) === 'lot_event',
     `D picking asks once, naming the table (${reads().map((c) => c.url).join(' ')})`);
  let opened = null;
  try { opened = JSON.parse((byCls('table-config-raw') || {}).value || 'null'); } catch (e) { opened = null; }
  ok(JSON.stringify(opened) === JSON.stringify(DECL) && chosen() === 'lot_event',
     `D the raw box holds that table, and the picker names it (${chosen()})`);
  calls.length = 0;
  press('save-table-config');
  await settle();
  const resent = posts()[0] || null;
  ok(posts().length === 1 && resent.body.table === 'lot_event' && resent.body.from === 'lot_event'
     && resent.body.base === 'fp-1', `D its save carries the name, from and the base (${resent ? JSON.stringify(resent.body) : 'no save'})`);

  // ── E. + Add table from a picked table (this one did not open before 09-29 either) ─────
  calls.length = 0;
  press('add-table-config');
  await settle();
  ok(Boolean(byAttr('data-new-name')) && chosen() === NEW_NAME,
     `E Add from a picked table: a name box, the picker says a new name (${chosen()})`);

  return { pass: pass - before.pass, fail: fail - before.fail };
}

if (process.argv[2] === '--quiet') quiet = true;

console.log('-- the real page ---------------------------------------------------');
const base = await suite(await loadAdmin('real'));

// -- mutants: written against admin.js's own text, because the page is the subject ---------
const DEFECTS = [
  // lead a2c41fed3's mutant: the shape that kept + Add table shut.
  ['the table registry hands Add only the name',
    s => s.replace('      onOpen: (name, extra) => refreshTableConfig(name, extra || {}),',
                   '      onOpen: (name) => refreshTableConfig(name),')],
  ['the read forgets which table was chosen',
    s => s.replace('    const qs = table ? `?table=${encodeURIComponent(table)}` : \'\';', '    const qs = \'\';')],
  ['the save forgets the base fingerprint',
    s => s.replace('      body: JSON.stringify({ table, declaration, base, from }),',
                   '      body: JSON.stringify({ table, declaration, from }),')],
];
const CONTROLS = [
  ['a comment removed', s => s.replace(
    '      // 400 은 detail 안에 code·path·message 를 실어 보냅니다. 그대로 그립니다.\n', '')],
];

const escaped = [];
let caughtN = 0;
let controlsCaught = 0;
let tag = 0;
console.log('');
console.log('-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, mutate] of DEFECTS) {
  quiet = true;
  const delta = await suite(await loadAdmin(`d${tag += 1}`, mutate));
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) caughtN += 1; else escaped.push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  quiet = true;
  const delta = await suite(await loadAdmin(`c${tag += 1}`, mutate));
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} ${name}`);
}

// The real run is the verdict; a mutant that reddens is the harness working.
const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.pass} passed, ${base.fail} failed; ${caughtN}/${DEFECTS.length} defects caught, `
  + `${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
if (base.fail) console.log('FAILED: ' + failedNames.slice(0, base.fail).join(' | '));
if (base.fail || badScore) process.exitCode = 1;
