# 다섯 갈래가 walk 하나가 됐고, 표는 «선언» 둘이 됐으며, 프레임이 선언한 180을 아무도 안 읽고 있었다

> **커밋:** `896558da` (08:20) · `f9abae59` (08:29) · `5c2c7e7d` (08:35) · `99bd4da0` (08:36)
> · `19ca2ffc` (08:41) · `37694126` (08:44) · `d6bc18f8` (08:53)
> | **일자:** 2026-08-24 아침
> **레인:** 클라(R&D 보드)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 소유자가 그린 데이터 흐름에는 «갈래»가 없다

`api.js`에 라우트 갈래가 다섯이었고 부품마다 원하는 것을 임포트했다. 소유자 도식에는 그런
모양이 없다 — **같은 walk, 다른 선언**이다.

`896558da`가 다섯을 없앴다: `fetchSubgraph` · `fetchComposition` · `fetchTrends` ·
`fetchSiblings` · `fetchLotMap`(그리고 모델 함수 셋). 부품 파일 **여섯**이 임포트 줄을
`import { createWalk } from './api.js';` 하나로 바꿨다. 남은 것은 **함수 하나 + 여섯 칸짜리
`COLLECTS` 표**(`trend_y` · `candidate` · `wafer_process` · `map` · `basis` · `peer`).
각 칸이 `{ params: (start) => …, run: (params) => … }`이고, `createWalk(deps)`가
`apiBase`/`fetchImpl`을 한 번 묶고 **진행 중인 promise 만** 공유한다.
**아무도 선언 안 한 collect 는 null 이 아니라 «거절»** 이다.

실측: 라이브 보드 한 로드에 요청 **13**, 유일한 반복은 collect 둘 아래의 구성 URL.

## 표를 «두 번 손으로» 그린 것을 하나의 템플릿 + 선언 둘로

같은 화면의 표 둘이 머리·행높이·줄수·구분선·정렬·상태 표기가 전부 달랐다. `d6bc18f8`이
`client2/src/rnd_board/table_part.js` 하나를 만들고 표 둘을 **선언 둘**로 바꿨다.

```js
// composition_panel.js — 컬럼 선언
{ key: 'wafer',  label: '코어 웨이퍼', width: 'minmax(11rem, 16rem)', kind: 'mono' },
{ key: 'events', label: '이력',       width: '4rem',                 kind: 'number' },
{ key: 'state',  label: '상태',       width: '7rem',                 kind: 'badge' },
```

머리와 행이 같은 `_template()`을 쓰므로 **어긋날 수가 없다.** 부재 규칙이 못 박혔다 —
`isAbsent`는 `null`·`undefined`·`''`뿐이고 **`0`과 `false`는 값이다.**

## 🔴 프레임이 `rotation: 180`을 선언하는데 클라 어디에도 그 낱말이 없었다

`f9abae59`. `grep rotation client2/src/rnd_board/*.js`가 **0**을 답했다. 결과 둘:
본딩 웨이퍼가 **거꾸로** 그려졌고, 눈에 보이는 쪽으로는 **저장 좌표가 격자 기준이 아니라
«상자» 기준**이라 그것을 격자 인덱스로 앉히면 원반이 아니라 **구석의 네모 덩어리**가 그려졌다.

수리는 `seatFrameOfGrid`(격자 메타데이터의 순수 전사, `rotation: Number(grid.rotation) || 0`)와
`seatedProjection`을 더해 `client2/src/map2/seating.js`의 `computeSeating`/`visualExtent`에
위임한다 — 그 파일 자체가 `server/utils/coordinate_transformer.py`의 전사다.
커밋이 함께 적은 결과: **본드 (3,4)와 코어 (3,4)는 서로 다른 물리적 다이다.**

## 🔴 그릴 수는 있어도 마킹은 안 되는 자리 — 「찍힌 id」

서버가 노드 id 를 안 준 lot_map 셀에 클라가 자리표시자를 찍고 있었다:

```js
// client2/src/rnd_board/api.js
const STAMPED_PREFIX = 'unresolved-die:';
export function isStampedNodeId(id) {
  return typeof id === 'string' && id.startsWith(STAMPED_PREFIX);
}
```

**그리기에는 맞고 마킹에는 틀리다** — 마킹은 다음 walk 의 «주어»이기 때문이다. 거절이 둘 붙었다:
`fetchSubgraph`가 **네트워크를 타기 전에** `reason: 'seed_is_not_a_server_node'`로 돌려주고,
`map_panel.js`의 `clickAt`이 `cell.nodeIdResolved !== true`에서 막고 표시한다.
문장은 서버 거절과 **일부러 공유하지 않는다** — 「이 자리는 아직 원장 노드가 아닙니다 —
그릴 수는 있어도 마킹은 안 됩니다」. **라우트가 진짜 id 를 싣는 날 게이트는 스스로 열린다.**

## 아키텍처 영향

- 부품이 **라우트 이름을 안 부른다.** `start`와 `collect`를 선언하고 walk 은 하나다.
  fetch 함수 다섯이 사라졌다.
- **표 부품이 템플릿 하나**고 화면의 표들은 컬럼 선언이다.
- 맵이 **선언된 프레임**(회전·격자 반전·면·오프셋) 위에 앉는다. 좌표 전사가 서버 변환기와
  같은 규칙이다.
- 서버 노드가 아닌 자리는 **마킹 경로에서 이름 붙여 거절**된다.

## 그때 남아 있던 것

- `5c2c7e7d` 시점에 **부호 붙은 집합에 호출자가 없었고**(부품이 넘겨야 생긴다) **dist 도
  안 빌드했다** — 그 커밋 시점에 화면에는 아무것도 없었다.
- 후보 트렌드가 **메인 트렌드와 같은 계열을 그린다** — `trends`가 subject 를 안 받기 때문.
  배선은 맞고 재료가 없다(`19ca2ffc`).
- `896558da`의 「거짓 대시 여섯을 없앴다」에서 **여섯이라는 수는 diff 로 확인되지 않는다**
  (diff 는 `count: null` → `count: undefined` 두 자리를 바꾼다). 기전은 확인된다 —
  `_pill`은 `spec.count !== undefined`일 때만 개수 요소를 붙인다.
- 시험 하나가 빨갛고, 변경을 stash 해도 **HEAD 에서 똑같이 빨갛다.**
