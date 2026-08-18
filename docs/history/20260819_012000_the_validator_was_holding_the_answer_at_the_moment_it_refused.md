# 검증기는 거절하는 그 순간에 답을 손에 들고 있었다

**날짜:** 2026-08-19 01:20 · **커밋:** `50af175` · `9a60306` · **레인:** 서버(온톨로지 작성 모드)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 두 시간, 스무 번의 저장-거절

소유자가 두 번째 소스(`dt-job`)를 손으로 세웠다. 약 두 시간, 저장-거절 왕복 약 20회.
그 시간의 큰 몫이 **다른 데서 이미 결정된 것을 다시 적는 데** 들어갔고, 나머지 몫은
**거절문이 위치만 말하고 무엇이 허용되는지는 말하지 않아서** 사람이 옆에 앉아 통역했다.

실제로 맞은 거절 셋:

```
invalid_type    bundle.mappers.dt-job-role@1.emits      must be a list with at least one item
unknown_pack    bundle.mappers.dt-job-role@1.emits[0]   unknown pack 'dt-job@1'
unknown_field   bundle.packs...emit.object.payload      field is not allowed
```

셋 다 통역이 필요했다. 「`emits`는 `<pack>@<version>/<claim>` 문자열을 받는다」,
「`object`는 `kind`/`entity`/`value`/`qualifiers`만 받는다」.

## `50af175` — 답은 이미 한 스택 프레임 아래에 있었다

**허용 집합은 이미 `_Problems.exact()`의 인자다.** 거절하는 그 함수가 `required`와
`optional` 튜플을 손에 들고 있으면서 말을 안 했을 뿐이다. 새로 계산할 것이 없다.

- `unknown_field` → `field is not allowed; allowed here: kind (required), entity, value, qualifiers`
- 참조 목록의 `invalid_type` → `; each item is <pack>@<version>/<claim>` (철자는 그것을
  파싱하는 정규식 옆의 상수 하나에서 읽는다 — 두 군데에 적으면 언젠가 갈라진다)

**`unknown_*`는 「오타」와 「아직 안 썼음」을 가른다.** 둘은 정반대의 다음 행동이
필요한데 종전 문구는 둘을 합쳐 놨다. 이제 근접 매치면 `did you mean 'movement@1'?`,
아니면 `declared packs: 'movement@1'`, 아무것도 없으면 `no packs are declared yet`.
11개 자리에 같은 헬퍼를 붙였다.

**그리고 작성 경로는 문제를 전부 보고한다.** `validate_bundle_errors`는 원래부터
목록을 돌려주고 있었고, `python -m ledger.setup`이 로더가 던지게 두고 하나만 찍었을
뿐이다. 실제 진행 중인 config에 대고 재 봤더니 **트레이스백 하나 → 문제 셋**이 됐다.

🔴 **런타임은 그대로 첫 거절에서 멈춘다.** 원자를 쓰려는 소스에게 「어차피 거절될
config의 결함 목록」은 쓸모가 없고, 뒤 검사는 앞 검사가 이미 깨졌다고 선언한 번들을
읽게 된다. 테스트 하나가 **같은 루트에 대고 양쪽을 함께 채점**한다 — 둘이 다르다는
것이 단언되지, 각각 그럴듯하다는 것이 아니다.

## `9a60306` — 소유자 판정: 화면의 본질은 «도출»이다

> entity type이 `DTJob@1`이면 binding의 `keys`는 그 엔터티의 식별키일 수밖에 없다.
> 화면이 그걸 계산해서 할 일 목록을 보여 줘야 한다. **연결이 중요한 부분이다.**

그리고 이건 취향이 아니다 — **검증기가 이미 그렇게 강제한다.** 작성자가 그것을 다시
적을 때 자유도는 0이고, 더 낫게 쓸 수는 없고 틀리게만 쓸 수 있다. 그래서 규칙:

> **한 선언이 강제하는 것은 화면이 채운다. 진짜로 자유로운 것만 묻는다.**

표는 `task/ontology_config_authoring_mode_pending.md`에 있다. 30여 개 행, 절 A~F.
**모든 행을 실제로 어겨 보고** 나온 거절 코드·경로를 달았다 — 기억으로 쓰지 않은 이유는
같은 날 밤 기억으로 댄 필드명 `payload`와 `pack_ids`가 **둘 다 존재하지 않았고** 각각
한 번의 저장-거절을 태웠기 때문이다. 그 오류가 스펙에 박히면 훨씬 비싸다.

### 지시받은 목록에서 뒤집힌 것 둘

**1. 엔터티의 식별키 필드는 `keys`다. `identity_keys`가 아니다.**
`identity_keys`를 넣으면 `unknown_field` + `missing_field`가 나온다.

**2. 「어디서 이름된 컬럼이든 relation에 있어야 한다」는 거짓이다 — 우주가 셋이다.**

| 우주 | 어느 칸이 여기서 고르나 |
|---|---|
| RELATION (카탈로그 컬럼) | `order_by` · `cursor.columns` · `occurred_at.column` · preparer `input_columns` · `registration_probe.columns` |
| PREPARED (= RELATION ∪ preparer `output_columns`) | `driver.identity` · `driver.group_by` · mapper `input_columns` |
| MAPPER INPUT (= 그 mapper의 `input_columns`) | profile의 **모든** column binding |

판별 실측: preparer가 만드는 `target_id`(relation엔 없다)를 `driver.identity`에 쓰면
**통과**, `order_by`에 쓰면 `unknown_column: ... is not in relation 'input_rows'`.
같은 이름, 다른 답. 화면이 컬럼 드롭다운 하나로 통일하면 **반은 없는 컬럼을 보여 주고
반은 있는 컬럼을 숨긴다.** 이 주장은 아무것도 못 박고 있지 않았으므로 테스트를 붙였다 —
한 이름이 한 칸에서 받아들여지고 다른 칸에서 거절되는 **판별 케이스**로.

## 할 일 목록은 표에서 그냥 떨어진다

같은 정보를 반대편에서 보면 거절 목록이 할 일 목록이 된다. 반쯤 쓰인 선언 앞에서
화면은 **파생됨 / 빠짐 / 미답** 세 갈래로 나눌 수 있다. 이 구분이 가능한 이유는
화면이 **어느 필드가 파생 가능한지 알기 때문**이고, 그것이 표의 값어치다.

## 남긴 것

- 매퍼 «구현»이 요구하는 고정 철자(낱말 base 이름·mapping_id 6개·qualifier 집합)는
  `setup_bundle.py`가 아니라 `server/mappers/`가 강제한다. 이번 도출은 선언 검증기만
  훑었으므로 그쪽은 **아직 도출 안 됨** — 스펙에 그렇게 적었다.
- `difflib`이 `setup_bundle.py`의 허용 import 목록에 들어갔다. 순수 stdlib 문자열
  비교라 「런타임을 import하지 않는다」는 성질은 그대로다. 목록은 닫힌 채로 뒀다.
