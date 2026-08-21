"""Ledger v2 Stage 4 EventFrame -> RoleFrame -> LedgerFrame compiler.

This module is deliberately capability-poor.  It accepts an already prepared pandas
EventFrame and an immutable Stage 3 setup snapshot.  It has no database, cursor, gate,
store, source reader, virtual-join, or translator imports.  Both declarative and custom
Python mappers can only return :class:`RoleEmission` values; the Pack compiler is the
single owner of LedgerFrame payload construction.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math
import numbers
from types import MappingProxyType
from typing import Any, final
import uuid

import pandas as pd

from .envelope import source_event_identity
from .ledger_frame import (
    LEDGER_FRAME_COLUMNS,
    LEDGER_FRAME_ATTR,
    LEDGER_FRAME_SCHEMA_VERSION,
    validate_ledger_frame,
)
from .setup_registry import (
    ClaimDescriptor,
    ImplementationKey,
    LedgerSetupSnapshot,
    MapperDescriptor,
    ProfileDescriptor,
    RoleDescriptor,
    SourcePlan,
)


ROLE_FRAME_SCHEMA_VERSION = 1
ROLE_FRAME_ATTR = "assy_manager.role_frame_schema_version"
ROLE_FRAME_COLUMNS = (
    "source_event_id",
    "sentence",
    "predicate",
    "roles",
    "source_row_refs",
)
EVENT_FRAME_REQUIRED_ATTRS = (
    "source_id",
    "source_event_id",
    "molecule_ref",
    "source_raw_ref",
    "setup_snapshot_hash",
)
SOURCE_EVENT_INCOMPLETE_ATTR = "assy_manager.source_event_incomplete"
EVENT_FRAME_PASSTHROUGH_ATTRS = (SOURCE_EVENT_INCOMPLETE_ATTR,)
SOURCE_ROW_REF_COLUMN = "__source_row_ref"
#: Engine-owned column carrying the one instant the preparer validated for this event.
#: A mapper reads the time under THIS name whichever way the source declared its origin
#: (``occurred_at.column`` or ``occurred_at.basis``); resolving a declaration to a physical
#: column is the plan's job, and a mapper that had to ask for that name was carrying a
#: deployment detail it has no business knowing.  Like ``__source_row_ref`` this is stamped
#: by the preparation boundary, never by a source, and therefore is never declared.
SOURCE_OCCURRED_AT_COLUMN = "__occurred_at"
UNIT_SOURCE_ROW_REFS_ATTR = "assy_manager.unit_source_row_refs"


class RoleFrameError(ValueError):
    """Stable, path-addressed Stage 4 refusal."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({
            str(key): _freeze(value[key]) for key in sorted(value, key=str)
        })
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TypeError("naive datetime has no deterministic instant")
        return {"$datetime": value.isoformat()}
    if isinstance(value, uuid.UUID):
        return {"$uuid": str(value)}
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    return value


