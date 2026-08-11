"""The in-memory projection behind `GET /audit_logs/recent`.

WHAT WAS WRONG (measured on an isolated 2,900,000-row fixture, 2026-08-11,
widths copied from production's own catalogue)

    `load_initial` paged `audit_logs` newest-first in 5,000-row chunks with a
    GROWING OFFSET until it had 100 DISTINCT `transaction_id`s. Two independent
    things made that unbounded:

    1. NO `timestamp`-LEADING INDEX EXISTED, so every chunk was a parallel
       sequential scan of the whole table followed by a full sort that spilled
       to disk. One chunk, on the fixture:

           Parallel Seq Scan on audit_logs -> Sort (timestamp DESC, id DESC)
           Sort Method: external merge  Disk: 400,848 kB
           OFFSET 0        3,658 ms   153,307 buffers, 287,412 temp written
           OFFSET 100,000  3,698 ms   153,307 buffers, 287,408 temp written
           OFFSET 200,000  7,167 ms   153,307 buffers, 287,408 temp written

    2. A BULK INGESTION WRITES ONE `transaction_id` PER FILE, so 100,000 rows
       are ONE group. Finding group #2 means walking past all of them. On the
       fixture the newest 200,000 rows carry 2 transaction_ids, so the walk
       needed ~41 chunks of that plan.

    On top of that every scanned row was turned into an ORM entity AND run
    through `AuditLogResponse.model_validate` - including the ~200,000 rows that
    were counted and immediately thrown away, because a group keeps only 500.

WHAT IT DOES NOW

    DISCOVERY is a keyset walk over `(timestamp, id)` selecting three columns,
    so it is an index scan instead of a sort, and it carries a hard ceiling
    (`recent_max_scan_rows`). HYDRATION is a second pass that fetches - and
    validates - only the rows a group actually keeps, so the pydantic bill is
    bounded by `limit_groups * recent_logs_per_group` no matter how many rows
    were walked.

    The keyset predicate, the sort order and the cursor encoding are IMPORTED
    from `audit_history`, not re-typed. That module is the one place this
    project spells "newest-first page of audit history", and a second spelling
    of `(timestamp, id) < (ts, id)` that drifted would put two different orders
    on the same table.

WHY A CEILING NEEDS A WORD, AND WHY IT IS `truncated`

    A walk that gives up returns FEWER than `limit_groups` groups, and a short
    list is indistinguishable from a complete one. That is the silent-failure
    class this project keeps paying for, so the walk publishes `truncated` and
    `next_cursor` - the same two words `audit_history.fetch_page` returns, with
    the same meaning: `truncated` is "there is more history below the last
    entry", `next_cursor` is where to resume. Exactness comes from the same
    trick too: ask for one row more than the chunk needs.

    Both facts reach the wire twice: in `/audit_logs/recent`'s body, which is the
    envelope `{groups, truncated, next_cursor, limit_groups, returned}` since
    2026-08-11, and in the `X-Audit-Truncated` / `X-Audit-Next-Cursor` response
    headers, which were the whole channel before the body could move (client2
    iterated the bare list) and are kept because callers read them. See the route
    in `main.py`.

THE WATERMARK, AND THE COUNT IT WAS DOUBLING

    `_db_max_id` means "every audit row at or below this id is already
    reflected here". Only `load_initial` and `refresh_if_stale` ever advanced
    it. `add_logs_batch` - the path `/internal/events/batch-refresh` and every
    in-process `crud` write use - could not, and still cannot, because the log
    dicts it receives carry `"id": 0` verbatim (crud.create_audit_log writes the
    literal, and `bulk_insert_mappings` never writes the assigned key back).

    So the rows an event had already merged sat above the watermark and were
    read a SECOND time by the next `refresh_if_stale` - and counted a second
    time. Measured before this change: 300 rows written, event reports 300,
    `total_count` reads 600.

    The repair is not a watermark write (there is no id to write). It is a
    CREDIT: an event records how much it has already claimed for a group, and
    the next refresh - which reads the same rows from the database - absorbs
    its own count against that credit instead of adding to it. The database
    stays the single authority for the number; the event only buys latency.
"""
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

