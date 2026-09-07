// C-1 «화면 절반» — 「이 규칙이 마지막에 «무엇을 했나»」.
//
// 🔴 이 라운드가 닫는 문장: **「이 규칙이 «꺼져서» 안 돌았다」와 「돌았는데 바꿀 게 없었다」가
//    화면에서 «같은 모양»입니다.** 규칙 표는 선언(ACTIVE/DISABLED)만 그렸고, 그 규칙이
//    «실제로 무엇을 했는지»를 말하는 칸이 없었습니다. 서버는 `/admin/chain/queue` 의
//    `rule_outcomes` 로 «이미» 답하고 있었고 읽는 자리가 «0» 이었습니다.
//
// 🔴 어휘는 서버 것 «그대로»입니다 — `server/event_constants.py` 의 닫힌 여섯. 여기서 다시
//    철자하거나 한국어 동의어를 만들면 그날부터 두 어휘가 «갈릴 수» 있고, 갈려도 오류가
//    «안 납니다». 그래서 화면에 나가는 낱말도 그 토큰입니다.
//
// ⛔ 「바꿈」이라 쓰지 «않습니다**. `ran:changed` 의 사실은 「맵퍼가 «행을 냈다»」이지
//    「쓰기가 무언가를 «바꿨다»」가 아닙니다 — 서버가 자기 주석에 그 한계를 적어 두었고
//    (`chain_ingestion_worker.py:631`), 「바꿈」이라 그리면 화면이 «거짓»을 말합니다.
//
// ⛔ 그리고 이 줄은 C-9 의 `change_count` 와 «다른 알갱이»입니다 — 저쪽은 «이벤트» 단위이고
//    이쪽은 «규칙» 단위입니다. 한 줄에 섞으면 두 수가 서로를 설명하는 것처럼 보입니다.

// 🔴 스타일시트가 «실제로 그리는» 넷뿐입니다 (`admin.html` 의 badge 정의 실측).
//    없는 이름을 고르면 「그렸다」고 적어 두고 화면엔 아무 강조도 안 붙습니다 — 오늘 하루
//    제가 세 번 잡은 「발신 있고 독자 0」의 CSS 판입니다.
const BADGE = {
  'failed': 'badge-danger',                 // 유일하게 «오류»인 것
  'skipped:disabled': 'badge-warning',      // 유일하게 «운영자 손»에 있는 것
  'ran:changed': 'badge-success',           // 일을 «했다»
  'ran:unchanged': 'badge-muted',
  'skipped:not_triggered': 'badge-muted',   // 데이터의 사실 — 고칠 대상이 아니다
  'never_evaluated': 'badge-muted',         // 이 «프로세스»가 아직 이 규칙을 못 봤다
};

/**
 * 규칙 하나의 마지막 결과를 «무엇을 그리나»로.
 *
 * @param {object|null|undefined} entry  `rule_outcomes[<규칙명>]`
 * @returns {{read: boolean, outcome: string, badge: string, reason: string, age: number|null}}
 *          `read` 가 false 면 «아무것도 안 그립니다**
 *
 * ⚠️ 세 상태입니다. 이 화면의 `logName`·`restart`·`generatedAt` 과 «같은 규율»:
 *      값        그 토큰을 그린다
 *      `never_evaluated`   «값**이다 — 「이 프로세스가 아직」. 부재가 아니다
 *      키 «없음»  옛 서버 -> «안 그린다**. 부재는 이 뜻 «하나»여야 한다
 */
export function ruleOutcomeView(entry) {
  const none = { read: false, outcome: '', badge: '', reason: '', age: null };
  if (!entry || typeof entry !== 'object') return none;
  const outcome = typeof entry.last_outcome === 'string' ? entry.last_outcome.trim() : '';
  if (!outcome) return none;
  return {
    read: true,
    outcome,
    // 🔴 «모르는» 토큰도 그립니다 — 다만 강조는 «안 붙입니다**. 여기서 안 그리면 서버가 낸
    //    진짜 결과(예: 새 실패 종류)를 화면이 «삼킵니다**. 토큰을 그대로 내는 것은 «거짓일
    //    수 없고**, 등급을 지어내는 것만 거짓일 수 있습니다 — 그래서 낱말은 내고 색은 안 냅니다.
    badge: BADGE[outcome] || 'badge-muted',
    // 서버의 사유를 «그대로**. 없으면 «없는 채로** — 「없음」을 지어내지 않습니다.
    reason: typeof entry.last_reason === 'string' ? entry.last_reason : '',
    // 🔴 «나이»이지 시각이 아닙니다. 기준 시각은 «같은 응답»의 `generated_at` 이고, 그 줄은
    //    같은 화면의 큐 패널이 이미 그립니다 (S-20) — 여기서 두 번 그리지 않습니다.
    age: Number.isFinite(entry.last_age_seconds) ? entry.last_age_seconds : null,
  };
}
