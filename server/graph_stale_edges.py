"""Stale edge sweep - the half of re-derivation that has to be able to REMOVE.

WHY THIS EXISTS
---------------
Re-derivation is supposed to be a CORRECTION. Today it is partly an
ACCUMULATION, and that is the single defect that makes "an ontology is hard to
change" actually true in this repository (board O2, ``docs/process/DESIGN_TRACKS.md``
section "목적별 작은 온톨로지"). The purpose-scoped ontology strategy rests on
"the ontology is derived, not authored, so fixing it means fixing rows or the
mapping and re-deriving" - and that argument collapses the moment the graph keeps
corpses.

Three edge populations survive re-derivation TODAY. Measured, not assumed:

  (A) **the owning row was deleted.** ``graph_materializer.materialize_events``
      counts DELETE events into ``skipped_deletes`` and does nothing else, and
      ``resync_table`` iterates rows that EXIST, so a deleted row's edges are
      never in any ``processed_refs`` scope again. ``_retarget_stale_edges``
      therefore never sees them.
  (B) **the table's whole mapping was retired.** ``resync_table`` returns an
      empty stat block when ``mappings.get(table) is None``, so retiring an
      ``exp:`` purpose ontology by deleting its declaration removes the producer
      and leaves every edge it ever produced. This is exactly why "discarding a
      purpose-scoped ontology" has no mechanism.
  (C) **a superseded ``source_name`` on a still-produced triple.** NOT swept
      here, and NOT silently ignored either - see ``report_superseded_source_edges``
      and the module-level note at the bottom of this docstring.

What re-derivation DOES already handle, and what this module therefore refuses to
second-guess: a **reachable** row of a **mapped** table. Retire an edge type,
rename a label, correct an identity - ``_retarget_stale_edges`` deletes the
triples that row no longer claims, because the row is visited again. Recomputing
the produced set here would make this module a second materializer, which is the
failure this repository has already paid for twice in coordinate transforms.

THE OWNERSHIP MODEL - what a derivation is allowed to delete
------------------------------------------------------------
``graph_edges.source_row_ref`` is the graph-side equivalent of ``cell_sources``:
it is the record of WHICH derivation minted this edge, written in exactly one
place (``graph_materializer.bulk_upsert_edges``, ``f"{table_name}:{row_id}"``) and
nowhere else. An edge is **derivation-owned** iff that string parses into a
``(table, row_id)`` pair. Ownership is never inferred from ``type``, from a label,
or from an endpoint - a sweep that deleted "everything of type X" would take
another purpose's edges with it.

Four verdicts, one per distinct ``source_row_ref``:

  ``live``          a mapped table still holds that row → re-derivation reaches it.
                    Never swept here, whatever the edge looks like.
  ``row_gone``      mapped table, row absent → population (A). SWEEPABLE.
  ``not_declared``  the table is registered but the current declaration does not
                    map it → population (B). SWEEPABLE.
  ``not_reached``   ownership could NOT be established. NEVER swept, always
                    reported with a count.

``row_gone`` is a verdict of staleness, not a synonym for one of the honest-failure
words: it is a positive determination made by asking the RDB. The inability words
are reused verbatim from ``config_resolve_report`` (``not_declared``,
``mapping_unavailable``, ``not_reached``) rather than respelled here.

WHAT CANNOT BE SAFELY SWEPT (``not_reached``, reported by name)
---------------------------------------------------------------
* ``source_row_ref`` NULL/empty, or without a ``:`` - nothing records who minted
  it. Could be a hand-authored edge, could be a pre-provenance write. "I do not
  know who owns this" is not "nobody owns it".
* the literal ``"<table>:None"`` - ``bulk_upsert_edges`` formats the ref with an
  f-string, so a payload carrying no ``row_id`` produced that string. Asking the
  RDB for a row called ``None`` returns "absent" and the edge would be swept on
  the strength of a question that was never about it.
* a table that is not in ``DYNAMIC_TABLES`` - this process cannot query it, and
  "not registered in this process" is indistinguishable from "the table was
  retired". Reading the first as the second is precisely the
  ``mapping_unavailable`` → ``not_declared`` confusion this vocabulary exists to
  prevent.

HUMAN-CONFIRMED CONTENT SURVIVES
--------------------------------
An edge whose ``source_name`` is ``crud.USER_SOURCE`` carries a person's
one-time judgement. The clearest case is the enrichment promotion: every
``RESOLVED_AS`` edge is minted with ``source_override: "user"`` precisely because
it is "사람 교정 결과" (``ontology_config.synthesize_enrichment_mappings``). Those
edges are **removed from the delete set and reported as protected**, even when
their owning row is gone.

The asymmetry is deliberate. For a machine-derived edge, "no row produces this any
more" is a complete argument. For a human-confirmed one it is not: what the sweep
would destroy is the thing the system exists to propagate, and re-deriving cannot
bring it back. A stale user edge costs a wrong neighbour in a trace; a swept one
costs a person's judgement. Same shape as ``chain_replay``'s
``user_protected_cells`` and ``retroactive``'s ``pinned`` count - a human write is
selected POSITIVELY by ``crud.USER_SOURCE``, never by blacklisting the automatic
sources (there are 10,750 distinct automatic source values on live).

MEASURE BEFORE YOU DELETE
-------------------------
``plan_sweep`` writes nothing. ``apply_sweep`` deletes only ``plan["delete_ids"]``.
Every entry point defaults to the dry run, including ``run_sweep`` - which is the
one place this module deliberately diverges from its sibling
``graph_orphans.run_scheduled(apply_deletions=True)``. Deleting a degree-zero node
changes no answer anybody can traverse; deleting an edge changes what a trace
says. Same posture as ``GET /admin/enrichment/auto-confirm/dry-run``.

SAFETY LAYERS (the sibling's, for the same reasons)
---------------------------------------------------
* **clean-declaration precondition** - REFUSE ENTIRELY when the declaration did
  not load cleanly (``graph_orphans.declaration_blockers``, reused, not
  reimplemented). A rejected mapping makes a MAPPED table look unmapped, and this
  sweep reads "unmapped" as "sweep every edge that table ever produced". That is
  the sharpest form of the compound failure the blockers gate was built for.
* **budget guard per edge type** - a type that would lose more than
  ``max_fraction`` of its population is DECLINED and reported, not deleted. A
  mapping typo looks exactly like a retired purpose. Types under
  ``min_population`` are exempt (a 3-edge type is 100% of itself).
* **reversibility** - edges of a still-mapped table are derived, so a resync
  restores anything that should exist. That is real but not unlimited, and the
  populations swept here are precisely the ones a resync cannot restore. Hence
  the dry-run default and the human-confirmed exemption.

WHO CALLS THIS
--------------
* ``server/scripts/graph_stale_edge_sweep.py`` - the operator's door, dry run by
  default. NOT wired to the auto-update scheduler in this round: a destructive
  graph job should be run by a person who has read its dry run at least once
  before it runs unattended.

NOTE ON POPULATION (C), superseded ``source_name``
--------------------------------------------------
``_retarget_stale_edges`` matches on ``(from_node, type, to_node)`` only, so
re-ingesting the same rows from a differently named file mints a second edge with
a new ``source_name`` and the superseded one survives with its old ``event_time``.
Its ``source_row_ref`` still points at a LIVE row of a MAPPED table, so this sweep
correctly declines to touch it - the owning row IS reachable and the authority
there is ``resync_table``, not this module. ``report_superseded_source_edges``
counts them so an operator is told they exist. Fixing it belongs in the
materializer's matching key, which is a hot-path change and its own round.
"""
import logging
import time

