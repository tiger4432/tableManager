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
    preparer = "prepare-input@1"
    mapper = "map-transition@1"
    profile = "input-transition@1"
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
        "source_preparers": {
            preparer: {
                "implementation_id": "prepare-input",
                "implementation_version": 1,
                "input_columns": [join_key],
                "output_columns": {target_key: "string"},
                "accepts_verified_join_rules": True,
            },
        },
        "mappers": {
            mapper: {
                "implementation_id": "map-transition-role",
                "implementation_version": 1,
                "unit": {"kind": "event"},
                "input_columns": [source_key, target_key, occurred, event],
                "emits": ["movement@1/transition"],
            },
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
        "profiles": {
            profile: {
                "source": source_name,
                "packs": ["movement@1"],
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
        "sources": {
            source_name: {
                "relation": source_name,
                "driver": {
                    "unit": "group",
                    "identity": [event],
                    "group_by": [event],
                    "order_by": [record],
                    "occurred_at": {"column": occurred, "timezone": "Asia/Seoul"},
                    "cursor": {"columns": [occurred, record]},
                    "preparation": {
                        "preparer_id": preparer,
                        "inherit_virtual_join_rules": ["input_to_reference"],
                    },
                    "mapper_id": mapper,
                },
                "profile_id": profile,
            },
        },
    }


def add_unused_profile(bundle):
    profile = copy.deepcopy(bundle["profiles"]["input-transition@1"])
    bundle["profiles"]["unused-profile@1"] = profile
    return profile


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
    raw["profiles"]["input-transition@1"]["packs"].append("registration@1")
    raw["profiles"]["input-transition@1"]["mappings"].append({
        "mapping_id": "register_input", "use": "registration@1/register",
        "bind": {
            "subject": entity("InputEntity@1", "input_id", "source_id"),
            "occurred_at": binding("event_at"),
        },
    })
    raw["mappers"]["map-transition@1"]["emits"].append(
        "registration@1/register")
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
    assert schema["forbidden_sections"] == [
        "frames", "lookups", "positions", "manifest", "chains", "enrichments",
        "tables"]
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
    assert hashlib.sha256(first.serialize().encode()).hexdigest() == (
        "11571931bd673dea08ce62a36947993ec6cf1eea646528257a15b4d3ff06fbb9")


def test_list_order_is_preserved_but_object_order_is_not():
    original = logical_bundle()
    reversed_keys = reverse_mappings(original)
    assert validate_bundle(original).serialize() == validate_bundle(reversed_keys).serialize()
    changed = copy.deepcopy(original)
    changed["sources"]["input_rows"]["driver"]["cursor"]["columns"].reverse()
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
        '"entities":{},"source_preparers":{},"mappers":{},'
        '"packs":{},"profiles":{},"sources":{}}', encoding="utf-8")
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
    target = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"]
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
    bundle["sources"]["input_rows"]["driver"]["cursor"]["columns"][0] = "missing_col"
    column = issue(bundle, "unknown_column")
    assert column.path == "bundle.sources.input_rows.relation"
    assert "missing_col" in column.message


def test_timezone_must_be_explicit_and_valid():
    bundle = logical_bundle()
    del bundle["sources"]["input_rows"]["driver"]["occurred_at"]["timezone"]
    assert any(item.path.endswith("occurred_at.timezone") and item.code == "missing_field"
               for item in validate_bundle_errors(bundle))
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["driver"]["occurred_at"]["timezone"] = "Moon/Base"
    assert issue(bundle, "invalid_timezone").path.endswith("occurred_at.timezone")


def test_time_origin_requires_exactly_one_of_column_or_basis():
    """A source says WHERE its time came from, and says it once.

    Before this, the only legal shape named a column, so a table carrying no world time
    could only be declared by pointing at a non-time column or pinning a constant into the
    profile - both of which produce atoms that READ as world time. Declaring the absence is
    the honest form; declaring BOTH would leave a reader guessing which one won.
    """
    bundle = logical_bundle()
    del bundle["sources"]["input_rows"]["driver"]["occurred_at"]["column"]
    neither = issue(bundle, "invalid_driver")
    assert neither.path.endswith("driver.occurred_at")
    assert "neither" in neither.message

    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["driver"]["occurred_at"]["basis"] = "ingested"
    both = issue(bundle, "invalid_driver")
    assert both.path.endswith("driver.occurred_at")
    assert "both" in both.message


def test_time_basis_is_a_closed_list():
    """An open string here would let a typo become a silent claim about time."""
    bundle = logical_bundle()
    occurred = bundle["sources"]["input_rows"]["driver"]["occurred_at"]
    del occurred["column"]
    occurred["basis"] = "guessed"
    error = issue(bundle, "invalid_driver")
    assert error.path.endswith("driver.occurred_at.basis")
    assert "guessed" in error.message
    assert "ingested" in error.message


def test_a_declared_basis_names_no_source_column():
    """The basis reads the row's own ingestion stamp, so it must not be column-checked.

    Without this the cross-check would look for a column named ``None`` in the relation and
    report a missing column that the author never declared.
    """
    bundle = logical_bundle()
    occurred = bundle["sources"]["input_rows"]["driver"]["occurred_at"]
    del occurred["column"]
    occurred["basis"] = "ingested"
    codes = {item.code for item in validate_bundle_errors(bundle)}
    assert "unknown_column" not in codes
    assert "invalid_driver" not in codes


def test_entity_binding_requires_exact_registered_identity_keys():
    bundle = logical_bundle()
    keys = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["subject"]["keys"]
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


def test_unknown_pack_claim_role_preparer_mapper_and_join_are_named():
    cases = []
    bundle = logical_bundle()
    bundle["profiles"]["input-transition@1"]["mappings"][0]["use"] = "absent@1/transition"
    cases.append((bundle, "unknown_pack"))
    bundle = logical_bundle()
    bundle["profiles"]["input-transition@1"]["mappings"][0]["use"] = "movement@1/absent"
    cases.append((bundle, "unknown_claim"))
    bundle = logical_bundle()
    bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["absent"] = binding("event_key")
    cases.append((bundle, "unknown_role"))
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["driver"]["preparation"]["preparer_id"] = "absent@1"
    cases.append((bundle, "unknown_source_preparer"))
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["driver"]["mapper_id"] = "absent@1"
    cases.append((bundle, "unknown_mapper"))
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["driver"]["preparation"]["inherit_virtual_join_rules"] = ["absent"]
    cases.append((bundle, "unknown_join_rule"))
    for value, code in cases:
        assert any(item.code == code for item in validate_bundle_errors(value)), code


def test_unused_vocabulary_pack_profile_and_mapper_are_still_cross_validated():
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
    bundle["profiles"]["unused-profile@1"] = copy.deepcopy(
        bundle["profiles"]["input-transition@1"])
    bundle["profiles"]["unused-profile@1"]["packs"] = ["missing@1"]
    bundle["profiles"]["unused-profile@1"]["mappings"][0]["use"] = "missing@1/claim"
    bundle["mappers"]["unused-mapper@1"] = copy.deepcopy(
        bundle["mappers"]["map-transition@1"])
    bundle["mappers"]["unused-mapper@1"]["emits"] = ["missing@1/claim"]
    errors = validate_bundle_errors(bundle)
    assert any(error.code == "unknown_entity_type"
               and error.path.startswith("bundle.vocabulary.unused@1") for error in errors)
    assert any(error.code == "unknown_predicate"
               and error.path.startswith("bundle.packs.unused@1") for error in errors)
    assert any(error.code == "unknown_pack"
               and error.path.startswith("bundle.profiles.unused-profile@1") for error in errors)
    assert any(error.code == "unknown_pack"
               and error.path.startswith("bundle.mappers.unused-mapper@1") for error in errors)


def test_unused_profile_entity_binding_is_cross_validated_against_its_source():
    bundle = logical_bundle()
    profile = add_unused_profile(bundle)
    profile["mappings"][0]["bind"]["subject"]["entity_type"] = "Missing@1"

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    matches = [error for error in errors if error.code == "unknown_entity_type"]
    assert [error.path for error in matches] == [
        "bundle.profiles.unused-profile@1.mappings[0].bind.subject.entity_type"]


def test_unused_profile_leaf_column_is_cross_validated_against_event_frame():
    bundle = logical_bundle()
    profile = add_unused_profile(bundle)
    profile["mappings"][0]["bind"]["subject"]["keys"]["input_id"][
        "column"] = "missing_column"

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    matches = [error for error in errors if error.code == "unknown_column"]
    assert [error.path for error in matches] == [
        "bundle.profiles.unused-profile@1.mappings[0].bind.subject.keys.input_id.column"]


def test_normal_unused_profile_still_validates_without_duplicate_errors():
    bundle = logical_bundle()
    add_unused_profile(bundle)
    assert validate_bundle_errors(bundle) == ()


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


def test_profile_packs_mapping_use_and_mapper_emits_are_mutually_closed():
    bundle = logical_bundle()
    alternate = copy.deepcopy(bundle["packs"]["movement@1"])
    bundle["packs"]["alternate@1"] = alternate
    bundle["profiles"]["input-transition@1"]["packs"] = ["alternate@1"]
    alternate_claim = copy.deepcopy(alternate["claims"]["transition"])
    bundle["packs"]["movement@1"]["claims"]["secondary"] = alternate_claim
    bundle["mappers"]["map-transition@1"]["emits"] = ["movement@1/secondary"]
    errors = validate_bundle_errors(bundle)
    assert any(error.code == "invalid_profile" and error.path.endswith("mappings[0].use")
               and "profile.packs" in error.message for error in errors)
    assert any(error.code == "invalid_mapper" and error.path.endswith("emits[0]")
               for error in errors)
    assert any(error.code == "invalid_profile" and error.path.endswith("mappings[0].use")
               and "mapper" in error.message for error in errors)


def test_mapper_inputs_cover_profile_columns_and_preparer_outputs_do_not_collide():
    bundle = logical_bundle()
    bundle["mappers"]["map-transition@1"]["input_columns"].remove("event_key")
    errors = validate_bundle_errors(bundle)
    assert any(error.code == "invalid_mapper"
               and "Profile column 'event_key'" in error.message for error in errors)

    bundle = logical_bundle()
    bundle["source_preparers"]["prepare-input@1"]["output_columns"]["source_id"] = "string"
    errors = validate_bundle_errors(bundle)
    assert any(error.code == "output_column_collision"
               and error.path.endswith("output_columns.source_id") for error in errors)


@pytest.mark.parametrize(
    ("unit", "group_by"),
    [("unknown", ["event_key"]), ("row", ["event_key"]), ("group", [])],
)
def test_source_unit_and_group_contract_is_fail_closed(unit, group_by):
    bundle = logical_bundle()
    driver = bundle["sources"]["input_rows"]["driver"]
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
    driver = bundle["sources"]["input_rows"]["driver"]
    driver["order_by"] = ["event_at"]
    driver["cursor"]["columns"] = ["event_at"]

    errors = validate_bundle_errors(bundle)

    assert_structured_errors(errors)
    assert [(error.code, error.path) for error in errors
            if error.code == "invalid_cursor"] == [
        ("invalid_cursor", "bundle.sources.input_rows.driver.cursor.columns"),
        ("invalid_cursor", "bundle.sources.input_rows.driver.order_by"),
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
    driver = bundle["sources"]["input_rows"]["driver"]
    driver["order_by"] = ["event_at", "event_key", "record_id"]
    driver["cursor"]["columns"] = ["event_at", "event_key", "record_id"]
    assert validate_bundle_errors(bundle, catalog=_composite_key_catalog()) == ()


def test_partial_composite_unique_key_does_not_prove_total_order():
    bundle = logical_bundle()
    driver = bundle["sources"]["input_rows"]["driver"]
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
    driver = bundle["sources"]["input_rows"]["driver"]
    driver["order_by"] = ["event_at"]
    driver["cursor"]["columns"] = ["event_at"]
    errors = validate_bundle_errors(bundle, catalog=catalog)
    assert_structured_errors(errors)
    assert sum(error.code == "invalid_cursor" for error in errors) == 2


def test_missing_required_role_and_disallowed_binding_kind_are_rejected():
    bundle = logical_bundle()
    del bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["target"]
    assert issue(bundle, "missing_required_role").path.endswith("bind.target")
    bundle = logical_bundle()
    role = bundle["packs"]["movement@1"]["claims"]["transition"]["roles"]["occurred_at"]
    role["allowed_binding_kinds"] = ["constant"]
    assert issue(bundle, "invalid_binding").path.endswith("bind.occurred_at.kind")


def test_duplicate_mapping_id_is_rejected():
    bundle = logical_bundle()
    mappings = bundle["profiles"]["input-transition@1"]["mappings"]
    mappings.append(copy.deepcopy(mappings[0]))
    error = issue(bundle, "duplicate_id")
    assert error.path.endswith("mappings[1].mapping_id")


def test_binding_approval_metadata_survives_normalization():
    bundle = logical_bundle()
    event = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"]
    event["binding_origin"] = "system_suggested"
    event["approval_status"] = "pending"
    event["suggestion_reason"] = "header similarity"
    normalized = validate_bundle(bundle).to_mapping()
    got = normalized["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"]
    assert got["binding_origin"] == "system_suggested"
    assert got["approval_status"] == "pending"
    assert got["suggestion_reason"] == "header similarity"


def test_system_suggested_requires_a_reason():
    bundle = logical_bundle()
    event = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"]
    event["binding_origin"] = "system_suggested"
    error = issue(bundle, "invalid_binding")
    assert error.path.endswith("bind.event_key.suggestion_reason")


def test_constant_binding_must_be_finite_deterministic_json():
    bundle = logical_bundle()
    event = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"]
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
            "bundle.profiles.input-transition@1.mappings[0].bind."
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
    claim_binding = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]
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
    occurred = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"][
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
    event = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"]
    event["approval_status"] = status
    draft = validate_bundle(bundle)
    error = bundle_readiness_errors(draft)[0]
    assert error.code == "binding_not_approved"
    assert error.path.endswith("bind.event_key.approval_status")
    with pytest.raises(LedgerSetupValidationError):
        require_ready_bundle(draft)


def test_readiness_walks_nested_entity_key_bindings():
    bundle = logical_bundle()
    nested = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]["target"]["keys"]["output_id"]
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
    bundle["source_preparers"]["prepare-input@1"]["accepts_verified_join_rules"] = False
    errors = validate_bundle_errors(bundle)
    assert any(
        item.code == "invalid_driver"
        and item.path.endswith("accepts_verified_join_rules")
        for item in errors)


