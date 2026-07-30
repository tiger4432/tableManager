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
    - `cell_has_provenance` -> the target cell already has a CellSource row
      from ANY writer. A human who deliberately cleared a value has said "not
      this"; re-confirming over that would erase a judgement. This is stricter
      than M3's row-absence check because the unit here is a cell.
    A refused key stays in the queue, visibly unresolved. Nothing is silently
    turned from unknown into a confident wrong value.

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
REASON_NO_CANDIDATE = "no_candidate"
REASON_AMBIGUOUS = "ambiguous"
REASON_VIEW_ERROR = "view_error"
REASON_MISSING_BIND = "missing_bind"
REASON_CANDIDATE_COLUMN_MISSING = "candidate_column_missing"
REASON_CELL_HAS_PROVENANCE = "cell_has_provenance"
REASON_OVER_CAP = "over_cap"

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
    out = {"status": STATUS_REFUSED, "target_field": target_field, "reason": reason,
           "value": None, "support": 0, "candidates": [], "evidence": [], "errors": []}
    out.update(extra)
    return out


def resolve_target_candidate(db, rule: dict, key_values: dict, target_field: str) -> dict:
    """THE predicate: does exactly one candidate exist for this (key, field)?

    Returns a dict; `status` is `single` (safe to confirm) or `refused` (with a
    named `reason`). Never raises for a view-level failure - a failure is a
    named refusal, because a swallowed exception reads as "no candidate" and
    that is the one lie this module must not tell.

    Value identity uses `crud.clean_str_value`, the system's shared
    normalization (trim + integral-float folding), so 'WF01 ' and 'WF01', or 1.0
    and 1, are ONE candidate rather than two - otherwise a trailing space would
    manufacture an `ambiguous` refusal out of agreement.
    """
    import enrichment_config
    from database import crud

    views = declaring_views(rule, target_field)
    if not views:
        return _refused(target_field, REASON_NOT_DECLARED)

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
            columns, rows = enrichment_config.execute_reference_view(db, view, key_values)
        except enrichment_config.ReferenceViewError as e:
            errors.append({"label": label, "reason": REASON_VIEW_ERROR, "detail": str(e)})
            continue
        if column not in columns:
            errors.append({"label": label, "reason": REASON_CANDIDATE_COLUMN_MISSING,
                           "detail": column})
            continue
        idx = columns.index(column)
        hits = 0
        for row in rows:
            val = crud.clean_str_value(row[idx])
            if val == "":
                continue
            values[val] = values.get(val, 0) + 1
            hits += 1
        evidence.append({"label": label, "rows": len(rows), "candidate_rows": hits})

    distinct = sorted(values)

    # An unevaluated view is UNKNOWN, not empty: refuse even when the surviving
    # views agree, because the failed one may have held the contradiction.
    if errors:
        return _refused(target_field, errors[0]["reason"],
                        candidates=distinct[:AMBIGUOUS_SAMPLE], evidence=evidence, errors=errors,
                        value=distinct[0] if len(distinct) == 1 else None,
                        support=values.get(distinct[0], 0) if len(distinct) == 1 else 0)
    if not distinct:
        return _refused(target_field, REASON_NO_CANDIDATE, evidence=evidence)
    if len(distinct) > 1:
        return _refused(target_field, REASON_AMBIGUOUS,
                        candidates=distinct[:AMBIGUOUS_SAMPLE], evidence=evidence,
                        distinct_count=len(distinct))
    return {"status": STATUS_SINGLE, "target_field": target_field, "reason": None,
            "value": distinct[0], "support": values[distinct[0]],
            "candidates": distinct, "evidence": evidence, "errors": []}


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


