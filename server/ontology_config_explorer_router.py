"""Admin API for the Ledger v2 ontology config explorer."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from admin_auth import require_admin_token, require_admin_token_strict
from database.database import get_db
from ledger.column_stats import ColumnStatsError
from ledger.config_explorer import ConfigExplorerError
from ledger.config_explorer_service import OntologyExplorerService
from ledger.setup import DEFAULT_ONTOLOGY_ROOT


router = APIRouter(prefix="/admin/ontology-explorer", tags=["ontology-explorer"])
_service = OntologyExplorerService(config_root=DEFAULT_ONTOLOGY_ROOT)


def configure_service(service: OntologyExplorerService) -> None:
    """Test seam; production owns exactly one process-local immutable index cache."""
    global _service
    _service = service


def _refusal(exc: ConfigExplorerError | ColumnStatsError) -> HTTPException:
    status = 409 if exc.code in {
        "stale_base_snapshot", "stale_draft", "stale_revision",
        "conflict_draft", "stale_context", "review_revision_locked",
        "activation_locked", "convergence_mismatch", "convergence_unproven",
    } else 400
    return HTTPException(status_code=status, detail=exc.to_mapping())


@router.get("/view", dependencies=[Depends(require_admin_token)])
def explorer_view(
    selection: str | None = Query(default=None),
    q: str = Query(default=""),
    page: int = Query(default=1),
    limit: int = Query(default=100),
    reference_limit: int = Query(default=200),
    context_token: str | None = Query(default=None),
    draft_id: str | None = Query(default=None),
    revision: int | None = Query(default=None),
    view_mode: str = Query(default="active"),
):
    try:
        return _service.view(
            selection=selection, query=q, page=page, limit=limit,
            reference_limit=reference_limit, expected_context_token=context_token,
            draft_id=draft_id, revision=revision, view_mode=view_mode)

    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.get("/columns", dependencies=[Depends(require_admin_token)])
def column_picker(
    relation: str = Query(...),
    combination: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Candidate columns for `relation`, each with how many rows actually carry a value.

    A read, and an EXPENSIVE one by design: the population counts are exact and cost one
    table scan. `estimated_rows` comes back with them so a caller can see what it asked
    for. Nothing is written and no cursor moves.

    `combination` may be repeated to measure one ordering's real uniqueness on the same
    call -- the question that is otherwise answered mid-backfill.
    """
    try:
        return _service.column_picker(
            db, relation=relation, combination=combination or [])
    except (ColumnStatsError, ConfigExplorerError) as exc:
        raise _refusal(exc) from exc


@router.get("/authoring/schema", dependencies=[Depends(require_admin_token)])
def authoring_schema():
    """Every closed list the authoring screen offers, from the validator's own constants.

    The screen owns no copy.  This is what keeps "고를 수 있는 것" correct on the day a
    declaration is added instead of the day somebody notices the dropdown is short.
    """
    return _service.authoring_schema()


@router.get("/authoring/plan", dependencies=[Depends(require_admin_token)])
def authoring_plan_view(selection: str | None = Query(default=None)):
    """What one declaration forces (filled, WITH its ground), and what is still asked.

    A read of the authoring FILE, not of the compiled snapshot -- so it answers on a
    blank or half-written root, which is exactly when `/view` cannot.
    """
    try:
        return _service.authoring(
            selection_prefix=_service.authoring_prefix(selection))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.get("/deletion-preview", dependencies=[Depends(require_admin_token)])
def deletion_preview(
    targets: list[str] | None = Query(default=None),
    context_token: str | None = Query(default=None),
):
    """Name every declaration a deletion would take, BEFORE the author confirms.

    A read: nothing is written and no draft is created, which is why it sits behind the
    same token as `/view` rather than the strict one.
    """
    try:
        return _service.deletion_preview(
            targets=targets or [], expected_context_token=context_token)
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts", dependencies=[Depends(require_admin_token_strict)])
def create_draft(payload: dict[str, Any] = Body(...)):
    try:
        return _service.create_draft(
            target_key=str(payload.get("target_key", "")),
            base_snapshot_hash=str(payload.get("base_snapshot_hash", "")),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/bootstrap", dependencies=[Depends(require_admin_token_strict)])
def bootstrap_config():
    """Create the smallest config that validates, so a setup can start from nothing.

    A write, and the only one this screen performs without a draft -- so it is a POST the
    operator confirms, never something the screen does on its own when it notices the file
    is missing. Refuses if anything exists at the path, including a file that fails to
    parse: an unreadable config is somebody's work with a bad comma in it, not an absence.
    """
    try:
        return _service.bootstrap_config()
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts/new", dependencies=[Depends(require_admin_token_strict)])
def create_declaration_draft(payload: dict[str, Any] = Body(...)):
    """Author a declaration the snapshot has never seen.

    The last hole in the write path: this screen could edit a declaration and could not
    make one, so a new source had to be typed into the file by hand.  Refusals name the
    mistake -- `declaration_exists` (open it instead), `unauthorable_kind` (this screen
    cannot write that section).
    """
    try:
        return _service.create_declaration_draft(
            kind=str(payload.get("kind", "")),
            canonical_id=str(payload.get("canonical_id", "")),
            base_snapshot_hash=str(payload.get("base_snapshot_hash", "")),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.put("/drafts/{draft_id}", dependencies=[Depends(require_admin_token_strict)])
def save_draft(draft_id: str, payload: dict[str, Any] = Body(...)):
    try:
        return _service.save_draft(
            draft_id,
            expected_revision=payload.get("expected_revision"),
            raw=payload.get("raw"),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts/{draft_id}/review",
             dependencies=[Depends(require_admin_token_strict)])
def review_draft(draft_id: str, payload: dict[str, Any] = Body(...)):
    try:
        return _service.review_draft(
            draft_id, expected_revision=payload.get("expected_revision"))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts/{draft_id}/revise",
             dependencies=[Depends(require_admin_token_strict)])
def revise_draft(draft_id: str, payload: dict[str, Any] = Body(...)):
    try:
        return _service.revise_draft(
            draft_id, expected_revision=payload.get("expected_revision"))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.delete("/drafts/{draft_id}",
               dependencies=[Depends(require_admin_token_strict)])
def discard_draft(
    draft_id: str,
    expected_revision: int = Query(...),
):
    try:
        return _service.discard_draft(
            draft_id, expected_revision=expected_revision)
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.delete("/declarations/{target_key:path}",
               dependencies=[Depends(require_admin_token_strict)])
def delete_declaration(
    target_key: str,
    base_snapshot_hash: str,
    db: Session = Depends(get_db),
):
    try:
        import main as app_main
        return _service.delete_declaration(
            target_key, base_snapshot_hash=base_snapshot_hash,
            reload_callback=lambda: app_main.reload_system_configs(db=db))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts/{draft_id}/activate",
             dependencies=[Depends(require_admin_token_strict)])
def activate_draft(
    draft_id: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    try:
        # Import only at the write boundary to avoid a router/main import cycle.
        import main as app_main
        return _service.activate_draft(
            draft_id,
            expected_revision=payload.get("expected_revision"),
            reload_callback=lambda: app_main.reload_system_configs(db=db),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc
