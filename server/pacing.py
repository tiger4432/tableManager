# -*- coding: utf-8 -*-
"""How hard a long job is allowed to push. One table, every long job reads it.

🔴 THE VALUES ARE IN A FILE AND NOT IN CONSTANTS, and that is the whole point. The chain's
equivalents (`OUTBOX_PURGE_MAX_CHUNKS`, `SWEEP_INTERVAL` in `chain_ingestion_worker.py`) are
constants, so an operator whose screen is crawling at 2am would have to edit code and restart
the server - and that restart is exactly what this handle exists to remove.

🔴 AND IT IS ONE TABLE FOR EVERY JOB, not one per job. It moved here from `ledger/` the
moment a second caller appeared, which is this repo's standing rule about when to lift
something into a template - not before, or the layer has one consumer; not later, or the
second caller writes its own copy and the two drift.

A pace is two numbers and nothing else: how many units of work before yielding, and how long
to yield for. What a "unit" is belongs to the caller - a page for the ledger, a chunk for
ingestion - because that is the boundary where ITS work is already committed and resuming is
exact. The table does not need to know.

The table ships as `config/sample/pacing.json.sample` (tracked); an operator's `config/pacing.json` holds only the
cells they changed and is read over it, cell by cell - a pace or a job by its name, any other key by itself (owner
11-09 «페이싱 깃 트래킹 빼»). A pace or job a release adds reaches a deployment whose own file predates it.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import paths
from error_said import told

#: The operator's cells (not tracked) - read over the shipped table.
PACING_PATH = Path(paths.config_path("pacing.json"))
SHIPPED_PATH = Path(paths.config_sample_path("pacing.json"))
#: Keys whose entries are read over by name rather than whole.
BY_NAME = ("paces", "jobs")

#: The pace that means "exactly what this did before the handle existed". Changing which
#: pace is the default is a different decision and it belongs to the owner.
DEFAULT_PACE = "fast"


class UnknownPace(ValueError):
    """An undeclared pace name. Raised rather than falling back to the default.

    🔴 THE FALLBACK IS THE DANGEROUS ANSWER HERE. Somebody reaches for `slow` because the
    service is already struggling; if a typo quietly meant `fast` they would watch the exact
    thing they were preventing, unable to tell "the handle does not work" from "the handle
    did not help" - and pressing it again does nothing either.
    """


def read_table(path=None):
    """The shipped table with the operator's cells over it; `path`: that one file alone."""
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    table = json.loads(SHIPPED_PATH.read_text(encoding="utf-8"))
    if PACING_PATH.exists():
        for key, value in json.loads(PACING_PATH.read_text(encoding="utf-8")).items():
            table[key] = dict(table.get(key) or {}, **value) if key in BY_NAME and isinstance(value, dict) else value
    return table


def load_paces(path=None):
    return read_table(path)["paces"]


#: The seconds a page aims at unless pacing.json says `page_seconds` (소유자 10-12 「모든 소급은 5 초에 한 번은 진행
#: 상황이 보이게」 · 「한 배치에 5 초 이내 무조건」) - never above the cap.
PAGE_SECONDS_KEY, PAGE_SECONDS_DEFAULT, PAGE_SECONDS_CAP = "page_seconds", 3.0, 5.0


def page_seconds(path=None):
    """The declared page time, the default when absent, unreadable or not a positive number, and never above the cap -
    a typo in pacing.json must not stop every page loop (the ledger follow-up reads its pace the same way)."""
    try:
        value = read_table(path).get(PAGE_SECONDS_KEY)
    except Exception as exc:                      # noqa: BLE001
        logging.getLogger(__name__).warning("[Pacing] page_seconds unreadable, using the default: %s", told(exc), exc_info=exc)
        return PAGE_SECONDS_DEFAULT
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return PAGE_SECONDS_DEFAULT
    return min(float(value), PAGE_SECONDS_CAP)


def load_jobs(path=None):
    """Which pace each self-starting job runs at. `{}` when the file declares none."""
    return read_table(path).get("jobs", {})


def job_pace(job, path=None):
    """-> (units_per_cycle, rest_seconds) for a job that has nobody to ask.

    🔴 A JOB NOBODY STARTS HAS NO OPERATOR TO CHOOSE FOR IT. Every caller so far took
    `pace` from whoever pressed the button; a task that wakes on its own cannot, so the
    answer is a declared cell instead of a constant in its module -- which is this file's
    whole reason for existing. An undeclared job resolves to `DEFAULT_PACE`, and that stays
    the one decision this module will not make on somebody's behalf.
    """
    return resolve(load_jobs(path).get(job), load_paces(path))


def resolve(name, paces=None):
    """-> (units_per_cycle, rest_seconds). `units_per_cycle` None means "never yield"."""
    paces = paces or load_paces()
    if name is None:
        name = DEFAULT_PACE
    if name not in paces:
        raise UnknownPace(
            f"'{name}' is not a declared pace. Declared: {', '.join(sorted(paces))} "
            f"(server/config/pacing.json)")
    chosen = paces[name]
    return chosen.get("units_per_cycle", chosen.get("pages_per_cycle")), float(
        chosen.get("rest_seconds") or 0)
