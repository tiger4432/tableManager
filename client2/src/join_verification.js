// JOIN VERIFICATION — 「이 조인 선언이 «승인»됐나, 아니면 «무엇을 만들어야» 하나」.
//
// 🔴 이 파일이 있는 이유: 화면이 부르던 `/admin/config/resolve` 는 「선언이 «유효한가»」까지만
//    답합니다. 승인 조건인 「조인 키를 덮는 UNIQUE 인덱스」는 `pg_index` 가 아는 사실이라
//    세션이 필요하고, 그래서 «다른 라우트»(`/admin/config/virtual-join/verify`)가 답합니다.
//    그 라우트는 오늘까지 소비자가 «0» 이었습니다 — 서버는 「무엇을 만들어야 하는지」를
//    DDL 문장으로 내고 있었는데, 화면은 한 낱말만 읽고 있었습니다.
//
// ⛔ 한 낱말짜리 답을 «지우지» 않습니다. 요약은 요약대로 쓸모가 있고, 이건 «옆에» 붙는 것입니다.
// ⛔ 문장을 여기서 «짓지» 않습니다. 서버(`config_resolve_report.virtual_join_detail`)가
//    정본이고, 같은 거부가 두 화면에서 다른 문장으로 나오는 순간 그 계약이 깨집니다.

/** 묻지 않았거나 못 받았습니다. 「승인 안 됨」이 아닙니다. */
export const JOIN_UNREAD = '진단 · 모름';

const list = (value) => (Array.isArray(value) ? value : []);
const str = (value) => (typeof value === 'string' && value ? value : '');

/**
 * 한 선언의 상태.
 *
 * 🔴 넷입니다: 아직 안 옴 · 통과 · 거절(+«무엇을 바꾸나») · 진단 못 냄.
 *    「거절」과 「진단 못 냄」을 합치면 운영자가 «고칠 자리»를 잃습니다 — 앞은 DDL 한 줄이
 *    답이고, 뒤는 답이 아직 없다는 뜻입니다.
 */
function declarationState(row) {
  if (row.accepted === true) return 'accepted';
  if (row.accepted === false) {
    // 서버가 「무엇을 만들어야 하는지」를 실었으면 그것이 «고칠 자리»입니다.
    return str(row.required_index_ddl) || str(row.detail) ? 'refused' : 'undiagnosed';
  }
  // `accepted` 가 없는 행은 「아니다」가 아닙니다.
  return 'undiagnosed';
}

/**
 * @param {object|null|undefined} report `/admin/config/virtual-join/verify` 의 응답
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
      detail: state === 'refused' ? str(row.detail) : '',
      ddl: state === 'refused' ? str(row.required_index_ddl) : '',
      index: str(row.unique_index) || str(row.required_index),
    };
  });
  // 모양 단계에서 떨어진 선언 — 규칙이 «되지도» 못한 것들이라 이름도 표도 없습니다.
  // 거절의 다른 «인구»이지 다른 상태가 아닙니다.
  const invalid = list(report.invalid).map((item) => ({
    subject: str(item && item.subject) || '이름 없음',
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
      ? `선언 ${rows.length}`
      : `승인 ${accepted} · 거절 ${refused + invalid.length}`,
    reason: '',
  };
}
