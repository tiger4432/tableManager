"""VOID SCHEMA - the declarations, the format reader and the ingest gate.

Scope note: the end-to-end proof (real watcher -> real upsert -> real
`GET /tables/{t}/data`, on PostgreSQL) is not here, because `assemble_composite
_business_key`, the unique index and the read path all need a real database and
the suite runs on sqlite. What IS here is everything that can be wrong without
one, plus the two DRIFT PINS that no end-to-end run would catch: this module
computes a key the platform also computes, and judges a row with a stand-in for
the object `crud` expects. Both are re-derived here from the platform's own
implementation, so a change on either side fails a test instead of quietly
producing voids that point at a run nobody wrote.
"""
import io
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "parsers")))

import void_sat_format as vsf                                      # noqa: E402
from database import crud, schemas                                 # noqa: E402

VOID, RUN = "void_obs", "inspection_run"

# 🔴 READ FROM THE FILE, NOT FROM `crud.TABLE_CONFIG`, and read it at IMPORT.
#
# `table_config.json` is the authority; `crud.TABLE_CONFIG` is a process
# singleton that other test modules REPLACE and do not restore -
# `test_runtime_table_create.py` monkeypatches `load_table_config` to a reduced
# config, and whatever ran last wins. These tests passed alone and failed in the
# suite for exactly that reason. Reading the file removes the dependency on test
# ORDER, and reading it during collection (before any test body runs) removes
# the dependency on whoever mutates the singleton first.
_CONFIG_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "config", "table_config.json"))
DECLARED = {t: cfg for t, cfg in
            json.load(io.open(_CONFIG_PATH, encoding="utf-8")).items()
            if t in (VOID, RUN)}


@pytest.fixture(autouse=True)
def _void_tables_declared():
    """Put the two declarations into the singleton for tests that need it.

    `crud.unfilled_key_columns` and `assemble_composite_business_key` both read
    `crud.TABLE_CONFIG`, so the gate cannot be exercised without it. Restores
    whatever was there, so this fixture does not become the next module's
    contamination.
    """
    previous = {t: crud.TABLE_CONFIG.get(t) for t in (VOID, RUN)}
    crud.TABLE_CONFIG.update(DECLARED)
    yield
    for table, value in previous.items():
        if value is None:
            crud.TABLE_CONFIG.pop(table, None)
        else:
            crud.TABLE_CONFIG[table] = value

HEADER = ("# observed_at: 2026-08-13 04:12:07\n"
          "# eqp_id: SAT-02\n"
          "# recipe_id: VOID_5PCT_R3\n"
          "# unit: um\n")
COLUMNS = "base wafer id,base_x,base_y,inchip_x,inchip_y,gate,radius_x,radius_y\n"
BODY = ("BW-1,12,34,101.5,220.25,3,4.75,2.5\n"
        "BW-1,12,34,140,180,3,1.25,1.125\n")


@pytest.fixture(autouse=True)
def _clean_counters():
    vsf.reset_counters()
    yield
    vsf.reset_counters()


def write(tmp_path, name, text):
    path = tmp_path / name
    io.open(str(path), "w", encoding="utf-8", newline="").write(text)
    return str(path)


# ---------------------------------------------------------------- declarations
def test_both_tables_are_declared_and_obey_R1():
    """R1: assigned names are strings, quantities are numeric."""
    for table in (VOID, RUN):
        assert table in DECLARED, f"{table} is not declared"

    void_types = DECLARED[VOID]["column_types"]
    run_types = DECLARED[RUN]["column_types"]

    # Identifiers. `base_wafer_id` is the one the proposal calls out by name:
    # it is a name a tool assigned, so a numeric column could not hold it and
    # would drop a leading zero if it could.
    for name in ("void_uid", "run_uid", "base_wafer_id", "unit"):
        assert void_types[name] == "string", name
    for name in ("run_uid", "method", "base_wafer_id", "recipe_id", "eqp_id"):
        assert run_types[name] == "string", name

    # Quantities - things arithmetic is done on.
    for name in ("base_x", "base_y", "inchip_x", "inchip_y",
                 "radius_x", "radius_y", "stack_gate"):
        assert void_types[name] == "number", name

    # R5: the inspection time is a real timestamp, not a string that sorts.
    assert run_types["observed_at"] == "datetime"


