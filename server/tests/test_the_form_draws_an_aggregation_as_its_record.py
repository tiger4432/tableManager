# -*- coding: utf-8 -*-
"""총괄 8b487d2e6 · 6c6d76924 — the declaration form draws `decide.aggregations` as records, says the cells it does not
read, and draws no Korean (소유자 「체인 선언창에 aggregation 이 안 뜨는데」 -> 「ㄱ 으로 폼 그려」).

  ① each aggregation reaches the form as its record - "count" too, through the reader's one fold - and the reader
    reads the record as it read what the file holds (a form save round-trips to the same normal form)
  ② a cell at the top or under `derive` the product does not read is named, on a rule that is off too
  ③ the form's ADVANCED line about a role-frame mapper is English
"""
import json
import re

import pytest

import mapper_sdk
from chain import rule_shape
from chain.enrichment import config as enrichment_config

AGGREGATIONS = {"n": "count", "hi": {"fn": "max", "column": "t"},
                "names": {"fn": "unique_concat", "column": "w", "separator": "/"}}
DECIDE = {"name": "agg_form", "enabled": True, "on": {"table": "src_t"}, "into": {"table": "derived_t"},
          "derive": {"kind": "decide", "decide": {"key": ["lot"], "fields": ["wafer"],
                                                   "aggregations": AGGREGATIONS}}}


def test_the_route_hands_each_aggregation_as_its_record_and_the_reader_reads_it_the_same(tmp_path, monkeypatch):
    from ledger import admin

    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [DECIDE]}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))

    out = admin.chain_rule_raw_view("agg_form")
    drawn = out["declaration"]["derive"]["decide"]["aggregations"]

    assert drawn == {"n": {"fn": "count"}, "hi": AGGREGATIONS["hi"], "names": AGGREGATIONS["names"]}
    assert json.loads(out["raw"]) == DECIDE, "the raw editor shows the file as written"
    for name, spec in AGGREGATIONS.items():
        assert enrichment_config._parse_aggregation(name, drawn[name]) == \
            enrichment_config._parse_aggregation(name, spec), name


@pytest.mark.parametrize("enabled", [True, False])
def test_a_cell_the_product_does_not_read_is_named_at_the_top_and_under_derive(enabled):
    declaration = dict(DECIDE, enabled=enabled, aggregations={"x": "count"}, zzz_cell=1, __comment="prose",
                       derive=dict(DECIDE["derive"], aggregations={"y": "count"}))
    _rules, refusal, notes = rule_shape.expand_declaration(
        declaration, {"src_t": {"column_types": {c: "string" for c in ("lot", "wafer", "t", "w")}},
                      "derived_t": {"business_key": "lot", "composite_key_source": ["lot"],
                                    "column_types": {c: "string" for c in ("lot", "wafer", *AGGREGATIONS)}}})
    tail = " The rule runs." if enabled else ""
    assert refusal is None
    assert "agg_form: top-level cell this product does not read — aggregations, zzz_cell.%s" % tail in notes, notes
    assert "agg_form: derive cell this product does not read — aggregations.%s" % tail in notes, notes


def test_the_role_frame_mappers_line_is_english():
    other = mapper_sdk.mapper_candidates()["other"]
    said = [o["why"] for o in other if o.get("kind") == "ledger_roleframe"]
    assert said and not any(re.search("[가-힣]", why) for why in said), said
