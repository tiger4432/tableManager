// RETROACTIVE (BACKFILL) SURFACE — the view model for the three `/admin/retroactive/*` routes.
//
// WHY THIS IS A SEPARATE, DOM-FREE MODULE.
//   Same reason `config_resolve_view.js` is one, and it is the load-bearing half of this seam:
//   the server composes every operator-facing sentence and this side renders it VERBATIM. A
//   renderer that builds DOM inline cannot be scored for that from node, so every string that
//   leaves this file is tagged with its provenance and `client2/tests/retroactive_view_harness.mjs`
//   checks each tag against the payload it was built from.
//
// THE ONE THING THIS SURFACE MUST NOT DO — PRESENT AN APPROXIMATE COUNT AS EXACT.
//   Four of the five counts cannot be exact on a request path, and `server/retroactive.py` says
//   so in three separate places rather than hiding it:
//
//     `count_kind`      exact | sample | upper_bound     — the machine-readable declaration
//     `affected_label`  e.g. "회수할 셀 (최대)"           — the qualifier, inside the label itself
//     `detail`          the whole sentence, with numbers
//
//   So the rule here is mechanical: **a number is never emitted without the server's own label
//   for it.** `buildCountView` returns `affected: null` when `affected_label` is missing, because
//   a bare integer on a screen is read as the answer, and for four of five it is not. The client
//   never decides that a count is approximate and never decides that it is not — it carries what
//   the server declared, in the server's words.
//
// WHAT THIS FILE IS ALLOWED TO KNOW
//   Structure, colour, and which URL exists. Not meaning. `count_kind` and `restartable` and
//   `truncated` appear here only as inputs to a colour, never as inputs to a sentence; anything
//   this file has no colour for draws neutral rather than being guessed at.
import { CHROME, srv, val, chrome, count } from './config_resolve_view.js';

// The failure sentences are NOT re-authored here. `CHROME.FETCH_*` and `fetchFailureLine` already
// split "nothing answered" / "the process is older than the route" / "our gate said no" / "a proxy
// answered instead of us", and those four have exactly the same meaning on these routes as on
// `/admin/config/resolve` — the routes landed later, so an older process 404s here too, and the
// same corporate proxy answers the same port. A second copy of that classifier would drift.
export { CHROME } from './config_resolve_view.js';

/** Client-authored strings. Structural labels only — never a verdict, never per-operation.
 *
 * Everything here names a SLOT ("삭제 대상", "커밋 단위"); what goes in the slot always comes
 * from the payload. The moment an entry here describes what an operation does, this table has
 * acquired an opinion the server did not authorise.
 */
export const RETRO_CHROME = Object.freeze({
  HEADLINE: 'Retroactive',
  HINT: 'details',
  LOADING: '…',
  LIST_FAILED: 'list unavailable',
  NO_OPERATIONS: 'the server reports no retroactive operations',
  OPERATIONS: 'operations',

  PARAMS: 'parameters',
  REQUIRED: 'required',

  COUNT: 'count',
  COUNTING: 'counting…',
  COUNT_FAILED: 'count failed',

  RUN: 'run',
  // 인라인 확인의 물러나기. 표가 «하나»라야 두 자리가 서로 다른 말을 안 합니다.
  CANCEL: 'cancel',
  RUNNING: 'requesting…',
  RUN_FAILED: 'run request failed',
  QUEUED: 'queued',
  RUN_ID: 'run id',

  DELETES: 'deletes',
  COMMIT: 'commits',
  BLOCKED: 'blocked',
  CLI: 'CLI',
  CLI_ONLY: 'CLI only',
  // A statement about the CLIENT'S OWN state — the inputs moved since the measurement — not a
  // verdict about the data. Same class as 「세는 중…」, and it never reaches the confirmation:
  // there a stale count is simply not shown.
  STALE: 'inputs changed — this count is not for the request you would send',
  // A SLOT NAME for `truncated`, whose value is spelled as itself. The server says nothing about
  // truncation in words on this route (its sibling dry-run route does), and the client will not
  // compose the missing sentence — but a border colour cannot reach a plain-text dialog, so the
  // fact travels as label + JSON value, which is `buildSetting`'s shape in the F9 report.
  TRUNCATED: 'sample hit its limit',
  KIND: 'count kind',
  PARAMS_ECHO: 'queued parameters',

  // The single confirmation. It asks the question; every FACT above it in the dialog is a string
  // the server sent (label, deletes, commit_granularity, and the count sentence when one exists).
  CONFIRM_QUESTION: 'Queue this retroactive run?',
});

