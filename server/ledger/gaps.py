# -*- coding: utf-8 -*-
"""Where the declaration says a link should be and the ledger has none.

🔴 THIS MODULE NAMES NOTHING. `docs/spec/APPLICATION_GAP_SPEC.md` named every gap and gave each
an action and an owner; `gap_names.json` is that table in machine-readable form, and this
file looks names UP. A label written here would be a second authority, and the first one
would go stale without anybody noticing.

🔴 AND IT BRANCHES ON NO DOMAIN WORD. What it computes comes from the declaration - which
objects are nodes, which predicate names a type its only way into existence - and what it
CALLS things comes from the table. Neither is a literal in this file.

🔴 THE TWO ARE CHECKED AGAINST EACH OTHER IN BOTH DIRECTIONS, and that is the brief's S1
made into code rather than a note. A question the declaration can ask and the table has no
name for would otherwise be reported under a neighbour's name; a table row whose predicate
the declaration no longer has would quietly stop being asked. Either way somebody reads a
screen that is missing something and looks complete.
"""
from __future__ import annotations

import json
from pathlib import Path

#: Ruled by the spec §1 exclusion ③ and not derivable from the declaration: the predicate
#: whose ABSENCE is the good outcome - a die with no defect is a good die. Cited here, not
#: decided here; this is the only predicate named in this file.
SPEC_EXCLUDED = ("observed@1",)

NAMES_PATH = Path(__file__).with_name("gap_names.json")


class GapTableMismatch(ValueError):
    """The declaration and the name table disagree. Raised instead of guessing.

    The brief's S1: "코드에서 이름을 지어내지 마십시오". A detector that filled the gap
    itself would answer confidently and wrongly, and the wrong answer looks exactly like
    the right one.
    """


def _bare(name):
    """`of_kind@1` -> `of_kind`. The table writes predicates bare and the declaration
    versions them; the version belongs to the declaration, not to the name."""
    return str(name).split("@")[0]


def load_names(path=None):
    return json.loads(Path(path or NAMES_PATH).read_text(encoding="utf-8"))


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


def questions(declaration, names=None):
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

    def declared(bare_predicate, where):
        full = by_bare.get(bare_predicate)
        if full is None:
            raise GapTableMismatch(
                f"{where}: the table names predicate '{bare_predicate}', which the "
                f"declaration does not have. Either the declaration retired it and the "
                f"table still asks for it, or it is a typo - both make a question that "
                f"can never be answered.")
        return full

    out = []
    for row in names.get("pairs", []):
        entity_type = row["type"]
        side_a = [declared(p, f"pairs[{entity_type}].side_a") for p in row["side_a"]]
        side_b = [declared(p, f"pairs[{entity_type}].side_b") for p in row["side_b"]]
        out.append({"form": "pair", "type": entity_type,
                    "present": side_a, "absent": side_b,
                    "name": row["a_only"], "meaning": row["a_only_meaning"],
                    "vacuous": False})
        out.append({"form": "pair", "type": entity_type,
                    "present": side_b, "absent": side_a,
                    "name": row["b_only"], "meaning": row["b_only_meaning"],
                    "vacuous": False})

    for row in names.get("subject_sides", []):
        predicate = declared(row["predicate"], "subject_sides")
        out.append({"form": "subject_side", "type": row["type"],
                    "present": [], "absent": [predicate],
                    "name": row["name"], "action": row["action"],
                    "vacuous": (row["predicate"], row["type"]) in vacuous})

    for row in names.get("object_sides", []):
        predicate = declared(row["predicate"], "object_sides")
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

    _refuse_unnamed(declaration, live, out)
    return out


