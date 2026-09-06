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
 * @returns {{state: 'done'|'failed'|'queued'|'unknown', tone: 'ok'|'danger'|'warn',
 *            settled: boolean}}
 *   `settled` 는 「이 건이 «끝났나»」입니다 — 대기는 끝난 것이 아니고, 그 구분이 이 파일이
 *   존재하는 이유입니다.
 */
export function retryVerdict(status) {
  const spelled = String(status == null ? '' : status).trim().toUpperCase();
  if (spelled === 'SUCCESS') return { state: 'done', tone: 'ok', settled: true };
  if (spelled === 'FAILED') return { state: 'failed', tone: 'danger', settled: true };
  // 🔴 대기는 «성공도 실패도 아닙니다». 워처가 집어 가야 결정됩니다 — 그때까지 이 건은
  //    「끝났다」고 말할 수 없고, 「실패했다」고 말할 수도 없습니다.
  if (spelled === 'PENDING_RETRY') return { state: 'queued', tone: 'warn', settled: false };
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
      return { tone: 'success', text: `✅ 재시도 완료${tail}` };
    case 'failed':
      return { tone: 'warning', text: `⚠️ 재시도가 다시 실패했습니다. 오류 메시지를 확인하세요.${tail}` };
    // 🔴 여기가 이 라운드의 전부입니다. 「완료」가 아니라 「대기」이고, 그 일을 «누가» 하는지도
    //    말합니다 — 워처가 서 있으면 이 건은 영원히 이 상태입니다.
    case 'queued':
      return { tone: 'warning', text: `⏳ 재시도 대기 — 워처가 집어 가야 처리됩니다${tail}` };
    // ⚠️ 「목록에 없다」와 「모르는 철자」는 다른 사실입니다. 앞은 필터가 FAILED 일 때
    //    «정상»으로 일어나고(성공한 행은 그 목록을 떠납니다), 뒤는 서버가 새 상태를
    //    만든 경우입니다. 둘을 한 문장으로 접으면 전자가 «고장처럼» 읽힙니다.
    default:
      return { tone: 'warning', text: status == null
        ? `↔️ 이 목록에서 빠졌습니다 — ALL 필터에서 상태를 확인하십시오${tail}`
        : `❔ 알 수 없는 상태 (${status})${tail}` };
  }
}
