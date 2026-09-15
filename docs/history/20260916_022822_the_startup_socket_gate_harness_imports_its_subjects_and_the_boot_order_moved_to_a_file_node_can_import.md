# 부팅 소켓 게이트 하니스가 대상을 «import» 한다 — 부팅 «순서»가 `startup.js` 로 나와 main.js 에 이름이 늘어도 하니스가 «전혀» 안 읽고, 비용은 0.7 초에서 36 초가 됐다 (C-110)

> **커밋:** `c96527d9` — test(client): C-110 - the startup socket gate harness imports its subjects instead of slicing them → main 병합 `bd6cb889`
> **일자:** 2026-09-16 02:28
> **레인:** «워크트리 서브에이전트»(클라 대행) — 클라 큐 소진(정지) 뒤 남은 등급 4 를 야간 에이전트에 → 「에이전트 첫째가 스스로 마무리」(보드 `11fea45e`) → 총괄 닫힘 `2c93ae9f`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** startup_socket_gate **111/0**(바닥 111 «그대로») · 변이 **9/9** 잡힘 · 대조군 **3/3** 탈출 · 실측 「main.js 에 `let` 하나 + `export function` 하나를 덧붙여도(바이트 그대로 복원) 111 · 9/9 · 3/3 동일」 · dist 재빌드 · 하니스 소요 **~36 s**(전 0.7 s) (커밋 본문). 총괄 확인 「111/0 · 변이 9/9 · main.js 에 이름을 더해도 초록(실측)」.

## ① 왜 — 하니스가 «글자 모양»을 재고 있었다

하니스는 main.js · api.js · websocket.js 를 «텍스트»로 읽어 함수 «열둘»을 정규식으로 잘라 `vm` 에서 돌렸다. 그 조각이 부르는 «모듈 수준 이름»은 하니스가 «손으로» 스텁을 심어야 했고, main.js 가 이름을 하나 얻을 때마다(`installAuditFilters` · `initGridSourceLabel` · `redoBannerFollows` — 09-15 가 마지막) 섹션 C 의 시나리오 «전부»가 옳은 코드에 ReferenceError 를 냈다. 하니스가 그때마다 스텁 한 줄과 앵커 한 줄을 «자랐다». 상설(2026-09-02)의 «정확히 그 모양»: 「import 를 하나 더하면 잘라낸 조각이 그 함수를 못 찾아 던진다」. 그리고 부팅 순서는 «import 안 되는 파일»(main.js — ag-grid 스타일시트를 import 하고 페이지 전체를 앉힌다)에 살고 있었다. 「대상이 import 가 안 되면 그것이 결함이다.」

## ② 변경 — 순서는 «파일 하나»로, 화면을 만지는 것은 «훅 둘»로

```js
// client2/src/startup.js — 모듈 최상단에서 DOM 도 CSS 도 안 만진다. 그것이 import 되게 하는 성질이다
import { initWebSocket } from './websocket.js';
import { checkServerHealth, loadTables } from './api.js';
export async function startup({ prepare, tableChosen }) {
  initWebSocket();          // «먼저». 그 뒤 무엇이 던지거나 멈춰도 소켓은 이미 열렸다
  prepare();                // main.js 의 설치 블록 «그대로» — 리스너 · 캐시된 설정 · 조립된 부품
  await checkServerHealth();
  await loadTables();
  tableChosen();            // 부팅 자동 선택도 «표를 고른 것» — 라벨과 배너에 알린다
}
```
```js
// client2/src/main.js — init() 은 «무엇을 설치할지»와 «표가 정해지면 누구에게 말할지»만 안다
await startup({
  prepare() { /* 옛 init 본문 그대로 — localStorage · initTheme · startSession · 리스너 · sourceLabel · redoBanner … */ },
  tableChosen() { if (sourceLabel) sourceLabel.setRelation(state.currentTable); redoBannerFollows(state.currentTable); },
});
```
```js
// client2/tests/startup_socket_gate_harness.mjs — 세 대상을 «통째로», 시나리오마다 «새 사본»
const apiLoad = await loadWithProbe(PATHS.api, { stubs: { './state.js': { state }, './dom.js': { elements },
    './grid.js': { renderGrid: () => { gridRebuilds++; }, ... }, ... }, mutate: mut.api, tag: 'sgapi' });
const wsLoad  = await loadWithProbe(PATHS.ws,  { stubs: { './api.js': { checkServerHealth: (...a) => api.checkServerHealth(...a), ... } }, ... });
const bootLoad = await loadWithProbe(PATHS.startup, { stubs: { './websocket.js': { initWebSocket: (...a) => ws.initWebSocket(...a) }, ... } });
boot.startup({ prepare: noop, tableChosen: noop }).then(...);   // await 하지 않는다 — 'hang' 시나리오가 그 이유
```
프로브(`lib/probe.mjs`)는 «덧붙이기 다리»다 — 파일을 바이트 그대로 복사하고 뒤에 접근자를 붙이며, 로드마다 «사본이 원본 바이트로 시작하는지» 단언한다. 잘라내는 양이 0. bare `import` 대신 프로브를 쓰는 이유 둘: hang 시나리오가 `tablesLoadInFlight` 래치에 «영원히 안 끝나는 약속»을 남겨 다음 시나리오를 «독으로» 물들이므로 시나리오마다 «새 모듈»이 필요하고, 변이는 «조각이 아니라 모듈 통째»여야 한다. 스텁은 «채점하는 질문이 지나가지 않는» 형제에만 — 프로브는 대상이 import 하지 않는 이름의 스텁을 «거절»하므로 스텁이 조용히 낡을 수 없다. `switchTable` 은 api.js 안에서 «진짜로» 돌고, 중복 부팅의 피해는 «그 문»에서 센다(`/schema` 읽기 하나 · `renderGrid` 하나). 재접속 상수는 config.js 에서 «import» 한다 — 정규식으로 뽑지 않는다.

