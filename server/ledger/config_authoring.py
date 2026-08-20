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
compiled from `bind.mappings.<sentence>.use`.  A `derived` row still costs the operator a line in
the file and a row on the screen; a retired one costs neither.

The tiers, strongest first, are recorded per field in ``tier`` so a reader can audit that
ranking rather than take it on faith:
``structural`` > ``derivation`` > ``constrained_input`` > ``diagnostic``.

NOTHING HERE WRITES.  The plan is a read over a bundle mapping and the catalog; the
authoring path that applies a choice is `config_drafts`, unchanged by this module.
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
from .setup_bundle import (
    _APPROVAL_STATUSES,
    _BINDING_ORIGINS,
    _MAPPER_UNITS,
    _OBJECT_KINDS,
    _OCCURRED_AT_BASES,
    _ROLE_KINDS,
    _SCALAR_ROLE_KINDS,
    _SOURCE_UNITS,
    PHYSICAL_CATALOG_FILENAME,
    public_bundle_schema,
    role_binding_kinds,
    validate_bundle_errors,
)

#: `setup_bundle` spells these inline in `_validate_vocabulary` rather than binding them
#: to a name, so this is the one closed list this module cannot import.  Kept next to the
#: imports so the day it becomes a constant there, the fix is one line here.
PREDICATE_STATUSES = ("active", "retired")

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
STEPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("entities", "엔터티", ("entities",)),
    ("vocabulary", "낱말", ("vocabulary",)),
    ("packs", "팩", ("packs",)),
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


def _role_reference(role_id: str, role: Mapping[str, Any]) -> str:
    """The only legal spelling of a reference to this Role from a non-required endpoint."""
    return f"${role_id}" if role.get("required") is True else f"${role_id}?"


