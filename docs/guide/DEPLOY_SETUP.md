# 🚀 운영 배포 — 직접 세팅해야 하는 것들 (요약)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 (§7 롤백 항목을 **드릴 실측**으로 교체 — 재기동 위치·`/health` 사각·스키마 잔여물. 전체 절차는 [ROLLBACK_PROCEDURE](ROLLBACK_PROCEDURE.md)로 분리. 직전: `90e284f` §1-4 `ASSY_ADMIN_TOKEN`) | **대상:** 새 환경에 assyManager를 올리는 사람
> **상세:** 각 항목의 키·함정·검증 절차는 [CONFIG_GUIDE](CONFIG_GUIDE.md)에 있다. 이 문서는 **"내가 무엇을 채워야 하는가"** 만 담는다.
> **프로덕션 게이트:** 배포 전 남은 차단 항목은 [PRODUCTION_READINESS](../process/PRODUCTION_READINESS.md).

---

## 0. 한 줄 원칙 — 무엇이 내 몫인가

**"이 테이블의 스키마를 누가 정하는가"** 로 갈린다.

| 구분 | 뜻 | 세팅 |
|---|---|---|
| **제품 소유** | assyManager 자신의 저장소. 이름·컬럼을 제품이 정한다 | `.sample`에 이미 선언돼 있다 — **건드리지 마라** |
| **현장 소유** | 우리 공장 데이터. 테이블명·컬럼이 사이트마다 다르다 | **전부 내가 채운다** |

`server/config/`는 통째로 gitignored다(`.sample`만 git에 올라간다). 즉 **`.sample`을 복사해서 시작하고, 그 사본이 내 자산**이다.

```bash
cd server/config
for f in *.sample; do cp "$f" "${f%.sample}"; done
```

---

## 1. 반드시 해야 하는 것 (없으면 안 뜬다)

### 1-1. 데이터베이스

`server/database/database.py`의 기본값은 `postgresql://postgres:admin@localhost:5432/assy_manager`다.
운영 DB의 이름·비밀번호가 다르면 **`server/config/database.json`으로 관리한다** — 소스를 고치지 마라.
`.sample`을 복사해 `url` 하나 또는 분리 필드(`host`/`port`/`database`/`user`/`password`)로 적고 **전 프로세스 재기동**(핫리로드 없음). 적용 확인은 기동 로그의 `[db] url source=config file target=...(비번 마스킹)` 줄 → 절차 상세는 [config/database.md](./config/database.md).

환경변수 `DATABASE_URL`은 **파일보다 우선하는 오버라이드**다:

```bash
DATABASE_URL=postgresql://<user>:<pw>@<host>:5432/<db>
```

우선순위(변경 금지): **환경변수 > `database.json` > 코드 기본값.** 격리 개발 환경이 이 환경변수로 DB를 갈아타므로, `devenv.py bootstrap`이 config 트리를 복사하면서 `database.json`이 격리 루트에 딸려 가도 환경변수가 이겨서 무해하다 — 순서가 뒤집히면 격리 스택이 운영 DB에 쓴다.

