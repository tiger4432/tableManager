# -*- coding: utf-8 -*-
"""Owner 10-22 (lead cd4eb98d0 · e53847114): the six reads the AI report's model calls - every table and column from
the report declaration, every read through the grid read path. Seed: evaluation E1 (W1 · W2 · W3, measured in that
order but written out of it), evaluation E0 (W0) in compare set «baseline», and the owner's summary table - a row a
wafer and item with its fail and total chips and a rate (owner 10-22 night: the product reads it, never makes it).

  conditions   condition value -> wafers, and a keyword's wafers
  yield_by     rows = the declared items, columns = this evaluation's wafers by time, cell «x% (F/N)» read off the
               summary row; a column of several wafers adds their F and N
  rate         a declared rate is what x is (over rate_scale) - a rate alone says «x%» and cannot be added
  pareto       items by fail chips with the cumulative share
  trend        an item's share in time order
  images       only this evaluation's wafers, only an item that occurred there, embedded and not told
  compare      a compare set's wafers become a second group of columns
  refused      a wafer not in the report · a condition that is not one · a read past the row cap ·
               a wafer and item two summary rows say
"""
import json

import pytest

from conftest import retire_dynamic_model
from database import crud, models

TABLES = {
    "rr_wafer": {"business_key": "wafer_id", "composite_key_source": ["wafer_id"],
                 "column_types": {"wafer_id": "string", "lot_id": "string", "eval_id": "string",
                                  "measured_at": "string", "split": "string"}},
    "rr_summary": {"composite_key_source": ["wafer_id", "defect_item", "n"],
                   "column_types": {"wafer_id": "string", "defect_item": "string", "n": "string",
                                    "fail_chips": "number", "total_chips": "number", "loss_pct": "number"}},
    "rr_image": {"business_key": "image_id", "composite_key_source": ["image_id"],
                 "column_types": {"image_id": "string", "wafer_id": "string", "defect_item": "string",
                                  "image_path": "string"}},
    "rr_set": {"composite_key_source": ["set_name", "member"],
               "column_types": {"set_name": "string", "member": "string", "kind": "string"}},
    "rr_cond": {"composite_key_source": ["wafer_id", "cname", "step"],
                "column_types": {"wafer_id": "string", "cname": "string", "step": "string", "cvalue": "string"}},
}
WAFERS = [("W2", "L1", "E1", "2026-10-02", "A"), ("W1", "L1", "E1", "2026-10-01", "A"),
          ("W3", "L2", "E1", "2026-10-03", "B"), ("W0", "L0", "E0", "2026-09-01", "A"),
          # recent evaluations before E1's latest wafer (10-03): E3 · E2 within 60 days; E9 too old; E4 after it
          ("W5", "L5", "E2", "2026-09-20", "A"), ("W6", "L5", "E2", "2026-09-19", "B"),
          ("W7", "L6", "E3", "2026-09-25", "A"), ("W8", "L7", "E4", "2026-10-10", "A"),
          ("W9", "L8", "E9", "2026-05-01", "A")]
#: wafer, item, F, N, the summary's own rate in percent - W1 particle's 2.5 is not 3/100, so a cell that says 2.5 read it
SUMMARY = [("W1", "particle", 3, 100, 2.5), ("W1", "scratch", 1, 100, 1.0), ("W2", "particle", 10, 200, 5.0),
           ("W2", "scratch", 0, 200, 0.0), ("W3", "particle", 0, 400, 0.0), ("W3", "scratch", 40, 400, 10.0),
           ("W0", "particle", 50, 100, 50.0), ("W5", "particle", 2, 100, 2.0), ("W6", "particle", 4, 100, 4.0),
           ("W7", "particle", 6, 100, 6.0)]
