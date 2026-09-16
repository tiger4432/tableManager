"""Ledger v2 Stage 4 focused RoleFrame and Claim compiler contract tests."""
from __future__ import annotations

import ast
import copy
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from ledger.envelope import Atom, source_event_identity
from ledger.roleframe import (
    BaseLedgerMapper,
    DeclarativeRoleMapper,
    EVENT_FRAME_REQUIRED_ATTRS,
    ROLE_FRAME_COLUMNS,
    RoleEmission,
    RoleFrameError,
    RoleMapperImplementationRegistry,
    SOURCE_OCCURRED_AT_COLUMN,
    compile_role_frame,
    dry_run_event_frame,
    map_event_frame,
    mapper_context,
)
from test_ledger_setup_bundle import (
    driver_mapper, logical_bundle, objectless_register_bundle, source_profile)
from test_ledger_setup_registry import snapshot


OCCURRED_AT = pd.Timestamp("2026-08-17T10:30:00+09:00")
MOLECULE_REF = "input_rows:event:E-1"
RAW_REF = "input_rows:record:R-1"


def event_frame(compiled, rows=None):
    rows = rows or [{
        "source_id": "IN-1",
        "target_id": "OUT-1",
        "event_at": OCCURRED_AT,
        "event_key": "E-1",
    }]
    frame = pd.DataFrame(rows)
    # The preparation boundary publishes the ONE interpreted instant on every event it
    # emits (`source_preparation` line 920), and a hand-built frame that skips that
    # boundary has to stand in for it: `DeclarativeRoleMapper` fills time Roles from this
    # column the same way both custom mappers do.  Constant across the rows of one event,
    # exactly as the preparer writes it.
    frame[SOURCE_OCCURRED_AT_COLUMN] = OCCURRED_AT.to_pydatetime()
    event_id, _ = source_event_identity(
        "input_rows", OCCURRED_AT.to_pydatetime(),
        molecule_ref=MOLECULE_REF, source_raw_ref=RAW_REF)
    frame.attrs.update({
        "source_id": "input_rows",
        "source_event_id": event_id,
        "molecule_ref": MOLECULE_REF,
        "source_raw_ref": RAW_REF,
        "setup_snapshot_hash": compiled.snapshot_sha256,
    })
    return frame


def implementations(mapper_type=DeclarativeRoleMapper):
    registry = RoleMapperImplementationRegistry()
    registry.register("map-transition-role", 1, mapper_type)
    return registry.seal()


def semantic_frame(frame):
    return [{column: frame.iloc[position][column]
             for column in frame.columns}
            for position in range(len(frame))]


def constant(value, *, status="approved", origin="user_declared"):
    return {
        "kind": "constant",
        "value": value,
        "binding_origin": origin,
        "approval_status": status,
    }


def test_declarative_column_constant_entity_bindings_make_role_frame():
    raw = logical_bundle()
    source_profile(raw)["mappings"]["main_transition"]["bind"]["event_key"] = (
        constant("fixed-event"))
    compiled = snapshot(raw)
    context = mapper_context(compiled, "input_rows")

    frame = map_event_frame(context, event_frame(compiled), implementations())

    assert tuple(frame.columns) == ROLE_FRAME_COLUMNS
    assert len(frame) == 1
    roles = frame.iloc[0]["roles"]
    assert roles["subject"] == {"type": "InputEntity@1", "keys": {"input_id": "IN-1"}}
    assert roles["target"] == {"type": "OutputEntity@1", "keys": {"output_id": "OUT-1"}}
    assert roles["occurred_at"] == OCCURRED_AT
    assert roles["event_key"] == "fixed-event"


class EquivalentPythonMapper(BaseLedgerMapper):
    def interpret_unit(self, context, unit, profile):
        sentence = next(iter(profile.mappings))
        row = unit.iloc[0]
        return [RoleEmission(
            sentence=sentence,
            roles={
                "subject": {"type": "InputEntity@1",
                            "keys": {"input_id": row["source_id"]}},
                "target": {"type": "OutputEntity@1",
                           "keys": {"output_id": row["target_id"]}},
                "occurred_at": row["event_at"],
                "event_key": row["event_key"],
            },
            source_row_refs=(unit.attrs["source_raw_ref"],),
        )]


