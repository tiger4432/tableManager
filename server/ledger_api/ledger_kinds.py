# -*- coding: utf-8 -*-
"""`GET /api/ledger/kinds` — the catalogue the console's kind picker is built from.

🔴 THIS MODULE DECLARES NOTHING. `server/finding_kinds.py` is the registry; this file
only READS it and attaches what only the database can answer (how many observations
exist, how many runs look for them). A second list of kinds here would be the exact
drift `finding_kinds`'s docstring exists to prevent — and it would be invisible, because
both lists would agree on the day it was written.

WHAT THE CONSOLE NEEDS, AND WHY EACH FIELD IS SERVED RATHER THAN DERIVED
------------------------------------------------------------------------
`has_denominator`
    🔴 SERVED, NOT COMPUTED BY THE CLIENT. A kind with no declared `observed_by`
    method has no `inspection_run` population to divide by, and the honest answer is
    「분모 없음 — 대조 불가」. `observed_by.length > 0` happens to be the rule TODAY;
    the day a kind's denominator becomes conditional on something else (a method that
    exists but is not systematic, say), a client computing it from a list length would
    keep answering the old rule with a straight face. The registry answers; the screen
    renders.

`atoms`
    Coverage: does this kind have data at all. 🔴 `null` is NOT `0` — `null` means
    nobody measured (the relation is absent, or the count was too expensive to pay for
    this request), and `0` means it was counted and there is nothing. The client
    renders a `null` as no number and a `0` as「0」, which are two different sentences
    to an operator deciding whether the console is broken or the kind is simply empty.

`runs`
    The size of the denominator population. `null` for a kind with no methods: there is
    no query to run, and 0 there would be arithmetic dressed as a measurement.

`classes`
    The kind's OWN closed class set (`MI_LEDGER_SCHEMA_PROPOSAL` §6-quater: 계면/벌크/
    에지 for a void, add-only, declared per kind). Empty is a fact about the kind, not a
    missing feature, and it renders as no class axis at all.

`in_ledger` / `ledger_state` / `ledger_atoms`  🔴 ruling R-2026-08-14-D
    THREE FIELDS BECAUSE THERE ARE THREE DIFFERENT QUESTIONS, and the structure census
    that produced this ruling is what proved they are different: every kind came back
    `in_ledger: false` while 91,756 voids sat in a source table, and one boolean could not
    say whether that meant "nobody translates this", "somebody translates it and has not
    run yet" or "it is translated and flowing".

      `in_ledger`    A DECLARATION fact: some `ledger_config.json` source declares this
                     kind and translates it under `ledger_predicate`. Costs no query, and
                     is answerable on a box with no ledger table at all.
      `ledger_state` The MEASURED half, in `GET /api/ledger/structure`'s own five words:
                     `absent` (nothing declares it), `declared_only` (declared, counted,
                     zero atoms — the backfill has not run), `flowing` (atoms exist),
                     `unmeasured` (the ledger relation is absent, or is too large to count
                     for a page-load request).
      `ledger_atoms` The count itself, `null` when unmeasured. Same `null`-is-not-`0` rule
                     as `atoms` above, one relation over.

    The linkage is DERIVED from the translator declarations rather than asserted here.
    Declaring a new observation source is therefore the whole of putting a kind in the
    ledger, and no list in this file has to be remembered.

🔴 A KIND WITH ZERO OBSERVATIONS IS LISTED. Dropping it would leave the operator unable
to learn that the kind exists — they would read「이 시스템은 박리를 모른다」off a screen
that merely had no delamination rows. Declared-and-empty and undeclared are different
answers and this endpoint gives both.

[SCALE — every query is bounded by something other than observation count]
* existence   `to_regclass`, a catalogue lookup that returns NULL instead of raising, so
              an undeployed relation never poisons the request's transaction.
* size        `pg_relation_size`, a filesystem stat.
* `atoms`     `count(*)` ONLY when the relation's on-disk size is under
              `EXACT_COUNT_MAX_BYTES`; above it, `pg_class.reltuples` and
              `atoms_exact: false`. A 10M-row observation table is the case this gate
              exists for: the picker is fetched on every page load and may not buy a
              sequential scan with it. The same rule `GET /coverage` already applies to
              the ledger's own atom count, applied to the source tables.
* `runs`      one grouped count over `inspection_run` filtered to the declared methods,
              under the same size gate, for every kind at once (not one query per kind).
"""
from __future__ import annotations

