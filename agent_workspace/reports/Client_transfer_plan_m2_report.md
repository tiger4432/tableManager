# 보고서: Universal Transfer Plan M2 — 클라이언트부 (DOE 페인팅 + 계획 패널 진화)

- 작성: client-pm (2026-07-26)
- 지시서: `agent_workspace/tasks/Client_transfer_plan_m2_task.md` (+ 총괄 중간 지시 2건: ① by_core 계약·테이블 3종 확정 ② stage 어휘 위반 교정·시드 정리)
- 판정: **완료** — `npm run build` 성공, 실서버 라이브 검증 전 항목 통과, 콘솔 에러 0건. 커밋/재기동 미수행(지시 준수).
- 세션 중도 종료(모델 한도) 후 재개 — 재개 시점에 상태 점검 후 잔여분만 진행.

## 1. 변경 파일 (client2/ 내부만)

| 파일 | 변경 |
|---|---|
| `client2/src/transfer_plan.js` | **신설** (~1,930줄) — 전사 계획 패널 전체(stage·DOE 목록·knob 계획·서버 영속화·페인팅 연동·검증) |
| `client2/src/transfer_plan.css` | **신설** — 패널 + 페인팅 플로팅 바 스타일 (tokens.css 시맨틱 토큰만) |
| `client2/src/map_editor.js` | 진입 배선 교체(`initTransferPlan` + 컨트롤러 주입) + **계획 페인팅 모드 엔진 신설**(~420줄, 파일 말미) + 훅 2건(`updateLegendCounts` 바 동기화 / `pushMapData` 성공 시 `planPaint.pushed`) |
| `client2/map_editor.html` | 툴바 버튼 `#btn-transfer-plan`, 마운트 `#transfer-plan-root` (구 bonding 마운트 대체) |
| `client2/src/bonding_plan.js`·`.css` | **삭제** — M2가 전량 흡수, 소스 내 import 0건 (git rm) |
| `client2/dist/**` | 빌드 산출물 |

server/·docs/ 미수정. 서버 계약 변경 없음(소비만).

## 2. 요구사항 체크리스트

### A. 계획 패널 진화
| # | 항목 | 상태 |
|---|---|---|
| A1 | stage 선택(stages API) + 타깃 자동완성 | ✅ 서버 API 소비 + 구버전 폴백. stage별 타깃/소스 label·층 배정 유무 자동 전환 |
| A2 | DOE 목록이 패널 중심(M1 층 행 대체·흡수) | ✅ DOE 행 = value 칩(색=맵 팔레트) + 소스·층범위(bonding만)·단위수량·knob 계획(key-value)·설명. M1의 잔여/이력/knob비교/경고 전부 소스 단위로 승계 |
| A2 | 가용 = source-summary 소비, tape 소스 by_core 분해 | ✅ M2 우선 → M1 `core-summary` 폴백 2단. by_core 7키 단일 렌더러 |
| A3 | localStorage 초안 → 관리 테이블 승격(draft/confirmed) | ✅ 서버 저장/확정/로드 3버튼, 상태 배지, 서버 우선 로드 |
| A3 | 구 초안 마이그레이션 프롬프트 | ✅ 1회 제안(수락 무관 플래그), M1 초안 비파괴 보존 |
| A3 | 구버전 서버면 초안 모드 graceful | ✅ 테이블/엔드포인트 부재 감지 → 초안 모드 유지 |

### B. DOE 페인팅
| # | 항목 | 상태 |
|---|---|---|
| B4 | 패널 → 맵 에디터가 `transfer_plan_map`을 타깃 규격으로 염 | ✅ 저장 grid_metadata 우선 → TAPE/BASE 프리셋 → 현 규격(graceful) |
| B4 | 신규 페인팅 엔진 발명 금지 | ✅ 기존 드래그/브러시/legend/Push 그대로. 엔진은 **데이터 소스·저장 대상 전환 + 스냅샷 원복**만 담당 |
| B5 | DOE 목록이 페인팅 값 팔레트로 노출 | ✅ DOE → legend 주입, 플로팅 바 칩 클릭 = 브러시 전환, 설명이 툴팁/ split registry 서술로 연동 |
| B6 | 저장 = 기존 맵 push → `transfer_plan_map` | ✅ 실서버 9행 적재 확인 |
| B6 | DOE별 페인팅 셀 수 집계 + 계획 수량 불일치 경고 | ✅ 행 배지 + 패널 집계 + 검증 배지 `페인팅 불일치 N` |
| B6 | validate API 병용 | ✅ 소비 구현 + 구버전 graceful (현재 서버 404) |
| B7 | DT stage에서 dt_map 참조 오버레이 (가산점) | ⬜ **미구현** — §5 참조 |

