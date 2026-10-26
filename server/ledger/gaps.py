# -*- coding: utf-8 -*-
"""Where the declaration says a link should be and the ledger has none.

🔴 THIS MODULE NAMES NOTHING. `docs/spec/APPLICATION_GAP_SPEC.md` named every gap and gave each
an action and an owner; `gap_names.json` is that table in machine-readable form, and this
file looks names UP. A label written here would be a second authority, and the first one
would go stale without anybody noticing.

🔴 AND IT BRANCHES ON NO DOMAIN WORD. What it computes comes from the declaration - which
objects are nodes, which predicate names a type its only way into existence - and what it
CALLS things comes from the table. Neither is a literal in this file.

🔴 THE TWO ARE CHECKED AGAINST EACH OTHER. A question the declaration asks and the table has not named is asked
in its own words, «<predicate> · <type> (no name)», and counted - owner 10-27 «안 막고 날 낱말로» replaced S1's
refusal, so a predicate the operator adds never stops the walk routes. A table row whose predicate the
declaration does not have is left unused and counted. The table is the operator's `config/gap_names.json`, else the
tracked sample.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: Ruled by the spec §1 exclusion ③ and not derivable from the declaration: the predicate
#: whose ABSENCE is the good outcome - a die with no defect is a good die. Cited here, not
#: decided here; this is the only predicate named in this file.
SPEC_EXCLUDED = ("observed",)

NAMES_FILE = "gap_names.json"


def names_path():
    """The operator's `config/gap_names.json`, else the shipped sample - the table is the operator's to write
    (owner 10-27)."""
    import paths

    live = paths.config_path(NAMES_FILE)
    # the TRACKED sample, not the data root's: an isolated root has no sample folder, and the table was read from the
    # code tree before it moved
    shipped = os.path.join(paths.SERVER_DIR, "config", paths.CONFIG_SAMPLE_DIRNAME, NAMES_FILE + ".sample")
    return live if os.path.exists(live) else shipped


from declaration_names import bare_name as _bare_name
from .schema import event_time_sql


#: `of_kind@1` -> `of_kind`. 🔴 이 번역의 «본체»는 `declaration_names` 에 있다 —
#: 같은 이름에 «네 본체»가 있었고 그 넷이 공백·대소문자·None 에서 갈렸다. 이름은 여기 남겨
#: 이 모듈의 아홉 호출부를 그대로 두고, 몸통만 한 자리로 보낸다.
#: ⚠️ 종전 이 판은 `str(None)` 을 태워 `"None"` 이라는 이름을 만들었다. 이제 빈 이름이다.
_bare = _bare_name


def load_names(path=None):
    return json.loads(Path(path or names_path()).read_text(encoding="utf-8"))


def _vocabulary(declaration):
    return (declaration or {}).get("vocabulary") or {}


def _object_kind(spec):
    return ((spec or {}).get("object") or {}).get("kind")


def _targets(spec):
    return tuple((spec or {}).get("object", {}).get("types") or ())


def _subjects(spec):
    return tuple((spec or {}).get("subjects") or ())


def vacuous_types(declaration):
    """Types that CANNOT exist without the predicate in question -> "해당 없음".

    🔴 NOT ZERO, AND NOT DROPPED EITHER. A node is never stored; it is derived from an
    atom's keys. So when a predicate is a type's ONLY appearance anywhere in the
    vocabulary, a node of that type with no such edge cannot exist at all - the set is
    empty by construction rather than by having nothing in it yet. Reporting 0 would say
    "we looked and found none"; dropping the row would send the next person to ask the
    same question again. The spec keeps the row and writes the reason.

    Returns `{(predicate, type): appearances}` for every pair where the predicate is the
    type's only appearance, whichever side it is on. One rule covers both sides, so a new
    predicate lands correctly without an edit here.
    """
    appearances = {}
    for name, spec in _vocabulary(declaration).items():
        for entity_type in _subjects(spec) + _targets(spec):
            appearances.setdefault(entity_type, set()).add(name)
    return {(name, entity_type)
            for entity_type, names in appearances.items() if len(names) == 1
            for name in names}


def questions(declaration, names=None, unused=None):
    """Every gap this declaration asks, named by the table. Pure - no database.

    Each question carries `form`, the `type` it is about, the predicates that make it, and
    the `name`/`action` the spec gave it. `vacuous` marks the ones that cannot have members
    rather than the ones that happen to have none.
    """
    names = names or load_names()
    vocabulary = _vocabulary(declaration)
    live = {name: spec for name, spec in vocabulary.items() if name not in SPEC_EXCLUDED}
    by_bare = {_bare(name): name for name in vocabulary}
    vacuous = {(_bare(p), t) for p, t in vacuous_types(declaration)}

    def declared(row, *predicates):
        """The declaration's names of a table row's predicates - None when this world lacks one: the row is left
        unused and counted in `unused`, not refused (owner 10-27 «안 막음» - worlds differ in vocabulary)."""
        full = [by_bare.get(p) for p in predicates]
        if None in full:
            if unused is not None:
                unused.append(row)
            return None
        return full

    out = []
    for row in names.get("pairs", []):
        entity_type = row["type"]
        both = declared(row, *row["side_a"], *row["side_b"])
        if both is None:
            continue
        side_a, side_b = both[:len(row["side_a"])], both[len(row["side_a"]):]
        out.append({"form": "pair", "type": entity_type,
                    "present": side_a, "absent": side_b,
                    "name": row["a_only"], "meaning": row["a_only_meaning"],
                    "vacuous": False})
        out.append({"form": "pair", "type": entity_type,
                    "present": side_b, "absent": side_a,
                    "name": row["b_only"], "meaning": row["b_only_meaning"],
                    "vacuous": False})

    for row in names.get("subject_sides", []):
        predicate = (declared(row, row["predicate"]) or [None])[0]
        if predicate is None:
            continue
        out.append({"form": "subject_side", "type": row["type"],
                    "present": [], "absent": [predicate],
                    "name": row["name"], "action": row["action"],
                    "vacuous": (row["predicate"], row["type"]) in vacuous})

    for row in names.get("object_sides", []):
        predicate = (declared(row, row["predicate"]) or [None])[0]
        if predicate is None:
            continue
        out.append({"form": "object_side", "type": row["type"],
                    "present": [], "absent": [predicate],
                    "name": row["name"], "action": row["action"],
                    "vacuous": (row["predicate"], row["type"]) in vacuous})

    # 🔴 EXCLUSION ① IS SHOWN, NOT SWALLOWED. A predicate whose object is not a node has no
    # object side that could be missing - `has_netdie` carries a number, `register` carries
    # nothing at all - and the brief's G2 asks for that to arrive as "질문이 성립하지 않음"
    # rather than as a silent absence from the list. Same reason the spec keeps the recipe
    # row: leaving it out sends the next person to ask why it is not there.
    #
    # No name is invented here. The type and the predicate come from the declaration and
    # the label is the application vocabulary's own value, which is a statement about the
    # QUESTION rather than about the domain.
    for name, spec in sorted(live.items()):
        if _object_kind(spec) == "entity_ref":
            continue
        out.append({"form": "object_side", "type": None, "present": [],
                    "absent": [name], "name": "해당 없음",
                    "action": "없음 — 목적이 노드가 아니라 가리킬 것이 없습니다",
                    "vacuous": True})

    for form, predicate, entity_type in _unnamed(declaration, live, out):
        out.append({"form": form, "type": entity_type, "present": [], "absent": [predicate],
                    "name": "%s · %s (no name)" % (_bare(predicate), _bare(entity_type)), "action": None,
                    "vacuous": False, "unnamed": True})
    return out


def _unnamed(declaration, live, named):
    """[(form, predicate, type)] - the questions the declaration asks and the table has not named. They are asked in
    their own words, not refused (owner 10-27 «안 막고 날 낱말로», which replaced S1's refusal): a predicate the
    operator adds keeps the walk routes up and shows as «<predicate> · <type> (no name)» until they name it."""
    covered = {(item["type"], tuple(sorted(item["absent"]))) for item in named}
    vacuous = {(_bare(p), t) for p, t in vacuous_types(declaration)}
    missing = []
    for name, spec in sorted(live.items()):
        if set(_subjects(spec)) & set(_targets(spec)):
            # Exclusion ②: a predicate whose subject type is also its object type is a
            # CHAIN, and every chain has a head and a tail. Counting those makes every
            # chain report two gaps and fills the screen with the shape of chains rather
            # than with missing work. Ruled by the spec §1, mechanical from the
            # declaration, and applied to BOTH sides - a chain has two ends.
            continue
        if _object_kind(spec) != "entity_ref":
            # Exclusion ①: an object that is not a node has no object side to be missing.
            # The subject side is still a question and is covered below.
            targets = ()
        else:
            targets = _targets(spec)
        for entity_type in _subjects(spec):
            if (_bare(name), entity_type) in vacuous:
                continue
            if (entity_type, (name,)) not in covered and not any(
                    entity_type == item_type and name in absent
                    for item_type, absent in covered):
                missing.append(("subject_side", name, entity_type))
        for entity_type in targets:
            if (_bare(name), entity_type) in vacuous:
                continue
            if not any(entity_type == item_type and name in absent
                       for item_type, absent in covered):
                missing.append(("object_side", name, entity_type))
    return sorted(set(missing))


#: How many distinct nodes one question examines before it calls itself a sample. Small on
#: purpose: this is a request path, and the cost measured on 2026-08-31 for a single
#: unbounded anti-join was 26.20 seconds. The budget is what makes twenty questions
#: answerable at all, and `count_kind` is what stops the answer pretending otherwise.
NODE_SCAN_LIMIT = 200

#: 🔴 THE SAMPLE IS NOT THE OLDEST N, AND SAYS SO. Choosing the oldest would mean ordering
#: every node of the type by age first, which is the full scan the budget exists to avoid.
#: The rows that come back DO carry their age and are shown oldest-first among themselves,
#: but the SET is the front of the KEY order (총괄 ㄱ 10-01 - it was whatever the scan met
#: first until `_nodes_of_type_sql` became a skip scan). Letting either read as "oldest" is
#: the misreading this whole vocabulary exists to prevent, so the wording is part of the
#: answer rather than a caveat somewhere else.
SAMPLE_NOT_AGE_ORDERED = (
    "표본은 키 순서로 «앞쪽» 노드들입니다 — «가장 오래된» 것들이 아닙니다. "
    "나이순으로 고르려면 그 타입 전체를 한 번 훑어야 하고, 그게 이 예산이 피하는 그 비용입니다. "
    "돌아온 것들끼리는 오래된 순으로 보여 드립니다.")


#: How a prefix is matched (총괄 bccbdd601): the database's default collation decides, asked once a request
#: (`prefix_case`). Where case sorts together, the run of keys that start with a prefix ignoring case is
#: unbroken and the scan can stop at its end; where it sorts apart (C), only the exact prefix is.
PREFIX_INSENSITIVE = "insensitive"
PREFIX_EXACT = "exact"


def prefix_case(connection) -> str:
    """`PREFIX_INSENSITIVE` when the default collation sorts case together ('a' before 'B' -
    Korean_Korea.949 on this box), else `PREFIX_EXACT` (C sorts every capital first, so a
    case-ignoring run would be split in two and the scan would stop at the split)."""
    return PREFIX_INSENSITIVE if connection.exec_driver_sql("SELECT 'a' < 'B'").scalar() else PREFIX_EXACT


def _nodes_of_type_sql(prefix=None):
    """Nodes of one type, from BOTH sides, with the moment each was first named.

    `prefix` (`PREFIX_INSENSITIVE` · `PREFIX_EXACT`, 총괄 bccbdd601): only the keys whose `%(axis)s`
    starts with `%(p)s` (`%(plen)s` characters) - each side's step starts at the least such node
    (`%(nulls)s`, every declared key JSON null, with the prefix set in that axis) and stops at the
    first key past the prefix, so it reads the matching keys and one more, wherever they stand in
    the type. No prefix: the statement as it always was.

    🔴 SUBJECT *AND* OBJECT, because a node is not stored - it is derived from an atom's
    keys - so it begins to exist the moment any atom names it, on either side. Measured on
    this box: `defect_kind@1` and `recipe@1` have ZERO atoms of their own and appear only
    as objects, so a subject-only enumeration would report them as having no members at
    all rather than as having no age.

    🔴 A SKIP SCAN, SO THE BUDGET IS WHAT IT COSTS (총괄 ㄱ 10-01). Grouping every atom of
    the type before the LIMIT made a budget of 200 cost the whole type. Each side steps from
    a key to the next larger one - one probe of the side's index (`idx_ledger_subject_entity`,
    `idx_ledger_object_entity`) a step - and stops at the budget; the first instant is read
    for the chosen keys only. The set is the FRONT OF THE KEY ORDER (`SAMPLE_NOT_AGE_ORDERED`).
    ⚠️ Reading a whole type this way is slower than grouping it - no caller asks past the
    route's seed cap (`ledger_subgraph.MAX_SEED_LIMIT`) or `NODE_SCAN_LIMIT`.
    """
    start_s = start_o = keep_s = keep_o = pick = ""
    if prefix is not None:
        # the one place the case is decided - the bound and the match together
        least = "LEAST(lower(%(p)s), upper(%(p)s))" if prefix == PREFIX_INSENSITIVE else "%(p)s"

        def match(keys):
            if prefix == PREFIX_INSENSITIVE:
                return " AND lower(left(" + keys + " ->> %(axis)s, %(plen)s)) = lower(%(p)s)"
            return " AND left(" + keys + " ->> %(axis)s, %(plen)s) = %(p)s"

        bound = "jsonb_set(%(nulls)s::jsonb, ARRAY[%(axis)s], to_jsonb(CAST(" + least + " AS text)))"
        start_s, start_o = " AND subject_keys >= " + bound, " AND object_payload->'keys' >= " + bound
        keep_s, keep_o, pick = match("subject_side.keys"), match("object_side.keys"), match("keys")
    return """
        WITH RECURSIVE subject_side(keys, n) AS (
            (SELECT subject_keys, 1 FROM {table} f WHERE subject_type = %(bare)s""" + start_s + """
              ORDER BY subject_keys LIMIT 1)
            UNION ALL
            SELECT (SELECT s.subject_keys FROM {table} s
                     WHERE s.subject_type = %(bare)s AND s.subject_keys > subject_side.keys
                     ORDER BY s.subject_keys LIMIT 1), n + 1
              FROM subject_side WHERE subject_side.keys IS NOT NULL AND n < %(scan)s""" + keep_s + """
        ), object_side(keys, n) AS (
            (SELECT object_payload->'keys', 1 FROM {table} f
              WHERE object_kind = 'entity_ref' AND object_payload->>'type' = %(bare)s""" + start_o + """
              ORDER BY object_payload->'keys' LIMIT 1)
            UNION ALL
            SELECT (SELECT o.object_payload->'keys' FROM {table} o
                     WHERE o.object_kind = 'entity_ref' AND o.object_payload->>'type' = %(bare)s
                       AND o.object_payload->'keys' > object_side.keys
                     ORDER BY o.object_payload->'keys' LIMIT 1), n + 1
              FROM object_side WHERE object_side.keys IS NOT NULL AND n < %(scan)s""" + keep_o + """
        ), named AS (
            SELECT keys FROM subject_side WHERE keys IS NOT NULL""" + pick + """
            UNION
            SELECT keys FROM object_side WHERE keys IS NOT NULL""" + pick + """
            ORDER BY keys LIMIT %(scan)s
        )
        SELECT named.keys AS keys, LEAST(
            (SELECT min(s.occurred_at) FROM {table} s
              WHERE s.subject_type = %(bare)s AND s.subject_keys = named.keys
                AND """ + event_time_sql("s") + """),
            (SELECT min(o.occurred_at) FROM {table} o
              WHERE o.object_kind = 'entity_ref' AND o.object_payload->>'type' = %(bare)s
                AND o.object_payload->'keys' = named.keys
                AND """ + event_time_sql("o") + """)) AS first_seen
          FROM named ORDER BY named.keys LIMIT %(scan)s
    """


def _names_node_sql(alias, node):
    """`alias` (an atom) names `node` (an SQL expression for its keys), on either side.

    🔴 [총괄 29cee1d47] ONE SPELLING of what a node of type `%(bare)s` is named by - the
    predicate question below and the key list's count (`trace_router.ledger_key_values`) both
    ask it. Measured on the box against two per-side subqueries: the same totals, no slower
    (task/scoped_redo_report.md, 29cee1d47).
    """
    return ("((%(a)s.subject_type = %%(bare)s AND %(a)s.subject_keys = %(n)s)"
            " OR (%(a)s.object_kind = 'entity_ref' AND %(a)s.object_payload->>'type' = %%(bare)s"
            " AND %(a)s.object_payload->'keys' = %(n)s))" % {"a": alias, "n": node})


def _has_predicate_sql():
    """One expression for "this node has that predicate", whichever side it is on.

    🔴 NO BRANCH ON DIRECTION. A subject-side question asks about a predicate the node
    should have gone OUT on, a pair asks about one that should have come IN, and both are
    the same question about the same node: does an atom of that predicate name it? Writing
    two expressions would mean deciding, per question, which one applies - a branch on the
    shape of the declaration, and a place for the two to drift apart.
    """
    return ("""
        EXISTS (
            SELECT 1 FROM {table} e
             WHERE e.predicate = ANY(%(preds)s)
               AND """ + _names_node_sql("e", "n.keys") + """)
    """)


class GapQuestionUnknown(ValueError):
    """`only` named a question that is not in the table. Refused rather than answered empty.

    An empty result for a typo reads exactly like "this gap has no members", which is the
    good news an operator would act on by moving along.
    """


def measure(engine, declaration, names=None, scan_limit=NODE_SCAN_LIMIT, only=None,
            relation=None):
    """Count each named gap over a bounded sample of nodes, with each one's age. READ ONLY.

    🔴 `only` EXISTS BECAUSE THE SCREEN HAS THREE SECONDS AND ALL TWENTY TAKE THIRTY.
    `questions()` is pure and costs nothing, so a screen can open with the twenty NAMES
    immediately and pay for a count only when somebody expands one - measured at about a
    twentieth of the batch. The all-at-once path stays for batch and CLI callers; this is a
    second entry to the same work, not a second implementation of it.

    🔴 EVERY NUMBER SAYS WHAT KIND OF NUMBER IT IS. `count_kind` is `exact` only when the
    scan saw every node of the type - the budget came back short - and `sample` otherwise.
    A question whose type cannot exist without the predicate is `not_applicable` and gets
    NO count at all: zero would say "we looked and found none" about a set that cannot have
    members, and the spec is explicit that the row stays so nobody asks again.
    """
    from . import schema

    names = names or load_names()
    asked = questions(declaration, names=names)
    if only is not None:
        asked = [item for item in asked if item["name"] == only]
        if not asked:
            raise GapQuestionUnknown(
                f"no gap is named {only!r}. The names come from "
                f"docs/spec/APPLICATION_GAP_SPEC.md - ask GET /api/ledger/gaps for the list.")
    # `relation`: the walk relation of the worlds asked about (the router's `_worlds`)
    relation = relation or schema.walk_relation((schema.world_names(),))
    node_sql = _nodes_of_type_sql().replace("{table}", relation)
    has_sql = _has_predicate_sql().replace("{table}", relation)

    out = []
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            for item in asked:
                row = {"name": item["name"], "type": item["type"], "form": item["form"],
                       "present": item["present"], "absent": item["absent"],
                       "action": item.get("action"), "meaning": item.get("meaning")}
                if item["vacuous"]:
                    # Not a count and not a zero: the set cannot have members.
                    row.update({"absence": "not_applicable", "count": None,
                                "count_kind": None, "examined": None, "oldest": []})
                    out.append(row)
                    continue
                bare = _bare(item["type"])
                params = {"bare": bare, "scan": scan_limit,
                          "absent": [_bare(p) for p in item["absent"]],
                          "present": [_bare(p) for p in item["present"]]}
                where = ["NOT " + has_sql.replace("%(preds)s", "%(absent)s")]
                if item["present"]:
                    where.append(has_sql.replace("%(preds)s", "%(present)s"))
                cursor.execute(
                    f"SELECT count(*), min(n.first_seen), max(n.first_seen), "
                    f"       (SELECT count(*) FROM ({node_sql}) c) "
                    f"FROM ({node_sql}) n WHERE " + " AND ".join(where), params)
                count, oldest, newest, examined = cursor.fetchone()
                complete = (examined or 0) < scan_limit
                row.update({
                    "count": int(count or 0),
                    "examined": int(examined or 0),
                    # EXACT only when the budget came back short, because then the scan WAS
                    # every node of the type.
                    "count_kind": "exact" if complete else "sample",
                    "sample_note": None if complete else SAMPLE_NOT_AGE_ORDERED,
                    "oldest": oldest.isoformat() if oldest else None,
                    "newest": newest.isoformat() if newest else None,
                    "absence": (None if count else
                                ("truly_none" if complete else "not_exhaustive")),
                })
                out.append(row)
    finally:
        connection.rollback()
        connection.close()
    return out
