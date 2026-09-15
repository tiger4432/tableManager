# enrich 가 통합 선언의 `decide` 종류가 됐다 — 확장기 «하나»에 문 «둘», 그리고 스위치가 자기 주어를 되찾았다

> **커밋:** `dc29056a` — feat(chain): enrich becomes a kind of the unified declaration, through the shell that already existed (S-239 · 판정 399·400·401)
> **일자:** 2026-09-15 10:31
> **레인:** 구현자(서버) — 짓기 «전» 블록 `6cde0a38` → 판정 `4e72ec0b` → 착지 → 보고 `fd7ad068`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **11** · 변이 다섯 부류 «전부» 빨강(OFF 미감지 2 · 부재를 OFF 로 1 · decide 칸 미변환 7 · 정규화기 건너뜀 4 · `auto_confirm_declared` 하드코딩 1) · enrichment·rule_shape·rule_census·load_chain_rules 모집단 **1,158 passed** · `--collect-only` **6,615** 에러 0 (구현자 보고). 총괄 닫힘 확인 「101 · 524 passed · 재기동 PID 2608 · `set(17)` 그대로」(`474f1aa9`).

## ① 왜 — 「실행은 한 줄도 안 바뀐다」가 이 라운드의 «전부»다

enrich 는 «이미» 체인 맵퍼다 — dedup 은 평범한 경로(`map_enrichment_dedup`), auto_confirm 은 follow-up 랩
(`builtin:auto_confirm`). 움직인 것은 «선언을 어디에 적을 수 있나»뿐이다: 옛 enrichment 파일 «또는»
`derive: {kind: "decide"}` 인 통합 선언.

### 짓기 «전»에 §0-ter 판별식 셋을 «답으로 먼저» — 그리고 하나가 «막혔다»
```
① 읽기/쓰기   쓰기. 이 diff 에 읽기 경로 네 파일(virtual_join/executor · column_filter · source_preparation ·
              resolved_expression) «0 줄», SQL 모양의 줄 «0»                                          ✅ 지은 뒤 재섬
② 행/배치     행. 기제는 `_isolated_execute` 의 SAVEPOINT — 이미 `test_enrichment_candidates` 가 채점
              (나쁜 문장 뒤 같은 세션의 SELECT 1 성공). 이 라운드는 실행을 안 바꾸므로 «둘째 사본» 없이 그 파일을 가리킴
③ 스위치      🔴 구현자가 «못 정하고 올렸다» — ASSY_CHAIN_SYNTHESIZE 의 «주어»가 「운영자가 안 적었고 볼 수도 없는
              파생 규칙」이라 통합 선언은 그 스위치 «밖». ㉠ 가두면 보이는 선언에 «둘째 끄는 자리» · ㉡ 안 가두면 게이트 ③ 이 그대로는 불성립
```
🔵 구현자가 「S-237 의 join 종류도 «이미» 같은 성질이고 그때 제가 안 올렸다」를 «같이» 올렸다 — 판정이 두 종류에 «같이» 떨어져야 한다고.

## ② 판정 셋 (`4e72ec0b`)

```
399  ㉡ + ③′.  ASSY_CHAIN_SYNTHESIZE 는 «파생 규칙»의 스위치이고 통합 선언에 «일부러» 안 닿는다(한 줄로 단언).
     통합 선언의 «유일한» 끄는 자리는 enabled:false 이고, 그것은 §0-ter 가 스위치에 요구하는 것을 «그대로» 뜻해야 한다:
     로더가 규칙을 «안 세우고» DB 를 «안 만진다» — 「세웠다가 나중에 거른다」가 아니라.
     S-237 의 join 종류도 «이 커밋에서» 같은 대접 — ③′ 가 생기기 전에 지어졌으므로
400  auto_confirm 은 «칸»이다(derive.decide.auto_confirm, boolean). 껍데기는 «어느 쪽이든 규칙 둘»을 내고
     컬렉터의 .active 가 실행 시점에 정한다 — 지시대로 «불변». 규칙을 «세는» 것은 껍데기의 사실이지 작성자의 문법이 아니다
401  auto_confirm_declared 는 칸이 «아니다». 정규화기가 «키의 존재»에서 이미 유도한다(= `"auto_confirm" in derive.decide`,
     enabled_written 부류). 칸으로 두면 「적었다고 적는 자리」가 생기고 둘이 «어긋날 수» 있다
```
📌 399 의 부류: **「한 이름이 두 뜻」의 «예방»판** — 스위치 «하나»의 주어를 좁혀 둘째 끄는 자리가 «안 생겼다».
   같은 날 아침 `1497ea3e` 가 「OFF 인데 DB 를 만지는 스위치」로 배운 것을, 이 종류는 «태어날 때부터» 받았다.

## ③ 변경 — 확장기를 «하나»로 두고 문을 «둘» 냈다

