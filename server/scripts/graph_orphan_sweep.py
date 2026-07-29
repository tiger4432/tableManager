"""Graph orphan sweep — bounded cleanup of nodes a label change leaves behind.

WHY THIS EXISTS
    There is no DELETE path for `graph_nodes` anywhere in production code. Edges get
    retargeted by `_retarget_stale_edges` (row-ref scoped), but the nodes those edges used
    to point at simply stay. So relabelling a table (e.g. `core_wafer_map` node
    `Wafer` -> `Core`) leaves the old `Wafer(LOT-A|05)` nodes sitting there with zero edges,
    and `/graph/stats` keeps reporting them. The count is then a lie, and a lie in the one
    place operators check after a mapping change.

WHAT THIS IS NOT
    This is NOT the general row-DELETE / stale-edge policy (spec §8, board 9b). It does not
    subscribe to DELETE events and it does not touch edges. It is a one-shot, fully
    enumerated cleanup of nodes that **no current mapping can produce and no edge references**.

ORPHAN DEFINITION (both conditions required)
    1. the node has zero edges (neither `from_node` nor `to_node`), and
    2. no currently-mapped table can produce its (label, identity_key).

    Condition 2 is what makes this safe. "Zero edges" alone is NOT an orphan: `SplitCondition`
    legitimately has 0.2 average degree - most of the DOE vocabulary has no edges at all, and
    a zero-edge sweep would delete the vocabulary. Producibility is evaluated with the very
    same `graph_materializer.compose_identity` the materializer uses, so this script cannot
    become a second identity implementation that drifts from the first (the failure this
    repository has already paid for twice in coordinate transforms).

SAFETY
    * dry-run is the default; `--apply` is required to delete anything.
    * budget guard: if a label would lose more than `--max-fraction` of its population
      (default 0.5), the script REFUSES and reports instead of deleting. A mapping typo must
      never be able to quietly empty a label.
    * every identity to be deleted is printed before anything happens.
    * refuses to run against a non-isolated data root unless `--allow-production` is passed.

USAGE
    conda run -n assy_manager python server/scripts/graph_orphan_sweep.py            # dry run
    conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --apply
    ... --label Wafer --label Core      # restrict to specific labels
"""
import argparse
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths  # single override point - never build config paths from __file__ (isolation leak)

CHUNK = 1000


