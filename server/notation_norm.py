"""WF/lot/slot notation normalization - a DERIVED column, never a rewrite.

[The reported pain, 2026-08-04]
    "WF.01, WF-01 and so on are mixed, which makes filters and JOINs awkward
    everywhere."

And the sharper case, already measured: `map_overlay.map_key_parts` splits a
composite map key on `_`, so a `core_lot` value that itself contains `_`
(`CL_2601_001_09`) shreds into lot='CL' + slot='2601_001_09' and renders ZERO
cells. 766 rows of the simulation carried that shape.

🔑 THE `_` SEPARATOR IS DELIBERATE and is NOT changed here. The operator built
the composite key so that typing just the lot yields `lot_*` and scans every
slot of that lot. This module does not change the convention - it makes the
convention HOLD, by keeping `_` out of the values that compose the key.

[THE SAFETY PROPERTY - this is a hard requirement, not a preference]
🔴 The raw column is NEVER touched. The normalized value lands in a SEPARATE,
declared column (`<col>_norm` by convention). A folding rule that turns out to
merge two genuinely different entities is therefore corrected by fixing the
rule and RE-DERIVING (`server/scripts/rederive_notation_norm.py`); nothing is
lost meanwhile. That is what made it safe to ship these rules before the
spelling census had been run.

The invariant is enforced in three places, not asserted in a comment:
  1. `_validate_column` refuses `derived == raw`.
  2. `_validate_column` refuses a derived column that is the business key or a
     member of `composite_key_source` - a derived value can never move a row's
     identity.
  3. `crud.refuse_notation_derived_columns` refuses any WRITE aimed at a
     derived column, on every write path (same posture, same funnel, as
     `refuse_virtual_join_columns`).

[THE RULES - independently switchable, on purpose]
    separator   '.' '_' '-' whitespace runs  ->  a single '-'    (LOW risk)
    case        upper                                            (LOW risk)
    zero_pad    leading zeros stripped        NOT IMPLEMENTED - see below

🔴 `zero_pad` is DECLARED AND REFUSED, not silently ignored. It is the one rule
whose false-merge risk is real (`WF010` and `WF10` both become `WF10`), and no
census has been run to say whether such a collapse exists in this fab. Setting
it to `true` produces a NAMED refusal (`zero_pad_unimplemented`) that surfaces
in `GET /admin/config/resolve`, because a knob that reads as ON and does
nothing is the exact silence this repo keeps paying for.
Note also that the separate ruling "slot is always int" retires the question
for slot -- but only once the column IS declared `number`: that path goes
through `canonical_key_value`'s integer parse, where '01' and '1' are already
one key and padding has no ambiguity left to lose.
Measured 2026-08-04: `dt_log.core_slot`, `dt_log.dt_slot`,
`core_wafer_map.core_slot` and `bonding_log.bond_slot` are all declared
`string` in the live config, so the retirement has NOT taken effect yet. The
ruling exists; the declarations have not caught up. The fix is the declared
type, not an implementation of zero_pad.

Bundling the three would mean the risky one could never be enabled separately
later, so each is its own boolean and `fold_notation` has no branch at all for
the unimplemented one.

[REUSE, NOT A SECOND SPELLING OF "NORMALIZE"]
`map_overlay.canonical_key_value` (7b) already exists, and exists precisely
because of this class of incident (`LOT_01` vs `1` made a lookup miss). What it
already folds:
    number-declared  -> integer parse ('01' / ' 1 ' / 1.0 / '1.0' all -> '1');
                        a non-integral numeric keeps its repr; an unreadable
                        value keeps its trimmed original
    string/undeclared-> trimmed as-is (padding in a string is DATA, per spec)
    float VALUE      -> integral floats lose the '.0' repr artifact
It does NOT fold separators and does NOT fold case. So R1/R2 are genuinely new,
and they are applied ON TOP of the canonical string rather than beside it:

    normalized = fold_notation(canonical_bind_value(table, column, raw), rules)

(`canonical_bind_value` is the wrapper that looks the declared type up and then
calls `canonical_key_value` -- named here as the symbol this module actually
imports, so grepping for the call site finds it.)

One vocabulary, two layers. `canonical_key_value` keeps deciding what the value
IS (by its declared type); this module decides only how its notation is spelled.

[PHASE 1 - nothing consumes the derived value yet]
🔴 Switching map-key parsing, filters or joins to the normalized value would
change every existing map key, and maps would stop resolving. That is a
separate, declared, opt-in decision with its own round. Phase 1 is: the derived
value exists, is correct, and is re-derivable.
"""
import json
import logging
import os
import re