```python
# server/enrichment/config.py — 루프 «몸»이 함수가 됐다. 본문은 «그대로»
def load_enrichment_chain_rules(path=None, known_tables=None) -> list:
    chain_rules = []
    for rule in load_enrichment_rules(path=path, known_tables=known_tables):
        chain_rules.extend(chain_rules_for(rule))          # <- 옛 문
    return chain_rules

def chain_rules_from_cells(name, enabled_written, enabled, source_table, derived_table, cells, known_tables=None):
    raw = {"source_table": source_table, "derived_table": derived_table}
    raw.update(cells or {})
    if enabled_written:
        raw["enabled"] = enabled
    normalized, why = _validate_rule(name, raw, known_tables)  # <- «같은» 정규화기
    if normalized is None:
        return [], why or "the declaration is disabled"
    return chain_rules_for(normalized), None                   # <- «같은» 확장기. 새 문
```
```python
# server/chain/rule_shape.py
DECIDE_CELLS = ("key", "fields", "list_columns", "aggregations", "reference_views", "auto_confirm", "alignment")
_DECIDE_TO_ENRICHMENT = {"key": "decision_key", "fields": "target_fields"}

def is_switched_off(internal: dict) -> bool:
    return internal.get("enabled_written") and internal.get("enabled") is False   # «적힌 false»만 OFF
```
```python
# server/chain/ingestion_worker.py  load_chain_rules() — 통합 문법 번역 자리
if rule_shape.is_switched_off(internal):
    logger.info("[ChainRules] %s: enabled=false — no rule stands for it.", rule.get("name"))
    continue                                # <- 아래 «아무것도» 안 돈다. 거절로도 «안 센다»
decided, decide_refusal = rule_shape.decide_rules(internal, _catalogue.TABLE_CONFIG)
```
🔴 **「동작 0」의 강한 모양은 «둘을 비교하는 것»이 아니라 «하나를 두 번 부르는 것»이다.** 둘째 확장기는 적는 날
일치하고 어휘에 칸이 하나 느는 날 갈라진다. 게이트의 census 비교가 「공유된다고 «적힌» 것」과 「공유«되는» 것」을 가른다.
🔵 `enabled` 를 «적었나»가 정규화기에 «그대로» 도착한다(`enabled_written` 이면 raw 에 넣고 아니면 안 넣는다) —
   「안 적음」과 「true」가 다른 선언이라는 왕복 계약이 새 문으로도 지켜진다.

## ④ 단언 하나는 «술어»에 걸었다 — 로더로는 못 가르므로

「off」의 두 해석(「«적힌 false»만」 vs 「true 가 아니면」)은 이 파일의 다른 입력 «전부»에 대해 «같은 답»을 낸다.
변이가 그것을 **ESCAPED** 로 잡아 준 뒤, `is_switched_off` 에 «직접» 묻는 시험을 더하고 그 사정을 시험에 적었다.
📌 부류: 변이 채점기가 「게이트가 재지 못하는 것」을 «이름 대어» 준 자리다 — 구멍을 시험 본문에 «말해» 두었다.

## ⑤ 그때 남아 있던 것

- 옛 확장기가 내는 규칙에 `"enrichment": rule` 이 `params` «옆에» 그대로 실린다 — `map_enrichment_dedup` 이 오늘
  `rule["enrichment"]` 을 읽는다. 그 키의 은퇴는 «맵퍼의 라운드»다(코드 주석이 그렇게 적어 둔 채로 착지).
- `derive.decide` 의 «모르는 칸»은 «이름만 대고» 규칙은 돈다(경고). 옛 껍데기(`virtual_join/config.py`)엔 허용 목록이
  여전히 «없다»(S-238).
- ② 판별식의 격리는 «문장» 단위(SAVEPOINT)이고 게이트 문장은 «행» 단위였다. 구현자가 짓기 전 블록에서 「그 단언을
  먼저 써서 돌려 보고 결과를 보고하겠다」고 적었는데, 착지 보고는 「둘째 사본을 안 만들고 그 파일을 가리킨다」로
  닫혔다 — **행 단위 단언의 «결과»는 두 보고 어디에도 없다.** 실행이 안 바뀌었으니 이 커밋의 문제는 아니고, «안 잰 것»으로 남았다.
- 박스에 통합 `decide` 선언이 «없어» 첫 실행은 없다. 재기동은 총괄이 했다(PID 2608, `set(17)` 그대로 — 즉 규칙 수 «무변»).
- S-240 이 큐에 올랐다: 통합 join 의 `key.unique` 를 로더가 읽지 않는다(별 항목 `20260915_100554` §⑤).

---
📎 수는 전부 구현자 보고·총괄 확인에 적힌 것을 옮겼고 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 판정 396~398(join 종류의 칸): `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §④.