export const RETRO_CHROME_STRINGS = Object.freeze(Object.values(RETRO_CHROME));

/** PRESENTATION ONLY — which colour an exactness declaration is drawn in.
 *
 * The server decides which kind a count is; this table decides nothing except the colour, and a
 * kind this client has never heard of draws neutral rather than being guessed at. Same shape and
 * same prohibition as `POPULATION_TONE` in `config_resolve_view.js`. No sentence is composed from
 * it: the WORDS that qualify the number are `affected_label` and `detail`, both server-owned.
 */
// 🔴 `exact` maps to an EXPLICIT tone so that `''` means "unrecognised" and nothing else. The
// first version left `exact` neutral, which made every kind this client has not heard of render
// in the one colour that says "this number is the answer" — an unknown qualifier drawn as the
// most confident one, which is `미상` reading as a value. F9's `POPULATION_TONE` does not have
// the collision (its safe value `effective` is `'ok'`); this table was modelled on it and had
// broken the property it was copying.
const KIND_TONE = { exact: 'ok', sample: 'warn', upper_bound: 'warn' };

// ---------------------------------------------------------------------------
// THE PER-OPERATION RECORD, and the three pure functions that read it.
//
// Everything a rendered row shows is a function of ONE record, because the two
// defects this section exists to prevent were both "derived state kept somewhere else":
// a count cached under the operation while the parameters it was measured for lived in a
// different map, and a write button whose in-flight state lived only in the DOM node that a
// re-render replaced. Both are the same mistake, so both get the same cure — the record is
// the only source, and every render is a pure function of it that node can score.
//
//   { params:   {name: string},           what the operator has typed
//     count:    {ok, view, failure, paramsKey} | null,
//     run:      {view} | null,
//     busy:     'count' | 'run' | null }
// ---------------------------------------------------------------------------

function list(value) {
  return Array.isArray(value) ? value : [];
}

/** A stable identity for one parameter set. Order-insensitive: the same request twice.
 *
 * This is what makes a measurement a fact about (operation, parameters) rather than about the
 * operation alone. `_count_chain_replay`'s `detail` does not name the rule it measured, so a
 * count carried onto a different parameter is invisible to the operator — the number and the
 * whole server sentence are wrong for what runs, and nothing on the dialog says so.
 */
export function paramsKey(entries) {
  return list(entries)
    .map((entry) => `${entry.key}=${entry.value}`)
    .sort()
    .join('\0');
}

/** The cached count, and whether it still belongs to what is in the inputs right now.
 *
 * ONE function answers this, and both the row and the buttons and the confirmation call it, so
 * they cannot disagree about whether the number on screen is about the request about to be sent.
 */
export function resolveCount(record, operation) {
  const count = (record && record.count) || null;
  if (!count) return { count: null, stale: false };
  const stale = count.paramsKey !== paramsKey(paramEntries(record, operation));
  return { count, stale };
}

/** The parameters as `[{key, value}]`, EMPTY VALUES DROPPED and undeclared keys impossible.
 *
 * The entries are derived from what the inventory declares, not from whatever the map happens to
 * hold: a server restart that renames or removes a parameter would otherwise leave the old key in
 * the map, and `main.py`'s count route rejects unknown parameter names with a 400 about a field
 * that is no longer on screen.
 */
export function paramEntries(record, operation) {
  const stored = (record && record.params) || {};
  const declared = operation ? list(operation.params).map((p) => p.key) : Object.keys(stored);
  return declared
    .map((key) => ({ key, value: String(stored[key] == null ? '' : stored[key]).trim() }))
    .filter((entry) => entry.value !== '');
}

function text(value) {
  return value === null || value === undefined || value === '' ? null : srv(value);
}

function integer(value) {
  return Number.isInteger(value) ? count(value) : null;
}