## 3. 총괄 확정 계약 반영

**by_core (7키 통일)** — `{core_id, core_lot, core_slot, total, fail, used, remaining}` + `by_core_origin`.
- 경로별 분기 없는 **단일 렌더러**. `fail` null → `미상`(이탤릭), `core_lot`/`core_slot` null → `core_id`를 표시명으로.
- `by_core_origin === "area_map"` → `영역 귀속 기준 (칩 단위 대응 없음)` 뱃지, `"log"` → `DT 로그 기준` 뱃지.
- **`core_id`는 표시용으로만 사용** — 조인 키로 쓰는 코드 없음(경로별 형식 차이 무해).

**stage 어휘 교정 (위반 → 수정)** — 최초 구현이 폴백 stage id를 `dt_plan`/`bonding_plan`으로 발명해 미선언 값이 저장됐다.
- 폴백 어휘를 **`dt` / `bonding`**으로 교정, 주석에 "stages API가 정본·유추 금지" 명시.
- `normalizeStage`는 서버 값을 **그대로 보존**. 타깃 종류 추론은 서버 명시 필드 우선, 미제공 시 **id만** 사용(기존엔 id+name을 봐서 "본딩 (Tape→Base)" 류 이름이 tape로 오판될 여지가 있었음 — 함께 수정).
- 서버 stage 목록에 없는 값은 저장 전 강등: 레거시 별칭(`dt_plan→dt`, `bonding_plan→bonding`) 시도 후 실패 시 첫 stage로. **미선언 값이 서버로 나가는 경로를 원천 차단.**
- 소스 식별자는 자동완성/서버 응답 값을 그대로 사용 — 변형 코드 없음(`parseSource`는 `|` 분리만). 문제의 `TAPE_A`는 제 수기 테스트 입력이었고 코드 결함 아님.

## 4. 라이브 검증 (실서버 :8080, 재기동 없이 — DOM/JS 평가)

검증 시점 서버: 계획 테이블 3종 **실재** / M2 REST 3종 **404**(서버부 미배포) → 폴백·graceful을 실조건에서 검증.

| 항목 | 결과 |
|---|---|
| `node --check` 2파일 + `npm run build` | PASS |
| 패널 마운트·개폐, 5개 섹션, 구 M1 버튼 부재 | PASS |
| stages 404 → 빌트인 폴백 + "구버전" 안내 | PASS |
| stage 전환: bonding=층 배정 노출/커버리지 검증, dt=층 입력 부재·소스 label `Wafer`·커버리지 미표시 | PASS |
| 층 커버리지(공백 4층 → 배정 후 공백 없음) | PASS |
| **source-summary 404 → M1 core-summary 폴백** (`M1 폴백` 뱃지, chips 사상, 역할 뱃지·`eds_fail 미연결`, 부족 경고) | PASS (실서버 실응답) |
| **서버 저장** → `transfer_plan` 1행 + `transfer_plan_doe` 2행, 복합 bk `plan_id\|doe_value`, `target_lot/slot`·`source_lot/slot` 분리 저장 | PASS (실 DB 되읽기 확인) |
| **페인팅 진입**: BASE 프리셋 자동 적용(29×25, chip 11), 테이블 `transfer_plan_map` 전환, `plan_id` 자동 입력, DOE→legend, 브러시=선택 DOE, 테이블/Load 잠금 | PASS |
| **기존 도구로 페인팅**: 드래그 페인트(D1 6셀), 브러시 전환(D2 4셀), 우클릭 드래그 지우기(→3셀), 바 칩 카운트 실시간 동기 | PASS |
| **Push → `transfer_plan_map`** 9행 적재(D1 6/D2 3, plan_id 파티션), split 서술 누락 경고 관문 동작 | PASS |
| **완료** → 바 제거·패널 재개방·집계 반영(`D1 6셀/계획 10`, 불일치 2), **에디터 완전 원복**(bonding_map·10×10·chip 2.5·원본 legend 4종·임시 옵션 제거·잠금 해제) | PASS |
| **취소** → 서버 맵 재로드 후 추가 페인팅분 폐기, 패널 집계 불변, 에디터 원복 | PASS |
| 서버 로드 왕복(qty 999로 변조 → 로드 시 10/12 복원, `source_lot\|source_slot` 재조합) | PASS |
| 계획 확정(confirmed) 저장·배지·서버 status 반영 | PASS |
| 서버 맵 집계 새로고침(`서버 맵 집계` 표기) | PASS |
| validate 404 → "미지원" graceful | PASS |
| M1 초안 마이그레이션: 프롬프트 발동·1회 플래그·**거절 시 M1 초안 보존 및 신 초안 미생성** | PASS |
| M1→M2 변환 로직(층 행→DOE, core→source, 폐기된 `core_region` 탈락) | PASS (동일 로직 node 재현 검증) |
| 레거시 stage 별칭(`bonding_plan` 초안 → `bonding`으로 복원) | PASS |
| **기존 맵 편집 회귀**(브러시 선택·드래그 페인트 4셀·우클릭 전량 지우기 0셀) | PASS |
| 콘솔 에러 | 0건 |
| 테스트 데이터 정리(DB 15행 + localStorage 전량) | 완료 |

