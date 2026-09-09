# -*- coding: utf-8 -*-
"""판정 179 ⓑ. A binding the compiler never reads: say so, do not refuse it.

`roleframe` fills a TIME role from the instant the preparation boundary already interpreted
and IGNORES the column the binding names -- ALWAYS, not only where the two coincide (its own
ruling, 2026-08-23: re-reading the cell would disagree with the event id minted from that
same value). Where the source ALSO declares `read.occurred_at.basis`, the declaration says
out loud that its time comes from elsewhere, and the cell beside it decides nothing.

🔴 WHY IT IS NOT REFUSED, AND THIS IS THE WHOLE RULING. Two shipped mappings carry such a
cell. A refusal means editing their declarations, and editing a declaration RE-TRANSLATES it
-- which is the one thing the freeze round promised not to do (F-0: a source that uses none
of the new slots must not move). So the form stops ASKING and the loader NAMES it; the
removal waits for the retirement round.

⛔ AND IT IS NOT HIDDEN EITHER. Dropping the row would take an author who wrote `event_time`
there and make their square vanish with no explanation. `derived` is this form's word for
「answered elsewhere」, so the row stops being a question without stopping being visible.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config_authoring, setup                          # noqa: E402


def bundle_with(basis, column):
    """A source whose time comes from `basis`, with a mapping naming `column` anyway."""
    source = {
        "relation": "parts",
        "read": {"unit": "row", "identity": ["row_id"], "group_by": [],
                 "order_by": ["row_id"],
                 "occurred_at": ({"basis": basis} if basis else {"column": "seen_at"})},
        "prepare": {}, "map": {},
        "bind": {"mappings": {"counted": {
            "predicate": "counted@1",
            "bind": ({"occurred_at": {"kind": "column", "column": column}}
                     if column else {})}}},
    }
    return {"dt_job": source}


def test_the_loader_names_every_dead_cell_by_its_path():
    """⛔ NOT A COUNT. 「2 dead cells」 tells an operator nothing they can act on; the path
    is what they can go and look at."""
    cells = setup._dead_time_cells(bundle_with("ingested", "event_time"))

    assert len(cells) == 1
    assert "sources.dt_job.bind.mappings.counted.bind.occurred_at=event_time" in cells[0]
    assert "ingested" in cells[0], "the reason has to travel with the path"


def test_a_source_that_reads_its_time_from_a_column_names_nothing():
    """The arm that must NOT fire. Without it this helper could return every mapping in
    the declaration and the line would be noise on every load."""
    assert setup._dead_time_cells(bundle_with(None, "seen_at")) == []


def test_a_source_with_a_basis_and_no_such_binding_names_nothing():
    assert setup._dead_time_cells(bundle_with("ingested", None)) == []


def test_the_shipped_sample_is_what_this_was_measured_on():
    """🔴 THE REASON THE REFUSAL COULD NOT LAND. These are real, they ship, and refusing
    them would move their fingerprints."""
    import io
    import json

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "config", "sample", "ledger_config.json.sample")
    cells = setup._dead_time_cells(
        json.load(io.open(path, encoding="utf-8"))["sources"])

    assert cells, "the sample used to carry dead time cells; if it no longer does, say so"
    assert all("basis ingested" in cell for cell in cells)


def test_the_form_shows_the_time_row_as_decided_elsewhere_rather_than_asking():
    """`derived` is 「answered elsewhere」. A `missing`/`unanswered` row here would be the
    screen asking a question whose answer changes nothing."""
    import inspect

    body = inspect.getsource(config_authoring._mapping_fields)
    assert 'role.get("kind") == "time"' in body
    assert '"time_from_source_basis"' in body
    # ⛔ NOT DROPPED. The row survives, so a declaration that already carries a column here
    # keeps its square instead of losing it without explanation.
    assert 'state="derived"' in body


# --------------------------------------------------------------------------- S-97

def test_the_dead_cell_line_is_said_once_per_process_and_again_if_it_changes():
    """S-97. The comment claimed "once" and the code said it on EVERY `load_setup`.

    `load_setup` is called by the census job (per tick, per source), the follow-up drain
    loop, the declaration routes and retroactive runs, so the same sentence reached the
    ledger log hundreds of times. A line repeated that often is one nobody reads - the very
    failure the sentence exists to prevent.

    ⚠️ THE KEY IS THE CELLS, NOT A FLAG. Silencing it forever after one load would trade a
    noisy truth for a quiet one: when a declaration changes so that a DIFFERENT cell goes
    dead, that is exactly when an operator needs to be told.
    """
    setup._DEAD_CELLS_ANNOUNCED.clear()
    try:
        assert setup._announce_dead_cells(["a.b.occurred_at"]) is True
        assert setup._announce_dead_cells(["a.b.occurred_at"]) is False, (
            "the same sentence must not be said twice in one process")

        assert setup._announce_dead_cells(["c.d.occurred_at"]) is True, (
            "a different dead cell is a different fact and has to be said")

        assert setup._announce_dead_cells([]) is False, "nothing dead, nothing said"
    finally:
        setup._DEAD_CELLS_ANNOUNCED.clear()


# ------------------------------------------------------- 판정 202 ①: the check's own scope

def profile_bundle(implementation, subject_column, target_column):
    """A source binding an entity at both ends of one sentence, under a named mapper."""
    def entity(column):
        return {"kind": "entity", "type": "lot@1",
                "keys": {"lot_id": {"kind": "column", "column": column}}}

    return {"lot_event": {
        "relation": "lot_log",
        "read": {"unit": "row", "identity": ["row_id"], "group_by": [],
                 "order_by": ["row_id"], "occurred_at": {"column": "event_time"}},
        "prepare": {}, "map": {"implementation_id": implementation},
        "bind": {"mappings": {"descent": {
            "predicate": "descends_from@1",
            "bind": {"subject": entity(subject_column),
                     "target": entity(target_column)}}}},
    }}


def test_a_sentence_no_one_scored_is_named_with_the_mapper_that_decides_instead():
    """🔴 THE SILENCE MEANT TWO OPPOSITE THINGS (판정 202 ①, 응용 D-12-2).

    `_validate_no_self_edge` is scored only where a `declarative-role` mapper EXECUTES the
    bindings - written without that distinction it refused the live setup on a placeholder
    that had stood harmlessly for weeks. Correct, and invisible: an author whose sentence was
    checked and passed, and one whose sentence nobody looked at, saw the same nothing.
    """
    unscored = setup._unscored_self_edge_sentences(
        profile_bundle("lot-event-role", "child_lot", "child_lot"))

    assert len(unscored) == 1
    assert "sources.lot_event.bind.mappings.descent" in unscored[0]
    assert "lot-event-role" in unscored[0], (
        "which mapper decides instead is the actionable half; a path alone sends the "
        "reader back to the declaration that is not the authority")


def test_a_source_whose_bindings_are_executed_names_nothing():
    """The arm that must NOT fire. Without it this line would name every entity-to-entity
    sentence in the declaration, including all the ones that WERE checked."""
    assert setup._unscored_self_edge_sentences(
        profile_bundle("declarative-role", "child_lot", "child_lot")) == []


def test_a_sentence_that_is_not_entity_to_entity_names_nothing():
    """⛔ SAME PAIR AS THE CHECK READS. The check only examines a sentence whose two ends are
    both entity bindings, so naming a wider set would report sentences that were never in
    its scope - a line that overstates what went unlooked-at is its own false log."""
    bundle = profile_bundle("lot-event-role", "child_lot", "parent_lot")
    bundle["lot_event"]["bind"]["mappings"]["descent"]["bind"]["target"] = {
        "kind": "value", "column": "parent_lot"}

    assert setup._unscored_self_edge_sentences(bundle) == []


def test_the_shipped_sample_is_what_this_was_measured_on_too():
    """🔴 THE REAL CASE. `lot_event` reads its roles through a PYTHON mapper, and its three
    entity-to-entity sentences are exactly the ones the check steps over. This is the source
    whose `descent` refused the live setup when the distinction was missing."""
    import io
    import json

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "config", "sample", "ledger_config.json.sample")
    unscored = setup._unscored_self_edge_sentences(
        json.load(io.open(path, encoding="utf-8"))["sources"])

    assert unscored, "the sample carries delegated sentences; if it no longer does, say so"
    assert all("mapper lot-event-role" in item for item in unscored)


def test_the_delegation_line_is_said_once_per_process_and_again_if_it_changes():
    """S-97's discipline, because this line has S-97's problem: `load_setup` runs per census
    tick, per drain and per declaration route."""
    setup._DELEGATED_BINDINGS_ANNOUNCED.clear()
    try:
        assert setup._announce_unscored_bindings(["sources.a.bind.mappings.x"]) is True
        assert setup._announce_unscored_bindings(["sources.a.bind.mappings.x"]) is False

        assert setup._announce_unscored_bindings(["sources.b.bind.mappings.y"]) is True, (
            "a different set of delegated sentences is a different fact")

        assert setup._announce_unscored_bindings([]) is False
    finally:
        setup._DELEGATED_BINDINGS_ANNOUNCED.clear()
