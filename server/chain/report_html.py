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
import json
import os

import paths
from chain import report_reads, report_shape

REPORTS_DIRNAME = "reports"
#: Beside a report file, its pictures' refs by number - what GET /reports/<file>/image/<n> opens (owner 10-29)
IMAGES_SUFFIX = ".images.json"
#: Beside a page: the tables the report read (`report_reads.fresh_reading`) - GET /reports opens the page only to who may
#: read them all; a page without it is an administrator's (owner 11-06 access).
TABLES_SUFFIX = ".tables.json"
#: the link around a picture to its original
ORIGINAL = "rpt-original"
STYLE = """
:root { --ink: #1d2433; --muted: #5b6475; --line: #d9dee8; --head: #eef2f8; --ground: #ffffff; }
body { margin: 0; padding: 24px 16px; background: var(--ground); color: var(--ink);
       font: 14px/1.5 -apple-system, "Segoe UI", "Malgun Gothic", sans-serif; }
main { margin: 0 auto; display: grid; gap: 24px; min-width: 0; width: 100%; max-width: 1280px; }
h1 { font-size: 20px; margin: 0; }
.meta { color: var(--muted); }
section { display: grid; gap: 8px; }
.scroll { overflow-x: auto; }
table { border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums;
        border-top: 1px solid var(--line); border-left: 1px solid var(--line); }
th, td { border: 0; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 4px 8px; text-align: center; white-space: normal;
         overflow-wrap: anywhere; vertical-align: top; }
th { background: var(--head); }
thead th { text-align: center; vertical-align: middle; }
thead th:first-child { text-align: left; }
th:first-child, td.rpt-name { text-align: left; }
td.rpt-name { position: sticky; left: 0; z-index: 1; background: var(--ground); }
thead th:first-child { position: sticky; left: 0; z-index: 2; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, var(--px, 320px)); gap: 12px; }
.gallery figure img { width: var(--px, 320px); height: var(--px, 320px); object-fit: contain; display: block;
                      background: var(--head); }
.gallery figure img[hidden] { display: none; }
a.rpt-original { display: contents; }
figure { margin: 0; display: grid; gap: 4px; }
figcaption { color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.text { white-space: pre-wrap; }
.note { color: var(--muted); font-size: 12px; }
section { min-width: 0; }
th.rpt-own { background: #ffcc80; }
"""
#: the report's own wafers' columns - orange (owner 10-24 «리포트 요청한 웨이퍼는 주황색으로 하이라이트»)
OWN = "rpt-own"


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


def _scaled(cells, better_high):
    """A row's cells coloured by their share across it, when no format rule colours them (owner 10-24 «수율은 높은 게
    하늘색 낮은 게 붉은색 · 나머지 디펙들은 반대로»): the row's best end sky, its worst red, the middle plain."""
    shares = [c.get("share") for c in cells if c.get("share") is not None]
    if len(shares) < 2 or max(shares) == min(shares):
        return [None] * len(cells)
    low, high = min(shares), max(shares)
    out = []
    for cell in cells:
        share = cell.get("share")
        if share is None:
            out.append(None)
            continue
        good = (share - low) / (high - low) if better_high else (high - share) / (high - low)
        out.append("background:rgba(135,206,250,%.2f)" % ((good - 0.5) * 2 * 0.8) if good > 0.5 else
                   "background:rgba(239,83,80,%.2f)" % ((0.5 - good) * 2 * 0.6) if good < 0.5 else None)
    return out


def _baseline(cells, own):
    """The other groups' cells of one item as one share: their F sum over their N sum, or None."""
    rest = [c for c, mine in zip(cells, own) if not mine and c.get("fail") is not None and c.get("total")]
    total = sum(c["total"] for c in rest)
    return 100.0 * sum(c["fail"] for c in rest) / total if total else None


def head_tiers(heads):
    """The columns' heads (a text a tier, each column) -> the tiers to draw, [(tier, [(text, span), ...])]: a column
    whose text and every text above are its left neighbour's joins its cell (owner 10-23: date › wafer › leg, the
    same value one cell); a blank never joins. A tier that repeats the one above is left out, the last never."""
    depth = len(heads[0]) if heads else 0
    tiers = []
    for level in range(depth):
        cells = []
        for at, texts in enumerate(heads):
            if at and texts[level] and heads[at - 1][:level + 1] == texts[:level + 1]:
                cells[-1] = (cells[-1][0], cells[-1][1] + 1)
            else:
                cells.append((texts[level], 1))
        tiers.append(cells)
    return [(at, tier) for at, tier in enumerate(tiers) if at == 0 or at == len(tiers) - 1 or tier != tiers[at - 1]]


