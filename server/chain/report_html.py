"""The AI report's one HTML file (owner 10-22: «html 에 모두 데이터는 임베딩», the original kept on the server): the
declared layout's slots in order - a table, the images, a text - every number and picture inside the file, nothing
fetched. A slot says what fills it (`derive.report.layout`):

    {"kind": "table", "fill": "<a read: yield_by · pareto · trend>"}   that read's last whole table
    {"kind": "image", "fill": "images"}                                the images `images()` embedded
    {"kind": "text",  "slot": "<a name>"}                              what the model wrote for that name

Every fixed word the file says passes `report_shape.word` (owner 10-23: the declaration's `labels`, in Korean).
The file is kept at <data root>/reports/<request>.html; its sha256 names the bytes written."""
from __future__ import annotations

import hashlib
import html
import os

import paths
from chain import report_reads, report_shape

REPORTS_DIRNAME = "reports"
STYLE = """
:root { --ink: #1d2433; --muted: #5b6475; --line: #d9dee8; --head: #eef2f8; --ground: #ffffff; }
body { margin: 0; padding: 24px 16px; background: var(--ground); color: var(--ink);
       font: 14px/1.5 -apple-system, "Segoe UI", "Malgun Gothic", sans-serif; }
main { max-width: 1200px; margin: 0 auto; display: grid; gap: 24px; }
h1 { font-size: 20px; margin: 0; }
.meta { color: var(--muted); }
section { display: grid; gap: 8px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { border: 1px solid var(--line); padding: 4px 8px; text-align: right; white-space: nowrap; }
th { background: var(--head); }
th:first-child, td:first-child, td.rpt-item, td.rpt-info, td.rpt-picture { text-align: left; }
.gallery { display: flex; flex-wrap: wrap; gap: 12px; }
figure { margin: 0; display: grid; gap: 4px; }
figcaption { color: var(--muted); font-size: 12px; }
.text { white-space: pre-wrap; max-width: 72ch; }
.note { color: var(--muted); font-size: 12px; }
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


#: The classes a template's CSS can style the report's tables by (lead 10-23).
HEAD, GROUP, ITEM, CELL = "rpt-head", "rpt-group", "rpt-item", "rpt-cell"
#: The summary table's row kinds under its head, in order: the kind (a sample row's mark, its class), its table key.
BLOCKS = (("info", "info"), ("picture", "pictures"), ("item", "rows"))
KIND_CLASS = {"info": "rpt-info", "picture": "rpt-picture"}
#: A wide table scrolls inside its own box - a template's fixed-width cell does not grow (lead 10-23).
WRAP = '<div class="scroll" style="overflow-x:auto;max-width:100%%">%s</div>'


def _cell(tag, cls, lent=None, colour=None, text="", rowspan=1, colspan=None):
    """One th / td: our class, then the sample's class and style (`lent`), then a format's colour over them."""
    lent = lent or {}
    classes = " ".join(c for c in (cls, lent.get("class")) if c)
    style = ";".join(s.strip().rstrip(";") for s in (lent.get("style"), colour) if s)
    return "<%s class=\"%s\"%s%s%s>%s</%s>" % (
        tag, _e(classes), ' style="%s"' % _e(style) if style else "", ' rowspan="%d"' % rowspan if rowspan > 1 else "",
        ' colspan="%d"' % colspan if colspan is not None else "", text, tag)


def row_heads(blocks, sep):
    """Item names split at `sep` into a row head of several cells (owner 10-23 «a.b.c, a.b.d 면 a, b rowspan»):
    -> (depth, [[(name, [(part, rowspan, colspan), ...]), ...] per block]). Names sharing a leading part are drawn
    together, in the order the first of them came; a name's last part spans the cells left. No `sep`: one cell."""
    split = [[(name, name.split(sep) if sep else [name]) for name in block] for block in blocks]
    depth = max([len(parts) for block in split for _n, parts in block] or [1])

    def gather(rows, level):
        groups = {}
        for name, parts in rows:
            leaf = len(parts) == level + 1
            groups.setdefault((parts[level], leaf), []).append((name, parts))
        out = []
        for (_part, leaf), members in groups.items():
            out += members if leaf else gather(members, level + 1)
        return out

    drawn = []
    for block in split:
        rows = gather(block, 0)
        heads = []
        for at, (name, parts) in enumerate(rows):
            cells = []
            for level, part in enumerate(parts):
                if level == len(parts) - 1:
                    cells.append((part, 1, depth - level))
                    continue
                prefix = parts[:level + 1]
                if at and len(rows[at - 1][1]) > level + 1 and rows[at - 1][1][:level + 1] == prefix:
                    continue
                span = 1
                while at + span < len(rows) and len(rows[at + span][1]) > level + 1 \
                        and rows[at + span][1][:level + 1] == prefix:
                    span += 1
                cells.append((part, span, None))
            heads.append((name, cells))
        drawn.append(heads)
    return depth, drawn