SPEC = {
    "wafer": {"table": "rr_wafer", "key": "wafer_id", "time": "measured_at", "lot": "lot_id", "evaluation": "eval_id",
              "conditions": ["split"]},
    "summary": {"table": "rr_summary", "wafer": "wafer_id", "item": "defect_item", "fail": "fail_chips",
                "total": "total_chips"},
    "images": {"table": "rr_image", "wafer": "wafer_id", "item": "defect_item", "image": "image_path", "per_item": 1,
               "px": 32},
    "sets": {"table": "rr_set", "name": "set_name", "member": "member", "kind": "kind", "default": ["baseline"],
             "kinds": {"evaluation": "EV", "lot": "LT"}},
    "rows": ["particle", "scratch"], "digits": 1,
    "control": {"recent": {"days": 60}, "max_wafers": 2, "max_evaluations": 2},
}


def _with_summary(**cells):
    spec = json.loads(json.dumps(SPEC))
    spec["summary"] = dict({"table": "rr_summary", "wafer": "wafer_id", "item": "defect_item"}, **cells)
    return spec


@pytest.fixture
def report(db_session, tmp_path, monkeypatch):
    import image_sources
    from chain import report_reads

    models.init_dynamic_models(TABLES)
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        models.DYNAMIC_TABLES[name].__table__.create(bind=db_session.get_bind())
    m = models.DYNAMIC_TABLES
    for n, (w, lot, ev, at, split) in enumerate(WAFERS):
        db_session.add(m["rr_wafer"](row_id="w%d" % n, wafer_id=w, lot_id=lot, eval_id=ev, measured_at=at,
                                     split=split))
    for n, (w, item, fail, total, rate) in enumerate(SUMMARY):
        db_session.add(m["rr_summary"](row_id="d%d" % n, wafer_id=w, defect_item=item, n="1", fail_chips=fail,
                                       total_chips=total, loss_pct=rate))
    (tmp_path / "pics").mkdir()
    for n, (w, item) in enumerate([("W1", "particle"), ("W1", "particle"), ("W2", "scratch"), ("W0", "particle")]):
        (tmp_path / "pics" / ("p%d.png" % n)).write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([n]))
        db_session.add(m["rr_image"](row_id="i%d" % n, image_id="i%d" % n, wafer_id=w, defect_item=item,
                                     image_path="pics:p%d.png" % n))
    db_session.add(m["rr_set"](row_id="s0", set_name="baseline", member="E0", kind="EV"))
    db_session.add(m["rr_set"](row_id="s1", set_name="keylots", member="L0", kind="LT"))
    db_session.add(m["rr_set"](row_id="s2", set_name="keylots", member="L9", kind="eval"))
    db_session.commit()
    monkeypatch.setattr(image_sources, "load_sources", lambda path=None: {
        "pics": {"kind": "folder", "root": str(tmp_path / "pics")}})
    monkeypatch.setattr(image_sources, "shrink", lambda answer, px: answer)
    try:
        yield report_reads.Report(db_session, json.loads(json.dumps(SPEC)), "E1")
    finally:
        db_session.rollback()
        for name in TABLES:
            models.DYNAMIC_TABLES[name].__table__.drop(bind=db_session.get_bind())
            retire_dynamic_model(name)


def _texts(rows):
    """A table's rows as the file shows them - each cell's text (a cell also carries its share, F and N)."""
    return [(item, [cell["text"] for cell in cells]) for item, cells in rows]


def _by_column(table, cells):
    """A row's cell texts by their column - (group, label): the columns stand by date, not by group (owner 10-24)."""
    return dict(zip([(name, col) for name, cols in table["groups"] for col in cols], [cell["text"] for cell in cells]))


def test_this_evaluations_wafers_are_in_time_order(report):
    assert report.groups == {"E1": [("W1",), ("W2",), ("W3",)]}


def test_conditions_fold_to_wafer_counts_and_a_keyword_picks_wafers(report):
    assert report.conditions()["context"] == "3 wafers in E1\nsplit: A 2, B 1"
    found = report.conditions("b")
    assert found["wafers"] == [("W3",)] and "W3" in found["context"]


