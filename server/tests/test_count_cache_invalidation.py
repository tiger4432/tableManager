"""`invalidate_table_cache` had EIGHT call sites and every one of them was dead.

The invalidator selected keys with `k == table_name or k.startswith(f"{table_name}_")`.
The writer built them with `"|".join(...)`. The separators never matched, so the prefix
test never fired and every invalidation removed 0 keys - measured 0 of 4 on a
reproduction of both spellings verbatim.

Two consequences, and the second is the worse one:

  * A count invalidated after a write survived its own invalidation for the full TTL.
  * `TABLE_COUNT_CACHE` grew ONE ENTRY PER DISTINCT USER-TYPED SEARCH STRING, forever.
    `?q=` and `?filters=` go into the key, nothing ever removed anything, and there was
    no bound of any kind. A long-lived web process accumulated a row per search until
    restart.

What is pinned here, and why each one is a way the fix could be green and wrong:

  * The invalidator removes the keys the WRITER actually wrote - driven through the real
    data endpoint, not a hand-built key. A test that invents its own key shape tests the
    test's spelling, which is precisely the bug.
  * The stale count is actually refreshed. Removing keys is the mechanism; serving a
    fresh number is the point, and only the second one is visible to a user.
  * A neighbouring table's keys SURVIVE. An invalidator that cleared everything would
    pass the first two tests and quietly throw away every other table's cache.
  * The cache is BOUNDED. Without this the fix repairs the staleness and leaves the leak.
"""
import uuid

import pytest

import main as main_mod
from database import models

TABLE = "raw_table_1"
OTHER = "inventory_master"


@pytest.fixture(autouse=True)
def _clean_cache():
    main_mod.TABLE_COUNT_CACHE.clear()
    yield
    main_mod.TABLE_COUNT_CACHE.clear()


def _keys_for(table):
    return [k for k in main_mod.TABLE_COUNT_CACHE
            if main_mod.count_cache_table_of(k) == table]