import logging

from ledger_api import finding_kinds
from ledger_trace import _fetch, relation_exists

logger = logging.getLogger(__name__)

#: Above this on-disk size, `count(*)` is refused and the catalogue's estimate is served
#: with `atoms_exact: false`. 256 MB is roughly 2-3M rows of an observation table on this
#: schema — comfortably past anything a page-load request should scan, and far below the
#: 10M-row target this project sizes for.
EXACT_COUNT_MAX_BYTES = 256 * 1024 * 1024

#: The three worlds, in `GET /api/ledger/coverage`'s vocabulary. One word means one thing
#: across both endpoints, so the console can reuse its reading.
STATE_ABSENT = "absent"    # no kind's observation relation exists — migration not run
STATE_EMPTY = "empty"      # relations exist and hold nothing — backfill not run
STATE_READY = "ready"      # at least one kind has observations

#: The ledger itself, for the per-kind translation linkage. Named rather than inlined for
#: the reason `ledger_trace_router` names it: it is the seam a materialised projection
#: would repoint.
LEDGER_RELATION = "ledger_events"

#: Per-kind ledger state, in `GET /api/ledger/structure`'s words. One vocabulary across
#: the ledger endpoints — see the module docstring for what each one answers.
LEDGER_STATE_ABSENT = "absent"
LEDGER_STATE_DECLARED_ONLY = "declared_only"
LEDGER_STATE_FLOWING = "flowing"
LEDGER_STATE_UNMEASURED = "unmeasured"


def _relation_facts(connection, relation):
    """`(exists, size_bytes, reltuples)` for one relation, from the catalogue only.

    Asked BEFORE any query against the relation, for the reason `relation_exists`
    states: one `UndefinedTable` poisons the transaction and every later statement in
    this request fails for an unrelated-looking reason.
    """
    if not relation_exists(connection, relation):
        return False, None, None
    rows = _fetch(connection,
                  "SELECT pg_relation_size(c.oid), c.reltuples "
                  "FROM pg_class c WHERE c.oid = to_regclass(%(rel)s)",
                  {"rel": relation})
    if not rows:
        return False, None, None
    size, reltuples = rows[0][0], rows[0][1]
    return True, (int(size) if size is not None else None), (
        float(reltuples) if reltuples is not None else None)


def _estimate(reltuples):
    """`reltuples` as a count, or None. Negative means never analysed (PG >= 14) and is
    NOT zero — reporting it as 0 is how a full table gets confidently called empty."""
    if reltuples is None or reltuples < 0:
        return None
    return int(reltuples)


def _count(connection, relation, size, reltuples):
    """`(count, exact)` under the size gate. `(None, False)` when nothing is knowable."""
    if size is not None and size <= EXACT_COUNT_MAX_BYTES:
        rows = _fetch(connection, f"SELECT count(*) FROM {relation}")
        return (int(rows[0][0]) if rows else None), True
    estimate = _estimate(reltuples)
    if estimate is None:
        logger.warning("kind catalogue: %s is %s bytes and has no usable statistics; "
                       "atoms reported as null rather than as a zero", relation, size)
    return estimate, False