def test_the_summary_table_is_items_down_and_wafers_across_by_time(report):
    answer = report.yield_by()
    assert answer["html"]["groups"] == [("E1", ["wafer_id W1", "wafer_id W2", "wafer_id W3"])]
    assert _texts(answer["html"]["rows"]) == [
        ("particle", ["3.0% (3/100)", "5.0% (10/200)", "0.0% (0/400)"]),
        ("scratch", ["1.0% (1/100)", "0.0% (0/200)", "10.0% (40/400)"])]
    lines = answer["context"].splitlines()
    assert "info split | A | A | B" in lines, "the condition group - its values differ"
    # the model reads the heads the page draws, a line a tier, and whose each column is (owner 10-24)
    assert "wafer_id | W1 | W2 | W3" in lines and lines[0].startswith("time | ")
    assert "group | E1 (this report) | E1 (this report) | E1 (this report)" in lines
    assert "particle | 3.0% (3/100) | 5.0% (10/200) | 0.0% (0/400)" in answer["context"].splitlines()
    by_split = report.yield_by(by="split")["html"]
    assert by_split["groups"] == [("E1", ["A", "B"])]
    assert _texts(by_split["rows"])[0] == ("particle", ["4.3% (13/300)", "0.0% (0/400)"]), "A adds W1's and W2's F and N"
    picked = report.yield_by({"where": {"split": "B"}})["html"]
    assert picked["groups"] == [("E1", ["wafer_id W3"])]


def test_a_declared_rate_is_read_not_made(report, db_session):
    from chain import report_reads

    both = report_reads.Report(db_session, _with_summary(fail="fail_chips", total="total_chips", rate="loss_pct",
                                                         rate_scale=100), "E1")
    assert _texts(both.yield_by()["html"]["rows"])[0] == ("particle", ["2.5% (3/100)", "5.0% (10/200)", "0.0% (0/400)"])
    alone = report_reads.Report(db_session, _with_summary(rate="loss_pct", rate_scale=100), "E1")
    assert _texts(alone.yield_by()["html"]["rows"])[1] == ("scratch", ["1.0%", "0.0%", "10.0%"])
    with pytest.raises(report_reads.ReadRefused, match="several wafers in one column need derive.report.summary.fail"):
        alone.yield_by(by="split")
    with pytest.raises(report_reads.ReadRefused, match="a pareto adds fail chips"):
        alone.pareto()
    assert alone.trend(items=["particle"])["context"] == (
        "particle: first 2.50% last 0.00% least 0.00% most 5.00% over 3 wafers")
    assert list(alone.images()["html"]) == ["particle"], "occurred = a rate above 0 when the summary holds a rate only"


def test_candidates_are_the_recent_evaluations_folded_newest_first(report, db_session):
    from chain import report_reads

    assert report.candidates()["context"].splitlines() == [
        "recent evaluations, newest first (E1 left out):", "E3 · 2026-09-25 · 1 rows · split A 1",
        "E2 · 2026-09-20 · 2 rows · split A 1, B 1", "E0 · 2026-09-01 · 1 rows · split A 1"]
    spec = json.loads(json.dumps(SPEC))
    spec["control"]["recent"] = {"days": 60, "evaluations": 2}
    both = report_reads.Report(db_session, spec, "E1").candidates()["context"].splitlines()
    assert [line.split(" · ")[0] for line in both[1:]] == ["E3", "E2"], "days and evaluations both narrow"
    del spec["control"]
    with pytest.raises(report_reads.ReadRefused, match="candidates need derive.report.control.recent"):
        report_reads.Report(db_session, spec, "E1").candidates()


