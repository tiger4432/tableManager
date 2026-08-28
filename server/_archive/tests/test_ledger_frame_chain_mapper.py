"""Phase 3: Chain mappers return one validated pandas LedgerFrame contract."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import pandas as pd
import pytest

from ledger import gate
from ledger import config as ledger_config
from ledger.chain_mapper import (
    LedgerMapperContext,
    LedgerMapperError,
    LedgerMapperRegistry,
    default_ledger_mapper_registry,
    describe_mapper,
    deterministic_source_event_context,
    mapper_execution_version,
    mapper_provenance,
    run_registered_mapper,
)
from ledger.envelope import Atom
from ledger.ledger_frame import (
    LEDGER_FRAME_ATTR,
    LEDGER_FRAME_COLUMNS,
    LedgerFrameError,
    atoms_from_ledger_frame,
    empty_ledger_frame,
    ledger_frame_from_atoms,
    validate_ledger_frame,
)
from ledger.profile_chain_mapper import (
    ClaimEmitterRegistry,
    DeclaredLookupAdapter,
)
from ledger.source_profile import (
    validate_profile,
)


WORLD_TIME = datetime(2026, 8, 17, 1, 2, 3, tzinfo=timezone.utc)


def atom(**changes):
    values = {
        "subject_type": "Lot",
        "subject_keys": {"lot": "L1"},
        "predicate": "derived_from",
        "object_kind": "entity_ref",
        "object_payload": {"type": "Lot", "keys": {"lot": "P1"}},
        "occurred_at": WORLD_TIME,
        "source_who": "test_source",
        "source_translator_ver": "test-v1#pair_field",
        "source_raw_ref": "test_source:{\"row\":1}",
        "molecule_ref": "event-1",
        "derivation": "pair_field",
    }
    values.update(changes)
    return Atom(**values)


def test_valid_ledger_frame_round_trips_existing_atom_without_flattening():
    original = atom(object_payload={"type": "Lot", "keys": {"lot": "P1"},
                                    "qualifiers": {"slot": 0}})
    frame = ledger_frame_from_atoms([original])
    assert validate_ledger_frame(frame) is frame
    assert tuple(frame.columns) == LEDGER_FRAME_COLUMNS
    assert frame.iloc[0]["subject_keys"] == {"lot": "L1"}
    assert frame.iloc[0]["object_payload"]["qualifiers"]["slot"] == 0
    rebuilt = atoms_from_ledger_frame(frame)[0]
    assert rebuilt.subject_keys == original.subject_keys
    assert rebuilt.object_payload == original.object_payload


def test_ledger_frame_missing_field_wrong_type_and_bad_structures_fail_closed():
    frame = ledger_frame_from_atoms([atom()])
    missing = frame.drop(columns=["derivation"])
    with pytest.raises(LedgerFrameError) as exc:
        validate_ledger_frame(missing)
    assert exc.value.code == "invalid_ledger_frame_schema"

    wrong_time = frame.copy(deep=True)
    wrong_time.attrs.update(frame.attrs)
    wrong_time.at[0, "occurred_at"] = "2026-08-17"
    with pytest.raises(LedgerFrameError) as exc:
        validate_ledger_frame(wrong_time)
    assert exc.value.code == "invalid_occurred_at"

    flat_identity = frame.copy(deep=True)
    flat_identity.attrs.update(frame.attrs)
    flat_identity.at[0, "subject_keys"] = "lot=L1"
    with pytest.raises(LedgerFrameError) as exc:
        validate_ledger_frame(flat_identity)
    assert exc.value.code == "invalid_structured_identity"

    flat_payload = frame.copy(deep=True)
    flat_payload.attrs.update(frame.attrs)
    flat_payload.at[0, "object_payload"] = '{"lot":"P1"}'
    with pytest.raises(LedgerFrameError) as exc:
        validate_ledger_frame(flat_payload)
    assert exc.value.code == "invalid_structured_payload"


def test_none_arbitrary_frame_and_explicit_empty_are_three_different_results():
    with pytest.raises(LedgerFrameError) as exc:
        validate_ledger_frame(None)
    assert exc.value.code == "missing_ledger_frame"
    with pytest.raises(LedgerFrameError) as exc:
        validate_ledger_frame(pd.DataFrame(columns=LEDGER_FRAME_COLUMNS))
    assert exc.value.code == "unmarked_ledger_frame"
    empty = empty_ledger_frame()
    assert empty.empty
    assert empty.attrs[LEDGER_FRAME_ATTR] == 1
    assert validate_ledger_frame(empty) is empty


def test_dataframe_index_never_changes_source_event_identity():
    first = ledger_frame_from_atoms([atom()])
    second = first.copy(deep=True)
    second.attrs.update(first.attrs)
    second.index = [987654321]
    validate_ledger_frame(second)
    assert second.iloc[0]["source_event_id"] == first.iloc[0]["source_event_id"]
    assert atoms_from_ledger_frame(second)[0].source_event_id == (
        atoms_from_ledger_frame(first)[0].source_event_id)


def test_driver_source_event_context_is_deterministic_and_index_free():
    first = [
        {"row_identity": "R2", "ignored": 2},
        {"row_identity": "R1", "ignored": 1},
    ]
    second = list(reversed(first))
    assert deterministic_source_event_context(
        "source", first, identity_fields=("row_identity",)) == (
            deterministic_source_event_context(
                "source", second, identity_fields=("row_identity",)))


def test_one_explicit_source_event_cannot_be_split_by_time_or_partially_gated():
    later = datetime(2026, 8, 17, 1, 2, 4, tzinfo=timezone.utc)
    with pytest.raises(LedgerFrameError) as exc:
        ledger_frame_from_atoms([atom(), atom(occurred_at=later)])
    assert exc.value.code == "inconsistent_source_event"

    frame = ledger_frame_from_atoms([
        atom(),
        atom(predicate="word_not_in_vocabulary", subject_keys={"lot": "L2"}),
    ])
    atoms = atoms_from_ledger_frame(frame)
    assert len({item.source_event_id for item in atoms}) == 1
    with gate.building_molecule("test_source"):
        with pytest.raises(gate.MoleculeRefused):
            gate.screen_molecule(
                "test_source", atoms, {"pair_field"}, {"Lot"},
                molecule_ref="event-1", source_rows=1)


LOT_SOURCE_CONFIG = {
    "kind": "lineage",
    "occurred_at_column": "event_time",
    "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
    "occurred_at_timezone": "Asia/Seoul",
    "subject_types": ["Lot", "Wafer"],
    "register_entity_types": ["Lot", "Wafer"],
    "list_separator": ":",
    "columns": {
        "row_identity": "row_id", "lot": "lot", "event_type": "event_type",
        "parent_lot": "parent_lot", "child_lot": "child_lot",
        "slots": "slots", "wafers": "wafers",
    },
    "vocabulary": {
        "split": {"lineage": "parent_child", "slot_pairing": "slot_preserving",
                  "emit_has_wafer": True, "emit_register": True},
        "merge": {"lineage": "parent_child", "slot_pairing": "shared_wafer",
                  "emit_has_wafer": True, "emit_register": True},
        "track_in": {"lineage": "none", "slot_pairing": "none",
                     "emit_has_wafer": True, "emit_register": True},
    },
}


def lot_rows(index=(3, 9)):
    rows = [
        {"lot": "P", "event_type": "split", "slots": "1:2",
         "wafers": "W1:W2", "parent_lot": "", "child_lot": "C",
         "row_identity": "R1", "event_time": "2026-08-17T10:00:00"},
        {"lot": "C", "event_type": "split", "slots": "3",
         "wafers": "W3", "parent_lot": "P", "child_lot": "",
         "row_identity": "R2", "event_time": "2026-08-17T10:00:00"},
    ]
    return pd.DataFrame(rows, dtype=object, index=list(index))


def test_mapper_failure_unknown_mapper_and_capability_boundary_are_explicit():
    with pytest.raises(LedgerMapperError) as exc:
        run_registered_mapper("not-registered", 1, lot_rows())
    assert exc.value.code == "unknown_mapper"
    context = LedgerMapperContext()
    assert not hasattr(context, "commit")
    assert not hasattr(context, "cursor")
    assert not hasattr(context, "engine")


def approved(kind, **values):
    return {
        "kind": kind,
        **values,
    }


def movement_profile():
    return {
        "profile_version": 1,
        "source": "simple_moves",
        "packs": ["transfer@1"],
        "mappings": [{
            "mapping_id": "move",
            "use": "transfer/movement",
            "bind": {
                "subject": approved("column", column="ITEM_ID"),
                "from": approved("constant", value="source_position"),
                "to": approved(
                    "declared_lookup", lookup_id="destination",
                    key=approved("column", column="MOVE_ID"), select="container"),
                "occurred_at": approved("column", column="EVENT_TIME"),
                "qty": approved("constant", value=2),
            },
        }],
    }


def destination_lookup(result_count=1):
    def resolve_many(_values, keys):
        return {
            json.dumps(key, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")): [
                {"container": {"type": "dt_slot",
                               "keys": {"dt_lot": "D1", "dt_slot": "01"},
                               "position": None}}
                for _ in range(result_count)
            ]
            for key in keys
        }
    return DeclaredLookupAdapter("destination", ("container",), resolve_many)


def profile_input():
    return pd.DataFrame([{
        "ITEM_ID": "W1", "MOVE_ID": "M1",
        "EVENT_TIME": "2026-08-17T01:02:03+00:00",
    }], index=[778], dtype=object)


def profile_rule(profile=None, **changes):
    out = {
        "profile_id": "simple-moves",
        "profile": profile or movement_profile(),
        "source": "simple_moves",
        "source_event": {
            "molecule_ref": "simple_moves:M1",
            "source_raw_ref": "simple_moves:{\"MOVE_ID\":\"M1\"}",
        },
    }
    out.update(changes)
    return out


def profile_context(adapter=None):
    adapter = adapter or destination_lookup()
    return LedgerMapperContext(lookups={adapter.lookup_id: adapter})


def test_profile_mapper_evaluates_column_constant_and_nested_lookup_key():
    frame = run_registered_mapper(
        "canonical-profile", 1, profile_input(),
        context=profile_context(), rule=profile_rule())
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["subject_keys"] == {"wafer": "W1"}
    assert row["object_payload"] == {
        "from": {"type": "wafer_grid", "keys": {"wafer": "W1"},
                 "position": None},
        "to": {"type": "dt_slot", "keys": {"dt_lot": "D1", "dt_slot": "01"},
               "position": None},
        "qty": 2,
    }
    assert row["occurred_at"] == WORLD_TIME
    assert "mapper:canonical-profile@1:" in row["source_translator_ver"]
    assert frame.attrs["gate_contract"]["declared_derivations"] == (
        "profile_transfer_movement",)


def test_profile_content_is_part_of_the_existing_cursor_execution_version():
    descriptor = default_ledger_mapper_registry().get("canonical-profile", 1)
    first = validate_profile(movement_profile())
    changed_raw = movement_profile()
    changed_raw["mappings"][0]["bind"]["qty"]["value"] = 3
    changed = validate_profile(changed_raw)
    first_version = mapper_execution_version(
        "base", descriptor, profile_id="simple-moves", profile=first)
    changed_version = mapper_execution_version(
        "base", descriptor, profile_id="simple-moves", profile=changed)
    assert first_version != changed_version
    assert "profile:simple-moves:" in first_version


def test_profile_declared_lookup_batches_unique_keys_without_n_plus_one():
    calls = []

    def resolve_many(_values, keys):
        calls.append(keys)
        return {
            json.dumps(key, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")): [{
                           "container": {
                               "type": "dt_slot",
                               "keys": {"dt_lot": "D1", "dt_slot": str(key)},
                               "position": None,
                           },
                       }]
            for key in keys
        }

    frame = pd.DataFrame([
        {"ITEM_ID": "W1", "MOVE_ID": "M1", "EVENT_TIME": WORLD_TIME.isoformat()},
        {"ITEM_ID": "W2", "MOVE_ID": "M2", "EVENT_TIME": WORLD_TIME.isoformat()},
        {"ITEM_ID": "W3", "MOVE_ID": "M1", "EVENT_TIME": WORLD_TIME.isoformat()},
    ], dtype=object)
    adapter = DeclaredLookupAdapter("destination", ("container",), resolve_many)
    mapped = run_registered_mapper(
        "canonical-profile", 1, frame,
        context=profile_context(adapter), rule=profile_rule())
    assert len(mapped) == 3
    assert calls == [("M1", "M2")]


def test_profile_emitter_fails_closed_on_malformed_entity_and_position_shapes():
    malformed_subject = profile_input()
    malformed_subject.at[malformed_subject.index[0], "ITEM_ID"] = {
        "type": "Lot", "keys": {"lot": "L1"},
    }
    with pytest.raises(LedgerMapperError) as exc:
        run_registered_mapper(
            "canonical-profile", 1, malformed_subject,
            context=profile_context(), rule=profile_rule())
    assert exc.value.code == "invalid_claim_value"
    assert exc.value.path.endswith("bind.subject")

    invalid_position = DeclaredLookupAdapter(
        "destination", ("container",),
        lambda _values, keys: {
            json.dumps(key, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")): [{
                           "container": {"type": "dt_slot", "keys": {"": "D1"},
                                         "position": None},
                       }]
            for key in keys
        },
    )
    with pytest.raises(LedgerMapperError) as exc:
        run_registered_mapper(
            "canonical-profile", 1, profile_input(),
            context=profile_context(invalid_position), rule=profile_rule())
    assert exc.value.code == "invalid_claim_value"
    assert exc.value.path.endswith("bind.to")


def test_profile_mapper_can_explicitly_return_normal_empty_ledger_frame():
    silent = {
        "profile_version": 1,
        "source": "silent_source",
        "packs": [],
        "mappings": [],
    }
    frame = run_registered_mapper(
        "canonical-profile", 1,
        pd.DataFrame([{"anything": 1}], dtype=object),
        context=LedgerMapperContext(),
        rule={
            "profile_id": "silent-profile",
            "profile": silent,
            "source": "silent_source",
            "source_event": {
                "molecule_ref": "silent:1",
                "source_raw_ref": "silent:{\"id\":1}",
            },
        },
    )
    assert frame.empty
    assert validate_ledger_frame(frame) is frame


# DELETED 2026-08-21 with the field it measured:
# `test_profile_mapper_reuses_readiness_gate_for_pending_and_rejected` (two
# parameters). It drove a nested lookup key's `approval_status` to a value no file in
# the tree ever held; the field retired for holding one reachable value, so the
# refusal it asserted is underivable rather than merely unchecked. That the mapper
# REUSES the readiness gate instead of carrying its own is still true and is stated
# by `profile_chain_mapper` calling `require_executable_profile`.


@pytest.mark.parametrize(("count", "code"), [
    (0, "lookup_not_found"),
    (2, "lookup_not_unique"),
])
def test_profile_lookup_zero_and_many_are_fail_closed(count, code):
    with pytest.raises(LedgerMapperError) as exc:
        run_registered_mapper(
            "canonical-profile", 1, profile_input(),
            context=profile_context(destination_lookup(count)), rule=profile_rule())
    assert exc.value.code == code


def test_profile_claim_without_registered_emitter_is_rejected():
    with pytest.raises(LedgerMapperError) as exc:
        run_registered_mapper(
            "canonical-profile", 1, profile_input(), context=profile_context(),
            rule=profile_rule(emitter_registry=ClaimEmitterRegistry().seal()))
    assert exc.value.code == "unsupported_claim_execution"


def test_a_retired_binding_field_changes_nothing_the_mapper_emits():
    """Was `test_binding_approval_metadata_never_promotes_...`.

    It set `binding_origin: imported` on one binding and asserted the emitted claim
    was identical to the `user_declared` one. The field retired on 2026-08-21 -- but
    the assertion gets SHARPER rather than deleted, because every v1 Profile on disk
    still writes all three names and this proves a mapper fed one emits the same
    frame as a mapper fed none.
    """
    plain = movement_profile()
    stamped = copy.deepcopy(plain)
    stamped["mappings"][0]["bind"]["subject"].update({
        "binding_origin": "imported",
        "approval_status": "rejected",
        "suggestion_reason": "header similarity",
    })
    plain_frame = run_registered_mapper(
        "canonical-profile", 1, profile_input(), context=profile_context(),
        rule=profile_rule(plain))
    stamped_frame = run_registered_mapper(
        "canonical-profile", 1, profile_input(), context=profile_context(),
        rule=profile_rule(stamped))
    assert plain_frame.iloc[0]["derivation"] == "profile_transfer_movement"
    assert stamped_frame.iloc[0]["derivation"] == "profile_transfer_movement"
    assert plain_frame.iloc[0]["predicate"] == stamped_frame.iloc[0]["predicate"]


def test_mapper_result_must_be_ledger_frame_and_crashes_are_typed():
    def arbitrary(_db, _payload, rule=None):
        del rule
        return pd.DataFrame()

    def crashes(_db, _payload, rule=None):
        del rule
        raise ZeroDivisionError("boom")

    def schema_error(_db, _payload, rule=None):
        del rule
        return ledger_frame_from_atoms([atom(occurred_at="not-a-time")])

    arbitrary_registry = LedgerMapperRegistry((
        describe_mapper("arbitrary", 1, arbitrary),
        describe_mapper("crashes", 1, crashes),
        describe_mapper("schema-error", 1, schema_error),
    )).seal()
    with pytest.raises(LedgerFrameError) as exc:
        run_registered_mapper(
            "arbitrary", 1, {}, registry=arbitrary_registry)
    assert exc.value.code == "unmarked_ledger_frame"
    with pytest.raises(LedgerMapperError) as exc:
        run_registered_mapper("crashes", 1, {}, registry=arbitrary_registry)
    assert exc.value.code == "mapper_failed"
    with pytest.raises(LedgerFrameError) as exc:
        run_registered_mapper("schema-error", 1, {}, registry=arbitrary_registry)
    assert exc.value.code == "invalid_source_event"


def test_default_registry_exposes_logical_ids_not_module_paths():
    registry = default_ledger_mapper_registry()
    metadata = registry.public_metadata()
    # Members, not a count: ``lot-event``@1 was retired with its module on 2026-08-18
    # and a bare length assertion would go green again the day anything replaces it.
    assert [item["mapper_id"] for item in metadata] == ["canonical-profile"]
    assert all("module" not in item and "path" not in item and "function" not in item
               for item in metadata)
    assert default_ledger_mapper_registry() is registry


def test_source_transition_is_explicit_and_config_cannot_execute_module_paths():
    base = {
        "version": 1,
        "sources": {"lot_event": copy.deepcopy(LOT_SOURCE_CONFIG)},
    }
    # No selector means the unconverted legacy path; adding the logical registry key is
    # the complete source-by-source transition declaration.
    assert ledger_config.validate(copy.deepcopy(base))
    selected = copy.deepcopy(base)
    selected["sources"]["lot_event"]["chain_mapper"] = {
        "mapper_id": "lot-event", "version": 1,
    }
    assert ledger_config.validate(selected)
    unsafe = copy.deepcopy(selected)
    unsafe["sources"]["lot_event"]["chain_mapper"]["module"] = "evil.path"
    with pytest.raises(ledger_config.LedgerConfigError):
        ledger_config.validate(unsafe)

    ignored = copy.deepcopy(selected)
    ignored["sources"]["lot_event"]["kind"] = "transfer"
    with pytest.raises(ledger_config.LedgerConfigError, match="not executable"):
        ledger_config.validate(ignored)


def test_canonical_mapper_selects_one_validated_profile_by_explicit_id():
    cfg = {
        "version": 1,
        "profiles": {"simple-moves-v1": movement_profile()},
        "sources": {"simple_moves": copy.deepcopy(LOT_SOURCE_CONFIG)},
    }
    cfg["sources"]["simple_moves"]["chain_mapper"] = {
        "mapper_id": "canonical-profile", "version": 1,
        "profile_id": "simple-moves-v1",
    }
    assert ledger_config.validate(copy.deepcopy(cfg))
    selected = ledger_config.selected_profile(cfg, "simple_moves")
    assert selected.source == "simple_moves"

    missing = copy.deepcopy(cfg)
    missing["sources"]["simple_moves"]["chain_mapper"].pop("profile_id")
    with pytest.raises(ledger_config.LedgerConfigError, match="profile_id"):
        ledger_config.validate(missing)

    unknown = copy.deepcopy(cfg)
    unknown["sources"]["simple_moves"]["chain_mapper"]["profile_id"] = "missing"
    with pytest.raises(ledger_config.LedgerConfigError, match="unknown Profile"):
        ledger_config.validate(unknown)

    mismatch = copy.deepcopy(cfg)
    mismatch["profiles"]["simple-moves-v1"]["source"] = "other_source"
    with pytest.raises(ledger_config.LedgerConfigError, match="not driver source"):
        ledger_config.validate(mismatch)


def test_legacy_atom_is_refused_by_general_mapper_and_allowed_only_by_import_api():
    def historical(_db, _payload, rule=None):
        return ledger_frame_from_atoms([atom(
            source_translator_ver=(mapper_provenance("historical-v1", rule)
                                   + "#pair_field"),
            source_event_id=uuid.uuid4(),
            source_event_state="legacy_atom",
        )])

    registry = LedgerMapperRegistry((
        describe_mapper("historical-import", 1, historical),
    )).seal()
    with pytest.raises(LedgerMapperError) as exc:
        run_registered_mapper(
            "historical-import", 1, {}, registry=registry)
    assert exc.value.code == "legacy_atom_forbidden"
    # The escape hatch this used to exercise -- `ledger.legacy_import` -- retired on
    # 2026-08-27 with `legacy_atom` itself: the rebuilt ledger holds 0 of them, so there was
    # nothing left for that door to open. The REFUSAL above is the half that still has a
    # subject, and it stays.


def test_mapper_layer_has_no_store_cursor_or_worker_capability():
    """The mapper layer may not reach the store, the cursor, or the worker.

    The ``mappers/ledger_lot_event_mapper.py`` half of this assertion went with that
    module on 2026-08-18, and ``ledger/legacy_import.py`` on 2026-08-27.  The ``ledger/``
    half below is the live boundary and is the reason this test is trimmed rather than
    deleted: nothing else asserts that these modules stay free of the writing layer.
    """
    phase3_modules = [
        Path(__file__).parents[1] / "ledger" / "ledger_frame.py",
        Path(__file__).parents[1] / "ledger" / "chain_mapper.py",
        Path(__file__).parents[1] / "ledger" / "profile_chain_mapper.py",
        Path(__file__).parents[1] / "ledger" / "profile_lookup_adapters.py",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in phase3_modules)
    assert "chain_ingestion_worker" not in joined
    assert "LedgerStore(" not in joined
    assert "write_batch(" not in joined
    assert "INSERT INTO" not in joined and "UPDATE " not in joined
