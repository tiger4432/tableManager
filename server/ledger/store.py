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

    def write_row_census(self, source: str, census) -> None:
        """Store one source's 「table rows · indexed rows · remainder」 measurement.

        ⛔ IT DOES NOT CREATE THE ROW. A source with no cursor row has never been set up,
        and inserting one here would put a census beside a translator version that does
        not exist -- a source that looks measured and has never run. The UPDATE simply
        matches nothing, which is the honest outcome.
        """
        import json as _json

        connection = self.connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {schema.CURSOR_TABLE} "
                    f"   SET {schema.ROW_CENSUS_COLUMN} = %s::jsonb "
                    f" WHERE source = %s", (_json.dumps(census), source))
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

    def write_batch(self, source, translator_ver, atoms, cursor_value, molecules,
                    refused=0, incomplete=0, *, reasons,
                    enforce_translator_version=False, advance_cursor=True,
                    withdraw_refs=None, row_refs=None):
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
            connection.commit()
            return {"attempted": attempted, "inserted": inserted,
                    "deduped": attempted - inserted, "molecules": molecules,
                    "withdrawn": withdrawn}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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
        with connection.cursor() as cursor:
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
        try:
            with connection.cursor() as cursor:
                if source is None:
                    cursor.execute(
                        f"DELETE FROM {schema.ROW_REF_TABLE} "
                        "WHERE relation = %s AND row_id = ANY(%s)",
                        (str(relation), [str(item) for item in row_ids]))
                else:
                    cursor.execute(
                        f"DELETE FROM {schema.ROW_REF_TABLE} "
                        "WHERE relation = %s AND source_who = %s AND row_id = ANY(%s)",
                        (str(relation), str(source),
                         [str(item) for item in row_ids]))
                removed = int(cursor.rowcount or 0)
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
