// LEDGER SETUP — the admin screens that wire a source table into the ledger and register a
// predicate, with no code and no restart.
//
// THE JOURNEY THIS SCREEN EXISTS FOR
//   pick a table → declare it → dry run → read the atoms → save → the 「먹었는가」 sentence.
//
// THREE RULES THIS FILE IS BUILT AROUND, and each of them is a shape, not a comment:
//
//   1. NO CLIENT COPY OF THE VOCABULARY. The kinds, the columns a kind requires, the entity
//      types, the object kinds, the walk directions, the traversable states, the signature a
//      new predicate must fill — every one of them arrives in a payload and the form is
//      GENERATED from it. Search this file for a predicate name or a column name and you will
//      not find one. A second copy of the gate's vocabulary drifts from the gate.
//
//   2. THE SAVE CONTROL DOES NOT EXIST UNTIL A DRY RUN OF THE CURRENT FORM STATE HAS RETURNED.
//      The server makes this structural with a token (`dry_run_stale`), and the screen agrees
//      with that rather than working around it: the button is APPENDED when a dry run returns
//      and REMOVED the moment any input changes. Not disabled — removed. A greyed button is
//      still a button someone waits for.
//
//   3. THE CLIENT NEVER COMPOSES A REASON. A refusal renders the server's `detail_ko` verbatim;
//      `code` is shown as the server's own word and `field` is used only to decide which input
//      the message hangs off. There is no code→wording table here, and there must never be one.
//
// The view model lives in `ledger_setup_view.js` (DOM-free) for the same reason the config
// report's does — the provenance of every string is visible in one file.

import './ledger_setup.css';
import { showToast } from './utils.js';
import { buildConfigResolveView, CHROME, fetchFailureLine } from './config_resolve_view.js';
import {
  LEDGER_CHROME as LC, buildRelationsView, buildSourcesView, buildVocabularyView,
  buildDryRunView, buildSaveView, buildViolationsView, buildRawView, hasViolations,
  declarationKey, nameText,
} from './ledger_setup_view.js';

// The raw read. Read out of `main.py` rather than guessed a second time: the route addresses
// the FILE and takes the source as a query parameter, which is why it is `config/raw?source=`
// and not `sources/{name}/raw`. The unit of writing is still one source — the path names where
// the declaration lives, not what gets rewritten.
const RAW_READ_PATH = (name) => `/admin/ledger/config/raw?source=${encodeURIComponent(name)}`;

// ── tiny DOM helpers (the cfg-* vocabulary is shared with the config report) ──

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function chip(text, tone) {
  const node = el('span', 'cfg-chip', text);
  if (tone) node.dataset.tone = tone;
  return node;
}

/** Text out of a view-model carrier. Empty when there is none — never a placeholder sentence. */
const t = (node) => (node && typeof node.text === 'string' ? node.text : '');

function group(labelText) {
  const wrap = el('div', 'ls-group');
  wrap.appendChild(el('div', 'cfg-group-label', labelText));
  return wrap;
}

function clear(node) {
  if (node) node.textContent = '';
}

// ── module state ─────────────────────────────────────────────

let deps = null;
let root = null;

// Why a read failed, kept until there is a node to say it on. See `getJson`.
const loadFailure = { relations: null, sources: null, vocabulary: null, raw: null };

let relationsView = null;
let sourcesView = null;
let vocabView = null;

// The picked table and its columns — the datalist every column input offers.
let pickedRelation = null;

// ── entry points ─────────────────────────────────────────────
//
// THERE IS NO SCREEN HERE, AND THAT IS THE POINT (owner ruling, brief §6-1).
//   The structure view already carries a row for every declaration — translators, axes,
//   resolvers, kinds, mechanism, and the vocabulary — and each row knows its own identity
//   (`data-predicate`, `data-kind`, `data-edge`). So these editors mount INTO a row, not into
//   a page of their own. An editor that lives somewhere else makes the operator connect
//   「what I just edited」 to 「where on the map that lives」 by hand, and that connection is
//   half of what the map is for.
//
//   Everything below is therefore host-agnostic: each `open*Editor` takes the element it should
//   render into and builds only its own controls — no card, no title, no tab.

/**
 * @param {{apiBase: string, adminFetch: Function,
 *          failureFactOf: Function, renderResolveInto: Function}} options
 */
export function configureLedgerSetup(options) {
  deps = options;
}

/** Fetch the form material once. Every generated form is built out of these three payloads. */
export async function loadFormMaterial() {
  if (!deps) return;
  await Promise.all([loadRelations(''), loadSources(), loadVocabulary()]);
}

/** The source→ledger editor, rendered into a row of the declaration map. */
export function openSourceEditor(hostEl) {
  root = hostEl;
  clear(hostEl);
  hostEl.appendChild(sourceEditor());
  renderRelations();
  renderKinds();
  renderSourceForm();
  renderSourceMode();
}

/** The predicate editor, rendered into a vocabulary row (`data-predicate`) or its panel. */
export function openPredicateEditor(hostEl, options = {}) {
  root = hostEl;
  clear(hostEl);
  hostEl.appendChild(predicateEditor());
  renderPredicateForm();
  renderRetire();
  if (options.name) {
    const pred = (vocabView ? vocabView.predicates : []).find((p) => p.key === options.name);
    if (pred && pred.editable) prefillPredicate(pred);
  }
}

/** The predicate list — read-only, and the only place `editable` decides anything. */
export function renderPredicateListInto(hostEl) {
  ids.predicateList = hostEl;
  renderPredicates();
}

function group2(labelText) {
  const node = el('div', 'ls-editor');
  if (labelText) node.appendChild(el('div', 'cfg-group-label', labelText));
  return node;
}

const ids = {};

// ═══════════════════════════════════════════════════════════════
// LAYER 1 — source → ledger
// ═══════════════════════════════════════════════════════════════

function sourceEditor() {
  const node = group2(null);

  // — table picker
  const pick = group(LC.RELATION);
  const searchRow = el('div', 'retro-field');
  const search = el('input', 'retro-input');
  search.type = 'search';
  search.placeholder = LC.RELATION_SEARCH;
  search.addEventListener('input', debounce(() => loadRelations(search.value.trim()), 250));
  searchRow.appendChild(search);
  pick.appendChild(searchRow);
  ids.relationList = el('div', 'ls-relations');
  pick.appendChild(ids.relationList);
  ids.relationNote = el('div', 'cfg-detail');
  pick.appendChild(ids.relationNote);
  node.appendChild(pick);

  // — kind picker (generated from the server's kinds)
  const kinds = group(LC.KIND);
  ids.kindList = el('div', 'ls-kinds');
  kinds.appendChild(ids.kindList);
  ids.kindNote = el('div', 'cfg-detail', LC.NO_KIND_FIT);
  kinds.appendChild(ids.kindNote);
  node.appendChild(kinds);

  // — form ⇄ raw. Two spellings of ONE declaration, and they take the SAME three steps:
  //   validation, dry run, save. Hand-edited JSON is exactly where a wrong declaration is born,
  //   so it is the path where the preview earns the most — it does not get a shortcut.
  ids.modeRow = el('div', 'ls-modes');
  [['form', LC.MODE_FORM], ['raw', LC.MODE_RAW]].forEach(([mode, label]) => {
    const btn = el('button', 'ls-pill', label);
    btn.type = 'button';
    btn.dataset.mode = mode;
    btn.addEventListener('click', () => setSourceMode(mode));
    ids.modeRow.appendChild(btn);
  });
  node.appendChild(ids.modeRow);

  // — the generated form
  ids.sourceForm = el('div', 'ls-form');
  node.appendChild(ids.sourceForm);

  // — the raw declaration for this ONE source (never the whole file)
  ids.sourceRaw = el('div', 'ls-raw');
  node.appendChild(ids.sourceRaw);

  // — three-step write surface
  ids.sourceActions = el('div', 'retro-actions ls-actions');
  node.appendChild(ids.sourceActions);
  ids.sourceResult = el('div', 'ls-result');
  node.appendChild(ids.sourceResult);

  ids.sourceConfigPath = el('div', 'cfg-path');
  node.appendChild(ids.sourceConfigPath);
  return node;
}

