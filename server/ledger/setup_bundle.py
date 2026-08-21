"""Pure Ledger authoring bundle schema and single-file loader.

This module deliberately has no database, translator, mapper, compiler, cursor, or store
imports.  Stage 2 owns only the authoring boundary: strict files in one root become one
deterministically serializable logical bundle.  Runtime registries are a later stage.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import difflib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SETUP_VERSION = 5

#: The one authoring file. The path does not move: the operator writes here.
CONFIG_FILENAME = "ledger_config.json"

#: The whole authoring surface, in the order the file declares it.  All four are
#: REQUIRED even when empty: a missing key and an empty one mean different things to a
#: reader, and "the section does not apply to me" is a decision worth writing down.
#:
#: 🔴 `profiles` IS NOT HERE EITHER (owner, 2026-08-20: 「그럼 프로필도 소스랑 묶여야 하는거
#: 아니야?」).  The 1:1 was already ENFORCED, not merely observed: a profile had to declare
#: `source`, and `_cross_validate` refused any value but the id of the source that selected
#: it -- so a profile could never be shared and a separate section bought nothing.  The body
#: now lives inline at `sources.*.bind`, and its `source` field is gone with the section:
#: the source that HOLDS it is the answer that field used to repeat.
#: 🔴 `source_preparers` AND `mappers` ARE NOT HERE EITHER (owner, 2026-08-20: 「소스플랜
#: 준비기 맵퍼」).  A preparer's `input_columns` must be columns of a PHYSICAL relation, and
#: `relation` is declared only by a source -- so a preparer sitting in its own section was
#: always one hop away from the only declaration that could check it.  Both bodies now live
#: inline at `sources.*.prepare` and `sources.*.map`, where the
#: relation is one key away.  Measured before the move: both were 1:1 with their source, so
#: no sharing was lost.  What is reused is CODE, not declaration, and that reuse is still
#: spelled `implementation_id` + `implementation_version`, which both bodies still carry.
#: 🔴 `tables` IS NOT HERE, AND ITS ABSENCE IS THE POINT (owner, 2026-08-18: "why is
#: `tables` in the ledger json as well?").  It used to be an eighth section restating
#: the physical schema.  Measured on the live root before removal: its one relation was a
#: COMPLETE duplicate of the catalog entry -- 8 columns, 8/8 types agreeing, the same
#: single-column business key -- and no RUNNING code compared them.  (One test did, for
#: that one relation; a hand-kept pin over one row says nothing about the next one, and
#: said nothing about the sample root, whose copy had drifted into columns that exist
#: nowhere.)  Two copies that no code puts side by side do not stay equal; they drift in
#: silence and disagree only at execution.
#: The physical schema now has exactly one author, `server/config/table_config.json`,
#: which `_physical_catalog` reads.  See `PHYSICAL_CATALOG_FILENAME`.
#: 🔴 `packs` LEFT ON 2026-08-21, AND IT IS THE THIRD RESTATEMENT THIS FILE HAS RETIRED
#: (owner: 「굳이 claims 도 불필요하지 않나 … 실질적 클레임은 vocab 만 남잖아」).  A Claim
#: declared Roles and an `emit` clause; `predicate_claim` now derives both from the
#: predicate the mapping names.  See that function for what was measured first.
LOGICAL_SECTIONS = (
    "vocabulary", "entities", "sources",
)

#: 🔴 OPTIONAL, AND THE DISTINCTION IS DELIBERATE.  The operator root stops carrying a
#: `virtual_joins` section -- it was empty there, and an enabled rule is refused unless a
#: caller supplies a physically verified descriptor, so nothing was lost by dropping it.
#: But the LOADER keeps the ability to read one, because a different root does use it:
#: `server/config/sample/ontology/transfer_explorer/` supplies real descriptors and
#: `docs/qa/FEATURE_CHECKLIST.md` lists that round trip as a capability.  Removing the
#: section from a FILE and removing support from the LOADER are not the same act, and
#: only the first was asked for.
OPTIONAL_SECTIONS = ("virtual_joins",)

ALL_SECTIONS = (*LOGICAL_SECTIONS, *OPTIONAL_SECTIONS)

#: The physical-schema authority for the WHOLE system -- ingestion, the chain workers, the
#: grid, and now the ledger read the same file.  The ledger does not get a private copy and
#: does not get a private checker.
#:
#: 🔴 WHY THIS ALSO CLOSES A HOLE RATHER THAN JUST REMOVING A DUPLICATE.
#: `server/schema_drift.py` (`_register_dynamic_models`) sweeps every SQLAlchemy-mapped
#: table, and that set INCLUDES the dynamic tables built from this file.  So a column named
#: here that the database does not have is already reported.  A column named in a ledger-
#: private `tables` section was checked against nothing, which is how an invented column
#: name came to pass green (measured 2026-08-18).  Reading this file is therefore not a
#: tidier spelling of the same check -- it is the difference between a declaration that is
#: verified against the database and one that is verified against itself.  Adding a second
#: "declaration vs database" verifier would put the system back where it started: two
#: verifiers that can disagree.
PHYSICAL_CATALOG_FILENAME = "table_config.json"

_VERSIONED_ID = re.compile(r"^[^@/\s]+@[1-9][0-9]*$")
_FORBIDDEN_DECLARATION_KEYS = frozenset({
    "module", "function", "path", "python", "sql", "javascript",
    "expression", "eval", "exec", "lookup", "lookups", "declared_lookup",
    "position", "positions", "frame", "frames",
})
_FORBIDDEN_EXECUTABLE_KEYS = frozenset({
    "module", "function", "path", "python", "sql", "javascript",
    "expression", "eval", "exec",
})
#: What an unwritten `binding_origin` means, and the ONLY reason it may be left unwritten.
#:
#: 🔴 SILENCE MAY ONLY DEFAULT TO THE VALUE THAT GRANTS NOTHING.  `user_declared` is the
#: plainest kind of authorship -- it permits nothing that writing it out would not, and the
#: one rule that reads this field (`suggestion_reason`, below) fires on
#: `system_suggested` alone.  So an absent field and a written `user_declared` are the same
#: claim, and 40 repetitions of a constant leave the operator's file.
#:
#: `approval_status` LOOKS symmetric and is not, which is why it stays required.
#: `roleframe._evaluate_binding` refuses to execute any binding that does not say
#: `approved`, so defaulting an absent one to `approved` would turn "approved only if it
#: says so" into "approved unless it says otherwise" -- and the legacy v1 reader
#: (`source_profile._binding`) already defaults the same absence to `pending`, so the two
#: would answer differently about one file.
_DEFAULT_BINDING_ORIGIN = "user_declared"
_BINDING_ORIGINS = frozenset({_DEFAULT_BINDING_ORIGIN, "system_suggested", "imported"})
_APPROVAL_STATUSES = frozenset({"pending", "approved", "rejected"})
_JOIN_FOLD_RULES = frozenset({"separator", "case", "zero_pad"})
_IMPLEMENTED_JOIN_FOLD_RULES = frozenset({"separator", "case"})
_ROLE_KINDS = frozenset({
    "entity", "time", "quantity", "identity", "order", "attribute", "symbolic",
})
_SCALAR_ROLE_KINDS = frozenset({
    "quantity", "identity", "order", "attribute", "symbolic",
})
_OBJECT_KINDS = frozenset({"none", "entity_ref", "value", "event_ref"})
_SOURCE_UNITS = frozenset({"row", "group"})
_MAPPER_UNITS = frozenset({"event", "row", "group_by"})
# A source whose table carries no world time declares that instead of naming a column.
# Closed on purpose: an open string here would let a typo become a silent claim about time.
_OCCURRED_AT_BASES = frozenset({"ingested"})


class LedgerSetupValidationError(ValueError):
    """One stable validation issue with its exact authoring path."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def load_physical_catalog(path: str | Path) -> Mapping[str, Any]:
    """`table_config.json` as the relation shape the cross-validators read.

    🔴 THE PATH IS REQUIRED, AND THIS MODULE DOES NOT KNOW WHERE DATA LIVES.
    Resolving it would mean importing `paths`, and this module's contract is that it
    imports no runtime at all -- a contract with a test behind it
    (`test_common_module_has_no_domain_source_branches_or_runtime_imports`).  "Which data
    root am I" is a deployment question and an isolated stack must answer it differently
    from production, so it is answered one level up, in `ledger.setup`.

    The translation, and why each rule is the rule:

    * ``columns``       <- ``column_types``.  Same fact, other spelling.
    * ``composite_key`` <- ``composite_key_source``.  That list IS the row identity: it is
      the tuple `crud.assemble_composite_business_key` joins to build `business_key_val`,
      so covering it is exactly what makes an ordering unique.
    * ``business_key``  <- ``business_key``, GATED ON IT BEING A DECLARED COLUMN.
      That membership test, and NOT the `composite_key_source` gate
      `chain_bindings.identity_column` applies, is the right gate for THIS question --
      worth stating because the two rules look interchangeable.  That one asks "which
      column carries the job" and must refuse an assembled CELL key; this one asks "which
      tuples are unique", and an assembled key MATERIALIZED into its own column is
      unique, so ordering by it is provably an ordering by identity.  A table declaring
      both -- and three relations in the live catalog do declare both -- therefore keeps
      both.  A `business_key` naming something that is not a column of the relation
      certifies nothing and is dropped.

    ⚠️ `map_key_columns` is NOT translated into a key.  It is a lookup prefix -- one map
    holds many rows -- and admitting it here would certify a NON-unique ordering as a
    cursor, which is the one direction that loses events.

    A missing or unreadable catalog is a NAMED refusal, never an empty catalog.  An empty
    catalog would refuse every source with `unknown_relation`, which points the operator at
    the wrong file to fix.
    """
    catalog_path = Path(path)
    if not catalog_path.is_file():
        raise LedgerSetupValidationError(
            "physical_catalog_absent", PHYSICAL_CATALOG_FILENAME,
            f"the ledger reads the physical schema from {catalog_path}, which does not "
            f"exist")
    try:
        document = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise LedgerSetupValidationError(
            "physical_catalog_unreadable", PHYSICAL_CATALOG_FILENAME,
            f"{catalog_path} could not be read as JSON: {exc}") from exc
    if not isinstance(document, Mapping):
        raise LedgerSetupValidationError(
            "physical_catalog_unreadable", PHYSICAL_CATALOG_FILENAME,
            f"{catalog_path} must hold a JSON object of table declarations")
    return _adapt_physical_catalog(document)


