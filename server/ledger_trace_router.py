"""`GET /api/ledger/trace` — the lineage screen's one endpoint.

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
        return ledger_trace.trace(lot, slot, lookup=_lookup_for(db))
    except ledger_trace.ResolverConfigError as exc:
        # A declared-but-broken resolver config is refused at the door and
        # counted, never half-applied (brief §3-1 gate discipline).
        logger.error("ledger resolver config refused: %s", exc)
        raise HTTPException(status_code=503, detail=f"해결기 config 거절: {exc}")
    except Exception as exc:                       # noqa: BLE001 - see below
        # `ledger_events` is created by a separate lane and may not exist yet on
        # a given database. "관계 없음" is an operational fact about THIS box, so
        # it is reported as one (503 + the relation name) rather than as a 500
        # that reads like a code defect.
        text = str(exc)
        if LEDGER_RELATION in text and (
                "does not exist" in text or "UndefinedTable" in text):
            logger.warning("ledger relation missing: %s", LEDGER_RELATION)
            raise HTTPException(
                status_code=503,
                detail=f"원장 테이블 {LEDGER_RELATION} 없음 — 번역기 미착지")
        raise
