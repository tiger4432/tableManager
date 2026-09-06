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
        None, description=("이 술어만 따라간다. 없으면 «전부» — 오늘 동작 그대로. "
                           "`이름:키1,키2` 로 쓰면 그 엣지는 씨앗과 «그 키가 같은» "
                           "노드로만 걷는다. 콜론이 없으면 제약 없음")),
    backbone_hops: int = Query(
        ledger_subgraph.DEFAULT_BACKBONE_HOPS, ge=0, le=40,
        description=("같은 자재를 따라가는 걸음에 주는 «별도» 예산. "
                     "양 끝이 «둘 다 dynamic» 인 걸음만 여기서 빠진다 — "
                     "정적/동적은 선언의 `class` 가 정한다. 0 이면 오늘과 같다")),
    collect: list[str] | None = Query(
        None, description=("응답의 `nodes` 에 실어 올 «노드 타입». 없으면 «전부» — "
                           "오늘 동작 그대로. 걷기는 안 바뀐다: 웨이퍼에서 결함으로 가려면 "
                           "다이를 «지나야» 하고, 지나는 것과 «실어 오는 것»은 다르다. "
                           "이름은 선언된 엔터티 타입이다 (`@` 버전은 있어도 없어도 된다)")),
    db: Session = Depends(get_db),
):
    """어느 증거 노드에서든 Entity–Event–Claim 서브그래프를 답한다."""
    # 🔴 AN UNDECLARED PREDICATE IS REFUSED, NOT ANSWERED WITH AN EMPTY GRAPH. A filter that
    # can never match returns exactly what "there is nothing here" returns, and the caller
    # cannot tell a typo from a fact -- the shape this repo spent a night removing from four
    # other layers. The declared set is read from the vocabulary, never restated here.
    # ⚠️ A DIRECT CALL LEAVES FastAPI's SENTINEL IN PLACE. Several tests call this
    # function rather than the route, and an omitted argument is then the `Query` object
    # itself - truthy, and not iterable. Through the app it is always a list or None.
    collect = list(collect) if isinstance(collect, (list, tuple, set)) else None
    # 🔴 SAME RULE AS `follow`, AND FOR THE SAME REASON. A type nobody declared can never
    # match, so answering it with an empty graph hands back exactly what "there is nothing
    # here" hands back and the caller cannot tell a typo from a fact.
    if collect:
        collectable = _collectable_types()
        unknown = sorted({str(name).split("@", 1)[0] for name in collect
                          if str(name).strip()} - collectable)
        if unknown:
            raise HTTPException(status_code=422, detail={
                "reason": "node_type_not_declared", "unknown": unknown,
                "declared": sorted(collectable),
                "message": "선언에 없는 노드 타입입니다: " + ", ".join(unknown),
            })
    follow, follow_keys = _split_follow(follow)
    if follow:
        followable = _followable_predicates()
        # 🔴 THE BARE HALF IS WHAT IS CHECKED. `inspected:x,y` is the declared predicate
        # `inspected` with a constraint on it, so refusing the whole string would make every
        # keyed request a 422 for a predicate that is in fact declared.
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
            follow_keys=follow_keys, backbone_hops=backbone_hops,
            collect=collect)
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


