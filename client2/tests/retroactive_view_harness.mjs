// Harness — the retroactive (backfill) admin surface renders the SERVER's words, and never
// shows a number without the server's label for it.
// Run: node client2/tests/retroactive_view_harness.mjs
//
// WHY THIS EXISTS, AND WHY IT IS NOT THE CONFIG-RESOLVE HARNESS AGAIN.
//   `contracts/config_resolve_report/client_harness.mjs` scores one route family against a
//   vectors file the server half also reads. This surface has no vectors file (its server half
//   is scored by `server/tests/`), but it inherits the same load-bearing prohibition and adds a
//   sharper one of its own:
//
//     P1  every string the view emits is either a string the SERVER sent, an integer the client
//         counted, or an entry in the module's own frozen RETRO_CHROME/CHROME table
//     P2  every `detail` the payload carries is rendered EXACTLY ONCE — nothing dropped (which
//         sends the operator to the daemon log), nothing doubled (two chances to disagree)
//     P3  🔴 A NUMBER NEVER APPEARS WITHOUT THE SERVER'S LABEL FOR IT. Four of the five counts
//         cannot be exact on a request path and the qualifier lives inside `affected_label`
//         ("회수할 셀 (최대)"). A bare integer on a screen is read as the answer.
//     P4  the single confirmation is CHROME + server strings + the operator's own input, and
//         exactly one line is the client's question. A paraphrased danger is the client deciding
//         what the danger is, and one of these five is not the same kind of operation as the
//         other four.
//
// THE PAYLOADS ARE THE REAL ONES. `INVENTORY` and the five count fixtures below were captured
// from a running server (`GET /admin/retroactive/*`, 2026-07-31) rather than imagined, so a
// field the server renamed shows up here as a failure instead of as a fixture that agrees with
// a stale belief. Server-owned sentences are replaced with MARKERS (`<<...>>`) so that any
// rewording by the client — a suffix, a trim, a translation — fails P1 loudly.
//
// EVERY CHECK IS PAIRED WITH A MUTANT. The suite re-runs against deliberately defective copies
// of the view module and FAILS if a defect still passes: a check that cannot fail proves
// nothing. Two CONTROL mutants (a local rename, and stripping comments) must ESCAPE — if a
// control is caught, some check is reading source text rather than behaviour.
//
// Exit codes: 0 = green | 1 = a check failed or a defect escaped | 2 = harness failure.
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const VIEW_PATH = join(SRC, 'retroactive_view.js');
const BASE_PATH = join(SRC, 'config_resolve_view.js');

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

if (!existsSync(VIEW_PATH)) die(`no view model at ${VIEW_PATH}`);
if (!existsSync(BASE_PATH)) die(`no base view model at ${BASE_PATH}`);

const PRISTINE = readFileSync(VIEW_PATH, 'utf8');
const BASE_URL = pathToFileURL(BASE_PATH).href;

/** Import a (possibly mutated) copy of the view module without writing into client2/src.
 *  The relative import is rewritten to an absolute file URL so a data: module can resolve it. */
async function loadView(source) {
  const rewritten = source.replaceAll("'./config_resolve_view.js'", `'${BASE_URL}'`);
  return import(`data:text/javascript;base64,${Buffer.from(rewritten, 'utf8').toString('base64')}`);
}

// ── the payloads ────────────────────────────────────────────────────────────────────
const mark = (kind, id) => `<<${kind}:${id}>>`;

/** `GET /admin/retroactive/operations`, captured 2026-07-31. Sentences replaced with markers. */
const INVENTORY = {
  operations: [
    {
      op: 'chain_replay', label: mark('label', 'chain_replay'),
      what_is_missing: mark('missing', 'chain_replay'),
      params: [{ name: 'rule', required: true, type: 'string', help: mark('help', 'rule') }],
      cli: mark('cli', 'chain_replay'),
      cli_only: [mark('cli_only', 'chain_replay#0'), mark('cli_only', 'chain_replay#1')],
      deletes: null, restartable: true,
      commit_granularity: mark('commit', 'chain_replay'),
    },
    {
      op: 'withdraw', label: mark('label', 'withdraw'),
      what_is_missing: mark('missing', 'withdraw'),
      params: [
        { name: 'table', required: true, type: 'string', help: '' },
        { name: 'source', required: true, type: 'string', help: '' },
        { name: 'columns', required: false, type: 'csv', help: mark('help', 'columns') },
      ],
      cli: mark('cli', 'withdraw'), cli_only: [mark('cli_only', 'withdraw#0')],
      deletes: mark('deletes', 'withdraw'), restartable: true,
      commit_granularity: mark('commit', 'withdraw'),
    },
    {
      // The one that is not like the others: it deletes an entity and rolls the whole run back.
      op: 'graph_orphans', label: mark('label', 'graph_orphans'),
      what_is_missing: mark('missing', 'graph_orphans'),
      params: [],
      cli: mark('cli', 'graph_orphans'), cli_only: [mark('cli_only', 'graph_orphans#0')],
      deletes: mark('deletes', 'graph_orphans'), restartable: false,
      commit_granularity: mark('commit', 'graph_orphans'),
    },
  ],
};

