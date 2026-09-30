/**
 * 🏷️ C-56 — 탐색기를 «여는» 경로가 참조 오류 없이 도나. 대상을 IMPORT 해서 «실행»합니다.
 *
 * 🔴 THIS FILE EXISTS BECAUSE A REFERENCE ERROR REACHED PRODUCTION AND EVERY GATE WAS GREEN.
 *    C-54 retired the `/refusals` chain by deleting a SPAN -- a comment block through the end
 *    of a function -- and `loadCensus` lived inside that span while its call site did not.
 *    The screen threw `loadCensus is not defined` the moment it opened.
 *
 * 🔴 WHY NOTHING SAW IT: `ontology_explorer.js` opens with `import './ontology_explorer.css'`,
 *    so node could not load the file and no harness could name it. The gate had a harness for
 *    the STORE and one for the VIEW; the CONTROLLER -- the half that wires them and the only
 *    half that can throw on open -- had none, because it could not be imported.
 *    `lib/css_loader.mjs` answers that, and the module is imported BYTE-FOR-BYTE as it ships.
 *
 * ⚠️ 잘라쓰기 «아닙니다» — 사본도 스텁도 없습니다. CSS 지정자만 빈 모듈로 풀립니다(번들러가
 *    하는 일과 같은 것). 그리고 이 하니스가 재는 것은 «반환»이 아니라 「열면 던지나」입니다.
 *
 * Run: node client2/tests/explorer_open_path_harness.mjs
 */
import { register } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
register(pathToFileURL(join(HERE, 'lib', 'css_loader.mjs')).href);

let ran = 0;
let failed = 0;
const ok = (name, cond, detail = '') => {
  ran += 1;
  if (cond) console.log(`  PASS ${name}`);
  else { failed += 1; console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// ── the smallest DOM the view touches on an open ────────────────────────────────────
function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null),
    _text: '', _classes: [], dataset: Object.create(null), title: '', value: '',
    style: { setProperty() {} },
    get className() { return this._classes.join(' '); },
    set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: {
      add(...n) { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); },
      remove(...n) { node._classes = node._classes.filter((c) => !n.includes(c)); },
      contains(n) { return node._classes.includes(n); },
      toggle(n, on) { if (on) node.classList.add(n); else node.classList.remove(n); },
    },
    append(...items) { for (const i of items) if (i) this.children.push(i); },
    appendChild(c) { this.children.push(c); return c; },
    replaceChildren(...items) { this.children = items.filter(Boolean); },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    removeAttribute(k) { delete this.attrs[String(k)]; },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {}, removeEventListener() {}, focus() {}, scrollIntoView() {},
    closest() { return null; }, contains() { return false; },
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set innerHTML(v) { this._text = String(v); this.children = []; },
    get innerHTML() { return this._text; },
  };
  return node;
}
globalThis.document = {
  createElement: element,
  createDocumentFragment: () => element('#fragment'),
  createTextNode: (t) => { const n = element('#text'); n.textContent = t; return n; },
  addEventListener() {}, removeEventListener() {},
  querySelector() { return null; }, querySelectorAll() { return []; },
};
globalThis.requestAnimationFrame = (fn) => fn();
globalThis.window = { addEventListener() {}, removeEventListener() {}, location: { hash: '' } };

// 🔴 THE CENSUS BODY IS THE PUBLIC ROUTE'S OWN SHAPE (C-47), not a description of it.
const DECLARATION = { sources: [
  { source: 'die_inspection', relation: 'inspection_run',
    census: { source: 'die_inspection', relation: 'inspection_run',
              measured_at: '2026-09-10T00:00:00+00:00',
              relation_rows: { estimate: 10, exact: true, method: 'count(*)' },
              indexed_rows: { estimate: 4, exact: true, method: 'count(distinct row_id)' },
              not_yet: { estimate: 6, exact: true, method: 'relation_rows - indexed_rows' } } },
  { source: 'no_census_yet', relation: 'brand_new' },
] };
const COMPILE = {
  context_token: 'ctx:1',
  view_context: { mode: 'active', context_token: 'ctx:1' },
  active_snapshot: { snapshot_hash: '1', valid: true },
  selection: null, items: [], nodes: [], outbound: [], used_by: [], integrity: [],
  page: 1, total: 0, changes: [], edge_changes: [],
};

const seen = [];
globalThis.fetch = async (url) => {
  seen.push(String(url));
  return { ok: true, status: 200, json: async () => DECLARATION };
};
// ⚠️ THE STUB ANSWERS PER ROUTE. One body for every admin URL made the VIEW throw on the
//    authoring plan (`plan.fields` undefined) -- an instrument fault that would have read as
//    a product defect, which is the shape this harness exists to tell apart.
const AUTHORING = { physical_schema_file: 'table_config.json',
  config_source: { file: '/x/ledger_config.json', state: 'present' },
  steps: [], fields: [] };
