// Harness - the enrichment reference panel on a PARTIAL decision key.
// Run: node client2/tests/enrichment_partial_key_reference_harness.mjs
//
// WHY THIS EXISTS [2026-08-05, product owner ruling: "when part of a decision key is
// blank, work with what remains"].
//   The server shipped its half: both writers resolve on whatever key columns survive,
//   `/enrichment/rules/{r}/references/{i}` SERVES the views that can still be asked, and
//   400s the ones that cannot with a sentence it composes itself. The client's half had
//   not shipped: `loadActiveReference` refused to fetch ANY view when ANY decision key
//   column was blank, so the unattended sweep could resolve a row that a human looking at
//   the same row could not see the evidence for. The human path was the closed one.
//
//   R1  THE CLIENT ASKS. No pre-decision about which views are answerable. That rule is
//       the server's and it already applies it; a second implementation here is the
//       two-spellings class, and the two drift while every server test stays green.
//   R2  THE WHOLE KEY IS SENT, BLANKS INCLUDED. Whether a blank value counts as "not
//       supplied" is the server's fold. Filtering here is that same second implementation
//       wearing a different hat.
//   R3  A PARTIALLY ANSWERABLE ROW IS THE NORMAL CASE. One view refuses, another answers,
//       on the SAME row. The row must not collapse into a single verdict.
//   R4  THE SENTENCE IS THE SERVER'S. The refusal text rendered is the server's `detail`,
//       verbatim; when the server says nothing the client says nothing rather than
//       inventing a reason. Same ruling `map2/verdict.js` was repaired under.
//   R5  ONE LINE ON SCREEN, THE WHOLE THING IN THE CONSOLE.
//   R6  A DETERMINISTIC REFUSAL IS CACHED PER (row, view); a transport failure is NOT.
//       "I could not ask just now" and "this view cannot be asked with this key" are
//       different facts, and caching the first one turns a blip into a permanent verdict.
//   R7  THE DETAIL PANEL STATES A FACT, NOT A VERDICT. It names which key columns are
//       blank. It no longer claims the row cannot be judged here, because that is now
//       false for a partial key.
//
// EVERY CHECK IS PAIRED WITH A MUTANT, and the suite FAILS if a defect still passes -
// a check that cannot fail proves nothing. Two CONTROLS must ESCAPE; if a control is
// caught, some check is reading source text instead of behaviour.
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
  return body.replace(/^export\s+/, '');
}

const SLICED = [
  'cellVal', 'hasDecisionKeys', 'renderDetail', 'loadActiveReference',
  'renderRefOutcome', 'renderRefTable', 'showRefStatus', 'hideRefStatus',
  'showRefIdle', 'showRefLoading', 'showRefError',
];

// ── Fixture: the live rule's shape - a TWO column decision key ──────────────────
// A one-column key cannot be partial, so scoring on one would measure nothing.
const RULE = {
  name: 'eqp_product_frame_attribution',
  decision_key: ['dt_eqp', 'product'],
  target_fields: ['core_frame'],
  list_columns: ['dt_job'],
};
const VIEWS = [{ label: '이 설비/제품의 DT job' }, { label: '표기 흔들림' }];

const row = (id, dtEqp, product) => ({
  row_id: id,
  data: {
    dt_eqp: { value: dtEqp, is_overwrite: false, priority_source: 'pipeline_parser' },
    product: { value: product, is_overwrite: false, priority_source: 'pipeline_parser' },
    dt_job: { value: 'J1', is_overwrite: false, priority_source: 'pipeline_parser' },
    core_frame: { value: null, is_overwrite: false, priority_source: null },
  },
});

// The sentence the live server composes. It is DATA here, never an expectation the client
// is asked to reproduce: every assertion below compares what was rendered against THIS
// string, so a client that writes its own wording fails no matter how plausible it reads.
const REFUSAL_ONE = "Reference query execution failed (missing required bind param(s): "
  + "['product']). Check required params.";