/** How dangerous this operation is to press, as a COLOUR — never as a sentence.
 *
 * `deletes` and `restartable` exist in the payload because one confirmation wording cannot fit
 * five buttons: four add or overwrite and resume from an interruption, and `graph_orphans` deletes
 * and rolls the whole run back. This function reads those two flags for a border colour. The words
 * that explain them are `deletes` and `commit_granularity`, rendered verbatim next to the button.
 */
function operationTone(spec) {
  if (spec && spec.restartable === false) return 'danger';
  if (spec && spec.deletes) return 'warn';
  return '';
}

/** The per-operation facts that are the same in the inventory and in a count response.
 *  Built once so the two surfaces cannot disagree about what an operation deletes. */
function buildFacts(spec) {
  return {
    deletesLabel: chrome(RETRO_CHROME.DELETES),
    deletes: text(spec && spec.deletes),
    commitLabel: chrome(RETRO_CHROME.COMMIT),
    commit: text(spec && spec.commit_granularity),
    tone: operationTone(spec),
  };
}

function buildParam(param) {
  return {
    // The routing key. Not a text carrier: it goes into a query string, not onto the screen.
    key: param && param.name != null ? String(param.name) : '',
    name: text(param && param.name),
    help: text(param && param.help),
    required: Boolean(param && param.required),
    requiredLabel: chrome(RETRO_CHROME.REQUIRED),
    // 🔴 «닫힌 집합»을 가진 파라미터는 선언이 그 집합을 실어 보냅니다. 없으면 «자유 문자열»이고
    //    입력칸 그대로입니다 — 여기에 «대체 목록을 들지 않습니다». 그것이 이 필드가 생긴 이유고,
    //    들고 있으면 선언이 늘어난 날 화면이 옛 목록을 그립니다.
    //    label 과 when 은 선언의 것을 «그대로» 옮깁니다: 화면이 문구를 지으면
    //    페이스가 넷이 되는 날 그 넷째 문구를 또 이 파일에 적게 됩니다.
    choices: Array.isArray(param && param.choices) && param.choices.length
      ? param.choices.map((choice) => ({
        value: choice && choice.value != null ? String(choice.value) : '',
        label: text(choice && choice.label),
        when: text(choice && choice.when),
      })).filter((choice) => choice.value !== '')
      : null,
  };
}

function buildOperation(spec) {
  const facts = buildFacts(spec);
  return {
    // Routing key, not text: it is the `{op}` path segment.
    op: spec && spec.op != null ? String(spec.op) : '',
    // 🔴 선언의 낱말을 그대로 나릅니다 — 진행 목록의 × 가 이 값으로만 그려집니다.
    //    안 나르면 그 목록이 «어느 줄에도» × 를 안 그리고, 화면은 조용히 「못 멈춥」니다
    //    (실측 2026-08-31: 제가 그 상태로 한 번 그렸습니다).
    cancellable: (spec && spec.cancellable) === true,
    label: text(spec && spec.label),
    // WHY the operation exists, in the server's words. This is the sentence that makes the button
    // legible; without it a row is five verbs with no referent.
    whatIsMissing: text(spec && spec.what_is_missing),
    paramsLabel: chrome(RETRO_CHROME.PARAMS),
    params: list(spec && spec.params).map(buildParam),
    ...facts,
    cliLabel: chrome(RETRO_CHROME.CLI),
    cli: text(spec && spec.cli),
    // Carried deliberately by the server: the buttons cover the common shape of each operation and
    // the CLI still covers the rest. A surface that hid this would read as "these five buttons are
    // everything", which is the claim `retroactive.inventory()` explicitly refuses to make.
    cliOnlyLabel: chrome(RETRO_CHROME.CLI_ONLY),
    cliOnly: list(spec && spec.cli_only).map(srv),
    countLabel: chrome(RETRO_CHROME.COUNT),
    runLabel: chrome(RETRO_CHROME.RUN),
  };
}

/** `GET /admin/retroactive/operations` — the inventory. Config only; no count is taken. */
export function buildOperationsView(payload) {
  const operations = list(payload && payload.operations);
  return {
    headlineLabel: chrome(RETRO_CHROME.HEADLINE),
    hint: chrome(RETRO_CHROME.HINT),
    operationsLabel: chrome(RETRO_CHROME.OPERATIONS),
    total: count(operations.length),
    // The headline names the operations rather than summarising them: there is no "problem" state
    // to summarise here, and a fabricated verdict on a toolbox is worse than a list.
    titles: operations.map((spec) => text(spec && spec.label)).filter(Boolean),
    operations: operations.map(buildOperation),
    empty: operations.length === 0,
    emptyText: chrome(RETRO_CHROME.NO_OPERATIONS),
  };
}

