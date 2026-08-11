"""Which column of a table carries the DT job identity — READ, never assumed.

WHY THIS MODULE EXISTS
----------------------
Every chain mapper used to spell the job column ``dt_job``: either as a bare literal
(``_value(payload, "dt_job")``), or as the default half of
``rule.get("job_column", "dt_job")``.  A default that is only correct on the machine
that wrote it is worse than no default, because nobody ever has to declare the name
and so nobody ever finds out it is wrong.  The failure is SILENT at BOTH ends:

  * READING — ``_value(payload, "dt_job")`` returns ``None`` for a name the payload
    does not carry.  The mapper skips the row, returns an empty batch, and the chain
    worker records SUCCESS.  The loud ``source.dt_job`` ``AttributeError`` a few lines
    below is never reached, because the silent read already returned.
  * WRITING — ``crud.apply_batch_updates`` DROPS an ``updates`` key the target table
    does not declare in ``column_types``, warns once per ``(table, column)`` per
    process, and the write still returns success.

So a deployment that spells the column differently gets three dead chains, no
exception anywhere, and a 200.  No fixture in this repository could express that,
because every fixture writes ``dt_job``.

THE RULE
--------
::

    rule declaration  >  table_config derivation  >  refuse by name

There is no literal fallback.  ``68db020`` established exactly this precedence for map
coordinate bindings and deleted the convention fallback there for the same reason: a
name nobody declared, resolved to a convention, is a wrong answer wearing a configured
answer's clothes.  A refusal here names the rule, the config key, the table, and the
column, so the operator is told which declaration to write instead of being handed a
name that happens to work on one box.

PER TABLE, NOT PER CHAIN
------------------------
One mapper reads a trigger payload, queries a source table, and writes a target table.
Those are three different tables and they may legally spell the job differently — that
is precisely the case the single literal could not express.  Ask each table for its own
name, and let the rule override each one independently.

WHY NOT AN EXISTING PRIMITIVE
-----------------------------
The ``map_key_columns`` read IS an existing primitive and is reused:
``dt_map_derivation.identity_columns`` already reads it and already refuses by name.
This module wraps it rather than re-reading the key, so the chain and the dt_map
derivation cannot disagree about what a table's identity is.  What is added here and
does not belong there is (a) the rule-declaration layer, which is chain config that the
derivation engine has no business knowing about, and (b) the single-column
``business_key`` inheritance, which answers for a row-grained table like
``dt_inventory`` that is not a map at all.

``map_overlay.resolve_binding_parts`` is the other binding resolver and is deliberately
NOT reused: its precedence base is ``map_overlay_config.table_bindings``, it answers
about map coordinates, and it carries a lot/slot convention fallback that this change
exists to avoid.

DEPLOYMENT
----------
This module is TRACKED.  ``server/mappers/*.py`` is gitignored (only ``*.py.sample``
ships), so a helper placed beside the mappers would not reach a deployment at all.
"""
from __future__ import annotations

import logging

import dt_map_derivation

logger = logging.getLogger(__name__)


# Where a resolved name came from. Same vocabulary as `map_overlay`'s binding
# provenance, so an operator reading two refusals reads one language.
ORIGIN_DECLARED = "declared"
ORIGIN_INHERITED = "inherited"

_FROM_MAP_KEY_COLUMNS = "table_config.map_key_columns"
_FROM_BUSINESS_KEY = "table_config.business_key"


class ColumnBindingRefused(ValueError):
    """A column name could not be resolved, and the message NAMES what is missing.

    Subclasses ``ValueError`` on purpose: the chain worker aborts the transaction on
    any exception and logs the traceback, and the API layer already maps ``ValueError``
    to a 400 with the message body (same treatment as the ``replace_map`` scope
    refusal).  A new exception type would have needed both to be taught about it.
    """


def _table_config(table: str) -> dict:
    """Live declaration for `table`.

    Read through the module attribute every time — `crud.TABLE_CONFIG` is mutated in
    place on hot reload, so a snapshot taken at import goes stale silently.
    """
    from database import crud
    return (crud.TABLE_CONFIG or {}).get(table) or {}


def declared_columns(table: str):
    """Column names `table_config` states for `table`, or None if it states nothing.

    None means "I cannot judge this declaration" and is why a table absent from
    `table_config` keeps working instead of being refused.
    """
    types = _table_config(table).get("column_types")
    if not isinstance(types, dict) or not types:
        return None
    return set(types.keys())


