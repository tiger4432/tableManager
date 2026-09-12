# -*- coding: utf-8 -*-
"""S-192 shell ②. A sample folder IS a test — `input.*` in, `expected.tsv` out.

Owner 2026-09-12: 「체인 맵퍼·인제션 파서 개발용 시험 환경 — 샘플 인풋과 핵심 로직 아웃풋만」.

🔴 DISCOVERY, NOT ENUMERATION. `tests/samples/<kind>/<name>/` is found by walking, so an
author adds a case by adding a FOLDER — no test file to edit, nothing to remember. A list
here would be a second place to keep in step, and the one that gets forgotten.

🔴 AND IT GOES THROUGH `run_sample_folder`, THE SAME FUNCTION THE CLI CALLS. Two shells that
each assembled the call would drift, and then 「it works from the command line」 and 「the test
passes」 would be different facts about one mapper — which is the defect this repository has
paid for under 「같은 기능인데 두 경로가 있어서도 안 됨」.
"""
import io
import os
import subprocess
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import dev_bench                                                      # noqa: E402

SAMPLES = os.path.join(script_dir, "samples")
FOLDERS = dev_bench.sample_folders(SAMPLES)


def _label(folder):
    return "%s/%s" % (os.path.basename(os.path.dirname(folder)),
                      os.path.basename(folder))


def test_the_repository_ships_at_least_one_sample():
    """⛔ WITHOUT THIS, DELETING THE SAMPLES WOULD MAKE THIS FILE PASS WITH NOTHING TO RUN —
    a parametrised test over an empty list is green and silent."""
    assert FOLDERS, "no sample folder under %s" % SAMPLES


@pytest.mark.parametrize("folder", FOLDERS, ids=[_label(f) for f in FOLDERS])
def test_a_sample_folder_produces_its_expected_tsv(folder):
    """🔴 THE GATE. Change one cell of `expected.tsv` and this goes red — that is the whole
    contract an author is offered, and it is why the expectation is a FILE rather than an
    assertion somebody has to write."""
    expected_file = dev_bench.expected_path(folder)
    assert os.path.exists(expected_file), (
        "%s has an input but no expected.tsv — write one with "
        "`python scripts/try_core.py folder %s`" % (_label(folder), folder))

    result = dev_bench.run_sample_folder(folder)
    assert result["refusal"] is None, (_label(folder), result["refusal"])

    produced = dev_bench.rows_to_tsv(result["rows"])
    expected = io.open(expected_file, encoding="utf-8").read()
    # ⚠️ Compared with line endings normalised, because this repository checks out CRLF and a
    # gate that fails on the newline would fail on every fresh clone while the rows agree.
    assert produced.replace("\r\n", "\n") == expected.replace("\r\n", "\n"), _label(folder)


@pytest.mark.parametrize("folder", FOLDERS, ids=[_label(f) for f in FOLDERS])
def test_the_columns_and_the_rows_are_both_pinned(folder):
    """⚠️ A TSV COMPARISON ALREADY COVERS BOTH, and this says so out loud: the header line is
    the column SET and its order, and the body is the rows. Neither half can move without the
    file changing, which is what makes 「비교는 컬럼 집합 + 행 정렬 뒤 동일」 true here."""
    expected = io.open(dev_bench.expected_path(folder), encoding="utf-8").read()
    lines = [l for l in expected.replace("\r\n", "\n").split("\n") if l]
    assert lines, "an empty expectation proves nothing"
    header = lines[0].split("\t")
    assert len(header) == len(set(header)), ("a column is named twice", header)
    for line in lines[1:]:
        assert len(line.split("\t")) == len(header), (line, header)


def test_a_cell_reads_the_way_the_product_reads_it():
    """🔴 THE BENCH AND THE WIRE MUST SPELL A CELL THE SAME, or an author matches an
    expectation the product never produces.

    ⛔ THE SAMPLE FOLDER CANNOT PROVE THIS. Its cells are all plain scalars, so `str(value)`
    and `wire_text(value)` agree on every one of them — I mutated `rows_to_tsv` to drop
    `wire_text` and the folder test stayed GREEN. A fixture both rules agree on decides
    nothing, so the discriminator is asserted here directly: a dict cell.
    """
    from utils.wire_format import wire_text

    payload = {"wafer": "W7", "한글": "값"}
    produced = dev_bench.rows_to_tsv([{"subject_keys": payload}])
    assert produced.split("\n")[1] == wire_text(payload)
    assert "'" not in produced, "a python repr would quote with apostrophes"


def test_the_cli_and_the_fixture_print_the_same_tsv():
    """🔴 THE TWO SHELLS ARE SCORED AGAINST EACH OTHER, not each against my memory of the
    other. The CLI is run as a SUBPROCESS on purpose — importing `main()` would share this
    process's already-imported modules and could pass while the command line does not."""
    folder = FOLDERS[0]
    completed = subprocess.run(
        [sys.executable, os.path.join(server_dir, "scripts", "try_core.py"),
         "folder", folder],
        cwd=server_dir, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    produced = dev_bench.rows_to_tsv(dev_bench.run_sample_folder(folder)["rows"])
    assert completed.stdout.replace("\r\n", "\n") == produced.replace("\r\n", "\n")


def test_a_refusal_is_a_named_answer_rather_than_an_exception(tmp_path):
    """⚠️ 「nobody claimed this file」 IS AN ANSWER. `directory_watcher` already separates that
    from a failure, and an author meets it constantly while writing `match()` — so it arrives
    as a sentence naming what was offered, not as a traceback."""
    orphan = tmp_path / "nothing_claims_me.txt"
    orphan.write_text("a,b\n1,2\n", encoding="utf-8")
    result = dev_bench.try_parser(str(orphan), scripts_path=str(tmp_path))
    assert result["rows"] == [] and result["who"] is None
    assert "no parser claimed this file" in result["refusal"]
