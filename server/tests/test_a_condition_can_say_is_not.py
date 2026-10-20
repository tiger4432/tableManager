# -*- coding: utf-8 -*-
"""소유자 10-12 「컬럼 a 값이 b 일 때는 c, b 가 아닐 때는 d」 · 「아니다도 추가해」.

A `when` value is `<v>` or `{"not": <v>}`. Per row the second is the exact complement of the
first, so a row whose `a` is blank says d. One seat judges both (`roleframe._unit_says`) for a
sentence's `when`, `read.exclude_when` and `entities.<type>.references[].from.when`.

The declaration is the RELEASE_LOG example, read out of the log and run as written.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                           # noqa: E402
from ledger.backfill import prepare_v2_cursor_batch                   # noqa: E402
from ledger.event_frame import named_columns, row_excluded            # noqa: E402
from ledger.roleframe import _unit_says, map_event_frame              # noqa: E402
from test_ledger_setup_bundle import (                                # noqa: E402
    DEFAULT_CATALOG, logical_bundle, validate_bundle_errors)
from test_ledger_setup_registry import snapshot                       # noqa: E402
from test_ledger_roleframe import implementations, mapper_context     # noqa: E402
from test_ledger_event_frame import NOW, base_rows                    # noqa: E402
from test_an_entity_reference_is_written_by_every_source_naming_it import (  # noqa: E402
    REFERENCE, SAMPLE, _dies, _edges, _preview, _snapshot, _transfer_rows)

SOURCE = "input_rows"
RELEASE_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "process", "RELEASE_LOG.md")
HEADING = "## 2026-10-12 · 원장 선언 — 조건에 «아니다» — 칸 a 가 b 면 문장 c, 아니면 문장 d"

#: The fixture plant with the column the example names.
CATALOG = copy.deepcopy(DEFAULT_CATALOG)
CATALOG[SOURCE]["columns"]["a"] = "string"

#: a = b twice, another value twice, NULL, and a blank string.
A_VALUES = ["b", "b", "other", "other", None, ""]


def release_log_example():
    text = open(RELEASE_LOG, encoding="utf-8").read()
    assert HEADING in text, "the RELEASE_LOG entry is gone or renamed"
    block = re.search(r"```json\n(.*?)\n```", text.split(HEADING, 1)[1], re.S)
    return json.loads(block.group(1))


def _bundle(sentences, exclude=None):
    """The fixture source read row by row, its one sentence copied once per `sentences` entry
    with that entry's `when` (None: no `when`)."""
    raw = logical_bundle()
    source = raw["sources"][SOURCE]
    source["read"].update(unit="row", identity=["row_id"], group_by=[])
    source["map"]["unit"] = {"kind": "row"}
    mappings = source["bind"]["mappings"]
    main = mappings.pop("main_transition")
    for sentence, when in sentences.items():
        mappings[sentence] = copy.deepcopy(main)
        if when is not None:
            mappings[sentence]["when"] = copy.deepcopy(when)
    if exclude is not None:
        source["read"]["exclude_when"] = exclude
    return raw


def _paths(raw):
    return {issue.path for issue in validate_bundle_errors(raw, catalog=CATALOG)}


def _rows():
    """As the read hands rows over - dicts, so a NULL stays None (`backfill._v2_frame`)."""
    rows = base_rows(len(A_VALUES)).to_dict("records")
    for row, value in zip(rows, A_VALUES):
        row.update(event_at=NOW, a=value, unselected_note=None)
    return rows


def _said(raw):
    """source_id -> the sentences its row said, through the read and the real mapper."""
    compiled = snapshot(raw, catalog=CATALOG)
    context = mapper_context(compiled, SOURCE)
    said = {}
    for frame in prepare_v2_cursor_batch(compiled, SOURCE, _rows()):
        (row,) = frame["source_id"].tolist()
        out = map_event_frame(context, frame, implementations())
        said[row] = sorted(out["sentence"].tolist())
    return said


def _landed(clauses):
    return sorted(source for frame in prepare_v2_cursor_batch(
        snapshot(_bundle({"main": None}, exclude=clauses), catalog=CATALOG), SOURCE, _rows())
        for source in frame["source_id"].tolist())


