"""Stage 7 manifest-only Ledger v2 cutover boundary.

This module deliberately starts *after* the existing cursor has read a bounded physical
batch.  It selects an approved v2 source, then delegates to the Stage 6 preview/execute
path.  It has no reset, truncate, migration, legacy deletion, or independent cursor.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pandas as pd

from verified_join_contract import VerifiedJoinDescriptor
from .roleframe import RoleMapperImplementationRegistry
from .runtime_v2 import (
    CursorBatchExecutionResult,
    CursorBatchPreview,
    execute_cursor_batch,
    preview_cursor_batch,
)
from .implementations import (
    role_mapper_registry,
    source_preparer_registry,
    trusted_implementations,
)
from .setup_bundle import LedgerSetupBundle, load_setup_bundle, require_ready_bundle
from .setup_registry import LedgerSetupSnapshot, compile_setup_snapshot
from .source_preparation import (
    SourcePreparerImplementationRegistry,
    VerifiedJoinBatchReader,
)


DEFAULT_ONTOLOGY_ROOT = Path(__file__).parents[1] / "config" / "ontology"
SELECTOR_DECLARATION = "ledger_v2_execution"
_MODES = frozenset({"legacy", "v2"})
_PARITY_STATUSES = frozenset({"pending", "approved", "rejected"})


class LedgerV2CutoverError(ValueError):
    """Stable Stage 7 config or selection refusal."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class SourceCutoverSelection:
    source_id: str
    mode: str
    parity_status: str
    approval_ref: str


@dataclass(frozen=True)
class LedgerV2CutoverSetup:
    config_root: Path
    bundle: LedgerSetupBundle
    snapshot: LedgerSetupSnapshot
    selections: Mapping[str, SourceCutoverSelection]
    preparers: SourcePreparerImplementationRegistry
    mappers: RoleMapperImplementationRegistry

    def selection(self, source_id: str) -> SourceCutoverSelection:
        try:
            return self.selections[source_id]
        except KeyError as exc:
            raise LedgerV2CutoverError(
                "unknown_cutover_source", f"sources.{source_id}",
                f"source {source_id!r} is not selected by the ontology manifest",
            ) from exc


def load_cutover_setup(
    root: str | Path = DEFAULT_ONTOLOGY_ROOT,
    *,
    verified_joins: Sequence[VerifiedJoinDescriptor] = (),
) -> LedgerV2CutoverSetup:
    """Load one manifest, enforce readiness/selector proof, and compile one snapshot."""
    root_path = Path(root).resolve(strict=True)
    bundle = require_ready_bundle(load_setup_bundle(root_path))
    selections = _validate_selector(bundle)
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), verified_joins)
    return LedgerV2CutoverSetup(
        config_root=root_path,
        bundle=bundle,
        snapshot=snapshot,
        selections=MappingProxyType(selections),
        preparers=source_preparer_registry(),
        mappers=role_mapper_registry(),
    )


def preview_selected_cursor_batch(
    setup: LedgerV2CutoverSetup,
    source_id: str,
    base_rows: pd.DataFrame,
    cursor_value: Mapping[str, Any],
    join_reader: VerifiedJoinBatchReader,
    *,
    known_registrations: Any = None,
) -> CursorBatchPreview:
    _require_v2_selection(setup, source_id)
    return preview_cursor_batch(
        setup.snapshot, source_id, base_rows, cursor_value, join_reader,
        setup.preparers, setup.mappers,
        known_registrations=known_registrations,
    )


def execute_selected_cursor_batch(
    setup: LedgerV2CutoverSetup,
    source_id: str,
    base_rows: pd.DataFrame,
    cursor_value: Mapping[str, Any],
    join_reader: VerifiedJoinBatchReader,
    store: Any,
    *,
    known_registrations: Any = None,
) -> CursorBatchExecutionResult:
    """Use the existing Stage 6 gate/store transaction for an approved v2 source."""
    _require_v2_selection(setup, source_id)
    return execute_cursor_batch(
        setup.snapshot, source_id, base_rows, cursor_value, join_reader,
        setup.preparers, setup.mappers, store,
        known_registrations=known_registrations,
    )