def test_no_verdict_and_no_area_are_stored():
    """§2-bis's central ruling, as an assertion rather than a comment.

    A stored grade cannot be re-judged when the recipe threshold moves, and a
    stored area is the same mistake one step earlier. Both are computed from
    the geometry at read time; the expression index in
    `add_void_schema_indexes.sql` is what makes that affordable.
    """
    columns = set(DECLARED[VOID]["column_types"])
    forbidden = {"grade", "verdict", "pass_fail", "judgement", "severity",
                 "area", "void_area", "void_yn", "is_fail", "b_bn"}
    assert not (columns & forbidden), f"a derived verdict was stored: {columns & forbidden}"


def test_declared_business_keys_have_a_unique_index_in_the_migration():
    """R2: declaring a business_key OBLIGES an index. Check the shipped SQL.

    Without this the pair can drift the cheap way - someone adds a third table
    to the config and the migration silently keeps covering only two.
    """
    sql = io.open(os.path.join(os.path.dirname(__file__), "..", "migrations",
                               "add_void_schema_indexes.sql"),
                  encoding="utf-8").read()
    reverse = io.open(os.path.join(os.path.dirname(__file__), "..", "migrations",
                                   "add_void_schema_indexes_reverse.sql"),
                      encoding="utf-8").read()
    for table in (VOID, RUN):
        assert DECLARED[table].get("business_key")
        assert f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_bk_{table}" in sql
        # Every forward index must be reversible, or an operator cannot undo it.
        assert f"uq_bk_{table}" in reverse

    forward_names = {line.split("IF NOT EXISTS")[1].strip()
                     for line in sql.splitlines()
                     if "INDEX CONCURRENTLY IF NOT EXISTS" in line}
    for name in forward_names:
        assert f"DROP INDEX CONCURRENTLY IF EXISTS {name};" in reverse, name


def test_map_key_columns_are_deliberately_absent_so_R3_cannot_bite():
    """R3 is satisfied by not declaring map keys - a decision, not an oversight.

    Declaring them would opt these tables into `replace_map` purge scoping,
    whose derived branch WIDENS a purge when a key column is blank (R3's
    incident). A void is a point with continuous coordinates, not a grid cell.
    """
    for table in (VOID, RUN):
        declared = DECLARED[table].get("map_key_columns")
        assert not declared, f"{table} declared map_key_columns: {declared}"
        # And if a later change adds them, R3 must hold on the spot.
        source = DECLARED[table].get("composite_key_source") or []
        assert all(c in source for c in (declared or []))


def test_the_sample_declares_the_same_thing_as_the_live_config():
    """`server/config/*` is gitignored, so `.sample` is what actually ships."""
    here = os.path.join(os.path.dirname(__file__), "..", "config")
    sample = json.load(io.open(os.path.join(
        here, "sample", "table_config.json.sample"),
        encoding="utf-8"))
    for table in (VOID, RUN):
        assert table in sample, f"{table} is missing from table_config.json.sample"
        assert sample[table]["column_types"] == DECLARED[table]["column_types"]
        assert sample[table]["composite_key_source"] == \
            DECLARED[table]["composite_key_source"]


# ---------------------------------------------------------------- drift pins
def test_compose_business_key_is_the_platforms_own_key_not_a_second_join():
    """`void_obs.run_uid` must equal the key `inspection_run` lands under.

    If these two ever diverge, both tables still load and nothing errors - the
    voids simply reference a run that does not exist. That failure is invisible
    at write time, which is why it is pinned here.
    """
    run_row = {"method": vsf.METHOD, "base_wafer_id": "BW-1", "base_x": 12.0,
               "base_y": 34.0, "stack_gate": 3.0,
               "observed_at": "2026-08-13T04:12:07+09:00"}

    item = schemas.GeneralUpdateItem(updates=dict(run_row))
    assert crud.assemble_composite_business_key(RUN, item) is True
    platform_key = item.business_key_val

    assert vsf.compose_run_uid("BW-1", 12.0, 34.0, 3.0,
                               "2026-08-13T04:12:07+09:00") == platform_key
    # And the separator/order really do come from the config, not from a literal.
    assert platform_key.startswith(vsf.METHOD)
    assert DECLARED[RUN]["composite_key_separator"] in platform_key


