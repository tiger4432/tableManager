# 세 규칙 파일은 «이름공간 하나»다 — 겹친 이름은 둘 다 안 서고 한 줄로 파일을 대며, 파생 규칙 스위치는 은퇴했고, `rule_order` 가 둘째 사본을 «말없이» 떨어뜨리고 있었다 (S-234, 판정 408·409)

> **커밋:** `5c845e67` — feat(chain): three rule files are one namespace, one off switch, one boot line (S-234, rulings 408/409) → main 병합 `8fb41a11`
> **일자:** 2026-09-16 01:49
> **레인:** «워크트리 서브에이전트»(구현자 대행) — 구현자는 00:52 이후 침묵(초인종 둘, S-241-b 도 총괄이 착지) → 야간 목표대로 총괄이 워크트리 에이전트에 S-234 를 맡김 → 착지 → 총괄 닫힘 `82d46ebc`(「재기동 PID 52312」) · 구현자 채널에 「깨어나면 이 커밋을 검수」로 적힘
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 `test_three_files_declare_one_chain_namespace.py` **5**(깨끗한 셋 · 두 파일 겹침 · 조인 겹침 · 한 파일 안 두 번 · 스위치 드리프트 오라클) · 은퇴한 시험 «넷»(`enrichment_name_collisions` 둘 · `join_name_collisions` 하나 — 그 자리에 `written_in` 시험 하나 · `synthesized_kind_counts` 하나) + 판정 399 ㉡ 시험 하나 · 커밋 게이트 「세 파일 선언 셋의 census 바이트 동일, 로그 차이는 접힌 줄 하나」(커밋 본문). 총괄 확인 「main 310 passed(test_api 포함) · 부팅 set(19) 한 줄 · 『Synthesized』 줄 없음 · `ASSY_CHAIN_SYNTHESIZE` 참조 0」.

## ① 왜 — 검사기가 «파일마다» 있다는 것이 이름공간이 «파일마다» 있다는 증거였다

`chain_rules.json`(평면·통합) · `enrichment_rules.json` · `virtual_join_rules.json` 은 체인 규칙을 «적는 세 가지 방법»이고 셋 다 «같은 적재 집합»으로 끝난다. 그런데 겹침 검사가 `enrichment_name_collisions` · `join_name_collisions` «둘»이었고, 둘 다 「chain_rules.json 이 선언한 이름을 합성 규칙이 «또» 내면 합성 쪽을 떨어뜨린다」였다 — 「어느 쪽이 참인지 제품이 못 고른다」고 적어 놓고 «한쪽을 골라» 살리고 있었다. 그리고 `ASSY_CHAIN_SYNTHESIZE` 는 「운영자가 못 보는 파생 규칙」을 끄는 스위치였는데, 부팅 set 줄이 «모든» 규칙을 origin 과 함께 이름으로 보여 주게 된 뒤로 그 스위치의 «주어»가 사라져 있었다(판정 408). 두 스위치가 한 물건을 끄면 하나는 잊힌다.

## ② 변경 — 판정은 «집합을 보는 자리» 하나에서, 합성 «뒤» · `rule_order` «앞»

```python
# server/chain/ingestion_worker.py — load_chain_rules
written_in = [os.path.basename(RULES_PATH)] * len(rules)          # chain_rules.json 은 «자리»로 태그
...
synthesized = [r for r in builtins.synthesize_chain_rules(known_tables=crud.TABLE_CONFIG)
               if r.get("enabled", True)]                          # 스위치 없음 · 겹침 필터 없음
if synthesized:
    rules = rules + synthesized
    written_in += [builtins.written_in(r) for r in synthesized]   # 합성분은 «어느 파일에서 왔나»를 셀 하나로
...
rules, twice = _refuse_names_claimed_twice(rules, written_in)     # 집합의 판정자 «하나»
if twice:
    for name, files in twice:
        logger.error(operator_line.line("ChainRules", name,
            "같은 규칙 이름이 %d 번 선언돼 있습니다 (%s) — 어느 쪽도 돌지 않습니다" % (len(files), " · ".join(sorted(set(files)))),
            operator_line.rename_one_declaration(files)))
        refused_here.append((name, "name_claimed_twice"))
```
```python
# server/chain/builtins.py — synthesized_kind_counts 자리에
def written_in(rule) -> str:
    if (rule or {}).get("mapper") == virtual_join.config.JOIN_MAPPER:
        return os.path.basename(virtual_join.config.VIRTUAL_JOIN_RULES_PATH)
    return os.path.basename(enrichment.config.ENRICHMENT_RULES_PATH)
# server/operator_line.py — 행동 어휘 하나
def rename_one_declaration(files) -> str:
    distinct = sorted(set(str(item) for item in (files or ())))
    if len(distinct) > 1: return "두 파일 중 하나에서 이름을 바꾸십시오"
    return "%s 에서 한쪽 선언의 이름을 바꾸십시오" % (_names(distinct) or "그 파일")
```
«둘 다» 안 선다 — 살리는 쪽을 고르는 것이 곧 「해소」이고, 옛 검사기의 「합성 절반을 떨어뜨림」이 정확히 그것이었다. 「Synthesized N (a dedup · b auto-confirm · c join)」 부팅 줄은 set 줄로 «접혔고», 그래서 `synthesized_kind_counts` 와 그 시험이 같은 커밋에서 죽었다. `RUN.md` §3 의 `ASSY_CHAIN_SYNTHESIZE=0` 줄은 「규칙 «하나»만 끄려면 그 규칙이 적힌 파일에서 `enabled: false`」로 바뀌었다.

