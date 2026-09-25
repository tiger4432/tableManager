# -*- coding: utf-8 -*-
"""총괄 bed890af2 — 소스 현황 부품 안쪽 줄의 기계 낱말은 «서버 한 자리»의 이름표로 나간다.

> 총괄: 「relation_rows ≈117662 · indexed_rows · not_yet · measured_at · … · no_row_id」
>       「낱말은 상태 이름과 같은 방법(서버 한 자리)」

🔴 THE SAME METHOD AS `SOURCE_STATES`: a names table beside the words' own seat, shipped with the
   answer that carries the words. Census words ride on `/api/ledger/declaration`, so their names
   (`backfill.CENSUS_NAMES`) ride there; refusal reasons ride on the translator's ledger, so
   theirs (`gate.REFUSAL_REASON_NAMES`) ride in `ingestion`. A screen draws the name and falls
   back to the key - it never keeps a copy of the vocabulary.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import admin, backfill, gate, trace_router                  # noqa: E402
from ledger import config as _config                                   # noqa: E402

HANGUL = re.compile("[가-힣]")
#: The census cells a screen draws (`client2/src/source_backlog.js` BACKLOG_FIELDS + MEASURED_AT).
DRAWN = {"relation_rows", "indexed_rows", "not_yet", "measured_at"}


class _Cursor:
    def execute(self, statement):
        return []


class _Refused:
    planned = False
    refusal = {"path": "sources.x", "message": "m"}


@pytest.fixture
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(_config, "load", lambda: {"entities": {"wafer@1": {"keys": ["wid"]}},
                                                   "vocabulary": {}})
    app = FastAPI()
    app.include_router(trace_router.router)
    return TestClient(app)


def test_every_gate_reason_has_a_name_and_nothing_else_does():
    """The gate's vocabulary is closed (a test asserts it); its names are the same closed set."""
    assert set(gate.REFUSAL_REASON_NAMES) == set(gate.REFUSAL_REASONS)


def test_the_translators_ledger_carries_the_reason_names():
    view = admin.ingestion_view(_Cursor(), declared=[])
    assert view["reason_names"] == gate.REFUSAL_REASON_NAMES


def test_the_declaration_route_carries_the_census_names(client):
    answer = client.get("/api/ledger/declaration")
    assert answer.status_code == 200, answer.text
    names = answer.json()["census_names"]
    assert DRAWN <= set(names), sorted(names)


def test_the_census_refusal_code_is_one_the_names_table_knows():
    """⚠️ `_loader_refusal` writes the code and `CENSUS_NAMES` names it - two spellings in one
    file. If the writer's code moves, this line goes red before the screen draws a bare key."""
    assert backfill._loader_refusal(_Refused())["refused"] in backfill.CENSUS_NAMES


@pytest.mark.parametrize("table", ["census", "reasons"])
def test_every_name_is_english_and_not_blank(table):
    names = backfill.CENSUS_NAMES if table == "census" else gate.REFUSAL_REASON_NAMES
    assert all(value.strip() and not HANGUL.search(value) for value in names.values()), names
