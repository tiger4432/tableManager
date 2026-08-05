"""Read-only enrichment analytics: [④] why a gap exists, [②] which judgement
has become a rule — plus [①]'s retroactive sweep, whose dry-run is the
measurement.

These are analytical queries (they walk the whole queue), so they never sit on a
request path unbounded. `apply` is opt-in everywhere and dry-run is the default,
the same posture as `backfill_enrichment.py`.

THIS MODULE RUNS IN THREE PROCESSES, NOT ONE
    The CLI (`server/scripts/enrichment_insights.py`) was the first caller and
    this docstring used to say it was the only one. It is not, and believing it
    was is what shipped a defect: the retroactive admin surface calls the sweep
    from the WEB process (`GET /admin/retroactive/enrichment_confirm/count`,
    `GET /admin/enrichment/auto-confirm/dry-run`) and from the SCHEDULER process
    (`retroactive.execute`, behind `POST /admin/retroactive/{op}/run`). Anything
    this module imports must therefore resolve in all three - see the note on the
    queue predicate below.

WHY THE THREE LIVE TOGETHER
    They walk the same two row sets - the queue (target blank, keys non-blank)
    and its resolved complement - through the same keyset-paginated iterator.
    Three copies of that walk is how a predicate drifts into three answers, which
    is the mistake `queue_filters` was created to undo (spec §5.1).

THE QUEUE PREDICATE IS NOT REDEFINED HERE
    `iter_derived_rows` builds its SQL from
    `enrichment_config.queue_predicate_condition` - the server's single
    implementation of "which rows still need work" - which is the same function
    `GET /tables/{t}/data?enrichment_queue=<rule>` runs for the worklist, the
    badge and the admin count. So those surfaces and these reports cannot
    disagree about which rows are in the queue.

    THE QUEUE IS *ANY* TARGET BLANK  [2026-08-05, user ruling]
    It used to be composed here out of `queue_filters`, one `blank` spec per
    target field, conjoined - so on a multi-target rule it meant EVERY target
    blank, and filling one column dropped the row out of the queue while its
    sibling was still empty. Both live rules declare two targets. The repair
    needs a cross-column OR, which the public filter DSL cannot express, so the
    queue stopped being a client-visible filter dict and became a NAMED
    server-side predicate asked for by name.

    WHICH scope each caller takes is the load-bearing part. `queue` is the whole
    queue, because the progress bar's denominator counts every derived row and
    the remainder has to count the same population (N36). `keyed` adds "every
    decision key non-blank"; `blank_key` is its complement inside the queue.

    THE WRITE PATH NO LONGER TAKES THE KEYED COMPOSITION  [2026-08-05, user ruling]
    It did until now, and this docstring said the sweep "may not touch" blank-key
    rows. The ruling is the opposite and its reasoning is that `auto_confirm` IS
    the consent: it is per-rule, it is off unless declared, and whoever declares
    it has accepted unattended writes for that rule. A second gate underneath it
    would be code holding an opinion about operational behaviour that config
    already decided. So `run_auto_confirm_sweep` walks SCOPE_QUEUE and works
    whatever survives of each key; what refuses is arithmetic, not policy, and it
    refuses down in `resolve_target_candidate` where the evidence actually is
    (`missing_bind` per view, `no_decision_key` when nothing survives at all).

    ② (`propose_rules`) still walks SCOPE_KEYED, and that is not a leftover: it
    learns "this key determined this value" from RESOLVED rows, and a row missing
    part of its key cannot teach that - the judgement it records would be
    attributed to columns that were not there. ④ (`classify_queue`) walks both
    and names the blank-key rows (`blank_decision_key`), which keeps its total
    equal to the worklist remainder and the badge.

    That translator used to be reached as `main.get_column_filter_condition`, and
    the import was lazy so that a worker would not drag the web app in. The lazy
    import did not make `main` SAFE, only late: the scheduler puts every
    collector's directory on `sys.path[0]`, so in that process `import main` binds
    whatever `main.py` a user happens to have put there, and the sweep died with
    `module 'main' has no attribute 'get_column_filter_condition'` while the same
    run from the CLI worked. The translator now lives in `column_filter.py`, which
    is not an entry point and is not called `main`.
"""
import logging

