# -*- coding: utf-8 -*-
"""총괄 026ced7f1 (소유자 「테스트런에서 생성 원자 자세히 볼 수 없니」): the test run carries the atoms its
sampled rows became - the atoms execution hands the ledger, in the ledger's own spelling
(`store.atom_record`, which the ledger write itself goes through), each with whether execution
writes it. The rows, the atoms and the sentence counts speak of one page. Rows that carry no row
id still show their atoms, untied. On the shipped sample's `lot_slot_wafer`, rows from memory."""
import json
import os
from types import SimpleNamespace

import pytest

from test_the_test_run_reads_until_it_has_a_molecule import SAMPLE, _StubEngine, _row
from ledger import backfill, config_explorer_service, gate, runtime_v2, store
from ledger.envelope import ROW_COLUMNS
from ledger.setup_bundle import load_physical_catalog

SOURCE = "lot_slot_wafer"
LINK_FIELDS = ("sentence", "row_ids", "writes", "drop_reason")


def _document(registered_wafer=False, attribute=False):
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    source = document["sources"][SOURCE]
    if registered_wafer:
        document["vocabulary"]["register@1"]["subjects"].append("wafer@1")
        source["bind"]["mappings"]["wafer-registered"] = {"predicate": "register@1", "bind": {
            "occurred_at": {"kind": "column", "column": "event_time", "approval_status": "approved"},
            "subject": {"kind": "entity", "entity_type": "wafer@1", "approval_status": "approved",
                        "keys": {"wafer": {"kind": "column", "column": "wafer",
                                           "approval_status": "approved"}}}}}
        source["read"]["registration_probe"] = [{"entity_type": "wafer@1", "columns": ["wafer"]}]
    if attribute:
        document["entities"]["wafer@1"]["attributes"] = ["event_type"]
        source["bind"]["entities"] = {
            "wafer@1": {"attributes": {"event_type": {"kind": "column", "column": "event_type"}}}}
    return document


