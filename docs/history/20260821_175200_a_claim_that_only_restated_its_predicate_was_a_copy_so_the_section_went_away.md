# 주장이 술어를 옮겨 적기만 했으므로, 그 절을 통째로 지웠다

> **커밋:** `9b6c5da0` (17:52) · `b11d3ce6` (19:33) | **일자:** 2026-08-21 저녁
> **레인:** 서버(원장 설정 문법) + 클라(탐색기)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **검증:** 서버 **286 passed** · 작성 하니스 **44/0** · 마이그레이션 재실행이 두 설정 모두
> **변화 없음** 보고 · 여섯 문장이 여전히 여섯 술어에 닿음
> **앞 항목:** [문장에 별명이 붙자…](20260821_073200_a_sentence_got_a_nickname_and_the_structure_search_had_nothing_left_to_do.md)

## 배경 — 「닿을 수 없다면 선언도 닿으면 안 된다」의 세 번째 적용

> 소유자: 「packs 도 아예 삭제 가능하네. claims 도 필요없고. 그냥 맵퍼가 say 한 문장 id 에
> vocab 만 달아주면 되는 거 아님?」

`packs` 절은 문장마다 **어떤 역할을 묶는지**와 **어떤 발화를 내는지**를 선언했다. 둘 다
그 문장이 가리키는 **어휘 항목이 이미 함의**하고 있었다.

🔴 **지우기 «전에» 쟀다.** 라이브 설정의 다섯 술어 중 **두 개의 서로 다른 역할 집합으로
쓰인 것은 0개**, claim 의 모든 qualifier 이름이 그 술어의 `object.qualifiers`와 **글자 단위로
일치**, `emit` 절 여섯 중 **다섯이 `$subject`/`$occurred_at` 그대로**였다. 여섯째만 자기
끝점을 `$child`/`$parent`로 철자했고, 그래서 이 라운드가 그것을 `subject`/`target`으로
개명했다 — 매퍼는 위치로 넘기므로 **손대지 않았다.**

## 세 절이 서로 동의하는 대신, 한 함수가 파생한다

소스는 이제 `mappings.<sentence> = {predicate, bind}`라고만 말하고,
`setup_bundle.predicate_claim` 하나가 **컴파일러·검증기·작성 계획에 같은 파생**을 건넨다.

```python
def predicate_claim(predicate_id: str, predicate: Any) -> dict[str, Any]:
    """The Roles and the emission ONE predicate forces -- the Claim, with nobody to say it.

    🔴 THIS FUNCTION IS WHAT `packs` USED TO BE ...  Measured before removing the section:
    of the five predicates in the live config, ZERO were used with two different Role sets,
    every qualifier name in a Claim's `roles` matched its predicate's `object.qualifiers`
    character for character, and five of six `emit` clauses were verbatim."""
```

```python
 LOGICAL_SECTIONS = (
-    "vocabulary", "entities", "packs", "sources",
+    "vocabulary", "entities", "sources",
 )
```

**화면도 그것을 읽는다.** 술어를 고르면 그 술어가 **강제하는 슬롯이 선언된 이름 그대로**
깔린다. 이것이 절 삭제를 「작성자에게 짐을 넘기는 것」이 아니라 **작성자에게도 단순화**로
만드는 절반이다.

`object.kind`가 목적어 슬롯을 결정한다 — `entity_ref`면 `target`이 열리고, 값 종류면
`value`가 열리고, `none`이면 **둘 다 안 열린다.** 그래서 `register@1`은 **비워 둘 target
칸을 받지 않는다.**

## 마이그레이션이 «지우고 있는 절에서» 새 이름을 읽는다

`scripts/migrate_ledger_config_to_v5.py`는 새 이름을 추측하지 않고 **삭제하는 `emit` 절에서
꺼내 읽는다.** 그리고 claim 과 술어가 **어긋나는 파일은 거절한다** — 그 파일에 대해서는
이 라운드의 전제가 거짓이기 때문이다.

## 같이 간 것 — 카탈로그가 `row_id` 가 PK 임을 몰랐다

🔴 실측 2026-08-21: PostgreSQL 의 **26개 표 중 26개**가 `PRIMARY KEY (row_id)`를 갖고,
카탈로그에 그것을 선언한 표는 **0개**였다. 그래서 두 소비자
(`_table_has_unique_key`·`_columns_cover_declared_unique_key`)는 **영원히 빈 가지**였고,
**어떤 소스도 카탈로그가 받아 줄 재개 가능 커서 정렬을 이름 붙일 수 없었다.**

⚠️ **컬럼도 같이 넣었고 그건 편의가 아니다.** `column_types`는 **업무** 컬럼을 이름 붙이고
`row_id`는 인제션 프레임워크 자신의 정체성이라 26개 중 0개가 그것을 나열한다. 이 블록의
**첫 판본은 `"row_id" in columns`로 가드했고 그래서 모든 표에서 죽어 있었다** — 정확히 이
블록이 제거하려던 그 결함, **영원히 거짓인 가지**다.

## 41분 뒤 — 소유자가 화면을 열었고 아무것도 못 봤다

```
TypeError: e.plannedMembers is not a function
```

`renderReadTree`는 작성 컨텍스트가 제공하는 모든 함수를 **스텁으로** 채운 읽기 전용
컨텍스트를 만든다 — `planRow`·`declared`·`rolesNear`·`renderRow`·`suggest`. packs 라운드가
`plannedMembers`와 그 호출 지점을 추가하면서 **작성 컨텍스트만 갱신하고 이쪽은 안 했다.**
호출 지점의 가드는 `keyed_by === 'index'` 하나뿐인데, **소스 안의 맵은 대부분 이름으로
키잉**되므로 항목을 열면 그리기 전에 던졌다.

부류로 판정했다 — 그 파일의 `context.<name>` **13개를 전부 열거**해 두 제공자에 대조했다.
`append`는 같은 변수명의 DOM 엘리먼트 소유이고, `readOnly`는 작성 쪽에 **일부러** 없으며,
나머지는 양쪽에 다 있다. `plannedMembers`가 유일한 진짜 구멍이었다.

🔴 **이것이 소유자에게 닿은 이유를 적어 둔다.** packs 라운드의 화면 시험 4·5번이
재기동에 막혀 있었고, **재기동은 했는데 그 뒤에 아무도 화면을 걷지 않았다.
소유자가 테스터가 됐다.**

## 아키텍처 영향

- 논리 섹션이 **셋**(`vocabulary`·`entities`·`sources`)이 됐다. 문장 → 술어가 **직접
  참조**이고 팩/주장이라는 중간 주소가 없다.
- `setup_version` 4 → 5.
- 읽기 전용 트리 컨텍스트와 작성 컨텍스트는 **같은 이름 집합을 제공해야 하는 쌍**임이
  이 사고로 기록됐다.

## 그때 남아 있던 것

- `packs` 절이 사라지면서, 아침 라운드(`879ad8ef`)가 씨앗 대상으로 열거했던 필수 flag 셋 중
  `packs.*.claims.*.roles.*.required`가 **존재하지 않게 됐다.** 그 씨앗 규칙은 이름이 아니라
  hint 를 읽으므로 코드는 안 움직였다.
- 이 커밋의 마이그레이션은 **재실행 시 두 설정 모두 변화 없음**을 보고했다. 라이브 운영자
  설정은 gitignore 라 이 저장소의 커밋에는 없다.
