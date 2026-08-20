"""The only tests of ``mappers/ledger_v2_lot_event_role_mapper.py``.

Named for parity because it began as a legacy-vs-v2 comparison. That arm was removed on
2026-08-18 with ``ledger/lot_event_translator.py``: there is nothing left to compare
against, so the comparison could only have been made green by weakening it.

What survives is not leftovers. Each of the four cases below is the sole cover for its
contract -- the registration snapshot requirement, positional-list failure ordering, the
mapper-layer import boundary, and incomplete-molecule accounting -- and every other test
in the suite passes ``known_registrations=()`` or asserts ``incomplete_count == 0``, so
none of them takes these branches.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
import inspect
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from ledger import gate
from ledger.envelope import canonical_keys
from ledger.roleframe import RoleMapperImplementationRegistry
from ledger.runtime_v2 import (
    LedgerV2RuntimeError,
    execute_cursor_batch,
    preview_cursor_batch,
)
from ledger.setup_bundle import (
    SETUP_VERSION,
    LedgerSetupValidationError,
    validate_bundle,
)
from ledger.setup_registry import TrustedImplementationCatalog, compile_setup_snapshot
from ledger.source_preparation import (
    SOURCE_EVENT_INCOMPLETE_COLUMN,
    BaseSourcePreparer,
    SourcePreparationError,
    SourcePreparerImplementationRegistry,
    VerifiedJoinBatchReader,
)
from mappers.ledger_v2_lot_event_role_mapper import (
    EVENT_GROUP_COLUMN,
    LOT_EVENT_COLUMNS,
    LotEventRoleMapper,
    # The module private on purpose: the event-grouping rule is what the production
    # preparer and the double below must share, and reaching for it here is the signal
    # that this file -- not `server/mappers/` -- is where the double belongs.
    _event_outputs,
)


class LotEventSourcePreparer(BaseSourcePreparer):
    """Group split/merge rows that already carry the LOGICAL column names.

    Test-only, and it lives here for that reason.  It sat in
    ``mappers/ledger_v2_lot_event_role_mapper.py`` next to the production
    ``LiveLotEventSourcePreparer``, nearly identical in shape and never registered, so
    nothing in that file said which of the two actually runs.  It declares no
    ``implementation_id``, so ``ledger.implementations`` never made it addressable from
    config -- these tests register it by hand, which is the only way it has ever run.
    """

    def prepare_outputs(self, context, base_frame, joins):
        if joins:
            raise SourcePreparationError(
                "unsupported_source_preparation",
                "source_preparation.join_rules",
                "lot_event preparation does not accept virtual joins",
            )
        declared = set(
            context.source_plan.driver.preparation.preparer.output_columns)
        if declared != {EVENT_GROUP_COLUMN, SOURCE_EVENT_INCOMPLETE_COLUMN}:
            raise SourcePreparationError(
                "unsupported_source_preparer_output",
                "source_preparation.outputs",
                "lot_event preparer requires event group and incomplete outputs",
            )
        missing = sorted(set(LOT_EVENT_COLUMNS) - set(base_frame.columns))
        if missing:
            raise SourcePreparationError(
                "source_preparation_incomplete",
                "source_batch.columns",
                f"lot_event source columns are missing: {missing}",
            )
        return _event_outputs(base_frame)


NOW = datetime(2026, 8, 17, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))


def approved_column(column):
    return {
        "kind": "column", "column": column,
        "binding_origin": "user_declared", "approval_status": "approved",
    }


def approved_entity(entity_type, key, column):
    return {
        "kind": "entity", "entity_type": entity_type,
        "keys": {key: approved_column(column)},
        "binding_origin": "user_declared", "approval_status": "approved",
    }


#: The PHYSICAL half of the lot_event deployment -- `table_config.json`'s job.  Written
#: out apart from `lot_event_bundle()` and never derived from it: the ledger's own
#: `tables` section was retired because a physical claim checked against nothing drifts in
#: silence, and a catalog built from the bundle under test would agree by construction.
LOT_EVENT_CATALOG = {
    "lot_event": {
        "columns": {
            "lot": "string", "event_type": "string", "slots": "string",
            "wafers": "string", "parent_lot": "string", "child_lot": "string",
            "row_identity": "string", "event_time": "datetime",
        },
        "business_key": "row_identity",
    },
}


def lot_event_bundle():
    entity_role = {"kind": "entity", "required": True}
    time_role = {"kind": "time", "required": True}
    attribute_role = {"kind": "attribute", "required": True}

    def entity_claim(predicate, qualifiers=()):
        roles = {
            "subject": entity_role, "target": entity_role,
            "occurred_at": time_role,
        }
        roles.update({name: attribute_role for name in qualifiers})
        return {
            "roles": roles,
            "emit": {
                "predicate": predicate, "subject": "$subject",
                "object": {
                    "kind": "entity_ref", "entity": "$target",
                    "qualifiers": {name: f"${name}" for name in qualifiers},
                },
                "occurred_at": "$occurred_at",
            },
        }

    packs = {
        "lot-lineage@1": {"claims": {
            "register_lot": {
                "roles": {"subject": entity_role, "occurred_at": time_role},
                "emit": {
                    "predicate": "register@1", "subject": "$subject",
                    "object": {"kind": "none"},
                    "occurred_at": "$occurred_at",
                },
            },
            "register_wafer": {
                "roles": {"subject": entity_role, "occurred_at": time_role},
                "emit": {
                    "predicate": "register@1", "subject": "$subject",
                    "object": {"kind": "none"},
                    "occurred_at": "$occurred_at",
                },
            },
            "membership": entity_claim("has_wafer@1", ("slot",)),
            "lineage": entity_claim("derived_from@1"),
            "split_slot": entity_claim(
                "slot_map@1", ("from", "to", "wafer")),
            "merge_slot": entity_claim(
                "slot_map@1", ("from", "to", "wafer")),
        }},
    }

    def bind(subject, target=None, qualifiers=()):
        values = {
            "subject": subject,
            "occurred_at": approved_column("event_time"),
        }
        if target is not None:
            values["target"] = target
        for name, column in qualifiers:
            values[name] = approved_column(column)
        return values

    lot = approved_entity("Lot@1", "lot", "lot")
    wafer = approved_entity("Wafer@1", "wafer", "wafers")
    # Custom mapper computes parent/child from the complete event.  Profile Entity
    # bindings retain the approved Entity type/key contract; the Python mapper owns the
    # event-level value rather than pretending each half-row has both pair columns.
    child = approved_entity("Lot@1", "lot", "lot")
    parent = approved_entity("Lot@1", "lot", "lot")
    mappings = [
        {"mapping_id": "first_sight_lot",
         "use": "lot-lineage@1/register_lot", "bind": bind(lot)},
        {"mapping_id": "first_sight_wafer",
         "use": "lot-lineage@1/register_wafer", "bind": bind(wafer)},
        {"mapping_id": "positional_row",
         "use": "lot-lineage@1/membership",
         "bind": bind(lot, wafer, (("slot", "slots"),))},
        {"mapping_id": "pair_field", "use": "lot-lineage@1/lineage",
         "bind": bind(child, parent)},
        # The only shape class with two members: both say the same sentence and differ
        # only in the rule that computed it, so each declares which mapper sentence it
        # realizes.  Drop either `sentence` and the bundle is refused (`ambiguous_sentence`)
        # -- see the compile-time test below.
        {"mapping_id": "slot_preserving", "sentence": "split_slot_carry",
         "use": "lot-lineage@1/split_slot",
         "bind": bind(parent, child, (("from", "slots"), ("to", "slots"),
                                      ("wafer", "wafers")))},
        {"mapping_id": "shared_wafer", "sentence": "merge_slot_join",
         "use": "lot-lineage@1/merge_slot",
         "bind": bind(parent, child, (("from", "slots"), ("to", "slots"),
                                      ("wafer", "wafers")))},
    ]
    return {
        "setup_version": SETUP_VERSION,
        "virtual_joins": {},
        "vocabulary": {
            "register@1": {
                "status": "active", "layer": "ontology",
                "subjects": ["Lot@1", "Wafer@1"],
                "object": {"kind": "none",
                           "qualifiers": {"required": [], "optional": []}},
            },
            "has_wafer@1": {
                "status": "active", "layer": "ontology",
                "subjects": ["Lot@1"],
                "object": {"kind": "entity_ref", "types": ["Wafer@1"],
                           "qualifiers": {"required": ["slot"], "optional": []}},
            },
            "derived_from@1": {
                "status": "active", "layer": "ontology",
                "subjects": ["Lot@1"],
                "object": {"kind": "entity_ref", "types": ["Lot@1"],
                           "qualifiers": {"required": [], "optional": []}},
            },
            "slot_map@1": {
                "status": "active", "layer": "ontology",
                "subjects": ["Lot@1"],
                "object": {"kind": "entity_ref", "types": ["Lot@1"],
                           "qualifiers": {
                               "required": ["from", "to", "wafer"],
                               "optional": [],
                           }},
            },
        },
        "entities": {
            "Lot@1": {"keys": ["lot"]},
            "Wafer@1": {"keys": ["wafer"]},
        },
        "packs": packs,
        "sources": {
            "lot_event": {
                "relation": "lot_event",
                "read": {
                    "unit": "group",
                    "identity": [EVENT_GROUP_COLUMN],
                    "group_by": [EVENT_GROUP_COLUMN],
                    "order_by": ["row_identity"],
                    "occurred_at": {
                        "column": "event_time", "timezone": "Asia/Seoul"},
                    "cursor": {"columns": ["event_time", "row_identity"]},
                },
                "prepare": {
                    "implementation_id": "lot-event-frame",
                    "implementation_version": 1,
                    "input_columns": list(LOT_EVENT_COLUMNS),
                    "output_columns": {
                        EVENT_GROUP_COLUMN: "string",
                        SOURCE_EVENT_INCOMPLETE_COLUMN: "boolean",
                    },
                    "accepts_verified_join_rules": False,
                    "inherit_virtual_join_rules": [],
                },
                "map": {
                    "implementation_id": "lot-event-role",
                    "implementation_version": 1,
                    "unit": {"kind": "event"},
                    "input_columns": [*LOT_EVENT_COLUMNS, EVENT_GROUP_COLUMN,
                                      SOURCE_EVENT_INCOMPLETE_COLUMN],
                },
                "bind": {
                    "mappings": mappings,
                },
            },
        },
    }


def compiled_lot_event():
    trusted = TrustedImplementationCatalog.build(
        source_preparers=[("lot-event-frame", 1)],
        mappers=[("lot-event-role", 1)],
    )
    return compile_setup_snapshot(
        validate_bundle(lot_event_bundle(), catalog=LOT_EVENT_CATALOG), trusted,
        catalog=LOT_EVENT_CATALOG)


class NoJoinReader(VerifiedJoinBatchReader):
    def read_chunk(self, descriptor, keys):
        raise AssertionError("lot_event has no virtual join")


def preparers():
    registry = SourcePreparerImplementationRegistry()
    registry.register("lot-event-frame", 1, LotEventSourcePreparer)
    return registry.seal()


def mappers():
    registry = RoleMapperImplementationRegistry()
    registry.register("lot-event-role", 1, LotEventRoleMapper)
    return registry.seal()


def split_rows():
    return pd.DataFrame([
        {"lot": "P", "event_type": "split", "slots": "1:2",
         "wafers": "W1:W2", "parent_lot": "", "child_lot": "C",
         "row_identity": "R1", "event_time": NOW},
        {"lot": "C", "event_type": "split", "slots": "3",
         "wafers": "W3", "parent_lot": "P", "child_lot": "",
         "row_identity": "R2", "event_time": NOW},
    ], dtype=object)


def track_rows(at=NOW + timedelta(minutes=2), prefix="T"):
    return pd.DataFrame([
        {"lot": "T", "event_type": "track_in", "slots": "7:8",
         "wafers": "W7:W8", "parent_lot": "", "child_lot": "",
         "row_identity": prefix, "event_time": at},
    ], dtype=object)


def preview(frame, *, known=(), snapshot=None):
    row = frame.iloc[-1]
    return preview_cursor_batch(
        snapshot or compiled_lot_event(), "lot_event", frame,
        {"event_time": row["event_time"], "row_identity": row["row_identity"]},
        NoJoinReader(), preparers(), mappers(), known_registrations=known)


#: Every declaration spelling the mapper used to carry as a Python literal, respelled.
#: Entity IDENTITY KEYS (`lot`, `wafer`) and qualifier names (`slot`, `from`, `to`,
#: `wafer`) are deliberately NOT renamed: those are business vocabulary that the mapper is
#: allowed to know, and renaming them here would make the test pass for the wrong reason.
FOREIGN_SPELLINGS = {
    "Lot@1": "Batch@1", "Wafer@1": "Slice@1",
    "has_wafer@1": "carries_slice@1", "derived_from@1": "descends_from@1",
    "slot_map@1": "slot_trace@1", "register@1": "first_seen@1",
    "register_lot": "mid_a", "register_wafer": "mid_b",
    "membership": "carriage", "lineage": "descent",
    "first_sight_lot": "m_one", "first_sight_wafer": "m_two",
    "positional_row": "m_three", "pair_field": "m_four",
    # Nothing is exempt any more: the last two mapping ids are renamed here too, because
    # the mapper now names the SENTENCE and the config says which mapping realizes it.
    "slot_preserving": "m_five", "shared_wafer": "m_six",
}
UNSPELL = {new.split("@")[0]: old.split("@")[0]
           for old, new in FOREIGN_SPELLINGS.items()}


def respell(value):
    if isinstance(value, dict):
        return {FOREIGN_SPELLINGS.get(k, k): respell(v) for k, v in value.items()}
    if isinstance(value, list):
        return [respell(item) for item in value]
    if isinstance(value, str):
        for old, new in FOREIGN_SPELLINGS.items():
            if value == old or value.endswith(f"/{old}"):
                return value[:len(value) - len(old)] + new
        return value
    return value


def test_a_foreign_deployments_spellings_change_nothing_the_mapper_emits():
    """The owner's definition of done, executed: a different-schema environment needs
    ZERO lines of Python.

    Everything the declaration names is renamed -- both entity types, all four
    predicates, four of the six mappings, and the claim ids -- and the mapper is asked
    for the same split.  It must emit the same sentences.

    This is the test the old mapper could not pass: it carried `"Lot"`, `"Wafer"`,
    `"has_wafer"`, `"positional_row"` and friends as literals, and against this bundle it
    refused every case with `invalid_lot_event_contract` instead of emitting anything.

    NOTHING is exempt: all six mapping ids are renamed too.  The mapper names the
    SENTENCE in its own vocabulary and each mapping declares which sentence it realizes,
    so the naming runs config -> mapper and a rename cannot reach the mapper at all.
    """
    foreign = compile_setup_snapshot(
        validate_bundle(respell(lot_event_bundle()), catalog=LOT_EVENT_CATALOG),
        TrustedImplementationCatalog.build(
            source_preparers=[("lot-event-frame", 1)],
            mappers=[("lot-event-role", 1)]),
        catalog=LOT_EVENT_CATALOG)

    def sentences(result):
        return sorted(
            (UNSPELL.get(item["subject_type"], item["subject_type"]),
             canonical_keys(item["subject_keys"]),
             UNSPELL.get(item["predicate"], item["predicate"]),
             canonical_keys(respell_back(item["object_payload"])))
            for item in result.candidate_semantics)

    def respell_back(payload):
        if not isinstance(payload, dict):
            return {} if payload is None else {"value": payload}
        out = dict(payload)
        if "type" in out:
            out["type"] = UNSPELL.get(out["type"], out["type"])
        return out

    native = sentences(preview(split_rows(), known=()))
    assert native, "the native bundle must emit something to compare against"
    assert sentences(preview(split_rows(), known=(), snapshot=foreign)) == native


def test_registration_snapshot_is_required_and_dedupes_across_events():
    frame = pd.concat([
        track_rows(prefix="T1"),
        track_rows(at=NOW + timedelta(minutes=3), prefix="T2"),
    ], ignore_index=True)

    with pytest.raises(LedgerV2RuntimeError) as exc:
        preview_cursor_batch(
            compiled_lot_event(), "lot_event", frame,
            {"event_time": frame.iloc[-1]["event_time"],
             "row_identity": frame.iloc[-1]["row_identity"]},
            NoJoinReader(), preparers(), mappers())
    assert exc.value.code == "registration_context_required"

    result = preview(frame, known=())
    registers = [item for item in result.candidate_semantics
                 if item["predicate"] == "register"]
    assert {(item["subject_type"], canonical_keys(item["subject_keys"]))
            for item in registers} == {
        ("Lot", canonical_keys({"lot": "T"})),
        ("Wafer", canonical_keys({"wafer": "W7"})),
        ("Wafer", canonical_keys({"wafer": "W8"})),
    }

    known = {(item["subject_type"], canonical_keys(item["subject_keys"]))
             for item in registers}
    replay = preview(frame, known=known)
    assert all(item["predicate"] != "register"
               for item in replay.candidate_semantics)


def test_invalid_positional_lists_fail_before_any_candidate_is_returned():
    frame = track_rows()
    frame.at[0, "wafers"] = "W7"

    with pytest.raises(Exception) as exc:
        preview(frame, known=())
    assert getattr(exc.value, "code", None) == "invalid_positional_list"


def test_lot_event_free_hooks_have_no_atom_payload_db_cursor_or_store_capability():
    import mappers.ledger_v2_lot_event_role_mapper as module

    tree = ast.parse(inspect.getsource(module))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    assert not imported & {
        "database", "ledger.envelope", "ledger.gate", "ledger.ledger_frame",
        "ledger.store",
    }
    assert "map" not in LotEventRoleMapper.__dict__
    assert "prepare_batch" not in LotEventSourcePreparer.__dict__


def test_incomplete_pair_lands_visible_claims_and_updates_existing_cursor_metric():
    frame = split_rows().iloc[[0]].reset_index(drop=True)
    calls = []

    class Store:
        def write_batch(self, source, translator_ver, atoms, cursor_value, molecules,
                        refused=0, incomplete=0, *, reasons,
                        enforce_translator_version=False):
            calls.append({"atoms": tuple(atoms), "molecules": molecules,
                          "refused": refused, "incomplete": incomplete})
            return {"attempted": len(atoms), "inserted": len(atoms),
                    "deduped": 0, "molecules": molecules}

    gate.reset_counters()
    result = execute_cursor_batch(
        compiled_lot_event(), "lot_event", frame,
        {"event_time": frame.iloc[0]["event_time"],
         "row_identity": frame.iloc[0]["row_identity"]},
        NoJoinReader(), preparers(), mappers(), Store(), known_registrations=())

    assert result.preview.incomplete_count == 1
    assert result.preview.atom_count > 0
    assert len(calls) == 1
    assert len(calls[0]["atoms"]) == result.preview.atom_count
    assert calls[0]["molecules"] == 1
    assert calls[0]["refused"] == 0
    assert calls[0]["incomplete"] == 1
    assert gate.incomplete_molecules()["lot_event"] == 1
    gate.reset_counters()


def test_two_shape_identical_mappings_with_no_sentence_are_refused_at_compile_time():
    """The tie is a NAMED config error, never a run-time coin flip.

    `slot_preserving` and `shared_wafer` are indistinguishable to a mapper: same object
    kind, same three qualifiers, same subject Entity type.  Whichever one a resolver
    "found first" would be an election from an unordered set -- correct today, and wrong
    the day a third mapping joins the class, at which point everything that already worked
    starts emitting a different `derivation` with nothing naming the cause.

    So dropping `sentence` must fail validation, at the path of the mapping that is
    missing it, before anything runs.
    """
    bundle = lot_event_bundle()
    mappings = bundle["sources"]["lot_event"]["bind"]["mappings"]
    ambiguous = [index for index, mapping in enumerate(mappings)
                 if mapping.get("sentence")]
    assert len(ambiguous) == 2, "the fixture must still contain the ambiguous pair"

    for index in ambiguous:
        broken = lot_event_bundle()
        del broken["sources"]["lot_event"]["bind"]["mappings"][index]["sentence"]
        with pytest.raises(LedgerSetupValidationError) as exc:
            validate_bundle(broken, catalog=LOT_EVENT_CATALOG)
        assert exc.value.code == "ambiguous_sentence", exc.value.code
        assert exc.value.path == (
            f"bundle.sources.lot_event.bind.mappings[{index}].sentence"), exc.value.path
        # the message must name the peers, or a reader cannot find the other half
        assert "slot_preserving" in exc.value.message
        assert "shared_wafer" in exc.value.message

    # ...and a mapping whose shape is already unique must NOT be forced to restate itself.
    unique = next(index for index, mapping in enumerate(mappings)
                  if not mapping.get("sentence"))
    assert "sentence" not in mappings[unique]
    validate_bundle(lot_event_bundle(), catalog=LOT_EVENT_CATALOG)
