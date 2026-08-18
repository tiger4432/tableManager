"""Pure Ledger authoring bundle schema and single-file loader.

This module deliberately has no database, translator, mapper, compiler, cursor, or store
imports.  Stage 2 owns only the authoring boundary: strict files in one root become one
deterministically serializable logical bundle.  Runtime registries are a later stage.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SETUP_VERSION = 3

#: The one authoring file. The path does not move: the operator writes here.
CONFIG_FILENAME = "ledger_config.json"

#: The whole authoring surface, in the order the file declares it.  All seven are
#: REQUIRED even when empty: a missing key and an empty one mean different things to a
#: reader, and "the section does not apply to me" is a decision worth writing down.
#:
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
LOGICAL_SECTIONS = (
    "vocabulary", "entities", "packs",
    "source_preparers", "mappers", "profiles", "sources",
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
_CLAIM_REF = re.compile(r"^(?P<pack>[^@/\s]+@[1-9][0-9]*)/(?P<claim>[^/\s]+)$")
_FORBIDDEN_DECLARATION_KEYS = frozenset({
    "module", "function", "path", "python", "sql", "javascript",
    "expression", "eval", "exec", "lookup", "lookups", "declared_lookup",
    "position", "positions", "frame", "frames",
})
_FORBIDDEN_EXECUTABLE_KEYS = frozenset({
    "module", "function", "path", "python", "sql", "javascript",
    "expression", "eval", "exec",
})
_BINDING_ORIGINS = frozenset({"user_declared", "system_suggested", "imported"})
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
        # `table_config.json` declares no `indexes` today, so this passes nothing through
        # on the live catalog.  It is wired anyway rather than left for later, because the
        # consumers (`_table_has_unique_key`, `_columns_cover_declared_unique_key`) DO read
        # unique indexes: without this line they are permanently-empty branches that would
        # start giving the wrong answer, silently, on the day the catalog grammar gains the
        # key -- and "wrong answer about which orderings are unique" is the direction that
        # loses events.
        indexes = declared.get("indexes")
        if isinstance(indexes, list) and indexes:
            relation["indexes"] = [dict(item) for item in indexes
                                   if isinstance(item, Mapping)]
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
            self.add(code, key_path, _RETIRED_FIELD_HELP.get(key_path,
                                                             "field is not allowed"))
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
        "forbidden_sections": ["frames", "lookups", "positions",
                               "manifest", "chains", "enrichments", "tables"],
    }


def role_binding_kinds(role: Mapping[str, Any]) -> tuple[str, ...]:
    """Resolve one validated Role's effective binding kinds from the Pack contract."""
    if not isinstance(role, Mapping):
        raise TypeError("role must be a mapping")
    declared = role.get("allowed_binding_kinds")
    if _is_list(declared):
        return tuple(declared)
    return _default_binding_kinds(role.get("kind"))


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
    if isinstance(value.get("source_preparers"), Mapping):
        _validate_preparers(value["source_preparers"], problems)
    if isinstance(value.get("mappers"), Mapping):
        _validate_mappers(value["mappers"], problems)
    if isinstance(value.get("packs"), Mapping):
        _validate_packs(value["packs"], problems)
    if isinstance(value.get("profiles"), Mapping):
        _validate_profiles(value["profiles"], problems)
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
    for profile_id, profile in bundle.section("profiles").items():
        for index, mapping in enumerate(profile["mappings"]):
            base = f"bundle.profiles.{profile_id}.mappings[{index}].bind"
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
    problems = _Problems()
    if problems.exact(
            document, "ledger_config",
            required=("setup_version", *LOGICAL_SECTIONS),
            optional=OPTIONAL_SECTIONS):
        if document.get("setup_version") != SETUP_VERSION:
            problems.add(
                "unsupported_setup_version", "ledger_config.setup_version",
                f"supported setup_version is {SETUP_VERSION}")
    issues = problems.finish()
    if issues:
        raise issues[0]
    return validate_bundle(document, catalog=catalog)


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


def _claim_ref(value: Any, path: str, problems: _Problems) -> None:
    if _parse_claim_ref(value) is None:
        problems.add("invalid_claim_ref", path, "must use pack@version/claim")


