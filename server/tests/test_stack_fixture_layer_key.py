# -*- coding: utf-8 -*-
"""Can `bonding_log`'s declared key carry ONE ROW PER DIE?

[The shape this measures]

Product owner, 2026-08-13: a package is a STACK. One base-wafer position holds
8-12 dies bonded on top of each other, and production writes one `bonding_log`
row per die. The trace fixture writes ONE row per base position, so the thing the
fixture exists to exercise -- "which core die is at each layer, and what do the
layers share" -- cannot happen in it.

The obvious repair is "emit twelve rows instead of one". This file measures what
the real write path does with those twelve rows BEFORE anyone writes that
generator, because the answer is not the one the repair assumes.

`bonding_log` declares:

    "business_key": "bond_cell_key",
    "composite_key_source": ["bond_lot", "bond_slot", "bond_x", "bond_y"]

Those four columns are the BASE POSITION. Twelve dies stacked at one position
supply the same four values, so `crud.assemble_composite_business_key` composes
ONE key for all twelve and the upsert resolves eleven of them onto the first row.
The rows are not rejected and nothing errors: the batch reports success and
eleven dies are gone.

[Why a test and not an argument]

Reading the declaration makes this obvious; obvious is not measured. These tests
drive `crud.apply_batch_updates` -- the real one, the same call the ingestion path
makes -- and count the rows that survive.

[The four cases, and why C and D are here]

  A  today's declaration              -> 12 dies in,  1 row stored
  B  layer column IN the key          -> 12 dies in, 12 rows stored
  C  layer column declared but NOT in
     the key (the half-fix)           -> 12 dies in,  1 row stored
  D  layer keyed, feed omits it       -> 12 rows stored with NO business key

C is the injected fault. It is the repair a reader reaches for first -- "the
table needs a layer column, so declare one" -- and it changes NOTHING: the column
lands, the grid shows it, and eleven dies still vanish. A guard that only checked
"is there a layer column" would pass C. This one does not, and that is the whole
reason it is worth keeping.

D is the repair's migration cost, measured rather than assumed: keying the layer
un-keys every feed that does not supply it.

Table names carry a `stackfix_` prefix that cannot collide with a real table in
the operator's gitignored config. `bonding_log` itself is the recorded precedent
for why: a test that borrowed a real table name broke when the operator later
declared it.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_SERVER = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from database.database import Base                     # noqa: E402
from database import models, crud, schemas             # noqa: E402

TABLE = "stackfix_bond_probe"
LAYERS = 12
BASE = {"bond_lot": "BS-2601-001", "bond_slot": "01", "bond_x": 11, "bond_y": 9}

#: The declared columns of `bonding_log` today, renamed onto the probe table.
_BASE_TYPES = {
    "bond_cell_key": "string",
    "bond_lot": "string", "bond_slot": "string",
    "bond_x": "number", "bond_y": "number",
    "b_bn": "string", "stack_height": "number",
    "dt_lot": "string", "dt_slot": "string",
    "dt_x": "number", "dt_y": "number",
    "event_time": "string",
}


def _config(layer_column=None, layer_in_key=False):
    """One probe-table declaration. `layer_column` is declared when named;
    `layer_in_key` decides whether it also joins the composite key."""
    types = dict(_BASE_TYPES)
    if layer_column:
        types[layer_column] = "number"
    key_src = ["bond_lot", "bond_slot", "bond_x", "bond_y"]
    if layer_column and layer_in_key:
        key_src.append(layer_column)
    return {TABLE: {
        "business_key": "bond_cell_key",
        "composite_key_source": key_src,
        "composite_key_separator": "_",
        "column_types": types,
        "display_columns": list(types),
    }}


def _stack(layer_column=None):
    """One package: 12 dies at ONE base position, each from a different DT source.

    The sources diverge deliberately -- three lots over twelve layers -- because a
    stack whose layers all came from one lot cannot answer "what do the layers
    share", which is the question the fixture exists for.
    """
    items = []
    for layer in range(1, LAYERS + 1):
        upd = dict(BASE)
        upd.update({
            "b_bn": "0" if layer == 7 else "1",
            "stack_height": LAYERS,
            "dt_lot": "DT-2601-%03d" % (1 + layer % 3),
            "dt_slot": "%02d" % layer,
            "dt_x": layer, "dt_y": layer,
            "event_time": "2026-05-26 00:00:00",
        })
        if layer_column:
            upd[layer_column] = layer
        items.append(schemas.GeneralUpdateItem(updates=upd, source_name="pipeline_parser"))
    return schemas.GeneralUpdateBatch(updates=items, silent=True)


@pytest.fixture(name="probe")
def fixture_probe():
    """A sqlite session per declaration. The collapse happens in
    `assemble_composite_business_key`, before any SQL is emitted, so the dialect
    is not load-bearing here -- the row count is what is being read."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    made = []

    def build(cfg):
        models.init_dynamic_models(cfg)
        crud.TABLE_CONFIG.update(cfg)
        Base.metadata.create_all(bind=engine)
        models.sync_dynamic_tables_schema(engine)
        db = Session()
        made.append(db)
        return db

    yield build
    for db in made:
        db.close()
    Base.metadata.drop_all(bind=engine)


