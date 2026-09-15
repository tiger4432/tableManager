# -*- coding: utf-8 -*-
"""판정 406. 체인 루프는 «자기 프로세스»에서 돈다 — API 안에서 도는 것은 «단독 기동»뿐이다.

> 소유자 2026-09-15: 「과연 이런 문제 요소가 한두 개일까? 운영에서는 **수십 개 체인·인제션·
> 서버 요청이 도는데**」

🔴 THE STRUCTURE, NOT THE INSTANCE. The chain loop's body is synchronous database work, and
`main.py` starts it with `create_task` on the event loop - so ANY slow tick (a query, a
mapper, a cycle) freezes every HTTP request for exactly that long. S-252 was one instance:
a single unconsumable outbox row spun the loop and the whole API stopped answering. Moving
that one tick off the loop would have fixed that row and left the shape.

⛔ AND THE LAUNCHER ALREADY HAD THE ANSWER, HALF-APPLIED. `run_decoupled_app.py` starts
`run_chain_worker.py` as a child of its own AND did not tell the API child to stand down -
so a launcher-run deployment had TWO chain loops, one of them inside uvicorn.

⚠️ 「두 경로 금지」 IS WHY THIS IS NOT AN EXECUTOR. Moving the tick to a thread pool would
leave two ways to run the chain; one process is the answer (판정 406).

🔴 WHAT THIS FILE SCORES, SAID PLAINLY: TEXT, not a running deployment. The launcher's
child specs ARE configuration - reading them is reading the configuration, which is the
subject - but the two `main.py` assertions read SOURCE for behaviour I could not drive
without standing up a FastAPI startup. They are the weaker kind, and what would actually
prove the pair is a launcher start with `ASSY_CHAIN_WORKER` observed in the API child's
environment and one chain heartbeat rather than two. That is a restart, and the restart is
총괄's.
"""
import io
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.abspath(os.path.join(SERVER_DIR, ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

LAUNCHER = os.path.join(REPO_ROOT, "run_decoupled_app.py")


def _launcher_source() -> str:
    return io.open(LAUNCHER, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the launcher tells the API child to stand down
# ---------------------------------------------------------------------------

def test_the_api_child_is_told_not_to_run_a_chain_loop():
    """🔴 THE ONE LINE THIS RULING IS. Without it the launcher runs two chain loops and one
    of them is inside the process serving HTTP."""
    source = _launcher_source()
    api_spec = source[source.index('ChildSpec("Backend FastAPI Server"'):]
    api_spec = api_spec[:api_spec.index("ChildSpec(", 10)]

    assert '"ASSY_CHAIN_WORKER": "0"' in api_spec, api_spec[-400:]


def test_the_chain_worker_child_is_still_started_by_the_launcher():
    """⚠️ THE CONTROL. Telling the API to stand down is only right because a process whose
    whole job is the chain is started beside it - otherwise this ruling would switch the
    chain off in production."""
    source = _launcher_source()

    assert "run_chain_worker.py" in source
    assert 'heartbeat="chain"' in source


def test_the_chain_worker_child_is_not_told_to_stand_down():
    """⛔ THE OBVIOUS WAY TO GET THIS WRONG. The variable is read by `main.py` at startup,
    and a launcher that exported it globally rather than per-child would silence the very
    process it just started."""
    source = _launcher_source()
    worker_spec = source[source.index('ChildSpec("Chained Ingestion Worker"'):]
    worker_spec = worker_spec[:worker_spec.index("ChildSpec(", 10)]

    assert "ASSY_CHAIN_WORKER" not in worker_spec


# ---------------------------------------------------------------------------
# ⛔ ⓑ — and the off branch has to actually work
# ---------------------------------------------------------------------------

def test_the_off_branch_does_not_touch_a_task_it_never_created():
    """⛔ IT DID. `chain_task` is `None` on that branch and `add_done_callback` ran
    unconditionally, so `ASSY_CHAIN_WORKER=0` raised `AttributeError` into the handler
    below and reported itself as 「Startup step failed (watcher/chain worker)」.

    🔴 THE SWITCH HAD NEVER BEEN EXERCISED, and 판정 406 ① is the day it becomes the NORMAL
    path for every launcher-run deployment - a guard goes wrong the day it is reachable."""
    import inspect

    import main

    body = inspect.getsource(main.startup_event)
    callback = body[body.index("add_done_callback") - 400:body.index("add_done_callback")]

    assert "if chain_task is not None:" in callback, callback[-200:]


def test_running_inside_the_api_says_so_rather_than_being_silent():
    """⚠️ [판정 406 ②] SINGLE-PROCESS MODE STAYS, because a box and a development run want
    it - but silence about it is what let a chain loop live inside uvicorn in production
    without anyone deciding that it should."""
    import inspect

    import main

    body = inspect.getsource(main.startup_event)

    assert "INSIDE the API process" in body
    assert "run_decoupled_app.py" in body


def test_standing_down_is_not_reported_as_a_failure():
    """⚠️ IT IS THE CORRECT STATE UNDER THE LAUNCHER, so it cannot read as a warning about
    something being wrong - an operator who greps warnings would find one on every healthy
    production start."""
    import inspect

    import main

    body = inspect.getsource(main.startup_event)
    stand_down = body[body.index("NOT started in this process") - 200:
                      body.index("NOT started in this process")]

    assert "logger.info(" in stand_down, stand_down[-160:]
