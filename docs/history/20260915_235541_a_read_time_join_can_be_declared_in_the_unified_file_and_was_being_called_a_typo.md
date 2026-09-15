# 통합 파일에 «읽기 시점» 조인을 적을 수 있다 — 문법엔 있었고 읽는 쪽이 없었으며, 그 선언은 «오타»로 보고되고 있었다 (S-251)

> **커밋:** `e175d3f8` — feat(joins): a read-time join can be declared in the unified file
> **일자:** 2026-09-15 23:55
> **레인:** 구현자(서버) — 착지 → 보고 `df029983`(«앞선 보고 하나를 정정» 포함) → 총괄 닫힘 `0363b091`(「재기동 PID 49960」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **8** · 가상 조인·로더·실행기·회수 모집단 **92 passed** · `--collect-only` **6,784** 에러 0 (구현자 보고). 총괄 확인 「가상 조인·census·문법 모집단 **928 passed** · 부팅 오류 0 · 체인 19」.

## ① 왜 — 이 저장소의 그 부류, 그리고 그보다 «나쁜» 것

`rule_shape.from_join_rule` 은 가상 조인을 `into: {read: true}` 내부 모양으로 «번역해 들여왔다». 그러나 그 모양을 다시 «세우는» 쪽이 아무도 없었다 — 문법에 칸은 있고 읽는 쪽이 없는, 이 저장소의 반복 결함. 읽기 조인은 `virtual_join_rules.json` 에서만 살 수 있었다.

⛔ 실측하니 «조용한 것보다 나빴다»: `chain_rules.json` 에 적힌 그런 선언은 `expand_declaration` 에서 «맵퍼 칸 없는 규칙»으로 나왔고, 로더가 `unresolvable_mapper` 로 떨어뜨렸다 — **옳은 선언을 운영자에게 오타라고 보고**하고 있었다. 그래서 라운드는 지시의 «한 층»이 아니라 «두 반쪽»이 됐다(게이트 ②가 요구했다).

## ② 변경 — 같은 목록, 같은 검증기

```python
# server/chain/rule_shape.py — expand_declaration
if ((internal.get("derive") or {}).get("kind") == "join"
        and (internal.get("into") or {}).get("read")):
    return ([], None, ["%s: into.read — a READ-TIME join. It stands beside the ones declared in virtual_join_rules.json, not as a chain rule." % name])
    #        ^ 규칙 0  ^ 거절 아님  ^ 메모
```
```python
# server/virtual_join/config.py — load_virtual_join_rules
rules = validate_virtual_join_rules(raw_config, known_tables=known_tables, rejections=rejections)
if path is None:                                   # ⛔ `path` 를 준 호출자는 «부분 목록»을 «일부러» 읽는다 — 통합 몫을 안 준다
    rules.extend(_read_time_joins_from_unified({rule["name"] for rule in rules}, known_tables, rejections))
return rules

def _read_time_joins_from_unified(taken, known_tables, rejections):
    for raw in ingestion_worker.read_rules_document()["rules"] or ():
        internal = rule_shape.from_declaration(raw)
        if (internal.get("derive") or {}).get("kind") != "join" or not (internal.get("into") or {}).get("read"): continue
        if rule_shape.is_switched_off(internal): continue           # ⛔ OFF IS OFF (판정 399 ③′) — 검증도 셈도 불평도 없음
        if name in taken:                                            # 🔴 ONE NAME, ONE JOIN — 이름 대고 «한 번» 거절
            _record(rejections, "rule", name, "declared in both virtual_join_rules.json and chain_rules.json - one name is one join. ...", code=CODE_SHAPE); continue
        normalized, err, code, facts = _validate_join(name, rule_shape.as_join_rule(internal), known_tables, rejections=rejections)
        ...
        normalized["origin"] = "decl"
```
통합 선언은 옛 파일이 만드는 «같은 목록»에 «같은 `_validate_join`» 을 지나 합류한다 — 같은 검증 · 같은 이름공간 · 같은 유일 인덱스 요구(S-235) · 같은 회수(S-248). 둘째 검증기는 「이 조인이 돌 수 있나」에 대한 «둘째 답»이고, 통합 문법의 요점은 «어디에 적었나가 뜻을 안 바꾸는 것»이다. 게이트 ①은 두 파일에서 온 조인을 이름 빼고 «칸 단위로 같다»고 단언한다.

## ③ 부재가 더는 «질문의 끝»이 아니다

종전 로더는 `virtual_join_rules.json` 이 «없으면» 그 자리에서 `[]` 를 돌려줬다. 통합 파일에만 조인을 적은 설치는 «아무것도» 못 받았을 것이다. 이제 파일 부재는 «빈 원문»이고 통합 몫은 그 뒤에 온다.

## ④ ⚠️ 구현자가 «자기 앞선 보고»를 정정했다 — 「카탈로그는 제품이 부르는 길로 든다」를 또 어겼다

16:0x 보고에 「`virtual_join_rules.json` rule 항목 «0»(전부 은퇴 주석)」이라 적었는데 **틀렸다.** 그 파일은 선언이 «최상위 키»이고 `rules` 배열이 아니다 — `raw.get("rules")` 로 읽어 `None` 을 「0 건」으로 옮겼다. 제품의 길(`load_virtual_join_rules`)로 다시 재니 이 박스에 가상 조인 «둘»(dt_log→dt_inventory · dt_inventory→dt_job_attribution, 둘 다 읽기 시점, 오른쪽 키 dt_job). 그래서 「이 박스엔 가상 조인이 없다」는 «거짓»이었다. 좁혀서 참인 것: `chain_rules.json` 의 «통합 join 0» 은 제품 리더로 잰 것이라 맞고, 따라서 S-240 의 `key.unique` 부팅 줄은 이 박스에서 «뜰 수 없다». S-245 의 키 식은 그 조인 둘이 «실제로 지나지만» 키가 `string` 이라 캐스트가 «안 붙는» 쪽이다.

📌 같은 함정이 09-09 에 한 번(「날것 json.load 로 S-85 를 지어냈다」) 있었고, 이번엔 같은 레인이 «자기 손으로» 잡아 정정했다.

## ⑤ 운영자 쪽 — `RUN.md` §5-bis 에 예 한 덩이

`into` 가 «택1»: `table` 이면 «쓰는» 조인, `read: true` 면 «읽을 때 답하는» 조인. 같은 이름을 두 파일에 적으면 거절(그 이름을 댄다) · 이 선언은 «체인 규칙이 아니라» 부팅 줄 `[ChainRules] set(N)` 에 «안 뜬다» · 기존 파일은 옮길 필요 없음(소유자 「가상 조인은 그대로 두고」).

## ⑥ 아키텍처 영향

- 통합 문법의 `into` 축이 «둘 다 읽힌다»: `table`(쓰기, S-242 계열) · `read`(읽기, 이 커밋).
- 가상 조인 목록의 «저자»는 여전히 `load_virtual_join_rules` «하나»이고, 입력 «둘»(옛 파일 · 통합 파일)을 받는다.
- 체인 로더는 읽기 조인에 «규칙을 세우지 않는다» — 그것이 «메모»이지 «거절»이 아니라는 구별이 코드에 생겼다.
- 그대로인 것: 실행기 · 거절 어휘 · `unique_key` · `join_into` · `virtual_join_rules.json` 의 읽기 방식.

## ⑦ 그때 남아 있던 것

- **폼은 아직 `into.read` 를 그릴 수 없었다** — 스켈레톤이 평면 키에서만 생성되고 있었다(S-241, 다음 서버 커밋).
- 통합 몫은 `path is None` 일 때만 붙는다 — `path` 를 넘기는 호출자(보고서·시험)가 «두 파일의 합»을 보려면 길이 없었다. 그것은 이 커밋이 «고른» 쪽이다(S-248 의 부분 목록 거부와 같은 이유).
- 이름 충돌은 «통합 쪽이 무시되고» 옛 파일 쪽이 선다 — 어느 쪽을 «믿을지»는 이 커밋이 정했고(옛 파일), 사용자가 고를 자리는 없었다.
- S-241 · S-234 «미착지». 구현자 채널의 미답 «하나»: PG 실행 시험.

---
📎 이 항목의 수(8 · 92 · 6,784 · 928 · 19 · 조인 «둘»)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다 — ③의 「설치」는 코드에서 나오는 구조 주장이다.
📎 쓰기 조인의 소급(S-242): `20260915_130844_a_declared_join_can_be_backfilled_and_a_bad_page_costs_one_page.md` · «맞는 선언을 오타라고» 의 형제(S-243, 부재는 층을 만들지 않는다): `20260915_162502_absence_makes_no_layer_only_a_deliberate_blank_does.md` · 판정 399 ③′(꺼진 것은 꺼진 것).