import keyset_scan

logger = logging.getLogger(__name__)

# Keyset page size for the derived-table walk. The derived table is the
# deduplicated side (its cardinality is the number of decision-key identities,
# not the source row count), but it is still walked in pages and never loaded
# whole.
SCAN_CHUNK = 1000

# Chunk for the source-side grouped lookups (shared 1000-row discipline; the key
# IN-list bound mirrors enrichment_mapper.RECOUNT_KEY_CHUNK).
KEY_CHUNK = 500

SAMPLES_PER_CLASS = 5

# Which scope of the named queue predicate a walk uses. The definitions live in
# `enrichment_config.QUEUE_SCOPE_*`; `_queue_condition` maps these onto them.
SCOPE_KEYED = "keyed"
SCOPE_BLANK_KEY = "blank_key"
# The whole queue: ANY target field blank, no key predicate at all - the same
# scope the worklist and the progress remainder ask the route for. This is what
# the sweep walks, so the population it examines is the population the operator
# sees.
SCOPE_QUEUE = "queue"

# ④ classes. The first two are the BUG class: a human filling one of these is
# paying off a pipeline defect.
CLS_MAPPING_GAP = "mapping_gap_same_name"
CLS_BLANK_DECISION_KEY = "blank_decision_key"
CLS_NO_SOURCE_ROWS = "no_source_rows"
CLS_RESOLVABLE = "resolvable_from_reference"
# SOME blank targets resolve to one candidate and some do not [2026-08-05].
# Split out of CLS_RESOLVABLE, which used to swallow it on `any(single)` - so a
# row whose second column was ambiguous was reported as needing no human, and the
# work it still held vanished from the report. It is not CLS_AMBIGUOUS either:
# part of this row IS mechanically decided and the sweep will fill it.
CLS_PARTIALLY_RESOLVABLE = "partially_resolvable"
CLS_AMBIGUOUS = "ambiguous_reference"
CLS_NO_EVIDENCE = "no_evidence"
CLS_UNPROBED = "unprobed"

# `blank_decision_key` is a BUG class and the strongest member of it: the other
# bug class costs a human one row of manual work, this one cannot be worked at
# all. The reference views are bound to the key's value, so with no key there is
# nothing to look up - the row can only be fixed upstream. It became visible on
# 2026-08-04 when `queue_filters` stopped hiding it (see enrichment_config).
BUG_CLASSES = (CLS_MAPPING_GAP, CLS_BLANK_DECISION_KEY)
# A partially resolvable row STILL NEEDS A HUMAN, for the columns that did not
# resolve, so it belongs to the work total even though a machine will fill part
# of it. Counting it under `resolvable` instead (as `any(single)` did) understated
# the work by exactly the rows the sweep can only half finish.
REAL_WORK_CLASSES = (CLS_AMBIGUOUS, CLS_NO_EVIDENCE, CLS_PARTIALLY_RESOLVABLE)


class AnalysisRefused(Exception):
    """Raised when an analysis must not proceed. The message states why."""


# ---------------------------------------------------------------------------
# Shared row walk
# ---------------------------------------------------------------------------

