# 🧾 기능 인벤토리 — 서버 절반 (2026-09-16 실측)

> **무엇인가:** 「이 서버가 «무엇을 할 줄 아나» · 그 기능이 «어디 살고» · «누가 부르고» ·
> «오늘 닿는 것이 있나»」를 한 표로. 총괄에게 이 목록이 없었다.
> **무엇이 아닌가:** 설계 제안도, 대기열도 아니다. 판정은 §C·§D 만 낸다.

## 0. 어떻게 쟀나 — 순서와 규칙

```
① 문서를 «먼저» 읽었다   docs/architecture/CODE_MAP.md(5,417줄) · docs/overview/SYSTEM_OVERVIEW.md(280) ·
                       docs/architecture/SYSTEM_FLOWS.md(773) · docs/architecture/PRIMITIVES.md(2,231)
② 그다음 «오늘의 코드»에 대고 쟀다   인용한 문장이 근거가 아니라, «오늘도 참인지»가 근거다
③ 어긋난 자리는 «발견»으로 적었다     조용히 우회하지 않았다 — §D
```

**계수 규칙 — 「소비자 0」을 말하기 전에 네 갈래를 «먼저» 뺐다**
```
① 데코레이터가 등록한다      110 라우트 전부가 여기 해당한다 — import 소비자가 «있을 수 없다»
② 시험만 쓴다               server/tests 455 파일
③ 설정이 «문자열»로 부른다    chain_rules.json 의 `mapper` · ledger_config 의 `implementation_id`
④ «명령줄»이 이름을 든다      uvicorn main:app · run_watcher.py · run_chain_worker.py · run_auto_update.py ·
                          server/scripts/*.py (CLI)
```
🔴 훑기는 전부 `git grep`. 평문 grep 은 `server/config/*`·`server/mappers/*`·`server/ingestion_workspace/*`
를 같이 세는데 **셋 다 gitignore 돼 있어** 그 수는 이 박스 얘기이지 어느 설치의 얘기도 아니다
(`.gitignore:64 · 75 · 88` 실측). 그래서 §E 를 반드시 읽을 것.

### 0-1. 모집단 검증 — 총괄이 준 수를 다시 쟀다

| 준 값 | 잰 값 | 철자 | 판정 |
|---|---|---|---|
| 라우트 데코레이터 110 | **110** | `git grep -cE '^@(app\|router)\.(get\|post\|put\|delete\|patch\|websocket)' -- server/` | ✅ 일치 |
| `server/main.py` 91 | **91** | 위 철자 · `@app.websocket("/ws")` «포함» | ✅ |
| `ontology_config_explorer_router.py` 15 | **15** | prefix `/admin/ontology-explorer` | ✅ |
| `ledger/trace_router.py` 4 | **4** | prefix `/api/ledger` | ✅ |
| 긴 프로세스 = 런처의 자식 넷 | **넷** | `server/runtime/launcher_specs.child_specs()` 가 값으로 든다 | ✅ |

**라우트 91 의 접두 분포(main.py)** — `/admin` 36 · `/tables` 21 · `/api` 17 · `/internal` 4 ·
`/map-presets` 3 · `/enrichment` 2 · `/audit_logs` 2 · `/ws`·`/runtime`·`/health`·`/dashboard`·`/chain`·`/` 각 1.

**게이트 실측** — `/admin` 36 + `/internal` 4 + **`/chain/graph`·`/runtime` 둘**(접두가 `/admin` 이
아닌데 `require_admin_token` 을 단다) = 42. 탐색기 라우터 15 는 전부 게이트(그중 strict 9).
`ledger/trace_router` 4 는 **게이트 없음**(공개 읽기면).

**런처 자식 넷** (`launcher_specs.child_specs()`):
`Backend FastAPI Server`(uvicorn `main:app`, `DECOUPLED=True`·`ASSY_CHAIN_WORKER=0`) ·
`File Ingestion Watcher`(`run_watcher.py`, heartbeat `watcher`) ·
`Chained Ingestion Worker`(`run_chain_worker.py`, heartbeat `chain`) ·
`Auto Update Scheduler`(`run_auto_update.py`, heartbeat `scheduler`).
데스크톱 셸은 이 값에 «없다» — `main()` 이 서버 전용 모드가 아닐 때만 덧붙인다.

### 0-2. 「배선?」의 어휘 — 네 글자만 쓴다

```
✅ 닿는다     오늘 부르는 쪽이 있다. 그 부르는 쪽을 «칸에 적는다»
⚠️ 반쪽       서버는 도는데 «화면이 없다» 또는 «갈래가 죽었다». §A·§B 로 간다
⛔ 안 닿는다   네 갈래를 뺀 뒤에도 부르는 쪽이 0
🔒 못 잰다    소비자가 gitignore 밖에 있을 수 없다 — §E
```

---

