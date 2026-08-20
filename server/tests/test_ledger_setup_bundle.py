"""Stage 2 contract tests for the pure Ledger v2 setup bundle boundary."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from ledger import setup_bundle as setup_bundle_module
from ledger.setup_bundle import (
    LedgerSetupValidationError,
    LOGICAL_SECTIONS,
    SETUP_VERSION,
    bundle_readiness_errors,
    public_bundle_schema,
    require_ready_bundle,
)
# `validate_bundle`, `validate_bundle_errors` and `load_setup_bundle` are NOT imported:
# thin wrappers below supply the fixture plant's catalog, which the real functions now
# require to answer any physical question. Reached through `setup_bundle_module`.


def binding(column, *, status="approved", origin="user_declared", reason=None):
    out = {
        "kind": "column",
        "column": column,
        "binding_origin": origin,
        "approval_status": status,
    }
    if reason is not None:
        out["suggestion_reason"] = reason
    return out


def entity(entity_type, key_name, column, *, status="approved"):
    return {
        "kind": "entity",
        "entity_type": entity_type,
        "keys": {key_name: binding(column, status=status)},
        "binding_origin": "user_declared",
        "approval_status": "approved",
    }


def logical_catalog(*, source_name="input_rows", prefix=""):
    """The PHYSICAL half of the fixture, in `table_config.json` shape.

    🔴 THIS IS A SEPARATE FUNCTION ON PURPOSE, AND IT MUST NEVER BE DERIVED FROM THE
    BUNDLE.  The ledger stopped carrying its own `tables` section precisely because a
    physical fact the ledger states about itself is checked against nothing.  A fixture
    that built its catalog out of the bundle under test would restore that, and every
    "unknown column" assertion below would be unfalsifiable -- the two sides would agree
    by construction.  They are written out twice HERE, in a test, exactly so that a test
    can make them DISAGREE.

    In production there is no second copy at all: `server/config/table_config.json` is
    the only author, and `schema_drift` checks it against the database.
    """
    record = prefix + "record_id"
    event = prefix + "event_key"
    occurred = prefix + "event_at"
    source_key = prefix + "source_id"
    target_key = prefix + "target_id"
    join_key = prefix + "join_id"
    return {
        source_name: {
            "columns": {
                record: "string", event: "string", occurred: "datetime",
                source_key: "string", join_key: "string",
            },
            "business_key": record,
        },
        prefix + "reference_rows": {
            "columns": {join_key: "string", target_key: "string"},
            "business_key": join_key,
            "indexes": [{"name": prefix + "uq_reference", "columns": [join_key],
                         "unique": True}],
        },
    }


#: The fixture plant's whole physical schema: the default variant plus every named
#: variant the suite builds.  One catalog for all of them, because a real deployment has
#: ONE `table_config.json` and a per-test catalog would let a bundle be validated against
#: a world shaped to fit it.
DEFAULT_CATALOG = {
    **logical_catalog(),
    **logical_catalog(source_name="dt_log"),
    **logical_catalog(source_name="arbitrary_rows", prefix="renamed_"),
    **logical_catalog(source_name="alternate_rows", prefix="z_"),
}


def validate_bundle_errors(value, *, catalog=None):
    """Fixture-defaulting wrapper. Production callers pass nothing and read the live
    `table_config.json`; here the fixture plant's catalog stands in for it."""
    return setup_bundle_module.validate_bundle_errors(
        value, catalog=DEFAULT_CATALOG if catalog is None else catalog)


def validate_bundle(value, *, catalog=None):
    return setup_bundle_module.validate_bundle(
        value, catalog=DEFAULT_CATALOG if catalog is None else catalog)


def load_setup_bundle(root, *, config_name=None, catalog=None):
    kwargs = {} if config_name is None else {"config_name": config_name}
    return setup_bundle_module.load_setup_bundle(
        root, catalog=DEFAULT_CATALOG if catalog is None else catalog, **kwargs)


def logical_bundle(*, source_name="input_rows", prefix=""):
    record = prefix + "record_id"
    event = prefix + "event_key"
    occurred = prefix + "event_at"
    source_key = prefix + "source_id"
    target_key = prefix + "target_id"
    join_key = prefix + "join_id"
    right_relation = prefix + "reference_rows"
    return {
        "setup_version": SETUP_VERSION,
        "virtual_joins": {
            "input_to_reference": {
                "left_table": source_name,
                "right_table": right_relation,
                "join_key": [{"left": join_key, "right": join_key}],
                "expose": [target_key],
                "join_cardinality": "one",
                "enabled": True,
            },
        },
        "vocabulary": {
            "moves_to@1": {
                "status": "active",
                "layer": "ontology",
                "subjects": ["InputEntity@1"],
                "object": {
                    "kind": "entity_ref",
                    "types": ["OutputEntity@1"],
                    "qualifiers": {"required": [], "optional": ["event_key"]},
                },
            },
        },
        "entities": {
            "InputEntity@1": {"keys": ["input_id"]},
            "OutputEntity@1": {"keys": ["output_id"]},
        },
        "packs": {
            "movement@1": {
                "claims": {
                    "transition": {
                        "roles": {
                            "subject": {"kind": "entity", "required": True},
                            "target": {"kind": "entity", "required": True},
                            "occurred_at": {"kind": "time", "required": True},
                            "event_key": {"kind": "identity", "required": False},
                        },
                        "emit": {
                            "predicate": "moves_to@1",
                            "subject": "$subject",
                            "object": {
                                "kind": "entity_ref",
                                "entity": "$target",
                                "qualifiers": {"event_key": "$event_key?"},
                            },
                            "occurred_at": "$occurred_at",
                        },
                    },
                },
            },
        },
        "sources": {
            source_name: {
                "relation": source_name,
                "read": {
                    "unit": "group",
                    "identity": [event],
                    "group_by": [event],
                    "order_by": [record],
                    "occurred_at": {"column": occurred, "timezone": "Asia/Seoul"},
                    "cursor": {"columns": [occurred, record]},
                },
                "prepare": {
                    "implementation_id": "prepare-input",
                    "implementation_version": 1,
                    "input_columns": [join_key],
                    "output_columns": {target_key: "string"},
                    "accepts_verified_join_rules": True,
                    "inherit_virtual_join_rules": ["input_to_reference"],
                },
                "map": {
                    "implementation_id": "map-transition-role",
                    "implementation_version": 1,
                    "unit": {"kind": "event"},
                    "input_columns": [source_key, target_key, occurred, event],
                },
                "bind": {
                    "mappings": [{
                        "mapping_id": "main_transition",
                        "use": "movement@1/transition",
                        "bind": {
                            "subject": entity("InputEntity@1", "input_id", source_key),
                            "target": entity("OutputEntity@1", "output_id", target_key),
                            "occurred_at": binding(occurred),
                            "event_key": binding(event),
                        },
                    }],
                },
            },
        },
    }


#: The preparer, the mapper and the profile have no section and no id of their own since
#: 2026-08-20 -- they are clauses of a source.  These two say so once, so a test that pokes at a body
#: reads as "this source's mapper" rather than repeating a five-key path.
MAPPER_PATH = "bundle.sources.input_rows.map"
PREPARATION_PATH = "bundle.sources.input_rows.prepare"
PROFILE_PATH = "bundle.sources.input_rows.bind"


def driver_mapper(bundle, source_name="input_rows"):
    return bundle["sources"][source_name]["map"]


def driver_preparation(bundle, source_name="input_rows"):
    return bundle["sources"][source_name]["prepare"]


def source_profile(bundle, source_name="input_rows"):
    return bundle["sources"][source_name]["bind"]