## ③ 🔴 부수 발견 — `rule_order` 가 같은 이름의 둘째 사본을 «말없이» 떨어뜨리고 있었다

판정자를 «어디에» 둘지 정하다 나왔다. `rule_order.order_rules` 는 이름을 키로 걷는다. 그래서 `chain_rules.json` «한 파일 안»에 같은 이름이 두 번 있으면 첫 사본만 남고 둘째는 «한 줄도 없이» 사라졌다 — 옛 검사기 둘은 «파일 사이»만 봤으니 이 경우는 아무도 안 봤다. 「같아 보이는 다섯 개의 0」의 한 갈래. 새 판정자가 `rule_order` «앞»에 서는 이유가 이것이고, 넷째 시험(`..._in_one_file_is_refused_rather_than_halved`)이 그 자리를 고정한다: 둘 다 안 서고(`names == []`) 줄이 «그 파일 하나»를 가리킨다.

## ④ 드리프트 오라클이 «자기 docstring» 에 걸렸다

`ASSY_CHAIN_SYNTHESIZE` 가 `server/` 아래 «어디에도» 없음을 `git grep` 으로 잰다 — 텍스트가 «주어»라 잘라쓰기 금지의 예외 모양이다. 시험 파일 docstring 이 적어 둔 사실: 그 이름을 파일에 «그대로» 적어 두자 파일이 추적되는 순간 오라클이 «자기 자신»에 빨개졌다. 그래서 이름을 두 조각(`"ASSY_CHAIN_" + "SYNTHESIZE"`)으로 조립한다. 「추적 파일을 훑는 게이트는 내가 커밋하면 모집단이 바뀐다」(2026-09-07)의 재현이고, 이번엔 커밋 «전»에 잡혔다.

## ⑤ 아키텍처 영향

- 체인 규칙의 이름은 «집합 하나». 겹침 판정 자리가 «하나»(`load_chain_rules`, 합성 뒤·정렬 앞)이고 어휘는 `name_claimed_twice` · `rename_one_declaration`.
- 체인을 끄는 손잡이는 «둘»: 규칙 하나 = 그 파일의 `enabled: false` · 전부 = `ASSY_CHAIN_WORKER=0`. 셋째 스위치는 없다.
- 부팅 줄은 set 줄 «하나». census 의 origin 어휘(`declared|synthesized`)는 그대로(게이트 a 바이트 동일).
- 그대로인 것: 합성 좌석 하나(판정 304) · `declared_kind`(접두어는 같아도 «질문»이 다르다는 docstring 이 갱신됨) · `is_switched_off`.

## ⑥ 그때 남아 있던 것

- **문서 앵커가 낡은 채 남았다** — CODE_MAP · PRIMITIVES · BASIS · CCC 가 `ASSY_CHAIN_SYNTHESIZE` · `synthesized_kind_counts` 를 현행으로 인용(총괄 「아침 정비 패스」). 코드에서 이름이 사라진 «뒤» 문서가 그 이름을 든 상태.
- **구현자가 이 커밋을 «검수하지 않았다»** — 채널에 「깨어나면 `_refuse_names_claimed_twice` 의 자리와 `written_in` 태그를 당신 눈으로」로 적혀 있고, 착지 시점 구현자는 침묵 중.
- `written_in` 은 «합성기에서 나온 규칙»에만 맞는다 — `chain_rules.json` 에 적힌 통합 `decide` 도 `origin: synthesized:` 를 들고 있어, 자리로 태그하지 않으면 파일이 틀리게 적힌다(함수 docstring 이 스스로 적음). 즉 「어느 파일」의 답은 «두 기제»(자리 · 셀)의 합이다.
- 판정 412 로 미룬 `CHAIN_RULE_REGISTRY.oneOf` 은퇴(클라)는 「평면 문법이 은퇴하는 날」에 걸려 있고, 이 커밋은 평면 문법을 «읽는 것»을 그대로 둔다 — S-234 의 이름이 「옛 껍데기 은퇴」였지만 착지한 범위는 이름공간·스위치·부팅 줄 «셋»이다.

---
📎 이 항목의 수(5 · 310 · set(19) · PID 52312)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 앞선 라운드: `20260916_004105_the_skeleton_declares_the_unified_grammar_and_a_branch_node_lives_under_its_key.md`(S-241/-b, 판정 408·409 가 태어난 자리) · 옛 검사기의 자리: S-179 ①(판정 292) · 「같아 보이는 다섯 개의 0」 · 「추적 파일을 훑는 게이트는 내가 커밋하면 모집단이 바뀐다」(2026-09-07).
