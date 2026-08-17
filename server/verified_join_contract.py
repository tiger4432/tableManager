"""Immutable hand-off produced only after virtual-join physical verification.

The shape-only declaration remains owned by ``virtual_join_config``.  This module owns
the neutral value passed from that verifier to every consumer, including the UI join
executor and Ledger v2 setup compiler.  It has no database imports or execution methods.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


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


@dataclass(frozen=True, init=False)
class VerifiedJoinDescriptor(Mapping[str, Any]):
    """One shape-valid join with a named physical UNIQUE-index proof.

    Mapping compatibility keeps existing read-only consumers unchanged while the class
    prevents a catalog declaration from being confused with a physically verified rule.
    """

    _data: Mapping[str, Any]

    @classmethod
    def from_verified_rule(cls, rule: Mapping[str, Any]) -> "VerifiedJoinDescriptor":
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
        descriptor = object.__new__(cls)
        object.__setattr__(descriptor, "_data", _freeze(normalized))
        return descriptor

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
