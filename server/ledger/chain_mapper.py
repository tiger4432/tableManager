"""Trusted Chain-mapper calls for the existing Ledger-owned execution loop.

This reuses the established mapper function shape ``(db, payload, rule=None)`` without
starting the Chain worker or accepting module paths from configuration.  For Ledger the
first argument is a deliberately capability-poor context, never a writable ORM session.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import inspect
import json
from types import MappingProxyType
from typing import Any, Callable, Optional

from .ledger_frame import LedgerFrameError, validate_ledger_frame


MAPPER_METADATA_RULE_KEY = "__ledger_mapper__"
LedgerMapperFunction = Callable[[Any, Any, Optional[Mapping[str, Any]]], Any]


class LedgerMapperError(RuntimeError):
    """Stable execution error that is neither a gate refusal nor an empty result."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


class LedgerMapperRefused(LedgerMapperError):
    """The source event was understood and explicitly refused by its mapper."""


@dataclass(frozen=True)
class LedgerMapperContext:
    """Read-only capabilities explicitly supplied by the Ledger driver.

    Lookup adapters may be placed in ``lookups``.  There is intentionally no engine,
    session, commit, cursor or source reader on this object.
    """

    lookups: Mapping[str, Any] = MappingProxyType({})
    values: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self):
        if not isinstance(self.lookups, Mapping) or not isinstance(self.values, Mapping):
            raise TypeError("LedgerMapperContext mappings must be mappings")
        object.__setattr__(self, "lookups", MappingProxyType(
            {str(name): self.lookups[name] for name in sorted(self.lookups, key=str)}))
        object.__setattr__(self, "values", MappingProxyType(
            {str(name): self.values[name] for name in sorted(self.values, key=str)}))


@dataclass(frozen=True)
class LedgerMapperDescriptor:
    mapper_id: str
    version: int
    function: LedgerMapperFunction
    fingerprint: str

    @property
    def provenance_token(self) -> str:
        return f"mapper:{self.mapper_id}@{self.version}:{self.fingerprint[:16]}"

    def public_metadata(self) -> dict[str, Any]:
        return {
            "mapper_id": self.mapper_id,
            "version": self.version,
            "fingerprint": self.fingerprint,
        }


class LedgerMapperRegistry:
    """Add-only callable registry; module names and file paths are never executable."""

    def __init__(self, descriptors: Sequence[LedgerMapperDescriptor] = ()):
        self._items: dict[tuple[str, int], LedgerMapperDescriptor] = {}
        self._sealed = False
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: LedgerMapperDescriptor) -> None:
        if self._sealed:
            raise RuntimeError("ledger mapper registry is sealed")
        if not isinstance(descriptor, LedgerMapperDescriptor):
            raise TypeError("mapper descriptor must be LedgerMapperDescriptor")
        if not isinstance(descriptor.mapper_id, str) or not descriptor.mapper_id.strip():
            raise ValueError("mapper_id must not be blank")
        if (isinstance(descriptor.version, bool)
                or not isinstance(descriptor.version, int)
                or descriptor.version < 1):
            raise ValueError("mapper version must be a positive integer")
        if not callable(descriptor.function):
            raise TypeError("mapper function must be callable")
        if (not isinstance(descriptor.fingerprint, str)
                or len(descriptor.fingerprint) != 64
                or any(char not in "0123456789abcdef"
                       for char in descriptor.fingerprint)):
            raise ValueError("mapper fingerprint must be a lowercase sha256 hex digest")
        key = (descriptor.mapper_id, descriptor.version)
        if key in self._items:
            raise ValueError(f"mapper {descriptor.mapper_id!r}@{descriptor.version} exists")
        self._items[key] = descriptor

    def seal(self) -> "LedgerMapperRegistry":
        self._sealed = True
        return self

    def get(self, mapper_id: str, version: int) -> Optional[LedgerMapperDescriptor]:
        return self._items.get((mapper_id, version))

    def public_metadata(self) -> list[dict[str, Any]]:
        return [self._items[key].public_metadata() for key in sorted(self._items)]


