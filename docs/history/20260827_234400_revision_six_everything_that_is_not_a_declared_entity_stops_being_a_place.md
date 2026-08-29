# 개정 6 — 「선언된 엔터티가 아닌 것은 «자리»이기를 그만둔다」. 라우트 여덟과 노드 종류 축이 같은 밤에 나갔다

> **커밋:** `2cb9a8b9` (22:25) · `cb504254` (22:30) · `ab0b1ad6` (22:30) · `73cdfdbf` (22:43)
> · `000a5cc6` (22:58) · `ed1ac47c` (23:11) · `c7350f5e` (23:25) · `449a58d9` (23:27)
> · `10f58b7c` (23:35) · `9f0d964d` (23:44)
> | **일자:** 2026-08-27 심야
> **레인:** 서버 레인 A(walk) · 레인 B(라우터) + 클라(걷기 상자)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 소유자 판정: 「엔티티 · 어휘 · walk. 이게 끝」

노드 id 를 만드는 함수가 **일곱**이라 `decode_node_id`가 접두어로 갈래를 텄고, 그 갈래 수가
그대로 walk 루프의 갈래 수가 됐다 — 그중 **원장을 읽는 것은 `entity` 하나**였고 나머지는
**투영이 접은 것을 투영이 다시 펴는 자리**였다.

## 레인 B — 라우터가 «두 라우트»가 됐다

`2cb9a8b9`. **679줄 → 316줄.** 남은 것은 walk 과 선언이다.

```
지운 라우트 «8»   /subgraph/table · /siblings · /trends · /composition
                 /selection/resolve · /kinds · /structure · /lot_map
                 + 그것들만 부르던 헬퍼 둘 + 읽는 이 없어진 임포트 열둘
함께 나간 표면 셋  /subgraph 의 observations 축 (접힘이 사라지면 고를 것이 없다)
                 follow 검증기와 /declaration 의 «참조 엣지 광고» 둘
```

부재 단언을 **집합 등식**으로 바꿔서 **라우트가 다시 생겨도 산수로는 통과 못 하게** 했다.

## 레인 A — walk 이 1,927 → 1,437, 그리고 접두어가 하나가 됐다

`ab0b1ad6`. 지운 것마다 **소비자 수를 먼저 세고** 지웠다:

```
id 빌더 5     finding_point · finding_collection · quantity · value · event   외부 소비자: 시험뿐
노드 빌더 8   _finding_point_node · _finding_collection_node · _quantity_node
              _claim_node · _event_node · _value_label · _bound_quantities · _enrich_action_node
decode_node_id   접두어 갈래 여섯  ->  «하나», ledger-entity:v1:
walk 루프     네 무리(발견 요약 · 발견점 · 물리량 · 소스 이벤트) + enrich 꼬리 175줄
_expand_atom  entity_ref 갈래가 «함수 전체»가 된다
```

🔴 **`claim_node_id`는 일부러 남겼다.** 인구조사가 「외부 소비자 3」이라 했고 둘은 시험인데,
`enrichment_actions.py:268`이 `atom.claim_node_id` — **EvidenceAtom 의 «속성»** — 을 읽고
그 속성이 함수를 부른다. **내 grep 이 함수와 속성을 거의 혼동할 뻔한 이름**이었다. 신고만 했다.

## 모듈 넷이 «세고 나서» 나갔다

`cb504254`. 지난번에 「공유하는 이유」로 묶었을 때 멤버 하나에 살아 있는 소비자가 있었기 때문에,
이번엔 임포터를 전부 셌다:

```
ledger_trends.py       임포터 4
ledger_composition.py  임포터 4
ledger_structure.py    임포터 6
ledger_lots.py         임포터 9
```

라우터와 시험 밖의 **살아 있는 임포터는 «하나»** — `ledger_selection.py`가 집계의 subject type 을
`ledger_trends.DEFAULT_GRAIN`에서 읽고 있었다. 그 낱말을 **선언에 묻게** 바꿨다(실측 `wafer`,
grain 이 들던 값과 같다). 시험 파일 여섯 · 살아남는 파일 안의 시험 함수 다섯 · 스크립트
진입점 둘이 같이 나갔다. `SCORED_AGGREGATES`는 **남겼다** — 고아처럼 보였지만
`seed_syn_aug_material.py:259`가 읽는다.

## 코드에 도메인 낱말이 «0»이 됐다

`73cdfdbf`. `DEFAULT_KIND` 상수 · void/delam dict 카탈로그 · `ledger_selection`의 void 전용
갈래 · 신원의 집계 쌍에 박힌 void.

```
finding_kinds.py   17,255 -> 15,058 바이트. 레지스트리가 «비어서» 시작하고
                   config/finding_kinds.json 이 선언하는 것이 전부다
                   기본 kind 를 잃은 시그니처 «6» -> 호출자가 각자 자기 kind 를 이름 댄다
ledger_selection.py 74,646 -> 72,561. void 전용 결함 층과 _void_map_cells_sql 이 나갔다
                   그 생산자가 SQL 에서 void_obs 라고 이름 대고 있어서 «다른 종류는 층이
                   아예 없었고 맵은 독자가 볼 수 있는 어떤 방식으로도 그것을 인정하지 않았다»
ledger_identity.py {"kind": "void_by_experiment_unit", "finding_kind": "void"} 가 나갔다
```