# ------------------------------------------------------------------ the validator

def test_the_example_loads_through_the_product_validator():
    example = release_log_example()
    assert set(example) == {"c", "d"}
    base = _paths(_bundle({"c": None, "d": None}))
    assert _paths(_bundle({name: body["when"] for name, body in example.items()})) == base


@pytest.mark.parametrize("value", [{"not": "b"}, {"not": 3}, {"not": True}])
def test_is_not_takes_a_string_a_number_or_a_boolean(value):
    assert _paths(_bundle({"c": {"a": value}})) == _paths(_bundle({"c": None}))


@pytest.mark.parametrize("value", [{"not": None}, {"not": []}, {"not": [["b"]]}, {"ne": "b"}, {"not": "b", "x": 1}],
                         ids=["not-null", "not-an-empty-list", "not-a-list-of-lists", "another-operator",
                              "not-and-more"])
def test_any_other_object_is_refused_at_its_column(value):
    errors = validate_bundle_errors(_bundle({"c": {"a": value}}), catalog=CATALOG)
    new = {(e.path, e.message) for e in errors} - {
        (e.path, e.message) for e in validate_bundle_errors(_bundle({"c": None}), catalog=CATALOG)}
    assert [path for path, _ in new] == ["bundle.sources.input_rows.bind.mappings.c.when.a"], new
    assert '{"not": <one of those>}' in next(iter(new))[1]


# ------------------------------------------------------------------ the partition

def test_every_row_says_exactly_one_of_c_and_d_and_a_blank_a_says_d():
    example = release_log_example()
    said = _said(_bundle({name: body["when"] for name, body in example.items()}))

    assert len(said) == len(A_VALUES), said                      # canary: every row was mapped
    assert all(sum(name in rows for rows in said.values()) > 0 for name in ("c", "d")), said
    assert said == {"IN-0000": ["c"], "IN-0001": ["c"],             # a = b
                    "IN-0002": ["d"], "IN-0003": ["d"],             # a = other
                    "IN-0004": ["d"],                               # a NULL
                    "IN-0005": ["d"]}, said                         # a ''


def test_the_one_seat_is_the_complement_per_value_and_for_a_group():
    for value in ("b", 1, 1.0, "  b ", "other", None, "", True):
        unit = {"a": (value,)}
        assert _unit_says(unit, {"a": "b"}) != _unit_says(unit, {"a": {"not": "b"}}), value
    assert _unit_says({"n": (1.0,)}, {"n": {"not": 1}}) is False     # the same fold as equality
    mixed = {"a": ("b", "other")}
    assert (_unit_says(mixed, {"a": "b"}), _unit_says(mixed, {"a": {"not": "b"}})) == (False, False)


# ------------------------------------------------------------------ exclude_when

def test_exclude_when_is_not_keeps_only_the_rows_that_are_b():
    kept = _landed([{"when": {"a": {"not": "b"}}}])
    taken = _landed([{"when": {"a": "b"}}])

    assert kept == ["IN-0000", "IN-0001"], kept                     # the blank rows leave too
    assert taken == ["IN-0002", "IN-0003", "IN-0004", "IN-0005"], taken
    clauses = [{"when": {"a": {"not": "b"}}}]
    assert [row_excluded(clauses, {"a": v}.get) for v in A_VALUES] == [
        False, False, True, True, True, True]


class _Cursor:
    def __init__(self, counts, rows):
        self._counts, self._rows = list(counts), rows

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return (self._counts.pop(0),)

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Engine:
    """Answers the census's two counts, then the declared columns of the rows the index does not name."""

    def __init__(self, counts, rows):
        self.cursor_object = _Cursor(counts, rows)

    def raw_connection(self):
        engine = self

        class _Connection:
            def cursor(self):
                return engine.cursor_object

            def rollback(self):
                pass

            def close(self):
                pass
        return _Connection()


