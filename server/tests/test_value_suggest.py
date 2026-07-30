"""[F3] Unique-value lookup — `GET /tables/{t}/columns/{c}/values`.

Every INV of the mandate gets a test that FAILS when the guard is removed
(each one carries the counter-injection that was actually run against it):

  INV-F3-1  truncation is spoken, never silent
  INV-F3-2  an empty prefix is hard-capped, and refused when policy says so
  INV-F3-3  table/column are checked against the DECLARATION, never interpolated
  INV-F3-4  a `number` column suggests the STORED form via canonical_key_value
  INV-F3-5  NULL / empty / whitespace-only values are not suggestions
  INV-F3-6  cannot-answer degrades with a REASON, not an innocent empty list

Plus the pure helpers (`prefix_upper_bound`, `numeric_prefix_ranges`,
`resolve_settings`, `index_targets`) and the shared prefix predicate that
`/graph/nodes/search` now uses.
"""
import uuid

import pytest
import sqlalchemy as sa

import value_suggest
from database import models


def _seed(db, table, column, values, extra=None):
    """Insert one row per value (None means "leave the column NULL")."""
    model = models.DYNAMIC_TABLES[table]
    for i, v in enumerate(values):
        kwargs = {"row_id": str(uuid.uuid4()), "business_key_val": f"BK_{i}_{uuid.uuid4()}"}
        kwargs[column] = v
        kwargs.update(extra or {})
        db.add(model(**kwargs))
    db.commit()


@pytest.fixture()
def parts_env(db_session):
    """`inventory_master.category` — a low-cardinality text column, the shape a
    dropdown is best at (and the shape a plain DISTINCT is worst at)."""
    _seed(db_session, "inventory_master", "category",
          ["CDIE", "CHIP_VAR", "CHIP_WEB", "ALPHA", "BETA", None, "", "   "])
    return db_session


# ---------------------------------------------------------------------------
# INV-F3-1 — truncation is part of the answer
# ---------------------------------------------------------------------------

def test_truncation_is_reported(client, parts_env):
    """Counter-injection: hardcoding `result["truncated"] = False` in
    `suggest_values` turns this into 3 values silently claiming completeness."""
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"limit": 3}).json()
    assert len(body["values"]) == 3
    assert body["truncated"] is True, "잘렸는데 잘렸다고 말하지 않으면 드롭다운이 '이게 전부'라고 암시한다"

    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"limit": 50}).json()
    assert body["values"] == ["ALPHA", "BETA", "CDIE", "CHIP_VAR", "CHIP_WEB"]
    assert body["truncated"] is False


def test_truncation_flag_is_not_always_true(client, parts_env):
    """The mirror of the above: a flag that is always True is equally useless.
    A prefix that fits inside the limit must report False."""
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"prefix": "CH", "limit": 5}).json()
    assert body["values"] == ["CHIP_VAR", "CHIP_WEB"]
    assert body["truncated"] is False


def test_probe_budget_exhaustion_also_reports_truncated(client, db_session, monkeypatch):
    """Stopping on the BUDGET is still stopping early — it must read as truncated,
    not as a complete short list.

    Counter-injection: returning `values, False` from the budget branch of
    `_numeric_values` makes this assert fail while the value list is unchanged.
    """
    _seed(db_session, "inventory_master", "stock_qty", [float(v) for v in range(1, 40)])
    monkeypatch.setattr(value_suggest, "load_config",
                        lambda path=None: {"max_probe_values": 3})
    body = client.get("/tables/inventory_master/columns/stock_qty/values",
                      params={"limit": 20}).json()
    assert len(body["values"]) < 20
    assert body["truncated"] is True


# ---------------------------------------------------------------------------
# INV-F3-2 — an empty prefix never degrades silently
# ---------------------------------------------------------------------------

def test_empty_prefix_is_hard_capped_and_says_so(client, parts_env):
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"prefix": "", "limit": 2}).json()
    assert body["values"] == ["ALPHA", "BETA"]
    assert body["truncated"] is True
    assert body["limit"] == 2


def test_min_prefix_length_refuses_explicitly(client, parts_env, monkeypatch):
    """Counter-injection: deleting the `len(prefix) < min_len` check returns 200
    with values — a policy that exists in the config file and nowhere else."""
    monkeypatch.setattr(value_suggest, "load_config",
                        lambda path=None: {"min_prefix_length": 2})
    res = client.get("/tables/inventory_master/columns/category/values",
                     params={"prefix": "C"})
    assert res.status_code == 400
    assert "2자" in res.json()["detail"]

    ok = client.get("/tables/inventory_master/columns/category/values",
                    params={"prefix": "CH"})
    assert ok.status_code == 200
    assert ok.json()["values"] == ["CHIP_VAR", "CHIP_WEB"]


def test_limit_is_capped_by_max_limit(client, parts_env, monkeypatch):
    monkeypatch.setattr(value_suggest, "load_config",
                        lambda path=None: {"max_limit": 2, "default_limit": 2})
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"limit": 9999}).json()
    assert body["limit"] == 2
    assert len(body["values"]) == 2
    assert body["truncated"] is True


# ---------------------------------------------------------------------------
# INV-F3-3 — the declaration is the authority
# ---------------------------------------------------------------------------

def test_undeclared_table_is_refused(client, parts_env):
    res = client.get("/tables/not_a_table/columns/category/values")
    assert res.status_code == 404


def test_undeclared_column_is_refused(client, parts_env):
    res = client.get("/tables/inventory_master/columns/nope/values")
    assert res.status_code == 400


def test_physical_but_undeclared_column_is_refused(client, parts_env):
    """`business_key_val` exists in the physical table but is NOT declared in
    `column_types` — the declaration decides, not the database.

    Counter-injection: validating against `model.__table__.c` instead of
    `column_types` makes this return 200 and leak an internal column.
    """
    for col in ("business_key_val", "row_id", "created_at"):
        res = client.get(f"/tables/inventory_master/columns/{col}/values")
        assert res.status_code == 400, col


