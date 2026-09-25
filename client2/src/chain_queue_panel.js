// CHAIN QUEUE INSTRUMENT — turns 「체인 요청이 몇 개 씹히는 것 같다」 into numbers.
//
// Reads `GET /admin/chain/queue` and draws it. READ ONLY: there is no cancel, no retry, no
// reordering here, and there must not be. The queue's own worker owns the queue; a screen that
// could reorder it would be a second writer.
//
// ═══ THE THREE RULES THIS FILE EXISTS TO KEEP ═══════════════════════════════════════════
//
// ① `null` IS NOT `0`. An empty queue answers `oldest_waiting_seconds: null`; a queue that
//    just received something answers `0`. They are different facts and they get different
//    pixels. If they rendered the same, this instrument would reproduce the exact ambiguity
//    it was built to remove.
//
// ② A NUMBER THAT CANNOT BE READ HAS NO CELL. A blind cell (a count this screen cannot see)
//    is dropped, not drawn as 0 — the four numbers become three or two. `not_measured`
//    (`retried_total`, `processed_recently`) is NOT drawn since mockup A: the screen has no
//    slot for those numbers, so nothing reads as their zero (lead 6fdd79d4e).
//
// ③ NO INVENTED THRESHOLD. There is no operational basis in this repository for "60 seconds
//    is late", and a colour applied on a made-up number is a domain claim this file is not
//    entitled to make. The route's own docstring says what decides it: 「계속 자라면 실제로
//    안 나가는 것이고, 0 근처를 오가면 큐는 흐르고 있다」 — that is a comparison ACROSS
//    refreshes, not a property of one sample. So the age is stated and no colour pretends to
//    have judged it. The one coloured cell is Failed, and only when it is not 0.
//
// ④ THE LIST IS CUT, AND THE CUT IS SAID. The route reads at most `listed.cap` rows, so
//    a short list can mean 「this is all of it」 or 「this is as far as I looked」. Those are
//    different facts, and a silently truncated list reads as the whole queue — the same
//    class of misreading as ② one layer out. When `listed.capped`, the screen says so.
//
// ═══ SHAPE — mockup A (owner 「A 로 해」, lead 3c3f2b1f2 · 437a5d25f · 6fdd79d4e) ═══════════
//    stale line (only when the picker's records failed — it must be read BEFORE the numbers)
//    four numbers   Waiting · Oldest · Running · Failed since <date>
//    the list       Transaction · Waiting · Tables · Rows · Drained by (+ 「retry N」 when not 0)
//    meta line      retried · Log · Loop · Mapper · As of
//    below it       the lines that appear only when something needs a look, the scheduler's
//                   three pickup lines, and the per-owner lines when there are two or more
//    The section head (「Queue · … · Open Chain tab ›」) is the PAGE's, not this part's —
//    inside the Chain tab that link would point at itself.
//
// The view model is pure and total (`queueView`), so a harness scores it by importing it.
// The class owns exactly one div, takes its mount in the constructor, and holds no
// module-level state — two of these can sit on one page without touching each other.
// The table reuses `admin.html`'s existing `.table-container` / `.table-header` /
//    `.table-row` styles — a diagnostic panel is not a reason to grow a second table style.

import { ABSENT, UNKNOWN, countText, isCount } from './absent.js';
import { FAILED, NONE, WAITING, unitText } from './ui_words.js';
import { countWithAbsence } from './count_with_absence.js';
import { pickupState } from './pickup_state.js';
import { retroactiveNote } from './retroactive_note.js';
import { NO_TIME, localShort, localStamp } from './server_time.js';
import { RunLines } from './run_lines.js';
import { buildProgressCell } from './retroactive_view.js';

// 🔴 총괄 8e331ca17 — each item carries `state` (running · orphaned · unknown), the server's one
//    judgment (utils/heartbeat.runner_state). The ONE place this file asks it: the count, the
//    longest and a line's motion all go through `isRunningItem`. An item without the key is an
//    older server's, whose every item was running — it stays counted.
const STATE_RUNNING = 'running';
export const isRunningItem = (item) => !item || !('state' in item) || item.state === STATE_RUNNING;

/**
 * One `now_running` item -> a `RunLines` row. `where` and `state` are the server's words, drawn
 * as they come (5996d7f54: the screen never branches on `where`); `cancel` null means no ×.
 * A line whose owner is gone does not move — it must not draw like a running one.
 */
