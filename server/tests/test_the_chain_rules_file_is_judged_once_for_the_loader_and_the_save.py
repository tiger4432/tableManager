# -*- coding: utf-8 -*-
"""chain_rules.json is read and judged in ONE place - `read_rules_document` - for the loader, the editor's view, the
save and the grammar conversion (lead 10-29: the box's file was refused by the save's check «not an object with a
rules array» while the loader read the same shape as no rules - two judgements of one file).

  shape                         loader            view error     save / check / convert
  absent · {} · comment only    no rules          none           the shape passes (the first rule is written)
  top-level list · rules {} ·   RULES_NOT_AN_     that sentence  config_not_object, that sentence
  rules null · rules "x"        OBJECT
  not JSON                      its told()        that sentence  config_unreadable, that sentence
"""
import json
import logging

import pytest

from chain import ingestion_worker
from ledger import admin

RUNNABLE = {"trigger_table": "x", "target_table": "y", "mapper_module": "m", "mapper_function": "f"}
NO_RULES = {"absent": None, "empty object": {}, "comment only": {"__comment": "x"}}
REFUSED = {"top-level list": [], "rules object": {"rules": {}}, "rules null": {"rules": None}, "rules text": {"rules": "x"}}


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    path = tmp_path / "chain_rules.json"
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(ingestion_worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "backup"))
    for held in ("_RULES_DOCUMENT", "_LOADED_RULES", "_REFUSED_RULES"):          # load_chain_rules sets them
        monkeypatch.setattr(ingestion_worker, held, getattr(ingestion_worker, held))

    def write(shape, raw=None):
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
        elif shape is not None:
            path.write_text(json.dumps(shape), encoding="utf-8")
        return path

    return write


def _refusal(call):
    with pytest.raises(Exception) as refused:
        call()
    return refused.value.detail


@pytest.mark.parametrize("shape", list(NO_RULES.values()), ids=list(NO_RULES))
def test_no_rules_is_read_alike_and_the_first_rule_is_written(rules_file, shape):
    path = rules_file(shape)
    read = ingestion_worker.read_rules_document(str(path))
    assert (read["error"], read["rules"]) == (None, [])
    assert admin.chain_rule_raw_view()["error"] is None
    assert admin.save_chain_rule_raw("fresh", RUNNABLE, admin.file_fingerprint(str(path)), check_only=True)
    said = admin.save_chain_rule_raw("fresh", RUNNABLE, admin.file_fingerprint(str(path)))
    assert said["created"] is True
    written = json.loads(path.read_text(encoding="utf-8"))
    assert [rule["name"] for rule in written["rules"]] == ["fresh"]
    assert {k: v for k, v in written.items() if k != "rules"} == (shape or {}), "the file's other cells carried"


@pytest.mark.parametrize("shape, raw, code", [(shape, None, "config_not_object") for shape in REFUSED.values()]
                         + [(None, "{", "config_unreadable")], ids=list(REFUSED) + ["not JSON"])
def test_what_the_loader_cannot_read_every_door_refuses_with_its_sentence(rules_file, caplog, shape, raw, code):
    path = rules_file(shape, raw)
    before = path.read_bytes()
    read = ingestion_worker.read_rules_document(str(path))
    assert read["rules"] == [] and read["error"]
    if raw is None:
        assert read["error"] == ingestion_worker.RULES_NOT_AN_OBJECT
    with caplog.at_level(logging.ERROR):
        ingestion_worker.load_chain_rules()
    assert "Failed to load chain rules: " + read["error"] in caplog.text
    assert admin.chain_rule_raw_view()["error"] == read["error"]
    base = admin.file_fingerprint(str(path))
    for door in (lambda: admin.save_chain_rule_raw("fresh", RUNNABLE, base, check_only=True),
                 lambda: admin.save_chain_rule_raw("fresh", RUNNABLE, base),
                 lambda: admin.convert_chain_rule_grammar("fresh", "unified")):
        detail = _refusal(door)
        assert (detail["code"], detail["message"]) == (code, read["error"]), detail
    assert path.read_bytes() == before, "nothing written"
