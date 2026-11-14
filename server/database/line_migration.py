"""The migration's copy of the old layers into the line tables - what server/scripts/copy_layers_to_lines.py runs a
page at a time (docs/design/CELL_SOURCE_OVERHAUL.md «이주»)."""
from . import lines


def declared_vs_stored(db, tables: dict) -> list:
    """(table, column, declared, stored) for every declared column whose stored kind differs from its declared
    type - such a column migrates as it is stored (text stays text). The pre-check REPORTS these; it does not
    refuse. tables = {name: table_cfg} of the tables to migrate."""
    out = []
    for name, cfg in tables.items():
        stored = lines.physical_kinds(db, name)
        for column, declared in (cfg.get("column_types") or {}).items():
            kind = declared if declared in ("number", "datetime") else "string"
            if column in stored and stored[column] != kind:
                out.append((name, column, declared, stored[column]))
    return out


def report_line(differences: list):
    """The operator line the pre-check prints and the migration screen shows, or None."""
    if not differences:
        return None
    listed = ", ".join(f"{t}.{c} (declared {d}, stored {s})" for t, c, d, s in differences)
    return f"Columns migrated as stored: {listed} - retyping them is a separate step"


COPY_WORK = "copy"
#: a layer value that is a JSON object: no writer is known to store one (box: 0 of 39.5M), so the copy refuses the
#: page rather than guess how to read it (lead 11-11) - if it happens, unwrapping goes in front of line_text, once
OBJECT_HELD = "holds an object value"


def copy_refusal(table, row_id, column, source, why) -> str:
    """The one sentence a copy refuses a page with - an object value, or a value today's write refuses (lead 11-11):
    the old layer may not win, so the grid cannot fix it and ops has no SQL - the lead decides on the row."""
    return (f"Cannot copy {table}: row {row_id} column {column} (source {source}) {why} - "
            "nothing of this page was copied; tell the lead")


class AlreadyCopied(Exception):
    """t's old layers were copied once already (an audit_batches row of work kind «copy») - copying again would
    double every line."""

    def __init__(self, table, lines):
        self.table, self.lines = table, lines
        super().__init__(f"{table}: already copied, {lines} lines")


def _copyable(db, table, table_cfg):
    if not isinstance(table_cfg, dict) or not lines.keeps_lines(table, table_cfg):
        raise ValueError(f"{table}: not a declared table that keeps lines - nothing to copy")
    if not lines.has_lines(db, table):
        raise ValueError(f"{table}: its lines are not built yet - the schema sync builds them first")
    from sqlalchemy import inspect

    insp = inspect(db.connection())
    if not insp.has_table(OLD_LAYERS):
        raise ValueError(f"{table}: there is no {OLD_LAYERS} table here - nothing to copy from")
    missing = sorted(set(OLD_COLUMNS) - {c["name"] for c in insp.get_columns(OLD_LAYERS)})
    if missing:
        # the old table is cold after the landing - nothing adds its columns any more (lead 11-11 ㄱ)
        raise ValueError(f"{table}: {OLD_LAYERS} has no {', '.join(missing)} - the copy reads them; "
                         f"this database cannot be copied")


#: the old layer table and the columns copy_page reads from it
OLD_LAYERS = "cell_sources"
OLD_COLUMNS = ("table_name", "row_id", "column_name", "source_name", "value", "ingested_at", "updated_by",
               "owner_rule", "owner_key")


def copy_total(db, table: str) -> int:
    """How many old layer cells t has in cell_sources - the unit copy_page counts in, for the progress line."""
    from sqlalchemy import func, select

    from .models import CellSource

    cs = CellSource.__table__
    return db.execute(select(func.count()).select_from(cs).where(cs.c.table_name == table)).scalar() or 0


def _cursor_record(db, table: str, transaction_id: str):
    from .models import FileIngestionCheckpoint as Record

    return db.query(Record).filter(Record.table_name == table,
                                   Record.file_signature == transaction_id).one_or_none()


