# -*- coding: utf-8 -*-
"""The database refused the atom the translator had just learned to build.

S-52-h. `ck_ledger_objectless_has_no_payload` said `object_kind IS NOT NULL OR
object_payload IS NULL` -- an atom with no object carries no payload. Since S-52 a
`register` atom carries its subject's declared attributes in `object_payload.qualifiers`,
which `envelope.registration_fingerprint` reads and the walk turns into a node's columns. So
`rescope --apply` died on the CHECK, on the parent and on every partition, and the shipped
sample's own declaration could not be written at all.

🔴 THE RULE IS STILL A RULE, WHICH IS WHY THIS FILE SCORES THE REFUSALS TOO. What may ride
in an objectless payload is `qualifiers` and nothing else: an objectless atom carrying a
`value` is an object wearing no name. A migration that simply dropped the constraint would
pass a test that only checked the new shape goes in.

⚠️ REAL POSTGRES, because a CHECK constraint is not a Python judgement -- it either accepts
the bytes or it does not. Skipped where no database is declared, like every other `pg_engine`
test here.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import schema                                            # noqa: E402

OCCURRED_AT = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)

RETIRED_DDL = (f"ALTER TABLE {schema.LEDGER_TABLE} ADD CONSTRAINT "
               f"{schema.RETIRED_OBJECTLESS_CONSTRAINT} CHECK "
               f"(object_kind IS NOT NULL OR object_payload IS NULL)")


# ------------------------------------------ what the migration DOES, with no server at all

class SpyCursor:
    """A cursor that answers the catalogue and records the DDL, and nothing else."""

    def __init__(self, present):
        self.present = set(present)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if sql.startswith("SELECT 1 FROM pg_constraint"):
            self.answer = params[1] in self.present
            return
        self.statements.append(" ".join(sql.split()))

    def fetchone(self):
        return (1,) if self.answer else None


def migrate(present):
    cursor = SpyCursor(present)
    changed = schema.ensure_objectless_payload_constraint(cursor)
    return changed, cursor.statements


def test_an_up_to_date_install_issues_no_ddl_at_all():
    """🔴 THIS RUNS AT THE START OF EVERY BACKFILL. `ADD CONSTRAINT IF NOT EXISTS` does not
    exist for CHECKs, and an ALTER that decides it has nothing to do still takes ACCESS
    EXCLUSIVE on the parent and every partition -- which is the lock the partition-creation
    comment in this module already records wedging a run. So the catalogue is asked first
    and nothing is issued."""
    changed, statements = migrate({schema.OBJECTLESS_PAYLOAD_CONSTRAINT})
    assert changed is False and statements == []


def test_an_install_that_predates_attributes_drops_then_adds():
    """The order is the safety: both are catalogue-only and both ride in the caller's
    transaction, so the table never carries neither rule."""
    changed, statements = migrate({schema.RETIRED_OBJECTLESS_CONSTRAINT})
    assert changed is True and len(statements) == 2
    assert statements[0] == (f"ALTER TABLE {schema.LEDGER_TABLE} DROP CONSTRAINT "
                             f"{schema.RETIRED_OBJECTLESS_CONSTRAINT}")
    assert statements[1].startswith(
        f"ALTER TABLE {schema.LEDGER_TABLE} ADD CONSTRAINT "
        f"{schema.OBJECTLESS_PAYLOAD_CONSTRAINT} CHECK ")
    assert statements[1].endswith("NOT VALID"), (
        "the migration must not take a scan of the ledger at backfill start")


def test_a_table_carrying_neither_rule_is_given_the_new_one():
    """A DROP of a constraint that is not there aborts the transaction and every statement
    after it fails for an unrelated reason -- this module's standing rule."""
    changed, statements = migrate(set())
    assert changed is True and len(statements) == 1
    assert "ADD CONSTRAINT" in statements[0]


def test_the_alter_and_the_create_carry_one_body():
    """🔴 THE `uq_ledger_atom` LESSON, ENFORCED. A fresh install gets this rule from
    `CREATE_LEDGER` and an upgraded one from the ALTER; when those two bodies drift, the
    two boxes enforce different rules and neither errors."""
    _, statements = migrate({schema.RETIRED_OBJECTLESS_CONSTRAINT})
    body = " ".join(schema.OBJECTLESS_PAYLOAD_CHECK.split())
    assert body in statements[0] or body in statements[1]
    assert body in " ".join(schema.CREATE_LEDGER.split())
    # ⚠️ AND THE BODY IS STILL THE WIDENED ONE. This much is a literal, said out loud: what
    # the rule MEANS is decided by PostgreSQL and is scored below, where a database is
    # declared. Without this line a revert to `object_kind IS NOT NULL OR object_payload IS
    # NULL` would keep every assertion above green -- they compare the constant with itself.
    assert "'qualifiers'" in body and "object_payload IS NULL" in body


# ------------------------------------------- and what the CONSTRAINT means, against Postgres

@pytest.fixture
def ledger(pg_engine):
    """A real `ledger_events` in the scratch schema, with one partition to write into."""
    connection = pg_engine.raw_connection()
    try:
        schema.ensure_schema(connection)
        schema.ensure_partition(connection, OCCURRED_AT)
        yield connection
    finally:
        connection.close()


