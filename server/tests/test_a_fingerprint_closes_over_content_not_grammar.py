# -*- coding: utf-8 -*-
"""S-87, grade 1. A source's fingerprint must move when its DECLARATION moves - and only then.

🔴 THE INCIDENT. `source_cursor_fingerprint` serialised each compiled descriptor by
walking `fields()`, so the hash closed over the descriptor's SHAPE as well as the
declaration's content. Deleting `EntityTypeDescriptor.key_types` - a field neither the live
config nor the shipped sample ever filled - moved ALL FIFTEEN fingerprints on 2026-09-09.
Every cursor then refused with `cursor_snapshot_reset_required`, the owner's ledger stopped at
the previous day's backfill, and it took a person running `ledger_restamp_cursor.py --apply`
by hand to start again.

⚠️ THE REFUSAL ITSELF IS CORRECT and is not what changed. A cursor whose declaration
moved must stop. What changed is that a GRAMMAR edit no longer counts as its declaration
moving, and that the one-time stop such a change still causes is cleared by the process
itself at boot rather than by a person.
"""
from dataclasses import dataclass, field
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.setup_registry import _semantic_plain                    # noqa: E402
from ledger.store import LedgerStore                                 # noqa: E402


@dataclass(frozen=True)
class Narrow:
    name: str
    columns: tuple = ()


@dataclass(frozen=True)
class Wide:
    """`Narrow` after a grammar round added a key nobody has filled in yet."""

    name: str
    columns: tuple = ()
    key_types: dict = field(default_factory=dict)
    exclude_when: tuple = ()


def test_a_grammar_key_no_one_filled_does_not_move_the_material():
    """🔴 THE HEADLINE, AND THE EXACT SHAPE OF THE INCIDENT. Adding - or removing - a
    descriptor field that no declaration uses must leave the serialised material identical,
    because nothing about what this source translates has changed."""
    assert _semantic_plain(Wide(name="dt_job", columns=("a",))) ==         _semantic_plain(Narrow(name="dt_job", columns=("a",)))


def test_a_filled_key_does_move_it():
    """The arm that must NOT be lost. The whole point of the fingerprint is to stop a cursor
    whose declaration changed, so a key that was actually ANSWERED has to count."""
    assert _semantic_plain(Wide(name="dt_job", columns=("a",), key_types={"lot": "string"}))         != _semantic_plain(Narrow(name="dt_job", columns=("a",)))


def test_false_and_zero_and_empty_string_are_answers_rather_than_absences():
    """⛔ THE LINE BETWEEN 「unfilled」 AND 「answered with nothing」. `enabled: false` is a
    decision an author wrote; dropping it would let turning a source OFF read as the same
    declaration as never mentioning it."""
    @dataclass(frozen=True)
    class Flagged:
        enabled: bool = True
        retries: int = 1
        label: str = "x"

    plain = _semantic_plain(Flagged(enabled=False, retries=0, label=""))
    assert plain == {"enabled": False, "retries": 0, "label": ""}


def test_an_empty_container_is_an_absence():
    """The other side of that line, and it is what makes the headline work: `()` and `{}`
    mean 「no columns declared」, which is what a missing key means too."""
    assert _semantic_plain(Narrow(name="x", columns=())) == {"name": "x"}


# ------------------------------------------------------ the one predicate, shared

def decision(stored, wanted="ledger-v2:new"):
    return LedgerStore.restamp_decision(stored, wanted)


def test_a_cursor_whose_content_is_unchanged_may_be_restamped():
    verdict, _reason = decision("ledger-v2:old")
    assert verdict == "restamp"


def test_a_cursor_already_carrying_the_wanted_string_is_left_alone():
    assert decision("ledger-v2:new")[0] == "already"


def test_a_source_with_no_cursor_row_is_not_a_restamp():
    """⚠️ 「nothing to move」 IS NOT 「moved」. A first run writes the current string by
    itself, and reporting this as a re-stamp would put a number in the log for work nobody
    did."""
    assert decision(None)[0] == "absent"


def test_a_v1_shaped_cursor_is_refused_by_name_and_not_moved():
    """⛔ THE REFUSAL THE DAEMON MUST INHERIT. Re-stamping a v1 cursor hides its own gate
    (`legacy_cursor_reset_required`, which reads `cursor_value`'s SHAPE) behind a v2-looking
    string while the position stays v1-shaped. The boot step asks THIS function, so it cannot
    be more permissive than the script an operator would have run."""
    verdict, reason = decision("legacy-v1:whatever")
    assert verdict == "refused"
    assert "v2" in reason


# --------------------------------------------- the boot that clears the one-time stop

def test_a_boot_restamps_the_moved_cursors_and_names_every_one(monkeypatch, caplog):
    """🔴 THE GATE THAT MAKES THIS SAFE TO LAND. This very change moves all fifteen
    fingerprints - measured on the shipped sample - because dropping unfilled fields rewrites
    the canonical JSON for every source. Landing that alone would stop the operator's ledger
    exactly as the last one did. The daemon now clears it at boot, and says which.

    ⚠️ THE POSITION IS NOT IN THE WRITE. `restamp_cursor` moves `translator_ver` and nothing
    else, so no row is re-read and no atom is re-emitted; a reset would re-read rows already
    in the ledger and land them AGAIN under the new fingerprint.
    """
    import logging
    import chain_ingestion_worker as worker
    from ledger import setup as ledger_setup, store as ledger_store
    from ledger import setup_registry

    written = []

    class _Store:
        def __init__(self, engine):
            pass

        restamp_decision = staticmethod(LedgerStore.restamp_decision)

        def connection(self):
            class _C:
                def close(self_inner):
                    pass
            return _C()

        def read_cursor(self, connection, source):
            return {"translator_ver": {"stale": "ledger-v2:old",
                                       "fresh": "ledger-v2:new",
                                       "legacy": "v1-cursor"}[source],
                    "cursor_value": {"row_id": "R7"}}

        def restamp_cursor(self, source, *, expect, translator_ver):
            written.append((source, expect, translator_ver))
            return True

    snapshot = type("S", (), {"source_plans": {"stale": None, "fresh": None,
                                               "legacy": None}})()
    monkeypatch.setattr(ledger_setup, "load_setup",
                        lambda *a, **k: type("Setup", (), {"snapshot": snapshot})())
    monkeypatch.setattr(ledger_store, "LedgerStore", _Store)
    monkeypatch.setattr(setup_registry, "cursor_translator_version",
                        lambda snap, source: "ledger-v2:new")

    class _Session:
        def get_bind(self):
            return None

        def close(self):
            pass

    with caplog.at_level(logging.INFO):
        worker._restamp_moved_fingerprints_sync(lambda: _Session())

    assert written == [("stale", "ledger-v2:old", "ledger-v2:new")], (
        "only the cursor whose content is unchanged may be moved")

    said = " ".join(record.getMessage() for record in caplog.records)
    assert "stale" in said and "position stays" in said, (
        "a fingerprint that moves silently cannot be audited, and this runs every boot")
    assert "legacy" in said, "the v1 cursor must be named as NOT re-stamped, not skipped"