def _warm(client, table, **params):
    """Populate the count cache the way production does - through the route."""
    r = client.get(f"/tables/{table}/data", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# The keys the writer actually writes
# ---------------------------------------------------------------------------

def test_invalidation_removes_the_keys_the_endpoint_wrote(client):
    """The whole defect in one assertion, on REAL keys."""
    _warm(client, TABLE)
    _warm(client, TABLE, q="EQP_1")
    _warm(client, TABLE, q="EQP_2", cols="EQP_ID")
    before = _keys_for(TABLE)
    assert len(before) >= 3, f"fixture did not populate the cache: {list(main_mod.TABLE_COUNT_CACHE)}"

    main_mod.invalidate_table_cache(TABLE)

    assert _keys_for(TABLE) == [], (
        f"invalidation left {len(_keys_for(TABLE))} of {len(before)} keys behind: "
        f"{_keys_for(TABLE)}")


def test_a_neighbouring_tables_keys_survive(client):
    """An invalidator that just cleared the dict would pass the test above."""
    _warm(client, TABLE, q="EQP_1")
    _warm(client, OTHER)
    assert _keys_for(OTHER), "fixture did not populate the other table's cache"

    main_mod.invalidate_table_cache(TABLE)

    assert _keys_for(TABLE) == []
    assert _keys_for(OTHER), "invalidating one table threw away another table's cache"


def test_the_writer_and_the_reader_agree_on_the_separator():
    """The root cause, stated directly: two spellings 1,100 lines apart.

    `build_count_cache_key` is the only place the separator exists and
    `count_cache_table_of` is its inverse. If someone re-introduces a literal
    `"|".join(...)` or changes one side, this fails before any endpoint does.
    """
    key = main_mod.build_count_cache_key(TABLE, "total_count", "q:a|b", "filters:{}")
    assert main_mod.count_cache_table_of(key) == TABLE
    # A table whose name is a PREFIX of another must not be caught by the other's sweep.
    assert main_mod.count_cache_table_of(
        main_mod.build_count_cache_key("raw_table_10", "total_count")) != TABLE


# ---------------------------------------------------------------------------
# The consequence a user can see
# ---------------------------------------------------------------------------

def test_a_stale_count_is_refreshed_after_invalidation(client, db_session):
    """Removing keys is the mechanism; a fresh number is the point.

    The TTL is 5s, so without invalidation this row is invisible for 5 seconds
    after it is written - which is exactly what every write path calls
    `invalidate_table_cache` to prevent.
    """
    first = _warm(client, TABLE)["total"]

    model = models.DYNAMIC_TABLES[TABLE]
    db_session.add(model(row_id=str(uuid.uuid4()), business_key_val="EQP_NEW", EQP_ID="EQP_NEW"))
    db_session.commit()

    # Control: inside the TTL, the cache still answers with the OLD number. This is
    # what makes the assertion after invalidation mean something - if the cache were
    # not serving at all, the final assert would pass for the wrong reason.
    assert _warm(client, TABLE)["total"] == first, \
        "the count cache did not serve a cached value; this test cannot prove anything"

    main_mod.invalidate_table_cache(TABLE)

    assert _warm(client, TABLE)["total"] == first + 1, \
        "the count survived its own invalidation"


# ---------------------------------------------------------------------------
# The leak
# ---------------------------------------------------------------------------

def test_the_cache_is_bounded(client):
    """One entry per distinct user-typed search, forever, was the second consequence.

    Driven through `store_table_count` because that is the single writer; the number
    of DISTINCT search strings a user can type is unbounded and nothing else in this
    process ever removed an entry.
    """
    cap = main_mod.COUNT_CACHE_MAX_ENTRIES
    for i in range(cap + 200):
        main_mod.store_table_count(
            main_mod.build_count_cache_key(TABLE, "total_count", f"q:search-{i}"), i)

    assert len(main_mod.TABLE_COUNT_CACHE) <= cap, (
        f"cache grew to {len(main_mod.TABLE_COUNT_CACHE)} entries against a declared "
        f"bound of {cap}")
    # And it is still a working cache, not an empty one: the newest write is readable.
    newest = main_mod.build_count_cache_key(TABLE, "total_count", f"q:search-{cap + 199}")
    assert newest in main_mod.TABLE_COUNT_CACHE, \
        "the bound evicted the entry it had just written"


# ---------------------------------------------------------------------------
# `?defer_total=true` — the count leaves the first paint, and `.../data/count`
# answers the same question with the same filters through the same cache.
# ---------------------------------------------------------------------------
# 🔴 THE COUNT IS STILL EXACT. What this changes is WHEN it arrives, never how right it
# is: no estimate, no widened TTL. So every test here compares the deferred answer to the
# number the grid used to carry and demands they are equal.

import json as _json

DEFER_ROWS = 7


@pytest.fixture()
def seeded(client, db_session):
    """Rows whose filters actually SPLIT them.

    A fixture where every filter matches everything (or nothing) makes "the two routes
    agree" true for the wrong reason - two zeros are equal.
    """
    model = models.DYNAMIC_TABLES[TABLE]
    for i in range(DEFER_ROWS):
        key = "DEFER_%s_%02d" % ("ODD" if i % 2 else "EVEN", i)
        db_session.add(model(row_id=str(uuid.uuid4()), business_key_val=key, EQP_ID=key))
    db_session.commit()
    main_mod.TABLE_COUNT_CACHE.clear()
    return client


def _count_calls(monkeypatch):
    """Every `Query.count()` this process makes, counted at the real method.

    Patched on SQLAlchemy rather than on our own helper: the claim is that the route does
    not COUNT, and a spy on the helper would still read green for a route that reached
    past it. `Count: 0.000s` in the debug line is the same fact, measured here instead of
    by reading a log.
    """
    from sqlalchemy.orm import Query

    real, calls = Query.count, []

    def spy(self):
        calls.append(1)
        return real(self)

    monkeypatch.setattr(Query, "count", spy)
    return calls


FILTER_SHAPES = [
    ("no filter", {}),
    ("q", {"q": "DEFER_ODD"}),
    ("filters", {"filters": _json.dumps({"EQP_ID": {"type": "contains",
                                                    "filter": "DEFER_EVEN"}})}),
]


@pytest.mark.parametrize("label,params", FILTER_SHAPES, ids=[s[0] for s in FILTER_SHAPES])
def test_the_deferred_count_is_the_same_number_the_grid_used_to_carry(seeded, label, params):
    """🔴 THE ONE FAILURE THIS ROUND CAN CAUSE, AND IT IS SILENT.

    If `.../data/count` interpreted `?filters=` a second time the grid would show rows the
    footer says are not there, and neither response would carry anything saying which half
    is wrong. So the comparison is per filter shape, and the shapes have to actually
    narrow - asserted below, or "they agree" would just mean "both said everything".
    """
    grid = seeded.get(f"/tables/{TABLE}/data", params=params)
    assert grid.status_code == 200, grid.text
    counted = seeded.get(f"/tables/{TABLE}/data/count", params=params)
    assert counted.status_code == 200, counted.text

    assert counted.json()["total"] == grid.json()["total"]
    assert counted.json()["table_name"] == TABLE
    if params:
        whole = seeded.get(f"/tables/{TABLE}/data/count").json()["total"]
        assert 0 < counted.json()["total"] < whole, (
            "this filter shape does not narrow, so agreeing about it proves nothing")


def test_deferring_the_total_does_not_count_at_all(seeded, monkeypatch):
    """Not "counts less often" - counts ZERO times, cache hit or miss.

    Reading the cache first would leave exactly today's behaviour in place: usually fast,
    occasionally the full scan, which is the 600ms-to-2000ms swing this round exists to
    take off the first paint.
    """
    calls = _count_calls(monkeypatch)

    body = seeded.get(f"/tables/{TABLE}/data", params={"defer_total": "true"})
    assert body.status_code == 200, body.text

    assert calls == [], f"the deferred request counted {len(calls)} time(s)"
    assert body.json()["data"], "it must still return the rows; only the total is deferred"


def test_a_deferred_total_is_null_and_null_is_not_zero(seeded):
    """🔴 `0` MEANS 「no row matches」 AND THE SCREEN READS IT THAT WAY.

    Asserted with `is None` and again against `0`, because in Python the two compare
    unequal but a JSON of `0` and a JSON of `null` are one careless `or` apart on either
    side of the wire - and this repo has met "unknown and empty render the same" often
    enough to spell the difference out here.
    """
    body = seeded.get(f"/tables/{TABLE}/data", params={"defer_total": "true"}).json()
    assert body["total"] is None
    assert body["total"] != 0


def test_omitting_the_parameter_is_byte_for_byte_todays_response(seeded):
    """Backward compatibility is the requirement, not a courtesy: today's client sends
    no such parameter and must keep working with no change at all."""
    plain = seeded.get(f"/tables/{TABLE}/data").json()
    explicit = seeded.get(f"/tables/{TABLE}/data", params={"defer_total": "false"}).json()

    # The number is not spelled here: this table carries rows the fixture did not put in
    # it, and asserting a literal would pin the fixture rather than the contract. What is
    # asserted is that a total ARRIVED, that it covers what was seeded, and that the two
    # spellings of "do not defer" are the same response.
    assert plain["total"] is not None and plain["total"] >= DEFER_ROWS
    assert plain == explicit


def test_both_routes_apply_the_named_queue_predicate(seeded):
    """The predicate is on BOTH paths, shown by the refusal they share.

    An unknown rule name is refused with 400 by `apply_enrichment_queue_predicate`, so a
    count route carrying its own assembly - the way the CSV export does, which omits this
    predicate entirely - would answer 200 with the UNFILTERED total instead. That is the
    exact shape of "the two halves disagree and nothing errors", caught without needing a
    rule fixture to exist.
    """
    params = {"enrichment_queue": "no_such_rule_exists"}
    assert seeded.get(f"/tables/{TABLE}/data", params=params).status_code == 400
    assert seeded.get(f"/tables/{TABLE}/data/count", params=params).status_code == 400


def test_the_two_routes_share_one_cache_entry(seeded, monkeypatch):
    """One cache, one key, one invalidation.

    A count route that spelled its own key would still return the right number - and
    would double the counting, halve the hit rate, and survive `invalidate_table_cache`
    on one side. None of that shows up in a response body, so it is pinned here.
    """
    seeded.get(f"/tables/{TABLE}/data")            # the grid warms it
    warmed = _keys_for(TABLE)
    assert len(warmed) == 1, f"expected one key for an unfiltered read, got {warmed}"

    warmed_total = seeded.get(f"/tables/{TABLE}/data").json()["total"]
    calls = _count_calls(monkeypatch)
    assert seeded.get(f"/tables/{TABLE}/data/count").json()["total"] == warmed_total
    assert calls == [], "the count route missed the entry the grid had just filled"
    assert _keys_for(TABLE) == warmed, "it wrote a second key for the same question"

    main_mod.invalidate_table_cache(TABLE)
    assert _keys_for(TABLE) == []


def test_the_jump_still_finds_a_rows_page_and_still_counts_to_get_there(seeded, monkeypatch):
    """`target_row_id` is EXCLUDED from this round, and exclusion has to be measured.

    Only the jump's MISS path had a test (`test_table_data_serialization`); the hit path -
    the one that runs its own `count()` to turn a row id into an offset - had none, and it
    now consumes a query built by the shared assembly. So it is pinned here rather than
    argued from "nothing was edited in that block".

    🔴 AND IT COUNTS EVEN WHEN THE TOTAL IS DEFERRED, on purpose: the offset is not the
    total and cannot be served from `.../data/count`. A caller that sends both gets a fast
    first paint for every request EXCEPT a jump, and that is the contract, not an oversight.
    """
    rows = seeded.get(f"/tables/{TABLE}/data", params={"limit": 500}).json()["data"]
    target = rows[len(rows) // 2]["row_id"]

    jumped = seeded.get(f"/tables/{TABLE}/data",
                        params={"target_row_id": target, "limit": 2}).json()
    assert jumped["target_offset"] >= 0, "the jump did not locate the row"
    assert jumped["calculated_skip"] == jumped["skip"]
    assert any(r["row_id"] == target for r in jumped["data"]), (
        "the page it calculated does not contain the row it was asked for")

    calls = _count_calls(monkeypatch)
    deferred = seeded.get(f"/tables/{TABLE}/data",
                          params={"target_row_id": target, "limit": 2,
                                  "defer_total": "true"}).json()
    assert deferred["total"] is None
    assert deferred["target_offset"] == jumped["target_offset"], (
        "deferring the total moved the jump")
    assert len(calls) == 1, (
        f"the jump's offset count is the only count a deferred request may make, "
        f"and it made {len(calls)}")
