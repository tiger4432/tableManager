# M2-v2 차단 결함 C1 수정 — B2 회복 재시도 경로

> **작업:** client-pm / 2026-07-26 · 대상 `client2/src/transfer_plan.js` (+ `npm run build`)
> **범위:** QA 재검수 §2 C1 **단 1건**. C2~C8은 손대지 않음.
> **DB 쓰기 0건** — 모든 `PUT …/data/updates`·`POST …/rows/batch_delete`를 브라우저 `fetch` 셰임으로 가로챘고, 검수 전후 `map_doe` 6행·`map_doe_source` 8행의 `updated_at` 불변을 SQL로 확인(§4). 커밋하지 않음.

---

## 1. 판정 요약

C1의 뿌리는 **"서버에 요청이 성공했다"가 "화면이 서버본이다"로 승격되던 것**이다. 조회 함수가 전역
권한(`S.serverKeys` / `S.doeServerLoaded`)을 스스로 세웠기 때문에, 회복 재시도가 성공하면 `S.doe`는
여전히 실패 당시의 초안인데 권한만 켜졌다. 그 상태에서 `keep`(화면)과 `serverKeys`(서버)의 차집합이
곧 삭제 대상이 됐다.

**구조로 강제했다.** 조회 함수는 키 집합을 **반환만** 하고, 권한은 `adoptServerDoe()` **한 지점**에서만
생긴다 — 그 함수가 `S.doe`에 서버본을 넣는 바로 그 지점이다. 불변식 `doeServerLoaded === true ⇒
S.doe는 서버본에서 유래` 가 호출부 규율이 아니라 **코드 구조**로 성립한다.

순 변경 **+29 / −13 줄** (주석 포함), 리팩터링 확대 없음.

---

## 2. 수정 diff 요약 (`client2/src/transfer_plan.js`)

### ① 조회 함수에서 전역 대입 제거 — 키를 **반환**한다 (`:1164-1180`)

```js
-    // ★ 여기까지 왔을 때만 "서버 상태를 안다"고 선언한다 (prune의 유일한 근거)
-    S.serverKeys.doe = doeKeys;
-    S.serverKeys.source = srcKeys;
-    S.doeServerLoaded = true;
-    if (rows.length === 0) return { ok: true, rowCount: 0 };
+    // ★ [C1] 이 함수는 **조회만 한다.** …권한은 채택 지점(adoptServerDoe)에서 화면 반영과 원자적으로 얻는다.
+    const keys = { doe: doeKeys, source: srcKeys };
+    if (rows.length === 0) return { ok: true, rowCount: 0, keys };
     …
-    return { ok: true, rowCount: rows.length, doe: loaded };
+    return { ok: true, rowCount: rows.length, doe: loaded, keys };
```

### ② 채택 = 권한 획득 (신설, `:1183-1194`)

```js
// [C1] 서버본 **채택** — prune 권한(serverKeys/doeServerLoaded)이 생기는 유일한 지점이다.
// 불변식: `doeServerLoaded === true` ⇒ `S.doe`는 서버본에서 유래했다.
// 서버 0건이면 serverKeys도 비므로 prune 후보가 존재하지 않는다(초안 유지가 안전).
function adoptServerDoe(r) {
  S.serverKeys = { doe: (r && r.keys && r.keys.doe) || new Set(),
                   source: (r && r.keys && r.keys.source) || new Set() };
  if (r && r.doe instanceof Map && r.doe.size > 0) S.doe = r.doe;
  S.doeServerLoaded = true;
}
```

### ③ 회복 재시도 성공 → 채택 후 **쓰기 없이 종료** (`:927-953`)

```js
   if (!S.doeServerLoaded) {
+    const seq = S.loadSeq;
     const retry = await loadDoeFromServer();
+    if (seq !== S.loadSeq) return;   // 재시도 중 맵이 바뀌었다 — 이전 맵의 응답을 채택하지 않는다
     if (!retry.ok) { …저장 보류 (기존 유지)… return; }
-    // 회복 성공: 이제 serverKeys를 알므로 안전하게 쓸 수 있다.
-    // ⚠️ 서버본을 화면에 덮어쓰지는 않는다 — 사용자가 그 사이 편집한 내용이 정본이다.
-    S.saveError = null;
+    if (retry.unsupported) { S.saveError = null; renderPlanHead(); return; }
+    adoptServerDoe(retry);
+    S.saveError = null;
+    renderAll();
+    showToast('서버 계획을 불러왔습니다. 조회 실패 중 편집한 내용은 서버에 반영되지 않았고 '
+            + '브라우저 초안에 남아 있습니다.', 'warning', { dedupeKey: 'doe_server_recovered' });
+    return;
   }
```

