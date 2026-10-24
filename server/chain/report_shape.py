"""The AI report's settings ARE its chain declaration - `derive.report` (owner 10-22, lead: one concept, one more
declaration kind). Its cells, the form's shape of each, and what the save refuses: a table or column the catalogue
does not declare, wafer keys of another length than the wafer table's, a layout slot of an unknown kind, a rule
that does not stand on a report table of its own (owner 10-23 «리포트용 표가 따로 있어야지»: the operator's table, one
row a wafer, its results in three of its columns; «요약표는 그냥 데이터 표»: the summary table is read, never written).

A wafer is named by one column or a list of them in every role, matched across roles in list order (owner 10-22
«키도 복수로»); the form draws each as a list - one column is a list of one."""
from __future__ import annotations

import re

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
    # a long table of a wafer's conditions, a row a condition - mostly written only when it is out of the ordinary
    # (owner 10-23): a wafer without rows is at the default conditions. Read as the wafer's {name: value}, its time
    # and title when the wafer role names none.
    "conditions": (WAFER_CELL, "name", "value", "time", "title"),
}
#: `images.item_sep`: the image row's item column names several items, split by it (owner 10-23 «including_defects 는
#: "defect_type_1, defect_type_2"») - an image is the chip's, shown for each item it holds.
ITEM_SEP = "item_sep"
#: `images.source`: the image source (image_sources.json) an image column's plain path is read through - the path
#: written as it is, `<source>:<path>` made here (owner 10-23: img_path is an absolute path).
IMAGE_SOURCE = "source"
#: `images.match`: {summary item: image kind or [image kinds]} - the image table's kinds a summary item's pictures are
#: (owner 10-24 «void, signal -> typeA»: {"typeA": ["void", "signal"]}). Undeclared, a picture is its summary item by
#: the same name.
IMAGE_MATCH = "match"
#: `conditions.time_item`: the condition item whose value is the unit's time when the wafer role names no time column
#: (owner 10-24: the wafer's time is a conditions row, not a column) - a table keyed by the wafer alone gives it to
#: every leg, as every condition.
TIME_ITEM = "time_item"
#: `conditions.title_item`: the condition item whose value is the unit's title (owner 10-24 «컨디션 아이템에 타이틀도
#: 있는데 이것도 받게 해») - the title the model reads of a candidate, not a condition row.
TITLE_ITEM = "title_item"
#: `summary.yield_item`: the summary rows (an item name, or a list) that are the unit's yield, not a defect (owner 10-24
#: «요약표에 수율을 그냥 free item으로 넣었는데 … 자꾸 불량 유형으로 리포트하네») - read as every row (rate, or F and N),
#: drawn as the matrix's yield rows, left out of the defect rows, the pareto, the trend and the images.
YIELD_ITEM = "yield_item"


def yield_items(spec) -> set:
    """`summary.yield_item` as a set of item names - one written alone a set of one; empty undeclared. Names are
    compared without surrounding spaces (`name`)."""
    said = ((spec or {}).get("summary") or {}).get(YIELD_ITEM)
    return {name(said)} if isinstance(said, str) else {name(s) for s in said} if isinstance(said, list) else set()


def name(value) -> str:
    """An item or condition name as the declaration and the data are compared - without surrounding spaces, a space
    inside it kept (lead 10-24: «TKOUT DATE » in the data is «TKOUT DATE» declared)."""
    return str(value).strip()
#: The roles a report cannot be made without.
REQUIRED_ROLES = ("wafer", "summary")
#: The columns that are a LIST of names (a wafer key; the conditions the model reads).
LIST_COLUMNS = {("wafer", "key"), ("wafer", "conditions"), ("summary", WAFER_CELL), ("images", WAFER_CELL),
                ("conditions", WAFER_CELL)}
#: What a layout slot holds.
SLOT_KINDS = ("table", "image", "text")
#: The reads whose answer a table slot draws (`report_html.TABLES` draws each).
TABLE_FILLS = ("yield_by", "pareto", "trend")
#: `columns`: the summary table's column heads, a tier each, top first (owner 10-23 «DATE › WAFER › LEG») - a wafer
#: key column, COLUMN_TIME (the wafer's day) or COLUMN_GROUP (this report's or a control's). Declared, the columns
#: stand in the heads' order; undeclared, the group then the key, in the groups' order.
COLUMNS, COLUMN_TIME, COLUMN_GROUP = "columns", "time", "group"
#: `label` (info tables, summary): the head a table's rows stand under - a wide info table's one row its name.
#: `choose` (info tables): the model keeps which rows (yield_by's rows) - owner 10-23 «COND 쪽 넣을 항목은 AI 가 선택».
LABEL, CHOOSE = "label", "choose"
#: `labels.columns`: the word left of each column head tier ({tier: word}) - `column_word`.
LABEL_COLUMNS = "columns"
#: `keys`: every key column of the report's tables, by name, and what it does (owner 10-23 «키 칸을 리스트로 받게»):
#: KEY_UNIT one report a value (the report table's columns), KEY_LATEST only each report's latest value (read as a
#: time), KEY_FOLD rows that differ only there are one (a chip's layers - the smallest drawn, keys' order). A column
#: of no word is a plain part of a row's identity. A role's `wafer` names the key columns its table has.
KEYS, KEY_UNIT, KEY_LATEST, KEY_FOLD = "keys", "unit", "latest", "fold"
KEY_WORDS = (KEY_UNIT, KEY_LATEST, KEY_FOLD)
#: The cells of `derive.report`, in the form's order.
REPORT_CELLS = tuple(ROLE_COLUMNS) + ("rows", "digits", "prompts", "layout", "loop", "template", "control",
                                     "formats", "item_sep", "columns", "keys", "labels", "info", "picture_rows", "results", "send_to")
