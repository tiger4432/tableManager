# Server — `.sample` config v1 잔재 정정 + 전제 테이블 명문화

- 담당: Server PM
- 일자: 2026-07-26
- 상태: **완료** (총괄 판단 1·2 반영 후 재검증)
- 커밋 없음. 라이브 config(비-sample) 무수정. 파일 삭제 없음. **실 DB DDL 0건**. `server/transfer_plan.py` 무수정.

---

## 0. 최종 변경 파일

| 파일 | 변경 |
|---|---|
| `server/config/transfer_plan_config.json.sample` | `plan_store` v1 잔재 제거 → v2 계약(`doe`/`doe_source`)으로 교체. `source_region`은 **미선언 유지**(휴면, 흔적만 `__comment`). 전제 테이블 1줄 추가 |
| `server/config/table_config.json.sample` | **제품 소유** `map_doe`·`map_doe_source`·**`map_split_registry`** 선언 추가 |
| `server/config/map_overlay_config.json.sample` | 폐기 테이블 `transfer_plan_map`의 `table_bindings`·`paint_lock` 제거. 전제 테이블 1줄 추가 |
| `server/config/bonding_plan_config.json.sample` | 전제 테이블 1줄 추가(`__doc__`) |
| `server/tests/test_api.py` | **`test_map_presets_api` 격리** — 라이브 `maps.json` 읽기·쓰기 제거(tmp_path + `MAPS_CONFIG_PATH` 몽키패치), 단언 대상을 테스트가 심은 프리셋으로 교체 · **`test_file_ingestion_callback_direct` 격리** — 워크스페이스를 tmp_path로 이동, 폐기된 `config.json` 생성 제거 |
| `docs/guide/CONFIG_GUIDE.md` | §5.8 경고 → 정정 사실로 교체. **§5.8-ter "기능별 필요 테이블 체크리스트"** 신설(제품 소유 4종 표 + bk 구분자 경고 포함) |

`enrichment_rules.json.sample`에는 **일부러 `__comment`를 넣지 않았다** — 이 파일의 루트는 `{rule_name: rule}`이라 주석 키가 규칙으로 파싱되어 매 로드마다 `[Enrichment:__comment] rule skipped` 경고가 찍힌다(`server/enrichment_config.py:237-244`). 대신 체크리스트 표에 enrichment 행을 넣어 덮었다.

## 1. 계약의 출처 (라이브 config 미참조)

| 요구 | 출처 |
|---|---|
| `doe` 필수 `(ref_table, map_key, doe_value, band_seq)` | `server/transfer_plan.py:209-210`, `:1138-1139` |
| `doe_source` 필수 `(… , source_lot, source_slot)` | `server/transfer_plan.py:213-217`, `:1178-1181` |
| 실제 소비 컬럼 | `_doe_get`: `doe_value`·`band_seq`·`stack_band`·`qty_total` / `_sget`: `source_lot`·`source_slot`·`qty`·`note` (`:1196-1203`, `:1236-1290`) |
| bk 조립 규칙(`\|` 구분자, `band_seq`가 키·`stack_band`는 라벨) | `server/transfer_plan.py:17-25` (모듈 독스트링 = 설계 정본) |
| 테이블명 `map_doe`/`map_doe_source` | `server/scripts/setup_transfer_plan_indexes.py:33-35` |
| 컬럼 형태 | `server/tests/test_transfer_plan.py:88-113` `TP_TABLES` |

## 2. 변경 전후 키 대조표

### 2-1. `transfer_plan_config.json.sample` → `plan_store`

