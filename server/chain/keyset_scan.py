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
import contextlib
import contextvars
import math
import time

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1000
#: A run's first page (소유자 10-12 「인벤토리 리플레이는 1 행씩 시작해야지」).
FIRST_PAGE = 1


def fixed_and_per_row(timed):
    """(F, c): least squares page seconds = F + c x rows over `timed` [(rows, seconds), ...] in page order, the first
    page left out - its one-off ~2.9 s (the first reload and progress) read c 60 ms as F 0.61 / c 48 (B's board 11-08).
    None until two pages past it, while every size is one, or when the line has no fixed cost or no cost a row to read
    (F < 0, c <= 0). `PageSize`'s and the run's progress line's one fit (소유자 11-08: the page size reads F apart)."""
    points = timed[1:]
    n = len(points)
    if n < 2:
        return None
    mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    if not sxx:
        return None
    c = sum((x - mx) * (y - my) for x, y in points) / sxx
    fixed = my - c * mx
    return (fixed, c) if fixed >= 0 and c > 0 else None


def next_size(size, took, seconds, most, rates, fit=None):
    """The page after one of `size` rows that took `took` s. With `fit` (F, c - `fixed_and_per_row`): F is taken off
    the page, so a page is what c fills in `seconds` and takes F longer (소유자 11-08 - a 2.5 s fixed cost held pages at
    190 rows, 24 rows a second). Without: what the slowest of `rates` (rows a second, None unknown) fills. A page whose
    rows alone overshoot `seconds` cuts the next by that overshoot; else at most double; never above `most`.
    `PageSize`'s rule, and a retroactive chain line's batch (`slots.next_row_budget`)."""
    fixed, rate = (fit[0], 1 / fit[1]) if fit else (0.0, min((r for r in rates if r), default=None))
    if took - fixed > seconds:
        return max(1, int(size * seconds / (took - fixed)))
    return min(most, size * 2, math.ceil(rate * seconds) if rate else size * 2)


class PageSize:
    """THE ONE PAGE-SIZE RULE every retroactive page loop asks (소유자 10-12 「모든 소급은 5 초에 한 번은 진행 상황이 보이게 배치
    크기 조절해」): the first page is FIRST_PAGE; a page that took under half the declared page time
    (`pacing.page_seconds`) doubles the next, one under the page time grows the next to what the slower of its own and
    the page before's rate fills in that time (at most double - a fixed cost between half and the whole page time held
    a one-row page there; the slower rate - 총괄 2ea5ee2a7, 응용: a page sized by a fast page before it took 5.2 s), one
    that took longer cuts the next by its overshoot; once a fixed cost a page is read apart (`fixed_and_per_row`) the
    rates are c alone and the overshoot is past F (`next_size`); never above `most`
    (a hand-given chunk_size is the ceiling). A page's time runs from one `next()` to the next - the read and whatever
    its caller did with it - less the pace's rests (`rest`). A live proposal's pages (`pages`) stay fixed: there one
    write is one event (총괄 a02ad0f2b NO-GO ①)."""

    def __init__(self, most=None, seconds=None):
        import pacing

        self.most = most or DEFAULT_CHUNK_SIZE
        self.seconds = pacing.page_seconds() if seconds is None else seconds
        self.size = min(FIRST_PAGE, self.most)
        self._since = self._rate = None
        self.timed = []                         # (rows, seconds) of every page so far - `fixed_and_per_row`'s input

    def next(self) -> int:
        now = time.monotonic()
        if self._since is not None:
            took = now - self._since
            rate = self.size / took if took > 0 else None
            self.timed.append((self.size, took))
            self.size = next_size(self.size, took, self.seconds, self.most, (rate, self._rate),
                                  fixed_and_per_row(self.timed))
            self._rate = rate
        self._since = now
        return self.size

    def rest(self, seconds) -> None:
        """The pace's rest between pages - slept, and not counted as the page's time."""
        time.sleep(seconds)
        if self._since is not None:
            self._since += seconds


def step_of(checkpoint):
    """`step(name, page, pages, rows)` - the step seat on a run's checkpoint (`retroactive._checkpoint`, 총괄 e71f7d6f1):
    a line and the progress time inside a page; a no-op when there is none (a dry run, a direct call)."""
    return getattr(checkpoint, "step", None) or (lambda *_: None)


#: The control of the retroactive run this thread works for, set around the run (`retroactive._run_to_the_end`) - so a
#: stage below the page loop, where no checkpoint is handed (the translator, the ledger store), reaches that run's line.
RUN_CONTROL = contextvars.ContextVar("retroactive_run_control", default=None)


