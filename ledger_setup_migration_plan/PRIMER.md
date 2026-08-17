# 입문 — 한 행의 여행: 모든 구성요소의 역할과 실물 예시

> 실제 DB의 스플릿 행 하나가 원장 원자가 되기까지. 각 요소가 «언제 등장해
> 무엇을 하는지»를 실물로. (03 사전 화면의 원고이기도 하다)

## 0. 출발 — 실물 행 (lot_event 표, 라이브)

```
lot=CL-2601-006 · event_type=split · child_lot=CL-2601-006-A1
slot_numbers="01:02:03:…:25" · wafer_ids="WF.010601:WF.010602:…"
event_time=2026-05-03 02:17
```

이 행은 아직 **뜻이 없다.** 그냥 문자열이다. 아래 요소들이 뜻을 붙인다.

## 1. 여행 순서대로 — 요소 × 역할 × 이 예시에서

| # | 요소 | 정체 (비유) | 역할 | 이 예시에서 실물 |
|---|---|---|---|---|
| 1 | **소스 테이블** | 세계의 수첩 | 사실이 행으로 눕는 곳. 뜻 없음 | 위의 행 |
| 2 | **table_config** | 표의 주민등록 | 이 표의 행을 «하나»로 세는 법 | business_key = lot\|event_type\|event_time |
| 3 | **PROFILE** | 이 소스의 독해 지침서 | 「이 표를 어떻게 읽는가」 전부: 묶음·문장 선택·컬럼 잇기·시각·전제 | unit=row_pair(lot,event_type,event_time) · use lineage/split · occurred_at=event_time(Asia/Seoul) |
| 4 | **엔진 group** | 제본기 | Profile의 UNIT대로 행들을 «분자(한 사건)»로 묶음 — 코드 아닌 선언이 구동 | 부모행+자식행 2행 → 스플릿 분자 1개 |
| 5 | **MAPPER 훅** | 통역사 | (구조 변환일 때만) 분자가 «무슨 뜻»인지 해석해 Claim들로 | split 분자 → Claim(갈라짐: 자식→부모) 1 + Claim(소속: 랏·슬롯·웨이퍼) ×19 |
| 6 | **PACK** | 표준 문장 양식집 | Claim의 빈칸(role)을 받아 **payload 철자로 컴파일**. 사람 문장↔문법의 다리 | 소속 Claim → 술어 has_wafer, payload {keys:{wafer}, qualifiers:{slot}} 로 접기 |
| 7 | **vocabulary.py** | **국어사전 + 문법책** | 아래 §2 상세 | has_wafer 항목: 주어는 Lot만, 목적어는 Wafer ref, 걷기는 「도달만·통과 금지」 |
| 8 | **게이트** | 검문소 | 원자마다 사전(7)의 서명과 대조 — 하나라도 틀리면 **분자 전체** 거절 | has_wafer의 목적어가 Wafer ref인가? qualifiers에 slot 있는가? |
| 9 | **봉투** | 규격 서류 양식 | 모든 원자의 고정 7필드 모양 | 아래 §3의 실물 원자 |
| 10 | **원장** | 등기부 | 통과한 문장이 영구히 눕는 곳. 추가 전용 | ledger_events에 20행 삽입 |
| 11 | **읽기측** | 해석기들 | 걷기·대조·여정이 원자를 «질의 시점에» 해석 | 걷기가 derived_from만 건너 혈통 복원 |

## 2. vocabulary.py — 「아직도 모르겠는」 그것

**원장 언어의 국어사전 + 문법책**이다. 딱 세 가지를 담는다:

**① 낱말 목록 (닫힌 집합)** — 이 원장이 말할 수 있는 동사 전부. 지금 11개
(register, pin, derived_from, has_wafer, slot_map, processed_with, transferred,
observed, measured, has_param + 예약 same_as/frame_confirmed).
목록이 닫혀 있는 이유: 아무나 낱말을 만들면 읽는 쪽이 해석 불능이 된다.

**② 낱말마다 문형(서명)** — 실물 항목:

```python
"has_wafer": {
    "subject": ["Lot"],                          # 주어가 될 수 있는 것
    "object": {"kind": "entity_ref",             # 목적어의 모양
               "types": ["Wafer"]},
    "traversable": False,                        # ③ 걷기 규칙 (아래)
}
"derived_from": {
    "subject": ["Lot"],
    "object": {"kind": "entity_ref", "types": ["Lot"]},
    "traversable": True, "direction": "subject_to_object",   # 걷기가 «건너는» 유일한 낱말
}
```

이 서명이 곧 **게이트의 검사 기준**이다. Pack이 뭘 컴파일하든, 서명에 안 맞으면
원장에 못 들어간다. (그래서 Pack이 틀려도 원장이 오염 안 된다 — 권위는 여기)

**③ 걷기 규칙** — traversable 3상태: True(혈통처럼 재귀로 건넘) /
False(닿으면 주석으로 가져오되 통과 금지 — has_wafer) / None(걷기가 아예 안
가져옴 — observed 10만 개를 혈통 조회에 끌고 오면 죽는다).
**걷기 코드가 아니라 이 선언이 걷기의 행동을 정한다** — 선언과 구현이 어긋나면
걷기는 추측하지 않고 이름을 대며 거절한다.

왜 .py인가: 닫힌 집합을 테스트로 못박기 위해(조용히 자라는 어휘 방지). 지금은
코드 v0 + config 확장(R-M, origin: code|config 구분)의 이중 출처다.

## 3. 도착 — 실물 원자 (라이브 원장에서 인용)

```json
{"predicate": "derived_from", "subject_type": "Lot",
 "subject_keys": {"lot": "CL-2601-006-A1"},
 "object_kind": "entity_ref",
 "object_payload": {"type": "Lot", "keys": {"lot": "CL-2601-006"}},
 "occurred_at": "2026-05-03T02:17:00+09:00", "source_who": "lot_event"}

{"predicate": "has_wafer", "subject_type": "Lot",
 "subject_keys": {"lot": "CL-2601-006"},
 "object_kind": "entity_ref",
 "object_payload": {"type": "Wafer", "keys": {"wafer": "WF.010601"},
                     "qualifiers": {"slot": "01"}},
 "occurred_at": "2026-05-03T02:17:00+09:00", "source_who": "lot_event"}
  … (×19)
```

문자열이던 행이 「CL-2601-006-A1은 CL-2601-006에서 갈라져 나왔다」 + 「01번
자리에 WF.010601이 있다」×19 라는 **검사받은 문장 20개**가 됐다.

## 4. 한 문장 요약

**소스**는 사실을 눕히고, **Profile**은 읽는 법을 선언하고, **엔진**이 묶고,
**Mapper**가 뜻을 해석하고, **Pack**이 문장으로 작문하고, **vocabulary**가
문법을 검사시키고(게이트), **봉투**에 담겨 **원장**에 눕고, **읽기측**이 질의
시점에 해석한다. — 사용자가 만지는 건 Profile(항상)과 Mapper 훅(예외)뿐이다.
