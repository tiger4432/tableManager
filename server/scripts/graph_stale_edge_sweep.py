"""Operator's door to the graph STALE EDGE sweep - measure first, delete second.

The logic lives in ``server/graph_stale_edges.py`` (why the sweep exists, the
ownership model, what cannot be swept and why, and how human-confirmed edges are
protected are all documented there). This file is the human path.

Sibling: ``graph_orphan_sweep.py`` removes degree-zero NODES. This one removes
EDGES that no derivation can produce any more. Run this one first: an edge keeps
both its endpoints out of the orphan sweep's reach, so the node cleanup can only
finish after the edge cleanup has.

USAGE
    conda run -n assy_manager python server/scripts/graph_stale_edge_sweep.py          # dry run
    conda run -n assy_manager python server/scripts/graph_stale_edge_sweep.py --apply
    ... --max-fraction 1.0        # a retired purpose IS 100% of its edge types
    ... --scan-limit 5000         # cap the scan; the report then says count_kind=sample

EXIT CODES
    0  nothing to do, or everything planned was reported/applied
    2  refused: not an isolated data root and ``--apply`` was asked for
    3  something was DECLINED (budget guard), the declaration is not clean, or the
       scan was truncated. Non-zero even when the passing types were applied -
       "the job is incomplete" is a state the operator must not miss.

ISOLATION
    A dry run is read-only and is allowed anywhere. ``--apply`` against a
    non-isolated data root requires ``--allow-production``.
"""
import argparse
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths  # single override point - never build config paths from __file__ (isolation leak)
import graph_orphans  # noqa: E402  (declaration loading + blockers, shared with the node sweep)
import graph_stale_edges  # noqa: E402  (the single implementation; see its docstring)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete. Without this nothing is written.")
    ap.add_argument("--max-fraction", type=float,
                    default=graph_stale_edges.DEFAULT_MAX_FRACTION,
                    help="decline an edge type that would lose more than this "
                         "fraction (default %(default)s)")
    ap.add_argument("--min-population", type=int,
                    default=graph_stale_edges.DEFAULT_MIN_POPULATION,
                    help="edge types smaller than this are exempt from the guard")
    ap.add_argument("--scan-limit", type=int, default=None,
                    help="cap the edge scan. MEASUREMENT ONLY: the report then says "
                         "count_kind=sample and every type is declined, because the "
                         "budget guard cannot be answered from a sample.")
    ap.add_argument("--allow-production", action="store_true",
                    help="permit --apply against a non-isolated data root")
    ap.add_argument("--ignore-rejected", action="store_true",
                    help="proceed even though some ontology mapping failed to load. "
                         "Read the reasons first: a rejected mapping makes a MAPPED "
                         "table look unmapped, and this sweep reads unmapped as "
                         "'delete every edge that table produced'.")
    ap.add_argument("--limit-print", type=int, default=200,
                    help="how many edges to print per type (default %(default)s); "
                         "0 prints all of them")
    args = ap.parse_args()

    print(f"data root : {paths.DATA_ROOT}  (isolated={paths.IS_ISOLATED})")
    url, src = paths.resolve_database_url()
    print(f"database  : {paths.mask_db_password(url)}  ({src})")
    if args.apply and not paths.IS_ISOLATED and not args.allow_production:
        print("\nREFUSING to --apply: this is not an isolated data root. Re-run under "
              "devenv.py, or pass --allow-production if you really mean the live graph. "
              "(A dry run needs neither.)")
        return 2

    from database.database import SessionLocal

    mappings, rejections = graph_orphans.load_declaration()
    print(f"mappings  : {len(mappings)} table(s) -> {sorted(mappings)}")

    blockers = graph_orphans.declaration_blockers(mappings, rejections)
    if blockers:
        print(f"\n-- {len(blockers)} DECLARATION BLOCKER(S) --")
        for b in blockers:
            print(f"     {b}")
        if not args.ignore_rejected:
            print("\nREFUSING: a mapping that was REJECTED "
                  f"({graph_stale_edges.REASON_MAPPING_UNAVAILABLE}) is not a mapping "
                  f"that was RETIRED ({graph_stale_edges.REASON_NOT_DECLARED}), and "
                  "this sweep cannot tell them apart from the outside. Fix it (the "
                  "same list is on GET /graph/mapping-summary), or pass "
                  "--ignore-rejected if you have read the reasons above.")
            return 3
        print("\n  --ignore-rejected given; continuing against a partial declaration.")

    db = SessionLocal()
    try:
        plan = graph_stale_edges.plan_sweep(
            db, mappings, max_fraction=args.max_fraction,
            min_population=args.min_population, scan_limit=args.scan_limit,
        )

        print(f"\nscanned {plan['scanned']} edge(s), count_kind={plan['count_kind']}"
              + (f" (TRUNCATED at --scan-limit {plan['scan_limit']}; the numbers below "
                 "describe the scanned rows and nothing about the rest)"
                 if plan["truncated"] else ""))

        nr = plan["not_reached"]
        print(f"\n-- {graph_stale_edges.REASON_NOT_REACHED}: {nr['edges']} edge(s) across "
              f"{nr['refs']} ref(s) whose owner could not be established --")
        print("     These are NEVER swept. 'I do not know who minted this' is not "
              "'nobody minted this'.")
        for s in nr["samples"]:
            print(f"     [{s['id']:>7}] {s['type']:<18} ref={s['ref']!r}")

        prot = plan["protected"]
        print(f"\n-- PROTECTED: {prot['edges']} human-confirmed edge(s) "
              f"(source_name='user') --")
        if prot["by_type"]:
            for t, n in sorted(prot["by_type"].items()):
                print(f"     {t:<18} {n}")
            print("     A person's judgement is not re-derivable. These stay even "
                  "though nothing produces them any more.")

        stale_total = sum(plan["per_type"].values())
        if not stale_total:
            print(f"\nNo sweepable stale edges. Nothing to do. "
                  f"(detection {plan['elapsed_ms']:.0f} ms)")
            return 3 if plan["truncated"] else 0

        print(f"\n-- {stale_total} stale edge(s): the owning row is gone, or its table "
              f"is no longer declared (detection {plan['elapsed_ms']:.0f} ms) --")
        for e_type in sorted(plan["per_type"]):
            entries = plan["sweepable"].get(e_type)
            if entries is None:
                continue
            shown = entries if args.limit_print <= 0 else entries[:args.limit_print]
            print(f"   {e_type} ({len(entries)})")
            for edge_id, verdict, ref in shown:
                print(f"     [{edge_id:>7}] {verdict:<14} {ref}")
            if len(shown) < len(entries):
                print(f"     ... {len(entries) - len(shown)} more (use --limit-print 0)")

        print("\n-- budget guard --")
        for e_type, n in sorted(plan["per_type"].items()):
            total = plan["population"].get(e_type, 0)
            frac = (n / total) if total else 1.0
            if e_type in plan["declined"]:
                flag = "DECLINED"
            elif total < args.min_population:
                flag = "ok (small type, exempt)"
            else:
                flag = "ok"
            print(f"     {e_type:<18} {n}/{total} = {frac:.0%}  {flag}")

        if plan["declined"]:
            print(f"\nDECLINED {len(plan['declined'])} type(s) - reason per type:")
            for e_type, d in sorted(plan["declined"].items()):
                print(f"     {e_type:<18} {d['reason']}")
            if not plan["truncated"]:
                print("     Verify the declaration, then re-run with a higher "
                      "--max-fraction if the loss is genuinely intended.")

        try:
            dups = graph_stale_edges.report_superseded_source_edges(db)
        except Exception:
            dups = []
        if dups:
            print("\n-- NOTE: superseded-source duplicate edges exist (NOT swept here; "
                  "their owning rows are live, so resync is the authority) --")
            for t, triples, surplus in dups:
                print(f"     {t:<18} {triples} duplicated triple(s), {surplus} surplus edge(s)")

        if not args.apply:
            print(f"\nDRY RUN - nothing written. {len(plan['delete_ids'])} edge(s) would "
                  f"be deleted. Re-run with --apply.")
            return 3 if (plan["declined"] or plan["truncated"]) else 0

        deleted = graph_stale_edges.apply_sweep(db, plan)
        print(f"\nAPPLIED: deleted {deleted} stale edge(s) across "
              f"{len(plan['sweepable'])} type(s).")
        print("Run graph_orphan_sweep.py next: the nodes those edges were holding "
              "in place are only now degree-zero.")
        return 3 if (plan["declined"] or plan["truncated"]) else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
