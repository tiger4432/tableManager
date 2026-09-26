# -*- coding: utf-8 -*-
"""The collector status record carries each collector's declared `# window:` (lead 09f0be40f).

The Auto Update tab turns a collector's Backfill on only for a collector that declares a
window, and it reads that from `/admin/auto-update/status`, which is this record passed
through. A collector without the header - or a class collector, which has no header -
records `None`, so the screen can tell 「not declared」 from 「an older record without the key」.
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_auto_update import MultiDiscoveryScheduler                 # noqa: E402


def _collector(script, **extra):
    """Only the cells the status writer reads - no workspace folders made."""
    return SimpleNamespace(table_name="probe_table", script_path=f"/probe/{script}",
                           cron_expression=None, next_run=None, last_run=None,
                           last_status="PENDING", last_error=None, runner=None, **extra)


def test_the_record_names_the_declared_window_and_none_elsewhere(tmp_path):
    s = MultiDiscoveryScheduler(check_interval=5, server_dir=str(tmp_path))
    s.status_file_path = str(tmp_path / "config" / "scheduler_status.json")
    s.collectors = [
        _collector("daily.py", window_length="1d"),   # a script that declares `# window: 1d`
        _collector("plain.py", window_length=None),   # a script without the header
        _collector("ClassCollector"),                 # a class collector: no such attribute
    ]

    s._write_status_file()

    with open(s.status_file_path, encoding="utf-8") as fh:
        rows = json.load(fh)["collectors"]
    assert [(r["script_name"], r["window"]) for r in rows] == [
        ("daily.py", "1d"), ("plain.py", None), ("ClassCollector", None)]