import audit_history
from database import models
from database import schemas

# Every knob is a DEFAULT that `audit_history_config.json` overrides - the same
# file the row/cell history endpoints read, because this is the same feature and
# an operator should not have to find two files to bound one table's reads.
RECENT_DEFAULTS = {
    # Hard ceiling on how far the discovery walk goes before it gives up on
    # reaching `limit_groups`. This is the number that makes the first call
    # bounded: the cost stops depending on how many rows one ingestion happened
    # to write.
    #
    # WHY HALF A MILLION AND NOT A HUNDRED THOUSAND. The ceiling is not only a
    # latency budget, it decides HOW MUCH HISTORY THE PANEL CAN SHOW after a
    # bulk load: an ingestion writes one transaction_id per FILE, so K freshly
    # ingested files of 100,000 rows hide the older transactions behind K x
    # 100,000 rows. At the measured 0.64-1.11 us/row of the aggregate walk this
    # ceiling costs ~400 ms in the worst case and covers four such files; at
    # 200,000 it cost ~220 ms and the fixture's panel fell to TWO entries.
    "recent_max_scan_rows": 500_000,
    # Rows per discovery round trip. It is also the walk's FLOOR - even a
    # projection that finds its hundred groups in the first 1,400 rows reads one
    # whole chunk - so it trades round trips against that floor. 20,000 is ~22 ms.
    "recent_scan_chunk_rows": 20_000,
    # Logs kept per group. The projection serves one representative log plus the
    # column list, and `/audit_logs/transaction/{id}` falls back to the database
    # for anything deeper, so this is a convenience cache, not the record.
    "recent_logs_per_group": 500,
    # Above this many new rows, a delta merge stops being cheaper than a
    # rebuild: the merge validates every new row in Python (~47 us each), while
    # a rebuild is bounded by `recent_max_scan_rows` regardless of the delta.
    "recent_refresh_max_delta_rows": 2_000,
}


# Sort placeholder for a null `timestamp`. Never compared against a real value -
# the `is not None` term of the sort key separates them first - it exists only so
# that the tuple comparison has something of the right TYPE to look at.
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def resolve_recent_settings(config: dict = None) -> dict:
    """Resolved scan settings - always every key, always usable.

    A malformed knob falls back to its default with a warning rather than
    taking the endpoint down or silently folding a typo into a number.
    """
    declared = config if isinstance(config, dict) else audit_history.load_config()
    resolved = dict(RECENT_DEFAULTS)
    for key, default in RECENT_DEFAULTS.items():
        if key not in declared:
            continue
        value = declared[key]
        # bool is a subclass of int - True must not silently become 1.
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            print(f"[AuditCache] '{key}' must be a positive integer "
                  f"(got {value!r}); using {default}.")
            continue
        resolved[key] = value
    return resolved


