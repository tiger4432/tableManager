# -*- coding: utf-8 -*-
"""총괄 10-22 (굳음 측정): the recent-history rebuild held the cache's lock for its whole walk - up to 5.2 s - and every
worker notification (`add_logs_batch`) waited on it, up to 4.4 s; past 3 s the worker said «not delivered». The walk
now runs outside the lock and only the swap is inside: a merge during the walk does not wait, a reader meanwhile is
answered the projection there is, one builder at a time, and each row is counted once after the swap and the next
refresh."""
import threading
import time
from datetime import datetime, timezone

from admin.audit_cache import AuditLogCache
from database import models


def _audit(tx_id, row_id):
    return models.AuditLog(table_name="rebuild_lock_test", row_id=row_id, column_name="value", old_value=None,
                           new_value="new", source_name="chain_ingestion", updated_by="chain_replay",
                           transaction_id=tx_id, timestamp=datetime.now(timezone.utc))


def _event_log(tx_id, row_id):
    """As the internal event carries it - id 0 (see test_audit_cache_cross_process._event_log)."""
    return {"id": 0, "table_name": "rebuild_lock_test", "row_id": row_id, "column_name": "value", "old_value": None,
            "new_value": "new", "source_name": "chain_ingestion", "updated_by": "chain_replay", "transaction_id": tx_id,
            "timestamp": datetime.now(timezone.utc), "business_key": None}


def _totals(cache):
    return {g["transaction_id"]: g["total_count"] for g in cache.groups}


def test_a_merge_during_the_walk_does_not_wait_and_every_row_is_counted_once(db_session):
    cache = AuditLogCache()
    db_session.add_all([_audit("A", "a%d" % i) for i in range(3)])
    db_session.commit()
    cache.load_initial(db_session)
    assert _totals(cache) == {"A": 3}, "CANARY: the first projection"
    db_session.add_all([_audit("B", "b%d" % i) for i in range(2)])
    db_session.commit()

    seen = {}
    real_hydrate = cache._hydrate

    def hydrate_with_a_merge(*args, **kwargs):
        # the walk has read its watermark: a row committed now, and the notification that says so
        db_session.add(_audit("C", "c0"))
        db_session.commit()
        merged = threading.Thread(target=cache.add_logs_batch, args=([_event_log("C", "c0")], 1))
        began = time.perf_counter()
        merged.start()
        merged.join(2.0)
        seen["merge_waited"] = time.perf_counter() - began
        seen["merge_done"] = not merged.is_alive()
        seen["read_meanwhile"] = _totals(cache)
        other = threading.Thread(target=cache.load_initial, args=(db_session,),
                                 kwargs={"force": True, "refresh_above": 10 ** 9})
        other.start()
        other.join(2.0)
        seen["second_builder_left"] = not other.is_alive()
        return real_hydrate(*args, **kwargs)

    cache._hydrate = hydrate_with_a_merge
    cache.load_initial(db_session, force=True)
    cache._hydrate = real_hydrate

    assert seen["merge_done"] and seen["merge_waited"] < 1.0, seen
    assert seen["read_meanwhile"] == {"C": 1, "A": 3}, "a reader meanwhile is answered the projection there is"
    assert seen["second_builder_left"], "one builder at a time - the other request answers as it is"
    assert _totals(cache) == {"B": 2, "A": 3}, "the merge went with the old groups; C is above the watermark"
    assert cache.refresh_if_stale(db_session) is True
    assert _totals(cache) == {"C": 1, "B": 2, "A": 3}, "C counted once - by the refresh"


class _SwapOnSecondTake:
    """The cache's lock, that before its second taking swaps in `swap()` - a rebuild landing between a refresh's
    read of its delta and its merge."""

    def __init__(self, swap):
        self._inner, self._swap, self.taken = threading.Lock(), swap, 0

    def __enter__(self):
        self.taken += 1
        if self.taken == 2:
            self._swap()
        self._inner.acquire()
        return self

    def __exit__(self, *exc):
        self._inner.release()


def test_a_delta_read_before_a_swap_is_not_merged_twice(db_session):
    """A refresh reads its delta, a rebuild swaps in a projection that already holds those rows, then the refresh
    would merge: the watermark moved, so this merge is left out - the next read starts from the swapped one."""
    cache = AuditLogCache()
    db_session.add(_audit("A", "a0"))
    db_session.commit()
    cache.load_initial(db_session)
    db_session.add(_audit("D", "d0"))
    db_session.commit()
    rebuilt = AuditLogCache()
    rebuilt.load_initial(db_session)
    assert _totals(rebuilt) == {"D": 1, "A": 1}, "CANARY: the rebuild holds D"

    def swap():
        cache.groups, cache._db_max_id = rebuilt.groups, rebuilt._db_max_id

    cache._lock = _SwapOnSecondTake(swap)
    assert cache.refresh_if_stale(db_session) is False
    assert cache._lock.taken == 2, "CANARY: the swap landed between the read and the merge"
    assert _totals(cache) == {"D": 1, "A": 1}, "D once, not twice"


def test_a_notification_s_claim_is_absorbed_per_group_by_the_merge(db_session):
    """총괄 10-22: the credit is absorbed by a group's count, not row by row - a notification that claimed 3 of a
    transaction's 10 rows, then the merge reads all 10: 10, not 13; one that claimed more than the merge reads keeps
    the rest as credit."""
    cache = AuditLogCache()
    db_session.add(_audit("seed", "s"))
    db_session.commit()
    cache.load_initial(db_session)
    db_session.add_all([_audit("E", "e%d" % i) for i in range(10)])
    db_session.commit()
    cache.add_logs_batch([_event_log("E", "e0")], 3)
    assert _totals(cache)["E"] == 3, "CANARY: the claim"
    assert cache.refresh_if_stale(db_session) is True
    assert _totals(cache)["E"] == 10
    cache.add_logs_batch([_event_log("F", "f0")], 4)
    db_session.add_all([_audit("F", "f%d" % i) for i in range(2)])
    db_session.commit()
    assert cache.refresh_if_stale(db_session) is True
    group = next(g for g in cache.groups if g["transaction_id"] == "F")
    assert (group["total_count"], group["_event_credit"]) == (4, 2), "two still claimed, not yet read"


def test_a_group_s_count_is_cumulative_however_its_rows_arrive(db_session):
    """«수 = 누적» (총괄 10-22): a group's count is what it had plus what came - the same whether its rows arrive in
    one delta or one at a time, and the same as a rebuild's count of them."""
    one, each = AuditLogCache(), AuditLogCache()
    db_session.add_all([_audit("G", "g0"), _audit("G", "g1")])
    db_session.commit()
    one.load_initial(db_session)
    each.load_initial(db_session)
    for i in range(2, 7):
        db_session.add(_audit("G", "g%d" % i))
        db_session.commit()
        each.refresh_if_stale(db_session)
    one.refresh_if_stale(db_session)
    rebuilt = AuditLogCache()
    rebuilt.load_initial(db_session)
    assert _totals(one) == _totals(each) == _totals(rebuilt) == {"G": 7}
    assert [log.row_id for log in one.groups[0]["logs"]] == [log.row_id for log in each.groups[0]["logs"]] == [
        log.row_id for log in rebuilt.groups[0]["logs"]]
