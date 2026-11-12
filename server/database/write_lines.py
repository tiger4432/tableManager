"""Every write of a declared table - the cell-source overhaul's one write (docs/design/CELL_SOURCE_OVERHAUL.md «쓰기»).

`write_lines` works inside the caller's transaction, a few statements a batch and none a row: claim the entities'
current lines (1), leave out what changes nothing (2), one line a remaining item (3), take the head bits off the lines
the new ones replace (4), merge the touched current lines again (5), rebuild the key of a row whose key part moved and
merge it into the row already holding that key (5½), one audit row a work kind (6). The table shape,
the bit map, the rank and the winners query are `database.lines`' - nothing here spells «__now» or «__lines».

An item is a dict:
    row_id        the entity, or None for one named by its key
    key           {key column: value} - composed by `crud.compose_business_key`; a given `business_key_val` wins
    line_kind     "write" (default) · "withdraw" · "deleted" · "created" (a row made with no value - the grid's
                  «add row»; the pair of «deleted», C 11-11) · "mark"
    values        {column: value} for a write - cast here by `crud.cast_value_by_type`
    cast          {column: value already cast} - the funnel's own cast, not cast again (lead 11-12 c)
    columns       [column] for a withdraw
    source_name · written_by · input_row · owner_rule · owner_key · confirmed
    acted_by      who did this write when it is not the value's author (written_by) - a retroactive op re-spelling a
                  person's line keeps the person as its author and names itself here; the audit row says it (lead
                  11-11: a line's written_by is its value's author, an audit row's the write's actor)
    at            a line's «when» kept from the line it re-spells (design «쓰기» 53: a fold writes a new line whose
                  rank does not move); else the write's instant - the batch keeps when it was done
    respelled     true: the line re-spells what is stored (the notation backfill) - no new hand: it moves no mark or
                  pin, and a key merge reads it as neither named nor a person's
    rekey         true: step 5½ rebuilds the row's key though no key part moved (a key in an old spelling; a mark
                  item with no columns carries it)
    A mark naming no column and asking no re-key merges its row again and writes no line (`_merges_again` -
    lead 11-11: a formula saved, R3, the notation backfill's re-merge, a formula column offered alone).
    blank         on such a mark: columns that go blank where no line speaks (a removed formula's - owner 11-11, no
                  value of no source; t keeps its value elsewhere); a name t does not hold is ignored
    old_key       the key the item was sent with when it is not its assembled key (a raw spelling, a rename by
                  the old key): asked when the assembled key is nobody's - ruling 191, S-90 - and the row it
                  names is re-keyed
    work          the word its audit row says for it, where the caller names one («formula» - a formula's
                  write, owner 11-12 ㄴ); a word only, nothing runs by it
    folds         {source name: columns} whose head bits the write's line also takes off there - set by step 2 (a file's
                  layers of its share that say the same value, `crud.file_layer_fold`)
    of            the item step 2 split this one off (a column written under its share's older layer - owner 11-08)
    version_judged  true when the caller judged the row's version already (a map judged whole)
`kind` is the writing seat's word (funnel · chain · formula · withdraw · delete · create · notation · merge · mark ·
seed); the
work kind of each item (edit · new · delete · withdraw · merge · mark) is decided in step 1.
"""
from __future__ import annotations

import logging

from sqlalchemy import bindparam, delete, insert, or_, select, text, update

from database import crud, lines

logger = logging.getLogger(__name__)

WRITE, WITHDRAW, DELETED, CREATED, MARK = "write", "withdraw", "deleted", "created", "mark"
LINE_KINDS = (WRITE, WITHDRAW, DELETED, CREATED, MARK)
#: bound parameters one statement carries at most - under sqlite's 32,766
PARAMS_MOST = 30000
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


def _sets_at_once(db) -> bool:
    """A step's rows in one set statement: PostgreSQL (psycopg2 sends an UPDATE's parameter sets one round trip each,
    lead 11-12 ㄴ); sqlite keeps the parameter sets - no round trips there, and no bit_or."""
    return db.get_bind().dialect.name == "postgresql"


def _owner(item) -> tuple:
    """(owner_rule, owner_key) a line of `item` carries: as the item names them, else as its source's name says them
    (`crud.layer_owner` - a layer `owned_layer_name` built; (None, None) for any other) - so the rank's «declared rule
    first» reads every chain line the funnel writes (lead 11-12 ㄱ; 83de1715e)."""
    if item.get("owner_rule") is not None:
        return item.get("owner_rule"), item.get("owner_key")
    return crud.layer_owner(item.get("source_name")) or (None, None)


def _cast(table, types, item, column, value):
    """`value` cast as every write casts it (`crud.cast_value_by_type`) - the item's own cast where it carries one
    (the funnel's «cast», lead 11-12 c: a value is cast once)."""
    done = item.get("cast")
    if done is not None and column in done:
        return done[column]
    return crud.cast_value_by_type(value, types.get(column, "string"), column, table)


