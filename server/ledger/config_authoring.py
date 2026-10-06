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

from declaration_names import fold_versions

from .column_stats import declared_unique_keys
from .config_explorer import AUTHORABLE_SECTIONS, ISOLATION_ROOTS
from .implementations import (
    # Private on purpose over there and imported anyway: it is the ONE spelling of "a
    # source-specific implementation lives under this package", and `_registered_ids`
    # ranks candidates by exactly that distinction.  A second copy of the word here is
    # the hand-kept list `implementations.py` exists to have deleted.
    _IMPLEMENTATION_PACKAGE,
    implementation_choices,
    mapper_declarations,
)
from .setup_registry import relation_columns, with_source_attributes
from .setup_bundle import (
    _profile_binding_columns as _setup_bundle_profile_binding_columns,
    _MAPPER_UNITS,
    CARDINALITIES,
    EMITTABLE_VALUE_TYPES,
    LIFECYCLE_STATES,
    OBJECT_KINDS,
    _OCCURRED_AT_BASES,
    _ROLE_KINDS,
    _SCALAR_ROLE_KINDS,
    _SOURCE_UNITS,
    PHYSICAL_CATALOG_FILENAME,
    SUBJECT_ROLE,
    VALUE_TYPES,
    predicate_claim,
    public_bundle_schema,
    read_group_by,
    default_ordering_key,
    is_event_time_role,
    registering_sentences,
    role_binding_kinds,
    role_must_be_bound,
    source_defaults,
    unit_group_columns,
    validate_bundle_errors,
    with_read_defaults,
)

#: ⚰️ THE DAY THE COMMENT ABOVE PREDICTED. It read 「`setup_bundle` spells these
#: inline ... the day it becomes a constant there, the fix is one line here」 -- and on
#: 2026-09-09 it became `LIFECYCLE_STATES`, because an ENTITY and a SOURCE now carry the
#: same field and the pair was no longer the predicate's alone. One author, so a screen
#: can no longer offer a choice the validator refuses.
LIFECYCLE_STATUSES = tuple(sorted(LIFECYCLE_STATES))


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
    ("entities", "Entities", ("entities",)),
    ("vocabulary", "Predicates", ("vocabulary",)),
    ("sources", "Sources", ("sources",)),
)

#: The column universe a square offers. ⚰️ [총괄 e14416950] There were two -- RELATION and
#: PREPARED (relation + preparer outputs) -- and with the preparer gone they are one set, so
#: one name.
UNIVERSE_RELATION = "RELATION"

_UNIVERSE_NOTE = {
    UNIVERSE_RELATION: "Table columns",
}

_ABSENT = object()

#: section -> the node kind the explorer tree uses, so a ground path can be turned into
#: something CLICKABLE.  Imported rather than restated: `AUTHORABLE_SECTIONS` is already
#: the one map from kind to section and is scored against the index by a test.
_KIND_BY_SECTION = {
    section: kind for kind, section in AUTHORABLE_SECTIONS.items()}

#: The same map WIDENED TO WHAT THE LOADER MAY ISOLATE (판정 281) -- see
#: `config_explorer.ISOLATION_ROOTS` for why the two are not one map. Built from
#: `ISOLATION_ROOTS` so a section added there cannot be forgotten here; the kind is the
#: section's singular, which is the rule every entry above already follows.
_ISOLATION_KIND_BY_SECTION = {
    section: _KIND_BY_SECTION.get(section, section.rstrip("s"))
    for section in ISOLATION_ROOTS}


def _declaration_key(path: str, kinds) -> str | None:
    """`<section>.<id>...` -> `<kind>|<id>`, for whichever map of sections is asked."""
    steps = _split_path(path)
    if len(steps) < 2 or not isinstance(steps[0], str) or not isinstance(steps[1], str):
        return None
    kind = kinds.get(steps[0])
    return f"{kind}|{steps[1]}" if kind else None


def isolation_key(path: str, ) -> str | None:
    """Which declaration a problem blames, for the LOADER (판정 281).

    🔴 THE SAME QUESTION AS `ground_node_key` ASKED OF A WIDER SET, and it needs its own
    name because the two sets answer different questions. `ground_node_key` is the
    AUTHORING affordance: it decides where a screen sends a person to change a derived
    value, so it covers what that screen can edit. This one decides which declarations may
    FALL ALONE when a config is broken, and a virtual join rule qualifies for that without
    being authorable here. One map served both until 판정 281, and the cost was a broken
    join rule blaming nothing and refusing the whole bundle.
    """
    return _declaration_key(path, _ISOLATION_KIND_BY_SECTION)


def ground_node_key(path: str) -> str | None:
    """`bundle.entities.DTJob@1.keys` -> `entity|DTJob@1`, or None if not a declaration.

    🔴 THIS IS THE OVERRIDE AFFORDANCE FOR A ZERO-FREEDOM FIELD.  Owner rule: a derived
    value a person cannot change is force, and force must not be rendered as a greyed
    box.  For a field whose value is fixed by ANOTHER declaration, the lever is not on
    this field at all -- it is on that declaration.  So the screen sends the person
    there instead of showing them a control that does nothing.
    """
    return _declaration_key(path, _KIND_BY_SECTION)


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
    #: Getting this wrong paints a legal declaration red.
    comparison: str = "equal"
    #: 🔴 THIS VALUE DECIDES WHICH SQUARES EXIST OR WHAT THEY OFFER (총괄 791c0f45e 1) - the
    #: screen asks for the plan again, over the unsaved body, when such a leaf changes. Set
    #: where the plan reads the value to lay out other rows, so the screen names no path.
    reshapes: bool = False
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
            "reshapes": self.reshapes,
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