def _canonical(value: Any, *, path: str) -> str:
    try:
        return json.dumps(
            _plain(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RoleFrameError(
            "invalid_role_value", path,
            f"value is not deterministic JSON: {exc}",
        ) from exc


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(missing, bool):
        return missing
    if getattr(missing, "shape", None) == ():
        return bool(missing)
    return False


@dataclass(frozen=True)
class RoleEmission:
    """The only value a custom mapper interpretation hook may emit.

    🔴 NO `claim_ref`, AND THE ABSENCE IS THE POINT (owner, 2026-08-20: 「클레임과 맵퍼
    함수는 완전 별개인데 왜 맵퍼에서 쓸 클레임을 정의함? 프로필에서 해야하는거 아니야?」 ->
    「닿을 수 없다면 선언도 닿으면 안됨」).  A mapper names a sentence; which PREDICATE that
    sentence utters is `bind.mappings.<sentence>.predicate`, one declaration away, and a
    mapper that restated it could only restate it wrongly.  `_role_frame_from_emissions`
    looks it up from `sentence` against the same Profile the mapper was handed.  (The
    declaration spelled a `<pack>/<claim>` ref until the `packs` section went on
    2026-08-21; the direction it runs in never changed.)

    🔴 `sentence`, NOT `mapping_id`, as of 2026-08-21 (owner: 「맵퍼 구조를 문장에 별명을
    붙여 부르게 만들고 그 별명에 바인드를 한다면?」).  A mapping is now KEYED by the
    sentence it realizes, so the two were the same string wearing two names; the one that
    survives is the one the mapper actually declares.
    """

    sentence: str
    roles: Mapping[str, Any]
    source_row_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("sentence",):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise RoleFrameError(
                    "invalid_role_emission", f"role_emission.{name}",
                    "must be a trimmed non-blank string",
                )
        if not isinstance(self.roles, Mapping):
            raise RoleFrameError(
                "invalid_role_emission", "role_emission.roles", "must be a mapping")
        refs = tuple(self.source_row_refs)
        if (not refs or any(not isinstance(item, str) or not item.strip()
                            or item != item.strip() for item in refs)):
            raise RoleFrameError(
                "invalid_role_emission", "role_emission.source_row_refs",
                "must contain trimmed non-blank source row references",
            )
        object.__setattr__(self, "roles", _freeze(self.roles))
        object.__setattr__(self, "source_row_refs", tuple(sorted(set(refs))))


@dataclass(frozen=True)
class MapperContext:
    """Read-only Stage 4 mapper context; no runtime or persistence capability."""

    snapshot: LedgerSetupSnapshot
    source_plan: SourcePlan

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, LedgerSetupSnapshot):
            raise TypeError("snapshot must be LedgerSetupSnapshot")
        if not isinstance(self.source_plan, SourcePlan):
            raise TypeError("source_plan must be SourcePlan")
        registered = self.snapshot.source_plans.get(self.source_plan.source_id)
        if registered is not self.source_plan:
            raise RoleFrameError(
                "invalid_source_plan", "context.source_plan",
                "source plan must be the descriptor owned by the setup snapshot",
            )


def mapper_context(snapshot: LedgerSetupSnapshot, source_id: str) -> MapperContext:
    if not isinstance(snapshot, LedgerSetupSnapshot) or snapshot.readiness != "ready":
        raise RoleFrameError(
            "setup_not_ready", "snapshot", "a ready LedgerSetupSnapshot is required")
    plan = snapshot.source_plans.get(source_id)
    if plan is None:
        raise RoleFrameError(
            "unknown_source", "source_id", f"source {source_id!r} is not registered")
    return MapperContext(snapshot=snapshot, source_plan=plan)


class BaseLedgerMapper:
    """Template Method for all Stage 4 RoleFrame-producing mappers.

    A concrete mapper declares its OWN trusted identity through ``implementation_id`` and
    ``implementation_version``.  ``ledger.implementations`` discovers those declarations
    and builds both the trusted catalog and the executable registry from them, so adding a
    mapper is one file and edits no list.  A subclass that leaves them ``None`` (a test
    double, an abstract intermediate) is simply not addressable from config, which keeps
    the boundary the whitelist existed for: config names an ID, never a module or path.
    """

    #: Self-declared trusted identity; ``None`` means "not addressable from config".
    implementation_id: str | None = None
    implementation_version: int | None = None

    @final
    def map(
        self,
        context: MapperContext,
        event_frame: pd.DataFrame,
        descriptor: MapperDescriptor,
        profile: ProfileDescriptor,
    ) -> pd.DataFrame:
        _validate_event_frame(context, event_frame, descriptor, profile)
        emissions: list[RoleEmission] = []
        for unit_index, unit in enumerate(
                _partition_units(context, event_frame, descriptor)):
            try:
                produced = self.interpret_unit(context, unit, profile)
            except RoleFrameError:
                raise
            except Exception as exc:
                raise RoleFrameError(
                    "mapper_failed", f"mapper.units[{unit_index}]",
                    f"interpret_unit raised {exc.__class__.__name__}: {exc}",
                ) from exc
            if (isinstance(produced, (pd.DataFrame, Mapping, str, bytes, bytearray))
                    or not isinstance(produced, Sequence)):
                raise RoleFrameError(
                    "unsupported_mapper_output", f"mapper.units[{unit_index}]",
                    "interpret_unit must return a sequence of RoleEmission values",
                )
            for emission_index, emission in enumerate(produced):
                if not isinstance(emission, RoleEmission):
                    raise RoleFrameError(
                        "unsupported_mapper_output",
                        f"mapper.units[{unit_index}].emissions[{emission_index}]",
                        "raw Atom, LedgerFrame, mappings, and arbitrary values are forbidden",
                    )
                emissions.append(emission)
        frame = _role_frame_from_emissions(event_frame.attrs, emissions, profile)
        return validate_role_frame(context, frame, descriptor, profile)

    def interpret_unit(
        self,
        context: MapperContext,
        unit: pd.DataFrame,
        profile: ProfileDescriptor,
    ) -> Sequence[RoleEmission]:
        raise NotImplementedError


class DeclarativeRoleMapper(BaseLedgerMapper):
    """Evaluate approved column/constant/entity Profile bindings without DB access.

    This is the GENERIC mapper: it executes the Profile's declared bindings and holds no
    knowledge of any particular source.  A source whose business reading is fully
    expressible as bindings needs no mapper code at all -- it names this implementation.
    """

    implementation_id = "declarative-role"
    implementation_version = 1

    def interpret_unit(
        self,
        context: MapperContext,
        unit: pd.DataFrame,
        profile: ProfileDescriptor,
    ) -> Sequence[RoleEmission]:
        refs = _source_row_refs(unit)
        out = []
        for sentence, mapping in profile.mappings.items():
            roles = {
                role_id: _evaluate_binding(binding, unit, path=(
                    f"{mapping.config_path}.bind.{role_id}"))
                for role_id, binding in mapping.bindings.items()
            }
            out.append(RoleEmission(
                sentence=sentence,
                roles=roles,
                source_row_refs=refs,
            ))
        return out


@dataclass(frozen=True)
class SentenceShape:
    """One sentence a mapper can say, carrying the mapper's own NAME for it.

    A business reading knows things like "a wafer sits in a slot of a lot".  That sentence
    carries one qualifier the business calls ``slot``.  It does NOT know that this
    deployment's declaration spells the predicate ``has_wafer@1``, calls the two entity
    types ``Lot@1``/``Wafer@1``, or files the values under role ids ``subject``/``target``.
    Those are one operator's words for the sentence and they are exactly what changes in a
    different-schema environment; the sentence does not change.

    🔴 NO `has_object` AS OF 2026-08-21, AND THE REASON IS THAT MATCHING BY STRUCTURE IS
    GONE (owner: 「맵퍼 구조를 문장에 별명을 붙여 부르게 만들고 그 별명에 바인드를 한다면?」).
    Measured before removing it: the flag was read at exactly two places, the structural
    match in ``ProfileSentences._resolve`` and the refusal text that reported it.  Both go
    with the match, so keeping the field would keep a declaration nothing can reach.
    ``qualifiers`` is NOT symmetric with it and stays: :meth:`ProfileSentences.say` checks
    the keys a mapper actually passed against it, which has nothing to do with selection.
    """

    qualifiers: tuple[str, ...] = ()
    #: The mapper's own word for this sentence, taken from the class attribute the shape
    #: was bound to (lowercased).  Never a constructor argument: a shape is named by being
    #: bound, or it has no name at all.  ``compare=False`` keeps it out of equality and
    #: hashing, because ``__set_name__`` fills it in AFTER construction and a hash that
    #: changed under the object would be a trap for any later dict use.
    sentence: str | None = field(default=None, init=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "qualifiers", tuple(sorted(self.qualifiers)))

    def __set_name__(self, owner: type, name: str) -> None:
        """A shape bound to a class attribute already HAS a name: the attribute's.

        Two shape-identical sentences used to be told apart by a string the mapper
        declared twice -- once as a constant, once at the call site -- next to the same
        word a third time in the Profile.  Two of those three are the mapper's own
        vocabulary, and Python already records the one that matters, so this takes it
        rather than asking for it again.

        🔴 THIS NAME IS NOW THE WHOLE OF SELECTION.  It is the key under which the Profile
        files the mapping that realizes the sentence, so an unbound shape -- one built
        inline rather than assigned to a class attribute -- can say nothing at all, and
        :meth:`ProfileSentences._resolve` refuses it by name instead of matching a
        structure it happens to share with something else.

        🔴 One instance bound to two attribute names is refused HERE, at class creation,
        because its name could only be one of the two and the other call site would then
        say a sentence it did not mean -- silently, and correctly for as long as the two
        happen to resolve the same way.  Sharing one shape between two sentences is what
        the mapper did before this change; the fix is a shape per sentence, not a name
        per call.
        """
        auto = name.lower()
        if self.sentence is not None and self.sentence != auto:
            raise RoleFrameError(
                "ambiguous_sentence_shape", f"{owner.__qualname__}.{name}",
                f"one SentenceShape is bound to both {self.sentence!r} and {auto!r}; "
                f"a shape carries the name of the sentence it says, so two sentences "
                f"need two shapes",
            )
        object.__setattr__(self, "sentence", auto)


class ProfileSentences:
    """Turn one mapper unit's sentences into RoleEmissions using only the declaration.

    This is the wiring that used to be copied into every custom mapper: find the Profile
    mapping, read the Claim's role ids, assemble the Entity references, and remember which
    identities have already been announced in this unit.  A mapper that owns this code
    inevitably names the declaration to steer it -- which is how predicate spellings and
    entity-type spellings ended up as Python literals in a file whose only job was domain
    interpretation.

    Selection here is by the mapper's OWN NAME for the sentence -- one key lookup.  Two
    things follow:

    * a deployment may rename any predicate or entity type and the mapper is untouched,
      which is the owner's definition of done ("a different-schema production environment
      needs zero lines of code").  The naming still runs config -> mapper: the key is the
      mapper's word, and an operator who wants a different one edits the mapper, not the
      config;
    * entity-type spellings are LEARNED rather than asserted -- ask
      :meth:`subject_type_of` / :meth:`object_type_of` what this Profile calls the thing
      that holds items in slots, instead of writing ``"Lot"`` and hoping.

    Versions are compared WHOLE.  The retired mapper compared ``_base()`` spellings, so
    ``Wafer@1`` and ``Wafer@2`` matched each other; two Entity versions with different
    identity keys would have been silently interchangeable.
    """

    def __init__(
        self,
        context: MapperContext,
        profile: ProfileDescriptor,
        *,
        occurred_at: Any,
    ) -> None:
        self._context = context
        self._profile = profile
        self._occurred_at = occurred_at
        self._announced: set[tuple[str, str]] = set()

    def subject_type_of(self, shape: SentenceShape) -> str:
        """What THIS Profile calls the subject of that sentence."""
        mapping, claim = self._resolve(shape)
        return self._entity_binding(mapping, claim.emission.subject.role_id)["entity_type"]

    def object_type_of(self, shape: SentenceShape) -> str:
        """What THIS Profile calls the object of that sentence."""
        mapping, claim = self._resolve(shape)
        if claim.emission.object_role is None:
            raise RoleFrameError(
                "invalid_sentence_contract", mapping.config_path,
                "sentence has no object Entity")
        return self._entity_binding(
            mapping, claim.emission.object_role.role_id)["entity_type"]

    def say(
        self,
        shape: SentenceShape,
        subject: Any,
        refs: Sequence[str],
        *,
        obj: Any = None,
        qualifiers: Mapping[str, Any] | None = None,
    ) -> RoleEmission:
        mapping, claim = self._resolve(shape)
        emission = claim.emission
        values = dict(qualifiers or {})
        if set(values) != set(shape.qualifiers):
            raise RoleFrameError(
                "invalid_sentence_contract", mapping.config_path,
                "qualifier values disagree with the declared sentence shape")
        roles: dict[str, Any] = {
            emission.subject.role_id: self._entity_value(
                mapping, emission.subject.role_id, subject),
            emission.occurred_at.role_id: self._occurred_at,
        }
        if emission.object_role is not None:
            roles[emission.object_role.role_id] = self._object_value(
                mapping, emission, obj)
        for name, reference in emission.qualifiers.items():
            roles[reference.role_id] = values[name]
        return RoleEmission(
            sentence=shape.sentence,
            roles=roles,
            source_row_refs=tuple(refs),
        )

    def first_sight(
        self,
        shape: SentenceShape,
        subject: Any,
        refs: Sequence[str],
    ) -> RoleEmission | None:
        """Announce an identity the first time this unit mentions it, else ``None``.

        The de-duplication is the engine's because it is not domain knowledge: every
        source that announces identities wants exactly this, and a mapper that reimplements
        it has to name the mapping to find it.
        """
        self._resolve(shape)
        token = (
            shape.sentence,
            json.dumps(_plain(subject), ensure_ascii=False, sort_keys=True),
        )
        if token in self._announced:
            return None
        self._announced.add(token)
        return self.say(shape, subject, refs)

    def _resolve(self, shape: SentenceShape) -> tuple[Any, ClaimDescriptor]:
        """Look the sentence up by the name the mapper gave it.  One key, one mapping.

        🔴 THIS WAS A STRUCTURE MATCH UNTIL 2026-08-21 (owner: 「지금 자연스럽지 못한 자리가
        맵퍼가 낸 정규 문장 - 클레임으로 바인드 여기네」 -> 「맵퍼 구조를 문장에 별명을 붙여
        부르게 만들고 그 별명에 바인드를 한다면?」).  It compared object-ness, qualifier
        names, and two entity-type spellings, and consulted the name LAST, as a tiebreak --
        while a stable name existed on both sides the whole time.  Selection is now the
        name and nothing else.

        The naming direction is unchanged, which is why this is safe: the key is the
        SHAPE's name, taken from the class attribute it was bound to
        (:meth:`SentenceShape.__set_name__`), so it runs config -> mapper exactly as the
        tiebreak did.  What is gone is the possibility of two mappings answering to one
        sentence: ``bind.mappings`` is a map keyed by sentence, so a duplicate cannot be
        written down at all, and ``setup_bundle._ambiguous_sentences`` retired with the
        state it refused rather than with the rule it enforced.
        """
        if shape.sentence is None:
            raise RoleFrameError(
                "unnamed_sentence", self._profile.config_path,
                "a SentenceShape says nothing until it is bound to a class attribute, "
                "which is where its name comes from",
            )
        mapping = self._profile.mappings.get(shape.sentence)
        claim = None if mapping is None else self._claim_of(mapping)
        if claim is None:
            raise RoleFrameError(
                "unresolved_sentence", self._profile.config_path,
                f"no Profile mapping realizes sentence {shape.sentence!r}; "
                f"declared here: {sorted(self._profile.mappings)}",
            )
        return mapping, claim

    def _claim_of(self, mapping: Any) -> ClaimDescriptor | None:
        """The Claim the mapping's predicate forces -- one lookup, no pack to open first.

        It was `snapshot.packs[pack].claims[claim]` until 2026-08-21, splitting a
        `<pack>/<claim>` ref that `bind.mappings.<sentence>` no longer writes.  Nothing
        pack-shaped was consumed on the way through, so this is a substitution.
        """
        predicate_id = getattr(mapping, "predicate_id", None)
        return self._context.snapshot.claims.get(predicate_id)

    def _entity_binding(self, mapping: Any, role_id: str) -> Mapping[str, Any]:
        binding = mapping.bindings.get(role_id)
        if not isinstance(binding, Mapping) or binding.get("kind") != "entity":
            raise RoleFrameError(
                "invalid_sentence_contract", f"{mapping.config_path}.bind.{role_id}",
                "Entity Role requires an entity binding")
        return binding

    def _object_value(self, mapping: Any, emission: Any, value: Any) -> Any:
        """Shape the object a mapper handed over the way the Claim DECLARES it.

        Every object kind the Vocabulary allows (``setup_bundle._OBJECT_KINDS``) is
        answered here, deliberately and by name:

        * ``entity_ref`` -- the mapper supplies one identity key and the Profile binding
          supplies the Entity type and the key's name;
        * ``value`` and ``event_ref`` -- the object IS the value.  What constrains it is
          the object Role's own kind (``quantity``, ``identity``, ``symbolic``, ...),
          which :func:`validate_role_frame` already checks against the Claim, and the
          Pack compiler is still the only thing that wraps it into a payload.  Assembling
          an Entity reference here was the reason a Claim declaring
          ``"object": {"kind": "value", ...}`` could not be said by a mapper at all;
        * ``none`` -- a Claim with no object has no object Role, so this method is never
          reached for it.  An emission that declares ``none`` and binds an object Role
          anyway contradicts itself and falls to the refusal below.

        The refusal is the point: a kind added to the Vocabulary and not answered here
        must fail by name rather than silently take the entity path and mint a wrong atom.
        """
        role_id = emission.object_role.role_id
        kind = emission.object_kind
        if kind == "entity_ref":
            return self._entity_value(mapping, role_id, value)
        if kind in {"value", "event_ref"}:
            return value
        raise RoleFrameError(
            "unsupported_object_kind", f"{emission.config_path}.object.kind",
            f"a sentence cannot say an object of kind {kind!r}")

    def _entity_value(self, mapping: Any, role_id: str, value: Any) -> Mapping[str, Any]:
        binding = self._entity_binding(mapping, role_id)
        keys = binding.get("keys")
        if not isinstance(keys, Mapping) or len(keys) != 1:
            raise RoleFrameError(
                "invalid_sentence_contract",
                f"{mapping.config_path}.bind.{role_id}.keys",
                "a mapper-supplied Entity reference carries one identity key")
        return {"type": binding.get("entity_type"), "keys": {next(iter(keys)): value}}


class RoleMapperImplementationRegistry:
    """Closed executable mapper classes keyed only by trusted implementation ID/version."""

    def __init__(self) -> None:
        self._items: dict[ImplementationKey, type[BaseLedgerMapper]] = {}
        self._sealed = False

    def register(
        self,
        implementation_id: str,
        implementation_version: int,
        mapper_type: type[BaseLedgerMapper],
    ) -> None:
        if self._sealed:
            raise RuntimeError("role mapper implementation registry is sealed")
        key = ImplementationKey(implementation_id, implementation_version)
        if not isinstance(mapper_type, type) or not issubclass(mapper_type, BaseLedgerMapper):
            raise TypeError("mapper_type must inherit BaseLedgerMapper")
        for ancestor in mapper_type.__mro__:
            if ancestor is BaseLedgerMapper:
                break
            if "map" in ancestor.__dict__:
                raise RoleFrameError(
                    "unsupported_mapper_override", "mapper_type.map",
                    "BaseLedgerMapper.map() is final and cannot be overridden",
                )
        if key in self._items:
            raise ValueError(f"mapper implementation {implementation_id!r}@"
                             f"{implementation_version} is already registered")
        self._items[key] = mapper_type

    def seal(self) -> "RoleMapperImplementationRegistry":
        self._sealed = True
        return self

    def resolve(self, key: ImplementationKey) -> BaseLedgerMapper:
        if not self._sealed:
            raise RoleFrameError(
                "mapper_registry_not_sealed", "mapper_registry",
                "mapper implementation registry must be sealed before execution",
            )
        mapper_type = self._items.get(key)
        if mapper_type is None:
            raise RoleFrameError(
                "unsupported_mapper_implementation", "mapper.implementation",
                f"no executable Role mapper is registered for "
                f"{key.implementation_id!r}@{key.implementation_version}",
            )
        try:
            return mapper_type()
        except TypeError as exc:
            raise RoleFrameError(
                "unsupported_mapper_implementation", "mapper.implementation",
                "registered Role mapper must have a no-argument constructor",
            ) from exc


def map_event_frame(
    context: MapperContext,
    event_frame: pd.DataFrame,
    implementations: RoleMapperImplementationRegistry,
) -> pd.DataFrame:
    if not isinstance(implementations, RoleMapperImplementationRegistry):
        raise TypeError("implementations must be RoleMapperImplementationRegistry")
    descriptor = context.source_plan.driver.mapper
    mapper = implementations.resolve(descriptor.implementation)
    return mapper.map(context, event_frame, descriptor, context.source_plan.profile)


def _validate_event_frame(
    context: MapperContext,
    value: Any,
    descriptor: MapperDescriptor,
    profile: ProfileDescriptor,
) -> None:
    path = "event_frame"
    if not isinstance(value, pd.DataFrame):
        raise RoleFrameError(
            "invalid_event_frame", path, "expected pandas.DataFrame")
    if value.empty:
        raise RoleFrameError(
            "invalid_event_frame", path, "one source event must contain at least one row")
    if value.columns.has_duplicates:
        raise RoleFrameError(
            "invalid_event_frame", f"{path}.columns", "duplicate columns are forbidden")
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        if name not in value.attrs:
            raise RoleFrameError(
                "missing_event_context", f"{path}.attrs.{name}", "attribute is required")
    source_id = value.attrs["source_id"]
    if source_id != context.source_plan.source_id or source_id != profile.source_id:
        raise RoleFrameError(
            "invalid_event_context", f"{path}.attrs.source_id",
            "source_id disagrees with SourcePlan/Profile")
    event_id = value.attrs["source_event_id"]
    if not isinstance(event_id, uuid.UUID):
        raise RoleFrameError(
            "invalid_event_context", f"{path}.attrs.source_event_id",
            "source_event_id must be uuid.UUID")
    for name in ("molecule_ref", "source_raw_ref"):
        item = value.attrs[name]
        if not isinstance(item, str) or not item.strip():
            raise RoleFrameError(
                "invalid_event_context", f"{path}.attrs.{name}",
                "must be a non-blank string")
    if value.attrs["setup_snapshot_hash"] != context.snapshot.snapshot_sha256:
        raise RoleFrameError(
            "snapshot_mismatch", f"{path}.attrs.setup_snapshot_hash",
            "EventFrame was not prepared for this setup snapshot")
    missing = [column for column in descriptor.input_columns
               if column not in value.columns]
    if missing:
        raise RoleFrameError(
            "missing_mapper_input", f"{path}.columns",
            f"mapper input columns are missing: {missing}")


def _partition_units(
    context: MapperContext,
    frame: pd.DataFrame,
    descriptor: MapperDescriptor,
) -> tuple[pd.DataFrame, ...]:
    kind = descriptor.unit_kind
    if kind == "event":
        unit = frame.copy(deep=False)
        unit.attrs[UNIT_SOURCE_ROW_REFS_ATTR] = _frame_row_refs(frame)
        return (unit,)
    if kind == "row":
        ordered = sorted(
            range(len(frame)),
            key=lambda position: _row_sort_token(frame.iloc[position], frame.columns),
        )
        units = []
        refs = _frame_row_refs(frame)
        for position in ordered:
            unit = frame.iloc[[position]].copy(deep=False)
            unit.attrs[UNIT_SOURCE_ROW_REFS_ATTR] = (refs[position],)
            units.append(unit)
        return tuple(units)
    if kind == "group_by":
        columns = tuple(descriptor.unit_columns)
        if not columns or any(column not in frame.columns for column in columns):
            raise RoleFrameError(
                "invalid_mapper_unit", "mapper.unit.group_by",
                "MapperDescriptor group_by columns must exist in EventFrame")
        groups: dict[str, list[int]] = {}
        for position in range(len(frame)):
            token = _canonical(
                {column: frame.iloc[position][column] for column in columns},
                path=f"event_frame.rows[{position}]",
            )
            groups.setdefault(token, []).append(position)
        refs = _frame_row_refs(frame)
        units = []
        for token in sorted(groups):
            positions = groups[token]
            unit = frame.iloc[positions].copy(deep=False)
            unit.attrs[UNIT_SOURCE_ROW_REFS_ATTR] = tuple(
                sorted(refs[position] for position in positions))
            units.append(unit)
        return tuple(units)
    raise RoleFrameError(
        "unsupported_mapper_unit", "mapper.unit.kind",
        f"unsupported mapper unit {kind!r}")


def _row_sort_token(row: pd.Series, columns: Sequence[Any]) -> str:
    return _canonical(
        {str(column): row[column] for column in sorted(columns, key=str)},
        path="event_frame.row",
    )


def _source_row_refs(unit: pd.DataFrame) -> tuple[str, ...]:
    declared = unit.attrs.get(UNIT_SOURCE_ROW_REFS_ATTR)
    if isinstance(declared, tuple) and declared:
        return declared
    return _frame_row_refs(unit)


def _frame_row_refs(frame: pd.DataFrame) -> tuple[str, ...]:
    if SOURCE_ROW_REF_COLUMN in frame.columns:
        refs = tuple(str(value).strip() for value in frame[SOURCE_ROW_REF_COLUMN].tolist())
        if any(not value for value in refs):
            raise RoleFrameError(
                "invalid_source_row_ref", f"event_frame.{SOURCE_ROW_REF_COLUMN}",
                "source row references must be non-blank")
        if len(set(refs)) != len(refs):
            raise RoleFrameError(
                "ambiguous_source_row_ref", f"event_frame.{SOURCE_ROW_REF_COLUMN}",
                "source row references must be unique within one source event")
        return refs
    base = str(frame.attrs.get("source_raw_ref") or "").strip()
    if len(frame) == 1:
        return (base,)
    refs = []
    for position in range(len(frame)):
        token = _row_sort_token(frame.iloc[position], frame.columns)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        refs.append(f"{base}#row:{digest}")
    if len(set(refs)) != len(refs):
        raise RoleFrameError(
            "ambiguous_source_row_ref", "event_frame.rows",
            "indistinguishable rows require explicit __source_row_ref values")
    return tuple(refs)


def _evaluate_binding(binding: Mapping[str, Any], unit: pd.DataFrame, *, path: str) -> Any:
    if binding.get("approval_status") != "approved":
        raise RoleFrameError(
            "binding_not_approved", f"{path}.approval_status",
            "only approved bindings are executable")
    kind = binding.get("kind")
    if kind == "column":
        column = binding.get("column")
        if column not in unit.columns:
            raise RoleFrameError(
                "missing_binding_column", f"{path}.column",
                f"column {column!r} is absent from the EventFrame unit")
        values = [unit.iloc[index][column] for index in range(len(unit))]
        if any(_is_missing(value) for value in values):
            raise RoleFrameError(
                "missing_binding_value", f"{path}.column",
                f"column {column!r} contains a missing value")
        distinct = {_canonical(value, path=f"{path}.column") for value in values}
        if len(distinct) != 1:
            raise RoleFrameError(
                "ambiguous_binding_value", f"{path}.column",
                f"column {column!r} has multiple values in one mapper unit")
        return values[0]
    if kind == "constant":
        return _plain(binding.get("value"))
    if kind == "entity":
        keys = {
            key: _evaluate_binding(child, unit, path=f"{path}.keys.{key}")
            for key, child in binding.get("keys", {}).items()
        }
        return {"type": binding.get("entity_type"), "keys": keys}
    raise RoleFrameError(
        "unsupported_binding", f"{path}.kind",
        f"binding kind {kind!r} is not supported by Stage 4")


def _role_frame_from_emissions(
    event_attrs: Mapping[str, Any],
    emissions: Sequence[RoleEmission],
    profile: ProfileDescriptor,
) -> pd.DataFrame:
    """Fill the RoleFrame, resolving each emission's claim from the Profile that owns it.

    A `sentence` the Profile does not realize resolves to the empty string rather than
    raising here.  `validate_role_frame` refuses that same row as `unknown_mapping` one
    step later, which is the refusal an author can act on -- it names the sentence.
    """
    rows = [{
        "source_event_id": event_attrs["source_event_id"],
        "sentence": emission.sentence,
        "predicate": (profile.mappings[emission.sentence].predicate_id
                      if emission.sentence in profile.mappings else ""),
        "roles": emission.roles,
        "source_row_refs": emission.source_row_refs,
    } for emission in emissions]
    frame = pd.DataFrame({
        column: pd.Series([row[column] for row in rows], dtype=object)
        for column in ROLE_FRAME_COLUMNS
    })
    frame.attrs[ROLE_FRAME_ATTR] = ROLE_FRAME_SCHEMA_VERSION
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        frame.attrs[name] = event_attrs[name]
    for name in EVENT_FRAME_PASSTHROUGH_ATTRS:
        if name in event_attrs:
            frame.attrs[name] = event_attrs[name]
    return frame


def validate_role_frame(
    context: MapperContext,
    value: Any,
    descriptor: MapperDescriptor | None = None,
    profile: ProfileDescriptor | None = None,
) -> pd.DataFrame:
    descriptor = descriptor or context.source_plan.driver.mapper
    profile = profile or context.source_plan.profile
    path = "role_frame"
    if not isinstance(value, pd.DataFrame):
        raise RoleFrameError(
            "invalid_role_frame", path, "expected pandas.DataFrame")
    if value.attrs.get(ROLE_FRAME_ATTR) != ROLE_FRAME_SCHEMA_VERSION:
        raise RoleFrameError(
            "unmarked_role_frame", f"{path}.attrs.{ROLE_FRAME_ATTR}",
            "arbitrary DataFrames are not RoleFrames")
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        if name not in value.attrs:
            raise RoleFrameError(
                "missing_event_context", f"{path}.attrs.{name}",
                "RoleFrame must preserve EventFrame provenance")
    if value.attrs["source_id"] != context.source_plan.source_id:
        raise RoleFrameError(
            "invalid_event_context", f"{path}.attrs.source_id",
            "RoleFrame source_id disagrees with SourcePlan")
    if value.attrs["setup_snapshot_hash"] != context.snapshot.snapshot_sha256:
        raise RoleFrameError(
            "snapshot_mismatch", f"{path}.attrs.setup_snapshot_hash",
            "RoleFrame was not built for this setup snapshot")
    if tuple(value.columns) != ROLE_FRAME_COLUMNS:
        raise RoleFrameError(
            "invalid_role_frame_schema", f"{path}.columns",
            f"columns must exactly match RoleFrame v{ROLE_FRAME_SCHEMA_VERSION}")
    sort_rows: list[tuple[str, dict[str, Any]]] = []
    for position in range(len(value)):
        row = value.iloc[position]
        row_path = f"{path}.rows[{position}]"
        if row["source_event_id"] != value.iloc[0]["source_event_id"]:
            raise RoleFrameError(
                "cross_event_mapper_output", f"{row_path}.source_event_id",
                "one RoleFrame may not cross source-event boundaries")
        if row["source_event_id"] != value.attrs["source_event_id"]:
            raise RoleFrameError(
                "cross_event_mapper_output", f"{row_path}.source_event_id",
                "RoleFrame row source_event_id disagrees with preserved EventFrame context")
        mapping = profile.mappings.get(row["sentence"])
        if mapping is None:
            raise RoleFrameError(
                "unknown_mapping", f"{row_path}.sentence",
                f"Profile realizes no sentence {row['sentence']!r}")
        # 🔴 BOTH OF THESE ARE NOW TAUTOLOGIES, AND THAT IS WHY THEY STAY.  They were not
        # removed; the state they refused stopped being expressible.  `predicate` is looked
        # up from `sentence` against this same Profile, so the first compares a value with
        # its own source; `descriptor.emits` is compiled from those same declarations, so
        # the second does too.  A mapper that invents a `sentence` is already refused three
        # lines up as `unknown_mapping`.  Deleting a check that can no longer fail would
        # also delete the record of what used to be writable -- and `validate_role_frame`
        # is a boundary that accepts frames it did not build.
        if row["predicate"] != mapping.predicate_id:
            raise RoleFrameError(
                "invalid_predicate_ref", f"{row_path}.predicate",
                "predicate disagrees with the Profile mapping")
        if row["predicate"] not in descriptor.emits:
            raise RoleFrameError(
                "unsupported_predicate", f"{row_path}.predicate",
                "predicate is outside MapperDescriptor.emits")
        claim = _claim(context.snapshot, row["predicate"], f"{row_path}.predicate")
        roles = row["roles"]
        if not isinstance(roles, Mapping):
            raise RoleFrameError(
                "invalid_roles", f"{row_path}.roles", "must be a mapping")
        unknown = sorted(set(roles) - set(claim.roles))
        if unknown:
            raise RoleFrameError(
                "unknown_role", f"{row_path}.roles.{unknown[0]}",
                f"Claim does not declare Role {unknown[0]!r}")
        for role_id, role in claim.roles.items():
            if role.required and role_id not in roles:
                raise RoleFrameError(
                    "missing_required_role", f"{row_path}.roles.{role_id}",
                    f"Claim requires Role {role_id!r}")
            if role_id in roles:
                _validate_role_value(
                    context.snapshot, role, roles[role_id],
                    path=f"{row_path}.roles.{role_id}")
                binding = mapping.bindings.get(role_id)
                if (isinstance(binding, Mapping) and binding.get("kind") == "entity"
                        and isinstance(roles[role_id], Mapping)
                        and roles[role_id].get("type") != binding.get("entity_type")):
                    raise RoleFrameError(
                        "invalid_entity_ref", f"{row_path}.roles.{role_id}.type",
                        "entity Role type disagrees with the Profile binding")
        refs = row["source_row_refs"]
        if (not isinstance(refs, (tuple, list)) or not refs
                or any(not isinstance(item, str) or not item.strip() for item in refs)):
            raise RoleFrameError(
                "invalid_source_row_ref", f"{row_path}.source_row_refs",
                "must be a non-empty sequence of source row references")
        normalized_row = {
            "source_event_id": row["source_event_id"],
            "sentence": row["sentence"],
            "predicate": row["predicate"],
            "roles": roles,
            "source_row_refs": tuple(sorted(set(refs))),
        }
        canonical_row = dict(normalized_row)
        canonical_row["source_event_id"] = str(row["source_event_id"])
        sort_rows.append((_canonical(canonical_row, path=row_path), normalized_row))
    sorted_rows = [item[1] for item in sorted(sort_rows, key=lambda item: item[0])]
    out = pd.DataFrame({
        column: pd.Series([row[column] for row in sorted_rows], dtype=object)
        for column in ROLE_FRAME_COLUMNS
    })
    out.attrs[ROLE_FRAME_ATTR] = ROLE_FRAME_SCHEMA_VERSION
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        out.attrs[name] = value.attrs[name]
    for name in EVENT_FRAME_PASSTHROUGH_ATTRS:
        if name in value.attrs:
            out.attrs[name] = value.attrs[name]
    return out


def _claim(snapshot: LedgerSetupSnapshot, predicate_id: Any, path: str) -> ClaimDescriptor:
    claim = None if not isinstance(predicate_id, str) else snapshot.claims.get(predicate_id)
    if claim is None:
        raise RoleFrameError(
            "unknown_predicate", path, f"unknown predicate {predicate_id!r}")
    return claim


def _runtime_id(versioned_id: str) -> str:
    """Config/Registry addresses are versioned; the existing Ledger API is not.

    The version remains in the immutable snapshot hash and translator version.  The
    physical predicate/entity spellings stay compatible with the existing LedgerStore
    and read APIs (`register`, `Lot`, ...), rather than leaking Registry addresses such
    as `register@1` into the evidence graph.
    """
    return versioned_id.rsplit("@", 1)[0]


def _validate_role_value(
    snapshot: LedgerSetupSnapshot,
    role: RoleDescriptor,
    value: Any,
    *,
    path: str,
) -> None:
    kind = role.kind
    if _is_missing(value):
        raise RoleFrameError(
            "missing_role_value", path, "present Role values cannot be null/missing")
    if kind == "entity":
        if not isinstance(value, Mapping) or set(value) != {"type", "keys"}:
            raise RoleFrameError(
                "invalid_entity_ref", path,
                "entity Role must be exactly {'type', 'keys'}")
        entity_type = value.get("type")
        entity = snapshot.entities.get(entity_type)
        if entity is None:
            raise RoleFrameError(
                "unknown_entity_type", f"{path}.type",
                f"unknown entity type {entity_type!r}")
        keys = value.get("keys")
        if not isinstance(keys, Mapping) or set(keys) != set(entity.identity_keys):
            raise RoleFrameError(
                "invalid_entity_ref", f"{path}.keys",
                "entity keys must exactly match the registered identity keys")
        for key in entity.identity_keys:
            key_value = keys[key]
            if _is_missing(key_value) and not entity.allow_null:
                raise RoleFrameError(
                    "invalid_entity_ref", f"{path}.keys.{key}",
                    "null entity identity key is not allowed")
            _scalar(key_value, f"{path}.keys.{key}", allow_null=entity.allow_null)
        return
    if kind == "time":
        if (not isinstance(value, datetime) or value.tzinfo is None
                or _is_missing(value)):
            raise RoleFrameError(
                "invalid_time_role", path,
                "time Role must be a timezone-aware datetime")
        return
    if kind == "quantity":
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise RoleFrameError(
                "invalid_quantity_role", path, "quantity Role must be a JSON number")
        if not math.isfinite(float(value)):
            raise RoleFrameError(
                "invalid_quantity_role", path, "quantity Role must be finite")
        return
    if kind in {"identity", "order", "attribute", "symbolic"}:
        _scalar(value, path)
        if kind == "symbolic" and value not in role.allowed_values:
            raise RoleFrameError(
                "invalid_symbolic_value", path,
                f"value {value!r} is outside the registered symbolic domain")
        return
    raise RoleFrameError(
        "unsupported_role_kind", path, f"unsupported Role kind {kind!r}")


def _scalar(value: Any, path: str, *, allow_null: bool = False) -> None:
    if value is None and allow_null:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, numbers.Integral):
        return
    if isinstance(value, numbers.Real) and math.isfinite(float(value)):
        return
    if isinstance(value, str):
        return
    raise RoleFrameError(
        "invalid_scalar_role", path,
        "Role value must be a finite JSON scalar")


