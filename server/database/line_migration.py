"""migrate_to_lines - the stage functions B's retro job calls (docs/design/CELL_SOURCE_OVERHAUL.md «이주»)."""
from . import lines


class GateFailed(Exception):
    """A migration gate found a difference; the stage rolls back and the job stops."""


class SwapLockBusy(Exception):
    """The swap could not take its table lock in time; the job retries."""


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


def copied_through(db, table: str, table_cfg: dict, transaction_id: str):
    """The last row id an interrupted copy already moved - the highest row of t's lines whose batch is the copy's
    transaction_id (a page commits whole, so every row up to it is copied) - or None. copy_page resumes from it when
    asked from the start; the driver may say it (B 11-11). The driver passes one transaction_id per table across
    runs, so this finds the earlier run's lines."""
    from sqlalchemy import func, select

    lt = lines.shape(db, table, table_cfg)["lines"]
    return db.execute(select(func.max(lt.c.row_id)).where(lt.c.batch == transaction_id)).scalar()


def copy_page(db, table: str, table_cfg: dict, after, page_size: int, *, transaction_id: str,
              written_by: str = "system", mismatched: list = None) -> tuple:
    """Copy the old layers (cell_sources) of the next `page_size` rows of t after row id `after` into t__lines: one
    «write» line per (row, source, ingested_at, updated_by, owner), each value the one today's write would have stored
    (`crud.cast_value_by_type` on the declared type, then `crud.line_text` - lead 11-11) - so each cell keeps its own time
    and the order rank_terms walks gives today's winner. A column a later write already heads keeps that head (the
    copied line is history under it). t's values are not touched; won_by names a line only where the line's value
    is what t shows. In the caller's transaction - the caller commits per page.
    The last page (next_after None) writes the «copy» audit row; a first page (after None) on a copied table
    raises AlreadyCopied, on a table an earlier run left half copied resumes after copied_through.
    `mismatched`: filled with (row_id, column, t's value, the lines' winner) where the copied lines merged again do not
    give what t shows - the migration's gate (owner 11-11); the caller rolls the page back.
    -> (cells copied, next_after or None)."""
    from sqlalchemy import func, select, update

    from . import crud
    from .models import CellSource

    _copyable(db, table, table_cfg)
    ab = lines.AuditBatch.__table__
    if after is None:
        done = db.execute(select(ab.c.transaction_id).where(ab.c.table_name == table, ab.c.work_kind == COPY_WORK)
                          .limit(1)).scalar()
        if done is not None:
            s = lines.shape(db, table, table_cfg)
            n = db.execute(select(func.count()).select_from(s["lines"])
                           .where(s["lines"].c.batch == done)).scalar() or 0
            raise AlreadyCopied(table, n)
        after = copied_through(db, table, table_cfg, transaction_id)
    cs = CellSource.__table__
    t = lines.current_table(db, table, table_cfg)
    q = select(cs.c.row_id).where(cs.c.table_name == table).group_by(cs.c.row_id).order_by(cs.c.row_id).limit(page_size)
    if after is not None:
        q = q.where(cs.c.row_id > after)
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
                named.append([row_id, {**(now[lines.WON_BY] or {}), **won}])
        if named and lines.sets_at_once(db):             # one set statement for the page (lead 11-12)
            crud.update_by_arrays(db, t, [lines.WON_BY], named, None)
        else:
            for row_id, won_by in named:
                db.execute(update(t).where(t.c.row_id == row_id).values({lines.WON_BY: won_by}))
    if next_after is None:
        db.execute(ab.insert().values(transaction_id=transaction_id, table_name=table, written_by=written_by,
                                      work_kind=COPY_WORK, at=func.now()))
    return copied, next_after
