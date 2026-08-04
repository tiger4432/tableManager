# `notation_rules.json` 세팅 — 표기 정규화(파생 컬럼)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-04 (`92b8d6f` 신설 — WF/lot 표기 정규화 1단계. 🔴 **이 문서의 JSON 예시는 전부 실제 검증기(`notation_norm.validate_notation_rules`)에 먹여 본 것이고, 붙어 있는 반환값·거절 메시지는 실행 결과 그대로입니다.** ⚠️ **1단계라 아직 아무도 파생값을 읽지 않습니다** — §0을 먼저 읽으십시오. 🔴 **켜는 것은 층이 셋**입니다(물리 컬럼 · 파생 쌍 · 가시성 — §2), 그중 셋째는 1단계에서 **일부러 안 하는 단계**입니다) | **Owner:** Backend / Ops
> 상위: [폴더 인덱스](./README.md) · 지도는 [CONFIG_GUIDE §1](../CONFIG_GUIDE.md) · 1단계는 [table_config.json](./table_config.md)이 먼저다 · 정본 코드는 `server/notation_norm.py`

<!-- Loader evidence (2026-08-04, 92b8d6f):
  fold:            notation_norm.fold_notation  (rules: separator, case; zero_pad refused)
  value:           notation_norm.normalized_value = fold_notation(map_overlay.canonical_bind_value(...))
  load/validate:   notation_norm.load_notation_rules / validate_notation_rules / _validate_column
                   / _normalize_rules   (rejection codes: would_rewrite_raw, key_column,
                   zero_pad_unimplemented, unknown_rule, undeclared, shape)
  cache:           notation_norm.RULES_CACHE_TTL = 5.0 + reset_cache()
                   (main.reload_local_process_cache -> notation_norm.reset_cache)
  write hook:      crud.apply_row_update_internal -> notation_norm.apply_derivations
                   (after the value loop AND after the audit block; failure is logged, never fatal)
  write refusal:   crud.refuse_notation_derived_columns, called from crud.apply_batch_updates
                   beside refuse_virtual_join_columns; ValueError -> HTTP 400 (main.py:2319)
  re-derivation:   notation_norm.rederive (keyset on row_id, bulk_update_mappings, dry-run default)
                   CLI server/scripts/rederive_notation_norm.py  (--apply/--table/--chunk-size)
  visibility:      main.get_table_schema (main.py:1929) -> display_columns when declared,
                   else model columns; client2/src/api.js state.currentColumns ->
                   client2/src/grid.js buildColumnDefs (the ONLY source of grid columns).
                   /tables/{t}/data and /tables/{t}/export build from column_types, NOT
                   display_columns - so the derived value ships and extracts either way.
                   display_columns is ALSO the std parser's load filter
                   (parsers/directory_watcher.py:1767, std_parser.py:62).
  report:          config_resolve_report._resolve_notation (DOMAIN_NOTATION)
                   GET /admin/config/resolve?domain=notation  (config only, zero DB queries)
  tests:           server/tests/test_notation_normalization.py  (23)
  live state 2026-08-04: server/config/notation_rules.json DOES NOT EXIST (only the .sample)
-->

## 0. 🔴 지금 무엇을 얻고, 무엇은 못 얻는가 (1단계)

**얻는 것**: 원본 컬럼 옆에 **정규화된 표기가 담긴 파생 컬럼**이 생깁니다. 값은 정확하고, 새 쓰기마다 자동으로 갱신되며, 규칙을 바꾸면 언제든 다시 계산할 수 있습니다. **CSV 추출과 SQL로 볼 수 있고 셀 수 있습니다**(그리드에 그려질지는 별개의 세 번째 결정입니다 → §2.3).

**못 얻는 것**: **아무것도 그 값을 읽지 않습니다.** 맵 키 분해도, 그리드 필터도, virtual join도 여전히 **원본 값**을 씁니다. 그러니 `CL-2601-001`과 `CL_2601_001`이 화면에서 **오늘 합쳐지지 않습니다.**

> 🔴 **필터가 합쳐지기를 기대하고 켜지 마십시오.** 합치는 것(2단계)은 설정 스위치가 아니라 **데이터 마이그레이션**입니다: `wafer_map_metadata`의 행은 **원본 신원**으로 등록돼 있어서(`map_overlay.compose_map_id`가 원본 값을 `_`로 잇습니다), 맵 키가 정규화 값을 읽는 순간 **기존 `map_id`가 자기 메타 행과 안 맞게 되고 맵이 안 열립니다.** 메타를 다시 등록할 것인지, 어느 쪽 테이블에 파생 컬럼을 둘 것인지가 전부 별도 라운드의 결정입니다.

그래서 1단계에서 이 파일을 켜는 이유는 하나입니다 — **2단계를 결정하기 전에, 접었을 때 무엇이 합쳐지는지 실제 데이터로 보기 위해서**(§5.2의 false-merge 확인).

## 1. 무엇인가 — 원본은 어떤 경우에도 안 고친다

같은 것을 여러 철자로 적어 온 값(`WF.01` / `WF-01` / `WF_01` / `wf 01`)을 **하나의 표기**로 접어 **별도 컬럼**(`<컬럼>_norm` 관례)에 기록합니다.

