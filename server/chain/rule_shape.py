"""세 문법을 담는 «내부 규칙» 하나와, 오늘의 소비자에게 돌려주는 어댑터 둘 (S-234 2단계 ①②).

🔴 아직 «아무도 안 쓴다». 그것이 이 단계의 전부다 — 통합의 위험은 새 모양이 아니라 «소비자를
같이 옮기는 것»에 있고, 2026-09-14 의 사고 넷은 전부 그 부류(한 번에 엄해진 변경)였다.

[계약] `from_* -> as_*` 는 **원본과 같은 dict** 를 돌려준다. 그래야 다음 단계(로더가 내부 객체를
만들고 소비자에게는 어댑터를 통과한 오늘의 dict 를 주는 것)가 «희망»이 아니라 «정의상» 동작 0 이다.

[그래서 `extra` 가 있다] 이 모듈이 «아는» 칸만 모양으로 접고, 나머지는 순서까지 그대로 나른다.
   ⛔ 아는 척하고 버리면 왕복이 깨지고, 왕복이 깨지면 이 파일은 위험을 «옮기기만» 한 것이다.
   ⚠️ `extra` 가 큰 것은 흠이 아니라 «오늘의 정직한 크기»다 — 단계가 갈수록 줄어든다.
"""
from __future__ import annotations

from chain import join_into

#: 체인 문법에서 «모양으로 접히는» 칸. 나머지는 전부 `extra` 로 간다.
CHAIN_MODELLED = ("name", "enabled", "trigger_table", "trigger_columns",
                  "target_table", "mapper", "mapper_module", "mapper_function",
                  "params", "group_by", "max_group_rows", "max_group_attempts",
                  "idempotent")

#: 조인 문법에서 접히는 칸. `materialize` 는 «일부러» 여기 없다 — 8.5 ③ 의 판단 대기 항목이라
#: 지금 접으면 아직 안 받은 판정을 코드가 «먼저» 내려 버린다.
JOIN_MODELLED = ("left_table", "right_table", "left_columns", "right_columns",
                 "right_folds")

_LIMIT_KEYS = ("group_by", "max_group_rows", "max_group_attempts", "idempotent")


def _present(raw: dict, keys) -> dict:
    """선언에 «있는» 칸만. 없는 칸을 None 으로 채우면 왕복이 원본에 없던 키를 만든다."""
    return {key: raw[key] for key in keys if key in raw}


def from_chain_rule(raw: dict, origin: str = "declared") -> dict:
    """오늘의 체인 규칙 dict -> 내부 규칙."""
    raw = raw if isinstance(raw, dict) else {}
    mapper = _present(raw, ("mapper", "mapper_module", "mapper_function", "params"))
    return {
        "name": raw.get("name"),
        "enabled": raw.get("enabled", True),
        # ⚠️ 「안 적음」과 「true 라고 적음」은 «다른 선언»이다. 값만 들고 있으면 왕복이
        #    원본에 없던 칸을 만들어 내고, 그러면 census 가 매 적재마다 「바뀜」이라 말한다.
        "enabled_written": "enabled" in raw,
        "on": _rename(_present(raw, ("trigger_table", "trigger_columns")),
                      {"trigger_table": "table", "trigger_columns": "columns"}),
        "derive": {"kind": "mapper", "mapper": mapper},
        "into": ({"table": raw["target_table"]} if "target_table" in raw else {}),
        "limits": _present(raw, _LIMIT_KEYS),
        "origin": origin,
        "grammar": "chain",
        "extra": {key: value for key, value in raw.items()
                  if key not in CHAIN_MODELLED},
    }


#: The cells of `key`. Named so the form and the reader cannot drift: `builtins`
#: asks `key.unique` when it decides whether to build an index (S-240), and a form that
#: spelled its own cell names would be a second author of this list.
KEY_CELLS = ("columns", "unique")

#: The two things `into` can say, and they are exclusive: a join that WRITES names its
#: table, a join that answers at READ time says so (S-251). The form draws one or the
#: other, never both.
INTO_KINDS = ("table", "read")

#: The three words a declaration's `derive.kind` can say. A LOADED rule has already been
#: translated to today's flat shape, so the word has to be read back off what it RUNS.
DECLARED_KINDS = ("join", "decide", "mapper")


