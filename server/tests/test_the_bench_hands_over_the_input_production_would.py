# -*- coding: utf-8 -*-
"""S-197 ⓐ. 「이름을 적으면 입력이 온다」 — and it is the input production would hand over.

🔴 THE FAILURE THIS SCORES IS A BENCH THAT ASSEMBLES ITS OWN ENVELOPE. A mapper input is
`{"row_id": …, "data": {col: {"value": x}}}`, and it is easy to build one that looks right and
is not — `as_payloads` itself shipped with the cells at the TOP level first, and the sample
mapper died on `None of [Index(['wafer'])] are in the [columns]`. So the table path goes
through `outbox_expand._data_columns` + `_synthesize_payload`, the two functions the worker
uses when it reads a collapsed event's rows back, and this file asserts BOTH the resulting
columns and the fact that the construction is not respelled here.

🔴 AND THE PARSER SIDE IS ABOUT READ FAILURE BEING NORMAL. Owner: 「파서는 DataFrame 으로
안 읽힐 수도 있어 read dataframe 부터 만들어야 함」. A file production's default reader cannot
open is precisely the file the author opened the notebook for, so `raw_for_parser` returns the
reason AS A VALUE with the bytes and decoded lines still beside it.
"""
import io
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import dev_bench                                                      # noqa: E402

VOID_LINES = os.path.join(script_dir, "samples", "parser", "void_lines")
DOUBLE_X = os.path.join(script_dir, "samples", "mapper", "bench_double_x")


# ---------------------------------------------------------------------------
# ① the input — a sample file
# ---------------------------------------------------------------------------

def test_a_sample_file_arrives_as_the_worker_shaped_frame():
    """⚠️ THE SAMPLE PATH AND THE TABLE PATH MUST PRODUCE ONE SHAPE, or an author develops
    against a file and ships against a table."""
    frame = dev_bench.input_for_mapper(os.path.join(DOUBLE_X, "input.csv"))
    assert list(frame.columns)[0] == "row_id", list(frame.columns)
    assert "x" in frame.columns, list(frame.columns)
    assert len(frame) > 0


def test_a_name_that_is_neither_a_file_nor_a_declared_table_is_refused_by_name():
    """⛔ 「없다」 HAS TO SAY WHAT THERE IS. A bare KeyError sends the author looking for a
    typo in their own cell when the answer is 「that table is not declared here」."""
    with pytest.raises(LookupError) as caught:
        dev_bench.input_for_mapper("s197_no_such_table_anywhere")
    assert "s197_no_such_table_anywhere" in str(caught.value)
    assert "declared:" in str(caught.value)


def test_a_table_input_is_built_by_the_workers_own_two_functions(db_session, monkeypatch):
    """🔴 THE COLUMN GATE (판정 order: 「이 표에서 준 df 의 컬럼 = 워커 payload 컬럼」).

    ⚠️ THE READ-ONLY SESSION IS STOOD IN FOR, DELIBERATELY. What is scored here is the
    PAYLOAD CONSTRUCTION; that the connection PostgreSQL hands back refuses writes is
    `db_safety`'s contract and `try_mapper`'s test, and re-proving it here would be a second
    gate able to disagree with the first. On sqlite the real one yields `None`.
    """
    import outbox_expand
    from database.models import DYNAMIC_TABLES

    monkeypatch.setattr(dev_bench, "_readonly_session",
                        lambda: (db_session, lambda: None))

    frame = dev_bench.input_for_mapper("raw_table_1", rows=3)

    model = DYNAMIC_TABLES["raw_table_1"]
    expected = ["row_id"] + list(outbox_expand._data_columns(model))
    assert list(frame.columns) == expected, list(frame.columns)
    assert len(frame) == 3, "the window is honoured"
    assert frame["EQP_ID"].iloc[0].startswith("EQP_")


def test_the_window_can_be_named_rows_or_ids(db_session, monkeypatch):
    monkeypatch.setattr(dev_bench, "_readonly_session",
                        lambda: (db_session, lambda: None))
    everything = dev_bench.input_for_mapper("raw_table_1", rows=10)
    picked = list(everything["row_id"])[:2]

    narrowed = dev_bench.input_for_mapper("raw_table_1", row_ids=picked)
    assert sorted(narrowed["row_id"]) == sorted(picked)


