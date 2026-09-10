# -*- coding: utf-8 -*-
"""인덱스는 «선언»에서 나온다 — 도메인 낱말이 코드에 없다 (S-94, 판정 237).

🔴 WHY THIS FILE EXISTS. An alignment view build runs one
`SELECT DISTINCT … FROM <source> WHERE <decision_key> = ? ORDER BY …` per job, and the
alignment mapper builds one view per job. Measured on this box: a Seq Scan removing
109,877 rows to keep 88, 21.96 ms, one thousand times per chain group - 23.8 s of a 44.9 s
group, the single largest thing the chain does.

⛔ AND THE FIX MUST NOT KNOW A DOMAIN WORD. `dt_job` appears in no product line: the
columns are `decision_key`, which is what the rule declares it keys on, so an installation
keying on something else gets an index on that instead with zero code changes. That is the
owner's definition of done ("두 줄로 말해진다: 이 규칙에 이 칸을 적으면 됩니다"), and it is
what these cases pin.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.models import (                                        # noqa: E402
    alignment_decision_key_index_ddl,
    map_key_index_ddl,
)


def test_the_columns_are_the_rules_declared_decision_key():
    name, ddl = alignment_decision_key_index_ddl(
        {"alignment": True, "source_table": "some_source", "decision_key": ["a", "b"]},
        {"kind": "table"})

    assert name == "idx_some_source_decision_key"
    assert '"a", "b"' in ddl, ddl
    assert 'ON "some_source"' in ddl
    assert "CONCURRENTLY" in ddl and "IF NOT EXISTS" in ddl


def test_a_view_gets_no_index_because_a_view_cannot_be_indexed():
    """The same refusal `map_key_index_ddl` already makes, and for the reason it records:
    without it `dt_log_transferable` failed on every boot and every config reload."""
    assert alignment_decision_key_index_ddl(
        {"alignment": True, "source_table": "v", "decision_key": ["a"]},
        {"kind": "view"}) == (None, None)


def test_a_rule_that_is_not_an_alignment_rule_asks_for_nothing():
    """⛔ THE COST BEING FIXED IS THE ALIGNMENT VIEW'S. An index for every enrichment rule
    would be a write cost on tables whose reads this never touches - the opposite of the
    standing rule about being careful with schema."""
    assert alignment_decision_key_index_ddl(
        {"source_table": "t", "decision_key": ["a"]}, {"kind": "table"}) == (None, None)


def test_a_rule_with_no_decision_key_asks_for_nothing():
    assert alignment_decision_key_index_ddl(
        {"alignment": True, "source_table": "t", "decision_key": []},
        {"kind": "table"}) == (None, None)


def test_the_map_key_builder_still_says_what_it_said():
    """⚠️ THE NEIGHBOUR, PINNED BECAUSE THIS ROUND MOVED ITS BUILD STEP. The CONCURRENTLY
    dance - including the invalid-leftover repair - was extracted so both ensures call one
    copy; the DDL each one asks for did not change, and nothing else covered that."""
    name, ddl = map_key_index_ddl("some_map", {"map_key_columns": ["k1", "k2"]})

    assert name == "idx_some_map_map_key"
    assert '"k1", "k2"' in ddl and 'ON "some_map"' in ddl
    assert map_key_index_ddl("v", {"kind": "view",
                                   "map_key_columns": ["k"]}) == (None, None)


def test_the_boot_sequence_calls_the_ensure_and_not_only_the_reload_path():
    """🔴 착지는 배선이 아니다 — AND THIS FILE'S OWN CHANGE PROVED IT ONE COMMIT LATER.

    The builder was wired into `create_missing_dynamic_tables`, which runs on a CONFIG
    RELOAD. A deployment that restarts never passes through it, so it would come up with
    the index still missing and every alignment view build still scanning its source. The
    seat that runs at boot is the chain worker's ensure sequence, beside the business-key
    unique index (판정 189).

    ⚠️ ASSERTED ON THE SOURCE OF THE STARTER, because the alternative is booting a worker
    in a test - and what can go wrong here is a call being deleted, which the text sees.
    """
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "_ensure_alignment_decision_key_indexes_sync" in body, body[:400]
    assert hasattr(worker, "_ensure_alignment_decision_key_indexes_sync")


def test_the_ensure_runs_with_no_config_because_boot_calls_it_that_way():
    """🔴 THE FALLBACK NOBODY HAD REACHED. Both ensures read a bare `TABLE_CONFIG` when a
    caller left `config` out, and this module has no such name - the reload path always
    passes one, so it had never been evaluated. The boot wiring reached it on its first
    run and the ensure died with `NameError`, saying so in the log.

    Asserted by CALLING it the way boot does, with a database double that answers nothing:
    what is being proved is that the function gets as far as asking the engine, not what
    the engine says.
    """
    from database import models

    class _Refuses:
        def connect(self):
            raise RuntimeError("no database here")

    # Rules are supplied so the call does not read the box's own declaration.
    created = models.ensure_alignment_decision_key_indexes(
        _Refuses(), config={"t": {"kind": "table"}},
        rules=[{"alignment": True, "source_table": "t", "decision_key": ["a"]}])
    assert created == [], "a database that refuses builds nothing, and does not raise"

    # And with no config at all - the shape boot uses - it must still resolve a catalogue.
    assert models.ensure_alignment_decision_key_indexes(_Refuses(), rules=[]) == []


def test_two_rules_over_one_table_ask_for_one_index_and_the_count_says_one():
    """🔴 A COUNT THAT IS NOT THE NUMBER OF THINGS THAT EXIST (깔끔 ①). The first boot
    logged "built 3" where the catalogue held 2: three alignment rules, two of them over
    the same table with the same decision key, so two of the three name one index.

    ⛔ SKIPPED, NOT DEDUPLICATED AT THE END, because the second pass would also issue a
    CONCURRENTLY build for an index the first pass just made."""
    from database import models

    built = []

    class _Engine:
        pass

    def _fake(engine, name, statement, what):
        built.append(name)
        return True

    original = models._ensure_one_index
    models._ensure_one_index = _fake
    try:
        created = models.ensure_alignment_decision_key_indexes(
            _Engine(), config={"t": {"kind": "table"}},
            rules=[{"alignment": True, "source_table": "t", "decision_key": ["a"]},
                   {"alignment": True, "source_table": "t", "decision_key": ["a"]},
                   {"alignment": True, "source_table": "u", "decision_key": ["a"]}])
    finally:
        models._ensure_one_index = original

    assert created == ["idx_t_decision_key", "idx_u_decision_key"]
    assert built == created, "the duplicate must not even be attempted"
