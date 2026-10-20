# -*- coding: utf-8 -*-
"""총괄 88761926b: a decide rule's derived row keyed by a PLAIN key column is named in that column's spelling - the
source's text «001» is the number key «1» (`crud.compose_business_key`), as the write keys the row. Spelled as the source
gave it, the key the rule says is gone («001») named no row (stored «1») and the derived row stayed when its last source
row left.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import anyio                                                          # noqa: E402
import pytest                                                         # noqa: E402

from database import crud, models, schemas                            # noqa: E402
from tests.support.enrich_decl import enrich_chain_rules, write_rules  # noqa: E402

SRC, DERIVED = "zz_plain_spell_src", "zz_plain_spell_derived"
TABLES = {
    SRC: {"business_key": "src_id", "column_types": {"src_id": "string", "lot": "string", "wafer": "string"}},
    DERIVED: {"business_key": "lot", "column_types": {"lot": "number", "wafer": "string", "n": "number"}},
}
RULE = {"zz_plain_spell": {"source_table": SRC, "derived_table": DERIVED, "decision_key": ["lot"],
                           "target_fields": ["wafer"], "aggregations": {"n": "count"}}}


@pytest.fixture()
def env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    write_rules(tmp_path, monkeypatch, RULE)
    return db_session


def _write(db, item, tx_id):
    crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(source_name="pipeline_parser", updated_by="watcher", **item)],
        transaction_id=tx_id, silent=True))


def _chain(db, tx_id):
    from chain.ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrich_chain_rules(known_tables=crud.TABLE_CONFIG)
    events = [e for e in db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == SRC,
                                                          DatabaseOutbox.processed_chain == False)  # noqa: E712
              .order_by(DatabaseOutbox.id.asc()).all() if (e.payload or {}).get("transaction_id") == tx_id]
    assert events, tx_id

    async def run():
        ok, err, _ = await process_chain_transaction_group(tx_id, events, db, rules)
        assert ok, err
        for e in events:
            e.processed_chain = True
        db.commit()
    anyio.run(run)


def _derived(db):
    return [(r.business_key_val, r.n) for r in db.query(models.DYNAMIC_TABLES[DERIVED]).all()]


def test_the_derived_row_goes_when_its_last_source_row_leaves_its_key(env):
    _write(env, {"business_key_val": "S1", "updates": {"src_id": "S1", "lot": "001", "wafer": "W1"}}, "tx-1")
    _chain(env, "tx-1")
    assert _derived(env) == [("1", 1)]                       # canary: the number key's spelling

    row_id = env.query(models.DYNAMIC_TABLES[SRC]).one().row_id
    _write(env, {"row_id": row_id, "updates": {"lot": "002"}}, "tx-2")
    _chain(env, "tx-2")
    assert sorted(_derived(env)) == [("2", 1)]
