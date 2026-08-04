# `notation_rules.json` 세팅 — 표기 정규화(조회 시점 폴드)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-04 (🔴 **전면 재작성 — 이 문서가 서술하던 모델은 철회됐습니다.** `92b8d6f`가 출하한 **물리 파생 컬럼(`<컬럼>_norm`)**은 `8d306a5`에서 **아무도 소비하기 전에** 통째로 제거됐습니다(사용자 확정 2026-08-04). 지금 선언이 뜻하는 것은 「이 컬럼의 **표기가 정규화된 것으로 선언됐다**」 하나이고, 소비자가 **조회 시점에 비교의 양쪽을 SQL에서 접습니다**. **저장되는 것은 없습니다** — 파생 컬럼도, `<컬럼>_norm` 관례도, 재파생 스크립트도 이제 없습니다. 종전 판의 §2(층 셋)·§4.1·§4.2·§4.4·§7은 **전부 소멸했고**, 그 자리를 §2(한 단계)·§5.2(병합군 라우트)·§6(가상 조인의 함수 인덱스)이 대신합니다) | **Owner:** Backend / Ops
> 상위: [폴더 인덱스](./README.md) · 지도는 [CONFIG_GUIDE §1](../CONFIG_GUIDE.md) · **소비자는 [virtual_join_rules](./virtual_join_rules.md)** · 정본 코드는 `server/notation_norm.py`

<!-- Loader evidence (2026-08-04, 8d306a5 - measured against the tree, not transcribed):
  python fold:    notation_norm.fold_notation(text, rules)        (reference spelling)
  SQL fold:       notation_norm.fold_sql_text(inner_sql, rules)   (THE only Postgres spelling)
                  notation_norm.fold_notation_sql(expr, rules)    (SQLAlchemy expression)
                  notation_norm.SQL_FOLD_FUNCTION = "assy_fold_notation"  (non-PG dialects)
                  notation_norm.install_sqlite_fold()  <- database/database.py:67
  load/validate:  load_notation_rules / validate_notation_rules / _validate_column
                  rejection codes: undeclared, not_text, zero_pad_unimplemented,
                                   unknown_rule, shape
                  (would_rewrite_raw / key_column are GONE - they guarded a write)
  read entry:     normalized_by_table() -> rules_for_column / is_normalized
                  join_pair_rules(lt, lc, rt, rc)  <- "either side declared = both folded"
  cache:          RULES_CACHE_TTL = 5.0 + reset_cache()  (main.reload_local_process_cache)
  consumers:      virtual_join_executor.join_onclause      (the ON clause, both sides)
                  virtual_join_config.index_key_expression / required_index_ddl
  preview:        notation_norm.fold_preview / declared_previews (PREVIEW_GROUP_LIMIT 500)
                  GET /admin/config/notation/preview   (admin token; DB scan; read-only)
  report:         config_resolve_report._resolve_notation + notation_preview_detail
                  GET /admin/config/resolve?domain=notation   (config only, zero DB queries)
  tests:          server/tests/test_notation_normalization.py (30)
                  server/tests/test_notation_fold_contract.py (1 - shim)
                  contracts/notation_fold/ (43 vectors x 4 rule combinations, live PG)
  live state 2026-08-04: server/config/notation_rules.json DOES NOT EXIST (only .sample)
  GONE: server/scripts/rederive_notation_norm.py (deleted in 8d306a5)
-->

## 0. 🔴 이 문서를 어제 읽으셨다면 — 모델이 바뀌었습니다

| | 종전(`92b8d6f`, 철회) | 지금(`8d306a5`) |
|---|---|---|
| 선언이 뜻하는 것 | 「이 컬럼은 **저 컬럼으로 파생된다**」 | 「이 컬럼의 **표기가 정규화됐다**」 |
| 값 | 물리 컬럼 `<컬럼>_norm`에 **저장** | **아무것도 저장하지 않음** |
| 켜는 절차 | `table_config` 컬럼 → 이 파일 쌍 → `display_columns` (**층 셋**) | 이 파일에 **한 줄** |
| 소비 | 없음(1단계라 아무도 안 읽음) | **가상 조인의 키 비교**가 양쪽을 접어 씀 |
| 규칙이 틀렸을 때 | 규칙 고치고 **재파생 스크립트** 실행 | 규칙만 고치면 **다음 조회부터** 끝 |
| 쓰기 거부 | 파생 컬럼으로 가는 쓰기를 400으로 거부 | **거부할 것이 없음**(쓰기 경로에 존재하지 않음) |

