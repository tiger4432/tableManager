# 문장은 서버가 짓고 클라는 그대로 그린다 — 그리고 401은 스스로를 증명하지 못한다

> **일자:** 2026-07-31 새벽~오후 | **관련 커밋:** `93610cb`(06:44, 클라 절반) · `cde3398`(14:21, CORS) · `1dc761b`(14:22, 실패 다섯 상태) — **한 라운드다.** `cde3398`과 `1dc761b`은 71초 차이로 나란히 착지했다.
> **담당:** 사용자(QA 관찰 — 「토큰을 넣었는데 그대로다」) · 구현자는 커밋에 기록이 없다
> **대상:** `client2/src/config_resolve_view.js`(신설) · `client2/src/admin.js` · `client2/admin.html` · `contracts/config_resolve_report/client_harness.mjs` · `server/main.py`(CORS `expose_headers`) · `docs/architecture/frontend.md` · `client2/dist`(`1dc761b`에서 재빌드)
> **선행 항목:** `20260730_195606_did_the_config_take_effect_and_a_probe_that_confirmed_a_column_name.md` — 같은 기능의 **서버 절반**(`f3fd785`, 07-30 19:56)
> **계기·채점:** 이 항목 작성 시점에 HEAD에서 계약 하네스 재실행 —
> `contracts/config_resolve_report/client_harness.mjs` → **29개 파일 스캔, 렌더된 문자열 159개가 전부 페이로드나 클라의 고정 라벨표로 역추적된다, OK.**
> 서버 스위트(HEAD = `1dc761b`): `pytest server/tests contracts` **1707 통과 / 0 실패**(그 시점 커밋된 파일만 수집한 수).

## 배경 — 리로드 버튼이 한 번도 답을 하지 않았다

`POST /admin/reload-configs`는 줄곧 **쓰기 전용**이었다. 캐시를 새로 읽고, 무엇이 먹었는지는
운영자에게 한 마디도 하지 않는다. `93610cb` 시점의 살아 있는 증거: **enrichment 규칙 두 개가
모두 `ineffective / not_declared`인데 제품의 어떤 화면도 그 사실을 말하지 않았다.**

## 계약의 지지대는 부정형이다 — 그리고 DOM 빌더 안에서 어기기 쉽다

> **서버가 운영자용 문장을 짓고, 클라는 `detail`을 그대로 렌더한다.**

말하기는 쉽고 지키기는 어렵다. **DOM을 인라인으로 조립하는 렌더러 안에서는, 한국어를 지어내는
렌더러도 grep에 깨끗하게 잡힌다.** 그래서 뷰 모델을 **DOM이 없는 별도 모듈**로 떼고, 내보내는
문자열마다 **출처**를 붙였다.

| `src` | 뜻 | 하네스가 채점하는 방식 |
|---|---|---|
| `server` | 페이로드가 쓴 문장 | 페이로드 어딘가에 **글자 그대로** 존재해야 한다 |
| `value` | 페이로드의 **값**을 JSON으로 적은 것 | `JSON.stringify(<페이로드 값>)`와 정확히 같아야 한다 |
| `chrome` | 클라가 소유한 구조 라벨 | **고정된 `CHROME` 표**에서 와야 한다 |
| `count` | 클라가 센 정수 | 정수를 자기 자신으로 적은 것 |

```js
/** A string the SERVER wrote. Rendered verbatim, never reworded. */
function srv(value) { return { src: 'server', text: String(value) }; }
/** A payload VALUE, spelled in JSON — the syntax of the file the operator edited. */
function val(value) { return { src: 'value', text: JSON.stringify(value), raw: value }; }
```

**하네스는 이 모듈을 읽지 않고 실행한다.** `vectors.json`의 케이스를 그대로 먹여 네 부류를
전부 검사한다 — 페이로드의 모든 `detail`이 정확히 한 번씩 돌아오는지까지. 설정 상태에 대한
문장이 이 파일 안에서 조립되는 순간 그것은 페이로드에도 `CHROME`에도 없고, 하네스가
파일과 줄 번호로 그렇게 말한다.

그래서 `INV-F9-4`가 `PENDING` 출력을 멈추고 **채점되기 시작했다.** `93610cb`이 적은 수는
렌더 문자열 155개 전부 추적. **이 항목 작성 시점 실측은 159**(`1dc761b`이 실패 문장 넷을
`CHROME`에 더했다).