> 같은 변수로 검증 환경을 분리한다 → [개발 환경 격리](#5-검증개발-환경-선택)

### 1-2. `table_config.json` — 동적 테이블 선언 (**핵심**)

이 시스템의 스키마 SSOT다. 여기 선언된 테이블만 존재한다.

- **이미 들어 있는 것(제품 소유 — 그대로 두기)**: `wafer_map_metadata`, `map_split_registry`(전사 계획의 DOE 저장소 — `knobs`·`bands` 컬럼 포함), 그리고 🗄️ `map_doe`·`map_doe_source`(**폐기 2026-07-27 — 아무것도 쓰지 않고 기존 행 읽기용으로만 남아 있다**)
- **내가 추가할 것(현장 소유)**: 우리 공장 로그·맵 테이블 전부. 아래 §2의 기능별 표 참조.

각 테이블에 필요한 것: 컬럼 정의(`column_types`), **비즈니스 키**(`business_key`), 복합키면 `composite_key_source` + `composite_key_separator`.

> ⚠️ **구분자 함정**: 맵 키는 `_`가 흔하고 테이블명에도 `_`가 있다. 복합키 구분자로 `_`를 쓰면 파싱이 깨진다. 제품 소유 3종은 `|`를 쓴다 — 새로 만들 때도 `|` 권장.

#### 제품 소유 4종은 **손으로 옮기지 않는다** (2026-07-27)

이미 쓰던 `table_config.json`이 있는 환경에 제품 선언을 넣을 때는 설치 스크립트를 쓴다. 정의의 원본은 **`server/product_tables.py` 하나**이고, `.sample`조차 그 모듈에서 생성된다 — 옮겨 적을 목록이 애초에 없다.

```bash
python server/scripts/install_product_tables.py            # dry run (기본)
python server/scripts/install_product_tables.py --apply    # 실제 반영
```

- **현장 항목은 재직렬화하지 않는다** — 원본 텍스트에 바이트 단위로 끼워 넣으므로 키 순서·들여쓰기·줄바꿈이 그대로 보존된다.
- 없으면 추가 / 같으면 **아무것도 쓰지 않음** / **다르면 드리프트로 보고만 하고 손대지 않는다**(강제하려면 `--overwrite-drift`).
- `--apply`는 타임스탬프 백업을 먼저 쓰고, 반영 후 손대지 않은 항목을 바이트 대조해 어긋나면 **백업을 되돌린다.**
- **DDL은 하지 않는다.** 선언이 물리 테이블이 되는 것은 리로드 경로의 일이다 → [CONFIG_GUIDE §4.1](CONFIG_GUIDE.md).
- 종료코드: `0` 할 일 없음 · `1` 조치 필요 · `2` 오류.

### 1-3. 인제션 워크스페이스

`server/ingestion_workspace/<테이블명>/` 아래에 `raws/ archives/ err/ config/ auto_update/ scripts/`가 필요하다. 파일을 `raws/`에 떨구면 워처가 집어간다.

> 워크스페이스별 `config/config.json`은 **폐기된 개념**이다(하위호환 읽기만 남아 있음). 테이블명·파싱 규칙은 전역 `table_config.json`이 이긴다. 새로 만들지 마라.

### 1-4. `ASSY_ADMIN_TOKEN` — 어드민 접근 토큰 (2026-07-27 신설)

`/admin/*`은 **인증이 전혀 없었다.** 사내망에 패킷을 보낼 수 있는 누구나 `POST /admin/scripts/code`로 임의의 파이썬 파일을 쓰고 `POST /admin/auto-update/run-now`로 그것을 실행시킬 수 있었다. 이제 **공유 토큰 하나**로 잠근다 — 로그인 화면도, 사용자 계정도 없다(2~5명 사내 공유 환경이라 의도적으로 그렇게 두었다).

**셸마다 문법이 다르다.** 이 프로젝트의 운영 환경은 Windows + PowerShell이다:

| 셸 | 명령 |
|---|---|
| **PowerShell** (운영 기본) | `$env:ASSY_ADMIN_TOKEN = "<토큰>"` |
| cmd.exe | `set ASSY_ADMIN_TOKEN=<토큰>` |
| bash/zsh | `export ASSY_ADMIN_TOKEN=<토큰>` |

> 🚨 **PowerShell에서 `set`을 쓰면 조용히 실패한다.** `set`은 PowerShell에서 `Set-Variable`의 **별칭**이라, `set ASSY_ADMIN_TOKEN=admin`은 `ASSY_ADMIN_TOKEN=admin`이라는 이름의 **PowerShell 변수**를 만들고 끝난다. 환경변수는 건드리지 않으므로 uvicorn·워커 자식 프로세스는 아무것도 못 본다. **에러가 나지 않아 성공한 것처럼 보인다** — 판별법은 기동 로그의 `is NOT set` 경고가 사라졌는지 하나뿐이다(2026-07-28 실제로 여기서 막혔다).

설정한 **바로 그 셸에서** 런처를 띄워야 한다. 자식 프로세스는 기동 시점의 환경을 복사해 가므로, 다른 창에서 설정하면 영원히 반영되지 않는다.

토큰 값은 **길고 추측 불가능한 ASCII 문자열**이어야 한다.

> 🚨 **반드시 ASCII로.** HTTP 헤더는 latin-1로 디코딩되므로 **한글·이모지 토큰은 절대 인증에 성공할 수 없다.** 서버는 이런 값을 **거부하고 무시**하며 기동 로그에 `ERROR`로 남긴다 — 즉 토큰을 넣었는데도 어드민이 잠기지 않은 상태가 된다. 예전에는 이 경우 "is set"이라고 안심시켜 놓고 올바른 토큰에도 매번 403을 돌려줬다(2026-07-27 수정). `openssl rand -hex 24` 같은 출력이 안전하다.

**환경변수인 이유**: `DATABASE_URL`·`ASSY_DATA_ROOT`와 같은 자리다. 그리고 `server/config/`에 파일로 두면 gitignore가 지켜주긴 하지만 `devenv.py snapshot`이 config 트리를 통째로 복사하므로 **비밀이 두 군데로 늘어난다.** 환경변수는 저장소 안에 아예 존재하지 않는다.

**설정하지 않으면 (fail closed, 단 부분적으로)**:

| 라우트 | 토큰 미설정 | 토큰 설정 |
|---|---|---|
| `POST /admin/scripts/code`, `POST /admin/auto-update/run-now` | **503으로 거부** (코드 실행 경로 — 설정을 잊었다고 구멍이 열려선 안 된다) | 헤더 필수 |
| 나머지 `/admin/*` 전체 (조회 포함) | 그대로 동작 | 헤더 필수 |
| `/internal/events/*` (워커→웹서버 IPC) | 그대로 동작 | 헤더 필수 — **워커가 자동으로 보낸다** |
| `GET /health` | 항상 무인증 (모니터링 표면) | 항상 무인증 |

나머지를 열어 두는 것은 **의도된 선택**이다. 새 빌드로 처음 재기동한 운영자가 어드민 페이지 전체에서 잠겨버리는 사고를 막는다 — 잃는 것은 위험한 두 개뿐이다.

> `/internal/events/*`는 워커가 웹서버에 보내는 내부 통지다. 조회 전용 어드민은 잠겨 있는데 **모든 접속 클라이언트의 그리드에 임의의 값을 뿌릴 수 있는 이 경로가 열려 있던 것**이 거꾸로였다(2026-07-27). 워커는 런처(`run_decoupled_app.py`)의 환경을 그대로 물려받으므로 **변수를 한 번만 설정하면 따로 해줄 일이 없다.** 단, 워커를 손으로 따로 띄운다면 그 셸에도 같은 변수가 있어야 한다 — 없으면 워커 로그에 `API notification failed: ... -> 401`이 쌓이고 실시간 동기화가 조용히 멈춘다.

**워커 로그에서 401/403을 읽는 법 (2026-07-30 개선).** 이제 통지 실패 줄에 **누가 거절했는지**가 함께 찍힌다. 판정 기준은 게이트가 자기 거부에만 붙이는 `WWW-Authenticate: X-Admin-Token` 헤더 하나다:

| 로그에 찍히는 것 | 뜻 | 조치 |
|---|---|---|
| `admin-gate=yes` + `401` | **우리 게이트**가 거부. 워커가 헤더를 아예 안 보냈다 | 워커 쪽 변수 확인 후 **트리 전체** 재기동 |
| `admin-gate=yes` + `403` | **우리 게이트**가 거부. 양쪽이 **서로 다른 토큰**을 쥐고 있다 | 지문 비교 → 한 셸에서 트리 전체 재기동(웹서버만 재기동하면 재발) |
| `admin-gate=no` | **우리가 아니다.** 앞단(프록시·방화벽·다른 프로세스)이 거부했다 | 아래 §1-5. 토큰을 아무리 만져도 안 고쳐진다 |

**기동 로그가 상태를 말해 준다.** 미설정이면 `WARNING`으로 어떤 라우트가 꺼졌고 어떤 변수를 설정해야 하는지 한 줄에 담아 찍는다:

```
[admin-auth] ASSY_ADMIN_TOKEN is NOT set (token fingerprint none). POST /admin/scripts/code and
POST /admin/auto-update/run-now are DISABLED (503) ...
```

**🔑 토큰 지문(fingerprint) — "양쪽이 같은 토큰을 쥐고 있나"를 한눈에 (2026-07-30 신설).** 웹서버와 **모든 데몬**이 기동 시 `token fingerprint <8자리>`를 찍는다. 값은 `sha256(토큰)`의 앞 8자리 16진수로, **토큰 자체는 절대 로그에 남지 않는다**(단방향). 운영자가 손에 든 토큰으로 직접 재현할 수 있다:

```bash
python -c "import hashlib;print(hashlib.sha256(b'<토큰>').hexdigest()[:8])"
```

| 지문 표기 | 뜻 | 조치 |
|---|---|---|
| `a3f19c2b` 같은 16진수 8자리 | 그 프로세스가 쥔 토큰 | **모든 프로세스가 같아야 한다.** 다르면 그 프로세스만 다른 셸에서 떴다는 뜻 |
| `none` | 변수 미설정 | 변수를 **추가**하고 트리 전체 재기동 |
| `unusable-non-ascii` | 설정돼 있으나 비-ASCII | 변수를 **교체**(추가가 아니다)하고 트리 전체 재기동 |

지문이 도입되기 전에는 배너가 `is set`이라고만 말해서, **두 프로세스의 토큰이 같은지 아닌지 아무도 알 수 없었다.** 2026-07-30 인시던트에서 이것이 진단을 몇 시간 늦췄다.

**클라이언트**: 어드민 페이지가 게이트 거부(`WWW-Authenticate: X-Admin-Token`)를 받으면 토큰을 한 번 묻고 `localStorage`에 보관한 뒤 `X-Admin-Token` 헤더로 보낸다. 운영자가 할 일은 **처음 한 번 붙여넣기**뿐이다.

#### 🚨 토큰을 켜기 전에 — 클라이언트 번들을 반드시 다시 빌드해서 커밋할 것

서버가 서빙하는 것은 `client2/src/admin.js`가 **아니라** 빌드 산출물 `client2/dist/assets/admin-*.js`다(그리고 그 파일은 git에 올라간다). 소스만 고치고 번들을 그대로 두면 **토큰을 설정하는 순간 어드민 페이지가 죽는다** — 요청은 401을 받는데 토큰을 물어보는 코드가 서빙되는 파일에 없어서 **프롬프트가 아예 뜨지 않는다.** 복구하려면 변수를 도로 지우고 재기동해야 하니, 사실상 보안 조치를 되돌리게 된다.

```bash
cd client2 && npm run build      # dist/ 갱신 후 커밋
```

> **[2026-07-30 `5a14e77`] `npm run build`는 이제 게이트를 통과해야 진행됩니다.** `prebuild`가 클립보드 관례 검사 + **계약 하네스 4종**(`contracts/*/client_harness.mjs`)을 먼저 돌리고, 하나라도 발산하면 `dist/`가 생성되지 않습니다. **빌드가 실패하면 번들도 갱신되지 않았다는 뜻**이므로 아래 `grep` 확인이 0으로 남습니다 — "빌드했는데 왜 그대로냐"의 첫 번째 원인이 이것입니다. 계약이 실제로 바뀐 것이라면 벡터를 고쳐 통과시키지 말고 총괄에 가져가십시오([frontend §2.1](../architecture/frontend.md)).

**확인 방법 (운영자·리뷰어 모두 이걸로 판정한다 — 0이면 아직 옛 번들이다):**

```bash
grep -c X-Admin-Token client2/dist/assets/admin-*.js    # 1 이상이어야 한다
```

> ⚠️ 토큰을 **쿼리 파라미터로 보내지 마라.** 쿼리 문자열은 액세스 로그에 남는다. 서버는 헤더만 받는다.

### 1-5. 사내 프록시 — 내부 통지가 밖으로 나가는 함정 (2026-07-30 실제 장애)

**증상.** 체인 워커가 `POST /internal/events/broadcast`에 **403**을 반복해서 받는다. 재기동해도 그대로다. 토큰을 아무리 맞춰도 안 고쳐진다. 그리드는 멀쩡해 보이는데 교정이 실시간으로 안 퍼진다.

**원인은 우리 코드가 아니라 프록시였다.** `requests`는 기본값이 `trust_env=True`라 `HTTP_PROXY`/`http_proxy` 환경변수와 **Windows 프록시 레지스트리**를 읽는다. 여기에 함정이 하나 더 있다 — 레지스트리 `ProxyOverride`의 **`<local>` 토큰은 점(`.`)이 없는 호스트명만 우회 대상으로 친다.** 즉:

| 주소 | `<local>`이 우회해 주나 |
|---|---|
| `localhost` | ✅ 우회 (점이 없다) |
| **`127.0.0.1`** | ❌ **우회 안 함 (점이 있다)** |

우리 워커의 `API_BASE_URL` 기본값이 `http://127.0.0.1:8080`이므로, **자기 자신에게 보내는 통지가 사내 프록시로 나갔고** 프록시는 사설 주소로의 중계를 403으로 거절했다.

**모든 증상이 이것으로 설명된다:** 401이 아니라 403인 것(우리 게이트는 헤더가 없으면 401을 낸다), 게이트가 아예 없는 `GET /health`까지 403인 것, 재기동 면역인 것, 그리고 **프록시가 없는 개발 장비에서는 재현이 안 되는 것**.

**판별 (1분).** 프록시를 끄고 같은 요청을 보내 본다:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" --noproxy "*" http://127.0.0.1:8080/health
```

`--noproxy`를 붙였을 때만 200이면 확정이다. ⚠️ **PowerShell의 `curl`은 `Invoke-WebRequest`의 별칭이고 그쪽도 시스템 프록시를 탄다** — 반드시 `curl.exe`로 불러야 한다. 이걸 몰라서 진단 자체가 오염된 적이 있다.

**코드 측 조치 (완료 — 2026-07-30).** 프로세스 간 loopback 호출은 **프록시 설정을 절대 참조하지 않는다.**

- 워커 3종(`run_watcher`·`chain_ingestion_worker`·`graph_sync_worker`)은 세션을 직접 만들지 않고 **`server/internal_event_client.internal_event_session()`** 하나에서 받는다(`trust_env=False`). 발신자마다 따로 고치다 같은 결함이 세 번 재발한 이력이 있어, **세션을 직접 만드는 발신자가 생기면 테스트가 실패**하도록 막아 두었다.
- 웹서버 → GraphSync 워커(`/api/graph/sync` → `127.0.0.1:8090`)의 `httpx`도 `trust_env=False`다. **같은 모양의 네 번째 홉**이라 같이 막았다.

**운영 측 조치 (권장).** 코드가 막고 있어도, 런처 셸에 아래를 넣어 두면 아직 정리되지 않은 다른 도구(`curl`, 수집 스크립트 등)까지 안전해진다:

```powershell
$env:NO_PROXY = "127.0.0.1,localhost"
```

**기동 로그가 이제 미리 말해 준다.** 데몬 3종은 기동 시 `/health`를 한 번 찔러 보고 프록시 환경을 함께 찍는다:

```
[internal-events] http://127.0.0.1:8080/health -> 200, direct (proxy bypassed). proxy-env=none
```

`proxy-env`에 프록시가 잡히거나 `/health`가 **200이 아닌 HTTP 상태**로 답하면 그 줄이 `ERROR`로 뜨면서 프록시 가능성과 조치를 함께 알려준다. `/health`는 게이트가 없으므로 **HTTP 상태가 돌아온다는 것 자체가 "우리가 답한 게 아니다"라는 증거**다. (연결 거부는 기동 순서상 정상이므로 `INFO`다 — 매 부팅마다 경고를 울리면 아무도 안 읽는다.)

#### 토큰 교체(로테이션) — **무중단이 아니다. 계획하고 하라**

솔직히 적는다: **로테이션 절차는 매끄럽지 않고, 매끄럽게 만드는 장치도 없다.** 토큰은 하나뿐이고 **유예 기간(옛 토큰·새 토큰 동시 허용)이 없다.** 서버는 매 요청에서 **정확히 하나의 값**과만 비교한다. 즉 교체는 **단절 전환**이다.

무엇이 걸리는지 — 넷 다 걸린다.

| 대상 | 교체 시 무슨 일이 | 조치 |
|---|---|---|
| 웹서버 | 프로세스 환경은 밖에서 못 바꾼다 | **재기동 필요** |
| 워커 4종 | 런처가 기동 시점 환경을 복사해 물려준다(`os.environ.copy()`) — 옛 토큰을 든 채로 남는다 | **런처째 재기동 필요** |
| 운영자 브라우저 | `localStorage`에 옛 토큰이 남아 401 → 프롬프트 → 각자 **다시 붙여넣기** | 사람마다 1회 |
| `client2/dist` 번들 | 토큰은 번들에 박혀 있지 않다 | **재빌드 불필요** |

**절차 (이 순서를 지킬 것)**

1. 새 토큰을 만든다 — `openssl rand -hex 24` (ASCII 전용).
2. 어드민 작업 중인 사람이 없는지 확인한다. 저장 도중 전환되면 그 요청은 401로 죽는다.
3. 환경변수를 새 값으로 바꾸고 **런처(`run_decoupled_app.py`)를 통째로 재기동한다.**
   - ⚠️ **웹서버만 재기동하지 마라.** 워커가 옛 토큰을 든 채 남으면 `/internal/events/*`가 **401**을 돌려주고, **실시간 동기화가 조용히 멈춘다** — 화면은 멀쩡하고 데이터만 안 들어온다. 증상은 워커 로그의 `API notification failed: ... -> 401`뿐이다.
4. 기동 배너가 `[admin-auth] ... is set`(**INFO**)인지 본다. `ERROR`면 새 값에 비-ASCII가 섞인 것이고, 이때 서버는 **미설정 상태로 돌아가 있다**(잠긴 것이 아니라 **열린 것**이다).
5. 운영자들에게 "어드민에서 한 번 다시 물어볼 것"이라고 알린다. 각자 새 값을 붙여넣으면 끝이다.

> **유출됐다면**: 토큰은 사용자별이 아니라 **공유**다. 즉 폐기 목록도, 한 사람만 끊는 방법도 없다 — **전원 교체**가 유일한 대응이다. 그리고 토큰이 유출됐다는 것은 그 시점까지 `/admin/scripts/code`로 임의 파일이 쓰였을 수 있다는 뜻이므로, 교체와 함께 `mappers/`·`<workspace>/scripts/`·`auto_update/`의 변경 이력을 확인하라.
> **로그아웃 버튼은 없다.** 특정 브라우저에서 토큰을 지우려면 그 브라우저 개발자도구에서 `localStorage.removeItem('assy.adminToken')`.

---

## 2. 기능을 켤 때만 필요한 것

각 기능은 **현장 테이블이 `table_config.json`에 선언돼 있어야** 동작한다. 아래 이름은 **예시일 뿐 표준이 아니다** — 우리 이름으로 선언하고, config의 `table`/`columns`를 그 이름에 맞추면 된다.

| 기능 | config 파일 | 필요한 현장 테이블(예시) |
|---|---|---|
| **전사 계획 / DOE** (M2) | `transfer_plan_config.json` | stage 참조 테이블 — `dt_map`, `dt_log`, `bonding_log`, `eds_fail_map` 등 |
| **본딩 가용량** (M1) | `bonding_plan_config.json` | `bonding_log`, `core_defect_map`, `eds_fail_map`, `wafer_process` |
| **맵 오버레이** | `map_overlay_config.json` | 겹칠 맵 테이블들 (x/y 컬럼 + 맵 키 컬럼 선언 필요) |
| **체인 인제션** | `chain_rules.json` | 트리거/타깃 테이블 + `server/mappers/`의 매퍼 모듈 |
| **결손 보완** | `enrichment_rules.json` | 규칙이 참조하는 테이블 |
| **온톨로지 그래프** | `ontology_mapping.json` | 노드/엣지로 승격할 테이블 |

**상태 확인**: 바인딩이 제대로 붙었는지는 API가 알려준다. `missing`이 뜨면 그 테이블이 `table_config.json`에 없거나 컬럼명이 어긋난 것이다.

```bash
curl http://localhost:8080/api/transfer-plan/stages
```

---

## 3. 맵을 쓴다면 — 정렬의 전제

**`wafer_map_metadata` 등록이 전제다.** 맵을 담는 모든 테이블(defect·EDS·DT·bonding·core)이 대상이고, **미등록은 정상 상태가 아니라 누락**이다.

- 정렬은 소스·타깃 메타의 **델타에서 유도**된다. 별도 보정 레이어는 없다.
- 계측 결과(DEFECT WF 돌려서 잰 값)도 **메타에 기록**한다.
- 메타가 없으면 화면에 `화면기준` 칩이 뜬다 — "지금 화면 규격으로 가정해서 그렸다"는 뜻이다. 이 칩이 보이면 그 맵은 메타를 등록해야 한다.

`maps.json`에 **제품 규격별 프리셋**을 만들어 두면 등록이 쉬워진다. 프리셋 한 세트가 곧 메타 JSON이다:

```json
{"grid_cols":40,"grid_rows":40,"grid_start_x":1,"grid_start_y":1,"grid_y_invert":false,
 "rotation":180,"side":"front","phys_wafer_dia":300.0,"phys_chip_x":7.0,"phys_chip_y":7.0,
 "phys_offset_x":0,"phys_offset_y":0,"phys_edge_margin":3.0}
```

> 격자 크기(`grid_cols/rows/start`)는 **방향·물리 규격에서 파생**된다. 데이터 좌표 범위에서 역산하지 마라.

---

## 4. 선택 — 기본값으로 둬도 되는 것

| 파일 | 안 만들면 | 언제 손대나 |
|---|---|---|
| `ingestion_settings.json` | 전부 기본값 동작 | heavy 임계(기본 10MB) 조정, dedup·재개 끄기 |
| `auto_update_control.json` | 수집기 전부 활성 | 특정 수집기만 끄고 싶을 때 |
| `maps.json` | 프리셋 없음 | 맵 프리셋 등록 시 (§3) |

---

## 5. 검증/개발 환경 (선택이 아니라 **검증의 기본 자리**)

운영 데이터 위에서 테스트하지 않는다. 에이전트·QA의 검증 작업은 전부 여기서 한다.

```bash
python server/scripts/dev_env/devenv.py snapshot     # 운영에서 읽기 전용 스냅샷 → assy_qa
python server/scripts/dev_env/devenv.py up           # :8081, 워처·스케줄러 없음
python server/scripts/dev_env/devenv.py status       # 무엇이 떠 있고 어디를 보고 있나
python server/scripts/dev_env/devenv.py env          # 일회성 스크립트용 환경변수 출력
python server/scripts/dev_env/devenv.py down
```

무엇이 갈리는가 — 넷 다 갈린다.

| | 운영 | 격리 |
|---|---|---|
| DB | `assy_manager` | `assy_qa` (`DATABASE_URL`) |
| 디스크 | `server/config`, `server/ingestion_workspace` | `dev_env/…` (`ASSY_DATA_ROOT`) |
| API | 127.0.0.1:8080 | 127.0.0.1:8081 |
| 그래프 워커 | 127.0.0.1:8090 | 127.0.0.1:8091 |

`ASSY_DATA_ROOT`가 `config/`·`ingestion_workspace/`**·프로세스 로그**를 통째로 옮기는 단일 지점이다(`server/paths.py`). 안 걸면 기존 경로 그대로다.

> ✅ **로그도 따라온다(2026-07-27).** 이전에는 `utils/logger.py`가 자기 `__file__`에서 경로를 만들어 격리 프로세스가 **운영 로그 파일에 덧썼다**. 인시던트를 재구성하려고 읽는 로그에 드릴의 줄이 섞이면 안 된다. 같은 스윕에서 `virtual_graph.json` 경로 누수도 닫혔다.

### 5.1 인제션 드릴용 격리 워처

`up`은 **일부러 워처와 스케줄러를 띄우지 않는다** — 2분 주기 수집기의 churn이 측정 재현성을 깨는 주범이다. 드릴에 워처가 필요하면 **별도 동사**를 쓴다.

```bash
python server/scripts/dev_env/devenv.py watcher-up
python server/scripts/dev_env/devenv.py watcher-down
```

**운영을 향한 워처는 기동 자체를 거부한다.** 이건 규율이 아니라 구조다:

- 관문은 **순수 함수**(`iso_watcher.check_static_isolation` / `check_live_isolation`)라 프로세스·연결 없이 "이 설정이면 거부되는가"를 물어볼 수 있다.
- **로그를 열거나 DDL을 내기 전에** 돈다(`import run_watcher`만으로도 로그 핸들러가 생기고 DDL이 나간다).
- 라이브 검사는 방금 읽은 환경변수가 아니라 **실제로 열린 세션에 `SELECT current_database()`를 묻는다.** `assy_qa`라고 적혀 있지만 다른 데로 붙는 URL이 여기서 잡힌다.
- **증명하지 못하는 것도 거부**다(DB 도달 불가·URL 파싱 실패 = 경고가 아니라 거부).

---

## 6. 순서 요약

1. PostgreSQL 준비 → `DATABASE_URL` 설정
2. `server/config/*.sample` → 확장자 떼고 복사 (**기존 환경이면** `install_product_tables.py --apply`로 제품 소유 4종만 병합 — §1-2)
3. **`table_config.json`에 우리 현장 테이블 선언** (여기가 대부분의 작업)
4. `server/ingestion_workspace/<테이블>/` 디렉터리 생성
5. 켤 기능의 config에서 `table`/`columns`를 우리 이름으로 맞춤 (§2)
6. 맵을 쓴다면 `wafer_map_metadata` 등록 (§3)
7. **`ASSY_ADMIN_TOKEN` 설정** (§1-4) — 안 하면 어드민의 코드 저장·즉시 실행이 503으로 막힌다
   - ⚠️ **먼저** `grep -c X-Admin-Token client2/dist/assets/admin-*.js`가 1 이상인지 확인. 0이면 번들부터 다시 빌드·커밋한다(§1-4) — 아니면 토큰을 켜는 순간 어드민 페이지가 잠긴다
8. 기동 → 서버 로그 첫 줄에서 `[admin-auth]`가 **WARNING/ERROR가 아닌지** 확인(`ERROR`면 토큰이 비-ASCII라 무시된 것) → `curl http://localhost:8080/health` 가 **JSON 200**인지 → `/api/transfer-plan/stages` 등으로 바인딩 상태 확인

### 6.1 기동 후 상시 감시

`GET /health`를 폴링하면 된다. **HTTP 코드만 봐도 된다** — 정상 200, 조치 필요 503. 어디가 문제인지는 본문 `problems[]`가 문장으로 담는다.

- 워커는 pid가 아니라 **진행 박동**으로 판정된다 — 살아 있는 채 멈춘 프로세스(`wedged`)를 잡기 위해서다. 상태값은 8종이고([backend §1.3](../architecture/backend.md)), 그중 **`stalled`는 따로 봐야 한다**: 박동은 신선한데 **claim한 작업이 300초간 무진행**인 경우로, "워커는 살아 있고 루프도 도는데 일이 안 나가는" 상태다.
- outbox 적체는 **크기가 아니라 나이**로 판정된다. 큰 파일 하나가 outbox 십만 행을 만드는 것은 정상이다.
- 자식 프로세스는 런처가 감시·재시작한다. **6번째 연속 실패에서 포기**하고 `/health`가 계속 503을 낸다 — 그때는 사람이 고쳐야 한다는 뜻이다.
- 계약 상세: [backend §1.3](../architecture/backend.md)

---

## 7. 함정 (실제로 물린 것들)

- **`.sample`을 복사만 하고 테이블 선언을 안 하면** 바인딩이 전부 `missing`이 된다. `.sample`은 *기능 템플릿*이지 완성된 설정이 아니다.
- **`/tables/{t}/schema`가 200이라고 물리 반영의 증거가 아니다** — config 싱글턴을 읽는다. 실제 컬럼은 `information_schema`로 확인하라.
- **기존 테이블에 컬럼을 추가하면** 런타임 ALTER는 `config_watcher`만 한다. `/admin/reload-configs`는 **신규 CREATE 전용**이다. (저장 방식은 무관하다 — 2026-07-29 #9/H3부터 제자리 쓰기·원자적 rename·타 디렉터리 rename을 모두 감지한다. 반영은 마지막 쓰기 후 약 1초.)
- **존재하지 않는 API 경로는 정적 catch-all이 HTML을 200으로 반환한다.** 오타 난 경로가 성공처럼 보인다. `/health`는 **실제 라우트로 존재하며 항상 JSON**이니(2026-07-27 신설) 감시 대상은 그쪽으로 붙이고, 그 외 경로를 살아있음의 근거로 쓰지 마라.
- **미선언 컬럼은 저장에서 조용히 버려진다.** `table_config.json`에 없는 컬럼을 보내면 드롭되고 **200이 나간다.** 2026-07-27부터 `(테이블, 컬럼)`당 1회 경고가 남으니, 값이 안 들어갈 때는 서버 로그의 `[Schema]` 경고부터 보라(⚠️ 워처 프로세스 로그 배선은 [PRODUCTION_READINESS](../process/PRODUCTION_READINESS.md)로 미해결).
- **`server/config/`와 `server/ingestion_workspace/`는 백업 대상이다.** git에 없다 — 그리고 **일부러** 없다(배포 시 현장 자산 오염 방지). git에 넣어 "고치지" 마라.
  - **config는 2026-07-28부터 자동 백업된다** — 주 1회 `<이름>_<yymmdd>.json.bak` 스냅샷, 1개월 FIFO. Auto-Update 스케줄러가 돌리며, **위험한 배포 전에는 손으로 하나 더 뜨는 것이 권장 절차**다: `python server/scripts/backup_config.py snapshot`. 규격은 [CONFIG_GUIDE §1](CONFIG_GUIDE.md), 복원은 [ROLLBACK_PROCEDURE §3.1-bis](ROLLBACK_PROCEDURE.md).
  - ⚠️ **`ingestion_workspace/`는 아직 자동 백업 대상이 아니다**(매퍼·수집기 스크립트가 여기 있다). 여기는 여전히 사람이 챙겨야 한다.
  - 백업이 멈추면 `/health`의 `checks.config_backup`이 `degraded`로 알린다 — **첫 배포 직후에는 스냅샷이 없으므로 정상적으로 `missing`이 뜬다.** 스케줄러가 한 번 돌면 사라진다.
- 🚨 **config를 코드보다 먼저 바꾸면 코드만 되돌려서는 복구되지 않는다.** 계획·오버레이 계열 config(`transfer_plan_config`·`bonding_plan_config`·`map_overlay_config`)는 **요청마다 디스크에서 다시 읽히고**, 코드는 **재기동까지 고정**된다. 즉 두 반영 시점이 애초에 다르다.
  - **실제 사례(2026-07-27, M2.6)**: `transfer_plan_config.json`의 `plan_store`를 새 바인딩으로 먼저 바꿨고, 실행 중인 웹서버는 옛 모듈을 들고 있었다 → `GET /api/transfer-plan/validate`가 **404**. 여기서 코드를 되돌려도 config가 이미 새 형태라 **양쪽 어느 조합도 동작하지 않는다.**
  - **규칙**: 배포는 **코드 → 재기동 → config**. 롤백은 **config → 코드 → 재기동**. 목록을 거꾸로 읽은 것이 아니다 — **재기동이 배포에서는 가운데, 롤백에서는 맨 마지막**이며, 그래야 재기동 시점에 config가 이미 옛 형태라 시스템이 정확한 상태로 올라온다.
  - **전체 절차는 [ROLLBACK_PROCEDURE](ROLLBACK_PROCEDURE.md)** — 2026-07-28에 격리 스택에서 **전 구간 드릴을 실행**했다(코드만 되돌리면 여전히 깨져 있고 `/health`는 `ok`라고 말한다는 것까지 실측). 올바른 순서의 총 소요는 **30초**, 사용자 체감 장애는 **16초**.
  - 같은 배포에서 `table_config.json`의 컬럼 추가는 `config_watcher`가 **재기동 없이** ALTER를 실행한다. 즉 한 배포 안에서 **컬럼은 즉시·config는 즉시·코드는 재기동 후**로 반영 시점이 셋으로 갈린다.
  - ⚠️ 그 ALTER는 `print()`로만 나가고 **로그 파일에 남지 않는다** — 런처가 자식 stdout을 리다이렉트하지 않으므로 **운영자 콘솔에만** 뜬다. 재기동하면 사라지니, 롤백 전에 스크롤백을 복사해 두라.
  - ⚠️ **되돌려도 물리 스키마는 되돌아가지 않는다.** 선언을 지워도 `CREATE`된 테이블·`ALTER`된 컬럼은 남는다. 잔여물 찾기 → `python server/scripts/list_undeclared_tables.py` (읽기 전용, [ROLLBACK_PROCEDURE §5](ROLLBACK_PROCEDURE.md)).