def dry_run_report(setup: LedgerV2CutoverSetup) -> Mapping[str, Any]:
    """Deterministic, write-free operator report for the active manifest."""
    return MappingProxyType({
        "config_root": setup.config_root.as_posix(),
        "setup_version": setup.snapshot.setup_version,
        "snapshot_sha256": setup.snapshot.snapshot_sha256,
        "readiness": setup.snapshot.readiness,
        "sources": tuple({
            "source_id": source_id,
            "mode": setup.selections[source_id].mode,
            "parity_status": setup.selections[source_id].parity_status,
            "approval_ref": setup.selections[source_id].approval_ref,
        } for source_id in sorted(setup.selections)),
        "destructive_actions": MappingProxyType({
            "database_reset": False,
            "cursor_reset": False,
            "legacy_removal": False,
        }),
    })


def _validate_selector(bundle: LedgerSetupBundle) -> dict[str, SourceCutoverSelection]:
    chains = bundle.section("chains")
    path = f"bundle.chains.{SELECTOR_DECLARATION}"
    declaration = chains.get(SELECTOR_DECLARATION)
    if not isinstance(declaration, Mapping) or set(declaration) != {"sources"}:
        raise LedgerV2CutoverError(
            "invalid_execution_selector", path,
            "selector must be an object containing only sources",
        )
    raw_sources = declaration.get("sources")
    if not isinstance(raw_sources, Mapping):
        raise LedgerV2CutoverError(
            "invalid_execution_selector", f"{path}.sources",
            "sources must be an object",
        )
    declared_sources = set(bundle.section("sources"))
    selected_sources = set(raw_sources)
    missing = sorted(declared_sources - selected_sources)
    unknown = sorted(selected_sources - declared_sources)
    if missing:
        raise LedgerV2CutoverError(
            "missing_execution_selector", f"{path}.sources.{missing[0]}",
            f"source {missing[0]!r} requires an explicit execution selector",
        )
    if unknown:
        raise LedgerV2CutoverError(
            "unknown_execution_source", f"{path}.sources.{unknown[0]}",
            f"selector names unknown source {unknown[0]!r}",
        )
    out: dict[str, SourceCutoverSelection] = {}
    for source_id in sorted(raw_sources):
        item_path = f"{path}.sources.{source_id}"
        item = raw_sources[source_id]
        required = {"mode", "parity_status", "approval_ref"}
        if not isinstance(item, Mapping) or set(item) != required:
            raise LedgerV2CutoverError(
                "invalid_execution_selector", item_path,
                "source selector requires exactly mode, parity_status, approval_ref",
            )
        mode = item.get("mode")
        parity = item.get("parity_status")
        approval_ref = item.get("approval_ref")
        if mode not in _MODES:
            raise LedgerV2CutoverError(
                "invalid_execution_mode", f"{item_path}.mode",
                f"mode must be one of {sorted(_MODES)}",
            )
        if parity not in _PARITY_STATUSES:
            raise LedgerV2CutoverError(
                "invalid_parity_status", f"{item_path}.parity_status",
                f"parity_status must be one of {sorted(_PARITY_STATUSES)}",
            )
        if (not isinstance(approval_ref, str) or not approval_ref.strip()
                or approval_ref != approval_ref.strip()):
            raise LedgerV2CutoverError(
                "invalid_approval_ref", f"{item_path}.approval_ref",
                "approval_ref must be a trimmed non-blank string",
            )
        if mode == "v2" and parity != "approved":
            raise LedgerV2CutoverError(
                "cutover_not_approved", f"{item_path}.parity_status",
                "v2 execution requires approved source parity",
            )
        out[source_id] = SourceCutoverSelection(
            source_id=source_id, mode=mode,
            parity_status=parity, approval_ref=approval_ref)
    return out


def _require_v2_selection(
    setup: LedgerV2CutoverSetup,
    source_id: str,
) -> SourceCutoverSelection:
    if not isinstance(setup, LedgerV2CutoverSetup):
        raise TypeError("setup must be LedgerV2CutoverSetup")
    selection = setup.selection(source_id)
    if selection.mode != "v2":
        raise LedgerV2CutoverError(
            "legacy_source_selected", f"sources.{source_id}.mode",
            f"source {source_id!r} remains on the legacy execution path",
        )
    if selection.parity_status != "approved":
        raise LedgerV2CutoverError(
            "cutover_not_approved", f"sources.{source_id}.parity_status",
            "v2 execution requires approved source parity",
        )
    return selection


def main() -> int:
    setup = load_cutover_setup()
    print(json.dumps(
        dict(dry_run_report(setup)), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=lambda value: dict(value),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
