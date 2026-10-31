# -*- coding: utf-8 -*-
"""Owner 10-21 «키 칸은 시간 절대 안 쓰는 걸로», lead 10-31 ㄱ: a table save that makes a key column datetime is refused
- by the retype's own judgment seat (`retype.hold`), with the reason and the next step; an old table that already
declared its key column datetime still saves, said in a note, so it can be edited elsewhere.

  this save, against the file's entry before it            answer
  a new table, its key column datetime                      refused (retype_refused, the column named)
  a key column turned datetime                              refused
  a datetime value column made a key column                 refused
  an old table's datetime key column, another column edited saved + a note
  that key column declared string                           saved, no note
  a datetime value column                                   saved, no note
"""
import json

import pytest
from fastapi import HTTPException

KEY_TIME = "key column t is declared datetime - declare it string; a key's spelling is its identity"
HELD = ("probe: key column t is declared datetime - saved as before; a new key column is not a time - declared string, "
        "the queue converts it in the key's own spelling")


def _entry(t_type="datetime", keys=("lot", "t"), v_type="string"):
    return {"composite_key_source": list(keys), "column_types": {"lot": "string", "t": t_type, "v": v_type}}


@pytest.fixture(name="save")
def fixture_save(tmp_path, monkeypatch):
    from database import config_watcher
    from ledger import admin

    path = tmp_path / "table_config.json"
    monkeypatch.setattr(admin, "table_config_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "backup"))
    monkeypatch.setattr(config_watcher, "changed", lambda *a, **k: None)

    def save(entry, before=None, check_only=False):
        path.write_text(json.dumps({"probe": before} if before is not None else {}), encoding="utf-8")
        return admin.save_table_config_raw("probe", entry, admin.file_fingerprint(str(path)), check_only=check_only)

    save.path = path
    return save


@pytest.mark.parametrize("before, entry", [
    (None, _entry()),
    (_entry(t_type="string"), _entry()),
    (_entry(keys=("lot",)), _entry()),
], ids=["a new table", "a key column turned datetime", "a datetime value column made a key"])
@pytest.mark.parametrize("check_only", [False, True], ids=["save", "check only"])
def test_a_key_column_this_save_makes_a_time_is_refused(save, before, entry, check_only):
    with pytest.raises(HTTPException) as refused:
        save(entry, before, check_only)

    detail = refused.value.detail
    assert (detail["code"], detail["path"], detail["message"]) == ("retype_refused", "tables.probe.column_types.t",
                                                                   KEY_TIME)
    assert json.loads(save.path.read_text(encoding="utf-8")) == ({"probe": before} if before is not None else {}), \
        "nothing written"


@pytest.mark.parametrize("before, entry, notes", [
    (_entry(), _entry(v_type="number"), [HELD]),
    (_entry(), _entry(t_type="string"), []),
    (_entry(keys=("lot",)), _entry(keys=("lot",), v_type="datetime"), []),
], ids=["an old table's time key, another column edited", "that key column declared string",
        "a datetime value column"])
def test_what_is_not_a_new_time_key_saves(save, before, entry, notes):
    checked = save(entry, before, check_only=True)
    saved = save(entry, before)

    assert checked["notes"] == saved["notes"] == notes
    assert json.loads(save.path.read_text(encoding="utf-8"))["probe"]["column_types"] == entry["column_types"]
