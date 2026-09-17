"""로드된 «규칙 집합»의 사진과 그 사진 둘의 «차이» — 통합 라운드의 안전망 (S-234 0단계).

🔴 왜 이것이 기능보다 «먼저» 지어지나. 2026-09-14 운영 장애 넷은 전부 「어제까지 관대하던 것이
오늘 엄해졌고, 그 엄함이 «이미 돌던 것»을 무효로 만들었다」였다. 그중 하나는 모르는 칸 하나로
운영자의 선언이 «삭제»됐고, 부팅 로그는 개수만 찍어 사라진 줄 아무도 몰랐다. 그날 없던 것은
기능이 아니라 **「바꾸기 전과 바꾼 뒤가 같은가」를 묻는 자리**였다.

[무엇인가] 규칙 목록 하나를 «비교 가능한 사진»으로 접는다. 그것뿐이다 — 판정하지 않고,
고치지 않고, 제품 경로를 한 줄도 지나지 않는다.

[왜 이 칸들인가] 사진에 담는 것은 «운영자가 잃으면 아는 것»이다:
    name          사라졌는지
    enabled       꺼졌는지
    trigger/target  어느 표에서 어느 표로 — 배선이 바뀌었는지
    trigger_columns 컬럼 트리거의 폭 (S-140)
    derive        값을 어떻게 얻는가 (mapper · join · decide) — 통합의 «축»
    origin        운영자가 «쓴» 것인가, 제품이 «만든» 것인가 (선언 파일 밖에서 온 규칙)
    position      순서 (S-156 이 유도하는 것)
⛔ 담지 않는 것: 맵퍼 «인자»와 임의의 칸. 그것들이 바뀌는 것은 정상이고, 사진을 시끄럽게 만들면
   아무도 안 본다 — 그러면 이 파일은 있으나 마나다.
"""
from __future__ import annotations


#: 사진 한 장의 칸. 바뀌면 그것이 «보고할 차이»다.
CENSUS_FIELDS = ("name", "enabled", "tables", "trigger_columns", "derive", "origin")


def table_keys():
    """표를 이름 대는 칸의 «유일한 저자»에게 묻는다 (`chain_bindings.RULE_TABLE_KEYS`).

    🔴 여기 «글자로» 적지 않는 이유가 실물로 드러났다. 처음 이 파일은 `trigger_table` 과
    `target_table` «둘»만 찍었는데, 저자가 든 목록은 «일곱»이다 — `source_table` ·
    `map_table` · `inventory_table` · `metadata_target_table` · `derivation_source_table`.
    그 다섯 중 하나로 배선이 바뀌면 사진이 그것을 «못 본다». 두 번째 목록은 새 키가
    생긴 날 한쪽만 모른다는 그 규칙이 정확히 이 결함을 잡았다(전 스위트가 잡음).
    """
    import chain_bindings
    return tuple(chain_bindings.RULE_TABLE_KEYS)


def derive_kind(rule: dict) -> str:
    """이 규칙이 값을 «어떻게» 얻는가 — join / decide / mapper.

    ⚰️ [판정 501 ⓒ] THIS WAS A HAND-WRITTEN CASCADE AND IT HAD GONE WRONG WHERE NOBODY
    LOOKS. It read `derive` / `right_table` / `decision_key` off the rule - TOP-LEVEL cells
    that `expand_declaration` does NOT leave on a loaded rule - so every loaded rule answered
    「mapper」, including every synthesised join and auto-confirm. That word goes straight into
    the boot line `[ChainRules] set(N): 이름[출처,방식]`, which RUN.md tells the operator to
    read: they declared a join, restarted, searched the boot log for `join`, and found none -
    while the retroactive banner called the same rule `kind: "join"`.

    🔴 ONE AUTHOR NOW. `rule_run.rule_label` answers from what the kinds REGISTERED, which
    is where 판정 498 ④ put this judgement; a second cascade here is the same defect that
    ruling closed, wearing the census's clothes.
    """
    if not isinstance(rule, dict):
        return "unknown"
    if not (rule.get("mapper") or rule.get("mapper_module")
            or rule.get("mapper_function")):
        # ⚠️ 「NAMES NO CODE」 IS NOT A LABEL, IT IS A GAP. The seat answers 「mapper」 for any
        #    name it does not know, which is right when a rule HAS a name; a rule with no name
        #    at all is a different fact and the census is the one place that says so.
        return "unknown"

    from chain import rule_run

    return rule_run.rule_label(rule)