| 역할 | before | after | 근거 |
|---|---|---|---|
| `plan` | `transfer_plan` / `plan_id, stage, target_lot, target_slot, status, memo` | **제거** | 계획 헤더 폐기(코드 미참조) |
| `map` | `transfer_plan_map` / `plan_id, x, y, val` | **제거** | 계획 맵 사본 폐기 |
| `doe_layer` | `transfer_plan_doe_layer` / `doe_key, layer, source_lot, source_slot, qty, note` | **제거** | "층마다 소스 1개" 차원 소멸 |
| `doe` | `transfer_plan_doe` / `plan_id, doe_value, source_lot, source_slot, qty_per_unit, layer_from, layer_to, knobs, description` — 필수 4개 **전부 부재 → `missing`** | `map_doe` / `ref_table, map_key, doe_value, band_seq, stack_band, qty_total, knobs, note` | 필수 4/4 |
| `doe_source` | **키 없음** | `map_doe_source` / `ref_table, map_key, doe_value, band_seq, source_lot, source_slot, qty, note` | 필수 6/6 |
| `source_region` | 키 없음 | **키 없음(유지)** + `plan_store.__comment`에 활성화 절차 명시 | **판단 2** |

### 2-2. `table_config.json.sample` (신규 — 판단 1 + 후속 판단)

| 테이블 | bk | `composite_key_source` (sep `\|`) | 그 외 컬럼 |
|---|---|---|---|
| `map_doe` | `doe_key` | `ref_table, map_key, doe_value, band_seq` | `stack_band, qty_total, knobs, note` |
| `map_doe_source` | `source_key` | `ref_table, map_key, doe_value, band_seq, source_lot, source_slot` | `qty, note` |
| `map_split_registry` | `split_key` | `ref_table, map_key, value` | `split_desc, color, eventtime` |

세 정의 모두에 `__comment`("제품 소유 저장소 — 이름·컬럼을 바꾸지 마라" + bk 설계 이유)를 넣었다.

**`map_split_registry` 컬럼의 역산 출처** — 라이브 config가 아니라 **소비 코드**다:

| 항목 | 출처 |
|---|---|
| bk 컬럼 `split_key`, 페이로드 `ref_table`·`map_key`·`value`·`split_desc`·`color`·`eventtime` | `client2/src/map_editor.js:176-198` (`buildLegendRegistryUpdates` — `PUT /tables/map_split_registry/data/updates` 페이로드 빌더) |
| 구분자 `\|`(필수) | 같은 파일 `:163-166` — "`map_key` 자체가 `_` 조인 문자열이고 테이블명에도 `_`가 흔하므로 bk 분리자는 `\|` 사용, `table_config`의 `composite_key_separator`와 반드시 일치" |
| 읽기 경로 컬럼 | 같은 파일 `:203-227` (`parseLegendRegistryRows` — `value`/`split_desc`/`color`/`map_key`) |
| 값 단위 속성의 정본이라는 지위 | `server/transfer_plan.py:26` |

> 역산 후 라이브 `table_config.json`의 정의와 **사후 대조**했더니 7개 컬럼·bk·구분자가 전부 일치했다(베낀 것이 아니라 독립 도출 → 교차 검증).

**경계 계약 무영향 확인**: `GET /tables/{t}/schema`는 원본 dict를 그대로 내보내지 않고 `display_columns`·`column_types`·`business_key`만 조립하므로(`server/main.py:1530-1556`) `__comment`는 스키마 응답에 노출되지 않는다. `init_dynamic_models`는 `column_types`만 읽으므로 등록에도 무해하다(검증 [2]).

**현장 소유는 선언하지 않았다** — `dt_map`, `dt_log`, `bonding_log`, `core_defect_map`, `eds_fail_map`, `wafer_process`, `bonding_job_inventory`. 사용자 지시("실 운영 환경은 테이블 명들이 다르니 커스텀 가능하게")대로 예시 스키마를 박지 않고 체크리스트로 유도한다.

### 2-3. `map_overlay_config.json.sample`

| 위치 | before | after |
|---|---|---|
| `table_bindings.transfer_plan_map` | 폐기 테이블 바인딩 | **제거** |
| `paint_lock.transfer_plan_map` | `from_overlay:[core_defect_map, eds_fail_map]` | 키명을 `__example_bonding_map`으로 (파일 내 기존 관례 `align_overrides.__example_eds_fail_map`와 동일) |

