# Server 보고서 — WAFER PROCESS 가짜 테이블 + auto_update + enrichment 판단 근거 등록

- **작업일**: 2026-07-25 (21:10~21:25 KST, 라이브 무재기동)
- **담당**: server-pm
- **작업 영역**: 전부 gitignored 사용자 영역 (`server/config/*.json`, `server/ingestion_workspace/`) — **git 커밋 대상 아님, 코드 수정 0건**
- **실행 환경**: 라이브 5프로세스 스택 (uvicorn:8080 · run_watcher · run_chain_worker · run_graph_sync · run_auto_update, 전부 conda `assy_manager`)

## 1. 변경 요약

| # | 파일 | 변경 |
|---|------|------|
| 1 | `server/config/table_config.json` | `wafer_process` 테이블 신규 등록 (bk=`proc_id`, 전 컬럼 string, display_columns=전 컬럼) |
| 2 | `server/ingestion_workspace/wafer_process/auto_update/generate_wafer_process.py` | 신규 — 3분 주기 가짜 수집기 (`# schedule: */3 * * * *`) |
| 3 | `server/config/enrichment_rules.json` | `core_wafer_attribution`에 3번째 참조뷰 "공정 이력 (wafer_process)" 추가 (기존 2개 유지) |
| 4 | `server/config/ontology_mapping.json` | `wafer_process` → `ProcessEvent` 노드 + `PERFORMED_ON`→Wafer / `EXECUTED_BY`→Eqp 엣지 |

재기동 없이 `POST /admin/reload-configs` 2회로 전 항목 배선 완료.

## 2. 검증 결과 (전부 라이브, 무재기동)

| 항목 | 확인 시각 | 결과 |
|------|-----------|------|
| 1차 reload 후 `GET /tables/wafer_process/data` | 21:15 | **HTTP 200** `{total:0}` — 동기 CREATE 경로로 물리 테이블 생성 확인 |
| 워크스페이스 자동 생성 | 21:15 (reload 직전 부재 확인 → 직후 존재) | `ingestion_workspace/wafer_process/` + `archives/auto_update/config/err/raws/scripts` 전체 자동 생성 (watcher의 SYSTEM_RELOAD 워크스페이스 sync) |
| `GET /tables/wafer_process/schema` | 21:15 | 200 — 10개 사용자 컬럼 + 메타컬럼(`is_graph_synced` 등) 노출, bk=proc_id |
| 수집기 등록 (`/admin/auto-update/status`) | 21:17 (2차 reload +8초) | `wafer_process/generate_wafer_process.py`, cron `*/3 * * * *`, next_run 21:18:00, active=true |
| 첫 CSV 적재 (std parser, 커스텀 스크립트 없이) | **21:18:04 생성 → 21:18:08 적재 완료** | `eqp_wafer_process_20260725_211804.csv`(6행) → archives/ 이동, DB `total:6`, 셀 형태 `{value, is_overwrite, priority_source}` 정상 |
| 2번째 주기 실행 | 21:21 (아래 §2.1) | 주기성 확인 |
| enrichment 참조뷰 3번째 탭 | 21:16(빈 응답 200) / 21:19(실데이터) | `GET /enrichment/rules` → 3개 label 노출. `/references/2?params={"core_lot":"LOT-A","core_slot":"05"}` → **6행 공정 이력 반환** (검증기 통과 — bind는 decision_key만) |
| graph_nodes에 ProcessEvent | 21:18:08 (graph sync last_sync) | `/graph/stats`: `ProcessEvent:6`, `PERFORMED_ON:6`, `EXECUTED_BY:6`. `/graph/neighbors?label=ProcessEvent&identity=WP-211804-00` → **기존 Wafer 노드 `LOT-A\|05`(chip_count 249)로 정확히 연결** + Eqp `EQP-08` 신규 노드 |
| mapping-summary | 21:16 | `/graph/mapping-summary` 응답에 `wafer_process` + `ProcessEvent` 포함 |

### 2.1 2번째 주기 실행 (21:21 cron)

