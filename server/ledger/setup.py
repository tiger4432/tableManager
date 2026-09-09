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
import logging
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Any

import pandas as pd

from verified_join_contract import VerifiedJoinDescriptor
from .roleframe import RoleMapperImplementationRegistry
from .runtime_v2 import (
    CursorBatchExecutionResult,
    CursorBatchPreview,
    execute_cursor_batch,
    execute_scoped_batch,
    preview_cursor_batch,
)
from .implementations import (
    role_mapper_registry,
    source_preparer_registry,
    trusted_implementations,
)
from .setup_bundle import (
    CONFIG_FILENAME,
    PHYSICAL_CATALOG_FILENAME,
    LedgerSetupBundle,
    LedgerSetupValidationError,
    bundle_readiness_errors,
    load_physical_catalog,
    load_setup_bundle,
    require_ready_bundle,
    setup_bundle_errors,
    validate_bundle,
)
from .setup_registry import (
    LedgerSetupSnapshot, compile_setup_snapshot, snapshot_compile_errors)
from .source_preparation import (
    SourcePreparerImplementationRegistry,
    VerifiedJoinBatchReader,
)


DEFAULT_ONTOLOGY_ROOT = Path(__file__).parents[1] / "config" / "ontology"


def physical_catalog_path() -> Path:
    """Where `table_config.json` lives for THIS data root.

    Resolved through `paths`, like every other reader of that file, so an isolated stack
    (`ASSY_DATA_ROOT`) reads its own catalog instead of the operator's. `setup_bundle`
    deliberately cannot answer this -- it imports no runtime -- so the deployment question
    is answered here, once.
    """
    import paths

    return Path(paths.config_path(PHYSICAL_CATALOG_FILENAME))


def live_physical_catalog() -> Mapping[str, Any]:
    """The physical relation shape this deployment's `table_config.json` declares."""
    return load_physical_catalog(physical_catalog_path())


