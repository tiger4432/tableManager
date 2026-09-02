"""EVERY COLUMN TYPE a virtual-join `expose` can name, through the read surface (N8).

[Why this file exists as a CLASS and not as a second copy of test_virtual_join_numeric]
N7 shipped as "a numeric column needs a cast". That framing is why the round closed with
`datetime` holding the identical defect: the label in `COALESCE(<parts>, '<label>')` is
TEXT, so the property that breaks is "this part is not text", and `number` was only the
first type to walk into it. QA reproduced the second one on PostgreSQL 18.3 on 2026-08-04
(`InvalidDatetimeFormat`), and a third - `boolean` - was found by enumerating instead of
waiting (`InvalidTextRepresentation`, same server, same day).

[The enumeration, and why it is an assertion rather than a comment]
`models.init_dynamic_models` is the only thing that decides what type an exposed column
can have. It maps `column_types` to Float / DateTime(timezone=True) / String, and the
shared metadata columns add Boolean and DateTime. `virtual_join_config` validates
`expose` against `column_types` KEYS, and the model builder SKIPS metadata names while
the metadata column keeps existing - so declaring `"needs_graph_rollback": "..."` yields a
Boolean expose column through an ordinary declaration. `test_the_expose_type_universe_is_
exactly_what_this_file_covers` pins that list: a fourth type appearing in the mapper turns
this file red instead of turning a production read into a 500.

[RED before the fix, per type, measured 2026-08-04]
  string   : green already (unchanged funnel arm).
  number   : green already (N7).
  datetime : SQLite `ValueError: Invalid isoformat string: '미상'` - SQLAlchemy hands the
             label to the DateTime result processor. PostgreSQL 18.3
             `InvalidDatetimeFormat: invalid input syntax for type timestamp with time
             zone: ""`. A crash on BOTH dialects.
  boolean  : PostgreSQL 18.3 `InvalidTextRepresentation` on both `COALESCE(bool, text)`
             and `blank_to_null`'s `bool = ''`. On SQLite it does NOT crash - it answered
             `True` for the UNMATCHED row, i.e. every unresolved cell claimed a value and
             a search for 미상 returned nothing. The quiet one is the dangerous one.

[격리] 테이블명 접두 `vjt_test_` ― 사용자 gitignored config에 실존할 수 없다.
[승인 대역] sqlite에서 `unique_index_covering`은 항상 None이라(모르면 거부) 대역 없이는
조인이 0건이고 모든 테스트가 헛통과한다 ― `test_virtual_join_numeric.py`와 같은 대역.
[시딩] datetime/boolean 컬럼은 **쓰기 깔때기를 통과할 수 없다** ― `cast_value_by_type`에
datetime 분기가 없어 문자열을 반환하고, SQLite의 DATETIME 바인딩이 그것을 거부한다.
그래서 오른쪽 행은 모델 객체로 직접 시딩한다(계약 파일의 `through_funnel=False`와 같은
자세). 그 사실 자체가 별도 보고 항목이다.
"""
import csv
import datetime
import io
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

LABEL = "미상"

# Two instants that pin the two halves of the canonical format: one with a non-zero
# microsecond field, one with a zero one (PostgreSQL's default cast DROPS the fractional
# part for the second and keeps it for the first - which is exactly why the format is
# pinned rather than inherited).
T_MICRO = datetime.datetime(2026, 8, 4, 6, 23, 39, 123456)
T_ZERO = datetime.datetime(1999, 1, 2, 3, 4, 5, 0)
T_MICRO_TEXT = "2026-08-04 06:23:39.123456"
T_ZERO_TEXT = "1999-01-02 03:04:05.000000"

TYPE_TABLES = {
    "vjt_test_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string",
            # collide AND temporal - the one shape whose left-owned cells cannot be made
            # to agree without breaking the "a lost join changes nothing" invariant.
            "stamp_at": "datetime",
        },
    },
    "vjt_test_ref": {
        "business_key": "ref_key",
        "column_types": {
            "ref_key": "string", "core_lot": "string",
            "site": "string",           # string     - the arm that was already correct
            "slot_no": "number",        # Float      - N7's arm, kept in the class
            "event_at": "datetime",     # DateTime   - N8, virtual_only
            "stamp_at": "datetime",     # DateTime   - N8, collide
            # A metadata NAME declared in column_types: the model builder skips it and the
            # shared Boolean metadata column answers instead. This is the only way a
            # Boolean reaches `expose`, and it is reachable from an ordinary config.
            "needs_graph_rollback": "string",
        },
    },
}

