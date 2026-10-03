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
import { readFileSync } from 'node:fs';

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
    _text: '', _classes: [], dataset: Object.create(null), title: '', value: '', _on: Object.create(null),
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
    // Listeners are kept so a walk can fire a part's own control (the branch picker, [8]).
    addEventListener(type, fn) { (this._on[type] ||= []).push(fn); },
    removeEventListener() {}, focus() {}, scrollIntoView() {},
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
  // 🔴 43a738d58 ②: what the SCREEN shows is the raw window as last drawn (dom_patch syncs its value
  //    on every render), so it tells a keystroke that redrew from one that only moved the draft.
  const rawShown = () => { const t = walkAll(root).find((n) => n.dataset && n.dataset.action === 'edit-raw'); return t ? String(t.value) : null; };
  const shownBefore = rawShown();
  await fire('input', field(LEAF, 'd'));
  out.firstTyped = { draft: controller.getState().editorText, shown: rawShown(), before: shownBefore,
    dirty: controller.getState().dirty,
    save: !!walkAll(root).find((n) => n.dataset && n.dataset.action === 'save-draft' && !n.disabled) };
  await fire('input', field(LEAF, 'die'));
  out.typed = posts.length;
  out.shownWhileTyping = rawShown();
  await fire('change', field(LEAF, 'die'));
  out.shownAfterChange = rawShown();
  out.draftAfterChange = controller.getState().editorText;
  out.picked = posts.length;
  out.sent = posts[0] || null;
  out.text = controller.getState().editorText;
  out.keysDie = keysNow();
  out.toasts = [...toasts];
  await fire('input', field(PLAIN, 'hello'));
  await fire('change', field(PLAIN, 'hello'));
  out.plain = posts.length;
  // A box that does not reshape the form: no plan answer will redraw, so only leaving the box can.
  out.shownAfterPlain = rawShown();
  out.draftAfterPlain = controller.getState().editorText;
  await fire('change', field(LEAF, 'die'));
  out.same = posts.length;
  await fire('input', field(LEAF, 'wafer'));
  await fire('change', field(LEAF, 'wafer'));
  out.again = posts.length;
  out.keysWafer = keysNow();
  if (controller.getState().draft) await click('save-draft');
  out.savedClass = saved.class;
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
  // ── 43a738d58 ②: typing changes the draft, not the screen — the raw window's rule ──────────
  const ft = seen5.firstTyped || {};
  say('R11 a keystroke in a form box moves the draft and draws nothing',
    ft.draft !== ft.before && ft.draft.includes('"d"') && ft.shown === ft.before
      && seen5.shownWhileTyping === ft.before, `${JSON.stringify(ft.shown)} vs ${JSON.stringify(ft.draft)}`);
  say('R12 leaving the box draws once: the screen shows what was typed — a box that reshapes nothing too',
    seen5.shownAfterChange === seen5.draftAfterChange && seen5.shownAfterChange.includes('"die"')
      && seen5.shownAfterPlain === seen5.draftAfterPlain && String(seen5.shownAfterPlain).includes('"hello"'),
    `${JSON.stringify(seen5.shownAfterChange)} | ${JSON.stringify(seen5.shownAfterPlain)}`);
  say('R13 the first keystroke marks the draft changed, and Save is on', ft.dirty === true && ft.save === true,
    `${ft.dirty} ${ft.save}`);
  say('R14 what Save writes is what was typed', seen5.savedClass === 'wafer', String(seen5.savedClass));
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
    // ── 43a738d58 ② ──────────────────────────────────────────────────────────────────────
    { id: 'T1', what: 'every keystroke draws the whole screen again', catches: 'R11',
      mutate: (text) => swap(text, '    if (typing) return state;\n', '') },
    { id: 'T2', what: 'leaving the box draws nothing', catches: 'R12',
      mutate: (text) => swap(text, "    if (TYPED_BOXES.has(event.target?.dataset?.action)) dispatch({ type: 'EDITOR_CHANGED', text: state.editorText });\n", '') },
    { id: 'T3', what: 'the typing mark never clears, so the screen stops drawing', catches: 'R12',
      mutate: (text) => swap(text, '    try { onInput(event); } finally { typing = false; }', '    onInput(event);') },
  ];
  const run = async (m) => reshapeRun(
    (await loadWithProbe(SUBJECT, { mutate: (t) => m.mutate(t) })).module.createOntologyExplorerController);
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
    (await loadWithProbe(STORE, { mutate: (t) => m.mutate(t) })).module.draftReshapesPlan),
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
    (await loadWithProbe(SUBJECT, { mutate: (t) => m.mutate(t) })).module.createOntologyExplorerController)),
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
    (await loadWithProbe(SUBJECT, { mutate: (t) => m.mutate(t) })).module.createOntologyExplorerController)),
    { baselineRan: pathBarBase.ran, baselineNames: pathBarBase.names,
      title: '\n  [7] mutants — each must be caught by the check it names.' });
  ran += MUTANTS.length;
  failed += scored.wrong;
}

