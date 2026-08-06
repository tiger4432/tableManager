"""How many CONFIRMED maps would the valid-die origin box move, and by how much. READ-ONLY.

    conda run -n assy_manager python server/scripts/confirmed_origin_box_delta.py

WHY THIS EXISTS
---------------
Until 2026-08-06 `map_alignment.start_from_placement` computed the confirmed origin on the
wafer CIRCLE box unconditionally, while `client2/src/map_editor.js:1942-2006` switches to the
valid-die MASK box whenever the map's `valid_die_ref` resolves. Confirmation writes that
reference (`apply_valid_die_ref`), so it turns the editor's mask branch on for exactly the maps
it just wrote an origin for -- and the two sides then disagree about which box the stored
`grid_start_x/y` is relative to.

The repair is in place. This script answers the OTHER question: what does it mean for rows that
were confirmed BEFORE it. It rewrites nothing and decides nothing; the ruling on whether to
recompute those rows or leave them alone is the lead PM's.

WHAT IT MEASURES, AND WHY IT NEEDS NO ALIGNMENT REPLAY
-----------------------------------------------------
The delta between the two computations does not depend on the anchor pair. The box enters
`make_frame_transform` as a pure translation, and the anchor enters as a DIFFERENCE, so the
translation cancels out of `tf(anchor_src) - anchor_ref` and what is left is a constant. That
is not assumed here: each row is measured with two different dummy anchor pairs and the two
answers are required to agree, otherwise the row is reported as `ANCHOR-DEPENDENT` rather than
counted.

⚠️ THE POPULATION IS `frame_confirmed_from` AND A RESOLVABLE `valid_die_ref` TOGETHER. A
   confirmed row with no reference still draws from the circle in the editor, so its stored
   origin is right and it is not at risk. A row that declares a reference which REFUSES (the
   pinned-table rule, MAP_EDITOR_SPEC section 5.7-a) also draws from the circle. Both are
   reported separately rather than folded into a zero.
⚠️ `--counterfactual` additionally prints, for confirmed rows with NO reference, what the delta
   WOULD be if the confirmation that wrote them had also written its reference. That is not a
   defect count -- those rows are correct as they stand -- it is the magnitude to expect once
   re-confirmation starts attaching references.
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import map_alignment as ma          # noqa: E402
import map_meta_registrar           # noqa: E402
import map_overlay                  # noqa: E402
from database.database import SessionLocal, SQLALCHEMY_DATABASE_URL  # noqa: E402
from database import crud, models   # noqa: E402

#: Two anchor pairs, only to prove the delta does not depend on them (see the module docstring).
PROBE_ANCHORS = (((0, 0), (0, 0)), ((7, 3), (-2, 11)))


def _grid_metadata(row):
    gm = getattr(row, "grid_metadata", None)
    if isinstance(gm, str):
        try:
            gm = json.loads(gm)
        except ValueError:
            return None
    return gm if isinstance(gm, dict) else None


def _delta(meta, ref_meta, box):
    """(dx, dy) the new box moves this row's confirmed origin by, or a string reason."""
    seen = None
    for a_src, a_ref in PROBE_ANCHORS:
        old = ma.start_from_placement(meta, ref_meta, a_src, a_ref)
        new = ma.start_from_placement(meta, ref_meta, a_src, a_ref, source_box=box)
        if old is None or new is None:
            return "refused (geometry not computable / dims differ)"
        d = (new[0] - old[0], new[1] - old[1])
        if seen is None:
            seen = d
        elif seen != d:
            return "ANCHOR-DEPENDENT (%s vs %s)" % (seen, d)
    return seen


def main(counterfactual=False):
    models.init_dynamic_models(crud.TABLE_CONFIG)
    print("database: %s" % SQLALCHEMY_DATABASE_URL.split("@")[-1])
    db = SessionLocal()
    try:
        model = models.DYNAMIC_TABLES.get(map_meta_registrar.META_TABLE)
        if model is None:
            print("'%s' is not a declared table on this box - nothing to assess"
                  % map_meta_registrar.META_TABLE)
            return
        metas = {}
        for row in db.query(model).all():
            gm = _grid_metadata(row)
            if gm is not None:
                metas[(str(row.target_table), str(row.map_id))] = gm

        confirmed = {k: m for k, m in metas.items()
                     if m.get(map_overlay.FRAME_CONFIRMED_KEY)}
        print("wafer_map_metadata rows        : %d" % len(metas))
        print("  carrying a frame confirmation: %d" % len(confirmed))

        cfg = map_overlay.load_overlay_config()
        cells_cache, deltas, skipped, moved_rows = {}, Counter(), Counter(), []

        def _cells(table, map_id):
            key = (table, map_id)
            if key not in cells_cache:
                try:
                    cells, _v, trunc, _k = ma._cells_of(
                        db, cfg, table, map_id, map_overlay.MAX_VALID_DIE_CELLS)
                    cells_cache[key] = None if trunc else cells
                except Exception as e:                       # noqa: BLE001
                    print("   ! cells unreadable for %s/%s: %s" % (table, map_id, e))
                    cells_cache[key] = None
            return cells_cache[key]

        for (table, map_id), meta in sorted(confirmed.items()):
            ref, err = map_overlay.parse_valid_die_ref(meta, default_table=table)
            if err is not None:
                skipped["valid_die_ref present but unreadable"] += 1
                continue
            if ref is None:
                skipped["no valid_die_ref - the editor draws this one from the circle"] += 1
                if not counterfactual:
                    continue
                mark = meta.get(map_overlay.FRAME_CONFIRMED_KEY) or {}
                ref = {"table": mark.get("table"), "map_id": mark.get("map_id")}
                if not ref.get("table") or not ref.get("map_id"):
                    continue
            ref_meta = metas.get((ref["table"], ref["map_id"]))
            if ref_meta is None:
                skipped["reference has no wafer_map_metadata row"] += 1
                continue
            cells = _cells(ref["table"], ref["map_id"])
            if not cells:
                skipped["reference resolves to no cells (or exceeds the cap)"] += 1
                continue
            mask = map_overlay.die_mask_from_reference(ref_meta, cells)
            box = map_overlay.origin_box(meta, mask) if mask else None
            if box is None:
                skipped["no grid meta / mask does not project"] += 1
                continue
            d = _delta(meta, ref_meta, box)
            deltas[d] += 1
            if d != (0, 0):
                moved_rows.append((table, map_id, ref["table"], ref["map_id"], d,
                                   map_overlay.origin_box(meta, None), box, len(cells)))

        print()
        print("== delta distribution (new origin - old origin) ==")
        if not deltas:
            print("   (no confirmed row was assessable)")
        for d, n in sorted(deltas.items(), key=lambda kv: (-kv[1], str(kv[0]))):
            print("   %-32s %d" % (d, n))
        print("   assessed %d, would move %d"
              % (sum(deltas.values()), sum(n for d, n in deltas.items() if d != (0, 0))))
        if skipped:
            print()
            print("== not at risk / not assessable ==")
            for k, n in skipped.most_common():
                print("   %-58s %d" % (k, n))
        if moved_rows:
            print()
            print("== rows whose origin moves ==")
            for t, m, rt, rk, d, cb, mb, nc in moved_rows:
                print("   %s/%s <- %s/%s (%d cells)  delta=%s  circle=%s mask=%s"
                      % (t, m, rt, rk, nc, d, cb, mb))
    finally:
        db.close()


if __name__ == "__main__":
    main(counterfactual="--counterfactual" in sys.argv)
