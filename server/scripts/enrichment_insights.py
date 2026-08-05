"""Enrichment insight CLI — [④] classify gaps, [②] propose rules, [①] confirm.

Read-only by default, everywhere. Only `confirm --apply` writes, and only when
the rule's `auto_confirm` knob is on.

    conda run -n assy_manager python server/scripts/enrichment_insights.py classify <rule>
    conda run -n assy_manager python server/scripts/enrichment_insights.py propose  <rule> [--min-support N]
    conda run -n assy_manager python server/scripts/enrichment_insights.py confirm  <rule> [--apply]
    ... any subcommand with no <rule> runs every enabled rule.

THREE NUMBERS THAT ARE NOT THE SAME NUMBER (2026-08-05: they were all `limit`)
    --max-keys              how many KEYS are examined. Widens no read.
    --probe-scan-rows       how many ROWS one probe reads   -> probe_truncated
    --probe-distinct-values how many DISTINCT VALUES it sees -> distinct_truncated
    A truncation refusal names which one cut it and where that one is set.

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


def _caps_from_args(args):
    """Read-cap snapshot for this run: config, then any explicit CLI override.

    Overriding here rather than inside each analysis keeps ONE snapshot for the
    whole invocation - a run whose caps change mid-walk is a run whose numbers
    cannot be compared to each other.
    """
    import enrichment_config as ec

    caps = ec.load_read_caps()
    for flag, key in ((getattr(args, "probe_scan_rows", None), ec.CAP_PROBE_SCAN_ROWS),
                      (getattr(args, "probe_distinct_values", None),
                       ec.CAP_PROBE_DISTINCT_VALUES)):
        if flag is not None:
            caps[key] = {"value": flag, "declared": True}
    return caps


def _cap_lines(res):
    """One block per cap that actually clipped a read, naming the repair.

    Absent from the output when nothing was clipped: a report that lists every
    ceiling every time trains people to skim past the one that mattered.
    """
    lines = []
    for cap, s in sorted((res.get("cap_hits") or {}).items()):
        lines += [
            "",
            f"  A READ WAS CLIPPED BY '{cap}' = {s['cap_value']}"
            + ("" if s["cap_declared"] else "   <- NOT declared; this is the shipped value"),
            f"      reads clipped                : {s['hits']} (largest read {s['max_read']})",
            # The two outcomes are different repairs and must not be one number.
            f"      raising it -> AMBIGUOUS      : {s['ambiguous']}   (>=2 distinct values "
            f"were ALREADY read - a person decides these, not a knob)",
            f"      raising it -> unknown        : {s['unknown']}   (the read is too short "
            f"to tell whether the rest agrees)",
            f"      set it at                    : {s['cap_home']}",
        ]
    return lines


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
        f"   (KEY budget --max-keys={res['max_keys']}, probed {res['probed']};"
        f" this bounds keys, not reads)",
    ]
    lines += _cap_lines(res)
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
    lines += _cap_lines(stats)
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
    # THREE NUMBERS, THREE NAMES, NONE OF THEM `--limit` [2026-08-05 incident].
    # `--max-keys` bounds HOW MANY KEYS are examined. The two `--probe-*` caps
    # bound ONE READ. The old `--probe-limit` was the key budget wearing a name
    # that sounded like a read cap, and after a `distinct_truncated` refusal an
    # operator raised it and nothing happened - it is the only one they could
    # reach. It still works, and it says what it is.
    sub.choices["classify"].add_argument(
        "--max-keys", dest="max_keys", type=int, default=200,
        help="KEY BUDGET: how many keys are probed. Widens no read.")
    sub.choices["classify"].add_argument(
        "--probe-limit", dest="max_keys", type=int,
        help="deprecated alias for --max-keys (it is the KEY BUDGET, not a read cap)")
    # Available on BOTH classify and confirm: measuring with one ceiling and
    # writing with another is how two surfaces come to disagree.
    for name in ("classify", "confirm"):
        sub.choices[name].add_argument(
            "--probe-scan-rows", dest="probe_scan_rows", type=int, default=None,
            help="READ CAP: max rows one candidate probe scans (probe_truncated)")
        sub.choices[name].add_argument(
            "--probe-distinct-values", dest="probe_distinct_values", type=int, default=None,
            help="READ CAP: max distinct values one probe may see (distinct_truncated)")
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

    caps = _caps_from_args(args)
    db = SessionLocal()
    rc = 0
    try:
        for rule in rules:
            try:
                if args.cmd == "classify":
                    print(_report_classify(ea.classify_queue(
                        db, rule, max_keys=args.max_keys, limit=args.limit,
                        caps=caps, log=lambda m: print(f"  {m}"))))
                elif args.cmd == "propose":
                    print(_report_propose(ea.analyze_promotions(
                        db, rule, min_support=args.min_support, limit=args.limit,
                        log=lambda m: print(f"  {m}"))))
                else:
                    print(_report_confirm(ea.run_auto_confirm_sweep(
                        db, rule, apply=args.apply, limit=args.limit,
                        ignore_knob=args.ignore_knob, caps=caps,
                        log=lambda m: print(f"  {m}"))))
            except ea.AnalysisRefused as e:
                print(f"REFUSED [{rule['name']}]: {e}")
                rc = 2
    finally:
        db.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