`paint_lock`은 정확한 테이블명 키 조회(`map_overlay.py:688-691`)라 `__example_` 키는 어떤 테이블에도 매칭되지 않는다 → **동작 변화 0**, 예시 문서 가치는 보존. `bonding_map`을 활성 항목으로 승격하면 신규 환경에 페인트 차단 정책을 임의로 강제하게 되어 하지 않았다.

### 2-4. `docs/guide/CONFIG_GUIDE.md`

- §5.8 doc-keeper 경고 → **정정 사실**로 교체(제거된 v1 역할/컬럼, 필수 키 세트, `.sample` 3종 복사만으로 `connected`가 되는 사실, `source_region` 미선언 사유와 활성화 절차).
- **§5.8-ter 기능별 필요 테이블 체크리스트** 신설 — "제품 소유 vs 현장 소유" 기준선 표 + 기능별(전사 계획 M2 / 본딩 가용량 M1 / enrichment / 맵 오버레이) 필요 테이블 표 + "표의 이름은 예시일 뿐 표준이 아니다" 경고 + 상태 확인 API. 기능을 켜는 순서를 **①`table_config.json` 선언 → ②바인딩의 `table`/`columns` 정렬**로 못 박았다.
- `.sample`의 전제 테이블 주석은 절 번호가 아니라 **제목**("기능별 필요 테이블 체크리스트")을 참조한다 — 번호 재정렬에 깨지지 않게.

## 3. 검증

### 3-1. 신규 환경 시뮬레이션 (요구 검증)

```
harness: <scratchpad>/verify_fresh_env.py   (conda run -n assy_manager python …)
격리:   .sample 3종(table_config / transfer_plan_config / map_overlay_config)을
        임시 디렉터리에 복사 → 그 복사본만 로드. 라이브 config 미접근.
        엔진은 sqlite:///:memory: 하나뿐 — 실 DB 커넥션·DDL 0건 (보드 이슈 #16 회피).
```

```
[0] table_config.json.sample tables: [bonding_map, inventory_master, large_table_100,
                                      map_doe, map_doe_source, map_split_registry,
                                      parts, production_plan, wafer_map_metadata]
[1] PASS — 제품 소유 4종 선언 / 현장 소유 0종 (판단1 기준선 준수)
[1-bis] PASS — bk 조립 계약(컬럼 순서·구분자 '|') 3종 일치
[2] PASS — init_dynamic_models OK (테이블 정의 내 __comment 키 무해)
[3] doe        -> map_doe        바인딩 8개 전부 table_config·ORM에 실재
[3] doe_source -> map_doe_source 바인딩 8개 전부 table_config·ORM에 실재
[4] _plan_store_statuses(fresh env) = {"doe": "connected", "doe_source": "connected"}
[4] PASS — source_region 키 없음 (판단2 준수)
[5] drop doe.columns.band_seq            -> doe=missing
[5] drop doe_source.columns.source_lot   -> doe_source=missing
[5] unknown table (map_doe_not_declared) -> doe=missing
[5] PASS — 컬럼 축·테이블 축 모두 결함을 잡는다
[6] PASS — paint_lock 키: ['*', '__example_bonding_map'] / 폐기 테이블 참조 없음
[7] PASS — sqlite 메모리에 map_doe/map_doe_source 물리 생성 확인
           (실 DB DDL 0건, engine.url=sqlite:///:memory:)

FRESH-ENV SIMULATION PASSED
```

검사 [5]에 **테이블 미선언 축**을 추가했다. 지난 대조군은 컬럼 축만 흔들었는데 이번 사건의 진짜 원인 축은 "바인딩은 멀쩡한데 테이블이 `table_config`에 없다"였다. 그 축을 활성화하지 않으면 [4]의 `connected`는 판단 1이 실제로 적용됐다는 증거가 되지 못한다.

검사 [1]의 `현장 소유 0종`은 **역방향 회귀 가드**다 — 나중에 누가 편의로 `dt_log` 같은 현장 테이블을 샘플에 박으면 즉시 실패한다. `[1-bis]`는 bk 구분자가 `_`로 되돌아가는 회귀를 잡는다(클라 `SPLIT_KEY_SEP`와의 계약).

### 3-2. `test_map_presets_api` 격리 (범위 확대분)