def _adapt_physical_catalog(document: Mapping[str, Any]) -> Mapping[str, Any]:
    catalog: dict[str, dict[str, Any]] = {}
    for table_id, declared in document.items():
        if str(table_id).startswith("__") or not isinstance(declared, Mapping):
            continue
        columns = declared.get("column_types")
        if not isinstance(columns, Mapping) or not columns:
            continue
        relation: dict[str, Any] = {
            "columns": {str(name): str(value) for name, value in columns.items()},
        }
        composite = declared.get("composite_key_source")
        if isinstance(composite, list) and composite:
            relation["composite_key"] = [str(column) for column in composite]
        # The consumers (`_table_has_unique_key`, `_columns_cover_declared_unique_key`)
        # read unique indexes to decide whether an ordering can resume deterministically.
        # `table_config.json` may declare extra ones per table, and they pass through here.
        indexes = declared.get("indexes")
        if isinstance(indexes, list) and indexes:
            relation["indexes"] = [dict(item) for item in indexes
                                   if isinstance(item, Mapping)]
        # 🔴 `row_id` IS THE PRIMARY KEY OF EVERY INGESTED TABLE, AND THE CATALOG DID NOT
        # SAY SO.  Measured 2026-08-21: 26 of 26 tables carry `PRIMARY KEY (row_id)` in
        # PostgreSQL, and 0 of 26 declared it here -- so the two consumers above were
        # permanently-empty branches and no source could name ANY resumable cursor whose
        # ordering the catalog would accept.
        # Declaring it per table would be 26 copies of one sentence, which is the shape
        # this config has spent the day deleting; the invariant belongs to the loader.
        # It is added rather than replaced so a table that also declares its own unique
        # index keeps it.
        #
        # ⚠️ THE COLUMN IS ADDED TOO, AND THAT IS NOT A CONVENIENCE.  `column_types` names
        # the BUSINESS columns; `row_id` is the ingestion framework's own identity and 0 of
        # 26 tables list it.  A first version of this guarded on `"row_id" in columns` and
        # was therefore dead on every table -- a permanently-false branch, which is the
        # exact defect this block exists to remove.  Declaring the column is what makes the
        # index nameable: a cursor may only cite columns the catalog admits.
        relation["columns"].setdefault("row_id", "string")
        relation.setdefault("indexes", []).append(
            {"columns": ["row_id"], "unique": True})
        business_key = declared.get("business_key")
        if (isinstance(business_key, str) and business_key.strip()
                and business_key in relation["columns"]):
            relation["business_key"] = business_key
        catalog[str(table_id)] = relation
    return catalog


