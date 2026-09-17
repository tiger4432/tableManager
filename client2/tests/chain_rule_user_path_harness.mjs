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
 *   H  staying under the page's own clock: the 30-second read names no rule, and what is being
 *      edited is still there afterwards -- while the LIST it went for does refresh (C-101 ①)
 *   I  choosing rather than typing: the table catalogue reaches the reference cells, and a name
 *      the catalogue does not hold is still accepted as typed (C-101 ②)
 *   J  the mapper list: BOTH what the decorator registered and what the files define, in two
 *      groups, and choosing a file function fills the two cells (C-101 ③)
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
// 🔴 [판정 542] THE BRANCH THIS BOX DOES NOT HAVE, MADE ON PURPOSE. Every rule in the box
//    reads as flat or unified, so 「the grammar cannot be read」 was never once walked -- the
//    lead said their own green was silent about it for exactly that reason. `dt_log_to_dt_map`
//    is LEFT OUT of this map, which is how the route says 「모른다」 (it omits rather than
//    defaulting to flat), and that name is never opened by any section below.
const GRAMMARS = { lot_event_to_lot_slot_wafer: 'flat' };

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
// 🔴 COUNTED ACROSS THE WHOLE WALK, not inside one section. `calls` is emptied between sections,
//    and inside any one of them 「once」 and 「every time」 look identical -- which is how a list
//    re-read per rule opened would pass as cached.
let catalogueReads = 0;
let answer = () => ({ status: 404, body: null });
globalThis.fetch = async (url, init) => {
  const call = { url: String(url), method: (init && init.method) || 'GET',
                 body: init && init.body ? JSON.parse(init.body) : null };
  calls.push(call);
  if (isCatalogue(call)) catalogueReads += 1;
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

// 🔴 [판정 540·542] THE ROUTE ALWAYS SENDS `grammar`, AND THE LIST SENDS A MAP BESIDE IT.
//    A fixture that left `grammar` out was simulating 「the grammar cannot be read」 while
//    asserting that the FLAT form is drawn -- the two cannot both be right, and after 542
//    the screen answers the first. `rule_grammars` leaves a name OUT when it is unknown
//    (`{n: g for ... if g}`), so the map here is not keyed by every name on purpose.
const rawView = (name) => {
  const out = {
    config_path: '/box/chain_rules.json', base: 'fp-1', rules: NAMES,
    error: null, editable_unit: 'rule', skeleton: SKELETON,
    grammar: 'unified',
    rule_grammars: GRAMMARS,
  };
  if (name) {
    out.name = name;
    out.declaration = name === RULE.name ? RULE : { name };
    out.raw = JSON.stringify(out.declaration, null, 2);
    out.enabled = true;
    out.grammar = GRAMMARS[name] || undefined;
    if (out.grammar === undefined) delete out.grammar;
  }
  return out;
};

// The catalogue route, which is NOT behind the admin gate -- `crud.TABLE_CONFIG.keys()` plus two
// fields this screen deliberately does not read (`map_key_columns`, `kind`: other questions).
// ⚠️ Matched on the END of the path: `/admin/tables/config/raw` contains 「/tables」 too, and a
//    fixture that answered both would be feeding one route's body to another route's reader.
const TABLES = ['lot_event', 'lot_slot_wafer', 'dt_log', 'dt_map'];
// 🔴 THE SHAPE THE ROUTE ANSWERS WITH TODAY, both cells. `registered` is what the decorator
//    registered; `data` is every top-level def the AST found. The owner's mappers subclass
//    `BaseMapper`, so they are in the SECOND cell and in no other -- which is why a screen
//    reading only the first told them 「선택지 없음」 while their files sat right there.
const MAPPERS = {
  status: 'success',
  registered: ['build_dt_map'],
  data: [{ filename: 'lot_slot_wafer_mapper.py', module_name: 'mappers.lot_slot_wafer_mapper',
           functions: [{ name: 'build_lot_slot_wafer_rows', arguments: ['rows'], summary: '' }] }],
};
const isCatalogue = (call) => /\/tables$/.test(call.url.split('?')[0]);

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
  catalogueReads = 0;
}

