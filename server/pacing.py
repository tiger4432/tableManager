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
"""
from __future__ import annotations

import json
from pathlib import Path

PACING_PATH = Path(__file__).with_name("pacing.json")

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


def load_paces(path=None):
    return json.loads(Path(path or PACING_PATH).read_text(encoding="utf-8"))["paces"]


def resolve(name, paces=None):
    """-> (units_per_cycle, rest_seconds). `units_per_cycle` None means "never yield"."""
    paces = paces or load_paces()
    if name is None:
        name = DEFAULT_PACE
    if name not in paces:
        raise UnknownPace(
            f"'{name}' is not a declared pace. Declared: {', '.join(sorted(paces))} "
            f"(server/pacing.json)")
    chosen = paces[name]
    return chosen.get("units_per_cycle", chosen.get("pages_per_cycle")), float(
        chosen.get("rest_seconds") or 0)