const adminFetch = async (url) => {
  seen.push(String(url));
  const body = String(url).includes('/authoring') ? AUTHORING : COMPILE;
  return { ok: true, status: 200, json: async () => body };
};

const { createOntologyExplorerController } =
  await import('../src/ontology_explorer.js');

console.log('\n[1] opening the explorer does not throw');
let controller = null;
let opened = null;
try {
  controller = createOntologyExplorerController({
    root: element('div'), apiBase: '', adminFetch, showToast: () => {},
  });
  opened = await controller.refresh();
  ok('the open path runs to completion', true);
} catch (err) {
  ok('the open path runs to completion', false, String(err && err.message));
}
void opened;
{
  // 🔴 AND THIS IS THE ONE THAT BITES, measured against the broken bundle rather than assumed:
  //    `void loadCensus()` sits INSIDE the load's own try/catch, so a ReferenceError there does
  //    NOT escape -- it is swallowed into `REQUEST_FAILED` and the screen renders the failure
  //    state. 「던지나」 stayed GREEN on the shipped defect. What separates them is whether the
  //    open ENDED IN AN ERROR STATE, so that is what is asserted.
  const s = controller ? controller.getState() : null;
  ok('...and does not land in the failure state', !!s && !s.error,
    s ? String(s.error) : 'no state');
}

console.log('\n[2] the census reaches the store on that same open');
{
  // ⚠️ `loadCensus` is fired and NOT awaited — the list is drawn whether or not the counters
  //    arrive, which is the design. So the assertion has to let the microtasks run, or it
  //    would score the moment before the answer instead of the answer.
  for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r));
  const state = controller ? controller.getState() : null;
  ok('the controller has a state', !!state);
  const census = (state && state.census) || {};
  // 🔴 IT IS THE PUBLIC ROUTE, and it is asked for on open -- not on a click.
  ok('the declaration route was asked, without a token',
    seen.some((u) => u.includes('/api/ledger/declaration')), seen.join(' | '));
  eq('the census is keyed by source', 'die_inspection', Object.keys(census).sort().join(','));
  eq('...and the envelope is carried whole', 6,
    census.die_inspection && census.die_inspection.not_yet
      && census.die_inspection.not_yet.estimate);
  // ⚠️ A SOURCE WITH NO CENSUS IS ABSENT FROM THE MAP, never present-and-empty: absent is
  //    「안 쟀다」 and an empty object would draw as 「셌더니 아무것도 없다」.
  ok('a source with no census key is not in the map',
    !Object.prototype.hasOwnProperty.call(census, 'no_census_yet'), Object.keys(census).join(','));
}

console.log('\n[3] the retired route is not asked for');
{
  // 🔴 `/admin/ontology-explorer/refusals` answers 404 since S-113/S-114. Asking again would
  //    be a request whose only possible outcome is a silent failure.
  ok('nothing asks the retired refusals route',
    !seen.some((u) => u.includes('ontology-explorer/refusals')), seen.join(' | '));
}

// ═══════════════════════════════════════════════════════════════════════════════════════════
// [4] order af991aae5 — a save that reaches the file but does not LOAD says so.
//
// 🔴 THE OWNER: a declaration with a grammar error said 「Saved」 and then was not there. The
//    save writes the file either way (owner's ruling); the PUT's own `draft.validation_errors`
//    (config_drafts.py) says whether it will load, and the window never read it.
// 🔴 DRIVEN THROUGH THE CONTROLLER'S OWN CLICKS -- create-draft, then save-draft -- because the
//    decision lives in the save handler, not in a function a test could call around it.
// ═══════════════════════════════════════════════════════════════════════════════════════════
console.log('\n[4] saved but not applied');
const KEY = 'entity|quantity@1';
const REASON = { code: 'invalid_entity_ref', path: 'bundle.entities.quantity@1.class',
  message: 'must be one word or a list of words' };
const DRAFT = { draft_id: 'd1', target_key: KEY, target_kind: 'entity', target_id: 'quantity@1',
  revision: 1, raw: { class: 3, keys: ['quantity'] }, lifecycle_status: 'draft',
  validation_errors: [] };
const SELECTED = { ...COMPILE,
  selection: { key: KEY, canonical_id: 'quantity@1', kind: 'entity', context_token: 'ctx:1',
               raw: DRAFT.raw },
  items: [{ key: KEY, canonical_id: 'quantity@1', kind: 'entity', context_token: 'ctx:1' }] };
const walkAll = (n, out = []) => { out.push(n); for (const c of n.children || []) walkAll(c, out); return out; };

