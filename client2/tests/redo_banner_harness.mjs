// redo_banner_harness — THE LINES RUN, AND THE FILE STILL KNOWS NO ROUTE.
//
// The re-translate moved out of the right-click menu and into the header, because selection
// happens in the grid and a menu that grows with it is what the owner objected to twice. The
// ruling that shaped the first version was option A: assemble here, run in admin. THAT RULING
// IS OVERTURNED (owner, 2026-09-01) — a line is pressed and it runs where it was pressed.
//
// 🔴 SO THE SHARPEST CHECK IN HERE IS STILL ABOUT WHAT THE FILE DOES NOT CONTAIN. It may ASK
// whether a token exists; it may never read one, and it may not know a route. Running is one
// injected function. That is what lets this harness score the whole feature with a fake, and
// it is why gate ⑥ could ask for no real token in here.
//
// 🔴 SOURCE IS THE PART PLUS `dropdown.js`, because that is what actually runs. The dismiss
// behaviour moved there when the filter strip became the second thing needing it, and a harness
// that kept reading one file would have gone quiet on the two mutants that live in the other —
// which is the same as not having them.
//
// The second is that the two buttons group in DIFFERENT PLACES. The ledger's groups come from
// the declaration this page already has, so they are assembled here. The chain's groups are one
// per rule and the rule list is behind the token, so this page hands over the keys and lets
// admin group them. A part that grouped both here would have to call a gated route.
//
// Every check is paired with a mutant; two controls must escape.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'redo_banner.js');
const DROPDOWN_PATH = join(HERE, '..', 'src', 'dropdown.js');
// The direction of this panel is a STYLESHEET fact, and a stub document has no layout to
// measure it with. What can be scored here is that the tag was not left to decide it.
const STYLE_PATH = join(HERE, '..', 'src', 'style.css');
const read = (p) => readFileSync(p, 'utf8').replace(/\r\n/g, '\n');
// The dependency is INLINED, not stubbed: `load()` evaluates a plain script, so an import
// statement would not survive it -- and a stub would score a dismiss that is not the one
// shipping. Two of the mutants live in that file now.
const SOURCE = read(DROPDOWN_PATH) + '\n'
  + read(SRC_PATH).replace(/^import .*$/gm, '');

let passed = 0;
let failed = 0;

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

