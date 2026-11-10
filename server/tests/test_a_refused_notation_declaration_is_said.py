# -*- coding: utf-8 -*-
"""A notation declaration the read refuses is said - once per read in the log, in the config resolution, and in the
backfill count, all from the one list the read holds (lead 11-10, owner «ㅇㅇ»). Before, only the resolution box knew,
and the backfill counted «0 · Truly none» for a column whose rule was off."""
import pytest

import config_resolve_report
import notation_norm as nn
from admin import retroactive
from test_a_written_column_is_stored_folded import PLAIN, _declare, _write, env  # noqa: F401

KOREAN_REPLACE = ["([0-9]+)월 ([0-9]+)일", "2026-\\1-\\2"]
REFUSED = {PLAIN: {"v": {"write": True, "rules": {"join": "-", "replace": [["wafer", "WF"], KOREAN_REPLACE]}}}}
SAYS = "%s.v: rule 'replace' texts must be printable ASCII without a quote" % PLAIN


def _notation_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Notation] ")]


def test_a_refused_rule_is_logged_once_per_read_and_says_the_whole_rule_is_off(env, tmp_path, monkeypatch, caplog):
    _declare(tmp_path, monkeypatch, REFUSED)
    with caplog.at_level("WARNING"):
        rules = nn.rules_for_column(PLAIN, "v")
        nn.normalized_by_table()
    (line,) = _notation_lines(caplog)
    assert line.startswith("[Notation] " + SAYS) and line.endswith("; the whole rule is left off - not folded"), line
    assert (rules.get("join"), rules.get("replace")) == ("-", None), "the other rule stays; the whole list goes"
    caplog.clear()
    _declare(tmp_path, monkeypatch, REFUSED)                    # read again: said again
    with caplog.at_level("WARNING"):
        nn.normalized_by_table()
    assert len(_notation_lines(caplog)) == 1


def test_the_resolution_box_reads_the_held_list(env, tmp_path, monkeypatch):
    _declare(tmp_path, monkeypatch, REFUSED)
    rejected = [entry for entry in config_resolve_report._resolve_notation()["rejected"]
                if SAYS in str(entry)]
    assert len(rejected) == 1 and nn.refused_declarations()[0]["detail"] in str(rejected[0]), rejected


@pytest.mark.parametrize("declared, absence, says", [
    (REFUSED, retroactive.ABSENCE_CANNOT_POINT, "Declared but refused - " + SAYS),
    ({PLAIN: {"v": {"write": True, "rules": {"join": "-"}}}}, retroactive.ABSENCE_TRULY_NONE, None),
])
def test_the_backfill_count_names_a_refused_declaration_instead_of_none(env, tmp_path, monkeypatch, declared,
                                                                        absence, says):
    _write(env, PLAIN, [{"k": "K-01", "v": "a-b"}])
    _declare(tmp_path, monkeypatch, declared)
    count = retroactive._count_fold_written_notation(env, {"table": PLAIN}, 1000)
    assert (count["affected"], count["absence"]) == (0, absence)
    assert count["detail"].startswith(says) if says else "refused" not in count["detail"], count["detail"]
