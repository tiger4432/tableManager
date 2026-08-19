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
    authorable_bundle_path,
    build_explorer_index,
    definition_diff,
    document_hash,
    node_key,
)
from .implementations import trusted_implementations
from .setup_bundle import (
    LedgerSetupValidationError,
    require_ready_bundle,
    validate_bundle,
    validate_bundle_errors,
)
from .setup_registry import compile_setup_snapshot, snapshot_compile_errors


_DRAFT_ID = re.compile(r"^[0-9a-f]{32}$")
_EDITABLE_FILE = "ledger_config.json"

_UNRESOLVED_CODES = {
    "unknown_entity_type", "unknown_pack", "unknown_claim", "unknown_source",
    "unknown_preparer", "unknown_mapper", "unknown_table", "unknown_virtual_join",
}
_WRONG_VERSION_CODES = {
    "unsupported_pack_version", "unsupported_profile_version",
    "unsupported_preparer_version", "unsupported_mapper_version",
}
_WRONG_KIND_CODES = {"invalid_entity_ref", "invalid_reference_kind"}
_SIGNATURE_CODES = {
    "missing_required_payload", "unknown_payload_field", "invalid_binding",
    "missing_required_role", "unknown_role", "invalid_emission",
    "invalid_symbolic_constant", "predicate_signature_mismatch",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue(error: Exception) -> dict[str, str]:
    if isinstance(error, LedgerSetupValidationError):
        return error.to_mapping()
    if isinstance(error, ConfigExplorerError):
        return error.to_mapping()
    return {"code": "preview_compile_failed", "path": "draft.raw",
            "message": str(error)}


def _decorate_issue(value: Mapping[str, Any]) -> dict[str, Any]:
    issue = dict(value)
    code = str(issue.get("code", ""))
    if code in _UNRESOLVED_CODES:
        issue["reference_status"] = "unresolved"
    elif code in _WRONG_VERSION_CODES:
        issue["reference_status"] = "wrong_version"
    elif code in _WRONG_KIND_CODES:
        issue["reference_status"] = "wrong_kind"
    elif code in _SIGNATURE_CODES:
        issue["reference_status"] = "signature_mismatch"
    issue["json_pointer"] = _error_pointer(str(issue.get("path", "")))
    return issue


def _error_pointer(path: str) -> str:
    if path.startswith("/"):
        return path
    parts: list[str] = []
    for name, index in re.findall(r"(?:^|\.)([^.\[\]]+)|\[([0-9]+)\]", path):
        value = name or index
        if value == "bundle" and not parts:
            continue
        parts.append(str(value).replace("~", "~0").replace("/", "~1"))
    return "/" + "/".join(parts) if parts else "/"


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

    # 🔴 THE DRAFT IS JUDGED AGAINST THE CATALOG THE ACTIVE SETUP WAS JUDGED AGAINST.
    # Re-reading `table_config.json` here instead would let a preview go green (or red)
    # for a physical reason the operator's live config never saw -- and the preview's
    # whole job is to answer "what happens if I activate THIS".
    catalog = active_setup.catalog
    issues = validate_bundle_errors(logical, catalog=catalog)
    if issues:
        return DraftPreview(
            False, None, None,
            tuple(_decorate_issue(issue.to_mapping()) for issue in issues),
        )
    try:
        bundle = require_ready_bundle(validate_bundle(logical, catalog=catalog))
        verified = tuple(active_setup.snapshot.verified_joins.values())
        compile_issues = snapshot_compile_errors(
            bundle, trusted_implementations(), verified, catalog=catalog)
        if compile_issues:
            return DraftPreview(
                False, None, None,
                tuple(_decorate_issue(issue.to_mapping()) for issue in compile_issues),
            )
        snapshot = compile_setup_snapshot(
            bundle, trusted_implementations(), verified, catalog=catalog)
        preview_setup = SimpleNamespace(
            config_root=active_setup.config_root,
            bundle=bundle,
            snapshot=snapshot,
            catalog=catalog,
        )
        return DraftPreview(
            True, preview_setup, build_explorer_index(preview_setup), tuple())
    except (LedgerSetupValidationError, ConfigExplorerError, TypeError, ValueError) as exc:
        return DraftPreview(False, None, None, (_decorate_issue(_issue(exc)),))


class _Remove:
    """Sentinel: this operation removes the leaf rather than writing one.

    A distinct object rather than `None`, because `None` is a legal JSON value and a
    declaration whose body is `null` must stay distinguishable from one that is gone.
    """

    __slots__ = ()

    def __repr__(self) -> str:                      # pragma: no cover - diagnostics only
        return "REMOVE"


REMOVE = _Remove()


def draft_target(record: Mapping[str, Any], index: ExplorerIndex) -> Any:
    """Where this draft writes -- for a declaration that exists, and for one that does not.

    🔴 A CREATE DRAFT HAS NO NODE TO ASK, AND THAT IS THE WHOLE REASON CREATING WAS
    IMPOSSIBLE. `index.node(key)` refuses an id the snapshot has never seen, so every path
    into the draft machinery was gated on the declaration already existing: the screen could
    edit and it could not author. The owner hit this from the other side -- they wrote a new
    source by hand in a text editor for two hours.

    Only two fields of the target are ever used downstream (`compile_draft_preview` and
    `activate` read `config_file` and `bundle_path`), so a create draft carries its own
    path, stamped at creation by `authorable_bundle_path` -- the same function the explorer
    index uses, so the two cannot disagree about where a `mapper` lives.

    Records written before this existed have no stored path and fall back to the index,
    which is exactly right for them: they always target something that exists.
    """
    key = str(record.get("target_key"))
    stored = record.get("target_bundle_path")
    existing = index.nodes.get(key)
    if existing is not None:
        return existing
    if not stored:
        return index.node(key)          # refuses by name, as before
    return SimpleNamespace(
        key=key,
        canonical_id=record.get("target_id"),
        kind=record.get("target_kind"),
        config_file=_EDITABLE_FILE,
        bundle_path=tuple(stored),
        definition_hash=None,
        raw=record.get("raw"),
    )


def _set_path(document: Any, path: Sequence[Any], value: Any) -> None:
    if not path:
        raise KeyError("empty target path")
    current = document
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False))


