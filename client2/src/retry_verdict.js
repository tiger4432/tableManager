// ═══════════════════════════════════════════════════════════════════════════════
// RETRY VERDICT — 파일 인제션 로그의 상태를 「무슨 일이 났나」로 옮기는 한 곳
//
// 🔴 상태가 «셋»인데 화면이 «하나의 부재»로 물었습니다.
//    `POST /admin/file-ingestion/retry-failed` 는 DECOUPLED 모드에서 «재시도하지 않습니다» —
//    FAILED 를 `PENDING_RETRY` 로 표시하고 즉시 돌아오며, 실제 처리는 별도 워처
//    프로세스(`run_watcher.py`)가 자기 질의로 집어 갑니다. 그런데 화면은 성공을
//    「아직 FAILED 인가」로 판정했고, 세 번째 상태는 그 물음을 «만족»합니다.
//    -> 시작도 안 한 일에 「✅ 재시도 완료」가 떴습니다.
//
// 🔴 그리고 이 결함은 «모드에 따라 조용히 참/거짓이 바뀝니다.**
//    DECOUPLED 가 꺼져 있으면 그 라우트는 «동기» 재시도라 「완료」가 참입니다. 그래서 이 줄이
//    반쯤 참인 채로 오래 살았습니다 — 다음 사람이 「어떤 환경에선 멀쩡한데?」로 되돌리지
//    않도록 여기에 적어 둡니다. 고쳐야 하는 것은 «환경»이 아니라 «갈래가 있다는 사실»입니다.
//
// ⚠️ 「모른다」는 「아니다」가 아닙니다. 여기가 모르는 철자는 `unknown` 으로 답하고, 부르는
//    쪽은 그때 «성공이라고 말하지 않습니다». 서버가 상태를 하나 더 만드는 날, 화면이
//    조용히 「완료」라고 말하는 것보다 「모르는 상태」라고 말하는 편이 낫습니다.
// ═══════════════════════════════════════════════════════════════════════════════

// ⛔ THE CATALOGUE IS NOT HERE, AND THAT IS THE POINT.
//    The first draft of this file exported the state list. Measured 2026-09-07 while writing
//    it: the server side already owns that list
//    (`server/file_ingestion_status.FILE_INGESTION_STATUS_VOCABULARY`) and it has FIVE members
//    (`PENDING` and `SKIPPED` besides the three a screen usually sees). A three-name list here
//    would have been a second catalogue AND a wrong one - the exact shape this repository has
//    been closing all night (`_bare` under one name with four bodies).
//
//    So this module answers 「이 상태가 무슨 뜻인가」 and never 「어떤 상태들이 있나」. The
//    second question has one owner and it is not the client.

/**
 * 이 상태가 「무슨 일이 났나」.
 *
 * @returns {{state: 'done'|'failed'|'queued'|'skipped'|'unknown', tone: 'ok'|'danger'|'warn',
 *            settled: boolean}}
 *   `settled` 는 「이 건이 «끝났나»」입니다 — 대기는 끝난 것이 아니고, 그 구분이 이 파일이
 *   존재하는 이유입니다.
 */
export function retryVerdict(status) {
  const spelled = String(status == null ? '' : status).trim().toUpperCase();
  if (spelled === 'SUCCESS') return { state: 'done', tone: 'ok', settled: true };
  // Files spell it FAILED, collectors FAIL (lead e1af65168) — one meaning, the server's words kept.
  if (spelled === 'FAILED' || spelled === 'FAIL') return { state: 'failed', tone: 'danger', settled: true };
  // 🔴 대기는 «성공도 실패도 아닙니다». 워처가 집어 가야 결정됩니다 — 그때까지 이 건은
  //    「끝났다」고 말할 수 없고, 「실패했다」고 말할 수도 없습니다.
  if (spelled === 'PENDING_RETRY') return { state: 'queued', tone: 'warn', settled: false };
  // Skipped is ended, and neither loaded nor failed (lead 69aad666e) — amber, like the badge.
  if (spelled === 'SKIPPED') return { state: 'skipped', tone: 'warn', settled: true };
  return { state: 'unknown', tone: 'warn', settled: false };
}