| 규칙 | 하는 일 | 위험 |
|---|---|---|
| `separator` | `.` `_` `-` 공백의 **연속**을 `-` 하나로 | 낮음 |
| `case` | 대문자로 접기 | 낮음 |
| `zero_pad` | (앞자리 0 제거) | **미구현 — 켜면 거절됩니다** (§4) |

실측 결과(`normalized_value`, `dt_log.core_lot`, `separator`+`case`):

```
'CL-2601-001'        -> 'CL-2601-001'
'CL_2601_001'        -> 'CL-2601-001'
'CL_2601_006_A1_A7'  -> 'CL-2601-006-A1-A7'
'WF.01'              -> 'WF-01'
'wf 01'              -> 'WF-01'
'WF--01'             -> 'WF-01'
'WF010'              -> 'WF010'      (zero_pad 미구현 ― 안 접습니다)
'WF10'               -> 'WF10'
None                 -> None
'   '                -> None         (없는 값에는 표기가 없습니다)
```

**왜 `-`로 접는가.** `_`는 복합 맵 키를 **잇는 문자**입니다. 값 자체가 `_`를 품으면 그 값은 자기가 속한 키를 조각냅니다 — `core_lot`이 `CL_2601_001_09`이면 슬롯 `5`와 합쳐진 키 `CL_2601_001_09_5`가 `lot='CL'` + `slot='2601_001_09_5'`로 되읽혀 **셀이 0개 그려집니다**(이 저장소의 시뮬레이션 데이터 766행이 그 모양이었습니다). `_` 관례는 **일부러 그렇게 만든 것**이고 이 기능은 그것을 바꾸지 않습니다 — 대신 `_`를 **값 밖으로 몰아냅니다.**

**원본은 절대 안 바뀝니다.** 이것이 이 기능의 안전 성질 전부입니다. 접기 규칙이 틀렸다는 것을 나중에 알아도 되돌릴 것이 없습니다 — 규칙을 고치고 다시 파생하면 끝입니다(§7). 그 성질은 주석이 아니라 **세 개의 거절**로 강제됩니다(§4).

## 2. 🔴 층이 셋이다 — 물리 컬럼 · 파생 쌍 · 가시성

운영자가 통제하는 것은 **세 가지**이고 서로 다른 곳에서 결정됩니다. 「컬럼을 선언했는데 그리드가 그대로다」는 고장이 아니라 **셋째 층을 아직 안 건드린 것**입니다.

| 층 | 어디서 결정 | 켜면 무엇이 되나 | 1단계 권장 |
|---|---|---|---|
| ① **물리 컬럼** | `table_config.json`의 `column_types` | DB에 컬럼이 **실제로 생깁니다**(watcher가 ALTER를 냅니다) | **필수** |
| ② **파생 쌍** | `notation_rules.json`(이 파일)의 `columns` | 그 컬럼에 **값이 채워집니다** | **필수** |
| ③ **가시성** | `table_config.json`의 `display_columns` | 그 컬럼이 **그리드에 그려집니다** | **하지 마십시오** (§2.3) |

①과 ②는 **순서가 있고**(§2.1), ③은 **일부러 안 하는 단계**입니다(§2.3).

### 2.1 순서 — ① 다음 ②

| 단계 | 어디 | 무엇 | 확인 |
|---|---|---|---|
| **1** | `table_config.json` | 파생 컬럼을 `column_types`에 **`"string"`으로** 추가 → 물리 ALTER 대기 | `information_schema`로 **컬럼이 실제로 생겼는지** 확인 ([table_config §3](./table_config.md)) |
| **2** | `notation_rules.json` (이 파일) | `columns` 아래에 `원본: 파생` 쌍 선언 | `GET /admin/config/resolve?domain=notation` (§5.1) |

1단계 예 (`table_config.json`의 `dt_log` 항목):

```json
"column_types": {
  "core_lot": "string",
  "core_lot_norm": "string"
}
```

제약 둘 — 둘 다 로더가 거절로 강제합니다(§4):
- 파생 컬럼은 **반드시 `"string"`**입니다. `number`로 선언하면 `'WF-01'`을 받지 못합니다.
- 파생 컬럼은 **`business_key`도, `composite_key_source`의 멤버도 될 수 없습니다.** (원본 컬럼이 키 멤버인 것은 괜찮습니다 — `core_wafer_map.core_lot`이 그 예입니다.)

### 2.2 뒤집으면 무슨 일이 나는가 — 두 가지 모양이고, 하나는 시끄럽고 하나는 조용하다

**(A) 1단계를 아예 건너뛰었을 때 — 시끄럽게 거절됩니다.** 검증기가 `table_config.json`에 없는 컬럼을 지목한 선언을 반려합니다. 실제 반환값:

```json
{
  "scope": "column",
  "subject": "dt_log.core_lot",
  "detail": "derived column 'core_lot_norm' is not declared in table_config.json for 'dt_log'. Add it as a \"string\" column there first - until the physical column exists there is nowhere to put the normalized value",
  "code": "undeclared"
}
```

