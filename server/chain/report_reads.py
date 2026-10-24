"""The six reads the AI report's model calls by one JSON line (owner 10-22: the model writes no SQL - it reads the
conditions, picks wafers and calls; the numbers are these functions'). Every table and column comes from the report's
declaration (`derive.report`, `report_shape`); every read passes the grid read path (`grid_read.narrowed_table_query`)
with the grid filter's own conditions. Each answers {"context": <the model's short text>, "html": <the whole table>}.

  conditions(keyword?)       condition value -> wafers; with a keyword, the wafers whose condition holds it
  yield_by(wafers, by?, rows?) rows = items, columns = wafers (or condition values), cell «x% (F/N)» read
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
import logging

from chain import report_shape

#: the report's reads said on the terminal (owner 10-24 «해결 못하면 로그라도 찍어야 내가 보고 알려주지»)
logger = logging.getLogger("Chain")

#: The most rows one read takes - past it the read is refused by name (narrow the wafers).
READ_ROW_CAP = 100_000
#: How many items a pareto tells the model; the HTML has every one.
PARETO_TOLD = 10
WAFER_SEP = "/"
#: The summary cells a row is read by, in order.
SUMMARY_CELLS = ("fail", "total", "rate")


class ReadRefused(ValueError):
    """A call the reads cannot answer - said back to the model as the reason."""


#: Two values one wafer's condition holds, said together (`Report._long_conditions`).
BOTH = " / "
#: A condition row whose value is blank (owner 10-23 trap wafer: a condition named, its value not written).
EMPTY = "(empty)"


def label(wafer) -> str:
    return WAFER_SEP.join("" if part is None else str(part) for part in wafer)


def _model(table):
    from database import models

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        raise ReadRefused("table %r has no model in this process" % table)
    return model


def _equals_any(column, values):
    """One column's grid filter: equal to any of `values` (equals joined by OR); a None among them (a blank key part,
    `_part`) is the grid's «blank» - blank meets blank (owner 10-24: ops wafers with a blank part had no numbers)."""
    return {"filterType": "text", "operator": "OR",
            "conditions": [{"filterType": "text", "type": "blank"} if value is None else
                           {"filterType": "text", "type": "equals", "filter": value} for value in values]}


def _part(value):
    """A wafer key part as compared - blank (`crud.fold_key_value`: None, «», spaces, NaN) is None, else spelled as a
    key is (`crud.clean_str_value`: 1.0 and «1» one part - lead 10-24, a key column stored as a number in one table and
    as text in another)."""
    from database import crud

    return None if crud.is_blank_key_part(value) else crud.clean_str_value(value)


def _parts(row):
    return tuple(_part(value) for value in row)


def _rows(db, role, columns, wafers=None, where=None, newest=None, keys=None, capped=False, _said=True):
    """`columns` of the role's table for these wafers (None: every row) - through the grid read path. Rows past
    READ_ROW_CAP are refused - or, with `newest` (a column), the newest READ_ROW_CAP by it are the answer. `keys`: the
    key columns `wafers` are spelled in, `columns` first (default the role's own)."""
    import grid_read
    from fastapi import HTTPException

    if capped and wafers is not None and len(wafers) > 1:
        # a picture table is read wafer by wafer, each to the cap - one cap over them all kept the first wafers' rows
        # and dropped every other wafer (owner 10-24 «10000rows 때문에 다른 wf 안나오는거 아니냐»)
        out = [row for wafer in wafers for row in _rows(db, role, columns, [wafer], where, newest, keys, capped, _said=False)]
        logger.warning("[report] read %s: %d rows for %d wafers (wafer by wafer, %d each at most)",
                       role["table"], len(out), len(wafers), READ_ROW_CAP)
        return out
    table = role["table"]
    model = _model(table)
    filters = dict(where or {})
    keys = keys if keys is not None else report_shape.wafer_columns(role.get("wafer", role.get("key")))
    if wafers is not None:
        if not wafers:
            return []
        for at, column in enumerate(keys):
            filters[report_shape.column_of(role, column)] = _equals_any(
                column, sorted({_part(w[at]) for w in wafers}, key=lambda v: (v is not None, v or "")))
    try:
        query, _key = grid_read.narrowed_table_query(db, table, model, filters=json.dumps(filters) if filters else None)
    except HTTPException as refused:                       # a filter the table cannot take, by name (S-71)
        raise ReadRefused(str(refused.detail)) from None
    if newest:
        query = query.order_by(getattr(model, report_shape.column_of(role, newest)).desc())
    found = query.with_entities(*(getattr(model, report_shape.column_of(role, c)) for c in columns)).limit(
        READ_ROW_CAP + 1).all()
    if newest or capped:              # capped: the first READ_ROW_CAP rows, as read (a picture table, owner 10-24)
        found = found[:READ_ROW_CAP]
    elif len(found) > READ_ROW_CAP:
        # what was read, for whom, by which filter, and why the cap - the refusal and the terminal say it whole
        # (owner 10-24 «뭘 했는데 뭐가 안 됐다 · 왜 10만인지 적어야지»)
        said = ("%s: over %d rows (READ_ROW_CAP, the most one report read takes) reading %s for %s wafers%s - "
                "filters %s" % (table, READ_ROW_CAP, ", ".join(map(str, columns)),
                                "every" if wafers is None else len(wafers),
                                " (%s ...)" % ", ".join(map(str, wafers[:3])) if wafers else "",
                                {c: len((f or {}).get("conditions") or [f]) for c, f in filters.items()}))
        logger.warning("[report] read REFUSED %s", said, stack_info=True)
        raise ReadRefused("%s - pick fewer" % said)
    if _said:
        logger.warning("[report] read %s: %d rows for %s wafers%s (filters %s)", table, len(found),
                       "every" if wafers is None else len(wafers),
                       " - cut at %d" % READ_ROW_CAP if len(found) >= READ_ROW_CAP else "", sorted(filters))
    if wafers is None:
        return [tuple(row) for row in found]
    wanted = {_parts(w) for w in wafers}
    width = len(keys)
    return [tuple(row) for row in found
            if _parts(row[:width]) in wanted]