def describe_mapper(mapper_id: str, version: int,
                    function: LedgerMapperFunction) -> LedgerMapperDescriptor:
    """Register deterministic identity for the mapper's complete code artifact.

    Hashing only ``inspect.getsource(function)`` is insufficient: the registered entry
    point delegates to module-level pairing/emitter helpers, and changing one of those
    helpers would otherwise keep the same provenance fingerprint.  A real module-backed
    mapper therefore fingerprints its whole module.  Dynamically defined callables retain
    the narrower function-source fallback used by tests and controlled extensions.
    """
    module = inspect.getmodule(function)
    try:
        if module is not None and getattr(module, "__file__", None):
            artifact_name = module.__name__
            source = inspect.getsource(module)
        else:
            artifact_name = function.__qualname__
            source = inspect.getsource(function)
    except (OSError, TypeError) as exc:
        raise ValueError(
            f"mapper {mapper_id!r}@{version} has no inspectable code artifact") from exc
    material = f"{mapper_id}\n{version}\n{artifact_name}\n{source}".encode("utf-8")
    return LedgerMapperDescriptor(
        mapper_id=mapper_id,
        version=version,
        function=function,
        fingerprint=hashlib.sha256(material).hexdigest(),
    )


def run_registered_mapper(
        mapper_id: str,
        version: int,
        payload,
        *,
        context: Optional[LedgerMapperContext] = None,
        rule: Optional[Mapping[str, Any]] = None,
        registry: Optional[LedgerMapperRegistry] = None):
    """Call one trusted mapper and fail closed on result or provenance drift."""
    return _run_registered_mapper(
        mapper_id, version, payload, context=context, rule=rule,
        registry=registry, allow_legacy_atom=False)


def _run_registered_mapper(
        mapper_id: str,
        version: int,
        payload,
        *,
        context: Optional[LedgerMapperContext] = None,
        rule: Optional[Mapping[str, Any]] = None,
        registry: Optional[LedgerMapperRegistry] = None,
        allow_legacy_atom: bool = False):
    """Shared implementation; only ``ledger.legacy_import`` may opt into old IDs."""
    registry = registry or default_ledger_mapper_registry()
    descriptor = registry.get(mapper_id, version)
    if descriptor is None:
        raise LedgerMapperError(
            "unknown_mapper", "mapper",
            f"ledger mapper {mapper_id!r}@{version} is not registered")
    mapper_rule = dict(rule or {})
    mapper_rule[MAPPER_METADATA_RULE_KEY] = MappingProxyType(
        descriptor.public_metadata())
    try:
        result = descriptor.function(
            context or LedgerMapperContext(), payload, rule=mapper_rule)
    except (LedgerFrameError, LedgerMapperError, LedgerMapperRefused):
        raise
    except Exception as exc:
        raise LedgerMapperError(
            "mapper_failed", "mapper",
            f"{mapper_id}@{version} raised {exc.__class__.__name__}: {exc}") from exc
    frame = validate_ledger_frame(result)
    if not allow_legacy_atom:
        for position in range(len(frame)):
            if frame.iloc[position]["source_event_state"] == "legacy_atom":
                raise LedgerMapperError(
                    "legacy_atom_forbidden",
                    f"ledger_frame.rows[{position}].source_event_state",
                    "legacy_atom is accepted only by the explicit historical import API")
    token = descriptor.provenance_token
    for position in range(len(frame)):
        translator_ver = frame.iloc[position]["source_translator_ver"]
        if token not in translator_ver:
            raise LedgerMapperError(
                "mapper_provenance_missing",
                f"ledger_frame.rows[{position}].source_translator_ver",
                f"mapper result must preserve {token!r}")
    return frame


def mapper_provenance(base_version: str, rule: Mapping[str, Any]) -> str:
    """Compose the required mapper identity into an Atom provenance value."""
    metadata = rule.get(MAPPER_METADATA_RULE_KEY) if isinstance(rule, Mapping) else None
    if not isinstance(metadata, Mapping):
        raise LedgerMapperError(
            "mapper_metadata_missing", f"rule.{MAPPER_METADATA_RULE_KEY}",
            "Ledger mapper must be called through run_registered_mapper")
    mapper_id = metadata.get("mapper_id")
    version = metadata.get("version")
    fingerprint = metadata.get("fingerprint")
    if (not isinstance(mapper_id, str) or not mapper_id.strip()
            or isinstance(version, bool) or not isinstance(version, int)
            or not isinstance(fingerprint, str) or len(fingerprint) != 64):
        raise LedgerMapperError(
            "mapper_metadata_invalid", f"rule.{MAPPER_METADATA_RULE_KEY}",
            "mapper metadata is incomplete")
    base = str(base_version or "").strip()
    if not base:
        raise LedgerMapperError(
            "mapper_provenance_invalid", "source_translator_ver",
            "base translator version must not be blank")
    return f"{base}|mapper:{mapper_id}@{version}:{fingerprint[:16]}"


