# -*- coding: utf-8 -*-
"""The refusal knew which field was wrong and the answer never left the process.

`envelope.check_envelope` has answered `(code, path, message)` since it landed, and
`screen_molecule` has carried them in `report["violation_details"]` ever since. Measured
2026-09-05: that key had two writers and ZERO readers, `gate.samples()` had zero callers,
`gate.captured()` had zero callers, and the one production caller of the report discarded
it. So an operator got a sentence and no address -- "which field do I fix" had no answer
while three carriers held it.

Nothing new is computed here. The refusal path hands the addresses it already has to
`gate.refuse`, which stamps them on the sample list, and a backfill run reports that list.

⛔ NOT ON THE COUNTS. `_refusals` is `(source, reason) -> count` and its invariant is that
the breakdown SUMS to the number of refusals. An address per atom breaks that equality
while still looking right, which is why the carrier is the sample list -- capped, one entry
per refusal, and in no sum at all.

⚠️ AND THE CAP IS SAID AS A NUMBER. "400 refused, 20 addressed" must not render as "20
refusals": truncation read as absence is the same failure class one layer up.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import envelope, gate                                # noqa: E402

ADDRESS = {"code": envelope.ENVELOPE_RAW_REF_EMPTY,
           "path": "atom.source.raw_ref", "message": "source.raw_ref is empty"}


@pytest.fixture(autouse=True)
def clean_counters():
    gate.reset_counters()
    yield
    gate.reset_counters()


def refuse(addresses=(), source="probe"):
    gate.refuse(source, gate.REFUSE_NO_RAW_REF, "detail", atoms=2, rows=1,
                addresses=addresses)


# ------------------------------------------------------------------- the address arrives

def test_the_address_reaches_the_published_sample():
    refuse([ADDRESS])
    got = gate.samples()[0]["addresses"]
    assert got == [{"code": envelope.ENVELOPE_RAW_REF_EMPTY,
                    "path": "atom.source.raw_ref"}]


def test_the_sentence_is_not_repeated_into_the_address():
    """It is already in `detail`; carrying it twice puts the same text in the payload
    twice and invites a screen to render both."""
    refuse([ADDRESS])
    assert set(gate.samples()[0]["addresses"][0]) == {"code", "path"}


def test_a_refusal_with_no_address_reports_an_empty_list_not_a_missing_key():
    """A reader that has to tell "no address" from "the key is gone" is reading two
    shapes for one state."""
    refuse()
    assert gate.samples()[0]["addresses"] == []


def test_every_envelope_code_can_travel():
    for code in (envelope.ENVELOPE_OCCURRED_AT_MISSING, envelope.ENVELOPE_OCCURRED_AT_NAIVE,
                 envelope.ENVELOPE_SOURCE_WHO_EMPTY, envelope.ENVELOPE_TRANSLATOR_VER_EMPTY,
                 envelope.ENVELOPE_RAW_REF_EMPTY,
                 envelope.ENVELOPE_PAYLOAD_NOT_PRESERVABLE):
        gate.reset_counters()
        refuse([{"code": code, "path": "atom.probe"}])
        assert gate.samples()[0]["addresses"][0]["code"] == code


# ------------------------------------------------- ⛔ the counts keep their invariant

def test_the_breakdown_still_sums_to_the_number_of_refusals():
    """🔴 THE FORBIDDEN PLACE. Hanging an address off `_refusals` would break this equality
    while every screen still rendered. The application lane found that before it was
    written, and this is the assertion that keeps it found."""
    for _ in range(3):
        refuse([ADDRESS, {"code": "second", "path": "atom.other"}])
    assert sum(gate.refusals().values()) == 3
    assert sum(gate.rows_refused().values()) == 3


def test_the_counts_do_not_carry_an_address_at_all():
    refuse([ADDRESS])
    for key in gate.refusals():
        assert isinstance(key, tuple) and len(key) == 2
    assert all(isinstance(v, int) for v in gate.refusals().values())


# --------------------------------------------------------- ⚠️ truncation is said, in numbers

def test_the_sample_list_is_capped_and_the_total_is_not():
    """The two numbers a reader needs. With only the list, 400 refusals render as 20."""
    for _ in range(gate.MAX_REFUSAL_SAMPLES + 7):
        refuse([ADDRESS])
    assert len(gate.samples()) == gate.MAX_REFUSAL_SAMPLES
    assert sum(gate.refusals().values()) == gate.MAX_REFUSAL_SAMPLES + 7


def test_the_run_result_publishes_both_counts_and_flags_the_cap():
    """🔴 THE DESTINATION. `backfill`'s result is what an operator already reads back, so
    this is a read of a value that existed, not a new surface."""
    import inspect

    from ledger import backfill

    body = inspect.getsource(backfill._run_v2_lineage)
    for name in ("refused_total", "refused_samples", "refused_samples_capped"):
        assert '"%s"' % name in body, "the run result stopped reporting %s" % name
    assert "gate.samples()" in body and "gate.refusals()" in body


def test_the_refusal_path_is_what_carries_it_not_the_returned_report():
    """⚠️ THE PREMISE WORTH PINNING. `screen_compiled_molecule` is called inside
    `building_molecule`, where `gate.refuse` RAISES -- so the pair the caller binds is only
    ever the accepting answer, and reading it there would yield nothing about a refusal.
    That is why the addresses go out through `refuse`."""
    import inspect

    body = inspect.getsource(gate.screen_compiled_molecule)
    assert "addresses=report.get(\"violation_details\")" in body, (
        "the refusal stopped carrying the addresses the report worked out")
