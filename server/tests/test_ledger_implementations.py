"""The trusted implementation set is DERIVED from the classes the repository ships.

Before this round the same fact lived in four hand-kept lists (a trusted catalog and two
registries in ``ledger/cutover_v2.py``, plus a private literal in the transfer sample's
test support).  The measurable consequence: two generic implementations that were already
written and already correct were unreachable from every config file, and the sample this
product ships named two implementation ids that no class anywhere declared -- so opening a
draft on it and saving it UNCHANGED was refused with ``untrusted_implementation``.

These tests pin the DERIVATION, not a count.  A count would go green again if these two
implementations were swapped for two others, which is the failure they exist to catch.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.config_drafts import compile_draft_preview                  # noqa: E402
from ledger.config_explorer import build_explorer_index                 # noqa: E402
from ledger.implementations import (                                    # noqa: E402
    ImplementationDeclarationError,
    _self_declared_identity,
    mapper_declarations,
    role_mapper_registry,
    trusted_implementations,
)
from ledger.roleframe import BaseLedgerMapper, DeclarativeRoleMapper    # noqa: E402
from ledger.setup_registry import ImplementationKey                     # noqa: E402
from tests.support.ontology_explorer_sample import (                    # noqa: E402
    load_transfer_sample_setup,
)


def test_generic_implementations_are_addressable_from_config():
    """The implementation that was locked out by omission is trusted. (Its preparer
    sibling `direct-join` left with the preparer in setup_version 6.)"""
    trusted = trusted_implementations()
    assert ImplementationKey("declarative-role", 1) in trusted.mappers
    assert mapper_declarations()[("declarative-role", 1)] is DeclarativeRoleMapper


def test_trusted_catalog_and_executable_registries_cannot_disagree():
    """Every trusted key resolves to a runnable object, and nothing else is trusted.

    This is the invariant the four hand-kept lists could not hold: a name could be trusted
    with no class behind it, or a class could exist with no name in front of it.
    """
    trusted = trusted_implementations()
    mappers = role_mapper_registry()

    assert {(key.implementation_id, key.implementation_version)
            for key in trusted.mappers} == set(mapper_declarations())
    for key in trusted.mappers:
        assert isinstance(mappers.resolve(key), BaseLedgerMapper)


def test_a_subclass_that_declares_nothing_is_not_addressable():
    """Silence is not an address -- a test double must not become callable from config."""

    class UndeclaredMapper(BaseLedgerMapper):
        def interpret_unit(self, context, unit, profile):
            return []

    assert UndeclaredMapper not in mapper_declarations().values()
    assert _self_declared_identity(UndeclaredMapper) is None


def test_an_inherited_identity_is_not_re_used_by_a_subclass():
    """A subclass inherits behaviour, never an address.

    Without this rule the first two subclasses of any registered implementation would
    collide on one key, and the collision message would name a class nobody had touched.
    """

    class QuietSubclass(DeclarativeRoleMapper):
        pass

    assert _self_declared_identity(QuietSubclass) is None
    assert _self_declared_identity(DeclarativeRoleMapper) == ("declarative-role", 1)


@pytest.mark.parametrize("identifier,version", [
    ("test-bad-version", 0),
    ("test-bad-version", True),
    (" untrimmed", 1),
    ("", 1),
    (None, 1),
    ("test-bad-version", "1"),
])
def test_a_malformed_self_declaration_is_refused_rather_than_ignored(identifier, version):
    """A typo in the declaration must be loud, never silently skipped.

    A skipped class is the OLD failure wearing a new coat: the implementation exists,
    config names it, and the refusal points at the config instead of at the typo.

    Deliberately built OFF the implementation base classes.  A broken subclass would join
    ``BaseLedgerMapper.__subclasses__()`` and make every later call to the real discovery
    walk raise -- a test that breaks unrelated tests through an interpreter-global.
    """
    malformed = type("MalformedImplementation", (), {
        "implementation_id": identifier, "implementation_version": version})
    with pytest.raises(ImplementationDeclarationError):
        _self_declared_identity(malformed)


def test_transfer_sample_draft_validates_unchanged_with_a_non_lot_event_implementation():
    """The shipped sample uses NO lot-event implementation, and its draft compiles.

    MEASURED before this round: ``trusted_cutover_implementations()`` was a literal naming
    only ``lot-event-live-frame``@1 and ``lot-event-role``@1, so this exact interaction --
    open the draft, change nothing, save -- returned ``valid: False`` with
    ``untrusted_implementation``.  The sample now names the generic implementations that
    really exist, and the trusted set is read back off those classes.
    """
    setup = load_transfer_sample_setup()
    plan = setup.snapshot.source_plans["dt_log"]
    assert plan.driver.mapper.implementation == ImplementationKey("declarative-role", 1)

    index = build_explorer_index(setup)
    node = index.nodes["source_plan|dt_log"]
    preview = compile_draft_preview(setup, node, node.raw)

    assert [issue["code"] for issue in preview.errors] == []
    assert preview.valid is True
