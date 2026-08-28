# ✅ [A 구현자] **②③ 착지 — `02c4cc6c`. 다만 게이트의 «후» 기대가 안 맞습니다** (2026-08-29 05:2x)

`git pull` 후 트리 «깨끗» 확인하고 시작했습니다(미커밋 «0»). ①은 `4cbcb086` 으로 커밋돼
있는 것을 확인했고 **열지 않았습니다.**

## 🔴 먼저 — 게이트의 「후에는 더 멀리 닿아야」가 «안 닿습니다». 이유도 쟀습니다
지시하신 씨앗·인자 그대로:
```
GET /api/ledger/subgraph · id=wafer{SYN-BW-101-16} · hops=6 · node_limit=1000 · direction=both

전 (②③ 전)          nodes «754» · edges «1200» · hops_reached «2» · truncated [claims, edges]
후, 인자 안 보냄      nodes «754» · edges «1200» · hops_reached «2» · truncated [claims, edges]
후, continues_hops=12 nodes «754» · edges «1200» · hops_reached «2» · truncated [claims, edges]
```
**셋이 «완전히 같습니다».** 맞춰 놓지 않고 그대로 적습니다.

### 원인 — 그 씨앗에서 walk 을 막는 것은 «홉»이 아닙니다
```
truncated 가 [claims, edges] 입니다. hops «6» 을 줬는데 hops_reached 가 «2» 입니다
=> 걷기가 홉 예산을 «한 번도 다 못 쓰고» 엣지·클레임 예산에서 끝납니다
   (그 요청은 edge_limit 을 안 줘서 라우트 기본 1200 이고, claim 상한은 그 두 배인 2400 입니다)
=> 그래서 «자재 예산을 아무리 줘도» 바뀔 것이 없습니다. 축이 죽은 게 아니라 «다른 벽»입니다
```

### 그래서 «홉이 벽이 되게» 만들어 축을 확인했습니다 — 작동합니다
같은 씨앗 · node_limit=1000 · edge_limit=3000 · both:
```
hops=1 continues_hops=0   nodes «40»  · hops_reached «1» · truncated [depth]
hops=1 continues_hops=4   nodes «157» · hops_reached «3» · truncated «없음»
hops=2 continues_hops=0   nodes «118» · hops_reached «2» · truncated [depth]
hops=2 continues_hops=4   nodes «157» · hops_reached «3» · truncated «없음»
```
`hops=1` 한 홉만 주고도 깊이 «3» 까지 닿고 depth 절단이 «꺼집니다» — 자재 걸음이 떠남 예산을
안 쓰기 때문입니다. **축은 삽니다. 지시하신 인자에서만 다른 벽에 가려집니다.**

👉 판정 필요: 게이트 씨앗을 「홉이 벽이 되는 인자」로 바꾸시겠습니까, 아니면 이 결과를
   그대로 받으시겠습니까. 제가 게이트를 고쳐 쓰지 않았습니다.

## 게이트 ③ — 새 인자가 산다
```
안 보냄            위 「후, 인자 안 보냄」과 동일 = 전과 동일  ✅
continues_hops=0   동일 (오늘의 걷기)                          ✅
continues_hops=-1  «422»  (ge=0 으로 이름 대어 거절)           ✅
선언에서 읽은 집합  bonded_from · derived_from · has_wafer · inspected · slot_map · transfer  «여섯»
                   -> `_continuing_predicates()` 를 직접 불러 확인했습니다. 코드에 박힌 이름 «0»
```

## 게이트 ④ — 이 파일들을 지나는 하니스
```
tests/test_ledger_subgraph.py + tests/test_ledger_explorer.py   -> «12 passed · 1 skipped»
전체 스위트는 «안 돌렸습니다» (지시대로)
```

## 무엇을 어떻게 고쳤나
```
② ledger_trace_router.py
   _continuing_predicates()   `_followable_predicates` 와 «같은 모양». 선언에서만 읽고,
                              읽기 실패는 «빈 집합»(= 모든 걸음이 떠남 = 오늘의 걷기)
   continues_hops             Query(DEFAULT_CONTINUES_HOPS, ge=0, le=40)
③ ledger_api/ledger_subgraph.py
   DEFAULT_CONTINUES_HOPS = 0  🔴 0 인 이유: 선언에 이미 여섯이 붙어 있어서, 다른 기본값이면
                               «축을 넣는 그 커밋»이 모든 화면의 답을 바꿉니다
   dep_cost{}                  «떠난» 횟수. depths 는 «뜻 그대로» — 그래서 truncation·
                               hops_reached·자취·클라가 전부 그대로 삽니다
   _spend(near, far, charge)   먼 쪽에 charge 를 싣고 «최솟값»을 유지 (add_node 가 깊이를
                               최솟값으로 두는 것과 같은 이유)
   frontier                    depths==depth «그리고» dep_cost < hops 인 것만 편다
   루프 상한                    range(hops + continues_hops), 절단 판정 둘(:879·:884)도 같은 상한
```
⛔ 술어 이름 코드에 박기 «0» · 라이브 선언 열기 «0» · 클라 변경 «0» · 자재 걸음을 0홉으로 «안 셈»
   (자재 걸음도 depths 는 올립니다 — split·transfer 반복이 무한이 되지 않습니다)

## ⚠️ 측정 조건 — 어제 사고 난 자리라 명시합니다
```
제 수치는 «TestClient(app)» 로 잰 것이라 «지금 트리 = 지금 커밋»의 코드입니다
   (커밋 직전 git status 로 두 파일이 «스테이지됨(M )»인 것을 눈으로 확인하고 커밋했습니다)
총괄이 «돌고 있는 서버»에 대고 재시려면 04:4x 재기동 이후 ②③이 들어갔으므로 «다시 재기동»이
필요합니다 — 안 하면 제 전/후가 아니라 «전/전»을 보시게 됩니다
```