/** The three shapes of count the server declares. Every one of these is a real response shape. */
const COUNTS = {
  // sample + a SECOND labelled number that must never be added into `affected`
  sample_with_labelled_extra: {
    affected: 12, affected_label: mark('affected-label', 'chain_replay'),
    count_kind: 'sample', scanned: 200, scan_limit: 200, truncated: true,
    detail: mark('detail', 'chain_replay'),
    blocked_reason: null,
    extra: {
      withdrawal_candidates: 4,
      withdrawal_candidates_label: mark('extra-label', 'withdrawal_candidates'),
      user_protected_cells: 7,               // no label -> must NOT be rendered
      trigger_table: 'bonding_log',          // not a number -> must NOT be rendered
      samples: [{ row_id: 1 }],
    },
    op: 'chain_replay', mode: 'dry-run', params: { rule: 'r1' },
    label: mark('label', 'chain_replay'), cli: mark('cli', 'chain_replay'),
    deletes: null, restartable: true, commit_granularity: mark('commit', 'chain_replay'),
  },
  // upper_bound + the sentence that names the gap between the ceiling and the answer
  upper_bound: {
    affected: 31, affected_label: mark('affected-label', 'withdraw'),
    count_kind: 'upper_bound', scanned: null, scan_limit: null, truncated: false,
    detail: mark('detail', 'withdraw'),
    blocked_reason: null,
    extra: { cells_claimed: 40, pinned: 9, why_upper_bound: mark('why', 'withdraw') },
    op: 'withdraw', mode: 'dry-run', params: { table: 't', source: 's' },
    label: mark('label', 'withdraw'), cli: mark('cli', 'withdraw'),
    deletes: mark('deletes', 'withdraw'), restartable: true,
    commit_granularity: mark('commit', 'withdraw'),
  },
  // the knob is off: the number answers "what happens if I turn it on", and the button is barred
  blocked: {
    affected: 0, affected_label: mark('affected-label', 'enrichment_confirm'),
    count_kind: 'sample', scanned: 0, scan_limit: 200, truncated: false,
    detail: mark('detail', 'enrichment_confirm'),
    blocked_reason: 'auto_confirm_off',
    extra: { queue_size: 0, refused: {}, auto_confirm: false },
    op: 'enrichment_confirm', mode: 'dry-run', params: { rule: 'e1' },
    label: mark('label', 'enrichment_confirm'), cli: mark('cli', 'enrichment_confirm'),
    deletes: null, restartable: true, commit_granularity: mark('commit', 'enrichment_confirm'),
  },
  // 🔴 the server declined to label the number. The screen must then show no number at all.
  unlabelled: {
    affected: 999, affected_label: null,
    count_kind: 'exact', scanned: null, scan_limit: null, truncated: false,
    detail: mark('detail', 'unlabelled'),
    blocked_reason: null, extra: {},
    op: 'graph_orphans', mode: 'dry-run', params: {},
    label: mark('label', 'graph_orphans'), cli: mark('cli', 'graph_orphans'),
    deletes: mark('deletes', 'graph_orphans'), restartable: false,
    commit_granularity: mark('commit', 'graph_orphans'),
  },
};

const RUN_ACK = {
  status: 'queued', run_id: 'a1b2c3d4e5f6', op: 'withdraw',
  params: { table: 't', source: 's' }, label: mark('label', 'withdraw'),
};

// ── scoring ─────────────────────────────────────────────────────────────────────────

/** Every string anywhere in a payload (keys included — some server words arrive as keys), and
 *  every `detail` value specifically. */
function scanPayload(node, strings = new Set(), details = []) {
  if (node === null || node === undefined) return { strings, details };
  if (Array.isArray(node)) {
    for (const c of node) scanPayload(c, strings, details);
    return { strings, details };
  }
  if (typeof node === 'string') { strings.add(node); return { strings, details }; }
  if (typeof node !== 'object') return { strings, details };
  for (const [key, value] of Object.entries(node)) {
    strings.add(key);
    if (key === 'detail' && typeof value === 'string' && value !== '') details.push(value);
    scanPayload(value, strings, details);
  }
  return { strings, details };
}

let quiet = false;