def test_the_census_takes_out_the_same_rows_the_read_does(monkeypatch):
    clauses = [{"when": {"a": {"not": "b"}}}]
    compiled = snapshot(_bundle({"main": None}, exclude=clauses), catalog=CATALOG)
    ids = ["RID-%04d" % i for i in range(len(A_VALUES))]
    monkeypatch.setattr(backfill, "rows_missing_from_the_index", lambda *a, **k: ids)
    setup = type("S", (), {"snapshot": compiled})()
    columns = named_columns(compiled.source_plans[SOURCE])
    assert "a" in columns                                          # canary: the clause column is read

    report = backfill.rows_not_yet_translated(
        _Engine([len(A_VALUES), 0], [tuple(row.get(c) for c in columns) for row in _rows()]),
        setup, SOURCE)

    assert (report["relation_rows"], report["indexed_rows"], report.get("excluded_rows"),
            report["not_yet"]) == (6, 0, 4, 2), report
    assert report["not_yet"] == len(_landed(clauses))


# ------------------------------------------------------------------ references

def test_a_reference_from_when_says_is_not():
    """transfer_event names a Wafer die and a DT die; «mat_type is not Wafer» puts the edge on the DT die."""
    def change(document):
        reference = copy.deepcopy(REFERENCE)
        reference["from"]["when"] = {"mat_type": {"not": "Wafer"}}
        document["entities"]["die@1"]["references"] = reference

    preview = _preview(_snapshot(change), "transfer_event", _transfer_rows())
    dt, wafer = _dies(preview, "DT"), _dies(preview, "Wafer")
    assert len(dt) == 1 and len(wafer) == 1, (dt, wafer)            # canary: both dies are named
    assert [die for die, _ in _edges(preview)] == sorted(dt)


REFUSED_VALUE = ('must be a string, number or boolean the column equals, {"not": <one of those>} '
                 'for a column that does not, or {"not": [<those>, ...]} for none of them')


def _root_with_reference_when(tmp_path, value):
    """The shipped sample with die's reference conditioned on `value`, as a config root."""
    document = json.load(open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8"))
    reference = copy.deepcopy(REFERENCE)
    reference["from"]["when"] = {"mat_type": value}
    document["entities"]["die@1"]["references"] = reference
    root = tmp_path / "root"
    root.mkdir()
    (root / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")
    return root


@pytest.mark.parametrize("value", [["Wafer", "DT"], None, {"ne": "Wafer"}],
                         ids=["a-list", "null", "another-operator"])
def test_a_reference_from_when_of_neither_form_leaves_its_entity_and_users_out(value, tmp_path):
    """총괄 10-12 QA ③: unchecked before this round. The load goes on without the entity, the
    predicates naming it and the sources using it - each left out by name, the root at the value."""
    from ledger.setup import load_setup
    from ledger.setup_bundle import load_physical_catalog

    root = _root_with_reference_when(tmp_path, value)
    setup = load_setup(str(root), catalog=load_physical_catalog(
        os.path.join(SAMPLE, "table_config.json.sample")))

    reason = setup.left_out["entity|die"]["reasons"][0]
    assert (reason["path"], reason["message"]) == (
        "bundle.entities.die.references[0].from.when.mat_type", REFUSED_VALUE)
    assert {"source_plan|transfer_event", "source_plan|die_inspection"} <= set(setup.left_out)
    assert setup.snapshot.source_plans["transfer_event"].planned is False


def test_the_setup_door_names_every_declaration_it_left_out(tmp_path, capsys, monkeypatch):
    """The pre-pull check (RUN.md): `python -m ledger.setup --root` still answers «ready», and says on
    stderr what it left out, each with its root reason, and how many."""
    from ledger import setup as setup_module
    from ledger.setup_bundle import load_physical_catalog

    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    monkeypatch.setattr(setup_module, "live_physical_catalog", lambda: catalog)
    root = _root_with_reference_when(tmp_path, ["Wafer", "DT"])

    assert setup_module.main(["--root", str(root)]) == 0
    captured = capsys.readouterr()
    lines = captured.err.splitlines()
    left = [line.split("\t") for line in lines if line.startswith("left out\t")]

    assert json.loads(captured.out)["readiness"] == "ready"
    assert ["left out", "entity|die", "bundle.entities.die.references[0].from.when.mat_type",
            REFUSED_VALUE] in left
    assert lines[-1] == "python -m ledger.setup: %d declaration(s) left out in %s" % (len(left), root)
