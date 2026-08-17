"""Deterministic legacy <-> Ledger v2 semantic shadow comparison."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any


PARITY_FIELDS = (
    "source_event_id", "source_event_state", "subject_type", "subject_keys",
    "predicate", "object_kind", "object_payload", "occurred_at", "source_who",
    "source_raw_ref", "source_translator_ver", "supersedes", "derivation",
    "molecule_ref",
)
MATCH_FIELDS = (
    "subject_type", "subject_keys", "predicate", "occurred_at",
)
OUTCOME_FIELDS = ("molecules", "refused", "incomplete")


@dataclass(frozen=True)
class ParityDifference:
    status: str
    path: str
    legacy: Any
    v2: Any
    reason: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path": self.path,
            "legacy": self.legacy,
            "v2": self.v2,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ShadowParityReport:
    equal_claims: int
    explained_differences: int
    regressions: int
    differences: tuple[ParityDifference, ...]

    @property
    def status(self) -> str:
        if self.regressions:
            return "regression"
        if self.explained_differences:
            return "explained_difference"
        return "equal"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "equal_claims": self.equal_claims,
            "explained_differences": self.explained_differences,
            "regressions": self.regressions,
            "differences": [item.to_mapping() for item in self.differences],
        }


def compare_shadow(
    legacy_candidates: Sequence[Any],
    v2_candidates: Sequence[Any],
    *,
    ignored_fields: Sequence[str] = (),
    approved_explanations: Mapping[str, str] | None = None,
    legacy_outcome: Mapping[str, int] | None = None,
    v2_outcome: Mapping[str, int] | None = None,
) -> ShadowParityReport:
    """Classify every semantic difference; no difference is silently ignored.

    ``ignored_fields`` is an explicit comparison-normalization declaration for values
    such as compiler fingerprints. ``approved_explanations`` keys are exact difference
    paths or ``*.field`` suffix rules and always require a non-blank reason.
    """
    ignored = frozenset(ignored_fields)
    unknown = ignored - set(PARITY_FIELDS)
    if unknown:
        raise ValueError(f"unknown parity ignored fields: {sorted(unknown)}")
    explanations = dict(approved_explanations or {})
    if any(not isinstance(path, str) or not path.strip()
           or not isinstance(reason, str) or not reason.strip()
           for path, reason in explanations.items()):
        raise ValueError("approved parity explanations require non-blank path/reason")
    legacy = [_normalize(item, ignored) for item in legacy_candidates]
    v2 = [_normalize(item, ignored) for item in v2_candidates]

    legacy_exact = Counter(_canonical(item) for item in legacy)
    v2_exact = Counter(_canonical(item) for item in v2)
    equal = sum((legacy_exact & v2_exact).values())

    legacy_by_key = _remaining_by_key(legacy, legacy_exact & v2_exact)
    v2_by_key = _remaining_by_key(v2, legacy_exact & v2_exact)
    differences: list[ParityDifference] = []
    for key in sorted(set(legacy_by_key) | set(v2_by_key)):
        left = legacy_by_key.get(key, [])
        right = v2_by_key.get(key, [])
        pair_count = min(len(left), len(right))
        for index in range(pair_count):
            prefix = f"claims[{key}][{index}]"
            for path, before, after in _walk_diff(left[index], right[index], prefix):
                reason = _explanation(path, explanations)
                differences.append(ParityDifference(
                    status="explained_difference" if reason else "regression",
                    path=path, legacy=before, v2=after, reason=reason,
                ))
        for index in range(pair_count, len(left)):
            path = f"claims[{key}].legacy_only[{index}]"
            reason = _explanation(path, explanations)
            differences.append(ParityDifference(
                status="explained_difference" if reason else "regression",
                path=path, legacy=left[index], v2=None, reason=reason,
            ))
        for index in range(pair_count, len(right)):
            path = f"claims[{key}].v2_only[{index}]"
            reason = _explanation(path, explanations)
            differences.append(ParityDifference(
                status="explained_difference" if reason else "regression",
                path=path, legacy=None, v2=right[index], reason=reason,
            ))
    left_outcome = _outcome(legacy, legacy_outcome, "legacy_outcome")
    right_outcome = _outcome(v2, v2_outcome, "v2_outcome")
    for path, before, after in _walk_diff(
            left_outcome, right_outcome, "outcome"):
        reason = _explanation(path, explanations)
        differences.append(ParityDifference(
            status="explained_difference" if reason else "regression",
            path=path, legacy=before, v2=after, reason=reason,
        ))
    differences.sort(key=lambda item: (
        item.path, _canonical(item.legacy), _canonical(item.v2)))
    explained = sum(item.status == "explained_difference" for item in differences)
    regressions = sum(item.status == "regression" for item in differences)
    return ShadowParityReport(
        equal_claims=equal,
        explained_differences=explained,
        regressions=regressions,
        differences=tuple(differences),
    )


def _outcome(
    records: Sequence[Mapping[str, Any]],
    declared: Mapping[str, int] | None,
    path: str,
) -> dict[str, int]:
    if declared is None:
        molecules = {
            record.get("molecule_ref") for record in records
            if record.get("molecule_ref") is not None
        }
        return {"molecules": len(molecules), "refused": 0, "incomplete": 0}
    if not isinstance(declared, Mapping) or set(declared) != set(OUTCOME_FIELDS):
        raise ValueError(
            f"{path} must contain exactly {list(OUTCOME_FIELDS)}")
    out = {}
    for field in OUTCOME_FIELDS:
        value = declared[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{path}.{field} must be a non-negative integer")
        out[field] = value
    return out


def _normalize(value: Any, ignored: frozenset[str]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        source = value
    else:
        source = {field: getattr(value, field, None) for field in PARITY_FIELDS}
    out = {}
    for field in PARITY_FIELDS:
        if field in ignored:
            continue
        item = source.get(field)
        if hasattr(item, "isoformat") and field == "occurred_at":
            item = item.isoformat()
        elif field in {"source_event_id", "supersedes"} and item is not None:
            item = str(item)
        out[field] = _plain(item)
    return out


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _remaining_by_key(
    records: Sequence[Mapping[str, Any]],
    exact_intersection: Counter[str],
) -> Mapping[str, list[Mapping[str, Any]]]:
    consumed = Counter()
    out: dict[str, list[Mapping[str, Any]]] = {}
    for record in sorted(records, key=_canonical):
        token = _canonical(record)
        if consumed[token] < exact_intersection[token]:
            consumed[token] += 1
            continue
        key = _canonical({field: record.get(field) for field in MATCH_FIELDS
                          if field in record})
        out.setdefault(key, []).append(record)
    return MappingProxyType(out)


def _walk_diff(before: Any, after: Any, path: str):
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        for key in sorted(set(before) | set(after), key=str):
            yield from _walk_diff(before.get(key), after.get(key), f"{path}.{key}")
        return
    if isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            left = before[index] if index < len(before) else None
            right = after[index] if index < len(after) else None
            yield from _walk_diff(left, right, f"{path}[{index}]")
        return
    if before != after:
        yield path, before, after


def _explanation(path: str, explanations: Mapping[str, str]) -> str | None:
    if path in explanations:
        return explanations[path]
    matches = [reason for pattern, reason in explanations.items()
               if pattern.startswith("*.") and path.endswith(pattern[1:])]
    if len(matches) > 1:
        raise ValueError(f"multiple parity explanations match {path!r}")
    return matches[0] if matches else None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False, default=str)
