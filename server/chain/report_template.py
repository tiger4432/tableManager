"""The report's company template (owner 10-23 «회사 양식 엑셀 · 클립보드에 html»): the HTML Excel puts on the
clipboard, pasted into `derive.report.template` as it is. A cell whose text is one mark - {{<text slot>}} ·
{{table:<fill>}} · {{images}} · {{meta}} · {{title}} - has its inside replaced; every other byte of the template
stays, its mso styles included.

The sample block (owner 10-23): the rows right under {{table:yield_by}}'s row whose first cells are {{info}} ·
{{picture}} · {{item}} - each row's first cell (name) and second cell (value) lend their class and style to the
summary table's cells of that kind, the mark's own row to its head; the rows become one cell holding the table.

What the save refuses: a script or a frame · an on… attribute · a reference outside the file (http · https · file ·
//, a CSS url) · a mark this report does not fill · a sample mark outside the sample block · a text slot of the
layout the template has no mark for · a mark not alone in its cell or outside a cell. What is dropped on the way
(lead 10-23): Excel's housekeeping links, its charset line (the file says utf-8, once) and the pictures it puts on
the clipboard as local file paths - the file fetches nothing."""
from __future__ import annotations

import html.parser
import re

MARK = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
#: The marks every report can fill; a table mark is TABLE_PREFIX + one of `report_shape.TABLE_FILLS`.
FIXED_MARKS = ("title", "meta", "images")
TABLE_PREFIX = "table:"
#: The table a sample block lends its formats to, and the row kinds it may sample (`report_html` draws each kind).
SAMPLE_TABLE = TABLE_PREFIX + "yield_by"
SAMPLE_MARKS = ("info", "picture", "item")
SAMPLE_HEAD = "head"
#: Excel's own links on the clipboard - its file list and theme, all local paths.
HOUSEKEEPING_RELS = ("main-file", "file-list", "edit-time-data", "themedata", "colorschememapping")
PICTURE_TAGS = ("img", "v:imagedata")
REFUSED_TAGS = ("script", "iframe", "frame", "object", "embed", "base")
REFERENCE_ATTRS = ("src", "href", "background", "data", "action", "poster", "lowsrc")
OUTSIDE = re.compile(r"^\s*(https?:|file:|ftp:|javascript:|//)", re.I)
#: Excel's pictures on the clipboard - dropped (lead 10-23); a picture from anywhere else is refused.
LOCAL_FILE = re.compile(r"^\s*file:", re.I)
CSS_URL = re.compile(r"url\(\s*['\"]?\s*(?!data:)([^)'\"]*)", re.I)
CELLS = ("td", "th")
DROPPED_SAID = "image(s) dropped: %d - Excel puts pictures on the clipboard as local file paths"
#: The one charset line the file carries - a template's own (Excel writes its code page) is dropped.
CHARSET = '<meta charset="utf-8">'


def _flat(text):
    return " ".join(text.replace("\xa0", " ").split())


