"""The AI report's one HTML file (owner 10-22: «html 에 모두 데이터는 임베딩», the original kept on the server): the
declared layout's slots in order - a table, the images, a text - every number and picture inside the file, nothing
fetched. A slot says what fills it (`derive.report.layout`):

    {"kind": "table", "fill": "<a read: yield_by · pareto · trend>"}   that read's last whole table
    {"kind": "image", "fill": "images"}                                the images `images()` embedded
    {"kind": "text",  "slot": "<a name>"}                              what the model wrote for that name

The file is kept at <data root>/reports/<request>.html; its sha256 names the bytes written."""
from __future__ import annotations

import hashlib
import html
import os

import paths
from chain import report_reads

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
th:first-child, td:first-child { text-align: left; }
.gallery { display: flex; flex-wrap: wrap; gap: 12px; }
figure { margin: 0; display: grid; gap: 4px; }
figcaption { color: var(--muted); font-size: 12px; }
.text { white-space: pre-wrap; max-width: 72ch; }
.note { color: var(--muted); font-size: 12px; }
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _summary_table(table) -> str:
    """yield_by's table: a head row of group names over their columns, then a row per item."""
    head = "".join('<th colspan="%d">%s</th>' % (len(columns), _e(name)) for name, columns in table["groups"])
    columns = "".join("<th>%s</th>" % _e(c) for _name, cols in table["groups"] for c in cols)
    rows = "".join("<tr><td>%s</td>%s</tr>" % (_e(item), "".join("<td>%s</td>" % _e(c) for c in cells))
                   for item, cells in table["rows"])
    note = ('<p class="note">Left out - %s: %s</p>' % (report_reads.LEFT_OUT, _e(", ".join(table["left_out"])))
            if table.get("left_out") else "")
    return ('<div class="scroll"><table><thead><tr><th></th>%s</tr><tr><th>Item</th>%s</tr></thead>'
            "<tbody>%s</tbody></table></div>%s" % (head, columns, rows, note))


def _plain_table(table) -> str:
    head = "".join("<th>%s</th>" % _e(c) for c in table["columns"])
    rows = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _e(c) for c in row) for row in table["rows"])
    return '<div class="scroll"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (head, rows)


def _trend_table(table) -> str:
    wafers = []
    for _item, shares in table["series"]:
        for wafer, _share in shares:
            if wafer not in wafers:
                wafers.append(wafer)
    rows = [[item] + ["%.2f%%" % dict(shares)[w] if w in dict(shares) else "" for w in wafers]
            for item, shares in table["series"]]
    return _plain_table({"columns": ["Item"] + wafers, "rows": rows})


TABLES = {"yield_by": _summary_table, "pareto": _plain_table, "trend": _trend_table}


def _images(embedded) -> str:
    if not embedded:
        return '<p class="note">No image of an occurred defect.</p>'
    out = []
    for item, pictures in embedded.items():
        figures = "".join(
            '<figure><img src="%s" alt="%s on %s"><figcaption>%s</figcaption></figure>'
            % (p["src"], _e(item), _e(p["wafer"]), _e(p["wafer"])) if p.get("src") else
            '<figure><figcaption>%s - %s</figcaption></figure>' % (_e(p["wafer"]), _e(p.get("refused")))
            for p in pictures)
        out.append("<h3>%s</h3><div class=\"gallery\">%s</div>" % (_e(item), figures))
    return "".join(out)


def build(title, meta, layout, tables, embedded, texts) -> str:
    """The file: `layout`'s slots in order. `tables`: read name -> its last whole table; `embedded`: item ->
    pictures; `texts`: slot name -> what the model wrote. A slot with nothing to show says so."""
    sections = []
    for slot in layout or ():
        kind = slot.get("kind")
        if kind == "table":
            fill = slot.get("fill")
            table = tables.get(fill)
            body = TABLES[fill](table) if table is not None and fill in TABLES else \
                '<p class="note">%s was not read.</p>' % _e(fill)
        elif kind == "image":
            body = _images(embedded)
        else:
            said = texts.get(slot.get("slot"))
            body = '<div class="text">%s</div>' % _e(said) if said else \
                '<p class="note">Nothing was written for %s.</p>' % _e(slot.get("slot"))
        sections.append("<section>%s</section>" % body)
    return ("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            "content=\"width=device-width, initial-scale=1\"><title>%s</title><style>%s</style></head>"
            "<body><main><h1>%s</h1><p class=\"meta\">%s</p>%s</main></body></html>"
            % (_e(title), STYLE, _e(title), _e(meta), "".join(sections)))


def keep(request_id, text) -> tuple:
    """Write the file -> (its path, sha256 of its bytes)."""
    data = text.encode("utf-8")
    folder = os.path.join(paths.DATA_ROOT, REPORTS_DIRNAME)
    os.makedirs(folder, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(request_id)) or "report"
    path = os.path.join(folder, safe + ".html")
    with open(path + ".tmp", "wb") as handle:
        handle.write(data)
    os.replace(path + ".tmp", path)
    return path, "sha256:" + hashlib.sha256(data).hexdigest()
