"""Graph orphan sweep — the cleanup that propagation left unattached.

WHY THIS EXISTS
---------------
There is no DELETE path for ``graph_nodes`` anywhere else in production code.
``graph_materializer._retarget_stale_edges`` deletes **edges** (row-ref scoped),
and nothing deletes the node an edge left behind. So this is not only about
retiring a label: **every cell edit that changes an identity leaks a node.**
Correct a lot name from ``LOT-A`` to ``LOT-B`` and the edge is retargeted
faithfully while ``Core(LOT-A|05)`` stays behind forever with zero edges. Measured
on live 2026-07-30: 12,761 degree-zero nodes surviving repeated resyncs.

``/graph/stats`` keeps counting those nodes, which makes the count a lie in the one
place an operator looks after a mapping change.

WHAT THIS IS NOT
----------------
NOT the general row-DELETE / stale-edge policy (spec §8, board 9b). It does not
subscribe to DELETE events and it does not touch edges.

ORPHAN DEFINITION (both conditions required)
--------------------------------------------
1. the node has zero edges (neither ``from_node`` nor ``to_node``), and
2. no currently-mapped table can produce its ``(label, identity_key)``.

Condition 2 is what makes this safe. "Zero edges" alone is NOT an orphan:
``SplitCondition`` legitimately has ~0.2 average degree — most of the DOE
vocabulary has no edges at all, and a zero-edge sweep would delete the
vocabulary. Producibility is evaluated with the very same
``graph_materializer.compose_identity`` the materializer writes with, so this
module cannot become a second identity implementation that drifts from the first
(the failure this repository has already paid for twice in coordinate transforms).

SAFETY — FOUR LAYERS, AND WHY EACH ONE IS THERE
-----------------------------------------------
* **producibility** (above): what the RDB can still mint is never swept.
* **budget guard**: if a label would lose more than ``max_fraction`` of its
  population, that label is DECLINED and reported, not deleted. A mapping typo
  looks exactly like a retired label. Labels smaller than ``min_population`` are
  exempt from the fraction test (a 3-node label is 100% of itself).
* **clean-declaration precondition**: the sweep REFUSES ENTIRELY if the ontology
  mapping did not load cleanly. This is the compound failure the two halves make
  together — a renamed column silently drops a whole table's mapping
  (``ontology_config`` logs and skips), every label that table produced then looks
  unproducible, and the sweep would delete them. The fraction guard catches the
  big labels; it does NOT catch a label under ``min_population``. So a suspect
  declaration disqualifies the judgement, not just some of its conclusions.
* **reversibility**: nodes are derived from the RDB, so a resync restores anything
  that should exist. That is real but not unlimited — an identity that no row
  produces any more does not come back, which is exactly the population being
  swept.

PER-LABEL, NOT ALL-OR-NOTHING
-----------------------------
A declined label must not block the others. The 12,468 retired ``Chip`` nodes
would otherwise hold the ongoing per-edit leak hostage forever. Every run reports
both sets: what it took and what it declined, with counts. A sweep whose skipped
set is invisible reads as "nothing to do".

WHO CALLS THIS
--------------
* ``run_auto_update.py`` (the auto-update scheduler tick) → ``run_scheduled()``.
  A maintenance job, not a collector — same shape and same reasoning as
  ``config_backup``: a collector is per-table and writes a CSV into that table's
  ``raws/``, which this is not, and a collector that yields nothing now reports
  FAIL by design.
* ``server/scripts/graph_orphan_sweep.py`` — the operator's door to the same code.
"""
import logging
import os
import time

logger = logging.getLogger("GraphOrphans")

CHUNK = 1000

# A label losing more than this fraction of its population is declined, not swept.
DEFAULT_MAX_FRACTION = 0.5

# Labels smaller than this are exempt from the fraction test.
DEFAULT_MIN_POPULATION = 10

# Scheduled cadence. Orphans are not urgent — the point of the schedule is that
# the leak stops accumulating unattended, and that the log says so every cycle.
SWEEP_INTERVAL_SEC = 86400.0

# How often the scheduler re-asks whether a sweep is due. The check itself is a
# clock comparison, so this only exists to keep a 5 s tick from asking constantly.
CHECK_INTERVAL_SEC = 1800.0

ENABLE_ENV = "GRAPH_ORPHAN_SWEEP_ENABLED"


def sweep_enabled() -> bool:
    """Off switch, spelled like ``GRAPH_MATERIALIZER_ENABLED`` (its sibling)."""
    return os.getenv(ENABLE_ENV, "true").strip().lower() == "true"


# ----------------- declaration loading -----------------