**중요 발견 — 프리뷰 pane 0×0 뷰포트**: 최초 페인팅 검증이 전부 실패했는데 원인은 `documentElement.clientHeight === 0`(캔버스 rect 0×0 → 히트테스트 불가)이었다. `resize_window`로 실뷰포트(1600×1000) 부여 후 정상. 추가로 rect를 한 번만 캡처하면 레이아웃 안정화(761→702px) 때문에 좌표가 어긋난다 — **드래그 직전마다 rect 재측정**해야 한다. (첫 회귀 측정에서 "지우기 4→2" 이상이 나온 원인이며, 앱 결함 아님을 재측정으로 확인.)

## 5. 미구현·에스컬레이션

1. **B7 dt_map 참조 오버레이 미구현**(가산점 항목). 서버가 계획 페인팅 화면용 dt_map 배경 데이터를 어떤 형태로 줄지 미정 — "클라 변환 금지" 원칙상 좌표를 클라에서 합성할 수 없어 보류. 서버 응답 형태 확정 후 착수 권장.
2. **`transfer_plan`에 `total_layers` 컬럼 부재** — 층 커버리지 검증의 기준값인 총 층수를 서버에 저장할 곳이 없다. 현재 **로컬 초안에만** 보관(라벨에 `(로컬)` 표기 + 서버 로드가 로컬 값을 덮지 않도록 처리). 컬럼 추가 여부 총괄 결정 요청.
3. **`plan_id` 합성 규칙이 클라 자체 결정** — `<stage>__<target_lot>_<target_slot>`(`transfer_plan_map` 복합 bk가 `plan_id|x|y`라 `|` 사용 불가). 서버가 별도 규칙을 쓴다면 불일치하므로 규칙 확정 필요.
4. **`updated_by` 컬럼이 null로 저장됨** — item-level·updates 양쪽에 `CURRENT_USER`를 넣었으나 DB에는 null. `config.js`의 `CURRENT_USER` 값 또는 서버 처리 확인 필요(레이어링 자체의 수정자 추적은 정상).
5. `GET /tables/{t}/schema`는 **존재하지 않는 테이블에도 200 + 시스템 컬럼 스켈레톤**을 반환한다(존재 확인 불가). 존재 판정은 `GET /tables/{t}/data`(404)로만 가능 — 페인팅 진입 게이트를 이 방식으로 수정했다. 서버부 인지 필요.

## 6. 정리한 테스트 시드 (총괄 승인분 — 완료)

`plan_id = bonding_plan__TESTPLAN_M2VERIFY_01` 관련 **15행 삭제 완료, 잔여 0**:
`transfer_plan_map` 9 · `transfer_plan_doe` 2 · `transfer_plan` 1 · `wafer_map_metadata` 1 · `map_split_registry` 2.
- 삭제 경로: `POST /tables/{t}/rows/batch_delete` (스크립트에 `TP-SMOKE` 감지 시 중단 안전장치 포함).
- **서버부 시드 `TP-SMOKE-1`은 전 테이블에서 무손상 확인**(plan 1 / doe 2 / map 4행 그대로).
- localStorage: `transfer_plan_draft::*`·`transfer_plan_last`·`transfer_plan_m1_migrated`·`map_legend_transfer_plan_map`·테스트용 M1 초안 전량 삭제.

