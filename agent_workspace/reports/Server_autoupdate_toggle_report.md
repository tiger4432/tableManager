# Server 보고서 — auto update 수집기 active 토글

- **작업:** 어드민에서 auto update 수집기의 active 상태 제어 (총괄 고정 계약 5항 전부 이행)
- **작업자:** Server PM · 본체 main 트리 · **미커밋 (총괄 커밋 예정)**
- **일시:** 2026-07-25

## 1. 변경 파일

| 파일 | 변경 |
|---|---|
| `server/utils/auto_update_control.py` | **신설** — 제어 파일 공용 IO. `read_disabled_scripts`(부재/손상 시 빈 집합 = 전부 active, fail-open) · `set_script_active`(tmp+`os.replace` 원자적 쓰기 + 프로세스 내 Lock) · `validate_script_key`(`^[A-Za-z0-9_\-.]+/[A-Za-z0-9_\-.]+\.py$` + `..`/`\` 차단) · `resolve_script_file` · `get_control_path`. `SERVER_DIR` 모듈 상수(테스트 monkeypatch 지점) |
| `server/run_auto_update.py` | 크론 틱 본체를 `check_and_run_schedules(now)` 메서드로 추출(run 루프는 위임 호출). 매 틱 제어 파일 읽어 disabled 수집기 = 실행 스킵 + `last_status="SKIPPED"` + next_run 전진 + status 파일 기록(**핫 반영, 재기동 불필요**). `_collector_key()` 헬퍼(`<table>/<script.py>` — 제어 파일 규격과 동일). `_write_status_file`에 `active` 필드 추가. `run_collector_on_demand` docstring에 run-now의 active 무관 실행 계약 명시. `MultiDiscoveryScheduler`·`GenericScriptRunnerCollector`에 optional `server_dir` 파라미터 추가(기본값 = 기존 동작, 순수 추가 — 테스트 격리용) |
| `server/main.py` | `GET /admin/auto-update/status` — 각 항목에 `"active": bool` 부가(기존 필드 불변). **제어 파일을 요청 시점에 직접 읽어** 계산하므로 toggle 직후 스케줄러가 status 파일을 재기록하기 전에도 즉시 일치. `POST /admin/auto-update/toggle` 신설(~L3253) — 검증실패 400(형식·타입·경로탈출), 스크립트 파일 미존재 404, 성공 200 `{"status":"success","script":...,"active":...}` |
| `server/config/auto_update_control.json.sample` | **신설** — 사용자 config `.sample` 관례 준수(`server/config/*`는 gitignored, `*.sample`만 tracked — 확인 완료) |
| `server/tests/test_auto_update_toggle.py` | **신설** — 20 케이스 |
| `docs/architecture/backend.md` | 엔드포인트 표 + Auto-Update Scheduler 행 갱신(제어 파일·SKIPPED·run-now 계약 문서화) |
| `docs/architecture/CODE_MAP.md` | §1 admin 표에 toggle 추가·status 라인앵커 보정(~3222/3253/3286), §6에 `auto_update_control.py` 행 추가 |
| `docs/history/20260725_234500_auto_update_active_toggle.md` (+`README.md` 재생성) | 히스토리 기록 + `gen_index.py` 실행 완료 |

## 2. 계약 이행 매핑

1. **제어 파일** — `server/config/auto_update_control.json`, `{"disabled": ["<ws>/<script.py>"]}`, 부재 시 전부 active. 손상 시에도 fail-open(전부 active) + 경고 로그 — 수집 중단이 더 큰 사고라는 판단. ✔
2. **스케줄러 핫 스킵** — 매 5초 틱마다 제어 파일 재독(작은 JSON 1회 read, 부하 무시 가능). 스킵 시 status에 `SKIPPED` 반영 + next_run 전진(재활성화 시 과거분 폭주 실행 없음). ✔
3. **status `active` 부가** — 기존 8개 필드 바이트 단위 불변(테스트로 검증), 순수 추가. ✔
4. **toggle** — 200/404/400 규격 그대로. 400은 FastAPI 422가 아닌 명시적 400을 위해 `payload: dict` 수동 검증. 404 판정 기준은 `ingestion_workspace/<ws>/auto_update/<script>` 파일 실존 여부. ✔
5. **run-now active 무관** — 코드 경로상 제어 파일 미참조(변경 없음이 곧 보장) + docstring·backend.md 문서화 + 테스트(`test_run_now_ignores_disabled`). ✔

## 3. 검증

- 신규 테스트 20건 전부 통과: 제어 파일 IO(부재·손상·wrong-shape fail-open, 왕복, 멱등, 키 검증 11케이스), 스케줄러(disabled 스킵 = SKIPPED + raws 산출물 0 + next_run 전진 + status active:false / 재활성 실행 = SUCCESS + CSV 산출 / run-now는 disabled여도 실행), status 엔드포인트(active 부가 + 기존 필드 불변 + 제어파일 부재 시 전원 active), toggle(왕복 200, 404, 400 파라미터라이즈 7종).
- **전체 스위트: 203 passed / 1 failed — 실패는 기허용 `test_api.py::test_map_presets_api` 단 1건.**
- 전수 Grep(사용자 영역 `server/config/`·`ingestion_workspace/`·`mappers/` 포함): 변경 시그니처(`GenericScriptRunnerCollector`/`MultiDiscoveryScheduler`)의 외부 소비자 없음. 사용자 수집기 스크립트(`bonding_map`, `inventory_master`)는 스케줄러가 로드하는 대상일 뿐 시그니처 비의존 — 영향 없음.

## 4. 경계 계약 준수

- REST: `GET /admin/auto-update/status` 기존 필드 불변(추가만), `POST /admin/auto-update/toggle`은 총괄 고정 계약 그대로 신설. WS·셀 형태·스키마 계약 무접촉.
- 클라이언트 병렬 개발 참고: status 항목 키는 `table_name`/`script_name`이며 toggle의 `script` 키는 `f"{table_name}/{script_name}"` 조합과 정확히 일치한다(스케줄러 `_collector_key`와 동일 규격).

## 5. 미해결·다음 단계

- (선택) 클래스 상속형 `BaseCollector` 수집기 중 `script_path`가 없는 경우 키가 `<table>/<클래스명>`으로 잡히는데, 실제 로드 경로상 `script_path`는 항상 주입되므로 도달 불가에 가까움 — 현행 폴백으로 충분.
- 커밋·PROJECT_STATUS 보드 갱신은 총괄 몫(본 보고서 기준).

## 6. 교훈 제안 (memory/server-pm.md 반영 후보)

- **함정**: FastAPI에서 body 필드 타입 오류는 기본 422로 떨어진다 — 계약이 400을 요구하면 Pydantic 모델 선언으로는 불가.
  **올바른 방법**: `payload: dict = Body(...)`로 받아 수동 검증 후 명시적 `HTTPException(400)`.
- **함정**: 두 프로세스(웹서버 쓰기 / 스케줄러 읽기)가 공유하는 JSON 제어 파일은 일반 write 시 부분 읽기 레이스가 난다.
  **올바른 방법**: tmp 파일 기록 후 `os.replace` 원자적 교체(Windows 포함) — 본 프로젝트 raws 드롭과 동일 패턴.
