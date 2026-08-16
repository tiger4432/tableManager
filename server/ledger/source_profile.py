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
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROFILE_SCHEMA_VERSION = 1
PROFILE_CONFIG_SECTION = "profiles"

MAPPING_STATUS_HUMAN_APPROVED = "human_approved"
MAPPING_STATUS_INFERRED = "inferred"
MAPPING_STATUSES = frozenset({
    MAPPING_STATUS_HUMAN_APPROVED,
    MAPPING_STATUS_INFERRED,
})


class ProfileValidationError(ValueError):
    """A rejected Profile value with a stable code and its exact Profile path."""

    def __init__(self, path: str, message: str, code: str = "invalid_profile"):
        self.path = path
        self.code = code
        self.message = message
        super().__init__(f"{path}: {message}")


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
class SourceOntologyProfile:
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
        """Return the stable UTF-8 JSON representation of this validated Profile."""
        return json.dumps(self.to_mapping(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)


def validate_profile(profile: Mapping[str, Any], *, path: str = "profile",
                     registries: Optional[ProfileRegistries] = None
                     ) -> SourceOntologyProfile:
    """Validate and normalize one Profile without touching runtime config or a DB."""
    if registries is None:
        registries = _default_registries()
    raw = _expect_mapping(profile, path)
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

    return SourceOntologyProfile(
        schema_version=version,
        source=source,
        entity=entity,
        event=event,
        roles=roles,
        containers=containers,
    )


def serialize_profile(profile: Mapping[str, Any] | SourceOntologyProfile, *,
                      path: str = "profile",
                      registries: Optional[ProfileRegistries] = None) -> str:
    validated = (profile if isinstance(profile, SourceOntologyProfile)
                 else validate_profile(profile, path=path, registries=registries))
    return validated.serialize()


def validate_profile_section(config: Mapping[str, Any], *,
                             path: str = "ledger_config",
                             registries: Optional[ProfileRegistries] = None
                             ) -> dict[str, SourceOntologyProfile]:
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
    result: dict[str, SourceOntologyProfile] = {}
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
        "schema_version": PROFILE_SCHEMA_VERSION,
        "config_section": PROFILE_CONFIG_SECTION,
        "mapping_statuses": sorted(MAPPING_STATUSES),
        "templates": registries.templates.public_metadata(),
        "entity_types": registries.entities.public_metadata(),
        "container_types": registries.containers.public_metadata(),
    }


def _default_registries() -> ProfileRegistries:
    from .source_profile_builtins import default_profile_registries
    return default_profile_registries()


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
    if name and (name[0].isalpha() or name[0] == "_") and all(
            character.isalnum() or character == "_" for character in name):
        return f"{parent}.{name}"
    return f"{parent}[{json.dumps(name, ensure_ascii=False)}]"