**무엇이 틀렸었나** — 이 API의 저장소는 DB가 아니라 파일(`server/config/maps.json`)인데 테스트가 그 경로를 그대로 썼다. 그래서 ①단언(`"std_300_12x13" in presets`)이 **`maps.json.sample`에만 있는 키를 라이브에서** 찾아 환경에 따라 상시 실패했고 ②`POST`가 **사용자 자산에 프리셋을 써넣었다**.

**어떻게 고쳤나** (`server/tests/test_api.py:611-`):

```python
maps_path = tmp_path / "maps.json"
maps_path.write_text(json.dumps(seeded), encoding="utf-8")
monkeypatch.setattr(main, "MAPS_CONFIG_PATH", str(maps_path))
assert str(tmp_path) in main.MAPS_CONFIG_PATH          # 격리 가드
...
assert set(res_data["presets"]) == {"pytest_seed_std"}  # 심은 것 '만' 보여야 한다
...
on_disk = json.loads(maps_path.read_text(encoding="utf-8"))
assert set(on_disk["presets"]) == {"pytest_seed_std"}   # 쓰기도 tmp에만
```

`load_maps_config`/`save_maps_config`가 모듈 전역 `MAPS_CONFIG_PATH`를 **호출 시점에** 읽으므로(`server/main.py:2856-2875`) 몽키패치로 저장소를 통째로 갈아끼울 수 있다. 프로젝트에 이미 있는 관례(`test_bonding_plan.py:151-152`, `test_map_overlay.py:121-122`의 `tmp_path` + `CONFIG_PATH` 몽키패치)를 그대로 따랐다.

단언 `set(presets) == {"pytest_seed_std"}`는 **격리 자체를 검사**한다 — 몽키패치가 풀리면 라이브 프리셋(`core_std` 등)이 섞여 들어와 즉시 깨진다. "심은 키가 있다"가 아니라 "심은 키 **만** 있다"로 쓴 이유다.

### 3-3. 전체 스위트 + 격리 증명 (바이트 동일성)

```
BEFORE sha256=5FCC8C8AF26624FDFF2997887C4B84F781A28E56F663D3CBEB4A7A0234BA000A
       bytes=1228  mtime=2026-07-26T01:34:54.6780247Z

conda run -n assy_manager python -m pytest server/tests/ -q
→ 414 passed, 13 warnings in 47.55s        ← 허용 실패 0

AFTER  sha256=5FCC8C8AF26624FDFF2997887C4B84F781A28E56F663D3CBEB4A7A0234BA000A
       bytes=1228  mtime=2026-07-26T01:34:54.6780247Z
LIVE maps.json UNCHANGED (byte-identical)
```

해시·크기뿐 아니라 **mtime까지 동일**하다 — 내용이 같게 다시 쓰인 것이 아니라 **파일이 열리지도 않았다**는 뜻이다.

`server/tests/test_transfer_plan.py -q` → **53 passed** (계약 무변경 확인).

### 3-4. `test_file_ingestion_callback_direct` 격리 (마지막 1건)

**격리 방식** — 몽키패치가 필요 없었다. `IngestionHandler.__init__`은 `workspace_path`·`config_path`·`archives_path`를 **전부 생성자 인자로 받는다**(`server/parsers/directory_watcher.py:441`). 라이브 경로를 쓴 건 테스트가 스스로 `dirname(__file__)/..`로 계산했기 때문이지 코드가 강제해서가 아니었다. 따라서 `tmp_path / "inventory_master"`를 넘기는 것으로 끝난다. 폴더명은 `inventory_master`로 유지했다 — 테이블명 해석이 `find_workspace_alias(folder_name, …)`부터 시작하므로(`:495-497`) 폴더명을 바꾸면 해석 경로가 달라진다.

**`config.json` 쓰기는 제거했다** (지시 2의 "필요성 판정"):

