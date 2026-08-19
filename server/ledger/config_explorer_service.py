"""Cached application service for the ontology config explorer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Sequence

from .column_stats import (
    ColumnStatsError, combination_uniqueness, estimated_rows, ordering_candidates,
    population,
)
from .config_authoring import authoring_plan, closed_lists
from .config_drafts import OntologyDraftStore
from .config_explorer import (
    ConfigExplorerError,
    ExplorerIndex,
    authorable_bundle_path,
    build_explorer_index,
    definition_diff,
    deletion_plan,
    explorer_view,
    reference_diff,
)
from .setup import DEFAULT_ONTOLOGY_ROOT, live_physical_catalog, load_setup
from .setup_bundle import (
    CONFIG_FILENAME, LOGICAL_SECTIONS, SETUP_VERSION, validate_bundle_errors,
)


class OntologyExplorerService:
    def __init__(
        self,
        *,
        config_root: str | Path = DEFAULT_ONTOLOGY_ROOT,
        draft_root: str | Path | None = None,
        setup_loader: Callable[[str | Path], Any] = load_setup,
        catalog_loader: Callable[[], Mapping[str, Any]] = live_physical_catalog,
        convergence_probe: Callable[[str], dict[str, str]] | None = None,
    ):
        self._catalog_loader = catalog_loader
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

    def column_picker(
        self,
        db: Any,
        *,
        relation: str,
        combination: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Candidate columns WITH the numbers that decide between them.

        🔴 THE NUMBERS ARE THE FEATURE.  A picker that lists 38 column names is a spelling
        aid; a picker that says `dt_job_id  0 / 34,939` is the thing that stops a config
        which validates, compiles, runs, and yields nothing.  Both defects of 2026-08-18
        were invisible to every refusal in the system and visible in one glance here.

        `combination` is optional and answers the second question on the same surface:
        given these columns, is the ordering actually unique?  The compile-time check only
        asks whether an ordering covers a DECLARED key, and the declaration can be wrong --
        `dt_log` declares one made of three empty columns.

        The relation must be declared in `table_config.json`, which this reads and never
        writes.  Undeclared tables are refused by name rather than silently offered: a
        relation the rest of the system does not know has no keys, no ingestion and no
        chains, and binding the ledger to it produces atoms about rows nobody can address.
        """
        setup, _, _ = self.active()
        catalog = getattr(setup, "catalog", None)
        if not isinstance(catalog, Mapping) or relation not in catalog:
            raise ColumnStatsError(
                "undeclared_relation", "relation",
                f"relation {relation!r} is not declared in table_config.json; declare it "
                f"there first -- an undeclared table has no keys, no ingestion and no "
                f"chains, so the ledger cannot address its rows")
        payload = population(db, relation)
        payload["estimated_rows"] = estimated_rows(db, relation)
        payload["ordering"] = ordering_candidates(db, relation, catalog[relation])
        payload["combination"] = (
            combination_uniqueness(db, relation, list(combination))
            if combination else None)
        return payload

    def authoring_schema(self) -> dict[str, Any]:
        """Every closed list the authoring screen may offer.

        Served from the constants the VALIDATOR enforces, so the screen never carries a
        copy.  A list literal in the UI is a second author for a value whose first author
        is a refusal, and the two diverge in silence the day a declaration is added.
        """
        return closed_lists()

    @staticmethod
    def authoring_prefix(selection: str | None) -> str | None:
        """`kind|id` -> the bundle path prefix its authoring rows live under.

        Lenient by design.  Sub-declaration kinds (`claim`, `mapping`, `binding`) have no
        entry in `AUTHORABLE_SECTIONS`, and a selection this cannot place must widen the
        plan to everything rather than refuse -- a screen that answers "no rows" for a
        claim would read as "nothing left to do", which is the silent-empty-panel failure
        this whole round exists to remove.
        """
        if not selection or "|" not in selection:
            return None
        kind, canonical_id = selection.split("|", 1)
        try:
            section, name = authorable_bundle_path(kind, canonical_id)
        except ConfigExplorerError:
            return None
        return f"bundle.{section}.{name}"

    def authoring(self, *, selection_prefix: str | None = None) -> dict[str, Any]:
        """What is filled by force, what is missing, and what is still a real question.

        🔴 THIS DELIBERATELY DOES NOT GO THROUGH `active()`.  A compiled snapshot exists
        only for a bundle that already validates, and the authoring screen is needed
        exactly when it does not -- a half-written source, or a blank root that makes
        `/view` answer 500.  So the plan reads the authoring FILE, tolerates any shape it
        finds, and lets `authoring_plan` name the deficits instead of raising.
        """
        path = self.config_root / CONFIG_FILENAME
        if not path.is_file():
            # A named absence, not an empty plan: the operator needs the file name.
            bundle: Mapping[str, Any] = {}
            source = {"file": str(path), "state": "absent"}
        else:
            try:
                bundle = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ConfigExplorerError(
                    "unreadable_config", CONFIG_FILENAME,
                    f"{path} could not be read as JSON: {exc}") from exc
            if not isinstance(bundle, Mapping):
                raise ConfigExplorerError(
                    "unreadable_config", CONFIG_FILENAME,
                    f"{path} must contain a JSON object")
            source = {"file": str(path), "state": "present"}
        payload = authoring_plan(
            bundle, self._catalog_loader(), selection_prefix=selection_prefix)
        payload["config_source"] = source
        return payload

    def bootstrap_config(self) -> dict[str, Any]:
        """Write the smallest file that validates, so a setup can start from nothing.

        Until this existed the screen could not be used from a blank root at all: every
        authoring path needs a config to read, so the first declaration had to be typed
        into a text editor by hand. That is the trip this removes.

        🔴 REFUSES IF ANYTHING IS AT THE PATH, and the reason is not tidiness. An
        UNREADABLE config is not an absent one -- it is very likely a file somebody spent
        hours on with one bad comma in it, and writing a skeleton over that destroys the
        work while looking like a feature. Absence is the only state this may act on, so
        the check is `exists()`, not "does it parse": a file that fails to parse still
        exists, and that is exactly the case that must be refused rather than repaired.
        The operator is told to fix the file; `authoring()` already reports the parse error
        with its position.

        🔴 THE SKELETON IS MEASURED, NOT INVENTED. `setup_version` and the section names
        come from `setup_bundle`'s own constants, so a section added to the grammar appears
        here without anyone remembering to add it. Nothing else is written: every extra
        field would be a guess, and `validate_bundle_errors` refuses guesses. Verified
        against the live catalog -- this exact object produces 0 issues, while `{}`
        produces 9, so the check is not vacuous.
        """
        path = self.config_root / CONFIG_FILENAME
        if path.exists():
            raise ConfigExplorerError(
                "config_already_present", CONFIG_FILENAME,
                f"{path} already exists; this screen never overwrites a config. If it "
                f"does not load, fix the reported parse error -- a file that cannot be "
                f"read is still a file somebody wrote",
            )
        skeleton = {
            "setup_version": SETUP_VERSION,
            **{name: {} for name in LOGICAL_SECTIONS},
        }
        # Checked BEFORE it is written, against the same validator the loader uses. A
        # skeleton that does not validate would hand the operator a file to repair, which
        # is the trip this whole path exists to remove.
        issues = validate_bundle_errors(skeleton, catalog=self._catalog_loader())
        if issues:
            raise ConfigExplorerError(
                "bootstrap_invalid", CONFIG_FILENAME,
                "the starting file did not validate and was not written",
                [issue.to_mapping() for issue in issues],
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(skeleton, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
            encoding="utf-8")
        self.invalidate()
        return {"created": str(path), "bundle": skeleton, "sections": list(LOGICAL_SECTIONS)}

    def create_draft(self, *, target_key: str, base_snapshot_hash: str) -> dict[str, Any]:
        setup, index, _ = self.active()
        if base_snapshot_hash != index.snapshot_hash:
            raise ConfigExplorerError(
                "stale_base_snapshot", "base_snapshot_hash",
                "active snapshot changed before draft creation",
            )
        return self.draft_store.create(setup, index, target_key)

    def create_declaration_draft(self, *, kind: str, canonical_id: str,
                                 base_snapshot_hash: str) -> dict[str, Any]:
        """Open a draft for a declaration that does not exist yet.

        Separate from `create_draft` rather than a flag on it, because the two take
        DIFFERENT ARGUMENTS: editing names an existing node by key, authoring names a kind
        and an id that nothing has claimed.  Folding them into one endpoint would mean a
        `target_key` for a node that is not there, which is the shape that made creating
        impossible in the first place.
        """
        setup, index, _ = self.active()
        if base_snapshot_hash != index.snapshot_hash:
            raise ConfigExplorerError(
                "stale_base_snapshot", "base_snapshot_hash",
                "active snapshot changed before draft creation",
            )
        return self.draft_store.create_new(setup, index, kind, canonical_id)

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