증명으로 결함 둘을 되돌려 넣었다 — 사유마다 클라가 문장을 짓게 하면 **불일치 12건**,
사유 단어를 리터럴로 적어 두면 **`INV-F9-7`이 파일:줄과 함께** 뜬다. 확인 후 원복.

## UI 규율 — 새 영역·모드·모달 0개

개요 화면이 **세 번째 줄**을 얻는다. 이미 있는 핵심가치 두 줄과 같은 문법이다.
헤드라인은 항상 보이고, 자세한 내용은 네이티브 `<details>` 뒤에서 제자리 펼침이다.

- 리포트가 깨끗하지 않으면 **한 번** 자동으로 열린다.
- 응답이 바뀌지 않았으면 **아예 다시 그리지 않는다** — 안 그러면 운영자가 읽고 있던 참조뷰가
  발밑에서 접힌다.
- **밀도는 작은 글씨가 아니라 접기로 푼다.**

## `1dc761b` — 상태 코드는 진단이지 실패 깃발이 아니다

F9 뷰가 무엇에 대해서든 「조회 실패」를 찍고 있었다. 이제 다섯 상태다. 나뉜 이유는 **각각이
운영자의 손을 다른 곳으로 보내기** 때문이다.

| 응답 | 문장 | 손이 가는 곳 |
|---|---|---|
| 응답 없음 | 서버에 연결할 수 없습니다 ― 서버가 실행 중인지 확인하세요 | 서버가 떠 있나 |
| 404 | 실행 중인 서버가 구버전입니다 ― 서버를 재시작하세요 | **재기동** |
| 401/403 **+ 게이트** | 관리자 토큰이 거부되었습니다 ― 새로고침 후 다시 입력하세요 | 토큰 |
| 401/403 **게이트 아님** | 관리자 게이트가 아닌 응답입니다 ― 프록시 등 앞단에… | 이 포트에 뭐가 있나 |
| 그 밖 | 조회 실패 | 호출자 자신의 실패 라벨 |

### 지지대는 401을 가르는 곳이다

**401은 그 자체로 우리 게이트라는 증거가 아니다.** 앞단 프록시가 같은 포트에 자기
`WWW-Authenticate: Basic realm=…`으로 답하고, 2026-07-30의 loopback 프록시 인시던트가 정확히
그 모양이었다 — 앞단의 403이 인증 실패로 읽혀 오후를 썼다.

판정은 상태 코드가 아니라 **헤더**다. 그리고 **다시 유도하지 않고 그대로 재사용한다.**

```js
function isGateRejection(res) {                     // 이 라운드가 만든 것이 아니다 (90e284f)
  if (res.status !== 401 && res.status !== 403) return false;
  const challenge = res.headers && res.headers.get
    ? (res.headers.get('WWW-Authenticate') || '') : '';
  return challenge.toLowerCase().includes(ADMIN_TOKEN_HEADER.toLowerCase());
}
```

뷰 모듈이 이 헤더를 언급하는 유일한 자리는 **자기가 그것을 검사하지 않는 이유를 적은 주석**
뿐이다. 사본이 둘이 되면 갈린다.

### `Server:` 헤더는 증거이지 문장이 아니다

```js
export function fetchFailureText(failure, fallback = CHROME.FETCH_FAILED) { … }  // 언제나 CHROME 상수
export function fetchFailureEvidence(failure) {
  const server = failure && failure.server ? String(failure.server).trim() : '';
  if (!server || /uvicorn/i.test(server)) return null;
  return server.slice(0, 40);
}
```

둘을 따로 두고 나중에 이어 붙인다. 그래야 **「문장은 언제나 `CHROME` 항목이다」가 글자 그대로
참이고 검사 가능**하다 — 보간하는 함수 하나로 합쳤으면 그 성질을 조용히 내줬을 것이다.
`uvicorn`이면 숨긴다(우리 서버가 자기 이름을 말하는 것은 운영자에게 아무 정보가 아니다).
길이를 자르는 이유는 그것이 **의심 대상 당사자가 보낸 입력**이기 때문이다.

### 스로틀 시계가 fetch **앞에서** 찍히고 있었다

이 라운드에서 사용자 관찰이 지목한 결함이다 — 토큰을 넣었는데 실패 문구가 그대로였다.

```js
// 종전: 시도 시작 시점에 무조건 찍었다 → 실패가 성공과 똑같은 침묵 1분을 샀다
const tokenChanged = adminTokenGeneration !== configResolveTokenGeneration;
if (!force && !tokenChanged
    && now - configResolveLastAt < CONFIG_RESOLVE_MIN_INTERVAL_MS) return;
…
const raw = await res.text();
configResolveLastAt = now;          // ← 읽기에 성공한 뒤에만 찍는다
```