def test_caller_text_never_reaches_sql(client, parts_env):
    """A column name carrying SQL is a 400, and the table is still there.

    Counter-injection: building the query with an f-string instead of resolving
    a Column object turns this into a 500 (or worse, a DROP).
    """
    res = client.get("/tables/inventory_master/columns/"
                     "category%22%29%3B%20DROP%20TABLE%20inventory_master%3B%20--/values")
    assert res.status_code in (400, 404)
    ok = client.get("/tables/inventory_master/columns/category/values")
    assert ok.status_code == 200 and ok.json()["values"]


def test_datetime_column_is_refused_not_guessed(client, db_session):
    """A datetime canonicalisation would be a SECOND normalisation. Refuse."""
    from database import crud
    crud.TABLE_CONFIG["inventory_master"]["column_types"]["due_at"] = "datetime"
    try:
        res = client.get("/tables/inventory_master/columns/due_at/values")
        assert res.status_code == 400
        assert "날짜" in res.json()["detail"]
    finally:
        crud.TABLE_CONFIG["inventory_master"]["column_types"].pop("due_at")


# ---------------------------------------------------------------------------
# INV-F3-4 — number columns suggest the STORED form (canonical_key_value)
# ---------------------------------------------------------------------------

def test_number_column_suggests_canonical_form(client, db_session):
    """Counter-injection: replacing `_canonical` with `str(v)` yields
    ['1.0','2.0','10.0'] — every suggestion unusable as an input value."""
    _seed(db_session, "inventory_master", "stock_qty", [1.0, 2.0, 10.0, 7.5])
    body = client.get("/tables/inventory_master/columns/stock_qty/values").json()
    assert body["values"] == ["1", "2", "7.5", "10"]


def test_number_prefix_is_canonicalised_too(client, db_session):
    """Typing `01` must find the stored `1` — the SAME normaliser on both sides."""
    _seed(db_session, "inventory_master", "stock_qty", [1.0, 2.0, 10.0, 11.0, 21.0])
    body = client.get("/tables/inventory_master/columns/stock_qty/values",
                      params={"prefix": "01"}).json()
    assert body["values"] == ["1", "10", "11"]
    assert "21" not in body["values"]


def test_number_prefix_spans_magnitudes(client, db_session):
    """`9` also starts `90`, `900`. Walking upward from 9 instead of expanding
    magnitudes would burn the probe budget on 10..89 and return the wrong list.

    Counter-injection: making `numeric_prefix_ranges` return a single
    `[(9, 10)]` drops 90 and 900 from this answer.
    """
    _seed(db_session, "inventory_master", "stock_qty",
          [9.0, 10.0, 50.0, 90.0, 91.0, 900.0])
    body = client.get("/tables/inventory_master/columns/stock_qty/values",
                      params={"prefix": "9"}).json()
    assert body["values"] == ["9", "90", "91", "900"]


def test_negative_number_prefix_finds_the_stored_value(client, db_session):
    """The test that should have existed: seed negative values, ask by prefix.

    Nothing in the original suite ever sent a negative prefix at the ENDPOINT —
    only `numeric_prefix_ranges('-1')` was inspected, and it was inspected with
    an assertion that encoded the defect. So `bonding_map.y` held `-9.0`, the
    live endpoint answered `values: [], truncated: false` for `prefix=-9`, and
    1215 tests passed.

    Counter-injection: reverting `_mirror_negative` to `(-hi, -lo)` returns []
    for every negative prefix below while `prefix='-'` still returns everything —
    the exact live signature.
    """
    _seed(db_session, "inventory_master", "stock_qty",
          [-9.0, -2.0, -90.0, -1.5, -20.0, 3.0])

    def values(prefix):
        return client.get("/tables/inventory_master/columns/stock_qty/values",
                          params={"prefix": prefix}).json()["values"]

    assert values("-9") == ["-90", "-9"], "가장 둥근 값이 조용히 빠지면 안 된다"
    assert values("-2") == ["-20", "-2"]
    assert values("-1.5") == ["-1.5"]
    # ...and the bare sign still reaches every negative, which is what proved
    # the values were reachable at all when the prefixed queries came back empty.
    assert values("-") == ["-90", "-20", "-9", "-2", "-1.5"]


def test_negative_prefix_does_not_leak_positives(client, db_session):
    """The mirrored bound is widened by one ULP, so it must not widen far enough
    to admit the positive side (or `-9` would start answering with `9`)."""
    _seed(db_session, "inventory_master", "stock_qty", [-9.0, 9.0, 0.0, -0.5])
    body = client.get("/tables/inventory_master/columns/stock_qty/values",
                      params={"prefix": "-9"}).json()
    assert body["values"] == ["-9"]
    body = client.get("/tables/inventory_master/columns/stock_qty/values",
                      params={"prefix": "9"}).json()
    assert body["values"] == ["9"]


def test_number_prefix_that_cannot_match_returns_empty_not_error(client, db_session):
    _seed(db_session, "inventory_master", "stock_qty", [1.0, 2.0])
    body = client.get("/tables/inventory_master/columns/stock_qty/values",
                      params={"prefix": "abc"}).json()
    assert body["values"] == []
    assert body["truncated"] is False
    assert body["unavailable_reason"] is None


# ---------------------------------------------------------------------------
# INV-F3-5 — NULL / empty / whitespace-only are not suggestions
# ---------------------------------------------------------------------------

def test_null_and_blank_values_are_excluded(client, parts_env):
    """Counter-injection: dropping `col != ''` from the base conditions puts a
    blank first entry at the top of every dropdown (it sorts before A)."""
    body = client.get("/tables/inventory_master/columns/category/values").json()
    assert "" not in body["values"]
    assert "   " not in body["values"]
    assert all(v.strip() for v in body["values"])
    assert body["values"][0] == "ALPHA"


