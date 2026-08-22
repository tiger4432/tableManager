"""What one declaration FORCES, and what a person still genuinely has to answer.

This module is the engine behind the authoring panels.  It reads a bundle (valid or
half-written) plus the physical catalog and returns, for every authoring field it knows
about, one of four states:

* ``derived``    -- another declaration determines this.  The screen fills it and does
                    NOT ask.  Zero degrees of freedom.
* ``missing``    -- forced to exist, and it is not there.  A to-do item.
* ``unanswered`` -- genuinely free, and not chosen yet.  A question, with its candidates.
* ``answered``   -- genuinely free, and chosen.

🔴 EVERY DERIVED FIELD CARRIES ITS GROUND, AND THE INVARIANT IS ENFORCED IN CODE.
`Field.__post_init__` refuses to build a ``derived`` record without a `Ground` naming the
declaration it came from and the Korean sentence the screen shows beside the value.  This
is not stylistic.  On 2026-08-18 a `basis: "ingested"` source resolved a grouped event's
time from one row's `created_at`; 26 of 396 jobs had rows from two ingestion batches, and
12 wrong atoms landed reading "59 dies" where the answer was 72 -- the engine chose
silently and the silence became data.  A screen that fills a field without saying what
filled it reproduces that defect at authoring scale, one config at a time.  So: if a
derivation cannot state its ground, it is a guess, and this module emits ``unanswered``
with candidates instead of a filled value.

WHY DERIVE AT ALL, rather than validate better.  Measured 2026-08-18: ~40 refusals across
one two-hour setup session, of which about five were actual decisions.  The rest were
transcriptions of things already written elsewhere and checked for exact equality --
`profile.packs` against the mappings' `use`, `mapper.emits` against the same set, an
entity binding's `keys` against the entity's `keys`.  A field checked for exact equality
against another declaration cannot be written BETTER, only WRONG.  Improving its refusal
message is the weakest available fix; removing the question is the strongest.

The first two of those three took the strongest fix on 2026-08-21 and are no longer
fields at all -- `bind` and `map` do not carry them, and `MapperDescriptor.emits` is
compiled from `bind.mappings.<sentence>.predicate`.  A `derived` row still costs the
operator a line in the file and a row on the screen; a retired one costs neither.

Later the same day the WHOLE `packs` step went the same way.  Every field it had restated
its predicate, so `_mapping_fields` now lays the Role slots out from the vocabulary and
asks only for each slot's material.

The tiers, strongest first, are recorded per field in ``tier`` so a reader can audit that
ranking rather than take it on faith:
``structural`` > ``derivation`` > ``constrained_input`` > ``diagnostic``.

NOTHING HERE TOUCHES A FILE.  The plan is a read over a bundle mapping and the catalog,
and `filled_declaration` -- the one function that produces a document rather than a
description of one -- returns a new mapping.  `config_drafts` is still the only writer;
it calls that function at the moment of save so a square the screen says is FILLED is
filled in the file too, rather than being refused as missing one step later.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field as dataclass_field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .column_stats import declared_unique_keys
from .config_explorer import AUTHORABLE_SECTIONS
from .implementations import (
    # Private on purpose over there and imported anyway: it is the ONE spelling of "a
    # source-specific implementation lives under this package", and `_registered_ids`
    # ranks candidates by exactly that distinction.  A second copy of the word here is
    # the hand-kept list `implementations.py` exists to have deleted.
    _IMPLEMENTATION_PACKAGE,
    mapper_declarations,
    source_preparer_declarations,
)
from .setup_bundle import (
    _MAPPER_UNITS,
    _OBJECT_KINDS,
    _OCCURRED_AT_BASES,
    _ROLE_KINDS,
    _SCALAR_ROLE_KINDS,
    _SOURCE_UNITS,
    PHYSICAL_CATALOG_FILENAME,
    SUBJECT_ROLE,
    predicate_claim,
    public_bundle_schema,
    role_binding_kinds,
    validate_bundle_errors,
)

#: `setup_bundle` spells these inline in `_validate_vocabulary` rather than binding them
#: to a name, so this is the one closed list this module cannot import.  Kept next to the
#: imports so the day it becomes a constant there, the fix is one line here.
PREDICATE_STATUSES = ("active", "retired")

#: The canonical predicate whose emission makes `read.registration_probe` load-bearing.
#: It is `vocabulary.PREDICATES["register"]`, and the atom spelling -- not the config's
#: `register@1` address -- is what `runtime_v2._filtered_event_atoms` and
#: its two `atom.predicate == "register"` tests compare against.  Named here rather
#: than spelled inline so the three sites are one grep.
REGISTER_PREDICATE = "register"

TIER_STRUCTURAL = "structural"
TIER_DERIVATION = "derivation"
TIER_CONSTRAINED = "constrained_input"
TIER_DIAGNOSTIC = "diagnostic"

#: The authoring order, which is also the dependency order: a later step references
#: earlier ones.  Published (id AND label) so the step bar has no list literal in the UI.
#:
#: 🔴 FOUR, NOT SIX, SINCE 2026-08-20. The 「준비기·매퍼」 layer named two sections that no
#: longer exist -- both bodies live inside a source plan now -- so the layer had nothing to
#: count and would have rendered as a permanently empty band. 「프로필」 went the same way
#: the same evening. Their FIELDS did not vanish with the layers: all of them moved to the
#: `sources` step, which is where the operator now writes them, and a source is therefore
#: authored in ONE band instead of being started in one and finished in another.
#:
#: 🔴 THREE SINCE 2026-08-21, and this one is a REAL band that stopped existing. 「팩」 had
#: fields of its own -- Role kinds, `emit` endpoints, qualifier refs -- and every one of
#: them was a transcription of the predicate one band earlier. They did not move to
#: `sources`; they stopped being questions. What the operator answers instead is the
#: binding for each Role the predicate forces, which `_mapping_fields` lays out.
STEPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("entities", "엔터티", ("entities",)),
    ("vocabulary", "낱말", ("vocabulary",)),
    ("sources", "소스", ("sources",)),
)

#: The three column universes of §3E, which are NOT one set.  Measured: a preparer output
#: (`target_id`) passes in `read.identity` and is refused in `read.order_by` with
#: `unknown_column ... is not in relation`.  Same name, different answer, so a single
#: merged dropdown would hide half the real columns and offer half that do not exist.
UNIVERSE_RELATION = "RELATION"
UNIVERSE_PREPARED = "PREPARED"

_UNIVERSE_NOTE = {
    UNIVERSE_RELATION: "물리 표 컬럼",
    UNIVERSE_PREPARED: "물리 표 + 준비기 산출 컬럼",
}

_ABSENT = object()

#: section -> the node kind the explorer tree uses, so a ground path can be turned into
#: something CLICKABLE.  Imported rather than restated: `AUTHORABLE_SECTIONS` is already
#: the one map from kind to section and is scored against the index by a test.
_KIND_BY_SECTION = {
    section: kind for kind, section in AUTHORABLE_SECTIONS.items()}


def ground_node_key(path: str) -> str | None:
    """`bundle.entities.DTJob@1.keys` -> `entity|DTJob@1`, or None if not a declaration.

    🔴 THIS IS THE OVERRIDE AFFORDANCE FOR A ZERO-FREEDOM FIELD.  Owner rule: a derived
    value a person cannot change is force, and force must not be rendered as a greyed
    box.  For a field whose value is fixed by ANOTHER declaration, the lever is not on
    this field at all -- it is on that declaration.  So the screen sends the person
    there instead of showing them a control that does nothing.
    """
    steps = _split_path(path)
    if len(steps) < 2 or not isinstance(steps[0], str) or not isinstance(steps[1], str):
        return None
    kind = _KIND_BY_SECTION.get(steps[0])
    return f"{kind}|{steps[1]}" if kind else None


class AuthoringGroundError(RuntimeError):
    """A derivation tried to fill a field without naming what filled it."""


@dataclass(frozen=True)
class Ground:
    """Where a derived value came from -- rendered NEXT TO the value, never in a tooltip."""

    rule: str
    text: str
    from_paths: tuple[str, ...]
    from_value: Any = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "text": self.text,
            "from_paths": list(self.from_paths),
            # Deduplicated and order-preserving: eight binding paths under one profile
            # are one place to go, not eight.
            "from_keys": list(dict.fromkeys(
                key for key in map(ground_node_key, self.from_paths) if key)),
            "from_value": _plain(self.from_value),
        }


@dataclass(frozen=True)
class Field:
    path: str
    step: str
    label: str
    state: str
    tier: str
    value: Any = None
    declared: Any = _ABSENT
    ground: Ground | None = None
    candidates: tuple[Any, ...] | None = None
    universe: str | None = None
    note: str = ""
    #: How the derived value relates to what the file says.  ``equal`` is the zero-freedom
    #: case; ``superset`` is a derived MINIMUM that a wider declaration still satisfies.
    #: Getting this wrong paints a legal declaration red -- measured on
    #: `lot-event-role@1.input_columns`, where the file declares 10 and the bindings need
    #: 4, and an equality comparison called that a conflict.
    comparison: str = "equal"
    #: 🔴 WHAT A PERSON MAY DO ABOUT A FILLED VALUE.  Owner rule, 2026-08-19: a derived
    #: field renders its value AND its ground AND can be overridden -- and a field that
    #: CANNOT be overridden is not derivation, it is force, and force belongs out of the
    #: file entirely rather than behind a disabled input.  A greyed box is the worst of
    #: the three: it occupies space, cannot be acted on, and still implies a choice.
    #: So every derived row must land on one of:
    #:   `remove_from_file`      -- MEASURED removable: deleting it still validates.
    #:   `grammar_requires_it`   -- MEASURED not removable: the grammar demands the key
    #:                              even though its value is forced.  An open item, said
    #:                              out loud, not a locked control.
    #:   `default_overridable`   -- a default with a ground; the author may widen/change.
    #:   `shape`                 -- not a file leaf at all (a row set, a slot list).
    #:   `unmeasured`            -- the bundle does not validate, so a removal probe
    #:                              would be confounded by errors it did not cause.
    disposition: str = ""
    #: Names this field may NOT take, with the same standing as candidates.  A forbidden
    #: list is not a value: putting it in ``value`` would tell the screen to fill the
    #: field with the very names that are refused.
    forbidden: tuple[Any, ...] = dataclass_field(default_factory=tuple)
    refusals: tuple[Mapping[str, str], ...] = dataclass_field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.state not in {"derived", "missing", "unanswered", "answered"}:
            raise ValueError(f"unknown authoring state {self.state!r}")
        if self.state == "derived":
            # 🔴 The invariant. See the module docstring: a fill without a stated ground
            # is the UI-scale shape of the grouped-event `basis` defect.
            if self.ground is None or not self.ground.text or not self.ground.from_paths:
                raise AuthoringGroundError(
                    f"{self.path}: derived field must state its ground "
                    f"(rule, Korean text, and the declaration path it came from)")

    @property
    def conflicts(self) -> bool:
        """The file says something the derivation refuses. The derivation is the rule."""
        if self.state != "derived" or self.declared is _ABSENT:
            return False
        if self.comparison == "superset":
            required = _plain(self.value) or []
            declared = _plain(self.declared) or []
            return not set(map(repr, required)) <= set(map(repr, declared))
        return _plain(self.declared) != _plain(self.value)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "step": self.step,
            "label": self.label,
            "state": self.state,
            "tier": self.tier,
            "value": _plain(self.value),
            "declared": None if self.declared is _ABSENT else _plain(self.declared),
            "has_declared": self.declared is not _ABSENT,
            "conflicts": self.conflicts,
            "ground": self.ground.to_mapping() if self.ground else None,
            "candidates": None if self.candidates is None else [
                _plain(item) for item in self.candidates],
            "universe": self.universe,
            "universe_note": _UNIVERSE_NOTE.get(self.universe or "", ""),
            "comparison": self.comparison,
            "disposition": self.disposition,
            "forbidden": [_plain(item) for item in self.forbidden],
            "note": self.note,
            "refusals": [dict(item) for item in self.refusals],
        }


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_plain(item) for item in value]
        return sorted(items, key=repr) if isinstance(value, (set, frozenset)) else items
    return value


def _section(bundle: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = bundle.get(name)
    return value if isinstance(value, Mapping) else {}


def _mappings(profile: Any) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """The mappings of one `bind` clause, as (sentence, mapping) pairs.

    A map keyed by sentence as of 2026-08-21; it was a list, and the caller's index was
    the address.  Sorted so the authoring rows are stable whatever order the file holds.
    """
    if not isinstance(profile, Mapping):
        return ()
    value = profile.get("mappings")
    if not isinstance(value, Mapping):
        return ()
    return tuple(sorted(
        (key, item) for key, item in value.items() if isinstance(item, Mapping)))


def _listed(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _role_name(ref: Any) -> str:
    if not isinstance(ref, str) or not ref.startswith("$"):
        return ""
    return ref[1:].removesuffix("?")


def is_remaining(row: Mapping[str, Any]) -> bool:
    """Does a PERSON still have to decide this one?

    The number rendered as 「정할 것 n개 남음」, and it is the one thing about a progress
    indicator that has to be right: an operator who sees work remaining on a finished
    declaration stops reading the number, and an ignored indicator is worse than an absent
    one because it costs a glance forever.

    So it counts neither fields nor problems nor the 164 rows:

      * `derived` is never counted -- nobody decides it, that is what derived means;
      * a person-decided field that is FILLED is done, not remaining;
      * a field carrying a refusal is remaining even though it has a value, because the
        value is one somebody has to revisit.

    🔴 `missing` AND `unanswered` ARE NOT THE SAME EMPTY, and only the first counts.
    `config_authoring` spells them `state="missing" if required else "unanswered"`, so
    `unanswered` means OPTIONAL AND ABSENT -- a question nobody is obliged to answer.
    Counting it measured 1 remaining on the live config, which is complete and valid
    (`sources.dt_job.prepare.output_columns`), i.e. a finished setup reporting
    unfinished work on the first screen an operator sees.

    This is also the predicate the collapse rule has to agree with. If the count says 3
    remain and the folding hides one of the 3, the screen contradicts itself and the
    operator trusts neither number -- so both read THIS, rather than each deciding.
    """
    if row.get("state") == "derived":
        return False
    if row.get("state") == "missing":
        return True
    return bool(row.get("refusals")) or bool(row.get("conflicts"))


# 🔴 NOT IN THE CONFIG ROOT. `_config_root_errors` refuses any file beside
# `ledger_config.json` there -- "the setup is one file" -- so a skeleton parked next to the
# operator's config takes the whole setup down. Measured: 12 errors across the explorer
# suite the moment it landed there. It belongs beside the validator anyway; it describes
# the grammar that module enforces, and it ships with the code rather than with the data.
SKELETON_PATH = Path(__file__).parent / "ledger_skeleton.json"


@lru_cache(maxsize=1)
def skeleton() -> dict[str, Any]:
    """The shape of a ledger config, as a document.

    Owner's ruling, 2026-08-20: 「관리문서 = 스켈레톤」.  The screen generates its form from
    this instead of carrying a hand-written table of the grammar -- a second author of a
    contract drifts in silence, which is how `emit.object` came to offer `kind` and `value`
    while the validator had allowed `entity` and `qualifiers` all along, with nothing red.

    It is a GUIDE, not a gate: the validator still decides what is good, and this only
    decides what the form OFFERS.  `test_ledger_skeleton.py` counts the drift in both
    directions against the validator's own field tuples and requires both counts to be 0.

    Read from beside the module rather than through `config_path()`: this ships with the
    code, it is not operator data, so a stack pointed at another data root still finds it
    -- and the config root will not have it, by that root's own rule.
    """
    return json.loads(SKELETON_PATH.read_text(encoding="utf-8"))


def _deref(node: Any, defs: Mapping[str, Any], seen: frozenset[str]) -> Any:
    """Follow `{use}` to a real node, refusing to chase a definition through itself."""
    while isinstance(node, Mapping) and isinstance(node.get("use"), str):
        name = node["use"]
        if name in seen:
            return None
        seen = seen | {name}
        node = defs.get(name)
    return node


def empty_value(node: Any, defs: Mapping[str, Any],
                seen: frozenset[str] = frozenset()) -> Any:
    """The emptiest document of this node's shape, with required CONTAINERS already there.

    🔴 A CONTAINER THE GRAMMAR REQUIRES CANNOT WAIT FOR ITS FIRST MEMBER.  Owner, on a new
    predicate: 「qualifier 안넣을건데 이거 기본으로 키 안들어가 있어서 에러남」.  The form built a
    map only when somebody added a member to it, so a person who wants NO qualifiers had no
    way to produce `qualifiers: {...}` -- the validator asked for a key that the screen could
    only create by adding something and taking it away again.

    Containers, and the one leaf whose control cannot DRAW its own absence.  A required text
    or choice leaf stays absent on purpose: absent is `missing_field`, which tells the
    operator to fill it, while a seeded `""` would read as a value they chose -- and the
    screen can show that, because an empty box and a blank select both look unanswered.

    🔴 A CHECKBOX HAS NO BLANK.  `hint: flag` draws `checked = value === true`, so `undefined`
    and `false` are PIXEL-IDENTICAL: the operator reads "answered, false", saves, and gets
    `invalid_type` + `missing_field` on a field the screen showed them as settled.  Owner,
    walking a new source: the only way through was to tick the box on and back off.  Here the
    seeded value is not a guess about what they meant -- it is the value the screen was
    ALREADY showing them, so the file stops disagreeing with the pixels.

    The class, not the case.  `accepts_verified_join_rules` is the one that showed today;
    the skeleton has two required flags (`virtual_joins.*.enabled` is the other -- the
    third, `packs.*.claims.*.roles.*.required`, left with its section on 2026-08-21), and
    the hint is READ, so a third is covered the day it is declared.  `entities.*.allow_null` is `required: false` and stays absent --
    seeding what is NOT required is the complaint below, coming straight back.

    Nothing here knows a field by name -- it asks the skeleton whether the field is required
    and what its control is, so the next section with the same shape is covered without being
    mentioned.

    🔴 REQUIRED IS NOT UNCONDITIONAL: `when` SAYS WHO IT IS REQUIRED OF.  Four fields of
    `defs.binding` are `required: true` behind a `when` gate on `kind` -- `column`, `value`,
    `entity_type`, `keys` -- and a brand-new binding has no `kind` at all, so none of them
    is required OF IT yet.  Seeding the one that happens to be a container gave every new
    binding a `keys: {}` its own kind forbids, and the form has no control that takes a
    REQUIRED field back out; building a source through the form ended at two
    `unknown_field` refusals nobody could clear.

    So the gate is ASKED, never listed.  `when` appears at eight sites in the skeleton and
    names four different kinds; a set of kinds written here would be a second author for
    the grammar and would go stale the first time the skeleton changes its mind -- silently,
    which is the failure this module keeps removing.  The gate is read against the record as
    it is being seeded, so an ungated required container (`qualifiers`, the complaint this
    function exists for) still lands exactly as before.
    """
    shape = _deref(node, defs, seen)
    if not isinstance(shape, Mapping):
        return ""
    kind = shape.get("kind")
    if kind == "map":
        return [] if shape.get("keyed_by") == "index" else {}
    if kind == "record":
        seeded: dict[str, Any] = {}
        for field in shape.get("fields") or []:
            if field.get("required") is not True:
                continue
            gate = field.get("when")
            if isinstance(gate, Mapping) and seeded.get(gate.get("field")) != gate.get("is"):
                continue
            child = _deref(field.get("node"), defs, seen)
            if not isinstance(child, Mapping):
                continue
            if child.get("kind") == "leaf" and child.get("hint") != "flag":
                continue
            seeded[field["key"]] = empty_value(field.get("node"), defs, seen)
        return seeded
    return False if shape.get("hint") == "flag" else ""


def empty_declaration(section: str) -> dict[str, Any]:
    """What a brand-new declaration of `section` starts as, per the skeleton."""
    doc = skeleton()
    node = doc.get("root", {})
    for step in (section, "*"):
        node = _deref(node, doc.get("defs", {}), frozenset())
        if not isinstance(node, Mapping):
            return {}
        if node.get("kind") == "record":
            field = next((item for item in node.get("fields") or []
                          if item.get("key") == step), None)
            node = field.get("node") if field else None
        elif node.get("kind") == "map":
            node = node.get("of")
        else:
            return {}
    value = empty_value(node, doc.get("defs", {}))
    return value if isinstance(value, dict) else {}


@lru_cache(maxsize=1)
def versioned_sections() -> frozenset[str]:
    """Which sections does the validator require `id@version` of? ASKED, not listed.

    🔴 FOUR OF THE FIVE REQUIRE IT AND ONE DOES NOT -- sources are keyed `dt_job`, no `@`.
    So "always append @1" breaks sources, and a hand-written list of the other four is the
    hardcode this round keeps removing: it would go stale the day the grammar changes its
    mind, and go stale SILENTLY.

    So the answer is measured. Each section is handed a declaration named without a version
    and the validator is asked what it thinks; the sections that come back with
    `invalid_versioned_id` against that name are the ones that carry versions. The screen
    never decides this -- it reads the answer.

    🔴 AND THE 2026-08-20 MERGE IS THE PROOF THAT WAS WORTH IT. `source_preparers` and
    `mappers` were two of the six; both moved inside a source plan and stopped having ids
    at all. This function was not edited, no list of kinds was edited, and the answer went
    from six sections to four on its own. A hardcoded list would have kept publishing
    `versioned: true` for two kinds that no longer exist.
    """
    from .setup_bundle import validate_bundle_errors

    probe = "zzprobeid"                      # deliberately unversioned
    carries: set[str] = set()
    for section in AUTHORABLE_SECTIONS.values():
        # `catalog` is required by name -- omitting it refuses before any section is read,
        # which is how the first version of this probe measured 0 for all of them.
        errors = validate_bundle_errors(
            {section: {probe: empty_declaration(section)}}, catalog={})
        # The path must END at the declaration's own name. A source refuses a versioned id
        # at `...zzprobeid.read.registration_probe[0].entity_type` and, until 2026-08-20,
        # at `...zzprobeid.profile_id` -- those are REFERENCES it holds, not its own key,
        # and counting them would have made every section look versioned.
        if any(error.code == "invalid_versioned_id"
               and error.path == f"bundle.{section}.{probe}"
               for error in errors):
            carries.add(section)
    return frozenset(carries)


def closed_lists() -> dict[str, Any]:
    """Every closed list the authoring screen may offer, from the code that enforces it.

    The screen renders what this returns and owns no copy.  A list literal in the UI is
    a second author for a value whose first author is a validator, and the two diverge in
    silence on the day a declaration is added -- which is the same failure mode as the
    `tables` section that was removed from the ledger config for duplicating the catalog.
    """
    schema = public_bundle_schema()
    return {
        **schema,
        "predicate_status": list(PREDICATE_STATUSES),
        "object_kind": sorted(_OBJECT_KINDS),
        "role_kind": sorted(_ROLE_KINDS),
        "scalar_role_kind": sorted(_SCALAR_ROLE_KINDS),
        "source_unit": sorted(_SOURCE_UNITS),
        "mapper_unit": sorted(_MAPPER_UNITS),
        "occurred_at_basis": sorted(_OCCURRED_AT_BASES),
        "column_universes": [
            {"id": name, "note": note} for name, note in _UNIVERSE_NOTE.items()],
        "steps": [{"id": step, "label": label} for step, label, _ in STEPS],
        # 🔴 THE FORM'S SHAPE RIDES THE PAYLOAD THE SCREEN ALREADY FETCHES. Rule 5 of the
        # skeleton spec: one more key here, rather than an endpoint and a request the
        # client would have to learn to sequence against the plan it already waits for.
        "skeleton": skeleton(),
        # 🔴 WHAT THE SCREEN MAY AUTHOR, FROM THE MAP THAT DECIDES IT. The tree only
        # renders kinds that already have members, so an empty section had no entry point
        # at all -- you could not create the first pack because there was nowhere to click.
        # Sourced from `AUTHORABLE_SECTIONS`, which is also what `deletion_plan` reads, so
        # the screen cannot offer to create something it could not then remove.
        # 🔴 `versioned` RIDES ALONG SO THE SCREEN NEVER HOLDS THE LIST. Four of the five
        # need `id@version` and sources do not, so "always append @1" breaks sources and a
        # list of the other four in the client is a hardcode that goes stale in silence.
        # `versioned_sections()` asks the validator instead of asserting -- see its comment.
        "authorable_kinds": [
            {"id": kind, "section": section,
             "versioned": section in versioned_sections()}
            for kind, section in sorted(AUTHORABLE_SECTIONS.items())
        ],
        "tiers": [
            {"id": TIER_STRUCTURAL, "label": "구조적 제거"},
            {"id": TIER_DERIVATION, "label": "유도"},
            {"id": TIER_CONSTRAINED, "label": "제약 입력"},
            {"id": TIER_DIAGNOSTIC, "label": "진단"},
        ],
    }


# --------------------------------------------------------------------------- universes


def relation_columns(catalog: Mapping[str, Any], relation: Any) -> tuple[str, ...]:
    table = catalog.get(relation) if isinstance(relation, str) else None
    columns = table.get("columns") if isinstance(table, Mapping) else None
    return tuple(sorted(columns)) if isinstance(columns, Mapping) else ()


def _column_types(catalog: Mapping[str, Any], relation: Any) -> Mapping[str, str]:
    table = catalog.get(relation) if isinstance(relation, str) else None
    columns = table.get("columns") if isinstance(table, Mapping) else None
    return columns if isinstance(columns, Mapping) else {}


def prepared_columns(bundle: Mapping[str, Any], catalog: Mapping[str, Any],
                     source: Mapping[str, Any]) -> tuple[str, ...]:
    """RELATION ∪ the preparer's `output_columns` -- mirrors `available` in the validator.

    Kept as its own function because the profile's column bindings are checked against
    THIS set (`_binding_refs` receives `available`), not against the mapper's
    `input_columns`.  Once `input_columns` is derived from the bindings, PREPARED is the
    only universe a person picks from, and offering RELATION there would hide every
    preparer-made column.

    `bundle` is no longer read -- the preparer is a clause of `source` itself as of
    2026-08-20 -- and stays in the signature because every caller has it and the parameter
    names what this set is derived FROM.
    """
    columns = set(relation_columns(catalog, _driver_relation(source)))
    outputs = _preparation(source).get("output_columns")
    if isinstance(outputs, Mapping):
        columns.update(str(name) for name in outputs)
    return tuple(sorted(columns))


def _driver(source: Any) -> Mapping[str, Any]:
    """The source's `read` clause.  Named for the plan it compiles into, not the key.

    `driver` split into `read`/`prepare`/`map` in the FILE on 2026-08-21; `SourceDriverPlan`
    did not, so this reader keeps the compiled word and changes only which key it opens.
    """
    driver = source.get("read") if isinstance(source, Mapping) else None
    return driver if isinstance(driver, Mapping) else {}


def _driver_relation(source: Any) -> Any:
    return source.get("relation") if isinstance(source, Mapping) else None


def _preparation(source: Any) -> Mapping[str, Any]:
    prep = source.get("prepare") if isinstance(source, Mapping) else None
    return prep if isinstance(prep, Mapping) else {}


def _mapper(source: Any) -> Mapping[str, Any]:
    mapper = source.get("map") if isinstance(source, Mapping) else None
    return mapper if isinstance(mapper, Mapping) else {}


def _binding_columns(binding: Any, path: str) -> list[tuple[str, str]]:
    """Every column a binding names, with the exact authoring path that names it."""
    if not isinstance(binding, Mapping):
        return []
    if binding.get("kind") == "column":
        column = binding.get("column")
        return [(column, f"{path}.column")] if isinstance(column, str) else []
    out: list[tuple[str, str]] = []
    keys = binding.get("keys")
    if isinstance(keys, Mapping):
        for key in sorted(keys, key=str):
            out.extend(_binding_columns(keys[key], f"{path}.keys.{key}"))
    return out


def profile_binding_columns(path: str, profile: Any
                            ) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for sentence, mapping in _mappings(profile):
        base = f"{path}.mappings.{sentence}.bind"
        bind = mapping.get("bind")
        if not isinstance(bind, Mapping):
            continue
        for role in sorted(bind, key=str):
            out.extend(_binding_columns(bind[role], f"{base}.{role}"))
    return tuple(out)


# ------------------------------------------------------------------------- derivations


def _entities_fields(bundle: Mapping[str, Any]) -> Iterable[Field]:
    for entity_id in sorted(_section(bundle, "entities"), key=str):
        entity = _section(bundle, "entities")[entity_id]
        keys = _listed(entity.get("keys")) if isinstance(entity, Mapping) else ()
        yield Field(
            path=f"bundle.entities.{entity_id}.keys",
            step="entities", label="식별키",
            state="answered" if keys else "missing",
            tier=TIER_CONSTRAINED,
            value=list(keys), declared=list(keys) if keys else _ABSENT,
            note="이 이름이 이후 모든 entity binding의 keys를 결정한다.",
        )


def _vocabulary_fields(bundle: Mapping[str, Any]) -> Iterable[Field]:
    entities = sorted(_section(bundle, "entities"), key=str)
    for predicate_id in sorted(_section(bundle, "vocabulary"), key=str):
        predicate = _section(bundle, "vocabulary")[predicate_id]
        if not isinstance(predicate, Mapping):
            continue
        base = f"bundle.vocabulary.{predicate_id}"
        subjects = _listed(predicate.get("subjects"))
        yield Field(
            path=f"{base}.subjects", step="vocabulary", label="주어 타입",
            state="answered" if subjects else "missing", tier=TIER_CONSTRAINED,
            value=list(subjects), declared=list(subjects) if subjects else _ABSENT,
            candidates=tuple(entities),
        )
        obj = predicate.get("object")
        obj = obj if isinstance(obj, Mapping) else {}
        kind = obj.get("kind")
        yield Field(
            path=f"{base}.object.kind", step="vocabulary", label="목적어 종류",
            state="answered" if kind else "missing", tier=TIER_CONSTRAINED,
            value=kind, declared=kind if kind else _ABSENT,
            candidates=tuple(sorted(_OBJECT_KINDS)),
        )
        if kind == "entity_ref":
            types = _listed(obj.get("types"))
            yield Field(
                path=f"{base}.object.types", step="vocabulary", label="목적어 엔터티",
                state="answered" if types else "missing", tier=TIER_CONSTRAINED,
                value=list(types), declared=list(types) if types else _ABSENT,
                candidates=tuple(entities),
                note="entity_ref일 때만 존재하는 칸.",
            )


#: The one line the candidate list needs beside it.  A name that is not on the list yet is
#: NOT a wall: `/admin/scripts/code` reads and writes Python under `mappers/`, and
#: `implementations._descendants()` picks a newly written class up on the next start.  Said
#: once, because the preparer list and the mapper list are the same situation.
NEW_IMPLEMENTATION_NOTE = (
    "새 구현: /admin/scripts/code 에서 mappers/ledger_v2_*.py 작성 · 서버 재시작 후 후보")


def _registered_ids(declarations: Mapping[tuple[str, int], type]) -> tuple[str, ...]:
    """The addressable implementation names, GENERIC ONES FIRST.

    🔴 THE ORDER IS THE ADVICE.  Most sources need no code at all -- a shape that says N
    things per row is `DeclarativeRoleMapper`'s whole job -- and a person reading an
    alphabetical list top-down meets somebody else's source-specific class first and
    concludes they have to write one.  So the ranking is MEASURED off where the class
    lives: `ledger.*` ships with the engine and is generic by construction, while
    `mappers/ledger_v2_*.py` is one operator's one source.  `_IMPLEMENTATION_PACKAGE` is
    the same constant the discovery walk uses, so a rename moves both together -- naming
    the generic implementation here would be this module keeping a copy of the registry's
    most important entry, which is the bookkeeping `implementations.py` exists to end.
    """
    ranked = sorted(
        (implementation.__module__.startswith(f"{_IMPLEMENTATION_PACKAGE}."), identifier)
        for (identifier, _version), implementation in declarations.items())
    return tuple(dict.fromkeys(identifier for _specific, identifier in ranked))


def _registered_versions(declarations: Mapping[tuple[str, int], type],
                         identifier: Any) -> tuple[int, ...]:
    """Every version registered under this name, ascending."""
    if not isinstance(identifier, str):
        return ()
    return tuple(sorted(version for name, version in declarations if name == identifier))


def _implementation_clause_fields(base: str, clause: Mapping[str, Any],
                                  declarations: Mapping[tuple[str, int], type],
                                  identifiers: tuple[str, ...],
                                  label: str, note: str) -> Iterable[Field]:
    """`implementation_id` + `implementation_version` for one clause -- one question, not two.

    🔴 THE VERSION IS NOT A SECOND DECISION, AND ASKING FOR IT AS ONE IS WHAT THE FORM DID.
    The registry is keyed by `(id, version)` and every trusted address is stated BY THE
    CLASS (`implementations._self_declared_identity`), so picking the name has already
    picked the number: measured 2026-08-21, all 2 preparers and all 3 mappers register
    exactly one version each.  The old form drew a bare number box beside a bare text box,
    which is two ways to be wrong about one fact -- `unsupported_implementation_version`
    lands at compile time on a person who typed the only other integer they could think of.

    So the id gets the candidates and the version gets `derived` with the id as its ground.
    `derived` is the word for zero degrees of freedom, not a picker with one entry: a
    single-candidate row is still a question, and this one has no question left in it.

    The version's `declared` is compared ONLY where the registry knows the name.  An id
    nothing has registered already carries `untrusted_implementation` on its own row, and
    painting the VERSION red for it would put the refusal one square away from its cause.
    """
    identifier = clause.get("implementation_id")
    yield Field(
        path=f"{base}.implementation_id", step="sources", label=label,
        state="answered" if identifier else "missing", tier=TIER_CONSTRAINED,
        value=identifier, declared=identifier if identifier else _ABSENT,
        candidates=identifiers,
        note=note,
    )
    versions = _registered_versions(declarations, identifier)
    yield Field(
        path=f"{base}.implementation_version", step="sources",
        label=f"{label} 버전", state="derived", tier=TIER_STRUCTURAL,
        value=versions[-1] if versions else None,
        declared=clause.get("implementation_version", _ABSENT) if versions else _ABSENT,
        ground=Ground(
            "implementation_version_from_registered_id",
            (f"채움: 등록된 {identifier}@{versions[-1]}"
             + (f" · 이 이름의 등록 버전 {len(versions)}개" if len(versions) > 1 else "")
             ) if versions else "채움: implementation_id를 고르면 버전이 따라온다",
            (f"{base}.implementation_id",), versions[-1] if versions else None),
    )


def _implementation_fields(bundle: Mapping[str, Any], catalog: Mapping[str, Any]
                           ) -> Iterable[Field]:
    """The preparer and mapper clauses of every source, walked FROM the source.

    🔴 THE OWNER LOOKUP IS GONE, AND THAT IS THE POINT OF THE 2026-08-20 MOVE.  This
    function used to walk two sections and search backwards for the source that selected
    each member -- which is why an unselected mapper got a 「소스 미연결」 diagnostic row: it
    was a shape the file could hold and nothing could interpret.  A body inside a source
    always has its source, its `relation`, and therefore its column universes.
    """
    sources = _section(bundle, "sources")
    # Read ONCE per plan rather than per source: `_declarations` re-walks `mappers/` on
    # every call, and the answer cannot change between two sources of one bundle.  Not
    # cached across calls on purpose -- a class written through `/admin/scripts/code` has
    # to appear the moment the process that imported it serves the next plan.
    preparers = source_preparer_declarations()
    mappers = mapper_declarations()
    preparer_ids = _registered_ids(preparers)
    mapper_ids = _registered_ids(mappers)
    for source_id in sorted(sources, key=str):
        source = sources[source_id]
        if not isinstance(source, Mapping):
            continue
        profile = source.get("bind") if isinstance(source.get("bind"), Mapping) else None
        profile_base = f"bundle.sources.{source_id}.bind"
        relation = _driver_relation(source)
        physical = relation_columns(catalog, relation)
        prepared = prepared_columns(bundle, catalog, source)

        # ------------------------------------------------------------------ preparer
        preparation = _preparation(source)
        prep_base = f"bundle.sources.{source_id}.prepare"
        # Not gated on `physical`: which preparer runs is a fact about the REGISTRY, and a
        # source whose relation is not in the catalog yet still has to be able to name one.
        yield from _implementation_clause_fields(
            prep_base, preparation, preparers, preparer_ids, "준비기 구현",
            NEW_IMPLEMENTATION_NOTE)
        if physical:
            # 🔴 MEMBERSHIP, NOT TRUTHINESS, AND `dt_job` IS WHY.  `_nonblank_list` passes
            # `allow_empty=True` for this key, so `[]` is a LEGAL answer and `dt_job`
            # declares exactly that.  `inputs if inputs else _ABSENT` -- what stood here --
            # reported that declaration as `has_declared: false`, which under the default
            # below would hand the square to the derivation and write all 24 columns into a
            # source that said it wanted none.
            declared_inputs = (list(_listed(preparation.get("input_columns")))
                               if "input_columns" in preparation else _ABSENT)
            # 🔴 THE WHOLE RELATION, AND THE PERSON TAKES AWAY (owner, 2026-08-22: 「준비기는
            # 테이블 컬럼 전부」 · 「현재 선택방식으로 하되 기본을 전체 선택으로」).  A preparer
            # reads the PHYSICAL table and nothing else -- it runs before anything has been
            # prepared -- so RELATION is both the universe and now the default.  The control
            # does not change: this is a default a person NARROWS, not a constraint.
            #
            # The cost, chosen knowingly: the saved list names columns this source does not
            # read, so dropping one of them from the table stops this source too.  The
            # default is a SNAPSHOT written at save, so the guard that refuses a vanished
            # column keeps working on exactly the names the file ends up holding.
            yield Field(
                path=f"{prep_base}.input_columns", step="sources",
                label="준비기 input_columns",
                state="derived", tier=TIER_DERIVATION,
                value=list(physical), declared=declared_inputs,
                ground=Ground(
                    "preparer_inputs_from_relation",
                    f"기본값: relation {relation}의 카탈로그 컬럼 {len(physical)}개 전부",
                    (f"{PHYSICAL_CATALOG_FILENAME}:{relation}",), list(physical)),
                # 🔴 STATED, NOT MEASURED, AND `comparison` IS NOT THE LEVER FOR IT.  The
                # derived value is now the MAXIMUM a person narrows, which is neither of the
                # two things `comparison` can say (`equal` = zero freedom, `superset` = a
                # derived MINIMUM a wider declaration satisfies).  `superset` is the word
                # that already produced a false red on `input_columns` once, so it is not
                # kept here just to route the row; the row states its own disposition, as
                # `_source_fields`' `group_by` does.
                disposition="default_overridable",
                candidates=tuple(physical), universe=UNIVERSE_RELATION,
                note="기본은 물리 표 컬럼 전부 · 빼려면 x",
            )
            outputs = preparation.get("output_columns")
            names = sorted(outputs, key=str) if isinstance(outputs, Mapping) else []
            # NOT a derived value.  The relation's columns are what this field may not
            # BE; filling the field with them would declare exactly the collisions
            # `output_column_collision` refuses.
            yield Field(
                path=f"{prep_base}.output_columns", step="sources",
                label="준비기 output_columns",
                state="answered" if names else "unanswered", tier=TIER_CONSTRAINED,
                value=names, declared=names if names else _ABSENT,
                forbidden=tuple(physical),
                ground=Ground(
                    "preparer_output_collision_from_relation",
                    f"제한: relation {relation}의 컬럼 {len(physical)}개와 이름이 겹칠 수 없음",
                    (f"{PHYSICAL_CATALOG_FILENAME}:{relation}",), list(physical)),
                note="준비기가 새로 만드는 컬럼 이름. 물리 표에 있는 이름은 쓸 수 없다.",
            )
        inherited = _listed(preparation.get("inherit_virtual_join_rules"))
        # 🔴 IS THIS DECLARATION EVEN NEEDED -- ASKED BEFORE IT WAS WIRED.  Measured
        # 2026-08-21: exactly one file outside the validator mentions the key, and it does
        # not READ it -- `setup_registry` writes
        # `SourcePreparerDescriptor.accepts_verified_join_rules` at compile time and
        # nothing ever looks at the attribute again.  The validator states one rule about
        # it (`invalid_driver`: must be true when the source inherits virtual join rules).
        # So inheriting FORCES true, and not inheriting leaves a bit whose value changes
        # nothing -- a default, not a question, in both directions.
        #
        # It used to be derived only in the first case, which is why this square sat on the
        # form as a bare checkbox for all four live sources: none of them inherits a rule,
        # so none of them reached the derivation, and the operator was asked for a bit
        # nobody consumes.  The `if` is what left; the inheriting branch is unchanged.
        #
        # 🔴 AND THE STRONGER FIX IS STILL OPEN, SAID OUT LOUD.  A key nothing reads should
        # leave the grammar rather than be filled in silence; that is `setup_bundle` +
        # `setup_registry` + every config on disk, not this module, so it stays an open
        # item here instead of being absorbed into a green box.
        yield Field(
            path=f"{prep_base}.accepts_verified_join_rules", step="sources",
            label="accepts_verified_join_rules", state="derived",
            tier=TIER_DERIVATION, value=bool(inherited),
            declared=preparation.get("accepts_verified_join_rules", _ABSENT),
            ground=Ground(
                "accepts_join_rules_from_inheritance",
                f"채움: 소스 {source_id}가 join rule {len(inherited)}건 상속"
                if inherited else
                f"기본값: 소스 {source_id}가 상속하는 join rule 없음 → false",
                (f"{prep_base}.inherit_virtual_join_rules",), bool(inherited)),
        )

        # -------------------------------------------------------------------- mapper
        mapper = _mapper(source)
        base = f"bundle.sources.{source_id}.map"
        yield from _implementation_clause_fields(
            base, mapper, mappers, mapper_ids, "매퍼 구현",
            "맨 앞은 코드 없이 선언만으로 도는 구현 · " + NEW_IMPLEMENTATION_NOTE)
        # `emits` was a `derived` row here until 2026-08-21 -- set equality in BOTH
        # directions, zero degrees of freedom.  A field the screen fills and never asks is
        # still a field the file carries, so this round removed the declaration instead:
        # `MapperDescriptor.emits` is compiled from `bind.mappings.<sentence>.use` and there is
        # nothing left to show.
        binding_columns = profile_binding_columns(profile_base, profile) if profile else ()
        # 🔴 THE PREPARED FRAME, NOT THE BINDINGS (owner, 2026-08-22: 「맵퍼는 준비기 컬럼
        # 전부」).  Deriving this from `bind.mappings` was the lead's proposal and the owner
        # replaced it with the shorter rule: whatever the frame carries after preparation is
        # what the mapper is offered.  It covers in one sentence the columns a binding never
        # names and a custom mapper still reads (`__source_event_incomplete` on `lot_event`),
        # and it makes the gate the FRAME rather than the profile -- a source with no
        # mappings yet, which is what a half-built one looks like, now gets the row too.
        if prepared:
            yield Field(
                path=f"{base}.input_columns", step="sources",
                label="매퍼 input_columns", state="derived", tier=TIER_DERIVATION,
                value=list(prepared),
                declared=list(_listed(mapper.get("input_columns")))
                if "input_columns" in mapper else _ABSENT,
                ground=Ground(
                    "mapper_inputs_from_prepared_frame",
                    f"기본값: 준비 뒤 프레임 컬럼 {len(prepared)}개 전부 "
                    f"(relation {relation} + 준비기 output_columns)",
                    (f"{PHYSICAL_CATALOG_FILENAME}:{relation}",
                     f"{prep_base}.output_columns"),
                    list(prepared)),
                # Stated for the same reason as the preparer row above: the value is the
                # MAXIMUM and a person narrows it, so `comparison` has no word for it and
                # the classification is written here instead of being routed through a
                # removal probe that would answer a different question.
                disposition="default_overridable",
                # 🔴 RELATION ∪ 준비기.output_columns, WHICH THE MAPPER COULD NOT BE TOLD
                # BEFORE.  The mapper runs AFTER preparation, so a preparer-made column is
                # legal here and a physical one still is too -- the widening the move was
                # for.  Universe and default are now the same set; the universe is what a
                # person may put BACK after narrowing.
                candidates=tuple(prepared), universe=UNIVERSE_PREPARED,
                note="기본은 준비 뒤 컬럼 전부 · 빼려면 x",
            )
        unit = mapper.get("unit") if isinstance(mapper.get("unit"), Mapping) else {}
        kind = unit.get("kind")
        yield Field(
            path=f"{base}.unit.kind", step="sources", label="매퍼 단위",
            state="answered" if kind else "missing", tier=TIER_CONSTRAINED,
            value=kind, declared=kind if kind else _ABSENT,
            candidates=tuple(sorted(_MAPPER_UNITS)),
        )
        if kind == "group_by":
            group_by = list(_listed(_driver(source).get("group_by")))
            columns = list(_listed(unit.get("columns")))
            derived_inputs = sorted({column for column, _ in binding_columns})
            yield Field(
                path=f"{base}.unit.columns", step="sources",
                label="unit.columns",
                state="answered" if columns else "missing",
                tier=TIER_CONSTRAINED,
                value=columns, declared=columns if columns else _ABSENT,
                candidates=tuple(derived_inputs),
                note="소스 read.group_by와 같게 · "
                     f"{', '.join(str(key) for key in group_by) or '없음'}",
            )


def _profile_fields(bundle: Mapping[str, Any], catalog: Mapping[str, Any]
                    ) -> Iterable[Field]:
    """Every source's profile body, walked FROM the source.

    🔴 THE OWNER LOOKUP IS GONE, exactly as it went for the preparer and the mapper.  This
    function used to walk the `profiles` section and search backwards for the source that
    selected each member, then derive `profile.source` from what it found -- a field whose
    only correct value was the key of the thing that pointed at it.  A body inside a source
    has no such field and needs no such search.
    """
    sources = _section(bundle, "sources")
    vocabulary = _section(bundle, "vocabulary")
    entities = _section(bundle, "entities")
    for source_id in sorted(sources, key=str):
        source = sources[source_id]
        if not isinstance(source, Mapping):
            continue
        profile = source.get("bind")
        if not isinstance(profile, Mapping):
            continue
        base = f"bundle.sources.{source_id}.bind"
        # `packs` was a `derived` row here on the same terms as the mapper's `emits`, and
        # left the file with it on 2026-08-21.
        available = prepared_columns(bundle, catalog, source)
        sentences = _mappings(profile)
        # 🔴 THE MAP ITSELF IS A SQUARE.  An empty `mappings` is refused with
        # `invalid_profile ... must be a non-empty object keyed by sentence`, and until this
        # row existed that refusal had no field to sit on: it went to `unattached_refusals`,
        # so a source with no sentence yet showed NO red square and still would not compile.
        # The row is drawn where the form already draws one -- `renderSkeletonMap` asks
        # `branchOwnRow` for the map's own plan row, on the same line as the 「+ 매핑」
        # button that answers it.  No control is added; the refusal is given the square the
        # screen was already drawing.
        yield Field(
            path=f"{base}.mappings", step="sources", label="문장",
            state="answered" if sentences else "missing", tier=TIER_CONSTRAINED,
            value=[sentence for sentence, _ in sentences],
            declared=[sentence for sentence, _ in sentences] if sentences else _ABSENT,
            note="아래 「+ 매핑」으로 문장을 하나 이상 추가",
        )
        for sentence, mapping in sentences:
            yield from _mapping_fields(
                base, sentence, mapping, vocabulary, entities, available)


def _mapping_fields(base: str, sentence: str, mapping: Mapping[str, Any],
                    vocabulary: Mapping[str, Any], entities: Mapping[str, Any],
                    available: Sequence[str]) -> Iterable[Field]:
    """One sentence: which predicate it utters, and one row per slot that predicate forces.

    🔴 THE SLOTS ARE LAID OUT THE MOMENT A PREDICATE IS CHOSEN (owner, 2026-08-21:
    「packs 제거 후 소스에는 문장id - vocab - vocab 정의 따른 하위 항목별 binding 템플릿
    이런 형태가 되어야 함」).  Deleting `claims` without this would MOVE the burden instead
    of removing it: the operator would have to know that `has_wafer@1` wants a `slot` from
    somewhere outside the screen.  `predicate_claim` answers it from the vocabulary, so the
    form asks only what is genuinely free -- the MATERIAL for each slot.

    🔴 AND ONLY THE SLOTS IT FORCES.  A predicate whose object is `none` gets no `target`
    row, because laying every possible slot out always is how the zero-degrees-of-freedom
    boxes this project spent 2026-08-21 deleting would come back on a different screen.
    """
    mpath = f"{base}.mappings.{sentence}"
    predicate_id = mapping.get("predicate")
    predicate = (vocabulary.get(predicate_id)
                 if isinstance(predicate_id, str) else None)
    if not isinstance(predicate, Mapping):
        yield Field(
            path=f"{mpath}.predicate", step="sources", label="낱말",
            state="missing", tier=TIER_CONSTRAINED,
            value=predicate_id, declared=predicate_id,
            candidates=tuple(sorted(
                name for name, item in vocabulary.items()
                if isinstance(item, Mapping) and item.get("status") == "active")),
            note="이 문장이 말하는 낱말. 고르면 아래 역할 칸이 깔린다.",
        )
        return
    yield Field(
        path=f"{mpath}.predicate", step="sources", label="낱말",
        state="answered", tier=TIER_CONSTRAINED,
        value=predicate_id, declared=predicate_id,
        candidates=tuple(sorted(
            name for name, item in vocabulary.items()
            if isinstance(item, Mapping) and item.get("status") == "active")),
        note="retired 낱말은 후보에서 빠진다.",
    )
    roles = predicate_claim(predicate_id, predicate)["roles"]
    bind = mapping.get("bind") if isinstance(mapping.get("bind"), Mapping) else {}

    # The row set itself is derived: which roles exist is the predicate's business.
    yield Field(
        path=f"{mpath}.bind", step="sources", label="결선할 역할",
        state="derived", tier=TIER_DERIVATION,
        value=sorted(roles, key=str),
        ground=Ground(
            "bind_rows_from_predicate",
            f"채움: 낱말 {predicate_id}이 요구하는 역할 {len(roles)}개",
            (f"bundle.vocabulary.{predicate_id}",),
            sorted(roles, key=str)),
        disposition="shape",
    )
    for role_id in sorted(roles, key=str):
        role = roles[role_id]
        if not isinstance(role, Mapping):
            continue
        binding = bind.get(role_id)
        required = role.get("required") is True
        if not isinstance(binding, Mapping):
            yield Field(
                path=f"{mpath}.bind.{role_id}", step="sources",
                label=f"역할 {role_id}",
                state="missing" if required else "unanswered",
                tier=TIER_CONSTRAINED,
                candidates=tuple(role_binding_kinds(role)),
                note=f"kind={role.get('kind')}",
                refusals=({
                    "code": "missing_required_role",
                    "path": f"{mpath}.bind.{role_id}",
                    "message": f"predicate {predicate_id!r} requires role "
                               f"{role_id!r}"},) if required else (),
            )
            continue
        yield Field(
            path=f"{mpath}.bind.{role_id}.kind", step="sources",
            label=f"역할 {role_id} 결선 종류",
            state="answered" if binding.get("kind") else "missing",
            tier=TIER_CONSTRAINED, value=binding.get("kind"),
            declared=binding.get("kind"),
            candidates=tuple(role_binding_kinds(role)),
        )
        if role.get("kind") == "symbolic" and binding.get("kind") == "constant":
            yield Field(
                path=f"{mpath}.bind.{role_id}.value", step="sources",
                label=f"역할 {role_id} 상수",
                state="answered" if binding.get("value") else "missing",
                tier=TIER_CONSTRAINED, value=binding.get("value"),
                declared=binding.get("value"),
                # 🔴 ALWAYS EMPTY SINCE `packs` LEFT, so this offers no candidate today.
                # `allowed_values` could only be written at `packs.*.claims.*.roles.*`, and
                # the derivation that replaced it (`setup_bundle.predicate_claim`) emits
                # `kind` and `required` and nothing else -- measured 2026-08-22: zero
                # occurrences in the live config, the sample, or any producer in `server/`.
                # Kept rather than deleted: the day an axis writes rosters again, this is
                # where they have to reach the screen, and rebuilding it then costs more
                # than carrying a line that returns `()`.
                candidates=tuple(_listed(role.get("allowed_values"))),
            )
        if binding.get("kind") == "column":
            yield Field(
                path=f"{mpath}.bind.{role_id}.column", step="sources",
                label=f"역할 {role_id} 컬럼",
                state="answered" if binding.get("column") else "missing",
                tier=TIER_CONSTRAINED, value=binding.get("column"),
                declared=binding.get("column"),
                candidates=tuple(available), universe=UNIVERSE_PREPARED,
            )
        if binding.get("kind") == "entity":
            yield from _entity_binding_fields(
                f"{mpath}.bind.{role_id}", binding, entities, available)
    for role_id in sorted(bind, key=str):
        if role_id not in roles:
            yield Field(
                path=f"{mpath}.bind.{role_id}", step="sources",
                label=f"역할 {role_id}", state="missing", tier=TIER_DIAGNOSTIC,
                candidates=tuple(sorted(roles, key=str)),
                refusals=({
                    "code": "unknown_role", "path": f"{mpath}.bind.{role_id}",
                    "message": f"role {role_id!r} is not declared by Claim"},),
                note="Claim이 선언하지 않은 역할.",
            )


def _entity_binding_fields(path: str, binding: Mapping[str, Any],
                           entities: Mapping[str, Any], available: Sequence[str]
                           ) -> Iterable[Field]:
    entity_type = binding.get("entity_type")
    yield Field(
        path=f"{path}.entity_type", step="sources", label="엔터티 타입",
        state="answered" if entity_type else "missing", tier=TIER_CONSTRAINED,
        value=entity_type, declared=entity_type if entity_type else _ABSENT,
        candidates=tuple(sorted(entities, key=str)),
    )
    entity = entities.get(entity_type) if isinstance(entity_type, str) else None
    if not isinstance(entity, Mapping):
        return
    keys = tuple(str(name) for name in _listed(entity.get("keys")))
    if not keys:
        return
    declared_keys = binding.get("keys")
    # ① 오늘의 발단.  The validator demands SET EQUALITY with the entity's keys, so the
    # only remaining question is which column supplies each key.
    yield Field(
        path=f"{path}.keys", step="sources", label="식별키 이름",
        state="derived", tier=TIER_STRUCTURAL,
        # Set equality is the rule (`_binding_refs`), so both sides are compared sorted:
        # a differing ORDER is not a defect and must not render as a conflict.
        value=sorted(keys),
        declared=sorted(declared_keys, key=str)
        if isinstance(declared_keys, Mapping) else _ABSENT,
        ground=Ground(
            "entity_binding_keys_from_entity",
            f"채움: {entity_type}의 식별키",
            (f"bundle.entities.{entity_type}.keys",), list(keys)),
        note="각 키에 어느 컬럼인지만 아래에서 고르세요",
        disposition="shape",
    )
    for key in keys:
        child = declared_keys.get(key) if isinstance(declared_keys, Mapping) else None
        column = child.get("column") if isinstance(child, Mapping) else None
        yield Field(
            path=f"{path}.keys.{key}.column", step="sources",
            label=f"키 {key} 공급 컬럼",
            state="answered" if column else "unanswered", tier=TIER_CONSTRAINED,
            value=column, declared=column if column else _ABSENT,
            candidates=tuple(available), universe=UNIVERSE_PREPARED,
        )


def _registering_sentences(source: Any) -> tuple[tuple[str, str], ...]:
    """(sentence, subject entity type) for every sentence of this source that REGISTERS.

    🔴 DERIVED FROM THE SAME WORD THE RUNTIME KEYS ON, not from a spelling rule.  A
    sentence registers when its predicate resolves to the canonical `register`
    (`REGISTER_PREDICATE`); the config addresses it as `register@1` and the atom carries
    it unversioned, which is the split `roleframe._runtime_id` makes everywhere else.

    The entity type comes out of the subject binding, and is `""` while that binding is
    half-written.  The two answers are kept apart on purpose: whether the source registers
    at all decides that the probe is REQUIRED, and a subject nobody has bound yet must not
    turn that requirement back off -- it only leaves the candidate list short until the
    binding names something.
    """
    profile = source.get("bind") if isinstance(source, Mapping) else None
    found: list[tuple[str, str]] = []
    for sentence, mapping in _mappings(profile):
        predicate = mapping.get("predicate")
        if not isinstance(predicate, str):
            continue
        if predicate.rsplit("@", 1)[0] != REGISTER_PREDICATE:
            continue
        bind = mapping.get("bind") if isinstance(mapping.get("bind"), Mapping) else {}
        subject = bind.get(SUBJECT_ROLE) if isinstance(bind, Mapping) else None
        entity_type = subject.get("entity_type") if isinstance(subject, Mapping) else None
        found.append((sentence, entity_type if isinstance(entity_type, str) else ""))
    return tuple(found)


#: The timezone offered when the file answers nowhere at all.
#:
#: 🔴 A DEFAULT, NOT A CONSTRAINT (lead, 2026-08-21).  Both live sources say `Asia/Seoul`,
#: and two sources are a SAMPLE, not a rule -- so this is only the value that goes in when
#: there is nothing to read.  Nothing enforces it: the box beside the picker is free text
#: and no timezone list is published, because a closed list here would be this module
#: authoring a vocabulary it does not own.
_TIMEZONE_FALLBACK = "Asia/Seoul"


def _declared_timezones(bundle: Mapping[str, Any]) -> list[str]:
    """Every timezone this file's sources already answer with, sorted.

    Read from the document rather than written here, so a site that types its own once is
    offered that answer on every later source without a line of code changing.
    """
    found = []
    for source in _section(bundle, "sources").values():
        read = source.get("read") if isinstance(source, Mapping) else None
        occurred = read.get("occurred_at") if isinstance(read, Mapping) else None
        value = occurred.get("timezone") if isinstance(occurred, Mapping) else None
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
    return sorted(found)


def _source_fields(bundle: Mapping[str, Any], catalog: Mapping[str, Any]
                   ) -> Iterable[Field]:
    entities = _section(bundle, "entities")
    # The most-used answer in the file, ties broken alphabetically so two runs of the same
    # file never disagree about which chip a new source is offered.
    zones = _declared_timezones(bundle)
    timezone_default = max(zones, key=zones.count) if zones else _TIMEZONE_FALLBACK
    timezone_candidates = tuple(sorted({*zones, timezone_default}))
    for source_id in sorted(_section(bundle, "sources"), key=str):
        source = _section(bundle, "sources")[source_id]
        if not isinstance(source, Mapping):
            continue
        base = f"bundle.sources.{source_id}"
        driver = _driver(source)
        relation = source.get("relation")
        physical = relation_columns(catalog, relation)
        available = prepared_columns(bundle, catalog, source)
        yield Field(
            path=f"{base}.relation", step="sources", label="relation",
            state="answered" if relation else "missing", tier=TIER_CONSTRAINED,
            value=relation, declared=relation if relation else _ABSENT,
            candidates=tuple(sorted(catalog, key=str)),
            note=f"후보의 출처는 {PHYSICAL_CATALOG_FILENAME}. 없으면 거기서 먼저 선언한다.",
        )
        unit = driver.get("unit")
        yield Field(
            path=f"{base}.read.unit", step="sources", label="단위",
            state="answered" if unit else "missing", tier=TIER_CONSTRAINED,
            value=unit, declared=unit if unit else _ABSENT,
            candidates=tuple(sorted(_SOURCE_UNITS)),
        )
        identity = list(_listed(driver.get("identity")))
        yield Field(
            path=f"{base}.read.identity", step="sources", label="identity",
            state="answered" if identity else "missing", tier=TIER_CONSTRAINED,
            value=identity, declared=identity if identity else _ABSENT,
            candidates=tuple(available), universe=UNIVERSE_PREPARED,
        )
        if unit == "row":
            yield Field(
                path=f"{base}.read.group_by", step="sources", label="group_by",
                state="derived", tier=TIER_STRUCTURAL, value=[],
                declared=list(_listed(driver.get("group_by")))
                if "group_by" in driver else _ABSENT,
                ground=Ground(
                    "group_by_absent_for_row_unit",
                    "채움: unit=row → group_by 없음",
                    (f"{base}.read.unit",), "row"),
                note="unit=row면 이 칸 자체가 없다.",
            )
        elif unit == "group":
            group_by = list(_listed(driver.get("group_by")))
            # 🔴 A DEFAULT ONLY WHERE THE FILE SAYS NOTHING, AND THAT IS WHY IT CANNOT PAINT
            # A LEGAL DECLARATION RED.  `group_by` equals `identity` on both live sources,
            # and the validator binds them ONE WAY ONLY -- `invalid_driver: group_by columns
            # must be included in identity` -- so a strict SUBSET is legal and common.
            # Deriving unconditionally would compare the whole of `identity` against such a
            # declaration and call it a conflict, which is the `input_columns` mistake the
            # `comparison` docstring was written for.  A declared `group_by` therefore stays
            # exactly as answered as it was; only the empty box gets filled.
            #
            # 🔴 THE DISPOSITION IS STATED RATHER THAN MEASURED, and it has to be.  This row
            # only exists while the bundle REFUSES (`group unit requires at least one
            # group_by column`), so `_dispositions` is in its `unmeasured` branch -- and
            # `editableFor` hands a box to `default_overridable` and to nothing else.
            # Measured 2026-08-22 by rendering the real plan through the real view: with the
            # word, the list editor and the `identity` chip both survive; with `unmeasured`
            # they are replaced by the skeleton's bare `+ 컬럼` and the chip is gone.
            # (No probe cost: an empty `group_by` under `unit: group` cannot occur in a
            # bundle that validates, so the measured branch never sees this path.)
            filling = bool(identity) and not group_by
            yield Field(
                path=f"{base}.read.group_by", step="sources", label="group_by",
                state="derived" if filling else "answered" if group_by else "missing",
                tier=TIER_CONSTRAINED,
                value=list(identity) if filling else group_by,
                declared=group_by if group_by else _ABSENT,
                candidates=tuple(identity), universe=UNIVERSE_PREPARED,
                disposition="default_overridable" if filling else "",
                ground=Ground(
                    "group_by_default_from_identity",
                    f"기본값: identity {', '.join(str(key) for key in identity)}",
                    (f"{base}.read.identity",), list(identity)) if filling else None,
                note="후보는 identity로 제한된다.",
            )
        table = catalog.get(relation) if isinstance(relation, str) else None
        unique_keys = declared_unique_keys(table) if isinstance(table, Mapping) else ()
        # 🔴 ONE ORDERING ROW, NOT TWO.  `read.cursor.columns` stood here beside
        # `order_by` with the same default, the same candidates and the same ground, and
        # the owner answered it by pasting the box above -- 「커서 어차피 복붙할건데 왜
        # 적으라 그래?」.  The validator scored both under one predicate, so no answer to
        # one was ever a wrong answer to the other.  The cursor is now written from this
        # list (`setup_bundle._derived_cursor`) and is not a question any more.
        if unique_keys:
            shortest = min(unique_keys, key=len)
            declared = driver.get("order_by")
            yield Field(
                path=f"{base}.read.order_by", step="sources", label="order_by",
                state="derived", tier=TIER_DERIVATION, value=list(shortest),
                declared=list(_listed(declared)) if declared is not None else _ABSENT,
                ground=Ground(
                    "ordering_default_from_catalog_key",
                    f"기본값: {PHYSICAL_CATALOG_FILENAME}의 {relation} 선언 키 "
                    f"{list(shortest)}",
                    (f"{PHYSICAL_CATALOG_FILENAME}:{relation}",),
                    [list(key) for key in unique_keys]),
                comparison="superset",
                candidates=tuple(physical), universe=UNIVERSE_RELATION,
                # A note beside a box says WHAT TO DO with the box.  This one used to
                # say 「선언 키는 주장이지 실측이 아니다」 -- our design conversation,
                # printed on the operator's form, where it reads as a warning about
                # something they cannot act on.  The default is IN the boxes; the only
                # thing left to say is that it can be changed and how.
                note=f"기본 {', '.join(str(key) for key in shortest)}"
                     " · 바꾸려면 고르세요",
            )
        occurred = driver.get("occurred_at")
        occurred = occurred if isinstance(occurred, Mapping) else {}
        types = _column_types(catalog, relation)
        # `string` stands beside `datetime` here.  The operational tables keep time in
        # varchar ON PURPOSE (owner 2026-08-21: the text formats are not uniform in
        # production), and the read path now parses those spellings -- so a catalog type
        # of `string` no longer means "not a time".  Leaving it out would let a person
        # declare a column the screen will not offer, which is the same wall from the
        # other side.
        time_columns = tuple(sorted(
            name for name, kind in types.items() if kind in ("datetime", "string")))
        # The CANDIDATE SET is derived; the answer is not.  A table with no time-typed
        # column leaves `basis` as the only door, and the screen says so instead of
        # letting a person discover it through three refusals -- but it still ASKS,
        # because which basis a grouped event should read is not settled (see the note).
        answered = bool(occurred.get("column") or occurred.get("basis"))
        narrowed = bool(physical) and not time_columns
        # 🔴 AN OFFERED CANDIDATE IS A COMPLETE ANSWER OR IT IS A TRAP.  The candidates
        # named `column` or `basis` and stopped; `timezone` sits in the same record and is
        # REQUIRED, so pressing a chip produced a half-written record and two refusals
        # (`missing_field`, `blank_value`) at a path no plan row spoke for -- i.e. the
        # screen could show zero red squares and still refuse to compile, which is the
        # owner's own report (2026-08-21: 「timezone 수동으로 쳐야하고」).  Measured the
        # same evening: 16 of 16 candidates left that refusal standing.
        zone = occurred.get("timezone")
        zone = (zone.strip() if isinstance(zone, str) and zone.strip()
                else timezone_default)
        yield Field(
            path=f"{base}.read.occurred_at", step="sources", label="시각",
            state="answered" if answered else "missing", tier=TIER_CONSTRAINED,
            value=dict(occurred) if occurred else None,
            declared=dict(occurred) if occurred else _ABSENT,
            candidates=tuple(
                [{"column": name, "timezone": zone} for name in time_columns]
                + [{"basis": name, "timezone": zone}
                   for name in sorted(_OCCURRED_AT_BASES)]),
            universe=UNIVERSE_RELATION,
            ground=Ground(
                "occurred_at_candidates_from_column_types",
                (f"제한: {relation}에 시각으로 읽을 컬럼 없음 → basis만"
                 if narrowed
                 else f"후보: {relation}의 시각으로 읽을 컬럼 {len(time_columns)}개 + basis"),
                (f"{PHYSICAL_CATALOG_FILENAME}:{relation}",), list(time_columns)),
            # 🔴 A PENDING RULING IS NOT A FORM FIELD'S BUSINESS.  This said which question
            # was still open and named the task file holding it -- true, and useless to
            # somebody filling the box, who cannot act on either.  What is left is the one
            # rule that changes what they press.
            note="column · basis 중 하나만 고르세요",
        )
        # 🔴 THE SQUARE THE TIMEZONE REFUSAL LANDS ON.  Filling it from the picker above is
        # only half: the validator refuses at `…occurred_at.timezone`, and with no row at
        # that exact path both refusals fell into `unattached_refusals` -- reachable on the
        # map and on no box.  This row is also what keeps the value CHANGEABLE: the picker
        # swallows the keys it writes (`covering`), and the client's rule is that a key the
        # plan speaks for in its own right keeps its box.  Measured on the live config
        # before this existed: adding `timezone` to the candidates deleted the only input
        # for it anywhere in the form.
        declared_zone = occurred.get("timezone")
        answered_zone = isinstance(declared_zone, str) and bool(declared_zone.strip())
        yield Field(
            path=f"{base}.read.occurred_at.timezone", step="sources",
            label="시각 timezone",
            state="answered" if answered_zone else "missing", tier=TIER_CONSTRAINED,
            value=declared_zone if answered_zone else None,
            declared=declared_zone if answered_zone else _ABSENT,
            # 🔴 A SUGGESTION, NEVER A LIST TO PICK FROM.  What the file already answers
            # plus the default -- no IANA table is shipped and none is enforced, so a site
            # outside Seoul types it once and every later source is offered that answer.
            candidates=timezone_candidates,
            note="시각을 고르면 함께 채워짐 · 다르면 직접 입력",
        )
        probes = _listed(driver.get("registration_probe"))
        single_key = tuple(sorted(
            name for name, entity in entities.items()
            if isinstance(entity, Mapping) and len(_listed(entity.get("keys"))) == 1))
        # 🔴 THE SENTENCES SAY WHETHER THIS DECLARATION IS OPTIONAL, AND THE SKELETON
        # CANNOT.  `registration_probe` is `required: false` in the grammar and that is
        # right for most sources -- one that emits no `register` needs no probe.  For one
        # that DOES, it is not optional at all: `runtime_v2._filtered_event_atoms` refuses
        # the whole run with `registration_context_required`, which is why `lot_event`
        # never ran until 2026-08-21.  The refusal lands at backfill, hours and one screen
        # away from the person who filled the form and passed save.  So the condition is
        # asked here, per source, off the same `bind` the compiler reads.
        registers = _registering_sentences(source)
        # Both grounds, kept: the entity must be one this source registers (a probe for
        # anything else suppresses nothing) AND single-keyed, which is what
        # `_cross_registration_probe` refuses with `unsupported_registration_probe`.
        probe_entities = tuple(
            name for name in sorted({entity for _, entity in registers if entity})
            if name in single_key)
        if registers or probes:
            yield Field(
                path=f"{base}.read.registration_probe", step="sources",
                label="등록 탐침",
                state="answered" if probes else "missing", tier=TIER_CONSTRAINED,
                value=[dict(probe) for probe in probes if isinstance(probe, Mapping)],
                declared=list(probes) if probes else _ABSENT,
                ground=Ground(
                    "registration_probe_required_by_register_sentences",
                    f"필요: 이 소스의 register 문장 {len(registers)}개 "
                    f"({', '.join(sentence for sentence, _ in registers) or '없음'})",
                    tuple(f"{base}.bind.mappings.{sentence}"
                          for sentence, _ in registers) or (base,)),
                note="register 문장이 있으면 필수 · 없으면 백필이 통째로 거절",
            )
        for probe_index, probe in enumerate(probes):
            if not isinstance(probe, Mapping):
                continue
            ppath = f"{base}.read.registration_probe[{probe_index}]"
            yield Field(
                path=f"{ppath}.entity_type",
                step="sources", label="등록 탐침 엔터티",
                state="answered" if probe.get("entity_type") else "missing",
                tier=TIER_CONSTRAINED, value=probe.get("entity_type"),
                declared=probe.get("entity_type"),
                candidates=probe_entities,
                note="register 문장이 등록하는 엔터티 · 식별키 1개",
            )
            columns = list(_listed(probe.get("columns")))
            # 🔴 RELATION, NOT PREPARED, AND THE SAME REFUSAL SAYS SO.  The probe is asked
            # BEFORE preparation, on physical column names, while the bindings name
            # post-preparation ones -- so offering the preparer's outputs here produces
            # `unknown_column ... has no column`, which is exactly the refusal a person
            # gets today for typing the binding's spelling from memory.
            yield Field(
                path=f"{ppath}.columns", step="sources", label="등록 탐침 컬럼",
                state="answered" if columns else "missing", tier=TIER_CONSTRAINED,
                value=columns, declared=columns if columns else _ABSENT,
                candidates=tuple(physical), universe=UNIVERSE_RELATION,
                note="준비 전에 묻기 때문에 물리 표 컬럼만",
            )
            # 🔴 `list_separator` GETS NO ROW HERE, AND THE MEASUREMENT IS WHY.  It reads
            # like the obvious third row -- `waferids` is `:`-separated and probing the
            # unsplit string finds none of the wafers, the under-approximation that
            # duplicates `register`.  But a plan row REPLACES the skeleton's own control
            # for a leaf (`renderTreeLeaf` prefers it), and `renderAuthoringRow` builds no
            # control at all unless the row carries candidates -- so a candidate-less row
            # here DELETES the text box the operator types the separator into.  Measured
            # 2026-08-21 on the live `lot_event`: with the row, `INPUT.oe-field-input`
            # disappears from both probes; without it, the skeleton draws it for both.  No
            # catalog knows a separator, so there are no candidates to give, and inventing
            # a list of punctuation would be this module authoring a closed list it does
            # not own.  The plan speaks for a leaf when it has something to say about it.


# ------------------------------------------------------------ removability, measured


_PATH_STEP = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _split_path(path: str) -> list[Any]:
    """`bundle.a.b[0].c` -> ['a', 'b', 0, 'c'] (the leading `bundle.` is dropped)."""
    steps: list[Any] = []
    for name, index in _PATH_STEP.findall(path.removeprefix("bundle.")):
        steps.append(name if name else int(index))
    return steps


def _without(bundle: Mapping[str, Any], path: str) -> dict[str, Any] | None:
    """A deep copy with that one leaf gone, or None if the path does not resolve."""
    steps = _split_path(path)
    if not steps:
        return None
    document = copy.deepcopy(dict(bundle))
    cursor: Any = document
    for step in steps[:-1]:
        if isinstance(step, int):
            if not isinstance(cursor, list) or step >= len(cursor):
                return None
            cursor = cursor[step]
        else:
            if not isinstance(cursor, dict) or step not in cursor:
                return None
            cursor = cursor[step]
    last = steps[-1]
    if isinstance(last, int):
        if not isinstance(cursor, list) or last >= len(cursor):
            return None
        cursor.pop(last)
    else:
        if not isinstance(cursor, dict) or last not in cursor:
            return None
        cursor.pop(last)
    return document


def _dispositions(bundle: Mapping[str, Any], catalog: Mapping[str, Any],
                  paths: Sequence[str], base_valid: bool) -> dict[str, str]:
    """Which forced fields can actually LEAVE the file -- by deleting them and re-checking.

    🔴 MEASURED, NOT CLAIMED.  "This field is determined, so it could be removed" is a
    statement about the grammar, and the grammar is not obliged to agree: a value can be
    fully forced by another declaration and still be a REQUIRED key.  Deleting it and
    running the validator is the only way to tell those apart, and it costs one pass per
    field over a bundle small enough that the whole plan compiles in milliseconds.

    The probe is skipped when the base bundle already refuses, because a removal probe run
    against a bundle carrying unrelated errors reports the unrelated errors and would call
    every field unremovable.
    """
    if not base_valid:
        return {path: "unmeasured" for path in paths}
    out: dict[str, str] = {}
    for path in paths:
        reduced = _without(bundle, path)
        if reduced is None:
            out[path] = "shape"
            continue
        out[path] = (
            "remove_from_file"
            if not validate_bundle_errors(reduced, catalog=catalog)
            else "grammar_requires_it")
    return out


# ------------------------------------------------------------------------------- plan


def authoring_plan(bundle: Mapping[str, Any], catalog: Mapping[str, Any], *,
                   selection_prefix: str | None = None) -> dict[str, Any]:
    """The whole authoring surface: what is filled, what is missing, what is still asked.

    `bundle` may be INVALID or half-written -- that is the normal authoring state, and a
    plan that only worked on a compiled bundle would be useless exactly when it is needed.
    Every accessor here tolerates the wrong shape and simply produces fewer fields.
    """
    if not isinstance(bundle, Mapping):
        raise TypeError("bundle must be a mapping")
    fields: list[Field] = [
        *_entities_fields(bundle),
        *_vocabulary_fields(bundle),
        *_implementation_fields(bundle, catalog),
        *_profile_fields(bundle, catalog),
        *_source_fields(bundle, catalog),
    ]
    refusals = [issue.to_mapping()
                for issue in validate_bundle_errors(bundle, catalog=catalog)]
    # Owner rule: a derived value is a default a person can change, or it is force that
    # belongs out of the file. Which one each field is gets MEASURED here, not asserted.
    forced = [
        item.path for item in fields
        if item.state == "derived" and item.comparison == "equal"
        and item.disposition != "shape"
    ]
    disposition = _dispositions(bundle, catalog, forced, not refusals)
    by_path: dict[str, list[dict[str, str]]] = {}
    for issue in refusals:
        by_path.setdefault(issue["path"], []).append(issue)
    rows = []
    attached: set[str] = set()
    for item in fields:
        payload = item.to_mapping()
        if not payload["disposition"]:
            payload["disposition"] = (
                disposition.get(item.path, "")
                if item.state == "derived" and item.comparison == "equal"
                else "default_overridable" if item.state == "derived" else "")
        extra = by_path.get(item.path, ())
        if extra:
            attached.add(item.path)
            # A field states the refusal it EXPECTS, and the validator states the one it
            # produced; where those agree the operator must see one line, not two.  Keyed
            # on (code, path) because the message text is the part that may differ.
            seen = {(row["code"], row["path"]) for row in payload["refusals"]}
            payload["refusals"] = payload["refusals"] + [
                dict(row) for row in extra
                if (row["code"], row["path"]) not in seen]
        # 🔴 A DEFAULT IS FOR AN EMPTY SQUARE.  A default computed over a square somebody
        # ALREADY ANSWERED has nothing to offer and one thing to cost: `conflicts` compares
        # it with the answer and reports the answer as a fault.  Measured 2026-08-22 on
        # `lot_event.read.order_by`, where the catalog's shortest declared key derives
        # `['txn_seq']` and the file says `['event_time', 'row_id']` -- both legal
        # (`_columns_cover_declared_unique_key` is a superset test over EVERY declared key,
        # and the file's ordering covers `row_id`), and the file's is the one 1,323 atoms
        # were read in.  The row was the only red square on that source.
        #
        # 🔴 THE CLASS, NOT THE ROW.  Every `default_overridable` row is a default and none
        # of them may compute one over an answer, so the withholding is here -- at the one
        # place the disposition is known for the whole plan -- rather than as a `filling`
        # branch inside each producer.  `_source_fields`' `group_by` already carries such a
        # branch and is the proof it works; four more rows needed it and did not have it.
        #
        # 🔴 AN EMPTY VALUE THE VALIDATOR REFUSES IS NOT AN ANSWER, AND THE TEST IS THE
        # REFUSAL RATHER THAN THE EMPTINESS.  `read.order_by: []` -- what the old screen
        # seeded -- would otherwise read as "answered", withhold the default, AND still
        # carry `invalid_type: must be a list with at least one item`.  Keying on
        # emptiness alone would be wrong in the other direction: `_nonblank_list` passes
        # `allow_empty=True` for `prepare.input_columns`, `map.input_columns` and
        # `read.group_by`, so `[]` IS an answer there, and `_says_nothing`'s own docstring
        # records the same thing for a declared `false`.  So: nothing in the box AND the
        # validator objecting to this square.
        if payload["disposition"] == "default_overridable" and payload["has_declared"]:
            if _says_nothing(payload["declared"]) and payload["refusals"]:
                # The default WINS.  The square holds nothing the validator will take, so it
                # is not a rival answer and must not be scored as one -- the derivation goes
                # on filling it, and `filled_declaration` writes it at save.  The refusal
                # itself stays exactly as the validator wrote it; what stops is calling the
                # empty box a DISAGREEMENT with the value about to be written into it.
                payload["conflicts"] = False
            else:
                payload.update(state="answered", value=payload["declared"],
                               conflicts=False, ground=None, disposition="")
        # Stamped so the screen never re-derives it. The fold rule and the per-layer count
        # must answer from ONE predicate: a screen saying "3 남음" while folding one of the
        # three away is a screen where neither number is believed.
        payload["remaining"] = is_remaining(payload)
        rows.append(payload)
    if selection_prefix:
        rows = [row for row in rows if row["path"].startswith(selection_prefix)]

    counts: dict[str, dict[str, int]] = {
        step: {"derived": 0, "missing": 0, "unanswered": 0, "answered": 0}
        for step, _, _ in STEPS}
    remaining_by_step: dict[str, int] = {step: 0 for step, _, _ in STEPS}
    for row in rows:
        counts[row["step"]][row["state"]] += 1
        if is_remaining(row):
            remaining_by_step[row["step"]] += 1
    steps = []
    for step, label, sections in STEPS:
        tally = counts[step]
        declared = sum(len(_section(bundle, name)) for name in sections)
        if not declared:
            status = "empty"
        elif tally["missing"]:
            status = "blocked"
        else:
            status = "ready"
        steps.append({
            "id": step, "label": label, "sections": list(sections),
            "declared": declared, "status": status,
            "remaining": remaining_by_step[step], **tally,
        })
    force = {}
    for row in rows:
        if row["state"] == "derived" and row["disposition"]:
            force[row["disposition"]] = force.get(row["disposition"], 0) + 1
    return {
        "steps": steps,
        # 🔴 THE ONE SOURCE FOR "WHAT IS DECLARED", AND IT HAS TO COME FROM HERE.
        # The obvious client-side source is the explorer tree, and it is wrong: `/view` is
        # PAGED and filtered by the search box, so a picker reading it would offer only
        # what happens to be on screen -- silently short, and shortest exactly when the
        # operator has typed a filter. `fields` cannot answer either; it is per-field, not
        # per-declaration. So the sections are listed here, unpaged and unfiltered,
        # straight off the bundle the plan already read.
        "sections": {
            name: sorted(_section(bundle, name), key=str)
            for name in AUTHORABLE_SECTIONS.values()
        },
        "fields": rows,
        # 🔴 SAID OUT LOUD RATHER THAN ABSORBED.  `grammar_requires_it` counts fields whose
        # value is fully determined by another declaration AND that `validate_bundle`
        # still demands as a key -- measured by deleting each one.  Every such field is a
        # tier-① fix the grammar currently blocks: the screen can fill it and can point
        # at the lever, but it cannot make the question go away.  Reporting the number is
        # how that stays an open item instead of becoming 28 quiet locked boxes.
        "force_summary": force,
        "counts": {
            state: sum(step[state] for step in steps)
            for state in ("derived", "missing", "unanswered", "answered")
        },
        "refusals": refusals,
        "unattached_refusals": [
            issue for issue in refusals if issue["path"] not in attached],
        "physical_schema_file": PHYSICAL_CATALOG_FILENAME,
    }


# ------------------------------------------------------- the fill, at the moment of save


def _says_nothing(value: Any) -> bool:
    """Does the document hold nothing at this leaf?

    Absent, `null`, and the skeleton's empty containers (`[]`, `{}`, `""`) all mean "not
    answered".  `false` and `0` do NOT -- they are answers, and treating a declared `false`
    as a gap is how a fill starts overwriting decisions.  `accepts_verified_join_rules` is
    exactly that field and is `false` on all three live sources.
    """
    return value is None or (isinstance(value, (str, list, tuple, dict)) and not value)


def _fill_leaf(document: Any, steps: Sequence[Any], value: Any) -> None:
    """Write `value` at `steps`, into containers that are already there. In place.

    Two refusals to guess, both deliberate:

    * a missing intermediate container is NOT created.  The plan speaks about a leaf; it
      says nothing about which shape should hold it, and inventing one is this module
      authoring a declaration rather than completing one.
    * a leaf addressed by list INDEX is skipped.  Nothing derived addresses one today, and
      the day something does, the question "does slot 3 exist yet" is a shape question.
    """
    cursor = document
    for step in steps[:-1]:
        if isinstance(step, int):
            if not isinstance(cursor, list) or step >= len(cursor):
                return
        elif not isinstance(cursor, dict) or step not in cursor:
            return
        cursor = cursor[step]
    last = steps[-1] if steps else None
    if not isinstance(last, str) or not isinstance(cursor, dict):
        return
    if last in cursor and not _says_nothing(cursor[last]):
        return
    cursor[last] = copy.deepcopy(value)


def filled_declaration(bundle: Mapping[str, Any], catalog: Mapping[str, Any],
                       bundle_path: Sequence[Any], raw: Mapping[str, Any]
                       ) -> dict[str, Any]:
    """`raw`, with the plan's derived values written into the gaps it leaves.

    🔴 THE SCREEN SAYS 「채움」 AND THE FILE HAS TO AGREE.  A `derived` row renders its value
    and its ground, so the operator reads "this is filled in" -- and then the declaration is
    saved with the box still empty, the validator refuses `missing_field` on the very square
    that said it filled itself, and the square goes red.  Measured on the half-built
    `user_test` source, 2026-08-21: of its 7 red squares, 3 were this -- both
    `implementation_version` boxes and `read.order_by` -- so three of the seven things it
    asked a person to go and fix were things it had already answered.

    ONE PASS OVER THE PLAN, NOT ONE RULE PER FIELD.  The plan already knows which rows are
    derived, what each one derives to, and (via `disposition == "shape"`) which of them are
    not file leaves at all -- a row set like `bind.mappings.<sentence>.bind`, whose "value"
    is the list of Role names to lay out and would be nonsense in the file.  So the rule is
    the plan's own vocabulary, and a derivation added later lands in the file without a
    second author here.

    🔴 IT FILLS A GAP; IT DOES NOT OVERWRITE, AND THIS IS THE ONE PLACE IT DIFFERS FROM
    `setup_bundle._derived_cursor`.  A cursor MUST equal its `order_by` -- a watermark can
    only be expressed in the order the read ran -- so that one overwrites.  These are
    defaults the plan itself marks `default_overridable`, and overwriting them would rewrite
    a live decision: measured on `lot_event`, whose `read.order_by` is `['event_time',
    'row_id']` while the catalog's declared key derives `['txn_seq']`.  Overwriting it moves
    `source_cursor_fingerprint`, and a moved fingerprint stops a running cursor with
    `cursor_snapshot_reset_required` -- i.e. an operator saving an unrelated edit to that
    source would silently halt its backfill.

    `bundle` is the document to derive AGAINST (the active setup's), `bundle_path` is where
    `raw` lives in it (`['sources', 'user_test']`), and the return value is a new mapping --
    nothing here touches a file.
    """
    steps = [str(step) for step in bundle_path]
    out = copy.deepcopy(dict(raw))
    if not steps:
        return out
    document = copy.deepcopy(dict(bundle))
    cursor: Any = document
    for step in steps[:-1]:
        if not isinstance(cursor, dict) or not isinstance(cursor.get(step), dict):
            return out
        cursor = cursor[step]
    if not isinstance(cursor, dict):
        return out
    cursor[steps[-1]] = out
    # Not `selection_prefix`: that is a `startswith` over a dotted path, so saving
    # `user_test` would also match `user_test_2`'s rows and fill THEM into this body at the
    # same relative steps.  The trailing dot is what makes the prefix a whole declaration.
    prefix = "bundle." + ".".join(steps) + "."
    for row in authoring_plan(document, catalog)["fields"]:
        if not row["path"].startswith(prefix):
            continue
        if row["state"] != "derived" or row["disposition"] == "shape":
            continue
        # `None` is the derivation having NO ANSWER YET, not an answer of nothing: an
        # `implementation_version` whose `implementation_id` has not been chosen derives to
        # `None`, and writing that would turn `missing_field` into `invalid_version` while
        # inventing a value nobody picked.  An empty LIST is a different thing -- it is the
        # answer for `read.group_by` under `unit: row` -- so it is written.
        if row["value"] is None:
            continue
        _fill_leaf(out, _split_path(row["path"])[len(steps):], row["value"])
    return out
