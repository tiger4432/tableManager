# -*- coding: utf-8 -*-
"""Lead 11-07 (owner «함수를 씌워서 인덱스를 못 탄다면 안 씌우면 안 됨?»): a virtual read asks a key column as it holds the
value (`sql_translate._held`) - a number or a time key only where the key speller spells it back to the frontier's own
text, as the join's spelled comparison did; a column with notation rules stays spelled (`Leg.key`).

  a number     "9" -> 9.0 kept · "9.0" / "x" dropped (no value of the column is spelled so)
  a time key   its ISO with the offset -> the instant kept · another spelling of the same instant dropped
  rules        the spelled expression, the text as it is
"""
import notation_norm
from ledger.sql_translate import Leg
from ledger_api.ledger_subgraph import VirtualEvidenceLookup


class _Leg:
    relation = "t"
    compared = Leg.compared                 # the one key comparison (lead D ccac72ede), on this leg's specs

    def __init__(self, **specs):
        self.specs = specs

    def columns_of(self, _arm):
        return sorted(self.specs.items())

    def key(self, spec):
        return f"SPELLED({spec['column']})"


def _asked(leg, texts):
    params = {}
    said = VirtualEvidenceLookup._in(leg, "outgoing", texts, params, "p")
    return said, params


def test_a_number_is_kept_only_in_its_own_spelling():
    said, params = _asked(_Leg(x={"column": "x", "kind": "float"}), [("9",), ("9.0",), ("x",), ("0.25",)])
    assert 'w."x"' in said and "SPELLED" not in said
    assert sorted(params["p0"]) == [0.25, 9.0]


def test_a_time_key_is_its_instant_in_its_own_spelling():
    leg = _Leg(at={"column": "at", "kind": "time", "zone": "Asia/Seoul"})
    said, params = _asked(leg, [("2026-08-14T00:03:00+09:00",), ("2026-08-14 00:03:00",)])
    assert 'w."at"' in said and "timestamptz[]" in said
    assert [each.isoformat() for each in params["p0"]] == ["2026-08-14T00:03:00+09:00"]


def test_a_column_with_rules_stays_spelled(monkeypatch):
    monkeypatch.setattr(notation_norm, "rules_for_column", lambda relation, column: ["upper"])
    said, params = _asked(_Leg(name={"column": "name", "kind": "text"}), [("A",)])
    assert "SPELLED(name)" in said and params["p0"] == ["A"]


def test_nothing_held_reads_nothing():
    said, _params = _asked(_Leg(x={"column": "x", "kind": "float"}), [("9.0",)])
    assert said == "false"