#: `results`: the report table's column a report's file path goes in, on the wafer's row - the operator names it
#: (owner 10-23 «wafer, 보고서 파일 경로 이 두 개가 최종 출력»). A report's state and why are its Evidence and the
#: chain log; `UNWRITTEN_RESULTS` written are said, not refused (`notes`).
RESULTS_CELL, RESULT_CELLS = "results", ("file",)
UNWRITTEN_RESULTS = ("state", "reason")
#: `send_to`: where a made report's file is POSTed (tools/report_receiver/receive.py - <send_to>/<name>.html).
SEND_TO = "send_to"
#: `picture_rows`: rows of one picture a column in the summary table (owner 10-23 «열마다 한 장») - each a table, its
#: wafer columns and picture column, the row's label and the picture's width (PICTURE_PX: columns × pictures make the
#: file, so smaller than images.px).
PICTURE_ROWS = "picture_rows"
#: `info`: tables of what a wafer is, shown under the summary table's head (owner 10-23) - a long one (`item` the
#: name a row is about, `value` what it says) or a wide one (no `item`: its `value` column is the row, named by it -
#: a yield table [wafer, leg] · yield, lead 10-23). One table or a list of them.
INFO, INFO_COLUMNS = "info", ("item", "value")
INFO_COLUMN = chain_bindings.column_ref(("derive.report.%s.*.table" % INFO,))
PICTURE_COLUMNS = (WAFER_CELL, "image")
PICTURE_PX = 160
#: The prompts: what the model is and its rules (blank: the product's sample text, `report_loop`), and the three the
#: guide names - how it picks wafers, how it writes, what it compares (lead 10-22 «에이전트 문맥» [1] · [2]).
PROMPT_CELLS = ("role", "rules", "select", "style", "compare", "control")
#: `prompts.functions.<read>.about`: a read's line in the model's instructions, when the product's is not the one.
FUNCTIONS_CELL, ABOUT_CELL = "functions", "about"
#: The reads the model calls by name (`report_reads.Report`), in the order its instructions list them.
READS = ("conditions", "candidates", "yield_by", "pareto", "trend", "images", "compare")
LOOP_CELLS = ("steps", "seconds", "context_tokens")
#: `control`: how far back the model may pick a control group from (`recent`: days and/or evaluations before this
#: evaluation's latest wafer, both narrowing when both are written) and how much it may pick (owner 10-23).
RECENT_CELLS = ("days", "evaluations")
#: `control.same`: the wafer table's columns a control candidate shares with this report's wafers - the operator names
#: them (a product group, say; owner 10-23 「제품군도 필터링」). Empty or absent filters nothing.
CONTROL_SAME = "same"
CONTROL_LIMITS = {"max_wafers": 30, "max_evaluations": 3}
NUMBER_CELLS = {("images", "per_item"), ("images", "px")}
#: `formats`: item -> rules, the first that holds colours the cell - a fixed bar on the cell's share (`when`, `value`
#: in percent) or this evaluation against the other groups' F sum / N sum (`vs` control, `times`) (owner 10-23).
FORMAT_WHEN = (">=", ">", "<=", "<")
FORMAT_VS = "control"
FORMAT_CELLS = ("when", "value", "vs", "times", "fill", "color")
FORMAT_COLOURS = ("fill", "color")
#: The fixed words the report file says - a declaration's `labels` says them otherwise (owner 10-23: in Korean).
LABELS = {"report": "report", "left_out": "Left out - two rows for one wafer and name",
          "not_read": "%s was not read.", "nothing_written": "Nothing was written for %s.",
          "no_image": "No image of an occurred defect.", "pareto_item": "item", "pareto_fail": "fail chips",
          "pareto_cumulative": "cumulative", "control": "compare", "mixed": "mixed (%d)", "evidence": "Evidence",
          "conditions": "Conditions", "yield": "Yield", "unpaired": "Image kinds no summary item matches (images.match): %s",
          "no_control": "This report's wafers only - no compare set default or control.recent is declared."}
