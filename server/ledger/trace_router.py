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

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from database.database import get_db

from ledger_api import ledger_subgraph
from ledger import gaps, schema, trace
from declaration_names import bare_name as _bare_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

def _worlds(world):
    """The names of the ledger worlds a request asked for, in the order asked (총괄 60d7e8e42 ·
    092a6f9e5) - the ledgers the walk reads, the declarations it reads. `world` is one name or
    several (`world=a&world=c`); none, blanks or FastAPI's `Query` sentinel (a direct call) is
    the operating world. An unknown world is refused by name with the list, never answered from
    the default: the same posture as an undeclared predicate."""
    asked = [world] if isinstance(world, str) else (
        list(world) if isinstance(world, (list, tuple)) else [])
    asked = list(dict.fromkeys(str(name).strip() for name in asked if str(name).strip()))
    try:
        return tuple(schema.require_world(name) for name in asked or [None])
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=404, detail={
            "reason": "world_unknown", "world": world, "worlds": schema.world_listing()["worlds"],
            "message": f"{exc} - pick one from 'worlds'"})


def _declaration_and_whose(world=None):
    """The declaration of the worlds asked, merged in the order asked (`config.merged`), and which
    world each name came from."""
    from ledger import config as _config

    return _config.merged([(names.name, _config.load(names.declaration_path) or {})
                           for names in _worlds(world)])


def _declaration(world=None) -> dict:
    return _declaration_and_whose(world)[0]


def _ledgers_present(connection, names):
    """Every ledger the walk would read is there - or the first that is not, refused by name."""
    for each in names:
        if not trace.relation_exists(connection, each.ledger):
            raise _relation_absent(each.ledger)










# `GET /api/ledger/explore_entity` was retired 2026-08-23 (round 3, "v1 retirement").
# `GET /api/ledger/subgraph` answers the same question and keeps competing claims visible
# instead of letting a subgraph projection cover the facts. Measured before removal: zero
# references anywhere in `client2/` - source or built bundles - which is why this one could
# go alone while `trace`, `explore` and `structure` wait for a client round.


def _subgraph_contract_state(connection, relation):
    """Name missing deployment pieces before the evidence query can scan slowly."""
    rows = trace._fetch(connection, """
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
    """, {"relation": relation})
    names = ("source_event_id", "source_event_state",
             "idx_ledger_source_event", "idx_ledger_object_entity")
    return [name for name, present in zip(names, rows[0]) if not present]


