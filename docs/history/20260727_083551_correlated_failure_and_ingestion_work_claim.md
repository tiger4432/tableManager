# 상관 실패 재시도 · 인제션 work claim — **총괄의 전제가 틀렸고, 만들기 전에 측정해서 알았다**

> 커밋 `d56e7e2` · 2026-07-27 08:35 · 도메인 Server / 운영·프로세스·로깅
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 체크리스트: [PRODUCTION_READINESS](../process/PRODUCTION_READINESS.md)
> 선행: [자식 프로세스 감시 + 진짜 `/health`](./20260727_064058_process_supervision_and_health_endpoint.md)

## 배경 — 이 항목에서 가장 중요한 것은 코드가 아니다

총괄이 상관 실패(correlated failure) 처리를 지시했다. 근거는 이랬다:
**"DB 장애가 나면 자식 다섯이 함께 죽고 약 80초 만에 전부 영구 실패로 고정된다."**

에이전트는 만들기 전에 그 장애를 **유발했다.** 실행 중인 전체 스택에서 DB 경로를 5분간 끊었다.

```
07:13:07 >>> DB 경로 차단 <<<
   ... 300초 ...
07:18:07 spawn counts during outage: {Server:1, Watcher:1, Graph:1, Chain:1, Scheduler:1}
07:18:07 failed_children     = []
07:18:07 correlated_children = []
07:18:09 /health during outage -> 200 degraded   problems: ['database probe timed out']
```

**종료 0건, 재기동 0건.** 워커 루프가 전부 `OperationalError`를 잡아 자체 재시도하고,
`/health`는 설계대로 **200 degraded** — DB 행은 down, 워커 행은 ok로 분리해 보고했다.

> **전제가 틀렸다.** 그것만 막는 가드를 만들었다면, **존재하지 않는 실패 모드를 위한 가드**가 됐을 것이다.

### 진짜 아픈 장애는 자식을 **정확히 하나** 죽인다

실제로 부서지는 모양은 **DB가 불가한 상태에서의 시작·재시작**이다 — PostgreSQL이 앱보다 늦게 올라오는 정전 복구 같은.
`server/main.py:46`이 임포트 시점에 `models.Base.metadata.create_all(bind=engine)`을 돌리므로 uvicorn이 부팅하지 못한다.

```
t+ 7.0s  Backend FastAPI Server  backoff/r1     (나머지 워커 넷: running/r0)
t+57.2s                          backoff/r5
t+94.4s                          failed         failed=['Backend FastAPI Server']
```

**웹서버가 94초 만에 영구 사망하고, 그것도 혼자 죽는다.** 워커 넷은 멀쩡하니 상관 지을 동료 실패가 없다.
즉 총괄이 명세한 규칙 — *"혼자 실패했을 때만 영구 실패"* — 은
**가장 흔한 실제 인시던트를 정확히 놓쳤을 규칙**이었다. UI는 사람이 런처를 다시 띄울 때까지 죽어 있다.

이 항목의 교훈은 여기 있다. **가드를 만들기 전에 그 장애를 먼저 유발해 무슨 일이 실제로 벌어지는지 측정하면,
측정이 설계를 바꾼다.** 이번에는 위임한 쪽의 전제를 위임받은 쪽이 뒤집었다.

## 변경 내용

### "혼자가 아니다"의 증거를 **동료 실패 너머로** 넓혔다

예산이 소진된 **그 순간에만** 판정한다. 항시 프로브가 아니다.

```python
# server/process_supervisor.py — 예산이 다 떨어진 지점
if child.consecutive_failures > self.max_consecutive_failures:
    peers = self._peers_failed_recently(child, now)          # ① 120초 창 안의 동료 실패
    env_down, env_detail = False, None
    if len(peers) + 1 < self.correlated_min_children:
        try:
            env_down, env_detail = self.environment_probe()  # ② 공유 의존성이 실제로 죽었는가
        except Exception as e:
            # 프로브가 깨지면 아무것도 결정하지 못한다.
            self._log(f"environment probe failed: {e}", level="WARNING")
    if len(peers) + 1 >= self.correlated_min_children or env_down:
        self._enter_correlated(child, now, peers, exit_code, env_detail)
    else:
        self._fail_permanently(child, exit_code, reason)
```

둘 중 하나면 `retrying_correlated` — **평탄한 60초 백오프로 무기한 재시도, 영구 실패 없음, 그동안 `/health`는 계속 unhealthy.**

판단 근거 셋:

- **exit code가 아니라 시각으로 묶는다.** Windows에서는 미처리 파이썬 예외가 전부 exit 1이라
  exit code 서명은 거의 모든 실패 쌍을 "상관"이라 부르고 아무것도 증명하지 못한다.
- **120초 창.** `2+4+8+16+32`초를 소진하는 시점은 첫 사망 후 약 90초다. 실측에서 동료의 최근 실패는 그 순간 20–60초 전이었다.
- **2/5 자식.** "혼자"의 바로 위, 가장 느슨한 문턱을 **의도적으로** 골랐다.

### 거짓 양성의 **방향**을 골랐다

세 경로 모두 "상관"쪽, 즉 **계속 재시도하는 쪽**으로 틀린다. 그 대가는 고장난 자식에 대한 무한 재시도 루프인데,
시끄럽고(진입 시 ERROR 배너 + 재시도마다 ERROR 한 줄) 보이고(`/health` 503, `supervisor_status.json`, `launcher.log`) 자체 교정된다.
반대 방향의 대가는 **정상 시스템이 장애 중에 사람을 필요로 하고, 그걸 다음에 누가 볼 때까지 모른다**는 것이다.

무한 사면이 되지 않도록 두 가지를 잠갔다.

- **모르면 healthy로 센다.** `DATABASE_URL` 없음·sqlite·파싱 불가·프로브 예외는 전부 "증거 없음"이다.
  프로브는 증거를 **더하기만** 할 수 있다.
- **correlated는 영구가 아니다.** 이후 실패마다 재평가한다. 동료가 회복하고 DB가 응답하는데도 혼자 계속 죽으면 `failed`가 된다.

### 워처의 비트가 **재시도 폴러가 아니라 인제션 경로**에서 나온다

종전 비트는 워처의 3초 폴러 스레드에서 찍혔다. 그래서 **인제션 안에서 얼어붙은 워처가 계속 비트를 찍었고 `/health`는 ok라고 했다.**
그렇다고 비트를 인제션으로 **옮기기만** 하면 구멍이 이동할 뿐이다 — 인제션은 대부분 놀고 있으므로 그 비트는 대부분 stale이고 아무 말도 못 한다.

그래서 **두 사실을 분리**했다. 인제션은 파일마다 **work claim**을 열고 진행하며 갱신하고,
claim의 나이는 **다음에 비트를 찍는 스레드가 누구든 그 비트에 실려** 공개된다.
폴러는 가림막이 아니라 **신고자**가 된다 — 자기는 살아 있으니 비트를 찍고, 그 비트가 "어떤 파일이 400초째 진행이 없다"를 나른다.

```
supervisor: running + 비트 신선 + claim 진행    -> ok
supervisor: running + 비트 신선 + claim 정체    -> stalled   (503)   <- 신규
supervisor: running + 비트 stale                -> wedged    (503)
supervisor: not running                         -> down      (503)
```

claim은 **스레드 귀속(thread-affine)**이다. 비트는 **자기 스레드에서 연 claim만** 갱신하므로,
건강한 heavy 레인 작업이 얼어붙은 inline 작업의 claim을 대신 갱신해 주지 못한다.

### 임계값 두 개는 서로 다른 것을 잰다

`DEFAULT_STALL_AFTER_SEC = 300.0`으로 비트 stale(60초)보다 훨씬 크다.
비트 결손은 "2–5초 루프가 안 돌았다"이고, claim 정체는 "진짜 작업 한 덩이가 안 끝났다"이며 덩이는 균일하지 않다.
바닥을 정하는 것은 **계측할 수 없는 구간**이다 — 커스텀 파이프라인 파서는 사용자 스크립트라
파일 하나를 불투명한 호출 하나로 읽고 아무것도 보고하지 않는다.

> **거짓 양성 방향은 침묵 쪽이다.** 이건 운영 대시보드에 503을 띄우는 신호이고,
> 사람들이 신경 쓰는 바로 그 작업 중에 늑대를 외치는 health check는 **뮤트된다.**
> 5분의 탐지 지연보다 뮤트가 비싸다. 팀에 5분이 너무 길면 숫자는 움직일 수 있다(측정은 ~130초 위 아무 값이나 지지한다).

### B3 — 모듈 로거가 프로세스 로그 파일에 도달한다