**왜 뒤집혔나** — 이유는 취향이 아니라 실측이었고, `server/notation_norm.py` 모듈 상단에 그대로 남아 있습니다:

- **층 셋 사이에 조용한 실패가 있었습니다.** `table_config.json`에 컬럼을 적어만 놓고 물리 ALTER 착지를 확인하지 않으면, 해석 보고서는 「선언 1건이 유효」라고 답하는데 값은 영원히 비어 있었습니다.
- **파생 컬럼이 그 자체로 부채였습니다** — 보이는데 못 고치고, CSV에 딸려 나가며, `display_columns`에 넣는 순간 같은 헤더의 파일이 들어오면 그 배치 전체가 실패했습니다.
- 🔴 **결정타: 조인에 쓰려면 운영자가 `<컬럼>_norm`을 양쪽 `join_key`에 적어야 했습니다.** 실측 2026-08-04 — `dt_log.core_lot`은 병합군 15개, `core_wafer_map.core_lot`은 **0개**입니다. 깨끗한 쪽에 선언할 이유가 있는 운영자는 없고, **한쪽만 접힌 조인은 이미 맞고 있던 매치를 조용히 잃습니다.** 문법은 멀쩡한데 결과가 틀린 config는 만들 수 있는 것 중 가장 나쁜 모양이라 컬럼을 없앴습니다.

> 🔴 **`{"core_lot": "core_lot_norm"}` 같은 옛 선언은 그대로 두면 이름 붙여 거절됩니다.** 로더가 `derived` 키와 문자열 형태를 알아보고 *「`derived`는 더 이상 없습니다 — 정규화는 컬럼을 만들지 않고 비교의 양쪽을 접습니다」*라고 답합니다. `true`로 바꾸고, 아무도 안 쓰면 `table_config.json`에서 `<컬럼>_norm` 컬럼도 지우십시오(**물리 컬럼은 선언을 지워도 DB에 남습니다** — [table_config](./table_config.md)의 한 방향 문).

## 1. 무엇인가 — 아무것도 저장하지 않는다

같은 것을 여러 철자로 적어 온 값(`WF.01` / `WF-01` / `WF_01` / `wf 01`)을 **비교할 때만** 하나의 표기로 접습니다. 접는 자리는 **SQL이고 조회 시점**이며, 접힌 값이 어딘가에 남지 않습니다.

| 규칙 | 하는 일 | 위험 |
|---|---|---|
| `separator` | `.` `_` `-` 공백의 **연속**을 `-` 하나로 | 낮음 |
| `case` | **ASCII `a-z`만** 대문자로 | 낮음 |
| `zero_pad` | (앞자리 0 제거) | **미구현 — 켜면 이름 붙여 거절합니다** (§4.2) |

```
'CL-2601-001'        ->  'CL-2601-001'
'CL_2601_001'        ->  'CL-2601-001'
'WF.01'              ->  'WF-01'
'wf 01'              ->  'WF-01'
'WF--01'             ->  'WF-01'
'WF010'              ->  'WF010'      (zero_pad 미구현 — 안 접습니다)
None                 ->  None         (문자열이 아니면 그대로 통과)
```

**왜 `-`로 접는가.** `_`는 복합 맵 키를 **잇는 문자**입니다(`map_overlay.compose_map_id`). 값이 `_`를 품으면 그 값은 자기가 속한 키를 조각냅니다 — `core_lot`이 `CL_2601_001_09`이면 슬롯 `5`와 합친 키가 `lot='CL'` + `slot='2601_001_09_5'`로 되읽혀 **셀이 0개 그려집니다**. `_` 관례는 일부러 그렇게 만든 것이고, 이 기능은 그것을 바꾸지 않고 **`_`를 값 밖으로 몰아냅니다.**

### 1.1 🔴 안전 성질이 조건부에서 무조건으로 바뀌었습니다

종전 판은 「원본은 절대 안 고친다」를 **거절 셋으로 강제**했습니다. 지금은 **강제할 것이 없습니다** — 쓰기 자체가 없으므로 저장된 값은 **언제나 원본**이고, 규칙을 바꾸면 바뀌는 것은 **다음 질의가 계산하는 값**뿐입니다. 되돌릴 것도, 다시 파생할 것도, 치울 컬럼도 없습니다.