def test_the_gate_shim_judges_exactly_as_a_real_update_item_does():
    """`_Judged` stands in for `GeneralUpdateItem`; pin them to one verdict.

    A shim that grew stale would not raise - `unfilled_key_columns` would just
    stop finding the attribute it wanted and start accepting everything.
    """
    rows = [
        {"run_uid": "R|1", "inchip_x": 1.0, "inchip_y": 2.0},   # keyed
        {"run_uid": "R|1", "inchip_x": None, "inchip_y": 2.0},  # blank part
        {"run_uid": "", "inchip_x": 1.0, "inchip_y": 2.0},      # blank part
        {},                                                      # nothing at all
    ]
    for row in rows:
        via_shim = crud.unfilled_key_columns(VOID, vsf._Judged(dict(row)))
        via_real = crud.unfilled_key_columns(
            VOID, schemas.GeneralUpdateItem(updates=dict(row)))
        assert via_shim == via_real, row


# ---------------------------------------------------------------- the gate
def _capture(caplog):
    caplog.set_level(logging.INFO, logger="void_sat_format")
    return caplog


GOOD = {"run_uid": "R|1", "base_wafer_id": "BW-1", "base_x": 1.0, "base_y": 2.0,
        "stack_gate": 3.0, "inchip_x": 10.0, "inchip_y": 20.0,
        "radius_x": 1.0, "radius_y": 1.0, "unit": "um"}


def test_a_blank_key_column_is_refused_counted_and_named(caplog):
    _capture(caplog)
    kept, report = vsf.screen(VOID, [GOOD, dict(GOOD, inchip_x=None)],
                              source="scan.csv")

    assert len(kept) == 1 and report["refused_rows"] == 1
    assert report["by_reason"] == {vsf.REFUSAL_UNKEYED_ROW: 1}
    # Counted for the life of the process, so another process can ask.
    assert vsf.refused_rows() == {VOID: 1}
    assert vsf.refusals() == {(VOID, vsf.REFUSAL_UNKEYED_ROW): 1}
    # The operator's log names the COLUMN - "some key is missing" is not
    # actionable at 3am.
    assert "inchip_x" in caplog.text
    assert "REFUSED 1 of 2" in caplog.text
    assert vsf.note() and "rows=1" in vsf.note()


def test_the_gate_stays_quiet_and_keeps_everything_when_nothing_is_wrong(caplog):
    """The other half of the previous test: a gate that refuses everything
    would pass it too."""
    _capture(caplog)
    kept, report = vsf.screen(VOID, [GOOD, dict(GOOD, inchip_x=77.0)])
    assert len(kept) == 2 and report["refused_rows"] == 0
    assert vsf.refusals() == {} and vsf.note() is None
    assert caplog.text == ""


@pytest.mark.parametrize("row, reason, named", [
    (dict(GOOD, unit="nanometres"), vsf.REFUSAL_UNDECLARED_UNIT, "nanometres"),
    (dict(GOOD, unit=None), vsf.REFUSAL_UNDECLARED_UNIT, "None"),
    (dict(GOOD, stack_gate=3.5), vsf.REFUSAL_NON_INTEGRAL_GATE, "3.5"),
])
def test_undeclared_vocabulary_and_fractional_layers_are_refused_by_value(
        row, reason, named, caplog):
    """A unit nobody declared silently mixes two machines' numbers, and the
    physical `double precision` column cannot forbid layer 3.5 - so this does."""
    _capture(caplog)
    _kept, report = vsf.screen(VOID, [row])
    assert report["by_reason"] == {reason: 1}
    assert named in caplog.text, caplog.text


def test_two_voids_at_one_location_in_one_file_do_not_silently_merge(caplog):
    """The upsert would fold them into one row and a real void would vanish
    with no error. The first is kept; the rest are refused and named."""
    _capture(caplog)
    kept, report = vsf.screen(VOID, [GOOD, dict(GOOD), dict(GOOD, inchip_x=99.0)])
    assert len(kept) == 2
    assert report["by_reason"] == {vsf.REFUSAL_DUPLICATE_LOCATION: 1}
    assert "already used by row 0" in caplog.text