def _queue_condition(table_model, rule: dict, resolved: bool = False,
                     scope: str = SCOPE_KEYED):
    """SQL condition for the queue predicate (or its resolved complement).

    🔴 THIS IS A LOOKUP, NOT A DEFINITION. The predicate lives in
    `enrichment_config.queue_predicate_condition` - the same function the route
    `GET /tables/{t}/data?enrichment_queue=<rule>` runs for the worklist, the
    badge and the admin count. This wrapper exists only to map this module's
    scope vocabulary onto it and to raise this module's refusal type.

    It used to compose the condition here out of `queue_filters`, and that is how
    the defect reached the reports too: the composition was a CONJUNCTION of
    per-target `blank` specs, so a partly filled row was outside the queue on
    every surface at once. `resolved=True` is meaningful for SCOPE_KEYED only.
    """
    import enrichment_config

    if resolved and scope == SCOPE_KEYED:
        named = enrichment_config.QUEUE_SCOPE_RESOLVED
    else:
        named = {
            SCOPE_QUEUE: enrichment_config.QUEUE_SCOPE_QUEUE,
            SCOPE_KEYED: enrichment_config.QUEUE_SCOPE_KEYED,
            SCOPE_BLANK_KEY: enrichment_config.QUEUE_SCOPE_BLANK_KEY,
        }.get(scope)
        if named is None:
            raise AnalysisRefused(f"unknown queue scope '{scope}'")
    try:
        return enrichment_config.queue_predicate_condition(table_model, rule,
                                                           scope=named)
    except enrichment_config.QueuePredicateError as e:
        raise AnalysisRefused(str(e))


def iter_derived_rows(db, rule: dict, resolved: bool = False, limit: int = None,
                      extra_columns: list = None, scope: str = SCOPE_KEYED):
    """Yield derived rows matching the queue predicate (or its complement).

    Keyset pagination on `row_id` (PK) - no OFFSET, no full load. Yields dicts
    of {row_id, business_key_val, keys{}, targets{}, extra{}}.
    """
    from database import models

    model = models.DYNAMIC_TABLES.get(rule["derived_table"])
    if model is None:
        raise AnalysisRefused(
            f"derived table model '{rule['derived_table']}' is not initialized "
            f"(is it registered in table_config.json?)")

    decision_key = rule["decision_key"]
    target_fields = rule["target_fields"]
    extra = [c for c in (extra_columns or []) if hasattr(model, c)]
    cols = ([model.business_key_val]
            + [getattr(model, c) for c in decision_key]
            + [getattr(model, c) for c in target_fields]
            + [getattr(model, c) for c in extra])
    cond = _queue_condition(model, rule, resolved=resolved, scope=scope)

    # `keyset_scan.iter_pages` prepends row_id as the cursor, so `cols` must not
    # repeat it - the shared walk owns the cursor.
    for page in keyset_scan.iter_pages(db, model, columns=cols, condition=cond,
                                       chunk_size=SCAN_CHUNK, limit=limit):
        for row in page:
            i = 2
            keys = dict(zip(decision_key, row[i:i + len(decision_key)]))
            i += len(decision_key)
            targets = dict(zip(target_fields, row[i:i + len(target_fields)]))
            i += len(target_fields)
            yield {
                "row_id": row[0], "business_key_val": row[1],
                "keys": keys, "targets": targets,
                "extra": dict(zip(extra, row[i:])),
            }


def _typed_key_values(rule: dict, keys: dict) -> tuple:
    """(clean_key_tuple, typed_raw_tuple) for source-side binding.

    Mirrors `enrichment_mapper.map_enrichment_dedup`: the source column's
    DECLARED type governs the cast, so a number-declared key binds as a number
    and the index is actually used.
    """
    from database import crud

    src_types = (crud.TABLE_CONFIG.get(rule["source_table"], {}).get("column_types", {}))
    clean, raw = [], []
    for k in rule["decision_key"]:
        sv = crud.clean_str_value(keys.get(k))
        if sv == "":
            return None, None
        clean.append(sv)
        raw.append(crud.cast_value_by_type(sv, src_types.get(k, "string"), k))
    return tuple(clean), tuple(raw)


