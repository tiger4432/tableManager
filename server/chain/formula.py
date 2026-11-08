# -*- coding: utf-8 -*-
"""A same-row formula on a grid column (owner 10-28) - the declaration it is, and back.

`=[a]+[b]*3` on column c of table T is a join of T onto itself on T's own key, taking c from the formula
(`join_into.FORMULA_MARK`): one chain rule in chain_rules.json, named «formula T.c». The formula text is the take's `fn`
as written, so opening the rule again shows the same text. The grammar is the shared calculator's
(`server/expression.py`); the join judges it (`join_into.take_refusal`).
"""
import logging

from chain import cell_layer, join_into, rule_shape
from chain import ingestion_worker as worker

logger = logging.getLogger(__name__)

#: The name a formula's rule is saved under: «formula <table>.<column>» - the product writes it (lead 10-28).
RULE_NAME = "formula %s.%s"


def to_declaration(table: str, column: str, text: str) -> dict:
    """The chain rule a formula on `table`.`column` is - switched on (lead 10-28: written on the grid, it applies), and
    woken by what other rules write too, as a spreadsheet's cell follows the cells it reads (owner 10-28 «1 ㄱ»: one
    reading another formula's column, or a column a rule writes, stayed on the old value). Its own writes still wake
    nothing; `max_chain_depth` is how many steps a chain of them goes."""
    keys = cell_layer.entry_key_columns(_config(table))
    return {"name": RULE_NAME % (table, column), "enabled": True, "allow_chain_trigger": True,
            "on": {"table": table}, "into": {"table": table},
            "derive": {"kind": "join", "join": {"on": [{"left": key, "right": key} for key in keys],
                                                "take": [{"into": column, "fn": str(text).strip()}]}}}


def of_declaration(declaration):
    """(table, column, formula text) when `declaration` is a formula's rule - the shape `to_declaration` writes, under
    its name - else None."""
    if not isinstance(declaration, dict):
        return None
    on, into, derive = (declaration.get(cell) or {} for cell in ("on", "into", "derive"))
    join = (derive.get("join") if isinstance(derive, dict) else None) or {}
    table = on.get("table") if isinstance(on, dict) else None
    takes = (join.get("take") if isinstance(join, dict) else None) or []
    if not table or not isinstance(into, dict) or into.get("table") != table or not isinstance(takes, list) \
            or len(takes) != 1 or not isinstance(takes[0], dict):
        return None
    column, text = takes[0].get("into"), takes[0].get(join_into.TAKE_FN)
    keys = cell_layer.entry_key_columns(_config(table))
    if join_into.formula_of(text) is None or declaration.get("name") != RULE_NAME % (table, column) \
            or join.get("on") != [{"left": key, "right": key} for key in keys]:
        return None
    return table, column, text


#: (the loaded rule set it was read from, {(table, column): (layer, function, columns read)}) - `columns`' answer.
_COLUMNS = [None, {}]


def columns() -> dict:
    """{(table, column): (layer name, the formula's function, the columns it reads, its text)} - the formulas this process
    runs:
    each loaded rule that is switched on and is a formula (`of_declaration` over the document it was loaded from). Read
    again when the rules are (`ingestion_worker.forget_loaded_chain_rules`, every process's config watcher). Asked
    for every cell the display answer resolves - nothing is imported or built on the way back."""
    loaded = worker._LOADED_RULES
    if loaded is None or _COLUMNS[0] is not loaded:
        from database import crud

        if loaded is None:
            worker.loaded_chain_rules()
            loaded = worker._LOADED_RULES
        running = {rule.get("name") for rule in loaded or () if not rule_shape.is_switched_off(rule)}
        out = {}
        for declaration in (worker._RULES_DOCUMENT or {}).get("rules") or ():
            said = of_declaration(declaration)
            if said and declaration.get("name") in running:
                table, column, text = said
                out[(table, column)] = (crud.merged_layer_name(crud.CHAIN_SOURCE, RULE_NAME % (table, column)),
                                        _typed(join_into.take_function(text)[0], table, column),
                                        join_into.formula_of(text)["names"], text)
        _COLUMNS[:] = [loaded, out]
    return _COLUMNS[1]


def _typed(answer, table, column):
    """The formula's function, its answer in the column's type the way every write casts (`crud.cast_value_by_type`) -
    blank where it does not fit (owner 10-28)."""
    from database import crud

    column_type = (_config(table).get("column_types") or {}).get(column, "string")

    def typed(values):
        value = answer(values)
        try:
            return None if value is None else crud.cast_value_by_type(value, column_type, column, table)
        except crud.CellRefused:
            return None

    return typed


#: Why a rule cannot write a column a formula computes (lead 10-28: two writers of one cell, one losing in silence).
WRITES_A_FORMULA = "%s writes %s.%s, which %s computes - a formula column has one writer"