def _summary_table(table, spec, lent=None):
    """yield_by's and trend's table: the columns' heads in tiers (`head_tiers` - the first the group row), then the
    info · picture · item rows, each head split by `item_sep` (the items under the summary's `label`), each value
    cell coloured by `formats`."""
    lent = lent or {}
    head = lent.get("head") or {}
    sizes = dict(report_shape.SIZE_DEFAULTS, **(spec.get(report_shape.SIZES) or {}))   # derive.report.sizes
    sep = spec.get("item_sep") or ""
    under = table.get("item_label")
    blocks = [(kind, [(under + sep + name if kind == "item" and under else name, cells, name)
                      for name, cells in table.get(key) or []]) for kind, key in BLOCKS]
    depth, drawn = row_heads([[name for name, _c, _r in rows] for _k, rows in blocks], sep)
    corner = depth if depth > 1 else None
    tiers, named = head_tiers(table["heads"]), table.get("tiers") or ()
    own = table["own"]
    out = []
    for level, (at, tier) in enumerate(tiers):
        cls = GROUP if level == 0 else HEAD
        cells, first = [], 0
        for text, span in tier:
            mine = bool(own[first:first + span]) and all(own[first:first + span])
            cells.append(_cell("th", cls + (" " + OWN if mine else ""), head.get("value"), text=_e(text),
                               colspan=span if level == 0 or span > 1 else None))
            first += span
        out.append("<tr>%s%s</tr>" % (
            _cell("th", cls, head.get("name"), text=_e(report_shape.column_word(spec, named[at]))
                  if at < len(named) else "", colspan=corner), "".join(cells)))
    columns = [c for _n, cols in table["groups"] for c in cols]
    formats = spec.get("formats") or {}
    body = []
    for (kind, rows), heads in zip(blocks, drawn):
        dress = lent.get(kind) or lent.get("item") or {}
        cells_of = {name: (cells, raw) for name, cells, raw in rows}
        name_class, value_class = KIND_CLASS.get(kind, ITEM), KIND_CLASS.get(kind, CELL)
        for name, parts in heads:
            cells, raw = cells_of[name]
            baseline = _baseline(cells, own) if kind == "item" else None
            scaled = (_scaled(cells, False) if kind == "item" and not formats.get(raw) else
                      _scaled(cells, True) if any(c.get("higher") == "better" for c in cells) else [None] * len(cells))
            # each row-head cell held at its column's left while the values scroll (owner 10-24 «좌측 헤더열 스크롤
            # 우측해도 보이게») - its level counted from the row's last cell, which ends at the depth
            lefts, at = [], max(depth, 1)
            for _part, _rowspan, colspan in reversed(parts):
                at -= colspan or 1
                lefts.insert(0, "left:%gpx" % (sizes["name_px"] * at) if at else None)
            row_head = "".join(_cell("td", name_class + " rpt-name", dress.get("name"), left, text=_e(part),
                                     rowspan=rowspan, colspan=colspan if colspan and colspan > 1 else None)
                               for (part, rowspan, colspan), left in zip(parts, lefts))
            values = "".join(_cell("td", _aligned(value_class, cell, kind) + (" " + OWN if own[at] else ""),
                                   dress.get("value"),
                                   _colour(formats.get(raw), cell, own[at], baseline) if kind == "item" and
                                   formats.get(raw) else scaled[at],
                                   _value(cell, name, columns[at] if at < len(columns) else ""))
                             for at, cell in enumerate(cells))
            body.append("<tr>%s%s</tr>" % (row_head, values))
    note = ('<p class="note">%s: %s</p>' % (_e(report_shape.word(spec, "left_out")), _e(", ".join(table["left_out"])))
            if table.get("left_out") else "")
    # widths held by the columns themselves - a cell's max-width does not hold a table column (owner 10-24 «표 컬럼폭
    # 100으로»): derive.report.sizes, a long text wraps
    name_px, value_px, heads_at = sizes["name_px"], sizes["value_px"], max(depth, 1)
    cols = "<colgroup>%s%s</colgroup>" % ('<col style="width:%gpx">' % name_px * heads_at,
                                          '<col style="width:%gpx">' % value_px * len(columns))
    return WRAP % ('<table style="table-layout:fixed;width:%gpx;font-size:%gpx">%s<thead>%s</thead><tbody>%s</tbody>'
                   '</table>' % (name_px * heads_at + value_px * len(columns), sizes["font_px"], cols, "".join(out),
                                 "".join(body))) + note


