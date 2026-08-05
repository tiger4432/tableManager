"""Enrichment insight CLI — [④] classify gaps, [②] propose rules, [①] confirm.

Read-only by default, everywhere. Only `confirm --apply` writes, and only when
the rule's `auto_confirm` knob is on.

    conda run -n assy_manager python server/scripts/enrichment_insights.py classify <rule>
    conda run -n assy_manager python server/scripts/enrichment_insights.py propose  <rule> [--min-support N]
    conda run -n assy_manager python server/scripts/enrichment_insights.py confirm  <rule> [--apply]
    ... any subcommand with no <rule> runs every enabled rule.

Same bootstrap and dry-run-first posture as `backfill_enrichment.py`.
"""
import argparse
import json
import os
import sys

_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)


def _rules(rule_name=None):
    import enrichment_config
    from database import crud

    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    if rule_name:
        rule = next((r for r in rules if r["name"] == rule_name), None)
        if rule is None:
            available = ", ".join(sorted(r["name"] for r in rules)) or "<none>"
            print(f"REFUSED: rule '{rule_name}' not found or invalid; available: {available}")
            return None
        return [rule]
    return rules


def _report_classify(res):
    import enrichment_analysis as ea

    bug = sum(res["counts"].get(c, 0) for c in ea.BUG_CLASSES)
    work = sum(res["counts"].get(c, 0) for c in ea.REAL_WORK_CLASSES)
    auto = res["counts"].get(ea.CLS_RESOLVABLE, 0)
    lines = [
        "",
        f"=== [4] gap causes - rule '{res['rule']}' ===",
        f"  source / derived      : {res['source_table']} -> {res['derived_table']}",
        f"  queue size            : {res['queue_size']}",
        "",
        f"  A PIPELINE BUG (a human should never pay this): {bug}",
        f"      {ea.CLS_MAPPING_GAP:<26} {res['counts'].get(ea.CLS_MAPPING_GAP, 0)}",
        # Not merely a bug a human should not pay: one a human CANNOT pay. With no
        # decision key there is nothing to bind a reference view to, so the row is
        # visible (deliberately) but unworkable until it is fixed upstream.
        f"      {ea.CLS_BLANK_DECISION_KEY:<26} "
        f"{res['counts'].get(ea.CLS_BLANK_DECISION_KEY, 0)}"
        f"   (cannot be worked here at all - fix upstream)",
        f"  MECHANICALLY RESOLVABLE (item 1 handles it)   : {auto}",
        f"      {ea.CLS_RESOLVABLE:<26} {auto}   (EVERY blank target decided)",
        f"  REAL HUMAN WORK                              : {work}",
        f"      {ea.CLS_AMBIGUOUS:<26} {res['counts'].get(ea.CLS_AMBIGUOUS, 0)}",
        f"      {ea.CLS_NO_EVIDENCE:<26} {res['counts'].get(ea.CLS_NO_EVIDENCE, 0)}",
        # Counted as work because the columns item 1 cannot decide are still a
        # person's job - but item 1 does fill the rest, so the row is cheaper
        # than an ambiguous one and saying so is the point of the split.
        f"      {ea.CLS_PARTIALLY_RESOLVABLE:<26} "
        f"{res['counts'].get(ea.CLS_PARTIALLY_RESOLVABLE, 0)}"
        f"   (item 1 fills SOME columns; the rest still need a person)",
        f"  OTHER                                        : "
        f"{res['counts'].get(ea.CLS_NO_SOURCE_ROWS, 0) + res['counts'].get(ea.CLS_UNPROBED, 0)}",
        f"      {ea.CLS_NO_SOURCE_ROWS:<26} {res['counts'].get(ea.CLS_NO_SOURCE_ROWS, 0)}",
        f"      {ea.CLS_UNPROBED:<26} {res['counts'].get(ea.CLS_UNPROBED, 0)}"
        f"   (probe budget {res['probe_limit']}, probed {res['probed']})",
    ]
    if res["no_evidence_reasons"]:
        lines.append(f"  no_evidence refusal reasons: {res['no_evidence_reasons']}")
    # Per COLUMN, because the row classes above cannot say WHICH column is stuck.
    # `not_declared` in here is a config gap, not a judgement: nobody asked.
    for field, verdicts in sorted((res.get("target_verdicts") or {}).items()):
        lines.append(f"  target '{field}': "
                     + ", ".join(f"{k}={v}" for k, v in sorted(verdicts.items())))
    lines.append(f"  bug-class check covered targets: {res['same_name_targets_checked'] or '[]'}")
    if res["unchecked_targets"]:
        lines.append(
            f"  NOT checkable for the bug class : {res['unchecked_targets']} - the source "
            f"table has no column of that name, and a differently-named source column is "
            f"not inferred (declaration only).")
    for cls, samples in sorted(res["samples"].items()):
        for s in samples[:3]:
            lines.append(f"    [{cls}] {s['business_key_val']}: {s['detail']}")
    lines.append("")
    return "\n".join(lines)


