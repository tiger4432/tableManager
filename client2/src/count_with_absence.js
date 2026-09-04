// 「수 + «그 0 이 무엇인지»」를 그리는 «한 곳».
//
// 🔴 왜 부품인가: 「0 인데 일감이 있다」가 네 탭에서 «따로» 생겼고, 그때마다 그 화면이
//    «자기 문장»을 썼습니다. 다섯 번째를 손으로 쓰지 않으려고 여기 하나로 모읍니다
//    (상설: 「근원 템플릿 요소 개발 후 데이터 갈아끼우기」).
//    그래서 이 파일에는 도메인 낱말이 «하나도» 없습니다 — 부르는 쪽이 선언합니다.
//
// 🔴 그리고 «만드는» 것이 아니라 «잇는» 것입니다: 서버가 부재 어휘를 «닫힌 목록 여섯»으로
//    이미 값으로 냅니다 (`retroactive.ABSENCE_WORDS`). 읽는 화면이 0 이었습니다.
//
// ⛔ 문장을 늘리지 않습니다. 「0」 옆의 «한 낱말»입니다.
// ⛔ 못 읽은 것은 «0 이 아닙니다» — 철자는 `absent.js` 하나뿐입니다.

import { ABSENT, isCount } from './absent.js';

/**
 * 서버의 닫힌 목록 여섯. 🔴 «토큰 -> 운영자가 읽는 낱말» 이고, 그 대응은
 * `task/APPLICATION_RUN_WORDS.md` 가 정본입니다 — 여기서 지어낸 것이 «하나도» 없습니다.
 * ⚠️ 모르는 토큰은 «그대로» 내보냅니다. 아는 여섯으로 접으면 새 낱말이 조용히 사라집니다.
 */
export const ABSENCE_WORDS = Object.freeze({
  not_yet: '아직',
  not_exhaustive: '전수가 아님',
  cannot_point: '가리킬 수 없음',
  truly_none: '정말 없음',
  already_missing: '이미 빠져 있음',
  not_applicable: '해당 없음',
});

/**
 * @param {{value?: *, absence?: *, unread?: *}} decl  부르는 쪽의 «선언»
 *   value    셀 수 (없으면 `—`)
 *   absence  그 수가 0 일 때 «무엇의 0 인가» — 서버 토큰이거나, 부르는 쪽이 «선언한» 낱말
 *   unread   못 읽었으면 여기에 이유. 그러면 수를 «안 그립니다»
 * @returns {{text: string, word: string, read: boolean}}
 */
export function countWithAbsence(decl = {}) {
  if (decl.unread) {
    // 「못 읽었다」는 「0」이 아닙니다. 수를 그리지 않고, 못 읽은 사유가 그 자리에 섭니다.
    return Object.freeze({ text: ABSENT, word: String(decl.unread), read: false });
  }
  const has = isCount(decl.value);
  const number = has ? String(Number(decl.value)) : ABSENT;
  // 🔴 부재 낱말은 «0 일 때» 뜻이 있습니다. 0 이 아닌 수 옆에 붙이면 그 수를 부정합니다.
  const wants = has && Number(decl.value) === 0 && decl.absence != null && decl.absence !== '';
  const raw = wants ? String(decl.absence) : '';
  const word = raw
    ? (Object.prototype.hasOwnProperty.call(ABSENCE_WORDS, raw) ? ABSENCE_WORDS[raw] : raw)
    : '';
  return Object.freeze({
    text: word ? `${number} · ${word}` : number,
    word,
    read: has,
  });
}