def test_a_control_group_stands_beside_this_evaluation_in_the_tables(report):
    assert report.compare(evaluations=["E2"])["context"] == "compare E2: 2 wafers (wafer_id W6, wafer_id W5)"
    table = report.yield_by()["html"]
    assert table["groups"] == [("compare E2", ["wafer_id W6", "wafer_id W5"]),
                               ("E1", ["wafer_id W1", "wafer_id W2", "wafer_id W3"])], "columns by date (owner 10-24)"
    particle = _by_column(table, table["rows"][0][1])
    assert (particle[("compare E2", "wafer_id W6")], particle[("compare E2", "wafer_id W5")]) == (
        "4.0% (4/100)", "2.0% (2/100)")
    trend = report.trend(items=["particle"])
    assert trend["html"]["groups"][-1] == ("compare E2", ["wafer_id W6", "wafer_id W5"])
    assert trend["context"].splitlines() == [
        "particle: first 3.00% last 0.00% least 0.00% most 5.00% over 3 wafers",
        "particle [compare E2]: first 4.00% last 2.00% least 2.00% most 4.00% over 2 wafers"]
    report.compare(wafers=["W7"])
    assert [name for name in report.groups] == ["E1", "compare E3"], "a new pick replaces the compare wafers"


@pytest.mark.parametrize("said, refused", [
    ({"evaluations": ["E1"]}, "E1 is this evaluation - compare wafers come from another"),
    ({"evaluations": ["E9"]}, "E9 is not a recent evaluation - candidates() lists them"),
    ({"evaluations": ["E4"]}, "E4 is not a recent evaluation"),
    ({"wafers": ["W1"]}, "W1 is not a wafer of a recent evaluation"),
    ({"evaluations": ["E2", "E3", "E0"]}, "3 evaluations - control.max_evaluations is 2"),
    ({"evaluations": ["E2", "E3"]}, "3 wafers - control.max_wafers is 2; name fewer wafers"),
])
def test_a_control_out_of_range_or_over_its_limits_is_refused(report, said, refused):
    from chain import report_reads

    with pytest.raises(report_reads.ReadRefused, match=refused.replace("(", r"\(").replace(")", r"\)")):
        report.compare(**said)


def test_pareto_and_trend(report):
    assert report.pareto()["html"]["rows"] == [("scratch", "41", "75.9%"), ("particle", "13", "100.0%")]
    assert report.trend(items=["particle"])["context"] == (
        "particle: first 3.00% last 0.00% least 0.00% most 5.00% over 3 wafers")


def test_images_are_this_evaluations_occurred_defects_embedded_not_told(report):
    answer = report.images()
    assert list(answer["html"]) == ["particle"], "W2's scratch image: scratch never occurred on W2"
    [only] = answer["html"]["particle"]
    assert only["wafer"] == "wafer_id W1" and only["src"].startswith("data:image/png;base64,"), "per_item 1"
    assert "base64" not in answer["context"] and answer["context"] == "images picked: particle 1"
    report.compare()
    from chain.report_reads import ReadRefused
    with pytest.raises(ReadRefused, match="images are this evaluation's only - wafer_id W0"):
        report.images(["W0"])


def test_image_kinds_are_paired_with_a_summary_item_by_match(report, db_session, tmp_path):
    """images.match (owner 10-24 «void, signal -> typeA»): the image table's kinds void and signal are particle's
    pictures; dust, paired with nothing and no summary item, shows under itself after a line naming it. Without
    match the three are not pictures of an occurred item - today's same-name rule."""
    m = models.DYNAMIC_TABLES
    for n, kind in enumerate(["void", "signal", "dust"], start=10):
        (tmp_path / "pics" / ("p%d.png" % n)).write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([n]))
        db_session.add(m["rr_image"](row_id="i%d" % n, image_id="i%d" % n, wafer_id="W1", defect_item=kind,
                                     image_path="pics:p%d.png" % n))
    db_session.commit()
    report.spec["images"]["per_item"] = 9
    assert [(item, len(pictures)) for item, pictures in report.images()["html"].items()] == [("particle", 2)]
    report.embedded = {}
    report.spec["images"]["match"] = {"particle": ["void", "signal"]}
    unpaired = "Image kinds no summary item matches (images.match): dust"
    assert [(item, len(pictures)) for item, pictures in report.images()["html"].items()] == [
        ("particle", 4), (unpaired, 0), ("dust", 1)]
    assert list(report.embedded) == ["particle", unpaired, "dust"], "the file draws them in that order"
    report.spec["images"]["match"] = {"particle": "void"}
    assert [item for item in report.images()["html"]] == [
        "particle", "Image kinds no summary item matches (images.match): dust, signal", "dust", "signal"], \
        "a kind written alone is a list of one"
    from chain import report_shape

    refused = report_shape.refusal(dict(SPEC, images=dict(SPEC["images"], match={"particle": 3})))
    assert refused.startswith("derive.report.images.match is {summary item: image kind or [image kinds]}"), refused


