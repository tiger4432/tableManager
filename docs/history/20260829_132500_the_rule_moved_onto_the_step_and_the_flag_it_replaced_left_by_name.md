# 규칙이 «노드»가 아니라 «걸음»에 붙었다 — 그리고 그것이 대체한 플래그가 이름째 떠났다

> **커밋:** `2f0251e4` (12:31) · `9f8db5ab` (12:58) · `35f1963c` (13:17) · `4001fe62` (13:25)
> | **일자:** 2026-08-29 낮
> **레인:** 서버(walk · 선언 · 검증기) + 클라(R&D 보드)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — `continues` 는 «자재 예산»이었지 «허가»가 아니었다

전날 새벽 `continues` 가 술어마다 붙는 플래그로 선언에 들어갔다(→ `20260829_045900_...`).
그런데 그것이 실제로 하던 일은 **「같은 자재 안을 걷는 걸음은 «떠남»이 아니니 홉을 안 쓴다」**
였고, 그건 **술어의 성질이 아니라 «양 끝 노드»의 성질**이다.

이 라운드는 그 축을 **엔티티 클래스**로 옮기고, 옮긴 것이 재어진 뒤 **옛 플래그를 은퇴**시킨다.

## ① 엔티티가 static / dynamic 을 «선언»한다 — 네 조각이 같이 움직였다

`2f0251e4`. `4cbcb086` 이 세운 모양 그대로 넷이 함께 갔다.

```
검증기   엔티티에 «선택» 필드 `class`. static·dynamic 이외의 철자는 «이름을 대고» 거절
스켈레톤 같은 필드 -> 작성 폼이 그것을 «내놓는다»
라우트   정적 집합을 «선언에서만» 읽는다
walk    그것으로 정책 «하나»를 강제한다
```
⚠️ **부재는 dynamic 을 뜻하고 «적지 않는다».** 그래야 「dynamic 으로 선언됨」과
「한 번도 분류 안 됨」이 계속 구별된다.

## 🔴 그리고 «어디에» 규칙을 붙이느냐가 재서 갈렸다

당연해 보이는 철자 —「정적 노드를 펴지 마라」— 는 **정적↔정적도 같이 자른다.**

```
씨앗 quantity{bond_pressure} · follow=leads_to
   「정적 노드를 펴지 마라」   ->  «1 노드 · 0 엣지»   인과 사슬이 «통째로» 사라진다
                                (그 사슬의 모든 고리가 quantity → quantity 이기 때문)
   「걸음이 s->d 면 거절」     ->  18 노드 · 18 엣지 · hops_reached «4»  = 오늘과 동일
```
소유자의 문장이 맞는 철자였다 — **`s -> s` 허용, `s -> d` 거절.**

```python
# 🔴 A NAME MAY BE REACHED, AND MAY LEAD TO ANOTHER NAME, BUT NOT BACK INTO THE
# WORLD. The owner's rule is about the STEP and not about the node: `s -> s` is
# allowed, `s -> d` is not. ...
near_kind = far_kind = None
if subject_near and not target_near:
    near_kind, far_kind = _bare(atom.subject_type), _bare(payload.get("type"))
elif target_near and not subject_near:
    near_kind, far_kind = _bare(payload.get("type")), _bare(atom.subject_type)
if near_kind in static_types and far_kind and far_kind not in static_types:
    return
```

정책이 «무엇을 위한 것인지»도 같이 쟀다 (wafer SYN-BW-101-16 · hops=6 · both · 1000/3000):
```
정적 집합 «빈» 상태   nodes 1000 · edges 3000 · 절단 claims+edges+nodes · wafer «776»
정적 집합 «적용»      nodes  225 · edges  224 · 절단 claims           · wafer «1»
```
🔴 775 개의 웨이퍼가 **`defect_kind` 와 `quantity` 를 거쳐 «거꾸로»** 들어오고 있었다 —
둘 다 **모든 인스턴스가 가리키는 «이름»** 이다. `defect_kind` 는 원자 **103,841** 개를
지고 있는데 **서로 다른 목적어는 정확히 «하나»** 다.
노드·엣지 절단은 걷히고 **주장 절단은 여전히 문다**. 그리고 그 씨앗에서 `defect_kind` 는
**여전히 안 닿는다** — 덮지 않고 그대로 보고됐다.

⚠️ **정책 넷 중 «넷째»만 강제된다.** 1·2·3 은 허용형이라 아무 코드도 안 짰다 — 특히
**한 홉 상한을 안 만들었다.** 그것도 같은 사슬을 잘랐을 것이다.