> 🔴 **사라진 거절 둘(`would_rewrite_raw`·`key_column`)은 완화된 것이 아니라 주어가 소멸한 것입니다.** 둘 다 **쓰기**를 막던 문구였습니다. 언젠가 접힌 값을 어딘가에 다시 저장하게 되면 **둘은 함께 돌아와야 하고**, 무엇을 지키던 것인지는 `notation_norm` 모듈 docstring이 기록으로 남기고 있습니다.

### 1.2 🔴 폴드가 **두 엔진에** 있고, 둘은 계약으로 채점됩니다

이 저장소가 반복해서 대가를 치른 결함 계급이 「같은 연산의 두 철자」입니다. 폴드는 파이썬(기준)과 SQL(실제로 도는 것) **양쪽에** 존재할 수밖에 없으므로, `contracts/notation_fold/`가 **살아 있는 PostgreSQL**에 벡터를 먹여 두 결과를 **바이트 단위로** 대조합니다(43벡터 × 규칙 조합 4).

그 대조가 **측정해서** 정한 것 셋 — 되돌리지 마십시오:

1. **`\s` / `[[:space:]]`는 이식성이 없고 두 엔진이 실제로 다릅니다.** 파이썬 `\s`는 29 코드포인트, 이 서버의 `[[:space:]]`는 그중 26개 + `U+180E`이고 `U+001C~U+001F`를 놓칩니다. 게다가 그 답은 **DB의 ctype에 딸린 성질**(실측 `Korean_Korea.949`)이라 리눅스 배포에서는 또 다릅니다. → 공백류는 **`\uXXXX`로 열거**되고 두 정규식이 **같은 상수 하나**에서 만들어집니다.
2. **`upper()`는 `str.upper()`가 아닙니다.** 실측 — `upper('straße')`는 에스체트를 유지하는데 파이썬은 `'STRASSE'`(길이가 바뀝니다), `upper('ı')`·`upper('ﬁ')`는 무동작입니다. → `case`는 **ASCII `a-z`만** 접고, 양쪽 다 `translate` / `str.translate`를 씁니다. **종전 `fold_notation`의 `.upper()`보다 좁아진 것**이고, 저장된 것이 없으므로 발밑이 바뀌는 값도 없습니다.
3. **`regexp_replace`는 `'g'` 없이는 첫 매치만 바꿉니다**(실측 `'WF.A_B 01'` → `'WF-A_B 01'`). 그 플래그는 `fold_sql_text` 한 곳에만 적혀 있습니다.

## 2. 켜는 것은 **한 단계**입니다

```json
{
  "rules": { "separator": true, "case": true, "zero_pad": false },
  "columns": {
    "dt_log": { "core_lot": true }
  }
}
```

이게 전부입니다. **`table_config.json`에 추가할 컬럼이 없고, `display_columns`에 대한 결정도 없고, 채워 넣을 과거 데이터도 없습니다.** 다음 질의부터 접힙니다.

**전제 하나**: 그 컬럼이 `table_config.json`에 **`"string"`으로 선언**돼 있어야 합니다(값을 텍스트로 읽고 있다면 이미 그렇습니다). `number`는 **거절**입니다 — 숫자에는 표기가 없고, `number` 컬럼은 `map_overlay.canonical_key_value`의 정수 파싱이 이미 `'01'`과 `'1'`을 한 값으로 만들고 있습니다(§4.3).

### 2.1 선언의 세 가지 형태

| 형태 | 뜻 |
|---|---|
| `"core_lot": true` | 정규화됨. 규칙은 테이블/파일 기본값을 상속 |
| `"core_lot": false` | **정규화 안 함 — 기록으로 남는 결정.** 로더가 거절 없이 건너뜁니다. 아예 안 적은 것과의 차이는 「누군가 보고 결정했다」가 다음 사람에게 보인다는 것 |
| `"core_lot": {"rules": {...}}` | 정규화됨 + 그 컬럼만의 규칙(테이블 기본값을 **대체**) |

규칙은 **파일 전체 → 테이블 → 컬럼** 순으로 덮이고, **병합이 아니라 대체**입니다 — 컬럼 수준에서 `{"separator": true}`만 적으면 나머지는 미지정이 아니라 **기본값**(`case:true`, `zero_pad:false`)이 들어옵니다.