def _parse_claim_ref(value: Any) -> Optional[tuple[str, str]]:
    if not isinstance(value, str):
        return None
    matched = _CLAIM_REF.fullmatch(value)
    return None if matched is None else (matched.group("pack"), matched.group("claim"))


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


def _role_name(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.startswith("$"):
        return None
    return value[1:].removesuffix("?") or None


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
                   *, allow_empty: bool = False) -> None:
    if not _is_list(value) or (not value and not allow_empty):
        problems.add("invalid_type", path,
                     "must be a list" + ("" if allow_empty else " with at least one item"))
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
                item, path, required=("status", "layer", "subjects", "object")):
            continue
        if item.get("status") not in ("active", "retired"):
            problems.add("invalid_predicate", f"{path}.status", "must be active or retired")
        _nonblank_text(item.get("layer"), f"{path}.layer", problems)
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


def _validate_preparers(section: Mapping[str, Any], problems: _Problems) -> None:
    for preparer_id in sorted(section, key=str):
        path = f"bundle.source_preparers.{preparer_id}"
        _versioned_id(preparer_id, path, problems)
        item = section[preparer_id]
        if not problems.exact(
                item, path,
                required=("implementation_id", "implementation_version", "input_columns",
                          "output_columns", "accepts_verified_join_rules")):
            continue
        _implementation(item, path, problems)
        _nonblank_list(item.get("input_columns"), f"{path}.input_columns", problems,
                       allow_empty=True)
        _column_types(item.get("output_columns"), f"{path}.output_columns", problems)
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


def _validate_mappers(section: Mapping[str, Any], problems: _Problems) -> None:
    for mapper_id in sorted(section, key=str):
        path = f"bundle.mappers.{mapper_id}"
        _versioned_id(mapper_id, path, problems)
        item = section[mapper_id]
        if not problems.exact(
                item, path,
                required=("implementation_id", "implementation_version", "unit",
                          "input_columns", "emits")):
            continue
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
        _nonblank_list(item.get("emits"), f"{path}.emits", problems)


def _validate_packs(section: Mapping[str, Any], problems: _Problems) -> None:
    for pack_id in sorted(section, key=str):
        path = f"bundle.packs.{pack_id}"
        _versioned_id(pack_id, path, problems)
        pack = section[pack_id]
        if not problems.exact(pack, path, required=("claims",)):
            continue
        claims = pack.get("claims")
        if not isinstance(claims, Mapping) or not claims:
            problems.add("invalid_pack", f"{path}.claims", "must be a non-empty object")
            continue
        for claim_id in sorted(claims, key=str):
            cpath = f"{path}.claims.{claim_id}"
            _nonblank_id(claim_id, cpath, problems)
            claim = claims[claim_id]
            if not problems.exact(claim, cpath, required=("roles", "emit")):
                continue
            roles = claim.get("roles")
            if not isinstance(roles, Mapping) or not roles:
                problems.add("invalid_pack", f"{cpath}.roles", "must be non-empty")
            else:
                for role_id in sorted(roles, key=str):
                    rpath = f"{cpath}.roles.{role_id}"
                    _nonblank_id(role_id, rpath, problems)
                    role = roles[role_id]
                    if problems.exact(
                            role, rpath, required=("kind", "required"),
                            optional=("allowed_binding_kinds", "allowed_values")):
                        role_kind = role.get("kind")
                        if not isinstance(role_kind, str) or role_kind not in _ROLE_KINDS:
                            problems.add("invalid_role_kind", f"{rpath}.kind",
                                         f"must be one of {sorted(_ROLE_KINDS)}")
                        if not isinstance(role.get("required"), bool):
                            problems.add("invalid_type", f"{rpath}.required", "must be boolean")
                        if "allowed_binding_kinds" in role:
                            _binding_kind_list(role["allowed_binding_kinds"],
                                               f"{rpath}.allowed_binding_kinds", problems)
                            allowed = set(_column_values(role["allowed_binding_kinds"]))
                            compatible = set(_default_binding_kinds(role_kind))
                            if role_kind in _ROLE_KINDS and not allowed <= compatible:
                                problems.add(
                                    "invalid_role_kind", f"{rpath}.allowed_binding_kinds",
                                    f"binding kinds must be a subset of {sorted(compatible)}")
                        if role_kind == "symbolic":
                            if "allowed_values" not in role:
                                problems.add(
                                    "missing_field", f"{rpath}.allowed_values",
                                    "symbolic role requires allowed_values")
                            else:
                                values = role["allowed_values"]
                                _nonblank_list(values, f"{rpath}.allowed_values", problems)
                                if (_is_list(values)
                                        and list(values) != sorted(values, key=str)):
                                    problems.add(
                                        "invalid_role_kind", f"{rpath}.allowed_values",
                                        "symbolic allowed_values must be sorted")
                        elif "allowed_values" in role:
                            problems.add(
                                "invalid_role_kind", f"{rpath}.allowed_values",
                                "allowed_values is only valid for symbolic roles")
            _validate_emission(claim.get("emit"), f"{cpath}.emit", problems)