def copy_cursor(db, table: str, table_cfg: dict, transaction_id: str) -> tuple:
    """(the row id after which an interrupted copy resumes, or None; True when this call seeded it) - THE resume
    position: its own record (a file_ingestion_checkpoints row, file_signature the copy's transaction_id), written by
    copy_page in each page's transaction, so no write moves it. Before it, the position was the copy lines' highest
    row id, and a key merge moves a row's lines onto its key holder: a holder past the position made the resume skip
    every row up to it (lead 11-14, the merge-between-runs gate). No record but copy lines there - a copy stopped
    before this record existed: seeded once, in the caller's transaction, from those lines' highest row id. That is
    still the truth on a database the old release ran on since (ops 11-14: ⑥ stopped half way, back to 11-11e) - the
    old release has no line tables, so nothing moved a line; after a 14b key merge it would not be."""
    from sqlalchemy import func, select

    from .models import FileIngestionCheckpoint as Record

    record = _cursor_record(db, table, transaction_id)
    if record is not None:
        return record.cursor, False
    lt = lines.shape(db, table, table_cfg)["lines"]
    seed = db.execute(select(func.max(lt.c.row_id)).where(lt.c.batch == transaction_id)).scalar()
    if seed is None:
        return None, False
    db.add(Record(table_name=table, file_signature=transaction_id, cursor=seed, transaction_id=transaction_id))
    db.flush()
    return seed, True


def _note_page(db, table, transaction_id, page, copied, seconds, done) -> None:
    """The page just copied on its table's record (`copy_cursor`), in the page's transaction."""
    from ingestion.checkpoint import STATUS_DONE, STATUS_IN_PROGRESS

    from .models import FileIngestionCheckpoint as Record

    record = _cursor_record(db, table, transaction_id)
    if record is None:
        record = Record(table_name=table, file_signature=transaction_id, transaction_id=transaction_id,
                        processed_rows=0, pages=0, layers=0, seconds=0.0)
        db.add(record)
    if page:                                       # a copy's last page may be empty: a full page cannot tell it is last
        record.cursor = page[-1]
        record.processed_rows = (record.processed_rows or 0) + len(page)
        record.pages = (record.pages or 0) + 1
        record.layers = (record.layers or 0) + copied
    record.seconds = (record.seconds or 0.0) + seconds
    record.status = STATUS_DONE if done else STATUS_IN_PROGRESS
    db.flush()


def unrecorded_page(db, table: str, table_cfg: dict, after, page_size: int) -> tuple:
    """([(row_id, column, t's value, its winning line's value)], cells compared, next row id or None) - of the next
    `page_size` rows of t after row id `after`, each cell whose won_by line holds another value than t shows: a write
    that no line records (lead 11-14 - the old release 11-11e writing a row after the copy moved it; its layer is in
    cell_sources, and `copy_page(rows=)` brings it over). A won_by naming no line is listed with None. The formula's
    mark (FORMULA_WON) holds no line and is not compared. Reads only."""
    from sqlalchemy import select

    from . import crud

    s = lines.shape(db, table, table_cfg, assign=False)
    lt, bits, kinds = s["lines"], s["bits"], s["kinds"]
    t = lines.current_table(db, table, table_cfg, won_by=True)
    q = select(t).order_by(t.c.row_id).limit(page_size)
    rows = db.execute(q if after is None else q.where(t.c.row_id > after)).mappings().all()
    won = {r["row_id"]: lines.won_by_cells(r[lines.WON_BY], bits) for r in rows}
    ids = sorted({lid for cells in won.values() for lid in cells.values() if lid != lines.FORMULA_WON})
    cells = [lt.c[lines.value_column(c)] for c in bits if lines.value_column(c) in lt.c]
    said = {}
    for at in range(0, len(ids), 1000):
        for line in db.execute(select(lt.c.line_id, *cells).where(lt.c.line_id.in_(ids[at:at + 1000]))).mappings():
            said[line["line_id"]] = line
    out, compared = [], 0
    for r in rows:
        for column, line_id in sorted(won[r["row_id"]].items()):
            if line_id == lines.FORMULA_WON or column not in t.c:
                continue
            compared += 1
            kind = kinds.get(column, "string")
            line = said.get(line_id)
            value = None if line is None else crud.line_value(line[lines.value_column(column)], kind)
            if line is None or crud.line_text(r[column], kind) != crud.line_text(value, kind):
                out.append((r["row_id"], column, r[column], value))
    return out, compared, (rows[-1]["row_id"] if len(rows) == page_size else None)


