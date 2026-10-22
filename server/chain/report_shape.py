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
    "fail": (WAFER_CELL, "item", "chips"),
    "total": (WAFER_CELL, "chips"),
    "images": (WAFER_CELL, "item", "image"),
    "sets": ("name", "member", "kind"),
}
#: The roles a report cannot be made without.
REQUIRED_ROLES = ("wafer", "fail", "total")
#: The columns that are a LIST of names (a wafer key; the conditions the model reads).
LIST_COLUMNS = {("wafer", "key"), ("wafer", "conditions"), ("fail", WAFER_CELL), ("total", WAFER_CELL),
                ("images", WAFER_CELL)}
#: What a layout slot holds.
SLOT_KINDS = ("table", "image", "text")
#: The cells of `derive.report`, in the form's order.
REPORT_CELLS = tuple(ROLE_COLUMNS) + ("rows", "digits", "prompts", "layout", "loop")
PROMPT_CELLS = ("select", "style", "compare")
LOOP_CELLS = ("steps", "seconds", "context_tokens")
NUMBER_CELLS = {("images", "per_item"), ("images", "px")}
SETS_DEFAULT = "default"


def _column(role):
    return chain_bindings.column_ref(("derive.report.%s.table" % role,))


def _role_node(role):
    fields = [{"key": "table", "required": True, "node": chain_bindings.table_ref()}]
    for cell in ROLE_COLUMNS[role]:
        node = chain_bindings.list_node("column", _column(role)) if (role, cell) in LIST_COLUMNS else _column(role)
        fields.append({"key": cell, "required": False, "node": node})
    fields += [{"key": cell, "required": False, "node": {"kind": "leaf", "hint": "number"}}
               for (at, cell) in sorted(NUMBER_CELLS) if at == role]
    if role == "sets":
        fields.append({"key": SETS_DEFAULT, "required": False,
                       "node": chain_bindings.list_node("set", {"kind": "leaf", "hint": "free"})})
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
        {"key": "prompts", "required": False, "node": _record(PROMPT_CELLS, "free")},
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
    if "digits" in spec and not _whole(spec["digits"], 0):
        return "derive.report.digits must be a whole number from 0, got %r" % (spec["digits"],)
    for cell in LOOP_CELLS:
        if cell in (spec.get("loop") or {}) and not _whole(spec["loop"][cell], 1):
            return "derive.report.loop.%s must be a whole number from 1, got %r" % (cell, spec["loop"][cell])
    for at, slot in enumerate(spec.get("layout") or ()):
        kind = slot.get("kind") if isinstance(slot, dict) else None
        if kind not in SLOT_KINDS:
            return "derive.report.layout[%d].kind %r - one of %s" % (at, kind, " · ".join(SLOT_KINDS))
    return None