def test_the_table_path_does_not_respell_the_envelope():
    """🔴 SCORED ON THE SOURCE, because a second construction that agrees TODAY is exactly
    the defect — and this one has already been got wrong once, in `as_payloads`."""
    import inspect

    body = inspect.getsource(dev_bench.input_for_mapper)
    for required in ("_data_columns", "_synthesize_payload", "payloads_to_df"):
        assert required in body, required
    for rebuilt in ('{"value"', '"data":', "is_overwrite"):
        assert rebuilt not in body, (
            "the bench builds its own payload envelope again: %s" % rebuilt)


# ---------------------------------------------------------------------------
# ① the input — a raw file for a parser
# ---------------------------------------------------------------------------

def test_a_readable_file_comes_back_with_productions_frame():
    raw = dev_bench.raw_for_parser(os.path.join(DOUBLE_X, "input.csv"))
    assert raw["read_refusal"] is None
    assert raw["df"] is not None and len(raw["df"]) > 0
    assert raw["size_bytes"] > 0
    assert raw["encoding"] in dev_bench.ENCODING_LADDER
    assert raw["lines"], "the decoded head is there even when the frame is"


def test_an_unreadable_file_says_so_as_a_VALUE_and_still_shows_the_bytes(tmp_path):
    """🔴 THE WHOLE REASON THIS FUNCTION EXISTS. Owner: a format production cannot read is
    what cell ② is for — so cell ① must not raise on it.

    ⚠️ AND THE BYTES MUST SURVIVE THE FAILURE. A refusal with no `lines` would leave the
    author writing a read override against a file they cannot see.
    """
    # An instrument dump: a preamble line, then rows that do not agree on how many fields
    # they have. `pd.read_csv` raises `ParserError` on it — measured, not supposed.
    target = tmp_path / "instrument.dat"
    target.write_text("INSTRUMENT DUMP v2\nsite,x,y\n1,2,3,4,5,6\n7,8\n", encoding="utf-8")

    raw = dev_bench.raw_for_parser(str(target))

    assert raw["df"] is None
    assert raw["read_refusal"] and raw["read_refusal"].startswith(dev_bench.UNREADABLE)
    assert raw["size_bytes"] == target.stat().st_size
    assert raw["lines"] and raw["lines"][0].startswith("INSTRUMENT")


def test_a_file_that_is_not_utf8_still_decodes_for_display(tmp_path):
    """⚠️ DISPLAY ONLY. Production has no detection step, so this ladder must never be
    presented as what the parser will get — it is there so the author can SEE the file."""
    target = tmp_path / "cp949.csv"
    target.write_bytes("이름,수량\n볼트,3\n".encode("cp949"))

    raw = dev_bench.raw_for_parser(str(target))
    assert raw["encoding"] == "cp949"
    assert raw["lines"][0] == "이름,수량"


# ---------------------------------------------------------------------------
# 🔴 the survey, and the three stages
# ---------------------------------------------------------------------------

def test_claimers_reports_every_parser_and_claims_none():
    """🔴 `try_parser` ANSWERS 「who gets it」; THIS ANSWERS 「who wants it」 — and the second
    is the question that finds two parsers fighting over one file."""
    survey = dev_bench.claimers(os.path.join(VOID_LINES, "input.txt"),
                                scripts_path=VOID_LINES)
    assert [r["class"] for r in survey["rows"]] == ["BenchVoidParser"]
    assert survey["winners"] and survey["winners"][0]["match"] is True
    assert survey["load_errors"] == {}


def test_a_parser_that_does_not_want_the_file_is_listed_rather_than_dropped():
    """⚠️ 「didn't claim」 AND 「wasn't there」 MUST NOT LOOK THE SAME — an author debugging a
    `match()` needs to see the class that answered no."""
    survey = dev_bench.claimers(os.path.join(VOID_LINES, "expected.tsv"),
                                scripts_path=VOID_LINES)
    assert [r["class"] for r in survey["rows"]] == ["BenchVoidParser"]
    assert survey["winners"] == []
    assert survey["rows"][0]["match"] is False


