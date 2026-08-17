"""Pure Ledger v2 authoring bundle schema and manifest loader.

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


SETUP_VERSION = 2
LEDGER_FILE_VERSION = 2
CATALOG_FILE_VERSION = 1
DATAFLOW_FILE_VERSION = 1

LOGICAL_SECTIONS = (
    "tables", "virtual_joins", "vocabulary", "entities",
    "source_preparers", "mappers", "packs", "profiles", "sources",
    "chains", "enrichments",
)

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
_OBJECT_KINDS = frozenset({"entity_ref", "value", "event_ref"})
_SOURCE_UNITS = frozenset({"row", "group"})
_MAPPER_UNITS = frozenset({"event", "row", "group_by"})


class LedgerSetupValidationError(ValueError):
    """One stable validation issue with its exact authoring path."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class LedgerSetupBundle:
    """Immutable normalized logical bundle; mappings are recursively read-only."""

    _data: Mapping[str, Any]

    @property
    def setup_version(self) -> int:
        return int(self._data["setup_version"])

    def section(self, name: str) -> Mapping[str, Any]:
        if name not in LOGICAL_SECTIONS:
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
            self.add(code, key_path, "field is not allowed")
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
        "manifest_fields": ["setup_version", "ledger", "catalog", "dataflows"],
        "logical_fields": ["setup_version", *LOGICAL_SECTIONS],
        "binding_kinds": ["column", "constant", "entity"],
        "binding_origin": sorted(_BINDING_ORIGINS),
        "approval_status": sorted(_APPROVAL_STATUSES),
        "forbidden_sections": ["frames", "lookups", "positions"],
    }


def role_binding_kinds(role: Mapping[str, Any]) -> tuple[str, ...]:
    """Resolve one validated Role's effective binding kinds from the Pack contract."""
    if not isinstance(role, Mapping):
        raise TypeError("role must be a mapping")
    declared = role.get("allowed_binding_kinds")
    if _is_list(declared):
        return tuple(declared)
    return _default_binding_kinds(role.get("kind"))


def validate_bundle(value: Mapping[str, Any]) -> LedgerSetupBundle:
    issues = validate_bundle_errors(value)
    if issues:
        raise issues[0]
    normalized = _normalize(value)
    return LedgerSetupBundle(_freeze(normalized))


def validate_bundle_errors(value: Mapping[str, Any]
                           ) -> tuple[LedgerSetupValidationError, ...]:
    problems = _Problems()
    if not problems.exact(
            value, "bundle", required=("setup_version", *LOGICAL_SECTIONS)):
        return problems.finish()
    if value.get("setup_version") != SETUP_VERSION:
        problems.add(
            "unsupported_setup_version", "bundle.setup_version",
            f"supported setup_version is {SETUP_VERSION}")
    for section in LOGICAL_SECTIONS:
        if section in value and not isinstance(value[section], Mapping):
            problems.add("invalid_type", f"bundle.{section}", "must be an object")

    if isinstance(value.get("tables"), Mapping):
        _validate_tables(value["tables"], problems)
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
    for section in ("chains", "enrichments"):
        if isinstance(value.get(section), Mapping):
            _validate_opaque_declarations(value[section], f"bundle.{section}", problems)

    # Cross-validation only consumes structurally sound descriptors.  This makes every
    # malformed JSON shape a stable validation result instead of an AttributeError or
    # TypeError from a later semantic lookup.
    if problems.items:
        return problems.finish()
    if all(isinstance(value.get(name), Mapping) for name in LOGICAL_SECTIONS):
        _cross_validate(value, problems)
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