def compile_role_frame(context: MapperContext, role_frame: pd.DataFrame) -> pd.DataFrame:
    """Compile a normalized RoleFrame with the snapshot-owned Pack emission only."""
    normalized = validate_role_frame(context, role_frame)
    rows = []
    for position in range(len(normalized)):
        row = normalized.iloc[position]
        claim = _claim(context.snapshot, row["predicate"],
                       f"role_frame.rows[{position}].predicate")
        emission = claim.emission
        roles = row["roles"]
        subject = roles[emission.subject.role_id]
        occurred_at = roles[emission.occurred_at.role_id]
        obj_value = (None if emission.object_role is None
                     else roles.get(emission.object_role.role_id))
        qualifiers = {
            name: roles[reference.role_id]
            for name, reference in emission.qualifiers.items()
            if reference.role_id in roles
        }
        predicate = context.snapshot.vocabulary.get(emission.predicate_id)
        if predicate is None or predicate.status != "active":
            raise RoleFrameError(
                "invalid_predicate", f"{claim.config_path}.emit.predicate",
                "Pack emission requires an active registered predicate")
        if subject["type"] not in predicate.subject_entity_types:
            raise RoleFrameError(
                "invalid_entity_ref", f"role_frame.rows[{position}].roles."
                f"{emission.subject.role_id}.type",
                "subject Entity type is outside the Vocabulary signature")
        if emission.object_kind != predicate.object_kind:
            raise RoleFrameError(
                "invalid_predicate", f"{claim.config_path}.emit.object.kind",
                "Pack object kind disagrees with the Vocabulary signature")
        if (emission.object_kind == "entity_ref"
                and obj_value["type"] not in predicate.object_entity_types):
            raise RoleFrameError(
                "invalid_entity_ref", f"role_frame.rows[{position}].roles."
                f"{emission.object_role.role_id}.type",
                "object Entity type is outside the Vocabulary signature")
        qualifier_names = set(qualifiers)
        required_qualifiers = set(predicate.required_qualifiers)
        allowed_qualifiers = required_qualifiers | set(predicate.optional_qualifiers)
        if not required_qualifiers <= qualifier_names:
            missing = sorted(required_qualifiers - qualifier_names)[0]
            raise RoleFrameError(
                "missing_required_payload", f"{claim.config_path}.emit.object."
                f"qualifiers.{missing}",
                f"predicate requires qualifier {missing!r}")
        if not qualifier_names <= allowed_qualifiers:
            unknown = sorted(qualifier_names - allowed_qualifiers)[0]
            raise RoleFrameError(
                "unknown_payload_field", f"{claim.config_path}.emit.object."
                f"qualifiers.{unknown}",
                f"predicate does not allow qualifier {unknown!r}")
        if emission.object_kind == "none":
            object_kind = None
            object_payload = None
        elif emission.object_kind == "entity_ref":
            object_kind = "entity_ref"
            object_payload = {
                "type": _runtime_id(obj_value["type"]),
                "keys": _plain(obj_value["keys"]),
            }
        elif emission.object_kind == "value":
            object_kind = "value"
            object_payload = {"value": _plain(obj_value)}
        elif emission.object_kind == "event_ref":
            object_kind = "event_ref"
            object_payload = {"event": _plain(obj_value)}
        else:
            raise RoleFrameError(
                "unsupported_object_kind", f"{claim.config_path}.emit.object.kind",
                f"object kind {emission.object_kind!r} is unsupported")
        if qualifiers:
            object_payload["qualifiers"] = _plain(qualifiers)
        expected_id, event_state = source_event_identity(
            context.source_plan.source_id,
            occurred_at,
            molecule_ref=str(normalized.attrs["molecule_ref"]),
            source_raw_ref=str(normalized.attrs["source_raw_ref"]),
        )
        if expected_id != row["source_event_id"]:
            raise RoleFrameError(
                "invalid_source_event",
                f"role_frame.rows[{position}].source_event_id",
                "source_event_id does not match source provenance and occurred_at Role",
            )
        rows.append({
            "source_event_id": expected_id,
            "source_event_state": event_state,
            "subject_type": _runtime_id(subject["type"]),
            "subject_keys": _plain(subject["keys"]),
            "predicate": _runtime_id(emission.predicate_id),
            "object_kind": object_kind,
            "object_payload": object_payload,
            "occurred_at": occurred_at,
            "source_who": context.source_plan.source_id,
            "source_translator_ver": (
                f"ledger-v2:{context.snapshot.snapshot_sha256}#"
                f"{row['sentence']}"),
            "source_raw_ref": _claim_source_raw_ref(
                normalized.attrs["source_raw_ref"], row["source_row_refs"]),
            "supersedes": None,
            "molecule_ref": normalized.attrs["molecule_ref"],
            "derivation": row["sentence"],
        })
    frame = pd.DataFrame({
        column: pd.Series([row[column] for row in rows], dtype=object)
        for column in LEDGER_FRAME_COLUMNS
    })
    frame.attrs[LEDGER_FRAME_ATTR] = LEDGER_FRAME_SCHEMA_VERSION
    return validate_ledger_frame(frame)


