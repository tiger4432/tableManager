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