# ---------------------------------------------------------------------------
# INV-F3-6 — cannot-answer says WHY and returns nothing
# ---------------------------------------------------------------------------

def test_query_failure_degrades_with_a_reason(client, parts_env, monkeypatch):
    """Counter-injection: `except Exception: return result` (no reason) leaves a
    plausible empty list — a dropdown showing "no matches" for a working column.
    """
    def boom(*a, **k):
        raise sa.exc.OperationalError("SELECT 1", {}, Exception("canceling statement due to statement timeout"))

    monkeypatch.setattr(value_suggest, "_text_values", boom)
    res = client.get("/tables/inventory_master/columns/category/values")
    assert res.status_code == 200
    body = res.json()
    assert body["values"] == []
    assert body["truncated"] is False
    assert body["unavailable_reason"], "실패를 빈 목록으로 위장하면 안 된다"
    assert "OperationalError" in body["unavailable_reason"] or \
           "시간 초과" in body["unavailable_reason"]


def test_deadline_degrades_instead_of_serving_a_short_list(client, parts_env, monkeypatch):
    """Running out of TIME is what a missing prefix index looks like: every seek
    falls back to a sequential scan, the loop dies after a few of them, and the
    leftovers read as a short but COMPLETE pick list.

    Counter-injection: treating the deadline like the probe budget
    (`truncated = stop is not None`) returns 200 with values and no reason —
    a dropdown quietly showing a fraction of the real options.
    """
    monkeypatch.setattr(value_suggest, "load_config", lambda path=None: {"timeout_ms": 1})
    monkeypatch.setattr(value_suggest.time, "monotonic",
                        lambda _c=[0]: _c.__setitem__(0, _c[0] + 10) or _c[0])
    body = client.get("/tables/inventory_master/columns/category/values").json()
    assert body["values"] == [], "시간이 모자란 답을 정상 목록처럼 돌려주면 안 된다"
    assert body["truncated"] is False
    assert "시간 초과" in body["unavailable_reason"]


def test_budget_stop_keeps_its_values_but_deadline_does_not(client, db_session, monkeypatch):
    """The two stop reasons must not collapse into one another: a budget stop
    still yields a correct first-N, so throwing those away would be as wrong as
    keeping the deadline's."""
    _seed(db_session, "inventory_master", "category", ["AAA", "BBB", "CCC", "DDD"])
    monkeypatch.setattr(value_suggest, "load_config",
                        lambda path=None: {"max_probe_values": 2})
    body = client.get("/tables/inventory_master/columns/category/values").json()
    assert body["values"] == ["AAA", "BBB"]
    assert body["truncated"] is True
    assert body["unavailable_reason"] is None


def test_diagnosis_names_the_missing_index_only_on_postgres_timeout(db_session):
    """The dashboard's F6 lesson: do not blame the index unconditionally.

    A non-timeout failure must NOT point at an index — that sends whoever is on
    call to tune something that was never the problem.
    """
    non_timeout = value_suggest._diagnose(
        db_session, "bonding_map", "base", ValueError("column missing"), 1500, True)
    assert "idx_suggest_" not in non_timeout
    assert "ValueError" in non_timeout


def test_missing_index_message_is_not_a_dead_end(db_session, monkeypatch):
    """"Run setup_db_performance.py" is useless advice when the builder was never
    going to create this index. An excluded column, a column missing from an
    `index_columns` list, and a table under `index_min_rows` (the live database
    has 15 of those) all re-run to the same nothing.

    This is the same class as the `number`-column fix already in the history —
    that one covered a CASE; the reason has to come from the RULE, which is
    `index_targets`, the single owner of the policy.

    Counter-injection: dropping the `settings` argument and going back to the
    unconditional "run the script" sentence fails all three.
    """
    def reason(config):
        msg = value_suggest._diagnose(
            db_session, "inventory_master", "category", TimeoutError("x"), 1500,
            True, timed_out=True,
            settings=value_suggest.resolve_settings(config))
        # The generic "check your config" fallback names all three knobs, so a
        # test that only looked for a knob name would pass through it and prove
        # nothing about the branching. Each branch must be identified by the
        # sentence only IT produces.
        assert "확인)" not in msg, f"진단이 폴백으로 빠졌다: {msg}"
        return msg

    msg = reason({"index_exclude": {"inventory_master": ["category"]},
                  "index_min_rows": 1})
    assert "index_exclude" in msg and "제외를 풀고" in msg, msg

    msg = reason({"index_columns": {"inventory_master": ["part_no"]}})
    assert "index_columns" in msg and "목록에 추가하고" in msg, msg

    msg = reason({"index_min_rows": 10 ** 9})
    assert "index_min_rows" in msg and "선언하고" in msg, msg

    # ...and when the builder WOULD create it, the plain instruction is right —
    # no invented obstacle for an operator whose only step really is to re-run.
    msg = reason({"index_min_rows": 0})
    assert msg.endswith("server/scripts/setup_db_performance.py 를 실행하세요.")
    assert "index_exclude" not in msg and "index_min_rows" not in msg


def test_invalid_index_is_not_reported_as_present(db_session, monkeypatch):
    """`to_regclass` resolves an INVALID index perfectly well. A cancelled
    `CREATE INDEX CONCURRENTLY` leaves one behind under the wanted name, the
    planner never touches it, and the builder's `IF NOT EXISTS` then skips that
    name forever — so "the index exists" is the one sentence that must not be
    said. The guide's own warning (a worker `idle in transaction` makes the step
    look hung) describes exactly how operators reach this state.

    Counter-injection: reverting `_index_state` to the `to_regclass IS NOT NULL`
    check reports the index as present and the message loses its repair.
    """
    monkeypatch.setattr(value_suggest, "_index_state",
                        lambda db, name: value_suggest._INDEX_INVALID)
    msg = value_suggest._diagnose(
        db_session, "inventory_master", "category", TimeoutError("x"), 1500, True,
        timed_out=True)
    assert "INVALID" in msg
    assert "REINDEX" in msg or "DROP INDEX" in msg
    assert "는 존재합니다" not in msg