## 7. 재기동/배포 후 확인 항목

1. **stages API 실응답** — 실제 선언 어휘(`dt`/`bonding`)와 `target_kind`/`roles` 필드 존재 여부. 서버가 `target_kind`를 안 주면 클라가 id로 추론하므로, stage id가 `dt`로 시작하지 않는 신규 tape형 stage가 생기면 오판 가능.
2. **source-summary 실응답** — `by_core` 7키·`by_core_origin` 렌더(특히 `area_map` 경로의 null `fail` → `미상` 표기), `fail_breakdown` 키 구성.
3. **validate 실응답** — 경고 배열 형태 및 `stage_unknown` 미발생 확인.
4. M1 마이그레이션 **수락** 경로 1회 수동 확인(자동화 환경이 confirm을 자동 거절해 거절 경로만 실검증됨).
5. 페인팅 진입 시 저장된 `grid_metadata` 기반 규격 복원(이번엔 메타 미존재로 프리셋 경로만 탐).

## 8. 교훈 제안 (총괄 검수 후 반영)

- **함정**: 프리뷰 pane이 0×0 뷰포트로 뜨면 캔버스 `getBoundingClientRect()`가 0이 되어 마우스 히트테스트 기반 검증이 전부 조용히 실패한다(에러 없이 "아무 일도 안 일어남").
  **올바른 방법**: 캔버스 상호작용 검증 전 `resize_window`로 실뷰포트를 주고 rect가 0이 아님을 먼저 확인. 드래그 좌표는 **매 드래그 직전 rect 재측정**(레이아웃 안정화로 크기가 바뀐다).
- **함정**: `GET /tables/{t}/schema`는 존재하지 않는 테이블에도 200을 반환해 "테이블 존재 확인"에 쓸 수 없다.
  **올바른 방법**: 존재 판정은 `GET /tables/{t}/data`(미존재 404). 업무 컬럼·`map_key_columns`가 비었으면 미구성으로 보고 강등.
- **함정**: 서버 stage/enum 어휘를 클라가 임의로 발명하면(`bonding_plan`) 서버 검증이 조용히 스킵되어(`stage_unknown`) 나머지 검증이 통째로 죽는다.
  **올바른 방법**: enum류는 항상 서버 목록 API가 정본. 폴백 상수도 선언 어휘와 일치시키고, 저장 직전 "서버 목록에 없으면 강등" 가드를 둔다.
- (M1 제안 재확인) Bash heredoc에 한글 대형 블록을 넣으면 파싱 오류가 난다 — Write로 스크래치 파일 생성 후 `cat file >> target`. 이번에도 동일 함정 재발했고 동일 방법으로 해결.

## 9. 히스토리 초안 (통합 시 총괄 기록용)

> feat(client): Universal Transfer Plan M2 — map editor 패널을 stage·DOE 모델로 진화(M1 본딩 패널 흡수·삭제). DOE = value ↦ {소스, 층범위, 단위수량, knob 계획, 설명}이 패널 중심이 되고, 관리 테이블 3종(`transfer_plan`/`_doe`/`_map`)에 draft/confirmed로 영속화(localStorage는 graceful 폴백 + M1 초안 1회 마이그레이션). **DOE 페인팅**: 기존 맵 에디터 페인팅 도구(드래그·브러시·legend·Push)를 그대로 쓰되 데이터 소스·저장 대상만 계획 맵으로 전환하는 모드 엔진 신설 — 타깃 규격 자동 적용(저장 메타 > TAPE/BASE 프리셋 > 현 규격), DOE 팔레트 주입, 편집 상태 스냅샷 원복(더티 가드), 완료 시 DOE별 셀 수 집계 → 계획 수량 대조 경고. source-summary는 M2→M1 core-summary 2단 폴백, by_core 7키 단일 렌더러(+`by_core_origin` 강등 표기), stage 어휘는 stages API 정본(미선언 값 저장 차단·레거시 별칭). 신규: transfer_plan.js/.css, 삭제: bonding_plan.js/.css.