/**
 * 운영자가 읽을 한 문장. 🔴 서버가 «이미 말한» 것을 덮지 않습니다 — 서버 메시지를 받으면
 * 그것을 싣고, 이 함수는 «그 앞의 판정»만 정합니다.
 */
export function retryMessage(status, serverMessage) {
  const tail = serverMessage ? ` — ${serverMessage}` : '';
  switch (retryVerdict(status).state) {
    case 'done':
      return { tone: 'success', text: `✅ Retry done${tail}` };
    case 'failed':
      return { tone: 'warning', text: `⚠️ Retry failed again · check the error message${tail}` };
    // 🔴 여기가 이 라운드의 전부입니다. 「완료」가 아니라 「대기」이고, 그 일을 «누가» 하는지도
    //    말합니다 — 워처가 서 있으면 이 건은 영원히 이 상태입니다.
    case 'queued':
      return { tone: 'warning', text: `⏳ Retry waiting — runs when the watcher picks it up${tail}` };
    // ⚠️ 「목록에 없다」와 「모르는 철자」는 다른 사실입니다. 앞은 필터가 FAILED 일 때
    //    «정상»으로 일어나고(성공한 행은 그 목록을 떠납니다), 뒤는 서버가 새 상태를
    //    만든 경우입니다. 둘을 한 문장으로 접으면 전자가 «고장처럼» 읽힙니다.
    default:
      return { tone: 'warning', text: status == null
        ? `↔️ Left this list — check its state under the ALL filter${tail}`
        : `❔ Unknown state (${status})${tail}` };
  }
}

/**
 * `POST /admin/outbox/retry-failed` reply -> one toast. The verdict is the server's `status`
 * (lead f063c948e): `refused` (nothing reset) is the server's sentence as a refusal, never a
 * success; a reset with skips is both halves, which the server's sentence already names.
 * A row-state vocabulary (`retryVerdict`) is a different envelope - this reads the reply.
 */
export function outboxRetryMessage(body) {
  const reply = body && typeof body === 'object' ? body : {};
  const said = typeof reply.message === 'string' ? reply.message.trim() : '';
  // What it did NOT do. `ended_missing_row` is done (the row is gone and the event ended), not a skip.
  const skipped = Number(reply.skipped_reexpanded) || 0;
  if (reply.status === 'refused') return { tone: 'error', refused: true, text: `⛔ ${said || 'Refused'}` };
  if (reply.status === 'success') {
    return skipped > 0
      ? { tone: 'warning', refused: false, text: `⚠️ ${said}` }
      : { tone: 'success', refused: false, text: `🔄 ${said}` };
  }
  return { tone: 'warning', refused: false,
    text: `❔ Unknown reply${reply.status ? ` (${reply.status})` : ''}${said ? ` — ${said}` : ''}` };
}

/** 「Did it fail?」 — tone danger, for a count as for a badge (lead 457b34131: the spelling is
 *  compared in this file only). */
export const isFailedStatus = (status) => retryVerdict(status).tone === 'danger';

/** 「Is it done?」 — the file card's ok face and the toast's one-line collapse (lead 65f2c808d),
 *  and the Retry button's off state: today's rule kept, anything not done can be retried. */
export const isDoneStatus = (status) => retryVerdict(status).state === 'done';

/** A file that went in: loaded or skipped - ended, and not failed (lead 10-11 R: the rows read again with today's parser). */
export const wentIn = (status) => ['done', 'skipped'].includes(retryVerdict(status).state);

/**
 * A file row's Retry (owner 10-11 R): a row that went in is read again with today's parser - its request carries the
 * statuses that include it (`includeStatuses`, folder_retry's) and says so before it runs; any other row asks as before.
 */
