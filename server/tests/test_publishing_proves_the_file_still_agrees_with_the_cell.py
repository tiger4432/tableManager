# -*- coding: utf-8 -*-
"""S-197 ⓑ. 「되면 발행 셀이 함수 파일을 만든다」 — and the file has to prove it still agrees.

🔴 WHAT PUBLISHING ACTUALLY RISKS IS DRIFT AT THE MOMENT OF TRANSCRIPTION. `inspect.getsource`
gives the cell as it was last EXECUTED, and copy-paste gives whatever the hand copied; both
can differ from the cell on the screen, and the file then runs in a folder production watches
producing something nobody looked at. So `publish_mapper`/`publish_parser` read the file back,
run it on the same input, and DELETE it when the answer differs.

🔴 AND THE PARSER CHECK GOES THROUGH THE CLAIM. A published parser that is correct but never
reached — because another class in the same folder claims the file first — is a failure that
calling the class directly cannot see. Production takes the FIRST yes.
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

DOUBLE_X = os.path.join(script_dir, "samples", "mapper", "bench_double_x")
VOID_LINES = os.path.join(script_dir, "samples", "parser", "void_lines")

DOUBLE_BODY = "    out = df.copy()\n    out['x'] = out['x'].astype(float) * 2\n    return out"


@pytest.fixture(autouse=True)
def _no_name_left_claimed():
    """⚠️ `MAPPER_REGISTRY` IS PROCESS-WIDE. A name left in it after a test is the same class
    of leak as a dynamic model left in `Base.metadata` (S-191), and it would make the NEXT
    publish of that name refuse for the wrong reason."""
    import mapper_sdk

    before = set(mapper_sdk.MAPPER_REGISTRY)
    yield
    for name in set(mapper_sdk.MAPPER_REGISTRY) - before:
        mapper_sdk.MAPPER_REGISTRY.pop(name, None)
        getattr(mapper_sdk, "MAPPER_PARAMS", {}).pop(name, None)


def _frame():
    return dev_bench.input_for_mapper(os.path.join(DOUBLE_X, "input.csv"))


def _doubled(frame):
    out = frame.copy()
    out["x"] = out["x"].astype(float) * 2
    return out


# ---------------------------------------------------------------------------
# the mapper
# ---------------------------------------------------------------------------

def test_a_cell_that_agrees_becomes_a_decorated_mapper_file(tmp_path):
    frame = _frame()
    published = dev_bench.publish_mapper(
        "s197_doubler", ("factor",), DOUBLE_BODY,
        frame=frame, expected=_doubled(frame), directory=str(tmp_path))

    assert published["path"] == str(tmp_path / "s197_doubler.py")
    source = io.open(published["path"], encoding="utf-8").read()
    assert "@mapper(params=('factor',))" in source, source
    assert "def s197_doubler(df, db):" in source
    assert "out['x'].astype(float) * 2" in source, "the body is the cell's own bytes"


def test_the_published_name_is_registered_so_the_worker_can_find_it(tmp_path):
    """🔴 A FILE IS NOT A MAPPER. `chain_rules.json` names a mapper, and the decorator is
    what puts that name where the worker resolves it — so publishing has to traverse the
    decorator, not merely write text that contains it."""
    import mapper_sdk

    frame = _frame()
    dev_bench.publish_mapper("s197_registered", (), DOUBLE_BODY,
                             frame=frame, expected=_doubled(frame),
                             directory=str(tmp_path))
    assert "s197_registered" in mapper_sdk.MAPPER_REGISTRY


def test_a_body_that_disagrees_is_refused_AND_the_file_is_gone(tmp_path):
    """🔴 THE GATE THE WHOLE PIECE EXISTS FOR. A published file that does not match the cell
    is worse than no file — it claims real inputs in a folder production reads."""
    frame = _frame()
    with pytest.raises(dev_bench.PublishRefused) as caught:
        dev_bench.publish_mapper(
            "s197_drifted", (), DOUBLE_BODY,
            frame=frame,
            expected=frame,                      # the cell "produced" the input unchanged
            directory=str(tmp_path))

    assert "s197_drifted" in str(caught.value)
    assert not (tmp_path / "s197_drifted.py").exists(), "a refused publish leaves nothing"


def test_a_body_that_raises_is_refused_and_leaves_nothing(tmp_path):
    frame = _frame()
    with pytest.raises(dev_bench.PublishRefused) as caught:
        dev_bench.publish_mapper("s197_raiser", (), "    return df['nope_not_a_column']",
                                 frame=frame, expected=frame, directory=str(tmp_path))
    assert "raised" in str(caught.value)
    assert not (tmp_path / "s197_raiser.py").exists()


def test_an_existing_file_is_never_overwritten(tmp_path):
    """⛔ NO `overwrite=` ARGUMENT. Somebody is running that file; replacing it from a
    notebook cell is a deploy nobody asked for."""
    (tmp_path / "s197_taken.py").write_text("# somebody's parser\n", encoding="utf-8")
    frame = _frame()
    with pytest.raises(dev_bench.PublishRefused) as caught:
        dev_bench.publish_mapper("s197_taken", (), DOUBLE_BODY, frame=frame,
                                 expected=_doubled(frame), directory=str(tmp_path))
    assert "already exists" in str(caught.value)
    assert (tmp_path / "s197_taken.py").read_text(encoding="utf-8") == "# somebody's parser\n"


def test_a_name_that_is_not_a_module_name_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(dev_bench.PublishRefused):
        dev_bench.publish_mapper("not a name", (), DOUBLE_BODY, frame=_frame(),
                                 expected=_frame(), directory=str(tmp_path))
    assert os.listdir(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------

READ_BODY = "        return pd.read_csv(file_path, sep='|')"
PROCESS_BODY = "        return df[['wafer', 'x']]"


@pytest.fixture()
def piped(tmp_path):
    """A file production's default reader CANNOT open — which is why `read_df` exists."""
    target = tmp_path / "instrument.csv"
    target.write_text("wafer|x|y\nW1|1|2\nW2|3|4\n", encoding="utf-8")
    return target


def test_both_free_form_cells_land_in_the_published_parser(tmp_path, piped):
    """🔴 THE READ OVERRIDE IS PUBLISHED TOO (owner's correction). A parser workbench that
    only published `process_dataframe` would leave the author's format unreadable in
    production — the exact case the notebook was opened for."""
    import pandas as pd

    scripts = tmp_path / "scripts"
    expected = pd.read_csv(str(piped), sep="|")[["wafer", "x"]]

    published = dev_bench.publish_parser(
        "s197_piped", READ_BODY, PROCESS_BODY, file=str(piped), expected=expected,
        scripts_path=str(scripts))

    source = io.open(published["path"], encoding="utf-8").read()
    assert "def _read_file_to_dataframe" in source and "sep='|'" in source
    assert "def process_dataframe" in source and "['wafer', 'x']" in source
    assert "class S197Piped(BasePipelineParser):" in source
    assert published["who"].startswith("s197_piped.py")
    assert [r["wafer"] for r in published["rows"]] == ["W1", "W2"]


def test_the_draft_match_claims_by_extension_and_says_it_is_a_draft(tmp_path, piped):
    import pandas as pd

    scripts = tmp_path / "scripts"
    expected = pd.read_csv(str(piped), sep="|")[["wafer", "x"]]
    published = dev_bench.publish_parser(
        "s197_draft_match", READ_BODY, PROCESS_BODY, file=str(piped), expected=expected,
        scripts_path=str(scripts))

    source = io.open(published["path"], encoding="utf-8").read()
    assert "MATCH_PATTERN = '*.csv'" in source, source
    assert "DRAFT" in source, "the operator must be told to narrow it"


def test_a_parser_someone_else_claims_first_is_refused_by_that_name(tmp_path, piped):
    """🔴 THE FAILURE CALLING THE CLASS DIRECTLY CANNOT SEE. Production takes the FIRST class
    that says yes, so a correct parser behind a greedy one never runs — and nothing about it
    looks broken."""
    import pandas as pd

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "aaa_greedy.py").write_text(
        "from pipeline_base import BasePipelineParser\n"
        "class AaaGreedy(BasePipelineParser):\n"
        "    @classmethod\n"
        "    def match(cls, file_path):\n"
        "        return True\n", encoding="utf-8")

    expected = pd.read_csv(str(piped), sep="|")[["wafer", "x"]]
    with pytest.raises(dev_bench.PublishRefused) as caught:
        dev_bench.publish_parser("s197_behind", READ_BODY, PROCESS_BODY, file=str(piped),
                                 expected=expected, scripts_path=str(scripts))

    assert "AaaGreedy" in str(caught.value)
    assert not (scripts / "s197_behind.py").exists(), "a refused publish leaves nothing"


def test_a_parser_that_disagrees_with_its_cells_is_refused_and_removed(tmp_path, piped):
    import pandas as pd

    scripts = tmp_path / "scripts"
    wrong = pd.read_csv(str(piped), sep="|")[["wafer"]]      # the cell "produced" one column
    with pytest.raises(dev_bench.PublishRefused) as caught:
        dev_bench.publish_parser("s197_mismatch", READ_BODY, PROCESS_BODY, file=str(piped),
                                 expected=wrong, scripts_path=str(scripts))
    assert "S197Mismatch" in str(caught.value)
    assert not (scripts / "s197_mismatch.py").exists()


# ---------------------------------------------------------------------------
# 🔴 one place moves a cell body into a file
# ---------------------------------------------------------------------------

def _free_form(df, db):
    """A docstring the published file must not inherit."""
    out = df.copy()
    out["x"] = 1
    return out


def test_cell_body_hands_back_the_body_at_column_zero():
    """🔴 SO THE AUTHOR NEVER COPIES. Copying is where 「what I ran」 and 「what I shipped」
    come apart, and one seat for the move is what the owner asked for."""
    body = dev_bench.cell_body(_free_form)
    assert body.splitlines()[0].startswith('"""'), "the whole body comes across"
    assert "out = df.copy()" in body
    assert not body.startswith(" "), "column zero — the template decides the indent"
    assert "def _free_form" not in body


def test_cell_body_refuses_something_that_is_not_a_cell_function():
    with pytest.raises(ValueError):
        dev_bench.cell_body(len)


def test_a_body_taken_by_cell_body_publishes_and_agrees(tmp_path):
    """⚠️ THE ROUND TRIP, END TO END. `cell_body` is allowed to be STALE — it reads the cell
    as last executed — and the publisher's comparison is what makes that safe. Here they are
    exercised together, which is the only configuration an author ever uses."""
    frame = _frame()
    published = dev_bench.publish_mapper(
        "s197_round_trip", (), dev_bench.cell_body(_free_form),
        frame=frame, expected=_free_form(frame, None), directory=str(tmp_path))
    assert os.path.exists(published["path"])

def test_the_comparison_is_not_optional_in_either_publisher():
    """⛔ SCORED ON THE SOURCE. A publisher that writes the file and returns is a publisher
    that ships drift; the check is what makes 「it worked in the notebook」 mean anything, so
    it must not be reachable to skip."""
    import inspect

    for fn, runner in ((dev_bench.publish_mapper, "rows_to_tsv"),
                       (dev_bench.publish_parser, "try_parser(")):
        body = inspect.getsource(fn)
        assert runner in body, (fn.__name__, runner)
        assert "PublishRefused" in body and "_discard(" in body, fn.__name__


def test_both_publishers_refuse_an_existing_file_through_one_function():
    """⚠️ ONE REFUSAL, NOT TWO. Two overwrite checks would be two chances to differ, and the
    one that got it wrong would be the one nobody read."""
    import inspect

    for fn in (dev_bench.publish_mapper, dev_bench.publish_parser):
        body = inspect.getsource(fn)
        assert "_publish_target(" in body, fn.__name__
        assert "os.path.exists" not in body, (
            "%s checks for the existing file itself" % fn.__name__)
