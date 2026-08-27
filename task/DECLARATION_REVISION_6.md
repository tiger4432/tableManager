# 선언 개정안 — 「투영이 만들던 것을 «전부» 엔티티·어휘로」

> 소유자 지시 2026-08-28: 「그냥 다 엔티티 어휘로 전환」
> 원칙(CLAUDE.md): 「술어가 아닌 것은 표면적으로 노드」 · 「선언을 읽으면 그래프를 안다」
> 🔴 규칙 하나로 줄입니다 — **엣지는 «선언된 술어»뿐. 투영은 엣지를 만들지 않는다.**

---

## 1. 지금 투영이 «지어내는» 것 — 전수 (총괄 실측 2026-08-27~28)

```
합성 엣지            잇는 쌍   그중 «유일한 연결»    지금 어디서 오나
  in_container        128            «0»            entities.die@1.references
  has_findings         28            «28»           투영 (observed 의 value 원자)
  finding              56            «56»           투영 (Quantity <-> Finding Collection)
  mechanism             8            «8»            config/mechanism_models.json
지어낸 노드 타입
  Finding Point                                     observed 원자 «낱개»
  Finding Collection                                observed 원자 «묶음» (label "void (5)")
  Quantity                                          집계 투영
  WaferLeg                                          트렌드 grain 의 이름 (원자 0)
```
🔴 `in_container` 만 «유일한 연결 0» 입니다 — **지워도 그래프가 안 끊깁니다.** 나머지 셋은 끊깁니다.

## 2. 개정 — 무엇이 무엇이 되나

### ① `in_container` · `references` — «삭제»
```
근거   유일한 연결 «0». wafer<->die 는 inspected@1 원자가 이미 잇고, 원자 엣지는 «양방향»이다
       (소유자: 「어차피 있는 엣지 거꾸로 타고 가면 wf 에서 다이로 닿잖아」 — 실측 일치)
지울 것 entities.die@1.references (항목 2 · 266자)
       entity_references 의 targets_for · reference_edges · reference_edge_names
       ledger_subgraph.py:1442 · ledger_trace_router.py:206 · 561
       setup_bundle 의 entity optional "references" + _validate_references
🟢 남길 것  entity_references.declared_types · identity_keys  ← 소비자 «많음»
           ledger/config.py · source_profile_builtins.py · ledger_identity.py(동률 규칙) …
           🔴 모듈을 지우면 안 됩니다. 반만 죽습니다
```

### ② 발견 — `defect@1` 엔티티 + `observed@1` 목적어를 entity_ref 로
```
지금   observed@1  주어 die@1 · 목적어 «value» · 원자 103,841
       qualifiers optional: inchip_x · inchip_y · radius_y · unit · gate · finding_kind · run_uid
       -> 투영이 Finding Point / Finding Collection 을 만들고 has_findings 로 붙인다

개정   entities.defect@1                        (키는 §3 판정)
       vocabulary.observed@1  목적어 entity_ref -> defect@1
       -> Finding Point · Finding Collection · has_findings · finding «전부 불필요»
🟢 문법은 이미 있습니다 — entity_ref 목적어는 inspected@1 · transfer@1 이 쓰고 있습니다
```
수식어 일곱의 행선지 (제안):
```
inchip_x · inchip_y · radius_y · unit · gate   ->  defect@1 의 «속성»(원자 수식어 그대로)
finding_kind                                   ->  «종류» 노드   defect_kind@1 (void · delam …)
run_uid                                        ->  «스캔» 노드   scan@1
   -> 그때 「같은 스캔의 다른 발견」·「같은 종류의 다른 발견」이 walk 한 번으로 돈다
   (소유자 2026-08-27: 「디펙의 종류 모델링 등 다른 관계 및 노드가 붙을 수 있음」)
```

### ③ `mechanism` — 그대로 둡니다
```
출처가 config/mechanism_models.json 으로 «이미 선언»입니다. ledger_config 로 옮길 이유가 없습니다
⚠️ 다만 그 엣지가 잇는 «Quantity» 노드는 집계 투영입니다 — ②가 끝난 뒤 다시 봅니다
```

### ④ 원자 «0» 인 술어 둘 — 판정 필요
```
has_wafer@1     lot_slot -> wafer   원자 «0»   ← 랏에서 웨이퍼로 건너갈 다리인데 비어 있음
derived_from@1  lot -> lot          원자 «0»
   둘 중 하나: (ㄱ) 인제션이 채운다   (ㄴ) 선언에서 뺀다
   🔴 지금은 「선언은 있는데 아무도 말한 적 없는 낱말」이고, 그 상태가 제일 헷갈립니다
```

## 3. 소유자 판정이 필요한 «둘»

```
① defect@1 의 «키»            무엇이 같으면 같은 발견인가
                              후보: (run_uid, inchip_x, inchip_y)
                              지금 Finding Point 가 드는 것: {finding_kind, run_uid, map_id, position}
② 주어를 어느 쪽으로          소유자 초안은 「defect observed at die」 = «발견이 주어»
                              그러면 발견을 마킹해 바로 걸어 나갈 수 있습니다(마킹 = 질의의 주어)
                              지금은 die 가 주어입니다. 총괄 추천: «발견을 주어로»
```

## 4. 하지 않는 것 — 명시

```
⛔ delam 을 원장에 넣지 않습니다 — 파서가 «없고» 선언 sources 열에도 «없습니다».
   씨앗 스크립트 셋에만 있는 픽스처이고, 원장 원자 0 은 «설계대로»입니다
   (총괄이 8/27 에 「박리 위험」으로 올린 것은 픽스처를 쫓은 것이라 «철회»합니다)
⛔ 새 문법을 만들지 않습니다 — entity_ref 목적어·엔티티·키 전부 이미 있습니다
⛔ WaferLeg 를 엔티티로 만들지 않습니다 — 집계의 «이름»이지 노드가 아닙니다 (판정 2026-08-27)
⛔ 예산(node_limit 1000 · edge_limit 3000)을 손대지 않습니다 — 별개 문제입니다
```

## 5. 착지 순서 — 작업은 «일괄», 검증은 «분할»

```
선언 개정 «한 번»  ->  재적재 «한 번»  ->  게이트를 «하나씩»
   ⓐ 조립 자재 «9종» 그대로   (기준선 nodes 800 · edges 1,314 · 자재 9)
   ⓑ 발견 «28 / 128» 그대로   (맵과 «같은 수». 트렌드는 점들의 «합»으로 비교)
   ⓒ 보드 요청 «14» · non-200 «0»
   ⓓ /declaration 의 predicates 에 in_container «없음» · follow=in_container 는 422
   ⓔ walk 응답에 Finding Point · Finding Collection · has_findings «0건»
```
🔴 선언을 조각내면 재적재를 여러 번 하게 되고 그게 제일 비쌉니다. 그래서 작업은 일괄입니다.
🔴 그런데 오늘 하나 고칠 때마다 «앞 수리가 가리던 결함»이 나왔습니다(씨앗→트렌드0→분모).
   그래서 «검증»은 게이트별로 갑니다.
