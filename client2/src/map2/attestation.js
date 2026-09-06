// F-19 — 「누가 이 프레임을 «확정»했나」의 한 자리.
//
// 🔴 왜 이 파일이 있나. 이 판정이 `main.js` 의 `bootstrap()` 안 클로저에 살아서, 채점하려면
//    DOM 을 통째로 세워야 했습니다. 표준 규율은 「재려는 로직을 import 되는 모듈로 뺀다」이고,
//    총괄이 지목한 선례(`retry_verdict.js`)와 «같은 모양»입니다.
//
// 🔴 이 라운드가 닫는 문장: **같은 맵을 오버레이는 「확정됨」이라 그리는데 확정 워크리스트는
//    「pending」이라 그립니다.** 사유는 `declared_frame_source === 'confirmed'` 가 «사람 확정»과
//    «체인 표지»를 «구별하지 못하기» 때문입니다 — 체인 맵퍼 둘이 같은 토큰을 찍습니다.
//
// ⛔ 토큰(`GEOMETRY_CONFIRMED`)을 «가르지» 않습니다 (총괄 판정 29) —
//    `map_alignment.py` 가 그것을 «신뢰 토큰»으로 읽어, 가르면 «정렬 동작»이 움직입니다.
//    가르는 것은 토큰이 아니라 «질문»입니다: 「프레임이 있나」와 「사람이 확정했나」.
//
// ⚠️ 프레임은 «체인 표지 맵에도 참»입니다. 그래서 마크(✓)만 떼고 «값은 그대로» 그립니다 —
//    「고르지 않음」으로 떨어뜨리면 거짓 문장 하나를 «다른 거짓 문장»으로 바꾸는 것입니다.

/**
 * 이 출처 행이 프레임에 대해 «무엇을 말해야» 하나.
 *
 * @param {object} src  적응된 출처 행 — `stored_candidate_id` · `confirmed_candidate_id` ·
 *                      `confirmed_by_person` 를 읽습니다.
 * @param {(id: string) => string} spellFrame  후보 id 를 사람이 읽는 프레임 문구로.
 * @returns {{attest: 'declared'|'confirmed'|'attested'|'none', text: string, mark: boolean}}
 *
 * 🔴 `mark` 가 이 라운드의 «전부»입니다. `attest` 와 `text` 는 그것에서 따라옵니다 —
 *    그래서 셋이 «갈라질 수 없습니다».
 */
export function sourceFrameAttestation(src, spellFrame) {
  const declared = (src && src.stored_candidate_id) || null;
  // 🔴 선언이 «이깁니다». 선언된 프레임은 확정 마크를 달지 않습니다 — 그 둘은 다른 사실이고,
  //    오늘 동작이 그렇습니다(`!declared &&` 가 원래 조건이었습니다).
  if (declared) return { attest: 'declared', text: spellFrame(declared), mark: false };

  const confirmed = (src && src.confirmed_candidate_id) || null;
  if (!confirmed) return { attest: 'none', text: '고르지 않음', mark: false };

  // 🔴 «엄격히» true 일 때만. 없는 칸(옛 서버)은 「사람이 확정 안 함」이지
  //    「아무도 안 한 확정」이 아닙니다.
  const mark = (src && src.confirmed_by_person) === true;
  return {
    // ⚠️ `attested` 는 오늘 «아무도 안 읽는» 속성의 넷째 값입니다 (실측: `data-me2-attest` 는
    //    이 저장소에서 «쓰기만» 하고 스타일시트·마크업·하니스 어디서도 안 읽습니다).
    //    `none` 으로 접지 않는 이유는 그것이 «거짓»이기 때문입니다 — 프레임이 있습니다.
    attest: mark ? 'confirmed' : 'attested',
    text: mark ? `✓ ${spellFrame(confirmed)}` : spellFrame(confirmed),
    mark,
  };
}
