# 그리드의 «다시 돌리기» 목록은 «이 표»의 것이고 줄이 «어디서 어디로»를 말한다 — 그리고 긷는 함수는 `main.js` 를 나왔다, 잘라쓰기 없이 재려면 그 길뿐이라서

> **커밋:** `c87080e3` — feat(replay): the grid's replay list is THIS table's rules, and a line says where each one runs (C-109, 클라 절반 · 서버 절반은 S-250)
> **일자:** 2026-09-15 17:07 (design 워크트리) → main 병합 `8527e886`
> **레인:** 클라(design) — 지시 `d65a32b2` → 착지 → 보고 `dc922110` → 이음매 덧붙임 `f6206246` → 총괄 받음 `43d79df9`(C-110 큐) · 닫힘 `c21bacbf`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** `replay_rules_harness.mjs` **28/0 신설 · import 기반** (변이 9/9 «이름 댄 단언»으로 잡힘 · 대조군 2/2 탈출) · `redo_banner_harness` 51/0 · `startup_socket_gate` 111/0 · 계약 12/12 · 빌드 · `client2/dist` 같은 커밋 (클라 보고). 총괄 확인 「하니스 28 + 51 초록 · dist 번들에 라우트 낱말 · 실제 페이지(8080) dt_log 행 선택 → Replay chain → 팝업이 「토큰 없음」과 「1 key from 1 row」를 가름」.

## ① 왜 — 목록이 «표를 몰랐다», 그리고 아무것도 «오류를 내지 않았다»

`main.js::loadChainRuleNames()` 가 `GET /admin/chain/rules` 를 «부팅에 한 번» 읽어 «이름 문자열»로 접었다.
```
ⓐ 어느 표의 규칙인지 화면이 몰랐다        표와 무관하게 «전부»
ⓑ 같은 이름의 조인과 합성이 같아 보였다     이름 문자열이라
ⓒ 표를 바꿔도 목록이 안 바뀌었다           부팅에 한 번만 읽어서
```

## ② 변경 — 긷는 자리 하나(자기 파일) · 배선 한 줄 · 줄의 모양

```javascript
// client2/src/replayable_rules.js  — «서버가 준 객체를 그대로». 거르는 것은 서버(S-250)다. 화면이 거르면 그 규칙이 «두 곳»에 산다
export async function loadReplayableRules(table) {
  if (!table) return null;                    // 「표를 아직 안 골랐다」는 「없다」가 아니라 「모른다」
  const token = readAdminToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE}/admin/chain/rules/replayable?table=${encodeURIComponent(table)}`,
      { headers: { [ADMIN_TOKEN_HEADER]: token } });
    if (!res.ok) return null;                 // null(못 읽음) · [](이 표를 트리거로 하는 규칙 없음) · 배열 — «세 상태»
    const body = await res.json();
    if (!body || body.status !== 'success' || !Array.isArray(body.data)) return null;
    return body.data;
  } catch (e) { return null; }
}
```
```javascript
// client2/src/main.js — 부팅과 표 바꿈이 «같은 줄»을 지난다. 갈라지면 한쪽 경로에서만 목록이 낡는다(깔끔 ④)
function redoBannerFollows(table) {
  if (!redoBanner) return;
  redoBanner.setRelation(table);
  redoBanner.setBusinessKey(state.currentBusinessKey);
  loadReplayableRules(table).then((rules) => redoBanner.setRules(rules));
}
```
```javascript
// client2/src/redo_banner.js — 줄: `이름 · 트리거 → 대상 — N keys from M rows` + 종류는 «자기 칸»(join · decide · mapper)
const path = (rule && rule.trigger_table && rule.target_table) ? ` · ${rule.trigger_table} → ${rule.target_table}` : '';
return { text: `${name}${path} — ${from}`, kind: (rule && rule.kind) || '',
         params: name ? { rule: name, business_keys: keys } : null };   // 이름 없는 규칙은 «누르는 줄»이 아니다 — rule 은 필수
```
서버가 안 말한 것은 «안 그린다»: 종류 없으면 배지 없음 · 표 없으면 화살표 없음 · 이름 없으면 못 누름. 크기(`from`)는 줄에 «남는다» — 확인 창이 없고 «그 줄을 누르는 것»이 확인이다.

## ③ 지시에서 «두 자리» 벗어났고, 둘 다 «재서» 벗어났다 — 총괄 「옳다」

```
㉠ 함수의 집    지시: main.js 의 loadChainRuleNames → loadReplayableRules
              실측: main.js 는 node 가 import 못 한다(최상단 ag-grid + CSS 둘, 마지막 줄 init()). 거기 두면 재는 길이 «잘라쓰기»뿐 = 금지
              -> 자기 모듈로. source_rows.js(C-14) · write_guard.js(C-107) 가 «같은 사유»로 나온 자리 — 이 파일이 셋째
