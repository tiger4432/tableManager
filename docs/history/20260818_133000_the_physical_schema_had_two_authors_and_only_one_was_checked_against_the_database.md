# 물리 스키마에 저자가 둘이었고, 데이터베이스에 대조되는 쪽은 하나였다

**날짜:** 2026-08-18 12:34~13:28 · **커밋:** `c7eca0d` `b090056` `fab045a` `2b541dd` `ede69d1`
**레인:** 서버(원장 단순화 1라운드 마무리) · **측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 소유자의 한 문장

> **「`tables`가 왜 원장 json에도 있지?」**

오전에 다섯 파일이 한 파일이 되면서 `catalog/tables.json`의 내용이 그 파일의 여덟째 칸으로
들어갔다. 그런데 물리 스키마는 **이미 `server/config/table_config.json`에 있었다.**
파일 수를 줄인 것이 사본 하나를 **더 잘 보이는 자리로 옮겼을 뿐**이었다.

## 실측 — 두 사본은 그때까지 같았다. 그게 위험한 부분이다

`2b541dd`가 제거 «전에» 라이브 루트에서 잰 것을 코드 옆에 남겼다.

```
Measured on the live root before removal: its one relation was a COMPLETE duplicate of the
catalog entry -- 8 columns, 8/8 types agreeing, the same single-column business key -- and
no RUNNING code compared them.  (One test did, for that one relation; a hand-kept pin over
one row says nothing about the next one, and said nothing about the sample root, whose copy
had drifted into columns that exist nowhere.)
```

**한 관계는 일치했고, 샘플 루트의 사본은 이미 어긋나 있었다** — 어디에도 없는 컬럼으로.
같은 사실을 두 곳에 적어 두면 「지금 같다」는 관측은 「계속 같을 것」을 뜻하지 않는다.

## 🔴 이건 중복 제거가 아니라 «검증되는 쪽»으로 옮긴 것이다

여기가 이 커밋의 핵심이고, 「사본 하나 줄였다」로 요약하면 잃어버리는 부분이다.

```
`server/schema_drift.py` (`_register_dynamic_models`) sweeps every SQLAlchemy-mapped table,
and that set INCLUDES the dynamic tables built from this file.  So a column named here that
the database does not have is already reported.  A column named in a ledger-private `tables`
section was checked against nothing, which is how an invented column name came to pass green
(measured 2026-08-18).
```

`table_config.json`에 적힌 컬럼은 **데이터베이스에 대조된다.** 원장 전용 `tables`에 적힌
컬럼은 **자기 자신에 대조됐다.** 그래서 지어낸 컬럼 이름이 초록으로 통과할 수 있었고,
실제로 그랬다.

그리고 **두 번째 검증기를 만들지 않은 것**도 판정이다 — 「선언 대 DB」 검증기를 하나 더 두면
서로 어긋날 수 있는 검증기가 둘이 되어 출발점으로 돌아간다.

## 번역 규칙이 각각 왜 그런 규칙인지

`load_physical_catalog`의 docstring이 규칙마다 이유를 붙였다. 두 개가 특히 헷갈리는 자리라
명시됐다.

- `composite_key` ← `composite_key_source`. 그 목록이 **행의 정체**다 —
  `crud.assemble_composite_business_key`가 이어 붙여 `business_key_val`을 만드는 바로 그
  튜플이므로, 그것을 덮는 것이 정렬을 유일하게 만드는 것과 같은 말이다.
- `business_key` ← `business_key`, **단 그것이 선언된 컬럼일 때만.** 이 멤버십 검사는
  `chain_bindings.identity_column`이 쓰는 게이트와 **바꿔 쓸 수 있어 보이지만 다른 질문**이다.
  저쪽은 「어느 컬럼이 잡을 나르나」라서 조립된 셀 키를 거절해야 하고, 이쪽은 「어느 튜플이
  유일한가」라서 **자기 컬럼으로 실체화된 조립 키는 유일하므로 인정된다.** 라이브 카탈로그의
  세 관계가 둘 다 선언하고 있어 실제로 갈리는 자리다.
