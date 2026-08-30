# -*- coding: utf-8 -*-
"""Where the declaration says a link should be and the ledger has none.

🔴 THIS MODULE NAMES NOTHING. `task/APPLICATION_GAP_SPEC.md` named every gap and gave each
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
            + ". Name them in task/APPLICATION_GAP_SPEC.md and add the rows to "
              "gap_names.json - do not name them here.")