class _Reader(html.parser.HTMLParser):
    """One pass: the cells holding a mark, the rows, the spans to drop, the pictures dropped, what is refused."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text = text
        # the parser counts lines by "\n" alone (splitlines would also split on \r, \x0c,   …)
        self.lines = [0] + [at + 1 for at, ch in enumerate(text) if ch == "\n"]
        self.cells, self.slots, self.drops, self.pictures, self.refused = [], [], [], set(), []
        self.loose = []                                   # text outside every cell
        self.rows = []                                    # {"open": end of <tr …>, "end", "cells": [attrs + mark]}
        self.head = None                                  # the end of <head …>
        self.in_style = False
        self.feed(text)
        self.close()
        self._close_row(len(text))

    def _at(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def _close_row(self, at):
        if self.rows and self.rows[-1]["end"] is None:
            self.rows[-1]["end"] = at

    def _attrs(self, tag, attrs):
        start = self._at()
        end = start + len(self.get_starttag_text() or "")
        named = {name.lower(): value or "" for name, value in attrs}
        if tag in REFUSED_TAGS:
            self.refused.append("a <%s> runs or fetches outside the file" % tag)
        for name in named:
            if name.startswith("on"):
                self.refused.append("<%s %s=…> runs a script" % (tag, name))
        if (tag == "link" and named.get("rel", "").lower() in HOUSEKEEPING_RELS) or (
                tag == "meta" and ("charset" in named or named.get("http-equiv", "").lower() == "content-type")):
            self.drops.append((start, end))
            return
        if tag in PICTURE_TAGS and LOCAL_FILE.match(named.get("src", "")):
            self.drops.append((start, end))
            self.pictures.add(named.get("src"))
            return
        for name in REFERENCE_ATTRS:
            if OUTSIDE.match(named.get(name, "")):
                self.refused.append("<%s %s=\"%s\"> is fetched from outside the file" % (tag, name, named[name][:80]))
        for found in CSS_URL.findall(named.get("style", "")):
            self.refused.append("<%s style=…url(%s)> is fetched from outside the file" % (tag, found[:80]))
        return end, named

    def handle_starttag(self, tag, attrs):
        read_ = self._attrs(tag, attrs)
        if tag == "style":
            self.in_style = True
        if tag == "head" and read_:
            self.head = read_[0]
        if tag == "tr" and read_:
            self._close_row(self._at())
            self.rows.append({"open": read_[0], "end": None, "cells": []})
        if tag in CELLS and read_:
            end, named = read_
            row = self.rows[-1] if self.rows and self.rows[-1]["end"] is None else None
            if row is not None:
                row["cells"].append({"class": named.get("class"), "style": named.get("style"),
                                     "colspan": named.get("colspan"), "mark": None})
            self.cells.append({"start": end, "text": [], "row": row})

    def handle_startendtag(self, tag, attrs):
        self._attrs(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
        if tag == "tr":
            at = self._at()
            self._close_row(self.text.find(">", at) + 1 if self.text.find(">", at) >= 0 else at)
        if tag == "table":
            self._close_row(self._at())
        if tag in CELLS and self.cells:
            cell = self.cells.pop()
            said = _flat("".join(cell["text"]))
            found = MARK.findall(said)
            if found and MARK.fullmatch(said):
                self.slots.append((cell["start"], self._at(), found[0]))
                if cell["row"] is not None:
                    cell["row"]["cells"][-1]["mark"] = found[0]
            elif found:
                self.refused.append("{{%s}} stands alone in its cell - the cell also says %r"
                                    % (found[0], MARK.sub("", said).strip()[:40]))

    def handle_data(self, data):
        if self.in_style:
            for found in CSS_URL.findall(data):
                self.refused.append("a style's url(%s) is fetched from outside the file" % found[:80])
            return
        (self.cells[-1]["text"] if self.cells else self.loose).append(data)

    def sample(self):
        """The sample block under {{table:yield_by}}'s row, or None: {"span": (from, to), "colspan": n, "lent":
        {kind: {"name": attrs, "value": attrs}}} - the head (the mark's row) and each sampled kind."""
        for at, row in enumerate(self.rows):
            if not any(cell["mark"] == SAMPLE_TABLE for cell in row["cells"]):
                continue
            taken = [(SAMPLE_HEAD, row)]
            for below in self.rows[at + 1:]:
                kind = below["cells"][0]["mark"] if below["cells"] else None
                if kind not in SAMPLE_MARKS or kind in {k for k, _r in taken}:
                    break
                taken.append((kind, below))
            if len(taken) == 1:
                return None
            lent = {kind: {"name": _lent(r["cells"][0]), "value": _lent(r["cells"][min(1, len(r["cells"]) - 1)])}
                    for kind, r in taken}
            span = sum(int(c["colspan"]) if str(c["colspan"] or "").isdigit() else 1 for c in row["cells"])
            return {"span": (row["open"], taken[-1][1]["end"]), "colspan": span, "lent": lent}
        return None


def _lent(cell):
    return {name: cell[name] for name in ("class", "style") if cell.get(name)}


def read(text):
    return _Reader(text)


def known_marks(spec) -> set:
    from chain import report_shape

    texts = {str(slot.get("slot")) for slot in (spec or {}).get("layout") or ()
             if isinstance(slot, dict) and slot.get("kind") == "text"}
    return set(FIXED_MARKS) | {TABLE_PREFIX + fill for fill in report_shape.TABLE_FILLS} | texts


def _sampled(read_, sample):
    return [(start, end, name) for start, end, name in read_.slots
            if sample and sample["span"][0] <= start < sample["span"][1]]


def refusal(spec):
    """Why this template cannot stand, or None - the first reason, said with the mark or the tag."""
    template = (spec or {}).get("template")
    if template is None or (isinstance(template, str) and not template.strip()):
        return None
    if not isinstance(template, str):
        return "derive.report.template is the HTML Excel puts on the clipboard, got %r" % (type(template).__name__,)
    read_ = read(template)
    if read_.refused:
        return "derive.report.template: %s" % read_.refused[0]
    loose = MARK.findall(_flat("".join(read_.loose)))
    if loose:
        return "derive.report.template: {{%s}} is outside a table cell - put it in a cell of its own" % loose[0]
    sampled = _sampled(read_, read_.sample())
    stray = [name for slot in read_.slots if slot not in sampled for name in [slot[2]] if name in SAMPLE_MARKS]
    if stray:
        return ("derive.report.template: {{%s}} is a sample row's first cell - put it in a row right under "
                "{{%s}}'s row" % (stray[0], SAMPLE_TABLE))
    known = known_marks(spec)
    unknown = sorted({name for slot in read_.slots if slot not in sampled for name in [slot[2]]} - known)
    if unknown:
        return ("derive.report.template: {{%s}} is not a mark this report fills - one of %s"
                % (unknown[0], " · ".join("{{%s}}" % mark for mark in sorted(known))))
    placed = {name for _s, _e, name in read_.slots}
    from chain import report_loop

    missing = [slot for slot in report_loop.text_slots(spec) if slot not in placed]
    if missing:
        return ("derive.report.template has no {{%s}} - the layout's text slot %s would be written nowhere"
                % (missing[0], missing[0]))
    return None


def note(spec):
    """What the template loses on the way - its pictures - or None."""
    template = (spec or {}).get("template")
    if not isinstance(template, str) or not template.strip():
        return None
    pictures = read(template).pictures
    return "derive.report.template: " + DROPPED_SAID % len(pictures) if pictures else None


def lent(template):
    """The sample block's formats ({kind: {"name", "value"}}), or None - what `report_html` dresses the summary in."""
    sample = read(template).sample() if isinstance(template, str) else None
    return sample["lent"] if sample else None


def fill(template, contents) -> str:
    """The template with each mark cell's inside replaced by `contents[mark]` (HTML) - the sample block's rows by one
    cell holding {{table:yield_by}}'s - its dropped spans gone and one utf-8 charset line after <head>."""
    read_ = read(template)
    sample = read_.sample()
    sampled = _sampled(read_, sample)
    edits = [(start, end, contents.get(name, "")) for start, end, name in read_.slots if (start, end, name)
             not in sampled]
    if sample:
        edits.append(sample["span"] + ('<td colspan="%d">%s</td></tr>' % (sample["colspan"],
                                                                         contents.get(SAMPLE_TABLE, "")),))
    edits += [(start, end, "") for start, end in read_.drops if not any(s <= start < e for s, e, _n in edits)]
    head = read_.head if read_.head is not None else 0
    edits.append((head, head, CHARSET))
    out, at = [], 0
    for start, end, said in sorted(edits, key=lambda edit: (edit[0], edit[1])):
        out.append(template[at:start])
        out.append(said)
        at = end
    out.append(template[at:])
    return "".join(out)
