"""[F6] The builder attaches indexes to the DECLARED keys, and stops paying for the
two families measurement says nothing reads.

WHY THESE ASSERTIONS AND NOT OTHERS
-----------------------------------
The defect this round repaired was invisible from inside the code: `init_dynamic_models`
built a fixed set of indexes and never read `map_key_columns` at all, and nothing broke,
because a missing index is a slow query rather than a wrong answer. So the net has to be
about the SHAPE of what the builder declares, not about behaviour.

🔴 The single most important test here is `test_the_naive_rule_is_not_reintroduced`. The
rule that looks obvious - "index every table's `map_key_columns`" - is the one ruling
`R-2026-08-14-B` declined, because the busiest index in the system covers a table that
declares no `map_key_columns` at all. If someone later "simplifies" `declared_key_columns`
down to that one tier, every other test in this file still passes. That one does not.

Table names carry an `f6idx_` prefix that cannot exist in the user's (gitignored)
`table_config.json`; a collision would let the real schema win the shared in-memory
sqlite and make these tests fail for an unrelated reason.
"""
import pytest

from database import models


# --- one table per resolution tier, plus the two refusal shapes ---------------
TIER_TABLES = {
    # Tier 1: map key declared -> the NARROWER index wins over the composite.
    "f6idx_map": {
        "business_key": "f6idx_cell_key",
        "composite_key_source": ["f6_lot", "f6_slot", "f6_x", "f6_y"],
        "composite_key_separator": "_",
        "map_key_columns": ["f6_lot", "f6_slot"],
        "column_types": {"f6idx_cell_key": "string", "f6_lot": "string",
                         "f6_slot": "string", "f6_x": "number", "f6_y": "number"},
    },
    # Tier 2: THE COUNTER-EXAMPLE SHAPE - no map key, read by its composite key.
    "f6idx_meta": {
        "business_key": "f6idx_meta_pk",
        "composite_key_source": ["f6_target_table", "f6_map_id"],
        "composite_key_separator": "_",
        "column_types": {"f6idx_meta_pk": "string", "f6_target_table": "string",
                         "f6_map_id": "string", "f6_grid": "string"},
    },
    # Tier 3: no composite key at all - row identity IS one declared column.
    "f6idx_master": {
        "business_key": "f6_part_no",
        "column_types": {"f6_part_no": "string", "f6_qty": "number"},
    },
    # Refusal A: the declaration names a column the table does not have.
    "f6idx_broken": {
        "business_key": "f6_id",
        "map_key_columns": ["f6_lot", "f6_absent_column"],
        "composite_key_source": ["f6_lot", "f6_x"],
        "composite_key_separator": "_",
        "column_types": {"f6_id": "string", "f6_lot": "string", "f6_x": "number"},
    },
    # Refusal B: a COMPOSITE business key is not an identity column. `f6idx_cell_key`
    # is a declared column here on purpose - the gate that must stop it is the
    # presence of `composite_key_source`, not the absence of the column.
    "f6idx_composite_bk": {
        "business_key": "f6idx_cell_key",
        "composite_key_source": ["f6_lot", "f6_absent_column"],
        "composite_key_separator": "_",
        "column_types": {"f6idx_cell_key": "string", "f6_lot": "string"},
    },
}


@pytest.fixture(scope="module")
def built():
    models.init_dynamic_models(TIER_TABLES)
    return {name: models.DYNAMIC_TABLES[name].__table__ for name in TIER_TABLES}


def index_map(table_obj):
    return {ix.name: [c.name for c in ix.columns] for ix in table_obj.indexes}


# =============================================================================
# 1. The rule resolves to the right declaration, per tier
# =============================================================================
@pytest.mark.parametrize("table,expected_cols,expected_source", [
    ("f6idx_map", ["f6_lot", "f6_slot"], "map_key_columns"),
    ("f6idx_meta", ["f6_target_table", "f6_map_id"], "composite_key_source"),
    ("f6idx_master", ["f6_part_no"], "business_key"),
])
def test_each_tier_resolves_to_its_declaration(table, expected_cols, expected_source):
    cols, source = models.declared_key_columns(TIER_TABLES[table])
    assert cols == expected_cols
    assert source == expected_source


def test_map_key_beats_composite_key():
    """Tier order is not cosmetic: it decides how WIDE the index is, and width is
    WAL per row on every insert. `f6idx_map` declares BOTH, and the narrower one
    must win."""
    cols, source = models.declared_key_columns(TIER_TABLES["f6idx_map"])
    assert source == "map_key_columns"
    assert cols == ["f6_lot", "f6_slot"]
    assert len(cols) < len(TIER_TABLES["f6idx_map"]["composite_key_source"])