logger = logging.getLogger("NotationNorm")

import paths  # single override point (ASSY_DATA_ROOT)
# THE existing canonicalization (7b). Module level and not a per-call import:
# `normalized_value` runs once per value, and re-derivation runs it 10M times.
# Safe from cycles - map_overlay imports only stdlib + paths at module level and
# reaches `crud` lazily, while `crud` reaches this module lazily.
from map_overlay import canonical_bind_value

NOTATION_RULES_PATH = paths.config_path("notation_rules.json")

# --- The rule vocabulary -----------------------------------------------------

RULE_SEPARATOR = "separator"
RULE_CASE = "case"
RULE_ZERO_PAD = "zero_pad"

KNOWN_RULES = (RULE_SEPARATOR, RULE_CASE, RULE_ZERO_PAD)

# Rules this module can actually apply. `zero_pad` is deliberately absent - see
# the module docstring. Membership here is what `_normalize_rules` checks, so
# implementing it later is one tuple entry plus one branch in `fold_notation`,
# and the refusal disappears on its own.
IMPLEMENTED_RULES = (RULE_SEPARATOR, RULE_CASE)

DEFAULT_RULES = {RULE_SEPARATOR: True, RULE_CASE: True, RULE_ZERO_PAD: False}

# The one form every separator collapses to. '-' and not '_' is the whole point:
# '_' is the composite map-key join character (`map_overlay.compose_map_id`), so
# a value that keeps its '_' is a value that shreds the key it is part of.
SEPARATOR_TARGET = "-"

# A RUN of separators becomes ONE '-', so 'WF-.01' and 'WF__01' land together.
# The census SQL (`server/scripts/wf_spelling_census.sql`) writes this class as
# `[._[:space:]]+` -> '-', which folds the same pairs the operator reported
# ('WF.01' and 'WF-01' both reach 'WF-01'); including '-' in the class here is
# strictly more folding, and only for mixed/repeated runs.
_SEPARATOR_RUN_RE = re.compile(r"[._\-\s]+")

# --- Rejection codes (mirrors virtual_join_config's {scope,subject,detail,code})

CODE_SHAPE = "shape"
CODE_ZERO_PAD_UNIMPLEMENTED = "zero_pad_unimplemented"
CODE_UNKNOWN_RULE = "unknown_rule"
CODE_UNDECLARED = "undeclared"
CODE_WOULD_REWRITE_RAW = "would_rewrite_raw"
CODE_KEY_COLUMN = "key_column"

SCOPE_FILE = "file"
SCOPE_TABLE = "table"
SCOPE_COLUMN = "column"

# TTL cache, same discipline as `virtual_join_executor.RULES_CACHE_TTL`: the
# explicit invalidation (`reset_cache`) is wired into the web server's reload
# hook, and the TTL is what covers the worker processes that never reach it.
# A derivation spec that changes mid-batch is self-healing - re-deriving is the
# supported repair - so this does not need the per-file snapshot discipline that
# ingestion settings need.
RULES_CACHE_TTL = 5.0
_RULES_CACHE = {"at": 0.0, "by_table": None}


def reset_cache():
    """Drop the derivation-spec cache (web server config-reload hook)."""
    _RULES_CACHE["at"] = 0.0
    _RULES_CACHE["by_table"] = None


# ---------------------------------------------------------------------------
# The fold
# ---------------------------------------------------------------------------

def fold_notation(text, rules: dict):
    """Apply the ENABLED folding rules to an already-canonical string.

    Each rule is its own independent branch. Passing `{}` (or all-false) returns
    the input unchanged, which is what makes "prove each rule toggles alone"
    a real test rather than a claim.

    Non-strings pass through untouched: this folds NOTATION, and a value that is
    not text has none.
    """
    if not isinstance(text, str):
        return text
    out = text
    if rules.get(RULE_SEPARATOR):
        out = _SEPARATOR_RUN_RE.sub(SEPARATOR_TARGET, out)
    if rules.get(RULE_CASE):
        out = out.upper()
    return out


def normalized_value(table: str, column: str, value, rules: dict):
    """Raw stored value -> the derived normalized value (or None).

    Layered on `canonical_key_value`, never beside it (see module docstring).
    None and blank stay None: an absent value has no notation, and inventing
    '' here would make the derived column claim a value the row does not have.
    """
    canon = canonical_bind_value(table, column, value)
    if canon is None:
        return None
    folded = fold_notation(canon, rules or {})
    if isinstance(folded, str) and folded.strip() == "":
        return None
    return folded


# ---------------------------------------------------------------------------
# Declaration loading
# ---------------------------------------------------------------------------