#: 🔴 [S-241, 판정 407] THE FORM'S NODE VOCABULARY, WRITTEN DOWN. It had no author: the
#: conformance test derived 「what a form can draw」 by WALKING this ledger skeleton, so the
#: vocabulary was 「whatever this document happens to use today」. That answers 「is this kind
#: known」 with 「did somebody already use it」 - which makes adding a kind impossible without
#: first using it somewhere, and makes DELETING the last use of one silently narrow the
#: language.
#:
#: ⚠️ `oneOf` IS THE ONE THIS ROUND ADDS, and the ledger skeleton does not use it. The
#: chain grammar has two 「pick one」 axes (`derive` of three kinds, `into` of two) and the
#: vocabulary could not say so - `hint: choice` picks a VALUE, not a SHAPE. A form drawing
#: that by hand would be a second author of the grammar.
#: `either` (총괄 7255b4918 ④): one value of several shapes told apart by the value's own form -
#: a text for a leaf, an object for a record (`{of: [<node>, ...]}`). An entity binding's type
#: is a declared name or `{kind: column, column}`; `oneOf` keys its branches by a name the
#: value carries, and a name has no key to carry.
SKELETON_NODE_KINDS = ("record", "map", "leaf", "oneOf", "either")


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

    The class, not the case.  `accepts_verified_join_rules` is the one that showed that day
    (⚰️ it left with `prepare`, setup_version 6); the skeleton had two required flags
    (`virtual_joins.*.enabled` is the other -- the
    third, `packs.*.claims.*.roles.*.required`, left with its section on 2026-08-21), and
    the hint is READ, so a third is covered the day it is declared.  ⚰️ [판정 484]
    A THIRD WAS DECLARED ON 2026-09-17 (`virtual_joins.*.materialize`) AND THE COVER WAS
    WRONG. The prediction had the mechanism right and the result wrong: the hint WAS read,
    the flag WAS seeded, and `False` was the wrong answer because 판정 446 had collapsed
    that field's domain to one value, so the seed produced a join the validator refuses.
    What a required flag is seeded with is settled ABOVE, by `const`.  `entities.*.allow_null` is `required: false` and stays absent --
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

    So the gate is ASKED (`_gate`), never listed.  `when` appears across the skeleton and
    names several kinds; a set of kinds written here would be a second author for
    the grammar and would go stale the first time the skeleton changes its mind -- silently,
    which is the failure this module keeps removing.  The gate is read against the record as
    it is being seeded, so an ungated required container (`qualifiers`, the complaint this
    function exists for) still lands exactly as before.
    """
    shape = _deref(node, defs, seen)
    if not isinstance(shape, Mapping):
        return ""
    # 🔴 [판정 484] A FIELD WITH ONE LEGAL VALUE IS NOT A QUESTION, SO IT IS NOT ASKED -
    # it is STAMPED. `materialize` is the case that forced this: 판정 446 retired the only
    # other spelling, so `true` is the whole of its domain, and seeding a required flag
    # `False` (right for a two-value flag, see the note above) made every form-born join a
    # declaration the validator refuses. The form grew the box 481 asked for and still
    # produced something rejected - the same state, through a different door.
    #
    # ⛔ THE SEED IS NOT HARDCODED TO `true` HERE. That would put a domain word in the
    # authoring engine and make the next such field a second edit. The SKELETON says what
    # the one legal value is, the way it says everything else about the form.
    #
    # ⚠️ This stamps the DEFAULT. Someone who deliberately clears it still meets the
    # validator's refusal, by name and with the two repairs in it - that is an informed
    # refusal of a deliberate act, not a trap sprung on a default. Drawing a `const` leaf
    # as settled rather than as a live checkbox is the client's half and is routed.
    if "const" in shape:
        return shape["const"]
    kind = shape.get("kind")
    if kind == "map":
        return [] if shape.get("keyed_by") == "index" else {}
    if kind == "record":
        seeded: dict[str, Any] = {}
        for field in shape.get("fields") or []:
            if field.get("required") is not True:
                continue
            if _gate(field, seeded) is not True:
                continue
            child = _deref(field.get("node"), defs, seen)
            if not isinstance(child, Mapping):
                continue
            if child.get("kind") in ("leaf", "either") and child.get("hint") != "flag":
                continue                 # an `either` starts unchosen, as a leaf does
            seeded[field["key"]] = empty_value(field.get("node"), defs, seen)
        return seeded
    return False if shape.get("hint") == "flag" else ""


def _gate(field: Mapping[str, Any], record: Mapping[str, Any]) -> bool | None:
    """What a field's `when` says of `record`: True - it applies, False - the record chose
    otherwise, None - the record has not chosen yet. A field with no `when` applies."""
    gate = field.get("when")
    if not isinstance(gate, Mapping):
        return True
    chosen = record.get(gate.get("field")) if isinstance(record, Mapping) else None
    if _says_nothing(chosen):
        return None
    return chosen == gate.get("is")


def _skeleton_node(doc: Mapping[str, Any], steps: Sequence[Any]) -> Any:
    """The skeleton node for the document path `steps` (a map member is any name)."""
    node = doc.get("root", {})
    for step in steps:
        node = _deref(node, doc.get("defs", {}), frozenset())
        if not isinstance(node, Mapping):
            return None
        if node.get("kind") == "record":
            field = next((item for item in node.get("fields") or []
                          if item.get("key") == step), None)
            node = field.get("node") if field else None
        elif node.get("kind") == "map":
            node = node.get("of")
        else:
            return None
    return node


def empty_declaration(section: str) -> dict[str, Any]:
    """What a brand-new declaration of `section` starts as, per the skeleton."""
    doc = skeleton()
    node = _skeleton_node(doc, (section, "*"))
    if not isinstance(_deref(node, doc.get("defs", {}), frozenset()), Mapping):
        return {}
    value = empty_value(node, doc.get("defs", {}))
    return value if isinstance(value, dict) else {}


def _drop_switched_off(value: Any, node: Any, defs: Mapping[str, Any], path: str,
                       dropped: list) -> None:
    """Remove, in place, every field of `value` whose `when` the record chose otherwise
    (총괄 b30fbd38c ㄱ) - `{kind: constant, column: ""}` left by a switch from column. Each
    goes into `dropped` as `{path, value}`. A field with no `when`, or whose record has not
    chosen yet, is not touched."""
    shape = _deref(node, defs, frozenset())
    if not isinstance(shape, Mapping):
        return
    if shape.get("kind") == "record" and isinstance(value, dict):
        for field in shape.get("fields") or []:
            key = field.get("key")
            if key not in value:
                continue
            if _gate(field, value) is False:
                dropped.append({"path": "%s.%s" % (path, key), "value": value.pop(key)})
            else:
                _drop_switched_off(value[key], field.get("node"), defs,
                                   "%s.%s" % (path, key), dropped)
    elif shape.get("kind") == "map":
        members = (value.items() if isinstance(value, dict)
                   else enumerate(value) if isinstance(value, list) else ())
        for name, member in members:
            _drop_switched_off(member, shape.get("of"), defs, "%s.%s" % (path, name), dropped)


def closed_lists(sources: Any = None) -> dict[str, Any]:
    """Every closed list the authoring screen may offer, from the code that enforces it.

    The screen renders what this returns and owns no copy.  A list literal in the UI is
    a second author for a value whose first author is a validator, and the two diverge in
    silence on the day a declaration is added -- which is the same failure mode as the
    `tables` section that was removed from the ledger config for duplicating the catalog.

    🔴 `sources` IS THE ONE ARGUMENT, AND IT IS OPTIONAL BECAUSE ONE ENTRY HERE IS COUNTED
    RATHER THAN FIXED.  Every other list above is a property of the CODE and is the same
    answer in every deployment.  `implementation_choices` is a property of THIS
    DEPLOYMENT'S DECLARATION -- which implementation its own sources already use most --
    so it needs the declaration, and a caller that has none (a skeleton conformance check,
    a screen served while the config is unreadable) gets the options with no default,
    which is the honest answer rather than a guessed one.
    """
    schema = public_bundle_schema()
    # ONE call, read here and projected twice below. The strings are what a `choice` leaf
    # can draw (`closed_list.js` keeps only strings); the block beside them carries the
    # version and the counted default, which a list of members cannot hold. Both come from
    # this one value, so there is no second author to diverge from.
    implementations = implementation_choices(sources)
    return {
        **schema,
        "lifecycle_status": list(LIFECYCLE_STATUSES),
        # ⛔ THE FORM OFFERS WHAT THE EMITTER CAN HONOUR, NOT WHAT THE GRAMMAR PARSES
        # (판정 178). Offering `string` while the compiler pins a value to a quantity
        # is the screen recommending a refusal.
        "value_type": sorted(EMITTABLE_VALUE_TYPES),
        "cardinality": sorted(CARDINALITIES),
        "object_kind": sorted(OBJECT_KINDS),
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
        # ⚰️ `versioned` retired with the `@N` it answered for (총괄 4eb1fe98f): no section
        # carries a version, so the screen names what it creates as typed.
        "authorable_kinds": [
            {"id": kind, "section": section}
            for kind, section in sorted(AUTHORABLE_SECTIONS.items())
        ],
        # 🔴 THE NAME THE OPERATOR CANNOT INVENT, FROM THE REGISTRY THAT ENFORCES IT.
        # The `implementation_id` square was free text, so the only way to reach
        # `declarative-role` was to already know it -- and `untrusted_implementation` at
        # compile time is where a typo showed up.
        "map_implementation": [
            option["id"] for option in implementations["map"]["options"]],
        # ⚠️ THE DEFAULT IS A STARTING VALUE AND IS PUBLISHED, NOT APPLIED. Nothing here
        # writes it into a document: a screen that fills a square the file does not hold
        # edits somebody's config by drawing it. `counts` rides along so a reader can see
        # what the default was counted from instead of trusting the word.
        "implementations": implementations,
        "tiers": [
            {"id": TIER_STRUCTURAL, "label": "Structural"},
            {"id": TIER_DERIVATION, "label": "Derived"},
            {"id": TIER_CONSTRAINED, "label": "Constrained"},
            {"id": TIER_DIAGNOSTIC, "label": "Diagnostic"},
        ],
    }


# --------------------------------------------------------------------------- universes


def _column_types(catalog: Mapping[str, Any], relation: Any) -> Mapping[str, str]:
    table = catalog.get(relation) if isinstance(relation, str) else None
    columns = table.get("columns") if isinstance(table, Mapping) else None
    return columns if isinstance(columns, Mapping) else {}


def _driver(source: Any) -> Mapping[str, Any]:
    """The source's `read` clause.  Named for the plan it compiles into, not the key.

    `driver` split into `read`/`map` in the FILE on 2026-08-21; `SourceDriverPlan`
    did not, so this reader keeps the compiled word and changes only which key it opens.
    """
    driver = source.get("read") if isinstance(source, Mapping) else None
    return driver if isinstance(driver, Mapping) else {}


def _driver_relation(source: Any) -> Any:
    return source.get("relation") if isinstance(source, Mapping) else None


def _mapper(source: Any) -> Mapping[str, Any]:
    mapper = source.get("map") if isinstance(source, Mapping) else None
    return mapper if isinstance(mapper, Mapping) else {}


#: 🔴 ONE IMPLEMENTATION (S-196, 판정 306-b 되돌림). This module carried its own copy of the
#: traversal and `setup_bundle` carried another — two answers to 「which columns do this
#: profile's bindings name」, measured identical on all 15 live sources and one edit away from
#: diverging. The validator's is now the only one, made tolerant of a half-built profile
#: because THIS caller needs that and the validator never sees one.
#:
#: ⚠️ AN ASSIGNMENT, so it is the same function object — the idiom `main.py` uses for
#: `reload_local_process_cache`, and the reason callers by name keep resolving.
profile_binding_columns = _setup_bundle_profile_binding_columns


# ------------------------------------------------------------------------- derivations


def _entities_fields(bundle: Mapping[str, Any]) -> Iterable[Field]:
    for entity_id in sorted(_section(bundle, "entities"), key=str):
        entity = _section(bundle, "entities")[entity_id]
        keys = _listed(entity.get("keys")) if isinstance(entity, Mapping) else ()
        yield Field(
            path=f"bundle.entities.{entity_id}.keys",
            step="entities", label="Identity keys",
            state="answered" if keys else "missing",
            tier=TIER_CONSTRAINED,
            value=list(keys), declared=list(keys) if keys else _ABSENT,
            note="These names set the keys of every entity binding that follows.",
        )
        # 🔴 ONLY WHERE THE TYPE DECLARES ONE.  `attributes` is optional on an entity, so
        # a row drawn unconditionally would put a square on every type in every declaration
        # that has never used the feature, and the skeleton already offers the box.  What
        # the plan is needed for is the STATE and the refusal: `invalid_type` and
        # `duplicate_id` are written at exactly this path (`setup_bundle._validate_entities`)
        # and until now had no field to land on.
        if not isinstance(entity, Mapping) or "attributes" not in entity:
            continue
        names = _listed(entity.get("attributes"))
        yield Field(
            path=f"bundle.entities.{entity_id}.attributes",
            step="entities", label="Attributes",
            state="answered" if names else "missing",
            tier=TIER_CONSTRAINED,
            value=list(names), declared=list(names) if names else _ABSENT,
            note="These names set the attribute binding squares of each source.",
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
            path=f"{base}.subjects", step="vocabulary", label="Subject types",
            state="answered" if subjects else "missing", tier=TIER_CONSTRAINED,
            value=list(subjects), declared=list(subjects) if subjects else _ABSENT,
            candidates=tuple(entities),
        )
        obj = predicate.get("object")
        obj = obj if isinstance(obj, Mapping) else {}
        kind = obj.get("kind")
        yield Field(
            path=f"{base}.object.kind", step="vocabulary", label="Object kind",
            state="answered" if kind else "missing", tier=TIER_CONSTRAINED,
            value=kind, declared=kind if kind else _ABSENT,
            candidates=tuple(sorted(OBJECT_KINDS)),
        )
        if kind == "entity_ref":
            types = _listed(obj.get("types"))
            yield Field(
                path=f"{base}.object.types", step="vocabulary", label="Object entities",
                state="answered" if types else "missing", tier=TIER_CONSTRAINED,
                value=list(types), declared=list(types) if types else _ABSENT,
                candidates=tuple(entities),
                note="Only when the object kind is entity_ref.",
            )


#: The one line the candidate list needs beside it.  A name that is not on the list yet is
#: NOT a wall: `/admin/scripts/code` reads and writes Python under `mappers/`, and
#: `implementations._descendants()` picks a newly written class up on the next start.
NEW_IMPLEMENTATION_NOTE = (
    "New implementation: write mappers/ledger_v2_*.py in /admin/scripts/code · listed after a server restart")


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
    picked the number: measured 2026-08-21, all 3 mappers register exactly one version
    each.  The old form drew a bare number box beside a bare text box,
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
        note=note, reshapes=True,
    )
    versions = _registered_versions(declarations, identifier)
    yield Field(
        path=f"{base}.implementation_version", step="sources",
        label=f"{label} version", state="derived", tier=TIER_STRUCTURAL,
        value=versions[-1] if versions else None,
        declared=clause.get("implementation_version", _ABSENT) if versions else _ABSENT,
        ground=Ground(
            "implementation_version_from_registered_id",
            (f"Filled: registered {identifier}@{versions[-1]}"
             + (f" · {len(versions)} registered versions of this name" if len(versions) > 1 else "")
             ) if versions else "Filled: picking implementation_id picks the version",
            (f"{base}.implementation_id",), versions[-1] if versions else None),
    )


def _implementation_fields(bundle: Mapping[str, Any], catalog: Mapping[str, Any]
                           ) -> Iterable[Field]:
    """The mapper clause of every source, walked FROM the source.

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
    mappers = mapper_declarations()
    mapper_ids = _registered_ids(mappers)
    for source_id in sorted(sources, key=str):
        source = sources[source_id]
        if not isinstance(source, Mapping):
            continue
        profile = source.get("bind") if isinstance(source.get("bind"), Mapping) else None
        profile_base = f"bundle.sources.{source_id}.bind"
        # -------------------------------------------------------------------- mapper
        mapper = _mapper(source)
        base = f"bundle.sources.{source_id}.map"
        yield from _implementation_clause_fields(
            base, mapper, mappers, mapper_ids, "Mapper implementation",
            "The first one runs on the declaration alone, with no code · " + NEW_IMPLEMENTATION_NOTE)
        # `emits` was a `derived` row here until 2026-08-21 -- set equality in BOTH
        # directions, zero degrees of freedom.  A field the screen fills and never asks is
        # still a field the file carries, so this round removed the declaration instead:
        # `MapperDescriptor.emits` is compiled from `bind.mappings.<sentence>.use` and there is
        # nothing left to show.
        binding_columns = profile_binding_columns(profile_base, profile) if profile else ()
        unit = mapper.get("unit") if isinstance(mapper.get("unit"), Mapping) else {}
        kind = unit.get("kind")
        # A unit the file leaves out is the loader's (`source_defaults`), shown as the read cells
        # show theirs - it was a red square the loader then filled (총괄 04cecc30f).
        filled_unit = (source_defaults(source, catalog).get("map") or {}).get("unit")
        yield Field(
            path=f"{base}.unit.kind", step="sources", label="Mapper unit",
            tier=TIER_CONSTRAINED, declared=kind if kind else _ABSENT,
            candidates=tuple(sorted(_MAPPER_UNITS)), reshapes=True,
            **_answer_or_default(kind, filled_unit.get("kind")
                                 if isinstance(filled_unit, Mapping) else None, base),
        )
        if kind == "group_by":
            group_by = list(_listed(read_group_by(_driver(source))))
            # 🔴 THE SAME FUNCTION THE DERIVATION USES (판정 306-b). Reading `unit` here
            # too would be a second reader, and the two would disagree about whether a
            # column is required to exist.
            columns = unit_group_columns(mapper)
            derived_inputs = sorted({column for column, _ in binding_columns})
            yield Field(
                path=f"{base}.unit.columns", step="sources",
                label="unit.columns",
                state="answered" if columns else "missing",
                tier=TIER_CONSTRAINED,
                value=columns, declared=columns if columns else _ABSENT,
                candidates=tuple(derived_inputs),
                note="Same as the source's read.group_by · "
                     f"{', '.join(str(key) for key in group_by) or 'none'}",
            )