// ═════════════════════════════════════════════════════════════════
// [8] lead 64c380aeb — the branch the screen reads.
//
// 🔴 ONE SEAT, EVERY REQUEST. `state.world` is the screen's world and every request goes through the two
//    wrappers built on it; one that goes round them reads the default beside a branch's picture and
//    nothing errors. So the walk records EVERY URL, admin and public, and the gate is 「all of them」.
// ⚠️ Default is the day before: the same walk (open, then one create-draft) against the source before the
//    round, captured in fixtures/explorer_requests.before.json.
// ═════════════════════════════════════════════════════════════════
console.log('\n[8] the branch the screen reads');
const REQUESTS_BEFORE = JSON.parse(readFileSync(join(HERE, 'fixtures', 'explorer_requests.before.json'), 'utf8'));
const PREVIEW = { world: 'w2', schema: 'ledger_w2', atoms: 7, files: ['a.json', 'b.json'] };
// GET /worlds as the server shapes it (6bfb6d4be), the operating world NOT the default - so an empty pick
// and a pick of `default` are different requests (lead 120450931 ①). History is oldest first, as written.
const WORLDS = { worlds: ['default', 'w1'], operating: 'w1', beneath: { w1: ['default'] },
  history: [{ world: 'default', by: 'operator', at: '2026-10-01T00:00:00+00:00' },
    { world: 'w1', by: 'operator', at: '2026-10-02T00:00:00+00:00' }] };