`GET /admin/config/resolve?domain=notation`에서는 같은 것이 한국어 앞머리와 함께 `rejected`로 뜹니다(§5.1의 B). 이 경우는 **아무 값도 파생되지 않고**, 왜 안 됐는지가 화면에 남으므로 안전합니다.

**(B) `table_config.json`에는 넣었는데 물리 ALTER 착지를 확인하지 않았을 때 — 조용합니다. 이쪽이 위험합니다.**

검증기는 **config만 읽습니다**(`/admin/config/resolve`의 계약이 「DB 질의 0건」입니다). 그래서 `table_config.json`에 컬럼 이름이 적혀 있기만 하면 선언은 **`effective` 1건으로 정상 보고됩니다.** 그런데 파생을 실행하는 `notation_norm.apply_derivations`는 행 객체에 그 컬럼이 없으면(`hasattr(row, derived_col)`가 거짓) **그 컬럼을 그냥 건너뜁니다 — 예외도, 경고 로그도 남기지 않습니다.**

즉 증상은 이렇습니다:

> **해석 보고서는 「선언 1건이 유효합니다」라고 말하는데, 파생 컬럼은 계속 비어 있고 어디에도 에러가 없다.**

그래서 2단계 전에 **`information_schema`로 컬럼 존재를 눈으로 확인**하는 것이 절차에 들어 있습니다. `GET /tables/{t}/schema`의 200은 증거가 아닙니다 — config 싱글턴을 읽을 뿐이라 DB에 없는 컬럼도 보입니다([CONFIG_GUIDE §4.3](../CONFIG_GUIDE.md)).

복구는 어렵지 않습니다 — ALTER가 실제로 착지한 뒤 **재파생 한 번**(§7)이면 건너뛴 행이 전부 채워집니다. 다만 **그 사이에 「기능이 고장 났다」고 결론짓지 않는 것**이 이 절의 목적입니다.

### 2.3 세 번째 층 — 그리드에 보이게 할 것인가 (1단계에서는 **하지 마십시오**)

파생 컬럼은 **진짜 물리 컬럼**입니다. 그래서 「이제 내 그리드에 뜨는가?」라는 질문이 당연히 나오는데, 답은 **`display_columns`를 선언했는지에 달려 있고 그것은 별도의 결정**입니다.

실측한 경로 (`92b8d6f` 시점 코드 기준):

- `GET /tables/{t}/schema`는 `display_columns`가 **선언돼 있으면 그 목록을 그대로** 돌려주고, **없을 때만** 모델의 컬럼을 훑어 만듭니다(`main.get_table_schema`, `main.py:1929`). 시스템 컬럼 5종은 어느 쪽이든 뒤에 붙습니다.
- 클라는 그 `columns`를 `state.currentColumns`에 그대로 담고(`client2/src/api.js`), `buildColumnDefs()`가 **그 배열에서만** 그리드 컬럼을 만듭니다(`client2/src/grid.js`).

따라서:

| 그 테이블에 `display_columns`가 | 파생 컬럼은 |
|---|---|
| **있다** | DB에는 있지만 **그리드에 안 뜹니다** — 목록에 직접 추가할 때까지 |
| **없다** | 자동으로 **뜹니다**(모델 컬럼 열거로 떨어지므로) |

> 2026-08-04 이 환경 실측: `table_config.json`에 등록된 **14개 테이블 전부가 `display_columns`를 선언**하고 있습니다. 즉 **여기서는 기본이 「안 보임」**입니다.

🔴 **1단계에서는 추가하지 마십시오.** 아직 **아무도 그 값을 읽지 않으므로**(§0), 그리드에 컬럼을 하나 더 붙이는 것은 이득 없이 화면만 넓히는 일입니다. 접기 결과를 눈으로 보고 싶어질 때만 `display_columns`에 한 줄 추가하면 되고, **한 줄 지우면 그대로 되돌아갑니다** — 물리 컬럼도 값도 건드리지 않는 **되돌릴 수 있는 결정**입니다(`display_columns` 편집은 ALTER를 유발하지 않습니다).

**그리고 그리드를 넓히지 않고도 결과를 볼 수 있습니다.** CSV 추출(`GET /tables/{t}/export`)은 헤더를 `display_columns`가 아니라 **`column_types` 전체**에서 만듭니다(`main.py`의 `business_cols`). 즉 **파생 컬럼은 `display_columns`에 없어도 CSV에는 나옵니다.** 행 페이로드(`GET /tables/{t}/data`)도 마찬가지로 `column_types` 기준이라 값 자체는 이미 클라까지 갑니다 — 그리지 않을 뿐입니다. §5.2의 false-merge 확인은 SQL이므로 애초에 이 층과 무관합니다.

> ⚠️ **추가한다면 부작용 하나를 알고 하십시오.** `display_columns`는 그리드 표시 순서일 뿐 아니라 **표준 파서의 적재 대상 집합**이기도 합니다([table_config §5](./table_config.md)) — 목록에 없는 컬럼은 crud에 닿기 전에 버려집니다. 파생 컬럼을 목록에 넣으면, 마침 같은 이름의 헤더를 가진 원본 파일이 들어왔을 때 그 값이 crud까지 도달하고 **쓰기 거부(§4.4)에 걸려 그 배치 전체가 실패**합니다. 목록에서 빼 두면 파서 단계에서 조용히 버려져 그런 일이 없습니다.

