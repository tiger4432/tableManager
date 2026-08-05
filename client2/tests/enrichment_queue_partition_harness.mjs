// Harness - the enrichment conveyor's queue REQUEST, its arithmetic and its ordering rule.
// Run: node client2/tests/enrichment_queue_partition_harness.mjs
//
// WHY THIS EXISTS [N36, 2026-08-04].
//   `queue_filters` stopped demanding a non-blank decision key, so the progress bar's
//   numerator and denominator finally count ONE population (rows whose targets are
//   blank). The server half of that is scored by `server/tests/test_enrichment.py`.
//   What lands ONLY on the client is the consequence: blank-key rows now appear in
//   the worklist, they cannot be judged there, and the conveyor is consumed
//   front-first in row_id order - so without an ordering rule they sit at the head
//   and are hit over and over.
//
// AND WHAT THE 2026-08-05 RULING ADDED. `queue_filters` shipped the queue as a filter
//   dict, one `blank` spec per target, and every consumer ANDs those specs - so on a
//   rule with TWO targets the queue meant EVERY target blank, and filling one column
//   dropped the row while its sibling was still empty. Both live rules declare two
//   targets. The queue is now a NAMED server-side predicate (OR-of-blank across the
//   rule's own `target_fields`) that the client asks for rather than reconstructs.
//
//   P1  A ROW WITHOUT ITS KEYS IS DEMOTED, NEVER DROPPED. `partitionQueueRows` puts
//       every keyed row ahead of every keyless one. Dropping them would be the defect
//       the user overruled; leaving them in place would wedge the conveyor.
//   P2  ROW_ID ORDER SURVIVES INSIDE EACH PARTITION. The conveyor's invariant is
//       "consume from the front"; this changes WHICH rows are at the front, not that
//       the server's order governs.
//   P3  BLANKNESS IS THE SHARED SPELLING. Every decision key must be non-blank, and
//       blank means null / undefined / '' / whitespace - the same fold the server's
//       `clean_str_value` applies. `.some` instead of `.every`, or a missing trim, and
//       a half-keyed row is treated as workable.
//   P4  "판단키 없음 N건" IS READ, NOT COMPUTED. It is the server's own `blank_key`
//       total, verbatim. It used to be remainder minus a keyed total - a difference of
//       two numbers that existed only because the filter DSL could not express a
//       cross-column OR, and that under ANY-blank would subtract two DIFFERENT
//       populations. When the server cannot be asked (an older build), the honest
//       answer is to say nothing - NOT to render "0건", which is a claim.
//   P5  THE PROGRESS LABEL SAYS WHAT THE VALUE IS. Both sides are row counts, so the
//       unit is rows. "keys" was true only while `composite_key_source == decision_key`
//       on every live rule, which the loader does not require.
//   P6  THE QUEUE IS ASKED FOR BY NAME, IN ONE SPELLING. `enrichment_queue.js` composes
//       `?enrichment_queue=<rule>[&enrichment_queue_scope=...]`; the absence of
//       `queue_predicate` is the ONLY old-server signal, and a scope that server does
//       not publish is UNANSWERABLE rather than silently widened to the plain queue.
//   P7  THE CALL SITES SEND IT. The worklist and the blank-key count go through P6, and
//       a queue that cannot be composed produces NO request - dropping the condition
//       would return the whole table under the queue's name.
//
// NOT SCORED HERE, and deliberately: `ui.js updateEnrichmentBadge` and
//   `admin.js fetchEnrichmentStatus`, the other two call sites. Both are unavoidably
//   bound to the bundler and the DOM singletons (`ui.js` -> `grid.js` -> ag-grid +
//   its CSS; `admin.js` -> `./tokens.css`), so neither can be imported under bare
//   node. What IS scored is that all three now share ONE composer, which is the half
//   that could drift.
//
// EVERY CHECK IS PAIRED WITH A MUTANT, and the suite FAILS if a defect still passes -
// a check that cannot fail proves nothing. Controls must ESCAPE; if a control is
// caught, some check is reading source text instead of behaviour.
//
// Exit codes: 0 = green | 1 = a check failed or a defect escaped | 2 = harness failure.
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as SHIPPED from '../src/enrichment_queue.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'enrichment.js');
const QUEUE_PATH = join(HERE, '..', 'src', 'enrichment_queue.js');

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