// `dropped`: the owner's case (order d763cb9f3). The loader leaves the saved declaration OUT,
// so after activation the snapshot has no such key: the mirror omits it and opening a draft
// by key answers `unknown_selection` -- the server's own refusal, spelled as it spells it.
async function saveWalk(create, { dropped = false } = {}) {
  const clicks = [];
  const root = element('div');
  root.addEventListener = (type, fn) => { if (type === 'click') clicks.push(fn); };
  const click = async (action) => {
    const target = { dataset: { action }, disabled: false };
    target.closest = () => target;
    for (const fn of clicks) await fn({ target });
  };
  const toasts = [];
  const opened = [];
  let reasons = [];
  let gone = false;
  const fetchOf = async (url, init = {}) => {
    const u = String(url);
    const path = u.split('?')[0];
    const method = init.method || 'GET';
    const id = (path.match(/\/drafts\/(d\d)/) || [])[1];
    const asked = (u.match(/draft_id=(d\d)/) || [])[1];
    const mirror = gone ? COMPILE : SELECTED;
    let body = asked ? { ...mirror, draft: { ...DRAFT, draft_id: asked, context_token: 'ctx:1' } } : mirror;
    if (u.includes('/authoring')) body = AUTHORING;
    else if (/\/drafts$/.test(path) && method === 'POST') {
      if (gone) {
        return { ok: false, status: 404, json: async () => ({ detail: { code: 'unknown_selection',
          path: 'selection', message: `selection '${KEY}' does not exist in this snapshot` } }) };
      }
      body = DRAFT;
    } else if (/\/drafts\/new$/.test(path)) {
      opened.push(JSON.parse(init.body));
      body = { ...DRAFT, draft_id: 'd2', creates_declaration: true, raw: {} };
    } else if (id && path.endsWith('/activate')) {
      gone = dropped && reasons.length > 0;
      body = { ok: true };
    } else if (id && method === 'PUT') {
      body = { draft: { ...DRAFT, draft_id: id, revision: 2,
                        raw: JSON.parse(JSON.parse(init.body).raw), validation_errors: reasons } };
    }
    return { ok: true, status: 200, json: async () => body };
  };
  const controller = create({ root, apiBase: '', adminFetch: fetchOf,
                              showToast: (text) => toasts.push(String(text)) });
  await controller.refresh();
  await click('create-draft');
  const out = {};
  reasons = [REASON];
  await click('save-draft');
  for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r));
  const headOf = () => walkAll(root).find((n) => n._classes?.includes('oe-not-applied'));
  const typed = () => { try { return JSON.parse(controller.getState().editorText); } catch (e) { return null; } };
  out.bad = { toasts: [...toasts], notApplied: controller.getState().notApplied,
              head: headOf()?.textContent || '', reopened: Boolean(controller.getState().draft),
              opened: [...opened], typed: typed() };
  toasts.length = 0;
  reasons = [];
  // Nothing open means nothing to save -- a mutant that loses the draft must FAIL the walk,
  // not throw it (a thrown run is scored as a hole, not a catch).
  if (controller.getState().draft) await click('save-draft');
  for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r));
  out.clean = { toasts: [...toasts], notApplied: controller.getState().notApplied,
                head: headOf()?.textContent || '' };
  return out;
}

function saveSuite(seen4) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  const { bad, clean } = seen4;
  say('S1 a save the loader will not load does not say "Saved"', !bad.toasts.includes('Saved'),
    bad.toasts.join(' | '));
  say('S2 ...it says saved but not applied, with the reason, at the head of the form',
    bad.head.startsWith('Saved but not applied') && bad.head.includes(REASON.path)
      && bad.head.includes(REASON.message), bad.head);
  say('S3 ...and the declaration is open again to be fixed', bad.reopened);
  say('S4 a clean save still says "Saved", and the line is gone',
    clean.toasts.includes('Saved') && clean.notApplied === null && clean.head === '',
    `${clean.toasts.join(' | ')} · ${JSON.stringify(clean.notApplied)} · ${clean.head}`);
  return { ran: names.length, names, failures };
}

function droppedSuite(seen4) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  const { bad, clean } = seen4;
  say('D1 a save the load leaves OUT says neither "Saved" nor unknown_selection',
    !bad.toasts.includes('Saved') && !bad.toasts.some((t) => t.includes('unknown_selection')),
    bad.toasts.join(' | '));
  say('D2 ...it opens again on the text just saved, as the declaration it is',
    bad.opened.length === 1 && bad.opened[0].kind === 'entity'
      && bad.opened[0].canonical_id === 'quantity@1'
      && JSON.stringify(bad.typed) === JSON.stringify(DRAFT.raw),
    `${JSON.stringify(bad.opened)} · ${JSON.stringify(bad.typed)}`);
  say('D3 ...with "Saved but not applied" and the reason at the head of its form',
    bad.head.startsWith('Saved but not applied') && bad.head.includes(REASON.message), bad.head);
  say('D4 fixed and saved, it says "Saved"', clean.toasts.includes('Saved') && clean.notApplied === null,
    `${clean.toasts.join(' | ')} · ${JSON.stringify(clean.notApplied)}`);
  return { ran: names.length, names, failures };
}

