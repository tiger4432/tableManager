# -*- coding: utf-8 -*-
"""총괄 d34247b3d ㉠ — one rule name had two answers. A CLI asked the operation's own lookup
before recording and refused; the admin publish only normalized the params, queued the run, and
the child failed on that same lookup. `validate` - which the publish, the count and a CLI's
`run_here` all pass - now asks it, so a name the operation cannot find leaves no row behind."""
import pytest

from admin import retroactive
from chain import enrich_declarations, replay
from database import models
from tests.test_a_declared_join_can_be_backfilled_like_any_rule import _rules
from tests.test_retroactive_admin import RULE_MIXED, retro_env  # noqa: F401

RULE_OPS = ["chain_replay", "enrichment_backfill", "enrichment_confirm"]


def _recorded(db):
    return (db.query(models.RetroactiveRun).count(),
            db.query(models.DatabaseOutbox).filter(
                models.DatabaseOutbox.event_type == retroactive.RUN_EVENT_TYPE).count())


@pytest.fixture(name="no_enrich_rules")
def fixture_no_enrich_rules(monkeypatch):
    """No enrich declaration stands - the box's own rules file is never read."""
    monkeypatch.setattr(enrich_declarations, "declarations", lambda *a, **k: [])
    monkeypatch.setattr(enrich_declarations, "find", lambda *a, **k: None)


def test_the_rule_taking_operations_are_the_three_judged():
    """Canary: the parametrized cells below are every operation that takes a rule."""
    takes_rule = sorted(op for op, spec in retroactive.OPERATIONS.items()
                        if any(p["name"] == "rule" for p in spec["params"]))
    assert takes_rule == sorted(RULE_OPS)
    assert all(retroactive.OPERATIONS[op]["judge"] is not None for op in RULE_OPS)


@pytest.mark.parametrize("op", RULE_OPS)
def test_the_publish_the_count_and_a_cli_give_one_refusal_and_record_nothing(
        retro_env, no_enrich_rules, op):
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, op, {"rule": "no_such_rule"}),
                lambda: retroactive.count(retro_env, op, {"rule": "no_such_rule"}),
                lambda: retroactive.run_here(op, {"rule": "no_such_rule"},
                                             log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert "'no_such_rule'" in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0), "a refused name must leave no run and no event"


@pytest.mark.parametrize("shape, words", [
    ({"idempotent": False}, "idempotent"),
    ({"trigger_table": "not_a_registered_table"}, "is not initialized"),
])
def test_a_replay_the_run_would_refuse_is_refused_before_it_is_recorded(
        retro_env, monkeypatch, shape, words):
    """총괄 69aad666e ④: what `replay_rule` refuses before its first page is the judge's too,
    so the refusal arrives before a run row is written (075174b41's promise)."""
    from chain import replay

    rule = dict(RULE_MIXED, **shape)
    monkeypatch.setattr(replay, "load_rules", lambda: [rule])
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, "chain_replay", {"rule": rule["name"]}),
                lambda: retroactive.count(retro_env, "chain_replay", {"rule": rule["name"]}),
                lambda: retroactive.run_here("chain_replay", {"rule": rule["name"]},
                                             log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert words in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0), "a refused replay must leave no run and no event"


def test_a_rule_it_can_find_is_still_queued(retro_env):
    """The control: the judgment refuses what the run would refuse, nothing more."""
    out = retroactive.publish(retro_env, "chain_replay", {"rule": RULE_MIXED["name"]})

    assert out["status"] == "queued"
    assert _recorded(retro_env)[0] == 1


def test_picked_rows_still_make_a_companion_a_legal_subject(monkeypatch):
    """S-270: the rows travel into the judgment - without them the grid's replay of a join's
    second half would be refused at the door it used to pass."""
    # The judge now asks what the run asks before its first page - the tables' models among
    # it (69aad666e ④) - so the two tables are registered as the run would find them.
    from database import crud
    from tests.test_a_declared_join_can_be_backfilled_like_any_rule import TABLES
    models.init_dynamic_models(TABLES)
    for name, cfg in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, cfg)
    rules = _rules()
    monkeypatch.setattr(replay, "load_rules", lambda: rules)
    companion = rules[1]["name"]

    assert retroactive.validate(
        "chain_replay", {"rule": companion, "row_ids": "r1"})["row_ids"] == ["r1"]
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("chain_replay", {"rule": companion})
    assert "second half of declaration" in str(refused.value)


