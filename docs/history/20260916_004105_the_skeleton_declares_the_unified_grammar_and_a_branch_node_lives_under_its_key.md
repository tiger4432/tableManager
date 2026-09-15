# 스켈레톤이 «통합 문법»을 낸다 — 어휘에 저자가 생겼고(`oneOf`), 첫 컷은 가지 셋을 «한 층 깊게» 쌌으며, 그 세 줄은 총괄이 착지시켰다 (S-241 · S-241-b, 판정 407·410·411)

> **커밋:** `0dda6f08` — feat(form): the skeleton declares the unified grammar, and the vocabulary gains an author (S-241, 구현자) · `7c81c6d5` — fix(skeleton): a branch node lives under its key - mapper, table and read are leaves (S-241-b, 총괄 착지)
> **일자:** 2026-09-16 00:41 · 01:35
> **레인:** 구현자(서버) — 빈칸 하나를 «짓기 전에» 올림 `6e6cdbdf` → 초인종 `a4433913`/`eb35987d` → 착지 → 보고 `17faee46` → 총괄 닫힘 `603d570c`. 그 뒤 클라 실측 `fedf6a15` → 판정 408~411 `48d8ffa5` → 구현자가 세 줄 + 시험을 쓰고 «40 분 침묵»(미커밋, 초인종 `e3df3b68`) → 총괄이 착지 `7c81c6d5` · 보고 `c83f9c15` → 닫힘 `eea69cbc`(「재기동 PID 41872」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** S-241 신설 **8** · 폼·로더·저장 관문 모집단 **63 passed** · `chain_skeleton.json` 재생성 · `test_chain_skeleton`·`test_ledger_skeleton` 초록 · `--collect-only` **6,792** 에러 0 (구현자 보고). S-241-b: **362 passed**(총괄). 총괄 박스 in-process: 소유자의 통합 규칙 `inventory_confirmed` 의 raw view = `grammar: unified` · derive{join record · decide record · mapper leaf} · into{table leaf · read leaf}.

## ① 왜 — 로더는 읽는데 화면은 «쓸 수 없는» 문법

`chain_bindings.skeleton()` 은 `routing_keys()`(«평면» 키)에서만 생성됐다. 이 제품이 «더한» 통합 문법(`on`/`derive`/`into`)을 로더는 읽는데 폼은 «그릴 수 없었다». 그리고 판정 407: 클라가 잰 어휘는 kind = record|map|leaf, `oneOf` 0 — `hint: choice` 는 «값»을 고르지 «모양»을 고르지 않는다. 「셋 중 하나」를 그리려면 폼이 «손으로» 그려야 하고, 그 순간 화면이 문법의 둘째 저자가 된다. 노드 종류 하나(`oneOf`)가 그것을 닫는다.

## ② 변경 (S-241) — 낱말은 «생성»이지 «적은 것»이 아니다

```python
# server/chain_bindings.py
def _unified_root():
    from chain import join_into, rule_shape
    derive_branches = {
        "join":   _record(*[_field(cell, _leaf(cell)) for cell in join_into.JOIN_CELLS]),
        "decide": _record(*[_field(cell, _leaf(cell)) for cell in rule_shape.DECIDE_CELLS]),
        "mapper": _record(_field("mapper", _leaf("mapper"))),            # <- 첫 컷. ⑤ 에서 leaf 가 된다
    }
    into_branches = {
        "table": _record(_field("table", _leaf("target_table"), required=True)),   # <- 첫 컷
        "read":  _record(_field("read", {"kind": "leaf", "hint": "flag"}, required=True)),
    }
    return _record(
        _field("name", ...), _field("enabled", ...), _field("on", _record(...)),
        _field("derive", {"kind": "oneOf", "hint": "choice", "branches": {k: derive_branches[k] for k in rule_shape.DECLARED_KINDS}}, required=True),
        _field("into",   {"kind": "oneOf", "hint": "choice", "branches": {k: into_branches[k]   for k in rule_shape.INTO_KINDS}},    required=True),
        _field("key",    _record(*[... for cell in rule_shape.KEY_CELLS])),
        _field("limits", _record(*[... for cell in rule_shape._LIMIT_KEYS])),
    )
# skeleton() 은 "root"(평면, 바이트 무변) 옆에 "unified_root" 를 «같이» 낸다
```
```python
# server/chain/rule_shape.py — 새 상수 둘
KEY_CELLS  = ("columns", "unique")
INTO_KINDS = ("table", "read")
# server/ledger/admin.py — chain_rule_raw_view: 규칙이 «어느 문법인지»를 칸으로
out["grammar"] = "unified" if isinstance((named.get(name) or {}).get("derive"), dict) else "flat"
```
가지의 칸은 `DECLARED_KINDS`·`JOIN_CELLS`·`DECIDE_CELLS`·`KEY_CELLS`·`_LIMIT_KEYS` 에서 나온다 — 폼이 칸 이름을 «적는» 날 그것이 둘째 저자이고, 문법이 칸 하나를 얻는 날 «조용히» 갈린다. `grammar` 의 판별은 `derive` 한 칸 — 이 제품이 다른 데서도 쓰는 그 칸이다.

## ③ 🔴 판정 407 이 «한 노드»보다 컸다 — 어휘에 «저자가 없었다»

`test_chain_skeleton` 은 「폼이 그릴 수 있는 종류」를 «원장 스켈레톤을 걸어서» 유도하고 있었다. 즉 「이 종류가 알려진 것인가」의 답이 「누가 이미 썼는가」였다 — 종류를 «쓰기 전엔 더할 수 없고», 마지막 사용처를 지우면 언어가 «조용히 좁아진다».
```python
# server/ledger/config_authoring.py — 검증기 옆에 «적었다»
SKELETON_NODE_KINDS = ("record", "map", "leaf", "oneOf")
```
시험은 이제 kind 를 «그 목록»에 대고 재고, hint 는 «일부러» 그대로 걷는다(이번 라운드가 hint 를 안 더했고 둘을 같이 옮기면 판정보다 커진다). 📌 「판정을 구현으로 색인하면 구현과 함께 죽는다」(08-29)의 «어휘» 판이다.

## ④ 판정 407 의 `list` 칸은 «안 냈다» — 짓기 전에 올렸고, «되돌릴 수 있는 쪽»으로 지었다

그 칸은 닫힌 목록의 «이름»인데 체인 쪽엔 목록을 내주는 자리가 없다(`chain_rule_raw_view` 목록 칸 0 · 저장소의 `closed_lists()` 는 원장 작성 화면 것). 없는 이름을 가리키면 그게 이번 주에 세 번 고친 「폼이 그리는데 읽는 쪽이 없다」(S-240 · S-243 · S-247-b). 그래서 `branches` 의 «키»가 곧 목록이다. 구현자는 이 빈칸을 00:0x 에 «짓기 전에» 올렸고(`6e6cdbdf`), 초인종이 움직임을 요구하자 «`lists` 칸을 나중에 더하는 것은 되지만 내보낸 계약에서 매달린 이름을 빼는 것은 안 된다» 쪽으로 지었다. 판정 410 이 그대로 확정했다.

## ⑤ S-241-b — 첫 컷은 가지 «다섯 중 셋»을 한 층 깊게 쌌다, 클라가 «짓기 전에» 잡았다

클라(C-111)가 서버 JSON 을 «커밋된 선언 픽스처» 옆에 놓고 재니(`fedf6a15`): `derive.join`·`derive.decide` 는 이미 선언 모양인데 `derive.mapper`·`into.table`·`into.read` 는 스켈레톤이 `record(x)` 로 «한 층 더» 싸고 있었다. 그 모양의 폼은 `into: {"table": {"table": "dt_x"}}` 를 요구했을 것이다 — 로더가 받는 선언을 «만들 수 없는 화면», 두-저자 결함이 산문이 아니라 «스키마»로 온 것. 판정 411: 「가지의 노드는 가지 키 «밑»에 산다」.
```python
# server/chain_bindings.py — 세 줄
-        "mapper": _record(_field("mapper", _leaf("mapper"))),
+        "mapper": _leaf("mapper"),
-        "table": _record(_field("table", _leaf("target_table"), required=True)),
-        "read":  _record(_field("read", {"kind": "leaf", "hint": "flag"}, required=True)),
+        "table": _leaf("target_table"),
+        "read":  {"kind": "leaf", "hint": "flag"},
```
```python
# server/tests/test_the_skeleton_declares_the_unified_grammar.py — 다섯 가지 «전부»를 선언 픽스처 모양에 대고
DECLARED_AT_BRANCH = {("derive","join"): {...}, ("derive","decide"): {...},
                      ("derive","mapper"): "mappers.x.y", ("into","table"): "dt_x", ("into","read"): True}
@pytest.mark.parametrize("where,branch", sorted(DECLARED_AT_BRANCH))
def test_a_branch_node_matches_what_a_declaration_puts_there(where, branch): ...   # dict 면 record 이고 키를 덮는다, 아니면 leaf
```
`join`·`decide` 가 맞았던 «이유»가 단서다 — 그 둘의 칸은 «레코드 그 자체»이고, `mapper`·`table`·`read` 는 이름·이름·플래그다.

**누가 착지시켰나:** 구현자가 세 줄과 파라미터 시험을 쓰고 «40 분 침묵»했다(00:52 부터 공유 트리에 미커밋). 초인종 둘(`e3df3b68` · 10 분 감시)에 움직임이 없어 총괄이 착지시켰다 — 구현자 편집 그대로 + 빠진 `import pytest` + 첫 컷의 «감싼 모양»을 기대하던 낡은 단언 «하나» 재작성. 트리에 남은 구현자 편집은 «없다»(전부 커밋).

## ⑥ 아키텍처 영향

- 스켈레톤이 «두 뿌리»를 낸다(`root` 평면 · `unified_root` 통합). 노드 어휘에 `oneOf`(가지 = «모양» 고르기)가 생겼고 그 어휘의 «저자»가 상수 하나로 섰다.
- 규칙 응답이 «자기 문법»을 말한다(`grammar`). 화면이 재유도하지 않는다.
- 통합 문법의 «가지 노드 = 가지 키 밑의 값 모양» 이 시험으로 강제된다 — 선언 픽스처가 그 기준이다.
- 그대로인 것: 평면 뿌리 바이트 · `routing_keys()` · hint 어휘의 유도 방식 · 로더.

## ⑦ 그때 남아 있던 것

- **S-234(평면 껍데기 은퇴) 미착지** — 구현자 침묵 중, 총괄이 «워크트리 서브에이전트»로 짓기로(보드). 판정 408·409(스위치 은퇴 · 겹침은 집합 자리에서 이름 대고 거절 · 검사기 둘 삭제)가 그 지시다.
- 클라 C-111 은 `0dda6f08` 시점의 «첫 컷 모양»으로 짓지 않고 판정 411 규칙으로 «미리» 지었다(01:09) — 그래서 `7c81c6d5` «전»까지 실제 페이지 게이트는 참이 아니었다(폼이 `into`·`derive.mapper` 를 한 층 깊게 그림).
- hint 어휘는 여전히 «걸어서» 유도된다 — 저자가 없는 반쪽이 «일부러» 남아 있다.
- 총괄의 실제 페이지 확인은 «in-process raw view»였다 — 어드민 토큰이 손에 없어 «폼 픽셀»은 하니스 80 으로 갈음(보드 문장 그대로).
- 구현자 채널 미답 «하나»(PG 실행 시험)는 S-256(등급 4)으로 큐에 들어갔다.

---
📎 이 항목의 수(8 · 63 · 6,792 · 362 · 40 분)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 클라 절반(C-111): `20260916_010926_pick_one_is_drawn_from_the_skeleton_and_the_flat_registry_stays_until_the_flat_grammar_retires.md` · 「폼은 그리는데 읽는 쪽이 없다」 이번 주 셋: `20260915_162502_absence_makes_no_layer_only_a_deliberate_blank_does.md`(S-243) · S-240 · S-247-b(`20260915_163019_the_cycle_note_spelled_by_hand_the_shape_it_claimed_to_follow.md`) · 판정을 구현으로 색인한 앞선 사고: `node_class`(CLAUDE.md 문서 원칙 ②).