const saveBase = saveSuite(await saveWalk(createOntologyExplorerController));
ran += saveBase.ran;
failed += saveBase.failures.length;
console.log('\n[4b] saved, and the load left it out');
const droppedBase = droppedSuite(await saveWalk(createOntologyExplorerController, { dropped: true }));
ran += droppedBase.ran;
failed += droppedBase.failures.length;

{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const SUBJECT = join(HERE, '..', 'src', 'ontology_explorer.js');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const MUTANTS = [
    { id: 'M1', what: 'the save ignores validation_errors and says "Saved"', catches: 'S1 a save the loader',
      mutate: (text) => swap(text, "        if (!unapplied.length) showToast('Saved', 'success');",
                             "        showToast('Saved', 'success');") },
    { id: 'M2', what: 'the not-applied line is never recorded', catches: 'S2 ...it says saved',
      mutate: (text) => swap(text,
        "        dispatch({ type: 'SAVE_NOT_APPLIED', key: targetKey, errors: unapplied });\n", '') },
  ];
  const run = async (m) => saveSuite(await saveWalk(
    (await loadWithProbe(SUBJECT, { mutate: m.mutate })).module.createOntologyExplorerController));
  const scored = await scoreMutants(MUTANTS, run,
    { baselineRan: saveBase.ran, baselineNames: saveBase.names,
      title: '\n  [4] mutants — each must be caught by the check it names.' });
  ran += MUTANTS.length;
  failed += scored.wrong;
  // 🔴 The owner's case, put back: the refused reopen is only a toast again.
  const DROPPED = [
    { id: 'M3', what: 'a save the load left out is reopened by key, and only a toast remains',
      catches: ['D1 a save the load leaves OUT', 'D2 ...it opens again'],
      mutate: (text) => swap(text, "      if (error?.detail?.code === 'unknown_selection' && savedRaw !== undefined) {",
                             '      if (false) {') },
  ];
  const runDropped = async (m) => droppedSuite(await saveWalk(
    (await loadWithProbe(SUBJECT, { mutate: m.mutate })).module.createOntologyExplorerController,
    { dropped: true }));
  const scoredDropped = await scoreMutants(DROPPED, runDropped,
    { baselineRan: droppedBase.ran, baselineNames: droppedBase.names,
      title: '\n  [4b] mutants — each must be caught by the check it names.' });
  ran += DROPPED.length;
  failed += scoredDropped.wrong;
}

// ═══════════════════════════════════════════════════════════════════════════════════════════
// [5] order 791c0f45e — a leaf the server marks `reshapes` asks for THIS draft's form, unsaved.
//
// 🔴 DRIVEN THROUGH THE CONTROLLER'S OWN EVENTS (input, change, click). The leaf names below are
//    the fixture's; the screen names none — which leaf reshapes is the plan's `reshapes` mark.
// ═══════════════════════════════════════════════════════════════════════════════════════════
console.log('\n[5] the draft\'s form, asked without a save');
const LEAF = 'bundle.entities.quantity@1.class';
const PLAIN = 'bundle.entities.quantity@1.note';
const planRow = (path, value, reshapes) => ({ path, value, reshapes, label: path, state: 'answered',
  tier: 'constrained_input', candidates: null, refusals: [] });
const KEYS_OF = { die: ['x', 'y'], wafer: ['lot', 'wafer'] };
const planFor = (raw) => ({ ...AUTHORING, fields: [
  planRow(LEAF, raw.class ?? null, true), planRow(PLAIN, raw.note ?? null, false),
  ...(KEYS_OF[raw.class] || []).map((k) => planRow(`bundle.entities.quantity@1.keys.${k}`, null, false))] });
const SCHEMA = { ...AUTHORING, authorable_kinds: [{ id: 'entity', section: 'entities' }], skeleton: null };

