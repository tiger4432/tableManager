# -*- coding: utf-8 -*-
"""총괄 11-06 ㄱ-1: a build the one builder left for later (`INDEX_DEFERRED` - nothing started) is asked again; a built,
present or failed one is not. One judgment (`models.comes_again`), two callers:

  start work    the line's start - a work that left one stays in `_LEFT`, each poll asks it again until none does
  lookup memo   `unique_key.ensure_lookup_once` - a deferred report is not remembered, so the next call builds
The builder's own words are its PG gates (`test_one_index_builder_waits_says_and_leaves_nothing`); here it is scripted.
"""
import pytest

from chain import ingestion_worker as worker
from chain import join_key_index as vjc
from chain import unique_key
from database import models
from runtime import index_wants, maintenance_line, system_reload


@pytest.fixture(name="builder")
def fixture_builder(monkeypatch):
    """The builder answers the scripted words in turn; `calls` the names it was asked for."""
    script = {"words": [], "calls": []}

    def once(engine, name, *args, **kwargs):
        script["calls"].append(name)
        return script["words"].pop(0)

    monkeypatch.setattr(models, "_ensure_one_index_once", once)
    monkeypatch.setattr(worker, "_analyze_stale_tables_sync", lambda *a, **k: None)
    monkeypatch.setattr(maintenance_line, "_LEFT", [])
    return script


def _poll(monkeypatch):
    """One poll of the line with nothing new asked - only `_LEFT` can build."""

    class Db:
        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(system_reload, "reloads_after", lambda db, mark: [])
    monkeypatch.setattr(system_reload, "reload_for", lambda *a: False)
    monkeypatch.setattr(index_wants, "taken", lambda db: [])
    maintenance_line.poll_once(lambda: Db(), 0)


def _start_with(monkeypatch, *names):
    works = [(lambda n=n: models._ensure_one_index(None, n, "S", "test", say=lambda line: None, table="t"),)
             for n in names]
    monkeypatch.setattr(maintenance_line, "_start_work", lambda factory: works)
    maintenance_line._start(None)


def test_a_deferred_start_index_is_built_at_the_next_poll_and_then_asked_no_more(builder, monkeypatch):
    builder["words"] = [models.INDEX_DEFERRED, models.INDEX_BUILT, models.INDEX_BUILT]
    _start_with(monkeypatch, "ix_later", "ix_now")
    assert builder["calls"] == ["ix_later", "ix_now"] and len(maintenance_line._LEFT) == 1

    _poll(monkeypatch)
    assert builder["calls"][2:] == ["ix_later"] and maintenance_line._LEFT == [], "built at the next poll - list empty"

    _poll(monkeypatch)
    assert builder["calls"][3:] == [], "nothing left - the polls after ask the builder nothing"


@pytest.mark.parametrize("word", [models.INDEX_FAILED, models.INDEX_PRESENT, models.INDEX_BUSY])
def test_a_start_index_not_deferred_is_not_asked_again(builder, monkeypatch, word):
    """A failure's retry is a whole build each poll (총괄 11-06 ㄱ-1: next start or Reload, as its line says)."""
    builder["words"] = [word]
    _start_with(monkeypatch, "ix")
    _poll(monkeypatch)
    assert builder["calls"] == ["ix"] and maintenance_line._LEFT == []


def test_the_join_lookup_forgets_a_deferred_build_and_remembers_a_built_one(builder, monkeypatch):
    class Db:
        def rollback(self):
            pass

        def get_bind(self):
            return None

    monkeypatch.setattr(unique_key, "auto_index_off", lambda: "")
    monkeypatch.setattr(vjc, "_dialect_of", lambda db: "postgresql")
    monkeypatch.setattr(unique_key, "index_validity", lambda db, names: {})
    unique_key.forget()
    builder["words"] = [models.INDEX_DEFERRED, models.INDEX_BUILT]
    try:
        first = unique_key.ensure_lookup_once(Db(), "gk_meas", ["lot"])
        second = unique_key.ensure_lookup_once(Db(), "gk_meas", ["lot"])
        third = unique_key.ensure_lookup_once(Db(), "gk_meas", ["lot"])
    finally:
        unique_key.forget()
    assert (first["state"], second["state"], third["state"]) == ("deferred", "ok", "ok")
    assert len(builder["calls"]) == 2, "deferred: asked again; built: remembered"
