"""Every write of a declared table - the cell-source overhaul's one write (docs/design/CELL_SOURCE_OVERHAUL.md «쓰기»).

`write_lines` works inside the caller's transaction, a few statements a batch and none a row: claim the entities'
current lines (1), leave out what changes nothing (2), one line a remaining item (3), take the head bits off the lines
the new ones replace (4), merge the touched current lines again (5), one audit row a work kind (6). The table shape,
the bit map, the rank and the winners query are `database.lines`' - nothing here spells «__now» or «__lines».

An item is a dict:
    row_id        the entity, or None for one named by its key
    key           {key column: value} - composed by `crud.compose_business_key`; a given `business_key_val` wins
    line_kind     "write" (default) · "withdraw" · "deleted" · "mark"
    values        {column: value} for a write - cast here by `crud.cast_value_by_type`
    columns       [column] for a withdraw
    source_name · written_by · input_row · owner_rule · owner_key · confirmed
    folds         source names whose head bits the write's columns also take off (a file's folded layer)
`kind` is the writing seat's word (funnel · chain · formula · withdraw · delete · notation · merge · mark · seed); the
work kind of each item (edit · new · delete · withdraw · merge · mark) is decided in step 1.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, and_, bindparam, cast, delete, exists, insert, literal, or_, select
from sqlalchemy import union_all, update

from database import crud, lines

WRITE, WITHDRAW, DELETED, MARK = "write", "withdraw", "deleted", "mark"
LINE_KINDS = (WRITE, WITHDRAW, DELETED, MARK)
#: bound parameters one statement carries at most - under sqlite's 32,766; and the rows one UNION ALL joins, under
#: sqlite's 500 compound SELECTs
PARAMS_MOST, UNION_MOST = 30000, 500
BITS_A_CHUNK = 64


def _signed(word: int) -> int:
    """A 64-bit word as the signed bigint the column stores - bit 63 is the sign."""
    return word - (1 << 64) if word >= 1 << 63 else word


def _masks(bits: dict, chunks: int, columns) -> list:
    """The columns as one signed word a chunk."""
    words = [0] * chunks
    for c in columns:
        words[bits[c] // BITS_A_CHUNK] |= 1 << (bits[c] % BITS_A_CHUNK)
    return [_signed(w) for w in words]


def _bit(bits: dict, c: str):
    """(chunk, signed mask) of one column."""
    return bits[c] // BITS_A_CHUNK, _signed(1 << (bits[c] % BITS_A_CHUNK))


def _data(bits: dict) -> list:
    """The declared columns of the bit map - the framework columns (row_id · business_key_val · created_at ·
    updated_at) have slots too but are the line's own, not a value it says."""
    framework = {name for name, _type in lines.FRAMEWORK}
    return [c for c in bits if c not in framework]