def test_errors_have_deterministic_order():
    bundle = logical_bundle()
    bundle["sources"]["input_rows"]["relation"] = "absent"
    bundle["profiles"]["input-transition@1"]["mappings"][0]["use"] = "missing@1/nope"
    first = [item.to_mapping() for item in validate_bundle_errors(bundle)]
    second = [item.to_mapping() for item in validate_bundle_errors(reverse_mappings(bundle))]
    assert first == second
    assert first == sorted(first, key=lambda item: (item["path"], item["code"], item["message"]))


def test_followup_validation_errors_have_deterministic_order():
    bundle = logical_bundle()
    profile = add_unused_profile(bundle)
    profile["mappings"][0]["bind"]["subject"]["entity_type"] = "Missing@1"
    profile["mappings"][0]["bind"]["subject"]["keys"]["input_id"][
        "column"] = "missing_column"
    bundle["entities"]["InputEntity@1"]["key_types"] = {"input_id": {"bad": True}}
    driver = bundle["sources"]["input_rows"]["driver"]
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
    # sweep vacuous. It moved 150 -> 145 when `tables` left the bundle (149 nodes today,
    # was 158). Lower it only alongside a deliberate shape change, and say which one.
    assert checked >= 145


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
    # `tables`; 894 today (149 x 6).
    assert checked >= 870


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
    assert imported <= {"__future__", "collections", "dataclasses", "json", "pathlib",
                        "re", "types", "typing", "zoneinfo"}
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
    missing["mappers"]["map-transition@1"]["unit"] = {"kind": "group_by"}
    errors = validate_bundle_errors(missing)
    assert any(error.to_mapping() == {
        "code": "missing_field",
        "path": "bundle.mappers.map-transition@1.unit.columns",
        "message": "group_by mapper unit requires columns",
    } for error in errors)

    unknown = logical_bundle()
    unknown["mappers"]["map-transition@1"]["unit"] = {
        "kind": "group_by", "columns": ["not_an_input"]}
    errors = validate_bundle_errors(unknown)
    assert any(error.code == "invalid_mapper"
               and error.path == "bundle.mappers.map-transition@1.unit.columns"
               for error in errors)

    valid = logical_bundle()
    valid["mappers"]["map-transition@1"]["unit"] = {
        "kind": "group_by", "columns": ["target_id"]}
    assert validate_bundle(valid).section("mappers")["map-transition@1"]["unit"] == {
        "kind": "group_by", "columns": ("target_id",)}


def test_non_group_mapper_unit_rejects_columns():
    raw = logical_bundle()
    raw["mappers"]["map-transition@1"]["unit"] = {
        "kind": "event", "columns": ["event_key"]}
    errors = validate_bundle_errors(raw)
    assert any(error.code == "invalid_mapper"
               and error.path == "bundle.mappers.map-transition@1.unit.columns"
               for error in errors)