- ⚠️ `map_key_columns`는 **키로 번역하지 않는다.** 조회 접두사(맵 하나에 행 여럿)라서 이걸
  인정하면 **유일하지 않은 정렬을 커서로 승인**하게 되고, 그건 이벤트를 잃는 유일한 방향이다.

그리고 이 모듈은 **경로를 스스로 알아내지 않는다.** 알아내려면 `paths`를 import해야 하고,
「런타임을 전혀 import하지 않는다」는 이 모듈의 계약에는 테스트가 붙어 있다. 「어느 데이터
루트인가」는 배포 질문이라 한 층 위(`ledger.setup`)에서 답한다.

## 거절문은 결함이 아니라 «행동»을 말해야 한다

`ede69d1`. `tables`를 남겨 둔 config는 `unknown_field: field is not allowed`로 거절됐다.
그 문장을 받는 사람은 **어제까지 맞던 config를 든 채 운영 박스에 서 있는 사람**이다.

```python
_RETIRED_FIELD_HELP = {
    "ledger_config.tables": (
        "field is not allowed - the 'tables' section retired on 2026-08-18. "
        "Physical schema is declared once, in server/config/table_config.json, and the "
        "ledger reads it from there. Delete this section; do NOT copy its contents "
        "anywhere. ..."),
}
```

**「어디로 옮겨 적어라」가 아니라 「옮겨 적지 마라」**가 핵심 문장이다 — 사본을 만들지 않는
것이 이 변경의 목적이므로, 거절문이 사본을 유도하면 변경이 되돌아간다.

## 오늘 밤이 착지하면 «이 박스»에서 무엇이 멈추는가

`b090056`가 그 질문을 문서로 세우고 `fab045a`가 답하는 도구를 만들었다.

```
Whether that is harmless or a stoppage depends on what this box is standing on, and that
cannot be answered from a developer machine.  Run this here, on the box you are about to
deploy to, and it will say which case it is.
```

읽기만 한다. **원장을 import하지 않으므로 새 코드가 배포되기 «전»에도 돌릴 수 있다** —
이것이 프리플라이트가 프리플라이트인 이유다. 세 가지 config 모양 중 어느 것인지, 커서 행이
있는지를 그 박스에 대고 묻는다.

## 아키텍처 영향

`LOGICAL_SECTIONS`가 여덟에서 **일곱**이 됐다. 물리 스키마의 저자는 시스템 전체에 하나
(`server/config/table_config.json`)가 됐고, 인제션·체인 워커·그리드·원장이 같은 파일을 읽는다.
원장은 **자기 사본도 자기 검사기도 갖지 않는다.**

## 검증

- 기록자가 직접 확인한 것: 위 인용문들이 각 커밋 diff에 실재한다는 것, `2b541dd`가 라이브·
  샘플 두 `ledger_config.json`에서 `tables` 섹션을 지웠다는 것(−15 / −37줄).
- ⚠️ 「8/8 타입 일치」와 「샘플 사본이 없는 컬럼으로 어긋나 있었다」는 **커밋이 제거 전에 잰
  값**이다. 기록자가 재측정하지 않았고, 제거 후에는 재현할 대상이 없다.

## 그때 남아 있던 것

- `c7eca0d`가 남긴 `task/ledger_tables_read_from_table_config.md`가 이 판정의 지시서다.
- 프리플라이트는 **운영 박스에서 아직 돌지 않았다.** 이 항목이 기록하는 것은 도구가 생겼다는
  사실이지 어떤 박스가 어느 경우인지가 아니다.
- 이 시점의 여덟→일곱 축소는 **작성 화면과 무관하게** 이뤄졌다. 작성 화면이 이 일곱 칸을
  어떻게 보여 줄지는 그날 밤 다른 커밋들의 문제다.