def _stored(db, cfg):
    return db.query(models.DYNAMIC_TABLES[TABLE]).all()


def _run(db, batch):
    crud.apply_batch_updates(db, TABLE, batch)
    db.commit()


def test_todays_declaration_collapses_a_stack_to_one_row(probe):
    """12 dies in, 1 row out -- and the batch reports success."""
    cfg = _config()
    db = probe(cfg)
    _run(db, _stack())

    rows = _stored(db, cfg)
    assert len(rows) == 1, (
        "expected the declared key (bond_lot, bond_slot, bond_x, bond_y) to "
        "collapse the stack; got %d rows" % len(rows))
    # All twelve composed the SAME key -- the base position, with no layer in it.
    assert rows[0].business_key_val == "BS-2601-001_01_11_9"
    # The survivor is the LAST die written, so the eleven below it are not merely
    # missing: their b_bn (layer 7 is the bad one here) is gone with them.
    assert rows[0].dt_slot == "%02d" % LAYERS


def test_layer_in_the_key_keeps_every_die(probe):
    """The repair: the layer joins `composite_key_source`, and all 12 survive."""
    cfg = _config(layer_column="stack_layer", layer_in_key=True)
    db = probe(cfg)
    _run(db, _stack(layer_column="stack_layer"))

    rows = _stored(db, cfg)
    assert len(rows) == LAYERS, (
        "expected one row per die once the layer joins the key; got %d" % len(rows))
    keys = {r.business_key_val for r in rows}
    assert len(keys) == LAYERS
    assert "BS-2601-001_01_11_9_1" in keys and "BS-2601-001_01_11_9_12" in keys
    # The sources diverge across the stack, which is what makes the sibling
    # question answerable at all.
    lots = {r.dt_lot for r in rows}
    assert len(lots) == 3, "the seeded stack should span 3 dt lots, got %r" % lots


def test_declaring_the_layer_without_keying_it_changes_nothing(probe):
    """🔴 The injected fault: the half-fix that looks like the fix.

    The column is declared, the value is supplied, the grid would show it -- and
    eleven dies are still silently merged away, because identity is decided by
    `composite_key_source` and nothing else. A guard that asserted only "the layer
    column exists" would have gone green here.
    """
    cfg = _config(layer_column="stack_layer", layer_in_key=False)
    db = probe(cfg)
    _run(db, _stack(layer_column="stack_layer"))

    rows = _stored(db, cfg)
    assert len(rows) == 1, (
        "declaring the layer column without keying it must NOT change the row "
        "count; got %d" % len(rows))
    # And the column is populated, which is exactly what makes the half-fix
    # convincing: the surviving row carries a layer number.
    assert rows[0].stack_layer is not None


def test_a_row_without_the_layer_gets_no_key_once_the_layer_is_keyed(probe):
    """The migration cost of the repair, measured rather than assumed.

    `_unfilled_composite_parts` refuses to assemble a key when ANY source column
    is blank, so the moment the layer joins `composite_key_source` every feed that
    does not supply it stops being keyed. The rows still land -- they are just no
    longer addressable, and the next push inserts duplicates instead of upserting.

    This is not an argument against the repair; it is the thing that has to be
    sequenced with it. Any existing bonding feed has to carry the layer from the
    same release, or it silently stops upserting.
    """
    cfg = _config(layer_column="stack_layer", layer_in_key=True)
    db = probe(cfg)
    _run(db, _stack())          # NOTE: no layer supplied

    rows = _stored(db, cfg)
    assert len(rows) == LAYERS, "unkeyed rows insert rather than merge"
    assert all(r.business_key_val is None for r in rows), (
        "expected no business key at all when the layer is missing; got %r"
        % [r.business_key_val for r in rows][:3])