async function reshapeWalk(create, { refuse = false } = {}) {
  const on = { click: [], change: [], input: [] };
  const root = element('div');
  root.addEventListener = (type, fn) => { if (on[type]) on[type].push(fn); };
  const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r)); };
  const fire = async (type, target) => { for (const fn of on[type]) await fn({ target }); await settle(); };
  const click = (action) => { const t = { dataset: { action }, disabled: false }; t.closest = () => t; return fire('click', t); };
  const field = (path, value) => ({ dataset: { action: 'edit-field', value: path }, value });
  const posts = [];
  const toasts = [];
  let saved = DRAFT.raw;
  const gets = [];              // the class each plan GET was answered for
  const fetchOf = async (url, init = {}) => {
    const u = String(url);
    const path = u.split('?')[0];
    const method = init.method || 'GET';
    // The load after a draft opens asks with its id, and the draft rides back on that answer.
    let body = /draft_id=d1/.test(u) ? { ...SELECTED, draft: { ...DRAFT, raw: saved, context_token: 'ctx:1' } } : SELECTED;
    if (/\/drafts\/d1$/.test(path) && method === 'PUT') {
      saved = JSON.parse(JSON.parse(init.body).raw);
      body = { draft: { ...DRAFT, revision: 2, raw: saved, validation_errors: [] } };
    } else if (path.endsWith('/activate')) body = { ok: true };
    else if (path.endsWith('/authoring/schema')) body = SCHEMA;
    else if (path.endsWith('/authoring/plan') && method === 'POST') {
      const sent = JSON.parse(init.body);
      posts.push(sent);
      if (refuse) {
        return { ok: false, status: 422, json: async () => ({ detail: { code: 'invalid_json',
          path: 'raw', message: 'raw is not JSON' } }) };
      }
      body = planFor(JSON.parse(sent.raw));
    } else if (path.endsWith('/authoring/plan')) { gets.push(saved.class); body = planFor(saved); }
    else if (/\/drafts$/.test(path) && method === 'POST') body = DRAFT;
    return { ok: true, status: 200, json: async () => body };
  };
  const controller = create({ root, apiBase: '', adminFetch: fetchOf, showToast: (t) => toasts.push(String(t)) });
  await controller.refresh();
  await settle();
  await click('create-draft');
  const keysNow = () => ((controller.getState().authoring || {}).fields || [])
    .map((r) => r.path).filter((p) => p.includes('.keys.')).map((p) => p.split('.').pop()).join(',');
  const out = { opened: posts.length };
  await fire('input', field(LEAF, 'd'));
  await fire('input', field(LEAF, 'die'));
  out.typed = posts.length;
  await fire('change', field(LEAF, 'die'));
  out.picked = posts.length;
  out.sent = posts[0] || null;
  out.text = controller.getState().editorText;
  out.keysDie = keysNow();
  out.toasts = [...toasts];
  await fire('input', field(PLAIN, 'hello'));
  await fire('change', field(PLAIN, 'hello'));
  out.plain = posts.length;
  await fire('change', field(LEAF, 'die'));
  out.same = posts.length;
  await fire('input', field(LEAF, 'wafer'));
  await fire('change', field(LEAF, 'wafer'));
  out.again = posts.length;
  out.keysWafer = keysNow();
  if (controller.getState().draft) await click('save-draft');
  out.afterSave = posts.length;
  out.keysSaved = keysNow();
  out.savedGet = gets.includes('wafer');   // a plan GET answered for the SAVED class
  out.toastsAfter = [...toasts];
  return out;
}

function reshapeSuite(seen5, refused) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  say('R1 opening the draft asks nothing: its values are the plan\'s', seen5.opened === 0, String(seen5.opened));
  say('R2 typing asks nothing — only a committed pick', seen5.typed === 0, String(seen5.typed));
  say('R3 the pick asks once', seen5.picked === 1, String(seen5.picked));
  say('R4 ...with the GET\'s selection, this draft and the editor text as it stands',
    !!seen5.sent && seen5.sent.selection === KEY && seen5.sent.draft_id === DRAFT.draft_id
      && seen5.sent.raw === seen5.text, JSON.stringify(seen5.sent));
  say('R5 the answer\'s fields take the plan\'s place — the key fields, unsaved', seen5.keysDie === 'x,y', seen5.keysDie);
  say('R6 a leaf the plan does not mark asks nothing', seen5.plain === 1, String(seen5.plain));
  say('R7 the same value again asks nothing', seen5.same === 1, String(seen5.same));
  say('R8 another value asks once more, and the fields follow it',
    seen5.again === 2 && seen5.keysWafer === 'lot,wafer', `${seen5.again} ${seen5.keysWafer}`);
  say('R10 after the save the plan GET draws the same fields, and nothing more is asked',
    seen5.savedGet && seen5.afterSave === seen5.again && seen5.keysSaved === 'lot,wafer',
    `${seen5.savedGet} ${seen5.afterSave} ${seen5.keysSaved} ${seen5.toastsAfter.join(' | ')}`);
  say('R9 a refused ask says the server\'s words, and the saved form stays',
    refused.toasts.some((t) => t.includes('raw is not JSON')) && refused.keysDie === '', `${refused.toasts.join(' | ')} · ${refused.keysDie}`);
  return { ran: names.length, names, failures };
}

