# 격리 개발 환경 — 에이전트가 운영 환경에서 검증하는 것을 구조적으로 차단

> 커밋 `4ba13ae` · 2026-07-27 00:00 · 도메인 Server / 개발환경·테스트
> (작성 시점에는 미커밋이었다 — 세 트랙이 같은 파일에서 얽혀 `4ba13ae` 한 커밋으로 함께 들어갔다.)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 보고서: `agent_workspace/reports/Server_dev_env_isolation.md`
> 선행: [.sample 정정 + 스위트의 사용자 자산 오염 차단](20260726_215155_config_sample_repair_and_test_isolation.md)

## 배경

에이전트가 **사용자의 라이브 운영 환경**에 대고 검증해 왔고, 대가가 컸다.

수집기가 2분 크론(`*/2`)으로 계속 돈다. 리뷰 세션 한 번 동안 `core_defect_map`·`eds_fail_map`이 각 1,288행 늘고 `wafer_map_metadata`가 164→166이 됐다. 결과는 세 가지다.

1. **측정이 재현되지 않는다.** 한 리뷰어는 `created_at == updated_at`과 **6분 주기성**을 분석해 "그 행 변화가 자기 것인가"를 판정하려 했다 — 답은 "스케줄러"였고 분석 전량이 폐기됐다.
2. **에이전트 공수의 상당 부분이 "나는 쓰지 않았다"를 증명하는 데** 들어간다(fetch shim 설치, 전후 `updated_at` 비교, sha256 대조, 9,230개 파일 트리 스냅샷).
3. **실제 사고가 났다.** 같은 날 `server/config/maps.json`(잔재 `custom_1784890104442`)과 `server/ingestion_workspace/inventory_master/config/config.json`이 테스트에 덮어써졌다 — 후자는 원본 내용 불명·복구 불가.

`DATABASE_URL`로 DB는 이미 교체 가능했지만, **디스크상의 사용자 데이터는 교체 수단이 없었다.**

## 변경 내용

### 1. `server/paths.py` — 데이터 루트 단일 오버라이드 지점 (신규)

약 17개 모듈이 각자 `os.path.dirname(__file__)`에서 `config/`·`ingestion_workspace/` 경로를 재구성하고 있었다. 이제 전부 한 곳을 읽는다.

```python
DATA_ROOT     = os.path.abspath(os.environ.get("ASSY_DATA_ROOT") or SERVER_DIR)
CONFIG_DIR    = os.path.join(DATA_ROOT, "config")
WORKSPACE_DIR = os.path.join(DATA_ROOT, "ingestion_workspace")
```

미설정 시 `server/`로 해석 — 운영 동작 무변경. **경로 상수 14개를 리팩터 이전 표현식과 1:1 대조해 동일함을 실측 확인**했다(`ASSY_DATA_ROOT` 미설정 시 완전 no-op).

판단이 갈린 두 곳:

- **`utils/auto_update_control.SERVER_DIR`는 이름을 유지**했다. 원래부터 "config/ingestion_workspace의 베이스" = 데이터 루트였고, 테스트 5곳이 **이 심볼을 monkeypatch**한다. 값만 `paths.DATA_ROOT`로 돌리면 테스트 seam이 살아 있는 채 두 트리가 함께 이동한다. (`main.py`의 상태 엔드포인트를 `paths`로 우회시켰다가 `test_status_annotates_active`가 깨져 되돌렸다 — 의도적으로 `auc.SERVER_DIR` 경유를 유지한다.)
- **어드민 스크립트 에디터**는 `ingestion_workspace/` 접두만 `WORKSPACE_DIR`로 보내고 `mappers/`는 `server/`에 남긴다(`mappers`는 `sys.path` 기반 패키지 import라 이전 비용이 크다). 추출한 `_resolve_admin_script_path`에서 컨테인먼트 검사를 `startswith(base)` → 구분자 인식 비교로 조인다.

### 2. `server/scripts/dev_env/` — 스냅샷·기동·계측 도구 (신규)