def _run_counts(connection, methods):
    """`{method: run count}`, one query for every kind's methods at once.

    Returns `{}` when the run relation is absent or too large to count, and the caller
    turns that into `runs: null` — never into a zero.
    """
    if not methods:
        return {}
    exists, size, _reltuples = _relation_facts(connection, finding_kinds.RUN_TABLE)
    if not exists:
        return {}
    if size is not None and size > EXACT_COUNT_MAX_BYTES:
        # A per-method estimate does not exist in the catalogue (`reltuples` is
        # whole-relation), and inventing one by proportion would be a number nobody
        # measured. The denominator's SIZE is unavailable; `has_denominator` — whether
        # one exists at all — is a declaration and is unaffected.
        logger.info("kind catalogue: %s is %s bytes; run counts omitted",
                    finding_kinds.RUN_TABLE, size)
        return {}
    rows = _fetch(connection,
                  f"SELECT method, count(*) FROM {finding_kinds.RUN_TABLE} "
                  f"WHERE method = ANY(%(methods)s) GROUP BY method",
                  {"methods": list(methods)})
    return {row[0]: int(row[1]) for row in rows}


def _declared_translations():
    """`{finding_kind: {"source": ..., "predicate": ...}}` from `ledger_config.json`.

    🔴 THE IMPORT IS LAZY, AND THAT IS A DEPLOYMENT GUARANTEE RATHER THAN A STYLE CHOICE.
    `LEDGER_GUIDE` §0 promises that nothing on the web server's boot path imports
    `server/ledger` — the translator package can be absent, broken or mid-edit and the
    server still starts. This module IS on that path (`ledger_trace_router` imports it), so
    the import stays inside the call and an unreadable declaration degrades to "no kind is
    declared" with a warning, never to a failed boot.
    """
    try:
        from ledger import config as ledger_config
        cfg = ledger_config.load()
        observation = ledger_config.SOURCE_KIND_OBSERVATION
        predicate = ledger_config.OBSERVATION_PREDICATE
    except Exception as exc:
        logger.warning("kind catalogue: translator declarations unreadable (%s); every "
                       "kind reports in_ledger=false", exc)
        return {}
    found = {}
    for name, source in (cfg.get("sources") or {}).items():
        if not isinstance(source, dict) or source.get("kind") != observation:
            continue
        kind = str(source.get("finding_kind") or "").strip()
        if kind:
            found[kind] = {"source": name, "predicate": predicate}
    return found


def _partitioned_bytes(connection, relation):
    """On-disk size of a PARTITIONED relation. A filesystem stat per partition.

    🔴 `pg_relation_size` on the parent of a partitioned table is ZERO — the rows live in
    the children — so the obvious one-liner would report a 39 MB ledger as 0 bytes and let
    every size gate through. Returns `None` when the relation does not exist.
    """
    rows = _fetch(connection, """
        SELECT coalesce(sum(pg_relation_size(c.oid)), 0)
        FROM pg_class parent
        JOIN pg_inherits i ON i.inhparent = parent.oid
        JOIN pg_class c ON c.oid = i.inhrelid
        WHERE parent.oid = to_regclass(%(rel)s)
    """, {"rel": relation})
    if not rows:
        return None
    return int(rows[0][0] or 0)


def _ledger_atoms_by_source(connection, predicates):
    """`{source_who: atoms}` for the given predicates, or `None` when nothing was counted.

    ONE grouped query for every kind at once, and it is GATED: a `GROUP BY source_who` over
    `ledger_events` has no index to ride (the type-level census pays the same price and
    says so), so above `EXACT_COUNT_MAX_BYTES` this returns `None` and every kind reports
    `unmeasured` rather than making a page load buy a 10-million-row scan.

    `None` and `{}` are different answers and both are used: `None` is "nobody counted",
    `{}` is "counted, and this predicate has written nothing anywhere".
    """
    if not predicates:
        return {}
    if not relation_exists(connection, LEDGER_RELATION):
        return None
    size = _partitioned_bytes(connection, LEDGER_RELATION)
    if size is not None and size > EXACT_COUNT_MAX_BYTES:
        logger.info("kind catalogue: %s is %s bytes; per-kind atom counts omitted",
                    LEDGER_RELATION, size)
        return None
    rows = _fetch(connection,
                  f"SELECT source_who, count(*) FROM {LEDGER_RELATION} "
                  f"WHERE predicate = ANY(%(predicates)s) GROUP BY source_who",
                  {"predicates": sorted(set(predicates))})
    return {row[0]: int(row[1]) for row in rows}