def declared_kind(rule: dict) -> str:
    """A loaded chain rule -> the word its DECLARATION would use for it.

    🔴 THE OPERATOR'S WORD, NOT THE PLUMBING'S. A screen that offers 「builtin:join_into」
    or 「enrichment_dedup:」 is asking the reader to know this product's internals to pick a
    rule - the same defect the COLLECT dropdown had when it offered `point` and `collection`
    (2026-08-27: 「사용자가 claim, point, collection 이런 걸 어케 암」).

    ⚠️ IT IS NOT `builtins.synthesized_kind_counts`, AND THE DIFFERENCE IS THE QUESTION.
    That function asks 「how many rules did the PRODUCT synthesise, of each origin」 for the
    boot line; this asks 「what does the DECLARATION behind this rule say it is」. Same
    prefixes, different subjects - folding them would make one answer serve two questions.
    """
    from chain import join_into
    from enrichment import config as enrichment_config
    import virtual_join.config as vjc

    rule = rule if isinstance(rule, dict) else {}
    mapper = rule.get("mapper")
    if mapper in (join_into.JOIN_INTO_MAPPER, vjc.JOIN_MAPPER):
        return "join"
    # ⚠️ BOTH HALVES OF A `decide` DECLARATION ANSWER 「decide」. The dedup half and its
    # auto-confirm companion come from ONE declaration, and an operator reading a list of
    # rules for one table should see what the declaration says, not which half they got.
    name = str(rule.get("name") or "")
    if (mapper == enrichment_config.AUTO_CONFIRM_MAPPER
            or name.startswith(enrichment_config.DEDUP_PREFIX)
            or name.startswith(enrichment_config.AUTO_CONFIRM_PREFIX)):
        return "decide"
    return "mapper"


def as_chain_rule(internal: dict) -> dict:
    """내부 규칙 -> 오늘의 체인 규칙 dict. `from_chain_rule` 의 역이다."""
    out = {}
    if internal.get("name") is not None or "name" in internal:
        out["name"] = internal.get("name")
    on = internal.get("on") or {}
    if "table" in on:
        out["trigger_table"] = on["table"]
    if "columns" in on:
        out["trigger_columns"] = on["columns"]
    into = internal.get("into") or {}
    if "table" in into:
        out["target_table"] = into["table"]
    derive = internal.get("derive") or {}
    if derive.get("kind") == "join" and "table" in into:
        # 🔴 [S-237] A `join` KIND IS A MAPPER THE PRODUCT OWNS. Until this, a unified
        # declaration saying `derive: {kind: "join"}` came out of here with NO mapper cell
        # and the loader refused it as `unresolvable_mapper` (measured) - the grammar could
        # be written and could never run.
        #
        # ⚠️ ONLY WHEN IT WRITES. `into.read` is the READ-TIME virtual join, which is not a
        # chain rule at all and must keep coming out of `as_join_rule` untouched; the two are
        # told apart by which `into` the declaration carries, which is the distinction the
        # internal shape already makes.
        out["mapper"] = join_into.JOIN_INTO_MAPPER
        out["params"] = dict(derive.get("join") or {})
        # 🔴 [판정 398] THE AUTHOR WRITES THE JOIN ONCE AND THE SHELL DERIVES THE TRIGGER.
        # The left join key IS the trigger column - true by coincidence in every virtual join
        # declared today, and the new grammar says it instead of leaving it to be rediscovered.
        # A second place to write one value is a second place for it to be wrong.
        derived = join_trigger_columns(derive.get("join") or {})
        if derived:
            out["trigger_columns"] = derived
        # 🔴 PACED, NOT INLINE. One reference row reaches 70,800 target rows on this
        # product's own measurement (S-151), and 「요청·커밋 경로 인라인 금지」 is standing.
        # The cell says so in the rule rather than only in the dispatcher.
        out["follow_up"] = True
        # The cell travels with the rule so the SHELL can read it at load time. It is not a
        # mapper argument - `join_into` never sees it - which is why it sits beside `params`
        # rather than inside it.
        if internal.get("key"):
            out["key"] = dict(internal["key"])
    out.update(derive.get("mapper") or {})
    out.update(internal.get("limits") or {})
    out.update(internal.get("extra") or {})
    # `enabled` 는 «생략된 것»과 «적힌 것»이 다른 문장이므로 «적혀 있었을 때만» 되돌린다
    if internal.get("enabled_written"):
        out["enabled"] = internal.get("enabled")
    return out