// Source form state. Only what the operator typed — the shapes come from the payload.
const sourceForm = {
  kind: '',
  columns: {},           // role → column name
  occurredColumn: '',
  occurredFormat: '',
  occurredTimezone: '',
  subjectTypes: [],
  registerTypes: [],
  watermark: [],
  blocks: {},            // block id → { text } (raw JSON) or { fields: {name: value} }
};

// Which spelling of the declaration is being edited. Not a second declaration — one thing,
// two ways of typing it, one save path.
let sourceMode = 'form';
// The raw read: the declaration text, the file around it for context, and the fingerprint.
let rawState = null;
let rawEditor = null;

function setSourceMode(mode) {
  if (sourceMode === mode) return;
  sourceMode = mode;
  // A dry run measured the OTHER spelling. Switching spellings changes the declaration this
  // form is about, so the token it earned is not about this one.
  sourceFlow.invalidate();
  renderSourceMode();
}

function resetSourceForm() {
  sourceForm.kind = '';
  sourceForm.columns = {};
  sourceForm.occurredColumn = '';
  sourceForm.occurredFormat = '';
  sourceForm.occurredTimezone = '';
  sourceForm.subjectTypes = [];
  sourceForm.registerTypes = [];
  sourceForm.watermark = [];
  sourceForm.blocks = {};
}

async function loadRelations(q) {
  const view = await getJson(`/admin/ledger/relations?q=${encodeURIComponent(q || '')}`,
    buildRelationsView, 'relations');
  if (!view) return;
  relationsView = view;
  renderRelations();
}

// THE LOADERS RUN BEFORE ANY EDITOR IS MOUNTED, AND THAT IS THE NORMAL ORDER.
// `loadFormMaterial()` fetches once for the whole panel; `openSourceEditor`/`openPredicateEditor`
// mount later, onto whichever row the operator opened. So every renderer below must be a no-op
// when its nodes do not exist yet — the payload is cached and the open* call draws it. Without
// this the first load throws on `undefined.appendChild` and the panel never comes up.
function mounted(node) {
  return Boolean(node && node.appendChild);
}

function renderRelations() {
  if (!mounted(ids.relationList) || !mounted(ids.relationNote)) return;
  const view = relationsView;
  clear(ids.relationList);
  clear(ids.relationNote);
  if (loadFailure.relations) {
    ids.relationNote.appendChild(el('div', 'cfg-detail', loadFailure.relations));
  }
  if (!view) return;
  // The server's sentences come first and they are shown WHETHER OR NOT there are rows: a
  // search can match declared tables and still have something to say about an undeclared one.
  // EVERY entry renders — showing the first would be a silent cap on the one surface whose job
  // is to say what is missing.
  view.undeclared.forEach((entry) => {
    ids.relationNote.appendChild(relationNoteRow(entry, LC.UNDECLARED, 'warn'));
  });
  view.missing.forEach((entry) => {
    ids.relationNote.appendChild(relationNoteRow(entry, LC.MISSING_RELATION, 'danger'));
  });
  if (view.empty) {
    if (view.emptyText) ids.relationNote.appendChild(el('div', 'cfg-detail', t(view.emptyText)));
    return;
  }
  view.relations.forEach((rel) => {
    const btn = el('button', 'ls-pill');
    btn.type = 'button';
    btn.appendChild(el('span', 'cfg-subject', t(rel.name)));
    btn.appendChild(chip(`${LC.RELATION_COLUMNS} ${rel.columnCount.text}`, 'muted'));
    if (pickedRelation && pickedRelation.key === rel.key) btn.dataset.picked = '1';
    btn.addEventListener('click', () => {
      pickedRelation = rel;
      resetSourceForm();
      // The raw read and its fingerprint belonged to the PREVIOUS source. Carrying either to a
      // new table would send one declaration's `base` with another declaration's text.
      rawState = null;
      rawEditor = null;
      sourceFlow.invalidate();
      renderRelations();
      renderKinds();
      renderSourceForm();
      renderSourceMode();
    });
    ids.relationList.appendChild(btn);
  });
  // APPEND, never assign: `textContent =` here would erase the server's sentences above it, and
  // it would do so only on searches wide enough to truncate — the least reproducible way to
  // lose a message.
  if (view.truncated) {
    ids.relationNote.appendChild(el('div', 'cfg-detail', t(view.truncatedText)));
  }
  // How many tables the picker can ever offer, so four results is legible as a slice of a
  // known whole rather than as the whole world.
  if (view.declaredTotal) {
    const total = el('div', 'cfg-row-head');
    total.appendChild(el('span', 'cfg-path', t(view.declaredTotalLabel)));
    total.appendChild(el('span', 'cfg-jsonval', view.declaredTotal.text));
    ids.relationNote.appendChild(total);
  }
}

/** One `{name, detail_ko}` note under the picker — the server's sentence, verbatim, with the
 *  table it is about beside it. `undeclared` and `missing_relations` are opposite failures with
 *  different next steps, so they get different tones and are never folded together. */
function relationNoteRow(entry, labelText, tone) {
  const row = el('div', 'cfg-row');
  row.dataset.tone = tone;
  const head = el('div', 'cfg-row-head');
  head.appendChild(chip(labelText, tone));
  head.appendChild(el('span', 'cfg-subject', t(entry.name)));
  row.appendChild(head);
  if (entry.detail) row.appendChild(el('div', 'cfg-detail', t(entry.detail)));
  return row;
}

async function loadSources() {
  const view = await getJson('/admin/ledger/sources', buildSourcesView, 'sources');
  if (!view) return;
  sourcesView = view;
  renderKinds();
  renderSourceForm();
  // The path label is part of the editor's DOM, so it only exists once an editor is open.
  if (mounted(ids.sourceConfigPath)) ids.sourceConfigPath.textContent = t(view.configPath);
}

function renderKinds() {
  if (!mounted(ids.kindList)) return;
  clear(ids.kindList);
  if (loadFailure.sources && mounted(ids.kindNote)) {
    clear(ids.kindNote);
    ids.kindNote.appendChild(el('div', 'cfg-detail', loadFailure.sources));
  }
  if (!sourcesView) return;
  sourcesView.kinds.forEach((kind) => {
    const btn = el('button', 'ls-pill');
    btn.type = 'button';
    btn.appendChild(el('span', 'cfg-subject', t(kind.name)));
    if (kind.label) btn.appendChild(el('span', 'ls-pill-label', t(kind.label)));
    if (sourceForm.kind === kind.key) btn.dataset.picked = '1';
    btn.disabled = !pickedRelation;
    btn.addEventListener('click', () => {
      sourceForm.kind = kind.key;
      sourceForm.columns = {};
      sourceForm.blocks = {};
      sourceFlow.invalidate();
      renderKinds();
      renderSourceForm();
    });
    ids.kindList.appendChild(btn);
  });
  // A kind with no translator is shown WITH the server's sentence and cannot be picked —
  // the form must say so and stop, not quietly omit it.
  sourcesView.unsupported.forEach((kind) => {
    const box = el('div', 'ls-pill');
    box.dataset.tone = 'muted';
    box.appendChild(el('span', 'cfg-subject', t(kind.name)));
    box.appendChild(chip(LC.UNSUPPORTED, 'warn'));
    if (kind.detail) box.appendChild(el('span', 'cfg-detail', t(kind.detail)));
    ids.kindList.appendChild(box);
  });
}

function currentKind() {
  if (!sourcesView) return null;
  return sourcesView.kinds.find((k) => k.key === sourceForm.kind) || null;
}