def test_force_disabled_still_reaches_the_judgment(monkeypatch):
    """The CLI's `--force-disabled` travels too - a disabled rule the operator forced is not
    refused as disabled."""
    monkeypatch.setattr(enrich_declarations, "declarations", lambda *a, **k: [])
    monkeypatch.setattr(
        enrich_declarations, "find",
        lambda name, include_disabled=False, **k: (
            {"name": name, "enabled": False} if include_disabled else None))

    assert retroactive.validate(
        "enrichment_backfill", {"rule": "enr_off", "force_disabled": "true"}
    )["force_disabled"] is True
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("enrichment_backfill", {"rule": "enr_off"})
    assert "is disabled" in str(refused.value)


# ---------------------------------------------------------------------------
# 총괄 8e54a261b ④ — the table and ledger operations are judged at the same seat
# ---------------------------------------------------------------------------

NAME_OPS = {
    "resolve": ({"table": "no_such_table"}, {"table": "retro_test_target"}),
    "fold_file_layers": ({"table": "no_such_table"}, {"table": "retro_test_target"}),
    "withdraw": ({"table": "no_such_table", "source": "retro_src"},
                 {"table": "retro_test_target", "source": "retro_src"}),
    "ledger_backfill": ({"source": "no_such_source"}, {"source": "dt_job"}),
    "ledger_rescope": ({"source": "no_such_source", "scope_column": "row_id",
                        "scope_values": "a"},
                       {"source": "dt_job", "scope_column": "row_id", "scope_values": "a"}),
}


@pytest.fixture(name="shipped_ledger")
def fixture_shipped_ledger(tmp_path, monkeypatch):
    """The SHIPPED declaration plus one source the loader refuses (it reads a view), loaded
    wherever the product calls `load_setup` - never this box's gitignored ontology."""
    import json
    from pathlib import Path

    from ledger import setup as ledger_setup
    from ledger.setup_bundle import load_physical_catalog

    sample = Path(__file__).resolve().parent.parent / "config" / "sample"
    document = json.loads((sample / "ledger_config.json.sample").read_text(encoding="utf-8"))
    refused = json.loads(json.dumps(document["sources"]["lot_slot_wafer"]))
    refused["relation"] = "ledger_events"
    document["sources"]["reads_a_view"] = refused
    root = tmp_path / "ontology"
    root.mkdir()
    (root / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")
    catalog = load_physical_catalog(sample / "table_config.json.sample")
    real = ledger_setup.load_setup
    monkeypatch.setattr(ledger_setup, "load_setup",
                        lambda *a, **k: real(root, catalog=catalog))


def test_every_operation_is_judged_before_it_is_recorded():
    """Canary: no operation is left for its run to be the first to judge its names."""
    assert sorted(op for op, spec in retroactive.OPERATIONS.items()
                  if spec["judge"] is None) == []
    assert (set(NAME_OPS) | set(RULE_OPS) | set(COLLECTOR_OPS) | set(SET_ASIDE_OPS)
            == set(retroactive.OPERATIONS))


@pytest.mark.parametrize("op", sorted(NAME_OPS))
def test_an_unknown_table_or_source_gets_one_refusal_at_every_door_and_no_record(
        retro_env, shipped_ledger, op):
    unknown = NAME_OPS[op][0]
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, op, dict(unknown)),
                lambda: retroactive.count(retro_env, op, dict(unknown)),
                lambda: retroactive.run_here(op, dict(unknown), log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert "no_such_" in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0), "a refused name must leave no run and no event"


@pytest.mark.parametrize("op", ["resolve", "withdraw"])
def test_an_undeclared_column_gets_one_refusal_at_every_door_and_no_record(retro_env, op):
    """총괄 bf9d3367a — R2 and R3 look the table AND its columns up in one place, and the
    judgment asks that place."""
    params = dict(NAME_OPS[op][1], columns="no_such_col")
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, op, dict(params)),
                lambda: retroactive.count(retro_env, op, dict(params)),
                lambda: retroactive.run_here(op, dict(params), log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert "no_such_col" in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0)


#: The operations whose name is a collector script (`<table>/<script.py>`), judged the same way.
COLLECTOR_OPS = ["collector_backfill"]

#: The emergency stop's pair - a scope of tables, rules or transactions; a rule is judged by name.
SET_ASIDE_OPS = ["rerun_set_aside", "set_aside"]


@pytest.mark.parametrize("op", SET_ASIDE_OPS)
@pytest.mark.parametrize("params", [{"rules": "no_such_rule"}, {}])
def test_a_set_aside_with_an_unknown_rule_or_no_scope_is_refused_once_and_leaves_nothing(
        retro_env, op, params):
    given = dict(params, **({"reason": "r"} if op == "set_aside" else {}))
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, op, dict(given)),
                lambda: retroactive.count(retro_env, op, dict(given)),
                lambda: retroactive.run_here(op, dict(given), log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert ("no_such_rule" if params else "at least one table") in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0), "a refused set-aside must leave no run and no event"