/** Labelled numbers inside `extra`, found by the SERVER'S OWN labelling, not by a key list here.
 *
 * `_count_chain_replay` ships `withdrawal_candidates` next to `withdrawal_candidates_label`
 * precisely so a second number can be shown without being added into `affected` — R1 never writes
 * a blank, and a surface that summed the two would overstate the writing operation with the count
 * of the one thing it deliberately will not do.
 *
 * So the rule is: a number in `extra` is shown IF AND ONLY IF the server labelled it. Which
 * numbers reach the operator is then the server's decision, made in the payload, and adding one
 * later needs no client change. Every other value in `extra` is already inside `detail`, and a
 * second rendering of the same fact is a second chance to disagree with it.
 */
function buildExtras(extra) {
  const source = (extra && typeof extra === 'object') ? extra : {};
  // The SERVER'S OWN ORDER, not ASCII order of its internal key names. `JSON.parse` preserves
  // document order for string keys, so iterating without sorting is the server's decision about
  // sequence — which is the same principle as its decision about which numbers appear at all.
  // Sorting made `pinned` precede `withdrawal_candidates` for no reason anybody chose.
  return Object.keys(source)
    .filter((key) => !key.endsWith('_label'))
    .map((key) => ({ key, label: text(source[`${key}_label`]), value: integer(source[key]) }))
    .filter((pair) => pair.label && pair.value)
    .map((pair) => ({ label: pair.label, count: pair.value }));
}

/** `GET /admin/retroactive/{op}/count` — one measurement, and what kind of number it is.
 *
 * 🔴 THE NUMBER TRAVELS WITH ITS LABEL OR IT DOES NOT TRAVEL. `affected` is emitted only when
 * `affected_label` is present, because the qualifier for four of the five counts lives IN that
 * label ("회수할 셀 (최대)"). Rendering the integer alone would strip the one word that keeps the
 * screen honest, and `detail` — which always carries the number in a sentence — is still there.
 */
export function buildCountView(payload) {
  const data = payload || {};
  const kind = data.count_kind == null ? null : String(data.count_kind);
  const affectedLabel = text(data.affected_label);
  return {
    label: text(data.label),
    affectedLabel,
    affected: affectedLabel ? integer(data.affected) : null,
    // The server's own word for "what kind of number is this". Rendered as vocabulary, the way
    // the population names are on the config report — not translated, not re-judged.
    kindLabel: chrome(RETRO_CHROME.KIND),
    kind: text(kind),
    kindTone: (kind && Object.prototype.hasOwnProperty.call(KIND_TONE, kind))
      ? KIND_TONE[kind] : '',
    // THE sentence. Straight through, untouched.
    detail: text(data.detail),
    // A second server sentence, on the two counts whose cheap query answered a superset. It names
    // the gap between the ceiling and the answer, which `detail` states but does not explain.
    why: text(data.extra && data.extra.why_upper_bound),
    extras: buildExtras(data.extra),
    // `truncated` means the scan budget ran out before the population did, i.e. the sample number
    // is a floor. The server does not (yet) put that in words on this route (its sibling dry-run
    // route appends a sentence), and this file will not compose the missing one. What it does do
    // is stop letting a BORDER COLOUR be the only carrier: the fact travels as a slot name plus
    // the payload value spelled in JSON, so it survives into the plain-text confirmation too.
    truncated: Boolean(data.truncated),
    truncatedLabel: typeof data.truncated === 'boolean' ? chrome(RETRO_CHROME.TRUNCATED) : null,
    truncatedValue: typeof data.truncated === 'boolean' ? val(data.truncated) : null,
    // The knob state travels separately from the count so the button can be disabled rather than
    // letting the operator discover the refusal by pressing it. The reason WORD is rendered as
    // data; this file does not know what any particular reason means.
    blockedLabel: chrome(RETRO_CHROME.BLOCKED),
    blocked: text(data.blocked_reason),
    ...buildFacts(data),
  };
}

