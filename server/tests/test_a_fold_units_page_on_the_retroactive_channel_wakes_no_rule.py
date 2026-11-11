"""Before fold-units writes through the funnel (lead 11-11 ㄱ, scratchpad ruling): a page of a fold rule's marks written
by the door the move will use - crud.apply_batch_updates in collapsed mode - inside a retroactive run's channel stages
ONE outbox row and wakes NO rule, an opt-in one included (owner 09-26 «큰 소급으로 한 거 체인 연쇄 안 되게»,
chain_ingestion_guide §5.6). The same page off the channel wakes the opt-in rule - the control that the rule would
wake, so the 0 is the channel's doing."""
import pytest

import event_constants
from chain import ingestion_worker as worker
from database import crud, models, schemas
from database.context import channel, outbox_mode
from support import line_tables

LOG, MARK = "fu_retro_log", "fold_mark"
TABLES = {LOG: {"business_key": "record_id", "column_types": {"record_id": "string", MARK: "string"}}}
RULE = {"name": "fu_retro_optin", "trigger_table": LOG, "target_table": "fu_retro_elsewhere",
        "mapper": "production_mapper", "allow_chain_trigger": True}


@pytest.fixture()
def db(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    line_tables.build(db_session.get_bind(), LOG)
    yield db_session
    db_session.rollback()
    line_tables.drop(db_session.get_bind(), LOG)
    from conftest import retire_dynamic_model
    retire_dynamic_model(LOG)
    crud.TABLE_CONFIG.pop(LOG, None)


def _page(db, mark):
    """A fold page's marks on three log rows, as the chain's layer - the write fold-units makes."""
    crud.apply_batch_updates(db, LOG, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=key, updates={"record_id": key, MARK: mark}, source_name=crud.CHAIN_SOURCE,
        updated_by="fold_rule") for key in ("r1", "r2", "r3")], silent=True))
    db.commit()


@pytest.mark.parametrize("retroactive, woken", [(True, ()), (False, (RULE["name"],))])
def test_one_page_stages_one_row_and_wakes_no_rule_on_the_retroactive_channel(db, retroactive, woken):
    _page(db, "seed")                                        # the rows the page marks, there before
    before = db.query(models.DatabaseOutbox.id).count()
    with (channel(event_constants.CHANNEL_RETROACTIVE) if retroactive else channel(None)), \
            outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        _page(db, "AUTO")
    staged = db.query(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id).all()[before:]

    assert len(staged) == 1, [(e.event_type, e.payload) for e in staged]
    assert worker._rules_for_group(staged, [RULE]) == woken
