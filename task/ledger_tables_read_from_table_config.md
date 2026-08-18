# [Task] `ledger_config.tables` 제거 — 물리 스키마는 `table_config.json` 하나로

> **상태:** 착수 승인됨 (소유자, 2026-08-18 「a만 해」)
> **소유자 지적:** 「ledger json에 tables 왜 또 있어? table config.json과 다른 거야?」

## 실측 — 다르지 않다. 같은 사실의 두 번째 사본이다

`lot_event`를 양쪽에서 대조한 결과:

| | `ledger_config.tables` | `table_config.json` |
|---|---|---|
| 컬럼 | 8 | 8 |
| 한쪽에만 있는 컬럼 | 없음 | 없음 |
| 타입이 다른 컬럼 | 없음 (8/8 일치) | |
| business_key | `txn_seq` | `txn_seq` |

**두 곳에 같은 것을 적고 아무도 둘을 대조하지 않는다.** 어긋나도 조용하고, 실행할 때만
드러난다 — 오늘 오전에 매퍼와 config 사이에서 이미 한 번 나온 모양이다.

## 판정 — 원장이 `table_config.json`을 읽는다

`ledger_config.json`의 `tables` 섹션을 **없앤다.** 원장이 물리 스키마를 물어야 할 때는
`table_config.json`을 읽는다.

원장이 이 정보를 쓰는 곳은 둘뿐이다:

1. 준비기 `input_columns`가 실재하는 컬럼인지 확인
2. 커서 컬럼이 유일키를 이루는지 확인

둘 다 `table_config.json`의 `column_types`·`business_key`·`composite_key_source`로 답할 수 있다.

### 🔴 실물 DB 대조는 이미 있다 — 새로 만들지 않는다

소유자 지적: 「어차피 c는 드리프트 에러 뜨잖아」. 확인했고 맞다.
`schema_drift`가 **SQLAlchemy가 매핑한 모든 표**를 훑는데 여기에 `table_config.json`에서
만들어진 동적 표가 포함된다(`server/schema_drift.py:25`, `_register_dynamic_models`).
즉 `table_config`에 적힌 컬럼이 DB에 없으면 **이미 잡힌다.**

그래서 원장이 `table_config`를 읽는 순간 **실물 대조가 공짜로 따라온다.**
별도의 「선언 대 DB」 검사를 만들지 않는다. 오늘 검증에서 「지어낸 컬럼이 초록이었다」던
구멍은 이 전환으로 닫힌다 — 원장이 자기 사본을 보는 걸 그만두기 때문이다.

## 걸리는 것 하나 — 인제션이 안 쓰는 표

`void`처럼 **원장만 읽고 인제션은 안 쓰는 표**가 생기면 `table_config.json`에 그 표가
없을 수 있다. 그때의 답은 「원장에 사본을 만든다」가 아니라 **「`table_config.json`에
선언한다」**이다. 그 파일이 이 시스템의 물리 스키마 정본이고, 선언하면 드리프트 검사와
그리드가 함께 따라온다.

즉 새 소스를 붙이는 순서에 한 걸음이 **명시**된다: 먼저 `table_config.json`에 표를 선언하고,
그다음 `ledger_config.json`에 의미를 선언한다.

## 작업 범위

1. `setup_bundle`에서 `tables` 섹션 제거. `LOGICAL_SECTIONS`와 필수 키 목록에서 뺀다
2. 물리 스키마가 필요한 교차 검증(준비기 input, 커서 유일키)을 `table_config.json`
   기준으로 바꾼다
3. 원장이 선언하는 소스의 relation이 `table_config.json`에 없으면 **이름을 대며 거절**한다.
   조용히 통과시키지 않는다
4. 라이브 `server/config/ontology/ledger_config.json`에서 `tables` 섹션을 걷어낸다
   (변환기와 같은 규율: 원본을 지우지 않고, 무엇이 빠졌는지 표로 보고)
5. 가이드 §5(`tables`)를 「이 섹션은 없어졌고 물리 스키마는 `table_config.json`이 정본」으로
   고친다. 새 소스 추가 절차(§10)에 위의 「먼저 table_config에 선언」 걸음을 넣는다
6. `task/evidence/void_source_declaration_draft.json`의 `tables.void`도 같은 판정을 받는다 —
   그 표는 `table_config.json`에 선언되어야 한다

## 합격 기준

- [ ] `ledger_config.json`에 `tables` 섹션이 없다. 일곱 칸이 된다
- [ ] 준비기 input과 커서 유일키 검증이 `table_config.json`으로 답해진다
- [ ] `table_config.json`에 없는 relation을 소스가 가리키면 이름을 대며 거절한다
- [ ] **원자 디프 0** — `lot_event` 원자가 한 글자도 안 바뀐다
- [ ] 가이드에 사본이 둘이라는 서술이 남아 있지 않다

## 비범위

- `table_config.json`의 모양 변경. 그건 인제션·그리드가 함께 쓰는 정본이다
- 새 「선언 대 DB」 검사. 드리프트가 이미 한다