function renderSourceForm() {
  if (!mounted(ids.sourceForm)) return;
  clear(ids.sourceForm);
  sourceFlow.render();
  const kind = currentKind();
  if (!pickedRelation || !kind) return;

  const columnNames = pickedRelation.columns.map((c) => c.key);

  // The selected grammar and its executable profile are one authoring choice. Show the
  // server-owned molecule/operator description before asking for mappings, so an operator
  // does not fill a lineage form and discover only at dry run that it groups two rows.
  const translator = group(LC.TRANSLATOR_PROFILE);
  const translatorFacts = el('div', 'retro-extras');
  [
    [LC.TRANSLATOR_PROFILE, kind.translator.profile],
    [LC.MOLECULE, kind.translator.molecule],
    [LC.OPERATOR, kind.translator.operator],
  ].forEach(([label, value]) => {
    if (!value) return;
    const item = el('span', 'retro-extra');
    item.appendChild(el('span', 'cfg-path', label));
    item.appendChild(el('span', 'cfg-jsonval', value.text));
    translatorFacts.appendChild(item);
  });
  translator.appendChild(translatorFacts);
  ids.sourceForm.appendChild(translator);

  // — column mapping: one input per role the KIND declared. Required and optional are the
  //   server's own split; the screen does not decide which is which.
  const cols = group(`${LC.COLUMNS} · ${LC.REQUIRED}`);
  kind.required.forEach((role) => {
    cols.appendChild(columnField(role, columnNames, true));
  });
  ids.sourceForm.appendChild(cols);
  if (kind.optional.length) {
    const opt = group(`${LC.COLUMNS} · ${LC.OPTIONAL}`);
    kind.optional.forEach((role) => opt.appendChild(columnField(role, columnNames, false)));
    ids.sourceForm.appendChild(opt);
  }

  // — occurred_at: column, format, timezone. No defaults: a timezone nobody declared is a
  //   nine-hour error that nothing complains about.
  const when = group(LC.OCCURRED_AT);
  when.appendChild(textField(LC.OCCURRED_AT_COLUMN, 'occurred_at_column', columnNames,
    () => sourceForm.occurredColumn, (v) => { sourceForm.occurredColumn = v; }));
  when.appendChild(textField(LC.OCCURRED_AT_FORMAT, 'occurred_at_format', null,
    () => sourceForm.occurredFormat, (v) => { sourceForm.occurredFormat = v; }));
  when.appendChild(textField(LC.OCCURRED_AT_TIMEZONE, 'occurred_at_timezone', null,
    () => sourceForm.occurredTimezone, (v) => { sourceForm.occurredTimezone = v; }));
  ids.sourceForm.appendChild(when);

  // — subject_types / register_entity_types: the declared entity types, from the vocabulary
  //   payload. Not a list this file keeps.
  const types = vocabView ? vocabView.entityTypes : [];
  ids.sourceForm.appendChild(
    checkField(LC.SUBJECT_TYPES, 'subject_types', types, sourceForm.subjectTypes));
  ids.sourceForm.appendChild(
    checkField(LC.REGISTER_TYPES, 'register_entity_types', types, sourceForm.registerTypes));

  // — watermark columns (ordered: the cursor reads them in order)
  ids.sourceForm.appendChild(listField(LC.WATERMARK, 'watermark.columns',
    columnNames, sourceForm.watermark));

  // — any other block the kind declared. A block that described its own fields gets inputs;
  //   one that did not gets a JSON box under its own name.
  kind.extraBlocks.forEach((block) => {
    const box = group(`${LC.BLOCKS} · ${nameText(block)}`);
    if (block.fields.length) {
      block.fields.forEach((f) => {
        const path = `${block.name}.${f.name}`;
        box.appendChild(textField(nameText(f), path, columnNames,
          () => blockField(block.name, f.name),
          (v) => setBlockField(block.name, f.name, v)));
      });
    } else {
      const wrap = el('div', 'retro-field');
      wrap.dataset.lsField = block.name;
      wrap.appendChild(el('label', 'ls-label', LC.BLOCK_JSON));
      const area = el('textarea', 'retro-input ls-json');
      area.rows = 4;
      area.value = (sourceForm.blocks[block.name] || {}).text || '';
      area.addEventListener('input', () => {
        sourceForm.blocks[block.name] = { text: area.value };
        sourceFlow.invalidate();
      });
      wrap.appendChild(area);
      box.appendChild(wrap);
    }
    ids.sourceForm.appendChild(box);
  });
}

/** Show the picked spelling, and load the raw declaration the first time it is asked for. */
function renderSourceMode() {
  if (!mounted(ids.modeRow)) return;
  Array.from(ids.modeRow.children).forEach((btn) => {
    if (btn.dataset.mode === sourceMode) btn.dataset.picked = '1';
    else delete btn.dataset.picked;
  });
  if (mounted(ids.sourceForm)) ids.sourceForm.style.display = sourceMode === 'form' ? '' : 'none';
  if (mounted(ids.sourceRaw)) ids.sourceRaw.style.display = sourceMode === 'raw' ? '' : 'none';
  if (sourceMode === 'raw' && pickedRelation && !rawState) loadRaw(pickedRelation.key);
}

async function loadRaw(name) {
  if (!mounted(ids.sourceRaw)) return;
  clear(ids.sourceRaw);
  ids.sourceRaw.appendChild(el('div', 'cfg-detail', LC.RAW_LOADING));
  const view = await getJson(RAW_READ_PATH(name), buildRawView, 'raw');
  if (!view) {
    clear(ids.sourceRaw);
    if (loadFailure.raw) ids.sourceRaw.appendChild(el('div', 'cfg-detail', loadFailure.raw));
    return;
  }
  rawState = view;
  renderRaw();
}

function renderRaw() {
  if (!mounted(ids.sourceRaw) || !rawState) return;
  clear(ids.sourceRaw);
  rawEditor = null;
  if (rawState.path) ids.sourceRaw.appendChild(el('div', 'cfg-path', t(rawState.path)));

  const box = el('div', 'ls-raw-editor');
  ids.sourceRaw.appendChild(box);

  // Monaco when the host page has it (admin loads it for the code editor); a textarea when it
  // does not. The fallback is deliberate — a raw editor that only exists on one page is a raw
  // editor that disappears the day the panel moves, and losing the control is worse than
  // losing the syntax colouring.
  if (window.monaco && window.monaco.editor) {
    rawEditor = window.monaco.editor.create(box, {
      value: rawState.text,
      language: 'json',
      automaticLayout: true,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      theme: document.documentElement.dataset.theme === 'light' ? 'vs' : 'vs-dark',
    });
    rawEditor.onDidChangeModelContent(() => sourceFlow.invalidate());
  } else {
    const area = el('textarea', 'retro-input ls-json');
    area.rows = 18;
    area.value = rawState.text;
    area.addEventListener('input', () => {
      rawState.text = area.value;
      sourceFlow.invalidate();
    });
    box.appendChild(area);
  }

  // What else is in the file — NAMES ONLY, because names are all the route sends. Its docstring
  // says the whole document is readable here; its payload sends `sources`. The screen shows the
  // one that exists rather than an empty 「파일 전체」 box claiming a context nobody sent.
  if (rawState.siblings.length) {
    const context = el('details', 'cfg-views');
    context.appendChild(el('summary', null,
      `${LC.RAW_CONTEXT} (${rawState.siblings.length})`));
    const list = el('div', 'cfg-row-head');
    rawState.siblings.forEach((name) => list.appendChild(chip(name, 'muted')));
    context.appendChild(list);
    ids.sourceRaw.appendChild(context);
  }

  // The server's sentence about why one source is the unit. Verbatim — this is the reasoning
  // behind the constraint the operator is about to work inside of.
  if (rawState.note) ids.sourceRaw.appendChild(el('div', 'cfg-detail', t(rawState.note)));
  // A read that failed says so instead of presenting an empty editor, which looks exactly like
  // an empty declaration and would invite the operator to "fix" it by typing one.
  if (rawState.error) {
    const box = el('div', 'cfg-row');
    box.dataset.tone = 'danger';
    box.appendChild(el('div', 'cfg-detail', t(rawState.error)));
    ids.sourceRaw.appendChild(box);
  }
}

/** What the raw editor currently holds. Monaco owns its buffer, so it is asked rather than
 *  mirrored — a shadow copy of an editor's text is a copy that goes stale mid-keystroke. */
function rawText() {
  if (rawEditor) return rawEditor.getValue();
  return rawState ? rawState.text : '';
}