def objectless_register_bundle():
    raw = logical_bundle()
    raw["vocabulary"]["register@1"] = {
        "status": "active", "layer": "ontology",
        "subjects": ["InputEntity@1"],
        "object": {
            "kind": "none",
            "qualifiers": {"required": [], "optional": []},
        },
    }
    raw["packs"]["registration@1"] = {"claims": {"register": {
        "roles": {
            "subject": {"kind": "entity", "required": True},
            "occurred_at": {"kind": "time", "required": True},
        },
        "emit": {
            "predicate": "register@1", "subject": "$subject",
            "object": {"kind": "none"}, "occurred_at": "$occurred_at",
        },
    }}}
    source_profile(raw)["mappings"].append({
        "mapping_id": "register_input", "use": "registration@1/register",
        "bind": {
            "subject": entity("InputEntity@1", "input_id", "source_id"),
            "occurred_at": binding("event_at"),
        },
    })
    return raw


def reverse_mappings(value):
    if isinstance(value, dict):
        return {key: reverse_mappings(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [reverse_mappings(item) for item in value]
    return value


def json_nodes(value, path=()):
    yield path, value
    if isinstance(value, dict):
        for key in sorted(value):
            yield from json_nodes(value[key], (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from json_nodes(item, (*path, index))


def replace_json_node(value, path, replacement):
    if not path:
        return replacement
    out = copy.deepcopy(value)
    cursor = out
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement
    return out


def assert_structured_errors(errors):
    assert errors
    for error in errors:
        assert isinstance(error.code, str) and error.code
        assert isinstance(error.path, str) and error.path
        assert isinstance(error.message, str) and error.message
        assert error.to_mapping() == {
            "code": error.code, "path": error.path, "message": error.message}


def write_tree(root: Path, bundle=None, *, manifest=None):
    bundle = copy.deepcopy(bundle or logical_bundle())
    files = {
        "ledger_config.json": dict(bundle),
    }
    for relative, value in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return files


def issue(bundle, code):
    return next(item for item in validate_bundle_errors(bundle) if item.code == code)


def test_public_schema_is_the_single_logical_contract():
    schema = public_bundle_schema()
    assert schema["setup_version"] == 3
    assert schema["config_file"] == "ledger_config.json"
    assert schema["logical_fields"] == ["setup_version", *LOGICAL_SECTIONS]
    assert schema["optional_fields"] == ["virtual_joins"]
    assert schema["binding_kinds"] == ["column", "constant", "entity"]
    # manifest/chains/enrichments joined the FORBIDDEN list rather than merely
    # disappearing: a root still carrying one must be refused, not quietly ignored, or a
    # converted-but-not-cleaned tree looks like it loaded what it did not.
    # `tables` joined them for the same reason (owner, 2026-08-18): a physical
    # declaration left sitting in this file that nothing reads is exactly the silent
    # second copy the section was removed for.
    # `source_preparers`/`mappers` joined on 2026-08-20 for the third time in the same
    # shape: both moved INTO the source itself, so a file still carrying them at the root
    # has to be named, not skipped.
    assert schema["forbidden_sections"] == [
        "frames", "lookups", "positions", "manifest", "chains", "enrichments",
        "tables", "source_preparers", "mappers", "profiles"]
    # And the contract SAYS where the physical half went, so a screen can name the file
    # instead of leaving an operator to work out an absence.
    assert schema["physical_schema_file"] == "table_config.json"


def test_objectless_predicate_and_pack_emission_have_one_closed_spelling():
    validated = validate_bundle(objectless_register_bundle())
    normalized = validated.to_mapping()

    assert normalized["vocabulary"]["register@1"]["object"] == {
        "kind": "none", "qualifiers": {"required": [], "optional": []}}
    assert normalized["packs"]["registration@1"]["claims"]["register"][
        "emit"]["object"] == {"kind": "none"}


@pytest.mark.parametrize(
    ("mutation", "path"),
    [
        (lambda raw: raw["vocabulary"]["register@1"]["object"].update(
            {"types": ["InputEntity@1"]}),
         "bundle.vocabulary.register@1.object.types"),
        (lambda raw: raw["vocabulary"]["register@1"]["object"][
            "qualifiers"]["optional"].append("unexpected"),
         "bundle.vocabulary.register@1.object.qualifiers"),
        (lambda raw: raw["packs"]["registration@1"]["claims"]["register"][
            "emit"]["object"].update({"value": "$subject"}),
         "bundle.packs.registration@1.claims.register.emit.object"),
    ],
)
def test_objectless_contract_rejects_every_payload_surface(mutation, path):
    raw = objectless_register_bundle()
    mutation(raw)

    errors = validate_bundle_errors(raw)

    assert any(item.path == path and item.code in {
        "invalid_predicate", "invalid_emission", "unknown_field"}
               for item in errors)


def test_same_bundle_normalizes_and_serializes_deterministically():
    first = validate_bundle(logical_bundle())
    second = validate_bundle(reverse_mappings(logical_bundle()))
    assert first.serialize() == second.serialize()
    assert first.to_mapping() == second.to_mapping()
    # 🔴 This literal is a FINGERPRINT OF THE FIXTURE, not of the serializer, so it moves
    # exactly when the fixture's shape moves and never otherwise. It changed here because
    # `chains` and `enrichments` left the bundle -- two fewer keys to serialize. If it
    # ever changes without a deliberate shape change, the serializer stopped being
    # deterministic and THAT is the bug; do not refresh this value to make a red go green.
    # was 93bb7009... while the bundle still carried chains + enrichments.
    # was c08e7183... while it still carried `tables` (owner ruling 2026-08-18 moved the
    # physical schema to `table_config.json`; one fewer key to serialize).
    # was 11571931... while `source_preparers` and `mappers` were still root sections
    # (owner ruling 2026-08-20 folded both bodies into `sources.*.driver`; two fewer keys
    # at the root, the same bodies one level down).
    # was 2a21fed8... while `profiles` was still a root section (same owner, same evening;
    # the body moved to `sources.*.profile` and shed its `source` field).
    # was b884892c... while a source had `relation` / `profile` / `driver`. On 2026-08-21
    # `driver` split into `read` / `prepare` / `map`, `profile` became `bind`, and
    # `map.emits`, `bind.packs` and every default `binding_origin` stopped being written.
    assert hashlib.sha256(first.serialize().encode()).hexdigest() == (
        "3260c937828e4c7537baf6d0b00ecd62a9cdedca4fd8ec9b8788de7d13582e3d")


def test_list_order_is_preserved_but_object_order_is_not():
    original = logical_bundle()
    reversed_keys = reverse_mappings(original)
    assert validate_bundle(original).serialize() == validate_bundle(reversed_keys).serialize()
    changed = copy.deepcopy(original)
    changed["sources"]["input_rows"]["read"]["cursor"]["columns"].reverse()
    assert validate_bundle(original).serialize() != validate_bundle(changed).serialize()


def test_loaded_files_produce_the_same_logical_bundle(tmp_path):
    write_tree(tmp_path)
    loaded = load_setup_bundle(tmp_path)
    assert loaded.serialize() == validate_bundle(logical_bundle()).serialize()


def test_file_key_order_does_not_change_loaded_bundle(tmp_path):
    """MOVED from test_manifest_and_file_key_order_...: the manifest half is gone, the
    property is not. Key order inside the one file must not reach the loaded bundle."""
    one, two = tmp_path / "one", tmp_path / "two"
    write_tree(one)
    write_tree(two, reverse_mappings(logical_bundle()))
    assert load_setup_bundle(one).serialize() == load_setup_bundle(two).serialize()


@pytest.mark.parametrize("unsafe", ["../outside.json", "C:/outside.json", "*.json"])
def test_unsafe_config_paths_are_rejected(tmp_path, unsafe):
    """MOVED from test_manifest_unsafe_paths_are_rejected.

    The manifest no longer names a file, but the traversal/absolute/glob guard it fed
    still stands between a caller and the filesystem: `load_setup_bundle` takes the file
    name as `config_name`. The escape refused is the same one; only the field carrying it
    changed."""
    write_tree(tmp_path)
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path, config_name=unsafe)
    assert caught.value.code == "unsafe_config_path"
    assert caught.value.path == "config_root"


def test_unlisted_json_file_is_rejected_not_auto_loaded(tmp_path):
    write_tree(tmp_path)
    (tmp_path / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path)
    assert caught.value.code == "unlisted_config_file"
    assert caught.value.path == "config_root.extra.json"


def test_missing_config_file_is_rejected_by_name(tmp_path):
    """MOVED from test_missing_manifest_file_...: there are no slots left to name, but an
    absent config is still a refusal rather than an empty bundle."""
    write_tree(tmp_path)
    (tmp_path / "ledger_config.json").unlink()
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path)
    assert caught.value.code == "missing_config_file"
    assert caught.value.path == "config_root"


def test_symlink_escape_is_rejected_when_host_supports_symlinks(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    write_tree(root)
    link = root / "escaped.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"host cannot create a file symlink: {exc}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["ledger"] = "escaped.json"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(root)
    assert caught.value.code == "unsafe_manifest_path"
    assert caught.value.path == "manifest.ledger"


# RETIRED: test_duplicate_manifest_path_is_rejected.
# It proved two manifest slots could not name one file. THE MACHINERY IS GONE -- there are
# no slots, and one file cannot collide with itself. Retired because the thing it guarded
# no longer exists, not because it stopped passing.


def test_duplicate_json_key_is_rejected_before_normalization(tmp_path):
    write_tree(tmp_path)
    (tmp_path / "ledger_config.json").write_text(
        '{"schema_version":2,"vocabulary":{},"vocabulary":{},'
        '"entities":{},"packs":{},"sources":{}}', encoding="utf-8")
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path)
    assert caught.value.code == "duplicate_id"
    assert caught.value.path == "ledger_config"


@pytest.mark.parametrize("raw", ["{", "[1,", '{"x":NaN}'])
def test_malformed_json_text_has_structured_rejection(tmp_path, raw):
    write_tree(tmp_path)
    (tmp_path / "ledger_config.json").write_text(raw, encoding="utf-8")
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path)
    assert caught.value.code == "invalid_json"
    assert caught.value.path == "ledger_config"
    assert_structured_errors((caught.value,))


def test_non_utf8_json_has_structured_rejection(tmp_path):
    write_tree(tmp_path)
    (tmp_path / "ledger_config.json").write_bytes(b"\xff\xfe{")
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path)
    assert caught.value.code == "invalid_json"
    assert caught.value.path == "ledger_config"
    assert_structured_errors((caught.value,))


