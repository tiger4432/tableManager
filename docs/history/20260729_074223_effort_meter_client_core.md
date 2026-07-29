# V1 계기 계측 — 클라이언트 코어(수집기 모듈 + 메인 그리드 배선)

> 2026-07-29 · client-pm · 대기열 0번(V1 계기 계측)의 **클라 코어 절반**. 맵/계획 절반은 map-pm, 수신 절반은 server-pm이 같은 계약으로 동시 진행.

## 현상 / 배경

SSOT §1의 핵심가치 #1은 「최소 공수 교정」인데, 그것을 **직접 재는 계기가 없었다.** 2026-07-29 사용자가 정본 계기를 **「완료까지의 상호작용 점수」**(키 1 · 마우스 3 · 컨텍스트 상실 이동 5, 낮을수록 좋음)로 교체했다.

이 값은 **소급 산출이 불가능하다** — 과거 세션에 클릭 로그가 없다. 따라서 UI 개선 라운드(R1)보다 **먼저** 머지돼야 "before"를 얻을 수 있다. 계기는 게이지일 뿐 아니라 **설계 목표**이기도 하다: 배점이 마우스 3·이동 5이므로 드롭다운·입력 추천·prefill·범위 일괄 채우기가 "클릭하고 타이핑하기"보다 **눈에 띄게 좋아 보여야** 한다.

조사 결과 클라이언트에는 재사용할 프리미티브가 **전무**했다: `sessionStorage` 사용 0건, 상호작용 카운터 0건, 텔레메트리 0건. 유일한 UUID 생성기는 `enrichment.js:64`의 모듈 지역 `newSessionToken()`인데 이는 **서버 쓰기 동시성 가드**이지 세션 id가 아니고 영속되지도 않아 재사용 불가였다. → 신규 모듈이 정당화됨.

## 해결

### 1. 유일한 수집기 `client2/src/effort_meter.js` (신규)

총괄 소유 계약 API 6개(`startSession`/`countKey`/`countMouse`/`countNav`/`snapshot`/`commit`) + 부가 헬퍼. **복제 금지**가 핵심 규율 — 중복 상수 목록은 U6 라운드에서 6건을 삭제한 전력이 있다. 경로↔라우트 매핑표와 전역 리스너를 **모듈 안에** 둬서 각 페이지가 자기 사본을 만들 이유를 없앴다(실제로 map-pm이 같은 헬퍼를 그대로 소비했다 — 수동 `countKey`/`countMouse` 0건, 이중 계산 없음).

**깨지기 쉬운 불변식 5가지:**

1. **성공에만 리셋** — 저장이 실패하면 계속 누적한다. 재시도 공수도 사람의 진짜 공수이고, 시도 시점에 리셋하면 *실패하는 저장이 싸 보인다*.
2. **같은 탭 새로고침에서 생존** — 교정 도중 새로고침이 사람의 작업을 되돌리지는 않는다(`sessionStorage`, 탭과 함께 소멸).
3. **기본은 "상실(계산됨)"** — 설정이 없거나 404거나 파싱 불가면 **전부 계산**한다. 절대 "0점"으로 fail-open 하지 않는다.
4. **분류는 버리지 않는다** — 총괄 계약 보정(2026-07-29). 면제 전이도 `nav_preserved`로 계속 센다.
5. **사용자에게 보이지 않음** — 새 UI·배지·토스트 0건.

### 1-bis. 계약 보정 — `nav_preserved` (총괄, 2026-07-29)

초기 설계는 "원시 카운트를 저장하고 배점은 조회 시점에"라는 원칙을 세워놓고, **전이 분류만은 수집 시점 결정**으로 만들어 놨었다 — 면제된 전이는 `nav`를 증가시키지 않고 그냥 사라졌다. 총괄이 이 불일치를 지적했고, 배점보다 이쪽이 더 위험하다: **이 계기는 소급 산출이 불가능**하므로 오늘 잘못 면제한 전이는 **베이스라인에서 영영 복구할 수 없다.**

```js
export function countNav(fromRoute, toRoute) {
  const key = transitionKey(fromRoute, toRoute);
  if (!key) return;
  const s = ensure();
  if (preservingSet.has(key)) s.nav_preserved += 1;   // 유지(현재 0점)
  else s.nav += 1;                                     // 상실(점수 대상)
  flush();
}
```

