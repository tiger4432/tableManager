# 인덱스 정책 — 선언이 인덱스를 정한다

> **Status:** 🟢 Living | **Last-verified:** 2026-08-14 (신설 — F6 라운드. `models.init_dynamic_models`가
> 하드코딩 목록 대신 `table_config.json`의 **선언**에서 인덱스를 파생하도록 바뀌었고, 아무도 안 읽는
> 감사 인덱스 두 가족이 은퇴했습니다. 판정 근거는 `R-2026-08-14-B`) | **Owner:** Backend / server-pm

> **이 문서를 읽어야 하는 때 (read trigger)**
> ① 동적 테이블에 인덱스를 **추가하려 할 때** — 여기 근거 칸이 못 채워지면 만들지 마십시오.
> ② `table_config.json`의 `map_key_columns`·`composite_key_source`·`business_key`를 **고칠 때** —
>    그 선언이 곧 인덱스입니다.
> ③ 인덱스가 **느려서 / 커서** 의심스러울 때 — §4 실측 가격표.
>
> **문서 위치 판단**: `server/database/models.py`의 리빙 문서는 `architecture/data_model.md`
> ([DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md) 「데이터 모델/레이어링」 행)입니다. 그런데 이 내용은
> **표별 18행 × 근거 칸**이라 절 하나로는 안 들어가고, 무엇보다 **읽는 시점이 다릅니다** — data_model은
> "이 시스템이 무엇을 저장하는가"를 볼 때 읽고, 이 문서는 "인덱스를 하나 더 만들까"를 결정할 때
> 읽습니다. 그래서 별도 문서로 두고 data_model §1.2에서 가리킵니다.

---

## 0. 규칙, 한 줄

**빌더가 만드는 모든 인덱스는 `table_config.json`의 선언 하나를 이름 댈 수 있어야 한다.**
이름 못 대는 인덱스는 선언이 아니라 **선언의 옷을 입은 드리프트**입니다(F3 판정의 적용).

동적 테이블 하나가 받는 인덱스는 **일곱**입니다.

| # | 인덱스 | 무엇의 선언인가 |
|---|---|---|
| 1 | `<표>_pkey` — `row_id` | 대리 기본키 |
| 2 | `ix_<표>_business_key_val` | `business_key` (프레임워크가 materialise한 값) |
| 3 | `idx_<표>_updated` — `(updated_at, row_id)` | 갱신 시각 정렬·워터마크 |
| 4 | `ix_<표>_updated_at` | 〃 (§3에 중복 고지) |
| 5 | `ix_<표>_is_graph_synced` | 그래프 동기화 커서 |
| 6 | `ix_<표>_needs_graph_rollback` | 〃 |
| 7 | **`idx_<표>_declared_key`** | **`map_key_columns` → 없으면 `composite_key_source` → 없으면 단일 컬럼 `business_key`** |

7번이 이 라운드에서 새로 생긴 것이고, 이 문서가 존재하는 이유입니다.
철자는 `server/database/models.py`의 `declared_key_columns` **한 곳**뿐입니다.

### 0.1 🔴 순진한 규칙이 왜 틀리는가 — 반례를 여기 남긴다

「`map_key_columns`를 인덱스한다」는 규칙은 **명백해 보이고 틀립니다.**

> **시스템에서 가장 많이 스캔된 인덱스는 `wafer_map_metadata`의 `(target_table, map_id)`이고
> (2026-08-14 `assy_manager` 실측 **44,103회**), 그 표는 `map_key_columns`를 아예 선언하지 않습니다.**
> `(target_table, map_id)`는 그 표의 `composite_key_source`입니다.

즉 순진한 규칙은 **시스템 최다 읽기를 통째로 놓치면서** 카디널리티 한 자릿수인 표 열 개에 인덱스를
얹었을 것입니다. `R-2026-08-14-B` ①이 canon 승격을 거절한 이유가 정확히 이것입니다.

그래서 규칙은 **3단 폴백**이고, 이 문단은 다음 사람이 같은 규칙을 다시 세우는 것을 막기 위해
문서에 남깁니다. 폴백 순서의 근거:

- `map_key_columns`가 **먼저**인 이유 — 선언한 아홉 표 전부에서 `map_key_columns`는
  `composite_key_source`의 **선두 접두**입니다(2026-08-14 라이브 config 전수 확인). 같은 조회를
  **더 좁은 인덱스**로 덮으므로 행당 WAL이 덜 듭니다.
- `business_key`가 **마지막**이고 `composite_key_source`가 없을 때만인 이유 — `dt_cell_key`·`cell_key`
  같은 **복합 셀 키는 컬럼이 아닙니다**. 이 게이트가 그것을 신원 컬럼으로 오인하는 것을 막습니다.
  같은 판단을 `chain_bindings.identity_column`이 이미 하고 있고, `declared_key_columns`는 그것을
  **아리티 1 → 임의 아리티**로 일반화한 것이지 두 번째 철자가 아닙니다.
