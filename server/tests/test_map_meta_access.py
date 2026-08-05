"""«맵 규격 미등록» is THREE different facts, and two of them are not about the data.

`map_overlay.load_map_meta` returns `None` for three unrelated reasons:

  (a) the meta MODEL is not loaded - `wafer_map_metadata` is absent from the declared-table
      config;
  (b) the SELECT itself failed - the live table's columns no longer match the model (schema
      drift), or a prior failed statement aborted the transaction;
  (c) that (target_table, map_id) genuinely has no row.

Every caller collapsed the three, so the screen always said (c) - "register the map" about
maps that were already registered.

🔴 WHY THIS STOPPED BEING A LABELLING BUG AND BECAME A SAFETY ONE
Since [D4]/[D5] a map with NO spec row is the NORMAL case: it borrows the floor's wafer AND
grid and gets SCORED. So an unreadable meta table no longer merely mislabels - it makes the
server mistake EVERY map for an unregistered one, including maps that declare their own
frame, and seat them on a borrowed frame. That is the silent-overlay failure: the screen is
perfect and every coordinate is wrong. Borrowing must therefore be reachable from (c) ONLY,
and `test_a_broken_meta_table_never_reaches_the_borrow` is the load-bearing test in this
file - the rest check labelling.

THE OTHER INVARIANTS
- The honest case is unchanged: a map that really has no row still reaches the borrow.
- One fault, one word, across view / worklist / reference refusal.
- The healthy path pays nothing: the probe only runs when some meta came back None.
"""
import json

import pytest
from sqlalchemy import text

import map_alignment as ma
import map_overlay
from database import crud, models

# Prefixed so they cannot collide with a table in the operator's gitignored
# `table_config.json` - a collision wins the shared in-memory schema and surfaces later as
# `no such column` (server-pm memory: the `bonding_log` trap).
SRC = "metaacc_test_log"
MAPT = "metaacc_test_map"

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}
THRESHOLDS = {"min_margin_dies": 1, "min_discriminating_dies": 1}

RULE = {"name": "metaacc_test_rule", "source_table": SRC,
        "derived_table": "metaacc_test_unit", "decision_key": ["job_id"],
        "target_fields": ["map_metadata"]}

TABLES = {
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "job_id": "string", "job": "string",
                           "x": "number", "y": "number", "val": "string"},
          "map_key_columns": ["job"]},
    "metaacc_test_unit": {"business_key": "unit_key",
                          "composite_key_source": ["job_id"],
                          "column_types": {"unit_key": "string", "job_id": "string",
                                           "map_metadata": "string"}},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "job": "string",
                            "x": "number", "y": "number", "val": "string"},
           "map_key_columns": ["job"]},
    # Product-owned tables, declarations copied VERBATIM from table_config.json: a fixture
    # that invents a different shape breaks the first run and passes every run after it.
    map_overlay.VALID_DIE_TABLE: {
        "business_key": "cell_key",
        "composite_key_source": ["product", "type", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {"cell_key": "string", "product": "string", "type": "string",
                         "x": "number", "y": "number", "val": "string"},
        "map_key_columns": ["product", "type"]},
    map_overlay.META_TABLE: {"business_key": "map_pk",
                             "composite_key_source": ["target_table", "map_id"],
                             "column_types": {"map_pk": "string",
                                              "target_table": "string",
                                              "map_id": "string",
                                              "grid_metadata": "string"}},
}

CFG = {"table_bindings": {
    SRC: {"columns": {"x": "x", "y": "y", "val": "val", "key_columns": ["job"]}},
}, "alignment": THRESHOLDS}

FLOOR_SPEC = "%s:P1_T1" % map_overlay.VALID_DIE_TABLE