def _validate_emission(value: Any, path: str, problems: _Problems) -> None:
    if not problems.exact(
            value, path, required=("predicate", "subject", "object", "occurred_at")):
        return
    _versioned_id(value.get("predicate"), f"{path}.predicate", problems)
    _role_ref(value.get("subject"), f"{path}.subject", problems)
    _role_ref(value.get("occurred_at"), f"{path}.occurred_at", problems)
    obj = value.get("object")
    if problems.exact(obj, f"{path}.object", required=("kind",),
                      optional=("entity", "value", "qualifiers")):
        if (not isinstance(obj.get("kind"), str)
                or obj.get("kind") not in _OBJECT_KINDS):
            problems.add("invalid_emission", f"{path}.object.kind",
                         f"must be one of {sorted(_OBJECT_KINDS)}")
        if "entity" in obj:
            _role_ref(obj["entity"], f"{path}.object.entity", problems)
        if "qualifiers" in obj and not isinstance(obj["qualifiers"], Mapping):
            problems.add("invalid_type", f"{path}.object.qualifiers", "must be an object")
        elif isinstance(obj.get("qualifiers"), Mapping):
            for name in sorted(obj["qualifiers"]):
                _role_ref(obj["qualifiers"][name], f"{path}.object.qualifiers.{name}",
                          problems)


