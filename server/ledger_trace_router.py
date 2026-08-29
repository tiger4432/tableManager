"""The ledger read routes — ten of them, and none is the pair this line used to name.

`/api/ledger/trace` and `/api/ledger/coverage` retired; what this module opens today is
`subgraph`, `subgraph/table`, `siblings`, `trends`, `composition`, `selection/resolve`,
`kinds`, `declaration`, `structure` and `lot_map`.

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

from ledger_api import ledger_subgraph
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










# `GET /api/ledger/explore_entity` was retired 2026-08-23 (round 3, "v1 retirement").
# `GET /api/ledger/subgraph` answers the same question and keeps competing claims visible
# instead of letting a subgraph projection cover the facts. Measured before removal: zero
# references anywhere in `client2/` - source or built bundles - which is why this one could
# go alone while `trace`, `explore` and `structure` wait for a client round.


def _subgraph_contract_state(connection):
    """Name missing deployment pieces before the evidence query can scan slowly."""
    rows = ledger_trace._fetch(connection, """
        SELECT
          EXISTS (SELECT 1 FROM pg_attribute
                  WHERE attrelid = to_regclass(%(relation)s)
                    AND attname = 'source_event_id'
                    AND attnum > 0 AND NOT attisdropped),
          EXISTS (SELECT 1 FROM pg_attribute
                  WHERE attrelid = to_regclass(%(relation)s)
                    AND attname = 'source_event_state'
                    AND attnum > 0 AND NOT attisdropped),
          to_regclass('idx_ledger_source_event') IS NOT NULL,
          to_regclass('idx_ledger_object_entity') IS NOT NULL
    """, {"relation": LEDGER_RELATION})
    names = ("source_event_id", "source_event_state",
             "idx_ledger_source_event", "idx_ledger_object_entity")
    return [name for name, present in zip(names, rows[0]) if not present]


@router.get("/subgraph")
def evidence_subgraph(
    node_id: str = Query(..., alias="id",
                         description="Entity/Event/Claim/Collection/Point/Value/Action의 불투명 id"),
    hops: int = Query(12, ge=1, le=40, description="증거 그래프 탐색 깊이"),
    direction: str = Query("both", pattern="^(outgoing|incoming|both)$",
                           description="Entity 주장 방향; 구조 엣지는 항상 양쪽 보존"),
    node_limit: int = Query(400, ge=10, le=1000, description="응답 노드 상한"),
    edge_limit: int = Query(
        1200, ge=20, le=ledger_subgraph.MAX_EDGE_LIMIT,
        description="응답 엣지 상한"),
    positive: list[str] | None = Query(
        None, description="추가 관측 씨앗. `id` 는 항상 positive 다"),
    negative: list[str] | None = Query(
        None, description="대조군 씨앗 — 봤는데 안 난 주어. 목록에 없는 주어는 미검사이지 대조군이 아니다"),
    follow: list[str] | None = Query(
        None, description="이 술어만 따라간다. 없으면 «전부» — 오늘 동작 그대로"),
    backbone_hops: int = Query(
        ledger_subgraph.DEFAULT_BACKBONE_HOPS, ge=0, le=40,
        description=("같은 자재를 따라가는 걸음에 주는 «별도» 예산. "
                     "양 끝이 «둘 다 dynamic» 인 걸음만 여기서 빠진다 — "
                     "정적/동적은 선언의 `class` 가 정한다. 0 이면 오늘과 같다")),
    db: Session = Depends(get_db),
):
    """어느 증거 노드에서든 Entity–Event–Claim 서브그래프를 답한다."""
    # 🔴 AN UNDECLARED PREDICATE IS REFUSED, NOT ANSWERED WITH AN EMPTY GRAPH. A filter that
    # can never match returns exactly what "there is nothing here" returns, and the caller
    # cannot tell a typo from a fact -- the shape this repo spent a night removing from four
    # other layers. The declared set is read from the vocabulary, never restated here.
    if follow:
        followable = _followable_predicates()
        unknown = sorted(set(follow) - followable)
        if unknown:
            raise HTTPException(status_code=422, detail={
                "reason": "predicate_not_declared", "unknown": unknown,
                "declared": sorted(followable),
                "message": "선언에 없는 술어입니다: " + ", ".join(unknown),
            })
    try:
        return _evidence_graph(
            db.connection(), node_id=_signed_start(node_id, positive, negative),
            hops=hops, direction=direction,
            node_limit=node_limit, edge_limit=edge_limit, follow=follow,
            backbone_hops=backbone_hops)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "reason": "subgraph_request_invalid", "message": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:                       # noqa: BLE001 - DDL race backstop
        if _is_undefined_table(exc):
            raise _relation_absent()
        raise


def _signed_start(node_id, positive, negative):
    """`id` alone stays exactly the argument it has always been.

    🔴 The signed lists widen it ONLY when at least one of them arrives, so a request that
    names neither reaches `subgraph()` with the same single id it did before.  `id` is
    always positive: the response's `seed` keeps pointing at it, and a walk of controls
    with nothing marked is not a question anyone asks.
    """
    if not positive and not negative:
        return node_id
    return {"positive": [node_id] + list(positive or []),
            "negative": list(negative or [])}


def _followable_predicates():
    """Every predicate a caller may name in `follow` -- read from the DECLARATION, only.

    🔴 THIS USED TO BE A UNION with a code-held word list, and the union is what the v1
    retirement removes. The code half named three predicates (`transferred`, `measured`,
    `has_param`) that the declaration does not declare, so naming them in `follow` was
    accepted and then walked nothing -- the caller got a silent empty instead of a refusal.
    Now the declaration is the only authority and those three answer 422, which is the
    point: a word you may follow is a word the ledger says it emits.

    Read, never restated -- adding a predicate to the declaration makes it followable
    without editing this file, and that is the only way to add one.

    🔴 AND A REFERENCE EDGE IS DECLARED TOO. `entities.<type>.references[].edge`
    (today: `in_container`, die -> wafer / die -> dtjob) has no atoms, so it is not in
    `vocabulary` -- but it is the bridge a die crosses to reach its wafer, and refusing to
    let a caller NAME it meant they could not narrow a walk without cutting that bridge.
    `follow` stays one parameter; what widened is the list it is checked against.
    """
    names = set()
    try:
        from ledger import config as _config
        declared = (_config.load() or {}).get("vocabulary") or {}
        names |= {str(key).split("@", 1)[0] for key in declared}
    except Exception:      # an unreadable declaration refuses everything rather than guessing
        return set()
    return names


def _static_types():
    """Entity types the declaration marks `class: "static"` -- names, not happenings.

    🔴 SAME SHAPE AS `_followable_predicates`, and for the
    same reason: the declaration is the only authority, so an entity becomes static by
    being declared static and never by an edit here. An unreadable declaration returns the
    EMPTY set, which is exactly today's walk rather than a guess about which types are
    hubs.

    Bare names, because the declaration versions its ids (`defect_kind@1`) and a projected
    node carries the bare one.
    """
    try:
        from ledger import config as _config
        declared = (_config.load() or {}).get("entities") or {}
    except Exception:
        return set()
    return {str(key).split("@", 1)[0] for key, rule in declared.items()
            if (rule or {}).get("class") == "static"}


def _static_step_predicates():
    """Predicates whose BOTH ends are declared static -- the only ones a static node may be
    expanded along.

    🔴 SAME SHAPE AS `_static_types`, and it exists because the policy it serves was
    enforced one layer too late. `s -> s` is allowed and `s -> d` is not; the walk knew
    that and dropped every `s -> d` atom in the projection -- AFTER the query had fetched
    it and charged it to the claim budget.

    MEASURED 2026-08-29, seeded at one defect with `hops=4`:
        with    `of_kind`  ->  claims 6,000 (the ceiling) ·  13 nodes · stopped at hop 2
        without `of_kind`  ->  claims   371               · 315 nodes · reached hop 4
    `defect_kind` carries 103,841 atoms against ONE distinct object, so the walk was
    buying all of them to throw them away, and the walk died two hops from its seed.

    Today this set is `{"leads_to"}` -- the mechanism chain, quantity to quantity, which is
    exactly the step the `s -> s` allowance was written for. Read, never restated: a new
    static-to-static predicate widens it with no edit here, and an unreadable declaration
    returns the EMPTY set, which expands no static node at all.
    """
    try:
        from ledger import config as _config
        declared = _config.load() or {}
    except Exception:
        return set()
    entities = declared.get("entities") or {}
    static = {str(key).split("@", 1)[0] for key, rule in entities.items()
              if (rule or {}).get("class") == "static"}
    names = set()
    for key, rule in (declared.get("vocabulary") or {}).items():
        subjects = [str(item).split("@", 1)[0] for item in ((rule or {}).get("subjects") or [])]
        targets = [str(item).split("@", 1)[0]
                   for item in (((rule or {}).get("object") or {}).get("types") or [])]
        if not subjects or not targets:
            continue
        if all(item in static for item in subjects) and all(item in static for item in targets):
            names.add(str(key).split("@", 1)[0])
    return names


def _evidence_graph(connection, *, node_id, hops, direction,
                    node_limit, edge_limit, follow=None,
                    backbone_hops=ledger_subgraph.DEFAULT_BACKBONE_HOPS):
    if not ledger_trace.relation_exists(connection, LEDGER_RELATION):
        raise _relation_absent()
    missing = _subgraph_contract_state(connection)
    if missing:
        raise HTTPException(status_code=503, detail={
            "reason": "source_event_projection_not_deployed",
            "state": "not_deployed", "missing": missing,
            "message": ("Source Event 그래프 마이그레이션이 필요합니다: "
                        "server/migrations/add_ledger_source_events.py --apply"),
        })
    return ledger_subgraph.subgraph(
        node_id, ledger_subgraph.SqlEvidenceLookup(
        connection, relation=LEDGER_RELATION),
        hops=hops, direction=direction,
        node_limit=node_limit, edge_limit=edge_limit, follow=follow,
        backbone_hops=backbone_hops, static_types=_static_types(),
        static_follow=_static_step_predicates())




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














@router.get("/declaration")
def ledger_declaration_catalog():
    """무엇을 물을 수 있나 — 노드 타입 · 그 타입의 키 · 따라갈 술어 · 모을 노드 종류.

    🔴 데이터 라우트가 «아니다». 원장을 한 줄도 읽지 않는다 — 답은 «선언»이고, 그래서
    선언이 바뀌면 이 답이 바뀌고 코드는 안 바뀐다. 걷기 검색창의 드롭다운 넷이 여기서 나온다.

    🔴 목록을 여기 다시 적지 않는다. 선언에서 «읽어» 내보내므로, 술어를 선언에서 하나 지우면
    이 답도 하나 줄어든다. 코드에 사본이 있으면 안 줄어들고, 그게 이 라우트가 틀렸다는 판별식이다.

    🔴 `subjects` 를 «그대로» 실어 보낸다. 「고른 타입에서 나갈 수 있는 술어」를 좁히는 것은
    화면이 만드는 규칙이 아니라 선언이 이미 들고 있는 사실이다. 좁히기를 서버가 «대신»
    해 주면 화면은 「왜 이것만 나오나」를 물을 수 없게 된다.

    🔴 빈 목록은 «답»이지 오류가 아니다. 목적어로만 나오는 타입(recipe)은 나가는 술어가 없고,
    그것을 404 나 500 으로 말하면 「없다」와 「고장」이 한 낱말이 된다. 읽을 수 없는 선언만
    503 이며, 그건 배포 사실이지 물음에 대한 답이 아니다.
    """
    try:
        from ledger import config as _config
        declared = _config.load() or {}
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"선언을 읽지 못했습니다: {exc}"})

    entities = [
        {"type": name, "keys": list((spec or {}).get("keys") or [])}
        for name, spec in sorted((declared.get("entities") or {}).items())
    ]
    predicates = [
        {"name": name,
         "subjects": list((spec or {}).get("subjects") or []),
         "object": (spec or {}).get("object") or {},
         "origin": "vocabulary"}
        for name, spec in sorted((declared.get("vocabulary") or {}).items())
    ]
    # 🔴 THE SAME ARRAY, THE SAME SHAPE. A reference edge is followable, so the
    # catalogue must offer it - and in `predicates[]` rather than a second array, because a
    # client that had to read two arrays would grow a branch. `origin` tells them apart for
    # anyone who needs it; nobody has to look. `subjects` stays VERSIONED (`die@1`) because
    # the client filters options by subject and a bare spelling would match nothing.
    return {
        "state": "ready" if entities else "empty",
        "entities": entities,
        "predicates": predicates,
    }










