"""THE WALK'S SHAPE GATE (owner 11-11 «노드, 엣지 속성, 키 모든 타입 그리고 걷기 끝»): every seat a declaration can
put a column in, times every column type, is walkable - the node or edge appears, its value is spelled, a blank (and a
NaN) is not said, nothing is left out. ONE product of `SEATS` x `TYPES` builds the table, its rows and the declaration;
the PG file walks it, the SQLite file compiles it. A cell is never listed by hand - only the cells that cannot exist
(`CANNOT_EXIST`), by name.

The table `shape_gate`: `sid` names the subject (S1 · S2 · S3), `at` the time of every sentence but the event-time
seat's, `j` a second key part, and one column a type, `c_<type>`. Row S1 holds each type's value, S2 a blank in every
typed column, S3 a NaN in a column whose type holds one (a blank in the rest)."""
from datetime import date, datetime, timezone
from decimal import Decimal

ZONE = "Asia/Seoul"
TABLE = "shape_gate"
ROWS = ("S1", "S2", "S3")
AT = "2026-09-30T00:00:00+00:00"

#: type -> (PostgreSQL type, table_config type, the value S1 holds, what a binding reading it as a time adds, holds NaN)
TYPES = {
    "text": ("text", "string", "A1", {}, False),
    "integer": ("integer", "number", 7, {}, False),
    "bigint": ("bigint", "number", 9000000000, {}, False),
    "double": ("double precision", "number", 9.5, {}, True),
    "numeric": ("numeric", "number", Decimal("1.25"), {}, True),
    "boolean": ("boolean", "string", True, {}, False),
    "timestamptz": ("timestamptz", "datetime", datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc), {}, False),
    "timestamp_zone": ("timestamp", "datetime", datetime(2026, 9, 30, 10, 0), {"timezone": ZONE}, False),
    "date": ("date", "string", date(2026, 9, 30), {}, False),
    "text_format": ("text", "string", "20260930_100000", {"timezone": ZONE, "format": "%Y%m%d_%H%M%S"}, False),
}
TIMES = ("timestamptz", "timestamp_zone", "date", "text_format")
SEATS = ("key_one", "key_several", "key_constant", "attribute", "qualifier_optional", "qualifier_required", "value",
         "event_time")
#: a constant is a JSON value: it has no column, so no column type - the four JSON kinds stand for it
CANNOT_EXIST = {("key_constant", kind): "a constant has no column type"
                for kind in ("bigint", "numeric", "timestamptz", "timestamp_zone", "date", "text_format")}
CELLS = tuple((seat, kind) for seat in SEATS for kind in TYPES if (seat, kind) not in CANNOT_EXIST)
#: the cells the gate holds today - a landing switches cells on here, nothing else
ENABLED = frozenset({("attribute", "numeric"), ("qualifier_optional", "numeric"), ("qualifier_required", "numeric")})
PENDING_OWNER = "pending owner: the walk draws no value object (retired 2026-08-28) - the owner's ruling (lead 11-11)"


def not_yet(seat, kind):
    """Why a cell is collected but not held yet - None for an enabled one."""
    if (seat, kind) in ENABLED:
        return None
    if seat == "value":
        return PENDING_OWNER
    if seat == "event_time":
        return ("next landing: read as 00:00 in the declared zone" if kind == "date" else
                "next landing: holds the save-time refusal" if kind not in ("timestamptz", "timestamp_zone") else
                "next landing: switched on with the table")
    if seat in ("attribute", "qualifier_optional", "qualifier_required") and kind in TIMES:
        return "next landing: a time attribute or qualifier read and spelled as the walk spells a time (group 2)"
    if seat in ("attribute", "qualifier_optional", "qualifier_required") and kind == "boolean":
        return "next landing: a boolean attribute or qualifier read (group 3)"
    if seat in ("key_one", "key_several") and kind in ("boolean", "date"):
        return "next landing: a key from a boolean or date column read in the key spelling (group 5)"
    return "next landing: switched on with the table"
VALUE_TYPES = {"text": "string", "boolean": "boolean", **{kind: "timestamp" for kind in TIMES}}


def column(kind):
    return f"c_{kind}"


def name(seat, kind):
    return f"{seat}_{kind}"


def cell_of_row(kind, row):
    """The cell `row` holds in `column(kind)`: the value, a blank (None) or a NaN."""
    if row == "S1":
        return TYPES[kind][2]
    if row == "S3" and TYPES[kind][4]:
        return float("nan") if kind == "double" else Decimal("NaN")
    return None


def catalogue():
    """`shape_gate`'s table_config entry."""
    types = {"sid": "string", "at": "datetime", "j": "string", **{column(k): spec[1] for k, spec in TYPES.items()}}
    return {"column_types": types}


