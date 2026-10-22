"""The six reads the AI report's model calls by one JSON line (owner 10-22: the model writes no SQL - it reads the
conditions, picks wafers and calls; the numbers are these functions'). Every table and column comes from the report's
declaration (`derive.report`, `report_shape`); every read passes the grid read path (`grid_read.narrowed_table_query`)
with the grid filter's own conditions. Each answers {"context": <the model's short text>, "html": <the whole table>}.

  conditions(keyword?)       condition value -> wafers; with a keyword, the wafers whose condition holds it
  yield_by(wafers, by?)      rows = items, columns = wafers by time (or condition values), cell «x% (F/N)» read
                             off the owner's summary table - wafers in one column add their F and N
  pareto(wafers)             items by fail chips added over the wafers, cumulative share
  trend(wafers, items)       each item's share in time order, first · last · least · most
  images(wafers, items?)     defect images of this evaluation's wafers where the item occurred - embedded, not told
  compare(sets)              the compare sets' wafers beside this evaluation's, the same table

A wafer is its key - one column or several (`report_shape.wafer_columns`), said to the model as the parts joined
by «/»."""
from __future__ import annotations

import base64
import datetime
import json

from chain import report_shape

#: The most rows one read takes - past it the read is refused by name (narrow the wafers).
READ_ROW_CAP = 100_000
#: How many items a pareto tells the model; the HTML has every one.
PARETO_TOLD = 10
WAFER_SEP = "/"
#: The head of a control group's name - «control <evaluation>».
CONTROL = "control"
#: The summary cells a row is read by, in order.
SUMMARY_CELLS = ("fail", "total", "rate")
#: Why a wafer's item is left out of a table.
LEFT_OUT = "two summary rows for one wafer and item"


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


