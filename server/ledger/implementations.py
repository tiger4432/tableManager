"""Discover the executable implementations the repository actually ships.

WHY THIS FILE REPLACED THREE HAND-KEPT LISTS
--------------------------------------------
A ledger source declaration names an ``implementation_id`` -- a NAME, never a module, a
path, or an expression (``setup_bundle._FORBIDDEN_DECLARATION_KEYS`` is the other half of
that rule).  Something therefore has to say which names are executable, or a config file
would be able to call arbitrary Python.  **That boundary is correct and this module keeps
it.**

What was wrong was not the boundary but the bookkeeping: the same fact was written down in
FOUR places -- a trusted catalog, a preparer registry, a mapper registry, and a fourth
literal inside the transfer sample's test support -- so adding one mapper meant editing
four lists, and forgetting one produced ``untrusted_implementation`` at compile time with
no hint that the class existed.  MEASURED 2026-08-18: two generic implementations
(:class:`ledger.roleframe.DeclarativeRoleMapper`,
:class:`ledger.source_preparation.DirectJoinSourcePreparer`) were already written, already
correct, and unreachable from any config because nobody had added them to the lists.

Now the class states its own identity and this module reads it back.  The trusted set is
therefore DERIVED from the code that exists, and the two can no longer disagree.

WHAT COUNTS AS TRUSTED, PRECISELY
---------------------------------
A class is addressable from config when all of the following hold, and each is checked:

  1. it subclasses :class:`~ledger.source_preparation.BaseSourcePreparer` or
     :class:`~ledger.roleframe.BaseLedgerMapper`;
  2. it declares a non-blank ``implementation_id`` and a positive
     ``implementation_version`` **on itself**, not merely inherited (an intermediate base
     must not lend its identity to every subclass);
  3. it lives in a module this file imports -- ``ledger.roleframe``,
     ``ledger.source_preparation``, or a ``mappers/ledger_v2_*.py`` module.  The import
     set is a property of the REPOSITORY LAYOUT, not of any config file, which is what
     keeps a declaration from choosing what gets imported;
  4. it passes the registry's own structural gate -- ``map()`` / ``prepare_batch()`` are
     final and must not be overridden, and it must construct with no arguments.  Those
     checks already lived in the registries and are still the ones that run.

So "add a mapper" is one new file under ``server/mappers/`` named ``ledger_v2_*.py``, and
this module is not edited.
"""
from __future__ import annotations

from collections.abc import Iterator
import importlib
import pkgutil

from .roleframe import BaseLedgerMapper, RoleMapperImplementationRegistry
from .setup_registry import TrustedImplementationCatalog
from .source_preparation import (
    BaseSourcePreparer,
    SourcePreparerImplementationRegistry,
)


#: Package scanned for source-specific implementations, and the prefix that marks a
#: module as carrying Ledger v2 implementations.  The prefix exists because
#: ``server/mappers/`` also holds chain-ingestion mappers that import database machinery;
#: importing those here would put the ledger setup path behind an unrelated dependency.
_IMPLEMENTATION_PACKAGE = "mappers"
_IMPLEMENTATION_MODULE_PREFIX = "ledger_v2_"


class ImplementationDeclarationError(ValueError):
    """Two classes claim one ``implementation_id``@version, or a claim is malformed."""


def _import_implementation_modules() -> None:
    package = importlib.import_module(_IMPLEMENTATION_PACKAGE)
    for info in pkgutil.iter_modules(list(package.__path__)):
        if info.name.startswith(_IMPLEMENTATION_MODULE_PREFIX):
            importlib.import_module(f"{_IMPLEMENTATION_PACKAGE}.{info.name}")


def _descendants(base: type) -> Iterator[type]:
    seen: set[int] = set()
    stack = list(base.__subclasses__())
    while stack:
        item = stack.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        stack.extend(item.__subclasses__())
        yield item


def _self_declared_identity(implementation: type) -> tuple[str, int] | None:
    """Return this class's OWN declaration, or ``None`` when it does not make one.

    ``__dict__`` rather than ``getattr`` on purpose: an inherited identity would silently
    give every subclass of a registered implementation the same address, and the first two
    such subclasses would then collide with each other for a reason nobody wrote down.
    """
    identifier = implementation.__dict__.get("implementation_id")
    version = implementation.__dict__.get("implementation_version")
    if identifier is None and version is None:
        return None
    if not isinstance(identifier, str) or not identifier.strip() \
            or identifier != identifier.strip():
        raise ImplementationDeclarationError(
            f"{implementation.__module__}.{implementation.__qualname__}: "
            "implementation_id must be a trimmed non-blank string")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ImplementationDeclarationError(
            f"{implementation.__module__}.{implementation.__qualname__}: "
            "implementation_version must be a positive integer")
    return identifier, version


def _declarations(base: type) -> dict[tuple[str, int], type]:
    _import_implementation_modules()
    found: dict[tuple[str, int], type] = {}
    for implementation in _descendants(base):
        identity = _self_declared_identity(implementation)
        if identity is None:
            continue
        existing = found.get(identity)
        if existing is not None and existing is not implementation:
            raise ImplementationDeclarationError(
                f"{identity[0]!r}@{identity[1]} is declared by both "
                f"{existing.__module__}.{existing.__qualname__} and "
                f"{implementation.__module__}.{implementation.__qualname__}")
        found[identity] = implementation
    return found


def source_preparer_declarations() -> dict[tuple[str, int], type]:
    return _declarations(BaseSourcePreparer)


def mapper_declarations() -> dict[tuple[str, int], type]:
    return _declarations(BaseLedgerMapper)


def trusted_implementations() -> TrustedImplementationCatalog:
    """The trusted set, derived from the classes that exist rather than from a list."""
    return TrustedImplementationCatalog.build(
        source_preparers=tuple(sorted(source_preparer_declarations())),
        mappers=tuple(sorted(mapper_declarations())),
    )


def source_preparer_registry() -> SourcePreparerImplementationRegistry:
    registry = SourcePreparerImplementationRegistry()
    for (identifier, version), implementation in sorted(
            source_preparer_declarations().items()):
        registry.register(identifier, version, implementation)
    return registry.seal()


def role_mapper_registry() -> RoleMapperImplementationRegistry:
    registry = RoleMapperImplementationRegistry()
    for (identifier, version), implementation in sorted(mapper_declarations().items()):
        registry.register(identifier, version, implementation)
    return registry.seal()