def _source_target_presence(db, rule: dict, target_field: str, key_raw_values: dict) -> dict:
    """Per key: how many SOURCE rows carry a NON-BLANK value for `target_field`?

    Sibling of `enrichment_mapper._recount_affected_keys` - same chunked
    `(k1,..) IN (...) GROUP BY` shape, same reason (the affected key set is far
    smaller than the row set, and no full scan is ever issued). Returns {} when
    the source table has no such column, which is the honest answer to "did the
    source ever have it": it could not have.
    """
    from sqlalchemy import func, tuple_, cast, String, and_, or_
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(rule["source_table"])
    if model is None:
        raise AnalysisRefused(f"source table model '{rule['source_table']}' is not initialized")
    if not hasattr(model, target_field):
        return {}

    cols = [getattr(model, k) for k in rule["decision_key"]]
    tgt = getattr(model, target_field)
    # THE shared notBlank spelling, not a third copy. `cast(..., String)` stays because
    # `target_field` can name a numeric column and `crud.not_blank_sql_condition` compares
    # against `''` - the caller owns making the expression text-typed (documented on that
    # helper). This is byte-for-byte the predicate that used to be written out here.
    non_blank = crud.not_blank_sql_condition(cast(tgt, String))

    out = {}
    items = list(key_raw_values.items())
    for i in range(0, len(items), KEY_CHUNK):
        chunk = items[i:i + KEY_CHUNK]
        if len(cols) == 1:
            cond = cols[0].in_([raw[0] for _, raw in chunk])
        else:
            cond = tuple_(*cols).in_([tuple(raw) for _, raw in chunk])
        rows = (db.query(*cols, func.count().label("cnt"))
                .filter(cond, non_blank).group_by(*cols).all())
        for row in rows:
            key = tuple(crud.clean_str_value(v) for v in row[:-1])
            out[key] = int(row[-1])
    return out


# ---------------------------------------------------------------------------
# ④ Classify the cause of a gap
# ---------------------------------------------------------------------------

