"""The column picker's guards and query SHAPE, without a database.

🔴 WHAT THIS FILE DOES NOT PROVE, STATED FIRST.  `db_safety.install_global_test_database_guard`
refuses any engine that opens the production database while pytest is running, and that net
is right -- a test that measured the live plant would be one edit away from writing to it.
So the NUMBERS are not asserted here.  They were measured by running
`server/scripts/check_source_ordering.py dt_job` against the live table on 2026-08-19:
`dt_job_id` 0 / 34,939, `[dt_job, dt_index]` 8,580 duplicate rows, `[dt_job, dt_cell_key]`
unique -- reproducing both defects of 2026-08-18 as numbers.

What IS asserted here is everything that does not need rows: the identifier boundary, the
one-scan cost property, the text-versus-numeric distinction in the aggregate chosen, and
the pure catalog derivation.  A recording session stands in for the database, so these are
claims about behaviour under a known answer rather than claims about the plant.
"""
from __future__ import annotations

import pytest

from ledger import column_stats
from ledger.column_stats import (
    ColumnStatsError,
    combination_uniqueness,
    declared_unique_keys,
    ordering_candidates,
    population,
)


RELATION = "probe_rows"
COLUMNS = {
    "id": "character varying",
    "note": "text",
    "amount": "double precision",
    "seen_at": "timestamp with time zone",
}


class RecordingSession:
    """Answers `information_schema` from a fixed map and records every statement.

    Deliberately dumb: it does not parse SQL.  The assertions below are about how many
    statements were issued and whether a string ever reached one, which is exactly what a
    fake can answer honestly.
    """

    def __init__(self, columns=COLUMNS, aggregate_row=None):
        self.columns = dict(columns)
        self.statements: list[str] = []
        self.aggregate_row = aggregate_row or (0,) * 16

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "information_schema.columns" in sql:
            name = (params or {}).get("relation")
            rows = [] if name != RELATION else list(self.columns.items())
            return _Result(rows)
        return _Result([self.aggregate_row])

    def touching(self, needle: str) -> list[str]:
        return [item for item in self.statements if needle in item]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        row = self.fetchone()
        return None if row is None else row[0]


def test_a_column_name_never_reaches_a_statement_unless_the_relation_has_it():
    """🔴 THE INJECTION BOUNDARY, AND THERE IS NO OTHER ONE.

    A column name is an identifier, so it cannot be a bound parameter -- it reaches the SQL
    as text or not at all.  The rule is therefore membership in the live
    `information_schema` answer, and the test that means something is not "it raised" but
    "the payload appears in NO statement": a guard that refused AFTER building the query
    would still raise, and would still have built the query.
    """
    payload = 'id"; DROP TABLE ' + RELATION + '; --'
    session = RecordingSession()
    with pytest.raises(ColumnStatsError) as refused:
        population(session, RELATION, [payload])
    assert refused.value.code == "unknown_column"
    assert refused.value.path == f"{RELATION}.{payload}"
    assert session.touching("DROP TABLE") == [], session.statements

    session = RecordingSession()
    with pytest.raises(ColumnStatsError):
        combination_uniqueness(session, RELATION, ["id", payload])
    assert session.touching("DROP TABLE") == []
    # Not even the legal half of the request was executed: the check runs before the query
    # is assembled, so one bad name refuses the whole call rather than half-running it.
    assert session.touching("GROUP BY") == []


@pytest.mark.parametrize("columns, code", [
    ([], "no_columns"),
    (["nope"], "unknown_column"),
    ([f"c{index}" for index in range(column_stats.MAX_MEASURED_COLUMNS + 1)],
     "too_many_columns"),
])
def test_the_measurement_refuses_by_name(columns, code):
    with pytest.raises(ColumnStatsError) as refused:
        combination_uniqueness(RecordingSession(), RELATION, columns)
    assert refused.value.to_mapping()["code"] == code


def test_an_undeclared_relation_is_refused_rather_than_scanned():
    session = RecordingSession()
    with pytest.raises(ColumnStatsError) as refused:
        population(session, "not_this_one", ["id"])
    assert refused.value.code == "unknown_relation"
    assert session.touching("count(") == []


def test_every_column_is_one_more_aggregate_in_the_same_scan():
    """The property that lets this be opened on a 10M-row table.

    Counted rather than read: a refactor into a loop would still return correct numbers on
    a fixture table and would make the picker unusable on the only tables where the numbers
    matter.  One statement asks `information_schema`, exactly one touches the relation.
    """
    session = RecordingSession()
    population(session, RELATION)
    scans = session.touching(f'"{RELATION}"')
    assert len(scans) == 1, session.statements
    assert scans[0].count("count(") == len(COLUMNS) + 1      # +1 for count(*)