### 2.4 반영 시점

`notation_rules.json`은 **config watcher의 감시 대상이 아닙니다**(watcher가 보는 파일은 `table_config.json` 하나뿐입니다). 반영은 두 갈래입니다:

- **자동**: 선언 캐시의 TTL이 **5초**(`RULES_CACHE_TTL`)라, 저장하고 5초 뒤 다음 쓰기부터 새 선언이 적용됩니다 — 워커 프로세스도 포함입니다.
- **즉시**: `POST /admin/reload-configs` (웹서버 프로세스의 캐시를 그 자리에서 버립니다).

> ⚠️ **파생은 「원본 컬럼이 바뀐 쓰기」에서만 다시 계산됩니다**(신규 행은 항상). 선언을 켜도 **이미 쌓여 있던 행은 그대로 비어 있습니다** — 그것을 채우는 것이 §7의 재파생입니다.

## 3. 선언 예시 — 전부 실제 검증기에 먹인 것

> 아래 「검증기 반환」은 `conda run -n assy_manager python`으로 `notation_norm.validate_notation_rules(<입력>, known_tables=<이 환경의 table_config>)`를 돌린 **실제 출력**입니다. 손으로 쓴 기대값이 아닙니다.

### 3.1 최소 선언 (1단계가 끝난 상태)

```json
{
  "rules": { "separator": true, "case": true, "zero_pad": false },
  "columns": {
    "dt_log": { "core_lot": "core_lot_norm" }
  }
}
```

검증기 반환 (거절 0건):

```json
{
  "dt_log": {
    "core_lot": {
      "table": "dt_log",
      "raw": "core_lot",
      "derived": "core_lot_norm",
      "rules": { "separator": true, "case": true, "zero_pad": false }
    }
  }
}
```

### 3.2 컬럼별 규칙 오버라이드

규칙은 **파일 전체 → 테이블 → 컬럼** 순으로 덮입니다. 대소문자를 살려야 하는 컬럼이 하나 있다고 해서 규칙을 전역으로 끌 필요가 없습니다.

```json
{
  "rules": { "separator": true, "case": true },
  "columns": {
    "dt_log": {
      "core_lot": "core_lot_norm",
      "dt_lot": {
        "derived": "dt_lot_norm",
        "rules": { "separator": true, "case": false }
      }
    }
  }
}
```

검증기 반환 (거절 0건) — 한 테이블 안에서 두 컬럼이 **서로 다른 규칙 집합**을 갖습니다:

```json
{
  "dt_log": {
    "core_lot": {
      "table": "dt_log", "raw": "core_lot", "derived": "core_lot_norm",
      "rules": { "separator": true, "case": true, "zero_pad": false }
    },
    "dt_lot": {
      "table": "dt_log", "raw": "dt_lot", "derived": "dt_lot_norm",
      "rules": { "separator": true, "case": false, "zero_pad": false }
    }
  }
}
```

### 3.3 아무것도 안 하면 아무 일도 안 일어난다

출하되는 `notation_rules.json.sample`은 `"columns": {}`입니다. **그 파일을 그대로 복사해 두면 이 기능은 완전히 무동작입니다.** 샘플 전체를 그대로 검증기에 먹인 결과: 반환 `{}`, 거절 `[]`.

> 2026-08-04 이 환경의 실제 상태: `server/config/notation_rules.json`은 **아직 존재하지 않습니다**(`.sample`만 있습니다). 파일이 없는 것은 거절이 아니라 「선언 없음」입니다 — 로더가 조용히 `{}`를 돌려주고, 해석 보고서는 *「선언 파일이 없습니다 ― 표기 정규화가 적용되는 컬럼이 하나도 없습니다.」*라고 말합니다.
>
> `_`로 시작하는 이름은 로더에게 **주석**입니다. 그래서 샘플의 `_example_columns` 블록은 아무 효과가 없고, 켜는 방법은 그 안의 항목을 `columns`로 **옮기는** 것입니다.

## 4. 거절 — 이름과, 각각이 막아 주는 것

거절은 조용히 무시되지 않습니다. 전부 이름(`code`)이 붙고 `GET /admin/config/resolve?domain=notation`의 `rejected`에 뜹니다. 아래 메시지는 **코드가 실제로 내놓은 문자열**입니다.

### 4.1 `would_rewrite_raw` — 원본을 덮어쓰는 선언

**무엇을 치면 걸리나**: 파생 컬럼 자리에 원본 컬럼 이름을 그대로 적었을 때.

```json
{ "columns": { "dt_log": { "core_lot": "core_lot" } } }
```

검증기 반환: `{}` (선언 0건 채택), 거절:

