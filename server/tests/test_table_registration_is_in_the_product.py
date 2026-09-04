# -*- coding: utf-8 -*-
"""Registering a table must be possible from inside the application.

No admin route wrote `table_config.json`, so adding a table meant editing a file on the
server host - which turns the completion rule's two lines into three, and the third is
"leave the application" (owner's ruling, 2026-09-04).

🔴 THE FUNCTION THIS REPLACES WAS NOT SAFE TO REVIVE. `crud.update_table_config` has no
callers at all; its body is a plain `open(w)` whose failure is swallowed by a `print`, so
an exception leaves a ZERO-BYTE registration for five processes to read - and
`config_watcher`'s own comments record having read a partially-written file from that
writer. The three guards here are the ruling, not decoration.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_admin                                             # noqa: E402


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "table_config.json"
    path.write_text(json.dumps({"existing": {"business_key": "k"}}), encoding="utf-8")
    monkeypatch.setattr(ledger_admin, "table_config_path", lambda: str(path))
    monkeypatch.setattr(ledger_admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    return path


def base_of(path):
    return ledger_admin.file_fingerprint(str(path))


def test_a_new_table_can_be_registered_without_leaving_the_app(config_file):
    ledger_admin.save_table_config_raw(
        "probe", {"business_key": "pk"}, base_of(config_file))
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["probe"] == {"business_key": "pk"}


def test_saving_one_table_does_not_erase_the_others(config_file):
    """🔴 THE MERGE IS SHALLOW ON PURPOSE. Whole-file writing makes every save a rewrite of
    everyone else's registration - the reason the ledger raw editor chose the same unit."""
    ledger_admin.save_table_config_raw(
        "probe", {"business_key": "pk"}, base_of(config_file))
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["existing"] == {"business_key": "k"}


def test_a_save_against_a_moved_file_is_refused_by_name(config_file):
    """Two operators open the same file; without this the second silently erases the
    first. Same refusal name as the ledger raw editor."""
    stale = base_of(config_file)
    ledger_admin.save_table_config_raw("other", {"business_key": "x"}, stale)

    with pytest.raises(Exception) as raised:
        ledger_admin.save_table_config_raw("probe", {"business_key": "pk"}, stale)
    assert raised.value.detail["code"] == "stale_base", raised.value.detail


def test_a_declaration_that_is_not_an_object_is_refused_before_anything_is_written(
        config_file):
    """⚠️ Refused BEFORE, and the file must be byte-identical afterwards - a validation
    that runs after the write has already been read by the watcher."""
    before = config_file.read_bytes()
    with pytest.raises(Exception) as raised:
        ledger_admin.save_table_config_raw("probe", ["not", "an", "object"],
                                           base_of(config_file))
    assert raised.value.detail["code"] == "declaration_not_object"
    assert config_file.read_bytes() == before


def test_a_refusal_carries_a_code_and_an_address_rather_than_prose(config_file):
    """⛔ The replaced function printed its failure and returned None, so a save that did
    not happen looked exactly like one that did."""
    with pytest.raises(Exception) as raised:
        ledger_admin.save_table_config_raw("", {"business_key": "pk"},
                                           base_of(config_file))
    detail = raised.value.detail
    assert detail["code"] and detail["path"] and detail["message"]
    assert detail["ok"] is False


def test_the_view_offers_one_table_and_the_base_the_save_will_check(config_file):
    view = ledger_admin.table_config_raw_view("existing")
    assert view["editable_unit"] == "table"
    assert view["tables"] == ["existing"]
    assert view["declaration"] == {"business_key": "k"}
    assert view["base"] == base_of(config_file)


def test_the_write_is_atomic_and_leaves_no_temp_behind(config_file, tmp_path):
    """🔴 A plain open(w) that throws leaves zero bytes, and five processes read this
    file. The temp lands in the SAME directory so the watcher sees a replace."""
    ledger_admin.save_table_config_raw(
        "probe", {"business_key": "pk"}, base_of(config_file))
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == [], leftovers
    assert json.loads(config_file.read_text(encoding="utf-8"))["probe"]


def test_the_previous_registration_is_kept_as_the_undo(config_file, tmp_path):
    """🔴 THE COPY IS THE UNDO (R-2026-08-13-G), and it is what separates this from a
    plain `open(w)`: a bare write leaves no way back and no temp to notice either, so
    without this assertion a mutant that drops the atomic writer passes every other case.
    """
    result = ledger_admin.save_table_config_raw(
        "probe", {"business_key": "pk"}, base_of(config_file))
    assert result["backup"], "no backup was taken, so the save cannot be undone"
    assert os.path.exists(result["backup"])
    assert "existing" in json.loads(
        open(result["backup"], encoding="utf-8").read())


@pytest.mark.parametrize("bad", [[], "text", 3, None])
def test_column_types_must_be_a_mapping_because_boot_reads_it_as_one(config_file, bad):
    """🔴 THE ONE HOLE THE REVIEW FOUND. `init_dynamic_models` calls
    `table_cfg.get("column_types", {}).items()`, so a list here raises INSIDE the boot
    path - where main's broad except swallows it. The server then comes up with ZERO
    dynamic models, one ERROR line, and a screen that looks empty; crud.py:760 records
    having measured that exact failure.

    ⚠️ And nothing is written: the file must be byte-identical after the refusal.
    """
    before = config_file.read_bytes()
    with pytest.raises(Exception) as raised:
        ledger_admin.save_table_config_raw(
            "probe", {"column_types": bad}, base_of(config_file))
    assert raised.value.detail["code"] == "column_types_not_object"
    assert raised.value.detail["path"] == "tables.probe.column_types"
    assert config_file.read_bytes() == before


def test_a_registration_without_column_types_is_still_allowed(config_file):
    """⛔ Present-and-wrong is refused; ABSENT is not. Requiring it would invent a rule
    this round was told not to write, and boot defaults it to an empty mapping."""
    ledger_admin.save_table_config_raw(
        "probe", {"business_key": "pk"}, base_of(config_file))
    assert json.loads(config_file.read_text(encoding="utf-8"))["probe"]


def test_a_good_column_types_mapping_goes_through(config_file):
    ledger_admin.save_table_config_raw(
        "probe", {"column_types": {"a": "string"}}, base_of(config_file))
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["probe"]["column_types"] == {"a": "string"}
