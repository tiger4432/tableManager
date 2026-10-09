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
    ]
    # A replay HANDS ROWS OVER; the chain worker writes them. 이 명령이 「몇 칸을 썼다」를
    # 말하려면 규칙을 여기서 한 번 더 돌려야 하고, 그 두 번째 판단이 이번에 죽은 것이다.
    # 쓴 것은 워커 로그와 큐에서 `chain_<tx>` 라벨로 읽는다.
    if s["mode"] == "apply":
        lines += [f"  rows handed over      : {s['rows_staged']} in "
                  f"{s['events_staged']} outbox event(s)",
                  f"  the worker writes them under one transaction; watch the chain log"]
    else:
        lines.append("  (no --apply: nothing was handed over)")
    if s["pages_failed"]:
        lines.append(f"  pages that failed     : {s['pages_failed']}")
        for f in s["page_failures"][:5]:
            lines.append(f"      page {f['page']} ({f['rows']} rows): {f['error']}")
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
                         f"{sm['new_value']!r} (now from {sm['top_source']!r}; "
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
                     f"{c['new_value']!r} (now from {c['top_source']!r}, "
                     f"{c['reason']}; layers {c['sources']})")
    if not list_all and len(s["changes"]) > len(shown):
        lines.append(f"      ... {len(s['changes']) - len(shown)} more (use --list-all)")
    if (s.get("truncated") or {}).get("changes", {}).get("cut"):
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
    # 🔴 [S-254] AND THE OTHER IDENTITY, for the same reason: the button takes it, so
    # the promised `cli` line has to do the same job. A grid holds `row_id`; on a
    # `composite_key_source` table the stored business key is an ASSEMBLED string that
    # appears in no column, so a screen sending what it can SEE matched nothing.
    p.add_argument("--row-ids", default=None,
                   help="comma-separated row_id list: replay only these rows. This is the "
                        "identity a grid holds for every table; --business-keys is for a "
                        "plain-keyed table. Sending both is refused")
    # Same reason as --business-keys above: the button takes a pace, so the `cli` line has
    # to do the same job or an operator who types it gets an unpaced run and no error.
    p.add_argument("--pace", default=None,
                   help="fast (default, unchanged) | slow | trickle - yield between pages "
                        "so the database stays free for everything else. Declared in "
                        "server/pacing.json")
    # 🪦 `--cascade` (ac918a451) is gone: a script replay cascades nothing - the owner's
    #    「큰 소급 스크립트 문으로 가는 거 연쇄 안 하면 되겠네」 (09-26) · 「한번만」 (09-27).
    #    The grid's click replay is the one seat that asks for it (총괄 5057d030b).

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

    # 총괄 d72dc0283: the retroactive Fold duplicate rows - without --apply, its count's sentence.
    p = sub.add_parser("fold-rows")
    p.add_argument("table")
    p.add_argument("--keys", required=True, help="comma-separated key columns")
    p.add_argument("--order", required=True, help="the column that picks the row to keep")
    p.add_argument("--keep", default="min", choices=["min", "max"], help="min (earliest, default) | max")
    p.add_argument("--prefer-column", default=None, help="with --prefer-text: a row whose column holds it stays first")
    p.add_argument("--prefer-text", default=None, help="the text (any case) --prefer-column holds")
    p.add_argument("--pace", default=None, help="fast (default) | slow | trickle - server/pacing.json")
    p.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)

    from database import crud, models
    from database.database import SessionLocal
    from chain import replay
    from admin import retroactive

    def say(m):
        print(f"  {m}")

    def written(op, params):
        """--apply: the admin button's run record, gate and cancel - the work stays here."""
        return retroactive.run_here(op, params, log=say)["stats"]

    if not crud.TABLE_CONFIG:
        print("REFUSED: table_config.json is empty or missing - nothing is registered")
        return 2
    models.init_dynamic_models(crud.TABLE_CONFIG)

    db = SessionLocal()
    try:
        if args.cmd == "list":
            rules = replay.load_rules()
            print(f"\n{len(rules)} enabled chain rule(s):")
            for r in replay.order_rules(rules):
                self_note = "  [SELF-TRIGGERING]" if replay.is_self_triggering(r) else ""
                print(f"  {r.get('name'):<40} {r.get('trigger_table')} -> "
                      f"{r.get('target_table')}{self_note}")
            print("\n(listed in replay order: a producer before its consumer)\n")
            return 0

        if args.cmd == "replay":
            selected = ([k.strip() for k in args.business_keys.split(",") if k.strip()]
                        if args.business_keys is not None else None)
            rows = ([r.strip() for r in args.row_ids.split(",") if r.strip()]
                    if args.row_ids is not None else None)
            # ⚠️ [S-270] PARSED BEFORE THE LOOKUP, because `--row-ids` is what makes a
            # reference-side rule a legal subject. Asking first and narrowing after is how
            # a CLI comes to refuse what the button accepts (S-254 was that shape).
            rule = replay.find_rule(args.rule_name, row_scoped=bool(rows))
            print(_report_replay(written("chain_replay", {
                "rule": rule["name"], "business_keys": selected, "row_ids": rows,
                "pace": args.pace, "limit": args.limit, "chunk_size": args.chunk_size})
                if args.apply else replay.replay_rule(
                    db, rule, apply=False, limit=args.limit, chunk_size=args.chunk_size,
                    business_keys=selected, row_ids=rows, pace=args.pace, log=say)))
        elif args.cmd == "replay-all":
            out = replay.replay_all(
                db, apply=args.apply, limit=args.limit, chunk_size=args.chunk_size, log=say,
                run_one=(lambda rule: written("chain_replay", {
                    "rule": rule["name"], "limit": args.limit,
                    "chunk_size": args.chunk_size})) if args.apply else None)
            for s in out["rules"]:
                print(_report_replay(s))
        elif args.cmd == "fold-rows":
            params = {"table": args.table, "keys": args.keys, "order": args.order,
                      "keep": args.keep, "pace": args.pace,
                      **({"prefer_column": args.prefer_column} if args.prefer_column is not None else {}),
                      **({"prefer_text": args.prefer_text} if args.prefer_text is not None else {})}
            if args.apply:
                s = written("fold_duplicate_rows", params)
                print(f"\nfold-rows '{args.table}': {s['rows_deleted']} of {s['rows_to_delete']} row(s) "
                      f"deleted in {s['pages']} page(s), {s['keys_folded']} key(s)"
                      + (f" ({s['keys_preferred']} kept a row whose {args.prefer_column} holds "
                         f"'{args.prefer_text}')" if args.prefer_column else "")
                      + f", {s['rows_blank_key']} row(s) with a blank key part left as they are"
                      + (" - STOPPED by request, run it again for the rest" if s["stopped"] else ""))
            else:
                print("\n" + retroactive.count(db, "fold_duplicate_rows", params)["detail"]
                      + "\n-> add --apply to delete")
        elif args.cmd == "resolve":
            cols = [c.strip() for c in args.columns.split(",")] if args.columns else None
            print(_report_resolve(written("resolve", {
                "table": args.table, "columns": cols, "limit": args.limit,
                "chunk_size": args.chunk_size})
                if args.apply else replay.recompute_display_values(
                    db, args.table, columns=cols, apply=False, limit=args.limit,
                    chunk_size=args.chunk_size, log=say),
                list_all=args.list_all))
        else:
            cols = [c.strip() for c in args.columns.split(",")] if args.columns else None
            print(_report_withdraw(written("withdraw", {
                "table": args.table, "source": args.source, "columns": cols})
                if args.apply else replay.withdraw_source(
                    db, args.table, args.source, columns=cols, apply=False, log=say)))
    except (replay.ReplayRefused, retroactive.RetroactiveRefused) as e:
        print(f"REFUSED: {e}")
        return 2
    except retroactive.RunCancelled as e:
        print(f"CANCELLED: {e}")
        return 2
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