def _service(tmp_path, document):
    root = tmp_path / "decl"
    root.mkdir(exist_ok=True)
    (root / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    return config_explorer_service.OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts", catalog_loader=lambda: catalog)


def _run(tmp_path, document, relation, sample_rows, registered=frozenset()):
    service = _service(tmp_path, document)
    setup, _index, _ = service.active()
    asked = []

    def existing(self, connection, subjects):
        asked.append(set(subjects))
        return set(subjects) & set(registered)
    original = store.LedgerStore.existing_registrations
    store.LedgerStore.existing_registrations = existing
    try:
        plan = setup.snapshot.source_plans[SOURCE]
        result = service.test_run(_StubEngine(relation, plan.driver.cursor_columns[0]),
                                  source_id=SOURCE, sample_rows=sample_rows)
    finally:
        store.LedgerStore.existing_registrations = original
    return setup, result, asked


def _preview(setup, relation, sample_rows):
    plan = setup.snapshot.source_plans[SOURCE]
    return backfill.preview_first_batch(_StubEngine(relation, plan.driver.cursor_columns[0]),
                                        setup, SOURCE, sample_rows=sample_rows)


def _record(entry):
    return {k: v for k, v in entry.items() if k not in LINK_FIELDS}


def test_the_sample_is_what_execution_writes_spelled_as_the_ledger_writes_it(tmp_path):
    relation = [_row(i) for i in range(4)]
    setup, result, _ = _run(tmp_path, _document(registered_wafer=True, attribute=True), relation, 2)
    reading = _preview(setup, relation, 2)
    kept = runtime_v2._screened_atoms(setup.snapshot, SOURCE, reading.preview)  # execution's own
    shown_rows = {row["row_id"] for row in result["rows_sample"]}
    rows_of = {}
    for _relation, row_id, raw_ref in reading.preview.row_refs:
        rows_of.setdefault(raw_ref, set()).add(row_id)
    expected = []
    for atom in kept:
        if rows_of.get(atom.source_raw_ref, set()) & shown_rows:
            record = store.atom_record(atom)
            del record["id"]
            expected.append(record)
    assert expected                                                      # canary
    assert [_record(entry) for entry in result["atoms_sample"]] == expected
    assert all(entry["writes"] and entry["drop_reason"] is None for entry in result["atoms_sample"])


def test_the_ledger_write_goes_through_the_same_record(monkeypatch, tmp_path):
    import psycopg2.extras

    relation = [_row(i) for i in range(3)]
    setup, _result, _ = _run(tmp_path, _document(registered_wafer=True, attribute=True), relation, 3)
    atoms = runtime_v2._screened_atoms(setup.snapshot, SOURCE, _preview(setup, relation, 3).preview)
    written = []
    monkeypatch.setattr(psycopg2.extras, "execute_values",
                        lambda cursor, sql, rows, page_size=None: written.extend(rows))

    class _Cursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    connection = SimpleNamespace(cursor=_Cursor)
    store.LedgerStore.insert_atoms(SimpleNamespace(names=SimpleNamespace(ledger="ledger")),
                                   connection, atoms)
    assert len(written) == len(atoms) > 0                                # canary
    for row, atom in zip(written, atoms):
        record = store.atom_record(atom)
        assert [getattr(value, "adapted", value) for value in row] == [
            str(record[c]) if c == "id" else record[c] for c in ROW_COLUMNS]


def test_a_role_attribute_shows_on_its_own_registration_not_inside_the_relation(tmp_path):
    _setup, result, _ = _run(tmp_path, _document(registered_wafer=True, attribute=True),
                             [_row(i) for i in range(2)], 1)
    by_sentence = {entry["sentence"]: entry for entry in result["atoms_sample"]}
    assert by_sentence["wafer-registered"]["object_payload"] == {"qualifiers": {"event_type": "track_in"}}
    assert "qualifiers" not in by_sentence["seat-holds-wafer"]["object_payload"]


def test_every_atom_points_into_the_rows_shown_and_none_comes_from_outside(tmp_path):
    _setup, result, _ = _run(tmp_path, _document(), [_row(i) for i in range(4)], 2)
    shown = {row["row_id"] for row in result["rows_sample"]}
    assert result["atoms"] == 4 and shown == {"ROW-000", "ROW-001"}      # canary: the page made more
    assert {r for entry in result["atoms_sample"] for r in entry["row_ids"]} == shown
    assert all(set(entry["row_ids"]) <= shown for entry in result["atoms_sample"])


def test_the_rows_the_atoms_and_the_sentences_come_from_one_page(tmp_path):
    """A blank head as long as a page: the run reads on to the page that compiles, and the rows
    it shows are that page's - not the head's."""
    document = _document()
    document["sources"][SOURCE]["read"]["exclude_when"] = [{"column": "wafer", "blank": True}]
    blank = backfill.PREVIEW_FETCH_ROWS
    relation = [_row(i, filled=False) for i in range(blank)] + [_row(i) for i in range(blank, blank + 3)]
    _setup, result, _ = _run(tmp_path, document, relation, 2)
    assert result["pages"] == 2 and result["atoms"] == 3                 # canary: the head was skipped
    first_page = {"ROW-%03d" % i for i in range(blank - 1)}             # cut on a group boundary
    shown = [row["row_id"] for row in result["rows_sample"]]
    assert len(shown) == 2 and not set(shown) & first_page
    assert result["atoms_sample"]
    assert all(set(entry["row_ids"]) <= set(shown) for entry in result["atoms_sample"])


def test_rows_with_no_row_id_are_refused_before_any_atom(tmp_path):
    """Every planned source reads rows that carry a row id (총괄 f3bc02f6e), so there is no
    untied sample to show: such rows stop the run before an atom exists."""
    relation = [{k: v for k, v in _row(i).items() if k != "row_id"} for i in range(3)]
    _setup, result, _ = _run(tmp_path, _document(), relation, 2)
    assert (result["status"], result["refusal"]["code"]) == ("refused", "source_preparation_incomplete")
    assert "atoms_sample" not in result


def test_more_atoms_than_the_limit_are_cut_and_counted(tmp_path):
    over = runtime_v2.ATOMS_SAMPLE_LIMIT + 7
    _setup, result, _ = _run(tmp_path, _document(), [_row(i) for i in range(over)], over)
    assert len(result["atoms_sample"]) == runtime_v2.ATOMS_SAMPLE_LIMIT
    assert (result["truncated"]["atoms_sample"]["cut"], result["truncated"]["atoms_sample"]["omitted"]) == (True, 7)


def test_a_registration_the_ledger_already_holds_is_shown_dropped(tmp_path):
    from ledger.envelope import registration_token

    held = registration_token("wafer", {"wafer": "W000"})
    _setup, result, asked = _run(tmp_path, _document(registered_wafer=True), [_row(i) for i in range(5)],
                                 3, registered={held})
    assert result["atoms"] == 10                                         # canary: the page has more
    registrations = [e for e in result["atoms_sample"] if e["sentence"] == "wafer-registered"]
    assert [(e["subject_keys"]["wafer"], e["writes"], e["drop_reason"]) for e in registrations] == [
        ("W000", False, runtime_v2.DROP_ALREADY_REGISTERED), ("W001", True, None), ("W002", True, None)]
    # one narrowed read: the shown registrations' subjects, nothing else
    assert asked == [{registration_token("wafer", {"wafer": "W%03d" % i}) for i in range(3)}]


def test_a_gate_refusal_marks_every_atom_and_moves_no_process_counter(monkeypatch, tmp_path):
    real = gate.screen_compiled_molecule

    def refusing(source, atoms, *args, **kwargs):
        gate.refuse(source, gate.REFUSE_ATOMICITY, "forced by the gate test")
        return real(source, atoms, *args, **kwargs)
    monkeypatch.setattr(gate, "screen_compiled_molecule", refusing)
    before = gate.refusals()
    _setup, result, _ = _run(tmp_path, _document(), [_row(i) for i in range(2)], 2)
    assert result["atoms_sample"]                                        # canary
    assert {(e["writes"], e["drop_reason"]) for e in result["atoms_sample"]} == {
        (False, gate.REFUSE_ATOMICITY)}
    assert gate.refusals() == before
