# -*- coding: utf-8 -*-
"""총괄 10-07: ingestion_settings.json is opened in one place (`ingestion.settings`) - the watcher,
the enrichment config and candidates, and the retry poller read the same value from a file with a
BOM (the reading table_config has)."""
import codecs
import json

import run_watcher
from chain.enrichment import candidates
from chain.enrichment import config as enrichment_config
from ingestion import settings
from parsers import directory_watcher

CELL = "retry_reclaim_after_seconds"


def test_the_four_readers_read_one_value_from_a_file_with_a_bom(monkeypatch, tmp_path):
    path = tmp_path / "ingestion_settings.json"
    path.write_bytes(codecs.BOM_UTF8 + json.dumps({CELL: 42}).encode("utf-8"))
    for module in (settings, directory_watcher, candidates, enrichment_config):
        monkeypatch.setattr(module, "INGESTION_SETTINGS_PATH", str(path))
    assert [directory_watcher.load_ingestion_settings().get(CELL),
            candidates._load_ingestion_settings().get(CELL),
            enrichment_config._load_ingestion_settings().get(CELL),
            run_watcher.reclaim_grace_setting()] == [42, 42, 42, 42]
