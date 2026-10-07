"""Admin API for the Ledger v2 ontology config explorer."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from admin import sso
from admin.auth import require_admin_token, require_admin_token_strict
from database.database import get_db
from ledger.column_stats import ColumnStatsError
from ledger.config_explorer import ConfigExplorerError
from ledger.config_explorer_service import OntologyExplorerService, required_draft_id
from ledger.setup import DEFAULT_ONTOLOGY_ROOT


router = APIRouter(prefix="/admin/ontology-explorer", tags=["ontology-explorer"])
#: One explorer per ledger world, built from the world seat's names (총괄 60d7e8e42): its
#: declaration root, its drafts, and the declaration a new branch starts from. Key None is
#: the default world.
_services = {None: OntologyExplorerService(config_root=DEFAULT_ONTOLOGY_ROOT)}


def configure_service(service: OntologyExplorerService, world: str | None = None) -> None:
    """Put `service` in front of one world's routes (the default when `world` is None)."""
    _services[world] = service


def _service_for(world) -> OntologyExplorerService:
    """The explorer of the world a request named - None, blank or FastAPI's `Query` sentinel
    (a direct call) is the default. A branch not made yet is served too: its bootstrap is
    how it is made. A name that is not a world name is refused by name."""
    from ledger import schema

    try:
        names = schema.world_names(
            world if isinstance(world, str) and world.strip() else None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={
            "reason": "world_unknown", "world": world, "message": str(exc)})
    if names.world not in _services:
        _services[names.world] = OntologyExplorerService(
            config_root=names.declaration_root, draft_root=names.draft_root)
    return _services[names.world]


@router.delete("/worlds/{world}", dependencies=[Depends(require_admin_token_strict)])
def delete_world(world: str, confirm_atoms: int | None = Query(default=None)):
    """A ledger branch goes whole - its schema and its files (총괄 8d10633ae ㉢). Without
    `confirm_atoms` this answers what would go and deletes nothing; with the atom count that
    answer showed, it deletes. A DROP is not undone, so the answer always comes first."""
    from database.database import engine
    from ledger import schema

    try:
        if confirm_atoms is None:
            return schema.world_deletion(engine, world)
        deleted = schema.drop_world(engine, world, confirm_atoms)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={
            "reason": "world_unknown", "world": world, "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "reason": "world_not_deleted", "world": world, "message": str(exc)})
    _services.pop(world, None)
    return deleted


def _worlds() -> dict:
    from ledger import schema

    listing = schema.world_listing()
    return {**listing, "live": {world: schema.live(world) for world in listing["worlds"]},
            "history": list(schema.layout().get("history", []))}


@router.get("/worlds", dependencies=[Depends(require_admin_token)])
def list_worlds():
    """The worlds, the operating one, which follow their tables live, and who switched what
    when."""
    return _worlds()


@router.put("/worlds/{world}/live", dependencies=[Depends(require_admin_token_strict)])
def set_world_live(world: str, request: Request, payload: dict[str, Any] = Body(...),
                   db: Session = Depends(get_db)):
    """Switch `world`'s live follow-up on or off from the next batch on (총괄 092a6f9e5); the
    history keeps who and when. On: what it missed while off is caught up by a job through the
    job door (`ledger_catch_up`, 총괄 71880678a), and the answer carries its `run_id`."""
    from admin import retroactive
    from ledger import schema

    live = payload.get("live")
    if not isinstance(live, bool):
        raise HTTPException(status_code=400, detail={
            "reason": "live_required", "message": "Send live: true or false."})
    by = sso.who(request, request.headers.get("X-User"))
    try:
        schema.set_live(world, live, by)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=404, detail={
            "reason": "world_unknown", "world": world, "message": str(exc)})
    answer = _worlds()
    if live:
        answer["run_id"] = retroactive.publish(
            db, "ledger_catch_up", {"world": schema.world_names(world).name},
            requested_by=by)["run_id"]
    return answer


