"""Lead 11-10 ㄴ: the work behind the reads - the grid's whole counts, the recent history's catch-up, the column picker's
counts - runs on one mechanism (`runtime.behind`), each Behind on workers of its own: a key runs once at a time, its
last run is kept, it runs again only when asked; a count held on one does not hold another's; every run is on «running
now»; the picker's limit never cancels a connection after it was given back.
"""
import threading
import time

from ledger import column_stats
from runtime import behind, running


def _until(predicate, seconds=10.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_a_key_runs_once_is_kept_and_runs_again_only_when_asked():
    worker = behind.Behind("probe-behind", lambda: 0.0, "[Probe] %s not done")
    runs, go = [], threading.Event()

    def work():
        runs.append(1)
        go.wait(10)
        return {"n": len(runs)}

    worker.ask("k", work)
    worker.ask("k", work)                                        # due already
    assert _until(lambda: worker.running()), "canary: the run started"
    worker.ask("k", work)                                        # running
    go.set()
    assert _until(lambda: not worker.busy("k"))
    assert worker.ask("k", work)["n"] == 1 and not worker.busy("k") and runs == [1]
    worker.ask("k", work, again=lambda kept: True)
    assert _until(lambda: not worker.busy("k")) and runs == [1, 1]
    assert worker.ask("k", work)["n"] == 2


def test_a_failed_run_keeps_the_last_result_and_says_it_failed():
    worker = behind.Behind("probe-behind", lambda: 0.0, "[Probe] %s not done")
    answers = iter([{"n": 1}, ValueError("no")])

    def work():
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    worker.ask("k", work)
    assert _until(lambda: (worker.ask("k", work) or {}).get("n") == 1)
    worker.ask("k", work, again=lambda kept: True)
    assert _until(lambda: (worker.ask("k", work) or {}).get("failed"))
    kept = worker.ask("k", work)
    assert kept["n"] == 1 and kept["failed"]["reason"].startswith("ValueError: no")


def test_a_column_count_held_does_not_hold_the_grids_whole_count(client):
    go = threading.Event()
    key = ("held_probe", (), ())
    column_stats.COUNTS.ask(key, lambda: go.wait(30) and {})
    try:
        assert _until(lambda: column_stats.COUNTS.running()), "canary: the column count runs"
        assert _until(lambda: client.get("/tables/raw_table_1/data/count").json()["counting"] is False), \
            "the grid's whole count waited on the column count"
        assert client.get("/tables/raw_table_1/data/count").json()["total"] == 10
        assert column_stats.COUNTS.running(), "canary: still held"
        said = [item for item in running._behind() if item["what"].startswith("column-counts")]
        assert [(item["what"], item["where"]) for item in said] == [("column-counts · held_probe", running.WHERE_API)]
    finally:
        go.set()
        _until(lambda: not column_stats.COUNTS.busy(key))
        column_stats.COUNTS.forget()


def test_the_picker_limit_never_cancels_after_its_block_ended():
    said = []
    with column_stats._Deadline(60, lambda: said.append("cancel")) as deadline:
        pass
    deadline._fire()                                             # the timer's body, late
    assert said == []
    with column_stats._Deadline(0.05, lambda: said.append("cancel")):
        assert _until(lambda: said, 5)
    assert said == ["cancel"]