`get_process_logger`가 핸들러를 **프로세스 이름 로거**에 붙이고 루트를 벗겨 냈다.
그래서 그 이름의 **자식** 로거만 우연히 상속받았고(`Watcher.DirectoryWatcher`), 나머지는 전부 새어 나갔다.
`crud.py`는 `logging.getLogger("Server")`에 찍는데, 워커 프로세스에서 그 로거는 핸들러가 없고
핸들러 없는 루트로 전파돼 `logging.lastResort`(맨 stderr)로 떨어졌다 — **워커 자기 로그 파일에는 없었다.**

**핸들러를 루트로 옮기고, 이름 로거는 핸들러 없이 전파로 도달하게 했다.** 대가 둘을 같이 처리했다:
중복 출력(테스트가 `named_handlers == 0`·`root_handlers == 2`를 단언)과 서드파티 홍수
(`NOISY_THIRD_PARTY`로 sqlalchemy/watchdog/urllib3 등을 WARNING에 고정, 단 **그들의 ERROR는 통과해야 한다** —
침묵으로 과교정하는 것도 결함이다).

## 검증

### 결정적 드릴 — 312초간 `200/ok`, 그런데 비트는 1초 전 것

커스텀 파이프라인 파서가 `parse()` 안에서 블록하도록 만들었다(사용자 스크립트가 멈춘 네트워크 호출이나 락에 걸린 실제 모양).
파일 둘을 동시에 떨어뜨려 heavy 레인과 inline 레인을 모두 덮었다.

```
 t+   0.0s  http=200 worker=ok       beats=1    beat_age=0.38  claims=None no_progress=None
 t+ 150.9s  http=200 worker=ok       beats=55   beat_age=0.67  claims=2    no_progress=148.94
 t+ 301.8s  http=200 worker=ok       beats=107  beat_age=0.01  claims=2    no_progress=299.87
 t+ 311.9s  http=503 worker=STALLED  beats=153  beat_age=1.01  claims=2    no_progress=309.95
```

세 열이 이 드릴을 결정적으로 만든다.

- **`claims=2`가 내내 유지** — 두 레인 모두 claim을 열었다. heavy 레인 전용 워커 스레드까지 덮였다는 뜻이다.
- **`beats`가 1→153, `beat_age`가 3초를 넘긴 적 없다.** 503이 뜨는 그 순간에도 비트는 **신선했다.**
  **종전 신호는 312초 내내 "정상"이라고 말했다.** 그 구멍을 재현한 뒤 막았다.
- **문턱 전 연속 31회의 `200/ok`** — 일찍 발화하는 가드였다면 여기서 드러났다. 느린 인제션은 경보가 아니다.

**첫 시도는 실패했고 그 이유가 기록할 값이 있다.** 처음엔 장애 드릴용 killable 프록시를 통해 DB에 접속했는데,
부하에서 프록시가 연결을 떨궈 t+10초에 **DB 행** 때문에 503이 떴고, 드릴의 "첫 503" 로직이 그걸 탐지 성공으로 채점했다.
DB 직결로 다시 돌리고 채점 조건을 `worker_status == "stalled"`로 바꿨다.
**503은 그 자체로 증거가 아니다. 이유가 맞아야 한다.**

### 부하 실측이 유휴 실측을 대체했다 — 60초는 그대로다

종전 60초 근거는 **거의 유휴** 스택의 최악 간격 10.26초였다.
실제 런처로 다섯 자식을 모두 띄운 채 **10만 행 / 35MB heavy 레인 인제션**(893.6초) 중에 재측정했다.

| worker | phase | n | p50 | **max** | 여유 |
|---|---|---|---|---|---|
| **chain** | **load** | **405** | 1.99 | **7.01** | **8.6×** |
| graph | load | 446 | 2.00 | 3.02 | 19.9× |
| scheduler | load | 176 | 5.01 | 6.61 | 9.1× |
| watcher | load | 386 | 2.94 | 4.24 | 14.1× |

**부하 최악 7.01초가 유휴 최악 10.26초보다 오히려 낫다.** 부하가 여유를 먹지 않았다.
모든 p50이 각 워커의 설계 루프 주기에 그대로 떨어진 것 자체가 비트가 작업 루프에서 나온다는 증거다.
이제 `test_stale_threshold_survives_the_measured_load`가 이 측정을 고정한다 —
나중에 문턱을 이 아래로 조이면 운영에서 거짓 503이 아니라 **스위트가 실패한다.**

### 자기가 만든 누수를 자기가 잡았다 — 스위트가 라이브 트리에 썼다

