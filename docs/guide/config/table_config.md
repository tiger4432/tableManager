# `table_config.json` 세팅 — 동적 테이블 스키마 SSOT

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 (`deed6d2`: §5 키 표에 `map_push_ok` 행 — 로그형 테이블 에디터 Push 허용 선언, JSON boolean만 유효. 직전: §6 대소문자 전환 절차 신설 — 운영 테이블 소문자 개명 체크리스트) | **Owner:** Lead / Backend
> 상위: [폴더 인덱스](./README.md) · [CONFIG_GUIDE](../CONFIG_GUIDE.md)(시나리오 S1/S2·리로드 규율 §4·함정 §6의 **정본**)

<!-- Loader evidence (2026-07-28):
  load: server/database/crud.py:172 load_table_config (parse failure -> silent {})
  hot-swap: server/database/config_watcher.py:19 (basename == "table_config.json", on_modified only, 1s debounce)
  watcher log lines: config_watcher.py:29,46,48,50
  refresh entrypoint: server/database/models.py:524 refresh_dynamic_models (empty config -> keep existing singleton)
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
- **대문자 이름의 운영 테이블을 소문자로 개명할 때** (§6 — config만이 아니라 물리·데이터·폴더까지 걸린 절차)

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

   비-ASCII/공백 컬럼명은 피하고, 저장 전에 **유효한 JSON인지 확인**하십시오 — 파싱 실패는 로그 없이 `{}`가 되어 재기동 시 전 테이블이 사라집니다.
3. **제자리(in-place) 쓰기로 저장**합니다. watcher는 `on_modified`만 봅니다(1초 디바운스) — **temp 파일에 쓰고 rename하는 "원자적 저장" 도구는 watcher를 발화시키지 못해 ALTER가 조용히 누락됩니다** (이슈 #9). 에디터가 어느 쪽인지 모르면 저장 후 §3으로 확인하고, 미발화면 파일을 다시 열어 공백 하나 넣고 지운 뒤 재저장(in-place)하십시오.
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
| `business_key` | string (필수) | 사용자 관점 키 컬럼명 |
| `composite_key_source` | string[] | 복합 bk 구성 컬럼 — 지정 시 `business_key` 값 자동 생성 |
| `composite_key_separator` | string, 기본 `"_"` | 조합 구분자. 계획/맵 계열 제품 테이블은 `\|` — **바꾸지 말 것** |
| `column_types` | {컬럼: 타입} | `"string"`/`"number"`/`"datetime"` — 그 외는 String 처리. 시스템 컬럼(`created_at` 등 5종)은 쓰지 않음 |
| `display_columns` | string[] | 그리드 표시 순서 + **표준 파서의 헤더 검증·적재 대상 집합** |
| `map_key_columns` | string[] | 맵 replace 시 삭제 범위 한정 키(맵 테이블 전용) |
| `map_push_ok` | boolean, 기본 `false` | **로그형 테이블에 대한 에디터 Push 허용 선언.** 맵 에디터는 대상 테이블에 맵 계약(맵 키 + X/Y/값 + 시스템 컬럼, 합성 bk는 `composite_key_source`가 전부 계약 내 컬럼일 때만 서버 재생성이라 제외) 밖의 데이터 컬럼이 있으면 Push를 **차단**한다 — replace 적재가 그 컬럼 값을 전부 소실시키기 때문. `true` 선언 = "이 테이블로의 에디터 덮어쓰기는 알려진 흐름(R&D 수동 계측 등)이고 **소실을 인지하고 진행한다**" — 차단 대신 소실 컬럼명을 명시한 확인창 1회로 완화된다. 양산 전환 시 선언을 **제거**하면 다시 잠긴다. `std_parse`와 같은 규율: **JSON boolean `true`만 유효**, 문자열 `"true"` 등 오타는 false로 서빙 |
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
   - `ontology_mapping.json` — 테이블 키
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

> ⚠️ 이 절차는 **개명이지 롤백이 아닙니다** — 되돌리려면 같은 절차를 역방향으로 다시 밟아야 하며, 중간 상태(물리만 개명·config 미반영)로 기동하면 watcher가 옛 이름 테이블을 새로 만들어 **양쪽 이름의 테이블이 공존**하게 됩니다. 의심스러우면 [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md)의 스냅샷 복원부터.