class LedgerSetupError(ValueError):
    """Stable Stage 7 config or selection refusal."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class LedgerSetup:
    config_root: Path
    bundle: LedgerSetupBundle
    snapshot: LedgerSetupSnapshot
    preparers: SourcePreparerImplementationRegistry
    mappers: RoleMapperImplementationRegistry
    #: The physical relation shape from `table_config.json` that `bundle` was validated
    #: against. Carried rather than re-read so that everything downstream -- the explorer
    #: most of all -- describes the SAME catalog the validation used. Re-reading it later
    #: would let a screen disagree with the refusal an operator just saw.
    catalog: Mapping[str, Any] = MappingProxyType({})

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.snapshot.source_plans))

    def require_source(self, source_id: str) -> str:
        """Being declared IS being active; the only question left is whether it exists."""
        if source_id not in self.snapshot.source_plans:
            raise LedgerSetupError(
                "unknown_source", f"sources.{source_id}",
                f"source {source_id!r} is not declared in {self.config_root.name}",
            )
        return source_id


logger = logging.getLogger(__name__)


def _dead_time_cells(sources):
    """`bind.occurred_at` paths that name a column the compiler will not read.

    🔴 판정 179 ⓑ — NAMED, NOT REFUSED. `roleframe` fills a TIME role from the instant the
    preparation boundary already interpreted and IGNORES the binding's column (ruled
    2026-08-23: re-reading the cell would disagree with the event id minted from that same
    value). Where the source also declares a `basis`, the declaration says out loud that its
    time comes from somewhere else, and the cell beside it is dead.

    ⚠️ REFUSING IT WOULD MOVE FINGERPRINTS. Two shipped sources carry such a cell, so a
    refusal means editing their declarations, and editing a declaration re-translates it --
    which is the one thing the freeze round promised not to do. So the loader SAYS it, and
    the removal waits for the retirement round (Ⓐ, with S-79).
    """
    # ⚠️ TAKES THE `sources` SECTION, NOT THE BUNDLE. `load_setup` holds a
    # `LedgerSetupBundle`, which is not a mapping -- a first draft called `.get` on it and
    # 34 tests said so before it landed. Taking the section makes the raw-document caller
    # and the loaded-bundle caller pass the SAME thing.
    dead = []
    for source_id in sorted(sources or {}, key=str):
        source = sources[source_id]
        if not isinstance(source, Mapping):
            continue
        read = source.get("read")
        occurred = read.get("occurred_at") if isinstance(read, Mapping) else None
        basis = occurred.get("basis") if isinstance(occurred, Mapping) else None
        if not basis:
            continue
        profile = source.get("bind")
        mappings = profile.get("mappings") if isinstance(profile, Mapping) else None
        for sentence in sorted(mappings or {}, key=str):
            mapping = mappings[sentence]
            bind = mapping.get("bind") if isinstance(mapping, Mapping) else None
            slot = bind.get("occurred_at") if isinstance(bind, Mapping) else None
            column = slot.get("column") if isinstance(slot, Mapping) else None
            if column:
                dead.append(
                    f"sources.{source_id}.bind.mappings.{sentence}.bind.occurred_at"
                    f"={column} (basis {basis})")
    return dead


def load_setup(
    root: str | Path = DEFAULT_ONTOLOGY_ROOT,
    *,
    verified_joins: Sequence[VerifiedJoinDescriptor] = (),
    catalog: Mapping[str, Any] | None = None,
) -> LedgerSetup:
    """Load one file, enforce binding readiness, and compile one snapshot.

    `catalog` is the physical relation shape; omitting it reads the live
    `table_config.json`, which is what production does and the only thing production
    should do. It is resolved ONCE here and carried on the result so no later reader
    re-reads the file and gets a different answer.
    """
    root_path = Path(root).resolve(strict=True)
    resolved_catalog = (
        dict(live_physical_catalog()) if catalog is None else dict(catalog))
    bundle = require_ready_bundle(
        load_setup_bundle(root_path, catalog=resolved_catalog))
    # 🔴 ONE LINE, EVERY CELL NAMED (판정 179 ⓑ). A count would be the silence this
    # says nothing about; a warning per load would fire every backfill on a condition that
    # is EXPECTED, and a warning that always fires is one nobody reads. So: info, once,
    # with the paths.
    dead = _dead_time_cells(bundle.section("sources"))
    if dead:
        logger.info("[Ledger] dead cell: %s ignored -- the time role is filled from the "
                    "source's declared basis", "; ".join(dead))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), verified_joins,
        catalog=resolved_catalog)
    return LedgerSetup(
        config_root=root_path,
        bundle=bundle,
        snapshot=snapshot,
        preparers=source_preparer_registry(),
        mappers=role_mapper_registry(),
        catalog=MappingProxyType(resolved_catalog),
    )


def setup_from_document(
    document: Mapping[str, Any],
    *,
    config_root: str | Path = DEFAULT_ONTOLOGY_ROOT,
    verified_joins: Sequence[VerifiedJoinDescriptor] = (),
    catalog: Mapping[str, Any] | None = None,
) -> LedgerSetup:
    """`load_setup`, but from a document already in hand instead of from the file.

    🔴 THE CALLER OWNS THE DOCUMENT, AND NOBODY WRITES IT BACK. The explorer resolves a
    half-written setup by dropping what cannot load from an IN-MEMORY copy and compiling
    what remains; that reduced document must never reach the disk, so this takes a mapping
    and returns a setup, and knows nothing about files.

    `load_setup` is unchanged and is still what production calls.
    """
    resolved_catalog = (
        dict(live_physical_catalog()) if catalog is None else dict(catalog))
    bundle = require_ready_bundle(validate_bundle(document, catalog=resolved_catalog))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), verified_joins, catalog=resolved_catalog)
    return LedgerSetup(
        config_root=Path(config_root),
        bundle=bundle,
        snapshot=snapshot,
        preparers=source_preparer_registry(),
        mappers=role_mapper_registry(),
        catalog=MappingProxyType(resolved_catalog),
    )


def preview_selected_cursor_batch(
    setup: LedgerSetup,
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
    setup: LedgerSetup,
    source_id: str,
    base_rows: pd.DataFrame,
    cursor_value: Mapping[str, Any],
    join_reader: VerifiedJoinBatchReader,
    store: Any,
    *,
    known_registrations: Any = None,
    retranslate_approved: bool = False,
) -> CursorBatchExecutionResult:
    """Use the existing Stage 6 gate/store transaction for an approved v2 source."""
    _require_declared_source(setup, source_id)
    return execute_cursor_batch(
        setup.snapshot, source_id, base_rows, cursor_value, join_reader,
        setup.preparers, setup.mappers, store,
        known_registrations=known_registrations,
        retranslate_approved=retranslate_approved,
    )


def execute_selected_scoped_batch(
    setup: LedgerSetup,
    source_id: str,
    base_rows: pd.DataFrame,
    scope: Any,
    join_reader: VerifiedJoinBatchReader,
    store: Any,
    *,
    known_registrations: Any = None,
    withdraw_refs: Any = None,
) -> CursorBatchExecutionResult:
    """The same gate and store transaction for a NAMED PART of an approved v2 source.

    Takes a scope where its neighbour takes a cursor, which is the whole difference between
    the two: one says where the forward scan reached, the other says which rows are being
    redone, and only the first is written down.
    """
    _require_declared_source(setup, source_id)
    return execute_scoped_batch(
        setup.snapshot, source_id, base_rows, scope, join_reader,
        setup.preparers, setup.mappers, store,
        known_registrations=known_registrations,
        withdraw_refs=withdraw_refs,
    )


def dry_run_report(setup: LedgerSetup) -> Mapping[str, Any]:
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


def _require_declared_source(setup: "LedgerSetup", source_id: str) -> str:
    """Kept as the ONE spelling of "may this source run", now that the answer is
    "is it declared". Callers (`backfill.run`, the preview/execute entries) ask through
    this rather than each testing membership, so a future gate lands in one place."""
    if not isinstance(setup, LedgerSetup):
        raise TypeError("setup must be LedgerSetup")
    return setup.require_source(source_id)


def _resolve_cli_root(value: str | None) -> Path:
    """Turn a `--root` argument into a config root, refusing by name rather than by
    traceback.

    🔴 THE OPERATOR IS POINTING THIS AT A DRAFT, so the two ways of getting the argument
    wrong are both likely and neither should arrive as a stack trace: a path that is not
    there yet, and the file itself rather than the directory holding it. The second is
    the one worth naming explicitly -- `--root .../ledger_config.json` is the reading the
    word "root" does not obviously exclude.
    """
    if value is None:
        return DEFAULT_ONTOLOGY_ROOT
    candidate = Path(value).expanduser()
    if not candidate.exists():
        raise LedgerSetupError(
            "config_root_absent", "--root", f"no such path: {candidate}")
    if candidate.is_file():
        hint = (" — point --root at the directory that CONTAINS it, not at the file"
                if candidate.name == CONFIG_FILENAME else "")
        raise LedgerSetupError(
            "config_root_not_a_directory", "--root",
            f"{candidate} is a file{hint}")
    if not (candidate / CONFIG_FILENAME).is_file():
        raise LedgerSetupError(
            "config_root_has_no_config", "--root",
            f"{candidate} holds no {CONFIG_FILENAME}")
    return candidate


def main(argv: Sequence[str] | None = None) -> int:
    """Verify a config root and print the write-free report. READ ONLY.

    `--root` exists because the setup guide tells an operator to verify BEFORE editing,
    and without it the only way to verify a draft was to overwrite the live file first —
    exactly what the guide forbids. Omitting it keeps the previous behaviour: the live
    `DEFAULT_ONTOLOGY_ROOT`. The report already carries `config_root`, so the answer says
    which file it is about and a draft run cannot be mistaken for a live one.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ledger.setup",
        description="Load and compile one ledger config root, then print its "
                    "write-free readiness report. Nothing is written or migrated.")
    parser.add_argument(
        "--root", default=None, metavar="PATH",
        help=f"directory holding {CONFIG_FILENAME}. Default: the live config root "
             f"({DEFAULT_ONTOLOGY_ROOT.as_posix()}). Use this to verify a DRAFT "
             f"without touching the live file.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Only the --root ARGUMENT's own refusals are caught here, and only when --root was
    # given, so the no-argument path is byte-for-byte what it was. A bad config still
    # raises: that is the report, and swallowing it would turn a failed verification into
    # a tidy line an operator could mistake for a pass.
    try:
        root = _resolve_cli_root(args.root)
    except LedgerSetupError as refusal:
        print(f"{parser.prog}: {refusal}", file=sys.stderr)
        return 2

    try:
        setup = load_setup(root)
    except LedgerSetupValidationError as refusal:
        # 🔴 AUTHORING REPORTS EVERY PROBLEM; THE RUNTIME STILL STOPS AT THE FIRST.
        # `load_setup` above is the runtime path and is unchanged -- it raised, and a
        # source about to write atoms should stop exactly there. This command is the
        # AUTHORING path, and the difference was measured 2026-08-19: an author writing a
        # second source by hand spent five save-and-run cycles discovering five problems
        # that were all present in the first save. The first refusal is not more true than
        # the other four; it is only alphabetically first.
        issues = _authoring_issues(root, refusal)
        for issue in issues:
            print(f"{issue.code}	{issue.path}	{issue.message}", file=sys.stderr)
        print(f"{parser.prog}: {len(issues)} problem(s) in {root}", file=sys.stderr)
        return 1

    print(json.dumps(
        dict(dry_run_report(setup)), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=lambda value: dict(value),
    ))
    return 0


def _authoring_issues(
    root: Path, fallback: LedgerSetupValidationError,
) -> tuple[LedgerSetupValidationError, ...]:
    """The whole list, in the three stages a config is judged in.

    Staged rather than concatenated because each stage needs the previous one to have
    passed: readiness reads a validated bundle, and the compiler reads a ready one.
    Reporting a later stage's consequences beside an earlier stage's causes would bury the
    causes.  WITHIN a stage every problem is reported -- that is the change.

    `fallback` is the refusal the loader already raised.  If none of the three stages can
    reproduce it the loader is still right and the operator still gets an answer; a report
    that said "0 problems" about a config that just failed to load would be worse than the
    single message it replaced.
    """
    catalog = dict(live_physical_catalog())
    issues = setup_bundle_errors(root, catalog=catalog)
    if not issues:
        bundle = load_setup_bundle(root, catalog=catalog)
        issues = bundle_readiness_errors(bundle)
    if not issues:
        issues = snapshot_compile_errors(
            bundle, trusted_implementations(), (), catalog=catalog)
    return issues or (fallback,)


if __name__ == "__main__":
    raise SystemExit(main())
