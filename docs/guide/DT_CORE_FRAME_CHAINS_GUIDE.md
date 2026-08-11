# DT/Core frame 체인 운영 가이드

> **대상:** 공정·설정 운영자 | **최종 검증:** 2026-08-11 (§1-bis 잡 컬럼 이름 신설 — 매퍼에 `dt_job` 기본값이 없어졌다)

이 문서는 DT와 Core frame 파생 체인을 설정·운영하는 방법을 설명한다. 데이터
소유권과 전체 구조는 [DT/Core frame 체인 구조](../architecture/DT_CORE_FRAME_CHAINS.md)를
먼저 읽는다.

## 1. 설정 순서

다음 순서를 지켜야 워커가 이미 존재하는 선언만 참조한다.

1. `table_config.json`에 `dt_inventory`, `dt_map`, `core_wafer_map`,
   `core_usage_map`과 각각의 맵 키·파생 컬럼을 선언한다.
2. `maps.json` / `map_overlay_config.json`에 DT 유효다이맵과 물리 Core
   기준맵을 등록한다. Core 기준맵에는 결과 `core_frame.valid_die_ref`로
   복사할 유효다이 메타가 있어야 한다.
3. `chain_rules.json`에 DT metadata/inventory/map 규칙과
   `dt_log_to_primary_core_frame`을 설정한다.
4. 원본이 lot/slot만 주는 경우 `core_wafer`를 확정하는 enrichment를 켠다.
   `core_wafer`가 없으면 usage map은 의도적으로 생성하지 않는다.
5. 테이블 또는 체인 선언을 바꿨다면 전체 프로세스를 재시작한다.

추적되는 `server/config/*.json.sample`과
`docs/guide/config_reference/*.json`은 실행 정본이 아니라 스냅샷이다.
활성 설정을 바꾸면 같은 변경에서 활성 JSON을 두 샘플 위치에 그대로 복사한다.
(격리 개발 환경을 쓴다면 `dev_env/config/`가 **네 번째 사본**이다 — 이미
어긋나 있으므로 옮길 때 확인한다.)

### 1-bis. 잡 컬럼 이름 (2026-08-11)

🔴 **매퍼 코드에는 잡 컬럼 이름이 없다.** `dt_job`이라는 기본값도 없다. 각 테이블의
잡 컬럼 이름은 그 테이블의 `table_config.json` 선언에서 유도된다 —
**`map_key_columns`가 한 컬럼**이면 그것, 없으면 **`composite_key_source`가 없는
테이블의 한 컬럼짜리 `business_key`**. 어느 쪽으로도 못 풀면 체인은 **이름을 대고
거절**한다(어느 룰·어느 키·어느 테이블인지 메시지에 나온다).

- **컬럼 이름을 바꾼다면** `table_config.json`의 그 테이블 선언만 고치면 네 체인이
  모두 따라온다. 매퍼 파일은 건드리지 않는다.
- **테이블마다 철자가 다를 수 있다.** `dt_log`·`dt_map`·`dt_inventory`는 서로 다른
  이름을 가질 수 있고, 이제 코드가 그것을 표현한다.
- **유도를 덮어쓰려면** 해당 `chain_rules.json` 룰에 `trigger_job_column` ·
  `source_job_column` · `target_job_column` · `inventory_job_column` 중 필요한 것을
  선언한다. 기존 `job_column` · `reference_job_column` ·
  `derivation_source_column`도 그대로 덮어쓰기 키로 동작한다.
- ⚠️ **`server/mappers/*.py`는 git 밖의 운영자 자산이다.** `.sample`만 배포된다.
  샘플을 활성 매퍼 위에 통째로 덮어쓰면 운영자가 직접 넣은 수정이 조용히 되돌아간다.
  §4의 대응표를 먼저 본다.

## 2. Core 자동 frame 규칙

`dt_log_to_primary_core_frame`에서 중요한 항목은 다음과 같다.

| 설정 | 의미 |
|---|---|
| `primary_selector.group_by` | 사용할 Core 후보를 식별하는 필드 |
| `primary_selector.order_by` | 후보를 하나로 고르는 결정 순서. 일반적으로 `dt_index` 우선 |
| `reference.table` / `map_id_template` | 채점할 물리 Core 기준맵 |
| `columns.x`, `columns.y`, `columns.value` | 원본 Core 좌표와 bin (`c_wx`, `c_wy`, `c_bn`) |
| `metrics` | 허용하는 증거 방식 (`values`, `occupancy`) |
| `thresholds` | 채점 결과를 확정하는 품질 게이트 |
| `source_filters` | 원본 `dt_log`를 읽을 때 적용할 Core 식별 조건 |

