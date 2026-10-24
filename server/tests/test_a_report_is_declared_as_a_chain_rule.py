# -*- coding: utf-8 -*-
"""Owner 10-22 (lead: the report's settings ARE its chain declaration): `derive.kind "report"` - the window's form
draws it from the skeleton, the save refuses a table or column the catalogue does not declare, and a declaration
stands as one rule on a report table of the operator's own naming the report mapper with the settings as its
arguments (owner 10-23 «리포트용 표가 따로» · «wafer, 보고서 파일 경로 이 두 개가 최종 출력»: one row a wafer, its file path;
the summary table only read).

  stands    report table -> report table, mapper declared:report, the settings as params; no rows-per-run cut, no
            writes cell; the file column is what the mapper says it writes; state · reason named are said, not written
  wafer     one column or a list in every role - one column reads as a list of one; lengths must agree
  refused   a role missing · an undeclared table · an undeclared column · a wafer of another length ·
            a layout slot of an unknown kind · digits not a whole number · a summary saying neither F and N nor
            a rate · a rate without rate_scale 1 or 100 · results.file missing or not the report table's column · a
            rule on the summary table, on a table without the wafer's column, on one table into another · send_to
            not an address · causes not {seed_type, follow, collect, hops}
  named     a cell the product does not read is said, and the rule still stands
  form      the skeleton's report record: tables by name, columns of the role's own table, wafer keys as lists
"""
import copy

import pytest

from chain import report_shape, rule_shape
from database import crud

TABLES = {
    "wafer": {"column_types": {"wafer_id": "string", "slot": "string", "lot_id": "string", "eval_id": "string",
                               "measured_at": "datetime", "split": "string", "total_chips": "number"}},
    "defect_summary": {"column_types": {"wafer_id": "string", "slot": "string", "defect_item": "string",
                                        "fail_chips": "number", "total_chips": "number", "loss_rate": "number"}},
    "wafer_report": {"column_types": {"wafer_id": "string", "report_file": "string"}},
    "defect_image": {"column_types": {"wafer_id": "string", "slot": "string", "defect_item": "string",
                                      "image_path": "string"}},
    "compare_set": {"column_types": {"set_name": "string", "member": "string", "kind": "string"}},
}
REPORT = {
    "wafer": {"table": "wafer", "key": "wafer_id", "time": "measured_at", "lot": "lot_id", "evaluation": "eval_id",
              "conditions": ["split"]},
    "summary": {"table": "defect_summary", "wafer": ["wafer_id"], "item": "defect_item", "fail": "fail_chips",
                "total": "total_chips"},
    "images": {"table": "defect_image", "wafer": "wafer_id", "item": "defect_item", "image": "image_path",
               "per_item": 3, "px": 320},
    "sets": {"table": "compare_set", "name": "set_name", "member": "member", "kind": "kind",
             "kinds": {"evaluation": "eval", "lot": "lot"}},
    "rows": ["particle", "scratch"], "digits": 1,
    "prompts": {"select": "pick the split", "style": "short", "compare": "against baseline"},
    "layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}],
    "loop": {"steps": 8, "seconds": 300, "context_tokens": 16000},
    "results": {"file": "report_file"},
    "send_to": "http://relay:8765/reports",
    "causes": {"seed_type": "defect_kind", "follow": ["leads_to"], "collect": ["quantity"], "hops": 4},
}


def _declaration(report=None, table="wafer_report", into=None):
    return {"name": "eval_summary", "on": {"table": table},
            "derive": {"kind": "report", "report": copy.deepcopy(REPORT if report is None else report)},
            "into": {"table": into or table}}


@pytest.fixture(autouse=True)
def tables(monkeypatch):
    for name, entry in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)


def test_a_report_stands_as_one_rule_naming_its_mapper_with_its_settings():
    rules, refusal, notes = rule_shape.expand_declaration(_declaration())
    assert refusal is None and notes == [], (refusal, notes)
    [rule] = rules
    assert (rule["trigger_table"], rule["target_table"], rule["mapper"]) == (
        "wafer_report", "wafer_report", report_shape.REPORT_MAPPER)
    assert rule["params"] == REPORT
    assert not {"rows_per_run", "writes", "allow_replace_map"} & set(rule), rule
    assert rule["is_batch"] is True, "the group's rows in one call - a wafer's rows make one report"
    assert report_shape.result_columns(rule) == ["report_file"]
    assert rule_shape.from_declaration({"derive": {"report": REPORT}})["derive"]["kind"] == "report", \
        "a derive naming only its report cell is a report"