와이어 형태는 `effort: {session_id, key, mouse, nav, nav_preserved}`. 둘 다 원시 카운트이므로 allowlist는 **조회 시점의 해석**이 된다 — 나중에 `grid > trace`를 세야 했다고 판단해도 데이터가 남아 있다. 클라 분류 로직 자체는 그대로 두고 **버리는 동작만 제거**했다.

**평문 HTTP 함정 처리** — `crypto.randomUUID`는 **보안 컨텍스트 게이트**라 사내망 평문 HTTP 운영에서 `undefined`다(`navigator.clipboard`를 죽인 그 함정). `crypto.getRandomValues`는 게이트가 아니므로 이쪽이 실질 주경로다:

```js
function newSessionId() {
  try { if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID(); }
  catch (err) { /* secure-context gated — fall through */ }
  // crypto.getRandomValues is NOT gated → the real primary path in production.
  ...b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;  // v4
```

**와일드카드 거부** — 하니스가 잡아낸 실제 결함. `'*>*'` 항목이 리터럴 키로 **집합에 남아** 있었다. 무해하게 작동하지 않을 뿐이지만, 설정 작성자는 `getConfig()`에서 항목을 보고 *적용됐다고 오해*한다. → `transitionKey`에서 `*` 포함 시 거부해 **눈에 보이게 탈락**시킨다.

### 2. 메인 그리드 배선

**쓰기 5경로 전부**에 `effort: snapshot()` 첨부 + `res.ok`에서만 `commit()`:
`api.js`(단건 편집) · `main.js`(Tx 일괄 적용) · `ui.js`(범위 값 채우기) · `clipboard.js`(붙여넣기 / 셀 비우기).

**이동 계측** — 내비 앵커 4건(위임 리스너), Enrichment 배지, 테이블 전환, 뷰모드 전환, `navigateToLog`, 추적 새 탭.

> 테이블 전환은 `switchTable()` **안이 아니라** `main.js`의 `change` 리스너에서 센다 — `switchTable`은 부팅 자동선택과 `navigateToLog`에서도 호출되며 둘 다 사용자의 이동이 아니다(오계수 방지).

**Enrichment 배지의 목적지 id 분리** — 배지는 `?rule=`을 실어 사용자가 **클릭한 바로 그것**에 착지시키는 targeted continuation이지만, 규칙 없이 누르면 일반 큐로 떨어진다. 두 경우가 한 키(`grid > enrichment`)를 공유하면 **한쪽 방향으로는 반드시 틀린다** → `enrichment:rule`(면제) / `enrichment`(계산)로 분리.

### 3. Enrichment 컨베이어 계측 (`enrichment.js`)

`saveCurrent`의 PUT은 **교정 쓰기 경로**이므로 계측 범위 안이다(총괄 판정). 같은 패턴으로 `effort` 첨부 + 성공 시 `commit()`, 페이지 진입 시 `startSession`/`installGlobalListeners`/`installNavLinkCounting`.

`commit()`은 **stale 가드보다 앞**에 둔다 — 저장 중 규칙이 바뀌면 UI 반영은 건너뛰지만 **서버는 이미 커밋했고 공수도 이미 보고됐다.**

규칙 전환은 `selectRule()` 안이 아니라 `change` 핸들러에서 센다(부팅 딥링크가 같은 함수를 부른다). 새로고침 버튼은 **같은 규칙 재조회**라 이동이 아니므로 세지 않는다.

## 검증

- `client2/tests/effort_meter_harness.mjs` (vm 샌드박스, node_modules 불필요) — **71/71 통과**.
- **변이 검사 3종**(하니스가 진짜로 회귀를 잡는지 자기 점검): ① `snapshot()`이 리셋하도록 ② 설정 실패 시 fail-open 하도록 ③ 면제 전이를 버리도록 일부러 고장 낸 소스를 넣어 **셋 다 검출됨을 확인**. 검출되지 않았다면 위 단언들은 아무것도 증명하지 못한다.
- ⚠️ **변이 검사가 자기 자신의 노후화를 잡았다** — `nav_preserved` 도입으로 소스가 바뀌자 변이 A·B의 타깃 문자열이 어긋나 `replace`가 **조용한 no-op**이 됐고, "고장 낸 버전"이 사실은 정상 버전이라 검사가 통과해 버렸다. 이제 **변이가 실제로 소스를 바꾸지 않으면 에러를 던진다** — 이 부류는 한 번 발생하면 다시는 눈에 띄지 않는다.
- 실패 경로를 실제로 실행: 설정 fetch 거부·404·가비지 항목·설정 도착 전 레이스·`sessionStorage` 읽기/쓰기 throw·손상 JSON·비보안 컨텍스트(randomUUID 부재/throw/crypto 전무) 전부 별도 시나리오로 통과.
- `npm run build` 성공(경고 2건은 기존 것 — `INEFFECTIVE_DYNAMIC_IMPORT`, 청크 크기).
- 번들 실측: `assy.effort`·`api/effort/config` 각 **1개 청크에만 1회**(수집기 단일성 확인), `main` 번들에 `effort:` 첨부 **정확히 5회**(쓰기 5경로와 일치).
- 서버 계약 대조: `get_public_config()`가 `{weights, context_preserving_transitions}`를, 전이를 `{from,to}` **객체 형태**로 서빙 — 클라 파서가 문자열/객체 양쪽을 수용하므로 호환. `effort`는 `Optional[EffortReport]`(미계측 = 없음, 0 아님)이고 서버가 `session_id` 비어있음·비정수·음수를 400으로 거절하는데, 클라 `toCount`가 항상 **0 이상 정수**를, `ensure()`가 항상 비어있지 않은 `session_id`를 보장한다.

