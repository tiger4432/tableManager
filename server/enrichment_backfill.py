"""Retroactive enrichment backfill - apply an enrichment rule to source rows
that predate the rule.

Why this exists: the enrichment queue is outbox-increment driven.
`enrichment_mapper.map_enrichment_dedup` only consumes changed-row payloads, so
source rows ingested BEFORE a rule was declared never produce derived rows and
the worklist cannot see them. This module scans the source table once (keyset
pagination, chunked - never a full-table load), diffs the distinct decision-key
combinations against the derived table, and (only with `apply=True`) feeds the
NEW combinations through the REAL mapper and the REAL write path
(`crud.apply_batch_updates`, the same route the chain worker uses). There is no
second implementation of grouping / aggregation / business-key assembly - the
mapper output is used verbatim, only provenance fields are stamped.

TWO CALLERS, AND WHY THE LOGIC LIVES HERE RATHER THAN IN THE SCRIPT
-------------------------------------------------------------------
* the operator CLI, `server/scripts/backfill_enrichment.py` (unchanged path, same
  flags - `BACKFILL_GUIDE.md` prints those commands);
* `retroactive.py`, which is what `GET /admin/retroactive/enrichment_backfill/count`
  and the queued run behind `POST /admin/retroactive/enrichment_backfill/run`
  call.

The second caller is why this file exists. `run_backfill` used to live in
`server/scripts/backfill_enrichment.py`, and `server/scripts` is on NO runtime
process's `sys.path` - every file in there bootstraps `server/` for itself when
run as `__main__`, which makes `server/` importable FROM a script and never the
reverse. So the route's lazy `import backfill_enrichment` raised
`ModuleNotFoundError` the first time an operator pressed the button, while the
test suite stayed green because a test file had put `server/scripts` on `sys.path`
for its own use and pytest shares one interpreter.

The split is the one `chain_replay.py` <-> `scripts/chain_replay_cli.py` and
`enrichment_analysis.py` <->
`scripts/enrichment_insights.py` follow: **semantics in `server/`, argparse and
report formatting in `scripts/`.** The alternative - putting `server/scripts` on
`sys.path` - would make all fifteen scripts importable from the runtime, which is
a larger door than the one defect needed. `server/tests/prod_import_check.py`
holds the line.

Import side effects are deliberately nil beyond the module-level constants: the
heavy imports (`database`, `enrichment_mapper`, `keyset_scan`) happen inside the
functions that need them, so importing this module from a request handler costs
nothing.

Safety / provenance invariants:
- Pre-existing derived rows are NEVER part of the write batch (value gaps on
  them are the queue's job; this module only fixes row absence).
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
import json
import os
import uuid

SOURCE_NAME = "enrichment_backfill"
DEFAULT_CHUNK_SIZE = 1000
EXISTING_BK_FETCH_CHUNK = 5000
# IN-list size for the bounded existence probe. Same value the sibling batched
# existence checks use (`map_meta_registrar`, `enrichment_candidates`); a probe is
# capped by the sample anyway (retroactive.MAX_SCAN_LIMIT = 2000 source rows), so
# in practice this is one round trip.
BK_PROBE_CHUNK = 1000
PROGRESS_EVERY_CHUNKS = 50
SAMPLE_NEW_KEYS = 20


class BackfillRefused(Exception):
    """Raised when a run must not proceed. The message states why."""


def load_rule(rule_name: str, known_tables: dict, force_disabled: bool = False) -> dict:
    """Load and validate ONE rule via the real loader (enrichment_config).

    Uses `enrichment_config._validate_rule` deliberately: the public
    `validate_enrichment_rules` swallows rejection reasons into log warnings,
    while this path must fail loudly WITH the loader's reason.
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


# --- "which of these identities already exist" — two answers, one question -----
#
# `run_backfill` asks this once per source chunk. WHICH implementation answers it
# is the difference between a CLI run and a request-path preview, and the two are
# not interchangeable:
#
#   * A COMPLETE backfill means "new, measured against the whole derived table".
#     That is the preload, and it stays exactly as it was.
#   * A SAMPLED preview reads at most `scan_limit` source rows, and a preload
#     would still walk every derived identity — so `scan_limit` would not
#     actually bound the request. The probe resolves only the sample's own keys.
#
# Both memo their answers for the life of a run, so a key created by an early
# chunk is never re-classified as pre-existing by a later one. That invariant is
# load-bearing: `run_backfill` refines rows it created in earlier chunks (display
# hints, counts), and treating one as pre-existing would silently drop that write.

class _PreloadedKeys:
    """Every existing identity, snapshotted before the scan. The CLI's answer."""

    kind = "preload"

    def __init__(self, db, derived_model, log=print):
        self._keys = _load_existing_business_keys(db, derived_model)
        log(f"[backfill] derived '{derived_model.__table__.name}': "
            f"{len(self._keys)} existing identities loaded")

    def existing(self, bks) -> set:
        return {bk for bk in bks if bk in self._keys}


