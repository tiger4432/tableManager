"""Pure registered Chain mapper for one driver-delimited ``lot_event`` event.

The function keeps the project's established mapper call shape
``(db, payload, rule=None)``. It reads no source, owns no cursor, receives no writable
DB capability, and returns only the standard pandas LedgerFrame. Group/boundary checks
operate on the supplied DataFrame; the old Molecule and LotEventTranslator are parity
references only, not this runtime path.
"""
from __future__ import annotations

from collections.abc import Mapping
import json

import pandas as pd

from ledger import gate, vocabulary
from ledger.chain_mapper import (
    LedgerMapperError,
    LedgerMapperRefused,
    mapper_provenance,
)
from ledger.config import DEFAULT_OCCURRED_AT_FORMAT
from ledger.envelope import Atom, canonical_keys, entity_ref
from ledger.ledger_frame import ledger_frame_from_atoms
from ledger.store import parse_occurred_at


REQUIRED_COLUMNS = (
    "lot", "event_type", "slots", "wafers", "parent_lot", "child_lot",
    "row_identity", "event_time",
)


def group_lot_event_frames(rows):
    """Group already-read logical rows into deterministic source-event DataFrames.

    This is source interpretation, not cursor ownership: the Ledger reader still
    selects and orders ``rows`` and decides which page/cursor is being processed.
    """
    grouped: dict[tuple, list[dict]] = {}
    order = []
    for raw in rows:
        row = {name: raw.get(name) for name in REQUIRED_COLUMNS}
        key = _event_key(row)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(row)
    return [pd.DataFrame(grouped[key], columns=REQUIRED_COLUMNS, dtype=object)
            for key in order]


def map_lot_event_to_ledger_frame(db, payload, rule=None):
    """Map one explicit event batch to LedgerFrame, with no side effects."""
    del db
    if not isinstance(payload, pd.DataFrame):
        raise LedgerMapperError(
            "invalid_mapper_input", "payload",
            "lot-event mapper requires a pandas DataFrame")
    if not isinstance(rule, Mapping):
        raise LedgerMapperError(
            "missing_mapper_rule", "rule", "lot-event mapper requires its source rule")
    missing = sorted(set(REQUIRED_COLUMNS) - set(payload.columns))
    if missing:
        raise LedgerMapperError(
            "invalid_mapper_input", "payload.columns",
            f"lot-event input is missing logical columns {missing}")
    if payload.empty:
        _refuse(gate.REFUSE_NO_IDENTITY, "lot-event source event has no rows")

    source = _required_text(rule.get("source"), "rule.source")
    source_cfg = rule.get("source_config")
    if not isinstance(source_cfg, Mapping):
        raise LedgerMapperError(
            "missing_mapper_rule", "rule.source_config",
            "validated lot-event source config is required")
    translator_version = _required_text(
        rule.get("translator_version"), "rule.translator_version")
    declared = rule.get("declared_derivations")
    if (not isinstance(declared, (set, frozenset, tuple, list))
            or any(not isinstance(item, str) or not item.strip() for item in declared)):
        raise LedgerMapperError(
            "missing_mapper_rule", "rule.declared_derivations",
            "declared derivations must be supplied by the Ledger source config")

    rows = [
        {name: _plain(payload.iloc[position][name]) for name in REQUIRED_COLUMNS}
        for position in range(len(payload))
    ]
    keys = {_event_key(row) for row in rows}
    if len(keys) != 1:
        raise LedgerMapperError(
            "invalid_source_event_boundary", "payload",
            f"driver supplied {len(keys)} lot events in one mapper call; expected 1")
    event_type, event_time, parent, child, ambiguous = next(iter(keys))
    event = {
        "event_type": event_type,
        "event_time": event_time,
        "parent": parent,
        "child": child,
        "ambiguous": ambiguous,
        "rows": rows,
    }
    event["ref"] = json.dumps(
        [event_type, event_time, parent, child, ambiguous],
        ensure_ascii=False, separators=(",", ":"), default=_json_value)
    report = {
        "molecule": event["ref"],
        "refused": False,
        "reason": None,
        "atoms": 0,
        "incomplete": bool(parent and child and len(rows) < 2),
        "blank_wafer_positions": 0,
    }

    if ambiguous:
        row = rows[0]
        _refuse(
            gate.REFUSE_AMBIGUOUS_PAIR,
            f"row {ambiguous!r} fills both "
            f"{source_cfg['columns']['parent_lot']}={row.get('parent_lot')!r} and "
            f"{source_cfg['columns']['child_lot']}={row.get('child_lot')!r}")
    event_rule = (source_cfg.get("vocabulary") or {}).get(event_type)
    if event_rule is None:
        _refuse(
            gate.REFUSE_UNDECLARED_VOCABULARY,
            f"event_type={event_type!r} is not declared for source {source!r}")
    occurred_at = parse_occurred_at(
        event_time,
        source_cfg.get("occurred_at_format", DEFAULT_OCCURRED_AT_FORMAT),
        source_cfg["occurred_at_timezone"],
    )
    if occurred_at is None:
        _refuse(
            gate.REFUSE_MISSING_OCCURRED_AT,
            f"{source_cfg['occurred_at_column']}={event_time!r} is not a declared "
            "source world time; arrival time is not substituted")

    execution_version = mapper_provenance(translator_version, rule)
    register_types = frozenset(source_cfg.get("register_entity_types") or ())
    try:
        registered = set(rule.get("registered_entities") or ())
    except TypeError as exc:
        raise LedgerMapperError(
            "invalid_mapper_context", "rule.registered_entities",
            "registered memo must contain hashable (type, canonical_keys) pairs") from exc

    atoms: list[Atom] = []
    lineage = event_rule.get("lineage", "none")
    pairing = event_rule.get("slot_pairing", "none")
    emit_register = event_rule.get("emit_register", True)
    lots = sorted({value for value in (
        {row["lot"] for row in rows} | {parent, child}) if value})
    if not lots:
        _refuse(gate.REFUSE_NO_IDENTITY, "event names no lot identity")

    def make_atom(predicate, subject_type, subject_keys, raw_rows, derivation,
                  object_kind=None, object_payload=None):
        return Atom(
            subject_type=subject_type,
            subject_keys=subject_keys,
            predicate=predicate,
            object_kind=object_kind,
            object_payload=object_payload,
            occurred_at=occurred_at,
            source_who=source,
            source_translator_ver=f"{execution_version}#{derivation}",
            source_raw_ref=_raw_ref(raw_rows, source),
            molecule_ref=event["ref"],
            derivation=derivation,
        )

    def register(entity_type, keys, raw_rows):
        if entity_type not in register_types or not vocabulary.requires_register(
                entity_type):
            return None
        memo = (entity_type, canonical_keys(keys))
        if memo in registered:
            return None
        registered.add(memo)
        return make_atom(
            "register", entity_type, keys, raw_rows, "first_sight")

    for lot in lots:
        candidate = register("Lot", {"lot": lot}, rows) if emit_register else None
        if candidate:
            atoms.append(candidate)

    if event_rule.get("emit_has_wafer", True):
        for row in rows:
            for slot, wafer in _positional_pairs(row, source_cfg):
                if not wafer:
                    report["blank_wafer_positions"] += 1
                    continue
                candidate = (register("Wafer", {"wafer": wafer}, [row])
                             if emit_register else None)
                if candidate:
                    atoms.append(candidate)
                atoms.append(make_atom(
                    "has_wafer", "Lot", {"lot": row["lot"]}, [row],
                    "positional_row", "entity_ref",
                    entity_ref("Wafer", {"wafer": wafer}, slot=slot)))

    if lineage == "parent_child" and parent and child:
        atoms.append(make_atom(
            "derived_from", "Lot", {"lot": child}, rows, "pair_field",
            "entity_ref", entity_ref("Lot", {"lot": parent})))

    if pairing != "none" and parent and child:
        parent_row = next((row for row in rows if row["lot"] == parent), None)
        child_row = next((row for row in rows if row["lot"] == child), None)
        if pairing == "slot_preserving" and child_row is not None:
            for slot, wafer in _positional_pairs(child_row, source_cfg):
                if not wafer or not slot:
                    continue
                atoms.append(make_atom(
                    "slot_map", "Lot", {"lot": parent}, [child_row],
                    "slot_preserving", "entity_ref",
                    entity_ref("Lot", {"lot": child},
                               **{"from": slot, "to": slot, "wafer": wafer})))
        elif (pairing == "shared_wafer" and parent_row is not None
              and child_row is not None):
            parent_at = {
                wafer: slot
                for slot, wafer in _positional_pairs(parent_row, source_cfg) if wafer
            }
            for slot, wafer in _positional_pairs(child_row, source_cfg):
                if not wafer or wafer not in parent_at:
                    continue
                atoms.append(make_atom(
                    "slot_map", "Lot", {"lot": parent},
                    [parent_row, child_row], "shared_wafer", "entity_ref",
                    entity_ref("Lot", {"lot": child},
                               **{"from": parent_at[wafer], "to": slot,
                                  "wafer": wafer})))

    unknown = sorted({atom.derivation for atom in atoms} - set(declared))
    if unknown:
        raise LedgerMapperError(
            "undeclared_mapper_derivation", "rule.declared_derivations",
            f"mapper emitted undeclared derivations {unknown}")
    report["atoms"] = len(atoms)
    frame = ledger_frame_from_atoms(atoms)
    frame.attrs["mapper_report"] = report
    return frame