DT job이 여러 Core wafer를 사용할 수 있어도, 작업 중 좌표 frame 자체가 바뀌지는
않으므로 자동 체인은 대표 Core 하나만 맞춘다. 모든 사용 영역을 보려면 frame을
여러 번 쓰지 말고 `core_usage_map`을 조회한다.

## 3. 인제션 결과 확인

DT job이 들어온 뒤 아래 순서로 확인한다.

1. `wafer_map_metadata`에 `target_table=dt_log`, `map_id=dt_job`인 DT 메타가
   있는지 확인한다.
2. `dt_inventory`에 `dt_frame`, 여섯 `dt_*` 수식 필드가 있는지 확인한다.
   물리 Core 매칭이 성공했다면 `core_frame`과 여섯 `core_*` 수식 필드도 있어야
   한다.
3. `dt_map`에 해당 job의 표준 좌표 셀만 있고, 메타가 `front`, 회전 `0`, 시작
   `(1,1)`, 원본과 같은 `valid_die_ref`인지 확인한다.
4. `core_wafer` enrichment가 끝난 뒤 `core_usage_map`에 해당 wafer의 표준 Core
   좌표, `used_count`, `used_dt_jobs`가 있는지 확인한다.

`core_usage_map`이 생성될 때는 같은 `core_wafer`를 `map_id`로 하여
`wafer_map_metadata`도 함께 갱신한다. 이 메타의 좌표 규약은 항상
`front`, 회전 `0`, 시작 `(1,1)`이다. 격자·물리 치수와 `valid_die_ref`만
대표 `core_frame`에서 이어받는다.

과거 데이터는 Admin에서 체인 소유 규칙을 재생한다. 반드시 좁은 job/wafer 범위를
선택하고 미리보기/건수 확인을 먼저 실행한다. frame이 없는데 맵 규칙만 재생해도
복구되지 않는다. DT는 alignment → inventory → standard DT map 순서, Core는
alignment → inventory → core usage map 순서로 재생한다.

## 4. 문제 대응

| 증상 | 확인 및 조치 |
|---|---|
| `dt_map`이 없음 | `dt_inventory.dt_frame`과 여섯 DT 수식이 있는지 확인하고 `dt_inventory_to_standard_dt_map`을 재생한다. |
| Core frame이 없음 | 원본에 설정된 Core 식별값이 있는지, 해당 `core_wafer_map`이 있는지 확인한 뒤 후보 채점 결과를 본다. 문턱부터 내리지 않는다. |
| `core_usage_map`이 없음 | `core_wafer`가 필수다. 기존 attribution enrichment를 고친 뒤 `dt_log_to_core_usage_map`을 재생한다. |
| 한 wafer의 usage 셀이 둘로 갈라짐 | lot/slot을 map key에 넣지 않는다. 하나의 `core_wafer` 값으로 정규화·enrich한다. |
| Core frame의 `valid_die_ref`가 없음 | 선택된 `core_wafer_map` 메타에 유효다이 참조를 등록한다. 매퍼는 선언된 참조만 복사한다. |
| `unexpected keyword argument 'alignment_thresholds'` | 워커마다 코드/설정 버전이 섞인 상태다. 전체 프로세스를 재시작한 뒤 재생한다. |
| 정렬기가 winner를 못 고름 | 원본 좌표, 기준맵 셀, metric, source filter를 검토한다. 애매함을 margin 하향으로 숨기지 않는다. |
| **체인이 에러 없이 아무것도 안 씀** (2026-08-11) | 잡 컬럼 이름 불일치의 옛 증상이다. 로그에서 `[Schema] Column '<컬럼>' ... was DROPPED from the update`를 찾는다 — 나오면 그 테이블의 `table_config.json` 선언과 실제 컬럼 이름이 어긋난 것이다. 이제 이름을 못 풀면 체인이 `ColumnBindingRefused`로 **거절**하므로, 조용한 성공 대신 로그에 룰·키·테이블이 찍힌다. |
| **`ColumnBindingRefused`** | 메시지가 지목하는 테이블의 `table_config.json`에 한 컬럼짜리 `map_key_columns`(또는 `composite_key_source` 없는 한 컬럼짜리 `business_key`)를 선언하거나, 그 룰에 해당 `*_job_column` 키를 직접 선언한다. 매퍼 코드는 고치지 않는다. |

## 5. 안전한 변경 원칙

- DT/Core frame을 변경한 뒤에는 하위 replace-map 소유 체인을 재생한다. 해당 맵
  범위는 append되지 않고 새 결과로 교체된다.
- Core 기준맵의 유효다이맵을 바꾸면 채점 근거도 바뀐다. 먼저 Core frame을
  재평가하고 usage map을 재생한다.
- `dt_core_view`는 Map Editor의 시각 검토용이다. 자동 쓰기 경로로 사용하지 않는다.
- `frame_confirmation`은 폐기했다. job별 통합 frame 정본은
  `dt_inventory`다.
