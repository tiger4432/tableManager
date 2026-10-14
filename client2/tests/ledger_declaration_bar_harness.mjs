// THE LEDGER DECLARATION WINDOW (owner 10-14, task/design/LEDGER_DECLARATION_BAR.dc.html) - the bar's edits on the
// short form (implementer B 10-14), its drawing, the test run's answer as its table, the explorer's editor that hands
// a short-form source / node type / predicate to it, the controller's chips through the one draft text, and the
// store's column-list refresh on a table save. Imports only; each layer has a defect that must go red at its line.
import { register } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
register(pathToFileURL(path.join(HERE, 'lib', 'css_loader.mjs')).href);
const SRC = path.join(HERE, '..', 'src');
const BAR = path.join(SRC, 'ledger_declaration_bar.js');
const SAMPLE = path.join(SRC, 'ledger_declaration_sample.js');
const STORE = path.join(SRC, 'ontology_explorer_store.js');
const VIEW = path.join(SRC, 'ontology_explorer_view.js');
const SCREEN = path.join(SRC, 'ontology_explorer.js');

function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null), _classes: [], dataset: Object.create(null),
    _on: Object.create(null), style: { setProperty() {} }, _text: '',
    get className() { return this._classes.join(' '); }, set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: { add(...n) { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); },
      remove(...n) { node._classes = node._classes.filter((c) => !n.includes(c)); }, contains(n) { return node._classes.includes(n); },
      toggle(n, on) { if (on) node.classList.add(n); else node.classList.remove(n); } },
    get childElementCount() { return this.children.length; },
    append(...items) { for (const i of items) if (i !== null && i !== undefined && i !== '') this.children.push(typeof i === 'string' ? text(i) : i); },
    appendChild(c) { this.children.push(c); return c; },
    replaceChildren(...items) { this.children = items.filter(Boolean); }, removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, removeAttribute(k) { delete this.attrs[k]; },
    hasAttribute(k) { return k in this.attrs; },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }, querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener(type, fn) { (this._on[type] ||= []).push(fn); }, removeEventListener() {}, focus() {}, scrollIntoView() {},
    closest() { return null; }, contains() { return false; },
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
function text(t) { const n = element('#text'); n.textContent = t; return n; }
globalThis.document = { createElement: element, createDocumentFragment: () => element('#fragment'), createTextNode: text,
  addEventListener() {}, removeEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; } };
globalThis.requestAnimationFrame = (fn) => fn();
globalThis.window = { addEventListener() {}, removeEventListener() {}, location: { hash: '' }, confirm: () => true };

