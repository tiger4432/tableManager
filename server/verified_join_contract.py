"""Immutable hand-off produced only after virtual-join physical verification.

The shape-only declaration remains owned by ``virtual_join_config``.  This module owns
the neutral value passed from that verifier to every consumer, including the UI join
executor and Ledger v2 setup compiler.  It has no database imports or execution methods.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
import inspect
from types import MappingProxyType
from typing import Any
from weakref import WeakSet

__all__ = ["VerifiedJoinDescriptor", "is_physically_verified_descriptor"]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({
            str(key): _freeze(value[key]) for key in sorted(value, key=str)
        })
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True, init=False, eq=False)
class VerifiedJoinDescriptor(Mapping[str, Any]):
    """One shape-valid join with a named physical UNIQUE-index proof.

    Mapping compatibility keeps existing read-only consumers unchanged while the class
    prevents a catalog declaration from being confused with a physically verified rule.
    """

    _data: Mapping[str, Any]
    __eq__ = object.__eq__
    __hash__ = object.__hash__

    def __new__(cls, *args: Any, **kwargs: Any) -> "VerifiedJoinDescriptor":
        raise TypeError(
            "VerifiedJoinDescriptor cannot be constructed directly; "
            "use virtual_join_config.load_verified_rules")

    @classmethod
    def _issue(cls, *args: Any, **kwargs: Any) -> "VerifiedJoinDescriptor":
        """Reject the former raw issuance API, including callers holding the issuer."""
        raise TypeError(
            "direct VerifiedJoinDescriptor issuance is not allowed; "
            "use virtual_join_config.load_verified_rules")

    @staticmethod
    def _validated_data(rule: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(rule, Mapping):
            raise TypeError("verified join rule must be a mapping")
        required = (
            "name", "left_table", "right_table", "join_key", "expose",
            "join_cardinality", "unique_index",
        )
        missing = [name for name in required if name not in rule]
        if missing:
            raise ValueError(f"verified join rule is missing {missing!r}")
        for field in ("name", "left_table", "right_table", "unique_index"):
            value = rule[field]
            if (not isinstance(value, str) or not value.strip()
                    or value != value.strip()):
                raise ValueError(f"verified join {field} must be a trimmed non-blank string")
        if rule["join_cardinality"] != "one":
            raise ValueError("verified join requires join_cardinality 'one'")
        pairs = rule["join_key"]
        if (not isinstance(pairs, Sequence)
                or isinstance(pairs, (str, bytes, bytearray)) or not pairs):
            raise ValueError("verified join_key must be a non-empty sequence")
        for index, pair in enumerate(pairs):
            if not isinstance(pair, Mapping):
                raise ValueError(f"verified join_key[{index}] must be a mapping")
            for side in ("left", "right"):
                value = pair.get(side)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"verified join_key[{index}].{side} must be non-blank")
                if value != value.strip():
                    raise ValueError(
                        f"verified join_key[{index}].{side} must be trimmed")
            fold = pair.get("fold")
            if fold is not None and not isinstance(fold, Mapping):
                raise ValueError(f"verified join_key[{index}].fold must be an object or null")
        expose = rule["expose"]
        if (not isinstance(expose, Sequence)
                or isinstance(expose, (str, bytes, bytearray)) or not expose):
            raise ValueError("verified expose must be a non-empty sequence")
        if any(not isinstance(value, str) or not value.strip()
               or value != value.strip() for value in expose):
            raise ValueError("verified expose values must be trimmed non-blank strings")
        if len(expose) != len(set(expose)):
            raise ValueError("verified expose values must be unique")
        normalized = dict(rule)
        normalized["verified"] = True
        normalized["verification_basis"] = "physical_unique_index"
        return _freeze(normalized)

    @property
    def rule_id(self) -> str:
        return self._data["name"]

    @property
    def unique_index(self) -> str:
        return self._data["unique_index"]

    @property
    def verification_basis(self) -> str:
        return self._data["verification_basis"]

    @property
    def join_key_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple((pair["left"], pair["right"])
                     for pair in self._data["join_key"])

    @property
    def pair_folds(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(pair.get("fold") or MappingProxyType({})
                     for pair in self._data["join_key"])

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def to_mapping(self) -> dict[str, Any]:
        return _plain(self._data)


def _build_verification_boundary():
    """Create a closed issuer registry with no module-level mutation handle."""
    issued_descriptors: WeakSet[VerifiedJoinDescriptor] = WeakSet()
    issuer_token = object()

    class _PhysicalVerifierIssuer:
        """Capability bound to ``virtual_join_config`` production code."""

        __slots__ = ("_token",)

        def __init__(self, token: object) -> None:
            if token is not issuer_token:
                raise TypeError("physical verifier issuer cannot be constructed directly")
            self._token = token

        def issue(self, rule: Mapping[str, Any]) -> VerifiedJoinDescriptor:
            frame = inspect.currentframe()
            caller = frame.f_back if frame is not None else None
            module_name = (
                caller.f_globals.get("__name__") if caller is not None else None)
            loader = (
                caller.f_globals.get("load_verified_rules")
                if caller is not None else None)
            if (module_name not in {"virtual_join_config", "server.virtual_join_config"}
                    or loader is None
                    or caller.f_code is not getattr(loader, "__code__", None)):
                raise TypeError(
                    "verified join descriptors can only be issued inside "
                    "virtual_join_config.load_verified_rules")
            descriptor = object.__new__(VerifiedJoinDescriptor)
            object.__setattr__(
                descriptor, "_data", VerifiedJoinDescriptor._validated_data(rule))
            issued_descriptors.add(descriptor)
            return descriptor

    def is_issued(value: object) -> bool:
        return (
            isinstance(value, VerifiedJoinDescriptor)
            and value in issued_descriptors
        )

    def bind_issuer():
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        module_name = caller.f_globals.get("__name__") if caller is not None else None
        if module_name not in {"virtual_join_config", "server.virtual_join_config"}:
            raise TypeError(
                "physical verifier issuer is only available to virtual_join_config")
        return _PhysicalVerifierIssuer(issuer_token)

    return is_issued, bind_issuer


is_physically_verified_descriptor, _bind_physical_verifier_issuer = (
    _build_verification_boundary())
del _build_verification_boundary
