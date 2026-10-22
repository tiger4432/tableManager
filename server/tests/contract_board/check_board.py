"""Contract board invariants for one board - run from the worktree's server folder with the launcher's env (the scratch
schema pinned). Asks the PRODUCT's own judges (cell_layer.shells, models.sql_type_of) - not a second spelling.
usage: check_board.py <source table> <target table>  -> one JSON line «BOARD {...}»"""
import json
import sys

from sqlalchemy import text

import paths  # noqa: F401 - the data root from the env
from database import crud, models
from database.database import SessionLocal, engine
from chain import cell_layer

SRC, DST = sys.argv[1:3]
cfg = crud.load_table_config_or_raise() if hasattr(crud, "load_table_config_or_raise") else {}
crud.TABLE_CONFIG.clear()
crud.TABLE_CONFIG.update(cfg)
models.init_dynamic_models(cfg)

schema = engine.connect().execute(text("SELECT current_schema()")).scalar()
db = SessionLocal()
out = {"schema": schema}
try:
    def rows(table):
        cols = list((cfg.get(table) or {}).get("column_types") or {})
        got = db.execute(text('SELECT row_id, business_key_val, %s FROM "%s"' % (", ".join('"%s"' % c for c in cols),
                                                                                    table))).fetchall()
        return cols, got

    scols, srows = rows(SRC)
    _by = lambda t: tuple((v is None, v or "") for v in t)    # a blank cell next to a text one
    dcols, drows = rows(DST)
    # what the target should hold for a frame-through rule: one row per source row, the same cells
    want = sorted([tuple(None if crud.is_blank_value(v) else str(v) for v in r[2:]) for r in srows], key=_by)
    have = sorted([tuple(None if crud.is_blank_value(v) else str(v) for v in r[2:]) for r in drows], key=_by)
    out["src_rows"], out["dst_rows"] = len(srows), len(drows)
    out["dst_equals_src"] = want == have
    out["missing_in_dst"] = [w for w in want if w not in have][:5]
    out["extra_in_dst"] = [h for h in have if h not in want][:5]
    keys = [r[1] for r in drows]
    out["same_key_rows"] = len(keys) - len(set(keys))
    out["shells"] = len(cell_layer.shells(db, DST, [r[0] for r in drows]))
    layer = db.execute(text("SELECT row_id, column_name, source_name FROM cell_sources WHERE table_name = :t"),
                       {"t": DST}).fetchall()
    live = {r[0] for r in drows}
    out["layers"] = len(layer)
    out["orphan_layers"] = sum(1 for r in layer if r[0] not in live)
    per_cell = {}
    for row_id, column, source in layer:
        per_cell[(row_id, column, source)] = per_cell.get((row_id, column, source), 0) + 1
    out["cells_with_two_layers_of_one_source"] = sum(1 for n in per_cell.values() if n > 1)
    out["outbox_waiting"] = db.execute(text("SELECT count(*) FROM database_outbox WHERE NOT processed_chain")).scalar()
    out["outbox_failed"] = db.execute(text("SELECT count(*) FROM database_outbox WHERE status NOT IN "
                                           "('SUCCESS', 'PENDING', 'PROCESSING')")).scalar()
    import event_constants
    from database.models import DatabaseOutbox as ob
    out["set_aside"] = db.query(ob.id).filter(ob.payload[event_constants.CANCEL_MARK].as_string().isnot(None)).count()
    # declared type = the database column's type (models.sql_type_of is the one answer)
    mism = []
    for table in (SRC, DST):
        for column, declared in ((cfg.get(table) or {}).get("column_types") or {}).items():
            pg = db.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema = current_schema() "
                                 "AND table_name = :t AND column_name = :c"), {"t": table, "c": column}).scalar()
            expect = {"number": "double precision", "datetime": "timestamp with time zone"}.get(declared,
                                                                                               "character varying")
            if pg != expect:
                mism.append("%s.%s declared %s, column %s" % (table, column, declared, pg))
    out["type_mismatch"] = mism
    out["snapshot"] = {"dst": have, "layers_by_source": sorted({s for _r, _c, s in layer}),
                       "layer_count": len(layer)}
finally:
    db.close()
print("BOARD " + json.dumps(out, ensure_ascii=False, default=str))