- **전부 아니면 전무** — 선언이 없는 컬럼을 가리키면 인덱스를 통째로 **거절**하고 이유를 말합니다.
  일부만 인덱스하면 «선언과 다른» 인덱스가 조용히 생깁니다.

---

## 1. 표별 정책

> **읽는 법.** 「자동으로 붙는가」 칸이 **「자동화 불가」**인 행이 이 표에서 제일 중요한 정보입니다.
> 그 자리는 앞으로도 사람이 손으로 만들어야 하고, 그래서 잊힙니다.
>
> **스캔 수의 유효기간** — `stats_reset`이 NULL이고 postmaster가 **2026-08-13 08:37 KST** 기동이라
> 모든 스캔 수는 **하루치 개발 워크로드**입니다. 「어느 인덱스가 실제로 쓰이는가」에는 유효하고
> **운영 볼륨 주장에는 쓸 수 없습니다.** 그리고 이 박스는 운영이 아닙니다.
>
> **픽스처 오염** — 🧪 표시된 행 수는 합성이 섞여 있습니다(보드 ⚠️ 블록 기준):
> `void_obs`·`inspection_run` **100%**, `bonding_log` **98.5%**, `wafer_map_metadata` 72.9%.

| 표 | 무슨 목적의 읽기인가 | 그래서 어떤 인덱스가 필요한가 (술어를 «발행하는» 자리) | 어떻게 «자동으로» 붙는가 |
|---|---|---|---|
| **core_wafer_map**<br>24,749행 | 코어 웨이퍼 맵 **한 장을 (랏, 슬롯)으로 연다**. 화면이 맵을 열 때마다, 정렬 후보를 셀 때마다. | `(core_lot, core_slot)` — `map_overlay.build_key_filters`가 조립 → `map_alignment._cells_of`(셀 읽기) · `_count_cells`(맵당 COUNT) · `map_overlay.get_overlay` · `crud.derive_replace_map_scope`(replace_map DELETE 범위) · `_count_cells_bulk`(`GROUP BY` 전량) | ✅ `map_key_columns`.<br>이미 `idx_core_wafer_map_map_key`로 존재(**28,027 스캔**, 이 표 최다) — 손으로 만든 그 인덱스가 **규칙이 파생하는 것과 같습니다**(§6.1 이름 잔재) |
| **wafer_map_metadata**<br>3,431행 🧪 | 🔴 **맵 한 장의 격자 기하를 «어느 표의 어느 맵»으로 찾는다.** 맵을 그리는 모든 요청이 여기를 먼저 지납니다. | `(target_table, map_id)` — `map_overlay._meta_select`(`LIMIT 1`) · `map_alignment._meta_row_exists` · `_load_metas_reporting`(`map_id IN`) · `resolve_reference_catalog`(선두 컬럼만) · `bonding_plan.load_map_meta` | ✅ **`composite_key_source`** — `map_key_columns`가 **없습니다**.<br>🔴 **§0.1의 반례가 바로 이 행입니다** (**44,103 스캔**, 시스템 최다) |
| **map_split_registry**<br>166행 | legend/DOE 자체 목록을 **(참조표, 맵키)로 연다**. | `(ref_table, map_key)` — `transfer_plan.validate_plan` | ✅ `map_key_columns`. 이미 `idx_map_split_registry_ref_map`로 존재(17 스캔) |
| **bonding_log**<br>~~357,796행~~ → **368,371행** 🧪<br>(2026-08-14 재측정 · 실데이터 ~5,300)<br>⚠️ **선택도가 바뀐 컬럼 넷**: `core_lot`·`core_slot`·`cx`·`cy`가 **전부 NULL이던 상태에서 84,600행(랏 24개)이 채워졌다**([data_model §3.3](./data_model.md)). 오늘 그 컬럼을 타는 인덱스는 없지만, **붙일 때 「거의 전부 NULL」을 전제로 계획을 읽지 말 것** | ① 본딩 맵 **한 장을 (본딩랏, 슬롯)으로 연다** ② 🔴 **패키지 좌표에서 다이를 되짚는다**(원장 형제 조회) | ① `(bond_lot, bond_slot)` — `build_key_filters` · `derive_replace_map_scope`<br>② `(base_id, bx, by, row_id) INCLUDE (stack_height)` — `ledger_siblings._factors` · `_assemble` · `_scanned_in_universe` | ① ✅ `map_key_columns` — **오늘 이 인덱스가 없습니다**(가장 큰 실공백)<br>② ❌ **자동화 불가 — 손으로.** 이유: `(base_id, bx, by)`는 이 표의 **어떤 선언도 아닙니다**. 패키지 신원이지 맵 키가 아니고 `INCLUDE` 페이로드는 선언 어휘에 없습니다 → `server/migrations/add_bonding_base_join_index.sql`. `assy_qa`에서 **61,813 스캔**으로 그 박스 최다 |
| **dt_log**<br>13,789행 | ① DT 잡 **하나의 셀 전부를 연다** ② 설비·시각으로 잡을 되짚는다(귀속 참조 뷰) | ① `(dt_job)` — `build_key_filters` · `core_usage_mapper` · `core_alignment_mapper` · `dt_inventory_metadata_mapper` · `dt_standard_map_mapper` · `enrichment_rules.json`의 참조 뷰 `WHERE dt_job = :dt_job`<br>② `(dt_eqp, event_time)` — 같은 참조 뷰의 `d.dt_eqp = j.eqp AND d.event_time = j.et` | ① ✅ `map_key_columns`<br>② ❌ **자동화 불가 — 손으로.** 이유: **조인 술어가 config JSON 안의 SQL 문자열**에 있습니다. 선언 어휘에 「이 두 컬럼으로 조인한다」를 적는 자리가 없습니다 → `add_dt_log_trigger_indexes.sql`(헤더가 **NOT RUN**이라 밝히고 있고 여전히 안 돌았습니다) |
| **dt_core_view**<br>366행 | DT 잡 하나의 코어 좌표 투영을 연다(정렬 검토용). | `(dt_job)` — `build_key_filters` · 정렬 워크리스트 | ✅ `map_key_columns` |
| **dt_map**<br>5,619행 | 파생된 DT 맵 한 장을 **(DT랏, 슬롯)으로 연다**. | `(dt_lot, dt_slot)` — `build_key_filters` · `derive_replace_map_scope` | ✅ `map_key_columns`.<br>⚠️ 이 박스에서 **distinct 2 / 5,619행** — 등호 조회가 표의 절반을 돌려주므로 플래너가 안 씁니다. 그런데 **선언이 바뀌면 인덱스가 자동으로 따라갑니다** — `R-2026-08-14-A`가 회부한 writer/reader 키 분열이 뒤집히면 손댈 파일이 **0개**입니다. 그것이 이 규칙이 사는 것입니다 |
| **core_usage_map**<br>366행 | 코어 사용 오버레이 한 장을 **웨이퍼로 연다**. | `(core_wafer)` — `build_key_filters` · `derive_replace_map_scope`(`scope: {core_wafer: …}`) | ✅ `map_key_columns`. ⚠️ distinct 2 / 366행 |
| **bonding_map**<br>413행 | 패키지 격자 한 장을 **base로 연다**. | `(base)` — `build_key_filters`(파생 바인딩) | ✅ `map_key_columns`.<br>⚠️ 이 박스는 **대표성이 없습니다** — `server/value_suggest.py`의 자체 실측이 **운영 1.75M행 `bonding_map`**을 인용합니다. 여기 413행/distinct 1을 근거로 「쓸모없다」고 판정하면 안 됩니다 |
| **valid_die_ref**<br>4,598행 | 유효 다이 맵(바닥 표)을 **(제품, 타입)으로 연다**, 그리고 **카탈로그가 맵별 셀 수를 한 번에 센다**. | `(product, type)` — `map_overlay._resolve_valid_die_uncached` · `map_alignment._cells_of`/`_count_cells` · 🔴 **`_count_cells_bulk`의 `SELECT product, type, count(*) … GROUP BY 1,2` (WHERE 없음, 카탈로그 요청마다 1회 전량)** | ✅ `map_key_columns`.<br>`R-2026-08-14-A` F5는 「지금 안 건다」였고 **등호 조회 근거로는 여전히 맞습니다**(distinct **8** / 97페이지 = 12.5% 선택도). 그러나 **소비자가 하나 더 있습니다** — 위 `GROUP BY`는 인덱스가 있으면 HashAgg → GroupAgg가 됩니다. 같은 문장 모양을 `core_wafer_map`에서 잰 수: **7.899 ms → 4.782 ms**(§2.1) |
| **void_obs**<br>91,756행 🧪 | 스캔 한 번이 본 보이드를 **런으로 모은다**(분모 조인). | `(run_uid, …)` — `ledger_siblings._Plan._build`의 `JOIN runs r ON r.run_key = o.run_uid` — **선두 컬럼**이 조인 키 | ✅ `composite_key_source` = `(run_uid, inchip_x, inchip_y)`.<br>❌ **자동화 불가(별건)**: `idx_void_obs_area`는 `pi() * radius_x * radius_y`에 걸린 **식 인덱스**입니다. **식은 선언이 아닙니다** → `add_void_schema_indexes.sql` |
| **delam_obs**<br>10,421행 🧪 | 〃 (박리 관측) | `(run_uid, …)` — 같은 `_Plan._build`, `finding_kinds.observation_table`이 표 이름을 종류에서 뽑습니다 | ✅ `composite_key_source`.<br>⚠️ `void_obs`가 가진 **면적 식 인덱스에 대응하는 것이 없습니다**(data_model §1.2-bis가 이미 지적) — 크기 질의를 붙일 때 **함께** 필요합니다 |
| **inspection_run**<br>107,500행 🧪 | ① 어떤 방법으로 **스캔이 일어났는가**(분모) ② 패키지 좌표로 스캔 이력을 되짚는다 | ① `(method, …)` — `ledger_siblings._Plan._build`의 `WHERE method = ANY(:methods) [AND observed_at 범위]` · `finding_kinds.population_ctes`<br>② `(base_wafer_id, base_x, base_y, stack_gate, observed_at DESC)` — `_factors`의 `JOIN … ON base_wafer_id/base_x/base_y` | ① ✅ `composite_key_source`(6칸).<br>🔴 **여기가 이 규칙이 제일 비싸고 제일 안 듣는 자리입니다** — 선두 `method`가 실제로 술어에 있긴 한데 **distinct 2 / 107,500행**(53,750행/키)이라 안 좁힙니다. 비용은 §4에서 **+131.2 B/행**으로 실측했습니다. 폭이 선언에서 나오므로 줄이려면 **선언을 고쳐야** 합니다(코드가 아니라)<br>② ❌ **자동화 불가 — 손으로.** 선두가 `method`가 아니라 `base_wafer_id`이고 `observed_at DESC`라 **정렬 방향까지 필요**합니다. 선언은 정렬 방향을 말하지 않습니다 → `add_void_schema_indexes.sql` §3 |
| **lot_event**<br>44행 | ① 원장 백필이 **시각 순서로 걸어 나간다** ② 참조 뷰가 `track_in` 사건을 설비·시각으로 찾는다 | ① `(event_time, business_key_val)` — `ledger/backfill.fetch_page`의 `WHERE event_time > ? ORDER BY event_time, business_key_val LIMIT` · `fetch_group` · `ledger/observability.probe_source_head`<br>② `(event_type, equipment, event_time)` — `enrichment_rules.json`의 참조 뷰 | 🔴 **선언 인덱스 `(lot, event_type, event_time)`은 오늘 읽는 사람이 없습니다.** 선두 `lot`은 어디에서도 술어가 아니고 **SELECT만 됩니다.**<br>① ❌ **자동화 불가 — 손으로.** 백필의 키셋 커서는 `ledger_config.json`이 정하고 `table_config`가 아닙니다<br>규칙은 그래도 붙입니다(44행이라 비용 0에 가깝고, 규칙에 표별 예외를 파는 순간 규칙이 아니게 됩니다). **원장 백필이 규모로 돌기 시작하면 ① 인덱스가 필요해집니다 — 그때 손으로.** |
| **wafer_id_status**<br>59행 | 서버 쪽 술어가 **하나도 없습니다.** 그리드가 컬럼 필터를 걸 때만 읽힙니다. | `(core_lot, core_slot, valid_from)` — `main.apply_column_filters`(AG-Grid `?filters=`) · `value_suggest.suggest_values` | ✅ `composite_key_source`.<br>근거가 **범용 그리드 필터뿐**이고, 그 경로는 선두 컬럼 등호에서만 인덱스를 씁니다. 59행이라 비용도 이득도 0에 수렴 |
| **dt_inventory**<br>251행 | 🔴 **잡 하나의 프레임/변환식을 «잡 번호»로 찾는다.** 코어 사용 맵과 정렬 워크리스트가 이걸로 조인합니다. | `(dt_job)` — `core_usage_mapper`의 `WHERE dt_inventory.dt_job IN (all_jobs)` · `map_alignment.build_alignment_worklist`의 `dt_job == val` / `ilike` · `enrichment_analysis.iter_derived_rows` | ✅ **`business_key`** (3단 폴백의 마지막 층).<br>🔴 **이 행이 3층이 존재하는 이유입니다** — `map_key_columns`도 `composite_key_source`도 없지만 **업무 키가 진짜 컬럼**이고 코드가 그 컬럼으로 WHERE를 냅니다. 251행 전부 유일 키이고 **오늘 인덱스가 없습니다.** 같은 판단을 `chain_bindings.identity_column`이 이미 하고 있었고, 인덱스만 그걸 안 읽고 있었습니다 |
| **production_plan**<br>10행 | 서버 술어 **없음**. 그리드 필터·값 제안만. | `(plan_id)` — `main.apply_column_filters` · `value_suggest` | ✅ `business_key`. 10행 |
| **inventory_master**<br>15행 | 서버 술어 **없음**. 그리드 필터·값 제안만. | `(part_no)` — 〃 | ✅ `business_key`. 15행 |