def test_a_declaration_naming_an_absent_column_is_refused_whole():
    """Not a partial index. A partial tuple is a DIFFERENT index than the one
    declared, and it would be created silently."""
    cols, reason = models.declared_key_columns(TIER_TABLES["f6idx_broken"])
    assert cols == []
    assert "f6_absent_column" in reason
    assert "refusing" in reason
    # And specifically NOT the leading column on its own.
    assert cols != ["f6_lot"]


def test_a_composite_business_key_is_not_an_identity_column():
    """`f6idx_composite_bk` declares a business key that IS a declared column, but
    it also declares a composite key - so the business key is a JOIN of other
    columns, not a lookup key. Tier 3 must not fire."""
    cols, reason = models.declared_key_columns(TIER_TABLES["f6idx_composite_bk"])
    assert cols == []
    assert "f6idx_cell_key" not in cols


# =============================================================================
# 2. 🔴 The counter-example. This is the test that stops the naive rule coming back.
# =============================================================================
def test_the_naive_rule_is_not_reintroduced(built):
    """`f6idx_meta` is the shape of `wafer_map_metadata`, whose `(target_table, map_id)`
    index took 44,103 scans on 2026-08-14 - the most-scanned index in the system - while
    the table declares NO `map_key_columns`.

    A rule that only reads `map_key_columns` produces NO index here. If that rule ever
    comes back, this assertion is the one that fails.
    """
    assert TIER_TABLES["f6idx_meta"].get("map_key_columns") is None
    idx = index_map(built["f6idx_meta"])
    assert idx.get("idx_f6idx_meta_declared_key") == ["f6_target_table", "f6_map_id"]


def test_tier_three_covers_the_business_key_column(built):
    """`f6idx_master` is the shape of `dt_inventory`, which is filtered as
    `WHERE dt_job IN (...)` on its BUSINESS KEY COLUMN (chain_bindings resolves that
    column the same way). `business_key_val` cannot serve that predicate - it is a
    different column."""
    idx = index_map(built["f6idx_master"])
    assert idx.get("idx_f6idx_master_declared_key") == ["f6_part_no"]


# =============================================================================
# 3. What the builder must NOT attach any more
# =============================================================================
@pytest.mark.parametrize("table", sorted(TIER_TABLES))
def test_the_two_unread_families_are_gone(built, table):
    """Measured 2026-08-14 across both dev copies: `ix_<t>_created_at` read zero on 35
    of 36 (table, database) pairs and `idx_<t>_bk` read zero on every one. They were
    maintained on every insert of every table."""
    idx = index_map(built[table])
    assert f"ix_{table}_created_at" not in idx
    assert f"idx_{table}_bk" not in idx
    # The column itself stays - only its index is retired.
    assert "created_at" in built[table].columns


@pytest.mark.parametrize("table", sorted(TIER_TABLES))
def test_every_index_names_a_declaration(built, table):
    """The invariant the whole round exists to establish: an index that cannot name
    the declaration it serves is drift wearing a declaration's clothes (ruling F3).

    The allowed set is closed. A new index added to the builder without a declaration
    behind it fails here rather than being discovered by a survey a month later.
    """
    allowed = {
        f"ix_{table}_business_key_val",       # business_key (materialised)
        f"idx_{table}_updated",               # updated_at ordering / watermark
        f"ix_{table}_updated_at",             # 〃
        f"ix_{table}_is_graph_synced",        # graph sync cursor
        f"ix_{table}_needs_graph_rollback",   # 〃
        f"idx_{table}_declared_key",          # THE declared lookup key
    }
    assert set(index_map(built[table])) <= allowed


def test_a_table_with_no_usable_declaration_gets_no_key_index(built):
    idx = index_map(built["f6idx_broken"])
    assert "idx_f6idx_broken_declared_key" not in idx
    assert set(idx) == {
        "ix_f6idx_broken_business_key_val", "idx_f6idx_broken_updated",
        "ix_f6idx_broken_updated_at", "ix_f6idx_broken_is_graph_synced",
        "ix_f6idx_broken_needs_graph_rollback",
    }


# =============================================================================
# 4. The LIVE config - every registered table is decided, none is silently skipped
# =============================================================================
def test_live_config_every_table_is_decided():
    """Not "every table gets an index" - that would be a rule with no refusals, and a
    rule with no refusals is not being evaluated. What must hold is that every declared
    table gets either a key tuple made of ITS OWN declared columns, or a stated reason.
    """
    from database import crud
    cfg = crud.load_table_config() or {}
    tables = [t for t in cfg if not t.startswith("__")]
    if not tables:
        pytest.skip("no live table_config.json on this checkout")
    for name in tables:
        cols, source = models.declared_key_columns(cfg[name])
        assert isinstance(source, str) and source.strip(), name
        if cols:
            declared = set((cfg[name].get("column_types") or {}))
            assert set(cols) <= declared, (name, cols)
            assert source in ("map_key_columns", "composite_key_source", "business_key")
