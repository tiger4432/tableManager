"""«Not adopted» (owner 11-08 ㄱ): the chain worker counts, a page at a time, the chain's layers no rule owns - written
before ownership - by who wrote them and the tables they hold; GET /admin/chain/rules reads the last lap."""
from sqlalchemy.orm import sessionmaker

from tests.test_a_chain_groups_writes_are_one_commit import fixture_db, DST  # noqa: F401
from chain import cell_layer
from chain import ingestion_worker as worker
from database import crud, schemas
from utils import heartbeat


def _layer(db, key, name, by):
    crud.apply_batch_updates(db, DST, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"k": key, "w": name}, source_name=name, updated_by=by)]))


def test_the_lap_counts_unowned_chain_layers_by_writer_and_the_route_reads_it(db, monkeypatch):
    _layer(db, "K1", crud.CHAIN_SOURCE, "chain_worker")
    _layer(db, "K2", crud.CHAIN_SOURCE, "old_rule")
    _layer(db, "K3", crud.owned_layer_name("new_rule", "K3"), "new_rule")
    _layer(db, "K4", crud.USER_SOURCE, "kim")
    db.commit()
    monkeypatch.setattr(cell_layer, "DEFAULT_CHUNK_SIZE", 2)
    monkeypatch.setattr("pacing.job_pace", lambda job: (1, 0))
    said = []

    names = worker.count_unowned_layers_sync(sessionmaker(bind=db.get_bind()), log=said.append)

    # the key column «k» is a chain layer too on the chain's rows (the row was made by that write)
    assert {row["name"]: row["layers"] for row in names} == {"chain_worker": 2, "old_rule": 2}
    assert all(row["tables"] == [[DST, 2]] for row in names)
    lap = heartbeat._laps["chain"][worker.UNOWNED_CENSUS_LOOP]
    assert lap["layers"] == 4 and lap["depth"] >= 4 and lap["not_adopted"] == names    # four writes, a line each
    assert said and said[0].startswith("[ChainUnowned] pass: 4 layer(s) under 2 name(s) no rule owns")

    import main
    monkeypatch.setattr(main._heartbeat_mod, "read_all", lambda: {"chain": {"laps": {worker.UNOWNED_CENSUS_LOOP: lap}}})
    monkeypatch.setattr(worker, "read_rules_document", lambda *a, **k: {"exists": True, "error": None, "rules": [], "document": {"rules": []}})
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: [])
    answer = main.get_chain_rules(db=db)
    assert answer["not_adopted"] == {"at": lap["at"], "layers": 4, "names": names}


def test_before_a_lap_ended_the_route_says_none(db, monkeypatch):
    import main
    monkeypatch.setattr(main._heartbeat_mod, "read_all", lambda: {"chain": {"laps": {}}})
    monkeypatch.setattr(worker, "read_rules_document", lambda *a, **k: {"exists": True, "error": None, "rules": [], "document": {"rules": []}})
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: [])
    assert main.get_chain_rules(db=db)["not_adopted"] is None