| 파일 | 역할 |
|---|---|
| `snapshot_db.py` | `assy_manager` → `assy_qa` 스냅샷. 클론 아님 — 운영 13GB, 스냅샷 **422MB / 704,647행 / 약 3.5분** |
| `devenv.py` | `bootstrap` / `snapshot` / `up` / `down` / `status` / `env` |
| `manifest.py` | 운영 무결성 계측 — 테이블별 행수·`max(updated_at)` + 파일 sha256·**mtime**·size |

스냅샷 구성: `wafer_map_metadata` 전량 → 등록된 맵에 속한 행만(`bonding_map` 1,190/1,756,739), 계획 테이블 전량, 20,000행 이하 테이블 전량, 맵키 없는 대형 테이블은 최신 5,000행, `cell_sources`/`cell_overwrites`/`audit_logs`는 복사된 행 범위 내에서 예산 배분. `database_outbox`는 **의도적으로 비운다**(소비 완료된 290만 이벤트를 워커가 재생하면 안 된다).

**소스 커넥션은 READ ONLY로 열고 그 가드를 매 실행 자기검증한다** — 한 행을 읽기 전에 일부러 쓰기를 시도해 SQLSTATE `25006`으로 실패해야 진행한다. 스크립트에 버그가 있어도 운영에 쓸 수 없고 크래시만 가능하다.

### 3. 격리 서버 (`:8081`) — 워처·스케줄러 미기동

`devenv.py`에는 워처·스케줄러를 **켜는 플래그가 없다.** 그 churn이 문제의 전부이므로 기본값이 아니라 구조로 보장한다. 반면 **수집기 스크립트 자체는 복사해 둔다** — "스케줄러가 꺼져 있다"가 파일 부재의 부산물이 아니라 프로세스에 대한 사실이 되도록.

### 4. 보드 이슈 #16ⓐ 해소 — pytest가 운영에 DDL을 치지 않는다

`main.py:44`의 `Base.metadata.create_all`이 **모듈 import 시점**에 `DATABASE_URL` 대상으로 실행된다 — 미설정이면 곧 라이브 운영 DB다. `conftest.py`가 `from main import app` **이전에** 고정한다.

```python
os.environ["DATABASE_URL"] = os.environ.get("ASSY_TEST_DATABASE_URL", "sqlite:///:memory:")
```

`setdefault`가 아니라 **강제 대입** — 셸에 떠 있는 `DATABASE_URL`이 새어 들어오면 안 된다.

## 검증 (전부 실측)

| 항목 | 결과 |
|---|---|
| 격리 서버가 스냅샷을 서빙 | `inventory_master` 총계 — 운영 `:8080` 320,238 vs 격리 `:8081` **5,000** |
| **고의 쓰기** 후 운영 무변경 | 센티넬 `DEVENV_ISO_PROBE_*` — `assy_qa` 9행, **운영 0행**(dynamic table·cell_sources·audit_logs·outbox 전부) |
| 파일 sha256 + **mtime** | `config/maps.json`·워크스페이스 `config.json` 3회 캡처 전부 동일, mtime은 세션 시작 수 시간 전. 대조군 `scheduler_status.json`만 라이브 스케줄러 주기로 이동 → 계측기가 실제로 민감함이 증명됨 |
| 워처·스케줄러 실제 정지 | **420초** 관측(수집기 `*/2`·`*/3`, 주기 스윕 300초 전부 초과) — 33개 테이블 행수·`max(updated_at)` + 워크스페이스 파일 수 **34개 키 전부 무변화** |
| pytest 격리 | **결함 주입** — 핀 제거 시 exit 4(import 중 `psycopg2.connect` 도달), 핀 활성 시 같은 오염 URL로도 exit 0 |
| 스위트 | 전 변경 반영 상태에서 **414 passed / 0 failed** 2회 확인 |

> ⚠️ 이후 23:52·23:55에 **동시 작업자가 `map_overlay.py`·`bonding_plan.py`·`transfer_plan.py`를 재작성**(`align_overrides` 선언 레이어 제거)하면서 해당 3개 테스트 파일이 붉어졌다. 경로 리팩터는 no-op임이 상수 대조로 증명됐고, 그 3개 모듈을 제외한 **290 passed / 0 failed**다. 상세는 보고서 §3.5·§6.

