"""[filename_rules] Declaration-driven extraction from a nested source path.

Nested files are ingested IN PLACE, so the parser is handed the real path
(`directory_watcher.relative_source_path` → POSIX, relative to raws/) and
`filename_rules` is the channel that turns folder names into columns. Two halves,
verified as one contract:

A. The SUBJECT contract — the declaration sees a relative, POSIX path, so a rule
   is portable between machines and "/" is an inherently structural separator (it
   cannot occur inside a directory name). A bare filename is the degenerate case,
   which is why there is ONE mechanism and not a sibling `path_rules`.
B. The MECHANISM contract — nothing a declaration asked for goes missing
   silently:
     - declared and absent          -> `no_match`, reported
     - matched two distinct values  -> `ambiguous_reference`, REFUSED not resolved
     - matched but uncastable       -> `cast_failed`, reported (not stored as None)
     - `required: true` unmet       -> the whole file yields 0 rows
     - malformed declaration        -> RuleDeclarationError at LOAD, named reason
                                       (a group-less regex is a declaration error,
                                       not an IndexError at parse time)
     - row disagrees with the path  -> `file_overrides_path`, COUNTED not blocked
                                       (ruling 2026-07-30: "파일이 정본")
"""

import json
import os
import re
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

from advanced_ingester import (
    AdvancedIngester,
    RuleDeclarationError,
    REASON_AMBIGUOUS,
    REASON_CAST_FAILED,
    REASON_FILE_OVERRIDES_PATH,
    REASON_NO_MATCH,
    REASON_PATH_OVERRIDES_HEADER,
)

# ---------------------------------------------------------------------------
# The worked example. The user's structures vary too much for a positional
# depth->column map ("너무 다양해서 케이스 하나 못정함"), so the patterns are
# VALUE-SHAPED and position-independent — they match wherever the token lands, at
# whatever depth, because `re.search` does not care.
# ---------------------------------------------------------------------------
LOT_RULE = {"column": "lot_id", "regex": r"(LOT-[A-Z]\d+)", "type": "str"}
EQP_RULE = {"column": "eqp_id", "regex": r"(EQP-\d+)", "type": "str"}
DATE_RULE = {"column": "run_date", "regex": r"(\d{8})", "type": "str"}

# Positional variants, for the (rarer) case where an operator knows the depth of a
# particular drop. "/" is the separator and cannot occur inside a folder name, so
# `[^/]+` is exactly one component — no invented separator, nothing to sanitize.
LV1_RULE = {"column": "folder_1", "regex": r"^([^/]+)/"}
LV2_RULE = {"column": "folder_2", "regex": r"^[^/]+/([^/]+)/"}


def _ingester(tmp_path, **config):
    config.setdefault("table_name", "fnr_test_metrics")
    config.setdefault("business_key_column", "sensor_id")
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return AdvancedIngester(str(path))


# ===========================================================================
# A. Subject contract — the worked declaration against a real relative path
# ===========================================================================

def test_worked_example_extracts_two_folder_levels_from_a_nested_path(tmp_path):
    """The subject is what the watcher produces for
    raws/LOT-A1/EQP-7/user(kim)measure.csv."""
    ing = _ingester(tmp_path, filename_rules=[LV1_RULE, LV2_RULE, LOT_RULE, EQP_RULE])
    data, refusal = ing.extract_path_metadata("LOT-A1/EQP-7/user(kim)measure.csv")
    assert refusal is None
    assert data == {
        "folder_1": "LOT-A1", "folder_2": "EQP-7",
        "lot_id": "LOT-A1", "eqp_id": "EQP-7",
    }


def test_value_shaped_rules_match_at_any_depth(tmp_path):
    ing = _ingester(tmp_path, filename_rules=[LOT_RULE, EQP_RULE, DATE_RULE])
    for subject in (
        "LOT-A1/EQP-7/20260730_run.csv",
        "EQP-7/sub/LOT-A1/20260730.csv",
        "20260730/LOT-A1_EQP-7.csv",
        "site/20260730/deep/deeper/LOT-A1/EQP-7/x.csv",
    ):
        data, refusal = ing.extract_path_metadata(subject)
        assert refusal is None
        assert data == {
            "lot_id": "LOT-A1", "eqp_id": "EQP-7", "run_date": "20260730",
        }, subject