def _meta(**kw):
    m = {"grid_cols": 13, "grid_rows": 13, "rotation": 0, "side": "front",
         "grid_y_invert": False, "grid_start_x": 1, "grid_start_y": 1}
    m.update(PHYS)
    m.update(kw)
    return m


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _seed(db, job_id="J1", jobs=("M1",), with_meta=True, floor=False):
    """A unit whose maps have BOTH halves seeded, so that when a test later removes the
    server's ability to READ the meta table, «the rows are sitting right there» is a fact of
    the fixture rather than an assumption - that is the exact production shape."""
    s = models.DYNAMIC_TABLES[SRC]
    d = models.DYNAMIC_TABLES["metaacc_test_unit"]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    db.add(d(row_id="d_%s" % job_id, business_key_val=job_id,
             unit_key=job_id, job_id=job_id))
    cells = [(x, y) for x in range(2, 11) for y in range(2, 11)]
    for j in jobs:
        for i, (x, y) in enumerate(cells):
            db.add(s(row_id="s_%s_%s_%d" % (job_id, j, i),
                     business_key_val="%s_%s_%d" % (job_id, j, i),
                     cell_key="%s_%s_%d" % (job_id, j, i),
                     job_id=job_id, job=j, x=x, y=y, val="1"))
        if with_meta:
            db.add(meta_model(row_id="m_%s_%s" % (MAPT, j),
                              business_key_val="%s_%s" % (MAPT, j),
                              target_table=MAPT, map_id=j,
                              grid_metadata=json.dumps(_meta())))
    if floor:
        v = models.DYNAMIC_TABLES[map_overlay.VALID_DIE_TABLE]
        for i, (x, y) in enumerate(cells):
            db.add(v(row_id="v%d" % i, business_key_val="v%d" % i, cell_key="v%d" % i,
                     product="P1", type="T1", x=x, y=y, val="1"))
        db.add(meta_model(row_id="mv", business_key_val="floor",
                          target_table=map_overlay.VALID_DIE_TABLE, map_id="P1_T1",
                          grid_metadata=json.dumps(_meta())))
    db.commit()
    return cells


def _view(db, **kw):
    kw.setdefault("include_cells", False)
    return ma.build_alignment_view(db, CFG, RULE, {"job_id": "J1"}, MAPT,
                                   x_col="x", y_col="y", **kw)


def _codes(view):
    return {e["reason_code"] for e in view["excluded"]}


def _break_the_model(monkeypatch):
    """(a) the meta model is not loaded. `monkeypatch.delitem` restores it - a bare `del`
    would leak into every later test in the session (DYNAMIC_TABLES is module state)."""
    monkeypatch.delitem(models.DYNAMIC_TABLES, map_overlay.META_TABLE)


def _break_the_query(db):
    """(b) the SELECT fails. Dropping the physical table is the cheapest faithful stand-in
    for schema drift: the model still maps the columns, the live table does not have them.
    The next test's `create_all` puts it back (conftest drops/creates per test)."""
    db.commit()
    db.execute(text("DROP TABLE %s" % map_overlay.META_TABLE))
    db.commit()


# ---------------------------------------------------------------------------
# 1. the layer that answers the question, on its own
# ---------------------------------------------------------------------------

def test_the_three_causes_have_three_answers_at_the_one_place_that_judges(env, monkeypatch):
    """`meta_access_state` is THE spelling of «can the server read its own meta table».
    If this ever collapses two of the three, every consumer below collapses with it."""
    _seed(env)
    assert map_overlay.meta_access_state(env)[0] == map_overlay.META_ACCESS_OK

    _break_the_model(monkeypatch)
    assert map_overlay.meta_access_state(env)[0] == map_overlay.META_ACCESS_UNDECLARED
    monkeypatch.undo()

    _break_the_query(env)
    state, detail = map_overlay.meta_access_state(env)
    assert state == map_overlay.META_ACCESS_QUERY_FAILED
    # The detail must name what broke, or the operator goes back to the log to find out
    # WHICH table or column the server could not read.
    assert detail and map_overlay.META_TABLE in detail


