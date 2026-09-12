# -*- coding: utf-8 -*-
"""S-197 ⓑ. The two workbench notebooks call production, and re-implement nothing.

🔴 TEXT IS THE SUBJECT HERE, NOT A PROXY FOR BEHAVIOUR (CLAUDE.md, 「텍스트가 «대상»인
하니스」). The property being scored IS 「what do these cells import and spell」, so a cell that
changes shape SHOULD turn this red — that is the feature, not the defect the cut-and-run
prohibition is about.

⚠️ AND EXECUTION IS NOT TESTED, BECAUSE IT CANNOT BE HERE. `nbformat`/`nbclient`/`nbconvert`
are ABSENT from this environment — measured, not assumed; `ipykernel` and `jupyter_client` are
present, which is why the notebooks run in the VS Code editor and not from a server. The
execution test is skipped BY NAME rather than quietly omitted, so installing those packages
turns it on rather than leaving a hole nobody remembers.

🔴 THE FREE-FORM CELLS ARE THE EXCEPTION AND THEY ARE TAGGED. 「자유폼」 is the product: the
author's `read_df` / `process` / `build` bodies are theirs, and wrapping them would be the
defect. So the boundary is declared in cell metadata rather than guessed from content — a
guess would either forbid the author's `pd.read_csv` or excuse a bench cell's.
"""
import io
import json
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

NOTEBOOKS = os.path.join(server_dir, "notebooks")
NAMES = ("mapper_workbench.ipynb", "parser_workbench.ipynb")

#: Everything a BENCH cell is allowed to import. The bench functions and the standard library
#: it takes to name a path — everything else belongs behind `dev_bench`.
ALLOWED_IMPORTS = {"dev_bench", "pandas", "sys", "json", "shutil", "pathlib",
                   "parsers", "parsers.directory_watcher"}

#: Spellings that mean a cell stopped calling production and started being it.
REIMPLEMENTED = ("read_csv", "read_excel", "payloads_to_df", '{"value"',
                 "scan_workspace_pipeline_parsers", "clean_for_postgres",
                 "_read_file_to_dataframe")


def _load(name):
    with io.open(os.path.join(NOTEBOOKS, name), encoding="utf-8") as handle:
        return json.load(handle)


def _code_cells(notebook):
    return [c for c in notebook["cells"] if c["cell_type"] == "code"]


def _text(cell):
    return "".join(cell["source"])


def _is_freeform(cell):
    return "freeform" in ((cell.get("metadata") or {}).get("tags") or [])


def _imports(text):
    found = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            found.add(stripped[len("import "):].split()[0].split(",")[0])
        elif stripped.startswith("from "):
            found.add(stripped[len("from "):].split()[0])
    return found


# ---------------------------------------------------------------------------
# they exist, and they are notebooks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_the_notebook_is_in_the_repository_and_parses(name):
    """⛔ THE POINT OF MOVING IT HERE. The one that existed was UNTRACKED, so it was one
    machine's tool — a workbench nobody else has is a workbench that drifts from the code it
    claims to exercise."""
    notebook = _load(name)
    assert notebook["cells"], name
    assert notebook["metadata"]["kernelspec"]["name"] == "python3"


@pytest.mark.parametrize("name", NAMES)
def test_every_code_cell_compiles(name):
    """⚠️ WITHOUT nbclient THIS IS THE STRONGEST EXECUTION EVIDENCE AVAILABLE, and it is
    honestly weaker than running them: it catches a broken cell, not a wrong one."""
    for index, cell in enumerate(_code_cells(_load(name))):
        source = _text(cell)
        for magic in ("%load_ext autoreload", "%autoreload 2"):
            source = source.replace(magic, "pass")
        compile(source, "<%s cell %d>" % (name, index), "exec")


@pytest.mark.parametrize("name", NAMES)
def test_the_first_cell_says_which_interpreter_it_is_on(name):
    """🔴 THE BARE-PYTHON ACCIDENT, PREVENTED AT THE TOP OF THE SCREEN. A kernel on the wrong
    interpreter has no `psycopg2`, so the DB cells fail in a way that reads as 「the database
    is down」. Printing `sys.executable` costs one line and answers it."""
    first = _code_cells(_load(name))[0]
    assert "sys.executable" in _text(first), name


@pytest.mark.parametrize("name", NAMES)
def test_no_cell_carries_this_boxs_absolute_path(name):
    """⛔ 「박스 절대경로 금지」. The repository root is FOUND by walking up to
    `server/dev_bench.py`, so the notebook works in any checkout."""
    # ⚠️ THE CELL TEXT, NOT `json.dumps` OF IT — the dump escapes every quote, so a probe
    # spelling one finds nothing and the assertion reads as 「absent」 while being unasked.
    body = "".join(_text(c) for c in _load(name)["cells"])
    for spelling in ("C:\\Users", "C:/Users", "/home/"):
        assert spelling not in body, (name, spelling)
    assert 'server" / "dev_bench.py' in body, "the root is found, not assumed"


@pytest.mark.parametrize("name", NAMES)
def test_autoreload_is_armed_so_an_edit_to_a_mapper_is_seen(name):
    """⚠️ WITHOUT IT THE AUTHOR EDITS THEIR FILE, RE-RUNS, AND SEES THE OLD MODULE — the
    「built is not loaded」 defect, in a shell where nothing announces it."""
    assert "%autoreload 2" in _text(_code_cells(_load(name))[0]), name


# ---------------------------------------------------------------------------
# 🔴 재구현 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_bench_cells_import_only_the_bench_and_the_standard_library(name):
    for index, cell in enumerate(_code_cells(_load(name))):
        if _is_freeform(cell):
            continue
        unexpected = _imports(_text(cell)) - ALLOWED_IMPORTS
        assert not unexpected, (name, index, sorted(unexpected))


@pytest.mark.parametrize("name", NAMES)
def test_bench_cells_do_not_re_implement_a_production_step(name):
    """🔴 THE DRIFT ORACLE. A cell that spells `pd.read_csv` or rebuilds a payload envelope
    has stopped being a window onto production and become a second implementation of it — and
    the second one is the one that is right until the day it is not."""
    for index, cell in enumerate(_code_cells(_load(name))):
        if _is_freeform(cell):
            continue
        body = _text(cell)
        for spelling in REIMPLEMENTED:
            assert spelling not in body, (name, index, spelling)


@pytest.mark.parametrize("name", NAMES)
def test_the_free_form_cells_are_tagged_and_there_are_some(name):
    """⛔ WITHOUT THIS, DELETING THE TAGS WOULD MAKE THE TWO GATES ABOVE PASS BY COVERING
    NOTHING — an exemption that can be granted silently is not a boundary."""
    tagged = [c for c in _code_cells(_load(name)) if _is_freeform(c)]
    assert tagged, "%s declares no free-form cell" % name
    for cell in tagged:
        assert "def " in _text(cell), "a free-form cell defines the function publish takes"


def test_each_notebook_reaches_the_bench_functions_its_lane_needs():
    """⚠️ NAMED, NOT COUNTED. 「it mentions dev_bench」 would stay green if the input cell were
    replaced by a hand-rolled query — these are the seats the two lanes actually stand on."""
    mapper = "".join(_text(c) for c in _load("mapper_workbench.ipynb")["cells"])
    for required in ("dev_bench.input_for_mapper(", "dev_bench.publish_mapper(",
                     "dev_bench.cell_body("):
        assert required in mapper, required

    parser = "".join(_text(c) for c in _load("parser_workbench.ipynb")["cells"])
    for required in ("dev_bench.raw_for_parser(", "dev_bench.claimers(",
                     "dev_bench.run_stages(", "dev_bench.publish_parser(",
                     "dev_bench.cell_body("):
        assert required in parser, required


# ---------------------------------------------------------------------------
# execution — off, by name
# ---------------------------------------------------------------------------

def _nb_runner_missing():
    missing = []
    for module in ("nbformat", "nbclient"):
        try:
            __import__(module)
        except Exception:
            missing.append(module)
    return missing


@pytest.mark.skipif(bool(_nb_runner_missing()),
                    reason="no notebook runner here: %s absent (ipykernel and "
                           "jupyter_client ARE present, which is why these run in the VS "
                           "Code editor and not from a server)" % ", ".join(
                               _nb_runner_missing() or ["-"]))
@pytest.mark.parametrize("name", NAMES)
def test_the_notebook_executes_end_to_end(name):
    """⚠️ THE HONEST LIMIT OF THIS FILE. Everything above scores TEXT. Only this scores
    behaviour, and it does not run here — so 「the notebook works」 is not something this
    suite has measured, and saying so is the point of leaving the test visible."""
    import nbclient
    import nbformat

    notebook = nbformat.read(os.path.join(NOTEBOOKS, name), as_version=4)
    nbclient.NotebookClient(notebook, timeout=120,
                            kernel_name="python3").execute()
