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

### ② 발견 · 종류 — «전부» 선언으로. 예외 없음
> 소유자 2026-08-28: 「무조건 전환」 · 「delam observed at die 하면 되잖아」
> 「delam 속성에 길이 넣고 이고 예시고 모든게 가능함」
> 🔴 **「뭔가 지울 수 없다는 건 하드코딩이니 무시하고 지울 것」**

제가 앞서 「has_findings 는 «유일한 연결»이라 못 지운다」고 적은 것은 **제약이 아니라
하드코딩을 제약으로 보고한 것**입니다. 유일한 연결인 «이유»가 투영이 그렇게 박아서입니다.

```
지금   observed@1  주어 die@1 · 목적어 «value» · 원자 103,841
       투영이 Finding Point / Finding Collection 을 만들고 has_findings · finding 으로 붙인다
       종류(void · delam)는 «파이썬 dict» 에 산다 — finding_kinds.py:105·117·134

개정   entities.defect@1                 (키는 §3)
       entities.defect_kind@1            void · delam · 그리고 앞으로 무엇이든
       entities.scan@1                   run_uid
       vocabulary.observed@1   주어 die@1 · 목적어 entity_ref -> defect@1
       vocabulary.of_kind@1    주어 defect@1 · 목적어 entity_ref -> defect_kind@1
       vocabulary.seen_by@1    주어 defect@1 · 목적어 entity_ref -> scan@1
```
🔴 **delam 도 같은 자리에 들어갑니다.** 파서가 아직 없다는 것은 «원자가 0» 이라는 뜻일 뿐,
   선언에서 뺄 이유가 아닙니다. 선언에 있으면 데이터가 오는 날 코드 0줄로 발화합니다.
   (총괄이 앞서 「delam 은 픽스처라 제외」라고 적은 것 — 소유자 지시로 «철회»합니다)

속성은 defect@1 이 듭니다 — 소유자 예시 「길이」 포함:
```
inchip_x · inchip_y · radius_y · unit · gate   그리고 종류마다 다른 것(길이 등)
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
✅ delam 도 «선언에 넣습니다» (소유자 지시). 파서가 없다 = 원자 0 일 뿐이고 선언의 문제가 아닙니다
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

---

# 6. 🔴 지울 하드코딩 — 실측 목록 (총괄 2026-08-28)

> 소유자: 「하드코딩 아직도 안 없애고 있네」 · 「지울 수 없다는 건 하드코딩이니 무시하고 지울 것」

## 투영이 «지어낸 낱말» — 전부 `ledger_subgraph.py`
```
787   "type": "Finding Point"
816   "type": "Finding Collection",  node_kind "collection"
1170  씨앗 경로의 "Finding Point"
1180  씨앗 경로의 "Finding Collection"
1523  _edge("has_findings", subject_id, collection["id"], …)
1705  주석의 발명 엣지 목록: has_findings · on_subject · contains · finding · mechanism · needs_enrichment
12·13·20  모듈 docstring 이 그 구조를 «설계»로 적어 둔 자리
```
`ledger_trace_router.py:107`  `observations=summary|claims` 축 설명
   -> 낱개/묶음은 «타입»이 아니라 세는 방식입니다 (소유자 판정 2026-08-27). 이 축도 같이 갑니다

## 도메인 낱말이 «코드에 값으로» 박힌 자리
```
finding_kinds.py:105   DEFAULT_KIND = "void"
finding_kinds.py:117   "void":  { … }        <- 종류 카탈로그가 «파이썬 dict»
finding_kinds.py:134   "delam": { … }
ledger_identity.py:116  "kind": "void_by_experiment_unit", "finding_kind": "void"
🔴 ledger_selection.py:565  if finding_kind == "void" and final_units:
                            <- «코드가 도메인 낱말로 갈래를 튼다». 이게 가장 나쁩니다
```

## 판정
```
위 전부 «지웁니다». 「유일한 연결이라 못 지운다」는 근거가 아닙니다 —
유일한 연결인 이유가 저 박아 놓은 코드이기 때문입니다
종류 카탈로그는 dict 가 아니라 «선언»(defect_kind@1)이 듭니다
그래야 「다른 스키마 운영 환경에서 코드 0줄」이 참이 됩니다
```