def _split_follow(follow):
    """`follow=inspected:x,y` -> the bare name the walk filters on, and the keys it binds.

    🔴 THE COLON IS OPTIONAL AND ITS ABSENCE IS NOT A DEFAULT — it is the whole of today's
    behaviour. `follow=slot_map` yields no keys for that predicate, which yields no
    constraint, which is the walk this repo already ships; the client sends no colons and
    keeps running unchanged. That is a requirement of this round, not a courtesy.

    Split on the FIRST colon only. A key name with a colon in it is not a thing the ledger
    can hold - the entity's key names come from the declaration - but a predicate spelled
    with one would otherwise be silently truncated, and the bare half then answers 422
    rather than walking something nobody asked for.

    Returns `(names, keys)` where `names` is what `follow` has always been.
    """
    names, keys = [], {}
    for entry in follow or []:
        name, _, spec = str(entry).partition(":")
        name = name.strip()
        names.append(name)
        wanted = tuple(part.strip() for part in spec.split(",") if part.strip())
        if wanted:
            # A predicate named twice keeps the LAST spec rather than merging: two specs for
            # one predicate is a caller contradicting itself, and intersecting them would
            # answer a third question neither side asked.
            keys[name] = wanted
    return names, keys


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

    🔴 THE BRIDGE CAME BACK AS A PREDICATE, so this list is the vocabulary and nothing
    else. It used to widen over `entities.<type>.references[].edge`, because `in_container`
    lived there with no atoms of its own and a caller who could not NAME it could not
    narrow a walk without cutting a die off from its wafer.

    MEASURED 2026-08-29: `in_container@1` is DECLARED in `vocabulary` now and emitted by two
    mappings on the `bonded_from` source, and NO entity carries `references` at all. The
    grammar for `references` still validates in `setup_bundle` and nothing reads it, so the
    widening this docstring described has no subject left -- it would matter again only on
    the day a reference edge is declared.
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
                    node_limit, edge_limit, follow=None, follow_keys=None,
                    backbone_hops=ledger_subgraph.DEFAULT_BACKBONE_HOPS,
                    collect=None):
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
        follow_keys=follow_keys,
        backbone_hops=backbone_hops, static_types=_static_types(),
        static_follow=_static_step_predicates(), collect=collect)


#: How many ledger rows one key-values answer may READ. The scan is bounded, not the
#: grouping: a `GROUP BY` over a whole subject_type would visit every row that type has,
#: which is the full scan this route exists beside rather than adds.
KEY_VALUE_SCAN_ROWS = 20000

#: How many distinct values one answer may CARRY. Asked as `limit + 1` so the answer can
#: say it was cut instead of looking complete.
KEY_VALUE_DEFAULT_LIMIT = 50
KEY_VALUE_MAX_LIMIT = 500