def classify_queue(db, rule: dict, probe_limit: int = 200, limit: int = None,
                   log=logger.info) -> dict:
    """Split the current queue into named cause classes. READ ONLY.

    The queue mixes two fundamentally different things and charges a human for
    both:
      - the source never had it            -> real work
      - the source HAS it and nothing carried it across -> a BUG; filling it by
        hand means a person is paying off a pipeline defect, forever, one row at
        a time.
    Classification separates them once.

    Two further classes fall out of ①'s predicate and are worth separating
    because they are not human judgement either: a key whose DECLARED reference
    views leave exactly ONE candidate is mechanically resolvable (that is ①),
    while >=2 candidates is exactly the judgement the queue is for.

    A ROW IS ONE CLASS; A COLUMN IS ONE VERDICT  [2026-08-05]
    On a multi-target rule those are not the same statement, and this used to
    pretend they were: `any(single)` filed a row under `resolvable` the moment ONE
    of its blank columns resolved, so a row that ① can only half finish reported
    as needing no human at all. The row classes now distinguish fully from
    `partially_resolvable`, and `target_verdicts` carries the per-COLUMN account
    beside them - which column was ambiguous, which returned nothing, which no
    view declares a candidate for. Those are three different instructions to
    whoever reads the report.

    HONEST LIMITS (stated, not hidden):
    - The bug class is detected by COLUMN NAME on the source table. A source
      column carrying the value under a DIFFERENT name cannot be found without a
      declaration, and this module will not guess one (the overlay DECOY
      lesson). If a real case appears, declare it rather than infer it.
    - The reference probe costs one query per declaring view per key, so it is
      bounded by `probe_limit`. Keys past the budget are reported as
      `unprobed` - never silently folded into another class.
    """
    from database import crud

    counts = {}
    samples = {}
    reason_detail = {}
    # COLUMN grain, beside the row-grain `counts`: {target_field: {"single"|reason: n}}.
    # `counts` can only put a row in one class, so on a multi-target rule it cannot
    # say which COLUMN was ambiguous and which was simply never asked. This can.
    target_verdicts = {}

    target_fields = list(rule["target_fields"])
    src_cfg = crud.TABLE_CONFIG.get(rule["source_table"], {})
    src_cols = set(src_cfg.get("column_types", {}).keys())
    same_name_targets = [t for t in target_fields if t in src_cols]

    rows = list(iter_derived_rows(db, rule, resolved=False, limit=limit))
    # The blank-key rows are part of the queue the operator SEES (2026-08-04), so
    # they are part of the total this report accounts for - otherwise `classify`
    # and the worklist badge would disagree by exactly their count and the
    # FEATURE_CHECKLIST reconciliation would start reading as a defect. They are
    # walked separately because everything below this line needs a key.
    keyless = list(iter_derived_rows(db, rule, limit=limit, scope=SCOPE_BLANK_KEY))
    log(f"[classify] rule '{rule['name']}': {len(rows) + len(keyless)} queue "
        f"entr{'y' if len(rows) + len(keyless) == 1 else 'ies'} "
        f"({len(keyless)} without a decision key)")

    # 1) Source-side facts for the whole queue, in chunked grouped queries.
    key_raw = {}
    row_key = {}
    for r in rows:
        clean, raw = _typed_key_values(rule, r["keys"])
        if clean is None:
            continue
        key_raw.setdefault(clean, raw)
        row_key[r["row_id"]] = clean

    from enrichment_mapper import _recount_affected_keys
    total_per_key = _recount_affected_keys(
        db, rule["source_table"], rule["decision_key"], key_raw) if key_raw else {}
    presence = {t: _source_target_presence(db, rule, t, key_raw) for t in same_name_targets}

    # 2) Per row: cheap classes first, reference probe only for what survives.
    import enrichment_candidates
    probed = 0

    def bump(cls, r, detail=None):
        counts[cls] = counts.get(cls, 0) + 1
        if len(samples.setdefault(cls, [])) < SAMPLES_PER_CLASS:
            samples[cls].append({"business_key_val": r["business_key_val"], "detail": detail})

    for r in keyless:
        missing = [k for k in rule["decision_key"]
                   if crud.clean_str_value(r["keys"].get(k)) == ""]
        bump(CLS_BLANK_DECISION_KEY, r,
             f"decision key {missing} blank - no reference view can be bound, so "
             f"this row cannot be resolved here; fix it upstream")

    for r in rows:
        key = row_key.get(r["row_id"])
        blanks = [t for t in target_fields if crud.clean_str_value(r["targets"].get(t)) == ""]
        if key is None:
            # Reached only when the SQL notBlank and `clean_str_value` disagree
            # (a whitespace-only key passes the first and folds to '' in the
            # second). Same fact as the class above, so it is named the same.
            bump(CLS_BLANK_DECISION_KEY, r, "decision key is whitespace-only in the derived row")
            continue
        if total_per_key.get(key, 0) == 0:
            bump(CLS_NO_SOURCE_ROWS, r, "no source rows for this decision key")
            continue
        gap = [t for t in blanks if presence.get(t, {}).get(key, 0) > 0]
        if gap:
            bump(CLS_MAPPING_GAP, r,
                 f"source '{rule['source_table']}' has non-blank {gap} for this key")
            continue
        if probed >= probe_limit:
            bump(CLS_UNPROBED, r, f"reference probe budget ({probe_limit}) exhausted")
            continue
        probed += 1
        # ONE VERDICT PER BLANK COLUMN, and the row's class is a function of the
        # SET of them - not of the first one that happened to succeed.
        verdicts = [enrichment_candidates.resolve_target_candidate(db, rule, r["keys"], t)
                    for t in blanks]
        for v in verdicts:
            name = ("single" if v["status"] == enrichment_candidates.STATUS_SINGLE
                    else v["reason"])
            slot = target_verdicts.setdefault(v["target_field"], {})
            slot[name] = slot.get(name, 0) + 1
        singles = [v for v in verdicts if v["status"] == enrichment_candidates.STATUS_SINGLE]
        still_open = [v for v in verdicts if v["status"] != enrichment_candidates.STATUS_SINGLE]
        decided = ", ".join(f"{v['target_field']}={v['value']!r} (support {v['support']})"
                            for v in singles[:SAMPLES_PER_CLASS])
        if singles and not still_open:
            bump(CLS_RESOLVABLE, r, decided)
        elif singles:
            bump(CLS_PARTIALLY_RESOLVABLE, r,
                 decided + "; still open: " + ", ".join(
                     f"{v['target_field']}:{v['reason']}"
                     for v in still_open[:SAMPLES_PER_CLASS]))
        elif any(v["reason"] == enrichment_candidates.REASON_AMBIGUOUS for v in verdicts):
            amb = next(v for v in verdicts
                       if v["reason"] == enrichment_candidates.REASON_AMBIGUOUS)
            bump(CLS_AMBIGUOUS, r,
                 f"{amb['target_field']}: {amb.get('distinct_count')} candidates "
                 f"{amb['candidates']}")
        else:
            first = verdicts[0] if verdicts else None
            reason = first["reason"] if first else "no_blank_target"
            reason_detail[reason] = reason_detail.get(reason, 0) + 1
            bump(CLS_NO_EVIDENCE, r, f"refusal: {reason}")

    return {
        "rule": rule["name"],
        "source_table": rule["source_table"],
        "derived_table": rule["derived_table"],
        # The whole queue as the operator sees it, so this reconciles with the
        # worklist remainder and the badge (FEATURE_CHECKLIST ④).
        "queue_size": len(rows) + len(keyless),
        "blank_decision_key": len(keyless),
        "counts": counts,
        "samples": samples,
        "target_verdicts": target_verdicts,
        "no_evidence_reasons": reason_detail,
        "probe_limit": probe_limit,
        "probed": probed,
        "same_name_targets_checked": same_name_targets,
        "unchecked_targets": [t for t in target_fields if t not in same_name_targets],
    }