### 사이드 이펙트 전수 분석

- **이벤트 흐름**: 전역 리스너는 전부 `capture` + `passive:true`. `passive`라 **`preventDefault` 호출이 브라우저 차원에서 불가능**하고 `stopPropagation`도 하지 않는다 → 과거 Ctrl+C keydown 분기가 `copy` 핸들러를 굶겼던 사고를 **구조적으로** 반복할 수 없다. `clipboard.js` 드래그 선택/`map_editor.js` 페인팅의 `mousedown`도 무간섭.
- **공유 상태**: `state.js` 미변경. 카운터는 자체 모듈 + `sessionStorage`에만 산다.
- **확장성(§2)**: 페이로드는 배치 크기와 **무관하게 스칼라 4개** — 10,000행 붙여넣기도 동일. 새 쿼리·루프·전량 로드 0건.
- **경계 계약(§1)**: 엔드포인트 경로·WS 이벤트·셀 형태 `{value,is_overwrite,priority_source}`·`/schema` 응답 **전부 무변경**. `effort`는 기존 PUT에 얹은 **선택 추가 필드**뿐이며 별도 텔레메트리 요청을 만들지 않았다.

## 미해결 / 다음 단계

- **`context_preserving_transitions` 승인 완료, 서빙 설정 설치는 미완**. 총괄 승인 3건 + 배지 1건:
  `map_editor > map_editor:material` · `map_editor:material > map_editor` · `grid > trace` · `grid > enrichment:rule`.
  `server/config/effort_metric.json`은 **아직 존재하지 않는다**(`.sample`만 있음) — 설치는 server-pm/총괄 소관이며, 미설치 상태에서는 전부 `nav`(상실)로 계산된다(안전한 기본값).
- **`grid > grid:log_jump`는 의도적으로 면제하지 않음** — 테이블을 넘나들 수 있어 사용자의 자리를 잃는다. `nav_preserved` 분리 덕에 **되돌릴 수 있는 판단**이 됐으므로 데이터가 쌓인 뒤 재검토한다.
- **동시 저장 이중 계상**: 비-Tx 모드에서 저장 2건이 겹치면 같은 공수가 두 tx에 실린다(리셋 전 스냅샷). **부풀리는 방향**이라 안전하지만 노이즈다.
- **모달은 화면 이동으로 세지 않는다**(총괄 확정) — 아래 화면이 그대로 남아 컨텍스트가 구조적으로 보존되고, 열고 닫는 클릭은 이미 마우스로 계산된다.
- **`admin.js`는 미계측** — 교정 표면이 아니라 운영 화면이라 이번 범위 밖.
- 화면 표시(어드민 Overview 등)는 아직 없다 — 이번 라운드는 **수집만**.

---

# 수리 라운드 (2026-07-29, QA 레인 A 지적 반영)

QA가 라이브 프로브로 확인한 결함 3건(F2·F1·F3)과 표시면 부재(F5)를 고쳤다. **셋 다 점수를 낮추는(계기를 미화하는) 방향**이었고, **셋 다 조용했다.** 기준선을 잴 창은 한 번뿐이라 미화 방향의 침묵이 가장 위험하다.

## F2 — 빈 스냅샷이 "측정된 0점 교정"으로 저장되던 문제

