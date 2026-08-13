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

from . import schema
from .envelope import ROW_COLUMNS

logger = logging.getLogger("Ledger.Store")

INSERT_PAGE_SIZE = 1000


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
            rows.append((
                str(atom.id), atom.subject_type, _json(atom.subject_keys),
                atom.predicate, atom.object_kind,
                None if atom.object_payload is None else _json(atom.object_payload),
                atom.occurred_at, atom.source_who, atom.source_translator_ver,
                atom.source_raw_ref,
                str(atom.supersedes) if atom.supersedes else None,
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
                f"       source_head, head_probed_at, updated_at "
                f"FROM {schema.CURSOR_TABLE} WHERE source = %s", (source,))
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "source": source, "translator_ver": row[0], "cursor_value": row[1],
            "molecules_done": row[2], "atoms_written": row[3], "atoms_deduped": row[4],
            "molecules_refused": row[5], "incomplete_molecules": row[6],
            "source_head": row[7], "head_probed_at": row[8], "updated_at": row[9],
        }

    def _advance_cursor(self, connection, source, translator_ver, cursor_value,
                        molecules, atoms, deduped, refused, incomplete):
        """Issue the cursor UPDATE on the caller's OPEN transaction. No commit."""
        with connection.cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO {schema.CURSOR_TABLE} (
                    source, translator_ver, cursor_value, molecules_done, atoms_written,
                    atoms_deduped, molecules_refused, incomplete_molecules, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
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
                    updated_at           = now()
            """, (source, translator_ver, _json(cursor_value), molecules, atoms,
                  deduped, refused, incomplete))

    def write_batch(self, source, translator_ver, atoms, cursor_value, molecules,
                    refused=0, incomplete=0):
        """🔴 The atomic unit. Atoms in, cursor forward, ONE commit, or nothing at all.

        The counters are ACCUMULATED, not set. A field that is SET has been a defect in
        this system before (QA D-1: an override count under-reported because two messages
        for one transaction arrived and the last overwrote the first), and a backfill
        writes many batches for one cursor row, so accumulate is the only semantics that
        can be right here.
        """
        connection = self.connection()
        try:
            self.ensure_partitions(connection, {a.occurred_at for a in atoms})
            attempted, inserted = self.insert_atoms(connection, atoms)
            self._advance_cursor(connection, source, translator_ver, cursor_value,
                                 molecules, inserted, attempted - inserted,
                                 refused, incomplete)
            connection.commit()
            return {"attempted": attempted, "inserted": inserted,
                    "deduped": attempted - inserted, "molecules": molecules}
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


def parse_occurred_at(raw, fmt: str, tzname: str):
    """Source text -> an aware datetime, or `None` if it cannot be parsed.

    `None` is a REFUSAL signal for the caller, never a licence to substitute `now()`.
    That substitution is risk 2 of the brief and it is the kind of defect that never
    announces itself: every atom looks well formed and the ordering of history is wrong.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=_zone(tzname))
    text = str(raw).strip()
    if not text:
        return None
    try:
        naive = datetime.strptime(text, fmt)
    except (ValueError, TypeError):
        return None
    return naive.replace(tzinfo=_zone(tzname))


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
