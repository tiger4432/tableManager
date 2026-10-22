# -*- coding: utf-8 -*-
"""Owner 10-22 (lead: the report's settings ARE its chain declaration): `derive.kind "report"` - the window's form
draws it from the skeleton, the save refuses a table or column the catalogue does not declare, and a declaration
stands as one rule on its request table naming the report mapper with the settings as its arguments.

  stands    report_request -> report, mapper declared:report, the settings as params, one request a group;
            its step and wafer tables in the rule's writes cell, replaced map by map
  wafer     one column or a list in every role - one column reads as a list of one; lengths must agree
  refused   a role missing · an undeclared table · an undeclared column · a wafer of another length ·
            a layout slot of an unknown kind · digits not a whole number · a summary saying neither F and N nor
            a rate · a rate without rate_scale 1 or 100
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
    "defect_image": {"column_types": {"wafer_id": "string", "slot": "string", "defect_item": "string",
                                      "image_path": "string"}},
    "report_request": {"column_types": {"request_id": "string", "setting": "string"}},
    "report": {"column_types": {"request_id": "string", "state": "string"}},
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
}


def _declaration(report=None):
    return {"name": "eval_summary", "on": {"table": "report_request"},
            "derive": {"kind": "report", "report": copy.deepcopy(REPORT if report is None else report)},
            "into": {"table": "report"}}


@pytest.fixture(autouse=True)
def tables(monkeypatch):
    for name, entry in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)


def test_a_report_stands_as_one_rule_naming_its_mapper_with_its_settings():
    rules, refusal, notes = rule_shape.expand_declaration(_declaration())
    assert refusal is None and notes == [], (refusal, notes)
    [rule] = rules
    assert (rule["trigger_table"], rule["target_table"], rule["mapper"], rule["rows_per_run"]) == (
        "report_request", "report", report_shape.REPORT_MAPPER, 1)
    assert rule["params"] == REPORT
    assert (rule["writes"], rule["allow_replace_map"]) == (["report_step", "report_wafer"], True)
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
     "derive.report.summary.wafer names 2 column(s) and derive.report.wafer.key 1"),
    (("wafer", "key"), [], "derive.report.wafer.key names no column"),
    (("layout",), [{"kind": "chart"}], "derive.report.layout[0].kind 'chart' - one of table · image · text"),
    (("layout",), [{"kind": "table", "fill": "summary"}], "derive.report.layout[0].fill 'summary' - a table is one of"),
    (("layout",), [{"kind": "text"}], "derive.report.layout[0].slot names no text"),
    (("digits",), 1.5, "derive.report.digits must be a whole number from 0"),
    (("sets", "kinds"), None, "derive.report.sets.kinds says what the kind column holds for evaluation · lot"),
    (("sets", "kinds"), {"run": "R"}, "derive.report.sets.kinds says what the kind column holds"),
    (("wafer", "lot"), None, "derive.report.sets.kinds.lot needs derive.report.wafer.lot"),
    (("wafer", "key"), ["wafer_id"] * 5, "derive.report.wafer.key names 5 columns - a report keeps a wafer's key in at most 4"),
    (("images", "px"), 0, "derive.report.images.px must be a whole number from 1"),
    (("loop", "steps"), "8", "derive.report.loop.steps must be a whole number from 1"),
    (("prompts", "functions"), {"sql": {"about": "x"}}, "derive.report.prompts.functions.sql - one of conditions"),
    (("control",), {"max_wafers": 5}, "derive.report.control.recent says how far back"),
    (("control",), {"recent": {"weeks": 2}}, "derive.report.control.recent says how far back"),
    (("control",), {"recent": {"days": 30}, "max_wafers": 0}, "derive.report.control.max_wafers must be a whole number"),
    (("template",), "<table><tr><td>{{nope}}</td></tr></table>", "{{nope}} is not a mark this report fills"),
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
    assert {key for key, f in fields.items() if f["required"]} == {"wafer", "summary"}
    wafer = {f["key"]: f["node"] for f in fields["wafer"]["node"]["fields"]}
    assert wafer["table"] == chain_bindings.table_ref()
    assert wafer["key"] == chain_bindings.list_node("column", chain_bindings.column_ref(("derive.report.wafer.table",)))
    summary = {f["key"]: f["node"] for f in fields["summary"]["node"]["fields"]}
    assert summary["fail"] == chain_bindings.column_ref(("derive.report.summary.table",)), \
        "a role's columns are its own table's"
    assert summary["rate_scale"] == {"kind": "leaf", "hint": "number"}
    assert fields["template"]["node"] == {"kind": "leaf", "hint": "free"}, "the form pastes the clipboard HTML at derive.report.template"
    control = {f["key"]: f["node"] for f in fields["control"]["node"]["fields"]}
    assert set(control) == {"recent", "max_wafers", "max_evaluations"}
