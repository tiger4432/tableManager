// Harness - the enrichment conveyor's TARGET FORM: what it shows, and what a save writes.
// Run: node client2/tests/enrichment_provenance_harness.mjs
//
// WHY THIS EXISTS [2026-08-05].
//   The queue predicate became OR-of-blank, so a row with ONE of its two targets filled now
//   stays in the queue - which was the point. But the conveyor handed the operator that row
//   with every box EMPTY, and `saveCurrent` demanded every box be non-empty. So the operator
//   retyped a value that was already there, and the retyped copy went out as `user`
//   (priority 0), overwriting the machine's decision with a hand-typed duplicate of itself.
//   A machine decision became a human declaration, at the highest priority, because a form
//   did not show what it already knew. Nobody intends that, and nothing on screen said it
//   happened.
//
//   P1  A FILLED TARGET RENDERS WITH ITS VALUE, AND SAYS WHOSE IT IS. Marked with the
//       `제안` shape the map screen already draws (dashed + muted): what is in this control
//       was not put there by you. Blankness folds the way the queue folds it (trim), so
//       stored whitespace is no value at all.
//   P2  THE MARK TRACKS THE TEXT, NOT THE PRESENCE OF A VALUE. It drops the instant the text
//       differs from the stored string and returns if that string is typed back - because
//       retyping a machine value character for character is not a decision, and the save
//       must not record one either.
//   P3  THE WRITE SET IS WHAT WAS EDITED, AND NOTHING ELSE. An untouched column is ABSENT
//       from the payload, so it keeps its value AND its provenance
//       (`enrichment_auto_confirm`, or whatever wrote it). Only an edited one becomes `user`.
//       This is the assertion the round exists for: what is NOT sent.
//   P4  A SAVE WITH NOTHING EDITED IS A REFUSAL, NOT A SILENT SUCCESS. No request, one line
//       on screen, whole record to the console. A button that reports success while writing
//       nothing teaches the operator that the button lies.
//   P5  EMPTYING A FILLED BOX IS REFUSED, NOT SENT. Writing '' as `user` would erase a
//       machine decision by hand and sign the empty space with a person's name.
//   P6  THE ROW LEAVES THE QUEUE ONLY WHEN EVERY TARGET IS FILLED. Filling one of two is now
//       reachable; removing the row for it would drop it off the screen while it is still in
//       the queue, and drift the remainder by one per save.
//   P7  NOTHING IS FABRICATED ON THE WAY BACK. The PUT does not return the stored row, so a
//       written cell's `priority_source` is null (unread) - never the OLD source, which
//       would attribute the new value to a writer that did not write it.
//   P8  OVERWRITING A MACHINE VALUE ON PURPOSE STILL WORKS, WITH NO EXTRA CONTROL. Editing
//       the field IS the act. What it must never be is an accident.
//
// `enrichment.js` is BUNDLER-BOUND (`ag-grid-community` plus two of its stylesheets), so it
// cannot be imported under bare node and its functions are sliced as text, the way the two
// sibling enrichment harnesses do it. What runs here is the real function bodies against a
// minimal document written in this file - no jsdom, no node_modules dependency.
//
// EVERY CHECK IS PAIRED WITH A MUTANT, and the suite FAILS if a defect still passes - a check
// that cannot fail proves nothing. Controls must ESCAPE; a caught control means some check is
// reading source text instead of behaviour.
//
// Exit codes: 0 = green | 1 = a check failed or a defect escaped | 2 = harness failure.
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'enrichment.js');

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

if (!existsSync(SRC_PATH)) die(`no source at ${SRC_PATH}`);
const PRISTINE = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

// ── Extraction: anchored at a real declaration, never at a bare name ─────────────
function sliceBalanced(src, startIdx, open, close) {
  const i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === open) depth++;
    else if (src[j] === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}
