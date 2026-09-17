# -*- coding: utf-8 -*-
"""소유자 2026-09-17: 「인리치는 참조뷰 기능은 «보존»해야 해. v2 로 «따로» 빼되」

🔴 THE DEFECT THIS PINS WAS MEASURED, NOT IMAGINED. `rule_shape.expand_declaration` carries
`reference_views` through for a unified `derive.decide` declaration - probed - while every
consumer looked the rule up with `enrichment.config.load_enrichment_rules`, which opens ONE
file. So a view declared in the unified grammar was declared, carried, and unreachable.

⚠️ THE CONTROL GROUP IS THE OLD LOOKUP. If `load_enrichment_rules` ever starts finding the
unified declaration, this file's 「the seat is what added the reach」 claim is hollow and the
first assertion below would pass for the wrong reason.
"""
import io
import json
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import reference_view                                     # noqa: E402
from chain.enrichment import config as enrichment_config                   # noqa: E402

VIEW = {"label": "이 키의 원본 행",
        "query": "SELECT a FROM t WHERE k = :k ORDER BY a",
        "candidate_for": {"f": "a"},
        "limit": 120}

UNIFIED = {"name": "refview_unified",
           "on": {"table": "rv_src"}, "into": {"table": "rv_derived"},
           "derive": {"kind": "decide",
                      "decide": {"key": ["k"], "fields": ["f"],
                                 "reference_views": [VIEW]}}}

OLD_FILE = {"refview_old": {"source_table": "rv_src", "derived_table": "rv_derived",
                            "decision_key": ["k"], "target_fields": ["f"],
                            "reference_views": [VIEW]}}


def _paths(tmp_path):
    chain_path = tmp_path / "chain_rules.json"
    chain_path.write_text(json.dumps({"rules": [UNIFIED]}), encoding="utf-8")
    enrich_path = tmp_path / "enrichment_rules.json"
    enrich_path.write_text(json.dumps(OLD_FILE), encoding="utf-8")
    return str(chain_path), str(enrich_path)


def test_a_view_declared_in_either_grammar_is_reachable(tmp_path):
    """🔴 BOTH, AND THE SAME SHAPE. The route reads `reference_views` off whatever comes
    back, so a declaration that arrives without them is a 404 the operator cannot explain."""
    chain_path, enrich_path = _paths(tmp_path)

    found = {r["name"]: r for r in reference_view.declarations(
        chain_rules_path=chain_path, enrichment_path=enrich_path)}

    assert sorted(found) == ["refview_old", "refview_unified"]
    for name in found:
        views = found[name].get("reference_views") or []
        assert [v["label"] for v in views] == ["이 키의 원본 행"], name
        assert views[0]["query"].startswith("SELECT a FROM t"), name
        assert views[0]["candidate_for"] == {"f": "a"}, name
        assert views[0]["required_binds"] == ["k"], name


def test_the_old_lookup_still_cannot_see_the_unified_one(tmp_path):
    """⚠️ THE CONTROL GROUP. This is the state the round found, kept as a fact rather than a
    memory: `load_enrichment_rules` reads one file, and that is why the seat above exists.
    If this ever fails, the reach came from somewhere else and the seat is not the reason."""
    _chain_path, enrich_path = _paths(tmp_path)

    names = [r["name"] for r in enrichment_config.load_enrichment_rules(path=enrich_path)]

    assert names == ["refview_old"]
    assert "refview_unified" not in names


def test_find_and_the_list_walk_the_same_list(tmp_path):
    """🔴 `index` MEANS THE SAME THING AT BOTH ENDS. `/enrichment/rules` names the views and
    `/…/references/{index}` runs the index-th one; two lists would silently run the wrong
    view rather than fail."""
    chain_path, enrich_path = _paths(tmp_path)
    kwargs = {"chain_rules_path": chain_path, "enrichment_path": enrich_path}

    listed = reference_view.declarations(**kwargs)

    for rule in listed:
        one = reference_view.find(rule["name"], **kwargs)
        assert one is not None, rule["name"]
        assert [v["label"] for v in one["reference_views"]] == [
            v["label"] for v in rule["reference_views"]], rule["name"]
    assert reference_view.find("nothing_declares_this", **kwargs) is None


def test_a_switched_off_declaration_offers_no_views(tmp_path):
    """⚠️ 「OFF」 IS NOT 「BROKEN」 (판정 399). A disabled declaration stands no rule, so it has
    no views to run - and the loader has already said so in its own words."""
    chain_path = tmp_path / "chain_rules.json"
    chain_path.write_text(json.dumps(
        {"rules": [dict(UNIFIED, enabled=False)]}), encoding="utf-8")
    enrich_path = tmp_path / "empty.json"
    enrich_path.write_text(json.dumps({}), encoding="utf-8")

    found = reference_view.declarations(chain_rules_path=str(chain_path),
                                        enrichment_path=str(enrich_path))

    assert [r["name"] for r in found] == []
