"""A walk's value filters (lead 11-11, owner «여기에 걸을 엣지 필터, 노드 필터 이런 거 하는 거지»).

`edge_filter=<predicate>:<expression>` keeps a step of that predicate whose qualifiers the expression holds true of;
`node_filter=<type>:<expression>` keeps a node of that type the walk reaches whose keys it holds true of - one it does
not hold of is not drawn and not walked on (a node the read starts from is not judged again). Several on one name: all.

The expression is the one grammar (`expression`). The calculator (`holds`) is THE judge: the stored walk runs it over
each atom it fetched. The virtual walk says the same reading in its legs' WHERE (`where`), so a step it refuses is not
read - held to the calculator's answer by test_a_walk_filter_sql_answers_as_the_calculator_pg. What the SQL says
exactly is this much: comparisons of a reference or a literal (a text, a number, true / false), and / or / not, is null;
anything else is refused by name when the walk is asked (`compiled`), as is a reference the predicate or type does not
carry. A time qualifier is refused «not yet»: the calculator compares a time as its text (lead 11-11: an instant).
"""
import expression

#: the nodes a filter is said in - a truth: cmp · and · or · not · isnull; a value under cmp and isnull: ref · lit
TRUTHS, VALUES = ("cmp", "and", "or", "not", "isnull"), ("ref", "lit")
OPERATORS = {"=": "=", "<>": "<>", "!=": "<>", "<": "<", ">": ">", "<=": "<=", ">=": ">="}
#: `expression.NUMERAL` in PostgreSQL's regex: a text a comparison with a number reads as one (storage holds it trimmed)
NUMERAL_SQL = r"^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$"
SAID = "comparisons (= <> < > <= >=), and, or, not, is null"


class NotRead(ValueError):
    """What a walk does not compare yet - said by name (422), never read another way."""


def kind_of(value):
    """A value's kind as a comparison takes it (`expression._kind`): "bool" · "number" · "text", or None."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return "text" if isinstance(value, str) else None


def split(entries):
    """["<name>:<expression>", ...] -> {name: [expression text]} - split on the first colon, as `follow`'s keys."""
    out = {}
    for entry in entries or ():
        name, _, text = str(entry).partition(":")
        out.setdefault(name.strip(), []).append(text)
    return out


def compiled(argument, name, text, readable, not_yet=()):
    """`text` compiled for a filter on `name` reading only `readable` - ValueError names what it cannot be; a name in
    `not_yet` (a time qualifier) is said so."""
    said = f"{argument}={name}:{text}"
    got = expression.compile(text)
    if not got["ok"]:
        raise ValueError(f"{said}: {got['why']}")
    refused = _refused(got["tree"], truth=True)
    if refused:
        raise ValueError(f"{said}: {refused} is not read by a walk filter - it reads {SAID}")
    later = [ref for ref in got["names"] if ref in not_yet]
    if later:
        raise NotRead(f"{said}: {', '.join('[%s]' % ref for ref in later)} is a time - a walk filter does not compare "
                      f"times yet")
    unknown = [ref for ref in got["names"] if ref not in readable]
    if unknown:
        raise ValueError(f"{said}: {', '.join('[%s]' % ref for ref in unknown)} is not one {name} carries - it "
                         f"carries {', '.join('[%s]' % ref for ref in readable) or 'none'}")
    return got


def _refused(node, truth):
    """The first part of `node` the filter does not say, in the grammar's words - None when it says all of it."""
    t = node["t"]
    if t not in (TRUTHS if truth else VALUES):
        return f"«{node.get('name', t)}»" if t == "call" else f"a {t} where a {'condition' if truth else 'value'} is"
    if t == "cmp":
        return (f"«{node['op']}»" if node["op"] not in OPERATORS else
                _refused(node["a"], truth=False) or _refused(node["b"], truth=False))
    if t in ("and", "or"):
        return _refused(node["a"], truth=True) or _refused(node["b"], truth=True)
    if t == "not":
        return _refused(node["a"], truth=True)
    if t == "isnull":
        return _refused(node["a"], truth=False)
    return None


