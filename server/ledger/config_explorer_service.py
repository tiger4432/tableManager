"""Cached application service for the ontology config explorer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Sequence

from .config_drafts import OntologyDraftStore
from .config_explorer import (
    ConfigExplorerError,
    ExplorerIndex,
    build_explorer_index,
    definition_diff,
    deletion_plan,
    explorer_view,
    reference_diff,
)
from .setup import DEFAULT_ONTOLOGY_ROOT, load_setup


class OntologyExplorerService:
    def __init__(
        self,
        *,
        config_root: str | Path = DEFAULT_ONTOLOGY_ROOT,
        draft_root: str | Path | None = None,
        setup_loader: Callable[[str | Path], Any] = load_setup,
        convergence_probe: Callable[[str], dict[str, str]] | None = None,
    ):
        self.config_root = Path(config_root)
        self.draft_store = OntologyDraftStore(
            draft_root or self.config_root.parent / "backup" / "ontology_drafts")
        self._setup_loader = setup_loader
        self._convergence_probe = convergence_probe or (
            lambda expected: {"ontology-explorer-api": expected})
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
        view_mode: str = "active",
    ) -> dict[str, Any]:
        if view_mode not in {"active", "draft_preview"}:
            raise ConfigExplorerError(
                "invalid_view_mode", "view_mode",
                "view mode must be active or draft_preview",
            )
        if view_mode == "draft_preview" and draft_id is None:
            raise ConfigExplorerError(
                "draft_required", "draft_id",
                "draft_preview mode requires a draft id",
            )
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
        edge_changes = None
        draft = None

        if draft_id is not None:
            record = self.draft_store.get(draft_id)
            if revision is not None and revision != record["revision"]:
                raise ConfigExplorerError(
                    "stale_revision", "revision",
                    f"requested revision {revision}, current is {record['revision']}",
                )
            draft = self.draft_store.public(record)
            preview = self.draft_store.preview(record, setup, active_index)
            if view_mode == "draft_preview" and preview.valid and preview.index is not None:
                index = preview.index
                token = (
                    f"draft:{record['draft_id']}:{record['revision']}:"
                    f"{index.snapshot_hash}")
                diff = definition_diff(active_index, index)
                edge_changes = reference_diff(active_index, index)
                context = {
                    "mode": "draft_preview",
                    "context_token": token,
                    "active_snapshot_hash": active_index.snapshot_hash,
                    "preview_snapshot_hash": index.snapshot_hash,
                    "fallback_reason": None,
                }
            elif view_mode == "draft_preview":
                reason = preview.errors[0]["code"] if preview.errors else "draft_invalid"
                if reason in {"stale_draft", "conflict_draft"}:
                    # A read does not rewrite draft history, but its public lifecycle must
                    # describe the current active-base relationship, not the old saved state.
                    draft["lifecycle_status"] = reason.removesuffix("_draft")
                context = {
                    "mode": "active_fallback",
                    "context_token": active_token,
                    "active_snapshot_hash": active_index.snapshot_hash,
                    "preview_snapshot_hash": None,
                    "fallback_reason": reason,
                }
                draft["validation_errors"] = [dict(item) for item in preview.errors]
            elif not preview.valid and preview.errors:
                reason = preview.errors[0]["code"]
                if reason in {"stale_draft", "conflict_draft"}:
                    draft["lifecycle_status"] = reason.removesuffix("_draft")

        payload = explorer_view(
            index, context_token=token, selection=selection, query=query,
            page=page, limit=limit, reference_limit=reference_limit, diff=diff,
            edge_diff=edge_changes)
        if diff is not None:
            payload["changes"] = [
                self._definition_change(
                    key, status, token=token,
                    active=active_index, preview=index,
                )
                for key, status in sorted(diff.items())
                if status != "unchanged"
            ]
        if edge_changes is not None:
            active_edges = {edge.edge_id: edge for edge in active_index.edges}
            preview_edges = {edge.edge_id: edge for edge in index.edges}
            payload["edge_changes"] = [
                {
                    **(preview_edges.get(edge_id) or active_edges[edge_id]).to_mapping(),
                    "change_status": status,
                    "context_token": token,
                }
                for edge_id, status in sorted(edge_changes.items())
                if status != "unchanged"
            ]
        payload["active_snapshot"] = {
            "snapshot_hash": active_index.snapshot_hash,
            "compiled_at": compiled_at,
            "valid": True,
        }
        payload["view_context"] = context
        payload["draft"] = draft
        if draft is not None:
            draft["context_token"] = token
            draft["affected_definitions"] = payload["changes"]
            draft["affected_edges"] = payload["edge_changes"]
            for error in draft.get("validation_errors") or []:
                error["context_token"] = token
        self._assert_context(payload)
        if expected_context_token is not None and expected_context_token != token:
            raise ConfigExplorerError(
                "stale_context", "context_token",
                "requested view context no longer matches the compiled response context",
            )
        return payload

    @staticmethod
    def _definition_change(
        key: str,
        status: str,
        *,
        token: str,
        active: ExplorerIndex,
        preview: ExplorerIndex,
    ) -> dict[str, Any]:
        node = preview.nodes.get(key) or active.nodes[key]
        return {
            **node.to_mapping(include_definition=False),
            "change_status": status,
            "context_token": token,
        }

    def deletion_preview(
        self,
        *,
        targets: Sequence[str],
        expected_context_token: str | None = None,
    ) -> dict[str, Any]:
        """What would go with this deletion -- READ ONLY, and it does not refuse.

        The blockage belongs in the payload, not in an exception: the screen has to render
        "this one is still referenced, by that one" next to the casualties, and an operator
        who only gets a 400 cannot see the list they were asked to confirm.  The write path
        is where `require_deletable` turns the same rows into a refusal.

        Computed against the ACTIVE index only.  A draft preview compiles a DIFFERENT
        snapshot, and naming casualties from one snapshot for a deletion applied to another
        is how a confirm screen ends up listing declarations that are not there.
        """
        _, index, _ = self.active()
        token = f"active:{index.snapshot_hash}"
        if expected_context_token is not None and expected_context_token != token:
            raise ConfigExplorerError(
                "stale_context", "context_token",
                "requested deletion context no longer matches the active snapshot",
            )
        payload = deletion_plan(index, targets).to_mapping()
        payload["context_token"] = token
        payload["snapshot_hash"] = index.snapshot_hash
        for field in ("removed", "released", "blocked"):
            for row in payload[field]:
                row["context_token"] = token
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

    def revise_draft(self, draft_id: str, *, expected_revision: int) -> dict[str, Any]:
        return self.draft_store.revise(
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
            reload_callback=reload_callback, refreshed_setup=refreshed,
            convergence_probe=self._convergence_probe)
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
        for field in (
            "items", "nodes", "outbound", "used_by", "path_candidates",
            "integrity", "changes", "edge_changes",
        ):
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
        draft = payload.get("draft")
        if draft is not None:
            if draft.get("context_token") != token:
                raise ConfigExplorerError(
                    "context_mismatch", "draft.context_token",
                    "draft metadata must describe the rendered view context",
                )
            for index, error in enumerate(draft.get("validation_errors") or []):
                if error.get("context_token") != token:
                    raise ConfigExplorerError(
                        "context_mismatch",
                        f"draft.validation_errors[{index}].context_token",
                        "draft validation must describe the rendered view context",
                    )