class _ProbedKeys:
    """Only the sample's identities, resolved by indexed IN. The preview's answer.

    Rides `business_key_val`, which every dynamic table indexes twice
    (`models.py`: the column's own `index=True` plus the composite
    `idx_<table>_bk`) — verified against the live catalogue, not assumed.

    Same shape as `map_meta_registrar`'s batched existence check: chunked IN plus
    a memo of what has already been answered. It is not a general replacement for
    the preload — on a full scan it would issue a probe per chunk for the whole
    table — which is why the caller picks by `scan_limit`, not by preference.

    One deliberate difference from the preload: it matches the STORED key exactly,
    where the preload compares `str(bk).strip()`. Exact is the truer answer here,
    because `crud.apply_batch_updates` also matches rows with a raw
    `business_key_val.in_(...)` — so on a key that only agrees after stripping,
    the probe predicts what a write would actually do and the preload does not.
    """

    kind = "probe"

    def __init__(self, db, derived_model, log=print):
        self._db = db
        self._model = derived_model
        self._present = set()
        self._absent = set()
        log(f"[backfill] derived '{derived_model.__table__.name}': bounded mode — "
            f"existing identities resolved per chunk (no full read)")

    def existing(self, bks) -> set:
        unknown = [bk for bk in bks
                   if bk not in self._present and bk not in self._absent]
        for i in range(0, len(unknown), BK_PROBE_CHUNK):
            chunk = unknown[i:i + BK_PROBE_CHUNK]
            found = {r[0] for r in self._db.query(self._model.business_key_val)
                     .filter(self._model.business_key_val.in_(chunk)).all()}
            self._present |= found
            # Caching ABSENCE is what keeps a key this run created classified as
            # new for the rest of the run — the same thing the preload's
            # before-the-scan snapshot does, by never containing it.
            self._absent |= (set(chunk) - found)
        return {bk for bk in bks if bk in self._present}


