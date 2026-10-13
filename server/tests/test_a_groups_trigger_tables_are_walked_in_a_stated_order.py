# -*- coding: utf-8 -*-
"""S-228 (판정 385 ㉡). 한 그룹의 트리거 표 순회 순서가 «프로세스마다» 달랐다.

🔴 MEASURED, AND THE SECOND MEASUREMENT IS THE ONE THAT IS TRUE. Six table names in a set,
flattened in five separate processes with `PYTHONHASHSEED` unset -> FIVE DIFFERENT ORDERS.
A first run with only FOUR names over three processes came out identical, and stopping there
would have produced 「it is deterministic」 from a sample that decided the answer.

🔴 WHY IT MATTERS BEYOND TIDINESS. A group carrying two trigger tables ran its rules in an
order that could change at every restart - so 「A runs before B」 (S-156) had nothing to stand
on, and a gate written on top of it would have been measuring the hash seed.

⚠️ SORTED IS ARBITRARY AND SAYS SO. 「The order they arrived in」 would be the outbox's id
order, a second axis that would make this depend on how a writer chunked its commit. The
property that matters is only that every process gives the SAME answer.
"""
import os
import subprocess
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                           # noqa: E402

NAMES = ["dt_log", "lot_event", "production_plan", "bonding_log", "inventory_master", "dt_map"]

#: ⚠️ SIX, NOT FOUR. Four names is the sample that agreed with itself three times.
PROBE = (
    "import sys; sys.path.insert(0, %r)\n"
    "from chain import ingestion_worker as w\n"
    "class E:\n"
    "    def __init__(self, t):\n"
    "        self.table_name, self.event_type = t, 'CREATE'\n"
    "print('|'.join(w.trigger_tables_in_order([E(n) for n in %r])))\n"
) % (SERVER_DIR, NAMES)


class _Event:
    def __init__(self, table_name, event_type="CREATE"):
        self.table_name = table_name
        self.event_type = event_type


def _order_under_seed(seed):
    environment = dict(os.environ, PYTHONHASHSEED=seed)
    done = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True,
                          env=environment, cwd=SERVER_DIR)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout.strip().splitlines()[-1]


def test_two_processes_with_different_hash_seeds_walk_the_same_order():
    """🔴 THE GATE THE RULING NAMED. Two seeds, one answer - and the seeds are what made the
    old code disagree with itself."""
    assert _order_under_seed("0") == _order_under_seed("1")


def test_the_order_is_the_one_the_function_states():
    """⚠️ The subprocess pair proves 「the same every time」; this says WHICH order, so that a
    change from sorted to something else cannot pass by being consistently wrong."""
    events = [_Event(name) for name in NAMES]

    assert worker.trigger_tables_in_order(events) == sorted(NAMES)


def test_only_a_create_or_an_edit_is_a_trigger():
    """The filter is part of the answer: a DELETE does not wake a rule, so its table must not
    appear and then match nothing."""
    events = [_Event("kept", "CREATE"), _Event("also_kept", "EDIT"),
              _Event("dropped", "DELETE")]

    assert worker.trigger_tables_in_order(events) == ["also_kept", "kept"]


def test_one_table_named_by_many_events_is_walked_once():
    events = [_Event("t"), _Event("t"), _Event("t")]

    assert worker.trigger_tables_in_order(events) == ["t"]


def test_no_events_is_no_walk():
    assert worker.trigger_tables_in_order([]) == []