function blockField(blockId, fieldName) {
  const b = sourceForm.blocks[blockId];
  return (b && b.fields && b.fields[fieldName]) || '';
}

function setBlockField(blockId, fieldName, value) {
  const b = sourceForm.blocks[blockId] || { fields: {} };
  if (!b.fields) b.fields = {};
  b.fields[fieldName] = value;
  sourceForm.blocks[blockId] = b;
}

function columnField(role, columnNames, required) {
  return textField(nameText(role), `columns.${role.name}`, columnNames,
    () => sourceForm.columns[role.name] || '',
    (v) => { sourceForm.columns[role.name] = v; }, required);
}

/** One labelled text input. `options` (when given) become a datalist — the table's real columns
 *  are OFFERED, never enforced: a screen that refuses what the server would accept is a second
 *  gate, and the second gate is always the wrong one. */
function textField(labelText, path, options, get, set, required) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  const label = el('label', 'ls-label', labelText);
  if (required) label.appendChild(chip(LC.REQUIRED, 'warn'));
  wrap.appendChild(label);
  const input = el('input', 'retro-input');
  input.type = 'text';
  input.value = get() || '';
  if (options && options.length) {
    const listId = `ls-dl-${path.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
    let dl = document.getElementById(listId);
    if (!dl) {
      dl = el('datalist');
      dl.id = listId;
      wrap.appendChild(dl);
    }
    clear(dl);
    options.forEach((o) => {
      const opt = el('option');
      opt.value = o;
      dl.appendChild(opt);
    });
    input.setAttribute('list', listId);
  }
  input.addEventListener('input', () => {
    set(input.value.trim());
    sourceFlow.invalidate();
  });
  wrap.appendChild(input);
  return wrap;
}

/** A multi-select over a server-supplied list, backed by an array in form state. */
function checkField(labelText, path, entries, target) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', labelText));
  const box = el('div', 'ls-checks');
  entries.forEach((entry) => {
    const label = el('label', 'ls-check');
    const input = el('input');
    input.type = 'checkbox';
    input.checked = target.includes(entry.name);
    input.addEventListener('change', () => {
      const at = target.indexOf(entry.name);
      if (input.checked && at < 0) target.push(entry.name);
      if (!input.checked && at >= 0) target.splice(at, 1);
      sourceFlow.invalidate();
    });
    label.appendChild(input);
    label.appendChild(el('span', null, nameText(entry)));
    box.appendChild(label);
  });
  wrap.appendChild(box);
  return wrap;
}

/** An ordered list of strings (watermark columns). Order is part of the declaration. */
function listField(labelText, path, options, target) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', labelText));
  const rows = el('div', 'ls-list');
  const draw = () => {
    clear(rows);
    target.forEach((value, index) => {
      const row = el('div', 'ls-list-row');
      const input = el('input', 'retro-input');
      input.type = 'text';
      input.value = value;
      if (options && options.length) {
        const listId = `ls-dl-${path.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
        let dl = document.getElementById(listId);
        if (!dl) {
          dl = el('datalist');
          dl.id = listId;
          wrap.appendChild(dl);
          options.forEach((o) => {
            const opt = el('option');
            opt.value = o;
            dl.appendChild(opt);
          });
        }
        input.setAttribute('list', listId);
      }
      input.addEventListener('input', () => {
        target[index] = input.value.trim();
        sourceFlow.invalidate();
      });
      const remove = el('button', 'glass-btn cfg-btn', LC.REMOVE);
      remove.type = 'button';
      remove.addEventListener('click', () => {
        target.splice(index, 1);
        sourceFlow.invalidate();
        draw();
      });
      row.appendChild(input);
      row.appendChild(remove);
      rows.appendChild(row);
    });
    const add = el('button', 'glass-btn cfg-btn', LC.ADD);
    add.type = 'button';
    add.addEventListener('click', () => {
      target.push('');
      sourceFlow.invalidate();
      draw();
    });
    rows.appendChild(add);
  };
  draw();
  wrap.appendChild(rows);
  return wrap;
}

/** The declaration this form describes. Empty inputs are OMITTED rather than sent as "" — an
 *  empty string is a declared emptiness, and the server's refusal for a missing field is the
 *  sentence the operator needs. The screen does not pre-empt it. */
/** The declaration fields for the wire: `{raw}` from the editor, `{declaration}` from the form.
 *
 * 🔴 RAW GOES UNDER `raw`, NOT UNDER `declaration`. `declaration_rejected` comes back with a
 * line AND a column, which only the side that did the parsing can name — if the client parsed
 * first it would have to author the syntax error itself, the one thing this screen must never
 * do. The operator's characters go over the wire exactly as typed. */
function sourcePayloadFields() {
  if (sourceMode === 'raw') return { raw: rawText() };
  return { declaration: sourceDeclaration() };
}

function sourceDeclaration() {
  const kind = currentKind();
  const out = {};
  if (kind) out.kind = kind.key;
  if (sourceForm.occurredColumn) out.occurred_at_column = sourceForm.occurredColumn;
  if (sourceForm.occurredFormat) out.occurred_at_format = sourceForm.occurredFormat;
  if (sourceForm.occurredTimezone) out.occurred_at_timezone = sourceForm.occurredTimezone;
  if (sourceForm.subjectTypes.length) out.subject_types = sourceForm.subjectTypes.slice();
  if (sourceForm.registerTypes.length) {
    out.register_entity_types = sourceForm.registerTypes.slice();
  }
  const marks = sourceForm.watermark.filter(Boolean);
  if (marks.length) out.watermark = { columns: marks };
  const columns = {};
  Object.keys(sourceForm.columns).forEach((role) => {
    if (sourceForm.columns[role]) columns[role] = sourceForm.columns[role];
  });
  if (Object.keys(columns).length) out.columns = columns;
  Object.keys(sourceForm.blocks).forEach((blockId) => {
    const b = sourceForm.blocks[blockId];
    if (b && b.fields) {
      const fields = {};
      Object.keys(b.fields).forEach((f) => { if (b.fields[f]) fields[f] = b.fields[f]; });
      if (Object.keys(fields).length) out[blockId] = fields;
      return;
    }
    const text = (b && b.text ? b.text : '').trim();
    if (!text) return;
    // A JSON box that does not parse is sent as the TEXT it is. The server owns
    // `declaration_rejected`, and a client-side parse verdict would be a second judge.
    try {
      out[blockId] = JSON.parse(text);
    } catch (e) {
      out[blockId] = text;
    }
  });
  return out;
}

// ═══════════════════════════════════════════════════════════════
// LAYER 2 — vocabulary (ontology layer only)
// ═══════════════════════════════════════════════════════════════

function predicateEditor() {
  const node = group2(null);

  const formGroup = group(LC.PREDICATE_NEW);
  const nameRow = el('div', 'retro-field');
  nameRow.dataset.lsField = 'name';
  nameRow.appendChild(el('label', 'ls-label', LC.NAME));
  ids.predicateName = el('input', 'retro-input');
  ids.predicateName.type = 'text';
  ids.predicateName.addEventListener('input', () => predicateFlow.invalidate());
  nameRow.appendChild(ids.predicateName);
  formGroup.appendChild(nameRow);
  ids.predicateForm = el('div', 'ls-form');
  formGroup.appendChild(ids.predicateForm);
  node.appendChild(formGroup);

  ids.predicateActions = el('div', 'retro-actions ls-actions');
  node.appendChild(ids.predicateActions);
  ids.predicateResult = el('div', 'ls-result');
  node.appendChild(ids.predicateResult);

  // Retirement — the ONLY removal path there is. There is no delete route anywhere and no
  // delete affordance on this screen, for either target.
  const retire = group(LC.RETIRE);
  ids.retireRow = el('div', 'retro-field');
  retire.appendChild(ids.retireRow);
  ids.retireResult = el('div', 'ls-result');
  retire.appendChild(ids.retireResult);
  node.appendChild(retire);

  ids.vocabConfigPath = el('div', 'cfg-path');
  node.appendChild(ids.vocabConfigPath);
  return node;
}