def holds(texts, row):
    """Does every compiled filter in `texts` answer true of `row` {reference: value} - THE judge (the calculator)."""
    for each in texts:
        got = expression.run(each, [row])
        if (got.get("values") or [got.get("value")])[0] is not True:
            return False
    return True


def where(texts, cell_of, params, name):
    """SQL: every compiled filter in `texts` answers true - `cell_of(reference)` -> (SQL, "text" | "number", its blank
    SQL) or None when the row carries none of it (blank). Literals go in `params` under `name`."""
    counter = [0]

    def param(value):
        counter[0] += 1
        key = f"{name}{counter[0]}"
        params[key] = value
        return f"%({key})s"

    def value(node):
        if node["t"] == "ref":
            said = cell_of(node["name"])
            if said and said[1] == "time":
                raise NotRead(f"[{node['name']}] is a time - a walk filter does not compare times yet")
            return said[:3] if said else ("NULL", "null", "TRUE")
        v = node["v"]
        if expression.is_blank(v):
            return "NULL", "null", "TRUE"
        return param(v if kind_of(v) != "text" else str(v)), kind_of(v) or "text", "FALSE"

    def numeric(cell, kind):
        """The calculator's `number_of`: a number as it is, a text only when it reads as a number."""
        if kind == "number":
            return f"CAST({cell} AS numeric)", "TRUE"
        return f"CAST({cell} AS numeric)", f"({cell} ~ '{NUMERAL_SQL}')"

    def truth(node):
        t = node["t"]
        if t in ("and", "or"):
            return f"({truth(node['a'])} {t.upper()} {truth(node['b'])})"
        if t == "not":
            return f"(NOT {truth(node['a'])})"
        if t == "isnull":
            blank = value(node["a"])[2]
            return f"(NOT {blank})" if node["negate"] else f"({blank})"
        (a, ka, blank_a), (b, kb, blank_b), op = value(node["a"]), value(node["b"]), OPERATORS[node["op"]]
        if "null" in (ka, kb) or (ka != kb and "bool" in (ka, kb)):       # a bool and another kind: not known
            return "(NULL::boolean)"
        if ka == kb == "text":
            said, reads = f"({a} COLLATE \"C\" {op} {b})", "TRUE"
        elif ka == kb:
            said, reads = f"({a} {op} {b})", "TRUE"
        else:                                           # a text and a number: both as numbers, or not known
            (x, reads_a), (y, reads_b) = numeric(a, ka), numeric(b, kb)
            said, reads = f"({x} {op} {y})", f"({reads_a} AND {reads_b})"
        return f"(CASE WHEN {blank_a} OR {blank_b} THEN NULL WHEN {reads} THEN {said} ELSE NULL END)"

    return " AND ".join(f"({truth(each['tree'])} IS TRUE)" for each in texts) or "true"


def _end(kind, keys):
    import json

    from declaration_names import bare_name

    return bare_name(str(kind)), json.dumps(keys or {}, sort_keys=True, default=str)


def frontier_of(entities):
    """{(bare type, keys)} of the entities a read starts from - `(type, keys, ...)` as a lookup is handed them."""
    return {_end(item[0], item[1]) for item in entities or ()}


def keeps_atom(filters, atom, frontier):
    """THE judge over an atom (the stored and in-memory reads): its predicate's edge filters hold of its qualifiers,
    and each end it reaches - not in `frontier` (`frontier_of`) - holds its type's node filters over its keys."""
    from declaration_names import bare_name

    edges, nodes = filters.get("edge") or {}, filters.get("node") or {}
    texts = edges.get(bare_name(str(atom.predicate)))
    if texts and not holds(texts, (atom.object_payload or {}).get("qualifiers") or {}):
        return False
    ends = [(atom.subject_type, atom.subject_keys)]
    if atom.object_kind == "entity_ref":
        ends.append(((atom.object_payload or {}).get("type"), (atom.object_payload or {}).get("keys")))
    for kind, keys in ends:
        texts = nodes.get(bare_name(str(kind)))
        if texts and _end(kind, keys) not in frontier and not holds(texts, keys or {}):
            return False
    return True
