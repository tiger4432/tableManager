# -*- coding: utf-8 -*-
"""A collector script whose header and markers do not fit is refused by name - at the
scheduler's load and on the Declarations screen, by ONE judge (`collector_markers.
script_refusals`), in one sentence.

A window header and the window markers come as a pair; a list marker names a column the
table catalogue declares and the grid can list. The report lives in the API process, which
must not import `run_auto_update` (it rewrites proxy settings on import) - so the judge
lives in `collector_markers`, and both doors import that.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config_resolve_report as crr                                        # noqa: E402
import paths                                                               # noqa: E402
import run_auto_update as rau                                              # noqa: E402
from database import crud                                                  # noqa: E402

TABLE = "judged_probe_tbl"
GRID = "judged_parts"
SCHEDULE = "# schedule: * * * * *\n"
WINDOW = "# window: 1d\n"
USES_WINDOW = 'out = [{"s": "{{WINDOW_START}}", "e": "{{WINDOW_END}}"}]\n'

#: (cell, header, body, the start of the refusal sentence or None when it loads)
CELLS = [
    ("header and markers", SCHEDULE + WINDOW, USES_WINDOW, None),
    ("no header and no markers", SCHEDULE, 'out = [{"a": "1"}]\n', None),
    ("a window header with no markers", SCHEDULE + WINDOW, 'out = [{"a": "1"}]\n',
     "'probe.py' declares '# window: 1d' but writes neither"),
    ("markers with no window header", SCHEDULE, USES_WINDOW,
     "'probe.py' writes {{WINDOW_START}} or {{WINDOW_END}} but declares no '# window:'"),
    ("a window that is not a length", SCHEDULE + "# window: 1w\n", USES_WINDOW,
     "'# window: 1w' is not a length"),
    ("a list of a declared text column", SCHEDULE, 'x = "{{LIST:judged_parts.part_id}}"\n', None),
    ("a list of an undeclared column", SCHEDULE, 'x = "{{LIST:judged_parts.nope}}"\n',
     "{{LIST:judged_parts.nope}} names a column table_config does not declare"),
    ("a list of a datetime column", SCHEDULE, 'x = "{{LIST:judged_parts.made_at}}"\n',
     "{{LIST:judged_parts.made_at}} names a datetime column"),
]


@pytest.fixture(autouse=True)
def fixture_grid_catalogue(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, GRID, {
        "business_key": "k",
        "column_types": {"k": "string", "part_id": "string", "made_at": "datetime"}})


@pytest.mark.parametrize("cell,header,body,refusal", CELLS, ids=[c[0] for c in CELLS])
def test_the_scheduler_and_the_report_give_one_verdict(cell, header, body, refusal,
                                                       tmp_path, monkeypatch):
    folder = os.path.join(str(tmp_path), "ingestion_workspace", TABLE, "auto_update")
    os.makedirs(folder)
    with open(os.path.join(folder, "probe.py"), "w", encoding="utf-8") as f:
        f.write(header + body)
    logged = []
    monkeypatch.setattr(rau.logger, "error",
                        lambda msg, *args, **kw: logged.append(msg % args if args else msg))
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

    scheduler = rau.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    scheduler.discover_and_load_collectors()
    domain = crr._resolve_collector()
    subject = "%s/probe.py" % TABLE
    effective = [e for e in domain["effective"] if e["subject"] == subject]
    rejected = [e for e in domain["rejected"] if e["subject"] == subject]

    if refusal is None:
        assert [c.table_name for c in scheduler.collectors] == [TABLE], logged
        assert effective and not rejected
        return
    assert scheduler.collectors == [], "a refused script is not loaded"
    assert rejected and not effective
    [said] = rejected[0]["fields"]["issues"]
    assert said.startswith(refusal), said
    assert rejected[0]["reason"] == crr.REASON_MAPPING_UNAVAILABLE
    assert any(said in line for line in logged), "the scheduler says the same sentence"


def test_the_report_lists_the_collector_area():
    assert crr.DOMAIN_COLLECTOR in [d["domain"] for d in crr.resolve_report()["domains"]]