def _colour(rules, cell, here, baseline):
    """The first rule that holds for this cell -> its style, or None (owner 10-23: from the top, the first)."""
    share = cell.get("share")
    if share is None:
        return None
    for rule in rules or ():
        if rule.get("vs"):
            holds = here and baseline is not None and share >= rule["times"] * baseline
        else:
            holds = {">=": share >= rule["value"], ">": share > rule["value"], "<=": share <= rule["value"],
                     "<": share < rule["value"]}[rule["when"]]
        if holds:
            return ";".join("%s:%s" % (prop, rule[cell_]) for cell_, prop in (("fill", "background"), ("color", "color"))
                            if rule.get(cell_))
    return None


def _baseline(cells, here):
    """The other groups' cells of one item as one share: their F sum over their N sum, or None."""
    rest = [c for c in cells[here:] if c.get("fail") is not None and c.get("total")]
    total = sum(c["total"] for c in rest)
    return 100.0 * sum(c["fail"] for c in rest) / total if total else None


def _two_tiers(table):
    parts = table.get("parts")
    if not parts or any(p is None or len(p) < 2 for group in parts for p in group):
        return None
    top, low = [], []
    for group in parts:
        for at, wafer in enumerate(group):
            if at and group[at - 1][0] == wafer[0]:
                top[-1] = (top[-1][0], top[-1][1] + 1)
            else:
                top.append((wafer[0], 1))
            low.append(report_reads.label(wafer[1:]))
    return top, low


def _summary_table(table, spec, lent=None):
    """yield_by's and trend's table: a head row of group names over their columns (a wafer key of several columns in
    two tiers - its first column merged over the rest), then the info · picture · item rows, each head split by
    `item_sep`, each value cell coloured by `formats`."""
    lent = lent or {}
    head = lent.get("head") or {}
    blocks = [(kind, table.get(key) or []) for kind, key in BLOCKS]
    depth, drawn = row_heads([[name for name, _c in rows] for _k, rows in blocks], spec.get("item_sep") or "")
    corner = depth if depth > 1 else None
    tiers = _two_tiers(table)
    out = ["<tr>%s%s</tr>" % (_cell("th", GROUP, head.get("name"), colspan=corner), "".join(
        _cell("th", GROUP, head.get("value"), text=_e(name), colspan=len(columns)) for name, columns in table["groups"]))]
    columns = tiers[1] if tiers else [c for _n, cols in table["groups"] for c in cols]
    if tiers:
        out.append("<tr>%s%s</tr>" % (_cell("th", HEAD, head.get("name"), colspan=corner), "".join(
            _cell("th", HEAD, head.get("value"), text=_e(part), colspan=span if span > 1 else None)
            for part, span in tiers[0])))
    out.append("<tr>%s%s</tr>" % (_cell("th", HEAD, head.get("name"), text=_e(report_shape.word(spec, "item")),
                                        colspan=corner),
                                  "".join(_cell("th", HEAD, head.get("value"), text=_e(c)) for c in columns)))
    here = len(table["groups"][0][1]) if table["groups"] else 0
    formats = spec.get("formats") or {}
    body = []
    for (kind, rows), heads in zip(blocks, drawn):
        dress = lent.get(kind) or lent.get("item") or {}
        cells_of = dict(rows)
        name_class, value_class = KIND_CLASS.get(kind, ITEM), KIND_CLASS.get(kind, CELL)
        for name, parts in heads:
            cells = cells_of[name]
            baseline = _baseline(cells, here) if kind == "item" else None
            row_head = "".join(_cell("td", name_class, dress.get("name"), text=_e(part), rowspan=rowspan,
                                     colspan=colspan if colspan and colspan > 1 else None)
                               for part, rowspan, colspan in parts)
            values = "".join(_cell("td", value_class, dress.get("value"),
                                   _colour(formats.get(name), cell, at < here, baseline) if kind == "item" else None,
                                   _value(cell, name, columns[at] if at < len(columns) else ""))
                             for at, cell in enumerate(cells))
            body.append("<tr>%s%s</tr>" % (row_head, values))
    note = ('<p class="note">%s: %s</p>' % (_e(report_shape.word(spec, "left_out")), _e(", ".join(table["left_out"])))
            if table.get("left_out") else "")
    return WRAP % ("<table><thead>%s</thead><tbody>%s</tbody></table>" % ("".join(out), "".join(body))) + note


