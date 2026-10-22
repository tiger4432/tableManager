"""The AI report's settings ARE its chain declaration - `derive.report` (owner 10-22, lead: one concept, one more
declaration kind). Its cells, the form's shape of each, and what the save refuses: a table or column the catalogue
does not declare, wafer keys of another length than the wafer table's, a layout slot of an unknown kind.

A wafer is named by one column or a list of them in every role, matched across roles in list order (owner 10-22
«키도 복수로»); the form draws each as a list - one column is a list of one."""
from __future__ import annotations

import chain_bindings

#: The mapper a report declaration stands as (`rule_shape.as_chain_rule`).
REPORT_MAPPER = "declared:report"
#: The roles that name a table and its columns, and the cells of each that name a column (`WAFER_CELL`: a list).
WAFER_CELL = "wafer"
ROLE_COLUMNS = {
    "wafer": ("key", "time", "lot", "evaluation", "conditions"),
    "summary": (WAFER_CELL, "item", "fail", "total", "rate"),
    "images": (WAFER_CELL, "item", "image"),
    "sets": ("name", "member", "kind"),
}
#: The roles a report cannot be made without.
REQUIRED_ROLES = ("wafer", "summary")
#: The columns that are a LIST of names (a wafer key; the conditions the model reads).
LIST_COLUMNS = {("wafer", "key"), ("wafer", "conditions"), ("summary", WAFER_CELL), ("images", WAFER_CELL)}
#: What a layout slot holds.
SLOT_KINDS = ("table", "image", "text")
#: The reads whose answer a table slot draws (`report_html.TABLES` draws each).
TABLE_FILLS = ("yield_by", "pareto", "trend")
#: The cells of `derive.report`, in the form's order.
REPORT_CELLS = tuple(ROLE_COLUMNS) + ("rows", "digits", "prompts", "layout", "loop")
#: The prompts: what the model is and its rules (blank: the product's sample text, `report_loop`), and the three the
#: guide names - how it picks wafers, how it writes, what it compares (lead 10-22 «에이전트 문맥» [1] · [2]).
PROMPT_CELLS = ("role", "rules", "select", "style", "compare")
#: `prompts.functions.<read>.about`: a read's line in the model's instructions, when the product's is not the one.
FUNCTIONS_CELL, ABOUT_CELL = "functions", "about"
#: The reads the model calls by name (`report_reads.Report`), in the order its instructions list them.
READS = ("conditions", "yield_by", "pareto", "trend", "images", "compare")
LOOP_CELLS = ("steps", "seconds", "context_tokens")
NUMBER_CELLS = {("images", "per_item"), ("images", "px")}
#: The owner's summary table holds a wafer's value per item (owner 10-22: the product does not make it again) - its
#: fail and total chips, or a rate, or both. A rate is read over `rate_scale`: 1 (a fraction) or 100 (a percent).
RATE_SCALE = "rate_scale"
RATE_SCALES = (1, 100)
SETS_DEFAULT = "default"
#: `sets.kinds`: what a compare set's `kind` column says for a member that is an evaluation, and for one that is a lot -
#: the wafer table's own cells of that name are what it picks by (lead 10-22: no such word in code).
SETS_KINDS = "kinds"
KIND_ROLES = ("evaluation", "lot")


def _column(role):
    return chain_bindings.column_ref(("derive.report.%s.table" % role,))


def _role_node(role):
    fields = [{"key": "table", "required": True, "node": chain_bindings.table_ref()}]
    for cell in ROLE_COLUMNS[role]:
        node = chain_bindings.list_node("column", _column(role)) if (role, cell) in LIST_COLUMNS else _column(role)
        fields.append({"key": cell, "required": False, "node": node})
    fields += [{"key": cell, "required": False, "node": {"kind": "leaf", "hint": "number"}}
               for (at, cell) in sorted(NUMBER_CELLS | {("summary", RATE_SCALE)}) if at == role]
    if role == "sets":
        fields.append({"key": SETS_DEFAULT, "required": False,
                       "node": chain_bindings.list_node("set", {"kind": "leaf", "hint": "free"})})
        fields.append({"key": SETS_KINDS, "required": True, "node": _record(KIND_ROLES, "free")})
    return {"kind": "record", "fields": fields}


def _record(cells, hint):
    return {"kind": "record", "fields": [{"key": cell, "required": False, "node": {"kind": "leaf", "hint": hint}}
                                         for cell in cells]}


def skeleton_node():
    """`derive.report`'s node in the chain skeleton's unified root."""
    fields = [{"key": role, "required": role in REQUIRED_ROLES, "node": _role_node(role)} for role in ROLE_COLUMNS]
    fields += [
        {"key": "rows", "required": False, "node": chain_bindings.list_node("item", {"kind": "leaf", "hint": "free"})},
        {"key": "digits", "required": False, "node": {"kind": "leaf", "hint": "number"}},
        {"key": "prompts", "required": False, "node": {"kind": "record", "fields": _record(PROMPT_CELLS, "free")[
            "fields"] + [{"key": FUNCTIONS_CELL, "required": False, "node": {"kind": "record", "fields": [
                {"key": read, "required": False, "node": _record((ABOUT_CELL,), "free")} for read in READS]}}]}},
        {"key": "layout", "required": False, "node": chain_bindings.list_node("slot", _record(
            ("kind", "fill", "slot"), "free"))},
        {"key": "loop", "required": False, "node": _record(LOOP_CELLS, "number")},
    ]
    return {"kind": "record", "fields": fields}


