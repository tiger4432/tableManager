"""The ONE keyset page walk over a dynamic table.

WHY THIS EXISTS
    Four places need "read a whole table in bounded pages without OFFSET":
    `backfill_enrichment` (replay a rule over pre-existing rows),
    `enrichment_analysis` (walk the queue and its resolved complement),
    and `chain_replay` (R1 recompute).
    They were about to become hand-rolled `while True: ... row_id > last`
    loops, and this codebase already knows how that ends - `compose_map_id` had
    three implementations giving three answers.

    The traversal is centralized here so callers share one bounded keyset walk.

WHY row_id
    `row_id` is the primary key on every dynamic table, so ordering by it is
    index-ordered and a `row_id > last` seek is a range scan. No OFFSET means
    page N costs the same as page 1 - the requirement that makes this safe at
    10M rows (SKILL §2 "큰 OFFSET 금지").

WHY PAGES AND NOT ROWS
    The caller gets a page (list) at a time, so it can do one grouped query per
    page instead of one per row, and can commit per page. Yielding single rows
    would quietly invite N+1.
"""
import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1000
#: A run's first page (소유자 10-12 「인벤토리 리플레이는 1 행씩 시작해야지」).
FIRST_PAGE = 1


class PageSize:
    """THE ONE PAGE-SIZE RULE every page loop asks (소유자 10-12 「모든 소급은 5 초에 한 번은 진행 상황이 보이게 배치
    크기 조절해」): the first page is FIRST_PAGE; a page that took under half the declared page time
    (`pacing.page_seconds`) doubles the next, one that took longer cuts the next by its overshoot; never above `most`
    (a hand-given chunk_size is the ceiling). A page's time runs from one `next()` to the next - the read and whatever
    its caller did with it - less the pace's rests (`rest`)."""

    def __init__(self, most=None, seconds=None):
        import pacing

        self.most = most or DEFAULT_CHUNK_SIZE
        self.seconds = pacing.page_seconds() if seconds is None else seconds
        self.size = min(FIRST_PAGE, self.most)
        self._since = None

    def next(self) -> int:
        now = time.monotonic()
        if self._since is not None:
            took = now - self._since
            if took > self.seconds:
                self.size = max(1, int(self.size * self.seconds / took))
            elif took < self.seconds / 2:
                self.size = min(self.most, self.size * 2)
        self._since = now
        return self.size

    def rest(self, seconds) -> None:
        """The pace's rest between pages - slept, and not counted as the page's time."""
        time.sleep(seconds)
        if self._since is not None:
            self._since += seconds


def pages(items, start: int = 0, size=None):
    """`(the page of `items` from `start`, the start of the next page or None, the PageSize to hand the next call)`.
    A proposal that writes in pages (the join, the fold mapper - 총괄 e10c58e5e · 634c06fc3) cuts here, and asks the
    next page only when the write seat has written this one - so the time between the calls is the page's."""
    size = size or PageSize()
    after = start + size.next()
    return items[start:after], (after if after < len(items) else None), size


def iter_pages(db, model, columns=None, condition=None, chunk_size: int = DEFAULT_CHUNK_SIZE,
               limit: int = None, max_row_id: str = None, size=None):
    """Yield pages of rows ordered by `row_id`, keyset-seeked.

    :param columns: column expressions to select. `model.row_id` is ALWAYS
        selected first (the cursor), so callers get it whether they asked or not.
        None selects whole ORM entities.
    :param condition: SQLAlchemy condition applied to every page.
    :param limit: stop after this many rows in total (None = all).
    :param max_row_id: never read past this cursor. This is the SELF-WRITE GUARD:
        a replay whose target table IS its trigger table must not see the rows it
        is itself creating, or it walks its own output forever. Snapshot the max
        row_id before writing and pass it here.

    :param chunk_size: the largest page; each page's size is `PageSize`'s answer.
    :param size: the `PageSize` to ask, when the caller rests between pages (`PageSize.rest`).

    Yields: list of result rows. With `columns`, row[0] is always `row_id`.
    """
    if chunk_size is None or chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive (got {chunk_size})")
    size = size or PageSize(chunk_size)

    entity_mode = columns is None
    select_cols = None if entity_mode else [model.row_id] + list(columns)

    seen = 0
    last_row_id = ""
    while True:
        q = db.query(model) if entity_mode else db.query(*select_cols)
        q = q.filter(model.row_id > last_row_id)
        if condition is not None:
            q = q.filter(condition)
        if max_row_id is not None:
            q = q.filter(model.row_id <= max_row_id)
        page_size = size.next()
        if limit is not None:
            remaining = limit - seen
            if remaining <= 0:
                return
            page_size = min(page_size, remaining)
        page = q.order_by(model.row_id.asc()).limit(page_size).all()
        if not page:
            return
        last_row_id = page[-1].row_id if entity_mode else page[-1][0]
        seen += len(page)
        yield page
        if limit is not None and seen >= limit:
            return


def current_max_row_id(db, model) -> str:
    """Largest `row_id` present right now — the snapshot bound for a self-write
    replay. Returns None for an empty table (no bound needed)."""
    from sqlalchemy import func
    return db.query(func.max(model.row_id)).scalar()