def test_index_state_asks_the_catalog_whether_it_is_usable(db_session, monkeypatch):
    """The three-way mapping itself — the part the test above patches away.

    An invalid index cannot be manufactured here (the suite is SQLite and the
    live database is off limits for DDL), so the catalog answer is stubbed and
    what is verified is that `_index_state` ASKS for `indisvalid AND indisready`
    and maps all three answers apart. The old `to_regclass IS NOT NULL` shape
    cannot express the middle one at all.
    """
    seen = {}

    class _Result:
        def __init__(self, v):
            self._v = v

        def scalar(self):
            return self._v

    def fake_execute(stmt, params=None):
        seen["sql"] = str(stmt)
        return _Result(seen["answer"])

    monkeypatch.setattr(db_session, "execute", fake_execute)
    for answer, expected in ((True, value_suggest._INDEX_USABLE),
                             (False, value_suggest._INDEX_INVALID),
                             (None, value_suggest._INDEX_ABSENT)):
        seen["answer"] = answer
        assert value_suggest._index_state(db_session, "idx_suggest_x") == expected
    assert "indisvalid" in seen["sql"] and "indisready" in seen["sql"]
    assert "to_regclass" not in seen["sql"]


# ---------------------------------------------------------------------------
# Case-insensitivity — the shared predicate (consumer #1)
# ---------------------------------------------------------------------------

def test_prefix_match_is_case_insensitive(client, parts_env):
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"prefix": "cd"}).json()
    assert body["values"] == ["CDIE"]


def test_like_metacharacters_are_literal(client, db_session):
    """A range comparison has no wildcards, so `%` can only match a literal `%`.

    Counter-injection: going back to `LIKE prefix || '%'` without escaping makes
    the first assertion return every row.
    """
    _seed(db_session, "inventory_master", "category", ["AAA", "BBB", "%pct", "_und"])
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"prefix": "%"}).json()
    assert body["values"] == ["%pct"]
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"prefix": "_"}).json()
    assert body["values"] == ["_und"]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_prefix_upper_bound():
    assert value_suggest.prefix_upper_bound("ab") == "ac"
    assert value_suggest.prefix_upper_bound("a") == "b"
    assert value_suggest.prefix_upper_bound("") is None
    # The surrogate block cannot be encoded in UTF-8 - the successor must skip it.
    assert value_suggest.prefix_upper_bound("퟿") == ""
    # No successor exists -> None, and the lower bound alone is then exact.
    assert value_suggest.prefix_upper_bound("\U0010ffff") is None


def test_prefix_upper_bound_carries_past_a_maxed_out_character():
    """A trailing U+10FFFF is a digit that rolls over, not the end of the road.

    Incrementing only the LAST character gave up here and returned None, which
    left `prefix_conditions` emitting a lower bound alone — a filter matching
    everything at or above the term. That is harmless for the seek loop (it
    re-tests in Python) and wrong for `/graph/nodes/search`, which has no second
    filter. Measured on the live database: `q='L\\U0010FFFF'` returned MEAS,
    PHOTO, ... where the old ILIKE returned nothing.

    Counter-injection: restoring the single-character increment makes the first
    two assertions return None.
    """
    assert value_suggest.prefix_upper_bound("L\U0010ffff") == "M"
    assert value_suggest.prefix_upper_bound("ab\U0010ffff\U0010ffff") == "ac"
    # Only an all-U+10FFFF prefix has no bound - and there every string >= it
    # provably starts with it, so the lower bound alone really is exact.
    assert value_suggest.prefix_upper_bound("\U0010ffff\U0010ffff") is None


def test_prefix_conditions_is_an_exact_range_not_just_a_narrowing():
    """Consumer #2 has no Python re-test behind this predicate, so "superset" is
    not good enough — every prefix that HAS a bound must emit both ends.

    Counter-injection: dropping the `conds.append(lk < upper)` branch leaves one
    condition here and turns the graph search into an "everything from here on"
    query.
    """
    col = models.GraphNode.identity_key
    assert value_suggest.prefix_conditions(col, "", False) == []
    assert len(value_suggest.prefix_conditions(col, "ab", False)) == 2
    assert len(value_suggest.prefix_conditions(col, "L\U0010ffff", False)) == 2


def test_db_fold_uses_the_databases_own_lower(db_session):
    """`lower()` is not one function. PostgreSQL folds some non-ASCII and not
    other non-ASCII (`Korean_Korea.949`: U+00C4 stays, Cyrillic folds); Python
    folds everything; SQLite folds ASCII only. Since the INDEX stores the
    database's `lower(col)`, the prefix has to be folded by the same one.

    Counter-injection: `return prefix.lower()` unconditionally makes the last
    assertion fail on SQLite (Python folds U+00C4, SQLite does not).
    """
    assert value_suggest.db_fold(db_session, "AB") == "ab"   # ASCII fast path
    assert value_suggest.db_fold(db_session, "") == ""
    native = db_session.execute(
        sa.select(sa.func.lower(sa.literal("ÄB", sa.Text())))).scalar()
    assert value_suggest.db_fold(db_session, "ÄB") == native