def take_copy_lines(db, table, cfg, rows, tx) -> int:
    """Take these rows' copy lines (batch `tx`) out of t__lines, and the won_by entries naming them - before
    copy_page(rows=) copies them again (copy_layers_to_lines --rows). In the caller's transaction. -> lines taken."""
    from sqlalchemy import delete, select, update

    s = lines.shape(db, table, cfg)
    lt, t = s["lines"], lines.current_table(db, table, cfg)
    gone = set(db.execute(select(lt.c.line_id).where(lt.c.batch == tx, lt.c.row_id.in_(rows))).scalars())
    if gone:
        db.execute(delete(lt).where(lt.c.line_id.in_(sorted(gone))))
        for row_id, won_by in lines.won_by_of(db, table, rows, s["bits"]).items():
            kept = {c: lid for c, lid in won_by.items() if lid not in gone}
            if kept != won_by:
                db.execute(update(t).where(t.c.row_id == row_id).values(
                    {lines.WON_BY: lines.won_by_stored(kept, s["bits"])}))
    return len(gone)


def copy_page(db, table: str, table_cfg: dict, after, page_size: int, *, transaction_id: str,
              written_by: str = "system", mismatched: list = None, rows: list = None) -> tuple:
    """Copy the old layers (cell_sources) of the next `page_size` rows of t after row id `after` into t__lines: one
    «write» line per (row, source, ingested_at, updated_by, owner), each value the one today's write would have stored
    (`crud.cast_value_by_type` on the declared type, then `crud.line_text` - lead 11-11) - so each cell keeps its own time
    and the order rank_terms walks gives today's winner. A column a later write already heads keeps that head (the
    copied line is history under it). t's values are not touched; won_by names a line only where the line's value
    is what t shows. In the caller's transaction - the caller commits per page.
    The last page (next_after None) writes the «copy» audit row; a first page (after None) on a copied table
    raises AlreadyCopied, on a table an earlier run left half copied resumes after its record (`copy_cursor`), which
    each page moves to its last row - with the page's rows, layers and seconds.
    `mismatched`: filled with (row_id, column, t's value, the lines' winner) where the copied lines merged again do not
    give what t shows - the migration's gate (owner 11-11); the caller records them (owner ㄴ).
    `rows`: these rows only, as a page - `--rows` copying a record's rows again; no resume, no «copy» audit row.
    -> (cells copied, next_after or None)."""
    import time

    from sqlalchemy import func, select, update

    from . import crud
    from .models import CellSource

    began = time.perf_counter()
    _copyable(db, table, table_cfg)
    ab = lines.AuditBatch.__table__
    only = rows                                        # `rows` is t's rows of the page below
    if only is None and after is None:
        done = db.execute(select(ab.c.transaction_id).where(ab.c.table_name == table, ab.c.work_kind == COPY_WORK)
                          .limit(1)).scalar()
        if done is not None:
            s = lines.shape(db, table, table_cfg)
            n = db.execute(select(func.count()).select_from(s["lines"])
                           .where(s["lines"].c.batch == done)).scalar() or 0
            raise AlreadyCopied(table, n)
        after = copy_cursor(db, table, table_cfg, transaction_id)[0]
    cs = CellSource.__table__
    t = lines.current_table(db, table, table_cfg)
    q = select(cs.c.row_id).where(cs.c.table_name == table).group_by(cs.c.row_id).order_by(cs.c.row_id)
    if only is not None:
        page, next_after = db.execute(q.where(cs.c.row_id.in_(sorted(only)))).scalars().all(), None
    else:
        q = q.limit(page_size) if after is None else q.where(cs.c.row_id > after).limit(page_size)
        page = db.execute(q).scalars().all()
        next_after = page[-1] if len(page) == page_size else None
    rows = set(db.execute(select(t.c.row_id).where(t.c.row_id.in_(page))).scalars()) if page else set()
    s = lines.shape(db, table, table_cfg)
    lt, bits, chunks = s["lines"], s["bits"], s["chunks"]
    kinds = lines.value_types(db, table)
    declared = table_cfg.get("column_types") or {}
    heads = {}
    if rows:
        head_cols = lines.bit_columns("head", chunks)
        for r in db.execute(select(lt.c.row_id, lt.c.source_name, *[lt.c[h] for h in head_cols])
                            .where(lt.c.row_id.in_(rows))):
            held = heads.setdefault((r[0], r[1]), [0] * chunks)
            for i, v in enumerate(r[2:]):
                held[i] |= v
    cells = db.execute(select(cs.c.row_id, cs.c.column_name, cs.c.source_name, cs.c.value, cs.c.ingested_at,
                              cs.c.updated_by, cs.c.owner_rule, cs.c.owner_key)
                       .where(cs.c.table_name == table, cs.c.row_id.in_(rows))).all() if rows else []
    groups = {}
    copied = 0
    for row_id, col, source, value, at, by, rule, key in cells:
        if col not in bits:
            continue                                   # a column t no longer holds
        if isinstance(value, dict):                    # a shape no writer is known to store - refused, not guessed
            raise ValueError(copy_refusal(table, row_id, col, source, OBJECT_HELD))
        g = groups.setdefault((row_id, source, at, by, rule, key), {})
        try:
            value = crud.cast_value_by_type(value, declared.get(col, "string"), col, table)
        except crud.CellRefused as refused:
            raise ValueError(copy_refusal(table, row_id, col, source, "holds %r, which the write refuses: %s is expected"
                                          % (refused.value, refused.expected))) from None
        g[col] = crud.line_text(value, kinds.get(col, "string"))
        copied += 1
    empty = {**{lines.value_column(c): None for c in bits},
             **{f"{f}_{i}": 0 for f in lines.BIT_FAMILIES for i in range(chunks)}}
    out = []
    for (row_id, source, at, by, rule, key), vals in groups.items():
        written = [0] * chunks
        for col in vals:
            b = bits[col]
            written[b // lines.BITS_PER_CHUNK] |= lines._mask(b)
        held = heads.get((row_id, source), [0] * chunks)
        out.append({**empty, "line_kind": "write", "source_name": source, "at": at, "written_by": by,
                    "batch": transaction_id, "owner_rule": rule, "owner_key": key, "row_id": row_id,
                    **{lines.value_column(c): v for c, v in vals.items()},
                    **{f"written_{i}": written[i] for i in range(chunks)},
                    **{f"head_{i}": written[i] & ~held[i] for i in range(chunks)}})
    if out:
        names = sorted({o["source_name"] for o in out})
        lines.note_sources(db, names, copies={n: crud.merged_layer_origin(n) for n in names
                                              if crud.merged_layer_origin(n) is not None})
        lines.insert_lines(db, lt, out)
        shown = {r[0]: r for r in db.execute(select(t).where(t.c.row_id.in_(rows)))}
        named = []
        for row_id, cols in lines.merge(db, table, table_cfg, sorted(rows)).items():
            now = shown[row_id]._mapping
            won = {c: lid for c, (v, lid) in cols.items() if lid is not None and c in t.c
                   and crud.line_text(now[c], kinds.get(c, "string")) == crud.line_text(v, kinds.get(c, "string"))}
            if mismatched is not None:
                mismatched.extend((row_id, c, now[c], v) for c, (v, lid) in sorted(cols.items())
                                  if lid is not None and c in t.c and c not in won)
            if won:
                named.append([row_id, lines.won_by_stored({**lines.won_by_cells(now[lines.WON_BY], bits), **won}, bits)])
        if named and lines.sets_at_once(db):             # one set statement for the page (lead 11-12)
            crud.update_by_arrays(db, t, [lines.WON_BY], named, None)
        else:
            for row_id, won_by in named:
                db.execute(update(t).where(t.c.row_id == row_id).values({lines.WON_BY: won_by}))
    if only is None and (page or next_after is None):
        _note_page(db, table, transaction_id, page, copied, time.perf_counter() - began, next_after is None)
    if next_after is None and only is None:
        db.execute(ab.insert().values(transaction_id=transaction_id, table_name=table, written_by=written_by,
                                      work_kind=COPY_WORK, at=func.now()))
    return copied, next_after