# ---------------------------------------------------------------------------
# ② Promote a repeated judgement to a rule
# ---------------------------------------------------------------------------

def _human_resolved_cells(db, derived_table: str, row_ids: list, target_fields: list) -> set:
    """(row_id, column) pairs whose value was written by a HUMAN.

    A promotion must be mined from human judgements only. A value written by any
    machine source (a backfill, a previous auto-confirm) is not evidence that a
    person decided anything, and promoting from it would launder a machine guess
    into a rule. `source_name == 'user'` is the one layer that means "a human
    typed this" (crud.SOURCE_PRIORITY comment).
    """
    from database import models

    out = set()
    row_ids = [r for r in row_ids if r]
    for i in range(0, len(row_ids), SCAN_CHUNK):
        chunk = row_ids[i:i + SCAN_CHUNK]
        rows = (db.query(models.CellSource.row_id, models.CellSource.column_name)
                .filter(models.CellSource.table_name == derived_table,
                        models.CellSource.row_id.in_(chunk),
                        models.CellSource.column_name.in_(list(target_fields)),
                        models.CellSource.source_name == "user")
                .all())
        out.update(rows)
    return out


def analyze_promotions(db, rule: dict, min_support: int = 3, limit: int = None,
                       log=logger.info) -> dict:
    """Find repeated human judgements that have become a functional rule.

    PROPOSES ONLY - never writes config. A rule promoted from a wrong pattern
    fossilises that error across N rows, and stale-source withdrawal (Chain
    Replay R2) does not exist yet, so there is no retraction path. The output is
    text for a person to read and paste, deliberately.

    THE ANTECEDENT IS A PROPER SUBSET OF THE DECISION KEY, and that is not an
    arbitrary choice - it is what the existing contract permits. A promoted rule
    is expressed as a reference view (§5 `reference_views`) whose bind params
    `_validate_view_sql` restricts to decision_key columns. So the only shape
    that can actually run is "part of the key determines the target".

    WHY A REFERENCE VIEW AND NOT A NEW MAPPER
        The promoted artifact must be something this system ALREADY executes. A
        reference view plus a `candidate_for` declaration is executed by ①: the
        next key with the same antecedent resolves to a single candidate and is
        confirmed with zero human interaction. No new executor, no mapper code,
        no second definition of "apply a rule".
        It also inherits ①'s safety for free: if the antecedent later maps to two
        different values, the view returns two candidates and ① REFUSES - the
        item degrades back to a human judgement instead of fossilising. That is
        the closest thing to retraction available before R2.
    """
    from itertools import combinations
    from database import crud
    import enrichment_config

    decision_key = list(rule["decision_key"])
    target_fields = list(rule["target_fields"])
    derived_table = rule["derived_table"]

    # Proper non-empty subsets only. A full-key antecedent promotes nothing (it
    # is the row itself); with a single-column key there is no proper subset.
    antecedents = [list(c) for n in range(1, len(decision_key))
                   for c in combinations(decision_key, n)]
    if not antecedents:
        return {
            "rule": rule["name"], "refused": "no_proper_subset",
            "detail": (f"decision_key {decision_key} has one column, so no proper subset "
                       f"exists. A promotion says 'part of the key determines the target'; "
                       f"with a single-column key there is no part."),
            "proposals": [], "conflicts": [], "resolved_rows": 0,
        }

    rows = list(iter_derived_rows(db, rule, resolved=True, limit=limit))
    human = _human_resolved_cells(db, derived_table, [r["row_id"] for r in rows], target_fields)
    log(f"[propose] rule '{rule['name']}': {len(rows)} resolved row(s), "
        f"{len(human)} human-written target cell(s)")

    # antecedent_key -> target -> antecedent_value -> {target_value: support}
    observed = {}
    for r in rows:
        for t in target_fields:
            if (r["row_id"], t) not in human:
                continue
            tval = crud.clean_str_value(r["targets"].get(t))
            if tval == "":
                continue
            for ant in antecedents:
                avals = [crud.clean_str_value(r["keys"].get(c)) for c in ant]
                if any(v == "" for v in avals):
                    continue
                bucket = (observed.setdefault(tuple(ant), {})
                          .setdefault(t, {}).setdefault(tuple(avals), {}))
                bucket[tval] = bucket.get(tval, 0) + 1

    proposals, conflicts = [], []
    for ant, by_target in sorted(observed.items()):
        for t, by_value in sorted(by_target.items()):
            entries, bad = [], []
            for aval, tvals in sorted(by_value.items()):
                support = sum(tvals.values())
                if len(tvals) > 1:
                    bad.append({"antecedent": dict(zip(ant, aval)),
                                "target_values": sorted(tvals), "support": support})
                elif support >= min_support:
                    entries.append({"antecedent": dict(zip(ant, aval)),
                                    "value": next(iter(tvals)), "support": support})
            if bad:
                conflicts.append({
                    "antecedent_columns": list(ant), "target_field": t,
                    "conflicting_values": bad[:SAMPLES_PER_CLASS],
                    "conflict_count": len(bad),
                    "why_rejected": (
                        f"{list(ant)} does not determine '{t}': the same antecedent value "
                        f"resolved to more than one target value, so this is not a rule."),
                })
                continue
            if not entries:
                continue
            view = _proposed_reference_view(rule, ant, t, entries)
            err = enrichment_config._validate_view_sql(view["query"], decision_key)
            if err is not None:
                # Never propose something the real loader would reject.
                conflicts.append({"antecedent_columns": list(ant), "target_field": t,
                                  "why_rejected": f"generated view rejected by the loader: {err}"})
                continue
            proposals.append({
                "antecedent_columns": list(ant), "target_field": t,
                "distinct_antecedent_values": len(entries),
                "total_support": sum(e["support"] for e in entries),
                "entries": entries[:SAMPLES_PER_CLASS],
                "entry_count": len(entries),
                "reference_view": view,
            })

    return {"rule": rule["name"], "refused": None, "min_support": min_support,
            "resolved_rows": len(rows), "human_cells": len(human),
            "proposals": proposals, "conflicts": conflicts}