def test_case_variant_the_database_folds_is_reachable(client, db_session):
    """End-to-end version of the above, written so it holds on ANY backend:
    whatever this database's `lower()` maps together, the endpoint must too.

    Counter-injection: folding the prefix with Python's `.lower()`, or restoring
    the `canon.lower().startswith(folded)` re-test, returns [] here on SQLite —
    silently, with `truncated: false`.
    """
    stored = "ÄBC"      # U+00C4: PostgreSQL/SQLite leave it, Python lowers it
    _seed(db_session, "inventory_master", "category", [stored, "ZZZ"])
    folded_prefix = db_session.execute(
        sa.select(sa.func.lower(sa.literal(stored[:2], sa.Text())))).scalar()
    body = client.get("/tables/inventory_master/columns/category/values",
                      params={"prefix": folded_prefix}).json()
    assert body["values"] == [stored], "DB가 같다고 보는 값을 제안이 못 찾으면 안 된다"
    assert body["unavailable_reason"] is None


def test_numeric_prefix_ranges():
    assert value_suggest.numeric_prefix_ranges("") == [(None, None)]
    assert value_suggest.numeric_prefix_ranges("abc") == []
    assert value_suggest.numeric_prefix_ranges("0") == [(0.0, 1.0)]
    r = value_suggest.numeric_prefix_ranges("9")
    assert r[0] == (9.0, 10.0) and (90.0, 100.0) in r and (900.0, 1000.0) in r
    assert value_suggest.numeric_prefix_ranges("1.5") == [(1.5, 1.6)]


def test_numeric_ranges_are_ascending_and_walkable():
    """Ascending order is what makes the cursor walk monotonic — a range list out
    of order re-seeks ground it already covered."""
    for p in ("9", "-1", "-9", "1.5", "-1.5"):
        r = value_suggest.numeric_prefix_ranges(p)
        los = [lo if lo is not None else float("-inf") for lo, _ in r]
        assert los == sorted(los), f"{p}: 범위는 오름차순이어야 커서 진행이 단조롭다"


def test_negative_ranges_contain_their_own_endpoint():
    """THE fix. Mirroring `[lo, hi)` onto the negative axis yields `(-hi, -lo]`,
    but `_numeric_values` applies every range as `col >= lo AND col < hi` — so a
    literal mirror EXCLUDES `-lo`, and `-lo` is `-d * 10^k`: the roundest values
    there are. Live proof: `bonding_map.y` holds `-9.0` and `prefix=-9` returned
    `values: []` with `truncated: false`.

    Counter-injection: restoring `(-hi, -lo)` (drop the `math.nextafter` widening
    in `_mirror_negative`) fails every assertion below.
    """
    def covers(ranges, v):
        return any((lo is None or v >= lo) and (hi is None or v < hi)
                   for lo, hi in ranges)

    for prefix, value in (("-1", -1.0), ("-9", -9.0), ("-2", -2.0),
                          ("-9", -90.0), ("-1", -100.0), ("-1.5", -1.5)):
        assert covers(value_suggest.numeric_prefix_ranges(prefix), value), \
            f"{prefix!r} 범위가 자기 끝점 {value}를 떨군다"


def test_numeric_top_magnitude_is_open_above():
    """`_MAX_MAGNITUDE` stops ENUMERATING magnitudes; it must not stop MATCHING
    them. A closed top range makes every value past it invisible to a short
    prefix in exactly the way the negative mirror lost its endpoints."""
    def covers(ranges, v):
        return any((lo is None or v >= lo) and (hi is None or v < hi)
                   for lo, hi in ranges)

    assert covers(value_suggest.numeric_prefix_ranges("9"), 9e20)
    assert covers(value_suggest.numeric_prefix_ranges("-9"), -9e20)


def test_resolve_settings_rejects_nonsense_and_keeps_working():
    s = value_suggest.resolve_settings({
        "default_limit": -5,          # negative -> default
        "max_limit": True,            # bool is not an int knob -> default
        "timeout_ms": 0,              # zero timeout would answer nothing -> default
        "min_prefix_length": 3,       # valid
        "index_columns": {"t": ["a", "b"]},
        "index_exclude": "nope",      # wrong shape -> {}
    })
    assert s["default_limit"] == value_suggest.DEFAULTS["default_limit"]
    assert s["max_limit"] == value_suggest.DEFAULTS["max_limit"]
    assert s["timeout_ms"] == value_suggest.DEFAULTS["timeout_ms"]
    assert s["min_prefix_length"] == 3
    assert s["index_columns"] == {"t": ["a", "b"]}
    assert s["index_exclude"] == {}


def test_resolve_settings_clamps_default_above_max():
    s = value_suggest.resolve_settings({"default_limit": 500, "max_limit": 10})
    assert s["default_limit"] == 10


def test_index_name_stays_within_identifier_limit():
    long_name = value_suggest.suggest_index_name("t" * 60, "c" * 60)
    assert len(long_name) <= 63
    assert long_name != value_suggest.suggest_index_name("t" * 60, "c" * 59)


def test_index_name_is_what_postgres_will_actually_store():
    """PostgreSQL folds unquoted identifiers. A name we ask for but the catalog
    never stores makes both the orphan report and the missing-index diagnosis
    lie about an index they named themselves.

    Counter-injection: dropping the `.lower()` makes the first assert fail.
    """
    name = value_suggest.suggest_index_name("inventory_master", "MAX")
    assert name == name.lower()
    # ...and folding must not merge two genuinely different columns
    assert name != value_suggest.suggest_index_name("inventory_master", "max")


def test_index_targets_policy():
    cfg = {
        "big": {"column_types": {"a": "string", "n": "number", "d": "datetime"}},
        "small": {"column_types": {"a": "string"}},
        "absent": {"column_types": {"a": "string"}},
    }
    settings = value_suggest.resolve_settings({"index_min_rows": 1000})
    rows = {"big": 5000, "small": 10, "graph_nodes": 1}
    got = {(t, c) for t, c, _, _ in value_suggest.index_targets(cfg, settings, rows)}
    assert ("big", "a") in got
    # datetime is refused by the endpoint, so an index for it would be dead weight
    assert ("big", "d") not in got
    # below the threshold, and physically absent, get nothing
    assert ("small", "a") not in got
    assert ("absent", "a") not in got
    # the system target rides along
    assert ("graph_nodes", "identity_key") in got