def test_registered_python_mapper_and_declarative_mapper_share_contract():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    source = event_frame(compiled)

    declarative = map_event_frame(context, source, implementations())
    custom = map_event_frame(context, source, implementations(EquivalentPythonMapper))

    assert tuple(declarative.columns) == tuple(custom.columns) == ROLE_FRAME_COLUMNS
    assert semantic_frame(declarative) == semantic_frame(custom)


def test_mapper_override_of_final_map_is_rejected():
    class UnsafeMapper(BaseLedgerMapper):
        def map(self, context, event_frame, descriptor, profile):
            return event_frame

        def interpret_unit(self, context, unit, profile):
            return []

    registry = RoleMapperImplementationRegistry()
    with pytest.raises(RoleFrameError) as caught:
        registry.register("unsafe", 1, UnsafeMapper)
    assert caught.value.to_mapping() == {
        "code": "unsupported_mapper_override",
        "path": "mapper_type.map",
        "message": "BaseLedgerMapper.map() is final and cannot be overridden",
    }


def test_unsealed_mapper_registry_cannot_execute():
    compiled = snapshot()
    registry = RoleMapperImplementationRegistry()
    registry.register("map-transition-role", 1, DeclarativeRoleMapper)
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled), registry)
    assert caught.value.code == "mapper_registry_not_sealed"
    assert caught.value.path == "mapper_registry"


def test_pack_compiler_is_the_only_entity_ref_payload_builder():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    role_frame = map_event_frame(context, event_frame(compiled), implementations())

    ledger_frame = compile_role_frame(context, role_frame)

    assert ledger_frame.iloc[0]["subject_type"] == "InputEntity"
    assert ledger_frame.iloc[0]["subject_keys"] == {"input_id": "IN-1"}
    assert ledger_frame.iloc[0]["predicate"] == "moves_to"
    assert ledger_frame.iloc[0]["object_kind"] == "entity_ref"
    assert ledger_frame.iloc[0]["object_payload"] == {
        "type": "OutputEntity",
        "keys": {"output_id": "OUT-1"},
        "qualifiers": {"event_key": "E-1"},
    }
    assert ledger_frame.iloc[0]["derivation"] == "main_transition"
    assert ledger_frame.iloc[0]["source_translator_ver"].endswith("#main_transition")


def test_pack_compiler_maps_closed_none_object_to_existing_physical_nulls():
    compiled = snapshot(objectless_register_bundle())
    result = dry_run_event_frame(
        mapper_context(compiled, "input_rows"), event_frame(compiled),
        implementations())
    register = result.ledger_frame[
        result.ledger_frame["predicate"] == "register"].iloc[0]

    assert register["subject_type"] == "InputEntity"
    assert register["subject_keys"] == {"input_id": "IN-1"}
    assert register["object_kind"] is None
    assert register["object_payload"] is None


@pytest.mark.parametrize(
    ("object_kind", "role_kind", "value", "payload"),
    [
        ("value", "quantity", 12.5, {"value": 12.5}),
        ("event_ref", "identity", "EVENT-42", {"event": "EVENT-42"}),
    ],
)
def test_claim_compiler_supports_closed_scalar_object_kinds(
        object_kind, role_kind, value, payload):
    """Was `test_pack_compiler_...`.

    The three lines that hand-built the Claim (drop `target`, drop `event_key`, add a
    `result` role of kind `role_kind`, point `emit.object.value` at it) are gone: changing
    `object.kind` is now the WHOLE edit, and `predicate_claim` derives the same Role set
    -- under the canonical name `value`.  `role_kind` stays a parameter because it is what
    the derivation is being scored on, so it is asserted directly rather than declared.
    """
    raw = logical_bundle()
    raw["vocabulary"]["moves_to@1"]["object"] = {
        "kind": object_kind,
        "qualifiers": {"required": [], "optional": []},
    }
    mapping = source_profile(raw)["mappings"]["main_transition"]
    mapping["bind"].pop("target")
    mapping["bind"].pop("event_key")
    mapping["bind"]["value"] = constant(value)
    compiled = snapshot(raw)
    assert compiled.claims["moves_to@1"].roles["value"].kind == role_kind

    result = dry_run_event_frame(
        mapper_context(compiled, "input_rows"), event_frame(compiled),
        implementations())

    assert result.ledger_frame.iloc[0]["object_kind"] == object_kind
    assert result.ledger_frame.iloc[0]["object_payload"] == payload


