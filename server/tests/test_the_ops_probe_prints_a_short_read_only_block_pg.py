# -*- coding: utf-8 -*-
"""Lead 11-14 (owner «속도테스트에 운영 수치 반영해»): scripts/ops_probe.py reads this install's PostgreSQL read-only and
prints a block short enough to read off a screen; --full writes the long listing. On sqlite there is nothing to read
(skipped by the pg marker)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import ops_probe                                                    # noqa: E402
from tests.support import isolated_pg                               # noqa: E402

pytestmark = pytest.mark.pg


def test_the_block_is_short_read_only_and_names_each_part(tmp_path):
    url, why = isolated_pg.resolve_url()
    if url is None:
        pytest.skip(why)
    full = tmp_path / "probe.txt"
    block = ops_probe.probe(url, {"no_such_table": {"column_types": {"a": "string"}}}, str(full))
    assert len(block) <= 25, block
    assert "read_only=on" in block[0] and "RAM " in block[0]
    assert all(("%s=" % s) in block[1] for s in ops_probe.SETTINGS)
    assert block[2].startswith("db ") and " | collation " in block[2] and " ctype " in block[2]
    assert any(line.startswith("ix_auto indexes: 0 on 0 of 1 data tables") for line in block)
    assert any(line.startswith("groups GB(index): ") for line in block)
    assert any(line.startswith("leftover columns in 0 tables: none") for line in block)
    assert any(line.startswith("seq read") for line in block)
    text = full.read_text(encoding="utf-8")
    assert text.startswith(block[0]) and len(text.splitlines()) > len(block)
    assert "ix_auto no_such_table: none" in text.splitlines()