@contextlib.contextmanager
def stage(name, rows=None):
    """One stage inside a page (총괄 d9be013cb, 소유자 「내부 진행 코드마다 로그」): its line when it ends - the step line,
    with its own seconds - and the stage the run's beat says it is in while it runs (`RunControl.stage`). Yields a dict:
    a `note` written there ends the line. Outside a run (the ledger follow-up, a CLI's direct call) the dict alone."""
    control = RUN_CONTROL.get()
    if control is None:
        yield {}
        return
    with control.stage(name, rows) as said:
        yield said


def say(sentence) -> bool:
    """One line in the log of the run this thread works for (`RunControl.say`) - whatever `retroactive_debug` says.
    -> whether there was a run to say it to."""
    control = RUN_CONTROL.get()
    if control is not None:
        control.say(sentence)
    return control is not None


def debugging() -> bool:
    """Are the stage lines on for the run this thread works for (`retroactive_debug`) - what a stage asks before it
    spends a statement on its note (an EXPLAIN)."""
    control = RUN_CONTROL.get()
    return bool(control is not None and control.debug)


def pages(items, start: int = 0):
    """`(the page of `items` from `start`, the start of the next page or None)` - DEFAULT_CHUNK_SIZE at a time, and
    the page count when `start` is 0. A proposal that writes in pages (the join, the fold mapper - 총괄 e10c58e5e ·
    634c06fc3) cuts here, so its pages and the line that counts them have one size."""
    size = DEFAULT_CHUNK_SIZE
    after = start + size
    return items[start:after], (after if after < len(items) else None), -(-len(items) // size)


#: Rows a whole-key read takes from the server cursor at a time (`keyed_rows`).
KEYED_READ_ROWS = 10000


def keyed_rows(db, model, columns, key_of, condition=None, max_row_id=None) -> dict:
    """{key: [row_id, ...]} of the rows `condition` picks - a row's key is `key_of({column: value})` over `columns`, the
    keys in the row_id order of their first row. One streamed read of the row_id and those columns; the replay's
    whole-key pages (`key_pages`) and the fold's groups (`replay.fold_units`) stand on it."""
    from sqlalchemy import select

    names = list(columns)
    statement = select(model.row_id, *(getattr(model, name) for name in names)).order_by(model.row_id)
    if condition is not None:
        statement = statement.where(condition)
    if max_row_id is not None:
        statement = statement.where(model.row_id <= max_row_id)
    keyed, spelled = {}, {}                        # spelled: raw values -> key, asked once a distinct value set
    for row in db.execute(statement.execution_options(yield_per=KEYED_READ_ROWS)):
        raw = tuple(row[1:])
        if raw not in spelled:
            spelled[raw] = key_of(dict(zip(names, raw)))
        keyed.setdefault(spelled[raw], []).append(row[0])
    return keyed


def key_pages(keyed, size, log=logger.info):
    """Pages of row_ids from `keyed` (`keyed_rows`) that end only between keys - a key's rows are on one page (소유자 10-20
    「집계하는 체인인데도 리플레이 쪼개네」). A page takes whole keys up to `size.next()` rows; a key with more rows than the
    largest page (`size.most`) is a page that size, said in one line."""
    page, n = [], size.next()
    for key, ids in keyed.items():
        if page and len(page) + len(ids) > n:
            yield page
            page, n = [], size.next()
        if len(ids) > size.most:
            log("[pages] key %s holds %d rows, more than a page of %d - its page holds them all" % (key, len(ids), size.most))
        page.extend(ids)
    if page:
        yield page


def iter_pages(db, model, columns=None, condition=None, chunk_size: int = DEFAULT_CHUNK_SIZE,
               limit: int = None, max_row_id: str = None, size=None, ranged: bool = False):
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
    :param ranged: `condition` judged within each page's row_id range - the table's next `PageSize` rows by the
        primary key, its end named by one index read - so one statement reads at most a page of the table
        wherever the matching rows sit (총괄 ff4eb2cf0 6: in the WHERE, the gap before a sparse match was one
        statement - 8.68 s at 4M rows with the first 50 queued). A page may then hold none of them.

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
            page_size = page_size if ranged else min(page_size, remaining)
        if ranged:
            # the range's end: the page_size-th row after the cursor, read off the primary key alone
            bound = (db.query(model.row_id).filter(model.row_id > last_row_id,
                                                   *([model.row_id <= max_row_id] if max_row_id is not None else []))
                     .order_by(model.row_id.asc()).offset(page_size - 1).limit(1).scalar())
            if bound is not None:
                q = q.filter(model.row_id <= bound)
            q = q.order_by(model.row_id.asc())
            page = (q.limit(limit - seen) if limit is not None else q).all()
            seen += len(page)
            if bound is None:
                if page:
                    yield page
                return
            last_row_id = bound
            yield page
            if limit is not None and seen >= limit:
                return
            continue
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