def _profile_fields(bundle: Mapping[str, Any], catalog: Mapping[str, Any]
                    ) -> Iterable[Field]:
    """Every source's profile body, walked FROM the source.

    🔴 THE OWNER LOOKUP IS GONE, exactly as it went for the mapper.  This
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
        available = relation_columns(catalog, _driver_relation(source))
        # 🔴 `bind.entities` IS A SIBLING OF `bind.mappings` and gets squares the same
        # way -- one per attribute the type declares -- so a refusal written at
        # `….attributes.<name>` lands on a row instead of in `unattached_refusals`.
        bound_entities = profile.get("entities")
        for entity_type in sorted(
                bound_entities if isinstance(bound_entities, Mapping) else {}, key=str):
            item = bound_entities[entity_type]
            declared = entities.get(entity_type)
            yield from _attribute_binding_fields(
                f"{base}.entities.{entity_type}", str(entity_type),
                _listed(declared.get("attributes"))
                if isinstance(declared, Mapping) else (),
                item.get("attributes") if isinstance(item, Mapping) else None)
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
            path=f"{base}.mappings", step="sources", label="Sentences",
            state="answered" if sentences else "missing", tier=TIER_CONSTRAINED,
            value=[sentence for sentence, _ in sentences],
            declared=[sentence for sentence, _ in sentences] if sentences else _ABSENT,
            note="Add one or more sentences with + Mapping below",
        )
        # 🔴 판정 179 ⓑ. The `occurred_at` role's binding is IGNORED by the compiler -- always, not
        # only where a basis is declared (`roleframe`, ruled 2026-08-23: the instant comes
        # from the preparation boundary, and re-reading the cell would disagree with the
        # event id minted from that same value). Where the source declares a BASIS the
        # dead cell is also visible in the declaration, so that is where the form stops
        # ASKING -- it shows the row as decided elsewhere rather than as a box.
        read = source.get("read") if isinstance(source.get("read"), Mapping) else {}
        occurred = read.get("occurred_at")
        time_basis = (occurred.get("basis")
                      if isinstance(occurred, Mapping) else None)
        for sentence, mapping in sentences:
            yield from _mapping_fields(
                base, sentence, mapping, vocabulary, entities, available,
                time_basis=time_basis, source_id=source_id)
            yield from _inherited_attribute_fields(base, sentence, mapping, bound_entities)


def _mapping_fields(base: str, sentence: str, mapping: Mapping[str, Any],
                    vocabulary: Mapping[str, Any], entities: Mapping[str, Any],
                    available: Sequence[str], *, time_basis: Any = None,
                    source_id: str = "") -> Iterable[Field]:
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
            path=f"{mpath}.predicate", step="sources", label="Predicate",
            state="missing", tier=TIER_CONSTRAINED,
            value=predicate_id, declared=predicate_id,
            candidates=tuple(sorted(
                name for name, item in vocabulary.items()
                if isinstance(item, Mapping) and item.get("status") == "active")),
            note="The predicate this sentence states. Picking one lays out the role squares below.",
            reshapes=True,
        )
        return
    yield Field(
        path=f"{mpath}.predicate", step="sources", label="Predicate",
        state="answered", tier=TIER_CONSTRAINED,
        value=predicate_id, declared=predicate_id,
        candidates=tuple(sorted(
            name for name, item in vocabulary.items()
            if isinstance(item, Mapping) and item.get("status") == "active")),
        note="Retired predicates are not candidates.",
        reshapes=True,
    )
    # The screen lays out one row per slot the predicate forces, and since S-52 an
    # object-less predicate forces one per attribute its subject types declare - so the
    # author sees the boxes to bind them in. `entities` is already this function's
    # argument; without passing it the form would silently offer fewer rows than the
    # compiler accepts.
    roles = predicate_claim(predicate_id, predicate, entities)["roles"]
    bind = mapping.get("bind") if isinstance(mapping.get("bind"), Mapping) else {}

    # The row set itself is derived: which roles exist is the predicate's business.
    yield Field(
        path=f"{mpath}.bind", step="sources", label="Roles to bind",
        state="derived", tier=TIER_DERIVATION,
        value=sorted(roles, key=str),
        ground=Ground(
            "bind_rows_from_predicate",
            f"Filled: the {len(roles)} roles predicate {predicate_id} requires",
            (f"bundle.vocabulary.{predicate_id}",),
            sorted(roles, key=str)),
        disposition="shape",
    )
    for role_id in sorted(roles, key=str):
        role = roles[role_id]
        if not isinstance(role, Mapping):
            continue
        if time_basis and is_event_time_role(role_id):
            # ⚠️ SHOWN, NOT HIDDEN. Dropping the row would make a declaration that
            # already carries a column here lose its square with no explanation -- and an
            # author who wrote `event_time` there deserves to be told it decides nothing,
            # not to watch it vanish. `derived` is this form's word for 「answered
            # elsewhere」, so the row stops being a question without stopping being
            # visible.
            declared = bind.get(role_id)
            declared_cell = (declared.get("column")
                             if isinstance(declared, Mapping) else None)
            yield Field(
                path=f"{mpath}.bind.{role_id}", step="sources",
                label=f"Role {role_id}", state="derived", tier=TIER_DERIVATION,
                value=time_basis,
                ground=Ground(
                    "time_from_source_basis",
                    f"Filled: this source's time is set by "
                    f"read.occurred_at.basis={time_basis!r}",
                    (f"bundle.sources.{source_id}.read.occurred_at",),
                    time_basis),
                disposition="shape",
                note=(f"This square is not read"
                      + (f" - the {declared_cell!r} written here is ignored too"
                         if declared_cell else "")),
            )
            continue
        binding = bind.get(role_id)
        required = role_must_be_bound(role_id, role)
        if not isinstance(binding, Mapping):
            yield Field(
                path=f"{mpath}.bind.{role_id}", step="sources",
                label=f"Role {role_id}",
                state="missing" if required else "unanswered",
                tier=TIER_CONSTRAINED,
                candidates=tuple(role_binding_kinds(role)),
                note=f"kind={role.get('kind')}", reshapes=True,
                # 총괄 04cecc30f ②: an unbound event time is a not-an-event edge (`role_must_be_bound`).
                ground=(Ground("not_an_event", "Not an event",
                               (f"bundle.vocabulary.{predicate_id}",))
                        if is_event_time_role(role_id) else None),
                refusals=({
                    "code": "missing_required_role",
                    "path": f"{mpath}.bind.{role_id}",
                    "message": f"predicate {predicate_id!r} requires role "
                               f"{role_id!r}"},) if required else (),
            )
            continue
        yield Field(
            path=f"{mpath}.bind.{role_id}.kind", step="sources",
            label=f"Role {role_id} binding kind",
            state="answered" if binding.get("kind") else "missing",
            tier=TIER_CONSTRAINED, value=binding.get("kind"),
            declared=binding.get("kind"),
            candidates=tuple(role_binding_kinds(role)), reshapes=True,
        )
        if role.get("kind") == "symbolic" and binding.get("kind") == "constant":
            yield Field(
                path=f"{mpath}.bind.{role_id}.value", step="sources",
                label=f"Role {role_id} constant",
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
                label=f"Role {role_id} column",
                state="answered" if binding.get("column") else "missing",
                tier=TIER_CONSTRAINED, value=binding.get("column"),
                declared=binding.get("column"),
                candidates=tuple(available), universe=UNIVERSE_RELATION,
            )
        if binding.get("kind") == "entity":
            yield from _entity_binding_fields(
                f"{mpath}.bind.{role_id}", binding, entities, available)
    for role_id in sorted(bind, key=str):
        if role_id not in roles:
            yield Field(
                path=f"{mpath}.bind.{role_id}", step="sources",
                label=f"Role {role_id}", state="missing", tier=TIER_DIAGNOSTIC,
                candidates=tuple(sorted(roles, key=str)),
                refusals=({
                    "code": "unknown_role", "path": f"{mpath}.bind.{role_id}",
                    "message": f"role {role_id!r} is not declared by Claim"},),
                note="A role Claim does not declare.",
            )


def _inherited_attribute_fields(base: str, sentence: str, mapping: Any,
                                by_type: Any) -> Iterable[Field]:
    """One read-only row per role that inherits the source's attributes (총괄 12cc7dd1f ①).

    🔴 THE RULE IS THE COMPILER'S, CALLED - NOT RESTATED. `with_source_attributes` is what
    translation binds; a role it changed inherits, and its value is what translation uses.
    `shape`, so the fill never writes it into the role - a role that carries attributes
    OVERRIDES the source's, and a copy there would stop following the source."""
    bind = mapping.get("bind") if isinstance(mapping, Mapping) else None
    if not isinstance(bind, Mapping) or not isinstance(by_type, Mapping):
        return
    compiled = with_source_attributes(bind, by_type)
    for role_id in sorted(bind, key=str):
        if compiled.get(role_id) == bind.get(role_id):
            continue
        entity_type = bind[role_id].get("entity_type")
        inherited = compiled[role_id].get("attributes")
        yield Field(
            path=f"{base}.mappings.{sentence}.bind.{role_id}.attributes", step="sources",
            label="Attributes (inherited)", state="derived", tier=TIER_STRUCTURAL,
            value=inherited,
            ground=Ground(
                "inherited_from_source",
                f"Inherited: this source's attributes of {entity_type}",
                (f"{base}.entities.{entity_type}.attributes",), inherited),
            disposition="shape",
        )