㉡ 가른이      지시: `${name}  ${trigger} → ${target}`(공백 둘)
              실측(실제 브라우저): HTML 이 공백 둘을 «하나로 접어» 「lot_slot_wafer dt_lot」이 한 낱말처럼 읽혔다
              -> 기호 `·`
```

## ④ 하니스 둘이 «자기가 읽는 코드의 진실»을 말했다 — 조용히 초록이 아니라

```
redo_banner_harness §I     규칙이 «객체»가 됐고 빈 목록 문구가 «좁아졌다»(「서버에 규칙 없음」은 오늘 거짓 — 다른 표엔 있을 수 있다)
                          -> 단언을 «지우지 않고 바꿨다». 지우면 새 규칙을 재는 것이 아무것도 안 남는다
startup_socket_gate       init() 을 «잘라» vm 에 넣으므로 제가 더한 «이름 하나»(redoBannerFollows)에 26개 시나리오가 전부 ReferenceError
                          = 금지문이 예고한 «바로 그 모양»(「import 를 하나 더하면 … 던집니다」)
                          -> 스텁 한 줄 + SITE_SOCKET_LAST 앵커를 오늘의 꼬리로. 그 자리는 «자기 주석에» 「또 움직이면 INERT 로 소리 내겠다」고 적어 뒀고 실제로 그렇게 됐다(두 번째)
```
🔴 총괄이 이것을 **C-110(등급 4)** 으로 큐에 넣었다: `startup_socket_gate` 는 잘라쓰기 하니스다 — 「재려는 로직을 import 되는 모듈로」 또는 «덧붙이기 다리»로 옮길 것. 지금은 짓지 않는다.

## ⑤ 이음매 실측 — 「S-250 이 제 트리에 없다」는 «그 측정 시점의 사실»이었다

보고 시점 클라 워크트리에 `git grep replayable -- server` = **0**(S-250 미병합) → 라이브 라우트로는 «한 번도» 안 걸었다. 30분 뒤 `f6206246`: S-250 이 main 에 착지해 서버 모양을 «읽어» 대조 — 칸 넷(`name · trigger_table · target_table · kind`) «같음», `DECLARED_KINDS` 셋 «같음». 코드 변경 0.
```
접은 자리 «하나»를 이름 대어 둠   서버는 모르는 표를 404 로 «이름 대어» 거절하는데, 화면은 res.ok 아니면 전부 null(「chain rules not loaded」)
                             왜: 그리드가 보내는 표는 «언제나 카탈로그에서»(state.currentTable) — 이 페이지에서 그 404 는 도달 불가. 둘째 문장은 「아무도 안 타는 갈래」
```

## ⑥ 아키텍처 영향

- 목록의 «주어»가 표다. 표가 늘어도 화면은 «한 글자도» 안 바뀐다(거르는 것은 서버).
- 배너에 «표를 알리는 자리»가 하나(`redoBannerFollows`)다 — 부팅과 표 바꿈이 갈라질 수 없다.
- 클라의 «import 가능한 부품»이 하나 늘었고, `main.js` 에서 «꺼내야 재진다»는 사례가 셋이 됐다.

## ⑦ 그때 남아 있던 것

- **「표를 바꾸면 다시 부른다」의 배선은 하니스가 «못 잰다»**(main.js 는 import 불가). 실제 페이지에서 걷는 것으로 대신했고, 보고서가 그렇게 «적었다».
- 총괄은 실제 페이지(8080)에 «토큰을 넣지 못해» 목록 자체는 하니스 + in-process 로 확인했다. 브라우저에서 목록이 «표를 따라 바뀌는 것»을 본 기록은 이 시점에 없다.
- 이 커밋의 배너는 여전히 **화면 컬럼 값을 `business_keys` 로** 보냈다. 같은 날 밤(22:3x) 그것이 composite 표(dt_log)의 저장 업무키(`GEN-dt_cell_key-…`)와 «다른 세계»라 `rows_scanned 0` 이 됐고, S-254/C-112(row_id 로)가 열렸다 — 이 커밋 시점엔 «아무도 몰랐다».
- 제안 표 «넷»(배너 문구 한국어 통일 · 이름 거르기 · 마지막 돌린 규칙 위로 · 돌린 뒤 무엇이 돌았나 남기기) — 짓지 «않았고» 판정 대기.
- C-110(잘라쓰기 하니스 이전)은 큐에만 있고 클라는 «정지».

---
📎 수는 클라 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 서버 절반: `20260915_165535_the_replay_list_is_the_set_that_actually_runs_filtered_by_trigger.md` · `main.js` 에서 꺼낸 앞선 둘: C-14 `source_rows.js` · C-107 `write_guard.js` · `startup_socket_gate` 가 앵커에 INERT 로 소리 낸 첫 번: 그 하니스 자기 주석(SITE_SOCKET_LAST). 잘라쓰기 금지의 정본: `docs/guide/HARNESS_DISCIPLINE_GUIDE.md`.