def test_the_probe_queries_the_same_columns_the_real_read_queries(env):
    """A probe that selects a DIFFERENT column set can answer «readable» while the real read
    blows up - precisely the state this vocabulary exists to catch. So the probe must fail
    when the column the real read needs is gone."""
    _seed(env)
    env.commit()
    env.execute(text("ALTER TABLE %s RENAME COLUMN grid_metadata TO grid_metadata_x"
                     % map_overlay.META_TABLE))
    env.commit()
    assert map_overlay.meta_access_state(env)[0] == map_overlay.META_ACCESS_QUERY_FAILED


# ---------------------------------------------------------------------------
# 2. THE SAFETY PROPERTY - borrowing is reachable from genuine absence ONLY
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("how", ["model", "query"])
def test_a_broken_meta_table_never_reaches_the_borrow(env, monkeypatch, how):
    """🔴 THE load-bearing test. Every map here HAS a spec row (the fixture seeded them) and
    a declared floor is available. If the unreadable table were mistaken for «no spec row»,
    the maps would be seated on the FLOOR's frame and scored - a confident answer computed
    from somebody else's geometry, invisible in a cell count.

    So: nothing may be borrowed, nothing may be scored, and the refusal must name the fault
    rather than the data."""
    _seed(env, floor=True)
    if how == "model":
        _break_the_model(monkeypatch)
    else:
        _break_the_query(env)

    view = _view(env, reference_spec=FLOOR_SPEC, assume_reference_geometry=True)

    assert view["ruling"].get("geometry_assumed") in (False, None)
    assert view["stats"].get("assumed_map_ids", []) == []
    assert view["stats"].get("usable_map_ids", []) == []
    assert view["sources"]["usable_map_count"] == 0
    assert _codes(view) <= {ma.EXCLUDE_META_TABLE_UNDECLARED, ma.EXCLUDE_META_QUERY_FAILED}
    assert _codes(view)
    # and it is NOT told as a story about the floor either - the floor is fine
    assert view["basis_refusal"] is None


def test_the_borrow_gate_holds_when_only_the_source_lookups_failed(env, monkeypatch):
    """🔴 The case the end-to-end fixture above CANNOT reach, and a mutation proved it: when
    the whole table is unreadable the FLOOR fails to resolve too, so `score_candidates` never
    runs and its gate is never exercised. Deleting that gate left the suite green.

    A PARTIAL failure does reach it - a lock timeout, a transient error, one query in a batch
    failing after the floor was already read. Then the floor resolves, scoring proceeds, and
    the gate is the only thing standing between «could not read» and «unregistered, borrow
    the floor's frame». Fixture: the floor reads fine, the source lookups come back empty,
    and the access probe reports the fault - exactly that world."""
    _seed(env, floor=True)
    real = map_overlay.load_map_meta

    def _floor_only(db, target_table, map_id):
        if target_table == MAPT:
            return None                      # the source lookups came back empty
        return real(db, target_table, map_id)

    monkeypatch.setattr(map_overlay, "load_map_meta", _floor_only)
    monkeypatch.setattr(map_overlay, "meta_access_state",
                        lambda db: (map_overlay.META_ACCESS_QUERY_FAILED, "OperationalError: x"))

    view = _view(env, reference_spec=FLOOR_SPEC, assume_reference_geometry=True)

    assert view["reference"]["state"] == ma.REFERENCE_RESOLVED, "the floor must resolve here"
    assert view["stats"]["assumed_map_ids"] == []         # nothing borrowed
    assert view["stats"]["usable_map_ids"] == []          # nothing scored
    assert _codes(view) == {ma.EXCLUDE_META_QUERY_FAILED}
    assert view["meta_access"]["reason_code"] == ma.EXCLUDE_META_QUERY_FAILED


def test_a_map_that_really_has_no_row_still_reaches_the_borrow(env):
    """The control. The whole point of splitting the three is that (c) keeps its behaviour -
    a fix that closed the borrow for genuine absence would undo [D4]/[D5]."""
    _seed(env, with_meta=False, floor=True)
    view = _view(env, reference_spec=FLOOR_SPEC, assume_reference_geometry=True)

    assert view["meta_access"] is None
    assert view["stats"]["assumed_map_ids"] == ["M1"]
    assert view["sources"]["usable_map_count"] == 1
    assert ma.EXCLUDE_META_MISSING not in _codes(view)