def test_an_absent_workspace_is_refused_by_path(tmp_path):
    with pytest.raises(FileNotFoundError) as caught:
        dev_bench.claimers("x.txt", scripts_path=str(tmp_path / "nope"))
    assert "nope" in str(caught.value)


def test_run_stages_keeps_the_three_apart():
    """🔴 `parse()` ANSWERS ONLY 「did it work」. The author needs to know WHICH stage broke
    the assumption, and the sample parser drops columns in stage two — so the three shapes
    here are genuinely different and a collapsed implementation could not fake them."""
    survey = dev_bench.claimers(os.path.join(VOID_LINES, "input.txt"),
                                scripts_path=VOID_LINES)
    cls = survey["winners"][0]["cls"]

    staged = dev_bench.run_stages(cls, os.path.join(VOID_LINES, "input.txt"))

    assert list(staged.processed.columns) == ["wafer", "x", "y", "kind"]
    assert len(staged.raw.columns) >= len(staged.processed.columns)
    assert len(staged.records) == len(staged.processed)
    assert isinstance(staged.records[0], dict)


def test_run_stages_attaches_what_the_watcher_attaches():
    """⚠️ A PARSER THAT READS `rel_path` MUST NOT BEHAVE DIFFERENTLY HERE. The watcher sets
    these before `parse()`; a bench that skipped them would be a bench whose green is about
    a code path production does not take."""
    survey = dev_bench.claimers(os.path.join(VOID_LINES, "input.txt"),
                                scripts_path=VOID_LINES)
    staged = dev_bench.run_stages(survey["winners"][0]["cls"],
                                  os.path.join(VOID_LINES, "input.txt"),
                                  source_root="/somewhere")
    assert staged.parser.rel_path == "input.txt"
    assert staged.parser.source_root == "/somewhere"


# ---------------------------------------------------------------------------
# 🔴 the two things one file cannot answer (판정 308)
# ---------------------------------------------------------------------------

def test_the_sweep_names_the_files_nobody_claims(tmp_path):
    """🔴 TOO NARROW IS INVISIBLE FROM ONE FILE. A parser whose `match()` misses its own
    input leaks it to the std parser, and nothing anywhere says so."""
    for name in ("input.txt", "stranger.log"):
        (tmp_path / name).write_text("x\n", encoding="utf-8")

    swept = dev_bench.sweep_claims(str(tmp_path), scripts_path=VOID_LINES)

    by_file = {os.path.basename(f["file"]): f["claimed_by"] for f in swept["files"]}
    assert by_file == {"input.txt": ["BenchVoidParser"], "stranger.log": []}
    assert [os.path.basename(f) for f in swept["unclaimed"]] == ["stranger.log"]


def test_the_sweep_names_a_file_two_parsers_both_want(tmp_path):
    """🔴 TOO WIDE IS WORSE, AND LOOKS IDENTICAL. Production takes the first yes, so the
    second parser is simply never reached — no error, no log, just rows under the wrong
    name."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "greedy.py").write_text(
        "from pipeline_base import BasePipelineParser\n"
        "class Greedy(BasePipelineParser):\n"
        "    @classmethod\n"
        "    def match(cls, file_path):\n"
        "        return True\n", encoding="utf-8")
    (scripts / "narrow.py").write_text(
        "import os\n"
        "from pipeline_base import BasePipelineParser\n"
        "class Narrow(BasePipelineParser):\n"
        "    @classmethod\n"
        "    def match(cls, file_path):\n"
        "        return os.path.basename(file_path) == 'mine.csv'\n", encoding="utf-8")

    raws = tmp_path / "raws"
    raws.mkdir()
    (raws / "mine.csv").write_text("a\n", encoding="utf-8")
    (raws / "theirs.csv").write_text("a\n", encoding="utf-8")

    swept = dev_bench.sweep_claims(str(raws), scripts_path=str(scripts))

    contested = [os.path.basename(f["file"]) for f in swept["contested"]]
    assert contested == ["mine.csv"]
    assert swept["unclaimed"] == [], "the greedy one takes everything, so nothing is free"


def test_a_match_that_throws_is_not_a_match_that_said_no(tmp_path):
    """⚠️ PRODUCTION TREATS A THROW AS A DECLINE, and it is right to. But the author has to
    see WHICH it was — a `match()` that raises on every file is a parser that never runs."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "angry.py").write_text(
        "from pipeline_base import BasePipelineParser\n"
        "class Angry(BasePipelineParser):\n"
        "    @classmethod\n"
        "    def match(cls, file_path):\n"
        "        raise ValueError('nope')\n", encoding="utf-8")
    raws = tmp_path / "raws"
    raws.mkdir()
    (raws / "a.csv").write_text("a\n", encoding="utf-8")

    swept = dev_bench.sweep_claims(str(raws), scripts_path=str(scripts))
    assert swept["files"][0]["claimed_by"] == ["Angry!ValueError"]