def _delete_path(document: Any, path: Sequence[Any]) -> None:
    """Remove the leaf at `path`. Absent is an ERROR, not a silent success.

    A delete that shrugs at a missing target turns "someone already removed this" and
    "I removed the wrong thing and the real one is still there" into the same green.
    """
    if not path:
        raise KeyError("empty target path")
    current = document
    for part in path[:-1]:
        current = current[part]
    if path[-1] not in current:
        raise ConfigExplorerError(
            "declaration_absent", "target_key",
            f"{'/'.join(str(p) for p in path)} is not in the file; nothing was changed",
        )
    del current[path[-1]]


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
            "target_bundle_path": list(node.bundle_path),
            "base_snapshot_hash": index.snapshot_hash,
            "base_definition_hash": node.definition_hash,
            "creates_declaration": False,
            "revision": 0,
            "lifecycle_status": "editing",
            "raw": node.raw,
            "preview_snapshot_hash": None,
            "preview_valid": False,
            "validation_errors": [],
            "review_revision": None,
            "review_history": [],
            "activated_snapshot_hash": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._write_record(record)
        return self.public(record)

    def create_new(self, active_setup: Any, index: ExplorerIndex,
                   kind: str, canonical_id: str) -> dict[str, Any]:
        """Open a draft for a declaration that does not exist yet.

        Two refusals, and each one is a different mistake:

          * a kind this screen cannot author -- `authorable_bundle_path` raises, and it is
            the SAME map `deletion_plan` reads, so what can be created is exactly what can
            be removed (the invariant landed 2026-08-19);
          * an id already in the snapshot -- creating would silently overwrite a live
            declaration, which is an edit wearing a create's clothes;

        The record stores `target_bundle_path` because there is no node to ask later; see
        `draft_target`.
        """
        section, name = authorable_bundle_path(kind, canonical_id)
        key = node_key(kind, canonical_id)
        if key in index.nodes:
            raise ConfigExplorerError(
                "declaration_exists", "canonical_id",
                f"{canonical_id!r} is already declared; open it to edit instead of "
                f"creating a second one",
            )
        now = _now()
        record = {
            "draft_id": uuid4().hex,
            "target_key": key,
            "target_id": canonical_id,
            "target_kind": kind,
            "target_bundle_path": [section, name],
            # 🔴 None, not the hash of an empty mapping. `stale_status` compares this
            # against what the index holds now, and a real hash here would make "nobody has
            # created this yet" indistinguishable from "somebody created it and it happens
            # to be empty".
            "base_snapshot_hash": index.snapshot_hash,
            "base_definition_hash": None,
            "creates_declaration": True,
            "revision": 0,
            "lifecycle_status": "editing",
            "raw": {},
            "preview_snapshot_hash": None,
            "preview_valid": False,
            "validation_errors": [],
            "review_revision": None,
            "review_history": [],
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
            if record["base_snapshot_hash"] != active_index.snapshot_hash:
                stale_status = self.stale_status(record, active_index)
                record["lifecycle_status"] = stale_status
                record["updated_at"] = _now()
                self._write_record(record)
                raise ConfigExplorerError(
                    f"{stale_status}_draft", "base_snapshot_hash",
                    "active snapshot changed; rebase before saving",
                )
            node = draft_target(record, active_index)
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
            if (record["lifecycle_status"] == "review_requested"
                    and record.get("review_revision") == record["revision"]):
                return self.public(record)
            record["lifecycle_status"] = "review_requested"
            record["review_revision"] = record["revision"]
            history = list(record.get("review_history") or [])
            history.append({
                "revision": record["revision"],
                "preview_snapshot_hash": record["preview_snapshot_hash"],
                "raw": record["raw"],
                "requested_at": _now(),
            })
            record["review_history"] = history
            record["updated_at"] = _now()
            self._write_record(record)
            return self.public(record)

    def revise(self, draft_id: str, *, expected_revision: int) -> dict[str, Any]:
        """Open a new editable revision without mutating the reviewed revision."""
        with self._lock:
            record = self._read_record(draft_id)
            self._require_revision(record, expected_revision)
            if record["lifecycle_status"] != "review_requested":
                raise ConfigExplorerError(
                    "review_revision_not_locked", "lifecycle_status",
                    "only a review-requested draft needs a new editable revision",
                )
            record["revision"] += 1
            record["lifecycle_status"] = "editing"
            record["preview_valid"] = False
            record["preview_snapshot_hash"] = None
            record["validation_errors"] = []
            record["review_revision"] = None
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
        convergence_probe: Callable[[str], Mapping[str, str]],
    ) -> dict[str, Any]:
        with self._lock:
            record = self._read_record(draft_id)
            self._require_revision(record, expected_revision)
            # 🔴 NO REVIEW PRECONDITION. Saving IS the write to the config file -- the
            # owner's ruling, and the button set that carries it is 생성·편집·저장·삭제.
            # A separate review step gated a door that no longer has a handle: with the
            # 활성화 button gone, a draft could never reach `review_requested`, so this
            # check would have refused every save the screen could make.
            # 🔴 THE BASIS IS THE FILE, NOT THE COMPILED SNAPSHOT. A compare-and-swap
            # asks "did the file change since I read it?" -- and under partial loading the
            # compiled hash also moves when an UNRELATED declaration stops resolving, which
            # would refuse the operator's save for something they did not touch. It is also
            # simply absent while a setup is mid-construction and compiles to nothing,
            # which is exactly when this check still has to work.
            if record["base_snapshot_hash"] != active_index.snapshot_hash:
                stale_status = self.stale_status(record, active_index)
                record["lifecycle_status"] = stale_status
                record["updated_at"] = _now()
                self._write_record(record)
                raise ConfigExplorerError(
                    f"{stale_status}_draft", "base_snapshot_hash",
                    "active snapshot changed; activation compare-and-swap refused",
                )
            node = draft_target(record, active_index)
            preview = compile_draft_preview(active_setup, node, record["raw"])
            # 🔴 NOT COMPILING NO LONGER BLOCKS THE WRITE. 「지금은 안읽히면 저장도
            # 안하네」 -- three gates used to stand here and each presumed a successful
            # compile, so each refused exactly the state a person is in while building:
            #
            #   draft_preview_invalid   refused any declaration whose references do not
            #                           exist YET -- the pack before its predicate, the
            #                           mapper before its pack. That is every intermediate
            #                           step of authoring, not an error.
            #   preview_hash_mismatch   compared a stored preview hash to a fresh compile.
            #                           A draft that does not compile has no stored hash
            #                           (`None`), so this could only ever fire.
            #   activation_hash_mismatch (below) same presumption after the reload.
            #
            # What replaces them is not a weaker check, it is a check in the right place:
            # the reader resolves declaration by declaration and tags what it cannot read.
            # `preview` is still compiled -- its errors are what the screen shows -- it just
            # no longer decides whether the file may be written.

            config_path = Path(active_setup.config_root) / node.config_file
            backup = self._activate_file(
                config_path, [(node.bundle_path, record["raw"])])
            # 🔴 THE WRITE STAYS, EVEN IF WHAT FOLLOWS FAILS. This used to restore the
            # backup and reload on any exception. Under the new model that would throw away
            # the operator's work for the ordinary case -- a declaration that does not
            # resolve yet -- and hand back a file that silently lost what they just typed.
            # The backup is still taken; it is a way back, not an automatic undo.
            reload_callback()
            actual_hash = document_hash(json.loads(
                config_path.read_text(encoding="utf-8")))
            consumer_hashes = dict(convergence_probe(actual_hash))
            if not consumer_hashes:
                raise ConfigExplorerError(
                    "convergence_unproven", "runtime_convergence",
                    "activation requires at least one declared persistent consumer",
                )
            mismatched = {
                consumer: value for consumer, value in consumer_hashes.items()
                if value != actual_hash
            }
            if mismatched:
                raise ConfigExplorerError(
                    "convergence_mismatch", "runtime_convergence",
                    "not every declared persistent consumer reports the activated snapshot",
                )

            record["lifecycle_status"] = "activated"
            record["activated_snapshot_hash"] = actual_hash
            record["updated_at"] = _now()
            self._write_record(record)
            return {
                "draft": self.public(record),
                "active_snapshot_hash": actual_hash,
                "runtime_convergence": {
                    "status": "confirmed",
                    "snapshot_hash": actual_hash,
                    "required_consumers": sorted(consumer_hashes),
                    "confirmed_consumers": sorted(consumer_hashes),
                    "consumer_hashes": dict(sorted(consumer_hashes.items())),
                    "note": (
                        "all declared persistent Ledger v2 consumers confirmed; "
                        "backfill consumers compile the manifest at each run boundary"),
                },
                "backup": str(backup),
            }

    def preview(
        self,
        record: Mapping[str, Any],
        active_setup: Any,
        active_index: ExplorerIndex,
    ) -> DraftPreview:
        if record["base_snapshot_hash"] != active_index.snapshot_hash:
            stale_status = self.stale_status(record, active_index)
            return DraftPreview(False, None, None, ({
                "code": f"{stale_status}_draft",
                "path": "base_snapshot_hash",
                "message": "active snapshot changed; draft preview is stale",
            },))
        node = draft_target(record, active_index)
        return compile_draft_preview(active_setup, node, record["raw"])

    @staticmethod
    def public(record: Mapping[str, Any]) -> dict[str, Any]:
        # 🔴 THIS IS A WHITELIST, so a field added to the record is INVISIBLE on the wire
        # until it is named here -- and invisible reads to the screen as absent, not as
        # missing. `creates_declaration` is what lets the client tell "authoring a new
        # declaration" from "editing a live one", which is the difference between the
        # confirm saying 새로 만듦 and 덮어씀.
        return {key: record.get(key) for key in (
            "draft_id", "target_key", "target_id", "target_kind",
            "target_bundle_path", "creates_declaration",
            "base_snapshot_hash", "base_definition_hash", "revision",
            "lifecycle_status", "raw",
            "preview_snapshot_hash", "preview_valid", "validation_errors",
            "review_revision", "review_history", "activated_snapshot_hash",
            "created_at", "updated_at",
        )}

    @staticmethod
    def stale_status(record: Mapping[str, Any], active_index: ExplorerIndex) -> str:
        """`stale` -- the file moved under us. `conflict` -- it moved UNDER THIS TARGET.

        🔴 THE TWO CASES INVERT FOR A CREATE DRAFT. For an edit, an absent target means
        somebody deleted what we are editing -- a conflict. For a create, absent is the
        NORMAL state and the whole point; what is a conflict there is the target having
        APPEARED, because somebody else authored the same name while we were typing and
        activating would overwrite them.

        Reading the edit rule onto a create draft reports a conflict on every single
        create, which reads to the operator as "this screen cannot make new declarations"
        -- the defect being fixed, restated as a status string.
        """
        current = active_index.nodes.get(str(record.get("target_key")))
        if record.get("creates_declaration"):
            return "conflict" if current is not None else "stale"
        if current is None:
            return "conflict"
        return (
            "conflict"
            if current.definition_hash != record.get("base_definition_hash")
            else "stale"
        )

    def _activate_file(self, path: Path,
                       operations: Sequence[tuple[Sequence[Any], Any]]) -> Path:
        """Apply every operation to one document in ONE replace.

        Operations rather than a single value because a RENAME is a removal and a write
        that must not be separable: two activations would leave a window in which the
        declaration exists twice, or not at all, and a reader arriving in that window
        would see a config that no author ever wrote.
        """
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
            for op_path, op_value in operations:
                if isinstance(op_value, _Remove):
                    _delete_path(document, op_path)
                else:
                    _set_path(document, op_path, op_value)
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
