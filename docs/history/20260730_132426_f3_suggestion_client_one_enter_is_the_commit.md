# F3 클라 절반 — 접두어 + Enter 한 번, 그리고 그 Enter가 **커밋 그 자체**여야 한다

> **일자:** 2026-07-30 13:17~13:24 | **커밋:** `77a2c15` · `847ceaf` · `e14b1d0` | **담당:** Client PM | **검수 등급:** T2(QA 투입 → GO-WITH-FIXES)
> **대상:** `client2/src/value_suggest.js`(신규 662줄 → +19 → +29/−…) · `client2/src/grid.js`(+28) · `client2/src/style.css`(+115) · `client2/package.json` · `client2/tests/value_suggest_keys_harness.mjs`(신규 1077줄 → +34/−…)
> **선행:** 서버 절반 `20260729_213000_f3_unique_value_lookup.md` · Ctrl+Enter 대량 채우기 `883b680`
> **보드:** `82114da`(F3 양쪽 종료) · `850b9d2`(QA HIGH 둘 등재) — 판정 근거는 거기 있다
> **후속 기록:** 같은 라운드의 두 사고는 별도 항목이다 —
> `20260730_132737_server_test_swept_up_by_a_client_commit.md` ·
> `20260730_135043_two_escapes_past_a_green_instrument.md`

## 배경 — 이 기능은 **산술로 미리 판정할 수 있는** 기능이다

전부 타이핑하면 `N`타. 제안을 쓰면 `P + 1`타(접두어 P + Enter). 따라서
`P <= N − 2`이면 이기고 **절대 지지 않는다.** 단 한 가지 조건이 붙는다 —
**후보를 받아들이는 Enter가 셀을 커밋하는 Enter와 같아야 한다.** Enter가 둘이면 비용이
`P + 2`가 되어 **모든 사용이 +1을 지불하고 기능이 뒤집힌다.**

그래서 이 라운드의 수용 기준은 성능이 아니라 **한 번의 Enter**였다.

## 변경 ① — 순서를 타이머가 아니라 프레임워크의 자기 순서에서 가져왔다

```js
// grid.js — processCellKeyboardEvent는 suppressKeyboardEvent를 cellCtrl.onKeyDown보다 먼저 본다
if (params.editing && isSuggestEditorActive()) {
  const verdict = handleEditorKey(event);
  if (verdict === 'suppress') return true;   // the list consumed the key
  if (verdict === 'accepted') return false;  // let THIS event commit the candidate
  // 'pass' falls through to the pre-existing branches below, unchanged.
}
```

AG-Grid의 `processCellKeyboardEvent`가 `colDef.suppressKeyboardEvent`를
`cellCtrl.onKeyDown`**보다 먼저** 상의하고, `onKeyDown`의 Enter 갈래가 `stopEditing` →
`getValue()`를 부른다. 그래서 훅이 후보를 입력창에 써 넣고 "진행하라"를 돌려주면 **같은 이벤트
디스패치가** 그 값을 커밋한다. 받아들이기와 커밋이 **구성적으로** 한 번이다 — 타이머도
마이크로태스크도 없다. `return false`는 포기가 아니라 커밋이다.

컬럼 범위는 좁게 잡혔다: `string`만. `number`는 `agNumberCellEditor`가 이 그리드의
`valueSetter`가 의존하는 수치 검증을 나르고 있고, `datetime`은 엔드포인트 자체가 거절한다.
서버는 수치 접두어도 지원하므로(`_numeric_values`) 확장은 이 술어 한 줄의 변경이지만, 숫자
검증을 에디터 안에 다시 구현하는 일이 딸려 온다.

## 변경 ② — 빈 접두어는 **서버보다 엄격하게** 클라에서 거절한다

서버의 `min_prefix_length` 기본값은 0이지만 클라는 `MIN_PREFIX_LEN = 1`이다. 접두어가 없으면
첫 후보가 임의값이고, 그러면 "Enter는 옳다"가 **"Enter는 동전 던지기"**가 된다. 임의의 기존값을
쓰는 Enter는 기능이 없는 것보다 나쁘다. 규율은 한 방향이다 — **서버보다 엄격하게, 절대 느슨하지
않게.** 그래서 서버가 최소값을 올리면 클라가 그것을 발견하고 따른다(`columnFloor`).

## 변경 ③ — 요청 수가 타이핑당 하나다

