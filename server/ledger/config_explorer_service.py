"""Cached application service for the ontology config explorer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from .config_drafts import OntologyDraftStore
from .config_explorer import (
    ConfigExplorerError,
    ExplorerIndex,
    build_explorer_index,
    definition_diff,
    explorer_view,
)
from .cutover_v2 import DEFAULT_ONTOLOGY_ROOT, load_cutover_setup


class OntologyExplorerService:
    def __init__(
        self,
        *,
        config_root: str | Path = DEFAULT_ONTOLOGY_ROOT,
        draft_root: str | Path | None = None,
        setup_loader: Callable[[str | Path], Any] = load_cutover_setup,
    ):
        self.config_root = Path(config_root)
        self.draft_store = OntologyDraftStore(
            draft_root or self.config_root.parent / "backup" / "ontology_drafts")
        self._setup_loader = setup_loader
        self._lock = RLock()
        self._stamp: tuple[Any, ...] | None = None
        self._setup: Any | None = None
        self._index: ExplorerIndex | None = None
        self._compiled_at: str | None = None

    def invalidate(self) -> None:
        with self._lock:
            self._stamp = None
            self._setup = None
            self._index = None
            self._compiled_at = None

    def active(self, *, force: bool = False) -> tuple[Any, ExplorerIndex, str]:
        with self._lock:
            stamp = self._file_stamp()
            if force or self._setup is None or stamp != self._stamp:
                setup = self._setup_loader(self.config_root)
                index = build_explorer_index(setup)
                self._setup = setup
                self._index = index
                self._stamp = stamp
                self._compiled_at = datetime.now(timezone.utc).isoformat()
            return self._setup, self._index, self._compiled_at

    def view(
        self,
        *,
        selection: str | None = None,
        query: str = "",
        page: int = 1,
        limit: int = 100,
        reference_limit: int = 200,
        expected_context_token: str | None = None,
        draft_id: str | None = None,
        revision: int | None = None,
    ) -> dict[str, Any]:
        setup, active_index, compiled_at = self.active()
        active_token = f"active:{active_index.snapshot_hash}"
        context = {
            "mode": "active",
            "context_token": active_token,
            "active_snapshot_hash": active_index.snapshot_hash,
            "preview_snapshot_hash": None,
            "fallback_reason": None,
        }
        index = active_index
        token = active_token
        diff = None
        draft = None

        if draft_id is not None:
            record = self.draft_store.get(draft_id)
            if revision is not None and revision != record["revision"]:
                raise ConfigExplorerError(
                    "stale_revision", "revision",
                    f"requested revision {revision}, current is {record['revision']}",
                )
            preview = self.draft_store.preview(record, setup, active_index)
            draft = self.draft_store.public(record)
            if preview.valid and preview.index is not None:
                index = preview.index
                token = (
                    f"draft:{record['draft_id']}:{record['revision']}:"
                    f"{index.snapshot_hash}")
                diff = definition_diff(active_index, index)
                context = {
                    "mode": "draft_preview",
                    "context_token": token,
                    "active_snapshot_hash": active_index.snapshot_hash,
                    "preview_snapshot_hash": index.snapshot_hash,
                    "fallback_reason": None,
                }
            else:
                reason = preview.errors[0]["code"] if preview.errors else "draft_invalid"
                if reason == "stale_draft":
                    # A read does not rewrite draft history, but its public lifecycle must
                    # describe the current active-base relationship, not the old saved state.
                    draft["lifecycle_status"] = "stale"
                context = {
                    "mode": "active_fallback",
                    "context_token": active_token,
                    "active_snapshot_hash": active_index.snapshot_hash,
                    "preview_snapshot_hash": None,
                    "fallback_reason": reason,
                }
                draft["validation_errors"] = [dict(item) for item in preview.errors]

        payload = explorer_view(
            index, context_token=token, selection=selection, query=query,
            page=page, limit=limit, reference_limit=reference_limit, diff=diff)
        payload["active_snapshot"] = {
            "snapshot_hash": active_index.snapshot_hash,
            "compiled_at": compiled_at,
            "valid": True,
        }
        payload["view_context"] = context
        payload["draft"] = draft
        self._assert_context(payload)
        if expected_context_token is not None and expected_context_token != token:
            raise ConfigExplorerError(
                "stale_context", "context_token",
                "requested view context no longer matches the compiled response context",
            )
        return payload

    def create_draft(self, *, target_key: str, base_snapshot_hash: str) -> dict[str, Any]:
        setup, index, _ = self.active()
        if base_snapshot_hash != index.snapshot_hash:
            raise ConfigExplorerError(
                "stale_base_snapshot", "base_snapshot_hash",
                "active snapshot changed before draft creation",
            )
        return self.draft_store.create(setup, index, target_key)

    def save_draft(self, draft_id: str, *, expected_revision: int, raw: str
                   ) -> dict[str, Any]:
        setup, index, _ = self.active()
        draft, preview = self.draft_store.save(
            draft_id, expected_revision=expected_revision, raw_text=raw,
            active_setup=setup, active_index=index)
        draft["context_token"] = (
            f"draft:{draft_id}:{draft['revision']}:{draft['preview_snapshot_hash']}"
            if preview.valid else f"active:{index.snapshot_hash}")
        return draft

    def review_draft(self, draft_id: str, *, expected_revision: int) -> dict[str, Any]:
        return self.draft_store.request_review(
            draft_id, expected_revision=expected_revision)

    def discard_draft(self, draft_id: str, *, expected_revision: int) -> dict[str, Any]:
        return self.draft_store.discard(
            draft_id, expected_revision=expected_revision)

    def activate_draft(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        reload_callback: Callable[[], None],
    ) -> dict[str, Any]:
        setup, index, _ = self.active()

        def refreshed() -> Any:
            self.invalidate()
            return self.active(force=True)[0]

        result = self.draft_store.activate(
            draft_id, expected_revision=expected_revision,
            active_setup=setup, active_index=index,
            reload_callback=reload_callback, refreshed_setup=refreshed)
        self.invalidate()
        return result

    def _file_stamp(self) -> tuple[Any, ...]:
        if not self.config_root.is_dir():
            return ((str(self.config_root), "missing"),)
        values = []
        for path in sorted(self.config_root.rglob("*.json")):
            stat = path.stat()
            values.append((
                path.relative_to(self.config_root).as_posix(),
                stat.st_mtime_ns,
                stat.st_size,
            ))
        return tuple(values)

    @staticmethod
    def _assert_context(payload: dict[str, Any]) -> None:
        token = payload["context_token"]
        if payload["view_context"]["context_token"] != token:
            raise ConfigExplorerError(
                "context_mismatch", "view_context.context_token",
                "view context token does not match the response token",
            )
        for field in ("items", "nodes", "outbound", "used_by"):
            for index, item in enumerate(payload[field]):
                if item.get("context_token") != token:
                    raise ConfigExplorerError(
                        "context_mismatch", f"{field}[{index}].context_token",
                        "response objects must use one context token",
                    )
        if payload["selection"].get("context_token") != token:
            raise ConfigExplorerError(
                "context_mismatch", "selection.context_token",
                "selection token does not match the response token",
            )
