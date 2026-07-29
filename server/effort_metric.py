"""Interaction-effort instrument — config side.

SYSTEM_OVERVIEW §1 core value #1 is "minimum-effort correction". Its canonical
instrument (user, 2026-07-29) is the INTERACTION SCORE TO COMPLETION: how much
human effort one completed correction cost. Lower is better.

    score(tx) = key * w_key + mouse * w_mouse + nav * w_nav

This module owns the *declared* half of that instrument: the weights and the
allowlist of screen transitions that do NOT cost the navigation penalty. The
raw counts live in `models.InteractionEffortLog`; the aggregate lives in
`crud.get_effort_stats`.

WHY WEIGHTS ARE CONFIG, NOT CONSTANTS
    Raw counts are stored, the score is computed at READ time (see
    crud.get_effort_stats). That is deliberate: if a weight is ever re-tuned,
    every past transaction is re-interpreted under the new weights instead of
    being frozen at the value it happened to have when it was recorded. A
    hardcoded weight would make the historical baseline unreadable the moment
    anyone disagreed with it - and the whole point of this instrument is to
    compare before/after a UI overhaul.

WHY THE TRANSITION LIST DEFAULTS TO EMPTY
    An undeclared transition scores the full navigation penalty. The allowlist
    is a positive declaration ("this jump preserves context, e.g. DOE -> dt map
    routing"), never an inference. Seeding it with guesses would bias the
    instrument optimistic in exactly the direction its owner would like, which
    is how an instrument stops being one. Entries are proposed by whoever owns
    the routing (client) and approved by the lead - not invented here.

The client reads this through `GET /api/effort/config` and keeps no copy of its
own, the same way `GET /api/maps/paint-rules` serves `binding`.
"""
import json
import logging
import math
import os

import paths

logger = logging.getLogger(__name__)

CONFIG_PATH = paths.config_path("effort_metric.json")

# The user-specified scoring (2026-07-29): keystroke 1, mouse click 3,
# context-losing screen move 5. These are the DEFAULTS - the config file
# overrides them, and a missing config file is normal operation, not an error.
#
# `nav_preserved` (lead addendum 2026-07-29) weighs the transitions the client
# classified as CONTEXT-PRESERVING. It defaults to 0, so today it contributes
# nothing and the published score is unchanged - but the count is stored, so a
# transition that turns out to have been wrongly exempted can be re-scored from
# the existing rows by moving this one number. Classification therefore stays a
# QUERY-time interpretation, exactly like the other weights.
#
# This matters more than a mis-set weight would: the metric is not
# retroactively computable, so the pre-UI-overhaul window is the only baseline
# that will ever exist. Discarding exempted transitions at collection time
# would have made a classification error permanently unfixable.
DEFAULT_WEIGHTS = {"key": 1, "mouse": 3, "nav": 5, "nav_preserved": 0}

WEIGHT_KEYS = ("key", "mouse", "nav", "nav_preserved")


def load_config(path: str = None) -> dict:
    """Load effort_metric.json. Missing file -> {} (all defaults apply)."""
    p = path or CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("[EffortMetric] failed to load config %s: %s", p, e)
        return {}


def resolve_weights(config: dict = None) -> dict:
    """Return the RESOLVED weights - always all three keys, always usable.

    A declared weight must be a finite, non-negative number. A negative weight
    would mean "more effort scores better", which inverts the instrument; a
    non-numeric one would crash the aggregate SQL. Either way the offending key
    falls back to its default and says so in the log, rather than taking the
    dashboard down or silently publishing a meaningless average.
    """
    declared = (config or {}).get("weights")
    resolved = dict(DEFAULT_WEIGHTS)
    if not isinstance(declared, dict):
        if declared is not None:
            logger.warning("[EffortMetric] 'weights' must be an object; using defaults.")
        return resolved

    for k in WEIGHT_KEYS:
        if k not in declared:
            continue
        v = declared[k]
        # bool is a subclass of int in Python - True would silently become 1.
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            logger.warning("[EffortMetric] weight '%s' must be a number (got %r); using default %s.",
                           k, v, resolved[k])
            continue
        if not math.isfinite(v) or v < 0:
            logger.warning("[EffortMetric] weight '%s' must be finite and >= 0 (got %r); using default %s.",
                           k, v, resolved[k])
            continue
        resolved[k] = v
    return resolved


def resolve_context_preserving_transitions(config: dict = None) -> list:
    """Return the declared allowlist of context-PRESERVING route transitions.

    Shape of one entry: {"from": "<route>", "to": "<route>"} (both non-empty
    strings, EXACT route names). Anything else is REJECTED with a warning and
    never served - a malformed entry that was silently kept would read as
    "declared" and quietly zero a real penalty.

    WILDCARDS ARE REJECTED, NOT IGNORED. `"*"`, `"*>*"` or any `*` inside a
    route name is refused. Matching is exact, so a wildcard would sit in the
    config as an INERT LITERAL: it matches no real route, yet a config author
    reading the file would believe a whole class of moves had been exempted.
    Silently keeping it is the worst outcome - the declaration and the
    behaviour disagree and nothing says so. Refusing it makes the disagreement
    visible in the log and in `GET /api/effort/config`, which omits the entry.

    DEFAULT IS COUNTED. An empty list (the seeded state) means every screen
    move costs the nav weight. The client is the only party that can classify a
    transition, so it consumes this list and reports the split as `nav` /
    `nav_preserved`; the server does not classify navigation itself.
    """
    declared = (config or {}).get("context_preserving_transitions")
    if declared is None:
        return []
    if not isinstance(declared, list):
        logger.warning("[EffortMetric] 'context_preserving_transitions' must be a list; "
                       "treating as empty (every transition counted).")
        return []

    out = []
    for entry in declared:
        if not (isinstance(entry, dict)
                and isinstance(entry.get("from"), str) and entry["from"].strip()
                and isinstance(entry.get("to"), str) and entry["to"].strip()):
            logger.warning("[EffortMetric] REJECTED malformed transition entry %r "
                           "(expected {\"from\": str, \"to\": str}). It is NOT exempt.", entry)
            continue
        if "*" in entry["from"] or "*" in entry["to"]:
            logger.warning(
                "[EffortMetric] REJECTED wildcard transition entry %r. Route matching is "
                "EXACT - a wildcard would never match anything while looking like a "
                "declaration. Declare each transition explicitly. It is NOT exempt.", entry)
            continue
        out.append({"from": entry["from"], "to": entry["to"]})
    return out


def get_public_config(path: str = None) -> dict:
    """The single client-facing view of the instrument's declared half."""
    config = load_config(path)
    return {
        "weights": resolve_weights(config),
        "context_preserving_transitions": resolve_context_preserving_transitions(config),
    }
