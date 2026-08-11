# 🖼️ Frontend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-08-11 | **Owner:** UI / Excel Interaction
> **Source-of-truth:** `client2/src/*`, `client2/vite.config.js`, `client/desktop_wrapper.py`
>
> ### 이번 라운드 (2026-08-11 3차 · `42d7600`)
> - ✅ **바로 아래 2차 라운드의 ⚠️ 항목이 닫혔습니다 — 확정 문구의 arity 판정이 끝났습니다.** 슬롯은 **하나**(`data-me2-confirm-unit`)이고 룰이 선언한 `decision_key` 값들을 그 자리 하나에 채웁니다. 두 훅(`data-me2-confirm-eqp`/`-product`)과 그것을 먹이던 두 이름 필드는 **삭제**됐습니다. §4.2 갱신.
> - 🔴 **판정의 내용은 「문구를 어떻게 쓰나」가 아니라 「arity를 아는 자리를 어디에 두나」였습니다.** `3d43a6c`가 `keyFrom`에서 지운 **두 값 모양**이 화면 문구에 **한 벌 더** 있었고(같은 결함의 두 번째 사본), 그래서 운영 룰(선언 컬럼 1개)이 읽는 문장은 **그 룰이 갖지 않은 모양**으로 지어져 있었습니다. 지금은 문구를 짓는 함수 안에 **arity를 가르는 분기가 없습니다** — 선언의 키 순서가 곧 순서이고 길이가 곧 arity입니다.
> - ⚠️ **화면 문구 자체는 이 문서에 옮기지 않습니다**(DOC_OWNERSHIP의 이 파일 행 규율). 문서가 소유하는 것은 **슬롯이 하나이고 그 내용이 선언에서 온다**는 사실이고, 글자는 마크업이 정본입니다.
> - **§3 모듈 표의 map2 줄 수 재실측** — `412 + 9,877` → **`470 + 10,173`**(파일 수 18은 그대로). 헤드 실측이며 워킹트리의 다른 레인은 이 디렉터리를 안 건드립니다.
> - ⚠️ **`42d7600`이 스스로 열어 둔 것 둘**(수리 아님, 기록): ① 문구와 전송 키가 **같은 `__key`를 서로 다른 두 함수로** 읽으므로, 채택된 룰이 선언하지 않은 컬럼이 서빙되면 **보여 준 뒤 버려집니다**. ② arity 1·3 룰을 **라이브 서버에 물려 확정 버튼을 누른 적은 없습니다**(하네스·브라우저 파서까지만).
>
> ### 직전 라운드 (2026-08-11 2차 · `3d43a6c`)
> - 🔴 **§4.2에 확정 키 조립과 룰 채택 실패 사유를 추가했습니다.** `decisionKeyOf(declaration, decision)`가 `keyFrom`을 대체했습니다 — 룰의 `decision_key` 선언을 아무 arity에서나 그대로 따르고, 선언된 컬럼을 하나라도 못 채우면 `key`는 `null`입니다(옛 `keyFrom`은 arity 2에서만 선언을 따르고 그 외 전부에서 `{dt_eqp, product}`를 하드코딩해, 컬럼 하나만 선언하는 운영 룰을 한 번도 확정시키지 못했습니다). 그리고 **룰 채택 실패가 침묵 대신 사유를 말합니다** — `selectAlignmentRules`가 `alignment: true` 선언 0건/여러건일 때 워크리스트 요청 자체가 안 나갔는데(`refreshWorklist()` 진입 전 리턴), 종전 화면은 그것을 빈 목록으로만 보여줘 "로딩 중"과 "실패"가 같은 픽셀이었습니다. 지금은 `정렬 규칙 없음 · alignment 선언 0/N건 · 1건 필요` / `규칙 선택 필요 · alignment 선언 N건 · 1건만 자동 채택`을 냅니다. 정본은 [MAP_ALIGNMENT_SPEC §5](../spec/MAP_ALIGNMENT_SPEC.md)(계약 자체는 그 문서 소유, 여기는 모듈 경계만).
> - ✅ ~~**`map_editor2.html:856`의 확정 문구는 아직 정확히 두 개의 키 값(`data-me2-confirm-eqp`/`-product`)을 전제합니다** — 위 수정으로 arity 1/3 룰의 확정이 처음으로 도달 가능해졌는데 문구는 아직 안 바뀌었습니다. 총괄 판정 대기(`3d43a6c` 커밋 본문).~~ → **`42d7600`으로 닫혔습니다**(위 이번 라운드). **이 문장의 두 절이 모두 거짓이 됐습니다** — 전제도 두 훅 이름도 더는 존재하지 않습니다.
>
> ### 직전 라운드 (2026-08-11 1차 · 리빙 동기화 ― `db1ee42`)
> - 🔴 **§4.2의 후보 축 문장을 다시 썼습니다 — 직전 라운드가 적은 「거울 반쪽 = 우상단 시작 반쪽」이 *같은 날* 거짓이 됐습니다.** ① 그 등가는 **4분의 1 회전에서 틀리고**(거울은 90°/270°에서 행 축을 뒤집습니다) ② `db1ee42`부터 **거울은 후보 집합에 없습니다.** 후보는 `candidates.js`가 조립하는 **4회전 × 2시작모서리**(`rot90_tl`/`rot90_tr`), 면은 전부 `front`입니다. ⚠️ **레거시 `_back` 철자는 계속 읽히고 `뒷면`이라고 그려집니다** — 걸음 축 이전에 확정된 행은 **진짜 거울 선언**이라 `우상단 시작`이라 부르면 이 화면이 틀린 등가를 다시 말하게 됩니다.
>
> ### 그 앞 라운드 (2026-08-08 · 리빙 동기화 ― `e943e46`·`21209d7`·`c959368`·`15a2b39`)
> - ✅ **§4.2의 「마크업 문구는 아직 두 단계」가 해소됐습니다** — HEAD 실측: `map_editor2.html`이 「쓰기는 한 동작(클릭 또는 Enter)」·`Enter 확정`을 들고 있고 `data-armed`는 없습니다.
> - 🔴 **§4.2에 셋을 더했습니다.** ① **확정 버튼의 유일한 관문은 「무언가 골랐는가」**(`21209d7`) — `not_scorable`과 「추측 위에 선 답」은 **막는 것이 아니라 알리는 것**이 됐습니다(채점기가 못 채점한 상태가 **사람이 유일한 답인 바로 그 상태**였습니다). ② **후보 문구는 `앞면/뒷면`이 아니라 `좌상단/우상단 시작`**(`c959368`) — 🔴 **이 항목에 함께 적었던 「거울 반쪽 = 우상단 시작 반쪽」은 `db1ee42`에 교체됐습니다**(위 이번 라운드 참조). ③ **워크리스트는 테이블마다 묻는다**(`e943e46`) — 안 다시 물으면 실패는 「낡은 목록」이 아니라 **「한 화면에 두 테이블」**이고, 교체는 `AbortController` 하나이며 **취소는 실패가 아닙니다.**
> - **§3 모듈 표: 줄 수 9행 재실측**(2026-08-04 이후 드리프트) — `enrichment.js` 788→**1266**, `map_editor.js` 9683→**11060**, `config.js` 5→**113**, `websocket.js` 350→**488**, `map2` 17파일/7,260→**18파일/9,877**, 그 외 4행 소폭. **`enrichment.js`에 셀 복사(`15a2b39`)를 등재**했습니다 — 🔴 **AG-Grid가 기본적으로 셀 텍스트 선택을 막는다**는 것이 원인이었고 클립보드 문제가 아니었으며, `clipboard.js`를 **부르지 않은 것이 설계**입니다.
>
> ### 직전 라운드 (2026-08-06 · 프레임 바인딩 삭제 `62520b9` + 한 동작 확정 `02416d4`)
> - 🔴 **§4의 「`withPhysFrame`(프레임 창)으로 규격 읽기 지점을 갈아끼운다」가 거짓이 됐습니다** — 그 창 함수와 모듈 바인딩 `physFrameOverride`가 **삭제**됐고 프레임은 **첫 인자**가 됐습니다. 답은 하나도 안 바뀌었고 바뀐 것은 전달 방식입니다. 🔴 **`null`(의도적으로 화면을 읽어라)과 `undefined`(호출자가 잊었다 → `throw`)가 다른 답**이라는 것이 새로 생긴 규약입니다.
> - **§2.1의 `MODULE_STATE` 실측을 48 → 47로 갱신**(천장은 48 그대로, 여유 하나). 그 1이 리팩터 전체에서 이 수가 움직인 유일한 순간입니다.
> - 🔴 **§2.1의 「6계약」을 지우고 구성원으로 바꿨습니다** — `map2_seam`이 들어오면서 그 수가 낡았고, **목록 옆의 수는 목록의 두 번째 사본**입니다. `contracts/notation_fold/`는 클라 절반이 없어 이 스캔에 안 잡힙니다(디렉터리 수 ≠ 계약 수).
> - ✅ **§4.2의 「`api.js`의 `ROUTES`가 옛 철자를 들고 있다」가 해소됐습니다** — 전수 대조 결과 어긋나는 철자 **0건**. 대신 **확정이 한 동작**이라는 사실을 적었고, **마크업 문구는 아직 두 단계**라 워킹트리에만 있다는 것도 함께 적었습니다.
>
> ### 직전 라운드 (2026-08-05)
> - 🔴 **§2 진입점 표와 §3 모듈 표에 `map_editor2.html` / `src/map2/*`가 없었습니다** — 페이지 하나와 모듈 17개(약 7,700줄)가 **이 문서에 존재하지 않는 채로** 출하됐습니다. §4.2 신설.
> - 🔴 **「정렬 캔버스에 웨이퍼 테두리가 그려진다」는 거짓입니다**(`d4e0fed`) — 그 원은 **어떤 JS도 읽지 않는 하드코딩 장식**이었고 **모든 맵이 구성상 그것을 넘쳤습니다.** 근거 없이는 아무것도 그리지 않습니다.
> - **`src/map2/*`에는 파일별 행을 만들지 않았습니다** — 읽어야 할 것은 파일 이름이 아니라 **층 경계**이고, 목록은 이 표의 유지 주기보다 빨리 낡습니다.
>
> ### 그 앞 라운드 (2026-08-04)
> - 🔴 **「`mm`은 일부러 비어 있다」를 삭제했습니다 — 클라에 mm 공간이 생겼습니다**(`cd3e0f4`, 나흘간 이 문서를 포함해 여러 곳에서 거짓이었습니다). §4의 오버레이 행이 새 좌표 단계를 싣습니다.
> - **§3 모듈 표에 3행 신설** — `map_key.js`·`split_registry_row.js`(맵 에디터 분할 R1/R2) + 행 없이 굴러가던 `retroactive_view.js`. `map_editor.js`는 **분할 진행 중**이라 행이 그 사실을 적습니다.
> - **줄 수 전면 재실측** + §2.1의 하네스 **수를 삭제**했습니다(러너가 매 실행마다 찍는 수를 산문이 다시 적을 이유가 없고, 그 사본이 세 번 낡았습니다). `check:contracts`는 **6계약**(`blank_predicate` 추가)입니다.
> - **§2.1에 `ASSERTIONS` 프로토콜과 단언 플로어**(`b322267`→`efc4514`) — 종료코드는 근거 없는 판결입니다.
>
> **이전 라운드 기록은 [`docs/history/`](../history/)에 있습니다** — 🔴 이 헤더에 쌓지 마십시오. 2026-08-04에 5,647자짜리 변경 이력 괄호 하나를 걷어냈고, 그 내용은 전부 히스토리에 있습니다. 헤더는 **날짜 · 이번 라운드에 바뀐 것**까지입니다.
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

---

## 1. 개요: 웹앱 + 얇은 데스크톱 셸

메인 클라이언트는 **`client2`(웹)**이며, 데스크톱 앱은 이를 감싸는 QtWebEngine 셸입니다.

- **`client2/`** — Vite 멀티페이지 앱(**엔트리 목록의 정본은 §2 표이고 여기에 수를 적지 않습니다** — 「6엔트리」라고 적혀 있었고 `map_editor2.html`이 들어오면서 낡았습니다), **Vanilla ESM JavaScript(프레임워크 없음)**, JS ~13,000줄. 듀얼 테마(기본 라이트, `tokens.css` 토큰 SSOT + `theme.js` 토글).
- **`client/desktop_wrapper.py`** — `{해석된 서버}/?client=desktop`를 로드하는 `QWebEngineView`(:280-287). `?client=desktop` 플래그로 `state.isDesktop`(state.js:32) 토글. 서버 주소는 하드코딩이 아니라 §1.1의 우선순위로 해석된다.

> ⚠️ 구 PySide6 데스크톱 클라이언트(`client/main.py`, `client/ui/`, `client/models/table_model.py`)는 **제거되었습니다.** 남은 것은 `desktop_wrapper.py`뿐.

### 데스크톱 셸 네이티브 기능
| 기능 | 구현 |
|---|---|
| OS 드래그앤드롭 업로드 | `DropEventFilter`+`dropEvent`, `window.currentTable` 조회 후 `httpx`로 `{base}/tables/{t}/upload` POST (:357-399) |
| 네이티브 다운로드 다이얼로그 | `handle_download_request` → `QFileDialog` (:401-419) |
| DevTools | F12 인스펙터, 원격 디버깅 :9222 |
| URI 스킴 | `assymanager://` HKCU 등록 (:433-461). 등록 커맨드는 `"{python_exe}" "{wrapper_path}" "%1"` — **서버 주소를 담지 않는다**(핸들러는 주소와 무관) |

### 1.1 서버 주소 해석 — **셸이 어느 서버를 보는지의 유일한 결정 지점** (2026-07-30)

이전에는 두 곳이 각자 주소 문자열을 만들었고 **서로 달랐다**: 업로드는 `http://127.0.0.1:8080/tables/...`, 페이지는 `http://localhost:8080/?client=desktop`. 그리고 `client/client_settings.json`(git 추적 대상, `server_host`/`server_port` 보유)은 **한 번도 읽히지 않았다.**

지금은 `resolve_server_target()`(:183) 하나가 결정하고, `base_url()`(:216)이 **주소를 URL 문자열로 만드는 유일한 자리**다. 소비자는 각자 경로만 붙인다 — 페이지 `?client=desktop`(:287), 네이티브 업로드 `/tables/{t}/upload`(:377). 둘 다 `self.server_base` 하나를 읽는다.

| 순위 | 원천 | 형태 | 이유 |
|---|---|---|---|
| 1 | `--server` 인자 | `--server 10.0.0.5:9999` · `--server=host` · `http://host:port` | 한 번 다른 서버에 붙이는 일이 파일 편집을 요구해선 안 된다 |
| 2 | `ASSY_SERVER` 환경변수 | 위와 동일 | 배포 스크립트·바로가기용. **빈 값은 미선언으로 취급**(`set ASSY_SERVER=`가 Windows의 해제 방식) |
| 3 | `client_settings.json` | `{"server_host": ..., "server_port": ...}` | 기존 권위이자 사람이 편집하는 자리. 단 **git 추적 대상**이라 운영자가 편집하면 워킹트리가 더러워진다 — 1·2가 앞서는 이유 |
| 4 | 기본값 | `127.0.0.1:8080` | 파일이 없거나 비어도 **이전 하드코딩과 동일 동작**(무회귀) |

**선언이 있는데 잘못되면 조용히 기본값으로 내려가지 않고 거절한다**(`ServerTargetError` → stderr + `QMessageBox` + `exit 2`). 포트를 잘못 적은 운영자가 아무 통보 없이 다른 서버에 붙는 일을 막는 게 목적이다. 거절 대상: 파싱 불가 JSON · 비숫자/범위 밖 포트(**0 포함 — 미상 ≠ 0**) · 빈 `server_host` · `https` 스킴(조용한 강등 금지). **파일 부재·빈 파일·서버 키 미선언은 정상 설정**이며 조용히 기본값을 쓴다.

- **시작 로그 1줄**: `[Desktop Wrapper] Server target: http://host:port (source: arg|env|client_settings.json|default)`. `source`가 있어야 운영자가 "내 편집이 무시됐다"를 알 수 있다. (이전 줄 `"Vite dev server not detected..."`는 **Vite가 켜져 있어도 무조건 출력되는 거짓말**이었고 짝인 `is_port_open`은 한 번도 호출되지 않았다 — 둘 다 삭제.)
- **`--print-target`**: 해석·출력 후 종료(GUI·HKCU 미접촉)하는 헤드리스 점검 경로.
- **`NO_PROXY`**: :9의 기준값은 루프백뿐이므로 해석된 호스트가 LAN 주소면 `extend_no_proxy()`(:227)가 그 호스트를 추가한다. **httpx 업로드 경로에는 유효하지만 QtWebEngine에는 보장되지 않는다** — Windows Chromium은 프록시 설정을 OS에서 읽는다. Qt측 레버는 `QNetworkProxy.setApplicationProxy(NoProxy)`(:510, 주석 처리 유지).
- **`ASSY_API_HOST`/`ASSY_API_PORT`(`run_decoupled_app.py`)는 재사용하지 않는다**: 그쪽은 서버의 *바인드* 선언이고 `ASSY_API_HOST` 기본값은 **빈 문자열(듀얼스택 와일드카드)** — 다이얼할 수 있는 주소가 아예 아니다. (2026-08-04 이전엔 `0.0.0.0`이었고 그 역시 다이얼 대상이 아니었다. 근거는 [backend §1.3-ter](./backend.md).)
- 셸이 로드한 origin은 웹앱 전체로 전파된다: `config.js:2`의 `API_BASE = window.location.origin`(프로덕션 빌드), `WS_URL`도 동일 host 기준. 즉 **REST·WS는 별도 설정 없이 해석된 서버를 따라간다.**
- ⚠️ **exe 재빌드 필요**: `client/dist/`·`client/build/`·`client/*.spec`은 의도적으로 gitignore(소스만 push). 소스를 바꿨으면 exe는 낡는다. `AssyManagerClient.spec`의 `datas=[]`이므로 `client_settings.json`은 exe에 **번들되지 않는다** — 운영자 사본은 exe 옆에 두며, `settings_file_path()`(:60)가 frozen일 때 `sys.executable` 디렉터리를 먼저 본다.

---

## 2. 진입점 & 빌드

`vite.config.js` **멀티페이지 빌드**(`rollupOptions.input`):

