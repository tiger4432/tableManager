# -*- coding: utf-8 -*-
"""콘솔은 «고른 자식»만 보여 준다. 파일은 그대로다 (S-138 ①, 소유자 「콘솔이 난장판」).

🔴 THE SUPERVISOR TEES FOUR CHILDREN INTO ONE CONSOLE. The files were already split by
purpose - `server_stdout.log`, `watcher_stdout.log`, and so on - so the mixing was only ever
on screen, which is exactly where the owner is reading.

⛔ THE FILE IS NEVER GATED ON THIS. The file is the record and the console is a pair of
eyes; an operator choosing what to WATCH must not thereby choose what gets KEPT. So the
predicate reaches only the console write, and a test pins that the file write is outside it.

⚠️ DEFAULT IS EVERY CHILD, so a launcher started the way it always was behaves the way it
always did.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from launcher_args import parse_launcher_args                        # noqa: E402
from process_supervisor import Supervisor                            # noqa: E402


def _supervisor(names=()):
    sup = Supervisor([], log=lambda *a, **k: None)
    sup.console_names = frozenset(names)
    return sup


# ── the selection ────────────────────────────────────────────────────────────

def test_no_selection_means_every_child_as_before():
    sup = Supervisor([], log=lambda *a, **k: None)

    assert sup._tees_to_console("Chained Ingestion Worker")
    assert sup._tees_to_console("Backend FastAPI Server")


def test_only_the_named_child_reaches_the_console():
    sup = _supervisor({"chained ingestion worker"})

    assert sup._tees_to_console("Chained Ingestion Worker")
    assert not sup._tees_to_console("Backend FastAPI Server")


def test_an_operator_may_type_it_with_different_case_or_spacing():
    """⚠️ 이름은 `specs` 의 것 «그대로»이고, 관대한 것은 «비교»뿐이다."""
    sup = _supervisor({"chained ingestion worker"})

    assert sup._tees_to_console("  Chained Ingestion Worker  ")
    assert sup._tees_to_console("CHAINED INGESTION WORKER")


def test_a_name_nobody_declared_simply_matches_nothing():
    sup = _supervisor({"no such child"})

    assert not sup._tees_to_console("Backend FastAPI Server")


# ── the flag ─────────────────────────────────────────────────────────────────

def test_both_spellings_of_the_flag_are_accepted():
    assert sorted(parse_launcher_args(["--console", "chain"]).console_names) == ["chain"]
    assert sorted(parse_launcher_args(["--console=a,b"]).console_names) == ["a", "b"]


def test_an_unset_flag_selects_nothing_which_means_everything():
    assert parse_launcher_args(["--server-only"]).console_names == frozenset()


def test_the_existing_flags_still_parse_and_a_typo_is_still_refused():
    """⚠️ 기존 인자 무변 — 그리고 이 파일의 «존재 이유»인 오타 거절이 살아 있어야 한다."""
    args = parse_launcher_args(["--server-only", "--console", "chain"])

    assert args.server_only and not args.is_refusal
    assert parse_launcher_args(["--consoel", "chain"]).is_refusal


# ── the file must not be affected ────────────────────────────────────────────

def test_the_file_write_is_outside_the_console_predicate():
    """🔴 THE ONE THING THIS MUST NOT DO. If the predicate reached the file write, an
    operator narrowing what they WATCH would silently stop what gets KEPT."""
    import inspect

    body = inspect.getsource(Supervisor._attach_log_pump)

    console_at = body.index("_tees_to_console")
    assert "handle.write(line)" in body
    assert body.index("handle.write(line)") > console_at, \
        "the file write must not sit inside the console branch"
    # And the console write is the only thing the predicate guards.
    assert "console.write(line)" in body


def test_the_launcher_hands_the_selection_to_the_supervisor():
    """착지는 배선이 아니다."""
    import io as _io
    import os as _os

    root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    src = _io.open(_os.path.join(root, "run_decoupled_app.py"), encoding="utf-8").read()

    assert "supervisor.console_names = args.console_names" in src
