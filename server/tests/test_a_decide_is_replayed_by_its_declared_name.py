# -*- coding: utf-8 -*-
"""A decide declaration is replayed by the name the operator wrote (lead 10-24 defect 1): the loader stands it as
`enrichment_dedup:<name>` and `enrichment_auto_confirm:<name>`, and the declared name was refused «not found» while
the list named only the two stood ones.

  the declared name        -> the dedup half (the confirm half by its own name - a replay wakes no rule)
  a stood name             -> that rule, as before
  an off declaration       -> found by its declared name too (naming it is the one way it runs, owner 10-23)
  an unknown name          -> refused; the list says the declared name beside the stood ones
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import replay, rule_shape                                  # noqa: E402
from database import crud                                             # noqa: E402

DIE, PAIR, NAME = "rn_die", "rn_pair", "rn_pairs"
TABLES = {
    DIE: {"business_key": "die_key", "composite_key_source": ["die_key"],
          "column_types": {"die_key": "string", "bonded_wafer": "string", "core_wafer": "string"}},
    PAIR: {"business_key": None, "composite_key_source": ["bonded_wafer", "core_wafer"],
           "column_types": {"bonded_wafer": "string", "core_wafer": "string", "die_count": "number"}},
}
KEY = ["bonded_wafer", "core_wafer"]


@pytest.fixture(name="stood")
def fixture_stood(monkeypatch):
    for name, table in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, table)

    def stand(**cells):
        rules, refusal = rule_shape.expand_declaration(dict(
            {"name": NAME, "on": {"table": DIE, "require": KEY}, "into": {"table": PAIR},
             "derive": {"kind": "decide", "decide": {"key": KEY, "aggregations": {"die_count": "count"}}}},
            **cells), crud.TABLE_CONFIG)[:2]
        assert refusal is None, refusal
        return rules
    return stand


def test_the_declared_name_replays_the_dedup_half(stood):
    rules = stood()
    assert [r["name"] for r in rules] == ["enrichment_dedup:" + NAME, "enrichment_auto_confirm:" + NAME], \
        "CANARY: the loader stands two rules under other names"
    assert replay.find_rule(NAME, rules)["name"] == "enrichment_dedup:" + NAME
    assert replay.find_rule("enrichment_auto_confirm:" + NAME, rules)["name"] == "enrichment_auto_confirm:" + NAME


def test_an_off_declaration_is_found_by_its_declared_name(stood, monkeypatch):
    off = stood(enabled=False)
    assert all(rule_shape.is_switched_off(r) for r in off), "CANARY: both halves off"
    monkeypatch.setattr("chain.ingestion_worker.loaded_chain_rules", lambda: off)
    monkeypatch.setattr(replay, "load_rules", lambda: [])
    assert replay.find_rule(NAME)["name"] == "enrichment_dedup:" + NAME


def test_an_unknown_name_is_refused_with_the_declared_name_in_the_list(stood):
    with pytest.raises(replay.ReplayRefused) as raised:
        replay.find_rule("rn_no_such_rule", stood())
    assert str(raised.value) == (
        "chain rule 'rn_no_such_rule' not found or disabled; available: enrichment_auto_confirm:%s, "
        "enrichment_dedup:%s, %s" % (NAME, NAME, NAME))
