"""The value rules (join · pad_last_number · replace · time) and the alias table - stage one of
총괄 5ee9d3bd1: the fold and its declaration check. Storing through the write door is stage two.

Both engines agreeing on join · pad · replace is scored in `contracts/notation_fold/`; this file
holds what only Python does (alias, time, the declaration check, the write preview).
"""
import json
from datetime import datetime

import pytest

import notation_norm as nn
from database import crud, models, schemas
from product_tables import NOTATION_ALIAS_TABLE, PRODUCT_TABLES
from utils.time_format import TS_FMT

TABLES = {
    "notval_test_wafer": {
        "business_key": "row_key",
        "composite_key_source": ["lot", "wafer"],
        "composite_key_separator": "_",
        "map_key_columns": ["lot"],
        "column_types": {"row_key": "string", "lot": "string", "wafer": "string",
                         "seen_at": "string", "note": "string"},
    },
}
OWNER = {"join": "-", "pad_last_number": 2, "case": False}


def _declare(tmp_path, monkeypatch, columns):
    path = tmp_path / "notation_rules.json"
    path.write_text(json.dumps({"columns": {"notval_test_wafer": columns}}), encoding="utf-8")
    monkeypatch.setattr(nn, "NOTATION_RULES_PATH", str(path))
    nn.reset_cache()


@pytest.fixture()
def val_env(db_session, tmp_path, monkeypatch):
    tables = dict(TABLES, **{NOTATION_ALIAS_TABLE: PRODUCT_TABLES[NOTATION_ALIAS_TABLE]})
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    _declare(tmp_path, monkeypatch, {
        "wafer": {"write": True, "rules": OWNER},
        "seen_at": {"write": True, "rules": {"time": {"from": ["%Y/%m/%d %H:%M:%S",
                                                               "%d.%m.%Y %H:%M"]}}},
        "note": {"rules": OWNER},
    })
    yield db_session
    nn.reset_cache()
    from conftest import retire_dynamic_model
    for name in tables:
        retire_dynamic_model(name)
        crud.TABLE_CONFIG.pop(name, None)


def _refusals(columns, known=TABLES):
    rejections = []
    by_table = nn.validate_notation_rules({"columns": {"notval_test_wafer": columns}},
                                          known_tables=known, rejections=rejections)
    return by_table.get("notval_test_wafer") or {}, rejections


# --- the owner's examples, through the declaration --------------------------------------

@pytest.mark.parametrize("written, stored", [
    ("wafer.01", "wafer-01"), ("wafer.1", "wafer-01"), ("mylot.1", "mylot-01"),
    ("wafer_01", "wafer-01"), ("WAFER.1", "WAFER-01"),
    ("wafer.A", "wafer-A"), ("wafer.123", "wafer-123"),
])
def test_the_owners_examples_are_what_a_write_column_stores(val_env, written, stored):
    got, verdict = nn.fold_for_write("notval_test_wafer", "wafer", written)
    assert (got, verdict) == (stored, None)
    assert nn.fold_for_write("notval_test_wafer", "wafer", got) == (got, None), "not idempotent"


def test_today_a_column_rules_object_brings_back_case_true():
    """⚠️ OPEN - asked of 총괄 at the stage-one landing: 451ac4f75's example omits `case` and
    says 「대소문자 그대로」. Today a column `rules` object REPLACES the defaults WITH the
    defaults (guide §2.1), so `case: true` comes back unless written false. This pins today's
    answer so whichever way it is decided, the change is seen."""
    specs, rejections = _refusals({"wafer": {"write": True,
                                             "rules": {"join": "-", "pad_last_number": 2}}})
    assert not rejections
    assert nn.fold_notation("wafer.1", specs["wafer"]["rules"]) == "WAFER-01"


def test_a_column_not_declared_write_is_stored_as_written(val_env):
    assert nn.fold_for_write("notval_test_wafer", "note", "wafer.1") == ("wafer.1", None)
    assert nn.fold_for_write("notval_test_wafer", "lot", "wafer.1") == ("wafer.1", None)
    assert nn.fold_for_write("notval_test_wafer", "wafer", 7) == (7, None)


# --- the alias table ---------------------------------------------------------------------