서버는 명시적 0을 **측정된 값으로 받아들인다**(의도된 동작 — 진짜 무공수 교정은 의미가 있다). 그런데 클라의 모든 호출부가 `snapshot()`을 **무조건** 실어 보내서, 누적이 하나도 없는 저장이 **진짜 0점 교정**으로 기록됐다. QA 실측: 진짜 교정 1건(37점) + 유령 1건 → `avg_score: 18.5`. 기준선이 절반이 됐다.

수정은 계약이 이미 가진 프리미티브(**부재 = 미계측**)를 재사용한다 — 새 규칙도, 서버 변경도 없다:

```js
export function snapshot() {
  const s = ensure();
  if (!s.key && !s.mouse && !s.nav && !s.nav_preserved) return undefined;
  ...
}
```

`effort: snapshot()`이 `undefined`면 `JSON.stringify`가 **키째 지운다.** 가드를 7개 호출부가 아니라 **수집기 안**에 둔 이유가 이것이다 — 여덟 번째 호출부가 잊을 수 없다.

판정은 **원시 4카운트**로 하며 점수로 하지 않는다. `nav_preserved`만 있는 세션은 오늘 0점이지만 실제로 일어난 일이고, 그 원시 카운트가 바로 나중에 재채점할 근거다(점수로 판정했다면 `nav_preserved` 도입 취지를 스스로 무너뜨렸을 것이다).

## F1 — no-op 저장이 그 저장에 든 공수를 지우던 문제

이미 같은 값이 든 셀에 같은 값을 다시 쓰면 서버는 `200 {change_count: 0, created_logs: []}`을 주고 **공수 행을 쓰지 않는다**(교정이 일어나지 않았으므로 옳다). 그런데 클라는 `res.ok`만 보고 `commit()`했다. 결과: 키 20 + 클릭 5가 사라지고, 화면이 안 바뀌는 걸 본 작업자가 키 3 + 클릭 1로 다시 하면 **두 번 시도한 교정 — 마찰이 가장 큰 사건이자 이 계기의 존재 이유 — 이 데이터셋에서 가장 낮은 점수를 기록한다.**

server-pm이 응답에 `effort_recorded: bool`을 추가했고, 클라는 그걸 보고 판단한다:

```js
export function commitIfRecorded(resBody) {
  const recorded = resBody && typeof resBody === 'object' ? resBody.effort_recorded : undefined;
  if (typeof recorded === 'boolean') { if (recorded) commit(); return recorded; }
  commit();   // 필드 없음(구 서버) → 종전 동작
  return true;
}
```

**필드가 없으면 종전 동작으로 되돌아간다** — 영영 리셋하지 않으면 카운터가 무한히 자라 한 세션의 브라우징 전체가 나중의 저장 하나에 청구되고, 그건 그 자체로 더 큰 결함이다.

7개 호출부 전부 `commit()` → `commitIfRecorded(result)`. 부수 효과로 `api.js`·`ui.js`·`clipboard.js`(2)는 `commit()`이 `await res.json()` **뒤로** 이동했다(응답을 읽어야 판단할 수 있으므로). `enrichment.js`는 성공 경로에서 본문을 읽지 않았어서 `res.json().catch(() => null)`을 추가했다 — 파싱 실패는 "필드 없음"과 같이 취급된다.

## F3 — 존재하지 않는 라우트를 지목한 허용목록 항목이 조용히 무력했던 문제

서버는 항목의 **형태만** 검증하고 라우트 어휘를 모른다. SSOT가 예시로 든 `{"from":"doe","to":"dt_map"}`은 **아무것도 면제하지 못한다**(실제 id는 `map_editor`·`map_editor:material`). 문제는 그 효과 — "전부 계속 계산됨" — 가 **정상 동작과 똑같이 보인다**는 점이다. 와일드카드 거부가 막으려던 바로 그 실패가 다른 축에 열려 있었다.

라우트 어휘는 클라가 소유하므로(`countNav` 호출부가 id를 만든다) 검증도 클라에 둔다. 신규 export `ROUTE_IDS`(기본 6 + 서브컨텍스트 5)와 대조해, 미지의 id를 지목한 항목은 **거절 + `console.error` + `getConfig().rejected_transitions` 노출**. 조용히 버리지도, 조용히 받아들이지도 않는다. 거절된 항목은 계산 쪽에 남으므로 편향은 **과대계상(안전)** 방향이다.