class Report:
    """One report's reads - its declaration, this evaluation, and what it has read so far."""

    def __init__(self, db, spec, evaluation, only=None):
        """`only`: one wafer as {column: value} - its report table's wafer columns (`report_shape.report_key`); this
        report's own group is the wafer table's rows of it (every leg of a wafer keyed by more columns, owner 10-23),
        and its evaluation is theirs."""
        spec = report_shape.matched(spec)        # a role's wafer list by position (owner 10-24)
        self.db, self.spec, self.evaluation = db, spec, evaluation
        role = spec["wafer"]
        self.keys = report_shape.wafer_columns(role["key"])
        self.conditions_at = [c for c in report_shape.wafer_columns(role.get("conditions")) if c]
        self.same_at = [c for c in (spec.get("control") or {}).get(report_shape.CONTROL_SAME) or () if c]
        self.long = spec.get("conditions") if isinstance(spec.get("conditions"), dict) else None
        self.wafers = {}                         # wafer -> {"time", "lot", "evaluation", "conditions": {col: value}}
        self.groups = {}                         # group name -> [wafer, ...] - this evaluation first
        # the report's unit - `keys` unit, or the report table's wafer columns; a candidate is one of those
        self.picked_by = report_shape.unit_columns(spec) or list(only or ())
        self.key_words = report_shape.key_words(spec)
        if only is not None:
            only = {c: _part(v) for c, v in only.items()}
            here = [w for w in self._wafer_rows({c: _equals_any(c, [v]) for c, v in only.items()})
                    if all(dict(zip(self.keys, w)).get(c) == v for c, v in only.items())]
            said = label(tuple(only.values()))
            if not here:
                raise ReadRefused("wafer %s is not in %s" % (said, role["table"]))
            evaluations = sorted({str(self.wafers[w]["evaluation"]) for w in here})
            if len(evaluations) > 1:
                raise ReadRefused("wafer %s is in %d evaluations (%s) - a report is one evaluation's"
                                  % (said, len(evaluations), ", ".join(evaluations)))
            # a wafer role of no evaluation column: the report's own group is named by the wafer
            self.evaluation = evaluation = self.wafers[here[0]]["evaluation"] or said
        else:
            here = self._wafer_rows({role["evaluation"]: _equals_any(role["evaluation"], [evaluation])}
                                    if role.get("evaluation") else None)
        self.groups[evaluation] = self._ordered(here)
        logger.warning("[report] start %s: %d wafers - %s", evaluation, len(here), "; ".join(
            "%s @ %r" % (self.said(w), self.wafers[w]["time"]) for w in self.groups[evaluation]) or "none")
        self.embedded = {}                       # what images() embedded - for the HTML only
        self._candidates = None                  # the recent evaluations, read once (`_recent`)

    # ---- the wafer table -------------------------------------------------------------------------------------
    def _wafer_rows(self, where, newest=False, only_time=False):
        role = self.spec["wafer"]
        extra = [role.get(cell) for cell in ("time", "lot", "evaluation")]
        columns = self.keys + [c for c in extra if c] + self.conditions_at
        columns += [c for c in self.same_at if c not in columns]
        # wafer.exclude (owner 10-24 «무시해야하는 leg 스타일»): a row the gate holds back is no unit - not reported,
        # compared or drawn; judged by the chain's one row gate (`rule_run.gate_misses`, * ? a pattern)
        import chain_bindings
        from chain import rule_run

        gates ={chain_bindings.EXCLUDE_KEY: role.get(chain_bindings.EXCLUDE_KEY) or []}
        gated = [c for c in chain_bindings.gate_columns(gates[chain_bindings.EXCLUDE_KEY]) if c not in columns]
        read = [(_parts(row[:len(self.keys)]), row)
                for row in _rows(self.db, role, columns + gated, where=where,
                                 newest=role.get("time") if newest else None, capped=where is None)
                if not gates[chain_bindings.EXCLUDE_KEY] or not rule_run.gate_misses(
                    gates, dict(zip(columns + gated, row)), role["table"])]
        out = []
        for wafer, row in self._latest(read):
            values = dict(zip(columns, row))
            self.wafers[wafer] = {"time": values.get(role.get("time")), "lot": values.get(role.get("lot")),
                                  "evaluation": values.get(role.get("evaluation")),
                                  "conditions": {c: values.get(c) for c in self.conditions_at},
                                  "same": tuple(values.get(c) for c in self.same_at), "title": None}
            out.append(wafer)
        if self.long and out:
            self._long_conditions(out, only_time=only_time)
        self.named = {}                          # the name a model says -> the wafers it names
        for wafer in self.wafers:
            for name in dict.fromkeys((label(wafer), self.said(wafer))):
                self.named.setdefault(name, []).append(wafer)
        # names two key spellings share (lot «A/B» + «1», «A» + «B/1») - counted once per list, for the step record
        self.overlaps = {name: wafers for name, wafers in self.named.items() if len(wafers) > 1}
        return out

    def said(self, wafer) -> str:
        """A unit as the model, the Evidence and the file read it - each key part by its column's word
        (`report_shape.column_word`: labels.columns, else the column), «WAFER W1 · LEG L1» (owner 10-24: the model
        wrote each leg as a wafer of its own reading «W1/L1»)."""
        return " · ".join("%s %s" % (report_shape.column_word(self.spec, column), "" if part is None else part)
                          for column, part in zip(self.keys, wafer))

    def _units(self, wafers) -> list:
        """A line a report unit (`picked_by`) - its key parts, then its units' other parts (owner 10-24 «wafer W1: legs
        L1, L2»); [] when the unit is the whole key."""
        unit = [self.keys.index(c) for c in self.picked_by if c in self.keys]
        rest = [at for at in range(len(self.keys)) if at not in unit]
        if not unit or not rest:
            return []
        word = lambda at, part: "%s %s" % (report_shape.column_word(self.spec, self.keys[at]), "" if part is None else part)
        by = {}
        for wafer in wafers:
            by.setdefault(tuple(wafer[at] for at in unit), []).append(wafer)
        return ["%s: %s" % (" · ".join(word(at, part) for at, part in zip(unit, key)),
                            ", ".join(" · ".join(word(at, wafer[at]) for at in rest) for wafer in members))
                for key, members in by.items()]

    def _latest(self, read):
        """Each unit's rows of its latest value in every `keys` latest column (owner 10-23 «TKOUT_TIME 도 키에», the
        report from the latest measurement) - read as a time by the one reader, or as its text when one of the unit's
        values is not a time the reader knows (lead 10-24: 20261001123000 · 2026/10/01 · 2026.10.01 sort as text); a
        unit of no value keeps its rows."""
        for column in [c for c in self.keys if report_shape.KEY_LATEST in self.key_words.get(c, ())]:
            at, unit = self.keys.index(column), [self.keys.index(c) for c in self.picked_by]
            said = {}
            for wafer, _row in read:
                if wafer[at] is not None:
                    said.setdefault(tuple(wafer[i] for i in unit), set()).add(wafer[at])
            best = {}
            for mine, values in said.items():
                order = _instant if all(_instant(v) is not None for v in values) else str
                best[mine] = (order, max(order(v) for v in values))
            read = [(wafer, row) for wafer, row in read if tuple(wafer[i] for i in unit) not in best
                    or wafer[at] is not None and best[tuple(wafer[i] for i in unit)][0](wafer[at]) == best[
                        tuple(wafer[i] for i in unit)][1]]
        return read

    def _matched(self, role, columns, wafers, capped=False, where=None):
        """[(wafer, values)] - the role's rows of these wafers, matched by the key columns the role's table has, by name
        (owner 10-23 «키 칸을 리스트로»): a table without some of the wafer key's (a condition of every measurement)
        answers each wafer it matches; `values` are `columns`, then the table's key columns beyond the wafer key."""
        names = report_shape.wafer_columns(role["wafer"])
        shared = [c for c in names if c in self.keys]
        beyond = [c for c in names if c not in self.keys]
        at = [self.keys.index(c) for c in shared]
        by = {}
        for wafer in dict.fromkeys(wafers):                 # a wafer in two groups is read once
            by.setdefault(_parts(wafer[i] for i in at), []).append(wafer)
        out = []
        for row in _rows(self.db, role, shared + columns + beyond, list(by), where=where, keys=shared, capped=capped):
            for wafer in by.get(_parts(row[:len(shared)]), ()):
                out.append((wafer, row[len(shared):]))
        return out

    def _long_conditions(self, wafers, only_time=False):
        """The conditions role's rows of these wafers into their {name: value} - and their time and title, when the
        wafer role names none (the long table's first row's). A wafer with no row keeps {} - the default conditions."""
        role = self.long
        # conditions.time_item: that item's value is the unit's time when the wafer role names no time column
        time_item = None if self.spec["wafer"].get("time") else role.get(report_shape.TIME_ITEM)
        title_item = role.get(report_shape.TITLE_ITEM)
        extra = [c for c in ("time", "title") if role.get(c) and not (c == "time" and time_item)
                 and not (c == "title" and title_item)]
        # only_time: the time_item rows alone, one a wafer - what picking candidates needs (owner 10-24 «10만행 읽을게
        # 없잖아»: every wafer's every condition was read before the days cut)
        where = {report_shape.column_of(role, role["name"]): {"filterType": "text", "type": "contains",
                                                              "filter": report_shape.name(time_item)}} \
            if only_time and time_item else None
        seen_names = {}
        for wafer, row in self._matched(role, [role["name"], role["value"]] + [role[c] for c in extra],
                                        sorted(set(wafers), key=label), where=where):
            facts = self.wafers[wafer]
            # two rows of one wafer and name (a key part beyond the wafer's): both values, distinct, in the rows' order
            # «300 / 320» - none silently wins (owner 10-24)
            name, said = str(row[0]), facts["conditions"].get(str(row[0]))
            if said is None:
                facts["conditions"][name] = row[1]
            elif row[1] is not None and str(row[1]) not in str(said).split(BOTH):
                facts["conditions"][name] = "%s%s%s" % (said, BOTH, row[1])
            if time_item and report_shape.name(row[0]) == report_shape.name(time_item) and facts.get("time") is None:
                facts["time"] = row[1]
            if title_item and report_shape.name(row[0]) == report_shape.name(title_item) and facts.get("title") is None:
                facts["title"] = row[1]
            if time_item:
                seen_names[report_shape.name(row[0])] = seen_names.get(report_shape.name(row[0]), 0) + 1
            for at, cell in enumerate(extra):
                if facts.get(cell) is None:
                    facts[cell] = row[2 + at]

        if time_item:
            # what the time item read - each wafer's value and the day it is taken as (owner 10-24 «날짜 뭐 읽었는지 다
            # 로그 띄워 · Bonding Date 를 못 읽는 거 같아»)
            timed = [w for w in set(wafers) if self.wafers[w].get("time") is not None]
            logger.warning("[report] time_item %r (%s.%s): %d of %d wafers have it; names read: %s", time_item,
                           role["table"], role["name"], len(timed), len(set(wafers)),
                           ", ".join("%r x%d" % kv for kv in sorted(seen_names.items())[:30]) or "none")
            for w in sorted(set(wafers), key=label):
                logger.warning("[report]   %s: %s %r -> %s", self.said(w), time_item, self.wafers[w].get("time"),
                               _instant(self.wafers[w].get("time")))

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
            where = {self._condition(c): v for c, v in (said.get("where") or said).items()}
            return [w for w in here if all(str(self.wafers[w]["conditions"].get(c)).strip() == str(v).strip()
                                           for c, v in where.items())]
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
    def _pairs(self, role, columns, wafers, name=None, capped=False):
        """(wafer, name) -> the role's `columns` of its row, from a long table a row a wafer and name (the summary,
        the info; a picture row is one `name`, a row a wafer) - a pair two rows say is left out, named."""
        named = [role["item"]] if name is None else []
        found, twice = {}, set()
        for wafer, row in self._matched(role, named + columns, wafers, capped=capped):
            said = row[0] if name is None else name
            if said is None:
                continue
            pair = (wafer, str(said))
            if pair in found:
                twice.add(pair)
            found[pair] = row[len(named):len(named) + len(columns)]
        for pair in twice:
            del found[pair]
        return found, sorted("%s %s" % (self.said(wafer), item) for wafer, item in twice)

    def _summary(self, wafers, yields=False):
        """(wafer, item) -> {"fail", "total", "rate"} as the owner's summary table holds them (owner 10-22: the
        product does not make a wafer's value again) - its defect rows, or with `yields` the rows of
        `summary.yield_item` (the unit's yield, owner 10-24): every reader of a defect reads this, so the yield is in
        none of them."""
        role = self.spec["summary"]
        named = report_shape.yield_items(self.spec)
        cells = [cell for cell in SUMMARY_CELLS if role.get(cell)]
        found, twice = self._pairs(role, [role[cell] for cell in cells], wafers)
        return {((pair[0], report_shape.name(pair[1])) if yields else pair): {
            cell: _number(value) for cell, value in zip(cells, row)}
                for pair, row in found.items() if (report_shape.name(pair[1]) in named) == yields}, \
            [said for said in twice if any(said.endswith(" " + item) for item in named) == yields]

    def _yield_rows(self, columns):
        """The matrix's yield rows (`summary.yield_item`): a row an item, a column's cell read as a defect's is - «x%
        (F/N)», several wafers summed - under labels.yield «Yield»."""
        named = report_shape.yield_items(self.spec)
        if not named:
            return [], []
        found, twice = self._summary([w for members in columns for w in members], yields=True)
        head, sep = report_shape.word(self.spec, "yield"), self.spec.get("item_sep") or ""
        rows = []
        for item in sorted(named):
            cells = [self._cell(found.get((members[0], item)) if len(members) == 1
                                else self._summed([found.get((w, item)) for w in members])) for members in columns]
            rows.append((head if len(named) == 1 else head + sep + item if sep else item,
                         [{"text": cell["text"], "share": cell["share"], "higher": "better"} for cell in cells]))
        return rows, twice

    def _info(self, columns, chosen=None):
        """The info rows under the summary table's head (owner 10-23): [(name, [cell, ...])] over the table's columns
        (each a list of wafers), each info table in turn - one value said shows it, several «mixed (n)», none a blank
        - and the pairs left out. A table of no `item` is one row, its value column's name or its `label`; a long
        table's names stand under its `label`; a table that says `choose` keeps the names `chosen` (yield_by)."""
        rows, left_out = [], []
        mixed = report_shape.word(self.spec, "mixed")
        sep = self.spec.get("item_sep") or ""
        chosen = [str(name) for name in chosen or ()]
        everyone = [w for members in columns for w in members]
        for role in report_shape.info_rows(self.spec):
            found, twice = self._pairs(role, [role["value"]], everyone,
                                       name=None if role.get("item") else str(role["value"]))
            present = {name for _w, name in found}
            names = [n for n in [str(n) for n in role.get("rows") or ()] or sorted(present) if n in present]
            kept = [n for n in names if any(n == c or (sep and n.startswith(c + sep)) for c in chosen)]
            head = role.get("label")
            drawn_rows = []
            for name in names:
                cells = []
                for members in columns:
                    said = sorted({str(found[(w, name)][0]) for w in members
                                   if (w, name) in found and found[(w, name)][0] is not None})
                    cells.append({"text": said[0] if len(said) == 1 else mixed % len(said) if said else ""})
                drawn = name if not head else head if not role.get("item") else head + sep + name
                drawn_rows.append((name, drawn, cells))
            rows += [(drawn, cells) for name, drawn, cells in drawn_rows
                     if not role.get("choose") or name in kept or not kept and _differs(cells, len(columns))]
            left_out += twice
        return rows, left_out

    def _condition_rows(self, columns, chosen=None):
        """The condition group (owner «조건도 안나오고»): a row a condition of the columns' wafers (wafer.conditions,
        the conditions role) - the names the model kept (yield_by rows, owner 10-23 «COND 쪽 넣을 항목은 AI 가 선택»),
        else those whose value differs between the columns, every one when there is one column."""
        mixed = report_shape.word(self.spec, "mixed")
        sep = self.spec.get("item_sep") or ""
        head = report_shape.word(self.spec, "conditions")
        # the time_item condition is the date head's, not a condition row (owner 10-24)
        timed = None if self.spec["wafer"].get("time") else (self.long or {}).get(report_shape.TIME_ITEM)
        titled = (self.long or {}).get(report_shape.TITLE_ITEM)     # the title_item is the wafer's title, no row
        names = [n for n in dict.fromkeys(str(n) for members in columns for w in members
                                          for n in self.wafers[w]["conditions"])
                 if (timed is None or report_shape.name(n) != report_shape.name(timed))
                 and (titled is None or report_shape.name(n) != report_shape.name(titled))]
        kept = [n for n in names if n in [str(c) for c in chosen or ()]]
        rows = []
        for name in names:
            cells = []
            for members in columns:
                said = sorted({_shown(self.wafers[w]["conditions"].get(name)) for w in members
                               if self.wafers[w]["conditions"].get(name) is not None})
                cells.append({"text": said[0] if len(said) == 1 else mixed % len(said) if said else ""})
            others = [cell for cell, members in zip(cells, columns)
                      if not set(members) <= set(self.groups[self.evaluation])]
            if others and all(not cell["text"] for cell in others):
                continue
            if name in kept or not kept and _differs(cells, len(columns)):
                rows.append((head + sep + name if sep else name, cells))
        return rows

    def _pictures(self, columns):
        """The picture rows (owner 10-23 «열마다 한 장»): [(label, [cell, ...])] - a column of one wafer its picture
        embedded (or why not), any other column (a condition value's: `[]`) «—», a wafer with no row a blank - and
        the pairs left out."""
        rows, left_out = [], []
        for role in self.spec.get(report_shape.PICTURE_ROWS) or ():
            name = str(role["label"])
            # a picture table of many rows (chip patches) is read to its cap, never refused (owner 10-24 «컴페어 patches
            # 1만개 이상이라고 멈추네»)
            found, twice = self._pairs(role, [role["image"]], [members[0] for members in columns
                                                                if len(members) == 1], name=name, capped=True)
            px = role.get("px") or report_shape.PICTURE_PX
            source = role.get(report_shape.IMAGE_SOURCE)
            cells = [{"text": "—"} if len(members) != 1 else
                     _picture(_ref(source, found[(members[0], name)][0]), px) if found.get((members[0], name), (None,))[0]
                     else {"text": ""} for members in columns]
            rows.append((name, cells))
            left_out += twice
        return rows, left_out

    def _cell(self, row):
        """A table cell: its text, and the numbers a format holds it by - its share, its F and N."""
        return {"text": self.cell(row), "share": self.share(row), "fail": (row or {}).get("fail"),
                "total": (row or {}).get("total")}

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
            return {"context": "wafers whose condition holds %r: %s" % (keyword, ", ".join(map(self.said, found)) or "none"),
                    "html": None, "wafers": found}
        folded = {c: {} for c in self.conditions_at}
        for w in here:
            for c, v in self.wafers[w]["conditions"].items():
                folded.setdefault(c, {})[_shown(v)] = folded.get(c, {}).get(_shown(v), 0) + 1
        units = self._units(here)
        lines = ["%d wafers in %s" % (len(here), self.evaluation)] + (
            ["units - a report unit, then its parts:"] + ["  " + line for line in units] if units else []) + [
            "%s: %s" % (c, ", ".join("%s %d" % (v, n) for v, n in sorted(values.items(), key=lambda kv: -kv[1])))
            for c, values in folded.items()]
        if self.long:
            default = [w for w in here if not self.wafers[w]["conditions"]]
            lines.append("default conditions (no condition row): %d wafers" % len(default))
        return {"context": "\n".join(lines), "html": None}

    def yield_by(self, wafers=None, by=None, rows=None):
        """`rows`: the names the model keeps of an info table that says `choose` (owner 10-23 «COND 쪽 넣을 항목은 AI
        가 선택») - a name keeps the names under it; none kept, or none said: every row."""
        columns = [(name, col, members) for name, cols in self._column_groups(self.pick(wafers), by)
                   for col, members in cols]
        heads = self._heads(columns, by)
        if not by:                         # by the heads: the date first (owner 10-24 «날짜순으로 표 나열»)
            order = sorted(range(len(columns)), key=lambda at: heads[at][1])
            columns, heads = [columns[at] for at in order], [heads[at] for at in order]
        everyone = [w for _name, _col, members in columns for w in members]
        found, twice = self._summary(everyone)
        items = self._items(found)
        out = []
        for item in items:
            out.append((item, [self._cell(found.get((members[0], item)) if len(members) == 1
                                          else self._summed([found.get((w, item)) for w in members]))
                               for _name, _col, members in columns]))
        spans = [members for _name, _col, members in columns]
        info, info_twice = self._info(spans, rows)
        if not by and not any(role.get(report_shape.CHOOSE) for role in report_shape.info_rows(self.spec)):
            info = self._condition_rows(spans, rows) + info
        yields, yield_twice = self._yield_rows(spans)
        info, info_twice = info + yields, info_twice + yield_twice
        pictures, pictures_twice = self._pictures([[] if by else members for members in spans])
        table = dict(self._columns_of(columns, heads, by), info=info, pictures=pictures, rows=out,
                     item_label=self.spec["summary"].get("label"),
                     left_out=sorted(twice + info_twice + pictures_twice))
        return {"context": _table_text(table), "html": table}

    def _heads(self, columns, by=None):
        """Each column's head, a text a tier, and its order - `derive.report.columns` (owner 10-23: date › wafer ›
        leg): "time" the wafer's day (its rows' latest, the candidates' fold), "group" its group, a key column its
        part. Undeclared: the group, then the key. A column of a condition value: the group, then the value."""
        tiers = self._tiers(by)
        named = list(dict.fromkeys(name for name, _col, _members in columns))
        out = []
        for name, col, members in columns:
            one = members[0] if len(members) == 1 else None
            parts = dict(zip(self.keys, one)) if one else {}
            texts, order = [], []
            for tier in tiers:
                if tier == report_shape.COLUMN_GROUP:
                    texts.append(name)
                    order.append((named.index(name), ""))
                elif tier == report_shape.COLUMN_TIME:
                    # the day of the head under it (date > wafer > leg: the wafer's, every leg one date - owner 10-24
                    # «같은 웨이퍼 다른 레그인데 왜 병합 안 돼»)
                    under = [k for k in tiers[tiers.index(tier) + 1:-1] if k in self.keys]
                    day = self._day(one, under) if one else None
                    texts.append(day or "")
                    order.append((day is None, day or ""))
                elif tier == report_shape.COLUMN_TITLE:
                    # the title of the head under it - a wafer's legs one title (owner 10-24 «헤더 시간 타이틀 웨이퍼 레그»)
                    under = [k for k in tiers[tiers.index(tier) + 1:-1] if k in self.keys]
                    title = self._title(one, under) if one else None
                    texts.append(title or "")
                    order.append((title is None, title or ""))
                elif tier is None or one is None:
                    texts.append(col)
                    order.append((False, col))
                else:
                    texts.append("" if parts.get(tier) is None else parts[tier])
                    order.append((parts.get(tier) is None, parts.get(tier) or ""))
            out.append((texts, order))
        return out

    def _tiers(self, by=None):
        """The column head tiers - `columns`, else the group then the key; a column of a condition value: the group,
        then the condition (None to the heads: the column's label)."""
        titled = (self.long or {}).get(report_shape.TITLE_ITEM) or (self.long or {}).get("title")
        return ([report_shape.COLUMN_GROUP, None] if by else self.spec.get(report_shape.COLUMNS) or
                [report_shape.COLUMN_TIME] + ([report_shape.COLUMN_TITLE] if titled else []) + self.keys)

    def _columns_of(self, columns, heads, by=None):
        """The table's columns: the groups in the columns' order (the model reads them), each column's head texts,
        and whether it is this report's own (the colours' «vs control» reads the others)."""
        groups = []
        for name, col, _members in columns:
            if groups and groups[-1][0] == name:
                groups[-1][1].append(col)
            else:
                groups.append((name, [col]))
        return {"groups": groups, "heads": [texts for texts, _order in heads],
                "tiers": [by if tier is None else tier for tier in self._tiers(by)],
                "own": [name == self.evaluation for name, _col, _members in columns]}

    def _title(self, wafer, under):
        """The title of the wafer's unit (`under`: key columns, as `_day`) - its first wafer's that says one."""
        at = [self.keys.index(k) for k in under or ()]
        unit = (lambda w: tuple(w[i] for i in at)) if at else self._report_wafer
        mine = unit(wafer)
        said = [str(f["title"]) for w, f in self.wafers.items() if unit(w) == mine and f.get("title") not in (None, "")]
        return said[0] if said else None

    def _day(self, wafer, under=None):
        """The wafer's day: the latest time of the rows of its report wafer - or, `under` (key columns), of every wafer
        of those parts - on the product's wall clock, or None."""
        at = [self.keys.index(k) for k in under or ()]
        unit = (lambda w: tuple(w[i] for i in at)) if at else self._report_wafer
        mine = unit(wafer)
        times = [at for at in (_instant(facts["time"]) for w, facts in self.wafers.items()
                               if unit(w) == mine) if at is not None]
        return max(times).date().isoformat() if times else None

    def _condition(self, said):
        """The condition a call names - a wafer table condition column or a conditions table item (owner 10-24 «read
        refused 컨디션 one of 가 아니래»: the long table's items were not known), matched without case and surrounding
        spaces; one of none is refused with the names there are."""
        known = list(dict.fromkeys(list(self.conditions_at) + [n for f in self.wafers.values() for n in f["conditions"]]))
        by_name = {report_shape.name(n).lower(): n for n in known}
        found = by_name.get(report_shape.name(said).lower())
        if found is None:
            raise ReadRefused("%r is not a condition - one of %s" % (said, ", ".join(map(str, known))))
        return found

    def _column_groups(self, wafers, by):
        """[(group name, [(column label, [wafer, ...]), ...])] - this evaluation's picked wafers, then each compare
        set; a column a wafer, or a condition value when `by` names one."""
        picked = set(wafers)
        out = []
        for name, members in self.groups.items():
            members = [w for w in members if name != self.evaluation or w in picked]
            if by:
                by = self._condition(by)
                values = {}
                for w in members:
                    values.setdefault(_shown(self.wafers[w]["conditions"].get(by)), []).append(w)
                out.append((name, sorted(values.items())))
            else:
                out.append((name, [(self.said(w), [w]) for w in members]))
        return out

    def pareto(self, wafers=None):
        picked = self.pick(wafers)
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
        return {"context": text or "no fail chips", "html": {"rows": rows}}

    def trend(self, wafers=None, items=None):
        """Each item's share wafer by wafer in time order - this evaluation's picked wafers, then every compare set
        and control group beside them (owner 10-23: other lots' trends as a control)."""
        groups = [(self.evaluation, self._ordered(self.pick(wafers)))] + [
            (name, members) for name, members in self.groups.items() if name != self.evaluation]
        found, twice = self._summary([w for _name, members in groups for w in members])
        names = [str(i) for i in items] if items else self._items(found)
        lines, rows = [], []
        for item in names:
            cells = []
            for name, members in groups:
                shares = [self.share(found.get((w, item))) for w in members]
                cells += [dict(self._cell(found.get((w, item))), text="" if share is None else "%.2f%%" % share)
                          for w, share in zip(members, shares)]
                said = [share for share in shares if share is not None]
                if said:
                    lines.append("%s%s: first %.2f%% last %.2f%% least %.2f%% most %.2f%% over %d wafers" % (
                        item, "" if name == self.evaluation else " [%s]" % name, said[0], said[-1], min(said),
                        max(said), len(said)))
            rows.append((item, cells))
        columns = [(name, self.said(w), [w]) for name, members in groups for w in members]
        table = dict(self._columns_of(columns, self._heads(columns)), rows=rows, left_out=twice)
        return {"context": "\n".join(lines) or "no item has a share", "html": table}

    def images(self, wafers=None, items=None):
        role = self.spec.get("images")
        if not role:
            raise ReadRefused("this report declares no images")
        picked = self.pick(wafers)
        outside = [self.said(w) for w in picked if w not in set(self.groups[self.evaluation])]
        if outside:
            raise ReadRefused("images are this evaluation's only - %s is not" % ", ".join(outside[:5]))
        found, _twice = self._summary(picked)
        said = "fail" if self.spec["summary"].get("fail") else "rate"
        occurred = {(w, report_shape.name(item)) for (w, item), row in found.items() if (row.get(said) or 0) > 0}
        wanted = {str(i) for i in items} if items else None
        per_item, px = role.get("per_item", 3), role.get("px", 320)
        sep, source = role.get(report_shape.ITEM_SEP), role.get(report_shape.IMAGE_SOURCE)
        beyond = [c for c in report_shape.wafer_columns(role["wafer"]) if c not in self.keys]
        fold = [beyond.index(c) for c in self.key_words if c in beyond
                and report_shape.KEY_FOLD in self.key_words[c]]
        chip = [at for at, c in enumerate(beyond) if at not in fold]
        rows = self._matched(role, [role["item"], role["image"]], picked, capped=True)   # capped, not refused
        # a chip's rows (owner 10-23: a layer a row, the chip seen through) - the smallest fold values first, keys' order
        rows.sort(key=lambda pair: [_ordinal(pair[1][2 + at]) for at in fold])
        # images.match: an image kind is its summary item's picture; with match declared, a kind it pairs with nothing
        # and no summary item is named shows under itself, after a line naming it (lead 10-24: no silent drop)
        match, items = report_shape.image_match(self.spec), {report_shape.name(item) for _w, item in found}
        unpaired = {}
        chosen, counts, stacks = {}, {}, {}
        for wafer, row in rows:
            ref = _ref(source, row[1])
            whose = (wafer, tuple(row[2 + at] for at in chip))
            for kind in ([part.strip() for part in str(row[0]).split(sep)] if sep else [report_shape.name(row[0])]):
                item = match.get(kind, kind)
                alone = bool(match) and kind not in match and kind not in items and kind != "None"
                if not alone and (wafer, item) not in occurred or (wanted and item not in wanted) or not ref:
                    continue
                if alone:
                    unpaired.setdefault(kind, [])
                layer = "/".join(str(row[2 + at]) for at in fold) if fold else None
                if fold and (item, whose) in stacks:
                    # every layer of a chip and defect, one stack the wheel turns (owner 10-24 «디펙별 이미지 모든 레이어
                    # · 마우스 휠로 레이어 바꿔 볼 수 있게»)
                    picture = _picture(ref, px)
                    if "src" in picture:
                        stacks[(item, whose)]["layers"].append(dict(picture, layer=layer))
                    continue
                # per_item a wafer row - each leg of a wafer its own (lead 10-23: all three were L1's)
                if counts.get((item, wafer), 0) >= per_item:
                    continue
                picture = _picture(ref, px)
                entry = dict(picture, wafer=self.said(wafer))
                if fold:
                    entry["layers"] = [dict(picture, layer=layer)] if "src" in picture else []
                    stacks[(item, whose)] = entry
                (unpaired[kind] if alone else chosen.setdefault(item, [])).append(entry)
                if "src" in picture:
                    counts[(item, wafer)] = counts.get((item, wafer), 0) + 1
        if unpaired:
            # the line, then each unpaired kind under itself - after the paired items
            chosen[report_shape.word(self.spec, "unpaired") % ", ".join(sorted(unpaired))] = []
            chosen.update(sorted(unpaired.items()))
        each = {}
        for (item, _wafer), n in counts.items():
            each[item] = each.get(item, 0) + n
        if not chosen:
            # 소유자 10-24 «아직도 no image of an occurred defect»: the page says why - what was found, what occurred
            kinds = sorted({str(row[0]) for _w, row in rows})
            why = ("No image of an occurred defect - %d image row(s) of %s for these wafers (matched by %s); their "
                   "kinds: %s; defects that occurred: %s%s" % (
                       len(rows), role["table"], ", ".join("%s=%s" % (c, report_shape.column_of(role, c))
                                                           for c in report_shape.wafer_columns(role["wafer"])),
                       ", ".join(kinds[:12]) or "-", ", ".join(sorted({i for _w, i in occurred})[:12]) or "-",
                       "; images.match: %s" % match if match else ""))
            chosen = {} if self.embedded else {why: []}     # said only while the page has no picture at all
            self._image_why = why
        elif getattr(self, "_image_why", None):
            self.embedded.pop(self._image_why, None)          # a later read found pictures - the reason goes
            self._image_why = None
        self.embedded.update(chosen)
        text = ", ".join("%s %d" % (item, n) for item, n in sorted(each.items())) or next(iter(chosen), "")
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
        # no evaluation column (owner 10-23): a candidate is a wafer, its title and conditions what the model reads to
        # judge «the same evaluation · the default conditions» (lead: the model judges, no rule picks); a wafer of no
        # time comes after the dated ones
        each = not role.get("evaluation")
        if not (role.get("time") or (self.long or {}).get("time") or (self.long or {}).get(report_shape.TIME_ITEM)) \
                or not (each or role.get("time")):
            raise ReadRefused("candidates need derive.report.wafer.time and evaluation, or conditions.time")
        own = set(self.groups[self.evaluation])
        here = [at for at in (_instant(self.wafers[w]["time"]) for w in own) if at is not None]
        if not here and not each:
            raise ReadRefused("%s's wafers say no time - recent is counted back from its latest" % self.evaluation)
        anchor = max(here) if here else None
        # `control.same`: a candidate shares those columns' values with this report's wafers
        alike = {self.wafers[w]["same"] for w in own}
        by = {}
        where = self._dated(own, anchor, recent)
        for wafer in [] if where == {} else self._wafer_rows(where, newest=bool(role.get("time")), only_time=True):
            facts = self.wafers[wafer]
            at, evaluation = _instant(facts["time"]), facts["evaluation"]
            # a wafer of no time is no candidate (owner 10-24 «날짜 없는 웨이퍼 후보 빼»)
            if (wafer in own or at is None if each else at is None or evaluation in (None, self.evaluation)) \
                    or facts["same"] not in alike:
                continue
            entry = by.setdefault(self._unit(wafer) if each else str(evaluation), {"latest": at, "wafers": []})
            entry["latest"] = max(entry["latest"], at) if entry["latest"] is not None and at is not None else \
                entry["latest"] or at
            entry["wafers"].append(wafer)
        # a candidate's time is its rows' latest - the anchor's own fold - and it stands or falls whole (lead 10-23:
        # a leg later than the report's wafer was left out, its other leg of no time stood a candidate alone). A wafer
        # later than this report's is a candidate too when no evaluation column says one (owner 10-23 «빼지 마»)
        for name in list(by):
            at = by[name]["latest"]
            if at is not None and anchor is not None and (at > anchor and not each or recent.get("days") and
                                                          anchor - at > datetime.timedelta(days=recent["days"])):
                del by[name]
        newest = sorted(by, key=lambda name: (by[name]["latest"] is not None, by[name]["latest"] or datetime.datetime.min,
                                              name), reverse=True)
        if recent.get("evaluations"):
            newest = newest[:recent["evaluations"]]
        timed = sum(1 for w in self.wafers if _instant(self.wafers[w]["time"]) is not None)
        logger.warning("[report] candidates: %d wafers read, %d with a time (time from %s); this report's %d wafers, "
                       "%d with a time, latest %s; recent %s -> %d candidates: %s", len(self.wafers), timed,
                       role.get("time") or (self.long or {}).get("time") or
                       "conditions.time_item %s" % (self.long or {}).get(report_shape.TIME_ITEM),
                       len(own), len(here), anchor, recent, len(newest), "; ".join(
                           "%s @ %s (%d)" % (n, by[n]["latest"], len(by[n]["wafers"])) for n in newest) or "none")
        # every wafer read and why it is no candidate - the owner reads the terminal (owner 10-24 «로그가 짧음»)
        for wafer in self.wafers:
            facts = self.wafers[wafer]
            name = self._unit(wafer) if each else str(facts["evaluation"])
            logger.warning("[report]   wafer %s: time %r (day %s) -> %s", self.said(wafer), facts["time"],
                           _instant(facts["time"]),
                           "this report" if wafer in own else "candidate" if name in newest else
                           "no time" if _instant(facts["time"]) is None else
                           "other same %s" % (facts["same"],) if facts["same"] not in alike else
                           "outside recent %s of %s" % (recent, anchor))
        if self.long:                      # the conditions of this report's wafers and the candidates kept - only
            self._long_conditions(list(own) + [w for name in newest for w in by[name]["wafers"]])
        self._candidates = {name: dict(by[name], wafers=self._ordered(by[name]["wafers"])) for name in newest}
        return self._candidates

    def _unit(self, wafer) -> str:
        """A candidate - the unit its date is of: the time_item table's key parts (a wafer, every leg one - owner 10-24
        «날짜는 wf 단위인데 leg 까지 보는 건 토큰 낭비»), else the report wafer."""
        at = getattr(self, "_date_unit", None)
        return label(tuple(wafer[i] for i in at)) if at else self._report_wafer(wafer)

    def _dated(self, own, anchor, recent):
        """The wafer table filter of the wafers dated within `recent` by `conditions.time_item` - the conditions
        table's time_item rows alone are read, every wafer's (owner 10-24 «조건 표에서 날짜 컬럼만 필터하고 날짜 구간
        내 웨이퍼 고르고»): None when the wafer table names the time (every wafer row is read), {} when none is dated
        within it."""
        role, long = self.spec["wafer"], self.long or {}
        time_item = None if role.get("time") else long.get(report_shape.TIME_ITEM)
        if not time_item:
            return None
        shared = [c for c in report_shape.wafer_columns(long["wafer"]) if c in self.keys]
        rows = _rows(self.db, long, shared + [long["name"], long["value"]], keys=shared, capped=True, where={
            report_shape.column_of(long, long["name"]): {"filterType": "text", "type": "contains",
                                                        "filter": report_shape.name(time_item)}})
        dates = {}
        for row in rows:
            at = _instant(row[len(shared) + 1])
            if report_shape.name(row[len(shared)]) == report_shape.name(time_item) and at is not None:
                key = _parts(row[:len(shared)])
                dates[key] = max(dates[key], at) if key in dates else at
        mine = [self.keys.index(col) for col in shared]
        self._date_unit = mine
        anchor = max([dates[k] for k in (_parts(w[i] for i in mine) for w in own) if k in dates] or [anchor]) \
            if anchor is None else anchor
        days = recent.get("days")
        kept = [k for k, at in dates.items() if anchor is None or not days or
                abs(anchor - at) <= datetime.timedelta(days=days)]
        logger.warning("[report] dated by %r: %d time_item rows, %d wafers dated, latest of this report %s, "
                       "%d within %s", time_item, len(rows), len(dates), anchor, len(kept), recent)
        if not kept:
            return {}
        return {report_shape.column_of(role, col): _equals_any(col, sorted({k[at] for k in kept},
                                                                     key=lambda v: (v is not None, v or "")))
                for at, col in enumerate(shared)}

    def pick_basis(self) -> list:
        """The Evidence's wafer pick: the candidates within `recent` (each with its date and wafers) and the groups the
        report read beside its own (owner 10-24 «기간 내 뭐뭐 있었고 그중에 이걸 뽑았다») - [] when none was looked at."""
        if self._candidates is None:
            return []
        recent = (self.spec.get("control") or {}).get("recent")
        lines = ["wafer pick - within %s: %d candidates" % (recent, len(self._candidates))]
        lines += ["    %s @ %s: %s" % (name, entry["latest"].date() if entry["latest"] else "-",
                                       ", ".join(map(self.said, entry["wafers"])))
                  for name, entry in self._candidates.items()]
        taken = [(name, members) for name, members in self.groups.items() if name != self.evaluation]
        lines.append("wafer pick - taken: %s" % ("; ".join("%s (%s)" % (name, ", ".join(map(self.said, members)))
                                                           for name, members in taken) or "none"))
        return lines

    def _report_wafer(self, wafer) -> str:
        """The wafer as the report table names it - its legs one candidate (lead 10-23), every column without `only`."""
        parts = dict(zip(self.keys, wafer))
        return label(tuple(parts[c] for c in self.picked_by) if self.picked_by else wafer)

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
                    value = _shown(self.wafers[wafer]["conditions"].get(column))
                    counts[value] = counts.get(value, 0) + 1
                folded.append("%s %s" % (column, ", ".join("%s %d" % (v, n) for v, n in
                                                           sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))))
            titles = []
            if self.long:
                folded = ["%s: %s" % (self.said(w), ", ".join("%s=%s" % (k, _shown(v)) for k, v in sorted(self.wafers[w]["conditions"].items()))
                                      or "default conditions") for w in entry["wafers"]]
                titles = sorted({str(self.wafers[w].get("title")) for w in entry["wafers"] if self.wafers[w].get("title")})
            date = entry["latest"].date().isoformat() if entry["latest"] else "no date"
            lines.append(" · ".join([name, date, "%d rows" % len(entry["wafers"])]
                                    + (["title " + " | ".join(titles)] if titles else []) + folded))
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
                raise ReadRefused("%s is this evaluation - compare wafers come from another" % name)
            if name not in found:
                raise ReadRefused("%s is not a recent evaluation - candidates() lists them" % name)
            chosen[name] = []
        for said in [str(w) for w in wafers or ()]:
            owner = next((name for name, entry in found.items() for w in entry["wafers"] if said in (label(w), self.said(w))), None)
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
        control = report_shape.word(self.spec, "control")
        for name in [n for n in self.groups if n.startswith(control + " ")]:
            del self.groups[name]
        lines = []
        for name, members in groups.items():
            self.groups["%s %s" % (control, name)] = members
            lines.append("%s %s: %d wafers (%s)" % (control, name, len(members), ", ".join(map(self.said, members[:10]))))
        return lines

    def compare(self, sets=None, evaluations=None, wafers=None):
        """Compare sets the declaration names (sets, or its default) and/or a control group from the recent
        evaluations (evaluations, wafers) - each a group of columns beside this evaluation's in the tables after it."""
        if sets is None and not (evaluations or wafers):
            return {"context": "\n".join(self.declared_compare()), "html": None}
        lines = []
        if sets is not None or not (evaluations or wafers):
            lines += self._sets(sets)
        if evaluations or wafers:
            lines += self._control(evaluations, wafers)
        return {"context": "\n".join(lines), "html": None}

    def declared_compare(self) -> list:
        """The comparison the declaration gives - `sets.default`, and the newest `control.recent` evaluations within
        `max_evaluations` · `max_wafers` - beside this report's group. The model's compare() with no arguments and the
        product's table read this one (lead 10-24, owner «근데 표 다른 웨이퍼 안불러오네»)."""
        lines = []
        if (report_shape.sets_role(self.spec) or {}).get(report_shape.SETS_DEFAULT):
            lines += self._sets(None)
        if (self.spec.get("control") or {}).get("recent"):
            picked, total = [], 0
            for name, entry in self._recent().items():
                if len(picked) >= report_shape.control_limit(self.spec, "max_evaluations") or \
                        total + len(entry["wafers"]) > report_shape.control_limit(self.spec, "max_wafers"):
                    break
                picked.append(name)
                total += len(entry["wafers"])
            lines += self._control(picked, None) if picked else ["control: no recent evaluation in range"]
        if not lines:
            raise ReadRefused("no compare set named - and this report declares no default (sets.default) and no "
                              "control.recent")
        return lines

    def _sets(self, sets):
        role = report_shape.sets_role(self.spec)
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
    """A time cell on the product's wall clock (`expression_time_zone`), or None - the one reader of a time, so a
    candidate's date is the day the operator wrote (lead 10-23: a UTC cut said 10-21 for 10-22T00:00+09:00)."""
    import expression

    return expression._instant(value)


