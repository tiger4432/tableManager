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

from verified_join_contract import (
    VerifiedJoinDescriptor,
    is_physically_verified_descriptor,
)

from .setup_bundle import (
    LedgerSetupBundle,
    LedgerSetupValidationError,
    bundle_readiness_errors,
    predicate_claim,
    role_binding_kinds,
    validate_bundle,
    validate_bundle_errors,
)


_DescriptorT = TypeVar("_DescriptorT")
#: 4 since 2026-08-21: the read path reads a varchar occurred_at instead of refusing it,
#: so the same rows now yield atoms with DIFFERENT instants.  Without this move a cursor
#: would call the setup unchanged and keep stacking new-reading atoms onto old-reading
#: ones with nothing recording which is which.
SNAPSHOT_COMPILER_VERSION = 4


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
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, frozenset):
        return [_plain(item) for item in sorted(value)]
    return value


def _semantic_plain(value: Any) -> Any:
    if isinstance(value, _SealedRegistry):
        return {key: _semantic_plain(value[key]) for key in value}
    if isinstance(value, Mapping):
        return {str(key): _semantic_plain(value[key])
                for key in sorted(value, key=str)}
    if is_dataclass(value):
        return {
            field.name: _semantic_plain(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_") and field.name != "config_path"
        }
    if isinstance(value, (tuple, list)):
        return [_semantic_plain(item) for item in value]
    if isinstance(value, frozenset):
        return [_semantic_plain(item) for item in sorted(value)]
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
    subject_entity_types: tuple[str, ...]
    object_kind: str
    object_entity_types: tuple[str, ...]
    required_qualifiers: tuple[str, ...]
    optional_qualifiers: tuple[str, ...]
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
    #: 🔴 Always `()` since `packs` left -- nothing writes the roster it carries, so this
    #: field is a shape the compiled plan preserves rather than a value it computes.
    #: Measured 2026-08-22 across the live config, the sample and every producer in
    #: `server/`: zero. Deleting it would have to be rebuilt the day rosters return, and
    #: defaulting it to something non-empty would invent a constraint nobody declared.
    allowed_values: tuple[str, ...]
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
    object_role: RoleReferenceDescriptor | None
    qualifiers: Mapping[str, RoleReferenceDescriptor]
    occurred_at: RoleReferenceDescriptor
    config_path: str


@dataclass(frozen=True)
class ClaimDescriptor:
    """What one predicate forces: its Roles and the emission that fills them.

    🔴 NOT COMPILED FROM A `packs` SECTION SINCE 2026-08-21 -- `setup_bundle.predicate_claim`
    derives the body from the vocabulary, and `claim_id` IS the predicate id.  See that
    function for what was measured before the section went.  The descriptor kept its shape
    on purpose: every reader of `roles` and `emission` is unchanged, and only where the
    material comes from moved.
    """

    claim_id: str
    roles: Mapping[str, RoleDescriptor]
    emission: EmissionDescriptor
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
    """One source's mapper.

    🔴 `emits` IS DERIVED, NOT DECLARED, as of 2026-08-21 (owner: 「닿을 수 없다면 선언도
    닿으면 안됨」).  `map` no longer carries a list of refs, because a mapper implementation
    cannot answer which sentences it produces -- it knows `SentenceShape`, and the naming
    runs config -> mapper in one direction.  The set is built here from
    `bind.mappings.<sentence>.predicate`, the one declaration that owns the answer, so the
    field a reader already had is still there and the question an author could only get
    wrong is not.  (It held `<pack>/<claim>` refs until the `packs` section went, later the
    same day; it now holds predicate ids, which is what a mapping names.)
    """

    mapper_id: str
    version: int
    implementation: ImplementationKey
    unit_kind: str
    unit_columns: tuple[str, ...]
    input_columns: tuple[str, ...]
    emits: tuple[str, ...]
    config_path: str


@dataclass(frozen=True)
class ProfileMappingDescriptor:
    """One Profile mapping: which predicate it utters, and how its Roles are filled.

    🔴 NO `mapping_id` AND NO `sentence` FIELD as of 2026-08-21 (owner: 「같이 넣어」).  The
    mapping is FILED under the sentence it realizes -- `ProfileDescriptor.mappings` is a
    map keyed by that name -- so an id field could only be a fourth copy of a name the key
    already carries, and `sentence` would be the key restated inside its own value.  The
    one place either was read, `roleframe.ProfileSentences._resolve`, now takes the key.
    """

    predicate_id: str
    bindings: Mapping[str, Any]
    config_path: str


@dataclass(frozen=True)
class ProfileDescriptor:
    """One source's profile, keyed and identified by the source that holds it.

    🔴 NO `version` FIELD, AND THE ABSENCE IS A DECISION.  A preparer and a mapper kept
    theirs through the same absorption because their bodies still declare
    `implementation_version` -- a real number that moves when the code contract moves.  A
    profile body declares no version of any kind once `profile@1` is gone, so the only
    ways to keep the field were a literal that can never change or a copy of something
    else's number.  Both would ride into `canonical_content_json` and therefore into
    `snapshot_sha256`, telling every reader that profiles are versioned when nothing can
    version them.  Measured before removing it: no execution path read it -- `roleframe`
    and `source_preparation` use `mappings`, `source_id` and `config_path` only.

    🔴 `pack_ids` LEFT ON 2026-08-21 FOR THE SAME MEASUREMENT.  `bind.packs` was
    `sorted(set(...))` of the packs `mappings.<sentence>.use` names, checked both ways, and nothing
    but that check ever read the compiled copy.  A mapping's `use` still names its pack, so
    the answer is not lost -- only the restatement is.  (`use` itself became `predicate`
    later the same day, when the `packs` section went.)

    🔴 `mappings` IS A MAP KEYED BY SENTENCE as of 2026-08-21, not a tuple.  That is what
    makes `ProfileSentences._resolve` one key lookup, and it is also what makes two
    mappings claiming one sentence UNWRITABLE rather than merely refused.
    """

    profile_id: str
    source_id: str
    mappings: Mapping[str, ProfileMappingDescriptor]
    config_path: str


@dataclass(frozen=True)
class SourcePreparationPlan:
    preparer: SourcePreparerDescriptor
    verified_join_descriptors: tuple[VerifiedJoinDescriptor, ...]


#: What each declared basis reads INSTEAD of a world-time column. ``created_at`` is put on
#: every table by the schema builder, so it exists wherever a source can be declared at all,
#: and it is STORED - re-running a backfill reads back the same instant instead of inventing
#: a fresh one, which is what makes an atom reproducible.
OCCURRED_AT_BASIS_COLUMNS = {"ingested": "created_at"}


@dataclass(frozen=True)
class OccurredAtPlan:
    """Where one source's time came from.

    ``column`` is always a column the engine can read, so the runtime never learns about
    this distinction. ``basis`` is None when that column IS world time as the table records
    it, and names the admission otherwise. The atom carries the admission because atoms
    outlive declarations - a reader months from now cannot re-read a config that has since
    changed to find out whether a timestamp meant "when it happened" or "when we saw it".
    """

    column: str
    timezone: str
    basis: str | None = None


@dataclass(frozen=True)
class RegistrationProbePlan:
    """One entity type's first-sight probe over BASE (pre-preparation) columns."""

    entity_type: str
    identity_key: str
    columns: tuple[str, ...]
    list_separator: str | None

    @property
    def subject_type(self) -> str:
        """The unversioned name atoms carry, e.g. ``Lot@1`` -> ``Lot``."""
        return self.entity_type.split("@", 1)[0]


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
    registration_probe: tuple[RegistrationProbePlan, ...] = ()


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


class ClaimRegistry(_SealedRegistry[ClaimDescriptor]):
    """Every predicate's derived Claim, keyed by the predicate id it belongs to."""


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
    compiler_contract_version: int
    setup_version: int
    bundle_canonical_json: str
    bundle_sha256: str
    canonical_content_json: str
    snapshot_sha256: str
    vocabulary: VocabularyRegistry
    entities: EntityTypeRegistry
    source_preparers: SourcePreparerRegistry
    mappers: MapperRegistry
    claims: ClaimRegistry
    profiles: ProfileRegistry
    verified_joins: VerifiedJoinRegistry
    source_plans: SourcePlanRegistry
    readiness: str

    @property
    def registries(self) -> Mapping[str, _SealedRegistry[Any]]:
        return MappingProxyType({
            "entities": self.entities,
            "claims": self.claims,
            "mappers": self.mappers,
            "profiles": self.profiles,
            "source_preparers": self.source_preparers,
            "sources": self.source_plans,
            "verified_joins": self.verified_joins,
            "vocabulary": self.vocabulary,
        })

    def to_mapping(self) -> dict[str, Any]:
        return {
            "compiler_contract_version": self.compiler_contract_version,
            "setup_version": self.setup_version,
            "bundle_canonical_json": self.bundle_canonical_json,
            "bundle_sha256": self.bundle_sha256,
            "canonical_content_json": self.canonical_content_json,
            "snapshot_sha256": self.snapshot_sha256,
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
    verified_joins: Sequence[VerifiedJoinDescriptor] = (),
    *,
    catalog: Mapping[str, Any] | None = None,
) -> tuple[LedgerSetupValidationError, ...]:
    """Return deterministic compile/readiness errors without creating a snapshot.

    `catalog` must be the SAME physical catalog the bundle was loaded against.  This
    function re-validates, and re-validating against a different catalog would let a
    bundle load clean and then fail to compile for reasons the loader never saw -- two
    verifiers disagreeing, which is the shape this whole change removes.  `None` means
    the live `table_config.json`, which is what production loads with.
    """
    if not isinstance(bundle, LedgerSetupBundle):
        raise TypeError("snapshot compiler requires a LedgerSetupBundle")
    if not isinstance(trusted, TrustedImplementationCatalog):
        raise TypeError("snapshot compiler requires a TrustedImplementationCatalog")

    structural = validate_bundle_errors(bundle.to_mapping(), catalog=catalog)
    if structural:
        return structural
    validated = validate_bundle(bundle.to_mapping(), catalog=catalog)
    readiness = bundle_readiness_errors(validated)
    if readiness:
        return readiness

    issues: list[LedgerSetupValidationError] = list(
        _verified_join_errors(validated, verified_joins))
    for source_id, source in validated.section("sources").items():
        for kind, clause, trusted_keys in (
            ("source preparer", "prepare", trusted.source_preparers),
            ("mapper", "map", trusted.mappers),
        ):
            item = source[clause]
            key = ImplementationKey(
                item["implementation_id"], item["implementation_version"])
            if key not in trusted_keys:
                issues.append(_untrusted_implementation_issue(
                    kind=kind,
                    path=f"bundle.sources.{source_id}.{clause}",
                    key=key,
                    trusted_keys=trusted_keys,
                ))
    return tuple(sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message)))


