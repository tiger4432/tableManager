# -*- coding: utf-8 -*-
"""Owner 10-31 «ㄴ» (lead): null_policy's "skip" retired - declared, it did nothing (`crud.key_fold_drops_row` had no
caller). "nokey" on a key column is the one value read; anything else is read as no null_policy, and said.

  null_policy         file                              grid               chain key gate     said
  not written         today's                           today's            today's            nothing
  "skip"              = not written                     = not written      = not written      one sentence
  an unknown value    = not written                     = not written      = not written      one sentence
  "nokey"             its blank key parts filled        = not written      = not written      nothing
                      nokey_... (today's answer)        (not a file row)

Where the sentence is heard: the table save's answer (`notes`, the help's check-only too), the reload's [Config]
line, the resolve report's catalogue entry.
"""
import json
import logging
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import retire_dynamic_model                                         # noqa: E402
from database import crud, models, schemas                                        # noqa: E402
from test_a_blank_key_is_filled_from_the_file_and_its_row import (                # noqa: E402,F401
    T, UNDECLARED, fixture_load)

POLICIES = {"not written": None, "skip": "skip", "unknown": "drop-it", "nokey": "nokey"}
SAID = ('{table}: null_policy cell this product does not read — slot: "{value}". Only "nokey" on a key column is '
        'read - the rest is read as no null_policy.')


def _declared(policy):
    return dict(UNDECLARED, **({"null_policy": {"slot": policy}} if policy else {}))


@pytest.mark.pg
def test_by_a_file_only_nokey_changes_what_is_written(load, pg_engine):
    got = {}
    for name, policy in POLICIES.items():
        with pg_engine.begin() as conn:
            conn.execute(text('DELETE FROM "%s"' % T))
            conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
        got[name] = load(_declared(policy))
    rows, line = got["not written"]
    assert rows == [("L1", None, "c")] and "nokey" not in line, "CANARY: today's answer - one row, its slot blank"
    assert got["skip"] == got["unknown"] == got["not written"], "the retired skip and an unknown value: as unwritten"
    filled, said = got["nokey"]
    assert len(filled) == 3 and all(slot.startswith("nokey_") for _lot, slot, _v in filled), filled
    assert "3 row(s) keyed nokey_... (slot)" in said
    for name, policy in POLICIES.items():
        assert crud.null_policy_unread(T, _declared(policy)) == (
            [SAID.format(table=T, value=policy)] if name in ("skip", "unknown") else []), name


def test_by_the_grid_no_value_changes_what_is_written(db_session, client):
    table = "null_policy_grid_probe"
    got = {}
    try:
        for name, policy in POLICIES.items():
            entry = _declared(policy)
            models.init_dynamic_models({table: entry})
            crud.TABLE_CONFIG[table] = entry
            model = models.DYNAMIC_TABLES[table]
            model.__table__.create(bind=db_session.get_bind())
            answer = client.put("/tables/%s/data/updates" % table, json={"updates": [
                {"updates": {"lot": "L1", "slot": slot, "v": v}, "source_name": "file", "updated_by": "probe"}
                for slot, v in (("", "a"), ("S2", "b"))]})
            assert answer.status_code == 200, answer.text
            got[name] = (sorted(((r.lot, r.slot, r.v) for r in db_session.query(model).all()), key=repr),
                         {k: answer.json().get(k) for k in ("status", "updated_count", "dropped", "change_count")})
            db_session.rollback()
            model.__table__.drop(bind=db_session.get_bind())
            retire_dynamic_model(table)
    finally:
        crud.TABLE_CONFIG.pop(table, None)
        retire_dynamic_model(table)
    assert {row[1] for row in got["not written"][0]} == {None, "S2"}, "CANARY: today's answer - the blank part kept"
    assert got["skip"] == got["unknown"] == got["nokey"] == got["not written"]


def test_by_the_chain_no_value_changes_what_the_key_gate_keeps():
    from chain import key_gate

    item = schemas.GeneralUpdateItem(updates={"lot": "", "slot": ""}, source_name="chain_ingestion",
                                     updated_by="chain_worker")
    got = {}
    try:
        for name, policy in POLICIES.items():
            crud.TABLE_CONFIG[T] = _declared(policy)
            kept, report = key_gate.screen(T, [item.model_copy(deep=True)])
            got[name] = (len(kept), report["refused_rows"], report["by_column"])
    finally:
        crud.TABLE_CONFIG.pop(T, None)
    assert got["not written"][1] == 1, "CANARY: today's answer - a row with no key is refused"
    assert got["skip"] == got["unknown"] == got["nokey"] == got["not written"]


def test_the_table_save_answers_the_sentence(tmp_path, monkeypatch):
    from database import config_watcher
    from ledger import admin

    path = tmp_path / "table_config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(admin, "table_config_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "backup"))
    monkeypatch.setattr(config_watcher, "changed", lambda *a, **k: None)
    said = [SAID.format(table="probe", value="skip")]
    checked = admin.save_table_config_raw("probe", _declared("skip"), admin.file_fingerprint(str(path)),
                                          check_only=True)
    saved = admin.save_table_config_raw("probe", _declared("skip"), admin.file_fingerprint(str(path)))
    assert (checked["notes"], saved["notes"]) == (said, said)
    assert json.loads(path.read_text(encoding="utf-8"))["probe"]["null_policy"] == {"slot": "skip"}, \
        "said, never refused"
    again = admin.save_table_config_raw("probe", _declared("nokey"), admin.file_fingerprint(str(path)))
    assert again["notes"] == []


def test_the_reload_says_it_once_per_table(caplog):
    from database import config_watcher

    with caplog.at_level(logging.WARNING):
        config_watcher._report_unsearchable_declarations({"a": _declared("skip"), "b": _declared("nokey"),
                                                          "c": UNDECLARED})
    lines = [r.getMessage() for r in caplog.records if "null_policy" in r.getMessage()]
    assert lines == ["[Config] " + SAID.format(table="a", value="skip")]


def test_the_resolve_report_s_catalogue_entry_says_it(monkeypatch):
    import config_resolve_report as crr

    monkeypatch.setattr(crud, "load_table_config_or_raise", lambda: {"a": _declared("skip"), "b": _declared("nokey")})
    domain = crr._resolve_catalog()
    detail = {e["subject"]: e["detail"] for e in domain["effective"]}
    assert detail["a"].endswith(" " + SAID.format(table="a", value="skip")), detail["a"]
    assert "null_policy" not in detail["b"]