def test_the_subject_is_relative_and_posix_so_a_rule_is_portable(tmp_path):
    """An absolute path would drag the machine's layout into the declaration and a
    backslash would have to be written as four characters in JSON. Both are why
    the watcher hands over a relative POSIX path — asserted here as the contract
    the declaration side depends on."""
    ing = _ingester(tmp_path, filename_rules=[LV1_RULE])
    assert ing.extract_path_metadata("LOT-A1/EQP-7/x.csv")[0] == {"folder_1": "LOT-A1"}
    # A dev-machine absolute path would make the SAME rule read the drive letter.
    absolute = "C:/Users/kk980/Developments/assyManager/server/ingestion_workspace/t/raws/LOT-A1/x.csv"
    assert ing.extract_path_metadata(absolute)[0] == {"folder_1": "C:"}
    # ...and a backslash subject would not split into components at all.
    assert ing.extract_path_metadata("LOT-A1\\EQP-7\\x.csv")[0] == {}


def test_a_bare_filename_is_the_degenerate_case(tmp_path):
    """One mechanism, not two: a file directly in raws/ has zero directories, so a
    positional rule simply finds nothing and a value-shaped rule still works."""
    ing = _ingester(tmp_path, filename_rules=[LV1_RULE, LOT_RULE])
    data, refusal = ing.extract_path_metadata("LOT-A1_measure.csv")
    assert data == {"lot_id": "LOT-A1"}  # no folder_1 — there is no folder
    assert refusal is None


def test_process_file_defaults_to_the_basename_when_no_rel_path_is_given(tmp_path):
    """The existing caller (a user script calling process_file(path)) is unchanged:
    omitting rel_path reproduces today's basename behaviour exactly."""
    ing = _ingester(
        tmp_path,
        filename_rules=[LV1_RULE, LOT_RULE],
        rules=[{"column": "sensor_id", "regex": r"ID: (S-\d+)", "type": "str"}],
    )
    nested = tmp_path / "LOT-A1" / "EQP-7"
    nested.mkdir(parents=True)
    src = nested / "m.csv"
    src.write_text("ID: S-1\n", encoding="utf-8")

    # No rel_path -> the subject is "m.csv": neither rule can see the folders.
    assert ing.process_file(str(src))[0].get("folder_1") is None
    assert "lot_id" not in ing.process_file(str(src))[0]
    # With rel_path -> the folder names become columns.
    row = ing.process_file(str(src), rel_path="LOT-A1/EQP-7/m.csv")[0]
    assert row["folder_1"] == "LOT-A1" and row["lot_id"] == "LOT-A1"


# ===========================================================================
# B1. Absence is reported, never blank
# ===========================================================================

def test_declared_and_absent_is_reported_not_blank(tmp_path, caplog):
    ing = _ingester(tmp_path, filename_rules=[LOT_RULE])
    issues = []
    with caplog.at_level("WARNING"):
        data, refusal = ing.extract_path_metadata("plain/run.csv", issues=issues)
    # The column is ABSENT from the payload — it is not set to None/"".
    assert data == {} and "lot_id" not in data
    assert refusal is None
    assert len(issues) == 1
    assert issues[0]["column"] == "lot_id"
    assert issues[0]["reason"] == REASON_NO_MATCH
    assert issues[0]["filename"] == "plain/run.csv"
    # A run that lost the column does not look like a run that matched.
    assert any(REASON_NO_MATCH in r.message for r in caplog.records)


def test_matched_but_uncastable_is_reported_not_stored_as_none(tmp_path):
    ing = _ingester(
        tmp_path,
        filename_rules=[{"column": "run_no", "regex": r"run(\w+)", "type": "int"}],
    )
    issues = []
    data, refusal = ing.extract_path_metadata("b/runABC.csv", issues=issues)
    assert data == {}  # would previously have been {"run_no": None}
    assert refusal is None
    assert issues[0]["reason"] == REASON_CAST_FAILED
    assert issues[0]["raw_value"] == "ABC"