| 판정 근거 | 위치 |
|---|---|
| `config_path=None`을 시그니처가 명시 허용 (`config_path: str \| None`) | `directory_watcher.py:441` |
| 파일 부재를 로더가 정상 처리 (`if self.config_path and os.path.exists(...)`) | `:476` |
| 테이블명 우선순위 ①별칭 ②레거시 config ③`default_table_name` — 테스트는 `default_table_name="inventory_master"`를 넘기므로 **②를 지워도 ③에서 같은 값**으로 해석된다 | `:490-503` |
| 테스트가 쓰던 `columns` 키는 **아무도 읽지 않는다**(소비 필드는 `table_name`/`std_parse` 뿐) | `:485` |

즉 폐기된 파일을 세우지 않아도 테스트는 동일하게 성립한다 — 실제로 **414 passed** 유지. 대신 `assert not os.path.exists(workspace_root/"config"/"config.json")`을 넣어 **다시 세워지면 깨지게** 고정했다(폐기의 완료를 테스트가 지키게 한다). 격리 가드 `assert str(tmp_path) in handler.workspace_path`도 함께 넣었다.

파일 cleanup(`os.remove`)은 제거했다 — tmp_path는 pytest가 회수하므로 불필요하고, "정리하니까 괜찮다"는 논리 자체가 이번 사고의 원인이었다. DB 부작용(outbox) 정리만 남겼다.

### 3-5. 격리 증명 — `ingestion_workspace` **전체 트리** 해시

파일 9,230개 전체의 `(경로, sha256, size, mtime)`을 스위트 전후로 비교했다.

```
SNAPSHOT files=9230
→ 414 passed, 13 warnings in 53.50s
files_before=9230 files_after=9233
added=3 removed=0 changed=0
  +  bonding_log/archives/eqp_bonding_log_20260726_214402.csv
  +  inventory_master/archives/web_inventory_data_20260726_214503.csv
  +  wafer_process/archives/eqp_wafer_process_20260726_214504.csv
```

**`changed=0`이 핵심이다** — 기존 파일이 하나도 수정되지 않았다. 이전 판이라면 `inventory_master/config/config.json`이 `changed`로 떴어야 한다.

added 3건은 테스트가 아니라 **가동 중인 auto-update 수집기**의 산물이다. 그것을 추측이 아니라 **대조군으로 증명**했다 — pytest를 **돌리지 않고** 같은 길이(60s)의 창을 관측:

```
(elapsed 60s, pytest NOT run)
files_before=9234 files_after=9236
added=3 removed=1 changed=0
  +  bonding_log/archives/eqp_bonding_log_20260726_214604.csv
  +  inventory_master/archives/web_inventory_data_20260726_214604.csv
  +  inventory_master/archives/web_inventory_data_20260726_214700.csv
  -  inventory_master/raws/web_inventory_data_20260726_214604.csv
```

pytest 없이도 **같은 파일 계열이 같은 규모로** 생겨난다(수집기가 `raws/`에 떨구고 워처가 `archives/`로 옮기는 정상 파이프라인). 양쪽 창 모두 `changed=0`이고, 테스트 산출물 이름(`test_direct_callback.csv`)은 어느 쪽에도 없다. **테스트에 귀속되는 트리 변화는 0이다.**

대상 파일 직접 확인:

```
server/ingestion_workspace/inventory_master/config/config.json
  sha256 = a4fbcee2619989e605f6ad1ef58d7ce8c67518414d10c8dff49f0437d1afa465
  bytes  = 70
  mtime  = 2026-07-26T21:35:42   ← 격리 '이전' 마지막 스위트 실행 시각에 멈춰 있다
  (이후 21:44·21:45 두 번의 스위트 실행 동안 변경 없음)
```

`maps.json` 해시도 동일 유지(`5FCC8C8A…000A`).

### 3-6. 전수 Grep

폐기 테이블 참조(`transfer_plan_map|transfer_plan_doe_layer|"transfer_plan"`, gitignored 사용자 영역 포함): 코드 히트는 `client2/src/map_editor.js:3478`(주석), `server/transfer_plan.py`(독스트링)뿐 — **살아있는 의존 없음**.

## 4. 같은 부류 전수 스윕 — 사용자 자산/실 DB에 쓰는 테스트 (목록만, 미수정)

