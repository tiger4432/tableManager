# -*- coding: utf-8 -*-
"""The preview refused every source that registers, while the apply it previews worked.

S-59. `preview_rescope` asked `_filtered_event_atoms` with a literal `None` where the line
directly above it asks `None if subjects is None else ()`. `None` there means "this source
declares no probe"; in `_filtered_event_atoms` it means "no snapshot was supplied", and that
is refused outright the moment any `register` atom appears
(`registration_context_required`). So the two most-used sources could never be previewed at
all -- and `rescope` itself offers `()` and has always worked, which is what made this
invisible: the number the operator was shown before applying was an exception, and the apply
was fine.

🔴 THE PREVIEW AND THE APPLY MUST ASK ON ONE BASIS. `rescope`'s docstring already says so in
as many words -- "the numbers it reports are the numbers this then produces, because both run
the SAME preview over the SAME scope". A preview that asks a different question is not a
preview.

⚠️ NO DATABASE HERE, AND THE FETCH IS THE ONLY THING STANDING IN. `_fetch_v2_lineage_rows`
and the ledger store are replaced; everything between them -- `_v2_frame`,
`_v2_registration_subjects`, `preview_selected_cursor_batch`, `_filtered_event_atoms` -- is
the production path, and it is where the defect lived.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                      # noqa: E402
from ledger.implementations import trusted_implementations       # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,          # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.implementations import (role_mapper_registry,         # noqa: E402
                                    source_preparer_registry)
from ledger.setup import LedgerSetup                             # noqa: E402
from ledger.setup_registry import compile_setup_snapshot         # noqa: E402
from pathlib import Path                                         # noqa: E402
from types import SimpleNamespace                                # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
OCCURRED_AT = "2026-09-08T01:00:00+09:00"


@pytest.fixture(scope="module")
def setup():
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), (), catalog=catalog)
    # The real type, because `preview_selected_cursor_batch` refuses a stand-in -- and it
    # should: a preview taken against something that is not the compiled setup is a
    # preview of nothing.
    return LedgerSetup(
        config_root=Path(SAMPLE), bundle=bundle, snapshot=snapshot,
        preparers=source_preparer_registry(), mappers=role_mapper_registry(),
        catalog=catalog)


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return (2,)


class FakeConnection:
    def cursor(self):
        return FakeCursor()

    def rollback(self):
        pass

    def close(self):
        pass


class FakeEngine:
    def raw_connection(self):
        return FakeConnection()


@pytest.fixture
def no_database(monkeypatch):
    """Everything the preview reaches OUT for, and nothing it decides."""
    import ledger.store as store_module

    monkeypatch.setattr(store_module, "LedgerStore",
                        lambda engine: SimpleNamespace(connection=FakeConnection))
    return FakeEngine()


def dt_log_rows(count=1):
    """What the fetch returns: exactly `base_select_columns(dt_job)` and nothing invented.

    `created_at` is there because `read.occurred_at.basis` is `ingested` -- the instant the
    ledger stamps this source's atoms with -- and leaving it out is refused by the
    preparation boundary rather than silently ignored.
    """
    return [{"created_at": OCCURRED_AT, "dt_cell_key": f"C{index}",
             "dt_eqp": "EQP-7", "dt_index": index, "dt_job": "SYN-DTJ-002-04",
             "event_time": OCCURRED_AT, "row_id": f"r{index}"}
            for index in range(count)]


def transfer_log_rows(count=1):
    """`base_select_columns(transfer_event)`, the source in this sample that registers
    NOTHING -- so it is the one that says whether anything moved for the rest of them."""
    return [{"b_wx": 1, "b_wy": 2, "c_wx": 3, "c_wy": 4,
             "core_wafer_id": "CW-1", "dt_cell_key": f"C{index}", "dt_job": "J1",
             "dt_job_id": "JID-1", "dt_x": 5, "dt_y": 6, "event_time": OCCURRED_AT,
             "product": "P1", "row_id": f"t{index}"}
            for index in range(count)]


def preview(setup, engine, monkeypatch, rows):
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows",
                        lambda *args, **kwargs: rows)
    return backfill.preview_rescope(
        engine, setup, "dt_job", "dt_job", ["SYN-DTJ-002-04"])


def test_a_source_that_registers_can_be_previewed(setup, no_database, monkeypatch):
    """🔴 THE GATE. `dt_job` emits `register`, which is what the refusal keyed on. The
    preview has to come back with numbers -- what it would withdraw and what it would
    remake -- rather than with an exception the operator cannot act on."""
    result = preview(setup, no_database, monkeypatch, dt_log_rows())
    assert result["source"] == "dt_job" and result["scope_column"] == "dt_job"
    assert result["rows_in_scope"] == 1
    assert result["remake"] > 0, "a scope holding rows must offer atoms to remake"
    assert result["refs"], "and it must name the refs the withdrawal will aim with"
    assert result["withdraw"] == 2


def test_the_preview_counts_the_register_the_apply_would_write(setup, no_database,
                                                               monkeypatch):
    """⚠️ NOT JUST "IT DID NOT RAISE". `()` means "nothing assumed already registered",
    which is the basis `rescope` applies on -- so the registration has to be AMONG the
    atoms counted. Passing a non-empty snapshot instead would return a smaller number that
    still looked like a working preview."""
    result = preview(setup, no_database, monkeypatch, dt_log_rows(2))
    # Two rows of one `dt_job` are ONE group, so the source says `register` once and
    # `has_netdie` once; the preview counts both.
    assert result["remake"] == 2


def test_the_preview_asks_on_exactly_the_basis_the_apply_offers(setup, no_database,
                                                                monkeypatch):
    """🔴 THE PROPERTY, NOT JUST THE SYMPTOM. Two spellings of one question is what this
    was, so what is pinned is the ARGUMENT: `()` for a source that declares a probe --
    "nothing assumed already registered", which is what `rescope` applies on -- and `None`
    for one that declares none, which is the one-sided safety that makes an unexpected
    `register` a refusal rather than a silent duplicate.

    Passing `()` unconditionally would fix the symptom and lose the second half; nothing
    else in this file could tell, because a source with no probe emits no `register`."""
    from ledger import runtime_v2

    seen = []
    real = runtime_v2._filtered_event_atoms
    monkeypatch.setattr(runtime_v2, "_filtered_event_atoms",
                        lambda results, known: (seen.append(known), real(results, known))[1])
    preview(setup, no_database, monkeypatch, dt_log_rows())
    # Two call sites -- the cursor preview inside `setup` and the count here -- and the
    # whole defect was that they disagreed. So EVERY call is scored, not the last one.
    assert len(seen) == 2 and all(basis == () for basis in seen), (
        "both askers must offer an empty snapshot for a source that registers")

    seen.clear()
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows",
                        lambda *args, **kwargs: transfer_log_rows())
    backfill.preview_rescope(
        no_database, setup, "transfer_event", "dt_cell_key", ["C0"])
    assert len(seen) == 2 and all(basis is None for basis in seen), (
        "a source that declares no probe must keep, at both askers, the refusal that "
        "catches an unexpected register")


def test_a_source_that_does_not_register_is_unchanged(setup, no_database, monkeypatch):
    """⚠️ THE OTHER HALF OF THE GATE. `transfer_event` never reached the defect, so its
    preview has to come back with the same numbers it always did."""
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows",
                        lambda *args, **kwargs: transfer_log_rows())
    result = backfill.preview_rescope(
        no_database, setup, "transfer_event", "dt_cell_key", ["C0"])
    assert result["rows_in_scope"] == 1 and result["remake"] == 1
    assert result["refs"] and result["withdraw"] == 2


def test_a_scope_that_finds_no_row_still_answers(setup, no_database, monkeypatch):
    """The empty scope never reached the defect and must not start reaching it: it returns
    before any registration question is asked."""
    result = preview(setup, no_database, monkeypatch, [])
    assert result["rows_in_scope"] == 0
    assert result["remake"] == 0 and result["refs"] == []
