# -*- coding: utf-8 -*-
"""A chain rule renamed in the editor is renamed WHERE IT STANDS (총괄 c6a8c069c ㉠, owner 「체인선언에서
체인명 바꾸면 복제가 되네」 -> 「ㄱ 제자리 바꾸기」). Before: the form sent the new name, the save
found no rule by it and appended a NEW rule switched off - the old one kept running and the
renamed one never ran. `from` is the name the editor opened.

A rename is refused, by name and with the next step, while a record holds the old name: a map
confirmation, an unprocessed replay event, another rule's `alignment_rule`, an unfinished
retroactive run - each is looked up by the rule's name and would be cut.
"""
import json
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                         # noqa: E402
from database import models                                          # noqa: E402
from ledger import admin                                             # noqa: E402

RUNNABLE = {"mapper_module": "m", "mapper_function": "f"}
RULES = [
    {"name": "first", "trigger_table": "a", "target_table": "b", **RUNNABLE, "enabled": True},
    {"name": "second", "trigger_table": "c", "target_table": "d", **RUNNABLE, "enabled": False},
    {"name": "third", "trigger_table": "e", "target_table": "f", **RUNNABLE, "enabled": True},
]


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for model in (models.DatabaseOutbox, models.FrameConfirmation, models.RetroactiveRun):
        model.__table__.create(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    import database.database as database_module
    monkeypatch.setattr(database_module, "SessionLocal", Session)
    session = Session()
    yield session
    session.close()


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": RULES}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "bk"))
    return path


def names(path):
    return [(r["name"], r["enabled"]) for r in json.loads(path.read_text(encoding="utf-8"))["rules"]]


def rename(path, db, old, new, **declaration):
    return admin.save_chain_rule_raw(
        new, {"trigger_table": "c", "target_table": "d", **RUNNABLE, **declaration},
        admin.file_fingerprint(str(path)), db=db, renamed_from=old)


def test_a_rename_keeps_the_place_and_the_switch_and_leaves_no_old_name(rules_file, db):
    result = rename(rules_file, db, "second", "second_renamed")

    assert names(rules_file) == [("first", True), ("second_renamed", False), ("third", True)]
    assert result["created"] is False and result["rules"] == 3
    assert result["renamed_from"] == "second"
    assert result["note"].startswith("Cells this rule wrote are written again")
    assert [r["name"] for r in worker.reread_rules_only()].count("second") == 0


def test_a_save_that_is_not_a_rename_says_nothing_about_one(rules_file, db):
    result = rename(rules_file, db, "second", "second")

    assert names(rules_file) == [("first", True), ("second", False), ("third", True)]
    assert "renamed_from" not in result and "note" not in result


def test_a_name_another_rule_has_is_refused(rules_file, db):
    with pytest.raises(Exception) as refused:
        rename(rules_file, db, "second", "third")

    assert "rule_name_taken" in str(refused.value.detail)
    assert names(rules_file) == [("first", True), ("second", False), ("third", True)]


def test_a_rule_that_left_the_file_after_it_was_opened_is_refused_as_stale(rules_file, db):
    with pytest.raises(Exception) as refused:
        rename(rules_file, db, "gone", "new_name")

    assert "stale_base" in str(refused.value.detail)
    assert len(names(rules_file)) == 3


def test_a_new_rule_without_from_is_saved_as_today(rules_file, db):
    result = admin.save_chain_rule_raw(
        "fresh", {"trigger_table": "x", "target_table": "y", **RUNNABLE},
        admin.file_fingerprint(str(rules_file)), db=db)

    assert result["created"] is True and result["enabled"] is False
    assert names(rules_file)[-1] == ("fresh", False) and len(names(rules_file)) == 4


def _confirmation(db):
    db.add(models.FrameConfirmation(confirmation_uid="u1", rule_name="second", unit_key="k",
                                    version=1, confirmed_frame="{}", ruling_state="ruled",
                                    weakest_source="user", weakest_priority=0,
                                    confirmed_by="operator"))


def _replay_event(db):
    db.add(models.DatabaseOutbox(event_uuid="e1", table_name="c", event_type="UPDATE",
                                 processed_chain=False, payload={"only_rule": "second:target"}))


def _run(db):
    db.add(models.RetroactiveRun(run_id="r1", op="chain_replay", state="queued",
                                 params=json.dumps({"rule": "second"})))


@pytest.mark.parametrize(("hold", "what"), [
    (_confirmation, "1 map confirmation(s)"),
    (_replay_event, "1 unprocessed replay event(s)"),
    (_run, "1 unfinished retroactive run(s)"),
])
def test_a_record_holding_the_old_name_refuses_the_rename_by_name(rules_file, db, hold, what):
    hold(db)
    db.commit()

    with pytest.raises(Exception) as refused:
        rename(rules_file, db, "second", "second_renamed")

    detail = str(refused.value.detail)
    assert "rule_name_held" in detail and what in detail and "Next: keep the name" in detail
    assert names(rules_file)[1] == ("second", False)


def test_another_rule_naming_it_as_alignment_rule_refuses_the_rename(rules_file, db):
    document = json.loads(rules_file.read_text(encoding="utf-8"))
    document["rules"][0]["alignment_rule"] = "second"
    rules_file.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(Exception) as refused:
        rename(rules_file, db, "second", "second_renamed")

    assert "1 rule(s) naming it as alignment_rule" in str(refused.value.detail)


def test_a_finished_run_or_a_processed_event_holds_nothing(rules_file, db):
    db.add(models.RetroactiveRun(run_id="r2", op="chain_replay", state="done",
                                 params=json.dumps({"rule": "second"})))
    db.add(models.DatabaseOutbox(event_uuid="e2", table_name="c", event_type="UPDATE",
                                 processed_chain=True, payload={"only_rule": "second"}))
    db.commit()

    assert rename(rules_file, db, "second", "second_renamed")["renamed_from"] == "second"