class InvalidEntityMapper(EquivalentPythonMapper):
    def interpret_unit(self, context, unit, profile):
        emission = super().interpret_unit(context, unit, profile)[0]
        roles = dict(emission.roles)
        roles["target"] = {"type": "OutputEntity@1", "keys": {"wrong": "OUT-1"}}
        return [RoleEmission(
            sentence=emission.sentence,
            roles=roles,
            source_row_refs=emission.source_row_refs,
        )]


def test_invalid_stage_local_entity_shape_is_rejected_before_ledger_frame():
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(InvalidEntityMapper))
    assert caught.value.code == "invalid_entity_ref"
    assert caught.value.path == "role_frame.rows[0].roles.target.keys"
    assert caught.value.message


class WrongStageEntityMapper(EquivalentPythonMapper):
    def interpret_unit(self, context, unit, profile):
        emission = super().interpret_unit(context, unit, profile)[0]
        roles = dict(emission.roles)
        roles["subject"] = {
            "type": "OutputEntity@1", "keys": {"output_id": "OUT-1"}}
        return [RoleEmission(
            sentence=emission.sentence,
            roles=roles,
            source_row_refs=emission.source_row_refs,
        )]


def test_python_mapper_cannot_substitute_another_registered_stage_entity():
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(WrongStageEntityMapper))
    assert caught.value.code == "invalid_entity_ref"
    assert caught.value.path == "role_frame.rows[0].roles.subject.type"
    assert "Profile binding" in caught.value.message


class RawDataFrameMapper(BaseLedgerMapper):
    def interpret_unit(self, context, unit, profile):
        return pd.DataFrame({"raw": ["ledger"]})


class RawAtomMapper(BaseLedgerMapper):
    def interpret_unit(self, context, unit, profile):
        return [Atom(
            subject_type="InputEntity@1", subject_keys={"input_id": "IN-1"},
            predicate="moves_to@1")]


@pytest.mark.parametrize("mapper_type", [RawDataFrameMapper, RawAtomMapper])
def test_raw_dataframe_or_atom_mapper_output_is_rejected(mapper_type):
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(mapper_type))
    assert caught.value.code == "unsupported_mapper_output"
    assert caught.value.path.startswith("mapper.units[0]")


