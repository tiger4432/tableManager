"""THE WALK'S SHAPE GATE (owner 11-11 «노드, 엣지 속성, 키 모든 타입 그리고 걷기 끝»): every seat a declaration can
put a column in, times every column type, is walkable - the node or edge appears, its value is spelled, a blank (and a
NaN) is not said, nothing is left out. ONE product of `SEATS` x `TYPES` builds the table, its rows and the declaration;
the PG file walks it, the SQLite file compiles it. A cell is never listed by hand - only the cells that cannot exist
(`CANNOT_EXIST`) and the cells whose answer is a refusal (`REFUSED`), by name.

The table `shape_gate`: `sid` names the subject (S1 · S2 · S3 · S4), `at` the time of every sentence but the event-time
seat's, `j` a second key part, and one column a type, `c_<type>` (the event time of a date reads `e_date`, declared
datetime). Row S1 holds each type's value, S2 a blank in every typed column, S3 a NaN in a column whose type holds one
(a blank in the rest), S4 S1's values again - what a walk bound on a qualifier comes back to (`follow_bound`)."""
from datetime import date, datetime, timezone
from decimal import Decimal

ZONE = "Asia/Seoul"
TABLE = "shape_gate"
ROWS = ("S1", "S2", "S3", "S4")
AT = "2026-09-30T00:00:00+00:00"

#: type -> (PostgreSQL type as `format_type` names it, table_config type, the value S1 holds, what a binding reading it
#: as a time adds, holds NaN)
TYPES = {
    "text": ("text", "string", "A1", {}, False),
    "integer": ("integer", "number", 7, {}, False),
    "bigint": ("bigint", "number", 9000000000, {}, False),
    "double": ("double precision", "number", 9.5, {}, True),
    "numeric": ("numeric", "number", Decimal("1.25"), {}, True),
    "boolean": ("boolean", "string", True, {}, False),
    "timestamptz": ("timestamp with time zone", "datetime", datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc), {},
                    False),
    "timestamp_zone": ("timestamp without time zone", "datetime", datetime(2026, 9, 30, 10, 0), {"timezone": ZONE},
                       False),
    "date": ("date", "string", date(2026, 9, 30), {"timezone": ZONE}, False),
    "text_format": ("text", "string", "20260930_100000", {"timezone": ZONE, "format": "%Y%m%d_%H%M%S"}, False),
}
TIMES = ("timestamptz", "timestamp_zone", "date", "text_format")
SEATS = ("key_one", "key_several", "key_constant", "attribute", "qualifier_optional", "qualifier_required",
         "qualifier_required_attribute", "follow_bound", "value", "event_time")
#: a constant is a JSON value: it has no column, so no column type - the four JSON kinds stand for it
CANNOT_EXIST = {("key_constant", kind): "a constant has no column type"
                for kind in ("bigint", "numeric", "timestamptz", "timestamp_zone", "date", "text_format")}
CELLS = tuple((seat, kind) for seat in SEATS for kind in TYPES if (seat, kind) not in CANNOT_EXIST)
#: the cells whose answer is the save-time refusal (lead 11-11): an event time read from a column that is not a time
#: (owner 11-07 «원장 소스에는 datetime만»), and from text with a format (83d2654bf retired that path)
REFUSED = {("event_time", kind): "{0} is {1} - declare {0} datetime".format(f"c_{kind}", TYPES[kind][1])
           for kind in ("text", "integer", "bigint", "double", "numeric", "boolean", "text_format")}
#: a required qualifier the sentence leaves to its subject's attribute: the save refuses it by name - a required role is
#: bound in the sentence (`setup_bundle` «missing_required_role»), so the stored translator never takes it from an
#: attribute and neither does the walk (lead 11-11 A)
REFUSED.update({("qualifier_required_attribute", kind):
                f"predicate 'p_qualifier_required_attribute_{kind}' requires role 'q'" for kind in TYPES})
#: the value row is held as «no node»: a value is not a node - it is a Quantity edge's qualifier (owner 11-11; the
#: 08-28 retirement of value nodes stands). This board declares no Quantity, so the walk is held to draw none
VALUE_IS_A_QUALIFIER = "by design not a node - a value is a Quantity edge qualifier (owner 11-11)"
REFUSED[("value", "timestamptz")] = ("role 'value' carries a timestamp, so its column binding must declare the "
                                     "timezone a naive reading is in - the compiler cannot know it and every atom "
                                     "would be refused without it")