def _validate_profiles(section: Mapping[str, Any], problems: _Problems) -> None:
    for profile_id in sorted(section, key=str):
        path = f"bundle.profiles.{profile_id}"
        _versioned_id(profile_id, path, problems)
        profile = section[profile_id]
        if not problems.exact(profile, path, required=("source", "packs", "mappings")):
            continue
        _nonblank_text(profile.get("source"), f"{path}.source", problems)
        _nonblank_list(profile.get("packs"), f"{path}.packs", problems)
        mappings = profile.get("mappings")
        if not _is_list(mappings) or not mappings:
            problems.add("invalid_profile", f"{path}.mappings", "must be a non-empty list")
            continue
        seen = set()
        for index, mapping in enumerate(mappings):
            mpath = f"{path}.mappings[{index}]"
            if not problems.exact(mapping, mpath, required=("mapping_id", "use", "bind")):
                continue
            mapping_id = mapping.get("mapping_id")
            _nonblank_text(mapping_id, f"{mpath}.mapping_id", problems)
            if isinstance(mapping_id, str):
                if mapping_id in seen:
                    problems.add("duplicate_id", f"{mpath}.mapping_id",
                                 f"mapping_id {mapping_id!r} is duplicated")
                seen.add(mapping_id)
            _claim_ref(mapping.get("use"), f"{mpath}.use", problems)
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
        required = ("kind", "column", "binding_origin", "approval_status")
    elif kind == "constant":
        allowed = ("kind", "value", "binding_origin", "approval_status", "suggestion_reason")
        required = ("kind", "value", "binding_origin", "approval_status")
    elif kind == "entity":
        allowed = ("kind", "entity_type", "keys", "binding_origin", "approval_status",
                   "suggestion_reason")
        required = ("kind", "entity_type", "keys", "binding_origin", "approval_status")
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
    origin = value.get("binding_origin")
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
    for source_id in sorted(section, key=str):
        path = f"bundle.sources.{source_id}"
        _nonblank_id(source_id, path, problems)
        source = section[source_id]
        if not problems.exact(source, path, required=("relation", "driver", "profile_id")):
            continue
        _nonblank_text(source.get("relation"), f"{path}.relation", problems)
        _versioned_id(source.get("profile_id"), f"{path}.profile_id", problems)
        driver = source.get("driver")
        if not problems.exact(
                driver, f"{path}.driver",
                required=("unit", "identity", "group_by", "order_by", "occurred_at",
                          "cursor", "preparation", "mapper_id"),
                optional=("registration_probe",)):
            continue
        _validate_registration_probe(
            driver.get("registration_probe"), f"{path}.driver.registration_probe",
            problems)
        source_unit = driver.get("unit")
        if not isinstance(source_unit, str) or source_unit not in _SOURCE_UNITS:
            problems.add("invalid_driver", f"{path}.driver.unit",
                         f"must be one of {sorted(_SOURCE_UNITS)}")
        for field in ("identity", "group_by", "order_by"):
            _nonblank_list(driver.get(field), f"{path}.driver.{field}", problems,
                           allow_empty=(field == "group_by"))
        group_by = driver.get("group_by")
        identity = driver.get("identity")
        if source_unit == "row" and _is_list(group_by) and group_by:
            problems.add("invalid_driver", f"{path}.driver.group_by",
                         "row unit requires an empty group_by list")
        if source_unit == "group" and _is_list(group_by) and not group_by:
            problems.add("invalid_driver", f"{path}.driver.group_by",
                         "group unit requires at least one group_by column")
        if (_is_list(group_by) and _is_list(identity)
                and any(isinstance(column, str) and column not in identity
                        for column in group_by)):
            problems.add("invalid_driver", f"{path}.driver.group_by",
                         "group_by columns must be included in identity")
        occurred = driver.get("occurred_at")
        if problems.exact(
                occurred, f"{path}.driver.occurred_at",
                required=("timezone",), optional=("column", "basis")):
            _occurred_at_origin(occurred, f"{path}.driver.occurred_at", problems)
            timezone = occurred.get("timezone")
            _nonblank_text(timezone, f"{path}.driver.occurred_at.timezone", problems)
            if isinstance(timezone, str) and timezone.strip():
                try:
                    ZoneInfo(timezone)
                except ZoneInfoNotFoundError:
                    problems.add("invalid_timezone", f"{path}.driver.occurred_at.timezone",
                                 f"unknown timezone {timezone!r}")
        cursor = driver.get("cursor")
        if problems.exact(cursor, f"{path}.driver.cursor", required=("columns",)):
            _nonblank_list(cursor.get("columns"), f"{path}.driver.cursor.columns", problems)
        prep = driver.get("preparation")
        if problems.exact(
                prep, f"{path}.driver.preparation",
                required=("preparer_id", "inherit_virtual_join_rules")):
            _versioned_id(prep.get("preparer_id"),
                          f"{path}.driver.preparation.preparer_id", problems)
            _nonblank_list(prep.get("inherit_virtual_join_rules"),
                           f"{path}.driver.preparation.inherit_virtual_join_rules",
                           problems, allow_empty=True)
        _versioned_id(driver.get("mapper_id"), f"{path}.driver.mapper_id", problems)


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
    packs = bundle["packs"]
    profiles = bundle["profiles"]
    preparers = bundle["source_preparers"]
    mappers = bundle["mappers"]
    sources = bundle["sources"]
    event_frame_columns: dict[str, set[str]] = {}

    _cross_vocabulary(vocabulary, entities, problems)
    _cross_packs(packs, vocabulary, problems)
    for mapper_id, mapper in mappers.items():
        for index, claim_ref in enumerate(mapper.get("emits", [])):
            _known_claim(claim_ref, packs, f"bundle.mappers.{mapper_id}.emits[{index}]",
                         problems)
    for profile_id, profile in profiles.items():
        _cross_profile_contract(profile_id, profile, packs, problems)

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
    # `_Problems.finish()` sorts by path and `bundle.mappers.` precedes `bundle.sources.`.
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
        driver = source["driver"]
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
            driver.get("registration_probe"), f"{path}.driver.registration_probe",
            relation, physical, tables, entities, problems)
        table = tables.get(relation)
        if isinstance(table, Mapping):
            ordering_contracts = (
                (driver.get("order_by"), f"{path}.driver.order_by"),
                (driver.get("cursor", {}).get("columns"),
                 f"{path}.driver.cursor.columns"),
            )
            for columns, order_path in ordering_contracts:
                if (_is_list(columns)
                        and not _columns_cover_declared_unique_key(table, columns)):
                    problems.add(
                        "invalid_cursor", order_path,
                        "ordering must include every column of a catalog-declared "
                        "business_key, composite_key, or UNIQUE index")

        profile_id = source.get("profile_id")
        profile = profiles.get(profile_id)
        if profile is None:
            problems.add("unknown_profile", f"{path}.profile_id",
                         f"unknown profile {profile_id!r}")
        elif isinstance(profile, Mapping) and profile.get("source") != source_id:
            problems.add("invalid_profile", f"bundle.profiles.{profile_id}.source",
                         f"must equal source ID {source_id!r}")

        prep = driver.get("preparation") if isinstance(driver.get("preparation"), Mapping) else {}
        preparer_id = prep.get("preparer_id")
        preparer = preparers.get(preparer_id)
        available = set(physical)
        if preparer is None:
            problems.add("unknown_source_preparer", f"{path}.driver.preparation.preparer_id",
                         f"unknown source preparer {preparer_id!r}")
        elif isinstance(preparer, Mapping):
            for column in preparer.get("input_columns", []):
                if column not in physical:
                    problems.add("unknown_column",
                                 f"bundle.source_preparers.{preparer_id}.input_columns",
                                 f"column {column!r} is not in relation {relation!r}")
            if isinstance(preparer.get("output_columns"), Mapping):
                for column in sorted(set(preparer["output_columns"]) & physical):
                    problems.add(
                        "output_column_collision",
                        f"bundle.source_preparers.{preparer_id}.output_columns.{column}",
                        f"preparer output collides with physical relation {relation!r}")
                available.update(preparer["output_columns"])
            inherited_rules = prep.get("inherit_virtual_join_rules", [])
            if inherited_rules and not preparer.get("accepts_verified_join_rules"):
                problems.add(
                    "invalid_driver",
                    f"bundle.source_preparers.{preparer_id}.accepts_verified_join_rules",
                    "must be true when the source inherits virtual join rules")
        for index, rule_id in enumerate(prep.get("inherit_virtual_join_rules", [])):
            rule = bundle["virtual_joins"].get(rule_id)
            rpath = f"{path}.driver.preparation.inherit_virtual_join_rules[{index}]"
            if rule is None:
                problems.add("unknown_join_rule", rpath, f"unknown rule {rule_id!r}")
            elif not rule.get("enabled"):
                problems.add("invalid_driver", rpath, f"join rule {rule_id!r} is disabled")
            elif rule.get("left_table") != relation:
                problems.add("invalid_driver", rpath,
                             f"join rule left_table must be {relation!r}")
            elif isinstance(preparer, Mapping):
                declared_inputs = set(preparer.get("input_columns", []))
                left_keys = {
                    pair.get("left") for pair in rule.get("join_key", [])
                    if isinstance(pair, Mapping)
                }
                missing_inputs = sorted(left_keys - declared_inputs)
                if missing_inputs:
                    problems.add(
                        "invalid_driver", rpath,
                        f"join rule {rule_id!r} left key column(s) {missing_inputs!r} "
                        f"must be declared by preparer {preparer_id!r} input_columns")

        for field in ("identity", "group_by"):
            for index, column in enumerate(driver.get(field, [])):
                if column not in available:
                    problems.add(
                        "unknown_column", f"{path}.driver.{field}[{index}]",
                        f"column {column!r} is not in prepared EventFrame schema")

        mapper_id = driver.get("mapper_id")
        mapper = mappers.get(mapper_id)
        if mapper is None:
            problems.add("unknown_mapper", f"{path}.driver.mapper_id",
                         f"unknown mapper {mapper_id!r}")
        elif isinstance(mapper, Mapping):
            for column in mapper.get("input_columns", []):
                if column not in available:
                    problems.add("unknown_column", f"bundle.mappers.{mapper_id}.input_columns",
                                 f"column {column!r} is not in EventFrame schema")
            if (mapper.get("unit", {}).get("kind") == "group_by"
                    and not driver.get("group_by")):
                problems.add("invalid_mapper", f"bundle.mappers.{mapper_id}.unit.kind",
                             "group_by mapper requires source group_by columns")
        event_frame_columns[source_id] = set(available)
        if isinstance(profile, Mapping) and isinstance(mapper, Mapping):
            profile_uses = [mapping["use"] for mapping in profile["mappings"]]
            mapper_emits = list(mapper.get("emits", []))
            for index, claim_ref in enumerate(mapper_emits):
                if claim_ref not in profile_uses:
                    problems.add(
                        "invalid_mapper", f"bundle.mappers.{mapper_id}.emits[{index}]",
                        f"Claim {claim_ref!r} has no mapping in profile {profile_id!r}")
            for index, mapping in enumerate(profile["mappings"]):
                if mapping["use"] not in mapper_emits:
                    problems.add(
                        "invalid_profile",
                        f"bundle.profiles.{profile_id}.mappings[{index}].use",
                        f"Claim {mapping['use']!r} is not declared by mapper {mapper_id!r}")
            mapper_inputs = set(mapper.get("input_columns", []))
            for column, column_path in _profile_binding_columns(profile_id, profile):
                if column not in mapper_inputs:
                    problems.add(
                        "invalid_mapper", f"bundle.mappers.{mapper_id}.input_columns",
                        f"Profile column {column!r} at {column_path} is missing")

    # Every Profile is an authoring contract, including Profiles not selected by a
    # Source.  Resolve its declared source once and apply the same entity/column
    # validation used for selected Profiles; keeping this outside the source loop
    # also prevents duplicate errors for selected Profiles.
    for profile_id in sorted(profiles, key=str):
        profile = profiles[profile_id]
        source_name = profile.get("source")
        if source_name not in sources:
            problems.add("unknown_source", f"bundle.profiles.{profile_id}.source",
                         f"unknown source {source_name!r}")
            continue
        if source_name in unresolved_sources:
            # Its EventFrame schema is unknown, not empty. Checking columns against an
            # empty set would report every binding as unknown -- noise under the root
            # refusal already raised above.
            continue
        available = event_frame_columns.get(source_name, set())
        _cross_profile_source(profile_id, profile, packs, entities, vocabulary,
                              available, problems)


