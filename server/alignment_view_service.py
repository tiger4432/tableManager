"""Shared, read-only alignment-view service for HTTP routes and chain mappers.

The public route and an automatic chain must never make independent alignment
decisions.  This module owns the small amount of rule/config validation that
surrounds :func:`map_alignment.build_alignment_view`; the scoring engine itself
remains the single implementation.
"""
from __future__ import annotations

from typing import Any

import enrichment_config
import map_alignment
import map_overlay
from database import crud


class AlignmentViewRequestError(ValueError):
    """A caller supplied a rule or decision key outside the declared contract."""


def declared_alignment_rule(rule_name: str) -> dict:
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    decl = next((r for r in rules if r["name"] == rule_name), None)
    if decl is None:
        raise AlignmentViewRequestError("Enrichment rule '%s' not found" % rule_name)
    if not decl.get("alignment"):
        raise AlignmentViewRequestError("Enrichment rule '%s' is not an alignment rule" % rule_name)
    return decl


def resolve_alignment_view(db, rule_name: str, key_values: dict[str, Any] | None,
                           map_table: str, *, reference_spec: str | None = None,
                           include_cells: bool = True, x_col: str | None = None,
                           y_col: str | None = None, value_col: str | None = None,
                           index_col: str | None = None,
                           assume_reference_geometry: bool = True) -> dict:
    """Return the same payload contract as ``GET /api/maps/alignment/view``.

    This deliberately performs no write and accepts already-parsed decision-key
    values, so a chain worker does not have to make a loopback HTTP request or
    create a second database snapshot.
    """
    decl = declared_alignment_rule(rule_name)
    if key_values is None:
        key_values = {}
    if not isinstance(key_values, dict):
        raise AlignmentViewRequestError("'params' must be an object")
    allowed = set(decl.get("decision_key", []))
    invalid = sorted(k for k in key_values if k not in allowed)
    if invalid:
        raise AlignmentViewRequestError(
            "'params' keys must be decision_key columns only; invalid: %s" % invalid)

    config = map_overlay.load_overlay_config()
    return map_alignment.build_alignment_view(
        db, config, decl, dict(key_values), map_table,
        reference_spec=reference_spec, include_cells=include_cells,
        x_col=x_col, y_col=y_col, value_col=value_col, index_col=index_col,
        assume_reference_geometry=assume_reference_geometry,
    )