#: The owner's summary table holds a wafer's value per item (owner 10-22: the product does not make it again) - its
#: fail and total chips, or a rate, or both. A rate is read over `rate_scale`: 1 (a fraction) or 100 (a percent).
RATE_SCALE = "rate_scale"
RATE_SCALES = (1, 100)
SETS_DEFAULT = "default"
#: `sets.kinds`: what a compare set's `kind` column says for a member that is an evaluation, and for one that is a lot -
#: the wafer table's own cells of that name are what it picks by (lead 10-22: no such word in code).
SETS_KINDS = "kinds"
KIND_ROLES = ("evaluation", "lot")
#: The columns a compare set is read by (`report_reads.Report._sets`) - a sets block naming fewer is read as none
#: (`sets_role`), said at save and load (`notes`); lead 10-24, owner «제대로 동기화 할거 아니면 화면 선언 막지마».
SETS_COLUMNS = ROLE_COLUMNS["sets"]
#: The file's slots when a declaration writes neither `layout` nor `template` (owner 10-24 «레이아웃은 알아서 하는거지?»)
#: - the image slot only when the images role is declared (`layout`).
DEFAULT_LAYOUT = ({"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}, {"kind": "image"},
                  {"kind": "text", "slot": "conclusion"})


def layout(spec) -> list:
    """The file's slots in order - `layout` as written; with neither layout nor template, DEFAULT_LAYOUT. The page,
    the model's text slots and the template's marks all read this."""
    spec = spec if isinstance(spec, dict) else {}
    template = spec.get("template")
    if spec.get("layout") or (isinstance(template, str) and template.strip()):
        return list(spec.get("layout") or ())
    return [dict(slot) for slot in DEFAULT_LAYOUT if slot["kind"] != "image" or isinstance(spec.get("images"), dict)]


def sets_role(spec):
    """The compare set role when it names every column it is read by (SETS_COLUMNS), else None - read as no sets."""
    sets = (spec or {}).get("sets")
    return sets if isinstance(sets, dict) and all(sets.get(cell) for cell in SETS_COLUMNS) else None


def image_match(spec) -> dict:
    """`images.match` as {image kind: summary item} - a kind written alone a list of one; {} undeclared."""
    match = ((spec or {}).get("images") or {}).get(IMAGE_MATCH)
    out = {}
    for item, kinds in (match.items() if isinstance(match, dict) else ()):
        for kind in [kinds] if isinstance(kinds, str) else kinds if isinstance(kinds, list) else ():
            out.setdefault(name(kind), name(item))
    return out


def info_rows(spec) -> list:
    """`derive.report.info` as a list of its tables - one written alone is a list of one."""
    info = (spec or {}).get(INFO)
    return [info] if isinstance(info, dict) else list(info) if isinstance(info, list) else []


def _column(role):
    return chain_bindings.column_ref(("derive.report.%s.table" % role,))


PICTURE_COLUMN = chain_bindings.column_ref(("derive.report.%s.*.table" % PICTURE_ROWS,))


def _role_node(role):
    fields = [{"key": "table", "required": True, "node": chain_bindings.table_ref()},
              {"key": RENAME, "required": False, "node": {"kind": "map", "keyed_by": "name", "member": "column",
                                                          "of": _column(role)}}]
    if role == "wafer":
        fields.append({"key": chain_bindings.EXCLUDE_KEY, "required": False, "node": chain_bindings.list_node(
            "column", chain_bindings.gate_item_node(("derive.report.wafer.table",)))})
    for cell in ROLE_COLUMNS[role]:
        node = chain_bindings.list_node("column", _column(role)) if (role, cell) in LIST_COLUMNS else _column(role)
        fields.append({"key": cell, "required": False, "node": node})
    fields += [{"key": cell, "required": False, "node": {"kind": "leaf", "hint": "number"}}
               for (at, cell) in sorted(NUMBER_CELLS | {("summary", RATE_SCALE)}) if at == role]
    if role == "images":
        fields += [{"key": cell, "required": False, "node": {"kind": "leaf", "hint": "free"}}
                   for cell in (ITEM_SEP, IMAGE_SOURCE)]
        fields.append({"key": IMAGE_MATCH, "required": False, "node": {
            "kind": "map", "keyed_by": "name", "member": "item",
            "of": chain_bindings.list_node("kind", {"kind": "leaf", "hint": "free"})}})
    if role == "summary":
        fields.append({"key": LABEL, "required": False, "node": {"kind": "leaf", "hint": "free"}})
        fields.append({"key": YIELD_ITEM, "required": False,
                       "node": chain_bindings.list_node("item", {"kind": "leaf", "hint": "free"})})
    if role == "conditions":
        fields.append({"key": TIME_ITEM, "required": False, "node": {"kind": "leaf", "hint": "free"}})
        fields.append({"key": TITLE_ITEM, "required": False, "node": {"kind": "leaf", "hint": "free"}})
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
        # the HTML Excel puts on the clipboard - the form pastes it (`report_template`)
        {"key": "template", "required": False, "node": {"kind": "leaf", "hint": "html"}},
        {"key": "control", "required": False, "node": {"kind": "record", "fields": [
            {"key": "recent", "required": False, "node": _record(RECENT_CELLS, "number")},
            {"key": CONTROL_SAME, "required": False, "node": chain_bindings.list_node("column", _column("wafer"))}]
            + _record(tuple(CONTROL_LIMITS), "number")["fields"]}},
        {"key": "formats", "required": False, "node": {"kind": "map", "keyed_by": "name", "member": "item",
                                                       "of": chain_bindings.list_node("rule", {"kind": "record", "fields": [
            {"key": cell, "required": False, "node": {"kind": "leaf", "hint": "number" if cell in ("value", "times")
                                                      else "free"}} for cell in FORMAT_CELLS]})}},
        {"key": "item_sep", "required": False, "node": {"kind": "leaf", "hint": "free"}},
        {"key": COLUMNS, "required": False, "node": chain_bindings.list_node("head", {"kind": "leaf", "hint": "free"})},
        {"key": KEYS, "required": False, "node": {"kind": "map", "keyed_by": "name", "member": "column",
                                                  "of": chain_bindings.list_node("word", {"kind": "leaf", "hint": "free"})}},
        {"key": "labels", "required": False, "node": {"kind": "record", "fields": _record(tuple(LABELS), "free")[
            "fields"] + [{"key": LABEL_COLUMNS, "required": False, "node": {
                "kind": "map", "keyed_by": "name", "member": "head", "of": {"kind": "leaf", "hint": "free"}}}]}},
        # «*»: the form fills it with the cell's own row number - a row's columns are its own table's (lead 10-23)
        {"key": INFO, "required": False, "node": chain_bindings.list_node("table", {"kind": "record", "fields": [
            {"key": "table", "required": True, "node": chain_bindings.table_ref()},
            {"key": WAFER_CELL, "required": True, "node": chain_bindings.list_node("column", INFO_COLUMN)},
            {"key": "item", "required": False, "node": INFO_COLUMN},
            {"key": "value", "required": True, "node": INFO_COLUMN},
            {"key": "rows", "required": False, "node": chain_bindings.list_node("name", {"kind": "leaf", "hint": "free"})},
            {"key": LABEL, "required": False, "node": {"kind": "leaf", "hint": "free"}},
            {"key": CHOOSE, "required": False, "node": {"kind": "leaf", "hint": "flag"}}]})},
        {"key": PICTURE_ROWS, "required": False, "node": chain_bindings.list_node("row", {"kind": "record", "fields": [
            {"key": "label", "required": True, "node": {"kind": "leaf", "hint": "free"}},
            {"key": "table", "required": True, "node": chain_bindings.table_ref()},
            {"key": WAFER_CELL, "required": True, "node": chain_bindings.list_node("column", PICTURE_COLUMN)},
            {"key": "image", "required": True, "node": PICTURE_COLUMN},
            {"key": "px", "required": False, "node": {"kind": "leaf", "hint": "number"}},
            {"key": IMAGE_SOURCE, "required": False, "node": {"kind": "leaf", "hint": "free"}}]})},
        {"key": RESULTS_CELL, "required": True, "node": {"kind": "record", "fields": [
            {"key": cell, "required": True, "node": chain_bindings.column_ref(("into.table",))}
            for cell in RESULT_CELLS]}},
        {"key": SEND_TO, "required": False, "node": {"kind": "leaf", "hint": "free"}},
    ]
    return {"kind": "record", "fields": fields}