@pytest.fixture(name="planted_collector")
def fixture_planted_collector(tmp_path, monkeypatch):
    """One collector that declares a window, in a workspace of its own."""
    import os

    import paths

    folder = os.path.join(str(tmp_path), "ingestion_workspace", "retro_test_target", "auto_update")
    os.makedirs(folder)
    with open(os.path.join(folder, "probe.py"), "w", encoding="utf-8") as f:
        f.write("# schedule: 0 * * * *\n# window: 1d\nout = ['{{WINDOW_START}}{{WINDOW_END}}']\n")
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    return "retro_test_target/probe.py"


def test_an_unknown_collector_gets_one_refusal_at_every_door_and_no_record(
        retro_env, planted_collector):
    unknown = {"collector": "no_such_table/probe.py", "start": "2026-09-24"}
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, "collector_backfill", dict(unknown)),
                lambda: retroactive.count(retro_env, "collector_backfill", dict(unknown)),
                lambda: retroactive.run_here("collector_backfill", dict(unknown),
                                             log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert "no_such_" in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0), "a refused name must leave no run and no event"


def test_a_known_collector_is_still_queued(retro_env, planted_collector):
    out = retroactive.publish(retro_env, "collector_backfill",
                              {"collector": planted_collector, "start": "2026-09-24"})

    assert out["status"] == "queued"
    assert _recorded(retro_env)[0] == 1


@pytest.mark.parametrize("op", sorted(NAME_OPS))
def test_a_known_table_or_source_is_still_queued(retro_env, shipped_ledger, op):
    out = retroactive.publish(retro_env, op, dict(NAME_OPS[op][1]))

    assert out["status"] == "queued"
    assert _recorded(retro_env)[0] == 1


def test_a_refused_source_is_a_name_that_exists_and_still_counts_as_before(
        retro_env, shipped_ledger):
    """Only the unknown name is the judgment's: a source the loader refused still gets its
    count's own answer - not applicable, not zero - and is not refused at the door."""
    out = retroactive.count(retro_env, "ledger_backfill", {"source": "reads_a_view"})

    assert out["absence"] == retroactive.ABSENCE_NOT_APPLICABLE
    assert out["extra"]["refused"] == "source_refused"


def test_a_refused_sources_rescope_is_refused_by_name_before_its_scope_is_read(
        retro_env, shipped_ledger):
    """총괄 06bb8f474 — the scope of a source the loader refused was read first and met its
    plan's missing driver as an AttributeError; the publish queued it and the child crashed.
    The one declared-source check comes first now, at every door."""
    params = {"source": "reads_a_view", "scope_column": "row_id", "scope_values": "a"}
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, "ledger_rescope", dict(params)),
                lambda: retroactive.count(retro_env, "ledger_rescope", dict(params)),
                lambda: retroactive.run_here("ledger_rescope", dict(params),
                                             log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert "refused by the loader" in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0)


def test_an_empty_table_config_is_said_before_any_name_is_judged(monkeypatch):
    """The judgments look tables up, so 「nothing is registered」 is asked first - in the CLI's
    door and the daemon's, the sentence the CLIs print themselves."""
    from database import crud

    monkeypatch.setattr(crud, "TABLE_CONFIG", {})
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.run_here("enrichment_backfill", {"rule": "x"}, log=lambda *_: None)
    out = retroactive.execute({"run_id": "empty-probe", "op": "enrichment_backfill",
                               "params": {"rule": "x"}}, log=lambda *_: None)

    assert "table_config.json is empty" in str(refused.value)
    assert out["status"] == "refused" and "table_config.json is empty" in out["error"]


def test_a_table_the_process_has_not_built_yet_is_built_before_it_is_judged(
        retro_env, monkeypatch):
    """A CLI process builds its models in the door; the judgment that looks the table up
    comes after that, or every table reads as 「not initialized」 there."""
    from conftest import retire_dynamic_model

    retire_dynamic_model("retro_test_target")
    monkeypatch.setattr(retroactive, "claim", lambda *a, **k: "built-probe")
    monkeypatch.setattr(retroactive, "_run_in_this_process",
                        lambda run_id, op, spec, params, log: {"ran": params["table"]})

    out = retroactive.run_here("resolve", {"table": "retro_test_target"},
                               log=lambda *_: None)

    assert out == {"ran": "retro_test_target"}