def second_writers(declarations, rules) -> list:
    """[(rule, the formula's rule name, sentence)] - each rule in `rules` (as the loader stands them) that writes a column a formula among
    `declarations` (the file's) computes, the formula's own rule aside. What a rule writes is
    `rule_run.columns_a_rule_writes`'; a rule whose columns are not known on a formula's table is not judged, and says
    so in one line (lead 11-08 ①ㄴ)."""
    from chain import rule_run

    formulas = {}
    for declaration in declarations or ():
        said = of_declaration(declaration)
        if said:
            formulas[said[:2]] = declaration.get("name")
    out = []
    for rule in rules or () if formulas else ():
        if not isinstance(rule, dict) or rule.get("name") in formulas.values():
            continue
        table = rule.get("target_table")
        written = rule_run.columns_a_rule_writes(rule)
        if written is None and any(at == table for at, _column in formulas):
            logger.warning("[ChainRules] %s: this rule's written columns are unknown - list target_columns to judge it",
                           rule.get("name"))
        for column in sorted(written or ()):
            if (table, column) in formulas:
                named = formulas[(table, column)]
                out.append((rule, named, WRITES_A_FORMULA % (rule.get("name"), table, column, named)))
                break
    return out


#: What saving a formula does to the column's old values (lead 10-28) - said before it is saved.
SAVING_REPLACES = ("Saving replaces this column's values row by row - earlier values are not kept per cell; "
                   "the history keeps one line per batch.")


class FormulaRefused(Exception):
    """Why a formula cannot stand, in the words the screen shows."""


def view(table: str) -> dict:
    """{"table", "formulas": [{"column", "formula", "rule", "enabled"}], "base"} - the formulas chain_rules.json holds
    for `table`, read from the file the rule editor reads (`ledger.admin.chain_rule_raw_view`)."""
    from ledger import admin

    listed = admin.chain_rule_raw_view()
    out = []
    for name in listed["rules"]:
        if not name.startswith(RULE_NAME % (table, "")):
            continue
        opened = admin.chain_rule_raw_view(name)
        said = of_declaration(opened.get("declaration"))
        if said and said[0] == table:
            out.append({"column": said[1], "formula": said[2], "rule": name,
                        "enabled": opened.get("enabled", True)})
    return {"table": table, "formulas": out, "base": listed["base"]}


#: How many of the table's first rows a preview answers.
SAMPLE_ROWS = 5


def preview(db, table: str, column: str, text: str) -> dict:
    """{"rule", "sample": [{"keys", "reads", "now", "becomes"}], "says"} - the formula over the table's first rows. Saving
    runs it over every row; the route says how many (the grid's count). Raises FormulaRefused with the judgement the save
    and the loader make (`rule_shape.expand_declaration`)."""
    from database import models

    _judge(table, column, text)
    read = join_into.formula_of(str(text).strip())
    (answer, _why), model = join_into.take_function(text.strip()), models.DYNAMIC_TABLES[table]
    keys = cell_layer.entry_key_columns(_config(table))
    sample = []
    for row in db.query(model).order_by(model.row_id).limit(SAMPLE_ROWS):
        reads = {name: getattr(row, name) for name in read["names"]}
        sample.append({"keys": {key: getattr(row, key) for key in keys}, "reads": reads,
                       "now": getattr(row, column), "becomes": answer([reads])})
    return {"rule": RULE_NAME % (table, column), "sample": sample, "says": SAVING_REPLACES}


def _judge(table: str, column: str, text: str):
    """Raises FormulaRefused with why `text` on `table`.`column` cannot stand - the judgement the save and the loader
    make (`rule_shape.expand_declaration`, `second_writers`)."""
    from chain import rule_shape
    from database import crud

    columns = (_config(table).get("column_types") or {})
    if not columns:
        raise FormulaRefused("%r is not a table table_config declares" % table)
    if column not in columns:
        raise FormulaRefused("%r is not a column of %s" % (column, table))
    if join_into.formula_of(str(text).strip()) is None:
        raise FormulaRefused("a formula starts with %s" % join_into.FORMULA_MARK)
    stood, refusal, _notes = rule_shape.expand_declaration(to_declaration(table, column, text), crud.TABLE_CONFIG)
    if refusal or not stood:
        raise FormulaRefused(refusal or "the formula stands no rule")
    for _rule, _formula, sentence in second_writers([to_declaration(table, column, text)], worker.loaded_chain_rules()):
        raise FormulaRefused(sentence)


def save(db, table: str, column: str, text: str, base: str, requested_by=None) -> dict:
    """{"rule", "run_id", "base"} - the formula's rule saved switched on (the rule editor's door,
    `ledger.admin.save_chain_rule_raw`) and R1 over the table queued (`retroactive.publish`, lead 10-28)."""
    from admin import retroactive
    from ledger import admin

    _judge(table, column, text)
    name = RULE_NAME % (table, column)
    saved = admin.save_chain_rule_raw(name, to_declaration(table, column, text), base, db=db)
    queued = retroactive.publish(db, "chain_replay", {"rule": name}, requested_by=requested_by)
    return {"rule": name, "run_id": queued["run_id"], "base": saved["base"]}


def remove(db, table: str, column: str, base: str, requested_by=None) -> dict:
    """{"rule", "run_id", "base"} - the formula's rule taken out (`ledger.admin.remove_chain_rule_raw`) and R3 over
    the column queued with `formula_removed` - its cells resolved from their layers, blank where none (lead 10-28 ㄱ)."""
    from admin import retroactive
    from ledger import admin

    name = RULE_NAME % (table, column)
    removed = admin.remove_chain_rule_raw(name, base, db=db)
    queued = retroactive.publish(db, "resolve", {"table": table, "columns": column, "formula_removed": column},
                                 requested_by=requested_by)
    return {"rule": name, "run_id": queued["run_id"], "base": removed["base"]}


def _config(table: str) -> dict:
    from database import crud

    return crud.TABLE_CONFIG.get(table) or {}