def unknown_cells(spec) -> list:
    """Cells of `derive.report` this product does not read - named, never refused (as a join's)."""
    return sorted(str(key) for key in (spec or {}) if key not in REPORT_CELLS)


#: A role's `rename`: {the report's key column: this table's column} - a table that spells the wafer's key by another
#: name (소유자 10-24 «컨디션 wf 컬럼 이름 다르면 안됨?»). Every other cell of the role is in the report's names.
RENAME = "rename"


def column_of(role, name):
    """`name` (the report's spelling) as the role's table spells it - its `rename`, else itself."""
    renamed = (role or {}).get(RENAME) if isinstance(role, dict) else None
    return str(renamed.get(name, name)) if isinstance(renamed, dict) else name


def _by_position(role, wafer_key, every):
    """A role's wafer list matched to the report's wafer key by POSITION (소유자 10-24 «의미적으로 wafer,leg ==
    wafer_id,leg» · «매칭 알아서»): its i-th column, when it is not a report key name, is the report key's i-th -
    the role then reads in the report's names and `rename` says its own."""
    if not isinstance(role, dict) or WAFER_CELL not in role:
        return role
    names = wafer_columns(role[WAFER_CELL])
    renamed = dict(role.get(RENAME) or {}) if isinstance(role.get(RENAME), dict) else {}
    from database import crud
    own = crud.TABLE_CONFIG.get(str(role.get("table") or ""), {}) or {}
    own_keys = set(own.get("composite_key_source") or ()) | ({own["business_key"]} if own.get("business_key") else set())
    out = []
    by_case = {key.lower(): key for key in wafer_key}
    for at, name in enumerate(names):
        same = by_case.get(name.lower())
        # a name that differs only in case is the report key it spells (WAFER = wafer); by POSITION only when the list
        # is as long as the wafer key - a shorter list (an image table with no time) would shift every part after the
        # gap (lead 10-24: L landed on tkout_time). Only a KEY column of the role's own table stands in.
        if name not in every and name in own_keys and same and same not in names:
            renamed.setdefault(same, name)
            out.append(same)
        elif (len(names) == len(wafer_key) and name not in every and name in own_keys
              and wafer_key[at] not in names):
            renamed.setdefault(wafer_key[at], name)
            out.append(wafer_key[at])
        else:
            out.append(name)
    return role if out == names else dict(role, **{WAFER_CELL: out, RENAME: renamed})