# ---------------------------------------------------------------------------
# 3. the request-level statement
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("how", ["model", "query"])
def test_a_global_fault_is_stated_once_at_the_request_level(env, monkeypatch, how):
    """Two maps, one truth. Without a request-level statement the operator reads N data
    stories when the fact is «the server cannot read its own table» - and N per-map lines
    look like evidence ABOUT the data, which is the opposite of what happened."""
    _seed(env, jobs=("M1", "M2"), floor=True)
    if how == "model":
        _break_the_model(monkeypatch)
    else:
        _break_the_query(env)

    view = _view(env, reference_spec=FLOOR_SPEC)
    block = view["meta_access"]
    assert block is not None
    assert block["reason_code"] in (ma.EXCLUDE_META_TABLE_UNDECLARED,
                                   ma.EXCLUDE_META_QUERY_FAILED)
    # A whole sentence, composed by the SERVER. The screen assembles nothing.
    assert block["text"] and len(block["text"]) > 30
    assert map_overlay.META_TABLE in block["text"]
    assert view["sources"]["map_count"] == 2        # stated once for two maps


def test_the_healthy_path_does_not_pay_for_the_diagnosis(env, monkeypatch):
    """The probe is a refusal-path question (the `_meta_row_exists` discipline). If it ever
    moved onto the normal path it would add a query to every request that is working
    perfectly - so make calling it at all a failure here."""
    _seed(env, floor=True)

    def _boom(*a, **kw):
        raise AssertionError("meta_access_state must not run when every meta was read")

    monkeypatch.setattr(map_overlay, "meta_access_state", _boom)
    view = _view(env, reference_spec=FLOOR_SPEC)
    assert view["meta_access"] is None


# ---------------------------------------------------------------------------
# 4. one fault, one word - across view / worklist / reference
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("how", ["model", "query"])
def test_the_worklist_and_the_view_use_the_same_word_for_the_same_fault(env, monkeypatch, how):
    """A list that says «미등록» and a detail screen that says «테이블 미선언» report one
    cause under two names, and the operator cannot tell they are the same incident."""
    _seed(env, floor=True)
    if how == "model":
        _break_the_model(monkeypatch)
    else:
        _break_the_query(env)

    view = _view(env, reference_spec=FLOOR_SPEC)
    wl = ma.build_alignment_worklist(env, CFG, RULE, MAPT)
    wl_codes = {r["reason_code"] for r in wl["unscorable_reasons"]}
    assert _codes(view) & wl_codes == _codes(view)
    assert wl["meta_access"] is not None
    assert wl["meta_access"]["reason_code"] == view["meta_access"]["reason_code"]


@pytest.mark.parametrize("how", ["model", "query"])
def test_the_worklist_does_not_invite_the_operator_into_an_unreadable_table(env, monkeypatch, how):
    """`assumable_map_count` counts maps with no spec row since [D5]. When the table cannot
    be READ every map looks like that - so the count would become an invitation built from a
    measurement that never happened."""
    _seed(env, floor=True)
    if how == "model":
        _break_the_model(monkeypatch)
    else:
        _break_the_query(env)
    wl = ma.build_alignment_worklist(env, CFG, RULE, MAPT)
    assert all(u["assumable_map_count"] == 0 for u in wl["units"])