**DB 축은 깨끗하다.** `server/tests/` 전체에서 엔진은 `sqlite:///:memory:` 또는 tmp 파일뿐이고 `postgresql`/`psycopg2`/`DATABASE_URL` 사용처는 0건이다(`conftest.py:19-25`, `test_composite_business_key.py:20`, `test_ingestion_checkpoint.py:75`). **실 DB에 쓰는 테스트는 없다.**

**config/워크스페이스 축 — 잔여 0건.** 발견된 2건 모두 격리 완료다.

| # | 테스트 | 오염 대상(수정 전) | 조치 | 상태 |
|---|---|---|---|---|
| 1 | `test_api.py::test_map_presets_api` | 라이브 `server/config/maps.json`을 읽고 **프리셋을 써넣음** | `tmp_path` + `MAPS_CONFIG_PATH` 몽키패치, 단언을 자기가 심은 프리셋으로 교체 | **해결** (§3-2) |
| 2 | `test_api.py::test_file_ingestion_callback_direct` | 라이브 `server/ingestion_workspace/inventory_master/config/config.json`을 **덮어씀** | 워크스페이스를 `tmp_path`로 이동 + 폐기된 `config.json` 쓰기 **제거** | **해결** (§3-4) |

나머지 config 쓰기 테스트(`test_auto_update_toggle`, `test_bonding_plan`, `test_map_overlay`, `test_enrichment`, `test_ontology_g1`, `test_heavy_lane`, `test_std_parser`, `test_directory_watcher_errors`, `test_composite_business_key`, `test_ingestion_checkpoint`, `test_transfer_plan`)는 전부 `tmp_path` 기반이거나 `CONFIG_PATH` 몽키패치로 이미 격리돼 있다 — 문제 없음.

### 4-1. 이미 발생한 오염 (복구 불가 — 사용자 고지 대상)

**`server/ingestion_workspace/inventory_master/config/config.json`의 원본 내용은 미상이며 복구할 수 없다.**

- 현재 내용은 테스트 페이로드 그대로다: `{"table_name": "inventory_master", "columns": ["part_no", "category"]}` (70바이트, mtime `2026-07-26T21:35:42`).
- 이 파일은 gitignored라 **git으로 복원할 수 없고**, 언제부터 덮여 왔는지도 알 수 없다(이 테스트는 오래전부터 있었다). 이번 세션에서 내가 스위트를 돌린 것도 덮어쓰기에 포함된다.
- **"무해"라고 단정할 수 없다.** 하위호환 읽기 경로가 살아 있고(`directory_watcher.py:468-488`), 그중 **`std_parse`는 글로벌 다음 2순위로 실제 파싱 규칙을 주입한다**(`:516-533`). 현재 잔재에 `std_parse` 키가 없으니 지금 규칙 주입은 없지만, **사용자가 거기에 `std_parse`를 두었을 가능성은 배제할 수 없다** — 그랬다면 그 설정은 소실됐다.
- 지시대로 **지우지도 되돌리지도 않았다**(사용자 자산). 하위호환 읽기 경로(`directory_watcher`)도 건드리지 않았다 — 이번 범위는 테스트 격리다.

**라이브 `maps.json`의 `custom_1784890104442`도 지우지 않았다** — **정리 후보**로만 남긴다. 두 테스트가 격리됐으므로 새 오염은 더 생기지 않는다.

## 5. 남은 관찰 (수정하지 않음 — 판단 요청)

1. **`table_config.json.sample`의 `large_table_100`** — 성능 테스트용으로 보이는 엔트리가 신규 환경 템플릿에 남아 있다. §5.8-ter에 "예시 엔트리 — 교체·삭제 가능"으로 적었으나 템플릿에서 빼는 편이 깨끗하면 별건 처리 가능.
2. **`ontology_mapping.json.sample`은 테이블 참조 스캔만 했다** — 키 구조가 달라 전수 정합 감사는 하지 않았다. 필요하면 doc-keeper 사이클에 태울 것.
3. **`inventory_master/config/config.json` 잔재의 처분** — 지금은 테스트 페이로드가 남아 있다. 사용자에게 고지 후 삭제(하위호환 읽기가 파일 부재를 정상 처리하므로 무해)하는 편이 폐기 완료에 부합하나, 사용자 자산이라 판단을 넘긴다.

