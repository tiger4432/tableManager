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

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