def test_number_columns_are_indexed_too(client, db_session):
    """Found on the live database, not in the suite: skipping `number` columns
    left the endpoint ANSWERING for them (INV-F3-4 requires it) while the
    builder never made their index — so they timed out and the degradation
    message named an index nothing would ever create.

    Counter-injection: filtering `number` out of `suggestible` in
    `index_targets` makes this fail.
    """
    cfg = {"big": {"column_types": {"a": "string", "n": "number"}}}
    settings = value_suggest.resolve_settings({"index_min_rows": 10})
    targets = {c: d for _, c, _, d in
               value_suggest.index_targets(cfg, settings, {"big": 100})}
    assert "n" in targets, "number 컬럼이 답을 하면 인덱스도 있어야 한다"
    # numeric comparison has no collation - a plain btree, not the text pair
    assert targets["n"] == '("n")'
    assert 'COLLATE "C"' in targets["a"]

    # and the endpoint really does answer for a number column
    _seed(db_session, "inventory_master", "stock_qty", [3.0])
    assert client.get(
        "/tables/inventory_master/columns/stock_qty/values").json()["values"] == ["3"]


def test_forced_column_that_cannot_be_indexed_is_reported(caplog):
    """A column named in `index_columns` that is undeclared or datetime cannot be
    indexed — but dropping it silently leaves the operator reading their own
    config entry as if it were in effect."""
    cfg = {"small": {"column_types": {"a": "string", "d": "datetime"}}}
    settings = value_suggest.resolve_settings(
        {"index_columns": {"small": ["a", "d", "ghost"]}})
    with caplog.at_level("WARNING"):
        got = {c for _, c, _, _ in
               value_suggest.index_targets(cfg, settings, {"small": 1})}
    assert got == {"a"}
    assert "d" in caplog.text and "ghost" in caplog.text


def test_index_targets_explicit_declaration_beats_the_threshold():
    cfg = {"small": {"column_types": {"a": "string", "b": "string"}}}
    settings = value_suggest.resolve_settings(
        {"index_min_rows": 1000, "index_columns": {"small": ["a"]}})
    got = {(t, c) for t, c, _, _ in value_suggest.index_targets(cfg, settings, {"small": 10})}
    assert ("small", "a") in got
    assert ("small", "b") not in got


def test_index_targets_exclusion_always_wins():
    cfg = {"big": {"column_types": {"a": "string", "b": "string"}}}
    settings = value_suggest.resolve_settings(
        {"index_min_rows": 10, "index_exclude": {"big": ["b"], "graph_nodes": ["identity_key"]}})
    got = {(t, c) for t, c, _, _ in
           value_suggest.index_targets(cfg, settings, {"big": 100, "graph_nodes": 5})}
    assert got == {("big", "a")}


def test_index_definition_is_the_byte_order_pair():
    d = value_suggest.suggest_index_definition("base")
    assert 'lower("base") COLLATE "C"' in d
    assert '"base" COLLATE "C"' in d


# ---------------------------------------------------------------------------
# Plan shape (F7 c) — the node type is NOT the property that matters
# ---------------------------------------------------------------------------
#
# Real plans, captured from the live database, kept verbatim as fixtures. The whole
# point of `classify_seek_plan` being pure text-in is that the 1.7M-row pathological
# case becomes a regression test instead of something only production can show.

# The one that matters: an index scan whose cost is LINEAR in the table.
# `bonding_map.base` indexed WITHOUT the `COLLATE "C"` decoration — the planner
# picked the index and then discarded every entry in a Filter. 569 ms for 3 values.
PLAN_LINEAR_INDEX_SCAN = """\
 Limit  (cost=0.43..0.61 rows=1 width=132) (actual time=569.001..569.002 rows=1 loops=1)
   ->  Index Only Scan using idx_bonding_map_base on bonding_map
         Index Cond: (base IS NOT NULL)
         Filter: ((base)::text ~~ 'C%'::text)
         Rows Removed by Filter: 548300
         Heap Fetches: 0
 Execution Time: 569.061 ms"""

# The healthy shape for the SAME column with the right index. Note it also has a
# `Filter:` line — presence of a filter is not the defect.
PLAN_RANGE_SHAPED = """\
 Limit  (cost=0.43..0.61 rows=1 width=132) (actual time=0.044..0.044 rows=1.00 loops=1)
   Buffers: shared hit=4
   ->  Index Only Scan using idx_suggest_bonding_map_base on bonding_map  (cost=0.43..19680.09 rows=106889 width=132)
         Index Cond: (((lower((base)::text)) >= 'c'::text) AND ((lower((base)::text)) < 'd'::text) AND (base IS NOT NULL))
         Filter: ((base)::text <> ''::text)
         Heap Fetches: 0
         Index Searches: 1
 Execution Time: 0.062 ms"""

# `wafer_process.wafer_id` BEFORE its index existed (F7's live defect, 2026-07-30).
PLAN_SEQ_SCAN = """\
 Limit  (cost=943.68..943.68 rows=1 width=108) (actual time=6.503..6.504 rows=0.00 loops=1)
   ->  Sort  (cost=943.68..943.81 rows=52 width=108)
         Sort Key: (lower((wafer_id)::text)) COLLATE "C", wafer_id COLLATE "C"
         ->  Seq Scan on wafer_process  (cost=0.00..943.42 rows=52 width=108)
               Filter: ((wafer_id IS NOT NULL) AND ((wafer_id)::text <> ''::text) AND ((lower((wafer_id)::text))::text >= '1'::text))
               Rows Removed by Filter: 10780
 Execution Time: 6.522 ms"""

