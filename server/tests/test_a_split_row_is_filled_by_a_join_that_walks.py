"""Split template step 3 through the join's own read and answer (lead 10-28): the expanded split rows (left) joined on
their item text to the item map (right, step 2's table), a take «fn: walk» writing each row's value and why - one walk
for the batch. Declared as an operator writes it; the ledger is the report values gate's in-memory one."""
import pytest

from chain import join_into, rule_shape
from database import crud, models
from conftest import retire_dynamic_model
from test_a_report_reads_the_quantities_values_by_two_walks import VALUES, _step_label, ledger  # noqa: F401

pytestmark = pytest.mark.usefixtures("stored_walks")   # a stored-only ledger fixture (11-10)

TABLES = {
    "sf_rows": {"composite_key_source": ["lot", "split", "item_text"], "column_types": {
        "lot": "string", "split": "string", "item_text": "string", "wafer": "string", "value": "string",
        "why": "string"}},
    "sf_map": {"composite_key_source": ["item_text"], "column_types": {"item_text": "string", "quantity": "string"}},
}
DECLARATION = {"name": "split_fill", "on": {"table": "sf_map"}, "into": {"table": "sf_rows"},
               "derive": {"kind": "join", "join": {"on": [{"left": "item_text", "right": "item_text"}], "take": [
                   {"from": "quantity", "into": "value", "fn": "walk", "walk": dict(VALUES), "row": ["wafer"],
                    "why": "why"}]}}}


@pytest.fixture
def world(db_session, ledger):
    models.init_dynamic_models(TABLES)
    m = models.DYNAMIC_TABLES
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        m[name].__table__.create(bind=db_session.get_bind())
    for n, (split, text, wafer) in enumerate((("base", "M2 두께", "W1"), ("leg", "M2 두께", "W3"),
                                              ("base", "via CD", "W1"), ("base", "아무거나", "W1"))):
        db_session.add(m["sf_rows"](row_id="r%d" % n, lot="L1", split=split, item_text=text, wafer=wafer))
    for n, (text, quantity) in enumerate((("M2 두께", "PA40-THK"), ("via CD", "PA60-CD"), ("아무거나", "not found"))):
        db_session.add(m["sf_map"](row_id="m%d" % n, item_text=text, quantity=quantity))
    db_session.commit()
    yield db_session
    db_session.rollback()
    for name in TABLES:
        m[name].__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(name)


def test_each_split_row_gets_its_value_or_why_and_the_batch_walks_once(world, ledger):
    rules, refusal, _notes = rule_shape.expand_declaration(DECLARATION)
    assert refusal is None, refusal
    target_side = next(r for r in rules if r.get("trigger_table") == "sf_rows")
    ledger["walks"].clear()
    answer = join_into.propose(world, target_side, ["r0", "r1", "r2", "r3"])
    said = {u["row_id"]: (u["updates"].get("value"), u["updates"].get("why"), sorted(set(u["updates"]) & {"value", "why"}))
            for u in answer["updates"]}
    step = _step_label(ledger)
    assert said == {"r0": ("12.3", None, ["value"]),
                    "r1": ("12 (est · %s · 3 wf)" % step, None, ["value"]),
                    "r2": (None, "no value", ["why"]),
                    "r3": (None, "no mapping", ["why"])}
    assert len(ledger["walks"]) == 2, "a model walk and a wafer walk for the four rows"