export function runLineRow(item) {
  const r = item || {};
  const secs = Number(r.elapsed_seconds);
  const known = r.elapsed_seconds !== null && r.elapsed_seconds !== undefined && Number.isFinite(secs) && secs >= 0;
  const p = r.progress || {};
  const cell = buildProgressCell(p.processed, p.total, known ? Math.floor(secs / 60) : NaN);
  const where = [r.where, r.pid != null ? `pid ${r.pid}` : ''].filter(Boolean).join(' · ');
  const runId = r.cancel && r.cancel.run_id ? String(r.cancel.run_id) : '';
  return Object.freeze({
    id: runId || `${r.where || ''}:${r.what || ''}`,
    what: { text: r.what ? String(r.what) : ABSENT },
    detail: where ? { text: where } : null,
    progress: { ...cell, elapsed: known ? formatAge(secs) : '' },
    stateName: r.state ? { text: String(r.state) } : null,
    cancel: Boolean(runId),
    moving: isRunningItem(r),
    finished: false,
    stopping: false,
  });
}

// 🔴 THE MINUTE IS ONE CONSTANT, READ FROM TWO PLACES. `formatAge` switches off 「초」
//    here, and C-61 lists a running chain 「나이가 분 단위를 넘으면」 — the SAME question.
//    Written as two literals they can be edited apart, and the day they are, the panel
//    lists an item whose age it still draws in seconds.
export const MINUTE_SECONDS = 60;

/**
 * Seconds -> a duration a person reads at a glance. Total: a non-finite input is `null`,
 * never `NaN초`.
 *
 * The unit pair stops at two on purpose ("1시간 5분", not "1시간 5분 3초"): the third unit is
 * never the reason anyone looks at this panel, and it makes the number wider than the label.
 */
/** 클래스 하나 붙인 div. 두 대기열 판이 «같은» 것을 쓴다 — 사본이 둘이면 둘이 갈라진다. */
export function line(doc, cls, text) {
  const el = doc.createElement('div');
  el.className = cls;
  el.textContent = text;
  return el;
}