logger = logging.getLogger("GraphStaleEdges")

CHUNK = 1000

# A type losing more than this fraction of its population is declined, not swept.
DEFAULT_MAX_FRACTION = 0.5

# Types smaller than this are exempt from the fraction test.
DEFAULT_MIN_POPULATION = 10

# ---- vocabulary -------------------------------------------------------------
# Imported, not respelled. `config_resolve_report.REASONS` is the canon and a
# synonym here would be a second dialect of the same distinction.
from config_resolve_report import (  # noqa: E402
    REASON_MAPPING_UNAVAILABLE,
    REASON_NOT_DECLARED,
    REASON_NOT_REACHED,
)
from retroactive import COUNT_EXACT, COUNT_SAMPLE  # noqa: E402

#: Positive determination: the RDB was asked and the owning row is not there.
#: Not an inability word - see the module docstring.
VERDICT_ROW_GONE = "row_gone"
#: Positive determination: a mapped table still holds the owning row.
VERDICT_LIVE = "live"

VERDICT_NOT_DECLARED = REASON_NOT_DECLARED
VERDICT_NOT_REACHED = REASON_NOT_REACHED

#: The only verdicts a sweep is allowed to act on.
SWEEPABLE_VERDICTS = (VERDICT_ROW_GONE, VERDICT_NOT_DECLARED)