새 모달·패널·확인 다이얼로그 **없음**(자동 저장 경로에 확인창 금지 규율 준수). 로컬 초안은 **건드리지 않는다** — 토스트가 주장하는 "초안에 남아 있습니다"가 실제로 참임을 §3-B에서 localStorage 덤프로 확인했다.

### ④ 정상 로드 경로도 같은 관문을 지난다 (`:1253-1266`)

```js
-          } else if (r.doe && r.doe.size > 0) {
-            const draftHadContent = …;  S.doe = r.doe;
-            if (draftHadContent) showToast('…서버본을 표시합니다.') else showToast('…복원했습니다.');
+          } else {
+            const draftHadContent = …;                       // 채택 **전에** 계산
+            const hadServerRows = r.doe instanceof Map && r.doe.size > 0;
+            adoptServerDoe(r);                               // seq 가드(:1226) 통과 후에만 도달
+            if (hadServerRows) showToast(draftHadContent ? '…' : '…', 'info');
           }
```

`pruneScoped` 헤더 주석도 새 근거(채택 지점)와 **`keep`/`knownKeys`는 같은 출처여야 한다**는 불변식으로 갱신(`:1047-1053`). `pruneScoped` 본문·가드 3종, 절단 응답 강등(`:1108-1111`, `:1139-1141`), 로드 실패 시 쓰기·삭제 전면 보류는 **무변경**.

---

## 3. 라이브 증명 (실제 브라우저 · 실제 서버 127.0.0.1:8080 · dist 번들)

**전제 확인:** 서버가 서빙 중인 번들이 수정본임을 먼저 확인 — 페이지 `<script src>` = `/assets/map_editor-CqnObVR-.js`이고 그 파일에 신규 문자열 `doe_server_recovered`가 존재. dist 6개 HTML의 asset 참조 **끊긴 링크 0건**.

**셰임 규약:** `/tables/**` 로 가는 **비-GET 요청은 전부 가로채 기록만 하고 합성 200을 돌려준다**(실 DB 무접촉). GET에는 시나리오별 주입(1회성 500 / `total>rows` 절단 위장 / 지연)만 건다.

### A. 1회 500 후 회복 — 나가는 쓰기 0건

| 단계 | 관측 |
|---|---|
| 주입 | `map_doe` GET **1회만** 500 (`injectDoeGetFail=1`) |
| 맵 오픈 `bonding_map/AAA` | `GET /tables/map_doe/data [INJECTED-500]` → 헤더 `⚠ 서버 상태 미확인`, 토스트 `⚠️ 서버 DOE 조회 실패 …(HTTP 500)`, DOE 목록 = `F/1/2 모두 "구간 없음"` (= 결함 발현 전제 성립) |
| 편집 1회 | `F`의 `[+ 구간]` 클릭 |

**편집 후 실제로 나간 요청 전량:**
```
GET  /tables/map_doe/data?limit=500&filters=…      [pass 200]     ← 회복 재시도
GET  /tables/map_doe_source/data?limit=500&…       [pass 200]
── 이상 끝. PUT /data/updates 0건 · POST /rows/batch_delete 0건 (셰임 차단 카운트 0) ──
```
- 화면 복원: `F → 구간 3개 [1 / 2-15 / 16] · 자재 5매 · 43 / 200`, `1 → 구간 3개 · 자재 3매` (= 서버본 `F|1` 100 / `F|2` 90 / `F|3` 10, source 5행)
- 토스트 **1건**: `⚠️ 서버 계획을 불러왔습니다. 조회 실패 중 편집한 내용은 서버에 반영되지 않았고 브라우저 초안에 남아 있습니다.`
- localStorage 초안 = 편집분 그대로 보존 (`F:[{seq:1, stack:"", need:"", materials:[]}]`)

> 종전 코드에서는 같은 조작이 `PUT map_doe/data/updates → F|1 stack_band="" qty_total=0` + `POST map_doe/rows/batch_delete` + `POST map_doe_source/rows/batch_delete` 전량이었다(QA 재현 ①).

**A-후속(권한이 정상적으로 켜졌는지):** 회복 직후 같은 화면에서 `총 소요 100 → 111` 수정 →
```
PUT /tables/map_doe/data/updates         {"updates":[ F|1 stack_band:"1" qty_total:111,
                                                       F|2 "2-15" 90, F|3 "16" 10 …]}
PUT /tables/map_doe_source/data/updates  {"updates":[ F|1|TAPE-A|01 qty:37, F|1|TAPE-C|03 qty:37, … ]}
POST …/rows/batch_delete  0건
```
서버본의 `stack_band`·자재가 **살아 있는 채로** 업서트된다(파괴 없음). 배분은 `ceil(111/3)=37` — M6 규약 유지.

### B. 절단 응답 위장 + 3주 묵은 로컬 초안 — 초안이 서버를 덮지 않는다

시드: `transfer_plan_draft::bonding_map::AAA` = `{F:[{stack:"STALE-DRAFT", need:8, materials:[OLD-LOT|99]}], saved_at:"2026-07-05T09:00:00Z"}`

| 단계 | 관측 |
|---|---|
| 맵 오픈 | `GET /tables/map_doe/data [INJECTED-TRUNCATED total=13 rows=6]` → 헤더 `⚠ 서버 상태 미확인`, 토스트 `…(응답 절단 (13 > 6))`, 화면 = **낡은 초안**(`STACK STALE-DRAFT · OLD-LOT|99 · 43 / 8`) |
| 편집 1회 | `총 소요 8 → 77` |

**편집 후 실제로 나간 요청 전량:**
```
GET  /tables/map_doe/data?…          [pass 200]
GET  /tables/map_doe_source/data?…   [pass 200]
── PUT 0건 · POST batch_delete 0건 ──
```
- 화면 = 서버본(`구간 3개 [1 / 2-15 / 16] · 자재 5매 · 200`)
- 토스트 1건(A와 동일 문구)
- 초안은 **보존**: `{stack:"STALE-DRAFT", need:77, materials:[{lot:"OLD-LOT",slot:"99"}]}` — 조용히 버리지 않았고, 서버로도 새지 않았다.

### C. 정상 경로 회귀 — 업서트·prune 정상

**C-1 로드:** 주입 없이 `bonding_map/AAA` 오픈 → 헤더 `서버 2026-07-26 20:18:10`, 화면 = 서버본, 토스트 `ℹ️ 서버에서 DOE 정의를 복원했습니다.`
**C-2 초안 병존 분기:** 내용 있는 초안(`DRAFT-ONLY`) 시드 후 오픈 → 토스트 `ℹ️ 서버에 저장된 DOE 정의를 불러왔습니다 — 브라우저 초안 대신 서버본을 표시합니다.` (두 분기 모두 실행 확인)
**C-3 삭제 반영:** 로드 성공 상태에서 `F`의 3번째 구간(`16` / 10 / TOP) 🗑 →
```
PUT  /tables/map_doe/data/updates          {"updates":[ F|1 …, F|2 …, (1|1..1|3) ]}   ← 남은 것만
PUT  /tables/map_doe_source/data/updates   qty 34 (=ceil(100/3))
GET  /tables/map_doe/data?…                                    ← prune 조회
POST /tables/map_doe/rows/batch_delete     {"row_ids":["019f9e24-b80c-7476-9fd8-3b517f67054d"]}
GET  /tables/map_doe_source/data?…
POST /tables/map_doe_source/rows/batch_delete {"row_ids":["019f9e24-de17-7ca2-a22b-3d94cf807992"]}
```
DB에서 그 두 `row_id`를 역조회한 결과 **정확히 삭제 대상 1쌍**이다:
```
map_doe        019f9e24-b80c-… -> bonding_map|AAA|F|3
map_doe_source 019f9e24-de17-… -> bonding_map|AAA|F|3|TOP|
```
→ 지워야 할 행은 지워지고, 나머지 5+7행은 후보에도 오르지 않았다. (요청 자체는 셰임이 가로채 DB 미반영)

### D. 맵 전환 — 권한 이월 없음