def matched(spec):
    """`spec` with every role's wafer list matched by position (`_by_position`) - what the save and the reads see."""
    if not isinstance(spec, dict) or not isinstance(spec.get("wafer"), dict):
        return spec
    wafer_key = wafer_columns(spec["wafer"].get("key"))
    every = wafer_key + [c for c in key_words(spec) if c not in wafer_key]
    out = dict(spec)
    for role in ROLE_COLUMNS:
        if isinstance(spec.get(role), dict):
            out[role] = _by_position(spec[role], wafer_key, every)
    for cell in (INFO, PICTURE_ROWS):
        value = spec.get(cell)
        if isinstance(value, dict):
            out[cell] = _by_position(value, wafer_key, every)
        elif isinstance(value, list):
            out[cell] = [_by_position(row, wafer_key, every) for row in value]
    return out


def wafer_columns(value) -> list:
    """A wafer cell as its list of columns - one column is a list of one."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(each) for each in value] if isinstance(value, list) else []


def _whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def _table_refusal(path, written, cells, lists, numbers, key_names):
    """A role (or a picture row): its table declared, each column its table's, its wafer columns key columns by name -
    one of the wafer key's at least, the unit's all (`key_names`: (the wafer key, every key column, the unit))."""
    if not isinstance(written, dict):
        return "%s is a table and its columns, got %r" % (path, written)
    table = written.get("table")
    known = chain_bindings.declared_columns(str(table or ""))
    if known is None:
        return "%s.table %r is not a declared table - name one of table_config" % (path, table)
    for cell in cells:
        if cell not in written:
            continue
        names = (wafer_columns(written[cell]) if cell in lists
                 else [written[cell]] if isinstance(written[cell], str) else None)
        if names is None:
            return "%s.%s is a column name, got %r" % (path, cell, written[cell])
        for name in names:
            if column_of(written, name) not in known:
                return "%s.%s %r is not a column of %r - name one of its columns%s" % (
                    path, cell, column_of(written, name), table,
                    ", or %s.%s {%r: <its column>}" % (path, RENAME, name) if cell == WAFER_CELL else "")
        if cell == WAFER_CELL:
            wafer_key, every, unit = key_names
            # 소유자 10-24 «키 컬럼 맞음» · «제대로 동기화 할거 아니면 화면 선언 막지마»: the table's own key columns pass too
            from database import crud
            own = crud.TABLE_CONFIG.get(str(table), {}) or {}
            own_keys = set(own.get("composite_key_source") or ()) | ({own["business_key"]} if own.get("business_key") else set())
            stray = [name for name in names if name not in every and column_of(written, name) not in own_keys]
            if stray:
                return ("%s.wafer %r is not a key column - the key columns a table has, by name: derive.report.wafer.key "
                        "(%s) and derive.report.keys" % (path, stray[0], ", ".join(wafer_key)))
            missing = [c for c in unit if c not in names]
            if not any(name in wafer_key for name in names) or missing:
                return ("%s.wafer names none of the report's wafer (%s) - a table is read by the wafer key columns it has; "
                        "a column spelled otherwise: %s.%s {%r: <its column>}"
                        % (path, ", ".join(missing or wafer_key), path, RENAME, (missing or wafer_key)[0]))
    for cell in numbers:
        if cell in written and not _whole(written[cell], 1):
            return "%s.%s must be a whole number from 1, got %r" % (path, cell, written[cell])
    return None


def key_words(spec) -> dict:
    """`keys` as {column: [word, ...]} - none written, {}."""
    keys = (spec or {}).get(KEYS)
    return {str(c): list(words) for c, words in keys.items()} if isinstance(keys, dict) else {}


def unit_columns(spec) -> list:
    """The key columns a report is one of (KEY_UNIT), in the wafer key's order - [] when `keys` says none."""
    said = key_words(spec)
    return [c for c in wafer_columns(((spec or {}).get("wafer") or {}).get("key")) if KEY_UNIT in said.get(c, ())]


def _keys_refusal(spec, wafer_key):
    keys = spec.get(KEYS)
    if keys is None:
        return None
    if not isinstance(keys, dict) or not all(isinstance(words, list) and all(w in KEY_WORDS for w in words)
                                             for words in keys.values()):
        return ("derive.report.keys is {key column: [what it does]} - each word one of %s, [] for a plain part; got %r"
                % (" · ".join(KEY_WORDS), keys))
    for column, words in keys.items():
        if (KEY_UNIT in words or KEY_LATEST in words) and column not in wafer_key:
            return ("derive.report.keys.%s %s is a wafer key column's - derive.report.wafer.key (%s)"
                    % (column, " · ".join(w for w in words if w != KEY_FOLD), ", ".join(wafer_key)))
        if KEY_FOLD in words and column in wafer_key:
            return ("derive.report.keys.%s fold is a column beyond the wafer key - the rows that differ only there are "
                    "one (a chip's layers)" % column)
        if KEY_UNIT in words and KEY_LATEST in words:
            return "derive.report.keys.%s is the unit or the latest of it, not both" % column
    if any(KEY_LATEST in words for words in keys.values()) and not unit_columns(spec):
        return "derive.report.keys latest needs a unit column - the latest is each report's"
    return None


def _label_refusal(path, role, spec, over_names):
    """A table's `label`: a text; over a table's names it needs `item_sep` - the head they stand under."""
    if LABEL not in role:
        return None
    if not isinstance(role[LABEL], str) or not role[LABEL].strip():
        return "%s.label is the head its rows stand under, got %r" % (path, role[LABEL])
    if over_names and not spec.get("item_sep"):
        return ("%s.label stands over the names - derive.report.item_sep says how a name splits into heads, e.g. "
                '"item_sep": "."' % path)
    return None