# ----------------- ownership -----------------

def parse_row_ref(ref):
    """``"table:row_id"`` -> ``(table, row_id)``; ``None`` when ownership is unknown.

    Returning ``None`` is a real answer, and the callers must keep it distinct
    from "the row is gone". See the module docstring's ``not_reached`` list for
    each case and why guessing in either direction is worse than saying so.
    """
    if not ref or not isinstance(ref, str):
        return None
    table, sep, row_id = ref.partition(":")
    table, row_id = table.strip(), row_id.strip()
    if not sep or not table or not row_id:
        return None
    if row_id == "None":
        # f-string artefact of a payload with no row_id, not an identity.
        return None
    return table, row_id


def classify_refs(db, refs, mappings) -> dict:
    """-> {ref: {"verdict", "table", "row_id"}} for every ref given.

    The row-existence question is asked ONLY for tables the current declaration
    maps and this process actually holds. Everything else gets a verdict without
    a query, because a query there would answer a different question.
    """
    from database.models import DYNAMIC_TABLES

    out = {}
    by_table = {}
    for ref in refs:
        parsed = parse_row_ref(ref)
        if parsed is None:
            out[ref] = {"verdict": VERDICT_NOT_REACHED, "table": None, "row_id": None}
            continue
        table, row_id = parsed
        if table not in DYNAMIC_TABLES:
            out[ref] = {"verdict": VERDICT_NOT_REACHED, "table": table, "row_id": row_id}
            continue
        if table not in mappings:
            out[ref] = {"verdict": VERDICT_NOT_DECLARED, "table": table, "row_id": row_id}
            continue
        by_table.setdefault(table, {})[row_id] = ref

    for table, wanted in by_table.items():
        model = DYNAMIC_TABLES[table]
        row_ids = sorted(wanted)
        alive = set()
        for i in range(0, len(row_ids), CHUNK):
            chunk = row_ids[i:i + CHUNK]
            for (rid,) in db.query(model.row_id).filter(model.row_id.in_(chunk)).all():
                alive.add(rid)
        for row_id, ref in wanted.items():
            out[ref] = {
                "verdict": VERDICT_LIVE if row_id in alive else VERDICT_ROW_GONE,
                "table": table,
                "row_id": row_id,
            }
    return out


def is_human_confirmed(source_name: str) -> bool:
    """Does this edge carry a person's judgement?

    Positively, by ``crud.USER_SOURCE`` - never by blacklisting automatic source
    names, which are open-ended (crud's own documented rule; 10,750 distinct
    values on live as of 2026-07-27).
    """
    from database import crud
    return source_name == crud.USER_SOURCE


# ----------------- scanning -----------------

