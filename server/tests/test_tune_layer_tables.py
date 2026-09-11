# -*- coding: utf-8 -*-
"""S-170. The vacuum tool decides nothing, and this file is what keeps it that way.

The owner cannot issue SQL, so the remedy had to be a command.  The trap a command like
this falls into is the opposite one: picking the knob for them.  The owner's own correction
(2026-09-11, 「dead 는 거의 0 이야 다」) is exactly why it must not -- with no dead tuples a
resident autovacuum is autoANALYZE or an insert-triggered/anti-wraparound VACUUM, and those
are three different knobs.  So the script reads WHICH KIND ran out of PostgreSQL's own
words and leaves the choice to a person.

What is scored here is everything that can be scored without a database: the refusal on a
name, the discriminator on the worker's query text, the honesty note about counters that
may have been lost, and -- the important one -- that the two optional settings appear ONLY
when a person named them.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from scripts import tune_layer_tables as tool                        # noqa: E402


class _Args:
    """The parser's result, minus the parser.  Only the fields the builder reads."""

    def __init__(self, **kw):
        self.cost_delay = tool.VACUUM_DEFAULTS["autovacuum_vacuum_cost_delay"]
        self.cost_limit = tool.VACUUM_DEFAULTS["autovacuum_vacuum_cost_limit"]
        self.vacuum_scale_factor = tool.VACUUM_DEFAULTS[
            "autovacuum_vacuum_scale_factor"]
        self.analyze_scale_factor = None
        self.insert_scale_factor = None
        self.__dict__.update(kw)


# ---------------------------------------------------------------------------
# 1. ⛔ The owner's rule: no automatic judgement
# ---------------------------------------------------------------------------

def test_the_two_optional_knobs_are_absent_until_a_person_names_them():
    """KILLS: giving `--analyze-scale-factor` or `--insert-scale-factor` a default.

    A default IS the automatic judgement the owner forbade. The dry run exists to show
    which kind of autovacuum actually ran; deciding before that is the tool answering a
    question it has not asked yet."""
    settings = tool.setting_values(_Args())
    assert set(settings) == set(tool.VACUUM_DEFAULTS)
    assert "autovacuum_analyze_scale_factor" not in settings
    assert "autovacuum_vacuum_insert_scale_factor" not in settings


def test_a_named_knob_is_written_and_the_three_defaults_stay():
    settings = tool.setting_values(_Args(analyze_scale_factor="0.02"))
    assert settings["autovacuum_analyze_scale_factor"] == "0.02"
    assert settings["autovacuum_vacuum_cost_delay"] == "2"

    both = tool.setting_values(
        _Args(analyze_scale_factor="0.02", insert_scale_factor="0.05"))
    assert both["autovacuum_vacuum_insert_scale_factor"] == "0.05"
    assert len(both) == len(tool.VACUUM_DEFAULTS) + 2


@pytest.mark.parametrize("typed, stored", [
    ("2ms", "2"), ("2", "2"), (" 20 MS ", "20"), ("0", "0"),
])
def test_a_millisecond_suffix_is_accepted_and_stripped(typed, stored):
    """MEASURED, not anticipated: the first live `--apply` came back
    「오류: 숫자 뒤에 쓸모 없는 값이 더 있음, "2ms" 부근」. The GUC of this name takes a unit
    suffix and the STORAGE PARAMETER does not -- and `2ms` is the spelling both the
    documentation and the order use, so refusing it would be this tool being right at the
    operator's expense."""
    assert tool.setting_values(
        _Args(cost_delay=typed))["autovacuum_vacuum_cost_delay"] == stored


def test_every_default_can_be_overridden():
    """The order asked for these to be arguments, not constants: the right cost budget is
    a property of the deployment's disks, which no file in this tree knows."""
    settings = tool.setting_values(
        _Args(cost_delay="5ms", cost_limit="500", vacuum_scale_factor="0.1"))
    assert settings == {
        "autovacuum_vacuum_cost_delay": "5",
        "autovacuum_vacuum_cost_limit": "500",
        "autovacuum_vacuum_scale_factor": "0.1",
    }


