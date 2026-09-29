# -*- coding: utf-8 -*-
"""[총괄 57ae5c2da ①] The chain rules are read when they change, not on every queue refresh.

🔴 소유자 09-29 「선언을 계속 읽은 set(22) 이거 계속떠」. The grid's queue tab asks
`GET /outbox/queue/rows` on every chain broadcast, and the route re-read the rules file each
time - one load and one `[ChainRules] set(N)` line per broadcast. Request paths now read the
set as last loaded; the rule save and the web server's reload seat make the next request
read it again, so `set(N)` counts real reads.
"""
import json
import logging

import pytest

from chain import ingestion_worker as worker
from ledger import admin
from runtime import system_reload

URL = "/outbox/queue/rows"
RUNNABLE = {"mapper_module": "m", "mapper_function": "f"}


def _rule(name):
    return {"name": name, "trigger_table": "t", "target_table": "u", "enabled": True, **RUNNABLE}


@pytest.fixture
def rules_file(tmp_path, monkeypatch):
    """⛔ NEVER the box's file - the running worker reads that one."""
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [_rule("rr_one")]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    return path


def _reads(caplog):
    return sum(r.getMessage().startswith("[ChainRules] set(") for r in caplog.records)


def _known(client):
    return set(client.get(URL).json()["rules_known"])


def test_a_hundred_queue_refreshes_read_the_rules_once(rules_file, client, caplog):
    caplog.set_level(logging.INFO)

    answers = [_known(client) for _ in range(100)]

    assert all("rr_one" in known for known in answers)
    assert _reads(caplog) == 1, "the queue re-read the rules on a refresh"


def test_a_saved_rule_is_read_by_the_next_request_and_only_once(rules_file, client, caplog):
    caplog.set_level(logging.INFO)
    assert "rr_two" not in _known(client)

    admin.save_chain_rule_raw("rr_two", _rule("rr_two"), admin.file_fingerprint(str(rules_file)))

    assert "rr_two" in _known(client), "the next request did not see the saved rule"
    _known(client)
    assert _reads(caplog) == 2


def test_a_file_the_server_did_not_write_is_read_after_reload(rules_file, client, caplog):
    """⚠️ THE TRADE, PINNED. A hand edit of the file is not a door this process sees - it
    waits for Reload Configs, as the chain worker's copy always has."""
    caplog.set_level(logging.INFO)
    _known(client)
    rules_file.write_text(json.dumps({"rules": [_rule("rr_one"), _rule("rr_hand")]}),
                          encoding="utf-8")

    assert "rr_hand" not in _known(client)
    system_reload.reload_local_process_cache()
    assert "rr_hand" in _known(client)
    _known(client)
    assert _reads(caplog) == 2