// Predicate form state: one entry per signature field the server declared.
const predicateForm = { fields: {} };

async function loadVocabulary() {
  const view = await getJson('/admin/ledger/vocabulary', buildVocabularyView, 'vocabulary');
  if (!view) return;
  vocabView = view;
  renderPredicates();
  renderPredicateForm();
  renderRetire();
  if (mounted(ids.vocabConfigPath)) ids.vocabConfigPath.textContent = t(view.configPath);
  // The entity-type checkboxes on the source form come from this payload.
  renderSourceForm();
}

function renderPredicates() {
  if (!mounted(ids.predicateList)) return;
  clear(ids.predicateList);
  if (loadFailure.vocabulary) {
    ids.predicateList.appendChild(el('div', 'cfg-detail', loadFailure.vocabulary));
  }
  if (!vocabView) return;
  if (vocabView.empty) {
    ids.predicateList.appendChild(el('div', 'cfg-detail', t(vocabView.emptyText)));
    return;
  }
  vocabView.predicates.forEach((pred) => {
    const row = el('div', 'cfg-row');
    const head = el('div', 'cfg-row-head');
    head.appendChild(el('span', 'cfg-subject', t(pred.name)));
    if (pred.origin) head.appendChild(chip(t(pred.origin), pred.originTone));
    if (pred.layer) head.appendChild(chip(t(pred.layer), 'muted'));
    if (pred.status) head.appendChild(chip(t(pred.status), pred.statusTone));
    head.appendChild(chip(pred.editable ? LC.EDITABLE : LC.READ_ONLY,
      pred.editable ? '' : 'muted'));
    if (pred.since) head.appendChild(el('span', 'cfg-path', t(pred.since)));
    row.appendChild(head);
    if (pred.label) row.appendChild(el('div', 'cfg-detail', t(pred.label)));

    const facts = el('div', 'ls-facts');
    if (pred.subject.length) {
      facts.appendChild(fact('subject', pred.subject.map(t).join(' · ')));
    }
    if (pred.objectKind) facts.appendChild(fact('object.kind', t(pred.objectKind)));
    if (pred.objectRequired.length) {
      facts.appendChild(fact('object.required', pred.objectRequired.map(t).join(' · ')));
    }
    if (pred.objectTypes.length) {
      facts.appendChild(fact('object.types', pred.objectTypes.map(t).join(' · ')));
    }
    if (pred.qualifiers.length) {
      facts.appendChild(fact('qualifiers', pred.qualifiers.map(t).join(' · ')));
    }
    facts.appendChild(fact('traversable', t(pred.traversable)));
    if (pred.direction) facts.appendChild(fact('direction', t(pred.direction)));
    if (pred.supersededBy) facts.appendChild(fact('superseded_by', t(pred.supersededBy)));
    row.appendChild(facts);

    // Prefill is offered only where the server said the entry is editable — which is only
    // `origin == "config"`. Canonical and code-loaded ontology are read-only, because code.
    if (pred.editable) {
      const load = el('button', 'glass-btn cfg-btn', LC.LOAD_INTO_FORM);
      load.type = 'button';
      load.addEventListener('click', () => prefillPredicate(pred));
      row.appendChild(load);
    }
    ids.predicateList.appendChild(row);
  });
}

function fact(label, value) {
  const box = el('span', 'retro-extra');
  box.appendChild(el('span', 'cfg-path', label));
  box.appendChild(el('span', 'cfg-jsonval', value));
  return box;
}

function prefillPredicate(pred) {
  ids.predicateName.value = pred.key;
  predicateForm.fields = {};
  const raw = pred.raw || {};
  (vocabView ? vocabView.signatureFields : []).forEach((field) => {
    if (Object.prototype.hasOwnProperty.call(raw, field.name)) {
      predicateForm.fields[field.name] = raw[field.name];
    }
  });
  predicateFlow.invalidate();
  renderPredicateForm();
}

/** The new-predicate form, generated from `signature_fields` — EXACTLY what the server said a
 *  new predicate must supply, in the server's order. A field this screen has no special widget
 *  for still gets a text box: an undrawn field is still a required field. */
function renderPredicateForm() {
  if (!mounted(ids.predicateForm)) return;
  clear(ids.predicateForm);
  predicateFlow.render();
  if (!vocabView) return;
  vocabView.signatureFields.forEach((field) => {
    ids.predicateForm.appendChild(predicateField(field));
  });
}

function predicateField(field) {
  const name = field.name;
  const label = nameText(field);
  const get = () => predicateForm.fields[name];
  const set = (value) => {
    if (value === undefined) delete predicateForm.fields[name];
    else predicateForm.fields[name] = value;
    predicateFlow.invalidate();
  };

  if (name === 'layer') {
    // The only layer this screen can write to. Canonical is not extensible from a screen.
    const wrap = el('div', 'retro-field');
    wrap.dataset.lsField = name;
    wrap.appendChild(el('label', 'ls-label', label));
    wrap.appendChild(chip(vocabView.editableLayer, 'ok'));
    if (get() === undefined) predicateForm.fields[name] = vocabView.editableLayer;
    return wrap;
  }
  if (name === 'subject' || name === 'object_types') {
    return multiField(label, name, vocabView.entityTypes, get, set);
  }
  if (name === 'qualifiers') {
    return csvField(label, name, get, set);
  }
  if (name === 'traversable') {
    // THREE-WAY, EXPLICIT, NO DEFAULT. A defaulted traversable is a declaration nobody made.
    return radioField(label, name, vocabView.traversableStates, get, set);
  }
  if (name === 'direction') {
    return selectField(label, name, vocabView.walkDirections, get, set);
  }
  if (name === 'status') {
    return selectField(label, name, vocabView.statuses, get, set);
  }
  if (name === 'object') {
    return objectField(label, name, get, set);
  }
  return plainField(label, name, get, set);
}

function plainField(label, path, get, set) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', label));
  const input = el('input', 'retro-input');
  input.type = 'text';
  const current = get();
  input.value = current === undefined || current === null ? '' : String(current);
  input.addEventListener('input', () => {
    const v = input.value.trim();
    set(v === '' ? undefined : v);
  });
  wrap.appendChild(input);
  return wrap;
}

function csvField(label, path, get, set) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', label));
  const input = el('input', 'retro-input');
  input.type = 'text';
  const current = get();
  input.value = Array.isArray(current) ? current.join(', ') : '';
  input.addEventListener('input', () => {
    const parts = input.value.split(',').map((s) => s.trim()).filter(Boolean);
    set(parts.length ? parts : undefined);
  });
  wrap.appendChild(input);
  return wrap;
}

function multiField(label, path, entries, get, set) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', label));
  const box = el('div', 'ls-checks');
  entries.forEach((entry) => {
    const item = el('label', 'ls-check');
    const input = el('input');
    input.type = 'checkbox';
    const current = Array.isArray(get()) ? get() : [];
    input.checked = current.includes(entry.name);
    input.addEventListener('change', () => {
      const now = Array.isArray(get()) ? get().slice() : [];
      const at = now.indexOf(entry.name);
      if (input.checked && at < 0) now.push(entry.name);
      if (!input.checked && at >= 0) now.splice(at, 1);
      set(now.length ? now : undefined);
    });
    item.appendChild(input);
    item.appendChild(el('span', null, nameText(entry)));
    box.appendChild(item);
  });
  wrap.appendChild(box);
  return wrap;
}

function selectField(label, path, entries, get, set) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', label));
  const select = el('select', 'glass-select retro-input');
  const blank = el('option', null, LC.UNSET_OPTION);
  blank.value = '';
  select.appendChild(blank);
  entries.forEach((entry) => {
    const opt = el('option', null, nameText(entry));
    opt.value = entry.name;
    select.appendChild(opt);
  });
  const current = get();
  select.value = current === undefined || current === null ? '' : String(current);
  select.addEventListener('change', () => {
    set(select.value === '' ? undefined : select.value);
  });
  wrap.appendChild(select);
  return wrap;
}

/** A radio group with NO preselected option. The empty state is "nobody chose yet", and it is
 *  not the same thing as any of the choices. */