def _rows(db, role, columns, wafers=None, where=None, newest=None):
    """`columns` of the role's table for these wafers (None: every row) - through the grid read path. Rows past
    READ_ROW_CAP are refused - or, with `newest` (a column), the newest READ_ROW_CAP by it are the answer."""
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
    if newest:
        query = query.order_by(getattr(model, newest).desc())
    found = query.with_entities(*(getattr(model, c) for c in columns)).limit(READ_ROW_CAP + 1).all()
    if newest:
        found = found[:READ_ROW_CAP]
    elif len(found) > READ_ROW_CAP:
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
        self._candidates = None                  # the recent evaluations, read once (`_recent`)
        self.used = {}                           # wafer -> the group it stood in, for every wafer a read answered on

    # ---- the wafer table -------------------------------------------------------------------------------------
    def _wafer_rows(self, where, newest=False):
        role = self.spec["wafer"]
        extra = [role.get(cell) for cell in ("time", "lot", "evaluation")]
        columns = self.keys + [c for c in extra if c] + self.conditions_at
        out = []
        for row in _rows(self.db, role, columns, where=where, newest=role.get("time") if newest else None):
            wafer = tuple(None if p is None else str(p) for p in row[:len(self.keys)])
            values = dict(zip(columns, row))
            self.wafers[wafer] = {"time": values.get(role.get("time")), "lot": values.get(role.get("lot")),
                                  "evaluation": values.get(role.get("evaluation")),
                                  "conditions": {c: values.get(c) for c in self.conditions_at}}
            out.append(wafer)
        self.named = {}                          # the name a model says -> the wafers it names
        for wafer in self.wafers:
            self.named.setdefault(label(wafer), []).append(wafer)
        # names two key spellings share (lot «A/B» + «1», «A» + «B/1») - counted once per list, for the step record
        self.overlaps = {name: wafers for name, wafers in self.named.items() if len(wafers) > 1}
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
        unknown = [str(each) for each in said if str(each) not in self.named]
        if unknown:
            raise ReadRefused("%s is not a wafer of this report" % ", ".join(unknown[:5]))
        for each in said:
            if str(each) in self.overlaps:
                raise ReadRefused("%s names two wafers - %s" % (each, " · ".join(
                    "(%s)" % ", ".join("" if p is None else p for p in w) for w in self.overlaps[str(each)])))
        return [self.named[str(each)][0] for each in said]

    # ---- the numbers -----------------------------------------------------------------------------------------
    def _summary(self, wafers):
        """(wafer, item) -> {"fail", "total", "rate"} as the owner's summary table holds them (owner 10-22: the
        product does not make a wafer's value again) - one row a pair; a pair two rows say is left out, named."""
        role = self.spec["summary"]
        width = len(self.keys)
        cells = [cell for cell in SUMMARY_CELLS if role.get(cell)]
        found, twice = {}, set()
        for row in _rows(self.db, role, report_shape.wafer_columns(role["wafer"]) + [role["item"]]
                         + [role[cell] for cell in cells], wafers):
            if row[width] is None:
                continue
            pair = (tuple(None if p is None else str(p) for p in row[:width]), str(row[width]))
            if pair in found:
                twice.add(pair)
            found[pair] = {cell: None if value is None else float(value) for cell, value in zip(cells, row[width + 1:])}
        for pair in twice:
            del found[pair]
        return found, sorted("%s %s" % (label(wafer), item) for wafer, item in twice)

    def _summed(self, rows):
        """Several wafers' rows of one item as one: their F and N added - counting only, so a summary that holds
        a rate alone cannot be summed (lead 10-22)."""
        if not self.spec["summary"].get("fail"):
            raise ReadRefused("several wafers in one column need derive.report.summary.fail and total - "
                              "this summary holds a rate only")
        rows = [row for row in rows if row]
        return {"fail": sum(row.get("fail") or 0 for row in rows),
                "total": sum(row.get("total") or 0 for row in rows)} if rows else None

    def _items(self, found):
        chosen = [str(item) for item in self.spec.get("rows") or ()]
        if chosen:
            return chosen
        if not self.spec["summary"].get("fail"):
            return sorted({item for _w, item in found})
        totals = {}
        for (_w, item), row in found.items():
            totals[item] = totals.get(item, 0) + (row.get("fail") or 0)
        return sorted(totals, key=lambda item: (-totals[item], item))

    def share(self, row):
        """A row's percent: its rate over rate_scale, or F/N when it holds no rate; None when it says neither."""
        if not row:
            return None
        if row.get("rate") is not None:
            return 100.0 * row["rate"] / self.spec["summary"][report_shape.RATE_SCALE]
        if row.get("fail") is not None and row.get("total"):
            return 100.0 * row["fail"] / row["total"]
        return None

    def cell(self, row):
        """«x% (F/N)» - «x%» when the row holds a rate alone, «—» for no row."""
        if not row:
            return "—"
        counts = ("(%s/%s)" % (_count(row["fail"]), _count(row["total"]))
                  if row.get("fail") is not None and row.get("total") is not None else "")
        share = self.share(row)
        said = "—" if share is None else "%.*f%%" % (self.spec.get("digits", 1), share)
        return ("%s %s" % (said, counts)).strip()

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
        for name, columns in groups:
            self._use(name, [w for _col, members in columns for w in members])
        found, twice = self._summary(everyone)
        items = self._items(found)
        header = [(name, [col for col, _m in columns]) for name, columns in groups]
        rows = []
        for item in items:
            cells = []
            for _name, columns in groups:
                for _col, members in columns:
                    row = (found.get((members[0], item)) if len(members) == 1
                           else self._summed([found.get((w, item)) for w in members]))
                    cells.append(self.cell(row))
            rows.append((item, cells))
        table = {"groups": header, "rows": rows, "left_out": twice}
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

    def _use(self, group, wafers):
        for wafer in wafers:
            self.used.setdefault(wafer, group)

    def pareto(self, wafers=None):
        picked = self.pick(wafers)
        self._use(self.evaluation, picked)
        if not self.spec["summary"].get("fail"):
            raise ReadRefused("a pareto adds fail chips - derive.report.summary.fail is not declared")
        found, _twice = self._summary(picked)
        totals = {}
        for (_w, item), row in found.items():
            totals[item] = totals.get(item, 0) + (row.get("fail") or 0)
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
        """Each item's share wafer by wafer in time order - this evaluation's picked wafers, then every compare set
        and control group beside them (owner 10-23: other lots' trends as a control)."""
        groups = [(self.evaluation, self._ordered(self.pick(wafers)))] + [
            (name, members) for name, members in self.groups.items() if name != self.evaluation]
        for name, members in groups:
            self._use(name, members)
        found, twice = self._summary([w for _name, members in groups for w in members])
        names = [str(i) for i in items] if items else self._items(found)
        lines, rows = [], []
        for item in names:
            cells = []
            for name, members in groups:
                shares = [self.share(found.get((w, item))) for w in members]
                cells += ["" if share is None else "%.2f%%" % share for share in shares]
                said = [share for share in shares if share is not None]
                if said:
                    lines.append("%s%s: first %.2f%% last %.2f%% least %.2f%% most %.2f%% over %d wafers" % (
                        item, "" if name == self.evaluation else " [%s]" % name, said[0], said[-1], min(said),
                        max(said), len(said)))
            rows.append((item, cells))
        table = {"groups": [(name, [label(w) for w in members]) for name, members in groups], "rows": rows,
                 "left_out": twice}
        return {"context": "\n".join(lines) or "no item has a share", "html": table}

    def images(self, wafers=None, items=None):
        import image_sources

        role = self.spec.get("images")
        if not role:
            raise ReadRefused("this report declares no images")
        picked = self.pick(wafers)
        outside = [label(w) for w in picked if w not in set(self.groups[self.evaluation])]
        if outside:
            raise ReadRefused("images are this evaluation's only - %s is not" % ", ".join(outside[:5]))
        self._use(self.evaluation, picked)
        found, _twice = self._summary(picked)
        said = "fail" if self.spec["summary"].get("fail") else "rate"
        occurred = {pair for pair, row in found.items() if (row.get(said) or 0) > 0}
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

    def _recent(self):
        """{evaluation: {"latest", "wafers"}} - the evaluations before this one's latest wafer, newest first, within
        `control.recent` (days and/or evaluations, both narrowing). Read once, newest wafer rows first."""
        if self._candidates is not None:
            return self._candidates
        role = self.spec["wafer"]
        recent = (self.spec.get("control") or {}).get("recent")
        if not recent:
            raise ReadRefused('candidates need derive.report.control.recent - {"days": <n>} and/or '
                              '{"evaluations": <n>}')
        if not role.get("time") or not role.get("evaluation"):
            raise ReadRefused("candidates need derive.report.wafer.time and evaluation")
        here = [_instant(self.wafers[w]["time"]) for w in self.groups[self.evaluation]]
        here = [at for at in here if at is not None]
        if not here:
            raise ReadRefused("%s's wafers say no time - recent is counted back from its latest" % self.evaluation)
        anchor = max(here)
        by = {}
        for wafer in self._wafer_rows(None, newest=True):
            facts = self.wafers[wafer]
            at, evaluation = _instant(facts["time"]), facts["evaluation"]
            if at is None or evaluation in (None, self.evaluation) or at > anchor:
                continue
            if recent.get("days") and anchor - at > datetime.timedelta(days=recent["days"]):
                continue
            entry = by.setdefault(str(evaluation), {"latest": at, "wafers": []})
            entry["latest"] = max(entry["latest"], at)
            entry["wafers"].append(wafer)
        newest = sorted(by, key=lambda name: (by[name]["latest"], name), reverse=True)
        if recent.get("evaluations"):
            newest = newest[:recent["evaluations"]]
        self._candidates = {name: dict(by[name], wafers=self._ordered(by[name]["wafers"])) for name in newest}
        return self._candidates

    def candidates(self):
        """The recent evaluations a control group may come from - one line each, newest first: name · date · wafers
        · each condition's values with their wafer counts."""
        found = self._recent()
        lines = ["recent evaluations, newest first (%s left out):" % self.evaluation]
        for name, entry in found.items():
            folded = []
            for column in self.conditions_at:
                counts = {}
                for wafer in entry["wafers"]:
                    value = str(self.wafers[wafer]["conditions"].get(column))
                    counts[value] = counts.get(value, 0) + 1
                folded.append("%s %s" % (column, ", ".join("%s %d" % (v, n) for v, n in
                                                           sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))))
            lines.append(" · ".join([name, entry["latest"].date().isoformat(), "%d wafers" % len(entry["wafers"])]
                                    + folded))
        if len(lines) == 1:
            lines.append("none in range")
        return {"context": "\n".join(lines), "html": None}

    def _control(self, evaluations, wafers):
        """Control groups «control <evaluation>» from the recent evaluations - the evaluations named (all their wafers)
        and the wafers named (their evaluations' groups hold only those). Replaces the control picked before."""
        found = self._recent()
        chosen = {}
        for name in [str(e) for e in evaluations or ()]:
            if name == self.evaluation:
                raise ReadRefused("%s is this evaluation - a control comes from another" % name)
            if name not in found:
                raise ReadRefused("%s is not a recent evaluation - candidates() lists them" % name)
            chosen[name] = []
        for said in [str(w) for w in wafers or ()]:
            owner = next((name for name, entry in found.items() for w in entry["wafers"] if label(w) == said), None)
            if owner is None:
                raise ReadRefused("%s is not a wafer of a recent evaluation - candidates() lists them" % said)
            chosen.setdefault(owner, []).append(self.named[said][0])
        most = report_shape.control_limit(self.spec, "max_evaluations")
        if len(chosen) > most:
            raise ReadRefused("%d evaluations - control.max_evaluations is %d" % (len(chosen), most))
        groups = {name: self._ordered(picked or found[name]["wafers"]) for name, picked in chosen.items()}
        total, most = sum(len(members) for members in groups.values()), report_shape.control_limit(
            self.spec, "max_wafers")
        if total > most:
            raise ReadRefused("%d wafers - control.max_wafers is %d; name fewer wafers" % (total, most))
        for name in [n for n in self.groups if n.startswith(CONTROL + " ")]:
            del self.groups[name]
        lines = []
        for name, members in groups.items():
            self.groups["%s %s" % (CONTROL, name)] = members
            lines.append("%s %s: %d wafers (%s)" % (CONTROL, name, len(members), ", ".join(map(label, members[:10]))))
        return lines

    def compare(self, sets=None, evaluations=None, wafers=None):
        """Compare sets the declaration names (sets, or its default) and/or a control group from the recent
        evaluations (evaluations, wafers) - each a group of columns beside this evaluation's in the tables after it."""
        lines = []
        if sets is not None or not (evaluations or wafers):
            lines += self._sets(sets)
        if evaluations or wafers:
            lines += self._control(evaluations, wafers)
        return {"context": "\n".join(lines), "html": None}

    def _sets(self, sets):
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
        return lines


READS = report_shape.READS


def _instant(value):
    """A time cell as a naive UTC instant to compare, or None - a datetime or an ISO string."""
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        value = datetime.datetime(value.year, value.month, value.day)
    if not isinstance(value, datetime.datetime):
        return None
    return value.astimezone(datetime.timezone.utc).replace(tzinfo=None) if value.tzinfo else value


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
        lines.append("left out (%s): %s" % (LEFT_OUT, ", ".join(table["left_out"])))
    return "\n".join(lines)
