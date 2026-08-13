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

import ledger_trace

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