const reshapeRun = async (create) => reshapeSuite(await reshapeWalk(create), await reshapeWalk(create, { refuse: true }));
const reshapeBase = await reshapeRun(createOntologyExplorerController);
ran += reshapeBase.ran;
failed += reshapeBase.failures.length;
{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const SUBJECT = join(HERE, '..', 'src', 'ontology_explorer.js');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const MUTANTS = [
    { id: 'M5', what: 'every keystroke asks', catches: 'R2',
      mutate: (text) => swap(text, "  root.addEventListener('input', (event) => {\n",
                             "  root.addEventListener('input', (event) => {\n    void reshapeIfMoved();\n") },
    { id: 'M6', what: 'the answer is not drawn', catches: 'R5',
      mutate: (text) => swap(text, "        dispatch({ type: 'AUTHORING_RECEIVED', plan });\n        dispatch({ type: 'FIELDS_DROPPED'",
                             "        void plan;\n        dispatch({ type: 'FIELDS_DROPPED'") },
    { id: 'M7', what: 'the saved text is sent instead of the draft', catches: 'R4',
      mutate: (text) => swap(text, 'draft_id: draft.draft_id, raw: state.editorText }',
                             'draft_id: draft.draft_id, raw: JSON.stringify(draft.raw) }') },
    { id: 'M8', what: 'a refusal is swallowed', catches: 'R9',
      mutate: (text) => swap(text, "      if (turn === reshapeTurn) showToast(errorMessage(error), 'error');",
                             '      void error;') },
  ];
  const run = async (m) => reshapeRun(
    (await loadWithProbe(SUBJECT, { mutate: (t) => m.mutate(t.replace(/\r\n/g, '\n')) })).module.createOntologyExplorerController);
  const scored = await scoreMutants(MUTANTS, run,
    { baselineRan: reshapeBase.ran, baselineNames: reshapeBase.names,
      title: '\n  [5] mutants — each must be caught by the check it names.' });
  ran += MUTANTS.length;
  failed += scored.wrong;

  // The rule itself, in the store: only a leaf the plan marks, only when its draft value moved.
  const STORE = join(HERE, '..', 'src', 'ontology_explorer_store.js');
  const tools = { splitBundlePath: (p) => String(p).replace(/^bundle\./, '').split('.'),
    getAtPath: (o, steps) => steps.reduce((v, k) => (v == null ? undefined : v[k]), o) };
  const at = (klass, note) => ({ draft: { target_kind: 'entity', target_id: 'quantity@1' },
    editorText: JSON.stringify({ class: klass, note }),
    authoringSchema: { authorable_kinds: [{ id: 'entity', section: 'entities' }] } });
  const ruleSuite = (fn) => {
    const names = [];
    const failures = [];
    const say = (name, cond) => { names.push(name); if (cond) console.log(`  PASS ${name}`); else { failures.push(name); console.log(`  FAIL ${name}`); } };
    const plan = { fields: [{ path: LEAF, value: 'die', reshapes: true }, { path: PLAIN, value: null, reshapes: false }] };
    say('Q1 no draft, nothing moved', fn({ draft: null }, plan, tools) === false);
    say('Q2 the marked leaf as planned: nothing moved', fn(at('die', null), plan, tools) === false);
    say('Q3 the marked leaf changed: moved', fn(at('wafer', null), plan, tools) === true);
    say('Q4 an unmarked leaf changed: nothing moved', fn(at('die', 'x'), plan, tools) === false);
    return { ran: names.length, names, failures };
  };
  const ruleBase = ruleSuite((await import('../src/ontology_explorer_store.js')).draftReshapesPlan);
  ran += ruleBase.ran;
  failed += ruleBase.failures.length;
  const RULE_MUTANTS = [
    { id: 'M9', what: 'the mark is not read — any leaf asks', catches: 'Q4',
      mutate: (text) => swap(text, '  return ((plan && plan.fields) || []).some((row) => row && row.reshapes === true\n',
                             '  return ((plan && plan.fields) || []).some((row) => row\n') },
    { id: 'M10', what: 'the planned value is not compared', catches: 'Q2',
      mutate: (text) => swap(text, '      !== JSON.stringify(row.value ?? null));', "      !== 'x');") },
  ];
  const scoredRule = await scoreMutants(RULE_MUTANTS, async (m) => ruleSuite(
    (await loadWithProbe(STORE, { mutate: (t) => m.mutate(t.replace(/\r\n/g, '\n')) })).module.draftReshapesPlan),
    { baselineRan: ruleBase.ran, baselineNames: ruleBase.names,
      title: '\n  [5] rule mutants — each must be caught by the check it names.' });
  ran += RULE_MUTANTS.length;
  failed += scoredRule.wrong;
}

