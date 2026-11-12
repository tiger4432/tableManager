# -*- coding: utf-8 -*-
"""Owner 11-10 (via lead): a summary column stood, its Composite cell blank, no reason - the picture row's key spelled
apart from the wafer's never paired. A picture cell with no picture says why, and a row not there names the picture
table's nearest key so the spelling apart shows."""
from database import crud, models, schemas
from test_every_declared_kind_runs_and_leaves_rows import fixture_db, fixture_reported  # noqa: F401


def test_a_picture_cell_with_no_picture_says_why(db, reported):
    from chain import report_html, report_reads, report_shape
    from conftest import retire_dynamic_model

    more = {"kinds_comp": {"composite_key_source": ["wafer", "shot", "leg"],
                           "column_types": {"wafer": "string", "shot": "string", "leg": "string", "img": "string"}}}
    models.init_dynamic_models(more)
    crud.TABLE_CONFIG.update(more)
    models.DYNAMIC_TABLES["kinds_comp"].__table__.create(bind=db.get_bind())
    try:
        rows = [{"wafer": "W1", "shot": "1", "leg": "L1", "img": "w1.png"},
                {"wafer": "W1", "shot": "1", "leg": "L2_", "img": "w1b.png"},       # the leg spelled apart
                {"wafer": "W3", "shot": "1", "leg": "L1", "img": "a.png"},
                {"wafer": "W3", "shot": "2", "leg": "L1", "img": "b.png"},         # two rows for one wafer
                {"wafer": "W4", "shot": "1", "leg": "L1", "img": ""}]             # its picture blank
        crud.apply_batch_updates(db, "kinds_comp", schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="kinds") for row in rows]))
        db.commit()
        spec = dict(reported[0]["params"], wafer={"table": "kinds_sum", "key": ["wafer", "leg"]},
                    picture_rows=[{"label": "Composite", "table": "kinds_comp", "wafer": ["wafer", "shot", "leg"],
                                   "image": "img"}])
        spec.pop("images", None)
        assert report_shape.refusal(spec, "kinds_rep", "kinds_rep") is None
        report = report_reads.Report(db, spec, None, only={"wafer": "W1"})
        report_reads._picture, kept = (lambda ref, px: {"src": ref}), report_reads._picture
        try:
            [(name, cells)], left_out = report._pictures(
                [[("W1", "L1")], [("W1", "L2")], [("W3", "L1")], [("W4", "L1")], [("W5", "L1")], []])
        finally:
            report_reads._picture = kept
        assert name == "Composite" and cells[0] == {"src": "w1.png"} and cells[5] == {"text": "—"}
        said = [cell.get("refused") for cell in cells[1:5]]
        assert said == ["no Composite row for wafer W1 · leg L2 - nearest: wafer W1 · leg L2_",
                        "2 Composite rows for wafer W3 · leg L1",
                        "Composite row of wafer W4 · leg L1 has no img",
                        "no Composite row for wafer W5 · leg L1"], said
        assert left_out == ["wafer W3 · leg L1 Composite"]
        assert said[0] in report_html._value(cells[1], name, "W1 · L2"), "the file draws the reason in the cell"
    finally:
        db.rollback()
        models.DYNAMIC_TABLES["kinds_comp"].__table__.drop(bind=db.get_bind())
        crud.TABLE_CONFIG.pop("kinds_comp", None)
        retire_dynamic_model("kinds_comp")