def _columns_refusal(spec):
    """`columns`: a list, each a wafer key column, «time» or «group», once."""
    heads = spec.get(COLUMNS)
    if heads is None:
        return None
    keys = wafer_columns(spec["wafer"].get("key"))
    known = keys + [COLUMN_TIME, COLUMN_GROUP]
    if not isinstance(heads, list) or not heads or any(not isinstance(h, str) or h not in known for h in heads) \
            or len(set(heads)) != len(heads):
        return ("derive.report.columns lists the column heads, top first, each once - a key column (%s), %r or %r; "
                "got %r" % (", ".join(keys), COLUMN_TIME, COLUMN_GROUP, heads))
    if COLUMN_TIME in heads and not (spec["wafer"].get("time") or (spec.get("conditions") or {}).get("time")
                                     or (spec.get("conditions") or {}).get(TIME_ITEM)):
        return ("derive.report.columns %r is the wafer's day - derive.report.wafer.time or conditions.time names the "
                "column it is read from" % COLUMN_TIME)
    return None


def report_key(spec, table) -> list:
    """The unit (`keys`) when written - else read off the report table, below."""
    if unit_columns(spec):
        return unit_columns(spec)
    return _report_table_key(spec, table)


def _report_table_key(spec, table) -> list:
    """The report table's wafer: the columns of `wafer.key` that `table` declares, in that order - a report table keyed
    by the wafer alone reads every row of it the wafer table holds (owner 10-23 «리포트는 wafer 하나지, leg 는 리포트
    내용에»). [] when it declares none."""
    known = chain_bindings.declared_columns(str(table or "")) or ()
    return [c for c in wafer_columns(((spec or {}).get("wafer") or {}).get("key")) if c in known]


def result_columns(rule) -> list:
    """The report table columns a report rule writes - `results`, in RESULT_CELLS order."""
    results = ((rule or {}).get("params") or {}).get(RESULTS_CELL) or {}
    return [str(results[cell]) for cell in RESULT_CELLS if isinstance(results, dict) and results.get(cell)]


