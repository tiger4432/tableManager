"""Split template step 3 (owner 10-27 e88e6d882 #3, lead 10-28 ㄱ): a join take «fn: walk» - the quantity the key's
mapping row hands, walked from the row's wafer(s) as a report's values are (one function, `report_reads.model_walk` ·
`wafer_walk` · `value_of`): own, else the same-transaction estimate; several wafers the mean and n; no node -> «no
mapping», no value -> «no value» in the `why` column. One walk a batch, however many rows. The ledger is the report
values gate's in-memory one (W1 own 12.3 · W2 est from one · W3 est from three · W0 nothing)."""
import pytest

from chain import join_into, rule_shape
from test_a_report_reads_the_quantities_values_by_two_walks import DB, VALUES, _step_label, ledger  # noqa: F401

WALK = {"fn": "walk", "walk": dict(VALUES), "row": ["wafers"], "why": "why"}
THK, CD = "PA40-THK", "PA60-CD"


def _made(rows, values):
    return join_into.walked(DB(), dict(WALK), values, rows)


def test_one_wafer_says_its_own_or_its_estimate_and_several_their_mean(ledger):
    made = _made([{"wafers": w} for w in ("W1", "W2", "W3", "W0")] + [{"wafers": ["W1", "W2", "W3"]}], [THK])
    value, why = made["value"], made["why"]
    step = _step_label(ledger)
    assert value([THK], {"wafers": "W1"}, {}) == "12.3" and why([THK], {"wafers": "W1"}, {}) is None
    assert value([THK], {"wafers": "W2"}, {}) == "12 (est · %s · 1 wf)" % step
    assert value([THK], {"wafers": "W3"}, {}) == "12 (est · %s · 3 wf)" % step
    assert value([THK], {"wafers": ["W1", "W2", "W3"]}, {}) == "12.1 (mean · 3 wf)", "12.3 · 12 · 12"
    assert (value([THK], {"wafers": "W0"}, {}), why([THK], {"wafers": "W0"}, {})) == (None, "no value")


def test_a_key_the_ledger_has_no_node_for_is_no_mapping_whatever_word_it_holds(ledger):
    made = _made([{"wafers": "W1"}], [THK, "not found"])
    assert (made["value"](["not found"], {"wafers": "W1"}, {}), made["why"](["not found"], {"wafers": "W1"}, {})) == (
        None, "no mapping"), "the none word of the item map is no node - the fill never learns it"
    assert made["why"]([CD], {"wafers": "W1"}, {}) == "no value", "a node with no value anywhere"


def test_the_words_are_the_declarations_when_it_says_them(ledger):
    made = join_into.walked(DB(), dict(WALK, walk=dict(VALUES, labels={"no_mapping": "unmapped"})), ["x"], [{"wafers": "W1"}])
    assert made["why"](["x"], {"wafers": "W1"}, {}) == "unmapped"


def test_one_walk_a_batch_however_many_rows(ledger):
    _made([{"wafers": "W1"}], [THK])
    one = len(ledger["walks"])
    ledger["walks"].clear()
    _made([{"wafers": w} for w in ("W1", "W2", "W3", "W0", "S1", "S5") * 4], [THK, CD])
    assert one == len(ledger["walks"]) == 2, "a model walk and a wafer walk"


@pytest.mark.parametrize("take,words", [
    (dict(WALK, row=[]), "row names the target column"),
    (dict(WALK, walk=dict(VALUES, follow=["nope"])), "take walk names nope"),
    (dict(WALK, walk=dict(VALUES, extra=1)), "walk extra - not a cell"),
])
def test_a_walk_take_that_cannot_stand_is_refused_by_name(ledger, take, words):
    record = {"fn": "walk", **{k: v for k, v in take.items() if k in ("walk", "row")}}
    assert words in join_into.walked.refusal(record)


def test_one_take_item_with_why_is_two_gathered_columns_of_one_function():
    spec = {"take": [dict(WALK, **{"from": "quantity", "into": "value"})]}
    assert [into for _right, into in join_into._takes(spec)] == ["value", "why"]
    fns = join_into._fn_takes(spec)
    assert sorted(fns) == ["value", "why"] and fns["why"][1]["of"] == "value"
    assert rule_shape  # the declaration's form carries walk and why: test_chain_skeleton