`000a5cc6`이 컨테이너 작성자를 지웠다 — **선언이 그것을 선언하기를 그만뒀기 때문**이다.
`ed1ac47c`이 **이제 아무도 부를 수 없는 조회 메서드 넷**을 지웠다.

## 투영 손잡이 다섯이 나가고, 순위가 함께 나갔다

`c7350f5e`(레인 B) — `include_values` · `enrich_actions` · `shape` · `property_limit` · `collect`.
`collect`가 **어느 노드 «종류»를 순위 매길지 고르던 것**인데 **모든 노드가 선언된 엔터티인
지금 값이 하나뿐인 스위치는 스위치가 아니다.** 부호 붙은 씨앗은 남는다 — 그건 투영이 아니라
walk 을 바꾼다.

```
측정 후: 라우트가 받는 것 = id · hops · direction · node_limit · edge_limit
                          · positive · negative · follow
웨이퍼 씨앗 walk 400 노드   id 전부 ledger-entity:v1: · 타입 전부 die/wafer
                          엣지 전부 bonded_from/inspected/transfer
                          has_findings «없음» · in_container «없음» · mechanism «없음»
```

🔴 그리고 **자기 측정을 보고하기 «전»에 스스로 정정했다** — 모르는 질의 인자가 422 를 내는 것처럼
보였고 그게 참이면 이 변경이 클라의 걷기 상자를 깬 것이 된다. 원인은 **자기 `node_limit`
5가 최소값에 걸린 것**이었다. 유효한 값으로 다시 재니 **모르는 인자는 무시되고 클라는 돈다.**

`9f0d964d`(레인 A)가 마지막 호출자와 함께 `collect` · `observation_mode` · `include_values` ·
`NODE_KINDS` · `RETIRED_NODE_KINDS` · `FOLDED_KINDS` · 응답의 `walk.collect` · `_rank_layers`를
지웠다. **1,171 → 1,082. 그날 밤 시작부터: 1,927 → 1,082, 그리고 walk 은 같은 답을 낸다.**

## 🔴 관측이 «항상» 가져와져야 했다 — 접힘이 나가면서 잠깐 안 닿았다

`449a58d9`. 투영 손잡이가 나가면서 관측이 조건부가 됐고 **발견에 닿지 못했다.**
그 라운드 안에서 「관측은 항상 가져온다」로 고정됐다. `10f58b7c`가 클라의 COLLECT 드롭다운을
없앴다 — **모든 노드가 선언된 엔터티이므로 고를 것이 없다.**

## 🔴 그리고 span 단언이 파일을 두 번 살리고 한 번 못 살렸다

`9f0d964d` 자기 기록: `NODE_KINDS` 블록을 지우면서 `_IDENTIFIER`가 함께 딸려 나갔다 —
span 검사가 `def `는 봤지만 **상수 사이에 앉은 다른 정의는 안 봤다.** 실행해서 잡고 HEAD 에서
복원했다. 교훈은 좁은 쪽이다: **span 이 «짧다»가 아니라 «무엇을 담으면 안 되는지»를 단언한다.**

## 아키텍처 영향

- **노드 종류 축이 없다.** 노드는 선언된 엔터티뿐이고 id 접두어는 `ledger-entity:v1:` 하나다.
- **라우트가 둘**이다 — walk 과 선언. 키를 받는 데이터 라우트 여덟이 사라졌다.
- 투영이 지어내던 노드 타입과 합성 엣지(`has_findings` · `in_container` · `mechanism`)가 없다.
- **제품 코드에 결함 종류 낱말이 0**이다. 카탈로그는 선언이다.

## 그때 남아 있던 것

- `ab0b1ad6` 시점에 **`claim_node_id`와 `NODE_KINDS`/`RETIRED_NODE_KINDS`가 일부러 남았다** —
  각각 다른 레인이 든 파일에 살아 있는 소비자가 있었다. 그날 밤 안에 닫혔다.
- 🔴 **종류 카탈로그가 이 상자에 «집이 없다».** `server/config/*`가 gitignore 라 대체물은
  `config/sample/finding_kinds.json.sample`로 배포됐고, 누군가 실체화하기 전까지 **이 상자의
  레지스트리는 비어 있다.**
- `2cb9a8b9`이 게이트 둘·셋은 **자기 레인이 못 닫는다**고 적었다 — 그 시점 walk 이 여전히
  finding-collection id 열다섯과 `has_findings`/`in_container` 엣지를 냈다. `c7350f5e`에서 닫혔다.
- `cb504254` 시점에 라우터가 **아직 지운 모듈 넷의 이름을 임포트**하고 있었다 — 레인 B 가
  착지할 때까지.
