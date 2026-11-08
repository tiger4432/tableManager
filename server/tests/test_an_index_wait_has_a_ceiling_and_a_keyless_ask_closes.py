# -*- coding: utf-8 -*-
"""Lead 11-08 (QA ④):

  (b) the build's wait   index_build_wait_seconds past PostgreSQL's int milliseconds overflowed lock_timeout and every
                         build failed - it is read at most INDEX_BUILD_WAIT_MOST
  (c) a keyless ask      a business-key index asked for a table with no business key never closed and held the index
                         line's one full wait - it closes on INDEX_REFUSED
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from parsers import directory_watcher                                # noqa: E402


def test_the_build_wait_is_read_at_most_what_a_lock_wait_can_be():
    most = directory_watcher.INDEX_BUILD_WAIT_MOST
    assert directory_watcher.index_build_wait({"index_build_wait_seconds": 300}) == 300.0
    assert directory_watcher.index_build_wait({"index_build_wait_seconds": 3000000}) == float(most)
    assert directory_watcher.index_build_wait({"index_build_wait_seconds": 0}) is None
    assert most * 1000 <= 2 ** 31 - 1 < (most + 1) * 1000, "the most is PostgreSQL's int milliseconds"


def test_a_business_key_ask_for_a_table_with_none_closes_refused(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from chain import ingestion_worker as worker
    from database import models
    from migrations import add_business_key_unique_index as uq

    monkeypatch.setattr(uq, "tables_with_business_key", lambda conn: ["zz_keyed"])
    monkeypatch.setattr(uq, "existing_unique_index", lambda conn, table: ("uq_zz_keyed", True))
    factory = sessionmaker(bind=db_session.get_bind())
    with models.built_tables():
        worker._ensure_business_key_unique_indexes_sync(factory, only=["zz_keyless", "zz_keyed"])
        words = models.words_in_round()
    assert words.get(uq.unique_index_name("zz_keyed")) == models.INDEX_PRESENT, "canary: the keyed one is answered"
    assert words.get(uq.unique_index_name("zz_keyless")) == models.INDEX_REFUSED, words
