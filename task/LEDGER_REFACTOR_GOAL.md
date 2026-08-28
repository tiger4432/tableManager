# 목표 — 원장 전면 리팩토링 (소유자 2026-08-28)

> 「원장 전면 리팩토링 진행」 · 「엔티티 어휘 walk 이게 끝」 · 「다 지워」
> 「kinds, finding 이란 말이 불편한데? 엔티티 술어 아니잖아」

---

## 🔴 도착지 — 아침에 이 다섯 문장이 «참»이면 끝난 것이다

```
① 화면·응답·선언 어디에도 «엔티티도 술어도 아닌 낱말»이 없다
     없어야 할 것: finding · finding_kind · kinds · node_kind · collect · claim · point
                  collection · quantity · value(노드로서) · enrich-action
② 결함의 «종류»는 노드다        defect_kind@1 엔티티 · of_kind@1 술어
③ 원장이 선언을 따라온다         선언을 고치면 원자가 그 모양이 된다 (코드 0줄)
④ 코드가 도메인 낱말로 갈래를 안 튼다   `== "void"` 류 «0»
⑤ 안 닿는 원장 모듈이 «0»       진입점 어디에서도 안 닿는 ledger 파일이 없다
⑥ «두 번째 온톨로지 선언»이 없다   ledger_config.json 하나가 «온톨로지»의 전부다
     🔴 2026-08-28 정정: 처음에 「선언 파일이 하나」로 적었는데 «닿을 수 없는 도착지»였다.
        table_config.json 은 «물리 스키마»의 정본이고(CLAUDE.md 기존 판정),
        인제션·체인·맵이 읽는다. 온톨로지에 물리 컬럼을 넣으면 두 관심사가 섞인다
     흡수 대상은 «둘»: mechanism_models.json · finding_kinds.json
     🔴 그리고 «선언만으로는 안 보인다» — walk 은 원자를 걷는다
        (증거: has_wafer@1 · derived_from@1 은 선언 술어인데 원자 0이라 walk 에 안 나온다)
        -> 흡수는 «선언을 소스로 삼는 인제션»이다. walk 이 선언에서 엣지를 만들게 하는 것이
           아니다 — 그건 오늘 아침 지운 references 기전을 다시 만드는 것이다
     지금 셋: mechanism_models.json · finding_kinds.json · (그리고 table_config.json)
     그 둘이 든 것은 «노드와 엣지»다 — bond_pressure -> interface_unfill -> void
     흡수되면 mechanism_gate 17KB(두 번째 그래프 탐색기) · finding_kinds 15KB 가 walk 하나로
```

## 지금 (2026-08-28 09:0x 실측)

```
① 낱말      walk 응답에 finding_kind «121»  · defect_kind «0»      ❌
            라이브 코드에 finding 48 · kinds 40 · finding_kind 24  ❌
② 종류      선언에 defect_kind@1 · of_kind@1 «있음»(총괄이 방금 넣음)  🟡 원자가 아직 없음
③ 따라옴    첫 변경(defect@1)에서는 «따라왔다» — 원자 103,841 이 entity_ref 로
            둘째 변경에서는 «아직». 백필 실행 중                      🟡
④ 갈래      제품 코드에 결함 종류 철자 «0» (어젯밤 C 가 지움)          ✅
⑤ 고아      ledger 관련 «여섯» · 78,545 B                            ❌
              profile_chain_mapper 19,620 · audit_changeset 20,442
              enrichment_actions 17,472 · chain_mapper 16,279
              profile_lookup_adapters 4,650 · examples 82
```

## 남은 일 — 도착지 기준으로만 적는다

```
[A] ①③ 선언·원자      of_kind 원자가 생기고 walk 이 defect_kind 노드를 낸다
                      observed 수식어에서 finding_kind 가 사라진다
[B] ① 코드 낱말        ledger_subgraph 의 죽은 import(finding_kinds) · 558~565 씨앗 잔재
                      docstring 의 「Finding Collection --finding--> Quantity」 서술
[C] ⑤ 고아 여섯        구성원마다 «소비자를 세고» 지운다
                      ⚠️ profile_chain_mapper 는 transferred 원자(0건)를 발화하던 v1 쓰기 경로
[D] ① finding_kinds.py 카탈로그는 선언이 대신한다.
                      남는 SQL 조각(population_ctes · payload_field_sql)은 «다른 질문»이므로
                      쓰는 쪽(씨앗 스크립트)으로 가거나 이름을 바꾼다 — 판정 필요
```

## 🔴 하지 않는 것 — 이번에도 명시한다

```
⛔ walk 자체를 다시 쓰지 않는다 — 882줄이 «넷»으로 회계돼 있다(SQL 두 arm · BFS · 예산 · 씨앗)
⛔ 화면 열둘을 이번에 짓지 않는다 — 그건 별도 라운드다
⛔ 「지울 수 없다」가 나오면 «전제»를 먼저 잰다. 어젯밤 두 번 다 전제가 거짓이었다
⛔ 숫자(줄 수·파일 수)를 목표로 삼지 않는다. 도착지는 위 다섯 «문장»이다
```

## 라운드마다 대조할 것

```
매 착지   walk 200 · 노드 «전부» ledger-entity · 엣지 «전부» 선언된 술어
          자재 9종 · defect 121 · 라우트 둘
그리고    위 다섯 문장 중 «몇이 참이 됐나»를 보고에 적는다
```