// ════════════════════════════════════════════════════════════════════════════
// 진행 목록 — 「도는 것들」 한 목록. 줄마다 [무엇] [진행] [ × ] 셋، 다섯째 없음.
//
// 🔴 막대는 «전체를 아는 것»에만. 모르면 «처리한 수 + 경과»를 글자로 말합니다.
//    `total_rows` 가 null 로 오는 것은 「0」이 아니라 「모름」입니다 — 서버가 그렇게 적어
//    보냅니다. 0 으로 채우면 화면이 「할 일 없음」과 0% 를 그리고, 그게 거짓입니다.
//
// 🔴 × 는 «모두에게» 나오지 않습니다. 배치 경계가 없는 연산은 요청을 세워도 볼 자리가
//    없어서, 그려 두면 «누릅도 안 멈췐» 또는 «죽은 버튼»이 됩니다. 연산 선언의
//    `cancellable` 이 그걸 말하고, 이 파일은 그 낱말을 «읽기만» 합니다.
//
// 🔴 취소를 누르면 줄이 «안 사라집니다». 즉시 지우면 「언제 실제로 멈컴는가」를
//    운영자가 못 보고, «요청했다»와 «멈컴다»를 같은 것으로 읽게 됩니다.
// ════════════════════════════════════════════════════════════════════════════

// 🔴 서버가 «선언한» 낱말 그대로입니다 (`server/retroactive.py`: RUN_QUEUED · RUN_RUNNING ·
//    RUN_DONE · RUN_CANCEL_REQUESTED · RUN_CANCELLED · RUN_FAILED). 앞 판본은 여기에
//    `succeeded` 라고 적었는데, 그건 이 서버에 «없는 낱말»입니다 -- 즉 그 거르개는 아무것도
//    거르지 않았고, 실행 행이 0 인 동안은 그 사실이 «안 보였습니다». 끝난 작업이 「Running」에
//    세어지고 그 줄에 죽은 × 가 달린 것이 그 결과입니다.
const RUN_FINISHED = ['done', 'cancelled', 'failed'];
// 끝난 것도 «몇 개는» 남깁니다 -- 방금 끝난 것이 목록에서 즉시 사라지면 「돌긴 했나」를
// 화면이 못 답합니다. 세지는 않고, × 도 안 답니다.
const RECENT_FINISHED_SHOWN = 3;

/** 몇 분째인가. 시각이 없으면 «null» — 0 분으로 적으면 「방금 시작」으로 읽힙니다. */
export function elapsedMinutes(startedAt, now) {
  if (!startedAt) return null;
  const start = Date.parse(startedAt);
  if (Number.isNaN(start)) return null;
  const ms = (typeof now === 'number' ? now : Date.now()) - start;
  return ms < 0 ? 0 : Math.floor(ms / 60000);
}

/** 진행 칸 하나. 막대는 «전체를 아는 때만»이고, 모르면 수와 경과를 글자로. */
export function buildProgressCell(processed, total, minutes) {
  const done = Number.isFinite(processed) ? Number(processed) : null;
  const all = Number.isFinite(total) && Number(total) > 0 ? Number(total) : null;
  const elapsed = Number.isFinite(minutes) ? `${minutes}m` : null;
  if (all !== null && done !== null) {
    const percent = Math.max(0, Math.min(100, Math.round((done / all) * 100)));
    return { mode: 'bar', percent, processed: done, total: all, elapsedMinutes: minutes,
             text: `${done.toLocaleString()} / ${all.toLocaleString()}`,
             elapsed };
  }
  // 🔴 가짜 % 를 안 그립니다. 이 연산들은 행이 떨어질 때까지 걷기 때문에
  //    시작 시점에 전체를 «알 수 없습니다». 모르는 것을 그리지 않고 «아는 것»만 적습니다.
  return { mode: 'text', percent: null, processed: done, total: null, elapsedMinutes: minutes,
           // 🔴 말을 적지 않습니다 (소유자 2026-08-31: 「하나하나 쓰지 말고 색으로」).
           // 수만 내고, «전체를 모른다»는 사실은 막대의 «색과 모양»이 말합니다.
           text: done === null ? '—' : done.toLocaleString(),
           elapsed };
}