def identity_column(table: str):
    """`(column, from)` derived from `table_config` alone, or `(None, why_not)`.

    Order:
      1. ``map_key_columns`` when it names EXACTLY ONE column — that column says which
         map/unit a row belongs to, which for these tables is the job.
      2. ``business_key`` when the table declares no ``composite_key_source`` and the
         business key is itself a declared column.  A table with no map key whose row
         identity is a single column is keyed by that column outright — ``dt_inventory``
         is one row per job and its business key IS the job.  The
         ``composite_key_source`` gate is what stops a composite CELL key
         (``dt_cell_key``, ``cell_key``, ``core_usage_cell_key``) from being mistaken
         for an identity column.
      3. Nothing.  Not a guess.
    """
    try:
        cols = dt_map_derivation.identity_columns(table)
    except dt_map_derivation.DerivationRefused:
        cols = []
    if len(cols) == 1:
        return cols[0], _FROM_MAP_KEY_COLUMNS
    if len(cols) > 1:
        return None, ("'%s' declares %d map_key_columns (%s), so which one carries the "
                      "job is not derivable" % (table, len(cols), ", ".join(cols)))

    cfg = _table_config(table)
    business_key = cfg.get("business_key")
    known = declared_columns(table)
    if (isinstance(business_key, str) and business_key.strip()
            and not cfg.get("composite_key_source")
            and known is not None and business_key in known):
        return business_key, _FROM_BUSINESS_KEY
    return None, ("'%s' declares neither a single-column 'map_key_columns' nor a "
                  "single-column 'business_key'" % table)


def _refuse_unknown(rule_name, key, name, table, purpose, known):
    raise ColumnBindingRefused(
        "chain rule '%s' resolves %s='%s' for %s on table '%s', but '%s' declares no "
        "such column (declared: %s). Correct the name in chain_rules.json, or declare "
        "the column in table_config.json — it cannot be inherited while a declaration "
        "out-ranks the derivation."
        % (rule_name, key, name, purpose, table, table, ", ".join(sorted(known))))


def resolve_column(rule, key: str, table: str, purpose: str) -> str:
    """The column of `table` that carries the job, for this rule. No literal default.

    `rule[key]` wins; otherwise `table_config` derives it; otherwise this REFUSES and
    the message names the rule, the key and the table.  `purpose` is a short phrase
    that says what the name is for ("the payload the chain is triggered by", "the
    output key written to the target"), so a refusal is actionable without reading the
    mapper.
    """
    rule = rule or {}
    rule_name = rule.get("name") or "<unnamed rule>"
    if not isinstance(table, str) or not table.strip():
        raise ColumnBindingRefused(
            "chain rule '%s' names no table for %s, so its job column cannot be "
            "resolved. Declare the table on the rule in chain_rules.json."
            % (rule_name, purpose))
    known = declared_columns(table)

    declared = rule.get(key)
    if isinstance(declared, str) and declared.strip():
        name = declared.strip()
        if known is not None and name not in known:
            _refuse_unknown(rule_name, key, name, table, purpose, known)
        return name

    name, origin_or_why = identity_column(table)
    if name is None:
        raise ColumnBindingRefused(
            "chain rule '%s' does not declare '%s' and it cannot be derived: %s. "
            "Declare '%s' on the rule in chain_rules.json, or give '%s' a "
            "single-column 'map_key_columns' in table_config.json. Refusing instead of "
            "assuming 'dt_job' — that name is only correct on the machine that wrote "
            "it, and assuming it makes %s fail silently."
            % (rule_name, key, origin_or_why, key, table, purpose))
    if known is not None and name not in known:
        _refuse_unknown(rule_name, key, name, table, purpose, known)
    logger.debug("[ChainBinding] %s.%s = '%s' (%s, for %s)",
                 rule_name, key, name, origin_or_why, purpose)
    return name


def resolve_decision_column(rule, key: str, decision_key, purpose: str) -> str:
    """Same precedence, for a name that must live in an alignment rule's decision key.

    The value is looked up out of a `key_values` dict whose keys ARE the alignment
    rule's `decision_key`, so the derivation source is that declaration rather than a
    table, and a declared name outside it can never match anything.
    """
    rule = rule or {}
    rule_name = rule.get("name") or "<unnamed rule>"
    names = [str(c) for c in (decision_key or ()) if str(c).strip()]

    declared = rule.get(key)
    if isinstance(declared, str) and declared.strip():
        name = declared.strip()
        if names and name not in names:
            raise ColumnBindingRefused(
                "chain rule '%s' declares %s='%s' for %s, but the alignment rule's "
                "decision_key is [%s]. A name outside the decision key matches nothing "
                "and would read as 'no job'."
                % (rule_name, key, name, purpose, ", ".join(names)))
        return name

    if len(names) == 1:
        return names[0]
    raise ColumnBindingRefused(
        "chain rule '%s' does not declare '%s' and the alignment rule's decision_key "
        "[%s] does not name exactly one column, so %s cannot be derived. Declare '%s' "
        "on the rule in chain_rules.json. Refusing instead of assuming 'dt_job'."
        % (rule_name, key, ", ".join(names) or "<empty>", purpose, key))


def model_column(model, table: str, column: str, purpose: str):
    """The mapped attribute for `column`, or a refusal that names table and column.

    Replaces the `hasattr(...)` gates that used to `return {}` — a loaded model without
    the resolved column means `table_config` and the physical table disagree, and
    continuing produced an empty batch that the worker recorded as success.
    """
    attribute = getattr(model, column, None)
    if attribute is None:
        raise ColumnBindingRefused(
            "'%s' resolves its job column to '%s' for %s, but the loaded model has no "
            "such attribute. table_config and the physical table disagree — run the "
            "schema sync, or correct the name." % (table, column, purpose))
    return attribute