| HTML | ESM 모듈 | 페이지 |
|---|---|---|
| `index.html` | `src/main.js` | 데이터 그리드(메인) — 「🕸️ 추적」 진입점(`trace_launch.js`) 포함 |
| `admin.html` | `src/admin.js` | 어드민 — 파이프라인 생애주기 5탭(§5, Monaco CDN) |
| `map_editor.html` | `src/map_editor.js` | 웨이퍼 맵 에디터 |
| `map_editor2.html` | `src/map_editor2.js` (+ `src/map2/*`) | **Map Editor 2 — 맵 정렬 화면**(2026-08-05 신설, 개발 중). 🔴 **레거시 에디터를 대체하지 않고 *옆에 선다*** — 위 진입점은 새 화면이 실제로 프레임을 확정할 수 있게 될 때까지 그대로 출하됩니다(`vite.config.js`가 그렇게 적고 있습니다). 서버 라우트는 `39b43ab`에서 붙었습니다 |
| ~~`enrichment.html`~~ | ~~`src/enrichment.js`~~ | 🗄️ **[2026-08-11 `ab36fab`] 삭제됨** — 파일도 vite `rollupOptions.input` 진입점도 없다. `1e29078`이 배지·nav 링크를 먼저 걷었고(product-owner ruling — "correction happens in the grid"), 이 커밋이 페이지 자체를 지웠다. `src/enrichment.js`는 소스에 남아 있으나 **어떤 HTML도 그것을 로드하지 않는 죽은 모듈**이다(`effort_meter.js`가 그 사실을 주석으로 명시하고 정리를 별도 결정으로 미룬다). 조회 절반(참조뷰)은 아래 §3 모듈 표의 `enrichment_reference_view.js`로 이식됐다. **[`fde424c`] `/enrichment.html`을 직접 열면 404 본문이 "Enrichment 페이지 폐지됨 · 참조뷰 → 메인 화면 이력 사이드바 탭"**이라고 답한다 — 종전 문구("Please build frontend first")는 존재할 수 없는 파일을 빌드하라고 운영자를 보내는 거짓 처방이었다. 라우트 자체는 살려 뒀다(북마크가 SPA 캐치올의 `index.html`로 떨어지지 않고 명확한 답을 받도록) |
| `graph.html` | `src/graph_viewer.js` | 지식그래프 서브그래프 뷰어(§6) |
| `trace.html` | `src/trace.js` | 객체 중심 추적 리포트(§6) |

빌드 산출물 `dist/`는 FastAPI(:8080)가 서빙. `define`로 빌드 타임에 `import.meta.env.VITE_USER`(OS 사용자명) 주입 → `config.js`의 `CURRENT_USER`.

```bash
cd client2
npm run dev       # :5173 개발서버 (API/WS는 127.0.0.1:8080 자동 타겟)
npm run build     # prebuild(§2.1의 세 채점자) → dist/ 생성
```

### 2.1 빌드 게이트 — **클라 절반을 채점하는 유일한 자리** (`5a14e77` → `77a2c15`/`d5f75a8` · 2026-07-30)

`package.json`의 `prebuild`가 `check:clipboard && check:contracts && check:harnesses` 순으로 돌고, **하나라도 실패하면 `vite build`에 도달하지 않습니다.**

> 🔴 **2026-07-30 밤 — `check:suggest-keys`가 `prebuild`에서 빠졌습니다. 약해진 게 아니라 흡수된 것입니다.** 그 하네스는 `client2/tests/` 안에 있고 신설 `check:harnesses`가 그 디렉터리를 **발견식으로** 훑으므로 여전히 매 빌드마다 돕니다. 스크립트 자체는 남아 있어 단독 실행이 됩니다. **이 문단이 세 번째로 낡은 자리이므로 다시 적습니다 — 정본은 `package.json`의 `prebuild` 한 줄입니다.**

> 📌 **이 절이 스스로 경고한 결함에 이 절이 걸렸습니다.** 아래 「하드코딩 목록은 이 결함을 그대로 재생산합니다」가 계약 러너에 대한 경고인데, **게이트 목록 자체를 산문으로 하드코딩한 이 문단**이 `check:suggest-keys` 착지 후 **하루도 안 돼 낡았습니다**(2행이라고 적혀 있었고 실제는 3행). 조용히 고치지 않고 남겨 두는 이유는 이것이 규율의 예시이기 때문입니다 — **게이트의 정본은 `package.json`의 `prebuild` 한 줄이고, 이 문단은 그것의 사본입니다.** 사본을 읽지 말고 그 줄을 읽으십시오.

- **왜 생겼나**: `contracts/<name>/client_harness.mjs`는 이음매(seam)의 **클라 절반**을 `vectors.json`에 채점하는데, 2026-07-30까지 **아무것도 그것들을 실행하지 않았습니다** — `pytest server/tests/`는 **서버 절반만** 채점하고 `client2/package.json`에는 스크립트가 없었습니다. 그 결과 `split_registry_harness.mjs`가 심볼 5개 개명 뒤 추출 단계에서 **몇 주 동안 예외로 죽어 있었고**, 부르는 사람이 없어 실패가 보이지 않았습니다. **아무도 돌리지 않는 계약은 주석입니다.**
- **발견식이지 목록이 아닙니다**: 러너(`client2/scripts/check_contracts.mjs`)는 `contracts/*/client_harness.mjs`를 **스캔**합니다. 하드코딩 목록은 이 결함을 그대로 재생산합니다 — 계약 #5가 착지하고 아무도 목록에 추가하지 않으면 빌드는 초록인 채 그 계약이 죽어 있습니다.
- 🔴 **빈 스캔은 실패입니다.** `contracts/`가 사라지거나 하네스가 하나도 안 잡히면 "0개, 전부 초록"이 아니라 **exit 1**입니다 — 없는 커버리지를 있다고 보고하는 것은 배선 안 된 종전 상태보다 나쁩니다.
- **판정은 종료코드 하나**로 읽습니다. 하네스의 산문을 러너가 재해석하면 채점자가 둘이 됩니다(`map_seam`은 이름 붙은 기대 발산을 출력하면서 exit 0입니다 — contract-keeper 헌장 규칙 5 "익명의 영구 빨강 금지").
- **게이트는 계약 하네스만이 아닙니다**(2026-07-30 정정). 종전 이 줄은 *"4계약 전부 통과"*로 끝났는데, 그것은 **`check:contracts`의 상태일 뿐 게이트 전체의 상태가 아닙니다.** 지금 세 채점자가 있습니다:
  - `check:clipboard` — 클립보드 관례(`scripts/check_clipboard_convention.mjs`).
  - `check:contracts` — `contracts/*/client_harness.mjs` **발견식 스캔**. 🔴 **수를 적지 않습니다 — 러너가 스캔한 것을 찍고, 이 자리에 적힌 수는 이미 한 번 낡았습니다**(2026-08-04에 「6계약」이라고 적었고 `map2_seam`이 들어오면서 거짓이 됐습니다. 목록 옆의 수는 목록의 두 번째 사본입니다). 실측 2026-08-06에 클라 절반을 가진 계약: `band_arithmetic` · `blank_predicate` · `config_resolve_report` · `doe_band_rules` · `legend_map_scope` · `map_seam` · **`map2_seam`**(맵 정렬 화면의 이음매). ⚠️ **`contracts/notation_fold/`는 이 스캔에 안 잡힙니다** — `vectors.json`과 서버 테스트만 있고 `client_harness.mjs`가 없습니다(클라 절반이 없는 계약이라 이 게이트가 채점할 것도 없습니다). **디렉터리 수 ≠ 계약 수**입니다. ⚠️ `config_resolve_report`는 **렌더러가 없는 지금도 채점합니다** — 금지 단언(INV-F9-7)은 초록이고 나머지 절반(INV-F9-4)은 **`PENDING`으로 이름 붙여** 보고합니다(통과로 세지 않습니다). 목록이 하드코딩이 아니라 **발견식**이라 신설 계약이 규약대로 놓이면 러너를 안 고쳐도 잡힙니다.
  - `check:harnesses` — **`client2/tests/*.mjs` 발견식 스캔**(2026-07-30 밤 신설, `scripts/check_harnesses.mjs`). 계약 러너와 같은 모양이고 **빈 스캔은 실패**입니다. 강제 대상과 부채 목록(`KNOWN_RED`)으로 갈리며, 부채 항목이 초록으로 돌아오면 「목록에서 빼라」는 줄을 출력합니다. 🔴 **여기에 하네스 수를 적지 않습니다.** 러너가 매 실행마다 `N harnesses ― M gated, K known-red`를 찍고, 그 사본은 하네스가 추가되는 커밋마다 낡습니다 — 이 자리에 적힌 수는 **세 번 낡았고 그중 한 번은 적힌 그 시점에 이미 틀렸습니다.** 알고 싶으면 세지 말고 **러너를 돌려 그 출력을 읽으십시오.** ⚠️ 그 디렉터리에는 **`seam_7b_oracle.py`도 있는데 파이썬이라 스캔 대상이 아닙니다** — 파일 수 ≠ 하네스 수입니다. 🔴 **이 게이트가 생긴 이유**: 직전까지 대부분을 **아무도 부르지 않았고**, 그 조건이 `split_registry_harness.mjs`를 몇 주 죽어 있게 뒀으며 `da8f390`이 두 개를 더 죽인 채 푸시되게 했습니다. **조용히 skip하면 게이트가 없는 것과 같으므로** 부채는 목록으로 드러냅니다.
  - 🔴 **`ASSERTIONS` 프로토콜**(`b322267` — 맵 에디터 분할 라운드 0의 전제조건): **종료 코드는 근거 없는 판결입니다.** 「0개 단언으로 빨강」(단언에 닿기 전에 죽은 하네스)과 「N개 단언으로 빨강」을 구분하지 못해 **죽은 하네스 셋이 부채로 위장**하고 있었습니다. 이제 모든 하네스가 자기 요약 지점에서 `ASSERTIONS <ran> <failed>` 한 줄을 찍고 러너는 **세지 않고 읽습니다**(하네스의 자기 집계가 유일한 채점자 — 러너가 마커를 다시 세면 채점자가 둘이 됩니다). 초록인데 줄이 없거나 `ran=0`이면, `failed>0`인데 초록이면, 그리고 `KNOWN_RED` 항목의 기록된 기대쌍(**`ran`은 바닥, `failed`는 천장**)을 벗어나면 **부채 여부와 무관하게 BLOCKING**입니다. 단언 없는 순수 측정 프로브(`reposition_regime_probe.mjs`)는 `ASSERTIONS 0 0`을 찍으므로 그 크래시가 언젠가 고쳐지면 러너가 「단언을 달라」고 거절합니다 — 의도된 강제입니다.
  - 🔴 **단언 플로어**(`efc4514`): 초록 하네스도 `FLOORS`에 **최소 `ran`**을 기록하고, 그 아래로 떨어지면 **하네스 자신이 exit 0이어도 BLOCKING**입니다(실측: 15개 중 4개를 지운 하네스가 `11 passed, 0 failed`로 깨끗하게 초록이었습니다 — 종전 러너는 그 27% 커버리지 상실 위에 「every gated harness is green」을 찍었습니다). **상승은 보고만 하고 강제하지 않습니다** — 단언을 *추가*했다고 빌드를 깨면 사람은 단언을 안 추가하게 됩니다. 한 하네스의 플로어는 **한 곳에만** 삽니다: `KNOWN_RED`에 있는 이름이 `FLOORS`에도 있으면 러너가 **기동을 거부**합니다. 플로어가 없는 신규 하네스는 실패가 아니라 **큰 소리의 메모**입니다.
  - 🔴 **천장(`CEILINGS`) — 플로어의 반대 방향**(2026-08-04 `510a748`). 플로어가 「이만큼은 채점해야 한다」면 천장은 **「이 수는 여기서 더 늘어나면 안 된다」**입니다. 현재 항목은 **하나**입니다: `undeclared_identifier_harness.mjs`의 `MODULE_STATE`, 대상은 **`client2/src/map_editor.js`의 모듈 레벨 가변 바인딩**, 상한 **48**. 분할이 진행 중인 파일에서 **순수 절반을 떼어내는 것보다 새 전역을 다는 것이 늘 더 쉬우므로**, 천장이 없으면 분할이 순손실이 됩니다.
    - ⚠️ **`CEILINGS`의 항목 수를 여기 적지 않습니다** — 종전 「현재 항목은 **하나**입니다」였고, 천장은 늘어납니다. 지금 걸린 항목: `undeclared_identifier_harness.mjs`의 `MODULE_STATE`.
    - **세는 규칙은 세는 쪽에 삽니다**(러너는 세지 않고 `MODULE_STATE <n>` 줄을 **읽습니다** — 채점자가 둘이 되지 않게). 규칙: **최상위 `let`/`var`의 선언자(declarator)마다 하나**, `let a, b;`는 둘, 구조 분해는 묶는 이름 전부, **`export let x`도 센다**(오히려 더 공개적인 가변 상태다). 세지 않는 것: `const`(재대입 불가) · `function`/`class` 선언(바인딩이지 상태가 아님) · 함수·블록·클래스 본문 안의 무엇이든.
    - 🔴 **줄이 없으면 BLOCKING입니다** — 조용한 천장은 천장이 아닙니다. 하네스는 자기 검출기가 살아 있음도 함께 채점합니다(최상위 `let` 하나를 주입하면 수가 **정확히 1** 오르고, 최상위 `const`·함수 지역 `let`/`var`는 **안 오릅니다**).
    - ⚠️ **실측 2026-08-06: 47, 천장은 여전히 48이므로 여유는 하나입니다.** 🔴 **종전 이 줄은 「실측 2026-08-04: 48 — 여유가 0」이었고 그것은 이제 낡았습니다** — `62520b9`(프레임 바인딩 삭제)가 `physFrameOverride`를 지우면서 48→47로 **1 내렸고, 그것이 그 리팩터 전체에서 이 수가 움직인 유일한 순간**입니다. 여유가 하나라는 것은 여전히 「하나 더 달면 그 다음이 막힌다」는 뜻입니다. 그리고 그 47에는 **이미 죽은 것으로 판정된 바인딩 둘(`tables`·`isMouseDown`)이 포함**돼 있습니다 — 여유를 원하면 새 천장을 협상하지 말고 그 둘을 지우십시오. ⚠️ **`check_harnesses.mjs`의 천장 주석은 아직 「48 INCLUDES TWO BINDINGS」라고 적고 있습니다**(코드라 이 라운드가 손대지 않았습니다 — 총괄 보고).
    - ⚠️ **git worktree에서는 이 하네스가 UNAVAILABLE입니다**(`rolldown/parseAst`를 임포트하므로 `client2/node_modules`가 있어야 합니다). 천장은 **본 체크아웃에서만 실제로 뭅니다.**
  - 🔴 **부채 항목의 산문(`why`)은 기계가 알 수 없는 것만 담습니다 — 수는 절대 담지 않습니다**(`db46525`). 러너가 같은 줄에 실측치를 나란히 찍으므로 산문의 수는 순수 중복이고, 그 중복이 「28」을 살려 두어 보드까지 「41」을 찍게 만들었습니다(실측은 42). 구조화 필드 `ran`/`failed`는 산문이 아니라 **강제의 바닥과 천장**이므로 지우지 마십시오.
  - `check:suggest-keys` — 값 제안 셀 에디터의 **키보드 계약**(`tests/value_suggest_keys_harness.mjs`, §3.3). ⚠️ `prebuild`에서는 빠졌지만 `check:harnesses`가 같은 파일을 발견해 돌리므로 **매 빌드에 여전히 채점됩니다**. 계약 벡터가 아니라 **AG-Grid 키보드 파이프라인 모델** 위에서 실제 `SuggestCellEditor`+`suppressKeyboardEvent`를 돌리고, 판정을 「핸들러가 옳은 문자열을 돌려줬나」가 아니라 **키스트로크 수**로 씁니다(`effort_meter`와 같은 계수 규칙). 모든 점검에 **변이(mutation)가 짝지어져** 있고 변이가 잡히지 않으면 실패합니다 — ⚠️ 변이는 **APPLIED와 CAUGHT를 따로** 보고합니다(`cb8f01a`: 18개 중 8개가 적용조차 안 되면서 베이스라인은 초록이었습니다. 검색 문자열이 안 맞는 변이는 **조용한 무장 해제**입니다).
  - ⚠️ 이 하네스가 통과해도 **브라우저 실측이 1차 증거**입니다. AG-Grid가 호출 순서를 바꾸면 모델은 통과하고 제품은 깨집니다.

> ⚠️ 이 게이트는 **소스**를 채점합니다. 서버가 서빙하는 것은 `dist/` 번들이므로, 소스 변경 후 `npm run build`로 `dist/`를 갱신하고 커밋하는 규율은 그대로입니다([DEPLOY_SETUP](../guide/DEPLOY_SETUP.md) · [FEATURE_CHECKLIST §2.16 A](../qa/FEATURE_CHECKLIST.md)).

---

## 3. 모듈 구조 (`client2/src`)

> **줄 수는 `wc -l` 실측입니다**(2026-08-04 전면 재실측). 정확성이 아니라 **상대 규모**를 읽는 열입니다 — 어느 모듈이 이 화면의 무게중심인지 보기 위한 것이므로, 몇 줄 어긋나는 것보다 **행이 아예 없는 모듈**이 훨씬 나쁩니다(실제로 `value_suggest.js`·`doe_bands.js`·`tsv.js` 셋이, 그리고 2026-08-04까지 `retroactive_view.js`가 행 없이 굴러갔습니다).