`_`로 시작하는 이름은 로더에게 **주석**입니다. 그래서 샘플의 `_example_columns` 블록은 아무 효과가 없고, 켜는 방법은 그 안의 항목을 `columns`로 **옮기는** 것입니다.

### 2.2 반영 시점

`notation_rules.json`은 **config watcher의 감시 대상이 아닙니다**(watcher가 보는 파일은 `table_config.json` 하나뿐입니다). 반영은 두 갈래입니다:

- **자동**: 선언 캐시 TTL이 **5초**(`RULES_CACHE_TTL`) — 저장하고 5초 뒤 다음 조회부터. 워커 프로세스도 포함입니다.
- **즉시**: `POST /admin/reload-configs`(웹서버 프로세스의 캐시를 그 자리에서 버립니다).

> ✅ **「이미 쌓인 행은 어떻게 되나」라는 질문이 사라졌습니다.** 저장되는 값이 없으므로 과거 행과 새 행에 차이가 없습니다 — 규칙을 바꾸면 **모든 행이 같은 순간에** 새 규칙으로 비교됩니다. 종전 판의 「한 컬럼에 두 세대가 섞인다」 함정은 존재하지 않습니다.

## 3. 🔴 선언한 다음에 반드시 해야 할 것 — 무엇이 합쳐지는지 본다

선언은 「접겠다」이고, **「접었더니 서로 다른 두 로트가 하나가 되지는 않았나」는 데이터만 답할 수 있습니다.** 그 질문에 답하는 라우트가 따로 있습니다:

```bash
curl -H "X-Admin-Token: <토큰>" \
  "http://<서버>/admin/config/notation/preview?table=dt_log&column=core_lot"
```

- 인자를 **둘 다 생략하면 선언된 모든 컬럼**을 훑습니다. 한쪽만 주면 400입니다.
- 돌려주는 것은 원본→접힌값 나열이 아니라 **병합군**입니다 — 한 접힌 값에 원본 표기가 **둘 이상** 모인 그룹과 그 원본 목록. 나열은 「합쳐졌는가」를 묻는 사람에게 답하지 않습니다.
- 🔴 **접기는 조인이 쓰는 바로 그 SQL 식으로 계산됩니다.** 파이썬에서 접어 보여 주면 운영자가 신뢰하는 화면이 조인이 쓰지 않는 답을 보여 주게 되고, 그것이 이 기능이 없애려는 문제 그 자체입니다.
- ⚠️ **비쌉니다.** 접힌 식에는 평범한 인덱스가 없으므로 `GROUP BY`는 전수 스캔입니다. 운영자가 직접 부르는 점검용이고 **쓰기는 없으며**, 반환 **그룹** 수에 상한이 있습니다(`PREVIEW_GROUP_LIMIT` = 500 — 행이 아니라 그룹의 상한이라 돌아온 그룹의 수치는 정확하고, 상한에 닿으면 `truncated`가 말합니다).

**읽는 법은 하나입니다** — 숫자가 아니라 `variants` 목록을 읽고 **「이것들이 정말 같은 물리 로트인가」**에 답하십시오. 서버가 만들어 주는 문장이 이미 그렇게 묻습니다:

```
dt_log.core_lot: 원본 표기 30종이 15종으로 접힙니다. 서로 다른 원본 표기가 한 값으로
합쳐진 그룹이 15개입니다. 가장 큰 그룹은 'CL-2601-001'이고 원본 2종
(CL-2601-001 | CL_2601_001)이 여기로 모입니다. 이 목록을 읽고 「이것들이 정말 같은
것인가」를 확인하세요 — 하나라도 아니라면 notation_rules.json의 규칙을 고치면
됩니다(저장된 값은 원본 그대로라 되돌릴 것이 없습니다).
```

- 전부 같은 것이면 규칙이 옳습니다.
- **한 그룹이라도 아니면** 이 파일의 규칙을 고치십시오. **끝입니다** — 되돌릴 데이터가 없습니다.
- 병합군 0개면 그 컬럼에는 접을 것이 애초에 없었습니다. 이상이 아니고, 서버 문장이 *「조인 반대편이 지저분하다면 그쪽에서 효과가 납니다」*라고 덧붙입니다.