def _entity_binding_fields(path: str, binding: Mapping[str, Any],
                           entities: Mapping[str, Any], available: Sequence[str]
                           ) -> Iterable[Field]:
    entity_type = binding.get("entity_type")
    yield Field(
        path=f"{path}.entity_type", step="sources", label="Entity type",
        state="answered" if entity_type else "missing", tier=TIER_CONSTRAINED,
        value=entity_type, declared=entity_type if entity_type else _ABSENT,
        candidates=tuple(sorted(entities, key=str)), reshapes=True,
    )
    entity = entities.get(entity_type) if isinstance(entity_type, str) else None
    if not isinstance(entity, Mapping):
        return
    keys = tuple(str(name) for name in _listed(entity.get("keys")))
    # 🔴 THE OVERRIDE, DRAWN ONLY WHERE IT IS ALREADY USED.  A source binds an attribute
    # at `bind.entities`; this address exists for the one case that cannot express -- one
    # sentence using one type in two roles -- so laying its squares out on every entity
    # binding would advertise the second-best answer as the ordinary one, and a type used by
    # K sentences would be offered K places to disagree.
    if isinstance(binding.get("attributes"), Mapping):
        yield from _attribute_binding_fields(
            path, str(entity_type), _listed(entity.get("attributes")),
            binding.get("attributes"))
    if not keys:
        return
    declared_keys = binding.get("keys")
    # ① 오늘의 발단.  The validator demands SET EQUALITY with the entity's keys, so the
    # only remaining question is which column supplies each key.
    yield Field(
        path=f"{path}.keys", step="sources", label="Identity key names",
        state="derived", tier=TIER_STRUCTURAL,
        # Set equality is the rule (`_binding_refs`), so both sides are compared sorted:
        # a differing ORDER is not a defect and must not render as a conflict.
        value=sorted(keys),
        declared=sorted(declared_keys, key=str)
        if isinstance(declared_keys, Mapping) else _ABSENT,
        ground=Ground(
            "entity_binding_keys_from_entity",
            f"Filled: the identity keys of {entity_type}",
            (f"bundle.entities.{entity_type}.keys",), list(keys)),
        note="Pick only which column feeds each key below",
        disposition="shape",
    )
    for key in keys:
        child = declared_keys.get(key) if isinstance(declared_keys, Mapping) else None
        column = child.get("column") if isinstance(child, Mapping) else None
        yield Field(
            path=f"{path}.keys.{key}.column", step="sources",
            label=f"Key {key} column",
            state="answered" if column else "unanswered", tier=TIER_CONSTRAINED,
            value=column, declared=column if column else _ABSENT,
            candidates=tuple(available), universe=UNIVERSE_RELATION,
        )