## 6. 인계 요약

- **검증**: 신규 환경 시뮬 8/8 PASS(네거티브 대조군 3축 + bk 구분자 계약) · **전체 스위트 414 passed / 0 failed** · 라이브 `maps.json` 해시·mtime 동일 · `ingestion_workspace` 9,230파일 트리 `changed=0`(무-pytest 대조군으로 배경 churn 분리) · `test_transfer_plan.py` 53 passed · 폐기 참조 Grep 클린 · 실 DB DDL 0건 · **사용자 자산 쓰기 0건**
- **커밋 안 함** — 총괄 diff 검수 대기. `CONFIG_GUIDE.md`에는 doc-keeper의 미커밋 변경이 이미 있었고 내 편집은 그 위(§5.8/§5.8-ter 구간)에 얹혔다.
- **히스토리 초안**: "`.sample` 정합 정정 — `transfer_plan_config.plan_store`를 v2 계약(`doe`/`doe_source`)으로 교체하고 `source_region`은 휴면이라 미선언 유지. 제품 소유 저장소 `map_doe`·`map_doe_source`를 `table_config.json.sample`에 선언(현장 소유 테이블은 의도적 미선언 — 표준 스키마 오해 방지). `map_overlay`의 폐기 `transfer_plan_map` 항목 제거. CONFIG_GUIDE에 §5.8-ter 기능별 필요 테이블 체크리스트 신설. 신규 환경 시뮬레이션으로 `.sample` 3종만으로 `plan_store: connected` 확인(실 DB DDL 0건)."
- **교훈 제안(`agent_workspace/memory/server-pm.md`)**:
  1. "`.sample` 정합성은 자기 파일만으로 판정할 수 없다 — 바인딩 샘플은 `table_config.json`에 테이블이 등록돼야 해석된다. 샘플을 고칠 때 **참조 테이블의 등록 여부까지** 확인하고 그 전제를 파일 `__comment`에 남겨라."
  2. "`.sample`에 무엇을 넣을지는 **'이 스키마를 누가 정하는가'**로 가른다 — 제품 소유는 선언, 현장 소유는 체크리스트로 유도(예시 스키마를 박으면 표준이 있는 것처럼 오해된다)."
  3. "검증의 결함 축은 **실패했던 그 축**이어야 한다. 컬럼 누락만 흔들고 테이블 미선언 축을 안 흔들면 `connected`는 아무것도 증명하지 못한다."
  4. "**상시 실패 테스트를 '알려진 실패'로 넘기지 마라.** 매번 눈으로 걸러내는 순간 스위트 전체가 신호를 잃는다 — 고치거나 지우거나 둘 중 하나다."
  5. "**파일이 저장소인 API는 테스트에서 반드시 경로를 갈아끼운다**(`tmp_path` + 경로 상수 몽키패치). 격리 증명은 '테스트가 통과했다'가 아니라 **사용자 파일의 해시·mtime이 그대로다**로 한다."
  6. "총괄이 대상을 열거해도 **기준선이 열거보다 우선한다** — 기준선에 명백히 걸리는 항목은 포함시키고 보고한다."
  7. "**테스트가 세우는 mock이 폐기된 개념이면 지워라.** 폐기 파일을 테스트가 계속 세우면 폐기가 완료되지 않는다 — 격리만으로 끝내지 말고 '이게 아직 필요한가'를 코드로 판정하라(`config_path=None` 허용 여부, 소비 필드 유무)."
  8. "**배경 프로세스가 도는 저장소에서 '변경 없음'을 주장하려면 대조군이 필요하다.** 가동 중인 수집기가 파일을 만들고 있으면 트리 diff만으로는 테스트 귀속을 못 가른다 — 같은 길이의 창을 **작업 없이** 관측해 배경 churn을 분리하라."