---

## 2. 인덱스를 «안» 붙이는 것 — 그리고 그 이유

근거 없이 빠지면 다음 사람이 「누락」으로 읽고 붙입니다. 안 붙이는 것도 결정입니다.

| 안 붙이는 것 | 이유 |
|---|---|
| **사용자 컬럼 일반**(키가 아닌 컬럼 전부) | 그리드 컬럼 필터(`main.apply_column_filters`)는 **아무 선언 컬럼에나** 술어를 냅니다. 그것을 근거로 삼으면 **컬럼 수만큼** 인덱스를 만들게 되고, 비용은 §4의 행당 비용 × 컬럼 수입니다. `bonding_log`는 사용자 컬럼이 16개입니다. 필터는 인덱스의 근거가 아니라 **상한(LIMIT)과 커서**의 근거입니다 |
| **`business_key` 컬럼**(복합 키를 선언한 표에서) | `core_cell_key`·`dt_cell_key`·`cell_key`·`bond_cell_key`·`pkg_id`·`split_key`·`map_pk`·`void_uid`·`delam_uid`·`wid_key`·`event_id` — 이 중 **어느 것에도 WHERE가 없습니다**(전수 확인 2026-08-14). 신원 조회는 프레임워크의 `business_key_val`로 갑니다 |
| **UNIQUE 제약으로의 승격** | `idx_<표>_declared_key`는 **맵 신원**이지 행 신원이 아닙니다. `core_wafer_map`의 `(core_lot, core_slot)`은 맵 한 장에 수백 셀이 공유합니다. UNIQUE로 만들면 **두 번째 셀부터 거절**됩니다 |
| **커버링 확장**(`INCLUDE`, 정렬 컬럼 추가) | 아래 §2.1이 이미 재 봤습니다: `(core_lot, core_slot, core_y, core_x, row_id) INCLUDE (c_bn)`은 셀 읽기를 0.082 ms → **0.110 ms로 느리게** 했고 `GROUP BY`를 HashAgg로 되돌렸습니다. 인제션 대상에 컬럼 여섯 폭의 쓰기 증폭을 사고 얻은 것이 없습니다 |
| **부분 인덱스**(그래프 플래그) | 아래 §3의 「은퇴 안 함」 참조 — 맞는 방향이지만 **이 라운드의 근거는 「아무도 안 읽는다」**이고 그래프 플래그는 읽힙니다. 다른 주장은 다른 라운드에서 |