export function fileRetryAsk(log, includeStatuses) {
  const reread = wentIn(log.status);
  return {
    confirm: reread ? `Read ${log.filename} again with today's parser?` : `Retry file ingestion for log #${log.id}?`,
    query: `log_id=${encodeURIComponent(log.id)}${reread ? `&statuses=${encodeURIComponent(includeStatuses)}` : ''}`,
  };
}

/** A file row's Retry answered: a file no longer where it was is said by name - not the row's state, which stays as it
 *  was; else the row's state as `retryMessage` says it, with its id. */
export function fileRetryToast(result, status, log) {
  const gone = Number((result || {}).missing) >= 1;
  if (gone) return { tone: 'warning', text: `Missing · ${((result.missing_files || [])[0]) || log.filename}` };
  const said = retryMessage(status, (result || {}).message);
  return { tone: said.tone, text: `${said.text.replace(/^(.)\s*/, '$1 ')} (ID #${log.id})` };
}

const FILE_END_TITLE = Object.freeze({
  done: '✅ File loaded', skipped: '⏭️ File skipped', failed: '❌ File load failed',
});

/** A file's end as the toast and the end card say it (lead 69aad666e) — written here from the
 *  status, in English; the server sends the status, not a sentence. */
export function fileEndView(status, filename, reason) {
  const v = retryVerdict(status);
  const word = String(status == null ? '' : status).trim();
  const title = FILE_END_TITLE[v.state] || `❔ File ended ${word || 'without a status'}`;
  const said = reason == null ? '' : String(reason).trim();
  const head = [title, filename ? String(filename) : ''].filter(Boolean).join(' — ');
  return { tone: v.tone, title, toast: said ? `${head} (${said.slice(0, 100)})` : head };
}

/** The toast word for a status, from its tone — a file's end toast says what its badge says. */
export function statusToastTone(status) {
  const tone = retryVerdict(status).tone;
  return tone === 'ok' ? 'success' : tone === 'danger' ? 'error' : 'warning';
}

/** A status badge's class from its tone — the collector list, the file list, the file drawer
 *  and the collector drawer all read this one. */
export function statusBadgeClass(status) {
  const tone = retryVerdict(status).tone;
  return `badge badge-${tone === 'ok' ? 'success' : tone === 'danger' ? 'danger' : 'warning'}`;
}

/** The drawer body's own class (admin.html `.traceback-text`, red). Every drawer that writes the
 *  body sets its class, so none inherits the neutral one a success file left behind. */
export const DRAWER_BODY_CLASS = 'traceback-text';

/**
 * A diagnostics drawer's title, badge, body and body colour, all from ONE tone - the badge's
 * (leads 59fa66aaf · 1f87a0baf · e1af65168). A sentence on a success is not filed under «error»,
 * an empty message on something that did not succeed does not claim it did, and only a failure
 * is drawn red. The two drawers differ only in their words.
 */
function drawerMessageView(status, message, words) {
  const tone = retryVerdict(status).tone;
  const said = typeof message === 'string' ? message.trim() : '';
  const empty = tone === 'ok' ? `No message — ${words.done}.`
    : tone === 'danger' ? 'No error message captured.' : 'No message captured.';
  return { tone,
    title: `${words.subject} ${tone === 'danger' ? 'error' : 'message'}`,
    body: said || empty,
    badgeClass: statusBadgeClass(status),
    bodyClass: tone === 'danger' ? DRAWER_BODY_CLASS : `${DRAWER_BODY_CLASS} is-neutral` };
}

/** File Ingestion drawer (`file_ingestion_logs.status` · `error_message`). */
export const ingestionMessageView = (status, message) =>
  drawerMessageView(status, message, { subject: 'Ingestion', done: 'ingested successfully' });

/** Auto Update collector drawer (`last_status` · `last_error`). */
export const collectorMessageView = (status, message) =>
  drawerMessageView(status, message, { subject: 'Last run', done: 'last run succeeded' });