// ═══════════════════════════════════════════════════════════════════════════════════════════
// [6] order 8771e43ac 2 — the fields the server dropped because the declaration's own choice
//     switched them off: said at the head of the form, from the unsaved plan and from the save.
// ═══════════════════════════════════════════════════════════════════════════════════════════
console.log('\n[6] what the server dropped, said');
const COLUMN = 'bundle.entities.quantity@1.column';
async function fieldDropWalk(create) {
  const on = { click: [], change: [], input: [] };
  const root = element('div');
  root.addEventListener = (type, fn) => { if (on[type]) on[type].push(fn); };
  const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r)); };
  const fire = async (type, target) => { for (const fn of on[type]) await fn({ target }); await settle(); };
  const click = (action) => { const t = { dataset: { action }, disabled: false }; t.closest = () => t; return fire('click', t); };
  const field = (at, value) => ({ dataset: { action: 'edit-field', value: at }, value });
  // The server's rule, in the fixture: a constant has no column, so a column beside it goes.
  const dropOf = (raw) => (raw.class === 'constant' && raw.column !== undefined
    ? { kept: Object.fromEntries(Object.entries(raw).filter(([k]) => k !== 'column')), dropped: [{ path: COLUMN, value: raw.column }] }
    : { kept: raw, dropped: [] });
  let saved = { class: 'column', column: 'lot_id', keys: ['quantity'] };
  const plan = (raw) => ({ ...AUTHORING, fields: [planRow(LEAF, raw.class ?? null, true),
    ...(raw.column !== undefined ? [planRow(COLUMN, raw.column, false)] : [])] });
  const fetchOf = async (url, init = {}) => {
    const u = String(url);
    const path = u.split('?')[0];
    const method = init.method || 'GET';
    const draftNow = { ...DRAFT, raw: saved, context_token: 'ctx:1' };
    let body = /draft_id=d1/.test(u) ? { ...SELECTED, draft: draftNow } : SELECTED;
    if (/\/drafts\/d1$/.test(path) && method === 'PUT') {
      const { kept, dropped } = dropOf(JSON.parse(JSON.parse(init.body).raw));
      saved = kept;
      body = { ...DRAFT, revision: 2, raw: saved, validation_errors: [], dropped_fields: dropped };
    } else if (path.endsWith('/activate')) body = { ok: true };
    else if (/\/drafts$/.test(path) && method === 'POST') body = draftNow;
    else if (path.endsWith('/authoring/schema')) body = SCHEMA;
    else if (path.endsWith('/authoring/plan') && method === 'POST') {
      const { kept, dropped } = dropOf(JSON.parse(JSON.parse(init.body).raw));
      body = { ...plan(kept), dropped_fields: dropped };
    } else if (path.endsWith('/authoring/plan')) body = { ...plan(saved), dropped_fields: [] };
    return { ok: true, status: 200, json: async () => body };
  };
  const controller = create({ root, apiBase: '', adminFetch: fetchOf, showToast: () => {} });
  await controller.refresh();
  await settle();
  await click('create-draft');
  const line = () => {
    const box = walkAll(root).find((n) => n._classes?.includes('oe-dropped'));
    return box ? box.textContent : '';
  };
  const typed = () => { try { return JSON.parse(controller.getState().editorText); } catch (e) { return {}; } };
  const out = {};
  await fire('input', field(LEAF, 'constant'));
  await fire('change', field(LEAF, 'constant'));
  out.planned = line();
  await click('save-draft');
  out.saved = line();
  out.typedAfter = typed();
  out.savedRaw = saved;
  await click('save-draft');
  out.again = line();
  return out;
}
function fieldDropSuite(seen6) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  const said = 'entities › quantity@1 › column = "lot_id"';
  say('X1 before the save, the plan says what the save will drop, in the declaration\'s words',
    seen6.planned.startsWith('Dropped on save') && seen6.planned.includes(said), seen6.planned);
  say('X2 the save says what it dropped', seen6.saved.startsWith('Dropped') && !seen6.saved.startsWith('Dropped on save')
    && seen6.saved.includes(said), seen6.saved);
  say('X3 the form is the saved body: no column', !('column' in seen6.typedAfter) && !('column' in seen6.savedRaw),
    JSON.stringify(seen6.typedAfter));
  say('X4 saved again, nothing is dropped and nothing is said', seen6.again === '', seen6.again);
  return { ran: names.length, names, failures };
}
const fieldDropBase = fieldDropSuite(await fieldDropWalk(createOntologyExplorerController));
ran += fieldDropBase.ran;
failed += fieldDropBase.failures.length;
{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const SUBJECT = join(HERE, '..', 'src', 'ontology_explorer.js');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const MUTANTS = [
    { id: 'M11', what: 'the save\'s dropped fields are not read', catches: 'X2',
      mutate: (text) => swap(text, "fields: record.dropped_fields, saved: true", "fields: [], saved: true") },
    { id: 'M12', what: 'the plan\'s dropped fields are not read', catches: 'X1',
      mutate: (text) => swap(text, "fields: plan.dropped_fields, saved: false", "fields: [], saved: false") },
  ];
  const scored = await scoreMutants(MUTANTS, async (m) => fieldDropSuite(await fieldDropWalk(
    (await loadWithProbe(SUBJECT, { mutate: (t) => m.mutate(t.replace(/\r\n/g, '\n')) })).module.createOntologyExplorerController)),
    { baselineRan: fieldDropBase.ran, baselineNames: fieldDropBase.names,
      title: '\n  [6] mutants — each must be caught by the check it names.' });
  ran += MUTANTS.length;
  failed += scored.wrong;
}