@router.put("/worlds/operating", dependencies=[Depends(require_admin_token_strict)])
def operate_world(request: Request, payload: dict[str, Any] = Body(...)):
    """Every seat that names no world reads and writes `payload.world` from the next request
    and the next follow-up batch on (총괄 e67ef53f3 ②); back = the same with the old name. Its
    schema is made first, so the follow-up has somewhere to write."""
    from database.database import engine
    from ledger import schema

    world = payload.get("world")
    if not isinstance(world, str) or not world.strip():
        raise HTTPException(status_code=400, detail={
            "reason": "world_required", "message": "Name the world to operate."})
    try:
        schema.ensure_world(engine, schema.require_world(world))
        schema.operate(world, sso.who(request, request.headers.get("X-User")))
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=404, detail={
            "reason": "world_unknown", "world": world, "message": str(exc)})
    return _worlds()


def _refusal(exc: ConfigExplorerError | ColumnStatsError) -> HTTPException:
    status = 409 if exc.code in {
        "stale_base_snapshot", "stale_draft", "stale_revision",
        "conflict_draft", "stale_context", "review_revision_locked",
        "activation_locked", "convergence_mismatch", "convergence_unproven",
    } else 400
    return HTTPException(status_code=status, detail=exc.to_mapping())


def _world_after_write(world) -> None:
    """After a door writes a world's declaration - bootstrap, activate, delete - its schema is
    made (총괄 c23b02aeb ②): without it a branch nothing has translated into yet has no ledger
    and its walk answers 503. The default's tables are the daemon's, so nothing happens."""
    from database.database import engine
    from ledger import schema

    schema.ensure_world(engine, schema.world_names(world))


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
    # 🔴 THE REQUEST'S OWN SESSION, NOT A NEW ONE (S-143, 판정 321). A draft preview states
    # what activating it would make re-run, and counting that needs the database. Opening a
    # second connection here would be the quiet kind of cost 「성능 마진 넉넉하게」 forbids;
    # this is the Session FastAPI already holds for this request.
    db: Session = Depends(get_db),
    world: str | None = Query(default=None)):
    try:
        return _service_for(world).view(
            selection=selection, query=q, page=page, limit=limit,
            reference_limit=reference_limit, expected_context_token=context_token,
            draft_id=draft_id, revision=revision, view_mode=view_mode, db=db)

    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


# ⚰️ `GET /refusals` — 문지기의 «프로세스 카운터»를 내던 라우트. 은퇴(S-114, 판정 223).
#
# 🔴 왜: 운영은 `DECOUPLED=True` 라 번역이 «체인 워커 프로세스»에서 돌고 이 라우트는 «웹
# 프로세스»가 답했다. 즉 「한 번도 번역하지 않은 프로세스」의 카운터를 냈다 — 거절이 나는
# 동안 «0 에 가까운 수»를 그렸다. 단일 프로세스 박스에서만 참이라 아무도 못 봤다.
# 클라 소비자도 «0» 이었다.
#
# ⚠️ S-39 가 이 라우트를 지은 사유(「사유를 내놓는 라우트가 하나도 없어 운영자가 짐작으로
# 시간 선언을 의심했다」)는 «유효하고, 이제 다른 길이 잇는다»: 번역하는 프로세스가 사유를
# 등록부 행에 쓰고(S-114 `store._record_refusals`), `ledger_admin.ingestion_view` 가 그 행을
# 실어 소스 패널이 그린다. 한 진실·한 경로.
#
# 문지기의 프로세스 카운터와 표본은 «그대로»다 — `backfill` 의 실행 보고(`refused_total`,
# `refused_samples`)와 로그 줄이 그 독자다.


@router.get("/columns", dependencies=[Depends(require_admin_token)])
def column_picker(
    relation: str = Query(...),
    combination: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    world: str | None = Query(default=None)):
    """Candidate columns for `relation`, each with how many rows actually carry a value.

    A read, and an EXPENSIVE one by design: the population counts are exact and cost one
    table scan. `estimated_rows` comes back with them so a caller can see what it asked
    for. Nothing is written and no cursor moves.

    `combination` may be repeated to measure one ordering's real uniqueness on the same
    call -- the question that is otherwise answered mid-backfill.
    """
    try:
        return _service_for(world).column_picker(
            db, relation=relation, combination=combination or [])
    except (ColumnStatsError, ConfigExplorerError) as exc:
        raise _refusal(exc) from exc