**D-1 (전환 후):** A 시나리오로 `AAA` 회복(권한 ON) → `bonding_map/88833143-…`로 전환. 새 맵의 `map_doe` GET을 **지속 실패**(500)로 두고 편집 1회 →
```
GET /tables/map_doe/data  [INJECTED-500]     ← 재시도 1회
── 이상 끝. 쓰기 0건 ──
헤더: ⚠ 서버 저장 실패 · 초안만
```
전 맵의 `serverKeys`/`doeServerLoaded`가 이월됐다면 여기서 업서트가 나갔어야 한다. 나가지 않았다.

**D-2 (전환 중 = 새로 넣은 `seq` 가드 실행):** `AAA` 로드 실패 → 편집 → 회복 재시도 GET을 **45초 지연**시킨 상태에서 다른 맵으로 전환.
```
11:36:17.177 GET /tables/map_doe/data           [DELAYED 45000ms]   ← AAA 재시도 시작
11:36:26.224 GET /tables/bonding_map/data       [pass 200]          ← 맵 전환(88833143-…)
11:36:27.272 GET /tables/map_doe/data           [pass 200]          ← 새 맵 자체 로드(정상)
11:36:27.287 GET /tables/map_doe_source/data    [pass 200]
11:37:03.182 GET /tables/map_doe/data           [DELAYED-RESOLVED]  ← 늦게 도착한 AAA 응답
11:37:03.183 GET /tables/map_doe_source/data    [pass 200]
── 쓰기 0건 ──
```
늦게 도착한 AAA 응답 이후에도 화면은 새 맵의 상태 그대로(`F · 구간 없음 · 323 / —`), 회복 토스트 **미발생** = `if (seq !== S.loadSeq) return;` 분기가 **실제로 실행**됐다. AAA의 키 집합이 새 맵의 권한으로 승격되지 않았다.

> **지난 라운드 실수 반복 여부:** 이번 A·B·D-2는 전부 **회복이 성공하는 분기**를 통과한다(주입 횟수 1 < 재시도 횟수 포함 2회 GET). D-1만 지속 실패 분기다. 실패·회복·전환 중 세 갈래를 각각 실행했다.

---

## 4. DB 무접촉 증거 (검수 전후 SQL)

`postgresql://…/assy_manager` 직접 조회(앱 밖 독립 오라클). 검수 **전**과 **후**가 완전히 동일:

| 테이블 | 행 수 | `updated_at` (전 → 후) |
|---|---|---|
| `map_doe` | 6 → 6 | `2026-07-26 20:18:10.169287+09` → **동일** (6행 전부) |
| `map_doe_source` | 8 → 8 | `2026-07-26 20:18:10.233107+09` → **동일** (8행 전부) |

값도 불변: `bonding_map|AAA|F|1` = `stack_band '1' / qty_total 100`, `F|2` = `'2-15' / 90`, `F|3` = `'16' / 10`, source 8행(`F|1` TAPE-A/C/D 각 34, `F|2` TAPE-B 90, `F|3` TOP 10, `1|1..3` 3행).
셰임이 가로챈 쓰기 시도 중 **DB에 도달한 것은 0건**이며, 맵 로드 시 부수적으로 발생하는 `PUT map_split_registry/data/updates`도 함께 차단했다.
**라이브 정리 목록: 없음.** 시드했던 `transfer_plan_draft::bonding_map::AAA`는 제거 완료(잔여 0), `window.fetch` 원복 완료.

---

## 5. 문서 정합 — 거짓이었던 서술 정정

`agent_workspace/reports/Client_transfer_plan_v2_impl_report.md`를 다음과 같이 고쳤다(삭제 없이 정정 블록 삽입):

| 위치 | 조치 |
|---|---|
| §6-c-1 제목 | `— 해소` → `— ⚠️ 부분 해소 (본 절의 "해소" 주장은 철회됨)` + 정정 블록: 회복 분기 미수정이었음, "`keep`이 비어도 대상 0"의 전제가 재시도 성공 시 성립하지 않음, 실제 해소 위치(`M2_v2_C1_fix.md`) 명시 |
| §6-c-1 ⓓ | `라이브 재현·해소 증명` → `라이브 재현 — ⚠️ 커버리지 부족 (증명으로 인정되지 않음)`. "차단된 GET 2회 = 지속 실패만 시험" 자인 |
| §6-c-6 | 40×40(`minC=0`) 케이스 선정이 **형식만 적용**이었음을 명기 + 규율("회귀 강도는 조합 수가 아니라 결함 축을 활성화하는 픽스처에서 나온다") + 재검증 픽스처 지정(29x25 / 27x21). C7 백로그와 함께 처리 |

