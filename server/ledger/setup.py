"""The Ledger setup boundary: load one config, compile one snapshot, hand over registries.

🔴 DECLARATION IS ACTIVATION.
This module used to consult a separate `chains.ledger_v2_execution` selector that named a
`mode`, a `parity_status` and an `approval_ref` per source. All three are gone. A source
listed in `sources` runs; there is no second place to also say so.

Why that is safe rather than lax: "declared but not ready to run" was never held by the
selector anyway. A profile whose bindings are not all `approved` is refused by
`require_ready_bundle` at LOAD time, so a half-written source could never run regardless of
what the switch said. And the switch's other position was connected to nothing -- `legacy`
reached a config that was never read. Keeping it meant every new source had to be written
down twice, in a file the explorer did not even show, which is how one of them came to be
forgotten.

If "finished, but switch it off for now" is ever really needed, it belongs inside that
source's own declaration (`sources.<id>.enabled`), not in a separate file that drifts.

This module deliberately starts *after* the existing cursor has read a bounded physical
batch.  It has no reset, truncate, migration, or independent cursor.
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
class LedgerV2CutoverSetup:
    config_root: Path
    bundle: LedgerSetupBundle
    snapshot: LedgerSetupSnapshot
    preparers: SourcePreparerImplementationRegistry
    mappers: RoleMapperImplementationRegistry

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.snapshot.source_plans))

    def require_source(self, source_id: str) -> str:
        """Being declared IS being active; the only question left is whether it exists."""
        if source_id not in self.snapshot.source_plans:
            raise LedgerV2CutoverError(
                "unknown_source", f"sources.{source_id}",
                f"source {source_id!r} is not declared in {self.config_root.name}",
            )
        return source_id


def load_setup(
    root: str | Path = DEFAULT_ONTOLOGY_ROOT,
    *,
    verified_joins: Sequence[VerifiedJoinDescriptor] = (),
) -> LedgerV2CutoverSetup:
    """Load one file, enforce binding readiness, and compile one snapshot."""
    root_path = Path(root).resolve(strict=True)
    bundle = require_ready_bundle(load_setup_bundle(root_path))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), verified_joins)
    return LedgerV2CutoverSetup(
        config_root=root_path,
        bundle=bundle,
        snapshot=snapshot,
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
    _require_declared_source(setup, source_id)
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
    _require_declared_source(setup, source_id)
    return execute_cursor_batch(
        setup.snapshot, source_id, base_rows, cursor_value, join_reader,
        setup.preparers, setup.mappers, store,
        known_registrations=known_registrations,
    )


def dry_run_report(setup: LedgerV2CutoverSetup) -> Mapping[str, Any]:
    """Deterministic, write-free operator report for the active config."""
    return MappingProxyType({
        "config_root": setup.config_root.as_posix(),
        "setup_version": setup.snapshot.setup_version,
        "snapshot_sha256": setup.snapshot.snapshot_sha256,
        "readiness": setup.snapshot.readiness,
        "sources": tuple({
            "source_id": source_id,
            "relation": setup.snapshot.source_plans[source_id].relation,
        } for source_id in setup.source_ids),
        "destructive_actions": MappingProxyType({
            "database_reset": False,
            "cursor_reset": False,
            "legacy_removal": False,
        }),
    })


def _require_declared_source(setup: "LedgerV2CutoverSetup", source_id: str) -> str:
    """Kept as the ONE spelling of "may this source run", now that the answer is
    "is it declared". Callers (`backfill.run`, the preview/execute entries) ask through
    this rather than each testing membership, so a future gate lands in one place."""
    if not isinstance(setup, LedgerV2CutoverSetup):
        raise TypeError("setup must be LedgerV2CutoverSetup")
    return setup.require_source(source_id)


def main() -> int:
    setup = load_setup()
    print(json.dumps(
        dict(dry_run_report(setup)), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=lambda value: dict(value),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