## ③ 판별 실측 — 「main.js 에 이름을 더하면」

커밋 본문의 실측: main.js 에 `let c110ScratchState = 0;` 과 `export function c110ScratchProbe() {…}` 를 덧붙이고(그 뒤 바이트 그대로 복원) 하니스를 돌리니 111 · 9/9 · 3/3 — 손대지 않은 트리와 «동일». 잘라쓰기 판에서는 «같은 편집»이 C-110 의 결함이었다. main.js 는 이제 하니스가 «전혀 읽지 않는다».

## ④ 아키텍처 영향

- 그리드 페이지의 부팅 «순서»가 `startup.js` 한 파일의 «성질»이다. main.js 는 순서를 «모르고» 훅 둘을 준다.
- 하니스 세 대상(startup · api · websocket) 전부 «통째 import». 앵커 유일성 단언은 그대로, 변이는 모듈 단위.
- 하니스는 이제 `client2/node_modules` 가 «필요하다» — 진짜 api.js 가 grid.js 를 지나 ag-grid-community 를 끌어온다(페이지가 그러듯). 옛 판은 「no node_modules — vm sandbox」였다.
- 그대로인 것: 채점되는 양(리터럴 `new WebSocket('ws://…/ws')` — 사용자가 Network 탭에서 «없음»을 읽은 그 사건) · 111 단언 · 변이 9 · 대조군 3 · `checkServerHealth`/`loadTables` 본문.

## ⑤ 그때 남아 있던 것

- **비용** — 시나리오 «~500» 회, 각각 세 모듈을 프로브로 통째 로드 → ~36 s(전 0.7 s). 총괄이 「적어 둠」으로만 닫았다. 게이트 전체(127 하니스)의 소요가 이만큼 늘었다.
- `startup.js` 가 스스로 적어 둔 «열린 결»: `checkServerHealth` 가 reject 하면 `loadTables` 가 건너뛰어져 표 목록이 빈다 — 둘 다 reject 하지 않게 «쓰여» 있고, 여기서 감싸는 것은 «자기 하니스 앵커를 가진 별 변경»이라 이 이동에 얹지 않았다(옛 init 의 「M1/M9 앵커」 메모가 그대로 옮겨 감).
- 클라 레인은 «정지» 중 — 이 커밋은 클라 레인이 아니라 워크트리 에이전트가 지었고 클라의 검수 줄은 없다.

---
📎 이 항목의 수(111 · 9/9 · 3/3 · 36 s · 0.7 s · ~500)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 「잘라쓰기 하니스 절대 금지 · 덧붙이기는 다리」(CLAUDE.md 2026-09-02, 총괄 판정 같은 밤) · 이 하니스가 태어난 사고: 2026-08-04 「웹소켓이 안 붙는다 — Network 탭에 /ws 요청이 «없음»」 · 「게이트가 import 못 하는 파일은 게이트가 못 보는 파일이다」(2026-09-10).
