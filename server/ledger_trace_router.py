"""`GET /api/ledger/trace` + `GET /api/ledger/coverage` — the lineage screen.

Self-contained `APIRouter` so that registering it in `main.py` costs two lines.
🔴 It MUST be included ABOVE `main.py`'s SPA catch-all `@app.get("/{file_name:path}")`:
FastAPI matches in registration order, and a route registered after the catch-all
is served index.html with a 200 — the same way `/health` used to be, which would
have let a monitor call a dead endpoint alive.

The response shape is pinned by the lead PM and a client lane is being built
against it. Changing it is an escalation, not an edit.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.database import get_db

import finding_kinds
import ledger_kinds
import ledger_lots
import ledger_siblings
import ledger_structure
import ledger_trace
import ledger_walk_contrast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

#: The relation the walk reads. Named here rather than inline because it is the
#: seam: pointing the screen at a materialised projection (week 2, slot-level
#: lineage — 780x inline vs materialised, measured) is this one string plus a
#: lookup class, and touches no resolver code.
LEDGER_RELATION = "ledger_events"

#: The translator's cursor table — the ledger's own registry of who has written
#: into it, and what `GET /coverage` reports as `sources`. Named beside the
#: relation above because the two move together: both are created by
#: `server/migrations/add_ledger_events.py` and both are seams a materialised
#: projection would repoint. (`server/ledger/schema.py` holds the single DDL
#: spelling; these two constants are the READ side's, kept here rather than
#: imported so that including this router does not drag the translator package
#: into the web server's boot — see the runbook §6 note that nothing imports
#: `server/ledger` at boot.)
LEDGER_CURSOR_RELATION = "ledger_translator_cursor"


def _lookup_for(db):
    """A `ClaimLookup` bound to the request's connection.

    The route knows one lookup exists; it does not know it is SQL-shaped beyond
    handing it a connection. Swapping the class here is the entire migration to
    a materialised lookup.
    """
    return ledger_trace.SqlClaimLookup(db.connection(), relation=LEDGER_RELATION)


@router.get("/trace")
def trace_lineage(
    lot: str = Query(..., description="추적 시작 랏"),
    slot: str = Query(None, description="위치(슬롯). 없으면 랏 단위 사슬만"),
    db: Session = Depends(get_db),
):
    """`(lot, slot)`의 혈통 사슬을 홉별 상태와 함께 돌려준다. 읽기 전용.

    🔴 A 200 with an empty `hops` list is not a possible answer. Where the chain
    breaks, the hop that broke and the reason it broke ARE the answer — that is
    what this screen exists for (brief §3-2). The only non-200 outcomes are a
    malformed request (422 from FastAPI) and the ledger relation being absent
    (503, below), and the second one says so instead of returning nothing.
    """
    lot = (lot or "").strip()
    if not lot:
        raise HTTPException(status_code=422, detail="lot 필요")

    try:
        # 🔴 ASK THE CATALOGUE FIRST — do not learn it from an exception.
        # This is the case that sent the product owner to a blank screen on
        # 2026-08-13: `assy_manager` had no `ledger_events` at all.
        #
        # WHAT WAS ACTUALLY MEASURED, because the tempting story is wrong. This
        # branch shipped with NO test, so nothing had ever driven it. Driving it
        # (mutant run, 2026-08-13) shows the previous string match DID fire — but
        # only on the half of its `or` that nothing guarantees. This PostgreSQL
        # speaks Korean, so `"does not exist"` is already dead here:
        #     (psycopg2.errors.UndefinedTable) 오류: "…" 이름의 릴레이션(relation)
        #     이 없습니다
        # It matched on `"UndefinedTable"` instead — a driver class name that
        # appears only because SQLAlchemy's `__str__` prefixes it. Nothing
        # promises that: a bare psycopg2 path, or a change in how SQLAlchemy
        # formats a wrapped error, and the deployment fact silently becomes a 500
        # that reads like a code defect.
        #
        # So the judgement moved to two things that ARE contracts: the catalogue,
        # and SQLSTATE. `to_regclass` returns NULL instead of raising, which also
        # keeps the request's transaction clean — one `UndefinedTable` poisons it
        # and every later statement fails for an unrelated-looking reason.
        if not ledger_trace.relation_exists(db.connection(), LEDGER_RELATION):
            raise _relation_absent()
        return ledger_trace.trace(lot, slot, lookup=_lookup_for(db))
    except ledger_trace.ResolverConfigError as exc:
        # A declared-but-broken resolver config is refused at the door and
        # counted, never half-applied (brief §3-1 gate discipline).
        logger.error("ledger resolver config refused: %s", exc)
        raise HTTPException(status_code=503, detail=f"해결기 config 거절: {exc}")
    except HTTPException:
        raise
    except Exception as exc:                       # noqa: BLE001 - see below
        # BACKSTOP for the race the gate cannot close: the relation is dropped
        # between the catalogue lookup and the walk. Judged on SQLSTATE `42P01`
        # (`undefined_table`), which is the same five characters in every locale
        # and every driver. PROVEN by disabling the gate above and re-running
        # `test_the_trace_route_names_an_absent_ledger_in_a_field_not_in_prose`:
        # it still answered 503 with the structured body, from here.
        if _is_undefined_table(exc):
            raise _relation_absent()
        raise


#: PostgreSQL `undefined_table`. The one fact about a missing relation that is
#: not translated.
SQLSTATE_UNDEFINED_TABLE = "42P01"


def _is_undefined_table(exc) -> bool:
    """True when `exc` (or the driver error SQLAlchemy wrapped) is a 42P01."""
    for candidate in (getattr(exc, "orig", None), exc):
        if getattr(candidate, "pgcode", None) == SQLSTATE_UNDEFINED_TABLE:
            return True
    return False


def _relation_absent() -> HTTPException:
    """The absent-relation refusal, in ONE spelling for both raisers.

    🔴 THE BODY IS STRUCTURED, NOT PROSE. Ruling R-2026-08-13-C: `reason` is
    prose for humans, and any fact the screen must BRANCH on goes out as a
    structured field. So the client reads `detail.reason`, the operator reads
    `detail.message`, and nobody has to parse Korean to tell "not deployed" from
    "no such lot". `state` repeats `GET /coverage`'s vocabulary on purpose — one
    word means one thing across both endpoints.
    """
    logger.warning("ledger relation missing: %s", LEDGER_RELATION)
    return HTTPException(status_code=503, detail={
        "reason": ledger_trace.REASON_RELATION_ABSENT,
        "state": "absent",
        "relation": LEDGER_RELATION,
        "message": (f"원장 테이블 {LEDGER_RELATION} 없음 — 마이그레이션 미실행 "
                    f"(server/migrations/add_ledger_events.py)"),
    })


@router.get("/siblings")
def ledger_siblings_route(
    finding: str = Query(None, description="관측 종류. 미지정 시 등록부의 기본값"),
    mode: str = Query("intersection", description="intersection | contrast"),
    window: str = Query(None, description="7d 또는 YYYY-MM-DD..YYYY-MM-DD"),
    limit: int = Query(None, description="요인 행 수 상한"),
    min_support: int = Query(None, description="요인 행의 최소 발견 건수"),
    axes: str = Query(None, description="축 이름 CSV. 미지정 시 선언된 전부"),
    scope: str = Query(None, description="랏 마킹 — <축이름>:<값>[,<값>...]. "
                                         "지정하면 걷기 대조로 전환"),
    db: Session = Depends(get_db),
):
    """「이 결함들이 공유하는 요인은?」과 「난 쪽과 안 난 쪽은 뭐가 다른가?」.

    🔴 ONE endpoint, TWO framings — `mode` is a parameter and never a second route.
    The row shape is identical in both modes, which is what lets the console put them
    side by side; a decoy factor tops `intersection` and is dropped by `contrast`, and
    that difference is only legible if the two answers are the same shape.

    🔴 `finding` IS A PARAMETER FROM THE FIRST LINE. `void` is the registry's default
    value, not a branch — `server/finding_kinds.py` is where a kind is declared, and a
    `finding_kind='void'` literal anywhere below the default would mean the
    generalisation had been lost (brief §0 [일반화]).

    Read-only. Every non-200 is a malformed request (422) or an undeployed relation,
    and the second one is answered as a 200 with `state: "absent"` rather than as an
    error — an absent table is one of this endpoint's ANSWERS, exactly as it is for
    `GET /coverage`.
    """
    try:
        # 🔴 `scope` SWITCHES THE ENGINE, and the response says which one answered.
        # Marking lots turns the question from 「난 쪽과 안 난 쪽은 뭐가 다른가」 into
        # 「이 랏들과 정상 양산은 뭐가 다른가」, and the second one has no item list:
        # the candidates are whatever the walk touches (owner, 2026-08-14: 「항목에
        # 가정이 들어가잖아」). Still ONE endpoint — `engine` is a field, not a route,
        # because a second endpoint is how two framings of one question stop being
        # comparable side by side.
        if (scope or "").strip():
            return ledger_walk_contrast.contrast(
                db.connection(), kind=finding, scope=scope, window=window,
                limit=limit, min_support=min_support)
        answer = ledger_siblings.siblings(
            db.connection(), kind=finding, mode=mode, window=window,
            limit=limit, min_support=min_support, axes=axes)
        answer.setdefault("engine", "axes")
        return answer
    except ledger_walk_contrast.WalkRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)
    except ledger_siblings.SiblingsRequestError as exc:
        # The body is STRUCTURED (ruling R-2026-08-13-C): the client branches on
        # `detail.reason`, the operator reads `detail.message`, and nobody parses Korean
        # to tell an unknown kind from a malformed window.
        raise HTTPException(status_code=422, detail=exc.detail)
    except ledger_siblings.SiblingsConfigError as exc:
        logger.error("siblings factor geometry refused: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "axes_config_refused", "message": f"요인 선언 거절: {exc}"})
    except finding_kinds.FindingKindError as exc:
        logger.error("finding-kind registry refused: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "finding_kind_registry_refused",
            "message": f"관측 종류 등록부 거절: {exc}"})
    except Exception as exc:                       # noqa: BLE001 - same backstop as trace
        if _is_undefined_table(exc):
            # The race the catalogue gate cannot close: a relation dropped between the
            # `to_regclass` lookup and the query. Judged on SQLSTATE, which is the same
            # five characters in every locale and every driver.
            raise _relation_absent()
        raise


@router.get("/kinds")
def ledger_kind_catalog(db: Session = Depends(get_db)):
    """어떤 불량 종류를 물을 수 있는지 — 화면이 로드할 때 한 번 묻는다. 읽기 전용.

    🔴 200 AND A `state` FOR AN ABSENT OR EMPTY SET OF OBSERVATION RELATIONS, never an
    error - the same rule `GET /coverage` follows, and the same three words. The one
    non-200 is a registry that cannot be read (503), which is a deployment fact and not
    an answer about kinds.

    🔴 EVERY DECLARED KIND IS LISTED, INCLUDING THE ONES WITH ZERO OBSERVATIONS. A kind
    hidden for having no rows cannot be distinguished from a kind that does not exist,
    and the operator would read the second from the first.
    """
    try:
        return ledger_kinds.catalog(db.connection())
    except finding_kinds.FindingKindError as exc:
        logger.error("finding-kind registry refused: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "finding_kind_registry_refused",
            "message": f"관측 종류 등록부 거절: {exc}"})
    except Exception as exc:                       # noqa: BLE001 - same backstop
        if _is_undefined_table(exc):
            # The race the catalogue gate cannot close: a relation dropped between the
            # `to_regclass` lookup and the count. Judged on SQLSTATE.
            raise _relation_absent()
        raise


@router.get("/structure")
def ledger_structure_view(
    window: str = Query(None, description="7d 또는 YYYY-MM-DD..YYYY-MM-DD. 건수만 좁힌다"),
    db: Session = Depends(get_db),
):
    """온톨로지 «구조» — 어떤 개체가 어떤 관계로 이어지고, 어디에 데이터가 얼마나 있나.

    🔴 유형 수준이다. 랏·웨이퍼·보이드 같은 «인스턴스»는 한 건도 나오지 않는다 —
    그건 `GET /trace`의 화면이고 이건 그 보완이다.

    🔴 200 AND A `state` FOR AN ABSENT OR EMPTY LEDGER. The DECLARED half of the graph is
    served in all three states, because a box with no `ledger_events` at all still has an
    ontology — and somebody staring at a blank screen is exactly who needs to see it.

    🔴 NOTHING IN THE RESPONSE IS HAND-DRAWN. Nodes and edges are generated from
    `server/ledger/vocabulary.py` (declared) merged with one `GROUP BY` over the ledger
    (observed). A predicate added to the vocabulary appears here with no edit to any
    route, and a shape observed that nothing declares appears as `undeclared` rather than
    being dropped.

    `window` narrows the COUNTS only; every declared edge stays on the screen at
    `atoms: 0`. Read-only.
    """
    try:
        return ledger_structure.structure(db.connection(), window=window)
    except ledger_siblings.SiblingsRequestError as exc:
        # `window` is parsed by ONE spelling (`ledger_siblings.parse_window`), so a
        # malformed window is refused here with the same structured body and the same
        # `reason` token the siblings route uses. A client branches on the token.
        raise HTTPException(status_code=422, detail=exc.detail)
    except ledger_structure.StructureError as exc:
        logger.error("ledger structure declaration unreadable: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "vocabulary_unreadable", "message": str(exc)})
    except ledger_trace.ResolverConfigError as exc:
        logger.error("ledger resolver config refused: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "resolver_config_refused", "message": f"해결기 config 거절: {exc}"})
    except Exception as exc:                       # noqa: BLE001 - same backstop
        if _is_undefined_table(exc):
            # The race the catalogue gate cannot close: a relation dropped between the
            # `to_regclass` lookup and the census. Judged on SQLSTATE.
            raise _relation_absent()
        raise


def _lot_grid_refusals(exc):
    """The refusals `lots` and `lot_map` share, in ONE spelling for both routes.

    Bodies are STRUCTURED (ruling R-2026-08-13-C): the client branches on
    `detail.reason`, the operator reads `detail.message`, and nobody parses Korean
    to tell an unknown aggregate from an unknown row axis.
    """
    if isinstance(exc, ledger_lots.LotGridRequestError):
        return HTTPException(status_code=422, detail=exc.detail)
    if isinstance(exc, ledger_siblings.SiblingsRequestError):
        return HTTPException(status_code=422, detail=exc.detail)
    if isinstance(exc, ledger_siblings.SiblingsConfigError):
        logger.error("lot grid axis geometry refused: %s", exc)
        return HTTPException(status_code=503, detail={
            "reason": "axes_config_refused", "message": f"요인 선언 거절: {exc}"})
    if isinstance(exc, finding_kinds.FindingKindError):
        logger.error("finding-kind registry refused: %s", exc)
        return HTTPException(status_code=503, detail={
            "reason": "finding_kind_registry_refused",
            "message": f"관측 종류 등록부 거절: {exc}"})
    return None


@router.get("/lots")
def ledger_lot_grid(
    columns: str = Query(None, description="열 명세 CSV — <종류>:<집계>. 미지정 시 선언된 기본값"),
    by: str = Query(None, description="행 축 이름. 미지정 시 선언된 기본 축"),
    window: str = Query(None, description="7d 또는 YYYY-MM-DD..YYYY-MM-DD"),
    kind: str = Query(None, description="행 축·기하를 고를 때 기준이 되는 종류"),
    limit: int = Query(None, description="행 수 상한"),
    offset: int = Query(None, description="행 오프셋"),
    db: Session = Depends(get_db),
):
    """놀라움 장치 — 행 = 선언된 축, 열 = {항목 × 집계}. 읽기 전용.

    🔴 「미검사」와 「0」은 다른 답이고 `cells[].state`가 그 둘을 가른다. 클라가 0에서
    미검사를 «추론»하지 않는다 — 실측으로 랏의 20.6%만 검사되므로, 랏 크기를 분모로
    쓰면 5배 틀린다.

    🔴 지표 목록은 이 파일에도 라우트에도 없다. 항목은 `finding_kinds` 등록부,
    집계는 `ledger_lots.AGGREGATES`, 행 축은 `siblings_axes.json`이 선언한다 —
    종류를 하나 선언하면 열 계열이 통째로 늘고 여기는 한 줄도 안 바뀐다.

    🔴 스캔이 상한을 넘으면 window가 «강제»되고 응답이 그렇게 말한다
    (`window.forced` + `forced_reason`). 한 달 치를 전 기간으로 표기하는 화면은 없다.
    """
    try:
        return ledger_lots.lots(db.connection(), columns=columns, by=by, window=window,
                                kind=kind, limit=limit, offset=offset)
    except Exception as exc:                       # noqa: BLE001 - mapped below
        mapped = _lot_grid_refusals(exc)
        if mapped is not None:
            raise mapped
        if _is_undefined_table(exc):
            # The race the catalogue gate cannot close: a relation dropped between the
            # `to_regclass` lookup and the scan. Judged on SQLSTATE.
            raise _relation_absent()
        raise


@router.get("/lot_map")
def ledger_lot_map(
    row: str = Query(..., description="마킹된 행의 값 (예: 본딩 랏 id)"),
    kind: str = Query(None, description="관측 종류. 미지정 시 등록부의 기본값"),
    by: str = Query(None, description="행 축 이름. /lots와 같은 축을 넘길 것"),
    slot: str = Query(None, description="슬롯. 프레임이 슬롯마다 다르므로 필요"),
    window: str = Query(None, description="7d 또는 YYYY-MM-DD..YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """마킹된 행의 불량 칩을 «선언된 축마다» 투영한다. 읽기 전용.

    🔴 좌표는 오리진 기준 «칸수»다. 피치를 곱하지 않고 mm를 내지 않는다.

    🔴 닿지 않는 축은 숨기지 않고 `state: "unreachable"` + `reason`으로 답한다.
    코어축이 지금 그 상태다 — `bonding_log.core_lot`·`cx`·`cy`가 357,796행 전부
    NULL이라 투영할 좌표 자체가 없고, 닿으려면 새 옆조인이 필요한데 그건
    R-2026-08-14-D 위반이다. 「없으면 없다고」.

    ⚠️ 한 랏 = 한 프레임이 아니다. 슬롯마다 격자 치수가 다르게 등록돼 있어
    `slot` 없이는 그리지 않고 고를 수 있는 슬롯 목록을 답한다.
    """
    try:
        return ledger_lots.lot_map(db.connection(), row=row, kind=kind, by=by,
                                   slot=slot, window=window)
    except Exception as exc:                       # noqa: BLE001 - mapped below
        mapped = _lot_grid_refusals(exc)
        if mapped is not None:
            raise mapped
        if _is_undefined_table(exc):
            raise _relation_absent()
        raise


@router.get("/coverage")
def ledger_coverage(db: Session = Depends(get_db)):
    """이 박스의 원장이 «무엇을 덮고 있는지» — 화면이 로드할 때 한 번 묻는다.

    🔴 200 AND A `state`, NEVER AN ERROR, FOR AN ABSENT OR EMPTY LEDGER. Those
    are the two answers this endpoint exists to give; raising for them would put
    the operator back in front of the same blank screen with a different colour.

        absent  마이그레이션 미실행 — 배포 문제
        empty   테이블은 있고 원자 0 — 백필 미실행
        ready   추적 가능

    The two remaining "nothings" — an unknown lot, and a known lot with no
    lineage claim — are properties of one lot rather than of the box, and
    `GET /trace` already answers them apart (`[unknown_subject]` vs
    `[root] … (register 있음)`). This endpoint deliberately does not duplicate
    that judgement; it tells the screen WHICH WORLD it is in, so an
    `[unknown_subject]` against `state: "empty"` reads as "백필 미실행" and the
    same hop against `state: "ready"` reads as "없는 랏".
    """
    try:
        return ledger_trace.coverage(
            db.connection(), relation=LEDGER_RELATION,
            cursor_relation=LEDGER_CURSOR_RELATION)
    except ledger_trace.ResolverConfigError as exc:
        logger.error("ledger resolver config refused: %s", exc)
        raise HTTPException(status_code=503, detail=f"해결기 config 거절: {exc}")