def _cross_vocabulary(vocabulary: Mapping[str, Any], entities: Mapping[str, Any],
                      problems: _Problems) -> None:
    for predicate_id, predicate in vocabulary.items():
        path = f"bundle.vocabulary.{predicate_id}"
        for index, entity_type in enumerate(predicate["subjects"]):
            if entity_type not in entities:
                problems.add("unknown_entity_type", f"{path}.subjects[{index}]",
                             f"unknown entity type {entity_type!r}")
        obj = predicate["object"]
        if obj["kind"] == "entity_ref":
            for index, entity_type in enumerate(obj["types"]):
                if entity_type not in entities:
                    problems.add("unknown_entity_type", f"{path}.object.types[{index}]",
                                 f"unknown entity type {entity_type!r}")


def _cross_packs(packs: Mapping[str, Any], vocabulary: Mapping[str, Any],
                 problems: _Problems) -> None:
    for pack_id, pack in packs.items():
        for claim_id, claim in pack["claims"].items():
            path = f"bundle.packs.{pack_id}.claims.{claim_id}"
            roles = claim["roles"]
            emission = claim["emit"]
            predicate_id = emission["predicate"]
            predicate = vocabulary.get(predicate_id)
            if predicate is None:
                problems.add("unknown_predicate", f"{path}.emit.predicate",
                             f"unknown predicate {predicate_id!r}")
            elif predicate["status"] != "active":
                problems.add("inactive_predicate", f"{path}.emit.predicate",
                             f"predicate {predicate_id!r} is not active")

            _cross_emission_role(
                roles, emission["subject"], f"{path}.emit.subject", {"entity"},
                problems, required_endpoint=True)
            _cross_emission_role(
                roles, emission["occurred_at"], f"{path}.emit.occurred_at", {"time"},
                problems, required_endpoint=True)
            obj = emission["object"]
            object_kind = obj["kind"]
            if predicate is not None and object_kind != predicate["object"]["kind"]:
                problems.add("invalid_predicate", f"{path}.emit.object.kind",
                             "Pack emission object kind disagrees with Vocabulary")
            if object_kind == "entity_ref":
                if "entity" not in obj or "value" in obj:
                    problems.add("invalid_emission", f"{path}.emit.object",
                                 "entity_ref object requires only an entity Role")
                elif "entity" in obj:
                    _cross_emission_role(
                        roles, obj["entity"], f"{path}.emit.object.entity", {"entity"},
                        problems, required_endpoint=True)
            elif object_kind in ("value", "event_ref"):
                expected = _SCALAR_ROLE_KINDS if object_kind == "value" else {"identity"}
                if "value" not in obj or "entity" in obj:
                    problems.add("invalid_emission", f"{path}.emit.object",
                                 f"{object_kind} object requires only a value Role")
                elif "value" in obj:
                    _cross_emission_role(
                        roles, obj["value"], f"{path}.emit.object.value", expected,
                        problems, required_endpoint=True)
            elif object_kind == "none":
                if set(obj) != {"kind"}:
                    problems.add(
                        "invalid_emission", f"{path}.emit.object",
                        "none object must contain only kind")
            for qualifier, role_ref in obj.get("qualifiers", {}).items():
                _cross_emission_role(
                    roles, role_ref, f"{path}.emit.object.qualifiers.{qualifier}",
                    _SCALAR_ROLE_KINDS, problems, required_endpoint=False)
            if predicate is not None:
                qualifier_contract = predicate["object"]["qualifiers"]
                required_qualifiers = set(qualifier_contract["required"])
                optional_qualifiers = set(qualifier_contract["optional"])
                emitted_qualifiers = set(obj.get("qualifiers", {}))
                for qualifier in sorted(required_qualifiers - emitted_qualifiers):
                    problems.add(
                        "missing_required_payload",
                        f"{path}.emit.object.qualifiers.{qualifier}",
                        f"predicate {predicate_id!r} requires qualifier {qualifier!r}")
                allowed_qualifiers = required_qualifiers | optional_qualifiers
                for qualifier in sorted(emitted_qualifiers - allowed_qualifiers):
                    problems.add(
                        "unknown_payload_field",
                        f"{path}.emit.object.qualifiers.{qualifier}",
                        f"predicate {predicate_id!r} does not allow qualifier {qualifier!r}")


