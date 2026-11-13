"""A sentence with no object (a registration) is a virtual leg whose object end is none (`sql_translate.NO_OBJECT`, lead
11-10 ㄷ): its rows are read from the subject's side only, a far-type door never keeps it (the stored read: no far end
passes no far type), and its atom is the stored one - object kind None, payload {}."""
from types import SimpleNamespace

from ledger.sql_translate import NO_OBJECT
from ledger_api.ledger_subgraph import VirtualEvidenceLookup

SEED = [("wafer", {"wafer": "W1"})]


class _Read(VirtualEvidenceLookup):
    def __init__(self):                         # no connection - `_arms` spells SQL only
        self.filters = {}                       # no value filter asked (e805afa11)

    @staticmethod
    def _in(leg, arm, texts, params, name):
        return "%s:%s" % (arm, sorted(texts))


def _leg():
    ends = {"outgoing": ("wafer", {"wafer": {"column": "wafer_id"}}), "incoming": NO_OBJECT}
    return SimpleNamespace(predicate="register", ends=ends,
                           named=lambda arm, entities: [(item, (item[1]["wafer"],)) for item in entities
                                                        if item[0] == ends[arm][0]])


def test_its_rows_are_read_from_the_subject_side_only():
    assert _Read()._arms(_leg(), "both", SEED, {}) == "((outgoing:[('W1',)]))"
    assert _Read()._arms(_leg(), "incoming", SEED, {}) is None


def test_a_far_type_door_never_keeps_it():
    for mode in ("in", "out"):
        assert _Read()._arms(_leg(), "both", SEED, {}, far_types=(mode, {"recipe"})) is None


def test_its_atom_is_the_stored_one():
    assert VirtualEvidenceLookup._object(None, {}) == (None, {})
    assert VirtualEvidenceLookup._object("recipe", {"recipe": "R"}) == ("entity_ref", {"type": "recipe",
                                                                                       "keys": {"recipe": "R"}})
