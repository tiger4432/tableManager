# MAPPER 표준 — 묶기의 몰수와 payload의 세 입구

> 2026-08-17 12:18 · Docs / Plan · 커밋 `8254fe7`

## 배경

소유자가 디자인 패턴을 직접 지정했다. 문제의식은 파편화: 「묶음은 어디서
정해지나」에 답이 여러 곳이었고, mapper 훅이 임의 dict를 payload에 밀어 넣을
수 있으면 잎 철자의 정본이 사라져 bindings·labels가 인용할 대상이 없어진다.
Profile-서술 정본화(R-P 제안)와 한 쌍으로, mapper가 자기 서술을 클래스 선언으로
들고 사전·현황판이 그것을 **인용**하는 구조를 표준으로 못 박았다.

## 변경 내용

`MAPPER_STANDARD.md` 신설(110줄). Template Method — 파이프라인 5구간 중 셋은
엔진 공통, 훅은 둘뿐:

```
fetch(커서·워터마크)   → 엔진 공통
group(행→분자)         → 엔진 공통 ← UNIT 선언이 구동  ★표준화의 핵심
interpret(분자→주장)   → 훅 ① (mapper가 구현하는 유일한 자유 코드)
emit(주장→원자 봉투)   → Pack emitter 공통
gate(전량/거절)        → 엔진 공통 (기존 게이트 그대로)
```

**묶기(group)를 mapper에서 몰수해 엔진으로** 올렸다. 묶음 종류는 넷뿐
(row/row_pair/eav_pivot/snapshot_diff — `ef4927c` 분류표의 기계판)이고, mapper는
선언만 한다:

```python
class LotEventMapper(LedgerMapper):
    UNIT = Unit(kind="row_pair", group_by=("lot", "event_type", "event_time"),
                doc="스플릿·머지 1건 = 부모행 + 자식행")
    EMITS = (Emit("derived_from", per="molecule", sentence="…"), ...)
    REQUIRES = ()
    def interpret(self, molecule) -> list[Claim]: ...
```

payload에 잎이 생기는 길은 선언된 셋뿐 — ① Pack 컴파일 규칙(role→골격 잎),
② Profile 수송 잎(`"payload.inchip_x": "column:inchip_x"`), ③ interpret 계산값도
**role로만** emitter에 전달. 훅이 봉투를 직접 조립하는 넷째 길은 금지다. 선언이
장식이 되지 않게 하는 자물쇠 셋: 엔진이 UNIT으로 묶고, 드라이런이 EMITS를
대조해 어긋나면 이름 붙은 거절이며, UNIT·EMITS 없는 클래스는 registry가
등재를 거부한다.

## 아키텍처 영향

문서 전용이나 계약의 무게가 크다: **잎 철자의 정본 = claim 정의**로 확정되어
bindings(기전)·labels(이름)는 인용자, 합의 검사기(06)는 인용 실측자로 역할이
갈렸다. 계획 반영으로 1단계에 「기존 lot-event mapper를 이 표준으로 개주 + 개주
전/후 디프 0」이 표준의 첫 실증으로 편입됐다.

## 그때 남아 있던 것

- `LedgerMapper` 베이스·`Unit`·`Emit`·registry 거부 로직 전부 미구현 — 이
  커밋 시점의 실물 `ledger_lot_event_mapper.py`는 아직 이 표준 이전 모양이었다.
- 엔진 group 4종 중 실제로 걸어 본 것은 없었다(기존 mapper는 자기 코드로 묶고
  있었다).

## 검증

문서 전용 커밋 — 테스트 스위트 실행 없음.
