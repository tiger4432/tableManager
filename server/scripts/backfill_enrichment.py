"""Retroactive enrichment backfill - apply an enrichment rule to source rows
that predate the rule.

Why this exists: the enrichment queue is outbox-increment driven.
`enrichment_mapper.map_enrichment_dedup` only consumes changed-row payloads, so
source rows ingested BEFORE a rule was declared never produce derived rows and
the worklist cannot see them. This script scans the source table once (keyset
pagination, chunked - never a full-table load), diffs the distinct decision-key
combinations against the derived table, and (only with --apply) feeds the NEW
combinations through the REAL mapper and the REAL write path
(`crud.apply_batch_updates`, the same route the chain worker uses). There is no
second implementation of grouping / aggregation / business-key assembly - the
mapper output is used verbatim, only provenance fields are stamped.

Usage (dry-run is the default - report first, act only on explicit flag):

    conda run -n assy_manager python server/scripts/backfill_enrichment.py <rule_name>
    conda run -n assy_manager python server/scripts/backfill_enrichment.py <rule_name> --apply
    conda run -n assy_manager python server/scripts/backfill_enrichment.py <rule_name> --apply --limit 100

Flags:
    --apply           actually write the new derived rows (default: dry-run report)
    --limit N         cap the number of NEW derived identities created per run
    --force-disabled  run even if the rule has "enabled": false
    --chunk-size N    source scan chunk size (default 1000)

Safety / provenance invariants:
- Pre-existing derived rows are NEVER part of the write batch (value gaps on
  them are the queue's job; this script only fixes row absence).
- target_fields are never written - the real mapper never emits them.
- Written cells carry source_name="enrichment_backfill" (unregistered in
  SOURCE_PRIORITY -> priority 99): they can never outrank user edits
  (priority 0), and later chain_ingestion writes (priority 4) win the display
  value, which is desired - fresher increments supersede the backfill.
- Writes go through the normal outbox hook, so the graph materializer picks
  the new rows up. The chain worker sees the events too, but the enrichment
  chain rule triggers on the SOURCE table while these events are on the
  DERIVED table, so the same rule cannot re-fire; any other chain rule
  cascading off the derived table runs at most one step, because every
  chain-worker write is tagged source_name="chain_ingestion" and filtered by
  the worker's loop guard.
"""
import argparse
import json
import os
import sys
import uuid

# Standalone bootstrap: make server/ importable (same pattern as reapply_chain.py).
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

# NOTE: keep module import side-effect free beyond sys.path (tests import this
# module directly). Heavy imports happen lazily inside functions.

SOURCE_NAME = "enrichment_backfill"
DEFAULT_CHUNK_SIZE = 1000
EXISTING_BK_FETCH_CHUNK = 5000
PROGRESS_EVERY_CHUNKS = 50
SAMPLE_NEW_KEYS = 20


class BackfillRefused(Exception):
    """Raised when a run must not proceed. The message states why."""


