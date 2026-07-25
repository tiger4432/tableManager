# 어드민 auto update 수집기 active 토글 (제어 파일 + 핫 스킵)

- **일시:** 2026-07-25 23:45
- **주체:** Server PM (총괄 위임 — auto update active 제어 지시서)
- **영역:** server (utils 신설 + run_auto_update.py + main.py + tests)
- **커밋:** (미커밋 — 총괄 검수 후 커밋 예정)

## 무엇이 바뀌었나

어드민에서 auto update 수집기 스크립트별 active 상태를 제어할 수 있게 했다.
영속 제어 파일은 `server/config/auto_update_control.json`
(`{"disabled": ["<workspace>/<script.py>", ...]}`, gitignored 사용자 config 관례,
`.sample` tracked). 파일 부재/손상 시 전부 active(fail-open).

- **`server/utils/auto_update_control.py` (신설)** — 제어 파일 공용 IO:
  `read_disabled_scripts`(fail-open) / `set_script_active`(tmp+`os.replace` 원자적
  쓰기, 프로세스 내 Lock) / `validate_script_key`(`<ws>/<script.py>` 정규식 + `..`
  차단) / `resolve_script_file`. 웹서버(쓰기·조회)와 스케줄러(읽기)가 공유.
- **`run_auto_update.py`** — 크론 틱 본체를 `check_and_run_schedules()`로 추출.
  매 틱 제어 파일을 읽어 disabled 수집기는 실행 스킵 + `last_status="SKIPPED"` +
  next_run 전진 + status 파일 기록(**핫 반영 — 재기동 불필요**).
  `_write_status_file`에 `active` 필드 추가(순수 추가).
  `run_collector_on_demand`(run-now)는 **active 무관 실행**(수동 실행은 명시적 의도 — 계약 #5).
  `MultiDiscoveryScheduler`/`GenericScriptRunnerCollector`에 optional `server_dir`
  파라미터 추가(기본값 유지 — 기존 호출 불변, 테스트 격리용).
- **`main.py`** — `GET /admin/auto-update/status` 응답의 각 스크립트 항목에
  `"active": bool` 부가(기존 필드 불변). active는 status 파일이 아니라 **제어 파일을
  실시간으로 읽어** 계산 — toggle 직후 스케줄러 재기록 전에도 즉시 일치.
  `POST /admin/auto-update/toggle` 신설 — body `{"script","active"}`, 성공 200
  `{"status":"success","script","active"}`, 스크립트 파일 미존재 404, 형식/타입
  검증 실패 400(경로 탈출 차단 포함).

## 검증

- 신규 `server/tests/test_auto_update_toggle.py` 20건: 제어 파일 IO(부재/손상/
  왕복/멱등), 스케줄러 스킵(SKIPPED + 미실행 + next_run 전진)·활성 실행·run-now
  active 무관, status `active` 부가(기존 필드 불변 검증), toggle 200/404/400(7종).
- 전체 스위트: 1 failed(기허용 `test_map_presets_api`), 203 passed.