```json
{
  "scope": "column",
  "subject": "dt_log.core_lot",
  "detail": "the derived column must not be the raw column itself - this feature never rewrites a raw value, because a wrong folding rule is repaired by re-deriving and that repair needs the original to still be there",
  "code": "would_rewrite_raw"
}
```

**무엇을 막아 주나**: 이 거절이 이 기능의 **안전 성질 전체를 지키는 자리**입니다. 원본이 한 번이라도 덮어써지면 「규칙이 틀렸으면 다시 파생하면 된다」가 성립하지 않습니다 — 되돌릴 원본이 없어지기 때문입니다. (구현자가 이 거절만 빼고 스위트를 돌렸을 때 빨개진 테스트는 **1건**이고, 그 한 줄이 성질 전체의 파수꾼입니다.)

### 4.2 `key_column` — 파생 컬럼이 업무 키에 속함

**무엇을 치면 걸리나**: 파생 대상으로 `business_key`나 `composite_key_source`의 멤버를 지목했을 때. 예 — `dt_log`의 복합 키 소스는 `["dt_job","dt_x","dt_y"]`입니다.

```json
{ "columns": { "dt_log": { "core_lot": "dt_job" } } }
```

거절:

```json
{
  "scope": "column",
  "subject": "dt_log.core_lot",
  "detail": "derived column 'dt_job' is part of this table's business key, so deriving it would rewrite row identity. Phase 1 only produces a value; what reads it is a separate decision",
  "code": "key_column"
}
```

**무엇을 막아 주나**: 파생값이 **행의 정체성을 옮기는 것**입니다. 업무 키 컬럼이 파생 대상이 되면 접기 규칙 하나가 행의 신원을 바꾸고, 같은 키로 재계산된 행끼리 충돌하거나 서로를 덮습니다. 원본 컬럼이 키 멤버인 것은 **괜찮습니다** — 거절하는 것은 **파생 쪽**입니다.

### 4.3 `zero_pad_unimplemented` — 켜져 있는 것처럼 읽히는 스위치를 만들지 않는다

**무엇을 치면 걸리나**: `"zero_pad": true`.

```json
{
  "rules": { "separator": true, "case": true, "zero_pad": true },
  "columns": { "dt_log": { "core_lot": "core_lot_norm" } }
}
```

거절:

```json
{
  "scope": "table",
  "subject": null,
  "detail": "rule 'zero_pad' is declared but NOT IMPLEMENTED, so it is refused rather than silently ignored. It is the one rule that can merge two different entities ('WF010' and 'WF10' both become 'WF10'), and no census has said whether such a collapse exists here. Run the false-merge check first.",
  "code": "zero_pad_unimplemented"
}
```

🔴 **이 거절은 선언 전체를 버리지 않습니다** — `zero_pad`만 `false`로 되돌려지고 나머지 선언은 그대로 채택됩니다(검증기 반환에 `"zero_pad": false`가 찍힌 채로 컬럼 선언이 살아 있습니다).

**무엇을 막아 주나**: 셋 중 **유일하게 서로 다른 것을 합칠 수 있는 규칙**입니다 — `WF010`과 `WF10`은 다른 웨이퍼일 수 있는데 앞자리 0을 떼면 하나가 됩니다. 그리고 이 거절이 **「켜 놓았는데 아무 일도 안 하는 노브」**를 원천적으로 막습니다. `"zero_pad": false`는 거절이 아닙니다 — **명시적으로 끄기로 한 결정**은 기록으로 남습니다.

### 4.4 쓰기 거부 — 파생 컬럼에 직접 값을 넣으려는 시도

**무엇을 치면 걸리나**: 그리드나 API로 파생 컬럼에 값을 저장하려 할 때. 그리드에서 `core_lot_norm` 칸을 고쳐 저장하는 것이 그대로 해당합니다.

거부는 `crud.refuse_notation_derived_columns`에서 나고, **배치 전체가 거부**됩니다(`apply_batch_updates`의 첫머리 — 트랜잭션이 열리기 전이라 반쯤 적용된 상태가 남지 않습니다). HTTP 400으로 아래 문구가 그대로 올라옵니다:

```
'dt_log' 테이블의 컬럼 core_lot_norm은(는) 원본 컬럼에서 자동으로 계산되는 표기 정규화 값이라
직접 저장할 수 없습니다. 값을 바꾸려면 원본 컬럼을 수정하세요.
```

**무엇을 막아 주나**: 손으로 넣은 값은 **원본 컬럼이 다음에 바뀌는 순간 설명 없이 사라집니다**. 그 사이 그 행은 자기 원본에서 나올 수 없는 정규화 값을 들고 있게 되는데, 그것이야말로 이 파생 컬럼이 없애려고 만들어진 불일치입니다.

### 4.5 나머지 거절 (모양·미선언)

| code | 언제 | 실제 메시지(발췌) |
|---|---|---|
| `undeclared` | 파생/원본 컬럼이 `table_config.json`에 없음 | `derived column 'core_lot_norm' is not declared in table_config.json for 'dt_log'. ...` |
| `undeclared` | 테이블 자체가 미등록 | `table 'no_such_table' is not registered in table_config.json` |
| `shape` | 파생 컬럼을 `number`로 선언 (예: `"core_lot": "core_x"`) | `derived column 'core_x' is declared as 'number'; a normalized notation is text and must be declared "string" (a number column would refuse 'WF-01' outright)` |
| `unknown_rule` | 없는 규칙 이름 (예: `"transliterate": true`) | `unknown rule 'transliterate'; known rules are separator, case, zero_pad` |