# ===========================================================================
# B2. Ambiguity is refused, not resolved
# ===========================================================================

def test_two_distinct_values_are_refused_as_ambiguous_reference(tmp_path):
    ing = _ingester(tmp_path, filename_rules=[LOT_RULE])
    issues = []
    data, refusal = ing.extract_path_metadata("LOT-A1/LOT-B2/run.csv", issues=issues)
    # re.search would have silently taken "LOT-A1". Nothing is stored.
    assert data == {}
    assert refusal is None  # not required -> reported, file still ingests
    assert issues[0]["reason"] == REASON_AMBIGUOUS
    assert issues[0]["values"] == ["LOT-A1", "LOT-B2"]
    # One vocabulary for one state, shared with the enrichment classification.
    from enrichment_analysis import CLS_AMBIGUOUS
    assert REASON_AMBIGUOUS == CLS_AMBIGUOUS


def test_the_same_value_twice_is_not_ambiguity(tmp_path):
    """DISTINCT values, not match count: a lot id repeated at two path levels is
    one answer stated twice, and refusing it would be a false refusal."""
    ing = _ingester(tmp_path, filename_rules=[LOT_RULE])
    issues = []
    data, refusal = ing.extract_path_metadata("LOT-A1/LOT-A1_retest/run.csv", issues=issues)
    assert data == {"lot_id": "LOT-A1"}
    assert issues == [] and refusal is None


# ===========================================================================
# B3. required: default false (no-op), true refuses the file
# ===========================================================================

def test_required_defaults_to_false_so_nothing_existing_changes(tmp_path):
    ing = _ingester(tmp_path, filename_rules=[LOT_RULE])
    assert ing.filename_rules[0]["required"] is False
    data, refusal = ing.extract_path_metadata("nothing/here.csv")
    assert data == {} and refusal is None  # reported, but not a refusal


@pytest.mark.parametrize("rel_path,reason", [
    ("b/nolot.csv", REASON_NO_MATCH),
    ("LOT-A1/LOT-B2/run.csv", REASON_AMBIGUOUS),
])
def test_required_column_unmet_yields_zero_rows(tmp_path, rel_path, reason):
    required_lot = dict(LOT_RULE, required=True)
    row_rule = [{"column": "sensor_id", "regex": r"ID: (S-\d+)", "type": "str"}]
    src = tmp_path / "m.csv"
    src.write_text("ID: S-1\nID: S-2\n", encoding="utf-8")

    ing = _ingester(tmp_path, filename_rules=[required_lot], rules=row_rule)
    issues = []
    rows = ing.process_file(str(src), rel_path=rel_path, issues=issues)
    assert rows == []  # a row without a required path column is not trustworthy
    assert any(i["reason"] == reason and i["required"] for i in issues)

    # Same file, same pattern, required omitted -> rows flow (proves the refusal
    # came from `required` and not from the pattern).
    ing2 = _ingester(tmp_path, filename_rules=[LOT_RULE], rules=row_rule)
    assert len(ing2.process_file(str(src), rel_path=rel_path)) == 2


# ===========================================================================
# B4. Malformed declaration fails at LOAD with a named reason
# ===========================================================================

def test_regex_without_a_capture_group_is_a_load_error_not_an_indexerror(tmp_path):
    with pytest.raises(RuleDeclarationError) as e:
        _ingester(tmp_path, filename_rules=[{"column": "lot_id", "regex": r"LOT-\d+"}])
    msg = str(e.value)
    assert "filename_rules[0]" in msg and "no capture group" in msg
    # The same hole is closed in the other two rule families (identical shape).
    for family in ("rules", "header_rules"):
        with pytest.raises(RuleDeclarationError) as e2:
            _ingester(tmp_path, **{family: [{"column": "c", "regex": r"nogroup"}]})
        assert f"{family}[0]" in str(e2.value)


