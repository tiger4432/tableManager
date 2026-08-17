"""Explicit execution door for historical LedgerFrames carrying ``legacy_atom`` IDs.

Ordinary registered mapper execution rejects storage identities that cannot be rebuilt
from source provenance.  Old exports may legitimately carry those identities, so import
code must opt into this conspicuously named module instead of weakening the live path.
This module owns no reader, cursor, gate, transaction, or store.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from .chain_mapper import (
    LedgerMapperContext,
    LedgerMapperRegistry,
    _run_registered_mapper,
)


def run_registered_legacy_import_mapper(
        mapper_id: str,
        version: int,
        payload,
        *,
        context: Optional[LedgerMapperContext] = None,
        rule: Optional[Mapping] = None,
        registry: Optional[LedgerMapperRegistry] = None):
    """Run a trusted mapper for an explicitly invoked historical-data import only."""
    return _run_registered_mapper(
        mapper_id, version, payload, context=context, rule=rule,
        registry=registry, allow_legacy_atom=True)
