"""Filesystem working drafts for the Ledger v2 ontology explorer.

Draft files live outside the manifest root.  Saving or requesting review never writes the
active authoring files.  Activation is the only active write and is guarded by the draft's
base snapshot hash, revision, full Bundle compile, and an atomic file replacement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from threading import RLock
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

import config_backup
from .config_explorer import (
    ConfigExplorerError,
    ExplorerIndex,
    ExplorerNode,
    build_explorer_index,
    definition_diff,
)
from .cutover_v2 import trusted_cutover_implementations
from .setup_bundle import (
    LedgerSetupValidationError,
    require_ready_bundle,
    validate_bundle,
    validate_bundle_errors,
)
from .setup_registry import compile_setup_snapshot, snapshot_compile_errors


_DRAFT_ID = re.compile(r"^[0-9a-f]{32}$")
_EDITABLE_FILE = "ledger_config.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue(error: Exception) -> dict[str, str]:
    if isinstance(error, LedgerSetupValidationError):
        return error.to_mapping()
    if isinstance(error, ConfigExplorerError):
        return error.to_mapping()
    return {"code": "preview_compile_failed", "path": "draft.raw",
            "message": str(error)}


@dataclass(frozen=True)
class DraftPreview:
    valid: bool
    setup: Any | None
    index: ExplorerIndex | None
    errors: tuple[Mapping[str, str], ...]


def compile_draft_preview(active_setup: Any, node: ExplorerNode, raw: Mapping[str, Any]
                          ) -> DraftPreview:
    if node.config_file != _EDITABLE_FILE:
        return DraftPreview(False, None, None, ({
            "code": "unsupported_draft_target",
            "path": "draft.target_id",
            "message": (
                "catalog and physically verified declarations are read-only in the "
                "current explorer"),
        },))
    logical = active_setup.bundle.to_mapping()
    try:
        _set_path(logical, node.bundle_path, raw)
    except (KeyError, IndexError, TypeError) as exc:
        return DraftPreview(False, None, None, ({
            "code": "draft_target_missing",
            "path": "draft.target_id",
            "message": str(exc),
        },))

    issues = validate_bundle_errors(logical)
    if issues:
        return DraftPreview(False, None, None, tuple(issue.to_mapping() for issue in issues))
    try:
        bundle = require_ready_bundle(validate_bundle(logical))
        verified = tuple(active_setup.snapshot.verified_joins.values())
        compile_issues = snapshot_compile_errors(
            bundle, trusted_cutover_implementations(), verified)
        if compile_issues:
            return DraftPreview(
                False, None, None,
                tuple(issue.to_mapping() for issue in compile_issues),
            )
        snapshot = compile_setup_snapshot(
            bundle, trusted_cutover_implementations(), verified)
        preview_setup = SimpleNamespace(
            config_root=active_setup.config_root,
            bundle=bundle,
            snapshot=snapshot,
        )
        return DraftPreview(
            True, preview_setup, build_explorer_index(preview_setup), tuple())
    except (LedgerSetupValidationError, ConfigExplorerError, TypeError, ValueError) as exc:
        return DraftPreview(False, None, None, (_issue(exc),))


def _set_path(document: Any, path: Sequence[Any], value: Any) -> None:
    if not path:
        raise KeyError("empty target path")
    current = document
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False))


class OntologyDraftStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._lock = RLock()

    def create(self, active_setup: Any, index: ExplorerIndex, target_key: str
               ) -> dict[str, Any]:
        node = index.node(target_key)
        if node.config_file != _EDITABLE_FILE:
            raise ConfigExplorerError(
                "unsupported_draft_target", "target_key",
                "this declaration is read-only in the current explorer",
            )
        now = _now()
        record = {
            "draft_id": uuid4().hex,
            "target_key": node.key,
            "target_id": node.canonical_id,
            "target_kind": node.kind,
            "base_snapshot_hash": active_setup.snapshot.snapshot_sha256,
            "revision": 0,
            "lifecycle_status": "editing",
            "raw": node.raw,
            "preview_snapshot_hash": None,
            "preview_valid": False,
            "validation_errors": [],
            "review_revision": None,
            "activated_snapshot_hash": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._write_record(record)
        return self.public(record)

    def get(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            return self._read_record(draft_id)

    def save(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        raw_text: str,
        active_setup: Any,
        active_index: ExplorerIndex,
    ) -> tuple[dict[str, Any], DraftPreview]:
        try:
            raw = json.loads(raw_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ConfigExplorerError(
                "invalid_json", "raw", f"invalid JSON: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise ConfigExplorerError(
                "invalid_json_type", "raw", "definition must be a JSON object")

        with self._lock:
            record = self._read_record(draft_id)
            self._require_revision(record, expected_revision)
            if record["lifecycle_status"] == "review_requested":
                raise ConfigExplorerError(
                    "review_revision_locked", "revision",
                    "a review-requested revision is immutable; create a new revision",
                )
            if record["lifecycle_status"] == "activated":
                raise ConfigExplorerError(
                    "draft_already_activated", "draft_id", "draft is already active")
            if record["base_snapshot_hash"] != active_setup.snapshot.snapshot_sha256:
                record["lifecycle_status"] = "stale"
                record["updated_at"] = _now()
                self._write_record(record)
                raise ConfigExplorerError(
                    "stale_draft", "base_snapshot_hash",
                    "active snapshot changed; rebase before saving",
                )
            node = active_index.node(record["target_key"])
            preview = compile_draft_preview(active_setup, node, raw)
            record["revision"] += 1
            record["raw"] = json.loads(json.dumps(raw, ensure_ascii=False))
            record["preview_valid"] = preview.valid
            record["preview_snapshot_hash"] = (
                preview.setup.snapshot.snapshot_sha256 if preview.valid else None)
            record["validation_errors"] = [dict(item) for item in preview.errors]
            record["lifecycle_status"] = "saved" if preview.valid else "invalid"
            record["review_revision"] = None
            record["updated_at"] = _now()
            self._write_record(record)
            return self.public(record), preview

    def request_review(self, draft_id: str, *, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(draft_id)
            self._require_revision(record, expected_revision)
            if not record["preview_valid"]:
                raise ConfigExplorerError(
                    "draft_preview_invalid", "preview_valid",
                    "only a valid compiled preview can request review",
                )
            if record["lifecycle_status"] not in {"saved", "review_requested"}:
                raise ConfigExplorerError(
                    "invalid_draft_state", "lifecycle_status",
                    "draft must be saved before requesting review",
                )
            record["lifecycle_status"] = "review_requested"
            record["review_revision"] = record["revision"]
            record["updated_at"] = _now()
            self._write_record(record)
            return self.public(record)

    def discard(self, draft_id: str, *, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(draft_id)
            self._require_revision(record, expected_revision)
            if record["lifecycle_status"] == "activated":
                raise ConfigExplorerError(
                    "draft_already_activated", "draft_id",
                    "an activated draft cannot be discarded",
                )
            path = self._record_path(draft_id)
            path.unlink()
            return {"draft_id": draft_id, "discarded": True}

    def activate(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        active_setup: Any,
        active_index: ExplorerIndex,
        reload_callback: Callable[[], None],
        refreshed_setup: Callable[[], Any],
    ) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(draft_id)
            self._require_revision(record, expected_revision)
            if (record["lifecycle_status"] != "review_requested"
                    or record["review_revision"] != record["revision"]):
                raise ConfigExplorerError(
                    "review_required", "lifecycle_status",
                    "the exact revision must be review requested before activation",
                )
            if record["base_snapshot_hash"] != active_setup.snapshot.snapshot_sha256:
                record["lifecycle_status"] = "stale"
                record["updated_at"] = _now()
                self._write_record(record)
                raise ConfigExplorerError(
                    "stale_draft", "base_snapshot_hash",
                    "active snapshot changed; activation compare-and-swap refused",
                )
            node = active_index.node(record["target_key"])
            preview = compile_draft_preview(active_setup, node, record["raw"])
            if not preview.valid or preview.setup is None:
                record["lifecycle_status"] = "invalid"
                record["preview_valid"] = False
                record["validation_errors"] = [dict(item) for item in preview.errors]
                self._write_record(record)
                raise ConfigExplorerError(
                    "draft_preview_invalid", "preview_valid",
                    "draft no longer compiles and cannot be activated",
                )
            if preview.setup.snapshot.snapshot_sha256 != record["preview_snapshot_hash"]:
                raise ConfigExplorerError(
                    "preview_hash_mismatch", "preview_snapshot_hash",
                    "stored preview hash does not match a fresh compile",
                )

            config_path = Path(active_setup.config_root) / node.config_file
            backup = self._activate_file(config_path, node.bundle_path, record["raw"])
            try:
                reload_callback()
                new_setup = refreshed_setup()
                actual_hash = new_setup.snapshot.snapshot_sha256
                if actual_hash != record["preview_snapshot_hash"]:
                    raise ConfigExplorerError(
                        "activation_hash_mismatch", "active_snapshot_hash",
                        "reloaded active snapshot does not match the reviewed preview",
                    )
            except Exception:
                shutil.copy2(backup, config_path)
                reload_callback()
                raise

            record["lifecycle_status"] = "activated"
            record["activated_snapshot_hash"] = actual_hash
            record["updated_at"] = _now()
            self._write_record(record)
            return {
                "draft": self.public(record),
                "active_snapshot_hash": actual_hash,
                "runtime_convergence": {
                    "status": "confirmed",
                    "required_consumers": ["ontology-explorer-api"],
                    "confirmed_consumers": ["ontology-explorer-api"],
                    "note": (
                        "persistent Ledger v2 snapshot consumer confirmed; backfill "
                        "consumers compile the manifest at each run boundary"),
                },
                "backup": str(backup),
            }

    def preview(
        self,
        record: Mapping[str, Any],
        active_setup: Any,
        active_index: ExplorerIndex,
    ) -> DraftPreview:
        if record["base_snapshot_hash"] != active_setup.snapshot.snapshot_sha256:
            return DraftPreview(False, None, None, ({
                "code": "stale_draft",
                "path": "base_snapshot_hash",
                "message": "active snapshot changed; draft preview is stale",
            },))
        node = active_index.node(record["target_key"])
        return compile_draft_preview(active_setup, node, record["raw"])

    @staticmethod
    def public(record: Mapping[str, Any]) -> dict[str, Any]:
        return {key: record.get(key) for key in (
            "draft_id", "target_key", "target_id", "target_kind",
            "base_snapshot_hash", "revision", "lifecycle_status", "raw",
            "preview_snapshot_hash", "preview_valid", "validation_errors",
            "review_revision", "activated_snapshot_hash", "created_at", "updated_at",
        )}

    def _activate_file(self, path: Path, bundle_path: Sequence[Any], value: Any) -> Path:
        lock_path = path.with_name(f".{path.name}.ontology-explorer.lock")
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ConfigExplorerError(
                "activation_locked", "active_config",
                "another ontology activation is in progress",
            ) from exc
        try:
            os.write(lock_fd, str(os.getpid()).encode("ascii"))
            os.close(lock_fd)
            with path.open("r", encoding="utf-8") as handle:
                document = json.load(handle)
            _set_path(document, bundle_path, value)
            backup_dir = Path(config_backup.backup_dir_for(str(path)))
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / (
                f"{path.stem}.ontology_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                f"{path.suffix}.bak")
            shutil.copy2(path, backup)
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            return backup
        finally:
            try:
                os.close(lock_fd)
            except OSError:
                pass
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def _record_path(self, draft_id: str) -> Path:
        if not _DRAFT_ID.fullmatch(str(draft_id)):
            raise ConfigExplorerError(
                "invalid_draft_id", "draft_id", "draft id is not valid")
        return self.root / f"{draft_id}.json"

    def _read_record(self, draft_id: str) -> dict[str, Any]:
        path = self._record_path(draft_id)
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError as exc:
            raise ConfigExplorerError(
                "unknown_draft", "draft_id", f"draft {draft_id!r} does not exist",
            ) from exc
        if not isinstance(value, dict):
            raise ConfigExplorerError(
                "corrupt_draft", "draft_id", "draft record is not an object")
        return value

    def _write_record(self, record: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._record_path(str(record["draft_id"]))
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(record, handle, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _require_revision(record: Mapping[str, Any], expected: int) -> None:
        if not isinstance(expected, int) or isinstance(expected, bool):
            raise ConfigExplorerError(
                "invalid_revision", "expected_revision", "must be an integer")
        if record.get("revision") != expected:
            raise ConfigExplorerError(
                "stale_revision", "expected_revision",
                f"expected revision {expected}, current is {record.get('revision')}",
            )
