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

⚠️ AND IT CARRIES ONE KIND TODAY, WHICH IS A NAMED TEMPORARY. Auto-confirm still runs from
its sweep, so a follow-up kind runs two ways until S-195 moves it here — gated on S-151's
measured 0.875 s per group not regressing. That is written down here and queued rather than
left to be discovered, which is the whole difference between a temporary and a drift.
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
    import enrichment_config
    import virtual_join_config

    rules = list(enrichment_config.load_enrichment_chain_rules(known_tables=known_tables))
    rules.extend(virtual_join_config.synthesized_join_chain_rules(known_tables=known_tables))
    return rules


def synthesized_kind_counts(rules) -> dict:
    """How many of each synthesised kind, for the boot line (판정 304).

    🔴 THE LINE SAYS WHICH KINDS, not just how many. 「N synthesized」 over three kinds is the
    shape that reported 8 of a kind there were 4 of, which is why S-179 ① split its own
    count in the first place.
    """
    import enrichment_config
    import virtual_join_config

    counts = {"dedup": 0, "auto_confirm": 0, "join": 0}
    for rule in rules or ():
        name = str(rule.get("name") or "")
        if name.startswith(virtual_join_config.JOIN_PREFIX):
            counts["join"] += 1
        elif name.startswith(enrichment_config.AUTO_CONFIRM_PREFIX):
            counts["auto_confirm"] += 1
        elif name.startswith(enrichment_config.DEDUP_PREFIX):
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
    import virtual_join_executor as vje

    joined = (rule or {}).get("params") or {}
    if key_values is not None:
        return vje.on_reference_rows_changed(db, joined, list(key_values))
    return vje.on_target_rows_changed(db, joined, list(row_ids or ()))


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
    import virtual_join_config

    register_builtin(virtual_join_config.JOIN_MAPPER, _run_join)


_install()