if (!existsSync(SRC_PATH)) die(`no source at ${SRC_PATH}`);
if (!existsSync(QUEUE_PATH)) die(`no source at ${QUEUE_PATH}`);
const PRISTINE = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');
const QUEUE_PRISTINE = readFileSync(QUEUE_PATH, 'utf8').replace(/\r\n/g, '\n');

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
  return src.slice(m.index, m.index + (m[0].startsWith('export') ? 0 : 0)) + body;
}

// `enrichment_queue.js` is DOM-free and dependency-free by design, so it needs no
// slicing: the whole module runs once its `export` keywords are dropped. That is why
// mutating it is honest - what runs here is the file, not a chosen fragment of it.
const QUEUE_EXPORTS = ['queueQuery', 'hasQueuePredicate', 'QUEUE_SCOPE_QUEUE',
  'QUEUE_SCOPE_KEYED', 'QUEUE_SCOPE_BLANK_KEY', 'QUEUE_SCOPE_RESOLVED'];
function buildQueueModule(src) {
  const body = src.replace(/^export\s+/gm, '');
  // eslint-disable-next-line no-new-func
  return new Function(`${body}\nreturn {${QUEUE_EXPORTS.join(', ')}};`)();
}

// ── Fixtures. The live shape: TWO target fields, which is what made the old
//    conjunctive spelling wrong in production rather than in principle. ──────────
const PREDICATE = {
  param: 'enrichment_queue',
  value: 'dt job attribution',           // a space, so encoding is scored not assumed
  scope_param: 'enrichment_queue_scope',
  scopes: ['queue', 'keyed', 'blank_key', 'resolved'],
};
const LEGACY_FILTERS = {
  dt_lot_confirmed: { type: 'blank' },
  dt_slot_confirmed: { type: 'blank' },
};
const RULE = {
  name: 'dt job attribution',
  derived_table: 'dt_job_attribution',
  decision_key: ['equipment', 'event_time'],
  target_fields: ['dt_lot_confirmed', 'dt_slot_confirmed'],
  queue_filters: LEGACY_FILTERS,
  queue_predicate: PREDICATE,
};
// An older server: no `queue_predicate` at all. Its absence IS the version signal.
const OLD_RULE = { ...RULE, queue_predicate: undefined };
// Older still: it does not even compose `queue_filters`.
const ANCIENT_RULE = { ...OLD_RULE, queue_filters: undefined };
// No targets and no predicate: there is no condition to send, and an unconditioned
// request is the whole table.
const NO_TARGET_RULE = { ...ANCIENT_RULE, target_fields: [] };
// A server that publishes the predicate but not the blank_key scope.
const NARROW_RULE = {
  ...RULE,
  queue_predicate: { ...PREDICATE, scopes: ['queue'] },
};

const row = (id, equipment, event_time) => ({
  row_id: id,
  data: {
    equipment: { value: equipment, is_overwrite: false, priority_source: 'pipeline_parser' },
    event_time: { value: event_time, is_overwrite: false, priority_source: 'pipeline_parser' },
    dt_lot_confirmed: { value: null, is_overwrite: false, priority_source: null },
  },
});

const PAGE_LIMIT = 200;
const API = 'http://x';