def refusal(spec, on_table=None, into_table=None) -> str | None:
    """Why this `derive.report` cannot be made, or None - the first reason, path first. `on_table` · `into_table`: the
    rule's, one report table (`report_key`); the summary table or a table without the wafer's column is refused by
    name. None: not checked."""
    spec = matched(spec) if isinstance(spec, dict) else {}
    missing = [role for role in REQUIRED_ROLES if not isinstance(spec.get(role), dict)]
    if missing:
        return "derive.report needs %s - each a table and its columns" % ", ".join(missing)
    wafer_key = wafer_columns(spec["wafer"].get("key"))
    if not wafer_key:
        return "derive.report.wafer.key names no column - the column (or columns) a wafer is known by"
    said = _keys_refusal(spec, wafer_key)
    if said:
        return said
    exclude = spec["wafer"].get(chain_bindings.EXCLUDE_KEY)
    if exclude is not None:
        known = chain_bindings.declared_columns(str(spec["wafer"].get("table") or "")) or ()
        if not isinstance(exclude, list) or any(chain_bindings.gate_item_refused(item) for item in exclude):
            return ('derive.report.wafer.exclude is a list of {column: [values]} - a value with * or ? a pattern, e.g. '
                    '[{"leg": ["*_T", "*TEST*"]}]; got %r' % (exclude,))
        unknown = [c for c in chain_bindings.gate_columns(exclude) if c not in known]
        if unknown:
            return "derive.report.wafer.exclude %r is not a column of %r - name one of its columns" % (
                unknown[0], spec["wafer"].get("table"))
    key_names = (wafer_key, wafer_key + [c for c in key_words(spec) if c not in wafer_key], unit_columns(spec))
    for role, cells in ROLE_COLUMNS.items():
        if spec.get(role) is not None:
            said = _table_refusal("derive.report.%s" % role, spec[role], cells,
                                  {c for at, c in LIST_COLUMNS if at == role}, {c for at, c in NUMBER_CELLS if at == role},
                                  key_names)
            if said:
                return said
    match = (spec.get("images") or {}).get(IMAGE_MATCH) if isinstance(spec.get("images"), dict) else None
    if match is not None and not (isinstance(match, dict) and all(
            isinstance(kinds, str) or isinstance(kinds, list) and all(isinstance(k, str) for k in kinds)
            for kinds in match.values())):
        return ('derive.report.images.match is {summary item: image kind or [image kinds]}, e.g. '
                '{"typeA": ["void", "signal"]}; got %r' % (match,))
    said = spec["summary"].get(YIELD_ITEM)
    if said is not None and not (isinstance(said, str) and said.strip() or isinstance(said, list) and said and all(
            isinstance(s, str) and s.strip() for s in said)):
        return ('derive.report.summary.yield_item is the summary item (or items) that is the yield, e.g. "YIELD"; got %r'
                % (said,))
    time_item = (spec.get("conditions") or {}).get(TIME_ITEM) if isinstance(spec.get("conditions"), dict) else None
    if time_item is not None and not (isinstance(time_item, str) and time_item.strip()):
        return ("derive.report.conditions.time_item is the condition item whose value is the wafer's time, e.g. "
                '"tkout_time"; got %r' % (time_item,))
    title_item = (spec.get("conditions") or {}).get(TITLE_ITEM) if isinstance(spec.get("conditions"), dict) else None
    if title_item is not None and not (isinstance(title_item, str) and title_item.strip()):
        return ("derive.report.conditions.title_item is the condition item whose value is the wafer's title, e.g. "
                '"Title"; got %r' % (title_item,))
    info = spec.get(INFO)
    if info is not None and not isinstance(info, (dict, list)):
        return "derive.report.info is a table and its columns, or a list of them, got %r" % (info,)
    for at, row in enumerate(info_rows(spec)):
        path = "derive.report.info" if isinstance(info, dict) else "derive.report.info[%d]" % at
        said = _table_refusal(path, row, (WAFER_CELL,) + INFO_COLUMNS, {WAFER_CELL}, set(), key_names)
        if said:
            return said
        if not row.get(WAFER_CELL) or not row.get("value"):
            return ("%s names wafer and value - the wafer columns and what a row says (item: the name a row is "
                    "about; none: the value column is the row)" % path)
        if "rows" in row and not (isinstance(row["rows"], list) and all(isinstance(r, str) for r in row["rows"])):
            return "%s.rows is a list of names, got %r" % (path, row["rows"])
        said = _label_refusal(path, row, spec, bool(row.get("item")))
        if said:
            return said
        if CHOOSE in row and not isinstance(row[CHOOSE], bool):
            return "%s.choose is true or false - the model keeps which of its rows, got %r" % (path, row[CHOOSE])
    rows = spec.get(PICTURE_ROWS)
    if rows is not None and not isinstance(rows, list):
        return "derive.report.%s is a list of picture rows, got %r" % (PICTURE_ROWS, rows)
    for at, row in enumerate(rows or ()):
        path = "derive.report.%s[%d]" % (PICTURE_ROWS, at)
        said = _table_refusal(path, row, PICTURE_COLUMNS, {WAFER_CELL}, {"px"}, key_names)
        if said:
            return said
        missing = [cell for cell in ("label",) + PICTURE_COLUMNS if not row.get(cell)]
        if missing or not isinstance(row["label"], str):
            return "%s needs label, wafer and image - the row's name, the wafer columns, the picture column" % path
    results = spec.get(RESULTS_CELL)
    if not isinstance(results, dict) or not all(isinstance(results.get(c), str) and results[c].strip()
                                                for c in RESULT_CELLS):
        return ('derive.report.results names the report table\'s column a report\'s file path goes in - '
                '{"file": "<column>"}')
    table = spec["summary"].get("table")
    if on_table is not None and into_table is not None and on_table != into_table:
        return ("the report rule stands on its report table - on.table and into.table are one table, got %r and %r"
                % (on_table, into_table))
    report_table = into_table if into_table is not None else on_table
    if report_table is not None and report_table == table:
        return ("the report rule stands on a report table of its own - one row a wafer, its wafer column "
                "(derive.report.wafer.key) and its file column (derive.report.results.file); the summary table %r is read, "
                "never written"
                % table)
    if report_table is not None and unit_columns(spec) and set(unit_columns(spec)) != set(
            _report_table_key(spec, report_table)):
        return ("derive.report.keys unit (%s) is the report table's wafer - %r holds %s of the wafer key"
                % (", ".join(unit_columns(spec)), report_table,
                   ", ".join(_report_table_key(spec, report_table)) or "none"))
    if report_table is not None and not report_key(spec, report_table):
        return ("%r has none of derive.report.wafer.key's columns (%s) - a report table is one row a wafer, its wafer "
                "column among them" % (report_table, ", ".join(wafer_columns(spec["wafer"].get("key")))))
    send_to = spec.get(SEND_TO)
    if send_to is not None and not (isinstance(send_to, str) and send_to.startswith(("http://", "https://"))):
        return "derive.report.send_to is the address a report is POSTed to (http://...), got %r" % (send_to,)
    summary = spec["summary"]
    known = chain_bindings.declared_columns(str(report_table or "")) or ()
    unknown = [results[c] for c in RESULT_CELLS if results[c] not in known]
    if report_table is not None and unknown:
        return ("derive.report.results %r is not a column of %r - add it to the report table's declaration"
                % (unknown[0], report_table))
    if not summary.get("item"):
        return "derive.report.summary.item names no column - the item a row is about"
    said = _label_refusal("derive.report.summary", summary, spec, True)
    if said:
        return said
    said = _columns_refusal(spec)
    if said:
        return said
    if bool(summary.get("fail")) != bool(summary.get("total")):
        return "derive.report.summary names fail and total together - the F and the N of one row"
    if not summary.get("rate") and not summary.get("fail"):
        return "derive.report.summary needs rate, or fail and total - what a row says about its item"
    if summary.get("rate") and not (_whole(summary.get(RATE_SCALE), 1) and summary[RATE_SCALE] in RATE_SCALES):
        return "derive.report.summary.rate_scale: 1 or 100 - what a full rate reads as, got %r" % (
            summary.get(RATE_SCALE),)
    sets = sets_role(spec)
    if sets is not None:
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
    control = spec.get("control")
    if control is not None:
        recent = control.get("recent") if isinstance(control, dict) else None
        if not isinstance(recent, dict) or not set(recent) & set(RECENT_CELLS) or set(recent) - set(RECENT_CELLS):
            return ('derive.report.control.recent says how far back - {"days": <n>} and/or {"evaluations": <n>}, '
                    "got %r" % (recent,))
        for cell, value in list(recent.items()) + [(c, control[c]) for c in CONTROL_LIMITS if c in control]:
            if not _whole(value, 1):
                return "derive.report.control.%s must be a whole number from 1, got %r" % (cell, value)
        same = control.get(CONTROL_SAME)
        if same is not None:
            table = (spec.get("wafer") or {}).get("table")
            known = chain_bindings.declared_columns(str(table or "")) or ()
            if not isinstance(same, list) or not all(isinstance(name, str) for name in same):
                return "derive.report.control.same is a list of the wafer table's columns, got %r" % (same,)
            unknown = [name for name in same if name not in known]
            if unknown:
                return "derive.report.control.same %r is not a column of %r - name one of its columns" % (
                    unknown[0], table)
    said = _formats_refusal(spec)
    if said:
        return said
    if "item_sep" in spec and not isinstance(spec["item_sep"], str):
        return "derive.report.item_sep is the text an item name splits at, got %r" % (spec["item_sep"],)
    if "labels" in spec and not isinstance(spec["labels"], dict):
        return "derive.report.labels is {name: text}, got %r" % (spec["labels"],)
    said = (spec.get("labels") or {}).get(LABEL_COLUMNS)
    if said is not None and not (isinstance(said, dict) and all(isinstance(v, str) for v in said.values())):
        return "derive.report.labels.columns is {column head: the word left of it}, got %r" % (said,)
    from chain import report_template

    return report_template.refusal(spec)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _formats_refusal(spec):
    formats = spec.get("formats")
    if formats is None:
        return None
    if not isinstance(formats, dict):
        return "derive.report.formats is {item: [rule, ...]}, got %r" % (formats,)
    for item, rules in formats.items():
        if not isinstance(rules, list):
            return "derive.report.formats.%s is a list of rules, got %r" % (item, rules)
        for at, rule in enumerate(rules):
            path = "derive.report.formats.%s[%d]" % (item, at)
            if not isinstance(rule, dict):
                return "%s is a rule, got %r" % (path, rule)
            if rule.get("vs") is not None:
                if rule["vs"] != FORMAT_VS or not (_number(rule.get("times")) and rule["times"] > 0):
                    return '%s: {"vs": "control", "times": <a number above 0>}, got %r' % (path, rule)
                if not spec["summary"].get("fail"):
                    return ("%s holds this evaluation against the others' F sum / N sum - derive.report.summary "
                            "needs fail and total" % path)
            elif rule.get("when") not in FORMAT_WHEN or not _number(rule.get("value")):
                return '%s: {"when": one of %s, "value": <percent>}, got %r' % (path, " ".join(FORMAT_WHEN), rule)
            for cell in FORMAT_COLOURS:
                if cell in rule and not (isinstance(rule[cell], str) and re.fullmatch(r"#[0-9a-fA-F]{6}", rule[cell])):
                    return "%s.%s is a colour #rrggbb, got %r" % (path, cell, rule[cell])
    return None


