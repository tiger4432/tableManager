# -*- coding: utf-8 -*-
"""S-77 (판정 169). A domain word had been compiled into a DB CHECK.

    CHECK ((predicate = 'register') = (object_kind IS NULL))

🔴 THE STORAGE LAYER IS THE ONE PLACE A DECLARATION CANNOT REACH. 「코드에 도메인 낱말이
«없다»」 is an architecture rule and not a style one, and this constraint is why: which
predicates carry no object is a DECLARED fact (`object.kind: none`), and `roleframe` already
refuses an emission whose object kind disagrees with its vocabulary signature -- in both
directions, naming the config path an author can go and edit.

🔴 AND IT WAS NARROWER THAN THE DECLARATION, WHICH IS WHAT MADE IT A DEFECT RATHER THAN
REDUNDANCY. Declare a SECOND objectless predicate (`retire@1`) and the atom compiles, emits,
passes every Python check, and is then refused BY THE DATABASE -- three layers from the line
the operator wrote, with a message naming neither the declaration nor the field.

⚠️ WHAT STAYS, AND THE TEST FOR WHY. `ck_ledger_objectless_carries_only_qualifiers` names no
predicate and owes nothing to any vocabulary, so it is true whatever a declaration says.
That is the whole admission rule for this layer, and it is asserted below rather than
described: a round that removed both would have left objectless atoms unconstrained.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import schema                                            # noqa: E402


def test_the_create_statement_names_no_predicate():
    """⛔ NOT 「the constant is gone」 -- the DDL is what a fresh install actually gets."""
    assert "ck_ledger_register_has_no_object" not in schema.CREATE_LEDGER
    assert "'register'" not in schema.CREATE_LEDGER


def test_no_domain_word_is_compiled_into_any_check():
    """The CLASS, not the instance. `register` was one word; the rule is that the storage
    layer names no predicate, entity type or source at all."""
    ddl = schema.CREATE_LEDGER
    for word in ("register", "retire", "observed", "inspected", "bonded_from",
                 "void", "defect", "wafer", "lot"):
        assert f"'{word}'" not in ddl, f"{word!r} is a domain word in the storage layer"


def test_the_structural_invariant_stays():
    """⚠️ REMOVING BOTH WOULD LEAVE AN OBJECTLESS ATOM UNCONSTRAINED. This one names no
    vocabulary, so it is true whatever a declaration says -- the admission rule for a CHECK
    at this layer."""
    assert schema.OBJECTLESS_PAYLOAD_CONSTRAINT in schema.CREATE_LEDGER
    assert "qualifiers" in schema.OBJECTLESS_PAYLOAD_CHECK
    assert "predicate" not in schema.OBJECTLESS_PAYLOAD_CHECK


def test_the_retired_name_survives_so_a_reader_can_tell_two_states_apart():
    """🪦 An install that predates S-77 still carries the constraint; one where somebody
    dropped a constraint by hand does not. Without the name, both read as 「absent」."""
    assert schema.RETIRED_REGISTER_OBJECT_CONSTRAINT == "ck_ledger_register_has_no_object"


def test_the_drop_is_idempotent_and_asks_before_it_acts():
    """`ensure_schema` runs at the start of every backfill, so a helper that issued DDL
    unconditionally would take an ACCESS EXCLUSIVE lock on the ledger every single run."""
    class _Cursor:
        """`constraint_exists` reads `fetchone() is not None`, so ABSENCE is None -- not a
        zero. A fake that returned `(0,)` for "not there" would have made the guard look
        broken while it worked."""

        def __init__(self, present):
            self.present = present
            self.calls = []

        def execute(self, statement, params=None):
            self.calls.append(statement)

        def fetchone(self):
            return (1,) if self.present else None

        def dropped(self):
            return [s for s in self.calls if "DROP CONSTRAINT" in s]

    # ⛔ BOTH ARMS ON THE SAME HELPER. A test that only ran the absent arm would pass on a
    # helper that never drops anything at all.
    fresh = _Cursor(present=False)
    assert schema.ensure_register_object_constraint_dropped(fresh) is False
    assert fresh.dropped() == [], fresh.calls

    old_install = _Cursor(present=True)
    assert schema.ensure_register_object_constraint_dropped(old_install) is True
    assert len(old_install.dropped()) == 1
    assert schema.RETIRED_REGISTER_OBJECT_CONSTRAINT in old_install.dropped()[0]


def test_ensure_schema_carries_the_drop():
    """A migration script nobody runs is not a migration. The install path does it too."""
    import inspect

    body = inspect.getsource(schema.ensure_schema)
    assert "ensure_register_object_constraint_dropped(cursor)" in body