def _record(rejections, scope: str, subject, detail: str, code: str = CODE_SHAPE):
    """One invalid declaration, collected for `GET /admin/config/resolve`.

    Same posture as `enrichment_config._record` and for the same reason - a skip
    that lives only in a daemon log is a skip nobody sees.
    """
    if rejections is None:
        return
    rejections.append({"scope": scope, "subject": subject, "detail": detail,
                       "code": code})


def _normalize_rules(raw, subject, rejections=None) -> dict:
    """A rule-toggle object -> the effective {rule: bool}, refusing by name.

    Unknown names and the unimplemented `zero_pad: true` are REJECTED, not
    dropped quietly. `zero_pad: false` is not a rejection - declaring a rule off
    is a decision on the record, and this repo distinguishes "declared false"
    from "undeclared" deliberately (`enrichment_config.auto_confirm_declared`).
    """
    effective = dict(DEFAULT_RULES)
    if raw is None:
        return effective
    if not isinstance(raw, dict):
        _record(rejections, SCOPE_TABLE, subject,
                "'rules' must be an object {rule_name: true|false}; the default "
                "rule set is used instead", CODE_SHAPE)
        return effective
    for name, on in raw.items():
        if not isinstance(name, str) or name.startswith("_"):
            continue  # '_'-prefixed names are comments, per the repo convention
        if name not in KNOWN_RULES:
            _record(rejections, SCOPE_TABLE, subject,
                    f"unknown rule '{name}'; known rules are "
                    f"{', '.join(KNOWN_RULES)}", CODE_UNKNOWN_RULE)
            continue
        if not isinstance(on, bool):
            _record(rejections, SCOPE_TABLE, subject,
                    f"rule '{name}' must be true or false (got {on!r}); the "
                    f"default is kept", CODE_SHAPE)
            continue
        if on and name not in IMPLEMENTED_RULES:
            _record(rejections, SCOPE_TABLE, subject,
                    f"rule '{name}' is declared but NOT IMPLEMENTED, so it is "
                    f"refused rather than silently ignored. It is the one rule "
                    f"that can merge two different entities ('WF010' and 'WF10' "
                    f"both become 'WF10'), and no census has said whether such a "
                    f"collapse exists here. Run the false-merge check first.",
                    CODE_ZERO_PAD_UNIMPLEMENTED)
            effective[name] = False
            continue
        effective[name] = on
    return effective


def _validate_column(table: str, raw_col: str, spec, table_rules: dict,
                     table_cfg: dict, rejections=None):
    """One raw->derived declaration. Returns the normalized dict, or None."""
    subject = f"{table}.{raw_col}"
    if isinstance(spec, str):
        derived, rules_raw = spec, None
    elif isinstance(spec, dict):
        derived, rules_raw = spec.get("derived"), spec.get("rules")
    else:
        _record(rejections, SCOPE_COLUMN, subject,
                "declaration must be either the derived column name (a string) "
                "or an object {derived, rules}", CODE_SHAPE)
        return None
    if not isinstance(derived, str) or not derived.strip():
        _record(rejections, SCOPE_COLUMN, subject,
                "'derived' must be a non-empty derived column name", CODE_SHAPE)
        return None
    derived = derived.strip()

    # 🔴 THE SAFETY PROPERTY. Everything in this module rests on the raw column
    # surviving untouched, so a declaration that would write the normalized
    # value back over its own source is refused here and cannot reach the write
    # path at all.
    if derived == raw_col:
        _record(rejections, SCOPE_COLUMN, subject,
                "the derived column must not be the raw column itself - this "
                "feature never rewrites a raw value, because a wrong folding "
                "rule is repaired by re-deriving and that repair needs the "
                "original to still be there", CODE_WOULD_REWRITE_RAW)
        return None

    col_types = (table_cfg or {}).get("column_types") or {}
    if raw_col not in col_types:
        _record(rejections, SCOPE_COLUMN, subject,
                f"raw column '{raw_col}' is not declared in table_config.json "
                f"for '{table}'", CODE_UNDECLARED)
        return None
    if derived not in col_types:
        _record(rejections, SCOPE_COLUMN, subject,
                f"derived column '{derived}' is not declared in "
                f"table_config.json for '{table}'. Add it as a \"string\" "
                f"column there first - until the physical column exists there "
                f"is nowhere to put the normalized value", CODE_UNDECLARED)
        return None
    if col_types.get(derived) != "string":
        _record(rejections, SCOPE_COLUMN, subject,
                f"derived column '{derived}' is declared as "
                f"'{col_types.get(derived)}'; a normalized notation is text and "
                f"must be declared \"string\" (a number column would refuse "
                f"'WF-01' outright)", CODE_SHAPE)
        return None

    # 🔴 A derived value must never be able to move a row's identity.
    key_col = (table_cfg or {}).get("business_key")
    comp_src = (table_cfg or {}).get("composite_key_source") or []
    if derived == key_col or derived in comp_src:
        _record(rejections, SCOPE_COLUMN, subject,
                f"derived column '{derived}' is part of this table's business "
                f"key, so deriving it would rewrite row identity. Phase 1 only "
                f"produces a value; what reads it is a separate decision",
                CODE_KEY_COLUMN)
        return None

    rules = _normalize_rules(rules_raw, subject, rejections) if rules_raw is not None \
        else dict(table_rules)
    return {"table": table, "raw": raw_col, "derived": derived, "rules": rules}


