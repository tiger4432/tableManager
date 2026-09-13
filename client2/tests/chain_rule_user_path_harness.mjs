/**
 * chain_rule_user_path -- the walk a person actually takes, through `admin.js` ITSELF:
 * open the tab -> pick a rule -> the boxes are filled -> change one -> save -> it is still there.
 *
 * WHY THIS EXISTS (C-95 ⑦). `chain_rule_form_harness` scores the PANEL, and it scores it well --
 * but it hands the panel a `declaration` directly. The owner's complaint was that picking a rule
 * leaves the boxes EMPTY, and that break does not live in the panel: it lives in the request the
 * page makes and the response it gets back. A harness that injects the declaration reproduces a
 * screen that works while the real one does not, and this repository has paid for exactly that
 * shape before -- 「a UI round closes only after walking the user's path on the real page route」.
 *
 * 🔴 SO THE SUBJECT IS `admin.js`, NOT THE PANEL. CLAUDE.md names `import './tokens.css'` as the
 *    reason a file cannot be imported by a harness. Measured 2026-09-13 with a ten-line spike:
 *    that is no longer true -- `probe_hooks.mjs` now resolves a stylesheet a PROBE COPY imports
 *    to an empty module, and `admin.js` imports whole. Nothing is cut; the byte-prefix assertion
 *    in `probe.mjs` passes exactly as before.
 *
 * WHAT IT SCORES:
 *   A  seating: the page finds its mount and puts a panel in it, with no name asked for yet
 *   B  picking: choosing a name makes ONE request, and that request carries the chosen name
 *   C  filling: the response's declaration reaches the boxes -- measured as VALUES, not as
 *      「the panel was called」. This is the assertion the owner's complaint is about
 *   D  editing: a box changed rewrites the document the save will send
 *   E  saving: ONE POST, shape {name, declaration, base}, through the page's own save
 *   F  staying: after the save the same rule is still selected and still filled
 *   G  the new name: [규칙 추가] asks for a name in ONE place, and the save carries THAT name
 *
 * ⚠️ WHAT IT DOES NOT SCORE, AND WHY. The query parameter's SPELLING is a seam between two
 *    files in two lanes (`admin.js` sends one word, `main.get_chain_rule_raw` declares another
 *    -- measured 2026-09-13). Asserting one spelling here would make this harness the second
 *    author of that contract and would go green while the screen stays broken, or red while
 *    somebody else fixes it correctly. It asserts that the CHOSEN NAME travels; which cell
 *    carries it is reported to the lead, not decided here.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { PICK_NAME } from '../src/raw_registry_panel.js';
import { makeDoc, flush } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const ADMIN = path.join(SRC, 'admin.js');

// The shipped skeleton, generated on the server from `chain_bindings.routing_keys()`. Reading it
// means a routing key added there reaches this harness -- the client authors none of these names.
const SKELETON = JSON.parse(readFileSync(
  path.join(HERE, '..', '..', 'server', 'chain_skeleton.json'), 'utf8'));

// A rule with the shape the shipped file actually uses: the TWO-CELL mapper spelling and flat
// parameter cells the skeleton has never heard of. Both are real (`chain_rules.json.sample`), and
// both are what makes 「the boxes are filled」 a claim worth scoring.
const RULE = {
  name: 'lot_event_to_lot_slot_wafer',
  trigger_table: 'lot_event',
  target_table: 'lot_slot_wafer',
  mapper_module: 'mappers.lot_slot_wafer_mapper',
  mapper_function: 'build_lot_slot_wafer_rows',
  is_batch: true,
  enabled: true,
  lot_column: 'lot_id',
};
const NAMES = ['dt_log_to_dt_map', 'lot_event_to_lot_slot_wafer'];

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

// ── the world `admin.js` wakes up in ──────────────────────────────────────────────────────
const doc = makeDoc('light');
// `renderSkeletonForm` builds with the GLOBAL document; the panel builds with `deps.doc`, which
// is the mount's. One document here is what makes the tree one tree.
globalThis.document = doc;
globalThis.window = {
  // Not 5173: that port switches `admin.js` to an absolute API base, and a harness that
  // depends on which host a URL names is scoring its own fixture.
  location: { port: '', origin: 'http://box', href: 'http://box/admin.html', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
};
globalThis.localStorage = globalThis.window.localStorage;
// node 22 ships a real `navigator`, and it is getter-only -- defining over it is how a
// harness dies before its first assertion. Only the piece the page might reach is added.
if (!globalThis.navigator.clipboard) {
  Object.defineProperty(globalThis.navigator, 'clipboard',
                        { value: { writeText: async () => {} }, configurable: true });
}

/** Every request the page makes, and the answer it is given. */
const calls = [];
let answer = () => ({ status: 404, body: null });
globalThis.fetch = async (url, init) => {
  const call = { url: String(url), method: (init && init.method) || 'GET',
                 body: init && init.body ? JSON.parse(init.body) : null };
  calls.push(call);
  const a = answer(call) || { status: 404, body: null };
  return {
    ok: a.status >= 200 && a.status < 300,
    status: a.status,
    json: async () => a.body,
    clone() { return this; },
    text: async () => JSON.stringify(a.body),
  };
};