const REFUSAL_BOTH = "Reference query execution failed (missing required bind param(s): "
  + "['dt_eqp', 'product']). Check required params.";

// ── A document small enough to read, large enough to run the real renderers ─────
function mkEl(tag) {
  const e = {
    tagName: tag, id: '', textContent: '', className: '', title: '', type: '',
    placeholder: '', autocomplete: '', htmlFor: '', value: '',
    style: {}, dataset: {}, children: [], scrollTop: 0,
    appendChild(c) { e.children.push(c); return c; },
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    classList: { toggle() {}, add() {}, remove() {} },
  };
  Object.defineProperty(e, 'innerHTML', {
    get() { return ''; },
    set(v) { if (v === '') e.children.length = 0; },
  });
  return e;
}

function textOf(node, out = []) {
  if (node.textContent) out.push(node.textContent);
  node.children.forEach(c => textOf(c, out));
  return out;
}

// ── The scope: real function texts plus stubs for what they reach outside ───────
function build(src, routes) {
  const parts = SLICED.map(n => fn(src, n)).join('\n\n');

  const els = new Map();
  const el = (id) => {
    if (!els.has(id)) { const e = mkEl('div'); e.id = id; els.set(id, e); }
    return els.get(id);
  };
  const document = { createElement: (tag) => mkEl(tag) };

  const nodes = new Map();
  const S = {
    rule: RULE, sessionToken: 'tok', refViews: VIEWS, refActiveIdx: 0, refSeq: 0,
    refTimer: null, refCache: new Map(), refCacheRowId: null, selectedRowId: null,
    gridApi: { getRowNode: (id) => nodes.get(String(id)) || null },
  };

  const calls = [];
  const fetchStub = async (url) => {
    const m = /\/references\/(\d+)\?params=([^&]*)$/.exec(url);
    if (!m) die(`the request URL no longer matches the reference contract: ${url}`);
    const idx = Number(m[1]);
    const params = JSON.parse(decodeURIComponent(m[2]));
    calls.push({ idx, params });
    const route = routes[idx];
    if (!route) die(`fixture has no route for view ${idx}`);
    if (route.transport) throw new Error(route.transport);
    return { ok: route.status === 200, status: route.status, json: async () => route.body };
  };

  const logs = [];
  const consoleStub = { log: (...a) => logs.push(a), error: () => {}, warn: () => {} };

  // eslint-disable-next-line no-new-func
  const make = new Function(
    'el', 'S', 'document', 'fetch', 'API_BASE', 'performance', 'console',
    'onInputKeydown', 'scheduleReferenceLoad',
    `${parts}\nreturn {${SLICED.join(', ')}};`);
  const api = make(el, S, document, fetchStub, 'http://x', { now: () => 0 }, consoleStub,
    () => {}, () => {});

  const put = (r) => { nodes.set(String(r.row_id), { data: r }); return r; };
  return { api, S, el, els, calls, logs, put };
}

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

  // ---- R1/R2/R3/R4/R5: one row, one view refused BY THE SERVER, one answered -----
  {
    const answered = { status: 200, body: { label: 'B', columns: ['dt_job'], rows: [['J77']] } };
    const refused = { status: 400, body: { detail: REFUSAL_ONE } };
    let ctx;
    try { ctx = build(src, { 0: refused, 1: answered }); }
    catch (e) { return { pass, fail: fail + 1, failed: [`build threw: ${e && e.message}`] }; }
    const { api, S, el, calls, logs, put } = ctx;

    put(row(7, 'EQP1', ''));          // partial key: dt_eqp survives, product is blank
    S.selectedRowId = 7;
    S.refActiveIdx = 0;
    await api.loadActiveReference();

    check('R1 a partially blank key still asks', calls.length, 1);
    check('R2 the request carries every key column, blank included',
      calls[0].params, { dt_eqp: 'EQP1', product: '' });
    check('R4 the refusal renders the server sentence verbatim',
      el('reference-status-sub').textContent, REFUSAL_ONE);
    check('R4 the refusal is not dressed as an empty result',
      el('reference-table-wrap').style.display, 'none');
    check('R5 the headline is one line',
      el('reference-status-text').textContent.includes('\n'), false);
    check('R5 the rendered sentence is one line',
      el('reference-status-sub').textContent.includes('\n'), false);
    check('R5 the whole thing reached the console', logs.length, 1);
    check('R5 and it carries the server detail unabridged',
      logs[0][1] && logs[0][1].detail, REFUSAL_ONE);
    check('R5 and the status that produced it', logs[0][1] && logs[0][1].status, 400);

    // The SAME row, the OTHER view: this is the case the old code could not produce.
    S.refActiveIdx = 1;
    await api.loadActiveReference();
    check('R3 the other view is asked for the same row', calls.length, 2);
    check('R3 and it answers', el('reference-table-wrap').style.display, 'block');
    check('R3 the answer is rendered as evidence, not a status',
      el('reference-status').style.display, 'none');
    check('R3 the served rows are on screen',
      textOf(el('reference-table-wrap')).includes('J77'), true);
    check('R3 the meta counts what came back',
      el('reference-meta').textContent, '1건 · 0ms');

    // R6: revisiting the refused tab must not re-ask.
    S.refActiveIdx = 0;
    await api.loadActiveReference();
    check('R6 a deterministic refusal is remembered for this row', calls.length, 2);
    check('R6 and it still shows the server sentence',
      el('reference-status-sub').textContent, REFUSAL_ONE);
  }

  // ---- R1: a WHOLLY blank key is asked too (no client-side shortcut at all) ------
  {
    const ctx = build(src, { 0: { status: 400, body: { detail: REFUSAL_BOTH } } });
    const { api, S, el, calls, put } = ctx;
    put(row(9, '', '   '));
    S.selectedRowId = 9;
    await api.loadActiveReference();
    check('R1 a wholly blank key is asked, not pre-judged', calls.length, 1);
    check('R2 whitespace is forwarded as it stands',
      calls[0].params, { dt_eqp: '', product: '   ' });
    check('R4 and the server sentence is what appears',
      el('reference-status-sub').textContent, REFUSAL_BOTH);
  }

  // ---- R4: silence when the server named nothing --------------------------------
  {
    const ctx = build(src, { 0: { status: 400, body: {} } });
    const { api, S, el, put } = ctx;
    put(row(11, 'EQP1', ''));
    S.selectedRowId = 11;
    await api.loadActiveReference();
    check('R4 no detail from the server means no sentence invented here',
      el('reference-status-sub').textContent, '');
  }

  // ---- R6: a transport failure is NOT a verdict about this view -----------------
  {
    const ctx = build(src, { 0: { transport: 'ECONNREFUSED' } });
    const { api, S, calls, put } = ctx;
    put(row(13, 'EQP1', ''));
    S.selectedRowId = 13;
    await api.loadActiveReference();
    await api.loadActiveReference();
    check('R6 a transport failure is retried, never cached', calls.length, 2);
  }

  // ---- R7: the detail panel names the blank columns as a fact -------------------
  {
    const ctx = build(src, { 0: { status: 400, body: { detail: REFUSAL_ONE } } });
    const { api, S, el, put } = ctx;
    const partial = put(row(21, 'EQP1', ''));
    api.renderDetail(partial);
    const notices = el('decision-key-body').children
      .filter(c => c.className === 'blankkey-notice').map(c => c.textContent);
    check('R7 the blank key column is named', notices, ['판단키 공백: product']);
    check('R7 one line', notices.every(t => !t.includes('\n')), true);

    api.renderDetail(put(row(22, 'EQP1', 'P1')));
    const none = el('decision-key-body').children.filter(c => c.className === 'blankkey-notice');
    check('R7 a complete key gets no notice', none.length, 0);

    api.renderDetail(put(row(23, '', '')));
    const both = el('decision-key-body').children
      .filter(c => c.className === 'blankkey-notice').map(c => c.textContent);
    check('R7 a wholly blank key names both columns', both, ['판단키 공백: dt_eqp, product']);
  }

  // ---- The standing prohibition: server reason tokens are not client literals ----
  // Comments are stripped first: the module discusses the server's fold in prose on
  // purpose, and a duplication guard that cries wolf is one that gets deleted.
  {
    const code = src.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n');
    check('R4 no server reason token is written down as a client literal',
      ['missing_bind', 'no_decision_key'].filter(w => code.includes(w)), []);
  }

  return { pass, fail, failed };
}