| 파일 | 줄 | 책임 |
|---|---|---|
| `main.js` | 2047 | 메인 페이지 오케스트레이터: init(+`initTraceEntry`), 이벤트 바인딩, 소스 모달, 스마트 페이스트(**§2.1-ter 걸쇠** — `smartPasteFromPasteEvent`(읽기)/`smartPasteViaIngestion`(클릭 진입)/`uploadSmartPastePayload`), Tx 모드 apply/discard |
| `state.js` | 162 | **단일 싱글턴 상태 저장소**(gridApi, 현재 테이블/스키마, ws, 선택/드래그, 페이지캐시, `pendingTxEdits`) + **`currentVirtualColumns`와 술어 `isVirtualColumn(colId)`**(§3.4). 🔴 가상 컬럼 목록은 **`currentColumns`에 병합하지 않습니다** — 그 배열의 뜻은 「이 테이블이 저장하는 컬럼」이고 소비자 넷이 그 뜻에 기댑니다 |
| `dom.js` | 57 | `getElementById` 지연 게터 모음(`elements`) |
| `api.js` | 533 | REST 계층: health, loadTables, switchTable(테이블 전환 시 `refreshTraceEntry` 재판정), loadSchema(**`virtual_columns`를 `state`에 그대로 보관 — 배열이 아니면 `[]`**), fetchData(페이지캐시), handleCellEdit(Tx 스테이징+숫자검증), addRows, deleteSelectedRows. ⚠️ **검색 드롭다운(`?cols=`)은 `currentColumns`만 훑습니다** — 그 값은 WHERE 절로 가고 가상 이름에는 대응 컬럼이 없습니다(§3.4). ⚠️ **`switchTable`은 `txModeActive`를 강제로 다시 켭니다**(:70-71 — 대기 편집을 버리는 것과 한 쌍이라 안전한 기본값이지만, **표를 바꾸면 토글이 되살아납니다**. 편집 E2E에서 두 번 새는 자리 — [FEATURE_CHECKLIST §2.0](../qa/FEATURE_CHECKLIST.md)) |
| `websocket.js` | 488 | 실시간 동기화: 지수 백오프 재연결(5s 천장 · `visibilitychange`/`online` 웨이크 · flap 가드), `batch_row_{create,upsert,delete}`/`batch_refresh_required`를 AG-Grid 트랜잭션으로 적용(셀 플래시). 🔴 **재연결 사다리 전체가 `initWebSocket` 안에 산다** — 그 함수에 닿지 못한 페이지는 소켓도 재시도도 없다. 그래서 `init()`의 **첫 문장**이다(§3.5) |
| `grid.js` | 869 | AG-Grid 설정/렌더: `buildColumnDefs`(저장 컬럼 뒤에 **가상 조인 컬럼을 APPEND** — §3.4), `renderGrid`, `ensureCellObject`(중첩 셀 `{value,is_overwrite,priority_source}` 정규화), 셀 읽기 공용 `rawCellValue`/`numericDisplayValue`, `extendRangeByKeyboard`(§2.1-bis `Shift`+방향키 범위 선택). **`string` 선언 컬럼의 `cellEditor`를 `SuggestCellEditor`로 갈아끼우는 자리**(§3.3)이고, `defaultColDef.suppressKeyboardEvent`의 **첫 분기**가 `handleEditorKey`를 부릅니다 — 그 한 분기가 **`Enter` 한 번 계약이 서는 기반**입니다(AG-Grid가 `suppressKeyboardEvent`를 `cellCtrl.onKeyDown`보다 **먼저** 호출하므로 `'accepted'` 판정은 "후보가 이미 입력에 들어갔으니 **이 이벤트가 그대로 확정하라**"는 뜻입니다. `false` 반환은 포기가 아니라 **확정**입니다) |
| `value_suggest.js` | 1003 | **값 제안 셀 에디터(§3.3)** — `SuggestCellEditor` + `handleEditorKey`(순수 키보드 판정 `suppress`/`accepted`/`pass`) + `isSuggestEditorActive`. 디바운스 90ms(트레일링)·요청 한도 12·여는 최소 접두 1·표시 8행. 컬럼별 학습(플로어·4연속 4xx 후 비활성·`unavailable_reason` 쿨다운)은 **전부 TTL 60초로 만료**(핫리로드되는 `table_config`를 클라 래치가 조용히 면제받지 않도록). 진단은 `window.__assySuggest` |
| `clipboard.js` | 858 | 엑셀형 범위 선택/클립보드: hit-test, `commitDragSelection`, `getRangeSelectedTSV`, paste, `clearSelectedCells`, `registerSmartPasteHandler`(**§2.1-ter** — paste 핸들러의 스마트 페이스트 걸쇠 분기). **쓰기 세 경로(붙여넣기·delete 비우기·행 복사 술어)는 `isVirtualColumn`으로, 읽기 두 경로(복사 술어)는 그 반대로** 갈립니다 — §3.4 |
| `tsv.js` | 121 | TSV 직렬화/파싱 순수 함수 — 클립보드 경로와 회사 양식 왕복이 공유하는 유일한 구현 |
| `doe_bands.js` | 753 | **DOE zone 모델의 순수 구현**(§4.1) — 구간 소요·자재당 분배 산식의 정본. 계약 벡터 `contracts/doe_band_rules/vectors.json`으로 서버와 같은 기댓값에 채점 |
| `timeline.js` | 899 (2026-08-11 재실측 — 종전 722는 낡음) | 감사 히스토리 패널: `loadHistory`, `appendHistoryLocally`, 로그→그리드 점프 네비게이터. **[2026-08-11 `dab9152`] `readHistoryPage`**(엔벨로프 `{logs,truncated,next_cursor,limit,returned}`와 구버전 bare-list 응답 양쪽을 받는 관용 파서) + 목록 끝 `일부만 (N건) · 더 보기` 페이징(§7) |
| `ui.js` | 431 | 공용 UI 반영: `updateTxModeUI`, `setTransactionFilter`, `applyValueToSelectedRange`(**Ctrl+Enter 일괄 채우기 — 사각형이 뒤쪽 가상 컬럼까지 닿으므로 `isVirtualColumn` 가드 필요**), 페이지캐시 유지, unload 경고. ⚠️ **[2026-08-11] Enrichment 배지(`updateEnrichmentBadge`)는 삭제됐다**(`5116f67` — 호출자 0건이던 죽은 함수) |
| `enrichment_reference_view.js` | 119 (2026-08-11 신설 `1e29078`) | **메인 그리드 History 패널의 참조뷰 탭** — 옛 `enrichment.html` 컨베이어의 조회 절반을 그리드 사이드바로 이식. `syncReferenceViewRule`(테이블 전환 시 그 테이블에 해당 규칙이 있으면 탭 노출) · `refreshReferenceForSelection`(셀 클릭 시 자동 갱신) · `installReferenceKeyboardIsolation`(패널 안 텍스트 선택·복사가 그리드 클립보드 핸들러에 가로채이지 않게 격리 — 그리드 핸들러는 선택이 남아 있으면 **항상** 자기 TSV로 덮어썼다). 같은 백엔드 라우트(`GET /enrichment/rules/{r}/references/{i}`)를 재사용, 새 엔드포인트 없음 |
| `utils.js` | 347 | `getLocalTimeString`, **전역 토스트**(`showToast` — window 부착), 인제션 진행 위젯. 토스트는 **벽시계 `expireAt` 기준 만료**(백그라운드 탭 setTimeout 스로틀링으로 무한 누적되던 원인 제거) · 상한 4(퇴거는 비-에러 오래된 것 우선, 방금 삽입분 면제) · TTL info/success 5s·warning 9s·**error 15s** · `visibilitychange`/`focus` 스윕 · `dedupeKey` 합치기(**에러 제외** — 건별 원인이 중요) · `dismissToasts(dedupeKey)`로 **회수**(지시형 토스트는 그 지시가 참이 아니게 된 순간 사라져야 한다 — §2.1-ter) |
| `theme.js` | 92 | 듀얼 테마 전환(`initTheme`/`toggleTheme`/`syncAgGridThemeClasses`) — 토큰 SSOT는 `tokens.css` |
| `config.js` | 113 | 환경 설정: `API_BASE`/`WS_URL`(5173→8080), `CURRENT_USER`, `pageLimit=1000` |
| `admin.js` | 3708 | 어드민 5탭(§5) |
| `config_resolve_view.js` | 324 | **config 해석 보고서의 뷰 모델(§5, F9)** — DOM 없는 순수 모듈. `GET /admin/config/resolve` 응답을 렌더 트리로 바꾸면서 **모든 문자열에 출처를 태그**한다(`server`=페이로드 원문 · `value`=페이로드 값의 JSON 철자 · `chrome`=고정된 클라 라벨표 · `count`=클라가 센 정수). DOM 빌더 안에 있으면 node에서 채점할 수 없어서 분리한 것이고, `contracts/config_resolve_report/client_harness.mjs`가 **이 모듈을 임포트해** INV-F9-4를 실행 채점한다 |
| `map_editor.js` | 11060 | 맵 에디터 + 페인트 잠금 + **오버레이 레이어**(§4) + 유효 다이 참조([MAP_EDITOR_SPEC §5.7/§5.7-bis](../spec/MAP_EDITOR_SPEC.md)). **이 저장소에서 가장 큰 클라 모듈**이고 **분할이 진행 중입니다** — 순수 함수 덩어리가 라운드마다 `client2/src/`의 별도 모듈로 빠져나가므로(아래 두 행), **「맵 에디터는 파일 하나」라고 읽지 마십시오.** 어느 심볼이 어느 파일에 있는지는 [CODE_MAP](./CODE_MAP.md)을 grep해서 확인하십시오. ⚠️ **「프레임 채택·저장 좌표 재배치」는 이 행에서 삭제됐습니다**(F8 `61440e6`+`94b9baa`로 심볼 8종이 소스에서 사라졌습니다 — 찾지 마십시오) |
| `map_key.js` | 158 | **맵 키의 정준형(§7b)** — `map_editor.js`에서 분리(R1 `689ebb9`). `canonicalKeyValue`(선언 타입으로 키 값을 캐노니컬화) · `composeMapId` · `decomposeMapKey` · `canonicalMapKey` · `getMapIdFromMeta`. 🔴 **서버 `map_overlay.py`와 같은 답을 내야 하는 이음새**이고 양측 채점은 `contracts/map_seam/` + `client2/tests/seam_7b_oracle.py`입니다 — 여기를 고치면 그 둘이 판정합니다. `getMapIdFromMeta`는 분리하면서 `tableSchema`를 **두 번째 인자로** 받게 됐습니다(본문은 바이트 동일 — 하네스가 이 텍스트를 잘라 vm에서 돌립니다) |
| `split_registry_row.js` | 366 | **`map_split_registry` 행의 정규형** — `map_editor.js`에서 분리(R2 `636f867`). 저장 페이로드(`buildLegendRegistryUpdates`·`LEGEND_PAYLOAD_COLUMNS`) · 응답 파서(`parseLegendRegistryRows`) · 지문/서명(`registryFingerprint`·`legendRowSignature`) · legend 아이템 정규화. 🔴 **모듈 상태를 하나도 읽지 않는 순수 절반이고, 그것이 경계가 여기 있는 이유입니다** — 저장 *오케스트레이션*(`saveLegendToServer`·`persistLegend` 등)은 legend 클러스터 7변수를 쓰므로 `map_editor.js`에 **영구히** 남습니다. 채점: `contracts/legend_map_scope/` · `contracts/band_arithmetic/` · `contracts/doe_band_rules/` · `server/tests/test_install_product_tables.py` |
| `map_editor2.js` + **`src/map2/*` (18 파일)** | 470 + 10,173 | **Map Editor 2 — 맵 정렬 화면**(§4.2, 개발 중). 🔴 **파일별 행을 여기 만들지 않습니다** — 이 디렉터리는 라운드마다 모듈이 갈라지고 합쳐지는 중이라 목록이 낡는 속도가 이 표의 유지 주기보다 빠릅니다. **읽어야 할 것은 파일 이름이 아니라 층 경계**이고 그 정본은 [MAP_ALIGNMENT_SPEC §0.2](../spec/MAP_ALIGNMENT_SPEC.md)입니다. 🔴 **레거시와 달리 이 층들은 모듈 상태를 갖지 않고, 그래서 하네스가 소스를 자르지 않고 `import`합니다** — 그 성질이 깨지면 이 디렉터리를 만든 이유가 없어집니다 |
| `transfer_plan.js` | 1875 | **전사 계획 사이드바**(§4.1) — map_editor.html에서 소비. 구 `bonding_plan.js`(M1 Info 패널)를 대체·삭제. **가용 수치의 자격 표시(`*`)가 여기 삽니다** — 서버가 `inactive_subtractions`로 「빼지 않은 감산」을 알리면 가용·잔여 칸에 각주 기호를 붙이고 ②의 각주에 서버의 역할 이름을 **그대로** 인쇄합니다([MAP_EDITOR_SPEC §6.2-ter](../spec/MAP_EDITOR_SPEC.md)가 계약 정본) |
| `retroactive_view.js` | 446 | **소급(backfill) 어드민 화면의 뷰 모델**(§5) — `GET /admin/retroactive/*` 응답을 렌더 트리로. `config_resolve_view.js`와 같은 이유로 DOM 없는 별도 모듈입니다(node에서 실행 채점 — `client2/tests/retroactive_view_harness.mjs`). 운영자 절차는 [BACKFILL_GUIDE §7](../guide/BACKFILL_GUIDE.md) |
| `enrichment.js` | 1266 | Enrichment 컨베이어: 규칙 선택(`loadRules/selectRule`), 워크리스트(`fetchWorklist`), 입력 흐름(`onInputKeydown/saveCurrent` → PUT `/data/updates`), 참조 패널(`initReferencePanel/loadActiveReference`, stale 가드). **셀 복사(2026-08-07 `15a2b39`)** — `GRID_SHARED_OPTIONS`에 `enableCellTextSelection`+`ensureDomOrder`. 🔴 **AG-Grid는 기본적으로 셀 텍스트 선택을 막습니다** — 드래그가 아예 시작되지 않던 것이지 클립보드 문제가 아니었습니다. ⚠️ **이것은 브라우저 기본 복사이지 범위 복사가 아닙니다**(AG-Grid의 범위 클립보드는 Enterprise이고 이 페이지는 Community). 🔴 **`clipboard.js`를 부르지 않은 것이 설계입니다** — 그 모듈이 `grid.js`·`state.js`·`dom.js`·`ui.js`를 직접 import하므로, 이 파일이 자기 기본값을 통째로 다시 써서 피한 **메인 앱 모듈 그래프가 그대로 딸려 옵니다.** 엑셀형 범위 복사가 필요해지면 **순수 부분을 먼저 떼어내는 것이 순서**입니다 |
| `graph_viewer.js` | 1254 | 그래프 서브그래프 뷰어(§6): stats 카드, 자동완성 검색, BFS 동심원 캔버스(무라이브러리), 팬·줌, Node Inspector, `?label=&identity=` 딥링크 |
| `trace.js` | 462 | trace.html 오케스트레이터(§6): `runTrace`(POST `/graph/trace`, seq 가드) → `renderReport`(그룹+타임라인 청크 렌더), 시드 칩·depth·시간범위, URL 동기화 |
| `trace_core.js` | 234 | 추적 순수 로직(무의존): `composeIdentity`(서버 G1 미러), `capSeeds`(상한 20), `buildTraceRequest`, `groupNodesByLabel`, `splitTimeline` |
| `trace_launch.js` | 111 | index 진입점: `initTraceEntry`/`refreshTraceEntry`(mapping-summary 판정), `openTraceForSelection`(선택 행→시드 변환) |
| `effort_meter.js` | 580 | **상호작용 계측기(§3.2)** — 핵심가치 #1 정본 계기의 **유일한 수집기**. 키·마우스·화면이동(상실/유지 분리) 원시 카운트 + 세션 id(`sessionStorage`), `PUT .../data/updates`에 선택 필드로 편승. 그리드·Enrichment·맵 에디터가 공유(**진입점 수를 적지 않습니다 — 화면이 늘면 늘어납니다**)(빌드에서 전용 청크로 분리 — 단일성 실측 가능) |

> `counter.js`는 Vite 템플릿 잔재(미사용).
> **클립보드는 `document`의 `copy`/`paste` 이벤트 + `e.clipboardData`가 정본이다**(`clipboard.js` `setupClipboardHandlers`). `navigator.clipboard`는 **보안 컨텍스트(HTTPS 또는 localhost/127.0.0.1)에서만 존재**하며, 운영은 사내망 평문 HTTP라 그곳에선 `undefined`다. 과거 `main.js`의 keydown에서 Ctrl+C를 가로채 `navigator.clipboard.writeText`로 복사하던 분기가 있었는데, ① 운영에서 `TypeError`(동기 throw라 `.catch()`도 못 받음)로 죽고 ② `preventDefault()`가 먼저 실행돼 정상 동작하던 `copy` 핸들러까지 굶겼다 → **삭제**(2026-07-27). **Ctrl+C/Ctrl+V를 keydown에서 가로채지 말 것.**

#### §2.1-bis 범위 선택은 키보드로도 된다 (`Shift`+방향키, 2026-07-30)

> **원칙: 손이 키보드를 떠나지 않게 한다.** 공수 계기(§계기 절)의 배점은 키 1 / 마우스 3이므로, **범위 드래그가 필요한 일괄 채우기는 이득의 대부분을 반납한다**. 그래서 `Shift`+방향키로 사각형을 잡는 경로를 추가했다(`grid.js` `extendRangeByKeyboard`). 격리 스택 실측: 같은 3셀 교정이 **셀별 개별 저장 4점×3건 = 12점 → 일괄 채우기 1건 6점**, 두 경우 모두 **마우스 0점**. N셀로 확장하면 개별 ≈ 5N, 일괄 ≈ N+3(N=100에서 500점 대 103점).
>
> **두 번째 범위 구현을 만들지 않았다.** 앵커는 기존 `state.dragStartCell`, 이동단은 `state.dragEndCell`이고 렌더는 `clipboard.isCellInRange`/`refreshSelectedRangeDiff`가 이미 그 사각형을 그린다. 쓰기 엔진도 기존 `ui.applyValueToSelectedRange`(Ctrl+Enter 경로)를 그대로 쓴다 — 새로 만든 것은 **선택 수단 하나뿐**이다.
>
> ⚠️ **`selectedCellsMap`에 확정(commit)하지 않는다** — Shift+클릭도 하지 않는 동작이고, `applyValueToSelectedRange`는 **맵을 먼저** 읽고 사각형은 폴백으로만 읽는다. 방향키마다 맵에 확정하면 낡은 키보드 사각형이 나중의 Shift+클릭 사각형을 **이겨서**, 사용자가 보는 선택과 실제 덮어쓰는 선택이 달라진다.
>
> ⚠️ **평범한 방향키는 범위를 해제한다**(정리 취향이 아니라 데이터 보호다). 해제하지 않으면 사용자가 방향키로 떠난 사각형이 살아남아 다음 `Ctrl+Enter`가 **본인이 선택했다고 믿지 않는 셀들을 덮어쓴다**. 마우스 경로는 이미 그렇게 동작한다(평범한 mousedown → `clearRangeSelection`) — 키보드가 맞추지 않으면 두 경로가 선택 상태를 두고 서로 다른 말을 한다.
>
> **알려진 한계**: 앵커는 사각형이 없을 때만 포커스 셀에서 새로 잡힌다. 사각형이 살아 있는 채 **프로그램적으로**(`element.focus()`) 포커스를 옮기면 재앵커되지 않는다 — 사람 조작(클릭·방향키)은 둘 다 해제 경로를 타므로 실사용에서는 드러나지 않지만, 스크립트 검증에서는 드러난다(2026-07-30 E2E에서 관측).
> ⚠️ 같은 결함이 남아 있는 곳(평문 HTTP에서 실패): `admin.js`(페이로드/트랜잭션 ID 복사). `map_editor.js` `copyGridToExcel`은 `7694b42`에서, `main.js` Smart Paste는 아래 §2.1-ter에서 해소됐다.

#### §2.1-ter 읽기는 버튼이 될 수 없다 — Smart Paste 걸쇠 (2026-07-30)

