"""Chain Replay CLI — R1 (re-apply a rule) and R2 (withdraw a stale source).

Dry-run everywhere by default; `--apply` is the only thing that writes.

    # R1 - what would change if this rule ran over all existing data?
    conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <rule>
    conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <rule> --apply
    conda run -n assy_manager python server/scripts/chain_replay_cli.py replay-all

    # R2 - retract a source's claim so the layer underneath becomes visible
    conda run -n assy_manager python server/scripts/chain_replay_cli.py withdraw <table> <source>
    conda run -n assy_manager python server/scripts/chain_replay_cli.py withdraw <table> <source> --columns a,b --apply

    # R3 - re-answer "which stored layer wins" and repair the materialised column
    conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <table>
    conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <table> --apply

`withdraw user` is refused: there is no supported way to remove a human's value
from here.

`resolve` creates and deletes nothing - it only re-materialises the winner over
cells that ALREADY carry two or more layers, and writes an AuditLog entry for every
cell whose displayed value moves. Its dry-run is the enumeration: run it without
`--apply` (add `--list-all`) to get the exact cells before changing any of them.
"""
import argparse
import os
import sys

_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)


def _report_replay(s):
    lines = [
        "",
        f"=== R1 rule re-application {s['mode'].upper()} - '{s['rule']}' ===",
        f"  {s['trigger_table']} -> {s['target_table']}"
        f"{'   (SELF-TRIGGERING: scan bounded by a start snapshot)' if s['self_triggering'] else ''}",
        f"  source rows scanned   : {s['rows_scanned']} in {s['pages']} page(s)",
        f"  mapper items          : {s['mapper_items']}",
        f"  cells proposed        : {s['cells_proposed']}",
    ]
    if s["mode"] == "apply":
        lines += [f"  cells written         : {s['cells_written']}",
                  f"  rows created/updated  : {s['rows_created']} / {s['rows_updated']}"]
    else:
        lines.append(f"  cells a human protects: {s['user_protected_cells']}  "
                     f"(replay writes its layer; the human's value keeps winning)")
    if s["skipped_blank_cells"]:
        lines += [
            f"  cells with NO value   : {s['skipped_blank_cells']}  (NOT written - absence "
            f"is not zero)",
            "  -> the rule no longer produces a value for these. To make the layer",
            "     underneath visible use R2:  withdraw "
            f"{s['target_table']} chain_ingestion --columns <col>",
        ]
        for c in s["withdrawal_candidates"][:5]:
            lines.append(f"      {c['business_key_val']}.{c['column']}")
    for sm in s["samples"][:3]:
        lines.append(f"      e.g. {sm['business_key_val']}: {sm['updates']}")
    lines.append("")
    return "\n".join(lines)


def _report_withdraw(s):
    lines = [
        "",
        f"=== R2 stale source withdrawal {s['mode'].upper()} - "
        f"'{s['source']}' on '{s['table']}' ===",
        f"  cells claimed by source : {s['cells_matched']}",
        f"  cells withdrawn         : {s['cells_withdrawn']}",
        f"    revealed another layer: {s['revealed']}",
        f"    left empty            : {s['emptied']}",
        f"    value unchanged       : {s['value_unchanged']}",
        f"  skipped (human-pinned)  : {s['pinned_skipped']}",
    ]
    if s["cells_withdrawn"]:
        lines.append("  Every cell whose visible value changed has an AuditLog entry naming")
        lines.append("  the withdrawn source, so the cell-history timeline explains it.")
    for sm in s["samples"][:8]:
        if sm["action"] == "skipped":
            lines.append(f"      SKIP {sm['row_id'][:8]}.{sm['column']}: {sm['why']}")
        else:
            lines.append(f"      {sm['row_id'][:8]}.{sm['column']}: {sm['old_value']!r} -> "
                         f"{sm['new_value']!r} (now from {sm['revealed_source']!r}; "
                         f"remaining {sm['remaining_sources']})")
    lines.append("")
    return "\n".join(lines)


