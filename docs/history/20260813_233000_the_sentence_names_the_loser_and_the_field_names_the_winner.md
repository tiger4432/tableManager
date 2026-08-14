# The sentence names the loser, and the field names the winner

**Date:** 2026-08-13 22:57 / 23:30 · **Domain:** Server (원장 E0) · **Status:** 착지 — 승인 `4983b58`, 구현 `5bacdfc`

---

## 승인 (`4983b58`) — enrich 접목의 페이즈

추적 결과가 교정 표면으로 흐른다: dt lot/slot 미상 행이 추적 유도 후보를 **근거와
함께** 받고 사람이 한 클릭으로 확정 — 눈으로 하던 n-hop 조회가 근거 첨부 한 클릭이
된다. **E0이 라우트 계약을 한 번만 움직인다** — `basis`와 `contested` 분리를 한
커밋에(따로 실으면 계약이 두 번 흔들린다 — R-C가 `basis`를 미룬 정확한 이유).
E1은 실체화 없이(한 행 추적은 한 자리 ms), 확정은 **기존 수동 편집 경로**로(수동 >
자동 유지, 쓰기가 근거를 기록 — 액션 스키마의 첫 실인스턴스). 🔴 강성 규칙: 관례
위나 계쟁에 앉은 hop은 근거로 렌더되되 **행을 미리 확정 표시하지 않는다** — 가정
기반 후보가 정확히 사람 눈이 필요한 행이다. E2는 실체화 대기, E3(청정 사슬 자동
확정)은 자기 검토 등급을 가진 체인 워커급 동작이라 전면 보류.

## 구현 (`5bacdfc`)

```
reason: "[contested] class=2 observation 답 9 · 하위 계급 반대 1종
         (3(convention:slot_preserving)) · 1순위 9 · basis=pair_field"
basis:  {"kind": "measured", "name": "pair_field"}
```

역전이 닫혔고 논증이 아니라 시연됐다: `convention:`은 문장 안에 있고 **진** 주장의
것이다. 필드는 **승자**를 서술한다 — 클라 정규식이 거꾸로 읽던 바로 그것.
**그리고 `basis`는 `state`에서 유도할 수 없다** — 아무도 반박 않는 관례-근거 hop은
`resolved`, 완전 측정 hop과 같은 단어다. 필드가 존재해야 하는 이유 전부다.

`kind`는 `is_convention_backed` — **계급을 결정하는 그 목록** — 이 정하므로
`kind == "convention" ⟺ class 3`이고, `basis.name`이 분류를 탈출한 파생의 둘째 무른
등록부가 될 수 없다. 단어 규칙:

```
resolved   n == 1
contested  최상 계급 만장일치, «하위» 계급이 반대   → 승자가 «선언»됐다
candidate  최상 계급이 k갈래                     → 타이브레이크만 결정했다
```

**둘 다인 hop은 `candidate`다** — 자기 자신과 불일치한 최상 계급은 아무것도 선언하지
않았다. 약한 단어가 이기고 반대는 여전히 `reason`에 이름 대고 `n`에 계수된다.

무버전·무게이트는 의도다: R-B 2항이 이 확장을 예고했고 유일한 소비자는 그것을 위해
지어졌다(미지 상태는 `gap`으로 강등, `ok`로는 절대). ⚠️ 전이 창은 실재하되 측정상
비었다: `assy_qa` 자연 데이터 16랏/278 hop에 contested **0**(195 resolved / 77
unresolvable / 6 candidate) — 이 원장엔 class-1 주장 없는 번역기 하나뿐이라 버리는
스키마에서 만들어야 보였다. **지시서 교정**: `CL-2601-005-A5` slot 02는 자연 계쟁이
아니라 분열 최상 계급 = `candidate` — 총괄이 계쟁 예시로 이름 댄 것이 다른 쪽이었다.

## 그때 남아 있던 것

- 검증: 224 passed, 2 skipped(기준선 213/2, +11 — 스킵 무변동이라 PG 절반이 실제로
  돌았다). 해소 순서 무접촉: 같은 rank key, 전 입력 같은 승자. 키셋 핀은 바닥이
  아니라 정확치가 됐고 차이를 모는 테스트 포함.
- 클라 핸드오프 전문이 기록됐다: 정규식은 `ledger_trace_core.js`에 있고, `kind`는
  정규식이 `'basis'`를 내던 자리에서 `'measured'`이고, `hopVerdict`·`summarize` 둘 다
  `contested` 팔이 필요하며, 캡처 픽스처 둘 다 `basis` 이전이다. (E1은 `4d9b912`.)