def test_refusal_detail_is_capped_but_the_count_never_is(caplog):
    """Every detail comes from a payload, so a malformed source must not be
    able to grow the report without limit - but the COUNT is the operator's
    actual question and is never capped."""
    _capture(caplog)
    many = [dict(GOOD, inchip_x=None, inchip_y=float(i)) for i in range(60)]
    _kept, report = vsf.screen(VOID, many)
    assert report["refused_rows"] == 60
    assert len(report["rows"]) == vsf.MAX_REFUSAL_ROWS
    assert report["rows_omitted"] == 60 - vsf.MAX_REFUSAL_ROWS
    assert vsf.refused_rows() == {VOID: 60}


# ---------------------------------------------------------------- the format
@pytest.mark.parametrize("spelling", [
    "base wafer id", "BASE WAFER ID", "Base_Wafer_Id", "base-wafer-id",
    "basewaferid",
])
def test_header_spelling_variance_we_do_not_control_is_absorbed(spelling):
    resolved, _unknown = vsf.resolve_columns(
        [spelling, "base_x", "base_y", "inchip_x", "inchip_y", "gate",
         "radius_x", "radius_y"])
    assert resolved["base_wafer_id"] == 0


def test_an_unresolvable_header_is_refused_and_never_read_by_position():
    """A silently mis-mapped `radius_x` is a wrong number that looks right."""
    with pytest.raises(vsf.UnreadableHeader) as exc:
        vsf.resolve_columns(["base wafer id", "base_x", "base_y", "inchip_x",
                             "inchip_y", "gate", "WIDTH", "radius_y"])
    assert "radius_x" in str(exc.value)     # what was missing
    assert "WIDTH" in str(exc.value)        # what was actually there


def test_two_columns_meaning_the_same_thing_are_refused_not_picked_between():
    with pytest.raises(vsf.UnreadableHeader) as exc:
        vsf.resolve_columns(["base wafer id", "base_x", "base_y", "inchip_x",
                             "inchip_y", "gate", "radius_x", "rx", "radius_y"])
    assert "radius_x" in str(exc.value)


def test_a_naive_source_timestamp_never_reaches_the_database_naive():
    """Measured on PostgreSQL: a naive string is ACCEPTED into timestamptz and
    read in the session's TimeZone - it lands wrong, silently, and differs
    between two processes. R5 forbids the value; this is what enforces it."""
    value, was_naive = vsf.declare_offset("2026-08-13 04:12:07")
    assert was_naive is True
    assert value.endswith(vsf.SOURCE_UTC_OFFSET)
    # A source that states its own zone outranks the site declaration.
    stated, was_naive = vsf.declare_offset("2026-08-13T04:12:07+02:00")
    assert was_naive is False and stated.endswith("+02:00")


def test_a_file_with_no_inspection_time_is_refused(tmp_path):
    """R5: arrival time is a different fact. Substituting it would make every
    run look like it happened when the file was copied."""
    path = write(tmp_path, "no_time.csv",
                 "# unit: um\n" + COLUMNS + BODY)
    with pytest.raises(vsf.UnreadableHeader) as exc:
        vsf.read_sat_file(path)
    assert "R5" in str(exc.value)


def test_a_scan_that_found_nothing_still_produces_a_run(tmp_path):
    """🔴 THE REGRESSION THIS FILE EXISTS FOR.

    The clean scan is the run that matters most: without it "no voids" and
    "never scanned" are the same absence, which is the entire reason this
    schema is two tables. It has no data rows, so the package it covered can
    only come from the header block - and the first implementation read header
    keys the header parser never produced, so every clean scan silently
    produced NO run at all. Caught end-to-end on `assy_qa`, pinned here.
    """
    path = write(tmp_path, "clean.csv",
                 HEADER + "# base_wafer_id: BW-9\n# base_x: 4\n# base_y: 9\n"
                 "# gate: 2\n" + COLUMNS)
    run_row, void_rows, _warnings = vsf.read_sat_file(path)
    assert void_rows == []
    assert run_row is not None, "a clean scan produced no denominator"
    assert (run_row["base_wafer_id"], run_row["base_x"],
            run_row["base_y"], run_row["stack_gate"]) == ("BW-9", 4.0, 9.0, 2.0)


def test_a_file_covering_two_package_layers_is_refused(tmp_path):
    """A run is ONE scan of ONE layer. Quietly taking the first would file
    every void under a denominator that never scanned it."""
    path = write(tmp_path, "two.csv", HEADER + COLUMNS + BODY +
                 "BW-2,12,34,10,10,3,1,1\n")
    with pytest.raises(vsf.UnreadableHeader) as exc:
        vsf.read_sat_file(path)
    assert "ONE scan of ONE layer" in str(exc.value)


