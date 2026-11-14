"""Two legs whose census SQL is the same read it once a walk (lead 11-14: box key-values wafer read inspection_run twice) -
and the census answers as if each leg had read its own: predicates, rows naming a node, its first time. A leg on the
same relation with other SQL reads its own rows."""
from types import SimpleNamespace

from ledger_api.ledger_subgraph import VirtualEvidenceLookup

SAID = ["w.k <> ''"]
OTHER = ["w.k <> ''", "w.flag"]
ROWS = {"same": [("W1", 2, 10), ("W2", 1, 30)], "other": [("W1", 5, 5), ("W3", 4, 40)]}


def _leg(predicate, said):
    return SimpleNamespace(predicate=predicate, relation="t", basis=None,
                           ends={"outgoing": ("wafer", {"wafer": {"column": "k"}}), "incoming": ("recipe", {})},
                           columns_of=lambda arm: [("wafer", {"column": "k"})] if arm == "outgoing" else [],
                           key=lambda spec: "w." + spec["column"], said=lambda: said, at=lambda: "w.at",
                           instant=lambda value: value)


class _Census(VirtualEvidenceLookup):
    def __init__(self, legs):                   # no connection - `_execute` answers from ROWS
        self.legs, self._census_of, self._census_rows, self.asked = legs, {}, {}, []

    def _execute(self, sql, params):
        self.asked.append(sql)
        return list(ROWS["other" if "w.flag" in sql else "same"])


def test_the_same_statement_is_read_once_and_each_leg_takes_its_rows():
    lookup = _Census([_leg("made_of", SAID), _leg("seen_in", SAID), _leg("flagged", OTHER)])
    census = lookup._census("wafer")
    assert len(lookup.asked) == 2 and len(set(lookup.asked)) == 2, lookup.asked
    got = {text: (keys, count, first, sorted(predicates)) for text, (keys, count, first, predicates) in census.items()}
    assert got == {
        '{"wafer":"W1"}': ({"wafer": "W1"}, 2 + 2 + 5, 5, ["flagged", "made_of", "seen_in"]),
        '{"wafer":"W2"}': ({"wafer": "W2"}, 1 + 1, 30, ["made_of", "seen_in"]),
        '{"wafer":"W3"}': ({"wafer": "W3"}, 4, 40, ["flagged"]),
    }, got


def test_a_second_census_in_the_same_walk_asks_nothing_again():
    lookup = _Census([_leg("made_of", SAID), _leg("seen_in", SAID)])
    first = lookup._census("wafer")
    assert lookup._census("wafer") is first and len(lookup.asked) == 1