@router.get("/key-values")
def ledger_key_values(
    type: str = Query(..., description="선언된 엔터티 타입 (`@` 버전은 있어도 없어도 된다)"),
    key: str | None = Query(
        None, description=("한 축만 보고 싶을 때의 «선택» 인자. 없으면 그 타입의 «주어»를 "
                           "답한다. 복합 키 타입에서 축 하나의 값은 «단독으로 씨앗이 안 될 "
                           "수» 있고, 응답의 `seedable` 이 그것을 말한다")),
    limit: int = Query(KEY_VALUE_DEFAULT_LIMIT, ge=1, le=KEY_VALUE_MAX_LIMIT),
    db: Session = Depends(get_db),
):
    """이 타입의 이 키에 «오늘 원장에 있는» 값들. 씨앗을 고르기 위한 목록이다.

    🔴 값을 적으라면서 «어떤 값이 있는지»는 안 알려 주던 자리다. 걷기 상자의 키는 자유
    텍스트였고, 운영자는 씨앗 하나를 «외워서» 쳐야 했다.

    🔴 **읽는 «행 수»를 자른다. 그룹을 자르는 것이 아니다.** 한 타입 전체에 `GROUP BY` 를
    걸면 그 타입의 모든 행을 방문하고, 그것이 오늘 밤 등급 5 로 올린 바로 그 모양이다.
    그래서 `KEY_VALUE_SCAN_ROWS` 로 «먼저 자르고» 그 위에서 센다 -- 같은 규율이
    `enrichment_candidates.execute_candidate_probe` 에 이미 있고 이 함수는 그것을 따른다.

    🔴 **절단이 «둘»이고 따로 보고한다.** `scan_truncated` 는 「행을 다 못 봤다」이고
    `values_truncated` 는 「값이 더 있는데 안 실었다」다. 한 표지로 접으면 「이 키에는 값이
    이만큼뿐」과 「이만큼까지만 봤다」가 같은 답이 된다 -- 오늘 밤 내내 걷어낸 그 부류다.

    정렬은 «빈도 내림차순, 동률은 값 오름차순»이다. 적어 두지 않으면 질의가 정한다.

    ⚠️ 세는 대상은 «읽은 창» 안의 빈도다. 창이 잘렸으면 그 빈도는 표본이지 전수가 아니고,
    `scan_truncated` 가 그것을 말한다.
    """
    wanted_type = str(type).split("@", 1)[0]
    collectable = _collectable_types()
    if wanted_type not in collectable:
        raise HTTPException(status_code=422, detail={
            "reason": "node_type_not_declared", "unknown": [wanted_type],
            "declared": sorted(collectable),
            "message": "선언에 없는 노드 타입입니다: " + wanted_type})

    declared_keys = _declared_keys(wanted_type)
    if key is not None and key not in declared_keys:
        raise HTTPException(status_code=422, detail={
            "reason": "key_not_declared", "unknown": [key],
            "declared": sorted(declared_keys), "type": wanted_type,
            "message": "'%s' 가 선언하지 않은 키입니다: %s" % (wanted_type, key)})

    connection = db.connection()
    if not ledger_trace.relation_exists(connection, LEDGER_RELATION):
        raise _relation_absent()

    # 🔴 THE GROUPING KEYS ARE THE SUBJECT, NOT ONE AXIS OF IT. Asked per key, a composite
    # type answers with one list per axis, and a screen that pairs them offers the CROSS
    # PRODUCT - measured 2026-09-06 on one wafer: 144 pairs against 128 dies that exist.
    # Choosing one of the 16 that do not builds a seed the walk answers emptily, and an
    # empty answer reads as "there is nothing there" rather than "you asked for a die
    # that was never made". That is the same defect as a route list offering a walk the
    # policy refuses: selectable, and only wrong AFTER it is chosen.
    grouping = [key] if key else sorted(declared_keys)
    if not grouping:
        raise HTTPException(status_code=422, detail={
            "reason": "type_declares_no_keys", "type": wanted_type,
            "message": "'%s' 가 키를 선언하지 않아 주어를 셀 수 없습니다" % wanted_type})

    params = {"type_prefix": wanted_type + "%",
              "scan": KEY_VALUE_SCAN_ROWS + 1, "limit": limit + 1}
    # Key NAMES are bound, never interpolated - they came from the declaration, and
    # binding them keeps that true no matter what a declaration is allowed to contain.
    selected = []
    for index, name in enumerate(grouping):
        params["k%d" % index] = name
        # 🔴 `->` NOT `->>`. The text extractor turns the ledger's 0.0 into "0.0", the
        # canonical seed id writes those two differently, and the walk then answers a seed
        # nobody has - measured 2026-09-06: composite seeds 8/8 empty, the same 8 ready
        # once the type survives. A key's TYPE is part of its identity here.
        selected.append("subject_keys -> %%(k%d)s AS v%d" % (index, index))
    columns = ", ".join("v%d" % index for index in range(len(grouping)))
    present = " AND ".join("subject_keys ? %%(k%d)s" % index
                           for index in range(len(grouping)))
    # jsonb `->` gives SQL NULL for a missing key and `'null'::jsonb` for a declared one
    # holding JSON null; neither is a value a seed can carry, and they are different rows.
    not_null = " AND ".join("v%d IS NOT NULL AND v%d <> 'null'::jsonb" % (index, index)
                            for index in range(len(grouping)))

    rows = connection.exec_driver_sql(
        # The window is taken FIRST and grouped after, so the work is bounded by
        # `KEY_VALUE_SCAN_ROWS` rather than by how many rows the type has.
        "SELECT " + columns + ", count(*) AS n FROM ("
        "  SELECT " + ", ".join(selected) + " FROM " + LEDGER_RELATION +
        "  WHERE subject_type LIKE %(type_prefix)s AND " + present +
        "  LIMIT %(scan)s"
        ") w WHERE " + not_null + " GROUP BY " + columns +
        " ORDER BY n DESC, " + columns + " LIMIT %(limit)s",
        params,
    ).fetchall()

    scanned = sum(int(row[-1]) for row in rows)
    subjects = [{"keys": {name: row[index] for index, name in enumerate(grouping)},
                 "count": int(row[-1])} for row in rows[:limit]]
    return {
        "type": wanted_type, "key": key, "keys": grouping,
        "subjects": subjects,
        # ⚠️ THIS SAYS WHAT IT MEASURED, AND `seedable` DID NOT. The old name claimed the
        # combination would seed a walk, which this route never checked and which was
        # FALSE for every composite subject while the values came back as text. Key
        # coverage is what a set comparison can know; whether the walk answers is a
        # different question and belongs to whoever asks it.
        "covers_declared_keys": set(grouping) == set(declared_keys),
        "scanned": min(scanned, KEY_VALUE_SCAN_ROWS),
        # 🔴 TWO CUTS, SAID SEPARATELY. Neither implies the other: a small key can fill
        # the value list off an untruncated scan, and a huge scan can yield three values.
        "scan_truncated": scanned > KEY_VALUE_SCAN_ROWS,
        "values_truncated": len(rows) > limit,
        "limits": {"scan_rows": KEY_VALUE_SCAN_ROWS, "values": limit},
        "order": "count_desc_then_value_asc",
    }


