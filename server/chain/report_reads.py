"""The six reads the AI report's model calls by one JSON line (owner 10-22: the model writes no SQL - it reads the
conditions, picks wafers and calls; the numbers are these functions'). Every table and column comes from the report's
declaration (`derive.report`, `report_shape`); every read passes the grid read path (`grid_read.narrowed_table_query`)
with the grid filter's own conditions. Each answers {"context": <the model's short text>, "html": <the whole table>}.

  conditions(keyword?)       condition value -> wafers; with a keyword, the wafers whose condition holds it
  yield_by(wafers, by?)      rows = items, columns = wafers by time (or condition values), cell «x% (F/N)»
  pareto(wafers)             items by fail chips, cumulative share
  trend(wafers, items)       each item's share in time order, first · last · least · most
  images(wafers, items?)     defect images of this evaluation's wafers where the item occurred - embedded, not told
  compare(sets)              the compare sets' wafers beside this evaluation's, the same table

A wafer is its key - one column or several (`report_shape.wafer_columns`), said to the model as the parts joined
by «/»."""
from __future__ import annotations

import base64
import json

from chain import report_shape

#: The most rows one read takes - past it the read is refused by name (narrow the wafers).
READ_ROW_CAP = 100_000
#: How many items a pareto tells the model; the HTML has every one.
PARETO_TOLD = 10
WAFER_SEP = "/"


class ReadRefused(ValueError):
    """A call the reads cannot answer - said back to the model as the reason."""


def label(wafer) -> str:
    return WAFER_SEP.join("" if part is None else str(part) for part in wafer)


def _model(table):
    from database import models

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        raise ReadRefused("table %r has no model in this process" % table)
    return model


def _equals_any(column, values):
    """One column's grid filter: equal to any of `values` (equals joined by OR)."""
    return {"filterType": "text", "operator": "OR",
            "conditions": [{"filterType": "text", "type": "equals", "filter": value} for value in values]}


def _rows(db, role, columns, wafers=None, where=None):
    """`columns` of the role's table for these wafers (None: every row) - through the grid read path. Rows past
    READ_ROW_CAP are refused."""
    import grid_read

    table = role["table"]
    model = _model(table)
    filters = dict(where or {})
    keys = report_shape.wafer_columns(role.get("wafer", role.get("key")))
    if wafers is not None:
        if not wafers:
            return []
        for at, column in enumerate(keys):
            filters[column] = _equals_any(column, sorted({str(w[at]) for w in wafers if w[at] is not None}))
    query, _key = grid_read.narrowed_table_query(db, table, model, filters=json.dumps(filters) if filters else None)
    found = query.with_entities(*(getattr(model, c) for c in columns)).limit(READ_ROW_CAP + 1).all()
    if len(found) > READ_ROW_CAP:
        raise ReadRefused("%s holds over %d rows for these wafers - pick fewer" % (table, READ_ROW_CAP))
    if wafers is None:
        return [tuple(row) for row in found]
    wanted = {tuple(None if p is None else str(p) for p in w) for w in wafers}
    width = len(keys)
    return [tuple(row) for row in found
            if tuple(None if p is None else str(p) for p in row[:width]) in wanted]


