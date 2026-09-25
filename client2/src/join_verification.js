// JOIN VERIFICATION — 「이 조인 선언이 «승인»됐나, 아니면 «무엇을 만들어야» 하나」.
//
// 🔴 이 파일이 있는 이유: 화면이 부르던 `/admin/config/resolve` 는 「선언이 «유효한가»」까지만
//    답합니다. 승인 조건인 「조인 키를 덮는 UNIQUE 인덱스」는 `pg_index` 가 아는 사실이라
//    세션이 필요하고, 그래서 «다른 라우트»(`/admin/chain/join/verify`)가 답합니다.
//    그 라우트는 오늘까지 소비자가 «0» 이었습니다 — 서버는 「무엇을 만들어야 하는지」를
//    DDL 문장으로 내고 있었는데, 화면은 한 낱말만 읽고 있었습니다.
//
// ⛔ 한 낱말짜리 답을 «지우지» 않습니다. 요약은 요약대로 쓸모가 있고, 이건 «옆에» 붙는 것입니다.
// ⛔ 문장을 여기서 «짓지» 않습니다. 서버(`config_resolve_report.join_detail`)가
//    정본이고, 같은 거부가 두 화면에서 다른 문장으로 나오는 순간 그 계약이 깨집니다.

/** 묻지 않았거나 못 받았습니다. 「승인 안 됨」이 아닙니다. */
export const JOIN_UNREAD = 'Diagnosis · unknown';

const list = (value) => (Array.isArray(value) ? value : []);
const str = (value) => (typeof value === 'string' && value ? value : '');

/**
 * 한 선언의 상태.
 *
 * 🔴 [판정 685·687] 종류를 묻는 자리는 «한 좌석»이고 그것은 «서버»입니다 — 행의
 *    `approval_state`, 닫힌 어휘(server/event_constants.py: APPROVAL_STATES).
 *    ⛔ accepted·detail·required_index_ddl 에서 «유도하지» 않습니다. 「DDL 이 없으면 안 물음」은
 *    대리라서, DDL 없는 거절이 생기는 날 조용히 틀립니다.
 * ⚠️ 화면 낱말은 'accepted' 그대로입니다(서버는 'approved'). 축이 둘이라서가 아니라 그 낱말이
 *    CSS·하니스의 이름이고, 고르는 자리는 «이 함수 하나»입니다.
 * ⚠️ 서버의 'not_asked' 는 「key.unique 없음」과 「꺼짐」을 «접습니다»(Q-198). 화면이 그 접힘을
 *    물려받습니다 — 가르려면 축이 셋이어야 하고, 문장으로 가르는 것은 685 가 금했습니다.
 */
function declarationState(row) {
  const said = str(row.approval_state);
  if (said === 'approved') return 'accepted';
  if (said === 'refused') return 'refused';
  if (said === 'not_asked') return 'not_asked';
  // 🔴 칸이 «있는데 모르는 값»이면 「진단 못 냄」입니다 — 어휘는 자랄 수 있고(총괄 09-22:
  //    「세 값은 제가 본 것이지 천장이 아니다」), 모르는 값을 아래 옛 읽기로 떨어뜨리면
  //    «새 상태가 「거절」로» 그려집니다. 모르는 것은 모른다고 그리는 편이 낫습니다.
  if (said) return 'undiagnosed';
  // 이 칸이 «없는» 응답(칸보다 오래된 서버)은 셋을 가를 수가 없습니다. 그때의 읽기를 그대로 둡니다 —
  // 여기서 없음을 메우면 그것이 위에서 금한 «유도»입니다.
  if (row.accepted === true) return 'accepted';
  if (row.accepted === false) {
    return str(row.required_index_ddl) || str(row.detail) ? 'refused' : 'undiagnosed';
  }
  // `accepted` 가 없는 행은 「아니다」가 아닙니다.
  return 'undiagnosed';
}

/**
 * @param {object|null|undefined} report `/admin/chain/join/verify` 의 응답
 * @param {{read?: boolean, failed?: string}} [opts] `failed` 는 못 받은 «사유»
 */
export function joinVerificationView(report, opts = {}) {
  const failed = str(opts.failed);
  if (opts.read === false || failed || !report) {
    return { read: false, rows: [], invalid: [], accepted: null, refused: null,
             text: JOIN_UNREAD, reason: failed };
  }
  const rows = list(report.declarations).map((row) => {
    const state = declarationState(row);
    return {
      name: str(row.name),
      state,
      // 조인 키는 서버가 이미 `left = right` 로 조립해 보냅니다. 다시 조립하지 않습니다.
      joinKey: list(row.join_key).map(String),
      // 🔴 접기는 «비교의 성질»이라 이 조인만 다른 인덱스를 요구하는 이유가 됩니다.
      //    빼면 운영자가 왜 이것만 다른지 알 길이 없습니다.
      folded: list(row.folded_join_key)
        .map((f) => `${str(f && f.left)} · ${list(f && f.rules).join(' ')}`.trim())
        .filter(Boolean),
      detail: state === 'refused' || state === 'not_asked' ? str(row.detail) : '',
      ddl: state === 'refused' ? str(row.required_index_ddl) : '',
      index: str(row.unique_index) || str(row.required_index),
    };
  });
  // 모양 단계에서 떨어진 선언 — 규칙이 «되지도» 못한 것들이라 이름도 표도 없습니다.
  // 거절의 다른 «인구»이지 다른 상태가 아닙니다.
  const invalid = list(report.invalid).map((item) => ({
    subject: str(item && item.subject) || 'No name',
    detail: str(item && item.detail),
  }));
  const accepted = Number.isFinite(report.accepted) ? report.accepted : null;
  const refused = Number.isFinite(report.refused) ? report.refused : null;
  return {
    read: true,
    rows,
    invalid,
    accepted,
    refused,
    // 「무엇의 수인가」를 옆에 답니다 — 수 하나만 있으면 다른 수로 읽힙니다.
    text: accepted === null || refused === null
      ? `Declared ${rows.length}`
      : `Accepted ${accepted} · refused ${refused + invalid.length}`,
    reason: '',
  };
}