// The token gate answers with a bare sentence; a delete refusal with the route's own object.
const TOKEN_REFUSED = 'Admin token required.';
const DELETE_REFUSED = "ledger world 'w2' is what 'w3' stands on";
async function branchWalk(create, { confirmDelete = true, typed = null, refuseKeep = false, pick = 'w1',
  beneath = null, confirmOperate = true, refuseOperate = false, refuseDelete = false } = {}) {
  const urls = [];
  const puts = [];
  const operated = [];
  const toasts = [];
  const clicks = [];
  const inputs = [];
  const root = element('div');
  root.addEventListener = (type, fn) => { if (type === 'click') clicks.push(fn); if (type === 'input') inputs.push(fn); };
  const mount = element('div');
  root.querySelector = (sel) => (sel === '.oe-branch-mount' ? mount : null);
  const click = async (action) => {
    const target = { dataset: { action }, disabled: false };
    target.closest = () => target;
    for (const fn of clicks) await fn({ target });
  };
  const fire = (node, type) => { for (const fn of (node && node._on[type]) || []) fn({ target: node }); };
  const part = (cls) => walkAll(mount).find((n) => n._classes.includes(cls)) || null;
  const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r)); };
  const reply = (body) => ({ ok: true, status: 200, json: async () => body });
  const adminOf = async (url, init = {}) => {
    const u = String(url);
    const method = init.method || 'GET';
    urls.push(`admin ${method} ${u}`);
    const path = u.split('?')[0];
    const asked = (u.match(/draft_id=(d\d)/) || [])[1];
    if (path.endsWith('/worlds/operating')) {
      const world = JSON.parse(init.body).world;
      operated.push(world);
      if (refuseOperate) return { ok: false, status: 401, json: async () => ({ detail: TOKEN_REFUSED }) };
      return reply({ ...WORLDS, operating: world,
        history: [...WORLDS.history, { world, by: 'operator', at: '2026-10-03T00:00:00+00:00' }] });
    }
    if (path.endsWith('/worlds')) return reply(WORLDS);
    if (method === 'PUT') {
      puts.push(JSON.parse(init.body));
      if (refuseKeep) return { ok: false, status: 409, json: async () => ({ detail: { code: 'stale_revision',
        path: 'expected_revision', message: 'the draft moved on' } }) };
    }
    if (u.includes('/authoring')) return reply(AUTHORING);
    if (/\/drafts$/.test(path) && method === 'POST') return reply(DRAFT);
    if (path.endsWith('/bootstrap')) return reply({ created: 'ledger_config.json' });
    if (path.includes('/worlds/') && refuseDelete) return { ok: false, status: 409, json: async () => ({
      detail: { reason: 'world_not_deleted', world: 'w2', message: DELETE_REFUSED } }) };
    if (path.includes('/worlds/')) return reply(u.includes('confirm_atoms=') ? { deleted: 'w2' } : PREVIEW);
    return reply(asked ? { ...SELECTED, draft: { ...DRAFT, draft_id: asked, context_token: 'ctx:1' } } : SELECTED);
  };
  const confirms = [];
  const keepFetch = globalThis.fetch;
  const keepConfirm = globalThis.window.confirm;
  globalThis.fetch = async (url, init = {}) => {
    urls.push(`public ${init.method || 'GET'} ${String(url)}`);
    return reply({ ...DECLARATION, worlds: ['w1'] });
  };
  const asks = [];
  globalThis.window.confirm = (text) => {
    if (String(text).startsWith('Make ')) { asks.push(String(text)); return confirmOperate; }
    confirms.push(String(text));
    return confirmDelete;
  };
  const texts = (cls) => walkAll(mount).filter((n) => n._classes.includes(cls)).map((n) => n.textContent);
  try {
    const controller = create({ root, apiBase: '', adminFetch: adminOf, showToast: (t) => toasts.push(String(t)) });
    await controller.refresh();
    await settle();
    await click('create-draft');
    await settle();
    const out = { onDefault: urls.splice(0).sort() };
    const opened = controller.getState();
    out.open = `${Boolean(opened.selection)}|${Boolean(opened.draft)}`;
    out.listed = walkAll(mount).filter((n) => n.tagName === 'OPTION').map((n) => n.value || '(operating)');
    out.emptyText = (walkAll(mount).find((n) => n.tagName === 'OPTION' && n.value === '') || {}).textContent;
    const offNow = part('branch-picker__operate');
    out.operateOff = `${offNow && offNow.disabled}|${offNow && offNow.getAttribute('title')}`;
    if (typed) {
      // Unsaved typing, then a pick: the one dirty dialog, answered with `typed`.
      for (const fn of inputs) fn({ target: { dataset: { action: 'edit-raw' }, value: '{"class": 4}' } });
      const pick = part('branch-picker__select');
      if (pick) { pick.value = 'w1'; fire(pick, 'change'); }
      const backdrop = walkAll(root).find((n) => n._classes.includes('oe-dirty-dialog-backdrop')) || null;
      if (backdrop) backdrop.remove = () => {};
      const answer = backdrop && walkAll(backdrop).find((n) => n.dataset.dirtyChoice === typed);
      if (answer) fire(answer, 'click');
      await settle();
      const s = controller.getState();
      out.typed = { asked: Boolean(answer), world: s.world, draft: Boolean(s.draft), dirty: s.dirty, urls: urls.splice(0),
        puts: puts.splice(0) };
      return out;
    }
    const select = part('branch-picker__select');
    if (select) { select.value = pick; fire(select, 'change'); }
    // Read before the branch answers: what the pick itself left of the screen.
    const picked = controller.getState();
    out.picked = `${picked.world}|${Boolean(picked.selection)}|${Boolean(picked.draft)}`;
    await settle();
    await click('create-draft');
    await settle();
    out.onBranch = urls.splice(0);
    const name = part('branch-picker__name');
    if (name) { name.value = 'w2'; fire(name, 'input'); }
    // What the new branch stands on, pressed in order; each press redraws the part.
    for (const label of beneath || []) {
      const chip = walkAll(mount).find((n) => n._classes.includes('branch-picker__chip') && n.textContent === label);
      if (chip) fire(chip, 'click');
    }
    const make = part('branch-picker__create');
    if (make) fire(make, 'click');
    await settle();
    toasts.splice(0);
    out.made = { world: controller.getState().world, urls: urls.splice(0),
      operating: texts('branch-picker__operating').join('|'),
      history: walkAll(mount).filter((n) => n.tagName === 'LI').map((n) => n.textContent.split(' · ')[0]).join(',') };
    const go = part('branch-picker__operate');
    if (go) fire(go, 'click');
    await settle();
    out.operated = { asks: asks.splice(0), sent: operated.splice(0), urls: urls.splice(0), toasts: toasts.splice(0),
      operating: texts('branch-picker__operating').join('|'),
      history: walkAll(mount).filter((n) => n.tagName === 'LI').length };
    const drop = part('branch-picker__delete');
    if (drop) fire(drop, 'click');
    await settle();
    out.dropped = { world: controller.getState().world, urls: urls.splice(0), confirms, toasts: toasts.splice(0) };
    return out;
  } finally {
    globalThis.fetch = keepFetch;
    globalThis.window.confirm = keepConfirm;
  }
}
const branchSeen = async (create) => ({ yes: await branchWalk(create),
  no: await branchWalk(create, { confirmDelete: false }),
  byName: await branchWalk(create, { pick: 'default' }),
  under: await branchWalk(create, { beneath: ['w1', 'default'] }),
  nothing: await branchWalk(create, { beneath: ['Nothing'] }),
  declined: await branchWalk(create, { confirmOperate: false }),
  tokenless: await branchWalk(create, { refuseOperate: true }),
  undeleted: await branchWalk(create, { refuseDelete: true }),
  discard: (await branchWalk(create, { typed: 'discard' })).typed,
  stay: (await branchWalk(create, { typed: 'cancel' })).typed,
  keep: (await branchWalk(create, { typed: 'keep' })).typed,
  refused: (await branchWalk(create, { typed: 'keep', refuseKeep: true })).typed });