`REQUEST_LIMIT = 12`이고 이 숫자는 **지연 계약**이다. 엔드포인트 비용이
`0.84 ms + 0.61 ms × (limit + 1)`이고 그 97%가 DB가 아니라 Python/SQLAlchemy다 — 행 수에
평평하고(n의 136배 범위에서 12.4% 분산) limit에 선형이다. 20은 15.3 ms로 어느 테이블 크기에서도
10 ms 예산을 넘고, 12는 약 8.7 ms다. 산술도 같은 방향을 가리킨다: 위치 k의 후보는 도달에 k타가
드니 **N−1 위치를 넘는 후보는 원리적으로 본전을 못 넘는다.**

빠르게 치면 90 ms 트레일링 디바운스가 접두어 전체를 합치고, 느리게 치면 **더 짧은 접두어의
COMPLETE 답을 로컬에서 좁힌다** — 서버의 긴 접두어 답은 짧은 접두어 답의 부분집합이므로.
단 **ASCII로 제한된다.** ASCII 밖에서 `lower()`와 `toLowerCase()`는 서로 다른 함수이고, 어떤
값들이 같이 접히는지는 DB만 안다.

취소 뒤에 **시퀀스 가드**가 하나 더 있다. 내용 비교는 **같은 접두어**에 대한 두 요청을 구분할 수
없고, 앞으로 쳤다가 지우면 정확히 그 형태가 나온다.

## 🔴 브라우저 E2E가 하네스가 놓친 결함을 찾았다 (`77a2c15` 안에서)

좁히기 스냅샷이 **셀 편집보다 오래 살았다.** "DEV"를 커밋하고 다음 셀에서 "DEV"를 치면 그것을
다시 제안하지 않았다 — 운영자가 새 값을 넣는 순간 기능이 그 값을 모르게 된다. 수리는 에디터
teardown에서 스냅샷을 버리는 것이고, 대가는 셀당 요청 하나다. 무엇이 바뀌었는지 추론하지
않는다.

## 변경 ④ — 진단이 빌드에서 사라지고 있었다 (`847ceaf`)

`getSuggestStats`/`resetSuggestStats`에 `client2/src` 안의 호출자가 없어서 **번들러가
tree-shake로 지워 버렸다.** `effort_meter.publishDiagnostics`가 닫으려고 쓰인 바로 그 함정이
다음 모듈에서 다시 걸렸다.

```js
try {
  if (typeof window !== 'undefined') {
    window.__assySuggest = { getSuggestStats, resetSuggestStats };
  }
} catch (err) { /* diagnostics must never break the page */ }
```

가설이 아니었다: 이 라운드의 브라우저 E2E에서 `window.__assySuggest`가 undefined였고, "그
접두어가 요청 몇 개를 썼나"를 콘솔에서 `fetch`를 손으로 감싸서 답해야 했다. `window`에 대한
대입은 실재하는 참조라 흔들려 나가지 않는다. 이후 :8081에서 느리게 세 글자를 치면 제품 자신의
카운터가 `{requests: 1, localNarrows: 2, aborted: 0}`을 보고했다.

## 변경 ⑤ — teardown이 후계자가 소유한 싱글턴을 놓아 버렸다 (`e14b1d0`, 자기 검수 발견)

`destroy()`가 공유물 셋을 **무조건** 놓았다 — 하나뿐인 플로팅 리스트, `active` 등록,
진행 중인 요청 하나. 그중 등록만 정체 가드를 갖고 있었다.

```js
const wasActive = active === this;
if (wasActive) this.closeList();
...
if (wasActive) active = null;
// 좁히기 캐시 삭제는 무조건이다 — 캐시 항목을 버리는 것은 요청 하나를 더 쓸 뿐 정확성 비용이 없다
completeResults.delete(colKey(this.table, this.column));
if (wasActive) abortInflight();
```

후계 에디터가 선행자보다 먼저 생성되면 선행자가 **살아 있는** 리스트를 비우고 **살아 있는**
요청을 취소한다. 증상은 **드롭다운이 나오지 않는 셀 하나이고 콘솔에는 아무것도 없다.**

경계선은 한 줄이다 — **인스턴스가 소유한 것은 항상 놓고, 공유 싱글턴은 `active === this`일 때만
놓는다.** 캐시 삭제만 무조건인 이유가 그 규칙을 증명한다: 그것은 정확성이 아니라 요청 하나를
잃는다.

**변이 스윕이 여기서 두 번 밥값을 했다.**

