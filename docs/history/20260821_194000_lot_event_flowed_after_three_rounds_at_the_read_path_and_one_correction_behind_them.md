# `lot_event` 이 «처음» 흘렀다 — 읽기 경로 세 라운드와, 그 뒤에 붙은 정정 하나

> **커밋:** `5ea23aaa` (19:03) · `8bb0f5f1` (19:29) · `f134eab6` (19:38) · `9aa147b9` (19:40)
> | **일자:** 2026-08-21 저녁
> **레인:** 서버(원장 · 소스 준비) + 소유자 판정 둘
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **검증:** `8bb0f5f1` 스위트 **263 passed**(패리티 테스트 포함) · 나머지는 운영 select 를
> 통과한 실측

## 배경 — 세 개의 벽이 차례로 서 있었고, 셋 다 «읽기» 쪽이었다

`lot_event`는 원장 v2 가 선 이래 **원자를 하나도 못 냈다.** 오늘 밤 그것이 세 라운드에 걸쳐
풀렸다. 셋 다 물리 표를 **읽어서 문장으로 만드는 경계**에 있었다.

## ① varchar 안의 시각을 «읽는다» — 거절하는 대신

운영 표는 **일부러** 타임스탬프를 varchar 에 담는다. 텍스트 형식이 운영에서 균일하지 않기
때문이다. 그리고 읽기 경로는 **그것을 전부 거절**했다 — 그런 컬럼을 선언한 소스는
**원자를 낼 수 없었다.**

규칙의 두 절반은 **이미 따로 있었다.** `profile_chain_mapper._aware_time`은 ISO 를 파싱하고
텍스트에 적힌 오프셋을 존중하지만 naive 값은 거절했다. `source_preparation._aware_time`은
선언된 `read.occurred_at.timezone`으로 naive 를 로컬라이즈하지만 **문자열은 전부 거절**했다.
이 커밋은 체인 쪽의 파싱을 **글자 그대로** 이미 여기 있던 로컬라이즈 **앞에** 옮겼다.

🔴 **판별식은 `dt_log`였지 `lot_event`가 아니다.** `dt_log.event_time`이 실제로 담고 있는
세 철자에서 실측 — `...Z`는 오프셋 0 유지, `...+09:00`은 +09:00 유지, naive
`2026-05-11 00:00:00`은 +09:00 이 된다. **`lot_event`는 이것을 보여 줄 수 없었다** — 두
형식이 다 naive 라서 **맞는 규칙과 틀린 규칙이 거기서는 같은 답**을 내고, `dt_log`만 둘을
가른다.

파싱이 안 되는 문자열은 여전히 거절로 떨어진다 — 인제션 시각으로 **대체되지 않는다.**

컴파일러 계약 버전이 **4로** 올라갔다. 같은 행이 이제 **다른 순간에** 원자를 내는데,
셋업이 안 바뀌었다고 말하는 커서는 **두 독해를 겹쳐 쌓고 어느 쪽인지 기록하는 것이
없기** 때문이다.

## ② 준비기가 「이 행은 내 것이 아니다」라고 «선언»한다

`lot_event` 표는 **두 세대**를 담고 있다. 80행은 정체성을 `lot_id`로 철자하고 나머지는
`lot`으로 철자하며, `slotnumbers`/`slot_numbers`·`waferids`/`wafer_ids`도 같은 분할이다.
준비기가 읽는 컬럼은 전부 **첫 번째 철자**라, 두 번째 세대는 정체성 루프에 **빈 채로
도착해 배치 전체를 거절시켰다.**

그리고 준비기에는 **「이 행은 내 것이 아니다」를 놓을 자리가 없었다** — 출력은 base 행당
정확히 하나여야 하고 base 값을 바꿔서는 안 되기 때문이다.

```python
SOURCE_ROW_EXCLUDED_COLUMN = "__source_row_excluded"
...
    if SOURCE_ROW_EXCLUDED_COLUMN in out.columns:
        excluded = out[SOURCE_ROW_EXCLUDED_COLUMN].tolist()
        if any(not isinstance(value, bool) for value in excluded):
            raise SourcePreparationError(
                "invalid_source_preparer_output", ...,
                "row exclusion marker must be a boolean for every source row")
        out = out.loc[[not value for value in excluded]].reset_index(drop=True)
```

**가드는 낮춘 게 아니라 좁힌 것이다.** 살아남은 모든 행은 여전히 **같은 거절문으로**
정체성을 요구받고, 「빈 `lot`은 우리 것이 아니다」라는 지식은 **소스 전용 준비기 안에**
남고, 컬럼은 `prepare.output_columns`에 선언되므로 **그것을 선언하지 않는 25개 소스는
차이를 알 수 없다.** 제거는 두 계약이 **채점된 «뒤», 정체성 루프 «앞»**에서 일어난다.

**전부 제외된 페이지는 거절이 아니라 빈 프레임**을 낸다. 페이지는 세대가 아니라 **커서로**
잘리므로 옛 행만 든 페이지는 정상이고, 거절하면 백필이 거기서 **영원히 선다.** 커서는
살아남은 것이 아니라 **base 페이지에서** 전진하므로 제외된 행은 **한 번 지나쳐지고 다시
안 읽힌다.**

실측(운영 select 통과): `lot_event` 142행 → **80 유지 · 62 제외 · 이벤트 40**.
`dt_job`은 3000행 넘게 **하나도 안 떨어진다.**

## ③ 그리고 9분 뒤, 그 라운드가 인용한 «숫자»가 틀렸다

🔴 `f134eab6`. 주석이 「62행이 정체성을 `lot`으로 철자한다」고 적었는데 **61행이 그렇고,
한 행은 «어느 쪽도» 철자하지 않는다.** 62는 그 컬럼이 말하는 수가 아니라 **제외가
치우는 수**다. 문장이 나타나는 **두 자리 모두** 고쳤다.