def test_a_wafer_row_the_exclude_gate_holds_is_no_unit(report, db_session):
    """derive.report.wafer.exclude (owner 10-24 «무시해야하는 leg 스타일이 있는데»): the chain's row gate, a value with * or
    ? a pattern - a wafer row it holds back is not reported, compared or drawn."""
    from chain import report_reads, report_shape

    spec = json.loads(json.dumps(SPEC))
    spec["wafer"]["exclude"] = [{"wafer_id": ["*3", "W?X"]}]
    gated = report_reads.Report(db_session, spec, "E1")
    assert gated.groups["E1"] == [("W1",), ("W2",)], "W3 matches *3"
    assert [c for _n, cols in gated.yield_by()["html"]["groups"] for c in cols] == ["wafer_id W1", "wafer_id W2"]
    assert report_shape.refusal(dict(spec, wafer=dict(spec["wafer"], exclude=[{"nope": ["*"]}]))) == (
        "derive.report.wafer.exclude 'nope' is not a column of 'rr_wafer' - name one of its columns")


def test_a_condition_item_is_the_wafers_time_when_the_wafer_role_names_none(report, db_session):
    """derive.report.conditions.time_item (owner 10-24: the wafer's time is a conditions row, not a column): that item's
    value is each wafer's time - the order and the day read it; a wafer role naming a time column keeps its own."""
    from chain import report_reads, report_shape

    m = models.DYNAMIC_TABLES
    for n, (w, name, value) in enumerate([("W1", "tkout", "2026-10-05 10:00:00"), ("W2", "tkout ", "2026-10-03 09:00:00"),
                                          ("W1", "recipe", "R1"), ("W2", "recipe", "R2")]):
        db_session.add(m["rr_cond"](row_id="c%d" % n, wafer_id=w, cname=name, cvalue=value))
    db_session.commit()
    spec = json.loads(json.dumps(SPEC))
    spec["conditions"] = {"table": "rr_cond", "wafer": "wafer_id", "name": "cname", "value": "cvalue",
                          "time_item": "tkout"}
    del spec["wafer"]["time"]
    timed = report_reads.Report(db_session, spec, "E1")
    assert [timed.wafers[w]["time"] for w in [("W1",), ("W2",), ("W3",)]] == [
        "2026-10-05 10:00:00", "2026-10-03 09:00:00", None]
    assert timed.groups["E1"] == [("W2",), ("W1",), ("W3",)], "by that time, a wafer without one last"
    rows = [name for name, _cells in timed.yield_by()["html"]["info"]]
    assert [r for r in rows if r.strip() == "tkout"] == [] and "recipe" in rows, (
        "the time item is the date's, not a condition row (owner 10-24); «tkout » in the data is «tkout»")
    spec["wafer"]["time"] = "measured_at"
    own = report_reads.Report(db_session, spec, "E1")
    assert own.wafers[("W1",)]["time"] == "2026-10-01", "the wafer role's time column stands"
    assert report_shape.refusal(dict(spec, conditions=dict(spec["conditions"], time_item=3))).startswith(
        "derive.report.conditions.time_item is the condition item whose value is the wafer's time")