def _declared_keys(bare_type: str) -> set:
    """The keys THIS type declares -- the same list `/declaration` publishes.

    🔴 Read, never restated: a key list held here would answer differently from the
    catalogue on the day an entity gains a key, and the caller reads both.
    """
    try:
        from ledger import config as _config
        declared = (_config.load() or {}).get("entities") or {}
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable while resolving keys: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"선언을 읽지 못했습니다: {exc}"})
    for name, spec in declared.items():
        if str(name).split("@", 1)[0] == bare_type:
            return {str(k) for k in ((spec or {}).get("keys") or [])}
    return set()


def _collectable_types():
    """Every node type a caller may name in `collect` -- read from the DECLARATION, only.

    🔴 THE SAME AUTHORITY `/declaration` PUBLISHES, not a second copy. That route already
    answers "what may I ask for" out of `entities`, and a list restated here would be a
    second author for one fact: declaring an entity would make it collectable on one
    surface and refused on the other.

    Versions are stripped so `defect` and `defect@1` are the same answer -- the caller
    should not have to know which spelling the declaration happens to use.
    """
    try:
        from ledger import config as _config
        declared = (_config.load() or {}).get("entities") or {}
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable while resolving collect: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"선언을 읽지 못했습니다: {exc}"})
    return {str(name).split("@", 1)[0] for name in declared}




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