def _cross_emission_role(roles: Mapping[str, Any], role_ref: str, path: str,
                         expected_kinds: set[str] | frozenset[str], problems: _Problems,
                         *, required_endpoint: bool) -> None:
    role_id = _role_name(role_ref)
    if role_id not in roles:
        problems.add("unknown_role", path, f"emission references unknown Role {role_id!r}")
        return
    descriptor = roles[role_id]
    role_kind = descriptor["kind"]
    if role_kind not in expected_kinds:
        problems.add("invalid_role_kind", path,
                     f"Role {role_id!r} kind {role_kind!r} is not one of {sorted(expected_kinds)}")
    is_optional_ref = role_ref.endswith("?")
    is_required_role = descriptor["required"] is True
    if required_endpoint and (not is_required_role or is_optional_ref):
        problems.add("invalid_role_ref", path,
                     "subject, object, and occurred_at require a required non-optional Role")
    elif not required_endpoint and is_required_role == is_optional_ref:
        expected = f"${role_id}" if is_required_role else f"${role_id}?"
        problems.add("invalid_role_ref", path,
                     f"Role optionality requires reference {expected!r}")


def _cross_profile_contract(profile_id: str, profile: Mapping[str, Any],
                            packs: Mapping[str, Any], problems: _Problems) -> None:
    path = f"bundle.profiles.{profile_id}"
    declared_packs = set(profile["packs"])
    used_packs: set[str] = set()
    for index, pack_id in enumerate(profile.get("packs", [])):
        if pack_id not in packs:
            problems.add("unknown_pack", f"{path}.packs[{index}]", f"unknown pack {pack_id!r}")
    for index, mapping in enumerate(profile.get("mappings", [])):
        mpath = f"{path}.mappings[{index}]"
        parsed = _parse_claim_ref(mapping["use"])
        if parsed is not None:
            used_packs.add(parsed[0])
            if parsed[0] not in declared_packs:
                problems.add("invalid_profile", f"{mpath}.use",
                             f"Pack {parsed[0]!r} is not listed by profile.packs")
        claim = _known_claim(mapping.get("use"), packs, f"{mpath}.use", problems)
        if claim is None:
            continue
        roles = claim["roles"]
        bindings = mapping["bind"]
        for role in sorted(bindings):
            if role not in roles:
                problems.add("unknown_role", f"{mpath}.bind.{role}",
                             f"role {role!r} is not declared by Claim")
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
                             f"Claim requires role {role!r}")
    for index, pack_id in enumerate(profile["packs"]):
        if pack_id in packs and pack_id not in used_packs:
            problems.add("invalid_profile", f"{path}.packs[{index}]",
                         f"Pack {pack_id!r} is declared but unused by mappings")