function radioField(label, path, states, get, set) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', label));
  const box = el('div', 'ls-checks');
  const groupName = `ls-radio-${path}`;
  states.forEach((state) => {
    const item = el('label', 'ls-check');
    const input = el('input');
    input.type = 'radio';
    input.name = groupName;
    const current = get();
    input.checked = current !== undefined && current === state.value;
    input.addEventListener('change', () => { if (input.checked) set(state.value); });
    item.appendChild(input);
    item.appendChild(el('span', null, nameText(state)));
    item.appendChild(el('span', 'cfg-jsonval', JSON.stringify(state.value)));
    box.appendChild(item);
  });
  wrap.appendChild(box);
  return wrap;
}

/** `object` is `null` or `{kind, required[], types[]}`. Three states, and they are different:
 *  未선택 (the field is not in the declaration at all), explicit `null`, and a kind. */
function objectField(label, path, get, set) {
  const wrap = el('div', 'retro-field');
  wrap.dataset.lsField = path;
  wrap.appendChild(el('label', 'ls-label', label));

  const current = get();
  const asObject = current && typeof current === 'object' ? current : null;

  const select = el('select', 'glass-select retro-input');
  const blank = el('option', null, LC.UNSET_OPTION);
  blank.value = '';
  select.appendChild(blank);
  const nullOpt = el('option', null, LC.NULL_OPTION);
  nullOpt.value = '\u0000null';
  select.appendChild(nullOpt);
  vocabView.objectKinds.forEach((kind) => {
    const opt = el('option', null, nameText(kind));
    opt.value = kind.name;
    select.appendChild(opt);
  });
  if (current === null) select.value = '\u0000null';
  else if (asObject && asObject.kind != null) select.value = String(asObject.kind);
  else select.value = '';
  wrap.appendChild(select);

  const detail = el('div', 'ls-object-detail');
  const required = el('input', 'retro-input');
  required.type = 'text';
  required.placeholder = 'required';
  required.value = asObject && Array.isArray(asObject.required) ? asObject.required.join(', ') : '';
  const types = el('input', 'retro-input');
  types.type = 'text';
  types.placeholder = 'types';
  types.value = asObject && Array.isArray(asObject.types) ? asObject.types.join(', ') : '';
  detail.appendChild(required);
  detail.appendChild(types);
  wrap.appendChild(detail);

  const csv = (input) => input.value.split(',').map((s) => s.trim()).filter(Boolean);
  const push = () => {
    if (select.value === '') { set(undefined); return; }
    if (select.value === '\u0000null') { set(null); return; }
    const out = { kind: select.value };
    const req = csv(required);
    if (req.length) out.required = req;
    const ts = csv(types);
    if (ts.length) out.types = ts;
    set(out);
  };
  select.addEventListener('change', push);
  required.addEventListener('input', push);
  types.addEventListener('input', push);
  return wrap;
}

function predicateDeclaration() {
  const out = {};
  Object.keys(predicateForm.fields).forEach((key) => {
    const value = predicateForm.fields[key];
    if (value === undefined) return;
    out[key] = value;
  });
  return out;
}

// ── retirement ───────────────────────────────────────────────

function renderRetire() {
  if (!mounted(ids.retireRow)) return;
  clear(ids.retireRow);
  if (!vocabView) return;
  const editable = vocabView.predicates.filter((p) => p.editable);
  const options = vocabView.predicates;

  ids.retireRow.appendChild(el('label', 'ls-label', LC.RETIRE));
  const target = el('select', 'glass-select retro-input');
  const blank = el('option', null, LC.UNSET_OPTION);
  blank.value = '';
  target.appendChild(blank);
  editable.forEach((p) => {
    const opt = el('option', null, p.key);
    opt.value = p.key;
    target.appendChild(opt);
  });
  ids.retireRow.appendChild(target);

  ids.retireRow.appendChild(el('label', 'ls-label', LC.RETIRE_SUPERSEDED_BY));
  const superseded = el('select', 'glass-select retro-input');
  const blank2 = el('option', null, LC.UNSET_OPTION);
  blank2.value = '';
  superseded.appendChild(blank2);
  options.forEach((p) => {
    const opt = el('option', null, p.key);
    opt.value = p.key;
    superseded.appendChild(opt);
  });
  ids.retireRow.appendChild(superseded);

  const btn = el('button', 'glass-btn cfg-btn', LC.RETIRE);
  btn.type = 'button';
  btn.addEventListener('click', async () => {
    if (!target.value) return;
    btn.disabled = true;
    try {
      const res = await post('/admin/ledger/vocabulary/retire',
        { name: target.value, superseded_by: superseded.value || null }, LC.RETIRE_FAILED);
      if (!res) return;
      if (res.violations) {
        renderViolations(ids.retireResult, res.violations, ids.retireRow);
        return;
      }
      clear(ids.retireResult);
      const view = buildSaveView(res.body);
      renderSaveResult(ids.retireResult, view);
      await loadVocabulary();
    } finally {
      btn.disabled = false;
    }
  });
  ids.retireRow.appendChild(btn);
}

// ═══════════════════════════════════════════════════════════════
// LAYER 3 — ontology (physics and names)
// ═══════════════════════════════════════════════════════════════

/** Physics and names — `mechanism_models.json` and `ledger_journey.json`.
 *
 * NOT BUILT, and the reason is a missing route rather than a missing decision: there is no
 * admin route for either file. `GET/POST /admin/scripts/code` is whitelisted to `mappers/` and
 * `ingestion_workspace/`, and the ledger contract adds nothing for `server/config/`. The
 * structure view has a 기전 panel and a 선언 지도 group for both files, so the editor belongs on
 * those rows the day a route exists — not on a page of its own. */

// ═══════════════════════════════════════════════════════════════
// THE THREE-STEP WRITE — one implementation, two targets
// ═══════════════════════════════════════════════════════════════

/** A write surface: dry run, then (and only then) save.
 *
 * `dry` holds the token AND the declaration it was measured on. `invalidate()` drops both, and
 * every input on both forms calls it. The save button is created inside `render()` and only
 * when the stored key still equals the current declaration — so "the form changed" removes the
 * button by construction rather than by remembering to.
 */
