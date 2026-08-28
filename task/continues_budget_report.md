# 🛑 [A 구현자] **멈춥니다 — 지시 ①이 «이미 트리에 있습니다». 커밋은 안 됐고, 제 것이 아닙니다** (2026-08-29 04:5x)

`continues` 라운드를 받아 착수 전 측정부터 했고, 첫 파일을 열자마자 벽이 나왔습니다.
**지시 ①(검증기)이 «작업 트리에 이미 구현돼» 있습니다.** 제가 쓴 것이 아닙니다.

## 실측
```
git status --porcelain -- server
   M server/ledger/setup_bundle.py         ← 커밋 안 됨
   M server/ledger/ledger_skeleton.json    ← 커밋 안 됨

git show HEAD:server/ledger/setup_bundle.py | grep -c 'optional=("continues",)'   ->  «0»
grep -c 'optional=("continues",)' server/ledger/setup_bundle.py                   ->  «1»
git log -S'optional=("continues",)' -- server/ledger/setup_bundle.py              ->  커밋 «없음»

mtime   setup_bundle.py       08-29 «04:38»
        ledger_skeleton.json  08-29 «04:38»
        ledger_trace_router.py        08-27 23:26   ← 안 건드려짐
        ledger_api/ledger_subgraph.py 08-28 18:12   ← 안 건드려짐
```

## 트리에 있는 것이 «지시 ① 그대로»입니다
`server/ledger/setup_bundle.py::_validate_vocabulary` (+16 / −1):
```python
if not problems.exact(
        item, path, required=("status", "subjects", "object"),
        optional=("continues",)):
    continue
if "continues" in item and not isinstance(item["continues"], bool):
    problems.add("invalid_predicate", f"{path}.continues", "must be true or false")
```
그 위에 13줄짜리 주석이 붙어 있고, **지시서의 「왜 술어 칸인가」 논거(8/11 · 11/11 · 부재가
뜻을 가진다)를 그대로 담고 있습니다.** 즉 이 지시를 읽은 «누군가»가 쓴 것입니다.

## 🔴 그리고 지시서에 «없는» 파일이 하나 더 바뀌어 있습니다
```json
server/ledger/ledger_skeleton.json  (+9)
  { "key": "continues", "required": false, "label": "자재 연속",
    "node": { "kind": "leaf", "hint": "flag" } }
```
어드민 작성 폼의 칸입니다. 제 지시서 ①②③ 어디에도 «없습니다».

## 그래서 안 했습니다 — 무엇을·왜
```
⛔ setup_bundle.py · ledger_skeleton.json  «열지도 안 건드리지도» 않았습니다
   남의 미커밋 작업입니다. 커밋하면 남의 것을 제 이름으로 착지시키는 것이고,
   되돌리면 지우는 것입니다 — 오늘 이 채널에서 그 부류를 두 번 봤습니다
⛔ ②(라우터) ③(walk) 도 «아직» 안 했습니다
   04:38에 ①을 쓴 손이 ②③으로 «가는 중»일 수 있습니다. 그러면 같은 지시를 두 레인이
   도는 것이고, 총괄이 보고처를 갈라 «막으려던» 바로 그 모양입니다
```

## 👉 판정 요청 — 셋 중 하나만 주시면 바로 갑니다
```
ⓐ 그 미커밋 변경이 «총괄 것»이다      -> 커밋은 총괄이 하시고, 저는 ②③만 갑니다
ⓑ 다른 레인이 이 라운드를 «돌고 있다»  -> 저는 빠집니다. 이 보고서만 남기겠습니다
ⓒ 그건 잔재이고 이 라운드는 «제 것»이다 -> ①의 커밋 권한을 주시면 세 개 다 한 커밋으로 갑니다
                                        (그 경우에도 skeleton 변경은 «지시 밖»이라 따로 여쭙니다)
```

## 그동안 «값이 남는 것»은 재 뒀습니다 — 게이트 ①의 «전» 줄
지시대로 총괄 문서에서 베끼지 않고 직접 쟀습니다.
```
GET /api/ledger/subgraph
   id = wafer{SYN-BW-101-16} · hops=6 · node_limit=1000 · direction=both

전(HEAD + 위 미커밋 변경 상태)
   nodes «754» · edges «1200» · hops_reached «2» · truncated [claims, edges]
   타입 분포  wafer 530 · die 117 · defect 89 · quantity 18

그리고 새 인자가 «아직 없다»는 것도 같이 쟀습니다
   continues_hops=0 -> 위와 «동일»    continues_hops=4 -> 위와 «동일»
   (FastAPI가 선언 안 된 쿼리 인자를 조용히 무시합니다 — ③의 「인자가 산다」는 지금 «거짓»입니다)
```
⚠️ 이 「전」 값은 «미커밋 변경이 트리에 있는 상태»에서 잰 것입니다. ①은 검증기라 walk 응답에
   영향이 없어 같은 수여야 하지만, **어제 제가 「트리에서 재고 커밋에 도장 찍었다」로 사고를
   낸 바로 그 자리**라 상태를 명시해 둡니다. 판정 후 다시 재서 전/후를 나란히 적겠습니다.