def ddl(schema):
    columns = ", ".join(f'"{column(kind)}" {spec[0]}' for kind, spec in TYPES.items())
    return (f'CREATE TABLE "{schema}"."{TABLE}" (row_id text PRIMARY KEY, sid text, "at" timestamptz, j text, '
            f"{columns})")


def rows():
    """[{column: cell}] of the three rows."""
    out = []
    for index, row in enumerate(ROWS, 1):
        out.append({"row_id": f"r{index}", "sid": row, "at": AT, "j": "J",
                    **{column(kind): cell_of_row(kind, row) for kind in TYPES}})
    return out


def _entity(entity_type, keys):
    return {"kind": "entity", "entity_type": entity_type, "keys": keys}


def _read(kind=None):
    """A source's `read`: its time from `at`, or from the cell's own column (the event-time seat)."""
    occurred = {"column": "at", "timezone": ZONE} if kind is None else {
        "column": column(kind), "timezone": ZONE, **({"format": TYPES[kind][3]["format"]}
                                                     if "format" in TYPES[kind][3] else {})}
    return {"unit": "row", "identity": ["row_id"], "order_by": ["row_id"], "cursor": {"columns": ["row_id"]},
            "occurred_at": occurred}


def document():
    """The ledger declaration: one source, one predicate a cell."""
    entities = {"subj@1": {"keys": ["sid"]}, "obj@1": {"keys": ["o"]}}
    vocabulary = {"register@1": {"status": "active", "subjects": [],
                                 "object": {"kind": "none", "qualifiers": {"required": [], "optional": []}}}}
    sources = {}
    subject = _entity("subj@1", {"sid": {"kind": "column", "column": "sid"}})
    target = _entity("obj@1", {"o": {"kind": "constant", "value": "O"}})
    for seat, kind in CELLS:
        cell, read = name(seat, kind), column(kind)
        as_time = dict(TYPES[kind][3])
        predicate = f"p_{cell}@1"
        bind = {"occurred_at": {"kind": "column", "column": "at"}, "subject": subject}
        qualifiers = {"required": [], "optional": []}
        obj = {"kind": "entity_ref", "types": ["obj@1"], "qualifiers": qualifiers}
        extra = {}
        if seat in ("key_one", "key_several", "key_constant"):
            far = f"{cell}@1"
            keys = {"k": {"kind": "constant", "value": TYPES[kind][2]} if seat == "key_constant"
                    else {"kind": "column", "column": read}}
            if seat == "key_several":
                keys["j"] = {"kind": "column", "column": "j"}
            entities[far] = {"keys": sorted(keys)}
            obj["types"] = [far]
            bind["target"] = _entity(far, keys)
        elif seat == "attribute":
            holder = f"{cell}@1"
            entities[holder] = {"keys": ["sid"], "attributes": ["v"]}
            vocabulary["register@1"]["subjects"].append(holder)
            bind["subject"] = _entity(holder, {"sid": {"kind": "column", "column": "sid"}})
            extra = {"entities": {holder: {"attributes": {"v": {"kind": "column", "column": read, **as_time}}}}}
            predicate, obj = "register@1", None
        elif seat in ("qualifier_optional", "qualifier_required"):
            qualifiers["required" if seat == "qualifier_required" else "optional"].append("q")
            bind["target"] = target
            bind["q"] = {"kind": "column", "column": read, **as_time}
        elif seat == "value":
            obj = {"kind": "value", "value_type": VALUE_TYPES.get(kind, "number"), "qualifiers": qualifiers}
            bind["value"] = {"kind": "column", "column": read, **as_time}
        else:                                           # event_time
            bind["target"] = target
            bind["occurred_at"] = {"kind": "column", "column": read}
        if obj is not None:
            vocabulary[predicate] = {"status": "active", "cardinality": "many", "subjects": ["subj@1"], "object": obj}
        sources[cell] = {"relation": TABLE, "read": _read(kind if seat == "event_time" else None),
                         "map": {"implementation_id": "declarative-role", "implementation_version": 1,
                                 "unit": {"kind": "row"}},
                         "bind": {**extra, "mappings": {f"s_{cell}": {"predicate": predicate, "bind": bind}}}}
    return {"setup_version": 6, "vocabulary": vocabulary, "entities": entities, "sources": sources}


def seeds():
    """(type, keys) of every node a walk starts from - the subjects, and each attribute cell's holders."""
    out = [("subj", {"sid": row}) for row in ROWS]
    out += [(name(seat, kind), {"sid": row}) for seat, kind in CELLS if seat == "attribute" for row in ROWS]
    return out
