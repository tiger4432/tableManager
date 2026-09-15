# 그리드의 «다시 돌리기» 목록은 파일 원문이 아니라 «실제로 도는 집합»이다 — 이 표를 트리거로, 조인 포함, 참조 쪽 제외

> **커밋:** `df824a9a` — feat(replay): the grid's replay list is the set that actually runs, filtered by trigger (S-250, 서버 절반 · 클라 절반은 C-109)
> **일자:** 2026-09-15 16:55
> **레인:** 구현자(서버) — 소유자 16:5x → 지시 `d65a32b2` → 착지 → 보고 `4c49781c` → 총괄 닫힘 `befc370b`(「재기동 PID 36636」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **15**(그중 **넷**은 라우트를 «실제로 불러서») · 변이 **7 «전부» 빨강** · 소급·로더·문법·어드민 인증 모집단 **328 passed** · `--collect-only` **6,755** 에러 0 (구현자 보고). 총괄 확인 「replay 모집단 246 passed · 토큰 게이트 401 실측 · 박스 in-process 로 dt_log/dt_inventory 목록 나옴」.

## ① 왜 — 소유자 「같은 체인문이면 보여야지」

> 「그리드 상단 리플레이 버튼에 조인도 달아줘. 같은 체인문이면 보여야지. 누를 시 목록은 해당 테이블이 트리거인 체인 규칙만」

배너는 `GET /admin/chain/rules` = `chain_rules.json` «원문»을 읽고 있었다. 원문이라 구멍이 «셋 동시»였다:
```
① 통합 join 이 «안 보였다»      원문은 `on.table` 을 쓰지 `trigger_table` 이 없다
② 합성 규칙이 «아예 없었다»      enrichment · 가상 조인은 로더가 세운다 — 그 파일에 있던 적이 없다
③ 표로 «거를 수 없었다»          어느 표의 규칙인지 원문은 모른다
```
🔴 **도는 집합이 아닌 목록은, 소급이 거절할 이름을 내미는 목록이다.** 운영자는 그것을 «누른 뒤에» 안다.

## ② 변경 — 저자 하나, 그리고 그것은 소급이 «이미 쓰는» 저자다

```python
# server/chain/replay.py
def replayable_rules_for(table: str) -> list:
    from chain import rule_shape
    wanted = str(table or "")
    out = []
    for rule in load_rules():                   # 로더의 «출력» — 번역·합성 포함, enabled 만(상류가 이미 결정)
        if str(rule.get("trigger_table") or "") != wanted:
            continue
        if is_reference_side(rule):             # ⛔ find_rule 이 거절에 쓰는 «그 판별식»(S-242) — 둘째 철자면 목록과 실행이 갈린다
            continue
        out.append({"name": rule.get("name"), "trigger_table": rule.get("trigger_table"),
                    "target_table": rule.get("target_table"), "kind": rule_shape.declared_kind(rule)})
    out.sort(key=lambda entry: str(entry["name"] or ""))
    return out
```
```python
# server/main.py
@app.get("/admin/chain/rules/replayable", dependencies=[Depends(require_admin_token)])
def get_replayable_chain_rules(table: str):           # 표를 안 주면 422 — 「전부」로 «떨어지지 않는다»
    wanted = str(table or "").strip()
    if wanted not in crud.TABLE_CONFIG:                # ⚠️ 모르는 표는 «빈 목록»이 아니라 «거절» — 「규칙이 없다」와 「그런 표가 없다」는 다른 사실
        raise HTTPException(status_code=404, detail="표 '%s' 가 카탈로그에 없습니다 — ... table_config.json 에 등록된 이름인지 확인하십시오" % wanted)
    return {"status": "success", "data": replay.replayable_rules_for(wanted)}
```

## ③ `kind` 는 «선언의 낱말»이다 — 배관의 낱말이 아니다

```python
# server/chain/rule_shape.py
DECLARED_KINDS = ("join", "decide", "mapper")

def declared_kind(rule: dict) -> str:
    mapper = rule.get("mapper")
    if mapper in (join_into.JOIN_INTO_MAPPER, vjc.JOIN_MAPPER):
        return "join"
    name = str(rule.get("name") or "")
    if (mapper == enrichment_config.AUTO_CONFIRM_MAPPER
            or name.startswith(enrichment_config.DEDUP_PREFIX)
            or name.startswith(enrichment_config.AUTO_CONFIRM_PREFIX)):
        return "decide"                          # ⚠️ decide 선언의 «두 반쪽» 다 decide — 한 선언에서 나왔고 운영자가 반쪽을 «고른 적 없다»
    return "mapper"
```
`builtin:join_into` 나 `enrichment_dedup:` 를 내미는 목록은 규칙을 «고르려고 우리 내부를 알아야» 하는 화면이다 — COLLECT 드롭다운의 결함(2026-08-27 「사용자가 claim, point, collection 이런 걸 어케 암」)과 같은 부류.

⚠️ `builtins.synthesized_kind_counts` 와 «접지 않았다» — 그쪽은 「제품이 무엇을 몇 개 합성했나」(부팅 줄), 이쪽은 「이 규칙 뒤의 선언이 자기를 뭐라 하나」. 같은 접두, 다른 주어. 나중에 접으면 한 답이 두 물음을 섬긴다 — 주석에 적어 두었다.

## ④ 시험의 한 판정 — 라우트는 «불러서» 잰다

넷은 TestClient 로 `GET /admin/chain/rules/replayable?table=` 을 «실제로 불러» 잰다(걸러진 답 · 모르는 표 404 에 표 이름과 `table_config` · 표 없음 422 · 옆의 원문 라우트 무변). 📌 「시그니처 단언은 «못 부르는 라우트»에도 참이다」(2026-09-13) 그대로.

## ⑤ 아키텍처 영향

- 「다시 돌릴 수 있는 규칙」의 집합에 저자가 «하나» 생겼고, 그 저자가 소급(`find_rule`)과 «같은 함수»를 지난다. 목록과 실행이 갈릴 «수 없다».
- 규칙의 «종류 낱말»(join · decide · mapper)이 서버 상수 `DECLARED_KINDS` 로 섰다 — 화면이 그리는 낱말의 출처.
- §0-ter: 읽기 라우트지만 «로더가 이미 읽은 것»을 되돌려 줄 뿐 새 SQL **0**.
- 그대로인 것: `/admin/chain/rules`(chain 탭은 «원문»을 편집해야 한다) · `load_rules` / `find_rule` / `is_reference_side` · 소급 라우트.

## ⑥ 그때 남아 있던 것

- **배너는 «안 건드렸다»** — 목록을 «묻고 그리는» 것은 C-109 이고 이 시점에 미착지(클라 레인은 09-13 정지 지시 중이라 소유자 창 두드림이 필요했다).
- 이 라우트는 «이 프로세스가 적재한 것»을 답한다. 마지막 리로드 뒤 파일에 추가된 규칙은 목록에 없다 — 다른 적재-규칙 답들과 «같은 창».
- 총괄이 화면에서 본 것은 없다 — 「박스 in-process 로 목록 나옴」은 함수 호출이지 배너가 아니다.
- 구현자의 앞선 물음(PG 실행 시험)은 그대로 열려 있었다.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 클라 절반: `20260915_170746_the_grids_replay_list_belongs_to_the_table_and_the_loader_left_main_js.md` · `is_reference_side` 가 태어난 자리(S-242): `20260915_130844_a_declared_join_can_be_backfilled_and_a_bad_page_costs_one_page.md` · 배관 낱말을 사용자에게 내밀던 앞선 판: `20260827` 계열(COLLECT 드롭다운, CLAUDE.md 「술어가 아닌 것은 표면적으로 노드」 절).