def test_an_empty_folder_is_an_answer_not_a_crash(tmp_path):
    swept = dev_bench.sweep_claims(str(tmp_path), scripts_path=VOID_LINES)
    assert swept == {"files": [], "unclaimed": [], "contested": [], "load_errors": {}}


def test_output_columns_are_judged_by_the_upserts_own_predicate(db_session):
    """🔴 `table.c.get(key) is None` IS `crud`'s `unknown_column` DECLINE, verbatim. One key
    the table does not have and the fast path declines for the WHOLE batch."""
    checked = dev_bench.check_output_columns(
        [{"EQP_ID": "E1", "NOT_A_COLUMN": 1}], "raw_table_1")

    assert checked["unknown"] == ["NOT_A_COLUMN"]
    assert "EQP_ID" in checked["declared"]
    assert set(checked["produced"]) == {"EQP_ID", "NOT_A_COLUMN"}


def test_the_framework_columns_are_not_counted_as_never_filled(db_session):
    """⚠️ 「never filled」 IS A QUESTION, NOT A FAULT — and it would be a useless one if it
    listed `row_id` and `created_at` every time. The exclusion is `models.FRAMEWORK_COLUMNS`,
    production's own name for them, rather than a list spelled in the bench."""
    from database import models

    checked = dev_bench.check_output_columns([{"EQP_ID": "E1"}], "raw_table_1")
    assert not (set(checked["never_filled"]) & set(models.FRAMEWORK_COLUMNS))


def test_a_table_that_is_not_declared_is_refused_by_name(db_session):
    with pytest.raises(LookupError) as caught:
        dev_bench.check_output_columns([{"a": 1}], "s197_no_such_table")
    assert "s197_no_such_table" in str(caught.value)


def test_neither_new_function_re_implements_what_it_asks():
    """🔴 SCORED ON THE SOURCE. The sweep must ask `match()` and the column check must ask
    `table.c.get` — a bench that compared filename patterns itself, or held its own list of
    system columns, would be right until the day production changed and it did not."""
    import inspect

    sweep = inspect.getsource(dev_bench.sweep_claims)
    assert ".match(" in sweep and "claimers(" in sweep
    for rebuilt in ("fnmatch", "endswith(", "MATCH_PATTERN"):
        assert rebuilt not in sweep, rebuilt

    check = inspect.getsource(dev_bench.check_output_columns)
    assert "table.c.get(" in check and "FRAMEWORK_COLUMNS" in check
    assert "created_at" not in check, "the system columns are spelled here again"


def test_the_stages_are_productions_own_methods():
    """🔴 SCORED ON THE SOURCE. A bench that read the file itself would be green on a parser
    whose read override production would actually have used."""
    import inspect

    body = inspect.getsource(dev_bench.run_stages)
    for required in ("_read_file_to_dataframe", "process_dataframe", "clean_for_postgres"):
        assert required in body, required
    for rebuilt in ("read_csv", "read_excel", "to_dict("):
        assert rebuilt not in body, rebuilt
