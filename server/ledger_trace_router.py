"""`GET /api/ledger/trace` + `GET /api/ledger/coverage` — the lineage screen.

Self-contained `APIRouter` so that registering it in `main.py` costs two lines.
🔴 It MUST be included ABOVE `main.py`'s SPA catch-all `@app.get("/{file_name:path}")`:
FastAPI matches in registration order, and a route registered after the catch-all
is served index.html with a 200 — the same way `/health` used to be, which would
have let a monitor call a dead endpoint alive.

The response shape is pinned by the lead PM and a client lane is being built
against it. Changing it is an escalation, not an edit.
"""

import csv
import io
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from database.database import get_db

from ledger_api import finding_kinds
import enrichment_actions
from ledger_api import ledger_composition
from ledger_api import ledger_kinds
import ledger_lots
from ledger_api import ledger_selection
from ledger_api import ledger_siblings
import ledger_structure
from ledger_api import ledger_subgraph
import ledger_trace
from ledger_api import ledger_trends
from ledger_api import ledger_walk_contrast

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
    include_values: bool = Query(True, description="값 목적어를 Value 노드로 표시"),
    observations: str = Query(
        "summary", pattern="^(summary|claims)$",
        description="summary=Finding Collection으로 접기, claims=개별 관측 펼치기"),
    include_actions: bool = Query(
        True, alias="enrich_actions",
        description="관련된 미완 Enrichment를 terminal Action 노드로 투영"),
    node_limit: int = Query(400, ge=10, le=1000, description="응답 노드 상한"),
    edge_limit: int = Query(1200, ge=20, le=3000, description="응답 엣지 상한"),
    shape: str = Query("graph", pattern="^(graph|tables)$",
                       description="graph 또는 Spotfire/Excel용 tables"),
    property_limit: int = Query(10000, ge=100, le=20000,
                                description="tables.properties 행 상한"),
    positive: list[str] | None = Query(
        None, description="추가 관측 씨앗. `id` 는 항상 positive 다"),
    negative: list[str] | None = Query(
        None, description="대조군 씨앗 — 봤는데 안 난 주어. 목록에 없는 주어는 미검사이지 대조군이 아니다"),
    collect: str | None = Query(
        None, description="산출을 노드 종류 하나로 좁혀 순위와 최상위 집합을 낸다. 없으면 순위를 내지 않는다"),
    follow: list[str] | None = Query(
        None, description="이 술어만 따라간다. 없으면 «전부» — 오늘 동작 그대로"),
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
        graph = _evidence_graph(
            db.connection(), node_id=_signed_start(node_id, positive, negative),
            hops=hops, direction=direction, include_values=include_values,
            node_limit=node_limit, edge_limit=edge_limit,
            observation_mode=observations, collect=collect, follow=follow,
            action_lookup=(enrichment_actions.SqlEnrichmentActionLookup(db)
                           if include_actions else None))
        return (ledger_subgraph.tabular_projection(graph, property_limit)
                if shape == "tables" else graph)
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
    """Every predicate a caller may name in `follow` -- the CODE set and the LIVE declaration.

    🔴 NEITHER ONE ALONE IS THE AUTHORITY, which is why this is a union and not a lookup.
    MEASURED 2026-08-25: `vocabulary.all_predicates()` returns the v1 code list of thirteen
    and `config_predicates()` is empty, so a check against it alone refuses `bonded_from`,
    `inspected`, `transfer` and `has_netdie` -- four predicates holding 151,321 atoms, one of
    them the edge this filter exists to follow. The live declaration alone misses the v1 names
    (`transferred`, `measured`, `has_param`) that are still in the ledger.

    The union covers all thirteen predicates the ledger actually holds, and still refuses a
    typo, which is the whole point of refusing. Read, never restated: adding a predicate to
    either source makes it followable without editing this file.
    """
    from ledger import vocabulary as _vocabulary
    names = set(_vocabulary.all_predicates())
    try:
        from ledger import config as _config
        declared = (_config.load() or {}).get("vocabulary") or {}
        names |= {str(key).split("@", 1)[0] for key in declared}
    except Exception:      # an unreadable declaration must not widen or narrow the code set
        pass
    return names


def _evidence_graph(connection, *, node_id, hops, direction, include_values,
                    node_limit, edge_limit, observation_mode="summary",
                    action_lookup=None, collect=None, follow=None):
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
        hops=hops, direction=direction, include_values=include_values,
        node_limit=node_limit, edge_limit=edge_limit,
        observation_mode=observation_mode, action_lookup=action_lookup,
        collect=collect, follow=follow)


