"""Public Source Ontology Profile model and validation contract.

This module is deliberately a pure configuration boundary.  It knows how to validate
and serialize a user's source description, but it does not compile that description,
run a translator, inspect a database, or write anything.

The generic engine lives here; concrete templates and type registrations live in
``source_profile_builtins`` so new registrations do not require source-name branches in
the validator.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROFILE_SCHEMA_VERSION = 1
PROFILE_CONFIG_SECTION = "profiles"

MAPPING_STATUS_HUMAN_APPROVED = "human_approved"
MAPPING_STATUS_INFERRED = "inferred"
MAPPING_STATUSES = frozenset({
    MAPPING_STATUS_HUMAN_APPROVED,
    MAPPING_STATUS_INFERRED,
})

BINDING_ORIGIN_USER_DECLARED = "user_declared"
BINDING_ORIGIN_SYSTEM_SUGGESTED = "system_suggested"
BINDING_ORIGIN_IMPORTED = "imported"
BINDING_ORIGINS = frozenset({
    BINDING_ORIGIN_USER_DECLARED,
    BINDING_ORIGIN_SYSTEM_SUGGESTED,
    BINDING_ORIGIN_IMPORTED,
})

APPROVAL_STATUS_PENDING = "pending"
APPROVAL_STATUS_APPROVED = "approved"
APPROVAL_STATUS_REJECTED = "rejected"
APPROVAL_STATUSES = frozenset({
    APPROVAL_STATUS_PENDING,
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_REJECTED,
})

CONSTANT_VALUE_TYPES = frozenset({
    "array", "boolean", "integer", "number", "object", "string",
})


class ProfileValidationError(ValueError):
    """A rejected Profile value with a stable code and its exact Profile path."""

    def __init__(self, path: str, message: str, code: str = "invalid_profile"):
        self.path = path
        self.code = code
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class RoleDescriptor:
    role_id: str
    kind: str
    required: bool = True
    allowed_binding_kinds: tuple[str, ...] = ("column",)
    allow_null: bool = False
    symbolic_constants: tuple[str, ...] = ()
    allowed_constant_types: tuple[str, ...] = ()

    def public_metadata(self) -> dict:
        return {
            "role_id": self.role_id,
            "kind": self.kind,
            "required": self.required,
            "allowed_binding_kinds": sorted(self.allowed_binding_kinds),
            "allow_null": self.allow_null,
            "symbolic_constants": sorted(self.symbolic_constants),
            "allowed_constant_types": sorted(self.allowed_constant_types),
        }


@dataclass(frozen=True)
class ClaimDescriptor:
    claim_id: str
    roles: tuple[RoleDescriptor, ...]

    @property
    def role_ids(self) -> frozenset[str]:
        return frozenset(role.role_id for role in self.roles)

    @property
    def required_role_ids(self) -> frozenset[str]:
        return frozenset(role.role_id for role in self.roles if role.required)

    def role(self, role_id: str) -> Optional[RoleDescriptor]:
        return next((role for role in self.roles if role.role_id == role_id), None)

    def public_metadata(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "roles": [role.public_metadata()
                      for role in sorted(self.roles, key=lambda item: item.role_id)],
        }


@dataclass(frozen=True)
class PackDescriptor:
    pack_id: str
    version: int
    claims: tuple[ClaimDescriptor, ...]

    def claim(self, claim_id: str) -> Optional[ClaimDescriptor]:
        return next((claim for claim in self.claims if claim.claim_id == claim_id), None)

    def public_metadata(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "version": self.version,
            "claims": [claim.public_metadata()
                       for claim in sorted(self.claims, key=lambda item: item.claim_id)],
        }


class PackRegistry:
    """Add-only registry keyed by ``(pack_id, version)``."""

    def __init__(self, descriptors: Sequence[PackDescriptor] = ()):
        self._descriptors: dict[tuple[str, int], PackDescriptor] = {}
        self._sealed = False
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: PackDescriptor) -> None:
        if self._sealed:
            raise RuntimeError("pack registry is sealed")
        _validate_pack_descriptor(descriptor)
        key = (descriptor.pack_id, descriptor.version)
        if key in self._descriptors:
            raise ValueError(
                f"pack {descriptor.pack_id!r}@{descriptor.version} is already registered")
        self._descriptors[key] = descriptor

    def seal(self) -> "PackRegistry":
        self._sealed = True
        return self

    def get(self, pack_id: str, version: int) -> Optional[PackDescriptor]:
        return self._descriptors.get((pack_id, version))

    def versions(self, pack_id: str) -> tuple[int, ...]:
        return tuple(sorted(version for name, version in self._descriptors
                            if name == pack_id))

    def pack_ids(self) -> tuple[str, ...]:
        return tuple(sorted({pack_id for pack_id, _ in self._descriptors}))

    def public_metadata(self) -> list[dict]:
        return [self._descriptors[key].public_metadata()
                for key in sorted(self._descriptors)]


@dataclass(frozen=True)
class BindingDefinition:
    kind: str
    values: Mapping[str, Any]
    binding_origin: str
    approval_status: str
    suggestion_reason: Optional[str] = None

    def to_mapping(self) -> dict:
        out = {"kind": self.kind}
        out.update({name: _thaw_json(self.values[name]) for name in sorted(self.values)})
        out["binding_origin"] = self.binding_origin
        out["approval_status"] = self.approval_status
        if self.suggestion_reason is not None:
            out["suggestion_reason"] = self.suggestion_reason
        return out


BindingNormalizer = Callable[
    [Mapping[str, Any], str, RoleDescriptor, "BindingKindRegistry"],
    tuple[Optional[Mapping[str, Any]], tuple[ProfileValidationError, ...]],
]


@dataclass(frozen=True)
class BindingKindDescriptor:
    kind: str
    normalize: BindingNormalizer
    allowed_role_kinds: tuple[str, ...] = ()

    def public_metadata(self) -> dict:
        return {
            "kind": self.kind,
            "allowed_role_kinds": sorted(self.allowed_role_kinds),
        }


class BindingKindRegistry:
    """Extensible binding grammar; the Profile validator has no kind switch."""

    def __init__(self, descriptors: Sequence[BindingKindDescriptor] = ()):
        self._descriptors: dict[str, BindingKindDescriptor] = {}
        self._sealed = False
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: BindingKindDescriptor) -> None:
        if self._sealed:
            raise RuntimeError("binding kind registry is sealed")
        if not isinstance(descriptor, BindingKindDescriptor):
            raise TypeError("binding kind descriptor must be BindingKindDescriptor")
        if not isinstance(descriptor.kind, str) or not descriptor.kind.strip():
            raise ValueError("binding kind must not be blank")
        if any(not isinstance(kind, str) or not kind.strip()
               for kind in descriptor.allowed_role_kinds):
            raise ValueError("allowed role kinds must not contain blanks")
        if descriptor.kind in self._descriptors:
            raise ValueError(f"binding kind {descriptor.kind!r} is already registered")
        self._descriptors[descriptor.kind] = descriptor

    def seal(self) -> "BindingKindRegistry":
        self._sealed = True
        return self

    def get(self, kind: str) -> Optional[BindingKindDescriptor]:
        return self._descriptors.get(kind)

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def descriptors(self) -> tuple[BindingKindDescriptor, ...]:
        return tuple(self._descriptors[kind] for kind in self.kinds())

    def public_metadata(self) -> list[dict]:
        return [self._descriptors[kind].public_metadata() for kind in self.kinds()]

    def normalize_binding(self, value: Any, *, path: str,
                          role: RoleDescriptor
                          ) -> tuple[Optional[BindingDefinition],
                                     tuple[ProfileValidationError, ...]]:
        if isinstance(value, str):
            prefix, separator, body = value.partition(":")
            if not separator:
                return None, (_binding_issue(
                    path, "binding shorthand must be kind:value"),)
            raw: Mapping[str, Any] = {"kind": prefix, prefix: body}
        elif isinstance(value, Mapping):
            raw = value
        else:
            return None, (_binding_issue(path, "binding must be an object or shorthand"),)

        kind_value = raw.get("kind")
        if not isinstance(kind_value, str) or not kind_value.strip():
            return None, (_binding_issue(_path(path, "kind"),
                                         "binding kind must not be blank"),)
        kind = kind_value
        descriptor = self.get(kind)
        if descriptor is None:
            return None, (_binding_issue(
                _path(path, "kind"), f"binding kind {kind!r} is not registered"),)
        if kind not in role.allowed_binding_kinds:
            return None, (_binding_issue(
                _path(path, "kind"),
                f"binding kind {kind!r} is not allowed for role {role.role_id!r}"),)
        if (descriptor.allowed_role_kinds
                and role.kind not in descriptor.allowed_role_kinds):
            return None, (_binding_issue(
                _path(path, "kind"),
                f"binding kind {kind!r} does not support role kind {role.kind!r}"),)

        issues: list[ProfileValidationError] = []
        binding_origin = raw.get(
            "binding_origin", BINDING_ORIGIN_USER_DECLARED)
        approval_status = raw.get(
            "approval_status", APPROVAL_STATUS_PENDING)
        suggestion_reason = raw.get("suggestion_reason")
        if (not isinstance(binding_origin, str)
                or binding_origin not in BINDING_ORIGINS):
            issues.append(_binding_issue(
                _path(path, "binding_origin"),
                f"must be one of {', '.join(sorted(BINDING_ORIGINS))}"))
        if (not isinstance(approval_status, str)
                or approval_status not in APPROVAL_STATUSES):
            issues.append(_binding_issue(
                _path(path, "approval_status"),
                f"must be one of {', '.join(sorted(APPROVAL_STATUSES))}"))
        if binding_origin == BINDING_ORIGIN_SYSTEM_SUGGESTED:
            if (not isinstance(suggestion_reason, str)
                    or not suggestion_reason.strip()):
                issues.append(_binding_issue(
                    _path(path, "suggestion_reason"),
                    "is required for a system_suggested binding"))
        elif suggestion_reason is not None:
            issues.append(_binding_issue(
                _path(path, "suggestion_reason"),
                "is only allowed for a system_suggested binding"))

        payload = {name: raw[name] for name in raw
                   if name not in {
                       "kind", "binding_origin", "approval_status",
                       "suggestion_reason",
                   }}
        normalized, kind_issues = descriptor.normalize(payload, path, role, self)
        issues.extend(kind_issues)
        if issues or normalized is None:
            return None, _sort_issues(issues)
        return BindingDefinition(
            kind=kind,
            values=MappingProxyType({name: _freeze_json(normalized[name])
                                     for name in sorted(normalized)}),
            binding_origin=binding_origin,
            approval_status=approval_status,
            suggestion_reason=suggestion_reason,
        ), ()


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    label: str
    required: bool = True

    def public_metadata(self) -> dict:
        return {"name": self.name, "label": self.label, "required": self.required}


@dataclass(frozen=True)
class ContainerSlotDefinition:
    name: str
    label: str
    required: bool = True

    def public_metadata(self) -> dict:
        return {"name": self.name, "label": self.label, "required": self.required}


@dataclass(frozen=True)
class TemplateDefinition:
    """Metadata required to validate and later render one event-template form."""

    name: str
    label: str
    entity_types: tuple[str, ...]
    roles: tuple[RoleDefinition, ...]
    containers: tuple[ContainerSlotDefinition, ...] = ()

    @property
    def role_names(self) -> frozenset[str]:
        return frozenset(role.name for role in self.roles)

    @property
    def required_role_names(self) -> frozenset[str]:
        return frozenset(role.name for role in self.roles if role.required)

    @property
    def container_names(self) -> frozenset[str]:
        return frozenset(slot.name for slot in self.containers)

    @property
    def required_container_names(self) -> frozenset[str]:
        return frozenset(slot.name for slot in self.containers if slot.required)

    def public_metadata(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "entity_types": sorted(self.entity_types),
            "roles": [role.public_metadata()
                      for role in sorted(self.roles, key=lambda item: item.name)],
            "containers": [slot.public_metadata()
                           for slot in sorted(self.containers,
                                              key=lambda item: item.name)],
        }


class TemplateRegistry:
    """Add-only registry used by validation and metadata-driven form rendering."""

    def __init__(self, definitions: Sequence[TemplateDefinition] = ()):
        self._definitions: dict[str, TemplateDefinition] = {}
        self._sealed = False
        for definition in definitions:
            self.register(definition)

    def register(self, definition: TemplateDefinition) -> None:
        if self._sealed:
            raise RuntimeError("template registry is sealed")
        if not isinstance(definition, TemplateDefinition):
            raise TypeError("template definition must be TemplateDefinition")
        _validate_template_definition(definition)
        if definition.name in self._definitions:
            raise ValueError(f"template {definition.name!r} is already registered")
        self._definitions[definition.name] = definition

    def seal(self) -> "TemplateRegistry":
        self._sealed = True
        return self

    def get(self, name: str) -> Optional[TemplateDefinition]:
        return self._definitions.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def public_metadata(self) -> list[dict]:
        return [self._definitions[name].public_metadata() for name in self.names()]


@dataclass(frozen=True)
class TypeDefinition:
    name: str
    keys: tuple[str, ...]
    label: str

    def public_metadata(self) -> dict:
        return {"name": self.name, "label": self.label, "keys": sorted(self.keys)}


class TypeRegistry:
    """Closed entity or container type registry with explicit identity keys."""

    def __init__(self, kind: str, definitions: Sequence[TypeDefinition] = ()):
        self.kind = kind
        self._definitions: dict[str, TypeDefinition] = {}
        self._sealed = False
        for definition in definitions:
            self.register(definition)

    def register(self, definition: TypeDefinition) -> None:
        if self._sealed:
            raise RuntimeError(f"{self.kind} type registry is sealed")
        if not isinstance(definition, TypeDefinition):
            raise TypeError("type definition must be TypeDefinition")
        if not isinstance(definition.name, str) or not definition.name.strip():
            raise ValueError(f"{self.kind} type name must not be blank")
        if (not definition.keys
                or any(not isinstance(key, str) or not key.strip()
                       for key in definition.keys)):
            raise ValueError(f"{self.kind} type {definition.name!r} needs non-empty keys")
        if len(set(definition.keys)) != len(definition.keys):
            raise ValueError(f"{self.kind} type {definition.name!r} repeats a key")
        if definition.name in self._definitions:
            raise ValueError(
                f"{self.kind} type {definition.name!r} is already registered")
        self._definitions[definition.name] = definition

    def seal(self) -> "TypeRegistry":
        self._sealed = True
        return self

    def get(self, name: str) -> Optional[TypeDefinition]:
        return self._definitions.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def public_metadata(self) -> list[dict]:
        return [self._definitions[name].public_metadata() for name in self.names()]


@dataclass(frozen=True)
class ProfileRegistries:
    templates: TemplateRegistry
    entities: TypeRegistry
    containers: TypeRegistry
    packs: PackRegistry
    binding_kinds: BindingKindRegistry


@dataclass(frozen=True)
class ColumnMapping:
    column: str
    status: str
    relation: Optional[str] = None
    reason: Optional[str] = None

    def to_mapping(self) -> dict:
        out = {"column": self.column, "status": self.status}
        if self.relation is not None:
            out["relation"] = self.relation
        if self.reason is not None:
            out["reason"] = self.reason
        return out


@dataclass(frozen=True)
class SourceDefinition:
    relation: str
    related: Mapping[str, str]

    def to_mapping(self) -> dict:
        out = {"relation": self.relation}
        if self.related:
            out["related"] = {name: self.related[name] for name in sorted(self.related)}
        return out


@dataclass(frozen=True)
class EntityDefinition:
    type: str
    keys: Mapping[str, str]

    def to_mapping(self) -> dict:
        return {"type": self.type,
                "keys": {name: self.keys[name] for name in sorted(self.keys)}}


@dataclass(frozen=True)
class EventDefinition:
    template: str
    timezone: str

    def to_mapping(self) -> dict:
        return {"template": self.template, "timezone": self.timezone}


@dataclass(frozen=True)
class ContainerLookup:
    event_role: str
    container_role: str

    def to_mapping(self) -> dict:
        return {"event_role": self.event_role,
                "container_role": self.container_role}


@dataclass(frozen=True)
class ContainerDefinition:
    type: str
    keys: Mapping[str, str]
    lookup: Optional[ContainerLookup] = None

    def to_mapping(self) -> dict:
        out = {"type": self.type,
               "keys": {name: self.keys[name] for name in sorted(self.keys)}}
        if self.lookup is not None:
            out["lookup"] = self.lookup.to_mapping()
        return out


@dataclass(frozen=True)
class LegacySourceOntologyProfile:
    """Unapproved phase-2 draft shape retained only for transition safety."""

    schema_version: int
    source: SourceDefinition
    entity: EntityDefinition
    event: EventDefinition
    roles: Mapping[str, ColumnMapping]
    containers: Mapping[str, ContainerDefinition]

    def to_mapping(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "source": self.source.to_mapping(),
            "entity": self.entity.to_mapping(),
            "event": self.event.to_mapping(),
            "roles": {name: self.roles[name].to_mapping()
                      for name in sorted(self.roles)},
            "containers": {name: self.containers[name].to_mapping()
                           for name in sorted(self.containers)},
        }

    def serialize(self) -> str:
        return json.dumps(self.to_mapping(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class PackReference:
    pack_id: str
    version: int

    def to_mapping(self) -> str:
        return f"{self.pack_id}@{self.version}"


@dataclass(frozen=True)
class ClaimMapping:
    mapping_id: str
    use: str
    bind: Mapping[str, BindingDefinition]

    def to_mapping(self) -> dict:
        return {
            "mapping_id": self.mapping_id,
            "use": self.use,
            "bind": {role_id: self.bind[role_id].to_mapping()
                     for role_id in sorted(self.bind)},
        }


@dataclass(frozen=True)
class SourceOntologyProfile:
    """Canonical phase-2 Claim Mapping Profile; it has no runtime behavior."""

    profile_version: int
    source: str
    packs: tuple[PackReference, ...]
    mappings: tuple[ClaimMapping, ...]

    def to_mapping(self) -> dict:
        return {
            "profile_version": self.profile_version,
            "source": self.source,
            "packs": [reference.to_mapping() for reference in self.packs],
            "mappings": [mapping.to_mapping() for mapping in self.mappings],
        }

    def serialize(self) -> str:
        return json.dumps(self.to_mapping(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)


def validate_profile(profile: Mapping[str, Any], *, path: str = "",
                     registries: Optional[ProfileRegistries] = None
                     ) -> SourceOntologyProfile | LegacySourceOntologyProfile:
    """Validate a canonical mapping Profile or the prior unapproved draft shape."""
    if registries is None:
        registries = _default_registries()
    raw = _expect_mapping(profile, path or "profile")
    if {"profile_version", "packs", "mappings"} & set(raw):
        normalized, issues = _normalize_claim_mapping_profile(raw, path, registries)
        if issues:
            raise issues[0]
        assert normalized is not None
        return normalized
    return _validate_legacy_profile(raw, path or "profile", registries)


def validate_profile_errors(profile: Mapping[str, Any], *, path: str = "",
                            registries: Optional[ProfileRegistries] = None
                            ) -> tuple[ProfileValidationError, ...]:
    """Return every canonical Profile issue in a deterministic order."""
    registries = registries or _default_registries()
    try:
        raw = _expect_mapping(profile, path or "profile")
    except ProfileValidationError as error:
        return (error,)
    _, issues = _normalize_claim_mapping_profile(raw, path, registries)
    return issues


def _validate_legacy_profile(raw: Mapping[str, Any], path: str,
                             registries: ProfileRegistries
                             ) -> LegacySourceOntologyProfile:
    """Validate the phase-2 draft shape without making it the canonical contract."""
    _reject_unknown(raw, {
        "schema_version", "source", "entity", "event", "roles", "containers",
    }, path)

    version_path = _path(path, "schema_version")
    if "schema_version" not in raw:
        raise ProfileValidationError(version_path, "is required", "missing_field")
    version = raw["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ProfileValidationError(version_path, "must be an integer", "invalid_type")
    if version != PROFILE_SCHEMA_VERSION:
        raise ProfileValidationError(
            version_path,
            f"version {version!r} is not supported; expected {PROFILE_SCHEMA_VERSION}",
            "unsupported_version")

    source = _parse_source(_required(raw, "source", path), _path(path, "source"))
    event = _parse_event(_required(raw, "event", path), _path(path, "event"),
                         registries.templates)
    template = registries.templates.get(event.template)
    assert template is not None
    roles = _parse_roles(_required(raw, "roles", path), _path(path, "roles"),
                         source, template)
    entity = _parse_entity(_required(raw, "entity", path), _path(path, "entity"),
                           roles, template, registries.entities)
    containers = _parse_containers(
        _required(raw, "containers", path), _path(path, "containers"), roles,
        template, registries.containers)

    return LegacySourceOntologyProfile(
        schema_version=version,
        source=source,
        entity=entity,
        event=event,
        roles=roles,
        containers=containers,
    )


def serialize_profile(profile: (Mapping[str, Any] | SourceOntologyProfile
                                | LegacySourceOntologyProfile), *,
                      path: str = "",
                      registries: Optional[ProfileRegistries] = None) -> str:
    validated = (profile if isinstance(
        profile, (SourceOntologyProfile, LegacySourceOntologyProfile))
                 else validate_profile(profile, path=path, registries=registries))
    return validated.serialize()


def validate_profile_section(config: Mapping[str, Any], *,
                             path: str = "ledger_config",
                             registries: Optional[ProfileRegistries] = None
                             ) -> dict[str, (SourceOntologyProfile
                                            | LegacySourceOntologyProfile)]:
    """Validate optional ``ledger_config.profiles`` beside legacy ``sources``.

    This is intentionally opt-in in schema phase 1: the existing runtime loader keeps
    consuming ``sources`` exactly as before.  The compiler phase will choose when and how
    validated Profiles become runtime declarations.
    """
    raw_config = _expect_mapping(config, path)
    if PROFILE_CONFIG_SECTION not in raw_config:
        return {}
    section_path = _path(path, PROFILE_CONFIG_SECTION)
    profiles = _expect_mapping(raw_config[PROFILE_CONFIG_SECTION], section_path)
    result: dict[str, SourceOntologyProfile | LegacySourceOntologyProfile] = {}
    for name in sorted(profiles):
        name_path = _path(section_path, str(name))
        if not isinstance(name, str) or not name.strip():
            raise ProfileValidationError(name_path, "profile name must not be blank",
                                         "invalid_profile_name")
        result[name] = validate_profile(profiles[name], path=name_path,
                                        registries=registries)
    return result


def public_profile_schema(registries: Optional[ProfileRegistries] = None) -> dict:
    """Metadata for a future form renderer; runtime implementation details are absent."""
    registries = registries or _default_registries()
    return {
        "profile_version": PROFILE_SCHEMA_VERSION,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "config_section": PROFILE_CONFIG_SECTION,
        "mapping_statuses": sorted(MAPPING_STATUSES),
        "binding_origins": sorted(BINDING_ORIGINS),
        "approval_statuses": sorted(APPROVAL_STATUSES),
        "packs": registries.packs.public_metadata(),
        "binding_kinds": registries.binding_kinds.public_metadata(),
        "templates": registries.templates.public_metadata(),
        "entity_types": registries.entities.public_metadata(),
        "container_types": registries.containers.public_metadata(),
    }


def _default_registries() -> ProfileRegistries:
    from .source_profile_builtins import default_profile_registries
    return default_profile_registries()


def default_binding_kind_registry() -> BindingKindRegistry:
    """Return the closed, execution-free binding grammar for Profile version 1."""
    return BindingKindRegistry((
        BindingKindDescriptor("column", _normalize_column_binding),
        BindingKindDescriptor(
            "constant",
            _normalize_constant_binding,
            allowed_role_kinds=("attribute", "order", "position", "quantity"),
        ),
        BindingKindDescriptor("declared_lookup", _normalize_lookup_binding),
    )).seal()


def _normalize_claim_mapping_profile(
        raw: Mapping[str, Any], path: str, registries: ProfileRegistries
        ) -> tuple[Optional[SourceOntologyProfile],
                   tuple[ProfileValidationError, ...]]:
    issues: list[ProfileValidationError] = []
    allowed_root = {"profile_version", "source", "packs", "mappings"}
    for name in sorted(set(raw) - allowed_root):
        issues.append(ProfileValidationError(
            _path(path, str(name)), "field is not allowed", "invalid_profile"))

    version = raw.get("profile_version")
    version_path = _path(path, "profile_version")
    if "profile_version" not in raw:
        issues.append(ProfileValidationError(
            version_path, "is required", "unsupported_profile_version"))
    elif (isinstance(version, bool) or not isinstance(version, int)
          or version != PROFILE_SCHEMA_VERSION):
        issues.append(ProfileValidationError(
            version_path,
            f"version {version!r} is not supported; expected {PROFILE_SCHEMA_VERSION}",
            "unsupported_profile_version"))

    source = raw.get("source")
    source_path = _path(path, "source")
    if not isinstance(source, str) or not source.strip():
        issues.append(ProfileValidationError(
            source_path, "must be a non-blank source name", "invalid_profile"))

    pack_refs: list[PackReference] = []
    declared_versions: dict[str, int] = {}
    invalid_pack_ids: set[str] = set()
    packs_value = raw.get("packs")
    packs_path = _path(path, "packs")
    if (not isinstance(packs_value, Sequence)
            or isinstance(packs_value, (str, bytes))):
        issues.append(ProfileValidationError(
            packs_path, "must be an array", "invalid_profile"))
        packs_value = ()
    for index, value in enumerate(packs_value):
        item_path = f"{packs_path}[{index}]"
        reference, reference_issue = _parse_pack_reference(value, item_path)
        if reference_issue is not None:
            issues.append(reference_issue)
            continue
        assert reference is not None
        if reference.pack_id in declared_versions:
            issues.append(ProfileValidationError(
                item_path,
                f"pack {reference.pack_id!r} is declared more than once",
                "invalid_profile"))
            invalid_pack_ids.add(reference.pack_id)
            continue
        declared_versions[reference.pack_id] = reference.version
        versions = registries.packs.versions(reference.pack_id)
        if not versions:
            issues.append(ProfileValidationError(
                item_path, f"pack {reference.pack_id!r} is not registered",
                "unknown_pack"))
            invalid_pack_ids.add(reference.pack_id)
            continue
        if reference.version not in versions:
            issues.append(ProfileValidationError(
                item_path,
                f"pack {reference.pack_id!r} does not support version "
                f"{reference.version}; supported versions: "
                f"{', '.join(str(item) for item in versions)}",
                "unsupported_pack_version"))
            invalid_pack_ids.add(reference.pack_id)
            continue
        pack_refs.append(reference)

    normalized_mappings: list[ClaimMapping] = []
    mapping_values = raw.get("mappings")
    mappings_path = _path(path, "mappings")
    if (not isinstance(mapping_values, Sequence)
            or isinstance(mapping_values, (str, bytes))):
        issues.append(ProfileValidationError(
            mappings_path, "must be an array", "invalid_profile"))
        mapping_values = ()
    seen_mapping_ids: set[str] = set()
    for index, value in enumerate(mapping_values):
        mapping_path = f"{mappings_path}[{index}]"
        mapping, mapping_issues = _normalize_claim_mapping(
            value, mapping_path, registries, declared_versions, invalid_pack_ids,
            seen_mapping_ids)
        issues.extend(mapping_issues)
        if mapping is not None:
            normalized_mappings.append(mapping)

    ordered_issues = _sort_issues(issues)
    if ordered_issues:
        return None, ordered_issues
    assert isinstance(version, int) and isinstance(source, str)
    return SourceOntologyProfile(
        profile_version=version,
        source=source,
        packs=tuple(sorted(pack_refs, key=lambda item: (item.pack_id, item.version))),
        mappings=tuple(sorted(normalized_mappings,
                              key=lambda item: item.mapping_id)),
    ), ()


def _normalize_claim_mapping(
        value: Any, path: str, registries: ProfileRegistries,
        declared_versions: Mapping[str, int], invalid_pack_ids: set[str],
        seen_mapping_ids: set[str]
        ) -> tuple[Optional[ClaimMapping], tuple[ProfileValidationError, ...]]:
    if not isinstance(value, Mapping):
        return None, (ProfileValidationError(
            path, "mapping must be an object", "invalid_profile"),)
    issues: list[ProfileValidationError] = []
    for name in sorted(set(value) - {"mapping_id", "use", "bind"}):
        issues.append(ProfileValidationError(
            _path(path, str(name)), "field is not allowed", "invalid_profile"))

    mapping_id = value.get("mapping_id")
    mapping_id_path = _path(path, "mapping_id")
    if not isinstance(mapping_id, str) or not mapping_id:
        issues.append(ProfileValidationError(
            mapping_id_path, "mapping_id is required", "invalid_mapping_id"))
    elif any(character.isspace() for character in mapping_id):
        issues.append(ProfileValidationError(
            mapping_id_path, "mapping_id must not contain whitespace",
            "invalid_mapping_id"))
    elif mapping_id in seen_mapping_ids:
        issues.append(ProfileValidationError(
            mapping_id_path, f"mapping_id {mapping_id!r} is duplicated",
            "duplicate_mapping_id"))
    else:
        seen_mapping_ids.add(mapping_id)

    use = value.get("use")
    use_path = _path(path, "use")
    pack_id, claim_id = _parse_use_reference(use)
    pack: Optional[PackDescriptor] = None
    claim: Optional[ClaimDescriptor] = None
    if pack_id is None or claim_id is None:
        issues.append(ProfileValidationError(
            use_path, "use must be pack_id/claim_id", "unknown_claim"))
    elif pack_id not in declared_versions:
        issues.append(ProfileValidationError(
            use_path, f"pack {pack_id!r} is not declared in packs", "unknown_pack"))
    elif pack_id not in invalid_pack_ids:
        pack = registries.packs.get(pack_id, declared_versions[pack_id])
        if pack is not None:
            claim = pack.claim(claim_id)
            if claim is None:
                issues.append(ProfileValidationError(
                    use_path,
                    f"claim {claim_id!r} is not registered in pack {pack_id!r}",
                    "unknown_claim"))

    bind_value = value.get("bind")
    bind_path = _path(path, "bind")
    if not isinstance(bind_value, Mapping):
        issues.append(ProfileValidationError(
            bind_path, "bind must be an object", "invalid_binding"))
        bind_value = {}
    normalized_bindings: dict[str, BindingDefinition] = {}
    if claim is not None:
        for role_id in sorted(set(bind_value) - claim.role_ids):
            issues.append(ProfileValidationError(
                _path(bind_path, str(role_id)),
                f"role {role_id!r} is not registered for {pack_id}/{claim_id}",
                "unknown_role"))
        for role_id in sorted(claim.required_role_ids - set(bind_value)):
            issues.append(ProfileValidationError(
                _path(bind_path, role_id),
                f"{pack_id}/{claim_id} requires {role_id}",
                "missing_required_role"))
        for role_id in sorted(set(bind_value) & claim.role_ids):
            role = claim.role(role_id)
            assert role is not None
            binding, binding_issues = registries.binding_kinds.normalize_binding(
                bind_value[role_id], path=_path(bind_path, role_id), role=role)
            issues.extend(binding_issues)
            if binding is not None:
                normalized_bindings[role_id] = binding

    ordered_issues = _sort_issues(issues)
    if ordered_issues:
        return None, ordered_issues
    assert isinstance(mapping_id, str) and isinstance(use, str)
    return ClaimMapping(mapping_id=mapping_id, use=use,
                        bind=MappingProxyType(normalized_bindings)), ()


def _parse_pack_reference(
        value: Any, path: str
        ) -> tuple[Optional[PackReference], Optional[ProfileValidationError]]:
    if not isinstance(value, str):
        return None, ProfileValidationError(
            path, "pack reference must be pack_id@version", "unknown_pack")
    pack_id, separator, version_text = value.rpartition("@")
    if (not separator or not pack_id or not version_text.isdigit()
            or any(character.isspace() for character in value)):
        return None, ProfileValidationError(
            path, "pack reference must be pack_id@version", "unknown_pack")
    return PackReference(pack_id=pack_id, version=int(version_text)), None


def _parse_use_reference(value: Any) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(value, str) or value.count("/") != 1:
        return None, None
    pack_id, claim_id = value.split("/", 1)
    if (not pack_id or not claim_id
            or any(character.isspace() for character in value)):
        return None, None
    return pack_id, claim_id


def _normalize_column_binding(
        payload: Mapping[str, Any], path: str, role: RoleDescriptor,
        registry: BindingKindRegistry
        ) -> tuple[Optional[Mapping[str, Any]], tuple[ProfileValidationError, ...]]:
    del role, registry
    issues = _binding_field_issues(payload, {"column"}, path)
    column = payload.get("column")
    if not isinstance(column, str) or not column.strip():
        issues.append(_binding_issue(_path(path, "column"),
                                     "column name must not be blank"))
    if issues:
        return None, _sort_issues(issues)
    return {"column": column}, ()


def _normalize_constant_binding(
        payload: Mapping[str, Any], path: str, role: RoleDescriptor,
        registry: BindingKindRegistry
        ) -> tuple[Optional[Mapping[str, Any]], tuple[ProfileValidationError, ...]]:
    del registry
    issues = _binding_field_issues(payload, {"value"}, path)
    if "value" not in payload:
        issues.append(_binding_issue(_path(path, "value"),
                                     "constant value must be explicitly present"))
        return None, _sort_issues(issues)
    value = payload["value"]
    if value is None and not role.allow_null:
        issues.append(_binding_issue(
            _path(path, "value"),
            f"null is not allowed for role {role.role_id!r}"))
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        issues.append(_binding_issue(_path(path, "value"),
                                     "constant must be a finite JSON value"))
    if value is not None:
        value_type = _constant_value_type(value)
        symbolic_match = (
            isinstance(value, str) and value in role.symbolic_constants)
        if (not symbolic_match
                and value_type not in role.allowed_constant_types):
            declared = [*sorted(role.symbolic_constants),
                        *sorted(role.allowed_constant_types)]
            issues.append(_binding_issue(
                _path(path, "value"),
                f"constant is not declared for role {role.role_id!r}; "
                f"allowed values or types: {', '.join(declared) or 'none'}"))
    if issues:
        return None, _sort_issues(issues)
    return {"value": value}, ()


def _constant_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "unknown"


def _normalize_lookup_binding(
        payload: Mapping[str, Any], path: str, role: RoleDescriptor,
        registry: BindingKindRegistry
        ) -> tuple[Optional[Mapping[str, Any]], tuple[ProfileValidationError, ...]]:
    del role
    allowed = {"lookup_id", "key", "select", "output_role"}
    issues = _binding_field_issues(payload, allowed, path)
    lookup_id = payload.get("lookup_id")
    if not isinstance(lookup_id, str) or not lookup_id.strip():
        issues.append(_binding_issue(_path(path, "lookup_id"),
                                     "lookup_id must not be blank"))
    if "select" in payload and "output_role" in payload:
        issues.append(_binding_issue(
            _path(path, "select"), "use only select or output_role"))
    select = payload.get("select", payload.get("output_role"))
    if not isinstance(select, str) or not select.strip():
        issues.append(_binding_issue(_path(path, "select"),
                                     "output selection role must not be blank"))
    key_role = RoleDescriptor(
        role_id="lookup_key", kind="lookup_key", required=True,
        allowed_binding_kinds=("column", "constant"), allow_null=False)
    if "key" not in payload:
        issues.append(_binding_issue(_path(path, "key"),
                                     "lookup key binding is required"))
        key_binding = None
    else:
        key_binding, key_issues = registry.normalize_binding(
            payload["key"], path=_path(path, "key"), role=key_role)
        issues.extend(key_issues)
    if issues or key_binding is None:
        return None, _sort_issues(issues)
    return {
        "lookup_id": lookup_id,
        "key": key_binding.to_mapping(),
        "select": select,
    }, ()


def _binding_field_issues(payload: Mapping[str, Any], allowed: set[str],
                          path: str) -> list[ProfileValidationError]:
    return [_binding_issue(_path(path, str(name)), "field is not allowed")
            for name in sorted(set(payload) - allowed)]


def _binding_issue(path: str, message: str) -> ProfileValidationError:
    return ProfileValidationError(path, message, "invalid_binding")


def _sort_issues(issues: Sequence[ProfileValidationError]
                 ) -> tuple[ProfileValidationError, ...]:
    return tuple(sorted(issues, key=lambda item: (item.path, item.code, item.message)))


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({name: _freeze_json(value[name])
                                 for name in sorted(value)})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {name: _thaw_json(value[name]) for name in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _validate_pack_descriptor(descriptor: PackDescriptor) -> None:
    if not isinstance(descriptor, PackDescriptor):
        raise TypeError("pack descriptor must be PackDescriptor")
    if not isinstance(descriptor.pack_id, str) or not descriptor.pack_id.strip():
        raise ValueError("pack_id must not be blank")
    if (isinstance(descriptor.version, bool) or not isinstance(descriptor.version, int)
            or descriptor.version < 1):
        raise ValueError(f"pack {descriptor.pack_id!r} needs a positive version")
    claim_ids = [claim.claim_id for claim in descriptor.claims]
    if not claim_ids or any(not isinstance(item, str) or not item.strip()
                            for item in claim_ids):
        raise ValueError(f"pack {descriptor.pack_id!r} needs named claims")
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError(f"pack {descriptor.pack_id!r} repeats a claim")
    for claim in descriptor.claims:
        role_ids = [role.role_id for role in claim.roles]
        if not role_ids or any(not isinstance(item, str) or not item.strip()
                               for item in role_ids):
            raise ValueError(
                f"claim {descriptor.pack_id}/{claim.claim_id} needs named roles")
        if len(set(role_ids)) != len(role_ids):
            raise ValueError(
                f"claim {descriptor.pack_id}/{claim.claim_id} repeats a role")
        for role in claim.roles:
            if not isinstance(role.kind, str) or not role.kind.strip():
                raise ValueError(f"role {role.role_id!r} needs a kind")
            if (not role.allowed_binding_kinds
                    or any(not isinstance(item, str) or not item.strip()
                           for item in role.allowed_binding_kinds)):
                raise ValueError(
                    f"role {role.role_id!r} needs allowed binding kinds")
            if (len(set(role.allowed_binding_kinds))
                    != len(role.allowed_binding_kinds)):
                raise ValueError(f"role {role.role_id!r} repeats a binding kind")
            if (any(not isinstance(item, str) or not item.strip()
                    for item in role.symbolic_constants)
                    or len(set(role.symbolic_constants))
                    != len(role.symbolic_constants)):
                raise ValueError(
                    f"role {role.role_id!r} has invalid symbolic constants")
            if (any(item not in CONSTANT_VALUE_TYPES
                    for item in role.allowed_constant_types)
                    or len(set(role.allowed_constant_types))
                    != len(role.allowed_constant_types)):
                raise ValueError(
                    f"role {role.role_id!r} has invalid constant value types")
            has_constant_contract = bool(
                role.symbolic_constants or role.allowed_constant_types)
            if "constant" in role.allowed_binding_kinds and not has_constant_contract:
                raise ValueError(
                    f"role {role.role_id!r} allows constants without a value contract")
            if "constant" not in role.allowed_binding_kinds and has_constant_contract:
                raise ValueError(
                    f"role {role.role_id!r} declares constants but does not allow them")


def _parse_source(value: Any, path: str) -> SourceDefinition:
    raw = _expect_mapping(value, path)
    _reject_unknown(raw, {"relation", "related"}, path)
    relation = _nonempty_string(_required(raw, "relation", path),
                                _path(path, "relation"))
    related: dict[str, str] = {}
    if "related" in raw:
        related_raw = _expect_mapping(raw["related"], _path(path, "related"))
        for alias, related_relation in related_raw.items():
            alias_path = _path(_path(path, "related"), str(alias))
            if not isinstance(alias, str) or not alias.strip():
                raise ProfileValidationError(alias_path, "relation alias must not be blank",
                                             "invalid_relation_alias")
            if alias == "primary":
                raise ProfileValidationError(
                    alias_path, "'primary' is reserved for the main source relation",
                    "reserved_relation_alias")
            related[alias] = _nonempty_string(related_relation, alias_path)
    return SourceDefinition(relation=relation, related=MappingProxyType(related))


def _parse_event(value: Any, path: str,
                 registry: TemplateRegistry) -> EventDefinition:
    raw = _expect_mapping(value, path)
    _reject_unknown(raw, {"template", "timezone"}, path)
    template_path = _path(path, "template")
    template = _nonempty_string(_required(raw, "template", path), template_path)
    if registry.get(template) is None:
        raise ProfileValidationError(
            template_path,
            f"template {template!r} is not registered ({', '.join(registry.names())})",
            "unregistered_template")
    timezone_path = _path(path, "timezone")
    timezone = _nonempty_string(_required(raw, "timezone", path), timezone_path)
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ProfileValidationError(timezone_path,
                                     f"timezone {timezone!r} is not recognized",
                                     "invalid_timezone") from None
    return EventDefinition(template=template, timezone=timezone)


def _parse_roles(value: Any, path: str, source: SourceDefinition,
                 template: TemplateDefinition) -> dict[str, ColumnMapping]:
    raw = _expect_mapping(value, path)
    unknown = sorted(set(raw) - template.role_names)
    if unknown:
        name = unknown[0]
        raise ProfileValidationError(
            _path(path, str(name)),
            f"role {name!r} is not registered for template {template.name!r}",
            "unregistered_role")
    missing = sorted(template.required_role_names - set(raw))
    if missing:
        name = missing[0]
        raise ProfileValidationError(
            _path(path, name),
            f"required role {name!r} is missing for template {template.name!r}",
            "missing_required_role")

    roles: dict[str, ColumnMapping] = {}
    allowed_relations = {"primary", *source.related.keys()}
    for name in sorted(raw):
        role_path = _path(path, name)
        role = _expect_mapping(raw[name], role_path)
        _reject_unknown(role, {"column", "status", "relation", "reason"}, role_path)
        column = _nonempty_string(_required(role, "column", role_path),
                                  _path(role_path, "column"))
        status_path = _path(role_path, "status")
        status = _nonempty_string(_required(role, "status", role_path), status_path)
        if status not in MAPPING_STATUSES:
            raise ProfileValidationError(
                status_path,
                f"must be one of {', '.join(sorted(MAPPING_STATUSES))}",
                "invalid_mapping_status")
        relation = None
        if "relation" in role:
            relation = _nonempty_string(role["relation"], _path(role_path, "relation"))
            if relation not in allowed_relations:
                raise ProfileValidationError(
                    _path(role_path, "relation"),
                    f"relation alias {relation!r} is not declared in source.related",
                    "unregistered_relation_alias")
        reason = None
        if "reason" in role:
            reason = _nonempty_string(role["reason"], _path(role_path, "reason"))
        if status == MAPPING_STATUS_INFERRED and reason is None:
            raise ProfileValidationError(
                _path(role_path, "reason"),
                "is required when a column mapping is inferred",
                "missing_inference_reason")
        roles[name] = ColumnMapping(column=column, status=status,
                                    relation=relation, reason=reason)
    return MappingProxyType(roles)


def _parse_entity(value: Any, path: str, roles: Mapping[str, ColumnMapping],
                  template: TemplateDefinition,
                  registry: TypeRegistry) -> EntityDefinition:
    raw = _expect_mapping(value, path)
    _reject_unknown(raw, {"type", "keys"}, path)
    type_path = _path(path, "type")
    entity_type = _nonempty_string(_required(raw, "type", path), type_path)
    type_definition = registry.get(entity_type)
    if type_definition is None:
        raise ProfileValidationError(
            type_path,
            f"entity type {entity_type!r} is not registered ({', '.join(registry.names())})",
            "unregistered_entity_type")
    if entity_type not in template.entity_types:
        raise ProfileValidationError(
            type_path,
            f"entity type {entity_type!r} is not supported by template {template.name!r}",
            "entity_type_not_supported")
    keys = _parse_key_roles(_required(raw, "keys", path), _path(path, "keys"),
                            type_definition.keys, roles)
    return EntityDefinition(type=entity_type, keys=MappingProxyType(keys))


def _parse_containers(value: Any, path: str,
                      roles: Mapping[str, ColumnMapping],
                      template: TemplateDefinition,
                      registry: TypeRegistry) -> dict[str, ContainerDefinition]:
    raw = _expect_mapping(value, path)
    unknown = sorted(set(raw) - template.container_names)
    if unknown:
        name = unknown[0]
        raise ProfileValidationError(
            _path(path, str(name)),
            f"container {name!r} is not registered for template {template.name!r}",
            "unregistered_container_slot")
    missing = sorted(template.required_container_names - set(raw))
    if missing:
        name = missing[0]
        raise ProfileValidationError(
            _path(path, name),
            f"required container {name!r} is missing for template {template.name!r}",
            "missing_required_container")

    containers: dict[str, ContainerDefinition] = {}
    for name in sorted(raw):
        container_path = _path(path, name)
        container = _expect_mapping(raw[name], container_path)
        _reject_unknown(container, {"type", "keys", "lookup"}, container_path)
        type_path = _path(container_path, "type")
        container_type = _nonempty_string(
            _required(container, "type", container_path), type_path)
        type_definition = registry.get(container_type)
        if type_definition is None:
            raise ProfileValidationError(
                type_path,
                f"container type {container_type!r} is not registered "
                f"({', '.join(registry.names())})",
                "unregistered_container_type")
        keys = _parse_key_roles(
            _required(container, "keys", container_path),
            _path(container_path, "keys"), type_definition.keys, roles)
        lookup = None
        if "lookup" in container:
            lookup_path = _path(container_path, "lookup")
            lookup_raw = _expect_mapping(container["lookup"], lookup_path)
            _reject_unknown(lookup_raw, {"event_role", "container_role"}, lookup_path)
            event_role = _role_reference(
                _required(lookup_raw, "event_role", lookup_path),
                _path(lookup_path, "event_role"), roles)
            container_role = _role_reference(
                _required(lookup_raw, "container_role", lookup_path),
                _path(lookup_path, "container_role"), roles)
            lookup = ContainerLookup(event_role=event_role,
                                     container_role=container_role)
        containers[name] = ContainerDefinition(
            type=container_type, keys=MappingProxyType(keys), lookup=lookup)
    return MappingProxyType(containers)


def _parse_key_roles(value: Any, path: str, expected_keys: Sequence[str],
                     roles: Mapping[str, ColumnMapping]) -> dict[str, str]:
    raw = _expect_mapping(value, path)
    expected = set(expected_keys)
    unknown = sorted(set(raw) - expected)
    if unknown:
        name = unknown[0]
        raise ProfileValidationError(
            _path(path, str(name)), f"key {name!r} is not registered for this type",
            "unregistered_key")
    missing = sorted(expected - set(raw))
    if missing:
        name = missing[0]
        raise ProfileValidationError(_path(path, name), "identity key is required",
                                     "missing_key")
    return {name: _role_reference(raw[name], _path(path, name), roles)
            for name in sorted(raw)}


def _role_reference(value: Any, path: str,
                    roles: Mapping[str, ColumnMapping]) -> str:
    role = _nonempty_string(value, path)
    if role not in roles:
        raise ProfileValidationError(
            path, f"role {role!r} is not mapped in profile.roles",
            "unmapped_key_role")
    if not roles[role].column.strip():
        # Defensive: normal parsing rejects this earlier, but injected Profile models
        # must never turn an empty identity column into a valid key.
        raise ProfileValidationError(path, f"role {role!r} has an empty column",
                                     "empty_key_column")
    return role


def _validate_template_definition(definition: TemplateDefinition) -> None:
    if not isinstance(definition.name, str) or not definition.name.strip():
        raise ValueError("template name must not be blank")
    if (not definition.entity_types
            or any(not isinstance(name, str) or not name.strip()
                   for name in definition.entity_types)):
        raise ValueError(f"template {definition.name!r} needs entity types")
    role_names = [role.name for role in definition.roles]
    if (not role_names
            or any(not isinstance(name, str) or not name.strip()
                   for name in role_names)):
        raise ValueError(f"template {definition.name!r} needs named roles")
    if len(set(role_names)) != len(role_names):
        raise ValueError(f"template {definition.name!r} repeats a role")
    container_names = [slot.name for slot in definition.containers]
    if any(not isinstance(name, str) or not name.strip()
           for name in container_names):
        raise ValueError(f"template {definition.name!r} has a blank container slot")
    if len(set(container_names)) != len(container_names):
        raise ValueError(f"template {definition.name!r} repeats a container slot")


def _expect_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileValidationError(path, "must be an object", "invalid_type")
    for name in value:
        if not isinstance(name, str):
            raise ProfileValidationError(
                f"{path}[{name!r}]", "object field names must be strings",
                "invalid_field_name")
    return value


def _required(mapping: Mapping[str, Any], name: str, path: str) -> Any:
    if name not in mapping:
        raise ProfileValidationError(_path(path, name), "is required", "missing_field")
    return mapping[name]


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise ProfileValidationError(path, "must be a string", "invalid_type")
    if not value.strip():
        raise ProfileValidationError(path, "must not be blank", "blank_value")
    return value


def _reject_unknown(mapping: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        name = unknown[0]
        raise ProfileValidationError(_path(path, str(name)), "field is not allowed",
                                     "unknown_field")


def _path(parent: str, name: str) -> str:
    if not parent:
        if name and (name[0].isalpha() or name[0] == "_") and all(
                character.isalnum() or character == "_" for character in name):
            return name
        return f"[{json.dumps(name, ensure_ascii=False)}]"
    if name and (name[0].isalpha() or name[0] == "_") and all(
            character.isalnum() or character == "_" for character in name):
        return f"{parent}.{name}"
    return f"{parent}[{json.dumps(name, ensure_ascii=False)}]"
