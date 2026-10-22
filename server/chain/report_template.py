"""The report's company template (owner 10-23 «회사 양식 엑셀 · 클립보드에 html»): the HTML Excel puts on the
clipboard, pasted into `derive.report.template` as it is. A cell whose text is one mark - {{<text slot>}} ·
{{table:<fill>}} · {{images}} · {{meta}} · {{title}} - has its inside replaced; every other byte of the template
stays, its mso styles included.

What the save refuses: a script or a frame · an on… attribute · a reference outside the file (http · https · file ·
//, a CSS url) · a mark this report does not fill · a text slot of the layout the template has no mark for · a mark
not alone in its cell or outside a cell. What is dropped on the way (lead 10-23): Excel's housekeeping links and the
pictures it puts on the clipboard as local file paths - the file fetches nothing."""
from __future__ import annotations

import html.parser
import re

MARK = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
#: The marks every report can fill; a table mark is TABLE_PREFIX + one of `report_shape.TABLE_FILLS`.
FIXED_MARKS = ("title", "meta", "images")
TABLE_PREFIX = "table:"
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


def _flat(text):
    return " ".join(text.replace("\xa0", " ").split())


class _Reader(html.parser.HTMLParser):
    """One pass: the cells holding a mark, the spans to drop, the pictures dropped, what is refused."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text = text
        # the parser counts lines by "\n" alone (splitlines would also split on \r, \x0c,   …)
        self.lines = [0] + [at + 1 for at, ch in enumerate(text) if ch == "\n"]
        self.cells, self.slots, self.drops, self.pictures, self.refused = [], [], [], set(), []
        self.loose = []                                   # text outside every cell
        self.in_style = False
        self.feed(text)
        self.close()

    def _at(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def _attrs(self, tag, attrs):
        start = self._at()
        end = start + len(self.get_starttag_text() or "")
        named = {name.lower(): value or "" for name, value in attrs}
        if tag in REFUSED_TAGS:
            self.refused.append("a <%s> runs or fetches outside the file" % tag)
        for name in named:
            if name.startswith("on"):
                self.refused.append("<%s %s=…> runs a script" % (tag, name))
        if tag == "link" and named.get("rel", "").lower() in HOUSEKEEPING_RELS:
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
        return end

    def handle_starttag(self, tag, attrs):
        end = self._attrs(tag, attrs)
        if tag == "style":
            self.in_style = True
        if tag in CELLS and end is not None:
            self.cells.append({"start": end, "text": []})

    def handle_startendtag(self, tag, attrs):
        self._attrs(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
        if tag in CELLS and self.cells:
            cell = self.cells.pop()
            said = _flat("".join(cell["text"]))
            found = MARK.findall(said)
            if found and MARK.fullmatch(said):
                self.slots.append((cell["start"], self._at(), found[0]))
            elif found:
                self.refused.append("{{%s}} stands alone in its cell - the cell also says %r"
                                    % (found[0], MARK.sub("", said).strip()[:40]))

    def handle_data(self, data):
        if self.in_style:
            for found in CSS_URL.findall(data):
                self.refused.append("a style's url(%s) is fetched from outside the file" % found[:80])
            return
        (self.cells[-1]["text"] if self.cells else self.loose).append(data)


def read(text):
    return _Reader(text)


def known_marks(spec) -> set:
    from chain import report_shape

    texts = {str(slot.get("slot")) for slot in (spec or {}).get("layout") or ()
             if isinstance(slot, dict) and slot.get("kind") == "text"}
    return set(FIXED_MARKS) | {TABLE_PREFIX + fill for fill in report_shape.TABLE_FILLS} | texts


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
    known = known_marks(spec)
    unknown = sorted({name for _s, _e, name in read_.slots} - known)
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


def fill(template, contents) -> str:
    """The template with each mark cell's inside replaced by `contents[mark]` (HTML), its dropped spans gone."""
    read_ = read(template)
    edits = sorted([(start, end, contents.get(name, "")) for start, end, name in read_.slots]
                   + [(start, end, "") for start, end in read_.drops
                      if not any(s <= start < e for s, e, _n in read_.slots)])
    out, at = [], 0
    for start, end, said in edits:
        out.append(template[at:start])
        out.append(said)
        at = end
    out.append(template[at:])
    return "".join(out)
