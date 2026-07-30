"""Operator's door to the graph orphan sweep — enumerate, then optionally delete.

The logic lives in ``server/graph_orphans.py`` (why the sweep exists, what an
orphan is, and the four safety layers are documented there). The same module is
what the auto-update scheduler runs on its tick, so this script and the scheduled
job can never drift into two different definitions of "orphan".

This file is the human path: run it before/after a mapping change to see the
identities by name, and to apply a one-off cleanup with an explicit budget.

USAGE
    conda run -n assy_manager python server/scripts/graph_orphan_sweep.py           # dry run
    conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --apply
    ... --label Wafer --label Core          # restrict to specific labels
    ... --max-fraction 1.0                  # a retired label IS 100% of itself

EXIT CODES
    0  nothing to do, or everything planned was reported/applied
    2  refused: not an isolated data root and ``--apply`` was asked for
    3  something was DECLINED (budget guard) or the declaration is not clean.
       Non-zero even when the passing labels were applied — "the job is
       incomplete" is a state the operator must not miss.

ISOLATION
    A dry run is read-only and is allowed anywhere: reporting the live population
    is exactly what a gated cleanup needs to do first. ``--apply`` against a
    non-isolated data root requires ``--allow-production``.
"""
import argparse
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths  # single override point - never build config paths from __file__ (isolation leak)
import graph_orphans  # noqa: E402  (the single implementation; see its docstring)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete. Without this nothing is written.")
    ap.add_argument("--label", action="append", dest="labels",
                    help="restrict to this label (repeatable)")
    ap.add_argument("--max-fraction", type=float, default=graph_orphans.DEFAULT_MAX_FRACTION,
                    help="decline a label that would lose more than this fraction "
                         "(default %(default)s)")
    ap.add_argument("--min-population", type=int,
                    default=graph_orphans.DEFAULT_MIN_POPULATION,
                    help="labels smaller than this are exempt from the fraction guard")
    ap.add_argument("--allow-production", action="store_true",
                    help="permit --apply against a non-isolated data root")
    ap.add_argument("--ignore-rejected", action="store_true",
                    help="proceed even though some ontology mapping failed to load. "
                         "Read the reasons first: a rejected mapping makes every node "
                         "it used to produce look unproducible.")
    ap.add_argument("--limit-print", type=int, default=200,
                    help="how many identities to print per label (default %(default)s); "
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
    print(f"mappings  : {len(mappings)} table(s) -> "
          f"{sorted({m['node']['label'] for m in mappings.values()})}")

    blockers = graph_orphans.declaration_blockers(mappings, rejections)
    if blockers:
        print(f"\n-- {len(blockers)} DECLARATION BLOCKER(S) --")
        for b in blockers:
            print(f"     {b}")
        if not args.ignore_rejected:
            print("\nREFUSING: the sweep asks 'can any mapping still produce this node?', "
                  "so a declaration that did not load cleanly cannot answer it. Every "
                  "label the rejected mapping produced now looks unproducible. Fix it "
                  "(the same list is on GET /graph/mapping-summary), or pass "
                  "--ignore-rejected if you have read the reasons above.")
            return 3
        print("\n  --ignore-rejected given; continuing against a partial declaration.")

    db = SessionLocal()
    try:
        plan = graph_orphans.plan_sweep(
            db, mappings, args.labels,
            max_fraction=args.max_fraction, min_population=args.min_population,
        )

        dups = graph_orphans.report_duplicate_source_edges(db)
        if dups:
            print("\n-- NOTE: superseded-source duplicate edges exist (not swept here, board 9b) --")
            for t, triples, surplus in dups:
                print(f"     {t:<18} {triples} duplicated triple(s), {surplus} surplus edge(s)")

        orphans = plan["orphans"]
        if not orphans:
            print(f"\nNo orphans found. Nothing to do. (detection {plan['elapsed_ms']:.0f} ms)")
            return 0

        print(f"\n-- {len(orphans)} orphan node(s): zero edges AND not producible by any "
              f"mapping (detection {plan['elapsed_ms']:.0f} ms) --")
        by_label = {}
        for node_id, label, ident in orphans:
            by_label.setdefault(label, []).append((node_id, ident))
        for label in sorted(by_label):
            entries = by_label[label]
            shown = entries if args.limit_print <= 0 else entries[:args.limit_print]
            print(f"   {label} ({len(entries)})")
            for node_id, ident in shown:
                print(f"     [{node_id:>7}] {ident}")
            if len(shown) < len(entries):
                print(f"     ... {len(entries) - len(shown)} more (use --limit-print 0)")

        print("\n-- budget guard --")
        for label in sorted(by_label):
            n = len(by_label[label])
            total = plan["population"].get(label, 0)
            frac = (n / total) if total else 1.0
            if label in plan["declined"]:
                flag = "DECLINED"
            elif total < args.min_population:
                flag = "ok (small label, exempt)"
            else:
                flag = "ok"
            print(f"     {label:<18} {n}/{total} = {frac:.0%}  {flag}")

        if plan["declined"]:
            print(f"\nDECLINED {len(plan['declined'])} label(s): "
                  f"{sorted(plan['declined'])}. Each would lose more than "
                  f"{args.max_fraction:.0%} of its population, and a mapping typo looks "
                  f"exactly like that. Verify the mapping, then re-run with a higher "
                  f"--max-fraction if the loss is genuinely intended.")

        if not args.apply:
            print(f"\nDRY RUN - nothing written. {len(plan['delete_ids'])} node(s) would "
                  f"be deleted. Re-run with --apply.")
            return 3 if plan["declined"] else 0

        deleted = graph_orphans.apply_sweep(db, plan)
        print(f"\nAPPLIED: deleted {deleted} orphan node(s) across "
              f"{len(plan['sweepable'])} label(s).")
        return 3 if plan["declined"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