- 가드 조건 이름을 바꾸자 M13의 검색 문자열이 매칭을 멈추고 실행이 `18 of 19 APPLIED`를
  보고했다 — APPLIED/CAUGHT 분리(`cb8f01a`)가 존재하는 이유인 **조용한 무장 해제** 그 자체다.
- M19의 첫 판은 **ESCAPED**했다. 선행자가 건드리지 않는 인스턴스 플래그 `second.listOpen`에
  단언을 걸었기 때문이다. 손상은 **공유 DOM**에 나므로 단언이 샌드박스 document에서 리스트
  요소를 읽어야 했다. **엉뚱한 관측 대상을 겨눈 단언은 통과한 단언과 구별되지 않는다.**

## 검증 — 이 항목을 쓰며 HEAD에서 다시 돌렸다

```
node client2/tests/value_suggest_keys_harness.mjs
  baseline assertions : 54 passed, 0 failed
  mutations declared  : 19
  mutations APPLIED   : 19
  mutations CAUGHT    : 19
```

커밋들이 주장한 수와 일치한다. 하네스는 실제 에디터와 실제 훅을 **AG-Grid 키보드 파이프라인의
모형**에 걸어 돌리고(모형은 `ag-grid-community@35`의 네 지점에 대해 함수명 기준으로 충실하다),
`prebuild`에 배선됐다 — **아무도 돌리지 않는 하네스는 주석이다.**

`77a2c15`가 :8081 격리 스택에서 실측한 점수: 같은 실제 교정
(`inventory_master.category` "aaa" → `DEVENV_ISO_PROBE_7f3c1a9e`)에 대해 **전부 타이핑 26타 vs
접두어+Enter 2타**, 마우스는 양쪽 1회. 두 번째 후보까지 화살표 하나면 3타이고, `Ctrl+Enter`는
받아들인 25자 값으로 세 셀을 총 5타에 채웠다. 두 점수 모두 V1 계기 자신의 카운터에서 읽었다.

거절 컬럼(4xx)과 답할 수 없는 컬럼(`unavailable_reason`)은 리스트도 토스트도 에러도 없이 평범한
타이핑으로 떨어진다 — **이 배포에는 엔드포인트가 정당하게 거절하는 편집 가능 컬럼이 없으므로**
두 경로를 브라우저에서 결함 주입으로 실제로 몰아 확인했다.

## `dist`가 이 커밋들에 없는 것은 판단이었다

공유 작업 트리에 다른 에이전트 둘의 진행 중 작업이 있어서, 이 빌드가 만든 번들은 그것으로
오염돼 있었다. 그리드 페이지 자신의 번들은 깨끗함을 확인했고(`index.html`이 어떤 map_editor
청크도 참조하지 않는다) 그래서 위 측정값이 선다. **그 판단이 나중에 다른 값을 했다** —
`850b9d2`가 기록한 대로, QA HIGH가 걸린 뒤 `dist` 미커밋 상태가 그 결함을 운영자 손에서
막아 주는 것이 됐다.

## 그때 남아 있던 것

- **QA HIGH 둘이 미수리 상태다**(`850b9d2` 등재). `Esc`가 타이밍에 따라 갈리는 문제이고,
  기제와 하네스가 그것을 볼 수 없었던 이유는
  `20260730_135043_two_escapes_past_a_green_instrument.md`에 있다.
- **MEDIUM 넷도 함께 등재됐다.** 그중 `unavailable_reason` 경로에 백오프가 전혀 없는 것 —
  비용이 0인 4xx 경로만 4-strike 래치를 받았다 — 이 F7(무음 저속) 상태의 컬럼과 만나면
  17자 lot id에 요청 17개, 각각 217 ms~1.9 s 동안 풀 커넥션을 잡는다. 피해자는 제안과
  가시적 연관이 없는 다른 요청들의 `pool_timeout`이다.
- `REQUEST_LIMIT = 12`는 지연 예산으로 골랐고, **truncated 답을 더 자주 만든다는 두 번째 효과는
  이 커밋 시점에 인지되지 않았다.** truncated 답은 캐시되지 않으므로 대부분의 타이핑에서 요청이
  떠 있는 상태가 된다 — `850b9d2`가 이것을 HIGH와 같은 방향으로 묶었다.
- `e14b1d0`이 자기 라운드가 아닌 서버 테스트 삭제 495줄을 함께 스테이징했다. 별도 항목이다.
