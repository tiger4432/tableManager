"""Remove a fixture's own atoms from the ledger, by source and translator prefix.

🔴 WHY THIS IS A MODULE AND NOT A BLOCK INSIDE A SEED (ruling 186). The ledger and the
outbox are not the product door's tables, so a script that writes them belongs to the
`migrate_`/`ops_` class - and that class is declared by the FILE NAME, which a block
inside `seed_syn_complex_composite.py` cannot claim. Extracting it lets the convention
hold as written: the seed keeps zero raw ledger writes, this file says what it is, and
there is one mechanism rather than two spellings of the same delete.

🔴 WHY IT IS A DELETE AND NOT A WITHDRAWAL. `store.withdraw` retires atoms whose SOURCE ROW
is gone, which is a true statement about the world. These atoms are different: a fixture is
being removed from a box entirely, source rows and all, and the honest description is that
this run never happened. That is a maintenance operation on the store rather than a fact
about the domain, which is exactly what puts this file in the ops class instead of behind
the door.

⚠️ IT REFUSES ANY DATABASE IT DOES NOT KNOW. The check moved here with the code; a
namespace delete pointed at the wrong database is not recoverable by anything this module
could offer afterwards.
"""
from __future__ import annotations

ALLOWED_DATABASES = frozenset({"assy_manager", "assy_qa"})


def refuse_unknown_database(connection):
    """Raise unless this connection is one of the boxes a fixture may be cleared from."""
    from sqlalchemy import text

    database = connection.execute(text("SELECT current_database()")).scalar()
    if database not in ALLOWED_DATABASES:
        raise SystemExit("REFUSED ledger namespace clear on database %r" % database)
    return database


def clear_source(connection, source, translator_prefix):
    """Delete one source's atoms and its cursor. Returns the atom count removed.

    `translator_prefix` narrows the atoms to the ones this fixture's translator wrote, so a
    source shared with anything else keeps the rest of its atoms.
    """
    from sqlalchemy import text

    refuse_unknown_database(connection)
    deleted = connection.execute(text(
        "DELETE FROM ledger_events WHERE source_who = :source "
        "AND source_translator_ver LIKE :translator"),
        {"source": source, "translator": translator_prefix + "%"}).rowcount
    connection.execute(text(
        "DELETE FROM ledger_translator_cursor WHERE source = :source"),
        {"source": source})
    return deleted


def clear_layer_rows(connection, updated_by):
    """Remove the cell-layer records one writer left, by its `updated_by` name.

    🔴 SEPARATE FROM THE DOOR'S OWN LAYER CLEANUP, AND NOT A DUPLICATE OF IT.
    `crud.delete_rows_batch` clears the layers belonging to the ROWS it deletes; this
    clears layers keyed on a WRITER, which outlives any particular row and is how a
    fixture's generic writes are attributed. A row deleted through the door takes its
    layers with it; a layer record whose row was never this fixture's does not.
    """
    from sqlalchemy import text

    refuse_unknown_database(connection)
    return connection.execute(text(
        "DELETE FROM cell_sources WHERE updated_by = :updated_by"),
        {"updated_by": updated_by}).rowcount