def _verified_join_errors(
    bundle: LedgerSetupBundle,
    verified_joins: Sequence[VerifiedJoinDescriptor],
) -> tuple[LedgerSetupValidationError, ...]:
    issues: list[LedgerSetupValidationError] = []
    supplied: dict[str, VerifiedJoinDescriptor] = {}
    for index, descriptor in enumerate(verified_joins):
        path = f"verified_joins[{index}]"
        if not is_physically_verified_descriptor(descriptor):
            issues.append(LedgerSetupValidationError(
                "invalid_verified_join", path,
                "must be a VerifiedJoinDescriptor produced by physical verification"))
            continue
        if descriptor.rule_id in supplied:
            issues.append(LedgerSetupValidationError(
                "duplicate_verified_join", path,
                f"verified join {descriptor.rule_id!r} is duplicated"))
            continue
        supplied[descriptor.rule_id] = descriptor

    declared = bundle.section("virtual_joins")
    enabled = {rule_id: rule for rule_id, rule in declared.items() if rule["enabled"]}
    for rule_id in sorted(enabled):
        path = f"bundle.virtual_joins.{rule_id}"
        descriptor = supplied.get(rule_id)
        if descriptor is None:
            issues.append(LedgerSetupValidationError(
                "unverified_join", path,
                f"join rule {rule_id!r} requires a physical UNIQUE "
                "verification descriptor"))
            continue
        rule = enabled[rule_id]
        expected_pairs = tuple(
            (pair["left"], pair["right"]) for pair in rule["join_key"])
        expected_fold = rule.get("fold") or {}
        actual_folds = tuple(dict(item) for item in descriptor.pair_folds)
        expected_folds = tuple(dict(expected_fold) for _ in expected_pairs)
        matches = (
            descriptor["left_table"] == rule["left_table"]
            and descriptor["right_table"] == rule["right_table"]
            and descriptor.join_key_pairs == expected_pairs
            and tuple(descriptor["expose"]) == tuple(rule["expose"])
            and descriptor["join_cardinality"] == rule["join_cardinality"]
            and actual_folds == expected_folds
            and descriptor.verification_basis == "physical_unique_index"
        )
        if not matches:
            issues.append(LedgerSetupValidationError(
                "verified_join_mismatch", path,
                f"physical verification descriptor does not match join rule {rule_id!r}"))
    for rule_id in sorted(set(supplied) - set(enabled)):
        issues.append(LedgerSetupValidationError(
            "unknown_verified_join", f"verified_joins.{rule_id}",
            f"verified join {rule_id!r} has no enabled Bundle declaration"))
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
    verified_joins: Sequence[VerifiedJoinDescriptor] = (),
    *,
    catalog: Mapping[str, Any] | None = None,
) -> LedgerSetupSnapshot:
    """Compile one validated, approved Bundle without source or database execution.

    `catalog` is the physical relation shape; see `snapshot_compile_errors`.
    """
    issues = snapshot_compile_errors(
        bundle, trusted, verified_joins, catalog=catalog)
    if issues:
        raise issues[0]
    bundle = validate_bundle(bundle.to_mapping(), catalog=catalog)

    vocabulary = _compile_vocabulary(bundle.section("vocabulary"))
    entities = _compile_entities(bundle.section("entities"))
    preparers = _compile_preparers(bundle.section("sources"))
    mappers = _compile_mappers(bundle.section("sources"))
    claims = _compile_claims(bundle.section("vocabulary"))
    profiles = _compile_profiles(bundle.section("sources"))
    verified_join_registry = _compile_verified_joins(verified_joins)
    source_plans = _compile_source_plans(
        bundle.section("sources"), preparers, mappers, profiles,
        verified_join_registry, entities)

    bundle_canonical_json = bundle.serialize()
    bundle_sha256 = sha256(bundle_canonical_json.encode("utf-8")).hexdigest()
    registries = {
        "claims": claims,
        "entities": entities,
        "mappers": mappers,
        "profiles": profiles,
        "source_preparers": preparers,
        "sources": source_plans,
        "verified_joins": verified_join_registry,
        "vocabulary": vocabulary,
    }
    content = {
        "compiler_contract_version": SNAPSHOT_COMPILER_VERSION,
        "setup_version": bundle.setup_version,
        "bundle_sha256": bundle_sha256,
        "readiness": "ready",
        # 🔴 THE CURSOR NO LONGER COMPARES AGAINST THIS VALUE (2026-08-21). It is still
        # every source's material at once, so it moves when ANY source is edited; that is
        # correct for "which WHOLE setup produced this atom" (`setup_snapshot_hash`) and
        # wrong for "may THIS cursor keep going". The cursor asks
        # `source_cursor_fingerprint` below instead.
        #
        # `declarations` used to carry `chains` and `enrichments` into the snapshot hash.
        # Neither reached execution, so editing an approval-reference string moved the
        # hash and blocked the cursor with `cursor_snapshot_reset_required` for a change
        # that could not alter one atom. Both sections are gone; the hash now covers only
        # what can change an atom.
        "registries": {
            key: _semantic_plain(registries[key]) for key in sorted(registries)
        },
    }
    canonical_content_json = json.dumps(
        content, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False)
    return LedgerSetupSnapshot(
        compiler_contract_version=SNAPSHOT_COMPILER_VERSION,
        setup_version=bundle.setup_version,
        bundle_canonical_json=bundle_canonical_json,
        bundle_sha256=bundle_sha256,
        canonical_content_json=canonical_content_json,
        snapshot_sha256=sha256(canonical_content_json.encode("utf-8")).hexdigest(),
        vocabulary=vocabulary,
        entities=entities,
        source_preparers=preparers,
        mappers=mappers,
        claims=claims,
        profiles=profiles,
        verified_joins=verified_join_registry,
        source_plans=source_plans,
        readiness="ready",
    )