def test_excessively_nested_json_has_structured_rejection(tmp_path):
    write_tree(tmp_path)
    raw = "[" * 2000 + "0" + "]" * 2000
    (tmp_path / "ledger_config.json").write_text(raw, encoding="utf-8")
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path)
    assert caught.value.code in {"invalid_json", "invalid_type"}
    assert caught.value.path == "ledger_config"
    assert_structured_errors((caught.value,))


def test_unsupported_setup_version_has_a_stable_error(tmp_path):
    """MOVED from test_unsupported_setup_and_file_versions_...

    The per-file `schema_version` half is RETIRED with the five files it versioned; one
    `setup_version` now states the grammar generation for the whole document. Checked
    through both doors on purpose -- a loaded file and an in-memory bundle are two ways
    into the same compiler and have disagreed before."""
    bundle = logical_bundle()
    bundle["setup_version"] = 9
    assert issue(bundle, "unsupported_setup_version").path == "bundle.setup_version"

    write_tree(tmp_path)
    path = tmp_path / "ledger_config.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["setup_version"] = 9
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(LedgerSetupValidationError) as caught:
        load_setup_bundle(tmp_path)
    assert caught.value.code == "unsupported_setup_version"
    assert caught.value.path == "ledger_config.setup_version"


@pytest.mark.parametrize("field", ["positions", "frames", "lookups"])
def test_retired_root_sections_are_unknown_and_unsafe(field):
    bundle = logical_bundle()
    bundle[field] = {}
    errors = validate_bundle_errors(bundle)
    assert any(item.code == "unsafe_declaration" and item.path == f"bundle.{field}"
               for item in errors)


@pytest.mark.parametrize(
    ("steps", "suffix"),
    [
        ([{"sql": "DROP"}], "steps[0].sql"),
        ([[{"sql": "DROP"}]], "steps[0][0].sql"),
        ([[[{"sql": "DROP"}]]], "steps[0][0][0].sql"),
    ],
)
def test_unsafe_execution_keys_are_found_through_nested_arrays(steps, suffix):
    """MOVED off the chains/enrichments vector, which is gone.

    The RECURSION is what is under test -- an executable key hidden several arrays deep
    must still be found -- and it is still reachable, through a virtual join's `fold`.
    Deleting this with the sections would have retired a LIVE protection just because its
    old front door closed."""
    bundle = logical_bundle()
    bundle["virtual_joins"]["input_to_reference"]["fold"] = {"steps": steps}

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    assert any(
        error.code == "unsafe_declaration"
        and error.path == f"bundle.virtual_joins.input_to_reference.fold.{suffix}"
        for error in errors)


@pytest.mark.parametrize("value", ["text", b"bytes", bytearray(b"bytes")])
def test_text_and_binary_values_are_not_treated_as_json_arrays(value):
    assert setup_bundle_module._is_list(value) is False


def test_declared_lookup_binding_is_rejected():
    bundle = logical_bundle()
    target = source_profile(bundle)["mappings"][0]["bind"]["event_key"]
    target.clear()
    target.update({
        "kind": "declared_lookup", "lookup_id": "x", "select": "y",
        "binding_origin": "user_declared", "approval_status": "approved",
    })
    error = issue(bundle, "invalid_binding")
    assert error.path.endswith("bind.event_key.kind")


def test_unknown_relation_and_column_have_exact_paths():
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["relation"] = "missing_rows"
    relation = issue(bundle, "unknown_relation")
    assert relation.path == "bundle.sources.input_rows.relation"
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["read"]["cursor"]["columns"][0] = "missing_col"
    column = issue(bundle, "unknown_column")
    assert column.path == "bundle.sources.input_rows.relation"
    assert "missing_col" in column.message


def test_timezone_must_be_explicit_and_valid():
    bundle = logical_bundle()
    del bundle["sources"]["input_rows"]["read"]["occurred_at"]["timezone"]
    assert any(item.path.endswith("occurred_at.timezone") and item.code == "missing_field"
               for item in validate_bundle_errors(bundle))
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["read"]["occurred_at"]["timezone"] = "Moon/Base"
    assert issue(bundle, "invalid_timezone").path.endswith("occurred_at.timezone")


def test_time_origin_requires_exactly_one_of_column_or_basis():
    """A source says WHERE its time came from, and says it once.

    Before this, the only legal shape named a column, so a table carrying no world time
    could only be declared by pointing at a non-time column or pinning a constant into the
    profile - both of which produce atoms that READ as world time. Declaring the absence is
    the honest form; declaring BOTH would leave a reader guessing which one won.
    """
    bundle = logical_bundle()
    del bundle["sources"]["input_rows"]["read"]["occurred_at"]["column"]
    neither = issue(bundle, "invalid_driver")
    assert neither.path.endswith("read.occurred_at")
    assert "neither" in neither.message

    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["read"]["occurred_at"]["basis"] = "ingested"
    both = issue(bundle, "invalid_driver")
    assert both.path.endswith("read.occurred_at")
    assert "both" in both.message


def test_time_basis_is_a_closed_list():
    """An open string here would let a typo become a silent claim about time."""
    bundle = logical_bundle()
    occurred = bundle["sources"]["input_rows"]["read"]["occurred_at"]
    del occurred["column"]
    occurred["basis"] = "guessed"
    error = issue(bundle, "invalid_driver")
    assert error.path.endswith("read.occurred_at.basis")
    assert "guessed" in error.message
    assert "ingested" in error.message


