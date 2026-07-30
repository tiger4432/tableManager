# 데스크톱 셸 서버 주소 — 하드코딩 2곳 → 우선순위 해석 1곳

- **일자:** 2026-07-30
- **담당:** Client PM
- **대상:** `client/desktop_wrapper.py` (259줄 → 514줄)

---

## 1. 현상

데스크톱 셸이 붙을 서버가 소스에 박혀 있었고, **두 곳이 각자 만들면서 서로 달랐다.**

```python
api_url = f"http://127.0.0.1:8080/tables/{table_name}/upload"   # :149 (업로드)
url = "http://localhost:8080/?client=desktop"                    # :254 (페이지)
```

동시에 `client/client_settings.json`은 **정확히 맞는 형태를 이미 담고 있으면서 한 번도 읽히지 않았다.**

```json
{ "server_host": "127.0.0.1", "server_port": 8080, "current_user": "kk980" }
```

Grep 결과 `client_settings`·`json.load`·`ASSY_*` 참조가 셸 코드에 0건. 즉 다른 서버(예: 격리 스택 :8081, LAN 배포)에 붙이려면 **소스를 고쳐 exe를 다시 빌드**하는 것이 유일한 방법이었다.

곁딸린 결함 2건:
- `:255`가 `"Vite dev server not detected. Loading integrated FastAPI URL on port 8080."`을 **조건 없이** 출력했다 — Vite가 켜져 있어도 같은 문구가 나온다. 짝인 `is_port_open`(`:246`)은 **정의만 되고 한 번도 호출되지 않았다.** 살아 있는 것처럼 읽히는 죽은 코드.
- `:5`의 `NO_PROXY = "127.0.0.1,localhost"`는 루프백을 전제한다. 해석된 호스트가 LAN 주소면 이 목록이 그를 덮지 못하고, **프록시가 연결을 삼키면 "서버가 죽었다"와 똑같이 보인다.**

## 2. 근본 원인

주소를 **선언**으로 다루지 않고 **문자열 리터럴**로 다뤘다. 그래서 (a) 조립 지점이 둘로 갈라져 서로 다른 답을 냈고(`127.0.0.1` vs `localhost`), (b) 이미 존재하는 선언 파일이 소비자 없이 방치됐다.

## 3. 해결

### 3.1 조립 지점 1개 (`resolve_server_target` → `base_url`)

`base_url()`(:216)이 **주소를 URL 문자열로 만드는 유일한 자리**다. 소비자는 경로만 붙인다.

```python
def base_url(host, port):
    return f"http://{host}:{port}"

# HybridDesktopClient.__init__ (:280)
self.server_base = server_base
self.web_url = f"{server_base}/?client=desktop"

# _do_upload (:371)
api_url = f"{self.server_base}/tables/{table_name}/upload"
```

### 3.2 우선순위: `--server` > `ASSY_SERVER` > `client_settings.json` > `127.0.0.1:8080`

| 순위 | 근거 |
|---|---|
| `--server` 인자 | 한 번 다른 서버에 붙이는 일이 파일 편집을 요구해선 안 된다 |
| `ASSY_SERVER` 환경변수 | 배포 스크립트·바로가기. 빈 값은 미선언으로 취급 |
| `client_settings.json` | 기존 권위이자 사람이 편집하는 자리. 단 **git 추적 대상**이라 운영자 편집이 워킹트리를 더럽힌다 — 위 둘이 앞서는 이유 (주석에 명시) |
| 기본값 | 파일이 없거나 비면 **이전 하드코딩과 동일 동작**(무회귀) |

`run_decoupled_app.py`의 `ASSY_API_HOST`/`ASSY_API_PORT`는 **재사용하지 않았다** — 그쪽은 서버의 *바인드* 선언이고 `ASSY_API_HOST` 기본값 `0.0.0.0`은 클라이언트가 다이얼할 수 없는 주소다.

`--server`는 argparse가 아니라 손 스캔이다: `register_uri_scheme()`이 등록한 HKCU 핸들러가 클릭된 `assymanager://` URL을 **argv[1]로** 넘기고, argparse는 그 미지의 위치 인자에서 `exit(2)`한다.

### 3.3 잘못된 선언은 조용히 기본값으로 내려가지 않고 거절

`ServerTargetError` → stderr + `QMessageBox` + `exit 2`. 거절 대상: 파싱 불가 JSON · 비숫자/범위 밖 포트(**0 포함 — 미상 ≠ 0**) · 불리언 포트(`bool`은 `int` 하위형이라 명시 배제) · 빈/비문자열 `server_host` · JSON 루트가 객체 아님 · `https` 스킴(조용한 강등 금지) · 잘못된 `--server`/`ASSY_SERVER`.

