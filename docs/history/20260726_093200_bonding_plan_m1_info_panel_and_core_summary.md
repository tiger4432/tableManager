# feat(bonding-plan): M1 — 실험계획 Info 패널 + 역할 바인딩 core-summary API (rect 모드 폐기 포함)

- **일시**: 2026-07-26
- **커밋**: `e6eabe4` (M1 본체 — 서버부+클라부) · `24753d3` (rect 영역 선택 모드 삭제)
- **작업자**: server-pm / client-pm (병행) · QA 변환 감사(`QA_map_transform_logic_audit.md`) 제약 반영
- **보고서**: `agent_workspace/reports/Server_bonding_plan_m1_report.md` · `Client_bonding_plan_m1_report.md`(§0 v2 추록)

## 배경

base + multistack core 구성 계획·검증(잔여 칩 = 총 − defect − EDS − 기사용, 공정 이력 경고로 사고 방지)의 M1(조회 전용) 단계. 실 운영 테이블명이 환경마다 다르므로 **역할 바인딩 config**(`bonding_plan_config.json`)로 역할→실테이블·컬럼을 매핑하고, 계측 좌표계 상이(EDS 180° 회전 등)는 config `align` 선언 + **서버 단독 변환** 원칙을 따른다(이슈 #11 — 클라 이중 구현 금지).

## 변경 내용

### 서버부 (e6eabe4)

- **`server/bonding_plan.py` 신규** — config 로더/검증 + align 정규화·변환 + region 파서/클램프 + 집계 코어 `get_core_summary`.
- **`GET /api/bonding-plan/core-summary?lot=&slot=[&region=]`** (main.py ~2957) — 역할별 집계: 맵 모드 소스는 (lot,slot) 행 카운트(`fail_values` 필터), `used_chips`는 distinct (x,y), `remaining = total − defect − eds_fail − used`(음수 = 백필 과도기 표시), history 50건 + `warnings[]`(result FAIL 매칭), knobs JSON 파싱(실패 시 raw 폴백).
- **align 어댑터** — QA 변환 감사(F1/F2) 반영이 핵심:

```python
# make_align_transform(align, src_grid, dst_grid) — 주입형
# coordinate_transformer.cell_to_physical(순수 인덱스 변환)만 재사용.
# 엔진 마스크/내접 타원 fallback(QA F1·F2 결함 지점)은 이 경로에 참여하지 않음.
# 90/270은 "자기 프레임 치수 = canonical 스왑" 규약(모순 시 ValueError),
# 격자 규격 미해결 시 raw 좌표로 조용히 계산하지 않고 "connected(align_unavailable)" 명시 실패.
```

- fake 원천: `core_defect_map`/`eds_fail_map` 신설(핫리로드 CREATE) + 수집기 2개(eds는 **일부러 180° 회전 좌표**로 기록 — align 실증 데이터), `wafer_process`에 `recipe_id`/`knobs` ALTER. CORE/BASE 맵 프리셋 + `wafer_map_metadata` 코어별 업서트 관례. (lot,slot) 인덱스 5종.
- 라이브 교차검증: region eds_fail 5 = 수동 180° 변환 SQL 5 — align 정합 실증. 테스트 +18(`test_bonding_plan.py`).
- **escalation(승인됨)**: `total_chips`는 지시서 예시(`core_wafer_map`)가 코어당 1행 집계 테이블이라 성립 불가 → `core_defect_map` 풀맵으로 재바인딩(로더는 지시서 형태 그대로 지원 — 실 운영에서 config 교체만).

### 클라부 (e6eabe4 → 24753d3 v2)

- **`client2/src/bonding_plan.js`/`bonding_plan.css` 신규** — map editor 우측 슬라이드 Info 패널(조회 전용): 층 범위 배정 목록(코어 자동완성 = `/graph/nodes/search` 재사용), core-summary 소비(수량 라인·sources 역할 뱃지(missing=미연결)·FAIL 타임라인·knob 칩 확장), knob 비교 뷰(공통 step × knob 표 — 값 상이 셀만 하이라이트 = 조건 이탈), 층 커버리지 스트립 + **경고 3종**(수량 부족/FAIL 이력/조건 이탈), localStorage 초안 자동 보관/복원(`bonding_plan_draft::<base>`). 구버전 서버 graceful(404 → 미지원 안내 + 편집 지속).
- `map_editor.js`: `loadSelectedPreset` → `applyPresetObject` 추출 리팩터 + `initBondingPlan()` 배선.

### rect 영역 선택 모드 삭제 (24753d3 — 사용자 지시)

M2에서 **"값 페인팅"이 영역 지정의 단일 정본**으로 확정되어 v1에서 구현했던 rect 영역 선택 모드(맵 에디터 rect 드래그 엔진·플로팅 바·미니 썸네일·행 region 필드)를 **전면 폐기**했다. 현재 코드에 존재하지 않는다.
- 유지: `applyPresetObject` 리팩터, Info 패널 나머지 전부, **서버 core-summary의 `region` 파라미터**(M2 cells 모드용 존치 — 클라만 미사용화).
- 초안 하위호환: 구 초안의 `core_region`/`base_region`은 로드 시 읽되 버림(재직렬화에서 자연 탈락 — 검증 완료).

## 아키텍처 영향

- 경계 계약 추가: REST 1종(`GET /api/bonding-plan/core-summary`). WS·셀 계약 무변경.
- 이슈 #11(좌표 변환 드리프트)의 첫 실소비자였던 align 경로가 결함 지점(엔진 fallback)을 **구조적으로 우회** — transformer 자체의 F1/F2 수정은 잔여 과제로 남음.
- 테스트 275 passed(+18) / 1 allowed fail(#4 기존).

## 다음 단계 (M2 — Universal Transfer Plan으로 재정의됨)

DT/Tape 계층 편입·전사 프리미티브·DOE 관리 단위는 별도 설계 기록([20260726_093300](./20260726_093300_dt_tape_layer_universal_transfer_plan_design.md)) 참조. by_eqp 장비별 align 적용, align 보정 모드, 관리 테이블 2종 + 온톨로지 승격은 M2.