def test_a_declared_basis_names_no_source_column():
    """The basis reads the row's own ingestion stamp, so it must not be column-checked.

    Without this the cross-check would look for a column named ``None`` in the relation and
    report a missing column that the author never declared.
    """
    bundle = logical_bundle()
    occurred = bundle["sources"]["input_rows"]["read"]["occurred_at"]
    del occurred["column"]
    occurred["basis"] = "ingested"
    codes = {item.code for item in validate_bundle_errors(bundle)}
    assert "unknown_column" not in codes
    assert "invalid_driver" not in codes


def test_entity_binding_requires_exact_registered_identity_keys():
    bundle = logical_bundle()
    keys = source_profile(bundle)["mappings"][0]["bind"]["subject"]["keys"]
    keys["extra"] = binding("source_id")
    error = issue(bundle, "invalid_entity_ref")
    assert error.path.endswith("bind.subject.keys")


@pytest.mark.parametrize("invalid", [
    {"bad": True}, [], None, True, 1, "", "   ", " string ",
])
def test_entity_key_types_values_are_trimmed_nonblank_strings(invalid):
    bundle = logical_bundle()
    bundle["entities"]["InputEntity@1"]["key_types"] = {"input_id": invalid}

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    assert any(
        error.path == "bundle.entities.InputEntity@1.key_types.input_id"
        and error.code == "invalid_type"
        for error in errors)


@pytest.mark.parametrize("invalid", [[], None, True, 1, "string"])
def test_entity_key_types_optional_branch_requires_an_object(invalid):
    bundle = logical_bundle()
    bundle["entities"]["InputEntity@1"]["key_types"] = invalid

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    assert any(
        error.path == "bundle.entities.InputEntity@1.key_types"
        and error.code == "invalid_type"
        for error in errors)


def test_entity_key_types_optional_branch_accepts_matching_string_types():
    bundle = logical_bundle()
    bundle["entities"]["InputEntity@1"]["key_types"] = {"input_id": "string"}
    bundle["entities"]["OutputEntity@1"]["key_types"] = {"output_id": "string"}
    assert validate_bundle_errors(bundle) == ()


def test_pack_vocabulary_subject_and_object_mismatch_are_rejected():
    bundle = logical_bundle()
    bundle["vocabulary"]["moves_to@1"]["subjects"] = ["OutputEntity@1"]
    subject = issue(bundle, "invalid_entity_ref")
    assert subject.path.endswith("emit.subject")
    bundle = logical_bundle()
    bundle["packs"]["movement@1"]["claims"]["transition"]["emit"]["object"]["kind"] = "value"
    obj = issue(bundle, "invalid_predicate")
    assert obj.path.endswith("emit.object.kind")


def test_unknown_pack_claim_role_and_join_are_named():
    cases = []
    bundle = logical_bundle()
    source_profile(bundle)["mappings"][0]["use"] = "absent@1/transition"
    cases.append((bundle, "unknown_pack"))
    bundle = logical_bundle()
    source_profile(bundle)["mappings"][0]["use"] = "movement@1/absent"
    cases.append((bundle, "unknown_claim"))
    bundle = logical_bundle()
    source_profile(bundle)["mappings"][0]["bind"]["absent"] = binding("event_key")
    cases.append((bundle, "unknown_role"))
    # RETIRED 2026-08-20 with the references they measured: the preparer and the mapper
    # are bodies inside the driver now, so there is no id left to misspell and no
    # `unknown_source_preparer` / `unknown_mapper` refusal to raise.
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["prepare"]["inherit_virtual_join_rules"] = ["absent"]
    cases.append((bundle, "unknown_join_rule"))
    for value, code in cases:
        assert any(item.code == code for item in validate_bundle_errors(value)), code


def test_unused_vocabulary_and_pack_are_still_cross_validated():
    bundle = logical_bundle()
    bundle["vocabulary"]["unused@1"] = {
        "status": "active", "layer": "ontology", "subjects": ["MissingEntity@1"],
        "object": {
            "kind": "entity_ref", "types": ["OutputEntity@1"],
            "qualifiers": {"required": [], "optional": []},
        },
    }
    bundle["packs"]["unused@1"] = {
        "claims": {"claim": copy.deepcopy(
            bundle["packs"]["movement@1"]["claims"]["transition"])}
    }
    bundle["packs"]["unused@1"]["claims"]["claim"]["emit"]["predicate"] = "missing@1"
    errors = validate_bundle_errors(bundle)
    assert any(error.code == "unknown_entity_type"
               and error.path.startswith("bundle.vocabulary.unused@1") for error in errors)
    assert any(error.code == "unknown_predicate"
               and error.path.startswith("bundle.packs.unused@1") for error in errors)


# RETIRED 2026-08-20 with the declaration they measured, not because they stopped passing:
# `test_unused_profile_entity_binding_is_cross_validated_against_its_source`,
# `test_unused_profile_leaf_column_is_cross_validated_against_event_frame`,
# `test_normal_unused_profile_still_validates_without_duplicate_errors` and the profile leg
# of the test above.  All four rested on a profile NO source selects.  The profile is a
# clause of a source now, so an unselected one cannot be written, and the second validation
# pass that existed to reach it -- and whose double-reporting the third test pinned -- is
# gone with it.  The predicates themselves did not retire: the two below assert the same
# `unknown_entity_type` and `unknown_column` on the only profile there can be.


def test_profile_entity_binding_is_cross_validated_against_its_source():
    bundle = logical_bundle()
    profile = source_profile(bundle)
    profile["mappings"][0]["bind"]["subject"]["entity_type"] = "Missing@1"

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    matches = [error for error in errors if error.code == "unknown_entity_type"]
    assert [error.path for error in matches] == [
        f"{PROFILE_PATH}.mappings[0].bind.subject.entity_type"]


def test_profile_leaf_column_is_cross_validated_against_event_frame():
    bundle = logical_bundle()
    profile = source_profile(bundle)
    profile["mappings"][0]["bind"]["subject"]["keys"]["input_id"][
        "column"] = "missing_column"

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    matches = [error for error in errors if error.code == "unknown_column"]
    assert [error.path for error in matches] == [
        f"{PROFILE_PATH}.mappings[0].bind.subject.keys.input_id.column"]


@pytest.mark.parametrize(
    ("mutation", "suffix"),
    [
        ("unknown_subject", "emit.subject"),
        ("wrong_subject_kind", "emit.subject"),
        ("wrong_time_kind", "emit.occurred_at"),
        ("wrong_object_kind", "emit.object.entity"),
        ("unknown_qualifier", "emit.object.qualifiers.event_key"),
        ("wrong_qualifier_kind", "emit.object.qualifiers.event_key"),
    ],
)
def test_emission_roles_must_exist_and_have_purpose_specific_kinds(mutation, suffix):
    bundle = logical_bundle()
    claim = bundle["packs"]["movement@1"]["claims"]["transition"]
    if mutation == "unknown_subject":
        claim["emit"]["subject"] = "$missing"
    elif mutation == "wrong_subject_kind":
        claim["roles"]["subject"]["kind"] = "attribute"
    elif mutation == "wrong_time_kind":
        claim["roles"]["occurred_at"]["kind"] = "attribute"
    elif mutation == "wrong_object_kind":
        claim["roles"]["target"]["kind"] = "identity"
    elif mutation == "unknown_qualifier":
        claim["emit"]["object"]["qualifiers"]["event_key"] = "$missing?"
    else:
        claim["roles"]["event_key"]["kind"] = "entity"
    errors = validate_bundle_errors(bundle)
    assert any(error.path.endswith(suffix)
               and error.code in {"unknown_role", "invalid_role_kind"}
               for error in errors)