**미갱신(총괄 일괄 대상):** `docs/architecture/CODE_MAP.md`에 신규 `adoptServerDoe`(`transfer_plan.js:1189`) 추가 필요 — QA가 지적한 `pruneScoped(4인자)`·`importOverlayToGrid`·`updatePaintLockIndicator`·`sweepToasts(keep)` 누락과 같은 큐. `PROJECT_STATUS.md`·히스토리 인덱스는 규율대로 손대지 않았다.

**히스토리 초안 (총괄 기입용):**
```
- 🔴 [QA C1] B2 회복 재시도 경로 미해소 — 조회 성공을 "화면이 서버본"으로 승격하던 구조를 분리.
  loadDoeFromServer는 키 집합 반환만, 권한(serverKeys/doeServerLoaded)은 adoptServerDoe 단일 지점에서
  화면 반영과 원자적으로 획득. 회복 성공 시 서버본 채택 후 그 저장 사이클은 쓰기 0건으로 종료(초안 보존 + 고지 1건).
  재시도 중 맵 전환 seq 가드 추가. 라이브 검증: 1회 500 회복 / 절단+낡은 초안 / 정상 prune / 맵 전환(전환 중 포함).
```

---

## 6. 빌드·범위

- `cd client2 && npm run build` 완료 → `dist/assets/map_editor-CqnObVR-.js` 갱신, HTML 참조 33건 **전부 해소(끊김 0)**.
- 변경 파일: `client2/src/transfer_plan.js` **1개** + dist 산출물 + 정정한 기존 보고서 1건. `server/**` 무접촉. **커밋 없음.**
- C2~C8·M3·M4·M7·L1 미착수(지시대로). 다만 **C2(맵 전환 레이스)는 이번 수정의 부수 효과로 실질 해소**됐다 — 전역 대입이 `loadDoeFromServer` 밖으로 나와 호출부의 `seq` 가드 **뒤**로 이동했고(`:1226` 이후), 저장 경로에도 동일 가드를 넣었다(§3-D2 실증). 총괄이 C2를 백로그에서 내릴지 판단 요망.

---

## 7. 교훈 제안 (`agent_workspace/memory/client-pm.md` — 총괄 검수 후 반영)

- **함정**: 조회 함수가 **반환값과 전역 권한을 동시에** 세우면, 호출부가 그 반환값을 버려도 권한만 남는다. "요청이 성공했다"가 "화면이 그 데이터다"로 조용히 승격된다.
  **올바른 방법**: 조회는 **반환만**. 상태를 실제로 채택하는 지점에서 권한을 **원자적으로** 함께 세운다. 불변식은 주석이 아니라 **호출 가능한 지점의 수**로 강제한다(채택 함수 1개).
- **함정**: 삭제 대상을 `A − B` 차집합으로 구하는 코드는 두 피연산자의 **출처·시점이 다르면** 조용히 "전량 삭제"가 된다.
  **올바른 방법**: 차집합 삭제를 보면 즉시 "이 둘은 같은 스냅샷에서 왔는가"를 묻는다. 아니면 그 자체가 결함이다.
- **함정**: 재시도·폴백을 추가하고 **실패 분기만** 시험하면 "해소"처럼 보인다. 정작 재시도를 넣은 이유인 **회복 성공 분기**가 미검증으로 남는다.
  **올바른 방법**: 주입 횟수 N을 보고할 때 **N이 총 시도 횟수 이상이면 회복 분기는 시험되지 않은 것**이다. 실패(지속) / 회복(1회 실패 후 성공) / 전환 중(레이스) 세 갈래를 각각 실행한 뒤에만 "해소"라고 쓴다.
- **함정**(검증 도구): 브라우저 탭이 화면에 렌더되지 않으면 `computer` 클릭이 무반응이고 `setInterval` 폴러도 심하게 스로틀된다(실측: 120ms 간격이 7.5초 동안 20회만 발화 → 토스트를 놓쳐 "미발생"으로 오판할 뻔했다).
  **올바른 방법**: 조작은 `dispatchEvent`(입력은 `change`까지)로, 관측은 **폴링이 아니라 요청 로그·DOM 스냅샷**으로. 토스트처럼 수명이 짧은 신호는 셰임/`MutationObserver`로 **누적 기록**한 뒤 읽는다.