def _attribute_binding_fields(path: str, entity_type: str, declared: Sequence[Any],
                              bound: Any) -> Iterable[Field]:
    """The attribute squares of ONE entity binding -- source level and role level alike.

    🔴 ONE FUNCTION FOR TWO ADDRESSES.  `bind.entities.<type>.attributes` is where a
    source binds an attribute once, and `…bind.<role>.attributes` is the override for the
    one case that address cannot express (one sentence using one type in two roles).  Two
    copies would let the levels draw different boxes for the same question, and the walk's
    `attribute_conflicts` would then be counting a disagreement this screen created.

    🔴 THE ROW IS THE BINDING, NOT THE COLUMN INSIDE IT, and the refusals decide that.
    `unknown_entity_attribute` and `invalid_binding` are both written at
    `….attributes.<name>` (`setup_bundle._bind_entities_refs` / `_validate_bind_entities`),
    so a plan that addressed `….attributes.<name>.column` -- the shape the identity keys
    use -- would leave every one of them in `unattached_refusals`: refused on save, with no
    red square to go to.  No candidate list rides here for the same reason: `editableFor`
    turns candidates into a control that writes at `row.path`, and a column name written
    there is a string where the grammar holds a binding record.

    The shape row is what makes the form draw an UNBOUND one.  `renderSkeletonMap` asks
    `plannedMembers`, which reads a `derived` row with `disposition="shape"` and takes its
    value as the member list; without it a name-keyed map shows only what the document
    already holds, so an attribute nobody has bound yet has no box to bind it in.
    """
    names = sorted(str(name) for name in declared)
    held = bound if isinstance(bound, Mapping) else {}
    if names:
        yield Field(
            path=f"{path}.attributes", step="sources", label="Attributes",
            state="derived", tier=TIER_STRUCTURAL,
            value=names,
            ground=Ground(
                "entity_binding_attributes_from_entity",
                f"Filled: the attributes of {entity_type}",
                (f"bundle.entities.{entity_type}.attributes",), names),
            disposition="shape",
        )
    # A name the type never declared is drawn too: that is precisely where
    # `unknown_entity_attribute` is written, and a refusal on a row nobody renders is the
    # defect this function exists to remove.
    for name in sorted({*names, *(str(key) for key in held)}, key=str):
        yield Field(
            path=f"{path}.attributes.{name}", step="sources",
            label=f"Attribute {name}",
            state="answered" if name in held else "unanswered",
            tier=TIER_CONSTRAINED,
            value=held.get(name),
            declared=held[name] if name in held else _ABSENT,
        )