class Report:
    """One report's reads - its declaration, this evaluation, and what it has read so far."""

    def __init__(self, db, spec, evaluation):
        self.db, self.spec, self.evaluation = db, spec, evaluation
        role = spec["wafer"]
        self.keys = report_shape.wafer_columns(role["key"])
        self.conditions_at = [c for c in report_shape.wafer_columns(role.get("conditions")) if c]
        self.wafers = {}                         # wafer -> {"time", "lot", "evaluation", "conditions": {col: value}}
        self.groups = {}                         # group name -> [wafer, ...] - this evaluation first
        here = self._wafer_rows({role["evaluation"]: _equals_any(role["evaluation"], [evaluation])}
                                if role.get("evaluation") else None)
        self.groups[evaluation] = self._ordered(here)
        self.embedded = {}                       # what images() embedded - for the HTML only

    # ---- the wafer table -------------------------------------------------------------------------------------
    def _wafer_rows(self, where):
        role = self.spec["wafer"]
        extra = [role.get(cell) for cell in ("time", "lot", "evaluation")]
        columns = self.keys + [c for c in extra if c] + self.conditions_at
        out = []
        for row in _rows(self.db, role, columns, where=where):
            wafer = tuple(None if p is None else str(p) for p in row[:len(self.keys)])
            values = dict(zip(columns, row))
            self.wafers[wafer] = {"time": values.get(role.get("time")), "lot": values.get(role.get("lot")),
                                  "evaluation": values.get(role.get("evaluation")),
                                  "conditions": {c: values.get(c) for c in self.conditions_at}}
            out.append(wafer)
        return out

    def _ordered(self, wafers):
        """By time, a wafer without one last, then by its key."""
        return sorted(set(wafers), key=lambda w: (self.wafers[w]["time"] is None, str(self.wafers[w]["time"] or ""),
                                                  label(w)))

    def pick(self, said):
        """The wafers a call names: labels, or {"where": {condition: value}} over this evaluation, or all of it."""
        here = self.groups[self.evaluation]
        if said in (None, "all", []):
            return list(here)
        if isinstance(said, dict):
            where = said.get("where") or said
            unknown = [c for c in where if c not in self.conditions_at]
            if unknown:
                raise ReadRefused("%s is not a condition - one of %s" % (", ".join(unknown), ", ".join(self.conditions_at)))
            return [w for w in here if all(str(self.wafers[w]["conditions"].get(c)) == str(v) for c, v in where.items())]
        if not isinstance(said, list):
            raise ReadRefused("wafers is a list of wafer names, «all», or {\"where\": {condition: value}}")
        by_label = {label(w): w for w in self.wafers}
        unknown = [str(each) for each in said if str(each) not in by_label]
        if unknown:
            raise ReadRefused("%s is not a wafer of this report" % ", ".join(unknown[:5]))
        return [by_label[str(each)] for each in said]

    # ---- the numbers --------------------------------------------------------------------------------------------
    def _fail(self, wafers):
        role = self.spec["fail"]
        width = len(self.keys)
        out = {}
        for row in _rows(self.db, role, report_shape.wafer_columns(role["wafer"]) + [role["item"], role["chips"]], wafers):
            wafer = tuple(None if p is None else str(p) for p in row[:width])
            item, chips = row[width], row[width + 1]
            if item is None or chips is None:
                continue
            out[(wafer, str(item))] = out.get((wafer, str(item)), 0) + float(chips)
        return out

    def _total(self, wafers):
        """wafer -> its total chips; a wafer whose rows say two totals is left out, named."""
        role = self.spec["total"]
        width = len(self.keys)
        seen = {}
        for row in _rows(self.db, role, report_shape.wafer_columns(role["wafer"]) + [role["chips"]], wafers):
            if row[width] is not None:
                seen.setdefault(tuple(None if p is None else str(p) for p in row[:width]), set()).add(float(row[width]))
        return {w: next(iter(v)) for w, v in seen.items() if len(v) == 1}, sorted(label(w) for w, v in seen.items()
                                                                                   if len(v) > 1)

    def _items(self, fail):
        chosen = [str(item) for item in self.spec.get("rows") or ()]
        if chosen:
            return chosen
        totals = {}
        for (_w, item), chips in fail.items():
            totals[item] = totals.get(item, 0) + chips
        return sorted(totals, key=lambda item: (-totals[item], item))

    def cell(self, fail_chips, total):
        digits = self.spec.get("digits", 1)
        if not total:
            return "— (%s/—)" % _count(fail_chips)
        return "%.*f%% (%s/%s)" % (digits, 100.0 * fail_chips / total, _count(fail_chips), _count(total))

    # ---- the six ------------------------------------------------------------------------------------------------
    def conditions(self, keyword=None):
        here = self.groups[self.evaluation]
        if keyword not in (None, ""):
            word = str(keyword).lower()
            found = [w for w in here if any(word in str(v).lower() for v in self.wafers[w]["conditions"].values())]
            return {"context": "wafers whose condition holds %r: %s" % (keyword, ", ".join(map(label, found)) or "none"),
                    "html": None, "wafers": found}
        folded = {c: {} for c in self.conditions_at}
        for w in here:
            for c, v in self.wafers[w]["conditions"].items():
                folded[c][str(v)] = folded[c].get(str(v), 0) + 1
        lines = ["%d wafers in %s" % (len(here), self.evaluation)] + [
            "%s: %s" % (c, ", ".join("%s %d" % (v, n) for v, n in sorted(values.items(), key=lambda kv: -kv[1])))
            for c, values in folded.items()]
        return {"context": "\n".join(lines), "html": None}

    def yield_by(self, wafers=None, by=None):
        groups = self._column_groups(self.pick(wafers), by)
        everyone = [w for _name, columns in groups for _col, members in columns for w in members]
        fail = self._fail(everyone)
        totals, differs = self._total(everyone)
        items = self._items(fail)
        header = [(name, [col for col, _m in columns]) for name, columns in groups]
        rows = []
        for item in items:
            cells = []
            for _name, columns in groups:
                for _col, members in columns:
                    f = sum(fail.get((w, item), 0) for w in members)
                    n = sum(totals.get(w, 0) for w in members if w in totals)
                    cells.append(self.cell(f, n))
            rows.append((item, cells))
        table = {"groups": header, "rows": rows, "left_out": differs}
        return {"context": _table_text(table), "html": table}

    def _column_groups(self, wafers, by):
        """[(group name, [(column label, [wafer, ...]), ...])] - this evaluation's picked wafers, then each compare
        set; a column a wafer, or a condition value when `by` names one."""
        picked = set(wafers)
        out = []
        for name, members in self.groups.items():
            members = [w for w in members if name != self.evaluation or w in picked]
            if by:
                if by not in self.conditions_at:
                    raise ReadRefused("%r is not a condition - one of %s" % (by, ", ".join(self.conditions_at)))
                values = {}
                for w in members:
                    values.setdefault(str(self.wafers[w]["conditions"].get(by)), []).append(w)
                out.append((name, sorted(values.items())))
            else:
                out.append((name, [(label(w), [w]) for w in members]))
        return out

    def pareto(self, wafers=None):
        picked = self.pick(wafers)
        fail = self._fail(picked)
        totals = {}
        for (_w, item), chips in fail.items():
            totals[item] = totals.get(item, 0) + chips
        whole = sum(totals.values()) or 1
        rows, running = [], 0
        for item in sorted(totals, key=lambda i: (-totals[i], i)):
            running += totals[item]
            rows.append((item, _count(totals[item]), "%.1f%%" % (100.0 * running / whole)))
        told = rows[:PARETO_TOLD]
        more = len(rows) - len(told)
        text = "\n".join("%s %s (cum %s)" % row for row in told) + ("\n... %d more item(s)" % more if more else "")
        return {"context": text or "no fail chips", "html": {"columns": ["item", "fail chips", "cumulative"], "rows": rows}}

    def trend(self, wafers=None, items=None):
        picked = self._ordered(self.pick(wafers))
        fail = self._fail(picked)
        totals, _differs = self._total(picked)
        names = [str(i) for i in items] if items else self._items(fail)
        lines, rows = [], []
        for item in names:
            shares = [(label(w), 100.0 * fail.get((w, item), 0) / totals[w]) for w in picked if totals.get(w)]
            if not shares:
                continue
            values = [s for _l, s in shares]
            lines.append("%s: first %.2f%% last %.2f%% least %.2f%% most %.2f%% over %d wafers"
                         % (item, values[0], values[-1], min(values), max(values), len(values)))
            rows.append((item, shares))
        return {"context": "\n".join(lines) or "no item has a total to share", "html": {"series": rows}}

    def images(self, wafers=None, items=None):
        import image_sources

        role = self.spec.get("images")
        if not role:
            raise ReadRefused("this report declares no images")
        picked = self.pick(wafers)
        outside = [label(w) for w in picked if w not in set(self.groups[self.evaluation])]
        if outside:
            raise ReadRefused("images are this evaluation's only - %s is not" % ", ".join(outside[:5]))
        fail = self._fail(picked)
        occurred = {(w, item) for (w, item), chips in fail.items() if chips > 0}
        wanted = {str(i) for i in items} if items else None
        width = len(self.keys)
        per_item, px = role.get("per_item", 3), role.get("px", 320)
        chosen, counts = {}, {}
        for row in _rows(self.db, role, report_shape.wafer_columns(role["wafer"]) + [role["item"], role["image"]], picked):
            wafer = tuple(None if p is None else str(p) for p in row[:width])
            item, ref = str(row[width]), row[width + 1]
            if (wafer, item) not in occurred or (wanted and item not in wanted) or not ref:
                continue
            if counts.get(item, 0) >= per_item:
                continue
            try:
                answer = image_sources.shrink(image_sources.resolve(ref), px)
            except image_sources.ImageRefused as refused:
                chosen.setdefault(item, []).append({"wafer": label(wafer), "refused": str(refused)})
                continue
            data, media = _image_bytes(answer)
            chosen.setdefault(item, []).append({"wafer": label(wafer),
                                                "src": "data:%s;base64,%s" % (media, base64.b64encode(data).decode())})
            counts[item] = counts.get(item, 0) + 1
        self.embedded.update(chosen)
        text = ", ".join("%s %d" % (item, n) for item, n in sorted(counts.items())) or "no image of an occurred defect"
        return {"context": "images picked: " + text, "html": chosen}

    def compare(self, sets=None):
        role = self.spec.get("sets")
        names = [str(s) for s in (sets or (role or {}).get(report_shape.SETS_DEFAULT) or ())]
        if not names:
            raise ReadRefused("no compare set named - and this report declares no default")
        if not role:
            raise ReadRefused("this report declares no compare set table")
        found = _rows(self.db, role, [role["name"], role["member"], role["kind"]],
                      where={role["name"]: _equals_any(role["name"], names)})
        wafer = self.spec["wafer"]
        lines = []
        for name in names:
            members = [(str(m), str(k)) for n, m, k in found if str(n) == name]
            if not members:
                lines.append("%s: no member" % name)
                continue
            wafers = []
            # each kind the declaration names picks members by the wafer column of the same role (sets.kinds)
            for by, said in (role.get(report_shape.SETS_KINDS) or {}).items():
                picked = [m for m, k in members if k == str(said)]
                if picked and wafer.get(by):
                    wafers += self._wafer_rows({wafer[by]: _equals_any(wafer[by], picked)})
            self.groups[name] = self._ordered(wafers)
            lines.append("%s: %d wafers (%s)" % (name, len(self.groups[name]), ", ".join(m for m, _k in members)))
        return {"context": "\n".join(lines), "html": None}


READS = ("conditions", "yield_by", "pareto", "trend", "images", "compare")


def _count(value):
    return str(int(value)) if float(value).is_integer() else "%g" % value


def _image_bytes(answer):
    if answer[0] == "file":
        import mimetypes

        with open(answer[1], "rb") as handle:
            return handle.read(), mimetypes.guess_type(answer[1])[0] or "application/octet-stream"
    return answer[1], answer[2]


def _table_text(table):
    """The summary table as the model reads it: a head line per group, then a line per item - the same «x% (F/N)»."""
    lines = []
    for name, columns in table["groups"]:
        lines.append("[%s] %s" % (name, " | ".join(columns)))
    for item, cells in table["rows"]:
        lines.append("%s | %s" % (item, " | ".join(cells)))
    if table.get("left_out"):
        lines.append("left out (their rows say two totals): %s" % ", ".join(table["left_out"]))
    return "\n".join(lines)