def _report_propose(res):
    lines = ["", f"=== [2] promotion proposals - rule '{res['rule']}' ==="]
    if res.get("refused"):
        lines += [f"  REFUSED: {res['refused']}", f"  {res['detail']}", ""]
        return "\n".join(lines)
    lines += [
        f"  resolved rows scanned : {res['resolved_rows']}",
        f"  human-written cells   : {res['human_cells']}",
        f"  min support           : {res['min_support']}",
        f"  proposals             : {len(res['proposals'])}",
        f"  rejected antecedents  : {len(res['conflicts'])}",
        "",
        "  NOTHING HAS BEEN APPLIED. Paste a proposal into the rule's",
        "  'reference_views' (with its candidate_for) to make item 1 execute it.",
    ]
    for p in res["proposals"]:
        lines += [
            "",
            f"  PROPOSAL: {'+'.join(p['antecedent_columns'])} -> {p['target_field']}",
            f"    distinct antecedent values : {p['distinct_antecedent_values']}",
            f"    total human decisions      : {p['total_support']}",
            f"    evidence (first few)       : "
            f"{[(e['antecedent'], e['value'], e['support']) for e in p['entries']]}",
            "    reference_views entry to paste:",
            "      " + json.dumps(p["reference_view"], ensure_ascii=False, indent=6)
            .replace("\n", "\n      "),
        ]
    for c in res["conflicts"]:
        lines += ["", f"  REJECTED: {'+'.join(c['antecedent_columns'])} -> {c['target_field']}",
                  f"    {c['why_rejected']}"]
        if c.get("conflicting_values"):
            lines.append(f"    examples: {c['conflicting_values']}")
    lines.append("")
    return "\n".join(lines)


def _report_confirm(stats):
    lines = [
        "",
        f"=== [1] single-candidate confirmation {stats['mode'].upper()} - "
        f"rule '{stats['rule']}' ===",
        f"  queue size              : {stats['queue_size']}",
        f"  key-fields probed       : {stats.get('keys_examined', 0)}",
        f"  single candidates       : {stats.get('confirmed', 0)}",
        f"  cells {'written' if stats['mode'] == 'apply' else 'that would be written'}"
        f"{'':<10}: {stats.get('written_cells', 0)}",
        # A partly filled row is progress, not a row still queued. Without this
        # line the only row-grain number was `queue size`, so a sweep that filled
        # two of three columns everywhere reported as having moved nothing.
        f"  rows: {stats.get('rows_fully_confirmed', 0)} complete, "
        f"{stats.get('rows_partly_confirmed', 0)} partly filled, "
        f"{stats.get('rows_unconfirmed', 0)} untouched "
        f"(of {stats.get('rows_examined', 0)} examined)",
        "  refusals (each named)   :",
    ]
    for reason, n in sorted((stats.get("refused") or {}).items()):
        lines.append(f"      {reason:<26} {n}")
    if not stats.get("refused"):
        lines.append("      none")
    for field, slot in sorted((stats.get("per_target") or {}).items()):
        lines.append(f"    target '{field}': {slot['confirmed']} confirmed"
                     + (f", refused {slot['refused']}" if slot["refused"] else ""))
    for s in (stats.get("samples") or [])[:5]:
        lines.append(f"    [single] {s['business_key_val']} {s['field']}="
                     f"{s['value']!r} (support {s['support']})")
    if stats["mode"] == "dry-run" and stats.get("confirmed"):
        lines.append("  -> these items need NO human interaction. On the V1 effort metric "
                     "each is 키n+마우스3 today and 0 with the knob on.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("classify", "propose", "confirm"):
        p = sub.add_parser(name)
        p.add_argument("rule_name", nargs="?", default=None)
        p.add_argument("--limit", type=int, default=None,
                       help="cap the number of rows examined")
    sub.choices["classify"].add_argument("--probe-limit", type=int, default=200,
                                         help="max keys probed against reference views")
    sub.choices["propose"].add_argument("--min-support", type=int, default=3,
                                        help="human decisions required before proposing")
    sub.choices["confirm"].add_argument("--apply", action="store_true",
                                        help="WRITE the confirmations (needs auto_confirm on)")
    sub.choices["confirm"].add_argument("--ignore-knob", action="store_true",
                                        help="measure a rule whose knob is off (dry-run only)")
    args = parser.parse_args(argv)

    from database import crud, models
    from database.database import SessionLocal
    import enrichment_analysis as ea

    if not crud.TABLE_CONFIG:
        print("REFUSED: table_config.json is empty or missing - nothing is registered")
        return 2
    models.init_dynamic_models(crud.TABLE_CONFIG)

    rules = _rules(args.rule_name)
    if rules is None:
        return 2
    if not rules:
        print("No enabled enrichment rules found.")
        return 0

    db = SessionLocal()
    rc = 0
    try:
        for rule in rules:
            try:
                if args.cmd == "classify":
                    print(_report_classify(ea.classify_queue(
                        db, rule, probe_limit=args.probe_limit, limit=args.limit,
                        log=lambda m: print(f"  {m}"))))
                elif args.cmd == "propose":
                    print(_report_propose(ea.analyze_promotions(
                        db, rule, min_support=args.min_support, limit=args.limit,
                        log=lambda m: print(f"  {m}"))))
                else:
                    print(_report_confirm(ea.run_auto_confirm_sweep(
                        db, rule, apply=args.apply, limit=args.limit,
                        ignore_knob=args.ignore_knob, log=lambda m: print(f"  {m}"))))
            except ea.AnalysisRefused as e:
                print(f"REFUSED [{rule['name']}]: {e}")
                rc = 2
    finally:
        db.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
