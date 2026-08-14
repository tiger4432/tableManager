# The client asked the state word whether the walk had moved

**Date:** 2026-08-14 08:12 · **Domain:** Client (원장 E1) · **Status:** 착지 — `4d9b912`

---

## 배경

E1: client2가 `basis: {kind, name}`를 유도하는 대신 **와이어에서 읽고**, `contested`
팔을 얻는다. 핸드오프는 추론 사이트 둘을 이름 댔다 — 실제로는 **일곱** + 픽스처 셋 +
하네스였고, 핸드오프가 못 댄 둘이 커밋의 값어치다.

## 안 댄 두 결함

1. `hasLineageStep`이 「걷기가 실제로 움직였나」를 `h.state === 'resolved'`로 판정했다.
   걷기는 `res.answer`를 따르고 그것은 `contested`·`candidate`에서도 non-null이다 —
   유일한 혈통 스텝이 계쟁이던 사슬이 「등재됐으나 혈통 주장 없음」 헤드라인을 받았다:
   **부모를 찾은 걷기가 부모 없음을 통보.** `candidate`에서 이미 틀려 있었고 셋째 상태
   단어는 열린 구멍을 넓혔을 뿐이다. 이제 `nodeId(h.to) !== null` — 걷기 자신의 이동
   기록 — 에 키잉되고, 다음 어휘 성장에 낡을 수 없다.
2. `renderSummary`가 칩의 **톤**을 버킷 키로 썼다 — 반대와 이견이 불일치 색을
   공유하므로 한 페이지에 공존할 수 없었다. 표현에 키잉된 렌더러에 착지하는 어휘
   확장은 두 값이 충돌할 때까지 안 보인다.

## 레인이 지시서의 전제를 교정했고, 그것이 계약의 더 날카로운 진술이다

`contested`는 관례-근거 승자를 가질 수 없다: class 3이 최하위라 class-3 승자에겐
반대할 하위 계급이 안 남는다. `contested ⟹ basis.kind !== 'convention'` — 그래서
contested는 basis가 state에서 유도 불가함을 보일 «틀린» 자리다. 둘이 눈에 보이게
갈라지는 유일한 곳은 **RESOLVED 쌍**(하나는 measured, 하나는 convention-backed)이고,
화면에서 검증된 것이 그 쌍이다: 같은 `data-state="resolved"`, 독립 신호 셋(칩 근거/
가정, 실선/점선 테두리, 레일)으로 분리, 다크 테마 재확인. 계쟁 hop은
`data-basis="measured"`에 실선인데 자기 reason 문장엔 `convention:slot_preserving` —
**진 쪽의 basis** — 가 있다. 이 축이 닫으러 존재하는 바로 그 역전이다.

## 그때 남아 있던 것

- 픽스처는 둘이 아니라 셋이 `basis` 이전이었다 — `ledger_trace_nothings.json`도 실서버
  출력이라 방치 시 레거시 접미사 경로를 탔을 것.
- mutant 둘이 처음에 「던져서 잡힘」(문서화된 throw 함정) — 이름 단언 실패로 재무장.
  323 passed, 55/55 mutant, 대조군 2/2 탈출. `npm run build` exit 0, 옛 번들 삭제가
  새것과 같은 커밋, 변경 문자열의 minified 출력 내 존재 확인.
- 레거시 접미사 폴백은 **남겼다**: `basis`가 무버전 출하라 pre-`5bacdfc` 서버 앞의
  클라가 아니면 가정 표시를 통째로 멈춘다 — 이 축이 막으려는 유일한 것. 키 «부재»
  에서만 도달하고, `basis: null`은 서버의 「선언된 basis 없음」으로 액면 수용.