def _report_resolve(s, list_all=False):
    lines = [
        "",
        f"=== R3 display-value recompute {s['mode'].upper()} - '{s['table']}' ===",
        f"  rows scanned            : {s['rows_scanned']} in {s['pages']} page(s)",
        f"  multi-layer cells       : {s['cells_examined']}  (cells with <2 layers are "
        f"never touched)",
        f"  human-pinned cells      : {s['pinned_examined']}",
        f"  cells whose value moves : {s['cells_changed']}",
        f"    tie broken by recency : {s['changed_by_tiebreak']}",
        f"    already out of step   : {s['changed_by_stale_materialisation']}",
        f"    of which human-pinned : {s['pinned_changed']}  (the pin still picks the "
        f"layer; only the stale display moves)",
    ]
    if s["cells_changed"]:
        lines.append("  Every cell listed below gets an AuditLog entry, so the cell-history")
        lines.append("  timeline explains the change rather than it appearing from nowhere.")
    shown = s["changes"] if list_all else s["changes"][:20]
    for c in shown:
        lines.append(f"      {c['business_key_val']}.{c['column']}: {c['old_value']!r} -> "
                     f"{c['new_value']!r} (now from {c['winning_source']!r}, "
                     f"{c['reason']}; layers {c['sources']})")
    if not list_all and len(s["changes"]) > len(shown):
        lines.append(f"      ... {len(s['changes']) - len(shown)} more (use --list-all)")
    if s["changes_truncated"]:
        lines.append("      WARNING: the change list hit its in-memory cap; the AuditLog "
                     "rows written by --apply are the complete record.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("replay")
    p.add_argument("rule_name")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--chunk-size", type=int, default=1000)
    # WHICH rows, beside --limit's HOW MANY. `retroactive.OPERATIONS` promises that its
    # `cli` line does the same job as the button, and without this the promise was false
    # for the half that selects.
    p.add_argument("--business-keys", default=None,
                   help="comma-separated business_key_val list: replay only these rows. "
                        "Omit to replay the whole rule. This chooses WHICH rows; --limit "
                        "still bounds how many are scanned")
    # Same reason as --business-keys above: the button takes a pace, so the `cli` line has
    # to do the same job or an operator who types it gets an unpaced run and no error.
    p.add_argument("--pace", default=None,
                   help="fast (default, unchanged) | slow | trickle - yield between pages "
                        "so the database stays free for everything else. Declared in "
                        "server/pacing.json")

    p = sub.add_parser("replay-all")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--chunk-size", type=int, default=1000)

    p = sub.add_parser("withdraw")
    p.add_argument("table")
    p.add_argument("source")
    p.add_argument("--columns", default=None, help="comma-separated column allowlist")
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("resolve")
    p.add_argument("table")
    p.add_argument("--columns", default=None, help="comma-separated column allowlist")
    p.add_argument("--limit", type=int, default=None, help="bound rows scanned")
    p.add_argument("--chunk-size", type=int, default=1000)
    p.add_argument("--list-all", action="store_true",
                   help="print every changed cell, not the first 20")
    p.add_argument("--apply", action="store_true")

    p = sub.add_parser("list")

    args = parser.parse_args(argv)

    from database import crud, models
    from database.database import SessionLocal
    import chain_replay

    if not crud.TABLE_CONFIG:
        print("REFUSED: table_config.json is empty or missing - nothing is registered")
        return 2
    models.init_dynamic_models(crud.TABLE_CONFIG)

    db = SessionLocal()
    try:
        if args.cmd == "list":
            rules = chain_replay.load_rules()
            print(f"\n{len(rules)} enabled chain rule(s):")
            for r in chain_replay.order_rules(rules):
                self_note = "  [SELF-TRIGGERING]" if chain_replay.is_self_triggering(r) else ""
                print(f"  {r.get('name'):<40} {r.get('trigger_table')} -> "
                      f"{r.get('target_table')}{self_note}")
            print("\n(listed in replay order: a producer before its consumer)\n")
            return 0

        if args.cmd == "replay":
            rule = chain_replay.find_rule(args.rule_name)
            selected = ([k.strip() for k in args.business_keys.split(",") if k.strip()]
                        if args.business_keys is not None else None)
            print(_report_replay(chain_replay.replay_rule(
                db, rule, apply=args.apply, limit=args.limit,
                chunk_size=args.chunk_size, business_keys=selected, pace=args.pace,
                log=lambda m: print(f"  {m}"))))
        elif args.cmd == "replay-all":
            out = chain_replay.replay_all(db, apply=args.apply, limit=args.limit,
                                          chunk_size=args.chunk_size,
                                          log=lambda m: print(f"  {m}"))
            for s in out["rules"]:
                print(_report_replay(s))
        elif args.cmd == "resolve":
            cols = [c.strip() for c in args.columns.split(",")] if args.columns else None
            print(_report_resolve(chain_replay.recompute_display_values(
                db, args.table, columns=cols, apply=args.apply, limit=args.limit,
                chunk_size=args.chunk_size, log=lambda m: print(f"  {m}")),
                list_all=args.list_all))
        else:
            cols = [c.strip() for c in args.columns.split(",")] if args.columns else None
            print(_report_withdraw(chain_replay.withdraw_source(
                db, args.table, args.source, columns=cols, apply=args.apply,
                log=lambda m: print(f"  {m}"))))
    except chain_replay.ReplayRefused as e:
        print(f"REFUSED: {e}")
        return 2
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