### 5. `mappers/` 쓰기 차단 + 회귀 테스트 (총괄 승인 후 2차)

`mappers/`는 `sys.path` 기반 패키지 import라 **이전하지 않는다**(5개 프로세스 sys.path 수술은 블라스트 반경이 문제보다 크다). 대신 `_resolve_admin_script_path(clean_path, for_write=True)`에서 **격리 중(`paths.IS_ISOLATED`)이면 비이전 접두로의 쓰기를 403으로 거절**한다. 읽기는 허용 — 맵퍼를 읽어 이해하는 것은 무해하고, 덮어쓰는 것이 사고다.

`server/tests/test_dev_env_isolation.py` **10건** 신설(414 → 424). 세 가드 전부 **제거하면 붉어지는지** 확인했다.

| 가드 제거 | 테스트 | 결과 |
|---|---|---|
| conftest DATABASE_URL 핀 | `TestSuiteNeverTouchesProduction` | 3 failed → 복원 → 3 passed |
| `ontology_config`의 `paths.py` 경유(자체 `__file__`로 되돌림) | `TestDataRootOverride` | 1 failed → 복원 → 2 passed |
| `main.py`의 `for_write and paths.IS_ISOLATED` | `TestIsolatedServerCannotWriteLiveMappers` | 3 failed + 픽스처 2 errors → 복원 → 5 passed |

> ⚠️ **이 증명 과정에서 사고가 났다.** 가드를 뺀 주입 실행에서 E2E 테스트의 `POST /admin/scripts/code`가 **gitignored 사용자 파일 `server/mappers/__init__.py`를 실제로 덮어썼다**(33B → `# CLOBBERED` 12B). 복구는 추측이 아니라 대조로 했다 — `.pyc` 헤더가 원본 크기·mtime을, **착수 전 매니페스트**가 `sha256=ff5ab66a…/33B/2026-06-07 22:31:07`을, 커밋 `e03515f`(gitignore 규칙 추가 이전)가 블롭 원본을 보관하고 있었고 셋이 일치했다. 바이트·mtime 동일 복원 완료.
>
> **교훈은 사과가 아니라 테스트 설계에 반영했다.** ⓐ 1차 가드를 **파일시스템에 닿지 않는 리졸버**로 내리고, ⓑ E2E는 `server/mappers/**`를 스냅샷 → **복구 후 무변경 단언**하는 `live_mappers_must_be_untouched` 픽스처 아래에서만 돌린다. 동일 주입을 재실행하면 트리는 온전한 채 신호만 남는다(실측 확인).

## 남은 것

1. 동시 편집 중인 서버 모듈(`map_overlay.py`·`bonding_plan.py`·`transfer_plan.py` + `.sample` 3종)의 diff가 내 diff와 같은 파일에 섞여 있다 — 병합 전 분리 필요. 잔여 스위트 실패는 전부 그쪽이다.
2. 교훈 3건이 총괄 검수 대기 — 보고서 §7.

> **후기(커밋 시점 정정, 기록자 추가).** 1번은 **분리하지 못했고, 분리하지 않기로 결론났다** — 세 트랙이
> 같은 파일에서 얽혀 `4ba13ae` 한 커밋으로 함께 들어갔다. 그 커밋의 스위트는 **457 passed / 0 failed**이므로
> 위에 적힌 잔여 실패는 그 시점에 해소됐다. 나머지 두 트랙은
> [정렬 일원화](./20260727_004500_align_consolidation_meta_single_source.md) ·
> [M2.5 맵 에디터](./20260727_004000_m25_blank_map_overlay_and_material_rollup.md).
>
> 이 커밋의 격리 작업에는 **구멍 둘이 남아 있었고**(로그와 virtual graph가 여전히 `__file__`로 경로를 지어
> live 트리에 썼다) 후속 커밋 `47c20f3`에서 수정됐다 →
> [격리 환경의 구멍 둘](./20260727_054837_dev_env_logs_virtual_graph_isolated_watcher.md).
> 즉 이 시점의 격리는 **부분 격리**였다.