function createFlow(config) {
  const state = { dry: null, busy: false };

  /** Any edit to the form drops the dry run AND redraws the action row.
   *
   * The redraw is unconditional on purpose. An earlier version only redrew when there WAS a
   * stored dry run, and the predicate surface was then unreachable: its name is typed rather
   * than clicked, so the action row kept the disabled button it was built with and typing a
   * name never re-enabled it. "Only redraw when something was invalidated" is the wrong test —
   * the button's enablement depends on the form too. */
  function invalidate() {
    state.dry = null;
    render();
  }

  function currentKey() {
    return `${config.getName()}\u0000${declarationKey(config.payloadFields())}`;
  }

  function render() {
    const actions = config.actionsEl();
    if (!actions) return;
    clear(actions);

    const dryBtn = el('button', 'glass-btn cfg-btn', state.busy ? LC.DRY_RUN_RUNNING : LC.DRY_RUN);
    dryBtn.type = 'button';
    dryBtn.disabled = state.busy || !config.getName();
    dryBtn.addEventListener('click', runDry);
    actions.appendChild(dryBtn);

    // THE SAVE CONTROL DOES NOT EXIST until a dry run of THIS declaration has returned.
    if (state.dry && state.dry.key === currentKey()) {
      const saveBtn = el('button', 'glass-btn btn-primary cfg-btn',
        state.busy ? LC.SAVING : LC.SAVE);
      saveBtn.type = 'button';
      saveBtn.disabled = state.busy;
      saveBtn.addEventListener('click', runSave);
      actions.appendChild(saveBtn);
    } else if (state.dry) {
      actions.appendChild(chip(LC.DRY_RUN_STALE, 'warn'));
    }
  }

  async function runDry() {
    state.busy = true;
    render();
    const key = currentKey();
    try {
      // 🔴 `declaration` OR `raw`, NEVER BOTH. The route only reaches `parse_raw_declaration`
      // when `declaration is None`, so a raw edit sent under `declaration` would skip the parser
      // entirely and hand a STRING to a checker that expects a mapping — the operator would get
      // a refusal about their declaration's shape instead of about their JSON.
      const res = await post('/admin/ledger/dry-run', Object.assign({
        target: config.target,
        name: config.getName(),
        rows: 20,
      }, config.payloadFields()), LC.DRY_RUN_FAILED);
      if (!res) return;
      const result = config.resultEl();
      clear(result);
      clearFieldViolations(config.formEl());
      if (res.violations) {
        state.dry = null;
        renderViolations(result, res.violations, config.formEl());
        return;
      }
      const view = buildDryRunView(res.body);
      // The sentence is kept so the save confirmation can QUOTE it. The client does not
      // summarise a write in words of its own, and this is the only place it could have.
      state.dry = { key, token: view.token, sentence: view.sentence ? view.sentence.text : '' };
      renderDryRun(result, view);
    } finally {
      state.busy = false;
      render();
    }
  }

  async function runSave() {
    if (!state.dry) return;
    // One confirmation, and it quotes the SERVER's dry-run sentence about what this declaration
    // does. The client does not summarise a write in words of its own.
    if (state.dry.sentence && !window.confirm(state.dry.sentence)) return;
    state.busy = true;
    render();
    try {
      // `base` rides along ONLY from the raw editor, and only because it read one. The form has
      // no such object: it builds a declaration from inputs rather than from a file it read, so
      // it has nothing to claim it was based on. Sending a fabricated one would be worse than
      // sending none — it would defeat the very check it looks like it is passing.
      const res = await post('/admin/ledger/save', Object.assign({
        target: config.target,
        name: config.getName(),
        token: state.dry.token,
      }, config.payloadFields(), config.extraSave ? config.extraSave() : {}));
      if (!res) return;
      const result = config.resultEl();
      clear(result);
      clearFieldViolations(config.formEl());
      if (res.violations) {
        // `dry_run_stale` lands here like any other refusal — same shape, same rendering.
        state.dry = null;
        renderViolations(result, res.violations, config.formEl());
        return;
      }
      state.dry = null;
      renderSaveResult(result, buildSaveView(res.body));
      if (config.onSaved) await config.onSaved();
    } finally {
      state.busy = false;
      render();
    }
  }

  return { invalidate, render };
}

const sourceFlow = createFlow({
  target: 'source',
  getName: () => (pickedRelation ? pickedRelation.key : ''),
  payloadFields: sourcePayloadFields,
  actionsEl: () => ids.sourceActions,
  resultEl: () => ids.sourceResult,
  // Refusals attach to inputs in form mode. In raw mode there are no inputs to attach to —
  // `field` has nothing to point at inside a text buffer — so they render in the list only.
  formEl: () => (sourceMode === 'form' ? ids.sourceForm : null),
  extraSave: () => ((sourceMode === 'raw' && rawState && rawState.base)
    ? { base: rawState.base } : {}),
  onSaved: async () => {
    // The file changed, so the fingerprint this editor is holding is spent. Drop it and re-read
    // rather than keep one that would now come back `stale_base` — against our own write.
    rawState = null;
    rawEditor = null;
    await loadSources();
    if (sourceMode === 'raw' && pickedRelation) await loadRaw(pickedRelation.key);
  },
});

const predicateFlow = createFlow({
  target: 'predicate',
  getName: () => (ids.predicateName ? ids.predicateName.value.trim() : ''),
  payloadFields: () => ({ declaration: predicateDeclaration() }),
  actionsEl: () => ids.predicateActions,
  resultEl: () => ids.predicateResult,
  formEl: () => ids.predicateForm,
  onSaved: () => loadVocabulary(),
});

// ── rendering the three results ──────────────────────────────

function renderDryRun(container, view) {
  const box = el('div', 'cfg-dryrun');
  if (view.readOnlyTone === 'ok') box.dataset.tone = 'ok';
  else box.dataset.tone = 'danger';

  // The server's sentence first — it is the thing worth reading.
  if (view.sentence) box.appendChild(el('div', 'cfg-detail', t(view.sentence)));

  const facts = el('div', 'retro-extras');
  view.facts.forEach((f) => {
    const item = el('span', 'retro-extra');
    item.appendChild(el('span', 'cfg-path', f.key));
    const value = el('span', 'cfg-jsonval', f.value.text);
    if (f.tone) value.dataset.tone = f.tone;
    item.appendChild(value);
    facts.appendChild(item);
  });
  const ro = el('span', 'retro-extra');
  ro.appendChild(el('span', 'cfg-path', t(view.readOnlyLabel)));
  ro.appendChild(el('span', 'cfg-jsonval', view.readOnly.text));
  facts.appendChild(ro);
  box.appendChild(facts);

  if (view.sourceContract) renderSourceContract(box, view.sourceContract);

  if (view.truncated) box.appendChild(chip(t(view.truncatedText), 'warn'));

  if (view.refusals.length) {
    const refusals = el('div');
    refusals.appendChild(el('div', 'cfg-group-label', t(view.refusalsLabel)));
    view.refusals.forEach((r) => {
      const row = el('div', 'cfg-row');
      row.dataset.tone = 'danger';
      const head = el('div', 'cfg-row-head');
      if (r.reason) head.appendChild(chip(t(r.reason), 'danger'));
      if (r.moleculeRef) head.appendChild(el('span', 'cfg-path', r.moleculeRef.text));
      row.appendChild(head);
      // The gate's own sentence. Verbatim.
      if (r.detail) row.appendChild(el('div', 'cfg-detail', t(r.detail)));
      refusals.appendChild(row);
    });
    box.appendChild(refusals);
  }

  // A predicate dry run has no atoms to show — it has the gate's own verdicts on a candidate
  // signature. Rendered as what it is: the case, whether the gate took it, and the gate's own
  // violation strings when it did not.
  if (view.probes.length) {
    const probes = el('div', 'ls-probes');
    probes.appendChild(el('div', 'cfg-group-label', t(view.probesLabel)));
    view.probes.forEach((probe) => {
      const row = el('div', 'cfg-row');
      if (!probe.accepted) row.dataset.tone = 'danger';
      const head = el('div', 'cfg-row-head');
      head.appendChild(chip(probe.accepted ? LC.PROBE_ACCEPTED : LC.PROBE_REFUSED,
        probe.accepted ? 'ok' : 'danger'));
      if (probe.caseText) head.appendChild(el('span', 'cfg-detail', t(probe.caseText)));
      row.appendChild(head);
      probe.violations.forEach((v) => row.appendChild(el('div', 'cfg-detail', t(v))));
      probes.appendChild(row);
    });
    box.appendChild(probes);
  }

  if (view.atoms.length) {
    const atoms = el('details', 'cfg-views ls-atoms');
    atoms.open = true;
    const summary = el('summary', null, `${t(view.atomsLabel)} (${view.atoms.length})`);
    atoms.appendChild(summary);
    view.atoms.forEach((atom) => {
      // AS THEY ARE. The envelope's own keys, the envelope's own order.
      atoms.appendChild(el('pre', 'ls-atom', JSON.stringify(atom.raw, null, 2)));
    });
    box.appendChild(atoms);
  }
  container.appendChild(box);
}

/** Draw the server-compiled authoring contract before the sample atoms.
 *
 * A sample answers "what fired in these rows".  This block answers the more important setup
 * question: "what can this translator ever say, and will the live vocabulary accept it?".
 */
