# `table_config.json` 세팅 — 동적 테이블 스키마 SSOT

> **Status:** 🟢 Living | **Last-verified:** 2026-08-14 (**§5 `composite_key_source` 행에 🔴 「이 키가 없으면 재인제션이 거절된다」 추가 + §1에 「선언은 있는데 컬럼이 빠져 있을 때」 항목 추가** — `50a21c7`. 🔴 **이 라운드가 드러낸 실패 모양은 「선언이 없다」가 아니라 «선언 안에 컬럼이 없다»입니다**: `bonding_log`·`dt_map`의 코어 컬럼 아홉이 물리 DB에 **이미 있었는데** `column_types`에 없어서 **모든 writer의 셀이 200과 함께 드롭**됐고, 화면은 「데이터가 없다」로 읽혔습니다. **`__comment`가 그 컬럼들을 «설명»하고 있어도 선언이 아닙니다.** 직전 2026-08-13: **§5 `column_types` 행에 🔴 「선언을 고쳐도 물리 타입은 안 바뀐다」 추가** — `8bdc136`. 이 문서는 자기가 「동적 테이블 스키마 SSOT」라고 말하면서 **선언이 물리 DB에 도달하는 방향이 한쪽뿐**이라는 사실을 어디에도 적지 않고 있었다. 직전 2026-08-06: **§5 `map_push_ok` 행에 실측 한 줄 추가** — 이 키를 선언한 테이블이 `table_config.json`에도 `.sample`에도 **0건**입니다. 즉 오늘 모든 로그형 테이블에서 Push는 차단이고 확인창 경로는 한 번도 열리지 않습니다. **술어는 살아 있고 외연이 비어 있는 상태**라, 차단을 만난 운영자가 물어야 할 것은 코드가 아니라 이 키입니다(`version_column` §7.1과 같은 형태). 직전 🔴 **표기 정규화 진입점을 삭제했습니다** — `92b8d6f`의 파생 컬럼(`<컬럼>_norm`)이 `8d306a5`에서 철회돼 **이 파일에서 할 일이 없어졌습니다.** §1의 그 항목과 §5 두 행의 서술을 정정했고, 남은 접점은 **「`"string"`으로 선언돼 있어야 정규화할 수 있다」** 하나입니다. `display_columns`가 「그리드에 보이는가」의 단독 결정자라는 사실은 그대로 유효하지만 **표기 정규화와는 무관해졌습니다**. 직전: **§7 신설 — `version_column`**: `092b83f`로 착지한 버전 게이트의 운영자 문서. **오늘 이 키를 선언한 테이블은 없고 기능은 전부 무동작**이며, 켜는 것은 운영자입니다. 🔴 **§7.2가 이 절에서 제일 중요합니다** — 버전 게이트를 건 테이블이 동시에 **체인/결손보정 타깃**이면 그 파생 쓰기가 전부 거절됩니다. §5 키 표에도 행을 추가했습니다. 직전 2026-07-28 `deed6d2`: §5 키 표에 `map_push_ok` 행 — 로그형 테이블 에디터 Push 허용 선언, JSON boolean만 유효) | **Owner:** Lead / Backend
> 상위: [폴더 인덱스](./README.md) · [CONFIG_GUIDE](../CONFIG_GUIDE.md)(시나리오 S1/S2·리로드 규율 §4·함정 §6의 **정본**)

