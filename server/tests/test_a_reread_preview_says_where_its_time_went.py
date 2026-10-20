# -*- coding: utf-8 -*-
"""총괄 10-20 (소유자 «미리보기 아직도 느림»): the re-read preview says where its seconds went - walk · sources · lookup ·
judge · total, the files and the folders - in its answer and one server line; and validates the external sources once
until table_config / ingestion_settings change or a reload (owner «시작할 때 안 읽는 거는»): judging a root resolves it,
and one unreachable share root cost every preview 21 s."""
import logging
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (SERVER_DIR, os.path.join(SERVER_DIR, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher                                         # noqa: E402
from ingestion import reread                                     # noqa: E402


def test_the_preview_answers_and_says_its_stages(tmp_path, monkeypatch, caplog):
    for folder in ("a", "b"):
        (tmp_path / "raws" / folder).mkdir(parents=True)
        (tmp_path / "raws" / folder / "f.csv").write_text("x")
    monkeypatch.setattr(reread, "table_sources", lambda table: (str(tmp_path / "raws"), []))
    monkeypatch.setattr(reread, "_newest_rows_of", lambda db, table, walked: {})
    caplog.set_level(logging.INFO, logger=reread.logger.name)
    got = reread.select_files(None, "t", str(tmp_path / "raws"))
    assert (got["walked"], got["folders"]) == (2, 3), got                      # raws, a, b
    assert set(got["took"]) == {"walk", "sources", "lookup", "judge", "total"} and \
        all(seconds >= 0 for seconds in got["took"].values()), got["took"]
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Reread] preview of ")]
    assert len(said) == 1 and "2 file(s) in 3 folder(s), 2 picked" in said[0] and "walk " in said[0] \
        and "sources " in said[0] and "lookup " in said[0] and "judge " in said[0], said


def test_the_sources_are_validated_once_until_a_file_changes_or_a_reload(tmp_path, monkeypatch):
    import json

    import paths
    from runtime import system_reload

    tables = {"asked": {"business_key": "k", "column_types": {"k": "string"}, "std_parse": True},
              "other": {"business_key": "k", "column_types": {"k": "string"}, "std_parse": True}}
    (tmp_path / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    settings = tmp_path / "ingestion_settings.json"
    sources = [{"path": str(tmp_path / "share"), "table_name": "asked", "options": {"glob": ["**/*.csv"]}},
               {"path": str(tmp_path / "theirs"), "table_name": "other", "options": {"glob": ["**/*.csv"]}}]
    settings.write_text(json.dumps({"external_sources": sources}), encoding="utf-8")
    monkeypatch.setattr(paths, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(paths, "WORKSPACE_DIR", str(tmp_path / "ingestion_workspace"))
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))
    validated, real = [], directory_watcher.validate_external_source_specs
    monkeypatch.setattr(directory_watcher, "validate_external_source_specs",
                        lambda *a: (validated.append(1), real(*a))[1])
    reread.forget_sources()
    _raws, specs = reread.table_sources("asked")
    reread.table_sources("other")
    reread.table_sources("asked")
    assert [spec["table_name"] for spec in specs] == ["asked"] and len(validated) == 1, validated     # once
    os.utime(settings, ns=(os.stat(settings).st_mtime_ns + 10 ** 9,) * 2)                          # the file changed
    reread.table_sources("asked")
    assert len(validated) == 2, validated
    system_reload.reload_local_process_cache()                                                      # a reload
    reread.table_sources("asked")
    assert len(validated) == 3, validated