# An EMPTY prefix on a healthy index. There is no range to make, so
# `Index Cond: (col IS NOT NULL)` is the CORRECT plan here.
PLAN_EMPTY_PREFIX_HEALTHY = """\
 Limit  (cost=0.43..0.47 rows=1 width=132) (actual time=0.031..0.031 rows=1.00 loops=1)
   ->  Index Only Scan using idx_suggest_bonding_map_base on bonding_map
         Index Cond: (base IS NOT NULL)
         Filter: ((base)::text <> ''::text)
         Heap Fetches: 0
 Execution Time: 0.046 ms"""


def test_plan_check_rejects_the_linear_index_scan_a_node_type_check_would_pass():
    """THE hole this check exists to close.

    `Index Only Scan` is the same node type the healthy plan uses, so a checker that
    recorded "was an index used?" passes a query that reads 548,300 rows to return
    3 — and reports the index as working while the endpoint stays 569 ms.
    """
    # The fixture really does contain the reassuring node type. If this ever stops
    # being true the test below has stopped proving anything about the hole.
    assert "Index Only Scan" in PLAN_LINEAR_INDEX_SCAN
    assert "Seq Scan" not in PLAN_LINEAR_INDEX_SCAN

    verdict, reasons, discarded = value_suggest.classify_seek_plan(
        PLAN_LINEAR_INDEX_SCAN)
    assert verdict != value_suggest.PLAN_OK
    # Both signals fire: the prefix never became a range, AND the walk was long.
    assert value_suggest.PLAN_PREFIX_NOT_A_RANGE in reasons
    assert value_suggest.PLAN_FILTER_DISCARDS in reasons
    assert discarded == 548300


def test_plan_check_accepts_a_range_shaped_plan_that_still_has_a_filter():
    """A `Filter:` line is NOT the defect — the healthy plan has one too
    (`base <> ''`, discarding nothing). A check that rejected any filter would fail
    every healthy column and get switched off, which is worse than no check.
    """
    assert "Filter:" in PLAN_RANGE_SHAPED
    verdict, reasons, discarded = value_suggest.classify_seek_plan(PLAN_RANGE_SHAPED)
    assert verdict == value_suggest.PLAN_OK, reasons
    assert reasons == [] and discarded == 0


def test_plan_check_rejects_a_seq_scan():
    verdict, reasons, discarded = value_suggest.classify_seek_plan(PLAN_SEQ_SCAN)
    assert verdict != value_suggest.PLAN_OK
    assert value_suggest.PLAN_NO_INDEX_COND in reasons
    assert value_suggest.PLAN_FILTER_DISCARDS in reasons
    assert discarded == 10780


def test_plan_check_does_not_demand_a_range_where_there_is_no_prefix():
    """The empty-prefix probe has no range to verify, so `IS NOT NULL` alone is
    correct there. Without `expect_range=False` the check would condemn a perfectly
    healthy index — and a check that cries wolf is a check nobody runs."""
    assert value_suggest.classify_seek_plan(
        PLAN_EMPTY_PREFIX_HEALTHY, expect_range=False)[0] == value_suggest.PLAN_OK
    # ...and with a range demanded, the very same plan is (correctly) rejected.
    assert value_suggest.classify_seek_plan(
        PLAN_EMPTY_PREFIX_HEALTHY, expect_range=True)[1] == [
            value_suggest.PLAN_PREFIX_NOT_A_RANGE]


def test_plan_check_reads_the_discard_count_not_just_its_presence():
    """A range-shaped seek can discard a handful of blanks; the defect is a LONG
    walk. The tolerance is what separates them, so it has to be honoured."""
    small = PLAN_RANGE_SHAPED.replace(
        "         Heap Fetches: 0", "         Rows Removed by Filter: 7")
    assert value_suggest.classify_seek_plan(small)[0] == value_suggest.PLAN_OK
    assert value_suggest.classify_seek_plan(small, max_discarded=3)[1] == [
        value_suggest.PLAN_FILTER_DISCARDS]


def test_the_verified_statement_is_the_statement_the_loop_issues(client, parts_env,
                                                                monkeypatch):
    """A plan check that rebuilds the query itself verifies a query nobody runs.

    `text_seek_query` is the single definition precisely so the builder's Step 3.9
    and the endpoint cannot drift. This pins the seek loop to it: reintroducing an
    inline `sa.select(...)` in `_text_values` makes the call count 0.
    """
    calls = []
    real = value_suggest.text_seek_query

    def spy(col, folded, is_pg, cursor=None):
        calls.append((col.name, folded, cursor))
        return real(col, folded, is_pg, cursor)

    monkeypatch.setattr(value_suggest, "text_seek_query", spy)
    r = client.get("/tables/inventory_master/columns/category/values?prefix=C")
    assert r.status_code == 200 and r.json()["values"]
    assert calls, "_text_values must issue its seek through text_seek_query"
    assert all(c[0] == "category" and c[1] == "c" for c in calls)
    # The cursor advances — i.e. this really is the loose scan, not one query.
    assert calls[0][2] is None and calls[-1][2] is not None


# ---------------------------------------------------------------------------
# F7 b — a CORRECT answer reports what it cost
# ---------------------------------------------------------------------------

def _slow_runner(monkeypatch, seconds=0.30):
    """Make the seek loop take real wall-clock time without breaking it.

    0.30 s clears the 200 ms default with margin. The deadline is 1500 ms, so this
    stays a SUCCESS — which is the whole point of these tests.
    """
    import time as _time
    real = value_suggest._text_values

    def slow(*a, **kw):
        _time.sleep(seconds)
        return real(*a, **kw)

    monkeypatch.setattr(value_suggest, "_text_values", slow)