## 1. 파일 인제션 — 워처 · 파서 · 체크포인트

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 디렉터리 감시 | `ingestion_workspace/*/raws/` 의 생성·이동·수정 이벤트와 주기 스윕으로 파일을 집어 파이프라인에 넘긴다 | `server/parsers/directory_watcher.py` (`WorkspaceWatcher`·`IngestionHandler`) | 명령줄 `run_watcher.py`(런처 자식). 단일 프로세스 모드에선 `main.startup_event` 가 인라인으로 | ✅ 닿는다 |
| 커스텀 파서 플러그인 | 워크스페이스의 `scripts/` 를 파일 이벤트마다 «다시 나열»해 `BasePipelineParser.match` 가 참인 첫 파서로 판다 | `parsers/pipeline_base.py` + `<workspace>/scripts/*.py` | `_discover_and_execute_pipeline` | 🔒 못 잰다(스크립트가 gitignore) |
| 표준 파서 폴백 | 커스텀이 «하나도» 안 맞을 때만, 헤더를 `table_config` 로 검증해 CSV/TSV/TXT 를 스트리밍으로 읽는다 | `parsers/std_parser.py` (`is_std_supported`·`parse_std_file`) | `directory_watcher._try_std_parse` «하나» | ✅ 닿는다 |
| 선언형 정규식 인제스터 | 행/헤더/**경로** 세 계열 규칙을 로드 시점에 검증하고 서열(경로<헤더<행)로 병합 | `parsers/advanced_ingester.py` (`AdvancedIngester`) | 🔴 **워처 경로에 없다** — 추적 트리의 호출자는 `server/tests/test_filename_rules_declaration.py` «하나». 부르는 쪽은 운영자가 손으로 복사한 워크스페이스 스크립트(`server_url` 로 API 에 POST) | 🔒 못 잔다 / ⚠️ 반쪽 (§D-3) |
| HTML 토폴로지 파서 | HTML 표를 그래프/행렬로. 격자 원점을 «두 번» 유도해 일치할 때만 채택하고 불일치는 이름 붙여 거절 | `parsers/html_topology_parser.py` (`HTMLTableGraphParser`·`HTMLMatrixTableParser`·`take_refusal`) | `directory_watcher` 가 legacy import shim 으로 별칭을 걸고 `take_refusal`/`clear_refusal` 을 읽는다 | ✅ 닿는다 |
| 오프셋 체크포인트 · 재투입 방지 | 파일 sha256 시그니처 dedup(tier-2) + 경로·stat dedup(tier-1) + 청크 진척 기록 + 재기동 재개 | `ingestion/checkpoint.py` (`plan_ingestion`·`record_chunk_progress`·`mark_done`·`find_terminal_by_path_stat_batch`) | `directory_watcher` | ✅ 닿는다 |
| heavy 레인 격리 | 임계(기본 10MB) 초과 파일을 전용 큐로 보내 다른 표를 안 막는다 | `directory_watcher.get_heavy_threshold_bytes` 외 | `ingestion_settings.json.heavy_file_mb` (문자열 선언, 갈래 ③) | ✅ 닿는다 |
| 인제션 진행 스냅샷 | QUEUED/PROCESSING/FINISHED 와 진행률을 웹서버의 «레지스트리»에 밀어 넣는다 | `ingestion/activity.py` (`IngestionActivityRegistry`) + `POST /internal/events/ingestion-state`·`/file-processed` | `run_watcher.trigger_ws_ingestion_state`·`trigger_ws_file_processed` | ✅ 닿는다 |
| 인제션 상태 어휘 | 「실행이 쓸 수 있는 상태 낱말」의 정본 하나 | `ingestion/file_ingestion_status.py` (32줄) | `directory_watcher` · `main.py` 어드민 로그 | ✅ 닿는다 |
| 원천 «없음» vs 「있는데 빔」 | 두 상태를 가르는 한 자리 | `server/listing_absence.py` (35줄) | 어드민 목록 응답 | ✅ 닿는다 |
| 외부 읽기 전용 소스 | 관리 워크스페이스 «밖»의 루트를 선언으로 붙이고 원본은 안 옮긴다 | `directory_watcher.validate_external_source_specs` · `SUPPORTED_EXTERNAL_PARSERS = {"voids_json"}` | `ingestion_settings.json.external_sources[]` (선언) | ✅ 닿는다 (파서 종류는 «하나»로 하드코딩 — §C-6) |
| 느린 선인출 실행계획 자동 인쇄 | 청크의 prefetch 가 임계를 넘으면 제품이 «스스로» EXPLAIN 을 찍는다(파일당 1회, ANALYZE 금지) | `directory_watcher._maybe_explain_slow_prefetch` + `_row_id_without_a_refresh` | `directory_watcher` 청크 루프 «한 자리», `try/except` 로 감싸여 있다 | ✅ 닿는다 · 🔵 09-16 장애의 수리가 착지해 있다 |
| 파일 업로드 인제션 | 브라우저/데스크톱이 파일을 직접 밀어 넣는다 | `POST /tables/{t}/upload` | `client2/src/main.js` · `desktop/desktop_wrapper.py` | ✅ 닿는다 |
| 인제션 로그·실패·재시도 | 적재 이력 조회 / 실패 목록 / 진행 중 / 재시도 | `GET /admin/file-ingestion/{logs,failed,active,workspaces}` · `POST /admin/file-ingestion/retry-failed` | `client2/src/admin.js` (File 탭) | ✅ 닿는다 |

---

## 2. 오토 업데이트 (스케줄러)

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 크론 스케줄러 | `ingestion_workspace/*/auto_update/*.py` 를 주석의 크론식으로 실행해 `raws/` 에 CSV 를 떨군다 | `server/run_auto_update.py` (`croniter`) | 명령줄(런처 자식). heartbeat `scheduler` | ✅ 닿는다 |
| 수집기별 on/off | 어드민이 쓰고 스케줄러가 «매 틱» 읽는다 — 재기동 없이 반영, 파일 부재 시 전부 active | `utils/auto_update_control.py` (`read_disabled_scripts`·`set_script_active`) + `config/auto_update_control.json` | `POST /admin/auto-update/toggle` · `run_auto_update` 루프 | ✅ 닿는다 |
| 상태 · 즉시 실행 | 스케줄 상태 조회 / 지금 한 번 돌리기(strict 토큰) | `GET /admin/auto-update/status` · `POST /admin/auto-update/run-now` | `client2/src/admin.js` (AutoUpdate 탭) | ✅ 닿는다 |
| 프록시 정책 확정 | 수집 스크립트가 볼 프록시 환경을 «이 프로세스»에서 정한다 — `*_proxy` 계열을 전부 걷어야 레지스트리가 산다 | `run_auto_update._apply_proxy_policy` | 스케줄러 기동 | ✅ 닿는다 |
| 주간 config 스냅샷 | 설정 파일을 파일당 스냅샷 + FIFO 보존. 30분마다 「때가 됐나」만 묻는다 | `server/config_backup.py` (`due`·`take_snapshot`·`run_scheduled`·`probe`) | 스케줄러 틱 · `runtime/health.probe_config_backups` · CLI `server/scripts/backup_config.py` | ✅ 닿는다 |
| 수집 스크립트 자체 | 외부/사내 시스템에서 긁어 CSV 를 만드는 코드 | `ingestion_workspace/*/auto_update/*.py` | 스케줄러가 «문자열 경로»로 로드 | 🔒 못 잰다 (gitignore) |

---

## 3. 인리치 (결손 보정)

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 규칙 로더/검증 | `enrichment_rules.json` 을 읽어 결정키·대상필드·참조뷰·집계를 검증. 모르는 키는 «이유를 대며» 거절 | `enrichment/config.py` (1,940줄 · `validate_enrichment_rules`) | 체인 로더 · 어드민 · 백필 | ✅ 닿는다 |
| dedup 파생 | 결정키로 묶어 파생 행을 만든다 | `enrichment/mapper.py` (`map_enrichment_dedup`) | 체인 규칙(선언이 «문자열»로 이름을 든다, 갈래 ③) | ✅ 닿는다 |
| 큐 분류 | 파생 행 중 「아직 못 채운 것」을 분류 | `enrichment/analysis.py` (`classify_queue`·`iter_derived_rows`) | 🔴 제품 경로 «0» — 오늘 부르는 곳은 CLI `server/scripts/enrichment_insights.py` 뿐 | ⚠️ 반쪽 (§A-7) |
| 큐 술어 (화면용) | 「어느 행이 아직 일이 남았나」를 **서버가** OR-of-blank 로 조립한다 | `GET /tables/{t}/data?enrichment_queue=<rule>` (`enrichment/config.py`) | `client2/src/enrichment_queue.js` → 소비자 **하나**(admin 결손 카운트). 그리드는 이 술어로 «좁히지 않는다» | ⚠️ 반쪽 |
| 후보 해석 | 참조뷰를 물어 대상 칸의 후보를 뽑고, 둘 이상이면 `REASON_AMBIGUOUS` 로 거절 | `enrichment/candidates.py` (`resolve_target_candidate`·`confirm_keys`·`AutoConfirmCollector`) | `builtin:auto_confirm` · 소급 `enrichment_confirm` | ✅ 닿는다 |
| 자동 확정 스윕 | 지지도 임계 위의 후보를 자동 확정. `apply` 는 체크포인트 없이는 «거절» | `enrichment/analysis.run_auto_confirm_sweep` | `GET /admin/enrichment/auto-confirm/dry-run` · 소급 op `enrichment_confirm` | ✅ 닿는다 |
| 룰 도입 «이전» 행의 파생 생성 | 소급 백필 | `enrichment/backfill.py` (`run_backfill`) | 소급 op `enrichment_backfill` · CLI `server/scripts/backfill_enrichment.py` | ✅ 닿는다 |
| 규칙·참조뷰 조회 | 규칙 목록 / 참조뷰 한 개 | `GET /enrichment/rules` · `GET /enrichment/rules/{rule}/references/{i}` | `client2/src/enrichment_reference_view.js` (메인 그리드 History 사이드바 «참조뷰» 탭) | ✅ 닿는다 |

---

## 4. 체인 (파생·연결)

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| outbox 소비 루프 | `LISTEN/NOTIFY` + 폴링으로 «자기가 소비할 수 있는 행만» 가져오고, 아무것도 안 한 틱도 양보한다 | `chain/ingestion_worker.py` (`start_chain_ingestion_worker`·`pending_chain_events`·`idle_wait`) | 명령줄 `run_chain_worker.py`. 손으로 띄운 uvicorn 에선 `main.startup_event` 가 인라인(그 경우 경고를 찍는다) | ✅ 닿는다 |
| 🔴 규칙 실행 «한 좌석» | 「이 규칙이 어느 문으로 가나」를 묻는 **유일한** 함수. 파일 맵퍼든 `builtin:` 이든 «한 모양»으로 답하고 «한 낱말»로 로그를 찍는다(`[ChainRule] rule= kind= rows_in= updates= written=`) | `chain/rule_run.py` (`run_rule`·`builtin_kind`·`chain_envelope`) | `ingestion_worker`(3자리) · `chain/replay.py`(2자리) | ✅ 닿는다 · 🔵 판정 420 착지 확인 — 두 문을 «직접» 부르는 곳은 `rule_run.py` 밖에 없다 |
| 파일 맵퍼 문 | 운영자가 쓴 모듈을 import 해 부른다 | `chain/mapper_call.py` (`execute_custom_mapper`) | `rule_run.run_rule` «하나» | ✅ 닿는다 |
| builtin 문 | 이 저장소가 소유한 이름표에서 찾아 부른다 — **종류 셋**: `builtin:join`(`virtual_join`) · `builtin:join_into` · `builtin:auto_confirm` | `chain/builtins.py` (`BUILTIN_KINDS`·`register_builtin`·`run_builtin`·`_install`) | `rule_run.run_rule` «하나» | ✅ 닿는다 |
| 통합 선언 확장기 | `derive:{kind: join\|decide}` + `on` + `into` 를 오늘의 평면 규칙으로 편다. 로더와 어드민 저장 관문이 **같은 확장기 하나**를 지난다 | `chain/rule_shape.py` (`expand_declaration`·`from_declaration`·`declared_kind`·`companion_rules`) | 체인 로더 · `POST /admin/chain/rules/raw` | ✅ 닿는다 |
| 규칙 순서·순환 | 순환을 «보고»한다(거절이 아니다 — 판정 402). 유한성은 최상단 `max_chain_depth` 가 맡는다 | `chain/rule_order.py` (`order_rules`·`cycle_note`·`say_cycle_once`) | 체인 로더 | ✅ 닿는다 |
| 규칙 인구조사 / diff | 선언 셋(평면·통합·합성)이 «어떤 규칙 집합»이 되는지 세고 before/after 를 비교 | `chain/rule_census.py` (`census`·`census_diff`·`describe`) | `GET /admin/chain/rules` · CLI `server/scripts/preview_unified_declarations.py` | ✅ 닿는다 |
| 조인 쓰기 | 선언이 말한 칸을 실제 컬럼에 «쓴다»(읽기 시점 조인과 다른 일) | `chain/join_into.py` (`run`·`join_spec`·`right_key`) | `builtin:join_into` | ✅ 닿는다 |
| 키 게이트 | 키 컬럼이 빈 행을 «이름 대고 세며» 건너뛴다 | `chain/key_gate.py` (`screen`·`refusals`·`note`) | `ingestion_worker` 쓰기 경로 | ✅ 닿는다 |
| 셀 층 철회 | 한 소스가 「더는 안 만드는 것」만 레이어에서 뺀다 | `chain/cell_layer.py` (`withdraw_source`) | `virtual_join/executor` · `chain/replay` | ✅ 닿는다 |
| 소급 재적용 (R1) | 규칙 하나를 페이징·페이싱으로 다시 돌린다. 멱등이 아니면 `force` 없이는 거절 | `chain/replay.py` (`replay_rule`·`replayable_rules_for`·`replay_is_refused`) | 소급 op `chain_replay` · `GET /admin/chain/rules/replayable` | ✅ 닿는다 |
| 활동 등록부 | 「이 규칙이 방금 뭘 했나」 — 두 문 «모두» 여기 기록된다 | `chain/activity.py` (`ChainActivityRegistry`·`running`) | `run_builtin` · `execute_custom_mapper` | ✅ 닿는다 |
| 대기열 가시화 | 막힌 머리·깊이·재시도를 값으로 낸다(목록은 200행에서 자르고 «잘렸다»고 말한다) | `GET /admin/chain/queue` (`_QUEUE_LIST_CAP`) · `QueueHeadWatch` | `client2/src/chain_queue_panel.js` | ✅ 닿는다 |
| 흐름 그림 | 선언 «넷»(chain·enrichment·virtual_join·ledger)을 한 그림으로. 로직 0 — 제품이 쓰는 로더로 읽기만 | `chain/graph.py` (`chain_graph`) → `GET /chain/graph` | `client2/src/admin.js` + `chain_graph.js` | ✅ 닿는다 |
| 맵퍼 시험 실행 | 규칙+표본 행 하나를 읽기 전용 연결에서 돌려 본다 | `POST /admin/chain/dry-run` → `admin/dev_bench.try_mapper` | 🔴 없음 | ⛔ §A-1 |
| 맵퍼 목록 | 이 배포가 아는 맵퍼(데코레이터 등록부 포함) | `GET /admin/mappers/list` | `client2/src/admin.js` (Chain 탭) | ✅ 닿는다 |
| 체인 맵퍼 본체 | 실제 파생 로직 | `server/mappers/*.py` | 체인 규칙이 «문자열»로 이름을 든다 | 🔒 못 잰다 (`.sample` 9개만 추적) |

---

## 5. 원장 — 번역 · 소급 · 철회

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 선언 로드 | `config/ontology/ledger_config.json` 하나에서 `entities`·`vocabulary`·`sources` 를 읽고, 소스마다 `relation`·`read`·`prepare`·`map`·`bind` 다섯 절을 검증 | `ledger/setup.py` (`load_setup`·`LedgerSetup`) | 번역기 · walk · 걷기 카탈로그 · 어드민 | ✅ 닿는다 |
| 쓰기 관문 | 분자(행/그룹) 단위로 원자를 검사하고 «이유를 대며» 거절. 거절은 세어진다 | `ledger/gate.py` (`screen_molecule`·`refuse`·`note`) | `ledger/runtime_v2` | ✅ 닿는다 |
| 원자 쓰기 | 커서 전진과 원자 삽입을 «한 트랜잭션»으로 | `ledger/store.py` (`LedgerStore.write_batch`·`withdraw`) | 🔴 정당한 호출자 `ledger/runtime_v2.py` «하나» + 씨앗 스크립트 **일곱** | ✅ / §C-2 |
| 번역 실행 | 커서 배치 미리보기와 «범위 한정» 실행 | `ledger/runtime_v2.py` (`preview_cursor_batch`·`execute_scoped_batch`) | `ledger/setup.preview_selected_cursor_batch`·`execute_selected_scoped_batch` | ✅ 닿는다 |
| **라이브** 번역 | 표가 써지면 그 행을 큐에 넣고, 체인 워커의 «페이싱된 별도 랩»이 빼서 번역한다 | `ledger/followup.py` (`enqueue`·`drain_once`·`queue_depth`·`base_tables_of`) | `chain/ingestion_worker.py`(`enqueue` 1자리 · `drain_once` 1자리) | ✅ 닿는다 |
| 전진 백필 | 커서 뒤 «전부»를 페이싱하며 번역 | `ledger/backfill.py` (`run`·`fetch_page`·`rows_not_yet_translated`) | 소급 op `ledger_backfill` · CLI | ✅ 닿는다 |
| 범위 재번역 | 회수+재생성을 «커서를 안 움직이고». 미리보기가 먼저 | `ledger/backfill.py` (`preview_rescope`·`rescope`·`count_orphan_atoms`) | 소급 op `ledger_rescope` | ✅ 닿는다 |
| 소스 단위 철회 | 「내 것 중 더는 안 만드는 것」만 뺀다 | `ledger/store.withdraw` · `chain/cell_layer.withdraw_source` | 소급 op `withdraw` | ✅ 닿는다 |
| 소급 등록부 | 실행 하나당 행 하나(`retroactive_runs`). 취소는 «협조적» — 행에 값을 세우고 도는 쪽이 배치 사이에서 묻는다. `runner` 가 「지금 누가 돌리나」에 답한다 | `admin/retroactive.py` (`OPERATIONS` **6종**: `chain_replay`·`withdraw`·`ledger_backfill`·`ledger_rescope`·`enrichment_backfill`·`enrichment_confirm`) | `GET /admin/retroactive/operations`·`{op}/count`·`runs` · `POST {op}/run`(strict)·`runs/{id}/cancel` | ✅ 닿는다 |
| 페이싱 프로파일 | 긴 작업이 옆 질의를 굶기지 않게 «쉬는 리듬»을 표 하나가 선언 | `server/pacing.py` + `server/pacing.json`(추적됨) | 원장 백필 · 체인 재적용 · 파일 인제션 · 원장 후속 랩 | ✅ 닿는다 |
| 결측 카탈로그 | 선언된 술어 × 엔터티를 순회해 「이 쌍이 원자를 하나도 안 만든다」를 찾는다. 이름은 `gap_names.json` 이 준다(표↔선언이 어긋나면 «양방향» 거절) | `ledger/gaps.py` + `ledger/gap_names.json` → `GET /api/ledger/gaps` | `client2/src/rnd_board/*` | ✅ 닿는다 |
| 선언 카탈로그 | 원장을 «한 줄도 안 읽고» 어휘·엔터티를 답한다 | `GET /api/ledger/declaration` | 보드 · 걷기 상자 | ✅ 닿는다 |
| 세션 계약 | SAVEPOINT 를 «여는 유일한 좌석» | `server/session_contract.py` (139줄, 2026-09-16 신설) | 쓰기 경로 | ✅ 닿는다 |
| 시각 렌더 정본 | naive 시각의 답이 «하나» | `server/utils/time_format.py` (219줄) | 응답·로그 | ✅ 닿는다 · ⚠️ `trace.py` 의 `display_timezone` 은 읽는 자 0 |

---

## 6. 걷기 / 서브그래프

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| walk | 마킹(`positive`/`negative`)을 씨앗으로 `follow` 로 좁힌 하위 그래프. `follow=inspected:x,y` 는 «씨앗과 키가 같은 노드»로만 걷는다. 못 맞추는 제약은 0이 아니라 **422** | `GET /api/ledger/subgraph` → `ledger_api/ledger_subgraph.py` (2,432줄) | `client2/src/rnd_board/api.js` (`fetchSubgraph` — `candidate`·`reach` 좌석) | ✅ 닿는다 |
| 씨앗 해석 | 접두어 «하나»만 받는다: `ledger-entity:v1:`. 나머지 철자는 «거절»(빈 그래프 아님) | `ledger_subgraph.decode_node_id` | walk | ✅ 닿는다 |
| 씨앗 노드 조립 | 씨앗 하나 → depth-0 노드 | `ledger_subgraph._seed_node` | walk | ⚠️ **여섯 갈래 중 다섯이 도달 불가** — §C-1 |
| 값 목록 | 「이 타입의 이 키에 오늘 «어떤 값»이 있나」. 그룹이 아니라 «행 수»를 자르고 절단을 둘로 나눠 보고 | `GET /api/ledger/key-values` | `client2/src/rnd_board/api.js` (`fetchKeyValues`) | ✅ 닿는다 · 🔴 **SSOT 가 모른다** (§D-1) |
| 경로 후보 | 선언에서 `from→to` 경로를 뽑아 `follow`·`hops` 를 채운다 | `client2/src/rnd_board/api.js` (`pathsBetween`·`typeGraph`) + `GET /api/ledger/declaration` | 걷기 상자 | ✅ 닿는다 (클라 절반) |
| 집계/그룹 | 노드를 축으로 묶고 median·mean·count 를 접는다 | `ledger_subgraph.group_nodes`·`_fold`·`AggregateRefused` | walk 응답 | ✅ 닿는다 |

---

## 7. 가상 조인 (읽기 시점 결합)

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 선언 로더/검증 | `virtual_join_rules.json` 을 읽고 검증 | `virtual_join/config.py` (1,115줄 · `JOIN_MAPPER="builtin:join"`) | 체인 로더 · 스키마 응답 · 어드민 | ✅ 닿는다 |
| 조회 시점 결합 | 그리드가 읽을 때 오른쪽 표의 값을 왼쪽 컬럼으로 노출 | `virtual_join/executor.py` (891줄 · `exposed_columns`·`resolved_expression`·`join_onclause`·`retract_rows`) | `main.py` 스키마/데이터 조립 · `database/config_watcher.py` | ✅ 닿는다 |
| 유일 키 보장 | 선언이 말한 유일 키를 «세우는» 껍데기 | `virtual_join/unique_key.py` (480줄) + `chain/builtins.ensure_declared_unique_keys` | 체인 기동 | ✅ 닿는다 |
| 거절 문장 | 왜 못 이었나를 «한 자리»에서 | `virtual_join/refusal.py` | 스키마/그리드 응답 | ✅ 닿는다 |
| 검증 리포트 | 「내 규칙이 서로 다른 두 로트를 하나로 합치지 않았나」 — 표 «안의 값»을 본다 | `GET /admin/config/virtual-join/verify` | `client2/src/join_verification.js` | ✅ 닿는다 |
| 가상 컬럼 쓰기 거절 | 가상 컬럼에 대한 쓰기를 깔때기 «하나»에서 막는다 | `crud.refuse_virtual_join_columns` | 모든 쓰기 경로 | ✅ 닿는다 |

---

## 8. 그래프 싱크 — ⚰️ **은퇴했다. 실행 코드가 «없다»**

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 그래프 머티리얼라이저 | (구) 행을 `graph_nodes`/`graph_edges` 사본으로 승격 | `run_graph_sync.py`·`graph_sync_worker.py`·`graph_materializer.py` — **셋 다 없다**(git grep 히트는 전부 주석·마이그레이션) | — | ⛔ 없음 |
| 옛 그래프 라우트 | (구) `/graph/*` 7종 + `POST /api/graph/sync` | 없다. 410 거절 스텁도 `8ffe23d7` 에서 삭제 | — | ⛔ 없음. `/api/*` 는 catch-all 의 차단 목록에 있어 **404**, `/graph/*` 는 SPA 폴백이라 **index.html 200** |
| 부기 컬럼 셋 | `is_graph_synced`·`needs_graph_rollback`·`graph_synced_at` — 이미 있는 표에 «그대로» 있고 스키마 응답에도 실린다 | `models.FRAMEWORK_COLUMNS` | 걸러 내는 자리 넷(서버 둘 · 클라 둘) | ⚠️ 잔해 — §C-5 |
| 저장소 폐기 | 표 셋 DROP + 역방향 | `migrations/drop_graph_storage.py` · `..._reverse.sql` | 운영자 CLI | ✅ (명령줄, 갈래 ④) |
| 클라 진입점 | (구) 선택 행 → 그래프 동기화 버튼 | `client2/src/main.js` `GRAPH_SYNC_RETIRED = true` 뒤의 죽은 블록 | 없음 — 상수가 항상 참이라 핸들러가 «등록되지 않는다» | ⛔ 잔해(요청은 안 나간다) |

---

## 9. 어드민 API

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 토큰 게이트 | `ASSY_ADMIN_TOKEN` + `X-Admin-Token`(ASCII 전용). 미설정 시 **fail-closed 셋**만 503, 나머지는 열린다 | `server/admin/auth.py` (463줄 · `require_admin_token`·`require_admin_token_strict`) | 42(main.py) + 15(탐색기) 라우트 | ✅ 닿는다 |
| 선언 원문 읽기/쓰기 | `table_config` · `chain_rules` · `ledger_config` 원문. 저장은 `ledger/admin.py` 가 하고 **삭제는 없다**, `init_dynamic_models` 를 여기서 «안» 부른다(그 일은 config_watcher 몫 — 두 번째 문 금지) | `GET/POST /admin/tables/config/raw` · `GET/POST /admin/chain/rules/raw` · `GET /admin/ledger/config/raw` | `client2/src/admin.js` (Monaco 편집기) | ✅ 닿는다 |
| 설정 해석 리포트 | 「내 선언이 먹었나」 — DB 질의 0건이 계약 | `server/config_resolve_report.py` → `GET /admin/config/resolve` | `client2/src/config_resolve_view.js` | ✅ 닿는다 |
| 표기 정규화 미리보기 | 「내 규칙이 서로 다른 둘을 한 병합군으로 만들지 않았나」 — 표 안의 값을 본다 | `server/notation_norm.py` → `GET /admin/config/notation/preview` | 🔴 없음 | ⛔ §A-2 |
| 원장 소스·관계 | 선언된 소스/관계 목록 | `GET /admin/ledger/sources` · `/admin/ledger/relations` | `client2/src/ledger_sources_panel.js` | ✅ 닿는다 |
| 아웃박스 실패·재시도 | 실패 목록과 일괄 재시도 | `GET /admin/outbox/failed` · `POST /admin/outbox/retry-failed` | `client2/src/admin.js` | ✅ 닿는다 |
| 스크립트 열람/수정 | 워크스페이스 파서/수집기 코드를 브라우저에서 (쓰기는 strict) | `GET/POST /admin/scripts/{list,code}` | `client2/src/admin.js` (Monaco, `#editor=<path>` 딥링크) | ✅ 닿는다 |
| 무중단 리로드 | `SYSTEM_RELOAD` outbox 이벤트를 적재해 모든 워커에 전파 | `runtime/system_reload.py` → `POST /admin/reload-configs` | `client2/src/admin.js` | ✅ 닿는다 |
| 전사 계획 dry-run | 저장 전에 「어느 철자가 이겼나」까지 답한다(행 조회 0) | `GET /admin/transfer-plan/dry-run` | `client2/src/admin.js` | ✅ 닿는다 |
| 온톨로지 탐색기 15종 | 뷰·컬럼 통계·작성 스키마·계획·삭제 미리보기·시험 실행·초안 CRUD/검토/개정/발효·선언 삭제 | `ledger_api/ontology_config_explorer_router.py` + `ledger/config_{authoring,explorer,explorer_service,drafts}.py`·`implementations.py`·`column_stats.py`·`ledger_skeleton.json` | `client2/src/ontology_explorer{,_store,_view}.js` — **15 전부** | ✅ 닿는다 |
| 런타임 고리 값 | 고리 아홉이 «마지막으로 무엇을 했나» — 값만. 판정은 `/health` | `runtime/loops.py` → `GET /runtime` | `client2/src/admin.js` + `runtime_panel.js` | ✅ 닿는다 |
| 개발 벤치 | 맵퍼를 읽기 전용 연결에서 시험 | `admin/dev_bench.py` (`try_mapper`) | `POST /admin/chain/dry-run`(화면 0) · pytest 픽스처 · CLI | ⚠️ 반쪽 |
| 감사 캐시 | 트랜잭션당 500건 상한의 인메모리 이력 | `admin/audit_cache.py` (`add_logs_batch`) | `POST /internal/events/batch-refresh` | ✅ 닿는다 · §C-3 |

---

## 10. 실시간 전파 (WebSocket)

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| WS 허브 | 연결 관리 + 브로드캐스트 | `main.py` `class ConnectionManager` · `WS /ws` | `client2/src/websocket.js` (메인 그리드 «전용») | ✅ 닿는다 |
| 브로드캐스트 발신 | 쓰기·삭제·소스변경·핀·업로드 등에서 20 자리가 `manager.broadcast` 를 부른다 | `server/main.py` | 각 라우트 핸들러 | ✅ 닿는다 |
| 워커 → 허브 중계 | 다른 프로세스가 임의의 WS 메시지를 밀어 넣는다 | `POST /internal/events/broadcast` | `chain/ingestion_worker`(2자리) · `admin/retroactive`(1자리) | ✅ 닿는다 |
| 배치 갱신 통지 | 「표 N 행이 바뀌었다」 + 감사 로그 동봉(500 절단, 총건수 별도) | `POST /internal/events/batch-refresh` | `run_watcher.trigger_ws_refresh` | ✅ 닿는다 |
| 파일 처리 완료 통지 | 성공/실패 + 사유 | `POST /internal/events/file-processed` | `run_watcher.trigger_ws_file_processed` | ✅ 닿는다 |
| 인제션 상태 통지 | heavy 레인 QUEUED/PROCESSING/FINISHED (WS 안 탄다 — admin active 전용) | `POST /internal/events/ingestion-state` | `run_watcher.trigger_ws_ingestion_state` | ✅ 닿는다 |
| 메시지 봉투 정본 | 아홉 발신자가 손으로 짓던 dict 를 «한 함수»가 짓는다 | `server/event_constants.py` (`batch_refresh_message`·`file_ingestion_completed_message`·`progress_event`) | 내부 라우트 · 인라인 워처 · 워처 진행 | ✅ 닿는다 · §C-3 |
| 미배달 마커 | 통지가 실패하면 durable 마커를 남기고, 체인 워커의 스윕이 줍는다 | `server/internal_event_client.py` (359줄 · `send_internal_event`·`record_undelivered_notification`) | `run_watcher` · `chain/ingestion_worker` · `admin/retroactive` | ✅ 닿는다 |
| 맵 에디터 | 🔴 **WS 를 «안 쓴다»** — REST + `localStorage` 로 동기화 | `client2/src/map_editor.js` | — | (SSOT §6 의 정정과 «일치») |

---

## 11. 백업 / 복원

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 주간 config 스냅샷 | 파일당 스냅샷 + FIFO 보존 + 동일 바이트면 안 뜬다 | `config_backup.take_snapshot`·`_prune`·`due` | `run_auto_update` 틱(30분마다 「때가 됐나」) | ✅ 닿는다 |
| 백업 건강 프로브 | 「스냅샷이 신선한가」 ok/stale/missing/unknown | `config_backup.probe` → `runtime/health.probe_config_backups` → `GET /health` | `/health` | ✅ 닿는다(청중은 바깥 모니터 — §A-6) |
| 수동 백업 | 지금 한 번 | CLI `server/scripts/backup_config.py` | 명령줄(갈래 ④) | ✅ 닿는다 |
| 🔴 복원 | **없다.** 모듈 머리글이 스스로 적는다 — 「`git` 은 복원 경로가 아니다 · 롤백 절차 2단계는 «파일을 복사»하는 것」 | — | — | ⛔ 기능 자체가 없음 — 운영자가 손으로 복사 (§A-8) |
| 초안 저장 시 백업 | 선언을 덮어쓰기 전에 같은 백업 디렉터리에 한 겹 | `ledger/config_drafts.py`·`ledger/admin.py` (`config_backup.backup_dir_for`) | 어드민 저장 경로 | ✅ 닿는다 |

---

## 12. 표 카탈로그 / 스키마 관리

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 동적 모델 빌드 | `table_config.json` → SQLAlchemy Table → ORM 매핑. 기존 표에 컬럼이 늘면 «핫스왑» | `database/models.py` (`init_dynamic_models`·`refresh_dynamic_models`·`FRAMEWORK_COLUMNS`) | 네 프로세스 전부가 기동 시 | ✅ 닿는다 |
| 물리 DDL 동기화 | 선언에 있는데 DB 에 없는 컬럼을 `ALTER TABLE` 로 | `models.sync_dynamic_tables_schema` | `run_watcher`·`run_chain_worker` 기동 · `config_watcher` | ✅ 닿는다 |
| 설정 파일 감시 | `config/*.json` 변경을 파일 경계에서 핫리로드 | `database/config_watcher.py` (`start_config_watcher`) | `main.startup_event` | ✅ 닿는다 |
| 스키마 드리프트 점검 | 「코드가 요구하는 스키마 ↔ 실제 DB」. **열이 «뷰»인 경우**까지 가른다 | `admin/schema_drift.py` (864줄 · `run_at_startup`·`check`·`banner_lines`) | `main.startup_event` · CLI `server/scripts/check_schema_drift.py` | ✅ 닿는다(화면은 «기동 배너» — §A-9) |
| 제품 소유 표 선언 | 「이 표는 제품 것이다」의 정본 | `server/product_tables.py` (`effective_declaration`) | `config_backup` · `map_overlay` · 설치 CLI | ✅ 닿는다 |
| 스키마 응답 | 그리드가 쓰는 컬럼·타입·가상 컬럼 | `GET /tables/{t}/schema` | `client2/src/api.js` | ✅ 닿는다 |
| 표 목록 | | `GET /tables` | `client2` | ✅ 닿는다 |

---

## 13. 액션 발급 (결손 보정 행위)

> 🔴 **「액션」이 이 저장소에서 «두 가지»를 가리켰고, 하나는 죽었다.**

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 후보 확정(= 오늘의 액션) | 참조뷰를 물어 대상 칸의 값을 «확정»한다. 애매하면 거절하고 센다 | `enrichment/candidates.confirm_keys`·`resolve_target_candidate` | `builtin:auto_confirm` (체인) · 소급 `enrichment_confirm` · dry-run 라우트 | ✅ 닿는다 |
| 자동 확정 스위치 | 전역 노브 + 규칙별 노브. 꺼져 있으면 실행 버튼을 «거부»하고 사유를 준다(`auto_confirm_off`) | `candidates.global_auto_confirm_enabled`·`rule_auto_confirm_enabled` | 소급 등록부 | ✅ 닿는다 |
| ⚰️ `Enrich Action` 노드 | (구) walk 에서 「채워야 할 것」을 «노드로» 세우고 `needs_enrichment` 로 도달 | `ledger_subgraph._seed_node` 의 `kind=="action"` 가지 + `_enrich_action_node` | 🔴 **없다** — `action_lookup` 을 넘기는 호출자가 «0»(항상 `None`), 그리고 `decode_node_id` 가 그 철자의 씨앗을 «거절»한다 | ⛔ 도달 불가 — §C-1 |
| ⚰️ `claim_contract` | (구) 인리치 결과를 원장 주장으로 내보내는 선언 | `enrichment/config.py` | 🔴 **은퇴**(S-184 · 판정 295) — 선언하면 삼키고 «거절 목록에 적는다» | ⛔ 은퇴 · §D-2 |
| ⚰️ `enrichment_actions.py` | (구) 액션 발급 모듈 | **파일이 없다**(`server/_archive/` 에도 없다 — 그 디렉터리엔 `tests/` 뿐) | — | ⛔ 없음 · §D-4 |

---

## 14. 그 밖 — 표 편집 · 이력 · 계기 · 맵 · 관측

| 기능 | 무엇을 하나 | 라우트/모듈 | 누가 부르나 | 배선? |
|---|---|---|---|---|
| 통합 배치 업서트 | 수동편집·인제션·맵저장이 «한 문»으로 들어온다 | `PUT /tables/{t}/data/updates` → `crud.apply_batch_updates` | 그리드 · 맵 에디터 · 워처 · 체인 | ✅ 닿는다 |
| 다중 소스 레이어링 | 한 칸에 여러 출처를 겹쳐 두고 전순서로 이긴 값을 낸다. **빈 칸은 층이 아니다**(판정 405) | `crud.compute_priority_value`·`resolve_priority_map`·`can_mean_emptied` | 모든 읽기/쓰기 | ✅ 닿는다 |
| 소스 조회·핀·삭제 | 칸 단위 + 배치 | `GET/DELETE .../sources`·`PUT .../priority`·`PUT .../cells/priority/batch`·`POST .../cells/sources/{delete/batch,query}` | `client2/src/main.js` | ✅ 닿는다 |
| 변경 이력 | 행/셀 계보 + 트랜잭션 묶음 + 최근 목록(절단 헤더 포함) | `GET /tables/{t}/rows/{id}/history`·`.../cells/{col}/history`·`/audit_logs/recent`·`/audit_logs/transaction/{tx}` | `client2/src/timeline.js` | ✅ 닿는다 |
| 상호작용 공수 계기 | 핵심가치 #1 의 정본 계기 — 키1·마우스3·화면이동5. 무변경 저장은 `effort_recorded:false` | `server/effort_metric.py` + `PUT .../data/updates` 의 선택 필드 · `GET /api/effort/config` · `/dashboard/summary` | `client2/src/effort_meter.js` | ✅ 닿는다 |
| 값 제안 | 셀 편집 중 후보 목록 | `GET /tables/{t}/columns/{col}/values` → `server/value_suggest.py` | `client2/src/value_suggest.js`·`map_editor.js` | ✅ 닿는다 |
| 좁히기 · 개수 | 조회와 개수가 «한 조립»을 지난다(두 벌이면 두 수가 갈리고 오류가 안 난다) | `GET /tables/{t}/data` · `/data/count` · `server/column_filter.py`·`keyset_scan.py` | `client2/src/api.js` | ✅ 닿는다 |
| 맵 오버레이 | 임의 맵을 타깃 맵 프레임 좌표로 정렬해 돌려준다(셀 상한 필수) | `server/map_overlay.py` (2,744줄) → `GET /api/maps/overlay` | 🔴 없음 | ⛔ §A-3 |
| 페인트 잠금 선언 | 어느 칸을 못 칠하나 + per-table 좌표 바인딩 | `GET /api/maps/paint-rules` | `client2/src/map_editor.js`·`map2/api.js` | ✅ 닿는다 |
| 프레임 정렬 채점 | 순번·방향·그룹·bin 지문·배치 다섯 축으로 «점수»를 낸다 | `server/map_alignment.py` (6,468줄) · `alignment_view_service.py` → `GET /api/maps/alignment/{view,worklist,references}` | `client2/src/map2/*` | ✅ 닿는다 |
| 정렬 확정 기록 | 확정을 append-only 로 남긴다 | `server/maps/frame_confirmation.py` · `migrations/add_frame_confirmation.py` → `POST /api/maps/alignment/confirm` | `client2/src/map2/*` | ✅ 닿는다 |
| 맵 프리셋 | 웨이퍼 물리 규격 프리셋 CRUD | `GET/POST /map-presets`·`/api/map-presets` · `DELETE .../{key}` | `client2/src/map_editor.js` | ✅ 닿는다 · §C-4 |
| 프리셋 라우팅 | 어느 표가 어느 프리셋을 쓰나 | `server/maps/preset_routing.py` → `GET /api/maps/preset-routing` | `client2/src/map_editor.js` | ✅ 닿는다 |
| 전사 계획 | stage 선언 · 가용 집계 · 검증. 계획 정체성 = `(ref_table, map_key)` | `server/transfer_plan.py` (3,731줄) → `GET /api/transfer-plan/{stages,source-summary,validate}` | `client2/src/transfer_plan.js` | ✅ 닿는다 |
| 본딩 계획 코어 집계 | 코어 웨이퍼 집계(역할 바인딩) | `server/bonding_plan.py` (1,049줄) → `GET /api/bonding-plan/core-summary` | 🔴 없음 (`bonding_plan` 모듈 자체는 어드민 거절 문장에서 쓰인다) | ⛔ §A-4 |
| DT/core 프레임 유도 | 프레임 «어휘»와 축 방정식 | `server/dt_map_derivation.py`(1,020줄)·`dt_frame_transform.py` | 체인 맵퍼(.sample) · 정렬 | ✅ 닿는다 |
| 프로세스 감독 | 자식 기동·포트 점유 판별·재시작 정책·stdout tee | `runtime/process_supervisor.py` (1,116줄) + `launcher_specs.py` | `run_decoupled_app.py` | ✅ 닿는다 |
| 심박 · 명부 | 워커 진척 비트 + 작업 단위 claim + 명부 발행 | `utils/heartbeat.py` (371줄) | 워처·체인·스케줄러 · `/health` | ✅ 닿는다 |
| 건강 판정 | 순수 함수 판정표 + config 백업 프로브 | `runtime/health.py` (498줄) → `GET /health` (무인증) | 🔴 client2 «0» — 의도된 것(판정 2026-09-06 「A」: 청중은 바깥 모니터) | ⚠️ 의도된 반쪽 — §A-6 |
| DB 안전 가드 | 시험 프로세스 · 운영자 읽기 전용 경로가 「만지면 안 되는 것」에 못 닿게 | `server/db_safety.py` (453줄) | 시험 conftest · dev bench | ✅ 닿는다 |
| 정적 서빙 격리 | SPA catch-all. 경로가 `tables/ws/audit_logs/dashboard/admin/map-editor/map_editor/map-presets/enrichment/ api` 로 시작하면 **404**, 그 밖엔 resolve 후 dist 안인지 확인 | `main.serve_static_or_index` | 브라우저 | ✅ 닿는다 |
| 데스크톱 배포 | 셸 실행파일 내려받기 | `GET /api/download/client`(index.html 의 `<a href>`) · `GET /api/desktop/download`(`main.js`) | 둘 다 화면에서 | ✅ 닿는다 |

---

# A. 「UI 가 없는 기능」 — 서버는 할 줄 아는데 닿는 화면이 없다

> 판정 기준: `client2/src/**` · `client2/*.html` · `client2/dist/**` · `desktop/desktop_wrapper.py`
> 전부에 대해 그 경로/심볼을 훑었고, **네 갈래를 뺀 뒤에도** 0인 것만 올렸다.

| # | 기능 | 어디 | 오늘 부를 수 있는 길 | 무게 |
|---|---|---|---|---|
| A-1 | **맵퍼 시험 실행** | `POST /admin/chain/dry-run` → `admin/dev_bench.try_mapper` | CLI · pytest 픽스처 | 🔴 크다 — Chain 탭에 규칙 폼이 있는데 「돌려 보기」가 화면에 없다. 라우트가 「세 답이 하나여야 한다」고 자기 docstring 에 적고도 그 «하나»가 화면에서 안 보인다 |
| A-2 | **표기 정규화 미리보기** | `GET /admin/config/notation/preview` → `server/notation_norm.py`(910줄) | 없음 | 🔴 크다 — 핸들러 docstring 이 「파생 컬럼이 사라져 운영자가 «눈으로» 보던 수단이 없어졌고 그 손실은 갚아야 한다」고 적고 있는데, 갚을 자리가 화면에 «없다» |
| A-3 | **범용 맵 오버레이** | `GET /api/maps/overlay` → `server/map_overlay.py`(2,744줄) | 없음 | 🔴 크다 — SSOT §6·SYSTEM_FLOWS ⑭ 둘 다 「서버+클라」로 적는다. 클라 절반이 «없다» |
| A-4 | **본딩 계획 코어 집계** | `GET /api/bonding-plan/core-summary` → `server/bonding_plan.py`(1,049줄) | 없음 | ⚠️ 중간 — 모듈은 어드민 거절 문장(`explain_binding_refusal`)으로 «다르게» 쓰인다 |
| A-5 | **표 CSV 내보내기 · 타깃 row_id 스캐너 · 단일 행 조회** | `GET /tables/{t}/export` · `POST /tables/{t}/row_ids/target` · `GET /tables/{t}/{row_id}` | 없음 | ⚠️ 중간 — `export` 는 상한 초과 시 «자르지 않고 413» 이라는 좋은 규율을 들고 있는데 누르는 자리가 없다 |
| A-6 | **`/health` 판정** | `GET /health` → `runtime/health.py`(498줄) | 바깥 모니터 | ✅ **의도된 것** — 소유자 판정 2026-09-06 「A」. 여기 적는 이유는 「없는 것」과 「일부러 없는 것」이 같은 모양이기 때문이다 |
| A-7 | **인리치 큐 분류** | `enrichment/analysis.classify_queue` | CLI `server/scripts/enrichment_insights.py` | ⚠️ 중간 — 워크리스트 화면이 2026-08-11 에 삭제되면서 제품 경로가 끊겼다. 남은 화면 소비자는 admin 결손 «카운트» 하나 |
| A-8 | **config 복원** | 없음(백업만 있다) | 운영자가 손으로 파일 복사 | 🔴 크다 — 모듈이 「`git` 은 복원 경로가 아니다」라고 적어 두고 «제품 안의 복원 경로»는 안 만들었다. 되돌릴 수 있게 만드는 것이 「변경 비용을 싸게」의 직접 항목이다 |
| A-9 | **스키마 드리프트 판정** | `admin/schema_drift.py`(864줄) | 기동 배너 + CLI | ⚠️ 중간 — 운영 로그를 붙일 수 없는 환경에서 «기동 순간»에만 보인다 |

---

# B. 「기능이 없는 UI」 — 화면이 부르는데 서버에 없거나 항상 거절한다

| # | 화면 | 부르는 주소 | 오늘 서버의 답 | 근거 |
|---|---|---|---|---|
| B-1 | **R&D 보드 — 맵 좌석** (`part === 'map'`, `legacyRoute: 'map'`) | `GET /api/ledger/lot_map` | **404** (`/api` 접두는 catch-all 차단 목록) | `client2/src/rnd_board/api.js` `ROUTES.lotMap`·`fetchLotMap` ← `main.js`(3자리). 서버의 `/api/ledger` 라우트는 `subgraph`·`key-values`·`gaps`·`declaration` **넷뿐** |
| B-2 | **자재 정보 · 펼친 층 · 머리 요약** (`legacyRoute: 'wafer_process'` 기본값) | `GET /api/ledger/composition` | **404** | `composition_panel.js`·`expanded_layer_panel.js`·`head_summary_panel.js` 가 «기본값»으로 이 좌석을 든다 |
| B-3 | **기반 위치 수** (`legacyRoute: 'basis'`) | `GET /api/ledger/composition` | **404** | `main.js` |
| B-4 | **기본 트렌드** (`legacyRoute: 'trend_y'`) | `GET /api/ledger/trends` | **404** | `api.js` 의 주석이 이 404 를 «이름 붙은 기다림»으로 스스로 적어 두었다(「Y축이 집계를 고르게 되면 걷기로 간다」) — 즉 **알고 있는 반쪽**이다 |
| B-5 | **또래 수** (`legacyRoute: 'peer'`) | `GET /api/ledger/siblings` | **404** | `main.js`·`api.js` |
| B-6 | (참고) 그래프 동기화 버튼 | `POST /api/graph/sync` | 404 | `client2/src/main.js` — 다만 `GRAPH_SYNC_RETIRED = true` 가 핸들러 «등록 자체»를 막아 **요청은 나가지 않는다**. B 가 아니라 ③ 잔해 |

🔴 **B-1~B-5 는 다섯 좌석이 아니라 «네 라우트»다.** 은퇴는 2026-08-28(개정 6)에 일어났고
보드의 `LEGACY_ROUTES` 표가 그때 «남겨졌다». `trend_y` 만 사유가 적혀 있고 나머지 넷은 사유가 없다.
⚠️ 이 다섯은 **보드 페이지(`rnd-board.html`)** 에만 있고 nav 링크가 없어 «직접 열어야» 보인다 —
그래서 조용하다. 조용한 것이 고쳐졌다는 뜻은 아니다.

---

# C. 🔴 「같은 기능에 두 경로」 — 판별식은 「둘이 있나」가 아니라 **「둘이 «갈라질 수» 있나」**

| # | 무엇이 둘인가 | 갈라질 수 있나 | 실측 |
|---|---|---|---|
| **C-1** | **걷기의 씨앗 노드 조립** — `_seed_node` 가 `entity`·`event`·`claim`·`point`·`collection`·`action` **여섯 갈래** | 🔴 **갈라지지 않는다. 다섯이 «죽어 있다»** | `seed_refs` 를 만드는 자리는 `decode_node_id` «하나»이고, 그 함수는 `ledger-entity:v1:` 이면 `kind:"entity"` 를 내고 **그 밖은 던진다**. 따라서 나머지 다섯 갈래·`action_lookup`(넘기는 호출자 0, 항상 `None`)·`ref["kind"]=="action"` 판정·`enrich_actions` 응답 칸이 전부 도달 불가. 같은 파일의 `terminal_finding_point_projection` 도 여기 산다. **CLAUDE.md 가 2026-09-06 에 「여섯 중 다섯」으로 적은 그 자리이고, 오늘도 그대로다** |
| **C-2** | **원장에 원자를 쓰는 문** — ① `ledger/runtime_v2.py`(선언→관문→store) ② 씨앗 스크립트가 `store.write_batch` «직접» | 🔴 **이미 갈라져 있다** | 직접 호출 **일곱**: `seed_syn_{complex_composite,composite_chip,journey_atoms,lot_excursion,process_ledger,split_merge_pressure,world}.py`. 둘째 문으로 들어온 원자는 **선언이 이름을 모르므로 walk 의 주어가 못 된다** — 오류는 안 난다. 상설 「표에 원천 데이터를 넣고 그걸로 원장」의 위반이고, `server/scripts/generate_source_rows.py` 가 그 규율을 자기 머리글에 적고 있다 |
| **C-3** | **워처 → 「표가 바뀌었다」 통지** — ① 분리 모드: `run_watcher.trigger_ws_refresh` → `POST /internal/events/batch-refresh` → 핸들러가 `event_constants.batch_refresh_message(..., total_log_count=...)` + `audit_cache.add_logs_batch` ② 단일 프로세스 모드: `main.startup_event` 안의 «같은 이름» `trigger_ws_refresh` → 같은 빌더를 `total_log_count` **없이** 부르고 `audit_cache` 를 **안 먹인다** | 🔴 **이미 갈라져 있다** | 봉투 빌더는 «하나»로 접혔지만(판정 427) **인자가 두 벌**이다. 단일 프로세스 모드에서 트랜잭션 총건수가 사라지고 감사 캐시가 인제션으로 안 채워진다. 두 모드 다 코드가 지지하는 모드다(`main.py` 가 인라인 모드에 경고를 찍을 뿐 막지 않는다) |
| **C-4** | **행 삭제** — ① `DELETE /tables/{t}/rows/{row_id}` ② `POST /tables/{t}/rows/batch_delete` | 🔴 **이미 갈라져 있다 (그리고 ①은 화면 0)** | `crud` 층은 하나로 접혀 있다(`delete_row` → `delete_rows_batch`). 갈라진 것은 **라우트 층**: ①은 `user_name` 을 «안 넘겨» 감사 로그가 `"system"` 저자로 남고, 브로드캐스트에 `updated_by`·`created_logs` 를 «안 싣는다». ②는 둘 다 싣는다. 같은 `batch_row_delete` 이벤트를 받는 클라가 한쪽에서만 `created_logs` 를 얻는다. **①을 부르는 화면은 오늘 0** |
| **C-5** | **은퇴한 그래프 컬럼 셋을 거르는 자리** — `models.FRAMEWORK_COLUMNS` 상수가 «있는데» `main.py` 두 자리와 `client2/src/grid.js`·`push_columns.js` 가 세 이름을 **손으로 다시 적는다** | ⚠️ 갈라질 수 있다 | 컬럼이 하나 더 은퇴하거나 이름이 바뀌면 네 자리를 각자 고쳐야 하고, 안 고친 자리는 «오류 없이» 그 컬럼을 그린다. 정본이 이미 있으므로 비용이 작다 |
| **C-6** | **외부 읽기 전용 파서 종류** — `SUPPORTED_EXTERNAL_PARSERS = frozenset({"voids_json"})` | ⚠️ 하드코딩 | 워크스페이스 파서는 «선언»으로 늘어나는데 외부 소스 파서는 코드의 집합이 정한다. 둘째가 필요해지는 날 「선언으로 못 적는다」가 된다 (판별식 ②: 「이 값을 사용자가 적을 수 있나」) |
| — | (참고) `/map-presets` vs `/api/map-presets` | ✅ **갈라질 수 없다** | 6 데코레이터가 `_save_map_preset_impl`·`_delete_map_preset_impl` 과 공유 GET 핸들러 **셋**으로 모인다. 주소가 둘이지 좌석이 둘이 아니다 |
| — | (참고) 체인 맵퍼 문 둘 | ✅ **갈라질 수 없다 (2026-09-16 수리 착지)** | `chain/rule_run.run_rule` 이 「어느 문이냐」를 묻는 **유일한** 자리이고, `execute_custom_mapper`·`run_builtin` 을 직접 부르는 제품 코드는 그 파일 «밖에 없다». 로그도 `[ChainRule]` 한 접두로 접혔다. 판정 420 |

---

# D. 문서 ↔ 코드가 어긋난 자리 — **조용히 우회하지 않고 적는다**

| # | 문서가 말하는 것 | 오늘의 코드 | 크기 |
|---|---|---|---|
| **D-1** | `SYSTEM_OVERVIEW §8`: 「`GET /api/ledger/*` 는 **라우트가 «셋»**(subgraph·declaration·gaps)」 · `CODE_MAP §5-H` 도 「라우트는 «셋»이다」 | **넷이다.** `GET /api/ledger/key-values` 가 `trace_router.py` 에 있고 보드(`fetchKeyValues`)가 «부른다». 두 문서 어디에도 없다 | 🔴 SSOT 의 «수»가 틀렸다. SSOT 는 스스로 「상충하면 이 문서가 우선한다」고 적는 문서라, 틀린 수가 「믿으라」고 지시한다 |
| **D-2** | `SYSTEM_OVERVIEW §5`: 「…선택적 `claim_contract`는 **결손 공급 계약**」 | **은퇴했다**(S-184 · 판정 295). `enrichment/config.py` 가 선언을 «삼키고» `RETIRED_CLAIM_CONTRACT_NOTE` 로 경고 + 거절 목록에 기록한다 | 🔴 운영자가 「선택적으로 쓸 수 있다」로 읽는다 |
| **D-3** | `CODE_MAP §3-bis`: 「[§3]의 트리 인제션이 나르는 경로를 **소비하는 쪽이 여기다**」(`AdvancedIngester`) | **워처 경로에 없다.** `directory_watcher` 가 `advanced_ingester` 를 부르는 자리는 «주석 한 줄»뿐이고, 파서 선택은 `_discover_and_execute_pipeline`(커스텀) → `_try_std_parse`(폴백) 둘이다. 추적 트리의 호출자는 시험 하나 | ⚠️ 「경로가 이어져 있다」로 읽히는데, 실제 소비자는 gitignore 밖의 운영자 스크립트다 |
| **D-4** | `SYSTEM_OVERVIEW §6` Enrichment Queue 행이 코드로 드는 것: `enrichment_actions.py` · `client2/src/enrichment.js` | **둘 다 파일이 없다.** `server/_archive/` 에도 없다(그 디렉터리엔 `tests/` 만). `CODE_MAP §5-H` 의 「`server/_archive/`로 이동했다」도 오늘 거짓 | ⚠️ 삭제를 「이동」으로 적으면 찾으러 간 사람이 못 찾는다 |
| **D-5** | `SYSTEM_OVERVIEW §8`: 어드민 게이트를 세는 술어는 `grep -cE '^@app\.(get\|post\|put\|delete\|patch)\("/admin' server/main.py` | 그 술어는 **`/admin` 접두가 아닌 게이트 둘을 못 본다** — `GET /chain/graph` · `GET /runtime`. 둘 다 `require_admin_token` 을 단다 | ⚠️ 「수를 적지 않는다」는 규율은 옳은데 «세는 술어»가 두 개를 흘린다 |
| **D-6** | `GET /api/ledger/subgraph` 의 `id` 파라미터 설명: 「Entity/Event/Claim/Collection/Point/Value/**Action**의 불투명 id」 | `decode_node_id` 는 `ledger-entity:v1:` **하나**만 받고 나머지는 «던진다». 그 목록의 여섯은 2026-08-28 에 은퇴했다 | 🔴 **API 문서 자체가 거짓 문장**이다(깔끔 ①: 「이 줄이 «참»인가」). OpenAPI 로 나가는 줄이라 «바깥»이 읽는다 |
| — | `SYSTEM_OVERVIEW §2`: 「백엔드 자식은 «넷»」 · 「맵 에디터는 WS 가 아니라 REST+localStorage」 · 「`/api/graph/sync` 만 404, `/graph/*` 는 index 200」 | ✅ **셋 다 오늘도 참** (`launcher_specs.child_specs()` · `map_editor.js` · `serve_static_or_index` 의 차단 목록) | — |
| — | `SYSTEM_FLOWS §2-bis`: 「`/health` 를 client2 에서 부르는 곳이 0」 | ✅ **오늘도 참** — 클라에 `/health` 는 «주석 둘»뿐 | — |

---

# E. 🔴 못 잰 것 — 0 으로 «가정하지 않는다»

```
E-1  server/mappers/*.py            추적 9(.sample 뿐) · 실물은 gitignore(.gitignore:75)
     => 체인 맵퍼가 «몇 개인지 · 어떤 종류인지 · @mapper 데코레이터를 몇이 쓰는지» 모른다.
        2026-09-07 에 이 자리를 평문 grep 으로 재서 「소비자 0」이라 답했다가 소유자가
        「운영에서 @mapper 로 했다니까」로 정정했다. 그 실패를 여기 다시 적는다

E-2  server/config/*.json           추적 22(.sample + pacing 계열) · 실물은 gitignore(.gitignore:64)
     => `table_config.json` 의 표 수 · `chain_rules.json` 의 규칙 수 · `enrichment_rules.json`
        의 규칙 수 · `virtual_join_rules.json` 의 조인 수 · `ledger_config.json` 의 소스 수를
        «하나도» 못 센다. 이 인벤토리의 어느 칸에도 그 수를 적지 않았다

E-3  server/ingestion_workspace/**  추적 1 · gitignore(.gitignore:88)
     => 커스텀 파서 스크립트 · 오토업데이트 수집기 · AdvancedIngester 선언(config/*.json)이
        전부 여기 산다. 그래서 다음 셋을 «못 판정»했다:
          · 커스텀 파서가 몇 표를 덮나
          · 수집기가 몇이고 몇이 켜져 있나
          · AdvancedIngester 를 «오늘 부르는 스크립트가 있나» (D-3 의 나머지 절반)

E-4  운영의 «수» 전부                소유자 2026-09-08: 「운영에서 재는 건 보안상 불가능」
     => 이 문서의 어느 줄도 「운영은 N 이다」를 말하지 않는다. 라우트 110 · 자식 넷 ·
        연산 6 · builtin 3 은 «코드»가 든 수라 어느 설치에서나 참이다.
        행 수 · 규칙 수 · 파일 수는 «안 적었다»

E-5  클라 절반                       이 조사는 «서버 절반»이다. §A·§B 의 클라 근거는
     `client2/src/**`·`client2/*.html`·`client2/dist/**`·`desktop/desktop_wrapper.py` 를
     훑은 것이고, 「그 화면이 실제로 «열리나»」는 안 재 봤다(페이지를 안 열었다).
     특히 §B 의 다섯은 `rnd-board.html` 이 nav 없이 직접 여는 페이지라,
     「직접 열면 404 다섯이 난다」까지가 이 조사의 주장이다

E-6  라우트의 «거절률»                각 라우트가 오늘 몇 %를 거절하는지는 못 잰다(E-4 와 같은 이유).
     §B 의 404 는 «라우트 부재»라 코드에서 갈리는 사실이고, 그래서 적었다
```

---

## 부록 — 이 조사가 «다시 확인»한 것 (기존 판정의 생존 확인)

```
✅ 판정 420 「문 가르기 금지」 — 체인 디스패처가 «한 좌석»(`rule_run.run_rule`)으로 접혔다.
   두 문을 직접 부르는 제품 코드가 그 파일 밖에 없고, 로그 접두도 하나다
✅ 판정 406 — 체인 루프는 자기 프로세스에서 돈다. 런처는 `ASSY_CHAIN_WORKER=0` 을 주는데,
   `main.py` 는 그 «전»에 `DECOUPLED=True` 로 이미 return 한다(둘째 가드이지 첫째가 아니다)
✅ 계측 상설 (2026-09-16 장애) — `_maybe_explain_slow_prefetch` 가 `try/except` 로 감싸였고
   시험(`test_a_diagnostic_may_not_kill_what_it_diagnoses.py`)이 같이 있다
✅ 판정 427 — 배치 갱신 봉투는 «빌더 하나»가 짓는다(다만 인자가 두 벌 — C-3)
✅ 판정 402 — 순환은 «보고»이고 거절이 아니다. 유한성은 `max_chain_depth`
✅ 그래프 갈래 은퇴 — 실행 코드·프로세스·라우트 «전부» 없다. 남은 것은 컬럼 셋과 거르는 자리 넷
```