같은 기구로 와일드카드·형식 오류도 이유와 함께 보고된다(종전에는 조용히 탈락). ⚠️ 새 서브컨텍스트로 `countNav`를 부르면서 `ROUTE_IDS` 등록을 잊으면 그 전이의 면제 항목이 "미지"로 뜬다 — 안전한 방향이지만 실재하는 함정이라 코드 주석·`frontend.md`·설정 가이드 세 곳에 적었다.

## F5 — 표시면 신설 (어드민 Overview 「교정 공수」 한 줄)

`effort`·`measured_ratio`를 읽는 코드가 `client2/src` 어디에도 없었다. 서버가 기록 예외를 삼키는 것과 겹치면, **기준선 창 전체에 걸친 수집 중단이 아무 신호도 내지 않는다.**

재교정률 줄 바로 아래 **한 줄**(카드·패널·차트·새 탭 없음, 같은 `/dashboard/summary` 응답과 같은 5분 스로틀 공유). 상태별 문구가 다른 것이 요점이다:

| 서버 응답 | 표시 |
|---|---|
| 정상 | `37.3점` · 최근 7일 · 세션 12개 평균 · 교정 480건 계측(커버리지 82%) |
| 커버리지 < 50% 또는 미상 | 위 + "대표값으로 읽지 말 것" (warn) |
| `unavailable_reason` 있음 | `—` · **그 사유 그대로** (danger) |
| `measured_ratio === 0` | `—` · ⚠ 사람 교정은 있으나 계측 0건 — **수집 중단 경고** (danger, 사유 문장까지 붉게) |
| 표본 없음(`measured_ratio: null`) | `—` · 교정 없음 (muted) |
| 응답에 `effort` 필드 자체가 없음 | `—` · **서버가 보고하지 않음** (구 서버 — "교정이 없었다"고 지어내지 않는다) |

## 검증

- `effort_meter_harness.mjs` **110/110**, `effort_instrument_harness.mjs` **28/28**.
- **변이 3종 추가**(총 6종): ④ 빈 스냅샷을 0으로 실어 보내도록 ⑤ `effort_recorded`를 무시하고 항상 리셋하도록 ⑥ 미지의 라우트 id를 조용히 받아들이도록 고장 낸 소스를 넣어 **셋 다 검출됨을 확인**. 맵 배선 하니스에도 `M8`(서버 응답을 무시하고 커밋) 추가.
- 하니스 소스 로딩을 **LF 정규화**로 바꿨다 — 파일이 CRLF가 되자 다중행 변이가 적용되지 않았다(`loadMutated`가 던지므로 거짓 통과는 아니었지만, 그날의 에디터에 의존하는 검사는 검사가 아니다).
- **브라우저 실측**(vite dev 5173, 실제 모듈·실제 DOM·실제 CSS): 4개 페이지 콘솔 에러 0건. 실제 `effort_meter.js` 인스턴스에 설정을 주입해 F3 재현 — `{doe, dt_map}` 거절(사유에 두 id 모두 명시) + 콘솔 에러 + 유효 이웃 `map_editor>map_editor:material`은 정상 면제. F2/F1 재현 — 새 세션에서 본문에 `effort` 키 없음, no-op(`effort_recorded:false`) 뒤 키 20·클릭 5 생존, 재시도 합산 **점수 41**(결함 버전이라면 6).
- 어드민 한 줄은 **서빙된 `admin.js` 소스에서 `renderEffort`를 그대로 들어올려** 6가지 응답 형태로 실행 — 문구·톤 전부 확인(라이트/다크 양쪽).

## 미해결

- `server/config/effort_metric.json` 설치는 여전히 미완(미설치 = 전부 `nav`, 안전한 기본값).
- 동시 저장 이중 계상(부풀리는 방향) 그대로.
- `dist/` 재빌드는 총괄 통합 시점.

---

## 수리 라운드 2차 — QA 레인 B(브라우저 E2E) 지적

### B-F1 — 읽기 화면 3개가 미배선이라 왕복 이동이 절반만 기록됐다

`graph_viewer.js`·`admin.js`·`trace.js`가 수집기를 아예 import 하지 않았다. QA가 `/graph.html`에서 🏠 Main을 클릭해 `/`로 이동한 뒤 카운터가 **바이트 단위로 동일**함을 확인했다 — 전체 페이지 로드가 0점이고 클릭조차 세지 않았다.

문제는 누락이 아니라 **비대칭**이다: `grid → graph`는 세고 `graph → grid`는 안 셌다. 읽기 표면으로 나갔다 오는 왕복이 실제 비용의 절반만 기록되므로, 100점짜리 우회가 5점으로 남는다. 미화 방향이고, 이 모듈 헤더 불변식 3이 금지하는 바로 그 방향이다.