**파일 부재·빈 파일·서버 키 미선언은 정상 설정**이며 조용히 기본값을 쓴다.

`QMessageBox`를 붙인 이유: `AssyManagerClient.spec`이 `console=False`라 **패키징된 exe에서는 stdout/stderr가 어디에도 도달하지 않는다.** 아무도 읽을 수 없는 거절은 조용한 실패와 같다. 거절 문구 자체는 ASCII로 고정했다 — 이 프로세스의 stdout은 `run_decoupled_app.py` 감시 하에서 cp949 파이프이고, 비ASCII `print`는 `UnicodeEncodeError`로 **거절을 트레이스백으로 바꿔버린다.**

### 3.4 시작 로그 1줄 (거짓말 삭제)

```
[Desktop Wrapper] Server target: http://127.0.0.1:8080 (source: client_settings.json)
```

`source`(`arg`/`env`/`client_settings.json`/`default`)가 있어야 운영자가 "내 편집이 무시됐다"를 알 수 있다. `is_port_open`과 거짓 Vite 문구는 삭제. `--print-target`은 해석·출력 후 종료하는 헬리스 점검 경로(GUI·HKCU 미접촉).

### 3.5 `NO_PROXY`

`extend_no_proxy()`(:227)가 해석된 호스트를 목록에 추가한다(멱등). **httpx 업로드 경로에는 유효하고 QtWebEngine에는 보장되지 않는다** — Windows Chromium은 프록시를 OS에서 읽는다. Qt측 레버 `QNetworkProxy.setApplicationProxy(NoProxy)`(:510)는 주석 처리 상태를 유지하되 "실수로 남은 죽은 줄"이 아니라 **문서화된 레버**로 주석에 명시했다.

## 4. 검증

GUI는 기동하지 않았다(사용자 지시). 세 층으로 채점.

| 층 | 방법 | 결과 |
|---|---|---|
| 단위 46건 | `resolve_server_target(argv=, env=, settings_path=)` 직접 호출 — 4순위 각각 · 2개 동시 설정으로 순서 증명 · 거절 13종 · 관용 입력 6종 · 구조 검사 7종 | **46 pass / 0 fail** |
| 프로세스 15건 | 실제 `__main__`을 `--print-target`으로 서브프로세스 실행(실 argv·실 env·실 파일) | **15 pass / 0 fail** |
| 변이 4건 | 결함을 되돌려 넣어 검증이 실제로 붉어지는지 | **4/4 사망** |

변이 검사 상세 — ① 우선순위 뒤집기(env를 arg보다 먼저) → 8건 red ② 잘못된 config를 조용히 기본값으로 → C1-C8 8건 red ③ 파일 부재를 거절로 → A4에서 즉사 ④ `base_url`을 하드코딩 복귀 → F1 red.

`pytest server/tests/` **1398 passed / 0 failed**(3분 44초, `conda run -n assy_manager`). 서버 코드는 건드리지 않았다.

**실행하지 못한 것:** 실제 원격 호스트로의 종단 연결(LAN 서버 없음)과 프록시 개입 시나리오. `?client=desktop`·`/tables/{t}/upload` 두 f-string은 `QMainWindow` 안이라 창 없이 실행할 수 없어 **정적 검사**로만 채점했다(H2-H5: 두 소비자가 `self.server_base`를 읽고 자체 주소를 갖지 않음, `http://` 조립 줄이 파일 전체에 1개).

## 5. 부작용 / 후속

- ⚠️ **exe 재빌드 필요**(~235 MB). `client/dist/`·`build/`·`*.spec`은 의도적 gitignore이므로 소스만 push되고 exe는 낡는다.
- `AssyManagerClient.spec`의 `datas=[]` → `client_settings.json`은 exe에 번들되지 않는다. `settings_file_path()`(:60)는 frozen일 때 `sys.executable` 디렉터리를 먼저 본다(운영자 사본은 exe 옆). frozen + 파일 없음 = 기본값, 즉 종전과 동일.
- `register_uri_scheme()`은 **서버 URL을 담지 않는다**(`"{python_exe}" "{wrapper_path}" "%1"`) — 범위 밖 확인. 다만 이 커맨드는 **소스 스크립트 + 현재 python**을 가리켜 exe만 설치한 사용자에게는 어긋난다(별건, 미수정).
- `run_decoupled_app.py`가 셸을 자식으로 띄우면 `ASSY_API_PORT`가 자식에게 상속된다. 지금 셸은 그것을 읽지 않으므로 `ASSY_API_PORT=8081`로 스택을 띄우면 **서버는 8081, 셸은 여전히 8080**이다(종전과 동일한 동작 — 무회귀 기준을 지키려 일부러 손대지 않음). 5번째 순위로 넣을지는 총괄 판단 사항.