def _claim_source_raw_ref(event_ref: str, row_refs: Sequence[str]) -> str:
    refs = tuple(sorted(set(row_refs)))
    if refs == (event_ref,):
        return event_ref
    return json.dumps(
        {"event": event_ref, "rows": refs}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class LedgerV2DryRunResult:
    role_frame: pd.DataFrame
    ledger_frame: pd.DataFrame
    gate_preview: Mapping[str, Any]
    provenance: Mapping[str, Any]
    snapshot_hash: str


def dry_run_event_frame(
    context: MapperContext,
    event_frame: pd.DataFrame,
    implementations: RoleMapperImplementationRegistry,
) -> LedgerV2DryRunResult:
    """Use the production mapper/compiler path and return candidates without writes."""
    _validate_event_frame(
        context, event_frame, context.source_plan.driver.mapper,
        context.source_plan.profile)
    role_frame = map_event_frame(context, event_frame, implementations)
    ledger_frame = compile_role_frame(context, role_frame)
    derivations = tuple(sorted(set(ledger_frame["derivation"].tolist())))
    subjects = tuple(sorted(set(ledger_frame["subject_type"].tolist())))
    sentences = tuple(sorted(set(role_frame["sentence"].tolist())))
    refs = tuple(sorted({ref for values in role_frame["source_row_refs"].tolist()
                         for ref in values}))
    gate_preview = MappingProxyType({
        "status": "candidate",
        "atom_count": len(ledger_frame),
        "source_event_id": str(event_frame.attrs["source_event_id"]),
        "declared_derivations": derivations,
        "declared_subject_types": subjects,
    })
    provenance = MappingProxyType({
        "source_id": event_frame.attrs["source_id"],
        "source_event_id": str(event_frame.attrs["source_event_id"]),
        "molecule_ref": event_frame.attrs["molecule_ref"],
        "source_raw_ref": event_frame.attrs["source_raw_ref"],
        "sentences": sentences,
        "source_row_refs": refs,
        "mapper_implementation": (
            f"{context.source_plan.driver.mapper.implementation.implementation_id}@"
            f"{context.source_plan.driver.mapper.implementation.implementation_version}"
        ),
        "setup_snapshot_hash": context.snapshot.snapshot_sha256,
    })
    return LedgerV2DryRunResult(
        role_frame=role_frame,
        ledger_frame=ledger_frame,
        gate_preview=gate_preview,
        provenance=provenance,
        snapshot_hash=context.snapshot.snapshot_sha256,
    )