@dataclass(frozen=True)
class LedgerSetupBundle:
    """Immutable normalized logical bundle; mappings are recursively read-only."""

    _data: Mapping[str, Any]

    @property
    def setup_version(self) -> int:
        return int(self._data["setup_version"])

    def section(self, name: str) -> Mapping[str, Any]:
        if name not in ALL_SECTIONS:
            raise KeyError(name)
        return self._data[name]

    def to_mapping(self) -> dict[str, Any]:
        return _thaw(self._data)

    def serialize(self) -> str:
        return json.dumps(
            self.to_mapping(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False)


class _DuplicateKey(ValueError):
    def __init__(self, key: str):
        self.key = key
        super().__init__(key)


class _InvalidJsonConstant(ValueError):
    pass


# A refusal that names the fault without naming the ACTION reads as "unknown error" to the
# operator who hits it, and the operator who hits this one is on the production box holding
# a config that was correct yesterday.  So a retired field says three things: what happened,
# where the truth lives now, and that nothing has to be copied across.
_RETIRED_FIELD_HELP = {
    "ledger_config.tables": (
        "field is not allowed - the 'tables' section retired on 2026-08-18. "
        "Physical schema is declared once, in server/config/table_config.json, and the "
        "ledger reads it from there. Delete this section; do NOT copy its contents "
        "anywhere. If a relation it named is missing from table_config.json, declare the "
        "relation there - this setup will then name that relation on its own."
    ),
}


#: How many declared names a refusal will list before it stops.  A message nobody reads to
#: the end helps nobody; the close-match branch below is the one that usually answers.
_CANDIDATE_LIMIT = 8


def _allowed_note(required: Sequence[str], optional: Sequence[str]) -> str:
    """What this object DOES take, appended to a refusal that says a field is not allowed.

    🔴 THE VALIDATOR IS HOLDING THE ANSWER AT THE MOMENT IT REFUSES.  `exact()` already has
    the required and optional tuples in hand; it just was not saying them.  Measured
    2026-08-19: an author hit `unknown_field` at `...emit.object.payload` and a human sitting
    beside them had to translate it into "object takes kind / entity / value / qualifiers".
    That translation is free -- it is two tuples one stack frame away.
    """
    names = [f"{name} (required)" for name in required] + list(optional)
    if not names:
        return "; no fields are allowed here"
    return "; allowed here: " + ", ".join(str(name) for name in names)


def _did_you_mean(wanted: Any, declared: Iterable[Any], label: str) -> str:
    """The half of an `unknown_*` refusal that says WHICH mistake this is.

    "unknown pack 'dt-job@1'" does not separate **you misspelled it** from **you have not
    written it yet**, and those two need opposite next actions -- fix a character, or go
    author a declaration.  Measured 2026-08-19: an author had a mapper emitting into a pack
    that did not exist yet and read the refusal as a typo.

    So the message answers the question it raised: nothing declared at all, a near miss to
    correct, or the declared names to choose from.
    """
    names = sorted({str(name) for name in declared})
    if not names:
        return f"; no {label} are declared yet"
    close = difflib.get_close_matches(str(wanted), names, n=3, cutoff=0.6)
    if close:
        return "; did you mean " + " or ".join(repr(name) for name in close) + "?"
    listed = ", ".join(repr(name) for name in names[:_CANDIDATE_LIMIT])
    if len(names) > _CANDIDATE_LIMIT:
        listed += f", +{len(names) - _CANDIDATE_LIMIT} more"
    return f"; declared {label}: {listed}"


class _Problems:
    def __init__(self):
        self.items: list[LedgerSetupValidationError] = []

    def add(self, code: str, path: str, message: str) -> None:
        self.items.append(LedgerSetupValidationError(code, path, message))

    def exact(self, value: Any, path: str, *, required: Sequence[str],
              optional: Sequence[str] = ()) -> bool:
        if not isinstance(value, Mapping):
            self.add("invalid_type", path, "must be an object")
            return False
        allowed = set(required) | set(optional)
        for name in sorted(set(value) - allowed, key=str):
            key_path = _path(path, str(name))
            code = ("unsafe_declaration"
                    if str(name).lower() in _FORBIDDEN_DECLARATION_KEYS
                    else "unknown_field")
            self.add(code, key_path, _RETIRED_FIELD_HELP.get(
                key_path, "field is not allowed" + _allowed_note(required, optional)))
        for name in required:
            if name not in value:
                self.add("missing_field", _path(path, name), "field is required")
        return True

    def finish(self) -> tuple[LedgerSetupValidationError, ...]:
        return tuple(sorted(
            self.items, key=lambda issue: (issue.path, issue.code, issue.message)))


def public_bundle_schema() -> dict[str, Any]:
    """Small public contract; no runtime registry or implementation details."""
    return {
        "setup_version": SETUP_VERSION,
        "config_file": CONFIG_FILENAME,
        "logical_fields": ["setup_version", *LOGICAL_SECTIONS],
        "optional_fields": list(OPTIONAL_SECTIONS),
        # Where the physical half of the setup is authored.  Published so a screen can
        # SAY which file to open instead of leaving the operator to discover that
        # `tables` is no longer here.
        "physical_schema_file": PHYSICAL_CATALOG_FILENAME,
        "binding_kinds": ["column", "constant", "entity"],
        "binding_origin": sorted(_BINDING_ORIGINS),
        "approval_status": sorted(_APPROVAL_STATUSES),
        # `tables` joins the list: naming it here is what turns "I pasted my old section
        # back in" from a silent no-op into `unknown_field` at `ledger_config.tables`.
        # `source_preparers` and `mappers` join it for the same reason on 2026-08-20 --
        # they retired into the source, and every config written before that day
        # still has them.  `profiles` joins them the same evening.  (Where inside the
        # source they landed changed once more on 2026-08-21: `driver` split into
        # `read`/`prepare`/`map` and the profile body became `bind`.)  `packs` joins the
        # list later the same day for the same reason: every config written before it went
        # still carries one, and a pasted-back section must say so by name.
        "forbidden_sections": ["frames", "lookups", "positions",
                               "manifest", "chains", "enrichments", "tables",
                               "source_preparers", "mappers", "profiles", "packs"],
    }


def role_binding_kinds(role: Mapping[str, Any]) -> tuple[str, ...]:
    """Resolve one validated Role's effective binding kinds from the Role contract."""
    if not isinstance(role, Mapping):
        raise TypeError("role must be a mapping")
    declared = role.get("allowed_binding_kinds")
    if _is_list(declared):
        return tuple(declared)
    return _default_binding_kinds(role.get("kind"))


#: The two Roles every predicate has, whatever it says about its object, and the one Role
#: an object contributes.  They are CONSTANTS because the vocabulary does not name them:
#: `subjects` says which entity TYPES may fill the subject, never what the slot is called,
#: so a per-predicate spelling would be a free choice with nothing to check it against.
SUBJECT_ROLE = "subject"
OCCURRED_AT_ROLE = "occurred_at"
TARGET_ROLE = "target"
VALUE_ROLE = "value"

#: `object.kind` -> the Role kind that carries the object, for the two kinds that carry one
#: in a Role rather than in an entity reference.  `value` is `quantity` because that is what
#: the only live value predicate (`has_netdie@1`) declared while a Claim still said so.
_OBJECT_VALUE_ROLE_KINDS = {"value": "quantity", "event_ref": "identity"}


def predicate_claim(predicate_id: str, predicate: Any) -> dict[str, Any]:
    """The Roles and the emission ONE predicate forces -- the Claim, with nobody to say it.

    🔴 THIS FUNCTION IS WHAT `packs` USED TO BE (owner, 2026-08-21: 「packs 도 아예 삭제
    가능하네. claims 도 필요없고. 그냥 맵퍼가 say 한 문장 id 에 vocab 만 달아주면 되는 거
    아님?」).  Measured before removing the section: of the five predicates in the live
    config, ZERO were used with two different Role sets, every qualifier name in a Claim's
    `roles` matched its predicate's `object.qualifiers` character for character, and five
    of six `emit` clauses were `$subject`/`$occurred_at` verbatim.  The sixth spelled its
    endpoints `$child`/`$parent`, which is why the same round renamed them: a Claim that
    only restates its predicate is a copy, and a copy that MAY differ is a defect waiting
    for the day someone edits one side.

    Returns the shape `packs.<pack>.claims.<claim>` had, so the compiler, the validator and
    the authoring plan all read one derivation instead of three agreeing ones.

    Tolerant of a half-written predicate on purpose: `config_authoring` runs this over
    bundles that do not validate yet, and a screen that raises tells an author nothing.
    """
    obj = predicate.get("object") if isinstance(predicate, Mapping) else None
    obj = obj if isinstance(obj, Mapping) else {}
    object_kind = obj.get("kind")
    qualifiers = obj.get("qualifiers") if isinstance(obj.get("qualifiers"), Mapping) else {}
    required_qualifiers = _column_values(qualifiers.get("required"))
    optional_qualifiers = _column_values(qualifiers.get("optional"))

    roles: dict[str, Any] = {
        SUBJECT_ROLE: {"kind": "entity", "required": True},
        OCCURRED_AT_ROLE: {"kind": "time", "required": True},
    }
    emit_object: dict[str, Any] = {"kind": object_kind}
    if object_kind == "entity_ref":
        roles[TARGET_ROLE] = {"kind": "entity", "required": True}
        emit_object["entity"] = f"${TARGET_ROLE}"
    elif object_kind in _OBJECT_VALUE_ROLE_KINDS:
        roles[VALUE_ROLE] = {
            "kind": _OBJECT_VALUE_ROLE_KINDS[object_kind], "required": True}
        emit_object["value"] = f"${VALUE_ROLE}"
    if object_kind != "none":
        emit_object["qualifiers"] = {
            **{name: f"${name}" for name in required_qualifiers},
            **{name: f"${name}?" for name in optional_qualifiers},
        }
    for name in required_qualifiers:
        roles[name] = {"kind": "attribute", "required": True}
    for name in optional_qualifiers:
        roles.setdefault(name, {"kind": "attribute", "required": False})
    return {
        "roles": roles,
        "emit": {
            "predicate": predicate_id,
            "subject": f"${SUBJECT_ROLE}",
            "object": emit_object,
            "occurred_at": f"${OCCURRED_AT_ROLE}",
        },
    }


def validate_bundle(value: Mapping[str, Any], *,
                    catalog: Mapping[str, Any] | None = None) -> LedgerSetupBundle:
    issues = validate_bundle_errors(value, catalog=catalog)
    if issues:
        raise issues[0]
    filled = {name: {} for name in OPTIONAL_SECTIONS if name not in value} | dict(value)
    normalized = _normalize(filled)
    return LedgerSetupBundle(_freeze(normalized))


def validate_bundle_errors(value: Mapping[str, Any], *,
                           catalog: Mapping[str, Any] | None = None
                           ) -> tuple[LedgerSetupValidationError, ...]:
    """Every structural and cross-section issue in one pass.

    `catalog` is the physical relation shape from `table_config.json`, and it is
    REQUIRED -- omitting it refuses by name rather than defaulting.  Two reasons, and the
    second is the one that cost something:

    * A default would make this function read a file off disk, and this module's whole
      job is to be the pure authoring boundary.
    * A silently-defaulted catalog is how a bundle comes to be validated against one
      world and compiled against another.  When the answer to "does this column exist"
      can come from a source the caller did not name, nobody can tell which answer they
      got.  The refusal names the fix.

    It is a parameter for the same reason `trusted_implementations()` and
    `verified_joins` are parameters on `compile_setup_snapshot`: the caller states which
    world it is judging against.  Production resolves it once, in `ledger.setup`.
    """
    problems = _Problems()
    if catalog is None:
        return (LedgerSetupValidationError(
            "physical_catalog_required", PHYSICAL_CATALOG_FILENAME,
            f"validation needs the physical relation shape; pass "
            f"catalog=ledger.setup.live_physical_catalog() or an explicit "
            f"load_physical_catalog(<path to {PHYSICAL_CATALOG_FILENAME}>)"),)
    if not problems.exact(
            value, "bundle", required=("setup_version", *LOGICAL_SECTIONS),
            optional=OPTIONAL_SECTIONS):
        return problems.finish()
    if value.get("setup_version") != SETUP_VERSION:
        problems.add(
            "unsupported_setup_version", "bundle.setup_version",
            f"supported setup_version is {SETUP_VERSION}")
    for section in ALL_SECTIONS:
        if section in value and not isinstance(value[section], Mapping):
            problems.add("invalid_type", f"bundle.{section}", "must be an object")
    # An omitted optional section is the same bundle as an empty one, resolved ONCE here
    # so every reader below -- and the compiler after it -- sees one shape. Leaving the
    # key absent for later code to `.get()` around is how two readers come to disagree
    # about whether "no joins" and "no joins section" are the same thing.
    value = {name: {} for name in OPTIONAL_SECTIONS if name not in value} | dict(value)

    if isinstance(value.get("virtual_joins"), Mapping):
        _validate_virtual_joins(value["virtual_joins"], problems)
    if isinstance(value.get("vocabulary"), Mapping):
        _validate_vocabulary(value["vocabulary"], problems)
    if isinstance(value.get("entities"), Mapping):
        _validate_entities(value["entities"], problems)
    if isinstance(value.get("sources"), Mapping):
        _validate_sources(value["sources"], problems)

    # Cross-validation only consumes structurally sound descriptors.  This makes every
    # malformed JSON shape a stable validation result instead of an AttributeError or
    # TypeError from a later semantic lookup.
    if problems.items:
        return problems.finish()
    if all(isinstance(value.get(name), Mapping) for name in ALL_SECTIONS):
        _cross_validate(value, catalog, problems)
    return problems.finish()


def bundle_readiness_errors(bundle: LedgerSetupBundle
                            ) -> tuple[LedgerSetupValidationError, ...]:
    if not isinstance(bundle, LedgerSetupBundle):
        raise TypeError("readiness requires a validated LedgerSetupBundle")
    problems = _Problems()
    for source_id, source in bundle.section("sources").items():
        profile = source["bind"]
        for sentence, mapping in sorted(profile["mappings"].items()):
            base = f"bundle.sources.{source_id}.bind.mappings.{sentence}.bind"
            for role in sorted(mapping["bind"]):
                _binding_readiness(mapping["bind"][role], f"{base}.{role}", problems)
    return problems.finish()


def require_ready_bundle(bundle: LedgerSetupBundle) -> LedgerSetupBundle:
    issues = bundle_readiness_errors(bundle)
    if issues:
        raise issues[0]
    return bundle


def load_setup_bundle(root: str | Path, *, config_name: str = CONFIG_FILENAME,
                      catalog: Mapping[str, Any] | None = None
                      ) -> LedgerSetupBundle:
    """Load the ONE authoring file under ``root``.

    This replaced a manifest naming five files across three directories.  The manifest
    existed to enumerate them; with one file there is nothing to enumerate, and
    `setup_version` alone states the grammar generation that five `schema_version` fields
    used to state five times.

    🔴 THE "NO OTHER JSON" REFUSAL IS THE SINGLE-FILE PROMISE, NOT TIDINESS.
    The old loader refused a JSON file the manifest did not list, so a stray file could
    never be silently half-read.  The same refusal is what now makes "open one file and you
    have seen everything" true: a leftover `catalog/tables.json` beside the new file would
    otherwise sit there looking authoritative while nothing read it.  A converted root that
    still contains the originals is therefore refused BY NAME, which is exactly the state
    the converter leaves behind on purpose.

    ⚠️ "ONE FILE" IS ABOUT THE SEMANTIC SETUP, NOT THE PHYSICAL SCHEMA.  The physical half
    is `table_config.json`, which sits in the config root -- OUTSIDE this directory, and so
    outside the refusal above -- because ingestion, the chain workers and the grid author
    it too.  It is not a second setup file to keep in step; it is the file the ledger
    stopped copying.  `catalog` overrides which one is read; see `validate_bundle_errors`.
    """
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise LedgerSetupValidationError(
            "invalid_config_root", "config_root", "must be a directory")
    config_path = _resolve_config_path(
        root_path, config_name, "config_root", require_json=True)
    extras = sorted(
        path.resolve() for path in root_path.rglob("*.json")
        if path.resolve() != config_path)
    if extras:
        relative = extras[0].relative_to(root_path).as_posix()
        # 🔴 The "move it outside" clause is not politeness. `rglob` RECURSES, so keeping
        # the retired files in a backup folder INSIDE the root still trips this -- and
        # keeping the originals beside the new file is exactly what a careful operator
        # does. Without the clause the message says what tripped but not what to do, so
        # the refusal lands hardest on the most cautious reader. Measured: this is how it
        # first fired in practice.
        raise LedgerSetupValidationError(
            "unlisted_config_file", f"config_root.{relative}",
            f"the setup is one file ({config_name}); this root also contains "
            f"{relative!r} — move it outside the config root")

    document = _read_json(config_path, "ledger_config")
    issues = _root_document_errors(document)
    if issues:
        raise issues[0]
    return validate_bundle(document, catalog=catalog)


def _root_document_errors(document: Mapping[str, Any]
                          ) -> tuple[LedgerSetupValidationError, ...]:
    problems = _Problems()
    if problems.exact(
            document, "ledger_config",
            required=("setup_version", *LOGICAL_SECTIONS),
            optional=OPTIONAL_SECTIONS):
        if document.get("setup_version") != SETUP_VERSION:
            problems.add(
                "unsupported_setup_version", "ledger_config.setup_version",
                f"supported setup_version is {SETUP_VERSION}")
    return problems.finish()


def setup_bundle_errors(root: str | Path, *, config_name: str = CONFIG_FILENAME,
                        catalog: Mapping[str, Any] | None = None
                        ) -> tuple[LedgerSetupValidationError, ...]:
    """EVERY problem in one root, for the AUTHORING path.

    🔴 THIS IS NOT A REPLACEMENT FOR `load_setup_bundle`, AND THE TWO MUST NOT BE MERGED.
    A source about to write atoms should still stop at the first refusal -- there is no
    value in enumerating faults in a config that is about to be refused anyway, and every
    later check would be reading a bundle the earlier one already declared broken.  It is
    AUTHORING that needs the whole list: measured 2026-08-19, an author hand-writing a
    second source spent five save-and-run cycles discovering five problems that were all
    present in the first save.

    Everything here is read-only and nothing is compiled: the file is read, the root shape
    is checked, and the cross-section validator -- which already returns a list -- is asked
    for all of it.  I/O-shaped refusals (unreadable file, invalid JSON, a stray second JSON
    file) still RAISE, because there is no second problem to find in a file that could not
    be parsed.
    """
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise LedgerSetupValidationError(
            "invalid_config_root", "config_root", "must be a directory")
    config_path = _resolve_config_path(
        root_path, config_name, "config_root", require_json=True)
    document = _read_json(config_path, "ledger_config")
    root_issues = _root_document_errors(document)
    if root_issues:
        # The section-level validator would read sections this one just called absent or
        # misspelled, and report a second wave of consequences rather than causes.
        return root_issues
    return validate_bundle_errors(document, catalog=catalog)


def _resolve_config_path(root: Path, relative: Any, path: str, *, require_json: bool) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "must be a non-blank relative path")
    if relative != relative.strip() or "\\" in relative or any(c in relative for c in "*?[]"):
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "must be a canonical relative path without glob syntax")
    candidate = Path(relative)
    if candidate.is_absolute() or ":" in relative or any(part in ("", ".", "..")
                                                          for part in candidate.parts):
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "path must stay below the config root")
    if require_json and candidate.suffix.lower() != ".json":
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "config path must end in .json")
    try:
        resolved = (root / candidate).resolve(strict=True)
    except FileNotFoundError as exc:
        raise LedgerSetupValidationError("missing_config_file", path,
                                         f"file {relative!r} does not exist") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise LedgerSetupValidationError("unsafe_config_path", path,
                                         "resolved path escapes config root") from exc
    if not resolved.is_file():
        raise LedgerSetupValidationError("missing_config_file", path,
                                         "config path must name a file")
    return resolved