def load_declaration(known_tables: dict = None):
    """-> (mappings, rejections). Registers dynamic models as a side effect.

    The scheduler process does not otherwise hold dynamic ORM models, and
    producibility needs them. ``init_dynamic_models`` issues no DDL.
    """
    import json

    import ontology_config
    import paths
    from database import models

    if known_tables is None:
        with open(paths.config_path("table_config.json"), "r", encoding="utf-8") as f:
            known_tables = json.load(f)
    models.init_dynamic_models(known_tables)

    rejections = []
    mappings = ontology_config.load_ontology_mappings(
        known_tables=known_tables, rejections=rejections
    )
    return mappings, rejections


def declaration_blockers(mappings: dict, rejections: list) -> list:
    """Reasons this declaration is not fit to judge producibility against.

    Empty list = fit. See the module docstring's third safety layer: a partially
    loaded declaration makes producible nodes look unproducible, and the fraction
    guard does not protect labels under ``min_population``.
    """
    blockers = []
    if not mappings:
        blockers.append(
            "no ontology mapping loaded at all — with an empty declaration every "
            "node in the graph is 'unproducible' by definition"
        )
    for r in rejections or []:
        blockers.append(
            "{scope} '{table}' was rejected: {reason}".format(
                scope=r.get("scope"), table=r.get("table"), reason=r.get("reason")
            )
        )
    return blockers


# ----------------- orphan detection -----------------

def _producing_declarations(mappings):
    """label -> [(table, [identity columns]), ...] for every way the graph mints it.

    Includes edge targets: ``target_identity_from`` mints stub nodes, so a node
    reachable only as an edge target is still producible and must not be swept.
    """
    out = {}
    for table, m in mappings.items():
        node = m["node"]
        out.setdefault(node["label"], []).append((table, list(node["identity"])))
        for e in m["edges"]:
            out.setdefault(e["target_label"], []).append(
                (table, list(e["target_identity_from"]))
            )
    return out


def _zero_edge_condition(db):
    """"this node has no edge in either direction" - the ONE definition.

    Extracted so ``count_zero_edge_nodes`` and ``_zero_edge_nodes`` cannot answer
    different questions; a preview that used a slightly different predicate from
    the sweep it previews would be wrong in a way nothing would report.
    """
    from database.models import GraphNode, GraphEdge
    from sqlalchemy import or_

    return ~db.query(GraphEdge.id).filter(
        or_(GraphEdge.from_node == GraphNode.id, GraphEdge.to_node == GraphNode.id)
    ).exists()


def _zero_edge_nodes(db, labels=None):
    from database.models import GraphNode

    q = db.query(GraphNode.id, GraphNode.label, GraphNode.identity_key).filter(
        _zero_edge_condition(db))
    if labels:
        q = q.filter(GraphNode.label.in_(list(labels)))
    return q.order_by(GraphNode.label.asc(), GraphNode.identity_key.asc()).all()


def count_zero_edge_nodes(db, labels=None) -> int:
    """[sweep preview] Degree-zero nodes, as one aggregate - never materialised.

    This is an UPPER BOUND on what a sweep deletes, and the gap is the whole
    safety design rather than an approximation error. Condition 1 of the orphan
    definition (zero edges) is cheap and answered here; condition 2 (no current
    mapping can produce this identity) requires paging through every mapped table
    via ``_producible_identities``, and the budget guard on top of it requires the
    per-label populations. Those are ``plan_sweep``'s expensive half - the module
    docstring's "SplitCondition legitimately has ~0.2 average degree" is exactly
    why the cheap half alone must never be presented as the answer.
    """
    from database.models import GraphNode
    from sqlalchemy import func

    q = db.query(func.count()).select_from(GraphNode).filter(_zero_edge_condition(db))
    if labels:
        q = q.filter(GraphNode.label.in_(list(labels)))
    return int(q.scalar() or 0)


def _producible_identities(db, table, identity_cols, wanted):
    """Which of ``wanted`` identities can ``table`` still produce? Keyset-chunked.

    Uses ``graph_materializer.compose_identity`` — the single implementation — so
    escaping and numeric normalisation cannot drift from what the materializer
    wrote.
    """
    from database.models import DYNAMIC_TABLES
    from graph_materializer import compose_identity

    model = DYNAMIC_TABLES.get(table)
    if model is None or not wanted:
        return set()

    found = set()
    last = None
    while wanted - found:
        q = db.query(model)
        if last is not None:
            q = q.filter(model.row_id > last)
        chunk = q.order_by(model.row_id.asc()).limit(CHUNK).all()
        if not chunk:
            break
        last = chunk[-1].row_id
        for r in chunk:
            ident = compose_identity([getattr(r, c, None) for c in identity_cols])
            if ident is not None and ident in wanted:
                found.add(ident)
        if len(chunk) < CHUNK:
            break
    return found