def _aligned(cls, cell, kind):
    """An info cell that says a number stands as the numbers do - right, tabular; its words stand left (lead 10-23)."""
    from expression import number_of

    return CELL if kind == "info" and number_of(cell.get("text")) is not None else cls


def _img(picture, alt, extra=""):
    """A picture's <img> - inside a link to its original when `link_pictures` gave it one (owner 10-29 «크게 보기»)."""
    img = '<img src="%s" alt="%s"%s>' % (picture["src"], alt, extra)
    if not picture.get("href"):
        return img
    rel = ' data-rel="%s"' % _e(picture["rel"]) if picture.get("rel") else ""
    return '<a class="%s" href="%s"%s target="_blank" rel="noopener">%s</a>' % (ORIGINAL, _e(picture["href"]), rel, img)


def link_pictures(file, tables, embedded):
    """Each picture of the page numbered - the tables' picture rows, then the gallery - and given the link its original
    opens at -
    `<file>/image/<n>`, relative to the page (GET /reports/<file>/image/<n>); with server_settings.json's `public_url`
    `<public_url>/reports/<file>/image/<n>`, so it opens from the file a mail carried (lead 10-29), the relative one
    kept beside it for the server's own pages (LINK_SCRIPT) - -> the refs by number, the list `keep` writes beside the
    file. Only pictures read by a ref (`report_reads._picture`)."""
    from runtime import request_timing

    public = request_timing.public_url()
    refs = []
    for picture in _pictures(tables, embedded):
        if picture.get("src") and picture.get("ref"):
            picture["href"] = "%s/image/%d" % (file, len(refs))
            if public:
                picture["rel"], picture["href"] = picture["href"], "%s/reports/%s" % (public, picture["href"])
            refs.append(picture["ref"])
    return refs


def _pictures(tables, embedded):
    """Every picture the page draws - the tables' picture rows, then the gallery, each layer of a stack."""
    for table in (tables or {}).values():
        for _name, cells in (table.get("pictures") or ()) if isinstance(table, dict) else ():
            yield from cells
    for pictures in (embedded or {}).values():
        for picture in pictures:
            yield from picture.get("layers") or [picture]


def _value(cell, name, column):
    if cell.get("src"):
        return _img(cell, "%s - %s" % (_e(name), _e(column)))
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
            _stack(item, p) if len(p.get("layers") or ()) > 1 else
            '<figure>%s<figcaption>%s</figcaption></figure>'
            % (_img(p, "%s on %s" % (_e(item), _e(p["wafer"]))), _e(p["wafer"])) if p.get("src") else
            '<figure><figcaption>%s - %s</figcaption></figure>' % (_e(p["wafer"]), _e(p.get("refused")))
            for p in pictures)
        # every patch one box of images.px, the picture fitted inside it - one grid, no ragged row (owner 10-24 «이미지
        # 패치들 정렬 일정하게 해 · 지금 삐뚤빼뚤함»)
        px = ((spec or {}).get("images") or {}).get("px", 320)
        out.append("<h3>%s</h3><div class=\"gallery\" style=\"--px:%dpx\">%s</div>" % (_e(item), px, figures))
    return "".join(out) + (STACK_SCRIPT if 'class="stack"' in "".join(out) else "")


#: a chip's layers one figure - the wheel over it turns them (owner 10-24 «슬라이드쇼 느낌으로 각 이미지 패치»)
STACK_SCRIPT = ("<script>document.querySelectorAll('figure.stack').forEach(function(f){"
                "var im=f.querySelectorAll('img'),cap=f.querySelector('.layer'),i=0;"
                "f.addEventListener('wheel',function(e){e.preventDefault();im[i].hidden=true;"
                "i=(i+(e.deltaY>0?1:-1)+im.length)%im.length;im[i].hidden=false;"
                "cap.textContent=im[i].dataset.layer+' ('+(i+1)+'/'+im.length+')';},{passive:false});});</script>")


