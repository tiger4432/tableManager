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