def iter_edges(db, scan_limit=None, chunk=CHUNK):
    """Keyset scan of ``graph_edges``. Yields (id, type, source_name, source_row_ref).

    Keyset rather than one ``.all()``: the 1,000-row discipline applies to reads
    that can grow with the graph, and this one grows with every ingested row.
    """
    from database.models import GraphEdge

    last_id = None
    yielded = 0
    while True:
        q = db.query(GraphEdge.id, GraphEdge.type, GraphEdge.source_name,
                     GraphEdge.source_row_ref)
        if last_id is not None:
            q = q.filter(GraphEdge.id > last_id)
        page = q.order_by(GraphEdge.id.asc()).limit(chunk).all()
        if not page:
            return
        for row in page:
            yield row
            yielded += 1
            if scan_limit is not None and yielded >= scan_limit:
                return
        last_id = page[-1][0]
        if len(page) < chunk:
            return


def edge_population(db) -> dict:
    """{type: total edges of that type}. One aggregate, always exact."""
    from database.models import GraphEdge
    from sqlalchemy import func as sa_func

    return dict(
        db.query(GraphEdge.type, sa_func.count(GraphEdge.id))
        .group_by(GraphEdge.type).all()
    )


def report_superseded_source_edges(db):
    """Read-only diagnostic: same (from, type, to), more than one ``source_name``.

    Deliberately NOT swept - see the module docstring's closing note. Delegates to
    the sibling so the query has one implementation, not two that can disagree
    about what "surplus" means.
    """
    import graph_orphans
    return graph_orphans.report_duplicate_source_edges(db)


# ----------------- planning and applying -----------------