def rule_row(rule: dict, position: int, origin: str = "declared") -> dict:
    """규칙 하나의 사진. `position` 은 «로드된 순서»이고 그것이 S-156 이 정한 순서다."""
    rule = rule if isinstance(rule, dict) else {}
    columns = rule.get("trigger_columns")
    return {
        "name": rule.get("name"),
        "enabled": bool(rule.get("enabled", True)),
        # 선언이 «든» 표 칸만. 없는 칸을 None 으로 채우면 「배선이 생겼다」와 구별이 안 된다
        "tables": {key: rule[key] for key in table_keys() if key in rule},
        # 정렬해 담는다 — 선언이 적은 «순서»는 이 축의 사실이 아니다
        "trigger_columns": sorted(str(c) for c in columns) if columns else None,
        "derive": derive_kind(rule),
        "origin": origin,
        "position": position,
    }


def census(rules, origins=None) -> list:
    """규칙 목록 -> 사진 목록. `origins` 는 {이름: 'declared'|'synthesized'}."""
    origins = origins or {}
    out = []
    for position, rule in enumerate(rules or []):
        name = rule.get("name") if isinstance(rule, dict) else None
        out.append(rule_row(rule, position, origins.get(name, "declared")))
    return out


def census_diff(before, after) -> dict:
    """두 사진의 차이 — «이름»으로 짝짓는다.

    🔴 위치가 아니라 이름으로 짝짓는 이유: 규칙 하나가 사라지면 그 뒤 전부가 한 칸씩 밀려
    「전부 바뀌었다」로 보인다. 그러면 진짜 사라진 하나가 소음에 묻힌다 — 2026-09-14 에
    부팅 로그가 개수만 찍어 여덟 중 무엇이 사라졌는지 못 보던 것과 같은 병이다.

    순서 변화는 «따로» 보고한다(`reordered`): 순서가 바뀐 것은 결함일 수도 S-156 의 정상
    동작일 수도 있어, 사라짐·꺼짐과 같은 칸에 두면 읽는 사람이 가를 수 없다.
    """
    before_by = {row["name"]: row for row in before or []}
    after_by = {row["name"]: row for row in after or []}

    removed = sorted(name for name in before_by if name not in after_by)
    added = sorted(name for name in after_by if name not in before_by)

    changed = []
    for name in sorted(set(before_by) & set(after_by)):
        was, now = before_by[name], after_by[name]
        fields = {field: {"before": was.get(field), "after": now.get(field)}
                  for field in CENSUS_FIELDS
                  if field != "name" and was.get(field) != now.get(field)}
        if fields:
            changed.append({"name": name, "fields": fields})

    reordered = [
        {"name": name,
         "before": before_by[name]["position"], "after": after_by[name]["position"]}
        for name in sorted(set(before_by) & set(after_by))
        if before_by[name]["position"] != after_by[name]["position"]]

    return {"removed": removed, "added": added,
            "changed": changed, "reordered": reordered,
            "same": not (removed or added or changed)}


def describe(diff: dict) -> str:
    """운영자·총괄이 읽는 한 문단. 「같음」이면 그렇게 말한다 — 침묵은 답이 아니다."""
    if diff.get("same") and not diff.get("reordered"):
        return "규칙 집합 동일 — 사라짐 0 · 새로 생김 0 · 바뀜 0 · 순서 변화 0"
    parts = []
    if diff.get("removed"):
        parts.append("🔴 사라짐 %d: %s" % (len(diff["removed"]), ", ".join(diff["removed"])))
    if diff.get("added"):
        parts.append("새로 생김 %d: %s" % (len(diff["added"]), ", ".join(diff["added"])))
    for entry in diff.get("changed") or []:
        parts.append("바뀜 %s — %s" % (
            entry["name"],
            " · ".join("%s %r→%r" % (field, value["before"], value["after"])
                       for field, value in sorted(entry["fields"].items()))))
    if diff.get("reordered"):
        parts.append("순서 변화 %d" % len(diff["reordered"]))
    return " | ".join(parts)