def _reachable_entity_ids(value: Any, known: frozenset[str], found: set[str]) -> None:
    """Collect every declared entity id that OCCURS anywhere in already-plain material.

    🔴 SCANNED, NOT ENUMERATED, AND DELIBERATELY SO. An entity id reaches a source through
    at least four unrelated shapes -- a predicate's `subjects`, a predicate's
    `object.types`, a `read.registration_probe[].entity_type`, and a binding's
    `entity_type` nested under `bind.mappings.<sentence>.bind.<role>` -- and a binding may
    nest further. Enumerating those four would be a list that goes silently WRONG the day
    a fifth shape is declared, and a closure that is too SMALL fails by not blocking a
    cursor that should have been blocked. A scan over the material errs the other way:
    a new shape is covered the day it lands, and the worst case is an extra entity in the
    closure, which only ever blocks more than strictly necessary.

    Keys are matched as well as values because an entity id is a versioned name
    (`Lot@1`), so a coincidental match would have to be that exact string.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key in known:
                found.add(key)
            _reachable_entity_ids(item, known, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reachable_entity_ids(item, known, found)
    elif isinstance(value, str) and value in known:
        found.add(value)


def source_cursor_fingerprint(
    snapshot: LedgerSetupSnapshot, source_id: str) -> str:
    """The hash of the material that can change ONE source's atoms.

    🔴 WHY THIS EXISTS AT ALL. `snapshot_sha256` covers every registry, so it moves when
    ANY source's declaration is edited. Every cursor compared against that one value, so
    editing `lot_event`'s bindings refused `dt_job`'s backfill with
    `cursor_snapshot_reset_required` -- a refusal for a change that could not alter one
    `dt_job` atom. `compile_setup_snapshot` already wrote the principle down ("the hash
    covers only what can change an atom"); this keeps it PER SOURCE.

    The closure is transitive and deliberately errs LARGE:

        the source plan       relation, read, prepare (preparer + verified joins),
                              map (mapper), bind (profile) -- all of it, since the
                              bodies now live inside the source
        the predicates        every predicate a `bind.mappings.<sentence>.predicate`
                              names.  This used to be "the packs, WHOLE, plus the
                              predicates their claims emitted".  The packs went on
                              2026-08-21 and the pack-shaped widening went with them:
                              a predicate IS the unit an author edits now, so the
                              closure lands exactly on it with nothing left to widen to
        the entities          every entity id occurring in the above (see
                              `_reachable_entity_ids`)
        + compiler_contract_version and setup_version -- when the grammar generation
          moves, every source's material moves, and that is correct

    🔴 SHARED MATERIAL MOVES EVERY SOURCE THAT TOUCHES IT, ON PURPOSE. `register@1` is
    named by both sources today, so editing it moves both fingerprints. That is
    the whole point: a closure narrowed to "my own declarations" would let a source keep
    running against a predicate that changed under it, which is silent and worse than
    blocking one cursor too many.

    🔴 `bundle_sha256` IS NOT IN HERE, and its absence is the fix. It is the hash of the
    whole config file, so including it would restore exactly the globality being removed.
    It stays in `snapshot_sha256` -- the atom's `setup_snapshot_hash` still answers "which
    WHOLE setup produced this row", which is a different question from "may this cursor
    keep going".
    """
    plan = snapshot.source_plans[source_id]
    predicate_ids = sorted({
        mapping.predicate_id for mapping in plan.profile.mappings.values()
    })
    material: dict[str, Any] = {
        "compiler_contract_version": snapshot.compiler_contract_version,
        "setup_version": snapshot.setup_version,
        "source": _semantic_plain(plan),
        "claims": {
            predicate_id: _semantic_plain(snapshot.claims[predicate_id])
            for predicate_id in predicate_ids
        },
        "vocabulary": {
            predicate_id: _semantic_plain(snapshot.vocabulary[predicate_id])
            for predicate_id in predicate_ids
        },
    }
    entity_ids: set[str] = set()
    _reachable_entity_ids(material, frozenset(snapshot.entities), entity_ids)
    material["entities"] = {
        entity_id: _semantic_plain(snapshot.entities[entity_id])
        for entity_id in sorted(entity_ids)
    }
    canonical = json.dumps(
        material, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def cursor_translator_version(
    snapshot: LedgerSetupSnapshot, source_id: str) -> str:
    """The string a source's cursor stores and is compared against. ONE spelling.

    The reader (`backfill._run_v2_lineage`) and the writer (`runtime_v2.execute_cursor_batch`)
    both call this. They used to build `f"ledger-v2:{snapshot_sha256}"` separately, and two
    spellings of the value a guard compares is how a guard stops guarding.
    """
    return f"ledger-v2:{source_cursor_fingerprint(snapshot, source_id)}"


def _compile_vocabulary(section: Mapping[str, Any]) -> VocabularyRegistry:
    builder = _RegistryBuilder(VocabularyRegistry)
    for predicate_id, item in section.items():
        _, version = _versioned_parts(predicate_id)
        obj = item["object"]
        builder.add(predicate_id, PredicateDescriptor(
            predicate_id=predicate_id,
            version=version,
            status=item["status"],
            subject_entity_types=tuple(item["subjects"]),
            object_kind=obj["kind"],
            object_entity_types=tuple(obj.get("types", ())),
            required_qualifiers=tuple(obj["qualifiers"]["required"]),
            optional_qualifiers=tuple(obj["qualifiers"]["optional"]),
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


def _compile_claims(section: Mapping[str, Any]) -> ClaimRegistry:
    """One Claim per PREDICATE, derived -- the `packs` section is gone.

    The body comes from `setup_bundle.predicate_claim`, so this function does exactly what
    it did before: turn a Role map and an `emit` clause into descriptors.  What changed is
    who wrote the Role map, and therefore that two predicates can no longer disagree about
    the same grammar.  `config_path` points at the predicate because that is now the
    declaration a refusal should send an author to.
    """
    builder = _RegistryBuilder(ClaimRegistry)
    for predicate_id, predicate in section.items():
        claim = predicate_claim(predicate_id, predicate)
        claim_path = f"bundle.vocabulary.{predicate_id}"
        roles: dict[str, RoleDescriptor] = {}
        for role_id, role in claim["roles"].items():
            roles[role_id] = RoleDescriptor(
                role_id=role_id,
                kind=role["kind"],
                required=role["required"],
                allowed_binding_kinds=role_binding_kinds(role),
                # 🔴 Reads a key no declaration carries any more, so this is `()` every
                # time. It stays because the compiler should copy what the grammar allows,
                # not what today's files happen to hold -- the day the roster returns, this
                # line already carries it. See the field's own note above.
                allowed_values=tuple(role.get("allowed_values", ())),
                config_path=claim_path,
            )
        emission = claim["emit"]
        obj = emission["object"]
        object_ref = obj.get("entity", obj.get("value"))
        builder.add(predicate_id, ClaimDescriptor(
            claim_id=predicate_id,
            roles=_freeze(roles),
            emission=EmissionDescriptor(
                predicate_id=emission["predicate"],
                subject=_role_reference(emission["subject"]),
                object_kind=obj["kind"],
                object_role=(None if object_ref is None
                             else _role_reference(object_ref)),
                qualifiers=_freeze({
                    key: _role_reference(value)
                    for key, value in obj.get("qualifiers", {}).items()
                }),
                occurred_at=_role_reference(emission["occurred_at"]),
                config_path=claim_path,
            ),
            config_path=claim_path,
        ))
    return builder.seal()


def _compile_preparers(section: Mapping[str, Any]) -> SourcePreparerRegistry:
    """One preparer per SOURCE, keyed by the source it prepares.

    🔴 THE KEY IS THE SOURCE ID BECAUSE THE DECLARATION NO LONGER HAS ONE.  The body moved
    inline to `sources.<id>.prepare` on 2026-08-20, so "which preparer" and
    "which source" are the same question and there is nothing else to key on.  The registry
    itself stays: `LedgerSetupSnapshot.registries` publishes it, the explorer reads it, and
    the trust check walks it -- only what identifies a member changed.

    `version` therefore tracks the IMPLEMENTATION's version, which is the only version the
    body still carries.
    """
    builder = _RegistryBuilder(SourcePreparerRegistry)
    for source_id, source in section.items():
        item = source["prepare"]
        builder.add(source_id, SourcePreparerDescriptor(
            preparer_id=source_id,
            version=item["implementation_version"],
            implementation=ImplementationKey(
                item["implementation_id"], item["implementation_version"]),
            input_columns=tuple(item["input_columns"]),
            output_columns=_freeze(item["output_columns"]),
            accepts_verified_join_rules=item["accepts_verified_join_rules"],
            config_path=f"bundle.sources.{source_id}.prepare",
        ))
    return builder.seal()


def _compile_mappers(section: Mapping[str, Any]) -> MapperRegistry:
    """One mapper per SOURCE, keyed by the source it maps -- see `_compile_preparers`."""
    builder = _RegistryBuilder(MapperRegistry)
    for source_id, source in section.items():
        item = source["map"]
        builder.add(source_id, MapperDescriptor(
            mapper_id=source_id,
            version=item["implementation_version"],
            implementation=ImplementationKey(
                item["implementation_id"], item["implementation_version"]),
            unit_kind=item["unit"]["kind"],
            unit_columns=tuple(item["unit"].get("columns", ())),
            input_columns=tuple(item["input_columns"]),
            emits=tuple(sorted({
                mapping["predicate"]
                for mapping in source["bind"]["mappings"].values()})),
            config_path=f"bundle.sources.{source_id}.map",
        ))
    return builder.seal()


def _compile_profiles(section: Mapping[str, Any]) -> ProfileRegistry:
    """One profile per SOURCE, keyed by the source it maps -- see `_compile_preparers`."""
    builder = _RegistryBuilder(ProfileRegistry)
    for source_id, source in section.items():
        item = source["bind"]
        path = f"bundle.sources.{source_id}.bind"
        mappings = MappingProxyType({
            sentence: ProfileMappingDescriptor(
                predicate_id=mapping["predicate"],
                bindings=_freeze(mapping["bind"]),
                config_path=f"{path}.mappings.{sentence}",
            )
            for sentence, mapping in sorted(item["mappings"].items())
        })
        builder.add(source_id, ProfileDescriptor(
            profile_id=source_id,
            source_id=source_id,
            mappings=mappings,
            config_path=path,
        ))
    return builder.seal()


def _compile_verified_joins(
    descriptors: Sequence[VerifiedJoinDescriptor],
) -> VerifiedJoinRegistry:
    builder = _RegistryBuilder(VerifiedJoinRegistry)
    for descriptor in sorted(descriptors, key=lambda item: item.rule_id):
        builder.add(descriptor.rule_id, descriptor)
    return builder.seal()


def _occurred_at_plan(declared: Mapping) -> OccurredAtPlan:
    """Resolve a declared time origin down to a column the engine can read.

    The bundle validator has already refused anything that is neither shape, so exactly
    one of the two branches applies here.
    """
    basis = declared.get("basis")
    if isinstance(basis, str):
        return OccurredAtPlan(
            column=OCCURRED_AT_BASIS_COLUMNS[basis],
            timezone=declared["timezone"],
            basis=basis,
        )
    return OccurredAtPlan(
        column=declared["column"],
        timezone=declared["timezone"],
    )


def _compile_registration_probe(
    value: Any,
    entities: EntityTypeRegistry,
) -> tuple[RegistrationProbePlan, ...]:
    """The identity key comes from the ENTITY declaration, never from the probe.

    Stating the key in both places would let them disagree, and the probe is the half
    nobody would re-read. ``_cross_registration_probe`` has already refused a composite-key
    entity, so exactly one key is available here.
    """
    if not value:
        return ()
    out = []
    for item in value:
        entity = entities[item["entity_type"]]
        out.append(RegistrationProbePlan(
            entity_type=item["entity_type"],
            identity_key=entity.identity_keys[0],
            columns=tuple(item["columns"]),
            list_separator=item.get("list_separator"),
        ))
    return tuple(sorted(out, key=lambda probe: probe.entity_type))


def _compile_source_plans(
    section: Mapping[str, Any],
    preparers: SourcePreparerRegistry,
    mappers: MapperRegistry,
    profiles: ProfileRegistry,
    verified_joins: VerifiedJoinRegistry,
    entities: EntityTypeRegistry,
) -> SourcePlanRegistry:
    builder = _RegistryBuilder(SourcePlanRegistry)
    for source_id, item in section.items():
        path = f"bundle.sources.{source_id}"
        # The COMPILED plan keeps `driver` as the name for the read clause and its two
        # bodies; only the FILE split.  Nothing downstream of the compiler asks the config
        # a question, so renaming `SourcePlan.driver` would move `backfill`,
        # `source_preparation` and `runtime_v2` for a spelling.
        driver = item["read"]
        preparation = item["prepare"]
        builder.add(source_id, SourcePlan(
            source_id=source_id,
            relation=item["relation"],
            driver=SourceDriverPlan(
                unit=driver["unit"],
                identity=tuple(driver["identity"]),
                group_by=tuple(driver["group_by"]),
                order_by=tuple(driver["order_by"]),
                occurred_at=_occurred_at_plan(driver["occurred_at"]),
                cursor_columns=tuple(driver["cursor"]["columns"]),
                preparation=SourcePreparationPlan(
                    preparer=preparers[source_id],
                    verified_join_descriptors=tuple(
                        verified_joins[rule_id]
                        for rule_id in preparation["inherit_virtual_join_rules"]
                    ),
                ),
                mapper=mappers[source_id],
                registration_probe=_compile_registration_probe(
                    driver.get("registration_probe"), entities),
            ),
            profile=profiles[source_id],
            config_path=path,
        ))
    return builder.seal()