def _csv_safe(value):
    """Prevent spreadsheet formula execution without stringifying real numbers."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@router.get("/subgraph/table")
def evidence_subgraph_table(
    node_id: str = Query(..., alias="id", description="불투명 그래프 노드 id"),
    table: str = Query("nodes", pattern="^(nodes|edges|properties)$"),
    output_format: str = Query("json", alias="format", pattern="^(json|csv)$"),
    hops: int = Query(12, ge=1, le=40),
    direction: str = Query("both", pattern="^(outgoing|incoming|both)$"),
    include_values: bool = Query(True),
    observations: str = Query("summary", pattern="^(summary|claims)$"),
    include_actions: bool = Query(True, alias="enrich_actions"),
    node_limit: int = Query(400, ge=10, le=1000),
    edge_limit: int = Query(1200, ge=20, le=3000),
    property_limit: int = Query(10000, ge=100, le=20000),
    positive: list[str] | None = Query(
        None, description="추가 관측 씨앗. `id` 는 항상 positive 다"),
    negative: list[str] | None = Query(
        None, description="대조군 씨앗. 목록에 없는 주어는 미검사다"),
    db: Session = Depends(get_db),
):
    """Spotfire/Excel이 직접 소비할 한 장표를 JSON 또는 UTF-8 CSV로 답한다."""
    try:
        graph = _evidence_graph(
            db.connection(),
            node_id=_signed_start(node_id, positive, negative),
            hops=hops, direction=direction,
            include_values=include_values, node_limit=node_limit,
            edge_limit=edge_limit, observation_mode=observations,
            action_lookup=(enrichment_actions.SqlEnrichmentActionLookup(db)
                           if include_actions else None))
        projection = ledger_subgraph.tabular_projection(graph, property_limit)
        selected = projection["tables"][table]
        body = {
            "schema_version": projection["schema_version"],
            "state": projection["state"], "generated_at": projection["generated_at"],
            "seed_id": projection["seed_id"], "table": table,
            "columns": selected["columns"], "rows": selected["rows"],
            "walk": projection["walk"], "limits": projection["limits"],
            "truncated": projection["truncated"],
            "provenance": projection["provenance"],
        }
        if output_format == "json":
            return body
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream, fieldnames=selected["columns"], extrasaction="ignore",
            lineterminator="\r\n")
        writer.writeheader()
        for row in selected["rows"]:
            writer.writerow({key: _csv_safe(row.get(key))
                             for key in selected["columns"]})
        csv_bytes = ("\ufeff" + stream.getvalue()).encode("utf-8")
        return Response(
            content=csv_bytes, media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition":
                    f'attachment; filename="ledger_subgraph_{table}.csv"',
                "X-Ledger-Generated-At": str(projection["generated_at"] or ""),
            })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "reason": "subgraph_request_invalid", "message": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:                       # noqa: BLE001 - DDL race backstop
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




@router.get("/trends")
def ledger_trends_route(
    kinds: str = Query(None, description="불량 종류 CSV. 미지정 시 선언된 전부"),
    window: str = Query(None, description="기본 90d, 최대 366일"),
    cursor: str = Query(None, description="Trend Table keyset cursor"),
    limit: int = Query(None, description="표 행 수, 최대 200"),
    max_points: int = Query(None, description="series별 표시점 상한, 최대 500"),
    grain: str = Query(None, description="분석 grain 선언 JSON. 미지정 시 서버 기본"),
    db: Session = Depends(get_db),
):
    """여러 불량 series와 Trend Table을 한 stable marking 계약으로 답한다.

    ``limit``와 ``max_points``는 표시 예산이지 도메인 cardinality가 아니다. 종류와
    subtype은 가변 길이 컬렉션이며, 표는 offset이 아니라 keyset cursor로 잇는다.

    ``grain``은 응답이 늘 «내보내던» 그 객체다. 이제 입력이기도 하며 응답은 받은 것을
    되비춘다. 축마다 표현이 «둘»인 이유는 분모가 스캔 관계의 컬럼이고 분자는 원자 안의
    경로이기 때문이다 — 어느 자리를 읽는지 선언하지 않으면 셀 수 없는 원장이 있다.
    """
    try:
        return ledger_trends.trends(
            db.connection(), kinds=kinds, window=window, cursor=cursor,
            limit=limit, max_points=max_points, grain=grain)
    except ledger_trends.TrendRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)
    except ledger_siblings.SiblingsRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)
    except finding_kinds.FindingKindError as exc:
        raise HTTPException(status_code=422, detail={
            "reason": "unknown_finding_kind", "message": str(exc)})
    except Exception as exc:                       # noqa: BLE001 - same SQLSTATE backstop
        if _is_undefined_table(exc):
            raise _relation_absent()
        raise


@router.get("/composition")
def ledger_composition_route(
    final_chip_id: str = Query(..., description="최종 CHIP 안정 식별자"),
    window: str = Query(None, description="기본 365d, 최대 730일"),
    db: Session = Depends(get_db),
):
    """최종 CHIP을 구성한 모든 component/DT/TRANSFER 분기를 역추적한다."""
    try:
        return ledger_composition.composition(
            db.connection(), final_chip_id=final_chip_id, window=window)
    except ledger_composition.CompositionRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)
    except ledger_siblings.SiblingsRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)
    except Exception as exc:                       # noqa: BLE001
        if _is_undefined_table(exc):
            raise _relation_absent()
        raise


@router.post("/selection/resolve")
def ledger_selection_resolve_route(
    payload: dict = Body(..., description="typed selection schema v5 (Wafer + experiment context)"),
    db: Session = Depends(get_db),
):
    """Trend/map/time marking을 원장 증거로 final CHIP과 비교 facet에 해소한다."""
    try:
        return ledger_selection.resolve(db.connection(), payload)
    except ledger_selection.SelectionRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)
    except ledger_siblings.SiblingsRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)
    except Exception as exc:                       # noqa: BLE001
        if _is_undefined_table(exc):
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
         "object": (spec or {}).get("object") or {}}
        for name, spec in sorted((declared.get("vocabulary") or {}).items())
    ]
    return {
        "state": "ready" if entities else "empty",
        "entities": entities,
        "predicates": predicates,
        "collect": list(ledger_subgraph.NODE_KINDS),
    }


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


