"""Registered read-only lookup capabilities for canonical Profile execution."""
from __future__ import annotations

from collections.abc import Mapping
import json
from types import MappingProxyType

from .chain_mapper import LedgerMapperError
from .profile_chain_mapper import DeclaredLookupAdapter


LOOKUP_CHUNK_SIZE = 1000
DESTINATION_LOOKUP_ID = "destination_inventory"


def destination_inventory_adapter(engine) -> DeclaredLookupAdapter:
    """Resolve business keys to the ``container`` JSON in bounded read-only batches.

    Deployment contract: ``destination_inventory`` has the standard dynamic-table
    ``row_id``/``business_key_val`` columns and a ``container`` JSON/JSON-text column.
    Two rows are deliberately retained so the Profile evaluator can reject ambiguity.
    """
    if engine is None or not callable(getattr(engine, "raw_connection", None)):
        raise TypeError("destination_inventory adapter requires a SQLAlchemy engine")

    def resolve_many(_values, keys):
        canonical_by_key: dict[str, str] = {}
        for index, key in enumerate(keys):
            if not isinstance(key, str) or not key.strip():
                raise LedgerMapperError(
                    "lookup_key_invalid", f"destination_inventory.keys[{index}]",
                    "destination_inventory keys must be non-blank strings")
            database_key = key.strip()
            canonical = _canonical_key(key)
            previous = canonical_by_key.setdefault(database_key, canonical)
            if previous != canonical:
                raise LedgerMapperError(
                    "lookup_key_invalid", f"destination_inventory.keys[{index}]",
                    "distinct Profile keys collapse to one database key")

        resolved = {canonical: [] for canonical in canonical_by_key.values()}
        ordered = sorted(canonical_by_key)
        for start in range(0, len(ordered), LOOKUP_CHUNK_SIZE):
            chunk = ordered[start:start + LOOKUP_CHUNK_SIZE]
            connection = engine.raw_connection()
            try:
                with connection.cursor() as cursor:
                    # This is a separate connection so a lookup cannot inherit a writable
                    # transaction from the LedgerStore path.  It is rolled back below even
                    # after success, which also releases every read lock before store DDL.
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(
                        "SELECT business_key_val, container FROM ("
                        "SELECT business_key_val, container, "
                        "row_number() OVER (PARTITION BY business_key_val ORDER BY row_id) "
                        "AS match_number FROM destination_inventory "
                        "WHERE business_key_val = ANY(%s)"
                        ") AS matched WHERE match_number <= 2 "
                        "ORDER BY business_key_val, match_number",
                        (chunk,),
                    )
                    for business_key, container in cursor.fetchall():
                        canonical = canonical_by_key.get(str(business_key))
                        if canonical is None:
                            continue
                        resolved[canonical].append({
                            "container": _container_value(container),
                        })
            finally:
                connection.rollback()
                connection.close()
        return resolved

    return DeclaredLookupAdapter(
        lookup_id=DESTINATION_LOOKUP_ID,
        selects=("container",),
        resolve_many=resolve_many,
    )


def default_profile_lookup_adapters(engine) -> Mapping[str, DeclaredLookupAdapter]:
    """The process's explicit Profile lookup registry, keyed by declared lookup ID."""
    adapter = destination_inventory_adapter(engine)
    return MappingProxyType({adapter.lookup_id: adapter})


def _canonical_key(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False)


def _container_value(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise LedgerMapperError(
                "lookup_result_invalid", "destination_inventory.container",
                "container text must be valid JSON") from exc
    if not isinstance(value, Mapping):
        raise LedgerMapperError(
            "lookup_result_invalid", "destination_inventory.container",
            "container must be a JSON object")
    return dict(value)