// ═══════════════════════════════════════════════════════════════════════════════════════════
// [7] lead 9073d7225 ㉰ — a step of the form's path bar goes where the map's own door goes.
//
// 🔴 explorer_path_bar_harness hands the widget its action itself, so it cannot see which one the
//    PAGE hands it: the lead swapped the page's 'map-goto' for 'select' and it stayed green. Here
//    the page builds the bar, the page's own hover fills it and the page's own click takes a step.
// ⚠️ This DOM finds nothing by selector, so the root answers the one seat the bar asks for with a
//    mount the harness holds, and the hover hands in two form nodes as the form nests them.
// ═══════════════════════════════════════════════════════════════════════════════════════════
console.log('\n[7] a form path step is the map\'s door');
async function pathBarWalk(create) {
  const on = { click: [], mouseover: [] };
  const root = element('div');
  root.addEventListener = (type, fn) => { if (on[type]) on[type].push(fn); };
  const mount = element('div');
  root.querySelector = (sel) => (sel === '.oe-bucket--form .oe-path-mount' ? mount : null);
  const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r)); };
  const controller = create({ root, apiBase: '', adminFetch, showToast: () => {} });
  await controller.refresh();
  await settle();
  const formNode = (at, parent) => {
    const n = element('div');
    n.className = 'oe-node';
    n.dataset.path = at;
    n.nodeType = 1;
    n.parentNode = parent || null;
    return n;
  };
  const outer = formNode('bundle.entities.quantity@1');
  const inner = formNode('bundle.entities.quantity@1.keys', outer);
  for (const fn of on.mouseover) fn({ target: { closest: () => inner } });
  const steps = walkAll(mount).filter((n) => n._classes?.includes('oe-path-step'));
  const pick = steps.find((n) => n.tagName === 'BUTTON') || null;
  if (pick) {
    pick.closest = () => pick;
    for (const fn of on.click) await fn({ target: pick });
    await settle();
  }
  return { steps: steps.map((n) => n.textContent), picked: pick ? pick.dataset.value : null,
           cursor: controller.getState().mapCursor };
}
function pathBarSuite(seen7) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  // The canary: with no step drawn the click below would score nothing.
  say('Y1 the page\'s hover draws the hovered node\'s trail in the form\'s bar',
    seen7.steps.join(' › ') === 'entities › quantity@1 › keys', seen7.steps.join(' › '));
  say('Y2 a picked step lands the map cursor on that step\'s path',
    seen7.picked === 'bundle.entities.quantity@1' && seen7.cursor === seen7.picked,
    `picked ${seen7.picked}, cursor ${seen7.cursor}`);
  return { ran: names.length, names, failures };
}
const pathBarBase = pathBarSuite(await pathBarWalk(createOntologyExplorerController));
ran += pathBarBase.ran;
failed += pathBarBase.failures.length;
{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const SUBJECT = join(HERE, '..', 'src', 'ontology_explorer.js');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const MUTANTS = [
    { id: 'M13', what: 'the page hands the form\'s bar the declaration pick (the lead\'s swap)', catches: 'Y2',
      mutate: (text) => swap(text, "new PathBar(null, { doc: document, action: 'map-goto' })",
        "new PathBar(null, { doc: document, action: 'select' })") },
  ];
  const scored = await scoreMutants(MUTANTS, async (m) => pathBarSuite(await pathBarWalk(
    (await loadWithProbe(SUBJECT, { mutate: (t) => m.mutate(t.replace(/\r\n/g, '\n')) })).module.createOntologyExplorerController)),
    { baselineRan: pathBarBase.ran, baselineNames: pathBarBase.names,
      title: '\n  [7] mutants — each must be caught by the check it names.' });
  ran += MUTANTS.length;
  failed += scored.wrong;
}

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