```python
-    # generations that spell the same facts differently -- 80 rows say `lot_id`, 62 say
-    # `lot` -- and the preparer reads only the first spelling, ...
+    # generations that spell the same facts differently -- 80 rows say `lot_id` and 61 say
+    # `lot`, with 1 row saying neither, so 62 are excluded -- and the preparer reads only
+    # the first spelling, ...
```

같은 커밋이 **지금 도는 프로세스가 코드와 라이브 선언이 «둘 다» 착지한 뒤에 시작됐음**을
기록했다 — 총괄이 경고한 ImportError 창이 여기서는 열려 있지 않다는 것을, **제기한 뒤가
아니라 제기하기 «전»에** 확인했다.

## ④ 소유자 판정 — 선언된 timezone 이 naive 컬럼을 읽는다

이것이 그 절반을 **안전장치가 아니라 규칙**으로 만든 것이다. 선언된 timezone 은 이벤트가
**어느 순간에** 일어났는지 결정하도록 **신뢰받고 있었는데**, 그 옆에 **게시되는 값에
대해서는 거절**당했다. 그래서 컬럼이 naive 텍스트를 담은 소스는 **id 를 만들고 나서 원자를
아예 못 냈다** — Role 검증기가 raw 문자열을 통째로 거절했다.

```python
 event[SOURCE_OCCURRED_AT_COLUMN] = pd.Series(
-    [occurred_cells[earliest]] * len(event), index=event.index, dtype=object)
+    [occurred_values[earliest]] * len(event), index=event.index, dtype=object)
```

옛 동작을 **의도적이라고 설명하던 주석**은 코드와 모순되게 남겨 두지 않고 다시 썼고,
**대가를 이름 붙였다**: 시각 컬럼이 존을 안 달고 있는 **모든** 소스가 이제 자기 선언된
timezone 으로 읽힌다.

> 하나의 가정이 정체성에는 충분하고 값에는 아니라는 것은 **신중함이 아니다.**
> `lot_event`가 그것이 어떻게 보이는지다.

그리고 이것이 그 선언 칸이 파일에 있어도 되는 근거이기도 하다 — 이것을 결정하도록 허락
받은 적이 없었다면 그 칸의 **자유도는 0**이었을 것이다.

실측: `lot_event` 142행 → 80 유지 · 40 이벤트 · **후보 원자 1,323 · incomplete 0**.
그전에는 **첫 행에서 거절**했다. `dt_job`은 43 이벤트 · 탈락 0 으로 불변.

## 결과 — 20:2x, 총괄이 돌린 실행

```
molecules 40 · refused 0 · incomplete 0 · rows_read 142 · 3.5초
attempted 1,323 -> inserted 1,323 · deduped 0
재실행     rows_read 0 · inserted 0 · 커서 그대로
```
```
has_wafer   Lot 907    register Wafer 125    register Lot 25
slot_map    Lot 226    derived_from Lot 40   <- 계보
원장  v2 792 -> 2,115        v1 220,771 «불변»
```

계보를 원장에서 직접 읽었다:

```
NAB539TA <- NAB539   2026-01-01 12:04:00+09:00
NAB122TA <- NAB122
NAB122TB <- NAB122   (같은 부모, 두 자식 = split)
```

🔴 **시각이 `+09:00`이다** — 소유자의 timezone 판정이 **코드가 아니라 «실제 원자»에**
적용된 증거다. 총괄이 살아남은 `parent_lot` 행에서 예측한 계보 40행도 그대로 맞았다.

## ⚠️ 그 실행은 «라이브 루트 그대로»가 아니었다

소유자가 새 소스를 만드는 중이라 **사본**으로 돌렸다 — 반쯤 지어진 소스 둘이 번들을
거절시켰기 때문이다. 그리고 사본에 **선언 하나를 넣었다**:

```
lot_event.read.registration_probe          그 시점 라이브엔 «없었다»
  [{"entity_type":"Lot@1",   "columns":["lot_id"]},
   {"entity_type":"Wafer@1", "columns":["waferids"], "list_separator":":"}]
```

`register@1`을 쏘는 소스는 「누가 이미 등록됐나」를 알아야 한다. **백업 14개를 전수로
훑었다 — 잃은 것이 아니라 «한 번도 쓰인 적 없는» 선언이다.** 소유자 승인 후 20:2x 에
라이브에 들어갔고, 라이브 `lot_event` 선언이 사본의 것과 동일함을 대조해 커서 지문이
나중에 어긋나지 않음을 확인했다.

🔴 **탐침은 «물리» 컬럼을 읽는다**(준비 «전» 페이지). `lot`/`wafers`가 아니라
`lot_id`/`waferids`다. 검증기도 카탈로그에 대고 보므로, 준비된 철자를 기억에서 먼저 썼다가
거절당했다.

## 그때 남아 있던 것

- 🔴 **`lot_event`의 분할 가드가 비활성이다.** 경고 그대로:
  `split guard inactive for lot_event: group columns ['event_group_key'] are not base
  columns`. 그룹 키가 파생이라 페이지에서 분할 분자를 잡지 못한다. 이번 실행은
  `batches=1`이라 무해했다. **페이지가 둘 이상으로 갈리는 상황은 아직 발생하지 않았다.**
- 🟡 `trace`·`explore`는 여전히 **503**이었다. 해결기가 v2 셋업이 아니라 **옛 세대 config**를
  읽는다 — 원자와 무관하고 이날 것이 아니다. **계보 자체는 원장에 있다**(위 실측).
- 라이브 루트로는 아직 못 돌았다 — 소유자의 미완성 소스 둘이 번들을 거절시키는 상태.