const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (root, name) => walk(root).filter((n) => n._classes?.includes(name));
const byAction = (root, action) => walk(root).filter((n) => n.dataset?.action === action);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail === undefined ? '' : ` -- ${detail}`}`);
};

const RAW0 = {
  table: 'wafer_process_recipe', attributes: { wafer: { lot: 'lot_id' } },
  sentences: [
    { sentence: 's1', subject: { node: 'wafer', keys: { wafer: 'wafer_id' } }, predicate: 'processed_with',
      target: { node: 'recipe', keys: { recipe: 'recipe_id' } }, step: 'step', when: { mat_type: '' }, occurred_at: { column: 'eventtime', timezone: 'Asia/Seoul' } },
    { sentence: 's2', subject: { node: 'dt_wafer', keys: { dt_wafer: 'wafer_id' } }, predicate: 'processed_with',
      target: { node: 'recipe', keys: { recipe: { const: 'R' } } }, when: { mat_type: { not: 'DT' } }, occurred_at: { column: 'eventtime', timezone: 'Asia/Seoul' } },
  ],
};
const CTX = { entities: [{ type: 'wafer', keys: ['wafer'], attributes: ['lot', 'step'] }, { type: 'die', keys: ['mat_id', 'x', 'y'] }],
  predicates: [{ name: 'processed_with', qualifiers: ['step', 'chamber'] }] };
const CATALOG = { tables: { wafer_process_recipe: [{ name: 'wafer_id', type: 'text' }, { name: 'eventtime', type: 'datetime' }, { name: 'slot', type: 'number' }] } };
const SERVER_RUN = { source_id: 'wafer_process_recipe', status: 'refused', rows_read: 3, atoms: 2,
  refused: { count: 1, reasons: { target_missing: 1 }, samples: [{ reason: 'target_missing', detail: 'recipe_id is blank — no target', row_key: { frame: 'p', position: 1204 } }] },
  atoms_sample: [{ sentence: 's1', row_ids: ['1201'], subject_type: 'wafer', subject_keys: { wafer: 'W-1' }, predicate: 'processed_with',
    object_kind: 'entity_ref', object_payload: { type: 'recipe', keys: { recipe: 'R-7' }, qualifiers: { step: 'BOND' } }, occurred_at: '2026-10-14 09:12:00' }] };
const DRAFT0 = { draft_id: 'd-1', target_key: 'source_plan|wafer_process_recipe', target_id: 'wafer_process_recipe', target_kind: 'source_plan',
  lifecycle_status: 'draft', revision: 3, base_snapshot_hash: 'h', preview_valid: true, validation_errors: [], updated_at: new Date(Date.now() - 5 * 60000).toISOString() };

async function suite(d) {
  const { bar, sample, store, view, makeController } = d;
  // fresh per run: a mutant that writes into what it was handed must not reach the next run
  const RAW = structuredClone(RAW0);
  const DRAFT = { ...DRAFT0, raw: structuredClone(RAW0) };
  console.log('\n── A. one edit, a path and a value ──');
  const keyed = bar.editDeclaration(RAW, { op: 'set', path: 'sentences.0.subject.keys.wafer', value: 'slot' }, CTX);
  ok('A1 a key chip sets its column', keyed.sentences[0].subject.keys.wafer === 'slot', JSON.stringify(keyed.sentences[0].subject));
  ok('A2 the declaration handed in is untouched', RAW.sentences[0].subject.keys.wafer === 'wafer_id');
  const renamed = bar.editDeclaration({ ...RAW, attributes: { wafer: { lot: 'lot_id' }, die: {} } }, { op: 'set', path: 'attributes.@wafer', value: 'lot' }, CTX);
  ok('A3 a node type renamed keeps its place and its attributes', same(Object.entries(renamed.attributes), [['lot', { lot: 'lot_id' }], ['die', {}]]), JSON.stringify(renamed.attributes));
  const node = bar.editDeclaration(RAW, { op: 'set', path: 'sentences.0.subject.node', value: 'die' }, CTX);
  ok('A4 a node picked takes that type\'s keys', same(node.sentences[0].subject, { node: 'die', keys: { mat_id: '', x: '', y: '' } }), JSON.stringify(node.sentences[0].subject));
  const time = bar.editDeclaration(RAW, { op: 'set', path: 'sentences.*.occurred_at.column', value: 'slot' }, CTX);
  ok('A5 the Read line\'s atom time is every sentence\'s', time.sentences.every((s) => s.occurred_at.column === 'slot' && s.occurred_at.timezone === 'Asia/Seoul'),
    JSON.stringify(time.sentences.map((s) => s.occurred_at)));
  const added = bar.editDeclaration(RAW, { op: 'add', path: 'sentences' }, CTX);
  ok('A6 a new sentence has both ends and the others\' atom time', added.sentences.length === 3
    && same(added.sentences[2].occurred_at, RAW.sentences[1].occurred_at) && added.sentences[2].subject && added.sentences[2].target, JSON.stringify(added.sentences[2]));
  const qual = bar.editDeclaration(RAW, { op: 'add', path: 'sentences.0' }, CTX);
  ok('A7 + Qualifier names the predicate\'s next free qualifier', qual.sentences[0].chamber === '', JSON.stringify(qual.sentences[0]));
  const removed = bar.editDeclaration(RAW, { op: 'remove', path: 'sentences.0' }, CTX);
  ok('A8 × takes that sentence out', removed.sentences.length === 1 && removed.sentences[0].sentence === 's2');

  console.log('\n── B. the drawing ──');
  const root = bar.renderDeclarationBar(document, RAW, { kind: 'source', name: 'wafer_process_recipe', sourceId: 'wafer_process_recipe', draftId: 'd-1',
    open: 'sentences.0.subject.keys.wafer', catalog: CATALOG, entities: CTX.entities, predicates: CTX.predicates,
    others: [{ source: 'transfer_event', sentence: { sentence: 'o1', subject: { node: 'die', keys: {} }, predicate: 'p', target: { node: 'die', keys: {} } } }] });
  const bars = byClass(byClass(root, 'ldb-sentences')[0], 'ldb-bar');
  ok('B1 a bar per sentence, another source\'s drawn inert', bars.length === 3 && bars[2].hasAttribute('inert') && !bars[0].hasAttribute('inert'),
    bars.map((b) => b.attrs.inert).join('|'));
  const pops = byClass(root, 'ldb-pop');
  const opts = pops.length ? byClass(pops[0], 'ldb-opt').filter((o) => o.dataset.action === 'decl-pick') : [];
  ok('B2 the open chip lists the table\'s columns with their types', pops.length === 1
    && same(opts.map((o) => [JSON.parse(o.dataset.value), byClass(o, 'ldb-type')[0]?.textContent]), [['wafer_id', 'text'], ['eventtime', 'datetime'], ['slot', 'number']]),
    JSON.stringify(opts.map((o) => o.dataset.value)));
  ok('B3 the list ends in «Constant…», which opens its box', byAction(pops[0] || element('i'), 'decl-type').length === 1);
  const typing = bar.renderDeclarationBar(document, RAW, { kind: 'source', open: 'sentences.0.subject.keys.wafer', typing: 'sentences.0.subject.keys.wafer', catalog: CATALOG });
  const box = byAction(typing, 'decl-const')[0];
  ok('B4 typing: the box carries its path and chip', Boolean(box) && box.dataset.path === 'sentences.0.subject.keys.wafer' && box.dataset.chip === 'col');
  const read = byClass(root, 'ldb-bar')[0].textContent;
  ok('B5 the Read line shows the sentences\' one atom time', read.includes('eventtime') && read.includes('Asia/Seoul'), read);
  const mixed = bar.editDeclaration(RAW, { op: 'set', path: 'sentences.1.occurred_at.column', value: 'slot' }, CTX);
  const mixedRead = byClass(bar.renderDeclarationBar(document, mixed, { kind: 'source', catalog: CATALOG }), 'ldb-bar')[0].textContent;
  ok('B6 sentences timed by different columns say «mixed», the server\'s refusal beside it', mixedRead.includes('mixed') && mixedRead.includes('one row, one time'), mixedRead);
  const untimed = bar.editDeclaration(RAW, { op: 'remove', path: 'sentences.1.occurred_at' }, CTX);
  const untimedRead = byClass(bar.renderDeclarationBar(document, untimed, { kind: 'source', catalog: CATALOG }), 'ldb-bar')[0].textContent;
  ok('B10 a sentence with no atom time does not make the time mixed', untimedRead.includes('eventtime') && !untimedRead.includes('mixed'), untimedRead);
  const all = root.textContent;
  ok('B7 a when reads its condition', all.includes('mat_type is blank') && all.includes('mat_type ≠ "DT"'), all.slice(0, 400));
  const run = byAction(root, 'test-run')[0];
  ok('B8 Test run names the source and the draft; Save draft and Activate are there', run?.dataset.value === 'wafer_process_recipe' && run?.dataset.draft === 'd-1'
    && byAction(root, 'save-draft-only').length === 1 && byAction(root, 'save-draft')[0]?.textContent === 'Activate');
  const s2 = bars[1];
  ok('B11 a sentence with no qualifier yet opens its with group on + Qualifier (its predicate takes one)',
    byAction(s2, 'decl-add').some((n) => n.dataset.path === 'sentences.1') && s2.textContent.includes('· with'), s2.textContent);
  const none = bar.renderDeclarationBar(document, RAW, { kind: 'source', catalog: CATALOG, predicates: [{ name: 'processed_with', qualifiers: [] }] });
  const s2none = byClass(byClass(none, 'ldb-sentences')[0], 'ldb-bar')[1];
  ok('B12 ...and none when its predicate takes none', !byAction(s2none, 'decl-add').some((n) => n.dataset.path === 'sentences.1'), s2none.textContent);
  const ENDS = { table: 't', sentences: [
    { sentence: 'counted', predicate: 'has_netdie', subject: { node: 'job', keys: { job: 'job' } }, value: 'netdie_count' },
    { sentence: 'register', predicate: 'register', subject: { node: 'job', keys: { job: 'job' } } }] };
  const endBars = byClass(byClass(bar.renderDeclarationBar(document, ENDS, { kind: 'source', catalog: CATALOG }), 'ldb-sentences')[0], 'ldb-bar');
  ok('B13 a sentence ending in a value draws «value ← column», not a node', endBars[0].textContent.includes('value ← netdie_count')
    && !byClass(endBars[0], 'is-node').some((n) => n.dataset.path === 'sentences.0.target.node'), endBars[0].textContent);
  ok('B14 a sentence with no object draws nothing past its predicate', !endBars[1].textContent.includes('→') && !endBars[1].textContent.includes('?'), endBars[1].textContent);
  const full = bar.renderDeclarationBar(document, sample.SAMPLE_RAW, sample.SAMPLE_VIEW);
  const hangul = walk(full).map((n) => n._text || '').concat(walk(full).map((n) => n.attrs?.['aria-label'] || '')).filter((s) => /[가-힣]/.test(s));
  ok('B9 every word drawn is English', hangul.length === 0, hangul.join(' | '));

  console.log('\n── C. the test run\'s answer as the bar\'s table ──');
  const mapped = bar.barRun(SERVER_RUN);
  ok('C1 rows read, edges, refused and the refusal\'s row', mapped && mapped.rows === 3 && mapped.edges === 2 && mapped.refused === 1
    && same(mapped.refusals, ['row 1204: recipe_id is blank — no target']), JSON.stringify(mapped));
  ok('C2 an atom: its row, its ends by type and key, its qualifier', same(mapped.lines[0], { row: '1201', sentence: 's1', subject: { node: 'wafer', key: 'W-1' },
    predicate: 'processed_with', target: { node: 'recipe', key: 'R-7' }, with: { name: 'step', value: 'BOND' }, at: '2026-10-14 09:12:00' }), JSON.stringify(mapped.lines[0]));
  ok('C3 no run, no table', bar.barRun(null) === null);
  ok('C4 the run is the draft\'s only when the answer names the draft', mapped.draft === false && bar.barRun({ ...SERVER_RUN, draft_id: 'd-1' }).draft === true);
  const titled = (r) => byClass(bar.renderDeclarationBar(document, RAW, { kind: 'source', catalog: CATALOG, run: r }), 'ldb-preview-head')[0].textContent;
  ok('C5 the table\'s title says what ran', titled(mapped).includes('Test run · active declaration') && titled({ ...mapped, draft: true }).includes('Test run · draft'),
    titled(mapped));

  console.log('\n── D. the explorer\'s editor hands the draft to the bar ──');
  const base = { ...store.initialExplorerState, draft: DRAFT, editorText: JSON.stringify(RAW), items: [{ key: 'source_plan|wafer_process_recipe', kind: 'source_plan', canonical_id: 'wafer_process_recipe' }],
    authoringSchema: { tables: { wafer_process_recipe: { columns: { wafer_id: 'string', eventtime: 'datetime' }, key: ['proc_id'] } } } };
  const editor = view.renderRaw(base);
  const ldb = byClass(editor, 'ldb');
  ok('D1 a short-form source is the bar, its JSON hidden, no second Save', ldb.length === 1 && byAction(editor, 'edit-raw').length === 0
    && !walk(editor).some((n) => n.dataset?.action === 'save-draft' && n.textContent === 'Save'));
  const shown = view.renderRaw({ ...base, decl: { ...base.decl, json: true } });
  ok('D2 JSON pressed: the draft\'s text is there to edit', byAction(shown, 'edit-raw').length === 1);
  const long = view.renderRaw({ ...base, editorText: JSON.stringify({ relation: 't', bind: {} }) });
  ok('D3 a source not in the short form keeps today\'s editor', byClass(long, 'ldb').length === 0 && byAction(long, 'edit-raw').length === 1);
  const dv = view.declarationView(base, 'source');
  ok('D4 the column list is built from the schema the screen holds', same(dv.catalog.tables.wafer_process_recipe, [{ name: 'wafer_id', type: 'string' }, { name: 'eventtime', type: 'datetime' }])
    && same(dv.catalog.keys, { wafer_process_recipe: ['proc_id'] }) && dv.draftAge === 'edited 5 min ago' && dv.sources[0].id === 'wafer_process_recipe', JSON.stringify(dv.catalog));

  console.log('\n── E. the chips go through the one draft text ──');
  const posted = [];
  const answer = (url, init) => {
    if (url.includes('/view')) return { active_snapshot: { snapshot_hash: 'h' }, selection: null, items: base.items.map((i) => ({ ...i, context_token: 't' })),
      draft: { ...DRAFT, context_token: 't' }, view_context: { context_token: 't' }, context_token: 't' };
    if (url.includes('/authoring/plan')) return { fields: [], sections: {}, steps: [] };
    if (url.includes('/test-run')) { posted.push(JSON.parse(init.body)); return SERVER_RUN; }
    if (url.includes('/drafts/')) return { ...DRAFT, revision: 4, raw: JSON.parse(JSON.parse(init.body).raw) };
    return {};
  };
  const host = element('div');
  const screen = makeController({ root: host, apiBase: '', showToast: () => {},
    adminFetch: async (url, init) => ({ ok: true, status: 200, json: async () => answer(url, init) }) });
  await screen.refresh();
  const fire = async (type, dataset, extra = {}) => { for (const fn of host._on[type] || []) await fn({ target: { closest: () => ({ dataset }), dataset, ...extra }, key: extra.key }); };
  await fire('click', { action: 'decl-open', path: 'sentences.0.subject.keys.wafer' });
  ok('E1 a chip pressed opens its list', screen.getState().decl.open === 'sentences.0.subject.keys.wafer', JSON.stringify(screen.getState().decl));
  await fire('click', { action: 'decl-pick', path: 'sentences.0.subject.keys.wafer', value: '"slot"' });
  const picked = (() => { try { return JSON.parse(screen.getState().editorText); } catch { return null; } })();
  ok('E2 an option picked is the draft\'s text, the list shut', picked?.sentences?.[0]?.subject?.keys?.wafer === 'slot' && screen.getState().decl.open === null && screen.getState().dirty === true,
    JSON.stringify(picked?.sentences?.[0]?.subject));
  await fire('change', { action: 'decl-const', path: 'sentences.0.step', chip: 'col' }, { value: 'BOND' });
  ok('E3 a typed constant lands as {const}', same(JSON.parse(screen.getState().editorText).sentences[0].step, { const: 'BOND' }), screen.getState().editorText.slice(0, 200));
  await fire('change', { action: 'decl-const', path: 'sentences.1.when', chip: 'when' }, { value: 'X' });
  ok('E4 a when\'s «= …» keeps its column', same(JSON.parse(screen.getState().editorText).sentences[1].when, { mat_type: 'X' }));
  await fire('click', { action: 'test-run', value: 'wafer_process_recipe', draft: 'd-1' });
  ok('E5 the bar\'s Test run asks for its draft', posted.length === 1 && posted[0].draft_id === 'd-1' && posted[0].source_id === 'wafer_process_recipe', JSON.stringify(posted));
  await fire('click', { action: 'decl-json' });
  ok('E6 JSON toggles', screen.getState().decl.json === true);

  console.log('\n── G. a node type: its bar, and its other fields on the More line ──');
  const SKELETON = { root: { kind: 'record', fields: [{ key: 'entities', node: { kind: 'map', keyed_by: 'name', of: { kind: 'record', fields: [
    { key: 'keys', node: { kind: 'map', keyed_by: 'index', of: { kind: 'leaf', hint: 'free' } } },
    { key: 'attributes', node: { kind: 'map', keyed_by: 'index', of: { kind: 'leaf', hint: 'free' } } },
    { key: 'label', node: { kind: 'map', keyed_by: 'name', of: { kind: 'leaf', hint: 'free' } } },
    { key: 'allow_null', node: { kind: 'leaf', hint: 'flag' } },
    { key: 'status', node: { kind: 'leaf', hint: 'choice', list: 'lifecycle_status' } }] } } }] }, defs: {} };
  const ENTITY_DRAFT = { ...DRAFT, target_kind: 'entity', target_key: 'entity|wafer', target_id: 'wafer' };
  const eState = { ...base, draft: ENTITY_DRAFT, editorText: JSON.stringify({ keys: ['wafer'], status: 'active' }),
    authoringSchema: { authorable_kinds: [{ id: 'entity', section: 'entities' }], lifecycle_status: ['active', 'retired'], skeleton: SKELETON } };
  const ev = view.declarationView(eState, 'entity');
  ok('G1 the More line is the skeleton\'s fields the bar does not draw', same(ev.more.map((f) => [f.name, f.kind, (f.options || []).map((o) => o.value)]),
    [['label', 'json', []], ['allow_null', 'options', [true, false]], ['status', 'options', ['active', 'retired']]]), JSON.stringify(ev.more));
  const eEditor = view.renderRaw(eState);
  const moreLine = byClass(bar.renderDeclarationBar(document, { keys: ['wafer'], status: 'active' }, ev), 'ldb-bar').find((b) => b.attrs['aria-label'] === 'More');
  ok('G2 a node type is its bar, its other fields on the More line', byClass(eEditor, 'ldb').length === 1 && Boolean(moreLine)
    && moreLine.textContent.includes('status = active') && moreLine.textContent.includes('label · JSON'), moreLine && moreLine.textContent);
  const eHost = element('div');
  const eScreen = makeController({ root: eHost, apiBase: '', showToast: () => {},
    adminFetch: async (url) => ({ ok: true, status: 200, json: async () => (url.includes('/view')
      ? { active_snapshot: { snapshot_hash: 'h' }, selection: null, items: [], draft: { ...ENTITY_DRAFT, raw: { keys: ['wafer'] }, context_token: 't' },
        view_context: { context_token: 't' }, context_token: 't' }
      : url.includes('/authoring/plan') ? { fields: [], sections: {}, steps: [] } : {}) }) });
  await eScreen.refresh();
  const eFire = async (dataset, value) => { for (const fn of eHost._on.change || []) await fn({ target: { dataset, value } }); };
  await eFire({ action: 'decl-const', path: 'label', chip: 'json' }, '{"en": "Wafer"}');
  ok('G3 a field\'s JSON typed is that field\'s value', same(JSON.parse(eScreen.getState().editorText).label, { en: 'Wafer' }), eScreen.getState().editorText);
  await eFire({ action: 'decl-const', path: 'label', chip: 'json' }, '{"en": ');
  ok('G4 a JSON that does not parse writes nothing', same(JSON.parse(eScreen.getState().editorText).label, { en: 'Wafer' }));

  console.log('\n── F. a table save reads the column lists again ──');
  const held = { ...store.initialExplorerState, authoringSchema: { tables: {} } };
  ok('F1 a table save clears the schema', store.reduceExplorerState(held, { type: 'AUTHORING_INVALIDATED', tables: true }).authoringSchema === null);
  ok('F2 any other invalidation keeps it', store.reduceExplorerState(held, { type: 'AUTHORING_INVALIDATED' }).authoringSchema !== null);
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const load = async (file, mutate, expose) => (await loadWithProbe(file, { ...(mutate ? { mutate } : {}), ...(expose ? { expose } : {}) }));
const deps = async (m = {}) => {
  const v = await load(VIEW, m.file === 'view' && m.mutate, ['renderRaw']);
  return {
    bar: (await load(BAR, m.file === 'bar' && m.mutate)).module, sample: (await load(SAMPLE)).module,
    store: (await load(STORE, m.file === 'store' && m.mutate)).module,
    view: { renderRaw: v.probe.renderRaw, declarationView: v.module.declarationView },
    makeController: (await load(SCREEN, m.file === 'screen' && m.mutate)).module.createOntologyExplorerController,
  };
};

const MUTANTS = [
  { name: 'a set writes into the declaration handed in', catches: ['A2'], file: 'bar', mutate: swap('  const out = clone(raw) || {};\n', '  const out = raw || {};\n') },
  { name: 'a rename appends instead of keeping the place', catches: ['A3'], file: 'bar',
    mutate: swap('(k === old ? [op.value, v] : [k, v])', '(k === old ? null : [k, v])).filter(Boolean).concat([[op.value, box[old]]]') },
  { name: 'a picked node keeps the old keys', catches: ['A4'], file: 'bar', mutate: swap('      if (e) box.keys = ', '      if (false) box.keys = ') },
  { name: 'the Read line\'s time writes one sentence', catches: ['A5'], file: 'bar', mutate: swap("  const star = String(op.path).split('.').indexOf('*');", "  const star = -1;") },
  { name: 'a new sentence has no atom time', catches: ['A6'], file: 'bar', mutate: swap('...(time ? { occurred_at: time } : {})', '') },
  { name: '+ Qualifier ignores the predicate', catches: ['A7'], file: 'bar', mutate: swap('      const free = ((pred && pred.qualifiers) || []).find((q) => !(q in holder));', '      const free = null;') },
  { name: 'another source\'s sentence is editable', catches: ['B1'], file: 'bar', mutate: swap("  if (from) bar.setAttribute('inert', '');\n", '') },
  { name: 'the list drops the column types', catches: ['B2'], file: 'bar', mutate: swap("    if (o.type) opt.append(el('span', 'ldb-type', o.type));\n", '') },
  { name: 'the «Constant…» line is gone', catches: ['B3'], file: 'bar', mutate: swap('    if (view.typing !== c.path) {', '    if (false) {') },
  { name: 'an untimed sentence counts as a time', catches: ['B10'], file: 'bar', mutate: swap('.filter((s) => s.occurred_at !== undefined && s.occurred_at !== null)', '') },
  { name: 'mixed times drawn without the refusal', catches: ['B6'], file: 'bar', mutate: swap("bar.append(el('span', 'ldb-pill is-bad', BAR_WORDS.timesDiffer));", '') },
  { name: 'the Read line reads one sentence\'s time', catches: ['B6'], file: 'bar', mutate: swap('  return seen.length > 1 ? BAR_WORDS.mixed : seen[0] || \'\';', '  return seen[0] || \'\';') },
  { name: 'a differs-when reads as equals', catches: ['B7'], file: 'bar', mutate: swap('`${c} ≠ ${JSON.stringify(v.not)}`', '`${c} = ${JSON.stringify(v.not)}`') },
  { name: 'Test run forgets its draft', catches: ['B8', 'E5'], file: 'bar', mutate: swap(' if (view.draftId) run.dataset.draft = view.draftId;', '') },
  { name: 'a word drawn in Korean', catches: ['B9'], file: 'bar', mutate: swap("  addSentence: '+ Sentence',", "  addSentence: '+ 문장',") },
  { name: 'a refusal without its row', catches: ['C1'], file: 'bar', mutate: swap('? `row ${s.row_key.position}: ` :', "? '' :") },
  { name: 'an entity end drawn as its kind', catches: ['C2'], file: 'bar', mutate: swap("a.object_kind === 'entity_ref' ?", 'false ?') },
  { name: 'the editor never hands over to the bar', catches: ['D1', 'D2'], file: 'view', mutate: swap('  if (!kind) return null;\n  let raw;', '  return null;\n  let raw;') },
  { name: 'JSON pressed shows nothing', catches: ['D2'], file: 'view', mutate: swap('state.decl && state.decl.json ? json : null', 'null') },
  { name: 'a long-form source goes to the bar too', catches: ['D3'], file: 'view', mutate: swap("kind === 'source' && !isShortForm(raw) ? null : ", '') },
  { name: 'the column list ignores the schema', catches: ['D4'], file: 'view', mutate: swap('  const tables = schema.tables && typeof schema.tables === \'object\' ? schema.tables : {};', '  const tables = {};') },
  { name: 'a chip press does not open its list', catches: ['E1'], file: 'screen', mutate: swap("decl: { open: state.decl.open === path ? null : path, typing: null }", 'decl: { typing: null }') },
  { name: 'a pick leaves the list open', catches: ['E2'], file: 'screen', mutate: swap("    state = reduceExplorerState(state, { type: 'DECL_UI', decl: { open: null, typing: null } });\n", '') },
  { name: 'a typed constant lands bare', catches: ['E3'], file: 'screen', mutate: swap("value = { const: typed };", 'value = typed;') },
  { name: 'the test run drops the draft', catches: ['E5'], file: 'screen', mutate: swap('...(target.dataset.draft ? { draft_id: target.dataset.draft } : {})', '') },
  { name: 'the More line repeats a field the bar draws', catches: ['G1'], file: 'view', mutate: swap('.filter((f) => !(BAR_FIELDS[kind] || []).includes(f.key))', '') },
  { name: 'a choice offers nothing', catches: ['G1'], file: 'view', mutate: swap('(Array.isArray(schema[n.list]) ? schema[n.list] : [])', '[]') },
  { name: 'a node type has no More line', catches: ['G2'], file: 'bar', mutate: swap('root.append(entityBar(el, view, raw || {}), moreBar(el, view, raw || {}));', 'root.append(entityBar(el, view, raw || {}));') },
  { name: 'a field\'s JSON lands as text', catches: ['G3'], file: 'screen', mutate: swap('try { value = JSON.parse(typed); } catch (error)', 'try { value = typed; } catch (error)') },
  { name: 'a broken JSON writes anyway', catches: ['G4'], file: 'screen', mutate: swap("showToast(`Not JSON: ${error.message}`, 'error'); return; }", "value = typed; }") },
  { name: 'a sentence with no qualifier has no door', catches: ['B11'], file: 'bar', mutate: swap('  if (!quals.length && free) {', '  if (false) {') },
  { name: 'the door drawn though the predicate takes none', catches: ['B12'], file: 'bar', mutate: swap('  if (!quals.length && free) {', '  if (!quals.length) {') },
  { name: 'every run called the draft\'s', catches: ['C4', 'C5'], file: 'bar', mutate: swap('draft: Boolean(run.draft_id) };', 'draft: true };') },
  { name: 'the title ignores what ran', catches: ['C5'], file: 'bar', mutate: swap("top.append(el('span', 'ldb-label', BAR_WORDS.run(Boolean(run && run.draft))),", "top.append(el('span', 'ldb-label', BAR_WORDS.run(true)),") },
  { name: 'a value end drawn as a node end', catches: ['B13', 'B14'], file: 'bar', mutate: swap('  if (s.target !== undefined) bar.append(', '  if (true) bar.append(') },
  { name: 'a value end not drawn', catches: ['B13'], file: 'bar', mutate: swap('  else if (s.value !== undefined) {', '  else if (false) {') },
  { name: 'a table save keeps the old column lists', catches: ['F1'], file: 'store', mutate: swap('...(action.tables ? { authoringSchema: null } : {})', '') },
  { name: 'every invalidation drops the schema', catches: ['F2'], file: 'store', mutate: swap('...(action.tables ? { authoringSchema: null } : {})', 'authoringSchema: null') },
];

console.log('== baseline ==');
const base = await suite(await deps());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const d = await deps(m);
  const real = console.log;
  console.log = () => {};
  ran = 0; failed = [];
  try { await suite(d); } finally { console.log = real; }
  return { failures: failed, ran };
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