#: the page opened by its signed link (/shared/report/<file>?k=): its pictures' links carry the same ?k= - the key
#: is the page address's, never written into the file (owner 10-29 ㄱ). A link at public_url (its relative one in
#: data-rel) is made relative again on the server's own pages, http(s) /reports/<file> and /shared/report/<file> -
#: they stay as they were; elsewhere (the mail's file, a file:// one in a folder named reports too) it stays as
#: written, the query untouched (lead 10-29)
LINK_SCRIPT = ("<script>document.querySelectorAll('a.%s').forEach(function(a){"
               "var here=location.pathname.replace(/[^/]*$/,'');"
               "if(!a.dataset.rel||location.protocol.indexOf('http')===0&&"
               "(here.endsWith('/reports/')||here.endsWith('/shared/report/'))){"
               "if(a.dataset.rel)a.setAttribute('href',a.dataset.rel);a.search=location.search;}});</script>"
               % ORIGINAL)


def _stack(item, picture):
    layers = picture["layers"]
    images = "".join(_img(p, "%s on %s" % (_e(item), _e(picture["wafer"])), ' data-layer="%s"%s' % (
        _e(p.get("layer")), "" if at == 0 else " hidden")) for at, p in enumerate(layers))
    return ('<figure class="stack" title="wheel: layers">%s<figcaption>%s &middot; <span class="layer">%s (1/%d)</span>'
            '</figcaption></figure>' % (images, _e(picture["wafer"]), _e(layers[0].get("layer")), len(layers)))


def _table(fill, tables, spec, lent=None):
    table = tables.get(fill)
    if table is None or fill not in TABLES:
        return '<p class="note">%s</p>' % _e(report_shape.word(spec, "not_read") % fill)
    note = table.get("note") if isinstance(table, dict) else None
    return TABLES[fill](table, spec, lent) + ('<p class="note">%s</p>' % _e(note) if note else "")


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
    folded = (_evidence(evidence, spec) if evidence is not None else "") + (
        LINK_SCRIPT if any(p.get("href") for p in _pictures(tables, embedded)) else "")
    layout, template = report_shape.layout(spec), spec.get("template")
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
    # one under another, in layout's order (owner 10-23 «배치 그냥 원래대로 세로 나열해»); a table the page's width,
    # wider ones scrolled inside it
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


def file_name(name) -> str:
    """The report file's name for `name` - `<name>.html`, every character outside letters, digits and «-_.» an «_»."""
    return ("".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(name)) or "report") + ".html"


def link_of(path) -> str:
    """The signed-in link to a report file - «reports/<file name>» with its leading slash, what GET /reports/<name>
    opens. The report's `results.file` cell and the GET /reports list both write it (owner 11-04); the path stays
    `keep`'s."""
    return "/reports/" + os.path.basename(str(path))


def keep(name, text, images=(), tables=None) -> tuple:
    """Write the file `<name>.html`, and when it links pictures, beside it `<name>.html` + IMAGES_SUFFIX - their refs
    by number (`link_pictures`), the only originals GET /reports/<file>/image/<n> opens; the list first, so a page never
    links to a list that is not there. A page with no picture leaves no list -> (the page's path, sha256 of its
    bytes)."""
    data = text.encode("utf-8")
    folder = os.path.join(paths.DATA_ROOT, REPORTS_DIRNAME)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, file_name(name))
    listed = path + IMAGES_SUFFIX
    if images:
        _write(listed, json.dumps(list(images), ensure_ascii=False).encode("utf-8"))
    elif os.path.exists(listed):
        os.remove(listed)                                    # written again with no picture: the old list goes
    if tables is not None:
        _write(path + TABLES_SUFFIX, json.dumps(sorted(tables), ensure_ascii=False).encode("utf-8"))
    _write(path, data)
    return path, "sha256:" + hashlib.sha256(data).hexdigest()


def tables_of(path):
    """The tables a page's report read, or None when the page has no record (written before 11-06)."""
    try:
        with open(path + TABLES_SUFFIX, encoding="utf-8") as handle:
            tables = json.load(handle)
    except (OSError, ValueError):
        return None
    return tables if isinstance(tables, list) else None


def _write(path, data):
    with open(path + ".tmp", "wb") as handle:
        handle.write(data)
    os.replace(path + ".tmp", path)