class AuditLogCache:
    """최신 히스토리 로그(트랜잭션 단위 100그룹)의 인메모리 프로젝션.

    단일 프로세스 멀티스레딩 환경에서 Thread-Safe하게 동작한다.
    """

    def __init__(self):
        self.groups: List[Dict] = []
        self.is_loaded = False
        self._lock = threading.Lock()
        self._db_max_id = None
        # [P2 #10] 다중 tx 혼재 배치 경고 1회 게이트 (핫패스 로그 홍수 방지)
        self._multi_tx_warned = False
        # Published by the scan; read by the route. See the module docstring.
        self.truncated = False
        self.next_cursor: Optional[str] = None
        self.scanned_rows = 0

    # ------------------------------------------------------------------
    # The scan
    # ------------------------------------------------------------------

    @staticmethod
    def _ordered_rows(query, floor):
        """Restrict to rows that HAVE a position, at or above `floor`.

        `>= floor` is the mirror of `audit_history.apply_cursor`'s `< ceiling`,
        and it lives here because a range floor is not something a page walk
        needs. Row-value comparison in both directions, never the OR expansion:
        `audit_history`'s module docstring carries the measurement showing
        PostgreSQL cannot push an OR-expanded bound into the btree.

        🔴 `timestamp IS NOT NULL` IS THE LOAD-BEARING PART, and it is stated
        rather than left to emerge. `timestamp` is nullable, and a row-value
        comparison against a NULL yields NULL, not true - so every chunk after
        the first ALREADY dropped null-stamped rows silently, while the first
        chunk (which has no cursor) kept them. On PostgreSQL that difference is
        not academic: `ORDER BY timestamp DESC` is NULLS FIRST there, so a
        null-stamped row would be the very first chunk's edge, its position
        cannot be encoded as a cursor, and a null cursor reads as "no cursor" -
        the walk would restart at the top of the table and count the head rows
        once per lap until the ceiling stopped it. SQLite sorts NULLs last and
        so hides the whole thing.

        Excluding them is the right answer and not merely the safe one: this
        projection is "the newest transactions BY TIME", and a row with no time
        has no place in it. It is still in `audit_logs`, and every other view of
        the audit trail still shows it.
        """
        m = models.AuditLog
        query = query.filter(m.timestamp.isnot(None))
        if floor is None:
            return query
        return query.filter(sa.tuple_(m.timestamp, m.id) >= sa.tuple_(*floor))

    def _chunk_edge(self, db: Session, cursor: Optional[str], want: int):
        """`(last_row_of_this_chunk, there_is_more_below_it)`.

        Two index entries, read at depth `want - 1`: the first is where this
        chunk ends, the second exists only if the table continues past it. That
        second row is the same has-more probe `audit_history.fetch_page` makes
        by asking for `limit + 1` - one extra index entry instead of a count(*)
        that would re-walk everything.

        `(None, False)` means fewer than `want` rows remain: the walk has
        reached the end of the table and nothing below it is unread.
        """
        m = models.AuditLog
        rows = self._ordered_rows(
            audit_history.apply_cursor(db.query(m.timestamp, m.id), m, cursor), None) \
            .order_by(*audit_history.order_desc(m)) \
            .offset(want - 1).limit(2).all()
        if not rows:
            return None, False
        return (rows[0][0], rows[0][1]), len(rows) > 1

    def _count_by_transaction(self, db: Session, cursor: Optional[str], edge):
        """One row per transaction inside `(cursor, edge]`, counted BY POSTGRES.

        🔴 THIS IS THE WHOLE REPAIR OF THE WALK. The previous version pulled
        every scanned row into Python to count it, which cost 5.4 us/row and
        made the ceiling on the walk a ceiling on how much history the panel
        could show. Counting in the aggregate costs 0.64-1.11 us/row measured on
        the 2,900,000-row fixture, so the same latency budget buys roughly five
        times the walk - and the walk is what decides whether a user who just
        ingested two files sees 2 recent transactions or 100.

        `max(timestamp), max(id)` is the group's newest position, which is also
        its DISCOVERY position: the first time a newest-first scan meets a
        transaction is at its newest row. Sorting the aggregate by that pair
        therefore reproduces the order the old row-by-row walk produced.
        """
        m = models.AuditLog
        q = db.query(m.transaction_id, func.count().label("n"),
                     func.max(m.timestamp), func.max(m.id))
        q = self._ordered_rows(audit_history.apply_cursor(q, m, cursor), edge)
        rows = q.group_by(m.transaction_id).all()
        # Belt and braces on the `IS NOT NULL` above: comparing a None against a
        # datetime raises, and a sort that raises takes the whole projection
        # down. Ordered as oldest rather than allowed to do that.
        rows.sort(key=lambda r: (r[2] is not None, r[2] or _EPOCH, r[3]), reverse=True)
        return rows

    def _discover_groups(self, db: Session, limit_groups: int, settings: dict):
        """Walk newest-first over `(timestamp, id)` and name the groups.

        Returns `(order, counts, tops, bottom, truncated, next_cursor, scanned)`.

        No ORM entity and no pydantic here at all: this pass answers only "which
        transactions are the newest ones and how big are they". Everything
        expensive happens in `_hydrate`, over the bounded set this returns.

        THE COUNT IS A COUNT WITHIN THE WINDOW THE WALK COVERED, and that is
        what it always was: the previous implementation stopped the moment it
        met transaction #101, so any of the first 100 with older rows below that
        point was already undercounted. The window is now a chunk boundary
        rather than a single row, which can only make a count MORE complete.
        """
        max_scan = settings["recent_max_scan_rows"]
        chunk_rows = settings["recent_scan_chunk_rows"]

        order: List[str] = []
        counts: Dict[str, int] = {}
        tops: Dict[str, Tuple] = {}
        cursor = None
        bottom = None
        scanned = 0
        more_below = False

        while len(order) < limit_groups and scanned < max_scan:
            want = min(chunk_rows, max_scan - scanned)
            edge, more_below = self._chunk_edge(db, cursor, want)
            rows = self._count_by_transaction(db, cursor, edge)
            if not rows:
                break
            for tid, n, newest_ts, newest_id in rows:
                scanned += n
                key = tid if tid is not None else "no_tid"
                if key in counts:
                    counts[key] += n
                elif len(order) < limit_groups:
                    order.append(key)
                    counts[key] = n
                    tops[key] = (newest_ts, newest_id)
                # Beyond limit_groups the rows were still read, so they are
                # still counted as scanned - but the projection does not hold
                # them and `truncated` will say the list stops short of history.
            bottom = edge if edge is not None else bottom
            if edge is None:
                break
            # The cursor is carried as the SAME opaque token the response
            # publishes, so the position the walk resumes from and the position
            # a caller is handed can never be two different things.
            #
            # The `is None` branch below is BELT AND BRACES and is expected to
            # be unreachable: `_ordered_rows` already keeps null-stamped rows
            # out of `_chunk_edge`, so an edge always has a position to encode.
            # It stays because the failure it would prevent is not a crash - a
            # `None` cursor reads as "no cursor" and restarts the walk at the
            # top of the table, so the projection would return an ANSWER with
            # the head rows counted once per lap. Nothing downstream would look
            # wrong. There is no test on this branch, deliberately: the tested
            # guarantee is the `IS NOT NULL`, and a second alarm for a branch
            # that cannot fire would be an alarm nobody has ever heard.
            cursor = _cursor_token(edge)
            if cursor is None:
                more_below = True
                break

        truncated = bool(more_below)
        return (order, counts, tops, bottom, truncated,
                _cursor_token(bottom) if truncated else None, scanned)

    def _hydrate(self, db: Session, order, counts, tops, bottom,
                 watermark: int, per_group: int) -> List[Dict]:
        """Fetch and model ONLY the rows a group actually keeps.

        Bounded by `limit_groups * recent_logs_per_group` by construction: the
        walk may cross a million rows, but pydantic never sees more than what
        the projection holds. That separation is the entire point of splitting
        discovery from hydration.

        The `(timestamp, id)` range is not decoration - it pins each fetch to
        the SAME window the count came from, and its upper end is the group's
        own newest position, so the planner can walk down from there and stop
        after `per_group` matches instead of sorting the transaction's whole
        history. `id <= watermark` excludes rows another process committed while
        this scan ran; those stay above the watermark for the next refresh.
        """
        m = models.AuditLog
        groups = []
        for tid in order:
            # `_ordered_rows` and not a hand-written pair of bounds: hydration
            # must exclude exactly what the count excluded. Without its
            # `IS NOT NULL`, a transaction that has BOTH stamped and unstamped
            # rows would hydrate the unstamped ones first (PostgreSQL sorts
            # NULLs first under DESC) and hand pydantic a null into
            # `AuditLogResponse.timestamp: datetime` - a 500 on the route, from
            # rows the count never even saw.
            q = self._ordered_rows(db.query(m).filter(m.id <= watermark), bottom)
            if tid == "no_tid":
                q = q.filter(m.transaction_id.is_(None))
            else:
                q = q.filter(m.transaction_id == tid)
            top = tops.get(tid)
            if top is not None:
                q = q.filter(sa.tuple_(m.timestamp, m.id) <= sa.tuple_(*top))
            logs = []
            for obj in q.order_by(*audit_history.order_desc(m)).limit(per_group).all():
                log_dict = obj.__dict__.copy()
                log_dict["business_key"] = obj.business_key
                logs.append(schemas.AuditLogResponse.model_validate(log_dict))
            groups.append({"transaction_id": tid, "logs": logs,
                           "total_count": counts[tid]})
        return groups

    def load_initial(self, db: Session, limit_groups: int = 100,
                     force: bool = False, refresh_above: int = None):
        """Build the projection from the database.

        `refresh_above` is the staleness stamp a caller observed BEFORE it
        decided a rebuild was needed. It exists so that N threads that all see
        the same new write collapse into ONE rebuild instead of N: whoever gets
        the lock second finds the watermark already past that stamp and leaves.
        """
        with self._lock:
            if self.is_loaded and not force:
                return
            if (refresh_above is not None and self.is_loaded
                    and (self._db_max_id or 0) >= refresh_above):
                return

            settings = resolve_recent_settings()
            # 🔴 The watermark is read BEFORE the walk, not after. A row
            # committed WHILE the walk runs is not in the walk's result; if the
            # watermark were taken afterwards it would sit ABOVE that row and
            # the projection would never merge it. Taken first, such a row stays
            # above the watermark and the next refresh picks it up.
            watermark = db.query(func.max(models.AuditLog.id)).scalar() or 0

            order, counts, tops, bottom, truncated, cursor, scanned = \
                self._discover_groups(db, limit_groups, settings)
            self.groups = self._hydrate(db, order, counts, tops, bottom, watermark,
                                        settings["recent_logs_per_group"])
            self.is_loaded = True
            self._db_max_id = watermark
            self.truncated = truncated
            self.next_cursor = cursor
            self.scanned_rows = scanned

            if truncated and len(order) < limit_groups:
                print(f"[AuditCache] recent scan gave up after {scanned:,} rows with "
                      f"{len(order)}/{limit_groups} transaction groups "
                      f"(recent_max_scan_rows={settings['recent_max_scan_rows']:,}). "
                      f"The response is marked truncated.")

    def refresh_if_stale(self, db: Session, limit_groups: int = 100) -> bool:
        """Merge audit rows committed by a separate process.

        The audit cache belongs to the API process, while chain replay and file
        ingestion write from workers. A primary-key MAX probe keeps the common
        read path cheap; when it advances, the delta is merged rather than the
        whole projection rebuilt - a one-row replay must not wait on the entire
        history, and `test_audit_cache_cross_process` pins that.

        A delta is only cheaper than a rebuild while it is SMALL, because the
        merge models every new row in Python. Past
        `recent_refresh_max_delta_rows` it is not, and an ingestion's delta is
        not small - so above the threshold this falls through to the bounded
        rebuild, whose cost depends on `recent_max_scan_rows` and nothing else.
        """
        latest_id = db.query(func.max(models.AuditLog.id)).scalar() or 0
        settings = resolve_recent_settings()
        with self._lock:
            if not self.is_loaded or latest_id <= (self._db_max_id or 0):
                return False
            previous_id = self._db_max_id or 0

        if latest_id - previous_id > settings["recent_refresh_max_delta_rows"]:
            # Not a replay - a bulk load. Rebuild, bounded.
            self.load_initial(db, limit_groups, force=True, refresh_above=latest_id)
            return True

        # Ascending id order preserves each transaction's newest log at the
        # top as it is merged, and the primary-key range is independent of the
        # total size of historic audit data.
        rows = db.query(models.AuditLog)\
                 .filter(models.AuditLog.id > previous_id,
                         models.AuditLog.id <= latest_id)\
                 .order_by(models.AuditLog.id.asc()).all()
        per_group = settings["recent_logs_per_group"]
        popped = False
        with self._lock:
            for log_obj in rows:
                log_dict = log_obj.__dict__.copy()
                log_dict["business_key"] = log_obj.business_key
                log_model = schemas.AuditLogResponse.model_validate(log_dict)
                tid = log_obj.transaction_id or "no_tid"
                for group in self.groups:
                    if group["transaction_id"] == tid:
                        # 🔴 ABSORB, DO NOT ADD, WHAT AN EVENT ALREADY CLAIMED.
                        # `add_logs_batch` cannot advance the watermark (its log
                        # dicts carry id 0), so these very rows were merged once
                        # already. Counting them again is how 300 rows read 600.
                        _absorb_one(group)
                        if len(group["logs"]) < per_group:
                            group["logs"].insert(0, log_model)
                        if self.groups.index(group) > 0:
                            self.groups.remove(group)
                            self.groups.insert(0, group)
                        break
                else:
                    self.groups.insert(0, {
                        "transaction_id": tid,
                        "logs": [log_model],
                        "total_count": 1,
                    })
            while len(self.groups) > limit_groups:
                self.groups.pop()
                popped = True
            if popped:
                # The projection now ends EARLIER than the scan that built it,
                # so its recorded resume point is behind the new tail and would
                # hand back groups this list still holds. Say "there is more"
                # and admit the position is gone rather than name a wrong one.
                self.truncated = True
                self.next_cursor = None
            # A row committed between the MAX probe and range query is left
            # above this watermark and is safely picked up by the next read.
            self._db_max_id = latest_id
        return bool(rows)

    # ------------------------------------------------------------------
    # Live merges (WebSocket / in-process writes)
    # ------------------------------------------------------------------

    def add_log(self, log_dict: dict):
        """단일 로그 발생 시 캐시에 동적으로 편입합니다."""
        with self._lock:
            if not self.is_loaded:
                return

            tid = log_dict.get("transaction_id") or "no_tid"
            log_model = schemas.AuditLogResponse.model_validate(log_dict)
            per_group = resolve_recent_settings()["recent_logs_per_group"]

            # [Fix] 기존 그룹 중에 같은 transaction_id가 있는지 전체 검색
            for group in self.groups:
                if group["transaction_id"] == tid:
                    _claim(group, 1)
                    # [최적화] 인메모리 캡핑
                    if len(group["logs"]) < per_group:
                        group["logs"].insert(0, log_model)

                    # 해당 그룹을 최상단으로 이동 (최신 활동 트랜잭션 순서 유지)
                    if self.groups.index(group) > 0:
                        self.groups.remove(group)
                        self.groups.insert(0, group)
                    return

            # 없으면 새 그룹 생성
            new_group = {"transaction_id": tid, "logs": [log_model], "total_count": 0}
            _claim(new_group, 1)
            self.groups.insert(0, new_group)

    def add_logs_batch(self, logs_list: List[dict], message_total_count: int = None):
        """대량의 로그를 단일 락(Lock) 획득으로 캐시에 일괄 편입합니다.

        [P2 이슈 #10 / QA D-1] `message_total_count`의 의미론 = **이 메시지 1건이 나르는
        로그의 절단 전 실건수(=이 tx에 대한 이 메시지의 기여분)**이며, 그룹 total_count에는
        **누적(+=)** 된다. 종전 이름(`override_total_count`)과 SET 대입은 "같은 tx id로
        메시지가 2회 이상 도착하는 경로"에서 마지막 메시지가 이전 총계를 지워 과소 표기를
        일으켰다. 실제 도달 경로(2026-07-26 실측):

          - 체인 워커: 한 소스 tx가 여러 target_table 룰을 트리거하면 `chain_{tx}` 하나로
            target_table 수만큼 broadcast가 발신된다(chain_ingestion_worker target_table 루프).
            600건 → 50건 순 도착 시 종전 SET는 total_count를 50으로 만들었다(실제 650).
          - 워처(파일 인제션): 파일당 file_tx_id가 유일하고 통지도 1회 → 신·구 의미론 동일.
          - override 미전달(crud 내부 호출): 종전과 동일하게 len(logs) 누적.

        `logs_list` 하나에 서로 다른 tx가 섞여 있으면 기여분을 tx별로 나눌 근거가 없으므로
        message_total_count를 적용하지 않고 그룹별 len(logs)로 폴백한다(경고 1회).

        🔴 이 경로는 **워터마크(`_db_max_id`)를 전진시킬 수 없다** — 받는 log dict의
        `id`가 전부 0이기 때문이다(crud.create_audit_log가 리터럴 0을 쓰고,
        bulk_insert_mappings는 채번된 키를 되돌려 쓰지 않는다). 그래서 여기서 센 건수는
        **선불(credit)** 로 기록하고, 같은 행을 DB에서 다시 읽는 `refresh_if_stale`이
        자기 카운트를 그 선불에서 **상계**한다. 그러지 않으면 300행이 600으로 읽힌다.
        """
        if not logs_list:
            return
        with self._lock:
            if not self.is_loaded:
                return

            from collections import defaultdict
            settings = resolve_recent_settings()
            per_group = settings["recent_logs_per_group"]
            logs_by_tx = defaultdict(list)
            for log_dict in logs_list:
                tid = log_dict.get("transaction_id") or "no_tid"
                try:
                    log_model = schemas.AuditLogResponse.model_validate(log_dict)
                    logs_by_tx[tid].append(log_model)
                except Exception:
                    continue

            # 다중 tx가 섞인 메시지에서는 message_total_count를 어느 tx에 귀속시킬지 알 수 없다.
            # (현행 발신 경로는 메시지당 단일 tx — 방어적 폴백 + 1회 경고)
            effective_total = message_total_count
            if effective_total is not None and len(logs_by_tx) > 1:
                if not self._multi_tx_warned:
                    self._multi_tx_warned = True
                    print(
                        "[AuditCache] message_total_count ignored: batch contains "
                        f"{len(logs_by_tx)} transactions — falling back to per-group len(logs). "
                        "(Sender should emit one transaction per message.)"
                    )
                effective_total = None

            for tid, logs in logs_by_tx.items():
                contribution = effective_total if (effective_total is not None) else len(logs)

                found = False
                for group in self.groups:
                    if group["transaction_id"] == tid:
                        # [P2 #10] SET → 누적. 같은 tx가 여러 메시지로 나뉘어 도착해도
                        # 총계가 마지막 메시지 값으로 덮어써지지 않는다.
                        _claim(group, contribution)

                        for log_model in reversed(logs):
                            if len(group["logs"]) < per_group:
                                group["logs"].insert(0, log_model)

                        idx = self.groups.index(group)
                        if idx > 0:
                            self.groups.pop(idx)
                            self.groups.insert(0, group)
                        found = True
                        break

                if not found:
                    new_group = {"transaction_id": tid, "logs": logs[:per_group],
                                 "total_count": 0}
                    _claim(new_group, contribution)
                    self.groups.insert(0, new_group)

            while len(self.groups) > 100:
                self.groups.pop()
                self.truncated = True
                self.next_cursor = None

    def remove_deleted_rows(self, row_ids: List[str]):
        """삭제된 행의 과거 로그를 캐시에서 제거하지 않고 보존합니다."""
        pass