- **21:21:03** `eqp_wafer_process_20260725_212103.csv`(5행) 생성·적재 → DB `total:11`, graph `ProcessEvent:11` (그래프 동기까지 자동 추종).
- 2번째 실행은 **30% 분기(미해결 조합 공간)가 발화**해 `LOT-E|08`을 선택 — `/references/2?params={"core_lot":"LOT-E","core_slot":"08"}` 호출 시 **5행의 공정 이력(FAIL 2건 포함)이 판단 근거로 반환**됨을 라이브 확인.
- 확인 시점 worklist(`core_wafer_map` 58건, 미해결 57건)에 `LOT-E|08`은 아직 없으나(bonding이 2분 주기로 동일 분포 신규 조합을 생성 중), LOT-C/D/E 미해결 조합 50여 건이 같은 값 공간에 있어 근거 누적은 시간에 따라 자연 축적된다.

## 3. 데이터 설계 (bonding 데모와의 연속성)

- `wafer_id` = `WF-<lot>-<slot>` 규격 (예: `WF-LOT-A-05`) — bonding 데모 lot/slot 값 공간과 동일.
- 70%: bonding `known_combos`(LOT-A 05/07/12, LOT-B 01/03) 재사용 → 해석된 wafer의 이력 축적.
- 30%: **미해결 조합 공간(LOT-C/D/E × slot 01~25)** — bonding 신규 결손 조합과 동일 분포라 시간이 지나며 워크리스트 미해결 항목의 참조뷰에 판단 근거가 실제로 쌓인다.
- 매 실행 3~6개 공정 이벤트, step ∈ {DEPO, CMP, PHOTO, ETCH, CLEAN, IMPLANT, ANNEAL}, eqp `EQP-01~08`, 시간은 과거→현재로 진행(20~90분 소요, 5~30분 간격), result 10% FAIL.
- `PERFORMED_ON`의 `target_identity_from: [lot, slot]` → 조인 키 `LOT-A|05` — `core_wafer_map`이 선언한 Wafer identity(`core_lot|core_slot`) 규격과 동일 값 공간이므로 그래프에서 즉시 연결됨(라이브 확인).

## 4. 변경 전문

### 4.1 `server/config/table_config.json` — 추가 블록 (`map_split_registry` 앞)

```json
"wafer_process": {
  "business_key": "proc_id",
  "column_types": {
    "proc_id": "string",
    "wafer_id": "string",
    "lot": "string",
    "slot": "string",
    "step": "string",
    "eqp_id": "string",
    "start_time": "string",
    "end_time": "string",
    "result": "string",
    "eventtime": "string"
  },
  "display_columns": [
    "proc_id", "wafer_id", "lot", "slot", "step",
    "eqp_id", "start_time", "end_time", "result", "eventtime"
  ]
}
```

### 4.2 `server/config/enrichment_rules.json` — `core_wafer_attribution.reference_views`에 3번째 항목 추가

```json
{
  "label": "공정 이력 (wafer_process)",
  "query": "SELECT wafer_id, step, eqp_id, start_time, end_time, result FROM wafer_process WHERE lot = :core_lot AND slot = :core_slot ORDER BY start_time DESC",
  "limit": 50
}
```

(LIMIT 50은 서버가 `limit` 필드로 강제 — SQL 본문에 LIMIT 불필요. bind 파라미터는 decision_key(`core_lot`, `core_slot`)만 사용 — `_validate_view_sql` 통과.)

### 4.3 `server/config/ontology_mapping.json` — 추가 블록 (`map_split_registry` 앞)

```json
"wafer_process": {
  "description": "wafer가 전공정 설비에서 단위 공정(step)을 수행한 이벤트 로그 — bonding 이전 단계의 공정 이력. lot|slot 표기로 Wafer에 연결된다",
  "node": {
    "label": "ProcessEvent",
    "identity": "proc_id",
    "props": ["step", "eqp_id", "result", "start_time", "end_time"]
  },
  "edges": [
    {
      "type": "PERFORMED_ON",
      "target_label": "Wafer",
      "target_identity_from": ["lot", "slot"],
      "description": "이 공정 이벤트가 수행된 대상 wafer (lot|slot 표기 기준 — core_wafer_map의 Wafer identity 규격(core_lot|core_slot)과 동일 값 공간)"
    },
    {
      "type": "EXECUTED_BY",
      "target_label": "Eqp",
      "target_identity_from": ["eqp_id"],
      "props": ["start_time", "end_time"],
      "description": "이 공정 이벤트를 실행한 설비(equipment)"
    }
  ]
}
```