def test_vocabulary_required_qualifier_missing_is_rejected_exactly():
    bundle = logical_bundle()
    bundle["vocabulary"]["moves_to@1"]["object"]["qualifiers"] = {
        "required": ["event_key"], "optional": []}
    del bundle["packs"]["movement@1"]["claims"]["transition"]["emit"][
        "object"]["qualifiers"]["event_key"]

    errors = validate_bundle_errors(bundle)

    assert [error.to_mapping() for error in errors] == [{
        "code": "missing_required_payload",
        "path": (
            "bundle.packs.movement@1.claims.transition.emit.object."
            "qualifiers.event_key"
        ),
        "message": "predicate 'moves_to@1' requires qualifier 'event_key'",
    }]


def test_vocabulary_undeclared_qualifier_is_rejected_exactly():
    bundle = logical_bundle()
    bundle["vocabulary"]["moves_to@1"]["object"]["qualifiers"] = {
        "required": [], "optional": ["event_key"]}
    bundle["packs"]["movement@1"]["claims"]["transition"]["emit"][
        "object"]["qualifiers"]["undeclared_payload"] = "$event_key?"

    errors = validate_bundle_errors(bundle)

    assert [error.to_mapping() for error in errors] == [{
        "code": "unknown_payload_field",
        "path": (
            "bundle.packs.movement@1.claims.transition.emit.object."
            "qualifiers.undeclared_payload"
        ),
        "message": (
            "predicate 'moves_to@1' does not allow qualifier "
            "'undeclared_payload'"
        ),
    }]


def test_the_only_place_a_source_names_a_claim_is_its_bind_mapping():
    """Retirement of `test_profile_packs_mapping_use_and_mapper_emits_are_mutually_closed`.

    That test drove `bind.packs` and `map.emits` out of agreement with `mappings[].use`
    and asserted three refusals.  None of the three can be provoked any more, and not
    because a check was relaxed: neither field exists, so the disagreement has nowhere to
    be written.  What replaces it is the statement that made them removable -- one
    declaration names the claim, and the compiled mapper's `emits` is that same set.
    """
    bundle = logical_bundle()
    source = bundle["sources"]["input_rows"]
    assert "packs" not in source["bind"]
    assert "emits" not in source["map"]
    validated = validate_bundle(bundle)
    assert set(validated.to_mapping()["sources"]["input_rows"]["bind"]) == {"mappings"}


def test_mapper_inputs_cover_profile_columns_and_preparer_outputs_do_not_collide():
    bundle = logical_bundle()
    driver_mapper(bundle)["input_columns"].remove("event_key")
    errors = validate_bundle_errors(bundle)
    assert any(error.code == "invalid_mapper"
               and "Profile column 'event_key'" in error.message for error in errors)

    bundle = logical_bundle()
    driver_preparation(bundle)["output_columns"]["source_id"] = "string"
    errors = validate_bundle_errors(bundle)
    assert any(error.code == "output_column_collision"
               and error.path.endswith("output_columns.source_id") for error in errors)


@pytest.mark.parametrize(
    ("unit", "group_by"),
    [("unknown", ["event_key"]), ("row", ["event_key"]), ("group", [])],
)
def test_source_unit_and_group_contract_is_fail_closed(unit, group_by):
    bundle = logical_bundle()
    driver = bundle["sources"]["input_rows"]["read"]
    driver["unit"] = unit
    driver["group_by"] = group_by
    assert any(error.code == "invalid_driver" for error in validate_bundle_errors(bundle))


def test_a_key_naming_a_column_the_relation_lacks_certifies_nothing():
    """MOVED, not lost: this used to read
    `test_catalog_key_index_columns_and_join_uniqueness_are_validated` and assert that a
    `tables` section naming a non-existent key column produced `unknown_column`.  The
    ledger no longer HAS a `tables` section to be internally inconsistent, so "is the
    catalog self-consistent" is now `table_config.json`'s own question -- answered by
    `models.declared_key_columns` (which refuses a partial index by name) and by
    `schema_drift` against the real database.

    What still has to be true HERE, and is what this asserts, is the LEDGER-side
    consequence: a key that names a column the relation does not have must not be allowed
    to certify an ordering as unique.  Silently accepting it is the direction that loses
    events, so the fail-closed behaviour gets its own test rather than riding on the
    retired one.
    """
    catalog = copy.deepcopy(DEFAULT_CATALOG)
    catalog["input_rows"]["business_key"] = "missing_key"
    errors = validate_bundle_errors(logical_bundle(), catalog=catalog)
    assert_structured_errors(errors)
    assert sum(error.code == "invalid_cursor" for error in errors) == 2


def test_join_right_side_without_an_exact_unique_key_is_refused():
    catalog = copy.deepcopy(DEFAULT_CATALOG)
    catalog["reference_rows"]["indexes"][0]["unique"] = False
    catalog["reference_rows"].pop("business_key")
    errors = validate_bundle_errors(logical_bundle(), catalog=catalog)
    assert_structured_errors(errors)
    error = next(item for item in errors if item.code == "invalid_join")
    assert error.path.endswith("join_key")


def test_order_and_cursor_reject_columns_without_catalog_unique_proof():
    bundle = logical_bundle()
    driver = bundle["sources"]["input_rows"]["read"]
    driver["order_by"] = ["event_at"]
    driver["cursor"]["columns"] = ["event_at"]

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    assert [(error.code, error.path) for error in errors
            if error.code == "invalid_cursor"] == [
        ("invalid_cursor", "bundle.sources.input_rows.read.cursor.columns"),
        ("invalid_cursor", "bundle.sources.input_rows.read.order_by"),
    ]


def test_business_key_tie_breaker_keeps_normal_source_valid():
    assert validate_bundle_errors(logical_bundle()) == ()


def _composite_key_catalog():
    """Catalog where the source relation's identity is a two-column composite."""
    catalog = copy.deepcopy(DEFAULT_CATALOG)
    catalog["input_rows"].pop("business_key")
    catalog["input_rows"]["composite_key"] = ["event_key", "record_id"]
    return catalog


def test_complete_composite_unique_key_proves_total_order():
    bundle = logical_bundle()
    driver = bundle["sources"]["input_rows"]["read"]
    driver["order_by"] = ["event_at", "event_key", "record_id"]
    driver["cursor"]["columns"] = ["event_at", "event_key", "record_id"]
    assert validate_bundle_errors(bundle, catalog=_composite_key_catalog()) == ()


def test_partial_composite_unique_key_does_not_prove_total_order():
    bundle = logical_bundle()
    driver = bundle["sources"]["input_rows"]["read"]
    driver["order_by"] = ["event_at", "event_key"]
    driver["cursor"]["columns"] = ["event_at", "event_key"]
    errors = validate_bundle_errors(bundle, catalog=_composite_key_catalog())
    assert_structured_errors(errors)
    assert sum(error.code == "invalid_cursor" for error in errors) == 2


def test_nonunique_index_is_not_a_total_order_proof():
    catalog = copy.deepcopy(DEFAULT_CATALOG)
    catalog["input_rows"].pop("business_key")
    catalog["input_rows"]["indexes"] = [
        {"name": "idx_event_at", "columns": ["event_at"], "unique": False}]
    bundle = logical_bundle()
    driver = bundle["sources"]["input_rows"]["read"]
    driver["order_by"] = ["event_at"]
    driver["cursor"]["columns"] = ["event_at"]
    errors = validate_bundle_errors(bundle, catalog=catalog)
    assert_structured_errors(errors)
    assert sum(error.code == "invalid_cursor" for error in errors) == 2


def test_missing_required_role_and_disallowed_binding_kind_are_rejected():
    bundle = logical_bundle()
    del source_profile(bundle)["mappings"][0]["bind"]["target"]
    assert issue(bundle, "missing_required_role").path.endswith("bind.target")
    bundle = logical_bundle()
    role = bundle["packs"]["movement@1"]["claims"]["transition"]["roles"]["occurred_at"]
    role["allowed_binding_kinds"] = ["constant"]
    assert issue(bundle, "invalid_binding").path.endswith("bind.occurred_at.kind")