def find_orphans(db, mappings, labels=None):
    """-> (orphans [(id, label, identity)], per_label_population {label: total})"""
    from database.models import GraphNode
    from sqlalchemy import func as sa_func

    candidates = _zero_edge_nodes(db, labels)
    by_label = {}
    for node_id, label, ident in candidates:
        by_label.setdefault(label, {})[ident] = node_id

    producers = _producing_declarations(mappings)
    orphans = []
    for label, idents in sorted(by_label.items()):
        wanted = set(idents)
        producible = set()
        for table, cols in producers.get(label, []):
            if not (wanted - producible):
                break
            producible |= _producible_identities(db, table, cols, wanted - producible)
        for ident in sorted(wanted - producible):
            orphans.append((idents[ident], label, ident))

    population = dict(
        db.query(GraphNode.label, sa_func.count(GraphNode.id))
        .group_by(GraphNode.label).all()
    )
    return orphans, population


def report_duplicate_source_edges(db):
    """Read-only diagnostic, deliberately NOT swept here.

    Re-ingesting the same rows from a differently named file mints a second edge
    with the same (from, type, to) but a new ``source_name``.
    ``_retarget_stale_edges`` matches on the triple only, so the superseded one
    survives forever carrying its old ``event_time``. Measured in the isolated
    snapshot: 830 surplus edges of 15,970 (5.2%). Cleaning these is the stale-edge
    policy (board 9b), not this module's job — but an operator running a sweep
    should be told they exist.
    """
    from sqlalchemy import text
    rows = db.execute(text("""
        WITH d AS (SELECT from_node, type, to_node, count(*) c
                   FROM graph_edges GROUP BY 1,2,3 HAVING count(*) > 1)
        SELECT type, count(*) AS triples, sum(c) - count(*) AS surplus
        FROM d GROUP BY 1 ORDER BY 3 DESC""")).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


# ----------------- planning and applying -----------------

def plan_sweep(db, mappings, labels=None, max_fraction=DEFAULT_MAX_FRACTION,
               min_population=DEFAULT_MIN_POPULATION):
    """Decide, without writing anything, what would be swept and what is declined.

    Returns a dict:
      ``orphans``   [(id, label, identity)] — every orphan found, declined included
      ``population`` {label: total nodes with that label}
      ``per_label`` {label: orphan count}
      ``sweepable`` {label: [(id, identity)]} — labels that pass the budget guard
      ``declined``  {label: {orphans, population, fraction, reason}}
      ``delete_ids`` [node id] — ids of the sweepable labels only
      ``elapsed_ms`` how long detection took (this is the expensive half)
    """
    t0 = time.monotonic()
    orphans, population = find_orphans(db, mappings, labels)
    elapsed_ms = (time.monotonic() - t0) * 1000.0

    per_label = {}
    grouped = {}
    for node_id, label, ident in orphans:
        per_label[label] = per_label.get(label, 0) + 1
        grouped.setdefault(label, []).append((node_id, ident))

    sweepable, declined = {}, {}
    for label, entries in sorted(grouped.items()):
        total = population.get(label, 0)
        frac = (len(entries) / total) if total else 1.0
        exempt = total < min_population
        if frac > max_fraction and not exempt:
            declined[label] = {
                "orphans": len(entries),
                "population": total,
                "fraction": frac,
                "reason": (
                    "would lose {:.0%} of the label (> max_fraction {:.0%}); a "
                    "mapping typo looks exactly like this".format(frac, max_fraction)
                ),
            }
        else:
            sweepable[label] = entries

    return {
        "orphans": orphans,
        "population": population,
        "per_label": per_label,
        "sweepable": sweepable,
        "declined": declined,
        "delete_ids": [nid for entries in sweepable.values() for nid, _ in entries],
        "max_fraction": max_fraction,
        "min_population": min_population,
        "elapsed_ms": elapsed_ms,
    }


def apply_sweep(db, plan) -> int:
    """Delete the planned node ids in chunks. Returns the number deleted."""
    from database.models import GraphNode

    ids = plan.get("delete_ids") or []
    deleted = 0
    for i in range(0, len(ids), CHUNK):
        deleted += db.query(GraphNode).filter(
            GraphNode.id.in_(ids[i:i + CHUNK])
        ).delete(synchronize_session=False)
    db.commit()
    return deleted