export function formatAge(seconds) {
  // 🔴 `Number(null) === 0`, and so is `Number('')`. Without this line an ABSENCE formats
  //    as 「0초」 — the same collapse rule ① exists to prevent, one layer down. `queueView`
  //    happens to check for null before calling here, but this function is exported and the
  //    next caller will not know to.
  if (seconds === null || seconds === undefined || seconds === '') return null;
  const n = Number(seconds);
  if (!Number.isFinite(n) || n < 0) return null;
  const s = Math.floor(n);
  if (s < MINUTE_SECONDS) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

// 🔴 `countOf` LIVED HERE UNTIL 2026-09-04 and it had this bug: `Number('') === 0` and
//    `''` is neither null nor undefined, so an empty string rendered as 「0」. The same
//    collapse `formatAge` guards against, in the function beside it. It moved to `absent.js`
//    with that hole closed, because this round needed the SAME spelling in five more files
//    and six private copies drift silently.
const countOf = countText;

/**
 * `blocked_by` → what to draw, or null. EVERY FIELD IS THE SERVER'S OWN VALUE.
 *
 * 🔴 NOTHING IS TRANSLATED HERE. `moving` is `progressing`/`stalled`/`unreported` and
 *    `cancel_reaches` is `at_next_batch`/`unknown`/`never`; those are the server's words for
 *    states it distinguishes deliberately (`unreported` is NOT `stalled` — four of six
 *    operations report progress and two never do, so "no progress since the start" is all
 *    that is known). Rewriting them into 「멈춤」/「안 닿음」 would fold that apart-ness
 *    back together and would be this screen asserting something the server did not say.
 *    The recovery sentence is the server's too, and is carried verbatim.
 */
/** 「<요청자> 가 <큐 시각> 에 <연산> 을 <인자> 에 걸었습니다」 — 한 줄, 값만. */
function whyLine(b) {
  const who = b.requested_by ? String(b.requested_by) : UNKNOWN;
  const when = b.queued_at ? String(b.queued_at) : UNKNOWN;
  const op = b.op == null ? '' : String(b.op);
  const params = (b.params && typeof b.params === 'object' && !Array.isArray(b.params))
    ? b.params : null;
  // ⛔ 값은 «안 나갑니다». 키는 «선언 순서» 그대로이고, 배열이면 개수를 셉니다.
  const args = params
    ? (Object.keys(params).length
      ? Object.keys(params).map(k => {
        const v = params[k];
        return Array.isArray(v) ? `${k}: ${v.length}` : k;
      }).join(' · ')
      : NONE)
    : NONE;
  return `${who} ran ${op} on ${args} at ${when}`;
}

function blockedView(b) {
  if (!b || typeof b !== 'object') return null;
  return Object.freeze({
    runId: String(b.run_id == null ? '' : b.run_id),
    op: String(b.op == null ? '' : b.op),
    state: String(b.state == null ? '' : b.state),
    moving: String(b.moving == null ? '' : b.moving),
    cancelReaches: String(b.cancel_reaches == null ? '' : b.cancel_reaches),
    // rule ① again: `null` here means the run never reported, which is not 「0초」.
    noProgress: formatAge(b.no_progress_seconds) ?? '—',
    stallAfter: formatAge(b.stall_after_seconds) ?? '—',
    processed: countOf(b.processed_rows),
    total: countOf(b.total_rows),
    recovery: b.recovery ? String(b.recovery) : '',
    // 🔴 「왜 도는지」. 서버가 셋을 «날것»으로 냅니다 — 요청자 · 큐 시각 · 인자.
    //    문장은 화면 몫이고(서버가 안 짓습니다), 「한 줄」입니다.
    //    ⚠️ 요청자가 없으면 «모름»입니다. 서버가 `null` 을 보내고, 이름을 지어내지
    //       않는 것이 이 도구의 규율입니다 — 「없음」도 답입니다.
    //    🔴 인자는 «키와 개수»만입니다. 값이 운영 데이터를 담을 수 있어서,
    //       무엇이 걸렸는지는 알 수 있고 «내용은 안 나갑니다». 보안 조건입니다.
    why: whyLine(b),
  });
}

/** head8… — the same abbreviation the failed-transaction table beside this one uses. */
function shortTx(id) {
  const t = String(id ?? '');
  return t.length > 9 ? `${t.slice(0, 8)}…` : t;
}

/**
 * `/admin/outbox/failed` 응답 -> 실패 수와 «언제부터». 못 읽음 · 0 · N(그 시각부터) 을 가르는
 * 자리는 여기 «하나» — 대기열의 Failed 칸과 Overview 의 Chain 카드가 같이 부릅니다.
 * ⚠️ `total` 이 수가 아니면 «못 읽음»입니다. `|| 0` 으로 채우면 없는 수가 「실패 없음」이 됩니다.
 */
export function failedSince(outbox) {
  // 🔴 총괄 e573a6edf — the rows the summary counts, when the answer carries it: the Overview's Chain
  //    line and the failure section read the same answer. `total` (transaction groups) otherwise.
  const lines = outbox && Array.isArray(outbox.summary) ? outbox.summary : null;
  const total = lines ? lines.reduce((n, l) => n + (isCount(l && l.count) ? Number(l.count) : 0), 0)
    : outbox && isCount(outbox.total) ? Number(outbox.total) : null;
  const cell = countWithAbsence(total === null ? { unread: UNKNOWN }
    : { value: total, absence: 'No failures' });
  const at = total > 0 && outbox.oldest_failed_at ? String(outbox.oldest_failed_at) : '';
  const shown = at ? localShort(at) : NO_TIME;
  return Object.freeze({ read: cell.read, total, text: cell.text, word: cell.word,
    since: !at ? '' : (shown === NO_TIME ? at : shown) });
}

/**
 * `payload` -> what to draw. Pure and total.
 *
 * @param {object|null} payload  the route's body, or null
 * @param {{unavailable?: string, failed?: object|null}} [opts]  `unavailable` is a reason the
 *        body could not be had (HTTP status, an older server process without this route, a
 *        network failure) — then NO numbers are drawn: a stale or invented zero is worse than an
 *        empty panel. `failed` is the `/admin/outbox/failed` body the page already read.
 */
export function queueView(payload, opts = {}) {
  if (opts.unavailable || !payload || typeof payload !== 'object') {
    return Object.freeze({
      available: false,
      reason: opts.unavailable
        || 'Response unreadable · no numbers drawn',
      numbers: Object.freeze([]),
      meta: Object.freeze([]),
      depth: '—',
      byOwner: Object.freeze([]),
      splitByOwner: false,
      rows: Object.freeze([]),
      truncated: '',
    });
  }

  const secs = payload.oldest_waiting_seconds;
  // ── rule ①: three distinct states, three distinct readings ──
  //   null    nothing is waiting
  //   0       something is waiting and it arrived within this second
  //   n > 0   something has been waiting n
  // 🔴 「대기 0」은 「밀린 것 없음」이 «아닐 수» 있습니다 — 실패한 행은
  //    `processed_chain=true` 라 «큐에서 빠집니다». 그래서 그 수가 «옆에» 서야 합니다.
  //    ⛔ 문장을 늘리지 않습니다. 값 하나이고, 못 읽었으면 «칸째» 안 그립니다 (0 으로도 안 그립니다).
  const failed = failedSince(opts.failed);
  // 🔴 «두 번째 소비자»: 도는 체인 루프. 빈 목록이 「없다」인지 「내가 못 본다」인지는
  //    `loop_seen_via` «하나»가 가릅니다 (총괄 36dff3b6a — `loop_in_this_process` 를 같은 물음에
  //    같이 쓰면 두 칸이 한 물음에 답해 갈라집니다). 못 봤으면 Running 칸째 뺍니다.
  // 🔴 「그래서 어느 «파일»인가」. 화면이 그 이름을 내는 자리가 «0» 이었고, 줄에 붙은
  //    태그는 «이미 맞는 파일을 연 사람»에게만 보입니다 — 열 파일을 고르는 데는 못 씁니다.
  //    서버가 로거에서 «읽어» 이름으로 냅니다 (경로가 아닙니다 — 디스크 구조는 화면 것이 아닙니다).
  //    ⚠️ 세 상태입니다: 이름 · null(«모름») · 키 없음(옛 서버 -> «안 그립니다»).
  //    ⛔ 부품(countWithAbsence)의 자리가 «아닙니다» — 그 부품은 「수 + 그 0 이 무엇인지」이고
  //       이것은 셀 것이 없는 «이름»입니다. 세 상태 규율만 같습니다.
  const logName = !('log_filename' in payload) ? ''
    : (typeof payload.log_filename === 'string' && payload.log_filename
      ? payload.log_filename : UNKNOWN);
  // 🔴 S-16: 「재시작하면 풀리나」 — 서버가 «두 수»로 답하는데 읽는 자리가 «0» 이었습니다
  //    (실측: 소스 0 · 번들 0. 발신은 `chain_activity.registry.ages()` 로 «살아 있었습니다»).
  //    그 판단 근거는 이미 이 응답 안에 있었고, 지금까지는 «큐가 1분 이상 막힌 뒤에만»
  //    «로그 문장 속 글자»로 나갔습니다 — 즉 이미 멈춘 시스템의 로그를 읽는 사람만 물을 수
  //    있던 질문입니다.
  // 🔴 「재적재 없음」과 「방금 재적재」는 «반대 사실»입니다. `null` 은 한 번도 안 했다는 뜻이고
  //    `0` 은 방금 했다는 뜻이라, 둘을 같은 글자로 그리면 이 줄이 답하려던 물음이 뒤집힙니다.
  // ⚠️ 세 상태, `logName` 과 «같은 규율»: 값 · `null`(모름/없음) · 키 없음(옛 서버 -> 안 그림).
  const restart = !('loop_uptime_seconds' in payload) && !('mapper_reload_age_seconds' in payload)
    ? ''
    : [
      `Loop ${formatAge(payload.loop_uptime_seconds) ?? UNKNOWN}`,
      payload.mapper_reload_age_seconds === null || payload.mapper_reload_age_seconds === undefined
        ? 'Mapper never reloaded'
        : `Mapper reloaded ${formatAge(payload.mapper_reload_age_seconds) ?? UNKNOWN} ago`,
    ].join(' · ');
  // 🔴 S-20: 「이 수들이 «언제» 것인가」. 서버가 `generated_at` 을 «항상» 보내는데 읽는
  //    자리가 «0» 이었습니다. 새로 고치지 않은 화면은 오래된 수를 «현재형»으로 말하고,
  //    그것이 「같아 보이는 0」 중 「지나가는 중이라서」입니다.
  // 🔵 그 값은 이 응답의 나이·`oldest_waiting_seconds` 와 «같은 순간»입니다 — 서버가
  //    한 번 읽은 `now_utc` 를 셋이 나눠 씁니다. 그래서 이 한 줄이 그 옆의 수들을 «설명»합니다.
  // ⚠️ 세 상태, `logName`·`restart` 와 «같은 규율»: 값 · 못 읽음(모름) · 키 없음(옛 서버 -> 안 그림).
  //    ⛔ 「0」도 「지금」도 지어내지 않습니다 — 옛 서버에서 「방금 잰 수」로 읽히는 것이
  //       이 줄이 막으려는 바로 그것입니다.
  //    시각은 «보는 쪽 zone» 으로 (`server_time.localStamp`) — 못 읽는 문자열은 그대로 냅니다.
  const stamp = typeof payload.generated_at === 'string' && payload.generated_at
    ? localStamp(payload.generated_at) : NO_TIME;
  const generatedAt = !('generated_at' in payload) ? ''
    : (typeof payload.generated_at === 'string' && payload.generated_at
      ? (stamp === NO_TIME ? payload.generated_at : stamp) : UNKNOWN);
  // 🔴 총괄 4994c3afe · 5996d7f54 (소유자 「러닝도 한문으로」) — 「지금 도는 것」 is ONE server seat,
  //    `runtime.running.running_now`: chain rules, retroactive runs, collectors and file ingestion in
  //    one shape. The count, the longest and one line per item all read `now_running`; the old
  //    chain-only `running` is no longer read here. The count still asks `loop_seen_via` ALONE
  //    (lead 36dff3b6a): an unseen chain loop adds nothing to the seat, so its count is blind,
  //    not 0. An older server without the field has no Running cell either.
  //    Only items whose `state` is running are counted and aged (8e331ca17); the others stay lines.
  const nowRunning = Array.isArray(payload.now_running) ? payload.now_running : null;
  const running = payload.loop_seen_via && nowRunning ? nowRunning.filter(isRunningItem).length : null;
  // 🔴 C-61 (소유자 09-10: 「가짜 running 3개 남아있음」). A COUNT CANNOT SEPARATE 「걸린 것」
  //    FROM 「가짜」 — what separates them is AGE, so the longest rides beside the count and
  //    every item's line carries its own elapsed time (`elapsed_seconds`, the seat's).
  // ⚠️ 세 상태 그대로: 나이가 읽히면 값 · 안 읽히면 «안 그림»(0 으로 접지 않습니다 —
  //    「방금 시작함」은 「나이를 모름」의 반대 사실입니다) · 목록이 비면 아무것도 없음.
  const runningItems = nowRunning || [];
  const runningAges = runningItems.filter(isRunningItem)
    .map((r) => Number(r && r.elapsed_seconds))
    .filter((v) => Number.isFinite(v) && v >= 0);
  const longestRunning = runningAges.length ? formatAge(Math.max(...runningAges)) : null;
  // One line per item in the server's order, drawn by the SAME part as the Overview's recent
  // runs (`RunLines`, lead 78ebdcfc0) — what · where · progress · elapsed · × where cancel reaches.
  const runningRows = runningItems.map(runLineRow);
  // rule ①, drawn: nothing waiting is 「—」 and one that arrived this second is 「0s」. An age
  // that does not read is `null` here — a blind cell, dropped (lead 6fdd79d4e: 「Oldest —」).
  const oldest = secs === null || secs === undefined ? ABSENT : formatAge(secs);

  // ── the list. Server order is `id` ascending = longest waiting first; that order IS the
  //    answer, so it is not re-sorted here. ──
  // ── 「누가 이 행을 비우나」 (2026-09-04) ────────────────────────────────
  // 🔴 `unknown` IS NOT `chain`. The server keeps the two apart on purpose, and folding
  //    them here would rebuild the exact misreading that sent someone to inspect a healthy
  //    worker: one undifferentiated number called 「체인 대기열」 while a scheduler run sat
  //    still. The buckets are carried through 1:1, in the server's order, with no arithmetic.
  const buckets = Array.isArray(payload.waiting_by_owner) ? payload.waiting_by_owner : [];
  // 🔴 THE PICKER'S OWN STATE, WHICH THIS PAYLOAD HAS BEEN CARRYING UNREAD. The server
  //    measured why it matters: waits are TWO peaks -- one tick, or unbounded -- so
  //    「how long is the queue」 cannot separate 「about to run」 from 「nothing is picking
  //    up」, and the age of the last pickup can. A short queue with an old pickup is the
  //    state that used to look like an empty one.
  //
  // ⚠️ Drawn only where the server sent the bucket. A deployment with no picker has no
  //    pickup to be unknown about, and 「모름」 on every screen that never had one is noise
  //    standing where a fact should be.
  const withQueue = buckets.find((b) => b && b.queue && typeof b.queue === 'object');
  const pickup = withQueue ? pickupState(withQueue.queue) : null;
  const byOwner = buckets.map(b => Object.freeze({
    owner: String((b && b.owner) == null ? '' : b.owner),
    waiting: countOf(b && b.waiting),
    age: formatAge(b && b.oldest_waiting_seconds) ?? '—',
    eventTypes: Object.freeze(Array.isArray(b && b.event_types) ? b.event_types.map(String) : []),
    blocked: blockedView(b && b.blocked_by),
    // \u{1f534} 「못 읽었다」는 「도는 것이 없다」가 아닙니다. 둘 다 `blocked_by: null` 로 오고,
    //    이 패널은 null 에 «아무것도 안 그립니다» -- 그 선택은 옳지만, 그러면 읽기가 실패한
    //    날에도 화면이 «조용»합니다. 서버가 이제 그 둘을 가르고, 여기서는 후자만 그립니다.
    // ⚠️ 키가 «없으면» 옛 서버입니다 -- 빈 문자열이 되어 아래 갈래를 안 탑니다.
    blockedState: String((b && b.blocked_by_state) == null ? '' : b.blocked_by_state),
  }));
  // 🔴 ONE OWNER IS NOT A SPLIT. Drawing a per-owner breakdown of a single owner adds a
  //    row that says the same thing as the Waiting number, and the reader has to compare two numbers
  //    to learn they are the same number.
  const splitByOwner = byOwner.length > 1;

  const src = Array.isArray(payload.waiting_transactions) ? payload.waiting_transactions : [];
  const rows = src.map(t => Object.freeze({
    txId: String(t.transaction_id ?? ''),
    txShort: shortTx(t.transaction_id),
    rows: countOf(t.rows),
    // 🔴 S-36. A RETROACTIVE ROW SAYS WHAT IT IS, IN THE SLOT THAT SAID 「—」. Its `tables` is
    //    empty by construction (the run is not about one table), so this column was a dash on
    //    exactly the rows an operator most needs to identify — and the answer was already in
    //    the row. Nothing new is drawn for any other row: `retroactiveNote` returns '' when the
    //    key is absent, and this expression then falls through to what it drew yesterday.
    tables: retroactiveNote(t.retroactive)
      || (Array.isArray(t.tables) && t.tables.length ? t.tables.join(', ') : '—'),
    eventTypes: Object.freeze(Array.isArray(t.event_types) ? t.event_types.map(String) : []),
    // rule ①, per row: an unreadable age is a dash, never 「0초」.
    age: formatAge(t.waiting_seconds) ?? '—',
    // 🔴 WHO EMPTIES THIS ROW. The server decides it once, from `event_type`; if the screen
    //    re-decided it from the same field there would be TWO copies of that judgement and they
    //    would drift. A row whose owners the server did not name draws a dash, not 「chain」.
    owners: Object.freeze(Array.isArray(t.owners) ? t.owners.map(String) : []),
    at: t.waiting_at || '',
    // An empty string means zero retries. The badge exists to surface the NON-zero ones,
    // and a 「0」 on every row is noise that hides the one row that is not 0.
    maxRetry: Number(t.max_retry) > 0 ? countOf(t.max_retry) : '',
  }));

  // ── rule ④: a cut list says it was cut ──
  const listed = payload.listed && typeof payload.listed === 'object' ? payload.listed : null;
  const truncated = listed && listed.capped
    ? `Read the first ${unitText(countOf(listed.rows_scanned), 'row')} only (cap ${countOf(listed.cap)}). `
      + 'The list below is not the whole queue.'
    : '';

  // ── the four numbers (A). A cell that cannot be read is DROPPED, not drawn as 0 (rule ②) ──
  const cell = (key, label, value, extra = {}) => Object.freeze({
    key, label, value, sub: '', tone: '', ...extra });
  const numbers = [];
  if (isCount(payload.waiting)) numbers.push(cell('waiting', WAITING, countOf(payload.waiting)));
  if (oldest !== null) numbers.push(cell('oldest', 'Oldest', oldest));
  // 🔴 C-61. 「최장」은 수 «옆»에 붙습니다 — 따로 줄을 만들면 운영자가 수를 먼저 읽고
  //    「3 개 돈다, 정상」으로 판정한 «뒤»에 나이를 봅니다. 나이가 읽히는 것이 하나도
  //    없으면 이 조각은 «안 붙습니다»(0 으로도, 「모름」으로도 지어내지 않습니다).
  if (running !== null) {
    numbers.push(cell('running', 'Running', String(running),
      { sub: longestRunning ? `longest ${longestRunning}` : '' }));
  }
  if (failed.read) {
    numbers.push(cell('failed', failed.since ? `${FAILED} since ${failed.since}` : FAILED,
      String(failed.total), { tone: failed.total > 0 ? 'danger' : '' }));
  }

  // ── the meta line (A): retried · Log · Loop · Mapper · As of ──
  // 🔴 The card strip carried `retried_among_waiting`; a measured number that stops being drawn
  //    is rule ② with the sign flipped, so it stays — always, here (lead 6fdd79d4e).
  // ⚠️ A piece whose key did not come is '' and is dropped HERE; the drawing side does not
  //    decide again (S-16 · S-20: an older server draws nothing, not a made-up 「0」 or 「now」).
  const meta = [
    { key: 'retried', text: `retried ${countOf(payload.retried_among_waiting)}` },
    { key: 'log', text: logName ? `Log ${logName}` : '' },
    { key: 'restart', text: restart },
    { key: 'generated', text: generatedAt ? `As of ${generatedAt}` : '' },
  ].filter((m) => m.text).map((m) => Object.freeze(m));

  return Object.freeze({
    available: true,
    reason: '',
    numbers: Object.freeze(numbers),
    runningRows: Object.freeze(runningRows),
    meta: Object.freeze(meta),
    depth: countOf(payload.waiting),
    byOwner: Object.freeze(byOwner),
    splitByOwner,
    pickup: pickup ? Object.freeze(pickup) : null,
    rows: Object.freeze(rows),
    truncated,
  });
}

/**
 * The panel. One mount, one div, no module state — two of these can sit on one page.
 *
 * Same constructor shape as `GridSourceLabel(host, deps)`: the mount is positional and the
 * document is INJECTED, so a harness drives it with a plain object instead of a browser.
 *
 * @param {HTMLElement} mount
 * @param {{doc?: Document}} [deps]
 */
export class ChainQueuePanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('ChainQueuePanel needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('ChainQueuePanel needs a document (deps.doc or mount.ownerDocument)');
    this.root = this.doc.createElement('div');
    this.root.className = 'chain-queue-panel';
    this.mount.appendChild(this.root);
    // × on a running line asks the page to cancel by run id; the page owns the route.
    this.onCancel = deps.onCancel || (() => {});
  }

  /** @param {string} cls @param {string} text */
  _line(cls, text) { return line(this.doc, cls, text); }

  /** @param {string} text @param {string} [col]  the column's name — its CSS reads it, no inline style */
  _td(text, col) {
    const td = this.doc.createElement('td');
    td.textContent = text;
    if (col) td.setAttribute('data-col', col);
    return td;
  }

  /** @param {string} icon @param {string} text */
  _empty(icon, text) {
    const box = this.doc.createElement('div');
    box.className = 'empty-state';
    const ic = this.doc.createElement('div');
    ic.className = 'empty-icon';
    ic.textContent = icon;
    box.appendChild(ic);
    box.appendChild(this._line('empty-text', text));
    return box;
  }

  /** @param {object|null} payload  @param {{unavailable?: string, failed?: object|null}} [opts] */
  render(payload, opts = {}) {
    const view = queueView(payload, opts);
    const doc = this.doc;
    this.root.textContent = '';

    if (!view.available) {
      this.root.appendChild(this._empty('⚪', view.reason));
      return view;
    }

    // 🔴 「아래 수가 틀렸을 수 있다」는 그 수들보다 «먼저» 읽혀야 뜻이 있습니다 — 뒤에 붙이면
    //    운영자가 이미 그 수를 믿은 뒤입니다. 그래서 숫자 넷 «위»입니다.
    if (view.pickup && view.pickup.stale) {
      this.root.appendChild(this._line('chain-queue-stale',
        `Record failures ${view.pickup.recordFailures} · the numbers below may be stale`));
    }

    const grid = doc.createElement('div');
    grid.className = 'chain-queue-numbers';
    for (const n of view.numbers) {
      const box = doc.createElement('div');
      box.className = 'chain-queue-number';
      box.setAttribute('data-key', n.key);
      if (n.tone) box.setAttribute('data-tone', n.tone);
      box.appendChild(this._line('chain-queue-number-label', n.label));
      box.appendChild(this._line('chain-queue-number-value', n.value));
      if (n.sub) box.appendChild(this._line('chain-queue-number-sub', n.sub));
      grid.appendChild(box);
    }
    this.root.appendChild(grid);

    // rule ④: the cut is read before the list it cuts.
    if (view.truncated) this.root.appendChild(this._line('chain-queue-truncated', view.truncated));
    this.root.appendChild(view.rows.length
      ? this._table(view.rows) : this._line('chain-queue-empty', 'Nothing waiting'));

    if (view.meta.length) {
      const meta = doc.createElement('div');
      meta.className = 'chain-queue-meta';
      for (const m of view.meta) {
        const piece = doc.createElement('span');
        piece.className = `chain-queue-meta-${m.key}`;
        piece.textContent = m.text;
        meta.appendChild(piece);
      }
      this.root.appendChild(meta);
    }

    // ── below the meta line: what needs a look first, then the scheduler's and the owners' lines ──
    // 🔴 C-61. 「최장」이 「걸린 것이 있다」를 말하고, 이 줄들이 «어느 것인지»를 말합니다 —
    //    도는 것마다 한 줄(RunLines), 판정은 운영자의 것.
    if (view.runningRows && view.runningRows.length) {
      const box = this.doc.createElement('div');
      box.className = 'chain-queue-running';
      this.root.appendChild(box);
      new RunLines(box, { doc: this.doc, onCancel: this.onCancel }).render(view.runningRows);
    }
    // 「도는 중인데 주인이 없음」 — the heartbeat decided it, not this file.
    for (const orphan of (view.pickup ? view.pickup.orphaned : [])) {
      this.root.appendChild(this._line('chain-queue-orphan',
                                       `No owner · ${orphan.op} · ${orphan.age}`));
    }

    // ── 그 소유자가 «왜» 기다리는가 ──
    // 🔴 `blocked_by` 가 null 이면 «아무것도» 그리지 않는다. 서버가 적어 둔 대로
    //    null 은 「막힌 것이 없다」가 아니라 「이유를 모른다」이고, 「없음」으로 그리면
    //    이 파일이 없애려는 바로 그 0 이 하나 더 생긴다.
    // 🔴 값은 «서버의 낱말로» 적는다. `moving` 과 `cancel_reaches` 를 번역하면
    //    서버가 일부러 갈라 둔 `stalled` 와 `unreported` 가 한 말로 접힌다.
    for (const b of view.byOwner) {
      if (!b.blocked) {
        // 🔴 여기가 그 하나입니다. 「없음」이 아니라 「못 읽었다」일 때만 한 줄 나갑니다.
        if (b.blockedState === 'unknown') {
          const box = doc.createElement('div');
          box.className = 'chain-queue-blocked';
          box.setAttribute('data-owner', b.owner);
          box.appendChild(this._line('chain-queue-blocked-head',
            `${b.owner} · blocked_by — ${UNKNOWN} (retroactive lookup failed)`));
          this.root.appendChild(box);
        }
        continue;
      }
      const box = doc.createElement('div');
      box.className = 'chain-queue-blocked';
      box.setAttribute('data-owner', b.owner);
      box.appendChild(this._line('chain-queue-blocked-head',
        `${b.owner} · blocked_by — ${b.blocked.op} ${b.blocked.runId}`));
      box.appendChild(this._line('chain-queue-blocked-fact',
        `state ${b.blocked.state} · moving ${b.blocked.moving} · cancel_reaches ${b.blocked.cancelReaches}`));
      box.appendChild(this._line('chain-queue-blocked-fact',
        `processed_rows ${b.blocked.processed} / total_rows ${b.blocked.total}`
        + ` · no_progress ${b.blocked.noProgress} · stall_after ${b.blocked.stallAfter}`));
      // 🔴 「왜 도는지」가 «사실» 줄들 다음, 복구 문장 앞에 섭니다.
      if (b.blocked.why) box.appendChild(this._line('chain-queue-blocked-why', b.blocked.why));
      if (b.blocked.recovery) {
        box.appendChild(this._line('chain-queue-blocked-recovery', b.blocked.recovery));
      }
      this.root.appendChild(box);
    }

    // 🔴 「집는 이가 살아 있나」 — 「곧 돈다」와 「아무도 안 집는다」를 가르는 것은 큐 길이가 아니라 이것.
    // ⛔ No verdict word and no predicted start: the age and the declared interval go out
    //    side by side with their units, and the reading is the operator's.
    if (view.pickup) {
      this.root.appendChild(this._line('chain-queue-pickup', view.pickup.pickup));
      if (view.pickup.basis) this.root.appendChild(this._line('chain-queue-basis', view.pickup.basis));
      if (view.pickup.waitingText) {
        this.root.appendChild(this._line('chain-queue-ahead', view.pickup.waitingText));
      }
    }

    // ── 누가 비우나 ── 소유자가 «하나»면 그리지 않는다 (위 `splitByOwner` 참조).
    if (view.splitByOwner) {
      const strip = doc.createElement('div');
      strip.className = 'chain-queue-owner-strip';
      for (const b of view.byOwner) {
        const line = this._line('chain-queue-owner',
          `${b.owner} · waiting ${b.waiting} · oldest ${b.age}`);
        line.setAttribute('data-owner', b.owner);
        strip.appendChild(line);
      }
      this.root.appendChild(strip);
    }
    return view;
  }

  /** The list (A): Transaction · Waiting · Tables · Rows · Drained by. No px widths — the Tables
   *  column takes what is left, the rest take their content (admin.html `.chain-queue-table`). */
  _table(rows) {
    const doc = this.doc;
    const table = doc.createElement('table');
    table.className = 'table-container chain-queue-table';
    const thead = doc.createElement('thead');
    thead.className = 'table-header';
    const hr = doc.createElement('tr');
    for (const [label, col] of [['Transaction', 'tx'], [WAITING, 'age'], ['Tables', 'tables'],
                                ['Rows', 'rows'], ['Drained by', 'owners']]) {
      const th = doc.createElement('th');
      th.textContent = label;
      th.setAttribute('data-col', col);
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = doc.createElement('tbody');
    for (const r of rows) {
      const tr = doc.createElement('tr');
      tr.className = 'table-row';
      tr.setAttribute('data-txid', r.txId);

      const tdId = this._td('', 'tx');
      const chip = doc.createElement('span');
      chip.className = 'tx-id-chip';
      chip.title = r.txId;
      chip.textContent = r.txShort;
      tdId.appendChild(chip);
      tr.appendChild(tdId);

      const tdAge = this._td(r.age, 'age');
      if (r.at) tdAge.title = `Waiting since ${r.at}`;
      tr.appendChild(tdAge);
      tr.appendChild(this._td(r.tables, 'tables'));
      tr.appendChild(this._td(r.rows, 'rows'));

      // 🔴 누가 빼나 — 서버가 정한 이름 그대로, 한 이름에 배지 하나. 이름이 없으면 대시(「chain」이 아니다).
      const tdOwners = this._td(r.owners.length ? '' : ABSENT, 'owners');
      tdOwners.setAttribute('data-owners', r.owners.join(', ') || ABSENT);
      for (const owner of r.owners) {
        const badge = doc.createElement('span');
        badge.className = 'chain-queue-owner-badge';
        badge.textContent = owner;
        tdOwners.appendChild(badge);
      }
      // rule ③ applies here too: the retry count is stated, never coloured into a verdict.
      if (r.maxRetry) {
        const retry = doc.createElement('span');
        retry.className = 'chain-queue-retry-badge';
        retry.textContent = `retry ${r.maxRetry}`;
        tdOwners.appendChild(retry);
      }
      tr.appendChild(tdOwners);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return table;
  }
}