def plan_sweep(db, mappings, max_fraction=DEFAULT_MAX_FRACTION,
               min_population=DEFAULT_MIN_POPULATION, scan_limit=None) -> dict:
    """Decide, WITHOUT WRITING ANYTHING, what would be removed and what would not.

    Returns a dict:
      ``population``   {type: total edges}                      (exact, one aggregate)
      ``per_type``     {type: stale edges found}
      ``sweepable``    {type: [(id, verdict, ref)]}             passed the budget guard
      ``declined``     {type: {stale, population, fraction, reason}}
      ``protected``    {"edges", "by_type", "samples"}          human-confirmed, kept
      ``not_reached``  {"edges", "refs", "samples"}             ownership unknown, kept
      ``delete_ids``   [edge id]                                the sweepable types only
      ``count_kind``   ``exact`` | ``sample``                   (see ``scan_limit``)
      ``scanned`` / ``scan_limit`` / ``truncated`` / ``elapsed_ms``

    ``scan_limit`` caps the edge scan. With a cap the numbers describe the rows
    that were looked at and NOTHING about the rest, so ``count_kind`` becomes
    ``sample`` and ``truncated`` is True. Default is no cap and ``exact``.

    IMPORTANT: A TRUNCATED SCAN DELETES NOTHING. Each stale edge in a sample is
    individually certain - the RDB was asked about its owner - but the budget
    guard is not: its numerator would come from the sample while its denominator
    is the whole population, so the fraction is a LOWER bound and the guard could
    only ever fail to decline. A guard that cannot answer must not wave things
    through, so a truncated plan reports every type in ``declined`` with the
    truncation named. ``scan_limit`` is a measurement knob, not a batch size.
    """
    t0 = time.monotonic()
    population = edge_population(db)

    edges = []
    refs = set()
    scanned = 0
    for edge_id, e_type, source_name, ref in iter_edges(db, scan_limit=scan_limit):
        edges.append((edge_id, e_type, source_name, ref))
        refs.add(ref)
        scanned += 1
    truncated = scan_limit is not None and scanned >= scan_limit

    verdicts = classify_refs(db, refs, mappings)

    grouped = {}            # type -> [(id, verdict, ref)]
    per_type = {}
    protected_by_type = {}
    protected_samples = []
    protected_edges = 0
    not_reached_edges = 0
    not_reached_refs = set()
    not_reached_samples = []

    for edge_id, e_type, source_name, ref in edges:
        verdict = verdicts[ref]["verdict"]
        if verdict == VERDICT_NOT_REACHED:
            # Counting only. The line BELOW is the single gate that decides what a
            # sweep may act on - deliberately not an early `continue` here, so
            # that `SWEEPABLE_VERDICTS` is the one place the answer lives rather
            # than a decoration next to a branch that already returned.
            not_reached_edges += 1
            not_reached_refs.add(ref)
            if len(not_reached_samples) < 10:
                not_reached_samples.append({"id": edge_id, "type": e_type, "ref": ref})
        if verdict not in SWEEPABLE_VERDICTS:
            continue  # live, or unownable - either way this module has no say
        if is_human_confirmed(source_name):
            protected_edges += 1
            protected_by_type[e_type] = protected_by_type.get(e_type, 0) + 1
            if len(protected_samples) < 10:
                protected_samples.append({"id": edge_id, "type": e_type, "ref": ref,
                                          "verdict": verdict})
            continue
        per_type[e_type] = per_type.get(e_type, 0) + 1
        grouped.setdefault(e_type, []).append((edge_id, verdict, ref))

    sweepable, declined = {}, {}
    for e_type, entries in sorted(grouped.items()):
        total = population.get(e_type, 0)
        frac = (len(entries) / total) if total else 1.0
        exempt = total < min_population
        if truncated:
            declined[e_type] = {
                "stale": len(entries),
                "population": total,
                "fraction": frac,
                "truncated": True,
                "reason": (
                    "the scan stopped at scan_limit {}, so this fraction ({:.0%}) is "
                    "a lower bound and the budget guard cannot answer whether the "
                    "type would be emptied. count_kind={}".format(
                        scan_limit, frac, COUNT_SAMPLE)
                ),
            }
        elif frac > max_fraction and not exempt:
            declined[e_type] = {
                "stale": len(entries),
                "population": total,
                "fraction": frac,
                "truncated": False,
                "reason": (
                    "would lose {:.0%} of the type (> max_fraction {:.0%}); a "
                    "mapping typo looks exactly like this".format(frac, max_fraction)
                ),
            }
        else:
            sweepable[e_type] = entries

    return {
        "population": population,
        "per_type": per_type,
        "sweepable": sweepable,
        "declined": declined,
        "protected": {
            "edges": protected_edges,
            "by_type": protected_by_type,
            "samples": protected_samples,
        },
        "not_reached": {
            "edges": not_reached_edges,
            "refs": len(not_reached_refs),
            "samples": not_reached_samples,
        },
        "delete_ids": [eid for entries in sweepable.values() for eid, _, _ in entries],
        "count_kind": COUNT_SAMPLE if truncated else COUNT_EXACT,
        "scanned": scanned,
        "scan_limit": scan_limit,
        "truncated": truncated,
        "max_fraction": max_fraction,
        "min_population": min_population,
        "elapsed_ms": (time.monotonic() - t0) * 1000.0,
    }


def apply_sweep(db, plan) -> int:
    """Delete exactly ``plan["delete_ids"]``, in chunks. Returns the number deleted.

    Takes the ids the plan decided on and re-derives nothing: if this function
    recomputed the population it could delete something the dry run never showed,
    which would make the dry run a decoration.
    """
    from database.models import GraphEdge

    ids = plan.get("delete_ids") or []
    deleted = 0
    for i in range(0, len(ids), CHUNK):
        deleted += db.query(GraphEdge).filter(
            GraphEdge.id.in_(ids[i:i + CHUNK])
        ).delete(synchronize_session=False)
    db.commit()
    return deleted