def test_reset_clears_every_option_the_tool_can_write():
    """⛔ ASYMMETRY IS A TRAP. An option `--apply` can set and `--reset` cannot clear is a
    setting an operator can never undo through this tool."""
    statement = tool.reset_sql("cell_sources", set(tool.VACUUM_DEFAULTS)
                               | set(tool.OPTIONAL_SETTINGS.values()))
    for option in set(tool.VACUUM_DEFAULTS) | set(tool.OPTIONAL_SETTINGS.values()):
        assert option in statement


# ---------------------------------------------------------------------------
# 2. The discriminator: which KIND is running
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("autovacuum: VACUUM public.cell_sources", "VACUUM"),
    ("autovacuum: VACUUM ANALYZE public.audit_logs", "VACUUM + ANALYZE"),
    ("autovacuum: ANALYZE public.cell_overwrites", "ANALYZE"),
    ("autovacuum: VACUUM public.audit_logs (to prevent wraparound)",
     "VACUUM (anti-wraparound)"),
    ("SELECT 1", "not an autovacuum worker"),
    # ⛔ THE PREFIX CONTAINS THE WORD 「vacuum」, so a substring test reads every ANALYZE as
    # a VACUUM + ANALYZE. This case caught exactly that, and the one below is its mirror.
    ("autovacuum: ANALYZE public.vacuum_audit_log", "ANALYZE"),
    ("autovacuum: VACUUM public.analyze_queue", "VACUUM"),
])
def test_the_worker_says_which_job_it_is_and_the_tool_reads_it(query, expected):
    """🔴 THE FOUR ANSWERS ARE FOUR DIFFERENT KNOBS. Collapsing them into 「vacuum is
    running」 is what sent this round after dead tuples that were not there."""
    assert tool.autovacuum_kind(query) == expected


def test_wraparound_wins_over_the_plain_reading():
    """An anti-wraparound pass also says VACUUM, and it is the one an operator must NOT
    tune away -- so the more specific reading has to win."""
    assert tool.autovacuum_kind(
        "autovacuum: VACUUM ANALYZE public.x (to prevent wraparound)"
    ) == "VACUUM (anti-wraparound)"


# ---------------------------------------------------------------------------
# 3. ⚠️ Counters that may have been lost
# ---------------------------------------------------------------------------

def test_agreeing_counters_say_nothing():
    """Silence is the answer when there is nothing to doubt: a note on every line is a
    note nobody reads."""
    assert tool.counter_note(13_000_000, 13_700_000) == ""


def test_a_reset_collector_is_named_rather_than_averaged():
    """The measured case (2026-08-06): 5,722 live against a real 13,709,607. A ratio
    computed from that denominator read as a confident bloat verdict and was an artefact."""
    note = tool.counter_note(5_722, 13_709_607)
    assert note and "리셋" in note


def test_two_zeros_are_not_read_as_a_reset():
    """A table nothing has analysed yet is a different fact from a lost counter, and the
    two must not print the same sentence."""
    assert "ANALYZE" in tool.counter_note(0, 0)


# ---------------------------------------------------------------------------
# 4. The name is judged before it is interpolated
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    'cell_sources"; DROP TABLE audit_logs; --',
    "cell sources",
    "",
    None,
    "public.cell_sources",
])
def test_a_name_that_is_not_an_identifier_is_refused(name):
    """`ALTER TABLE` and `VACUUM` take no bind parameters, so the name is interpolated --
    which is exactly why it is refused by pattern first."""
    with pytest.raises(ValueError):
        tool.quoted_identifier(name)


def test_a_plain_name_is_quoted():
    assert tool.quoted_identifier("cell_sources") == '"cell_sources"'
    assert tool.set_sql("cell_sources", {"autovacuum_vacuum_cost_limit": "2000"}) == (
        'ALTER TABLE "cell_sources" SET (autovacuum_vacuum_cost_limit = 2000)')


# ---------------------------------------------------------------------------
# 5. One mode at a time
# ---------------------------------------------------------------------------

def test_two_acting_modes_at_once_are_refused(capsys):
    """⛔ 「무엇을 했는지」 HAS TO BE ONE WORD. Two modes in one run make that answer two,
    and the operator reading the log afterwards cannot tell which produced what."""
    assert tool.main(["--apply", "--reset"]) == 2
    assert "하나만" in capsys.readouterr().err