def _claim_ref(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or value.count("/") != 1:
        return None
    pack_id, claim_id = value.split("/", 1)
    return (pack_id, claim_id) if pack_id and claim_id else None


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

    Only containers.  A required LEAF stays absent on purpose: absent is `missing_field`,
    which tells the operator to fill it, while a seeded `""` would read as a value they
    chose.  And nothing here knows a field by name -- it asks the skeleton whether the field
    is required and whether it is a container, so the next section with the same shape is
    covered without being mentioned.

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
            if not isinstance(child, Mapping) or child.get("kind") == "leaf":
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
        "binding_origin": sorted(_BINDING_ORIGINS),
        "approval_status": sorted(_APPROVAL_STATUSES),
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


def _packs_fields(bundle: Mapping[str, Any]) -> Iterable[Field]:
    vocabulary = _section(bundle, "vocabulary")
    for pack_id in sorted(_section(bundle, "packs"), key=str):
        pack = _section(bundle, "packs")[pack_id]
        claims = pack.get("claims") if isinstance(pack, Mapping) else None
        if not isinstance(claims, Mapping):
            continue
        for claim_id in sorted(claims, key=str):
            claim = claims[claim_id]
            if not isinstance(claim, Mapping):
                continue
            yield from _claim_fields(bundle, vocabulary, pack_id, claim_id, claim)


def _claim_fields(bundle: Mapping[str, Any], vocabulary: Mapping[str, Any],
                  pack_id: str, claim_id: str, claim: Mapping[str, Any]
                  ) -> Iterable[Field]:
    base = f"bundle.packs.{pack_id}.claims.{claim_id}"
    roles = claim.get("roles") if isinstance(claim.get("roles"), Mapping) else {}
    emit = claim.get("emit") if isinstance(claim.get("emit"), Mapping) else {}
    predicate_id = emit.get("predicate")
    predicate = vocabulary.get(predicate_id) if isinstance(predicate_id, str) else None

    active_predicates = tuple(sorted(
        name for name, item in vocabulary.items()
        if isinstance(item, Mapping) and item.get("status") == "active"))
    yield Field(
        path=f"{base}.emit.predicate", step="packs", label="낱말",
        state="answered" if predicate_id else "missing", tier=TIER_CONSTRAINED,
        value=predicate_id, declared=predicate_id if predicate_id else _ABSENT,
        candidates=active_predicates,
        note="retired 낱말은 후보에서 빠진다.",
    )

    obj = emit.get("object") if isinstance(emit.get("object"), Mapping) else {}
    if isinstance(predicate, Mapping):
        contract = predicate.get("object")
        contract = contract if isinstance(contract, Mapping) else {}
        kind = contract.get("kind")
        if isinstance(kind, str):
            # ① 자유도 0. The validator compares this for equality with the predicate.
            yield Field(
                path=f"{base}.emit.object.kind", step="packs", label="목적어 종류",
                state="derived", tier=TIER_STRUCTURAL,
                value=kind, declared=obj.get("kind", _ABSENT),
                ground=Ground(
                    "emit_object_kind_from_predicate",
                    f"채움: {predicate_id}의 object.kind",
                    (f"bundle.vocabulary.{predicate_id}.object.kind",), kind),
                note="kind에 따라 이 아래의 칸 구성이 바뀐다.",
            )
        qualifiers = contract.get("qualifiers")
        qualifiers = qualifiers if isinstance(qualifiers, Mapping) else {}
        required = tuple(str(name) for name in _listed(qualifiers.get("required")))
        optional = tuple(str(name) for name in _listed(qualifiers.get("optional")))
        emitted = obj.get("qualifiers")
        emitted = emitted if isinstance(emitted, Mapping) else {}
        if required or optional:
            yield Field(
                path=f"{base}.emit.object.qualifiers", step="packs", label="qualifier 칸",
                state="derived", tier=TIER_DERIVATION,
                value={"required": list(required), "optional": list(optional)},
                ground=Ground(
                    "qualifier_slots_from_predicate",
                    f"채움: {predicate_id}의 qualifier 계약",
                    (f"bundle.vocabulary.{predicate_id}.object.qualifiers",),
                    {"required": list(required), "optional": list(optional)}),
                disposition="shape",
                note="required는 칸을 미리 만들고, optional만 쓸지 묻는다.",
            )
        # One row per qualifier the predicate allows.  WHICH Role fills it is free; how
        # the reference is SPELLED is not -- `_cross_emission_role(...,
        # required_endpoint=False)` refuses when `is_required_role == is_optional_ref`,
        # so a required Role must read `$r` and an optional one `$r?`.  The candidates
        # are therefore emitted already spelled, and the question mark is never typed.
        candidates = tuple(
            _role_reference(name, roles[name])
            for name in sorted(roles, key=str)
            if isinstance(roles.get(name), Mapping)
            and roles[name].get("kind") in _SCALAR_ROLE_KINDS)
        for name in sorted(set(required) | set(optional) | set(emitted), key=str):
            qpath = f"{base}.emit.object.qualifiers.{name}"
            ref = emitted.get(name)
            role_id = _role_name(ref)
            role = roles.get(role_id) if isinstance(roles, Mapping) else None
            if isinstance(role, Mapping):
                yield Field(
                    path=qpath, step="packs", label=f"qualifier {name}",
                    state="derived", tier=TIER_STRUCTURAL,
                    value=_role_reference(role_id, role), declared=ref,
                    candidates=candidates,
                    ground=Ground(
                        "role_ref_spelling_from_role_required",
                        f"채움: Role {role_id} required="
                        f"{str(role.get('required') is True).lower()} → 표기 확정",
                        (f"{base}.roles.{role_id}.required",),
                        role.get("required") is True),
                )
            elif name in required:
                yield Field(
                    path=qpath, step="packs", label=f"qualifier {name}",
                    state="missing", tier=TIER_CONSTRAINED, candidates=candidates,
                    refusals=({
                        "code": "missing_required_payload", "path": qpath,
                        "message": f"predicate {predicate_id!r} requires qualifier "
                                   f"{name!r}"},),
                )
            else:
                yield Field(
                    path=qpath, step="packs", label=f"qualifier {name}",
                    state="unanswered", tier=TIER_CONSTRAINED, candidates=candidates,
                    note="optional qualifier. 쓸지 여부만 자유.",
                )

    for endpoint, expected_kinds in (
        ("subject", ("entity",)), ("occurred_at", ("time",)),
    ):
        candidates = tuple(sorted(
            name for name, role in roles.items()
            if isinstance(role, Mapping) and role.get("required") is True
            and role.get("kind") in expected_kinds))
        value = emit.get(endpoint)
        yield Field(
            path=f"{base}.emit.{endpoint}", step="packs", label=f"emit.{endpoint}",
            state="answered" if value else "missing", tier=TIER_CONSTRAINED,
            value=value, declared=value if value else _ABSENT,
            candidates=tuple(f"${name}" for name in candidates),
            note="required이고 kind가 맞는 Role만 후보.",
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
        if physical:
            inputs = list(_listed(preparation.get("input_columns")))
            # 🔴 THE ONE UNIVERSE THAT MADE THIS MOVE NECESSARY.  A preparer reads the
            # PHYSICAL table and nothing else -- it runs before anything has been
            # prepared -- so its candidates are `relation`'s columns.  While the body
            # lived in its own section this field had no relation to point at and the
            # screen offered a bare text box.
            yield Field(
                path=f"{prep_base}.input_columns", step="sources",
                label="준비기 input_columns",
                state="answered" if inputs else "unanswered", tier=TIER_CONSTRAINED,
                value=inputs, declared=inputs if inputs else _ABSENT,
                candidates=tuple(physical), universe=UNIVERSE_RELATION,
                note="준비기는 준비 전에 돌기 때문에 물리 표 컬럼만 읽을 수 있다.",
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
        if inherited:
            yield Field(
                path=f"{prep_base}.accepts_verified_join_rules", step="sources",
                label="accepts_verified_join_rules", state="derived",
                tier=TIER_DERIVATION, value=True,
                declared=preparation.get("accepts_verified_join_rules", _ABSENT),
                ground=Ground(
                    "accepts_join_rules_from_inheritance",
                    f"채움: 소스 {source_id}가 join rule {len(inherited)}건 상속",
                    (f"{prep_base}.inherit_virtual_join_rules",), True),
            )

        # -------------------------------------------------------------------- mapper
        mapper = _mapper(source)
        base = f"bundle.sources.{source_id}.map"
        # `emits` was a `derived` row here until 2026-08-21 -- set equality in BOTH
        # directions, zero degrees of freedom.  A field the screen fills and never asks is
        # still a field the file carries, so this round removed the declaration instead:
        # `MapperDescriptor.emits` is compiled from `bind.mappings.<sentence>.use` and there is
        # nothing left to show.
        binding_columns = profile_binding_columns(profile_base, profile) if profile else ()
        if binding_columns:
            yield Field(
                path=f"{base}.input_columns", step="sources",
                label="매퍼 input_columns", state="derived", tier=TIER_DERIVATION,
                value=sorted({column for column, _ in binding_columns}),
                declared=list(_listed(mapper.get("input_columns")))
                if "input_columns" in mapper else _ABSENT,
                ground=Ground(
                    "mapper_inputs_from_profile_bindings",
                    f"채움: 소스 {source_id}의 프로필이 바인딩한 컬럼 "
                    f"{len({column for column, _ in binding_columns})}개",
                    tuple(path for _, path in binding_columns),
                    sorted({column for column, _ in binding_columns})),
                comparison="superset",
                # 🔴 RELATION ∪ 준비기.output_columns, WHICH THE MAPPER COULD NOT BE TOLD
                # BEFORE.  The mapper runs AFTER preparation, so a preparer-made column is
                # legal here and a physical one still is too -- the widening the move was
                # for. The derived value is a MINIMUM; the universe is what a person may
                # widen it to.
                candidates=tuple(prepared), universe=UNIVERSE_PREPARED,
                note="최소 집합. 더 넓게 선언해도 통과하지만 물어볼 이유가 없다.",
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
                note=f"kind=group_by일 때만 존재. 소스 group_by={group_by}",
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
    packs = _section(bundle, "packs")
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
        for sentence, mapping in _mappings(profile):
            yield from _mapping_fields(
                base, sentence, mapping, packs, entities, available)


def _mapping_fields(base: str, sentence: str, mapping: Mapping[str, Any],
                    packs: Mapping[str, Any], entities: Mapping[str, Any],
                    available: Sequence[str]) -> Iterable[Field]:
    mpath = f"{base}.mappings.{sentence}"
    parsed = _claim_ref(mapping.get("use"))
    if parsed is None:
        yield Field(
            path=f"{mpath}.use", step="sources", label="use",
            state="missing", tier=TIER_CONSTRAINED,
            candidates=tuple(sorted(
                f"{pack_id}/{claim_id}"
                for pack_id, pack in packs.items()
                if isinstance(pack, Mapping) and isinstance(pack.get("claims"), Mapping)
                for claim_id in pack["claims"])),
        )
        return
    pack_id, claim_id = parsed
    pack = packs.get(pack_id)
    claims = pack.get("claims") if isinstance(pack, Mapping) else None
    claim = claims.get(claim_id) if isinstance(claims, Mapping) else None
    if not isinstance(claim, Mapping):
        return
    roles = claim.get("roles") if isinstance(claim.get("roles"), Mapping) else {}
    bind = mapping.get("bind") if isinstance(mapping.get("bind"), Mapping) else {}

    # The row set itself is derived: which roles exist is the Claim's business.
    yield Field(
        path=f"{mpath}.bind", step="sources", label="결선할 역할",
        state="derived", tier=TIER_DERIVATION,
        value=sorted(roles, key=str),
        ground=Ground(
            "bind_rows_from_claim_roles",
            f"채움: Claim {pack_id}/{claim_id}의 역할 {len(roles)}개",
            (f"bundle.packs.{pack_id}.claims.{claim_id}.roles",),
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
                    "message": f"Claim requires role {role_id!r}"},) if required else (),
            )
            continue
        yield Field(
            path=f"{mpath}.bind.{role_id}.kind", step="sources",
            label=f"역할 {role_id} 결선 종류", state="answered",
            tier=TIER_CONSTRAINED, value=binding.get("kind"),
            declared=binding.get("kind"),
            candidates=tuple(role_binding_kinds(role)),
        )
        if role.get("kind") == "symbolic" and binding.get("kind") == "constant":
            yield Field(
                path=f"{mpath}.bind.{role_id}.value", step="sources",
                label=f"역할 {role_id} 상수", state="answered",
                tier=TIER_CONSTRAINED, value=binding.get("value"),
                declared=binding.get("value"),
                candidates=tuple(_listed(role.get("allowed_values"))),
            )
        if binding.get("kind") == "column":
            yield Field(
                path=f"{mpath}.bind.{role_id}.column", step="sources",
                label=f"역할 {role_id} 컬럼", state="answered",
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
        note="남는 질문은 「각 키에 어느 컬럼」 하나뿐.",
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


def _source_fields(bundle: Mapping[str, Any], catalog: Mapping[str, Any]
                   ) -> Iterable[Field]:
    entities = _section(bundle, "entities")
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
            yield Field(
                path=f"{base}.read.group_by", step="sources", label="group_by",
                state="answered" if group_by else "missing", tier=TIER_CONSTRAINED,
                value=group_by, declared=group_by if group_by else _ABSENT,
                candidates=tuple(identity), universe=UNIVERSE_PREPARED,
                note="후보는 identity로 제한된다.",
            )
        table = catalog.get(relation) if isinstance(relation, str) else None
        unique_keys = declared_unique_keys(table) if isinstance(table, Mapping) else ()
        if unique_keys:
            shortest = min(unique_keys, key=len)
            cursor = driver.get("cursor") if isinstance(driver.get("cursor"), Mapping) else {}
            for name, declared in (
                ("order_by", driver.get("order_by")),
                ("cursor.columns", cursor.get("columns")),
            ):
                yield Field(
                    path=f"{base}.read.{name}", step="sources", label=name,
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
                    note="선언 키는 주장이지 실측이 아니다. 컬럼 피커의 유일성으로 확인할 것.",
                )
        occurred = driver.get("occurred_at")
        occurred = occurred if isinstance(occurred, Mapping) else {}
        types = _column_types(catalog, relation)
        time_columns = tuple(sorted(
            name for name, kind in types.items() if kind == "datetime"))
        # The CANDIDATE SET is derived; the answer is not.  A table with no time-typed
        # column leaves `basis` as the only door, and the screen says so instead of
        # letting a person discover it through three refusals -- but it still ASKS,
        # because which basis a grouped event should read is not settled (see the note).
        answered = bool(occurred.get("column") or occurred.get("basis"))
        narrowed = bool(physical) and not time_columns
        yield Field(
            path=f"{base}.read.occurred_at", step="sources", label="시각",
            state="answered" if answered else "missing", tier=TIER_CONSTRAINED,
            value=dict(occurred) if occurred else None,
            declared=dict(occurred) if occurred else _ABSENT,
            candidates=tuple(
                [{"column": name} for name in time_columns]
                + [{"basis": name} for name in sorted(_OCCURRED_AT_BASES)]),
            universe=UNIVERSE_RELATION,
            ground=Ground(
                "occurred_at_candidates_from_column_types",
                (f"제한: {relation}에 시각 타입 컬럼 없음 → basis만"
                 if narrowed
                 else f"후보: {relation}의 시각 타입 컬럼 {len(time_columns)}개 + basis"),
                (f"{PHYSICAL_CATALOG_FILENAME}:{relation}",), list(time_columns)),
            note="column과 basis 중 정확히 하나. "
                 "basis가 묶음 이벤트에서 무엇을 읽는지는 소유자 판정 대기"
                 "(task/ledger_basis_on_grouped_events.md).",
        )
        probes = _listed(driver.get("registration_probe"))
        single_key = tuple(sorted(
            name for name, entity in entities.items()
            if isinstance(entity, Mapping) and len(_listed(entity.get("keys"))) == 1))
        for probe_index, probe in enumerate(probes):
            if not isinstance(probe, Mapping):
                continue
            yield Field(
                path=f"{base}.read.registration_probe[{probe_index}].entity_type",
                step="sources", label="등록 탐침 엔터티", state="answered",
                tier=TIER_CONSTRAINED, value=probe.get("entity_type"),
                declared=probe.get("entity_type"),
                candidates=single_key,
                note="식별키가 하나인 엔터티만 후보.",
            )


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
        *_packs_fields(bundle),
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