def test_a_yield_item_of_the_summary_is_the_yield_not_a_defect(report, db_session):
    """derive.report.summary.yield_item (owner 10-24 «요약표에 수율을 그냥 free item으로 넣었는데 … 자꾸 불량 유형으로
    리포트하네»): those rows are the matrix's yield row, read as a defect's cell is, and in no defect read."""
    from chain import report_shape

    m = models.DYNAMIC_TABLES
    for n, (w, fail) in enumerate([("W1", 95), ("W2", 90)]):
        db_session.add(m["rr_summary"](row_id="y%d" % n, wafer_id=w, defect_item="YIELD", n="1", fail_chips=fail,
                                       total_chips=100))
    db_session.commit()
    assert "YIELD" in [row[0] for row in report.pareto()["html"]["rows"]], "undeclared: a defect, as before"
    report.spec["summary"]["yield_item"] = "YIELD"
    assert "YIELD" not in [row[0] for row in report.pareto()["html"]["rows"]]
    table = report.yield_by()["html"]
    assert [(name, [c["text"] for c in cells]) for name, cells in table["info"]][-1] == (
        "Yield", ["95.0% (95/100)", "90.0% (90/100)", "—"]), "W1 W2 W3 by time; W3 has no yield row"
    assert "info Yield | 95.0% (95/100)" in report.yield_by()["context"], "the model reads it as the yield"
    assert all(item != "YIELD" for item, _cells in table["rows"])
    assert report_shape.refusal(dict(SPEC, summary=dict(SPEC["summary"], yield_item=[]))).startswith(
        "derive.report.summary.yield_item is the summary item (or items) that is the yield")


def test_two_values_of_one_wafers_condition_are_both_said(report, db_session):
    """A conditions table keyed beyond the wafer (a step) holds two rows of one wafer and name: both values, distinct, in
    the rows' order - «300 / 320», in the table and the model's context; none silently wins (owner 10-24)."""
    from chain import report_reads

    m = models.DYNAMIC_TABLES
    for n, value in enumerate(["300", "320", "300"]):
        db_session.add(m["rr_cond"](row_id="d%d" % n, wafer_id="W1", cname="temp", step=str(n), cvalue=value))
    db_session.commit()
    spec = json.loads(json.dumps(SPEC))
    spec["conditions"] = {"table": "rr_cond", "wafer": "wafer_id", "name": "cname", "value": "cvalue"}
    both = report_reads.Report(db_session, spec, "E1")
    assert both.wafers[("W1",)]["conditions"]["temp"] == "300 / 320"
    assert "temp: 300 / 320 1" in both.conditions()["context"]


def test_a_compare_set_is_a_second_group_of_columns(report):
    """The kind column's values are the declaration's (sets.kinds) - «eval» written there is not one of them."""
    assert report.compare(["baseline", "keylots"])["context"].splitlines() == [
        "baseline: 1 wafers (E0)", "keylots: 1 wafers (L0, L9)"]
    assert report.groups["keylots"] == [("W0",)], "the lot member picks by the wafer table's lot column"
    assert report.compare()["context"].splitlines() == ["baseline: 1 wafers (E0)", "compare E3: 1 wafers (wafer_id W7)"], \
        "no arguments: the declaration's comparison - sets.default and the newest control.recent"
    table = report.yield_by()["html"]
    assert table["groups"] == [("baseline", ["wafer_id W0"]), ("keylots", ["wafer_id W0"]), ("compare E3", ["wafer_id W7"]),
                               ("E1", ["wafer_id W1", "wafer_id W2", "wafer_id W3"])], "columns by date (owner 10-24)"
    particle, scratch = (_by_column(table, cells) for _item, cells in table["rows"])
    assert particle[("keylots", "wafer_id W0")] == particle[("baseline", "wafer_id W0")] == "50.0% (50/100)"
    assert scratch[("compare E3", "wafer_id W7")] == scratch[("keylots", "wafer_id W0")] == "—", "W0 · W7: no scratch row"