@pytest.mark.parametrize("how", ["model", "query"])
def test_a_reference_is_refused_by_the_fault_rather_than_by_absence(env, monkeypatch, how):
    """An explicitly named floor takes a different route to the same `None`
    (`_load_reference`), and its old fallback `_meta_row_exists` folds model-missing and
    query-failed into False - so that route said «등록되지 않았습니다» too. Since [D5] that
    misdiagnosis is worse: an unresolved floor turns the source maps into `basis_undeclared`,
    i.e. «declare the floor's spec» about a floor that IS declared."""
    _seed(env, floor=True)
    if how == "model":
        _break_the_model(monkeypatch)
    else:
        _break_the_query(env)

    view = _view(env, reference_spec=FLOOR_SPEC)
    ref = view["reference"]
    assert ref["state"] == ma.REFERENCE_REFUSED
    assert ref["reason_code"] in (ma.REF_REFUSAL_META_TABLE_UNDECLARED,
                                  ma.REF_REFUSAL_META_QUERY_FAILED)
    assert ref["reason_code"] != ma.REF_REFUSAL_META_MISSING
    assert view["basis_refusal"] is None


def test_every_meta_fault_code_carries_a_sentence_and_exactly_one_spelling():
    """The two disciplines this vocabulary already keeps, extended to the new codes: a label
    for every code, and ONE string per fact shared by the exclusion vocabulary, the
    reference-refusal vocabulary and the worklist vocabulary."""
    new = (ma.EXCLUDE_META_TABLE_UNDECLARED, ma.EXCLUDE_META_QUERY_FAILED)
    for code in new:
        assert ma._EXCLUDE_TEXT.get(code)
        assert ma._WORKLIST_REASON_TEXT.get(code) == ma._EXCLUDE_TEXT[code]
        assert ma._META_ACCESS_TEXT.get(code)
    assert ma.REF_REFUSAL_META_TABLE_UNDECLARED is ma.EXCLUDE_META_TABLE_UNDECLARED
    assert ma.REF_REFUSAL_META_QUERY_FAILED is ma.EXCLUDE_META_QUERY_FAILED
    assert len({ma.EXCLUDE_META_MISSING, *new}) == 3


def test_every_meta_access_token_maps_to_an_exclusion_code():
    """The token vocabulary lives in `map_overlay`; the sentences live here. A token added
    there without a word here would silently degrade to «미등록» - and since [D5] a silent
    degrade to «미등록» means the map gets BORROWED, not just mislabelled."""
    tokens = {v for k, v in vars(map_overlay).items()
              if k.startswith("META_ACCESS_") and isinstance(v, str)}
    unmapped = tokens - set(ma._META_ACCESS_CODE) - {map_overlay.META_ACCESS_OK}
    assert not unmapped, "unmapped meta-access tokens: %s" % sorted(unmapped)


# ---------------------------------------------------------------------------
# 5. the other half of the lookup key
# ---------------------------------------------------------------------------

def test_a_target_table_mismatch_is_genuine_absence_not_a_server_fault(env):
    """`load_map_meta` filters on target_table AND map_id. A row registered under a different
    `target_table` produces the same symptom with rows sitting right there - but the server
    CAN read its table, so the honest answer is genuine absence and the map goes to the
    borrow. Pinned so a future change does not relabel this as a server fault and thereby
    close the borrow for it."""
    _seed(env, with_meta=False, floor=True)
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    env.add(meta_model(row_id="m_other", business_key_val="other_M1",
                       target_table=MAPT + "_other", map_id="M1",
                       grid_metadata=json.dumps(_meta())))
    env.commit()

    view = _view(env, reference_spec=FLOOR_SPEC, assume_reference_geometry=True)
    assert view["meta_access"] is None
    assert view["stats"]["assumed_map_ids"] == ["M1"]
    assert map_overlay.load_map_meta(env, MAPT + "_other", "M1") is not None


