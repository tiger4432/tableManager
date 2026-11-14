"""unique_concat answers one blank rule and one separator on both of its paths (lead 11-14, CLAUDE.md «길이 0 인 문자열은
NULL 이다 - 한 함수가 접는다»): a join's take (`join_into._gathered`, the real chain drain) and a decide aggregation
(`mapper._aggregate_affected_keys`) over the same rows written through the product's write. The fold is the write:
`crud.normalize_stored_text` stores every blank as NULL, so the SQL side (`blank_sql_condition`, NULL-or-'') and the
Python side (`crud.is_blank_value`) read one stored answer. The separator is `expression.JOINER`: the join take's
`UniqueConcatenate` joins with it and the decide aggregation's default (`AGGREGATION_SEPARATOR_DEFAULTS`) is it - it
was written twice (lead 11-14)."""
import math

from tests.test_a_join_take_can_gather_every_row_of_a_key import (  # noqa: F401 - the `db` fixture
    _drain, _put, _rules, fixture_db)
from database import crud, models

#: name -> the values one key's source rows hold
VALUES = {"none": [None], "empty": [""], "space": [" "], "tab": ["\t"], "nan": [math.nan],
          "a": ["A"], "spaced_a": [" A "], "a_and_blank": ["A", " "], "a_and_b": ["B", " A "]}
EXPECTED = {"none": None, "empty": None, "space": None, "tab": None, "nan": None,
            "a": "A", "spaced_a": "A", "a_and_blank": "A", "a_and_b": "A, B"}


def test_both_paths_give_each_key_the_same_cell(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch, [{"from": "v", "into": "vs", "fn": "unique_concat"}])
    _put(db, "ja_tgt", [{"k": "K_" + name} for name in VALUES])
    _drain(db, rules)
    _put(db, "ja_src", [{"rid": "r_%s_%d" % (name, i), "k": "K_" + name, "v": value}
                        for name, values in VALUES.items() for i, value in enumerate(values)])
    _drain(db, rules)
    db.expire_all()

    joined = {r.k[2:]: r.vs for r in db.query(models.DYNAMIC_TABLES["ja_tgt"])}
    from chain.enrichment import mapper
    keys = {("K_" + name,): ("K_" + name,) for name in VALUES}
    decided = {k[0][2:]: (one or {}).get("x") for k, one in mapper._aggregate_affected_keys(
        db, "ja_src", ["k"], keys, {"x": {"fn": "unique_concat", "column": "v"}}).items()}

    assert len(joined) == len(VALUES), "CANARY: every key's target row was written"
    decided = {name: decided.get(name) for name in VALUES}
    assert {"join take": joined, "decide aggregation": decided} == {
        "join take": EXPECTED, "decide aggregation": EXPECTED}
    assert {name for name, values in VALUES.items() if all(crud.is_blank_value(v) for v in values)} == \
        {name for name, cell in EXPECTED.items() if cell is None}, "the Python judgement on the raw values"