def _value(cell, name, column):
    if cell.get("src"):
        return '<img src="%s" alt="%s - %s">' % (cell["src"], _e(name), _e(column))
    return _e(cell.get("refused") or cell.get("text"))


def _pareto_table(table, spec, lent=None):
    head = "".join(_cell("th", HEAD, text=_e(report_shape.word(spec, word)))
                   for word in ("pareto_item", "pareto_fail", "pareto_cumulative"))
    rows = "".join("<tr>%s</tr>" % "".join(_cell("td", ITEM if at == 0 else CELL, text=_e(c))
                                           for at, c in enumerate(row)) for row in table["rows"])
    return WRAP % ("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (head, rows))


TABLES = {"yield_by": _summary_table, "pareto": _pareto_table, "trend": _summary_table}


def _images(embedded, spec) -> str:
    if not embedded:
        return '<p class="note">%s</p>' % _e(report_shape.word(spec, "no_image"))
    out = []
    for item, pictures in embedded.items():
        figures = "".join(
            '<figure><img src="%s" alt="%s on %s"><figcaption>%s</figcaption></figure>'
            % (p["src"], _e(item), _e(p["wafer"]), _e(p["wafer"])) if p.get("src") else
            '<figure><figcaption>%s - %s</figcaption></figure>' % (_e(p["wafer"]), _e(p.get("refused")))
            for p in pictures)
        out.append("<h3>%s</h3><div class=\"gallery\">%s</div>" % (_e(item), figures))
    return "".join(out)


def _table(fill, tables, spec, lent=None):
    table = tables.get(fill)
    return TABLES[fill](table, spec, lent) if table is not None and fill in TABLES else \
        '<p class="note">%s</p>' % _e(report_shape.word(spec, "not_read") % fill)


def _text(slot, texts, spec):
    said = texts.get(slot)
    return '<div class="text">%s</div>' % _e(said) if said else '<p class="note">%s</p>' % _e(
        report_shape.word(spec, "nothing_written") % slot)


def _evidence(lines, spec):
    """The report's steps, folded at its end - what each read and what came back, a line each (owner 10-23)."""
    return ('<details class="evidence"><summary>%s</summary><pre>%s</pre></details>'
            % (_e(report_shape.word(spec, "evidence")), _e("\n".join(lines or ()))))


def page(title, meta, spec, tables, embedded, texts, evidence=None) -> str:
    """The file: `spec.layout`'s slots in order - or, with a company `spec.template`, the template with each mark
    cell filled (`report_template`), the summary table dressed by its sample block. `tables`: read name -> its last
    whole table; `embedded`: item -> pictures; `texts`: slot name -> what the model wrote. A slot with nothing to
    show says so. `evidence`: the steps' lines, folded at the end."""
    spec = spec or {}
    folded = _evidence(evidence, spec) if evidence is not None else ""
    layout, template = spec.get("layout") or (), spec.get("template")
    if isinstance(template, str) and template.strip():
        from chain import report_template

        lent = report_template.lent(template)
        contents = {"title": _e(title), "meta": _e(meta), "images": _images(embedded, spec)}
        contents.update({report_template.TABLE_PREFIX + fill: _table(
            fill, tables, spec, lent if report_template.TABLE_PREFIX + fill == report_template.SAMPLE_TABLE else None)
            for fill in report_shape.TABLE_FILLS})
        contents.update({str(slot.get("slot")): _text(slot.get("slot"), texts, spec) for slot in layout
                         if slot.get("kind") == "text"})
        filled = report_template.fill(template, contents)
        at = filled.lower().rfind("</body>")
        return filled[:at] + folded + filled[at:] if at >= 0 else filled + folded
    sections = []
    for slot in layout:
        kind = slot.get("kind")
        body = (_table(slot.get("fill"), tables, spec) if kind == "table" else _images(embedded, spec)
                if kind == "image" else _text(slot.get("slot"), texts, spec))
        sections.append("<section>%s</section>" % body)
    return ("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            "content=\"width=device-width, initial-scale=1\"><title>%s</title><style>%s</style></head>"
            "<body><main><h1>%s</h1><p class=\"meta\">%s</p>%s%s</main></body></html>"
            % (_e(title), STYLE, _e(title), _e(meta), "".join(sections), folded))


def keep(name, text) -> tuple:
    """Write the file `<name>.html` -> (its path, sha256 of its bytes)."""
    data = text.encode("utf-8")
    folder = os.path.join(paths.DATA_ROOT, REPORTS_DIRNAME)
    os.makedirs(folder, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(name)) or "report"
    path = os.path.join(folder, safe + ".html")
    with open(path + ".tmp", "wb") as handle:
        handle.write(data)
    os.replace(path + ".tmp", path)
    return path, "sha256:" + hashlib.sha256(data).hexdigest()
