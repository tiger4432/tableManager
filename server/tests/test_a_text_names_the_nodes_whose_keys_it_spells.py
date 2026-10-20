# -*- coding: utf-8 -*-
"""총괄 a10d88cd7 — a text's mentions: each text row names the nodes whose keys it spells, one mention row each.

    운영에서는 체인 규칙 하나에 맵퍼 link_mentions 와 params(글 칸 · 옮길 칸 · 타입 칸 · 키 칸 · node_types)를 적고,
    원장 소스가 그 언급 표를 읽어 타입마다 술어 하나를 bind 하면 됩니다.

The match is `text_links._matches` (총괄 ① ㄱ): the four sentences measured on 10-21, where the loose match named
L1234 and L12345 in "L123 and 2345", are cells here.
"""
import json
import os
import re
import sys

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from mapper_sdk import MapperContractError                          # noqa: E402
from mappers import doc_mentions                                    # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

TEXT, MENTION = "dm_text", "dm_mention"
TABLES = {TEXT: {"business_key": "chunk_id", "column_types": {c: "string" for c in ("chunk_id", "document", "body")},
                 "display_columns": ["chunk_id", "document", "body"]},
          MENTION: {"composite_key_source": ["chunk_id", "node_type", "node_key"], "composite_key_separator": "|",
                    "column_types": {c: "string" for c in ("chunk_id", "document", "node_type", "node_key")},
                    "display_columns": ["chunk_id", "document", "node_type", "node_key"]}}
PARAMS = {"text_column": "body", "copy_columns": ["chunk_id", "document"], "type_column": "node_type",
          "key_column": "node_key", "node_types": ["lot", "wafer", "process"]}
RULES = [{"name": "dm_mentions", "trigger_table": TEXT, "target_table": MENTION, "mapper": doc_mentions.NAME,
          "is_batch": True, "params": PARAMS}]
#: the names of 10-21's measure: lot L1234 · L12345, wafer W01, process "dry etch"
NODES = {"lot": ["L1234", "L12345"], "wafer": ["W01"], "process": ["dry etch"]}
DECLARED = {"lot": ["lot"], "wafer": ["wafer"], "process": ["process"], "lot_slot": ["lot", "slot"]}


def _world(monkeypatch, tables):
    from ledger_api import declared_entities

    monkeypatch.setattr(declared_entities, "identity_keys", lambda bare: list(DECLARED.get(bare, ())))
    monkeypatch.setattr(doc_mentions, "_keys_of", lambda db, bare, axis: list(NODES[bare]))
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    doc_mentions._register()
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in tables:
            crud.TABLE_CONFIG.pop(name, None)


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    yield from _world(monkeypatch, TABLES)


def _write(db, rows, table=TEXT, rules=RULES):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates=dict(r), source_name="seed", updated_by="dm") for r in rows]))
    db.commit()
    _drain(db, rules)


def _drain(db, rules=RULES):
    for _ in range(6):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, [dict(r) for r in rules])
            assert ok, error
            deleted = worker._deleted_rows_of(events)
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
            worker._retract_deleted_rows(db, deleted)    # where the worker ends a group
    raise AssertionError("the chain did not settle")


def _mentions(db):
    """Every row of the mention table - one its text stopped naming goes, not left as a row of keys (총괄 10-21 ㄱ)."""
    db.expire_all()
    return sorted(tuple("" if v is None else v for v in (r.chunk_id, r.document, r.node_type, r.node_key))
                  for r in db.query(models.DYNAMIC_TABLES[MENTION]).all())


@pytest.mark.parametrize("text, named", [
    ("L123 and 2345 were fine", []),                                   # loose: L1234 · L12345
    ("L12345 only", [("lot", "L12345")]),                              # loose: L1234 too
    ("lot L1234 had a dry etch issue on W01", [("lot", "L1234"), ("process", "dry etch"), ("wafer", "W01")]),
    ("W01 웨이퍼의 dry  ETCH 공정", [("process", "dry etch"), ("wafer", "W01")]),
    ("Z999 only", []),
])
def test_a_text_names_a_node_only_where_it_spells_the_whole_key(db, text, named):
    _write(db, [{"chunk_id": "C1", "document": "D1", "body": text}])
    assert _mentions(db) == [("C1", "D1", t, k) for t, k in named]


def test_an_edited_text_takes_back_what_it_no_longer_names(db):
    _write(db, [{"chunk_id": "C1", "document": "D1", "body": "L1234 on W01"},
                {"chunk_id": "C2", "document": "D1", "body": "W01 again"}])
    assert len(_mentions(db)) == 3, "CANARY: three mentions before the edit"
    _write(db, [{"chunk_id": "C1", "document": "D1", "body": "L12345 now"}])
    assert _mentions(db) == [("C1", "D1", "lot", "L12345"), ("C2", "D1", "wafer", "W01")]
    _write(db, [{"chunk_id": "C1", "document": "D1", "body": "no name now"}])    # a blank write is no edit
    assert _mentions(db) == [("C2", "D1", "wafer", "W01")]


#: the shape most shipped composite tables have - the business key a column of its own beside the composite
WITH_KEY_COLUMN = {TEXT: TABLES[TEXT], MENTION: dict(
    TABLES[MENTION], business_key="mention_key",
    column_types=dict(TABLES[MENTION]["column_types"], mention_key="string"))}


def test_a_business_key_column_is_a_key_so_the_row_still_goes(monkeypatch):
    """총괄 10-21 ②: `mention_key` read as a shown column kept every withdrawn mention as a row of keys."""
    world = _world(monkeypatch, WITH_KEY_COLUMN)
    db = next(world)
    try:
        _write(db, [{"chunk_id": "C1", "document": "D1", "body": "L1234 on W01"}])
        assert len(_mentions(db)) == 2, "CANARY: two mentions before the edit"
        _write(db, [{"chunk_id": "C1", "document": "D1", "body": "W01 only"}])
        assert _mentions(db) == [("C1", "D1", "wafer", "W01")]
    finally:
        world.close()