## ② 예산 면제가 «술어 플래그»에서 «엔티티 클래스»로 갈아 끼워졌다

`9f8db5ab`. 정책 1 은 **허가가 아니라 «예산 면제»** 로 판명됐다 — 즉 `continues` 와
**같은 기계이고 키만 다르다.**

```python
# 🔴 A STEP BETWEEN TWO HAPPENINGS IS NOT A DEPARTURE - policy 1 of
# `ONTOLOGY_GRAPH_SPEC` §7.5c, and the same machine `continues` was, keyed on the
# ENTITY CLASS instead of on a per-predicate flag.
_charge = 0 if (near_kind and far_kind
                and near_kind not in static_types
                and far_kind not in static_types) else 1
```

게이트가 **대체를 재는 모양**이었다 — 「새 것이 좋다」가 아니라 **「옛 것의 수를 맞추거나
넘는가」**:
```
씨앗 wafer SYN-BW-101-16 · hops=1 · outgoing · 자재 술어 6 + processed_with
   continues_hops=0    nodes  40 · reached 1 · 절단 depth
   continues_hops=4    nodes 157 · reached 3 · 절단 «없음»
   continues_hops=6    nodes 157 · reached 3 · 절단 «없음»
   continues_hops=12   nodes 157 · reached 3 · 절단 «없음»
```
**157 이 맞춰야 할 수였고 거기서 «정착»한다.** 넘지 않는 이유까지 적혔다 —
D→D 가 들고 `continues` 가 안 들던 유일한 술어 `observed` 가 **이 follow 목록 밖**이라
추가 멤버가 여기서는 더할 것이 없다.
```
게이트 2   continues_hops 를 «안 주면» 답이 불변 — 이 파일을 HEAD 로 되돌린 것과 대조
          225 노드 · 224 엣지 · reached 2 · 절단 claims, «양쪽 동일»
게이트 3   인과 사슬은 여전히 4 에 닿는다
```
`continuing` 은 **과금에 안 쓰이면서 남았다.** 지금 은퇴시키면 **클라의 `continues_hops`
선언 둘이 없는 것을 가리키게** 되기 때문이다. **무제한 순회는 안 만들었다 — 둘째 예산도
여전히 예산이다.**
`tests/test_ledger_subgraph.py` + `test_ledger_explorer.py`: **12 passed · 1 skipped**.

## 🔴 ③ 은퇴 — 그런데 검증기 «하나»만 일부러 관용을 남겼다

`35f1963c`. 플래그가 walk·라우트·스켈레톤에서 사라졌다 — `continuing` 파라미터 없음,
`_continuing_predicates` 없음, 술어 레코드의 잎 없음, `_bare_predicate` 도 **마지막 호출자와
함께** 갔다. **예산 계산은 안 옮겼다** — 이미 엔티티 클래스에 키가 걸려 있었다.

```
검증기만 «관용을 유지»한다. 일부러, 그리고 «잠깐»
이유    라이브 선언이 여섯을 «아직 들고 있다»
       거절하면 «아무도 그것을 지우기 전에» 서버가 선언을 못 읽는다
       -> 필드가 들어올 때와 «같은 순서 문제»가 반대로 도는 것이다
```
그리고 이름이 **정책을 따라** 바뀌었다 — `continues_hops` → **`backbone_hops`**.
**옛 철자에 별칭을 안 뒀다.** 소비자가 둘 다 우리 것이고,
**치울 사람이 없는 호환 층은 영원히 남는다.**

```
게이트   선언은 여전히 continues 여섯을 들고 walk 은 여전히 답한다 (정리보다 «앞서» 검증 통과)
        backbone_hops=0 -> 40 노드 · depth 절단 |  =4 -> 157 · 절단 없음
        follow 에 observed 를 더하면 -> 246   (총괄이 잰 수)
        «옛 철자» continues_hops=4 -> 40, 예산 없는 요청과 «동일»
        => 무시되는 것이지 «조용히 옛 일을 하는» 것이 아니다
-k "subgraph or setup_bundle or skeleton or explorer or l1_unit":
   218 passed · 2 skipped · 7 failed — FAILED 정렬 목록이 그날 HEAD 대조와 «동일»
```
플래그를 서술하던 주석 셋이 클래스 규칙을 서술하도록 고쳐졌고, 그중 하나는
**라우트의 파라미터 설명 — 사용자에게 보이는 문장**이다.