def _proposed_reference_view(rule: dict, antecedent: tuple, target_field: str,
                             entries: list) -> dict:
    """Render the promotion as a `reference_views` entry ① can execute.

    The lookup source is the DERIVED TABLE ITSELF: the judgements already stored
    there are the rule. That keeps the proposal declarative (SQL + a
    `candidate_for` declaration, no code) and self-maintaining - a newly resolved
    key immediately participates, and a contradiction immediately makes ① refuse.
    """
    derived = rule["derived_table"]
    where = " AND ".join(f"{c} = :{c}" for c in antecedent)
    query = (f"SELECT DISTINCT {target_field} FROM {derived} "
             f"WHERE {where} AND {target_field} IS NOT NULL AND {target_field} <> ''")
    return {
        "label": f"promoted: {'+'.join(antecedent)} -> {target_field}",
        "query": query,
        "candidate_for": {target_field: target_field},
        "limit": 200,
    }


# ---------------------------------------------------------------------------
# ① Retroactive sweep — the dry-run IS the measurement
# ---------------------------------------------------------------------------

def run_auto_confirm_sweep(db, rule: dict, apply: bool = False, limit: int = None,
                           ignore_knob: bool = False, log=logger.info) -> dict:
    """Apply ① to the EXISTING queue (the chain hook only sees new writes).

    Dry-run is the default and performs reads only, so this is also the
    instrument: "how many of today's queue items need no human at all" is a
    number this produces without writing anything.

    `ignore_knob` lets an operator MEASURE a rule whose `auto_confirm` is off
    (the honest default) - it is refused in apply mode, where the knob is the
    consent.

    THE WALK IS SCOPE_QUEUE, NOT SCOPE_KEYED  [2026-08-05, user ruling]
    So this examines the same population the operator's worklist shows, including
    rows whose decision key is only partly present. Those resolve on the columns
    that survive and are written with `SOURCE_NAME_PARTIAL_KEY`, which is how the
    decision stays addressable afterwards. A row with NO surviving key refuses in
    `resolve_target_candidate` and is counted under `no_decision_key`.
    """
    import enrichment_candidates
    from database import crud

    if apply and not ignore_knob and not enrichment_candidates.rule_auto_confirm_enabled(rule):
        raise AnalysisRefused(
            f"rule '{rule['name']}' has '{enrichment_candidates.RULE_KNOB}' off "
            f"(default). Dry-run works regardless; to WRITE, set "
            f"\"{enrichment_candidates.RULE_KNOB}\": true on the rule in "
            f"enrichment_rules.json.")
    if apply and ignore_knob:
        raise AnalysisRefused(
            "--ignore-knob is a measurement-only flag and cannot be combined with --apply: "
            "the knob is where a human consents to automatic writes.")
    if not enrichment_candidates.candidate_target_fields(rule):
        raise AnalysisRefused(
            f"rule '{rule['name']}' declares no 'candidate_for' on any reference view, so "
            f"there is nothing to confirm. Declare which view column carries a target's "
            f"candidate - it is never guessed.")

    keyed = []
    for r in iter_derived_rows(db, rule, resolved=False, limit=limit, scope=SCOPE_QUEUE):
        blanks = [t for t in rule["target_fields"]
                  if crud.clean_str_value(r["targets"].get(t)) == ""]
        keyed.append({"row_id": r["row_id"], "business_key_val": r["business_key_val"],
                      "keys": r["keys"], "blank_targets": blanks})
    log(f"[confirm] rule '{rule['name']}': {len(keyed)} queue entr"
        f"{'y' if len(keyed) == 1 else 'ies'} to examine")

    stats = enrichment_candidates.confirm_keys(
        db, rule, keyed, apply=apply, tx_prefix="enrichment_sweep")
    stats["mode"] = "apply" if apply else "dry-run"
    stats["rule"] = rule["name"]
    stats["queue_size"] = len(keyed)
    if not apply:
        db.rollback()  # belt and braces: a dry-run holds no writes, make it structural
    enrichment_candidates.log_stats(rule["name"], stats, apply=apply)
    return stats