function renderSourceContract(container, contract) {
  const wrap = el('details', 'cfg-views ls-source-contract');
  wrap.open = true;
  const summary = el('summary', null, t(contract.title));
  summary.appendChild(chip(contract.state.text,
    contract.state.raw === 'ready' ? 'ok' : 'danger'));
  wrap.appendChild(summary);
  if (contract.sentence) wrap.appendChild(el('div', 'cfg-detail', t(contract.sentence)));

  const profile = el('div', 'retro-extras');
  [
    [contract.labels.profile, contract.translator.profile],
    [contract.labels.molecule, contract.translator.molecule],
    [contract.labels.operator, contract.translator.operator],
  ].forEach(([label, value]) => {
    if (!value) return;
    const item = el('span', 'retro-extra');
    item.appendChild(el('span', 'cfg-path', t(label)));
    item.appendChild(el('span', 'cfg-jsonval', value.text));
    profile.appendChild(item);
  });
  wrap.appendChild(profile);

  const claims = el('div');
  claims.appendChild(el('div', 'cfg-group-label', t(contract.labels.claims)));
  contract.emissions.forEach((claim) => {
    const row = el('div', 'cfg-row');
    if (claim.state.raw !== 'ready') row.dataset.tone = 'danger';
    const head = el('div', 'cfg-row-head');
    head.appendChild(el('span', 'cfg-subject', claim.predicate.text));
    head.appendChild(chip(claim.state.text, claim.state.raw === 'ready' ? 'ok' : 'danger'));
    head.appendChild(el('span', 'cfg-path', `${claim.subjects.text} → ${claim.objectKind.text}`));
    row.appendChild(head);

    const source = el('div', 'cfg-detail');
    source.appendChild(el('span', 'cfg-path', `${t(contract.labels.configuredBy)} `));
    source.appendChild(document.createTextNode(claim.configuredBy.text));
    row.appendChild(source);

    const signature = el('details', 'cfg-views');
    signature.appendChild(el('summary', null, t(contract.labels.signature)));
    signature.appendChild(el('pre', 'ls-atom', JSON.stringify(claim.vocabulary.raw, null, 2)));
    row.appendChild(signature);
    claim.issues.forEach((issue) => {
      const line = el('div', 'cfg-detail');
      line.dataset.tone = 'danger';
      line.appendChild(el('span', 'cfg-path', `${issue.code.text} `));
      if (issue.detail) line.appendChild(document.createTextNode(t(issue.detail)));
      row.appendChild(line);
    });
    claims.appendChild(row);
  });
  wrap.appendChild(claims);
  container.appendChild(wrap);
}

function renderSaveResult(container, view) {
  const box = el('div', 'cfg-dryrun');
  box.dataset.tone = 'ok';
  if (view.sentence) box.appendChild(el('div', 'cfg-detail', t(view.sentence)));
  const facts = el('div', 'retro-extras');
  view.facts.forEach((f) => {
    const item = el('span', 'retro-extra');
    item.appendChild(el('span', 'cfg-path', f.key));
    item.appendChild(el('span', 'cfg-jsonval', f.value.text));
    facts.appendChild(item);
  });
  if (view.facts.length) box.appendChild(facts);
  container.appendChild(box);

  // 「먹었는가」 — rendered by the ONE judge this system already has, not a second one.
  if (view.resolve && deps && deps.renderResolveInto) {
    const resolveBox = el('div', 'cfg-body');
    resolveBox.appendChild(el('div', 'cfg-group-label', t(view.resolveLabel)));
    deps.renderResolveInto(resolveBox, buildConfigResolveView(view.resolve));
    container.appendChild(resolveBox);
  }
}

/** Refusals: identical shape on all three writes, so one renderer.
 *
 * Every violation is listed here AND, when its `field` matches an input, repeated beside that
 * input. Both, deliberately: a message that only appears next to a scrolled-off input is a
 * message nobody read, and a list alone does not say where to type. */
function renderViolations(container, violationsBody, formEl) {
  const view = buildViolationsView(violationsBody);
  clearFieldViolations(formEl);
  const box = el('div', 'cfg-dryrun');
  box.dataset.tone = 'danger';
  const head = el('div', 'cfg-row-head');
  head.appendChild(el('span', 'cfg-group-label', t(view.label)));
  if (view.target) head.appendChild(chip(t(view.target), 'muted'));
  if (view.name) head.appendChild(el('span', 'cfg-subject', t(view.name)));
  box.appendChild(head);

  view.violations.forEach((v) => {
    const row = el('div', 'cfg-row');
    row.dataset.tone = 'danger';
    const line = el('div', 'cfg-row-head');
    if (v.code) line.appendChild(chip(t(v.code), 'danger'));
    if (v.field) line.appendChild(el('span', 'cfg-path', v.field));
    row.appendChild(line);
    // THE SERVER'S FULL KOREAN SENTENCE. Verbatim, always.
    if (v.detail) row.appendChild(el('div', 'cfg-detail', t(v.detail)));
    box.appendChild(row);

    const target = v.field ? findFieldNode(formEl, v.field) : null;
    if (target) {
      target.dataset.invalid = '1';
      target.appendChild(el('div', 'ls-violation cfg-detail', t(v.detail)));
    }
  });
  container.appendChild(box);
}

/** Drop the per-field marks from the PREVIOUS answer.
 *
 * Called before every write attempt, not only before a refusal. A reason that outlives the
 * declaration it was about is a screen saying something untrue: the operator changes the field,
 * the server accepts it, and the red sentence is still sitting under the input that fixed it. */
function clearFieldViolations(formEl) {
  if (!formEl) return;
  formEl.querySelectorAll('.ls-violation').forEach((node) => node.remove());
  formEl.querySelectorAll('[data-ls-field]').forEach((node) => { delete node.dataset.invalid; });
}

/** Which input a violation belongs to. Exact path first, then the nearest enclosing path
 *  (`columns.wafer` hangs off `columns.wafer`; `watermark` hangs off `watermark.columns`). */
function findFieldNode(formEl, field) {
  if (!formEl) return null;
  const escaped = field.replace(/["\\]/g, '\\$&');
  const exact = formEl.querySelector(`[data-ls-field="${escaped}"]`);
  if (exact) return exact;
  const nodes = Array.from(formEl.querySelectorAll('[data-ls-field]'));
  return nodes.find((node) => {
    const path = node.dataset.lsField;
    return path === field || path.startsWith(`${field}.`) || field.startsWith(`${path}.`);
  }) || null;
}

// ── transport ────────────────────────────────────────────────

/** GET + build, with the failure line the config report already owns.
 *
 * A 404 here means the running process predates these routes, and the sentence for that says
 * RESTART — which is a different hand than a refused connection or a rejected token. That split
 * lives in `fetchFailureLine`, and this reuses it rather than re-deriving it. */
async function getJson(path, build, key) {
  let failure = null;
  try {
    const res = await deps.adminFetch(`${deps.apiBase}${path}`);
    failure = deps.failureFactOf(res);
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    loadFailure[key] = null;
    return build(await res.json());
  } catch (e) {
    console.error('[LedgerSetup] fetch failed', path, failure, e);
    // STORED, not written to a node. The fetch happens before any editor is mounted, so a
    // failure written straight to the DOM would land nowhere and the editor would open later
    // as an empty picker with no reason on it — the silent screen this whole design is against.
    // The renderers read this the moment they have somewhere to put it.
    loadFailure[key] = fetchFailureLine(failure, CHROME.FETCH_FAILED);
    return null;
  }
}

/** POST. Returns `{body}` on success, `{violations}` on a 400 refusal, null when the request
 *  itself failed. The refusal body is NOT an error to be summarised — it is the answer. */
async function post(path, payload, fallback) {
  let failure = null;
  try {
    const res = await deps.adminFetch(`${deps.apiBase}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    failure = deps.failureFactOf(res);
    if (res.status === 400) {
      // The refusal arrives NESTED under `detail` (FastAPI wraps it). `hasViolations` owns that
      // unwrap so this call site cannot read the wrong path and render silence.
      const body = await res.json();
      if (hasViolations(body)) return { violations: body };
      throw new Error('400 without violations');
    }
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return { body: await res.json() };
  } catch (e) {
    console.error('[LedgerSetup] write failed', path, failure, e);
    showToast(fetchFailureLine(failure, fallback || LC.SAVE_FAILED), 'error');
    return null;
  }
}

// ── misc ─────────────────────────────────────────────────────

function debounce(fn, ms) {
  let handle = null;
  return (...args) => {
    if (handle) clearTimeout(handle);
    handle = setTimeout(() => fn(...args), ms);
  };
}