def _pages(seq, width: int, most=None):
    seq = list(seq)
    size = max(1, min(PARAMS_MOST // max(1, width), most or PARAMS_MOST))
    for at in range(0, len(seq), size):
        yield seq[at:at + size]


def write_lines(db, table: str, items, *, kind: str, transaction_id):
    """Write `items` into `table` as lines - see the module. Returns
    {"changed": {row_id: {"old": {col: value}|None, "new": {col: value}|None, "work": work kind}},
     "lines": lines written, "left_out": items that changed nothing,
     "audit": [{"transaction_id", "table_name", "changed_rows", "kind", "written_by"}] one an audit row - `kind` its work
     kind, `changed_rows` the distinct row_ids it wrote lines for in this write} - `old` is the current line step 1
    locked, `new` the one step 5 wrote (None: deleted), what the broadcast and the outbox read (one author)."""
    _open(db)
    cfg = crud.TABLE_CONFIG[table]
    shape = lines.shape(db, table, cfg)
    now, ln, bits, chunks = shape["now"], shape["lines"], shape["bits"], shape["chunks"]
    data = _data(bits)
    items = [dict(it, line_kind=it.get("line_kind") or WRITE) for it in items]
    for it in items:
        if it["line_kind"] not in LINE_KINDS:
            raise ValueError("write_lines: line kind %r is not one of %s" % (it["line_kind"], ", ".join(LINE_KINDS)))
        unknown = [c for c in list(it.get("values") or ()) + list(it.get("columns") or ()) if c not in data]
        if unknown:
            raise ValueError("write_lines: %r is not a column of %r" % (unknown[0], table))
    at = crud.batch_write_instant(db)
    if at is None:                                 # a line's at is its history - never NULL (C 11-10)
        raise RuntimeError("write_lines: the database gave no time for %r's lines" % table)

    targets, old, keys = _claim(db, table, cfg, now, items)
    kept, left_out = _leave_out(db, table, cfg, ln, bits, chunks, items, targets)
    work = {i: ("merge" if kind == "merge" else {DELETED: "delete", WITHDRAW: "withdraw", MARK: "mark"}.get(
        items[i]["line_kind"], "edit" if targets[i] in old else "new")) for i in kept}
    written = _lines(db, ln, bits, chunks, items, kept, targets, keys, at, transaction_id)
    _heads(db, ln, chunks, written)
    gone = sorted({targets[i] for i in kept if items[i]["line_kind"] == DELETED})
    for page in _pages(gone, 1):
        db.execute(delete(now).where(now.c.row_id.in_(page)))
    new = _merge_now(db, table, cfg, shape, sorted({targets[i] for i in kept} - set(gone)), at)
    changed = {}
    for i in sorted(kept):
        row_id = targets[i]
        changed.setdefault(row_id, {"old": old.get(row_id), "new": new.get(row_id), "work": work[i]})
    audit = _audit(db, table, items, kept, targets, work, transaction_id, at)
    return {"changed": changed, "lines": len(kept), "left_out": left_out, "audit": audit}


def _open(db):
    """sqlite has one write lock and no row locks: open the transaction IMMEDIATE, so a second writer waits for the lock
    before step 1 reads, not at its first insert with what it read gone stale. A transaction already open has the lock
    or will take it on its own. PostgreSQL locks rows in step 1."""
    if db.get_bind().dialect.name != "sqlite":
        return
    connection = db.connection()
    if not connection.connection.dbapi_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def _claim(db, table, cfg, now, items):
    """Step 1 - lock the entities' current lines in row_id order. A new key is put in its current line first (keys
    sorted, ON CONFLICT DO NOTHING) and read back under the same lock, so two writers of one new key end on one row_id
    and no line is orphaned. Returns ({item index: row_id}, {row_id: its current line before}, {row_id: its business
    key}). An item naming no current line is left out unless it writes - a write to a gone row_id makes it again, as
    today's `_get_or_create_row` does."""
    targets, old = {}, {}
    named = sorted({it["row_id"] for it in items if it.get("row_id")})
    for page in _pages(named, 1):
        for row in db.execute(select(now).where(now.c.row_id.in_(page)).order_by(now.c.row_id)
                              .with_for_update()).mappings():
            old[row["row_id"]] = dict(row)
    keys_of = cfg.get("composite_key_source") or []
    wanted, by_key, bare = {}, {}, []              # business key -> minted row_id · item -> key · rows of no key
    for i, it in enumerate(items):
        if it.get("row_id") in old:
            targets[i] = it["row_id"]
            continue
        if it["line_kind"] != WRITE:
            continue                               # nothing to take back from a row that is not there
        bk = it.get("business_key_val")
        if bk is None and it.get("key") and keys_of:
            bk = crud.compose_business_key(table, [it["key"].get(c) for c in keys_of], keys_of)
        if crud.is_blank_value(bk):
            targets[i] = crud._engine_minted_row_id(it.get("row_id"), table)
            bare.append(targets[i])
        else:
            wanted.setdefault(bk, crud._engine_minted_row_id(it.get("row_id"), table))
            by_key[i] = bk
    keys = {row_id: row.get("business_key_val") for row_id, row in old.items()}
    if wanted:
        if db.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as upsert
        else:
            from sqlalchemy.dialects.sqlite import insert as upsert
        ordered = sorted(wanted)
        for page in _pages(ordered, 2):
            db.execute(upsert(now).on_conflict_do_nothing(index_elements=["business_key_val"]),
                       [{"row_id": wanted[bk], "business_key_val": bk} for bk in page])
        holder = {}
        for page in _pages(ordered, 1):
            for row in db.execute(select(now).where(now.c.business_key_val.in_(page)).order_by(now.c.row_id)
                                  .with_for_update()).mappings():
                holder[row["business_key_val"]] = dict(row)
        for bk, row in holder.items():
            keys[row["row_id"]] = bk
            if row["row_id"] != wanted[bk]:
                old.setdefault(row["row_id"], row)  # the key was someone's already: an edit of that row
        for i, bk in by_key.items():
            targets[i] = holder[bk]["row_id"]
    for page in _pages(bare, 1):
        db.execute(insert(now), [{"row_id": row_id} for row_id in page])
    return targets, old, keys


def _leave_out(db, table, cfg, ln, bits, chunks, items, targets):
    """Step 2 - the items that change something. A write is left out when every column it writes equals its source's
    head line there - the cast stored forms compared IS NOT DISTINCT FROM in SQL (blank = NULL), no generator. A
    withdraw keeps the columns its source still speaks in and is left out when none - never by comparing values (a NULL
    head withdrawn by NULL = NULL would speak on). Deletes and marks are kept. Returns (kept indexes, how many left)."""
    types = cfg.get("column_types") or {}
    writes = [i for i in sorted(targets) if items[i]["line_kind"] == WRITE]
    for i in writes:                               # a line stores its value as text - one seat writes it (C 11-10)
        items[i]["values"] = {c: crud.line_text(crud.cast_value_by_type(v, types.get(c, "string"), c, table),
                                                types.get(c, "string"))
                              for c, v in (items[i].get("values") or {}).items()}
    same = set()
    columns = sorted({c for i in writes for c in items[i]["values"]})
    if writes and columns:
        # the incoming rows as a UNION ALL of SELECTs - sqlite takes no VALUES with column names
        named = [("i", Integer), ("row_id", String), ("src", String)] + [("w%d" % k, BigInteger) for k in range(chunks)]             + [(c, ln.c[c].type) for c in columns]
        for page in _pages(writes, len(named), UNION_MOST):
            rows = [(i, targets[i], items[i].get("source_name"), *_masks(bits, chunks, items[i]["values"]),
                     *[items[i]["values"].get(c) for c in columns]) for i in page]
            v = union_all(*[select(*[literal(value, kind).label(name) for value, (name, kind) in zip(row, named)])
                            for row in rows]).subquery("incoming")
            conds = []
            for c in columns:
                k, m = _bit(bits, c)
                h = ln.alias("h")
                spoken = exists().where(h.c.row_id == v.c.row_id, h.c.source_name == v.c.src,
                                        h.c.line_kind == WRITE, h.c["head_%d" % k].op("&")(m) != 0,
                                        h.c["withdrawn_%d" % k].op("&")(m) == 0,
                                        h.c[c].is_not_distinct_from(cast(v.c[c], ln.c[c].type)))
                conds.append(or_(v.c["w%d" % k].op("&")(m) == 0, spoken))
            same |= {row[0] for row in db.execute(select(v.c.i).where(and_(*conds)))}
    spoken = _spoken(db, ln, bits, chunks, {(targets[i], items[i].get("source_name")) for i in targets
                                            if items[i]["line_kind"] == WITHDRAW})
    kept, left_out = set(), 0
    for i in sorted(targets):
        it = items[i]
        if it["line_kind"] == WITHDRAW:
            it["columns"] = [c for c in it.get("columns") or () if c in spoken.get((targets[i], it.get("source_name")), ())]
        if (it["line_kind"] == WRITE and i in same) or (it["line_kind"] == WITHDRAW and not it["columns"]):
            left_out += 1
        else:
            kept.add(i)
    return kept, left_out


def _spoken(db, ln, bits, chunks, pairs) -> dict:
    """{(row_id, source): the columns that source heads on the row and has not withdrawn} - what it can take back.
    One read of the pairs' rows' head lines."""
    heads = [ln.c["head_%d" % k] for k in range(chunks)]
    out = {}
    for page in _pages(sorted({row_id for row_id, _s in pairs}), 1):
        for row in db.execute(select(ln.c.row_id, ln.c.source_name, *heads,
                                     *[ln.c["withdrawn_%d" % k] for k in range(chunks)])
                              .where(ln.c.row_id.in_(page), ln.c.line_kind == WRITE, or_(*[h != 0 for h in heads]))):
            if (row[0], row[1]) not in pairs:
                continue
            for c in bits:
                k, m = _bit(bits, c)
                if row[2 + k] & m and not row[2 + chunks + k] & m:
                    out.setdefault((row[0], row[1]), set()).add(c)
    return out


def _lines(db, ln, bits, chunks, items, kept, targets, keys, at, transaction_id):
    """Step 3 - one line a kept item, in item order. A write's head bits start as its written bits, a withdraw's too
    (with its withdrawn bits); a deleted or mark line's three are 0. Returns [(line_id, row_id, sources, masks)] of
    the write and withdraw lines in line_id order - the sources being its own and its folds - for step 4."""
    order = sorted(kept)
    rows = []
    for i in order:
        it = items[i]
        said = it.get("values") if it["line_kind"] == WRITE else it.get("columns") if it["line_kind"] == WITHDRAW else ()
        masks = _masks(bits, chunks, said or ())
        row = {"line_kind": it["line_kind"], "source_name": it.get("source_name"), "at": at,
               "written_by": it.get("written_by"), "batch": transaction_id, "input_row": it.get("input_row"),
               "owner_rule": it.get("owner_rule"), "owner_key": it.get("owner_key"), "confirmed": it.get("confirmed"),
               "row_id": targets[i], "business_key_val": keys.get(targets[i])}
        for k in range(chunks):
            row["written_%d" % k] = masks[k]
            row["head_%d" % k] = masks[k]
            row["withdrawn_%d" % k] = masks[k] if it["line_kind"] == WITHDRAW else 0
        for c in _data(bits):
            row[c] = (it.get("values") or {}).get(c) if it["line_kind"] == WRITE else None
        rows.append(row)
    if not rows:
        return []
    ids = db.execute(insert(ln).returning(ln.c.line_id, sort_by_parameter_order=True), rows).scalars().all()
    out = []
    for line_id, i, row in zip(ids, order, rows):
        if row["line_kind"] in (WRITE, WITHDRAW):
            out.append((line_id, row["row_id"], [row["source_name"]] + list(items[i].get("folds") or ()),
                        [row["written_%d" % k] for k in range(chunks)]))
    return sorted(out)


def _heads(db, ln, chunks, written):
    """Step 4 - each new write or withdraw line takes its columns' head bits off the earlier lines of its sources on
    the row (one UPDATE, a parameter set a line and source). Lines of one batch go in line_id order, so the later of
    two on one cell keeps the head."""
    params = [{"r": row_id, "s": source, "id": line_id, **{"n%d" % k: ~masks[k] for k in range(chunks)},
               **{"m%d" % k: masks[k] for k in range(chunks)}}
              for line_id, row_id, sources, masks in written for source in sources]
    if not params:
        return
    statement = update(ln).where(
        ln.c.row_id == bindparam("r"), ln.c.source_name == bindparam("s"), ln.c.line_id < bindparam("id"),
        or_(*[ln.c["head_%d" % k].op("&")(bindparam("m%d" % k)) != 0 for k in range(chunks)])
    ).values({"head_%d" % k: ln.c["head_%d" % k].op("&")(bindparam("n%d" % k)) for k in range(chunks)})
    db.execute(statement, params)


def _merge_now(db, table, cfg, shape, row_ids, at):
    """Step 5 - the touched current lines merged again from their head lines and pins, a column at a time by
    `lines.winners_sql` (the one query `lines.merge` reads too), and written with won_by. Returns {row_id: {column:
    value}} as written."""
    now, data = shape["now"], _data(shape["bits"])
    types = cfg.get("column_types") or {}
    if not row_ids:
        return {}
    merged = {row_id: {c: None for c in data} for row_id in row_ids}
    won_by = {row_id: {} for row_id in row_ids}
    for c in data:
        query = lines.winners_sql(table, cfg, c, "row_ids")
        for page in _pages(row_ids, 1):
            for row_id, value, line_id in db.execute(query, {"row_ids": page}):
                merged[row_id][c], won_by[row_id][c] = crud.line_value(value, types.get(c, "string")), line_id
    db.execute(update(now).where(now.c.row_id == bindparam("r")).values(
        {**{c: bindparam("v_" + c) for c in data}, "won_by": bindparam("won"), "updated_at": at}),
        [{"r": row_id, "won": won_by[row_id], **{"v_" + c: merged[row_id][c] for c in data}} for row_id in row_ids])
    return merged


def _audit(db, table, items, kept, targets, work, transaction_id, at):
    """Step 6 - one audit row a (work kind, who) of the batch: transaction, table, who, work kind, at. No values, no
    count - the panel counts the transaction's lines. -> the rows for the caller's after-commit add_changed, each with
    the distinct row_ids its (work kind, who) wrote in this write."""
    said = {}
    for i in kept:
        said.setdefault((work[i], items[i].get("written_by")), set()).add(targets[i])
    order = sorted(said, key=lambda p: (p[0], p[1] or ""))
    if order:
        db.execute(insert(lines.AuditBatch.__table__), [{"transaction_id": transaction_id, "table_name": table,
                                                         "written_by": who, "work_kind": work_kind, "at": at}
                                                        for work_kind, who in order])
    return [{"transaction_id": transaction_id, "table_name": table, "changed_rows": len(said[(work_kind, who)]),
             "kind": work_kind, "written_by": who} for work_kind, who in order]