def insert(connection, object_kind, object_payload, predicate="register"):
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {schema.LEDGER_TABLE} "
            "(id, subject_type, subject_keys, predicate, object_kind, object_payload,"
            " occurred_at, source_who, source_translator_ver, source_raw_ref,"
            " source_event_id, source_event_state) "
            "VALUES (%s, 'dtjob@1', '{\"dt_job\": \"J1\"}'::jsonb, %s, %s, %s::jsonb,"
            " %s, 'dt_job', 'v1', 'raw-1', %s, 'source_molecule')",
            (str(uuid.uuid4()), predicate, object_kind, object_payload,
             OCCURRED_AT, str(uuid.uuid4())))
    connection.commit()


def refused(connection, object_kind, object_payload, predicate="register"):
    with pytest.raises(Exception) as caught:
        insert(connection, object_kind, object_payload, predicate)
    connection.rollback()
    return str(caught.value)


# ------------------------------------------------------------------ what may now be written

def test_a_registration_carrying_its_attributes_is_accepted(ledger):
    """🔴 THE GATE. This is byte for byte the atom `roleframe.compile_role_frame` builds for
    the shipped sample's `dtjob@1.attributes: ["dt_eqp"]`, and the old rule refused it."""
    insert(ledger, None, '{"qualifiers": {"dt_eqp": "EQP-7"}}')
    with ledger.cursor() as cursor:
        cursor.execute(f"SELECT object_payload FROM {schema.LEDGER_TABLE} "
                       "WHERE source_raw_ref = 'raw-1'")
        assert cursor.fetchone()[0] == {"qualifiers": {"dt_eqp": "EQP-7"}}


def test_a_registration_with_nothing_to_say_is_still_a_null_payload(ledger):
    """⚠️ THE OTHER HALF OF 「바이트 동일」. Widening the rule must not turn the empty case
    into `{}` -- `registration_fingerprint` reads the empty string off a NULL payload, and
    that is what keeps "no attributes" and "this axis did not exist" the same atom."""
    insert(ledger, None, None)
    with ledger.cursor() as cursor:
        cursor.execute(f"SELECT object_payload FROM {schema.LEDGER_TABLE} "
                       "WHERE source_raw_ref = 'raw-1'")
        assert cursor.fetchone()[0] is None


# --------------------------------------------------------------- and what still may not be

@pytest.mark.parametrize("payload", [
    '{"value": 1}',
    '{"qualifiers": {"dt_eqp": "EQP-7"}, "value": 1}',
    '{"type": "dtjob@1", "keys": {"dt_job": "J1"}}',
    '{}',
    '[]',
    '"qualifiers"',
])
def test_an_objectless_payload_that_is_not_only_qualifiers_is_refused(ledger, payload):
    """⛔ THE RULE DID NOT GO AWAY. An objectless atom carrying anything but `qualifiers` is
    an object with no name on it, and a migration that merely dropped the constraint would
    let every one of these through while the accepted case above still passed."""
    assert schema.OBJECTLESS_PAYLOAD_CONSTRAINT in refused(ledger, None, payload)


# ------------------------------------------------------------------------- the migration

def test_an_install_that_predates_attributes_is_widened_once(ledger):
    """🔴 THE UPGRADE PATH, DRIVEN BACKWARDS. The scratch table is put back to the narrow
    rule and `ensure_schema`'s migration is asked to fix it -- which is what an existing
    deployment does on its next backfill.

    Idempotence is scored too: the second call must issue no DDL at all, because this runs
    at the start of every run and an ALTER that decides it has nothing to do still takes
    ACCESS EXCLUSIVE."""
    with ledger.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {schema.LEDGER_TABLE} DROP CONSTRAINT "
                       f"{schema.OBJECTLESS_PAYLOAD_CONSTRAINT}")
        cursor.execute(RETIRED_DDL)
    ledger.commit()
    assert refused(ledger, None, '{"qualifiers": {"dt_eqp": "EQP-7"}}')

    with ledger.cursor() as cursor:
        assert schema.ensure_objectless_payload_constraint(cursor) is True
    ledger.commit()
    insert(ledger, None, '{"qualifiers": {"dt_eqp": "EQP-7"}}')

    with ledger.cursor() as cursor:
        assert schema.ensure_objectless_payload_constraint(cursor) is False, (
            "a second pass must ask the catalogue and issue nothing")


def test_the_widened_rule_reaches_every_partition(ledger):
    """🔴 THE PARENT IS NOT WHERE THE ROWS ARE. Measured rather than assumed: `ADD
    CONSTRAINT ... NOT VALID` on a partitioned parent recurses, so the constraint has to be
    on the partition too -- an INSERT lands there, and a rule that stopped at the parent
    would be a rule on an empty table."""
    partition = schema.partition_name(OCCURRED_AT)
    with ledger.cursor() as cursor:
        assert schema.constraint_exists(cursor, partition,
                                        schema.OBJECTLESS_PAYLOAD_CONSTRAINT)
        assert not schema.constraint_exists(cursor, partition,
                                            schema.RETIRED_OBJECTLESS_CONSTRAINT)