def format_plan_summary(plan, blockers=None, applied=None) -> str:
    """One log line an operator can read without opening anything.

    Deliberately reports the declined set and the zero case explicitly. "nothing
    to do" and "everything was refused" are different states, and a line that
    omits the skipped set makes the second look like the first.
    """
    if blockers:
        return ("[GraphOrphans] REFUSED (%d blocker(s)): %s"
                % (len(blockers), " | ".join(blockers)))
    took = plan["delete_ids"]
    parts = []
    for label, entries in sorted(plan["sweepable"].items()):
        parts.append("%s=%d/%d" % (label, len(entries), plan["population"].get(label, 0)))
    decl = []
    for label, d in sorted(plan["declined"].items()):
        decl.append("%s=%d/%d(%.0f%%)" % (label, d["orphans"], d["population"],
                                          d["fraction"] * 100))
    verb = ("deleted %d" % applied) if applied is not None else ("would delete %d" % len(took))
    return (
        "[GraphOrphans] %s orphan node(s) in %d label(s) [%s]; DECLINED %d node(s) "
        "in %d label(s) [%s]; detection %.0f ms"
        % (verb, len(plan["sweepable"]), ", ".join(parts) or "-",
           sum(d["orphans"] for d in plan["declined"].values()),
           len(plan["declined"]), ", ".join(decl) or "-", plan["elapsed_ms"])
    )


# ----------------- the scheduled entry point -----------------

def due(last_run_monotonic: float, now_monotonic: float = None) -> bool:
    """True when ``SWEEP_INTERVAL_SEC`` has passed since ``last_run_monotonic``.

    0.0 means "run on the first tick", the same convention
    ``MultiDiscoveryScheduler._last_backup_check`` uses: a process that comes up
    after a long outage does the missed maintenance at boot rather than waiting.
    """
    now = time.monotonic() if now_monotonic is None else now_monotonic
    if not last_run_monotonic:
        return True
    return (now - last_run_monotonic) >= SWEEP_INTERVAL_SEC


def run_scheduled(known_tables: dict = None, apply_deletions: bool = True,
                  max_fraction=DEFAULT_MAX_FRACTION,
                  min_population=DEFAULT_MIN_POPULATION) -> dict:
    """One maintenance cycle. Logs its outcome every run, including refusals.

    Logs rather than raising, like ``config_backup.run_scheduled``: a sweep failure
    must not take the scheduler daemon down. Returns a result dict for tests and
    for the caller's own logging.
    """
    from database.database import SessionLocal
    from database.models import ensure_graph_tables

    out = {"status": "ok", "applied": None, "plan": None, "blockers": []}
    if not sweep_enabled():
        out["status"] = "disabled"
        logger.info("[GraphOrphans] sweep disabled by %s", ENABLE_ENV)
        return out

    try:
        mappings, rejections = load_declaration(known_tables)
    except Exception as e:
        out["status"] = "error"
        out["blockers"] = ["could not load the ontology declaration: %s" % e]
        logger.error("[GraphOrphans] REFUSED — %s", out["blockers"][0])
        return out

    blockers = declaration_blockers(mappings, rejections)
    if blockers:
        out["status"] = "refused"
        out["blockers"] = blockers
        logger.error(format_plan_summary(None, blockers=blockers))
        logger.error(
            "[GraphOrphans] the sweep judges 'can any mapping still produce this "
            "node?', so it will not run against a declaration that did not load "
            "cleanly — fix the rejection(s) above (visible on "
            "GET /graph/mapping-summary) and the next cycle proceeds."
        )
        return out

    db = SessionLocal()
    try:
        try:
            from database.database import engine
            ensure_graph_tables(engine)
        except Exception as e:
            logger.warning("[GraphOrphans] ensure_graph_tables failed: %s", e)

        plan = plan_sweep(db, mappings, max_fraction=max_fraction,
                          min_population=min_population)
        out["plan"] = plan

        if apply_deletions:
            out["applied"] = apply_sweep(db, plan) if plan["delete_ids"] else 0

        logger.info(format_plan_summary(plan, applied=out["applied"]))

        try:
            dups = report_duplicate_source_edges(db)
        except Exception:
            dups = []
        surplus = sum(d[2] or 0 for d in dups)
        if surplus:
            logger.info(
                "[GraphOrphans] note: %d superseded-source duplicate edge(s) exist "
                "across %d type(s) — not swept here (stale-edge policy, board 9b)",
                surplus, len(dups))
        return out
    except Exception as e:
        db.rollback()
        out["status"] = "error"
        out["blockers"] = [str(e)]
        logger.error("[GraphOrphans] sweep cycle raised: %s", e, exc_info=True)
        return out
    finally:
        db.close()