// Rebuilt by `freshPage()` before each run -- see there for why one page cannot serve two.
let mount = null;

const rawView = (name) => {
  const out = {
    config_path: '/box/chain_rules.json', base: 'fp-1', rules: NAMES,
    error: null, editable_unit: 'rule', skeleton: SKELETON,
  };
  if (name) {
    out.name = name;
    out.declaration = name === RULE.name ? RULE : { name };
    out.raw = JSON.stringify(out.declaration, null, 2);
    out.enabled = true;
  }
  return out;
};

/** The name the page asked for, whatever cell it used to ask. */
const askedName = (call) => {
  const q = call.url.split('?')[1] || '';
  for (const pair of q.split('&')) {
    const [, value] = pair.split('=');
    if (value) return decodeURIComponent(value);
  }
  return '';
};

const panelRoot = () => mount.children[0] || null;
// 🔴 THE HARNESS WALKS. `board_dom`'s selector engine answers `.class` and `[key="value"]` and
//    nothing else, deliberately -- 「an engine that silently answers the wrong thing is worse
//    than one that answers nothing」. A bare `[data-picker]` is neither form, and reading its
//    null as 「the picker is missing」 is exactly the silent wrong answer that rule prevents.
const all = (root, out = []) => {
  if (!root) return out;
  out.push(root);
  for (const kid of root.children || []) all(kid, out);
  return out;
};
const byAttr = (key, value) => all(panelRoot()).find(
  (el) => el.attrs && el.attrs[key] != null && (value === undefined || el.attrs[key] === value))
  || null;
const countAttr = (key) => all(panelRoot()).filter((el) => el.attrs && el.attrs[key] != null).length;
const byCls = (cls) => all(panelRoot()).find(
  (el) => String(el.className || '').split(/\s+/).includes(cls)) || null;
// ⚠️ THE CONTROL, NOT THE 「−」 BESIDE IT. An optional cell the document holds also draws a
//    remove button, and that button carries the SAME `data-value` -- taking the first hit read
//    a button's absent `.value` as 「the box is empty」 on four fields that were filled.
const FIELD_TAGS = ['INPUT', 'SELECT', 'TEXTAREA'];
const boxAt = (at) => all(panelRoot()).find(
  (el) => el.attrs && el.attrs['data-value'] === at && FIELD_TAGS.includes(el.tagName)) || null;
// 🔴 A MUTANT MUST FAIL THE WALK, NOT THROW IT. A run that dies half way scores the mutant as
//    caught for the wrong reason AND stops every later assertion from being asked at all. So a
//    missing control reads as a failed assertion here, never as an exception.
const held = () => {
  const area = byCls('chain-rule-raw');
  try { return JSON.parse((area && area.value) || 'null'); } catch (e) { return null; }
};
const press = (action) => {
  const btn = byAttr('data-action', action);
  if (btn) btn.dispatch('click', {});
  return Boolean(btn);
};
const type = (at, value) => {
  const box = boxAt(at);
  if (!box) return false;
  box.value = value;
  box.dispatch('change', { target: box });
  return true;
};

/** One load of `admin.js`, with the two functions the user path runs through exposed.
 *
 * 🔴 `admin.js` exports nothing, so the accessors are APPENDED to a byte-identical copy -- the
 *    bridge CLAUDE.md allows. Nothing is cut, and `probe.mjs`'s byte-prefix assertion is the
 *    evidence of that.
 */
const loadAdmin = (tag, mutate) => loadWithProbe(ADMIN, {
  tag, mutate, expose: ['refreshChainRule', 'saveChainRule'],
});

/** The tree `admin.js` seats into. Rebuilt per run: one run's panel must not answer for the next. */
function freshPage() {
  doc.body.children.length = 0;
  const m = doc.createElement('div');
  m.setAttribute('id', 'chain-rule-mount');
  doc.body.appendChild(m);
  const c = doc.createElement('span');
  c.setAttribute('id', 'chain-rule-editor-count');
  doc.body.appendChild(c);
  mount = m;
}