def catalog(connection):
    """Every declared finding kind, with its coverage. Read-only, one page-load call.

    Raises only `finding_kinds.FindingKindError` — a registry that cannot be read is a
    deployment fact and the route answers it as one. An absent or empty set of
    observation relations is an ANSWER here (`state`), never an error, exactly as it is
    for `GET /coverage`.
    """
    registry = finding_kinds.load()
    names = finding_kinds.kinds()

    wanted_methods = set()
    for name in names:
        wanted_methods.update(finding_kinds.methods(name))
    runs_by_method = _run_counts(connection, sorted(wanted_methods))
    runs_known = bool(runs_by_method) or not wanted_methods

    translations = _declared_translations()
    ledger_atoms = _ledger_atoms_by_source(
        connection, {t["predicate"] for t in translations.values()})

    rows, any_relation, any_atom = [], False, False
    for name in names:
        spec = registry[name]
        relation = finding_kinds.observation_table(name)
        exists, size, reltuples = _relation_facts(connection, relation)
        atoms, exact = (None, False)
        if exists:
            any_relation = True
            atoms, exact = _count(connection, relation, size, reltuples)
            if atoms:
                any_atom = True
        methods = finding_kinds.methods(name)
        has_denominator = finding_kinds.has_denominator(name)
        # 🔴 `runs` is null for a kind with no methods — there is no population to
        # count, and a 0 would read as "the scan exists and nobody ran it".
        runs = None
        if methods and runs_known:
            runs = sum(runs_by_method.get(m, 0) for m in methods)
        translation = translations.get(name)
        rows.append({
            "kind": name,
            "label": str(spec.get("label") or name),
            "atoms": atoms,
            "atoms_exact": exact,
            "runs": runs,
            "observed_by": methods,
            "has_denominator": has_denominator,
            "classes": finding_kinds.classes(name),
            "observation_table": relation,
            # The ledger linkage — see the module docstring for why it is three fields.
            "in_ledger": translation is not None,
            "ledger_source": (translation or {}).get("source"),
            "ledger_predicate": (translation or {}).get("predicate"),
            **_ledger_position(translation, ledger_atoms),
        })

    if not any_relation:
        state = STATE_ABSENT
    elif any_atom:
        state = STATE_READY
    else:
        state = STATE_EMPTY
    return {"state": state, "default": _default_kind(names), "kinds": rows}


def _ledger_position(translation, ledger_atoms):
    """`{ledger_state, ledger_atoms}` for one kind. The four words, decided in one place.

    🔴 `declared_only` vs `unmeasured` is the distinction this project has already paid for
    once (`absent-zero-is-not-inert-zero`): a kind whose translator has never run and a
    kind nobody counted are different sentences to an operator deciding whether to run a
    backfill or to go and look at the deployment.
    """
    if translation is None:
        return {"ledger_state": LEDGER_STATE_ABSENT, "ledger_atoms": None}
    if ledger_atoms is None:
        return {"ledger_state": LEDGER_STATE_UNMEASURED, "ledger_atoms": None}
    written = int(ledger_atoms.get(translation["source"], 0))
    return {
        "ledger_state": (LEDGER_STATE_FLOWING if written
                         else LEDGER_STATE_DECLARED_ONLY),
        "ledger_atoms": written,
    }


def _default_kind(names):
    """The kind the console opens on: the registry's default WHEN IT IS DECLARED.

    🔴 THE FIRST DECLARED KIND, AND NOTHING ELSE. This used to prefer a code constant
    (`finding_kinds.DEFAULT_KIND`) when the registry happened to declare it; that constant
    is gone, and with it the last way a site that declares neither of the two old names
    could be sent a default the very next request refuses by name (`spec()` never falls
    back — that is its whole point). The registry answers, not this file.
    """
    return names[0] if names else ""