def _refuse_unnamed(declaration, live, named):
    """🔴 The other direction of S1: a question the declaration can ask and nobody named.

    Without this the detector silently answers a smaller question than the declaration
    asks, and the screen looks complete while a whole kind of gap is invisible. It is the
    direction that cannot be noticed by reading the output, which is why it is a refusal
    rather than a log line.
    """
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
                missing.append(f"subject side of {name} on {entity_type}")
        for entity_type in targets:
            if (_bare(name), entity_type) in vacuous:
                continue
            if not any(entity_type == item_type and name in absent
                       for item_type, absent in covered):
                missing.append(f"object side of {name} on {entity_type}")
    if missing:
        raise GapTableMismatch(
            "the declaration asks questions the spec has not named: "
            + "; ".join(sorted(set(missing)))
            + ". Name them in docs/spec/APPLICATION_GAP_SPEC.md and add the rows to "
              "gap_names.json - do not name them here.")


#: How many distinct nodes one question examines before it calls itself a sample. Small on
#: purpose: this is a request path, and the cost measured on 2026-08-31 for a single
#: unbounded anti-join was 26.20 seconds. The budget is what makes twenty questions
#: answerable at all, and `count_kind` is what stops the answer pretending otherwise.
NODE_SCAN_LIMIT = 200

#: 🔴 THE SAMPLE IS NOT THE OLDEST N, AND SAYS SO. Choosing the oldest would mean ordering
#: every node of the type by age first, which is the full scan the budget exists to avoid.
#: The rows that come back DO carry their age and are shown oldest-first among themselves,
#: but the SET was chosen by whatever the scan met first. Letting "first found" read as
#: "oldest" is the misreading this whole vocabulary exists to prevent, so the wording is
#: part of the answer rather than a caveat somewhere else.
SAMPLE_NOT_AGE_ORDERED = (
    "표본은 «먼저 만난» 노드들입니다 — «가장 오래된» 것들이 아닙니다. "
    "나이순으로 고르려면 그 타입 전체를 한 번 훑어야 하고, 그게 이 예산이 피하는 그 비용입니다. "
    "돌아온 것들끼리는 오래된 순으로 보여 드립니다.")


def _nodes_of_type_sql():
    """Nodes of one type, from BOTH sides, with the moment each was first named.

    🔴 SUBJECT *AND* OBJECT, because a node is not stored - it is derived from an atom's
    keys - so it begins to exist the moment any atom names it, on either side. Measured on
    this box: `defect_kind@1` and `recipe@1` have ZERO atoms of their own and appear only
    as objects, so a subject-only enumeration would report them as having no members at
    all rather than as having no age.
    """
    return """
        SELECT keys, min(occurred_at) AS first_seen FROM (
            SELECT subject_keys AS keys, occurred_at
              FROM {table} WHERE subject_type = %(bare)s
            UNION ALL
            SELECT object_payload->'keys' AS keys, occurred_at
              FROM {table}
             WHERE object_kind = 'entity_ref' AND object_payload->>'type' = %(bare)s
        ) named GROUP BY keys LIMIT %(scan)s
    """


def _has_predicate_sql():
    """One expression for "this node has that predicate", whichever side it is on.

    🔴 NO BRANCH ON DIRECTION. A subject-side question asks about a predicate the node
    should have gone OUT on, a pair asks about one that should have come IN, and both are
    the same question about the same node: does an atom of that predicate name it? Writing
    two expressions would mean deciding, per question, which one applies - a branch on the
    shape of the declaration, and a place for the two to drift apart.
    """
    return """
        EXISTS (
            SELECT 1 FROM {table} e
             WHERE e.predicate = ANY(%(preds)s)
               AND ((e.subject_type = %(bare)s AND e.subject_keys = n.keys)
                 OR (e.object_kind = 'entity_ref'
                     AND e.object_payload->>'type' = %(bare)s
                     AND e.object_payload->'keys' = n.keys)))
    """


class GapQuestionUnknown(ValueError):
    """`only` named a question that is not in the table. Refused rather than answered empty.

    An empty result for a typo reads exactly like "this gap has no members", which is the
    good news an operator would act on by moving along.
    """


def measure(engine, declaration, names=None, scan_limit=NODE_SCAN_LIMIT, only=None):
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
    node_sql = _nodes_of_type_sql().replace("{table}", schema.LEDGER_TABLE)
    has_sql = _has_predicate_sql().replace("{table}", schema.LEDGER_TABLE)

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