@pytest.mark.parametrize("rule,needle", [
    ({"column": "lot_id", "rexeg": r"(LOT-\d+)"}, "unknown key(s) ['rexeg']"),
    ({"column": "", "regex": r"(x)"}, "'column' must be a non-empty string"),
    ({"column": "c"}, "'regex' must be a non-empty string"),
    ({"column": "c", "regex": r"([unclosed"}, "does not compile"),
    ({"column": "c", "regex": r"(x)", "type": "date"}, "unknown type 'date'"),
    ({"column": "c", "regex": r"(x)", "required": "yes"}, "'required' must be a boolean"),
])
def test_each_malformed_declaration_names_its_reason(tmp_path, rule, needle):
    with pytest.raises(RuleDeclarationError) as e:
        _ingester(tmp_path, filename_rules=[rule])
    assert needle in str(e.value)


def test_duplicate_column_in_one_family_is_refused(tmp_path):
    with pytest.raises(RuleDeclarationError) as e:
        _ingester(tmp_path, filename_rules=[LOT_RULE, dict(LOT_RULE, regex=r"(LOT-\d+)")])
    assert "declared twice" in str(e.value)


def test_the_live_sensor_config_still_loads(tmp_path):
    """The one real AdvancedIngester config in the repo must survive the new
    validation — the strict schema was chosen to fit what is actually declared."""
    live = os.path.join(
        server_dir, "ingestion_workspace", "sensor_metrics", "config", "sensor_config.json"
    )
    if not os.path.exists(live):
        pytest.skip("user workspace config not present (gitignored)")
    ing = AdvancedIngester(live)
    assert [r["column"] for r in ing.rules] == [
        "sensor_id", "temperature", "humidity", "vibration"
    ]
    assert ing.filename_rules == []  # zero live filename_rules


# ===========================================================================
# B5. Precedence — the file is authoritative; disagreement is counted
# ===========================================================================

def _conflict_ingester(tmp_path):
    return _ingester(
        tmp_path,
        filename_rules=[LOT_RULE],
        rules=[
            {"column": "sensor_id", "regex": r"ID: (S-\d+)", "type": "str"},
            {"column": "lot_id", "regex": r"lot=(LOT-[A-Z]\d+)", "type": "str"},
        ],
    )


def test_path_fills_the_column_only_where_the_row_does_not_carry_it(tmp_path):
    ing = _conflict_ingester(tmp_path)
    src = tmp_path / "m.csv"
    src.write_text("ID: S-1\nID: S-2 lot=LOT-B2\n", encoding="utf-8")
    issues = []
    rows = ing.process_file(str(src), rel_path="LOT-A1/m.csv", issues=issues)

    assert len(rows) == 2
    assert rows[0]["lot_id"] == "LOT-A1"   # row silent -> path fills it
    assert rows[1]["lot_id"] == "LOT-B2"   # row speaks -> the FILE wins
    # Counted, never blocking: both rows were ingested.
    conflicts = [i for i in issues if i["reason"] == REASON_FILE_OVERRIDES_PATH]
    assert len(conflicts) == 1
    assert conflicts[0]["column"] == "lot_id"
    assert conflicts[0]["count"] == 1
    assert conflicts[0]["path_value"] == "LOT-A1"
    assert conflicts[0]["example_row_value"] == "LOT-B2"
    # A disagreement is NOT ambiguity — here an authority exists, so only the
    # observation was missing. The two states stay named differently.
    assert REASON_FILE_OVERRIDES_PATH != REASON_AMBIGUOUS


def test_agreement_costs_nothing_and_reports_nothing(tmp_path):
    ing = _conflict_ingester(tmp_path)
    src = tmp_path / "m.csv"
    src.write_text("ID: S-1 lot=LOT-A1\n", encoding="utf-8")
    issues = []
    rows = ing.process_file(str(src), rel_path="LOT-A1/m.csv", issues=issues)
    assert rows[0]["lot_id"] == "LOT-A1"
    assert issues == []
    # No overlap at all -> the per-row check is not even reachable.
    plain = _ingester(tmp_path, filename_rules=[LOT_RULE],
                      rules=[{"column": "sensor_id", "regex": r"ID: (S-\d+)"}])
    assert plain._row_overlap == set() and plain._header_overlap == set()


