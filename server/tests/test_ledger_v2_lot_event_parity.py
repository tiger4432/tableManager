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
    # 🔴 NO `packs` SINCE 2026-08-21.  The `lot-lineage@1` pack written out here held six
    # Claims and 40-odd lines, and every one of them restated its predicate: two
    # `register_lot`/`register_wafer` bodies that were character-for-character identical,
    # and `split_slot`/`merge_slot`, which were identical AND emitted the same predicate.
    # `predicate_claim` derives all six from four predicates, so what used to make two
    # sentences distinguishable -- a Claim id apiece -- is now their MAPPING KEY alone.
    # That is not a loss here: this fixture already existed to prove that two sentences of
    # identical structure are told apart by name and nothing else.

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
    # 🔴 KEYED BY THE SENTENCE THE MAPPER SAYS, as of 2026-08-21.  Every key here is a
    # `SentenceShape` attribute of `LotEventRoleMapper`, lowercased -- that is the whole
    # of how a mapping is selected now, and it is why `mapping_id` is gone rather than
    # renamed: the key already was the identity, one copy later.
    mappings = {
        "first_sight_holder": {
            "predicate": "register@1", "bind": bind(lot)},
        "first_sight_item": {
            "predicate": "register@1", "bind": bind(wafer)},
        "in_slot": {
            "predicate": "has_wafer@1",
            "bind": bind(lot, wafer, (("slot", "slots"),))},
        "descent": {"predicate": "derived_from@1", "bind": bind(child, parent)},
        # These two utter the SAME predicate and differ only in the rule that computed
        # them.  Nothing about their structure tells them apart, which is exactly why
        # structure stopped being how a sentence is chosen.  (Until 2026-08-21 they named
        # two separate Claims, `split_slot` and `merge_slot`, whose bodies were identical
        # down to the predicate -- so the distinctness was already only in the name.)
        "split_slot_carry": {
            "predicate": "slot_map@1",
            "bind": bind(parent, child, (("from", "slots"), ("to", "slots"),
                                         ("wafer", "wafers")))},
        "merge_slot_join": {
            "predicate": "slot_map@1",
            "bind": bind(parent, child, (("from", "slots"), ("to", "slots"),
                                         ("wafer", "wafers")))},
    }
    return {
        "setup_version": SETUP_VERSION,
        "virtual_joins": {},
        "vocabulary": {
            "register@1": {
                "status": "active",
                "subjects": ["Lot@1", "Wafer@1"],
                "object": {"kind": "none",
                           "qualifiers": {"required": [], "optional": []}},
            },
            "has_wafer@1": {
                "status": "active",
                "subjects": ["Lot@1"],
                "object": {"kind": "entity_ref", "types": ["Wafer@1"],
                           "qualifiers": {"required": ["slot"], "optional": []}},
            },
            "derived_from@1": {
                "status": "active",
                "subjects": ["Lot@1"],
                "object": {"kind": "entity_ref", "types": ["Lot@1"],
                           "qualifiers": {"required": [], "optional": []}},
            },
            "slot_map@1": {
                "status": "active",
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
    # 🔴 THE SIX MAPPING IDS LEFT THIS TABLE ON 2026-08-21, and their absence is the
    # point rather than an omission.  A mapping is FILED under the sentence its mapper
    # says, so there is no longer a config-owned name to rename: renaming a key here would
    # be renaming `LotEventRoleMapper.IN_SLOT`, which is a code change and not a
    # deployment's spelling.
    # 🔴 THE FOUR CLAIM IDS (`register_lot`, `register_wafer`, `membership`, `lineage`)
    # LEFT IT LATER THE SAME DAY, when the `packs` section went.  Same reason once more:
    # a Claim is derived from its predicate and has no id of its own to respell, and the
    # predicate that IS its id is renamed one line above.  What a foreign deployment still
    # owns -- entity types, predicates, role ids, columns -- is all still renamed below.
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

    Everything the declaration OWNS is renamed -- both entity types, all four
    predicates -- and the mapper is asked for the same split.  It must
    emit the same sentences.

    This is the test the old mapper could not pass: it carried `"Lot"`, `"Wafer"`,
    `"has_wafer"`, `"positional_row"` and friends as literals, and against this bundle it
    refused every case with `invalid_lot_event_contract` instead of emitting anything.

    🔴 WHAT IS NOT RENAMED IS THE SENTENCE KEY, and that is a narrowing worth stating.
    Until 2026-08-21 a mapping also had a config-owned `mapping_id` and this test renamed
    all six.  The map is keyed by the sentence now, and a sentence is the MAPPER's word:
    the naming still runs config -> mapper, so what used to be "a rename cannot reach the
    mapper" is now "there is nothing left on the config side to rename".
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


# RETIRED: test_two_shape_identical_mappings_with_no_sentence_are_refused_at_compile_time.
# It deleted `sentence` from one of the two indistinguishable mappings and asserted an
# `ambiguous_sentence` refusal at that mapping's path. Both the field and the refusal are
# gone as of 2026-08-21, and NOT because the rule was relaxed: `mappings` is a map keyed by
# the sentence, so "two mappings realizing one sentence" cannot be written down, and "a
# mapping that names no sentence" cannot either -- a member of a map has a key. The state
# it refused stopped being expressible, which is the same shape as the retirement of
# `mapping_id`'s duplicate check. What made it removable is asserted instead.
def test_the_indistinguishable_pair_is_told_apart_by_its_key_and_nothing_else():
    bundle = lot_event_bundle()
    mappings = bundle["sources"]["lot_event"]["bind"]["mappings"]
    pair = {key: mapping for key, mapping in mappings.items()
            if mapping["predicate"] == "slot_map@1"}
    assert set(pair) == {"split_slot_carry", "merge_slot_join"}
    # Same roles, same qualifier names, same entity types on both ends: nothing but the
    # key separates them, and both keys are `SentenceShape` attributes of the mapper.
    carry, join = pair["split_slot_carry"], pair["merge_slot_join"]
    assert carry["bind"] == join["bind"]
    assert {LotEventRoleMapper.SPLIT_SLOT_CARRY.sentence,
            LotEventRoleMapper.MERGE_SLOT_JOIN.sentence} == set(pair)
    validate_bundle(lot_event_bundle(), catalog=LOT_EVENT_CATALOG)