# ---------------------------------------------------------------------------
# 6. THE PROBE MUST BE ABLE TO SEND ITS OWN VALUE
#    [2026-08-05] The probe shipped with a sentinel that begins with a NUL byte.
#    PostgreSQL `text` cannot hold a NUL, and psycopg2 refuses such a value
#    CLIENT-SIDE, during parameter adaptation - the statement is never sent. So
#    `meta_access_state` failed on its own sentinel and reported QUERY_FAILED
#    about a perfectly healthy table, on every request that reached the probe;
#    every source map was excluded with «wafer_map_metadata 조회 실패». The log
#    was silent because the warning lives in `load_map_meta`, which the probe
#    does not go through.
#
#    The suite was green at 2,684 because SQLite stores NUL inside a string
#    happily. That is the same SQLite-cannot-see-it gap that `pg_abort_semantics`
#    (test_enrichment_candidates.py) was built for, so this section restores the
#    missing rule the same way: inject it, keep everything else real.
# ---------------------------------------------------------------------------

class _NulRefused(ValueError):
    """Stand-in for psycopg2's refusal. It raises a bare `ValueError` with this exact
    message, and it raises it BEFORE the statement reaches the server - which is why
    catching a database error is not what distinguishes this case."""


@pytest.fixture()
def pg_text_semantics(env):
    """Impose PostgreSQL's «text cannot contain NUL» rule on the SQLite test engine.

    WHY A FAULT INJECTION RATHER THAN A POSTGRES-BACKED TEST
        Identical reasoning to `pg_abort_semantics`: conftest pins the suite to
        `sqlite:///:memory:` with a hard assignment so an ambient DATABASE_URL cannot
        aim it at production, so a Postgres-backed test would SKIP by default and a
        skipped test certifies nothing. What has to be restored is not Postgres, it is
        one documented RULE that pysqlite does not have:

            a `text` value cannot contain U+0000, and the driver rejects it locally,
            before the statement is sent.

        Everything else stays real: the real model, the real `_meta_select`, the real
        session. Only the NUL rule is injected.

    `before_cursor_execute` is the faithful hook - psycopg2 raises inside
    `cursor.execute` while adapting parameters, i.e. exactly here.
    """
    from sqlalchemy import event

    bind = env.get_bind()
    state = {"refused": 0}

    def _values(params):
        if isinstance(params, dict):
            return list(params.values())
        if isinstance(params, (list, tuple)):
            return list(params)
        return [params]

    def _before(conn, cursor, statement, parameters, context, executemany):
        rows = parameters if executemany else [parameters]
        for p in rows or []:
            for v in _values(p):
                if isinstance(v, str) and "\x00" in v:
                    state["refused"] += 1
                    raise _NulRefused(
                        "A string literal cannot contain NUL (0x00) characters.")

    event.listen(bind, "before_cursor_execute", _before)
    try:
        yield state
    finally:
        event.remove(bind, "before_cursor_execute", _before)
        env.rollback()


def test_the_nul_injection_actually_bites(env, pg_text_semantics):
    """Guard on the guard. If the injector silently did nothing, every test below would
    pass on the defect - which is precisely how this shipped."""
    _seed(env)
    with pytest.raises(Exception) as ei:
        env.execute(text("SELECT :v"), {"v": "\x00nope"}).first()
    assert "NUL" in str(ei.value)
    assert pg_text_semantics["refused"] == 1
    env.rollback()
    # ... and it does NOT fire on ordinary values, or it would prove nothing below.
    assert env.execute(text("SELECT :v"), {"v": "plain"}).scalar() == "plain"
    assert pg_text_semantics["refused"] == 1


def test_the_probe_can_send_its_own_sentinel(env, pg_text_semantics):
    """🔴 THE regression assertion. A healthy, fully seeded meta table, under a driver that
    refuses NUL: the probe must answer OK.

    Restore `_META_PROBE_KEY = "\\x00__meta_access_probe__"` and this dies - the probe blows
    up on its own value and accuses the table. That is the whole defect, and it is
    observable under SQLite because the RULE has been restored, not the database."""
    _seed(env)
    state, detail = map_overlay.meta_access_state(env)
    assert state == map_overlay.META_ACCESS_OK, (
        "the probe failed on its own sentinel, not on the table: %s" % (detail,))
    assert pg_text_semantics["refused"] == 0, (
        "the probe handed the driver a value it refuses to send")