def test_merge_order_is_the_declared_ruling(tmp_path):
    """header < filename < row. Pinned so a later 'simplification' of the merge
    cannot invert a ruling without going red."""
    ing = _conflict_ingester(tmp_path)
    merged = ing._merge_row({"lot_id": "header"}, {"lot_id": "path"}, {"lot_id": "row"})
    assert merged["lot_id"] == "row"
    assert ing._merge_row({"lot_id": "h"}, {"lot_id": "path"}, {})["lot_id"] == "path"
    assert ing._merge_row({"lot_id": "h"}, {}, {})["lot_id"] == "h"


def test_a_silent_row_does_not_null_out_the_path_value(tmp_path):
    """`parse_line` emits every declared column on every row, using None for the
    rules that did not match. A plain dict merge therefore let a SILENT row write
    that None over the path value — the fill half of the ruling never happened."""
    ing = _conflict_ingester(tmp_path)
    # This is exactly what parse_line produces for a line with no lot= token.
    row_data = {"sensor_id": "S-1", "lot_id": None}
    assert ing._merge_row({}, {"lot_id": "LOT-A1"}, row_data)["lot_id"] == "LOT-A1"
    assert ing._merge_row({"lot_id": "LOT-H"}, {}, row_data)["lot_id"] == "LOT-H"
    # A declared non-None `default` IS a value the declaration provides -> it wins.
    ing2 = _ingester(
        tmp_path,
        filename_rules=[LOT_RULE],
        rules=[{"column": "lot_id", "regex": r"lot=(LOT-[A-Z]\d+)", "default": "LOT-Z0"}],
    )
    assert ing2._merge_row({}, {"lot_id": "LOT-A1"}, {"lot_id": "LOT-Z0"})["lot_id"] == "LOT-Z0"
    # No overlap -> the fill pass is unreachable and a None column stays None,
    # exactly as before (a column nobody else can supply is still reported blank).
    plain = _ingester(tmp_path, rules=[{"column": "c", "regex": r"(x)"}])
    assert plain._fill_merge_cols == set()
    assert plain._merge_row({}, {}, {"c": None}) == {"c": None}


def test_path_over_header_overlap_is_named_rather_than_inferred(tmp_path, caplog):
    """The merge order makes the PATH win over the file's own header. Left as-is
    (the ruling was given for file ROWS vs path) but surfaced, not inferred from
    dict order."""
    with caplog.at_level("WARNING"):
        ing = _ingester(
            tmp_path,
            filename_rules=[LOT_RULE],
            header_rules=[{"column": "lot_id", "regex": r"Lot: (LOT-[A-Z]\d+)"}],
        )
    assert ing._header_overlap == {"lot_id"}
    assert any("PATH value wins" in r.message for r in caplog.records)

    src = tmp_path / "m.csv"
    src.write_text("Lot: LOT-B2\nID: S-1\n", encoding="utf-8")
    issues = []
    ing.process_file(str(src), rel_path="LOT-A1/m.csv", issues=issues)
    assert [i["reason"] for i in issues] == [REASON_PATH_OVERRIDES_HEADER]
    assert issues[0]["path_value"] == "LOT-A1"
    assert issues[0]["header_value"] == "LOT-B2"


# ===========================================================================
# Regression guard: the collector is optional and changes nothing
# ===========================================================================

def test_issues_collector_is_optional_and_does_not_change_the_return(tmp_path):
    ing = _ingester(
        tmp_path,
        filename_rules=[LOT_RULE],
        rules=[{"column": "sensor_id", "regex": r"ID: (S-\d+)", "type": "str"}],
    )
    src = tmp_path / "m.csv"
    src.write_text("ID: S-1\n", encoding="utf-8")
    assert ing.process_file(str(src), rel_path="nolot/m.csv") \
        == ing.process_file(str(src), rel_path="nolot/m.csv", issues=[])