@router.get("/authoring/schema", dependencies=[Depends(require_admin_token)])
def authoring_schema(world: str | None = Query(default=None)):
    """Every closed list the authoring screen offers, from the validator's own constants.

    The screen owns no copy.  This is what keeps "고를 수 있는 것" correct on the day a
    declaration is added instead of the day somebody notices the dropdown is short.
    """
    return _service_for(world).authoring_schema()


@router.get("/authoring/plan", dependencies=[Depends(require_admin_token)])
def authoring_plan_view(selection: str | None = Query(default=None),
                        world: str | None = Query(default=None)):
    """What one declaration forces (filled, WITH its ground), and what is still asked.

    A read of the authoring FILE, not of the compiled snapshot -- so it answers on a
    blank or half-written root, which is exactly when `/view` cannot.
    """
    try:
        return _service_for(world).authoring(
            selection_prefix=_service_for(world).authoring_prefix(selection))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/authoring/plan", dependencies=[Depends(require_admin_token)])
def authoring_plan_for_draft(payload: dict[str, Any] = Body(...),
                             world: str | None = Query(default=None)):
    """The same plan over the draft's UNSAVED body - `{selection, draft_id, raw}`, raw being
    the editor's text. Writes nothing (총괄 791c0f45e 1ㄴ)."""
    try:
        return _service_for(world).authoring(
            selection_prefix=_service_for(world).authoring_prefix(payload.get("selection")),
            draft_id=str(required_draft_id(payload.get("draft_id") or None)),
            raw=payload.get("raw"))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.get("/deletion-preview", dependencies=[Depends(require_admin_token)])
