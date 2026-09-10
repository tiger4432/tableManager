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


# ── ② each child in its own window (S-138 ②, 판정 257) ───────────────────────

def test_the_flag_parses_and_defaults_off():
    assert parse_launcher_args(["--own-window"]).own_window
    assert not parse_launcher_args(["--server-only"]).own_window
    assert parse_launcher_args(["--own_window"]).is_refusal, "underscore is still a typo"


def test_the_window_is_titled_with_the_child_name():
    """게이트: 창 제목 = 자식 이름. `STARTUPINFO` 가 `lpTitle` 을 안 내주므로 `cmd /c title`
    이 그 이름을 붙이는 «유일한» 자리다."""
    import inspect

    body = inspect.getsource(Supervisor._spawn_in_own_window)

    assert '"title", title' in body
    assert "spec.name" in body
    assert "CREATE_NEW_CONSOLE" in body


def test_the_pipe_is_given_up_and_that_is_the_whole_trade():
    """🔴 프로세스의 stdout 은 «하나»다. 자기 창에 쓰면 감독 파이프로는 안 온다 - 그래서
    이 갈래는 `stdout=PIPE` 를 «안 쓴다». 둘 다 되는 척하면 로그가 조용히 빈다."""
    import inspect

    body = inspect.getsource(Supervisor._spawn_in_own_window)

    assert "subprocess.PIPE" not in body


def test_the_ordinary_spawn_is_untouched_when_the_flag_is_off():
    """⚠️ 안 켜면 오늘 그대로 — 파이프도 파일도 그대로다."""
    import inspect

    body = inspect.getsource(Supervisor._default_spawn)

    assert 'getattr(self, "own_window", False)' in body
    assert 'os.name == "nt"' in body, "Windows 전용임이 코드에 있어야 한다"
    assert "stdout=subprocess.PIPE" in body, "기본 갈래는 여전히 파이프"


def test_the_launcher_names_which_files_go_empty_and_why():
    """🔴 판정 257 의 정정된 게이트. 빈 로그를 인시던트에서 「부재의 증거」로 읽는 것을
    막는 것이 이 한 줄의 일이다."""
    import io as _io
    import os as _os

    root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    src = _io.open(_os.path.join(root, "run_decoupled_app.py"), encoding="utf-8").read()

    assert "supervisor.own_window = args.own_window" in src
    assert "stay EMPTY" in src
    assert "writes its OWN log file" in src, "무엇이 «안» 바뀌는지도 같이 말해야 한다"
    assert "s.log_file" in src, "파일 이름을 specs 에서 «세어» 말한다"