def run_backfill(db, rule: dict, apply: bool = False, limit: int = None,
                 chunk_size: int = DEFAULT_CHUNK_SIZE, log=print,
                 scan_limit: int = None, checkpoint=None) -> dict:
    """Scan + diff (+ optionally write). Returns a stats dict.

    Dry-run performs reads only. Apply mode commits per chunk (via
    apply_batch_updates' own commit), so a very large backfill is restartable
    and idempotent: re-running diffs against the now-existing derived keys.

    `limit` and `scan_limit` bound DIFFERENT things and only one of them bounds
    the cost. `limit` caps how many NEW derived identities a run is allowed to
    create; the source scan continues to the end of the table regardless, counting
    the rest into `limit_skipped`. `scan_limit` caps how many SOURCE ROWS are read
    at all, which is the only knob that makes this callable from a request path -
    the admin count route passes it, the CLI does not. A `scan_limit`ed result is a
    sample: `rows_scanned` is the denominator the caller must report alongside it.

    `scan_limit` also selects HOW existing derived identities are resolved
    (`_PreloadedKeys` vs `_ProbedKeys` above, reported as `existing_lookup`). A
    full run keeps the whole-table snapshot, because that is what "complete"
    means; a sample resolves only its own keys, because otherwise `scan_limit`
    bounded the source read while the derived read stayed unbounded.

    WHICH ROWS ARE ELIGIBLE IS NOT DECIDED HERE  [2026-08-05, partial-key ruling]
    It never should have been. This module has one job - find identities the
    derived table is missing - and "is this key usable" is the mapper's question,
    asked by the live chain path on every increment. There used to be a copy of
    that question in the scan loop, and the copy is why the ruling looked like a
    one-line edit to this file. It is not: relaxing the copy alone leaves the
    mapper refusing the same rows one call later, so the sweep writes exactly
    what it wrote before while reporting that it skipped nothing. The gate now
    lives once, in `map_enrichment_dedup`, and both paths call it.

    DRY-RUN BUCKETS, BEFORE AND AFTER (the operator approves these numbers):
      before: `skipped_blank`  = source rows with ANY blank decision-key column
      after:  `skipped_no_key` = source rows with NO decision key at all
              `partial_key_combinations` = NEW identities built on a partial key
      A partial-key row therefore moves OUT of the skip bucket and INTO
      `distinct_combinations`/`new_combinations` - i.e. `affected` on the admin
      preview can rise for data that did not change. The key was renamed so an
      un-updated reader breaks loudly instead of reporting the old name with the
      new meaning.
    """
    from database import crud, models, schemas
    from enrichment_mapper import map_enrichment_dedup
    import enrichment_config

    if limit is not None and limit <= 0:
        raise BackfillRefused(f"--limit must be a positive integer (got {limit})")
    if scan_limit is not None and scan_limit <= 0:
        raise BackfillRefused(f"scan_limit must be a positive integer (got {scan_limit})")

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

    # `scan_limit` picks the resolver, not a preference: it is exactly the signal
    # "this is a bounded sample". Without this the preload walked every derived
    # identity even for a 200-row preview, so `scan_limit` bounded the source read
    # and nothing else.
    existing_keys = (_ProbedKeys if scan_limit is not None else _PreloadedKeys)(
        db, drv_model, log=log)

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
        # 🔴 RENAMED, because its MEANING changed and a number whose meaning
        # changed under an unchanged name is how a dry-run starts lying.
        # `skipped_blank` (<=2026-08-05) = source rows with ANY blank decision-key
        # column. `skipped_no_key` = source rows with NO decision key at all -
        # nothing to match on, still a true fact worth counting. The rows that
        # moved out of this bucket are PARTIAL keys, and they did not vanish:
        # they are now in `distinct_combinations` / `new_combinations`, counted
        # again under `partial_key_combinations` so the operator can see how much
        # of a preview is new work the ruling admitted rather than work that was
        # always there. The rename is deliberate: an un-updated consumer gets a
        # KeyError, not a silently re-pointed number.
        "skipped_no_key": 0,
        # The OTHER refusal, kept apart because the repairs are different: this
        # one is a config gap on the DERIVED table (its key contract cannot give
        # a partial key its own identity, and forcing one would silently merge
        # rows), not a fact about the data. `map_enrichment_dedup` logs the exact
        # table_config line to add.
        "skipped_unexpressible_key": 0,
        "distinct_combinations": 0,
        "partial_key_combinations": 0,
        "already_derived": 0,
        "new_combinations": 0,
        "limit_skipped": 0,
        "created_rows": 0,
        "updated_rows": 0,
        "chunks": 0,
        "sample_new_keys": [],
        # Which of the two answers above was used. Reported rather than inferred:
        # "already_derived" means a different thing when it came from a sample.
        "existing_lookup": existing_keys.kind,
    }

    import keyset_scan

    combos_seen = set()
    partial_key_bks = set()  # identities whose decision key is only partly present
    already_bks = set()
    new_bks = set()          # dry-run: all new identities / apply: identities allowed in
    limit_skipped_bks = set()
    run_id = uuid.uuid4().hex[:8]

    # The shared keyset walk (`keyset_scan.iter_pages`) - one implementation of
    # "read a whole table in bounded pages", also used by chain_replay (R1) and
    # enrichment_analysis. It prepends row_id as the cursor.
    for rows in keyset_scan.iter_pages(
            db, src_model, columns=[getattr(src_model, c) for c in payload_cols],
            chunk_size=chunk_size, limit=scan_limit):
        if checkpoint is not None and checkpoint(stats["rows_scanned"]):
            stats["stopped"] = True
            log(f"[backfill] stopped by request after {stats['rows_scanned']} rows")
            break
        stats["chunks"] += 1
        stats["rows_scanned"] += len(rows)

        # Synthesize the outbox-payload shape the mapper expects, and hand EVERY
        # scanned row over. There used to be a blank-key filter here, described
        # as "the mapper's own primitives, byte-identical semantics" - and that
        # is exactly what made it dangerous. It was a SECOND SPELLING of the
        # mapper's eligibility rule, so the partial-key ruling looked like a
        # one-line edit to this file; measured, relaxing this line alone changed
        # no row (the mapper dropped the same rows one call later) and turned
        # `skipped_blank` from a true 1 into a false 0. The rule is asked once
        # now, where row creation actually happens, and the count comes back
        # from the same call that made the decision.
        payloads = [{"data": {col: {"value": val}
                              for col, val in zip(payload_cols, r[1:])}}
                    for r in rows]

        result = map_enrichment_dedup(db, payloads, rule=mapper_rule)
        items = result.get("updates") or []
        stats["skipped_no_key"] += result.get("skipped_no_key", 0)
        stats["skipped_unexpressible_key"] += result.get("skipped_unexpressible_key", 0)

        # One existence question per chunk instead of one per item. Keys this run
        # already claimed are excluded rather than re-asked: with the preload that
        # was a no-op (`new_bks` and the snapshot are disjoint by construction),
        # and with the probe it is what stops a row created in chunk 1 from being
        # read back as pre-existing in chunk 5 and losing its refinement write.
        chunk_bks = {item.get("business_key_val") for item in items} - new_bks
        chunk_bks.discard(None)
        present_bks = existing_keys.existing(chunk_bks) if chunk_bks else set()

        batch_items = []
        for item in items:
            combos_seen.add(tuple(item["updates"].get(k) for k in decision_key))
            bk = item.get("business_key_val")
            if bk in present_bks:
                # Pre-existing derived identity: value gaps are the queue's
                # job - the backfill never touches these rows.
                already_bks.add(bk)
                continue
            if bk not in new_bks:
                if limit is not None and len(new_bks) >= limit:
                    limit_skipped_bks.add(bk)
                    continue
                new_bks.add(bk)
                # Accounting only - the SAME shared predicate the mapper used to
                # let this row through, asked again of the item it produced. Not
                # a second gate: nothing here can admit or refuse a row.
                if enrichment_config.blank_key_columns(rule, item["updates"]):
                    partial_key_bks.add(bk)
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
    stats["partial_key_combinations"] = len(partial_key_bks)
    stats["already_derived"] = len(already_bks)
    stats["new_combinations"] = len(new_bks)
    stats["limit_skipped"] = len(limit_skipped_bks)
    return stats