def _pages(seq, width: int, most=None):
    seq = list(seq)
    size = max(1, min(PARAMS_MOST // max(1, width), most or PARAMS_MOST))
    for at in range(0, len(seq), size):
        yield seq[at:at + size]


def key_owners(db, now, keys, *, but=(), lock=False, read=None) -> dict:
    """{key: the row that holds it} - THE answer to «which row is key K's»: of the rows storing K, but those in `but`,
    the one with the smallest row_id. A key held twice is a table without its unique index; the claim, step 5½ and
    the notation backfill ask here, so they answer alike (lead 11-11 - the old funnel's .first() had no order to
    keep). `read`: the columns read (row_id and the key are always among them); `lock`: FOR UPDATE on every row
    read. -> {key: {column: value}}."""
    cols = [now.c.row_id, now.c.business_key_val] + [c for c in (read or ()) if c.name not in
                                                      ("row_id", "business_key_val")]
    but, out = set(but), {}
    for page in _pages(sorted(set(keys)), 1):
        statement = select(*cols).where(now.c.business_key_val.in_(page)).order_by(now.c.row_id)
        for row in db.execute(statement.with_for_update() if lock else statement).mappings():
            if row["row_id"] not in but:
                out.setdefault(row["business_key_val"], dict(row))
    return out


def write_lines(db, table: str, items, *, kind: str, transaction_id):
    """Write `items` into `table` as lines - see the module. Returns
    {"changed": {row_id: {"old": {col: value}|None, "new": {col: value}|None, "work": work kind}},
     "lines": lines written, "left_out": items that changed nothing,
     "audit": [{"transaction_id", "table_name", "changed_rows", "kind", "written_by"}] one an audit row - `kind` its work
     kind, `changed_rows` the distinct row_ids it wrote lines for in this write,
     "gated": {reason: writes the version gate refused}, "at": the write's instant (its lines' `at`),
     "items": [{"row_id", "line_id", "work", "columns"}] one an item, in the items' order - the row it was claimed as (None: a
     withdraw, delete or mark of no current line), the line it wrote (None: none), its work kind or "left_out"
     (changed nothing) or "gated", the
     columns its line says (a write's after step 2),
     "merged": {row_id: the key holder step 5½ merged it into}} - `old` is the current line step 1 locked, `new` the
    one step 5 wrote (None: deleted or merged away), what the broadcast and the outbox read (one author). `items` is
    what a caller resolves its own items by - a map's rows claimed, a dropped cell's row; an item whose row was merged
    away names its holder."""
    _open(db)
    cfg = crud.TABLE_CONFIG.get(table) or {}       # a table the config does not declare keeps no lines
    keeps, shape = _table_shape(db, table, cfg)
    now, ln, bits, chunks = shape["table"], shape["lines"], shape["bits"], shape["chunks"]
    data = _data(bits) if keeps else [c.name for c in now.columns
                                      if c.name not in {name for name, _type in lines.FRAMEWORK}]
    items = [dict(it, line_kind=it.get("line_kind") or WRITE) for it in items]
    n = len(items)                                 # step 2 may split an item (`of`); the answer is per given item
    for it in items:
        if it["line_kind"] not in LINE_KINDS:
            raise ValueError("write_lines: line kind %r is not one of %s" % (it["line_kind"], ", ".join(LINE_KINDS)))
        unknown = [c for c in list(it.get("values") or ()) + list(it.get("columns") or ()) if c not in data]
        if unknown:
            raise ValueError("write_lines: %r is not a column of %r" % (unknown[0], table))
        if it["line_kind"] in (WRITE, WITHDRAW) and it.get("source_name") is None:   # a head with no source (C 11-11)
            raise ValueError("write_lines: a %s line of %r names no source" % (it["line_kind"], table))
    at = _instant(db, table)
    targets, old, keys = _claim(db, table, cfg, now, items)
    claimed = dict(targets)
    gated, before = _version_gate(table, cfg, items, targets, old)
    held = shape["kinds"]                          # a line's text by what t holds, not the declaration (C)
    plain = _plain(table, cfg, items, targets, before, held, keeps)
    asked = {i: set(it.get("values") or ()) for i, it in enumerate(items) if it["line_kind"] == WRITE}
    given = {i: dict(it.get("values") or {}) for i, it in enumerate(items) if it["line_kind"] == WRITE}  # before 2
    # a table with no lines: a delete still takes its row out and a create still makes it, with no line (lead 11-11 2);
    # a mark still merges its row again (a re-key it asks for)
    kept, left_out = (_leave_out(db, table, cfg, ln, bits, chunks, items, targets, held, before, at) if keeps
                      else ({i for i in targets if items[i]["line_kind"] in (DELETED, CREATED, MARK)},
                            sum(1 for i in targets if i not in plain and items[i]["line_kind"] not in (DELETED, CREATED, MARK))))
    again = {i for i in kept if _merges_again(items[i])}   # its row merged again, no line
    kept -= again
    split = {items[k]["of"] for k in kept if "of" in items[k]} - kept   # its columns all went to items split off it
    moved = [i for i in sorted(plain) if i not in kept and i not in split]  # changed only a column of no history
    left_out -= len(moved)
    work = {i: items[i].get("work") or ("merge" if kind == "merge" else {DELETED: "delete", WITHDRAW: "withdraw",
                                                                         MARK: "mark"}.get(
        items[i]["line_kind"], "edit" if targets[i] in old else "new")) for i in list(kept) + moved + sorted(again)}
    unpinned, line_ids = set(), {}
    if keeps:
        lines.note_sources(db, {items[i].get("source_name") for i in kept})   # the rank reads a line's source's row
        written, line_ids = _lines(db, ln, bits, chunks, items, kept, targets, keys, at, transaction_id)
        _heads(db, ln, chunks, written)
        unpinned = _marks(db, table, shape, items, kept, targets, asked)
    for i in sorted(targets):                      # a pin taken off moves the row's merge whatever the line did
        if targets[i] in {r for r, _c in unpinned} and i not in work and i not in split:
            work[i] = "edit"
            moved.append(i)
            left_out -= 1
    gone = sorted({targets[i] for i in kept if items[i]["line_kind"] == DELETED})
    for page in _pages(gone, 1):
        db.execute(delete(now).where(now.c.row_id.in_(page)))
    rows_plain = {}
    for i in sorted(plain):
        rows_plain.setdefault(targets[i], {}).update(plain[i])
    blank = {}
    for i in sorted(again):
        blank.setdefault(targets[i], set()).update(items[i].get("blank") or ())
    # the columns this write touched - its kept lines' and the cells a pin came off (lead 11-12 b); a mark merges all
    touched = None if again or any(items[i]["line_kind"] == MARK for i in kept) else (
        {c for i in kept for c in list(items[i].get("values") or ()) + list(items[i].get("columns") or ())}
        | {c for _r, c in unpinned})
    new = _merge_now(db, table, cfg, shape, sorted({targets[i] for i in list(kept) + moved + sorted(again)} - set(gone)),
                     at, old, rows_plain, keeps, blank, touched)
    merged = _rekey(db, table, cfg, shape, keeps, items, targets, given, new, old, keys, at, transaction_id)
    changed = {}
    for i in sorted(list(kept) + moved):
        row_id = targets[i]
        changed.setdefault(row_id, {"old": old.get(row_id), "new": new.get(row_id), "work": work[i]})
    types = cfg.get("column_types") or {}
    for i in sorted(again):                        # a row merged again changed when a shown value moved
        row_id = targets[i]
        if row_id in new and _moved(old.get(row_id) or {}, new[row_id], shape["columns"], types):
            changed.setdefault(row_id, {"old": old.get(row_id), "new": new[row_id], "work": work[i]})
    said_rows = {}
    for i in sorted(again):                        # its audit row only when a shown value moved (lead 11-11)
        if targets[i] in changed:
            said_rows.setdefault((work[i], items[i].get("acted_by") or items[i].get("written_by")), set()).add(targets[i])
    for i in kept:
        said_rows.setdefault((work[i], items[i].get("acted_by") or items[i].get("written_by")), set()).add(targets[i])
    for shell, (holder, holder_old, holder_new, who) in merged.items():
        changed[shell] = {"old": old.get(shell), "new": None, "work": "merge"}
        changed.setdefault(holder, {"old": holder_old, "work": "merge"})["new"] = holder_new
        said_rows.setdefault(("merge", who), set()).add(holder)
    audit = _audit(db, table, said_rows, transaction_id, at) if keeps else []
    wrote = {}                                     # a row's columns, every item on it (two items, one row)
    for i in list(kept) + moved:
        if items[i]["line_kind"] == WRITE:
            wrote.setdefault(targets[i], set()).update(set(items[i].get("values") or ()) | set(plain.get(i) or ()))
    _stage(db, table, cfg, shape["columns"], changed, keys, wrote)
    landed = {shell: m[0] for shell, m in merged.items()}
    kin = {}                                       # a given item and the items step 2 split off it
    for j, it in enumerate(items):
        kin.setdefault(it.get("of", j), []).append(j)
    said = []
    for i, it in enumerate(items[:n]):
        did = next((j for j in kin[i] if j in work), None)
        said.append({"row_id": landed.get(claimed.get(i), claimed.get(i)),
                     "line_id": line_ids.get(did) if did is not None else None,
                     "work": work[did] if did is not None else "gated" if i in claimed and i not in targets
                     else "left_out" if i in targets else None,
                     "columns": sorted(set().union(*[set(items[j].get("values") or ()) for j in kin[i]])
                                       | set(plain.get(i) or ())) if it["line_kind"] == WRITE
                     else list(it.get("columns") or ())})
    return {"changed": changed, "lines": len(kept) if keeps else 0, "left_out": left_out, "audit": audit, "gated": gated,
            "items": said, "at": at, "merged": landed}


def merge_rows(db, table: str, pairs, *, source_name, written_by, transaction_id) -> dict:
    """Each (row_id, holder row_id) - a row whose key the holder already holds - merged into the holder by step 5½'s
    merge (`_merge_into`), for a caller that writes no value (the notation backfill, rebuild_blank_business_keys
    --apply): no cell is a person's this time. Its events are staged and its «merge» audit row written; the caller
    commits. -> {"changed", "merged": {row_id: holder}, "audit", "at"} as write_lines answers."""
    _open(db)
    cfg = crud.TABLE_CONFIG.get(table) or {}
    keeps, shape = _table_shape(db, table, cfg)
    at = _instant(db, table)
    changed, merged, holders = {}, {}, set()
    for shell, holder in pairs:
        shell_old, holder_old, holder_new = _merge_into(db, table, cfg, shape, keeps, shell, holder, explicit={},
                                                        human=set(), source_name=source_name, written_by=written_by,
                                                        at=at, transaction_id=transaction_id)
        changed[shell] = {"old": shell_old, "new": None, "work": "merge"}
        changed.setdefault(holder, {"old": holder_old, "work": "merge"})["new"] = holder_new
        merged[shell] = holder
        holders.add(holder)
    audit = _audit(db, table, {("merge", written_by): holders}, transaction_id, at) if keeps and holders else []
    _stage(db, table, cfg, shape["columns"], changed, {}, {})
    return {"changed": changed, "merged": merged, "audit": audit, "at": at}


def _table_shape(db, table, cfg):
    """(t keeps lines, its shape) - read once a write: every seat below takes it, the merge too (`lines.merge` s=;
    lead 11-11). `kinds`: t's columns as stored - the type a line's text takes. A table with no lines (shipped, or one
    ensure refused) has t only: every column of no history (lead 11-11 2)."""
    if lines.has_lines(db, table):
        return True, lines.shape(db, table, cfg)
    now = lines.current_table(db, table, cfg)
    return False, {"table": now, "columns": [c.name for c in now.columns], "lines": None, "bits": None, "chunks": None,
                   "kinds": lines.value_types(db, table)}


def _instant(db, table):
    at = crud.batch_write_instant(db)
    if at is None:                                 # a line's at is its history - never NULL (C 11-10)
        raise RuntimeError("write_lines: the database gave no time for %r's lines" % table)
    return at


def _open(db):
    """sqlite has one write lock and no row locks: open the transaction IMMEDIATE, so a second writer waits for the lock
    before step 1 reads, not at its first insert with what it read gone stale. A transaction already open has the lock
    or will take it on its own. PostgreSQL locks rows in step 1."""
    if db.get_bind().dialect.name != "sqlite":
        return
    connection = db.connection()
    if not connection.connection.dbapi_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def _plain(table, cfg, items, targets, before, held, keeps) -> dict:
    """A write's columns of no history (`crud.keeps_history`, `no_history_columns` - state cells written every few
    seconds; lead 11-11 ㄴ) leave no line and no audit: their value goes to t as it is - the «a column of no line is t's
    value» rule's case, no new mechanism. Taken out of the item's values here, after the claim and the version gate
    saw them whole. -> {item index: {column: value as t holds it}} of the claimed items whose value moves."""
    types = cfg.get("column_types") or {}
    out = {}
    for i, it in enumerate(items):
        if it["line_kind"] != WRITE or i not in targets:
            continue
        free = {c: v for c, v in (it.get("values") or {}).items() if not keeps or not crud.keeps_history(table, c)}
        if not free:
            continue
        it["values"] = {c: v for c, v in it["values"].items() if c not in free}
        was = before.get(i)                        # the row this item meets (`_version_gate`), None: new
        said = {c: crud.line_value(crud.line_text(_cast(table, types, it, c, v), held.get(c, "string")),
                                   held.get(c, "string"))
                for c, v in free.items()}
        said = {c: v for c, v in said.items() if was is None or was.get(c) != v}
        if said:
            out[i] = said
    return out


def _claim(db, table, cfg, now, items):
    """Step 1 - lock the entities' current lines in row_id order. A new key is put in its current line first (keys
    sorted, ON CONFLICT DO NOTHING) and read back under the same lock, so two writers of one new key end on one row_id
    and no line is orphaned. Returns ({item index: row_id}, {row_id: its current line before}, {row_id: its business
    key}). An item naming no current line is left out unless it writes a value - a write to a gone row_id makes it
    again, as the old write door did."""
    targets, old = {}, {}
    named = sorted({it["row_id"] for it in items if it.get("row_id")})
    for page in _pages(named, 1):
        for row in db.execute(select(now).where(now.c.row_id.in_(page)).order_by(now.c.row_id)
                              .with_for_update()).mappings():
            old[row["row_id"]] = dict(row)
    keys_of = cfg.get("composite_key_source") or []
    wanted, by_key, bare, looked = {}, {}, [], {}  # key -> minted row_id · item -> key · rows of no key · found only
    for i, it in enumerate(items):
        if it.get("row_id") in old:
            if it["line_kind"] != CREATED:         # a row already there is not made again
                targets[i] = it["row_id"]
            continue
        if it["line_kind"] not in (WRITE, CREATED):
            continue                               # nothing to take back from a row that is not there
        bk = it.get("business_key_val")
        if bk is None and it.get("key") and keys_of:
            bk = crud.compose_business_key(table, [it["key"].get(c) for c in keys_of], keys_of)
        if it["line_kind"] == CREATED and crud.is_blank_value(bk):   # made with no value - its row_id or a minted one
            targets[i] = crud._engine_minted_row_id(it.get("row_id"), table)
            bare.append(targets[i])
            continue
        if it["line_kind"] == WRITE and not it.get("values"):
            # a write of nothing makes no row (the funnel's phantom-row guard); naming a row's key it still finds it
            if not crud.is_blank_value(bk):
                looked[i] = bk
            continue
        if crud.is_blank_value(bk):
            targets[i] = crud._engine_minted_row_id(it.get("row_id"), table)
            bare.append(targets[i])
        else:
            wanted.setdefault(bk, crud._engine_minted_row_id(it.get("row_id"), table))
            by_key[i] = bk
    _by_old_key(db, now, items, targets, old, wanted, by_key)
    keys = {row_id: row.get("business_key_val") for row_id, row in old.items()}
    if wanted:
        # the keys that have rows read first, so an unchanged re-push writes nothing (lead 11-12); only the rest are
        # put. With the key's unique index: a plain read, the rest ON CONFLICT DO NOTHING - a writer of the same new
        # key meanwhile still ends on one row (11-11 ㄹ). Without it (lines.key_index_next says why - the rules list
        # shows it): read under lock, the rest inserted, with its race window - two writers of one new key in the same
        # instant can make two rows (D3, as before; lead 11-11 ㄴ - collection never stops)
        standing = lines.key_index_standing(db.connection(), table)
        held = set()
        for page in _pages(sorted(wanted), 1):
            read = select(now.c.business_key_val).where(now.c.business_key_val.in_(page))
            held.update(db.execute(read if standing else read.with_for_update()).scalars())
        put = insert(now)
        if standing:
            if db.get_bind().dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as upsert
            else:
                from sqlalchemy.dialects.sqlite import insert as upsert
            put = upsert(now).on_conflict_do_nothing(index_elements=["business_key_val"])
        for page in _pages(sorted(set(wanted) - held), 2):
            db.execute(put.values([{"row_id": wanted[bk], "business_key_val": bk} for bk in page]))   # one statement a page
    if wanted or looked:
        holder = key_owners(db, now, set(wanted) | set(looked.values()), lock=True, read=list(now.c))
        for bk, row in holder.items():
            keys[row["row_id"]] = bk
            if row["row_id"] != wanted.get(bk):
                old.setdefault(row["row_id"], row)  # the key was someone's already: an edit of that row
        for i, bk in by_key.items():
            targets[i] = holder[bk]["row_id"]
            if items[i]["line_kind"] == CREATED and holder[bk]["row_id"] != wanted.get(bk):
                items[i]["line_kind"] = WRITE      # its key's row was there: named, not made again - a write of nothing
        for i, bk in looked.items():
            if bk in holder:
                targets[i] = holder[bk]["row_id"]
    for page in _pages(bare, 1):
        db.execute(insert(now), [{"row_id": row_id} for row_id in page])
    return targets, old, keys


def _by_old_key(db, now, items, targets, old, wanted, by_key) -> None:
    """Ruling 191 (S-90, lead 3eb161a9c ②): an item's assembled key first; when that is nobody's, the key it was
    sent with (`old_key`) - a row stored under a raw spelling, a rename naming the row by its old key. Both read
    under the claim's lock before a new key is put; the row found is the item's target, re-keyed in step 5½ (a key
    another row took meanwhile merges it there). The batch's other items of a key an old key gave a row go to that
    row too - the entity keeps its row_id whichever spelling came first (QA 11-11). Every key the claim asks is
    read in this one sorted, locked read, so the claim takes its rows in one order. `wanted` and `by_key` lose what
    it took."""
    asks = {i: items[i]["old_key"] for i in by_key if not crud.is_blank_value(items[i].get("old_key"))
            and items[i]["old_key"] != by_key[i]}
    if not asks:
        return
    held = key_owners(db, now, set(asks.values()) | set(by_key.values()), lock=True, read=list(now.c))
    took = {}                                      # assembled key -> the row an old key gave it
    for i, old_key in sorted(asks.items()):
        if by_key[i] in held or old_key not in held:
            continue
        row = held[old_key]
        targets[i] = row["row_id"]
        old.setdefault(row["row_id"], row)
        items[i]["rekey"] = True
        took.setdefault(by_key[i], row["row_id"])
        del by_key[i]
    for j, bk in list(by_key.items()):
        if bk in took:
            targets[j] = took[bk]
            if items[j]["line_kind"] == CREATED:
                items[j]["line_kind"] = WRITE  # the row is there: named, not made again
            del by_key[j]
    for bk in set(wanted) - set(by_key.values()):
        del wanted[bk]


def _version_gate(table, cfg, items, targets, old) -> tuple:
    """Step 1's other half - each item, in its order, meets its row as the batch's earlier items left it: the
    current line step 1 locked, with the values of the writes taken before it (None: a row the batch makes). THE
    seat of «was this row there before this item» - step 2's asking and `_plain` read `before`; the work kind asks
    «was it there before the batch» (`old` - a row the batch made is «new» in its audit however many items wrote it)
    (the old write's row_cache and is_new, lead 11-11: [v2, v1] on one key both went through and v1 showed). A write
    to a version-gated table (`version_column`) is judged on that row by `crud.version_gate_verdict`, taken or
    refused whole; a refused one leaves `targets` and the row as it was.
    -> ({reason: items refused}, {item index: the row it meets, None: new})."""
    from types import SimpleNamespace

    gate = bool(cfg.get("version_column"))
    gated, rows, before = {}, {}, {}
    for i in sorted(targets):
        it, row_id = items[i], targets[i]
        was = rows[row_id] if row_id in rows else old.get(row_id)
        if gate and it["line_kind"] == WRITE and not it.get("version_judged"):
            applied, reason = crud.version_gate_verdict(
                table, cfg, SimpleNamespace(**(was or {})), was is None,
                SimpleNamespace(source_name=it.get("source_name"), updates=it.get("values") or {}))
            if reason is not None:
                gated[reason] = gated.get(reason, 0) + 1
            if not applied:
                del targets[i]
                continue
        before[i] = was
        rows[row_id] = dict(was or {}, **(it.get("values") or {})) if it["line_kind"] == WRITE else (was or {})
    return gated, before


def _leave_out(db, table, cfg, ln, bits, chunks, items, targets, held, before, at):
    """Step 2 - the items that change something, judged in their order on the head lines as the batch's earlier
    items left them (a batch's last word wins - lead 11-11; its lines share an instant and the later line wins, C's
    rank_terms 2c). A write's column is left out when its source's head
    there says the same text (`_head_text`), from the same hand and input row (ruling 434), or when another source
    says it already (`_others`); the write when no column is left. A withdraw keeps the columns its source still
    speaks in and is left out when none - never by comparing values (a NULL head withdrawn by NULL = NULL would speak
    on). All ask one read of the head lines (`_spoken`). Deletes and marks are kept. Returns (kept indexes, how many
    left)."""
    types = cfg.get("column_types") or {}
    writes = [i for i in sorted(targets) if items[i]["line_kind"] == WRITE]
    for i in writes:                               # a line stores its value as text - one seat writes it (C 11-10)
        items[i]["values"] = {c: crud.line_text(_cast(table, types, items[i], c, v), held.get(c, "string"))
                              for c, v in (items[i].get("values") or {}).items()}
    columns = sorted({c for i in writes for c in items[i]["values"]})
    heads = {}                                     # {row_id: {source: {column: (hand, input row, text, at, line_id)}}}
    for (row_id, source), said in _spoken(db, ln, bits, chunks, {targets[i] for i in targets if items[i]["line_kind"]
                                                                 in (WRITE, WITHDRAW)}, columns).items():
        heads.setdefault(row_id, {})[source] = said
    asking = [i for i in writes if _asks_others(items[i], before.get(i) is not None)]   # `_version_gate`'s seat
    pins = ({cell: was[2] for cell, was in _overwrites(db, table, {targets[i] for i in asking},
                                                       {c for i in asking for c in items[i]["values"]}).items()}
            if asking else {})
    kept, left_out, ranks = set(), 0, {}
    for i in sorted(targets):
        it, row_id = items[i], targets[i]
        row = heads.setdefault(row_id, {})
        own = row.setdefault(it.get("source_name"), {})
        if it["line_kind"] == WITHDRAW:
            it["columns"] = [c for c in it.get("columns") or () if c in own]
            for c in it["columns"]:
                own.pop(c)
        elif it["line_kind"] == WRITE:
            hand = (_text_or_none(it.get("written_by")), _text_or_none(it.get("input_row")))
            if it.get("source_name") == "user" and not it.get("respelled"):  # takes the pin off (`_marks`) - for the items after
                for c in it["values"]:
                    pins.pop((row_id, c), None)
            same = {c for c, value in it["values"].items() if c in own and own[c][:2] == hand
                    and _head_text(own[c][2], held.get(c, "string")) == value}
            folds, moves = (_others(table, it, row_id, row, held, pins, same, ranks) if i in asking else ({}, {}))
            when = it.get("at") or at
            for source, cs in sorted(moves.items()):   # its share's layer of the value, under its own source
                kid = dict(it, source_name=source, values={c: it["values"][c] for c in cs}, of=i,
                           folds={s: f & cs for s, f in folds.items() if f & cs})
                targets[len(items)] = row_id
                kept.add(len(items))
                items.append(kid)
                same |= cs
                rule = _owner(kid)[0]
                for c in cs:
                    row.setdefault(source, {})[c] = hand + (kid["values"][c], when, UNNUMBERED + i, rule, None)
            it["folds"] = {s: f - same for s, f in folds.items() if f - same}
            it["values"] = {c: value for c, value in it["values"].items() if c not in same}
            rule = _owner(it)[0]
            for c, value in it["values"].items():
                own[c] = hand + (value, when, UNNUMBERED + i, rule, None)
            for s, f in folds.items():             # a folded source no longer heads the column, whichever line took it
                for c in f:
                    row.get(s, {}).pop(c, None)
            if not it["values"] and moves:
                continue                           # its columns went to the items split off it
        if (it["line_kind"] == WRITE and not it["values"]) or (it["line_kind"] == WITHDRAW and not it["columns"]):
            left_out += 1
        else:
            kept.add(i)
    return kept, left_out


#: the line_id step 2 ranks a batch line by before step 3 numbers it (rank 2c): after every stored line, in the
#: batch's item order - an item split off its parent at its parent's place (`_lines`; the two say no column alike)
UNNUMBERED = 1 << 62


def _head_text(text, kind):
    """A head line's value as step 2 compares it with a write's text: a blank is absence; a text column's text as it
    stands - a person re-sending it trimmed is a change (lead 11-11 ㄴ); any other kind its line text (a number's
    «1» and «1.0», one instant's two zone spellings are one text)."""
    if crud.is_blank_value(text):
        return None
    return text if kind == "string" else crud.line_text(text, kind)


def _spoken(db, ln, bits, chunks, row_ids, columns) -> dict:
    """{(row_id, source): {column: (written_by, input_row, value text, at, line_id, owner_rule, copy_of)}} - the columns each source heads on the row
    and has not withdrawn (what a withdraw can take back, the cell's layers), each with its head line's hand, input
    row, «when» and - for `columns` - its value. One read of the rows' head lines, one statement (no literal per
    item, 11-11; compiled once a write - lines.shape builds its Table anew)."""
    heads = [ln.c["head_%d" % k] for k in range(chunks)]
    withdrawn = [ln.c["withdrawn_%d" % k] for k in range(chunks)]
    values = [ln.c[lines.value_column(c)] for c in columns]
    src = lines.LineSource.__table__
    out = {}
    for page in _pages(sorted(row_ids), 1):
        for row in db.execute(select(ln.c.row_id, ln.c.source_name, ln.c.written_by, ln.c.input_row, ln.c.at,
                                     ln.c.line_id, ln.c.owner_rule, src.c.copy_of, *heads, *withdrawn, *values)
                              .select_from(ln.outerjoin(src, src.c.source_name == ln.c.source_name))
                              .where(ln.c.row_id.in_(page), ln.c.line_kind == WRITE, or_(*[h != 0 for h in heads]))):
            said = dict(zip(columns, row[8 + 2 * chunks:]))
            for c in bits:
                k, m = _bit(bits, c)
                if row[8 + k] & m and not row[8 + chunks + k] & m:
                    out.setdefault((row[0], row[1]), {})[c] = (row[2], row[3], said.get(c), row[4], row[5], row[6],
                                                               row[7])
    return out


def _asks_others(item, there) -> bool:
    """Whether step 2 asks what another source on the cell says (`_others`) of this write: a file's or the chain's,
    on a row there before, never a re-spelling (no new statement: its own line is re-spelled where it is)."""
    source = item.get("source_name")
    return (item["line_kind"] == WRITE and there and not item.get("respelled")
            and (crud.is_file_layer(source) or crud.writer_kind(source) == "chain"))


def _others(table, item, row_id, row, held, pins, same, ranks):
    """What another source on the cell says, for a write the old seat asked it of (lead 11-11 ㄴ - its two answers, on
    the row's head lines as step 2 holds them): a file's `crud.file_layer_fold` - a repeat is left out, its share's
    other layers of the value fold into the line, a value its share holds behind another layer is written under that
    layer's source when the file has no layer of its own there (owner 11-08 «층을 새로하지 말고 순서를 바꿔»; one it
    has takes the value, as the old write's `src_obj or moved`); a chain's new layer saying what the cell shows is
    left out (owner 11-08). Never the pinned layer. Adds to `same`; `ranks` the write's rank memo (one table); ->
    ({source: {column}} folds, {source: {column}} moves)."""
    from types import SimpleNamespace

    source = item.get("source_name")
    folds, moves = {}, {}
    for c, value in item["values"].items():
        if c in same:
            continue
        kind, pin = held.get(c, "string"), pins.get((row_id, c))
        layers = [SimpleNamespace(source_name=s, value=crud.line_value(said[c][2], kind), ingested_at=said[c][3],
                                  line_id=said[c][4], owner_rule=said[c][5], copy_of=said[c][6])
                  for s, said in row.items() if c in said]
        if crud.is_file_layer(source):
            repeat, folded, moved = crud.file_layer_fold(layers, source, value, kind, table, pin, ranks)
            if repeat:
                same.add(c)
            for gone in folded:
                folds.setdefault(gone.source_name, set()).add(c)
            if moved is not None and c not in row.get(source, {}):   # its own layer takes it (the old `src_obj or moved`)
                moves.setdefault(moved.source_name, set()).add(c)
        elif not any(crud.layer_ranks_as(s.source_name) == crud.layer_ranks_as(source) for s in layers):
            shown = crud.compute_priority_value({s.source_name: {"value": s.value, "ingested_at": s.ingested_at,
                                                                 "line_id": s.line_id, "owner_rule": s.owner_rule,
                                                                 "copy_of": s.copy_of}
                                                 for s in layers}, pin, table, ranks=ranks)[0]
            if not crud.values_differ(shown, value, kind):
                same.add(c)
    return folds, moves


def _overwrites(db, table, row_ids, columns) -> dict:
    """{(row_id, column): (is_overwrite, updated_by, manual_priority_source)} - the cells' cell_overwrites rows."""
    from database import models

    ov = models.CellOverwrite.__table__
    out = {}
    for page in _pages(sorted(row_ids), 1, most=PARAMS_MOST - len(columns)):
        for r, c, flag, by, pin in db.execute(select(ov.c.row_id, ov.c.column_name, ov.c.is_overwrite, ov.c.updated_by,
                                                      ov.c.manual_priority_source).where(
                ov.c.table_name == table, ov.c.row_id.in_(page), ov.c.column_name.in_(sorted(columns)))):
            out[(r, c)] = (flag, by, pin)
    return out


def _text_or_none(value):
    """A hand or an input row as its line cell holds it (text, None absent)."""
    return None if value is None else str(value)


def _lines(db, ln, bits, chunks, items, kept, targets, keys, at, transaction_id):
    """Step 3 - one line a kept item, in item order. A write's head bits start as its written bits, a withdraw's too
    (with its withdrawn bits); a deleted or mark line's three are 0. Returns [(line_id, row_id, sources, masks)] of
    the write and withdraw lines in line_id order - [(source, masks)]: its own with the line's columns, a fold's with
    its columns - for step 4 - and {item index: line_id} of every line."""
    order = sorted(kept, key=lambda i: (items[i].get("of", i), i))   # a split item's lines at its parent's place
    rows = []
    for i in order:
        it = items[i]
        said = it.get("values") if it["line_kind"] == WRITE else it.get("columns") if it["line_kind"] == WITHDRAW else ()
        masks = _masks(bits, chunks, said or ())
        rule, key = _owner(it)
        row = {"line_kind": it["line_kind"], "source_name": it.get("source_name"), "at": it.get("at") or at,
               "written_by": it.get("written_by"), "batch": transaction_id, "input_row": it.get("input_row"),
               "owner_rule": rule, "owner_key": key, "confirmed": it.get("confirmed"),
               "row_id": targets[i], "business_key_val": keys.get(targets[i])}
        for k in range(chunks):
            row["written_%d" % k] = masks[k]
            row["head_%d" % k] = masks[k]
            row["withdrawn_%d" % k] = masks[k] if it["line_kind"] == WITHDRAW else 0
        for c in _data(bits):
            row[lines.value_column(c)] = (it.get("values") or {}).get(c) if it["line_kind"] == WRITE else None
        rows.append(row)
    if not rows:
        return [], {}
    line_ids = {}
    ids = db.execute(insert(ln).returning(ln.c.line_id, sort_by_parameter_order=True), rows).scalars().all()
    out = []
    for line_id, i, row in zip(ids, order, rows):
        line_ids[i] = line_id
        if row["line_kind"] in (WRITE, WITHDRAW):
            out.append((line_id, row["row_id"], [(row["source_name"], [row["written_%d" % k] for k in range(chunks)])]
                        + [(s, _masks(bits, chunks, cs)) for s, cs in sorted((items[i].get("folds") or {}).items())]))
    return sorted(out), line_ids


def _heads(db, ln, chunks, written):
    """Step 4 - each new write or withdraw line takes its columns' head bits off the earlier lines of its source on
    the row, and a fold's columns' off its folded sources' (one UPDATE, a parameter set a line and source). Lines of
    one batch go in line_id order, so the later of two on one cell keeps the head."""
    params = [{"r": row_id, "s": source, "id": line_id, **{"n%d" % k: ~masks[k] for k in range(chunks)},
               **{"m%d" % k: masks[k] for k in range(chunks)}}
              for line_id, row_id, sources in written for source, masks in sources]
    if not params:
        return
    if _sets_at_once(db):
        # one statement: each earlier line's masks gathered by bit_or first - UPDATE ... FROM changes a line two of
        # the batch's lines reach once, where the parameter sets took both masks off in turn (lead 11-12 ㄴ)
        heads = ["head_%d" % k for k in range(chunks)]
        arrays, casts = crud.array_params(db, [ln.c.row_id, ln.c.source_name, ln.c.line_id] + [ln.c[h] for h in heads],
                                          [[p["r"], p["s"], p["id"]] + [p["m%d" % k] for k in range(chunks)]
                                           for p in params])
        db.execute(text(
            'UPDATE "{t}" SET {sets} FROM (SELECT l.line_id, {ors} FROM "{t}" l JOIN unnest({casts}) AS v(r, s, id, {ms}) '
            'ON l.row_id = v.r AND l.source_name = v.s AND l.line_id < v.id '
            'WHERE l.row_id = ANY({rows}) AND ({any}) GROUP BY l.line_id) g '
            'WHERE "{t}".line_id = g.line_id AND ({hit})'.format(
                t=ln.name, casts=", ".join(casts), rows=casts[0], ms=", ".join("m%d" % k for k in range(chunks)),
                sets=", ".join('{h} = "{t}".{h} & ~g.m{k}'.format(h=h, t=ln.name, k=k) for k, h in enumerate(heads)),
                ors=", ".join("bit_or(v.m%d) AS m%d" % (k, k) for k in range(chunks)),
                any=" OR ".join("l.%s <> 0" % h for h in heads),
                hit=" OR ".join('("{t}".{h} & g.m{k}) <> 0'.format(t=ln.name, h=h, k=k) for k, h in enumerate(heads)))),
            arrays)
        return
    statement = update(ln).where(
        ln.c.row_id == bindparam("r"), ln.c.source_name == bindparam("s"), ln.c.line_id < bindparam("id"),
        or_(*[ln.c["head_%d" % k].op("&")(bindparam("m%d" % k)) != 0 for k in range(chunks)])
    ).values({"head_%d" % k: ln.c["head_%d" % k].op("&")(bindparam("n%d" % k)) for k in range(chunks)})
    db.execute(statement, params)


def _marks(db, table, shape, items, kept, targets, asked):
    """Step 4½ - the overwrite mark and the pin of each written cell, in cell_overwrites as today (pins are outside
    this landing - design «셀소스 · 감사 이력 · 고정이 어디로»; lead 11-11), before step 5's merge reads the pins: a
    person's write ("user") takes its cells' pin off, the cells it repeats included; a cell a person's head line or a
    pin sits on is marked (is_overwrite, by the writer), any other cell's mark goes. A mark already saying exactly that
    on a cell whose line did not move is left - the old write door's rule, cell for cell. -> the cells (row_id,
    column) a pin was taken off - their merge moves though no line did."""
    from datetime import datetime

    cells, freed = {}, set()                       # (row_id, column) -> (item, its line moved); a person's cells
    for i in sorted(targets):
        it = items[i]
        if it["line_kind"] != WRITE or it.get("respelled"):
            continue
        moved = set(it.get("values") or ()) if i in kept else set()
        for c in (asked.get(i) or set()) if it.get("source_name") == "user" else moved:
            cells[(targets[i], c)] = (it, c in moved)
            if it.get("source_name") == "user":
                freed.add((targets[i], c))         # its pin stays off whatever item of the batch comes after
    if not cells:
        return set()
    row_ids = sorted({r for r, _c in cells})
    columns = sorted({c for _r, c in cells})
    held = _overwrites(db, table, row_ids, columns)
    ln, bits, chunks = shape["lines"], shape["bits"], shape["chunks"]
    person = set()                                 # (row_id, column) a person's head line says
    heads, gone = lines.bit_columns("head", chunks), lines.bit_columns("withdrawn", chunks)
    for page in _pages(row_ids, 1):
        for row in db.execute(select(ln.c.row_id, *[ln.c[n] for n in heads + gone]).where(
                ln.c.row_id.in_(page), ln.c.source_name == "user")):
            for c in columns:
                k, m = bits[c] // BITS_A_CHUNK, 1 << (bits[c] % BITS_A_CHUNK)
                if (row[1 + k] & ((1 << 64) - 1)) & m and not (row[1 + chunks + k] & ((1 << 64) - 1)) & m:
                    person.add((row[0], c))
    upserts, deletes, unpinned = [], [], set()
    for (r, c), (it, moved) in sorted(cells.items()):
        was = held.get((r, c))
        pin = None if (r, c) in freed else (was[2] if was else None)
        if was and was[2] is not None and pin is None:
            unpinned.add((r, c))
        who = it.get("written_by") or "system"
        if (r, c) in person or pin is not None:
            if moved or not (was and was[0] is True and was[1] == who and was[2] == pin):
                upserts.append({"table_name": table, "row_id": r, "column_name": c, "is_overwrite": True,
                                "updated_by": who, "updated_at": datetime.now(), "manual_priority_source": pin})
        elif was:
            deletes.append((table, r, c))
    crud.bulk_upsert_cell_overwrites(db, upserts)
    crud.bulk_delete_cell_overwrites(db, deletes)
    return unpinned


def _merge_now(db, table, cfg, shape, row_ids, at, old, plain, keeps, blank=None, columns=None):
    """Step 5 - the touched rows of t merged again by `lines.merge` (C - the one merge, ranked by crud.rank_terms):
    a column it decides takes its value and won_by; a column it leaves out (no line spoke in it, or its pinned source
    has no head line) keeps t's value and no won_by; then a column of no history takes its value (`_plain`). Written
    with won_by; updated_at is the write's instant on a new row or one whose values moved (`_moved`), else it stays -
    a line that moved nothing shown is no change of the row (the old write's rule, lead 11-11 ㄱ). `blank` {row_id:
    columns}: of those, a column the merge leaves out goes blank (a removed formula's). `columns`: the columns the
    write touched - only those are merged, every other keeps its value and won_by (lead 11-12 b); None, all. Returns
    {row_id: {column: value}} as written."""
    now = shape["table"]
    data = [c.name for c in now.columns if c.name not in {n for n, _t in lines.FRAMEWORK} and c.name != lines.WON_BY]
    if not row_ids:
        return {}
    merged = {row_id: {c: (old.get(row_id) or {}).get(c) for c in data} for row_id in row_ids}
    won_by = {row_id: {} if columns is None else {c: w for c, w in ((old.get(row_id) or {}).get("won_by") or {}).items()
                                                  if c not in columns} for row_id in row_ids}
    if columns is not None:                        # a column not merged reads as its line reads it (lead 11-11: 2, not 2.0)
        numbers = [c for c in data if c not in columns and shape["kinds"].get(c) == "number"]
        for row_id in row_ids:
            for c in numbers:
                if merged[row_id][c] is not None:
                    merged[row_id][c] = crud.line_value(crud.line_text(merged[row_id][c], "number"), "number")
    spoke = lines.merge(db, table, cfg, row_ids, s=shape, columns=columns) if keeps else {}
    for row_id, decided in spoke.items():
        for c, (value, line_id) in decided.items():
            merged[row_id][c] = value
            if line_id is not None:
                won_by[row_id][c] = line_id
    for row_id, columns in (blank or {}).items():
        for c in set(columns) & set(data) - set(spoke.get(row_id, ())):
            merged[row_id][c] = None
    for row_id, values in plain.items():
        if row_id in merged:
            merged[row_id].update(values)          # a column of no history: its value, no line, no won_by
    key_column = cfg.get("business_key") if cfg.get("composite_key_source") else None
    if key_column in data:                         # its key column shows its key, never a line
        for row_id in row_ids:
            key = (old.get(row_id) or {}).get("business_key_val")
            if key is not None:
                merged[row_id][key_column] = key
                won_by[row_id].pop(key_column, None)
    types = cfg.get("column_types") or {}
    if keeps:
        _formulas_won(db, table, shape, row_ids, data, merged, won_by)
    moved, only_won = [], []                       # a row where neither moved is not written - no dead row
    for row_id in row_ids:
        if row_id not in old or _moved(old[row_id], merged[row_id], data, types):
            moved.append(row_id)
        elif keeps and (old[row_id].get("won_by") or {}) != won_by[row_id]:
            only_won.append(row_id)
    names = data + (["won_by"] if keeps else [])
    if _sets_at_once(db) and all(
            crud.one_kind([merged[r][c] for r in moved + only_won]) for c in data):
        # one statement a page (crud.update_by_arrays, the set door - lead 11-12 ㄴ): psycopg2 sends an UPDATE's
        # parameter sets one round trip each
        for ids, stamp in ((moved, ["updated_at"]), (only_won, [])):
            for page in _pages(ids, 1):
                crud.update_by_arrays(db, now, names + stamp, [
                    [r] + [merged[r][c] for c in data] + ([won_by[r]] if keeps else []) for r in page], at)
        return merged
    # bound names no column can take - a bound name equal to one of t's columns is refused by SQLAlchemy
    if moved or only_won:
        db.execute(update(now).where(now.c.row_id == bindparam("__row")).values(
            {**{c: bindparam("__%d" % n) for n, c in enumerate(data)},
             **({"won_by": bindparam("__won")} if keeps else {}), "updated_at": bindparam("__at")}),
            [{"__row": row_id, "__won": won_by[row_id], **{"__%d" % n: merged[row_id][c] for n, c in enumerate(data)},
              "__at": at if row_id in set(moved) else old[row_id].get("updated_at")}
             for row_id in moved + only_won])
    return merged


def _formulas_won(db, table, shape, row_ids, data, merged, won_by) -> None:
    """A formula column's candidate (lead 10-28 ㄴ: a formula holds no line, its value is the merge's; A 11-11 안 1):
    each row's formula column ranked with its layers and pin by `crud.compute_priority_value(cell=)` - the rank the
    old write asked - over the row as merged; where the formula wins its answer is the value and won_by says
    `lines.FORMULA_WON`. A pin whose source has no head line leaves the merge's answer (t's value, lead 11-11)."""
    from types import SimpleNamespace

    from chain import formula

    said = {c: name for (t, c), (name, *_rest) in formula.columns().items() if t == table and c in data}
    if not said:
        return
    cells = lines.layers(db, table, row_ids, sorted(said), s=shape)
    pins = _overwrites(db, table, row_ids, sorted(said))
    ranks = {}
    for row_id in row_ids:
        row = SimpleNamespace(**merged[row_id])
        for c, name in sorted(said.items()):
            layers = cells.get((row_id, c)) or {}
            pin = (pins.get((row_id, c)) or (None, None, None))[2]
            if pin is not None and pin != name and pin not in layers:
                continue
            value, top = crud.compute_priority_value(dict(layers), pin, table, ranks=ranks, cell=(table, c, row))
            if top == name:
                merged[row_id][c] = value
                setattr(row, c, value)
                won_by[row_id][c] = lines.FORMULA_WON


def _merges_again(item) -> bool:
    """A mark naming no column and asking no re-key: its row merged again, no line written (lead 11-11 (가))."""
    return item["line_kind"] == MARK and not item.get("columns") and not item.get("rekey")


def _moved(old, new, columns, types) -> list:
    """The `columns` whose value moved from the row `old` to `new` - what a reader of t sees change."""
    return [c for c in columns if crud.values_differ(old.get(c), new.get(c), types.get(c, "string"))]


def _rekey(db, table, cfg, shape, keeps, items, targets, given, new, old, keys, at, transaction_id) -> dict:
    """Step 5½ - a row that was there before whose key part's value step 5 moved gets its key rebuilt
    (`crud.rebuilt_business_key` on the merged values, business_key_val and the declared key column - design «업무 키가 바뀔
    때»); on a table keyed by one column, that column's value composed (`crud.compose_business_key`) - a blank one
    writes nothing, and a row an item named by its key keeps that key: the old write door's rules.
    NEW for that shape: a key another row holds merges the row into it (design «업무 키가 바뀔 때», owner 11-10) -
    the old seat wrote the key and met the unique index. Every new key of the batch is known first: a key is held by a row outside the batch's moves, or by a row of
    the batch that took it before (row_id order) - so rows swapping or passing keys along in one batch move, not
    merge. The keys are written first (`_put_keys`); then a held key takes the row in (`_merge_into`), with what this
    write named as its explicit values and, from a person, its person's cells - the old write seat's rule
    (`crud.writes_as_person`); a pin's cells are both. -> {merged row_id: (holder, holder's line before, after,
    who)}; `new` and `keys` follow."""
    from types import SimpleNamespace

    parts, key_column = cfg.get("composite_key_source") or [], cfg.get("business_key")
    watched = parts or ([key_column] if key_column else [])
    if not watched:
        return {}
    now, types = shape["table"], cfg.get("column_types") or {}
    by_key = {targets[i] for i in targets if items[i].get("business_key_val") or items[i].get("key")}
    forced = {targets[i] for i in targets if items[i].get("rekey")}
    moving = {}
    for row_id in sorted(new):
        was = old.get(row_id)
        if was is None or not (row_id in forced or any(
                crud.values_differ(was.get(p), new[row_id].get(p), types.get(p, "string")) for p in watched)):
            continue
        if parts:
            key = crud.rebuilt_business_key(table, SimpleNamespace(**new[row_id]))
        else:
            if row_id in by_key and row_id not in forced:   # the item's own key wins (looked up by it)
                continue
            key = crud.compose_business_key(table, [new[row_id].get(key_column)], [key_column])
            if crud.is_blank_value(key):
                continue
        if key != keys.get(row_id, was.get("business_key_val")):
            moving[row_id] = key
    held = {key: row["row_id"] for key, row in key_owners(           # key -> the row outside the moves holding it
        db, now, {k for k in moving.values() if k is not None}, but=moving, lock=True).items()}
    taken, moves, into = {}, {}, {}
    for row_id, key in sorted(moving.items()):
        holder = None if key is None else taken.get(key) or held.get(key)
        if holder is None:
            moves[row_id] = key
            if key is not None:
                taken[key] = row_id
        else:
            into[row_id] = holder
    _put_keys(db, now, key_column if parts else None, moving, moves, new, keys, at)
    merged = {}
    for row_id, holder in sorted(into.items()):
        explicit, human, who = {}, set(), None
        for i in sorted(targets):
            it = items[i]
            if targets[i] != row_id:
                continue
            who = who or it.get("acted_by") or it.get("written_by")
            if it["line_kind"] == WRITE and not it.get("respelled"):     # no new hand: names nothing
                explicit.update(given.get(i) or {})
                if crud.writes_as_person(it.get("source_name"), it.get("written_by")):
                    human.update(given.get(i) or {})
            elif it["line_kind"] == MARK:          # a pin: a person choosing a layer, its cells as they show now
                explicit.update({c: new[row_id].get(c) for c in it.get("columns") or ()})
                human.update(it.get("columns") or ())
        # a value no line said is the merge's writer's: the actor's name when one acts for the author (a backfill
        # re-spelling a person's key) - never «user (<tag>)», a person's layer the person did not write (A 11-11)
        source = next((items[i].get("acted_by") or items[i].get("source_name")
                       for i in sorted(targets) if targets[i] == row_id), None)
        _shell, holder_old, holder_new = _merge_into(
            db, table, cfg, shape, keeps, row_id, holder, explicit=explicit, human=human, source_name=source,
            written_by=who, at=at, transaction_id=transaction_id,
            shell_key=keys.get(row_id, (old.get(row_id) or {}).get("business_key_val")))
        merged[row_id] = (holder, holder_old, holder_new, who)
        if holder in new:
            new[holder] = holder_new
    return merged


def _put_keys(db, now, key_column, moving, moves, new, keys, at) -> None:
    """Every row whose key moves - free or merged away - cleared first, then each free move's new key taken: two
    statements, a swap or a key passed along meets no unique key. On business_key_val and the declared key column
    where t has it - and then updated_at, a shown column having moved (the old
    write's written_col)."""
    if not moving:
        return
    column = key_column if key_column and key_column in now.c else None
    db.execute(update(now).where(now.c.row_id == bindparam("__row")).values(business_key_val=None),
               [{"__row": row_id} for row_id in sorted(moving)])
    if not moves:
        return
    db.execute(update(now).where(now.c.row_id == bindparam("__row")).values(
        {"business_key_val": bindparam("__key"), **({column: bindparam("__key"), "updated_at": at} if column else {})}),
        [{"__row": row_id, "__key": key} for row_id, key in sorted(moves.items())])
    for row_id, key in moves.items():
        keys[row_id] = key
        if column and row_id in new:
            new[row_id][column] = key


def _merge_into(db, table, cfg, shape, keeps, shell, holder, *, explicit, human, source_name, written_by, at,
                transaction_id, shell_key=None):
    """`shell` merged into `holder`, the row holding its key (design «업무 키가 바뀔 때»; the old
    merge body's rules, cell for cell). Which value wins is today's: the shell's - `explicit`'s where this
    write named it - unless the holder's cell is a person's or pinned and neither this write's nor the shell's is; a
    blank never wins. The layers left are today's, as head lines: the shell's lines move to the holder under
    `merged_layer_name(source, key_rowid)`; where both rows' cells are a person's the holder's «user» value stays as
    «user (old_exist_…)» and the shell's is «user»; a shell value no line said is a line of the writer's; a value
    that wins is a «collision_merge» line its pin shows, and one «mark» line says the merge on the holder whatever
    moved; a cell this write made a person's that the holder has no mark on is marked a person's there. The shell's
    current line and marks go; the holder is merged again - a moved line may show at once (lead 11-11 ㄱ). -> (shell's line, holder's before, holder's after)."""
    from datetime import datetime

    from database import models

    now = shape["table"]
    got = {row["row_id"]: dict(row) for row in db.execute(
        select(now).where(now.c.row_id.in_(sorted((shell, holder)))).order_by(now.c.row_id).with_for_update())
        .mappings()}
    s_now, h_now = got[shell], got[holder]
    types = cfg.get("column_types") or {}
    framework = {name for name, _type in lines.FRAMEWORK} | {lines.WON_BY, cfg.get("business_key")}
    data = [c.name for c in now.columns if c.name not in framework]
    ov = models.CellOverwrite.__table__
    marks = {(r, c): (flag, by, pin) for r, c, flag, by, pin in db.execute(
        select(ov.c.row_id, ov.c.column_name, ov.c.is_overwrite, ov.c.updated_by, ov.c.manual_priority_source)
        .where(ov.c.table_name == table, ov.c.row_id.in_((shell, holder))))}

    def persons(row_id, c):                        # a person's value or pin, not a merge's own mark
        m = marks.get((row_id, c))
        return bool(m) and crud.COLLISION_SOURCE not in (m[1], m[2]) and (bool(m[0]) or m[2] is not None)

    chosen, both = {}, set()
    for c in data:
        theirs, ours = persons(holder, c), c in human or persons(shell, c)
        if theirs and ours:
            both.add(c)
        value = crud.none_if_blank(s_now.get(c))
        if c in explicit:
            try:                                   # cast as every write casts (총괄 88761926b)
                value = crud.cast_value_by_type(explicit[c], types.get(c, "string"), c, table)
            except crud.CellRefused as refused:
                logger.warning("[Merge] %s row %s column %s: the edited value was refused (%s) - the merged row's "
                               "value %r is kept", table, holder, c, refused, value)
        if (value is not None and (ours or not theirs or c in explicit)
                and crud.values_differ(h_now.get(c), value, types.get(c, "string"))):
            chosen[c] = value
    bits = shape["bits"] if keeps else {}
    plain = {c: v for c, v in chosen.items() if c not in bits}
    if keeps:
        ln, chunks, held = shape["lines"], shape["chunks"], shape["kinds"]
        shell_key = shell_key if shell_key is not None else s_now.get("business_key_val")
        tag = "%s_%s" % (shell_key, shell) if shell_key else shell
        user_cols = sorted(c for c in both if c in bits)
        heads = lines.layers(db, table, [shell, holder], user_cols, s=shape) if user_cols else {}
        spoke = lines.spoken(db, table, [shell], s=shape).get(shell, set())
        talking = (WRITE, WITHDRAW)
        renamed = {src: crud.merged_layer_name(src, tag) for src in db.execute(
            select(ln.c.source_name).distinct().where(ln.c.row_id == shell, ln.c.source_name.is_not(None),
                                                      ln.c.line_kind.in_(talking))).scalars()}
        for src, name in sorted(renamed.items()):
            db.execute(update(ln).where(ln.c.row_id == shell, ln.c.source_name == src, ln.c.line_kind.in_(talking))
                       .values(row_id=holder, source_name=name))
        db.execute(update(ln).where(ln.c.row_id == shell).values(row_id=holder))
        if renamed:                                # a moved withdraw line is history - it does not make a cell spoken
            db.execute(update(ln).where(ln.c.row_id == holder, ln.c.source_name.in_(sorted(renamed.values())),
                                        ln.c.line_kind == WITHDRAW).values({"head_%d" % k: 0 for k in range(chunks)}))

        def text(values):
            return {c: crud.line_text(v, held.get(c, "string")) for c, v in values.items()}

        said = []
        theirs = {c: h for c in user_cols for h in [(heads.get((holder, c)) or {}).get(crud.USER_SOURCE)]
                  if h and h["value"] is not None}
        if theirs:
            said.append({"source_name": crud.merged_layer_name(crud.USER_SOURCE, "old_exist_%s" % holder[:6]),
                         "written_by": next(iter(theirs.values()))["updated_by"],
                         "values": text({c: h["value"] for c, h in theirs.items()})})
        ours = {c: h for c in user_cols for h in [(heads.get((shell, c)) or {}).get(crud.USER_SOURCE)] if h}
        if ours:
            said.append({"source_name": crud.USER_SOURCE, "written_by": next(iter(ours.values()))["updated_by"],
                         "values": text({c: h["value"] for c, h in ours.items()})})
            copy = renamed.get(crud.USER_SOURCE)
            if copy:                               # its moved copy no longer heads them - the shell's «user» does
                masks = _masks(bits, chunks, ours)
                db.execute(update(ln).where(ln.c.row_id == holder, ln.c.source_name == copy).values(
                    {"head_%d" % k: ln.c["head_%d" % k].op("&")(~masks[k]) for k in range(chunks)}))
        fallback = {c: s_now[c] for c in data
                    if c in bits and c not in spoke and not crud.is_blank_value(s_now.get(c))}
        if fallback:
            said.append({"source_name": crud.merged_layer_name(source_name or crud.USER_SOURCE, tag),
                         "written_by": written_by or "system", "values": text(fallback)})
        wins = {c: v for c, v in chosen.items() if c in bits}
        if wins:
            said.append({"source_name": crud.COLLISION_SOURCE, "written_by": written_by or "system",
                         "values": text(wins)})
        for it in said:
            it["line_kind"] = WRITE
        # one mark line on the holder, always: the merge's own new line - the migration's write_back finds a row by a
        # line newer than the copy, and moved lines keep their old line_id (C · lead 11-11)
        said.append({"line_kind": MARK, "source_name": crud.COLLISION_SOURCE, "written_by": written_by or "system"})
        # a copy of the shell's - its moved lines and a shell value no line said - ranks behind the holder's own
        # (lead 11-12 ㄴ); the holder's own person value kept as «old_exist» is the holder's, not a copy
        copies = {name: src for src, name in renamed.items()}
        if fallback:
            copies[crud.merged_layer_name(source_name or crud.USER_SOURCE, tag)] = source_name or crud.USER_SOURCE
        lines.note_sources(db, set(renamed.values()) | {it["source_name"] for it in said}, copies)
        if said:
            every = set(range(len(said)))
            written, _ids = _lines(db, ln, bits, chunks, said, every, {i: holder for i in every},
                                   {holder: h_now.get("business_key_val")}, at, transaction_id)
            _heads(db, ln, chunks, written)
    person = sorted(c for c in human if c not in chosen and (holder, c) not in marks)
    if chosen or person:
        crud.bulk_upsert_cell_overwrites(db, [{"table_name": table, "row_id": holder, "column_name": c,
                                               "is_overwrite": True, "updated_by": crud.COLLISION_SOURCE,
                                               "updated_at": datetime.now(),
                                               "manual_priority_source": crud.COLLISION_SOURCE}
                                              for c in sorted(chosen)]
                                         + [{"table_name": table, "row_id": holder, "column_name": c,
                                             "is_overwrite": True, "updated_by": written_by or "system",
                                             "updated_at": datetime.now(), "manual_priority_source": None}
                                            for c in person])
    db.execute(delete(now).where(now.c.row_id == shell))
    crud.delete_row_layers(db, table, [shell])
    merged = _merge_now(db, table, cfg, shape, [holder], at, {holder: h_now}, {holder: plain} if plain else {}, keeps)
    return s_now, h_now, merged[holder]


def _stage(db, table, cfg, view_columns, changed, keys, wrote):
    """Step 7 - this write's outbox events, in its transaction, from its answer - the one author the broadcast reads
    too (owner rule: the chain wakes on these). Today's shapes (the ORM flush hook's, kept letter for letter): a new
    row CREATE - per row its values, collapsed the columns it wrote with row_id and business_key_val; a current line
    whose shown values changed EDIT - those columns, their old values; none when nothing shown changed; a deleted row
    DELETE, collapsed always, its values as the old ones (`crud.delete_rows_batch`'s)."""
    from database.context import request_outbox_mode
    from database.database import json_value, stage_collapsed_event, stage_event
    from event_constants import OUTBOX_MODE_COLLAPSED, OUTBOX_PAYLOAD_EXCLUDED_COLUMNS
    from types import SimpleNamespace

    types = cfg.get("column_types") or {}
    shown = [c for c in view_columns if c not in OUTBOX_PAYLOAD_EXCLUDED_COLUMNS]
    collapsed = request_outbox_mode.get() == OUTBOX_MODE_COLLAPSED
    table_shape = SimpleNamespace(columns=[SimpleNamespace(name=c) for c in view_columns])
    events = {"CREATE": [], "EDIT": [], "DELETE": []}
    for row_id, change in changed.items():
        old, new = change["old"] or {}, change["new"]
        if new is None:
            events["DELETE"].append((row_id, None, {c: json_value(old.get(c)) for c in shown}, old))
            continue
        row = SimpleNamespace(__table__=table_shape, row_id=row_id,
                              business_key_val=keys.get(row_id, old.get("business_key_val")),
                              **{c: new.get(c) for c in shown})
        if change["old"] is None:
            events["CREATE"].append((row_id, sorted(wrote.get(row_id, set()) | {"row_id", "business_key_val"}),
                                     None, row))
            continue
        moved = _moved(old, new, shown, types)
        if moved:
            events["EDIT"].append((row_id, moved, {c: json_value(old.get(c)) for c in moved}, row))
    for event_type, rows in events.items():
        if not rows:
            continue
        if collapsed or event_type == "DELETE":
            stage_collapsed_event(db, event_type, table, [r[0] for r in rows],
                                  sorted({c for r in rows for c in r[1] or ()}) or None,
                                  old=[r[2] or {} for r in rows] if event_type != "CREATE" else None)
        else:
            for _row_id, _columns, old, row in rows:
                stage_event(db, event_type, table, row, old=old)


def _audit(db, table, said, transaction_id, at):
    """Step 6 - one audit row a (work kind, who) of the batch: transaction, table, who, work kind, at. No values, no
    count - the panel counts the transaction's lines. `said`: {(work kind, who): the distinct row_ids it wrote lines
    for}. -> the rows for the caller's after-commit add_changed, each with that count."""
    order = sorted(said, key=lambda p: (p[0], p[1] or ""))
    if order:
        db.execute(insert(lines.AuditBatch.__table__), [{"transaction_id": transaction_id, "table_name": table,
                                                         "written_by": who, "work_kind": work_kind, "at": at}
                                                        for work_kind, who in order])
    return [{"transaction_id": transaction_id, "table_name": table, "changed_rows": len(said[(work_kind, who)]),
             "kind": work_kind, "written_by": who} for work_kind, who in order]
