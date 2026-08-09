"""Read-only fuzzy occupancy probe for core-frame alignment.

This is deliberately not a chain mapper and writes no frame.  It proves the
acceptance evidence for partial/dumped core observations before any automatic
confirmation contract is enabled.

Usage:
    python server/scripts/probe_core_occupancy_alignment.py
    python server/scripts/probe_core_occupancy_alignment.py --job SYN-CORE-CLUSTER-P1-R0-HFD7A2F8D
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

RULE = "core_frame_review"
SOURCE_TABLE = "dt_core_view"
REFERENCE_TABLE = "core_wafer_map"
DEFAULT_MIN_HIT_RATIO = 0.85
DEFAULT_MIN_MARGIN_DIES = 5


def judge_occupancy(payload: dict, *, min_hit_ratio=DEFAULT_MIN_HIT_RATIO,
                    min_margin_dies=DEFAULT_MIN_MARGIN_DIES) -> dict:
    """Rank partial-map candidates without requiring a perfect match.

    ``agreement`` is occupied-cell overlap. A source dump has fewer observed
    cells, so it reduces evidence but does not become a mismatch by itself.
    A missing reference die lowers the hit ratio. Both remain reviewable
    through the reported numbers; this function only proposes, never writes.
    """
    source_count = int((payload.get("sources") or {}).get("cell_count") or 0)
    candidates = [c for c in (payload.get("candidates") or [])
                  if c.get("state") == "scored" and isinstance(c.get("agreement"), (int, float))]
    ranked = sorted(candidates, key=lambda c: (-c["agreement"], str(c.get("frame", ""))))
    if source_count <= 0 or not ranked:
        return {"state": "no_evidence", "source_count": source_count, "winner": None}
    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    hit_ratio = float(best["agreement"]) / source_count
    margin = int(best["agreement"] - (second["agreement"] if second else 0))
    accepted = hit_ratio >= min_hit_ratio and margin >= min_margin_dies
    return {
        "state": "proposed" if accepted else "review",
        "source_count": source_count,
        "winner": best.get("frame"),
        "reference_shift": best.get("shift"),
        "hits": int(best["agreement"]),
        "hit_ratio": hit_ratio,
        "margin": margin,
        "runner_up": second.get("frame") if second else None,
        "runner_up_hits": int(second["agreement"]) if second else None,
        "min_hit_ratio": min_hit_ratio,
        "min_margin_dies": min_margin_dies,
    }


def core_reference_for_job(db, job_id: str) -> str | None:
    """Resolve exactly one physical core-map identity from one observation job."""
    from database import models

    view = models.DYNAMIC_TABLES[SOURCE_TABLE]
    rows = db.query(view.core_lot, view.core_slot).filter(view.dt_job == job_id).distinct().all()
    identities = {(str(lot).strip(), str(slot).strip()) for lot, slot in rows
                  if lot is not None and slot is not None and str(lot).strip() and str(slot).strip()}
    if len(identities) != 1:
        return None
    lot, slot = next(iter(identities))
    return "%s:%s_%s" % (REFERENCE_TABLE, lot, slot)


def probe_job(db, job_id: str) -> dict:
    import alignment_view_service

    reference = core_reference_for_job(db, job_id)
    if reference is None:
        return {"job_id": job_id, "state": "reference_unresolved",
                "reason": "one physical core wafer is required"}
    payload = alignment_view_service.resolve_alignment_view(
        db, RULE, {"dt_job": job_id}, SOURCE_TABLE, reference_spec=reference,
        include_cells=False, x_col="core_x", y_col="core_y", value_col="")
    verdict = judge_occupancy(payload)
    return {"job_id": job_id, "reference": reference, **verdict}


def main():
    parser = argparse.ArgumentParser(description="Read-only fuzzy core occupancy alignment probe.")
    parser.add_argument("--job", action="append", default=[], help="one dt_job (repeatable)")
    args = parser.parse_args()

    from database.database import SessionLocal
    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        if args.job:
            jobs = args.job
        else:
            view = models.DYNAMIC_TABLES[SOURCE_TABLE]
            jobs = [row[0] for row in db.query(view.dt_job).filter(
                view.dt_job.like("SYN-CORE-CLUSTER-%")).distinct().order_by(view.dt_job).all()]
        for job_id in jobs:
            print(probe_job(db, job_id))
    finally:
        db.close()


if __name__ == "__main__":
    main()
