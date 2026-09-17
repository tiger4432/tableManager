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

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1000


def iter_pages(db, model, columns=None, condition=None, chunk_size: int = DEFAULT_CHUNK_SIZE,
               limit: int = None, max_row_id: str = None):
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

    Yields: list of result rows. With `columns`, row[0] is always `row_id`.
    """
    if chunk_size is None or chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive (got {chunk_size})")

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
        page_size = chunk_size
        if limit is not None:
            remaining = limit - seen
            if remaining <= 0:
                return
            page_size = min(chunk_size, remaining)
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