def _with(path, value):
    report = copy.deepcopy(REPORT)
    where = report
    for step in path[:-1]:
        where = where[step]
    if value is None:
        del where[path[-1]]
    else:
        where[path[-1]] = value
    return report


@pytest.mark.parametrize("path, value, said", [
    (("summary",), None, "derive.report needs summary"),
    (("summary", "table"), "nowhere", "derive.report.summary.table 'nowhere' is not a declared table"),
    (("summary", "fail"), "fail_chip", "derive.report.summary.fail 'fail_chip' is not a column of 'defect_summary'"),
    (("summary", "item"), None, "derive.report.summary.item names no column"),
    (("summary", "total"), None, "derive.report.summary names fail and total together"),
    (("wafer", "conditions"), ["split", "recipe"], "derive.report.wafer.conditions 'recipe' is not a column"),
    (("summary", "wafer"), ["wafer_id", "slot"],
     "derive.report.summary.wafer 'slot' is not a key column"),
    (("wafer", "key"), [], "derive.report.wafer.key names no column"),
    (("layout",), [{"kind": "chart"}], "derive.report.layout[0].kind 'chart' - one of table · image · text"),
    (("layout",), [{"kind": "table", "fill": "summary"}], "derive.report.layout[0].fill 'summary' - a table is one of"),
    (("layout",), [{"kind": "text"}], "derive.report.layout[0].slot names no text"),
    (("digits",), 1.5, "derive.report.digits must be a whole number from 0"),
    (("sets", "kinds"), None, "derive.report.sets.kinds says what the kind column holds for evaluation · lot"),
    (("sets", "kinds"), {"run": "R"}, "derive.report.sets.kinds says what the kind column holds"),
    (("wafer", "lot"), None, "derive.report.sets.kinds.lot needs derive.report.wafer.lot"),
    (("results",), None, "derive.report.results names the report table's column a report's file path goes in"),
    (("results", "file"), None, "derive.report.results names the report table's column"),
    (("results", "file"), "report_path", "derive.report.results 'report_path' is not a column of 'wafer_report'"),
    (("send_to",), "relay:8765", "derive.report.send_to is the address a report is POSTed to"),
    (("images", "px"), 0, "derive.report.images.px must be a whole number from 1"),
    (("loop", "steps"), "8", "derive.report.loop.steps must be a whole number from 1"),
    (("prompts", "functions"), {"sql": {"about": "x"}}, "derive.report.prompts.functions.sql - one of conditions"),
    (("control",), {"max_wafers": 5}, "derive.report.control.recent says how far back"),
    (("control",), {"recent": {"weeks": 2}}, "derive.report.control.recent says how far back"),
    (("control",), {"recent": {"days": 30}, "max_wafers": 0}, "derive.report.control.max_wafers must be a whole number"),
    (("template",), "<table><tr><td>{{nope}}</td></tr></table>", "{{nope}} is not a mark this report fills"),
    (("causes", "seed_type"), None, "derive.report.causes is {"),
    (("causes", "seed_type"), " ", "derive.report.causes is {"),
    (("causes", "follow"), "leads_to", "derive.report.causes is {"),
    (("causes", "collect"), [""], "derive.report.causes is {"),
    (("causes", "hops"), -1, "derive.report.causes is {"),
    (("causes", "hops"), 2.5, "derive.report.causes is {"),
    (("causes", "walk"), "static", "derive.report.causes is {"),
    (("causes",), ["defect_kind"], "derive.report.causes is {"),
])
def test_what_cannot_make_a_report_is_refused_by_its_path(path, value, said):
    """(Each row changes one cell of a declaration that stands.)"""
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration(_with(path, value)))
    assert rules == [] and refusal is not None and said in refusal, refusal


@pytest.mark.parametrize("summary, said", [
    ({"rate": "loss_rate", "rate_scale": 100}, None),
    ({"rate": "loss_rate", "rate_scale": 1, "fail": "fail_chips", "total": "total_chips"}, None),
    ({"rate": "loss_rate"}, "derive.report.summary.rate_scale: 1 or 100"),
    ({"rate": "loss_rate", "rate_scale": 50}, "derive.report.summary.rate_scale: 1 or 100"),
    ({"rate": "loss_rate", "rate_scale": True}, "derive.report.summary.rate_scale: 1 or 100"),
    ({}, "derive.report.summary needs rate, or fail and total"),
])
def test_a_summary_says_f_and_n_or_a_rate_read_over_its_scale(summary, said):
    report = copy.deepcopy(REPORT)
    report["summary"] = dict({"table": "defect_summary", "wafer": "wafer_id", "item": "defect_item"}, **summary)
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration(report))
    assert (refusal is None and len(rules) == 1) if said is None else (rules == [] and said in refusal), refusal


