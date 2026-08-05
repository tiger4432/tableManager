"""[Enrichment ①] A single candidate is a confirmation, not a judgement.

WHAT THIS IS
    The enrichment queue exists because a target value (e.g. `wafer_id`) cannot
    be derived by rule - it comes from a person's tacit knowledge
    (ENRICHMENT_QUEUE_SPEC §2). But that premise is not uniformly true per item.
    When the declared reference views yield EXACTLY ONE distinct value for a
    decision key, the human is not judging; they are agreeing with the only
    thing on screen. This module is the ONE server-side definition of that
    predicate, plus the absent-only writer that acts on it.

    On the V1 interaction-effort instrument (`effort_metric.py`, landed
    2026-07-29: score = key*1 + mouse*3 + nav*5) the same correction costs:
        typing it            -> 키n + 마우스3   (n keystrokes + the commit click)
        one-click confirm    -> 마우스3         (client half; see NOT BUILT below)
        automatic confirm    -> 0               (this module, knob ON)
    Because the instrument stores RAW COUNTS and scores at read time, the drop
    is measured from `InteractionEffortLog`, not asserted here: the transactions
    that never happen simply stop appearing. What this module can prove on its
    own is the count of queue items it can retire without a human
    (`enrichment_analysis.run_auto_confirm_sweep` dry-run) - see that report.

DECLARED, NEVER DERIVED
    A reference view is a candidate source only if it says so, via
    `candidate_for: {target_field: view_column}` (enrichment_config). The map
    overlay taught this the hard way: `derive_table_binding` guessed the first
    data column and attached a live DECOY. The user's real config is the
    argument - two views of the same rule both expose a `wafer_id` column, one
    keyed by (lot, slot) (one candidate) and one keyed by lot alone (N
    candidates). Any name-matching implementation auto-confirms garbage.

ABSENCE IS NOT ZERO (the refusal rules)
    Every refusal names its reason, and the strict ones matter more than the
    permissive ones:
    - `ambiguous` (>=2 distinct values) -> that IS the human judgement. Leave it.
    - `view_error` / `missing_bind` -> an unevaluated view is UNKNOWN, not
      empty. If ANY declaring view fails we refuse EVEN IF a surviving view
      returned exactly one value, because the failed one may have held the
      contradiction. (`resolve_target_candidate` still reports the partial
      finding so a UI can show it; `status` is what gates the write.)
    - `probe_truncated` / `distinct_truncated` -> the read itself was clipped
      (by rows, or by distinct groups). Same posture: an incomplete read is
      UNKNOWN, and "exactly one" is not provable from one. In particular a
      clipped read can FOLD back down to a single value under
      `crud.clean_str_value`, so the truncation has to refuse on its own rather
      than trust the `ambiguous` count.
      🔴 EACH ONE NAMES THE CAP THAT CUT IT [2026-08-05, live incident]. Three
      different numbers were all called `limit` - the CLI's key budget, the
      view's display row limit, and a module constant no operator could reach -
      and the refusal named none of them. Told to "raise the limit", the operator
      raised the only one within reach, which touches no read, and nothing
      changed. So a truncation now carries `cap` (its config name), `cap_value`,
      `cap_declared`, `cap_home` (the file and key to edit), and
      `expected_if_raised`: `ambiguous` when this read ALREADY holds >= 2 distinct
      values (a bigger cap renames the refusal, it does not resolve it), else
      `unknown`. A refusal that names no repair sends someone to a person.
    - `cell_has_provenance` -> the target cell already has a CellSource row
      from ANY writer. A human who deliberately cleared a value has said "not
      this"; re-confirming over that would erase a judgement. This is stricter
      than M3's row-absence check because the unit here is a cell.
    A refused key stays in the queue, visibly unresolved. Nothing is silently
    turned from unknown into a confident wrong value.

A COLUMN IS DECIDED ON ITS OWN EVIDENCE  [2026-08-05, user ruling]
    Ambiguity is a property of a COLUMN, not of a row. Two candidates that agree
    on `target_a` and differ on `target_b` have DETERMINED `target_a`; refusing
    both would be all-or-nothing where the evidence is not.
    `resolve_target_candidate` was already per (key, field) - the probe groups a
    single declared column - and `confirm_keys` already loops the fields
    independently, so the decision grain needed nothing new. What was missing was
    the ACCOUNT of it: refusals were tallied in one flat bag, so "column X was
    ambiguous" and "column Y was never asked" arrived as an undifferentiated
    total. `per_target` (below) indexes the same events by column.

    THE THREE FACTS A BLANK CAN CARRY, kept apart deliberately:
      - `ambiguous`      - we compared, and the candidates disagreed. A human
                           must judge; more evidence will not help.
      - `no_candidate`   - we asked, and the declared views returned nothing.
                           Go find evidence.
      - `not_declared`   - we NEVER ASKED. No reference view declares a candidate
                           column for this target, so no comparison happened.
                           This is a config gap, and it used to be invisible
                           whenever SOME other target on the same rule WAS
                           declared: the undeclared one was skipped in silence
                           and its blank read exactly like a judged one.

SAME SHAPE AS M3 (`auto_register_map_meta`, map_meta_registrar.py)
    Absent-only; writes carry `SOURCE_NAME` which is UNREGISTERED in
    `crud.SOURCE_PRIORITY` and therefore resolves to priority 99 - the lowest -
    so a later user edit (priority 0) always wins the displayed value and needs
    no special path. Knob read once per work unit (hot from the next unit,
    consistent within one). Non-boolean knob values warn once and fall back.
    Failure is isolated: it must never fail the ingestion/chain write.

    ONE DELIBERATE DIVERGENCE - THE DEFAULT IS OFF, where M3's is ON.
    M3 writes alignment geometry, which no queue consumes. This writes the very
    field whose blankness DEFINES queue membership (`to_public_rule`
    queue_filters: target blank), so a wrong auto-confirm makes the item LEAVE
    the worklist and stop being reviewed. There is also no retraction path yet
    (Chain Replay R2 stale-source withdrawal is not built). An opt-in default
    keeps that consequence a decision someone made, not a side effect of
    upgrading. Provenance stays auditable: the cell's `priority_source` reads
    `enrichment_auto_confirm` and the write lands in AuditLog like any other.

NOT BUILT HERE (needs lead approval - boundary contract + a held file)
    The ONE-CLICK confirm needs (a) the client to know which views are
    candidate sources, i.e. an additive field on `GET /enrichment/rules`, and
    (b) an endpoint to ask "is there a single candidate for this key". Both live
    in `server/main.py`, held by the concurrent ontology round, and both are
    boundary-contract changes. The predicate they would call is complete here,
    so neither would re-implement it.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

try:
    import paths
except ImportError:  # imported without server/ on sys.path (same guard as crud.py)
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paths

# Provenance of an automatic confirmation. Deliberately NOT added to
# crud.SOURCE_PRIORITY: unregistered -> 99 -> lowest, exactly like
# `auto_map_meta` and `enrichment_backfill`. Registering it would be the one
# edit that could let it outrank a human.
SOURCE_NAME = "enrichment_auto_confirm"

# THE PROVENANCE OF A DECISION MADE ON A PARTIAL KEY  [2026-08-05, user ruling]
# Same writer, same rank, different NAME. Also deliberately unregistered in
# `crud.SOURCE_PRIORITY` -> 99, byte-for-byte the standing of `SOURCE_NAME`, so
# this is not a layering change: it cannot outrank a human and it cannot outrank
# or be outranked by an ordinary auto-confirm.
#
# WHY A SOURCE NAME AND NOT A NEW FIELD
# `cell_sources` is already the per-cell answer to "how did this value come to
# be", and `source_name` is already how this path separates a human write
# (`user`) from a sweep (`enrichment_auto_confirm`). A partial-key decision is
# the same kind of fact, so it gets the same spelling rather than a column that
# only one writer would ever populate. The consequence is the point: when the
# missing key column finally arrives, "which cells were decided without a full
# key" is one predicate over `cell_sources.source_name` - an ANSWER, not a
# reconstruction. A decision that cannot be addressed cannot be re-derived.
SOURCE_NAME_PARTIAL_KEY = "enrichment_auto_confirm_partial_key"

# Per-rule knob in enrichment_rules.json. Per-rule rather than global because
# candidate reliability is a property of the rule's views, not of the server -
# and enrichment_rules.json is already re-read per work unit, so hot reload is
# inherited rather than reinvented.
RULE_KNOB = "auto_confirm"
DEFAULT_ENABLED = False

# Global kill switch, so an operator can stop every rule at once without
# editing N rules. Default True means "do not block" - the per-rule opt-in is
# still required, so the out-of-box behaviour is unchanged.
GLOBAL_KILL_SWITCH_KEY = "enrichment_auto_confirm_enabled"
INGESTION_SETTINGS_PATH = paths.config_path("ingestion_settings.json")

# Per work unit ceiling on how many decision keys we will probe. Each probed key
# costs one SQL round trip PER declaring reference view, so this is the only
# thing standing between a 10M-row ingestion and a query storm. Keys beyond the
# cap are NOT resolved and NOT lost - they stay in the queue and the skip is
# logged with its count (honest degradation, per the 10M-row rule).
MAX_KEYS_SETTINGS_KEY = "enrichment_auto_confirm_max_keys"
DEFAULT_MAX_KEYS_PER_UNIT = 200

# Shared chunk size for the batched existence/provenance lookups (the 1000-row
# chunking discipline).
CHUNK_SIZE = 1000

# Cap on how many distinct values an `ambiguous` refusal reports back, so a view
# that returns 200 rows of noise cannot produce a 200-element log line.
AMBIGUOUS_SAMPLE = 10

STATUS_SINGLE = "single"
STATUS_REFUSED = "refused"

REASON_NOT_DECLARED = "not_declared"
# The whole decision key is blank. Not a policy - arithmetic. Every view that
# binds anything refuses `missing_bind` on its own, but a view that binds NOTHING
# would run happily and return the same rule-wide constant for every keyless row,
# which is a value about no row in particular. Named here, before any probe, so
# the refusal does not depend on which views a rule happens to declare.
REASON_NO_DECISION_KEY = "no_decision_key"
# The row carries no `business_key_val`. Reachable only since blank-key rows
# entered the write path: the business key is usually COMPOSED from the decision
# key, so the rows most likely to be missing it are exactly these. The writer
# addresses by `row_id` first (`_get_or_create_row`), so this fires only when
# neither identifier is present - and then the alternative is an INSERT of a
# phantom row, not a write to the intended one.
REASON_NO_ROW_IDENTITY = "no_row_identity"
REASON_NO_CANDIDATE = "no_candidate"
REASON_AMBIGUOUS = "ambiguous"
REASON_VIEW_ERROR = "view_error"
REASON_MISSING_BIND = "missing_bind"
REASON_CANDIDATE_COLUMN_MISSING = "candidate_column_missing"
REASON_CELL_HAS_PROVENANCE = "cell_has_provenance"
REASON_OVER_CAP = "over_cap"
# The probe's ROW scan hit `enrichment_read_caps.probe_scan_rows`, so the read is
# TRUNCATED. "Exactly one candidate" is not provable from a truncated read - the
# unread remainder may hold the contradiction. Same posture as `view_error`: an
# incompletely evaluated view is UNKNOWN, not empty.
REASON_PROBE_TRUNCATED = "probe_truncated"
# The probe returned more DISTINCT groups than `enrichment_read_caps
# .probe_distinct_values` (undeclared: the view's own row `limit`), so the GROUP BY
# result itself was clipped. The same fact as `probe_truncated` one axis over - an
# incomplete read - and therefore the same named refusal, not a hint.
#
# It used to carry no error at all, on the reasoning that ">cap distinct values
# is >=2, which the ambiguous branch already names correctly". That reasoning
# ignores this function's OWN `clean_str_value` folding (2026-07-30 QA, at the
# shipped scan cap with a legal `limit: 1`):
#     pairs [('WF01', 1), ('WF01 ', 1)] -> folds to {'WF01'} -> verdict `single`
#     truth: two candidates (WF01, WF02); WF02 sat in the clipped group.
# So a clipped read could fold back down to one value and be auto-confirmed. That
# is the same lie the truncation rules exist to prevent, one layer down.
REASON_DISTINCT_TRUNCATED = "distinct_truncated"

# WHAT A BIGGER CAP WOULD ACTUALLY DO  [2026-08-05, user ruling]
# "Raise it" and "a person has to decide" are different repairs, and a refusal
# that offers only the first sends operators to turn a knob that cannot help.
# The probe already knows enough to tell them apart WITHOUT another query: the
# values it DID read are a lower bound on the distinct values that exist.
#   - >= 2 distinct canonical values already in hand -> raising the cap cannot
#     produce `single`. It converts this refusal into `ambiguous`, which is a
#     human judgement, not a setting.
#   - <= 1 so far -> genuinely unknown. The clipped remainder may agree (the cap
#     was the whole problem) or may hold the contradiction. Say so; do not
#     promise the operator a resolution the read cannot support.
EXPECT_AMBIGUOUS = "ambiguous"
EXPECT_UNKNOWN = "unknown"

_warned_once = set()


def _load_ingestion_settings() -> dict:
    """Minimal reader for ingestion_settings.json.

    A deliberate (tiny) local copy of the same read in map_meta_registrar /
    directory_watcher: importing either from here would drag watchdog and the
    legacy import shim into the chain worker for a 10-line file read.
    """
    try:
        if os.path.exists(INGESTION_SETTINGS_PATH):
            with open(INGESTION_SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
    except Exception as e:
        logger.warning("Could not load ingestion settings (%s): %s", INGESTION_SETTINGS_PATH, e)
    return {}


def _warn_once(key, msg, *args):
    if key in _warned_once:
        return
    _warned_once.add(key)
    logger.warning(msg, *args)


def reset_warnings():
    """Test hook - forget warn-once state."""
    _warned_once.clear()


def global_auto_confirm_enabled(settings: dict = None) -> bool:
    """Global kill switch (default True = do not block). Non-boolean warns once."""
    val = (settings if settings is not None else _load_ingestion_settings()).get(
        GLOBAL_KILL_SWITCH_KEY, True)
    if isinstance(val, bool):
        return val
    _warn_once(
        (GLOBAL_KILL_SWITCH_KEY, repr(val)),
        "Ignoring non-boolean '%s' value %r in ingestion_settings.json - expected JSON "
        "boolean true/false. Falling back to default True (per-rule opt-in still required).",
        GLOBAL_KILL_SWITCH_KEY, val)
    return True


def max_keys_per_unit(settings: dict = None) -> int:
    """Per-work-unit probe ceiling. Non-positive / non-integer warns once."""
    val = (settings if settings is not None else _load_ingestion_settings()).get(
        MAX_KEYS_SETTINGS_KEY, DEFAULT_MAX_KEYS_PER_UNIT)
    if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
        if val != DEFAULT_MAX_KEYS_PER_UNIT:
            _warn_once(
                (MAX_KEYS_SETTINGS_KEY, repr(val)),
                "Ignoring '%s' value %r in ingestion_settings.json - expected a positive "
                "integer. Falling back to default %s.",
                MAX_KEYS_SETTINGS_KEY, val, DEFAULT_MAX_KEYS_PER_UNIT)
        return DEFAULT_MAX_KEYS_PER_UNIT
    return val


def rule_auto_confirm_enabled(rule: dict, settings: dict = None) -> bool:
    """Is automatic confirmation enabled for THIS rule?

    Requires the global switch AND the per-rule opt-in. A non-boolean per-rule
    value warns once and falls back to the default (OFF) - the same posture as
    `map_meta_registrar.auto_register_enabled`, and the safe direction here.
    """
    if not global_auto_confirm_enabled(settings):
        return False
    val = (rule or {}).get(RULE_KNOB, DEFAULT_ENABLED)
    if isinstance(val, bool):
        return val
    _warn_once(
        (RULE_KNOB, rule.get("name"), repr(val)),
        "[Enrichment:%s] Ignoring non-boolean '%s' value %r in enrichment_rules.json - "
        "expected JSON boolean true/false. Falling back to default %s.",
        rule.get("name"), RULE_KNOB, val, DEFAULT_ENABLED)
    return DEFAULT_ENABLED


def declaring_views(rule: dict, target_field: str) -> list:
    """Reference views that DECLARE themselves candidate sources for this field."""
    return [v for v in (rule.get("reference_views") or [])
            if target_field in (v.get("candidate_for") or {})]


def candidate_target_fields(rule: dict) -> list:
    """Target fields this rule can produce candidates for (declaration-driven)."""
    return [t for t in (rule.get("target_fields") or []) if declaring_views(rule, t)]


def _refused(target_field, reason, **extra):
    # `partial_key`/`blank_key_columns` default here so EVERY result carries them
    # and no reader has to branch on their presence - an absent field and a false
    # one read the same to a careless caller, and only one of them is true.
    out = {"status": STATUS_REFUSED, "target_field": target_field, "reason": reason,
           "value": None, "support": 0, "candidates": [], "evidence": [], "errors": [],
           "partial_key": False, "blank_key_columns": []}
    out.update(extra)
    return out


def _truncation_error(label, reason, cap_key, cap_value, cap_declared, read, distinct_so_far):
    """One truncation refusal that names its own repair.

    Every field here exists because it was missing on 2026-08-05: the operator
    was told a read was clipped, was not told WHICH of three numbers spelled
    `limit` clipped it, raised the one they could reach (the CLI key budget,
    which touches no read), and nothing changed.
    """
    import enrichment_config

    return {
        "label": label,
        "reason": reason,
        "detail": read,
        # The cap by the name it has in config - never "limit".
        "cap": cap_key,
        "cap_value": cap_value,
        "cap_declared": bool(cap_declared),
        "cap_home": enrichment_config.read_cap_home(cap_key),
        "expected_if_raised": (EXPECT_AMBIGUOUS if distinct_so_far >= 2
                               else EXPECT_UNKNOWN),
        "distinct_values_read": distinct_so_far,
    }


def _diagnose_probe_failure(db, view: dict, column: str, key_values: dict) -> str:
    """Why did the grouped probe fail - a missing COLUMN, or a broken VIEW?

    The old row-based path could tell these apart for free (it read the result's
    column list, then looked the name up). The grouped probe interpolates the
    column INTO the SQL, so a name that is not in the result is a driver error
    indistinguishable from any other. Collapsing both into `view_error` would
    delete the one refusal reason that tells an operator their `candidate_for`
    declaration names a column the view does not return - which is precisely the
    "declared but the shape is wrong" case this round exists to surface.

    So: on failure only, run the ordinary DISPLAY wrap (cheap - it carries the
    view's own row limit) and ask whether the column is there. The happy path
    still costs exactly one query.
    """
    import enrichment_config
    try:
        columns, _ = enrichment_config.execute_reference_view(db, view, key_values)
    except enrichment_config.ReferenceViewError:
        return REASON_VIEW_ERROR      # the view itself does not execute
    return REASON_VIEW_ERROR if column in columns else REASON_CANDIDATE_COLUMN_MISSING


def resolve_target_candidate(db, rule: dict, key_values: dict, target_field: str,
                             caps: dict = None) -> dict:
    """THE predicate: does exactly one candidate exist for this (key, field)?

    Returns a dict; `status` is `single` (safe to confirm) or `refused` (with a
    named `reason`). Never raises for a view-level failure - a failure is a
    named refusal, because a swallowed exception reads as "no candidate" and
    that is the one lie this module must not tell.

    Value identity uses `crud.clean_str_value`, the system's shared
    normalization (trim + integral-float folding), so 'WF01 ' and 'WF01', or 1.0
    and 1, are ONE candidate rather than two - otherwise a trailing space would
    manufacture an `ambiguous` refusal out of agreement.

    THE PROBE IS GROUPED, THE DISPLAY IS NOT  [2026-07-30, F9]
    Counting distinct values in Python over rows the server already truncated
    made `support` a count over the first `limit` rows and made `ambiguous`
    unreachable past that boundary - measured live: the `wafer_process` view
    declares `limit: 50` while every one of 80 keys returns 69..217 rows. The
    probe therefore runs `execute_candidate_probe` (GROUP BY over the WHOLE
    result), while the human-facing display path keeps the row-limited wrap.
    One declaration, two execution shapes, because they ask different questions.

    A PARTIAL DECISION KEY IS WORKED, NOT REFUSED  [2026-08-05, user ruling]
    When part of the key is blank, this resolves on what remains. It already did,
    mechanically - a view bound to a proper subset of the key never noticed the
    blank column - and the guard that kept those rows away from writers lived
    upstream, in the queue predicate. That guard is gone, so the two refusals
    that remain here carry the whole weight, and both are arithmetic rather than
    policy:
      - `missing_bind` (per view, unchanged): this view binds the column that is
        blank, so it cannot be asked. Since ANY view error poisons the verdict,
        a rule whose declaring views all need the blank column still refuses.
      - `no_decision_key` (below): nothing survives at all.
    `partial_key` rides on the result so the caller can STAMP the write; it never
    changes `status`. Blocking is not what the fact is for.

    `caps`: the read-cap snapshot (`enrichment_config.load_read_caps`). Passed in
    from the work-unit boundary so every key in one sweep is measured against the
    same ceilings; loaded here only when a caller has none.
    """
    import enrichment_config
    from database import crud

    caps = caps if caps is not None else enrichment_config.load_read_caps()
    views = declaring_views(rule, target_field)
    if not views:
        return _refused(target_field, REASON_NOT_DECLARED)

    # Which declared key columns did not survive. Read from the RULE, not from
    # `key_values`: a caller that omits a column entirely has the same blank key
    # as one that passes "" for it, and only the rule knows the full list.
    blank_key_cols = sorted(k for k in (rule.get("decision_key") or [])
                            if crud.clean_str_value(key_values.get(k)) == "")
    partial = {"partial_key": bool(blank_key_cols), "blank_key_columns": blank_key_cols}
    if blank_key_cols and len(blank_key_cols) == len(rule.get("decision_key") or []):
        return _refused(target_field, REASON_NO_DECISION_KEY, **partial)

    values = {}      # canonical value -> supporting row count
    evidence = []    # per-view contribution
    errors = []      # per-view failure, each with a named reason

    for view in views:
        label = view.get("label")
        column = (view.get("candidate_for") or {})[target_field]
        needed = set(view.get("required_binds") or [])
        missing = sorted(needed - set(k for k, v in key_values.items()
                                      if crud.clean_str_value(v) != ""))
        if missing:
            errors.append({"label": label, "reason": REASON_MISSING_BIND, "detail": missing})
            continue
        try:
            probe = enrichment_config.execute_candidate_probe(db, view, column, key_values,
                                                              caps=caps)
        except enrichment_config.ReferenceViewError as e:
            errors.append({"label": label,
                           "reason": _diagnose_probe_failure(db, view, column, key_values),
                           "detail": str(e)})
            continue
        hits = 0
        # This view's OWN folded values. Kept separate from the cross-view `values`
        # tally because a truncation is one view's fact: what a bigger cap would do
        # is decided by what THAT read already saw, not by what a sibling view
        # contributed.
        view_values = set()
        for raw, count in probe["pairs"]:
            val = crud.clean_str_value(raw)
            if val == "":
                continue
            values[val] = values.get(val, 0) + count
            view_values.add(val)
            hits += count
        evidence.append({"label": label, "rows": probe["scanned"],
                         "distinct_values": len(probe["pairs"]),
                         "candidate_rows": hits,
                         "distinct_truncated": probe["distinct_truncated"],
                         "scan_rows_cap": probe["scan_rows_cap"],
                         "distinct_values_cap": probe["distinct_values_cap"]})
        # Both truncations are the SAME fact - the read is incomplete - so both
        # are named refusals. Neither can be left to the `ambiguous` branch: the
        # folding above can collapse a clipped result back to one value (see
        # REASON_DISTINCT_TRUNCATED). Each one now names WHICH cap cut it, where
        # that cap is set, and whether raising it can even help.
        if probe["row_truncated"]:
            errors.append(_truncation_error(
                label, REASON_PROBE_TRUNCATED,
                enrichment_config.CAP_PROBE_SCAN_ROWS, probe["scan_rows_cap"],
                probe["scan_rows_cap_declared"], probe["scanned"], len(view_values)))
        if probe["distinct_truncated"]:
            errors.append(_truncation_error(
                label, REASON_DISTINCT_TRUNCATED,
                enrichment_config.CAP_PROBE_DISTINCT_VALUES, probe["distinct_values_cap"],
                probe["distinct_values_cap_declared"], len(probe["pairs"]),
                len(view_values)))
    distinct = sorted(values)

    # An unevaluated view is UNKNOWN, not empty: refuse even when the surviving
    # views agree, because the failed one may have held the contradiction.
    if errors:
        return _refused(target_field, errors[0]["reason"],
                        candidates=distinct[:AMBIGUOUS_SAMPLE], evidence=evidence, errors=errors,
                        value=distinct[0] if len(distinct) == 1 else None,
                        support=values.get(distinct[0], 0) if len(distinct) == 1 else 0,
                        **partial)
    if not distinct:
        return _refused(target_field, REASON_NO_CANDIDATE, evidence=evidence, **partial)
    if len(distinct) > 1:
        return _refused(target_field, REASON_AMBIGUOUS,
                        candidates=distinct[:AMBIGUOUS_SAMPLE], evidence=evidence,
                        distinct_count=len(distinct), **partial)
    return dict({"status": STATUS_SINGLE, "target_field": target_field, "reason": None,
                 "value": distinct[0], "support": values[distinct[0]],
                 "candidates": distinct, "evidence": evidence, "errors": []}, **partial)


def find_unresolved_cells(db, derived_table: str, row_ids: list, target_fields: list) -> set:
    """Which (row_id, column) target cells have NO provenance at all?

    Batched on `idx_sources_lookup` (table_name, row_id, column_name) in
    CHUNK_SIZE chunks - one query per chunk, never per row. Returns the set of
    (row_id, column) pairs that are safe to write absent-only.
    """
    from database import models

    row_ids = [r for r in row_ids if r]
    if not row_ids or not target_fields:
        return set()
    taken = set()
    for i in range(0, len(row_ids), CHUNK_SIZE):
        chunk = row_ids[i:i + CHUNK_SIZE]
        rows = (db.query(models.CellSource.row_id, models.CellSource.column_name)
                .filter(models.CellSource.table_name == derived_table,
                        models.CellSource.row_id.in_(chunk),
                        models.CellSource.column_name.in_(list(target_fields)))
                .all())
        for row_id, column in rows:
            taken.add((row_id, column))
    return {(r, c) for r in row_ids for c in target_fields if (r, c) not in taken}


def _bump_target(st: dict, field: str, reason=None):
    """Record ONE target column's outcome, in both grains.

    The flat `refused` bag is the vocabulary every existing reader already
    consumes (`log_stats`, the CLI, the admin dry-run and `retroactive`), so it
    keeps counting exactly what it counted - this adds an INDEX, it does not mint
    a second set of names. `per_target` is the same events keyed by column, which
    is the grain the decision is actually made at.

    `reason=None` means the column was confirmed. Row-grain refusals
    (`no_row_identity`) are not routed here: they belong to no column.
    """
    slot = st["per_target"].setdefault(field, {"confirmed": 0, "refused": {}})
    if reason is None:
        slot["confirmed"] += 1
        return
    slot["refused"][reason] = slot["refused"].get(reason, 0) + 1
    st["refused"][reason] = st["refused"].get(reason, 0) + 1


def _record_cap_hit(st: dict, res: dict):
    """Roll this verdict's truncations up into the stats, BY CAP NAME.

    A census of `distinct_truncated=76` tells an operator a read was clipped 76
    times and nothing about what to do. Keyed by cap it says which number, what
    it is set to, whether anyone set it, and how the 76 split between "a bigger
    cap resolves this" and "a bigger cap just renames it `ambiguous`". Those are
    two different instructions and they must not arrive as one total.
    """
    for err in res.get("errors") or []:
        if not err.get("cap"):
            continue
        slot = st["cap_hits"].setdefault(err["cap"], {
            "cap_value": err["cap_value"], "cap_declared": err["cap_declared"],
            "cap_home": err["cap_home"], "hits": 0,
            EXPECT_AMBIGUOUS: 0, EXPECT_UNKNOWN: 0, "max_read": 0})
        slot["hits"] += 1
        slot[err["expected_if_raised"]] += 1
        slot["max_read"] = max(slot["max_read"], err.get("detail") or 0)


def confirm_keys(db, rule: dict, keyed_rows: list, apply: bool = False,
                 stats: dict = None, tx_prefix: str = None, caps: dict = None) -> dict:
    """Resolve + (optionally) write single candidates for a set of derived rows.

    `keyed_rows`: [{"row_id":..., "business_key_val":..., "keys": {col: val},
                    "blank_targets": [col, ...]}]  (blank_targets = target cells
    whose DISPLAYED value is blank; provenance is checked here.)

    Shared by both paths so there is one implementation of the write:
    the chain-worker collector (`AutoConfirmCollector.flush`) and the
    retroactive sweep (`enrichment_analysis.run_auto_confirm_sweep`).
    Dry-run (`apply=False`) performs reads only - that is the measuring mode.

    A row whose decision key is only PARTLY present is written like any other and
    stamped `SOURCE_NAME_PARTIAL_KEY` (see that constant). The stamp is per ITEM
    because partiality is a property of the ROW's key, not of the target field -
    every field on that row was decided from the same surviving columns.

    PARTIAL BY TARGET IS NOT STAMPED, AND THAT IS THE ANSWER, NOT AN OMISSION
    A partial-KEY decision needs a name because the fact lives on the row and no
    per-cell record carries it: every cell of that row was decided from a
    diminished key, and nothing in `cell_sources` says so. A partial-TARGET fill
    is the opposite - it IS per cell. `cell_sources` has one row per (row_id,
    column_name), so "which columns did the sweep decide" is already a predicate
    over `source_name`, and the columns it refused have NO source row at all.
    Adding a third source name would restate what the table's own grain says.

    THREE GRAINS OF COUNTER, ALL FROM ONE WALK
      - CELL:   `confirmed` / `written_cells` - already partial-friendly; a
                2-of-3 fill has always scored two.
      - COLUMN: `per_target` - which column was decided, and for the rest, WHY.
      - ROW:    `rows_fully_confirmed` / `rows_partly_confirmed` /
                `rows_unconfirmed`, which partition `rows_examined`. A sweep that
                fills 2 of 3 columns on a thousand rows did real work, and
                without this grain the only row-level number was `queue_size` -
                so that work reported as a thousand rows still queued.
    """
    from database import crud, schemas
    import enrichment_config

    caps = caps if caps is not None else enrichment_config.load_read_caps()
    st = stats if stats is not None else {}
    st.setdefault("keys_examined", 0)
    st.setdefault("confirmed", 0)
    st.setdefault("confirmed_partial_key", 0)
    st.setdefault("written_cells", 0)
    st.setdefault("refused", {})
    st.setdefault("samples", [])
    # ROW grain. These three are a partition of `rows_examined` - asserted in the
    # tests, because a partition that silently stops adding up is how a progress
    # number starts lying (N36).
    st.setdefault("rows_examined", 0)
    st.setdefault("rows_fully_confirmed", 0)
    st.setdefault("rows_partly_confirmed", 0)
    st.setdefault("rows_unconfirmed", 0)
    # COLUMN grain: {target_field: {"confirmed": n, "refused": {reason: n}}}.
    st.setdefault("per_target", {})
    # CAP grain: {cap_name: {cap_value, cap_declared, cap_home, hits, ambiguous,
    # unknown, max_read}} - what to turn, and whether turning it would help.
    st.setdefault("cap_hits", {})

    derived_table = rule["derived_table"]
    target_fields = candidate_target_fields(rule)
    declared = set(target_fields)
    if not target_fields:
        st["refused"][REASON_NOT_DECLARED] = st["refused"].get(REASON_NOT_DECLARED, 0) + len(keyed_rows)
        st["rows_examined"] += len(keyed_rows)
        st["rows_unconfirmed"] += len(keyed_rows)
        return st

    # Absent-only gate, batched before any per-key probing: a cell that already
    # carries provenance is never probed, so a resolved queue costs no queries.
    writable = find_unresolved_cells(
        db, derived_table, [r.get("row_id") for r in keyed_rows], target_fields)

    items = []
    for entry in keyed_rows:
        st["rows_examined"] += 1
        row_id = entry.get("row_id")
        business_key_val = entry.get("business_key_val")
        # Addressability is checked ONCE per row, before any probing, because a
        # row the writer cannot land on is not worth a query. `row_id` alone is
        # enough (`crud._get_or_create_row` prefers it), and neither present
        # would make the write CREATE a row rather than fill one.
        if not row_id and not crud.clean_str_value(business_key_val):
            st["refused"][REASON_NO_ROW_IDENTITY] = \
                st["refused"].get(REASON_NO_ROW_IDENTITY, 0) + 1
            st["rows_unconfirmed"] += 1
            continue
        blanks = set(entry.get("blank_targets") or target_fields)
        # A blank target that no view declares a candidate column for was NEVER
        # ASKED. It used to be skipped in silence whenever another target on the
        # same rule was declared (the `not_declared` tally only fired when NONE
        # was), so from outside it read identical to a column we compared and
        # found ambiguous. Those are different facts and only one of them is a
        # human's to settle.
        for field in sorted(blanks - declared):
            _bump_target(st, field, REASON_NOT_DECLARED)
        updates = {}
        partial_key = False
        for field in target_fields:
            if field not in blanks:
                continue
            if row_id and (row_id, field) not in writable:
                _bump_target(st, field, REASON_CELL_HAS_PROVENANCE)
                continue
            st["keys_examined"] += 1
            res = resolve_target_candidate(db, rule, entry.get("keys") or {}, field,
                                           caps=caps)
            if res["status"] != STATUS_SINGLE:
                # This column stays blank and its reason is recorded AGAINST THE
                # COLUMN. The row carries on: a sibling column with unanimous
                # candidates is still determined.
                _bump_target(st, field, res["reason"])
                _record_cap_hit(st, res)
                continue
            _bump_target(st, field, None)
            updates[field] = res["value"]
            partial_key = partial_key or bool(res.get("partial_key"))
            st["confirmed"] += 1
            st["confirmed_partial_key"] = st.get("confirmed_partial_key", 0) + \
                (1 if res.get("partial_key") else 0)
            if len(st["samples"]) < 20:
                st["samples"].append({
                    "business_key_val": business_key_val,
                    "field": field, "value": res["value"], "support": res["support"],
                    "partial_key": bool(res.get("partial_key")),
                    "blank_key_columns": list(res.get("blank_key_columns") or []),
                })
        if not updates:
            st["rows_unconfirmed"] += 1
            continue
        # "Fully" is measured against THIS row's blank targets, not the rule's -
        # a row whose only remaining blank was filled is finished, whatever its
        # already-resolved siblings did earlier.
        if len(updates) == len(blanks):
            st["rows_fully_confirmed"] += 1
        else:
            st["rows_partly_confirmed"] += 1
        st["written_cells"] += len(updates)
        if apply:
            item = dict(updates)
            # THE STAMP. Same writer, different name, same rank (both unregistered
            # -> 99). This is the record that makes the decision addressable when
            # the missing key column arrives.
            src = SOURCE_NAME_PARTIAL_KEY if partial_key else SOURCE_NAME
            items.append(schemas.GeneralUpdateItem(
                row_id=row_id,
                business_key_val=business_key_val,
                updates=item,
                source_name=src,
                updated_by=src,
            ))

    if apply and items:
        import uuid
        tx_id = f"{tx_prefix or SOURCE_NAME}_{uuid.uuid4().hex[:8]}"
        for i in range(0, len(items), CHUNK_SIZE):
            batch = schemas.GeneralUpdateBatch(
                updates=items[i:i + CHUNK_SIZE], transaction_id=tx_id, silent=False)
            crud.apply_batch_updates(db, derived_table, batch)
    return st


def log_stats(rule_name: str, st: dict, apply: bool):
    """One line that names every refusal reason with its count.

    Plus a second line, only when the rule has more than one target column: with
    one column the per-column breakdown is the first line restated, and a log
    that repeats itself gets skimmed.
    """
    refused = st.get("refused") or {}
    detail = ", ".join(f"{k}={v}" for k, v in sorted(refused.items())) or "none"
    logger.info(
        "[Enrichment:%s] auto-confirm %s: %d key-field(s) probed, %d single candidate(s) "
        "(%d on a partial decision key, source '%s'), %d cell(s) %s over %d row(s) "
        "(%d complete, %d partly filled, %d untouched); refusals: %s",
        rule_name, "APPLY" if apply else "DRY-RUN", st.get("keys_examined", 0),
        st.get("confirmed", 0), st.get("confirmed_partial_key", 0), SOURCE_NAME_PARTIAL_KEY,
        st.get("written_cells", 0),
        "written" if apply else "would be written",
        st.get("rows_examined", 0), st.get("rows_fully_confirmed", 0),
        st.get("rows_partly_confirmed", 0), st.get("rows_unconfirmed", 0), detail)
    per_target = st.get("per_target") or {}
    if len(per_target) > 1:
        logger.info(
            "[Enrichment:%s] auto-confirm per target column - %s", rule_name,
            "; ".join(
                f"{f}: {s['confirmed']} confirmed"
                + (", " + ", ".join(f"{r}={n}" for r, n in sorted(s["refused"].items()))
                   if s["refused"] else "")
                for f, s in sorted(per_target.items())))
    # A third line, only when a cap actually clipped something. It names the cap,
    # its value, whether anyone declared it, and where to set it - because the
    # 2026-08-05 incident was an operator raising a DIFFERENT number that shared
    # the word `limit`, and no message here told them there were three.
    for cap, s in sorted((st.get("cap_hits") or {}).items()):
        logger.warning(
            "[Enrichment:%s] auto-confirm: %d read(s) clipped by '%s'=%s (%s; largest "
            "read %s). Raising it would turn %d into an AMBIGUOUS judgement (a person "
            "decides, not a knob) and %d are unknowable until the read completes. "
            "Set it at: %s",
            rule_name, s["hits"], cap, s["cap_value"],
            "declared" if s["cap_declared"] else "NOT declared - this is the shipped value",
            s["max_read"], s[EXPECT_AMBIGUOUS], s[EXPECT_UNKNOWN], s["cap_home"])


class AutoConfirmCollector:
    """Per-work-unit collector for the chain-worker write path.

    Inert (`active=False`) unless every gate passes at construction: the global
    switch, a rule whose `derived_table` is this table, that rule's per-rule
    opt-in, and at least one `candidate_for` declaration. Construction is the
    work-unit boundary, so the knob snapshot is consistent for the whole tx
    group (the D1 snapshot discipline).

    Re-entrancy: writes here land on the DERIVED table while the enrichment
    chain rule triggers on the SOURCE table, so this cannot re-fire its own
    rule. And it is a fixpoint regardless of wiring - once a target cell has
    provenance the absent-only gate refuses it, so a second pass finds nothing.
    """

    def __init__(self, derived_table: str, rules: list = None, settings: dict = None):
        self.derived_table = derived_table
        self.active = False
        self.rule = None
        self.entries = {}   # business_key_val -> {"keys": {...}}
        self._max_keys = DEFAULT_MAX_KEYS_PER_UNIT
        # Read caps come from the SAME settings snapshot as the knobs, taken once
        # here at the work-unit boundary (D1). One file read, one set of ceilings
        # for the whole transaction group.
        self._caps = None

        settings = settings if settings is not None else _load_ingestion_settings()
        if not global_auto_confirm_enabled(settings):
            return
        if rules is None:
            import enrichment_config
            from database import crud
            rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
        for r in rules or []:
            if r.get("derived_table") != derived_table:
                continue
            if not rule_auto_confirm_enabled(r, settings):
                continue
            if not candidate_target_fields(r):
                _warn_once(
                    ("no_declaration", r.get("name")),
                    "[Enrichment:%s] '%s: true' has no effect: no reference view declares "
                    "'candidate_for' for any target field. Automatic confirmation needs a "
                    "DECLARED candidate column - it never guesses one.",
                    r.get("name"), RULE_KNOB)
                continue
            import enrichment_config
            self.rule = r
            self._max_keys = max_keys_per_unit(settings)
            self._caps = enrichment_config.load_read_caps(settings)
            self.active = True
            return

    def collect(self, items):
        """Accumulate decision-key values per business key from batch items.

        `items` may be `schemas.GeneralUpdateItem`s or plain dicts of updates -
        the chain worker passes the VALIDATED batch items, i.e. the same column
        names the upsert actually wrote.
        """
        if not self.active:
            return
        from database import crud

        decision_key = self.rule["decision_key"]
        for item in items:
            updates = getattr(item, "updates", None)
            bk = getattr(item, "business_key_val", None)
            if updates is None and isinstance(item, dict):
                updates = item.get("updates", item)
                bk = item.get("business_key_val", bk)
            if not isinstance(updates, dict):
                continue
            keys = {k: updates.get(k) for k in decision_key}
            if all(crud.clean_str_value(v) == "" for v in keys.values()):
                # NOTHING survives - not "part of the key is missing". A partial
                # key is worked on what remains [2026-08-05 ruling]; a wholly
                # blank one has nothing to bind any view to, and
                # `resolve_target_candidate` would refuse it `no_decision_key`
                # anyway. Dropping it here only saves the queries.
                continue
            if not bk:
                continue
            self.entries.setdefault(bk, {"keys": keys})

    def pending(self) -> bool:
        return self.active and bool(self.entries)

    def flush(self, db) -> dict:
        """Resolve + write for the collected keys. Returns the stats dict."""
        if not self.pending():
            return {}
        from database import crud, models

        model = models.DYNAMIC_TABLES.get(self.derived_table)
        if model is None:
            return {}
        target_fields = candidate_target_fields(self.rule)

        bks = list(self.entries)
        over_cap = 0
        if len(bks) > self._max_keys:
            over_cap = len(bks) - self._max_keys
            bks = bks[:self._max_keys]

        # Fetch row_id + current target values for the collected keys, batched on
        # the indexed business_key_val column. Only rows whose target is
        # currently blank are candidates for probing.
        keyed_rows = []
        cols = [model.row_id, model.business_key_val] + [getattr(model, f) for f in target_fields]
        for i in range(0, len(bks), CHUNK_SIZE):
            chunk = bks[i:i + CHUNK_SIZE]
            for row in db.query(*cols).filter(model.business_key_val.in_(chunk)).all():
                row_id, bk = row[0], row[1]
                blanks = [f for f, v in zip(target_fields, row[2:])
                          if crud.clean_str_value(v) == ""]
                if not blanks:
                    continue
                keyed_rows.append({
                    "row_id": row_id, "business_key_val": bk,
                    "keys": self.entries[bk]["keys"], "blank_targets": blanks,
                })

        stats = {"refused": {REASON_OVER_CAP: over_cap} if over_cap else {}}
        if keyed_rows:
            confirm_keys(db, self.rule, keyed_rows, apply=True, stats=stats,
                         tx_prefix=SOURCE_NAME, caps=self._caps)
        if over_cap:
            logger.warning(
                "[Enrichment:%s] %d decision KEY(s) beyond the per-unit key budget "
                "('%s'=%d) were NOT probed - they stay in the worklist. This budget "
                "bounds HOW MANY KEYS are examined; it does not widen any single read "
                "(that is enrichment_read_caps.probe_scan_rows / probe_distinct_values). "
                "Raise it or let the next ingestion pick them up.",
                self.rule.get("name"), over_cap, MAX_KEYS_SETTINGS_KEY, self._max_keys)
        if stats.get("confirmed") or stats.get("refused"):
            log_stats(self.rule.get("name"), stats, apply=True)
        return stats
