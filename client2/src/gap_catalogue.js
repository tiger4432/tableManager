// GAP CATALOGUE — 「선언이 «있어야 한다»고 한 자리 중 원장이 비어 있는 곳」의 목록.
//
// 🔴 이 화면이 없어서 생기던 일: 거절문이 사람을 명세로 보내는데, 명세는 「이 이름이 무슨
//    뜻인가」를 답하지 「지금 «내 것 중» 무엇이 그건가」를 답하지 않습니다. 그래서 운영자는
//    뜻은 알고 대상은 모른 채로 남았습니다.
//
// 🔴 그리는 것은 탐지기가 아는 «넷» 중 «셋»입니다:
//      ① 이름 + 다음 행동     거절문이 이미 이름표로 보내므로, 목록이 그 이름을 «실물»에 겁니다
//      ② 없는 «쪽»           주어 쪽이 빈 것과 목적어 쪽이 빈 것은 «반대 행동»입니다
//      ③ 🔴 «공허함»         「선언상 있을 수 없다」와 「있을 수 있는데 없다」
//    ⛔ 넷째(있는/없는 술어를 «이름으로» 나열)는 안 그립니다 — 화면 것이 아니라고 갈렸습니다.
//
// ⛔ 「공허함」을 여기서 «계산하지» 않습니다. 탐지기가 `vacuous` 로 이미 압니다. 화면이 다시
//    유도하면 선언이 바뀌는 날 두 답이 조용히 갈립니다.
//
// ⚠️ 그리고 이것이 오늘 부재 부류의 «다섯째 모양»입니다. 앞의 넷은 「모르는 것을 아는 척」인데
//    이건 «있을 수 없는 것»과 «없는 것»을 같게 보여 줍니다 — 비용이 구체적입니다.
//    운영자가 «선언이 금지한 데이터»를 찾으러 갑니다.

/** 안 물어봤거나 못 받았습니다. 「격차 없음」이 아닙니다. */
export const GAPS_UNREAD = '격차 · 모름';

/** 「없는 쪽」의 낱말. 서버의 `form` 값 그대로가 키입니다 — 여기서 갈래를 새로 만들지 않습니다. */
export const SIDE_LABELS = Object.freeze({
  pair: '한 쌍이 어긋남',
  subject_side: '주어 쪽 비었음',
  object_side: '목적어 쪽 비었음',
});

const list = (value) => (Array.isArray(value) ? value : []);
const str = (value) => (typeof value === 'string' && value ? value : '');

/**
 * @param {object|null|undefined} payload `GET /api/ledger/gaps` 의 응답
 * @param {{read?: boolean, refusal?: object}} [opts]
 *        `refusal` 은 503/404 의 `detail` — 「거절」과 「못 물어봄」은 다릅니다
 */
export function gapCatalogueView(payload, opts = {}) {
  const refusal = opts.refusal && typeof opts.refusal === 'object' ? opts.refusal : null;
  if (refusal) {
    // 🔴 거절은 «작성자»의 물음입니다 — 「이름을 어디에 적나」. 목록과 «합치지» 않습니다.
    //    서버의 문장이 이미 갈래·타입·술어를 이름으로 듭니다. 다시 쓰지 않습니다.
    return { read: false, refused: true, rows: [],
             reason: str(refusal.reason), text: str(refusal.message) || GAPS_UNREAD };
  }
  if (opts.read === false || !payload) {
    return { read: false, refused: false, rows: [], reason: '', text: GAPS_UNREAD };
  }
  const rows = list(payload.gaps).map((gap) => {
    const form = str(gap && gap.form);
    return {
      name: str(gap && gap.name),
      form,
      // 서버가 낸 갈래에 «우리 낱말»이 없으면 그 갈래를 그대로 보여 줍니다 — 조용히
      // 빠뜨리면 새 갈래가 생기는 날 화면이 «짧아지고» 아무도 모릅니다.
      side: SIDE_LABELS[form] || form,
      // 쌍은 「뜻」을, 한쪽 결측은 「다음 행동」을 답니다. 서버가 어느 쪽을 실었든 그대로.
      action: str(gap && gap.action) || str(gap && gap.meaning),
      type: str(gap && gap.type),
      vacuous: (gap && gap.vacuous) === true,
    };
  });
  const vacuous = rows.filter((row) => row.vacuous).length;
  return {
    read: true,
    refused: false,
    rows,
    reason: '',
    // 「무엇의 수인가」를 옆에 답니다. 공허한 것을 총계에 «섞으면» 운영자가 찾으러 갑니다.
    text: vacuous
      ? `격차 ${rows.length - vacuous} · 공허 ${vacuous}`
      : `격차 ${rows.length}`,
  };
}