async function suite(probe) {
  const before = { pass, fail };
  freshPage();
  const refreshChainRule = probe.probe.refreshChainRule;
  ok(typeof refreshChainRule === 'function', 'A admin.js imports, and its seating code is reachable');

  // ── A. the tab opens: no name yet, so the page asks for the list ────────────────────────
  answer = (call) => (call.url.includes('/admin/mappers/list')
    ? { status: 200, body: MAPPERS }
    : isCatalogue(call) ? { status: 200, body: { tables: TABLES } }
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
    ? { status: 200, body: MAPPERS }
    : isCatalogue(call) ? { status: 200, body: { tables: TABLES } }
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

  // ── I. the catalogue reaches the reference cells (C-101 ②) ──────────────────────────────
  // 🔴 THE OWNER'S OTHER SENTENCE: 「테이블이랑 맵퍼 설정은 리스트 좀 나오게해」. Measured in the
  //    shipped skeleton: SEVEN leaves are `hint: 'ref'` and none names a section, so the list has
  //    to come from what the registry declares -- and only the real declaration on the real page
  //    can prove that it does.
  const refBox = boxAt('trigger_table');
  const refListId = refBox ? refBox.attrs.list : '';
  const refOptions = all(panelRoot())
    // ⚠️ `id` is a PROPERTY here, not an attribute: `ontology_explorer_view` writes `list.id = …`
    //    and reading `attrs.id` found zero lists while the screen had one.
    .filter((el) => el.tagName === 'DATALIST' && (el.id || el.attrs.id) === refListId)
    .flatMap((el) => (el.children || []).map((o) => o.value));
  ok(Boolean(refListId) && refOptions.length > 0,
     `I the table cells offer the catalogue rather than a blank box (${refOptions.length} name(s))`);
  ok(TABLES.every((name) => refOptions.includes(name)),
     `I ... and it is the served catalogue, whole [${refOptions.join(',')}]`);
  // ── J. the mapper list carries BOTH cells, in two groups (C-101 ③) ──────────────────────
  // 🔴 THE OWNER'S RULE IS THE FIXTURE: `RULE` names its mapper with `mapper_module` +
  //    `mapper_function`, which is the spelling every rule in this box uses. Before this round
  //    the dropdown read `registered` only, so their file was not on it -- and the cell that
  //    held their mapper was a text box.
  const chooser = all(panelRoot()).find(
    (el) => el.tagName === 'SELECT' && el.attrs && el.attrs['data-value'] === 'mapper');
  const groups = chooser
    ? (chooser.children || []).filter((c) => c.tagName === 'OPTGROUP')
      .map((g) => g.getAttribute('label')) : [];
  ok(groups.length === 2, `J the mapper cell is a dropdown of two groups [${groups.join(',')}]`);
  const offeredMappers = chooser
    ? (chooser.children || []).flatMap((c) => (c.tagName === 'OPTGROUP' ? c.children : [c]))
      .map((o) => o.value) : [];
  ok(offeredMappers.includes('build_dt_map'),
     `J a decorator-registered name is offered [${offeredMappers.join(' | ')}]`);
  ok(offeredMappers.includes('mappers.lot_slot_wafer_mapper:build_lot_slot_wafer_rows'),
     'J ... and so is a function the FILES define, which is where this box`s mappers live');
  const picked2 = chooser
    ? (chooser.children || []).flatMap((c) => (c.tagName === 'OPTGROUP' ? c.children : [c]))
      .filter((o) => o.selected).map((o) => o.value) : [];
  ok(picked2.length === 1
     && picked2[0] === 'mappers.lot_slot_wafer_mapper:build_lot_slot_wafer_rows',
     `J the rule's own two-cell mapper is what the dropdown shows [${picked2.join(',')}]`);

  // ── D. editing: the document the save will send is rewritten ────────────────────────────
  type('target_table', 'lot_slot_wafer_v2');
  await flush();
  const afterEdit = held() || {};
  ok(afterEdit.target_table === 'lot_slot_wafer_v2', 'D a box changed rewrites the document');
  ok(afterEdit.lot_column === RULE.lot_column, 'D and rewrites nothing else');

  // ── H. the page's own clock does not swap out the form (C-101 ①) ────────────────────────
  // 🔴 THE OWNER'S SENTENCE, AS A WALK: 「체인 규칙 설정 쓰다가 지혼자 새로고침되서 초기화되는데?」
  //    `admin.js:408` fires every 30s and reaches `refreshChainRule()` WITH NO NAME. That read
  //    carries a list and no declaration, so drawing it removes the editor -- the boxes do not
  //    go stale, they go AWAY, and the rule deselects with them.
  // ⚠️ Called exactly as the timer calls it: no arguments. A harness that passed the background
  //    flag itself would be making the page's decision and would stay green with the page broken.
  answer = (call) => (call.url.includes('/admin/mappers/list')
    ? { status: 200, body: MAPPERS }
    : isCatalogue(call) ? { status: 200, body: { tables: TABLES } }
      : { status: 200, body: rawView(null) });
  await refreshChainRule();
  await flush();
  const kept = boxAt('target_table');
  ok(Boolean(kept) && kept.value === 'lot_slot_wafer_v2',
     `H the edited box survives the page's own refresh (${kept ? JSON.stringify(kept.value) : 'the form is GONE'})`);
  ok((held() || {}).target_table === 'lot_slot_wafer_v2',
     'H and the document the save would send is the edited one, not the served one');
  const underClock = byAttr('data-picker');
  const onClock = underClock
    ? underClock.children.filter((o) => o.getAttribute('selected')).map((o) => o.value) : [];
  ok(onClock.length === 1 && onClock[0] === RULE.name,
     `H the rule is still the one open -- deselecting IS the 「초기화」 (${JSON.stringify(onClock)})`);
  ok(Boolean(boxAt('lot_column')) || (held() || {}).lot_column === RULE.lot_column,
     'H and a cell the skeleton never heard of is still in the document');

  // 🔴 THE OTHER HALF, OR THE GUARD IS JUST 「IGNORE THE SERVER」. The page went for the list
  //    because the list can change under it; a rule added by somebody else must appear.
  answer = (call) => {
    if (call.url.includes('/admin/mappers/list')) return { status: 200, body: MAPPERS };
    if (isCatalogue(call)) return { status: 200, body: { tables: TABLES } };
    const body = rawView(null);
    body.rules = [...NAMES, 'a_rule_somebody_else_added'];
    return { status: 200, body };
  };
  await refreshChainRule();
  await flush();
  const grown = byAttr('data-picker');
  const names = grown ? grown.children.map((o) => o.value) : [];
  ok(names.includes('a_rule_somebody_else_added'),
     `H the list DOES refresh -- that is what the read was for (${JSON.stringify(names)})`);
  ok(names.indexOf(PICK_NAME) === -1,
     'H ... and refreshing it does not bring back 「아직 안 골랐다」 over an open rule');
  ok(Boolean(boxAt('target_table')) && boxAt('target_table').value === 'lot_slot_wafer_v2',
     'H ... while the edit is still untouched');

  // ── E. saving: one POST, the shape the route reads ──────────────────────────────────────
  let saved = null;
  answer = (call) => {
    if (call.url.includes('/admin/mappers/list')) return { status: 200, body: MAPPERS };
    if (isCatalogue(call)) return { status: 200, body: { tables: TABLES } };
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
  // 🔴 AND THE SAVE READ BACK THE RULE IT WROTE. Since C-101 ① a read that names no rule is the
  //    page's own clock and the panel steps around it -- so 「still selected, still filled」 is
  //    true of a save that forgot its own name too, and asserting only those would let that
  //    defect through. What only a NAMED read-back can do is two things: bring the server's
  //    version of the document to the screen, and let the screen say the write happened.
  const readBack = calls.filter((c) => c.method === 'GET' && c.url.includes('/admin/chain/rules/raw'));
  ok(readBack.length === 1 && askedName(readBack[0]) === RULE.name,
     `F the save reads back the rule it saved (${readBack.map(askedName).map((x) => JSON.stringify(x)).join(',') || 'no read'})`);
  ok(Boolean(byCls('chain-rule-saved')),
     'F and the screen says the write happened -- a save nobody can see is a save nobody trusts');

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

  // ── I (closing): the catalogue was read ONCE for this page ───────────────────────────────
  // 🔴 Six refreshes have happened by here -- opening, picking, two clock reads, a save and a new
  //    rule. The catalogue is the same answer to the same question every time, and asking it per
  //    rule opened is the shape S-72 already paid for once (44 requests, 76% thrown away).
  ok(catalogueReads === 1,
     `I the catalogue is read once for the page, not once per rule opened (${catalogueReads})`);

  // ── K. 판정 536 ④ — the screen SAYS what it counted ─────────────────────────────────────
  // 🔴 THE SILENCE IS THE DEFECT. After a migration a screen that says nothing reads as
  //    「끝났다」, and nothing on it tells 「0 left」 apart from 「never counted」.
  const marksOf = () => all(panelRoot())
    .filter((el) => String(el.className || '').split(/\s+/).includes('chain-rule-mark'))
    .map((el) => String(el.textContent || ''));
  const serve = (body) => { answer = (call) => (call.url.includes('/admin/mappers/list')
    ? { status: 200, body: MAPPERS }
    : isCatalogue(call) ? { status: 200, body: { tables: TABLES } }
      : { status: 200, body: body(call) }); };

  serve((call) => rawView(askedName(call)));
  await refreshChainRule(RULE.name);
  await flush();
  const shown = marksOf();
  ok(shown.includes('평면 1'),
     `K the screen counts the rules still written flat, off ONE response [${shown.join(' | ')}]`);
  // 🔴 판정 540·542. The route OMITS a name whose grammar it cannot read. Counting those as flat
  //    would put 「모른다」 back into 「평면」 inside the very screen that reports the migration.
  ok(shown.includes('문법 모름 1'),
     `K ... and an unreadable grammar is counted SEPARATELY, never folded into flat [${shown.join(' | ')}]`);

  // ㈎ 「제품이 모르는 칸 N 개 — 그대로 보존됩니다」. The cell exists because
  //    `rule_shape.to_declaration` gathers what the grammar does not model into ONE place
  //    (「흩어 두면 새 문법의 칸과 구별이 안 되고, 그러면 다음 사람이 그것을 문법이라 읽는다」).
  const UNIFIED = {
    name: RULE.name,
    on: { table: 'lot_event' },
    derive: { kind: 'mapper', mapper: 'lot_event_to_lot_slot_wafer' },
    into: { table: 'lot_slot_wafer' },
    extra: { lot_column: 'lot_id', slot_list_column: 'slots', list_delimiter: ',' },
  };
  serve(() => ({ ...rawView(RULE.name), grammar: 'unified',
                 declaration: UNIFIED, raw: JSON.stringify(UNIFIED, null, 2) }));
  await refreshChainRule(RULE.name);
  await flush();
  const carried = marksOf();
  ok(carried.includes('모르는 칸 3 · 보존'),
     `K a migrated rule says HOW MANY cells the product cannot model, and that they are kept `
     + `[${carried.join(' | ')}]`);

  // ── L. 판정 542 — 「모른다」 does not quietly become the flat form ────────────────────────
  // 🔴 THE TWO GRAMMARS ARE 27 CELLS AGAINST 7. Drawing the wrong one does not error: it puts
  //    empty boxes over real values, and a save then rewrites the rule into a grammar it is not.
  serve((call) => rawView(askedName(call)));
  await refreshChainRule('dt_log_to_dt_map');
  await flush();
  ok(!byCls('chain-rule-form'),
     'L a rule whose grammar cannot be read draws NO form, rather than falling to flat in silence');
  ok(Boolean(byCls('chain-rule-raw')),
     'L ... and the document itself still stands, so the operator can read and fix it');
  // 🔴 판정 543 ㉡. A form that just VANISHES reads as a broken screen. The reason is named,
  //    and it carries the rule's name because that is the place the operator has to go fix.
  const unread = marksOf();
  ok(unread.includes('문법 못 읽음 · dt_log_to_dt_map'),
     `L ... and the screen NAMES the rule it could not classify [${unread.join(' | ')}]`);
  // 🔴 판정 548 ④. A rule whose grammar cannot be read offers NO conversion - converting it would
  //    mean GUESSING which grammar it is, which is the same line 543 drew for the form.
  ok(!byAttr('data-action', 'convert-chain-rule'),
     'L ... and offers no conversion, because converting it would mean guessing its grammar');

  // ── M. 판정 548 — the conversion asks before it writes, and revert is the same door ─────────
  const convertBtn = () => byAttr('data-action', 'convert-chain-rule');
  // 🔴 A MUTANT MUST FAIL THE WALK, NOT THROW IT (this file's own rule, up at `held`).
  //    Under a mutant that removes the control, a bare `convertBtn().dispatch` ends the run and
  //    every later assertion goes unasked - which scores the mutant caught for the wrong reason.
  const clickConvert = () => { const b = convertBtn(); if (b) b.dispatch('click', {}); return Boolean(b); };
  serve((call) => rawView(askedName(call)));
  // 🔴 THE PICKER, NOT A DIRECT CALL. An earlier section pressed 「+ 규칙 추가」, and while the
  //    panel is drafting a NEW rule there is nothing stored to convert - so the control is
  //    correctly absent. Opening a rule the way an operator does is what leaves that mode.
  const pick = byAttr('data-picker');
  pick.value = RULE.name;
  pick.dispatch('change', { target: { value: RULE.name } });
  await flush();
  await flush();
  ok(Boolean(convertBtn()) && convertBtn().getAttribute('data-to') === 'unified',
     'M a rule stored flat offers ONE control, pointing at unified');
  ok(Boolean(convertBtn()) && convertBtn().textContent === '통합으로',
     `M ... and it says where it goes (${convertBtn() ? convertBtn().textContent : 'none'})`);

  // 🔴 THE DRY RUN COMES FIRST AND THE WRITE NEEDS A YES. 547: an unrevertable save must not land,
  //    and the operator is told what re-runs BEFORE it happens.
  let asked = null;
  globalThis.window.confirm = (text) => { asked = text; return false; };
  serve((call) => (call.url.includes('/chain/rules/grammar')
    ? { ok: true, name: RULE.name, to: 'unified', changed: true,
        reruns: { rows: 0, why: '규칙이 하던 일이 그대로입니다' } }
    : rawView(askedName(call))));
  calls.length = 0;
  clickConvert();
  await flush();
  await flush();
  const grammarPosts = calls.filter((c) => c.url.includes('/chain/rules/grammar'));
  ok(grammarPosts.length === 1 && grammarPosts[0].body && grammarPosts[0].body.dry_run === true,
     `M pressing it asks the server what WOULD happen, before anything is written (${grammarPosts.length})`);
  ok(grammarPosts.every((c) => c.body.dry_run === true),
     'M ... and saying no writes NOTHING - the refusal leaves the file alone');
  // 🔴 판정 549. 「세었고 0」 is not 「안 셌음」. Zero must read as 「없음」, never as a missing count.
  ok(typeof asked === 'string' && asked.includes('다시 돌 것 없음'),
     `M a counted zero is told as 「없음」, not as a number and not as silence (${JSON.stringify(asked)})`);

  // 🔴 판정 549 의 셋째 상태. The cell ABSENT means 「not counted」 - never drawn as 0.
  asked = null;
  serve((call) => (call.url.includes('/chain/rules/grammar')
    ? { ok: true, name: RULE.name, to: 'unified', changed: true,
        reruns: { why: '이 변환이 규칙의 실행 모양을 바꿉니다' } }
    : rawView(askedName(call))));
  clickConvert();
  await flush();
  await flush();
  ok(typeof asked === 'string' && asked.includes('안 셌음'),
     `M an ABSENT count says so, rather than being drawn as 0 (${JSON.stringify(asked)})`);
  // 🔴 WHY IT WAS NOT COUNTED IS THE SERVER'S SENTENCE. 「could not expand it」 and 「the shape
  //    moves」 are different facts, and a screen writing its own line would fold them into one.
  ok(typeof asked === 'string' && asked.includes('실행 모양을 바꿉니다'),
     `M ... and carries the server's reason verbatim, so the two 「not counted」 cases stay apart`);

  // 되돌리기는 «같은 문»입니다 - 판정 548: 왕복이 항등이라 반대 방향 변환이 곧 되돌리기입니다.
  globalThis.window.confirm = () => true;
  serve(() => ({ ...rawView(RULE.name), grammar: 'unified' }));
  await refreshChainRule(RULE.name);
  await flush();
  ok(Boolean(convertBtn()) && convertBtn().getAttribute('data-to') === 'flat',
     'M a rule now unified offers the way BACK through the same control, not a second button');
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
  // 🔴 C-101 ①, AS THE OWNER MET IT. Without this one line the page hands its periodic read to
  //    the panel as if a person had asked for it, and a read that names no rule draws no editor.
  ['the page hands its own 30-second read to the form, which then has no document to draw',
    s => s.replace('if (!name) opts.background = true;', '')],
  // 🔴 C-101 ②. The list never leaves the page, and seven table cells go back to being typed.
  ['the catalogue is read but never handed to the panel',
    s => s.replace('    ...(tables === null ? {} : { tables }),', '')],
  // ⚠️ S-207's class, on this route: `data` and `tables` are DIFFERENT QUESTIONS, and the mapper
  //    route next door answers with `data`. Reading the neighbour's cell empties the list while
  //    nothing errors.
  ['the catalogue is read from the cell the route next door uses',
    s => s.replace('    chainTableNames = body.tables.map(String);',
                   '    chainTableNames = (body.data || []).map(String);')],
  ['the catalogue is re-read every time a rule is opened',
    s => s.replace('  if (chainTableNames !== null) return chainTableNames;', '')],
  // 🔴 C-101 ③. S-207's shape, one route over: the page folds the answer itself and only the
  //    registered half survives -- which is the screen the owner met.
  ['the page folds the mapper answer itself, so only the registered half is offered',
    s => s.replace('  const mappers = mapperChoices(mapperBody);',
                   '  const mappers = mapperBody ? mapperBody.registered : null;')],
  // ⚠️ THE SAME LINE, SPELLED WRONG. 「!name」 is the whole judgement: a read that names a rule
  //    is a person opening it, and one that names none is the clock. Inverting it makes every
  //    real open silently refuse to draw, which is the failure mode nobody would guess from
  //    the fix's shape.
  ['the flag is raised on the reads that DO name a rule',
    s => s.replace('if (!name) opts.background = true;', 'if (name) opts.background = true;')],
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
