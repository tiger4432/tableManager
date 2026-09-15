# -*- coding: utf-8 -*-
"""S-260. The PG harness does not author a relation whose shape is written elsewhere.

🔴 29 PROOFS WENT DOWN AS *ERRORS* AND ONLY ON A BOX WITH A LIVE CATALOGUE. `pg_engine`
copied EVERY table in `Base.metadata` into its scratch schema and `create_all`-ed it - and
`init_dynamic_models` maps a `kind: view` entry too, from the `column_types` that describe
what a READER sees. So the scratch schema got a varchar `ledger_events`, and the product's
own `ensure_schema` then died on `CHECK jsonb_typeof(object_payload)`: the harness's copy
had pre-empted the ledger's partitioned jsonb DDL, which is the real author of that table.

⚠️ THE SUITE COULD NOT SEE IT. It is pinned to `sqlite:///:memory:`, where these proofs
skip, and a fresh checkout has no `table_config.json` at all - so 「green」 meant 「the
catalogue this box has was never loaded」. That is why the judge below is fed a catalogue
rather than the box's: the property has to hold where the defect cannot be reproduced.
"""
import os
import sys

from sqlalchemy import Column, MetaData, String, Table

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


def _two_relations():
    """One relation of each kind, otherwise identical - so the KIND is what decides."""
    metadata = MetaData()
    Table("plain_tbl", metadata, Column("id", String))
    Table("read_only_vw", metadata, Column("id", String))
    return metadata


def test_a_relation_declared_a_view_is_not_one_this_harness_builds():
    """🔴 THE GATE. `ledger_events` is the shape of this: declared `kind: view` so the
    write door refuses it (S-186), while its columns are authored by the ledger's own DDL."""
    from conftest import creatable_tables

    built = {t.name for t in creatable_tables(
        _two_relations(), {"read_only_vw": {"kind": "view"}})}

    assert built == {"plain_tbl"}


def test_a_relation_the_catalogue_does_not_hold_is_built():
    """⛔ THE REGRESSION LINE. `cell_sources`, `audit_logs` and the rest of the
    framework's own tables are declared in code, never in the catalogue - and the whole
    scratch schema is made of them. `catalog_kind(None)` answering 「table」 is what keeps
    this fix from emptying the harness."""
    from conftest import creatable_tables

    built = {t.name for t in creatable_tables(_two_relations(), {})}

    assert built == {"plain_tbl", "read_only_vw"}


def test_the_word_comes_from_the_catalogues_own_author():
    """⚠️ NOT A SECOND SPELLING OF `kind`. S-187 put the default in one place because
    four sites had written `str(x.get("kind") or "table")` for themselves; a harness that
    spelled a fifth would be the site that drifts, and it would drift into building a
    relation again."""
    from conftest import creatable_tables
    from ledger import setup_bundle

    assert "catalog_kind" in creatable_tables.__code__.co_names
    assert setup_bundle.catalog_kind({}) != "view"
    assert setup_bundle.catalog_kind({"kind": "view"}) == "view"