def test_a_blank_string_is_empty_but_a_zero_is_not():
    """The discriminating pair, asserted on the aggregate each column type gets.

    A `varchar` holding `''` binds fine and produces nothing -- it is empty in the sense the
    author cares about.  A numeric 0 is a real value, and a truthiness rule that called
    both empty would quietly hide a usable column.  So text columns get
    `count(nullif(btrim(col), ''))` and everything else gets plain `count(col)`.
    """
    session = RecordingSession()
    population(session, RELATION)
    sql = session.touching(f'"{RELATION}"')[0]
    assert 'count(nullif(btrim("note"), \'\'))' in sql
    assert 'count(nullif(btrim("id"), \'\'))' in sql
    assert 'count("amount")' in sql and 'btrim("amount")' not in sql
    assert 'count("seen_at")' in sql and 'btrim("seen_at")' not in sql


def test_uniqueness_reports_three_numbers_that_answer_different_questions():
    """`duplicate_rows` is rows minus distinct; `rows_in_duplicated_groups` is larger.

    An author confuses these, and so does a reader of the payload: the first is the number
    the ordering contract refuses on, the second is how much data is actually involved.
    The fixture row makes them differ so a field mix-up cannot pass.
    """
    # 9 rows in 4 combinations: one group of 4, one of 2, two of 1.  Every number below
    # differs from every other, so no assertion can pass by reading the wrong field.
    session = RecordingSession()
    session.execute = _sequenced(session, [(4, 9, 6, 4), (2,)])
    result = combination_uniqueness(session, RELATION, ["id", "note"])
    assert result["distinct_combinations"] == 4
    assert result["total_rows"] == 9
    assert result["duplicate_rows"] == 5          # rows - distinct
    assert result["rows_in_duplicated_groups"] == 6
    assert result["largest_group"] == 4
    assert result["null_bearing_rows"] == 2
    assert result["unique"] is False
    assert len({result["duplicate_rows"], result["rows_in_duplicated_groups"],
                result["largest_group"]}) == 3


def _sequenced(session, rows):
    """Return an `execute` that answers the aggregate queries in order."""
    inner = RecordingSession(session.columns)
    queue = list(rows)

    def execute(statement, params=None):
        sql = str(statement)
        session.statements.append(sql)
        if "information_schema.columns" in sql:
            return _Result(list(session.columns.items()))
        return _Result([queue.pop(0)])
    inner.statements = session.statements
    return execute


def test_declared_unique_keys_reads_every_shape_the_catalog_uses():
    """One list, so the picker's default and the validator's check cannot disagree.

    `_columns_cover_declared_unique_key` builds exactly this and keeps only the yes/no.
    A second implementation for the picker is how the screen comes to recommend an ordering
    the compiler then refuses.
    """
    assert declared_unique_keys({
        "business_key": "dt_cell_key",
        "composite_key": ["dt_job_id", "b_wx", "b_wy"],
        "indexes": [{"unique": True, "columns": ["row_id"]},
                    {"unique": False, "columns": ["event_time"]}],
    }) == (("dt_cell_key",), ("dt_job_id", "b_wx", "b_wy"), ("row_id",))
    assert declared_unique_keys({}) == ()
    # Duplicates collapse: the same key declared twice is one candidate, not two.
    assert declared_unique_keys({
        "business_key": "id", "indexes": [{"unique": True, "columns": ["id"]}],
    }) == (("id",),)


def test_a_declared_key_the_data_disagrees_with_is_measured_and_not_recommended():
    """🔴 DERIVATION ALONE WOULD HAND THE AUTHOR THE BROKEN KEY.

    `dt_log` declares a composite key of three columns that are all empty: it satisfies
    every compile-time check and identifies nothing.  So the derived default is offered
    only after the data agrees with it, and `recommended` is None when none survive --
    which is an answer, not a gap.  It means this relation cannot be ordered from its
    declaration alone.
    """
    session = RecordingSession()
    # First declared key measures unique (6 groups over 6 rows), second does not (1 over 6).
    session.execute = _sequenced(session, [(6, 6, 0, 1), (0,), (1, 6, 6, 6), (6,)])
    result = ordering_candidates(session, RELATION, {
        "business_key": "id", "composite_key": ["note"]})
    measured = {tuple(item["columns"]): item for item in result["declared_keys"]}
    assert measured[("id",)]["unique"] is True
    assert measured[("note",)]["unique"] is False
    assert result["recommended"] == ["id"]

    # A declared key naming a column the relation does not have is reported rather than
    # crashed on, and never recommended.
    absent = ordering_candidates(
        RecordingSession(), RELATION, {"business_key": "not_a_column"})
    assert absent["recommended"] is None
    assert absent["declared_keys"][0]["measurable"] is False
    assert "not_a_column" in absent["declared_keys"][0]["reason"]
