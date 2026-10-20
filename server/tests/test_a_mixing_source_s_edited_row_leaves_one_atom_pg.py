# -*- coding: utf-8 -*-
"""총괄 10-14 ② ㄹ (소유자 «ㄹ» - 섞여 가는 것을 받아들임): a source whose read the short form answers
differently (its identity) is translated on the new identity from the file's change on - and a row
translated on the OLD identity that is then edited leaves one atom, not two: its old atom is
withdrawn by the row it came from, the new one written on the new identity. On PostgreSQL, in the
hold world, with the source's identity the composite key where the table's default is row_id.
"""
import copy
import json
import os
import sys

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from database import crud, schemas                                  # noqa: E402
from database.context import channel, outbox_mode                   # noqa: E402
from declaration_names import fold_versions                         # noqa: E402
from ledger import schema                                           # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.setup import LedgerSetup                                # noqa: E402
from ledger.setup_bundle import require_ready_bundle, shorten_setup, validate_bundle  # noqa: E402
from ledger.setup_registry import compile_setup_snapshot            # noqa: E402
from scripts import migrate_ledger_config_to_v7 as v7               # noqa: E402
from support import hold_world as hw                                 # noqa: E402
from ledger.roleframe import when_says  # noqa: E402

pytestmark = pytest.mark.pg

COMPOSITE = list(hw.KEYS)


def _long():
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    source["read"].update({"identity": COMPOSITE, "order_by": COMPOSITE})
    return source


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    monkeypatch.setattr(hw, "LEDGER_SOURCE", _long())
    for world in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        yield world


def _atoms(world):
    with world["engine"].connect() as conn:
        return [(_identity(ref), float(value)) for ref, value in conn.execute(text(
            "SELECT source_raw_ref, object_payload->>'value' FROM %s WHERE source_who = :s ORDER BY 2"
            % schema.LEDGER_TABLE), {"s": hw.SOURCE})]


def _identity(raw_ref):
    """The identity an atom's row was named on: `<relation>:<identity json>` in its row ref."""
    (row,) = json.loads(raw_ref)["rows"]
    return json.loads(row.split(":", 1)[1])


def _short_setup(world):
    document = hw.sample("ledger_config.json.sample")
    document["sources"] = {hw.SOURCE: _long()}
    catalog = world["setup"].catalog
    _short, lines, written = v7.convert(document, catalog)
    assert written and [line.split()[:2] for line in lines] == [[hw.SOURCE, "mixes"]]
    short, _verdicts = shorten_setup(fold_versions(document), says=when_says)
    bundle = require_ready_bundle(validate_bundle(short, catalog=catalog))
    return LedgerSetup(config_root=world["setup"].config_root, bundle=bundle,
                       snapshot=compile_setup_snapshot(bundle, trusted_implementations(),
                                                       catalog=catalog),
                       mappers=role_mapper_registry(), catalog=catalog)


def test_an_old_identity_row_edited_after_the_file_is_short_leaves_one_atom(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert _atoms(world) == [({"dt_job": "J1", "dt_x": 1.0, "dt_y": 2.0}, 7.0)]

    world["setup"] = _short_setup(world)
    row_id = hw.official(world).row_id
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(world["db"], hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(row_id=row_id, updates={"netdie": 8}, source_name="user",
                                      updated_by="t")]))
        world["db"].commit()
    hw.settle(world)

    assert _atoms(world) == [({"row_id": row_id}, 8.0)]