def load_rule(rule_name: str, known_tables: dict, force_disabled: bool = False) -> dict:
    """Load and validate ONE rule via the real loader (enrichment_config).

    Uses `enrichment_config._validate_rule` deliberately: the public
    `validate_enrichment_rules` swallows rejection reasons into log warnings,
    while this script must fail loudly WITH the loader's reason.
    """
    import enrichment_config

    path = enrichment_config.ENRICHMENT_RULES_PATH
    if not os.path.exists(path):
        raise BackfillRefused(f"enrichment rules file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
    except Exception as e:
        raise BackfillRefused(f"failed to parse {path}: {e}")
    if not isinstance(raw_config, dict):
        raise BackfillRefused(f"{path} must be an object {{rule_name: rule}}")
    if rule_name not in raw_config:
        available = ", ".join(sorted(raw_config.keys())) or "<none>"
        raise BackfillRefused(
            f"rule '{rule_name}' not found in {path}; available rules: {available}"
        )

    raw = raw_config[rule_name]
    disabled = isinstance(raw, dict) and raw.get("enabled", True) is False
    if disabled and not force_disabled:
        raise BackfillRefused(
            f"rule '{rule_name}' is disabled (\"enabled\": false). "
            f"Pass --force-disabled to backfill a disabled rule anyway."
        )
    if disabled:
        # The loader silently drops disabled rules ((None, None)); the operator
        # explicitly forced this run, so validate it as if it were enabled.
        raw = {**raw, "enabled": True}

    normalized, err = enrichment_config._validate_rule(rule_name, raw, known_tables)
    if err is not None:
        raise BackfillRefused(f"rule '{rule_name}' rejected by the loader: {err}")
    if normalized is None:
        raise BackfillRefused(f"rule '{rule_name}' was not accepted by the loader")
    return normalized


def _load_existing_business_keys(db, derived_model) -> set:
    """All business_key_val values already present in the derived table.

    Keyset pagination on row_id (PK, indexed) - the derived table is the
    deduplicated side, so its cardinality is the number of decision-key
    identities, not the source row count.
    """
    import keyset_scan

    existing = set()
    for page in keyset_scan.iter_pages(db, derived_model,
                                       columns=[derived_model.business_key_val],
                                       chunk_size=EXISTING_BK_FETCH_CHUNK):
        for _, bk in page:
            if bk is not None and str(bk).strip() != "":
                existing.add(str(bk).strip())
    return existing


def run_backfill(db, rule: dict, apply: bool = False, limit: int = None,
                 chunk_size: int = DEFAULT_CHUNK_SIZE, log=print) -> dict:
    """Scan + diff (+ optionally write). Returns a stats dict.

    Dry-run performs reads only. Apply mode commits per chunk (via
    apply_batch_updates' own commit), so a very large backfill is restartable
    and idempotent: re-running diffs against the now-existing derived keys.
    """
    from database import crud, models, schemas
    from enrichment_mapper import map_enrichment_dedup, _cell_value

    if limit is not None and limit <= 0:
        raise BackfillRefused(f"--limit must be a positive integer (got {limit})")

    source_table = rule["source_table"]
    derived_table = rule["derived_table"]
    decision_key = rule["decision_key"]

    src_model = models.DYNAMIC_TABLES.get(source_table)
    if src_model is None:
        raise BackfillRefused(
            f"source table model '{source_table}' is not initialized "
            f"(is it registered in table_config.json?)"
        )
    drv_model = models.DYNAMIC_TABLES.get(derived_table)
    if drv_model is None:
        raise BackfillRefused(
            f"derived table model '{derived_table}' is not initialized "
            f"(is it registered in table_config.json?)"
        )

    # Columns the mapper reads from the payload: decision keys + display-hint
    # list_columns. list_columns are derived-table names; only those that also
    # exist on the source model can carry a value (identical to the chain path,
    # where a column absent from the source payload simply yields None).
    src_cols = {c.name for c in src_model.__table__.columns}
    missing_keys = [k for k in decision_key if k not in src_cols]
    if missing_keys:
        raise BackfillRefused(
            f"decision_key column(s) missing on source table model: {missing_keys}"
        )
    payload_cols = list(dict.fromkeys(
        decision_key + [c for c in rule.get("list_columns", []) if c in src_cols]
    ))

    existing_bks = _load_existing_business_keys(db, drv_model)
    log(f"[backfill] derived '{derived_table}': {len(existing_bks)} existing identities loaded")

    # In dry-run the count aggregations are irrelevant to identity diffing, so
    # strip them to skip the mapper's recount queries. Apply keeps them: counts
    # on the created rows come from the mapper's own idempotent recount.
    mapper_rule = {"enrichment": rule if apply else {**rule, "aggregations": {}}}

    stats = {
        "mode": "apply" if apply else "dry-run",
        "rule": rule["name"],
        "source_table": source_table,
        "derived_table": derived_table,
        "rows_scanned": 0,
        "skipped_blank": 0,
        "distinct_combinations": 0,
        "already_derived": 0,
        "new_combinations": 0,
        "limit_skipped": 0,
        "created_rows": 0,
        "updated_rows": 0,
        "chunks": 0,
        "sample_new_keys": [],
    }

    import keyset_scan

    combos_seen = set()
    already_bks = set()
    new_bks = set()          # dry-run: all new identities / apply: identities allowed in
    limit_skipped_bks = set()
    run_id = uuid.uuid4().hex[:8]

    # The shared keyset walk (`keyset_scan.iter_pages`) - one implementation of
    # "read a whole table in bounded pages", also used by chain_replay (R1) and
    # enrichment_analysis. It prepends row_id as the cursor.
    for rows in keyset_scan.iter_pages(
            db, src_model, columns=[getattr(src_model, c) for c in payload_cols],
            chunk_size=chunk_size):
        stats["chunks"] += 1
        stats["rows_scanned"] += len(rows)

        # Synthesize the outbox-payload shape the mapper expects. The blank
        # check below is composed of the mapper's own primitives (_cell_value +
        # crud.clean_str_value) - byte-identical semantics, counted here because
        # the mapper logs but does not return its skip count.
        payloads = []
        for r in rows:
            data = {col: {"value": val} for col, val in zip(payload_cols, r[1:])}
            if any(crud.clean_str_value(_cell_value(data, k)) == "" for k in decision_key):
                stats["skipped_blank"] += 1
                continue
            payloads.append({"data": data})
        if not payloads:
            continue

        result = map_enrichment_dedup(db, payloads, rule=mapper_rule)
        items = result.get("updates") or []

        batch_items = []
        for item in items:
            combos_seen.add(tuple(item["updates"].get(k) for k in decision_key))
            bk = item.get("business_key_val")
            if bk in existing_bks:
                # Pre-existing derived identity: value gaps are the queue's
                # job - the backfill never touches these rows.
                already_bks.add(bk)
                continue
            if bk not in new_bks:
                if limit is not None and len(new_bks) >= limit:
                    limit_skipped_bks.add(bk)
                    continue
                new_bks.add(bk)
                if len(stats["sample_new_keys"]) < SAMPLE_NEW_KEYS:
                    stats["sample_new_keys"].append(bk)
            if apply:
                stamped = dict(item)
                stamped["source_name"] = SOURCE_NAME
                stamped["updated_by"] = SOURCE_NAME
                batch_items.append(stamped)

        if apply and batch_items:
            batch = schemas.GeneralUpdateBatch(
                updates=batch_items,
                transaction_id=f"{SOURCE_NAME}_{run_id}_{stats['chunks']:06d}",
            )
            results, _changed, _logs, _deleted = crud.apply_batch_updates(
                db, derived_table, batch
            )
            for _row, is_new in results:
                if is_new:
                    stats["created_rows"] += 1
                else:
                    # A row this run created in an earlier chunk, refined by a
                    # later chunk (display hints / counts). Never a
                    # pre-existing row - those are filtered above.
                    stats["updated_rows"] += 1

        if stats["chunks"] % PROGRESS_EVERY_CHUNKS == 0:
            log(
                f"[backfill] progress: {stats['rows_scanned']} rows scanned, "
                f"{len(combos_seen)} combinations, {len(new_bks)} new"
            )

    if not apply:
        # Belt and braces: a dry-run holds no writes, make it structural.
        db.rollback()

    stats["distinct_combinations"] = len(combos_seen)
    stats["already_derived"] = len(already_bks)
    stats["new_combinations"] = len(new_bks)
    stats["limit_skipped"] = len(limit_skipped_bks)
    return stats


def format_report(stats: dict, limit: int = None) -> str:
    lines = [
        "",
        f"=== enrichment backfill {'APPLY' if stats['mode'] == 'apply' else 'DRY-RUN'} "
        f"- rule '{stats['rule']}' ===",
        f"  source table          : {stats['source_table']}",
        f"  derived table         : {stats['derived_table']}",
        f"  source rows scanned   : {stats['rows_scanned']}",
        f"  skipped (blank key)   : {stats['skipped_blank']}",
        f"  distinct combinations : {stats['distinct_combinations']}",
        f"  already derived       : {stats['already_derived']}  (NOT touched)",
    ]
    if stats["mode"] == "apply":
        lines.append(f"  new identities created: {stats['created_rows']}")
        if stats["updated_rows"]:
            lines.append(
                f"  refined in later chunks: {stats['updated_rows']} "
                f"(rows created by this run only)"
            )
        if stats["limit_skipped"]:
            lines.append(
                f"  skipped by --limit    : {stats['limit_skipped']} "
                f"(re-run to continue)"
            )
    else:
        would = stats["new_combinations"]
        lines.append(f"  new (would create)    : {would}")
        if limit is not None and stats["limit_skipped"]:
            lines.append(
                f"  ... of which beyond --limit {limit}: {stats['limit_skipped']}"
            )
        if would:
            lines.append(
                "  -> re-run with --apply to create them "
                "(target fields stay blank; the worklist picks them up)"
            )
    if stats["sample_new_keys"]:
        lines.append(f"  sample new keys       : {stats['sample_new_keys'][:SAMPLE_NEW_KEYS]}")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Retroactively apply an enrichment rule to source rows that predate "
            "it. Dry-run by default; nothing is written without --apply."
        )
    )
    parser.add_argument("rule_name", help="rule name as declared in enrichment_rules.json")
    parser.add_argument("--apply", action="store_true",
                        help="write the new derived rows (default: report only)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of NEW derived identities per run")
    parser.add_argument("--force-disabled", action="store_true",
                        help="run even if the rule is disabled (enabled: false)")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"source scan chunk size (default {DEFAULT_CHUNK_SIZE})")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.chunk_size <= 0:
        print(f"REFUSED: --chunk-size must be positive (got {args.chunk_size})")
        return 2

    from database import crud, models
    from database.database import SessionLocal

    if not crud.TABLE_CONFIG:
        print("REFUSED: table_config.json is empty or missing - nothing is registered")
        return 2
    models.init_dynamic_models(crud.TABLE_CONFIG)

    try:
        rule = load_rule(args.rule_name, crud.TABLE_CONFIG,
                         force_disabled=args.force_disabled)
    except BackfillRefused as e:
        print(f"REFUSED: {e}")
        return 2

    db = SessionLocal()
    try:
        stats = run_backfill(db, rule, apply=args.apply, limit=args.limit,
                             chunk_size=args.chunk_size)
        print(format_report(stats, limit=args.limit))
        return 0
    except BackfillRefused as e:
        print(f"REFUSED: {e}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