def test_duplicate_mapping_id_is_rejected():
    bundle = logical_bundle()
    mappings = source_profile(bundle)["mappings"]
    mappings.append(copy.deepcopy(mappings[0]))
    error = issue(bundle, "duplicate_id")
    assert error.path.endswith("mappings[1].mapping_id")


def test_binding_approval_metadata_survives_normalization():
    bundle = logical_bundle()
    event = source_profile(bundle)["mappings"][0]["bind"]["event_key"]
    event["binding_origin"] = "system_suggested"
    event["approval_status"] = "pending"
    event["suggestion_reason"] = "header similarity"
    normalized = validate_bundle(bundle).to_mapping()
    got = source_profile(normalized)["mappings"][0]["bind"]["event_key"]
    assert got["binding_origin"] == "system_suggested"
    assert got["approval_status"] == "pending"
    assert got["suggestion_reason"] == "header similarity"


def test_system_suggested_requires_a_reason():
    bundle = logical_bundle()
    event = source_profile(bundle)["mappings"][0]["bind"]["event_key"]
    event["binding_origin"] = "system_suggested"
    error = issue(bundle, "invalid_binding")
    assert error.path.endswith("bind.event_key.suggestion_reason")


def test_constant_binding_must_be_finite_deterministic_json():
    bundle = logical_bundle()
    event = source_profile(bundle)["mappings"][0]["bind"]["event_key"]
    event.clear()
    event.update({
        "kind": "constant", "value": float("nan"),
        "binding_origin": "user_declared", "approval_status": "approved",
    })
    error = issue(bundle, "invalid_binding")
    assert error.path.endswith("bind.event_key.value")


def test_unregistered_symbolic_constant_is_rejected_exactly():
    bundle = symbolic_bundle("NOT_REGISTERED_ANYWHERE")

    errors = validate_bundle_errors(bundle)

    assert [error.to_mapping() for error in errors] == [{
        "code": "invalid_symbolic_constant",
        "path": (
            f"{PROFILE_PATH}.mappings[0].bind."
            "movement_kind.value"
        ),
        "message": (
            "constant 'NOT_REGISTERED_ANYWHERE' is not registered by symbolic role "
            "'movement_kind'"
        ),
    }]


def symbolic_bundle(value="pick"):
    bundle = logical_bundle()
    bundle["vocabulary"]["moves_to@1"]["object"]["qualifiers"] = {
        "required": [], "optional": ["event_key", "movement_kind"]}
    claim = bundle["packs"]["movement@1"]["claims"]["transition"]
    claim["roles"]["movement_kind"] = {
        "kind": "symbolic",
        "required": False,
        "allowed_values": ["pick", "place"],
    }
    claim["emit"]["object"]["qualifiers"]["movement_kind"] = "$movement_kind?"
    claim_binding = source_profile(bundle)["mappings"][0]["bind"]
    claim_binding["movement_kind"] = {
        "kind": "constant",
        "value": value,
        "binding_origin": "user_declared",
        "approval_status": "approved",
    }
    return bundle


def test_registered_symbolic_constant_is_accepted():
    assert validate_bundle_errors(symbolic_bundle("pick")) == ()


@pytest.mark.parametrize(
    ("allowed_values", "code"),
    [
        (None, "invalid_type"),
        ({"pick": True}, "invalid_type"),
        ([True], "blank_value"),
        ([""], "blank_value"),
        (["pick", "pick"], "duplicate_id"),
        (["place", "pick"], "invalid_role_kind"),
    ],
)
def test_symbolic_allowed_values_fail_closed(allowed_values, code):
    bundle = symbolic_bundle()
    role = bundle["packs"]["movement@1"]["claims"]["transition"]["roles"][
        "movement_kind"]
    role["allowed_values"] = allowed_values

    errors = validate_bundle_errors(bundle)

    assert any(
        error.code == code
        and error.path.startswith(
            "bundle.packs.movement@1.claims.transition.roles."
            "movement_kind.allowed_values")
        and error.message
        for error in errors
    )


def test_general_time_constant_is_not_treated_as_symbolic():
    bundle = logical_bundle()
    bundle["vocabulary"]["moves_to@1"]["object"]["qualifiers"] = {
        "required": [], "optional": ["event_key"]}
    occurred = source_profile(bundle)["mappings"][0]["bind"][
        "occurred_at"]
    occurred.clear()
    occurred.update({
        "kind": "constant",
        "value": "2026-08-17T00:00:00+09:00",
        "binding_origin": "user_declared",
        "approval_status": "approved",
    })

    assert validate_bundle_errors(bundle) == ()


def test_binding_approval_never_adds_a_claim_epistemic_class():
    rendered = validate_bundle(logical_bundle()).serialize()
    assert '"approval_status":"approved"' in rendered
    for forbidden in ("claim_class", "confirmed", "pin_class", "resolution_class"):
        assert forbidden not in rendered


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_readiness_blocks_nonapproved_bindings_without_rejecting_draft(status):
    bundle = logical_bundle()
    event = source_profile(bundle)["mappings"][0]["bind"]["event_key"]
    event["approval_status"] = status
    draft = validate_bundle(bundle)
    error = bundle_readiness_errors(draft)[0]
    assert error.code == "binding_not_approved"
    assert error.path.endswith("bind.event_key.approval_status")
    with pytest.raises(LedgerSetupValidationError):
        require_ready_bundle(draft)


def test_readiness_walks_nested_entity_key_bindings():
    bundle = logical_bundle()
    nested = source_profile(bundle)["mappings"][0]["bind"]["target"]["keys"]["output_id"]
    nested["approval_status"] = "pending"
    errors = bundle_readiness_errors(validate_bundle(bundle))
    assert errors[0].path.endswith("bind.target.keys.output_id.approval_status")


def test_only_all_approved_bundle_is_ready():
    validated = validate_bundle(logical_bundle())
    assert bundle_readiness_errors(validated) == ()
    assert require_ready_bundle(validated) is validated


def test_same_pack_validates_with_completely_different_source_and_column_names():
    first = validate_bundle(logical_bundle())
    second = validate_bundle(logical_bundle(source_name="alternate_rows", prefix="z_"))
    assert first.section("packs") == second.section("packs")
    assert require_ready_bundle(second) is second


def test_virtual_join_change_changes_canonical_bundle():
    first = logical_bundle()
    second = copy.deepcopy(first)
    second["virtual_joins"]["input_to_reference"]["fold"] = {"case": True}
    assert validate_bundle(first).serialize() != validate_bundle(second).serialize()


def test_virtual_join_fold_must_be_an_object():
    bundle = logical_bundle()
    bundle["virtual_joins"]["input_to_reference"]["fold"] = "casefold"
    assert "invalid_join" in {item.code for item in validate_bundle_errors(bundle)}


def test_preparer_must_explicitly_accept_inherited_join_rules():
    bundle = logical_bundle()
    driver_preparation(bundle)["accepts_verified_join_rules"] = False
    errors = validate_bundle_errors(bundle)
    assert any(
        item.code == "invalid_driver"
        and item.path.endswith("accepts_verified_join_rules")
        for item in errors)


def test_errors_have_deterministic_order():
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["relation"] = "absent"
    source_profile(bundle)["mappings"][0]["use"] = "missing@1/nope"
    first = [item.to_mapping() for item in validate_bundle_errors(bundle)]
    second = [item.to_mapping() for item in validate_bundle_errors(reverse_mappings(bundle))]
    assert first == second
    assert first == sorted(first, key=lambda item: (item["path"], item["code"], item["message"]))