def test_a_wafer_of_two_columns_stands_when_every_role_names_two():
    report = copy.deepcopy(REPORT)
    report["wafer"]["key"] = ["wafer_id", "slot"]
    for role in ("summary", "images"):
        report[role]["wafer"] = ["wafer_id", "slot"]
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration(report))
    assert refusal is None and len(rules) == 1, refusal
    assert report_shape.wafer_columns("wafer_id") == ["wafer_id"] and report_shape.wafer_columns(["a", "b"]) == ["a", "b"]


def test_a_declaration_of_an_old_shape_is_refused_saying_the_report_table(monkeypatch):
    """On the summary table (10-23 morning), on a request table (before), on one table into another: refused, each
    naming the report table it stands on now - one row a wafer, its wafer column, its file column."""
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration(table="defect_summary"))
    assert rules == [] and ("the report rule stands on a report table of its own - one row a wafer, its wafer column "
                            "(derive.report.wafer.key)") in refusal and \
        "the summary table 'defect_summary' is read, never written" in refusal, refusal
    monkeypatch.setitem(crud.TABLE_CONFIG, "report_request", {"column_types": {"request_id": "string",
                                                                               "report_file": "string"}})
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration(table="report_request"))
    assert rules == [] and "'report_request' has none of derive.report.wafer.key's columns (wafer_id)" in refusal, \
        refusal
    rules, refusal, _notes = rule_shape.expand_declaration(_declaration(into="defect_summary"))
    assert rules == [] and "on.table and into.table are one table, got 'wafer_report' and 'defect_summary'" in \
        refusal, refusal


def test_a_state_or_reason_column_named_is_said_and_the_rule_stands():
    """Owner 10-23 «wafer, 보고서 파일 경로 이 두 개가 최종 출력»: a declaration of the three-column shape stands - its
    state and reason are not written, and the save says so."""
    rules, refusal, notes = rule_shape.expand_declaration(_declaration(dict(REPORT, results={
        "file": "report_file", "state": "report_state", "reason": "report_reason"})))
    assert refusal is None and len(rules) == 1, refusal
    assert any("derive.report.results.state · reason is not written" in note for note in notes), notes


def test_a_cell_the_product_does_not_read_is_named_and_the_rule_stands():
    rules, refusal, notes = rule_shape.expand_declaration(_declaration(dict(REPORT, colour="blue")))
    assert refusal is None and len(rules) == 1
    assert any("derive.report cell(s) this product does not read — colour" in note for note in notes), notes


def test_the_form_draws_the_report_from_the_skeleton():
    import chain_bindings

    branches = chain_bindings.skeleton()["unified_root"]
    derive = next(f for f in branches["fields"] if f["key"] == "derive")["node"]
    report = derive["branches"]["report"]
    fields = {f["key"]: f for f in report["fields"]}
    assert [key for key in fields] == list(report_shape.REPORT_CELLS)
    assert {key for key, f in fields.items() if f["required"]} == {"wafer", "summary", "results"}
    results = {f["key"]: f["node"] for f in fields["results"]["node"]["fields"]}
    assert results == {"file": chain_bindings.column_ref(("into.table",))}, "the file column is the report table's"
    assert fields["send_to"]["node"] == {"kind": "leaf", "hint": "free"}
    wafer = {f["key"]: f["node"] for f in fields["wafer"]["node"]["fields"]}
    assert wafer["table"] == chain_bindings.table_ref()
    assert wafer["key"] == chain_bindings.list_node("column", chain_bindings.column_ref(("derive.report.wafer.table",)))
    summary = {f["key"]: f["node"] for f in fields["summary"]["node"]["fields"]}
    assert summary["fail"] == chain_bindings.column_ref(("derive.report.summary.table",)), \
        "a role's columns are its own table's"
    assert summary["rate_scale"] == {"kind": "leaf", "hint": "number"}
    assert fields["template"]["node"] == {"kind": "leaf", "hint": "html"}, "the form pastes the clipboard HTML into an html cell"
    picture = {f["key"]: f["node"] for f in fields["picture_rows"]["node"]["of"]["fields"]}
    row_table = chain_bindings.column_ref(("derive.report.picture_rows.*.table",))
    assert picture["wafer"] == chain_bindings.list_node("column", row_table) and picture["image"] == row_table, \
        "a picture row's columns are its own row's table's - «*» is the cell's own row number"
    control = {f["key"]: f["node"] for f in fields["control"]["node"]["fields"]}
    assert set(control) == {"recent", "same", "max_wafers", "max_evaluations"}