def validate_notation_rules(raw_config: dict, known_tables: dict = None,
                            rejections: list = None) -> dict:
    """Config dict -> `{table: {raw_col: {derived, rules, ...}}}`.

    `known_tables` is `crud.TABLE_CONFIG`. Passing None skips the
    table/column-existence checks (pure shape validation), matching
    `enrichment_config._validate_rule`.
    """
    by_table = {}
    if not isinstance(raw_config, dict):
        _record(rejections, SCOPE_FILE, None,
                "notation_rules.json must be an object; the whole file was "
                "ignored and NO column is normalized", CODE_SHAPE)
        return by_table

    file_rules = _normalize_rules(raw_config.get("rules"), None, rejections)

    columns = raw_config.get("columns")
    if columns is None:
        return by_table
    if not isinstance(columns, dict):
        _record(rejections, SCOPE_FILE, None,
                "'columns' must be an object {table: {raw_column: derived}}",
                CODE_SHAPE)
        return by_table

    for table, decls in columns.items():
        if not isinstance(table, str) or table.startswith("_"):
            continue  # '_'-prefixed names are comments, per the repo convention
        if not isinstance(decls, dict):
            _record(rejections, SCOPE_TABLE, table,
                    "declaration must be an object {raw_column: derived}",
                    CODE_SHAPE)
            continue
        table_rules = dict(file_rules)
        if "rules" in decls:
            table_rules = _normalize_rules(decls.get("rules"), table, rejections)
        table_cfg = None
        if known_tables is not None:
            table_cfg = known_tables.get(table)
            if table_cfg is None:
                _record(rejections, SCOPE_TABLE, table,
                        f"table '{table}' is not registered in table_config.json",
                        CODE_UNDECLARED)
                continue
        for raw_col, spec in decls.items():
            if raw_col == "rules" or raw_col.startswith("_"):
                continue
            normalized = _validate_column(table, raw_col, spec, table_rules,
                                          table_cfg or {}, rejections)
            if normalized is not None:
                by_table.setdefault(table, {})[raw_col] = normalized
    return by_table


def load_notation_rules(path: str = None, known_tables: dict = None,
                        rejections: list = None) -> dict:
    """Read + validate notation_rules.json. A missing file is NOT a rejection."""
    rules_path = path or NOTATION_RULES_PATH
    if not os.path.exists(rules_path):
        return {}
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
    except Exception as e:
        logger.error("Failed to load %s: %s", rules_path, e)
        _record(rejections, SCOPE_FILE, None,
                f"notation_rules.json could not be read "
                f"({e.__class__.__name__}) - NO column is normalized", CODE_SHAPE)
        return {}
    return validate_notation_rules(raw_config, known_tables=known_tables,
                                   rejections=rejections)


def derivations_by_table() -> dict:
    """`{table: {raw_col: spec}}`, TTL-cached. The write path's only entry."""
    import time

    now = time.monotonic()
    cached = _RULES_CACHE["by_table"]
    if cached is not None and (now - _RULES_CACHE["at"]) < RULES_CACHE_TTL:
        return cached
    try:
        from database import crud
        loaded = load_notation_rules(known_tables=crud.TABLE_CONFIG)
    except Exception as e:
        # An unreadable declaration means NO derivation is in effect. Failing the
        # write here would turn a config problem into an outage
        # (`refuse_virtual_join_columns` records the same trade).
        logger.error("[NotationNorm] declarations unreadable, no column is "
                     "derived: %s", e)
        loaded = {}
    _RULES_CACHE["by_table"] = loaded
    _RULES_CACHE["at"] = now
    return loaded


def derivations_for(table_name: str) -> dict:
    """`{raw_col: spec}` for one table (empty when nothing is declared)."""
    return derivations_by_table().get(table_name) or {}