def from_join_rule(name: str, raw: dict, origin: str = "declared") -> dict:
    """오늘의 가상 조인 선언 -> 내부 규칙. 읽기 시점에 앉으므로 `into.read`."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "name": name,
        "enabled": raw.get("enabled", True),
        "enabled_written": "enabled" in raw,
        "on": ({"table": raw["left_table"]} if "left_table" in raw else {}),
        "derive": {"kind": "join",
                   "join": _present(raw, JOIN_MODELLED[1:])},
        "into": {"read": True},
        "limits": {},
        "origin": origin,
        "grammar": "join",
        "extra": {key: value for key, value in raw.items()
                  if key not in JOIN_MODELLED},
    }


def as_join_rule(internal: dict) -> dict:
    """내부 규칙 -> 오늘의 가상 조인 선언 dict."""
    out = {}
    on = internal.get("on") or {}
    if "table" in on:
        out["left_table"] = on["table"]
    out.update((internal.get("derive") or {}).get("join") or {})
    out.update(internal.get("extra") or {})
    return out


def _rename(source: dict, mapping: dict) -> dict:
    return {mapping[key]: value for key, value in source.items() if key in mapping}


# ---------------------------------------------------------------------------
# 새 문법 — 내부 객체를 «적는» 모양 (S-234 §2). 읽기와 쓰기가 한 쌍이다.
# ---------------------------------------------------------------------------

def to_declaration(internal: dict) -> dict:
    """내부 규칙 -> 새 문법 dict. 「사람이 적는 모양」이므로 «빈 칸을 만들지 않는다».

    ⚠️ 빈 `limits: {}` 나 `on: {}` 를 적어 두면 선언이 「무언가 설정됐다」고 읽힌다 —
    운영자에게 «없는 것»과 «비어 있게 정한 것»은 다른 문장이다.
    """
    out = {"name": internal.get("name")}
    if internal.get("enabled_written"):
        out["enabled"] = internal.get("enabled")
    for key in ("on", "derive", "into", "key", "limits"):
        value = internal.get(key)
        if value:
            out[key] = value
    if internal.get("extra"):
        # 🔴 제품이 뜻을 모르는 칸은 «한 자리»에 모아 둔다 — 흩어 두면 새 문법의 칸과
        #    구별이 안 되고, 그러면 다음 사람이 그것을 문법이라 읽는다.
        out["extra"] = internal["extra"]
    return out


def from_declaration(raw: dict, origin: str = "declared") -> dict:
    """새 문법 dict -> 내부 규칙. `to_declaration` 의 역이다."""
    raw = raw if isinstance(raw, dict) else {}
    derive = raw.get("derive") or {}
    kind = derive.get("kind")
    if not kind:
        for name in ("mapper", "join", "decide"):
            if name in derive:
                kind = name
                break
    return {
        "name": raw.get("name"),
        "enabled": raw.get("enabled", True),
        "enabled_written": "enabled" in raw,
        "on": dict(raw.get("on") or {}),
        "derive": dict(derive, kind=kind or "unknown"),
        "into": dict(raw.get("into") or {}),
        # 🔴 [S-240] `key` WAS DROPPED ON THE FLOOR. The plan says 「선언이 key.unique 라고
        # 말하면 제품이 성립시킨다」 and RUN.md said the product builds the index - and for a
        # unified join both were FALSE, because the cell never survived the translation:
        # nothing carried it, so nothing could read it.
        "key": dict(raw.get("key") or {}),
        "limits": dict(raw.get("limits") or {}),
        "origin": origin,
        "grammar": "unified",
        "extra": dict(raw.get("extra") or {}),
    }


#: What the reference-side companion's name is built from. One spelling, because the loader
#: writes it and the census reads it.
REFERENCE_SUFFIX = ":reference"


def companion_rules(internal: dict) -> list:
    """The EXTRA chain rules one unified declaration implies. Today: a join's reference side.

    🔴 ONE DECLARATION, TWO TRIGGERS (S-237 ㉢). A join has to be recomputed when a target row
    moves AND when the row it points at moves, and those are two different `trigger_table`
    values - the loader matches a rule to an event by that cell, so one rule cannot watch two
    tables. What must NOT be duplicated is the SPEC, and it is not: both rules carry the same
    `params`, and the mapper reads the side from `trigger_table`.

    ⚠️ EMPTY FOR EVERY OTHER KIND, and that is the point of a named function rather than a
    branch inside the translator: 「this declaration implies more rules」 is a question every
    kind will eventually answer, and the answer belongs somewhere a reader can find it.
    """
    derive = internal.get("derive") or {}
    into = internal.get("into") or {}
    if derive.get("kind") != "join" or "table" not in into:
        return []
    spec = dict(derive.get("join") or {})
    right_table = spec.get("right_table")
    name = internal.get("name")
    if not right_table or not name:
        return []
    primary = as_chain_rule(internal)
    if primary.get("trigger_table") == right_table:
        # The declaration already watches the reference table; a second rule would be the
        # same rule twice and the dispatcher would run the join twice per event.
        return []
    companion = dict(primary)
    companion["name"] = str(name) + REFERENCE_SUFFIX
    companion["trigger_table"] = right_table
    return [companion]


class JoinTriggerConflict(ValueError):
    """⛔ TWO ANSWERS TO 「WHICH COLUMNS WAKE THIS JOIN」 (판정 398). Writing `on.columns`
    beside `derive.join.on` is allowed only while the two AGREE; when they differ the product
    cannot know which the author meant, and picking one silently is how a join comes to watch
    a column nobody asked it to watch."""


def join_trigger_columns(spec: dict) -> list:
    """The left key columns of a join spec, in declared order - the trigger columns."""
    out = []
    for pair in (spec or {}).get("on") or ():
        if isinstance(pair, dict) and pair.get("left"):
            out.append(str(pair["left"]))
    return out


def refuse_join_trigger_conflict(internal: dict) -> None:
    """Raise when the author wrote `on.columns` AND it differs from the derived ones.

    ⚠️ AGREEING IS NOT AN ERROR. An author who writes both has said one thing twice, which is
    redundant rather than wrong, and refusing it would break declarations that are correct.
    """
    derive = internal.get("derive") or {}
    if derive.get("kind") != "join":
        return
    written = (internal.get("on") or {}).get("columns")
    if written is None:
        return
    derived = join_trigger_columns(derive.get("join") or {})
    if list(written) != derived:
        raise JoinTriggerConflict(
            "%r writes on.columns %r while derive.join.on implies %r; "
            "write the join once and let the trigger follow it"
            % (internal.get("name"), list(written), derived))


def unknown_join_cells(internal: dict) -> list:
    """Sub-cells of `derive.join` this product does not read. NAMED, never refused.

    ⚠️ A CELL THE PRODUCT DOES NOT KNOW MAY BE A LIVE ARGUMENT IT HAS NOT LEARNED YET, so
    the posture is yesterday's: say the name loudly and let the rule run. Refusing here would
    stop a declaration that works over a word nobody has defined.
    """
    derive = internal.get("derive") or {}
    if derive.get("kind") != "join":
        return []
    return join_into.unknown_cells(derive.get("join") or {})


#: The sub-cells of `derive.decide` this product reads. `auto_confirm_declared` is NOT among
#: them (판정 401): 「was it written」 is DERIVED from the key being present, the same way
#: `enabled_written` is, and a cell for it would be a place to write that you wrote something.
DECIDE_CELLS = ("key", "fields", "list_columns", "aggregations", "reference_views",
                "auto_confirm", "alignment")

#: How a `decide` cell is spelled in the enrichment vocabulary the normalizer already reads.
_DECIDE_TO_ENRICHMENT = {"key": "decision_key", "fields": "target_fields"}


def decide_rules(internal: dict, known_tables: dict = None) -> tuple:
    """A unified `decide` declaration -> (its chain rules, refusal).

    🔴 [S-239] THE SHELL IS THE WHOLE ROUND. `enrich` is ALREADY a chain mapper - dedup on
    the ordinary path, auto-confirm on the follow-up lap - so nothing about how it RUNS moves
    here. What moves is where the declaration may be written, and the proof that the two
    writings agree is that they reach one expander, not two.
    """
    from enrichment import config as enrichment_config

    derive = internal.get("derive") or {}
    if derive.get("kind") != "decide":
        return [], None
    cells = {}
    for key, value in (derive.get("decide") or {}).items():
        cells[_DECIDE_TO_ENRICHMENT.get(key, key)] = value
    return enrichment_config.chain_rules_from_cells(
        internal.get("name"), bool(internal.get("enabled_written")),
        bool(internal.get("enabled", True)),
        (internal.get("on") or {}).get("table"),
        (internal.get("into") or {}).get("table"),
        cells, known_tables)


def unknown_decide_cells(internal: dict) -> list:
    """Sub-cells of `derive.decide` this product does not read. NAMED, never refused."""
    derive = internal.get("derive") or {}
    if derive.get("kind") != "decide":
        return []
    return sorted(str(key) for key in (derive.get("decide") or {})
                  if key not in DECIDE_CELLS)


def is_switched_off(internal: dict) -> bool:
    """⛔ [판정 399, ③′] `enabled: false` IS THE ONE OFF SWITCH A UNIFIED DECLARATION HAS.

    So OFF has to mean what §0-ter demands of a switch: the loader touches no database and
    stands no rule - not 「stands it and filters it later」, which is the shape that let an
    operator turn everything off and watch it keep erroring. `ASSY_CHAIN_SYNTHESIZE` is a
    DIFFERENT switch with a different subject (rules the product derived from files the
    operator did not write), and it deliberately does not reach here.
    """
    return internal.get("enabled_written") and internal.get("enabled") is False


def expand_declaration(declaration, table_config=None) -> tuple:
    """A rules-file entry -> (the chain rules it stands, refusal, notes).

    🔴 [S-244] ONE AUTHOR, TWO CALLERS. The loader translated a unified declaration before
    scoring it; the save gate scored the RAW entry - so `POST /admin/chain/rules/raw` refused
    (`trigger_table` missing, `derive` unknown, `unresolvable_mapper`) what the loader accepts
    from the same file. S-204's sentence 「저장 관문과 로더가 같은 판정자」 had quietly become
    false for this grammar: same judge, different input is the same defect as two judges.

    ⚠️ AN OLD FLAT RULE COMES BACK UNTOUCHED, and that is what keeps the old save path byte
    for byte: no `derive`, no translation, the entry itself is the one rule it stands.

    🔴 THREE OUTCOMES, AND 「OFF」 IS NOT A REFUSAL (판정 399). A disabled declaration stands
    no rule and says so in `notes`; a refusal list is for declarations that are WRONG, and an
    operator who turned something off did not make a mistake.
    """
    if not isinstance(declaration, dict) or not isinstance(declaration.get("derive"), dict):
        return ([declaration], None, [])

    internal = from_declaration(declaration)
    name = declaration.get("name")
    if is_switched_off(internal):
        return ([], None, ["%s: enabled=false \u2014 no rule stands for it." % name])

    # 🔴 [S-251] A READ-TIME JOIN IS NOT A CHAIN RULE, AND SAYING SO IS NOT A REFUSAL.
    # `into: {read: true}` declares a join that answers when somebody READS - it writes
    # nothing, has no trigger and runs no mapper. Before this it came out of here as a rule
    # with no mapper cell and the loader dropped it as `unresolvable_mapper`: a correct
    # declaration reported as a typo. It stands in `virtual_join.config.load_virtual_join_rules`
    # instead, through the adapter that has always known how to write one (`as_join_rule`).
    if ((internal.get("derive") or {}).get("kind") == "join"
            and (internal.get("into") or {}).get("read")):
        return ([], None,
                ["%s: into.read \u2014 a READ-TIME join. It stands beside the ones declared "
                 "in virtual_join_rules.json, not as a chain rule." % name])

    decided, decide_refusal = decide_rules(internal, table_config)
    if decide_refusal:
        return ([], "%s: %s" % (name, decide_refusal), [])
    if decided:
        return (decided,
                None,
                ["%s: derive.decide cell this product does not read \u2014 %s. "
                 "The rule runs." % (name, cell)
                 for cell in unknown_decide_cells(internal)])

    try:
        refuse_join_trigger_conflict(internal)
    except JoinTriggerConflict as conflict:
        return ([], "join_trigger_conflict: %s" % conflict, [])

    notes = []
    unknown = unknown_join_cells(internal)
    if unknown:
        notes.append(
            "%s: derive.join cell(s) this product does not read \u2014 %s. The rule runs; "
            "check the spelling if it was meant to do something."
            % (name, ", ".join(unknown)))
    return ([as_chain_rule(internal)] + companion_rules(internal), None, notes)
