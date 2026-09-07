// ═══════════════════════════════════════════════════════════════════════════════
// S-35 — 확정 응답의 «판정», 읽힘.
//
// 🔴 왜 있나. `POST /api/maps/alignment/confirm` 은 방금 쓴 «기록 전체»를 돌려줍니다
//    (`frame_confirmation.as_payload`), 그 안에 `ruling.winner` — «채점기가 지목한 프레임» —
//    이 `confirmed.frame` — «조작자가 확정한 프레임» — 옆에 실려 옵니다.
//    화면은 그 응답을 «통째로 버렸습니다»: `main.js` 가 `.then(() => …)`, 인자 없는 콜백으로
//    받았습니다. 보내는 쪽은 살아 있고 듣는 쪽이 없는 그 부류입니다.
//
// 🔴 «비교»가 문장입니다. 그 두 칸은 조작자가 쓰고 나면 달리 알 길이 없는 것 하나에 답합니다:
//    채점기의 후보를 «받았나 · 뒤집었나 · 고를 후보가 없었나». 확정됨 표시는 셋 다 «똑같이»
//    생겼습니다.
//
// ⛔ 이 파일은 «채점하지도 순위를 매기지도 다시 판정하지도» 않습니다. 서버가 쓴 두 문자열을
//    견주고 셋 중 어느 경우인지 말할 뿐입니다. 어느 한쪽을 «선호»하기 시작하는 순간
//    두 번째 판정 구현이 되고, 그것은 `verdict.js` 가 자기 머리에 적어 둔 실패입니다.
// ═══════════════════════════════════════════════════════════════════════════════

import { STATE_NO_WINNER, STATE_NOT_SCORABLE } from './verdict.js';

/** 조작자가 채점기의 후보를 그대로 받았다. */
export const RULING_ACCEPTED = 'accepted';
/** 조작자가 채점기와 «다른» 프레임을 확정했다. */
export const RULING_OVERRIDDEN = 'overridden';
/** 채점기가 아무도 지목하지 않았다 — 받을 것도 뒤집을 것도 없었다. */
export const RULING_NO_CANDIDATE = 'no_candidate';
/**
 * 🔴 「판정이 없었다」가 «아니라» 「이 응답이 말하지 않는다」입니다. `ruling` 블록이 없던
 *    옛 서버와, 이 서버가 「판정을 기록하지 않았다」고 말하는 것이 둘 다 여기 옵니다 —
 *    둘 다 그릴 것이 «없다»이지, «없음을 그릴 것»이 아닙니다.
 */
export const RULING_UNRECORDED = 'unrecorded';

const NOTHING = Object.freeze({ state: RULING_UNRECORDED, text: '' });
const MARK_ACCEPTED = '채점기 후보 그대로';
const MARK_NONE = '이긴 후보 없음';
const MARK_UNSCORABLE = '채점 불가';

/**
 * @param {object} res 확정 라우트의 응답, 그대로
 * @returns {{state: string, text: string}} 한 줄, 또는 비교가 안 실려 온 응답이면 빈 문자열.
 *          `text` 는 «다음에 무엇을 하라»는 문장이 아닙니다 — 방금 무슨 일이 있었는지입니다.
 */
export function confirmRulingNote(res) {
  if (!res || typeof res !== 'object') return NOTHING;
  // ⚠️ 키 «부재»(옛 서버)와 `ruling: null`(이 서버가 「기록 안 했다」고 말함)은 다른 사실이지만
  //    이 화면에는 «같은 답»입니다 — 그릴 것이 없습니다. 그래서 한 줄로 받습니다.
  // 🔴 여기에 `hasOwnProperty` 갈래를 따로 두었다가 «지웠습니다»: 그 갈래를 없애는 변이가
  //    빠져나갔고, 이유는 두 길이 «같은 값»을 내기 때문이었습니다. 등가 변이는 공허한 단언으로
  //    쫓을 것이 아니라 «없앨 코드»입니다 — 갈래가 구별을 주장하는데 답이 하나면 그 주장이 거짓입니다.
  const ruling = res.ruling;
  if (!ruling || typeof ruling !== 'object') return NOTHING;

  const winner = ruling.winner != null && String(ruling.winner) !== ''
    ? String(ruling.winner) : null;
  if (winner === null) {
    // 🔴 기본 문장은 `winner` «하나»가 받칩니다. 「이긴 후보 없음」은 null winner 가 말하는
    //    바로 그것이라, 상태 낱말이 없거나 이 파일이 처음 보는 것이어도 «참으로 남습니다».
    //    상태는 «더 센 말»일 때만 문장을 올립니다: `not_scorable` 은 채점이 «성립조차»
    //    안 했다는 뜻이고, 읽는 사람에게는 「채점했는데 이긴 후보가 없다」와 다른 상황입니다.
    return Object.freeze({
      state: RULING_NO_CANDIDATE,
      text: ruling.state === STATE_NOT_SCORABLE ? MARK_UNSCORABLE : MARK_NONE,
    });
  }

  const confirmed = res.confirmed && res.confirmed.frame != null
    ? String(res.confirmed.frame) : null;
  // 견줄 것이 없는 승자는 «비교가 아닙니다». 아무것도 명명하지 않은 확정은 라우트가 이미
  // 거절하므로(`main.py` D-1), 화면이 답을 지어낼 모양이 아닙니다.
  if (confirmed === null) return NOTHING;

  if (confirmed === winner) {
    return Object.freeze({ state: RULING_ACCEPTED, text: MARK_ACCEPTED });
  }
  // 이름 «둘»을, 일이 일어난 순서로: 기계가 말한 것, 그다음 기록된 것.
  return Object.freeze({
    state: RULING_OVERRIDDEN,
    text: `채점기 ${winner} → 확정 ${confirmed}`,
  });
}

// 🔴 `STATE_NO_WINNER` 를 import 하고 «일부러 갈래로 안 씁니다». `no_winner` 는 이미
//    `winner === null` 이 덮고, 같은 경우에 시험을 하나 더 두면 한 조건의 두 철자가 갈라지기
//    시작합니다. import 해 두는 것은 그 낱말이 이 경우 밑에서 «개명되면 시끄럽게» 하기 위함입니다.
void STATE_NO_WINNER;
