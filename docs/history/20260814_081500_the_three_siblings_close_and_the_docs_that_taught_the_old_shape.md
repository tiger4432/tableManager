# The three siblings close, and the docs that taught the old shape

**Date:** 2026-08-14 07:59~08:15 · **Domain:** Server (원장 R-H-bis) + 문서 · **Status:** 착지 — `92547c3`, 판정 `5d100e9`, 문서 `3915766`, `e5ff59e`

---

## 구현 (`92547c3`) — 지시서의 서술 둘을 레인이 교정했다

R-H-bis 세 항목 전부. **항목 3은 중복 제거가 아니다** — 스코프 개방 «책임의 이동»이고
개수는 전 1(`translate`) 후 1(`backfill.run`의 분자 루프)이다. 그리고 **오늘 아무
동작도 사지 않는다**: 번역기 클래스 하나, `backfill.run`의 유일한 호출자는 자기 CLI
`main()`, 데몬 0 — grep으로 검증했지 보고로 받지 않았다. 현재 가치 전부가 미래 둘째
번역기 작성자가 맞을 RuntimeError다 — 「구전이 구조가 된다」는 판정의 요점 그대로,
다만 «landed»와 «wired»는 다른 단어다.

**항목 1은 지시서보다 좁다**: 「거절» 반환만 예외가 된다. 할 말이 없던 분자의 `[]`는
반환으로 남고 테스트로 고정 — 둘 다 raise시키는 것은 과적용이었다.

```python
def write_batch(..., refused=0, incomplete=0, *, reasons):  # keyword-only
    if reasons is None:
        raise TypeError(_REASONS_REQUIRED)   # 명시적 None도 거절
```

본문이 `reasons or {}`였어서 기본값 삭제만으론 미끼가 한 타 거리에 남았다 — 그 줄이
`_json(dict(reasons))`가 됐다. 증명 방법이 남길 부분: 이 가드들은 주입 코퍼스에
**일부러 안 넣었다** — 공용 하네스 둘 다 `AssertionError`를 성공으로 읽어 「예외가
난다」를 그 안에서 주장할 수 없다. 대신 옛 모양을 주입해 빨강을 측정: 유닛에서 DID
NOT RAISE, 실PG에서 `assert 0 == 2`(게이트 2 대 드라이버 0 — 계수 없는 손실 경로).
판정 문자 밖의 확장 하나(`_advance_cursor`도 reasons 요구)는 플래그와 함께 수용됐고
`5d100e9`가 **자기 주소에서 집행되는 불변식**으로 승인했다.

## 문서 (`3915766`, `e5ff59e`) — 명백한 재서술이 네 가지로 틀린다

스펙·가이드가 세 모양을 「의도적으로 남김」이라 서술 중이었다 — 이제 거짓. 은퇴
마커로 교체하되 옛 문장은 인용·날짜와 함께 남겨 검색이 어딘가에 착지하게 했다.
레인이 아무 보고서도 안 잡은 거짓 문장 하나를 더 찾았다: 두 문서가 일방향 문 —
예외가 값으로 돌아오는 «유일한» 자리 — 을 `translate`라 했는데 이제 **둘**이다(층이
다르다). 결함이 아니다: 드라이버의 핸들러는 `pending.extend(kept)` 밖에 앉아 unwind가
원자를 남길 수 없다. 살아남는 불변식은 종류가 다르다 — **문 «개수»가 아니라 각 문
아래 삼킴 표현식 없음.** `e5ff59e`는 에이전트가 매 세션 읽는 카탈로그(PRIMITIVES §7)
가 닫힌 위험을 열림으로 분류하던 것을 고치며, 명백한 재서술이 틀리는 네 방향(문
개수 / 이동 대 중복제거 / landed≠wired / 거절 대 무언)+ 방법론 한 줄(이 부류는 유닛
테스트로 안 정착한다)을 새로 적었다. 하중 카운트는 전부 상속 대신 재측정 — `with
gate.building_molecule(` grep 1건은 RuntimeError 메시지 문자열 안이었다.

가이드의 가장 위험한 줄: §3 ③이 새 번역기 작성자에게 `lot_event_translator` 모양을
베끼라 했고 그 모양이 `with`를 들고 있었다 — 오늘 베끼면 RuntimeError. **가이드가
판정이 막으려는 바로 그 실수를 가르치기 직전이었다.**

## 그때 남아 있던 것

- `92547c3` 검증: 원장 패키지 임포트 3파일 126 passed. PG는 `assy_qa` 스크래치
  스키마(teardown 드롭), 하네스가 `assy_manager`를 이름으로 거부.
- `LEDGER_TECHNICAL_SPEC.md:245`의 거짓 블록은 커밋 시점 별도 수리 중이었고
  `3915766`이 그 수리다.