async function suite(source) {
  const view = await loadView(source);
  const { collectTexts } = await import(BASE_URL);
  const chromeSet = new Set([...view.RETRO_CHROME_STRINGS, ...Object.values(view.CHROME)]);

  let pass = 0; const failed = [];
  /** The text out of a tagged node, for comparing a label against its chrome constant. */
  const cfg = (node) => (node && typeof node.text === 'string' ? node.text : '');
  const ok = (cond, what) => {
    if (cond) { pass++; return; }
    failed.push(what);
    if (!quiet) console.log(`  FAIL ${what}`);
  };

  /** P1 — provenance, for a whole view tree. */
  const scoreTexts = (texts, payload, label) => {
    const { strings } = scanPayload(payload);
    for (const t of texts) {
      if (t.src === 'server') {
        ok(strings.has(t.text),
          `${label}: emits "${t.text}" as server-owned, but the payload never said it`);
      } else if (t.src === 'chrome') {
        ok(chromeSet.has(t.text),
          `${label}: client-authored "${t.text}" is not in the frozen chrome table`);
      } else if (t.src === 'count') {
        ok(Number.isInteger(t.value) && String(t.value) === t.text,
          `${label}: count "${t.text}" does not spell its own integer (${t.value})`);
      } else if (t.src === 'value') {
        // A payload VALUE spelled in JSON — the tagger F9 uses to echo a config value back in
        // the syntax of the file it came from. Here it carries `truncated`, whose meaning the
        // server states in no words at all: the client must not translate a boolean into a
        // sentence, so it spells the boolean.
        ok(JSON.stringify(t.raw) === t.text,
          `${label}: value "${t.text}" is not JSON.stringify of ${JSON.stringify(t.raw)}`);
      } else {
        ok(false, `${label}: unknown provenance tag '${t.src}' for "${t.text}"`);
      }
    }
  };

  /** P2 — every server sentence rendered exactly once. */
  const scoreDetails = (texts, payload, label) => {
    const { details } = scanPayload(payload);
    const rendered = texts.filter((t) => t.src === 'server').map((t) => t.text);
    for (const detail of details) {
      const seen = rendered.filter((text) => text === detail).length;
      ok(seen === 1, `${label}: \`detail\` rendered ${seen} time(s), expected 1: ${detail}`);
    }
  };

  // ── the inventory ────────────────────────────────────────────────────────────────
  const ops = view.buildOperationsView(INVENTORY);
  const opTexts = collectTexts(ops);
  scoreTexts(opTexts, INVENTORY, 'inventory');
  ok(ops.operations.length === 3, 'inventory: all three operations survive the view');
  ok(ops.total.value === 3 && ops.total.text === '3', 'inventory: the headline counts what it lists');
  ok(!ops.empty, 'inventory: a populated payload is not reported as empty');
  ok(view.buildOperationsView({ operations: [] }).empty, 'inventory: an empty payload IS empty');

  // The row's colour follows the two flags; the WORDS come from the payload.
  const byOp = Object.fromEntries(ops.operations.map((o) => [o.op, o]));
  ok(byOp.graph_orphans.tone === 'danger',
    'inventory: the operation that cannot be resumed is drawn as the dangerous one');
  ok(byOp.withdraw.tone === 'warn', 'inventory: a deleting-but-restartable operation is warned');
  ok(byOp.chain_replay.tone === '', 'inventory: an additive restartable operation is neutral');
  ok(byOp.chain_replay.deletes === null,
    'inventory: an operation that deletes nothing carries no deletes line');
  ok(byOp.withdraw.params.length === 3 && byOp.withdraw.params[2].required === false,
    'inventory: the optional parameter is carried as optional');
  ok(byOp.graph_orphans.params.length === 0,
    'inventory: the parameterless operation asks for nothing');

  // ── the counts ───────────────────────────────────────────────────────────────────
  for (const [name, payload] of Object.entries(COUNTS)) {
    const cv = view.buildCountView(payload);
    const texts = collectTexts(cv);
    scoreTexts(texts, payload, `count/${name}`);
    scoreDetails(texts, payload, `count/${name}`);
  }

  const sampled = view.buildCountView(COUNTS.sample_with_labelled_extra);
  // P3, the positive half
  ok(sampled.affected && sampled.affected.value === 12 && sampled.affectedLabel,
    'count: a labelled number is shown, with its label');
  ok(sampled.kind && sampled.kind.text === 'sample',
    "count: the server's own word for what kind of number this is survives untranslated");
  ok(sampled.kindTone === 'warn', 'count: a sample is not drawn as a settled fact');
  ok(sampled.truncated === true, 'count: a budget-exhausted scan is flagged');
  // P3, the sharp half
  const unlabelled = view.buildCountView(COUNTS.unlabelled);
  ok(unlabelled.affected === null,
    '🔴 count: an UNLABELLED number must not reach the screen — a bare integer reads as the answer');
  ok(unlabelled.detail !== null,
    'count: dropping the number must not drop the sentence that contains it');
  ok(view.buildCountView({}).affected === null, 'count: an empty payload yields no number');

  // The second labelled number travels separately and is never folded into `affected`.
  ok(sampled.extras.length === 1 && sampled.extras[0].count.value === 4,
    'count: the server-labelled second number is shown');
  ok(sampled.affected.value === 12,
    'count: the second number is NOT added into the write count (12, not 16)');
  for (const extra of sampled.extras) {
    ok(Boolean(extra.label), 'count: every extra number carries the label the server gave it');
  }
  ok(view.buildCountView(COUNTS.upper_bound).extras.length === 0,
    'count: unlabelled extras are not invented into a label');
  ok(view.buildCountView(COUNTS.upper_bound).why !== null,
    'count: the sentence naming the gap between the ceiling and the answer is carried');

  const blocked = view.buildCountView(COUNTS.blocked);
  ok(blocked.blocked && blocked.blocked.text === 'auto_confirm_off',
    'count: the refusal word is carried as data, not interpreted');
  ok(sampled.blocked === null, 'count: an unblocked operation carries no refusal');

  // An unknown exactness declaration must draw neutral rather than be guessed at — AND neutral
  // must not be the colour of the most confident kind, or "unrecognised" renders as "this number
  // is the answer". That is the `미상`-reads-as-a-value shape.
  const toneOf = (kind) => view.buildCountView({ count_kind: kind, detail: 'x' }).kindTone;
  ok(toneOf('something_new') === '',
    'count: an unrecognised count kind draws neutral instead of a guess');
  ok(toneOf('exact') !== toneOf('something_new'),
    '🔴 F3: an unrecognised kind must not render identically to `exact`');
  ok(toneOf('sample') !== toneOf('exact') && toneOf('upper_bound') !== toneOf('exact'),
    'F3: an approximate kind never shares a colour with the exact one');

  // ── the acknowledgement ──────────────────────────────────────────────────────────
  const runView = view.buildRunView(RUN_ACK);
  scoreTexts(collectTexts(runView), RUN_ACK, 'run');
  ok(runView.runId.text === 'a1b2c3d4e5f6', 'run: the run id — the scheduler log key — is kept');
  // 🔴 F5: the acknowledgement must say WHAT was queued, from the server's own echo. Without it
  // the box says a run happened and not which one — and that is the fact that would expose a
  // measurement carried onto the wrong parameters.
  ok(runView.params.length === 2,
    '🔴 F5: the queued parameters the server echoed are carried into the acknowledgement');
  ok(runView.params.every((p) => p.name && p.values.length),
    'F5: every echoed parameter arrives with its name and its value(s)');
  const listAck = view.buildRunView({ ...RUN_ACK, params: { columns: ['a', 'b'] } });
  ok(listAck.params[0].values.length === 2
     && listAck.params[0].values.every((v) => v.src === 'server'),
    'F5: a list parameter carries its elements separately — a joined string is not payload text');

  // ── the single confirmation ──────────────────────────────────────────────────────
  const params = [{ key: 'table', value: 'bonding_log' }, { key: 'source', value: 'old_rule' }];
  const withdrawRecord = {
    params: { table: 'bonding_log', source: 'old_rule' },
    count: {
      ok: true, view: view.buildCountView(COUNTS.upper_bound),
      paramsKey: view.paramsKey(params),
    },
    busy: null,
  };
  const lines = view.buildConfirmLines(byOp.withdraw, withdrawRecord, params);

  /** P4 — one question, and every client-authored LABEL is followed by the value that fills it.
   *  `payload` is what the dialog's server strings must trace back to; default is the fixture the
   *  first scenario is built from. */
  const scoreConfirm = (rows, label, payload) => {
    const { strings } = payload
      ? scanPayload({ inventory: INVENTORY, count: payload })
      : scanPayload({ inventory: INVENTORY, count: COUNTS.upper_bound });
    let questions = 0;
    rows.forEach((line, i) => {
      if (line.src === 'chrome') {
        ok(chromeSet.has(line.text), `${label}: "${line.text}" is not in the frozen chrome table`);
        if (line.role === 'question') {
          questions++;
          ok(i === rows.length - 1, `${label}: the question is not the last line`);
        } else {
          ok(line.role === 'label', `${label}: chrome line "${line.text}" declares no role`);
          const next = rows[i + 1];
          ok(next && next.src !== 'chrome',
            `${label}: the label "${line.text}" is not followed by the value it names`);
        }
      } else if (line.src === 'server') {
        ok(strings.has(line.text), `${label}: "${line.text}" was never said by the server`);
      } else if (line.src === 'count') {
        ok(Number.isInteger(line.value), `${label}: a count spells an integer`);
      } else if (line.src === 'value') {
        ok(JSON.stringify(line.raw) === line.text,
          `${label}: value "${line.text}" is not JSON.stringify of its payload value`);
      } else if (line.src === 'input') {
        ok(line.text.includes(line.raw), `${label}: the operator input is echoed intact`);
      } else {
        ok(false, `${label}: unknown provenance '${line.src}'`);
      }
    });
    ok(questions === 1,
      `🔴 ${label}: exactly one client-authored SENTENCE, found ${questions} — every other line is `
      + 'a fact somebody else owns');
  };

  scoreConfirm(lines, 'P4 confirm');
  ok(lines.some((l) => l.text === COUNTS.upper_bound.deletes),
    "confirm: what this operation deletes is stated, in the server's words");
  ok(lines.some((l) => l.text === COUNTS.upper_bound.commit_granularity),
    "confirm: how it commits is stated, in the server's words");
  ok(lines.some((l) => l.text === COUNTS.upper_bound.detail),
    'confirm: the sentence from the count the operator just took is carried into the dialog');
  // 🔴 F4: whatever the row is allowed to say about certainty, the dialog says at least as much.
  // The row has four carriers; the dialog is plain text, so the two that were colour-only
  // (`count_kind` chip, `truncated` border) have to arrive as words and values.
  ok(lines.some((l) => l.text === COUNTS.upper_bound.count_kind),
    '🔴 F4: the exactness declaration reaches the last surface before the write');
  ok(lines.some((l) => l.text === JSON.stringify(COUNTS.upper_bound.truncated)),
    '🔴 F4: whether the sample hit its budget reaches the dialog — a border colour cannot');
  ok(lines.some((l) => l.text === COUNTS.upper_bound.extra.why_upper_bound),
    '🔴 F4: the sentence naming the gap between the ceiling and the answer reaches the dialog');
  const sampledLines = view.buildConfirmLines(
    byOp.chain_replay,
    { params: { rule: 'inv' },
      count: { ok: true, view: sampled, paramsKey: view.paramsKey([{ key: 'rule', value: 'inv' }]) },
      busy: null },
    [{ key: 'rule', value: 'inv' }]);
  scoreConfirm(sampledLines, 'F4 confirm (sample)', COUNTS.sample_with_labelled_extra);
  ok(sampledLines.some((l) => l.text === String(
    COUNTS.sample_with_labelled_extra.extra.withdrawal_candidates)),
    '🔴 F4: the server-labelled second number reaches the dialog too');
  ok(lines.some((l) => l.text.includes('bonding_log')),
    'confirm: the operator reads back what they typed');

  // Without a count taken, the confirmation still carries the operation's own facts.
  const blind = view.buildConfirmLines(byOp.graph_orphans, null, []);
  scoreConfirm(blind, 'P4 confirm (unmeasured)');
  ok(blind.some((l) => l.text === INVENTORY.operations[2].deletes),
    'confirm: an unmeasured run still says what it deletes');
  ok(blind.some((l) => l.text === INVENTORY.operations[2].commit_granularity),
    'confirm: an unmeasured run still says that it does not resume');

  // An operation that deletes nothing must not grow an empty "삭제 대상" line.
  const additive = view.buildConfirmLines(byOp.chain_replay, null, [{ key: 'rule', value: 'r1' }]);
  scoreConfirm(additive, 'P4 confirm (additive)');
  ok(!additive.some((l) => l.text === view.RETRO_CHROME.DELETES),
    'confirm: an operation that deletes nothing carries no deletes label');

  // ── F1: a measurement belongs to (operation, parameters), not to the operation ────
  //
  // `_count_chain_replay`'s `detail` does not name the rule it measured. So a count carried onto
  // a different parameter is INVISIBLE on the dialog: the number and the whole server sentence
  // are about something else and nothing says so. This is the quiet-plausible-wrong shape.
  const measured = view.buildCountView(COUNTS.sample_with_labelled_extra);
  const recordFor = (typed, countParams) => ({
    params: { rule: typed },
    count: { ok: true, view: measured, paramsKey: view.paramsKey([{ key: 'rule', value: countParams }]) },
    busy: null,
  });

  ok(view.paramsKey([{ key: 'rule', value: 'inv' }])
     === view.paramsKey([{ key: 'rule', value: 'inv' }]),
    'F1: the same parameter set has the same identity');
  ok(view.paramsKey([{ key: 'a', value: '1' }, { key: 'b', value: '2' }])
     === view.paramsKey([{ key: 'b', value: '2' }, { key: 'a', value: '1' }]),
    'F1: parameter identity does not depend on input order');
  ok(view.paramsKey([{ key: 'rule', value: 'inv' }])
     !== view.paramsKey([{ key: 'rule', value: 'lot_alias' }]),
    'F1: different parameters have different identities');

  // 🔴 THE SEPARATOR IS PINNED BY ITS VALUE, not by the three lines above -- those pass
  //    with ANY separator, so they cannot see it change. The spelling moved from a raw byte to
  //    an escape on 2026-08-31 (the raw byte made grep call this file binary and blinded two
  //    searches in one night); these two lines are what make that a spelling change and not a
  //    behaviour change.
  ok(view.paramsKey([{ key: 'a', value: '1' }, { key: 'b', value: '2' }])
     === ['a=1', 'b=2'].join(String.fromCharCode(0)),
    'F1: the identity joins on U+0000, and that is the separator it still joins on');
  // 🔴 THE DISCRIMINATING PAIR. A printable separator lets a VALUE forge a second entry:
  //    with ',' both of these read `a=1,b=2` and two different parameter sets share one identity,
  //    which is how a count measured for one set gets shown for another. U+0000 cannot be typed
  //    into a value, so they stay apart. A fixture both spellings agree on would decide nothing.
  ok(view.paramsKey([{ key: 'a', value: '1' }, { key: 'b', value: '2' }])
     !== view.paramsKey([{ key: 'a', value: '1,b=2' }]),
    'F1: a value carrying a printable separator cannot forge another parameter');

  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  // ── G. 진행 목록 — 「도는 것들」 한 목록, [무엇] [진행] [ × ] ──────────
  {
    const NOW = Date.parse('2026-08-31T09:00:00+09:00');
    const payload = {
      runs: [
        { run_id: 'r1', op: 'ledger_backfill', label: '원장 백필', params: { source: 'lot_event' },
          state: 'running', processed_rows: 1240, total_rows: null,
          started_at: '2026-08-31T08:43:00+09:00' },
        { run_id: 'r2', op: 'chain_replay', label: '체인 리플레이', params: { rule: 'inv' },
          state: 'cancelling', processed_rows: 5, total_rows: null,
          started_at: '2026-08-31T08:58:00+09:00' },
        { run_id: 'r3', op: 'ledger_rescope', label: '끝남', state: 'succeeded' },
      ],
      ingestions: [{ table_name: 'dt_log', filename: 'a.csv', status: 'PROCESSING',
                     processed_rows: 430, total_rows: 1000, elapsed_seconds: 190 }],
    };
    const rv = view.buildRunsView(payload, NOW, { ledger_backfill: true, chain_replay: true });

    ok(rv.rows.length === 3, 'G1: a finished run is not on the list of what is running');
    ok(same(rv.rows.map((r) => r.kind), ['run', 'run', 'ingestion']),
      'G1: both sources are ONE list, not two');

    ok(rv.rows[0].progress.mode === 'text',
      'G2: an operation that cannot know its total gets no bar');
    ok(rv.rows[0].progress.percent === null,
      'G2: ... and no percent at all, rather than a made-up one');
    ok(rv.rows[0].progress.text.includes('1,240'),
      'G2: ... it says the processed count it does know');
    // UI 가 영어로 가면서 이 단언도 같이 옴깁니다 — 재는 것은 같습니다.
    ok(rv.rows[0].progress.elapsed === '17m',
      'G2: ... and how long it has run, which is what decides whether to stop it');
    ok(rv.rows[2].progress.mode === 'bar',
      'G3: an operation whose total is known gets the bar');
    ok(rv.rows[2].progress.percent === 43,
      'G3: ... at the percentage its own numbers give');

    ok(same(rv.rows.map((r) => r.cancel), [true, true, false]),
      'G4: the X is drawn only where the declaration says the run can be cancelled');
    ok(same(view.buildRunsView(payload, NOW, {}).rows.map((r) => r.cancel), [false, false, false]),
      'G4: an operation the declaration does not mark cancellable gets no X');

    ok(rv.rows[1].stopping === true,
      'G5: a run whose cancel was requested says it is stopping');
    ok(rv.rows.some((r) => r.id === 'r2'),
      'G5: ... and stays on the list until it actually stops');

    ok(view.buildRunsView({ runs: [], ingestions: [] }, NOW, {}).empty === true,
      'G6: an empty list is a fact and says so');
    ok(view.buildRunsView(null, NOW, {}).rows.length === 0,
      'G6: no payload is the same empty, not a crash');

    ok(view.elapsedMinutes(null, NOW) === null,
      'G7: a run with no start time has no elapsed, not zero');

    // ── G8. WAITING IS NOT RUNNING ────────────────────────────────────────────────
    // 🔴 THE DISCRIMINATING FIXTURE. All four rows carry `processed 0 / total null`, so every
    //    other field on them is IDENTICAL -- same cell mode, same text, same absent percent.
    //    A queued run loads the server with nothing, and this screen exists to answer "which
    //    one do I cut". If waiting and working paint the same, that answer is wrong on the
    //    only rows where it costs something. `moving` is the whole difference, which is what
    //    makes this fixture able to see it; a payload where the two also differed in count
    //    would pass with the flag hardcoded either way.
    const waitPayload = {
      runs: [
        { run_id: 'q1', op: 'ledger_backfill', label: '대기', params: {}, state: 'queued',
          processed_rows: 0, total_rows: null, queued_at: '2026-08-31T08:20:00+09:00' },
        { run_id: 'w1', op: 'ledger_backfill', label: '진행', params: {}, state: 'running',
          processed_rows: 0, total_rows: null, started_at: '2026-08-31T08:20:00+09:00' },
      ],
      ingestions: [
        { table_name: 't', filename: 'q.csv', status: 'QUEUED', processed_rows: 0,
          total_rows: null, elapsed_seconds: 2400 },
        { table_name: 't', filename: 'p.csv', status: 'PROCESSING', processed_rows: 0,
          total_rows: null, elapsed_seconds: 30 },
      ],
    };
    const wv = view.buildRunsView(waitPayload, NOW, { ledger_backfill: true });
    ok(same(wv.rows.map((r) => r.progress.text), ['0', '0', '0', '0']),
      'G8: the four rows say the same thing about their counts');
    ok(same(wv.rows.map((r) => r.progress.mode), ['text', 'text', 'text', 'text']),
      'G8: ... and get the same cell, so nothing else can separate them');
    ok(same(wv.rows.map((r) => r.moving), [false, true, false, true]),
      'G8: ... and only the queued ones are marked as not moving');
    ok(wv.rows[0].moving === false && wv.rows[0].id === 'q1',
      'G8: a run sitting in the queue is not running, whichever source it came from');
    ok(wv.rows[2].moving === false && wv.rows[3].moving === true,
      'G8: ... and the ingestion registry word is read for the same judgement');
  }

  const stale = recordFor('lot_alias', 'inv');
  ok(view.resolveCount(stale, byOp.chain_replay).stale === true,
    'F1: a count measured for another parameter is reported stale');
  ok(view.resolveCount(recordFor('inv', 'inv'), byOp.chain_replay).stale === false,
    'F1: a count measured for the current parameter is not stale');

  const staleLines = view.buildConfirmLines(
    byOp.chain_replay, stale, [{ key: 'rule', value: 'lot_alias' }]);
  scoreConfirm(staleLines, 'F1 confirm (stale count)');
  ok(!staleLines.some((l) => l.text === measured.affected.text),
    '🔴 F1: the confirmation must NOT show a number measured for a different parameter');
  ok(!staleLines.some((l) => l.text === COUNTS.sample_with_labelled_extra.detail),
    '🔴 F1: the confirmation must NOT show a server sentence measured for a different parameter');
  ok(staleLines.some((l) => l.text.includes('lot_alias')),
    'F1: the parameter actually being submitted is still read back');

  const freshLines = view.buildConfirmLines(
    byOp.chain_replay, recordFor('inv', 'inv'), [{ key: 'rule', value: 'inv' }]);
  ok(freshLines.some((l) => l.text === measured.affected.text),
    'F1: a count that DOES belong to the submitted parameters is still carried');

  // A stale count must not keep barring the write either — that block was measured elsewhere.
  const staleBlocked = {
    params: { rule: 'other' },
    count: { ok: true, view: view.buildCountView(COUNTS.blocked),
             paramsKey: view.paramsKey([{ key: 'rule', value: 'core_wafer_attribution' }]) },
    busy: null,
  };
  ok(view.buildActionsView(byOp.chain_replay, staleBlocked).run.disabled === false,
    'F1: a refusal measured for another parameter does not bar the current one');

  // ── F2: a rebuild must not be able to forget that a write is in flight ───────────
  const idle = { params: {}, count: null, busy: null };
  ok(view.buildActionsView(byOp.graph_orphans, idle).run.disabled === false
     && view.buildActionsView(byOp.graph_orphans, idle).count.disabled === false,
    'F2: an idle row offers both buttons');

  const running = { params: {}, count: null, busy: 'run' };
  ok(view.buildActionsView(byOp.graph_orphans, running).run.disabled === true,
    '🔴 F2: a run in flight disables the write button — any rebuild reconstructs that');
  ok(view.buildActionsView(byOp.graph_orphans, running).count.disabled === true,
    '🔴 F2: a run in flight also holds the count button, which shares the row and its host');
  ok(cfg(view.buildActionsView(byOp.graph_orphans, running).run.label) === view.RETRO_CHROME.RUNNING,
    'F2: the write button says it is in flight');

  const counting = { params: {}, count: null, busy: 'count' };
  ok(view.buildActionsView(byOp.graph_orphans, counting).run.disabled === true,
    '🔴 F2: measuring holds the write button — the count returning is what used to re-arm it');
  ok(cfg(view.buildActionsView(byOp.graph_orphans, counting).count.label)
     === view.RETRO_CHROME.COUNTING,
    'F2: the count button says it is in flight');

  const blockedIdle = {
    params: { rule: 'e1' },
    count: { ok: true, view: view.buildCountView(COUNTS.blocked),
             paramsKey: view.paramsKey([{ key: 'rule', value: 'e1' }]) },
    busy: null,
  };
  ok(view.buildActionsView(byOp.chain_replay, blockedIdle).run.disabled === true,
    'F2: a current refusal still bars the write');

  // ── F10: a parameter the inventory no longer declares cannot be sent ─────────────
  // A restarted server that renamed or dropped a parameter would otherwise leave the old key in
  // the record, and the count route answers 400 about a field that is no longer on screen.
  const drifted = { params: { rule: 'inv', removed_knob: 'x' }, count: null, busy: null };
  const entries = view.paramEntries(drifted, byOp.chain_replay);
  ok(entries.length === 1 && entries[0].key === 'rule',
    '🔴 F10: only parameters the inventory declares are sent');
  ok(view.paramEntries({ params: { rule: '  ' } }, byOp.chain_replay).length === 0,
    'F10: a whitespace-only value is not a value');
  ok(view.paramEntries({ params: {} }, byOp.graph_orphans).length === 0,
    'F10: an operation that declares no parameters sends none');

  return { pass, fail: failed.length, failed };
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

const DEFECTS = [
  ['bare number reaches the screen',
    swap('affected: affectedLabel ? integer(data.affected) : null,',
      'affected: integer(data.affected),')],
  ['the server sentence is reworded on the way out',
    swap('detail: text(data.detail),', "detail: srv(String(data.detail) + ' (표본)'),")],
  ['the client decides what the count kind means',
    swap('kind: text(kind),', "kind: chrome(kind === 'sample' ? '대략' : '정확'),")],
  ['an unlabelled extra number is rendered anyway',
    swap('.filter((pair) => pair.label && pair.value)', '.filter((pair) => pair.value)')],
  ['the confirmation paraphrases the danger',
    swap('chrome(RETRO_CHROME.CONFIRM_QUESTION)', "chrome('되돌릴 수 없습니다. 계속할까요?')")],
  ['a dropped sentence sends the operator to the daemon log',
    swap('    pair(null, countView.detail);', '    /* dropped */')],
  ['a slot label is drawn with nothing in it',
    swap('    if (!value) return;',
      '    if (!value) { if (label) lines.push({ ...label, role: \'label\' }); return; }')],

  ['G8: a waiting run paints as a working one (runs)',
    swap("      moving: state !== 'queued',", '      moving: true,')],
  ['G8: a waiting file paints as a working one (ingestions)',
    swap("      moving: String(job.status || '') === 'PROCESSING',", '      moving: true,')],

  // ── the QA round's findings, pinned so none of them can come back quietly ────────
  ['F1: a measurement outlives the parameter it was measured for (confirmation)',
    swap(`  const countView = resolved.count && resolved.count.ok && !resolved.stale
    ? resolved.count.view : null;`,
      '  const countView = resolved.count && resolved.count.ok ? resolved.count.view : null;')],
  ['F1: a stale refusal keeps barring the write button',
    swap('  const view = resolved.count && resolved.count.ok && !resolved.stale ? resolved.count.view : null;',
      '  const view = resolved.count && resolved.count.ok ? resolved.count.view : null;')],
  ['F1: parameter identity ignores the value',
    swap('    .map((entry) => `${entry.key}=${entry.value}`)', '    .map((entry) => `${entry.key}`)')],
  ['F2: a rebuild re-arms the write button mid-flight',
    swap('      disabled: busy !== null || Boolean(blocked),', '      disabled: Boolean(blocked),')],
  ['F2: the count button is free to run during a write',
    swap('      disabled: busy !== null,\n    },\n    run: {', '      disabled: false,\n    },\n    run: {')],
  ['F3: an unrecognised count kind renders as the confident one',
    swap("const KIND_TONE = { exact: 'ok',", "const KIND_TONE = { exact: '',")],
  ['F4: the confirmation drops the exactness declaration',
    swap('    pair(countView.kindLabel, countView.kind);', '    /* dropped */')],
  ['F4: the confirmation drops whether the sample hit its budget',
    swap('    pair(countView.truncatedLabel, countView.truncatedValue);', '    /* dropped */')],
  ['F4: the confirmation drops the labelled second number',
    swap('    list(countView.extras).forEach((extra) => pair(extra.label, extra.count));',
      '    /* dropped */')],
  ['F5: the acknowledgement does not say what was queued',
    swap('    params: Object.keys(params).map((key) => ({', '    params: [].map((key) => ({')],
  ['F10: an undeclared parameter is still sent',
    swap('  const declared = operation ? list(operation.params).map((p) => p.key) : Object.keys(stored);',
      '  const declared = Object.keys(stored);')],
];

const CONTROLS = [
  ['a local rename', swap('function list(value) {\n  return Array.isArray(value) ? value : [];\n}',
    'function asList(v) {\n  return Array.isArray(v) ? v : [];\n}')],
  ['comments stripped', (src) => src.split('\n')
    .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

// The control that renames `list` must also rename its call sites, or it is not a control.
CONTROLS[0][1] = (src) => swap('function list(value) {\n  return Array.isArray(value) ? value : [];\n}',
  'function asList(v) {\n  return Array.isArray(v) ? v : [];\n}')(src).replaceAll('list(', 'asList(')
  .replace('function asList(v)', 'function asList(v)');

console.log('retroactive_view_harness ― the server makes the sentences, the client renders them\n');
const base = await suite(PRISTINE);
console.log(`\n── base suite: ${base.pass} passed, ${base.fail} failed`);

quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n── defect mutants (each must be CAUGHT) ───────────────────────────');
for (const [name, mutate] of DEFECTS) {
  let r;
  try { r = await suite(mutate(PRISTINE)); }
  catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}  (${r.failed[0]})`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0; const controlsCaughtNames = [];
console.log('\n── control mutants (each must ESCAPE) ─────────────────────────────');
for (const [name, mutate] of CONTROLS) {
  let r;
  try { r = await suite(mutate(PRISTINE)); }
  catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; controlsCaughtNames.push(`${name} (${r.failed[0]})`); console.log(`  CAUGHT  ${name}  (${r.failed[0]})`); }
}
quiet = false;

if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);
if (controlsCaughtNames.length) {
  console.error(`\ncontrols that were caught (a check is reading source text):\n  ${controlsCaughtNames.join('\n  ')}`);
}

const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; `
  + `${caught}/${DEFECTS.length} defects caught, ${escapedNames.length} escaped; `
  + `${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