def test_the_sentinel_is_carriable_by_construction(env):
    """The rule that makes the assertion above hold for every driver, not just the one
    fault we injected: the probe binds values from the SAME character repertoire the real
    read carries. Then any driver that can carry a real lookup can carry the probe, so
    «the probe failed» implies «the real read fails too» - which is the entire claim
    `meta_access_state` makes. A sentinel needing a WIDER repertoire (a NUL, a control
    byte) can fail where the real read would have succeeded."""
    assert map_overlay._probe_key_fault() is None
    assert map_overlay._probe_key_fault("\x00__meta_access_probe__") is not None
    # and it still cannot name a real row: `target_table` is written from a declared table
    # name, and this is not a legal one.
    assert map_overlay._META_PROBE_KEY not in models.DYNAMIC_TABLES
    assert map_overlay._META_PROBE_KEY not in crud.TABLE_CONFIG


def test_a_broken_probe_is_not_reported_as_a_broken_table(env, monkeypatch):
    """«the driver rejected my own value» and «the table is unreadable» are different facts
    with different repairs, and a value rejected locally never reached the database at all -
    so answering QUERY_FAILED about it is an accusation the server has no evidence for.

    It must also never degrade to «genuine absence»: `meta_absence_reason` maps unknown
    tokens to EXCLUDE_META_MISSING, which is the token that ALLOWS the borrow."""
    _seed(env)
    monkeypatch.setattr(map_overlay, "_META_PROBE_KEY", "\x00__meta_access_probe__")
    state, detail = map_overlay.meta_access_state(env)
    assert state == map_overlay.META_ACCESS_PROBE_BROKEN
    assert state != map_overlay.META_ACCESS_QUERY_FAILED
    assert detail and "U+0000" in detail
    code, _ = ma.meta_absence_reason(env)
    assert code == ma.EXCLUDE_META_PROBE_BROKEN
    assert code != ma.EXCLUDE_META_MISSING, "a broken probe must not open the borrow"


def test_the_operators_maps_come_back_when_the_driver_refuses_NUL(env, pg_text_semantics):
    """🔴 THE production reproduction - the reported symptom, not a scenario of mine.

    The report: every source map excluded with «wafer_map_metadata 조회 실패» while the
    table is healthy and the legacy editor reads it fine. This is that request: a healthy
    meta table, a map with genuinely no spec row (the [D5] normal case, which is what makes
    the probe run at all), a declared floor - under a driver that refuses NUL.

    Before the fix: `meta_access` is a query-failed block and `assumed_map_ids` is empty.
    After: the map borrows the floor and is scored, exactly as it does on SQLite today."""
    _seed(env, with_meta=False, floor=True)
    view = _view(env, reference_spec=FLOOR_SPEC, assume_reference_geometry=True)

    assert view["meta_access"] is None, (
        "a healthy table was reported as unreadable: %s" % (view["meta_access"],))
    assert _codes(view) == set() or ma.EXCLUDE_META_QUERY_FAILED not in _codes(view)
    assert view["stats"]["assumed_map_ids"] == ["M1"]
    assert view["sources"]["usable_map_count"] == 1


def test_the_injection_does_not_blind_the_probe_to_a_genuinely_broken_table(env,
                                                                           pg_text_semantics):
    """The negative control. A fix that made the probe answer OK unconditionally would pass
    every test above - and would re-open the borrow onto a table the server cannot read,
    which is the expensive failure this vocabulary exists to prevent."""
    _seed(env, floor=True)
    _break_the_query(env)
    state, detail = map_overlay.meta_access_state(env)
    assert state == map_overlay.META_ACCESS_QUERY_FAILED
    assert detail and map_overlay.META_TABLE in detail

    view = _view(env, reference_spec=FLOOR_SPEC, assume_reference_geometry=True)
    assert view["stats"].get("assumed_map_ids", []) == []
    assert _codes(view) == {ma.EXCLUDE_META_QUERY_FAILED}