def format_plan_summary(plan, blockers=None, applied=None) -> str:
    """One log line naming what it took, what it declined, and what it could not judge.

    A sweep that reports only its deletions makes "everything was refused" read
    exactly like "there was nothing to do".
    """
    if blockers:
        return ("[GraphStaleEdges] REFUSED (%d blocker(s)): %s"
                % (len(blockers), " | ".join(blockers)))
    took = []
    for e_type, entries in sorted(plan["sweepable"].items()):
        took.append("%s=%d/%d" % (e_type, len(entries),
                                  plan["population"].get(e_type, 0)))
    decl = []
    for e_type, d in sorted(plan["declined"].items()):
        decl.append("%s=%d/%d(%.0f%%)" % (e_type, d["stale"], d["population"],
                                          d["fraction"] * 100))
    verb = ("deleted %d" % applied) if applied is not None \
        else ("would delete %d" % len(plan["delete_ids"]))
    return (
        "[GraphStaleEdges] %s stale edge(s) in %d type(s) [%s]; DECLINED %d edge(s) "
        "in %d type(s) [%s]; PROTECTED %d human-confirmed edge(s); %s %d edge(s) "
        "across %d unattributable ref(s); count_kind=%s scanned=%d; detection %.0f ms"
        % (verb, len(plan["sweepable"]), ", ".join(took) or "-",
           sum(d["stale"] for d in plan["declined"].values()),
           len(plan["declined"]), ", ".join(decl) or "-",
           plan["protected"]["edges"], REASON_NOT_REACHED,
           plan["not_reached"]["edges"], plan["not_reached"]["refs"],
           plan["count_kind"], plan["scanned"], plan["elapsed_ms"])
    )


# ----------------- the entry point -----------------

def run_sweep(known_tables: dict = None, apply_deletions: bool = False,
              max_fraction=DEFAULT_MAX_FRACTION,
              min_population=DEFAULT_MIN_POPULATION, scan_limit=None) -> dict:
    """One sweep cycle. DRY RUN unless ``apply_deletions=True`` is asked for.

    Returns ``{"status", "applied", "plan", "blockers"}``. Logs rather than raises,
    like ``graph_orphans.run_scheduled``: a sweep failure must not take its caller
    down.
    """
    import graph_orphans
    from database.database import SessionLocal
    from database.models import ensure_graph_tables

    out = {"status": "ok", "applied": None, "plan": None, "blockers": []}

    try:
        mappings, rejections = graph_orphans.load_declaration(known_tables)
    except Exception as e:
        out["status"] = "error"
        out["blockers"] = ["could not load the ontology declaration: %s" % e]
        logger.error("[GraphStaleEdges] REFUSED (%s) - %s",
                     REASON_MAPPING_UNAVAILABLE, out["blockers"][0])
        return out

    # Reused from the sibling on purpose: the two sweeps must not disagree about
    # whether a declaration is fit to judge against.
    blockers = graph_orphans.declaration_blockers(mappings, rejections)
    if blockers:
        out["status"] = "refused"
        out["blockers"] = blockers
        logger.error(format_plan_summary(None, blockers=blockers))
        logger.error(
            "[GraphStaleEdges] this sweep reads 'the declaration does not map "
            "table T' as 'nothing can re-derive T's edges', so it will not run "
            "against a declaration that did not load cleanly - a rejected mapping "
            "(%s) is not a retired one (%s). Fix the rejection(s) above (visible on "
            "GET /graph/mapping-summary).",
            REASON_MAPPING_UNAVAILABLE, REASON_NOT_DECLARED)
        return out

    db = SessionLocal()
    try:
        try:
            from database.database import engine
            ensure_graph_tables(engine)
        except Exception as e:
            logger.warning("[GraphStaleEdges] ensure_graph_tables failed: %s", e)

        plan = plan_sweep(db, mappings, max_fraction=max_fraction,
                          min_population=min_population, scan_limit=scan_limit)
        out["plan"] = plan

        if apply_deletions:
            out["applied"] = apply_sweep(db, plan) if plan["delete_ids"] else 0

        logger.info(format_plan_summary(plan, applied=out["applied"]))
        return out
    except Exception as e:
        db.rollback()
        out["status"] = "error"
        out["blockers"] = [str(e)]
        logger.error("[GraphStaleEdges] sweep cycle raised: %s", e, exc_info=True)
        return out
    finally:
        db.close()