> `unknown_rule`도 **선언 전체를 버리지 않습니다** — 모르는 이름만 무시하고 나머지 규칙·컬럼 선언은 채택됩니다.

## 5. 반영 확인 — 두 가지 질문은 서로 다릅니다

### 5.1 「내 선언이 먹었나」 ― `GET /admin/config/resolve?domain=notation`

```bash
curl -H "X-Admin-Token: <토큰>" "http://<서버>/admin/config/resolve?domain=notation"
```

🔴 **로그에서 짐작하지 마십시오.** 이 라우트가 「먹었나 / 안 먹었으면 왜」에 답하도록 만들어져 있고, **DB 질의를 하지 않으므로** 언제 눌러도 안전합니다.

**A. 선언이 유효할 때** (`effective` 1건, `rejected` 0건) — `detail`이 그대로 화면에 렌더되는 문장입니다:

```
dt_log.core_lot의 정규화 표기가 core_lot_norm에 기록됩니다. 적용 중인 규칙: separator, case.
원본 컬럼 core_lot은(는) 절대 수정되지 않으므로, 규칙이 잘못 합쳐진 것을 발견하면 이 파일을
고치고 server/scripts/rederive_notation_norm.py --apply 로 다시 파생하면 됩니다. 다만 지금은
이 값을 읽는 코드가 아직 없습니다(1단계) ― 맵 키 분해·필터·조인은 여전히 원본 값을 씁니다.
```

같은 항목의 `fields`에 `{table, raw_column, derived_column, rules}`가 그대로 들어 있어 **어느 규칙 집합이 이 컬럼에 적용 중인지**를 눈으로 확인할 수 있습니다.

**B. 거절됐을 때** (`effective` 0건, `rejected` 1건, `reason: "not_declared"`):

```
table_config.json에 선언되지 않은 테이블/컬럼이라 반영하지 않았습니다 ―
derived column 'core_lot_norm' is not declared in table_config.json for 'dt_log'.
Add it as a "string" column there first - ...
```

**C. 아무것도 선언 안 했을 때**: `effective`·`rejected` 모두 0건, `sources[0].detail`이 *「선언 0건이 유효합니다.」*(파일이 없으면 *「선언 파일이 없습니다 ― 표기 정규화가 적용되는 컬럼이 하나도 없습니다.」*).

`settings` 블록에는 항상 세 줄이 함께 옵니다 — `implemented_rules`(실제로 적용 가능한 규칙: `separator`, `case`) · `separator_target`(`-`) · `rewrites_raw_column`(`false`).

### 5.2 🔴 「내 규칙이 서로 다른 것을 합치지는 않았나」 ― false-merge 확인

**이쪽이 진짜 검증입니다.** §5.1은 선언이 반영됐는지만 말합니다. 접기 규칙이 **의미적으로 옳은지**는 데이터가 답합니다. 파생이 한 번 돌고 난 뒤(§7의 재파생 포함), 컬럼당 쿼리 하나입니다 — 같은 쿼리가 `notation_rules.json.sample`의 `__false_merge_check`에도 들어 있습니다:

```sql
SELECT core_lot_norm,
       count(DISTINCT core_lot)                               AS n_raw,
       string_agg(DISTINCT core_lot, ' | ' ORDER BY core_lot) AS variants,
       count(*)                                               AS n_rows
FROM   dt_log
WHERE  core_lot_norm IS NOT NULL
GROUP  BY core_lot_norm
HAVING count(DISTINCT core_lot) > 1
ORDER  BY n_raw DESC, n_rows DESC;
```

🔴 **숫자를 보지 말고 `variants` 열을 읽으십시오.** 이 쿼리가 돌려주는 것은 「접었더니 하나가 된 원본 철자들」이고, 판단해야 할 질문은 하나뿐입니다:

> **이것들이 정말로 같은 물리 로트인가?**

- 전부 같은 것이면 — 규칙이 옳습니다. 그 행 수가 이 기능이 없앤 분열의 크기입니다.
- **한 그룹이라도 아니면** — 규칙을 이 파일에서 고치고 §7로 다시 파생합니다. **잃은 것은 없습니다**(원본이 그대로이므로).
- 결과가 0행이면 — 그 컬럼에는 접을 것이 애초에 없었습니다. 이상이 아닙니다.

> ⚠️ **한 가지 알려진 모양**: `variants`가 `-` · `_` · `.` · `--`처럼 **구분자만으로 된 값들**뿐인 그룹이 나올 수 있습니다. 구분자만 있는 값은 전부 `-` 하나로 접히기 때문입니다(공백뿐인 값과 달리 `NULL`이 되지 않습니다). 실제 로트가 아니라 **원본 데이터의 쓰레기 값이 한자리에 모인 것**이니, 그 그룹만 보고 규칙이 틀렸다고 판단하지 마십시오.