## ④ 전선의 이름이 바뀌었고, 그 순간 «재기동 창»이 열렸다

`4001fe62`. 클라가 새 이름을 쓴다. 그런데 **서버 프로세스가 아직 안 재기동됐다**
(가장 최근 백엔드 기동 13:18, 개명은 그 뒤 착지).

🔴 **게이트 A 가 «빨강»이고, 두 가지 방법으로 쟀다** — 상태 코드만으로는 절반만 말하기 때문이다.
```
코드로   backbone_hops=abc -> «200»   |  continues_hops=abc -> «422»
        = 모르는 파라미터와 «같은 모양»
효과로   씨앗 wafer SYN-BW-101-16 · hops=1 · outgoing · 자재 7
        예산 없음         -> 40 노드 · depth 절단
        continues_hops=4  -> 157 노드 · 절단 없음   (총괄 수 재현)
        backbone_hops=4   -> 40 노드 · depth 절단   = «아무것도 안 보낸 것과 문자 그대로 같음»
```
**효과 측정이 더 강한 증거다** — 이름을 모른다가 아니라 **예산이 «버려진다»**를 보인다.

그런데도 **미루지 않고 착지시켰고, 그 근거가 수다.** 별칭이 없으니 정적 파일 하나가
재기동 양쪽에서 동시에 옳을 수 없다 — 그래서 질문은 **「어느 창이 비용을 무나」**다.
```
좌석 씨앗 SYN-CX-BW-001 다이 40 · SYN-BW-101-02 다이 8 · 칩 확대 좌석의 실제 질의
   -> 예산 있든 없든, 옛 이름이든 새 이름이든 «전부 동일하게» 답한다
   이유: 좌석 씨앗은 예산이 물릴 만큼 «깊이 안 걷는다» (게이트 B 의 씨앗은 좌석 씨앗이 아니다)
=> 새 이름으로 먼저 가면 재기동과 «같은 방향»이 된다
   이 논증을 죽일 조건(「좌석이 예산이 물릴 만큼 깊이 걷는 날」)이 그 줄 옆 주석에 적혔다
```

번들을 다시 빌드해 재었다 — `backbone_hops` **11회** 등장, `continues_hops` **0**,
라이브 페이지가 새 이름을 실은 요청 **12** 개를 내고 옛 이름은 **0**.
```
하니스   rnd_board 170/0 · control_trend 59/0 · walk_box 48/0 · walk 32/0
        composition 40/0 · intersection 24/0 · reach 63/0
```
🔴 **하니스는 이 파라미터를 한 번도 언급하지 않는다.** 그래서 개명이 하니스 전부에게
**조용하다** — 「200 은 파라미터가 읽혔다는 증거가 아니다」의 클라 쪽 얼굴이고,
**게이트 A 가 여기가 아니라 서버에 있어야 하는 이유**다.

## 아키텍처 영향

- **엔티티가 `class`(static/dynamic)를 선언한다.** 부재는 dynamic 이고 적지 않는다.
- **정책 4 가 «걸음»에 강제된다** — `s -> s` 허용, `s -> d` 거절. 정책 1·2·3 은 허용형이고
  코드가 «없다».
- **홉 면제가 엔티티 클래스에 걸린다.** 술어 플래그 `continues` 는 walk·라우트·스켈레톤에서
  사라졌다.
- **전선 이름이 `backbone_hops`** 이고 **별칭이 없다.**

## 그때 남아 있던 것

- **검증기가 `continues` 를 아직 관용한다.** 일부러이고, 라이브 선언에서 여섯이 지워질 때
  같이 간다고 주석에 적혀 있다.
- **라이브 선언이 `continues` 여섯을 아직 들고 있다.**
- **서버가 재기동 전이라, 전선의 새 이름이 «아직 안 읽힌다»** — `backbone_hops=abc` 가 200 을
  준다. 이 항목을 쓰는 시점 기준으로 그것은 관측이지 결함이 아니다.
- `-k "subgraph or setup_bundle or skeleton or explorer or l1_unit"` 의 **빨강 7** 은
  그날 HEAD 대조와 **정렬 목록이 동일**하다 — 이 라운드의 것이 아니다.
- 프리빌드 게이트 둘(`check:contracts` · `check:harnesses`)이 **다른 레인 것으로 빨간 채**였고
  손대지 않았다.
- 이 항목의 노드·엣지·원자 수는 전부 **이 상자의 씨앗**에서 잰 것이다.
