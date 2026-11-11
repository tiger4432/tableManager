# -*- coding: utf-8 -*-
"""Owner 11-11 «리포트는 컴포짓맵 왜 여러개라고 안띄움? 마지막 마킹 시간해소 띄우라고» · «불량별 이미지는 leg별로 나눠서해».

`keys` latest on a column beyond the wafer key: of a table's rows of one wafer that differ only there, the latest -
every read through `_matched` (summary, info, picture row, conditions, images) the same answer (lead 11-11). Not
written, the rows stand as before (a picture cell «2 rows»). `images.by`: a defect's pictures one gallery each value."""
import pytest

from database import crud, models, schemas
from test_every_declared_kind_runs_and_leaves_rows import fixture_db, fixture_reported  # noqa: F401

MARKED = {"kinds_mark": {"composite_key_source": ["wafer", "leg", "item", "marked"],
                         "column_types": {"wafer": "string", "leg": "string", "item": "string", "marked": "string",
                                          "fail": "number", "total": "number", "img": "string", "value": "string"}}}
ROWS = [{"wafer": "W1", "leg": "L1", "item": "particle", "marked": "2026-11-01 10:00:00", "fail": 1, "total": 100,
         "img": "old.png", "value": "old"},
        {"wafer": "W1", "leg": "L1", "item": "particle", "marked": "2026-11-02 09:00:00", "fail": 5, "total": 100,
         "img": "new.png", "value": "new"},
        {"wafer": "W1", "leg": "L2", "item": "particle", "marked": "2026-11-01 10:00:00", "fail": 2, "total": 100,
         "img": "l2.png", "value": "l2"}]
L1, L2 = ("W1", "L1"), ("W1", "L2")


@pytest.fixture(name="marked")
def fixture_marked(db, reported):
    from conftest import retire_dynamic_model

    models.init_dynamic_models(MARKED)
    crud.TABLE_CONFIG.update(MARKED)
    models.DYNAMIC_TABLES["kinds_mark"].__table__.create(bind=db.get_bind())
    crud.apply_batch_updates(db, "kinds_mark", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="kinds") for row in ROWS]))
    db.commit()
    try:
        yield reported[0]["params"]
    finally:
        db.rollback()
        models.DYNAMIC_TABLES["kinds_mark"].__table__.drop(bind=db.get_bind())
        crud.TABLE_CONFIG.pop("kinds_mark", None)
        retire_dynamic_model("kinds_mark")


def _spec(params, latest, by=None):
    from chain import report_shape

    on = ["wafer", "leg", "marked"]
    spec = dict(params,
                summary={"table": "kinds_mark", "wafer": on, "item": "item", "fail": "fail", "total": "total"},
                info=[{"table": "kinds_mark", "wafer": on, "item": "item", "value": "value"}],
                picture_rows=[{"label": "Composite", "table": "kinds_mark", "wafer": on, "image": "img"}],
                conditions={"table": "kinds_mark", "wafer": on, "name": "item", "value": "value"},
                images=dict({"table": "kinds_mark", "wafer": on, "item": "item", "image": "img"},
                            **({"by": by} if by else {})),
                **({"keys": {"marked": ["latest"]}} if latest else {}))
    assert report_shape.refusal(spec, "kinds_rep", "kinds_rep") is None
    return spec


def _read(db, spec):
    from chain import report_reads

    report = report_reads.Report(db, spec, None, only={"wafer": "W1"})
    kept, report_reads._picture = report_reads._picture, (lambda ref, px: {"src": ref})
    try:
        summary, _ = report._summary([L1, L2])
        info, _ = report._info([[L1], [L2]])
        [(_name, cells)], _ = report._pictures([[L1], [L2]])
        report._long_conditions([L1, L2])
        images = report.images()["html"]["particle"]
    finally:
        report_reads._picture = kept
    return {"summary": (summary.get((L1, "particle")) or {}).get("fail"),
            "info": [cell["text"] for cell in dict(info)["particle"]],
            "picture": [cell.get("src") or cell.get("refused") for cell in cells],
            "conditions": report.wafers[L1]["conditions"].get("particle"),
            "images": sorted(p["src"] for p in images)}


def test_a_latest_key_beyond_the_wafer_leaves_each_read_the_latest_row(db, marked):
    assert _read(db, _spec(marked, latest=True)) == {
        "summary": 5, "info": ["new", "l2"], "picture": ["new.png", "l2.png"], "conditions": "new",
        "images": ["l2.png", "new.png"]}


def test_not_written_the_rows_stand_as_before(db, marked):
    assert _read(db, _spec(marked, latest=False)) == {
        "summary": None, "info": ["", "l2"], "picture": ["2 Composite rows for wafer W1 · leg L1", "l2.png"],
        "conditions": "old / new", "images": ["l2.png"]}   # L1 twice in the summary: no defect occurred there


def test_images_by_a_key_column_is_a_gallery_each_value(db, marked):
    from chain import report_html, report_reads, report_shape

    spec = _spec(marked, latest=True, by=["leg"])
    report = report_reads.Report(db, spec, None, only={"wafer": "W1"})
    kept, report_reads._picture = report_reads._picture, (lambda ref, px: {"src": ref})
    try:
        report.images()
    finally:
        report_reads._picture = kept
    assert [(p["by"], p["src"]) for p in report.embedded["particle"]] == [("L1", "new.png"), ("L2", "l2.png")]
    page = report_html._images(report.embedded, spec)
    assert page.index("<h3>particle</h3>") < page.index("<h4>L1</h4>") < page.index("new.png") \
        < page.index("<h4>L2</h4>") < page.index("l2.png")
    assert "<h4>" not in report_html._images({"particle": [{"src": "a.png", "wafer": "W1"}]}, spec), "undeclared: one"
    said = report_shape.refusal(dict(spec, images=dict(spec["images"], by=["img"])), "kinds_rep", "kinds_rep")
    assert said and said.startswith("derive.report.images.by is a list of the image table's key columns"), said