@router.get("/subgraph")
def evidence_subgraph(
    node_id: str | None = Query(None, alias="id",
                         description="Entity/Event/Claim/Collection/Point/Value/Action의 불투명 id"),
    world: list[str] | None = Query(
        None, description="Ledger worlds, repeated (world=a&world=c); none = the operating world"),
    hops: int = Query(ledger_subgraph.DEFAULT_HOPS, ge=1, le=ledger_subgraph.MAX_HOPS,
                      description="증거 그래프 탐색 깊이"),
    direction: str = Query("both", pattern="^(outgoing|incoming|both)$",
                           description="Entity 주장 방향; 구조 엣지는 항상 양쪽 보존"),
    since: str | None = Query(
        None, description="이 시각 «이상»의 원자만 (ISO 8601). 없으면 전 구간"),
    until: str | None = Query(
        None, description="이 시각 «미만»의 원자만 (ISO 8601). 없으면 전 구간"),
    # 🔴 THE WALK'S OWN DEFAULTS, CALLED (총괄 de9455c17): this route said 1200 edges while the walk
    #    measured 6000, so the screen, which sends none, was cut at 1200 edges and 2400 claims.
    node_limit: int = Query(ledger_subgraph.DEFAULT_NODE_LIMIT, ge=10,
                            le=ledger_subgraph.MAX_NODE_LIMIT, description="응답 노드 상한"),
    edge_limit: int = Query(
        ledger_subgraph.DEFAULT_EDGE_LIMIT, ge=20, le=ledger_subgraph.MAX_EDGE_LIMIT,
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
    seed_type: str | None = Query(
        None,
        description=("씨앗을 «열거하지 않고» 말한다 — 그 타입으로 «등록된 주어 전부»가 씨앗이다. "
                     "`negative[]` 와 같이 주면 그것이 「전체 ∖ 사례」이고, 집합 연산은 «없다» — "
                     "인자 둘이다. 많으면 `limits.seeds` 까지만 걷고 `truncated.seeds` 가 "
                     "«몇을 안 걸었는지» 말한다. ⛔ `id` 와 «같이» 줄 수 없다")),
    seed_limit: int = Query(
        ledger_subgraph.DEFAULT_SEED_LIMIT, ge=1, le=ledger_subgraph.MAX_SEED_LIMIT,
        description="서술된 씨앗의 상한. `node_limit` 과 같은 부류다"),
    group_by: str | None = Query(
        None,
        description=("이 걷기가 «닿은 노드»를 무엇으로 묶나 — `type`(노드 타입) 또는 "
                     "노드가 드는 «값의 이름»(키·속성·수식어). 없으면 봉투에 `groups` 칸이 "
                     "«생기지 않는다»(null 이 아니라 «없음» — 안 물은 것이다). "
                     "술어는 여기 오지 않는다: 길은 `follow` 가 고른다")),
    measure: list[str] | None = Query(
        None,
        description=("무리마다 무엇을 재나 — `count`·`distinct`·`sum`·`mean`·`min`·"
                     "`max`·`median`. 수를 접는 다섯은 «이름이 필요»하다: `mean:<이름>`. "
                     "이름은 키·속성·수식어·«술어»(그 노드가 든 그 술어의 claim 수) 순으로 찾고 "
                     "둘이 답하면 «거절»한다 — 순서는 응답의 `value_sources` 가 말한다. "
                     "«여러 번» 줄 수 있고, 무리의 `value` 는 measure 문자열로 키 잡은 «맵»이다 "
                     "(하나여도 맵). 없으면 `count`. 이 일곱은 화면이 이미 고르던 그 일곱이다")),
    response_format: str = Query(
        "json", alias="format",
        description=("`json`(기본) 또는 `rows`. `rows` 는 «같은 걷기 결과»를 TSV 로 접어 "
                     "돌려준다 — 첫 줄은 절단 표지, 그다음이 머리, 행 하나가 «닿은 노드 하나»"),
    ),
    db: Session = Depends(get_db),
    include_superseded: bool = Query(
        False,
        description=("Also draw facts that are no longer current - for a predicate declared "
                     "`cardinality: one`, a fact with a later fact for the same subject. "
                     "Default: the current fact only. Such edges carry `not_current`")),
    fanout_limit: int | None = Query(
        None, ge=1,
        description=("Steps from one node along one predicate and direction to more than this "
                     "many nodes are not drawn - the answer's `bundles` lists them with their "
                     "count. Absent: everything is drawn")),
    expand: list[str] | None = Query(
        None,
        description=("`<node id>|<predicate>|<direction>` of a bundle to draw past "
                     "`fanout_limit`. May repeat")),
):
    """어느 증거 노드에서든 Entity–Event–Claim 서브그래프를 답한다."""
    # ⛔ FIRST, BEFORE ANY OTHER ARGUMENT IS TOUCHED. A direct call leaves FastAPI's
    # `Query` sentinels in the other parameters (this handler's own note below says so), so
    # a refusal placed further down would raise a TypeError about an unrelated argument
    # instead of naming the format - and a caller who asked for rows and got JSON reads the
    # failure as 「the walk found nothing」.
    # ⚠️ A DIRECT CALL LEAVES THE `Query` SENTINEL HERE, exactly as this handler's note
    # below says of the other arguments. Stringifying it would make every direct caller look
    # like they asked for a format nobody answers - which is how this refusal first broke
    # three interval tests that never mentioned `format`.
    wants = (response_format if isinstance(response_format, str) else "json").strip().lower()
    if wants not in ("json", "rows"):
        raise HTTPException(status_code=422, detail={
            "reason": "format_unknown", "argument": "format", "value": response_format,
            "message": f"Unknown format: {response_format} - use json or rows"})
    # 🔴 AN UNDECLARED PREDICATE IS REFUSED, NOT ANSWERED WITH AN EMPTY GRAPH. A filter that
    # can never match returns exactly what "there is nothing here" returns, and the caller
    # cannot tell a typo from a fact -- the shape this repo spent a night removing from four
    # other layers. The declared set is read from the vocabulary, never restated here.
    # ⚠️ A DIRECT CALL LEAVES FastAPI's SENTINEL IN PLACE. Several tests call this
    # function rather than the route, and an omitted argument is then the `Query` object
    # itself - truthy, and not iterable. Through the app it is always a list or None.
    collect = list(collect) if isinstance(collect, (list, tuple, set)) else None
    # 🔴 EVERY NAME THIS REQUEST BRINGS GOES THROUGH `_declared_or_refused` (총괄 17b6337e4):
    # folded bare and, when the picked worlds do not declare it, refused by name - a filter
    # that can never match hands back what "there is nothing here" hands back.
    if collect:
        collect = _declared_or_refused(
            [name for name in collect if str(name).strip()], _collectable_types(world),
            reason="node_type_not_declared", what="type", world=world, argument="collect")
    follow = _follow_classes(follow, world)
    follow, follow_keys = _split_follow(follow)
    if follow:
        # 🔴 THE BARE HALF IS WHAT IS CHECKED. `inspected:x,y` is the declared predicate
        # `inspected` with a constraint on it, so refusing the whole string would make every
        # keyed request a 422 for a predicate that is in fact declared.
        follow = _declared_or_refused(
            follow, _followable_predicates(world), reason="predicate_not_declared",
            what="predicate", world=world, argument="follow")
        follow_keys = {_bare_name(name): keys for name, keys in follow_keys.items()}
    if isinstance(expand, (list, tuple)):
        expand = [_expanded_bundle(item, world) for item in expand]
    if isinstance(seed_type, str) and seed_type.strip():
        (seed_type,) = _declared_or_refused(
            [seed_type], _collectable_types(world), reason="seed_type_not_declared",
            what="type", world=world, argument="seed_type")
    if isinstance(group_by, str) and group_by.strip() and group_by != ledger_subgraph.GROUP_BY_TYPE:
        (group_by,) = _declared_or_refused(
            [group_by], _value_names(world), reason="value_name_not_declared",
            what="value name", world=world, argument="group_by")
    if isinstance(measure, (list, tuple)):
        # validated, not rewritten: the answer keys each value by the measure AS ASKED - a saved
        # board looks its number up by its own string - and the fold folds the name it reads
        _declared_or_refused(
            [spelled.partition(":")[2] for spelled in measure if spelled.partition(":")[2].strip()],
            _value_names(world), reason="value_name_not_declared", what="value name",
            world=world, argument="measure")
    interval = {}
    for name, raw in (("since", since), ("until", until)):
        # ⚠️ NOT `is None`. This endpoint is also CALLED DIRECTLY, by tests and by
        # neighbouring code, and an argument left out there arrives as FastAPI's `Query`
        # default object rather than as `None` - so a bare `is None` test refused every such
        # call with `interval_not_iso8601`. A string is a bound and is parsed or refused;
        # anything else means the caller did not supply one.
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            interval[name] = _instant_arg(raw)
        except ValueError:
            # \u26d4 REFUSED BY NAME, not silently ignored. An unparsable bound that is
            # dropped would answer the WHOLE history to a caller who asked for a window, and
            # they would read that as 「there is nothing outside my window」.
            raise HTTPException(status_code=422, detail={
                "reason": "interval_not_iso8601", "argument": name, "value": raw,
                "message": f"{name} is not an ISO 8601 time: {raw} - write it like 2026-09-29T08:00:00"})
    if len(interval) == 2 and interval["since"] >= interval["until"]:
        raise HTTPException(status_code=422, detail={
            "reason": "interval_empty",
            "message": "since must be before until - swap them or widen the window"})
    # \u26d4 A FORMAT WE DO NOT ANSWER IS REFUSED BY NAME. Falling back to JSON would hand a
    # caller who asked for rows a body they cannot parse, and they would read the failure as
    # 「the walk found nothing」 - the shape this route already refuses for an unparsable
    # interval and an undeclared predicate.
    # ⛔ TWO DEFINITIONS OF ONE QUESTION'S SEEDS IS NOT A DEFAULT TO PICK BETWEEN. Silently
    # preferring one would make that preference the answer, and the caller would read a walk
    # from subjects they did not ask for (S-148-a, 판정 337).
    # ⚠️ `isinstance(str)` BECAUSE A DIRECT CALL LEAVES FastAPI'S `Query` SENTINEL HERE, and
    # a sentinel is truthy — this handler's own note above says so, and measured: a bare
    # truthiness test refused two existing tests that pass neither argument.
    described = isinstance(seed_type, str) and bool(seed_type.strip())
    listed = isinstance(node_id, str) and bool(node_id.strip())
    if described and listed:
        raise HTTPException(status_code=422, detail={
            "reason": "seeds_defined_twice",
            "message": "`id` and `seed_type` cannot both be given - list the seeds with `id` "
                       "or describe them with `seed_type`"})
    # 🔴 `id` STOPPED BEING REQUIRED SO A DESCRIPTION COULD ARRIVE, AND THAT MADE 「neither」
    # REACHABLE. FastAPI used to refuse an absent `id` before this handler ran; now the
    # three states are ours to say, and 「씨앗을 안 말했다」 must be named rather than walked
    # from nothing.
    if not described and not listed:
        raise HTTPException(status_code=422, detail={
            "reason": "seeds_not_defined",
            "message": "No seeds given - list them with `id` or describe them with "
                       "`seed_type`"})
    try:
        payload = _evidence_graph(
            db.connection(), node_id=_signed_start(node_id, positive, negative), world=world,
            hops=hops, direction=direction,
            node_limit=node_limit, edge_limit=edge_limit, follow=follow,
            follow_keys=follow_keys, backbone_hops=backbone_hops,
            collect=collect, include_superseded=include_superseded,
            rows=(wants == "rows"),
            group_by=group_by, measure=measure,
            seed_type=seed_type, seed_limit=seed_limit,
            # A direct call leaves FastAPI's `Query` sentinels here, as for `collect` above.
            fanout_limit=fanout_limit if isinstance(fanout_limit, int) else None,
            expand=list(expand) if isinstance(expand, (list, tuple)) else None,
            **interval)
        if wants == "rows":
            # \U0001f534 THE SAME WALK, READ SIDEWAYS. No second route and no second traversal
            # of the source - `rows` was folded from this payload's own structures.
            return PlainTextResponse(payload.get("rows") or "",
                                     media_type="text/tab-separated-values")
        return payload
    except ledger_subgraph.AggregateRefused as exc:
        # 🔴 NAMED, WITH THE CHOICES (S-146, 판정 331). `subgraph_request_invalid` would tell
        # a caller their request was wrong and not which word -- and a screen that offers
        # measures cannot repair a refusal it cannot read. The same posture as
        # `node_type_not_declared`, which hands back `declared`.
        raise HTTPException(status_code=422, detail={
            "reason": exc.code, "message": exc.detail, "choices": list(exc.choices)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "reason": "subgraph_request_invalid", "message": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:                       # noqa: BLE001 - DDL race backstop
        if _is_undefined_table(exc):
            raise _relation_absent(", ".join(each.ledger for each in _worlds(world)))
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


#: `follow=class:<word>` names every predicate whose `class` holds the word (총괄 e6dd72526).
FOLLOW_CLASS_PREFIX = "class:"


def _follow_classes(follow, world=None):
    """`class:<word>` entries -> the declared predicates of that class; other entries untouched.

    Refused by name when no predicate declares the word - the same door as an undeclared
    predicate or node type: a class nobody declared can never match, and an empty walk would
    read as 「nothing is there」.
    """
    if not isinstance(follow, (list, tuple, set)):
        return follow
    entries = [str(entry) for entry in follow]
    wanted = [entry[len(FOLLOW_CLASS_PREFIX):].strip() for entry in entries
              if entry.startswith(FOLLOW_CLASS_PREFIX)]
    if not wanted:
        return list(follow)
    by_class = _predicate_classes(world)
    unknown = sorted(set(wanted) - set(by_class))
    if unknown:
        raise HTTPException(status_code=422, detail={
            "reason": "predicate_class_not_declared", "unknown": unknown,
            "declared": sorted(by_class),
            "message": ("Not a declared predicate class: " + ", ".join(unknown)
                        + " - pick one from 'declared'")})
    out = [entry for entry in entries if not entry.startswith(FOLLOW_CLASS_PREFIX)]
    for word in wanted:
        out.extend(name for name in by_class[word] if name not in out)
    return out


def _predicate_classes(world=None) -> dict:
    """{class word: the bare names of the predicates that carry it}, read from the declaration."""
    try:
        vocabulary = (_declaration(world) or {}).get("vocabulary") or {}
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable while resolving follow classes: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"The declaration could not be read: {exc} - fix the declaration and reload"})
    from ledger import setup_bundle

    out = {}
    for key, spec in vocabulary.items():
        for word in setup_bundle.class_words(spec):
            out.setdefault(word, set()).add(_bare_name(key))
    return {word: sorted(names) for word, names in out.items()}


def _split_follow(follow):
    """`follow=inspected:x,y` -> the bare name the walk filters on, and the keys it binds.

    ⚠️ `class:<word>` entries never reach here - `_follow_classes` expands them first, so a
    predicate literally named `class` cannot be followed by name (0 in the box and the sample).

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


def _predicate_cardinalities(world=None) -> dict:
    """`{predicate name: "one"|"many"}` from the declaration (S-133 ④, 판정 256).

    🔴 THE SCREEN HAS TO BE ABLE TO SAY 「하나」. A `one` predicate means a subject carries
    at most one object right now, and the walk is where anybody sees that - but an edge
    knew only `atom.predicate`, so the answer had to travel with it.

    Read from the same declaration `_static_types` and `_static_step_predicates` read, and
    keyed by the same unversioned name the edges use. Absent means `many`, which is what
    every declaration on disk means today, so an edge is never told something the
    declaration did not say.
    """
    try:
        declared = _declaration(world) or {}
    except Exception:                                                  # noqa: BLE001
        # A walk must answer even when the declaration cannot be read; it simply says
        # nothing about cardinality rather than refusing to draw the graph.
        return {}
    cardinalities = {}
    for key, rule in (declared.get("vocabulary") or {}).items():
        declared_value = (rule or {}).get("cardinality")
        if declared_value in ("one", "many"):
            cardinalities[_bare_name(key)] = declared_value
    return cardinalities


def _self_describing_predicates(world=None):
    """Predicates the declaration gives NO OBJECT -- the ones that describe their subject.

    🔴 THE WALK USED TO SPELL THIS `follow=["register"]`, A DOMAIN WORD IN THE CODE
    (S-263). 「코드에 도메인 낱말이 없다」: an installation whose registration predicate is
    called anything else got nodes with permanently empty attribute columns, and nothing
    said so - the same silence S-52-i removed one layer up. The declaration already
    answers this: a sentence with no object says nothing about an object and everything
    about its SUBJECT, which is what `roleframe` says where it compiles one, and the
    attributes an entity carries ride in exactly those atoms' qualifiers.

    SAME SHAPE AS `_static_types` and `_predicate_cardinalities`: the declaration is the
    only authority, read bare (an old `x@1` folds), and a second
    objectless predicate widens this with no edit here.

    The list is `setup_bundle.registration_predicates` - the declared object-less predicates and
    the name the translator registers bound attributes under (총괄 10-07 ⑤), so a declaration
    with no object-less predicate still carries those columns.

    ⚠️ EMPTY only when the declaration cannot be READ - a walk already answering without
    cardinalities and without static types. Refusing the graph over it would be this function
    deciding a question the route owns.
    """
    from ledger.setup_bundle import registration_predicates

    try:
        declared = _declaration(world) or {}
    except Exception:                                                  # noqa: BLE001
        return set()
    return set(registration_predicates(declared.get("vocabulary") or {}))


def _followable_predicates(world=None):
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
        declared = (_declaration(world) or {}).get("vocabulary") or {}
        names |= {_bare_name(key) for key in declared}
    except Exception:      # an unreadable declaration refuses everything rather than guessing
        return set()
    return names


def _static_types(world=None):
    """Entity types the declaration marks `class: "static"` -- names, not happenings.

    🔴 SAME SHAPE AS `_followable_predicates`, and for the
    same reason: the declaration is the only authority, so an entity becomes static by
    being declared static and never by an edit here. An unreadable declaration returns the
    EMPTY set, which is exactly today's walk rather than a guess about which types are
    hubs.

    Bare names: an old `defect_kind@1` folds to what a projected node carries.
    """
    try:
        declared = (_declaration(world) or {}).get("entities") or {}
    except Exception:
        return set()
    from ledger import setup_bundle

    return {_bare_name(key) for key, rule in declared.items()
            if setup_bundle.has_class(rule, "static")}


def _static_step_predicates(world=None):
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
        declared = _declaration(world) or {}
    except Exception:
        return set()
    from ledger import setup_bundle

    entities = declared.get("entities") or {}
    static = {_bare_name(key) for key, rule in entities.items()
              if setup_bundle.has_class(rule, "static")}
    names = set()
    for key, rule in (declared.get("vocabulary") or {}).items():
        subjects = [_bare_name(item) for item in ((rule or {}).get("subjects") or [])]
        targets = [_bare_name(item)
                   for item in (((rule or {}).get("object") or {}).get("types") or [])]
        if not subjects or not targets:
            continue
        if all(item in static for item in subjects) and all(item in static for item in targets):
            names.add(_bare_name(key))
    return names


def _instant_arg(raw):
    """One ISO 8601 bound, as a timezone-aware instant. Raises `ValueError` if it is not.

    \u26a0\ufe0f A NAIVE VALUE IS READ AS UTC rather than refused: the ledger stores
    `timestamptz`, so a bound with no zone has to mean SOMETHING, and every other instant this
    module renders is UTC. Refusing it would make the ordinary `?since=2026-09-01` a 422.
    """
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _declared_entities(world=None):
    """The entity declarations, read the way every other handler here reads them.

    ⛔ NOT A NEW LOADER. `/declaration` already publishes these (keys and attributes)
    through `ledger.config`, and the walk table's columns must be the SAME declaration the
    screen draws from - a second reader is how the two come to disagree about which
    columns exist. The import is local because every sibling handler in this module does
    the same: importing `ledger.config` at module scope would put a refusable load on this
    router's import path.
    """

    return (_declaration(world) or {}).get("entities") or {}


def _evidence_graph(connection, *, node_id, hops, direction, world=None,
                    node_limit, edge_limit, follow=None, follow_keys=None,
                    backbone_hops=ledger_subgraph.DEFAULT_BACKBONE_HOPS,
        # 기본은 `one` 술어의 «지금 것»(가장 늦은 occurred_at)만 가져온다. true 면 옛것도
        # 가져오되 엣지에 `not_current` 표지 (총괄 22ebdd153, 판정 256 뒤집음).
        include_superseded: bool = False,
                    collect=None, since=None, until=None, rows=False,
                    group_by=None, measure=None,
                    seed_type=None, seed_limit=ledger_subgraph.DEFAULT_SEED_LIMIT,
                    fanout_limit=None, expand=None):
    names = _worlds(world)
    _ledgers_present(connection, names)
    missing = sorted({name for each in names
                      for name in _subgraph_contract_state(connection, each.ledger)})
    if missing:
        raise HTTPException(status_code=503, detail={
            "reason": "source_event_projection_not_deployed",
            "state": "not_deployed", "missing": missing,
            "message": ("The Source Event graph is not migrated - run "
                        "server/migrations/add_ledger_source_events.py --apply"),
        })
    cardinalities = _predicate_cardinalities(world)
    return ledger_subgraph.subgraph(
        node_id, ledger_subgraph.SqlEvidenceLookup(
        connection, worlds=names, since=since, until=until,
        one=ledger_subgraph.one_predicates(cardinalities),
        current_only=not include_superseded),
        hops=hops, direction=direction,
        node_limit=node_limit, edge_limit=edge_limit, follow=follow,
        follow_keys=follow_keys,
        backbone_hops=backbone_hops, static_types=_static_types(world),
        static_follow=_static_step_predicates(world), collect=collect,
        registration_follow=_self_describing_predicates(world),
        cardinalities=cardinalities,
        # The declaration is the ONLY authority for which columns exist — the same source
        # the client reads through /declaration, so a key added to a declaration reaches
        # both the screen and the TSV with no edit in either (S-183).
        rows=rows, entities=_declared_entities(world) if rows else None,
        # S-146. The fold rides the SAME walk - no second query, no second budget.
        group_by=group_by, measure=measure,
        # S-148-a. The description resolves INSIDE the walk, on the same connection.
        seed_type=seed_type, seed_limit=seed_limit,
        fanout_limit=fanout_limit, expand=expand,
        # the worlds' own declarations, for the walk's key order and plural names
        declaration_paths=tuple(each.declaration_path for each in names))


#: How many NODES one key-values answer may read when it groups by ONE axis of a composite
#: type (several nodes can share a value there). Grouping by every declared key needs only
#: `limit + 1` nodes, since each node is then its own value. Scan + count at this budget, per
#: type on the box: task/scoped_redo_report.md (29cee1d47).
KEY_VALUE_SCAN_NODES = 1000

#: How many distinct values one answer may CARRY. Asked as `limit + 1` so the answer can
#: say it was cut instead of looking complete.
KEY_VALUE_DEFAULT_LIMIT = 50
KEY_VALUE_MAX_LIMIT = 500

#: Said in every key-values answer of a type whose first key is not text (`prefix_refusal`), and as the
#: 422 when such a type is asked `starts_with` (총괄 bccbdd601) - one sentence, both places.
PREFIX_REFUSAL = ("'%s' cannot be found by its first letters - its first key '%s' is not text. "
                  "Type the whole key in the key boxes")


def _prefix_axis(connection, relation, bare_type, declared_keys, case):
    """(the axis `starts_with` reads, or None; the refusal, or None). The axis is the declared key
    that comes FIRST in jsonb's own key order - asked of PostgreSQL, the order the subject index
    sorts by, so only on it is a prefix one range (총괄 bccbdd601). It must hold text: read from the
    first node with that axis at or past '' (two probes); a number or no text there is refused."""
    nulls = json.dumps({name: None for name in declared_keys})
    axis = connection.exec_driver_sql("SELECT k FROM jsonb_object_keys(%(o)s::jsonb) k LIMIT 1",
                                      {"o": nulls}).scalar()
    first = connection.exec_driver_sql(
        "SELECT keys::text FROM (%s) n" % gaps._nodes_of_type_sql(case).format(table=relation),
        {"bare": bare_type, "scan": 1, "nulls": nulls, "axis": axis, "p": "", "plen": 0}).scalar()
    if first is None or isinstance(json.loads(first).get(axis), str):
        return axis, None
    return None, PREFIX_REFUSAL % (bare_type, axis)


@router.get("/key-values")
def ledger_key_values(
    type: str = Query(..., description="선언된 엔터티 타입 (`@` 버전은 있어도 없어도 된다)"),
    key: str | None = Query(
        None, description=("한 축만 보고 싶을 때의 «선택» 인자. 없으면 그 타입의 «주어»를 "
                           "답한다. 복합 키 타입에서 축 하나의 값은 «단독으로 씨앗이 안 될 "
                           "수» 있고, 응답의 `seedable` 이 그것을 말한다")),
    limit: int = Query(KEY_VALUE_DEFAULT_LIMIT, ge=1, le=KEY_VALUE_MAX_LIMIT),
    world: list[str] | None = Query(
        None, description="Ledger worlds, repeated (world=a&world=c); none = the operating world"),
    starts_with: str | None = Query(
        None, description=("앞글자 — 그 타입의 `prefix_axis` 가 이것으로 시작하는 노드만, 원장 인덱스의 그 "
                           "범위에서 (`prefix_case` 가 대소문자를 말한다). 비면 오늘과 같은 답")),
    db: Session = Depends(get_db),
):
    """이 타입의 이 키에 «오늘 원장에 있는» 값들. 씨앗을 고르기 위한 목록이다.

    🔴 [총괄 29cee1d47] 노드는 `gaps._nodes_of_type_sql` 이 답한다 -- 주어 «와» 목적어 두 쪽.
    주어 쪽만 읽던 때는 목적어로만 나오는 타입(이 박스의 recipe · defect_kind)이 빈 목록이었고, `LIKE`
    접두가 `lot` 에 `lot_slot` 을 섞었다. 그 질의는 «키 순서의 앞»을 주므로 정렬은 «값 오름차순»
    이고, `count` 는 보인 값의 노드를 두 쪽에서 이름 부르는 원자 수다 (`gaps._names_node_sql`).

    🔴 **절단이 «둘»이고 따로 보고한다.** `scan_truncated` 는 「노드를 다 못 봤다」이고
    `values_truncated` 는 「값이 더 있는데 안 실었다」다. 모든 키로 묶으면 노드 하나가 값
    하나라 둘은 대개 같이 켜진다 -- 축 하나로 묶을 때 갈린다.
    """
    # The world asked is the declaration asked (총괄 5fec118bb ②): a type another world
    # declares used to pass here and be refused below as 「declares no keys」.
    (wanted_type,) = _declared_or_refused(
        [type], _collectable_types(world), reason="node_type_not_declared", what="type",
        world=world, argument="type")

    declared_keys = _declared_keys(wanted_type, world)
    # 🔴 [판정 524] SIBLING OF THE SEAT 521 FOLDED, IN THIS SAME FILE. Folding one seat and
    #   not the other is what makes a file read as 「already fixed」. `?key=` used to answer
    #   422 「'' 가 선언하지 않은 키입니다」 instead of 「every key」.
    from database import crud as _crud

    if not _crud.is_blank_value(key) and key not in declared_keys:
        raise HTTPException(status_code=422, detail={
            "reason": "key_not_declared", "unknown": [key],
            "declared": sorted(declared_keys), "type": wanted_type,
            "message": "'%s' does not declare the key %s - pick one from 'declared'"
                       % (wanted_type, key)})

    connection = db.connection()
    names = _worlds(world)
    _ledgers_present(connection, names)
    relation = schema.walk_relation(names)

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
            "message": "'%s' declares no keys, so its subjects cannot be counted - "
                       "declare its keys" % wanted_type})

    # 🔴 [총괄 bccbdd601] EVERY ANSWER SAYS WHICH KEY THE FIRST LETTERS SEARCH, starts_with or not - the
    #   screen asks once with none to learn which key box its search box stands for.
    case = gaps.prefix_case(connection)
    prefix_axis, prefix_refusal = _prefix_axis(connection, relation, wanted_type, declared_keys, case)
    prefixed = not _crud.is_blank_value(starts_with)
    if prefixed and prefix_refusal:
        raise HTTPException(status_code=422, detail={
            "reason": "prefix_axis_not_text", "type": wanted_type, "message": prefix_refusal})
    if prefixed and key and key != prefix_axis:
        raise HTTPException(status_code=422, detail={
            "reason": "prefix_on_another_key", "type": wanted_type, "key": key, "prefix_axis": prefix_axis,
            "message": "starts_with searches '%s', the first key of '%s' - not '%s'"
                       % (prefix_axis, wanted_type, key)})

    budget = limit + 1 if set(grouping) == set(declared_keys) else KEY_VALUE_SCAN_NODES
    # `::text` keeps each node's keys exactly as stored - a float round trip through Python
    # could name a node nobody has, and its count would read 0.
    nodes = [row[0] for row in connection.exec_driver_sql(
        "SELECT keys::text FROM (%s) n" % gaps._nodes_of_type_sql(case if prefixed else None).format(
            table=relation),
        {"bare": wanted_type, "scan": budget + 1, "axis": prefix_axis, "p": starts_with,
         "plen": len(starts_with or ""),
         "nulls": json.dumps({name: None for name in declared_keys})}).fetchall()]
    params = {"bare": wanted_type, "nodes": "[" + ",".join(nodes[:budget]) + "]",
              "limit": limit + 1}
    # Key NAMES are bound, never interpolated - they came from the declaration, and
    # binding them keeps that true no matter what a declaration is allowed to contain.
    selected = []
    for index, name in enumerate(grouping):
        params["k%d" % index] = name
        # 🔴 `->` NOT `->>`. The text extractor turns the ledger's 0.0 into "0.0", the
        # canonical seed id writes those two differently, and the walk then answers a seed
        # nobody has - measured 2026-09-06: composite seeds 8/8 empty, the same 8 ready
        # once the type survives. A key's TYPE is part of its identity here.
        selected.append("k.keys -> %%(k%d)s AS v%d" % (index, index))
    columns = ", ".join("v%d" % index for index in range(len(grouping)))
    # jsonb `->` gives SQL NULL for a missing key and `'null'::jsonb` for a declared one
    # holding JSON null; neither is a value a seed can carry, and they are different rows.
    not_null = " AND ".join("v%d IS NOT NULL AND v%d <> 'null'::jsonb" % (index, index)
                            for index in range(len(grouping)))

    rows = connection.exec_driver_sql(
        "SELECT " + columns + ", sum(n) AS n FROM ("
        "  SELECT " + ", ".join(selected) + ", (SELECT count(*) FROM " + relation + " e"
        "   WHERE " + gaps._names_node_sql("e", "k.keys") + ") AS n"
        "  FROM jsonb_array_elements(%(nodes)s::jsonb) AS k(keys)"
        ") w WHERE " + not_null + " GROUP BY " + columns +
        " ORDER BY " + columns + " LIMIT %(limit)s",
        params,
    ).fetchall() if nodes else []

    return {
        "type": wanted_type, "key": key, "keys": grouping,
        "nodes": [{"keys": {name: row[index] for index, name in enumerate(grouping)},
                   "count": int(row[-1])} for row in rows[:limit]],
        # ⚠️ THIS SAYS WHAT IT MEASURED, AND `seedable` DID NOT. The old name claimed the
        # combination would seed a walk, which this route never checked and which was
        # FALSE for every composite subject while the values came back as text. Key
        # coverage is what a set comparison can know; whether the walk answers is a
        # different question and belongs to whoever asks it.
        "covers_declared_keys": set(grouping) == set(declared_keys),
        "scanned": min(len(nodes), budget),
        # 🔴 TWO CUTS, SAID SEPARATELY - see the docstring for when they part.
        "scan_truncated": len(nodes) > budget,
        "values_truncated": len(rows) > limit,
        "limits": {"scan_nodes": budget, "values": limit},
        "order": "value_asc",
        "starts_with": starts_with if prefixed else None,
        "prefix_axis": prefix_axis, "prefix_case": case, "prefix_refusal": prefix_refusal,
    }


def _declared_keys(bare_type: str, world=None) -> set:
    """The keys THIS type declares -- the same list `/declaration` publishes.

    🔴 Read, never restated: a key list held here would answer differently from the
    catalogue on the day an entity gains a key, and the caller reads both.
    """
    try:
        declared = (_declaration(world) or {}).get("entities") or {}
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable while resolving keys: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"The declaration could not be read: {exc} - fix the declaration and reload"})
    for name, spec in declared.items():
        if _bare_name(name) == bare_type:
            return {str(k) for k in ((spec or {}).get("keys") or [])}
    return set()


def _declared_or_refused(names, declared, *, reason, what, world, argument):
    """🔴 THE ONE SEAT FOR A NAME A WALK REQUEST BRINGS (총괄 17b6337e4): folded by `bare_name` - a
    saved board or a bookmark still says `x@1` - and refused by name, with what IS declared in
    the picked worlds, when it is not there. Never answered with an empty walk. Returns the
    names folded, in the order asked."""
    folded = [_bare_name(name) for name in names]
    unknown = sorted(set(folded) - set(declared))
    if unknown:
        named = ", ".join(each.name for each in _worlds(world))
        raise HTTPException(status_code=422, detail={
            "reason": reason, "argument": argument, "unknown": unknown,
            "declared": sorted(declared), "world": named,
            "message": "%s %s is not declared in world %s - pick one from 'declared'"
                       % (what, ", ".join("'%s'" % each for each in unknown), named)})
    return folded


def _expanded_bundle(item, world=None):
    """`<node id>|<predicate>|<direction>` with its predicate through `_declared_or_refused`; a
    shape that is not three parts goes on to the walk, which refuses it by its own words."""
    parts = str(item).split("|")
    if len(parts) != 3 or not parts[1].strip():
        return item
    (parts[1],) = _declared_or_refused(
        [parts[1]], _followable_predicates(world), reason="predicate_not_declared",
        what="predicate", world=world, argument="expand")
    return "|".join(parts)


def _value_names(world=None):
    """Every name `group_by` and `measure` may read a value under - the fold's sources
    (`ledger_subgraph.VALUE_SOURCES`): an entity's keys and attributes, a predicate's
    qualifiers, a predicate itself (the claims a node carries). Read from the picked worlds'
    declaration."""
    try:
        declared = _declaration(world) or {}
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable while resolving value names: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"The declaration could not be read: {exc} - fix the declaration and reload"})
    names = set()
    for key, item in (declared.get("vocabulary") or {}).items():
        names.add(_bare_name(key))
        qualifiers = ((item or {}).get("object") or {}).get("qualifiers") or {}
        names |= {str(name) for name in (*(qualifiers.get("required") or ()),
                                         *(qualifiers.get("optional") or ()))}
    for item in (declared.get("entities") or {}).values():
        names |= {str(name) for name in (*((item or {}).get("keys") or ()),
                                         *((item or {}).get("attributes") or ()))}
    return names


def _collectable_types(world=None):
    """Every node type a caller may name in `collect` -- read from the DECLARATION, only.

    🔴 THE SAME AUTHORITY `/declaration` PUBLISHES, not a second copy. That route already
    answers "what may I ask for" out of `entities`, and a list restated here would be a
    second author for one fact: declaring an entity would make it collectable on one
    surface and refused on the other.

    Versions are stripped so `defect` and `defect@1` are the same answer -- the caller
    should not have to know which spelling the declaration happens to use.
    """
    try:
        declared = (_declaration(world) or {}).get("entities") or {}
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable while resolving collect: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"The declaration could not be read: {exc} - fix the declaration and reload"})
    return {_bare_name(name) for name in declared}




#: PostgreSQL `undefined_table`. The one fact about a missing relation that is
#: not translated.
SQLSTATE_UNDEFINED_TABLE = "42P01"


def _is_undefined_table(exc) -> bool:
    """True when `exc` (or the driver error SQLAlchemy wrapped) is a 42P01."""
    for candidate in (getattr(exc, "orig", None), exc):
        if getattr(candidate, "pgcode", None) == SQLSTATE_UNDEFINED_TABLE:
            return True
    return False


def _relation_absent(relation) -> HTTPException:
    """The absent-relation refusal, in ONE spelling for both raisers.

    🔴 THE BODY IS STRUCTURED, NOT PROSE. Ruling R-2026-08-13-C: `reason` is
    prose for humans, and any fact the screen must BRANCH on goes out as a
    structured field. So the client reads `detail.reason`, the operator reads
    `detail.message`, and nobody has to parse Korean to tell "not deployed" from
    "no such lot". `state` repeats `GET /coverage`'s vocabulary on purpose — one
    word means one thing across both endpoints.
    """
    logger.warning("ledger relation missing: %s", relation)
    return HTTPException(status_code=503, detail={
        "reason": trace.REASON_RELATION_ABSENT,
        "state": "absent",
        "relation": relation,
        "message": (f"Ledger table {relation} is missing - run "
                    f"server/migrations/add_ledger_events.py"),
    })














@router.get("/gaps")
def ledger_gap_catalogue(name: str = Query(None),
                         world: list[str] | None = Query(
                             None, description="Ledger worlds, repeated (world=a&world=c); none = the operating world")):
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
    from ledger import gaps as _gaps

    try:
        declared = _declaration(world) or {}
    except Exception as exc:                       # noqa: BLE001
        logger.error("declaration unreadable: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"The declaration could not be read: {exc} - fix the declaration and reload"})

    try:
        # 🔴 [판정 521] SAME SEAT SHAPE, SAME FOLD. `?name=` is `''` here too, and this
        #   route would fall through to the measured branch and count a question nobody
        #   asked. One spelling for emptiness, per the standing rule.
        from database import crud

        if crud.is_blank_value(name):
            asked = _gaps.questions(declared)
            return {"mode": "names", "count": len(asked), "gaps": asked}
        from database.database import engine
        return {"mode": "measured", "count": 1,
                "gaps": _gaps.measure(engine, declared, only=name,
                                      relation=schema.walk_relation(_worlds(world)))}
    except _gaps.GapQuestionUnknown as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except _gaps.GapTableMismatch as exc:
        # 503, not 500: the declaration and the spec disagree, which is a DEPLOYMENT fact
        # somebody has to fix in one of the two - not a failure of this request.
        raise HTTPException(status_code=503, detail={
            "reason": "gap_table_mismatch", "message": str(exc)})


def _row_census_by_source(world=None):
    """Every source's stored census, by source id - one query per world of the chain, no
    counting.

    ⚠️ FAILURE HERE COSTS THE CENSUS AND NOT THE CATALOGUE. The declaration answers from the
    DECLARATION; the census is a ledger table that may not exist yet on a fresh install, and
    a route that 500s because an optional column is missing would take the four dropdowns
    down with it.
    """
    try:
        from sqlalchemy import text

        from database.database import engine

        # Each source from the world whose declaration it is read from - the first asked
        # that declares it (총괄 092a6f9e5) - and the line names that world.
        whose = _declaration_and_whose(world)[1].get("sources", {})
        out = {}
        with engine.connect() as connection:
            for names in _worlds(world):
                for source, census in connection.execute(text(
                        f"SELECT source, {schema.ROW_CENSUS_COLUMN} FROM {names.cursor} "
                        f"WHERE {schema.ROW_CENSUS_COLUMN} IS NOT NULL")).all():
                    if whose.get(source) == names.name:
                        out[source] = {**census, "world": names.name}
        return out
    except Exception as exc:                       # noqa: BLE001 - see the docstring
        logger.warning("row census unavailable: %s", exc)
        return {}


@router.get("/declaration")
def ledger_declaration_catalog(
        world: list[str] | None = Query(
            None, description="Ledger worlds, repeated (world=a&world=c); none = the operating world")):
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
        declared, whose = _declaration_and_whose(world)
    except Exception as exc:                       # noqa: BLE001 - same backstop as /kinds
        logger.error("declaration unreadable: %s", exc)
        raise HTTPException(status_code=503, detail={
            "reason": "declaration_unreadable",
            "message": f"The declaration could not be read: {exc} - fix the declaration and reload"})

    # 🔴 `class` IS CARRIED, NOT DECIDED HERE. The walk refuses a step from a static type
    # to a dynamic one (`_static_step_predicates`), and a client deriving paths from the
    # type graph alone cannot know that - so the route list offers walks that come back
    # with the seed and nothing else. The value published is the one `_static_types(world)`
    # already reads, so declaring a type static changes both at once and neither can
    # drift from the other.
    #
    # ⚠️ AN ENTITY THAT DECLARES NO CLASS PUBLISHES `None`, NOT "dynamic". "I was not
    # told" and "I was told it is dynamic" are different facts, and filling the first
    # with the second is the exact shape this route exists to avoid - the reader would
    # then draw a path the walk may still refuse, with no way to know it guessed.
    # 🔴 `attributes` RIDES HERE SO NO SCREEN HAS TO NAME ONE (S-52). The walk's table gets
    # a column per attribute, and the only authority for which names exist is this
    # declaration - a client holding its own list would be right until the day an
    # operator adds one, and then quietly short. ABSENT rather than empty when the type
    # declares none, so a reader can tell "this type carries no values" from "this
    # deployment predates the axis".
    # 🔴 [총괄 07889c83d] `class` IS A LIST ON THE WIRE, read by `setup_bundle.class_words` -
    #   the one reader of 「one word or a list」 - so no screen interprets the shape again.
    from ledger import setup_bundle

    entities = []
    for name, spec in sorted((declared.get("entities") or {}).items()):
        item = {"type": name, "keys": list((spec or {}).get("keys") or []),
                "class": list(setup_bundle.class_words(spec)) or None,
                "world": whose["entities"][name]}
        attributes = (spec or {}).get("attributes")
        if attributes:
            item["attributes"] = [str(entry) for entry in attributes]
        entities.append(item)
    # 🔴 `absence_confirmed_by` RIDES HERE SO A SCREEN CAN TELL WHICH PREDICATE IS THE
    # EXAMINATION (S-216, 판정 366). S-149 folds an `absence` verdict onto every node, and a
    # column drawn from the nodes alone takes its POPULATION FROM THE DATA - it shows the
    # predicates that happened to arrive, which is the exact misreading that cell exists to
    # prevent. The declaration is the population, and this is where a client reads it.
    #
    # ⚠️ OMITTED, NOT EMPTIED - the same discipline as `class` and `attributes` above. 「this
    # predicate declares no confirmer」 and 「this deployment predates the axis」 are different
    # facts, and an empty string would collapse them into one.
    predicates = []
    for name, spec in sorted((declared.get("vocabulary") or {}).items()):
        item = {"name": name,
                "subjects": list((spec or {}).get("subjects") or []),
                "object": (spec or {}).get("object") or {},
                "origin": "vocabulary",
                "class": list(setup_bundle.class_words(spec)) or None,
                "world": whose["vocabulary"][name]}
        confirmer = (spec or {}).get("absence_confirmed_by")
        if confirmer:
            item["absence_confirmed_by"] = str(confirmer)
        predicates.append(item)
    # 🔴 THE SAME ARRAY, THE SAME SHAPE. A reference edge is followable, so the
    # catalogue must offer it - and in `predicates[]` rather than a second array, because a
    # client that had to read two arrays would grow a branch. `origin` tells them apart for
    # anyone who needs it; nobody has to look. `subjects` are the declaration's names as read -
    # bare - and the client filters options by them as sent (클라 96855816b).
    from ledger.backfill import CENSUS_NAMES
    catalogue = {
        "state": "ready" if entities else "empty",
        "entities": entities,
        "predicates": predicates,
        # What each `sources[].census` word is called on a screen (lead bed890af2). A
        # vocabulary, not data, so it rides whether or not the setup compiles.
        "census_names": dict(CENSUS_NAMES),
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
        from ledger.event_frame import base_select_columns
        from ledger.setup_bundle import emitted_predicates

        plans, planned_in, vocabulary_of = {}, {}, {}
        for names in _worlds(world):
            snapshot = load_setup(names.declaration_root).snapshot
            for source_id, plan in snapshot.source_plans.items():
                if source_id not in plans:
                    plans[source_id], planned_in[source_id] = plan, names.name
                    vocabulary_of[source_id] = snapshot.vocabulary
        declared_sources = declared.get("sources") or {}
        # 🔴 READ, NEVER COUNT (D5, 판정 180). 「표 행 N · 색인 M · 남은 N−M」 is two scans --
        # `count(*)` on a relation that may hold ten million rows and
        # `count(DISTINCT row_id)` on the index -- and a request that did them would be a
        # screen that waits for a table. The paced job `ledger_row_census` measures and
        # STAMPS; this reads the stamp.
        #
        # ⛔ ABSENT MEANS 「not measured yet」, NOT zero. A source whose census key is missing
        # has never been swept (a fresh install, a source declared minutes ago), and a 0
        # there would tell an operator their table is empty. The key is omitted rather than
        # filled, which is the same three-state discipline the `sources` key itself uses
        # eight lines up.
        census = _row_census_by_source(world)
        catalogue["sources"] = [
            {
                "source": source_id,
                "relation": plan.relation,
                "world": planned_in[source_id],
                # 🔴 REPORTED, NOT FILTERED (S-103). A retired source still has atoms and an
                # operator who retired it needs to see that it is there and no longer
                # moving; dropping it from this list would look like the declaration lost
                # it. The live path is what stops reading it.
                "status": plan.status,
                # 🔴 RETIRED MEANS 「THE CONTENT WAS NOT JUDGED」, AND THE SCREEN SAYS SO
                # (S-177 ①). The validator stops reading a retired source's clauses, so
                # its bindings may name a column the table no longer has -- true and
                # harmless, but an operator reading the same panel as an active source
                # would have no way to know the list beside it was never checked. The flag
                # rides only when it is false, so an active source is byte-identical to
                # what it published before.
                **({"content_validated": False} if plan.status != "active" else {}),
                # 🔴 TWO DIFFERENT FACTS, TWO FIELDS (S-177 ②). `status` is what the
                # OPERATOR wrote; `planned` is what the LOADER managed. A source whose
                # declaration is broken is still declared active, and folding that into
                # `status` would tell the screen an operator retired it.
                **({"planned": False,
                    "refusal": dict(plan.refusal or {})} if not plan.planned else {}),
                "emits": emitted_predicates(declared_sources.get(source_id),
                                            declared.get("entities"), vocabulary_of[source_id]),
                # ⛔ OMITTED, NOT EMPTIED, ON A RETIRED SOURCE. This list is compiled
                # from the read plan, and a retired source has none; `[]` would say 「reads
                # no columns」, which is a different and false fact.
                **({"scope_columns": list(base_select_columns(plan))}
                   if plan.runs else {}),
                **({"census": census[source_id]} if source_id in census else {}),
            }
            for source_id, plan in sorted(plans.items())
        ]
    except Exception as exc:                       # noqa: BLE001 - see the note above
        logger.error("declaration sources unavailable: %s", exc)
    # 총괄 8d10633ae ㉢ · e51e3e417: the worlds there are and the operating one ride the
    # response the screen already reads.
    catalogue.update(schema.world_listing())
    return catalogue










