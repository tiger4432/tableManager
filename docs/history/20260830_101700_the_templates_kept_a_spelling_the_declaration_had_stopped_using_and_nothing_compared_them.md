# 템플릿이 «선언이 그만 쓴 철자»를 들고 있었고, 그 둘을 비교하는 것이 아무것도 없었다

> **커밋:** `50be7eb6` (10:13) · `2f0f5deb` (10:17)
> | **일자:** 2026-08-30 오전
> **레인:** 서버(내장 템플릿 · 시험 앵커) + 시험 수리 레인 지시서
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 선언이 2026-08-27 에 엔티티 타입의 정본이 됐고, 이름을 «맨 소문자»로 부른다

내장 소스-프로필 템플릿 «둘»이 `entity_types` 에 옛 대문자 철자를 그대로 들고 있었다.

```python
# server/ledger/source_profile_builtins.py — default_profile_registries()
TemplateDefinition(name="lot_lineage", label="Lot 분할·병합",
                   entity_types=("lot",),  ...)   # 전: ("Lot",)
TemplateDefinition(name="transfer",     label="개체 이동",
                   entity_types=("wafer",), ...)  # 전: ("Wafer",)
```

🔴 **템플릿의 엔티티 타입을 타입 레지스트리와 대조하는 것이 아무것도 없다.**
그래서 이 표류는 **프로필이 실제로 파싱될 때까지 보이지 않았고**, 그때의 증상은 이렇게 나왔다 —
`_parse_entity` 가 타입을 **잘 풀어 놓고** 거절했다.

```
entity type 'lot' is not supported by template 'lot_lineage'
```

**소문자 `lot` 이 해석은 됐는데 템플릿이 대문자 `Lot` 만 안다고 말하는** 모양이라,
메시지만 보면 선언 쪽이 틀린 것처럼 읽힌다.

## 🔴 시험 앵커 둘 — «같은 부류로 묶으면 틀린다»

탐색기 시험이 라이브 선언에 더는 없는 앵커 둘을 들고 있었는데 **둘의 성질이 달랐다.**

```
entity|Lot@1        같은 개명이다 -> entity|lot@1
split_slot_carry    개명이 «아니다». 그 매핑은 «없어졌다»
                    (7e23677d 가 라이브 선언들을 샘플로 복사하면서)
```

그런데 그 단언들이 «무엇에 대한» 것인지 보면 **술어 `slot_map@1` 이고, 그것은 살아 있다** —
`lot_slot_move#seat-to-seat` 가 낸다. 그래서 앵커를 **술어를 따라** 옮겼다.

```python
# server/tests/test_ontology_config_explorer.py — 옮긴 뒤
"profile|lot_slot_move#profile",
"mapping|lot_slot_move#profile#mapping:seat-to-seat",
"binding|lot_slot_move#profile#mapping:seat-to-seat#binding:subject",
"table|lot_slot_move",
```

**살아 있어 보이는 이름으로 갈아 끼운 것이 아니다.** 단언이 «모양»을 지키는 대신 «주어»를 지켰다.

## 측정

```
test_source_ontology_profile      7 failed  ->  0
test_ontology_config_explorer     6 failed  ->  2
전수                              31 red    ->  21
```

남은 둘은 **다른 부류**라고 이름 붙였다 — 하나는 `lot_event` 의 event 단위 매퍼가 표현하지 못하는
`in_slot` 바인딩, 다른 하나는 라이브 `dt_job` 선언이 자기 `group_by` 검사에 걸리는 것.

> 이 항목 작성 시 재측정: `tests/test_source_ontology_profile.py` + `tests/test_ontology_config_explorer.py`
> -> **2 failed · 106 passed.** 빨강 둘은 위에 이름 붙은 그 둘이다.

## 남은 21 을 레인에 넘겼다 — 규칙 «둘»과 함께

`2f0f5deb`. 지시서(`task/TEST_REPAIR_BRIEF.md`)가 착수 «전»에 알아야 할 둘을 앞에 놓았고,
둘 다 비싸게 배운 것이다.

```
① 이 박스의 라이브 선언은 gitignore 이고 «소유자의 것»이다
② 핀이 가리키던 주어가 «움직인» 것은 «수리»가 아니라 «판정»이다
```

21 중 «넷»은 지시서 안에서 이미 진단해 두었다 — 이 세션이 잰 것을 레인이 자기 라운드에서
다시 도출하지 않도록.

## 아키텍처 영향

- 내장 템플릿의 엔티티 타입이 **선언과 같은 철자**를 쓴다.
- 탐색기 시험의 앵커가 **살아 있는 술어**를 따라간다 — 이름이 아니라 주어를 좇는다.

## 그때 남아 있던 것

- **템플릿의 `entity_types` 를 타입 레지스트리와 대조하는 것은 여전히 없다.**
  이번에 고친 것은 값이고, 값을 지키는 자리는 생기지 않았다.
- 전수 빨강 **21**. 그중 넷만 진단됐고 나머지는 이 시점에 이름만 있다.
- `in_slot` 롤프레임 결함과 `dt_job` 의 `group_by` 는 이 시점에 **열려 있다.**
