"""Pure Ledger v2 registry compiler and immutable setup snapshot.

Stage 3 compiles a validated :class:`LedgerSetupBundle` into sealed read models.
It deliberately has no source-row, database, mapper execution, cursor, gate, store, or
translator capability.  Domain entries come only from the bundle; trusted code is
represented only by closed implementation ID/version pairs supplied by the caller.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Generic, TypeVar

from .setup_bundle import (
    LedgerSetupBundle,
    LedgerSetupValidationError,
    bundle_readiness_errors,
    role_binding_kinds,
    validate_bundle,
    validate_bundle_errors,
)


_DescriptorT = TypeVar("_DescriptorT")


def _versioned_parts(identifier: str) -> tuple[str, int]:
    name, version = identifier.rsplit("@", 1)
    return name, int(version)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({
            str(key): _freeze(value[key]) for key in sorted(value, key=str)
        })
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, _SealedRegistry):
        return value.to_mapping()
    if is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, frozenset):
        return [_plain(item) for item in sorted(value)]
    return value


@dataclass(frozen=True, order=True)
class ImplementationKey:
    implementation_id: str
    implementation_version: int

    def __post_init__(self) -> None:
        if (not isinstance(self.implementation_id, str)
                or not self.implementation_id.strip()
                or self.implementation_id != self.implementation_id.strip()):
            raise ValueError("implementation_id must be a trimmed non-blank string")
        if (isinstance(self.implementation_version, bool)
                or not isinstance(self.implementation_version, int)
                or self.implementation_version < 1):
            raise ValueError("implementation_version must be a positive integer")


@dataclass(frozen=True)
class TrustedImplementationCatalog:
    """Closed code-owned implementation keys; never module/function/path strings."""

    source_preparers: frozenset[ImplementationKey]
    mappers: frozenset[ImplementationKey]

    def __post_init__(self) -> None:
        for name in ("source_preparers", "mappers"):
            values = frozenset(getattr(self, name))
            if any(not isinstance(item, ImplementationKey) for item in values):
                raise TypeError(f"{name} must contain ImplementationKey values")
            object.__setattr__(self, name, values)

    @classmethod
    def build(
        cls,
        *,
        source_preparers: Sequence[tuple[str, int]] = (),
        mappers: Sequence[tuple[str, int]] = (),
    ) -> "TrustedImplementationCatalog":
        return cls(
            source_preparers=frozenset(ImplementationKey(*item) for item in source_preparers),
            mappers=frozenset(ImplementationKey(*item) for item in mappers),
        )


@dataclass(frozen=True)
class PredicateDescriptor:
    predicate_id: str
    version: int
    status: str
    layer: str
    subject_entity_types: tuple[str, ...]
    object_kind: str
    object_entity_types: tuple[str, ...]
    config_path: str


@dataclass(frozen=True)
class EntityTypeDescriptor:
    entity_type_id: str
    version: int
    identity_keys: tuple[str, ...]
    key_types: Mapping[str, str]
    allow_null: bool
    config_path: str


@dataclass(frozen=True)
class RoleDescriptor:
    role_id: str
    kind: str
    required: bool
    allowed_binding_kinds: tuple[str, ...]
    config_path: str


@dataclass(frozen=True)
class RoleReferenceDescriptor:
    role_id: str
    optional: bool


@dataclass(frozen=True)
class EmissionDescriptor:
    predicate_id: str
    subject: RoleReferenceDescriptor
    object_kind: str
    object_role: RoleReferenceDescriptor
    qualifiers: Mapping[str, RoleReferenceDescriptor]
    occurred_at: RoleReferenceDescriptor
    config_path: str


@dataclass(frozen=True)
class ClaimDescriptor:
    claim_id: str
    roles: Mapping[str, RoleDescriptor]
    emission: EmissionDescriptor
    config_path: str


@dataclass(frozen=True)
class PackDescriptor:
    pack_id: str
    version: int
    claims: Mapping[str, ClaimDescriptor]
    config_path: str


@dataclass(frozen=True)
class SourcePreparerDescriptor:
    preparer_id: str
    version: int
    implementation: ImplementationKey
    input_columns: tuple[str, ...]
    output_columns: Mapping[str, str]
    accepts_verified_join_rules: bool
    config_path: str


@dataclass(frozen=True)
class MapperDescriptor:
    mapper_id: str
    version: int
    implementation: ImplementationKey
    unit_kind: str
    input_columns: tuple[str, ...]
    emits: tuple[str, ...]
    config_path: str


@dataclass(frozen=True)
class ProfileMappingDescriptor:
    mapping_id: str
    claim_ref: str
    bindings: Mapping[str, Any]
    config_path: str


@dataclass(frozen=True)
class ProfileDescriptor:
    profile_id: str
    version: int
    source_id: str
    pack_ids: tuple[str, ...]
    mappings: tuple[ProfileMappingDescriptor, ...]
    config_path: str


@dataclass(frozen=True)
class VerifiedJoinDescriptor:
    rule_id: str
    left_table: str
    right_table: str
    join_key: tuple[tuple[str, str], ...]
    expose: tuple[str, ...]
    join_cardinality: str
    fold: Mapping[str, Any]
    verified: bool
    verification_basis: str
    fold_verified: bool
    fold_verification_basis: str
    config_path: str


@dataclass(frozen=True)
class SourcePreparationPlan:
    preparer: SourcePreparerDescriptor
    verified_join_descriptors: tuple[VerifiedJoinDescriptor, ...]


@dataclass(frozen=True)
class OccurredAtPlan:
    column: str
    timezone: str


@dataclass(frozen=True)
class SourceDriverPlan:
    unit: str
    identity: tuple[str, ...]
    group_by: tuple[str, ...]
    order_by: tuple[str, ...]
    occurred_at: OccurredAtPlan
    cursor_columns: tuple[str, ...]
    preparation: SourcePreparationPlan
    mapper: MapperDescriptor


@dataclass(frozen=True)
class SourcePlan:
    source_id: str
    relation: str
    driver: SourceDriverPlan
    profile: ProfileDescriptor
    config_path: str


@dataclass(frozen=True)
class _SealedRegistry(Mapping[str, _DescriptorT], Generic[_DescriptorT]):
    _items: Mapping[str, _DescriptorT]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_items", MappingProxyType({
            key: self._items[key] for key in sorted(self._items)
        }))

    def __getitem__(self, key: str) -> _DescriptorT:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def to_mapping(self) -> dict[str, Any]:
        return {key: _plain(self._items[key]) for key in self}


class VocabularyRegistry(_SealedRegistry[PredicateDescriptor]):
    pass


class EntityTypeRegistry(_SealedRegistry[EntityTypeDescriptor]):
    pass


class PackRegistry(_SealedRegistry[PackDescriptor]):
    pass


class SourcePreparerRegistry(_SealedRegistry[SourcePreparerDescriptor]):
    pass


class MapperRegistry(_SealedRegistry[MapperDescriptor]):
    pass


class ProfileRegistry(_SealedRegistry[ProfileDescriptor]):
    pass


class VerifiedJoinRegistry(_SealedRegistry[VerifiedJoinDescriptor]):
    pass


class SourcePlanRegistry(_SealedRegistry[SourcePlan]):
    pass


class _RegistryBuilder(Generic[_DescriptorT]):
    """Compiler-local add-only builder; ``seal`` returns a read-only Registry."""

    def __init__(self, registry_type: type[_SealedRegistry[_DescriptorT]]):
        self._registry_type = registry_type
        self._items: dict[str, _DescriptorT] = {}
        self._sealed = False

    def add(self, identifier: str, descriptor: _DescriptorT) -> None:
        if self._sealed:
            raise RuntimeError("registry builder is sealed")
        if identifier in self._items:
            raise ValueError(f"duplicate registry identifier {identifier!r}")
        self._items[identifier] = descriptor

    def seal(self) -> _SealedRegistry[_DescriptorT]:
        if self._sealed:
            raise RuntimeError("registry builder is sealed")
        self._sealed = True
        return self._registry_type(self._items)


@dataclass(frozen=True)
class LedgerSetupSnapshot:
    setup_version: int
    canonical_json: str
    sha256: str
    vocabulary: VocabularyRegistry
    entities: EntityTypeRegistry
    source_preparers: SourcePreparerRegistry
    mappers: MapperRegistry
    packs: PackRegistry
    profiles: ProfileRegistry
    verified_joins: VerifiedJoinRegistry
    source_plans: SourcePlanRegistry
    readiness: str

    @property
    def registries(self) -> Mapping[str, _SealedRegistry[Any]]:
        return MappingProxyType({
            "entities": self.entities,
            "mappers": self.mappers,
            "packs": self.packs,
            "profiles": self.profiles,
            "source_preparers": self.source_preparers,
            "sources": self.source_plans,
            "verified_joins": self.verified_joins,
            "vocabulary": self.vocabulary,
        })

    def to_mapping(self) -> dict[str, Any]:
        return {
            "setup_version": self.setup_version,
            "canonical_json": self.canonical_json,
            "sha256": self.sha256,
            "readiness": self.readiness,
            "registries": {
                key: self.registries[key].to_mapping()
                for key in sorted(self.registries)
            },
        }

    def serialize(self) -> str:
        return json.dumps(
            self.to_mapping(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )


def snapshot_compile_errors(
    bundle: LedgerSetupBundle,
    trusted: TrustedImplementationCatalog,
) -> tuple[LedgerSetupValidationError, ...]:
    """Return deterministic compile/readiness errors without creating a snapshot."""
    if not isinstance(bundle, LedgerSetupBundle):
        raise TypeError("snapshot compiler requires a LedgerSetupBundle")
    if not isinstance(trusted, TrustedImplementationCatalog):
        raise TypeError("snapshot compiler requires a TrustedImplementationCatalog")

    structural = validate_bundle_errors(bundle.to_mapping())
    if structural:
        return structural
    validated = validate_bundle(bundle.to_mapping())
    readiness = bundle_readiness_errors(validated)
    if readiness:
        return readiness

    issues: list[LedgerSetupValidationError] = []
    for preparer_id, item in validated.section("source_preparers").items():
        key = ImplementationKey(
            item["implementation_id"], item["implementation_version"])
        if key not in trusted.source_preparers:
            issues.append(_untrusted_implementation_issue(
                kind="source preparer",
                path=f"bundle.source_preparers.{preparer_id}",
                key=key,
                trusted_keys=trusted.source_preparers,
            ))
    for mapper_id, item in validated.section("mappers").items():
        key = ImplementationKey(
            item["implementation_id"], item["implementation_version"])
        if key not in trusted.mappers:
            issues.append(_untrusted_implementation_issue(
                kind="mapper",
                path=f"bundle.mappers.{mapper_id}",
                key=key,
                trusted_keys=trusted.mappers,
            ))
    return tuple(sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message)))


def _untrusted_implementation_issue(
    *,
    kind: str,
    path: str,
    key: ImplementationKey,
    trusted_keys: frozenset[ImplementationKey],
) -> LedgerSetupValidationError:
    known_id = any(
        item.implementation_id == key.implementation_id for item in trusted_keys)
    code = "unsupported_implementation_version" if known_id else "untrusted_implementation"
    leaf = "implementation_version" if known_id else "implementation_id"
    return LedgerSetupValidationError(
        code,
        f"{path}.{leaf}",
        f"{kind} implementation {key.implementation_id!r} "
        f"version {key.implementation_version} is not trusted",
    )


def compile_setup_snapshot(
    bundle: LedgerSetupBundle,
    trusted: TrustedImplementationCatalog,
) -> LedgerSetupSnapshot:
    """Compile one validated, approved Bundle without source or database execution."""
    issues = snapshot_compile_errors(bundle, trusted)
    if issues:
        raise issues[0]
    bundle = validate_bundle(bundle.to_mapping())

    vocabulary = _compile_vocabulary(bundle.section("vocabulary"))
    entities = _compile_entities(bundle.section("entities"))
    preparers = _compile_preparers(bundle.section("source_preparers"))
    mappers = _compile_mappers(bundle.section("mappers"))
    packs = _compile_packs(bundle.section("packs"))
    profiles = _compile_profiles(bundle.section("profiles"))
    verified_joins = _compile_verified_joins(bundle.section("virtual_joins"))
    source_plans = _compile_source_plans(
        bundle.section("sources"), preparers, mappers, profiles, verified_joins)

    canonical_json = bundle.serialize()
    return LedgerSetupSnapshot(
        setup_version=bundle.setup_version,
        canonical_json=canonical_json,
        sha256=sha256(canonical_json.encode("utf-8")).hexdigest(),
        vocabulary=vocabulary,
        entities=entities,
        source_preparers=preparers,
        mappers=mappers,
        packs=packs,
        profiles=profiles,
        verified_joins=verified_joins,
        source_plans=source_plans,
        readiness="ready",
    )


def _compile_vocabulary(section: Mapping[str, Any]) -> VocabularyRegistry:
    builder = _RegistryBuilder(VocabularyRegistry)
    for predicate_id, item in section.items():
        _, version = _versioned_parts(predicate_id)
        obj = item["object"]
        builder.add(predicate_id, PredicateDescriptor(
            predicate_id=predicate_id,
            version=version,
            status=item["status"],
            layer=item["layer"],
            subject_entity_types=tuple(item["subjects"]),
            object_kind=obj["kind"],
            object_entity_types=tuple(obj.get("types", ())),
            config_path=f"bundle.vocabulary.{predicate_id}",
        ))
    return builder.seal()


def _compile_entities(section: Mapping[str, Any]) -> EntityTypeRegistry:
    builder = _RegistryBuilder(EntityTypeRegistry)
    for entity_id, item in section.items():
        _, version = _versioned_parts(entity_id)
        builder.add(entity_id, EntityTypeDescriptor(
            entity_type_id=entity_id,
            version=version,
            identity_keys=tuple(item["keys"]),
            key_types=_freeze(item.get("key_types", {})),
            allow_null=item.get("allow_null", False),
            config_path=f"bundle.entities.{entity_id}",
        ))
    return builder.seal()


def _role_reference(value: str) -> RoleReferenceDescriptor:
    return RoleReferenceDescriptor(
        role_id=value[1:-1] if value.endswith("?") else value[1:],
        optional=value.endswith("?"),
    )


def _compile_packs(section: Mapping[str, Any]) -> PackRegistry:
    builder = _RegistryBuilder(PackRegistry)
    for pack_id, item in section.items():
        _, version = _versioned_parts(pack_id)
        claims: dict[str, ClaimDescriptor] = {}
        for claim_id, claim in item["claims"].items():
            claim_path = f"bundle.packs.{pack_id}.claims.{claim_id}"
            roles: dict[str, RoleDescriptor] = {}
            for role_id, role in claim["roles"].items():
                roles[role_id] = RoleDescriptor(
                    role_id=role_id,
                    kind=role["kind"],
                    required=role["required"],
                    allowed_binding_kinds=role_binding_kinds(role),
                    config_path=f"{claim_path}.roles.{role_id}",
                )
            emission = claim["emit"]
            obj = emission["object"]
            object_ref = obj.get("entity", obj.get("value"))
            claims[claim_id] = ClaimDescriptor(
                claim_id=claim_id,
                roles=_freeze(roles),
                emission=EmissionDescriptor(
                    predicate_id=emission["predicate"],
                    subject=_role_reference(emission["subject"]),
                    object_kind=obj["kind"],
                    object_role=_role_reference(object_ref),
                    qualifiers=_freeze({
                        key: _role_reference(value)
                        for key, value in obj.get("qualifiers", {}).items()
                    }),
                    occurred_at=_role_reference(emission["occurred_at"]),
                    config_path=f"{claim_path}.emit",
                ),
                config_path=claim_path,
            )
        builder.add(pack_id, PackDescriptor(
            pack_id=pack_id,
            version=version,
            claims=_freeze(claims),
            config_path=f"bundle.packs.{pack_id}",
        ))
    return builder.seal()


def _compile_preparers(section: Mapping[str, Any]) -> SourcePreparerRegistry:
    builder = _RegistryBuilder(SourcePreparerRegistry)
    for preparer_id, item in section.items():
        _, version = _versioned_parts(preparer_id)
        builder.add(preparer_id, SourcePreparerDescriptor(
            preparer_id=preparer_id,
            version=version,
            implementation=ImplementationKey(
                item["implementation_id"], item["implementation_version"]),
            input_columns=tuple(item["input_columns"]),
            output_columns=_freeze(item["output_columns"]),
            accepts_verified_join_rules=item["accepts_verified_join_rules"],
            config_path=f"bundle.source_preparers.{preparer_id}",
        ))
    return builder.seal()


def _compile_mappers(section: Mapping[str, Any]) -> MapperRegistry:
    builder = _RegistryBuilder(MapperRegistry)
    for mapper_id, item in section.items():
        _, version = _versioned_parts(mapper_id)
        builder.add(mapper_id, MapperDescriptor(
            mapper_id=mapper_id,
            version=version,
            implementation=ImplementationKey(
                item["implementation_id"], item["implementation_version"]),
            unit_kind=item["unit"]["kind"],
            input_columns=tuple(item["input_columns"]),
            emits=tuple(item["emits"]),
            config_path=f"bundle.mappers.{mapper_id}",
        ))
    return builder.seal()


def _compile_profiles(section: Mapping[str, Any]) -> ProfileRegistry:
    builder = _RegistryBuilder(ProfileRegistry)
    for profile_id, item in section.items():
        _, version = _versioned_parts(profile_id)
        mappings = tuple(ProfileMappingDescriptor(
            mapping_id=mapping["mapping_id"],
            claim_ref=mapping["use"],
            bindings=_freeze(mapping["bind"]),
            config_path=f"bundle.profiles.{profile_id}.mappings[{index}]",
        ) for index, mapping in enumerate(item["mappings"]))
        builder.add(profile_id, ProfileDescriptor(
            profile_id=profile_id,
            version=version,
            source_id=item["source"],
            pack_ids=tuple(item["packs"]),
            mappings=mappings,
            config_path=f"bundle.profiles.{profile_id}",
        ))
    return builder.seal()


def _compile_verified_joins(section: Mapping[str, Any]) -> VerifiedJoinRegistry:
    builder = _RegistryBuilder(VerifiedJoinRegistry)
    for rule_id, item in section.items():
        if not item["enabled"]:
            continue
        builder.add(rule_id, VerifiedJoinDescriptor(
            rule_id=rule_id,
            left_table=item["left_table"],
            right_table=item["right_table"],
            join_key=tuple((pair["left"], pair["right"]) for pair in item["join_key"]),
            expose=tuple(item["expose"]),
            join_cardinality=item["join_cardinality"],
            fold=_freeze(item.get("fold", {})),
            verified=True,
            verification_basis="catalog_declared_unique",
            fold_verified=bool(item.get("fold")),
            fold_verification_basis=(
                "notation_rule_vocabulary" if item.get("fold") else "not_declared"),
            config_path=f"bundle.virtual_joins.{rule_id}",
        ))
    return builder.seal()


def _compile_source_plans(
    section: Mapping[str, Any],
    preparers: SourcePreparerRegistry,
    mappers: MapperRegistry,
    profiles: ProfileRegistry,
    verified_joins: VerifiedJoinRegistry,
) -> SourcePlanRegistry:
    builder = _RegistryBuilder(SourcePlanRegistry)
    for source_id, item in section.items():
        path = f"bundle.sources.{source_id}"
        driver = item["driver"]
        preparation = driver["preparation"]
        builder.add(source_id, SourcePlan(
            source_id=source_id,
            relation=item["relation"],
            driver=SourceDriverPlan(
                unit=driver["unit"],
                identity=tuple(driver["identity"]),
                group_by=tuple(driver["group_by"]),
                order_by=tuple(driver["order_by"]),
                occurred_at=OccurredAtPlan(
                    column=driver["occurred_at"]["column"],
                    timezone=driver["occurred_at"]["timezone"],
                ),
                cursor_columns=tuple(driver["cursor"]["columns"]),
                preparation=SourcePreparationPlan(
                    preparer=preparers[preparation["preparer_id"]],
                    verified_join_descriptors=tuple(
                        verified_joins[rule_id]
                        for rule_id in preparation["inherit_virtual_join_rules"]
                    ),
                ),
                mapper=mappers[driver["mapper_id"]],
            ),
            profile=profiles[item["profile_id"]],
            config_path=path,
        ))
    return builder.seal()