def test_an_alias_is_looked_up_before_the_rules(val_env):
    aliases = {("notval_test_wafer", "wafer"): {"W#1": "wafer.1", "wafer.7": "wafer-99"},
               ("notval_test_wafer", "lot"): {"wafer.2": "never"}}
    assert nn.fold_for_write("notval_test_wafer", "wafer", "W#1", aliases) == ("wafer-01", None)
    assert nn.fold_for_write("notval_test_wafer", "wafer", "wafer.7", aliases) == \
        ("wafer-99", None)
    assert nn.fold_for_write("notval_test_wafer", "wafer", "wafer.2", aliases) == \
        ("wafer-02", None), "another column's alias applied"


def test_the_alias_table_is_read_per_column(val_env):
    db = val_env
    rows = [{"table_name": "notval_test_wafer", "column_name": "wafer", "written": "W#1",
             "canonical": "wafer.1"},
            {"table_name": "notval_test_wafer", "column_name": "lot", "written": "L#1",
             "canonical": "mylot.1"},
            {"table_name": "notval_test_wafer", "column_name": "wafer", "written": "W#2"}]
    crud.apply_batch_updates(db, NOTATION_ALIAS_TABLE, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=r, source_name="user", updated_by="test")
                 for r in rows], silent=True))
    assert nn.aliases_by_column(db) == {
        ("notval_test_wafer", "wafer"): {"W#1": "wafer.1"},
        ("notval_test_wafer", "lot"): {"L#1": "mylot.1"}}


# --- time ---------------------------------------------------------------------------------

@pytest.mark.parametrize("written, stored, verdict", [
    ("2026-09-26 13:05:07", "2026-09-26 13:05:07", "already"),
    ("2026/09/26 13:05:07", "2026-09-26 13:05:07", "folded"),
    ("26.09.2026 13:05", "2026-09-26 13:05:00", "folded"),
    ("yesterday", "yesterday", "unmatched"),
    ("2026-09-26T13:05:07+09:00", "2026-09-26T13:05:07+09:00", "zoned"),
    ("", "", "blank"),
])
def test_the_time_rule_names_what_it_did(val_env, written, stored, verdict):
    assert nn.fold_for_write("notval_test_wafer", "seen_at", written) == (stored, verdict)


def test_a_format_that_reads_fractions_keeps_them():
    spec = {"from": ["%Y/%m/%d %H:%M:%S.%f"]}
    assert nn.fold_time("2026/09/26 13:05:07.250000", spec) == \
        ("2026-09-26 13:05:07.250000", "folded")


def test_the_smallest_stored_time_is_the_earliest():
    """The reason for one shape: `min` over the stored text is the earliest moment."""
    spec = {"from": ["%Y/%m/%d %H:%M:%S", "%d.%m.%Y %H:%M"]}
    written = ["26.09.2026 09:00", "2026/09/25 23:59:59", "2026-09-26 08:00:00",
               "01.10.2026 00:00"]
    stored = [nn.fold_time(w, spec)[0] for w in written]
    assert min(stored) == min(datetime.strptime(s, TS_FMT) for s in stored).strftime(TS_FMT)
    assert min(stored) == "2026-09-25 23:59:59"
    assert min(written) != "2026-09-25 23:59:59", "the fixture does not need the fold"


# --- the declaration check ------------------------------------------------------------------

@pytest.mark.parametrize("rules, says", [
    ({"join": "/"}, "rule 'join' must be one of"),
    ({"pad_last_number": 10}, "must be a width from 1 to 9"),
    ({"pad_last_number": True}, "must be a width from 1 to 9"),
    ({"replace": [["W|WA", "wafer"]]}, "'|' picks a different match"),
    ({"replace": [["a*(ab)?", "x"]]}, "a count after ')'"),
    ({"replace": [["a+?b", "x"]]}, "a count after a count"),
    ({"replace": [["WF$", "x"]]}, "use \\Z"),
    ({"replace": [["\\d+", "x"]]}, "\\d reads differently"),
    ({"replace": [["[[:digit:]]", "x"]]}, "a '[' inside [...]"),
    ({"replace": [["a{", "x"]]}, "'{' is a count"),
    ({"replace": [["a*", "x"]]}, "matches an empty value"),
    ({"replace": [["a", "\\n"]]}, "may only use \\1 to \\9"),
])
def test_a_value_rule_outside_the_shared_language_is_refused_by_name(rules, says):
    _specs, rejections = _refusals({"wafer": {"rules": rules}})
    assert len(rejections) == 1 and says in rejections[0]["detail"], rejections


