# -*- coding: utf-8 -*-
"""images.first_layer (owner 11-10 «모든 층 보여 주고 디폴트를 해당 층으로 고정»): the image table's column naming the
layer a chip's defect was found on - every layer still shown, the chip's strip opens there: first in the file and
marked, where the folding script starts. «1,2» its first; blank, or no picture of that layer, the first layer."""
import re

from chain import report_html, report_reads, report_shape
from database import crud, models, schemas

TABLES = {"fl_sum": {"composite_key_source": ["wafer", "item"],
                     "column_types": {"wafer": "string", "item": "string", "fail": "number", "total": "number"}},
          "fl_img": {"composite_key_source": ["wafer", "x", "y", "layer"],
                     "column_types": {"wafer": "string", "x": "number", "y": "number", "layer": "string",
                                      "img": "string", "defects": "string", "found": "string"}},
          "fl_rep": {"business_key": "wafer", "composite_key_source": ["wafer"],
                     "column_types": {"wafer": "string", "fl": "string"}}}
SPEC = {"wafer": {"table": "fl_sum", "key": ["wafer"]},
        "keys": {"wafer": ["unit"], "x": [], "y": [], "layer": ["fold"]},
        "summary": {"table": "fl_sum", "wafer": ["wafer"], "item": "item", "fail": "fail", "total": "total"},
        "images": {"table": "fl_img", "wafer": ["wafer", "x", "y", "layer"], "item": "defects", "image": "img",
                   "first_layer": "found", "per_item": 5},
        "control": {"recent": {"evaluations": 5}},
        "results": {"file": "fl"}}


def _strips(db, monkeypatch, found):
    """Each chip's strip as the file draws it with no script: [(layer, marked)] - chips (1,1), (1,2), (1,3) with
    layers L1 L2 L3, `found` the found column of chip (1,1); (1,2) names a layer it has no picture of, (1,3) none."""
    from conftest import retire_dynamic_model

    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.create(bind=db.get_bind())
    try:
        said = {1: found, 2: "L9", 3: None}
        rows = {"fl_sum": [{"wafer": "W1", "item": "void", "fail": 3, "total": 100}],
                "fl_img": [{"wafer": "W1", "x": 1, "y": y, "layer": layer, "img": "%d%s" % (y, layer),
                            "defects": "void", "found": said[y]} for y in (1, 2, 3) for layer in ("L1", "L2", "L3")]}
        for table, written in rows.items():
            crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="first") for row in written]))
        db.commit()
        assert report_shape.refusal(SPEC, "fl_rep", "fl_rep") is None
        monkeypatch.setattr(report_reads, "_picture", lambda ref, px: {"src": "data:image/png;base64," + ref})
        embedded = report_reads.Report(db, SPEC, None, only={"wafer": "W1"}).images()["html"]
        page = report_html.page("W1 report", "R", {"layout": [{"kind": "image"}]}, {}, embedded, {})
        assert 'class="stack"' in page and "<script>" in page
        drawn = re.sub(r"<script>.*?</script>", "", page, flags=re.S)
        return [re.findall(r'<figure( class="first")?><img[^>]*data-layer="(L\d)"', strip)
                for strip in re.findall(r'<div class="strip">(.*?)</div>', drawn, flags=re.S)]
    finally:
        db.rollback()
        for name in TABLES:
            models.DYNAMIC_TABLES[name].__table__.drop(bind=db.get_bind())
            crud.TABLE_CONFIG.pop(name, None)
            retire_dynamic_model(name)


def test_the_strip_opens_on_the_found_layer_marked_the_wheel_order_kept(db_session, monkeypatch):
    first, absent, blank = _strips(db_session, monkeypatch, "L2")
    assert first == [(' class="first"', "L2"), ("", "L3"), ("", "L1")], \
        "L2 first and marked; the wheel's order L2 L3 L1 - turning back from L2 is L1"
    assert absent == blank == [("", "L1"), ("", "L2"), ("", "L3")], "no picture of that layer, or blank: as before"
    assert "i=0" in report_html.STACK_SCRIPT, "the folding script starts on the strip's first - L2 here"


def test_of_several_layers_named_the_first_opens(db_session, monkeypatch):
    first, _absent, _blank = _strips(db_session, monkeypatch, "L3,L2")
    assert first[0] == (' class="first"', "L3"), first


def test_a_first_layer_column_the_image_table_has_not_is_refused(db_session):
    from conftest import retire_dynamic_model

    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    try:
        said = report_shape.refusal(dict(SPEC, images=dict(SPEC["images"], first_layer="nope")), "fl_rep", "fl_rep")
        assert "images.first_layer 'nope' is not a column of 'fl_img'" in said, said
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
            retire_dynamic_model(name)