> **쓰기와 읽기는 대칭이 아니다.** 쓰기는 `document.execCommand('copy')`로 합성 `copy` 이벤트를 일으켜 `e.clipboardData`를 갈아끼울 수 있다(`map_editor.writeClipboardRich`). 읽기에는 그 수가 없다 — `execCommand('paste')`는 웹 콘텐츠에서 **차단**된다(격리 스택 실측: `false` 반환). 그래서 평문 HTTP에서 클립보드를 읽는 문은 **네이티브 `paste` 이벤트 하나뿐**이고, **버튼은 그 문을 열 수 없다.**
>
> 종전 `smartPasteViaIngestion`은 `navigator.clipboard.read`가 없으면 **같은 undefined 객체의 `readText()`를 부르는** 분기로 떨어졌다(`7694b42`가 복사 쪽에서 고친 것과 글자 그대로 같은 결함, 방향만 반대). 운영에서는 `TypeError: Cannot read properties of undefined (reading 'readText')`가 나고 바깥 `catch`가 그걸 「오류가 발생했습니다」로 뭉갰다.
>
> **현행 구조 — 걸쇠(latch) 하나로 두 동선을 합류시킨다.**
> - `state.smartPasteArmedUntil`(만료 타임스탬프) + `state.smartPasteArmedTable`(무장 시점의 테이블).
> - `clipboard.js`의 `paste` 핸들러가 **입력 필드 가드 직후, `gridApi` 가드보다 먼저** 걸쇠를 확인한다. 걸려 있으면 `registerSmartPasteHandler`로 등록된 `main.smartPasteFromPasteEvent`에 이벤트를 넘기고 종료한다(1회 소비). 걸려 있지 않으면 **평소의 범위 붙여넣기가 그대로 실행된다.**
> - `Ctrl+Shift+V`가 직행 동선. **`preventDefault()`하지 않는다** — 브라우저 자체 붙여넣기 명령이 `paste` 이벤트를 만들어야 읽을 수 있기 때문이다. 브라우저가 그 조합을 붙여넣기로 번역하지 않으면 600ms 뒤 걸쇠를 15초로 늘리고 「이어서 Ctrl+V」를 안내한다.
> - 버튼·컨텍스트 메뉴는 **읽지 못한다**. 보안 컨텍스트면 `navigator.clipboard.read()`를 먼저 시도하고, 아니면 걸쇠를 무장하고 **누를 키를 한 줄로 알린다**(새 패널·모드·모달 없음).
>
> ⚠️ **다중 포맷은 첫 `await` 이전에 전부 스냅샷한다.** `paste` 이벤트의 `DataTransfer`는 디스패치 중에만 읽히므로, 포맷 선택 모달을 `await`한 뒤 `getData()`를 부르면 **빈 문자열**이 올라간다(초록 토스트가 덮는 조용한 데이터 손실).
>
> ⚠️ **`navigator.clipboard`가 없다고 판단한 분기에서 다시 `navigator.clipboard`를 부르지 말 것.** 각 분기는 **자기가 부를 바로 그 메서드**로 가드한다. 이 규약은 `client2/scripts/check_clipboard_convention.mjs`(prebuild 게이트)가 강제하며, `main.js`는 유일하게 허용된 **읽기** 예외다.
> **상태 관리 주의:** `state.js`는 리액티브 스토어가 아닌 **평범한 싱글턴**. 변조 후 명시적 UI 리프레셔를 호출하는 수동 패턴. `admin.js`/`map_editor.js`는 `state.js`를 임포트하지 않고 자체 모듈 지역 변수를 사용.

### 3.1 실시간 동기화 무결성 — **되풀이되는 세 문제** (2026-07-27 이관)

> **출처·이관 사유:** 아래 세 문제는 ⚪ [spec/DATA_SYNC_SPEC §3](../_archive/DATA_SYNC_SPEC.md)에서 옮겨 왔다. 그 문서의 **해결책 서술은 제거된 PySide6 클라이언트의 것이라 전부 폐기**됐지만, **문제 자체는 프레임워크와 무관하게 되풀이된다** — "페이지 단위로 나눠 읽는 목록"에 "밖에서 들어오는 변경"이 겹치면 언제나 같은 세 가지가 생긴다. 문제 서술을 여기로 옮김으로써 원 문서에 남은 마지막 유효 내용이 없어졌다.

**문제 ①: 중복 행** — 가상/페이지 로딩으로 이미 들고 있는 행과 WS로 새로 들어온 같은 행이 겹쳐, 한 행이 두 번 보인다.
- **올바른 형태**: 행의 **정체를 명시적으로 선언**하고, 유입을 *삽입*이 아니라 **정체 기준 교체**로 처리한다. 로컬 배열 인덱스를 정체로 쓰면 반드시 어긋난다.
- **현행**: `grid.js`가 `getRowId: params => params.data?.row_id || params.data?.id`(:282)를 선언하므로 **AG-Grid가 정체를 강제**하고 `applyTransaction`이 같은 `row_id`를 갱신으로 흡수한다. 즉 이 문제는 **구조적으로 닫혀 있다** — 단 `row_id`가 항상 실려 온다는 전제 위에서다.

**문제 ②: 늦게 도착한 응답이 현재 화면을 오염시킨다** — 필터·검색·페이지를 빠르게 바꾸면 먼저 떠난 요청의 응답이 **나중에** 도착해 이미 바뀐 화면을 덮는다.
- **올바른 형태**: 요청마다 **세대(시퀀스/세션 id)**를 부여하고, **현재 세대가 아닌 응답은 전량 폐기**한다. "마지막에 도착한 것이 최신"이라는 가정이 이 부류의 원인이다.
- **현행**: 이 형태가 실제로 있는 곳은 `trace.js`(`runTrace` seq 가드)와 **`enrichment_reference_view.js`**(2026-08-11 — `requestSequence`, 렌더 직전 `sequence === requestSequence` 대조. ⚠️ 이 형태가 예전에는 죽은 `enrichment.js`의 참조 패널에 있었고 그 파일은 지금 어떤 HTML도 로드하지 않는다 — 인용 대상을 이 파일로 옮겼다)다. ⚠️ **메인 그리드 `api.fetchData` 경로에서는 대응 장치를 찾지 못했다**(2026-07-27 확인) — `state.pageCache`는 캐시일 뿐 세대 가드가 아니다. **미검증 항목**이며 판정은 [doc-auditor 소관](../process/DOC_OWNERSHIP.md).

**문제 ③: `total`이 외부 삭제 후 드리프트한다** — 다른 클라이언트나 인제션이 행을 지우면, 클라가 로컬로 카운트를 가감하는 순간 **현재 필터에 매칭되던 행이었는지**를 알 수 없어 총계가 틀어진다.
- **올바른 형태**: 총계를 **로컬에서 계산하지 말고**, 현재 필터를 실어 **서버에 다시 묻는다.** 이 값은 클라가 알 수 있는 종류의 값이 아니다.
- **현행**: 조회 경로(`api.fetchData`)는 매 요청 **서버가 준 `result.total`을 그대로 쓴다**(:200-209 — 올바른 형태). ⚠️ 반면 WS 삭제 수신부(`websocket.js` :236-240)는 `applyTransaction({remove})`만 하고 **`total` 재조회를 하지 않는 것으로 보인다** — 하단 `Matches: N`이 낡은 채 남는 경로다. **미검증 항목**, 위와 같이 doc-auditor 소관.

---

### 3.2 상호작용 계측기 (`effort_meter.js`) — 핵심가치 #1의 정본 계기

SSOT §1의 정본 계기 **「완료까지의 상호작용 점수」**를 수집하는 **유일한 수집기**입니다. 점수는 `키 1 · 마우스 3 · 컨텍스트 상실 이동 5`, 낮을수록 좋습니다.

> ⚠️ **이 파일이 클라이언트 유일의 수집기입니다.** 다른 페이지에 카운터·세션 id 생성기·라우트 표를 **복제하지 마십시오.** (중복 상수 목록은 U6 라운드에서 6건을 삭제한 전력이 있는 반복 함정입니다.) 페이지별 번들은 각자 모듈 인스턴스를 갖되 **`sessionStorage`를 통해 같은 세션을 공유**합니다.