#: a walk that binds a predicate on a qualifier (`follow=<predicate>:<qualifier>`, `VirtualEvidenceLookup._bound`) - its
#: sentence is an optional qualifier's here; bound from S1 it comes back to S4 alone. A time read by a format is not
#: compared yet - refused by name (`walk_filter.NotRead`)
D_SHARE = "a bound time read by a format - the walk does not compare it yet (lead 11-11, D)"
#: the cells the gate holds - every cell but the bound formatted time
ENABLED = frozenset(cell for cell in CELLS if cell != ("follow_bound", "text_format"))
VALUE_TYPES = {"text": "string", "boolean": "boolean", **{kind: "timestamp" for kind in TIMES}}


def not_yet(seat, kind):
    """Why a cell is walked but not held - None for an enabled one."""
    return None if (seat, kind) in ENABLED else D_SHARE


def column(kind, seat=None):
    return "e_date" if (seat, kind) == ("event_time", "date") else f"c_{kind}"


def name(seat, kind):
    return f"{seat}_{kind}"


def cell_of_row(kind, row):
    """The cell `row` holds in `column(kind)`: the value, a blank (None) or a NaN."""
    if row in ("S1", "S4"):
        return TYPES[kind][2]
    if row == "S3" and TYPES[kind][4]:
        return float("nan") if kind == "double" else Decimal("NaN")
    return None


def catalogue():
    """`shape_gate`'s table_config entry."""
    types = {"sid": "string", "at": "datetime", "j": "string", "e_date": "datetime",
             **{column(k): spec[1] for k, spec in TYPES.items()}}
    return {"column_types": types}


def kinds():
    """{column: `format_type`} of the table's columns - what the catalogue says the database holds."""
    return {"row_id": "text", "sid": "text", "at": "timestamp with time zone", "j": "text", "e_date": "date",
            **{column(kind): spec[0] for kind, spec in TYPES.items()}}


def ddl(schema):
    columns = ", ".join(f'"{name_}" {kind}' for name_, kind in kinds().items() if name_ != "row_id")
    return f'CREATE TABLE "{schema}"."{TABLE}" (row_id text PRIMARY KEY, {columns})'


def rows():
    """[{column: cell}] of the rows."""
    out = []
    for index, row in enumerate(ROWS, 1):
        out.append({"row_id": f"r{index}", "sid": row, "at": AT, "j": "J", "e_date": cell_of_row("date", row),
                    **{column(kind): cell_of_row(kind, row) for kind in TYPES}})
    return out


def _entity(entity_type, keys):
    return {"kind": "entity", "entity_type": entity_type, "keys": keys}


def _read(seat, kind):
    """A source's `read`: its time from `at`, or from the cell's own column (the event-time seat)."""
    occurred = {"column": "at", "timezone": ZONE} if seat != "event_time" else {
        "column": column(kind, seat), "timezone": ZONE, **({"format": TYPES[kind][3]["format"]}
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
        cell, read = name(seat, kind), column(kind, seat)
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
        elif seat == "qualifier_required_attribute":
            holder = f"{cell}@1"                        # its subject's attribute `q` is the required qualifier
            entities[holder] = {"keys": ["sid"], "attributes": ["q"]}
            qualifiers["required"].append("q")
            bind["subject"] = _entity(holder, {"sid": {"kind": "column", "column": "sid"}})
            bind["target"] = target
            extra = {"entities": {holder: {"attributes": {"q": {"kind": "column", "column": read, **as_time}}}}}
        elif seat in ("qualifier_optional", "qualifier_required", "follow_bound"):
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
            vocabulary[predicate] = {"status": "active", "cardinality": "many", "object": obj,
                                     "subjects": [f"{cell}@1" if seat == "qualifier_required_attribute" else "subj@1"]}
        sources[cell] = {"relation": TABLE, "read": _read(seat, kind),
                         "map": {"implementation_id": "declarative-role", "implementation_version": 1,
                                 "unit": {"kind": "row"}},
                         "bind": {**extra, "mappings": {f"s_{cell}": {"predicate": predicate, "bind": bind}}}}
    return {"setup_version": 6, "vocabulary": vocabulary, "entities": entities, "sources": sources}


def expected(seat, kind, spell_time):
    """The S1 cell as the walk says it: a key in the ledger's one spelling (`map_overlay.canonical_key_value`, by the
    declared type), a time by `spell_time` (the walk's own instant spelling), anything else as the cell holds it."""
    from zoneinfo import ZoneInfo

    import map_overlay
    from ledger import roleframe

    value = TYPES[kind][2]
    if seat == "key_constant":
        return map_overlay.canonical_key_value(roleframe._plain(value), None)
    if seat in ("key_one", "key_several"):
        return map_overlay.canonical_key_value(value, TYPES[kind][1])
    if kind in TIMES:
        if kind == "date":
            value = datetime(value.year, value.month, value.day)
        elif kind == "text_format":
            value = datetime.strptime(value, TYPES[kind][3]["format"])
        return spell_time(value if value.tzinfo else value.replace(tzinfo=ZoneInfo(ZONE)))
    return roleframe._plain(value)