/**
 * 「도는 것들」 한 목록 — 요청형(소급 실행)과 상시형(파일 인제션)을 «같이».
 *
 * 🔴 사용자에겐 그냥 「도는 것들」입니다. 두 출처를 두 목록으로 나누면 «어느 목록을
 *    봐야 하나»가 생기고, 그건 「하나만 끊기」라는 이 화면의 목적과 반대입니다.
 *
 * @param payload  `{ runs, ingestions }` — 둘 다 없을 수 있고, 그때는 «빈 목록»입니다
 * @param cancellable  `op -> boolean`. 연산 선언이 말하는 것을 그대로 받습니다
 */
export function buildRunsView(payload, now, cancellable) {
  const data = payload || {};
  const canCancel = cancellable || {};
  const rows = [];
  const done = [];

  for (const run of Array.isArray(data.runs) ? data.runs : []) {
    if (!run) continue;
    const state = String(run.state || '');
    // 🔴 «모르는» 낱말은 도는 것으로 봅니다. 반대로 두면 서버가 상태를 하나 늘리는 날
    //    도는 작업이 화면에서 조용히 사라지고, 이 화면은 그걸 못 보여 주면 존재 이유가 없습니다.
    //    대신 모르는 것에는 × 를 안 답니다 (아래 `cancel`) -- 죽은 버튼보다 낫습니다.
    const finished = RUN_FINISHED.indexOf(state) !== -1;
    // 🔴 끝난 작업의 시계는 «멈춥니다». 지금 시각으로 재면 그 수가 계속 자라고, 어제 끝난
    //    작업이 「1,000분째」로 보입니다 -- 이 화면에서 시간은 「얼마나 오래 물고 있나」라서
    //    그 수는 곧 판단입니다. 끝났으면 «걸린 시간»을 말합니다.
    const stopped = finished ? Date.parse(run.finished_at || '') : NaN;
    const clock = Number.isFinite(stopped) ? stopped : now;
    const minutes = elapsedMinutes(run.started_at || run.queued_at, clock);
    (finished ? done : rows).push({
      // 🔴 id 는 «열쇠»이지 화면에 나가는 문장이 아닙니다. 태그를 붙이면 취소가 어느 행을
      //    가리키는지 잃습니다 -- 이 파일의 `text()` 는 출처를 «달아» 객체로 만듭니다.
      id: String(run.run_id || ''),
      kind: 'run',
      what: text(run.label) || text(run.op),
      detail: text(Object.values(run.params || {}).join(' · ')),
      progress: buildProgressCell(run.processed_rows, run.total_rows, minutes),
      // 🔴 멈출 수 없는 연산에는 × 를 안 그립니다 — 누르면 아무 일도 안 일어나는
      //    버튼은 화면이 하는 거짓말입니다. 선언이 모르는 연산도 그리지 않습니다.
      // 끝난 작업에는 «절대» 안 답니다. 눌러도 아무 일이 안 나거나 더 나쁜 일이 납니다.
      cancel: !finished && canCancel[run.op] === true,
      // 요청했지만 아직 멈추지 않았다 — 줄은 «남아있습니다».
      stopping: state === 'cancelling' || state === 'cancel_requested',
      // 🔴 «기다리는 것»은 도는 것이 아닙니다. 큐에 앉은 실행은 서버를 안 무겁게 하는데,
      //    흐르는 막대를 그리면 도는 것과 «똑같이» 보입니다 — 그러면 이 화면의 목적
      //    (「무엇을 끊어야 서버가 가벼워지나」)이 그 줄에서 거짓말을 합니다.
      moving: !finished && state !== 'queued',
      finished,
      state,
    });
  }

  for (const job of Array.isArray(data.ingestions) ? data.ingestions : []) {
    if (!job) continue;
    const minutes = Number.isFinite(job.elapsed_seconds)
      ? Math.floor(Number(job.elapsed_seconds) / 60) : null;
    rows.push({
      id: `ingest:${String(job.table_name || '')}:${String(job.filename || '')}`,
      kind: 'ingestion',
      what: text(job.filename),
      detail: text(job.table_name),
      progress: buildProgressCell(job.processed_rows, job.total_rows, minutes),
      // 파일 인제션은 이 라우트가 취소를 안 받습니다. 그러니 × 를 안 그립니다.
      cancel: false,
      stopping: false,
      // QUEUED 는 heavy 레인 대기열에 앉아 있는 것입니다 — 선언이 그 대기를 «정상»이라
      // 부르고 TTL 도 24시간입니다. 그 줄이 도는 것처럼 보이면 안 됩니다.
      moving: String(job.status || '') === 'PROCESSING',
      // 이 레지스트리는 «도는 것만» 들고 있습니다 (FINISHED 는 지워집니다).
      finished: false,
      state: text(job.status),
    });
  }

  // 끝난 것은 «아래»에, 그리고 몇 개만. 서버가 최근 것부터 주므로 순서는 그대로입니다.
  const recent = done.slice(0, RECENT_FINISHED_SHOWN);
  return {
    rows: rows.concat(recent),
    // 🔴 「몇 개가 도나」는 «도는 것»만 셉니다. 끝난 줄을 같이 세면 접힌 줄 하나로
    //    판단하는 이 화면이 「지금 하나 돌고 있다」고 거짓을 말합니다.
    liveCount: rows.length,
    // «비었다»는 사실이고, 한 줄로 말합니다. 빈 표를 그리면 「못 읽었다」처럼 보입니다.
    empty: rows.length + recent.length === 0,
  };
}