def _versioned_id(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, str) or not _VERSIONED_ID.fullmatch(value):
        problems.add("invalid_versioned_id", path, "must use nonblank-id@positive-version")


def _role_ref(value: Any, path: str, problems: _Problems, *, optional: bool = False) -> None:
    if not isinstance(value, str) or not value.startswith("$"):
        problems.add("invalid_role_ref", path, "must be a $role reference")
        return
    body = value[1:]
    if body.endswith("?"):
        body = body[:-1]
    elif optional:
        problems.add("invalid_role_ref", path, "optional qualifier must use $role?")
    if not body or any(char.isspace() for char in body):
        problems.add("invalid_role_ref", path, "role reference must not be blank")


def _nonblank_id(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        problems.add("invalid_id", path, "ID must be a non-blank trimmed string")


def _deterministic_json(value: Any, path: str, problems: _Problems) -> None:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            if not isinstance(key, str):
                problems.add("invalid_binding", path,
                             "constant object keys must be strings")
                return
            _deterministic_json(value[key], f"{path}.{key}", problems)
        return
    if _is_list(value):
        for index, item in enumerate(value):
            _deterministic_json(item, f"{path}[{index}]", problems)
        return
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        try:
            json.dumps(value, allow_nan=False)
        except ValueError:
            problems.add("invalid_binding", path,
                         "constant must be finite deterministic JSON")
        return
    problems.add("invalid_binding", path, "constant must be deterministic JSON")


def _nonblank_text(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, str) or not value.strip():
        problems.add("blank_value", path, "must be a non-blank string")


def _occurred_at_origin(occurred: Mapping, path: str, problems: _Problems) -> None:
    """A source says WHERE its time came from - a world column, or an admitted basis.

    Before this, every source had to name a column. A table with no time column could only
    be declared by pointing at something that is not a time, or by pinning a constant into
    the profile - both of which produce atoms that READ as world time and cannot be told
    apart afterwards. Declaring the absence is the honest form, so exactly one of the two
    must be present: naming both would leave the reader guessing which one won.
    """
    has_column = "column" in occurred
    has_basis = "basis" in occurred
    if has_column == has_basis:
        both = "both" if has_column else "neither"
        problems.add(
            "invalid_driver", path,
            f"declare exactly one of 'column' (the table carries world time) or 'basis' "
            f"(it does not - one of {sorted(_OCCURRED_AT_BASES)}); {both} was declared")
        return
    if has_column:
        _nonblank_text(occurred.get("column"), f"{path}.column", problems)
        return
    basis = occurred.get("basis")
    if not isinstance(basis, str) or basis not in _OCCURRED_AT_BASES:
        problems.add(
            "invalid_driver", f"{path}.basis",
            f"must be one of {sorted(_OCCURRED_AT_BASES)}, got {basis!r}")


def _nonblank_list(value: Any, path: str, problems: _Problems,
                   *, allow_empty: bool = False, item_form: str | None = None) -> None:
    """`item_form` is the item's SPELLING, for lists whose items are references.

    "must be a list with at least one item" tells an author the container is wrong and
    leaves them to guess the contents.  Optional because most lists here are plain names
    and have nothing extra to say.
    """
    if not _is_list(value) or (not value and not allow_empty):
        problems.add("invalid_type", path,
                     "must be a list" + ("" if allow_empty else " with at least one item")
                     + (f"; each item is {item_form}" if item_form else ""))
        return
    for index, item in enumerate(value):
        _nonblank_text(item, f"{path}[{index}]", problems)
    if _has_duplicate_strings(value):
        problems.add("duplicate_id", path, "list values must be unique")


def _column_list_or_text(value: Any, path: str, problems: _Problems) -> None:
    if isinstance(value, str):
        _nonblank_text(value, path, problems)
    else:
        _nonblank_list(value, path, problems)


def _column_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if _is_list(value):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _has_duplicate_strings(value: Any) -> bool:
    strings = _column_values(value)
    return len(strings) != len(set(strings))


def _is_list(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _path(base: str, child: str) -> str:
    return f"{base}.{child}" if base else child


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if _is_list(value):
        return [_normalize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value {value!r} is not deterministic JSON")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _validate_virtual_joins(section: Mapping[str, Any], problems: _Problems) -> None:
    for rule_id in sorted(section, key=str):
        path = f"bundle.virtual_joins.{rule_id}"
        _nonblank_id(rule_id, path, problems)
        rule = section[rule_id]
        if not problems.exact(
                rule, path,
                required=("left_table", "right_table", "join_key", "expose",
                          "join_cardinality", "enabled"),
                optional=("fold",)):
            continue
        for field in ("left_table", "right_table"):
            _nonblank_text(rule.get(field), f"{path}.{field}", problems)
        pairs = rule.get("join_key")
        if not _is_list(pairs) or not pairs:
            problems.add("invalid_join", f"{path}.join_key", "must be a non-empty list")
        else:
            for index, pair in enumerate(pairs):
                ppath = f"{path}.join_key[{index}]"
                if problems.exact(pair, ppath, required=("left", "right")):
                    _nonblank_text(pair.get("left"), f"{ppath}.left", problems)
                    _nonblank_text(pair.get("right"), f"{ppath}.right", problems)
        _nonblank_list(rule.get("expose"), f"{path}.expose", problems)
        if rule.get("join_cardinality") != "one":
            problems.add(
                "invalid_join", f"{path}.join_cardinality",
                "Ledger v2 requires join_cardinality 'one'")
        if not isinstance(rule.get("enabled"), bool):
            problems.add("invalid_type", f"{path}.enabled", "must be boolean")
        if "fold" in rule:
            _validate_join_fold(rule.get("fold"), f"{path}.fold", problems)


def _validate_join_fold(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, Mapping):
        problems.add("invalid_join", path, "must be an object of notation rule toggles")
        return
    _scan_unsafe_keys(value, path, problems)
    for name in sorted(value, key=str):
        rule_path = f"{path}.{name}"
        if str(name).lower() in _FORBIDDEN_EXECUTABLE_KEYS:
            continue
        if name not in _JOIN_FOLD_RULES:
            problems.add(
                "invalid_join", rule_path,
                f"unknown notation rule {name!r}; known rules are "
                f"{sorted(_JOIN_FOLD_RULES)}")
            continue
        enabled = value[name]
        if not isinstance(enabled, bool):
            problems.add("invalid_type", rule_path, "notation rule toggle must be boolean")
        elif enabled and name not in _IMPLEMENTED_JOIN_FOLD_RULES:
            problems.add(
                "invalid_join", rule_path,
                f"notation rule {name!r} is not implemented")


def _validate_vocabulary(section: Mapping[str, Any], problems: _Problems) -> None:
    for predicate_id in sorted(section, key=str):
        path = f"bundle.vocabulary.{predicate_id}"
        _versioned_id(predicate_id, path, problems)
        item = section[predicate_id]
        if not problems.exact(
                item, path, required=("status", "subjects", "object")):
            continue
        if item.get("status") not in ("active", "retired"):
            problems.add("invalid_predicate", f"{path}.status", "must be active or retired")
        _nonblank_list(item.get("subjects"), f"{path}.subjects", problems)
        obj = item.get("object")
        if problems.exact(
                obj, f"{path}.object", required=("kind", "qualifiers"),
                optional=("types",)):
            kind = obj.get("kind")
            if not isinstance(kind, str) or kind not in _OBJECT_KINDS:
                problems.add("invalid_predicate", f"{path}.object.kind",
                             f"must be one of {sorted(_OBJECT_KINDS)}")
            if kind == "entity_ref":
                if "types" not in obj:
                    problems.add("missing_field", f"{path}.object.types",
                                 "entity_ref object requires types")
                else:
                    _nonblank_list(obj["types"], f"{path}.object.types", problems)
            elif "types" in obj:
                problems.add("invalid_predicate", f"{path}.object.types",
                             f"{kind!r} object must not declare entity types")
            qualifiers = obj.get("qualifiers")
            qpath = f"{path}.object.qualifiers"
            if problems.exact(
                    qualifiers, qpath, required=("required", "optional")):
                required = qualifiers.get("required")
                optional = qualifiers.get("optional")
                _nonblank_list(required, f"{qpath}.required", problems, allow_empty=True)
                _nonblank_list(optional, f"{qpath}.optional", problems, allow_empty=True)
                overlap = sorted(set(_column_values(required)) &
                                 set(_column_values(optional)))
                if overlap:
                    problems.add(
                        "invalid_predicate", qpath,
                        f"qualifier names must not be both required and optional: {overlap!r}")
                if (kind == "none"
                        and (_column_values(required) or _column_values(optional))):
                    problems.add(
                        "invalid_predicate", qpath,
                        "none object cannot declare payload qualifiers")


def _validate_entities(section: Mapping[str, Any], problems: _Problems) -> None:
    for entity_id in sorted(section, key=str):
        path = f"bundle.entities.{entity_id}"
        _versioned_id(entity_id, path, problems)
        item = section[entity_id]
        if not problems.exact(
                item, path, required=("keys",), optional=("key_types", "allow_null")):
            continue
        keys = item.get("keys")
        _nonblank_list(keys, f"{path}.keys", problems)
        if _has_duplicate_strings(keys):
            problems.add("duplicate_id", f"{path}.keys", "identity keys must be unique")
        if "key_types" in item:
            if not isinstance(item["key_types"], Mapping):
                problems.add("invalid_type", f"{path}.key_types", "must be an object")
            else:
                if (_is_list(keys)
                        and set(item["key_types"]) != set(_column_values(keys))):
                    problems.add("invalid_entity_ref", f"{path}.key_types",
                                 "key_types must name exactly the identity keys")
                for key in sorted(item["key_types"], key=str):
                    value = item["key_types"][key]
                    if (not isinstance(value, str) or not value.strip()
                            or value != value.strip()):
                        problems.add(
                            "invalid_type", f"{path}.key_types.{key}",
                            "key type must be a non-blank trimmed string")
        if "allow_null" in item and not isinstance(item["allow_null"], bool):
            problems.add("invalid_type", f"{path}.allow_null", "must be boolean")


def _validate_preparation(item: Any, path: str, problems: _Problems) -> None:
    """One source's preparer body, at `sources.<id>.prepare`.

    No `_versioned_id` here and no id at all: the declaration is not named any more, it IS
    the source's preparation clause.  `implementation_id`/`implementation_version` stay,
    because the thing that is shared and versioned is the CODE the body selects, never the
    body itself.
    """
    if not problems.exact(
            item, path,
            required=("implementation_id", "implementation_version", "input_columns",
                      "output_columns", "accepts_verified_join_rules",
                      "inherit_virtual_join_rules")):
        return
    _implementation(item, path, problems)
    _nonblank_list(item.get("input_columns"), f"{path}.input_columns", problems,
                   allow_empty=True)
    _column_types(item.get("output_columns"), f"{path}.output_columns", problems)
    _nonblank_list(item.get("inherit_virtual_join_rules"),
                   f"{path}.inherit_virtual_join_rules", problems, allow_empty=True)
    inputs = set(_column_values(item.get("input_columns")))
    outputs = item.get("output_columns")
    if isinstance(outputs, Mapping):
        for column in sorted(set(outputs) & inputs):
            problems.add(
                "output_column_collision", f"{path}.output_columns.{column}",
                "preparer output must not overwrite an input column")
    if not isinstance(item.get("accepts_verified_join_rules"), bool):
        problems.add("invalid_type", f"{path}.accepts_verified_join_rules",
                     "must be boolean")


def _validate_mapper(item: Any, path: str, problems: _Problems) -> None:
    """One source's mapper body, at `sources.<id>.map`.

    🔴 NO `emits`, AND ITS ABSENCE IS THE POINT (owner, 2026-08-20: 「클레임과 맵퍼 함수는
    완전 별개인데 왜 맵퍼에서 쓸 클레임을 정의함?」 -> 「닿을 수 없다면 선언도 닿으면 안됨」).
    A mapper implementation knows `SentenceShape`, never a `claim`; "which claims can this
    mapper produce" is a question it has no way to answer, and the one declaration that can
    is `bind.mappings.<sentence>.use`.  So the field is not moved, it is gone: `MapperDescriptor.emits`
    is now DERIVED from those same `use` values, which is why the two could never disagree
    and why the rule that compared them is not written here any more.
    """
    if not problems.exact(
            item, path,
            required=("implementation_id", "implementation_version", "unit",
                      "input_columns")):
        return
    _implementation(item, path, problems)
    if problems.exact(
            item.get("unit"), f"{path}.unit", required=("kind",),
            optional=("columns",)):
        kind = item["unit"].get("kind")
        if not isinstance(kind, str) or kind not in _MAPPER_UNITS:
            problems.add("invalid_mapper", f"{path}.unit.kind",
                         f"must be one of {sorted(_MAPPER_UNITS)}")
        columns = item["unit"].get("columns")
        if kind == "group_by":
            if columns is None:
                problems.add(
                    "missing_field", f"{path}.unit.columns",
                    "group_by mapper unit requires columns")
            else:
                _nonblank_list(columns, f"{path}.unit.columns", problems)
                if (_is_list(columns)
                        and isinstance(item.get("input_columns"), list)):
                    missing = sorted(set(_column_values(columns))
                                     - set(_column_values(item["input_columns"])))
                    if missing:
                        problems.add(
                            "invalid_mapper", f"{path}.unit.columns",
                            f"group_by columns must be mapper input columns: {missing}")
        elif columns is not None:
            problems.add(
                "invalid_mapper", f"{path}.unit.columns",
                "unit.columns is only valid for group_by")
    _nonblank_list(item.get("input_columns"), f"{path}.input_columns", problems,
                   allow_empty=True)


def _validate_profile(profile: Any, path: str, problems: _Problems) -> None:
    """One source's bind clause, at `sources.<id>.bind`.

    No `_versioned_id` here and no id at all -- the same retirement `_validate_preparation`
    took earlier the same day.  `source` is gone with the section for a sharper reason than
    tidiness: it was a REPEAT of the key one level up, and `_cross_validate` refused every
    value except that key, so the only thing an author could do with the field was get it
    wrong.

    🔴 `packs` WENT THE SAME WAY on 2026-08-21, for the third time in the same file.  It was
    `sorted(set(...))` of the packs the mappings' `use` names, checked for equality in BOTH
    directions -- an author could not write it better, only wrong.

    🔴 AND `use` BECAME `predicate` THE SAME DAY, when the `packs` SECTION went too.  A
    mapping named a Claim that named a predicate; it names the predicate.  The value is a
    versioned vocabulary id, not a `<pack>/<claim>` pair, so the pattern that parsed one
    left with the section.

    🔴 AND IT STAYS A RECORD WITH ONE FIELD (owner: 「ㅇㅇ 남겨」).  `bind: [...]` would read
    the same today and would have to be unfolded -- with a migration -- the first time
    `bind` carries anything besides `mappings`.
    """
    if not problems.exact(profile, path, required=("mappings",)):
        return
    mappings = profile.get("mappings")
    if not isinstance(mappings, Mapping) or not mappings:
        problems.add("invalid_profile", f"{path}.mappings",
                     "must be a non-empty object keyed by sentence")
        return
    for sentence in sorted(mappings, key=str):
        mapping = mappings[sentence]
        mpath = f"{path}.mappings.{sentence}"
        _nonblank_id(sentence, mpath, problems)
        if not problems.exact(mapping, mpath, required=("predicate", "bind")):
            continue
        _versioned_id(mapping.get("predicate"), f"{mpath}.predicate", problems)
        bindings = mapping.get("bind")
        if not isinstance(bindings, Mapping) or not bindings:
            problems.add("invalid_profile", f"{mpath}.bind", "must be non-empty")
        else:
            for role in sorted(bindings):
                _nonblank_id(role, f"{mpath}.bind.{role}", problems)
                _validate_binding(bindings[role], f"{mpath}.bind.{role}", problems)


def _validate_binding(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, Mapping):
        problems.add("invalid_binding", path, "binding must be an object")
        return
    kind = value.get("kind")
    if kind == "column":
        allowed = ("kind", "column", "binding_origin", "approval_status", "suggestion_reason")
        required = ("kind", "column", "approval_status")
    elif kind == "constant":
        allowed = ("kind", "value", "binding_origin", "approval_status", "suggestion_reason")
        required = ("kind", "value", "approval_status")
    elif kind == "entity":
        allowed = ("kind", "entity_type", "keys", "binding_origin", "approval_status",
                   "suggestion_reason")
        required = ("kind", "entity_type", "keys", "approval_status")
    else:
        problems.add("invalid_binding", f"{path}.kind",
                     f"unsupported binding kind {kind!r}")
        return
    problems.exact(value, path, required=required,
                   optional=tuple(name for name in allowed if name not in required))
    if kind == "column":
        _nonblank_text(value.get("column"), f"{path}.column", problems)
    elif kind == "constant" and "value" in value:
        _deterministic_json(value["value"], f"{path}.value", problems)
    elif kind == "entity":
        _versioned_id(value.get("entity_type"), f"{path}.entity_type", problems)
        keys = value.get("keys")
        if not isinstance(keys, Mapping) or not keys:
            problems.add("invalid_entity_ref", f"{path}.keys", "must be non-empty")
        else:
            for key in sorted(keys):
                _nonblank_id(key, f"{path}.keys.{key}", problems)
                _validate_binding(keys[key], f"{path}.keys.{key}", problems)
                if isinstance(keys[key], Mapping) and keys[key].get("kind") == "entity":
                    problems.add(
                        "invalid_binding", f"{path}.keys.{key}.kind",
                        "entity identity keys allow only column or constant bindings")
    origin = value.get("binding_origin", _DEFAULT_BINDING_ORIGIN)
    approval = value.get("approval_status")
    if not isinstance(origin, str) or origin not in _BINDING_ORIGINS:
        problems.add("invalid_binding", f"{path}.binding_origin",
                     f"must be one of {sorted(_BINDING_ORIGINS)}")
    if not isinstance(approval, str) or approval not in _APPROVAL_STATUSES:
        problems.add("invalid_binding", f"{path}.approval_status",
                     f"must be one of {sorted(_APPROVAL_STATUSES)}")
    reason = value.get("suggestion_reason")
    if origin == "system_suggested" and not isinstance(reason, str):
        problems.add("invalid_binding", f"{path}.suggestion_reason",
                     "system_suggested binding requires suggestion_reason")
    elif origin == "system_suggested" and not reason.strip():
        problems.add("invalid_binding", f"{path}.suggestion_reason",
                     "system_suggested binding requires non-blank suggestion_reason")
    elif reason is not None and (not isinstance(reason, str) or not reason.strip()):
        problems.add("invalid_binding", f"{path}.suggestion_reason",
                     "suggestion_reason must be non-blank when present")


def _validate_sources(section: Mapping[str, Any], problems: _Problems) -> None:
    """Every source, in the order it RUNS.

    🔴 `driver` NAMED TWO JOBS AT ONCE AND IS GONE (owner, 2026-08-20: 「애초에 지금 컨피그
    스키마가 잘못돼 있는건데」).  Reading a physical batch and turning it into sentences are
    different steps with different column universes, and both sat under one key -- which is
    how the question "where does a preparer go" cost a round the day before.  The four
    clauses now stand as SIBLINGS of `relation`, and the file reads in the order execution
    happens:

        relation   the physical table this source reads.  UNMOVED -- `prepared_columns`
                   starts from it, and moving it would drag that with it for nothing
        read       unit, identity, group_by, order_by, occurred_at, cursor, probe
        prepare    the preparer body, character for character as it was
        map        the mapper body, character for character as it was
        bind       the profile body, character for character as it was

    The file itself is written `sort_keys=True`, so on disk these sit `bind · map · prepare
    · read`.  That is deliberate and is not fixed here: the serialization is canonical hash
    material, and the ORDER A READER SEES is made by the skeleton, which lists them in the
    order above.
    """
    for source_id in sorted(section, key=str):
        path = f"bundle.sources.{source_id}"
        _nonblank_id(source_id, path, problems)
        source = section[source_id]
        if not problems.exact(
                source, path, required=("relation", "read", "prepare", "map", "bind")):
            continue
        _nonblank_text(source.get("relation"), f"{path}.relation", problems)
        # Each clause is judged on its own: one malformed clause must not silence the
        # other three, or an author fixes four rounds of one refusal at a time.
        _validate_profile(source.get("bind"), f"{path}.bind", problems)
        _validate_preparation(source.get("prepare"), f"{path}.prepare", problems)
        _validate_mapper(source.get("map"), f"{path}.map", problems)
        read = source.get("read")
        if not problems.exact(
                read, f"{path}.read",
                required=("unit", "identity", "group_by", "order_by", "occurred_at",
                          "cursor"),
                optional=("registration_probe",)):
            continue
        _validate_registration_probe(
            read.get("registration_probe"), f"{path}.read.registration_probe",
            problems)
        source_unit = read.get("unit")
        if not isinstance(source_unit, str) or source_unit not in _SOURCE_UNITS:
            problems.add("invalid_driver", f"{path}.read.unit",
                         f"must be one of {sorted(_SOURCE_UNITS)}")
        for field in ("identity", "group_by", "order_by"):
            _nonblank_list(read.get(field), f"{path}.read.{field}", problems,
                           allow_empty=(field == "group_by"))
        group_by = read.get("group_by")
        identity = read.get("identity")
        if source_unit == "row" and _is_list(group_by) and group_by:
            problems.add("invalid_driver", f"{path}.read.group_by",
                         "row unit requires an empty group_by list")
        if source_unit == "group" and _is_list(group_by) and not group_by:
            problems.add("invalid_driver", f"{path}.read.group_by",
                         "group unit requires at least one group_by column")
        if (_is_list(group_by) and _is_list(identity)
                and any(isinstance(column, str) and column not in identity
                        for column in group_by)):
            problems.add("invalid_driver", f"{path}.read.group_by",
                         "group_by columns must be included in identity")
        occurred = read.get("occurred_at")
        if problems.exact(
                occurred, f"{path}.read.occurred_at",
                required=("timezone",), optional=("column", "basis")):
            _occurred_at_origin(occurred, f"{path}.read.occurred_at", problems)
            timezone = occurred.get("timezone")
            _nonblank_text(timezone, f"{path}.read.occurred_at.timezone", problems)
            if isinstance(timezone, str) and timezone.strip():
                try:
                    ZoneInfo(timezone)
                except ZoneInfoNotFoundError:
                    problems.add("invalid_timezone", f"{path}.read.occurred_at.timezone",
                                 f"unknown timezone {timezone!r}")
        cursor = read.get("cursor")
        if problems.exact(cursor, f"{path}.read.cursor", required=("columns",)):
            _nonblank_list(cursor.get("columns"), f"{path}.read.cursor.columns", problems)


def _validate_registration_probe(value: Any, path: str, problems: _Problems) -> None:
    """Which BASE columns can name an entity that might already be registered.

    🔴 WHY THIS IS A DECLARATION AND NOT AN INFERENCE.
    The driver asks the store, once per page, which of this batch's subjects already exist,
    so a `register` atom is emitted only on FIRST sight.  That question is asked BEFORE
    preparation, on physical column names, while the Profile binds POST-preparation logical
    names -- so the answer cannot be read off the bindings.  Until this declaration existed
    the driver hard-coded one source's column names, which is why exactly one source could
    run at all.

    🔴 THE DIRECTION OF ERROR IS NOT SYMMETRIC, AND THAT IS THE WHOLE SAFETY ARGUMENT.
    The probe result is used only to SUPPRESS a register atom for a subject already in the
    store.  Naming a column that contributes no subject is therefore free -- it yields
    candidates no atom mentions, and they match nothing.  MISSING a column is not free: a
    subject that is already registered goes unsuppressed and the batch emits a duplicate
    `register`.  So the declaration must be a SUPERSET of the subjects the atoms can
    mention, and over-declaring is the safe side to err on.

    `list_separator` exists because a column may carry a positional list of ids in one
    string.  Probing for the unsplit string would find none of them -- an
    under-approximation, the unsafe direction.  The retired grammar declared this as
    `list_separator` too; the current one had lost it into a hard-coded separator.
    """
    if value is None:
        return
    if not _is_list(value):
        problems.add("invalid_registration_probe", path, "must be a list")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not problems.exact(
                item, item_path, required=("entity_type", "columns"),
                optional=("list_separator",)):
            continue
        entity_type = item.get("entity_type")
        _versioned_id(entity_type, f"{item_path}.entity_type", problems)
        if isinstance(entity_type, str):
            if entity_type in seen:
                problems.add(
                    "duplicate_registration_probe", f"{item_path}.entity_type",
                    f"entity type {entity_type!r} is probed twice; merge the columns")
            seen.add(entity_type)
        _nonblank_list(item.get("columns"), f"{item_path}.columns", problems)
        if "list_separator" in item:
            separator = item.get("list_separator")
            if not isinstance(separator, str) or not separator:
                problems.add(
                    "invalid_registration_probe", f"{item_path}.list_separator",
                    "must be a non-empty string")


def _cross_registration_probe(value: Any, path: str, relation: Any,
                              physical: set[str], tables: Mapping[str, Any],
                              entities: Mapping[str, Any],
                              problems: _Problems) -> None:
    """The probed entity must exist, be single-keyed, and name real base columns."""
    if not _is_list(value):
        return
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            continue
        item_path = f"{path}[{index}]"
        entity_type = item.get("entity_type")
        entity = entities.get(entity_type) if isinstance(entity_type, str) else None
        if entity is None:
            problems.add(
                "unknown_entity_type", f"{item_path}.entity_type",
                f"entity type {entity_type!r} is not declared")
            continue
        keys = entity.get("keys")
        if _is_list(keys) and len(keys) != 1:
            # A composite-key entity needs one column per key part, and guessing which
            # declared column feeds which part is exactly the kind of inference this
            # declaration exists to remove. Refuse rather than probe a partial identity:
            # a partial probe under-approximates, which is the direction that duplicates
            # `register` atoms.
            problems.add(
                "unsupported_registration_probe", f"{item_path}.entity_type",
                f"entity type {entity_type!r} has {len(keys)} identity keys; the probe "
                f"supports single-keyed entities only")
            continue
        if isinstance(relation, str) and _is_list(item.get("columns")) and tables.get(relation):
            for column in item["columns"]:
                if isinstance(column, str) and column not in physical:
                    problems.add(
                        "unknown_column", f"{item_path}.columns",
                        f"{relation!r} has no column {column!r}")


def _cross_validate(bundle: Mapping[str, Any], catalog: Mapping[str, Any],
                    problems: _Problems) -> None:
    # The physical half of every cross-check below comes from `table_config.json`, not
    # from the ledger file.  The checks themselves are unchanged: what moved is WHO
    # ANSWERS "does this relation have this column, and is this ordering unique".
    tables = catalog
    entities = bundle["entities"]
    vocabulary = bundle["vocabulary"]
    sources = bundle["sources"]

    _cross_vocabulary(vocabulary, entities, problems)
    # `_cross_packs` stood here and checked a Claim against the predicate it emitted --
    # object kind agreement, every required qualifier present, no qualifier the predicate
    # does not allow, every `$role` endpoint declared with a compatible kind.  Every one of
    # those compared two declarations that `predicate_claim` now derives from ONE, so they
    # are not relaxed: they are unwritable.  The half that survives -- "is this predicate
    # known, and is it active" -- moved into `_cross_profile_contract`, which is where a
    # predicate is now named.
    #
    # The bind contract is a question about the LEDGER FILE alone -- does this predicate
    # exist, does its derived Claim declare this role -- so it is asked for every source,
    # including one whose relation is undeclared and which the loop below skips.
    for source_id, source in sources.items():
        profile = source.get("bind")
        if isinstance(profile, Mapping):
            _cross_profile_contract(
                f"bundle.sources.{source_id}.bind", profile, vocabulary, problems)

    for rule_id, rule in bundle["virtual_joins"].items():
        path = f"bundle.virtual_joins.{rule_id}"
        _relation_columns(rule.get("left_table"), [p.get("left") for p in rule.get("join_key", [])
                                                   if isinstance(p, Mapping)],
                          tables, f"{path}.left_table", problems)
        right_columns = [p.get("right") for p in rule.get("join_key", [])
                         if isinstance(p, Mapping)] + list(rule.get("expose", [])
                                                           if _is_list(rule.get("expose")) else [])
        _relation_columns(rule.get("right_table"), right_columns, tables,
                          f"{path}.right_table", problems)
        right_keys = [pair["right"] for pair in rule["join_key"]]
        right_table = tables.get(rule["right_table"])
        if (isinstance(right_table, Mapping)
                and not _table_has_unique_key(right_table, right_keys)):
            problems.add(
                "invalid_join", f"{path}.join_key",
                "right join columns require an exact declared UNIQUE key or index")

    # 🔴 THE UNDECLARED RELATION IS THE ROOT REFUSAL, SO IT IS ANSWERED FIRST AND ALONE.
    # Measured while wiring this: with the relation missing from the catalog, the first
    # error an operator saw was `unknown_column` on a MAPPER's `input_columns` -- because
    # `_Problems.finish()` sorted by path and `bundle.mappers.` preceded `bundle.sources.`.
    # (Both bodies now sit UNDER the source, so that particular ordering no longer applies;
    # the skip below is still what keeps the column complaints from burying the root.)
    # Every one of those complaints is downstream of "the table is not declared" and each
    # points at the wrong file to fix.  `ledger_admin.check_source_declaration` already
    # ruled this way for the legacy syntax ("before the column checks, because it is the
    # ROOT refusal"); this is the same rule, not a second one.  Only the affected source
    # is skipped -- an unrelated source keeps being validated.
    unresolved_sources = {
        source_id for source_id, source in sources.items()
        if source.get("relation") not in tables
    }
    for source_id in sorted(unresolved_sources):
        _relation_columns(sources[source_id].get("relation"), (), tables,
                          f"bundle.sources.{source_id}.relation", problems)

    for source_id, source in sources.items():
        if source_id in unresolved_sources:
            continue
        path = f"bundle.sources.{source_id}"
        relation = source.get("relation")
        driver = source["read"]
        base_columns = []
        if _is_list(driver.get("order_by")):
            base_columns.extend(driver["order_by"])
        if isinstance(driver.get("cursor"), Mapping) and _is_list(driver["cursor"].get("columns")):
            base_columns.extend(driver["cursor"]["columns"])
        if isinstance(driver.get("occurred_at"), Mapping):
            # A declared basis names no source column - its time comes from the row's own
            # ingestion stamp, which the schema builder puts on every table.
            occurred_column = driver["occurred_at"].get("column")
            if isinstance(occurred_column, str):
                base_columns.append(occurred_column)
        _relation_columns(relation, base_columns, tables, f"{path}.relation", problems)
        physical = set(_table_columns(tables, relation))
        _cross_registration_probe(
            driver.get("registration_probe"), f"{path}.read.registration_probe",
            relation, physical, tables, entities, problems)
        table = tables.get(relation)
        if isinstance(table, Mapping):
            ordering_contracts = (
                (driver.get("order_by"), f"{path}.read.order_by"),
                (driver.get("cursor", {}).get("columns"),
                 f"{path}.read.cursor.columns"),
            )
            for columns, order_path in ordering_contracts:
                if (_is_list(columns)
                        and not _columns_cover_declared_unique_key(table, columns)):
                    problems.add(
                        "invalid_cursor", order_path,
                        "ordering must include every column of a catalog-declared "
                        "business_key, composite_key, or UNIQUE index")

        profile = source.get("bind") if isinstance(source.get("bind"), Mapping) else None
        profile_path = f"{path}.bind"

        prep = source.get("prepare") if isinstance(source.get("prepare"), Mapping) else {}
        prep_path = f"{path}.prepare"
        available = set(physical)
        if prep:
            for column in prep.get("input_columns", []):
                if column not in physical:
                    problems.add("unknown_column", f"{prep_path}.input_columns",
                                 f"column {column!r} is not in relation {relation!r}")
            if isinstance(prep.get("output_columns"), Mapping):
                for column in sorted(set(prep["output_columns"]) & physical):
                    problems.add(
                        "output_column_collision",
                        f"{prep_path}.output_columns.{column}",
                        f"preparer output collides with physical relation {relation!r}")
                available.update(prep["output_columns"])
            inherited_rules = prep.get("inherit_virtual_join_rules", [])
            if inherited_rules and not prep.get("accepts_verified_join_rules"):
                problems.add(
                    "invalid_driver", f"{prep_path}.accepts_verified_join_rules",
                    "must be true when the source inherits virtual join rules")
        for index, rule_id in enumerate(prep.get("inherit_virtual_join_rules", [])):
            rule = bundle["virtual_joins"].get(rule_id)
            rpath = f"{prep_path}.inherit_virtual_join_rules[{index}]"
            if rule is None:
                problems.add("unknown_join_rule", rpath, f"unknown rule {rule_id!r}")
            elif not rule.get("enabled"):
                problems.add("invalid_driver", rpath, f"join rule {rule_id!r} is disabled")
            elif rule.get("left_table") != relation:
                problems.add("invalid_driver", rpath,
                             f"join rule left_table must be {relation!r}")
            else:
                declared_inputs = set(prep.get("input_columns", []))
                left_keys = {
                    pair.get("left") for pair in rule.get("join_key", [])
                    if isinstance(pair, Mapping)
                }
                missing_inputs = sorted(left_keys - declared_inputs)
                if missing_inputs:
                    problems.add(
                        "invalid_driver", rpath,
                        f"join rule {rule_id!r} left key column(s) {missing_inputs!r} "
                        f"must be declared by {prep_path}.input_columns")

        for field in ("identity", "group_by"):
            for index, column in enumerate(driver.get(field, [])):
                if column not in available:
                    problems.add(
                        "unknown_column", f"{path}.read.{field}[{index}]",
                        f"column {column!r} is not in prepared EventFrame schema")

        mapper = source.get("map") if isinstance(source.get("map"), Mapping) else None
        mapper_path = f"{path}.map"
        if mapper is not None:
            for column in mapper.get("input_columns", []):
                if column not in available:
                    problems.add("unknown_column", f"{mapper_path}.input_columns",
                                 f"column {column!r} is not in EventFrame schema")
            if (mapper.get("unit", {}).get("kind") == "group_by"
                    and not driver.get("group_by")):
                problems.add("invalid_mapper", f"{mapper_path}.unit.kind",
                             "group_by mapper requires source group_by columns")
        if profile is not None:
            # The EventFrame schema this source's Profile binds against is `available`,
            # which is only known HERE -- so the bind/column half of the Profile contract
            # is asked inside the source loop, while the file-only half was asked above.
            _cross_profile_source(profile_path, profile, entities, vocabulary,
                                  available, problems)
        if profile is not None and isinstance(mapper, Mapping):
            # The two-direction set equality between `map.emits` and these `use` values
            # stood here until 2026-08-21.  It is not relaxed -- it is unwritable: the
            # mapper no longer declares the set, `MapperDescriptor.emits` is compiled FROM
            # these very refs, and a rule comparing a value with its own source states
            # nothing.
            mapper_inputs = set(mapper.get("input_columns", []))
            for column, column_path in _profile_binding_columns(profile_path, profile):
                if column not in mapper_inputs:
                    problems.add(
                        "invalid_mapper", f"{mapper_path}.input_columns",
                        f"Profile column {column!r} at {column_path} is missing")


def _cross_vocabulary(vocabulary: Mapping[str, Any], entities: Mapping[str, Any],
                      problems: _Problems) -> None:
    for predicate_id, predicate in vocabulary.items():
        path = f"bundle.vocabulary.{predicate_id}"
        for index, entity_type in enumerate(predicate["subjects"]):
            if entity_type not in entities:
                problems.add("unknown_entity_type", f"{path}.subjects[{index}]",
                             f"unknown entity type {entity_type!r}"
                             + _did_you_mean(entity_type, entities, "entity types"))
        obj = predicate["object"]
        if obj["kind"] == "entity_ref":
            for index, entity_type in enumerate(obj["types"]):
                if entity_type not in entities:
                    problems.add("unknown_entity_type", f"{path}.object.types[{index}]",
                                 f"unknown entity type {entity_type!r}"
                                 + _did_you_mean(entity_type, entities, "entity types"))


def _cross_profile_contract(path: str, profile: Mapping[str, Any],
                            vocabulary: Mapping[str, Any], problems: _Problems) -> None:
    for sentence, mapping in sorted(profile.get("mappings", {}).items()):
        mpath = f"{path}.mappings.{sentence}"
        predicate_id = mapping.get("predicate")
        predicate = vocabulary.get(predicate_id)
        if predicate is None:
            problems.add("unknown_predicate", f"{mpath}.predicate",
                         f"unknown predicate {predicate_id!r}"
                         + _did_you_mean(predicate_id, vocabulary, "predicates"))
            continue
        if predicate.get("status") != "active":
            problems.add("inactive_predicate", f"{mpath}.predicate",
                         f"predicate {predicate_id!r} is not active")
        roles = predicate_claim(predicate_id, predicate)["roles"]
        bindings = mapping["bind"]
        for role in sorted(bindings):
            if role not in roles:
                problems.add("unknown_role", f"{mpath}.bind.{role}",
                             f"role {role!r} is not declared by predicate "
                             f"{predicate_id!r}"
                             + _did_you_mean(role, roles, "roles"))
            if role in roles:
                allowed = role_binding_kinds(roles[role])
                if bindings[role].get("kind") not in allowed:
                    problems.add("invalid_binding", f"{mpath}.bind.{role}.kind",
                                 f"binding kind is not allowed for role {role!r}")
                if (roles[role].get("kind") == "symbolic"
                        and bindings[role].get("kind") == "constant"
                        and bindings[role].get("value") not in
                        roles[role].get("allowed_values", [])):
                    problems.add(
                        "invalid_symbolic_constant", f"{mpath}.bind.{role}.value",
                        f"constant {bindings[role].get('value')!r} is not registered "
                        f"by symbolic role {role!r}")
        for role in sorted(roles):
            descriptor = roles[role]
            if descriptor.get("required") and role not in bindings:
                problems.add("missing_required_role", f"{mpath}.bind.{role}",
                             f"predicate {predicate_id!r} requires role {role!r}")
    # `packs` was checked here in both directions -- every declared pack had to be used and
    # every used pack had to be declared -- until 2026-08-21, when the list itself went.
    # `ProfileDescriptor` no longer carries one either: nothing read it.
    #
    # 🔴 `_ambiguous_sentences` AND `_sentence_signature` LEFT THE SAME DAY, and NOT because
    # the rule was relaxed.  They refused two mappings a mapper could not tell apart, back
    # when a mapper picked one by structure.  `mappings` is now a MAP keyed by the sentence,
    # so "two mappings realizing one sentence" is not a thing a config can say -- JSON has
    # one value per key.  The signature function went with it: it existed only to be the
    # same expression `roleframe.ProfileSentences._resolve` matched on, and that expression
    # is now a dict lookup with nothing to mirror.


def _cross_profile_source(path: str, profile: Mapping[str, Any],
                          entities: Mapping[str, Any],
                          vocabulary: Mapping[str, Any], available: set[str],
                          problems: _Problems) -> None:
    for sentence, mapping in sorted(profile["mappings"].items()):
        mpath = f"{path}.mappings.{sentence}"
        for role, binding in mapping["bind"].items():
            _binding_refs(binding, f"{mpath}.bind.{role}", entities, available, problems)
        predicate = vocabulary.get(mapping["predicate"])
        if predicate is not None:
            _cross_binding_entity_types(
                mapping["bind"], predicate, entities, f"{mpath}.bind", problems)


def _cross_binding_entity_types(bindings: Mapping[str, Any],
                                predicate: Mapping[str, Any],
                                entities: Mapping[str, Any],
                                path: str, problems: _Problems) -> None:
    """Do the two entity ENDPOINTS name types this predicate admits?

    The endpoints are read by their canonical names rather than through an `emit` clause's
    `$role` references: a derived Claim always spells them `subject` and `target`, so the
    indirection had exactly one possible answer.  The refusal moves with them -- it now
    addresses the binding the author wrote instead of a `bundle.packs.…emit` path that no
    longer exists.
    """
    subject = bindings.get(SUBJECT_ROLE)
    if isinstance(subject, Mapping) and subject.get("kind") == "entity":
        entity_type = subject.get("entity_type")
        if entity_type in entities and entity_type not in predicate.get("subjects", []):
            problems.add("invalid_entity_ref", f"{path}.{SUBJECT_ROLE}.entity_type",
                         f"entity {entity_type!r} is not an allowed predicate subject")
    predicate_object = (predicate.get("object", {})
                        if isinstance(predicate.get("object"), Mapping) else {})
    target = bindings.get(TARGET_ROLE)
    if isinstance(target, Mapping) and target.get("kind") == "entity":
        entity_type = target.get("entity_type")
        allowed = predicate_object.get("types", [])
        if entity_type in entities and entity_type not in allowed:
            problems.add("invalid_entity_ref", f"{path}.{TARGET_ROLE}.entity_type",
                         f"entity {entity_type!r} is not an allowed predicate object")


def _binding_refs(binding: Any, path: str, entities: Mapping[str, Any],
                  available: set[str], problems: _Problems) -> None:
    if not isinstance(binding, Mapping):
        return
    if binding.get("kind") == "column" and binding.get("column") not in available:
        problems.add("unknown_column", f"{path}.column",
                     f"column {binding.get('column')!r} is not in EventFrame schema")
    if binding.get("kind") == "entity":
        entity_type = binding.get("entity_type")
        descriptor = entities.get(entity_type)
        if descriptor is None:
            problems.add("unknown_entity_type", f"{path}.entity_type",
                         f"unknown entity type {entity_type!r}")
        elif isinstance(binding.get("keys"), Mapping) and set(binding["keys"]) != set(descriptor.get("keys", [])):
            problems.add("invalid_entity_ref", f"{path}.keys",
                         "entity binding must contain exactly the registered identity keys")
        for key, child in binding.get("keys", {}).items() if isinstance(binding.get("keys"), Mapping) else ():
            _binding_refs(child, f"{path}.keys.{key}", entities, available, problems)


def _binding_readiness(binding: Any, path: str, problems: _Problems) -> None:
    if not isinstance(binding, Mapping):
        return
    status = binding.get("approval_status")
    if status != "approved":
        problems.add("binding_not_approved", f"{path}.approval_status",
                     f"binding approval_status is {status!r}, expected 'approved'")
    if binding.get("kind") == "entity" and isinstance(binding.get("keys"), Mapping):
        for key in sorted(binding["keys"]):
            _binding_readiness(binding["keys"][key], f"{path}.keys.{key}", problems)


def _profile_binding_columns(path: str, profile: Mapping[str, Any]
                             ) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for sentence, mapping in sorted(profile["mappings"].items()):
        base = f"{path}.mappings.{sentence}.bind"
        for role in sorted(mapping["bind"]):
            out.extend(_binding_columns(mapping["bind"][role], f"{base}.{role}"))
    return tuple(out)


def _binding_columns(binding: Mapping[str, Any], path: str) -> list[tuple[str, str]]:
    if binding["kind"] == "column":
        return [(binding["column"], f"{path}.column")]
    out: list[tuple[str, str]] = []
    if binding["kind"] == "entity":
        for key in sorted(binding["keys"]):
            out.extend(_binding_columns(binding["keys"][key], f"{path}.keys.{key}"))
    return out


def _table_has_unique_key(table: Mapping[str, Any], columns: Sequence[str]) -> bool:
    target = tuple(columns)
    for field in ("business_key", "composite_key"):
        if field in table and tuple(_column_values(table[field])) == target:
            return True
    return any(
        index["unique"] is True and tuple(index["columns"]) == target
        for index in table.get("indexes", [])
    )


def _columns_cover_declared_unique_key(table: Mapping[str, Any],
                                       columns: Sequence[str]) -> bool:
    candidate = {column for column in columns if isinstance(column, str)}
    declared: list[tuple[str, ...]] = []
    for field in ("business_key", "composite_key"):
        if field in table:
            declared.append(tuple(_column_values(table[field])))
    declared.extend(
        tuple(index.get("columns", ()))
        for index in table.get("indexes", [])
        if isinstance(index, Mapping) and index.get("unique") is True
    )
    return any(key and set(key).issubset(candidate) for key in declared)


def _relation_columns(relation: Any, columns: Sequence[Any], tables: Mapping[str, Any],
                      path: str, problems: _Problems) -> None:
    if relation not in tables:
        # 🔴 NAME THE TABLE AND THE NEXT ACTION.  A table the ledger reads but ingestion
        # never writes -- `void` is the live shape of this -- can be missing from
        # `table_config.json`, and the answer is to DECLARE IT THERE, never to keep a copy
        # here: that file is the physical authority, and declaring a table in it brings
        # drift detection and the grid along with it.  Same refusal
        # `ledger_admin.check_source_declaration` already gives for the legacy syntax, so
        # an operator meets one sentence rather than two.
        problems.add(
            "unknown_relation", path,
            f"relation {relation!r} is not declared in {PHYSICAL_CATALOG_FILENAME}; "
            f"declare the table there first — the ledger reads the physical schema from "
            f"that file and an undeclared table has no columns, no key, and no drift "
            f"check")
        return
    known = set(_table_columns(tables, relation))
    for column in columns:
        if not isinstance(column, str) or column not in known:
            problems.add("unknown_column", path,
                         f"column {column!r} is not in relation {relation!r}")


def _table_columns(tables: Mapping[str, Any], relation: Any) -> tuple[str, ...]:
    table = tables.get(relation)
    if not isinstance(table, Mapping) or not isinstance(table.get("columns"), Mapping):
        return ()
    return tuple(table["columns"])


def _implementation(item: Mapping[str, Any], path: str, problems: _Problems) -> None:
    _nonblank_text(item.get("implementation_id"), f"{path}.implementation_id", problems)
    version = item.get("implementation_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        problems.add("invalid_version", f"{path}.implementation_version",
                     "must be a positive integer")


def _column_types(value: Any, path: str, problems: _Problems) -> None:
    if not isinstance(value, Mapping):
        problems.add("invalid_type", path, "must be an object")
        return
    for name in sorted(value):
        _nonblank_id(name, f"{path}.{name}", problems)
        _nonblank_text(value[name], f"{path}.{name}", problems)


def _binding_kind_list(value: Any, path: str, problems: _Problems) -> None:
    _nonblank_list(value, path, problems)
    if _is_list(value):
        for index, kind in enumerate(value):
            if kind not in ("column", "constant", "entity"):
                problems.add("invalid_binding", f"{path}[{index}]",
                             f"unsupported binding kind {kind!r}")


def _default_binding_kinds(role_kind: Any) -> tuple[str, ...]:
    return ("entity",) if role_kind == "entity" else ("column", "constant")


def _scan_unsafe_keys(value: Any, path: str, problems: _Problems) -> None:
    stack: list[tuple[Any, str]] = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if isinstance(current, Mapping):
            for key in sorted(current, key=str, reverse=True):
                child_path = _path(current_path, str(key))
                if str(key).lower() in _FORBIDDEN_EXECUTABLE_KEYS:
                    problems.add("unsafe_declaration", child_path, "field is not allowed")
                stack.append((current[key], child_path))
        elif _is_list(current):
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], f"{current_path}[{index}]"))


def _read_json(path: Path, logical_path: str) -> Mapping[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path, "config file is not valid UTF-8") from exc
    except OSError as exc:
        raise LedgerSetupValidationError(
            "config_read_failed", logical_path,
            f"could not read {path.name}: {exc.__class__.__name__}") from exc
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant)
    except _DuplicateKey as exc:
        raise LedgerSetupValidationError(
            "duplicate_id", logical_path, f"duplicate JSON key {exc.key!r}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path,
            f"invalid JSON at line {exc.lineno} column {exc.colno}") from exc
    except _InvalidJsonConstant as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path, str(exc)) from exc
    except RecursionError as exc:
        raise LedgerSetupValidationError(
            "invalid_json", logical_path, "JSON nesting is too deep") from exc
    if not isinstance(value, Mapping):
        raise LedgerSetupValidationError("invalid_type", logical_path,
                                         "JSON root must be an object")
    return value


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey(key)
        out[key] = value
    return out


def _reject_json_constant(value: str) -> None:
    raise _InvalidJsonConstant(f"non-standard JSON constant {value!r} is not allowed")