**이 환경에서 이미 측정된 결과** (`92b8d6f` 착지 시점, 운영 DB read-only):

| 컬럼 | 원본 철자 | 접은 뒤 | 합쳐진 그룹 |
|---|---:|---:|---:|
| `dt_log.core_lot` | 30 | **15** | **15** |
| `dt_log.dt_lot` | 6 | 6 | 0 |
| `dt_log.core_slot` | 34 | 34 | 0 |
| `core_wafer_map.core_lot` | 8 | 8 | 0 |
| `bonding_log.bond_lot` | 5 | 5 | 0 |
| `bonding_log.dt_lot` | 10 | 10 | 0 |
| `lot_event.lot` | 24 | 24 | 0 |

15개 그룹은 **전부 `CL-2601-00x` / `CL_2601_00x` 한 쌍**, 즉 같은 로트의 두 철자입니다(밑줄 형태가 766행). **의심스러운 병합은 한 건도 없었습니다.** 그리고 측정한 다른 lot/slot 컬럼은 **전부 0그룹**입니다 — 즉 이 규칙은 **보고된 바로 그 컬럼 하나에서만 일을 하고 나머지에는 무해**합니다.

## 6. 규칙 사전

| 키 | 위치 | 타입 / 기본값 | 의미 |
|---|---|---|---|
| `rules` | 파일 최상위 | 객체, 기본 `{separator:true, case:true, zero_pad:false}` | 파일 전체의 기본 규칙 집합 |
| `rules` | `columns.<테이블>` 아래 | 객체 | 그 테이블의 기본값(파일 기본값을 **대체**) |
| `rules` | 컬럼 선언 객체 안 | 객체 | 그 컬럼만의 규칙(테이블 기본값을 **대체**) |
| `columns` | 파일 최상위 | `{테이블: {원본컬럼: 파생}}` | 🔴 **비어 있으면 이 기능은 완전 무동작** |
| 컬럼 선언 | `columns.<테이블>` 아래 | 문자열 **또는** `{"derived": ..., "rules": {...}}` | 문자열이면 파생 컬럼 이름 그 자체 |
| `_`로 시작하는 이름 | 어디든 | — | **주석**. 로더가 통째로 무시합니다 |

> 규칙 집합은 **병합되지 않고 대체**됩니다. 컬럼 수준에서 `{"separator": true}`만 적으면 나머지는 명시되지 않은 것이 아니라 **기본값**(`case:true`, `zero_pad:false`)이 들어옵니다.

### slot 컬럼과 앞자리 0 — 다시 열 필요 없는 질문 (조건 하나 붙습니다)

`slot`은 사용자 판정으로 **항상 정수**이고, `table_config.json`에서 `"number"`로 선언된 컬럼은 이미 `map_overlay.canonical_key_value`의 **정수 파싱**을 지납니다 — 거기서 `'01'` · `' 1 '` · `1.0`이 전부 `'1'` 하나로 접힙니다. 즉 slot의 zero-pad 문제는 **새 규칙이 아니라 기존 연산의 재사용으로 이미 닫혀 있습니다.** `zero_pad`를 구현해 달라는 요구가 slot 때문이라면, 그 요구는 이미 충족돼 있습니다.

> ⚠️ **다만 그것은 `number`로 선언된 컬럼에 한합니다.** 2026-08-04 이 환경의 `table_config.json`을 실측하면 `dt_log.core_slot` · `dt_log.dt_slot` · `core_wafer_map.core_slot` · `bonding_log.bond_slot`은 전부 **`"string"`으로 선언**돼 있습니다. 문자열 컬럼에서는 패딩이 **데이터**라 보존됩니다(실측: `core_slot` `'01'` → `'01'`, `'1'` → `'1'` — 두 값이 합쳐지지 **않습니다**). slot에서 정수 접기를 실제로 얻으려면 그 컬럼을 `number`로 선언하는 것이 먼저이고, 그것은 이 파일이 아니라 [table_config.json](./table_config.md)의 결정이며 **타입 변경은 재기동 + 수동 마이그레이션**입니다.

## 7. 소급 — 이미 쌓인 행 채우기 / 규칙 바꾼 뒤 다시 계산하기

```bash
# 리포트만 (기본값 — 아무것도 쓰지 않습니다)
conda run -n assy_manager python server/scripts/rederive_notation_norm.py

# 실제로 씁니다
conda run -n assy_manager python server/scripts/rederive_notation_norm.py --apply

# 한 테이블만
conda run -n assy_manager python server/scripts/rederive_notation_norm.py --table dt_log --apply
```

플래그는 셋뿐입니다(`--help` 실측): `--apply` · `--table T` · `--chunk-size N`(기본 1000).

🔴 **기본이 dry-run이고, 쓰려면 `--apply`를 명시해야 합니다.** dry-run은 스캔한 행 수 · 바뀔 행 수 · 실제 값 샘플(`raw` / `was` / `now`)을 찍고 **아무것도 쓰지 않습니다.** 먼저 읽고, 납득한 다음에 `--apply`를 붙이십시오.