def test_role_and_ledger_frames_are_deterministic_under_row_reordering():
    raw = logical_bundle()
    driver_mapper(raw)["unit"] = {"kind": "row"}
    compiled = snapshot(raw)
    rows = [
        {"source_id": "IN-2", "target_id": "OUT-2",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
        {"source_id": "IN-1", "target_id": "OUT-1",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
    ]
    first_input = event_frame(compiled, rows)
    second_input = event_frame(compiled, list(reversed(rows)))
    context = mapper_context(compiled, "input_rows")

    first_roles = map_event_frame(context, first_input, implementations())
    second_roles = map_event_frame(context, second_input, implementations())
    first_ledger = compile_role_frame(context, first_roles)
    second_ledger = compile_role_frame(context, second_roles)

    assert semantic_frame(first_roles) == semantic_frame(second_roles)
    assert semantic_frame(first_ledger) == semantic_frame(second_ledger)
    refs = [value for values in first_roles["source_row_refs"].tolist()
            for value in values]
    assert len(refs) == len(set(refs)) == 2


def test_duplicate_derived_row_identity_requires_explicit_source_row_ref():
    raw = logical_bundle()
    driver_mapper(raw)["unit"] = {"kind": "row"}
    compiled = snapshot(raw)
    row = {"source_id": "IN-1", "target_id": "OUT-1",
           "event_at": OCCURRED_AT, "event_key": "E-1"}
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"),
            event_frame(compiled, [row, dict(row)]), implementations())
    assert caught.value.code == "ambiguous_source_row_ref"
    assert caught.value.path == "event_frame.rows"


def test_group_by_mapper_units_are_internal_and_deterministic():
    raw = logical_bundle()
    driver_mapper(raw)["unit"] = {
        "kind": "group_by", "columns": ["target_id"]}
    compiled = snapshot(raw)
    rows = [
        {"source_id": "IN-2", "target_id": "OUT-2",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
        {"source_id": "IN-1", "target_id": "OUT-1",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
    ]
    context = mapper_context(compiled, "input_rows")

    first = map_event_frame(
        context, event_frame(compiled, rows), implementations(EquivalentPythonMapper))
    second = map_event_frame(
        context, event_frame(compiled, list(reversed(rows))),
        implementations(EquivalentPythonMapper))

    assert len(first) == 2
    assert semantic_frame(first) == semantic_frame(second)


def test_binding_approval_metadata_never_creates_claim_class():
    raw_a = logical_bundle()
    raw_b = logical_bundle()
    source_profile(raw_b)["mappings"]["main_transition"]["bind"]["event_key"][
        "binding_origin"] = "imported"
    compiled_a = snapshot(raw_a)
    compiled_b = snapshot(raw_b)
    result_a = dry_run_event_frame(
        mapper_context(compiled_a, "input_rows"), event_frame(compiled_a),
        implementations())
    result_b = dry_run_event_frame(
        mapper_context(compiled_b, "input_rows"), event_frame(compiled_b),
        implementations())

    semantic_columns = ("subject_type", "subject_keys", "predicate", "object_kind",
                        "object_payload", "occurred_at", "derivation")
    assert {name: result_a.ledger_frame.iloc[0][name] for name in semantic_columns} == {
        name: result_b.ledger_frame.iloc[0][name] for name in semantic_columns}
    assert all("claim_class" not in str(value)
               for value in result_a.ledger_frame.iloc[0].tolist())


# The `pack` parameter -- adding a `note` role to the Claim -- became the same edit as
# `qualifier` on 2026-08-21: a Role is derived from the predicate's qualifier list, so
# there is no second declaration to move independently. It is not replaced by a copy of
# `vocabulary`; the two remaining parameters already differ in WHICH registry they move.
@pytest.mark.parametrize("change", ["vocabulary", "entity"])
def test_registry_semantic_changes_reach_snapshot_and_provenance(change):
    baseline = snapshot()
    raw = logical_bundle()
    if change == "vocabulary":
        # `layer` stood here until 2026-08-21, when it left the vocabulary declaration
        # (one legal value, so no decision to move).  `subjects` is its replacement for
        # the same reason it was chosen: it lands on `PredicateDescriptor` and nowhere
        # else, so this parameter still moves ONE registry.
        raw["vocabulary"]["moves_to@1"]["subjects"] = ["InputEntity@1", "OutputEntity@1"]
    else:
        # ⚰️ `key_types` was the semantic change this arm used until 2026-09-09, when it
        # was retired for having no reader. `class` replaces it for the same reason the
        # comment above gives for `subjects`: it lands on `EntityDescriptor` and nowhere
        # else, so this arm still moves exactly ONE registry.
        raw["entities"]["InputEntity@1"]["class"] = "static"
    changed = snapshot(raw)

    result = dry_run_event_frame(
        mapper_context(changed, "input_rows"), event_frame(changed), implementations())

    assert changed.snapshot_sha256 != baseline.snapshot_sha256
    assert result.snapshot_hash == changed.snapshot_sha256
    assert changed.snapshot_sha256 in result.ledger_frame.iloc[0]["source_translator_ver"]
    assert result.provenance["setup_snapshot_hash"] == changed.snapshot_sha256


def test_dry_run_returns_role_ledger_gate_preview_and_provenance_without_runtime():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    result = dry_run_event_frame(
        context, event_frame(compiled), implementations())

    assert len(result.role_frame) == len(result.ledger_frame) == 1
    assert result.gate_preview == {
        "status": "candidate",
        "atom_count": 1,
        "source_event_id": str(result.role_frame.iloc[0]["source_event_id"]),
        "declared_derivations": ("main_transition",),
        "declared_subject_types": ("InputEntity",),
    }
    assert result.provenance["sentences"] == ("main_transition",)
    assert not hasattr(context, "db")
    assert not hasattr(context, "cursor")
    assert not hasattr(context, "store")


def test_event_frame_context_and_snapshot_hash_are_fail_closed():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    frame = event_frame(compiled)
    del frame.attrs["molecule_ref"]
    with pytest.raises(RoleFrameError) as missing:
        map_event_frame(context, frame, implementations())
    assert missing.value.to_mapping() == {
        "code": "missing_event_context",
        "path": "event_frame.attrs.molecule_ref",
        "message": "attribute is required",
    }

    frame = event_frame(compiled)
    frame.attrs["setup_snapshot_hash"] = "0" * 64
    with pytest.raises(RoleFrameError) as mismatch:
        map_event_frame(context, frame, implementations())
    assert mismatch.value.code == "snapshot_mismatch"
    assert mismatch.value.path == "event_frame.attrs.setup_snapshot_hash"


class NaiveTimeMapper(EquivalentPythonMapper):
    def interpret_unit(self, context, unit, profile):
        emission = super().interpret_unit(context, unit, profile)[0]
        roles = dict(emission.roles)
        roles["occurred_at"] = datetime(2026, 8, 17, 10, 30)
        return [RoleEmission(
            sentence=emission.sentence,
            roles=roles,
            source_row_refs=emission.source_row_refs,
        )]


def test_naive_time_role_is_rejected_with_exact_path():
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(NaiveTimeMapper))
    assert caught.value.code == "invalid_time_role"
    assert caught.value.path == "role_frame.rows[0].roles.occurred_at"


#: Packages `roleframe` must not bind. The rule is 「could this name reach a session」, so
#: the subject is what an import BINDS, never how it is spelled (판정 460 ㉢).
CAPABILITY_FORBIDDEN = ("sqlalchemy", "psycopg2", "database", "ledger.store",
                        "ledger.gate", "ledger.cursor", "virtual_join")

#: (module, name) -> why this ONE name is allowed out of a forbidden package.
#:
#: 🔴 WRITTEN DOWN, BECAUSE 「PASSES」 AND 「IS PERMITTED」 WERE THE SAME PICTURE (판정 460 ㉡).
#: `clean_str_value` was passing not because anything allowed it but because the predicate
#: could not SEE it - and `SessionLocal`, the session factory itself, passed the same way.
#: The right answer was arriving for the wrong reason, and the wrong answer was arriving
#: silently beside it. An allowance has to be a sentence somebody wrote.
#:
#: The reason for the first two is quoted, not invented: `roleframe`'s own docstring says
#: they are 「a PURE helper that happens to live in `database.crud`, which is why the
#: capability guard forbids the `database` package rather than that one import」.
CAPABILITY_ALLOWED = {
    ("database.crud", "clean_str_value"): "pure helper, no session (roleframe's docstring)",
    ("database.crud", "is_blank_key_part"): "pure predicate, pinned by contracts/blank_predicate",
    ("virtual_join.config", "INDEX_PREFIX"): "a bare string constant; binds no module",
}


def _forbidden_root(dotted, forbidden):
    """The forbidden package `dotted` sits under, or None.

    🔴 BY DOTTED PREFIX, NOT BY EQUALITY. `import database.crud` puts 「database」 in the
    namespace, and an equality test against 「database」 never saw it because the alias records
    the full path. That one was the gate's whole reason for existing.
    """
    for bad in forbidden:
        if dotted == bad or dotted.startswith(bad + "."):
            return bad
    return None


#: `roleframe.py` lives here, and a relative import resolves against THIS package.
CAPABILITY_PACKAGE = "ledger"


def _resolve_relative(module, level, package):
    """The absolute dotted path a `from ... import` names, relative spellings included.

    `level` is the leading-dot count: 1 = this package, 2 = its parent. A relative import
    with a `level` and NO `module` names the package ITSELF, and then each alias is a
    SUBMODULE of it - the widest form there is, and the one the old predicate dropped
    whole, because `and node.module` discarded the node before anything looked at it.
    """
    if not level:
        return module or ""
    base = package
    for _ in range(level - 1):
        base = base.rpartition(".")[0]
    if not module:
        return base
    return "%s.%s" % (base, module) if base else module


def capability_reaches(tree, forbidden=CAPABILITY_FORBIDDEN, allowed=CAPABILITY_ALLOWED,
                       package=CAPABILITY_PACKAGE):
    """Every import in `tree` that BINDS something from a forbidden package.

    🔴 FOUR FORMS BIND FOUR DIFFERENT THINGS, AND THE OLD PREDICATE FOLDED THEM INTO ONE
    STRING (판정 460, then 판정 462 for the last):
        import a.b            binds `a`        - the package itself is in reach
        import a.b as x       binds module a.b - a module of it is in hand
        from a.b import c     binds `c`        - depends entirely on what `c` IS
        from . import b       binds module a.b - the `import` case in another spelling
    Only the third can ever be safe, and only when somebody has written down which name.

    ⚠️ THE RELATIVE SPELLING IS THIS FILE'S OWN DIALECT, not a form nobody would write:
    `roleframe.py` already calls three siblings as `from .envelope import ...`. So
    `from .store import Store` is what FOLLOWING THE FILE'S HABIT looks like, and until
    판정 462 the gate had nothing to say about it.
    """
    import ast as _ast

    reached = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                bad = _forbidden_root(alias.name, forbidden)
                if bad:
                    reached.append("%s (binds %s)"
                                   % (alias.name, alias.asname or alias.name.split(".")[0]))
        elif isinstance(node, _ast.ImportFrom):
            base = _resolve_relative(node.module, node.level, package)
            if node.level and not node.module:
                # Binds MODULES. The allowance table cannot speak for this form: it names
                # (module, name) pairs, and here every name IS a module.
                for alias in node.names:
                    dotted = "%s.%s" % (base, alias.name) if base else alias.name
                    if _forbidden_root(dotted, forbidden):
                        reached.append("%s (binds %s)"
                                       % (dotted, alias.asname or alias.name))
                continue
            if not _forbidden_root(base, forbidden):
                continue
            for alias in node.names:
                if (base, alias.name) in allowed:
                    continue
                reached.append("%s.%s" % (base, alias.name))
    return sorted(reached)


def test_roleframe_module_has_no_runtime_or_database_imports():
    path = Path(__file__).parents[1] / "ledger" / "roleframe.py"
    assert capability_reaches(ast.parse(path.read_text(encoding="utf-8"))) == []


#: (cell, source, is it reached) - the form table, drawn from the GRAMMAR GRID rather
#: than from the forms I could think of (판정 462 ④). 460 fixed the predicate by feeding
#: it seven forms; all seven were absolute, and so were the two I added to check the fix,
#: so the relative half of the grammar stayed unmeasured and four of its five spellings
#: were let through. A remembered list is a sample; the grid is the population:
#:     ast.Import      × {dotted · plain} × {as · no as}          = 4 cells
#:     ast.ImportFrom  × {level 0 · 1 · 2} × {module · bare}      = 6 cells
#: `ImportFrom L0 bare` is the one cell the grammar does not build, and it is ASSERTED
#: below rather than dropped - a missing row reads as a pass.
CAPABILITY_GRID = tuple("Import %s" % k for k in ("dotted", "dotted+as", "plain", "plain+as")) + \
    tuple("ImportFrom L%d %s" % (level, kind)
          for level in (0, 1, 2) for kind in ("module", "bare"))

#: The cell the grammar refuses to produce, so no source line can occupy it.
CAPABILITY_UNGRAMMATICAL = "ImportFrom L0 bare"

CAPABILITY_FORMS = (
    ("Import dotted", "import virtual_join.config", True),
    ("Import dotted", "import database.crud", True),
    ("Import dotted", "import utils.time_format", False),
    ("Import dotted+as", "import virtual_join.config as vjc", True),
    ("Import plain", "import virtual_join", True),
    ("Import plain", "import json", False),
    ("Import plain+as", "import virtual_join as vj", True),
    ("Import plain+as", "import pandas as pd", False),
    ("ImportFrom L0 module", "from virtual_join import executor", True),
    ("ImportFrom L0 module", "from database.crud import SessionLocal", True),
    ("ImportFrom L0 module", "from database.crud import clean_str_value", False),
    ("ImportFrom L0 module", "from virtual_join.config import INDEX_PREFIX", False),
    ("ImportFrom L1 module", "from .store import Store", True),
    ("ImportFrom L1 module", "from .gate import Gate", True),
    ("ImportFrom L1 module", "from .envelope import source_event_identity", False),
    ("ImportFrom L1 bare", "from . import store", True),
    ("ImportFrom L1 bare", "from . import cursor", True),
    ("ImportFrom L1 bare", "from . import envelope", False),
    ("ImportFrom L2 module", "from ..database import crud", True),
    ("ImportFrom L2 module", "from ..utils import time_format", False),
    ("ImportFrom L2 bare", "from .. import database", True),
    ("ImportFrom L2 bare", "from .. import utils", False),
)


@pytest.mark.parametrize("cell,source,reached", CAPABILITY_FORMS)
def test_the_capability_predicate_is_fed_forms_rather_than_trusted(cell, source, reached):
    """⚰️ RUNNING THE GATE AND READING 「35 passed」 PROVED NOTHING, AND I DID IT TWICE.

    A green there means 「roleframe does not use a forbidden name IN A SHAPE THIS PREDICATE
    CAN SEE」, and I read it as 「the predicate is fixed」. The step between them - 「can it
    see?」 - was missing, so four of seven forms went unnoticed, `SessionLocal` included:
    the session factory itself, in the gate whose entire question is 「could this reach a
    session」.

    ⚰️ AND THE REPAIR REPEATED THE DEFECT ONE AXIS OVER. The seven forms were all absolute,
    so `from .store import Store` - the spelling this very file uses for its siblings - was
    still permitted afterwards. The rows now come off the grammar grid.

    🔴 I ALSO 「VERIFIED DIRECTLY」 WITH A PROBE THAT DID NOT MATCH THE GATE. My check
    used `startswith`; the assertion used set intersection. So the probe answered a question
    the product never asks, and its answer went into a commit message as proof. Feeding the
    predicate its own inputs is the only check that cannot drift from it.
    """
    got = capability_reaches(ast.parse(source))
    assert bool(got) is reached, (cell, source, got)


def test_every_grammar_cell_carries_a_form():
    """🔴 빈 칸은 «빼지 말고 단언한다» — a cell with no row reads as a pass."""
    covered = {cell for cell, _s, _r in CAPABILITY_FORMS}
    assert covered == set(CAPABILITY_GRID) - {CAPABILITY_UNGRAMMATICAL}
    for cell in CAPABILITY_GRID:
        if cell == CAPABILITY_UNGRAMMATICAL:
            continue
        # every cell that CAN hold a forbidden import has one that is actually caught
        assert any(c == cell and reach for c, _s, reach in CAPABILITY_FORMS), cell


def test_the_empty_cell_is_empty_because_the_grammar_refuses_it():
    """`from import x` is not a Python statement, which is why L0 has no bare form."""
    with pytest.raises(SyntaxError):
        ast.parse("from import store")


def test_a_bare_relative_import_binds_the_module_itself():
    """🔴 `from . import store` is the WIDEST form and the one that was skipped whole.

    `and node.module` dropped the node before the alias loop, so the single line that hands
    over a whole sibling module was the one line the gate never read.
    """
    reached = capability_reaches(ast.parse("from . import store, envelope, cursor"))
    assert reached == ["ledger.cursor (binds cursor)", "ledger.store (binds store)"]


def test_the_allowances_are_named_rather_than_invisible():
    """⚠️ 「PASSES」 MUST NOT BE THE SAME PICTURE AS 「IS PERMITTED」. Every name that gets
    out of a forbidden package is in the table with a sentence; delete the entry and the
    import goes red, which is what makes the next pure helper a decision rather than a
    coincidence.
    """
    for (module, name), why in CAPABILITY_ALLOWED.items():
        assert _forbidden_root(module, CAPABILITY_FORBIDDEN), (module, "not even forbidden")
        assert why.strip(), (module, name)
        assert capability_reaches(
            ast.parse("from %s import %s" % (module, name))) == [], (module, name)
        # ... and with the allowance removed it is caught, so the entry is load-bearing.
        without = {k: v for k, v in CAPABILITY_ALLOWED.items() if k != (module, name)}
        assert capability_reaches(
            ast.parse("from %s import %s" % (module, name)), allowed=without) != []


def test_all_eventframe_context_attributes_are_preserved_in_roleframe():
    compiled = snapshot()
    source = event_frame(compiled)
    result = map_event_frame(
        mapper_context(compiled, "input_rows"), source, implementations())
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        assert result.attrs[name] == source.attrs[name]


# ---------------------------------------------------------------------------
# S-52 ②  속성은 «키 옆»에 실리고, «정체성이 아니다»
# ---------------------------------------------------------------------------

def _bundle_with_attribute(column="event_key"):
    """소스가 `InputEntity@1` 의 `product` 를 «한 번» 맵는 번들."""
    raw = logical_bundle()
    raw["entities"]["InputEntity@1"]["attributes"] = ["product"]
    raw["sources"]["input_rows"]["bind"]["entities"] = {
        "InputEntity@1": {"attributes": {"product": {"kind": "column",
                                                     "column": column}}}}
    return raw


def _subject_of(raw, want_source=False):
    compiled = snapshot(raw)
    context = mapper_context(compiled, "input_rows")
    source = event_frame(compiled)
    frame = map_event_frame(context, source, implementations())
    subject = frame.iloc[0]["roles"]["subject"]
    return (subject, source) if want_source else subject


def test_an_entity_payload_carries_its_attributes_beside_its_keys():
    subject, source = _subject_of(_bundle_with_attribute(), want_source=True)

    assert subject["keys"] == {"input_id": "IN-1"}
    # 값은 픽스처에서 «읽는다** — 여기에 적으면 컬럼이 바뀌는 날 이 시험이 «그 이유로» 죽는다.
    assert dict(subject["attributes"]) == {"product": source.iloc[0]["event_key"]}


def test_the_source_binds_it_once_and_every_sentence_of_that_source_inherits_it():
    """㉦ 판정 124 의 핵심. 속성이 «문장의 것»이면 K 문장에 K 번 적어야 하고, 그러면
    어긋날 자리가 K 개다 — 그 불일치는 «이 스키마가 만든» 것이지 데이터의 것이 아니다."""
    raw = _bundle_with_attribute()
    # 같은 타입을 주어로 쓰는 «둘째 문장** — bind.entities 는 «그대로 하나**.
    mappings = raw["sources"]["input_rows"]["bind"]["mappings"]
    second = copy.deepcopy(mappings["main_transition"])
    mappings["second_sentence"] = second
    raw["vocabulary"]["moves_to@1"]["object"]["types"] = ["OutputEntity@1"]

    compiled = snapshot(raw)
    profile = compiled.profiles["input_rows"]
    for sentence in ("main_transition", "second_sentence"):
        bound = profile.mappings[sentence].bindings["subject"]["attributes"]
        assert set(bound) == {"product"}, sentence


def test_an_attribute_does_not_change_what_makes_two_rows_the_same_entity():
    """🔴 이 축의 «판별식». 속성만 다른 두 페이로드는 «같은 엔티티»다 — 엔티티를 그 엔티티로
    만드는 것은 `keys` 이고, 이게 깨지면 속성 하나를 더할 때마다 걷기가 «새 노드»를 낳는다.

    ⚠️ 「같은 «원자»다」와는 «다른 말**이다 — 아래 시험이 그 둘을 가른다."""
    plain = _subject_of(logical_bundle())
    with_attr = _subject_of(_bundle_with_attribute())
    other_value = _subject_of(_bundle_with_attribute(column="source_id"))

    assert with_attr["keys"] == plain["keys"]
    assert other_value["keys"] == with_attr["keys"]
    assert other_value["attributes"] != with_attr["attributes"], (
        "the fixture must actually differ, or this asserts nothing")


def test_a_declaration_that_binds_no_attribute_produces_the_payload_it_always_did():
    """㉤ 무회귀. «키 없음»이지 «빈 값»이 아니다 — 이 축이 있기 «전»에 쓰인 원자와
    이 축이 있고 «안 적은» 선언의 원자가 «같은 바이트»여야 한다."""
    subject = _subject_of(logical_bundle())

    assert subject == {"type": "InputEntity@1", "keys": {"input_id": "IN-1"}}
    assert "attributes" not in subject


def test_the_two_dedupe_spellings_agree_that_an_attribute_makes_a_new_atom():
    """㉠ (판정 125) — 「원자가 같은가」를 «두 곳»이 답한다: Python 의 `identity` 와
    DB 의 정체성 인덱스. 두 철자가 갈리면 한쪽이 «조용히» 다른 답을 낸다.

    🔴 그리고 이 시험이 «제 문장 하나를 정정»한다. 층 ② 커밋이 「id·중복은 keys 만 읽는다」고
    적었는데, 그건 «주어 쪽»(평면 컬럼 둘)에만 참이고 «목적어»는 페이로드 «전체»가 재료다.
    속성이 바뀌면 «새 원자»이고, 그것이 판정 125 가 이력을 얻는 방식이다 — 결함이 아니다.
    """
    from ledger.envelope import Atom
    from ledger.schema import DEDUPE_COLUMNS

    def atom(product):
        return Atom(
            id="a", subject_type="InputEntity@1", subject_keys={"input_id": "IN-1"},
            predicate="moves_to@1", object_kind="entity_ref",
            object_payload={"type": "OutputEntity@1", "keys": {"output_id": "OUT-1"},
                            "attributes": {"product": product}},
            occurred_at=OCCURRED_AT, source_translator_ver="v1", source_raw_ref="r1")

    # ① Python 쪽: 속성만 달라도 «다른 원자»다.
    assert atom("A").identity() != atom("B").identity()
    assert atom("A").identity() == atom("A").identity()

    # ② DB 쪽이 «같은 재료»를 쓰는가 — 컬럼 이름에서 읽는다(그 표현식이 정본이므로).
    joined = " ".join(DEDUPE_COLUMNS)
    assert "object_payload" in joined, (
        "the database's identity index must read the payload, or the two spellings "
        "disagree about an attribute and one of them lets a duplicate through")
    assert len(DEDUPE_COLUMNS) == len(atom("A").identity()), (
        "the two dedupe spellings must carry the same number of fields")
