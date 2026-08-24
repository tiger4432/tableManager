"""Canonical experiment-unit mark shared by Trend and typed selection.

The mark is deliberately *not* an ontology entity identity.  A physical Wafer is the
subject.  ``bonding_leg`` names the human-planned experiment unit asserted by
``bonding_map`` and is used as the context for void aggregation inside that wafer.
"""
from __future__ import annotations

import base64
import json

import ledger_explorer


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


#: 🔴 THE SUBJECT TYPE IS THE CALLER'S DECLARATION, NOT THIS MODULE'S CONSTANT.
#: This held `SUBJECT_TYPE = "Wafer"` and every caller inherited it. On 2026-08-24 the
#: ledger's type names became lowercase and that literal started matching ZERO rows --
#: the void trend answered 0% while its own map read 50%, and delam went dark with it,
#: because `AND subject_type = 'Wafer'` excluded all 115,423 observation atoms. Nothing
#: raised; the series simply came back flat.
#:
#: ⚠️ THE REPAIR IS NOT SPELLING IT LOWERCASE. That survives exactly until the next rename.
#: The grain already declares which subject it aggregates, so the value arrives as an
#: argument and this module stops having an opinion about it.
def identity(wafer, bonding_leg, subject_type):
    wafer = _part(wafer, "wafer")
    bonding_leg = _part(bonding_leg, "bonding_leg")
    subject_type = _part(subject_type, "subject_type")
    keys = {"wafer": wafer}
    return {
        "type": subject_type,
        # 🔴 THE MARK IS A NODE, AND THIS IS ITS ID. Owner ruling 2026-08-24: 「키는 노드
        #    아이디와 노드 타입」. Until now the trend's key was `experiment-unit:v1:…`, a
        #    FIFTH id space that no other part could meet -- a click on a trend point and a
        #    click on the same wafer's map cell were different strings, so the maps never
        #    followed the trend. The same builder the map and the candidate list already use
        #    produces this, so the two now collide on purpose.
        # ⚠️ `mark_key` stays until every reader carries the pair (`MARKING_CONTRACT` §10.4):
        #    the reading side moving first is what blanked the maps this morning.
        "node_id": ledger_explorer.entity_id(subject_type, keys),
        "keys": keys,
        "context": {"role": CONTEXT_ROLE, "bonding_leg": bonding_leg},
        "aggregation": {"kind": "void_by_experiment_unit", "finding_kind": "void"},
        "mark_key": encode_mark(wafer, bonding_leg),
    }