인제션 경로에 비트를 넣자 `test_std_parser.py` 등이 `process_with_retry`를 타면서
**사용자 라이브 트리에 `server/config/worker_heartbeats/watcher.json`을 실제로 만들었다.**

```json
{"name":"watcher","pid":23844,"ts":...,"beats":45,"note":"done: ingest drop.csv","work":{"open":0}}
```

무해하지 않다. **`/health`는 하트비트를 디스크에서 읽으므로, 죽은 pytest 프로세스의 비트가 운영에 남으면
stale worker로 읽혀 정상 시스템에 503을 서빙한다.** 사후 확인에서 잡혔고(설계로 잡은 게 아니다),
파일을 지우는 대신 **구조적으로** 막았다 — `conftest.py`의 세션 autouse 픽스처가 스위트 전체의 하트비트 디렉터리를 돌린다.

```python
# server/tests/conftest.py — 개별 테스트 패치가 아니라 스위트 전체를 한 번에
@pytest.fixture(scope="session", autouse=True)
def _heartbeats_never_touch_the_live_tree(tmp_path_factory):
    ...
```

이후 두 번의 전체 스위트 실행에서 `server/config/worker_heartbeats/`는 생기지 않았다.

### 결함 주입 13/13 — 그리고 주입기 자체의 결함

가드를 하나씩 제거한 결함 13개를 주입해 **13건 모두 검출**, 복원 후 소스 바이트 동일(sha256).
`/health`가 stalled claim을 무시하게 만드는 D9, claim의 스레드 귀속을 없애는 D8,
환경 증거를 무시해 동료 규칙만 남기는 D2 등이 포함된다. D2는 §상관 규칙의 핵심 증거다 —
끄면 `test_a_lone_child_is_spared_while_its_database_is_down`이
*"the web server was permanently failed while its database was down"*으로 실패한다. 위에서 실측한 그 결과다.

> **첫 실행은 11/13이었고 둘은 미검출이 아니었다.** 여러 줄 앵커를 `\n`으로 썼는데
> `directory_watcher.py`는 디스크에서 CRLF라 **주입 자체가 안 됐다.**
> verdict 줄만 읽었다면 "11건 검출, 테스트 2개가 약함"으로 잘못 결론 났을 것이다.
> **주입기는 skip과 miss를 다른 문자열로 보고해야 한다.**

### 에이전트가 조용히 고치지 않고 보고한 자기 실수 둘

1. **측정 전에 임계값 근거를 주석·테스트에 써 뒀다.** "worst chunk gap 2.06s"라고 적어 둔 값이 실측 **12.50초**(6배 오차)였다.
   숫자는 코드에 적기 전에 측정한다.
2. **로그 기반 축약이 숫자를 3.6배 부풀렸다.** 최악 claim 간격을 45.56초로 냈는데,
   샘플러가 `note` 문자열이 **바뀔 때만** 기록하고 `beat()`는 파일 쓰기를 초당 1회로 throttle하기 때문이었다.
   실제로는 청크 5개(각 9.1초)를 한 덩이로 본 것. 행 카운트 기반 교차검증에서야 잡혔다.

두 건 다 **보고서에 남았기 때문에 이 항목에 남는다.** 조용히 고쳤다면 다음 사람이 같은 계측 함정에 빠진다.

### 스위트

**576 passed / 0 failed.** 이 중 **38개가 이번 작업분**이다(기준선 540에서 시작했으나
다른 에이전트가 세션 중 3회 커밋해 베이스가 움직였고, 파일별로 세어 38로 산정 — 남의 델타를 자기 것으로 세지 않았다).
운영 무영향: 드릴은 전부 격리 루트(`dev_env/ops2_root`, `:8086`/`:8096`)와
**killable TCP 프록시(:55432)**를 통해 돌았고, 사용자의 PostgreSQL 서비스는 멈춘 적이 없다.

## 아키텍처 영향

- **살아 있음(beat)과 진행(work claim)이 분리됐다.** 스레드가 여럿인 프로세스에서 하트비트를 하나만 두면
  "가장 부지런한 스레드"가 멈춘 스레드를 가린다 — 그게 종전 워처의 모양이었다.
- `/health` 페이로드는 **필드만 추가**됐다(`checks.supervisor.correlated_children`, `checks.workers.*.work`).
  경계 계약(REST 시그니처·WS 이벤트·셀 모양·스키마)은 하나도 바뀌지 않았고 `client2`는 `/health`를 소비하지 않는다.