### 2.1 선언 키 인덱스가 «읽기»에 얼마인가 — 보존된 실측

아래는 `4ed34a9`가 `core_wafer_map`에 손으로 인덱스를 걸며 잰 수입니다. 그 마이그레이션 파일은
이번 라운드에서 은퇴했고(→ `server/migrations/add_core_wafer_map_key_index.RETIRED.md`), **측정은
지나간 사건이라 낡지 않으므로** 여기로 옮겨 보존합니다. `assy_qa`, 24,200행 / 200맵, 각 계획 전
`ANALYZE`.

| 문장 | 인덱스 없음 | `(core_lot, core_slot)` | 계획 변화 |
|---|---|---|---|
| 셀 읽기 `LIMIT 2` (맵당 1회) | 3.615 ms | **0.082 ms** | Seq Scan → Index Scan |
| `COUNT(*)` 키 하나 (맵당 1회) | 3.727 ms | **0.050 ms** | 〃 |
| `GROUP BY` 키 (요청당 1회) | 7.899 ms | **4.782 ms** | HashAgg → GroupAgg |
| `GET /api/maps/alignment/references`, 200맵 | 1.128 s | **0.332 s** | — |

**맵당 문장이 중요한 이유**: 그 둘은 **후보 하나마다** 돌므로 비용이 `후보 수 × 표 행수`이고 양쪽에서
자랍니다. `GROUP BY`는 계획이 무엇이든 문장 하나입니다.