<!-- Loader evidence (2026-07-29):
  load: server/database/crud.py load_table_config (parse failure -> logged ERROR + {}) /
        load_table_config_or_raise (parse failure -> TableConfigError; boot path uses this)
        parse failure = undecodable OR bad JSON OR top level is not an object (H5).
        _decode_config_text honours UTF-8/UTF-16/UTF-32 BOMs (H1); no BOM -> strict utf-8.
  boot: server/main.py fail-fast on crud.TableConfigError; schema DDL moved out of module
        import into main.bootstrap_database_schema(), called from startup_event (#16a)
  hot-swap: server/database/config_watcher.py (basename == "table_config.json",
        on_modified + on_moved(dest_path) + on_created since 2026-07-29 #9/H3,
        TRAILING-edge 1s debounce - every event re-arms, fires after the last (H2))
  watcher: _maybe_reload/_fire/_reload; empty config -> ERROR "Config reload ABORTED", no silent skip
  refresh entrypoint: server/database/models.py refresh_dynamic_models (empty config -> keep existing singleton)
  tests: server/tests/test_config_reload_integrity.py
  key consumers: crud.py (business_key/composite_key_*/column_types), models.py:287 (dynamic Table build),
    parsers/directory_watcher.py:96 (workspace_name/std_parse), crud.py:247 (source_priority)
  restore in-place on purpose: server/scripts/backup_config.py:122-131
-->

## 1. 언제 이 파일을 만지는가

- **새 현장 테이블을 올릴 때** (그리드·인제션·다른 config가 그 테이블을 쓰려면 여기가 먼저)
- **기존 테이블에 컬럼을 추가할 때**
- **맵 테이블을 등록할 때** (`map_key_columns` + 좌표 컬럼 `number` 선언)
- 워크스페이스 폴더명이 테이블명과 다를 때 (`workspace_name`), 표준 파서를 끌 때 (`std_parse`)
- **제품 소유 테이블(`map_split_registry` 등) 설치/업그레이드** — 이때는 손편집이 아니라 `install_product_tables.py`를 씁니다 ([CONFIG_GUIDE §5.8-ter](../CONFIG_GUIDE.md))
- ~~**표기 정규화 파생 컬럼(`<컬럼>_norm`)을 만들 때**~~ — 🔴 **[2026-08-04 `8d306a5`] 이 항목은 삭제됐습니다.** 표기 정규화는 **파생 컬럼을 만들지 않습니다**(조회 시점에 비교의 양쪽을 접습니다). 이 파일에서 할 일은 **없고**, 유일한 전제는 대상 컬럼이 이미 `column_types`에 **`"string"`으로** 선언돼 있는 것뿐입니다(값을 텍스트로 읽고 있다면 이미 그렇습니다) → [notation_rules_config](./notation_rules_config.md)
- **같은 키의 행이 항상 「최신본」이어야 할 때** (`version_column` — §7. 철 지난 파일 재투입이 현재 값을 과거로 되돌리는 것을 막습니다. 🔴 **선언 전에 §7.2의 확인 한 줄을 먼저 돌리십시오**)
- **대문자 이름의 운영 테이블을 소문자로 개명할 때** (§6 — config만이 아니라 물리·데이터·폴더까지 걸린 절차)
- 🔴 **[2026-08-14 신설] 「그 컬럼에 값이 안 들어온다」는 신고를 받았을 때** — 컬럼이 물리 DB에 있는데 `column_types`에 없으면 **쓰기가 200을 받고 그 셀만 조용히 드롭**됩니다(미선언 컬럼 드롭 → [CONFIG_GUIDE §6](../CONFIG_GUIDE.md)). 화면에는 「데이터가 없다」로 보이므로 **인제션·체인·파서를 먼저 의심하기 쉽습니다.** 실사례 `50a21c7`: `bonding_log`의 `core_lot`/`core_slot`/`cx`/`cy`와 `dt_map`의 코어 컬럼 다섯이 **그 표가 선언된 이래** 빠져 있었고, 두 표의 `__comment`는 그동안 그 컬럼들을 **설명하고** 있었습니다. ⚠️ **`__comment`는 선언이 아니고 코드가 읽지도 않습니다** — 산문과 `column_types`가 어긋나면 언제나 `column_types`가 동작입니다. 확인 한 줄:
  ```sql
  SELECT column_name FROM information_schema.columns WHERE table_name = '<표>' ORDER BY 1;
  ```
  이 목록과 선언의 `column_types` 키 집합을 **집합으로** 대조하십시오 — **개수만 세면 안 됩니다.**

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. `server/config/table_config.json`을 열어 항목을 추가/수정합니다 (키는 §5, 스니펫 예):

   ```json
   "my_new_map": {
     "business_key": "pkg_id",
     "composite_key_source": ["base", "x", "y"],
     "column_types": { "pkg_id": "string", "base": "string", "x": "number", "y": "number", "leg": "string" },
     "display_columns": ["pkg_id", "base", "x", "y", "leg"],
     "map_key_columns": ["base"]
   }
   ```

   비-ASCII/공백 컬럼명은 피하고, 저장 전에 **유효한 JSON인지 확인**하십시오 — 파싱 실패 시 **웹서버가 뜨지 않습니다**(2026-07-29 #13, fail-fast). 로그에 `[Boot] Refusing to start - ... line N column M`이 남으니 그 위치를 고치고 재기동하십시오. 가동 중이라면 서버는 살아 있고 기존 스키마를 유지한 채 `[Config] ...` ERROR만 남습니다(편집은 반영되지 않음).

   여기서 "파싱 실패"는 셋입니다 — ①디코딩 불가 ②JSON 문법 오류 ③**최상위가 객체가 아님**(`[]`·`null`·빈 파일). ③은 예전에 게이트를 통과해 **동적 모델 0개로 부팅**했습니다(UI 빈 화면 + 거의 깨끗한 로그).
   **BOM은 파싱 실패가 아닙니다**(2026-07-29 H1). PowerShell 5.1의 `Set-Content -Encoding utf8`·`Out-File`(UTF-8 BOM)과 `>` 리다이렉트(UTF-16 LE), 메모장의 "UTF-8 with BOM"으로 저장해도 정상 로드됩니다. 예전에는 이것들이 전부 기동 차단 사유였습니다 — 파일은 어느 에디터에서 열어도 완벽해 보이는데 서버만 안 떴습니다.
3. **저장 방식은 자유입니다** (2026-07-29 #9/H2/H3). watcher는 `on_modified`(제자리 쓰기) · `on_moved`(같은 디렉터리 temp + rename) · `on_created`(**다른** 디렉터리 temp + rename — 이때는 `moved`가 아예 없습니다)를 모두 처리하고, 디바운스는 **트레일링 엣지**라 **연속 저장 중 어느 것도 버려지지 않습니다.** 반영은 **마지막 쓰기로부터 약 1초 뒤**이니, 저장 직후 즉시 확인하면 아직 안 보일 수 있습니다 — 1초 기다린 뒤 §3으로 확인하십시오.
   > 이 항목은 2026-07-29 이전에 **"in-place로 저장하라, 원자적 저장은 조용히 누락된다"** 였습니다. 그 시절 절차서를 기억하고 계신다면 더 이상 그럴 필요가 없습니다.
4. 반영 경로는 변경 종류에 따라 다릅니다:
   - **신규 테이블**: watcher 자동, 또는 `POST /admin/reload-configs` (`-H "X-Admin-Token: <토큰>"` — 토큰 설정 서버는 전 `/admin/*`에 필요)
   - **컬럼 추가(ALTER)**: **watcher 경로만** — reload-configs는 ALTER를 하지 않습니다
   - **컬럼 삭제·타입 변경**: 어떤 핫리로드도 반영하지 않음 — **재기동** + 수동 마이그레이션

## 3. 반영 확인

1. **웹서버 프로세스 로그**에서 watcher 발화 확인 (순서대로):
   ```
   Configuration change detected on ... Reloading dynamic models...
   Created missing physical tables at runtime: [...]        ← 신규 테이블일 때만
   Physical database schema synced successfully.
   Dynamic models reloaded and hot-swapped successfully.
   ```
2. **물리 반영의 유일한 증거는 DB**입니다:
   ```sql
   SELECT column_name, data_type FROM information_schema.columns
   WHERE table_name = '<table>' ORDER BY ordinal_position;
   ```
   🚨 `GET /tables/{t}/schema` 200은 증거가 아닙니다 — config 싱글턴을 읽을 뿐이라 DB에 없는 컬럼도 보입니다 ([CONFIG_GUIDE §4.3](../CONFIG_GUIDE.md)).
3. 신규 테이블이면 워크스페이스 자동 생성 확인: `GET /admin/file-ingestion/workspaces`.

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore table_config_<yymmdd>.json.bak --yes
```

restore는 **일부러 in-place로 써서 watcher를 발화**시킵니다(현재 파일은 `.prerollback.<ts>`로 보존, `Physical database schema synced successfully.` 로그로 확인). 단, **선언을 되돌려도 이미 만들어진 물리 테이블·컬럼은 남습니다**(한 방향 문) — 잔여물 검출은 `list_undeclared_tables.py`, 판단은 [ROLLBACK_PROCEDURE §5](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조 (테이블 항목당)

| 키 | 타입 / 기본값 | 의미 |
|---|---|---|
| `business_key` | string, 단일키일 때 필수 | 사용자 관점의 **실제 물리 키 컬럼명**. 원천에 합성 키 컬럼이 없다면 가짜 컬럼을 만들지 말고 이 키를 생략한 채 `composite_key_source`만 선언합니다 |
| `composite_key_source` | string[] | 복합 bk 구성 컬럼. `business_key` 물리 컬럼이 있으면 종전처럼 조립값을 그 컬럼에도 채우고, **없으면 프레임워크 시스템 컬럼 `business_key_val`에만 보관**합니다. 따라서 원천 스키마에 `cell_key` 같은 합성 컬럼을 추가할 필요가 없습니다.<br>🔴 **[2026-08-14 `50a21c7`] 이 키를 «선언하지 않은» 표는 인제션이 기존 행을 못 찾습니다 — 두 번째 파일이 통째로 거절됩니다.** 신원 해석기(`_get_or_create_row`)는 **`row_id`와 `business_key_val` 둘만** 보는데, payload에 `business_key_val`을 만들어 주는 것은 `assemble_composite_business_key`입니다. 그래서 단일 업무 키를 값으로만 실어 보내면서 `business_key_val`을 만들지 않는 경로는 신원 없이 도착해 **매번 새 행**이 되고, D3의 `uq_bk_<표>` 유니크 인덱스가 그것을 **3회 회복 시도 후 하드 실패**로 바꿉니다. **첫 쓰기는 성공하므로 처음 켤 때는 안 보입니다.** 판별 케이스·기전은 [architecture/data_model §3.1-quater](../../architecture/data_model.md), 운영자가 만나는 자리는 [process/OPERATOR_RUNBOOK §10](../../process/OPERATOR_RUNBOOK.md). ⚠️ **유니크 인덱스를 걷는 것은 처방이 아닙니다** — 인덱스가 없던 시절에는 같은 원인이 **같은 업무 키를 가진 행 둘**이라는 조용한 형태로 나타났을 뿐입니다 |
| `composite_key_separator` | string, 기본 `"_"` | 조합 구분자. 계획/맵 계열 제품 테이블은 `\|` — **바꾸지 말 것** |
| `column_types` | {컬럼: 타입} | `"string"`/`"number"`/`"datetime"` — 그 외는 String 처리. 시스템 컬럼(`created_at` 등 5종)은 쓰지 않음. 🔴 **[2026-08-13] 이 키를 고치는 것은 «절반»입니다 — 이미 있는 컬럼의 물리 타입은 절대 안 바뀝니다.** `sync_dynamic_tables_schema`는 `ALTER TABLE … ADD COLUMN`만 발행하고 **타입을 바꾸는 문장은 이 저장소 어디에도 없습니다.** 즉 `"number" → "string"` 수정은 **신규 설치에서만 맞고, 데이터가 든 바로 그 DB에서만 틀립니다**(`create_all`이 기존 테이블에 인덱스를 안 만드는 것과 같은 계급의 사각). 나머지 절반은 **마이그레이션 `.sql`을 같은 라운드에 내는 것**이고, 확인은 작업한 스크립트가 아니라 `server/scripts/audit_schema_canon.py`의 `declared_type_disagrees_with_catalogue`로 합니다. 실사례·절차는 [DEPLOY_SETUP §6 8-quinquies](../DEPLOY_SETUP.md), 타입 규칙의 정본은 [SCHEMA_CANON R1](../../architecture/SCHEMA_CANON.md)(식별자는 절대 수치형이 아니다). ⚠️ **표기 정규화는 이 키에 컬럼을 더하지 않습니다**(2026-08-04 `8d306a5` — 파생 컬럼 모델 철회). 여기서 걸리는 것은 **선언된 타입뿐**입니다: `notation_rules.json`은 **`"string"`으로 선언된 컬럼만** 정규화할 수 있고, `number`/`datetime`은 `not_text`로 거절합니다(숫자에는 표기가 없고, `number`는 정수 파싱이 이미 `'01'`과 `'1'`을 한 값으로 만듭니다) |
| `display_columns` | string[] | 그리드 표시 순서 + **표준 파서의 헤더 검증·적재 대상 집합**. 🔴 **이 키가 「그리드에 보이는가」의 단독 결정자입니다** — `/schema`는 선언돼 있으면 이 목록을 그대로 돌려주고 **없을 때만** 모델 컬럼을 열거합니다(`main.get_table_schema`). 즉 여기에 없는 컬럼은 **DB에 있어도 그리드에 안 뜹니다**(`/data` 페이로드와 CSV 추출은 반대로 `column_types` 기준이라 값은 그대로 나갑니다). ⚠️ **표기 정규화와는 무관합니다** — 그쪽은 컬럼을 만들지 않으므로 가시성 결정 자체가 없습니다(2026-08-04 정정) |
| `map_key_columns` | string[] | 🔴 **「이 테이블은 맵이다」 선언 그 자체다 — 삭제 범위 한정은 그중 하나일 뿐.** 세 가지가 이 한 줄에 달려 있다: ① 맵 replace 시 **삭제 범위 한정 키** ② **맵 에디터 테이블 목록에 뜨는 조건**(`map_editor.js`가 `/tables` 전 테이블의 `/schema`를 훑어 이 배열이 **비어 있지 않은** 것만 남긴다 — 미선언이면 그 테이블은 에디터에 **아예 없다**) ③ **인제션의 `wafer_map_metadata` 자동 등록 조건**(`map_meta_registrar`가 이 선언 **AND** 좌표 바인딩 해석을 둘 다 요구 — 미선언이면 메타가 0행이라 맵이 '화면기준'으로만 열린다). 🔴 **`map_overlay_config.table_bindings`에 좌표를 선언해도 이 줄을 대신하지 못한다** — 바인딩은 좌표만 말하고 「맵인가」는 여기서만 말한다(2026-08-02 실측: `dt_log`는 바인딩이 있는데 이 선언이 없어 에디터 목록에서 사라져 있었다). 값은 바인딩의 `key_columns`와 **같아야** 한다. 🔴 **④ [2026-08-14 F6] 이 선언이 곧 «인덱스»다** — `models.declared_key_columns`가 `map_key_columns` → 없으면 `composite_key_source` → 없으면 단일 컬럼 `business_key` 순으로 읽어 `idx_<표>_declared_key`를 만든다. **선언을 고치면 신규 테이블은 자동으로 따라오지만 기존 테이블은 안 따라온다** — `create_all`은 이미 있는 테이블에 인덱스를 추가하지 않으므로 `server/migrations/align_indexes_to_declarations.py`를 돌려야 한다. 정책·표별 근거는 [architecture/INDEX_POLICY](../../architecture/INDEX_POLICY.md) |
| `map_push_ok` | boolean, 기본 `false` | **로그형 테이블에 대한 에디터 Push 허용 선언.** 맵 에디터는 대상 테이블에 맵 계약(맵 키 + X/Y/값 + 시스템 컬럼, 합성 bk는 `composite_key_source`가 전부 계약 내 컬럼일 때만 서버 재생성이라 제외) 밖의 데이터 컬럼이 있으면 Push를 **차단**한다 — replace 적재가 그 컬럼 값을 전부 소실시키기 때문. `true` 선언 = "이 테이블로의 에디터 덮어쓰기는 알려진 흐름(R&D 수동 계측 등)이고 **소실을 인지하고 진행한다**" — 차단 대신 소실 컬럼명을 명시한 확인창 1회로 완화된다. 양산 전환 시 선언을 **제거**하면 다시 잠긴다. `std_parse`와 같은 규율: **JSON boolean `true`만 유효**, 문자열 `"true"` 등 오타는 false로 서빙.<br>⚠️ **[2026-08-06 실측] 이 키를 선언한 테이블은 이 저장소의 `table_config.json`에도 `.sample`에도 하나도 없습니다** — 즉 **오늘 모든 로그형 테이블에서 Push는 차단이고 확인창 경로는 한 번도 열리지 않습니다**(`version_column` §7.1과 같은 상태). 그런데도 서버는 **테이블마다** `/schema`에 이 필드를 실어 보내고(`main.get_table_schema`) 클라는 그것으로 게이트를 가릅니다(`push_columns.js` — `=== true`). **즉 술어는 살아 있고 외연이 비어 있습니다** — 「기능이 없다」가 아니라 「아무도 안 켰다」이고, 차단을 만난 운영자가 물어야 할 것은 코드가 아니라 **이 키**입니다 |
| `version_column` | string, 기본 없음(무동작) | **「이 테이블은 버전이 권위이고 도착 순서가 아니다」 선언.** 선언하면 **기계가 이미 있는 행을 덮어쓸 때** 「들어온 버전 > 저장된 버전」일 때만 반영합니다. 값은 **`column_types`에 있는 실제 컬럼명**이어야 하고, 없는 컬럼을 적으면 게이트가 꺼지는 것이 아니라 **기계의 모든 덮어쓰기가 거절**됩니다(안전한 방향 — 로그가 그 컬럼명을 찍습니다). 미선언·`null`은 **완전 무동작**(종전 last-write-wins 그대로). 🔴 **사람의 교정은 이 규칙 밖입니다** — 더 높은 버전도 사람이 고친 셀을 밀지 못하고, 그리드 편집은 게이트에 닿지도 않습니다. 🔴 **선언 전 필수 확인**: 그 테이블이 `chain_rules.json`의 `target_table`이거나 `enrichment_rules.json`의 `derived_table`이면 그 파생 쓰기가 전부 거절됩니다 → **절차·판정표·로그 읽는 법은 §7** |
| `workspace_name` | string | 폴더 별칭 — 섀도잉·중복은 무시 + ERROR 로그 |
| `std_parse` | boolean, 기본 `true` | **JSON boolean만 유효** — 문자열 `"false"`는 무시 + 경고 |
| `source_priority` | {소스: 정수} | 소스 서열 맵의 테이블별 오버라이드 |
| `__comment` | string | 운영자 주석 — 코드 미소비, `install_product_tables.py`가 드리프트로 세지 않는 유일한 부분 |

추가 함정(미선언 컬럼 200 드롭·별칭 섀도잉 등)은 [CONFIG_GUIDE §6](../CONFIG_GUIDE.md).

## 6. 대소문자 전환 절차 — 운영 테이블을 소문자로 개명할 때 (2026-07-28)

> **왜 이 절차가 필요한가.** PostgreSQL은 **따옴표 없는 식별자를 소문자로 접습니다**(fold — SQL 표준의 대문자 접기와 반대 방향인 PG 고유 규칙). 즉 `SELECT * FROM MyTable`은 `mytable`을 찾고, 대문자 이름의 테이블은 처음에 `CREATE TABLE "MyTable"`처럼 **따옴표로 만들었을 때만** 존재할 수 있습니다. 그 순간부터 그 테이블은 **모든 참조에 따옴표를 요구**하고, 동적 SQL·수기 쿼리·외부 도구 어느 하나라도 따옴표를 빼먹으면 "없는 테이블"이 됩니다. 전부 소문자로 통일하는 것이 유일하게 마찰 없는 상태이고, 이 절차는 그 전환을 **선언·데이터·물리를 한 번에** 옮기는 체크리스트입니다.

**절차 (순서 엄수):**

1. **스냅샷** — config 전체 + DB 백업:
   ```bash
   conda run -n assy_manager python server/scripts/backup_config.py snapshot
   ```
2. **콜드 스톱** — 5프로세스 전부 정지(`run_decoupled_app.py` 포함, 워처 필수). **watcher가 절반만 고친 선언을 봐서는 안 됩니다** — 살아 있으면 개명 도중의 config 저장이 발화해, 옛 이름의 물리 테이블을 새 이름으로 **다시 CREATE**합니다(한 방향 DDL — 잔여물이 됩니다).
3. **물리 개명** — 대문자 테이블마다:
   ```sql
   ALTER TABLE "UPPER_NAME" RENAME TO upper_name;   -- 새 이름은 따옴표 없이 = 소문자로 접힘
   ```
4. **테이블명을 담는 config 전수 소문자화** — 한 곳이라도 남으면 그 서브시스템만 조용히 죽습니다(대부분 `missing`/스킵으로 표면화):
   - `table_config.json` — **테이블 키** 자체
   - 계획 config 역할 바인딩 — `bonding_plan_config.json`·`transfer_plan_config.json`의 모든 `"table":` 값(`plan_store.registry` 포함)
   - `map_overlay_config.json` — `table_bindings`·`paint_lock` 등 테이블 키
   - `chain_rules.json` — `trigger_table`·`target_table` / `enrichment_rules.json` — `source_table`·`derived_table`
   - **`ingestion_workspace/` 폴더명** — 폴더명=테이블명 규약이므로 폴더도 개명(또는 `workspace_name` 별칭 선언). Windows는 대소문자 비구분이라 폴더는 멀쩡해 보여도, 워처의 테이블 매칭은 문자열 비교입니다
5. **테이블명을 값으로 담는 DATA 두 곳 UPDATE** — config가 아니라 **행 데이터**라 4에서 안 잡힙니다:
   ```sql
   UPDATE wafer_map_metadata SET target_table = lower(target_table) WHERE target_table <> lower(target_table);
   UPDATE map_split_registry SET ref_table   = lower(ref_table)   WHERE ref_table   <> lower(ref_table);
   ```
   (전자를 빼먹으면 개명된 맵이 전부 "메타 미등록"으로 강등되고, 후자를 빼먹으면 계획이 "없음"으로 보이다가 **다음 legend 저장이 새 이름 범위를 빈 계획으로 교체**할 수 있습니다 — replace 의미론.)
6. **기동** 후 검증:
   - `conda run -n assy_manager python server/scripts/list_undeclared_tables.py` — 옛 이름 잔여물이 검출되면 3~4 어딘가가 빠진 것
   - `GET /tables` — 새 소문자 이름으로 목록 확인
   - **맵 로드 1회**(메타가 있던 맵이 모달 없이 열리는가 = 5의 `wafer_map_metadata` 확인) + **인제션 1회**(해당 워크스페이스 드롭 → 적재 = 4의 폴더명 확인)
     > ⚠️ **모달이 떴다고 곧바로 5를 빠뜨렸다고 판정하지 마십시오**(2026-08-05 `98b48e9`). 좌표계 선택 모달은 **행이 없을 때뿐 아니라 행의 `grid_start_x/y`를 읽을 수 없을 때도** 뜹니다. 두 원인은 처방이 다르므로 `wafer_map_metadata`에서 그 맵 키의 행을 직접 확인하십시오 — **행이 없으면** 5의 개명 누락, **행이 있는데 START가 비었으면** 그 행 자체를 고쳐야 합니다.

> ⚠️ 이 절차는 **개명이지 롤백이 아닙니다** — 되돌리려면 같은 절차를 역방향으로 다시 밟아야 하며, 중간 상태(물리만 개명·config 미반영)로 기동하면 watcher가 옛 이름 테이블을 새로 만들어 **양쪽 이름의 테이블이 공존**하게 됩니다. 의심스러우면 [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md)의 스냅샷 복원부터.

---

## 7. `version_column` — 버전이 권위이고, 도착 순서는 아니다 (2026-08-04 `092b83f`)

> **한 줄.** 이 키를 선언한 테이블은 **기계가 이미 있는 행을 덮어쓸 때** 「들어온 버전 > 저장된 버전」일 때만 덮어씁니다.
> 🔴 **사람이 고친 셀은 이 규칙 밖입니다** — 더 높은 버전도 사람의 교정을 밀어내지 못합니다(§7.5).
>
> **출하 상태: 이 키를 선언한 테이블은 없고, 그래서 기능은 전부 무동작입니다.** 그게 의도된 출하 상태이고, 켜는 것은 운영자입니다.

### 7.1 대부분의 테이블은 이 키를 쓰지 않습니다

선언하지 않은 테이블은 이 기능이 **있기 전과 완전히 같습니다** — 나중에 도착한 쓰기가 이깁니다. 판정은 키가 없으면 첫 줄에서 돌아가고, 배치당 누산기조차 만들지 않습니다. `"version_column": null`도 **키가 아예 없는 것과 똑같이** 무동작이라, 「문서에는 적어 두되 아직 켜지 않는다」를 그 모양으로 남길 수 있습니다.

이 키가 필요한 테이블은 다음을 만족합니다:

> **같은 비즈니스 키의 행이 항상 「최신본」이어야 하고, 원본 파일에 그 최신성을 말하는 컬럼이 있다.**

증상으로 말하면 — **철 지난 파일을 다시 떨어뜨렸더니 현재 값이 과거로 되돌아갔다.** 지금 이 경로는 마지막 쓰기가 이기므로 그 되돌아감에 아무 기록도 남지 않습니다.

반대로, 그 일이 구조적으로 일어날 수 없는 테이블(적재할 때마다 새 키가 생기는 로그성 테이블 등)에는 **선언하지 마십시오.** 막을 것이 없고 §7.2만 떠안습니다.

### 7.2 🔴 선언하기 전에 반드시 돌리는 확인 한 줄 — 그 테이블이 파생 타깃인가

**버전 게이트를 건 테이블에 쓰는 모든 기계는 버전 컬럼을 들고 와야 합니다. 그런데 전부 그렇지는 않습니다.**

| 쓰는 주체 | 버전 컬럼을 들고 오나 |
|---|---|
| 파일 인제션(커스텀 파서·std 파서) | **예** — 파일에 그 컬럼이 있으니 페이로드에 실립니다 |
| 사람의 그리드 편집 | **면제** — `user` 소스는 게이트에 닿지도 않습니다(§7.5) |
| 맵 메타 자동 등록(`map_meta_registrar`) | **안전** — **부재한 행만** 만들고 기존 행은 손대지 않습니다. 생성은 덮어쓰기가 아니라 게이트를 그냥 지나갑니다 |
| **체인 워커** — `chain_rules.json`의 `target_table` | 🔴 **아니오** — 매퍼가 만든 컬럼만 씁니다 |
| **체인 재적용 R1** — `chain_replay_cli.py replay`(같은 룰 파일) | 🔴 **아니오** — 같은 매퍼 출력이라 결과도 같습니다 |
| **결손 보정 자동 확정 ①** — `enrichment_rules.json`의 `derived_table` + `auto_confirm` | 🔴 **아니오** — `target_fields`만 씁니다 |
| 결손 보정 소급 ⓒ — `backfill_enrichment.py` | **안전** — **새 파생 신원만** 만들고 이미 있는 행은 건너뜁니다 |

즉 **버전 게이트를 건 테이블이 동시에 파생 타깃이면, 그 파생 쓰기는 기존 행에 대해 전부 `version_missing`으로 거절됩니다.** 조용하지는 않습니다 — 로그가 이름을 부릅니다(§7.7). 다만 **운영자는 선언한 뒤에야 알게 됩니다.** 화면상 증상은 「체인이 멈춘 것 같다」이지 「버전 때문이다」가 아닙니다.

**그래서 선언 전에 이 한 줄을 돌립니다** (마지막 인자에 대상 테이블명):

```bash
conda run -n assy_manager python -c "import json,io,sys; t=sys.argv[1]; c=json.load(io.open('server/config/chain_rules.json',encoding='utf-8')).get('rules',[]); e=json.load(io.open('server/config/enrichment_rules.json',encoding='utf-8')); print('chain :', [(r.get('name'), r.get('enabled', True)) for r in c if r.get('target_table')==t] or 'none'); print('enrich:', [k for k,v in e.items() if isinstance(v,dict) and v.get('derived_table')==t] or 'none')" <테이블>
```

이 환경의 실측 출력(2026-08-04):

```
<테이블> = dt_log
  chain : none
  enrich: none

<테이블> = inventory_master
  chain : [('production_to_inventory_reservation_batch', True)]
  enrich: none

<테이블> = dt_job_attribution
  chain : none
  enrich: ['dt_job_lot_slot_attribution']
```

- **둘 다 `none`이면 선언해도 안전합니다** — `dt_log`가 그 경우입니다.
- **하나라도 이름이 나오면**, 그 룰의 **매퍼가 버전 컬럼도 함께 뱉도록 고쳐야** 합니다(코드 작업이므로 개발에 요청하십시오). 고치지 않고 선언하면 그 파생 경로는 그날부터 **기존 행을 갱신하지 못합니다.**
- 튜플의 두 번째 값(`True`/`False`)은 그 체인 룰이 **지금 켜져 있는지**입니다. **꺼져 있어도 없는 것으로 세지 마십시오** — 켜는 순간 같은 문제가 됩니다(`dt_map`의 `dt_log_to_dt_map`이 지금 그 상태입니다).

### 7.3 선언 방법

§2의 절차(스냅샷 → 저장 → 반영 확인)는 그대로이고, 항목에 한 줄이 늘 뿐입니다.

```json
"lot_summary": {
  "business_key": "lot_id",
  "version_column": "rev",
  "column_types": { "lot_id": "string", "rev": "number", "qty": "number", "grade": "string" },
  "display_columns": ["lot_id", "rev", "qty", "grade"]
}
```

- 버전 컬럼은 **`column_types`에 선언된 실제 컬럼**이어야 합니다. 🔴 **없는 컬럼 이름을 적으면 게이트가 꺼지는 것이 아니라 전부 거절됩니다** — 그 컬럼이 페이로드에 있을 수 없으므로 기계의 모든 덮어쓰기가 `version_missing`이 되고, 로그가 **적어 넣은 그 이름을 그대로** 찍어 오타를 찾게 해 줍니다. 잘못된 선언이 「게이트 없음」으로 열화되지 않는 쪽이 안전한 방향입니다.
- 이 키는 **물리 스키마를 바꾸지 않습니다**(ALTER 없음). watcher 반영만으로 즉시 유효하고, §3의 `information_schema` 확인은 이 키에는 해당하지 않습니다 — 반영 증거는 **다음 적재의 `[VersionGate]` 로그 줄**입니다(§7.7).
- `column_types`의 타입이 비교 방식을 **전부** 정하지는 않습니다 → §7.6.

### 7.4 판정은 행 단위이고, 결과마다 이름이 있다

🔴 **판정은 셀이 아니라 행 하나에 대해 한 번**, **행이 확정된 직후·어떤 셀도 건드리기 전에** 내려집니다. 그래서 거절된 행은 **반쯤 갱신된 상태가 되지 않습니다** — 통째로 들어오거나 통째로 안 들어옵니다. 거절된 행은 값도, `cell_sources`도, 감사 로그도, 실시간 브로드캐스트도 남기지 않습니다.

그리고 **게이트는 거절만 할 수 있습니다.** 통과가 「이 페이로드를 그대로 써라」는 뜻이 아닙니다 — 통과한 행도 셀 단위 레이어링을 그대로 지나갑니다(§7.5).

| 상황 | 로그에 붙는 이름 | 행이 반영되나 |
|---|---|---|
| 들어온 버전 **>** 저장된 버전 | (이름 없음 — 정상 통과) | ✅ 반영 |
| **새 행 생성** | (이름 없음) | ✅ 반영 — 생성은 덮어쓰기가 아니고, 되돌아갈 과거가 없습니다 |
| 사람의 편집(`user` 소스) | (게이트에 닿지 않음) | ✅ 반영 |
| 저장된 행에 쓸 수 있는 버전이 **없음** | `row_version_absent` | ✅ **반영 + 들어온 버전을 채택.** 거절하면 그 테이블이 수동 백필 뒤에 영원히 갇힙니다. 게이트를 막 켠 동안은 정상이고 **곧 멈춰야 합니다** |
| 들어온 버전 **<** 저장된 버전 | `version_older` | ❌ 거절 — 철 지난 파일이 늦게 온 것. **이 기능이 존재하는 이유** |
| 들어온 버전 **==** 저장된 버전 | `version_same` | ❌ 거절(무동작) |
| 버전은 그대로인데 **내용이 다름** | `version_same_content_differs` | ❌ 거절 + 🔴 **상류 결함 신호** — §7.7 |
| 들어온 버전이 **없거나 빈 값** | `version_missing` | ❌ 거절 — **모름은 과거도 미래도 아닙니다** |
| 버전을 **순서지을 수 없음** / 양쪽 종류가 다름 | `version_unorderable` | ❌ 거절 — 추측하지 않습니다 |

### 7.5 🔴 사람의 교정은 더 높은 버전에도 밀리지 않는다

**이 절에서 가장 중요한 문장이고, 이 시스템의 첫 번째 핵심가치입니다.**

**버전은 같은 우선순위 계층 *안에서만* 순서를 매기고, 계층을 넘지 않습니다.** 게이트는 레이어링 **앞에 놓인 거부권**이지 레이어링을 건너뛰는 승급권이 아닙니다. 행이 게이트를 통과해도 셀 하나하나는 종전대로 우선순위 판정을 지나가고, 거기서 `user`가 모든 기계 소스를 이깁니다(→ [data_model §2.1](../../architecture/data_model.md)).

실측 — `rev=1` 적재 → 사람이 `grade` 교정 → `rev=7` 적재:

| | `grade` | `qty` | `rev` |
|---|---|---|---|
| `rev=1` 적재 후 | `A` | 10 | 1 |
| 사람이 교정 | **`A-CORRECTED`** | 10 | 1 |
| `rev=7` 적재 후 | **`A-CORRECTED`** ← 사람 값 유지 | **99** | **7** |

**사람이 손대지 않은 셀은 앞으로 나아가고, 사람이 고친 셀만 그대로 남습니다.** 행 전체가 얼어붙는 것이 아닙니다.

반대 방향도 성립합니다 — **버전 게이트를 건 테이블도 사람에게는 계속 편집 가능합니다.** 그리드 편집은 셀 하나만 담고 버전 컬럼을 담지 않는데, 그것을 `version_missing`으로 거절하면 그 테이블이 사람에게 읽기 전용이 되어 이 기능의 취지가 뒤집힙니다. `user` 소스는 게이트에 닿기 전에 빠져나갑니다 — 실측하면 사람 편집에는 **`[VersionGate]` 줄이 한 줄도 남지 않습니다.**

### 7.6 버전 값은 어떻게 비교되나 — 텍스트 비교가 아닙니다

🔴 **컬럼을 `"string"`으로 선언했다고 문자열 비교가 되는 것이 아닙니다.** 비교 방식은 **값에서** 정해집니다. 문자열로 비교하면 `'10' < '9'`가 되어 순서가 뒤집히기 때문입니다.

| 버전 값의 모습 | 어떻게 읽히나 | 실측 |
|---|---|---|
| `"number"` 컬럼 | 숫자 | `rev=5` 뒤의 `rev=3` → 거절 |
| 텍스트 컬럼인데 **숫자로 읽히는 값** | **숫자로 먼저** 시도 | `'9'` → `'10'` 반영. 다시 `'9'` → 거절 (`10`이 `9`보다 **뒤**) |
| **ISO-8601 문자열** | 시각. **오프셋은 UTC로 접힙니다** | `10:00+09:00` 다음 `01:00+00:00`은 **같은 순간 → 무동작**, `02:00+00:00`은 반영 |
| `"datetime"` 컬럼 | 저장 측은 datetime 값, 들어오는 쪽은 파서가 뱉는 문자열 — 같은 순간으로 맞춰 비교. `18:00+09:00`과 `09:00Z`는 **같습니다** | |
| 그 밖의 텍스트 | **순서 없음 → 거절**(`version_unorderable`) | `REV_A` → `REV_B` 거절. `REV_B > REV_A`는 철자의 우연이지 버전 순서가 아닙니다 |
| **양쪽 종류가 다름** | **거절** — 코에르션하지 않습니다 | `'7'` 다음에 `'2026-08-04T09:00:00'` → 거절. 이건 앞으로 나아간 것이 아니라 **버전의 뜻이 바뀐 것**입니다 |
| `true`/`false` | 버전이 아님 → 거절 | |

> 버전 체계를 새로 정할 수 있다면 **정수 리비전** 또는 **ISO-8601 타임스탬프** 둘 중 하나로 고정하고, **한 테이블 안에서 종류를 섞지 마십시오.** 섞이는 순간 그 경계의 행들이 `version_unorderable`로 멈춥니다.

### 7.7 로그 읽는 법 — 인시던트 때 보는 자리

**행마다 한 줄씩 찍지 않습니다**(1,000만 행짜리 적재에서 행별 줄은 다른 모든 사건을 묻어버립니다). 대신 두 가지가 나옵니다.

**① WARNING — 그 프로세스에서 (테이블, 사유) 조합을 처음 본 순간 한 번.**

형태(작은따옴표 안이 현장 값):

```
[VersionGate] '<테이블>' is version-gated on column '<버전컬럼>': outcome '<사유>' seen for the first time in this process (source '<소스>'), N row(s) in this batch - <그 사유의 뜻 한 문장>. Repeats are reported at INFO, once per batch.
```

실측:

```
[VersionGate] 'vgdoc_lot' is version-gated on column 'rev': outcome 'version_older' seen for the first time in this process (source 'pipeline_parser'), 1 row(s) in this batch - the incoming version is LOWER than the stored one, so this is a superseded file arriving late - the stored row is kept. Repeats are reported at INFO, once per batch.
```

**② INFO — 배치마다 한 줄, 사유별 건수.**

```
[VersionGate] 'vgdoc_lot' version column 'rev', source 'pipeline_parser': version_older=200 out of 200 row(s) in this batch.
```

「아무것도 거절되지 않았다」와 「전부 거절됐다」가 **찾아본 사람에게 같아 보이지 않게** 하는 것이 이 줄의 목적입니다.

**첫 목격 WARNING은 (테이블, 사유)당 프로세스 수명에 한 번**입니다. 그래서 **WARNING이 또 떴다는 것 자체가 새 소식**입니다(같은 테이블의 *다른* 사유이거나, 다른 테이블). 반대로 **이미 본 사유는 계속 거절돼도 WARNING이 없으므로**, 지금도 막히고 있는지는 **INFO 줄의 숫자로** 봅니다. 프로세스를 재기동하면 첫 목격이 초기화됩니다.

**사유별로 무엇을 하는가:**

| 로그에 보이는 사유 | 무엇이 일어난 것인가 | 할 일 |
|---|---|---|
| `version_older` | 철 지난 파일이 늦게 도착해서 **막았습니다.** 이 기능이 하려던 일 그 자체 | 그 자체는 정상입니다. 반복되면 **왜 옛 파일이 자꾸 다시 들어오는가**를 상류에서 봅니다 |
| `version_same` | 같은 버전의 파일 재투입 | 내용까지 같다면 정상 상태입니다(아래 칸이 뜨지 않았다면 그렇습니다) |
| `version_same_content_differs` | 🔴 **버전은 안 움직였는데 내용은 바뀌었습니다** | **상류의 버전 관리가 깨졌습니다.** 로그의 `Differing column(s): ...`가 어느 컬럼인지 말해 줍니다. 이대로 두면 진짜 변경이 조용히 버려집니다 |
| `version_missing` | 들어온 행에 버전 값이 없습니다 | 소스가 `chain_ingestion`·`enrichment_auto_confirm`이면 **§7.2입니다**(매퍼가 버전 컬럼을 안 씁니다). 소스가 파서면 파일이나 파서가 그 컬럼을 안 싣고 있습니다. **선언한 컬럼명 오타**도 여기로 나옵니다 — 로그가 찍는 컬럼명이 테이블에 실제로 있는지 먼저 보십시오 |
| `version_unorderable` | 버전 값이 순서지을 수 없는 텍스트이거나, 값의 종류가 바뀌었습니다 | §7.6 |
| `row_version_absent` | 저장된 행에 버전이 없어 들어온 값을 **채택했고 행은 반영됐습니다** | 게이트를 켠 직후에는 정상입니다. **한참 뒤에도 계속 나오면** 그 키들이 매번 새로 만들어지고 있다는 뜻이니 비즈니스 키 쪽을 보십시오 |

⚠️ **`row_version_absent`는 거절이 아닙니다.** 다른 사유들과 **줄 모양이 같아서** 급할 때 뭉뚱그리기 쉽습니다 — 그 줄의 문장에 `the row WAS written`이 들어 있으니 **그 단어로** 가르십시오.

`version_same_content_differs` 실측(같은 `rev=5`인데 `grade`·`qty`가 바뀐 파일 재투입):

```
[VersionGate] 'vgdoc_lot' is version-gated on column 'rev': outcome 'version_same_content_differs' seen for the first time in this process (source 'pipeline_parser'), 1 row(s) in this batch - the version did NOT move but the content this source writes DID. The write was dropped; check version management upstream, because this is how a real change gets silently discarded. Differing column(s): grade, qty. Repeats are reported at INFO, once per batch.
```

> ⚠️ **「내용이 다르다」는 화면의 값이 아니라 *그 소스가 직전에 쓴 값*과 비교합니다.** 사람이 고친 셀은 파일과 영원히 달라지므로, 화면과 비교했다면 재투입할 때마다 거짓 경고가 떴을 것이고 — **항상 떠 있는 경고는 아무도 읽지 않습니다.** 실측: 사람이 고친 셀만 다른 재투입에서는 이 경고가 **나오지 않습니다.**

### 7.8 되돌리기

**키를 지우거나 `null`로 바꾸면** 즉시 이전 동작(마지막 쓰기가 이김)으로 돌아갑니다. watcher 반영만으로 충분하고 재기동·마이그레이션이 필요 없습니다 — 이 키는 **판정만 바꾸고 데이터 모양을 바꾸지 않기 때문입니다.**

- 게이트가 켜져 있는 동안 **거절된 쓰기는 애초에 일어나지 않았으므로** 되돌릴 흔적이 없습니다(§7.4).
- 다만 **막혀 있던 파일이 저절로 다시 들어오지는 않습니다** — 필요하면 그 파일을 `raws/`에 다시 투입하십시오.
- ⚠️ **`row_version_absent`로 채택된 버전 값은 남습니다.** 그건 정상적으로 쓰인 값이라 게이트를 꺼도 사라지지 않습니다.

> 게이트를 **켠 뒤 첫 적재**에서 확인할 것: `row_version_absent`(기존 행이 버전을 처음 갖는 정상 신호)가 나오고, `version_missing`이 **파생 소스 이름과 함께** 나오지는 않는지(→ §7.2를 건너뛴 것입니다).