def test_a_fresh_process_whose_first_run_names_nothing_still_takes_back(db):
    """Before a run proposes rows, the mapper's declared facts answer (`stamps_origin` · `columns`)."""
    from chain import rule_run

    _write(db, [{"chunk_id": "C1", "document": "D1", "body": "L1234 on W01"}])
    rule_run._ORIGIN_SEEN.clear()
    rule_run._COLUMNS_SEEN.clear()
    _write(db, [{"chunk_id": "C1", "document": "D1", "body": "no name now"}])
    assert _mentions(db) == []


def test_a_deleted_text_takes_back_its_own_mentions(db):
    _write(db, [{"chunk_id": "C1", "document": "D1", "body": "L1234 on W01"},
                {"chunk_id": "C2", "document": "D1", "body": "W01 again"}])
    texts = models.DYNAMIC_TABLES[TEXT]
    crud.delete_rows_batch(db, TEXT, [db.query(texts).filter(texts.chunk_id == "C1").one().row_id], "dm")
    db.commit()
    _drain(db)
    assert _mentions(db) == [("C2", "D1", "wafer", "W01")]


@pytest.mark.parametrize("node_types, said", [
    ([], "node_types is empty"),
    (None, "node_types is empty"),
    (["lot", "carrier"], "'carrier' is not a declared entity type"),
    (["lot_slot"], "'lot_slot' has 2 keys (lot, slot)"),
])
def test_a_type_list_it_cannot_read_is_refused_by_name(db, node_types, said):
    with pytest.raises(MapperContractError, match=re.escape(said)):
        doc_mentions._names(db, node_types)


# ------------------------------------------------------------------- the ledger's half: the sample

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")


def _shipped(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(name="shipped_db")
def fixture_shipped_db(monkeypatch):
    tables = _shipped("table_config.json.sample")
    picked = {name: tables[name] for name in ("doc_chunk", "doc_mention")}
    for spec in picked.values():       # SQLite's DateTime takes no text, and the write seat hands it text
        spec["column_types"]["written_at"] = "string"
    yield from _world(monkeypatch, picked)


def test_the_sample_walks_from_a_node_to_the_text_that_names_it(shipped_db):
    """The shipped rule writes the shipped mention table; the shipped source translates it; the walk from the lot
    reaches its chunk."""
    import uuid
    from ledger import explorer
    from ledger.implementations import role_mapper_registry, trusted_implementations
    from ledger.runtime_v2 import preview_cursor_batch
    from ledger.setup_bundle import load_physical_catalog, require_ready_bundle, validate_bundle
    from ledger.setup_registry import compile_setup_snapshot
    from ledger_api import ledger_subgraph

    rules = [r for r in _shipped("chain_rules.json.sample")["rules"] if r.get("name") == "doc_chunk_to_doc_mention"]
    written = "2026-10-21 09:00:00"
    _write(shipped_db, [{"chunk_id": "C1", "document": "D1", "written_at": written,
                         "chunk_text": "lot L1234 on W01, dry etch"},
                        {"chunk_id": "C2", "document": "D1", "written_at": written,
                         "chunk_text": "nothing here"}], table="doc_chunk", rules=rules)
    shipped_db.expire_all()
    mentions = models.DYNAMIC_TABLES["doc_mention"]
    frame = pd.DataFrame([{"row_id": r.row_id, "chunk_id": r.chunk_id, "document": r.document,
                           "node_type": r.node_type, "node_key": r.node_key,
                           "written_at": pd.Timestamp(r.written_at).tz_localize("Asia/Seoul")}
                          for r in shipped_db.query(mentions).order_by(mentions.node_type).all()])
    assert sorted(zip(frame["chunk_id"], frame["node_type"], frame["node_key"])) == [
        ("C1", "lot", "L1234"), ("C1", "wafer", "W01")], "the shipped rule loads lot and wafer, not process"

    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    snapshot = compile_setup_snapshot(
        require_ready_bundle(validate_bundle(_shipped("ledger_config.json.sample"), catalog=catalog)),
        trusted_implementations(), catalog=catalog)
    preview = preview_cursor_batch(snapshot, "doc_mention", frame,
                                   {"row_id": frame.iloc[-1]["row_id"]},
                                   role_mapper_registry(), known_registrations=())
    said = sorted((a["predicate"], a["subject_keys"]["chunk"], a["object_payload"]["type"],
                   json.dumps(a["object_payload"]["keys"])) for a in preview.candidate_semantics)
    assert said == [("mentions", "C1", "lot", '{"lot": "L1234"}'), ("mentions", "C1", "wafer", '{"wafer": "W01"}')]

    when = frame.iloc[0]["written_at"].to_pydatetime()
    atoms = [ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=n + 1)), subject_type="doc_chunk", subject_keys=a["subject_keys"],
        predicate=a["predicate"], object_kind="entity_ref", object_payload=a["object_payload"], occurred_at=when,
        source_who="doc_mention", source_translator_ver="v1", source_raw_ref="row:%d" % n, supersedes=None,
        source_event_id=str(uuid.UUID(int=900 + n)), source_event_state="source_molecule")
        for n, a in enumerate(preview.candidate_semantics)]
    body = ledger_subgraph.subgraph(explorer.entity_id("lot", {"lot": "L1234"}),
                                    ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=1)
    assert explorer.entity_id("doc_chunk", {"chunk": "C1"}) in {node["id"] for node in body["nodes"]}