DECL = {
    "vjt_rule": {
        "left_table": "vjt_test_log", "right_table": "vjt_test_ref",
        "join_key": [{"left": "core_lot", "right": "core_lot"}],
        "expose": ["site", "slot_no", "event_at", "stamp_at", "needs_graph_rollback"],
    }
}


@pytest.fixture()
def type_env(db_session, client, tmp_path, monkeypatch):
    models.init_dynamic_models(TYPE_TABLES)
    crud.TABLE_CONFIG.update(TYPE_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    p = tmp_path / "virtual_join_rules.json"
    p.write_text(json.dumps(DECL), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, columns: "uq_fake"
                        if table == "vjt_test_ref" else None)
    vjx.reset_cache()
    import main
    main.TABLE_COUNT_CACHE.clear()

    # 🔴 CORE inserts, not ORM `add()`. The `before_flush` outbox listener
    # (`database.database.auto_stage_database_outbox`) copies the row's attribute values
    # into a JSON payload, and a real `datetime` attribute is not JSON serializable - so
    # an ORM insert of a temporal column dies before the join is ever exercised. In
    # production the write funnel stores a STRING in these columns
    # (`cast_value_by_type` has no datetime branch and PostgreSQL casts on the way in),
    # so nothing hits it there; here we want the column to actually HOLD a datetime.
    right = models.DYNAMIC_TABLES["vjt_test_ref"].__table__
    left = models.DYNAMIC_TABLES["vjt_test_log"].__table__
    db_session.execute(right.insert(), [
        # R1 - every type carries a value
        dict(row_id="r1", ref_key="K1", business_key_val="K1", core_lot="LOT-A",
             site="FAB1", slot_no=3.0, event_at=T_MICRO, stamp_at=T_MICRO,
             needs_graph_rollback=True),
        # R2 - the FALSE boolean and the zero-microsecond timestamp. False is a VALUE,
        # not a blank, and a renderer that folds it into the label loses half the domain.
        dict(row_id="r2", ref_key="K2", business_key_val="K2", core_lot="LOT-B",
             site="FAB2", slot_no=2.5, event_at=T_ZERO, stamp_at=None,
             needs_graph_rollback=False),
        # R3 - right row EXISTS, every exposed value NULL: case (2) of 미상, per type.
        dict(row_id="r3", ref_key="K3", business_key_val="K3", core_lot="LOT-C",
             site=None, slot_no=None, event_at=None, stamp_at=None,
             needs_graph_rollback=None),
    ])
    db_session.execute(left.insert(), [
        dict(row_id="l1", log_id="L1", business_key_val="L1", core_lot="LOT-A", stamp_at=None),
        dict(row_id="l2", log_id="L2", business_key_val="L2", core_lot="LOT-B", stamp_at=None),
        dict(row_id="l3", log_id="L3", business_key_val="L3", core_lot="LOT-C", stamp_at=None),
        # L4 has no right row at all: case (1) of 미상.
        dict(row_id="l4", log_id="L4", business_key_val="L4", core_lot="LOT-Z", stamp_at=None),
        # L5 owns its OWN collide timestamp and has no right row - absent-only says the
        # left value wins, and the join must not touch that cell.
        dict(row_id="l5", log_id="L5", business_key_val="L5", core_lot="LOT-Y",
             stamp_at=T_ZERO),
    ])
    db_session.commit()
    yield client
    vjx.reset_cache()
    main.TABLE_COUNT_CACHE.clear()


def _payload(client, col):
    r = client.get("/tables/vjt_test_log/data", params={"limit": 500})
    assert r.status_code == 200, r.text
    out = {}
    for d in r.json()["data"]:
        cell = d["data"].get(col)
        out[d["data"]["log_id"]["value"]] = cell["value"] if isinstance(cell, dict) else None
    return out


def _sql(db, col):
    m = models.DYNAMIC_TABLES["vjt_test_log"]
    q = db.query(m.row_id)
    q, expr, _label = vjx.resolved_expression(db, m, "vjt_test_log", col, q)
    assert expr is not None, f"no resolved expression for exposed column {col!r}"
    return {r[0]: r[1] for r in q.with_entities(m.log_id, expr).all()}


def _get(client, **params):
    r = client.get("/tables/vjt_test_log/data", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    return {d["data"]["log_id"]["value"] for d in body["data"]}, body["total"]


def _filters(col, ftype, val=None):
    spec = {"type": ftype}
    if val is not None:
        spec["filter"] = val
    return json.dumps({col: spec})


# ---------------------------------------------------------------------------
# The enumeration itself
# ---------------------------------------------------------------------------

def test_the_expose_type_universe_is_exactly_what_this_file_covers(type_env):
    """A fourth SQLAlchemy type reaching an expose column must turn THIS red.

    Read out of the live model rather than out of `models.py`'s source: the point is what
    a declaration can actually produce, and a rewritten mapper that produces a Numeric or
    a JSON column would satisfy any grep-based version of this check.
    """
    from sqlalchemy.sql import sqltypes
    right = models.DYNAMIC_TABLES["vjt_test_ref"]
    got = {c: type(getattr(right, c).type).__name__
           for c in TYPE_TABLES["vjt_test_ref"]["column_types"]}
    assert got == {
        "ref_key": "String", "core_lot": "String", "site": "String",
        "slot_no": "Float", "event_at": "DateTime", "stamp_at": "DateTime",
        "needs_graph_rollback": "Boolean",
    }, f"the declaration->type mapping changed: {got}"

    # And every one of them must leave `column_text_sql` as a TEXT expression. This is
    # the property the COALESCE actually needs; the type names above are only how we got
    # here.
    for col in got:
        expr = crud.column_text_sql(getattr(right, col))
        assert isinstance(expr.type, sqltypes.String), (
            f"{col} renders to {expr.type!r}, which cannot sit beside a text label")


def test_a_type_the_funnel_has_never_heard_of_is_cast_not_passed_through():
    """The no-crash floor. `column_text_sql` decides by asking "is this ALREADY text",
    so a type added tomorrow gets a CAST rather than reopening N7/N8 a third time."""
    from sqlalchemy import Column, LargeBinary, JSON, Enum
    from sqlalchemy.sql import sqltypes
    for col in (Column("blob_col", LargeBinary), Column("json_col", JSON),
                Column("enum_col", Enum("a", "b", name="probe_enum"))):
        expr = crud.column_text_sql(col)
        assert isinstance(expr.type, sqltypes.String), f"{col.name} was not rendered to text"
        assert "CAST" in str(expr.compile(compile_kwargs={"literal_binds": True})).upper(), (
            f"{col.name} reached the COALESCE without a cast - this is the N7/N8 shape")


# ---------------------------------------------------------------------------
# 🔴 datetime - the live crash N8 names
# ---------------------------------------------------------------------------

def test_a_temporal_expose_column_can_be_read_at_all(type_env, db_session):
    """RED before this round on BOTH dialects: SQLite raised
    `ValueError: Invalid isoformat string: '미상'` from the DateTime result processor,
    PostgreSQL 18.3 raised `InvalidDatetimeFormat`. Every read that named the column -
    grid page, `?q=`, column filter, CSV export - was a 500."""
    got = _sql(db_session, "event_at")
    assert got["L1"] == T_MICRO_TEXT
    assert got["L2"] == T_ZERO_TEXT
    assert got["L3"] == LABEL, "right row exists, value NULL - case (2) of 미상"
    assert got["L4"] == LABEL, "no right row - case (1) of 미상"


def test_the_temporal_text_is_pinned_not_the_dialects_default(type_env, db_session):
    """The canonical spelling: UTC, space separator, SIX microsecond digits, always.

    PostgreSQL's own `CAST(timestamptz AS varchar)` renders in the SESSION's timezone and
    omits the fractional part when it is zero - so two servers holding the same row would
    compare different text. `T_ZERO` is in this corpus for exactly that second half.
    """
    got = _sql(db_session, "event_at")
    assert got["L2"] == T_ZERO_TEXT, (
        "a whole-second timestamp lost its .000000 - the dialect default leaked in")
    assert crud.temporal_text_value(T_MICRO) == T_MICRO_TEXT
    assert crud.temporal_text_value(T_ZERO) == T_ZERO_TEXT
    # An aware value is normalised to UTC, so the text does not follow a session GUC.
    aware = T_MICRO.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
    assert crud.temporal_text_value(aware) == "2026-08-03 21:23:39.123456"


def test_the_grid_and_the_search_spell_a_timestamp_the_same_way(type_env, db_session):
    """The acceptance criterion for a temporal column: what the browser paints is what a
    filter compares. The payload is rendered through `crud.resolved_text_value` for
    exactly this reason - a raw datetime would reach the browser as FastAPI's
    `.isoformat()`, whose offset follows the DB session timezone."""
    payload, sql = _payload(type_env, "event_at"), _sql(db_session, "event_at")
    for log_id, shown in payload.items():
        assert shown == sql[log_id], (
            f"event_at/{log_id}: grid displays {shown!r}, search compares {sql[log_id]!r}")


def test_filtering_a_temporal_column_by_what_the_grid_shows_finds_the_row(type_env):
    """⚠️ WEAK ON THIS DIALECT, and saying so is the point. Injecting the pre-fix
    `_text_part` leaves this test GREEN on SQLite: the filter path wraps the whole
    expression in `cast(..., String)` (`main.get_column_filter_condition`), which hides
    the result-processor crash, and SQLite's DATETIME storage text happens to equal the
    pinned format. On PostgreSQL the pre-fix expression raises inside the server before
    any outer cast applies (`InvalidDatetimeFormat`, measured 18.3). The decisive
    SQLite-side assertions are the `_sql`/payload ones above."""
    ids, total = _get(type_env, filters=_filters("event_at", "equals", T_MICRO_TEXT))
    assert ids == {"L1"} and total == 1
    ids, total = _get(type_env, filters=_filters("event_at", "contains", "2026-08-04"))
    assert ids == {"L1"} and total == 1
    ids, total = _get(type_env, filters=_filters("event_at", "equals", LABEL))
    assert ids == {"L3", "L4", "L5"} and total == 3


def test_q_search_reaches_a_temporal_virtual_column(type_env):
    ids, total = _get(type_env, q="1999-01-02 03:04:05.000000", cols="event_at")
    assert ids == {"L2"} and total == 1


def test_export_carries_the_temporal_virtual_column_in_the_pinned_spelling(type_env):
    r = type_env.get("/tables/vjt_test_log/export")
    assert r.status_code == 200, r.text
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    assert "event_at" in header
    by_id = {rec["log_id"]: rec for rec in (dict(zip(header, row)) for row in body if row)}
    assert by_id["L1"]["event_at"] == T_MICRO_TEXT, "the CSV must say what the screen says"
    assert by_id["L2"]["event_at"] == T_ZERO_TEXT
    assert by_id["L3"]["event_at"] == LABEL and by_id["L4"]["event_at"] == LABEL


# ---------------------------------------------------------------------------
# 🔴 boolean - the crash on PostgreSQL, the SILENT WRONG ANSWER on SQLite
# ---------------------------------------------------------------------------

def test_a_boolean_expose_column_does_not_claim_a_value_it_does_not_have(type_env, db_session):
    """RED before this round: on SQLite every row - including the ones with NO right row -
    came back `True`, because SQLAlchemy's Boolean result processor turned the label into
    `bool('미상')`. On PostgreSQL 18.3 the same expression raised
    `InvalidTextRepresentation`. The SQLite symptom is the one worth naming: 미상 became
    unfindable and every unresolved cell asserted a value."""
    got = _sql(db_session, "needs_graph_rollback")
    assert got["L1"] == "true"
    assert got["L2"] == "false", "False is a VALUE - folding it into the label loses half the domain"
    assert got["L3"] == LABEL, "right row exists, value NULL"
    assert got["L4"] == LABEL, "no right row at all - this is the one that used to say True"


def test_the_boolean_render_twin_spells_it_the_way_sql_does(type_env, db_session):
    """`'true'`, not Python's `'True'`. `clean_str_value(True)` is `'True'`, the one
    spelling no operator ever sees - the N9 lesson applied before it can bite.

    Scored on `attach`'s OWN output rather than on the HTTP payload, because of the fact
    the next test pins: on the wire the cell is already taken.
    """
    import virtual_join_executor as vjx_
    got = {}
    for rid, log_id in (("l1", "L1"), ("l2", "L2"), ("l3", "L3"), ("l4", "L4")):
        entry = [{"row_id": rid, "data": {}}]
        vjx_.attach(db_session, "vjt_test_log", entry)
        cell = entry[0]["data"].get("needs_graph_rollback")
        got[log_id] = cell["value"] if isinstance(cell, dict) else None
    sql = _sql(db_session, "needs_graph_rollback")
    assert got["L1"] == "true" and got["L2"] == "false"
    for log_id, shown in got.items():
        assert shown == sql[log_id], (
            f"needs_graph_rollback/{log_id}: the payload twin says {shown!r}, "
            f"search compares {sql[log_id]!r}")
    assert crud.boolean_text_value(True) == "true"
    assert crud.clean_str_value(True) == "True", (
        "if this ever became 'true', the two spellings merged and the comment above is stale")


def test_a_graph_meta_boolean_never_reaches_the_payload_because_the_cell_is_taken(type_env):
    """MEASURED SCOPE for the boolean arm, so the fix is not read as wider than it is.

    `fetch_and_merge_metadata` injects `is_graph_synced` / `needs_graph_rollback` /
    `graph_synced_at` as pseudo-cells on EVERY row before `attach` runs, so for these
    three names the left cell always exists and always holds a value - and absent-only
    therefore always keeps it. A Boolean expose column consequently reaches the SQL half
    of the seam (filter, `?q=`, CSV export - the half that 500s on PostgreSQL) but never
    the grid cell.

    Pinned because it decides where the boolean fix matters. If the injection ever moves
    after `attach`, this goes red and the payload assertions above become the live ones.

    🔴 KNOWN RED SINCE 2026-09-02, AND THE RED IS THE CORRECT SIGNAL. Do not repair this
    test to make it green. Recorded on the lead PM's ruling of the same night.

        WHY IT IS RED   the premise above - "the injected graph-meta cell always wins" -
                        was removed on purpose. `fetch_and_merge_metadata` no longer
                        injects `is_graph_synced` / `needs_graph_rollback` /
                        `graph_synced_at`; measured first, ZERO of the 44 live tables
                        declare any of the three, so every row of every page was carrying
                        three cells nobody had asked for.

        WHAT IT NOW SEES  `None`, not the join's `true`. That is NOT the new contract: it
                        is a BROKEN FIXTURE showing through. `attach` already failed here
                        at HEAD - "type object 'VjtTestRef' has no attribute
                        'needs_graph_rollback'" - and seven sibling tests in this file
                        were red for that same reason before the injection was removed.
                        The injected cell was OCCUPYING the seat, so the join's inability
                        to fill it could not be seen. Not "zero because absent" but
                        "zero because covered", which is the least visible kind here.

        WHAT IS BLOCKED  Retiring this test would remove the only cover over "a Boolean
                        expose column reaches the read surface"; its own text says the
                        payload assertions become the live ones, so what died is the
                        MECHANISM, not the assertion. Repairing the fixture is blocked on
                        a question nobody has answered yet:

        THE QUESTION    do REF models get the three metadata columns too?
                        yes -> the model builder is at fault, and fixing it turns the
                               seven siblings green with this one.
                        no  -> this fixture's expose list asks for something impossible,
                               a different Boolean sample is needed, and this file's own
                               claim at :83 - that an ordinary config reaches it too - is
                               FALSE on a ref.

        Asserting anything on top of today's `None` would freeze the broken half as the
        contract, which is why this is left failing and named instead.
    """
    payload = _payload(type_env, "needs_graph_rollback")
    assert payload["L1"] is False, (
        "the injected graph-meta cell no longer wins; re-scope the boolean arm")
    assert payload["L4"] is False, "an unmatched row keeps the injected default too"


def test_a_boolean_filter_value_arriving_as_a_bool_is_bridged(type_env):
    """AG-Grid sends a boolean-typed filter as a JSON boolean. Against a text-resolved
    expression that must compare as `'true'` - not error, not miss."""
    ids, total = _get(type_env, filters=json.dumps(
        {"needs_graph_rollback": {"type": "equals", "filter": True}}))
    assert ids == {"L1"} and total == 1
    ids, total = _get(type_env, filters=_filters("needs_graph_rollback", "equals", "false"))
    assert ids == {"L2"} and total == 1
    assert crud.comparison_text_value(True) == "true"
    assert crud.comparison_text_value(T_MICRO) == T_MICRO_TEXT


# ---------------------------------------------------------------------------
# The arms that were already correct - kept in the class so a refactor of the funnel
# cannot quietly drop one.
# ---------------------------------------------------------------------------

def test_string_and_number_arms_are_unchanged_by_the_funnel(type_env, db_session):
    site, slot = _sql(db_session, "site"), _sql(db_session, "slot_no")
    assert site["L1"] == "FAB1" and site["L3"] == LABEL and site["L4"] == LABEL
    assert slot["L1"] == "3", "N7's int spelling must survive the funnel"
    assert slot["L2"] == "2.5"
    assert slot["L3"] == LABEL and slot["L4"] == LABEL


# ---------------------------------------------------------------------------
# The one shape that CANNOT be made to agree - measured, not assumed
# ---------------------------------------------------------------------------

def test_a_collide_temporal_column_diverges_on_left_owned_cells_exactly_here(type_env, db_session):
    """DECLARED DIVERGENCE, and the pin is what keeps it from growing.

    A cell the join LOST must be byte-identical to what it would be without this feature
    (`_resolve_one`'s absent-only rule and the invariant recorded above it), so the left
    value stays a raw datetime and reaches the browser as FastAPI's `.isoformat()`. The
    SQL side renders the same column to `TEMPORAL_TEXT_FORMAT`. They therefore disagree
    on left-owned cells of a `collide` TEMPORAL column - and nowhere else.

    Scope, measured 2026-08-04: zero such declarations exist in the live config (the only
    `datetime` columns are `production_plan.created_at/updated_at`, and no rule exposes
    them). Closing it needs a declaration-time refusal of `collide` + non-text, which is a
    `virtual_join_config` change and a Lead PM call.
    """
    payload, sql = _payload(type_env, "stamp_at"), _sql(db_session, "stamp_at")
    agree = {k for k in payload if payload[k] == sql[k]}
    diverge = {k for k in payload if payload[k] != sql[k]}
    assert diverge == {"L5"}, (
        f"the collide-temporal divergence changed shape.\n"
        f"  recorded divergent: {{'L5'}} (the one left-owned cell)\n"
        f"  measured divergent: {diverge}\n"
        "Shrank -> it was closed and this pin now asserts nothing. Grew -> a second class "
        "of cell now paints one spelling and searches another. Both are Lead PM calls.")
    assert "L1" in agree, "join-owned cells must still agree"
    assert payload["L5"] == T_ZERO.isoformat(), "the left-owned cell is untouched, as designed"
    assert sql["L5"] == T_ZERO_TEXT


# ---------------------------------------------------------------------------
# The write refusal is a different funnel and must stay independent
# ---------------------------------------------------------------------------

def test_writes_to_the_temporal_virtual_only_column_are_still_refused(type_env):
    r = type_env.put("/tables/vjt_test_log/data/updates",
                     json={"updates": [{"updates": {"log_id": "L1", "event_at": "x"},
                                        "source_name": "user", "updated_by": "tester"}]})
    assert r.status_code == 400, (
        f"write refusal funnel must be untouched, got {r.status_code}: {r.text}")
    assert "event_at" in r.text