def test_a_fast_answer_reports_its_cost_and_claims_nothing_else(client, parts_env):
    r = client.get("/tables/inventory_master/columns/category/values").json()
    assert r["values"]
    assert r["unavailable_reason"] is None
    # Cost is on EVERY response, not only the interesting ones — a caller that has
    # to ask "is this field here?" cannot build a policy on it.
    assert "elapsed_ms" in r and isinstance(r["elapsed_ms"], int)
    assert r["slow_reason"] is None


def test_a_slow_but_correct_answer_keeps_its_values_and_names_the_cost(
        client, parts_env, monkeypatch):
    """F7's live defect, as a test: complete, correct, 20x over budget, and until
    now indistinguishable from a fast answer by anyone who was not reading a plan.

    Counter-injection: deleting the `slow_reason` assignment in `suggest_values`
    fails the third assert while every other assert still passes — which is exactly
    the state the endpoint shipped in.
    """
    _slow_runner(monkeypatch)
    r = client.get("/tables/inventory_master/columns/category/values").json()
    # NOT a degradation: the values are good and the caller must use them.
    assert r["values"], "느린 응답이라고 값을 버려서는 안 된다"
    assert r["unavailable_reason"] is None
    assert r["truncated"] is False
    # ...but the cost is now part of the answer.
    assert r["slow_reason"] is not None
    assert r["elapsed_ms"] >= 300
    # Machine-readable AND readable: the number and the budget are both named.
    assert str(r["elapsed_ms"]) in r["slow_reason"]
    assert "200" in r["slow_reason"]


def test_the_slow_threshold_is_configurable_and_zero_is_refused():
    default = value_suggest.DEFAULTS["slow_warn_ms"]
    # Pinned against the measurement that chose it: healthy indexed columns spiked
    # to 148 ms on the live database, so anything at or below that fires on healthy
    # traffic. Lowering this default is a decision, not a tidy-up.
    assert default > 148
    assert value_suggest.resolve_settings({})["slow_warn_ms"] == default
    assert value_suggest.resolve_settings({"slow_warn_ms": 400})["slow_warn_ms"] == 400
    # 0 would mark every answer slow, and a reason on every response is not a
    # signal. `elapsed_ms` is the always-on channel instead.
    assert value_suggest.resolve_settings({"slow_warn_ms": 0})["slow_warn_ms"] == default
    assert value_suggest.resolve_settings({"slow_warn_ms": -1})["slow_warn_ms"] == default


def test_raising_the_threshold_silences_the_reason_without_hiding_the_cost(
        client, parts_env, monkeypatch):
    """An operator who accepts a slower budget must still be able to see cost —
    otherwise raising the knob recreates the silent band it exists to reveal."""
    _slow_runner(monkeypatch)
    monkeypatch.setattr(value_suggest, "DEFAULTS",
                        dict(value_suggest.DEFAULTS, slow_warn_ms=10_000))
    r = client.get("/tables/inventory_master/columns/category/values").json()
    assert r["slow_reason"] is None
    assert r["elapsed_ms"] >= 300


def test_elapsed_ms_survives_the_unavailable_path(client, parts_env, monkeypatch):
    """A client backing off needs the cost of the answer that FAILED most of all."""
    def boom(*a, **kw):
        raise RuntimeError("seek exploded")

    monkeypatch.setattr(value_suggest, "_text_values", boom)
    r = client.get("/tables/inventory_master/columns/category/values").json()
    assert r["unavailable_reason"] and r["values"] == []
    assert "elapsed_ms" in r


def test_slow_reason_carries_the_index_advice_on_postgres(db_session, monkeypatch):
    """The measurement alone leaves the reader nowhere to go. `_slow_reason` reuses
    the SAME `_index_advice` the timeout path uses, so a slow success names the
    missing index and the script to run.

    Counter-injection: dropping the `_index_advice` call leaves a bare number.
    """
    monkeypatch.setattr(value_suggest, "_index_state",
                        lambda db, name: value_suggest._INDEX_ABSENT)
    msg = value_suggest._slow_reason(
        db_session, "inventory_master", "category", 240, 50, True,
        value_suggest.resolve_settings({"index_min_rows": 0}))
    assert "240ms" in msg and "50" in msg
    assert "idx_suggest_inventory_master_category" in msg
    assert "setup_db_performance.py" in msg
    # It must NOT claim a timeout — nothing timed out, the answer arrived.
    assert "시간 초과" not in msg


def test_slow_reason_survives_a_broken_diagnosis(db_session, monkeypatch):
    """Diagnosis is the bonus; the measurement is the signal. If the catalog read
    throws, the caller must still get the number it branches on."""
    def boom(*a, **kw):
        raise RuntimeError("catalog gone")

    monkeypatch.setattr(value_suggest, "_index_advice", boom)
    msg = value_suggest._slow_reason(
        db_session, "inventory_master", "category", 240, 50, True, None)
    assert "240ms" in msg


def test_slow_warning_is_logged_once_per_column_not_once_per_keystroke(
        db_session, monkeypatch, caplog):
    """A client types 17 characters and issues 17 requests. Seventeen copies of the
    same actionable message bury it — the condition is a property of the COLUMN, so
    it is said once and then counted at DEBUG."""
    monkeypatch.setattr(value_suggest, "_index_state",
                        lambda db, name: value_suggest._INDEX_ABSENT)
    monkeypatch.setattr(value_suggest, "_slow_warned", set())
    settings = value_suggest.resolve_settings({})
    with caplog.at_level("WARNING"):
        for _ in range(5):
            value_suggest._slow_reason(db_session, "inventory_master", "category",
                                       240, 50, True, settings)
    assert len([r for r in caplog.records if "category" in r.message]) == 1
    # A DIFFERENT column is a different condition and gets its own line.
    with caplog.at_level("WARNING"):
        value_suggest._slow_reason(db_session, "inventory_master", "part_no",
                                   240, 50, True, settings)
    assert len([r for r in caplog.records if "part_no" in r.message]) == 1