def test_followup_validation_errors_have_deterministic_order():
    bundle = logical_bundle()
    profile = source_profile(bundle)
    profile["mappings"][0]["bind"]["subject"]["entity_type"] = "Missing@1"
    profile["mappings"][0]["bind"]["subject"]["keys"]["input_id"][
        "column"] = "missing_column"
    bundle["entities"]["InputEntity@1"]["key_types"] = {"input_id": {"bad": True}}
    driver = bundle["sources"]["input_rows"]["read"]
    driver["order_by"] = ["event_at"]
    driver["cursor"]["columns"] = ["event_at"]
    # was `bundle["chains"]["bad"]`; that section is gone, the follow-up error it
    # contributed is not -- any additional error source exercises the ordering.
    bundle["virtual_joins"]["input_to_reference"]["fold"] = {"steps": [[{"sql": "DROP"}]]}

    first_errors = validate_bundle_errors(bundle)
    second_errors = validate_bundle_errors(reverse_mappings(bundle))
    first = [item.to_mapping() for item in first_errors]
    second = [item.to_mapping() for item in second_errors]

    assert_structured_errors(first_errors)
    assert first == second
    assert first == sorted(first, key=lambda item: (item["path"], item["code"], item["message"]))


@pytest.mark.parametrize("broken_path", ["role", "claims", "predicate_object", "emission"])
def test_malformed_nested_pack_descriptors_return_errors_instead_of_raising(broken_path):
    bundle = logical_bundle()
    claim = bundle["packs"]["movement@1"]["claims"]["transition"]
    if broken_path == "role":
        claim["roles"]["subject"] = "broken"
    elif broken_path == "claims":
        bundle["packs"]["movement@1"]["claims"] = "broken"
    elif broken_path == "predicate_object":
        bundle["vocabulary"]["moves_to@1"]["object"] = "broken"
    else:
        claim["emit"] = "broken"
    assert validate_bundle_errors(bundle)


def test_every_json_node_shape_mutation_returns_only_structured_errors():
    original = logical_bundle()
    checked = 0
    for path, node in json_nodes(original):
        replacement = [] if isinstance(node, dict) else {}
        malformed = replace_json_node(original, path, replacement)
        errors = validate_bundle_errors(malformed)
        assert_structured_errors(errors)
        checked += 1
    # Floor, not a census: it exists so a fixture that quietly shrank cannot make this
    # sweep vacuous. It moved 150 -> 145 when `tables` left the bundle, and 145 -> 140
    # when the preparer and mapper folded into the driver on 2026-08-20: two section nodes,
    # two id-keyed nodes and the two `*_id` leaves went, `driver.mapper` arrived, net -5.
    # 140 -> 136 on 2026-08-21, MEASURED at 141 -> 137: `map.emits` and `bind.packs` each
    # took their list node and its one item, and `driver` splitting into `read`/`prepare`/
    # `map` is net zero (one record node out, one in). Lower it only alongside a deliberate
    # shape change, and say which one.
    assert checked >= 136


def test_every_json_node_accepts_or_structurally_rejects_all_json_value_kinds():
    original = logical_bundle()
    replacements = (None, [], {}, "", 0, True)
    checked = 0
    for path, _node in json_nodes(original):
        for replacement in replacements:
            candidate = replace_json_node(original, path, replacement)
            errors = validate_bundle_errors(candidate)
            if errors:
                assert_structured_errors(errors)
                with pytest.raises(LedgerSetupValidationError) as caught:
                    validate_bundle(candidate)
                assert_structured_errors((caught.value,))
            else:
                validate_bundle(candidate)
            checked += 1
    # Same floor, times the six replacement kinds. Was 900 while the bundle carried
    # `tables`, 894 while the preparer and mapper had their own sections; 822 today
    # (137 x 6).
    assert checked >= 816


def test_common_module_has_no_domain_source_branches_or_runtime_imports():
    source_path = Path(__file__).resolve().parents[1] / "ledger" / "setup_bundle.py"
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("dt_log", "bonding_log", "core_wafer", "bond_slot",
                      "transfertranslator", "lot_event"):
        assert forbidden not in lowered
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    # `difflib` joined on 2026-08-19 so an `unknown_*` refusal can say "did you mean
    # 'movement@1'?". It is pure stdlib string comparison -- no I/O, no domain, no runtime --
    # which is the property this allowlist exists to protect. The list stays CLOSED: a new
    # name here is a decision, and anything that reads data or knows about a source is
    # still refused by the loop below.
    assert imported <= {"__future__", "collections", "dataclasses", "difflib", "json",
                        "pathlib", "re", "types", "typing", "zoneinfo"}
    for forbidden in ("database", "sqlalchemy", "psycopg2", "backfill", "store",
                      "translator", "chain_mapper"):
        assert forbidden not in imported


def test_stage_two_has_no_db_migration_write_runtime_or_compiler_surface():
    import ledger.setup_bundle as module
    public = {name for name in dir(module) if not name.startswith("_")}
    assert not {"execute", "compile", "translate", "write", "migrate", "advance_cursor"} & public
    assert not (Path(__file__).resolve().parents[1] / "migrations" / "ledger_setup_bundle.py").exists()


def test_group_by_mapper_unit_requires_closed_input_columns():
    missing = logical_bundle()
    driver_mapper(missing)["unit"] = {"kind": "group_by"}
    errors = validate_bundle_errors(missing)
    assert any(error.to_mapping() == {
        "code": "missing_field",
        "path": f"{MAPPER_PATH}.unit.columns",
        "message": "group_by mapper unit requires columns",
    } for error in errors)

    unknown = logical_bundle()
    driver_mapper(unknown)["unit"] = {
        "kind": "group_by", "columns": ["not_an_input"]}
    errors = validate_bundle_errors(unknown)
    assert any(error.code == "invalid_mapper"
               and error.path == f"{MAPPER_PATH}.unit.columns"
               for error in errors)

    valid = logical_bundle()
    driver_mapper(valid)["unit"] = {
        "kind": "group_by", "columns": ["target_id"]}
    compiled = validate_bundle(valid).section("sources")
    assert compiled["input_rows"]["map"]["unit"] == {
        "kind": "group_by", "columns": ("target_id",)}


def test_non_group_mapper_unit_rejects_columns():
    raw = logical_bundle()
    driver_mapper(raw)["unit"] = {
        "kind": "event", "columns": ["event_key"]}
    errors = validate_bundle_errors(raw)
    assert any(error.code == "invalid_mapper"
               and error.path == f"{MAPPER_PATH}.unit.columns"
               for error in errors)


# --- The refusal carries the answer it is already holding -------------------------------
#
# Measured 2026-08-19: the owner hand-authored a second source and every one of the three
# refusals below had to be translated by a human sitting next to them.  Nothing new has to
# be computed for any of them -- the allowed sets are frozensets and tuples one stack frame
# away from the `add()` call that refuses.


def test_an_unknown_field_refusal_names_what_the_object_does_take(tmp_path):
    """"field is not allowed" answers WHERE and not WHAT.

    `exact()` has the required and optional tuples in hand at the moment it refuses; the
    author has to go and find them.  The exact case measured was `emit.object.payload`,
    where a human had to say "object takes kind / entity / value / qualifiers".
    """
    raw = logical_bundle()
    raw["packs"]["movement@1"]["claims"]["transition"]["emit"]["object"]["payload"] = {"n": 1}
    refused = issue(raw, "unknown_field")

    assert refused.path == "bundle.packs.movement@1.claims.transition.emit.object.payload"
    assert refused.message.startswith("field is not allowed")
    # Every allowed name, and which one is not optional. Scored as a SET so the assertion
    # does not pin the join text of the sentence.
    listed = refused.message.split("allowed here: ", 1)[1]
    assert {part.strip() for part in listed.split(",")} == {
        "kind (required)", "entity", "value", "qualifiers"}

    # The retired-section help still wins where it applies -- it says what happened and
    # where the truth moved, which a bare field list would replace with something less
    # useful. Keyed on the FILE path, which is the one an operator pasting their old
    # section back in actually hits.
    retired = logical_bundle()
    retired["tables"] = {}
    write_tree(tmp_path, retired)
    tables = next(
        item for item in setup_bundle_module.setup_bundle_errors(
            tmp_path, catalog=DEFAULT_CATALOG)
        if item.path == "ledger_config.tables")
    assert "retired on 2026-08-18" in tables.message
    assert "allowed here" not in tables.message