> ⚠️ **알려진 무해한 모양**: `variants`가 `-` · `_` · `.` · `--`처럼 **구분자만으로 된 값들**뿐인 그룹이 나올 수 있습니다(그런 값은 전부 `-` 하나로 접힙니다). 실제 로트가 아니라 원본 데이터의 쓰레기 값이 한자리에 모인 것이니 그것만 보고 규칙이 틀렸다고 판단하지 마십시오.

**이 환경에서 이미 측정된 결과**(2026-08-04, 운영 DB read-only):

| 컬럼 | 원본 철자 | 접은 뒤 | 병합군 |
|---|---:|---:|---:|
| `dt_log.core_lot` | 30 | **15** | **15** |
| `dt_log.dt_lot` | 6 | 6 | 0 |
| `dt_log.core_slot` | 34 | 34 | 0 |
| `core_wafer_map.core_lot` | 8 | 8 | 0 |
| `bonding_log.bond_lot` | 5 | 5 | 0 |
| `bonding_log.dt_lot` | 10 | 10 | 0 |
| `lot_event.lot` | 24 | 24 | 0 |

15개 그룹은 전부 `CL-2601-00x` / `CL_2601_00x` 한 쌍입니다(밑줄 형태가 766행). **의심스러운 병합은 한 건도 없었습니다.** 🔴 **그리고 이 표가 §6의 이유입니다** — 지저분한 쪽은 `dt_log`뿐이고 `core_wafer_map`은 0그룹이라, **깨끗한 쪽에 선언할 이유가 있는 운영자는 없습니다.**

## 4. 거절 — 이름과, 각각이 막아 주는 것

거절은 조용히 무시되지 않습니다. 전부 `code`가 붙고 `GET /admin/config/resolve?domain=notation`의 `rejected`에 한국어 앞머리와 함께 뜹니다.

### 4.1 `undeclared` — `table_config.json`에 없는 테이블/컬럼

`table 'no_such_table' is not registered in table_config.json` 또는 `column 'core_lot' is not declared in table_config.json for 'dt_log'`.

**막아 주는 것**: 오타 난 이름이 「선언했는데 아무 일도 안 일어난다」로 조용히 흘러가는 것. 🔴 **종전 판의 위험한 (B) 경우 — 「보고서는 유효라는데 값이 안 채워진다」 — 는 없어졌습니다.** 채울 물리 컬럼이 없으므로 「컬럼이 실제로 생겼는지 `information_schema`로 확인」하는 단계 자체가 사라졌습니다.

### 4.2 `zero_pad_unimplemented` — 켜져 있는 것처럼 읽히는 노브를 만들지 않는다

`"zero_pad": true`를 치면 나오고, 값은 `false`로 되돌려집니다.

```
rule 'zero_pad' is declared but NOT IMPLEMENTED, so it is refused rather than
silently ignored. It is the one rule that can merge two different entities
('WF010' and 'WF10' both become 'WF10'), and no census has said whether such a
collapse exists here. Run the fold preview first.
```

🔴 **이 거절은 선언 전체를 버리지 않습니다** — `zero_pad`만 꺼지고 나머지 규칙·컬럼 선언은 그대로 채택됩니다. `"zero_pad": false`는 거절이 아닙니다(명시적으로 끄기로 한 결정은 기록으로 남습니다).

**막아 주는 것**: 셋 중 **유일하게 서로 다른 것을 합칠 수 있는 규칙**이고, 「켜 놓았는데 아무 일도 안 하는 노브」입니다.

### 4.3 `not_text` — 문자열 컬럼이 아님

`table_config.json`에서 `"number"`(또는 `"datetime"`)로 선언된 컬럼을 지목했을 때:

```
column 'core_x' is declared 'number'; only a "string" column can be normalized.
A number has no notation - and for a 'number' column the integer parse already
folds '01' and '1' into one value
```

**막아 주는 것 둘**: ① 숫자에는 표기가 없다는 것 자체 ② 🔴 **SQL 폴드 식이 인덱스 식이 될 수 있을 만큼 짧게 유지되는 것.** 비텍스트 컬럼을 허용하면 폴드가 `crud.column_text_sql`의 `CASE` 식 위에 얹혀야 하고, 그러면 함수 인덱스 DDL이 **읽을 수도 맞출 수도 없게** 됩니다(§6).