세 페이지에 `startSession` + `installGlobalListeners` + `installNavLinkCounting(ROUTES.X)`만 배선했다. **교정 쓰기가 없으므로 `effort` 페이로드는 어디에도 싣지 않는다** — 실을 요청 자체가 없다. 필요한 건 "나가는 것이 세어지는 것"뿐이다.

### B-F3 — `getConfig()`가 트리셰이킹으로 dist에서 사라졌다

`client2/src` 안에 호출자가 없어 번들러가 지웠다(dist에서 `loaded:` 0건). 운영 현장에서 **"허용목록이 비었다"와 "설정을 못 받았다"를 구별할 수 없었고**, 그 구별이 fail-closed 설계가 기대는 유일한 근거다. fail-closed **동작 자체는 옳았고 라이브에서 확인됐다** — 사라진 것은 어느 상태인지 아는 능력이다.

`startSession()`이 `window.__assyEffort = { getConfig, snapshot, ROUTE_IDS }`를 게시한다(실제 참조라 셰이킹 불가) + 설정 fetch 실패 시 `console.warn` 1줄. 화면 요소는 여전히 0개다.

### B-F5 — 서버가 버리는 형식을 클라가 받아주고 있었다

서버 `resolve_context_preserving_transitions`는 dict만 받는다. 클라는 `"from>to"` 문자열 축약도 honour 했다 — 작성자가 쓰면 **한쪽은 지키고 한쪽은 버리면서 아무도 알려주지 않는다**. 생산자보다 관대한 소비자는 관용이 아니라 **선언되지 않은 두 번째 계약**이다. 이제 객체 형식만 받고 문자열은 사유와 함께 거절한다.

### 총괄 지적 반영 — 과장된 서술 정정

"면제 전이를 버리지 않으므로 allowlist가 **조회 시점 해석**이 된다"는 서술은 과장이었다. **버킷은 수집 시점에 확정**되며 나중에 허용목록을 바꿔도 **이미 기록된 행은 재분류되지 않는다.** 조회 시점에 재해석되는 것은 **배점뿐**이다(두 버킷 다 원시 카운트이므로 `weights.nav_preserved`로 재채점 가능). 버리지 않는 것이 지키는 것은 재채점 가능성이지 분류의 되돌림이 아니다. 모듈 헤더 불변식 3-bis와 `frontend.md` §3.2를 그렇게 고쳤다(위 1차 수리 라운드 이전 절에 남아 있는 옛 표현은 당시 기록이라 그대로 둔다).

### 검증 (2차)

- `effort_meter_harness.mjs` **131/131**(변이 **8종** — G: 문자열 축약 재수용, H: 진단 미게시 추가), `effort_instrument_harness.mjs` 28/28.
- **§8b 배선 감사 신설** — 소스 레벨로 전 페이지를 훑어 ① 교정 경로가 bare `commit`을 import 하는가 ② 어떤 페이지가 수집기를 아예 import 하지 않는가 ③ 읽기 화면이 자기 라우트가 아닌 id로 세는가를 검사한다. import 절이 초크포인트다 — import 하지 않은 것은 호출할 수 없다. 이 감사 자체도 세 가지 역주입으로 자기 점검한다. (행동 테스트로는 "페이지가 수집기를 쓰는가"를 증명할 수 없어서 넣었다.)
- **브라우저 실측(QA 재현 그대로)**: `/graph.html` 🏠 Main 클릭 → `/` 착지, 카운터 `mouse +1 / nav +1`(종전 0/0). `/admin.html` Return to Main, `/trace.html` → Graph도 각각 +1/+1. 세 페이지 모두 `window.__assyEffort` 게시 확인, 8080이 `/api/effort/config`를 아직 안 서빙하므로 `loaded: false`가 **관측 가능**함도 확인.
- ⚠️ **리셋 경로 재확인(총괄 지시)**: 레인 B는 08:03 빌드(= `commitIfRecorded` 이전)를 봤으므로 그 증명은 현재 코드를 덮지 않는다. 실제 모듈로 브라우저에서 재확인 — no-op(`effort_recorded:false`) 뒤 키 20·클릭 5 생존, 재시도 합산 41점(결함 버전이면 6점), 진짜 저장·구 서버(필드 없음) 양쪽 리셋. 7개 호출부 전부가 게이트된 함수를 쓰는지는 §8b 감사가 import 절로 강제한다.
