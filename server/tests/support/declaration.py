"""A test that reads the operating declaration reads the one the repository ships - config/sample's ledger declaration
and the table catalogue it is checked against - from a config root of its own, not the box's gitignored files
(총괄 568388892 ③: on a fresh checkout those tests answered 503, and a real defect hid among them)."""
import os
import shutil

import paths

SAMPLE = os.path.join(paths.SERVER_DIR, "config", "sample")


def use_committed_declaration(monkeypatch, tmp_path):
    """The config root becomes `tmp_path/config`: ontology/ledger_config.json and table_config.json are the shipped
    samples. Returns that root."""
    from database import crud
    from ledger_api import declared_entities, ledger_subgraph

    root = tmp_path / "config"
    (root / "ontology").mkdir(parents=True)
    shutil.copyfile(os.path.join(SAMPLE, "ledger_config.json.sample"), root / "ontology" / "ledger_config.json")
    shutil.copyfile(os.path.join(SAMPLE, "table_config.json.sample"), root / "table_config.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(root))
    monkeypatch.setattr(crud, "CONFIG_PATH", str(root / "table_config.json"))    # bound at import, from CONFIG_DIR
    ledger_subgraph.reset_declaration_cache()
    monkeypatch.setattr(declared_entities, "_cache", None)     # read once per process - again for this root
    monkeypatch.setattr(declared_entities, "_keys", None)
    return root


def use_committed_catalogue(monkeypatch):
    """`crud.TABLE_CONFIG` holds the shipped table catalogue for this test (restored after it); returns it."""
    import json

    from database import crud, models

    with open(os.path.join(SAMPLE, "table_config.json.sample"), encoding="utf-8") as handle:
        catalogue = json.load(handle)
    catalogue = catalogue.get("tables", catalogue)
    for name, entry in catalogue.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)
    models.init_dynamic_models(catalogue)
    return catalogue