function ok(what, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${what}`); return; }
  failed++;
  console.log(`  FAIL ${what}${saw === undefined ? '' : `  -- saw ${JSON.stringify(saw)}`}`);
}

// ── a bare document, so nothing here can lean on a real DOM ─────────────────────────
function mkDoc() {
  // Document-level listeners, because outside-click and Escape are how this dropdown closes
  // and neither can be scored through the part's own DOM. `removeEventListener` is modelled
  // too: a stub that only ever adds cannot tell a part that detaches from one that leaks.
  const listeners = {};
  const el = (tag) => {
    const node = {
      tagName: String(tag).toUpperCase(), children: [], className: '',
      dataset: {}, disabled: false, type: '', handlers: {}, parentNode: null,
      appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
      setAttribute(k, v) { this.dataset[k] = String(v); },
      addEventListener(name, fn) { this.handlers[name] = fn; },
      click() { if (this.handlers.click) this.handlers.click(); },
    };
    // 🔴 `textContent = ''` CLEARS CHILDREN in a real document, and this part relies on
    // that to redraw. A stub that only stores the string lets every render pile up, which showed
    // as four buttons where two were asserted -- an instrument fault that looks exactly like a
    // double-render defect. Modelled here so the stub cannot invent one or hide one.
    let text = '';
    Object.defineProperty(node, 'textContent', {
      get() { return text || node.children.map((k) => k.textContent).join(''); },
      set(v) { text = String(v); if (text === '') node.children.length = 0; },
      configurable: true,
    });
    return node;
  };
  return {
    createElement: el,
    addEventListener(name, fn) { (listeners[name] = listeners[name] || []).push(fn); },
    removeEventListener(name, fn) {
      const list = listeners[name] || [];
      const at = list.indexOf(fn);
      if (at !== -1) list.splice(at, 1);
    },
    listenerCount() {
      return Object.keys(listeners).reduce((n, k) => n + listeners[k].length, 0);
    },
    fire(name, event) { (listeners[name] || []).slice().forEach((fn) => fn(event)); },
  };
}

const walk = (node) => (node.children || [])
  .reduce((all, kid) => all.concat([kid], walk(kid)), []);
const byClass = (root, cls) => walk(root)
  .filter((n) => String(n.className || '').split(/\s+/).includes(cls));

function load(src) {
  const sandbox = { Array, String, Object, Number, Boolean, JSON, Promise };
  vm.createContext(sandbox);
  const body = src.replace(/^export /gm, '');
  vm.runInContext(`${body}\nglobalThis.__x = { RedoBanner, ledgerGroups, scopeValuesFor };`,
    sandbox);
  return sandbox.__x;
}

const X = load(SOURCE);
if (!X || !X.RedoBanner) die('redo_banner.js did not evaluate — its exports moved or renamed.');

const SOURCES = [{ relation: 'dt_log', source: 'dt_log_src',
                   scope_columns: ['lot_id', 'wafer_id'] }];
const envelope = (obj) => ({ data: Object.fromEntries(
  Object.entries(obj).map(([k, v]) => [k, { value: v }])) });
const readEnvelope = (row, col) => {
  const cell = row && row.data ? row.data[col] : undefined;
  if (cell && typeof cell === 'object' && 'value' in cell) return cell.value;
  return row ? row[col] : undefined;
};

function build(rows, opts = {}) {
  const doc = mkDoc();
  const host = doc.createElement('div');
  let handed = null;
  const part = new X.RedoBanner(host, {
    doc,
    sources: 'sources' in opts ? opts.sources : SOURCES,
    getSelection: () => rows,
    readValue: opts.readValue || readEnvelope,
    businessKey: 'businessKey' in opts ? opts.businessKey : 'lot_id',
    handOff: (p) => { handed = p; },
  });
  part.setRelation(opts.relation === undefined ? 'dt_log' : opts.relation);
  part.render();
  return { part, host, handed: () => handed };
}

const buttons = (host) => byClass(host, 'redo-banner__btn');
const groupsShown = (host) => byClass(host, 'redo-panel__group').map((n) => n.textContent);
const note = (host) => (byClass(host, 'redo-panel__note')[0] || {}).textContent;
const press = (host, which) => buttons(host).find((b) => b.dataset.redo === which).click();

console.log('\n── A. THE BOUNDARY ─────────────────────────────────────────────────');
{
  // 🔴 The ruling is a property of the FILE, and no rendered output can show it.
  const stripped = SOURCE.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n');
  ok('A1 the part never names an admin route', !stripped.includes('/admin/'), stripped.length);
  ok('A2 ... and never fetches at all', !/\bfetch\s*\(/.test(stripped));
  // 🔴 The boundary MOVED on 2026-09-02: the part runs now, so it must ask whether a token
  //    exists. What it must never do is READ one. Asserting the absence of the word would now
  //    fail on `hasToken()`, and relaxing it to nothing would leave the real rule unguarded.
  ok('A3 ... and never reads a token value, it only asks whether there is one',
    !/localStorage|sessionStorage|X-Admin-Token|Authorization|getItem/i.test(stripped),
    stripped.length);
  ok('A4 ... and the asking is a call to something injected, not a value it keeps',
    /this\.hasToken\(\)/.test(stripped)
    && /this\.hasToken = options\.hasToken/.test(stripped), stripped.length);
}

console.log('\n── B. THE BUTTONS ──────────────────────────────────────────────────');
{
  const empty = build([]);
  ok('B1 with nothing selected both buttons are dead',
    buttons(empty.host).length === 2 && buttons(empty.host).every((b) => b.disabled === true),
    buttons(empty.host).map((b) => b.disabled));
  const chosen = build([envelope({ lot_id: 'L1', wafer_id: 'W1' })]);
  ok('B2 selecting a row brings both to life',
    buttons(chosen.host).every((b) => b.disabled === false),
    buttons(chosen.host).map((b) => b.disabled));
  // 🔴 THE DISCRIMINATING PAIR: on a table the declaration does not name, "nothing selected"
  //    and "not a ledger source" must not paint the same. The ledger button is ABSENT there.
  const notSource = build([envelope({ lot_id: 'L1' })], { relation: 'not_declared' });
  ok('B3 on a table that is not a ledger source the ledger button is absent, not merely dead',
    buttons(notSource.host).map((b) => b.dataset.redo).join(',') === 'chain',
    buttons(notSource.host).map((b) => b.dataset.redo));
}

console.log('\n── C. THE LEDGER GROUPS, ASSEMBLED HERE ────────────────────────────');
{
  const rows = [envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                envelope({ lot_id: 'L1', wafer_id: 'W2' }),
                envelope({ lot_id: 'L2', wafer_id: 'W3' })];
  const b = build(rows);
  press(b.host, 'ledger');
  const lines = groupsShown(b.host);
  ok('C1 one line per declared scope column', lines.length === 2, lines);
  ok('C2 the group count is the DISTINCT values, not the row count',
    lines[0].includes('2 groups from 3 rows'), lines[0]);
  ok('C3 a second column groups by its own values',
    lines[1].includes('3 groups from 3 rows'), lines[1]);
  b.host.children.slice(1).forEach(() => {});
  byClass(b.host, 'redo-panel__go')[0].click();
  const handed = b.handed();
  ok('C4 handing over sends one group per column, with the declared parameter names',
    handed && handed.op === 'ledger_rescope' && handed.groups.length === 2
    && handed.groups[0].params.scope_column === 'lot_id'
    && handed.groups[0].params.source === 'dt_log_src', handed);
  ok('C5 ... and each group carries its own values, joined the way the route reads them',
    handed.groups[0].params.scope_values === 'L1,L2', handed.groups[0].params);

  // A column with no value in the selection cannot be a group -- it would hand over an empty
  // scope and admin would take the 400. It is named instead of vanishing.
  const holed = build([envelope({ lot_id: 'L1' })]);
  press(holed.host, 'ledger');
  const hl = groupsShown(holed.host);
  ok('C6 a column with nothing in it is not handed over',
    hl.filter((l) => l.startsWith('wafer_id')).every((l) => l.includes('no value')), hl);
  byClass(holed.host, 'redo-panel__go')[0].click();
  ok('C7 ... and the payload holds only the column that has values',
    holed.handed().groups.length === 1
    && holed.handed().groups[0].label === 'lot_id', holed.handed());

  // THE DISCRIMINATING SELECTION: every fixture above has a value in every row, so the size
  // of the selection and the number of rows the groups actually cover are THE SAME NUMBER and
  // no assertion on them can tell the two apart. Here they differ, and the line has to name
  // the second one -- otherwise it reads "1 group from 3 rows, 2 without a value", which counts
  // the same rows twice and is what the owner asked about.
  const partial = build([envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                         envelope({ lot_id: 'L1' }),
                         envelope({ lot_id: 'L2' })]);
  press(partial.host, 'ledger');
  const pl = groupsShown(partial.host);
  ok('C8 the row count is the rows that CARRY the value, not the size of the selection',
    pl[1] === 'wafer_id \u2014 1 group from 1 row \u00b7 2 without a value', pl);
  ok('C9 ... and a column every row does carry still counts them all',
    pl[0] === 'lot_id \u2014 2 groups from 3 rows', pl);
}

console.log('\n── D. THE CHAIN KEYS, GROUPED ELSEWHERE ────────────────────────────');
{
  const rows = [envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L2' })];
  const b = build(rows);
  press(b.host, 'chain');
  byClass(b.host, 'redo-panel__go')[0].click();
  const handed = b.handed();
  ok('D1 the chain hand-off carries the KEYS, de-duplicated',
    handed.op === 'chain_replay' && handed.businessKeys.join(',') === 'L1,L2', handed);
  // 🔴 THE ONE THIS PART EXISTS TO GET RIGHT. Grouping by rule here would mean calling a gated
  //    route from the grid page, so the payload must NOT pretend to know the rules.
  ok('D2 ... and no rule grouping is invented here, because the rules are behind the token',
    handed.groups === undefined, handed);
  const noKey = build(rows, { businessKey: null });
  press(noKey.host, 'chain');
  ok('D3 a table with no business key says so rather than handing over nothing',
    (note(noKey.host) || '').includes('business key'), note(noKey.host));
}

console.log('\n── E. THE ENVELOPE ─────────────────────────────────────────────────');
{
  // Live measurement, 2026-08-31: this grid holds rows as `{data:{col:{value}}}`. Reading them
  // plainly returns "no values at all" and the screen then says a false thing.
  const rows = [envelope({ lot_id: 'L1' })];
  const plain = build(rows, { readValue: (row, col) => (row ? row[col] : undefined) });
  press(plain.host, 'ledger');
  ok('E1 without the injected reader the enveloped rows read as empty',
    (note(plain.host) || '').includes('no scope column has a value'), note(plain.host));
  const wired = build(rows);
  press(wired.host, 'ledger');
  ok('E2 with the reader the values are found where the grid keeps them',
    groupsShown(wired.host)[0].includes('1 group from 1 row'), groupsShown(wired.host));
}

console.log('\n── F. THE DROPDOWN CLOSES ──────────────────────────────────────────');
{
  // 🔴 「없어지지도 않는다」 was half the owner's complaint, and neither half can be seen from
  //    the part's own DOM: both live on the DOCUMENT. A stub that could only add listeners
  //    would score a part that leaks them exactly like one that cleans up.
  const doc = mkDoc();
  const host = doc.createElement('div');
  const rows = [envelope({ lot_id: 'L1', wafer_id: 'W1' })];
  const part = new X.RedoBanner(host, { doc, sources: SOURCES, getSelection: () => rows,
    readValue: readEnvelope, businessKey: 'lot_id', handOff: () => {} });
  part.setRelation('dt_log');
  part.render();
  const open = () => buttons(host).find((b) => b.dataset.redo === 'ledger').click();
  const isOpen = () => byClass(host, 'redo-panel').length === 1;

  ok('F1 closed, the part holds no document listener at all', doc.listenerCount() === 0);
  open();
  ok('F2 opening arms them', isOpen() && doc.listenerCount() > 0, doc.listenerCount());
  // THE DISCRIMINATING PAIR: a handler that closes on every mousedown would pass an
  // outside-click check and make the dropdown unusable, because pressing a line is a click too.
  doc.fire('mousedown', { target: byClass(host, 'redo-panel__group')[0] });
  ok('F3 a click INSIDE it is not an outside click', isOpen());
  doc.fire('keydown', { key: 'a' });
  ok('F4 ... and a key that is not Escape is not Escape', isOpen());
  doc.fire('keydown', { key: 'Escape' });
  ok('F5 Escape closes it', !isOpen());
  ok('F6 ... and the listeners come back off', doc.listenerCount() === 0, doc.listenerCount());
  open();
  doc.fire('mousedown', { target: doc.createElement('div') });
  ok('F7 a click outside closes it', !isOpen() && doc.listenerCount() === 0);
  open();
  buttons(host).find((b) => b.dataset.redo === 'ledger').click();
  ok('F8 the same button pressed twice closes it, listeners and all',
    !isOpen() && doc.listenerCount() === 0);
}

console.log('\n── G. A LINE IS PRESSED AND IT RUNS ────────────────────────────────');
{
  const rows = [envelope({ lot_id: 'L1' })];   // wafer_id missing -> one line with no params
  const calls = [];
  let settle;
  const doc = mkDoc();
  const host = doc.createElement('div');
  const part = new X.RedoBanner(host, { doc, sources: SOURCES, getSelection: () => rows,
    readValue: readEnvelope, businessKey: 'lot_id', handOff: () => {},
    hasToken: () => true,
    run: (op, params) => { calls.push({ op, params }); return new Promise((r) => { settle = r; }); } });
  part.setRelation('dt_log');
  part.render();
  buttons(host).find((b) => b.dataset.redo === 'ledger').click();

  const lines = () => byClass(host, 'redo-panel__group');
  ok('G1 with a token the runnable lines are buttons',
    lines()[0].tagName === 'BUTTON', lines().map((n) => n.tagName));
  // The dropped column has nothing to run, so it is a line and not a control that does nothing.
  ok('G2 a line with nothing to run is not a button',
    lines()[1].tagName === 'DIV' && lines()[1].textContent.includes('no value'),
    lines().map((n) => n.tagName));
  lines()[0].click();
  ok('G3 pressing it calls the injected runner once, with the declared parameter names',
    calls.length === 1 && calls[0].op === 'ledger_rescope'
    && calls[0].params.source === 'dt_log_src'
    && calls[0].params.scope_column === 'lot_id'
    && calls[0].params.scope_values === 'L1', calls);
  ok('G4 ... and that line says so immediately, before any answer',
    lines()[0].textContent.includes('running'), lines()[0].textContent);
  lines()[0].click();
  ok('G5 pressing again while it runs does not run it twice', calls.length === 1, calls.length);
  settle({ ok: true, state: 'queued' });
  await Promise.resolve(); await Promise.resolve();
  ok('G6 when the answer comes back the same line says what happened',
    lines()[0].textContent.includes('queued'), lines()[0].textContent);
}

console.log('\n── G-bis. AND WHEN IT FAILS, IT SAYS WHY ───────────────────────────');
{
  const doc = mkDoc();
  const host = doc.createElement('div');
  const part = new X.RedoBanner(host, { doc, sources: SOURCES,
    getSelection: () => [envelope({ lot_id: 'L1' })], readValue: readEnvelope,
    businessKey: 'lot_id', handOff: () => {}, hasToken: () => true,
    run: () => Promise.resolve({ ok: false, error: 'admin token rejected' }) });
  part.setRelation('dt_log');
  part.render();
  buttons(host).find((b) => b.dataset.redo === 'ledger').click();
  byClass(host, 'redo-panel__group')[0].click();
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const said = byClass(host, 'redo-panel__group')[0].textContent;
  ok('G7 a refusal is named on the line that asked for it',
    said.includes('failed') && said.includes('admin token rejected'), said);
}

console.log('\n── H. NO TOKEN SAYS SO ─────────────────────────────────────────────');
{
  const mk = (hasToken) => {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const part = new X.RedoBanner(host, { doc, sources: SOURCES,
      getSelection: () => [envelope({ lot_id: 'L1' })], readValue: readEnvelope,
      businessKey: 'lot_id', handOff: () => {}, hasToken: () => hasToken, run: () => {} });
    part.setRelation('dt_log');
    part.render();
    buttons(host).find((b) => b.dataset.redo === 'ledger').click();
    return host;
  };
  const without = mk(false);
  const with_ = mk(true);
  ok('H1 without a token the panel says so in a sentence',
    (byClass(without, 'redo-panel__nogo')[0] || {}).textContent !== undefined
    && byClass(without, 'redo-panel__nogo')[0].textContent.includes('token'),
    byClass(without, 'redo-panel__nogo').length);
  ok('H2 ... and its lines are not controls that would do nothing',
    byClass(without, 'redo-panel__group').every((n) => n.tagName === 'DIV'));
  // The pair: with a token that sentence is GONE. One of these alone proves nothing.
  ok('H3 with a token the sentence is not there', byClass(with_, 'redo-panel__nogo').length === 0);
  ok('H4 ... and the hand-off to admin survives in both',
    byClass(without, 'redo-panel__go').length === 1
    && byClass(with_, 'redo-panel__go').length === 1);
}

console.log('\n── J. THE TAG DOES NOT DECIDE THE LAYOUT ───────────────────────────');
{
  // 🔴 THE DEFECT THIS SECTION EXISTS FOR (owner, 2026-09-02): `.redo-panel__group` set only
  //    `padding`, so the TAG decided the direction — a div is block and stacked, a button is
  //    inline-block and flowed sideways. The panel was therefore vertical for anyone without a
  //    token and horizontal for anyone with one, and the two of us who checked it had none.
  const mk = (hasToken) => {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const part = new X.RedoBanner(host, { doc, sources: SOURCES,
      getSelection: () => [envelope({ lot_id: 'L1' })], readValue: readEnvelope,
      businessKey: 'lot_id', handOff: () => {}, hasToken: () => hasToken,
      run: () => Promise.resolve({ ok: true }) });
    part.setRelation('dt_log');
    part.render();
    buttons(host).find((b) => b.dataset.redo === 'ledger').click();
    return host;
  };
  const withToken = mk(true);
  const without = mk(false);
  const classesOf = (host) => byClass(host, 'redo-panel__group').map((n) => n.className);
  const tagsOf = (host) => byClass(host, 'redo-panel__group').map((n) => n.tagName);

  // The pair: the tags DIFFER, on purpose — which is exactly why the tag may not be what
  // positions them. If these were the same the section would prove nothing.
  ok('J1 the tags differ between the two token states',
    tagsOf(withToken).join(',') !== tagsOf(without).join(','),
    [tagsOf(withToken), tagsOf(without)]);
  ok('J2 ... and the class does NOT, so the layout cannot follow the tag',
    classesOf(withToken).join('|') === classesOf(without).join('|'),
    [classesOf(withToken), classesOf(without)]);
  ok('J3 every line carries the item class this screen already lays out',
    classesOf(withToken).length > 0
    && classesOf(withToken).every((c) => c.split(/\s+/).includes('dropdown-item')),
    classesOf(withToken));
  ok('J4 the panel wears the dropdown shell this screen already has, not a parallel one',
    byClass(withToken, 'glass-dropdown-panel').length === 1
    && byClass(without, 'glass-dropdown-panel').length === 1,
    byClass(withToken, 'glass-dropdown-panel').length);

  // And the stylesheet has to be the thing that decides, not the tag default.
  const css = readFileSync(STYLE_PATH, 'utf8').replace(/\r\n/g, '\n');
  const rule = (css.match(/\.glass-dropdown-panel \.dropdown-item \{[^}]*\}/) || [''])[0];
  ok('J5 the stylesheet gives that class a display and a width of its own',
    /display\s*:/.test(rule) && /width\s*:\s*100%/.test(rule), rule.slice(0, 90));
  const shell = (css.match(/\.glass-dropdown-panel \{[^}]*\}/) || [''])[0];
  ok('J6 ... and the shell stacks its children, which is where vertical comes from',
    /flex-direction\s*:\s*column/.test(shell), shell.slice(0, 90));
}

console.log('\n── I. THE CHAIN RULES: UNREAD IS NOT EMPTY ─────────────────────────');
{
  const mk = (rules) => {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const part = new X.RedoBanner(host, { doc, sources: SOURCES,
      getSelection: () => [envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L2' })],
      readValue: readEnvelope, businessKey: 'lot_id', handOff: () => {},
      hasToken: () => true, run: () => Promise.resolve({ ok: true }), rules });
    part.setRelation('dt_log');
    part.render();
    buttons(host).find((b) => b.dataset.redo === 'chain').click();
    return { host, lines: byClass(host, 'redo-panel__group') };
  };
  const unread = mk(null);
  const declaredEmpty = mk([]);
  // ⚠️ C-109: 목록은 «객체»입니다({name, trigger_table, target_table, kind}).
  //    이 절이 재는 것은 그대로입니다 — 「못 읽음 ≠ 빈 목록」과 「규칙마다 한 줄」.
  //    줄이 «어디서 어디로»를 말하는지는 `replay_rules_harness.mjs` 가 import 로 쟐니다.
  const loaded = mk([
    { name: 'r_alpha', trigger_table: 'dt_log', target_table: 'dt_a', kind: 'join' },
    { name: 'r_beta', trigger_table: 'dt_log', target_table: 'dt_b', kind: 'mapper' },
  ]);

  // 🔴 THE PAIR THIS SECTION EXISTS FOR. 403 and an empty config are different facts, and a
  //    screen that paints them the same sends the operator to fix the wrong thing.
  ok('I1 an unread rule list and a declared-empty one do not read the same',
    unread.lines.map((n) => n.textContent).join('|')
    !== declaredEmpty.lines.map((n) => n.textContent).join('|'),
    [unread.lines.map((n) => n.textContent), declaredEmpty.lines.map((n) => n.textContent)]);
  ok('I2 unread says it could not be loaded',
    unread.lines.some((n) => n.textContent.includes('not loaded')),
    unread.lines.map((n) => n.textContent));
  // ⚠️ C-109 에서 문구가 «좁아졌습니다»: 목록이 이제 「이 표를 트리거로 하는」 규칙만이라,
  //    「서버에 규칙이 없다」는 오늘 «거짓»입니다(다른 표에는 있을 수 있습니다).
  //    단언을 지우지 «않고» 문구를 바꿉니다 — 지우면 새 규칙을 재는 것이 아무것도 안 남습니다.
  ok('I3 declared-empty says no rule is triggered by THIS table',
    declaredEmpty.lines.some((n) => n.textContent.includes('이 표를 트리거로 하는 규칙 없음')),
    declaredEmpty.lines.map((n) => n.textContent));
  ok('I4 neither offers a line to press, because `rule` is required',
    unread.lines.every((n) => n.tagName === 'DIV')
    && declaredEmpty.lines.every((n) => n.tagName === 'DIV'));
  ok('I5 with rules there is one pressable line per rule',
    loaded.lines.length === 2 && loaded.lines.every((n) => n.tagName === 'BUTTON')
    && loaded.lines[0].textContent.startsWith('r_alpha')
    && loaded.lines[1].textContent.startsWith('r_beta'),
    loaded.lines.map((n) => n.textContent));
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

const DEFECTS = [
  ['M1 the buttons are live with nothing selected',
    swap('btn.disabled = !enabled;', 'btn.disabled = false;')],
  ['M2 the ledger button is drawn on a table that is not a source',
    swap('if (row) bar.appendChild', 'bar.appendChild')],
  ['M3 the group count counts rows instead of distinct values',
    swap('      const n = g.values.length;', '      const n = g.rows;')],
  ['M4 a column with no values is handed over as an empty scope',
    swap('if (!values.length) { dropped.push(column); continue; }',
      'if (!values.length) { groups.push({ key: column, values, missing, '
      + 'rows: (rows || []).length }); continue; }')],
  ['M5 the chain hand-off invents a rule grouping admin would not read',
    swap("const payload = { op: 'chain_replay', businessKeys: values };",
      "const payload = { op: 'chain_replay', businessKeys: values, "
      + "groups: values.map((v) => ({ label: v })) };")],
  ['M9 closing leaves the document listeners attached',
    swap('    if (this.dismiss) this.dismiss();', '    if (false) this.dismiss();')],
  // M10 and M11 live in `dropdown.js` now. They are still scored because SOURCE is what runs.
  ['M10 a click INSIDE the part closes it too',
    swap('    while (node) { if (node === host) return; node = node.parentNode; }',
      '    while (node) { node = node.parentNode; }')],
  ['M11 any key closes it, not just Escape',
    swap("if (event && event.key === 'Escape') close();", 'close();')],
  ['M12 the line is drawn as a button but never wired to run',
    swap("        line.addEventListener('click', () => this.fire(index, assembled.op, entry.params));",
      '        line.type = \'button\';')],
  ['M13 no token goes quietly grey instead of saying so',
    swap("      why.className = 'redo-panel__nogo';", "      why.className = 'redo-panel__quiet';")],
  ['M14 the unread rule list paints the same as a declared-empty one',
    swap("        { text: 'chain rules not loaded — open in admin to pick one', params: null },",
      "        { text: '이 표를 트리거로 하는 규칙 없음', params: null },")],
  ['M16 the line drops the item class when it becomes a button',
    swap("      line.className = 'dropdown-item redo-panel__group';",
      "      line.className = pressable ? 'redo-panel__group'\n"
      + "        : 'dropdown-item redo-panel__group';")],
  ['M17 the panel stops wearing the shell and picks its own',
    swap("    box.className = 'glass-dropdown-panel redo-panel';",
      "    box.className = 'redo-panel';")],
  ['M15 pressing a line says nothing until the answer comes back',
    swap("    this.said[index] = 'running…';\n    this.render();",
      "    this.render();")],
  ['M6 the scope values are joined with something the route does not read',
    swap("scope_values: g.values.join(',')", "scope_values: g.values.join(' ')")],
  ['M7 a repeated value becomes its own group',
    swap('if (!seen.includes(value)) seen.push(value);', 'seen.push(value);')],
  ['M8 the line counts the whole selection instead of the rows that carry the value',
    swap('rows: (rows || []).length - missing', 'rows: (rows || []).length')],
];

const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bseen\b/g, 'found')],
  ['comments stripped', (src) => src.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n')],
];

// 🔴 C-66 ②ⓑ. WHICH CHECK MUST CATCH WHICH MUTANT — MEASURED, NOT DECIDED. Every pairing here
//    was read off ⓐ's own run (the "by R#" line it prints under each verdict), so this table
//    records what the corpus DOES rather than what I think it ought to do. Writing it from
//    intuition is how a mutant comes to name an assertion that never fires: the corpus stays
//    green, and the line it was supposed to guard is unmeasured.
// ⚠️ It sits beside the mutants rather than inside each literal on purpose -- those literals
//    carry the commentary explaining each defect, and threading a field through them would bury
//    it. One table, one place to look, one place to correct.
// 🔵 EIGHT CHECKS ARE NAMED BY NOBODY: R4, R8, R10, R11, R13, R17, R18, R20. They are not dead
//    -- they run on the baseline and would redden it -- but no mutant proves they can still
//    fail. That is a measurement, reported rather than papered over.
const CATCHES = {
  M1: 'R1', M2: 'R2', M3: 'R3', M4: 'R6', M5: 'R7', M6: 'R5', M7: 'R3', M8: 'R9',
  M9: 'R12', M10: 'R14', M11: 'R15', M12: 'R16', M13: 'R21', M14: 'R22', M15: 'R19',
  M16: 'R23', M17: 'R24',
};
/** `['M1 …', fn]` -> the shape `lib/mutation_scorer.mjs` scores. */
const named = (list) => list.map(([name, mutate]) => ({
  name, mutate, catches: CATCHES[String(name).split(' ')[0]],
}));
/** Filled on the first mutant run; the source of the 「unexercised」 line at the end. */
let CHECK_IDS = null;
let CHECK_NAMES = null;   // the full names, for the scorer's ambiguity check

async function runMutant({ name, mutate }) {
  {
    let bad = false;
    const woke = [];   // the NAMED checks that did not hold -- ⓐ of C-66
    {
      const M = load(mutate(SOURCE));
      const rows = [envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                    envelope({ lot_id: 'L1', wafer_id: 'W2' }),
                    envelope({ lot_id: 'L2', wafer_id: 'W3' })];
      const doc = mkDoc();
      const host = doc.createElement('div');
      let handed = null;
      const part = new M.RedoBanner(host, {
        doc, sources: SOURCES, getSelection: () => rows, readValue: readEnvelope,
        businessKey: 'lot_id', handOff: (p) => { handed = p; },
      });
      part.setRelation('dt_log');
      part.render();
      // the checks that matter, read through guards so a crash cannot score as a catch
      const empty = new M.RedoBanner(mkDoc().createElement('div'), {
        doc: mkDoc(), sources: SOURCES, getSelection: () => [], readValue: readEnvelope });
      empty.host = mkDoc().createElement('div');
      empty.doc = doc;
      empty.setRelation('dt_log');
      empty.render();
      const notSource = new M.RedoBanner(doc.createElement('div'), {
        doc, sources: SOURCES, getSelection: () => rows, readValue: readEnvelope });
      notSource.setRelation('not_declared');
      notSource.render();
      const holed = new M.RedoBanner(doc.createElement('div'), {
        doc, sources: SOURCES, getSelection: () => [envelope({ lot_id: 'L1' })],
        readValue: readEnvelope, handOff: () => {} });
      holed.setRelation('dt_log');
      holed.render();
      holed.open = 'ledger';
      holed.render();
      // A selection where "how many rows I picked" and "how many rows this group covers" are
      // DIFFERENT numbers. Every other fixture here has both values in every row, which makes
      // the two indistinguishable and lets a count off the selection size score as correct.
      const partial = new M.RedoBanner(doc.createElement('div'), {
        doc, sources: SOURCES, readValue: readEnvelope, handOff: () => {},
        getSelection: () => [envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                             envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L2' })] });
      partial.setRelation('dt_log');
      partial.open = 'ledger';
      partial.render();
      part.open = 'ledger';
      part.render();
      const lines = groupsShown(host);
      const go = byClass(host, 'redo-panel__go')[0];
      if (go) go.click();
      const ledgerHanded = handed;
      part.open = 'chain';
      part.render();
      const go2 = byClass(host, 'redo-panel__go')[0];
      if (go2) go2.click();

      // ── the dropdown, exercised the way a person uses it ──────────────────────────
      // Everything above reaches the panel by setting `open` directly, which never touches the
      // document listeners, the runner or the rule list. A mutant living in any of those walks
      // straight through a replay that only reads text.
      const doc2 = mkDoc();
      const calls = [];
      let settle = null;
      const drop = new M.RedoBanner(doc2.createElement('div'), {
        doc: doc2, sources: SOURCES, getSelection: () => rows, readValue: readEnvelope,
        businessKey: 'lot_id', handOff: () => {}, hasToken: () => true, rules: ['r_alpha'],
        run: (op, params) => { calls.push({ op, params });
          return new Promise((res) => { settle = res; }); },
      });
      drop.setRelation('dt_log');
      drop.render();
      // 🔴 C-66 ②ⓑ. TOTAL FROM HERE DOWN, AND THAT IS WHAT LETS R14/R15 SPEAK. M10 and M11 make
      //    an inside click or a stray key CLOSE the panel -- which is exactly what those two
      //    checks are for -- but the next line then reached into a panel that was gone and threw,
      //    so the whole scoring block died and the crash was banked as the catch. `survived*` are
      //    read BEFORE that point, so the facts were already known; nothing but a dereference
      //    stood between them and being reported by name.
      const armedClosed = doc2.listenerCount();
      const firstGroup = () => byClass(drop.host, 'redo-panel__group')[0] || null;
      const openIt = () => {
        const b = buttons(drop.host).find((x) => x.dataset.redo === 'ledger');
        if (b) b.click();
      };
      const stillOpen = () => byClass(drop.host, 'redo-panel').length === 1;
      openIt();
      const armedOpen = doc2.listenerCount();
      doc2.fire('mousedown', { target: firstGroup() });
      const survivedInsideClick = stillOpen();
      doc2.fire('keydown', { key: 'a' });
      const survivedOtherKey = stillOpen();
      const pressable = firstGroup();
      if (pressable) pressable.click();
      // A panel that is not there says nothing -- and 「(no line)」 is not 「running…」, so R19/R20
      // fail by name rather than being skipped.
      const saidWhilePressed = firstGroup() ? firstGroup().textContent : '(no line)';
      if (settle) settle({ ok: true, state: 'queued' });
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
      const saidAfter = firstGroup() ? firstGroup().textContent : '(no line)';
      doc2.fire('keydown', { key: 'Escape' });
      const closedByEsc = !stillOpen();
      const armedAfter = doc2.listenerCount();

      // the token sentence, and the two absences of a rule list
      const panelOf = (opts) => {
        const dd = mkDoc();
        const p = new M.RedoBanner(dd.createElement('div'), Object.assign({
          doc: dd, sources: SOURCES, getSelection: () => rows, readValue: readEnvelope,
          businessKey: 'lot_id', handOff: () => {} }, opts));
        p.setRelation('dt_log');
        p.render();
        const opener = buttons(p.host).find((b) => b.dataset.redo === (opts.which || 'ledger'));
        if (opener) opener.click();
        return p.host;
      };
      const noToken = panelOf({ hasToken: () => false, run: () => {} });
      // 🔴 A FRESH OPEN ONE. `drop` was closed by the Escape above, so reading its classes here
      //    returns '' for every mutant AND every control -- the guard would be vacuously false
      //    and score everything as caught for a reason that is not the reason. The controls
      //    catching is what exposed it: a check that cannot pass cannot discriminate either.
      const withToken = panelOf({ hasToken: () => true, run: () => {} });
      const classes = (host) => byClass(host, 'redo-panel__group').map((n) => n.className).join('|');
      const sameClassBothWays = classes(withToken) !== ''
        && classes(withToken) === classes(noToken);
      const wearsTheShell = byClass(withToken, 'glass-dropdown-panel').length === 1;
      const chainText = (rules) => byClass(
        panelOf({ hasToken: () => true, run: () => {}, rules, which: 'chain' }),
        'redo-panel__group').map((n) => n.textContent).join('|');
      const unread = chainText(null);
      const declaredEmpty = chainText([]);

      // \ud83d\udd34 C-66 \u2461\u24d0. THIS WAS ONE ANONYMOUS DISJUNCTION \u2014 `bad = A || B || \u2026 `, twenty-four
      //    clauses, no names. It answered \u300csomething is wrong\u300d and could not answer \u300cWHAT\u300d, so
      //    every mutant in this file scored `caught` without anyone being able to say which
      //    fact noticed it. A mutant caught for an unrelated reason is a mutant nobody is
      //    measuring: the line it was written to protect can rot away underneath it while the
      //    corpus stays green. The clauses are the same clauses, in the same order, with the
      //    same meaning \u2014 each now carries the name of the fact it checks, and states it
      //    POSITIVELY (true = the screen is right), because a list of negations is read wrong.
      // \u26a0\ufe0f EACH CHECK RUNS IN ITS OWN TRY. In the disjunction a dereference of something a
      //    defect had removed (`calls[0].params`, `ledgerHanded.groups[0]`) threw out of the
      //    whole scoring block, and the throw was folded into `bad = true` \u2014 a crash banked as a
      //    catch. A check that cannot run has not passed; it fails, by name, and the rest still
      //    get to speak.
      const CHECKS = [
        ['R1 nothing selected leaves every button dead',
          () => buttons(empty.host).every((b) => b.disabled === true)],
        ['R2 a table that is not a source offers chain only',
          () => buttons(notSource.host).map((b) => b.dataset.redo).join(',') === 'chain'],
        ['R3 the group line counts distinct values, not rows',
          () => (lines[0] || '').includes('2 groups from 3 rows')],
        ['R4 the ledger hand-off carries the groups',
          () => !!ledgerHanded && ledgerHanded.groups.length === 2],
        ['R5 ...with the scope values joined the way the route reads them',
          () => ledgerHanded.groups[0].params.scope_values === 'L1,L2'],
        ['R6 a column with no values says so instead of going out as an empty scope',
          () => byClass(holed.host, 'redo-panel__group')
            .filter((n) => n.textContent.startsWith('wafer_id'))
            .every((n) => n.textContent.includes('no value'))],
        ['R7 the chain hand-off invents no rule grouping',
          () => !!handed && handed.groups === undefined],
        ['R8 ...and carries the business keys verbatim',
          () => handed.businessKeys.join(',') === 'L1,L2'],
        ['R9 rows without a value are counted apart from the ones that have it',
          () => groupsShown(partial.host)[1]
            === 'wafer_id \u2014 1 group from 1 row \u00b7 2 without a value'],
        ['R10 a closed panel arms no document listener', () => armedClosed === 0],
        ['R11 opening arms them', () => armedOpen !== 0],
        ['R12 closing disarms them again', () => armedAfter === 0],
        ['R13 Escape closes it', () => closedByEsc === true],
        ['R14 a click INSIDE the panel does not close it', () => survivedInsideClick === true],
        ['R15 another key does not close it', () => survivedOtherKey === true],
        ['R16 pressing a line runs it once, under the op the route reads',
          () => calls.length === 1 && calls[0].op === 'ledger_rescope'],
        ['R17 ...with the column', () => calls[0].params.scope_column === 'lot_id'],
        ['R18 ...and the values', () => calls[0].params.scope_values === 'L1,L2'],
        ['R19 the line says it is running while it is', () => saidWhilePressed.includes('running')],
        ['R20 ...and says what came back', () => saidAfter.includes('queued')],
        ['R21 no token is said, not shown as a grey line',
          () => byClass(noToken, 'redo-panel__nogo').length === 1],
        ['R22 an unread rule list and a declared-empty one are different sentences',
          () => unread !== declaredEmpty],
        ['R23 the line wears the same class with a token and without one',
          () => sameClassBothWays === true],
        ['R24 the panel wears the shell rather than styling itself', () => wearsTheShell === true],
      ];
      // Recorded once, so the 「unexercised」 line below is COMPUTED from the checks that
      // actually ran rather than typed out beside them -- a hand-written list of names drifts
      // the first time a check is added, and drifts silently.
      if (!CHECK_IDS) CHECK_IDS = CHECKS.map(([c]) => String(c).split(' ')[0]);
      if (!CHECK_NAMES) CHECK_NAMES = CHECKS.map(([c]) => String(c));
      for (const [checkName, fn] of CHECKS) {
        let held = false;
        try { held = fn() === true; } catch (e) { held = false; }
        if (!held) woke.push(checkName);
      }
      bad = woke.length > 0;
    }
    // \ud83d\udd34 \u24d1: THE SETUP NO LONGER SWALLOWS ITS OWN THROW. It used to be caught here and folded
    //    into `bad = true` -- the panel failing to build, scored as a mutant being noticed. It
    //    now propagates to `lib/mutation_scorer.mjs`, which reports INERT and counts it as an
    //    escape, because a harness that stopped is not a harness that noticed.
    void bad;
    return { failures: woke };
  }
}

const defects = await scoreMutants(named(DEFECTS), runMutant,
  { baselineNames: CHECK_NAMES, title: '\n\u2500\u2500 defect mutants (each must be CAUGHT by its named check) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500' });
const controls = await scoreMutants(named(CONTROLS), runMutant,
  { mustCatch: false, title: '\n\u2500\u2500 control mutants (each must ESCAPE) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500' });
const caught = defects.caught;
const escaped = CONTROLS.length - controls.wrong;
failed += defects.wrong + controls.wrong;

// 🔴 CHECKS NO MUTANT EXERCISES, SAID OUT LOUD (ruling, 2026-09-10). They are not dead -- they
//    run on the baseline and would redden it -- but nothing proves they can STILL fail, so what
//    they report is 「it passes today」 and not 「it goes red when it stops being true」. Naming
//    them is the whole treatment: the corpus grows by one when a fact is actually broken, never
//    by inventing a mutant per check.
{
  const exercised = new Set(Object.values(CATCHES));
  const idle = (CHECK_IDS || []).filter((id) => !exercised.has(id));
  console.log(idle.length
    ? `\n  unexercised checks (no mutant names them): ${idle.join(' · ')}`
    : '\n  unexercised checks: none — every check is named by a mutant');
}

console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