**실패가 시각을 찍으면 실패한 시도가 침묵을 사 버려서, 원인이 해소돼도 화면이 그대로다.**
그래서 운영자가 화면이 시킨 대로 정확히 했는데 화면은 계속 같은 말을 한다 —
「안 먹었다」로 읽힌다.

그리고 **마지막 시도 이후에 도착한 토큰은 타이머 틱이 아니라 바뀐 원인**이므로 창을 통째로
건너뛴다. 커밋이 적어 둔 실측: 실패한 읽기가 이제 0초/30초/60초에 재시도하는데, 종전 코드는
**30초 틱 자체를 만들어 낼 수 없었다.**

같은 분류기를 드라이런 버튼도 쓴다 — 그 라우트도 같은 커밋에 착지했으므로 구버전 프로세스는
거기서도 404를 내고, 같은 프록시가 같은 포트에 답한다. **분류기 하나, 둘이 아니다.**

## `cde3398` — 노출하지 않으면 교차 출처에서 게이트가 보이지 않는다

`WWW-Authenticate`가 `expose_headers`에 없었다. **브라우저가 교차 출처에서 그 헤더를 지운다.**
그래서 vite dev 출처(:5173)에서는 **진짜 게이트 거부가 「앞단이 답했다」로 표시된다** —
확신 있게 틀린 문장이고, 그것이 대체한 일반적 실패 문구보다 **더 나쁘다.**
같은 출처(:8080/:8081 직접 서빙)에서는 원래 읽혔고, 그래서 사무실 페이지는 올바로 보고했다.

```python
expose_headers=["Content-Disposition", "X-Estimated-Content-Length", "X-Total-Rows",
                "WWW-Authenticate"]
```

값은 **우리가 원하는 헤더의 이름**뿐이라 비밀이 없다.

## 추측 대신 「무엇을 재야 하는지」를 적었다

사용자가 401이 뜬 상태에서 `localStorage`가 비어 있고 토큰 모달도 안 뜨는 것을 봤다.
**나는 `adminTokenDeclined`가 설정된 탓이라고 설명했고, 그 설명은 반증됐다** — 그것은 모듈
변수라 새로고침이 지우는데, 새로고침해도 모달이 돌아오지 않았다.

그래서 보드에는 내가 가정한 것이 아니라 **재야 할 것**이 적혔다. 여기에는 「다른 어드민 호출은
애초에 401이 아니었을 가능성」이 포함된다 — 이 장비에서 `/admin/chain/rules`는 **토큰 없이
200을 답한다.** 게이트가 열려 있다면 F9 라우트만 거부하는 셈이고, 그러면 프롬프트가 뜨는
조건 자체가 달라진다. 사용자는 값을 직접 넣어 막힘이 풀린 상태였다.

## 그때 남아 있던 것

- **떠 있는 서버들이 `f3fd785`보다 오래됐다.** 그래서 F9 어드민 화면은 `93610cb` 이후로도
  한동안 「조회 실패」만 보였다 — 코드 결함이 아니라 프로세스 나이다. 404를 「재시작하세요」로
  가르는 이 라운드의 절반이 바로 그 관측에서 나왔다.
- **모집단 이름이 서버의 어휘 단어 그대로 렌더된다.** 클라가 지어낸 한국어가 아니다.
  계약상 옳지만 선택의 여지가 없었던 이유는 **서버가 그 라벨을 아직 내보내지 않기** 때문이다
  (`vocabulary.population_labels`가 비어 있다). 클라가 대신 지어내는 것이 이 리포트가 막으려는
  바로 그 부류다.
- **`93610cb`은 `dist`를 함께 실었고, `cde3398`은 서버만 만졌으며, `1dc761b`이 다시 빌드했다.**
  그 재빌드는 콘텐츠 해시를 동일하게 재현했다 — 이미 최신이었다는 뜻이다. 그 번들은 이 라운드
  만이 아니라 **맵 라운드까지 함께** 나른다.
- **토큰 모달이 뜨지 않는 관측은 미해결이다.** 위의 반증된 설명 말고는 원인이 확정되지 않았다.
- **`1dc761b`·`cde3398`의 커밋 본문에 서버 스위트 수치가 없다.** `cde3398`이 만진 서버 코드는
  CORS 한 줄이다.
