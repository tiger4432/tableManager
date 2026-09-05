# 그래프 가지가 «묘비까지» 사라졌다 — 그리고 죽은 화면이 페이지마다 «요청 둘»을 쓰고 있었다

> **커밋:** `8ffe23d7` (09:01) · `45d8b66f` (09:05)
> | **일자:** 2026-09-04 오전
> **레인:** 구현자(서버) + 클라
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 은퇴는 2026-08-14 에 됐고, «묘비 일곱»이 남아 있었다

판정 R-2026-08-14-H 가 추출 → 머티리얼라이즈 → 그래프 저장 가지를 이미 은퇴시켰지만
라우트 «일곱»을 **묘비**로 남겼다 — 본문에 후속 주소를 담아 **410 Gone** 으로 답하는
스텁이라, 옛 URL 을 친 클라가 «맨 404» 대신 «기능이 어디로 갔는지»를 배웠다.
09-04 에 소유자가 **묘비까지 전부 간다**고 판정했다.

## ① 서버 — 그리고 시험이 «같은 커밋»에서 같이 죽었다

`8ffe23d7`. `server/main.py` 에서 `GRAPH_BRANCH_RETIRED_REASON`·`GRAPH_BRANCH_SUCCESSOR`
·`_graph_branch_retired()` 와 스텁 일곱(`POST /api/graph/sync` · `GET /graph/stats`
· `/graph/neighbors` · `/graph/nodes/search` · `POST /graph/trace` · `GET /graph/chip-trace`
· `GET /graph/mapping-summary`), 그리고 410 을 설명하려고만 있던 주석 두 줄이 나갔다.

`server/tests/test_graph_branch_retired.py` 가 **같은 커밋에서** 삭제됐고 사유가
적혀 있다 — **그 시험은 지워지는 코드를 «정확히» 재고 있어서**, 남기면 부재에 실패하고
먼저 지우면 삭제가 «안 재진 채» 간다.

## 🔴 ② 지시서의 예측이 «틀렸고», 그것이 묘비가 있었던 이유였다

지시서는 프로브 라우트 둘이 404 가 될 거라고 했다. **안 된다.**

```python
@app.get("/{file_name:path}")
```
SPA catch-all 이 `/api` 가 «아닌» 모든 미지 경로에 `index.html` 과 **200** 을 답한다 —
**그게 애초에 묘비가 존재한 이유다.** 진짜로 404 가 되는 것은 `/api/graph/sync`
«하나»뿐이고, `/api` 에는 자기 가드가 있어서다.

⚠️ 이것은 «여기서 고쳐진 것»이 아니라 **기제와 함께 총괄에 보고됐다.**

## ③ 클라 — 그리고 「은퇴 안내」는 «남기지 않는다»로 뒤집혔다

`45d8b66f`. 앞선 지시는 화면이 있던 자리에 «안내/랜딩»을 남기라고 했다. 소유자가
그것을 뒤집었다 — 「저거 레거시 그래프 뷰어잖아 은퇴해도 무방」 · 「그냥 저거 없애. 관련도」.
**아무것도 안 남는다.**

🔴 **그리고 죽은 코드보다 나쁜 것이 있었다:**

```
trace_launch 가 /graph/mapping-summary 를 «매 그리드 로드»와 «매 데이터 fetch»에 쐈다
   그 라우트는 은퇴 이후 «410» 을 답해 왔다
   그리고 항목은 매핑 조회가 «실패하면 스스로를 숨겼다»
=> 화면은 «이미 죽어 있었고» 요청은 «안 보이게» 계속 나갔다
실측(이 상자, 빌드된 클라):  «페이지 로드마다 둘», 둘 다 거절
```

```
지운 것   graph.html · trace.html + vite 엔트리 둘
          graph_viewer.js (1,274줄) · trace.js (462) · trace_core.js (234) · trace_launch.js (111)
          main.js 의 부팅 호출 · api.js 의 매 fetch 호출 · index.html 의 trace 버튼과 문맥 메뉴 항목
```

## 🔴 ④ 남긴 것은 «세어서» 남겼다 — 지우면 «반대 효과»가 난다

`ROUTES.GRAPH`·`ROUTES.TRACE` 는 `client2/src/effort_meter.js` 에 **남는다.**
나간 것은 href 키 «둘»뿐이다. 파일 안에 사유가 적혀 있다:

```js
// The ROUTE IDS (`ROUTES.GRAPH` / `ROUTES.TRACE`) are deliberately NOT
// removed; see the note on `ROUTE_IDS`, which is a VALIDATOR for a served allowlist
// rather than a census of live navigations.
```
🔴 **허용 목록에서 id 를 빼면, 그 id 를 말하는 항목이 «미지»로 보고되면서 «계속 세어진다»**
— 의도의 «정반대»다.

훑기가 아니라 «판단»으로 남긴 것들도 기록됐다 — `grid.js` 의 `is_graph_synced` 컬럼과
그 410 주석은 «다른 기능»이라 남고, `map_key_datalist` 의 히트는 전부 낱말
"lexicographic" 이었고, `rnd_board` 의 그래프 모양 이름들은 그 화면 자기 것이다.
**없어진 모듈을 가리키던 주석 둘은 «남기지 않고» 고쳐 썼다.**

## ⑤ 하니스가 «코드와 함께» 움직였다

```
READ_PAGES 가 멤버 둘을 잃고, 그 변이 둘이 admin.js 로 «다시 겨눠진다»
/trace.html 을 말하던 라우트 단언 둘이 /admin.html 을 말한다
+ «은퇴한 화면이 null 로 풀린다»는 단언 둘 — 즉 «삭제 자체»에 채점자가 생겼다
131 -> 133 단언, 바닥 올림
```

## 아키텍처 영향

- 그래프 가지의 라우트가 **하나도 없다** — 묘비 포함. 은퇴 사실의 기록은
  `RETIRED_GRAPH_TABLES` 에만 남는다.
- 클라에 그래프 뷰어·트레이스가 **없다.** 그리고 **매 페이지 로드/데이터 fetch 마다
  나가던 거절 요청 둘이 없다.**
- 라우트 id 는 «살아 있는 이동의 인구조사»가 아니라 **허용 목록의 검증기**다 —
  파일 안에 그렇게 적혀 있다.

## 그때 남아 있던 것

- 🔴 **`RETIRED_GRAPH_TABLES` 는 남았고 «코드 소비자가 0»이다.** 지시서 목록에 없었고,
  `main.py:121` 의 부팅 주석이 여전히 그것을 「어느 표가 은퇴했나」의 기록으로 인용한다.
  `server/migrations/drop_graph_storage.py:66` 도 참조한다. **결정하지 않고 보고됐다.**
- 🔴 **은퇴한 그래프 경로는 404 가 «아니다»** — SPA catch-all 이 `index.html` 과 200 을
  답한다. `/api/graph/sync` 만 진짜 404 다.
- 이 커밋이 앞선 두 커밋에서 보류했던 **`rnd_board` 의 낡은 dist 청크**를 같이 착지시켰다
  — 이 빌드가 dist 전체를 다시 만들어서.