def test_a_wafer_and_item_two_rows_say_is_left_out_by_name(report, db_session):
    m = models.DYNAMIC_TABLES
    db_session.add(m["rr_summary"](row_id="dx", wafer_id="W3", defect_item="particle", n="2", fail_chips=9,
                                   total_chips=400))
    db_session.commit()
    table = report.yield_by()["html"]
    assert table["left_out"] == ["wafer_id W3 particle"] and _texts(table["rows"])[0][1][-1] == "—"
    assert _texts(table["rows"])[1][1][-1] == "10.0% (40/400)", "W3's other item stands"


def test_what_the_reads_cannot_answer_is_refused_by_name(report, monkeypatch):
    from chain import report_reads

    with pytest.raises(report_reads.ReadRefused, match="W7 is not a wafer of this report"):
        report.yield_by(["W7"])
    with pytest.raises(report_reads.ReadRefused, match="'tool' is not a condition"):
        report.yield_by(by="tool")
    monkeypatch.setattr(report_reads, "READ_ROW_CAP", 2)
    with pytest.raises(report_reads.ReadRefused, match="rr_summary: over 2 rows"):
        report.pareto()


def test_a_wafer_of_two_columns_is_read_column_for_column(report, db_session):
    """Wafers (A, 2) and (B, 1): each column's filter also lets (A, 1) through - its row must not count."""
    from chain import report_reads

    pair = {"rr_slot": {"composite_key_source": ["wafer_id", "slot"], "column_types": {
                "wafer_id": "string", "slot": "string", "eval_id": "string", "measured_at": "string"}},
            "rr_slot_summary": {"composite_key_source": ["wafer_id", "slot", "defect_item"], "column_types": {
                "wafer_id": "string", "slot": "string", "defect_item": "string", "fail_chips": "number",
                "total_chips": "number"}}}
    models.init_dynamic_models(pair)
    m = models.DYNAMIC_TABLES
    try:
        for name, entry in pair.items():
            crud.TABLE_CONFIG[name] = entry
            m[name].__table__.create(bind=db_session.get_bind())
        for n, (w, s, at) in enumerate([("A", "1", "1"), ("A", "2", "2"), ("B", "1", "3")]):
            db_session.add(m["rr_slot"](row_id="s%d" % n, wafer_id=w, slot=s, eval_id="E1", measured_at=at))
        for n, (w, s, chips) in enumerate([("A", "1", 90), ("A", "2", 5), ("B", "1", 7)]):
            db_session.add(m["rr_slot_summary"](row_id="d%d" % n, wafer_id=w, slot=s, defect_item="particle",
                                                fail_chips=chips, total_chips=100))
        db_session.commit()
        spec = {"wafer": {"table": "rr_slot", "key": ["wafer_id", "slot"], "time": "measured_at",
                          "evaluation": "eval_id"},
                "summary": {"table": "rr_slot_summary", "wafer": ["wafer_id", "slot"], "item": "defect_item",
                            "fail": "fail_chips", "total": "total_chips"}}
        two = report_reads.Report(db_session, spec, "E1")
        table = two.yield_by(["A/2", "B/1"])["html"]
        assert table["groups"] == [("E1", ["wafer_id A · slot 2", "wafer_id B · slot 1"])]
        assert _texts(table["rows"]) == [("particle", ["5.0% (5/100)", "7.0% (7/100)"])]
    finally:
        db_session.rollback()
        for name in pair:
            m[name].__table__.drop(bind=db_session.get_bind())
            retire_dynamic_model(name)