# ---------------------------------------------------------------------------
# The event credit
# ---------------------------------------------------------------------------
#
# `_event_credit` is "how much of this group's total_count was claimed by a
# notification whose rows the database has not yet been asked about". It is not
# a second count: `total_count` remains the ONE number the route serves, and the
# credit only decides whether the next database read ADDS to it or is absorbed
# by it.
#
# It cannot leak upward. An event claims N; the refresh that reads those same N
# rows absorbs exactly N. If a group is evicted and later rebuilt, the credit
# goes with it and the count is derived from the database alone.

def _claim(group: dict, contribution: int):
    """A notification adds to the total AND records that it did."""
    group["total_count"] = group.get("total_count", 0) + contribution
    group["_event_credit"] = group.get("_event_credit", 0) + contribution


def _absorb_one(group: dict):
    """One row read back from the database: absorb against credit, else add."""
    credit = group.get("_event_credit", 0)
    if credit > 0:
        group["_event_credit"] = credit - 1
        return
    group["total_count"] = group.get("total_count", 0) + 1


def _cursor_token(cursor) -> Optional[str]:
    """`(timestamp, id)` -> the opaque token `audit_history` already defines."""
    if not cursor or cursor[0] is None:
        return None
    return audit_history.encode_cursor(cursor[0], cursor[1])


audit_cache = AuditLogCache()
