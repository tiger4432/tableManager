# -*- coding: utf-8 -*-
"""What the PRODUCT contributes to the chain: synthesised rules, and the kinds that run them.

🔴 ONE SYNTHESIS SEAT (판정 304). `load_chain_rules` calls `synthesize_chain_rules` and
nothing else, and that function calls each half. 판정 292 forbids two synthesisers; putting
the join half inside `load_enrichment_chain_rules` would have satisfied the letter of that
while making a function named `enrichment_…` read the virtual-join file — a name that lies is
a cost paid by whoever next looks for where a declaration becomes a chain rule. Each half
keeps an honest name and reads its own file; the SEAT is what is singular.

🔴 ONE TABLE OF `builtin:` KINDS (판정 305). Measured before building: `builtin:auto_confirm`
appeared exactly twice, both in `enrichment_config`, and NOTHING read it — S-179 declared the
kind for the loader and graph layers and left execution in the auto-confirm sweep. So this is
the FIRST dispatcher the `builtin:` vocabulary has ever had.

🔵 AND THE TEMPORARY IS OVER (S-195). It carried one kind while auto-confirm still ran from
its own sweep, so a follow-up kind had two ways to run; both are in the table now and there is
one route. What made that survivable in between was that it was WRITTEN DOWN and queued — a
temporary nobody records is just a drift with a date on it.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("Chain.Builtins")


def synthesize_chain_rules(known_tables: dict = None) -> list:
    """Every chain rule the product derives from a declaration the operator wrote.

    ⚠️ THE ENRICHMENT HALF IS UNCHANGED, BYTE FOR BYTE. This seat only moved its CALL; a
    test compares the list before and against after, because a move that quietly reorders or
    drops a rule would be invisible until a chain stopped firing.
    """
    import enrichment.config
    import virtual_join.config

    rules = list(enrichment.config.load_enrichment_chain_rules(known_tables=known_tables))
    rules.extend(virtual_join.config.synthesized_join_chain_rules(known_tables=known_tables))
    return rules


def synthesized_kind_counts(rules) -> dict:
    """How many of each synthesised kind, for the boot line (판정 304).

    🔴 THE LINE SAYS WHICH KINDS, not just how many. 「N synthesized」 over three kinds is the
    shape that reported 8 of a kind there were 4 of, which is why S-179 ① split its own
    count in the first place.
    """
    import enrichment.config
    import virtual_join.config

    counts = {"dedup": 0, "auto_confirm": 0, "join": 0}
    for rule in rules or ():
        name = str(rule.get("name") or "")
        if name.startswith(virtual_join.config.JOIN_PREFIX):
            counts["join"] += 1
        elif name.startswith(enrichment.config.AUTO_CONFIRM_PREFIX):
            counts["auto_confirm"] += 1
        elif name.startswith(enrichment.config.DEDUP_PREFIX):
            counts["dedup"] += 1
    return counts


# ---------------------------------------------------------------------------
# the `builtin:` table
# ---------------------------------------------------------------------------

class UnknownBuiltinKind(ValueError):
    """⛔ REFUSED BY NAME, NEVER IGNORED. A rule naming a kind nothing implements would
    otherwise sit enabled, look live, and never run — the same silence
    `_report_unwatchable_trigger_columns` exists to break for a mistyped trigger column."""


def _run_join(db, rule, row_ids=None, key_values=None):
    """`builtin:join` — materialise one join rule's answer onto its target rows.

    ⚠️ TWO TRIGGERS, ONE KIND. Target rows moved (cheap, no ceiling) or a reference row moved
    (counts first, refuses over the rule's declared ceiling). The caller says which by which
    argument it passes; both land in the same declaration.
    """
    from virtual_join import executor as vje

    joined = (rule or {}).get("params") or {}
    if key_values is not None:
        return vje.on_reference_rows_changed(db, joined, list(key_values))
    return vje.on_target_rows_changed(db, joined, list(row_ids or ()))


def _run_auto_confirm(db, rule, row_ids=None, done=None, **_):
    """`builtin:auto_confirm` — the enrichment sweep, now reached through the table (S-195).

    🔴 THE WORK IS UNCHANGED; WHAT MOVED IS HOW IT IS FOUND. It ran from
    `_auto_confirm_followed_rows`, called directly on the drain beside this dispatcher — so a
    `follow_up` kind had TWO ways to run and the prohibition on that was carrying a named
    temporary. This closes it: one table, one route.

    🔴 AND THE RULE COMES FROM THE DECLARATION, NOT FROM A SECOND LOOKUP.
    `AutoConfirmCollector` already accepted `rules`; left to itself it called
    `load_enrichment_rules` and re-found what the synthesised rule is already carrying in
    `params`. Two readers of one fact is how they come to disagree — and here the second one
    also re-read a file on a paced path.

    ⚠️ `.active` STILL DECIDES. The global switch, the per-rule knob and 「does any reference
    view declare `candidate_for`」 are the collector's gates and stay there; this seat only
    hands it the rule it was already going to use.

    ⚠️ CONTAINED. A failure here must not cost the ledger follow-up that already succeeded.
    """
    import enrichment.candidates

    table = (done or {}).get("table")
    rows = list(row_ids or ())
    if not table or not rows:
        return {"confirmed": 0, "refused": 0}

    declared = (rule or {}).get("params") or None
    collector = enrichment.candidates.AutoConfirmCollector(
        table, rules=[declared] if isinstance(declared, dict) else None)
    if not collector.active:
        return {"confirmed": 0, "refused": 0}

    collector.collect_rows(db, rows)
    stats = collector.flush(db) or {}
    confirmed = stats.get("confirmed") or 0
    refused = sum((stats.get("refused") or {}).values())
    if done is not None:
        # Values, not a verdict: 「큰 깊이는 값으로 보임」 — a follow-up that confirms nothing
        # and one that never ran are different facts, and the note carries both. The drain
        # loop reads these two keys, so they keep their names.
        done["auto_confirmed"] = confirmed
        done["auto_refused"] = refused
    return {"confirmed": confirmed, "refused": refused,
            "source_name": enrichment.candidates.SOURCE_NAME}


#: kind -> callable. One table, the registry's posture: a name, a callable, nothing implicit.
BUILTIN_KINDS = {}


def register_builtin(kind: str, fn):
    existing = BUILTIN_KINDS.get(kind)
    if existing is not None and existing is not fn:
        raise UnknownBuiltinKind(
            "two implementations claim %r; a rule naming it could not say which it meant"
            % kind)
    BUILTIN_KINDS[kind] = fn
    return fn


def run_builtin(kind: str, db, rule, **kwargs):
    """Route one synthesised rule to its implementation, or refuse by name."""
    fn = BUILTIN_KINDS.get(kind)
    if fn is None:
        raise UnknownBuiltinKind(
            "no implementation for %r; known kinds: %s"
            % (kind, ", ".join(sorted(BUILTIN_KINDS)) or "none"))
    return fn(db, rule, **kwargs)


def _install():
    import enrichment.config
    import virtual_join.config
    from chain import join_into

    register_builtin(virtual_join.config.JOIN_MAPPER, _run_join)
    # 🔴 [S-237] THE UNIFIED DECLARATION'S `join` KIND, AND IT IS A DIFFERENT ENTRY ON
    # PURPOSE. `builtin:join` is the READ-TIME join and production runs on it; this one
    # WRITES what the declaration says into a column. `register_builtin` refuses two
    # claimants of one id by name, so the distinction is enforced here rather than trusted.
    register_builtin(join_into.JOIN_INTO_MAPPER, join_into.run)
    # S-195: the kind S-179 declared finally has an implementation, so the table carries the
    # whole `builtin:` vocabulary and the named temporary two-path condition is over.
    register_builtin(enrichment.config.AUTO_CONFIRM_MAPPER, _run_auto_confirm)


_install()
