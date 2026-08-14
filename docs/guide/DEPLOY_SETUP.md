# 🚀 운영 배포 — 직접 세팅해야 하는 것들 (요약)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-13
>
> **이번 라운드 (2026-08-13 3차)**: **§6에 마이그레이션 단계 둘이 늘었고, 배포 «의존성»이 하나 늘었다.** **8-sexies**(`346aa88` · void 스키마 인덱스 — 🔴 **3단계이지 1단계가 아니다**, 선언 손복사와 리로드가 테이블을 만든 «다음»에만 붙는다. 🔴 `idx_void_obs_area`는 **식 인덱스**이고 **면적 컬럼은 없어야 한다**). **8-septies**(`f896020`+`bee1aeb` · 정준 원장 — **추가 전용·멱등이고 안 돌려도 아무것도 안 깨진다**, 다만 그 상태에서 trace 라우트는 503 + 관계 이름으로 답한다). 🔴 **`environment.yml`에 `tzdata`가 새로 들어왔다** — `Asia/Seoul`은 런타임에 IANA DB에서 해석되고 `UTC`는 그런 적이 없었다. **없으면 폴백하지 않고 예외를 낸다**(조용한 UTC 폴백이 방금 고친 결함의 재현이므로). 🔴 **시간대 판정 «다음»에 원장을 돌려라 — 어긋난 시각도 well-formed해서 어떤 가드도 못 알아챈다.** 그리고 **§1-2에서 `map_doe`·`map_doe_source`가 은퇴했다**(`c0fb735`) — ⚠️ **기존 환경의 gitignore된 `table_config.json`에는 아직 남아 있을 수 있다.** 🔴 §1-2의 제품 소유 **목록**이 세 번째로 낡아, 이번에는 **수도 목록도 적지 않는다**(정본은 `product_tables.py`).
>
> **직전 라운드 (2026-08-13 2차)**: **§6-8의 배너 읽는 법에 `SELF-HEALING` 계급이 늘었다**(`eb700e5`) — config로 선언한 **동적 테이블**의 컬럼은 서버 프로세스 기동이 **스스로 추가**하고 이 점검은 그보다 **먼저** 돌 뿐이다. 🔴 **「할 일 없음」이고 마이그레이션을 쓰면 안 된다** — 종전에는 이것도 「이 테이블을 쓰는 모든 화면이 실패한다」로 나갔고 제품 소유자가 그 값을 냈다. ⚠️ **다만 «두 번째» 목격은 진짜다**(재기동 뒤에도 남으면 그 `ALTER`가 실패 중). **직전 라운드 (2026-08-13 1차)**: **§6에 마이그레이션 단계 둘이 늘었다** — **8-quater**(`ba664c5` · 인제션 원장 tier-1 열쇠. 안 돌리면 그 테이블이 **읽기부터** 죽는다)와 **8-quinquies**(`8bdc136` · `dt_inventory.dt_lot`/`dt_slot` 물리 타입). 🔴 **둘의 성격이 다르다**: 앞엣것은 **코드가 그 컬럼을 요구해서** 안 돌리면 깨지고, 뒤엣것은 **아무것도 안 깨진 채 선언과 물리가 계속 어긋난다** — 그래서 뒤엣것은 배너가 아니라 `audit_schema_canon.py`가 답한다.
>
> **직전 라운드 (2026-08-11)**: **§6에 8-ter 신설**(`dab9152`+`2630790` — 감사 이력 인덱스 세 종, 없으면 오늘의 성능 수리가 프로덕션에 안 먹는다) + **3단계에 `dt_job` 리네임 경고**(`5b09d69` — 컬럼명을 `table_config.json`에서 바꿔도 `add_dt_log_trigger_indexes.sql`의 인덱스 정의와 `enrichment_rules.json`의 자유 SQL 다섯 곳은 체인 리졸버 밖이라 조용히 안 따라온다. 정본은 [DT_CORE_FRAME_CHAINS_GUIDE §1-bis](./DT_CORE_FRAME_CHAINS_GUIDE.md#1-bis-잡-컬럼-이름-2026-08-11)).
>
> **직전 라운드 (2026-08-08 · D3 `4738d84`+`528dfcb`)**: **§6에 8-bis 신설 — 업무 키 UNIQUE 인덱스는 이제 배포 순서의 일부다.** 집합 기반 쓰기 경로가 행마다 내던 신원 SELECT를 없애면서 프로세스 간 경합 창이 **마이크로초 → 실측 2.4초**로 넓어졌고, 실제 프로세스 둘로 **한 업무 키에 두 행**이 재현됐다. 🔴 **8의 `--preflight-only`는 이것을 못 잡는다** — 드리프트 점검이 보는 것은 **컬럼**이지 인덱스가 아니다(실측: `schema_drift.py`에 인덱스 검사 0건).
>
> **직전 라운드 (2026-08-05 · `f6406b1`)**: **§6에 8단계 `--preflight-only` 신설** — 배포·재기동 직전에 **아무것도 띄우지 않고** 포트와 **스키마 드리프트**를 묻는 자리다. 🔴 **드리프트는 `/health`에 나오지 않는다**(§6.1) — 드리프트난 스택은 `/health`가 **정상 200**을 답하면서 그 테이블의 화면만 500을 내고, 2026-08-05 하루에 3건이 그렇게 나가 **전부 제품 소유자가 제품을 쓰다가 발견했다.** ⚠️ **종료 코드는 포트만 본다** — 스크립트로 감싸지 말고 배너를 읽을 것.
>
> ⚠️ **[doc-keeper 2026-08-05] 아래 괄호는 약 5,000자짜리 변경 이력이고 CONTRIBUTING §3의 「`Last-verified`는 날짜까지」를 어긴다** — `frontend.md`·`MAP_EDITOR_SPEC`·`PRIMITIVES`가 같은 이유로 이미 걷어냈다. **총괄 판단 대기**(내용이 `docs/history/`에 전부 있는지 확인해야 지울 수 있다).
>
> <details><summary>이전 라운드 기록 (접힘)</summary>
>
> (**§1-5-A의 기동 로그 판정을 4갈래 표로 교체 + §1-5-C-4 정정** — 🔴 **이 문서는 「`/health`가 200이 아닌 상태로 답하면 앞단이 답한 것이다」를 두 곳에서 말하고 있었고 그것이 거짓이 됐다.** `/health`는 체크 하나만 실패해도 **설계상 503**을 돌려주므로 그 규칙은 **아픈 스택을 프록시로 고발**한다 — 2026-07-31 중복 런처 인시던트에서 실제로 워커 두 개가 프록시 장문을 찍어 진단을 오도했다. 지금 판별자는 상태코드가 아니라 **응답 BODY**다(`internal_event_client.own_health_payload` — `status` 키와 dict `checks`가 **함께** 있으면 우리 것). 갈래는 `INFO`(200 직결) · `INFO`(연결 거부 = 기동 중 정상) · **`WARNING`(우리 body → 앱이 살아 있고 스스로 아프다)** · `ERROR`(그 밖 → 앞단). 탐지가 없어진 게 아니라 **방아쇠만 좁아졌다**. 직전 2026-07-30: **§1-4·§1-5를 증상 우선으로 재구성 + 「프로세스는 태어날 때의 환경을 쥔다」 신설** — 내용은 `4e23a9f`에서 맞았고 이번에 고친 것은 **형태**다. 운영자는 증상을 들고 오는데 두 절이 개념 순서로 짜여 있었다. ① 🔴 **§1-4-A 신설 — 하루 오후를 태운 사실이 어느 문서에도 없었다.** 프로세스는 **기동 시점의 환경 사본**을 쥐고, 「새 터미널을 열어라」는 그 터미널이 편집기(원격에서는 `vscode-server`)의 자식일 때 아무 소용이 없다. 이 상태에서는 §1-4의 **나머지 모든 지시가 듣지 않는 것처럼 보이므로** 맨 앞에 뒀다. 판별은 한 동작(도구의 자식이 **아닌** 셸에서 값 읽기), 해소는 호스트별 표(편집기 완전 종료 · 원격 호스트에서 `vscode-server` 프로세스 kill · SSH 재접속 · `Machine` 범위를 SSH로 읽으면 `Restart-Service sshd`). ② **설정을 네 칸 표로**(cmd·PowerShell × 세션·영구) — 운영자가 "cmd 호환은 안 되나"를 물은 자리다. 함정은 명령 **옆에** 뒀다: PowerShell `set`은 `Set-Variable` 별칭이라 조용히 실패, `setx`는 1024자에서 조용히 잘리고 **지울 수 없으며**(`setx VAR ""`는 빈 값을 남긴다), `SetEnvironmentVariable`은 **추가가 아니라 교체**(이 형태로 `NO_PROXY`의 사내 호스트 목록을 날렸다). ③ **검증을 지문 3자리 대조로 확정** — 운영자 셸(**환경에서 읽는** 형태)·웹서버 배너·워커 배너. 토큰 값은 어디에도 출력되지 않는다. ④ **로테이션을 §1-4-G로 되돌림** — 토큰 항목인데 §1-5(프록시) 아래에 들어가 있었다. ⑤ **§1-5-C-2 신설** — 수집 스크립트의 프록시는 이제 스케줄러가 **자기 프로세스에서** 정한다(`auto_update_control.json`의 `bypass_proxy`, 기본 직결, `4aae627`). 수집 403은 환경변수를 만지기 전에 이 값을 먼저 본다. ⑥ 🔴 **C-4 정정 — 「소스에 낡은 `NO_PROXY` 안내가 남아 있다」는 경고가 하루 만에 거짓이 됐다**(`98956fd`가 그 문구를 `[금지] NO_PROXY 를 설정하지 마세요`로 바꿨다). 직전 2026-07-30 `4e23a9f`: **§1-4에 영구 설정 신설 + §1-5 프록시 권장안 철회** — 최근 이틀의 운영자 실패가 **전부 이 파일 하나**에서 나왔다. ① **§1-4 「아래 세 줄은 전부 셸이 닫히면 사라진다」 신설** — `$env:`/`set`/`export`가 모두 프로세스 수명이라는 말이 **어디에도 없었고**, 그래서 운영자는 매 세션 다시 치거나 잊고 **잠기지 않은 서버**를 띄웠다. 답은 `[Environment]::SetEnvironmentVariable(..., "User")`이고, 이것이 `run_app.bat`(**cmd.exe**)가 PowerShell `$env:` 값을 못 보는 국면도 함께 닫는다. `"Machine"`은 금지(비밀을 전 사용자에게 노출). 🔴 **「추가가 아니라 교체」 경고를 명령 바로 옆에** 뒀다 — 실제로 이 형태로 `NO_PROXY`를 세웠다가 **사내 호스트가 든 기존 값을 날려** 자동 업데이트가 전부 403이 됐다. ② 🔴 **§1-5의 `$env:NO_PROXY` 권장 철회**(`94b9baa`) — 이름과 반대로 **그 트리의 모든 요청이 프록시를 안 타게 된다**: `urllib.request.getproxies()`가 `getproxies_environment() or getproxies_registry()`인데 `no_proxy`도 이름이 `_proxy`로 끝나 환경 dict를 비지 않게 만들고 **레지스트리가 조회되지 않는다**(실측: 없으면 `{}`, 있으면 `{'no': ...}`). 런처가 `os.environ.copy()`로 물려주므로 스케줄러의 사용자 스크립트 전부가 사내 API에서 403. 코드의 `trust_env=False`는 **우리 세션 객체에만** 붙어 이 성질이 없다. ⚠️ `internal_event_client.check_api_reachable()`의 ERROR 문구에 **아직 낡은 NO_PROXY 안내가 남아 있음**을 명기(코드 정정은 별건). ③ 지문 검사(`23a346d`)·ASCII 전용 경고는 **이미 §1-4에 있었음을 확인**(중복 추가 안 함). 직전 2026-07-28: §7 롤백 항목을 **드릴 실측**으로 교체 — 재기동 위치·`/health` 사각·스키마 잔여물. 전체 절차는 [ROLLBACK_PROCEDURE](ROLLBACK_PROCEDURE.md)로 분리. 직전: `90e284f` §1-4 `ASSY_ADMIN_TOKEN`)
>
> </details>
>
> **대상:** 새 환경에 assyManager를 올리는 사람
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

- **이미 들어 있는 것(제품 소유 — 그대로 두기)**: `wafer_map_metadata`, `map_split_registry`(전사 계획의 DOE 저장소 — `knobs`·`bands` 컬럼 포함), `valid_die_ref`. 🗄️ **[2026-08-13 `c0fb735`] `map_doe`·`map_doe_source`는 은퇴했다** — 선언·설치기 양쪽에서 사라졌다(2026-07-27 폐기 → 제품 소유자가 물리 삭제 승인). ⚠️ **기존 환경의 `table_config.json`에는 아직 남아 있을 수 있고**(이 파일은 gitignore라 배포가 안 덮는다) 남아 있어도 새로 쓰는 코드는 없다. 물리 `DROP`은 [process/OPERATOR_RUNBOOK §5](../process/OPERATOR_RUNBOOK.md).
- **내가 추가할 것(현장 소유)**: 우리 공장 로그·맵 테이블 전부. 아래 §2의 기능별 표 참조.

각 테이블에 필요한 것: 컬럼 정의(`column_types`), **비즈니스 키**(`business_key`), 복합키면 `composite_key_source` + `composite_key_separator`.

> ⚠️ **구분자 함정**: 맵 키는 `_`가 흔하고 테이블명에도 `_`가 있다. 복합키 구분자로 `_`를 쓰면 파싱이 깨진다. 제품 소유 테이블은 `|`를 쓴다 — 새로 만들 때도 `|` 권장. 🔴 **[2026-08-06 정정 · 2026-08-13 갱신] 종전 이 자리는 「제품 소유 *3종*」이었고 바로 아래 §는 「*4종*」이라 적어, 같은 파일이 같은 집합에 두 수를 적고 있었다.** 그 뒤 목록을 다섯으로 적었고, `c0fb735`가 그중 둘을 은퇴시켜 **그 목록도 낡았다** — 이것이 세 번째다. **수도 목록도 여기 다시 적지 않는다. 정본은 `server/product_tables.py`의 `PRODUCT_TABLES` 하나다.**

#### 제품 소유 테이블은 **손으로 옮기지 않는다** (2026-07-27 · 2026-08-06 기수 삭제)

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

#### 증상에서 시작하기 — 어느 항으로 갈 것인가

| 증상 | 십중팔구 이것 | 가는 곳 |
|---|---|---|
| 설정했는데 기동 로그가 `is NOT set`이다 | 그 프로세스가 **변경 전에 떠 있었다** | **A** 먼저, 아니면 B |
| 새 터미널을 열었는데도 값이 없다 | 그 터미널이 **낡은 것의 자식**이다 | **A** |
| 지웠는데 값이 그대로 살아 있다 | 같은 이유. 또는 `setx VAR ""`로 지운 줄 알았다 | **A** → B |
| 창을 닫을 때마다 사라진다 | 세션 범위 명령을 썼다 | B의 「영구」 열 |
| 프로세스마다 지문이 다르다 | 일부가 다른 셸·다른 시점에 떴다 | D |
| 워커 로그에 `admin-gate=yes` + 401/403 | **우리 게이트**가 거부했다 — 토큰 문제다 | D |
| 워커 로그에 `admin-gate=no`, 또는 게이트가 없는 `GET /health`까지 403 | **우리가 아니다** — 앞단이 거부했다 | **§1-5** |
| 어드민 페이지가 토큰을 **묻지도 않고** 죽는다 | 옛 번들이 서빙되고 있다 | F |

#### A. 🔴 프로세스는 태어날 때의 환경을 쥔다 — 「설정했는데 없다」의 첫 번째 원인 (2026-07-30)

**변수를 바꿔도 이미 돌고 있는 프로세스에는 닿지 않는다.** 그리고 **「새 터미널을 열어라」는 그 터미널이 낡은 것의 자식일 때 아무 소용이 없다.** 편집기의 통합 터미널은 편집기의 자식이고, 편집기는 **자기가 뜰 때 복사해 둔 환경**을 자식마다 그대로 나눠 준다. 탭을 새로 열어도 부모가 그대로이므로 값도 그대로다.

2026-07-30에 이것이 오후를 통째로 태웠다. 토큰을 영구로 세웠는데 보이지 않았고, 프록시 변수를 지웠는데 되살아났다. 레지스트리 범위·`setx` 의미·셸 별칭을 전부 뒤졌지만 원인은 하나였다 — VS Code(원격 호스트에서는 그 위의 `vscode-server`)가 **변경 전에 떠 있었고**, 그 안에서 연 모든 터미널에 자기 환경을 물려주고 있었다. code 서버를 죽이자 **토큰과 프록시가 동시에** 정상으로 돌아왔다.

**이 항이 맨 앞인 이유:** 이 상태에서는 아래 B~F의 **모든 지시가 듣지 않는 것처럼 보인다.** 명령은 맞았는데 확인하는 창이 거짓말을 하고 있는 것이다.

**판별 — 한 동작.** 도구의 자식이 **아닌** 셸을 하나 연다. 시작 메뉴 → `cmd`, 또는 새 SSH 접속. 거기서 값을 읽는다:

```powershell
[Environment]::GetEnvironmentVariable("ASSY_ADMIN_TOKEN", "User")
```

| 그 셸에서 값이 | 뜻 | 다음 |
|---|---|---|
| **맞다** | 변수는 정상이다. **도구가 낡은 환경을 쥐고 있다** | 아래 해소 표 |
| **틀리다 / 없다** | 변수 자체가 잘못 세워졌다 | B로 |

> ⚠️ 판별용 셸을 **도구 안에서** 띄우면(통합 터미널에서 `Start-Process`, 편집기의 새 탭) 그것도 자식이라 같은 낡은 값을 본다. 시작 메뉴·탐색기·새 SSH 접속만이 유효한 판별이다.

**해소 — 무엇이 낡은 환경을 쥐고 있느냐로 갈린다.**

| 쥐고 있는 것 | 해소 | 함정 |
|---|---|---|
| 로컬 편집기(VS Code 등) | **완전히 종료 후 다시 실행** | 터미널 **탭**을 새로 여는 것으로는 안 된다 — 부모가 그대로다 |
| Remote-SSH의 원격 서버 | 원격 호스트의 `vscode-server` 프로세스를 죽인다(아래 명령) | 팔레트 명령은 버전마다 이름이 다르거나 아예 없다 — **프로세스로 잡는 편이 확실하다** |
| SSH 세션 | **접속을 끊고 다시 붙는다** | 세션 **안에서** 새 셸을 여는 것은 소용없다 |
| `Machine` 범위를 SSH로 읽는 경우 | 관리자 셸에서 `Restart-Service sshd` | sshd는 **서비스가 뜰 때** 머신 환경을 읽는다 |
| 이미 돌고 있는 런처·워커 트리 | 런처(`run_decoupled_app.py`)째 재기동 | 웹서버만 재기동하면 워커가 옛 값을 쥔 채 남는다 → G |

```powershell
# 원격 호스트에서 실행한다.
Get-Process node -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like "*vscode-server*" } |
  Stop-Process -Force
```

- **평범한 SSH 세션에서** 돌린다. 편집기의 통합 터미널에서 돌리면 그 서버가 낳은 그 터미널도 함께 죽어 결과를 못 본다(죽는 것 자체는 정상이다 — 다시 붙으면 서버가 새 환경으로 다시 뜬다).
- 아무것도 안 잡히면 실행 파일 이름이 `node`가 아닐 수 있다. `Get-Process | Where-Object { $_.Path -like "*vscode-server*" }`로 먼저 본다.

#### B. 설정하기 — 셸 × 수명, 네 칸이 전부다

**두 방법이 다른 변수를 만들지는 않는다.** 영구 쪽 둘은 같은 레지스트리 자리에 쓰고, 세션 쪽 둘은 같은 프로세스 환경에 쓴다. **어느 셸에서 무엇을 타이핑하느냐의 문제일 뿐**이다.

| | **세션만** — 그 창을 닫으면 소멸 | **영구** — 이후에 뜨는 프로세스부터 |
|---|---|---|
| **PowerShell** (운영 기본) | `$env:ASSY_ADMIN_TOKEN = "<토큰>"` | `[Environment]::SetEnvironmentVariable("ASSY_ADMIN_TOKEN", "<토큰>", "User")` |
| **cmd.exe** | `set ASSY_ADMIN_TOKEN=<토큰>` | `setx ASSY_ADMIN_TOKEN "<토큰>"` |
| bash/zsh(참고) | `export ASSY_ADMIN_TOKEN=<토큰>` | — (Windows 영구 범위는 위 두 형태로) |

**세션 칸의 함정**

- 🚨 **PowerShell에서 `set`을 쓰면 조용히 실패한다.** `set`은 PowerShell에서 `Set-Variable`의 **별칭**이라, `set ASSY_ADMIN_TOKEN=admin`은 `ASSY_ADMIN_TOKEN=admin`이라는 이름의 **PowerShell 변수**를 만들고 끝난다. 환경변수는 건드리지 않으므로 uvicorn·워커 자식 프로세스는 아무것도 못 본다. **에러가 나지 않아 성공한 것처럼 보인다** — 판별법은 기동 로그의 `is NOT set` 경고가 사라졌는지 하나뿐이다(2026-07-28 실제로 여기서 막혔다).
- 설정한 **바로 그 셸에서** 런처를 띄워야 한다. 자식 프로세스는 기동 시점의 환경을 복사해 가므로, 다른 창에서 설정하면 영원히 반영되지 않는다.
- `run_app.bat`은 **cmd.exe**라 PowerShell에서 `$env:`로 넣은 값을 **보지 못한다.** 세션 설정을 쓰는 한 이 국면이 남는다 — 영구 설정을 권하는 두 번째 이유가 이것이다.

**영구 칸의 함정**

- 🔴 **추가가 아니라 교체다 — 세우기 전에 지금 값을 읽어라.** `SetEnvironmentVariable`도 `setx`도 기존 값을 **덮어쓴다.** 2026-07-30에 이 형태로 `NO_PROXY`를 세웠다가 **사내 호스트 목록이 들어 있던 기존 값을 통째로 날려** 자동 업데이트 스크립트 전부가 403으로 죽었다. 목록형 변수(`NO_PROXY`·`PATH`·`PYTHONPATH`)는 거의 항상 **이어붙여야 하는** 쪽이다.
  ```powershell
  [Environment]::GetEnvironmentVariable("ASSY_ADMIN_TOKEN", "User")
  [Environment]::GetEnvironmentVariable("ASSY_ADMIN_TOKEN", "Machine")
  ```
- 🚨 **`setx`는 1024자에서 조용히 자른다.** 더 긴 값을 주면 잘린 채 `SUCCESS:`를 찍는다. 긴 값은 `SetEnvironmentVariable` 쪽을 쓴다.
- 🚨 **`setx`로는 지울 수 없다.** `setx VAR ""`는 삭제가 아니라 **빈 값을 남기는** 것이다. 지우는 것은 이쪽이다:
  ```powershell
  [Environment]::SetEnvironmentVariable("ASSY_ADMIN_TOKEN", $null, "User")
  ```
- 🚨 **`"Machine"`을 쓰지 마라.** 그 범위는 **이 컴퓨터의 모든 사용자**가 읽을 수 있는 자리이고, 여기 들어가는 것은 어드민 전권 비밀이다.
- **이후에 뜨는 프로세스부터** 보인다. 이미 열린 창·이미 돌고 있는 편집기에는 반영되지 않는다 → **A**.

#### C. 값의 조건 — ASCII 전용, 그리고 왜 환경변수인가

토큰 값은 **길고 추측 불가능한 ASCII 문자열**이어야 한다.

> 🚨 **반드시 ASCII로.** HTTP 헤더는 latin-1로 디코딩되므로 **한글·이모지 토큰은 절대 인증에 성공할 수 없다.** 서버는 이런 값을 **거부하고 무시**하며 기동 로그에 `ERROR`로 남긴다 — 즉 토큰을 넣었는데도 어드민이 잠기지 않은 상태가 된다. 예전에는 이 경우 "is set"이라고 안심시켜 놓고 올바른 토큰에도 매번 403을 돌려줬다(2026-07-27 수정). `openssl rand -hex 24` 같은 출력이 안전하다.

**환경변수인 이유**: `DATABASE_URL`·`ASSY_DATA_ROOT`와 같은 자리다. 그리고 `server/config/`에 파일로 두면 gitignore가 지켜주긴 하지만 `devenv.py snapshot`이 config 트리를 통째로 복사하므로 **비밀이 두 군데로 늘어난다.** 환경변수는 저장소 안에 아예 존재하지 않는다.

#### D. 검증 — 지문 8자리를 **세 자리에서** 맞춘다

토큰은 로그에도 화면에도 절대 찍히지 않는다. 대신 `sha256(토큰)`의 앞 8자리 16진수(**지문**)를 비교한다. 단방향이라 지문에서 토큰을 되찾을 수 없다. **셋이 같으면 끝난 것이고, 하나라도 다르면 그 프로세스가 다른 셸·다른 시점에 떴다는 뜻이다**(→ A).

| # | 어디서 | 무엇을 본다 |
|---|---|---|
| ① | **운영자의 셸** — 지금 이 창이 실제로 쥔 값 | 아래 한 줄의 출력 |
| ② | **웹서버 기동 배너** | `[admin-auth] ... (token fingerprint <8자리>)` |
| ③ | **워커 기동 배너**(데몬마다 한 줄) | `[admin-auth] <프로세스명>: presenting X-Admin-Token on /internal/events/* (token fingerprint <8자리>)` |

```bash
python -c "import hashlib,os;v=os.environ.get('ASSY_ADMIN_TOKEN');print(hashlib.sha256(v.encode()).hexdigest()[:8] if v else 'none')"
```

> 이 형태는 **환경에서 읽는다** — 운영자가 "넣었다고 믿는 값"이 아니라 그 셸이 실제로 쥔 값의 지문이 나온다. 그것이 ①로 확인하고 싶은 것이다. 손에 든 문자열 자체를 확인하려면 `python -c "import hashlib;print(hashlib.sha256(b'<토큰>').hexdigest()[:8])"`(서버와 같은 계산식이다 — 무염 `sha256`, UTF-8). 단 그 형태는 **토큰이 셸 히스토리에 남는다** — 평소에는 위의 환경에서 읽는 형태를 쓴다.

| 지문 표기 | 뜻 | 조치 |
|---|---|---|
| `a3f19c2b` 같은 16진수 8자리 | 그 프로세스가 쥔 토큰 | **모든 프로세스가 같아야 한다** |
| `none` | 변수 미설정 | 변수를 **추가**하고 트리 전체 재기동 |
| `unusable-non-ascii` | 설정돼 있으나 비-ASCII | 변수를 **교체**(추가가 아니다)하고 트리 전체 재기동 → C |

지문이 도입되기 전에는 배너가 `is set`이라고만 말해서, **두 프로세스의 토큰이 같은지 아닌지 아무도 알 수 없었다.** 2026-07-30 인시던트에서 이것이 진단을 몇 시간 늦췄다.

**미설정일 때의 기동 로그**는 어떤 라우트가 꺼졌고 어떤 변수를 설정해야 하는지 한 줄에 담아 `WARNING`으로 찍는다:

```
[admin-auth] ASSY_ADMIN_TOKEN is NOT set (token fingerprint none). POST /admin/scripts/code and
POST /admin/auto-update/run-now are DISABLED (503) ...
```

**워커 로그에서 401/403을 읽는 법 (2026-07-30 개선).** 통지 실패 줄에 **누가 거절했는지**가 함께 찍힌다. 판정 기준은 게이트가 자기 거부에만 붙이는 `WWW-Authenticate: X-Admin-Token` 헤더 하나다:

| 로그에 찍히는 것 | 뜻 | 조치 |
|---|---|---|
| `admin-gate=yes` + `401` | **우리 게이트**가 거부. 워커가 헤더를 아예 안 보냈다 | 워커 쪽 변수 확인 후 **트리 전체** 재기동 |
| `admin-gate=yes` + `403` | **우리 게이트**가 거부. 양쪽이 **서로 다른 토큰**을 쥐고 있다 | 위 지문 3자리 비교 → 한 셸에서 트리 전체 재기동(웹서버만 재기동하면 재발) |
| `admin-gate=no` | **우리가 아니다.** 앞단(프록시·방화벽·다른 프로세스)이 거부했다 | **§1-5.** 토큰을 아무리 만져도 안 고쳐진다 |

#### E. 설정하지 않으면 — fail closed, 단 부분적으로

| 라우트 | 토큰 미설정 | 토큰 설정 |
|---|---|---|
| `POST /admin/scripts/code`, `POST /admin/auto-update/run-now` | **503으로 거부** (코드 실행 경로 — 설정을 잊었다고 구멍이 열려선 안 된다) | 헤더 필수 |
| 나머지 `/admin/*` 전체 (조회 포함) | 그대로 동작 | 헤더 필수 |
| `/internal/events/*` (워커→웹서버 IPC) | 그대로 동작 | 헤더 필수 — **워커가 자동으로 보낸다** |
| `GET /health` | 항상 무인증 (모니터링 표면) | 항상 무인증 |

나머지를 열어 두는 것은 **의도된 선택**이다. 새 빌드로 처음 재기동한 운영자가 어드민 페이지 전체에서 잠겨버리는 사고를 막는다 — 잃는 것은 위험한 두 개뿐이다.

> `/internal/events/*`는 워커가 웹서버에 보내는 내부 통지다. 조회 전용 어드민은 잠겨 있는데 **모든 접속 클라이언트의 그리드에 임의의 값을 뿌릴 수 있는 이 경로가 열려 있던 것**이 거꾸로였다(2026-07-27). 워커는 런처(`run_decoupled_app.py`)의 환경을 그대로 물려받으므로 **변수를 한 번만 설정하면 따로 해줄 일이 없다.** 단, 워커를 손으로 따로 띄운다면 그 셸에도 같은 변수가 있어야 한다 — 없으면 워커 로그에 `API notification failed: ... -> 401`이 쌓이고 실시간 동기화가 조용히 멈춘다.

**클라이언트**: 어드민 페이지가 게이트 거부(`WWW-Authenticate: X-Admin-Token`)를 받으면 토큰을 한 번 묻고 `localStorage`에 보관한 뒤 `X-Admin-Token` 헤더로 보낸다. 운영자가 할 일은 **처음 한 번 붙여넣기**뿐이다.

#### F. 🚨 토큰을 켜기 전에 — 클라이언트 번들을 반드시 다시 빌드해서 커밋할 것

서버가 서빙하는 것은 `client2/src/admin.js`가 **아니라** 빌드 산출물 `client2/dist/assets/admin-*.js`다(그리고 그 파일은 git에 올라간다). 소스만 고치고 번들을 그대로 두면 **토큰을 설정하는 순간 어드민 페이지가 죽는다** — 요청은 401을 받는데 토큰을 물어보는 코드가 서빙되는 파일에 없어서 **프롬프트가 아예 뜨지 않는다.** 복구하려면 변수를 도로 지우고 재기동해야 하니, 사실상 보안 조치를 되돌리게 된다.

```bash
cd client2 && npm run build      # dist/ 갱신 후 커밋
```

**확인 방법 (운영자·리뷰어 모두 이걸로 판정한다 — 0이면 아직 옛 번들이다):**

```bash
grep -c X-Admin-Token client2/dist/assets/admin-*.js    # 1 이상이어야 한다
```

> **[2026-07-30 `5a14e77`] `npm run build`는 이제 게이트를 통과해야 진행됩니다.** `prebuild`가 클립보드 관례 검사 + **계약 하네스 전부**(`contracts/*/client_harness.mjs` — 🔴 **수를 적지 않는다. 「4종」이라 적혀 있었고 그 사이에 셋이 더 늘었다**. 러너는 목록이 아니라 **발견식 스캔**이고 현재 구성원은 [architecture/frontend §2.1](../architecture/frontend.md)이 센다)을 먼저 돌리고, 하나라도 발산하면 `dist/`가 생성되지 않습니다. **빌드가 실패하면 번들도 갱신되지 않았다는 뜻**이므로 위 `grep` 확인이 0으로 남습니다 — "빌드했는데 왜 그대로냐"의 첫 번째 원인이 이것입니다. 계약이 실제로 바뀐 것이라면 벡터를 고쳐 통과시키지 말고 총괄에 가져가십시오([frontend §2.1](../architecture/frontend.md)).

> ⚠️ 토큰을 **쿼리 파라미터로 보내지 마라.** 쿼리 문자열은 액세스 로그에 남는다. 서버는 헤더만 받는다.

#### G. 토큰 교체(로테이션) — **무중단이 아니다. 계획하고 하라**

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
3. 환경변수를 새 값으로 바꾸고(**B**), **런처(`run_decoupled_app.py`)를 통째로 재기동한다.**
   - ⚠️ **웹서버만 재기동하지 마라.** 워커가 옛 토큰을 든 채 남으면 `/internal/events/*`가 **401**을 돌려주고, **실시간 동기화가 조용히 멈춘다** — 화면은 멀쩡하고 데이터만 안 들어온다. 증상은 워커 로그의 `API notification failed: ... -> 401`뿐이다.
   - ⚠️ 재기동을 **낡은 환경을 쥔 창에서** 하면 옛 값으로 다시 뜬다. 새 셸에서 띄우거나, 편집기 안이라면 **A**를 먼저 한다.
4. 기동 배너가 `[admin-auth] ... is set`(**INFO**)인지 본다. `ERROR`면 새 값에 비-ASCII가 섞인 것이고, 이때 서버는 **미설정 상태로 돌아가 있다**(잠긴 것이 아니라 **열린 것**이다).
5. **D**의 지문 3자리가 모두 같은지 확인한다.
6. 운영자들에게 "어드민에서 한 번 다시 물어볼 것"이라고 알린다. 각자 새 값을 붙여넣으면 끝이다.

> **유출됐다면**: 토큰은 사용자별이 아니라 **공유**다. 즉 폐기 목록도, 한 사람만 끊는 방법도 없다 — **전원 교체**가 유일한 대응이다. 그리고 토큰이 유출됐다는 것은 그 시점까지 `/admin/scripts/code`로 임의 파일이 쓰였을 수 있다는 뜻이므로, 교체와 함께 `mappers/`·`<workspace>/scripts/`·`auto_update/`의 변경 이력을 확인하라.
> **로그아웃 버튼은 없다.** 특정 브라우저에서 토큰을 지우려면 그 브라우저 개발자도구에서 `localStorage.removeItem('assy.adminToken')`.

### 1-5. 사내 프록시 — 내부 통지가 밖으로 나가는 함정 (2026-07-30 실제 장애)

#### 증상에서 시작하기 — 어느 항으로 갈 것인가

| 증상 | 뜻 | 가는 곳 |
|---|---|---|
| 워커가 `POST /internal/events/broadcast`에 **403**을 반복. 재기동해도 그대로. 토큰을 맞춰도 안 고쳐짐 | 요청이 프록시로 나갔다 | **A**(판별) → B(원인) |
| 게이트가 **없는** `GET /health`까지 403 | 우리가 답한 게 아니다 | **A** |
| 워커 로그에 `admin-gate=no` | 앞단이 거부했다 | **A** |
| **수집 스크립트**가 사내 API에서 403 | 스케줄러의 프록시 정책 | **C-2** — 환경변수를 만지기 **전에** 여기부터 |
| 프록시 변수를 지웠더니 오히려 프록시를 탄다 | 환경이 비면 **레지스트리**가 조회된다 | **C-3** |
| 그리드는 멀쩡한데 교정이 실시간으로 안 퍼진다 | 통지가 죽었다 | **A**. 아니면 토큰 쪽 → §1-4-D |
| 개발 장비에서는 재현이 안 된다 | 그 장비에 프록시가 없다 | **B** |

#### A. 판별 (1분)

프록시를 끄고 같은 요청을 보내 본다:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" --noproxy "*" http://127.0.0.1:8080/health
```

`--noproxy`를 붙였을 때만 200이면 확정이다.

> ⚠️ **PowerShell의 `curl`은 `Invoke-WebRequest`의 별칭이고 그쪽도 시스템 프록시를 탄다** — 반드시 `curl.exe`로 불러야 한다. 이걸 몰라서 진단 자체가 오염된 적이 있다.
> ⚠️ 이 우회는 **그 명령 하나에만** 붙이는 것이다. 환경변수로 승격시키지 마라(→ C-3).

**기동 로그가 미리 말해 준다.** 데몬 3종은 기동 시 `/health`를 한 번 찔러 보고 프록시 환경을 함께 찍는다:

```
[internal-events] http://127.0.0.1:8080/health -> 200, direct (proxy bypassed). proxy-env=none
```

🔴 **이 줄을 읽는 규칙은 상태코드가 아니라 응답 본문이다.** 판정은 세 갈래이고, 각각 **다른 조치**로 간다:

| 로그 레벨 | 줄의 모양 | 뜻 | 조치 |
|---|---|---|---|
| `INFO` | `-> 200, direct (proxy bypassed)` | 웹서버가 우리에게 직접 답했다 | 없음 (정상) |
| `INFO` | `not reachable yet (ConnectionError)` | 아직 아무도 안 듣는다 | **없음** — 런처가 API와 워커를 몇 초 간격으로 띄우고 uvicorn의 bind가 더 느리다. 기동마다 뜨는 경고는 아무도 안 읽는다 |
| `WARNING` | `-> 503, answered by THIS application reporting status='unhealthy'` | **앱이 살아 있고 스스로 아프다고 말한다** | 프록시가 아니다. 같은 줄의 `Problems:` 목록과 `GET /health` 본문을 본다 |
| `ERROR` | `-> <상태>. /health carries NO admin gate …` | 게이트가 없는 경로에 **우리가 아닌 무언가**가 답했다 | **§1-5** — 그 포트를 소유한 프로세스와 줄의 `answered by '<이름>'` |

⚠️ **`WARNING`과 `ERROR`를 상태코드로 가르려 하지 마라.** `/health`는 체크가 하나라도 실패하면 **설계상 503**을 돌려준다(`health.HTTP_UNHEALTHY`). 판정은 본문이 우리 헬스 모양인가(`status` + dict `checks`가 **함께** 있는가 — `internal_event_client.own_health_payload`)이고, 프록시·필터의 에러 페이지는 HTML이거나 다른 모양의 JSON이라 그 둘을 동시에 만족시킬 수 없다. 이 구분이 없던 시절 **2026-07-31에 중복 런처가 원인인 인시던트에서 워커 두 개가 프록시 장문을 찍어 진단을 오도**했다.

#### B. 원인 — `<local>`은 **점이 있는** 주소를 우회해 주지 않는다

**우리 코드가 아니라 프록시였다.** `requests`는 기본값이 `trust_env=True`라 `HTTP_PROXY`/`http_proxy` 환경변수와 **Windows 프록시 레지스트리**를 읽는다. 여기에 함정이 하나 더 있다 — 레지스트리 `ProxyOverride`의 **`<local>` 토큰은 점(`.`)이 없는 호스트명만 우회 대상으로 친다.** 즉:

| 주소 | `<local>`이 우회해 주나 |
|---|---|
| `localhost` | ✅ 우회 (점이 없다) |
| **`127.0.0.1`** | ❌ **우회 안 함 (점이 있다)** |

우리 워커의 `API_BASE_URL` 기본값이 `http://127.0.0.1:8080`이므로, **자기 자신에게 보내는 통지가 사내 프록시로 나갔고** 프록시는 사설 주소로의 중계를 403으로 거절했다.

**모든 증상이 이것으로 설명된다:** 401이 아니라 403인 것(우리 게이트는 헤더가 없으면 401을 낸다), 게이트가 아예 없는 `GET /health`까지 403인 것, 재기동 면역인 것, 그리고 **프록시가 없는 개발 장비에서는 재현이 안 되는 것**.

#### C. 조치 — 층위가 둘이고, **환경변수는 그중 어느 쪽도 아니다**

**C-1. 우리 코드의 내부 홉 (완료 — 2026-07-30).** 프로세스 간 loopback 호출은 **프록시 설정을 절대 참조하지 않는다.**

- 워커 `run_watcher`·`chain_ingestion_worker`(⚰️ **[2026-08-14 `2ec78b9`] `graph_sync_worker`는 스택에서 빠졌다** · **목록 옆에 수를 적지 않는다**)는 세션을 직접 만들지 않고 **`server/internal_event_client.internal_event_session()`** 하나에서 받는다(`trust_env=False`). 발신자마다 따로 고치다 같은 결함이 세 번 재발한 이력이 있어, **세션을 직접 만드는 발신자가 생기면 테스트가 실패**하도록 막아 두었다.
- ⚰️ **[2026-08-14] 종전 여기에 「웹서버 → GraphSync 워커(`/api/graph/sync` → `127.0.0.1:8090`)의 `httpx`도 `trust_env=False`」 항목이 있었다** — 그 홉의 대상이 은퇴했고 라우트는 410을 답한다. **규율 자체는 남는다**: 새 loopback 홉이 생기면 같은 처방을 붙일 것.
- 범위는 **우리 세션 객체 하나**다. `urllib`을 쓰는 수집 스크립트에는 닿지 않는다 — 그쪽은 C-2가 따로 맡는다.

**C-2. 수집 스크립트 — 스케줄러가 자기 프로세스에서 정한다 (2026-07-30 `4aae627`).** 수집 스크립트는 운영자가 쓰고 스케줄러가 `exec`로 돌리는 코드라 각자 프록시를 다룰 수 없다. 그래서 **스케줄러(`run_auto_update.py`)가 기동 시 자기 프로세스의 프록시 정책을 확정한다** — 셸에 무엇이 들어 있든 상관없이.

| 노브 | 파일 | 기본값 | 뜻 |
|---|---|---|---|
| `bypass_proxy` | `server/config/auto_update_control.json` | `true` (직결) | 수집 스크립트가 프록시를 우회한다. 이 배포의 수집 대상이 **사내 인트라넷**이고, 프록시를 경유하면 403이다 |

- 🔴 **수집 스크립트가 403을 받으면 환경변수를 만지기 전에 이 값을 먼저 본다.** 사외 호스트를 치는 스크립트가 생겨 프록시가 필요해졌다면 `false`.
- 어느 쪽인지 기동 로그가 말한다 — `[proxy] 수집 스크립트는 직결로 돕니다(no_proxy=*). 제거한 변수: …` 또는 `[proxy] bypass_proxy=false - 수집 스크립트가 환경의 프록시 설정을 그대로 씁니다.`
- 값이 boolean이 아니거나 파일을 못 읽으면 **기본값(직결)으로 진행**하고 `WARNING`을 찍는다. 조용히 반대로 도는 쪽이 더 나쁘기 때문이다.
- ⚠️ **구현은 「프록시 변수를 지운다」가 아니다.** 환경이 비면 `urllib`이 **레지스트리를 조회**해 사내 프록시가 되살아난다(아래 C-3의 바로 그 성질). 그래서 `*_proxy` 계열을 전부 걷어낸 뒤 `no_proxy=*` **하나를 남겨** dict를 비지 않게 만든다. 이 함정은 `auto_update_control.json.sample`에도 적혀 있다.
- 아래 C-3의 사고와 **효과는 같고 범위가 다르다.** 사고는 그것을 런처 셸의 환경변수로 걸어 **트리 전체와 모든 사용자 스크립트**에 퍼뜨렸고, 이것은 **스케줄러 프로세스 하나** 안에서 끝난다.

**C-3. 🔴 `NO_PROXY`는 답이 아니다. 세우지 마라.** (2026-07-30 철회. 종전 이 자리에 `$env:NO_PROXY = "127.0.0.1,localhost"`가 **권장**으로 적혀 있었고, **그 권장이 자동 업데이트를 죽였다.**)

무슨 일이 일어나는지 — 이름과 정반대다. **`NO_PROXY`를 세우면 그 프로세스 트리의 모든 요청이 프록시를 안 타게 된다**(loopback뿐 아니라 **사내 API로 나가는 것도**).

- `urllib.request.getproxies()`는 `getproxies_environment() or getproxies_registry()`, 즉 **`or`**다.
- `getproxies_environment()`는 **이름이 `_proxy`로 끝나는 변수를 전부** 긁어모으는데, `no_proxy`도 `_proxy`로 끝난다.
- 그래서 `NO_PROXY` **하나만** 세워도 환경 dict가 비지 않게 되고, `or`가 단락되어 **Windows 프록시 레지스트리는 아예 조회되지 않는다.** 결과 dict에 `http`/`https` 항목이 없으니 모든 요청이 직결로 나간다.

실측(2026-07-30, conda `assy_manager`):

```
변수 없음   → {}
NO_PROXY만  → {'no': '127.0.0.1,localhost'}
```

**왜 이게 사고가 되나:** 런처(`run_decoupled_app.py`)는 자식 환경을 `os.environ.copy()`로 만든다. 그래서 런처 셸에 세운 `NO_PROXY`가 **스케줄러가 돌리는 사용자 스크립트 전부**에 상속됐고, 그 스크립트들은 `urllib.request.urlopen`으로 **사내 API**를 부르는데 그쪽은 프록시가 선택이 아니다. 전부 403을 받기 시작했다(같은 스크립트를 그 환경 밖에서 돌리면 정상 동작하는 것으로 확인).

> **일반 규칙 — 프록시 우회를 프로세스 전역 환경변수로 하지 마라.** 그것은 트리의 모든 자식과 모든 사용자 스크립트에 닿는다. 우회는 **그 호출을 하는 클라이언트 객체**(C-1)나 **그 스크립트를 돌리는 프로세스**(C-2)에 붙인다. 손으로 진단할 때는 **그 명령 하나에만** 붙인다(A의 `curl.exe --noproxy "*"`).

**C-4. 소스의 안내도 이제 같은 말을 한다 (2026-07-30 `98956fd`).** 예전에는 `internal_event_client.check_api_reachable()`의 ERROR 문구가 *"NO_PROXY=127.0.0.1,localhost 를 설정하고"*라고 말해 이 문서와 **정반대**였다. 지금 그 줄은 `[금지] NO_PROXY 를 설정하지 마세요`로 바뀌었고, 한 가지를 더 말한다 — 그 세션은 이미 `trust_env=False`라 프록시 환경변수를 보지 않으므로, **`ERROR` 줄이 떴다면 그것은 환경변수 문제가 아니라 포트 앞단(리버스 프록시·필터)의 문제다.** 확인 대상은 그 포트를 소유한 프로세스와 로그의 `answered by '<이름>'` 값이다.

🔴 **그 `ERROR`가 뜨는 조건은 「200이 아니다」가 아니다.** 한때 그랬고, 그래서 **스택이 그냥 아플 때마다**(체크 하나만 실패해도 `/health`는 503이다) 이 문단으로 운영자를 보냈다 — 2026-07-31 인시던트에서 실제 원인은 중복 런처였는데 워커 두 개가 이 프록시 장문을 찍었다. 지금은 응답 **본문**이 우리 헬스 모양이면(`status` + dict `checks`) **`WARNING`으로 갈라져 "이 애플리케이션이 답했고 스스로 unhealthy라고 말한다"**로 나오고, 이 문단(§1-5)이 아니라 **`/health` 본문의 `problems[]`**로 간다. 이 문단은 **본문이 우리 것이 아닐 때만** 해당한다.

**아직 정리되지 않은 자체 도구가 있다면**, 환경변수가 아니라 **그 도구의 HTTP 클라이언트**를 [PRIMITIVES §6 `internal_event_session()`](../architecture/PRIMITIVES.md) 형태로 고친다.

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
| ⚰️ ~~**온톨로지 그래프**~~ | `ontology_mapping.json` | **[2026-08-14] 소비자 0** — 읽는 워커도 라우트도 없다(고쳐도 아무 일도 안 일어난다) |

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
| ⚰️ ~~그래프 워커~~ | ~~127.0.0.1:8090~~ | ~~127.0.0.1:8091~~ — **[2026-08-14] 아무도 바인드하지 않는다**(기동 배너도 삭제) |

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

### 5.2 테스트 스위트는 실제 DB에 닿지 못한다 (2026-07-31, #16ⓐ 완결)

같은 종류의 사고가 워처가 아니라 **pytest**로 한 번 일어났다 — 스위트를 돌린 것만으로 운영 `assy_manager`에 빈 테이블이 생겼다. 방어가 `server/tests/conftest.py`의 `DATABASE_URL` 핀 하나뿐이었고, **핀은 테스트 트리가 하는 일**이라 지우면 방어도 사라졌기 때문이다.

지금 거절은 **운영 코드**(`server/db_safety.py`)에 있고, pytest 프로세스 안에서만 무장한다.

- 통과 조건은 **허용목록**이다 — **sqlite**이거나, **`ASSY_TEST_DATABASE_URL`이 명시적으로 지목한 URL**. 그 외에는 운영 이름이 아니어도 거절한다(차단목록은 운영 DB가 둘이 되는 날 열린다).
- `ASSY_TEST_DATABASE_URL`에 **운영 DB를 적어도 거절**된다. 선언한다고 테스트 DB가 되지는 않는다.
- 거절 층이 셋이다 — 공유 엔진은 **소켓이 열리기 전에**(`do_connect`), 테스트가 스스로 만든 엔진은 첫 쿼리 전에(`Engine` 클래스 훅), 부팅 DDL은 **연결을 아예 열지 않고**(순수 판정) 거절한다.
- **운영에서는 전부 무동작**이다. `create_all`은 여전히 무가드이고, DB 불통이면 웹서버는 종전대로 시끄럽게 부팅에 실패해야 한다.

격리 PostgreSQL(`assy_qa`)에 대고 스위트를 돌리려면 지목이 필요하다.

```bash
# 이 선언이 없으면 sqlite가 아닌 대상은 전부 거절된다
ASSY_TEST_DATABASE_URL=postgresql://postgres:...@localhost:5432/assy_qa \
  conda run -n assy_manager python -m pytest server/tests contracts -q
```

---

## 6. 순서 요약

1. PostgreSQL 준비 → `DATABASE_URL` 설정
2. `server/config/*.sample` → 확장자 떼고 복사 (**기존 환경이면** `install_product_tables.py --apply`로 제품 소유 테이블만 병합 — §1-2)
3. **`table_config.json`에 우리 현장 테이블 선언** (여기가 대부분의 작업)
   - 🔴 **DT/Core 프레임 체인의 "잡" 컬럼 이름을 현장 철자(예: `dt_job_id`)로 여기서 바꾼다면**, 그 리네임을 **체인 리졸버가 모르는 파일 둘**과 같은 변경에서 손으로 맞춰라 — 안 맞추면 조용히 안 따라온다(2026-08-11, `5b09d69`): `server/migrations/add_dt_log_trigger_indexes.sql`의 `CREATE INDEX ... (dt_job)` 두 문(재실행하지 않으면 새 컬럼명 위에 인덱스가 없다), `server/config/enrichment_rules.json`의 자유 SQL 다섯 곳(`WHERE dt_job = :dt_job` — 리졸버 밖이라 옛 이름을 계속 찾고 매번 0행). 절차 정본은 [guide/DT_CORE_FRAME_CHAINS_GUIDE §1-bis](./DT_CORE_FRAME_CHAINS_GUIDE.md#1-bis-잡-컬럼-이름-2026-08-11).
4. `server/ingestion_workspace/<테이블>/` 디렉터리 생성
5. 켤 기능의 config에서 `table`/`columns`를 우리 이름으로 맞춤 (§2)
6. 맵을 쓴다면 `wafer_map_metadata` 등록 (§3)
7. **`ASSY_ADMIN_TOKEN` 설정** (§1-4) — 안 하면 어드민의 코드 저장·즉시 실행이 503으로 막힌다
   - ⚠️ **먼저** `grep -c X-Admin-Token client2/dist/assets/admin-*.js`가 1 이상인지 확인. 0이면 번들부터 다시 빌드·커밋한다(§1-4) — 아니면 토큰을 켜는 순간 어드민 페이지가 잠긴다
8. **기동 전에 한 번 물어본다** (2026-08-05 신설 · `f6406b1`):
   ```bash
   conda run -n assy_manager python run_decoupled_app.py --preflight-only
   ```
   **아무것도 띄우지 않고** API 포트(8080 — ⚠️ **[2026-08-14] 종전 「포트 두 개(8080·8090)」는 그래프 워커 은퇴로 거짓이 됐습니다**)와 **스키마 드리프트**를 점검한 뒤 종료합니다. 배포·재기동 직전이 이 명령의 자리입니다 — 「마이그레이션을 돌렸던가」를 **화면이 500을 내기 전에** 묻는 유일한 자리이기 때문입니다.
   - 🔴 **종료 코드는 포트만 봅니다**(비었으면 0, 물려 있으면 1). **드리프트는 종료 코드를 바꾸지 않습니다** — 무인 재기동이 컬럼 하나로 스택 전체를 계속 죽여 놓지 않게 하려는 의도입니다. 그러니 **배너를 읽으십시오.**
   - 배너가 `TABLE-DOWN`을 말하면 그 테이블은 **통째로 죽습니다**(그 컬럼을 읽지 않는 코드까지 — SQLAlchemy가 매핑된 컬럼 전부를 SELECT·INSERT에 싣습니다). 평결이 **어느 마이그레이션을 돌려라**까지 말하므로 그대로 실행하십시오.
   - `MISSING-TABLE`은 대개 웹서버를 한 번 띄우면(`create_all`) 해결됩니다. `INFO`(DB에만 있는 컬럼)는 **무해**합니다 — 되돌린 배포의 잔여물이며 [ROLLBACK_PROCEDURE §5](ROLLBACK_PROCEDURE.md)가 그 처리를 다룹니다.
   - 🔴 **`SELF-HEALING`은 「할 일 없음」이고, 마이그레이션을 쓰지 마십시오** (2026-08-13 `eb700e5` 신설). config로 선언한 **동적 테이블**의 컬럼은 서버 프로세스가 뜰 때 `models.sync_dynamic_tables_schema`가 **스스로 추가**합니다 — 이 점검은 그 프로세스들보다 **먼저** 돌기 때문에 없다고 답할 뿐입니다. 종전에는 이것도 「이 테이블을 쓰는 모든 화면이 실패한다」로 나갔고, 제품 소유자가 그 말을 믿고 조치·재기동한 뒤 **항목이 사라진 것을 발견**했습니다.
     - ⚠️ **그래도 인쇄는 됩니다 — 그리고 «두 번째로» 보이면 이야기가 달라집니다.** 전체 재기동 뒤에도 같은 줄이 남으면 그 `ALTER`가 실제로 실패하고 있는 것이고 그때는 정말로 테이블이 죽어 있습니다. 로그에서 `[Schema Sync] Failed to add column`을 찾고, 배너가 함께 찍어 준 수동 `ALTER` 문을 그대로 실행하십시오.
     - **빨간 블록의 헤드라인 수에는 안 들어갑니다.** 드리프트가 이것뿐이면 빨간 블록이 **아예 열리지 않습니다** — 조용해진 것은 이 한 조건뿐이고, 그 밖의 모든 계급(이 모듈이 아직 볼 줄 모르는 것 포함)은 **구성상 시끄럽게** 남습니다.
8-bis. 🔴 **업무 키 UNIQUE 인덱스를 반영한다 — 2026-08-07 이후의 쓰기 경로는 이것을 전제로 한다** (`4738d84`+`528dfcb`, D3)
   ```bash
   conda run -n assy_manager python server/migrations/add_business_key_unique_index.py          # 사전점검(읽기 전용)
   conda run -n assy_manager python server/migrations/add_business_key_unique_index.py --apply
   ```
   **왜 배포 순서에 들어왔는가**: 집합 기반 쓰기 경로가 행마다 내던 신원 SELECT를 없애면서, 프로세스 간 경합 창이 **마이크로초에서 실측 2.4초로** 넓어졌다. 이 시스템에 프로세스 간 락은 없고(`pg_advisory` 0건) 데이터 테이블에 쓰는 장수 프로세스는 넷이다. 실제 프로세스 둘·1,000건 청크로 **한 업무 키에 두 행**이 재현됐다. 🔴 **성능 개선이 구멍을 만든 것이 아니라, 설계로 보호된 적 없는 경로에서 마지막 *우연한* 가드를 걷어낸 것이다** — 그래서 수리도 되돌리기가 아니라 **불변식을 DB에 새기는 것**이고, 인덱스는 **P3 이전 코드의 같은 구멍도 함께 닫는다**.
   - ⚠️ **8의 `--preflight-only`는 이것을 못 잡는다** — 드리프트 점검이 보는 것은 **컬럼**이고 인덱스가 아니다(`server/schema_drift.py`에 인덱스 검사 0건). 「사전점검이 초록이었다」는 이 인덱스에 대해 아무 말도 하지 않는다.
   - **중복이 하나라도 있으면 `CREATE UNIQUE INDEX`가 실패한다.** 사전점검이 테이블별로 먼저 세고, 거부된 테이블은 **이름·중복 키 수·잉여 행 수·예시**와 함께 보고되며 **나머지 테이블은 계속 진행**한다. 절차·함정은 [POSTGRES_OPERATIONS §3.1](POSTGRES_OPERATIONS_GUIDE.md).
   - **키가 아예 안 조립된 행**은 다른 문제이고 다른 도구다 — `server/scripts/check_missing_business_key.py`(읽기 전용, 같은 절).
8-ter. 🔴 **감사 이력 인덱스 세 종을 반영한다 — 없으면 오늘(2026-08-11)의 성능 수리 전부가 무효다** (`dab9152`+`2630790`)
   ```bash
   psql "$DATABASE_URL" -f server/migrations/add_audit_history_keyset_indexes.sql   # idx_audit_row_history, idx_audit_cell_history
   psql "$DATABASE_URL" -f server/migrations/add_audit_recent_groups_index.sql      # idx_audit_recent_groups
   ```
   **왜 배포 순서에 들어왔는가**: 이 두 파일이 만드는 **인덱스 셋**이 없으면, `audit_history_config.json`의 상한(`recent_max_scan_rows` 등)을 아무리 낮춰도 각 청크는 여전히 **순차 스캔 + 디스크 정렬**이다(실측 2,900,000행 픽스처에서 청크 하나 3.6초 · 300,019행짜리 감사 이력 하나 121.6ms). 즉 **config만 배포하고 인덱스를 건너뛴 프로덕션 박스는 상한이 낮아진 것 말고는 아무것도 빨라지지 않는다** — 코드가 바뀌었다는 사실이 성능이 바뀌었다는 증거가 아니다.
   - `models.py`(`AuditLog.__table_args__`)에 이미 선언돼 있어 **신규** 설치는 `create_all`이 자동으로 만든다. `create_all`은 **기존** 테이블에 인덱스를 추가하지 않으므로(`idx_sources_by_source`와 같은 계급), 이미 떠 있는 프로덕션 DB는 이 단계가 유일한 반영 경로다.
   - `CONCURRENTLY`라 쓰기 락 없이 라이브 스택에 돌릴 수 있지만, **트랜잭션 블록 안에서 부를 수 없다** — `psql -f`(자동커밋)로 실행하고 래핑 `BEGIN`을 쓰지 말 것. 중단되면 `INVALID` 인덱스가 남아 쓰기 비용만 지불하고 아무 읽기도 못 받으므로, 각 파일 하단의 확인 SQL로 `indisvalid`를 재확인한다.
   - ⚠️ **8의 `--preflight-only`는 이것도 못 잡는다** — 드리프트 점검은 컬럼만 보고 인덱스는 보지 않는다(위 8-bis와 같은 사각).
   - 예상 소요·크기: `idx_audit_recent_groups` 166 MB(2,900,000행 기준, 4.2초) · `idx_audit_row_history`+`idx_audit_cell_history` 합계 실측 두 벌(운영 규모 210,196행에서 19+20 MB · 1,131,008행 픽스처에서 91+101 MB, ~170-195 B/행) — 프로덕션 `audit_logs` 행 수에 선형 비례한다.
8-quater. 🔴 **인제션 원장에 tier-1 열쇠를 반영한다 — 안 돌리면 원장이 «읽기부터» 죽는다** (2026-08-13)
   ```bash
   psql "$DATABASE_URL" -f server/migrations/add_ingestion_ledger_path_stat.sql   # file_mtime, file_size, idx_fic_path_stat
   ```
   **왜 배포 순서에 들어왔는가**: 위 8-bis·8-ter는 **인덱스만** 만드는 단계라 건너뛰면 「느려질 뿐」이지만, 이것은 **컬럼을 둘 추가**한다. `models.FileIngestionCheckpoint`가 그 컬럼들을 선언하므로 SQLAlchemy는 그 테이블의 **모든 SELECT·INSERT에 이름을 싣는다** — 즉 마이그레이션 없이 코드만 배포하면 `file_ingestion_checkpoints`는 **통째로 죽는다**(이 박스에서 실측: 전체 엔티티 SELECT가 `UndefinedColumn: file_ingestion_checkpoints.file_mtime`). 배너의 `TABLE-DOWN` 계급이 정확히 이것이다.
   - **워처는 죽지 않는다 — 그래서 더 나쁘다.** 원장 호출 세 자리(dedup 조회·체크포인트 계획·tier-1 조회)가 각자 예외를 잡고 경고를 남긴 뒤 계속 가므로, 인제션은 **체크포인트와 dedup이 통째로 꺼진 채** 살아남는다. `ingestion_settings.json`에 `archive_processed_files: false`가 함께 들어가면 **모든 파일이 매 스윕 재적재**된다.
   - ✅ **8의 `--preflight-only`가 이것은 잡는다** — 드리프트 점검이 보는 것이 **컬럼**이기 때문이다(8-bis·8-ter의 인덱스 사각과 반대). 배너를 읽고 이 명령을 실행하면 된다.
   - **신규** 설치는 `create_all`이 만들므로 이 단계가 필요 없다. `ALTER TABLE ADD COLUMN ... NULL`(기본값 없음)은 PG 11+에서 **메타데이터만** 바꾸므로 테이블 크기와 무관하게 즉시 끝나고, 인덱스는 `CONCURRENTLY`라 쓰기 락이 없다(트랜잭션 블록 밖에서 — `psql -f`).
   - 되돌리기: `server/migrations/add_ingestion_ledger_path_stat_reverse.sql`. 🔴 **되돌리기 전에 `archive_processed_files`를 `true`로 먼저 돌려놓고 워처를 재기동하라** — 컬럼 없이 「파일도 안 옮기는」 조합이 유일하게 아픈 순서다.
   - 크기·비용 실측(`assy_qa`, 300,063행): 인덱스 50MB(**행당 ~175B**, 경로 46자 기준) · 조회 `Index Scan` 8 buffers **0.096ms**. 원장은 **처리한 파일 수**만큼만 자란다(데이터 행 수와 무관).
8-quinquies. 🔴 **동적 테이블 인덱스를 «선언»에 맞춘다 — 안 돌리면 기존 DB는 한 개도 안 바뀐다** (2026-08-14 F6, 판정 `R-2026-08-14-B`)
   ```bash
   conda run -n assy_manager python server/migrations/align_indexes_to_declarations.py            # 사전점검(읽기 전용, PostgreSQL이 강제)
   conda run -n assy_manager python server/migrations/align_indexes_to_declarations.py --apply
   ```
   **왜 배포 순서에 들어왔는가**: 이 라운드에서 `models.init_dynamic_models`가 인덱스를 하드코딩 목록이 아니라 **`table_config.json`의 선언**에서 파생하도록 바뀌었다(`idx_<표>_declared_key`). 그런데 `create_all`은 **이미 있는 테이블에 인덱스를 추가하지도, 어떤 인덱스를 지우지도 않는다** — 그래서 빌더 변경은 **신규 테이블에만** 닿는다. 이 단계가 기존 DB의 유일한 반영 경로다. 정책·표별 근거는 [architecture/INDEX_POLICY](../architecture/INDEX_POLICY.md).
   - **무엇을 하는가**: ① 표마다 선언 키 인덱스를 **만든다**(`map_key_columns` → 없으면 `composite_key_source` → 없으면 단일 컬럼 `business_key`) ② 스캔 0으로 실측된 `ix_<표>_created_at`과 `idx_<표>_bk`를 **은퇴시킨다**.
   - 🔴 **순비용이 «음수»다.** `assy_qa` 실측(40,546행 INSERT, `EXPLAIN (ANALYZE, WAL)` 문장 단위): 2칸 키 형태에서 **−80.9 B/행 WAL(−10.9%)·insert 시간 −11.8%**, config에서 가장 넓은 6칸 키 형태에서도 **−28.6 B/행(−3.8%)**. 인덱스를 하나 더 얹는 값(+78.9 ~ +131.2 B/행)보다 은퇴 둘이 크다.
   - **모든 동작이 대상 DB에서 다시 증명된다.** 한 DB의 측정은 다른 DB의 사실이 아니다 — 증명에 실패한 항목은 **이름과 이유를 찍고 거절**되며 나머지는 계속 진행한다. 실제로 `assy_manager`에서 4건, `assy_qa`에서 7건이 「이 표의 인덱스가 전부 스캔 0 = 카운터가 아무것도 관측 못 함」으로 거절됐다(신선 복원·통계 리셋 방어). **거절이 있으면 종료 코드 1이다 — 실패가 아니라 「이 박스에서는 그 항목이 아직 증명 안 됐다」는 뜻**이니 출력을 읽을 것.
   - `CREATE`/`DROP` 모두 `CONCURRENTLY`라 라이브 스택에 쓰기 락 없이 돌지만 **트랜잭션 블록 안에서 못 돈다**(스크립트가 AUTOCOMMIT 연결을 따로 연다). 중단되면 `INVALID` 인덱스가 남고 스크립트가 그것을 **이름과 함께 실패로 보고**한다.
   - 되돌리기: 같은 스크립트의 `--reverse --apply`. 저장된 목록이 아니라 **같은 config·같은 카탈로그에서 다시 계산**하므로 정방향과 어긋날 수 없다. `assy_qa`에서 정방향 155→145, 역방향 145→155로 **표별 개수까지 원상 복귀**를 실측했다.
   - ⚠️ **8의 `--preflight-only`는 이것도 못 잡는다** — 드리프트 점검은 컬럼만 보고 인덱스는 보지 않는다(8-bis·8-ter와 같은 사각).
   - ⚠️ **`server/scripts/setup_bonding_plan_indexes.py`·`setup_transfer_plan_indexes.py`가 만드는 인덱스 둘은 선언 키와 컬럼이 «같고 이름만 다르다».** 마이그레이션은 이름이 아니라 컬럼으로 멱등이라 **중복을 만들지 않고 건너뛴다**. 이름 통일은 저 스크립트들을 먼저 정리해야 한다 → [INDEX_POLICY §6.1](../architecture/INDEX_POLICY.md).
8-quinquies. 🔴 **선언만 고친 컬럼 타입은 물리 DB에 «절대» 도달하지 않는다 — `dt_inventory.dt_lot`/`dt_slot`** (2026-08-13 `8bdc136`)
   ```bash
   psql "$DATABASE_URL" -f server/migrations/alter_dt_inventory_lot_slot_to_text.sql
   ```
   **왜 이것이 손으로 돌아야 하는 단계인가**: `table_config.json`의 `column_types`를 `"number" → "string"`으로 고쳐도 **물리 컬럼은 `double precision`으로 남는다.** `sync_dynamic_tables_schema`는 **`ALTER TABLE … ADD COLUMN`만** 발행하고 **타입을 바꾸는 문장은 이 저장소 어디에도 없다.** 그래서 선언 수정은 **언제나 절반짜리 수리**이고, 나머지 절반이 이 파일이다. 규칙의 정본은 [SCHEMA_CANON R1](../architecture/SCHEMA_CANON.md)(식별자는 절대 수치형이 아니다 — lot id `CL_2601_005_A5`는 `double precision`에 들어가지 않는다).
   - **이 박스 실측**: `assy_manager`는 `double precision`·251행·**0 filled**(변환할 것도 잃을 것도 없다), `assy_qa`는 이미 `character varying`. 스윕 전체에서 수치형인 lot/slot 컬럼은 **그 둘뿐**이었다 — ⚠️ **운영의 수는 다르다. 돌리기 전에 그쪽에서 다시 세라.**
   - **되돌리기**: `..._reverse.sql`. 🔴 **역방향은 대칭이 아니다** — 텍스트→수치는 값을 **바꾼다**(`DT-2601-001`은 수가 아니고 슬롯 `01`은 `1`이 되어 돌아오지 않는다). 그래서 변환 불가값이 하나라도 있으면 **거절하고, 그 거절 자체가 답이다**(그 컬럼은 애초에 수치형일 수 없었다는 뜻). 전부 변환 가능해도 **선행 0은 따로 경고**한다.
   - **확인은 작업한 스크립트가 아니라 검출기로**: `python server/scripts/audit_schema_canon.py`의 `declared_type_disagrees_with_catalogue`가 0이 되는지 본다.
   - ⚠️ **`declared_column_absent_from_catalogue`가 남는 것은 다른 이야기다** — 선언은 있고 컬럼이 없는 상태는 **다음 기동에 스스로 풀린다**(ADD는 동기화가 *하는* 일이다). 풀리지 않는 것은 **타입 불일치**뿐이다.
8-sexies. **void(보이드) 스키마 — 인덱스는 «테이블이 생긴 다음»이다** (2026-08-13 `346aa88`)
   ```bash
   psql "$DATABASE_URL" -f server/migrations/add_void_schema_indexes.sql
   ```
   순서 전체(선언 손복사 → 리로드/재기동으로 테이블 생성 → **이 인덱스** → 파서 shim 둘 → SAT 파일)는 [process/OPERATOR_RUNBOOK §4](../process/OPERATOR_RUNBOOK.md)가 정본이다. 🔴 **이 파일은 3단계이지 1단계가 아니다** — 선언이 `server/config/table_config.json`(gitignore)에 손복사되고 리로드가 물리 테이블을 만들기 전까지는 붙일 대상이 없다.
   - 🔴 **`idx_void_obs_area`는 «식» 인덱스다** — `pi() * radius_x * radius_y`. **면적 컬럼은 없고 앞으로도 없어야 한다**(합불 임계가 레시피 파라미터라 굳힌 판정은 이력을 다시 판정할 수 없게 만든다). 근거는 [architecture/data_model §1.2-bis](../architecture/data_model.md).
   - 되돌리기: `add_void_schema_indexes_reverse.sql`.
8-septies. **정준 원장 테이블 — 추가 전용이고 급하지 않다. 🔴 스크립트는 «둘»이다. 단, `tzdata`가 먼저다** (2026-08-13 `f896020`+`bee1aeb`+`0198e7e`)
   ```bash
   conda run -n assy_manager python server/migrations/add_ledger_events.py            # --report 로 상태만 보기
   conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py   # --report / --reverse
   ```
   - **성질**: 추가 전용·멱등. DROP 없음, 기존 것의 ALTER 없음, 기존 행을 건드리는 문장 없음 — **새 테이블 둘**(`ledger_events`·`ledger_translator_cursor`)만 만든다. **안 돌려도 아무것도 안 깨진다**(부팅 시 `server/ledger`를 import하는 프로세스가 없다). 다만 그 상태에서 `GET /api/ledger/trace`는 **503 + 관계 이름**으로 답한다.
   - 🔴 **두 번째 스크립트(`0198e7e`)는 커서 표에 `refusal_reasons JSONB` 하나를 붙인다**(열둘 → 열셋) — 거절 사유가 그전까지 **백필 프로세스의 메모리에만** 있어서 **이 DB를 어떻게 읽어도 사유 하나를 낼 수 없었다.** `ALTER TABLE … ADD COLUMN <nullable, DEFAULT 없음>` 한 문장이라 PG 11+에서 **카탈로그만** 바꾸고 힙을 안 건드린다(표 크기와 무관). 게이트가 `pg_attribute`라 **재실행은 DDL도 잠금도 0**이고, **어떤 표의 행도 읽거나 쓰지 않는다.**
     - 🔴 **이것을 «건너뛰어도» 서버는 500이 아니다 — 양방향으로 방어돼 있다.** 쓰기 쪽은 `ledger.schema.ensure_schema`가 같은 문장을 **모든 백필 첫 단계**에 적용하고, 읽기 쪽 `GET /api/ledger/coverage`는 **카탈로그에 어느 컬럼이 있는지 먼저 묻고** 있는 것만 SELECT한다. 8의 `--preflight-only`가 잡는 계급(`file_ingestion_checkpoints`가 통째로 죽던 8-quater)과 **다른 이유가 이것**이다: 저쪽은 ORM이 컬럼 이름을 모든 문장에 실어서 표가 죽었고, 이쪽은 **읽는 쪽이 물어보고 쓰는 쪽이 스스로 고친다.** 이 스크립트는 **운영자의 진입점이자 감사 기록**이다.
     - 되돌리기: `--reverse`. **진짜 역방향이다** — 원자도, 커서 위치도, 집계도 잃지 않고 **내역만** 잃는다.
     - ⚠️ **기존 커서 행은 NULL을 얻고, 그 NULL이 `{}`와 다른 뜻이다** — 「이 행은 컬럼보다 오래됐고 그 `molecules_refused`는 영원히 분해될 수 없다」. `/coverage`가 그것을 **`refusals_unaccounted > 0`**(배포 이력, **결함 아님**)으로 보고한다. 읽는 법은 [guide/LEDGER_GUIDE §4.4·§4.6](./LEDGER_GUIDE.md).
   - 🔴 **`environment.yml`에 `tzdata`가 새로 들어왔다(2026-08-13).** 원장의 세상 시각 선언이 `Asia/Seoul`이고 `zoneinfo.ZoneInfo("Asia/Seoul")`은 **런타임에 IANA DB에서** 해석된다 — 선언이 `UTC`이던 동안에는 CPython이 tzdata 없이 답했으므로 **진짜로 새 의존성**이다. **없으면 폴백하지 않고 예외를 낸다**(조용히 UTC로 떨어지면 방금 고친 「모든 원자가 9시간 어긋나고 아무것도 항의하지 않는」 상태가 그대로 재현된다). 환경 갱신: `conda env update -f environment.yml`.
   - 🔴 **시간대 판정 «다음»에 돌려라.** 선언이 틀리면 백필된 원자 전부가 어긋나고, **어긋난 시각도 여전히 well-formed한 시각이라 어떤 가드도 알아채지 못한다.** 정정은 재백필이지 제자리 `UPDATE`가 아니다(해결기가 `occurred_at` 내림차순으로 순위를 매기므로 낡은 원자가 **구성상 정정본을 이긴다**).
9. 기동 → 서버 로그 첫 줄에서 `[admin-auth]`가 **WARNING/ERROR가 아닌지** 확인(`ERROR`면 토큰이 비-ASCII라 무시된 것) → `curl http://localhost:8080/health` 가 **JSON 200**인지 → `/api/transfer-plan/stages` 등으로 바인딩 상태 확인
   - ⚠️ 런처와 웹서버가 **각자** 드리프트 배너를 한 번씩 찍습니다(약 14 ms). 8을 건너뛰었어도 기동 로그에 남으니 거기서 읽으십시오.

### 6.1 기동 후 상시 감시

`GET /health`를 폴링하면 된다. **HTTP 코드만 봐도 된다** — 정상 200, 조치 필요 503. 어디가 문제인지는 본문 `problems[]`가 문장으로 담는다.

- 워커는 pid가 아니라 **진행 박동**으로 판정된다 — 살아 있는 채 멈춘 프로세스(`wedged`)를 잡기 위해서다. 상태값은 8종이고([backend §1.3](../architecture/backend.md)), 그중 **`stalled`는 따로 봐야 한다**: 박동은 신선한데 **claim한 작업이 300초간 무진행**인 경우로, "워커는 살아 있고 루프도 도는데 일이 안 나가는" 상태다.
- outbox 적체는 **크기가 아니라 나이**로 판정된다. 큰 파일 하나가 outbox 십만 행을 만드는 것은 정상이다.
- 자식 프로세스는 런처가 감시·재시작한다. **6번째 연속 실패에서 포기**하고 `/health`가 계속 503을 낸다 — 그때는 사람이 고쳐야 한다는 뜻이다.
- 🔴 **스키마 드리프트는 `/health`에 나오지 않는다 — 부팅 배너에만 있다**(2026-08-05). 폴링으로는 절대 안 잡히므로 **배포·재기동 때마다 §6의 8을 돌리는 것이 유일한 관측 지점**이다. 드리프트난 스택은 `/health`가 **정상 200**을 답하면서 그 테이블의 화면만 500을 낸다 — 실제로 2026-08-05 하루에 3건이 그렇게 나갔고 **전부 제품 소유자가 제품을 쓰다가 발견했다.**
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
