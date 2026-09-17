# -*- coding: utf-8 -*-
"""S-188 ⓓ+ⓑ. One cell names the mapper, flat cells are read as params, and the loader
refuses a rule it cannot run.

🔴 THE LOADER VALIDATED NOTHING BEFORE THIS. `load_chain_rules` did `json.load` and took
`data["rules"]`; an unknown key or a typo was silent, which is how a rule could sit in the
file for weeks doing nothing.

⛔ AND THE FIRST VERSION OF THAT CHECK REFUSED NINE OF NINE RULES IN THIS BOX. `__comment`
is a comment by convention, so it is not a routing cell and not a mapper argument -- and
being neither, `exact` called it an unknown field. A validator written to protect the chain
switched the whole chain off. `test_a_comment_is_not_a_declaration` is that failure, pinned.

⚠️ WHAT IS REFUSED IS 「CANNOT RUN」, NOT 「UNFAMILIAR」. A top-level cell the product does not
know is a mapper argument still written flat, and the product cannot tell a stale one from a
live one because the mapper that reads it lives in a gitignored file. Those are NAMED. What
is refused is a rule with no `name`/`trigger_table`, or one whose mapper resolves to nothing.
"""
import io
import json
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import chain_bindings                                                # noqa: E402
import mapper_sdk                                                    # noqa: E402

RUNNABLE = {"mapper_module": "mappers.x", "mapper_function": "build"}


def _rule(**cells):
    base = {"name": "r", "trigger_table": "t"}
    base.update(RUNNABLE)
    base.update(cells)
    return base


@pytest.fixture()
def load(tmp_path, monkeypatch):
    """Drives the real `load_chain_rules` over a file we write."""
    from chain import ingestion_worker as worker
    from chain import mapper_call

    def run(rules):
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        kept = worker.load_chain_rules()
        # ⚠️ `load_chain_rules` ALSO APPENDS THE SYNTHESIZED ENRICHMENT RULES, and those are
        # built by this process rather than typed — the grammar check deliberately skips
        # them. Selecting by the names WE wrote is independent of how `origin` is spelled;
        # filtering on `origin != "synthesized"` silently kept all eight, because the real
        # value is `synthesized:<name>`.
        wrote = {r.get("name") for r in rules if isinstance(r, dict)}
        return [r for r in kept if r.get("name") in wrote], [r.get("name") for r in kept]

    return run


# ---------------------------------------------------------------------------
# ⓓ — the one cell
# ---------------------------------------------------------------------------

def test_the_one_cell_and_the_two_cells_are_read_from_one_place():
    assert chain_bindings.mapper_cells({"mapper": "build_rows"}) == ("build_rows", None, None)
    assert chain_bindings.mapper_cells(RUNNABLE) == (None, "mappers.x", "build")
    assert chain_bindings.mapper_cells(None) == (None, None, None)


def test_the_one_cell_is_a_routing_cell_and_so_is_params():
    """⛔ THE FIRST VERSION FORGOT THIS and `mapper` came out of `flat_param_cells` as though
    it were a mapper argument -- the cell that names the mapper, passed to the mapper."""
    keys = chain_bindings.routing_keys()
    assert chain_bindings.MAPPER_KEY in keys and chain_bindings.PARAMS_KEY in keys
    assert chain_bindings.flat_param_cells({"mapper": "m", "params": {}}) == ()


def test_a_flat_cell_is_read_as_a_param_and_the_block_wins():
    """🔴 ONE-WAY COMPATIBILITY: the operator's file is not touched. And if a name is written
    BOTH ways the block wins -- preferring the flat copy would make the migration a no-op
    that looks done."""
    rule = {"x_col": "flat", "params": {"x_col": "block", "y_col": "Y"}}
    assert chain_bindings.flat_param_cells(rule) == ("x_col",)
    assert chain_bindings.params_of(rule) == {"x_col": "block", "y_col": "Y"}


def test_the_seat_prefers_a_registered_mapper_over_the_two_cells(monkeypatch):
    """The one cell wins when it resolves; otherwise the module/function path runs, which is
    what every rule in a box with no decorated mappers still does.

    ⚰️ [판정 498] ASKED OF THE SEAT. The `if registered else import` lived inside
    `execute_custom_mapper`; that function folded into `rule_run.resolve` along with the
    builtin table, so the precedence is the seat's to answer now.
    🔴 AND THE TWO CELLS NAME SOMETHING UNIMPORTABLE ON PURPOSE. They used to be `None`,
    which passes whether the one cell won or the other arm merely did nothing; a module that
    cannot be found makes 「the one cell won」 the only way this can be green.
    """
    from chain import rule_run

    calls = []

    def fake(db, payloads, rule=None):
        calls.append("registered")
        return {"updates": []}

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "build_rows", fake)
    out = rule_run.run_rule(None, {"name": "r", "mapper": "build_rows", "is_batch": True,
                                   "mapper_module": "no_such_module_anywhere",
                                   "mapper_function": "emit"},
                            payloads=[])
    assert calls == ["registered"] and out["updates"] == []


# ---------------------------------------------------------------------------
# ⓑ — what the loader refuses, and what it only names
# ---------------------------------------------------------------------------

def test_a_comment_is_not_a_declaration(load):
    """⛔ THE REGRESSION THIS FILE EXISTS FOR. Measured before the fix: 9 of 9 rules in this
    box refused, every one of them for `__comment`."""
    kept, _ = load([_rule(__comment="why this exists", __why_enabled="owner asked")])
    assert len(kept) == 1, "a comment must not cost the rule"


def test_a_rule_that_names_no_runnable_mapper_is_refused(load):
    kept, _ = load([{"name": "no_mapper", "trigger_table": "t"}])
    assert kept == []


def test_a_rule_missing_a_required_cell_is_refused(load):
    assert load([{"trigger_table": "t", **RUNNABLE}])[0] == []
    assert load([{"name": "r", **RUNNABLE}])[0] == []


def test_one_refused_rule_does_not_cost_the_others(load):
    """🔴 「거절된 분자는 세고 건너뛴다, 죽은 페이지가 아니다」. The previous behaviour on a bad
    file was to log once and continue with NO rules at all."""
    kept, _ = load([_rule(name="good_one"),
                    {"name": "broken", "trigger_table": "t"},
                    _rule(name="good_two")])
    assert sorted(r["name"] for r in kept) == ["good_one", "good_two"]


def test_a_flat_cell_is_named_rather_than_refused(load):
    """⚠️ The product cannot tell a stale flat cell from a live one — the mapper that reads it
    is in a gitignored file. So it is reported, and the rule still runs."""
    kept, _ = load([_rule(x_col="X", lot_column="LOT")])
    assert len(kept) == 1
    assert chain_bindings.params_of(kept[0]) == {"x_col": "X", "lot_column": "LOT"}