def word(spec, name) -> str:
    """A fixed word of the report file - the declaration's `labels`, or the product's."""
    said = ((spec or {}).get("labels") or {}).get(name)
    return said if isinstance(said, str) and said.strip() else LABELS[name]


def column_word(spec, tier) -> str:
    """The word left of a column head tier (owner 10-23: DATE · WAFER · LEG) - `labels.columns`, else the key column's
    own name, «Date» for the wafer's day, nothing for the group."""
    said = ((spec or {}).get("labels") or {}).get(LABEL_COLUMNS) or {}
    if tier in said:
        return str(said[tier])
    return {COLUMN_TIME: "Date", COLUMN_GROUP: ""}.get(tier, "" if tier is None else str(tier))


def control_limit(spec, cell) -> int:
    return ((spec or {}).get("control") or {}).get(cell) or CONTROL_LIMITS[cell]


def notes(spec) -> list:
    """What a report declaration loses without being refused - said at save and load."""
    from chain import report_template

    said = report_template.note(spec)
    out = [said] if said else []
    unknown = sorted(str(name) for name in ((spec or {}).get("labels") or {})
                     if name not in LABELS and name != LABEL_COLUMNS)
    if unknown:
        out.append("derive.report.labels.%s is not a word the report says - one of %s"
                   % (unknown[0], " · ".join(LABELS)))
    sets = (spec or {}).get("sets")
    if isinstance(sets, dict) and sets_role(spec) is None:
        out.append("derive.report.sets names no %s - read as no compare set (a compare set is read by %s)"
                   % (" · ".join(c for c in SETS_COLUMNS if not sets.get(c)), " · ".join(SETS_COLUMNS)))
    unwritten = [c for c in UNWRITTEN_RESULTS if ((spec or {}).get(RESULTS_CELL) or {}).get(c)]
    if unwritten and isinstance(spec.get(RESULTS_CELL), dict):
        out.append("derive.report.results.%s is not written - a report writes its file path; its state and why are "
                   "the file's Evidence and chain_worker.log [Report]" % " · ".join(unwritten))
    return out
