# 완료 보고: 본딩 실험계획 M1 — 서버부 (fake 원천 + 역할 바인딩 config + 집계 API)

> 지시서: `agent_workspace/tasks/Server_bonding_plan_m1_task.md` + 총괄 보강 지시 3건
> (①맵 메타/프리셋 필수, ②align canonical frame 설계 대체 지시, ③align 스키마 호환성 확정)
> + QA 감사 반영 지시(`QA_map_transform_logic_audit.md` F1/F2 제약).
> 작업 위치: 메인 트리. **커밋 없음. 재기동 없음.** P1 heavy 레인 파일 일절 미접촉.

## 1. 요약 (판정: 완료 — 단 §5 escalation 2건 총괄 확인 필요)

| 항목 | 결과 |
|---|---|
| A. fake 원천 | `core_defect_map`/`eds_fail_map` 신설(핫리로드 CREATE + 물리 확인), 수집기 2개 신설, `wafer_process`에 `recipe_id`/`knobs` ALTER + 생성기 확장 |
| B. 역할 바인딩 config | `server/config/bonding_plan_config.json`(+`.sample` tracked) + 로더/검증 `server/bonding_plan.py` |
| C. 집계 API | `GET /api/bonding-plan/core-summary` (main.py — **재기동 전이라 라우트는 미가동**, 함수 단 라이브 검증 완료) |
| 보강① 메타/프리셋 | wafer_map_metadata 관례 등록(수집기가 코어별 업서트) + CORE/BASE 프리셋 등록 + region 클램프 |
| 보강② align | canonical frame + `align` 블록(로드 단 사상, coordinate_transformer 재사용), eds fake 데이터 180° 회전 실증 |
| 보강③ 호환성 | 단순형/확장형(`default`/`by_eqp`) 수용, 변환 함수 align 외부 주입형, `metro_eqp` 컬럼 포함 |
| QA 감사 반영 | align 경로는 엔진 마스크/타원 fallback **무참여**(순수 인덱스 변환), 90/270 치수 스왑 정합 + 테스트, 규격 불명 시 명시 실패(`align_unavailable`) |
| 테스트 | 기준선 257 passed/1 allowed fail → 최종 **275 passed/1 allowed fail(동일: `test_map_presets_api` #4)** + 신규 18개 전부 통과 |

## 2. 변경 파일

**신규 (git 추적 대상, 미커밋)**
- `server/bonding_plan.py` — config 로더 + align 정규화/변환 + region 파서/클램프 + 집계 코어 `get_core_summary`
- `server/tests/test_bonding_plan.py` — 18 tests (`bdp_test_*` 접두 격리)
- `server/scripts/setup_bonding_plan_indexes.py` — (lot,slot) 복합 인덱스 5종 멱등 셋업 (실행 완료)
- `server/config/bonding_plan_config.json.sample`

**수정 (git 추적, 미커밋)**
- `server/main.py` — 라우트 1개 추가(`get_bonding_plan_core_summary`, map-presets 섹션 뒤 ~L2952, catch-all보다 선등록). **P1 변경분(ingestion_activity 등)과 무충돌 — 순수 추가 편집만.**

**사용자 영역 (gitignored)**
- `server/config/bonding_plan_config.json` (전문 §3)
- `server/config/table_config.json` — `core_defect_map`/`eds_fail_map` 신설 + `wafer_process`에 `recipe_id`,`knobs` 추가 (in-place 재기록으로 config_watcher 발화 → **information_schema로 물리 CREATE/ALTER 확인 완료**)
- `server/config/maps.json` — CORE/BASE 프리셋(라이브 `/api/map-presets` POST로 등록, §4)
- `server/ingestion_workspace/core_defect_map/auto_update/generate_core_defect.py` (신규)
- `server/ingestion_workspace/eds_fail_map/auto_update/generate_eds_fail.py` (신규)
- `server/ingestion_workspace/wafer_process/auto_update/generate_wafer_process.py` (v3 — knobs/recipe 확장)

## 3. 배포 config 전문 (`server/config/bonding_plan_config.json`)

```json
{
  "core_identity": { "compose": ["lot", "slot"] },
  "map_metadata": {
    "table": "wafer_map_metadata",
    "columns": { "target_table": "target_table", "map_id": "map_id", "grid_metadata": "grid_metadata" }
  },
  "sources": {
    "process_history": {
      "table": "wafer_process",
      "columns": { "step": "step", "eqp": "eqp_id", "result": "result", "time": "start_time",
                    "recipe": "recipe_id", "knobs": "knobs", "lot": "lot", "slot": "slot" }
    },
    "defect": {
      "mode": "map", "table": "core_defect_map",
      "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val" },
      "fail_values": ["D"]
    },
    "eds_fail": {
      "mode": "map", "table": "eds_fail_map",
      "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val" },
      "fail_values": ["F"],
      "align": { "default": { "rotation": 180, "flip": "none", "offset": { "x": 0, "y": 0 } }, "by_eqp": {} }
    },
    "used_chips": {
      "table": "bonding_log",
      "columns": { "lot": "core_lot", "slot": "core_slot", "x": "cx", "y": "cy" }
    },
    "total_chips": {
      "mode": "map", "table": "core_defect_map",
      "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y" }
    }
  },
  "warnings": { "result_fail_values": ["FAIL"] }
}
```

## 4. 등록한 맵 메타/프리셋 전문

**프리셋 (maps.json, `/api/map-presets` POST — 편집 UX용)**
```json
"core_std": { "name": "CORE", "phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
              "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0,
              "rotation": 0, "side": "front", "is_custom": true }
"base_std": { "name": "BASE", "phys_wafer_dia": 300.0, "phys_chip_x": 11.0, "phys_chip_y": 13.0,
              "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0,
              "rotation": 0, "side": "front", "is_custom": true }
```
- CORE 규격 선정 근거: bonding_log의 코어 칩 좌표가 `cx,cy ∈ [1,40]`(기존 fake) → 40×40 격자 필수.
  300mm/40칸 = 7.5mm 피치 → chip 7×7mm. in-wafer 유효 칩 = **1,288개/코어**.
- BASE 규격: 기존 bonding_map 메타 지배 관례(chip 11×13, dia 300, margin 3) 승계.

**wafer_map_metadata (수집기가 코어별 업서트 — 관례: `map_pk = <table>_<lot>_<slot>`, `map_id = <lot>_<slot>`, source=custom_script)**
```json
// core_defect_map_* (canonical frame)
{ "grid_cols": 40, "grid_rows": 40, "grid_start_x": 1, "grid_start_y": 1, "grid_y_invert": false,
  "rotation": 0, "side": "front", "phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
  "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3.0 }
// eds_fail_map_* (자기 좌표계 — 180° 회전 계측; align이 프레임 간 다리)
{ ...동일..., "rotation": 180 }
```
- region 교차는 canonical 메타 치수로 rect **클램프**(범위 밖 절단, 완전 밖 rect 제거) 후 계산.
- 라이브 등록 확인: `core_defect_map_LOT-D_05`, `core_defect_map_LOT-E_02`, `eds_fail_map_LOT-C_06`, `eds_fail_map_LOT-C_13` (수집기 사이클마다 신규 코어분 증가).

## 5. ⚠️ Escalation — 총괄 확인 필요 2건

1. **total_chips 바인딩 이탈(핵심)**: 지시서 §B 예시는 `total_chips.table = "core_wafer_map"`이나,
   실측상 core_wafer_map은 **enrichment 파생 집계 테이블(코어당 1행**, chip_count = bonding_log 행수 집계)이라
   맵 모드 행 카운트 시 total=1이 되어 계약 예시(total 249)·클라 표시("잔여 = 총−…")가 성립 불가.
   또한 좌표가 없어 region 교차도 불가. → 배포 config는 **core_defect_map(전체 칩 풀맵 — val 'P'/'D')을
   total 원천으로 재바인딩**했다(같은 테이블에서 total=전행, defect=fail행). 로더는 지시서 §B 형태를
   그대로 지원하므로 실 운영에서 칩 레벨 total 테이블로 재바인딩만 하면 된다.
   *지시서의 "실 운영 테이블명 상이 대응" 취지로 config 값 차원의 조정이며 로더/계약 이탈은 아님 — 승인 요망.*
2. **config 스키마 optional 확장**: §B에 없는 `map_metadata` 블록(격자 규격 조회 바인딩 — QA 감사 §3
   "align 규격은 프리셋이 아니라 grid meta" 이행), `used_chips`/`total_chips`의 `x`/`y` 좌표 바인딩
   (region 교차용)을 추가했다. 모두 optional — 없으면 해당 기능만 강등(§6 규칙 참조).

## 6. 집계 의미론 (구현 규칙 — 클라/문서 공유용)

- 맵 모드 소스: (lot,slot) 행 카운트, `fail_values` 있으면 val 필터. **align은 카운트에 불변** —
  region 교차 시에만 좌표 페치(내부 연산, 응답 미포함, 하드캡 100k) 후 canonical 사상.
- `used_chips`: x/y 바인딩 시 **distinct (x,y)** 칩 수(중복 본딩 로그 이중 가산 방지), 미바인딩 시 행 수.
- region: 좌표 미바인딩 소스는 0. align 선언 + 격자 규격 미해결 시 raw 좌표로 조용히 계산하지 않고
  `"connected(align_unavailable)"` + region 0 (QA F2 취지). sources 마커: `"connected(aligned:180)"` 등.
- align 어댑터: `coordinate_transformer.cell_to_physical`만 재사용(순수 인덱스 변환) — 엔진 마스크/
  내접 타원 fallback(`is_inside_wafer`/bbox, QA F1·F2 결함 지점)은 **이 경로에 참여하지 않음**.
  90/270은 자기 프레임 치수=canonical 스왑 규약으로 정합(비정방 격자 테스트 포함), canonical 치수
  선언과 모순되면 ValueError(명시 실패). offset은 사상 후 가산(phys 오프셋 불변 관례와 별개 축).
- history: time desc 50건 → 오름차순 반환. warnings는 이 50건 윈도 내 `result_fail_values` 매칭.
- knobs: JSON 파싱 실패 시 raw 문자열 폴백(에러 아님).
- `remaining = total − defect − eds_fail − used` (missing=0). **음수 가능**: (a) 백필 과도기(총칩 맵
  미도착 코어), (b) 기존 bonding fake의 cx,cy가 마스크 밖 좌표 포함 — 계약 공식이라 유지, 클라는
  음수를 "미확인/과도기"로 표시 권장.

## 7. fake 수집기 설계

- `generate_core_defect.py` (*/3 cron): universe = `core_wafer_map` distinct 조합 추종, 미커버 코어
  사이클당 최대 2개 풀맵 백필(코어당 1,288행, `MAX_ROWS_PER_CYCLE=2900` 상한). defect율 3~8%,
  crc32 결정 해시로 "불량 과다 코어"(18~28%) 고정 선정. 전량 커버 후 생성 0(신규 조합 발생 시 재개).
- `generate_eds_fail.py`: 동일 구조, **일부러 180° 회전 좌표로 기록**(`stored = 41 − canonical`) +
  메타 rotation 180 등록 → align 실증 데이터. fail율 2~10%(과다 코어 15~25%), `metro_eqp`
  METRO-A/B 코어당 결정적(M2 장비별 align 시연 기반).
- 둘 다 마스크는 `PhysicalWaferEngine.is_cell_inside_wafer` 재사용(임포트 실패 시 동일 4-코너 산식
  폴백), 메타 업서트는 `/tables/wafer_map_metadata/data/updates` API 경유(레이어링 보존), stderr만 사용
  (subprocess 폴백 모드 CSV 오염 방지), 스케줄러 exec 분리 네임스페이스 함정 회피(평문 루프).
- `generate_wafer_process.py` v3: step별 knob 기본 세트(ETCH/CMP/DEPO/PHOTO/CLEAN/IMPLANT/ANNEAL) +
  crc32 결정 해시 "조건 이탈 코어"(10%)만 한 knob 변조(×1.25 또는 "-X"), `recipe_id = R-<step>-01`.

## 8. 검증 증거

1. **기준선 선측정**: `257 passed, 1 failed` — 실패는 `test_map_presets_api`(기허용 #4).
2. **물리 DDL**: information_schema 실측 — `core_defect_map`(13 cols), `eds_fail_map`(14 cols, metro_eqp 포함) CREATE, `wafer_process`에 `knobs`,`recipe_id` ALTER 반영. (table_config in-place 재기록 → config_watcher 발화 경로)
3. **인덱스**: `idx_core_defect_map_lot_slot` 외 4종 생성 완료(스크립트 출력 [ok] 5건).
4. **신규 테스트**: `test_bonding_plan.py` 18 passed — 집계 정확성/region 합집합·클램프·400/align 180
   네거티브 대조군·90 비정방·flip·offset·dims 모순 ValueError·align_unavailable/missing 부분 가동/
   빈 config/미존재 조합/history 50건 캡·오름차순/warnings/knobs 폴백/파서·클램프 단위.
5. **최종 전수**: `275 passed, 1 failed` — 실패는 기준선과 동일한 `test_map_presets_api`(#4).
   실패 원인은 기본 프리셋 `std_300_12x13` 부재로 **본 작업과 무관 확인**(신규 core_std/base_std는
   응답에 정상 포함되며 assert 대상 아님). "고쳐졌다" 판단 없음.
6. **라이브 시드**: run-now 트리거 → 각 테이블 2,576행(2코어×1,288칩) 인제션 + 메타 4건 등록 확인.
   wafer_process 신규 행에 recipe_id/knobs 유입 확인.
7. **라이브 함수 단 교차검증** (`get_core_summary`를 실 PG에 직접 호출, 원시 SQL 대조):
   - LOT-D/05: total 1288 = SQL, defect 70 = SQL, used 16 = SQL(distinct), remaining 1202 공식 일치.
   - LOT-C/06 + region(1..20,1..20): region eds_fail **5 = 수동 180° 변환 SQL(저장좌표 21..40 BETWEEN) 5** — align 라이브 실증.
   - 미존재 조합: 전 역할 connected + total 0.

## 9. 라이브 검증 한계 (재기동 후 확인 항목)

신설 API 라우트는 웹서버 프로세스 재기동이 필요하다(핫리로드 범위 밖 — 지시서 예외 인정 항목).
현재 라이브 :8080에는 **라우트 미존재 → 정적 catch-all이 HTML 200을 반환**하므로(교훈 파일 기지 함정)
클라이언트는 "응답이 JSON인지" 가드 필요(클라 지시서의 구버전 graceful 규칙과 합치).
재기동 후 확인 체크리스트:
1. `GET /api/bonding-plan/core-summary?lot=LOT-D&slot=05` → §8-7과 동일 수치의 JSON.
2. region 파라미터(URL 인코딩) → `region_chips` 포함 + 잘못된 region 400.
3. map editor Info 창(클라 병렬 산출물)과 통합 스모크.

## 10. 미해결·후속 (M2 후보 포함)

- Escalation §5 2건 (total_chips 재바인딩 승인 / config optional 확장 승인).
- 백필 완주: 수집기가 사이클당 2코어씩 우주(~65코어)를 채우는 중(~1.5h) — 그 동안 일부 코어는
  remaining 음수/eds 0 과도기. 완주 후 안정.
- 기존 `generate_bonding.py`의 cx,cy가 마스크 밖 좌표(격자 모서리)를 포함할 수 있음 — used가 total에
  없는 칩을 카운트하는 미세 왜곡. 수정하려면 bonding fake에 마스크 적용(타 데모 공유 데이터라 미접촉).
- by_eqp 장비별 align 적용, align 보정 모드(시험 align 오버레이 + config 원자 저장) — M2.
  `make_align_transform(align, src_grid, dst_grid)`가 주입형이라 그대로 재사용 가능.
- history 앵커 문서/CODE_MAP 갱신은 지시서 금지(문서 총괄 일괄) — §11 초안 참조.

## 11. 히스토리 초안 (총괄 통합 시 사용)

> feat(bonding-plan): M1 서버부 — 역할 바인딩 config(`bonding_plan_config.json`) + `GET /api/bonding-plan/core-summary` 집계 API(`server/bonding_plan.py`) + fake 원천 2종(core_defect_map/eds_fail_map 핫리로드 온보딩, 수집기 2개 — eds는 180° 회전 좌표로 align 실증) + wafer_process recipe_id/knobs 확장 + CORE/BASE 맵 프리셋·wafer_map_metadata 관례 등록 + (lot,slot) 인덱스 5종. align은 coordinate_transformer 순수 인덱스 변환 재사용(QA F1/F2 반영: 엔진 fallback 무참여, 90/270 치수 스왑, 규격 불명 시 align_unavailable 명시 실패). 테스트 275 passed(+18)/1 allowed fail(#4). API 라우트는 재기동 대기.

## 12. 교훈 제안 (server-pm.md 반영 후보)

1. **함정**: auto_update 수집기(`GenericScriptRunnerCollector`)의 subprocess 폴백 모드는 stdout 전체를
   CSV로 캡처한다 — 수집기 스크립트 안의 `print()` 한 줄이 데이터 파일을 오염시킨다.
   **올바른 방법**: 수집기 진단 출력은 반드시 `sys.stderr`로.
2. **함정**: `core_wafer_map`은 이름과 달리 칩 레벨 맵이 아니라 enrichment 파생 **코어당 1행 집계
   테이블**(chip_count=bonding_log 행수)이다 — 맵으로 가정한 설계(행 카운트·좌표 교차)가 조용히 틀린다.
   **올바른 방법**: 역할 바인딩 전 대상 테이블의 행 단위(row granularity)를 information_schema+실데이터로 확인.
3. **함정**: `WaferMapCoordinateTransformer`의 시각 계층(`cell_to_visual`/bbox)은 엔진 미장착 시 내접
   타원 fallback으로 실물과 어긋난다(QA F1/F2) — 서버측 좌표 변환에 무심코 visual 계층을 쓰면 오차.
   **올바른 방법**: 서버 집계/정합 용도는 `cell_to_physical`(순수 인덱스 변환)만 쓰고, 90/270은
   "자기 프레임 치수 = canonical 스왑" 규약을 명시 검증.