/** `POST /admin/retroactive/{op}/run` — the acknowledgement.
 *
 * The route publishes an outbox row and returns; it does not execute. Its response carries no
 * operator-facing sentence (only `status`, `run_id`, `op`, `params`, `label`), so the confirmation
 * text here is CHROME plus the server's `run_id` — the one fact worth keeping, because it is what
 * the scheduler log is keyed by.
 */
export function buildRunView(payload) {
  const data = payload || {};
  const params = (data.params && typeof data.params === 'object') ? data.params : {};
  return {
    queuedLabel: chrome(RETRO_CHROME.QUEUED),
    label: text(data.label),
    statusWord: text(data.status),
    runIdLabel: chrome(RETRO_CHROME.RUN_ID),
    runId: text(data.run_id),
    // 🔴 WHAT WAS QUEUED, from the server's echo — not from what the client believes it sent.
    // Dropping this was how the acknowledgement managed to say a run happened without saying what
    // ran, which is exactly the fact that makes a carried-over measurement visible.
    paramsLabel: chrome(RETRO_CHROME.PARAMS_ECHO),
    params: Object.keys(params).map((key) => ({
      name: srv(key),
      // A list parameter (`columns`) arrives as an array. Its ELEMENTS are payload strings; a
      // joined string is not, so each one is carried separately and the join is presentation.
      values: (Array.isArray(params[key]) ? params[key] : [params[key]]).map((v) => srv(String(v))),
    })),
  };
}

/** The two buttons' state, as a PURE FUNCTION OF THE RECORD.
 *
 * 🔴 THIS EXISTS BECAUSE A REBUILD MUST NOT BE ABLE TO FORGET WHAT THE ROW WAS DOING. The write
 * button's in-flight state used to live only in the DOM node — so any code path that rebuilt the
 * actions row (the count's `finally` did, unconditionally) constructed a fresh, ENABLED write
 * button while a POST was still queuing. A second press then wrote a second `RETROACTIVE_RUN` row,
 * and because both responses wiped the same host, only the second `run_id` was ever displayed:
 * one intent, two runs, one of them invisible.
 *
 * Deriving both buttons from the record makes that unreachable by construction rather than by
 * remembering to restore a flag at every rebuild site.
 */
/** 인라인 확인의 두 버튼. 클라가 쓰는 문자열은 전부 «얼어붙은 표»에서 오며,
 *  그래야 같은 말이 두 자리에서 다르게 적힐 수 없습니다. 확인의 «문장»은 여기가 아니라
 *  `buildConfirmLines` 의 마지막 줄입니다 -- 버튼은 동사만 듭니다. */
export function buildConfirmActions() {
  return { go: chrome(RETRO_CHROME.RUN), cancel: chrome(RETRO_CHROME.CANCEL) };
}