> **slot과 앞자리 0 — 다시 열 필요 없는 질문이지만 조건이 붙습니다.** `slot`은 사용자 판정으로 항상 정수이고, `"number"`로 선언된 컬럼은 이미 `canonical_key_value`의 정수 파싱을 지나 `'01'`·`' 1 '`·`1.0`이 전부 `'1'`로 접힙니다. ⚠️ **다만 2026-08-04 실측으로 `dt_log.core_slot`·`dt_log.dt_slot`·`core_wafer_map.core_slot`·`bonding_log.bond_slot`은 전부 `"string"`으로 선언돼 있어 그 은퇴가 아직 발효되지 않았습니다.** 고칠 곳은 **선언된 타입**이지 `zero_pad` 구현이 아닙니다(타입 변경은 재기동 + 수동 마이그레이션 → [table_config](./table_config.md)).

### 4.4 나머지 (`unknown_rule` · `shape`)

| code | 언제 | 실제 메시지(발췌) |
|---|---|---|
| `unknown_rule` | 없는 규칙 이름 (예: `"transliterate": true`) | `unknown rule 'transliterate'; known rules are separator, case, zero_pad` |
| `shape` | 선언이 `true`/`false`/객체가 아님 | `declaration must be true, false, or an object {rules}` |
| `shape` | **옛 모델의 `derived` 키** | `'derived' is no longer a thing: normalization does not produce a column any more, it folds BOTH SIDES of a comparison at query time. ...` |
| `shape` | 파일이 객체가 아님 / `columns`가 객체가 아님 | `notation_rules.json must be an object; the whole file was ignored and NO column is normalized` |

> `unknown_rule`도 **선언 전체를 버리지 않습니다** — 모르는 이름만 무시하고 나머지는 채택됩니다.

## 5. 반영 확인 — 두 질문은 서로 다르고, 라우트도 다릅니다

| 질문 | 라우트 | DB를 보나 |
|---|---|---|
| 「내 선언이 먹었나 / 안 먹었으면 왜」 | `GET /admin/config/resolve?domain=notation` | **안 봅니다**(config만) |
| 「내 규칙이 무엇을 합치는가」 | `GET /admin/config/notation/preview` (§3) | **봅니다**(전수 스캔) |
| 「이 조인이 승인됐나」 | `GET /admin/config/virtual-join/verify` (§6) | 봅니다(`pg_index`) |

### 5.1 `?domain=notation`이 답하는 것

**A. 선언이 유효할 때** — `detail`이 그대로 화면에 렌더되는 문장입니다:

```
dt_log.core_lot의 표기가 정규화된 것으로 선언됐습니다. 적용 중인 규칙: separator, case.
이 컬럼이 조인 키로 쓰이면 **비교의 양쪽이 모두** 접힌 값으로 비교됩니다 — 반대편
컬럼에 선언이 없어도 그렇습니다(한쪽만 접으면 이미 맞고 있던 매치를 조용히 잃기
때문입니다). 저장되는 값은 없습니다: 원본은 원본 그대로 남고, 규칙을 고치면 다음
조회부터 바로 반영됩니다. 무엇이 무엇으로 합쳐지는지는
GET /admin/config/notation/preview?table=dt_log&column=core_lot 가 병합군으로
답합니다 — 규칙을 켠 다음 그것부터 보세요.
```

`fields`에 `{table, column, rules}`가 들어 있어 **어느 규칙 집합이 이 컬럼에 적용 중인지**를 눈으로 확인할 수 있습니다.

**B. 규칙이 하나도 안 켜져 있을 때**: 선언은 `effective`에 남되 *「적용할 규칙이 하나도 켜져 있지 않아 아무것도 접지 않습니다 — 선언은 유효하지만 비교는 원본 그대로입니다」*라고 말합니다.

**C. 아무것도 선언 안 했을 때**: `sources[0].detail`이 *「선언 0건이 유효합니다.」*, 파일이 없으면 *「선언 파일이 없습니다 — 표기 정규화가 적용되는 컬럼이 하나도 없습니다.」*, 읽지 못했으면 *「선언 파일을 읽지 못했습니다 — 어떤 컬럼도 정규화되지 않습니다.」*

> ⚠️ **`effective`는 「이 컬럼이 정규화됐다고 선언됐다」까지입니다.** 「무엇이 합쳐졌나」도 「그 조인이 실제로 도나」도 답하지 않습니다 — 위 표의 나머지 두 줄이 그 자리입니다.

## 6. 🔴 소비자 — 가상 조인, 그리고 **평범한 UNIQUE 인덱스로는 안 되는 이유**