function branchSuite({ yes, no, byName, under, nothing, declined, tokenless, undeleted, discard, stay, keep, refused }) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  // One GET /worlds beside each census read (lead 120450931 ③) - the only request the round adds.
  const withWorlds = [...REQUESTS_BEFORE.urls, ...REQUESTS_BEFORE.urls
    .filter((u) => u === 'public GET /api/ledger/declaration').map(() => 'admin GET /admin/ontology-explorer/worlds')].sort();
  say('Z1 no world: the screen asks what it asked before the round, byte for byte, and reads the worlds beside each census',
    JSON.stringify(yes.onDefault) === JSON.stringify(withWorlds), yes.onDefault.join(' | '));
  say('Z2 the empty choice is named after the operating world; then the worlds as the server names them',
    yes.listed.join(',') === '(operating),default,w1' && yes.emptyText === 'Operating · w1',
    `${yes.listed.join(',')} :: ${yes.emptyText}`);
  say('Z3 a pick starts the screen over on the branch: nothing selected, no draft open',
    yes.open === 'true|true' && yes.picked === 'w1|false|false', `${yes.open} -> ${yes.picked}`);
  const lacking = yes.onBranch.filter((u) => !u.includes('world=w1'));
  const kinds = ['admin ', 'public '].every((k) => yes.onBranch.some((u) => u.startsWith(k)));
  say('Z4 on the branch every request carries it, admin and public alike',
    yes.onBranch.length > 0 && kinds && lacking.length === 0, lacking.join(' | ') || yes.onBranch.join(' | '));
  const view = yes.onBranch.find((u) => u.startsWith('admin GET /admin/ontology-explorer/view?')) || '';
  say('Z5 ...and the view the pick asks for names no selection and no draft',
    Boolean(view) && !view.includes('selection=') && !view.includes('draft_id='), view);
  say('Z6 a new branch is made by the bootstrap, sent on its name, and the screen reads it',
    yes.made.world === 'w2' && yes.made.urls[0] === 'admin POST /admin/ontology-explorer/bootstrap?world=w2'
      && yes.made.urls.length > 1 && yes.made.urls.every((u) => u.includes('world=w2')), yes.made.urls.join(' | '));
  const after = yes.dropped.urls.slice(2);
  say('Z7 delete: the preview, its count confirmed, the delete with that count; then no world (the operating one)',
    yes.dropped.urls[0] === 'admin DELETE /admin/ontology-explorer/worlds/w2?world=w2'
      && yes.dropped.urls[1] === 'admin DELETE /admin/ontology-explorer/worlds/w2?confirm_atoms=7&world=w2'
      && yes.dropped.confirms.length === 1 && yes.dropped.confirms[0].includes('7 atoms')
      && yes.dropped.confirms[0].includes('2 files') && yes.dropped.world === null
      && after.length > 0 && after.every((u) => !u.includes('world=')),
    `${yes.dropped.urls.join(' | ')} :: ${yes.dropped.confirms.join(' | ')}`);
  say('Z8 declined, nothing is deleted and the branch stays',
    no.dropped.urls.filter((u) => u.startsWith('admin DELETE')).length === 1 && no.dropped.world === 'w2',
    `${no.dropped.urls.join(' | ')} :: ${no.dropped.world}`);
  const opened = discard.urls.slice(1);
  say('Z9 unsaved typing asks first; Discard deletes the draft where it was typed, then the branch opens',
    discard.asked && discard.urls[0] === 'admin DELETE /admin/ontology-explorer/drafts/d1?expected_revision=1'
      && discard.world === 'w1' && !discard.draft && opened.length > 0 && opened.every((u) => u.includes('world=w1')),
    `${discard.asked} ${discard.world} ${discard.urls.join(' | ')}`);
  say('Z10 Stay sends nothing: the screen stays on its world with the typing',
    stay.asked && stay.urls.length === 0 && stay.world === null && stay.draft && stay.dirty,
    `${stay.asked} ${stay.world} ${stay.draft} ${stay.dirty} ${stay.urls.join(' | ')}`);
  // Keep is what it says (lead ccf374d48 answer 2): the typing goes into the draft store of the world it was
  // typed in - the default here, so no world on it - and only then does the screen leave.
  const kept = keep.urls.slice(1);
  say('Z14 Keep stores the typing in the world it was typed in, then the branch opens',
    keep.asked && keep.urls[0] === 'admin PUT /admin/ontology-explorer/drafts/d1' && keep.puts.length === 1
      && keep.puts[0].raw === '{"class": 4}' && keep.puts[0].expected_revision === 1
      && keep.world === 'w1' && !keep.draft && kept.length > 0 && kept.every((u) => u.includes('world=w1')),
    `${keep.asked} ${keep.world} ${JSON.stringify(keep.puts)} ${keep.urls.join(' | ')}`);
  say('Z15 a refused Keep stays, with the typing',
    refused.asked && refused.urls.length === 1 && refused.world === null && refused.draft && refused.dirty,
    `${refused.asked} ${refused.world} ${refused.draft} ${refused.dirty} ${refused.urls.join(' | ')}`);
  say('Z16 the default is picked by its name: every request then carries world=default',
    byName.picked === 'default|false|false' && byName.onBranch.length > 0
      && byName.onBranch.every((u) => u.includes('world=default')), `${byName.picked} ${byName.onBranch.join(' | ')}`);
  say('Z17 a new branch stands on what was pressed, in that order; Nothing sends it empty; untouched sends none',
    under.made.urls[0] === 'admin POST /admin/ontology-explorer/bootstrap?beneath=w1,default&world=w2'
      && nothing.made.urls[0] === 'admin POST /admin/ontology-explorer/bootstrap?beneath=&world=w2'
      && yes.made.urls[0] === 'admin POST /admin/ontology-explorer/bootstrap?world=w2',
    `${under.made.urls[0]} | ${nothing.made.urls[0]} | ${yes.made.urls[0]}`);
  say('Z18 Operate asks once and sends one PUT naming the world read; declined, it sends none',
    yes.operated.asks.length === 1 && JSON.stringify(yes.operated.sent) === '["w2"]'
      && yes.operated.urls.filter((u) => u.startsWith('admin PUT')).length === 1
      && declined.operated.asks.length === 1 && declined.operated.sent.length === 0
      && declined.operated.urls.length === 0,
    `${JSON.stringify(yes.operated)} :: ${JSON.stringify(declined.operated)}`);
  say('Z19 a refused Operate shows the server\'s sentence as it was sent',
    JSON.stringify(tokenless.operated.toasts) === JSON.stringify([TOKEN_REFUSED])
      && tokenless.operated.operating === 'Operating · w1', JSON.stringify(tokenless.operated));
  say('Z20 a refused delete shows the server\'s sentence and the branch stays',
    undeleted.dropped.toasts.join('|') === DELETE_REFUSED && undeleted.dropped.world === 'w2'
      && undeleted.dropped.confirms.length === 0, JSON.stringify(undeleted.dropped));
  say('Z21 on a branch the operating world is shown, its history newest first; Operate updates both',
    yes.made.operating === 'Operating · w1' && yes.made.history === 'w1,default'
      && yes.operated.operating === 'Operating · w2' && yes.operated.history === 3,
    `${yes.made.operating} ${yes.made.history} -> ${yes.operated.operating} ${yes.operated.history}`);
  say('Z22 on the empty choice Operate is off, with the reason', yes.operateOff === 'true|Already the operating world',
    yes.operateOff);
  return { ran: names.length, names, failures };
}
const branchBase = branchSuite(await branchSeen(createOntologyExplorerController));
ran += branchBase.ran;
failed += branchBase.failures.length;
{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const SUBJECT = join(HERE, '..', 'src', 'ontology_explorer.js');
  const WORLD = join(HERE, '..', 'src', 'world.js');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const MUTANTS = [
    { id: 'M14', what: 'the screen\'s requests go round the seat', catches: 'Z4',
      mutate: (text) => swap(text, "    const response = await ask(`${apiBase}/admin/ontology-explorer${path}`, init);",
        "    const response = await adminFetch(`${apiBase}/admin/ontology-explorer${path}`, init);") },
    { id: 'M15', what: 'the census goes round the seat', catches: 'Z4',
      mutate: (text) => swap(text, "      const res = await askPublic(`${apiBase}/api/ledger/declaration`);",
        "      const res = await fetch(`${apiBase}/api/ledger/declaration`);") },
    { id: 'M16', what: 'a new branch is bootstrapped with no world (the operating one)', catches: 'Z6',
      mutate: (text) => swap(text, "      const res = await ask(`${apiBase}/admin/ontology-explorer/bootstrap${under}`, {",
        "      const res = await adminFetch(`${apiBase}/admin/ontology-explorer/bootstrap${under}`, {") },
    { id: 'M17', what: 'a pick keeps the selection and the draft', catches: 'Z3',
      mutate: (text) => swap(text,
        '    state = { ...initialExplorerState, navigation: { back: [], forward: [] }, world: next, worlds: state.worlds,',
        '    state = { ...state, world: next, worlds: state.worlds,') },
    { id: 'M18', what: 'a branch is deleted without asking', catches: 'Z8',
      mutate: (text) => swap(text, 'if (!window.confirm(', 'if (void window.confirm(') },
    { id: 'M19', what: 'the seat sends a world when none is picked', catches: 'Z1 no world',
      load: async () => {
        const loud = (await loadWithProbe(WORLD, { mutate: (t) => swap(t, '    if (!world) return fetchImpl(url, init);\n', '') }))
          .module.withWorld;
        return (await loadWithProbe(SUBJECT, { stubs: { './world.js': { withWorld: loud } } })).module.createOntologyExplorerController;
      } },
    { id: 'M20', what: 'Stay does not stay', catches: 'Z10',
      mutate: (text) => swap(text, "    if (decision === 'cancel') { render(); return; }\n", '') },
    { id: 'M21', what: 'Discard leaves the draft in the world it was typed in', catches: 'Z9',
      mutate: (text) => swap(text,
        "    if (decision === 'discard' && state.draft && !(await discardDraft({ ask: false }))) return;\n    state = {",
        '    state = {') },
    { id: 'M29', what: 'Operate goes without asking', catches: 'Z18',
      mutate: (text) => swap(text, "    if (!window.confirm(`Make ${name} the operating world?`)) return;\n", '') },
    { id: 'M30', what: 'Operate is sent twice', catches: 'Z18',
      mutate: (text) => swap(text, "      const body = await jsonRequest('/worlds/operating', { method: 'PUT',",
        "      await jsonRequest('/worlds/operating', { method: 'PUT', body: JSON.stringify({ world: name }) });\n"
        + "      const body = await jsonRequest('/worlds/operating', { method: 'PUT',") },
    { id: 'M31', what: 'what a new branch stands on is dropped', catches: 'Z17',
      mutate: (text) => swap(text,
        "    const under = Array.isArray(beneath) ? `?beneath=${beneath.map(encodeURIComponent).join(',')}` : '';",
        "    const under = '';") },
    { id: 'M32', what: 'the token gate\'s sentence is folded into a status line', catches: 'Z19',
      mutate: (text) => swap(text, "(typeof detail === 'string' ? detail : detail.message)", 'detail.message') },
    { id: 'M33', what: 'the worlds are not read', catches: 'Z1 no world',
      mutate: (text) => swap(text, '      void loadWorlds();\n', '') },
    { id: 'M27', what: 'Keep leaves the typing behind', catches: 'Z14',
      mutate: (text) => swap(text, "    if (decision === 'keep' && state.dirty) {\n", "    if (false) {\n") },
    { id: 'M28', what: 'a refused Keep goes on anyway', catches: 'Z15',
      mutate: (text) => swap(text, "showToast(errorMessage(error), 'error'); render(); return; }\n    }\n",
        "showToast(errorMessage(error), 'error'); }\n    }\n") },
  ];
  const loadOf = async (m) => (m.load ? m.load()
    : (await loadWithProbe(SUBJECT, { mutate: m.mutate })).module.createOntologyExplorerController);
  const scored = await scoreMutants(MUTANTS, async (m) => branchSuite(await branchSeen(await loadOf(m))),
    { baselineRan: branchBase.ran, baselineNames: branchBase.names,
      title: '\n  [8] mutants — each must be caught by the check it names.' });
  ran += MUTANTS.length;
  failed += scored.wrong;
}

