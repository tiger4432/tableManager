# 저장 관문이 «로더가 세울 것»을 판정한다 — 판정자는 하나였는데 «먹는 것»이 달랐다

> **커밋:** `00da7e91` — fix(admin): the save gate judges what the loader would stand, not the raw entry (S-244)
> **일자:** 2026-09-15 11:32
> **레인:** 구현자(서버) — 지시 `5d3726d4` → 착지 → 보고 `2fc38974`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **10** · 변이 넷 «전부» 빨강(원문 재판정 5 · 반쪽 해결기 5 · 평면 규칙도 번역 7 · OFF 를 거절로 1) · 저장 관문·`rule_refusals`·`rule_shape`·로더·raw 라우트·고리 검증기 모집단 **344 passed** · `--collect-only` **6,626** 에러 0 (구현자 보고).

## ① 왜 — S-204 의 문장이 «판정자»에 대해선 참이고 «입력»에 대해선 거짓이 돼 있었다

소유자 「지금 조인 해봤는데 안 도는데」(11:3x)의 원인 «후보»로 총괄이 잡은 것이다.
```
저장 관문   save_chain_rule_raw -> rule_refusals(«원문 entry», mapper_resolvable=MAPPER_REGISTRY.get)
로더        load_chain_rules   -> «먼저 번역»(from_declaration …) -> 판정
통합 선언   name·on·derive·into 뿐 -> 원문엔 trigger_table 없음 · derive/on/into 는 모르는 칸 · mapper 없음
=> 같은 파일에서 로더가 «받는» 선언을 저장 버튼이 «세 문장으로» 거절했다
```
🔴 「같은 기능에 두 경로」의 «한 층 아래» 판이다 — 판정자를 하나로 모아도 «입력»이 갈리면 둘이다.
⚠️ 소유자는 파일로 직접 적어 이 문을 «안 지났다»(보드 `2f4abb4e`) — 즉 「안 도는데」의 «실제» 원인이 이것이었다는 근거는 없다. 후보였고, 결함은 결함이었다.

## ② 변경 — 확장기 «하나», 부르는 곳 «둘»

```python
# server/chain/rule_shape.py — 새 저자
def expand_declaration(declaration, table_config=None) -> tuple:
    """(세울 규칙들, 거절, 노트)"""
    if not isinstance(declaration, dict) or not isinstance(declaration.get("derive"), dict):
        return ([declaration], None, [])          # <- 옛 평면 규칙은 «그 객체 그대로»
    internal = from_declaration(declaration)
    if is_switched_off(internal):
        return ([], None, ["%s: enabled=false — no rule stands for it." % name])   # <- OFF 는 «거절이 아니다»
    decided, decide_refusal = decide_rules(internal, table_config)
    ...
    return ([as_chain_rule(internal)] + companion_rules(internal), None, notes)
```
```python
# server/chain/ingestion_worker.py  load_chain_rules() — 번역 블록 «전체»가 이 호출이 됐다
stood, refusal, notes = rule_shape.expand_declaration(rule, _catalogue.TABLE_CONFIG)
...
translated.extend(stood)
```
```python
# server/ledger/admin.py  save_chain_rule_raw()
stood, expand_refusal, _notes = rule_shape.expand_declaration(entry, _catalogue.TABLE_CONFIG)
for candidate in stood:
    grammar = chain_bindings.rule_refusals(
        candidate, f"rules.{name}",
        mapper_resolvable=ingestion_worker._resolvable_mapper,     # <- builtin: 종류를 «아는» 해결기
        mapper_params=mapper_sdk.MAPPER_PARAMS.get)
```
🔴 **해결기도 반쪽이었다.** `MAPPER_REGISTRY.get` 은 `builtin:` 종류를 모른다 — 번역된 규칙이 `builtin:join_into` 를 대면 저장 버튼은 거절하고 부팅은 돌렸다. 「돌 수 있나」에 한 제품이 답 둘.
🔵 고리 검증(`_validate_chain_cascade_graph`)도 «확장된 집합»에 묻게 됐다 — 고리는 «돌 규칙»의 사실이고 통합 선언은 펴지기 전엔 그 규칙이 아니다.

## ③ 판정 둘이 코드에 «자세»로 남았다

```
저장되는 것은 «운영자의 글»   판정받는 것은 번역본, 파일엔 적은 그대로.
                            확장본을 되쓰면 «안 적은 규칙 둘»이 «고르지 않은 문법»으로 파일에 앉고
                            다음 편집은 «제품의 산문»을 고치는 일이 된다
옛 평면 경로는 바이트 무변    derive 없음 -> 번역 없음 -> 확장기가 entry «그 객체»를 돌려준다(`stood[0] is flat` — 동일성 단언)
```

## ④ 시험 하나는 «변이가 부재를 찾아서» 생겼다

「OFF」와 「WRONG」을 가르는 증인이 없었다 — 꺼진 선언의 결과를 «거절»로 바꿔도 전부 초록이었다. 그런데 이 라우트는 «처음 보는 이름»에 `enabled: false` 를 찍는다(「armed but not firing」). 그랬다면 **통합 선언의 첫 저장이 전부 거절**됐을 것이다. 그 케이스가 지금 `test_a_new_declaration_saves_armed_but_not_firing` 이다.
📌 부류: 판정 399(「OFF 는 «아무 일도 없음»이지 거절이 아니다」)의 «저장 관문» 판. 같은 판정이 문 «둘»에서 같은 모양이어야 한다는 것을 변이가 짚었다.

## ⑤ 그때 남아 있던 것

- 첫 실행 «없음». 재기동은 총괄 몫이었고, 이 커밋 뒤 첫 재기동은 S-248 의 PID 22964(보드 12:0x)다.
- 이 채널의 미답 질문이 «하나» 열려 있었다 — S-242 ②의 격리 범위(판정 403 이 12:5x 에 닫는다, 별 항목).
- 「안 도는데」의 나머지 후보 — builtin 종류가 활동 등록부를 «안 지난다»(S-246, 대기열에 안 뜨고 돈다) — 는 그대로 큐에 있었다.
- `derive.decide` 의 모르는 칸은 «노트»로 이름만 대고 규칙은 돈다(판정 397 자세) — 옛 껍데기(`virtual_join/config.py`)의 허용 목록 부재(S-238)는 그대로.

---
📎 수는 전부 구현자 보고의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 판정 399·400·401 과 `is_switched_off`: `20260915_103121_enrich_became_a_decide_kind_through_one_expander_with_two_front_doors.md`.
