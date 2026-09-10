"""Writing atoms and moving the cursor - in ONE transaction, per the brief's risk 1.

WHY THE CURSOR ADVANCE AND THE ATOM APPEND SHARE A TRANSACTION
---------------------------------------------------------------
`ingestion_checkpoint.record_chunk_progress` (the watcher's P2-A pattern the brief tells
this lane to reuse) already argued this and the argument transfers exactly: writing the
cursor BEFORE the commit risks skipping work on a crash, writing it AFTER risks redoing
it, and putting both in one transaction makes "atoms written == cursor position" an
atomic fact. `write_batch` therefore takes the cursor value it should land on and issues
both statements on one connection with one commit.

WHY A MOLECULE IS NEVER SPLIT ACROSS TRANSACTIONS
--------------------------------------------------
The brief's rule is "transaction unit = one source event". A transaction holding N WHOLE
molecules satisfies it strictly more tightly than one molecule per transaction does, and
it is the only version that survives ten million rows - so the rule this implements is
"an integral number of source events, never a fraction". `backfill.py` owns the cutting
and cuts on a boundary the source itself provides; this module only ever receives whole
molecules and writes them together.

WHY `execute_values` AND NOT `executemany`
-------------------------------------------
`crud.py` measured this for the write path already: one multi-row `INSERT` instead of N
round trips. `page_size=1000` is the same chunking constant the rest of the system uses.

CONNECTIONS COME FROM THE SQLALCHEMY ENGINE, NOT FROM `psycopg2.connect`
------------------------------------------------------------------------
🔴 Deliberate and load-bearing. `database.database` installs `db_safety`'s guards on the
Engine class, and those guards are what make it impossible for a test process to reach
the production database. A raw `psycopg2.connect` would walk straight past them. Every
connection this module uses comes from `engine.raw_connection()`, so the guard is on the
path.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache

from . import schema
from .envelope import ROW_COLUMNS

logger = logging.getLogger("Ledger.Store")

INSERT_PAGE_SIZE = 1000

#: Ruling R-2026-08-13-H-bis 2. Spelled once, raised from both the public write and the
#: private statement under it, so the two cannot drift into saying different things about
#: the same rule.
_REASONS_REQUIRED = (
    "reasons is required and must not be None (ruling R-2026-08-13-H-bis 2). Pass this "
    "batch's refusals BY NAME as {reason: molecules}; pass an explicit {} when the batch "
    "refused nothing. There is no default, because a write that advances "
    "molecules_refused without names produces the same positive `refusals_unaccounted` "
    "that `ledger_trace` reports as DEPLOYMENT HISTORY - so a live bookkeeping hole "
    "would be shown to the operator as an old one.")

#: `enforce_translator_version` IS a WHERE clause on the cursor statement, so a caller who
#: asks for the guard AND asks to skip that statement would be told the write was guarded
#: when nothing guarded it. Refused by name rather than resolved either way, because both
#: resolutions lie: honouring the flag would move a cursor the caller said not to move, and
#: dropping it would drop a guard the caller asked for.
_VERSION_GUARD_NEEDS_CURSOR = (
    "enforce_translator_version requires advance_cursor=True: the version guard is a "
    "condition on the cursor statement, so a write that skips that statement cannot "
    "honour it. A scoped redo re-translates on purpose and asks for neither.")


class CursorVersionConflict(RuntimeError):
    """The stored cursor belongs to a different compiled execution contract."""


def _json(value):
    from psycopg2.extras import Json
    return Json(value)


def _insert_audit_row(connection, row):
    """INSERT one audit row on `connection`, in whatever transaction it is already in.

    🔴 ONE SPELLING OF THE INSERT, AND THE COLUMN LIST IS THE MODEL'S (S-117, 판정 248).
    Both callers reach this: the receipt that rides the atoms' commit, and the failure
    receipt that needs a commit of its own precisely because the atoms' one rolled back.
    The columns are read off `AuditLog.__table__` rather than typed here, so a column
    added to the model cannot leave this statement writing yesterday's shape.

    ⚠️ A RAW CONNECTION, NOT A SESSION, and that is why this exists at all. The atoms are
    written on `engine.raw_connection()`; a `Session` cannot join that transaction, so
    `crud.bulk_insert_audit_logs` - the ordinary insert - cannot be the one used here.
    What it CAN share, and does, is the decision about what the row says: the callers
    build `row` with `crud.create_audit_log(..., add_to_cache=False)`.
    """
    if not row:
        return 0
    from database import models

    import sqlalchemy
    from psycopg2.extras import Json

    table = models.AuditLog.__table__
    columns = [c for c in table.columns if c.name in row and not c.primary_key]
    if not columns:
        return 0

    def adapt(column, value):
        # 🔴 THE COLUMN'S OWN TYPE DECIDES, AND IT HAD TO (measured, first live run).
        # `new_value` is declared `JSON`, so the ORM serialises a dict on its way down and
        # a raw cursor does not: psycopg2 answered `can't adapt type 'dict'` and the
        # receipt was lost while the batch went on. Read off the model rather than named
        # here, so a column that becomes JSON later is carried without a second edit.
        if value is None or isinstance(value, (str, bytes)):
            return value
        if isinstance(column.type, sqlalchemy.JSON):
            return Json(value)
        return value

    statement = 'INSERT INTO "%s" (%s) VALUES (%s)' % (
        table.name,
        ", ".join('"%s"' % column.name for column in columns),
        ", ".join(["%s"] * len(columns)))
    with connection.cursor() as cursor:
        cursor.execute(statement,
                       tuple(adapt(column, row[column.name]) for column in columns))
    return 1


class LedgerStore:
    """Everything that touches the two ledger tables. One object, one engine.

    Holds no session state beyond the set of partitions it has already ensured, which is
    a pure cache of a catalogue fact and is safe to lose.
    """

    def __init__(self, engine, who: str = "ledger"):
        self.engine = engine
        self.who = who
        self._known_partitions = set()

    # ------------------------------------------------------------------ connections
    def connection(self):
        """A raw DBAPI connection from the guarded engine. Caller closes it."""
        return self.engine.raw_connection()

    def ensure_schema(self):
        connection = self.connection()
        try:
            schema.ensure_schema(connection)
        finally:
            connection.close()

    # ------------------------------------------------------------------------ writes
    def ensure_partitions(self, connection, occurred_ats):
        for when in occurred_ats:
            schema.ensure_partition(connection, when, known=self._known_partitions)

    def existing_registrations(self, connection, subjects):
        """Which of `subjects` already have a `register` atom.

        `subjects` is an iterable of `(subject_type, canonical_keys_json)` - the memo
        form `envelope.canonical_keys` produces - and the return value is a set in the
        same form, so the caller can union it straight into the translator's memo.

        ONE query per chunk for the whole page. A per-entity lookup is what turns a
        ten-million row backfill quadratic; this is the query `idx_ledger_register`
        exists for, and that index is partial (`WHERE predicate = 'register'`) because
        registers are O(entities) while the table is O(atoms).
        """
        wanted = sorted(set(subjects))
        if not wanted:
            return set()
        found = set()
        with connection.cursor() as cursor:
            for start in range(0, len(wanted), INSERT_PAGE_SIZE):
                chunk = wanted[start:start + INSERT_PAGE_SIZE]
                cursor.execute(
                    f"SELECT subject_type, subject_keys FROM {schema.LEDGER_TABLE} "
                    f"WHERE predicate = 'register' "
                    f"  AND (subject_type, subject_keys) IN %s",
                    (tuple((t, _json(json.loads(k))) for t, k in chunk),))
                for subject_type, keys in cursor.fetchall():
                    found.add((subject_type, json.dumps(
                        keys, sort_keys=True, separators=(",", ":"), ensure_ascii=False)))
        return found

    def current_atoms_for_subjects(self, connection, predicate, subjects):
        """The atom that is CURRENTLY true for each of `subjects` on one predicate.

        `subjects` is an iterable of `(subject_type, canonical_keys_json)` - the same memo
        form `existing_registrations` takes - and the answer maps each found subject to the
        id of its live atom, which is what a superseding atom points at.

        🔴 THE LATEST ATOM IS THE LIVE ONE, and that is a property of how supersession is
        written rather than an assumption about the data: each new atom on a `one`
        predicate points at the previous latest, so the chain is linear and its head is the
        most recent row. Asking 「which id is in nobody's supersedes」 would be the same
        answer through an anti-join.

        ONE query per chunk for the whole batch, exactly as `existing_registrations` does.
        A per-subject lookup is what turns a thousand-row transaction into a thousand round
        trips, which is the shape production actually runs.
        """
        wanted = sorted(set(subjects))
        if not wanted or not predicate:
            return {}
        current = {}
        with connection.cursor() as cursor:
            for start in range(0, len(wanted), INSERT_PAGE_SIZE):
                chunk = wanted[start:start + INSERT_PAGE_SIZE]
                cursor.execute(
                    f"SELECT DISTINCT ON (subject_type, subject_keys) "
                    f"       subject_type, subject_keys, id "
                    f"FROM {schema.LEDGER_TABLE} "
                    f"WHERE predicate = %s "
                    f"  AND (subject_type, subject_keys) IN %s "
                    f"ORDER BY subject_type, subject_keys, occurred_at DESC, id DESC",
                    (predicate,
                     tuple((t, _json(json.loads(k))) for t, k in chunk)))
                for subject_type, keys, atom_id in cursor.fetchall():
                    current[(subject_type, json.dumps(
                        keys, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False))] = atom_id
        return current

    def insert_atoms(self, connection, atoms):
        """Insert on an OPEN transaction. Returns `(attempted, inserted)`.

        Does not commit - `write_batch` owns the commit, because the cursor advance has
        to be inside the same one.

        `ON CONFLICT DO NOTHING` is the second idempotency net (`uq_ledger_atom`). The
        two numbers are returned separately and are never collapsed: `attempted >
        inserted` means the cursor let work through that the index then recognised as
        already done, and an operator has to be able to see that rather than read a
        single reassuring total.
        """
        from psycopg2.extras import execute_values

        rows = []
        for atom in atoms:
            atom.ensure_id()
            atom.ensure_source_event_identity()
            rows.append((
                str(atom.id), atom.subject_type, _json(atom.subject_keys),
                atom.predicate, atom.object_kind,
                None if atom.object_payload is None else _json(atom.object_payload),
                atom.occurred_at, atom.source_who, atom.source_translator_ver,
                atom.source_raw_ref,
                str(atom.supersedes) if atom.supersedes else None,
                str(atom.source_event_id), atom.source_event_state,
                atom.occurred_at_basis,
            ))
        if not rows:
            return 0, 0

        inserted = 0
        with connection.cursor() as cursor:
            for start in range(0, len(rows), INSERT_PAGE_SIZE):
                chunk = rows[start:start + INSERT_PAGE_SIZE]
                execute_values(
                    cursor,
                    f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                    f"VALUES %s ON CONFLICT DO NOTHING",
                    chunk, page_size=INSERT_PAGE_SIZE)
                inserted += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        return len(rows), inserted

    # ----------------------------------------------------------------------- cursor
    def read_cursor(self, connection, source: str):
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT translator_ver, cursor_value, molecules_done, atoms_written, "
                f"       atoms_deduped, molecules_refused, incomplete_molecules, "
                f"       source_head, head_probed_at, updated_at, refusal_reasons, "
                f"       {schema.ROW_CENSUS_COLUMN} "
                f"FROM {schema.CURSOR_TABLE} WHERE source = %s", (source,))
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "source": source, "translator_ver": row[0], "cursor_value": row[1],
            "molecules_done": row[2], "atoms_written": row[3], "atoms_deduped": row[4],
            "molecules_refused": row[5], "incomplete_molecules": row[6],
            "source_head": row[7], "head_probed_at": row[8], "updated_at": row[9],
            "refusal_reasons": row[10], "row_census": row[11],
        }

    def write_row_census(self, source: str, census, *, translator_ver: str) -> None:
        """Store one source's 「table rows · indexed rows · remainder」 measurement.

        🔴 THIS IS THE ONE PLACE A SOURCE GETS ITS ROW (S-113 ⓑ-1, ruling 221), and it
        is one statement. `_advance_cursor`'s INSERT used to be the only row creator in the
        table, and since S-76 the live path calls the store with `advance_cursor=False`, so
        nothing created a row any more: a source declared after that date could be measured
        every cycle and the UPDATE would match nothing, forever. That silence reached a
        screen -- `/declaration` reads this very column, and the sources panel reads the row's
        absence as `never_ran`.

        ⛔ IT USED TO REFUSE TO CREATE THE ROW, and the reason was right: a census beside a
        translator version that does not exist is "a source that looks measured and has never
        run". The answer is not to keep the silence but to write the version IN THE SAME
        STATEMENT, which is why `translator_ver` is required and keyword-only. The row that
        appears therefore says two true things at once -- which declaration this source is on,
        and what its relation held when it was last counted.

        🔴 ON CONFLICT IT DOES NOT TOUCH `translator_ver`. Re-stamping is
        `restamp_cursor`'s decision and it only ever moves a string it was told to expect
        (S-87). A census tick that overwrote the fingerprint would be exactly the unattended
        silent move that guard exists to prevent, so the version is carried by the INSERT
        alone and every later tick writes the census and the clock.

        ⚠️ `cursor_value` IS `'null'::jsonb` AND THAT IS THE HONEST VALUE. The column is
        NOT NULL and the position is retired -- nothing reads it to decide where to resume
        (`observability` reads it as `or {}`), so a JSON null says "this row carries no
        position" rather than a zero that would read as one. Dropping the constraint is a
        migration and is not part of this.
        """
        import json as _json

        connection = self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {schema.CURSOR_TABLE} "
                    f"       (source, translator_ver, cursor_value, "
                    f"        {schema.ROW_CENSUS_COLUMN}) "
                    f"VALUES (%s, %s, 'null'::jsonb, %s::jsonb) "
                    f"ON CONFLICT (source) DO UPDATE "
                    f"   SET {schema.ROW_CENSUS_COLUMN} = "
                    f"       EXCLUDED.{schema.ROW_CENSUS_COLUMN}, "
                    f"       updated_at = now()",
                    (source, translator_ver, _json.dumps(census)))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    #: `now()` as UTC ISO-8601, built in SQL so `last_at` is stamped by the DATABASE
    #: clock in the same transaction as the count it belongs to. Rendering it here rather
    #: than in Python also keeps one spelling of "when": `updated_at` beside it is
    #: `now()` too, so a reader comparing the two is comparing one clock.
    _NOW_ISO = "to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00'"

    #: The INSERT side: a `{reason: count}` delta becomes `{reason: {count, last_at}}`.
    #: An empty delta becomes `{}` - the writer has owned this row and refused nothing,
    #: which is a different fact from the NULL a row predating the column carries.
    _SHAPE_REASONS = f"""
        (SELECT coalesce(jsonb_object_agg(key, jsonb_build_object(
                    'count', value::bigint, 'last_at', {_NOW_ISO})), '{{}}'::jsonb)
         FROM jsonb_each_text(%s::jsonb))
    """

    def _merge_reasons_sql(self):
        """The ON CONFLICT side: old breakdown + this batch's delta, per reason.

        🔴 A FULL JOIN rather than `||`, because jsonb has no per-key arithmetic and `||`
        would REPLACE each key's count with the batch's instead of adding it - a
        breakdown that silently reported the last batch while the aggregate beside it
        reported the run. `last_at` moves only for reasons this batch actually saw;
        a reason that has gone quiet keeps the time it last fired, which is what makes a
        stale entry tell its own age instead of looking current.

        Bounded by the size of `gate.REFUSAL_REASONS` (a closed vocabulary), so this is
        arithmetic over at most a dozen keys no matter how large the ledger grows.
        """
        table = schema.CURSOR_TABLE
        return f"""
        (SELECT coalesce(jsonb_object_agg(k, jsonb_build_object(
                    'count', c, 'last_at', l)), '{{}}'::jsonb)
         FROM (
            SELECT coalesce(o.key, n.key) AS k,
                   coalesce((o.value->>'count')::bigint, 0)
                 + coalesce((n.value->>'count')::bigint, 0) AS c,
                   coalesce(n.value->>'last_at', o.value->>'last_at') AS l
            FROM jsonb_each(coalesce({table}.{schema.REFUSAL_REASONS_COLUMN},
                                     '{{}}'::jsonb)) o
            FULL JOIN jsonb_each(EXCLUDED.{schema.REFUSAL_REASONS_COLUMN}) n
                   ON n.key = o.key
         ) merged)
        """

    def _advance_cursor(self, connection, source, translator_ver, cursor_value,
                        molecules, atoms, deduped, refused, incomplete, *, reasons,
                        enforce_translator_version=False):
        """Issue the cursor UPDATE on the caller's OPEN transaction. No commit.

        `reasons` is this batch's `{reason: molecules}` DELTA - never a running total,
        because the column accumulates in SQL. `{}` is the ordinary value for a clean
        batch and leaves the breakdown untouched, and it is REQUIRED for the reason
        `write_batch` states: this is the statement that writes `molecules_refused`, so
        this is where a count without names would actually be committed.
        """
        if reasons is None:
            raise TypeError(_REASONS_REQUIRED)
        version_guard = ""
        if enforce_translator_version:
            version_guard = (
                f" WHERE {schema.CURSOR_TABLE}.translator_ver = EXCLUDED.translator_ver"
                " RETURNING source")
        with connection.cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO {schema.CURSOR_TABLE} (
                    source, translator_ver, cursor_value, molecules_done, atoms_written,
                    atoms_deduped, molecules_refused, incomplete_molecules,
                    {schema.REFUSAL_REASONS_COLUMN}, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {self._SHAPE_REASONS}, now())
                ON CONFLICT (source) DO UPDATE SET
                    translator_ver       = EXCLUDED.translator_ver,
                    cursor_value         = EXCLUDED.cursor_value,
                    molecules_done       = {schema.CURSOR_TABLE}.molecules_done
                                           + EXCLUDED.molecules_done,
                    atoms_written        = {schema.CURSOR_TABLE}.atoms_written
                                           + EXCLUDED.atoms_written,
                    atoms_deduped        = {schema.CURSOR_TABLE}.atoms_deduped
                                           + EXCLUDED.atoms_deduped,
                    molecules_refused    = {schema.CURSOR_TABLE}.molecules_refused
                                           + EXCLUDED.molecules_refused,
                    incomplete_molecules = {schema.CURSOR_TABLE}.incomplete_molecules
                                           + EXCLUDED.incomplete_molecules,
                    {schema.REFUSAL_REASONS_COLUMN} = {self._merge_reasons_sql()},
                    updated_at           = now()
                {version_guard}
            """, (source, translator_ver, _json(cursor_value), molecules, atoms,
                  deduped, refused, incomplete, _json(dict(reasons))))
            if enforce_translator_version and cursor.fetchone() is None:
                raise CursorVersionConflict(
                    f"source {source!r} cursor belongs to a different "
                    "translator/setup snapshot; explicit replay/reset is required")

    def _record_refusals(self, connection, source, translator_ver, refused, reasons):
        """Charge this batch's refusals to the source's registry row. Caller's transaction.

        🔴 WHY IT IS A SEPARATE STATEMENT FROM `_advance_cursor` (S-113 ⓓ-2, ruling 221).
        The scoped door is the only door the live path uses, and it must not move the
        position - so the counters that describe HOW FAR THE FORWARD SCAN GOT are skipped
        with it. Refusals are not one of those: "this source refused two molecules for this
        reason" is true of the source, not of a position, and skipping it is why the number
        the refusal screen exists to show has been zero everywhere since S-76.

        ⛔ THE AGGREGATE RIDES WITH THE BREAKDOWN AND THAT IS NOT OPTIONAL. `schema.py`
        states it: the aggregate is the authority, the breakdown explains it, and one
        transaction is what stops the two from disagreeing. `ledger_trace._unaccounted`
        branches on the SIGN of `molecules_refused - sum(breakdown)`, and a negative one
        means "a real bookkeeping fault". Writing the names without the number would
        manufacture exactly that on every source that refuses anything - a status strip
        crying wolf about its own bookkeeping.

        ⚠️ AND IT CREATES THE ROW, for the same reason the census tick does (S-113 ⓑ-1):
        since S-76 nothing else does, so an `UPDATE` would land nowhere for a source
        declared today. `translator_ver` rides on the INSERT and is left alone on conflict -
        re-stamping is `restamp_cursor`'s decision (S-87), never a side effect of counting.
        """
        if reasons is None:
            raise TypeError(_REASONS_REQUIRED)
        if not refused and not reasons:
            # A clean batch has nothing to charge. Returning early rather than writing `{}`
            # keeps NULL meaning "never broken down" for a row no writer has owned - the
            # three-state distinction `ledger_admin` draws.
            return
        table = schema.CURSOR_TABLE
        with connection.cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO {table} (
                    source, translator_ver, cursor_value, molecules_refused,
                    {schema.REFUSAL_REASONS_COLUMN}, updated_at)
                VALUES (%s, %s, 'null'::jsonb, %s, {self._SHAPE_REASONS}, now())
                ON CONFLICT (source) DO UPDATE SET
                    molecules_refused = {table}.molecules_refused
                                        + EXCLUDED.molecules_refused,
                    {schema.REFUSAL_REASONS_COLUMN} = {self._merge_reasons_sql()},
                    updated_at        = now()
            """, (source, translator_ver, refused, _json(dict(reasons))))

    def write_batch(self, source, translator_ver, atoms, cursor_value, molecules,
                    refused=0, incomplete=0, *, reasons,
                    enforce_translator_version=False, advance_cursor=True,
                    withdraw_refs=None, row_refs=None, receipt=None):
        """🔴 The atomic unit. Atoms in, cursor forward, ONE commit, or nothing at all.

        🔴 `advance_cursor=False` IS THE SCOPED REDO, AND IT IS THIS SAME DOOR. Everything
        above the cursor statement runs unchanged - the same gate, the same translation, the
        same atoms table, the same one commit - and the cursor statement alone is skipped.
        So the position does not move forward, does not move BACK, and there is no window
        between two transactions in which it could be wrong. `ledger/runtime_v2.py`'s
        `execute_scoped_batch` is what passes it, and only for a batch it has PROVED lies
        inside a named scope; without that proof this flag would mean "write a whole source
        and leave no trace in the cursor", which is the second door the standing rule
        forbids.

        The counters do not move either, and that is the same fact rather than a second
        decision: they are columns of the cursor row and they describe how far the FORWARD
        SCAN has got. Redoing a part the scan already passed is not progress along it, so
        accumulating there would make `molecules_done` claim the source is further through
        than it is. What the scoped write did is returned to its caller, which reports it.

        🔴 `reasons` HAS NO DEFAULT, and that is ruling R-2026-08-13-H-bis 2. It used to
        default to `None`, which meant a caller who said nothing about refusals got the
        behaviour from before the breakdown column existed: `molecules_refused` advanced
        and the names beside it did not. That is R-D's decoy field wearing a function
        signature - a field whose absence is indistinguishable from its emptiness - and
        the sign contract downstream is built on the difference. `ledger_trace` reads
        `molecules_refused - sum(breakdown)` and branches on the SIGN: `> 0` means
        "counted before this column existed", i.e. DEPLOYMENT HISTORY, not a fault. A
        defaulted `reasons` manufactures that same positive number on a current build, so
        a real gap and an old one become one number and the operator is told a live
        bookkeeping hole is history. Keyword-only rather than merely undefaulted so it
        cannot be supplied positionally by accident either, and an explicit `None` is
        rejected below: the only legitimate empty breakdown is an explicit `{}` from a
        run that refused nothing.

        The counters are ACCUMULATED, not set. A field that is SET has been a defect in
        this system before (QA D-1: an override count under-reported because two messages
        for one transaction arrived and the last overwrote the first), and a backfill
        writes many batches for one cursor row, so accumulate is the only semantics that
        can be right here.

        `reasons` is the same batch's refusals BY NAME (`{reason: molecules}`) and it
        rides in the SAME statement as `refused`, which is the whole of ruling
        R-2026-08-13-F's mechanism: the aggregate is the authority, the breakdown
        explains it, and one transaction is what stops the two from ever disagreeing.
        `sum(reasons.values()) == refused` is the caller's contract and
        `test_ledger_l1_pg.py` pins it at write time from the other side (the database).
        """
        if reasons is None:
            # Checked BEFORE the connection is opened: refusing early costs nothing and
            # keeps the refusal about the CALL rather than about a half-built transaction.
            raise TypeError(_REASONS_REQUIRED)
        if enforce_translator_version and not advance_cursor:
            raise TypeError(_VERSION_GUARD_NEEDS_CURSOR)
        connection = self.connection()
        try:
            self.ensure_partitions(connection, {a.occurred_at for a in atoms})
            withdrawn = self._withdraw_refs(connection, source, withdraw_refs)
            attempted, inserted = self.insert_atoms(connection, atoms)
            self._write_row_refs(connection, source, row_refs)
            if advance_cursor:
                self._advance_cursor(connection, source, translator_ver, cursor_value,
                                     molecules, inserted, attempted - inserted,
                                     refused, incomplete, reasons=reasons,
                                     enforce_translator_version=enforce_translator_version)
            else:
                # 🔴 THE REFUSALS STILL LAND (S-113 ⓓ-2). Not the position, not the progress
                # counters - those describe the forward scan and this door is not it. See
                # `_record_refusals` for why the two halves separate exactly here.
                self._record_refusals(connection, source, translator_ver, refused, reasons)
            written = {"attempted": attempted, "inserted": inserted,
                       "deduped": attempted - inserted, "molecules": molecules,
                       "withdrawn": withdrawn}
            # 🔴 THE RECEIPT RIDES THE ATOMS' OWN COMMIT (S-117, 판정 248). A receipt
            # written after this transaction closes can be lost while the atoms stand,
            # and then the history says a batch never happened that did - which is the
            # single falsehood this record exists to prevent. It is NOT an atom and it
            # does not open a second door for one: `receipt` returns a row for a
            # DIFFERENT table, and the atom statement above is untouched.
            #
            # ⚠️ AND THE STORE DOES NOT DECIDE WHAT IT SAYS. The callable is handed the
            # counts this transaction just computed and returns the row; the one place
            # that decides what an audit row contains is `crud.create_audit_log`, which
            # is what the caller uses. A dict assembled here would be a second spelling
            # of that, free to drift the day a column is added.
            if receipt is not None:
                _insert_audit_row(connection, receipt(written))
            connection.commit()
            return written
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def plant_rows_indexed(self, source, counted):
        """Write the counted index size down. Returns what it REPLACED, if that differed.

        🔴 THE COUNTER IS PLANTED ONCE AND MAINTAINED (S-122-b, 판정 250), so this is called
        by whoever counted exactly: the tick the first time a source is seen, and every run
        of the human `census` command after that.

        ⚠️ IT RETURNS THE DIFFERENCE RATHER THAN SWALLOWING IT. Both seats that move this
        number are inside the atoms' own transaction, so a drift is not a rounding error -
        it means one of them was not reached, and a counter that silently corrects itself
        can never tell anybody that. `None` when there was nothing there or nothing changed.
        """
        connection = self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {schema.CURSOR_TABLE} "
                    f"   SET {schema.ROWS_INDEXED_COLUMN} = %s "
                    f" WHERE source = %s "
                    f"RETURNING (SELECT {schema.ROWS_INDEXED_COLUMN} "
                    f"             FROM {schema.CURSOR_TABLE} c2 WHERE c2.source = %s)",
                    (int(counted), source, source))
                row = cursor.fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        previous = None if row is None else row[0]
        return None if previous is None or int(previous) == int(counted) else int(previous)

    def _withdraw_refs(self, connection, source, refs):
        """Delete this source's atoms for `refs`, IN THE CALLER'S TRANSACTION. Returns how
        many.

        🔴 IT LIVES HERE BECAUSE THE COMMIT DOES. `backfill.rescope` used to issue this
        DELETE in a transaction of its own and commit it, then translate and write in a
        second one -- so a remake that failed for any reason left the withdrawal standing
        and the rows' atoms were GONE. Measured on 2026-09-08: two atoms of one `dt_job`
        (its `register` and its `has_netdie`) disappeared exactly that way. Two transactions
        cannot be made safe by ordering them differently either: doing the remake first
        collides with the atoms still present on `uq_ledger_atom`, so the write would dedupe
        to nothing and the delete would then take everything.

        One transaction is the whole fix, and the "history briefly holds two generations"
        objection does not arise: nothing outside this transaction can see between the two
        statements.

        `source_who` is in the predicate, so an atom another source wrote about the same
        subject cannot be reached from here however the refs were spelled.
        """
        if not refs:
            return 0
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {schema.LEDGER_TABLE} "
                "WHERE source_who = %s AND source_raw_ref = ANY(%s)",
                (source, list(refs)))
            return int(cursor.rowcount or 0)

    def _write_row_refs(self, connection, source, refs):
        """Record which physical row each `source_raw_ref` was built from. Caller's
        transaction.

        🔴 THE SAME COMMIT AS THE ATOMS, AND THAT IS THE WHOLE ANSWER TO "CAN THIS INDEX GO
        STALE". An atom that exists while its index row does not is not a state that has to
        be repaired later -- it is a state that cannot be reached, because one transaction
        writes both or neither. The write door is `runtime_v2`, singular, so there is no
        second producer to disagree.

        Upsert rather than insert: re-translating a row (a rescope) writes the same pair
        again, and the ref may have MOVED if the row's `order_by` values changed -- which is
        precisely the correction a rescope exists for, so the newest translation wins.
        """
        if not refs:
            return 0
        from psycopg2.extras import execute_values

        rows = [(str(relation), str(row_id), source, str(ref))
                for relation, row_id, ref in refs]
        touched: dict = {}
        for relation, row_id, _source, _ref in rows:
            touched.setdefault(relation, set()).add(row_id)
        gained = 0
        with connection.cursor() as cursor:
            # 🔴 WHICH OF THESE ROWS IS NEW TO THE INDEX (S-122-b). The counter this feeds
            # is DISTINCT ROWS, so what it wants is the rows gaining their FIRST line -
            # not the number of lines written, which counts a row twice when a source says
            # two things about it. Asked BEFORE the delete below, over the named ids only,
            # so it is an index lookup of at most one page's worth and never a scan.
            for relation, row_ids in sorted(touched.items()):
                cursor.execute(
                    f"SELECT count(DISTINCT row_id) FROM {schema.ROW_REF_TABLE} "
                    " WHERE relation = %s AND source_who = %s AND row_id = ANY(%s)",
                    (relation, source, sorted(row_ids)))
                gained += len(row_ids) - int(cursor.fetchone()[0] or 0)
            # 🔴 THIS SOURCE'S LINES FOR THESE ROWS ARE REPLACED, NOT MERGED. A
            # re-translation may name the same row under a DIFFERENT claim ref -- a
            # corrected `order_by` value moves it, which is what a rescope exists for --
            # and the old line would then point at an atom the same transaction just
            # withdrew. Same commit, so the index cannot be seen mid-replacement.
            for relation, row_ids in sorted(touched.items()):
                cursor.execute(
                    f"DELETE FROM {schema.ROW_REF_TABLE} "
                    "WHERE relation = %s AND source_who = %s AND row_id = ANY(%s)",
                    (relation, source, sorted(row_ids)))
            execute_values(
                cursor,
                f"INSERT INTO {schema.ROW_REF_TABLE} "
                "(relation, row_id, source_who, source_raw_ref) VALUES %s "
                "ON CONFLICT DO NOTHING",
                rows)
            # ⚠️ ONLY WHERE THE SOURCE HAS ALREADY BEEN COUNTED. `NULL` means 「never
            # planted」, and `NULL + 3` is NULL in SQL - which would be the right answer by
            # accident. It is written explicitly so nobody later "fixes" it with COALESCE
            # and turns an unplanted source into one that claims three rows.
            if gained:
                cursor.execute(
                    f"UPDATE {schema.CURSOR_TABLE} "
                    f"   SET {schema.ROWS_INDEXED_COLUMN} = "
                    f"       {schema.ROWS_INDEXED_COLUMN} + %s "
                    f" WHERE source = %s AND {schema.ROWS_INDEXED_COLUMN} IS NOT NULL",
                    (gained, source))
            return len(rows)

    def withdraw(self, source, refs):
        """Withdraw one source's atoms for `refs`, in a transaction of its own.

        🔴 THE STANDALONE HALF, AND IT IS THE SAME STATEMENT. `write_batch` runs the
        withdrawal inside the commit that writes the replacement, because there IS one; a
        deleted physical row has no replacement, so there is nothing to be atomic with. Both
        entries go through `_withdraw_refs` so the predicate -- `source_who` included --
        cannot come to be spelled two ways.
        """
        if not refs:
            return 0
        connection = self.connection()
        try:
            removed = self._withdraw_refs(connection, source, refs)
            connection.commit()
            return removed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def row_refs_for(self, relation, row_ids, connection=None):
        """`[(source_who, source_raw_ref)]` for rows of `relation`. READ ONLY.

        The answer to "what did the ledger say about these rows", and the only way to ask it
        once they are gone: their translation goes with them.

        🔴 AND ALSO WHAT A RESCOPE AIMS WITH (S-101). A row that is still there but no longer
        translates -- excluded by `exclude_when`, or edited until its identity is blank --
        produces no ref either, so a withdrawal aimed at the current translation has nothing
        to aim with in exactly the case where the old atoms must go. Both callers therefore
        read the note taken while the row still spoke, rather than asking the row again.
        """
        if not row_ids:
            return []
        own = connection is None
        connection = connection or self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT source_who, source_raw_ref FROM {schema.ROW_REF_TABLE} "
                    "WHERE relation = %s AND row_id = ANY(%s)",
                    (str(relation), [str(item) for item in row_ids]))
                return [(row[0], row[1]) for row in cursor.fetchall()]
        finally:
            if own:
                connection.close()

    def indexed_row_ids(self, relation, row_ids, source, connection=None):
        """Which of `row_ids` this source's index already names. READ ONLY.

        ⚠️ ROWS, WHICH `row_refs_for` CANNOT SAY. That one answers with `(source, ref)` pairs
        and one row appears under SEVERAL refs, so counting its answer counts pairs -- the
        exact confusion `rows_not_yet_translated` had to fix with `count(DISTINCT row_id)`
        after it went negative on a source with two sentences.
        """
        if not row_ids:
            return set()
        own = connection is None
        connection = connection or self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT DISTINCT row_id FROM {schema.ROW_REF_TABLE} "
                    "WHERE relation = %s AND source_who = %s AND row_id = ANY(%s)",
                    (str(relation), str(source),
                     [str(item) for item in row_ids]))
                return {row[0] for row in cursor.fetchall()}
        finally:
            if own:
                connection.close()

    def forget_row_refs(self, relation, row_ids, connection=None, source=None):
        """Drop the index rows for physical rows the ledger no longer speaks for. How many.

        Last, not first: while these are still here the withdrawal can be run again, and a
        run that died between the two leaves an index row pointing at atoms that are already
        withdrawn -- which the next pass reads as "nothing to withdraw" and clears.

        🔴 `source` NAMES ONE SPEAKER, AND OMITTING IT MEANS ALL OF THEM. The two callers ask
        different questions and the predicate has to follow: a DELETED row is gone for
        everybody, so every source's line about it is stale; a row a rescope no longer
        translates is STILL THERE, and another source reading the same relation still speaks
        for it. Dropping that other source's line would leave an atom whose index row does
        not exist -- the one state `_write_row_refs` says one transaction makes unreachable,
        recreated here by a wider DELETE. One statement either way, so the two cannot come
        to be spelled differently.
        """
        if not row_ids:
            return 0
        own = connection is None
        connection = connection or self.connection()
        wanted = [str(item) for item in row_ids]
        try:
            with connection.cursor() as cursor:
                # 🔴 WHICH SOURCES LOSE WHICH ROWS, BEFORE THE DELETE (S-122-b). The
                # counter holds DISTINCT ROWS, so the decrement is "rows losing their LAST
                # line" - and with `source=None` this statement speaks for every source at
                # once, so the answer has to be grouped rather than a single number. Asked
                # over the named ids only: an index lookup, never a scan.
                if source is None:
                    cursor.execute(
                        f"SELECT source_who, count(DISTINCT row_id) "
                        f"  FROM {schema.ROW_REF_TABLE} "
                        " WHERE relation = %s AND row_id = ANY(%s) "
                        " GROUP BY source_who", (str(relation), wanted))
                else:
                    cursor.execute(
                        f"SELECT source_who, count(DISTINCT row_id) "
                        f"  FROM {schema.ROW_REF_TABLE} "
                        " WHERE relation = %s AND source_who = %s AND row_id = ANY(%s) "
                        " GROUP BY source_who",
                        (str(relation), str(source), wanted))
                losing = cursor.fetchall()

                if source is None:
                    cursor.execute(
                        f"DELETE FROM {schema.ROW_REF_TABLE} "
                        "WHERE relation = %s AND row_id = ANY(%s)",
                        (str(relation), wanted))
                else:
                    cursor.execute(
                        f"DELETE FROM {schema.ROW_REF_TABLE} "
                        "WHERE relation = %s AND source_who = %s AND row_id = ANY(%s)",
                        (str(relation), str(source), wanted))
                removed = int(cursor.rowcount or 0)
                # Same statement's transaction, so the index and the count cannot be seen
                # disagreeing - and `IS NOT NULL` keeps an unplanted source unplanted.
                for who, rows_lost in losing:
                    if rows_lost:
                        cursor.execute(
                            f"UPDATE {schema.CURSOR_TABLE} "
                            f"   SET {schema.ROWS_INDEXED_COLUMN} = "
                            f"       GREATEST({schema.ROWS_INDEXED_COLUMN} - %s, 0) "
                            f" WHERE source = %s "
                            f"   AND {schema.ROWS_INDEXED_COLUMN} IS NOT NULL",
                            (int(rows_lost), who))
            if own:
                connection.commit()
            return removed
        except Exception:
            if own:
                connection.rollback()
            raise
        finally:
            if own:
                connection.close()

    @staticmethod
    def restamp_decision(stored, wanted):
        """May this cursor's fingerprint string be moved, and why. ONE spelling (S-87).

        Returns `("restamp"|"already"|"absent"|"refused", <reason or None>)`. The script and
        the boot step both ask THIS, rather than each carrying an if-chain: two spellings of
        「may it be moved」 is how one of them comes to move a cursor the other would refuse.

        \u26d4 A v1-SHAPED CURSOR IS REFUSED BY NAME. Re-stamping it would hide its own gate
        (`legacy_cursor_reset_required`, which reads `cursor_value`'s SHAPE) behind a
        v2-looking string while the position stayed v1-shaped.
        """
        if stored is None:
            return "absent", "no cursor row yet -- a first run writes the current string"
        if stored == wanted:
            return "already", None
        if not str(stored or "").startswith("ledger-v2:"):
            return "refused", (f"stored cursor is not a v2 cursor ({stored!r}); its shape "
                               f"gate is a separate decision")
        return "restamp", None

    def restamp_cursor(self, source, *, expect, translator_ver):
        """Swap ONE cursor's fingerprint string. Reads no source row, moves no position.

        🔴 THIS IS NOT A RESET, AND THE DIFFERENCE IS THE WHOLE SAFETY ARGUMENT.
        `source_translator_ver` is part of `uq_ledger_atom` (`schema.py:60`), so a cursor
        that is deleted and recreated - or rewound - re-reads rows that are already in the
        ledger, and those re-read rows land AGAIN under the new fingerprint instead of
        deduping against the old ones. On a ledger of millions of rows that doubles it.

        So this statement touches `translator_ver` and NOTHING else: not `cursor_value`,
        not the counters, not the atoms. The next batch reads rows AFTER the unchanged
        position, which are facts arriving in the ledger for the first time and have no old
        row to collide with. Past atoms keep the fingerprint they were written under,
        because a ledger appends (owner, 2026-08-21: 「그냥 예전 것도 계속 append 하는 게
        원장이니 갈아치우는 건 아니지」).

        `expect` is required and is matched in the WHERE clause: a re-stamp is only ever
        correct as "this exact old string becomes this exact new one", and matching it in
        SQL is what makes a second run a no-op instead of a silent overwrite of whatever a
        concurrent writer left there. Returns True when one row moved, False when none did.
        """
        if not isinstance(expect, str) or not expect:
            raise ValueError("expect must be the exact stored translator_ver string")
        if not isinstance(translator_ver, str) or not translator_ver:
            raise ValueError("translator_ver must be a non-empty string")
        connection = self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {schema.CURSOR_TABLE} SET translator_ver = %s "
                    f"WHERE source = %s AND translator_ver = %s RETURNING source",
                    (translator_ver, source, expect))
                moved = cursor.fetchone() is not None
            connection.commit()
            return moved
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # -------------------------------------------------------------------- observation
    def atom_count(self, connection=None):
        own = connection is None
        connection = connection or self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {schema.LEDGER_TABLE}")
                return cursor.fetchone()[0]
        finally:
            if own:
                connection.close()

    def census(self, connection=None):
        """`{predicate: count}`. The number the report quotes and the backfill logs."""
        own = connection is None
        connection = connection or self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT predicate, count(*) FROM {schema.LEDGER_TABLE} "
                    f"GROUP BY 1 ORDER BY 1")
                return dict(cursor.fetchall())
        finally:
            if own:
                connection.close()

    def record_source_head(self, source, head_value):
        """Store the last observed source head. Its own tiny transaction on purpose -
        a lag probe must never be able to roll back a batch of atoms."""
        connection = self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {schema.CURSOR_TABLE} SET source_head = %s, "
                    f"head_probed_at = now() WHERE source = %s",
                    (_json(head_value), source))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


@lru_cache(maxsize=32)
def _candidate_formats(fmt: str):
    """The shapes `parse_occurred_at` will read for one DECLARED format.

    Two widenings, and only two. Both are stated here rather than spread across the
    reader so that "what this accepts" is one list somebody can read.

    ① THE DATE/TIME SEPARATOR IS TRANSPORT, NOT MEANING.
       Production emits `2026-08-13T13:45:00`; the trace fixture and the mirrored
       `lot_event` table on a development box hold `2026-08-13 13:45:00`, and that space
       is deliberate (`table_config.json` keeps the column TEXT so it sorts
       lexicographically). RFC 3339 §5.6 permits the space in place of the `T` by
       agreement, and this system is on both sides of that agreement. 🔴 Admitting both
       spellings of ONE declared shape is not guessing: no string is readable two ways
       under this list, so no string can be given two different instants. A shape the
       declaration did not name is still refused - this widens the SEPARATOR, not the
       grammar.

    ② A TRAILING OFFSET IS ADMITTED SO THAT IT CAN BE HONOURED.
       `%z` is not optional in `strptime`, so a shape carrying it and the same shape
       without it are DISJOINT - exactly one of the pair can match any given string.
       That is what keeps this a lookup and not a preference order. `%z` reads `+09:00`,
       `+0900` and `Z`.

    Ordered so the declared spelling costs exactly ONE `strptime` on the hot path; a
    ten-million row backfill pays for an alternative only on a row that needs it.
    Memoised on the format string because the candidate list is a pure function of it
    and rebuilding it per row would be the per-access-config defect in miniature.
    """
    shapes = [fmt]
    for declared, sibling in (("T%H", " %H"), (" %H", "T%H")):
        if declared in fmt:
            shapes.append(fmt.replace(declared, sibling, 1))
            break
    return tuple(shapes) + tuple(shape + "%z" for shape in shapes)


def parse_occurred_at(raw, fmt: str, tzname: str):
    """Source text -> an aware datetime, or `None` if it cannot be parsed.

    `None` is a REFUSAL signal for the caller, never a licence to substitute `now()`.
    That substitution is risk 2 of the brief and it is the kind of defect that never
    announces itself: every atom looks well formed and the ordering of history is wrong.

    🔴 AN EXPLICIT OFFSET IN THE SOURCE WINS; THE DECLARED ZONE IS APPLIED ONLY TO A
    NAIVE VALUE.
    `occurred_at_timezone` declares what a source's NAIVE text means. A string that
    carries its own offset has already said which instant it is, and there are exactly
    two ways to write the alternative, both of which pass a spot check:
      * re-localising it (`replace(tzinfo=...)`) keeps the wall clock and throws the
        offset away - a silent 9-hour shift on every atom that carried one;
      * converting it (`astimezone(...)`) is a no-op on the instant, which merely hides
        that the declaration was consulted at all.
    So the rule is decided once, here. It is not a new rule: this is what the module has
    always done for a `datetime` input (the branch immediately below), now extended to
    text so there is ONE rule rather than one per input type.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=_zone(tzname))
    text = str(raw).strip()
    if not text:
        return None
    for candidate in _candidate_formats(fmt):
        try:
            parsed = datetime.strptime(text, candidate)
        except (ValueError, TypeError):
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=_zone(tzname))
    return None


def _zone(tzname: str):
    if not tzname or tzname.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tzname)
    except Exception as exc:                                      # pragma: no cover
        raise ValueError(
            f"ledger_config declares timezone {tzname!r}, which this interpreter cannot "
            f"resolve ({exc}). The translator refuses rather than fall back to UTC - a "
            f"silent fallback would shift every occurred_at by the offset.") from exc