@router.get("/gaps")
def ledger_gap_catalogue(name: str = Query(None)):
    """선언이 「있어야 한다」고 말한 자리 중 원장이 «비어 있는» 곳.

    🔴 라우트는 «하나»이고 인자가 둘로 가릅니다 — 새 라우트가 아니라 «같은 질문의 두 배율»입니다.
    ```
    인자 없음   질문 «이름»만. 선언만 읽으므로 «즉시» (DB 를 안 탑니다)
    name=…     그 질문 «하나»를 셉니다 (~1초)
    ```
    이 화면의 판별식이 「열고 3초 안에 끊을지 정한다」인데, 스물을 한꺼번에 세면 «30초»입니다.
    그래서 목록은 공짜로 주고 «펼 때» 값을 냅니다.

    🔴 이름은 여기서 짓지 «않습니다». `docs/spec/APPLICATION_GAP_SPEC.md` 가 정본이고
    `ledger/gap_names.json` 이 그 기계 판형입니다. 선언과 표가 어긋나면 이 라우트는
    «거절»합니다 — 이름 없는 결측을 «이웃 이름»으로 답하면 화면이 멀쩡해 보이면서
    한 종류가 통째로 빠지고, 그건 출력을 봐서는 못 알아챕니다.

    🔴 수마다 «어떤 수인지»가 붙습니다. 표본은 「가장 오래된 것들」이 «아니라고» 말하고,
    성립하지 않는 질문은 «0이 아니라» 수를 안 냅니다.
    """
    from ledger import config as _config
    from ledger import gaps as _gaps

    try:
        declared = _config.load() or {}
    except Exception as exc:                       # noqa: BLE001
        logger.error("declaration unreadable: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"선언을 읽지 못했습니다: {exc}"})

    try:
        if name is None:
            asked = _gaps.questions(declared)
            return {"mode": "names", "count": len(asked), "gaps": asked}
        from database.database import engine
        return {"mode": "measured", "count": 1,
                "gaps": _gaps.measure(engine, declared, only=name)}
    except _gaps.GapQuestionUnknown as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except _gaps.GapTableMismatch as exc:
        # 503, not 500: the declaration and the spec disagree, which is a DEPLOYMENT fact
        # somebody has to fix in one of the two - not a failure of this request.
        raise HTTPException(status_code=503, detail={
            "reason": "gap_table_mismatch", "message": str(exc)})


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

    # 🔴 `class` IS CARRIED, NOT DECIDED HERE. The walk refuses a step from a static type
    # to a dynamic one (`_static_step_predicates`), and a client deriving paths from the
    # type graph alone cannot know that - so the route list offers walks that come back
    # with the seed and nothing else. The value published is the one `_static_types()`
    # already reads, so declaring a type static changes both at once and neither can
    # drift from the other.
    #
    # ⚠️ AN ENTITY THAT DECLARES NO CLASS PUBLISHES `None`, NOT "dynamic". "I was not
    # told" and "I was told it is dynamic" are different facts, and filling the first
    # with the second is the exact shape this route exists to avoid - the reader would
    # then draw a path the walk may still refuse, with no way to know it guessed.
    entities = [
        {"type": name, "keys": list((spec or {}).get("keys") or []),
         "class": (spec or {}).get("class")}
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
    catalogue = {
        "state": "ready" if entities else "empty",
        "entities": entities,
        "predicates": predicates,
    }

    # 🔴 `scope_columns` IS `base_select_columns`, NOT A SECOND LIST THAT LOOKS LIKE IT.
    # The scope reader already refuses a column outside that list by name, so a screen that
    # offered its options from anywhere else would show a column the server then rejects -
    # and the operator would read a correct refusal as a broken button. That is why these
    # come off the COMPILED plans rather than off the raw declaration: the compiled list is
    # the one the refusal is measured against. `emits` has no compiled form, so it is read
    # from the declaration's own mappings, which is this route's ordinary posture.
    #
    # 🔴 THE KEY IS OMITTED, NOT EMPTIED, WHEN THE SETUP WILL NOT COMPILE. The label
    # this feeds has to say three different things - "a ledger source", "not a source", and
    # "could not find out" - and if an uncompilable setup answered with `[]`, the last two
    # would render identically and the screen would tell an operator their table is not a
    # source when the truth is that nobody asked. Presence of the key means the list is
    # authoritative; absence means unknown. The rest of the catalogue still answers, because
    # a setup that will not compile does not stop `entities` and `predicates` being true.
    try:
        from ledger.setup import load_setup
        from ledger.source_preparation import base_select_columns

        plans = load_setup().snapshot.source_plans
        declared_sources = declared.get("sources") or {}
        catalogue["sources"] = [
            {
                "source": source_id,
                "relation": plan.relation,
                "emits": sorted({
                    (mapping or {}).get("predicate")
                    for mapping in (((declared_sources.get(source_id) or {})
                                     .get("bind") or {}).get("mappings") or {}).values()
                    if (mapping or {}).get("predicate")
                }),
                "scope_columns": list(base_select_columns(plan)),
            }
            for source_id, plan in sorted(plans.items())
        ]
    except Exception as exc:                       # noqa: BLE001 - see the note above
        logger.error("declaration sources unavailable: %s", exc)
    return catalogue