def _load_known_tables():
    import json
    with open(paths.config_path("table_config.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _producing_declarations(mappings):
    """label -> [(table, [identity columns]), ...] for every way the graph can mint that label.

    Includes edge targets: `target_identity_from` mints stub nodes, so a node reachable only
    as an edge target is still producible and must not be swept.
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


def _zero_edge_nodes(db, labels=None):
    from database.models import GraphNode, GraphEdge
    from sqlalchemy import select, or_

    q = db.query(GraphNode.id, GraphNode.label, GraphNode.identity_key).filter(
        ~db.query(GraphEdge.id).filter(
            or_(GraphEdge.from_node == GraphNode.id, GraphEdge.to_node == GraphNode.id)
        ).exists()
    )
    if labels:
        q = q.filter(GraphNode.label.in_(list(labels)))
    return q.order_by(GraphNode.label.asc(), GraphNode.identity_key.asc()).all()


def _producible_identities(db, table, identity_cols, wanted):
    """Which of `wanted` identities can `table` still produce? Keyset-chunked scan.

    Uses graph_materializer.compose_identity - the single implementation - so escaping and
    numeric normalisation cannot drift from what the materializer wrote.
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

    Re-ingesting the same rows from a differently named file mints a second edge with the
    same (from, type, to) but a new `source_name`. `_retarget_stale_edges` matches on the
    triple only, so the superseded one survives forever carrying its old `event_time`.
    Measured in the isolated snapshot: 830 surplus edges of 15,970 (5.2%). Cleaning these is
    the stale-edge policy (board 9b), not this script's job - but an operator running a sweep
    should be told they exist.
    """
    from sqlalchemy import text
    rows = db.execute(text("""
        WITH d AS (SELECT from_node, type, to_node, count(*) c
                   FROM graph_edges GROUP BY 1,2,3 HAVING count(*) > 1)
        SELECT type, count(*) AS triples, sum(c) - count(*) AS surplus
        FROM d GROUP BY 1 ORDER BY 3 DESC""")).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete. Without this nothing is written.")
    ap.add_argument("--label", action="append", dest="labels",
                    help="restrict to this label (repeatable)")
    ap.add_argument("--max-fraction", type=float, default=0.5,
                    help="refuse if a label would lose more than this fraction (default 0.5)")
    ap.add_argument("--min-population", type=int, default=10,
                    help="labels smaller than this are exempt from the fraction guard")
    ap.add_argument("--allow-production", action="store_true",
                    help="permit running against a non-isolated data root")
    args = ap.parse_args()

    print(f"data root : {paths.DATA_ROOT}  (isolated={paths.IS_ISOLATED})")
    url, src = paths.resolve_database_url()
    print(f"database  : {paths.mask_db_password(url)}  ({src})")
    if not paths.IS_ISOLATED and not args.allow_production:
        print("\nREFUSING: this is not an isolated data root. Re-run under devenv.py, or pass "
              "--allow-production if you really mean the live graph.")
        return 2

    import ontology_config
    from database.database import SessionLocal
    from database import models
    from database.models import GraphNode

    known = _load_known_tables()
    models.init_dynamic_models(known)
    mappings = ontology_config.load_ontology_mappings(known_tables=known)
    print(f"mappings  : {len(mappings)} table(s) -> "
          f"{sorted({m['node']['label'] for m in mappings.values()})}")

    db = SessionLocal()
    try:
        orphans, population = find_orphans(db, mappings, args.labels)

        dups = report_duplicate_source_edges(db)
        if dups:
            print("\n-- NOTE: superseded-source duplicate edges exist (not swept here, board 9b) --")
            for t, triples, surplus in dups:
                print(f"     {t:<18} {triples} duplicated triple(s), {surplus} surplus edge(s)")

        if not orphans:
            print("\nNo orphans found. Nothing to do.")
            return 0

        per_label = {}
        for _, label, _ in orphans:
            per_label[label] = per_label.get(label, 0) + 1

        print(f"\n-- {len(orphans)} orphan node(s): zero edges AND not producible by any mapping --")
        for node_id, label, ident in orphans:
            print(f"     [{node_id:>7}] {label:<18} {ident}")

        print("\n-- budget guard --")
        blocked = []
        for label, n in sorted(per_label.items()):
            total = population.get(label, 0)
            frac = (n / total) if total else 1.0
            exempt = total < args.min_population
            over = frac > args.max_fraction and not exempt
            flag = "REFUSE" if over else ("ok (small label, exempt)" if exempt else "ok")
            print(f"     {label:<18} {n}/{total} = {frac:.0%}  {flag}")
            if over:
                blocked.append(label)

        if blocked:
            print(f"\nREFUSING to delete: {blocked} would lose more than "
                  f"{args.max_fraction:.0%} of their population. A mapping typo can look "
                  f"exactly like this. Verify the mapping, then re-run with a higher "
                  f"--max-fraction if the loss is genuinely intended.")
            return 3

        if not args.apply:
            print("\nDRY RUN - nothing written. Re-run with --apply to delete the nodes above.")
            return 0

        ids = [o[0] for o in orphans]
        deleted = 0
        for i in range(0, len(ids), CHUNK):
            deleted += db.query(GraphNode).filter(
                GraphNode.id.in_(ids[i:i + CHUNK])
            ).delete(synchronize_session=False)
        db.commit()
        print(f"\nAPPLIED: deleted {deleted} orphan node(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