def deletion_preview(
    targets: list[str] | None = Query(default=None),
    context_token: str | None = Query(default=None),
    world: str | None = Query(default=None)):
    """Name every declaration a deletion would take, BEFORE the author confirms.

    A read: nothing is written and no draft is created, which is why it sits behind the
    same token as `/view` rather than the strict one.
    """
    try:
        return _service_for(world).deletion_preview(
            targets=targets or [], expected_context_token=context_token)
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/test-run", dependencies=[Depends(require_admin_token)])
def test_run(payload: dict[str, Any] = Body(...), world: str | None = Query(default=None)):
    """Run ONE real batch for a declared source and report what it produced.

    🔴 WRITES NOTHING AND MOVES NO CURSOR -- it stops one step before the gate, so no atom
    and no `ledger_cursor` row is touched. It is a POST rather than a GET because it costs
    a page read and a full compile, not because it changes anything.

    Behind the ordinary admin token for the same reason `/columns` is: it is an expensive
    READ. It executes only the trusted implementations the snapshot already names, which
    is exactly what the backfill executes.
    """
    from database.database import engine

    try:
        # 🔴 THE SAMPLE SIZE IS THE REQUEST'S, NOT THE DECLARATION'S (S-92). How many read
        # rows somebody wants to look at is a property of the looking; a declaration cell
        # would make one operator's screen preference part of what everyone else compiles.
        # Clamped in the service, so a caller cannot ask for a page-sized "sample".
        try:
            sample_rows = int(payload.get("sample_rows",
                                          _service_for(world).DEFAULT_SAMPLE_ROWS))
        except (TypeError, ValueError):
            sample_rows = _service_for(world).DEFAULT_SAMPLE_ROWS
        return _service_for(world).test_run(
            engine, source_id=str(payload.get("source_id", "")),
            sample_rows=sample_rows)
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts", dependencies=[Depends(require_admin_token_strict)])
def create_draft(payload: dict[str, Any] = Body(...), world: str | None = Query(default=None)):
    try:
        return _service_for(world).create_draft(
            target_key=str(payload.get("target_key", "")),
            base_snapshot_hash=str(payload.get("base_snapshot_hash", "")),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/bootstrap", dependencies=[Depends(require_admin_token_strict)])
def bootstrap_config(world: str | None = Query(default=None),
                     copy_from: str | None = Query(default=None)):
    """Create the smallest config that validates, so a setup can start from nothing.

    A write, and the only one this screen performs without a draft -- so it is a POST the
    operator confirms, never something the screen does on its own when it notices the file
    is missing. Refuses if anything exists at the path, including a file that fails to
    parse: an unreadable config is somebody's work with a bad comma in it, not an absence.

    `copy_from` - a world whose declaration the new one starts as, once; after that the two
    are independent (총괄 092a6f9e5). Not given: the smallest file that validates.
    """
    seed = None
    if isinstance(copy_from, str) and copy_from.strip():
        from ledger import schema

        try:
            seed = schema.require_world(copy_from.strip()).declaration_root
        except (LookupError, ValueError) as exc:
            raise HTTPException(status_code=404, detail={
                "reason": "world_unknown", "world": copy_from, "message": str(exc)})
    try:
        made = _service_for(world).bootstrap_config(seed_root=seed)
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc
    _world_after_write(world)
    return made


@router.post("/drafts/new", dependencies=[Depends(require_admin_token_strict)])
def create_declaration_draft(payload: dict[str, Any] = Body(...),
                             world: str | None = Query(default=None)):
    """Author a declaration the snapshot has never seen.

    The last hole in the write path: this screen could edit a declaration and could not
    make one, so a new source had to be typed into the file by hand.  Refusals name the
    mistake -- `declaration_exists` (open it instead), `unauthorable_kind` (this screen
    cannot write that section).
    """
    try:
        return _service_for(world).create_declaration_draft(
            kind=str(payload.get("kind", "")),
            canonical_id=str(payload.get("canonical_id", "")),
            base_snapshot_hash=str(payload.get("base_snapshot_hash", "")),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.put("/drafts/{draft_id}", dependencies=[Depends(require_admin_token_strict)])
def save_draft(draft_id: str, payload: dict[str, Any] = Body(...),
               world: str | None = Query(default=None)):
    try:
        return _service_for(world).save_draft(
            draft_id,
            expected_revision=payload.get("expected_revision"),
            raw=payload.get("raw"),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts/{draft_id}/review",
             dependencies=[Depends(require_admin_token_strict)])
def review_draft(draft_id: str, payload: dict[str, Any] = Body(...),
                 world: str | None = Query(default=None)):
    try:
        return _service_for(world).review_draft(
            draft_id, expected_revision=payload.get("expected_revision"))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.post("/drafts/{draft_id}/revise",
             dependencies=[Depends(require_admin_token_strict)])
def revise_draft(draft_id: str, payload: dict[str, Any] = Body(...),
                 world: str | None = Query(default=None)):
    try:
        return _service_for(world).revise_draft(
            draft_id, expected_revision=payload.get("expected_revision"))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.delete("/drafts/{draft_id}",
               dependencies=[Depends(require_admin_token_strict)])
def discard_draft(
    draft_id: str,
    expected_revision: int = Query(...),
    world: str | None = Query(default=None)):
    try:
        return _service_for(world).discard_draft(
            draft_id, expected_revision=expected_revision)
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc


@router.delete("/declarations/{target_key:path}",
               dependencies=[Depends(require_admin_token_strict)])
def delete_declaration(
    target_key: str,
    base_snapshot_hash: str,
    db: Session = Depends(get_db),
    world: str | None = Query(default=None)):
    try:
        from runtime import system_reload
        deleted = _service_for(world).delete_declaration(
            target_key, base_snapshot_hash=base_snapshot_hash,
            reload_callback=lambda: system_reload.reload_system_configs(db))
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc
    _world_after_write(world)
    return deleted


@router.post("/drafts/{draft_id}/activate",
             dependencies=[Depends(require_admin_token_strict)])
def activate_draft(
    draft_id: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    world: str | None = Query(default=None)):
    try:
        # Import at the write boundary, as the sibling handler does.
        from runtime import system_reload
        activated = _service_for(world).activate_draft(
            draft_id,
            expected_revision=payload.get("expected_revision"),
            reload_callback=lambda: system_reload.reload_system_configs(db),
        )
    except ConfigExplorerError as exc:
        raise _refusal(exc) from exc
    _world_after_write(world)
    return activated