@pytest.mark.parametrize("spec, says", [
    ({"rules": {"time": {"from": ["%Y/%m/%d"]}}}, "declare \"write\": true"),
    ({"write": True, "rules": {"time": {"from": ["%Y/%m/%d"]}, "join": "-"}},
     "'time' is the only rule"),
    ({"write": True, "rules": {"time": {"from": ["%Y-%m-%dT%H:%M:%S%z"]}}}, "time zone"),
])
def test_a_time_column_is_refused_unless_written_and_alone(spec, says):
    specs, rejections = _refusals({"seen_at": spec})
    assert "seen_at" not in specs or not specs["seen_at"]["rules"].get("time")
    assert any(says in r["detail"] for r in rejections), rejections


def test_a_join_that_would_split_a_stored_key_is_refused():
    specs, rejections = _refusals({
        "wafer": {"write": True, "rules": {"join": "_"}},      # composite key separator
        "lot": {"write": True, "rules": {"join": "_"}},        # map key joiner
        "note": {"write": True, "rules": {"join": "_"}},       # in no key
    })
    assert sorted(r["subject"] for r in rejections
                  if r["code"] == nn.CODE_JOIN_SPLITS_KEY) == [
        "notval_test_wafer.lot", "notval_test_wafer.wafer"]
    assert set(specs) == {"note"}
    specs, rejections = _refusals({"wafer": {"write": True, "rules": {"join": "-"}},
                                   "lot": {"rules": {"join": "_"}}})
    assert not rejections and set(specs) == {"wafer", "lot"}, \
        "a different join, or a comparison-only column, stores nothing that splits a key"


def test_the_resolve_report_says_why_a_join_was_refused(val_env, tmp_path, monkeypatch):
    import config_resolve_report as crr
    _declare(tmp_path, monkeypatch, {"wafer": {"write": True, "rules": {"join": "_"}}})
    rejected = crr._resolve_notation()["rejected"]
    assert [e["subject"] for e in rejected] == ["notval_test_wafer.wafer"]
    assert rejected[0]["detail"].startswith("Refused: the join character is the one")


def test_one_join_takes_one_value_rule_from_both_sides(val_env, tmp_path, monkeypatch):
    _declare(tmp_path, monkeypatch, {"wafer": {"rules": OWNER},
                                     "note": {"rules": dict(OWNER, join=".")}})
    with pytest.raises(ValueError, match="rule 'join' differs"):
        nn.join_pair_rules("notval_test_wafer", "wafer", "notval_test_wafer", "note")
    assert nn.join_pair_rules("notval_test_wafer", "wafer", "notval_test_wafer", "wafer") == \
        {"zero_pad": False, "separator": True, "case": False, "join": "-",
         "pad_last_number": 2}


# --- the write preview ------------------------------------------------------------------------

def test_the_write_preview_shows_what_would_be_stored(val_env):
    import config_resolve_report as crr
    db = val_env
    rows = [("L1", "wafer.1", "2026/09/26 13:05:07"), ("L2", "wafer.1", "yesterday"),
            ("L3", "wafer-01", "2026-09-26T13:05:07Z"), ("L4", "W#9", "26.09.2026 13:05")]
    crud.apply_batch_updates(db, "notval_test_wafer", schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates={"lot": lot, "wafer": w, "seen_at": t},
                                           source_name="user", updated_by="test")
                 for lot, w, t in rows], silent=True))
    crud.apply_batch_updates(db, NOTATION_ALIAS_TABLE, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(
            updates={"table_name": "notval_test_wafer", "column_name": "wafer",
                     "written": "W#9", "canonical": "wafer.1"},
            source_name="user", updated_by="test")], silent=True))

    wafer = nn.fold_preview(db, "notval_test_wafer", "wafer")
    assert wafer["write"] is True
    assert [(g["folded"], sorted(v["raw"] for v in g["variants"]))
            for g in wafer["merge_groups"]] == [("wafer-01", ["W#9", "wafer-01", "wafer.1"])]

    seen = nn.fold_preview(db, "notval_test_wafer", "seen_at")
    assert seen["time_left_as_is"] == {"unmatched": 1, "zoned": 1}
    assert "The time rule leaves rows as written - no matching format: 1, time zone " \
           "written: 1." in crr.notation_preview_detail(seen)