def load_setup_bundle(root: str | Path, *, manifest_name: str = "manifest.json"
                      ) -> LedgerSetupBundle:
    """Load exactly the files named by one manifest under ``root``."""
    root_path = Path(root).resolve(strict=True)
    if not root_path.is_dir():
        raise LedgerSetupValidationError(
            "invalid_config_root", "config_root", "must be a directory")
    manifest_path = _resolve_config_path(
        root_path, manifest_name, "manifest", require_json=True)
    manifest = _read_json(manifest_path, "manifest")
    _validate_manifest(manifest)

    slots = {
        "ledger": manifest["ledger"],
        "catalog.tables": manifest["catalog"]["tables"],
        "catalog.virtual_joins": manifest["catalog"]["virtual_joins"],
        "dataflows.chains": manifest["dataflows"]["chains"],
        "dataflows.enrichments": manifest["dataflows"]["enrichments"],
    }
    resolved: dict[str, Path] = {}
    seen_paths: dict[Path, str] = {}
    for slot, relative in slots.items():
        path = _resolve_config_path(root_path, relative, f"manifest.{slot}",
                                    require_json=True)
        if path in seen_paths:
            raise LedgerSetupValidationError(
                "duplicate_manifest_path", f"manifest.{slot}",
                f"same file is already owned by manifest.{seen_paths[path]}")
        seen_paths[path] = slot
        resolved[slot] = path

    declared = {manifest_path, *resolved.values()}
    extras = sorted(
        path.resolve() for path in root_path.rglob("*.json")
        if path.resolve() not in declared)
    if extras:
        relative = extras[0].relative_to(root_path).as_posix()
        raise LedgerSetupValidationError(
            "unlisted_config_file", f"config_root.{relative}",
            "JSON file is not listed by manifest")

    ledger = _read_json(resolved["ledger"], "ledger_config")
    tables = _read_json(resolved["catalog.tables"], "catalog.tables")
    joins = _read_json(resolved["catalog.virtual_joins"], "catalog.virtual_joins")
    chains = _read_json(resolved["dataflows.chains"], "dataflows.chains")
    enrichments = _read_json(
        resolved["dataflows.enrichments"], "dataflows.enrichments")
    _validate_file_root(
        ledger, "ledger_config", LEDGER_FILE_VERSION,
        ("vocabulary", "entities", "source_preparers", "mappers", "packs",
         "profiles", "sources"))
    _validate_file_root(tables, "catalog.tables", CATALOG_FILE_VERSION, ("tables",))
    _validate_file_root(
        joins, "catalog.virtual_joins", CATALOG_FILE_VERSION, ("rules",))
    _validate_file_root(chains, "dataflows.chains", DATAFLOW_FILE_VERSION, ("chains",))
    _validate_file_root(
        enrichments, "dataflows.enrichments", DATAFLOW_FILE_VERSION,
        ("enrichments",))

    logical = {
        "setup_version": manifest["setup_version"],
        "tables": tables["tables"],
        "virtual_joins": joins["rules"],
        "vocabulary": ledger["vocabulary"],
        "entities": ledger["entities"],
        "source_preparers": ledger["source_preparers"],
        "mappers": ledger["mappers"],
        "packs": ledger["packs"],
        "profiles": ledger["profiles"],
        "sources": ledger["sources"],
        "chains": chains["chains"],
        "enrichments": enrichments["enrichments"],
    }
    return validate_bundle(logical)


def _validate_manifest(value: Any) -> None:
    problems = _Problems()
    if problems.exact(
            value, "manifest", required=("setup_version", "ledger", "catalog", "dataflows")):
        if value.get("setup_version") != SETUP_VERSION:
            problems.add(
                "unsupported_setup_version", "manifest.setup_version",
                f"supported setup_version is {SETUP_VERSION}")
        problems.exact(
            value.get("catalog"), "manifest.catalog",
            required=("tables", "virtual_joins"))
        problems.exact(
            value.get("dataflows"), "manifest.dataflows",
            required=("chains", "enrichments"))
    issues = problems.finish()
    if issues:
        raise issues[0]


def _validate_file_root(value: Any, path: str, expected_version: int,
                        sections: Sequence[str]) -> None:
    problems = _Problems()
    if problems.exact(value, path, required=("schema_version", *sections)):
        if value.get("schema_version") != expected_version:
            problems.add(
                "unsupported_file_version", f"{path}.schema_version",
                f"supported schema_version is {expected_version}")
        for section in sections:
            if section in value and not isinstance(value[section], Mapping):
                problems.add("invalid_type", f"{path}.{section}", "must be an object")
    issues = problems.finish()
    if issues:
        raise issues[0]