def test_an_unknown_reference_separates_a_typo_from_a_declaration_not_written_yet():
    """"unknown pack 'dt-job@1'" does not say WHICH mistake this is.

    Misspelling an existing pack and emitting into one that has not been authored yet need
    opposite next actions -- fix a character, or go write a declaration.  The two fixtures
    disagree on purpose: a single fixture would pass under either rule.
    """
    typo = logical_bundle()
    source_profile(typo)["mappings"][0]["use"] = "movment@1/transition"
    near = issue(typo, "unknown_pack")
    assert "did you mean 'movement@1'?" in near.message

    absent = logical_bundle()
    source_profile(absent)["mappings"][0]["use"] = "shipment@9/transition"
    far = issue(absent, "unknown_pack")
    assert "did you mean" not in far.message
    assert "declared packs: 'movement@1'" in far.message

    # And the claim half of the same reference, scored against the pack it names.
    wrong_claim = logical_bundle()
    source_profile(wrong_claim)["mappings"][0]["use"] = "movement@1/transitions"
    claim = issue(wrong_claim, "unknown_claim")
    assert "did you mean 'transition'?" in claim.message

    # Nothing declared at all reads as neither of the above.
    empty = logical_bundle()
    empty["packs"] = {}
    assert "no packs are declared yet" in issue(empty, "unknown_pack").message


def test_a_refusal_about_a_claim_reference_says_how_one_is_spelled():
    """Replaces the `emits` half of `..._says_what_one_item_looks_like`.

    That test refused a LIST of claim references and asserted the list's refusal carried
    the item spelling.  `map.emits` was the only such list and is gone, so the clause it
    measured has no caller.  The need did not go with it: an author who writes a claim
    reference wrongly is exactly the one who does not know how one is spelled, and
    `mappings[].use` is now the only place they write it.
    """
    raw = logical_bundle()
    source_profile(raw)["mappings"][0]["use"] = "movement@1"
    refused = issue(raw, "invalid_claim_ref")
    assert refused.path == f"{PROFILE_PATH}.mappings[0].use"
    assert "must use <pack>@<version>/<claim>" in refused.message

    # And an ordinary list of names still says nothing about claim references.
    plain = logical_bundle()
    driver_mapper(plain)["input_columns"] = "record_id"
    assert "each item is" not in issue(plain, "invalid_type").message


def test_authoring_reports_every_problem_while_the_runtime_stops_at_the_first(tmp_path):
    """🔴 THE TWO PATHS MUST NOT BE COLLAPSED.

    Authoring needs the whole list -- measured, five save-and-run cycles for five problems
    that were all present in the first save.  The runtime does NOT: a source about to write
    atoms should stop at the first refusal, and every later check would be reading a bundle
    the earlier one already declared broken.

    So this scores both halves against ONE root, which is the only way to state that they
    differ rather than that each is separately plausible.
    """
    raw = logical_bundle()
    driver_mapper(raw)["input_columns"] = "record_id"
    raw["packs"]["movement@1"]["claims"]["transition"]["emit"]["object"]["payload"] = 1
    raw["vocabulary"]["moves_to@1"]["colour"] = "blue"
    raw["entities"]["InputEntity@1"]["allow_null"] = "yes"
    raw["sources"]["input_rows"]["read"]["unit"] = "wafer"
    write_tree(tmp_path, raw)

    issues = setup_bundle_module.setup_bundle_errors(
        tmp_path, catalog=DEFAULT_CATALOG)
    paths = [item.path for item in issues]
    assert len(set(paths)) >= 5, paths
    # All five mistakes, from one read. Named individually so a regression that drops one
    # kind of check cannot hide behind the count.
    for expected in (
        f"{MAPPER_PATH}.input_columns",
        "bundle.packs.movement@1.claims.transition.emit.object.payload",
        "bundle.vocabulary.moves_to@1.colour",
        "bundle.entities.InputEntity@1.allow_null",
        "bundle.sources.input_rows.read.unit",
    ):
        assert expected in paths, expected

    # The runtime loader still stops at the first, and the one it stops at is a MEMBER of
    # the list above -- the two paths disagree about how many, never about what.
    with pytest.raises(LedgerSetupValidationError) as refused:
        load_setup_bundle(tmp_path)
    assert refused.value.path in paths

    # And a clean root returns an empty list rather than raising on the way there.
    clean = tmp_path / "clean"
    write_tree(clean)
    assert setup_bundle_module.setup_bundle_errors(
        clean, catalog=DEFAULT_CATALOG) == tuple()


def test_a_root_shape_problem_is_reported_without_its_downstream_consequences(tmp_path):
    """Causes, not consequences.

    A document missing a whole section would make every cross-section check report the
    absence again in its own words.  The root stage returns alone for the same reason the
    section stage runs before cross-validation: a list where the cause is buried under
    thirty consequences is the single-message problem in a new costume.
    """
    raw = logical_bundle()
    del raw["packs"]
    write_tree(tmp_path, raw)
    issues = setup_bundle_module.setup_bundle_errors(tmp_path, catalog=DEFAULT_CATALOG)
    assert [item.path for item in issues] == ["ledger_config.packs"]
    assert issues[0].code == "missing_field"


def test_a_column_name_is_judged_against_three_different_universes():
    """🔴 "EVERY COLUMN MUST EXIST IN THE RELATION" IS FALSE, AND THE SCREEN DEPENDS ON IT.

    Derived 2026-08-19 while writing the authoring screen's forced-relationship table.  The
    same column name gets opposite answers depending on which field names it:

      * RELATION  = the catalog's columns          -- order_by, cursor.columns,
                                                      occurred_at.column, preparer
                                                      input_columns, registration_probe
      * PREPARED  = RELATION + preparer outputs    -- driver.identity, driver.group_by,
                                                      mapper input_columns
      * MAPPER IN = that mapper's input_columns    -- every profile column binding

    A screen that fed one list to every column dropdown would offer columns that do not
    exist in half the fields and hide legal ones in the other half.  So this is pinned by
    the DISCRIMINATING case: one name, accepted in one field and refused in another.  A
    fixture where the three universes coincide would prove nothing, which is why the column
    used here is a preparer OUTPUT -- a column that exists downstream and not upstream.
    """
    base = logical_bundle()
    produced = sorted(driver_preparation(base)["output_columns"])
    assert produced, "the fixture must have a preparer that produces a column"
    column = produced[0]
    assert column not in DEFAULT_CATALOG["input_rows"]["columns"], (
        f"{column!r} must NOT be a relation column or the two universes coincide here")

    prepared = copy.deepcopy(base)
    prepared["sources"]["input_rows"]["read"]["identity"] = [column]
    prepared["sources"]["input_rows"]["read"]["group_by"] = []
    assert not [
        item for item in validate_bundle_errors(prepared)
        if item.code == "unknown_column"
    ], "driver.identity reads the PREPARED frame, so a preparer output is legal there"

    relation = copy.deepcopy(base)
    relation["sources"]["input_rows"]["read"]["order_by"] = [column]
    refused = [
        item for item in validate_bundle_errors(relation)
        if item.code == "unknown_column"
    ]
    assert refused, "order_by reads the RELATION, so a preparer output must be refused"
    assert "is not in relation" in refused[0].message

    # And the third universe: a profile binds only what its mapper declares as input.
    narrowed = copy.deepcopy(base)
    driver_mapper(narrowed)["input_columns"] = ["source_id"]
    assert [
        item for item in validate_bundle_errors(narrowed)
        if item.code == "invalid_mapper" and "is missing" in item.message
    ], "profile column bindings are judged against the mapper's input_columns"