**부정 결과도 여기 남깁니다** — 커버링 확장 `(core_lot, core_slot, core_y, core_x, row_id)
INCLUDE (c_bn)`은 셀 읽기를 **0.110 ms로 느리게** 했고(제거한 정렬이 ~121행짜리 top-N heapsort라
비용이 0에 가깝습니다) `GROUP BY`를 HashAgg로 되돌렸으며, 엔드투엔드는 0.329 s 대 0.332 s로
실행 간 편차 안이었습니다. ⚠️ **맵당 셀 수가 자릿수로 커지면 균형이 바뀝니다** — 그때 다시 재야 할
수는 **맵당 행 수**이고 오늘 ~121입니다.

---

## 3. 이 라운드가 은퇴시키는 것 — 「같은 맹목의 반대면」

간극의 절반은 **읽는 술어에 인덱스가 없는 것**이었습니다. 나머지 절반은 **아무도 안 읽는 컬럼에
매 insert마다 값을 치르는 것**이고, 둘은 같은 결함입니다 — **아무도 라이브 술어에서 다시 유도해 본 적
없는 고정 목록.**

| 은퇴 대상 | 측정치 (2026-08-14, 두 개발 사본) | 왜 |
|---|---|---|
| **`ix_<표>_created_at`** | 36개 (표, DB) 쌍 중 **35개가 스캔 0**. 유일한 예외는 `assy_qa`의 `ix_production_plan_created_at` = **1**(10행 표, ~24시간) | 동적 테이블의 `created_at`에 **술어가 코드 어디에도 없습니다.** `created_at <` 검색은 전부 `DatabaseOutbox`로 갑니다. 매 insert마다 유지되고 읽는 곳이 0 |
| **`idx_<표>_bk`** = `(business_key_val, row_id)` | **양쪽 DB, 등록된 모든 표에서 스캔 0** | 옆의 단일 컬럼 `ix_<표>_business_key_val`이 신원 조회를 전부 가져갑니다. 신원 조회(`crud.get_row_by_business_key`·`_get_or_create_row`·`_find_business_key_conflict`)는 **행을 SELECT**하지 id만 뽑지 않으므로 `row_id` 접미가 index-only scan을 사 주지 못합니다 |