오늘 이 선언을 읽는 유일한 소비자는 **가상 조인의 키 비교**입니다(`virtual_join_executor.join_onclause` — ON 절의 **단일 철자**).

**① 어느 한쪽이라도 선언됐으면 양쪽이 접힙니다.** 한쪽만 접을 수 있는 인자도, 플래그도, 호출 모양도 **일부러 없습니다**(`notation_norm.join_pair_rules`). 양쪽이 서로 다른 규칙으로 선언돼 있으면 유효 집합은 **합집합**입니다 — 폴드는 컬럼의 성질이 아니라 **비교의 성질**이고, 합집합은 두 선언을 모두 만족하는 최소 집합이자 **더 합칠 수는 있어도 매치를 잃지는 않는** 유일한 단조 선택입니다.

**② 승인 게이트의 방향이 뒤집힙니다.** 가상 조인의 승인 조건은 「조인 키를 덮는 유효한 UNIQUE 인덱스」인데, 키에 정규화가 걸리면 **평범한 b-tree 인덱스는 후보에서 배제되고 표현식(함수) 인덱스만 후보가 됩니다.** 이유가 성능이 아니라 **정확성**이라는 점에 주의하십시오:

> 원본으로 서로 다른 두 행(`'CL-1'`과 `'CL_1'`)이 접히면 **한 값**입니다. 컬럼에 UNIQUE가 있어도 **접힌 키로는 중복**이고, 그 중복이 곧 조인 팬아웃입니다. 즉 평범한 UNIQUE 인덱스는 **게이트가 묻는 유일성을 애초에 증명하지 못합니다.**

거부 코드는 `no_unique_index`이고, `GET /admin/config/virtual-join/verify`가 **만들어야 할 DDL을 그대로** 줍니다(정규화가 걸린 키에서는 함수 인덱스 형태이고, 인덱스 이름에 `_nf` 접미가 붙습니다):

```sql
CREATE UNIQUE INDEX CONCURRENTLY uq_vjoin_..._nf ON "core_wafer_map" (
  translate(
    regexp_replace("core_lot", '[	
 ... 　-]+', '-', 'g'),
    'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), ...);
```

> 🔴 **위 문자류는 발췌입니다** — 실제 식은 코드포인트 **31개를 `\uXXXX`로 전부 열거**하고 `-`가 **반드시 마지막**입니다(다른 자리면 범위 연산자가 됩니다. `_check_pattern_shape`가 임포트 시점에 그것을 단언합니다). **손으로 옮겨 적지 말고 `verify` 응답의 문장을 그대로 붙여 넣으십시오** — 한 글자만 달라도 PostgreSQL이 그 인덱스를 쓰지 않습니다.

- 🔴 **조회 식과 인덱스 식은 반드시 같은 함수(`fold_sql_text`)에서 나옵니다.** PostgreSQL은 질의 식이 인덱스 식과 **일치할 때만** 함수 인덱스를 씁니다 — 두 철자를 두면 이론적 불일치가 아니라 **1,000만 행 순차 스캔**이 되고 테스트는 전부 통과합니다.
- DDL이 길어 보이는 것은 대가입니다. `\uXXXX` 이스케이프라 **전부 ASCII**이고 psql에 그대로 붙여 넣을 수 있습니다(제어문자를 날것으로 싣지 않는 이유입니다).
- ⚠️ **접기는 공짜가 아닙니다.** `8d306a5` 실측 — 폴드 자체가 행당 3.06µs, 그리고 함수 인덱스를 만들기 전 `dt_log` 조인이 **3.1ms → 151.6ms**였습니다. 켜기 전에 §3의 병합군을 보고, 켠 뒤에는 인덱스를 만드십시오.

절차의 정본은 [virtual_join_rules](./virtual_join_rules.md)와 [CONFIG_ROLLOUT_GUIDE §5](../CONFIG_ROLLOUT_GUIDE.md)입니다.

## 7. 🔴 맵 키는 이 기능이 건드리지 않습니다

맵 키 조립·분해는 여전히 **원본 값**을 씁니다. `canonical_map_key`를 접힌 값으로 돌리는 것은 **설정 스위치가 아니라 데이터 마이그레이션**입니다 — `wafer_map_metadata`의 행이 **원본 신원**으로 등록돼 있어서, 맵 키가 정규화 값을 읽는 순간 기존 `map_id`가 자기 메타 행과 안 맞고 **맵이 안 열립니다.** 별도 라운드의 별도 결정이고, 아직 내려지지 않았습니다.