def confirm_keys(db, rule: dict, keyed_rows: list, apply: bool = False,
                 stats: dict = None, tx_prefix: str = None) -> dict:
    """Resolve + (optionally) write single candidates for a set of derived rows.

    `keyed_rows`: [{"row_id":..., "business_key_val":..., "keys": {col: val},
                    "blank_targets": [col, ...]}]  (blank_targets = target cells
    whose DISPLAYED value is blank; provenance is checked here.)

    Shared by both paths so there is one implementation of the write:
    the chain-worker collector (`AutoConfirmCollector.flush`) and the
    retroactive sweep (`enrichment_analysis.run_auto_confirm_sweep`).
    Dry-run (`apply=False`) performs reads only - that is the measuring mode.
    """
    from database import crud, schemas

    st = stats if stats is not None else {}
    st.setdefault("keys_examined", 0)
    st.setdefault("confirmed", 0)
    st.setdefault("written_cells", 0)
    st.setdefault("refused", {})
    st.setdefault("samples", [])

    derived_table = rule["derived_table"]
    target_fields = candidate_target_fields(rule)
    if not target_fields:
        st["refused"][REASON_NOT_DECLARED] = st["refused"].get(REASON_NOT_DECLARED, 0) + len(keyed_rows)
        return st

    # Absent-only gate, batched before any per-key probing: a cell that already
    # carries provenance is never probed, so a resolved queue costs no queries.
    writable = find_unresolved_cells(
        db, derived_table, [r.get("row_id") for r in keyed_rows], target_fields)

    items = []
    for entry in keyed_rows:
        row_id = entry.get("row_id")
        blanks = set(entry.get("blank_targets") or target_fields)
        updates = {}
        for field in target_fields:
            if field not in blanks:
                continue
            if row_id and (row_id, field) not in writable:
                st["refused"][REASON_CELL_HAS_PROVENANCE] = \
                    st["refused"].get(REASON_CELL_HAS_PROVENANCE, 0) + 1
                continue
            st["keys_examined"] += 1
            res = resolve_target_candidate(db, rule, entry.get("keys") or {}, field)
            if res["status"] != STATUS_SINGLE:
                st["refused"][res["reason"]] = st["refused"].get(res["reason"], 0) + 1
                continue
            updates[field] = res["value"]
            st["confirmed"] += 1
            if len(st["samples"]) < 20:
                st["samples"].append({
                    "business_key_val": entry.get("business_key_val"),
                    "field": field, "value": res["value"], "support": res["support"],
                })
        if not updates:
            continue
        st["written_cells"] += len(updates)
        if apply:
            item = dict(updates)
            items.append(schemas.GeneralUpdateItem(
                business_key_val=entry.get("business_key_val"),
                updates=item,
                source_name=SOURCE_NAME,
                updated_by=SOURCE_NAME,
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
    """One line that names every refusal reason with its count."""
    refused = st.get("refused") or {}
    detail = ", ".join(f"{k}={v}" for k, v in sorted(refused.items())) or "none"
    logger.info(
        "[Enrichment:%s] auto-confirm %s: %d key-field(s) probed, %d single candidate(s), "
        "%d cell(s) %s; refusals: %s",
        rule_name, "APPLY" if apply else "DRY-RUN", st.get("keys_examined", 0),
        st.get("confirmed", 0), st.get("written_cells", 0),
        "written" if apply else "would be written", detail)


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
        self._cap = DEFAULT_MAX_KEYS_PER_UNIT

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
            self.rule = r
            self._cap = max_keys_per_unit(settings)
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
            if any(crud.clean_str_value(v) == "" for v in keys.values()):
                # A row without its decision keys cannot be resolved by anyone -
                # the same exclusion queue_filters applies to the worklist.
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
        if len(bks) > self._cap:
            over_cap = len(bks) - self._cap
            bks = bks[:self._cap]

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
                         tx_prefix=SOURCE_NAME)
        if over_cap:
            logger.warning(
                "[Enrichment:%s] %d decision key(s) beyond the per-unit cap (%s=%d) were "
                "NOT probed - they stay in the worklist. Raise the cap or let the next "
                "ingestion pick them up.",
                self.rule.get("name"), over_cap, MAX_KEYS_SETTINGS_KEY, self._cap)
        if stats.get("confirmed") or stats.get("refused"):
            log_stats(self.rule.get("name"), stats, apply=True)
        return stats
