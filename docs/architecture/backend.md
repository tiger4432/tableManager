# 🖥️ Backend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-07-31 | **Owner:** Backend/Sync
> 
> ### 이번 라운드 (2026-07-31 · `9200f20`·`fbc1053`·`1948338`·`9c6a1c9`)
> - **`GET /tables/{t}/schema`에 `virtual_columns` 키 신설** (`9200f20`) — **`columns`에 이름을 더하지 않고 별도 키**입니다. 그래서 이 키를 무시하는 클라이언트는 **키가 없던 때와 글자 그대로 같게** 동작합니다(컬럼 목록·push 게이트 산술·붙여넣기 대상 전부 불변). 🔴 **읽기 전용은 여기서 강제되지 않습니다** — 막는 것은 `crud.refuse_virtual_join_columns` 하나이고 `editable: false`는 클라가 편집을 **제안하지 않게** 하는 표시일 뿐입니다.
> - **소급 적용 어드민 표면 3라우트 신설** (`fbc1053`) — `/admin/retroactive/{operations,{op}/count,{op}/run}`. 등록부 `server/retroactive.py`는 **순수 디스패치**이고 새 연산을 하나도 구현하지 않습니다. 실행은 아웃박스 한 줄 + 즉시 반환(`run-now`와 같은 형태)이고, **모든 카운트가 `count_kind`를 함께 답합니다**(다섯 중 넷은 요청 경로에서 정확할 수 없습니다).
> - **§1.2에 `server/scripts` 한 방향 문 규율 신설** (`9c6a1c9`) — 런타임 코드가 `server/scripts/`를 import하면 **운영에서만 `ModuleNotFoundError`**가 납니다(그 디렉터리는 어느 프로세스의 `sys.path`에도 없습니다). 스위트는 초록이었습니다 — 테스트 파일 하나가 자기 용도로 그 경로를 넣어 두기 때문입니다.
> - **`/admin/*` 라우트 수 재실측** — 종전 「16개」는 낡았습니다(2026-07-31 실측 **22개**, strict **3개**).
> 
> 🔴 **이 헤더에 라운드를 쌓지 마십시오.** 이전 기록은 [`docs/history/`](../history/)에 있습니다.
> **Source-of-truth:** `server/main.py`, `server/database/crud.py`, `server/*_worker.py`, `server/run_*.py`, `server/map_overlay.py`, `server/map_preset_routing.py`, `server/transfer_plan.py`, `server/value_suggest.py`, `server/process_supervisor.py`, `server/health.py`, `server/utils/heartbeat.py`, `server/paths.py`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

---

> 이벤트 기반 흐름(Outbox staging·체인·그래프)의 심화 설명은 [event_driven_backend.md](./event_driven_backend.md) 참조.

## 1. 멀티프로세스 설계

FastAPI 웹서버(`main.py`)는 API + WebSocket 허브이고, 무거운 작업은 별도 데몬으로 분리됩니다. 조정은 PostgreSQL **Transactional Outbox** 패턴으로 이루어집니다.

