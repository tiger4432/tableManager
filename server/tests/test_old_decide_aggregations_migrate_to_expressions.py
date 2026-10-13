"""Lead 5667ea0fe ③: the migration writes each old decide aggregation as the expression the reader already runs it as
(`aggregation_record` - one fold for both), names what stays a record and why, runs twice to the same file, and its
compare finds the old record and its expression giving the same cell."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud, models                                     # noqa: E402
from scripts import migrate_decide_aggregations as migrate             # noqa: E402

SRC = "x5667m_src"
TABLES = {SRC: {"business_key": "rid", "column_types": {"rid": "string", "lot": "string", "n": "number",
                                                         "t": "datetime", "s": "string"}}}
AGGREGATIONS = {
    "c": "count",
    "n_min": {"fn": "min", "column": "n"},
    "t_max": {"fn": "max", "column": "t"},
    "s_all": {"fn": "unique_concat", "column": "s"},
    "s_min": {"fn": "min", "column": "s"},
    "s_slash": {"fn": "unique_concat", "column": "s", "separator": "/"},
    "avg": "Avg([n])",
}
DOCUMENT = {"rules": [
    {"name": "d", "on": {"table": SRC}, "into": {"table": "drv"},
     "derive": {"kind": "decide", "decide": {"key": ["lot"], "aggregations": AGGREGATIONS}}},
    {"name": "j", "on": {"table": SRC}, "derive": {"kind": "join"}},
]}


def test_each_old_record_becomes_its_expression_or_says_why_it_stays():
    written, found = migrate.plan(DOCUMENT, TABLES)
    said = {f["name"]: f.get("becomes") or f.get("stays") or "as written" for f in found}
    assert said == {"c": "Count()", "n_min": "Min([n])", "t_max": "Max([t])", "s_all": "UniqueConcatenate([s])",
                    "s_min": "min over a text column", "s_slash": "unique_concat with the separator '/'",
                    "avg": "as written"}, said
    assert written["rules"][0]["derive"]["decide"]["aggregations"] == dict(
        AGGREGATIONS, c="Count()", n_min="Min([n])", t_max="Max([t])", s_all="UniqueConcatenate([s])")
    assert DOCUMENT["rules"][0]["derive"]["decide"]["aggregations"] == AGGREGATIONS, "the input is not touched"
    assert migrate.say(found)[-1] == "7 aggregation(s): 4 become expressions, 2 stay records, 1 as written"
    again_written, again = migrate.plan(written, TABLES)
    assert again_written == written and not [f for f in again if "becomes" in f], "a second run moves nothing"


def test_the_compare_finds_the_old_cell_and_the_new_the_same(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    model = models.DYNAMIC_TABLES[SRC]
    model.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    utc = dt.timezone.utc
    for i, (lot, n, t, s) in enumerate([("A", 3.0, dt.datetime(2026, 10, 2, tzinfo=utc), "W2"),
                                        ("A", -1.5, dt.datetime(2026, 10, 3, tzinfo=utc), "W1"),
                                        ("B", None, None, ""), ("", 2.0, None, "Z")]):
        db_session.add(model(row_id="r%d" % i, business_key_val="r%d" % i, rid="r%d" % i, lot=lot, n=n, t=t, s=s))
    db_session.flush()
    _written, found = migrate.plan(DOCUMENT, TABLES)
    outs = {f["name"]: migrate.compare(db_session, f) for f in found if "becomes" in f}
    assert {name: (out["same"], out["keys"], out["different"]) for name, out in outs.items()} == {
        name: (2, 2, []) for name in ("c", "n_min", "t_max", "s_all")}, outs