def _cross_profile_source(profile_id: str, profile: Mapping[str, Any],
                          packs: Mapping[str, Any], entities: Mapping[str, Any],
                          vocabulary: Mapping[str, Any], available: set[str],
                          problems: _Problems) -> None:
    path = f"bundle.profiles.{profile_id}"
    for index, mapping in enumerate(profile["mappings"]):
        mpath = f"{path}.mappings[{index}]"
        for role, binding in mapping["bind"].items():
            _binding_refs(binding, f"{mpath}.bind.{role}", entities, available, problems)
        use = _parse_claim_ref(mapping["use"])
        if use is None or use[0] not in packs or use[1] not in packs[use[0]]["claims"]:
            continue
        claim = packs[use[0]]["claims"][use[1]]
        predicate = vocabulary.get(claim["emit"]["predicate"])
        if predicate is not None:
            _cross_emission_types(
                claim["emit"], mapping["bind"], predicate, entities,
                f"bundle.packs.{use[0]}.claims.{use[1]}.emit", problems)


def _cross_emission_types(emission: Mapping[str, Any], bindings: Mapping[str, Any],
                          predicate: Mapping[str, Any], entities: Mapping[str, Any],
                          path: str, problems: _Problems) -> None:
    subject_role = _role_name(emission.get("subject"))
    subject = bindings.get(subject_role) if subject_role else None
    if isinstance(subject, Mapping) and subject.get("kind") == "entity":
        entity_type = subject.get("entity_type")
        if entity_type in entities and entity_type not in predicate.get("subjects", []):
            problems.add("invalid_entity_ref", f"{path}.subject",
                         f"entity {entity_type!r} is not an allowed predicate subject")
    obj = emission.get("object") if isinstance(emission.get("object"), Mapping) else {}
    predicate_object = (predicate.get("object", {})
                        if isinstance(predicate.get("object"), Mapping) else {})
    target_role = _role_name(obj.get("entity"))
    target = bindings.get(target_role) if target_role else None
    if isinstance(target, Mapping) and target.get("kind") == "entity":
        entity_type = target.get("entity_type")
        allowed = predicate_object.get("types", [])
        if entity_type in entities and entity_type not in allowed:
            problems.add("invalid_entity_ref", f"{path}.object.entity",
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


def _known_claim(value: Any, packs: Mapping[str, Any], path: str,
                 problems: _Problems) -> Optional[Mapping[str, Any]]:
    parsed = _parse_claim_ref(value)
    if parsed is None:
        return None
    pack_id, claim_id = parsed
    pack = packs.get(pack_id)
    if pack is None:
        problems.add("unknown_pack", path, f"unknown pack {pack_id!r}")
        return None
    claims = pack.get("claims", {}) if isinstance(pack, Mapping) else {}
    if not isinstance(claims, Mapping):
        return None
    claim = claims.get(claim_id)
    if claim is None:
        problems.add("unknown_claim", path,
                     f"pack {pack_id!r} has no claim {claim_id!r}")
        return None
    return claim


def _profile_binding_columns(profile_id: str, profile: Mapping[str, Any]
                             ) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for index, mapping in enumerate(profile["mappings"]):
        base = f"bundle.profiles.{profile_id}.mappings[{index}].bind"
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
