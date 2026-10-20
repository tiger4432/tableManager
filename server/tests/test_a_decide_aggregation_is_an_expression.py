"""Lead 5667ea0fe: a decide aggregation is an expression (the server calculator, `expression`) - answered in SQL where
it folds there (`mapper._plan`: Count(), Sum · Min · Max of a number column), else over the key's source rows.

  ① a pushed expression answers what the calculator answers over the same rows - a NULL/'' blank key's two SQL groups
    included; on SQLite and PostgreSQL
  ② an old record and the expression it becomes give the same cell; one no expression answers the same keeps its record
  ③ the reader refuses an expression that is a value per row, reads a column the source lacks, or asks Latest of a
    table the ledger gives no one time
  ④ Latest orders a key's rows by their ledger time (총괄 112293f73, 소유자 «원자시각») - the calculator's Latest over the
    same rows with that time as $at; a row the source's exclude_when takes out has none
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest                                                         # noqa: E402

import expression                                                     # noqa: E402
from chain import enrichment                                          # noqa: E402
from chain.enrichment import mapper                                   # noqa: E402
from database import crud, models                                     # noqa: E402

SRC = "x5667_src"
TABLES = {
    SRC: {"business_key": "rid", "column_types": {"rid": "string", "lot": "string", "n": "number", "t": "datetime",
                                                   "s": "string"}},
    "x5667_drv": {"business_key": "lot", "composite_key_source": ["lot"],
                  "column_types": {"lot": "string", "agg": "string", "wafer": "string"}},
}
UTC = dt.timezone.utc
ROWS = [  # lot, n, t, s
    ("A", 3.5, dt.datetime(2026, 10, 3, tzinfo=UTC), "W2"),
    ("A", None, dt.datetime(2026, 10, 1, tzinfo=UTC), "W1"),
    ("A", -2.0, None, "w1"),
    ("A", 7.0, dt.datetime(2026, 10, 2, tzinfo=UTC), ""),
    ("B", None, None, None),
    (None, 1.0, dt.datetime(2026, 10, 5, tzinfo=UTC), "Z"),                  # the blank key, stored NULL
    ("", 4.0, dt.datetime(2026, 10, 4, tzinfo=UTC), "Y"),                    # ... and stored ''
]
KEYS = {("A",): ("A",), ("B",): ("B",), ("",): (None,)}
PUSHED = ["Count()", "Sum([n])", "Min([n])", "Max([n])"]
BY_ROWS = ["Avg([n])", "Count([n])", "Median([n])", "UniqueConcatenate([s])", "Min([t])", "Max([t])",
           "Sum([n]) / Count()", "UniqueCount([s])"]


def _board(db):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    model = models.DYNAMIC_TABLES[SRC]
    model.__table__.create(bind=db.get_bind(), checkfirst=True)
    for i, (lot, n, t, s) in enumerate(ROWS):
        db.add(model(row_id="r%d" % i, business_key_val="r%d" % i, rid="r%d" % i, lot=lot, n=n, t=t, s=s))
    db.flush()
    return model


def _rows_of(db, model, key):
    lot = model.lot
    cond = (lot.is_(None) | (lot == "")) if key == ("",) else lot == key[0]
    return [{"n": r.n, "t": r.t, "s": r.s} for r in db.query(model).filter(cond).order_by(model.rid)]


def _answers(db, aggregations):
    return mapper._aggregate_affected_keys(db, SRC, ["lot"], KEYS, aggregations)


@pytest.fixture(params=["sqlite", pytest.param("pg", marks=pytest.mark.pg)])
def board(request, db_session):
    db = db_session if request.param == "sqlite" else request.getfixturevalue("pg_session")
    model = _board(db)
    yield db, model
    db.rollback()
    if request.param == "pg":
        model.__table__.drop(bind=db.get_bind(), checkfirst=True)


def test_a_pushed_expression_answers_what_the_calculator_answers(board):
    db, model = board
    types = TABLES[SRC]["column_types"]
    for text in PUSHED + BY_ROWS:
        way = mapper._plan("agg", {"expression": text}, model, SRC, types)
        assert ("sql" in way) == (text in PUSHED), (text, sorted(way))
    got = _answers(db, {text: {"expression": text} for text in PUSHED + BY_ROWS})
    for key in KEYS:
        rows = _rows_of(db, model, key)
        for text in PUSHED + BY_ROWS:
            want = expression.run(expression.compile(text), rows, types)["value"]
            have = got[key][text]
            if isinstance(want, dt.datetime):
                assert have == want, (key, text, have, want)
            else:
                assert (have is None) == (want is None) and (want is None or abs(have - want) <= 1e-9 * max(1, abs(want))
                                                              if isinstance(want, (int, float)) else have == want), \
                    (key, text, have, want)
    assert got[("A",)]["Count()"] == 4 and got[("",)]["Count()"] == 2 and got[("B",)]["Sum([n])"] is None, got


OLD = {  # an old record -> the expression the reader folds it to
    "count": ({"fn": "count"}, "Count()"),
    "n_min": ({"fn": "min", "column": "n"}, "Min([n])"),
    "n_max": ({"fn": "max", "column": "n"}, "Max([n])"),
    "t_min": ({"fn": "min", "column": "t"}, "Min([t])"),
    "t_max": ({"fn": "max", "column": "t"}, "Max([t])"),
    "s_concat": ({"fn": "unique_concat", "column": "s"}, "UniqueConcatenate([s])"),
}
KEPT = {
    "s_min": ({"fn": "min", "column": "s"}, "min over a text column"),
    "s_slash": ({"fn": "unique_concat", "column": "s", "separator": "/"}, "unique_concat with the separator '/'"),
}


def test_an_old_record_and_its_expression_give_the_same_cell(board):
    db, model = board
    types = TABLES[SRC]["column_types"]
    for name, (record, text) in OLD.items():
        assert enrichment.config.aggregation_record(record, types) == (text, None), name
    for name, (record, why) in KEPT.items():
        assert enrichment.config.aggregation_record(record, types) == (record, why), name
    old = _answers(db, {name: dict(record, separator=", ") if record["fn"] == "unique_concat" else record
                        for name, (record, _text) in OLD.items() if record["fn"] != "count"})
    new = _answers(db, {name: {"expression": text} for name, (_record, text) in OLD.items()})
    for key in KEYS:
        assert new[key]["count"] == len(_rows_of(db, model, key)), key
        for name in old[key]:
            assert old[key][name] == new[key][name], (key, name, old[key][name], new[key][name])
    assert new[("A",)]["s_concat"] == "W1, W2, w1" and new[("A",)]["n_min"] == -2.0, new


@pytest.mark.parametrize("text, said", [
    ("[n] * 2", "is a value per row"),
    ("Avg([nope])", "missing in source table"),
    ("Latest([n])", "Latest needs the ledger time of x5667_src"),
    ("Avg([n]", "closing Avg"),
    ("Marked(\"B\")", "is the screen's"),
])
def test_the_reader_refuses_by_name(text, said):
    raw = {"source_table": SRC, "derived_table": "x5667_drv", "decision_key": ["lot"], "target_fields": ["wafer"],
           "aggregations": {"agg": text}}
    rule, why = enrichment.config._validate_rule("r", raw, TABLES)
    assert rule is None and said in why, why


def _ledger(monkeypatch, *sources):
    """The operating world's compiled declaration, as `followup.time_of_table` reads it: (name, relation, time column,
    exclude_when[, basis, group_by]) per source."""
    from types import SimpleNamespace

    from ledger import worker
    from ledger.setup_registry import OccurredAtPlan

    plans = {name: SimpleNamespace(relation=relation, runs=True, driver=SimpleNamespace(
        occurred_at=OccurredAtPlan(column=column, timezone="UTC", basis=(rest[0] if rest else None)),
        exclude_when=excluded, group_by=(rest[1] if rest else ())))
        for name, relation, column, excluded, *rest in sources}
    monkeypatch.setattr(worker, "_compiled_setup", lambda world: SimpleNamespace(snapshot=SimpleNamespace(
        source_plans=plans)))


@pytest.mark.parametrize("excluded, want", [((), {("A",): "W2", ("",): "Z", ("B",): None}),
                                            (({"when": {"s": "W2"}},), {("A",): "W1", ("",): "Z", ("B",): None})],
                         ids=["every row", "exclude_when takes the newest out"])
def test_latest_is_the_calculators_latest_by_ledger_time(board, monkeypatch, excluded, want):
    from ledger.event_frame import row_excluded

    db, model = board
    _ledger(monkeypatch, ("src_a", SRC, "t", excluded))
    got = _answers(db, {"latest": {"expression": "Latest([s])"}})
    assert {key: got[key]["latest"] for key in KEYS} == want
    types = TABLES[SRC]["column_types"]
    for key in KEYS:
        rows = [dict(row, **{"$at": None if row["t"] is None or row_excluded(excluded, row.get)
                             else (row["t"] if row["t"].tzinfo else row["t"].replace(tzinfo=UTC)).isoformat()})
                for row in _rows_of(db, model, key)]
        assert got[key]["latest"] == expression.run(expression.compile("Latest([s])"), rows, types)["value"], key


@pytest.mark.parametrize("sources, said", [
    ((("src_x", "elsewhere", "t", ()),), "Latest needs the ledger time of x5667_src - no ledger source reads it"),
    ((("src_a", SRC, "t", ()), ("src_b", SRC, "n", ())),
     "Latest needs the ledger time of x5667_src - its sources read it at different times: src_a (t UTC), src_b (n UTC)"),
    ((("src_g", SRC, "created_at", (), "ingested", ("lot",)),),
     "Latest needs the ledger time of x5667_src - it needs one atom time per row; src_g groups rows by lot"),
], ids=["no source", "two times", "a group's time"])
def test_latest_without_one_ledger_time_is_refused_by_name(monkeypatch, sources, said):
    _ledger(monkeypatch, *sources)
    raw = {"source_table": SRC, "derived_table": "x5667_drv", "decision_key": ["lot"], "target_fields": ["wafer"],
           "aggregations": {"agg": "Latest([s])"}}
    rule, why = enrichment.config._validate_rule("r", raw, TABLES)
    assert rule is None and said in why, why
    _ledger(monkeypatch, ("src_a", SRC, "t", ()))
    assert enrichment.config._validate_rule("r", raw, TABLES)[0] is not None, "control: one time - it stands"


def test_the_ledger_time_of_a_table_is_its_sources_occurred_at(monkeypatch, tmp_path):
    """The reading seat on the shipped declaration, compiled for real."""
    from ledger import followup, worker
    from tests.support.declaration import use_committed_declaration

    use_committed_declaration(monkeypatch, tmp_path)
    from database import config_watcher
    config_watcher.forget_held()
    setup = worker._compiled_setup(None)
    tables = {plan.relation for plan in setup.snapshot.source_plans.values() if plan.runs}
    assert tables, "control: the shipped declaration has sources"
    for table in sorted(tables):
        time, why = followup.time_of_table(setup, table)
        columns = {setup.snapshot.source_plans[n].driver.occurred_at.column
                   for n in followup.sources_for_table(setup, table)}
        assert (time is not None) == (len(columns) == 1), (table, why)
        if time is not None:
            assert time["occurred_at"].column in columns


def test_a_row_with_no_atom_is_not_in_latests_set(board, monkeypatch):
    """총괄 review of e2c3a9a15 ①: without it the calculator's «no time at all - the one value» rule took a row the
    ledger never made an atom of (W9 · W8)."""
    db, model = board
    for rid, lot, t, s in (("c1", "C", None, "W9"), ("c2", "C", dt.datetime(2026, 10, 6, tzinfo=UTC), ""),
                           ("d1", "D", dt.datetime(2026, 10, 7, tzinfo=UTC), ""),
                           ("d2", "D", dt.datetime(2026, 10, 1, tzinfo=UTC), "W8")):
        db.add(model(row_id=rid, business_key_val=rid, rid=rid, lot=lot, t=t, s=s))
    db.flush()
    _ledger(monkeypatch, ("src_a", SRC, "t", ({"when": {"s": "W8"}},)))
    got = mapper._aggregate_affected_keys(db, SRC, ["lot"], {("C",): ("C",), ("D",): ("D",), ("A",): ("A",)},
                                          {"latest": {"expression": "Latest([s])"}, "n": {"expression": "Count([s])"}})
    assert {key: got[key]["latest"] for key in got} == {("C",): None, ("D",): None, ("A",): "W2"}
    assert got[("C",)]["n"] == 1 and got[("D",)]["n"] == 1, "control: the other aggregations still see every row"


def test_a_time_the_ledger_cannot_read_fails_by_its_cell(board, monkeypatch):
    db, _model = board
    _ledger(monkeypatch, ("src_a", SRC, "s", ()))
    with pytest.raises(ValueError, match=r"Latest: x5667_src\.s holds '.+', which the ledger cannot read as its time"):
        _answers(db, {"latest": {"expression": "Latest([n])"}})