def derived_columns_for(table_name: str) -> set:
    """The derived column NAMES of one table - the write-refusal's input."""
    return {d["derived"] for d in derivations_for(table_name).values()}


# ---------------------------------------------------------------------------
# The write-path hook
# ---------------------------------------------------------------------------

def apply_derivations(table_name: str, row, changed_cols, is_new: bool,
                      specs: dict = None) -> list:
    """Refresh every derived column of `row`. Returns the ones that moved.

    Called from `apply_row_update_internal` AFTER the value loop, so it reads
    the value that actually WON the priority computation rather than one
    source's contribution - the derived column mirrors what the row shows.

    Only recomputed when the raw column changed (or the row is new), so a table
    with no notation declarations pays one dict lookup per row and a table with
    them pays nothing on writes that do not touch a raw source.
    """
    specs = derivations_for(table_name) if specs is None else specs
    if not specs:
        return []
    touched = []
    changed = set(changed_cols or ())
    for raw_col, spec in specs.items():
        if not is_new and raw_col not in changed:
            continue
        derived_col = spec["derived"]
        if not hasattr(row, derived_col):
            # Config declares it, the physical model does not have it yet
            # (schema rollout in flight). Skipping mirrors the existing
            # config/model-mismatch behaviour; the next re-derivation fills it.
            continue
        new_val = normalized_value(table_name, raw_col,
                                   getattr(row, raw_col, None), spec["rules"])
        if getattr(row, derived_col, None) != new_val:
            setattr(row, derived_col, new_val)
            touched.append(derived_col)
    return touched


# ---------------------------------------------------------------------------
# Re-derivation - the repair that makes a wrong rule cheap
# ---------------------------------------------------------------------------

REDERIVE_CHUNK_SIZE = 1000

# Sample rows carried back in the report so the operator can SEE what a rule
# change did before committing to it.
REDERIVE_SAMPLES = 10


def rederive(db, table_name: str, spec: dict, chunk_size: int = REDERIVE_CHUNK_SIZE,
             apply: bool = False, progress=None) -> dict:
    """Recompute one table's derived column for EVERY row. Dry-run by default.

    This is the whole safety story in one function: edit the rules, run this,
    and the derived column is whatever the new rules say. No manual cleanup,
    because the raw column - the only thing that cannot be recomputed - was
    never touched.

    [10M-row discipline] Keyset pagination on `row_id` (the dynamic tables' PK),
    never OFFSET, which degrades to a full scan at depth. Three columns are
    fetched, not the row. Writes go out as `bulk_update_mappings` carrying ONLY
    `{row_id, <derived>}`, so the emitted UPDATE sets exactly one column and the
    raw value is not even mentioned in the statement.

    🔴 It deliberately does NOT route through `apply_batch_updates`: that path
    would refuse the write (`refuse_notation_derived_columns`), and even if it
    did not, layering a pure projection would mint a CellSource row per cell -
    10M extra metadata rows for a value that has no sources to arbitrate.
    """
    from database import models

    model = models.DYNAMIC_TABLES.get(table_name)
    if model is None:
        raise ValueError(f"table '{table_name}' has no initialized model")
    raw_name, derived_name = spec["raw"], spec["derived"]
    raw_col = getattr(model, raw_name, None)
    derived_col = getattr(model, derived_name, None)
    if raw_col is None or derived_col is None:
        raise ValueError(
            f"'{table_name}' has no column {raw_name if raw_col is None else derived_name} "
            f"on its model - declare it in table_config.json and let the ALTER run first")

    stats = {"table": table_name, "raw": raw_name, "derived": derived_name,
             "rules": dict(spec["rules"]), "mode": "apply" if apply else "dry-run",
             "scanned": 0, "changed": 0, "samples": []}
    last_id = ""
    while True:
        rows = (db.query(model.row_id, raw_col, derived_col)
                .filter(model.row_id > last_id)
                .order_by(model.row_id)
                .limit(chunk_size).all())
        if not rows:
            break
        pending = []
        for row_id, raw_val, cur_val in rows:
            last_id = row_id
            stats["scanned"] += 1
            new_val = normalized_value(table_name, raw_name, raw_val, spec["rules"])
            if cur_val != new_val:
                stats["changed"] += 1
                if len(stats["samples"]) < REDERIVE_SAMPLES:
                    stats["samples"].append({"raw": raw_val, "was": cur_val,
                                             "now": new_val})
                pending.append({"row_id": row_id, derived_name: new_val})
        if apply and pending:
            db.bulk_update_mappings(model, pending)
            db.commit()
        if progress is not None:
            progress(stats)
    return stats