// The picker's own name field, the part alone: a blank name must make nothing - on the declaration
// screen it would bootstrap the OPERATING world - and the empty choice has nothing to delete.
async function pickerWalk(Picker) {
  const made = [];
  const dropped = [];
  const mount = element('div');
  const picker = new Picker(mount, { doc: document, onPick: () => {}, onCreate: (n) => made.push(n),
    onDelete: (n) => dropped.push(n) });
  picker.show({ worlds: ['w1'], current: null });
  const part = (cls) => walkAll(mount).find((n) => n._classes.includes(cls)) || null;
  const fire = (node, type) => { for (const fn of (node && node._on[type]) || []) fn({ target: node }); };
  const name = part('branch-picker__name');
  const make = part('branch-picker__create');
  const out = { fresh: `${make && make.disabled}|${make && make.getAttribute('title')}`, typed: [] };
  for (const typed of ['   ', '  w3 ']) {
    if (!name || !make) break;
    name.value = typed;
    fire(name, 'input');
    out.typed.push(String(make.disabled));
    fire(make, 'click');
  }
  out.made = made;
  out.deletable = Boolean(part('branch-picker__delete'));
  // The page redraws the part on its own renders: a made name is gone, a name being typed stays.
  picker.show({ worlds: ['w1'], current: null });
  out.afterMade = (part('branch-picker__name') || {}).value;
  const typing = part('branch-picker__name');
  if (typing) { typing.value = 'w4'; fire(typing, 'input'); }
  picker.show({ worlds: ['w1'], current: null });
  out.kept = `${(part('branch-picker__name') || {}).value}|${(part('branch-picker__create') || {}).disabled}`;
  // The empty choice's name (lead 120450931 ①), and what a new branch stands on, pressed in order (③).
  const words = new Picker(element('div'), { doc: document, onPick: () => {} });
  const emptyText = () => (walkAll(words.mount).find((n) => n.tagName === 'OPTION' && n.value === '') || {}).textContent;
  words.show({ worlds: ['default', 'w1'], current: null, operating: 'w1' });
  out.empty = emptyText();
  words.show({ worlds: ['default', 'w1'], current: null });
  out.bare = emptyText();
  const stood = [];
  const under = new Picker(element('div'), { doc: document, onPick: () => {}, onCreate: (n, b) => stood.push(b) });
  under.show({ worlds: ['default', 'w1'], current: null, operating: 'w1' });
  const press = (label) => {
    const chip = walkAll(under.mount).find((n) => n._classes.includes('branch-picker__chip') && n.textContent === label);
    if (chip) fire(chip, 'click');
  };
  const create = (presses) => {
    for (const label of presses) press(label);
    const field = walkAll(under.mount).find((n) => n._classes.includes('branch-picker__name'));
    if (field) { field.value = 'w3'; fire(field, 'input'); }
    const go = walkAll(under.mount).find((n) => n._classes.includes('branch-picker__create'));
    if (go) fire(go, 'click');
  };
  create(['w1', 'default']);
  create([]);
  create(['Nothing']);
  create(['w1', '1 · w1']);
  out.stood = JSON.stringify(stood);
  return out;
}
function pickerSuite(seen) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(detail ? `${name} — ${detail}` : name);
    console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`);
  };
  say('Z11 a blank name makes nothing: Create is off with the reason; a name goes trimmed',
    seen.fresh === 'true|Name the branch first' && seen.typed.join(',') === 'true,false'
      && JSON.stringify(seen.made) === '["w3"]', `${seen.fresh} ${seen.typed.join(',')} ${JSON.stringify(seen.made)}`);
  say('Z12 the empty choice offers nothing to delete', seen.deletable === false, String(seen.deletable));
  say('Z13 a redraw keeps a name being typed; a made branch clears it',
    seen.afterMade === '' && seen.kept === 'w4|false', `${JSON.stringify(seen.afterMade)} ${seen.kept}`);
  say('Z23 the empty choice is named after the operating world, or bare when the page does not know it',
    seen.empty === 'Operating · w1' && seen.bare === 'Operating', `${seen.empty} | ${seen.bare}`);
  say('Z24 beneath: pressed in order, Nothing is empty, a press taken back is none chosen, and each Create starts afresh',
    seen.stood === JSON.stringify([['w1', 'default'], null, [], null]), seen.stood);
  return { ran: names.length, names, failures };
}
const { BranchPicker } = await import('../src/branch_picker.js');
const pickerBase = pickerSuite(await pickerWalk(BranchPicker));
ran += pickerBase.ran;
failed += pickerBase.failures.length;
{
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const PICKER = join(HERE, '..', 'src', 'branch_picker.js');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const MUTANTS = [
    { id: 'M22', what: 'a blank name is sent (the screen would bootstrap the operating world)', catches: 'Z11',
      mutate: (text) => swap(text, '        if (isBlank(name.value)) return;\n', '') },
    { id: 'M23', what: 'Create is on with no name', catches: 'Z11',
      mutate: (text) => swap(text, "isBlank(name.value) ? NAME_FIRST : ''", "''") },
    { id: 'M24', what: 'the empty choice offers a delete', catches: 'Z12',
      mutate: (text) => swap(text, 'if (this.onDelete && this.current) {', 'if (this.onDelete) {') },
    { id: 'M25', what: 'a redraw drops the name being typed', catches: 'Z13',
      mutate: (text) => swap(text, '      name.value = this.typed;\n', '') },
    { id: 'M34', what: 'the empty choice is named Default again', catches: 'Z23',
      mutate: (text) => swap(text, "const empty = this.operating ? `Operating · ${this.operating}` : 'Operating';",
        "const empty = 'Default';") },
    { id: 'M35', what: 'a pressed world goes on top, not under the last', catches: 'Z24',
      mutate: (text) => swap(text, '[...list, world]', '[world, ...list]') },
    { id: 'M36', what: 'what was pressed outlives the Create', catches: 'Z24',
      mutate: (text) => swap(text, "        this.typed = '';\n        this.beneath = null;\n", "        this.typed = '';\n") },
    { id: 'M26', what: 'a made branch leaves its name in the field', catches: 'Z13',
      mutate: (text) => swap(text, "        this.typed = '';\n        this.beneath = null;\n", "        this.beneath = null;\n") },
  ];
  const scored = await scoreMutants(MUTANTS, async (m) => pickerSuite(await pickerWalk(
    (await loadWithProbe(PICKER, { mutate: m.mutate })).module.BranchPicker)),
    { baselineRan: pickerBase.ran, baselineNames: pickerBase.names,
      title: '\n  [8] picker mutants — each must be caught by the check it names.' });
  ran += MUTANTS.length;
  failed += scored.wrong;
}

// ═══════════════════════════════════════════════════════════════════════════════════════════
// [9] lead 04cecc30f — the slim source's form, through the controller's own clicks: opening the
//     folded read writes nothing, and a record chip writes only its own key and takes it back out.
// ═══════════════════════════════════════════════════════════════════════════════════════════
console.log('\n[9] the source form writes only what was picked');
{
  const on = { click: [] };
  const root = element('div');
  root.addEventListener = (type, fn) => { if (on[type]) on[type].push(fn); };
  const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r)); };
  const press = async (el) => { el.closest = () => el; el.disabled = false; for (const fn of on.click) await fn({ target: el }); await settle(); };
  const SKEY = 'source_plan|s';
  const leaf = { kind: 'leaf', hint: 'free' };
  const SOURCE_SCHEMA = {
    authorable_kinds: [{ id: 'source_plan', section: 'sources', versioned: false }],
    skeleton: { defs: {}, root: { kind: 'record', fields: [
      { key: 'sources', required: true, node: { kind: 'map', keyed_by: 'name', member: 'Source',
        of: { kind: 'record', fields: [
          { key: 'relation', required: true, node: leaf },
          { key: 'read', required: false, node: { kind: 'record', fields: [
            { key: 'unit', required: false, node: leaf },
            { key: 'exclude_when', required: false, node: { kind: 'map', keyed_by: 'index',
              member: 'Condition', of: { kind: 'record', fields: [
                { key: 'column', required: true, node: leaf },
                { key: 'blank', required: true, node: { kind: 'leaf', hint: 'flag' } }] } } }] } }] } } }] } },
  };
  const SLIM = { relation: 't' };
  const row = (over) => ({ step: 'sources', tier: 'constrained_input', declared: null, has_declared: false,
    conflicts: false, ground: null, candidates: null, universe: null, universe_note: '',
    comparison: 'equal', reshapes: false, disposition: '', forbidden: [], note: '', refusals: [], ...over });
  const planOf = (raw) => {
    const held = raw.read && raw.read.exclude_when;
    return { ...AUTHORING, fields: [
      row({ path: 'bundle.sources.s.read.unit', label: 'Unit', state: 'derived', tier: 'derivation',
        value: 'row', disposition: 'default_overridable',
        ground: { rule: 'read_default', text: 'Default: "row"', from_paths: ['bundle.sources.s.read'],
                  from_keys: [], from_value: 'row' } }),
      row({ path: 'bundle.sources.s.read.exclude_when', label: 'Exclude when blank',
        state: held ? 'answered' : 'unanswered', value: held || null, universe: 'RELATION',
        candidates: [{ column: 'a', blank: true }, { column: 'b', blank: true }] }),
    ] };
  };
  const SELECTION = { key: SKEY, canonical_id: 's', kind: 'source_plan', context_token: 'ctx:1', raw: SLIM };
  const VIEWED = { ...COMPILE, selection: SELECTION, items: [SELECTION] };
  const SDRAFT = { draft_id: 'd1', target_key: SKEY, target_kind: 'source_plan', target_id: 's',
    revision: 1, raw: SLIM, lifecycle_status: 'draft', validation_errors: [], context_token: 'ctx:1' };
  const fetchOf = async (url, init = {}) => {
    const u = String(url);
    const path = u.split('?')[0];
    const method = init.method || 'GET';
    let body = /draft_id=d1/.test(u) ? { ...VIEWED, draft: SDRAFT } : VIEWED;
    if (/\/drafts$/.test(path) && method === 'POST') body = SDRAFT;
    else if (path.endsWith('/authoring/schema')) body = SOURCE_SCHEMA;
    else if (path.endsWith('/authoring/plan') && method === 'POST') body = planOf(JSON.parse(JSON.parse(init.body).raw));
    else if (path.endsWith('/authoring/plan')) body = planOf(SLIM);
    return { ok: true, status: 200, json: async () => body };
  };
  const controller = createOntologyExplorerController({ root, apiBase: '', adminFetch: fetchOf, showToast: () => {} });
  await controller.refresh();
  await settle();
  const create = { dataset: { action: 'create-draft' } };
  await press(create);
  const text = () => controller.getState().editorText;
  const find = (test) => walkAll(root).find(test);
  const toggle = (value) => find((n) => n.dataset?.action === 'toggle-field' && n.dataset.value === value);
  const chip = (label) => find((n) => n._classes?.includes('oe-pick') && n.textContent === label);
  const before = text();
  ok('F0 the draft is open on the slim source', JSON.stringify(JSON.parse(before || 'null')) === JSON.stringify(SLIM), before);
  // The count is the panel harness's (K1): this stub has no childElementCount.
  ok('F1 read starts folded on its defaults', String(toggle('read')?.textContent).startsWith('Defaults · '),
    toggle('read')?.textContent);
  if (toggle('read')) await press(toggle('read'));
  ok('F2 opening it writes nothing - the draft is byte-identical', text() === before);
  const own = toggle('bundle.sources.s.read.exclude_when');
  if (own) await press(own);
  if (chip('column · a')) await press(chip('column · a'));
  const once = JSON.parse(text());
  ok('F3 a chip writes its clause and nothing else',
    JSON.stringify(once) === JSON.stringify({ relation: 't', read: { exclude_when: [{ column: 'a', blank: true }] } }),
    JSON.stringify(once));
  if (chip('column · a')) await press(chip('column · a'));
  const back = JSON.parse(text());
  ok('F4 its last chip takes the key out - no empty list is written',
    back.read && !('exclude_when' in back.read), JSON.stringify(back));
}

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