async function suite(probe) {
  const before = { pass, fail };
  freshPage();
  const refreshChainRule = probe.probe.refreshChainRule;
  ok(typeof refreshChainRule === 'function', 'A admin.js imports, and its seating code is reachable');

  // ── A. the tab opens: no name yet, so the page asks for the list ────────────────────────
  answer = (call) => (call.url.includes('/admin/mappers/list')
    ? { status: 200, body: { registered: [] } }
    : { status: 200, body: rawView(null) });
  calls.length = 0;
  await refreshChainRule();
  await flush();
  ok(Boolean(panelRoot()), 'A the page seats a panel in its own mount');
  const picker = byAttr('data-picker');
  ok(Boolean(picker), 'A the picker is drawn');
  ok(Boolean(picker) && picker.children.length === NAMES.length + 1,
     `A the picker holds the served names and the placeholder (${picker ? picker.children.length : 0})`);
  if (!picker) return { pass: pass - before.pass, fail: fail - before.fail };
  // 🔴 C-95-b. NOTHING IS PICKED YET, AND THE SCREEN SAYS SO. The first read carries no name, so
  //    without a placeholder the picker shows its first option by browser default -- and the
  //    boxes beside it are empty. 「이름이 있는데 칸이 비어 있다」 is the first thing anybody sees.
  const opening = picker.children.filter((o) => o.getAttribute('selected'));
  ok(opening.length === 1 && opening[0].value === PICK_NAME,
     `A nothing is picked, and the picker says that rather than naming a rule `
     + `(${opening.map((o) => o.value).join(',')})`);
  ok(!byCls('chain-rule-form') && !byCls('chain-rule-raw'),
     'A no editor is drawn before a name is chosen -- that would be an empty document under a live save');
  ok(Boolean(byAttr('data-action', 'add-chain-rule')),
     'A ... but the add control is there, because that is the other way in');

  // ── B. picking: one request, carrying the chosen name ───────────────────────────────────
  answer = (call) => (call.url.includes('/admin/mappers/list')
    ? { status: 200, body: { registered: [] } }
    : { status: 200, body: rawView(askedName(call)) });
  calls.length = 0;
  picker.value = RULE.name;
  picker.dispatch('change', { target: { value: RULE.name } });
  await flush();
  await flush();
  const rawCalls = calls.filter((c) => c.url.includes('/admin/chain/rules/raw'));
  ok(rawCalls.length === 1, `B picking a rule makes ONE read (${rawCalls.length})`);
  ok(rawCalls.length === 1 && askedName(rawCalls[0]) === RULE.name,
     'B the request carries the name that was picked');

  // ── C. filling: the response's values are IN THE BOXES ──────────────────────────────────
  // 🔴 THE ASSERTION THIS HARNESS EXISTS FOR. Not 「render was called」 -- the values.
  const filled = ['name', 'trigger_table', 'target_table', 'mapper_module', 'mapper_function']
    .map((key) => [key, boxAt(key)]);
  for (const [key, el] of filled) {
    ok(Boolean(el) && el.value === RULE[key],
       `C ${key} holds the served value (${el ? JSON.stringify(el.value) : 'no box'})`);
  }
  const flag = boxAt('is_batch');
  ok(Boolean(flag) && flag.checked === true, 'C a flag the rule sets is checked');
  const opened = held();
  ok(Boolean(opened) && opened.lot_column === RULE.lot_column,
     'C a cell the skeleton never heard of survives in the document');

  // ── D. editing: the document the save will send is rewritten ────────────────────────────
  type('target_table', 'lot_slot_wafer_v2');
  await flush();
  const afterEdit = held() || {};
  ok(afterEdit.target_table === 'lot_slot_wafer_v2', 'D a box changed rewrites the document');
  ok(afterEdit.lot_column === RULE.lot_column, 'D and rewrites nothing else');

  // ── E. saving: one POST, the shape the route reads ──────────────────────────────────────
  let saved = null;
  answer = (call) => {
    if (call.url.includes('/admin/mappers/list')) return { status: 200, body: { registered: [] } };
    if (call.method === 'POST') { saved = call; return { status: 200, body: { name: call.body.name, rules: NAMES, backup: '/box/bak', enabled: true } }; }
    return { status: 200, body: rawView(askedName(call)) };
  };
  calls.length = 0;
  press('save-chain-rule');
  await flush();
  await flush();
  const posts = calls.filter((c) => c.method === 'POST');
  ok(posts.length === 1, `E saving makes ONE write (${posts.length})`);
  ok(Boolean(saved) && saved.body.name === RULE.name, 'E the write names the rule that was open');
  ok(Boolean(saved) && saved.body.base === 'fp-1', 'E the write carries the base fingerprint back');
  ok(Boolean(saved) && saved.body.declaration
     && saved.body.declaration.target_table === 'lot_slot_wafer_v2',
     'E the write carries the EDITED document');

  // ── F. staying: the rule is still open and still filled ─────────────────────────────────
  const stillPicked = byAttr('data-picker');
  const selected = stillPicked
    ? stillPicked.children.filter((o) => o.getAttribute('selected')).map((o) => o.value)
    : [];
  ok(selected.length === 1 && selected[0] === RULE.name,
     `F after saving, the picker still shows that rule (${JSON.stringify(selected)})`);
  ok(Boolean(boxAt('trigger_table')) && boxAt('trigger_table').value === RULE.trigger_table,
     'F and the boxes are still filled');

  // ── G. the new name lives in ONE place, and the save carries it ─────────────────────────
  press('add-chain-rule');
  await flush();
  ok(countAttr('data-new-name') === 0,
     'G adding a rule does not open a SECOND name box beside the form');
  const nameBox = boxAt('name');
  ok(Boolean(nameBox) && nameBox.value === '', 'G the form starts empty');
  type('name', 'brand_new_rule');
  await flush();
  saved = null;
  calls.length = 0;
  press('save-chain-rule');
  await flush();
  await flush();
  ok(Boolean(saved) && saved.body.name === 'brand_new_rule',
     `G the save carries the name typed in the form (${saved ? saved.body.name : 'no save'})`);
  ok(Boolean(saved) && saved.body.declaration && saved.body.declaration.name === 'brand_new_rule',
     'G and the document says the same name -- one fact, one place');
  return { pass: pass - before.pass, fail: fail - before.fail };
}