def _registering_sentences(source: Any) -> tuple[tuple[str, str], ...]:
    """(sentence, subject entity type) for every sentence of this source that REGISTERS -
    which sentences do is `setup_bundle.registering_sentences`, the word the runtime keys on.
    The entity type is `""` while the subject binding names none."""
    found: list[tuple[str, str]] = []
    for sentence, mapping in registering_sentences(source):
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


def _answer_or_default(answer: Any, default: Any, from_path: str) -> dict:
    """A read cell's state and value: the file's answer, else the product's default shown as
    derived (`setup_bundle.source_defaults`, 총괄 261311e71), else missing."""
    if answer:
        return {"state": "answered", "value": answer}
    if default:
        shown = (", ".join(default) if isinstance(default, list)
                 and all(isinstance(item, str) for item in default)
                 else json.dumps(default, sort_keys=True))
        return {"state": "derived", "value": default, "disposition": "default_overridable",
                "ground": Ground("read_default", f"Default: {shown}", (from_path,), default)}
    return {"state": "missing", "value": answer}


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
        yield Field(
            path=f"{base}.relation", step="sources", label="relation",
            state="answered" if relation else "missing", tier=TIER_CONSTRAINED,
            value=relation, declared=relation if relation else _ABSENT,
            candidates=tuple(sorted(catalog, key=str)),
            note=f"Candidates come from {PHYSICAL_CATALOG_FILENAME}. Declare a missing one there first.",
            reshapes=True,
        )
        # 🔴 [총괄 261311e71] A CELL THE FILE LEAVES OUT IS SHOWN WITH THE PRODUCT'S ANSWER, from
        # the one function the validator fills it with - never asked as a red square.
        filled = source_defaults(source, catalog)
        filled = (filled.get("read") or {}) if isinstance(filled, Mapping) else {}
        unit = driver.get("unit")
        yield Field(
            path=f"{base}.read.unit", step="sources", label="Unit",
            tier=TIER_CONSTRAINED, declared=unit if unit else _ABSENT,
            candidates=tuple(sorted(_SOURCE_UNITS)),
            **_answer_or_default(unit, filled.get("unit"), f"{base}.read"),
        )
        identity = list(_listed(driver.get("identity")))
        yield Field(
            path=f"{base}.read.identity", step="sources", label="identity",
            tier=TIER_CONSTRAINED, declared=identity if identity else _ABSENT,
            candidates=tuple(physical), universe=UNIVERSE_RELATION,
            **_answer_or_default(identity, filled.get("identity"), f"{base}.read"),
        )
        # `unit: row` has no group_by row: the skeleton draws the field for `unit: group`
        # alone, and a row source writes none (`setup_bundle.read_group_by`).
        if unit == "group":
            group_by = list(_listed(read_group_by(driver)))
            # 🔴 A DEFAULT ONLY WHERE THE FILE SAYS NOTHING, AND THAT IS WHY IT CANNOT PAINT
            # A LEGAL DECLARATION RED.  `group_by` equals `identity` on both live sources,
            # and the validator binds them ONE WAY ONLY -- `invalid_driver: group_by columns
            # must be included in identity` -- so a strict SUBSET is legal and common.
            # Deriving unconditionally would compare the whole of `identity` against such a
            # declaration and call it a conflict - the mistake the `comparison` docstring
            # was written for.  A declared `group_by` therefore stays
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
                candidates=tuple(identity), universe=UNIVERSE_RELATION,
                disposition="default_overridable" if filling else "",
                ground=Ground(
                    "group_by_default_from_identity",
                    f"Default: identity {', '.join(str(key) for key in identity)}",
                    (f"{base}.read.identity",), list(identity)) if filling else None,
                note="Candidates are limited to identity.",
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
            shortest = default_ordering_key(catalog, relation)
            declared = driver.get("order_by")
            yield Field(
                path=f"{base}.read.order_by", step="sources", label="order_by",
                state="derived", tier=TIER_DERIVATION, value=list(shortest),
                declared=list(_listed(declared)) if declared is not None else _ABSENT,
                ground=Ground(
                    "ordering_default_from_catalog_key",
                    f"Default: the declared key of {relation} in {PHYSICAL_CATALOG_FILENAME} "
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
                note=f"Default {', '.join(str(key) for key in shortest)}"
                     " · pick to change",
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
        time_default = None if answered else filled.get("occurred_at")
        yield Field(
            path=f"{base}.read.occurred_at", step="sources", label="Time",
            state="answered" if answered else "derived" if time_default else "missing",
            tier=TIER_CONSTRAINED,
            value=dict(occurred) if occurred else time_default,
            declared=dict(occurred) if occurred else _ABSENT,
            disposition="default_overridable" if time_default else "",
            candidates=tuple(
                [{"column": name, "timezone": zone} for name in time_columns]
                + [{"basis": name, "timezone": zone}
                   for name in sorted(_OCCURRED_AT_BASES)]),
            universe=UNIVERSE_RELATION,
            ground=Ground(
                "occurred_at_candidates_from_column_types",
                (f"Limit: {relation} has no column to read as a time -> basis only"
                 if narrowed
                 else f"Candidates: {len(time_columns)} columns of {relation} readable as a time + basis"),
                (f"{PHYSICAL_CATALOG_FILENAME}:{relation}",), list(time_columns)),
            # 🔴 A PENDING RULING IS NOT A FORM FIELD'S BUSINESS.  This said which question
            # was still open and named the task file holding it -- true, and useless to
            # somebody filling the box, who cannot act on either.  What is left is the one
            # rule that changes what they press.
            note="Pick one of column · basis", reshapes=True,
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
        zone_default = (time_default or {}).get("timezone") if not answered_zone else None
        yield Field(
            path=f"{base}.read.occurred_at.timezone", step="sources",
            label="Time zone",
            state="answered" if answered_zone else "derived" if zone_default else "missing",
            tier=TIER_CONSTRAINED,
            value=declared_zone if answered_zone else zone_default,
            declared=declared_zone if answered_zone else _ABSENT,
            # 🔴 A SUGGESTION, NEVER A LIST TO PICK FROM.  What the file already answers
            # plus the default -- no IANA table is shipped and none is enforced, so a site
            # outside Seoul types it once and every later source is offered that answer.
            candidates=timezone_candidates,
            note="Filled with the time · type another if it differs",
            # A zone the file leaves out is the product's default (its event edges' zone), stated
            # as `_answer_or_default` states one - a derived row with no ground fails the whole
            # plan, so a slim source's form did not open (lead 5c3e49954).
            **({"disposition": "default_overridable",
                "ground": Ground("read_default", f"Default: {zone_default}", (f"{base}.read",),
                                 zone_default)} if zone_default else {}),
        )
        # 총괄 04cecc30f ③: one row over the relation's columns; a candidate is the whole clause
        # `_validate_exclude_when` accepts, so the screen writes no shape of its own.
        excluded = list(_listed(driver.get("exclude_when")))
        yield Field(
            path=f"{base}.read.exclude_when", step="sources", label="Exclude when blank",
            state="answered" if excluded else "unanswered", tier=TIER_CONSTRAINED,
            value=excluded or None, declared=excluded if excluded else _ABSENT,
            candidates=tuple({"column": name, "blank": True} for name in physical),
            universe=UNIVERSE_RELATION,
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
            probe_default = None if probes else filled.get("registration_probe")
            yield Field(
                path=f"{base}.read.registration_probe", step="sources",
                label="Registration probe",
                state="answered" if probes else "derived" if probe_default else "missing",
                tier=TIER_CONSTRAINED,
                value=([dict(probe) for probe in probes if isinstance(probe, Mapping)]
                       or probe_default or []),
                declared=list(probes) if probes else _ABSENT,
                ground=Ground(
                    "registration_probe_required_by_register_sentences",
                    f"Needed: this source has {len(registers)} register sentences "
                    f"({', '.join(sentence for sentence, _ in registers) or 'none'})",
                    tuple(f"{base}.bind.mappings.{sentence}"
                          for sentence, _ in registers) or (base,)),
                note="Required when there is a register sentence · without it the whole backfill is refused",
            )
        for probe_index, probe in enumerate(probes):
            if not isinstance(probe, Mapping):
                continue
            ppath = f"{base}.read.registration_probe[{probe_index}]"
            yield Field(
                path=f"{ppath}.entity_type",
                step="sources", label="Registration probe entity",
                state="answered" if probe.get("entity_type") else "missing",
                tier=TIER_CONSTRAINED, value=probe.get("entity_type"),
                declared=probe.get("entity_type"),
                candidates=probe_entities,
                note="The entity a register sentence registers · one identity key",
            )
            columns = list(_listed(probe.get("columns")))
            yield Field(
                path=f"{ppath}.columns", step="sources", label="Registration probe columns",
                state="answered" if columns else "missing", tier=TIER_CONSTRAINED,
                value=columns, declared=columns if columns else _ABSENT,
                candidates=tuple(physical), universe=UNIVERSE_RELATION,
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
    # rows at the paths the refusals name: both bare (총괄 4eb1fe98f)
    bundle = fold_versions(dict(bundle))
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
        # `allow_empty=True` for `read.group_by`, so `[]` IS an answer there, and `_says_nothing`'s own docstring
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
    as a gap is how a fill starts overwriting decisions.  `accepts_verified_join_rules` was
    exactly that field, `false` on all three live sources (⚰️ gone with `prepare`).
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


def _holds(document: Any, steps: Sequence[Any]) -> bool:
    """Is there a value at `steps`, addressed as `_fill_leaf` addresses (mapping keys)?"""
    for step in steps:
        if not isinstance(document, Mapping) or step not in document:
            return False
        document = document[step]
    return True


def filled_declaration(bundle: Mapping[str, Any], catalog: Mapping[str, Any],
                       bundle_path: Sequence[Any], raw: Mapping[str, Any]
                       ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`(raw, dropped)` - `raw` without the fields its own choices switched off, with the
    plan's derived values written into the gaps it leaves. `dropped` is what went, as
    `{path, value}` (총괄 b30fbd38c ㄱ - the save and the unsaved plan both pass here).

    🔴 THE SCREEN SAYS 「채움」 AND THE FILE HAS TO AGREE.  A `derived` row renders its value
    and its ground, so the operator reads "this is filled in" -- and then the declaration is
    saved with the box still empty, the validator refuses `missing_field` on the very square
    that said it filled itself, and the square goes red.  Measured on the half-built
    `user_test` source, 2026-08-21: of its 7 red squares, 3 were this -- both
    `implementation_version` boxes and `read.order_by` -- so three of the seven things it
    asked a person to go and fix were things it had already answered.  NARROWED, not reversed
    (총괄 04cecc30f): 「로더가 채우지 않는 칸은 화면이 채운 대로 파일에 — 로더가 채우는 칸은
    파일에 안 쓴다(3a2d79ff9 뒤)」.

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
        return out, []
    doc, dropped = skeleton(), []
    _drop_switched_off(out, _skeleton_node(doc, steps), doc.get("defs", {}),
                       "bundle." + ".".join(steps), dropped)
    document = copy.deepcopy(dict(bundle))
    cursor: Any = document
    for step in steps[:-1]:
        if not isinstance(cursor, dict) or not isinstance(cursor.get(step), dict):
            return out, dropped
        cursor = cursor[step]
    if not isinstance(cursor, dict):
        return out, dropped
    cursor[steps[-1]] = out
    # 🔴 [총괄 04cecc30f] A CELL THE LOADER FILLS IS NOT WRITTEN - the rule above, narrowed. The
    #    loader (`with_read_defaults`) fills a left-out cell before the bundle is hashed, so writing
    #    its value changed only the file: every default of a slim source landed in it the first
    #    time one of its read cells was saved. The loader is asked, not listed here.
    loaded: Any = with_read_defaults(document, catalog)
    for step in steps:
        loaded = loaded.get(step) if isinstance(loaded, Mapping) else None
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
        # inventing a value nobody picked.  An empty LIST is a different thing -- it is an
        # answer -- so it is written.
        if row["value"] is None:
            continue
        at = _split_path(row["path"])[len(steps):]
        if not _holds(out, at) and _holds(loaded, at):
            continue
        _fill_leaf(out, at, row["value"])
    return out, dropped