**은퇴 방식** — `server/migrations/align_indexes_to_declarations.py`. 기본이 **읽기 전용**이고
`--apply`로만 씁니다. 두 가지가 **다르게 게이트**됩니다:

- `idx_<표>_bk`는 **구조적으로** — 같은 표에 `business_key_val`로 시작하는 다른 유효 btree가 살아
  있을 때만 지웁니다. 이 증명은 `pg_index`에 있고 통계 카운터 유실과 무관합니다.
- `ix_<표>_created_at`은 **카운터로** — 그런데 카운터의 0은 **이유가 아니라 거절 게이트**입니다.
  그 표의 **다른** 인덱스들도 전부 0이면(신선 복원·통계 리셋) **거절합니다** — 그 0은 증거의 부재이지
  부재의 증거가 아닙니다. 실제로 `assy_manager` 4개 표, `assy_qa` 7개가 이 게이트에서 거절됐습니다.

**은퇴 안 하는 것**, 근거와 함께:

- `ix_<표>_updated_at` — `idx_<표>_updated`(`updated_at, row_id`)에 **구조적으로 포함**되지만 스캔이
  0이 아닙니다(`dt_map` 4, `assy_qa`의 `dt_log` 2 …). **「아무도 안 읽는다」와 「옆의 것이 대신할 수
  있다」는 다른 주장**이고 이 라운드는 앞엣것만 집행합니다.
- `ix_<표>_is_graph_synced` / `ix_<표>_needs_graph_rollback` — 읽힙니다(`assy_qa`의 `dt_inventory`
  354회). ⚠️ 다만 **boolean 2값**이라 부분 인덱스가 맞고, 읽는 함수가 `graph_sync_worker`에서
  **`[DEPRECATED — C-7]`** 표시입니다. 다음 라운드 후보이지 이번 근거로는 못 지웁니다.
- `ix_<표>_business_key_val` — **2026-08-14 기준 `assy_manager` 18표 전부에 `uq_bk_<표>`(UNIQUE, 같은
  단일 컬럼)가 존재**하므로 구조적으로 완전 중복입니다. 그런데 지우면 **갓 만든 DB가 마이그레이션
  전까지 업무 키 인덱스를 잃습니다** — `models.py`가 자기 주석에서 이미 경고하는 그 창입니다.
  보고만 하고 안 건드립니다.
- `ix_<표>_row_id`(12개 표에 남은 PK 사본) — 선언은 이미 은퇴([D3])했고 **물리 잔재의 정본 소유자가
  따로 있습니다**: `add_business_key_unique_index.py --drop-redundant`. 여기서 또 지우면 한 계급에
  기전이 둘이 됩니다.

---

## 4. 비용 — 실측

**측정 방법**: `assy_qa`의 프로브 테이블, 40,546행 INSERT, 5라운드 교대, `EXPLAIN (ANALYZE, WAL)`로
**문장 단위 WAL**(박스의 동시 워크로드가 오염시킬 수 없습니다 — `pg_current_wal_lsn()` 차분과 다른
점입니다). 프로브는 전부 드롭했습니다.