function fn(src, name) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in enrichment.js - renamed or reshaped.`);
  const body = sliceBalanced(src, m.index, '{', '}');
  if (!body) die(`unbalanced braces for ${name}`);
  return body;
}

// ── A document, written here rather than installed ──────────────────────────────
// Enough of one for the real `renderDetail` / `saveCurrent` bodies to run untouched:
// element creation, a child tree, id lookup, `dataset`, `style`, listeners and focus.
function makeDom() {
  const byId = new Map();
  let activeElement = null;

  const matches = (n, sel) => (sel.startsWith('.')
    ? String(n.className || '').split(/\s+/).includes(sel.slice(1))
    : n.tagName === sel.toUpperCase());
  const walk = (root, sel, out) => {
    (root.children || []).forEach(c => { if (matches(c, sel)) out.push(c); walk(c, sel, out); });
    return out;
  };

  function node(tag) {
    const n = {
      tagName: String(tag).toUpperCase(),
      className: '', textContent: '', value: '', type: '', placeholder: '',
      autocomplete: '', htmlFor: '', title: '',
      dataset: {}, style: {}, children: [], listeners: {},
      classList: {
        set: new Set(),
        add(c) { this.set.add(c); },
        remove(c) { this.set.delete(c); },
        toggle(c, on) { if (on === false) this.set.delete(c); else this.set.add(c); },
        contains(c) { return this.set.has(c); },
      },
      appendChild(c) { this.children.push(c); return c; },
      addEventListener(ev, f) { (this.listeners[ev] = this.listeners[ev] || []).push(f); },
      fire(ev, arg) { (this.listeners[ev] || []).forEach(f => f(arg)); },
      focus() { activeElement = this; },
      querySelectorAll(sel) { return walk(this, sel, []); },
      querySelector(sel) { return walk(this, sel, [])[0] || null; },
    };
    Object.defineProperty(n, 'id', {
      get() { return this._id || ''; },
      set(v) { this._id = v; byId.set(v, this); },
    });
    Object.defineProperty(n, 'innerHTML', {
      get() { return ''; },
      set(v) { if (v === '') this.children = []; },
    });
    return n;
  }

  const el = (id) => {
    if (!byId.has(id)) { const n = node('div'); n.id = id; }
    return byId.get(id);
  };
  return { el, document: { createElement: node }, active: () => activeElement };
}

// ── Fixtures: the live shape - TWO targets, one already decided by the sweep ─────
const RULE = {
  name: 'dt job attribution',
  derived_table: 'dt_job_attribution',
  decision_key: ['equipment', 'event_time'],
  target_fields: ['dt_lot_confirmed', 'dt_slot_confirmed'],
  list_columns: ['lot_id'],
  reference_views: [],
};
const cell = (value, source) => ({ value, is_overwrite: false, priority_source: source });
// A row the sweep half-answered: the lot is decided, the slot is not. Under OR-of-blank it
// stays in the queue, which is exactly the row that produced the defect.
const halfRow = () => ({
  row_id: 41,
  data: {
    equipment: cell('EQP1', 'pipeline_parser'),
    event_time: cell('2026-08-05 09:00', 'pipeline_parser'),
    lot_id: cell('LOT-9', 'pipeline_parser'),
    dt_lot_confirmed: cell('LOT-9', 'enrichment_auto_confirm'),
    dt_slot_confirmed: cell(null, null),
  },
});

const API = 'http://x';

function build(src) {
  const parts = ['cellVal', 'cellSource', 'hasDecisionKeys', 'isTargetUntouched',
    'markTargetInput', 'renderDetail', 'onInputKeydown', 'applyWrittenValues', 'saveCurrent']
    .map(n => fn(src, n)).join('\n\n');
  const dom = makeDom();

  const gridApi = {
    rows: [],
    updated: [],
    getRowNode(id) {
      const i = this.rows.findIndex(r => String(r.row_id) === String(id));
      return i < 0 ? null : { data: this.rows[i], rowIndex: i };
    },
    getDisplayedRowCount() { return this.rows.length; },
    applyTransaction(tx) {
      if (tx.remove) this.rows = this.rows.filter(d => !tx.remove.includes(d));
      if (tx.update) this.updated = this.updated.concat(tx.update);
      if (tx.add) this.rows = this.rows.concat(tx.add);
    },
  };
  const S = { rule: RULE, sessionToken: 'tok', gridApi, totalBlank: 9, totalAll: 20,
              blankKeyCount: 0, doneCount: 0, saving: false, selectedRowId: null,
              refViews: [] };

  const requests = [];
  let nextResponse = { ok: true, body: { status: 'success', effort_recorded: true } };
  const fetchStub = async (url, init) => {
    let payload = null;
    try { payload = init && init.body ? JSON.parse(init.body) : null; } catch (e) { payload = 'unparseable'; }
    requests.push({ url, method: init && init.method, payload });
    return { ok: nextResponse.ok, status: nextResponse.ok ? 200 : 500,
             json: async () => nextResponse.body };
  };
  const toasts = [];
  const logs = [];
  const stubs = `