// ── Defects that must be CAUGHT ─────────────────────────────────────────────────
const DEFECTS = [
  ['a pre-decision gate comes back (the whole round, undone)',
    s => s.replace('const view = S.refViews[idx];',
                   'const view = S.refViews[idx];\n  '
                   + 'if (!hasDecisionKeys(node.data, S.rule)) { showRefIdle(); return; }')],
  ['blank key values are filtered out of the request',
    s => s.replace('paramsObj[col] = cellVal(node.data, col);',
                   "const v = cellVal(node.data, col);\n    "
                   + "if (String(v).trim() !== '') paramsObj[col] = v;")],
  ['the client writes the refusal sentence itself',
    s => s.replace("showRefStatus('🚧', '조회 불가 참조뷰', detail || '');",
                   "showRefStatus('🚧', '조회 불가 참조뷰', "
                   + "'판단키가 비어 있어 조회할 수 없습니다.');")],
  ['a refusal is collapsed into "no evidence"',
    s => s.replace('showRefError(outcome.status, outcome.detail);',
                   "showRefStatus('🫙', '근거 데이터 없음', '');")],
  ['the refusal never reaches the console',
    s => s.replace("console.log('[enrichment] reference view refused', {",
                   "((x) => x)({")],
  ['a refusal is re-asked on every tab visit',
    s => s.replace('if (res.status === 400) S.refCache.set(idx, refusal);',
                   'if (res.status === 499) S.refCache.set(idx, refusal);')],
  ['a transport blip is cached as a verdict about the view',
    s => s.replace('renderRefOutcome({ refused: true, status: 0, detail: null });',
                   'S.refCache.set(idx, { refused: true, status: 0, detail: null });\n    '
                   + 'renderRefOutcome({ refused: true, status: 0, detail: null });')],
  ['the detail panel claims the row cannot be judged here',
    s => s.replace('warn.textContent = `판단키 공백:',
                   'warn.textContent = `판단키 없음, 여기서는 판단 불가:')],
  ['the notice fires on a complete key too',
    s => s.replace(".filter(col => String(cellVal(row, col)).trim() === '');",
                   ".filter(col => String(cellVal(row, col)).trim() !== undefined);")],
];

// ── Controls that must ESCAPE (else a check is reading source text) ─────────────
const CONTROLS = [
  ['local rename inside loadActiveReference',
    s => s.replace(/paramsObj/g, 'askWith')],
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
];

const base = await suite(PRISTINE);
if (base.fail) console.error(`\nbaseline failures:\n  ${base.failed.join('\n  ')}`);

quiet = true;
let caught = 0; const escaped = [];
for (const [name, mutate] of DEFECTS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) die(`defect "${name}" changed nothing - its anchor no longer matches. `
    + `An inert mutant is a check that cannot fail.`);
  let r;
  try { r = await suite(mutated); } catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) caught++; else escaped.push(name);
}
let controlsCaught = 0; const controlsCaughtNames = [];
for (const [name, mutate] of CONTROLS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) die(`control "${name}" changed nothing - it proves nothing.`);
  let r;
  try { r = await suite(mutated); } catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
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