export function buildActionsView(operation, record) {
  const resolved = resolveCount(record, operation);
  // A STALE count bars nothing: its refusal was measured for parameters that are no longer the
  // ones in the inputs, and carrying that block forward is the same defect as carrying the number.
  const view = resolved.count && resolved.count.ok && !resolved.stale ? resolved.count.view : null;
  const blocked = view && view.blocked ? view : null;
  const busy = (record && record.busy) || null;
  return {
    count: {
      label: chrome(busy === 'count' ? RETRO_CHROME.COUNTING : RETRO_CHROME.COUNT),
      // Both buttons write into the same host and the same record, so ONE busy state governs the
      // row. Letting them interleave is precisely what allowed a returning count to re-arm a write
      // that had not finished.
      disabled: busy !== null,
    },
    run: {
      label: chrome(busy === 'run' ? RETRO_CHROME.RUNNING : RETRO_CHROME.RUN),
      disabled: busy !== null || Boolean(blocked),
      // The knob state travels separately from the count so the button can be barred rather than
      // letting the operator discover the refusal by pressing it.
      blockedLabel: blocked ? blocked.blockedLabel : null,
      blocked: blocked ? blocked.blocked : null,
    },
  };
}

/** The one-shot confirmation, as an ORDERED LIST OF LINES rather than a composed string.
 *
 * Returned as data so the harness can score every line's provenance. Two roles of client-authored
 * line exist and they are NOT the same thing:
 *
 *   `role: 'label'`     a slot name ("삭제 대상"). It must be followed by the value that fills it,
 *                       or it is a label that says nothing — so the harness requires exactly that.
 *   `role: 'question'`  🔴 EXACTLY ONE, and it is the last line. This is the only sentence on the
 *                       dialog the client wrote. Everything above it is a string the server sent
 *                       or the operator's own input read back to them.
 *
 * A confirmation that paraphrased the danger would be the client deciding what the danger is —
 * and of these five, one deletes an entity and rolls a whole interrupted run back while the other
 * four add or overwrite and resume. One wording cannot be true of both.
 *
 * @param {object} operation a `buildOperationsView().operations[n]`
 * @param {object|null} record the per-operation record. The count is taken from it THROUGH
 *   `resolveCount`, never passed in bare, so there is no way to hand this function a measurement
 *   that does not belong to the parameters being submitted.
 * @param {Array<{key: string, value: string}>} params what the operator typed
 */
export function buildConfirmLines(operation, record, params) {
  const resolved = resolveCount(record, operation);
  // 🔴 A STALE COUNT CANNOT REACH THIS DIALOG. It is dropped here, in the view model, rather than
  // being filtered at the call site — the whole point of taking the record instead of a bare view
  // is that there is no argument shape that smuggles a mismatched measurement in.
  const countView = resolved.count && resolved.count.ok && !resolved.stale
    ? resolved.count.view : null;
  const lines = [];
  const pair = (label, value) => {
    if (!value) return;
    if (label) lines.push({ ...label, role: 'label' });
    lines.push(value);
  };
  pair(null, operation && operation.label);
  list(params).forEach((entry) => {
    // The operator's own input, echoed so the single confirmation shows what is about to run.
    // Tagged `input` — neither a server sentence nor a client label, and the harness scores it as
    // "must contain exactly what was passed in".
    lines.push({ src: 'input', text: `${entry.key} = ${entry.value}`, raw: entry.value });
  });
  if (countView) {
    pair(countView.affectedLabel, countView.affected);
    // 🔴 EVERY CARRIER THE ROW HAS, THE DIALOG HAS. The row shows the qualifier four ways — the
    // label text, the `count_kind` chip, the `truncated` border, the `why_upper_bound` sentence —
    // and the dialog is plain text, so no colour can reach it. Three of the five `affected_label`s
    // carry no qualifier of their own, which left the dialog's honesty resting on `detail` alone.
    pair(countView.kindLabel, countView.kind);
    pair(countView.truncatedLabel, countView.truncatedValue);
    pair(null, countView.detail);
    pair(null, countView.why);
    list(countView.extras).forEach((extra) => pair(extra.label, extra.count));
  }
  // The facts come from the count when one was taken and from the inventory otherwise. They are
  // byte-identical in the two payloads (`retroactive.count` copies them off the same spec), so
  // pressing run without measuring first loses the number, never the warning.
  const facts = countView || operation;
  pair(facts && facts.deletesLabel, facts && facts.deletes);
  pair(facts && facts.commitLabel, facts && facts.commit);
  lines.push({ ...chrome(RETRO_CHROME.CONFIRM_QUESTION), role: 'question' });
  return lines;
}