function scheduleReferenceLoad() {}
function flashSaved() {}
function updateHeaderStats() {}
function updateWorklistOverlay() {}
function selectDisplayedIndex() {}
function refillIfNeeded() {}
function moveSelection() {}
`;
  // eslint-disable-next-line no-new-func
  const make = new Function('el', 'S', 'document', 'showToast', 'console', 'fetch',
    'API_BASE', 'CURRENT_USER', 'effortSnapshot', 'effortCommitIfRecorded',
    `${parts}\n${stubs}\nreturn {cellVal, cellSource, isTargetUntouched, markTargetInput, `
    + `renderDetail, onInputKeydown, applyWrittenValues, saveCurrent};`);
  const api = make(dom.el, S, dom.document,
    (text, kind) => toasts.push({ text, kind }),
    { log: (label, rec) => logs.push({ label, rec }) },
    fetchStub, API, 'tester',
    () => ({ k: 1, m: 0, n: 0 }), () => {});

  return { api, S, dom, gridApi, requests, toasts, logs,
           setResponse: (r) => { nextResponse = r; } };
}

// The boxes, in the order the rule declares its targets.
const boxes = (dom) => dom.el('target-inputs').querySelectorAll('input');
const mark = (dom, i) => dom.el(`target-existing-${i}`);
// Typing: the value changes and the element's own `input` listener runs, which is what the
// real page does. Nothing here calls `markTargetInput` directly.
const type = (input, text) => { input.value = text; input.fire('input'); };

// ── Scoring ─────────────────────────────────────────────────────────────────────
let quiet = false;
async function suite(src) {
  let pass = 0, fail = 0; const failed = [];
  const check = (name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { pass++; return; }
    fail++; failed.push(name);
    if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  };

  let ctx;
  try { ctx = build(src); } catch (e) { return { pass, fail: fail + 1, failed: [`build threw: ${e && e.message}`] }; }
  const { api, S, dom, gridApi, requests, toasts, logs, setResponse } = ctx;

  // One row on the belt, and the counters back to a known start - every case below reads
  // them as a DELTA of its own save, not of everything the suite did before it.
  const seat = (row) => {
    gridApi.rows = [row];
    gridApi.updated = [];
    S.totalBlank = 9; S.doneCount = 0;
    requests.length = 0; toasts.length = 0; logs.length = 0;
    api.renderDetail(row);
    return boxes(dom);
  };

  // ── P1 - what the form shows for an already-filled column ───────────────────
  let bx = seat(halfRow());
  check('P1 one box per target field', bx.length, 2);
  check('P1 the filled target carries its stored value', bx[0].value, 'LOT-9');
  check('P1 and is marked as an existing value', bx[0].dataset.existing, 'true');
  check('P1 and the mark names who decided it',
    mark(dom, 0).textContent, '기존값 · enrichment_auto_confirm');
  check('P1 and the mark is visible', mark(dom, 0).style.display, 'inline-flex');
  check('P1 a filled box needs no placeholder prompt', bx[0].placeholder, '');
  check('P1 the empty target stays empty', bx[1].value, '');
  check('P1 and is NOT marked as existing', bx[1].dataset.existing, 'false');
  check('P1 and its mark says nothing', mark(dom, 1).textContent, '');
  check('P1 and it still prompts', bx[1].placeholder, 'dt_slot_confirmed 입력 후 Enter');
  check('P1 focus lands on the first EMPTY box', dom.active() === bx[1], true);

  // Provenance the payload did not carry: named as existing, with nothing invented.
  const noSrc = halfRow();
  noSrc.data.dt_lot_confirmed = cell('LOT-9', null);
  bx = seat(noSrc);
  check('P1 an unattributed stored value is still shown', bx[0].value, 'LOT-9');
  check('P1 and marked, with no writer invented', mark(dom, 0).textContent, '기존값');

  // Stored whitespace is not a value - the queue folds it the same way.
  const wsRow = halfRow();
  wsRow.data.dt_lot_confirmed = cell('   ', 'enrichment_auto_confirm');
  bx = seat(wsRow);
  check('P1 stored whitespace is no value', [bx[0].value, bx[0].dataset.existing], ['', 'false']);

  // ── P2 - the mark tracks the text ───────────────────────────────────────────
  bx = seat(halfRow());
  type(bx[0], 'LOT-OTHER');
  check('P2 editing drops the mark', bx[0].dataset.existing, 'false');
  check('P2 and clears its text', mark(dom, 0).textContent, '');
  type(bx[0], 'LOT-9');
  check('P2 retyping the stored string is not an edit', bx[0].dataset.existing, 'true');
  type(bx[0], '  LOT-9  ');
  check('P2 and neither is retyping it with whitespace', bx[0].dataset.existing, 'true');

  // ── P3 - the write set is what was edited, and nothing else ─────────────────
  bx = seat(halfRow());
  type(bx[1], 'SLOT-3');
  await api.saveCurrent();
  check('P3 exactly one request goes out', requests.length, 1);
  check('P3 and it carries ONLY the edited column',
    Object.keys((requests[0].payload.updates[0] || {}).updates || {}), ['dt_slot_confirmed']);
  check('P3 the untouched column is absent from the payload',
    'dt_lot_confirmed' in (requests[0].payload.updates[0].updates || {}), false);
  check('P3 the edited column carries its value', requests[0].payload.updates[0].updates.dt_slot_confirmed, 'SLOT-3');
  check('P3 and it is the human source', requests[0].payload.updates[0].source_name, 'user');
  check('P3 the row_id is the selected one', requests[0].payload.updates[0].row_id, 41);
  check('P3 the record names what was withheld and under whose provenance',
    (logs.find(l => l.label === '[enrichment] saved') || {}).rec.withheld,
    { dt_lot_confirmed: { value: 'LOT-9', priority_source: 'enrichment_auto_confirm' } });

  // THE REPORTED FAILURE, ONE LINE: the operator retypes the value that is already there.
  bx = seat(halfRow());
  type(bx[0], 'LOT-9');        // a hand-typed duplicate of the machine's own decision
  type(bx[1], 'SLOT-3');
  await api.saveCurrent();
  check('P3 a hand-typed duplicate of a machine value is NOT written',
    Object.keys(requests[0].payload.updates[0].updates), ['dt_slot_confirmed']);

  // ── P4 - a save with nothing edited ─────────────────────────────────────────
  bx = seat(halfRow());
  await api.saveCurrent();
  check('P4 nothing edited issues NO request', requests.length, 0);
  check('P4 it refuses out loud', toasts.length, 1);
  check('P4 with a warning, not a success', (toasts[0] || {}).kind, 'warning');
  check('P4 on ONE line', ((toasts[0] || {}).text || '').includes('\n'), false);
  check('P4 and the whole record goes to the console',
    (logs[0] || {}).label, '[enrichment] save refused: nothing edited');
  check('P4 the row is not consumed', gridApi.rows.length, 1);
  check('P4 the remainder is untouched', S.totalBlank, 9);
  check('P4 and nothing is counted as done', S.doneCount, 0);

  // Every target already filled: the same refusal, not an all-fields rewrite.
  const fullRow = halfRow();
  fullRow.data.dt_slot_confirmed = cell('SLOT-1', 'enrichment_auto_confirm');
  bx = seat(fullRow);
  check('P4 a fully decided row shows both values', [bx[0].value, bx[1].value], ['LOT-9', 'SLOT-1']);
  await api.saveCurrent();
  check('P4 and saving it writes nothing at all', requests.length, 0);

  // ── P5 - emptying a filled box ──────────────────────────────────────────────
  bx = seat(halfRow());
  type(bx[0], '');
  await api.saveCurrent();
  check('P5 an emptied target is not sent as an erasure', requests.length, 0);
  check('P5 it refuses out loud', (toasts[0] || {}).kind, 'warning');
  check('P5 and records which column', (logs[0] || {}).rec.field, 'dt_lot_confirmed');
  check('P5 the row stays', gridApi.rows.length, 1);

  // ── P6/P7 - the row leaves only when every target is filled ─────────────────
  bx = seat(halfRow());
  type(bx[1], 'SLOT-3');
  await api.saveCurrent();
  check('P6 the last blank filled retires the row', gridApi.rows.length, 0);
  check('P6 and the remainder falls by one', S.totalBlank, 8);
  check('P6 and the session count rises by one', S.doneCount, 1);

  bx = seat(halfRow());
  type(bx[0], 'LOT-REVISED');   // an overwrite, and the slot is left empty
  await api.saveCurrent();
  check('P8 a deliberate overwrite is written', requests[0].payload.updates[0].updates,
    { dt_lot_confirmed: 'LOT-REVISED' });
  check('P6 a row with a target still blank STAYS in the buffer', gridApi.rows.length, 1);
  check('P6 and the remainder does not move', S.totalBlank, 9);
  check('P6 and nothing is counted as done', S.doneCount, 0);
  check('P6 the buffer row is updated in place', gridApi.updated.length, 1);
  check('P7 the written value lands on the row',
    gridApi.rows[0].data.dt_lot_confirmed.value, 'LOT-REVISED');
  check('P7 and the old writer is NOT credited with it',
    gridApi.rows[0].data.dt_lot_confirmed.priority_source, null);
  bx = boxes(dom);
  check('P7 the form redraws it as an existing value',
    [bx[0].value, bx[0].dataset.existing], ['LOT-REVISED', 'true']);
  check('P7 with no writer invented for it', mark(dom, 0).textContent, '기존값');
  check('P7 and focus returns to the box still empty', dom.active() === bx[1], true);

  // ── Escape restores what is stored ──────────────────────────────────────────
  bx = seat(halfRow());
  type(bx[0], 'TYPO');
  api.onInputKeydown({ key: 'Escape', preventDefault() {} });
  check('Esc restores the stored value', bx[0].value, 'LOT-9');
  check('Esc restores the mark with it', bx[0].dataset.existing, 'true');
  check('Esc leaves the empty box empty', bx[1].value, '');

  // A failed write must consume nothing and keep the typing.
  bx = seat(halfRow());
  setResponse({ ok: false, body: { detail: 'boom' } });
  type(bx[1], 'SLOT-3');
  await api.saveCurrent();
  check('a failed save keeps the row', gridApi.rows.length, 1);
  check('and keeps the typed value', boxes(dom)[1].value, 'SLOT-3');
  check('and the remainder does not move', S.totalBlank, 9);
  setResponse({ ok: true, body: { status: 'success', effort_recorded: true } });

  return { pass, fail, failed };
}

// ── Defects that must be CAUGHT ─────────────────────────────────────────────────
const DEFECTS = [
  ['the form hands over an empty box for a decided column',
    s => s.replace('    input.value = stored;\n', "    input.value = '';\n")],
  ['no baseline is recorded (every prefilled box reads as an edit)',
    s => s.replace('input.dataset.baseline = stored;', "input.dataset.baseline = '';")],
  ['THE UNTOUCHED COLUMN IS SENT ANYWAY (its provenance is rewritten as user)',
    s => s.replace('    if (val === baseline) {\n', '    if (false) {\n')],
  ['the mark reads presence of a value instead of equality with the baseline',
    s => s.replace("return baseline !== '' && input.value.trim() === baseline;",
                   "return input.value.trim() !== '';")],
  ['the mark never drops (an edited box still claims to be the stored value)',
    s => s.replace("return baseline !== '' && input.value.trim() === baseline;",
                   "return baseline !== '';")],
  ['the baseline keeps stored whitespace (a blank column looks decided)',
    s => s.replace('const stored = String(cellVal(row, field)).trim();',
                   'const stored = String(cellVal(row, field));')],
  ['a writer is invented for an unattributed value',
    s => s.replace("mark.textContent = untouched ? (src ? `기존값 · ${src}` : '기존값') : '';",
                   "mark.textContent = untouched ? `기존값 · ${src}` : '';")],
  ['focus parks on a filled box (overwriting becomes the default gesture)',
    s => s.replace("const first = inputs.find(i => i.value.trim() === '') || inputs[0];\n  if (first) first.focus();\n\n  // [C] 참조뷰",
                   'const first = inputs[0];\n  if (first) first.focus();\n\n  // [C] 참조뷰')],
  ['an empty save is sent anyway (a write of nothing, reported as success)',
    s => s.replace('  if (Object.keys(updates).length === 0) {', '  if (false) {')],
  ['an emptied target is sent as a user-signed erasure',
    s => s.replace("      input.focus();\n      return;\n    }\n    updates[field] = val;",
                   '      input.focus();\n    }\n    updates[field] = val;')],
  ['the row is retired no matter what is still blank',
    s => s.replace("const stillBlank = (S.rule.target_fields || []).some(f => (after[f] || '') === '');",
                   'const stillBlank = false;')],
  ['a partial save still decrements the remainder',
    s => s.replace('      S.doneCount += 1;\n    }',
                   '    }\n    S.totalBlank = Math.max(0, S.totalBlank - 1);\n    S.doneCount += 1;')],
  ['the old writer is credited with the newly written value',
    s => s.replace("? { ...cell, value: written[col], priority_source: null }",
                   '? { ...cell, value: written[col] }')],
  ['Escape blanks the form instead of restoring what is stored',
    s => s.replace("inputs.forEach(i => { i.value = i.dataset.baseline || ''; markTargetInput(i); });",
                   "inputs.forEach(i => { i.value = ''; markTargetInput(i); });")],
  ['a failed save consumes the row anyway',
    s => s.replace('    if (!res.ok) {\n      const errData = await res.json().catch(() => ({}));\n      throw new Error(errData.detail || `HTTP ${res.status}`);\n    }\n',
                   '')],
];

// ── Controls that must ESCAPE (else a check is reading source text) ─────────────
const CONTROLS = [
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
  ['the refusal wording is reworded',
    s => s.replace('바뀐 값이 없습니다. 고칠 칸을 수정한 뒤 저장해 주세요.', '수정된 칸이 없습니다.')],
  ['the post-save state variable is renamed',
    s => s.replace('  const after = {};', '  const post = {};')
          .replace('    after[field] = val;', '    post[field] = val;')
          .replace("(after[f] || '')", "(post[f] || '')")],
];

const base = await suite(PRISTINE);
if (base.fail) console.error(`\nbaseline failures:\n  ${base.failed.join('\n  ')}`);

quiet = true;
let caught = 0; const escaped = [];
for (const [name, mutate] of DEFECTS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) {
    die(`defect "${name}" changed nothing - its anchor no longer matches. An inert mutant is `
      + `a check that cannot fail.`);
  }
  let r;
  try { r = await suite(mutated); } catch (err) { r = { fail: 1, failed: [`threw: ${err && err.message}`] }; }
  if (r.fail > 0) caught++; else escaped.push(name);
}
let controlsCaught = 0; const controlsCaughtNames = [];
for (const [name, mutate] of CONTROLS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) die(`control "${name}" changed nothing - it proves nothing.`);
  let r;
  try { r = await suite(mutated); } catch (err) { r = { fail: 1, failed: [`threw: ${err && err.message}`] }; }
  if (r.fail > 0) { controlsCaught++; controlsCaughtNames.push(`${name} (${r.failed[0]})`); }
}
quiet = false;

if (escaped.length) console.error(`\ndefects that escaped:\n  ${escaped.join('\n  ')}`);
if (controlsCaughtNames.length) {
  console.error(`\ncontrols that were caught (a check is reading source text):\n  `
    + controlsCaughtNames.join('\n  '));
}

const bad = base.fail + escaped.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} `
  + `controls escaped.`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