if (process.argv[2] === '--quiet') quiet = true;

console.log('-- the real page ---------------------------------------------------');
const base = await suite(await loadAdmin('real'));

// -- mutants -----------------------------------------------------------------------------
// Each one is a shape this screen has had or could quietly take. They are written against
// `admin.js`'s OWN text because that is the subject: the panel is measured elsewhere, and what
// is measured here is the PAGE -- what it asks for, what it hands the panel, what it sends back.
const DEFECTS = [
  // 🔴 THE OWNER'S COMPLAINT, AS A MUTANT. 「규칙을 골라도 칸이 안 채워진다」 is what a read that
  //    forgets the chosen name looks like from the screen: the route answers with the list and
  //    no declaration, and every box is empty while nothing errors.
  ['the read forgets which rule was chosen',
    s => s.replace('    const qs = name ? `?name=${encodeURIComponent(name)}` : \'\';',
                   '    const qs = \'\';')],
  ['the response is dropped and the panel is drawn from nothing',
    s => s.replace('  const view = chainRulePanel.render(body, opts);',
                   '  const view = chainRulePanel.render(null, opts);')],
  ['the save forgets the base fingerprint, so a concurrent edit is overwritten in silence',
    s => s.replace('      body: JSON.stringify({ name, declaration, base }),',
                   '      body: JSON.stringify({ name, declaration }),')],
  // 🔴 What 「저장했더니 사라졌다」 is made of: the save lands and the screen re-reads with no
  //    name, so the rule that was just written is no longer the one on the screen.
  ['after saving, the screen forgets which rule it saved',
    s => s.replace('    await refreshChainRule(name, { saved: answer || {} });',
                   '    await refreshChainRule(undefined, { saved: answer || {} });')],
];

// Controls must ESCAPE: a change that alters no behaviour must not redden anything, or the
// harness is scoring the file's letters rather than what the page does.
const CONTROLS = [
  ['a local rename', s => s.replace(/\bconst view = chainRulePanel\.render\(body, opts\);/,
                                   'const drawn = chainRulePanel.render(body, opts);')
                            .replace(/\bif \(count\) count\.textContent = view\.count;/,
                                     'if (count) count.textContent = drawn.count;')],
  ['a comment removed', s => s.replace(
    '  // C-86 ③. 목록은 «패널이 그리기 전»에 넣습니다. 한 번 읽고 기억합니다 — 규칙을 열 때마다\n'
    + '  // 등록부를 다시 묻는 것은 같은 답에 대한 두 번째 질문입니다.\n', '')],
];

const caught = [];
const escaped = [];
console.log('');
console.log('-- defect mutants (each must be CAUGHT) ----------------------------');
let tag = 0;
for (const [name, mutate] of DEFECTS) {
  quiet = true;
  const delta = await suite(await loadAdmin(`d${tag += 1}`, mutate));
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
let controlsCaught = 0;
for (const [name, mutate] of CONTROLS) {
  quiet = true;
  const delta = await suite(await loadAdmin(`c${tag += 1}`, mutate));
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} ${name}`);
}

// 🔴 The real run is the only one whose failures are the harness's verdict; a mutant that
//    reddens is the harness WORKING. So the exit code reads the real run, and the mutation
//    score is asserted separately.
const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.pass} passed, ${base.fail} failed; ${caught.length}/${DEFECTS.length} defects `
  + `caught, ${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
// 🔴 THE REAL RUN IS THE VERDICT. A mutant's failures are the harness WORKING, so counting them
//    in the gate line would make this file's number rise every time a defect is added.
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
if (base.fail) console.log('FAILED: ' + failedNames.slice(0, base.fail).join(' | '));
if (base.fail || badScore) process.exitCode = 1;