// Build a live scope out of the real function texts plus the minimum stubs they
// touch. Nothing here re-implements the logic under test.
function build(src, Q) {
  const parts = ['cellVal', 'hasDecisionKeys', 'partitionQueueRows', 'updateHeaderStats',
    'fetchWorklist', 'fetchBlankKeyTotal'].map(n => fn(src, n)).join('\n\n');
  const els = new Map();
  const el = (id) => {
    if (!els.has(id)) els.set(id, { id, textContent: '', title: '', style: {},
      classList: { toggle() {}, add() {}, remove() {} } });
    return els.get(id);
  };
  const gridApi = {
    rows: [],
    setGridOption(k, v) { if (k === 'rowData') this.rows = v.slice(); },
    getDisplayedRowCount() { return this.rows.length; },
    forEachNode(cb) { this.rows.forEach(d => cb({ data: d })); },
    applyTransaction(tx) { if (tx.add) this.rows = this.rows.concat(tx.add); },
  };
  const S = { rule: RULE, sessionToken: 'tok', gridApi, totalBlank: 0, totalAll: null,
              blankKeyCount: null, doneCount: 0, isFetching: false, exhausted: false };
  const calls = [];
  let queued = [];
  const fetchStub = async (url) => {
    calls.push(url);
    const next = queued.shift();
    if (!next) return { ok: false, status: 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => next };
  };
  const respond = (...rs) => { queued = rs; };
  const stubs = `
function updateWorklistOverlay() {}
function selectDisplayedIndex() {}
function blankKeyBoundaryIndex() { return S.gridApi.getDisplayedRowCount(); }
`;
  // eslint-disable-next-line no-new-func
  const make = new Function('el', 'S', 'queueQuery', 'QUEUE_SCOPE_BLANK_KEY', 'API_BASE',
    'pageLimit', 'fetch', 'showToast', 'console',
    `${parts}\n${stubs}\nreturn {cellVal, hasDecisionKeys, partitionQueueRows, `
    + `updateHeaderStats, fetchWorklist, fetchBlankKeyTotal};`);
  const api = make(el, S, Q.queueQuery, Q.QUEUE_SCOPE_BLANK_KEY, API, PAGE_LIMIT,
    fetchStub, () => {}, { log() {} });
  return { api, S, el, calls, respond };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let quiet = false;
async function suite(src, queueSrc) {
  let pass = 0, fail = 0; const failed = [];
  const check = (name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { pass++; return; }
    fail++; failed.push(name);
    if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  };

  let Q, ctx;
  try { Q = buildQueueModule(queueSrc); }
  catch (e) { return { pass, fail: fail + 1, failed: [`queue module threw: ${e && e.message}`] }; }
  try { ctx = build(src, Q); }
  catch (e) { return { pass, fail: fail + 1, failed: [`build threw: ${e && e.message}`] }; }
  const { api, S, el, calls, respond } = ctx;

  // P1/P2 - demotion, and row_id order preserved inside each partition.
  const mixed = [row(1, '', 'T1'), row(2, 'EQP1', 'T2'), row(3, '', ''), row(4, 'EQP2', 'T4')];
  check('P1 keyed rows lead',
    api.partitionQueueRows(mixed, RULE).map(r => r.row_id), [2, 4, 1, 3]);
  check('P1 nothing is dropped', api.partitionQueueRows(mixed, RULE).length, 4);
  const allKeyed = [row(7, 'A', 'T'), row(8, 'B', 'T'), row(9, 'C', 'T')];
  check('P2 an all-keyed page is returned untouched',
    api.partitionQueueRows(allKeyed, RULE).map(r => r.row_id), [7, 8, 9]);
  check('P2 an all-keyless page keeps row_id order',
    api.partitionQueueRows([row(5, '', ''), row(6, '', '')], RULE).map(r => r.row_id), [5, 6]);

  // P3 - the shared blankness spelling.
  check('P3 both keys present', api.hasDecisionKeys(row(1, 'EQP1', 'T1'), RULE), true);
  check('P3 one key missing is NOT keyed', api.hasDecisionKeys(row(1, 'EQP1', ''), RULE), false);
  check('P3 whitespace is blank', api.hasDecisionKeys(row(1, 'EQP1', '   '), RULE), false);
  check('P3 null is blank', api.hasDecisionKeys(row(1, null, 'T1'), RULE), false);
  check('P3 undefined is blank', api.hasDecisionKeys(row(1, undefined, 'T1'), RULE), false);

  // ── P6 - the request itself. One spelling, one version signal. ───────────────
  const NAMED = 'enrichment_queue=dt%20job%20attribution';
  check('P6 a new server is asked by name',
    Q.queueQuery(RULE), `${NAMED}&enrichment_queue_scope=queue`);
  check('P6 the blank-key scope rides the same request',
    Q.queueQuery(RULE, 'blank_key'), `${NAMED}&enrichment_queue_scope=blank_key`);
  check('P6 the rule name is encoded', Q.queueQuery(RULE).includes('dt job'), false);
  check('P6 a new server is never asked with a filter dict',
    Q.queueQuery(RULE).includes('filters='), false);
  check('P6 hasQueuePredicate is the version signal',
    [Q.hasQueuePredicate(RULE), Q.hasQueuePredicate(OLD_RULE)], [true, false]);
  check('P6 an old server falls back to its own queue_filters',
    Q.queueQuery(OLD_RULE),
    `filters=${encodeURIComponent(JSON.stringify(LEGACY_FILTERS))}`);
  check('P6 an old server cannot be asked for a scope', Q.queueQuery(OLD_RULE, 'blank_key'), null);
  check('P6 an older server still gets the shape composed from its targets',
    Q.queueQuery(ANCIENT_RULE),
    `filters=${encodeURIComponent(JSON.stringify(LEGACY_FILTERS))}`);
  check('P6 no targets and no filters is unanswerable, not unconditioned',
    Q.queueQuery(NO_TARGET_RULE), null);
  check('P6 an unpublished scope is unanswerable, not widened',
    Q.queueQuery(NARROW_RULE, 'blank_key'), null);
  check('P6 and the plain queue still works on that same server',
    Q.queueQuery(NARROW_RULE), `${NAMED}&enrichment_queue_scope=queue`);

  // ── P7 - the call sites send it. ────────────────────────────────────────────
  calls.length = 0;
  S.rule = RULE; S.blankKeyCount = null;
  respond({ total: 12, data: [row(1, 'A', 'T'), row(2, '', 'T')] });
  await api.fetchWorklist(true);
  check('P7 the worklist issues exactly one request', calls.length, 1);
  check('P7 and asks for the queue by name', (calls[0] || '').includes(NAMED), true);
  check('P7 and never as a filter dict', (calls[0] || '').includes('filters='), false);
  check('P7 and keeps the conveyor order', (calls[0] || '').includes('order_by=row_id'), true);
  check('P7 the remainder is the server total', S.totalBlank, 12);

  calls.length = 0;
  S.rule = NO_TARGET_RULE; S.isFetching = false;
  await api.fetchWorklist(true);
  check('P7 an uncomposable queue asks for NOTHING', calls.length, 0);
  check('P7 and says so on one line', el('worklist-meta').textContent, '큐 조건 없음');

  // ── P4 - the named aggregate is READ from the server, never computed. ───────
  calls.length = 0;
  S.rule = RULE; S.totalBlank = 7; S.blankKeyCount = null;
  respond({ total: 3 });
  await api.fetchBlankKeyTotal();
  check('P4 it asks for the blank_key scope',
    (calls[0] || '').includes('enrichment_queue_scope=blank_key'), true);
  check('P4 it reads only a total', (calls[0] || '').includes('limit=1'), true);
  // 7 - 3 = 4. If the subtraction came back, this reads 4.
  check('P4 the count is the server number verbatim', S.blankKeyCount, 3);
  S.totalAll = 10;
  api.updateHeaderStats();
  check('P4 the badge names it', el('blankkey-badge').textContent, '⚠️ 판단키 없음 3건');
  check('P4 the badge is shown', el('blankkey-badge').style.display, 'inline-block');
  S.blankKeyCount = 0;
  api.updateHeaderStats();
  check('P4 zero blank-key rows hides the badge', el('blankkey-badge').style.display, 'none');

  calls.length = 0;
  S.rule = OLD_RULE; S.blankKeyCount = 5;
  await api.fetchBlankKeyTotal();
  check('P4 an old server is not asked at all', calls.length, 0);
  check('P4 an unanswerable count claims nothing', S.blankKeyCount, null);
  el('blankkey-badge').textContent = '';
  api.updateHeaderStats();
  check('P4 and renders no badge', el('blankkey-badge').style.display, 'none');
  check('P4 and writes no number', el('blankkey-badge').textContent, '');

  // P5 - the label states the unit the value actually carries.
  S.rule = RULE; S.totalAll = 10; S.totalBlank = 4; S.blankKeyCount = 0;
  api.updateHeaderStats();
  check('P5 progress is counted in rows', el('progress-text').textContent, '6 / 10 행');
  check('P5 percentage tracks the same two numbers', el('progress-percent').textContent, '60%');
  // The N36 shape itself: every row unanswered must read 0%, not 100%.
  S.totalAll = 2; S.totalBlank = 2; S.blankKeyCount = 2;
  api.updateHeaderStats();
  check('P5 [N36] all-unanswered reads 0%', el('progress-percent').textContent, '0%');
  check('P5 [N36] and every one of them is named',
    el('blankkey-badge').textContent, '⚠️ 판단키 없음 2건');

  return { pass, fail, failed };
}

// ── Defects that must be CAUGHT ─────────────────────────────────────────────────
// `where` names which file the mutation lands in - the queue composer is a second
// target because it is where the request's meaning now lives.
const DEFECTS = [
  ['enrichment', 'no demotion (blank-key rows wedge the conveyor head)',
    s => s.replace('rows.forEach(r => (hasDecisionKeys(r, rule) ? keyed : keyless).push(r));\n  return keyed.concat(keyless);',
                   'rows.forEach(r => keyed.push(r));\n  return keyed.concat(keyless);')],
  ['enrichment', 'partition reverses row_id order inside a partition',
    s => s.replace('return keyed.concat(keyless);', 'return keyed.reverse().concat(keyless);')],
  ['enrichment', 'ANY key non-blank counts as keyed (.some for .every)',
    s => s.replace('(rule.decision_key || []).every(col =>', '(rule.decision_key || []).some(col =>')],
  ['enrichment', 'whitespace key counts as keyed (no trim)',
    s => s.replace("String(cellVal(row, col)).trim() !== ''", "String(cellVal(row, col)) !== ''")],
  ['enrichment', 'the worklist goes back to shipping a filter dict',
    s => s.replace('`?skip=0&limit=${pageLimit}&order_by=row_id&order_desc=false&${queue}`',
                   '`?skip=0&limit=${pageLimit}&order_by=row_id&order_desc=false'
                   + '&filters=${encodeURIComponent(JSON.stringify(S.rule.queue_filters))}`')],
  ['enrichment', 'an uncomposable queue is asked anyway (whole table under the queue name)',
    s => s.replace('const queue = queueQuery(S.rule);\n  if (!queue) {',
                   "const queue = queueQuery(S.rule) || '';\n  if (false) {")],
  ['enrichment', 'THE SUBTRACTION COMES BACK (remainder minus the server total)',
    s => s.replace('S.blankKeyCount = result.total;',
                   'S.blankKeyCount = Math.max(0, S.totalBlank - result.total);')],
  ['enrichment', 'the blank-key count asks the plain queue instead of its scope',
    s => s.replace('queueQuery(S.rule, QUEUE_SCOPE_BLANK_KEY)', 'queueQuery(S.rule)')],
  ['enrichment', 'an unanswerable blank-key count is claimed as zero',
    s => s.replace('    S.blankKeyCount = null;\n', '    S.blankKeyCount = 0;\n')],
  ['enrichment', 'an unknown count is rendered anyway',
    s => s.replace('if (known) bkBadge.textContent =', 'bkBadge.textContent =')],
  ['enrichment', 'progress label claims keys again',
    s => s.replace('${S.totalAll.toLocaleString()} 행', '${S.totalAll.toLocaleString()} keys')],
  ['enrichment', 'blank-key badge shown even at zero',
    s => s.replace("bkBadge.style.display = (known && S.blankKeyCount > 0) ? 'inline-block' : 'none';",
                   "bkBadge.style.display = 'inline-block';")],
  ['queue', 'the scope is dropped from the request',
    s => s.replace('    if (!scopable) return base;\n    return `${base}&${encodeURIComponent(p.scope_param)}=${encodeURIComponent(scope)}`;',
                   '    return base;')],
  ['queue', 'an unpublished scope silently widens to the plain queue',
    s => s.replace("if (!scopable && scope !== QUEUE_SCOPE_QUEUE) return null;",
                   'if (false) return null;')],
  ['queue', 'the rule name is not encoded',
    s => s.replace('${encodeURIComponent(p.param)}=${encodeURIComponent(p.value)}',
                   '${encodeURIComponent(p.param)}=${p.value}')],
  ['queue', 'queue_filters wins over the named predicate',
    s => s.replace('if (hasQueuePredicate(rule)) {',
                   'if (hasQueuePredicate(rule) && !rule.queue_filters) {')],
  ['queue', 'a rule with no targets yields an unconditioned request',
    s => s.replace('if (targets.length === 0) return null;', 'if (false) return null;')],
];

// ── Controls that must ESCAPE (else a check is reading source text) ─────────────
const CONTROLS = [
  ['enrichment', 'local rename inside partitionQueueRows',
    s => s.replace('const keyed = [], keyless = [];', 'const aa = [], bb = [];')
          .replace('rows.forEach(r => (hasDecisionKeys(r, rule) ? keyed : keyless).push(r));',
                   'rows.forEach(r => (hasDecisionKeys(r, rule) ? aa : bb).push(r));')
          .replace('return keyed.concat(keyless);', 'return aa.concat(bb);')],
  ['enrichment', 'comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
  ['queue', 'comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
];

// ── The extraction must be the thing that ships ─────────────────────────────────
// `enrichment_queue.js` is mutated as TEXT, so what is scored is only as honest as
// the claim that the text and the module agree. Checked once, outside the mutation
// loop: inside it, every queue mutant would "fail" this and be counted as caught for
// the wrong reason.
{
  const evaluated = buildQueueModule(QUEUE_PRISTINE);
  const probes = [[RULE], [RULE, 'blank_key'], [OLD_RULE], [OLD_RULE, 'blank_key'],
                  [ANCIENT_RULE], [NO_TARGET_RULE], [NARROW_RULE, 'blank_key']];
  for (const args of probes) {
    const a = evaluated.queueQuery(...args);
    const b = SHIPPED.queueQuery(...args);
    if (a !== b) die(`the evaluated copy of enrichment_queue.js disagrees with the imported `
      + `module (${JSON.stringify(args[1] || 'queue')}): ${a} vs ${b}. Mutating text that is `
      + `not what runs proves nothing.`);
  }
  if (SHIPPED.QUEUE_SCOPE_BLANK_KEY !== 'blank_key') {
    die(`QUEUE_SCOPE_BLANK_KEY is '${SHIPPED.QUEUE_SCOPE_BLANK_KEY}' - the server publishes `
      + `'blank_key'. The scope name is a wire value, not a local label.`);
  }
}

const base = await suite(PRISTINE, QUEUE_PRISTINE);
if (base.fail) console.error(`\nbaseline failures:\n  ${base.failed.join('\n  ')}`);

const apply = (where, mutate) => (where === 'queue'
  ? [PRISTINE, mutate(QUEUE_PRISTINE)]
  : [mutate(PRISTINE), QUEUE_PRISTINE]);
const original = (where) => (where === 'queue' ? QUEUE_PRISTINE : PRISTINE);

quiet = true;
let caught = 0; const escaped = [];
for (const [where, name, mutate] of DEFECTS) {
  const [e, q] = apply(where, mutate);
  if ((where === 'queue' ? q : e) === original(where)) {
    die(`defect "${name}" changed nothing in ${where} - its anchor no longer matches. `
      + `An inert mutant is a check that cannot fail.`);
  }
  let r;
  try { r = await suite(e, q); } catch (err) { r = { fail: 1, failed: [`threw: ${err && err.message}`] }; }
  if (r.fail > 0) caught++; else escaped.push(`[${where}] ${name}`);
}
let controlsCaught = 0; const controlsCaughtNames = [];
for (const [where, name, mutate] of CONTROLS) {
  const [e, q] = apply(where, mutate);
  if ((where === 'queue' ? q : e) === original(where)) {
    die(`control "${name}" changed nothing in ${where} - it proves nothing.`);
  }
  let r;
  try { r = await suite(e, q); } catch (err) { r = { fail: 1, failed: [`threw: ${err && err.message}`] }; }
  if (r.fail > 0) { controlsCaught++; controlsCaughtNames.push(`[${where}] ${name} (${r.failed[0]})`); }
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