### 4.4 `server/ingestion_workspace/wafer_process/auto_update/generate_wafer_process.py` — 신규 전문

```python
# schedule: */3 * * * *
# filename_prefix: eqp_wafer_process

# [DEMO] WAFER PROCESS 전공정 이력 fake 생성기 — Enrichment 판단 근거 데모용.
# 3분마다 wafer 단위 공정 이벤트(step 진행)를 raws/에 드롭한다.
# bonding_log 데모의 lot/slot 값 공간(LOT-A~E, slot 01~25)과 이어지도록 설계:
#   - wafer_id는 WF-<lot>-<slot> 규격 (예: WF-LOT-A-05)
#   - 70%: bonding이 이미 아는 조합(LOT-A/B) 재사용 → 해석된 wafer의 이력 축적
#   - 30%: bonding의 미해결 조합 공간(LOT-C/D/E × slot 01~25) → enrichment
#     참조뷰("공정 이력 (wafer_process)")에 판단 근거가 실제로 쌓인다.

import pandas as pd
from random import randint, random, choice
from datetime import datetime, timedelta

STEPS = ["DEPO", "CMP", "PHOTO", "ETCH", "CLEAN", "IMPLANT", "ANNEAL"]

now = datetime.now()
uniq = now.strftime("%H%M%S")

# 기존 조합(bonding known_combos와 동일) vs 미해결 조합 공간 — 30% 확률로 후자
known_combos = [("LOT-A", "05"), ("LOT-A", "07"), ("LOT-B", "01"), ("LOT-A", "12"), ("LOT-B", "03")]
if random() < 0.3:
    lot = choice(["LOT-C", "LOT-D", "LOT-E"])
    slot = f"{randint(1, 25):02d}"
else:
    lot, slot = choice(known_combos)

wafer_id = f"WF-{lot}-{slot}"

rows = []
n_events = randint(3, 6)
# 공정 시간은 과거에서 현재로 진행 (step당 20~90분 소요, 5~30분 간격)
cursor = now - timedelta(minutes=randint(180, 360))
for j in range(n_events):
    step = choice(STEPS)
    duration = randint(20, 90)
    start = cursor
    end = start + timedelta(minutes=duration)
    cursor = end + timedelta(minutes=randint(5, 30))
    rows.append({
        "proc_id": f"WP-{uniq}-{j:02d}",
        "wafer_id": wafer_id,
        "lot": lot,
        "slot": slot,
        "step": step,
        "eqp_id": f"EQP-{randint(1, 8):02d}",
        "start_time": start.strftime("%Y-%m-%d %H:%M"),
        "end_time": end.strftime("%Y-%m-%d %H:%M"),
        "result": "FAIL" if random() < 0.1 else "PASS",
        "eventtime": now.strftime("%Y-%m-%d %H:%M"),
    })

out = pd.DataFrame(rows)
```

## 5. 미해결 / 참고

- **proc_id 유일성**: `WP-<HHMMSS>-<idx>` — 하루 내 동일 초 재실행 시에만 충돌 가능(cron 3분 주기라 실질 없음). 날짜가 바뀌면 동일 HHMMSS 재발 가능하나 upsert(bk) 특성상 덮어쓰기로 수렴 — 데모 목적상 허용. 장기 운용 시 날짜 포함 권장.
- **미해결 조합 매칭은 확률적**: 참조뷰 근거는 LOT-C/D/E 조합이 bonding 결손 조합과 겹칠 때 쌓인다(동일 분포이므로 시간이 지나며 누적). 즉시 시연이 필요하면 `/admin/auto-update/run-now`를 수 회 눌러 가속 가능.
- 문서(히스토리·리빙 문서) 변경 없음 — 전부 gitignored 사용자 영역이라 tracked delta 0. 이력 남길지 여부는 총괄 판단 위임.

## 6. 교훈 제안 (총괄 검수용)

- `/graph/neighbors`는 `node_id`가 아니라 `label` + `identity` 쿼리 파라미터를 받는다 (`/graph/nodes/search` 결과의 `id`를 그대로 넣으면 422).
- `/schema`라는 전역 경로는 없다 — 스키마 계약 확인은 `GET /tables/{t}/schema` (없는 경로는 catch-all이 index.html을 200으로 돌려주므로 "200이지만 HTML"에 속지 말 것).