def _validate_tables(section: Mapping[str, Any], problems: _Problems) -> None:
    for table_id in sorted(section, key=str):
        path = f"bundle.tables.{table_id}"
        _nonblank_id(table_id, path, problems)
        table = section[table_id]
        if not problems.exact(
                table, path, required=("columns",),
                optional=("business_key", "composite_key", "indexes")):
            continue
        columns = table.get("columns")
        if not isinstance(columns, Mapping) or not columns:
            problems.add("invalid_relation", f"{path}.columns", "must be a non-empty object")
        else:
            for name in sorted(columns, key=str):
                _nonblank_text(name, f"{path}.columns.{name}", problems)
                _nonblank_text(columns[name], f"{path}.columns.{name}", problems)
        for field in ("business_key", "composite_key"):
            if field in table:
                _column_list_or_text(table[field], f"{path}.{field}", problems)
                for index, column in enumerate(_column_values(table[field])):
                    if isinstance(columns, Mapping) and column not in columns:
                        suffix = f"[{index}]" if _is_list(table[field]) else ""
                        problems.add(
                            "unknown_column", f"{path}.{field}{suffix}",
                            f"key column {column!r} is not declared by the relation")
        indexes = table.get("indexes", [])
        if not _is_list(indexes):
            problems.add("invalid_type", f"{path}.indexes", "must be a list")
        else:
            index_names: set[str] = set()
            for index, item in enumerate(indexes):
                ipath = f"{path}.indexes[{index}]"
                if problems.exact(item, ipath, required=("name", "columns", "unique")):
                    name = item.get("name")
                    _nonblank_text(name, f"{ipath}.name", problems)
                    if isinstance(name, str):
                        if name in index_names:
                            problems.add("duplicate_id", f"{ipath}.name",
                                         f"index name {name!r} is duplicated")
                        index_names.add(name)
                    _nonblank_list(item.get("columns"), f"{ipath}.columns", problems)
                    for column_index, column in enumerate(_column_values(item.get("columns"))):
                        if isinstance(columns, Mapping) and column not in columns:
                            problems.add(
                                "unknown_column",
                                f"{ipath}.columns[{column_index}]",
                                f"index column {column!r} is not declared by the relation")
                    if not isinstance(item.get("unique"), bool):
                        problems.add("invalid_type", f"{ipath}.unique", "must be boolean")


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
                          "cursor", "preparation", "mapper_id")):
            continue
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
                occurred, f"{path}.driver.occurred_at", required=("column", "timezone")):
            _nonblank_text(occurred.get("column"),
                           f"{path}.driver.occurred_at.column", problems)
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


def _validate_opaque_declarations(section: Mapping[str, Any], path: str,
                                  problems: _Problems) -> None:
    for name in sorted(section, key=str):
        _nonblank_id(name, f"{path}.{name}", problems)
        if not isinstance(section[name], Mapping):
            problems.add("invalid_type", f"{path}.{name}", "must be an object")
        else:
            _scan_unsafe_keys(section[name], f"{path}.{name}", problems)


def _cross_validate(bundle: Mapping[str, Any], problems: _Problems) -> None:
    tables = bundle["tables"]
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

    for source_id, source in sources.items():
        path = f"bundle.sources.{source_id}"
        relation = source.get("relation")
        driver = source["driver"]
        base_columns = []
        for field in ("identity", "group_by", "order_by"):
            if _is_list(driver.get(field)):
                base_columns.extend(driver[field])
        if isinstance(driver.get("cursor"), Mapping) and _is_list(driver["cursor"].get("columns")):
            base_columns.extend(driver["cursor"]["columns"])
        if isinstance(driver.get("occurred_at"), Mapping):
            base_columns.append(driver["occurred_at"].get("column"))
        _relation_columns(relation, base_columns, tables, f"{path}.relation", problems)
        physical = set(_table_columns(tables, relation))
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
        problems.add("unknown_relation", path, f"unknown relation {relation!r}")
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


def _resolve_config_path(root: Path, relative: Any, path: str, *, require_json: bool) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise LedgerSetupValidationError("unsafe_manifest_path", path,
                                         "must be a non-blank relative path")
    if relative != relative.strip() or "\\" in relative or any(c in relative for c in "*?[]"):
        raise LedgerSetupValidationError("unsafe_manifest_path", path,
                                         "must be a canonical relative path without glob syntax")
    candidate = Path(relative)
    if candidate.is_absolute() or ":" in relative or any(part in ("", ".", "..")
                                                          for part in candidate.parts):
        raise LedgerSetupValidationError("unsafe_manifest_path", path,
                                         "path must stay below the config root")
    if require_json and candidate.suffix.lower() != ".json":
        raise LedgerSetupValidationError("unsafe_manifest_path", path,
                                         "config path must end in .json")
    try:
        resolved = (root / candidate).resolve(strict=True)
    except FileNotFoundError as exc:
        raise LedgerSetupValidationError("missing_config_file", path,
                                         f"file {relative!r} does not exist") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise LedgerSetupValidationError("unsafe_manifest_path", path,
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
