# -*- coding: utf-8 -*-
"""Lead 11-11: a seed is undone by its batch, not by SQL pasted on a table (a table reads through its lines once the
cell-source overhaul lands). Every write of one seed run carries one transaction_id, printed when the run starts; the
door the HTTP seeds write through sends it, and the in-process seeds' batches carry it."""
import io
import json
import os
import sys

import pytest

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.dirname(SCRIPTS))

import product_door                                                   # noqa: E402


class _Opener:
    def __init__(self):
        self.bodies = []

    def open(self, request, timeout=None):
        self.bodies.append(json.loads(request.data.decode("utf-8")))
        return _Answer()


class _Answer(io.BytesIO):
    def __init__(self):
        super().__init__(b'{"updated_count": 1}')

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


@pytest.mark.parametrize("given", ["01a1c6aa-0000-7000-8000-000000000001", None])
def test_the_door_sends_the_runs_transaction_id_when_given(monkeypatch, given):
    opener = _Opener()
    monkeypatch.setattr(product_door, "opener", lambda: opener)
    product_door.put_rows("t", [{"business_key_val": "k1", "updates": {"a": 1}}], log=lambda *_: None,
                          transaction_id=given)
    assert [body.get("transaction_id") for body in opener.bodies] == [given]


@pytest.mark.parametrize("module", ["seed_syn_world", "seed_syn_process_ledger"])    # seed_syn_k1_lot retired aeb838eba
def test_an_in_process_seeds_batch_carries_its_runs_transaction_id(module):
    seed = __import__(module)
    batch = seed._batch([{"a": 1}])
    assert batch.transaction_id == seed.RUN_TX and len(seed.RUN_TX) == 36
