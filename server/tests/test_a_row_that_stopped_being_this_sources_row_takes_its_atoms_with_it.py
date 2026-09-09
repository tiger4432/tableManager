# -*- coding: utf-8 -*-
"""S-101, ruling 199, grade 1. A row the declaration no longer translates KEPT its atoms.

🔴 THE AIM WENT EMPTY IN EXACTLY THE CASE THAT NEEDED IT. `rescope` withdrew the refs the
CURRENT declaration makes from the rows in scope -- so a row that is no longer this source's
row produces no ref, the aim is empty, and `rescope` returned before writing anything.
Measured on the applied experiment: 5 rows in scope, 10 atoms already written, 5 index rows,
`exclude_when` added, refs previewed 0, and the 10 atoms and 5 index rows STAYED.

⚠️ NOT A DEPLOYMENT-ONLY DOOR. An EDIT that merely blanks the declared column arrives at the
same place through the follow-up, which calls this with `withdraw=True`.

The withdrawal is now aimed from `schema.ROW_REF_TABLE` -- the note taken while the row still
spoke -- which is the instrument `withdraw_deleted_rows` already used. A row that STOPS being
translated is withdrawn by the same road as a row that was deleted.

⛔ THE UNION, NOT THE DIFFERENCE. Ruling 199 names the difference because that is what this
ADDS; the refs the new generation re-creates must be withdrawn as well or the old generation
stands beside the new one, which is the S-60 hazard.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                          # noqa: E402
from ledger.implementations import (role_mapper_registry,            # noqa: E402
                                    source_preparer_registry,
                                    trusted_implementations)
from ledger.setup import LedgerSetup                                 # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,              # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot             # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
SOURCE = "dt_job"
RELATION = "dt_log"
JOB = "SYN-DTJ-002-04"
OCCURRED_AT = datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc)

#: What the ledger already said about those five rows, taken while they still spoke. Two
#: refs on one row is the ordinary shape - one physical row appears under several claim refs
#: when a source emits more than one sentence over different subsets.
INDEXED = {"r0": ["old-a"], "r1": ["old-b"], "r2": ["old-c"],
           "r3": ["old-d"], "r4": ["old-e", "old-e-2"]}


def compiled(exclude_when=None):
    """The shipped declaration, compiled IN MEMORY, optionally with a clause added.

    The operator's edit is one key in one source's `prepare`; everything else - catalogue,
    validation, compile - is the product's own path, so what this scores is the declaration
    rather than a bundle assembled for the test.
    """
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    if exclude_when is not None:
        document["sources"][SOURCE]["prepare"]["exclude_when"] = exclude_when
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), (), catalog=catalog)
    return LedgerSetup(config_root=Path(SAMPLE), bundle=bundle, snapshot=snapshot,
                       preparers=source_preparer_registry(),
                       mappers=role_mapper_registry(), catalog=catalog)


@pytest.fixture(scope="module")
def setup():
    return compiled()


@pytest.fixture(scope="module")
def setup_excluding():
    return compiled([{"column": "dt_eqp", "blank": True}])


def rows(count=5, eqp="EQP-7"):
    """Five rows of one `dt_job` group.

    ⚠️ THE CLAUSE IS ON `dt_eqp` RATHER THAN ON AN IDENTITY PART, and the reason is a
    measurement: `dt_job` reads its cursor from `dt_job, dt_cell_key`, and a batch whose last
    row leaves a CURSOR column blank is refused by name (`cursor_value.<column>: cursor value
    is missing`) before any of this is reached. So a source cannot be made to stop
    translating by blanking one of those - the refusal arrives first, and it is a different
    question. `dt_eqp` is a column the clause can name and the cursor does not.
    """
    return [{"created_at": OCCURRED_AT, "dt_cell_key": f"C{index}",
             "dt_eqp": eqp, "dt_index": index, "dt_job": JOB,
             "event_time": OCCURRED_AT, "row_id": f"r{index}"}
            for index in range(count)]


class Reader:
    """Every connection `rescope` and the preview open for themselves. Reads only."""

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return (0,)

    def fetchall(self):
        return []

    def rollback(self):
        pass

    def close(self):
        pass


class IndexStore:
    """A store that knows what the index says and records what it is asked to remove."""

    def __init__(self, indexed=None):
        self.indexed = INDEXED if indexed is None else indexed
        self.writes = []
        self.forgotten = []
        self.asked_for_rows = None
        #: The ORDER the two statements were asked for in, which is load-bearing.
        self.log = []

    def connection(self):
        return Reader()

    def row_refs_for(self, relation, row_ids):
        self.asked_for_rows = (relation, tuple(row_ids))
        return [(SOURCE, ref)
                for row_id in row_ids
                for ref in self.indexed.get(str(row_id), ())]

    def write_batch(self, *args, **kwargs):
        self.writes.append(kwargs)
        self.log.append("write")
        return {"attempted": 0, "inserted": 0, "deduped": 0, "molecules": 0,
                "withdrawn": len(kwargs.get("withdraw_refs") or ())}

    def forget_row_refs(self, relation, row_ids, source=None):
        self.forgotten.append({"relation": relation, "row_ids": tuple(row_ids),
                               "source": source})
        self.log.append("forget")
        return len(tuple(row_ids))


def run(setup, monkeypatch, store, relation_rows, withdraw=True):
    """A real `preview_rescope` over patched READS, so the aim comes from the compiler.

    🔴 THE PREVIEW IS NOT STUBBED HERE, and that is the point: "the declaration produces no
    ref for these rows" has to be something the declaration DOES, not something the test
    asserts by handing in an empty list.
    """
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows",
                        lambda *a, **k: relation_rows)
    monkeypatch.setattr("ledger.store.LedgerStore", lambda engine: store)
    engine = SimpleNamespace(raw_connection=Reader)
    return backfill.rescope(engine, setup, SOURCE, "dt_job", [JOB],
                            apply=True, withdraw=withdraw)


def withdrawn_refs(store):
    assert len(store.writes) == 1, store.writes
    return sorted(store.writes[0].get("withdraw_refs") or ())


def indexed_refs():
    return sorted({ref for refs in INDEXED.values() for ref in refs})


# ------------------------------------------------------------------ the headline


def test_the_atoms_of_an_excluded_row_are_withdrawn_instead_of_left(
        setup_excluding, monkeypatch):
    """🔴 THE DEFECT, AS A TEST. Every row in scope is excluded by the clause, so the new
    translation names nothing; the index still names what this source said, and that is what
    the withdrawal is aimed with. Before S-101 this returned with `applied` False and made no
    store call at all."""
    store = IndexStore()
    result = run(setup_excluding, monkeypatch, store, rows(eqp="  "))

    assert result["applied"] is True
    assert withdrawn_refs(store) == indexed_refs(), (
        "the refs the index holds for the rows in scope must all be withdrawn")
    assert result["withdrawn"] == len(indexed_refs())
    assert store.writes[0]["advance_cursor"] is False
    # Nothing replaces them - the rows are not this source's rows any more.
    assert result["inserted"] == 0

    # ⚠️ AND THE EDIT DOOR IS THIS SAME CALL, not a second seam to score: `followup` follows
    # an EDIT with `rescope(..., apply=True, withdraw=(event_type != "CREATE"))`, which is
    # the call above. A clause deployed long ago and a row edited to blank today arrive here
    # identically, which is why the applied experiment saw both turn back at one line.


def test_the_index_rows_go_last_and_only_this_sources_lines(
        setup_excluding, monkeypatch):
    """🔴 ORDER AND WIDTH, both stated by `withdraw_deleted_rows` and both load-bearing.

    LAST, because while the index rows are here the withdrawal can be run again; a run that
    dies between the two leaves an index row pointing at atoms already withdrawn, which the
    next pass reads as "nothing to withdraw" and then clears.

    ONLY THIS SOURCE, because the row is still THERE. A deleted row is gone for everybody and
    that call passes no source; here another source reading `dt_log` still speaks for these
    rows, and dropping its line would leave its atoms with no index row at all.
    """
    store = IndexStore()
    result = run(setup_excluding, monkeypatch, store, rows(eqp=""))

    assert store.log == ["write", "forget"], (
        "the index line must outlive the withdrawal it aims: dropped first, a run that dies "
        "between the two is unrepeatable")
    assert len(store.forgotten) == 1, store.forgotten
    forgotten = store.forgotten[0]
    assert forgotten["relation"] == RELATION
    assert sorted(forgotten["row_ids"]) == sorted(INDEXED)
    assert forgotten["source"] == SOURCE, (
        "a rescope drops its own index lines, not every source's")
    assert result["forgotten"] == len(INDEXED)


def test_a_row_the_new_generation_still_names_keeps_its_index_line(setup, monkeypatch):
    """The control, and the half that must NOT change: with no clause the same five rows
    still translate, so the write indexes them again and nothing is forgotten."""
    store = IndexStore()
    result = run(setup, monkeypatch, store, rows())

    assert result["applied"] is True
    assert store.forgotten == [], "these rows still speak; their index lines stand"
    assert result["forgotten"] == 0


def test_the_refs_the_new_generation_makes_are_withdrawn_too(setup, monkeypatch):
    """⛔ THE UNION, NOT THE DIFFERENCE (the mutation this file exists to catch second).

    Ruling 199 spells the addition as a difference. Passing only the difference would leave
    the previous generation of a row that STILL translates standing beside the new one -- the
    S-60 hazard, arrived at from the other side. So the refs the preview makes have to be in
    the aim as well, which is what this reads.
    """
    store = IndexStore()
    run(setup, monkeypatch, store, rows())

    aimed = set(withdrawn_refs(store))
    assert set(indexed_refs()) <= aimed, "the index's refs are in the aim"
    assert aimed - set(indexed_refs()), (
        "the refs the current translation makes must be withdrawn too, or the old "
        "generation of a corrected row stands beside the new one")


# ------------------------------------------------------------------ what must not move


def test_nothing_happens_when_neither_the_index_nor_the_preview_names_anything(
        setup_excluding, monkeypatch):
    """The rule that replaces the old early return. It used to fire whenever the PREVIEW was
    empty, which is the defect; it now fires only when there is nothing to withdraw at all
    and nothing to put in its place."""
    store = IndexStore(indexed={})
    result = run(setup_excluding, monkeypatch, store, rows(eqp=""))

    assert store.writes == [] and store.forgotten == []
    assert result["applied"] is False and result["withdrawn"] == 0


def test_a_create_still_translates_once(setup, monkeypatch):
    """판정 166. `withdraw=False` is the CREATE path: a row that has just been created holds
    no atoms, so the preview that would aim a withdrawal answers a question with no content
    and is not free. It must not have gained an index read either."""
    store = IndexStore()
    result = run(setup, monkeypatch, store, rows(), withdraw=False)

    assert store.asked_for_rows is None, "a create asks the index nothing"
    assert store.forgotten == []
    assert not withdrawn_refs(store)
    assert result["previewed"] is False and result["applied"] is True


# ------------------------------------------- the cost of the change, as a census value


class CensusStore(IndexStore):
    """Adds the one reader the census asks: which of these rows the index names."""

    def __init__(self, indexed_rows=()):
        super().__init__()
        self.indexed_rows = set(indexed_rows)
        self.asked = None

    def indexed_row_ids(self, relation, row_ids, source):
        self.asked = (relation, tuple(row_ids), source)
        return {row_id for row_id in row_ids if row_id in self.indexed_rows}


def count(setup, monkeypatch, store, page):
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_page", lambda *a, **k: page)
    monkeypatch.setattr("ledger.store.LedgerStore", lambda engine: store)
    return backfill.count_excluded_but_indexed(
        SimpleNamespace(raw_connection=Reader), setup, SOURCE)


def test_the_census_counts_rows_the_declaration_now_excludes_but_the_index_still_names(
        setup_excluding, monkeypatch):
    """🔴 THE COST OF A DECLARATION CHANGE, AS A NUMBER (ruling 199). Adding `exclude_when`
    does not un-write what the source already said: those rows keep their atoms until a scope
    is run. This is how much is waiting - and 0 and 「nobody counted」 are different answers,
    which is why the key is absent rather than zero when there is no clause."""
    page = [dict(row, dt_eqp=("" if index < 3 else "EQP-7"))
            for index, row in enumerate(rows())]
    store = CensusStore(indexed_rows={"r0", "r2"})

    excluded, read = count(setup_excluding, monkeypatch, store, page)

    assert (excluded, read) == (2, 5), (
        "three rows are blank, two of them are indexed; the third was never translated "
        "and is not a backlog")
    assert store.asked[0] == RELATION and store.asked[2] == SOURCE
    assert sorted(store.asked[1]) == ["r0", "r1", "r2"], (
        "only the excluded rows are asked about")


def test_a_source_with_no_clause_asks_nothing_at_all(setup, monkeypatch):
    """The arm that must NOT fire. Without it every source would pay a page read and report
    a zero that means 「this source excludes nothing」 dressed as 「nothing is waiting」."""
    store = CensusStore(indexed_rows={"r0"})

    assert count(setup, monkeypatch, store, rows()) == (0, 0)
    assert store.asked is None


def test_the_number_is_stamped_as_a_sample_with_its_method(setup_excluding, monkeypatch):
    """⚠️ THE OTHER CENSUS NUMBERS ARE FULL SCANS AND THIS ONE IS NOT, so it has to say so
    itself. 「blank」 is a python predicate (판정 194 ㉢ made it ONE function); asking a whole
    relation would mean spelling it a second time in SQL, and two spellings disagree exactly
    about the values in dispute. Ruling of 2026-09-09: sample it and stamp it."""
    monkeypatch.setattr(backfill, "rows_not_yet_translated", lambda *a, **k: {
        "source": SOURCE, "relation": RELATION, "relation_rows": 5, "indexed_rows": 5,
        "counts": "rows", "not_yet": 0})
    monkeypatch.setattr(backfill, "count_excluded_but_indexed", lambda *a, **k: (2, 5))

    stamped = backfill.measure_row_census(SimpleNamespace(), setup_excluding, SOURCE)

    assert stamped["excluded_but_indexed"]["estimate"] == 2
    assert stamped["excluded_but_indexed"]["exact"] is False, (
        "a sample rendered as an exact count is the 「about 13 million」 defect `measured` "
        "exists to stop")
    assert "5 rows" in stamped["excluded_but_indexed"]["method"]