def _event_key(row):
    lot = (row["lot"] or "").strip()
    parent = (row["parent_lot"] or "").strip()
    child = (row["child_lot"] or "").strip()
    if parent and child:
        return (row["event_type"], row["event_time"], parent, child,
                str(row["row_identity"]))
    if parent:
        return (row["event_type"], row["event_time"], parent, lot, None)
    if child:
        return (row["event_type"], row["event_time"], lot, child, None)
    return (row["event_type"], row["event_time"], None, lot, None)


def _positional_pairs(row, source_cfg):
    separator = source_cfg.get("list_separator", ":")
    slots = _split_list(row["slots"], separator)
    wafers = _split_list(row["wafers"], separator)
    if len(slots) != len(wafers):
        _refuse(
            gate.REFUSE_ATOMICITY,
            f"row {row['row_identity']!r}: "
            f"{source_cfg['columns']['slots']} has {len(slots)} entries but "
            f"{source_cfg['columns']['wafers']} has {len(wafers)}")
    return [(slot.strip(), wafer.strip()) for slot, wafer in zip(slots, wafers)]


def _split_list(value, separator):
    if value is None or str(value) == "":
        return []
    return str(value).split(separator)


def _raw_ref(rows, source):
    identities = sorted({str(row["row_identity"]) for row in rows})
    return source + ":" + json.dumps(
        identities, ensure_ascii=False, separators=(",", ":"))


def _json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _refuse(reason: str, message: str):
    raise LedgerMapperRefused(reason, "payload", message)


def _plain(value):
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return None
    return value


def _required_text(value, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerMapperError(
            "missing_mapper_rule", path, "must be a non-blank string")
    return value
