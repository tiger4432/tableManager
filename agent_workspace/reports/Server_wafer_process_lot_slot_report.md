# Server 보고서 — wafer_process에 lot/slot 정보(lot_id·slot_no) 추가

- **작업일**: 2026-07-25 (21:4x~21:5x KST, 라이브 무재기동 — 전부 핫리로드)
- **담당**: server-pm
- **작업 영역**: 전부 gitignored 사용자 영역 (`server/config/*.json`, `server/ingestion_workspace/`) — **git 커밋 0건, server/*.py 코드 수정 0건** (병행 에이전트 충돌 없음)
- **지시서**: `agent_workspace/tasks/Server_wafer_process_lot_slot_task.md`

## 0. 착수 시 발견 사항 (설계 판단)

현행 `wafer_process`에는 **`lot`/`slot` 컬럼이 이미 존재**했다 (어제 데모 구축 시 wafer identity 소스로 넣은 것 — `PERFORMED_ON` 엣지의 `target_identity_from: [lot, slot]`과 enrichment 뷰 WHERE 절이 이를 사용 중).

지시서가 명시한 `lot_id`/`slot_no`를 **추가**하되(ALTER 경로 검증 목적 포함), 기존 `lot`/`slot`은 다음 이유로 **보존**했다:
- `PERFORMED_ON` 엣지 규격(`[lot, slot]`)은 경계 계약에 준하는 그래프 identity 배선 — 단독 변경 회피.
- 기존 159행은 `lot_id`/`slot_no`가 NULL이므로, 엣지·뷰 WHERE를 새 컬럼으로 바꾸면 기존 데이터 연결이 끊긴다.
- 결과: `lot_id = lot`, `slot_no = slot` (동일 값, 수집기에서 동일 변수 분해) — **중복 정리 여부는 §5 총괄 판단 항목**.

## 1. 변경 요약

| # | 파일 | 변경 |
|---|------|------|
| 1 | `server/config/table_config.json` | `wafer_process.column_types`에 `lot_id`/`slot_no`(string) 추가 + `display_columns`에 동일 추가 (slot 뒤) |
| 2 | `server/ingestion_workspace/wafer_process/auto_update/generate_wafer_process.py` | 각 행에 `"lot_id": lot, "slot_no": slot` 추가 — wafer identity(`lot|slot`) 구성 변수를 그대로 분해 사용, 30% 미해결 분기(LOT-C/D/E) 포함 전 행 기록. 헤더 주석 갱신 |
| 3 | `server/config/ontology_mapping.json` | `ProcessEvent.node.props`에 `lot_id`, `slot_no` 추가 (엣지 신설 없음 — §5 참조) |
| 4 | `server/config/enrichment_rules.json` | "공정 이력 (wafer_process)" 뷰 SELECT에 `lot_id, slot_no` 추가 (WHERE는 기존 행 호환 위해 `lot`/`slot` 유지) |

## 2. 검증 결과 (전부 라이브, 무재기동)

| 항목 | 결과 |
|------|------|
| `POST /admin/reload-configs` | 200 success. 직후 `GET /tables/wafer_process/schema` → `lot_id`/`slot_no` string으로 노출 (config 레벨 반영) |
| **물리 ALTER** (information_schema 직접 조회) | 최초 확인 시 **미반영** → 원인 규명(§3) 후 table_config.json in-place 재기록으로 watcher 발화 → `lot_id character varying`, `slot_no character varying` 물리 추가 확인 |
| `run-now` + 21:51 cron 적재 | `WP-215102-*` 등 신규 35행에 lot_id/slot_no 채움 (`total=177, with_lot_id=35`). **이번 실행이 30% 미해결 분기(LOT-E\|25)를 발화** — `lot_id=LOT-E, slot_no=25 = lot/slot = WF-LOT-E-25 분해값` 정합 확인. 기존 행은 NULL(로그 불변 — 정상) |
| 데이터 API 셀 형태 | `lot_id`/`slot_no` 셀이 `{value, is_overwrite, priority_source, ...}` 표준 형태로 반환 (셀 계약 불변) |
| 그래프 반영 | `/graph/neighbors?label=ProcessEvent&identity=WP-215102-17` → `props: {step, eqp_id, lot_id: "LOT-E", slot_no: "25", result, start_time, end_time}` + `PERFORMED_ON`→Wafer `LOT-E\|25` + `EXECUTED_BY`→Eqp `EQP-05`. `/graph/stats`: ProcessEvent 177 = 테이블 total (동기 완주, last_sync 21:51:05). 기존 노드 재파생 없음(지시서 허용 범위) — backfill 불필요 판단 |
| enrichment 참조뷰 | `GET /enrichment/rules` → 3번째 뷰 유지. `/enrichment/rules/core_wafer_attribution/references/2?params={"core_lot":"LOT-E","core_slot":"25"}` → `columns: ["wafer_id","lot_id","slot_no","step","eqp_id","start_time","end_time","result"]`, 신규 35행 전부 lot/slot 판단 근거 노출 |

## 3. 발견한 인프라 사실 — **ALTER 핫리로드의 실제 트리거** (교훈 후보)

- `/admin/reload-configs` → `reload_local_process_cache` → `refresh_dynamic_models(engine)`는 **신규 테이블 CREATE 전용**이다 (`create_missing_dynamic_tables`, C-8에 의해 기존 테이블 런타임 ALTER는 의도적 범위 밖).
- 기존 테이블 **ALTER의 유일한 런타임 경로는 `config_watcher`**(웹서버 프로세스, watchdog로 `table_config.json` 파일 감시 → `sync_dynamic_tables_schema`)다.
- 그런데 **에이전트 Edit 도구의 원자적 쓰기(temp 파일 + rename)는 watchdog `on_modified`를 깨우지 못한다** (핸들러가 on_modified만 구현 — moved/created 이벤트 미처리). 실측: Edit 후 수 분간 물리 미반영 → 동일 내용을 `open(path,"w")`로 in-place 재기록하자 ~1초 내 ALTER 2건 발화.
- 즉 "reload-configs 200 + schema API에 컬럼 노출"은 **물리 반영의 증거가 아니다** — schema API는 config 싱글턴을 읽는다. 물리 확인은 information_schema 직접 조회로.

## 4. 변경 전문

### 4.1 `table_config.json` — wafer_process (변경 후 전문)

```json
"wafer_process": {
  "business_key": "proc_id",
  "column_types": {
    "proc_id": "string",
    "wafer_id": "string",
    "lot": "string",
    "slot": "string",
    "lot_id": "string",
    "slot_no": "string",
    "step": "string",
    "eqp_id": "string",
    "start_time": "string",
    "end_time": "string",
    "result": "string",
    "eventtime": "string"
  },
  "display_columns": [
    "proc_id", "wafer_id", "lot", "slot", "lot_id", "slot_no",
    "step", "eqp_id", "start_time", "end_time", "result", "eventtime"
  ]
}
```

### 4.2 수집기 diff (`generate_wafer_process.py`)

```python
# 헤더 주석 추가:
#   - lot_id/slot_no: wafer identity(lot|slot) 구성 변수를 그대로 분해 기록 —
#     "이 wafer가 어느 step에서 어떤 lot, slot, eqp로 진행되었는지" 시공간 로그.
#     기존 PERFORMED_ON 연결 규격(lot|slot)과 동일 값이 보장된다.

# rows.append({...}) 내부:
        "lot": lot,
        "slot": slot,
        "lot_id": lot,      # 추가
        "slot_no": slot,    # 추가
```

(70% known_combos / 30% LOT-C/D/E 분기 **공통 경로**에서 lot/slot 변수가 결정되므로 미해결 분기도 자동으로 채워짐 — 21:51 실행의 LOT-E|25로 실증.)

### 4.3 `ontology_mapping.json` — ProcessEvent props (변경 후)

```json
"props": ["step", "eqp_id", "lot_id", "slot_no", "result", "start_time", "end_time"]
```

(엣지·description·PERFORMED_ON/EXECUTED_BY는 불변.)

### 4.4 `enrichment_rules.json` — 3번째 참조뷰 query (변경 후)

```json
"query": "SELECT wafer_id, lot_id, slot_no, step, eqp_id, start_time, end_time, result FROM wafer_process WHERE lot = :core_lot AND slot = :core_slot ORDER BY start_time DESC"
```

(bind는 decision_key만 — `_validate_view_sql` 통과, 라이브 응답 200 확인.)

## 5. 총괄 판단 항목

1. **Lot 노드 신설 여부**: 현행 ontology_mapping·라이브 그래프 어디에도 `Lot` label 부재 (노드: Chip/Wafer/ProcessEvent/SplitCondition, 타겟: Base/Step/Eqp + enrichment 파생 LineModelRegistry/Owner). 지시대로 props까지만 반영. `ProcessEvent -PERFORMED_IN-> Lot` 엣지를 원하면 Lot label 신설이 선행돼야 하며, 이는 Wafer identity(`lot|slot`)와의 관계(Lot⊃Wafer 시공간 topology, 스펙 §7.5) 설계가 필요 — 매핑 신설 남발 금지 원칙에 따라 보류.
2. **`lot`/`slot` vs `lot_id`/`slot_no` 중복**: 현재 동일 값 이중 기록. 장기적으로 (a) 구컬럼 유지(엣지·기존 행 호환, 현상태), (b) 엣지·뷰 WHERE를 신컬럼으로 이관 + 기존 159행 backfill 후 구컬럼 폐기 중 택일 필요. 데모 목적상 (a)로 두었다.
3. 수집기 `n_events`가 10~20으로 상향돼 있어(내 변경 아님) start/end_time이 **미래 시각**(+수 시간)까지 진행함 — 로그 리얼리즘이 중요하면 시작 오프셋(`180~360분`)을 이벤트 수에 비례해 늘릴 필요.

## 6. 교훈 제안 (총괄 검수용)

- **함정**: 에이전트 Edit(원자적 temp+rename)로 `table_config.json`을 고치면 config_watcher의 `on_modified`가 발화하지 않아 기존 테이블 ALTER가 조용히 누락된다. `/admin/reload-configs`는 신규 CREATE 전용이라 대체 경로가 아니며, schema API는 config 싱글턴을 읽으므로 "200 + 컬럼 노출"이 물리 반영 증거가 아니다.
  **올바른 방법**: 기존 테이블 컬럼 추가 후엔 파일을 in-place 재기록(`open(path,"w")`)해 watcher를 깨우고, information_schema 직접 조회로 물리 반영을 확정할 것.

---

## 8. [추가 작업] 수집기 v2 — bonding 워크리스트 조합 우주 커버 (22:0x KST)

**배경**: 사용자 리포트 "bonding log enrich에서 공정 이력이 하나도 안 뜬다 (LOT-D, LOT-E)". 총괄 triage: 워크리스트 조합 수십 개 대비 wafer_process에는 11개 조합만 존재 — 뷰 쿼리는 정상, 데이터 커버리지 결손.

### 8.1 접근법 선택 근거 (권장안 채택 — DB에서 실존 조합 읽기)

- 수집기는 `run_auto_update.py`의 `GenericScriptRunnerCollector.execute()`가 **동일 프로세스 내 `exec()`로 실행** — conda `assy_manager` 환경이라 psycopg2 가용, 폴백 subprocess도 `sys.executable`(동일 env)이므로 양 경로 모두 DB 접근 가능.
- 하드코딩 확장은 bonding이 2분마다 30% 확률로 신규 조합을 만들어 **우주가 계속 자라므로** 곧 다시 결손이 생긴다. DB에서 `SELECT DISTINCT core_lot, core_slot FROM bonding_log`로 우주를 읽으면 신규 조합을 자동 추종.
- 안전장치: `connect_timeout=3` + 전체 try/except → 실패 시 실측 분포 하드코딩 폴백(`FALLBACK_UNIVERSE` 10조합)으로 동작, 수집기는 죽지 않음.

### 8.2 생성 정책 (폭주 방지)

| 항목 | 값 |
|------|-----|
| 미커버 조합(우주 − wafer_process 기존 lot/slot) | 셔플 후 **전부** 타겟 (백필) |
| 정상 상태 추가 생성 | 기존 조합 1~2개 재선택, 조합당 3~6 이벤트 |
| 절대 상한 | `MAX_ROWS_PER_CYCLE=240` (외/내 루프 이중 가드 — 초과분은 다음 사이클이 미커버로 자연 이월) |
| 정상 상태 사이클당 생성량 | 신규 bonding 조합 0~2개 + 재선택 1~2개 ≈ 10~25행 (기존 v1의 10~20행과 동급) |
| 시각 리얼리즘 | 시작 오프셋 720~1080분 전 — 이벤트 최대 소요(6×120분)를 흡수해 §5-3의 미래 시각 문제 함께 해소 |

lot_id/slot_no 분해 기록·`WF-<lot>-<slot>`·셀/엣지 규격은 §4.2 그대로 유지. proc_id는 `WP-<HHMMSS>-<seq:03d>`로 자릿수만 확장(240행 대응, 포맷 계약 없음 확인).

### 8.3 발견한 실행 컨텍스트 함정 (교훈 후보 — 실측)

스케줄러의 `exec(code, global_ns, local_ns)`는 **globals/locals 분리 네임스페이스**다. 스크립트 top-level에서 import한 이름(`os` 등)은 local_ns에 바인딩되는데, 스크립트 안에서 **함수를 정의하면 그 함수의 `__globals__`는 global_ns**라 함수 본문에서 top-level 이름 참조 시 NameError가 난다. 실측: `_load_combos()` 함수 안의 `os.getenv`가 NameError → except가 삼켜 **조용히 폴백 10조합만 생성**(드라이런에서 적발). 함수 제거 후 top-level 인라인 try/except로 재작성해 해결. → **auto_update 수집기 스크립트에서는 top-level 이름을 참조하는 함수 정의 금지** (모든 import를 함수 안에서 다시 하거나, 인라인으로 작성).

### 8.4 라이브 검증 (run-now 1회 + 후속 주기, 무재기동)

| 항목 | 결과 |
|------|------|
| 드라이런 (exec 분리 네임스페이스 재현) | 240행 / 54조합 / `lot_id==lot`·`slot_no==slot` 전행 True / LOT-C 포함 |
| run-now(22:07) + 22:07 주기 | 총 177→**586행**. SQL 실측: bonding universe **62조합**, wafer_process 커버 64조합, **uncovered = 0** (완전 커버) |
| 참조뷰 — 임의 조합 3개 | `LOT-C\|05` 4행 (FAIL 1건 포함) · `LOT-D\|08` 3행 · `LOT-E\|18` 4행 — 전부 `columns=[wafer_id, lot_id, slot_no, step, eqp_id, start_time, end_time, result]`로 이력 반환, start_time 전부 과거 시각 |
| 그래프 추종 | `/graph/stats`: ProcessEvent 586 = 테이블 행수, PERFORMED_ON/EXECUTED_BY 586, last_sync 22:08:03 — 자동 완주 |

### 8.5 참고

- covered(64) > universe(62)인 것은 v1이 생성한 `LOT-E|25` 등 bonding에 없는 조합 이력이 남아 있기 때문 — 로그로서 무해.
- 백필 첫 사이클 이후 테이블 성장은 bonding 신규 조합 발생률(2분당 30%)에 종속 — 일 수천 행 수준으로 v1과 동급. 장기 운용 시 보존기간 purge는 별도 과제.

## 7-1. 이력 초안 (총괄 통합용 — 직접 기록하지 않음)

> 2026-07-25: wafer_process에 lot_id/slot_no 추가 (config·수집기·ProcessEvent props·enrichment 뷰, 전부 gitignored 사용자 영역·핫리로드). 추가로 수집기 v2 — bonding_log 실존 조합 우주를 DB에서 읽어 미커버 조합 백필(상한 240행/사이클), 워크리스트 전 조합에서 공정 이력 참조뷰 표시 확인. 부산물 실측 2건: (1) config_watcher가 원자적 파일 교체(on_modified 미발화)에 반응하지 않아 런타임 ALTER 누락 가능 — on_moved 보강 후보. (2) auto_update의 분리 네임스페이스 exec에서 스크립트 내 함수가 top-level import 이름을 참조하면 NameError — 수집기 작성 가이드 반영 후보.
