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


def ensure_declared_unique_keys(db, rules) -> dict:
    """[S-240] Make the unique key a unified join DECLARED, at load time. Returns a report.

    🔴 THE CELL WAS WRITTEN AND READ BY NOBODY. `key.unique: true` never survived the
    translation (`rule_shape` dropped it), and the only place that builds a `uq_vjoin_*` is
    the OLD read-time shell - so the plan's 「선언이 key.unique 라고 말하면 제품이
    성립시킨다」 and RUN.md's 「제품이 인덱스를 세웁니다」 were both false for a unified join.

    ⚠️ THE SHELL CALLS IT, NOT `join_into`. That module must not import `virtual_join` -
    a boundary its own test asserts - so it hands back the right table, its columns and the
    folds, and this seat, which already knows both halves, does the building.

    ⛔ LOAD TIME, NEVER THE READ PATH (§0-ter ①), and `enabled: false` means ZERO calls
    (판정 399 ③′): a switch that still probes is the defect that took the read path down
    on 2026-09-14.
    """
    from virtual_join import config as vjc
    from virtual_join import unique_key

    report = {"ensured": [], "skipped": []}
    seen = set()
    for name, table, columns, folds, skip in declared_unique_targets(rules):
        if skip:
            report["skipped"].append((name, skip))
            continue
        # ⚠️ ONE DECLARATION STANDS TWO RULES AND NEEDS ONE INDEX. The target half and
        # its `:reference` companion join the same two tables on the same key, so they ask
        # for the SAME index name - asking twice would probe `pg_index` twice at every
        # reload and report one index as two.
        index_name = vjc.required_index_name(table, columns, folds)
        if index_name in seen:
            continue
        seen.add(index_name)
        report["ensured"].append(
            (name, unique_key.ensure_once(db, name, table, columns, folds)))
    return report


def declared_unique_targets(rules):
    """(name, right table, columns, folds, skip reason) per unified join that DECLARED one.

    🔴 ONE WALKER, BECAUSE THEY ARE ONE QUESTION. 「which index do we build」 and
    「which index do we require」 must never be able to disagree - the day they do, the
    product builds an index at warmup and retracts it on the next read, forever.
    """
    from chain import join_into

    for rule in rules or ():
        if not isinstance(rule, dict):
            continue
        if rule.get("mapper") != join_into.JOIN_INTO_MAPPER:
            continue
        name = rule.get("name")
        if not rule.get("enabled", True):
            yield (name, None, None, None, "enabled=false")
            continue
        if not (rule.get("key") or {}).get("unique"):
            # ⚠️ ABSENT IS NOT 「no」 TO A QUESTION NOBODY ASKED. A declaration that says
            # nothing about uniqueness gets no index and no complaint; `join_into`'s own
            # row-level net still refuses a left row with two right answers.
            continue
        table, columns, folds = join_into.right_key(rule)
        if not table or not columns:
            yield (name, None, None, None, "no right key to cover")
            continue
        # ⚠️ `key.columns` IS A CHECK, NOT A CHOICE. The index has to be built over the
        # join's OWN right key or PostgreSQL will not use it (S-181) - so a list that names
        # other columns cannot be honoured, and honouring it silently would build an index
        # that covers nothing this join compares. It is read so that a typo is a sentence
        # rather than a cell nobody looks at, which is the whole defect of this round.
        declared = [str(column) for column in
                    ((rule.get("key") or {}).get("columns") or ()) if column]
        if declared and declared != list(columns):
            yield (name, table, columns, folds,
                   "key.columns %s is not this join's right key %s — the index covers "
                   "the right key" % (declared, list(columns)))
            continue
        yield (name, table, columns, folds, None)


def declared_unique_index_names(known_tables: dict = None) -> set:
    """Every `uq_vjoin_*` name the LIVE unified declarations require (S-240 · S-248).

    🔴 AN INDEX LIVES EXACTLY AS LONG AS THE JOIN THAT REQUIRES IT - and after S-240
    there are TWO kinds of join that require one. The retraction that enforces that lifetime
    computes 「required」 from the read-time declarations alone, so without this the index
    THIS module builds at warmup is dropped by the next read-path load, rebuilt at the next
    restart, and dropped again: a switch flapping on its own.

    ⚠️ THE DECLARATION IS EXPANDED BY THE SAME JUDGE THE LOADER USES (S-244). A second
    reading of the file would be a second answer to 「what does this declaration stand」,
    and this one has to agree with the seat that built the index.
    """
    from chain import ingestion_worker, rule_shape
    from database import crud
    from virtual_join import config as vjc

    catalogue = known_tables if known_tables is not None else crud.TABLE_CONFIG
    names = set()
    for raw in ingestion_worker.read_rules_document()["rules"] or ():
        stood, refusal, _notes = rule_shape.expand_declaration(raw, catalogue)
        if refusal:
            # ⚠️ The loader already says this out loud; saying it again here would put a
            # refusal on the read path every few seconds - the flood 2026-09-14 was.
            continue
        for _name, table, columns, folds, skip in declared_unique_targets(stood):
            if skip:
                continue
            names.add(vjc.required_index_name(table, columns, folds))
    return names


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
