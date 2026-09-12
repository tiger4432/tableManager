# -*- coding: utf-8 -*-
"""S-201. `/admin/chain/rules` stops opening the file itself, and stops being kinder than the loader.

🔴 THREE READERS, ONE FILE. The loader, this route, and the setup report all wanted
`chain_rules.json`. S-180 ⓑ gave it one reader; this is the last caller to move over.

🔴 AND ONE ANSWER CHANGES ON PURPOSE. A top-level LIST file was handed back by this route as
`data` while the LOADER refused it — so the screen listed rules the boot would never run.
That is a false green, and it is the same shape as the dry-run preview accepting a mapper the
loader dropped (S-180 ⓑ-0). The screen must not be kinder than the loader.

⚠️ 「없는 파일」 IS NOT 「빈 파일」 and that answer is untouched: `absent_listing` still answers
for a file that is not there.
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

import main                                                           # noqa: E402


@pytest.fixture()
def rules_file(monkeypatch, tmp_path):
    """Points `paths.config_path` at a temp file for this one name only."""
    import paths as paths_module

    target = tmp_path / "chain_rules.json"
    real = paths_module.config_path

    def fake(*parts):
        if parts and str(parts[-1]) == "chain_rules.json":
            return str(target)
        return real(*parts)

    monkeypatch.setattr(paths_module, "config_path", fake)
    monkeypatch.setattr(main.paths, "config_path", fake)
    return target


def _call():
    return main.get_chain_rules()


# ---------------------------------------------------------------------------
# unchanged answers
# ---------------------------------------------------------------------------

def test_a_normal_document_answers_exactly_as_before(rules_file):
    """⚠️ THE BYTE-IDENTITY GATE (판정 316). The ordinary case is the one an operator sees
    every day, and moving the read must not move it."""
    rules = [{"name": "r1", "trigger_table": "t"}, {"name": "r2", "trigger_table": "u"}]
    rules_file.write_text(json.dumps({"rules": rules}), encoding="utf-8")

    assert _call() == {"status": "success", "data": rules}


def test_a_missing_file_is_still_ABSENT_and_not_empty(rules_file):
    """⛔ `absent` IS NOT `empty`. A caller that cannot tell 「설치가 덜 됐다」 from 「아직
    아무것도 없다」 has lost the only fact that decides what to do next."""
    assert not rules_file.exists()
    answer = _call()

    assert answer["state"] == "absent"
    assert answer["data"] == []
    assert answer["absent_path"] == str(rules_file)


def test_a_document_with_no_rules_key_is_empty_and_not_absent(rules_file):
    rules_file.write_text(json.dumps({"note": "nothing yet"}), encoding="utf-8")
    assert _call() == {"status": "success", "data": []}


def test_broken_json_is_an_error_with_the_reason_in_it(rules_file):
    rules_file.write_text("{ not json", encoding="utf-8")
    answer = _call()

    assert answer["status"] == "error" and answer["data"] == []
    assert answer["message"], "the reason must travel — 「읽지 못했다」 alone sends nobody anywhere"


# ---------------------------------------------------------------------------
# 🔴 the one answer that changes
# ---------------------------------------------------------------------------

def test_a_top_level_list_is_REFUSED_the_way_the_loader_refuses_it(rules_file):
    """🔴 THE BEHAVIOUR CHANGE, NAMED (S-201). This route used to return the list as `data`
    while the loader refused the same file — so the screen showed rules that would never run.

    ⚠️ Measured before the change: the route answered `data=[{...}]` and the loader answered
    「Failed to load chain rules: 'list' object has no attribute 'get'」. Two answers about one
    file, and the kinder one was on the screen.
    """
    rules_file.write_text(json.dumps([{"name": "top_level"}]), encoding="utf-8")

    answer = _call()

    assert answer["status"] == "error", "the screen must not be kinder than the loader"
    assert answer["data"] == []
    assert "list" in answer["message"], answer["message"]


def test_the_route_and_the_loader_agree_on_that_file(rules_file):
    """🔴 THE PROPERTY, NOT THE SPELLING. Both go through `read_rules_document`, so this
    cannot be satisfied by two checks that happen to match today."""
    import chain_ingestion_worker as worker

    rules_file.write_text(json.dumps([{"name": "top_level"}]), encoding="utf-8")
    read = worker.read_rules_document(str(rules_file))

    assert read["error"] and read["rules"] == []
    assert _call()["message"] == read["error"]


def test_the_route_opens_no_file_of_its_own():
    """🔴 THE DRIFT ASSERTION. A second `open` here is a second reader, free to disagree with
    the loader about what the operator wrote."""
    import inspect

    source = inspect.getsource(main.get_chain_rules)
    body = source
    doc = inspect.getdoc(main.get_chain_rules)
    if doc:
        for line in doc.splitlines():
            body = body.replace(line, "")

    assert "read_rules_document" in body
    for spelled in ("open(", "json.load"):
        assert spelled not in body, spelled