| 형태 | 구성 | 인덱스 수 | WAL B/행 | insert ms(중앙값) | 인덱스 저장 |
|---|---|---|---|---|---|
| `bonding_log`(2칸 키) | 오늘 | 8 | 741.9 | 1,826 | 8.30 MB |
| | **제안**(−`created_at` −`bk` +선언키) | **7** | **661.0** | **1,611** | **6.46 MB** |
| | 참고: 오늘 + 선언키(은퇴 없이) | 9 | 820.8 | 1,942 | 8.92 MB |
| `inspection_run`(6칸 키) | 오늘 | 8 | 744.4 | 1,837 | 8.30 MB |
| | **제안** | **7** | **715.8** | **1,732** | 9.03 MB |
| | 참고: 오늘 + 선언키 | 9 | 875.6 | 2,239 | 11.49 MB |

**읽는 법 — 이 표의 핵심은 부호입니다.**

- 선언 키 인덱스 **하나를 더하는** 값은 2칸 키에서 **+78.9 B/행**, 6칸 키에서 **+131.2 B/행**입니다.
  (F5 조사가 다른 계기 — `pg_current_wal_lsn()` 차분 — 로 같은 형태를 재서 **+74.8 B/행**을 얻었습니다.
  **계기 둘이 5% 안에서 일치**하므로 이 수는 계기의 산물이 아닙니다.)
- 그런데 **은퇴 둘이 그것보다 큽니다.** 이 라운드 전체의 순변화는
  **`bonding_log` 형태 −80.9 B/행 (−10.9% WAL, −11.8% 시간)**,
  **config에서 가장 넓은 키인 `inspection_run` 형태에서도 −28.6 B/행 (−3.8%, −5.7%)**.
  🔴 **가장 비싼 경우에도 쓰기 비용이 «줄어듭니다».**
- WAL 표본은 반복 실행에서 **바이트가 동일**했습니다(제안 `bonding_log` 5회 전부
  26,801,713 B). 시간은 겹치는 분포이므로 **판정 가능한 수는 WAL입니다.**
- ⚠️ 저장 크기는 방향이 갈립니다 — 2칸 키는 −22%, 6칸 키는 **+8.8%**. `pg_relation_size`로 인덱스를
  재면 쓰기 비용을 잘못 읽습니다(btree 중복 제거가 디스크에서만 압축합니다).

### 4.1 이 비용을 못 감당하는 표

인제션 대상에서는 인덱스 하나가 **인제션되는 모든 행에서** 값을 치르고, 락은 곧 멈춘 레인입니다.

- 🔴 **최고 회전 — `replace_map`이 맵을 통째로 지우고 다시 넣는 표**: `dt_map` · `dt_core_view` ·
  `core_usage_map`. 손댄 맵의 모든 행마다 모든 인덱스가 다시 써집니다.
- 🔴 **파서 대상**: `void_obs` · `delam_obs` · `inspection_run` · `core_wafer_map` · `bonding_log` ·
  `dt_log` · `lot_event` · `bonding_map`.
- 🟡 **체인 대상**: `dt_inventory` · `inventory_master` · `wafer_map_metadata`.
- ⚪ **읽기 위주 — 인덱스가 거의 공짜**: `valid_die_ref` · `map_split_registry` · `production_plan` ·
  `wafer_id_status`.

**그래서 결정은 이렇습니다**: 표별로 켜고 끄지 **않습니다.** 순비용이 음수이므로 켜고 끌 것이
없고, 표별 예외를 파는 순간 규칙이 아니라 다시 목록이 됩니다. 그리고 **테이블이 만들어지는 시점에는
그 표가 얼마나 커질지 아무도 모릅니다** — 선언은 그때 이미 있습니다.

---

## 5. 자동화가 못 하는 것 — 손으로 남는 인덱스

이 목록이 이 문서에서 가장 오래 쓸모 있을 부분입니다. **선언에서 나올 수 없는 이유**가 각각 다릅니다.

| 인덱스 | 사는 곳 | 왜 선언에서 못 나오는가 |
|---|---|---|
| `idx_bonding_log_base_position` — `(base_id, bx, by, row_id) INCLUDE (stack_height)` | `add_bonding_base_join_index.sql` | **패키지 신원**은 이 표의 맵 키도 업무 키도 아닙니다. 게다가 `INCLUDE` 페이로드를 적을 어휘가 `table_config`에 없습니다 |
| `idx_inspection_run_layer` — `(base_wafer_id, base_x, base_y, stack_gate, observed_at DESC)` | `add_void_schema_indexes.sql` | 선두가 선언 순서와 다르고, **`DESC` — 정렬 방향**이 필요합니다. 선언은 방향을 말하지 않습니다 |
| `idx_void_obs_area` — `pi() * radius_x * radius_y` | 〃 | **식(expression) 인덱스**. 식은 선언이 아닙니다 |
| `idx_dt_log_dt_job` / `idx_dt_log_eqp_product` / `idx_dt_map_dt_job` | `add_dt_log_trigger_indexes.sql`(**아직 안 돌았음**) | 술어가 **`enrichment_rules.json` 안의 SQL 문자열**에 있습니다. 조인 술어를 적는 선언 어휘가 없습니다 |
| 값 제안용 접두 인덱스 — `lower(col) COLLATE "C"` | `value_suggest.py`가 정의를 소유(빌더는 `server/scripts/`) | **평범한 btree는 C 콜레이션 밖에서 `LIKE 'prefix%'`를 못 씁니다.** 필요한 것은 정렬이 바이트 순서인 **식 + 콜레이션** 인덱스이고, 둘 다 선언 어휘 밖입니다. 🔴 그래서 `idx_bonding_map_declared_key`가 `base`에 붙어도 **값 제안은 그 인덱스를 쓰지 못합니다** |
| `(event_time, business_key_val)` on `lot_event` | 아직 없음 | 백필의 키셋 커서는 **`ledger_config.json`**이 정합니다. `table_config`가 아닙니다 |

