# `table_config.json` 세팅 — 동적 테이블 스키마 SSOT

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Lead / Backend
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
| `workspace_name` | string | 폴더 별칭 — 섀도잉·중복은 무시 + ERROR 로그 |
| `std_parse` | boolean, 기본 `true` | **JSON boolean만 유효** — 문자열 `"false"`는 무시 + 경고 |
| `source_priority` | {소스: 정수} | 소스 서열 맵의 테이블별 오버라이드 |
| `__comment` | string | 운영자 주석 — 코드 미소비, `install_product_tables.py`가 드리프트로 세지 않는 유일한 부분 |

추가 함정(미선언 컬럼 200 드롭·별칭 섀도잉 등)은 [CONFIG_GUIDE §6](../CONFIG_GUIDE.md).