- 프로세스 로그가 이제 **그 프로세스에서 도는 모든 로거**를 담는다. `watcher.log` 안의 `[Server]` 줄이 그 증거다 —
  `crud.py`의 미선언 컬럼 경고가 실제 인제션을 돌린 프로세스의 로그에서 발견됐다.
- `psutil`이 `environment.yml`과 `pyproject.toml` **양쪽**에 선언됐고, 없을 때의 강등이 **부팅 시점에 시끄럽게** 알려진다
  (종전에는 종료 시점에 발견됐다). 선행 항목이 "해소되지 않았다"고 남긴 그 미선언 의존성이다.

## 아직 덮이지 않은 것

- **웹서버는 `/health`가 보고할 수 없는 유일한 자식이다.** 자기가 그 엔드포인트이기 때문이다.
  드릴 중 300초간 `/health` 자체가 닿지 않았다. 지속 기록은 `supervisor_status.json`과 `launcher.log`뿐이고,
  외부 모니터는 JSON 이유가 아니라 연결 거부를 본다.
- **천천히 죽이는 공유 원인은 잡히지 않는다.** 창은 자기 예산 소진 시점 기준 120초다.
  원인이 두 번째 자식을 죽이는 데 10분 걸리면 첫 번째는 이미 혼자 영구 실패한 뒤다.
- **프로브 대상은 DB뿐이다.** 디스크 가득 참, 파일 핸들 고갈, `ingestion_workspace`를 담은 네트워크 공유 단절은
  전부 공유 원인인데 프로브가 없다. 자식 둘이 함께 죽으면 여전히 잡히지만, 혼자 죽으면 못 잡는다.
- **프로브는 도달 가능성만 본다, 사용 가능성이 아니다.** 접속은 받지만 인증을 거부하거나 스키마가 없는 DB는
  healthy로 읽힌다 — 의도적이다(재시도 루프는 설정 결함을 고치지 못한다). 대신 그 상태에서 크래시 루프하는 자식은 영구 실패한다.
- **`retrying_correlated`는 설계상 영원히 재시도한다.** 원인이 안 풀리면 루프도 안 멈춘다. 시끄럽고 unhealthy하지만 **아무도 호출하지 않는다.**
- **다른 워커 셋에는 work claim이 없다.** 체인 워커·그래프 머티리얼라이저·스케줄러는 여전히 liveness 비트만 낸다.
  **워처에서 막은 그 구멍이 나머지 셋에는 그대로 열려 있다.**
- **불투명한 parse 구간은 계측되지 않는다.** 4분간 블록하는 커스텀 파서와 정상 동작 중인 파서를 구별할 방법이 없다.
- **로그 로테이션이 여전히 없다.** 라이브 `server/*.log`가 이미 2–19MB인데 로거를 더 모았으니 **조금 더 빨리 큰다.**
- **supervisor를 감시하는 것은 없다**(선행 항목에서 이월). 상관 상태는 런처 프로세스 단위라 재기동하면 증거 창이 초기화된다.

## 다음 단계

1. **총괄 결정 대기 — 환경 프로브.** "혼자가 아니다"의 증거를 동료 실패 너머로 넓힌 것은
   위임 범위(=`"함께"의 정의`) 밖으로 한 걸음 나간 판단이다. 에이전트가 숨기지 않고 결정 사항으로 올렸다.
   거부하려면 인자 하나면 된다: `Supervisor(environment_probe=lambda: (False, None))` — 양쪽 동작의 테스트가 이미 있다.
2. **300초 stall 문턱**도 같은 성격의 결정 사항이다(침묵 쪽으로 편향).
3. **`server/main.py:46`의 임포트 시점 `create_all`이 근본 원인이다.** 이번 변경은 그 실패를 **관용**한 것이지 없앤 것이 아니다.
   지연 실행이나 재시도로 바꾸면 실패 자체가 사라지고, 들리는 것보다 작은 변경이다.
4. **체인 워커에 work claim**이 가장 유력한 다음 후보다 — 부하 최악 간격 7.01초의 그 워커이고 outbox를 빼는 주체다.
5. `PRIMITIVES.md`에 하트비트·health·감시 항목이 아직 **없다.** 그래서 이번 에이전트도 소스를 읽어 메커니즘을 재발견해야 했다.
   (문서 소관은 doc-keeper.)
6. `devenv`에 **이름 붙은 인스턴스나 락이 없다**(이월). `:8081`/`:8091`이 점유돼 있어 이번에도 사설 루트와 포트를 손으로 만들었다.