def configured_mapper(source_config: Mapping[str, Any], *,
                      registry: Optional[LedgerMapperRegistry] = None
                      ) -> Optional[LedgerMapperDescriptor]:
    """Resolve an explicitly selected source mapper; absent means legacy path."""
    selection = source_config.get("chain_mapper")
    if selection is None:
        return None
    if not isinstance(selection, Mapping):
        raise LedgerMapperError(
            "invalid_mapper_config", "chain_mapper", "must be an object")
    mapper_id = selection.get("mapper_id")
    version = selection.get("version")
    if not isinstance(mapper_id, str) or not mapper_id.strip():
        raise LedgerMapperError(
            "invalid_mapper_config", "chain_mapper.mapper_id",
            "must be a non-blank registered mapper ID")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise LedgerMapperError(
            "invalid_mapper_config", "chain_mapper.version",
            "must be a positive integer")
    registry = registry or default_ledger_mapper_registry()
    descriptor = registry.get(mapper_id, version)
    if descriptor is None:
        raise LedgerMapperError(
            "unknown_mapper", "chain_mapper",
            f"ledger mapper {mapper_id!r}@{version} is not registered")
    return descriptor


def mapper_execution_version(base_version: str,
                             descriptor: Optional[LedgerMapperDescriptor], *,
                             profile_id: Optional[str] = None,
                             profile=None) -> str:
    """Version stored on the existing Ledger cursor for the selected execution."""
    if descriptor is None:
        return base_version
    version = f"{base_version}|{descriptor.provenance_token}"
    if descriptor.mapper_id == "canonical-profile":
        if (not isinstance(profile_id, str) or not profile_id.strip()
                or profile is None or not callable(getattr(profile, "serialize", None))):
            raise LedgerMapperError(
                "missing_profile_selection", "chain_mapper.profile_id",
                "canonical-profile cursor identity requires an explicit validated Profile")
        digest = hashlib.sha256(profile.serialize().encode("utf-8")).hexdigest()[:16]
        version += f"|profile:{profile_id.strip()}:{digest}"
    return version


def deterministic_source_event_context(
        source: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        identity_fields: Sequence[str]) -> Mapping[str, str]:
    """Build one source-event boundary from declared row identities, never indexes.

    The result depends only on the source name and the complete set of declared identity
    values.  Row order and pandas indexes therefore cannot change source-event identity.
    """
    if not isinstance(source, str) or not source.strip():
        raise LedgerMapperError(
            "invalid_source_event", "source", "source name must not be blank")
    fields = tuple(identity_fields)
    if (not fields or any(not isinstance(name, str) or not name.strip()
                          for name in fields)):
        raise LedgerMapperError(
            "invalid_source_event", "identity_fields",
            "at least one non-blank source identity field is required")
    identities = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise LedgerMapperError(
                "invalid_source_event", f"rows[{index}]", "source row must be a mapping")
        missing = [name for name in fields if name not in row]
        if missing:
            raise LedgerMapperError(
                "invalid_source_event", f"rows[{index}]",
                f"source event identity fields are missing: {missing}")
        identity = {name: row[name] for name in fields}
        try:
            rendered = json.dumps(
                identity, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False, default=_event_json_value)
        except (TypeError, ValueError) as exc:
            raise LedgerMapperError(
                "invalid_source_event", f"rows[{index}]",
                f"source event identity is not deterministic JSON: {exc}") from exc
        identities.append(rendered)
    if not identities:
        raise LedgerMapperError(
            "invalid_source_event", "rows", "source event must contain at least one row")
    body = json.dumps(
        {"identity_fields": fields, "rows": sorted(identities)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return MappingProxyType({
        "molecule_ref": f"{source}:event:{digest}",
        "source_raw_ref": f"{source}:{body}",
    })


def _event_json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


@lru_cache(maxsize=1)
def default_ledger_mapper_registry() -> LedgerMapperRegistry:
    """Process-scoped sealed registry: the only executable mapper list for Ledger v1.

    Artifact inspection and SHA-256 hashing happen once, never once per source event.
    """
    from mappers.ledger_lot_event_mapper import map_lot_event_to_ledger_frame
    from .profile_chain_mapper import map_profile_to_ledger_frame

    return LedgerMapperRegistry((
        describe_mapper("lot-event", 1, map_lot_event_to_ledger_frame),
        describe_mapper("canonical-profile", 1, map_profile_to_ledger_frame),
    )).seal()