def test_a_wafer_whose_key_part_is_blank_reads_its_rows(report, db_session):
    """Wafer (A, blank slot) - its summary row spells the blank «» where the wafer table holds NULL; blank meets blank
    (owner 10-24: ops wafers with a blank part had no numbers). (A, 1) must not count."""
    from chain import report_reads

    pair = {"rr_blank": {"composite_key_source": ["wafer_id", "slot"], "column_types": {
                "wafer_id": "string", "slot": "string", "eval_id": "string", "measured_at": "string"}},
            "rr_blank_summary": {"composite_key_source": ["wafer_id", "slot", "defect_item"], "column_types": {
                "wafer_id": "string", "slot": "string", "defect_item": "string", "fail_chips": "number",
                "total_chips": "number"}}}
    models.init_dynamic_models(pair)
    m = models.DYNAMIC_TABLES
    try:
        for name, entry in pair.items():
            crud.TABLE_CONFIG[name] = entry
            m[name].__table__.create(bind=db_session.get_bind())
        for n, (w, s, at) in enumerate([("A", "1", "1"), ("A", None, "2"), ("B", "1", "3")]):
            db_session.add(m["rr_blank"](row_id="s%d" % n, wafer_id=w, slot=s, eval_id="E1", measured_at=at))
        for n, (w, s, chips) in enumerate([("A", "1", 90), ("A", "", 5), ("B", "1", 7)]):
            db_session.add(m["rr_blank_summary"](row_id="d%d" % n, wafer_id=w, slot=s, defect_item="particle",
                                                 fail_chips=chips, total_chips=100))
        db_session.commit()
        spec = {"wafer": {"table": "rr_blank", "key": ["wafer_id", "slot"], "time": "measured_at",
                          "evaluation": "eval_id"},
                "summary": {"table": "rr_blank_summary", "wafer": ["wafer_id", "slot"], "item": "defect_item",
                            "fail": "fail_chips", "total": "total_chips"}}
        two = report_reads.Report(db_session, spec, "E1")
        assert ("A", None) in two.wafers
        table = two.yield_by(["A/", "B/1"])["html"]
        assert _texts(table["rows"]) == [("particle", ["5.0% (5/100)", "7.0% (7/100)"])]
    finally:
        db_session.rollback()
        for name in pair:
            m[name].__table__.drop(bind=db_session.get_bind())
            retire_dynamic_model(name)


def test_a_name_two_wafers_share_is_refused_and_counted(report, db_session):
    """Lot «A/B» slot «1» and lot «A» slot «B/1» are both said «A/B/1» to the model (lead 10-22 안 1)."""
    from chain import report_reads

    pair = {"rr_lot_slot": {"composite_key_source": ["lot", "slot"], "column_types": {
        "lot": "string", "slot": "string", "eval_id": "string", "measured_at": "string"}}}
    models.init_dynamic_models(pair)
    model = models.DYNAMIC_TABLES["rr_lot_slot"]
    try:
        crud.TABLE_CONFIG["rr_lot_slot"] = pair["rr_lot_slot"]
        model.__table__.create(bind=db_session.get_bind())
        for n, (lot, slot) in enumerate([("A/B", "1"), ("A", "B/1"), ("C", "1")]):
            db_session.add(model(row_id="x%d" % n, lot=lot, slot=slot, eval_id="E1", measured_at=str(n)))
        db_session.commit()
        spec = {"wafer": {"table": "rr_lot_slot", "key": ["lot", "slot"], "time": "measured_at", "evaluation": "eval_id"},
                "summary": {"table": "rr_lot_slot", "wafer": ["lot", "slot"], "item": "lot", "fail": "slot",
                            "total": "slot"}}
        named = report_reads.Report(db_session, spec, "E1")
        assert sorted(named.overlaps) == ["A/B/1"] and len(named.overlaps["A/B/1"]) == 2
        with pytest.raises(report_reads.ReadRefused) as refused:
            named.pick(["A/B/1"])
        assert str(refused.value).startswith("A/B/1 names two wafers - ")
        assert "(A/B, 1)" in str(refused.value) and "(A, B/1)" in str(refused.value)
        assert named.pick(["C/1"]) == [("C", "1")], "a name only one wafer has still picks it"
    finally:
        db_session.rollback()
        model.__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model("rr_lot_slot")
