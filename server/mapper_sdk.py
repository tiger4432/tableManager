# -*- coding: utf-8 -*-
"""What a chain mapper's author should not have to write.

The owner's shape for a mapper is three steps:

    ① payloads          -> DataFrame
    ② DataFrame + SQL   -> DataFrame        <- the only one the author writes
    ③ DataFrame         -> updates payload

and the goal is that ① and ③ leave the author's file. This module is where they go.

🔴 IT LIVES HERE AND NOT IN `mappers/` BECAUSE `mappers/` DOES NOT SHIP. `.gitignore`
excludes `server/mappers/*` and re-admits only `*.sample` and `ledger_v2_*.py`, so a
module put beside the mappers would exist on the box that wrote it and nowhere else -
the same failure a declaration pointing at a hand-made view has. Authors import it by
name; nothing here asks to be inherited from.

🔴 AND NO DOMAIN MODULE IS IMPORTED HERE. A mapper that never touches a map must not
drag the map engine in behind it, so this file knows about payloads, frames and the
table declaration, and about nothing else.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def _python_scalar(value):
    """A numpy scalar as the Python value the writer's type check expects.

    🔴 MEASURED 2026-09-03: on this pandas, `astype(object).to_dict("records")` already
    hands back `int`, `float`, `bool`, `Timestamp` and `str` - NOTHING with `.item()`. So
    on the frame path below this function is a pass-through today, and that is written
    down rather than left for someone to discover by deleting it and seeing nothing go
    red.

    It stays, and it is tested directly, because the conversion is part of the contract
    the guide states rather than an artefact of one pandas version: older pandas returned
    `numpy.int64` from `to_dict`, and a `numpy.int64` is not an `int` to everything
    downstream. What must not happen is a branch nobody can reach that still reads like a
    handled case - so the test feeds it numpy scalars directly.
    """
    return value.item() if hasattr(value, "item") else value


class MapperContractError(ValueError):
    """The frame cannot be turned into a payload the writer would accept. Named, never
    silently emitted - every failure this raises is one that otherwise lands rows the
    upsert can never find again."""


def payloads_to_df(payloads: List[Dict[str, Any]]) -> pd.DataFrame:
    """Outbox payloads -> one flat row each. Step ①.

    The cell shape is `{col: {"value": x, ...}}`; this keeps the value and drops the
    envelope, and carries `row_id` through because identity is not a data column.

    This is the SAME implementation `mappers/utils.payloads_to_df` holds, so that
    `BaseMapper` - which the owner keeps for the production mappers that inherit it -
    and this SDK cannot answer differently. Two doors, one judgement.
    """
    if not payloads:
        return pd.DataFrame()

    flat_rows = []
    for p in payloads:
        flat_row = {"row_id": p.get("row_id")}
        for col_name, cell in (p.get("data") or {}).items():
            flat_row[col_name] = (cell["value"]
                                  if isinstance(cell, dict) and "value" in cell
                                  else cell)
        flat_rows.append(flat_row)
    return pd.DataFrame(flat_rows)


class BaseMapper:
    """The name the production mappers already import. Owner's ruling: leave it alone.

    🔴 IT LIVES HERE SO THE IMPLEMENTATION SHIPS. It was defined in `mappers/base.py`,
    which `.gitignore` excludes, so production carries its own copy and a fix here would
    never reach it. Moving the class into a tracked file makes `mappers/base.py` a
    re-export - one edit per box, once - and after that the implementation travels the
    normal way.

    🔴 THE SURFACE IS UNCHANGED AND STAYS THAT WAY. One static method, the same name and
    signature, delegating to the same `payloads_to_df` the SDK exposes - there is no
    second copy to drift. Nothing inherits from this class today (both call sites use
    `BaseMapper.payloads_to_df(...)` statically, whatever the old docstring said), so the
    move breaks no inheritance chain. Adding a method here would start making inheritance
    look like the intended route; new mappers should use the functions.
    """

    @staticmethod
    def payloads_to_df(payloads: List[Dict[str, Any]]) -> pd.DataFrame:
        """Nested outbox payloads -> a flat DataFrame. Delegated, never re-implemented."""
        return payloads_to_df(payloads)


def sql(db, query: str, params: dict | None = None) -> pd.DataFrame:
    """A read, as a DataFrame, ON THE CALLER'S SESSION. Step ② is the author's; this is
    the one piece of it they should not have to assemble.

    🔴 IT USES `db`, NOT A NEW CONNECTION, AND THAT IS THE PROPERTY THAT MATTERS. A chain
    mapper runs inside the worker's transaction and is forbidden to commit, so rows the
    chain has already staged in that transaction are visible to it and to nothing else. A
    helper that opened its own connection would read the database as it was BEFORE this
    batch - the mapper would derive from stale state, silently, and only under
    concurrency. Passing the session through is what keeps "what I can see" the same
    question for the ORM path and this one.

    🔴 PARAMETERS ARE BOUND, NEVER FORMATTED. `sql(db, "... WHERE lot = :lot", {"lot": x})`.
    A mapper composing its own string would be one value away from an injection and, more
    ordinarily, one `None` away from `WHERE lot = None` silently matching nothing.

    ⚠️ COLUMN NAMES STILL COME FROM THE DECLARATION. This helper cannot check that for
    you: a query that spells its own column names is the same defect as a mapper that
    does, and it is the author's to avoid (guide, "Column names: read them, never spell
    them").

    ⚠️ AND SQL NULL ARRIVES AS `NaN`, whose type is float. That is pandas, not this
    function - `df_to_updates` turns it back into `None` on the way out, which is the
    only reason a mapper can round-trip a null without spelling the repair itself.
    """
    from sqlalchemy import text

    return pd.read_sql(text(query), db.connection(), params=params or {})


def df_to_updates(df, table_name: str, *, source_name: str, updated_by: str) -> dict:
    """DataFrame -> the `{"updates": [...]}` a chain mapper returns. Step ③.

    🔴 THE AUTHOR DOES NOT DECIDE THE BUSINESS KEY, AND THAT IS THE POINT OF THIS
    FUNCTION. Whether a target composes its key from several columns or carries one
    outright is a fact about the DECLARATION, and getting it wrong is silent in both
    directions:

        composite target, key spelled by the mapper
            ⚰️ UNTIL 판정 190 the mapper's string won: `assemble_composite_business_key`
            returned at its first statement when the item already carried a
            `business_key_val`, so a mapper that spelled its own key silently stopped
            following the declaration. It no longer does — the assembly runs whenever
            the parts are there and the DECLARATION wins, so a separator or column-list
            change now reaches every mapper instead of drifting in one.

        non-composite target, key left to the framework
            nothing lifts `updates[business_key]` into `business_key_val` -
            `_get_or_create_row` resolves identity from `row_id`/`business_key_val`
            alone - so the write has NO identity. The row lands, the upsert can never
            find it again, and every run inserts another copy. `unfilled_key_columns`
            answers `[]` for such an item, so the pre-write gate does not catch it
            either.

    Both were measured on 2026-09-02, and both are the kind that is found much later by
    someone counting rows. So the author emits columns and this function reads
    `TABLE_CONFIG` to decide which of the two the target is.

    🔴 AND A MISSING KEY COLUMN IS REFUSED RATHER THAN EMITTED. On a composite target an
    absent source column assembles nothing and the key stays `None`; on a plain one an
    absent key column produces the identity-less write above. Both are refused here, by
    name, because a batch that lands without identity cannot be distinguished afterwards
    from one that was never sent.

    🔴 SO IS A MISSING *DECLARATION*, AND THAT IS A DIFFERENT SENTENCE. The paragraph
    above was true of a COLUMN and silently false of the declaration that names it: when
    this process cannot see the table at all, or sees it and finds no key declared,
    neither branch below fires and the envelope went out with no `business_key_val` and
    no refusal - the exact identity-less write the paragraph promises to refuse. It lands
    without an error, because a UNIQUE index treats NULLs as distinct, so every run adds
    another copy (owner report 2026-09-07, running a decorated mapper in production).

    The two cases get their own sentence because the operator's next move differs: an
    unreadable table is a CONFIGURATION fact (this process did not load it, or the rule
    names it differently), a keyless one is a DECLARATION fact (nothing says what
    identifies a row of it). One message for both sends them looking in one place.

    NaN and NaT become `None`, not the string "nan". `pd.read_sql` turns SQL NULL into
    NaN - a float - so a bare `to_dict("records")` turns "there was no value" into "the
    value is nan", which is a value. Measured 2026-09-02 on `lot_event.parent_lot`.
    numpy scalars become Python scalars for the same reason: what reaches the writer has
    to be what the declaration's type check expects.
    """
    from database import crud            # lazy: `crud` imports back into this layer

    if df is None or len(df) == 0:
        return {"updates": []}

    # NOT `or {}`. That turned "this process cannot see the table" into "the table
    # declares nothing", and the second is a state this function can reason about while
    # the first is one it must refuse.
    config = crud.TABLE_CONFIG.get(table_name)
    if config is None:
        raise MapperContractError(
            f"'{table_name}' is not among the table declarations this process loaded, so "
            f"there is nothing to read the business key from. Emitting anyway lands rows "
            f"with no identity. Check that the target table is declared in "
            f"table_config.json and that this process has been restarted since.")
    composite_src = config.get("composite_key_source")
    key_col = config.get("business_key")

    # 🔴 `astype(object)` FIRST. On a column pandas typed as float, assigning None puts
    # NaN back; widening to object is what lets the None survive to the payload.
    clean = df.astype(object).where(pd.notna(df), None)

    columns = list(clean.columns)
    if composite_src:
        missing = [c for c in composite_src if c not in columns]
        if missing:
            raise MapperContractError(
                f"'{table_name}' composes its key from {list(composite_src)} and the "
                f"frame has no {missing}. Emitting anyway would land rows whose key is "
                f"None - they insert, they never match again, and nothing errors.")
    elif key_col:
        if key_col not in columns:
            raise MapperContractError(
                f"'{table_name}' carries the key '{key_col}' and the frame has no such "
                f"column. Emitting anyway would land rows with no identity - the upsert "
                f"cannot find them again and every run inserts another copy.")
    else:
        raise MapperContractError(
            f"'{table_name}' declares no identity: it names neither a "
            f"'composite_key_source' nor a 'business_key', so no column of this frame "
            f"identifies a row of it. Emitting anyway lands rows with no identity - the "
            f"upsert cannot find them again and every run inserts another copy.")

    updates = []
    for record in clean.to_dict("records"):
        values = {k: _python_scalar(v) for k, v in record.items()}
        item = {"updates": values,
                "source_name": source_name, "updated_by": updated_by}
        if not composite_src and key_col:
            # The plain case, and the ONLY one where this function names the key: the
            # framework does not lift it out of `updates`, so somebody has to, and it is
            # not the author's job to remember which tables those are.
            identity = values.get(key_col)
            if crud.is_blank_value(identity):
                raise MapperContractError(
                    f"'{table_name}' carries the key '{key_col}' and a row leaves it "
                    f"blank. That row would land with no identity; refused rather than "
                    f"written.")
            item["business_key_val"] = crud.clean_str_value(identity)
        updates.append(item)
    return {"updates": updates}

# ---------------------------------------------------------------------------
# S-188 ⓒ — the decorator IS the registry (판정 300)
# ---------------------------------------------------------------------------
#: name -> the wrapped callable the worker calls. 🔴 BEFORE THIS, `@mapper` REGISTERED
#: NOTHING: it wrapped `(df, db) -> df` into `(db, payloads, rule)` and returned it, so a
#: rule had to name its mapper with TWO cells (`mapper_module` + `mapper_function`) and the
#: worker resolved them with `importlib`. Nothing could answer 「which mappers exist」 --
#: which is what the builder needs and what ⓓ needs to collapse those two cells into one.
MAPPER_REGISTRY: dict[str, object] = {}

#: name -> the argument names that mapper reads out of its rule's `params` block. Declared
#: in CODE, beside the logic, because `server/mappers/**` is the OWNER's and gitignored:
#: the product cannot discover what a mapper reads, so the mapper has to say.
MAPPER_PARAMS: dict[str, tuple] = {}


class MapperNameClaimedTwice(MapperContractError):
    """⛔ REFUSED BY NAME, NEVER RESOLVED. Two mappers under one name means a rule naming it
    gets whichever module imported last -- an answer that changes with import order and says
    nothing about it. The same posture `load_chain_rules` takes toward a rule name claimed
    by both `chain_rules.json` and a synthesized rule (S-179 ①, 판정 292)."""


def reset_registry():
    """Forget every registration. 🔴 CALLED WHERE `mappers.*` LEAVES `sys.modules`.

    The registry lives in THIS module, which a reload does NOT evict, while the mapper
    modules it points into ARE evicted (`system_reload`). Left alone, the registry would
    hand the worker functions from modules nobody can reach any more, and the re-import
    would then trip `MapperNameClaimedTwice` on every name -- so a reload would break
    exactly the thing it exists to refresh.
    """
    MAPPER_REGISTRY.clear()
    MAPPER_PARAMS.clear()


def _origin(fn):
    """Where a registration came from — the MODULE, which is the unit that gets re-imported.

    ⛔ NOT `module.qualname`. That was the first spelling and it broke `test_mapper_sdk`:
    a function defined inside a test carries `…<locals>.emit` in its qualname, so two tests
    reusing one name looked like two different mappers and the second was refused. A module
    cannot hold two top-level functions of one name anyway — Python decides that — so the
    module is the whole of what 「same mapper」 means here.
    """
    return getattr(fn, "__module__", "?")


def register(name: str, fn, params=()):
    """One registration. Separate from the decorator so `discover` and a test share it."""
    existing = MAPPER_REGISTRY.get(name)
    # 🔴 「SAME NAME」 IS DECIDED BY ORIGIN, NOT BY OBJECT IDENTITY. A reload re-imports the
    # module, and the decorator then builds a NEW wrapper for the SAME source -- identity
    # would call that a collision and a reload would refuse every mapper it refreshed. What
    # must be refused is TWO modules claiming one name, because then which one a rule meant
    # depends on import order and nothing says so.
    if existing is not None and _origin(existing) != _origin(fn):
        raise MapperNameClaimedTwice(
            f"two mappers are registered as '{name}': "
            f"{_origin(existing)} and {_origin(fn)}. "
            f"Rename one - a rule naming '{name}' cannot say which it meant.")
    MAPPER_REGISTRY[name] = fn
    MAPPER_PARAMS[name] = tuple(params)
    return fn


def discover(package="mappers"):
    """Import every module of the mapper package so its decorators run. Returns
    `(registered, refusals)` where `refusals` is `{module: message}`.

    🔴 ONE BROKEN MAPPER MUST NOT COST THE OTHERS (S-177's posture). These files are the
    owner's; an ImportError in one is a thing to be told about by name, not a reason for the
    chain to come up with no mappers at all. `warmup_worker` already imports this way for
    the modules rules NAME -- this walks the package, because 「which mappers exist」 cannot
    be answered from the rules that happen to use them.
    """
    import importlib
    import pkgutil

    refusals = {}
    try:
        pkg = importlib.import_module(package)
    except Exception as exc:
        return tuple(MAPPER_REGISTRY), {package: f"{type(exc).__name__}: {exc}"}

    for info in pkgutil.iter_modules(getattr(pkg, "__path__", [])):
        name = f"{package}.{info.name}"
        try:
            importlib.import_module(name)
        except Exception as exc:
            refusals[name] = f"{type(exc).__name__}: {exc}"
    return tuple(sorted(MAPPER_REGISTRY)), refusals


def mapper(target_table=None, *, source_name: str = "chain_ingestion",
           updated_by: str | None = None, params=(), name: str | None = None):
    """Wrap an author's `(df, db) -> df` so that ① and ③ leave their file. Step ③ of the
    owner's shape, as a decorator.

        @mapper()
        def build_rows(df, db):
            ...                       # the author writes ONLY this
            return out                # a DataFrame

    What the worker calls is still `(db, payloads, rule=None)`, so a decorated function
    drops into `chain_rules.json` exactly where a hand-written one did - the SDK is not a
    second calling convention.

    🔴 THE TARGET TABLE COMES FROM THE RULE, NOT FROM THE DECORATOR, unless the author
    names one. `rule["target_table"]` is where that fact already lives, and a mapper that
    restates it is a second place for it to be wrong - the same defect as a mapper that
    spells a column name. The argument exists for the case where a rule cannot supply it;
    when both are present the rule wins, because the rule is what the operator edits.

    🔴 AND `updated_by` DEFAULTS TO THE AUTHOR'S FUNCTION NAME. Provenance that has to be
    typed is provenance that gets copied from the last mapper and then names the wrong
    one; the function's own name cannot drift from the function.

    ⚠️ A DataFrame that comes back EMPTY is an intentional no-op, and `{"updates": []}` is
    what the worker reads as one. A mapper returning `None` would hit
    `if target_payload and ...` and be read the same way, but only by accident.
    """
    def decorate(fn):
        import functools

        @functools.wraps(fn)
        def run(db, payloads, rule=None):
            table = (rule or {}).get("target_table") or target_table
            if not table:
                raise MapperContractError(
                    f"'{fn.__name__}' has no target table: the rule declares no "
                    f"'target_table' and the decorator was given none. The business key "
                    f"is decided from that table's declaration, so there is nothing to "
                    f"decide it from.")
            out = fn(payloads_to_df(payloads), db)
            if out is None:
                return {"updates": []}
            if not isinstance(out, pd.DataFrame):
                raise MapperContractError(
                    f"'{fn.__name__}' returned {type(out).__name__}; a decorated mapper "
                    f"returns a DataFrame and the envelope is built for it. Returning the "
                    f"envelope yourself means this decorator is not the thing you want.")
            return df_to_updates(out, table, source_name=source_name,
                                 updated_by=updated_by or fn.__name__)
        # 🔴 REGISTERED UNDER THE AUTHOR'S FUNCTION NAME unless one is given. The name a
        # rule writes has to be a name the author can see in their own file; a generated
        # one would be a third thing to keep in step. `params` is the argument names this
        # mapper reads out of `params` -- the loader warns about a name nobody declared,
        # and only the mapper can declare it (its file is gitignored).
        return register(name or fn.__name__, run, params)
    return decorate


# ---------------------------------------------------------------------------
# 🔴 THE SURFACE A MAPPER MAY IMPORT — declared here, resolved when touched (S-215, 판정 369)
# ---------------------------------------------------------------------------
#
# 🔴 WHY A TABLE AND NOT IMPORTS AT THE TOP: these nine modules are 13,406 lines, and
# `mapper_sdk` is read on the chain worker's BOOT path. Re-exporting eagerly would put all of
# it there for the sake of names most mappers never touch. Resolved on first access, a mapper
# pulls only what it uses and a process that uses none pays nothing.
#
# 🔴 AND THE TABLE IS THE DECLARATION. Re-export cannot wander outside it, because
# `__getattr__` has no other source - which is what makes 「only from the declared surface」 a
# property of the code rather than a habit.
#
# ⚠️ THE NAMES ARE NOT CHOSEN, THEY ARE MEASURED. This is what the owner's live mappers
# actually import today (`server/mappers/*.py`, gitignored - their files, read but never
# edited). It is a CONTRACT, not a wish list: shortening it breaks files this repo cannot see.
#
# ⚠️ TWO OF THEM ARE PRIVATE (`_cells_of`, `_load_metas`), and they are here under exactly
# those spellings (판정 368). A `_name` on an SDK looks wrong, and it is - but it is already
# the contract, and this round WRITES the contract down rather than changing it. Renaming
# would edit the operator's files, which is the one thing this surface exists to avoid.
#
# ⚠️ WHAT IS NOT HERE: `_load_metas` has a reporting variant that discards `complete`, and it
# stays out (판정 368 ④). What rides is what mappers use, nothing beside it.
MAPPER_SURFACE = {
    "CONFIRMED_JOIN_RULE": "dt_map_derivation",
    "ColumnBindingRefused": "chain_bindings",
    "DEFAULT_RULES": "notation_norm",
    "DerivationRefused": "dt_map_derivation",
    "FRAME_JOIN_RULE": "dt_map_derivation",
    "INDEX_AXIS_RANKING": "map_alignment",
    "MAX_VALID_DIE_CELLS": "map_overlay",
    "METRIC_INDEX": "map_alignment",
    "PLACEMENT_ANCHOR": "map_alignment",
    "REFUSE_SCOPE_TOO_LARGE": "dt_map_derivation",
    "SCOPE_ROW_CAP": "dt_map_derivation",
    "STATE_SCORED": "map_alignment",
    "VALID_DIE_REF_KEY": "map_overlay",
    "_cells_of": "map_alignment",
    "_load_metas": "map_alignment",
    "apply_dt_equations": "dt_frame_transform",
    "apply_valid_die_ref": "map_overlay",
    "basis_cells_for": "map_alignment",
    "compose_map_id": "map_meta_registrar",
    "confirmed_meta_for": "map_alignment",
    "core_equations": "dt_frame_transform",
    "declared_alignment_rule": "alignment_view_service",
    "declared_columns": "chain_bindings",
    "derive_cells": "dt_map_derivation",
    "dt_equations": "dt_frame_transform",
    "fold_notation": "notation_norm",
    "fold_notation_sql": "notation_norm",
    "frame_trigger_scope": "dt_map_derivation",
    "identity_columns": "dt_map_derivation",
    "join_pairs": "dt_map_derivation",
    "join_rule": "dt_map_derivation",
    "load_map_meta": "map_overlay",
    "load_overlay_config": "map_overlay",
    "meta_business_key": "map_meta_registrar",
    "model_column": "chain_bindings",
    "resolve_alignment_view": "alignment_view_service",
    "resolve_column": "chain_bindings",
    "resolve_decision_column": "chain_bindings",
    "resolve_table": "chain_bindings",
    "slow_warn_ms": "event_constants",
    "standard_meta": "dt_frame_transform",
}


def __getattr__(name):
    """Resolve a declared surface name to the REAL object in its module.

    🔴 THE SAME OBJECT, NOT A COPY (판정 368 ①). This returns what the source module holds,
    so `mapper_sdk.fold_notation is notation_norm.fold_notation`. A wrapper here would be a
    second implementation of something that already has one, and the two would drift.

    ⛔ NO BRANCH BEYOND THE TABLE (판정 369). A name that is not declared raises the ordinary
    `AttributeError` - this seat does not compose a refusal sentence. Inventing one would put
    a second author on a message Python already writes, and would make a typo look like a
    product rule.
    """
    source = MAPPER_SURFACE.get(name)
    if source is None:
        raise AttributeError(name)
    import importlib

    return getattr(importlib.import_module(source), name)


# ---------------------------------------------------------------------------
# 🔴 WHAT A RULE MAY NAME — the candidates a screen offers (S-223, 판정 379)
# ---------------------------------------------------------------------------

def _registered_kinds():
    """The `builtin:…` kinds, as things a rule can NAME - 판정 511.

    🔴 THE SCREEN COULD NOT DECLARE A JOIN. 소유자 2026-09-17: 「어드민 체인 규칙
    등록은 왜 옛날 모양이냐」. This list offered `MAPPER_REGISTRY` names and module-level
    functions - two of the three ways a rule names its code (판정 496) - and left the third
    out, so the operator had to hand-edit JSON to declare a join or an auto-confirm. A round
    that made one seat run every kind has not arrived while the place an operator WRITES the
    declaration still knows two kinds out of three.

    ⚠️ READ OFF THE REGISTRATION, NOT A LIST HERE. The name, and the word the product calls
    it, are both what `register_builtin` was given - so a fourth kind appears in the dropdown
    the day it is registered, with nobody editing this function.

    ⚠️ AND IT IS WRAPPED. This is the mapper listing; if the chain package cannot be
    imported in this process the other two families must still reach the screen.
    """
    try:
        from chain import builtins as chain_builtins
    except Exception:                          # pragma: no cover - chain absent
        return []
    return [{"module": "chain.builtins", "name": kind, "kind": "builtin",
             "label": chain_builtins.BUILTIN_LABELS.get(kind), "params": None}
            for kind in sorted(chain_builtins.BUILTIN_KINDS)]


def mapper_candidates(package="mappers"):
    """-> `{"candidates": [...], "other": [...], "refused": [...]}` from IMPORTED modules.

    🔴 THE DROPDOWN WAS EMPTY AND THE REASON WAS A CATEGORY ERROR. It offered
    `MAPPER_REGISTRY` alone - the names `@mapper` registered - while every mapper actually
    running on the owner's box is a MODULE-LEVEL FUNCTION a rule names through
    `mapper_function`. So the one list a screen had said 「no options」 about a directory full
    of working mappers.

    🔴 A CLASS IS NOT A CANDIDATE (measured, 판정 379). `execute_custom_mapper` does
    `getattr(module, name)` and then calls it, so a class is CONSTRUCTED - an instance goes on
    to the row count and a wrong answer leaves quietly. Callable is not runnable.

    🔴 THREE BUCKETS, MUTUALLY EXCLUSIVE, because 「it is not here」, 「it is broken」 and 「it is
    a different thing」 are three answers and collapsing any two of them puts a false sentence
    on the screen:
        candidates  a rule can name this today
        other       imports fine, but is a LEDGER roleframe mapper - no chain rule names it
        refused     did not import, with the reason by name

    ⚠️ `other` IS DECIDED ONLY AMONG MODULES THAT IMPORTED. Judging a family from a file that
    could not be loaded is exactly the mistake this round's own measurement made: parsing a
    file says nothing about importing it. A module that fails to import is `refused` and
    nothing else, and it MOVES to `other` the day it loads.

    ⚠️ A FUNCTION IS FILTERED BY ITS SIGNATURE, NEVER BY ITS NAME. The executor hands over
    `(db, payload)`, so 「takes at least two positional arguments」 is the property; a name
    filter would be this repository's oldest defect wearing a new hat.
    """
    import importlib
    import inspect
    import sys as _sys

    registered_names, refusals = discover(package)
    candidates = _registered_kinds() + [
        {"module": _origin(MAPPER_REGISTRY[name]), "name": name,
         "kind": "registered", "params": list(MAPPER_PARAMS.get(name, ()))}
        for name in registered_names if name in MAPPER_REGISTRY]

    # 🔴 A REGISTERED MAPPER IS NOT ALSO A PLAIN FUNCTION. `@mapper` leaves its wrapper
    # bound to the module-level name too, so the sweep below would list the SAME OBJECT a
    # second time under `kind: function` - one mapper, two rows, and the operator with no way
    # to tell that picking either runs the same code. Identity decides it, not the name.
    registered_objects = {id(MAPPER_REGISTRY[name])
                          for name in registered_names if name in MAPPER_REGISTRY}

    try:
        roleframe_base = importlib.import_module("ledger.roleframe").BaseLedgerMapper
    except Exception:                                    # pragma: no cover - ledger absent
        roleframe_base = None

    other = []
    prefix = package + "."
    for module_name in sorted(n for n in list(_sys.modules) if n.startswith(prefix)):
        module = _sys.modules.get(module_name)
        if module is None or module_name in refusals:
            continue
        functions = []
        roleframe_only = False
        for attribute, value in sorted(vars(module).items()):
            if attribute.startswith("_"):
                continue
            if (inspect.isfunction(value) and value.__module__ == module_name
                    and id(value) not in registered_objects):
                spec = inspect.getfullargspec(value)
                if len(spec.args) >= 2:
                    functions.append(attribute)
            elif (roleframe_base is not None and inspect.isclass(value)
                  and value is not roleframe_base and issubclass(value, roleframe_base)
                  and value.__module__ == module_name):
                roleframe_only = True
        for attribute in functions:
            candidates.append({"module": module_name, "name": attribute,
                               "kind": "function", "params": None})
        if not functions and roleframe_only:
            other.append({"module": module_name, "kind": "ledger_roleframe",
                          "why": "원장 롤프레임 매퍼입니다 — 체인 규칙이 이 모듈을 들지 않습니다"})

    return {
        "candidates": candidates,
        "other": other,
        "refused": [{"module": name, "why": why} for name, why in sorted(refusals.items())],
    }