def test_read_sat_file_reports_what_it_ignored_and_what_it_assumed(tmp_path):
    """An unrecognised column is the most likely place a needed value hides,
    so it is ignored but never silent."""
    path = write(tmp_path, "extra.csv",
                 HEADER + COLUMNS.rstrip("\n") + ",operator_note\n" +
                 "BW-1,12,34,101.5,220.25,3,4.75,2.5,looks fine\n")
    _run, voids, warnings = vsf.read_sat_file(path)
    assert len(voids) == 1
    assert any("operator_note" in w for w in warnings)
    assert any("no UTC offset" in w for w in warnings)


def test_the_eight_columns_round_trip_with_their_fractions(tmp_path):
    path = write(tmp_path, "scan.csv", HEADER + COLUMNS + BODY)
    run_row, voids, _warnings = vsf.read_sat_file(path)

    assert len(voids) == 2
    first = voids[0]
    assert first["radius_x"] == 4.75 and first["radius_y"] == 2.5
    assert first["inchip_x"] == 101.5 and first["inchip_y"] == 220.25
    assert first["base_wafer_id"] == "BW-1"     # kept as text, not 'BW-1.0'
    assert first["unit"] == "um"
    # The voids point at the run this same file produced.
    assert first["run_uid"] == vsf.compose_run_uid(
        run_row["base_wafer_id"], run_row["base_x"], run_row["base_y"],
        run_row["stack_gate"], run_row["observed_at"])
    # ...and the run records the recipe WITHOUT putting it in the identity, so
    # a corrected re-delivery updates instead of orphaning the voids.
    assert run_row["recipe_id"] == "VOID_5PCT_R3"
    assert "VOID_5PCT_R3" not in first["run_uid"]


def test_a_decimal_comma_is_caught_instead_of_shifting_every_later_column(tmp_path):
    """🔴 Found by a test I expected to pass for a different reason.

    `1,25` in a CSV is TWO fields, not one. Every column after it shifts by one
    and the shifted values are still valid numbers, so no numeric check fires -
    `radius_x` quietly ends up holding what was really `radius_y`. Comparing the
    row's arity to the header's is what catches it.
    """
    path = write(tmp_path, "comma.csv",
                 HEADER + COLUMNS + "BW-1,12,34,101.5,220.25,3,1,25,2.5\n")
    with pytest.raises(vsf.MisalignedRow) as exc:
        vsf.read_sat_file(path)
    assert "9 fields" in str(exc.value) and "8" in str(exc.value)
    assert "DECIMAL COMMA" in str(exc.value)


def test_a_truncated_row_is_refused_by_the_same_arity_check(tmp_path):
    path = write(tmp_path, "short.csv",
                 HEADER + COLUMNS + "BW-1,12,34,101.5\n")
    with pytest.raises(vsf.MisalignedRow):
        vsf.read_sat_file(path)


@pytest.mark.parametrize("bad", ["N/A", "nan", "inf"])
def test_a_numeric_cell_that_is_not_a_number_names_its_row_and_column(bad, tmp_path):
    """It fails the WHOLE file on purpose - a void that kept its position and
    silently lost its size would be an observation nobody can judge, and it
    would make the scan's void count quietly wrong. Loud and stopped beats
    partially loaded. The message has to be actionable, so it names both."""
    path = write(tmp_path, "bad.csv",
                 HEADER + COLUMNS + f"BW-1,12,34,101.5,220.25,3,{bad},2.5\n")
    with pytest.raises(vsf.UnreadableValue) as exc:
        vsf.read_sat_file(path)
    assert "radius_x" in str(exc.value) and "row 1" in str(exc.value)


def test_a_plugin_only_claims_files_in_its_own_workspace(tmp_path):
    root = tmp_path / "ingestion_workspace"
    assert vsf.targets_table(str(root / VOID / "raws" / "s.csv"), VOID)
    assert not vsf.targets_table(str(root / RUN / "raws" / "s.csv"), VOID)
    assert vsf.targets_table(str(root / RUN / "archives" / "s.csv"), RUN)
    # Outside the workspace layout entirely - a direct call or a test - it does
    # not refuse on a layout question the caller may not be using.
    assert vsf.targets_table(str(tmp_path / "s.csv"), VOID)
