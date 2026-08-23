"""Canonical experiment-unit mark shared by Trend and typed selection.

The mark is deliberately *not* an ontology entity identity.  A physical Wafer is the
subject.  ``bonding_leg`` names the human-planned experiment unit asserted by
``bonding_map`` and is used as the context for void aggregation inside that wafer.
"""
from __future__ import annotations

import base64
import json


SUBJECT_TYPE = "Wafer"
UNIT_KIND = "bonding_experiment_unit"
CONTEXT_ROLE = "planned_bonding_experiment_unit"
MARK_PREFIX = "experiment-unit:v1:"


class AnalysisIdentityError(ValueError):
    pass


def _part(value, name):
    if not isinstance(value, str) or not value.strip():
        raise AnalysisIdentityError(f"{name} must be a non-empty string")
    return value


def encode_mark(wafer, bonding_leg):
    body = json.dumps([UNIT_KIND, _part(wafer, "wafer"),
                       _part(bonding_leg, "bonding_leg")],
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MARK_PREFIX + base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")


def decode_mark(mark_key):
    if not isinstance(mark_key, str) or not mark_key.startswith(MARK_PREFIX):
        raise AnalysisIdentityError("mark_key is not a bonding experiment unit v1 mark")
    encoded = mark_key[len(MARK_PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        values = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise AnalysisIdentityError(f"invalid bonding experiment unit mark: {exc}") from exc
    if not isinstance(values, list) or len(values) != 3 or values[0] != UNIT_KIND:
        raise AnalysisIdentityError("invalid bonding experiment unit mark payload")
    wafer, bonding_leg = _part(values[1], "wafer"), _part(values[2], "bonding_leg")
    if encode_mark(wafer, bonding_leg) != mark_key:
        raise AnalysisIdentityError("bonding experiment unit mark is not canonical")
    return {"wafer": wafer, "bonding_leg": bonding_leg}


def identity(wafer, bonding_leg):
    wafer = _part(wafer, "wafer")
    bonding_leg = _part(bonding_leg, "bonding_leg")
    return {
        "type": SUBJECT_TYPE,
        "keys": {"wafer": wafer},
        "context": {"role": CONTEXT_ROLE, "bonding_leg": bonding_leg},
        "aggregation": {"kind": "void_by_experiment_unit", "finding_kind": "void"},
        "mark_key": encode_mark(wafer, bonding_leg),
    }