선언이 하나도 없으면 아무 일도 하지 않고 **종료 코드 2**로 끝납니다(실측 출력):

```
no notation derivation is declared (config/notation_rules.json) - nothing to do
```

종료 코드는 둘입니다 — **0**(리포트를 냈거나 실제로 썼음) · **2**(거부: 잘못된 `--chunk-size`, 선언 없음, 거절된 선언).

**이것이 「규칙이 틀려도 복구된다」의 실체입니다.** 규칙을 고치고 → 다시 파생하면 → 파생 컬럼은 새 규칙이 말하는 값이 됩니다. 손으로 치울 것이 없습니다. 왜냐하면 **다시 계산할 수 없는 유일한 것(원본 컬럼)을 한 번도 쓴 적이 없기** 때문입니다. 같은 명령이 두 방향 모두를 처리합니다 — 선언 이전에 쌓인 행 채우기, 그리고 규칙 변경 후 재계산. 두 번 돌리면 두 번째는 `changed: 0`입니다.

> 이 스크립트는 **DDL을 내지 않습니다**(`create_all` 없음). 파생을 고치는 도구가 자기가 고치는 스키마를 바꿀 수 있어서는 안 되기 때문입니다. 그래서 §2의 1단계는 **이 스크립트가 대신해 주지 않습니다.**

## 8. 잘못됐을 때 — 되돌리기

1. **선언만 되돌리기**: `columns`에서 해당 쌍을 지우면 새 쓰기부터 파생이 멈춥니다(TTL 5초 또는 `POST /admin/reload-configs`). **이미 쓰인 파생값은 남습니다** — 값이 남는 것이 곤란하면 `table_config.json`에서 컬럼을 지우는 별도 결정이 필요하고, [물리 컬럼은 선언을 지워도 남습니다](./table_config.md)(한 방향 문).
2. **파일 통째로 복구**:
   ```bash
   conda run -n assy_manager python server/scripts/backup_config.py list
   conda run -n assy_manager python server/scripts/backup_config.py restore notation_rules_<yymmdd>.json.bak --yes
   ```
3. **파일을 읽을 수 없게 됐을 때**(JSON 문법 오류 등): 쓰기가 실패하지 않습니다. 로더가 실패를 로그에 남기고 **「어떤 컬럼도 정규화하지 않음」**으로 떨어지며, 해석 보고서의 `sources`가 *「선언 파일을 읽지 못했습니다 ― 어떤 컬럼도 정규화되지 않습니다.」*로 바뀝니다. config 문제를 쓰기 장애로 바꾸지 않는 것이 의도된 거래입니다.

## 9. 함정

- 🔴 **「선언했는데 그리드가 그대로다」는 고장이 아닙니다** — 가시성은 세 번째 층이고 `display_columns`가 정합니다(§2.3). 이 환경의 14개 테이블은 전부 그것을 선언하고 있어 **기본이 「안 보임」**입니다. 반대로 `display_columns`가 없는 테이블에서는 **자동으로 뜨고**, 그때 파생 컬럼은 **편집 가능해 보이는데 쓰기는 거부**되므로(§4.4) 운영자에게 미리 알리십시오.
- ⚠️ **값은 안 보여도 이미 클라까지 갑니다.** `/data`의 행 페이로드와 CSV 추출은 `display_columns`가 아니라 `column_types` 기준입니다 — 그리드에서 숨겨도 **CSV에는 나옵니다.** 그것이 1단계에서 그리드를 넓히지 않고 접기 결과를 확인하는 방법입니다.
- ⚠️ **해석 보고서가 「유효」라고 해도 값이 나온다는 뜻은 아닙니다.** 그 보고서는 config만 봅니다 — §2의 (B)를 보십시오.
- ⚠️ **파생은 원본이 바뀐 쓰기에서만 갱신됩니다.** 규칙을 바꿔 놓고 재파생을 안 돌리면, 그 뒤로 건드린 행만 새 규칙이고 나머지는 옛 규칙 값입니다 — 한 컬럼 안에 두 세대가 섞입니다. **규칙 변경 뒤에는 항상 §7.**
- ⚠️ **선언 캐시 TTL이 5초라, 배치 도중에 규칙을 바꾸면 한 배치가 두 규칙 집합에 걸칠 수 있습니다.** 알려진 의도적 거래입니다 — 복구는 재파생입니다.
- ⚠️ **파생 실패는 쓰기를 실패시키지 않습니다.** `[NotationNorm]` ERROR 로그만 남고 원본 쓰기는 그대로 진행됩니다. 파생 컬럼이 조용히 비는 두 번째 경로이니, 값이 안 보이면 **로그에서 `[NotationNorm]`을 먼저 찾으십시오.**
- 🔴 **2단계를 「스위치 하나」로 계획하지 마십시오** — §0. 특히 조인은 **양쪽이 대칭으로 접히지 않습니다**: 위 실측에서 `dt_log.core_lot`은 15그룹이 합쳐지는데 `core_wafer_map.core_lot`은 0그룹입니다. 한쪽만 정규화해 이으면 **조용히 매칭이 줄어듭니다.**