- **Outbox 테이블** `database_outbox` — 이벤트를 트랜잭션과 함께 커밋해 유실 없이 전달.
- **LISTEN/NOTIFY** 채널 `outbox_event` — 데몬이 폴링 대신 알림 기반으로 반응.
- **HTTP 콜백** `POST /internal/events/*` — 데몬이 웹서버에 UI 이벤트(브로드캐스트/캐시 무효화)를 되돌려 보냄.
- `main.py`의 `startup_event`는 `DECOUPLED=True`가 아니면 워처·체인 워커를 인라인 기동. 운영에서는 `run_decoupled_app.py`가 `DECOUPLED=True`로 완전 분리.
- **런처는 감시자다** — 자식을 띄우고 자는 것이 아니라 생존을 감시하고 재시작한다(§1.3). API 포트는 `ASSY_API_PORT`(기본 8080)로 덮을 수 있어, 감시 정책 자체를 격리 스택(:8081)에서 재구현 없이 그대로 검증할 수 있다.
- **데이터 루트는 `ASSY_DATA_ROOT` 하나로 옮긴다**(`server/paths.py`) — `config/`·`ingestion_workspace/`·프로세스 로그가 모두 여기서 유도된다. 미설정이면 `server/` 그대로. 새 경로를 `__file__`에서 다시 조립하면 격리가 샌다.
- **DDL은 import가 아니라 기동에서 한다** (2026-07-29, #16ⓐ). `main.py`는 모듈 레벨에서 `Base.metadata.create_all`을 돌렸고, 그래서 **앱을 import하기만 해도**(pytest 수집 포함) 그 시점에 해석된 `DATABASE_URL`—미설정이면 운영 DB—로 DDL이 나갔다. 지금은 `bootstrap_database_schema()`로 묶여 `startup_event`가 호출한다. **삭제가 아니라 이동이다** — 신규 설치의 온보딩("config에 테이블 추가 → 기동 → 즉시 사용")이 이 경로를 타기 때문이다. DB 불통 시 `create_all`이 startup에서 던져 **`Application startup failed. Exiting.`(exit 3)** 으로 죽는 동작은 종전과 같고, 감시자는 종료 코드를 구분하지 않으므로 §1.3의 동료실패 판정도 그대로다.
- **그리고 그 이동만으로는 #16ⓐ가 닫히지 않았다** (2026-07-31 완결, `server/db_safety.py`). 이동 뒤에도 남은 근거는 "테스트 엔진은 확인해 보니 전부 sqlite"였고, **점검은 메커니즘이 아니다** — 유일한 방어가 `server/tests/conftest.py`의 `DATABASE_URL` 핀이었는데 그것은 **테스트 트리가 하는 일**이라, 핀을 지우면 방어도 함께 사라졌다. 이제 거절은 **운영 코드 쪽**에 있고 세 겹이다: ① `database.py`가 공유 엔진에 `do_connect` 훅을 걸어 **소켓이 열리기 전에** 거절 ② 같은 모듈이 `Engine` **클래스**에 훅을 걸어 테스트가 스스로 만든 엔진까지 덮음 ③ `bootstrap_database_schema()`가 DDL 직전에 **연결 없이 순수 판정**으로 거절. 판정은 **허용목록**이다 — sqlite이거나 `ASSY_TEST_DATABASE_URL`이 명시적으로 지목한 URL만 통과하고, 나머지는 "운영 이름이 아니어도" 거절한다(차단목록은 운영 DB가 둘이 되는 날 열린다). ⚠️ **셋 다 pytest 안에서만 무장한다** — `under_pytest()`가 거짓인 운영 프로세스에서는 즉시 반환하므로 `create_all`은 **여전히 무가드**이고 위 문단의 exit 3 계약은 그대로다. 회귀 그물 `server/tests/test_ddl_never_reaches_production.py`(핀을 지우면 스위트가 **수집 단계에서** `[#16a] REFUSED`로 죽는다 — 실측).
- **기동은 손상된 `table_config.json`에 대해 fail-fast다** (2026-07-29, #13). 파싱 실패 시 `[Boot] Refusing to start - ...`(파일 경로 + line/column)를 남기고 프로세스가 죽는다. 빈 화면으로 뜨는 것이 더 나쁘다 — 데이터 유실처럼 보이는데 로그가 깨끗하다. **파싱 실패에 한정**하며, 의미 수준 문제는 기동을 막지 않는다.

미들웨어 `db_context_middleware`가 `X-User`/`X-Transaction-ID`/`X-Source` 헤더를 ContextVar로 읽어 감사 추적에 사용. CORS는 `localhost:5173`/`127.0.0.1:5173`으로 제한.

> 🔴 **`expose_headers`는 장식이 아니라 진단의 일부입니다** (2026-07-31 `cde3398`). 목록에 없는 응답 헤더는 **브라우저가 교차 출처에서 지웁니다.** `WWW-Authenticate`가 그래서 목록에 있습니다 — 클라의 게이트 판정(`isGateRejection`)이 401/403에 더해 **이 헤더가 `X-Admin-Token`을 지목하는지**를 보고 「우리 게이트가 거부했다」와 「앞단 프록시가 답했다」를 가르기 때문입니다. 노출하지 않으면 vite dev 오리진에서만 **진짜 게이트 거부가 「앞단이 답했다」로** 잘못 표시됩니다(같은 출처 서빙에서는 원래 읽혔으므로 눈에 띄지 않습니다). 값은 헤더의 **이름**뿐이라 비밀이 없습니다. 현재 목록: `Content-Disposition` · `X-Estimated-Content-Length` · `X-Total-Rows` · `WWW-Authenticate`.

### 1.1 이벤트 루프 보호 원칙 (C-1, 2026-07-25)

uvicorn은 **단일 이벤트 루프**이므로, `async def` 핸들러 본문에서 동기 SQLAlchemy 쿼리·O(행×컬럼) 병합 루프·대형 JSON 직렬화를 실행하면 웹서버 전체(모든 REST/WS/내부 브로드캐스트)가 동결된다(라이브 실측 7초 freeze). 강제 규칙:

- **await가 필요 없는 핸들러는 `def`(sync)로 작성** → FastAPI가 threadpool에서 실행.
- **await(브로드캐스트 등)가 필요한 핸들러의 동기 구간(crud 호출, `fetch_and_merge_metadata`, ORM 속성 접근/직렬화)은 `run_in_threadpool`로 격리**. 적용 지점: PUT `/data/updates`, `batch_delete`(N+1 → `get_deleted_rows_business_keys_bulk` 벌크 IN 조회로 대체), `POST /rows`, `DELETE /rows/{id}`, priority(단건·배치), sources delete(단건·배치), `/internal/events/*`(audit_cache 갱신·json.dumps).
- 신규 엔드포인트 추가 시 이 원칙을 리뷰 포인트로 명시한다.

### 1.2 import 경로 불변식 (C-2)

모든 프로세스·스크립트는 `server/`를 sys.path에 두고 **최상위 `database.*` / `parsers.*` 경로로만** import한다. `server.database.*` 혼용 import는 동일 모듈 이중 로드 → outbox `before_flush` 리스너 2중 등록 → **전 이벤트 ×2 중복 발행**을 유발한다(상세: [event_driven_backend.md](./event_driven_backend.md) §2.1).

> 🔴 **`server/scripts/`는 한 방향 문이다 — 런타임 코드가 그쪽을 import하면 안 된다** (2026-07-31 `9c6a1c9`). 그 디렉터리는 **어느 운영 프로세스의 `sys.path`에도 없다.** 각 스크립트가 `__main__`으로 돌 때 자기 힘으로 `server/`를 부트스트랩하므로 **스크립트 → `server/`는 되고 그 반대는 안 된다.** 규율은 이 저장소가 이미 세 번 쓴 형태다 — **의미론은 `server/`에, argparse와 보고서 서식만 `scripts/`에**(`graph_orphans.py` ↔ `graph_orphan_sweep.py` · `chain_replay.py` ↔ `chain_replay_cli.py` · `enrichment_analysis.py` ↔ `enrichment_insights.py` · 2026-07-31 신설 `enrichment_backfill.py` ↔ `backfill_enrichment.py`).
>
> - **어겼을 때의 증상이 최악의 모양이다.** `retroactive.py`가 `backfill_enrichment`를 import했을 때, 카운트 라우트는 즉시 터졌지만 **실행 트리거는 200 `queued`를 돌려줬다** — `publish`는 검증하고 아웃박스 한 줄을 쓸 뿐이고, import 실패는 **스케줄러 스레드 안**에서 나 로그로만 남았다. 초록 버튼 · 쓰인 행 0 · 표면에 에러 없음.
> - 🔴 **「import되는가」는 공유 인터프리터 안에서 테스트할 수 없는 성질이다.** 같은 결함을 재주입하면 라우트 테스트는 단독으로는 빨갛지만 `test_install_product_tables.py`가 **먼저 돌면 초록이 된다**(그 파일이 정당하게 `SCRIPTS_DIR`을 `sys.path`에 넣고 파일명 정렬이 앞선다). conftest 가드로도 못 막는다 — 그 삽입은 모듈 import 시점이라 conftest보다 뒤다.
> - 판정은 **별도 프로세스**가 한다: `server/tests/prod_import_check.py`가 `-I` + `PYTHONPATH` 비운 채 shell out해 런타임 트리 전체의 import를 훑는다(진입은 `server/tests/test_prod_import_env.py`). `try/except ImportError`로 감싼 선택적 의존은 **소스에서 그 가드를 인식해** 통과시키므로 허용목록을 유지보수할 필요가 없다.

### 1.3 프로세스 감시와 헬스 (2026-07-27)

런처는 더 이상 자식을 띄우고 자기만 자는 루프가 아니다. `run_decoupled_app.py`가 `process_supervisor.Supervisor`를 돌리고, 그 결과를 `/health`가 밖으로 내보낸다. **두 축이 한 쌍**이다 — 감시 결과를 외부에서 볼 수 없으면 감시는 없는 것과 같다.

**감시자** (`server/process_supervisor.py` — 상태 파일 `<DATA_ROOT>/config/supervisor_status.json`)

- `ChildSpec(name, cmd, cwd, env, restartable, heartbeat, start_delay)`로 자식을 선언하고 1초 주기로 `poll_once()`.
- **유한 재시작 예산**: 연속 실패 n회째 `min(2·2^(n-1), 60)`초 백오프(2/4/8/16/32) → **6번째 연속 실패에서 `FAILED` 확정, 이후 재기동 없음**. 무한 재시작은 고장을 "감시가 도는 것처럼" 위장하므로 금지.
- **예산 회복**: 60초 이상 살아 있었으면 크래시 루프가 아니라고 보고 연속 카운터를 리셋.
- `restartable=False`(데스크톱 셸)의 종료는 **전체 종료 신호**다.
- `stop_all()`은 **정지 플래그를 먼저 세운 뒤** 종료한다(감시 루프가 종료 중인 자식을 "죽었다"고 되살리는 경쟁 방지). 자식의 손자 프로세스(스케줄러가 띄우는 수집기)는 부모가 살아 있는 동안 pid를 수집해 함께 정리한다 — 부모가 먼저 죽으면 손자를 찾을 방법이 없다.
- 상태 파일의 `updated_at`이 **감시자 자신의 생존 신호**다(감시자가 죽으면 자식은 계속 박동하는데 이 값만 멈춘다).

**진행 박동** (`server/utils/heartbeat.py` — `<DATA_ROOT>/config/worker_heartbeats/<name>.json`)

- 워커가 **자기 작업 루프 안에서** `beat(name)`을 호출한다. 이름 4종: `watcher` · `chain` · `graph` · `scheduler`.
- pid 검사가 아니라 **진행** 신호인 이유: 우리가 실제로 겪은 장애는 프로세스가 살아 있는 채 멈춘 이벤트 루프 동결이었다.
- 쓰기는 워커당 1초 이하로 스로틀되고, 원자적 replace이며, **모든 디스크 오류를 삼킨다**(감시 기능이 새 장애 원인이 되면 안 된다).
- 정체 임계 기본 **60초** — 워커별 루프 주기(2~5초) 대비 연속 12회 이상 누락에 해당한다. DB가 아니라 파일에 두는 이유는, DB 장애 때 전 워커가 동시에 정체로 보여 "DB 다운"과 "워커 정지"가 뭉개지기 때문이다.

**판정 조인** (`server/health.py`) — 프로세스 존재는 감시자가, 진행은 워커가 권위를 갖는다.

워커 상태값은 **정확히 8종**이며 전수는 다음과 같다(`health.py`의 `entry["status"]` 대입 지점 전수 — 2026-07-27 대조).

| 감시자 | 박동 | 판정 | 뜻 |
|---|---|---|---|
| running 아님 | — | `down` | 감시자가 프로세스 없음/실패로 본다 |
| running | 없음 · uptime < 60s | `starting` | 기동 유예 — **경보 아님**(`degraded`까지만) |
| running | 없음 · 유예 경과 | `missing` | 프로세스는 도는데 **한 번도 박동한 적 없음** |
| running | 다른 pid의 박동 | `foreign_beat` | 아래 pid 규율 참조 |
| running | 정체(60초) | `wedged` | **살아 있는데 진행 없음** — pid 검사로는 안 보이는 케이스 |
| 정보 없음 | 정체(60초) | `stale` | 감시자 상태 파일이 없어(`supervisor: absent`) 프로세스 관점을 못 얻음 |
| running | 신선 | `ok` | |
| running | 신선하지만 **claim한 작업이 300초간 무진행** | `stalled` | |

- ⚠️ **`stalled`는 `wedged`와 다른 검출기다.** 박동은 *루프 하나가 돈다*는 것만 증명한다 — 워처의 3초 재시도 폴러가 계속 박동하는 동안 인제션이 멈춰 있었고 `/health`는 `ok`였다. 그래서 **작업 단위의 진행**을 따로 본다. 임계가 60초가 아니라 **300초**인 것은 의도적이다(박동은 2~5초 루프, 작업 청크는 실측 p95 9.7초·max 12.5초로 균일하지 않다). 더 구체적인 판정(`down`/`wedged`/`missing`)은 **덮어쓰지 않는다** — `ok`일 때만 `stalled`로 강등된다.
- **박동은 감시자가 띄운 pid의 것만 인정한다.** 같은 역할의 유령 프로세스나 재기동 직전에 죽은 전임자의 박동이 정체를 가리는 사례가 드릴에서 관측됐다(불일치 시 `foreign_beat`).
- **감시자 자신의 상태값은 별개 어휘다** — `absent` · `ok` · `stale` · `correlated_failure` · `failed_children` 5종. 워커 상태값과 섞어 쓰지 말 것(`stale`만 두 어휘에 모두 존재하며 뜻이 다르다).
- **outbox 적체는 크기가 아니라 나이로 판정한다** — 정상적인 10만 행 적재 하나가 outbox 약 11.6만 행을 만들기 때문에, 멈춘 워커를 잡을 만큼 낮은 크기 임계는 큰 파일마다 오경보한다. 가장 오래된 미처리 행이 5분 초과 `degraded` / 15분 초과 `unhealthy`, 건수는 참고값(1만 캡). 두 질의 모두 부분 인덱스 `idx_outbox_unprocessed` 위 O(1).
- 감시자 상태 파일이 없으면 `supervisor: absent`(bare uvicorn·격리 스택) — 디스크의 박동만 참고 판정한다.
- **`config_backup`은 프로세스가 아니라 *산출물*을 본다** (2026-07-28, C3). 주간 config 스냅샷의 최신 파일이 없으면 `missing`, 10일 초과면 `stale`, 읽지 못하면 `unknown` — 셋 다 **`degraded`(HTTP 200 유지)**다. 백업 부재는 *다음* 사고를 어렵게 만들 뿐 지금 스택이 죽은 것이 아니므로, 503을 내면 멀쩡한 스택을 재기동하라고 모니터에 지시하는 꼴이 된다.
  - 판정 근거가 **디스크의 스냅샷 파일**이지 작업이 스스로 기록한 "마지막 실행" 필드가 아니라는 점이 핵심이다. 3주 전에 조용히 죽은 작업은 자기 성공 기록을 그대로 들고 있다.
  - `unknown`(읽기 실패)도 `degraded`로 올린다 — **"확인 못 했다"를 "이상 없다"로 보고하지 않는다**(수집기 실패 판정과 같은 계약).
  - 이 프로브만 **라우트에서 주입하지 않고 `compute_health`가 직접 호출**한다. DB 프로브가 주입되는 이유는 *멈출 수 있어서* 라우트의 `wait_for`가 필요하기 때문인데, 이쪽은 로컬 `listdir`이라 그 위험이 없고 60초 캐시까지 걸려 있다. 단위 테스트는 `backup_result=`를 명시 주입해 결정표를 순수하게 유지한다.

---

## 2. API 엔드포인트 지도 (`main.py`, 5,355줄 — 커밋 트리 `77d27d3` `wc -l` 실측)

> **라인 앵커는 이 문서에서 관리하지 않습니다** — 핸들러 함수명·정확 위치는 [CODE_MAP §1](./CODE_MAP.md#1-servermainpy--api--ws-허브) 참조(doc-keeper가 Grep 실측으로 유지).

### 데이터 CRUD / 조회
| 메서드 · 경로 | 용도 |
|---|---|
| `GET /tables` | 구성된 테이블 목록 |
| `GET /tables/{t}/data` | 페이징/지연 그리드 조회(q 검색, cols, order_by, filters, tx 필터, target_row_id 점프). 카운트 5초 캐시 |
| `GET /tables/{t}/schema` | columns, column_types, business_key, composite_key_source, map_key_columns, map_push_ok, **`virtual_columns`**. 아래 §2.2 |
| `GET /tables/{t}/columns/{c}/values` | **[F3] 고유값 조회 — 입력 제안(드롭다운)의 전제 프리미티브.** `?prefix=&limit=` → `{table, column, prefix, values[], truncated, limit, unavailable_reason}`. 아래 §2.1 |
| `GET /tables/{t}/{row_id}` | 단건(전 소스 병합 메타 포함) |
| `POST /tables/{t}/rows` | 빈 행 N개 생성 |
| `PUT /tables/{t}/data/updates` | **통합 배치 업서트**(`crud.apply_batch_updates` 위임, 백그라운드 브로드캐스트) |
| `DELETE /tables/{t}/rows/{row_id}` | 단건 삭제 |
| `POST /tables/{t}/rows/batch_delete` | 일괄 물리 삭제 |
| `POST /tables/{t}/row_ids/target` | 정렬 오프셋의 row_id 해석(점프 스캐너) |
| `GET /tables/{t}/export` | 필터/정렬 반영 CSV 스트림(최대 ~100만 행) |

### 이력 / 감사
`GET /audit_logs/recent` · `GET /audit_logs/transaction/{tx_id}` · `GET /tables/{t}/rows/{id}/history` · `GET .../cells/{col}/history` · `GET /dashboard/summary`

#### 재교정률 (`/dashboard/summary` → `recorrection`)
핵심가치 #1 **최소 공수 교정**([SYSTEM_OVERVIEW §1](../overview/SYSTEM_OVERVIEW.md))의 **보조 계기**. 정의·집계는 `crud.get_recorrection_stats`([data_model §2.3](./data_model.md) 참조), 응답 래핑은 `main._get_recorrection_stat`.

> **⚠️ 2026-07-29 — "유일한 계기"가 아닙니다.** 정본 계기는 SSOT §1이 정의하는 **완료까지의 상호작용**으로 교체됐고(사용자 확정), 재교정률은 보조로 강등됐습니다(원인이 UI 공수인지 데이터 품질인지 분리되지 않고, 대량 트랜잭션 포함 여부로 2.01%↔13.13% 6.5배 희석 — 사유 전문은 [data_model §2.3](./data_model.md)). **`/dashboard/summary`의 `recorrection` 필드는 정본 계기가 아닙니다** — 정본 계기는 자기 필드·자기 항목을 갖습니다. 이 항목에 얹지 마십시오(두 값은 뜻도 분모도 달라 한 계약으로 묶을 수 없습니다). 아래 계약은 재교정률의 것이고 강등과 무관하게 그대로 유효합니다.

- **응답 형태**: `{window_days, measured_cells, recorrected_cells, rate_pct, unavailable_reason}`. `rate_pct`는 표본 0 또는 집계 실패 시 `null` — 0%로 위장하지 않는다. 소비자는 **분모(`measured_cells`)를 반드시 함께 표시**한다.
- **비용 방어 2중화**: ① `RECORRECTION_CACHE` 60초 TTL(대시보드 로드마다 GROUP BY 금지) ② PostgreSQL `SET LOCAL statement_timeout`(`RECORRECTION_TIMEOUT_MS`, 기본 1500ms). 타임아웃 시 `db.rollback()` 후 `rate_pct=null` + 사유 — **지표 한 칸이 비는 것이 대시보드 전체가 느려지는 것보다 낫다.**
- **`unavailable_reason`은 실제 원인을 지목한다 (2026-07-29 F6 쌍둥이 — 상호작용 점수와 동일 규율).** 타임아웃일 때만 시간 초과 + `idx_audit_user_recorrection`를 말하고, 그 외에는 `집계 실패 — [예외타입] 첫 줄`을 싣는다. 종전 고정 문구("집계 시간 초과 또는 실패 (idx_audit_user_recorrection 인덱스 확인)")는 어떤 실패든 인덱스를 지목해, 컬럼 누락 같은 사고가 인덱스 문제로 읽혔다.
- 계산은 엔드포인트 **맨 마지막**에 수행한다(타임아웃 rollback이 앞선 집계를 건드리지 않도록).
- ⚠️ `/dashboard/summary` 자체가 테이블마다 `count(*)`를 도는 무거운 엔드포인트다(2026-07-27 실측 ~1.5s, `bonding_map` 176만 행 단독 0.5s). **주기 폴링에 얹지 말 것** — 클라이언트는 별도 간격(5분)으로 비차단 조회한다.

#### 상호작용 점수 (`/dashboard/summary` → `effort`) — **정본 계기** (2026-07-29 신설)
핵심가치 #1 **최소 공수 교정**의 **정본 계기** — 한 교정 tx를 완료하는 데 사람이 쓴 손의 양(낮을수록 좋음). 정의·집계 결정은 [data_model §2.4](./data_model.md)가 정본, 집계는 `crud.get_effort_stats`, 응답 래핑은 `main._get_effort_stat`.

- **수집 계약 (`PUT /tables/{t}/data/updates`의 선택 필드)**: `effort: {session_id, key, mouse, nav, nav_preserved}`.
  - **선택(OPTIONAL)이 계약의 핵심이다.** 워커·인제션·체인 경로는 같은 엔드포인트를 쓰지만 사람이 없다 — **없음 = 미계측이며 0이 아니다.** 서버는 미계측 tx의 행을 남기지 않는다(0으로 채우면 평균이 조용히 희석된다). 내부 필드도 전부 선택이며 `nav_preserved`를 아직 보내지 않는 클라도 정상이다.
  - `nav` = 컨텍스트를 **잃는** 전이 / `nav_preserved` = **유지하는** 전이. 둘 다 원시 카운트로 저장하고, 허용목록 판정은 **조회 시점 해석**으로 남긴다([data_model §2.4](./data_model.md)).
  - 🚨 **계기는 자기가 재는 작업을 절대 파괴하지 않는다 (2026-07-29 F4 — 총괄이 자기 지시를 부분 철회).** 음수·비정수(문자열·소수·boolean 포함)·모르는 키·`session_id` 누락·객체가 아닌 blob — **전부 계측만 폐기하고 교정은 그대로 수행한다.** 종전 계약(쓰기 전에 400으로 거절)은 클라 카운터 버그 하나가 **데이터 입력 전면 중단**으로 번지는 구조였다. 카운터 하나를 잃으면 지표의 한 행이 없어지지만, 쓰기를 거절하면 사람이 자기 교정을 잃는다 — 후자가 핵심가치 #1을 직접 위반한다. (그래서 `EffortReport`의 모든 필드는 `Any`이고 `GeneralUpdateBatch.effort`도 `Any`다 — pydantic이 422로 먼저 쳐내면 그 자체가 쓰기를 막는다.)
  - **폐기는 조용하지 않다** — 사유는 응답의 `effort_error`(문자열, 정상 시 `null`)와 서버 로그(`logger.error`, `[EffortMetric]`)에 **문제의 키 이름과 함께** 남는다. **조용한 클램프·캐스팅은 여전히 없다**(틀린 값을 그럴듯하게 만드는 것이 계기에는 가장 큰 손해다).
  - ⚠️ **모르는 키는 무시하지 않는다(키 이름 포함 보고).** pydantic 기본값은 미선언 키를 **조용히 버리는 것**이라, 클라가 새 카운터를 보내도 에러 없이 사라지고 나머지 값이 정상이라 아무것도 고장 나 보이지 않는다(2026-07-29 실측 — `nav_preserved` 도입 직전 그 상태였다). **조용히 버려진 값은 보내지 않은 값과 구별되지 않는다**는 이 프로젝트의 상습 결함 형태이고, 이 계기는 소급 재계산이 불가능해 발견 시점엔 그 기간의 기준선이 이미 없다. **빠진 키는 정상, 모르는 키만 오류.** 같은 규율이 **최상위 키**에도 적용된다(F7): `GeneralUpdateBatch`는 `extra="allow"`로 받아 `{"efort": {...}}` 같은 오타를 `effort_error`로 보고한다 — 종전에는 조용한 200이라 그 페이지의 저장 전부가 **영구 미계측**이 됐다.
  - 기록은 교정 커밋 **이후** 별도 트랜잭션(`crud.record_interaction_effort`). 실패해도 요청은 200 — **계측이 계측 대상을 깨뜨리지 않는다.**
  - 🚨 **응답 `effort_recorded`(bool)가 클라 카운터 리셋의 유일한 게이트다 (2026-07-29 F1).** `true` = 이 요청이 공수 행을 실제로 저장했다. `false` = 저장 안 됨(미계측·폐기·**no-op 저장**) → 클라는 카운터를 **리셋하지 않고 다음 시도에 계속 싣는다**. no-op이 왜 치명적이었나: 값이 이미 같은 셀을 고치면(오래된 그리드, 또는 `crud`의 `has_changed` 공백/숫자 정규화) 감사 로그가 없어 공수도 기록되지 않는데, 클라는 `res.ok`만 보고 카운터를 **지웠다**. 20키+5클릭을 날린 뒤 3키+1클릭으로 다시 성공하면 **제품에서 마찰이 가장 큰 2회 시도 교정이 데이터셋에서 가장 낮은 점수(6 vs 실제 ~40)로 기록**된다 — 계기가 핵심가치 #1이 잡아내야 할 바로 그것과 **역상관**이 된다. **기록 조건 자체는 바뀌지 않았다**(no-op은 완료된 교정이 아니고, 기록하면 `measured_ratio` 모집단 정합이 깨진다). 바뀐 것은 **서버가 기록 여부에 대해 진실을 말한다**는 것뿐이다.
- **응답 형태**: `{window_days, avg_score, tx_count, session_count, weights, measured_ratio, unavailable_reason}`. `avg_score`는 표본 0 또는 집계 실패 시 `null` — 0점으로 위장하지 않는다. 소비자는 **`measured_ratio`(커버리지)를 반드시 함께 표시**한다. `weights`를 동봉하는 이유는 그 숫자가 어떤 배점으로 읽힌 것인지 없이는 해석이 불가능하기 때문이다.
- **비용 방어 2중화**(재교정률과 동일): ① `EFFORT_CACHE` 60초 TTL ② `SET LOCAL statement_timeout`(`EFFORT_TIMEOUT_MS`, 기본 1500ms). 타임아웃 시 `db.rollback()` 후 `avg_score=null` + 사유. 두 계기 모두 엔드포인트 **맨 마지막**에서 각자 rollback하므로 한쪽 실패가 다른 쪽을 오염시키지 않는다.
- **`unavailable_reason`은 실제 원인을 지목한다 (2026-07-29 F6).** 타임아웃일 때만 시간 초과 + `idx_effort_window`를 말하고, 그 외에는 `집계 실패 — [예외타입] 첫 줄`을 싣는다. 종전에는 어떤 실패든 "집계 시간 초과 또는 실패"라는 고정 문구여서, 컬럼 누락 같은 사고가 **인덱스 문제로 읽히고 당직자가 애초에 원인이 아닌 인덱스를 손보러 갔다.** (✅ 재교정률 `_get_recorrection_stat`의 쌍둥이 문구도 **2026-07-29 M4 라운드에서 같은 규율로 수리**됐다 — 위 재교정률 항목 참조.)

| 경로 | 용도 |
|---|---|
| `GET /api/effort/config` | **배점·전이 선언의 유일한 정본**(`config/effort_metric.json`). 응답 `{weights{key,mouse,nav,nav_preserved}, context_preserving_transitions[{from,to}]}`. 라우트는 **정확 일치**로만 판정하며 **와일드카드(`*`)는 거절**된다(무력 리터럴이 선언처럼 보이는 것을 막는다 — 거절은 로그 + 서빙 목록 누락으로 관측 가능). 클라는 자기 사본을 두지 않고 이것을 읽어 적용한다(`/api/maps/paint-rules`가 `binding`을 서빙하는 것과 같은 패턴 — 배점을 클라에 하드코딩하면 서버 집계와 화면이 조용히 갈라진다). `context_preserving_transitions`는 **0점으로 칠 전이의 허용목록**이며 **기본은 상실(선언 없으면 이동 가중치 부과)** · 목록은 비어서 출발하고 항목은 라우팅 소유자 제안 + 총괄 승인으로만 늘어난다 |

### 소스 / 레이어링
| 경로 | 용도 |
|---|---|
| `GET .../{col}/sources` | 셀에 중첩된 전 소스값 + 계산 우선순위 |
| `DELETE .../sources/{source}` | 소스 1개 제거 |
| `PUT .../{col}/priority` | 표시 소스 수동 핀/해제 |
| `PUT /tables/{t}/cells/priority/batch` | 일괄 핀 |
| `POST /tables/{t}/cells/sources/delete/batch` | 일괄 소스 삭제 |
| `POST /tables/{t}/cells/sources/query` | 다중 셀 소스 조회 |

### 그래프 조회 (read-only — 웹서버가 `graph_nodes/edges` 직접 조회, 워커 미경유)
| 경로 | 용도 |
|---|---|
| `GET /graph/stats` | label/edge_type 카운트 + `last_sync`(graph_sync_state) — 뷰어 첫 화면 |
| `GET /graph/neighbors` | k-hop(1\|2) 이웃 서브그래프. **노드 limit 하드캡 500, 초과 시 `truncated`**, (from,type)/(to,type) 인덱스 경로만(C-7) |
| `GET /graph/nodes/search` | identity 시작일치 자동완성(limit 캡 50). **[F3] `ILIKE 'q%'` → 바이트 순서 범위 술어로 교체**(`value_suggest.prefix_conditions` 공용 — §2.1). 대소문자 무시 의미론은 그대로이고, LIKE가 없어져 이스케이프할 메타문자도 없다. **빈 q + label = 라벨 전체 리스팅**(identity 오름차순, limit/offset, 캡 200 — 뷰어 라벨 노드 리스트용, 전 테이블 덤프 금지 유지) |
| `POST /graph/trace` | **[G2] 멀티 시드 BFS 합집합** — depth 1..3(기본 2), 시간 필터(NULL event_time 통과)·edge_types 필터, 노드 하드캡 1000, `missing_seeds`/`truncated`. 의미 검증 실패는 400 |
| **`GET /graph/chip-trace`** | **[2026-07-30 `8670e3b`·`ae2811c` · 경계 계약]** 칩(`CoreCell`) 1개의 이력을 **웨이퍼 스코프**로 추적. **파라미터는 `identity` 하나 — depth는 없다**(노출하면 홍수가 되돌아온다: 같은 시드의 `POST /graph/trace` depth 2가 1,000 노드 캡을 태우고 그중 **994개가 형제 CoreCell**). BFS가 아니라 **고정 형상**이고 다리마다 인덱스 집합 조인 1회(실측 234노드/694엣지·57ms). 형상 3다리 — ① 칩 자신 `BONDED_TO→BaseCell`·`TRANSFERRED_TO→DtCell`(**스코프를 벗어나는 유일한 자리**, 형제 셀 불포함) ② 웨이퍼 `FROM_CORE→Core` ← `PERFORMED_ON` 인바운드 ③ 잎 `USED_KNOB`/`USED_RECIPE`/`EXECUTED_BY`(**되확장 금지** — 정책 엔진 G2.5가 없으므로 질의 형상이 강제). **다리별 닫힌 어휘 5종 + 스코프 1종, 빈 홉 금지**: `recorded` · `none_recorded`(선언은 있고 행 0) · `not_declared`(매핑이 그 `(type,target)`을 더는 선언하지 않음) · **`mapping_unavailable`**(**선언을 읽지 못했다** — 파일 저장 중·거부·부재. `not_declared`**만** 이것으로 강등하고 `recorded`/`none_recorded`는 실제로 읽은 행의 결론이라 강등하지 않는다. 503으로 거부하지 않는 이유: 참인 절반을 함께 버린다) · **`not_reached` + `blocked_by`**(앵커 다리가 죽어 **묻지 않았다** — `none_recorded`로 말하면 "이 웨이퍼는 knob을 쓰지 않았다"는 조작이 된다) · **`scope_unresolved`**(Core 주장이 0개 또는 2개 이상, **또는 그 다리가 잘림** — 추측하지 않고 칩 절반만 답하며 `scope_candidates` 보고). **절단은 상태가 아니라 다리별 `truncated`+`capped_at` 플래그**이고, `count`(엣지 주장 수)와 `node_ids`(개체 수)는 **의도적으로 다르다**. 응답에 **`declaration{status, path, exists, rejected[]}`**를 실어 `mapping_unavailable`의 원인을 밖에서 볼 수 있게 한다. 시드 부재 404. 계약 전문 [ONTOLOGY_GRAPH_SPEC §7.5d](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| `GET /graph/mapping-summary` | 로드된 온톨로지 매핑 요약(enrichment 승격 포함) — 클라이언트 추적 진입점 활성 판정용. **[`530fdfd` 2026-07-30] 거부된 매핑을 같은 응답에 싣는다**: `rejected[{scope, table, reason}]`·`rejected_count`·`source{path, exists}`. `scope`는 `table`(그 테이블만 스킵) \| `file`(파일 미판독 또는 v1 형식) \| `enrichment`(RESOLVED_AS 승격 사망). 로더 계약이 "무효 테이블은 로깅 후 스킵"이라 **컬럼 하나 rename에 그 테이블의 온톨로지가 통째로 사라지고 표면에는 아무것도 안 나왔다**(성공 개수만으로는 "안 늘었다"와 "죽었다"가 구별 불가). 🔴 **파일 부재는 거부가 아니라 `source.exists`로만 말한다** — 정상 상태에서 반드시 비어 있어야 하는 목록이고, 늘 뭔가 들어 있는 사유 목록은 곧 무시당한다. `tables` 형태는 불변(가산적 필드) |

### 인제션 / 어드민 / 내부 / 맵 / WS
| 경로 | 용도 |
|---|---|
| `GET /health` | **[운영]** 헬스체크. **항상 JSON**, 정상 200 / `unhealthy` 503(`degraded`는 200). 본문 `{status, checked_at, problems[], checks{database, workers, outbox, supervisor, config_backup}}`. DB 프로브는 2초 타임아웃 + 스레드 격리 + **중복 프로브 차단**(직전 프로브 미귀환이면 즉시 `timeout`으로 응답 — 헬스체크가 2차 장애가 되면 안 된다), `Cache-Control: no-store`. 판정 규칙은 §1.3 |
| `POST /tables/{t}/upload` | 클라이언트 파일을 `raws/`로 업로드 |
| `POST /api/graph/sync` | GraphSync 워커(:8090)로 프록시 — **백필/복구 도구**(주 경로는 materializer 자동 승격, [event_driven_backend §4](./event_driven_backend.md)) |
| `/admin/outbox/*`, `/admin/file-ingestion/*` | 아웃박스·파일적재 데드레터 관리·재시도 |
| `GET /admin/file-ingestion/active` | **[P1]** 진행 중 인제션 스냅샷(웹서버 인메모리 `ingestion_activity.py` 레지스트리 — TTL 퇴거 포함). admin File 탭 진행 섹션·재기동 경고의 데이터원 |
| `GET /api/bonding-plan/core-summary` | **[본딩 M1]** 코어(lot,slot) 역할별 집계(`bonding_plan.py` — 역할 바인딩 config, `remaining = total − defect − eds_fail − used`, align은 서버 단독 변환). `region` rects 파라미터, 잘못된 region 400 |
| `GET /api/maps/overlay` | **[M2 · 맵 인프라]** 임의의 맵들을 타깃 맵 **프레임 좌표로 정렬**해 `overlays[]` 반환(`map_overlay.py`). `sources`는 `table` 또는 `table:key` CSV(키 생략 시 `target_key` 승계, **최대 8종**), 셀 상한 20,000(초과 시 `truncated:true`). **align 규율: 소스·타깃 `wafer_map_metadata` 델타에서만 유도 > identity. 선언(`align_overrides`) 레이어는 2026-07-27 제거 — 정렬의 근거는 메타 하나뿐이다. 메타 부재는 실패가 아니며, 변환을 계산할 근거 자체가 없을 때만 `status: align_unavailable`. 변환기는 `map_overlay.resolve_map_transform` 단일 진입점이며 `bonding_plan`/`transfer_plan`의 가용량 산출도 이것을 쓴다.** 잘못된 `sources`/`limit` 400 |
| `GET /api/maps/paint-rules` | **[M2]** 페인트 잠금 선언 정본(`config/map_overlay_config.json`의 `paint_lock`) — **기존엔 클라 하드코딩 `'F'`**였다. 응답 `{table, rules{enabled, blocking_values, from_overlay, message}}`. 클라는 404/405만 "선언 없음"으로 해석하고 네트워크·5xx는 직전 잠금을 유지한다(fail-open 금지) |
| `GET /api/maps/preset-routing` | **[F5 2026-07-30 · 맵 인프라]** `(table, map_key)` → **이 맵을 열 물리 규격(프리셋)**(`map_preset_routing.py`). 해석 순서가 계약이다: ①`product_lookup`(선언된 제품코드 조회 테이블, **`LIMIT 1` 1회**) → `product_presets` → ②`rules`(순서 있는 텍스트 패턴, **첫 매치 승리**) → ③라우팅 없음. **`status != "ok"`이면 `preset_key`/`preset`은 항상 `null`** — 그럴듯한 프리셋을 지어내지 않는다(틀린 규격은 `inside`를, 따라서 저장 가능 집합을 바꾼다). **①의 미선언·조회 miss·테이블 부재는 전부 정상**이고 조용히 ②로 떨어진다(조회 테이블은 운영에만 있고 그마저 불완전하다 — 환경 분기는 코드에 없고 **선언만 다르다**). 결과는 로그가 아니라 `lookup{declared,status,product_code}`로만 드러난다. **절대 우선순위 `wafer_map_metadata` > 라우팅 > 패널**은 서버가 강제한다 — 규격이 등록된 맵은 `status: meta_present` + `preset_key: null`(클라가 메타를 덮을 수 없다). 키는 전부 `map_overlay.canonical_map_key`/`canonical_bind_value` 경유(7b 단일 정규화). `matched_by{stage, rule, lot, product_code}`가 어느 규칙이 왜 걸렸는지 싣는다 |
| `GET /api/transfer-plan/stages` | **[M2]** 선언된 전사 stage 목록 + 역할 연결 상태(config 해석만 — 행 조회 없음). 역할·`plan_store` 누락은 `missing` 부분 가동(에러 아님) |
| `GET /api/transfer-plan/source-summary` | **[M2]** 단계별 소스 (lot,slot) 가용 집계(`transfer_plan.py`). 공통 형태 `{identity, stage, source_kind, sources, chips{total, fail_breakdown, transferred, remaining, remaining_reliable}, history, warnings}`. tape-kind는 `by_core`(7키 `core_id/core_lot/core_slot/total/fail/used/remaining`) + `by_core_origin`(`"log"` 정확 \| `"area_map"` 강등, 후자는 `fail=null`) 동봉. **degraded 시 `remaining: null` + `remaining_reliable: false` + `warnings[source_degraded]` 3층 방어** — 소비자가 초록으로 뒤집을 수 없다. **칩 좌표 목록은 반환하지 않는다**(집계만). 미선언 stage 404. **[BIN 축 2026-07-27]** `bins=1,2`를 주면 `bins{axis, scope, entries[], truncated, cells_truncated, unbinned_cells, cells_total, population_ref}` 동봉 — 파라미터가 없으면 블록도 없다(기존 응답 불변). 항목 `status`는 `ok`/`bin_absent`/`unknown` **3종이고 `0`이 어느 것도 대신하지 않는다**(`0`은 '다 썼다'로 읽혀 신뢰 불가한 가용에서 확정 잔여를 만든다). 신뢰 불가면 `remaining: null`. 축은 `source.bin_map` **선언**으로만 성립한다 — 미선언은 `axis:"unavailable"` + `bin_axis_unavailable` 경고(추측 금지: 라이브 `dt_map.val`은 출신 코어 식별자다). `scope=lot`은 슬롯 없이 로트 전체를 묻고 `chips` 없이 `{slots, slots_origin, slots_status, by_slot, bins}`만 답한다(`slot` 동반 시 400). `by_slot`은 슬롯 한 줄씩 + `map_exists` — **로트 데이터 품질 진단면**이라 슬롯 목록은 선언된 `source.lot_membership`에서 오고, 맵 폴백은 `slots_origin:"map"`+`lot_membership_degraded`로 한계를 말하며, 열거 불가는 빈 목록이 아니라 `slots:null`+`slots_status:"unknown"`이다. 합산 `bins`는 `basis:"pool_sufficiency"` — **배분이 아니라 충분성 판정**이다. 상한 distinct BIN 200 · 좌표 200k · 슬롯 팬아웃 50 |
| `GET /api/transfer-plan/validate` | **[M2-v2]** 계획 검증 — **계획 정체성은 `(ref_table, map_key)`**(구 `plan_id` 폐기, 계획 헤더 테이블도 계획 맵 사본도 없다). stage는 `stages.*.target_map.table` 역인덱스로 유도하며 미선언 맵은 404가 아니라 `stage_unknown` 경고 + `status: unverified`(임의의 맵도 열 수 있어야 하므로). `status`는 `ok`/`warnings`/`unverified` 3값 — **"검사 안 함"과 "이상 없음"을 같은 값으로 내지 않는다.** **[M2.6 `0f8d35f`]** 계획 저장소는 `plan_store.registry` → `map_split_registry` 하나이고 구간·자재는 `bands` JSON에서 읽는다. **수량은 저장분을 읽지 않고 파생**한다(`층 수 = to − 이전 to` · `소요 = 칠한 셀 수 × 층 수` · `매당 = ceil(소요/자재 수)`) — 그래서 칠한 셀 집계가 불완전하면 **파생 전체를 게이트**해 `unverified`로 떨어뜨린다(0으로 읽으면 부족 경고가 조용히 죽는다). 캡 절단은 역할별로 `result_truncated`를 표면화하고 역시 `unverified`를 강제한다. `plan_store.registry`(필수 역할키 `bands` 포함) 미구성만 404 |
| `/admin/chain/rules`, `/admin/mappers/list` | 체인 규칙·맵퍼(AST 파싱) 목록 |
| `/admin/auto-update/{status,run-now,toggle}` | 스케줄러 상태(각 항목에 `active` 부가)·즉시실행·수집기 active 토글. toggle body `{"script": "<workspace>/<script.py>", "active": bool}` → `config/auto_update_control.json` 갱신(스케줄러 핫 반영, 재기동 불필요; 미존재 404·검증실패 400). **run-now는 active 무관 실행**(수동 실행은 명시적 의도) |
| `/admin/reload-configs` | 로컬 캐시 리로드(`models.refresh_dynamic_models` — 신규 테이블 **물리 CREATE 포함**, 이슈 #7) + `SYSTEM_RELOAD` 발행. CREATE가 발행보다 선행(웹서버가 1차 DDL 소유자) |
| `/admin/scripts/{list,code}` | 브라우저 코드 에디터(경로 traversal 가드) |
| **🔒 `/admin/*` 전체 (API 라우트 22개 — 커밋 트리 `77d27d3`에서 `@app.<verb>("/admin` 실측, 페이지 서빙 2개 제외. ⚠️ 라우트가 늘 때마다 낡는 수이고, 커버리지의 정본은 수가 아니라 `test_admin_auth.py`의 라우트 테이블 열거다)** | **공유 토큰 게이트**(`admin_auth.py`, 2026-07-27). 토큰은 `ASSY_ADMIN_TOKEN` 환경변수, 제시는 `X-Admin-Token` 헤더, 비교는 `secrets.compare_digest`. **토큰 설정 시 조회 포함 전부 필수**(소스 코드 반환·파이프라인 열거도 유출이다), 미제시 401·불일치 403. **미설정 시 둘로 갈린다** — **strict 3라우트**(`POST /admin/scripts/code`·`POST /admin/auto-update/run-now`·**`POST /admin/retroactive/{op}/run`** — 정본은 `test_admin_auth.STRICT_ADMIN_ROUTES`)는 **503**(코드 실행 또는 대량 쓰기 경로는 fail closed. 소급 실행이 여기 들어간 이유는 코드 실행이라서가 아니라 **같은 아웃박스로 같은 스케줄러 프로세스에 닿고 피해 계급이 같기** 때문이다 — 테이블 전체 재작성·소스 주장 회수·노드 삭제), 나머지는 **그대로 동작**(첫 재기동에 운영자가 어드민 전체에서 잠기지 않게 — 사용자 확정). 예외는 페이지 서빙 `GET /admin`·`/admin.html` 2개뿐(브라우저 내비게이션이라 헤더를 붙일 수 없고, 표시 데이터는 전부 게이트된 JSON 라우트에서 온다). **`GET /health`는 무인증 유지**(모니터링 표면). 토큰이 **비-ASCII면 인증이 구조적으로 불가**(헤더는 latin-1 디코딩)하므로 `configured_token()`이 거부하고 기동 배너가 `ERROR`로 알린다 — 미설정 상태로 취급하며, 조용히 전 라우트를 죽이지 않는다. 게이트가 낸 거부에는 **`WWW-Authenticate: X-Admin-Token`**이 붙는다: 핸들러가 자기 이유로 내는 동일 상태코드(예: `_resolve_admin_script_path`의 격리 403)와 클라가 구별할 수 있어야 하기 때문이다. 커버리지는 하드코딩 목록이 아니라 `test_admin_auth.py`가 **FastAPI 라우트 테이블을 열거**해 단언 — 신규 **HTTP** admin 라우트가 게이트 없이 등록되면 스위트가 빨개진다(⚠️ WS 라우트·mount는 `methods`가 `None`이라 열거에서 빠진다). **[`F8` 2026-07-30] 토큰 지문** — 웹서버와 데몬 3종이 기동 시 `token fingerprint <sha256 앞 8자리 hex>`를 찍는다. 유출 규율(값은 로그·감사행·에러 바디·트레이스백 어디에도 남지 않는다)의 **유일한 예외**이며, 그 예외가 필요한 이유는 배너가 `is set`만 말하던 시절 **"양쪽이 같은 토큰인가"를 제품이 답할 수 없었기** 때문이다. 절단은 보안 손실이 아니라 이득이다(전체 다이제스트는 추측을 확정해 주고, 8자리는 2^32당 1건의 오탐을 남긴다 — 실제 방어선은 토큰 엔트로피). 미설정은 `none`, 비-ASCII는 `unusable-non-ascii`로 **상태마다 다른 표기**(비교하는 운영자가 한쪽의 침묵을 보지 않도록). 설정 절차 [DEPLOY_SETUP §1-4](../guide/DEPLOY_SETUP.md) · 프록시 함정 [§1-5](../guide/DEPLOY_SETUP.md) |
| **🔒 `/internal/events/*` 4종** | **같은 토큰으로 게이트**(2026-07-27). 조회 전용 admin은 잠겨 있는데 **임의 dict를 접속 중인 전 WS 클라이언트에 중계**하고 `audit_cache`에 주입하는 이 경로가 무인증이던 비대칭을 해소. 워커 3종(`run_watcher`·`chain_ingestion_worker`·`graph_sync_worker`)이 `admin_auth.internal_event_headers()`로 헤더를 붙이며, **런처 환경을 상속**하므로 별도 설정이 없다. 미설정 시 개방(admin과 동일 규칙). **[`F8` 2026-07-30] 전송 계층은 `server/internal_event_client.py`가 독점한다** — 발신자가 직접 `requests.Session()`을 만들면 `trust_env=True` 기본값 때문에 `HTTP_PROXY`·**Windows 프록시 레지스트리**를 타고, `ProxyOverride`의 `<local>`은 **점 없는 호스트명만 우회**하므로 `127.0.0.1`이 사내 프록시로 나가 **403**으로 거절됐다(운영 장애). 세션은 `trust_env=False`이며, **발신자가 자기 클라이언트를 만들면 테스트가 실패**한다(같은 결함이 발신자별로 3번 재발한 이력) |
| **정적 폴백 containment** | `GET /{file:path}` SPA 폴백은 **결과 기반 containment 검사** 후에만 파일을 낸다(`abspath(join(dist, name))`이 dist 하위인지). 상단의 접두 denylist는 **API 섀도잉 방지용이지 보안 경계가 아니다** — 접두 매칭이라 `../../server/config/table_config.json`이 그냥 통과했고, 2026-07-27 이전엔 **무인증으로 임의 파일**(win.ini, `admin_auth.py` 자신)을 200으로 반환했다. 이 구멍은 admin 조회를 잠근 근거 자체를 무효화했다 |
| `POST /internal/events/{batch-refresh,broadcast,file-processed}` | 데몬→웹서버 콜백. batch-refresh 수신부는 msg 재구성 시 `total_log_count` 동봉(체인 passthrough 경로와 대칭 — P1 후속), broadcast/file-processed는 진행 레지스트리 인터셉트 겸함 |
| `POST /internal/events/ingestion-state` | **[P1]** watcher → 진행 상태 push(QUEUED/PROCESSING/FINISHED, heavy만 명시 통지). **WS 브로드캐스트 없음** — 레지스트리 전용 내부 이벤트 |
| `/map-presets`, `/api/map-presets` | 맵 지오메트리 프리셋(`config/maps.json`) |
| `GET /enrichment/rules` | Enrichment 규칙 메타. 참조뷰는 **`label` + `candidate_for` 둘만** 노출(설정 관점 정본 [guide/config/enrichment_rules §6](../guide/config/enrichment_rules.md)) — 쿼리 본문·limit은 노출 금지. **[F9 2026-07-30, 총괄 승인] `candidate_for`는 가산적 필드**: 노출값은 뷰 결과 **컬럼명**이고 그 컬럼명은 `/references/{i}` 응답 헤더에 이미 나타나므로 신규 노출 0. 없으면 클라가 「어느 뷰가 후보 원천인가」를 **유도**해야 하고, 유도는 맵 오버레이 `derive_table_binding`이 라이브 DECOY를 만든 실패 계급이다. 소스: `config/enrichment_rules.json`(`enrichment_config.py` 로더, 요청 시 재로드) |
| `GET /enrichment/rules/{rule}/references/{i}` | 참조뷰 서버측 실행 — `params`는 decision_key 컬럼만 허용(그 외 400), 파라미터 바인딩 전용(주입 불가), 서버 LIMIT 강제(기본 200/최대 1000), 규칙·인덱스 미존재 404. **[F9] 실행은 `enrichment_config.execute_reference_view`가 유일한 정의**(라우트가 갖고 있던 인라인 래핑 사본 제거) |
| `GET /admin/config/resolve?domain=` | **[F9 2026-07-30]** config **선언의 효과**. `{domains:[{domain, title, sources[], settings[], effective[], ineffective[], rejected[], counts}], vocabulary}`. 🔴 세 모집단을 **이름으로** 반환하고 사람이 읽을 문장(`detail`)을 **서버가 만든다** — 클라는 그것을 **그대로 렌더하고** 「효과 없음」을 스스로 판정하지 않는다(하드코딩 사본 계급 U6). ✅ **클라 렌더러 착지 2026-07-31 `93610cb`** — 어드민 Overview 탭의 세 번째 계기 줄(`admin.js`의 `refreshConfigResolve`, 뷰 모델 `client2/src/config_resolve_view.js`). 계약은 여전히 계약이고 이제 **양쪽 다 채점된다**: 금지 절반(**INV-F9-7** — 사유 4단어가 `client2/src`에 **소스 리터럴로** 있으면 divergence)에 더해, 긍정 절반(**INV-F9-4** — 렌더된 문장 == 서버 `detail`)이 `PENDING`에서 **실행 채점**으로 바뀌었다(하네스가 뷰 모델을 임포트해 벡터 페이로드를 먹인다).
  - 🔴 **읽기 실패는 상태코드가 아니라 헤더로 분류한다** (`1dc761b`). **401/403이 우리 게이트라는 보장은 상태코드에 없다** — 그 판정은 **`WWW-Authenticate: X-Admin-Token`**이고, 앞단 프록시는 같은 포트에 자기 `Basic realm=…`으로 답한다(2026-07-30 loopback 인시던트가 그 모양이었고 오후 하나를 썼다). 클라 판정자는 `admin.js`의 `isGateRejection` **하나**이고 뷰 모델은 그것을 **인자로 받는다**(사본 금지).
  - 🔴 **그래서 그 헤더는 CORS `expose_headers`에 있어야 한다** (`cde3398`). 없으면 브라우저가 **교차 출처에서 그 헤더를 지우므로**, vite dev(`:5173`)에서 **진짜 게이트 거부가 「앞단이 답했다」로 확신 있게 잘못 표시된다.** 같은 출처(`:8080`/`:8081` 직접 서빙)에서는 원래 읽혔다 — **이 결함은 dev 오리진에서만 보인다.** 값은 헤더의 **이름**뿐이라 비밀이 없다. 목록의 정본은 `server/main.py`의 `CORSMiddleware` 한 줄이다. 🔴 **INV-F9-8 — `detail`은 운영자가 읽는 최종 문자열이다**(`f9289f6`): Python repr(`['slot']을(를)`)도 리터럴 마크다운(`**…**`)도 실어 보내지 않는다. 클라가 자기 문장을 짓는 것이 금지돼 있으므로 **하류에 고칠 자리가 없다** — 운영자에게 되비추는 값은 그가 편집한 파일의 문법인 **JSON으로** 적는다(JSON `true`는 `'true'`가 아니다). 사유는 닫힌 어휘 4종이고 **전부 런타임 열화 어휘 재사용**(`not_declared`·`mapping_unavailable`·`scope_unresolved`·`not_reached` — `main.CHIP_TRACE_*`의 부분집합임을 계약 테스트가 검사). `settings`는 실효값 + **그 값이 온 파일**을 말한다(파일 부재로 기본값인 경우 포함). **DB 질의 0건**(config만) — 그래서 요청 경로에 앉을 수 있다. 구현 `server/config_resolve_report.py`(`_RESOLVERS`에 도메인당 등록기 1개 — **2026-07-31 실측 `enrichment` · `virtual_join` 둘**이고 나머지 config가 같은 틀로 붙는다), 계약 벡터 `contracts/config_resolve_report/` |
| `GET /admin/retroactive/operations` | **[2026-07-31 `fbc1053`]** 실행 가능한 **소급 적용 연산 5종**의 인벤토리(`chain_replay`(R1) · `withdraw`(R2) · `enrichment_backfill` · `enrichment_confirm` · `graph_orphans`). 각 항목이 `params`·`cli`·`cli_only`와 함께 **`deletes` · `restartable` · `commit_granularity`**를 싣는다 — 🔴 **확인 문구 하나로 다섯 버튼을 덮으면 그 하나가 틀린다**: 넷은 값을 쓰고 청크 단위로 커밋되어 이어서 재실행되지만 `graph_orphans`는 **노드를 지우고 삭제 루프가 끝난 뒤에야 한 번 커밋**한다(중단 시 이미 지운 청크까지 통째 롤백). **DB 질의 0건**(config만)이라 `/admin/config/resolve`와 같은 자세로 요청 경로에 앉는다. 등록부는 `server/retroactive.py`이고 **새 연산은 하나도 구현하지 않는다**(카운트는 각 연산 자신의 dry-run, 실행은 같은 함수의 `apply=True`) |
| `GET /admin/retroactive/{op}/count` | **[2026-07-31 `fbc1053`]** 「이 연산은 몇 건에 영향을 주는가」 — 쓰기 없는 계기(구조적 `rollback`). 🔴 **모든 카운트가 `count_kind`를 함께 답한다**: `exact`(값싼 질의가 전부를 답함) · `sample`(`scanned`+`truncated` 동반, **테이블이 아니라 표본에 대한 수**) · `upper_bound`(`why_upper_bound`가 부족분을 **말로** 말한다). 다섯 중 셋은 「몇 건인가」가 곧 드라이런 자체(테이블 전수 + 매퍼)라 요청 경로에 정확한 수가 앉을 수 없고, 그래서 **어느 것도 정확하다고 주장하지 않는다**(F9 auto-confirm 드라이런의 자세를 일반화). 예산 파라미터는 `scan_limit`(기본 200 / 최대 2000, `retroactive.DEFAULT_SCAN_LIMIT`·`MAX_SCAN_LIMIT`)이고 **어떤 CLI의 `--limit`도 아니다** — 다섯 CLI에서 그 철자는 서로 다른 세 가지를 뜻하고 고아 스윕에는 아예 없다. 행을 실제로 훑지 않은 연산은 응답 `scan_limit`이 **`null`**이다(안 한 표본을 했다고 말하지 않는다). 실행이 막힐 상태면 `blocked_reason`(예: `auto_confirm_off`). 모르는 파라미터 이름은 400 — **오타가 조용히 무시되면 「0건」이 정답처럼 보인다** |
| **🔒[STRICT]** `POST /admin/retroactive/{op}/run` | **[2026-07-31 `fbc1053`]** 소급 실행을 **큐에 넣고 즉시 반환**한다(`{"params": {...}}`). `POST /admin/auto-update/run-now`와 **같은 형태** — `DatabaseOutbox` 한 줄(`RETROACTIVE_RUN`, `table_name="__retroactive__"`) + `NOTIFY outbox_event`이고, 실제 실행은 auto-update 스케줄러가 **자기 스레드**에서 한다(§4 · [AUTO_UPDATE_GUIDE §4-quater](../guide/AUTO_UPDATE_GUIDE.md)). 동기 핸들러는 브라우저가 포기할 때까지 요청과 웹서버 워커를 붙잡는다. 🔴 **파라미터 판정은 `retroactive.validate` 한 곳뿐**이라 라우트와 워커가 「무엇이 유효한 요청인가」에 다른 답을 낼 수 없다. R2의 두 거절(`user` 소스 거부 · 사람이 핀한 셀 건너뛰기)은 `chain_replay.withdraw_source` **안**에 있고 이 경로는 그 함수로 들어가므로 **어드민을 거쳐도 우회되지 않는다**(라우트의 재확인은 400을 즉시 주려는 편의이지 안전장치가 아니다 — 테스트가 라우트 가드를 monkeypatch로 지우고 워커를 몰아 그 사실을 고정한다) |
| `GET /admin/enrichment/auto-confirm/dry-run?rule=&limit=` | **[F9 2026-07-30]** 「이 규칙은 사람 없이 몇 건을 확정 가능한가」. `enrichment_analysis.run_auto_confirm_sweep(apply=False)`를 그대로 노출(이미 읽기 전용 + 구조적 rollback — 새 계기를 만들지 않았다). 🔴 **`apply`는 이 경로에 존재하지 않는다**(쓰기는 CLI 전용). `ignore_knob=True`로 **꺼진 규칙도 측정**한다 — sweep 자신이 그 플래그와 apply의 결합을 거부한다. 큐 walk이므로 표본(`limit` 기본 200 / 최대 2000)이고 `truncated`로 그 사실을 말한다. 선언이 없으면 500이 아니라 `refused_reason: "not_declared"` — 위 라우트와 **같은 어휘**다 |
| `WS /ws` | `ConnectionManager` 브로드캐스트 허브 |
| `GET /`, `/admin`, `/map-editor`, `/enrichment`, `/{file:path}` | SPA 서빙 + fallback(`graph.html`/`trace.html`은 catch-all 경유) |

---

## 2.1 고유값 조회 (`value_suggest.py`) — 입력 제안의 전제 프리미티브 (F3)

`GET /tables/{t}/columns/{c}/values?prefix=&limit=` → `{table, column, prefix, values[], truncated, limit, unavailable_reason}`.

**응답 계약의 핵심은 `truncated`다.** 조용히 자른 목록은 드롭다운에서 "이게 전부"라고 **암시**한다. 잘림은 `limit + 1`번째 값을 실제로 한 번 더 찾아 확인하며, 프로브 예산으로 멈춘 경우도 잘림이다.

### 왜 `SELECT DISTINCT ... LIKE 'p%'`가 아닌가 (1.75M행 `bonding_map` 실측)

두 함정이 독립적으로 있다.

1. **비-C 콜레이션에서 btree는 `LIKE '접두%'`를 못 쓴다.** 이 DB는 `Korean_Korea.949`다 → 인덱스를 고르고도 175만 엔트리를 Filter로 버려 **232ms**. 해법은 인덱스 자체를 바이트 순서로 만드는 것: `(lower(col) COLLATE "C", col COLLATE "C")` → `Index Cond: lower(base) >= 'c' AND < 'd'` / **0.2ms**. 인덱스 운영은 [POSTGRES_OPERATIONS §3.1](../guide/POSTGRES_OPERATIONS_GUIDE.md).
2. **`DISTINCT`의 비용은 답의 개수가 아니라 "51개를 채울 때까지 걷는 행 수"다.** 올바른 인덱스가 있어도 일치가 **성기면** 그게 테이블 대부분이 된다 — `leg`(175만 행에 distinct **342**)는 **161ms**, `base LIKE 'C%'`(일치 3개)는 **144ms**. 둘 다 드롭다운이 실제로 던지는 질의다.

그래서 이 모듈은 **loose index scan(skip scan)** 을 쓴다 — 첫 값을 찾고, 이후 "직전 값보다 큰 첫 값"을 반복 탐색한다. 커서는 `(lower(col), col) > (직전 lower, 직전 값)`이며 제안 인덱스에서 **인덱스 하강 1회**로 처리된다. 비용은 **반환하는 값 1개당 seek 1회**로, 테이블 크기·카디널리티와 무관하다.

**실측** (`suggest_values` 종단, 51값, 7회 중앙값, `bonding_map` 1,756,794행):

| 컬럼 | distinct | loose scan | `SELECT DISTINCT … LIMIT 51` |
|---|---|---|---|
| `leg` | 342 | **33ms** | 161ms |
| `base` | 397,602 | **32ms** | 0.3ms (빈 접두) · 144ms (`'C%'`) |
| `pkg_id` | 1,753,841 | **37ms** | 3,364ms |

숫자의 요점은 배율이 아니라 **평탄함**이다. 순진한 질의는 같은 테이블 안에서 0.3ms~3.4s로 네 자릿수 널뛰기를 한다 — 데이터에 따라 비용이 그렇게 흔들리는 프리미티브 위에는 드롭다운을 못 올린다.

### 규율

| 항목 | 규칙 |
|---|---|
| **선언이 권위** | `table`·`column`은 `crud.TABLE_CONFIG`의 `column_types`와 대조한다. 물리적으로 존재해도 미선언이면 400(`business_key_val`·`row_id` 등). 호출자 문자열이 SQL 텍스트에 들어가는 경로는 없다(Column 객체로 해석) |
| **정규화 사본 없음** | 반환값은 `map_overlay.canonical_key_value`를 통과한다 — `number` 선언이면 저장형 `1`(`1.0`이 아니라). **접두도 같은 함수로 정규화**하므로 `01`을 쳐도 `1`을 찾는다 |
| **대소문자 무시 = DB의 `lower()`** | 라이브 데이터는 대문자 코드다(`CDIE`). 소문자를 무시하는 드롭다운은 아무도 안 쓴다. 다만 **어느 `lower()`인지가 계약의 일부다** — 인덱스 키가 PostgreSQL의 `lower(col)`이므로 접두도 **같은 함수**로 접는다(`db_fold`, ASCII는 왕복 없이 처리). 파이썬 `.lower()`로 접으면 두 함수가 갈린다: 이 DB의 `lower()`는 U+00C4를 그대로 두는데 파이썬은 소문자로 바꾸므로, 저장된 값이 `truncated: false`인 채 조용히 답에서 빠졌다. **따라서 "같은 값"의 정의는 DB가 같다고 접는 범위까지이며 그 이상도 이하도 아니다.** `/graph/nodes/search`가 이 술어를 그대로 재사용한다 |
| **술어는 지킬 수 있는 것만 준다** | `prefix_conditions`가 내는 범위는 좁히기용 상위집합이 아니라 **정확한 범위**다(`f <= lower(col) < succ(f)` ⟺ 접두 일치). 상한 계산은 마지막 문자에서 포기하지 않고 **자리올림**한다 — 소비자 2(`/graph/nodes/search`)에는 파이썬 재검사가 없어서 술어가 곧 답이기 때문이다. 하한만 남은 필터는 "그 지점 이후 전부"가 된다 |
| **datetime 거부** | 400. 날짜 정규화를 새로 만드는 것은 "두 번째 정규화"이므로 하지 않는다 |
| **빈 값 제외** | NULL·빈 문자열·공백만 있는 값은 제안이 아니다. 판정은 canonical이 비었는지로 하며(SQL `col <> ''`는 공백 문자열을 못 본다), 접두 일치도 **파이썬에서 최종 판정**한다 → 범위 산술은 좁히기만 할 뿐 틀린 값을 만들 수 없다 |
| **못 하면 못 한다고 말한다** | 예외·시간 초과는 `values: []` + `unavailable_reason`. **시간 초과는 잘림이 아니다** — 인덱스가 없으면 seek마다 Seq Scan이 되어 몇 개만 건지고 끝나는데, 그 결과는 "짧지만 완전한 픽 리스트"로 읽힌다. 사유 문자열은 실제 원인을 지목하며 인덱스는 **정말 없을 때만** 이름을 댄다(대시보드 강등 지표 F6과 같은 규율) |
| **사유는 읽는 사람이 행동할 수 있어야 한다** | "인덱스가 없으니 `setup_db_performance.py`를 실행하세요"는 **빌더가 애초에 그 인덱스를 만들 생각이 없을 때 막다른 길**이다(`index_exclude`에 있음 / `index_columns` 목록 밖 / `index_min_rows` 미만 — 라이브에 임계 미만 테이블이 15개다). 그래서 사유는 정책 소유자인 `index_targets`에게 **직접 물어서** 만든다: 대상이면 재실행을 지시하고, 아니면 어느 노브가 막고 있는지와 무엇을 고쳐야 하는지를 말한다 |
| **무효 인덱스는 없는 것보다 나쁘다** | `to_regclass`는 INVALID 인덱스도 해석하므로 이름만 보면 "존재합니다"가 된다. 실제로는 플래너가 절대 안 쓰고, 빌더의 `IF NOT EXISTS`가 **그 이름을 영원히 건너뛴다** — 재실행해도 안 고쳐진다. 취소된 `CREATE INDEX CONCURRENTLY`가 남기는 상태이고, 가이드가 경고하는 워커 `idle in transaction` 상황에서 실제로 도달한다. 판정은 `indisvalid AND indisready`로 하고, 사유 문자열이 `REINDEX`/`DROP` 복구 명령을 직접 제시한다 |
| **노브는 config** | `config/suggest_config.json` — [config/suggest_config](../guide/config/suggest_config.md). 요청당 1회 스냅샷(핫리로드는 다음 요청부터) |

---

## 2.2 `/schema`의 `virtual_columns` — **알림이지 강제가 아니다** (2026-07-31 `9200f20`)

`GET /tables/{t}/schema`는 저장 컬럼(`columns`/`column_types`) 옆에 **승인된 virtual join이 이 테이블의 읽기 페이로드에 *덧붙이는* 컬럼들**을 별도 키로 싣는다. 항목 하나가 컬럼 하나이고 형태는 `{name, type, editable: false, right_table, rule, unresolved_label}`이다. 승인된 조인이 없으면 **`[]`** — 키는 항상 있다(모양이 안정돼야 클라가 존재 여부를 묻지 않고 읽는다).

**왜 `columns`에 이름을 더하지 않았나 — 그 선택이 이 라운드의 전부다.** `columns`는 「이 테이블이 **저장하는** 컬럼」이라는 뜻이고, 그 뜻에 기대는 소비자가 넷 있다. 이름을 합치면 넷이 전부 조용히 틀린다 — 그리드는 하드코딩된 시스템 컬럼 목록으로 편집 가능성을 유도하므로 **편집 가능한 컬럼으로 렌더**되고, 검색 드롭다운은 SQL이 닿지 못하는 이름을 제안하며, 맵 에디터의 push 게이트는 그것을 「push가 파괴할 수 있는 보호 없는 데이터 컬럼」으로 **세어** 정당한 push를 강등한다. 별도 키라야 **「이 키를 무시하는 클라이언트는 키가 없던 때와 글자 그대로 같게 동작한다」**가 참이 된다.

- **`virtual_only`만 알린다.** `collide`(왼쪽에 실재하는 저장 컬럼을 조인이 부재일 때만 채우는 경우)는 이미 `columns`에 있고, 여기서 한 번 더 실으면 「이 컬럼은 저장되는가」에 한 응답이 **두 답**을 준다. 그래서 **collide만 있는 선언은 이 응답을 한 바이트도 바꾸지 않는다**(테스트가 본문 전체를 비교한다).
- 🔴 **최종 컬럼 목록과의 대조는 라우트가 한다.** 실행기의 `collide` 판정은 `column_types` 기준인데 `columns`는 그것이 전부가 아니다 — 시스템 꼬리(`created_at`·`updated_at`·`is_graph_synced`…)가 config와 무관하게 무조건 덧붙는다. 오른쪽 테이블이 `created_at`을 노출 선언하면 `virtual_only`에 도달해 **실재하는 컬럼 위에 알려질** 수 있었다. 최종 목록을 아는 것은 이 함수뿐이라 중복 제거가 여기 있고, **제거만 하므로** 저장 컬럼은 자기 정체성과 편집 가능성을 그대로 지킨다.
- 🔴 **읽기 전용은 여기서 강제되지 않는다.** 쓰기를 막는 것은 `crud.refuse_virtual_join_columns` 하나이고 그것이 모든 쓰기 경로가 수렴하는 깔때기에 앉아 있다([PRIMITIVES §1](./PRIMITIVES.md)). `editable: false`는 **편집을 제안하지 말라는 표시**일 뿐이라 그 표시를 지워도 쓰기는 여전히 400이다(그 독립성을 테스트가 양방향으로 고정한다 — 깔때기의 거부를 지우면 쓰기 테스트가 빨개지고, 알림을 `editable: true`로 뒤집으면 쓰기 테스트는 전부 초록으로 남는다).
- **실패하면 아무것도 알리지 않는다.** 조인 알림이 예외를 내도 스키마 라우트는 죽지 않고 `virtual_columns`가 빈 채로 나간다(로그 `[VirtualJoin]`). 읽기 경로와 **같은 방향**이다 — 알리지 않은 컬럼은 **눈에 보이는 부재**이지만, 유령 컬럼은 **조용한 오답이자 존재하지 않는 쓰기 대상**이다.
- ⚠️ **`type`은 오른쪽 테이블의 선언이고, 값의 정의역은 그것보다 넓다.** 매치가 없거나 오른쪽 값이 비면 셀에 `unresolved_label`(기본 `미상`)이 앉으므로 **`number` 컬럼이 문자열을 실을 수 있다.** 라벨을 함께 싣는 이유가 그것이다 — 클라가 `미상`을 하드코딩하지 않고 이 값을 읽어야 선언이 실제로 효력을 갖는다.

선언·승인·실행 계약은 [config/virtual_join_rules](../guide/config/virtual_join_rules.md), 클라 렌더는 [frontend §3.4](./frontend.md).

---

## 3. 배치 업서트 코어 (`crud.apply_batch_updates`)

모든 데이터 변경(수동 편집·파일 인제션·체인·맵 저장)이 이 함수 하나로 수렴합니다. (함수 위치는 [CODE_MAP §2](./CODE_MAP.md#2-serverdatabasecrudpy--레이어링-코어))

1. `transaction_context`(user/tx/source ContextVar)로 래핑.
2. **replace_map 모드** — 맵 저장 시 `map_key_columns` 기준으로 기존 행·`CellSource`·`CellOverwrite`를 bulk purge 후 신규 활성 칩만 재적재(유령 셀 0%). purge 범위는 `derive_replace_map_scope()` 단일 리졸버가 결정한다(요청의 명시적 `scope` 필드 우선, 없으면 `updates[0]`에서 파생). **범위를 못 잡으면 `ValueError` → 라우터 400** — 과거의 "아무것도 안 지우고 200" 무음 no-op은 폐기됐다(2026-07-28 U6). 명시적 `scope` + 빈 `updates`는 합법적 전량 소거이며, 응답 `scope: {filters, deleted, inserted}`로 실제 사용된 필터와 건수를 정직하게 알린다(라우터가 같은 리졸버로 echo).
3. 기존 행을 `row_id`/`business_key_val`로 `row_cache`에 적재하고 소스·오버라이트를 bulk 프리로드.
4. 셀별 `apply_row_update_internal` → `CellSource`에 값 기록 → `compute_priority_value`로 승자 재계산 → 네이티브 컬럼 + `CellOverwrite` 갱신. dialect별 `ON CONFLICT` upsert로 flush.
5. **collision_merge** — 비즈니스 키 변경 충돌 시 사용자 오버라이트 보존·병합, `manual_priority_source="collision_merge"` 태깅. → [data_preservation 규율](../guide/data_preservation_and_signature_change.md)
6. 반환: `(results[(row,is_new)], changed_cells, created_logs, deleted_row_ids)`. — replace_map의 purge 범위·건수는 선택적 out-param `replace_report`(dict)로 전달된다(4-튜플 언패킹 호출부를 깨지 않기 위한 하위 호환 채널; 라우터만 넘긴다).

> ⚠️ 이 반환 시그니처를 바꾸면 `main.py` 라우터·`chain_ingestion_worker.py`·`server/tests/` 언패킹을 **전수 연쇄 갱신**해야 합니다. → [시그니처 변경 규율](../guide/data_preservation_and_signature_change.md)

---

## 4. 백그라운드 워커

| 워커 | 트리거 | 동작 요약 |
|---|---|---|
| **Directory Watcher** (`directory_watcher.py`) | watchdog 파일 이벤트 | `raws/` 신규 파일 → `scripts/*.py`의 `BasePipelineParser.match()` 매칭 → `parse()` → 정규화 → `apply_batch_updates` 1000행 청크. **[`600b49d`] 폴더 드롭은 제자리 적재**: 중첩 폴더로 들어온 파일을 루트로 **승격하지 않고** 자기 실제 경로에서 같은 이벤트 경로에 넣고(`request_tree_ingest`/`_ingest_directory_tree`), 인제션 루트 기준 **상대 POSIX 경로**를 파서에 `self.rel_path`로 넘긴다(`relative_source_path` — 봉쇄는 결과 기반, 시그니처는 안 넓힘). 접두 승격 기계장치(`_build_collision_name`·`FLATTEN_SEP` 등)는 삭제. 아카이브는 **조건부**(`is_managed_source` — 외부 읽기 전용 트리의 파일은 이동·err/·삭제 없음, 기록은 원본 경로) + `_unique_dest`(동명 아카이브 충돌 방어). 토글 키는 뜻이 바뀐 채 `flatten_nested_dirs` 유지([INGESTION_GUIDE §1.9](../guide/INGESTION_GUIDE.md)). **커스텀 스크립트 무매칭 시 std parser 폴백**(`parsers/std_parser.py` — `column_types` 헤더 검증 기반 CSV/TSV/TXT 스트리밍, 키 결측 행 스킵). 성공 시 `archives/`, 실패 시 `err/`. `FileIngestionLog` 기록. 워크스페이스 폴더는 config 등록 시 자동 보충. **기동/주기 스윕**: 기동·신규 등록 시 `raws/` 기존 파일을 이벤트 경로 재사용으로 자동 처리 + 300s 주기 잔류 재스캔((mtime,size) 시그니처로 무한 재시도 차단). **[P1] Heavy 레인**: 크기 임계(기본 10MB, `config/ingestion_settings.json` 파일 경계 핫리로드) 초과 파일은 전용 큐+데몬 워커 `watcher-heavy-lane` 1개로 격리(HOL 제거 — 교차 워크스페이스 비차단), 같은 워크스페이스 FIFO는 backlog+직렬화 락+논블로킹 재라우팅으로 보존, 진행 상태는 `/internal/events/ingestion-state`로 push([INGESTION_GUIDE §1.7](../guide/INGESTION_GUIDE.md)). **[P2] 체크포인트·dedup**: 파일 전체 sha256 시그니처(`sha256:<size>:<digest>`)로 ① 동일 시그니처 `DONE`이면 skip(+archive+`FileIngestionLog(SKIPPED)`, 단 WS 통지 status는 `SUCCESS`+사유 detail) ② 미완이면 오프셋 재개. **오프셋 갱신은 청크 upsert와 같은 트랜잭션**이라 "커밋된 행 수 == 기록된 오프셋"이 원자적으로 성립하며, 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 전부 일치할 때만 한다(불일치는 0부터 + 사유 명시). 강제 재처리 3경로: 파일명 `__force__` / `dedup_by_signature:false` / 관리자 재시도([INGESTION_GUIDE §1.8](../guide/INGESTION_GUIDE.md)) |
| **Auto-Update Scheduler** (`run_auto_update.py`) | 5초 틱 + 크론 | `auto_update/*.py` 발견 → 상단 `# schedule:` 크론 파싱 → `exec()`로 `out` 변수 캡처(또는 stdout 폴백) → CSV를 `raws/`에 원자적 드롭. `scheduler_status.json` 갱신(`active` 포함). 매 틱 `config/auto_update_control.json`(`{"disabled": [...]}`, 부재/손상 시 전부 active)을 읽어 disabled 수집기는 실행 스킵 + `last_status="SKIPPED"` + next_run 전진(핫 반영). run-now(on-demand)는 active 무관 실행. **[2026-07-31 `fbc1053`] 세 번째 「수집기가 아닌 일」**: 틱마다 미처리 `RETROACTIVE_RUN` 아웃박스 행을 보고 `retroactive.execute`를 **전용 스레드**(`retroactive-run`)에서 돌린다 — 인라인 실행은 소급 실행 내내 `heartbeat.beat("scheduler")`를 멈춰 `/health`가 이 데몬을 **`wedged`로 보고**하게 만든다(운영자가 제품이 제안한 버튼을 눌러 감시 표면을 죽이는 꼴). **동시 1건**이며 진행 중 두 번째 요청은 조용히 큐잉하지 않고 **거절 + 로그**하고 아웃박스 행을 미처리로 남겨 다음 틱이 집는다 |
| **Chain Ingestion Worker** (`chain_ingestion_worker.py`) | outbox LISTEN/NOTIFY | `processed_chain=False` 폴링(200 배치) → tx별 그룹 → `chain_rules.json` 매칭 규칙의 맵퍼 동적 임포트·실행 → 파생 업데이트를 `chain_*` tx로 적용(source=chain_ingestion 순환 차단) → `/internal/events/broadcast`(통지의 created_logs는 직렬화 전 `MAX_NOTIFY_CREATED_LOGS`=500 절단 + `total_log_count` 실건수 동봉 — `event_constants.py` 공용 상수, 워처 C-5 계약과 동일 형태). 3회 재시도 후 FAILED. `load_chain_rules()`는 `enrichment_rules.json`에서 dedup 투영 룰(`enrichment_mapper.map_enrichment_dedup`, is_batch)을 자동 파생·병합하며, `rule` 인자를 선언한 맵퍼에만 룰 dict가 전달된다(기존 맵퍼 시그니처 불변) |
| **Graph Sync Worker — materializer** (`graph_sync_worker.py` + `graph_materializer.py`) | outbox 증분 소비(자체 keyset 커서 `graph_sync_state.last_outbox_id`, LISTEN/NOTIFY) | 독립 FastAPI(:8090). 이벤트 행을 `ontology_mapping.json` v2 매핑에 따라 **PG 엣지 스토어(`graph_nodes/edges`)로 자동 승격**. 엣지 provenance는 식별 컬럼 CellSource winner의 최저 서열(보수적), 재교정 시 `(from,type,source_row_ref)` 스코프 retarget. `[GraphLatency]` 계측(SLO 10s), 배치 본체는 `asyncio.to_thread` 격리. `/sync`(수동)는 키셋 청킹 **백필/복구** 도구(`"all"` 지원). Neo4j는 청크 훅으로 병행 가능(G3). 상세: [event_driven_backend §4](./event_driven_backend.md) · [ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md) |

공통: 위 4종 워커는 각자의 작업 루프 안에서 **진행 박동**(`watcher`/`chain`/`graph`/`scheduler`)을 발행하며, `/health`가 감시자의 프로세스 관점과 조인해 **8종**(`ok`·`starting`·`missing`·`foreign_beat`·`wedged`·`stale`·`stalled`·`down`)을 판정합니다 — 전수와 뜻은 §1.3.

공통: 모든 워커가 `SYSTEM_RELOAD` outbox 이벤트로 규칙·설정·맵퍼 캐시를 핫리로드하며, 이때 `models.refresh_dynamic_models(engine)`로 **신규 동적 테이블의 물리 CREATE까지 보충**합니다(게이트+checkfirst로 중복 무해 — 웹서버가 1차 소유자, 이슈 #7). graph materializer도 배치 내 SYSTEM_RELOAD를 감지해 매핑·테이블 config를 리로드합니다(이슈 #8 해소).

---

## 5. 참고

- 데이터 모델·레이어링 상세: [data_model.md](./data_model.md)
- 설정 파일: [SYSTEM_OVERVIEW §5](../overview/SYSTEM_OVERVIEW.md)
- 배치 스펙: [batch_update_technical_specification](../spec/batch_update_technical_specification.md)
- 실패 관리: [FAILURE_MANAGEMENT_SPEC](../spec/FAILURE_MANAGEMENT_SPEC.md)