**규율(F3 준용)**: 위 표에 없는 인덱스를 손으로 만들 때는 **`__reason`에 해당하는 근거**를 파일
헤더에 적고 이 표에 행을 추가하십시오. **이유 없는 인덱스 선언은 금지**입니다.

---

## 6. 남은 잔재 — 정직하게

### 6.1 이름이 아직 수렴하지 않았다

`assy_manager`에는 규칙이 파생하는 것과 **컬럼이 똑같은** 인덱스가 셋 있고, 이름만 사람이 지은 것입니다.

| 실제 이름 | 규칙이 지을 이름 | 만든 곳 |
|---|---|---|
| `idx_core_wafer_map_map_key` | `idx_core_wafer_map_declared_key` | `add_core_wafer_map_key_index.sql` — **이번에 은퇴**(→ 같은 자리의 `.RETIRED.md`). 인덱스 자체는 그대로 살아 있습니다 |
| `idx_wafer_map_metadata_target_map` | `idx_wafer_map_metadata_declared_key` | `server/scripts/setup_bonding_plan_indexes.py` |
| `idx_map_split_registry_ref_map` | `idx_map_split_registry_declared_key` | `server/scripts/setup_transfer_plan_indexes.py` |

마이그레이션은 **이름이 아니라 컬럼 목록으로** 멱등이라 이 셋을 「이미 덮여 있음」으로 건너뜁니다
(중복 인덱스를 만들지 않습니다). **이름 통일(`ALTER INDEX … RENAME`, 메타데이터 전용·즉시)은 이
라운드가 하지 않았습니다** — 아래 둘의 소유자가 `server/scripts/`이고 그 레인이 임계 경로에 있어서,
이름만 바꾸면 그 스크립트들이 **다음 실행에서 옛 이름으로 중복을 다시 만듭니다.**

**다음 사람이 할 일(순서 고정)**: ① `setup_bonding_plan_indexes.py`·`setup_transfer_plan_indexes.py`
에서 그 두 선언을 은퇴 → ② `ALTER INDEX … RENAME TO idx_<표>_declared_key` 셋.

### 6.2 갓 만든 DB와 오래된 DB가 다르다 (구조적)

`create_all`은 **이미 있는 테이블에 인덱스를 추가하지 않고** 인덱스를 **절대 지우지 않습니다.**
그래서 빌더 변경은 신규 테이블에만 닿고, 나머지는 마이그레이션이 닿습니다. 이 비대칭이 두 개발 사본의
수동 인덱스 집합을 **교집합 공집합**으로 갈라놓은 바로 그 기전입니다(F5 조사).
**빌더를 고쳤으면 마이그레이션을 돌리기 전까지 아무 DB도 안 바뀐 것입니다.**

### 6.3 런타임 config 리로드는 인덱스를 안 따라간다

`init_dynamic_models`는 이미 등록된 표에 대해 **컬럼 핫스왑만** 합니다. 운영 중에
`map_key_columns`를 바꾸면 **모델의 인덱스 선언은 다음 프로세스 재기동까지 그대로**이고, 물리
인덱스는 마이그레이션 전까지 그대로입니다. 선언을 바꾼 사람이 마이그레이션을 돌려야 합니다.

---

## 7. 관련 문서

- 판정: [process/LEDGER_RULINGS `R-2026-08-14-B`](../process/LEDGER_RULINGS.md)
- 저장 모델·동적 테이블: [architecture/data_model §1.2](./data_model.md)
- 선언 어휘: [guide/CONFIG_GUIDE](../guide/CONFIG_GUIDE.md) · [architecture/SCHEMA_CANON](./SCHEMA_CANON.md)
- 업무 키 UNIQUE(성능이 아니라 무결성): `server/migrations/add_business_key_unique_index.py`
- 배포 절차: [guide/DEPLOY_SETUP](../guide/DEPLOY_SETUP.md)