def _ordinal(value):
    """A fold column's value in its order - a number by its size, a text by its spelling, none last."""
    from expression import number_of

    number = number_of(value)
    return (value is None, number is None, number if number is not None else 0, "" if value is None else str(value))


def _differs(cells, columns) -> bool:
    """A row the product keeps by itself - its value differs between the columns, or there is one column."""
    return columns <= 1 or len({cell["text"] for cell in cells}) > 1


def _shown(value) -> str:
    """A condition value as the model and the file read it - a blank one (`crud.is_blank_value`) said EMPTY."""
    from database import crud

    return EMPTY if crud.is_blank_value(value) else str(value)


def _number(value):
    """A summary cell as a number - None for a blank or a text that is none («», «N/A»: ops data, owner 10-24 «빈값 등은
    당연히 있는데»), so one cell cannot stop a report."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _count(value):
    return str(int(value)) if float(value).is_integer() else "%g" % value


def _ref(source, value):
    """The image ref the grid hands /api/image for this cell - its value as written when it already names a source
    (owner 10-24 «api 에서 들고오는 문 그대로»: «sat_patches:\\..» was prefixed a second time), else `source:value`."""
    if not source or not value or str(value).startswith(str(source) + ":"):
        return value
    return "%s:%s" % (source, value)


def _picture(ref, px):
    """A picture embedded - {"src": data URI} - or {"refused": why}: the one way a report puts a picture in its file
    (images() and the picture rows)."""
    import image_sources

    try:
        answer = image_sources.shrink(image_sources.resolve(ref), px)
    except image_sources.ImageRefused as refused:
        return {"refused": str(refused)}
    data, media = _image_bytes(answer)
    return {"src": "data:%s;base64,%s" % (media, base64.b64encode(data).decode())}


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
    for name, cells in table.get("info") or ():
        lines.append("info %s | %s" % (name, " | ".join(cell["text"] for cell in cells)))
    for name, cells in table.get("pictures") or ():
        lines.append("%s: %d of %d columns" % (name, sum("src" in cell for cell in cells), len(cells)))
    for item, cells in table["rows"]:
        lines.append("%s | %s" % (item, " | ".join(cell["text"] for cell in cells)))
    if table.get("left_out"):
        lines.append("left out (two rows for one wafer and name): %s" % ", ".join(table["left_out"]))
    return "\n".join(lines)