## 8. 규칙 사전

| 키 | 위치 | 타입 / 기본값 | 의미 |
|---|---|---|---|
| `rules` | 파일 최상위 | 객체, 기본 `{separator:true, case:true, zero_pad:false}` | 파일 전체의 기본 규칙 집합 |
| `rules` | `columns.<테이블>` 아래 | 객체 | 그 테이블의 기본값(파일 기본값을 **대체**) |
| `rules` | 컬럼 선언 객체 안 | 객체 | 그 컬럼만의 규칙(테이블 기본값을 **대체**) |
| `columns` | 파일 최상위 | `{테이블: {컬럼: true\|false\|{rules}}}` | 🔴 **비어 있으면 이 기능은 완전 무동작** |
| 컬럼 선언 | `columns.<테이블>` 아래 | `true` / `false` / `{"rules": {...}}` | ~~문자열(파생 컬럼 이름)~~ 은 **거절됩니다** |
| `_`로 시작하는 이름 | 어디든 | — | **주석**. 로더가 통째로 무시합니다 |

> 2026-08-04 이 환경의 실제 상태: `server/config/notation_rules.json`은 **아직 존재하지 않습니다**(`.sample`만). 파일이 없는 것은 거절이 아니라 「선언 없음」입니다. 출하되는 샘플은 `"columns": {}`라 **그대로 복사해 두면 완전 무동작**입니다.

## 9. 잘못됐을 때 — 되돌리기

1. **선언 되돌리기**: `columns`에서 그 줄을 지우거나 `false`로 바꾸면 **다음 조회부터** 원본 비교로 돌아갑니다(TTL 5초 또는 `POST /admin/reload-configs`). 🔴 **치울 데이터가 없습니다** — 저장된 것이 없기 때문입니다. 함수 인덱스는 남지만 해롭지 않고, 필요 없으면 `DROP INDEX`하면 됩니다.
2. **파일 통째로 복구**:
   ```bash
   conda run -n assy_manager python server/scripts/backup_config.py list
   conda run -n assy_manager python server/scripts/backup_config.py restore notation_rules_<yymmdd>.json.bak --yes
   ```
3. **파일을 읽을 수 없게 됐을 때**(JSON 문법 오류 등): 조회가 실패하지 않습니다. 로더가 실패를 로그에 남기고 **「어떤 컬럼도 정규화하지 않음」**으로 떨어집니다 — 이 기능이 생기기 전과 **정확히 같은 동작**(원본 비교)이라 안전한 방향입니다.

## 10. 함정

- 🔴 **`server/scripts/rederive_notation_norm.py`는 삭제됐습니다**(`8d306a5`). 다시 파생할 것이 없기 때문입니다. 그 명령이 적힌 문서를 보면 그것이 낡은 것입니다.
- 🔴 **`<컬럼>_norm` 컬럼이 이 환경에 있다면 그것은 잔여물입니다.** 코드 어디도 그것을 쓰지 않습니다. `table_config.json`에서 지워도 **물리 컬럼은 DB에 남습니다**(한 방향 문).
- 🔴 **한쪽만 접을 방법을 찾지 마십시오** — 없는 것이 설계입니다. 「깨끗한 쪽은 선언 안 해도 되겠지」가 맞는 이유가 바로 그것이고(§3의 표), 그래서 **어느 한쪽만 선언해도 양쪽이 접힙니다.**
- ⚠️ **선언 캐시 TTL이 5초라, 배치 도중에 규칙을 바꾸면 한 배치가 두 규칙 집합에 걸칠 수 있습니다.** 종전 판과 달리 **복구할 것은 없습니다** — 다음 조회가 이미 새 규칙입니다.
- ⚠️ **`case`가 ASCII만 접는다는 것을 「미구현」으로 읽지 마십시오** — §1.2의 실측이 강제한 **의도된 좁힘**입니다. 비ASCII 대소문자 폴딩을 넣으면 두 엔진이 갈라지고 계약이 빨개집니다.
- ⚠️ **`/admin/config/notation/preview`는 요청 경로에 상주할 질의가 아닙니다** — 전수 스캔입니다. 대시보드에 걸지 마십시오.
