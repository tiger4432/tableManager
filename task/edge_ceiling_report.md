# ✅ [A 구현자] **천장을 모듈에서 읽습니다 — `743117ef`. 그리고 6000은 «더 큰 절단»이 아닙니다** (2026-08-29 11:0x)

한 줄입니다. 기본값 1200은 그대로 두고 «천장»만 옮겼습니다.
```
ledger_trace_router.py:92
   전   edge_limit: int = Query(1200, ge=20, le=3000, …)
   후   edge_limit: int = Query(1200, ge=20, le=ledger_subgraph.MAX_EDGE_LIMIT, …)
```
숫자를 다시 안 적고 «모듈에서 읽습니다» — 그래서 다음에 또 어긋날 자리가 없습니다.

## 게이트 — 셋 다 통과
```
① edge_limit=6000 이 422 가 아니어야 한다
   전  422  "Input should be less than or equal to 3000"
   후  «200»                                                          ✅
   그리고 6001 은 «여전히 422», 이번엔 이름이 «6000» 입니다             ✅
③ 안 보내면 오늘과 같은 답 (기본 1200)
   nodes 754 · edges 1200 · hops_reached 2 · truncated [claims, edges] ✅ 전과 동일
```
## 게이트 ② — 씨앗 `wafer SYN-BW-101-16` · hops=6 · node_limit=1000 · direction=both
`hops_reached` 는 지시하신 대로 «`walk` 블록»에서 읽었습니다(`limits` 아님).
```
edge_limit   nodes   edges   walk.hops_reached   truncated
3000         1000    3000    2                   claims, edges, nodes
6000         1000    «3324»  2                   claims, nodes          ← 엣지 플래그 «꺼짐»
```

## 🔴 그래서 이 라운드의 값은 「상한이 올라갔다」가 아닙니다
```
6000 을 줬는데 엣지가 «3324» 에서 «스스로» 멈춥니다 — 6000 을 안 씁니다
즉 모듈 주석의 「6000 이 엣지가 안 걸리는 지점」이 «맞았습니다». 정착점입니다
남은 벽은 nodes 와 claims 입니다 (nodes 는 1000 = node_limit 상한에 붙어 있습니다)
```
어젯밤 「상한을 올려도 벽이 옆으로 옮길 뿐」이라 하신 문장은 **틀리지 않았고, 이제 닿을 수 있는
끝에서 잰 값이 붙었습니다** — 엣지 벽은 «사라지고» 남은 것이 노드·클레임입니다.

## 하니스
```
tests/test_ledger_subgraph.py   11 passed · 1 skipped
```

## ⚠️ 측정 조건
```
TestClient(app) 로 잰 것이라 «지금 커밋»의 코드입니다
   (커밋 전 git status 로 스테이지 표시 M 을 눈으로 확인했습니다)
돌고 있는 서버에 대고 재시려면 «재기동» 후에 재십시오 — 안 하면 여전히 3000 에서 422 입니다
```