| 항목 | 내용 |
|---|---|
| 계약 API | `startSession()` · `countKey(n=1)` · `countMouse(n=1)` · `countNav(from,to)` · `snapshot()` · `commit()` · **`commitIfRecorded(응답본문)`**(2026-07-29 수리 라운드) — **총괄 소유**. 이름·형태 변경 금지 |
| 계약 API (2026-07-29 승격) | `installGlobalListeners()`(페이지 전역 키/마우스 수집, 멱등) · `installNavLinkCounting(from)`(`<a href>` 위임 카운트) · `routeFromHref()`/`currentRoute()`/`ROUTES`/**`ROUTE_IDS`**(경로↔라우트 매핑과 **라우트 id 어휘**의 단일 표) · `getConfig()`(진단). **부가 export가 아니라 계약입니다** — 이것들이 없으면 페이지마다 리스너와 경로표를 손으로 복제하게 되고, 그게 바로 이 모듈이 막으려는 중복입니다 |
| 저장 | `sessionStorage['assy.effort']` = `{session_id, key, mouse, nav, nav_preserved}`. **원시 카운트만** 저장하고 배점은 서버가 조회 시점에 적용 — 배점을 바꿔도 과거 데이터가 새 배점으로 재해석됩니다 |
| 전송 | 기존 `PUT /tables/{t}/data/updates`에 **선택 필드** `effort`로 편승. **별도 텔레메트리 요청 없음.** 미계측(필드 없음)은 정상이며 `0`이 아닙니다 — 그래서 **누적이 하나도 없으면 `snapshot()`이 `undefined`를 반환**해 필드가 본문에서 아예 사라집니다(불변식 5) |
| 선언 원천 | `GET /api/effort/config` → `{weights, context_preserving_transitions}`. 페인트 규칙이 `binding`을 서버에서 받는 것과 같은 규율 — **서버가 유일 원천**. 단 **라우트 id 어휘는 클라 소유**(`ROUTE_IDS`)이므로, 서빙된 항목이 존재하지 않는 라우트를 지목하면 클라가 거절하고 큰 소리로 보고합니다(불변식 6) |

**깨지기 쉬운 불변식 6가지:**

1. **성공에만, 그리고 서버가 기록했을 때만 리셋.** 저장 실패 시 카운터를 유지해 계속 누적합니다 — 재시도 공수도 사람의 진짜 공수이기 때문입니다. 시도 시점에 리셋하면 **실패하는 저장이 싸 보입니다.** 2026-07-29 수리 라운드에서 게이트가 하나 늘었습니다: **200도 교정의 증거가 아닙니다.** 이미 같은 값이 들어 있는 셀에 같은 값을 다시 쓰면 서버는 `200 {change_count: 0}`을 주고 **공수 행을 쓰지 않습니다**. 거기서 리셋하면 그 시도에 든 공수가 지워지고, 화면이 안 바뀌는 걸 본 작업자가 제대로 다시 하면 **두 번 시도한 교정 — 제품에서 마찰이 가장 큰 사건이자 이 계기의 존재 이유 — 이 데이터셋에서 가장 낮은 점수를 기록합니다.** 그래서 `commitIfRecorded(응답본문)`이 서버의 `effort_recorded`를 보고 판단하고, 필드가 없으면(구 서버) 종전 동작으로 되돌아갑니다 — 영영 리셋하지 않으면 카운터가 무한히 자라는 그 자체가 결함이기 때문입니다.
2. **같은 탭 새로고침에서 생존.** 교정 도중 새로고침이 사람의 작업을 되돌리지는 않으므로 `sessionStorage`를 씁니다(탭이 닫히면 세션 종료).
3. **기본은 "상실(계산됨)".** 서빙 설정이 없거나·404거나·파싱 불가면 **모든 전이를 계산**합니다. 절대 "0점"으로 fail-open 하지 않습니다 — 목록에서 빠진 전이는 점수를 나쁘게만 만들지만, 잘못 포함된 전이는 **조용히 점수를 미화**합니다. 같은 이유로 **와일드카드(`*`)는 거부**합니다(무해한 리터럴로 남겨두면 설정 작성자가 적용됐다고 오해합니다).
3-bis. **분류는 절대 버리지 않는다** (2026-07-29 총괄 계약 보정). 면제된 전이도 `nav_preserved`로 **계속 셉니다** — `nav`(상실, 점수 대상)와 `nav_preserved`(유지, 현재 0점) 둘 다 원시 카운트입니다. 이 계기는 소급 산출이 불가능하므로, 수집 시점에 조용히 버린 전이는 나중에 판단이 바뀌어도 **영영 복구할 수 없습니다.**
   ⚠️ **여기서 정확히 무엇을 얻는지 (2026-07-29 QA 레인 B 정정 — 종전 서술은 과장이었습니다):** 어느 **버킷**에 들어갈지는 **수집 시점에** 그때의 허용목록으로 확정됩니다. 허용목록을 나중에 바꿔도 **이미 기록된 행은 재분류되지 않습니다.** 조회 시점에 재해석되는 것은 **배점뿐**입니다 — 두 버킷 다 원시 카운트이므로 `weights.nav_preserved`를 올려 과거 데이터를 **재채점**할 수 있습니다. 버리지 않는 것이 지키는 것은 그 재채점 가능성이지, 분류의 되돌림이 아닙니다.
4. **수집은 사용자에게 보이지 않음.** 새 UI·배지·토스트가 없습니다(집계 결과 한 줄은 어드민 Overview에 있습니다 — §5). 리스너는 전부 `capture` + `passive:true`라 **`preventDefault`를 호출할 수 없고**, `stopPropagation`도 하지 않습니다 — 과거 Ctrl+C keydown 분기가 `copy` 핸들러를 굶겼던 사고(§3 주석)를 구조적으로 차단합니다.
5. **부재는 0이 아니다 (보내는 쪽에서도).** 누적이 하나도 없으면 `snapshot()`이 **`undefined`**를 반환하고, `effort: snapshot()`은 `JSON.stringify`에서 키째 사라집니다. 서버는 명시적 0을 **측정된 0점 교정**으로 받아들이므로(그건 의도된 동작입니다 — 진짜 무공수 교정은 의미가 있습니다), 상호작용 없이 나간 저장은 **진짜 0점으로 기록되어 기준선을 유령으로 끌어내립니다**(실측: 진짜 교정 1건 37점 + 유령 1건 → `avg_score` 18.5). 가드를 7개 호출 지점이 아니라 **수집기 안**에 둔 이유는 여덟 번째 호출 지점이 잊을 수 없게 하기 위해서입니다. 판정은 **원시 4카운트**로 하며 점수로 하지 않습니다 — `nav_preserved`만 있는 세션은 오늘 0점이지만 실제로 일어난 일이고, 그 원시 카운트가 바로 재채점의 근거이기 때문입니다.
6. **존재하지 않는 라우트를 지목한 허용목록 항목은 조용히 죽지 않는다.** 서버는 항목의 *형태*만 검증하고 라우트 어휘를 모르므로 오타를 그대로 되돌려줍니다. SSOT가 예시로 든 `{"from":"doe","to":"dt_map"}`은 **아무것도 면제하지 못합니다**(실제 id는 `map_editor`·`map_editor:material`). 문제는 그 효과 — "전부 계속 계산됨" — 가 **정상 동작과 똑같이 보인다**는 점입니다. 그래서 클라가 `ROUTE_IDS`로 대조해 **거절 + `console.error` + `getConfig().rejected_transitions` 노출**을 합니다. 거절된 항목은 계산 쪽에 남으므로 편향은 과대계상(안전) 방향입니다. ⚠️ 새 서브컨텍스트로 `countNav`를 부르면 **같은 변경에서 `ROUTE_IDS`에도 등록**해야 합니다.
   같은 규율로 **항목 형식은 서버가 받는 것만 받습니다** — `{"from":..., "to":...}` 객체뿐이고, `"from>to"` 문자열 축약은 **거절**합니다. 서버(`resolve_context_preserving_transitions`)가 dict만 받고 나머지를 버리므로, 클라만 관대하면 **작성자가 쓴 항목을 한쪽은 지키고 한쪽은 버리면서 아무도 알려주지 않는** 상태가 됩니다. 생산자보다 관대한 소비자는 관용이 아니라 **선언되지 않은 두 번째 계약**입니다.
7. **관측 가능성은 소스가 아니라 빌드 산출물에 있어야 한다.** `getConfig()`는 `client2/src` 안에 호출자가 없어 번들러가 **트리셰이킹으로 dist에서 지워 버렸습니다**(실측: dist에서 `loaded:` 0건). 그러면 운영 현장에서 "허용목록이 비었다"와 "설정을 못 받았다"를 구별할 수 없는데, 그 구별이야말로 fail-closed 설계가 기대는 유일한 근거입니다. 이제 `startSession()`이 `window.__assyEffort = { getConfig, snapshot, ROUTE_IDS }`를 게시합니다(실제 참조이므로 셰이킹 불가) + 설정 fetch 실패 시 `console.warn` 1줄. 화면 요소는 여전히 0개입니다.

**계측 지점 — 교정 쓰기 경로 전부**에 `effort` 첨부 + **서버가 기록했을 때만** `commitIfRecorded()`:

| 페이지 | 쓰기 경로 |
|---|---|
| 메인 그리드 | `api.js`(단건 편집) · `main.js`(Tx 일괄 적용) · `ui.js`(범위 값 채우기) · `clipboard.js`(붙여넣기, 셀 비우기) — **5경로** |
| ~~Enrichment 컨베이어~~ | ~~`enrichment.js` `saveCurrent` — **1경로**~~(2026-07-29 추가). 🔴 **[2026-08-11] 이 경로에 UI가 없다** — `enrichment.html`이 삭제돼(`ab36fab`) `saveCurrent`를 부를 화면이 없다. `effort_meter.js`의 `ROUTES.ENRICHMENT`/`'enrichment:rule'`은 **의도적으로 남아 있다**(허용목록 검증기이지 라이브 내비게이션 집계가 아니라서, 지우면 오히려 알 수 없는 항목이 됨) — 그러나 계측 자체는 죽었다. 결손 보정은 지금 그리드 직접 편집(F3 값 제안 셀 에디터)의 **5경로 계측에 흡수**된다 |
| 맵 에디터 | `map_editor.js` Push — **1경로**(map-pm 소관) |
| 읽기 전용 화면 (2026-07-29 추가) | `admin.js` · `graph_viewer.js` · `trace.js` — **교정 쓰기 0경로**이므로 `effort` 페이로드를 싣는 곳이 없습니다. 대신 `startSession`+`installGlobalListeners`+`installNavLinkCounting`만 배선합니다. 이유는 **대칭**입니다: 종전에는 `grid → graph`는 세고 `graph → grid`는 안 세서, 읽기 화면으로 나갔다 돌아오는 왕복이 **실제 비용의 절반만** 기록됐습니다(실측: `/graph.html`에서 🏠 Main 클릭 → 카운터 바이트 단위로 동일). 미화 방향이고, 다시 모을 수 없는 기준선에서 그건 불변식 3이 금지하는 방향입니다 |

**이동 계측:** 그리드 — 내비 앵커 4건(위임) + 테이블 전환 + 뷰모드 전환 + `navigateToLog` + 추적 새 탭. ⚠️ **[2026-08-11] "Enrichment 배지"·"Enrichment 페이지의 「메인으로」 앵커 2건 + 규칙 전환"은 둘 다 죽었다** — 배지는 삭제됐고(`5116f67`) 페이지 자체가 없다(`ab36fab`). 그리드 사이드바 참조뷰(`enrichment_reference_view.js`)는 읽기 전용 조회이고 effort 계측을 새로 배선하지 않았다(교정 쓰기가 아니므로 SSOT §1 계기의 범위 밖). 어드민·그래프·추적 — 내비 앵커(위임) 전량.

> ⚠️ **테이블/규칙 전환은 `switchTable()`·`selectRule()` 안이 아니라 사용자 핸들러에서 셉니다.** 두 함수는 부팅 자동선택·딥링크·`navigateToLog`에서도 호출되는데 그건 사용자가 이동한 것이 아니라서, 함수 안에서 세면 오계수가 납니다. (새로고침 버튼처럼 같은 대상을 다시 읽는 것도 이동이 아니므로 세지 않습니다.)

> 카운트 규칙(둘 다 **미화되지 않는 방향**으로 선택): 마우스는 `click`이 아니라 **`mousedown`**(범위 드래그는 `click`을 발생시키지 않지만 실제 누름 1회입니다), 키는 **자동 반복 포함 전부**이되 **단독 수식키**(Shift/Ctrl/Alt/Meta)는 제외(코드는 비수식키에서 1회 계산).
>
> 검증 하니스: `client2/tests/effort_meter_harness.mjs` (vm 샌드박스, node_modules 불필요, **131 단언**). **변이 검사 8종 포함** — ① `snapshot()`이 리셋하도록 ② 설정 실패 시 fail-open 하도록 ③ 면제 전이를 버리도록 ④ 빈 스냅샷을 0으로 실어 보내도록 ⑤ `effort_recorded`를 무시하고 항상 리셋하도록 ⑥ 미지의 라우트 id를 조용히 받아들이도록 ⑦ 문자열 축약을 다시 받아들이도록 ⑧ 진단을 `window`에 게시하지 않도록 일부러 고장 낸 버전을 넣어, 하니스가 **실제로 잡아내는지** 확인합니다. 별도로 **§8b 배선 감사**가 소스 레벨에서 전 페이지를 훑습니다 — 교정 경로가 bare `commit`을 다시 import 하는가, 어떤 페이지가 수집기를 아예 import 하지 않는가(B-F1 재발), 읽기 화면이 자기 라우트가 아닌 id로 세는가. 이 감사도 세 가지 역주입으로 자기 점검합니다. 변이가 소스 드리프트로 적용되지 않으면 **에러를 던집니다** — 조용한 no-op이 되면 "고장 난 버전이 통과"해 검사가 무의미해지기 때문입니다(실제로 한 번 발생해 이 가드를 넣었습니다). 맵 에디터 배선은 `client2/tests/effort_instrument_harness.mjs`(28 검사, 변이 9종 — 실제 `pushMapData` 본문을 소스에서 들어올려 실행).

### 3.3 값 제안 셀 에디터 — **`Enter` 한 번이 채택이고 확정이다** (F3 · `77a2c15` → Escape 시정 `d5f75a8` · 2026-07-30)

`value_suggest.js`의 `SuggestCellEditor`가 **`string` 선언 컬럼**의 셀 에디터를 대체합니다(`grid.js:313-323`). 타이핑이 목록을 좁히고, **`Enter` 한 번이 후보 채택과 셀 확정을 동시에** 합니다.

- **왜 한 번으로 끝나는가 — 타이머가 아니라 프레임워크의 호출 순서입니다.** AG-Grid의 `processCellKeyboardEvent`는 `suppressKeyboardEvent`를 `cellCtrl.onKeyDown`보다 **먼저** 호출하고, `onKeyDown`의 Enter 갈래가 `stopEditing → cellEditor.getValue()`를 부릅니다. 그래서 `handleEditorKey`가 `'accepted'`를 돌려주면 후보는 **같은 이벤트 디스패치가 확정에 도달하기 전에** 이미 입력에 들어가 있습니다. `grid.js`가 그때 `false`를 돌려주는 것은 포기가 아니라 **확정**입니다. 마이크로태스크도 setTimeout도 개입하지 않습니다.
- **범위는 의도적으로 좁습니다.** `number`는 `agNumberCellEditor`(그 에디터가 나르는 숫자 검증에 `valueSetter`가 의존), `datetime`은 엔드포인트 자신이 거부합니다. 서버는 숫자 접두도 지원하므로 넓히는 것은 **그 술어 한 줄의 변경**이지만, 에디터 안에 숫자 검증을 다시 구현하는 별개 라운드입니다.
- **여는 최소 길이는 1**입니다 — 서버 기본 `min_prefix_length: 0`보다 **엄격한 쪽**으로 고정했습니다. 빈 접두에서는 첫 후보가 컬럼 전체 값 집합에서 뽑힌 임의의 `limit`개 창이라 **`Enter`의 의미가 사라집니다**(고른 것이 아니라 표본입니다). 방향은 언제나 서버보다 엄격하게 — 운영자가 `min_prefix_length`를 **올리면** 그 선언은 그대로 존중됩니다(`columnFloor`).
- **요청 한도는 12**이고 그 수는 두 갈래로 부하가 걸립니다. ① 위치 `k`의 후보를 고르는 비용은 `k`타(화살표 `k-1` + Enter)이므로 **`N-1`번째 뒤의 후보는 접두를 한 글자 더 치는 것보다 항상 비쌉니다**(이 그리드가 담는 12자 부품번호에서는 ~11 이후가 그렇습니다). ② 조회 비용이 `t = 0.84ms + 0.61ms × (limit+1)`로 **테이블 크기가 아니라 요구한 한도의 함수**입니다(측정 2026-07-30 · 0.61ms의 97%가 Python/SQLAlchemy/프로토콜). 한도 20은 중위 15.3ms로 예산 초과, 12는 ~8.7ms입니다. ⚠️ **꼬리는 예산 밖입니다** — p95 예측 ~11.8ms. 중위만 인용하고 꼬리를 빼면 자기에게 유리한 수만 말하는 것입니다.
- **진단은 `window.__assySuggest`**(`getSuggestStats`/`resetSuggestStats`/`resetSuggestLearning`). 소스에만 있는 계측은 브라우저 E2E에서 존재하지 않는 것과 같습니다(`847ceaf`가 닫은 격차).

#### `Escape`의 뜻은 하나이고, **시계에는 표결권이 없다**

🔴 이 계약이 **먼저 깨진 뒤에 세워졌다는 사실이 계약의 일부입니다.** 원래 `Escape` 갈래는 `listOpen`을 물었고, 누른 순간 목록이 화면에 있었는지는 `DEBOUNCE_MS + 왕복시간`의 함수였습니다. 그래서 **한 키에 정반대 결과 둘**이 붙었습니다 — 목록만 닫고 글자를 남기거나, AG-Grid로 떨어져 **글자를 버리거나**. 화면에는 둘을 구별할 것이 아무것도 없었습니다(스피너가 **의도적으로** 없습니다). 게다가 닫아도 상태를 남기지 않아서, 비행 중이던 답이 도착하면 목록이 첫 행 하이라이트로 되살아나 다음 `Enter`가 **운영자가 고르지 않은 값**을 썼습니다.

**지금의 계약** — 판정하는 술어는 `suggestionsEngaged`(이 에디터가 **자기 입력에 대해** 물어본 적이 있는가. 운영자의 타이핑이 세우고, 한 편집 안에서 **단조**입니다):

| 누름 | 조건 | 결과 |
|---|---|---|
| `Esc` #1 | 이 셀에서 제안이 **engaged** | **목록만 닫습니다.** 타이핑한 글자는 남고, 예약된 질의는 취소되고, 비행 중인 요청은 **중단(abort)되고 플래그가 서서** 늦은 답이 목록을 되살리지 못합니다 |
| `Esc` #2 · 또는 engaged가 없는 셀의 `Esc` #1 | — | `'pass'` = AG-Grid의 평범한 **편집 취소**. 그런 셀은 실제로 평범한 텍스트 필드입니다 |

- **왜 "지금 요청이 떠 있는가"로 판정하지 않는가**: 그 술어 자체가 왕복시간의 함수라, 타이밍 이음매를 **없애는 게 아니라 옮기는 것**입니다("답이 Escape보다 먼저 왔나"로 이름만 바뀝니다).
- **대가를 정직하게 적습니다**: 제안 가능한 컬럼에서 **편집 취소에 `Esc`가 두 번 필요할 수 있습니다.** 그 키 하나보다 **결정성**이 값어치가 있다고 판단해 그쪽을 골랐습니다.
- ⚠️ **남아 있는 비균일성 하나** — engaged가 한 번도 없었던 컬럼(미선언·서버 플로어 미달·쿨다운 중)에서는 **첫 `Esc`가 곧 취소**이고, **화면에는 그 차이를 보여 주는 것이 없습니다.** 숨기지 않고 적어 둡니다.
- `↓`는 `Esc`로 닫은 목록을 **다시 엽니다**(추가 타이핑 없이). `↑`는 열지 않습니다 — 자기가 쓴 글자를 지키려는 운영자에게 **목록을 되살리지 않는 방향**을 하나 남겨 둡니다.
- **IME가 최우선입니다.** 조합 중(`isComposing` 또는 `keyCode === 229`)의 `Enter`는 IME 것입니다(한글 음절 확정). 이 제품은 한국어로 타이핑되므로, 그 `Enter`를 가로채면 글자를 닫으려던 사람에게 후보를 대입하게 됩니다.
- `Tab`은 `Enter`와 **같은 경로**(채택 후 이동)이고, `Ctrl+Enter`는 후보를 입력에 채택한 뒤 `'pass'`로 떨어뜨려 `grid.js`의 기존 범위 일괄 채우기가 **채택된 값**을 읽습니다 — 그쪽도 한 번 누름입니다.
- 제안 불가 컬럼(미선언·`datetime`·부재, 또는 `unavailable_reason`)은 **목록 없이 평범한 텍스트 에디터로** 동작합니다. 토스트도 에러도 없습니다 — 제안할 수 없는 컬럼에서 망가진 드롭다운은 드롭다운이 없는 것보다 나쁩니다.

> 점검 절차는 [FEATURE_CHECKLIST §2.0](../qa/FEATURE_CHECKLIST.md), 회귀 그물은 §2.1의 `check:suggest-keys`.

### 3.4 가상 조인 컬럼 — **그리는 순간 그것은 쓰기 대상이다** (2026-07-31 `4b50135`)

`/schema`의 `virtual_columns`([backend §2.2](./backend.md))를 그리드에 **덧붙여 그린다.** 목록은 `state.currentVirtualColumns`에 **원문 그대로** 두고, 저장 컬럼 목록(`state.currentColumns`)에 **병합하지 않는다** — 그 배열의 뜻은 「이 테이블이 저장하는 컬럼」이고 소비자 넷(검색 드롭다운·복사 술어·편집 가능성·맵 push 게이트의 「보호 없는 데이터 컬럼」 계수)이 그 뜻에 기댄다.

🔴 **그러나 병합하지 않는 것으로는 쓰기가 막히지 않는다 — 이 라운드의 핵심 정정이다.**
「목록에 안 넣으면 붙여넣기 대상이 안 된다」는 **거짓**이었다. 붙여넣기 경로는 `currentColumns`를 **읽지 않고** 배치를 **그리드 컬럼 id**에서 만들며, 유일한 관문은 하드코딩된 시스템 컬럼 배열이다. 즉 **컬럼이 렌더되는 순간 그것은 붙여넣기 대상**이고, 어느 목록에 사는지는 무관하다. 그리고 그 컬럼 하나가 겹치면 서버 거부가 **배치 단위**라 **붙여넣은 블록 전체가 400**이 된다. 같은 모양의 문이 둘 더 있다 — **delete로 비우기**와 **Ctrl+Enter 일괄 채우기**.

- **판정은 술어 하나**: `state.isVirtualColumn(colId)`. 사이트마다 배열에 이름을 더하는 방식이 불가능한 이유는 가상 컬럼의 **이름이 사이트별 선언**이기 때문이다. 🔴 **이 술어는 강제가 아니다** — 강제는 서버의 `crud.refuse_virtual_join_columns`이고, 이쪽은 **되돌아올 400을 제안하지 않기** 위한 것이다.
- **복사는 반대 방향으로 손봐야 했다.** `getRangeSelectedTSV`는 컬럼 창 안에서 `currentColumns`로 **거른다** — 그대로 두면 복사한 블록 **가운데서 컬럼이 빠지고 오른쪽 전부가 한 칸씩 밀려**, 선택한 것이 아닌 직사각형을 돌려준다. 복사는 읽기이므로 **두 복사 술어는 가상 이름을 받아들인다.**
- **정렬은 비교기를 붙였고, 필터는 일부러 껐다.** `number` 선언 컬럼의 값 정의역에는 `unresolved_label`이 섞이는데, AG-Grid 기본 비교는 `(50, '미상')`에서 **양쪽 비교가 모두 거짓**이라 미해결 행이 모든 숫자와 동률이 되어 결과 전체에 흩어진다. 필터는 `filter: false`다 — 이 그리드의 컬럼 필터는 **서버측**이고 서버는 이 컬럼을 모르므로, 조건이 하나도 성립하지 않아 **페이지가 필터 없이 돌아온다**(클라 행 모델만 걸러 화면은 필터된 것처럼 보이고 `Matches:`와 페이지 수는 전량 그대로다 — **반만 동작하면서 아무 말도 안 하는 필터**).
- **셀 읽기는 저장 컬럼과 같은 함수를 쓴다**(`rawCellValue`/`numericDisplayValue`). 서버 `attach`가 조인 셀을 `fetch_and_merge_metadata`와 **같은 키**로 채우므로 두 번째 리더가 필요 없다. `numericDisplayValue`가 **강제 변환하지 않는 것**이 계약이다 — `Number('미상')`은 `NaN`이라 가드가 원값을 돌려주고 라벨이 그대로 셀에 닿는다.
- **헤더는 `🔗`, 색은 시스템 컬럼과 같은 회색**(`cell-system-readonly`). 운영자에게는 사실이 동일하다 — **이 칸은 타이핑할 수 없다.** 툴팁이 `right_table`과 선언 이름을 싣는다: 서버의 쓰기 거부 문구는 「조인 원본에서 고치라」고만 하고 **어느 테이블인지 지목하지 못하므로**, 그 답이 화면에 있는 자리는 여기뿐이다.
- **⏳ 열려 있는 것 둘**(커밋 트리 `77d27d3` 기준 — ⚠️ 둘 다 작업 진행 중이니 인용 전 소스 확인) — ⓐ **CSV export(`GET /tables/{t}/export`)에는 가상 컬럼이 실리지 않는다.** 그 라우트는 `attach`를 부르지 않으므로 **화면에 보이는 컬럼이 추출물에는 없다.** ⓑ **`filter: false`라 `미상` 행을 찾을 방법이 없다.** 서버가 그 컬럼을 아는 형태가 필요해 **클라만으로는 못 고친다.** 둘 다 미해결이며 정본 목록은 [config/virtual_join_rules §9](../guide/config/virtual_join_rules.md).

> 회귀 그물 `client2/tests/virtual_column_render_harness.mjs`(§2.1 `check:harnesses`가 발견식으로 돌린다). 점검 절차는 [FEATURE_CHECKLIST §2.2-bis](../qa/FEATURE_CHECKLIST.md).

---

### 3.5 기동 순서 — **실시간 채널은 무엇에도 걸려 있지 않다** (2026-08-04)

`init()`의 **첫 문장**이 `initWebSocket()`이다. 종전에는 `await checkServerHealth()` → `await loadTables()` **뒤 마지막 문장**이었고, 재연결 사다리 전체가 `initWebSocket` **안에** 살기 때문에 그 줄에 닿지 못한 페이지는 **세션 내내 소켓도 재시도도 없이** 돌았다. 사용자 신고(2026-08-04)의 증상이 정확히 그것이다 — Network 탭에 실패한 `/ws`가 아니라 **`/ws` 요청 자체가 없었다.**

🔴 **평범한 reject는 이 결함이 아니다.** 두 호출부 모두 `try/catch`가 있어 `fetch` 거절만으로는 소켓이 살아남는다. 실제로 재현된 경로는 셋이고, 그중 둘은 **아무 소리도 내지 않는다**:

1. **catch 블록 자신이 던진다.** 두 catch가 DOM 핸들(`elements.performanceLog`·`elements.serverStatus`·`elements.tableSelect`)을 **가드 없이** 썼다. 핸들이 `null`이면 **처리된 장애가 그 자리에서 미처리 거절로 바뀐다** — 코드가 조심하려던 바로 그 순간에. 이 저장소에는 실측 전례가 있다(`elements` 게터 둘이 `index.html`에 **한 번도 존재한 적 없는** id를 가리켰다). ⚠️ **2026-08-04 현재도 게터 넷**(`globalSearch`·`searchCols`·`ingestFileBtn`·`smartPasteBtn`)**이 `index.html`에 없는 id를 가리킨다** — 전부 사용처가 가드돼 있어 지금은 안 터지지만, 이 부류가 살아 있다는 증거다.
2. **`fetch`가 영원히 settle하지 않는다.** 끊긴 백엔드나 사내 프록시에서 `await`는 **거절하지도 던지지도 로그를 남기지도 않는다.** 신고 증상(요청 없음 + 콘솔 조용함)과 가장 잘 맞는 경로다.
3. `init()`의 나머지 셋업(`setupEventListeners`·`setupClipboardHandlers`·`setupDragAndDrop`…) **어디서든** 던지면 같은 결과였다. 그래서 소켓은 「좀 더 앞」이 아니라 **전부보다 앞**이다.

**순서를 앞당기면서 지켜야 했던 것**: `onopen`은 테이블 선택기가 비어 있으면 `loadTables()`로 부트스트랩한다. 소켓이 먼저 뜨면(로컬 핸드셰이크 실측 중앙값 2.54ms) 그 부트스트랩이 `init()`의 `loadTables()`와 **겹친다** — `switchTable`이 두 번 돌아 스키마 로드도 그리드 재생성도 두 번이 된다. 그래서 `api.js`에 **in-flight 걸쇠**(`tablesLoadInFlight`)를 뒀다: 두 번째 호출은 **버리는 게 아니라 같은 프라미스를 공유**한다(`onopen`이 결과를 `await`하므로 버리면 목록이 없는 채 진행한다). 완료 시 반드시 해제된다 — 해제되지 않는 걸쇠는 동시 호출만 보면 정상과 구분되지 않고 세션 내내 목록을 얼린다.

> 회귀 그물 `client2/tests/startup_socket_gate_harness.mjs` — 실제 `init`/`checkServerHealth`/`loadTables`/`initWebSocket`을 vm에서 잘라내 가짜 소켓·가짜 `fetch`로 구동하고, **`new WebSocket(...)`이 실제로 일어났는지**를 채점한다(Network 탭에서 없던 바로 그 사건). 변이 9개 전원 검출, 그중 M9는 **라운드 이전 코드 전체**(소켓 마지막 + 가드 없는 catch)를 되돌려 catch-throws 경로를 재현한다.

#### 3.5-bis 아무것도 영원히 기다리지 않는다 — 연결 감시견과 **세 번째 상태**

소켓을 먼저 띄운 것만으로는 절반이다. **블랙홀 경로**(사내 프록시·끊긴 백엔드)에서 `WebSocket`은 `onopen`도 `onclose`도 부르지 않으므로, 재연결 사다리가 **한 번도 발화하지 않은 채** 세션이 끝난다.

- **감시견 `armConnectWatchdog`** — 소켓 생성 직후, 핸들러를 붙이기 **전에** 무장한다. 상한은 `WS_CONNECT_TIMEOUT_MS = 8000`(`config.js`). 발화하면 `abandonConnectingSocket()`이 **`onopen`/`onclose`/`onerror`/`onmessage`를 먼저 `null`로 만든 뒤** `close()`한다(안 그러면 정리가 `onclose`로 재진입한다) → 평범한 백오프 사다리로 복귀. **별도 복구 기계장치는 없다** — 발화는 「실패한 시도 한 번」일 뿐이다.
- 근거(주석에 기록): 로컬 핸드셰이크 중앙값 **2.54ms**·최대 4.15ms라 8초는 약 1,900배이고, 이 저장소에서 측정된 가장 느린 지연(수명주기 기동 3,094ms, n=324)에도 2.6배 여유가 있다. 최악 복구는 8초 + 사다리 한 칸(≤ `WS_RECONNECT_CEILING_MS` 5000) ≈ 13초.
- 관련 상한 하나 더: `WS_CONNECT_STALE_MS = 1000` — 깨우기 신호(`visibilitychange`·`online`)가 **CONNECTING 소켓을 버려도 되는** 최소 경과 시간(`wakeNow`).

🔴 **배지가 같은 글자로 덮고 있던 세 상태가 갈라졌다.**

| 실제 상태 | 지금 보이는 글자 | 어디서 |
|---|---|---|
| 소켓을 **만든 적이 없다**(`init()`이 `initWebSocket` 전에 죽음) | `WS: Connecting` — **`index.html`의 초기값이 손대지 않은 채 남은 것** | `client2/index.html` |
| 만들었고 **협상 중**이다 | `WS: 연결 시도 N` | `websocket.js` (`status-badge`) |
| 만들었는데 **경로가 응답을 삼켰다**(감시견 발화) | `WS: 응답 없음 N회` | `websocket.js` (`status-badge offline`) |

- 대비되는 종점 둘은 종전대로다 — `WS: CONNECTED`(`online`) / `WS: DISCONNECTED`(`offline`).
- 🔴 **첫 줄이 진단의 핵심이다**: `WS: Connecting`은 이제 **「아무도 이 배지를 쓴 적이 없다」**는 뜻이고, 그것이 곧 §3.5의 결함 서명이다. 반대로 **서버가 거절한 것**(`WS: DISCONNECTED`)과 **경로가 삼킨 것**(`WS: 응답 없음`)은 전혀 다른 고장인데 종전에는 화면이 같은 글자를 보여 줬다.
- ⚠️ **초기값을 「연결 안 함」류의 다른 문구로 바꾸지 마십시오** — 세 상태 중 하나가 *「JS가 그 줄에 닿지 않았다」*로 읽히는 것이 이 설계의 요점입니다.

---

## 4. 맵 에디터 (`map_editor.js` + `map_key.js` + `split_registry_row.js`)

> ⚠️ **맵 에디터는 더 이상 파일 하나가 아닙니다**(2026-08-04 R1/R2). 아래 표는 **기능 영역**이고 파일 경계와 일치하지 않습니다 — 심볼의 현재 거처는 [CODE_MAP](./CODE_MAP.md)을 grep해서 확인하십시오. 분할은 진행 중이라 **다음 라운드에 또 하나가 빠져나갑니다.**

| 영역 | 대표 함수 |
|---|---|
| 렌더링 | `renderGridCanvas`/`scheduleRenderGridCanvas`, `updateCellStyles`, `renderLegendTable`, `updateNotchPosition` |
| 좌표 변환 | `getDieIndex`/`getCanvasCellFromDieIndex`, `getDbCoords`/`getCanvasCellFromDb`, `getWaferBoundingBox`, `getTransformedPhysicalConfig`, `isCellInsideWafer{,Fast}` · **재배치 반응 `reseatCellsToStoredCoords`**(기록 `cellsSeatedUnder`/`seatingSnapshot`) <br>⚠️ **2026-07-31 개명**(`35e84c3`, 전 호출 지점): 구 `getPhysicalCoords`는 mm가 아니라 **칸 번호**를 돌려주고 구 `getVisualCoords`는 **저장 좌표**를 돌려줬다. 대응표는 [MAP_EDITOR_SPEC §1-bis](../spec/MAP_EDITOR_SPEC.md) <br>🔴 **[2026-08-06 `62520b9`] 프레임은 이제 인자다 — 모듈 바인딩 `physFrameOverride`와 창 함수 `withPhysFrame`은 삭제됐습니다**(비주석 언급 0건). 아래 §4의 오버레이 행이 「창을 연다」고 적고 있었고 그 문장은 이제 거짓입니다. 프레임을 **첫 인자로** 받는 함수는 이 표의 변환 함수들만이 아니라 규격 읽기(`physNum`·`gridDimNum`·`physDeclaration`·`geometryIsAutoRegistered`)·격자(`frameDieLattice`·`frameDimError`·`resolveFrame`)·기록(`seatingSnapshot`·`frameChosenFrom`)까지 걸칩니다 — **수를 적지 않는 이유는 다음 라운드에 또 늘기 때문**이고, 현재 목록은 `grep -n "^function [a-zA-Z_]*(frame" client2/src/map_editor.js`가 답합니다. <br>🔴 **`null`과 `undefined`는 다른 답입니다**(`physNum:1459`): `null` = 「프레임 없음, 화면 컨트롤을 읽어라」는 **의도된 답**(메인 로드), `undefined` = **호출자가 잊었다** → `throw`. 모듈 바인딩일 때는 창이 자동으로 적용돼 잊는 것이 불가능했고, 인자가 되면서 처음으로 가능해졌습니다 — 조용히 화면으로 폴백하면 **캔버스는 완벽하게 그려지고 저장 좌표만 틀립니다.** |
| **웨이퍼 mm** (`cd3e0f4`) | `dieIndexToWaferMm`(다이 인덱스 → 그 다이 **중심**의 절대 mm) / `waferMmToDieCell`(역함수 — **나머지를 버리지 않는다**: 몫이 칸, 나머지가 칸 **안에서의** mm) · `projectCellsToWaferMm` · `seatWaferMmInFrame`. <br>🔴 **종전 이 자리는 「`mm`은 일부러 비어 있다」였고 그것은 이제 거짓입니다** — 기준 가치 6)(서로 다른 메타의 오버레이)이 착지하면서 클라가 실제 밀리미터 공간을 갖게 됐습니다. <br>🔴 **mm는 세 번째 좌표 변환이 아닙니다.** 회전·반전·오프셋은 전부 `getDieIndex` 안에서 끝나고 여기서 더하는 것은 **단위 환산 하나**(칸 번호 × 피치)뿐입니다 — 오버레이 전용 기하식을 쓰지 않는다는 계약이 이 구조입니다. <br>🔴 **칸 안 나머지는 절대 길이라 피치에 의존합니다** — 7mm 칩 안의 3mm와 15mm 칩 안의 3mm는 다른 자리이므로, 칸 안 좌표는 맵 사이에서 그대로 못 옮기고 **반드시 절대 mm를 거쳐 다시 나눠야** 합니다. <br>⚠️ **저장 좌표는 여전히 칸수이고 mm가 아닙니다**(사용자 판정) — mm 공간이 생긴 것과 저장 좌표의 뜻이 바뀐 것은 **다른 얘기**입니다. 칸수에 피치를 곱해 mm로 읽으면 없는 결함이 만들어집니다([MAP_EDITOR_SPEC §1의 0)](../spec/MAP_EDITOR_SPEC.md)). |
| 드래그 선택/페인팅 | `initMouseDragEvents`, `handleCellClick`, `fillSelectedCells`, `remapGridValues`, `autoPaintE1E2` |
| 엑셀 복사 | `copyGridToExcel()` — TSV 클립보드 |
| 메타/레전드 | `renderMetadataInputs`, 프리셋 `/api/map-presets`, 레전드 `localStorage`(`map_legend_{table}`) |
| 데이터 동기화 | `loadExistingMap()`(REST pull), `pushMapData()`(REST push) |
| **페인트 잠금** (M2) | `fetchPaintRules`(GET `/api/maps/paint-rules` — 선언 정본이 서버로 이동, 구 `'F'` 하드코딩 대체), **`isProtectedFCell`**(편집 가능 판정의 **단일 관문** — 모든 편집 경로가 여기로 수렴), `updatePaintLockIndicator`. 404/405만 "선언 없음", 네트워크·5xx는 직전 잠금 유지(**조용한 fail-open 제거**). ⚠️ 콜드 스타트(첫 조회 실패)는 아직 열린 채 시작 — QA C4 미해소 |
| **오버레이 레이어** (`7d931dc`) | **좌표 변환은 클라 단일 구현이다** — `소스 원본(x,y) →[소스 메타 프레임]→ 물리 →[현재 화면 컨트롤]→ 셀`. `addOverlayLayer`가 `/tables/{src}/data`(원본 좌표) + `wafer_map_metadata` 2건을 읽고 투영한다. 오버레이 전용 기하 코드는 없다 — 소스 맵의 프레임을 **인자로 넘겨** 메인 로드와 같은 `getCanvasCellFromDb` → `getDieIndex`를 돌린다(`projectCellsToWaferMm`). 🔴 **[정정 `62520b9`] 종전 이 자리는 「`withPhysFrame`(프레임 창)으로 규격 읽기 지점만 갈아끼운다」였고 그것은 이제 거짓이다** — 그 창 함수와 모듈 바인딩 `physFrameOverride`는 삭제됐다. 바뀐 것은 **읽는 지점이 아니라 전달 방식**이고, 답은 하나도 안 바뀌었다(호출자가 창이 읽던 바로 그 값을 같은 동기 시점에 넘긴다). 얻은 것: **한 프레임의 계산이 다른 프레임의 계산을 흔들 수 없다** — 모듈 상태였을 때는 `await` 하나가 뒤집힌 프레임을 남의 코드에 보여 줄 수 있었고, A→B→A 교차 호출은 원리상 시험 불가능했다. **소스와 타깃의 피치가 다르면 다이 인덱스로는 못 겹치므로**(같은 인덱스가 같은 물리 자리가 아니다) `projectCellsToWaferMm`이 절대 웨이퍼 mm 항목을 만들고 `seatWaferMmInFrame`이 그것을 타깃 프레임의 칸에 앉힌다(§4의 웨이퍼 mm 행 — 규칙 6). 🔴 **mm 항목은 반올림 *전* 연속값에서 만든다** — 반올림된 다이 인덱스에서 되만들면 칸 미만 잔여가 빠져 모든 셀이 밀린다(실측: 한 픽스처에서 1,836칸 중 1,789칸이 틀린 칸에 앉았다). `currentGeomSignature`(물리 6종 포함)/`syncOverlayGeometry`가 화면 규격 변경을 추종하고, `overlayAlignChip`은 `align.origin`으로만 판정한다. `importOverlayToGrid`는 `gridData`로만 반영(서버 쓰기 없음). **메인 로드와 코드 경로 완전 분리** — `selectedTable`·`gridData`·legend·규격·brush를 쓰지 않고 `switchTable`을 경유하지 않는다. 기준이 바뀌면 오버레이는 **해제**된다(맵 로드·테이블 전환·프레임 진입 — **수를 적지 않는다**) |
| **오버레이 점의 색** (2026-08-04 `376e1c8`→`41b17ee`) | `legendColorForValue(val)` → `overlayMarkerFill(list)` → `paintOverlayDot(...)`. 🟩 **legend가 유일한 색 출처**이고 폴백은 셋뿐이다 — 열린 맵의 legend 행 → 서버가 서빙한 `default_legend`(`declaredLegendRow`) → **`null`(안 칠함)**. 🔴 **`pickUnusedColor()`·`LEGEND_PALETTE`는 여기서 안 부른다**(지어낸 색은 선언된 색처럼 읽힌다 — 하네스가 소스 대조로 0건을 채점). 미선언 값은 **속이 빈 링 점**이고(원호는 그대로 그리고 흰 후광 + 레이어 색으로 두 번 스트로크, `fillStyle`은 **대입조차 안 한다**), 한 칸에 값이 여럿이면 **값이 같아도** 안 칠한다(대표를 고르지 않는다). 부재의 두 이유는 픽셀이 아니라 칩으로 가른다 — `overlayFanChip`(여럿) / **`overlayLegendChip`(`범례 밖 N종` — 처방까지 말한다)**. 계약 정본 [MAP_EDITOR_SPEC §5.4-bis](../spec/MAP_EDITOR_SPEC.md) |
| **유효 다이 지정** (2026-08-04 `6420ad0` → **`5b15c24`**) | 저장 테이블이 **`valid_die_ref` 하나로 고정**(`VALID_DIE_TABLE`)돼 테이블 `<select>`가 사라졌다. 🔴 **[정정 `5b15c24`] `🎯 APPLY`·`💾 SAVE` 두 버튼은 삭제됐다** — 이 줄은 하루 전 그 둘을 계약으로 적고 있었고 지금 **거짓**이다(`btn-valid-die-apply`/`btn-valid-die-save`는 마크업·JS에 0건). **고르는 것이 곧 적용**이다: 키 컨트롤은 진짜 `<select>`이고 `change`가 즉시 적용하며(`onValidDieRefChanged`), 목록이 잘렸거나·읽지 못했거나·지금 키가 목록에 없거나·항목이 0개면 **텍스트 입력으로 폴백**해 **`Enter`만** 적용한다(`input`은 컨트롤을 다시 그릴 뿐, `blur`/`change` 리스너는 아예 없다 — `renderValidDieKeyControl`). 목록을 읽는 유일한 리스너는 여전히 `focus → populateValidDieRefList`이고 **완전한 목록만** 캐시한다. 기록은 `⚡ Push` 또는 **`📐 규격만 저장`**(`btn-save-map-spec` → `saveMapSpecOnly` — 유효 다이 블록 밖, 그리드 툴바)이 한다. ⚠️ **고정된 것은 저작이지 저장 형식이 아니다** — `parseValidDieRef`는 종전 두 형식을 그대로 받는다. 계약 정본 [MAP_EDITOR_SPEC §5.7-a/§5.7-b](../spec/MAP_EDITOR_SPEC.md) |
| **📐 규격만 저장** (2026-08-04 `5b15c24`+`30284bf`) | `saveMapSpecOnly` — `grid_metadata` 한 필드만 쓰고 **셀은 한 건도 쓰지 않는다**. 🔴 **신원은 `loadedIdentity`가 아니라 「지금 화면의 컨트롤」**(`selectedTable` + `getCurrentMapKey()`)이고, **없는 등록을 만들 수 있다**(새 라우트 없음 — 지워진 SAVE가 쓰던 `PUT /tables/wafer_map_metadata/data/updates`가 `business_key_val`로 upsert. 확인창이 「새로 등록」/「갱신」을 말한다). 페이로드는 `⚡ Push`와 **같은 조립기** `buildPushGridMetadata` + `mergeStoredGridMeta`(모르는 키 보존). **응답에 `MAP_SPEC_SAVE_TIMEOUT_MS = 15000` + `AbortController`**, 🔴 시한 초과 문구는 **「기록되지 않았다」고 말하지 않는다**(멱등 쓰기라 단정하면 운영자가 착지한 쓰기를 되돌린다) |
| **캔버스 축척** (2026-08-04 `102cdea`+`edc7ef6`) | `cellMetrics()`가 **축척의 단독 생산자**이고 렌더와 마우스 매핑 둘 다 그것을 부른다. **두 축에 px/mm 하나**(`s = min(sGrid, sWafer)`)이고 `sWafer`는 **선언된 웨이퍼 지름**에 정박한다(`effectiveRadius`가 아니다 — 그쪽은 edge margin을 접고 있어 같은 웨이퍼가 다르게 그려진다). 피치 X≠Y면 **셀은 직사각형**이고 그것이 요청된 결과다. 🔴 **여백에 「filler 셀」 객체는 없다** — 격자 밖 칸은 `strokeRect` 하나만 긋고 `gridCells2D` 등록 **전에** `continue`하므로 쓰이지도 세어지지도 않는다(쓰기는 마우스 경로의 두 번째 경계 검사가 따로 막는다). 오버레이 마커는 **축별**(`markerAxisRadius` → `rx`/`ry`, 다르면 `ctx.ellipse`). 🔴 **`auto_registered` 기하는 이 경로에 닿지 않는다** — `physDeclaration`이 chip을 `null`로 돌려 비등방 폴백으로 떨어지고, 오버레이 정렬은 **합성 1mm로 맞추지 않고 거절**한다. 계약 정본 [MAP_EDITOR_SPEC §1-ter](../spec/MAP_EDITOR_SPEC.md) |

> **정정:** 맵 에디터는 **WebSocket을 사용하지 않습니다.** REST pull/push + localStorage. 실시간 WS는 메인 그리드(`websocket.js`)에만.
> **오버레이와 서버의 관계 (2026-07-27 정정)**: 맵 에디터 클라는 `GET /api/maps/overlay`를 **전혀 호출하지 않습니다** — `client2/src/**` 전수 grep 0건(2026-07-27 실측). `7d931dc` 직후 남아 있던 `limit=1` 선언 probe가 **서버 선언 오버레이 레이어와 함께 삭제되면서 마지막 호출처가 없어졌습니다.** 엔드포인트와 `server/map_overlay.py`는 살아 있으나 소비자는 `bonding_plan`/`transfer_plan`의 가용량 산출 쪽입니다.
> 실패 상태는 **명명된 것들**(`meta_unavailable`·`binding_unavailable`·`align_unavailable`·`no_data` — 🔴 **목록 옆에 수를 적지 않습니다. 이 어휘는 자랍니다**) + IO 실패의 일반 `error`이며, 전부 **그리지 않고 목록에 실패 행으로 남습니다.** ⚠️ **`align_unavailable`의 사유가 바뀌었습니다**(`cd3e0f4`) — 「격자 규격 불일치」는 **더 이상 사유가 아니고**(치수가 다른 맵을 겹치는 것이 규칙 6의 목적), 남은 것은 **치수 정의역 밖**(`1~100` 정수 — 온전성 가드)과 **피치 미상** 둘입니다. *(구 `align_unconfirmed`·`align_override_declared`는 서버·클라 양쪽 어디에도 없습니다 — 선언 레이어와 함께 2026-07-27 삭제.)* 계약은 [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md).

### 4.1 전사 계획 사이드바 (`transfer_plan.js`, 1,875줄)

**「계획 = 지금 열어 편집 중인 그 맵」** — `bonding_map`을 열면 본딩 계획, `dt_map`을 열면 DT 계획. stage는 열린 테이블에서 유도되며 `plan_id`도 계획 맵 사본도 없습니다.

| 영역 | 내용 |
|---|---|
| 배선 | `map_editor.js`가 `initTransferPlan(paintController)`로 초기화하고 `notifyMapContext`/`notifyLegendChanged`/`notifyPaintCounts`로 통지(단방향) |
| 관리 단위 | **DOE = value**(맵에 칠한 값 하나 = `map_split_registry` 행 하나 = 조건군 하나). **[ZONE 2026-07-28 `b35bc9f` — band 모델 대체]** 층 구조는 그 행의 `stack`(총 층수) + **고정 구역 셋**(`mat_1h`=1층 · `mat_top`=STACK층 · `mat_mid`=그 사이 전부). FROM/TO·`bands` 행·`seq`·배열 순서는 **없습니다**(🗄️ `bands`는 폐기·읽기 전용) |
| **쓰기 소유권** | ⭐ **[M2.6] `transfer_plan.js`는 서버에 쓰지 않습니다.** 레지스트리 행의 유일한 기록자는 `map_editor.js`(⚡ Push 경로 — **자동 저장은 `b35bc9f`에서 삭제**)이고, 패널은 `controller.getLegend()`로 읽고 `controller.updateLegendRow(value, {stack, mat_1h, mat_mid, mat_top, knobs, …})`로만 씁니다 — 저장·삭제·동시성 가드가 **한 경로**에 모입니다. Push 전 편집은 지문 게이트 로컬 초안에만 존재합니다([MAP_EDITOR_SPEC §4-bis](../spec/MAP_EDITOR_SPEC.md)) |
| 파생값 | **저장하지 않습니다.** 구역 소요 = `칠한 셀 수 × 그 구역의 층 수`, 자재당 = `ceil(소요/자재 수)`(합을 먼저 내고 나눔). 식의 구현은 각각 하나뿐입니다(저장 `ceil`/표시 `round`로 갈려 DB 34·화면 33이던 결함) — 정본은 `doe_bands.js`의 순수 zone 모델 + `contracts/doe_band_rules/vectors.json` |
| 서버 왕복 | GET `/api/transfer-plan/{stages,source-summary,validate}` + PUT `/tables/map_split_registry/data/updates`(`replace_map`). ~~`map_doe`/`map_doe_source`~~는 M2.6에서 폐기 |
| **replace 권한 불변식** | `legendReplaceScope`(= `{table, mapKey, fingerprint}`) — "이 화면은 **이 맵의 행**에서 왔고 읽었을 때 이랬다"는 **하나의 주장**. `replace_map` 권한이자 동시성 검사의 기준선이며, 테이블 전환·조회 실패·**절단 응답**·맵 언로드에서 **소거**됩니다. 쓰기 직전 재읽기해 서버가 달라졌으면 upsert로 강등하지 않고 **거부**합니다(`legendConflict`) — 강등하면 낡은 층 구조가 남의 것을 덮습니다 |
| 이동 | `openMaterial(id)` — 맵 간 이동의 유일 허브(브레드크럼 + 뒤로가기 프레임 스택). **[`280ebf0`] 분해 안 되는 ID는 `{첫 맵 키 컬럼: 원문}` 폴백으로 LOAD와 같은 라우팅** — 없는 키는 빈 프레임으로 열리고 Push 시 생성. 존재 probe는 여전히 추측하지 않고 `미상`([MAP_EDITOR_SPEC §6.4](../spec/MAP_EDITOR_SPEC.md)) |

상세 규격: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)(§5 오버레이 정렬 계약 · §6 전사 계획) · [map_editor/](../map_editor/README.md)

### 4.2 Map Editor 2 (`map_editor2.js` + `src/map2/*`) — **정렬 화면, 레거시 옆에 선다** (2026-08-05 신설 · 개발 중)

> ⚠️ **이 절은 라운드가 지나도 살아남을 수준으로만 적습니다.** 화면이 매일 바뀌고 있으므로 **컨트롤 이름·문구·줄 수를 여기에 옮기지 마십시오** — 설계 계약의 정본은 [MAP_ALIGNMENT_SPEC](../spec/MAP_ALIGNMENT_SPEC.md)이고, 이 절이 붙드는 것은 **모듈 경계와 「무엇을 하지 않는가」** 둘입니다.

- **왜 별개 페이지인가**: 레거시 에디터는 **매일 운영 데이터 위에서 돌고 있고 옆에서 사고도 났습니다.** 새 화면이 실제로 프레임을 확정할 수 있게 되기 전까지 **옛것이 삽니다** — `vite.config.js`의 그 자리에 그렇게 적혀 있습니다. **레거시를 여기로 이식하지 마십시오.**
- **모듈 규율이 이 디렉터리의 존재 이유입니다** — `src/map2/*`의 순수 층은 **인자로 받고 값을 돌려주며 모듈 상태를 갖지 않습니다.** 그래서 하네스가 **소스를 텍스트로 자르지 않고 `import`합니다**(레거시 하네스 41개 전부가 텍스트 슬라이싱이고, 그 기법이 **소스 구조에 거부권**을 갖고 있습니다). 🔴 **새 코드는 모듈이다**가 규칙이고, **기존 하네스는 전환하지 않고 수명이 다하게 둡니다**([MAP_ALIGNMENT_SPEC §0.3](../spec/MAP_ALIGNMENT_SPEC.md)).
- **층 경계**(같은 문서 §0.2): 신원 · 선언(`declaration.js`) · **좌석**(`seating.js` — **등록만 하고 그릴 수 없습니다**) · 채점/판정(`verdict.js`) · 통신(`api.js`) · 세션(`session.js`) · 조립(`main.js`, **화면을 아는 유일한 층**) · 그리기(`painter.js`, **아무것도 만들지 않습니다**) · 입출력(`excel_io.js`). 🔴 **좌석과 그리기를 다시 합치지 마십시오** — 레거시가 정확히 그 결함이고(화면 밖 `continue`가 등록보다 앞서 선언된 셀이 저장 페이로드에서 사라졌습니다), 분리의 형태는 [PRIMITIVES §4 「좌석은 등록만 한다」](./PRIMITIVES.md)에 있습니다.
- 🔴 **웨이퍼 테두리·마스크는 이 캔버스에 그려지지 않습니다**(`d4e0fed`). 종전 점선 원은 **하드코딩된 장식**이었고 어떤 JS도 읽거나 쓰지 않았습니다 — 자리표시자 목업에 맞춰진 크기였는데 실제 데이터는 스테이지를 가득 채우므로 **모든 맵이 그 원을 넘쳤고**, 제품 소유자가 그것을 「유효 다이 맵이 웨이퍼 밖으로 흘러넘친다」로 읽었습니다. **웨이퍼처럼 보이면서 웨이퍼를 모르는 도형은 도형이 없는 것보다 나쁩니다** — 조작자에게 안/밖을 그것으로 읽으라고 초대하는데, 그 판정이 정확히 마스크의 일이기 때문입니다. 다시 그려지는 조건은 **그 맵 *자신의* 선언된 phys가 원을 몰 수 있을 때**뿐이고, 근거가 없으면 아무것도 그리지 않습니다. ⚠️ CSS 규칙(`.me2-wafer-edge`)은 **생산자 없는 채로 DORMANT 표시와 함께 남아 있습니다** — 지웠다가 다시 만들면 그날의 규칙이 조용히 달라지기 때문입니다.
- **서버 절반**: 채점·판정 `server/map_alignment.py`, 기하·어휘 `server/map_overlay.py`, 확정 기록 `server/frame_confirmation.py`. 이음매 채점은 `contracts/map2_seam/`.
- ✅ **[2026-08-06 해소] 종전 이 자리는 「클라 `api.js`의 `ROUTES`가 옛 철자(`/map/align/*`)를 들고 있고 서버에 그런 경로는 없습니다 — 총괄 판정 대기」였습니다. 전수 대조 결과 어긋나는 철자가 0건입니다.** `ROUTES`가 부르는 모든 경로(`/api/maps/alignment/{view,confirm,worklist,references}` · `/api/maps/paint-rules` · `/enrichment/rules` · `/tables` · `/tables/{t}/schema`)를 `server/main.py`(HEAD)에서 실측했고 전부 서빙됩니다. `ROUTES.config`만 `null`인데 **그것이 설계**입니다 — 부르면 `RouteNotServedError`로 거절합니다. ⚠️ **코드 주석 하나는 아직 낡았습니다**: `api.js`의 `worklist`에 「STILL UNSERVED … 서버 레인이 라우트를 낼 때까지 `null`」이 남아 있는데 같은 파일이 그 값을 채워 두었고 서버도 서빙합니다(코드라 이 라운드가 손대지 않았습니다 — 총괄 보고).
- 🔴 **확정은 한 동작입니다**(`02416d4`, 제품 소유자 판정 2026-08-06) — 무장(arm) 단계도 두 번째 확인창도 없고, 확정 버튼 클릭 또는 `Enter` 한 번이 곧 쓰기입니다. `Enter`는 **확정 버튼에 포커스가 있거나 아무 컨트롤에도 포커스가 없을 때만** 그 경로를 탑니다. ✅ **[2026-08-08 해소] 종전 이 자리는 「마크업의 라벨·힌트가 아직 두 단계 문구를 들고 있다」였습니다** — HEAD 실측: `map_editor2.html`이 「확정: 읽기는 무마찰, 쓰기는 한 동작(클릭 또는 Enter)」·`Enter 확정`을 들고 있고 `data-armed`는 없습니다. **문구도 착지했습니다.**
- 🔴 **확정 버튼의 유일한 관문은 「무언가 골랐는가」입니다**(`21209d7`, 제품 소유자 2026-08-07: *「어차피 사람이 검수하고 누르는거라 막을 이유없음」*). 게이트에서 빠진 둘은 **막는 것이 아니라 알리는 것**으로 바뀌었습니다: **① `not_scorable`** — 채점기가 못 채점한 상태는 **사람이 유일한 답인 바로 그 상태**인데, 종전에는 그 하나만 사람이 답할 수 없었습니다(서버는 처음부터 받고 있었습니다 — `frame_confirmation.accepted_ruling_states`가 `scored`/`no_winner`/`not_scorable` 셋을 돌려줍니다). **② 추측 위에 선 답**(추측된 x/y 바인딩·미진술 귀속) — **누르기 *전에* 조작자가 가져야 할 사실**이라 안내 문구로 남습니다(이 쓰기는 되돌릴 수 없습니다). `selectedId`만 남습니다 — **아무것도 확정하지 않는 것은 행위가 아닙니다.**
- 🔴 **후보의 두 번째 축은 `앞면/뒷면`이 아니라 `좌상단/우상단 시작`입니다**(`c959368` 문구 → `db1ee42` **축 자체**). 🔴 **[2026-08-11 정정] 종전 이 줄은 「거울 반쪽이 곧 우상단 시작 반쪽」이라 적었고 그 문장은 두 번 거짓이 됐습니다** — ① 그 등가는 **4분의 1 회전에서 틀립니다**(거울은 90°/270°에서 **행 축**을 뒤집습니다 — `seating.js:38-40`) ② 그리고 `db1ee42`부터 **거울은 후보 집합에 아예 없습니다.** 지금 후보는 `candidates.js`가 조립하는 **4회전 × 2시작모서리**이고 철자는 `rot90_tl`/`rot90_tr`, 면은 전부 `front`입니다. 정본은 [MAP_ALIGNMENT_SPEC §2.4](../spec/MAP_ALIGNMENT_SPEC.md)이고 **여기서 다시 유도하지 마십시오.**
  - **후보가 16이 나오면 그것이 결함입니다** — 걸음 축은 거울 반쪽의 **대체**이지 추가가 아닙니다. `candidates.js` 머리주석이 같은 말을 합니다.
  - ⚠️ **레거시 `_back` 철자는 계속 읽히고, `뒷면`이라고 그려집니다**(`parseCandidateId` → `spellFrame`). 걸음 축이 생기기 전에 확정된 행은 **진짜 거울 선언**을 들고 있으므로, 그것을 `우상단 시작`이라 부르면 **이 화면 하나가 틀린 등가를 다시 말하게 됩니다.** `뒷면`이라고 적어 조작자에게 물리 면을 말하는 것은 그 행에 대해서는 **참**입니다 — 한 클릭 옆 레거시 에디터의 물리 뒷면이 바로 그 값이기 때문입니다.
  - **컨트롤 배치도 이 모듈이 소유합니다** — 2열(시작 모서리) × 4행(회전). 조작자는 **아래로 읽어 회전을 고르고 옆으로 읽어 모서리를 바꿉니다.** 그리고 「뒤집기는 어떻게 하나」는 격자 아래 `INVERSION_FOOTNOTE`가 **한 번 영구히** 답합니다(실제 뒤집힌 웨이퍼는 맵 편집기에서 선언).
- 🔴 **확정 키는 화면이 조립하지 않고 룰의 선언을 읽습니다**(`3d43a6c`). `decisionKeyOf(declaration, decision)`(`src/map2/view_model.js`)가 룰이 선언한 `decision_key` 컬럼을 arity와 무관하게 그대로 채우고, **하나라도 못 채우면 `key`는 `null`**입니다 — 빈 값을 서버로 보내 "결정키 미충족" 거절을 클라가 대신 만들어내지 않습니다. 값은 컬럼별로(서버가 실어 준 `__key` → 같은 이름의 필드 → 레거시 위치 브리지 순서) 읽으므로, 이전에 채택된 다른 룰의 낡은 키가 섞여 들어올 수 없습니다. **컬럼 이름은 이 파일 어디에도 하드코딩돼 있지 않습니다** — 빌드 번들에 `dt_eqp` 0회. 계약 정본은 [MAP_ALIGNMENT_SPEC §5](../spec/MAP_ALIGNMENT_SPEC.md).
- 🔴 **확정 문구의 주어도 슬롯 *하나*입니다 — arity를 아는 분기가 없습니다**(`42d7600`). 마크업의 확정 문장은 `data-me2-confirm-unit` 한 자리를 갖고, `unitValuesOf(decision)`이 서버가 실어 준 `__key` dict를 그대로 읽어 채웁니다 — **키 순서가 곧 표시 순서이고 dict 길이가 곧 arity**라, 함수 안에서 arity를 가르는 분기가 성립하지 않습니다. 종전에는 훅이 둘(`data-me2-confirm-eqp`/`-product`)이고 뷰모델이 이름 붙은 두 필드로 먹였는데, 그것은 **`3d43a6c`가 `keyFrom`에서 지운 두 값 모양의 두 번째 사본**이었고 선언 컬럼이 하나뿐인 운영 룰은 자기가 갖지 않은 모양의 문장을 읽고 있었습니다. 구분자는 이 화면이 이미 토큰을 잇는 데 쓰던 것을 `UNIT_SEPARATOR`로 **한 번만** 철자합니다(발명 아님). ⚠️ **문구의 글자는 여기 옮기지 않습니다 — 마크업이 정본입니다.**
  - ⚠️ **열린 채로 남긴 둘**(`42d7600`이 스스로 진술): ① 문구와 전송 키가 **같은 `__key`를 서로 다른 두 함수로** 읽으므로, 채택된 룰이 선언하지 않은 컬럼이 서빙되면 **보여 준 다음 버려집니다** — 룰 전환을 견디는 판정이 필요하고 채점되지 않았습니다. ② `__key`가 서빙되지 않을 때의 **레거시 위치 브리지는 여전히 둘에서 멈춥니다.** ③ arity 1·3 룰을 **라이브 서버에 물려 확정 버튼을 누른 적은 없습니다**(하네스와 브라우저 HTML 파서까지가 실측 범위).
- 🔴 **룰 채택 실패가 침묵 대신 사유를 말합니다.** `selectAlignmentRules`가 `alignment: true`를 선언한 룰이 0건이거나 여러 건이면 워크리스트 요청 자체가 나가지 않았는데(`refreshWorklist()` 진입 전 리턴), 종전 화면은 그것을 빈 목록으로만 보여줬습니다 — 로딩 중인지 실패했는지 구별 불가능. 지금은 건수를 이름 댑니다: `정렬 규칙 없음 · alignment 선언 0/N건 · 1건 필요` / `규칙 선택 필요 · alignment 선언 N건 · 1건만 자동 채택`.
- 🔴 **워크리스트는 테이블마다 묻고, 테이블은 질문의 일부입니다**(`e943e46`). `map_table`이 라우트의 **필수** 파라미터이므로 화면의 워크리스트는 언제나 정확히 한 테이블의 것입니다. 그 필드를 바꾸는 사람은 **반드시 `fetchWorklist`를 다시 지나야** 합니다 — 안 지날 때의 실측 실패는 「목록이 낡는다」가 아니라 **「한 화면에 두 테이블」**입니다(컬럼 선택기는 새 테이블의 스키마로 즉시 다시 채워지는데 행과 맵 수는 옛 테이블의 것 — 실측 모집단 191/160/97/96/1 대 40/40/20/20/6). **교체는 두 번째 장치가 아니라 `AbortController`**이고(`value_suggest.js`가 이미 쓰는 그 형태), 🔴 **취소는 실패가 아닙니다** — 조작자가 자기 질문을 갈아치운 것을 오류 표면에 그리면 **일어나지 않은 장애를 보고**하게 됩니다. ⚠️ **`기준` select는 고장난 적이 없어 손대지 않았습니다**(`/worklist`는 기준 파라미터를 아예 받지 않습니다) — **대칭은 바꿀 이유가 아닙니다.**

---

## 5. 어드민 (`admin.js`, ~3,155줄) — 파이프라인 생애주기 5탭

2026-07-25 IA 재편: 탭 축이 메커니즘 7탭에서 **파이프라인 생애주기 5탭**으로 바뀌었습니다. 각 탭 본문은 생애 단계(현황 → 오류 → 수정/실행) 접이식 섹션 스택.

| 탭 | 내용 |
|---|---|
| **Overview** (첫 화면) | **재교정률 한 줄 + 교정 공수 한 줄 + 설정 반영 한 줄** + 헬스 카드(File/Chain/AutoUpdate/Enrichment — **수를 적지 않습니다** — 상세 수치+최근 이벤트+탭 딥링크), 전폭 레이아웃 |
| **File Ingestion** | 인제션 로그(필터/정렬/페이지) + Workspaces(기본 접힘·요약) + 실패 진단→커스텀 파서 편집 딥링크 |
| **Chain** | Rules 현황 + **Chain 실패(Outbox Transactions)** 재시도 + Mappers(행별 🛠️ Edit) + 실패 진단→맵퍼 편집 딥링크 |
| **Auto Update** | 상태/Run Now + **산출물 인제션 실패 연계**(auto-update 대상 ∩ 파일 실패 교집합) |
| **Enrichment** | 규칙 표 + 결손 카운트 — 규칙 편집은 read-only 안내(CRUD API는 백로그). ⚠️ **[2026-08-11 `5116f67`] Queue 딥링크(`enrichment.html?rule=`) 4건 삭제** — 대상 페이지 자체가 없어졌다. 규칙 포커스는 행 클릭 핸들러로 생존하지만, **특정 규칙의 결손 입력 워크리스트를 여는 경로는 대체되지 않았다** |

- **핵심가치 #1 계기 두 줄 (Overview 상단, `renderRecorrection` + `renderEffort`, 갱신은 `refreshCoreValueLines` 하나)**: 두 줄은 **같은 `/dashboard/summary` 응답 한 번**에서 나온다.
  - **재교정률**: 사람이 같은 셀을 두 번 이상 고친 비율 — **보조 계기**([backend](./backend.md#재교정률-dashboardsummary--recorrection) · 2026-07-29 강등).
  - **교정 공수** (2026-07-29 수리 라운드 신설): 한 교정을 끝내기까지의 상호작용 점수 = SSOT §1의 **정본 계기**. `avg_score`와 함께 **커버리지(`measured_ratio`)를 같은 줄에** 적는다 — 이 계기는 클라가 보내 줄 때만 쌓이고 서버는 기록 예외를 삼키므로, **커버리지가 화면에 없으면 수집이 통째로 끊겨도 아무 신호가 없다.** 기준선을 잴 창이 한 번뿐이라 그 신호가 전부다. 상태별 문구가 서로 다른 것이 요점이다: `unavailable_reason`이 오면 **그 사유를 그대로**, `measured_ratio === 0`(사람 교정은 있는데 계측 0건)이면 **수집 중단 경고**(danger — 이 줄에 한해 사유 문장까지 붉게), 응답에 `effort` 필드 자체가 없으면 "**서버가 보고하지 않음**"(구 서버 — "교정이 없었다"고 지어내지 않는다), 표본이 정말 없으면 "교정 없음". 커버리지 50% 미만 또는 미상이면 "대표값으로 읽지 말 것" + warn 톤.
  - 둘 다 **카드도 패널도 모달도 아닌 한 줄**이고, 값 옆에 **분모를 항상 같이 적는다**(재교정률은 표본 100 미만이면 "추세로 읽지 말 것" + muted 톤). 지켜야 할 두 가지:
  1. **자동 갱신 루프(`fetchOverview`)에 태우지 않는다.** 출처 `/dashboard/summary`는 테이블마다 `count(*)`를 도는 무거운 엔드포인트다(실측 ~1.5s). `await` 없이 던지고 **5분(`RECORRECTION_MIN_INTERVAL_MS`) 간격**으로만 갱신한다 — 본문 카드 렌더가 이 요청을 기다리지 않는다. 두 줄이 한 요청을 공유하므로 스로틀도 하나다.
  2. **`rate_pct=null`·`avg_score=null`은 "0"이 아니라 "—"로 렌더한다.** 표본 없음과 조회 실패를 정상 0으로 위장하면 지표가 거짓말을 한다. 그리고 **"—"에는 반드시 사유가 붙는다** — 사유 없는 대시는 정상(표본 없음)과 장애(수집 중단)를 구별하지 못하는데, 이 둘은 정반대 대응을 요구한다.
- **설정 반영 한 줄 (Overview 세 번째 줄 — F9 `GET /admin/config/resolve`, 2026-07-31)**: 「내가 쓴 config가 먹었는가」에 답하는 **유일한 화면**. 종전 `POST /admin/reload-configs`는 캐시를 갈아끼우고 **아무것도 반환하지 않는 쓰기 전용 버튼**이었고, 그 공백이 실제 결함을 숨기고 있었다 — `candidate_for` 선언 없이 `auto_confirm: true`를 켜면 규칙은 데몬 로그에 경고 한 줄만 남기고 조용히 비활성이 된다(라이브가 정확히 그 상태였다: `effective 0 / ineffective 2 / rejected 0`).
  - **🔴 문장은 전부 서버가 만든다. 클라는 「효과 없음」을 스스로 판정하지 않는다.** 사유는 닫힌 4어휘(`config_resolve_report.REASONS`)이고 사람이 읽을 문장은 서버의 `detail`이며, 클라는 그것을 **그대로** 렌더한다. 사유별로 문장을 짓기 시작하면 U6에서 6종을 삭제한 하드코딩 사본 계급이 그대로 재발한다. 계약 정본은 [spec/ENRICHMENT_QUEUE_SPEC §5.2-bis](../spec/ENRICHMENT_QUEUE_SPEC.md), 라우트는 [backend §2](./backend.md).
  - **뷰 모델을 `config_resolve_view.js`로 분리한 이유는 채점 가능성 하나다.** DOM 빌더 안에 있으면 node에서 실행할 수 없어 「렌더된 문장 == 서버가 만든 문장」이 grep으로만 확인된다. 지금은 `contracts/config_resolve_report/client_harness.mjs`가 그 모듈을 **임포트해** 벡터로 만든 페이로드를 먹이고, 나오는 문자열 전부를 출처로 채점한다(`server`는 페이로드에 그 문자열이 있어야 하고, 페이로드의 모든 `detail`은 **정확히 한 번** 렌더돼야 하며, 클라 자신의 문자열은 **고정된 `CHROME` 표**에서만 나온다). 이로써 **INV-F9-4의 클라 절반이 `PENDING`에서 실행 채점으로 바뀌었다.**
  - **모집단 이름(`effective`/`ineffective`/`rejected`)은 서버 어휘 그대로 칩에 적는다** — 한국어 라벨을 지어내면 그 순간 클라가 그 단어의 뜻을 자기 사본으로 갖게 된다(서버는 모집단의 한국어 명칭을 주지 않는다). 색만 클라가 정하고, **모르는 모집단은 추측하지 않고 중립색**이다.
  - **카드도 패널도 모달도 아닌 한 줄**이고 위의 두 계기 줄과 같은 문법으로 읽힌다. 헤드라인(모집단 카운트)은 클릭 없이 항상 보이고, 펼침은 `<details>`로 **제자리에서** 일어난다. **문제가 있을 때만 자동으로 한 번 펼친다** — 운영자가 접은 것을 갱신 주기가 다시 펴면 그 펼침은 곧 무시당한다. 응답이 직전과 **같으면 다시 그리지 않는다**(읽는 도중 참조뷰가 접히는 것을 막는 유일한 방법).
  - **`Reload Configs & Code`가 처음으로 무언가를 돌려주는 자리**: 리로드 성공 시 스로틀을 무시하고 다시 읽고, 보고서가 실제로 달라졌으면 낡은 드라이런 측정값을 버리고 자동 펼침 권한을 되살린다.
  - **드라이런(`GET /admin/enrichment/auto-confirm/dry-run`)은 규칙 항목 안의 버튼 하나**다. 읽기 전용이라(`apply`는 그 라우트에 존재하지 않는다) 확인 대화상자가 없지만, 큐를 걷는 분석 질의이므로 **자동으로는 절대 돌지 않는다** — 운영자가 물어볼 때만 센다. 결과는 그 버튼 아래에서만 교체된다(블록 전체를 다시 그리면 펼쳐 둔 참조뷰가 자기 클릭 때문에 접힌다).
  - **조회 실패는 「설정이 멀쩡하다」가 아니다** — 대시(―)와 사유를 남기고 자동으로 펼치지 않는다(muted 톤, 토스트·모달 없음).
  - **다만 「조회 실패」 한 마디로 뭉개면 안 되는 갈래가 넷 있다 (2026-07-31).** **404는 서버에 닿지 못한 것이 아니라 「이 서버엔 그 기능이 없다」는 서버의 대답**이고, 그 손은 「재기동」이라는 다른 곳에 간다 — 라이브에서 정확히 이 일이 일어났다(`f3fd785` 이전 프로세스가 8080·8081 양쪽에서 404, 화면엔 「조회 실패」만). 조용히 강등한다는 동작은 그대로 두고 **문구만** 다섯으로 갈랐다:
    | 상태 | 문구 | 손이 가는 곳 |
    |---|---|---|
    | 응답 없음(연결 거부·오프라인) | `서버에 연결할 수 없습니다 ― 서버가 실행 중인지 확인하세요` | 서버가 떠 있는가 |
    | `404` | `실행 중인 서버가 구버전입니다 ― 서버를 재시작하세요` | **재기동** |
    | `401`·`403` **+ `WWW-Authenticate: X-Admin-Token`** | `관리자 토큰이 거부되었습니다 ― 새로고침 후 다시 입력하세요` | 토큰(아래 토큰 절 3번의 복구 경로 그대로) |
    | `401`·`403` **그 헤더 없이** | `관리자 게이트가 아닌 응답입니다 ― 프록시 등 앞단에 무엇이 있는지 확인하세요` | **이 포트에 무엇이 답하는가** |
    | 그 외(5xx 등) | `조회 실패` / 드라이런은 `드라이런 요청 실패` | 라우트는 있고 깨진 것 — **이것만이 진짜 조회 실패** |
    - **401을 뭉개는 것은 같은 결함의 한 겹 안쪽이다.** 401이 우리 게이트라는 보장은 없다 — 포트 앞의 프록시는 **자기** `WWW-Authenticate: Basic realm=…`으로 답하고(2026-07-30 루프백 호출에서 실제로 일어났다), 그때 운영자를 토큰 모달로 보내면 오후가 날아간다. 판정은 상태코드가 아니라 헤더이고, **그 판정은 이미 `admin.js`의 `isGateRejection`이 갖고 있으므로 다시 유도하지 않고 재사용한다**(사본은 갈라진다 — 아래 토큰 절 1번이 같은 이유로 있다).
    - 응답의 **`Server:` 헤더가 있고 uvicorn이 아니면** 그 값을 문장 뒤에 괄호로 **그대로** 붙인다(`… (squid/5.7)`). 이 상황에서 화면에 나올 수 있는 가장 쓸모 있는 사실 한 조각이고, **지어낸 문장이 아니라 응답자가 보낸 값**이라 위의 `srv()`·`val()`과 같은 계급이다 — 그래서 문장(`fetchFailureText`)과 증거(`fetchFailureEvidence`)는 **분리돼 있다**. 「문구는 언제나 `CHROME` 상수」가 문자 그대로 참으로 남고 시험 가능해진다.
    이 문구들은 **서버가 만들 수 없는 유일한 문장**이라(라우트가 없는 서버는 「나에겐 그 라우트가 없다」를 답할 수 없다) 위의 🔴 규율의 **유일한 예외**이고, 그래서 클라가 지어내는 대신 **고정 `CHROME` 표**에 chrome으로 들어가 계약 하네스의 채점을 그대로 받는다. 분기는 `fetchFailureLine(failure, fallback)` **하나**뿐 — 드라이런 버튼도 같은 함수를 쓴다(같은 커밋에서 난 라우트라 구 서버에선 똑같이 404고, 같은 포트라 같은 프록시가 답한다).
  - **⏱ 실패는 스로틀 시각을 찍지 않는다 (2026-07-31).** 1분 스로틀은 **성공적인** 폴링이 화면을 계속 다시 그리는 것을 막으려고 있는 것이고, 실패한 시도는 그 일을 하지 않았다. 시각을 진입부에서 찍으면 **실패가 침묵 1분을 사 버려서**, 원인이 해소된 뒤에도 화면이 옛 문장을 그대로 들고 있다 — 운영자가 문장이 시킨 대로 토큰을 넣고도 「토큰은 이미 넣었는데」가 되는 경로다(실제 신고). 그래서 시각은 **읽기에 성공한 뒤**에만 찍는다(응답이 직전과 같아 다시 그리지 않는 경로도 성공이므로 찍는다 — 안 찍으면 정상 상태에서 요청이 2배가 된다). 여기에 더해 **`adminTokenGeneration`이 움직였으면**(= 토큰이 새로 들어왔으면) 창이 안 지났어도 다음 갱신을 통과시킨다 — 타이머가 아니라 **원인이 바뀌었을 때** 한 번 다시 읽는 것이고, 새 폴링은 만들지 않는다.
- **Code Editor는 독립 탭 폐지** → 편집 딥링크 공용 뷰(Monaco cdnjs, 파일 피커, dirty 가드). `#editor=<encoded path>`로 직접 오픈 가능.
- **해시 라우터**: `#overview/#file/#chain/#autoupdate/#enrichment` + 구 탭 별칭 호환(`#outbox→Chain`, `#workspace→File`, `#mapper→Chain`).
- 신규 서버 API 0건 — 기존 `/admin/*`·`/enrichment/rules`만 소비. 함수 목록: [CODE_MAP §7](./CODE_MAP.md#7-client2src--웹-클라이언트).
- **🔒 어드민 토큰 (2026-07-27)**: 서버가 `/admin/*`을 공유 토큰으로 잠근다([backend §API](./backend.md)). 클라 측 구현은 `admin.js`의 `adminFetch()` 하나뿐 — **로그인 화면도, 새 탭·모드·설정 패널도 없다.** `localStorage['assy.adminToken']`에 보관하고 `X-Admin-Token` 헤더로 전송한다. 서버에 토큰이 미설정이면 게이트가 열려 있어 프롬프트 자체가 뜨지 않는다. 판정 규칙 4가지가 **모두 필요**하다(각각 실제 오작동을 막는다):
  1. **상태코드가 아니라 `WWW-Authenticate: X-Admin-Token` 헤더로 판정한다.** `_resolve_admin_script_path`가 격리 사유로 내는 403이 있어, 상태코드만 보면 그것을 "토큰이 틀렸다"로 오해해 **정상 토큰을 사용자 입력으로 덮어썼다.**
  2. **토큰 세대 카운터** — 프롬프트 도중 이미 교체된 토큰에 대해 **먼저 날아간 응답**이 뒤늦게 도착하면 조용히 재시도한다. 이게 없으면 "동시 7건 → 프롬프트 1회"는 타이밍 운이고, 두 번째 모달이 **올바른 토큰을 두고** "거부되었습니다"라고 말한다.
  3. **취소(`prompt`→`null`)는 저장된 토큰을 지우지 않는다** — 지우면 30초 갱신 타이머가 영원히 모달을 띄운다. 취소 후에는 더 묻지 않고 토스트로 "새로고침하면 다시 물어봅니다"를 알린다.
  4. **503 본문을 토스트로 노출한다** — 서버가 `ASSY_ADMIN_TOKEN`을 설정하고 재기동하라고 정확히 알려주는데, 삼키면 화면엔 "저장 중 오류 발생"만 남아 503 분기의 존재 이유가 사라진다.
  ⚠️ **`/admin/*` 호출은 반드시 `adminFetch`로** — `grep 'fetch(\`${API_BASE}/admin/'`가 0건이어야 한다. 맨 `fetch`로 남은 호출부는 미설정 서버에서 멀쩡히 동작하다가 운영에서만 401이 난다.
  ⚠️ **서빙되는 것은 `dist/assets/admin-*.js`다.** 소스만 고치고 번들을 안 올리면 토큰을 켜는 순간 어드민이 잠긴다 — 판정은 `grep -c X-Admin-Token client2/dist/assets/admin-*.js` > 0.

---

## 6. 지식그래프 뷰어 & 추적 리포트 (온톨로지 트랙 UI)

| 페이지 | 역할 |
|---|---|
| `graph.html` + `graph_viewer.js` | **서브그래프 뷰어** — 첫 화면 `/graph/stats` 카운트 카드, label+identity 자동완성 검색, `/graph/neighbors` 1/2-hop 서브그래프를 무라이브러리 BFS 동심원 캔버스로 렌더. 노드 클릭=재중심 탐색, user provenance 엣지 강조(`--overwrite` 색), truncated 배지. 테마 색은 1회 캐싱+`themechange` 재캐싱(상시 rAF 없음) |
| `trace.html` + `trace.js`/`trace_core.js` | **추적 리포트** — 시드 칩(상한 20)·depth 1–3·시간 범위로 `POST /graph/trace` → 라벨별 엔티티 그룹 테이블 + event_time 시간순 타임라인(user provenance 강조, 구조 엣지 접이식). URL 동기화(`replaceState`), 청크 렌더(그룹 100행/타임라인 300건) |
| 진입 흐름 | 메인 그리드에서 행 선택 → 「🕸️ 추적」(`trace_launch.js`, `/graph/mapping-summary`로 활성 판정) → 선택 행을 identity로 조립(서버 `compose_identity` 미러 — `\|` 조인+이스케이프+float 안정화)해 시드로 전달. graph.html ↔ trace.html 양방향 크로스링크 |

---

## 7. 백엔드 계약

- REST + WebSocket at `127.0.0.1:8080` (FastAPI). 엔드포인트: [backend.md](./backend.md)
- 셀 데이터 형태: `data[col] = {value, is_overwrite, priority_source}` (grid.js `ensureCellObject`가 정규화). **가상 조인 셀도 같은 형태**다 — 서버 `attach`가 같은 키를 채우므로 클라에 두 번째 리더가 없다(§3.4)
- 스키마 형태: `GET /tables/{t}/schema` → `{table_name, columns, column_types, business_key, composite_key_source, map_key_columns, map_push_ok, virtual_columns}`. **`columns`는 저장 컬럼만**이고 `virtual_columns`는 별도 배열이다 — 둘을 합치는 순간 「저장하는가」에 기대는 소비자 넷이 조용히 틀린다([backend §2.2](./backend.md))
- 그래프 조회: `GET /graph/{stats,neighbors,nodes/search,mapping-summary}` + `POST /graph/trace` (read-only)