def unknown_cells(spec) -> list:
    """Cells of `derive.report` this product does not read - named, never refused (as a join's)."""
    return sorted(str(key) for key in (spec or {}) if key not in REPORT_CELLS)


def wafer_columns(value) -> list:
    """A wafer cell as its list of columns - one column is a list of one."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(each) for each in value] if isinstance(value, list) else []


def _whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def refusal(spec) -> str | None:
    """Why this `derive.report` cannot be made, or None - the first reason, path first."""
    spec = spec if isinstance(spec, dict) else {}
    missing = [role for role in REQUIRED_ROLES if not isinstance(spec.get(role), dict)]
    if missing:
        return "derive.report needs %s - each a table and its columns" % ", ".join(missing)
    key_length = len(wafer_columns(spec["wafer"].get("key")))
    if not key_length:
        return "derive.report.wafer.key names no column - the column (or columns) a wafer is known by"
    import product_tables
    if key_length > len(product_tables.REPORT_WAFER_KEYS):
        return ("derive.report.wafer.key names %d columns - a report keeps a wafer's key in at most %d"
                % (key_length, len(product_tables.REPORT_WAFER_KEYS)))
    for role, cells in ROLE_COLUMNS.items():
        written = spec.get(role)
        if written is None:
            continue
        if not isinstance(written, dict):
            return "derive.report.%s is a table and its columns, got %r" % (role, written)
        table = written.get("table")
        known = chain_bindings.declared_columns(str(table or ""))
        if known is None:
            return "derive.report.%s.table %r is not a declared table - name one of table_config" % (role, table)
        for cell in cells:
            if cell not in written:
                continue
            names = (wafer_columns(written[cell]) if (role, cell) in LIST_COLUMNS
                     else [written[cell]] if isinstance(written[cell], str) else None)
            if names is None:
                return "derive.report.%s.%s is a column name, got %r" % (role, cell, written[cell])
            for name in names:
                if name not in known:
                    return ("derive.report.%s.%s %r is not a column of %r - name one of its columns"
                            % (role, cell, name, table))
            if cell == WAFER_CELL and len(names) != key_length:
                return ("derive.report.%s.wafer names %d column(s) and derive.report.wafer.key %d - the same wafer, "
                        "column for column" % (role, len(names), key_length))
        for at, cell in NUMBER_CELLS:
            if at == role and cell in written and not _whole(written[cell], 1):
                return "derive.report.%s.%s must be a whole number from 1, got %r" % (role, cell, written[cell])
    summary = spec["summary"]
    if not summary.get("item"):
        return "derive.report.summary.item names no column - the item a row is about"
    if bool(summary.get("fail")) != bool(summary.get("total")):
        return "derive.report.summary names fail and total together - the F and the N of one row"
    if not summary.get("rate") and not summary.get("fail"):
        return "derive.report.summary needs rate, or fail and total - what a row says about its item"
    if summary.get("rate") and not (_whole(summary.get(RATE_SCALE), 1) and summary[RATE_SCALE] in RATE_SCALES):
        return "derive.report.summary.rate_scale: 1 or 100 - what a full rate reads as, got %r" % (
            summary.get(RATE_SCALE),)
    sets = spec.get("sets")
    if isinstance(sets, dict):
        kinds = sets.get(SETS_KINDS)
        said = {role: value for role, value in (kinds.items() if isinstance(kinds, dict) else ())
                if isinstance(value, str) and value.strip()}
        if not said or (isinstance(kinds, dict) and set(kinds) - set(KIND_ROLES)):
            return ("derive.report.sets.kinds says what the kind column holds for %s - e.g. "
                    '{"evaluation": "<value>", "lot": "<value>"}' % " · ".join(KIND_ROLES))
        unread = [role for role in said if not spec["wafer"].get(role)]
        if unread:
            return ("derive.report.sets.kinds.%s needs derive.report.wafer.%s - the wafer column it picks by"
                    % (unread[0], unread[0]))
    functions = (spec.get("prompts") or {}).get(FUNCTIONS_CELL) or {}
    unknown = sorted(str(name) for name in functions if name not in READS) if isinstance(functions, dict) else ["?"]
    if unknown:
        return "derive.report.prompts.functions.%s - one of %s" % (unknown[0], " · ".join(READS))
    if "digits" in spec and not _whole(spec["digits"], 0):
        return "derive.report.digits must be a whole number from 0, got %r" % (spec["digits"],)
    for cell in LOOP_CELLS:
        if cell in (spec.get("loop") or {}) and not _whole(spec["loop"][cell], 1):
            return "derive.report.loop.%s must be a whole number from 1, got %r" % (cell, spec["loop"][cell])
    for at, slot in enumerate(spec.get("layout") or ()):
        kind = slot.get("kind") if isinstance(slot, dict) else None
        if kind not in SLOT_KINDS:
            return "derive.report.layout[%d].kind %r - one of %s" % (at, kind, " · ".join(SLOT_KINDS))
        if kind == "table" and slot.get("fill") not in TABLE_FILLS:
            return "derive.report.layout[%d].fill %r - a table is one of %s" % (at, slot.get("fill"),
                                                                                 " · ".join(TABLE_FILLS))
        if kind == "text" and not str(slot.get("slot") or "").strip():
            return "derive.report.layout[%d].slot names no text - the name the model writes it under" % at
    return None
