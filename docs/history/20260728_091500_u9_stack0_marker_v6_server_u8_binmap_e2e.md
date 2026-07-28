# U9 서버 반쪽: STACK 0 마커 + V6 착지 · U8 격리 환경 bin_map 선언 경로 E2E 실증

## 현상 / 배경

- **U9**: 사용자 결정(2026-07-28) — legend의 STACK `0`은 높이도 오류도 아닌 **마커 선언**(상태 표시 값, 예: BASE FAIL)이다. 계약 벡터(`contracts/doe_band_rules/vectors.json`)가 map-pm에 의해 **v3**로 먼저 이동했고 클라이언트는 이미 준수 상태 — 서버가 같은 파일에 맞춰 착지해야 했다.
- **U8**: 라이브 실측(map-pm 확인) — 두 stage 모두 `bins.axis: "unavailable"`. 원인은 결함이 아니라 `bin_map`/`lot_membership` **미선언**이며, 사용자 판정은 "컬럼명을 코드·라이브 config에 박지 말 것(커스텀 가능하게)". 선언 경로가 실제로 동작하는지 **격리 환경(:8081)에서만** 증명하는 것이 과제.

## 해결 — Part 1: `server/transfer_plan.py` 마커 의미론 (vectors v3 채점)

- `stack_state`: 4번째 상태 `STACK_MARKER("marker")` — **정확히 0**(또는 `"0"`)만 승격. 공백은 여전히 blank(V5), 음수는 여전히 invalid(값 보존). `_int_state`는 불변 — 층 경계·BIN은 여전히 0을 거부한다(`MID1:0` 거부 유지).
- `mid_zone`: 마커 → `{from:null, to:null, size:0, known:true}` — **알 수 있는 빈 범위**. 판독 불가(`known:false`)와 절대 접지 않는다(접으면 한쪽은 V5가 합법 행을 갈구고, 반대쪽은 오타 높이가 조용히 소요 0이 된다).
- `zone_layers`: 마커 → `[]`(내용이 무엇이 적혀 있든). 내용의 모순은 기하가 아니라 V6가 보고한다. `zone_demand`는 이로부터 자동으로 0을 유도(칠한 셀 수는 곱수가 아니라 메시지).
- `validate_zone_plan`: **V6 신설** — 마커 행에 구역 자재가 있으면 모순 보고(자재를 메시지에 명기 — 클라에서 구역 칸이 「해당 없음」으로 비활성 렌더되므로). **마커 행이 답하는 유일한 규칙**: V5/V2/V1/V4/W-DUP-MAT 억제(`continue`), V3 풀 스캔에서도 마커 행 제외(소요 없는 토큰은 이중 계산 불가).
- `material_rollup_rows`: 마커 행은 롤업에서 **부재**(0으로 존재하지 않음 — "계획됨·비용 0"으로 읽히는 행 금지).
- `/api/transfer-plan/validate`: 별도 배선 불필요 — `validate_zone_plan` 경유로 V6가 `zone_rule_violation`(비차단 권고)로 나가고, 수요 루프는 `layers==0`에서 마커를 자연 제외(자재 조회·source_unresolved 미발생).

### 테스트 (`server/tests/test_doe_zone_model.py`)

- 벡터 **버전 핀** `version >= 3` + 그룹 구성 가드 유지(신규 그룹 조용한 스킵 불가). 그룹별 최소 케이스 수 상향(stack 12 · extent 7 · plan 15 · demand 8 · rollup 5) — 마커 케이스 삭제가 시끄럽게 실패하도록.
- 발화 규칙 집합에 **V6 추가** (`{V1..V6, W-DUP-MAT}` 전부 발화 확인).
- 마커 전용 축 고정 테스트 5본: 선언 vs 부재(blank) 구분 · known-empty vs unknowable 구분 · V6 단독 메시지(억제 범위) · V3 제외가 "마커 상태" 때문임을 증명하는 대조(fixture-activation: 같은 토큰쌍이 stack을 실높이로 바꾸면 V3 발화) · 롤업 부재.

### 검증

- `test_doe_zone_model.py` 29 passed · **전체 스위트 820 passed**.
- **뮤테이션 9/9 킬**: M1 marker→invalid 회귀 / M2 blank→marker 접힘 / M3 known:false 접힘 / M4 `[]`→`None` / M5 V6 후 fall-through / M6 V3 스캔 미제외 / M7 롤업 미제외 / M8 V6 미발화 / M9 마커가 1층 소요 — 전부 테스트 실패로 검출. 원본은 바이트 단위 복원(CRLF 함정 회피).

## 해결 — Part 2: U8 격리 환경(:8081) bin_map E2E

- **구조적 발견**: `source_config_ref`(M1 위임) stage는 `bin_map`을 선언해도 **축이 켜지지 않는다** — `get_stage_source_summary`가 위임 경로에서 bins 요청에 무조건 `unavailable`("core-kind(M1 위임) 소스는 좌표 집합을 갖지 않습니다")로 답한다(`transfer_plan.py` L1561-1567). `_bin_axis_binding`은 `_summarize_inline`(inline `source`)에서만 소비된다.
- 격리 조치(dev_env만, 라이브 무접촉): ① `devenv.py bootstrap --force`로 낡은 config(v1 plan_store) 라이브 동기화 ② dt stage를 inline `source`로 전환(bonding_plan 역할 미러 + **`origin_log` self-join**(core_defect_map → 자기 자신) — 루트 소스의 출신은 자기 자신이며, origin_log missing이면 remaining 강등으로 전 BIN unknown이 된다) ③ **선언**: `bin_map: {table: dt_map, columns: {lot, slot, x, y, bin: val}}` ④ assy_qa에 scratch BIN 셀 시딩(dt_map LOT-A/05, 1288셀 = core 좌표 복사, bin 1/2 반반 + unbinned 5셀).
- **E2E 결과** (`GET :8081/api/transfer-plan/source-summary?stage=dt&lot=LOT-A&slot=05&bins=`):
  - `bins.axis: "connected"`, 독립 대조 계산과 **완전 일치**: bin1 `{cells 644, total 644, fail 174, transferred 65, remaining 415, reliable true}` · bin2 `{644, 173, 63, 425}` · `unbinned_cells 5`.
  - `bins=1,9` → BIN 9는 `bin_absent`(+remaining null — 0 아님) 계약 유지.
  - `scope=lot` → `slots_origin:"map"` 강등 경고 + `by_slot[{slot:'05', map_exists:true}]` + `basis:"pool_sufficiency"` — QA의 잔여/맵여부 시나리오 재료 완비.
  - 보너스: scratch registry 2행(실 DOE + STACK '0' 마커)으로 `validate` 라이브 확인 — **V6 발화(비차단, status "warnings")**, 마커의 `MID9`는 조회·소요·롤업 어디에도 없음, 실 DOE는 유도 수량 2576(=644×4) vs 가용 840으로 `qty_shortage` 정상 발화.
- 격리 스택은 **가동 상태로 유지**(QA 라운드용): startup `sync_dynamic_tables_schema`가 assy_qa `map_split_registry`에 zone 4컬럼을 ALTER로 반영한 것도 information_schema로 확인.

## 문서

- `docs/guide/CONFIG_GUIDE.md` §5.8: 마커 의미론, V1~**V6**, `bin_map` 문단에 **M1 위임 stage 무효** 명기(선언 형태 자체는 실측 검증됨 — 정확했음).
- `docs/spec/MAP_EDITOR_SPEC.md` §6/§6.0-bis/§6.1-bis: 층 구조 행 마커 추가, V6 행 신설, bin_map 위임 경로 주의.
