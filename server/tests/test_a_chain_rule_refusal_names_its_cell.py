# -*- coding: utf-8 -*-
"""총괄 10-21 ① — a chain rule's save refusal names the CELL it refuses (`rules.<rule>.<cell>`), so the form stands the
sentence beside that cell. Each refusing return of `rule_shape.expand_declaration` gives its own cell
(`validation.Refusal`), driven here through the save gate one return at a time; the flag return is reached by the save
gate's own flag check first, so its expander return is asked directly."""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_shape                                        # noqa: E402
from database import crud                                           # noqa: E402
from ledger import admin                                            # noqa: E402

SRC, DST = "kcell_src", "kcell_dst"
TABLES = {
    SRC: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "grade": "string"}, "display_columns": ["job", "grade"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "grade": "string"}, "display_columns": ["job", "grade"]},
}


def _join(**join):
    return {"on": {"table": SRC}, "into": {"table": DST},
            "derive": {"kind": "join", "join": dict({"on": {"job": "job"}}, **join)}}


#: (the return it reaches, the declaration, the cell its refusal names)
CASES = [
    ("enabled", dict(_join(), enabled="false"), "enabled"),
    ("key.columns", dict(_join(), key={"columns": "job"}), "key.columns"),
    ("derive.kind", {"on": {"table": SRC}, "into": {"table": DST}, "derive": {"kind": "banana"}}, "derive.kind"),
    ("into.read", dict(_join(), into={"read": True}), "into.read"),
    ("right_table", _join(right_table=SRC), "derive.join.right_table"),
    ("on.table", dict(_join(), on={}), "on.table"),
    ("blank", _join(blank="maybe"), "derive.join.blank"),
    ("take fn", _join(take=[{"from": "grade", "fn": "banana"}]), "derive.join.take.grade.fn"),
    ("decide", {"on": {"table": SRC}, "into": {"table": DST}, "derive": {"kind": "decide", "decide": {}}},
     "derive.decide"),
    ("on.columns", dict(_join(), on={"table": SRC, "columns": ["grade"]}), "on.columns"),
]


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    crud.TABLE_CONFIG.update(TABLES)
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "backup"))
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    import paths
    real_config_path = paths.config_path
    monkeypatch.setattr(paths, "config_path",
                        lambda name: str(path) if name == "chain_rules.json" else real_config_path(name))
    try:
        yield path
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


@pytest.mark.parametrize("reaches, declaration, cell", CASES, ids=[case[0] for case in CASES])
def test_the_save_refusal_names_the_cell(rules_file, reaches, declaration, cell):
    name = "kcell_" + reaches.replace(" ", "_").replace(".", "_")
    with pytest.raises(Exception) as raised:
        admin.save_chain_rule_raw(name, dict(declaration, name=name), admin.file_fingerprint(str(rules_file)))
    detail = raised.value.detail
    assert detail["path"] == "rules.%s.%s" % (name, cell), detail


def test_the_expanders_own_flag_return_names_the_cell():
    _stood, refusal, _notes = rule_shape.expand_declaration(dict(_join(), name="kcell_flag", enabled="false"))
    assert refusal.cell == "enabled" and refusal.startswith("kcell_flag: enabled must be true or false"), refusal
