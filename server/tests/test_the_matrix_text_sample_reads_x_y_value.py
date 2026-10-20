# -*- coding: utf-8 -*-
"""Owner 10-20 «와처가 자동으로 읽게» (lead): the shipped sample plugin `parsers/matrix_text_parser.py.sample` - a matrix
text file (first line x values, then a y value and its values a line) -> one {x, y, value} row a non-blank value. The
whole sample file is loaded as the module it becomes once copied to a table's scripts/."""
import importlib.machinery
import importlib.util
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PARSERS = os.path.join(SERVER_DIR, "parsers")
if PARSERS not in sys.path:
    sys.path.insert(0, PARSERS)


@pytest.fixture(name="sample")
def fixture_sample():
    path = os.path.join(PARSERS, "matrix_text_parser.py.sample")
    loader = importlib.machinery.SourceFileLoader("matrix_text_parser", path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("matrix_text_parser", loader))
    loader.exec_module(module)
    return module


def _read(sample, tmp_path, text, name="m.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return [(r["x"], r["y"], r["value"]) for r in sample.MatrixTextParser().parse(str(path))]


def test_a_tab_file_with_a_blank_corner_keeps_a_blank_cell_in_its_place(sample, tmp_path):
    rows = _read(sample, tmp_path, "\t1\t2\t3\nA\t10\t\t30\nB\t40\t50\t60\n")
    assert rows == [("1", "A", "10"), ("3", "A", "30"), ("1", "B", "40"), ("2", "B", "50"), ("3", "B", "60")]


def test_a_first_line_shorter_than_the_data_lines_has_no_corner(sample, tmp_path):
    assert _read(sample, tmp_path, "1 2 3\nA 10 20 30\n") == [("1", "A", "10"), ("2", "A", "20"), ("3", "A", "30")]


def test_a_written_corner_as_long_as_the_data_lines_is_dropped(sample, tmp_path):
    assert _read(sample, tmp_path, "y/x,1,2\nA,5,6\n") == [("1", "A", "5"), ("2", "A", "6")]


def test_more_values_than_x_values_refuses_the_file_by_line(sample, tmp_path):
    with pytest.raises(ValueError, match="line 3: 3 values for 2 x values"):
        _read(sample, tmp_path, "\t1\t2\nA\t5\t6\nB\t7\t8\t9\n")


def test_it_takes_the_pattern_s_names_only(sample):
    take = sample.MatrixTextParser.match
    assert take("C:/w/raws/m.TXT") and take("C:/w/raws/user(kim)_m_abcdef12.txt")
    assert not take("C:/w/raws/m.csv")


def test_the_output_names_are_the_constant_s(sample, tmp_path, monkeypatch):
    monkeypatch.setattr(sample, "COLUMNS", ("col", "row", "v"))
    path = tmp_path / "m.txt"
    path.write_text("\t1\nA\t5\n", encoding="utf-8")
    assert sample.MatrixTextParser().parse(str(path)) == [{"col": "1", "row": "A", "v": "5"}]
