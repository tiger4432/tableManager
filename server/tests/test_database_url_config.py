"""DB URL resolution: env DATABASE_URL > config/database.json > built-in default.

The precedence order is a safety property, not a convenience: the isolated dev
stack (devenv.py) redirects its database via the DATABASE_URL env var, while
`devenv.py bootstrap` copies the whole config tree - including any
production-pointing database.json - into the isolated root. If the file ever
outranked the env var, an isolated stack would silently write to production.
test_env_beats_config_file pins that order.

Isolation note: conftest.py pins os.environ["DATABASE_URL"] before importing
the app; these tests only ever touch the environment through monkeypatch (which
restores it) and point paths.CONFIG_DIR at tmp_path, so the suite-wide pin is
never weakened and no test reads or writes the live server/config tree.
"""
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths


DEFAULT = "postgresql://postgres:admin@localhost:5432/assy_manager"


def _write_config(tmp_path, payload):
    p = tmp_path / paths.DB_CONFIG_FILENAME
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    else:
        p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Point paths.CONFIG_DIR at an empty tmp dir (config_path resolves through it)."""
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    return tmp_path


# --- precedence ---------------------------------------------------------------

def test_env_beats_config_file(config_dir, monkeypatch):
    """CRITICAL pin: an env DATABASE_URL must win over a present, valid file."""
    _write_config(config_dir, {"url": "postgresql://file:filepw@filehost:5432/filedb"})
    monkeypatch.setenv("DATABASE_URL", "postgresql://env:envpw@envhost:5432/envdb")
    url, source = paths.resolve_database_url(DEFAULT)
    assert url == "postgresql://env:envpw@envhost:5432/envdb"
    assert source == "env"


def test_empty_env_counts_as_unset(config_dir, monkeypatch):
    _write_config(config_dir, {"url": "postgresql://file:filepw@filehost:5432/filedb"})
    monkeypatch.setenv("DATABASE_URL", "")
    url, source = paths.resolve_database_url(DEFAULT)
    assert url == "postgresql://file:filepw@filehost:5432/filedb"
    assert source == "config file"


def test_config_file_used_when_env_unset(config_dir, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _write_config(config_dir, {"url": "postgresql://file:filepw@filehost:5432/filedb"})
    url, source = paths.resolve_database_url(DEFAULT)
    assert url == "postgresql://file:filepw@filehost:5432/filedb"
    assert source == "config file"


def test_missing_file_falls_through_to_default(config_dir, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url, source = paths.resolve_database_url(DEFAULT)
    assert url == DEFAULT
    assert source == "default"


def test_engine_module_consumed_env_source():
    """conftest pins DATABASE_URL before app import, so the imported engine
    module must report the env as its winning source."""
    from database import database as db_mod
    assert db_mod.DB_URL_SOURCE == "env"
    assert db_mod.SQLALCHEMY_DATABASE_URL == os.environ["DATABASE_URL"]


# --- split-field composition --------------------------------------------------

def test_split_fields_compose_with_special_char_password(config_dir, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _write_config(config_dir, {
        "host": "db.prod.local",
        "port": 5433,
        "database": "assy_prod",
        "user": "assy_user",
        "password": "p@ss:w%rd+1",
    })
    url, source = paths.resolve_database_url(DEFAULT)
    assert source == "config file"
    # quote_plus must have encoded every URL-hostile character.
    assert url == "postgresql://assy_user:p%40ss%3Aw%25rd%2B1@db.prod.local:5433/assy_prod"


def test_split_fields_defaults(config_dir, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _write_config(config_dir, {"database": "assy_prod", "password": "pw"})
    url, _ = paths.resolve_database_url(DEFAULT)
    assert url == "postgresql://postgres:pw@localhost:5432/assy_prod"


def test_url_key_wins_over_split_fields(config_dir, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _write_config(config_dir, {
        "url": "postgresql://u:p@urlhost:5432/urldb",
        "host": "splithost", "database": "splitdb",
    })
    url, _ = paths.resolve_database_url(DEFAULT)
    assert url == "postgresql://u:p@urlhost:5432/urldb"


# --- broken-file behaviour: ERROR, then fall through (never crash boot) -------

def test_malformed_json_falls_through_with_error(config_dir, monkeypatch, caplog):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = _write_config(config_dir, "{not valid json")
    with caplog.at_level(logging.ERROR, logger="paths"):
        url, source = paths.resolve_database_url(DEFAULT)
    assert (url, source) == (DEFAULT, "default")
    assert any(path in r.getMessage() for r in caplog.records), \
        "the ERROR must name the offending file"


def test_no_recognised_keys_falls_through_with_error(config_dir, monkeypatch, caplog):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _write_config(config_dir, {"_comment": "sample copied without editing keys away"})
    with caplog.at_level(logging.ERROR, logger="paths"):
        url, source = paths.resolve_database_url(DEFAULT)
    assert (url, source) == (DEFAULT, "default")
    assert caplog.records, "silently ignoring an operator config file is forbidden"


# --- password masking (boot log must never carry the raw URL) -----------------

def test_mask_db_password():
    assert paths.mask_db_password(
        "postgresql://assy_user:p%40ss%3Aw%25rd@host:5432/db"
    ) == "postgresql://assy_user:***@host:5432/db"
    # No password -> unchanged; falsy -> unchanged.
    assert paths.mask_db_password("sqlite:///:memory:") == "sqlite:///:memory:"
    assert paths.mask_db_password(None) is None


def test_describe_masks_env_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:supersecret@h:5432/d")
    desc = paths.describe()
    assert "supersecret" not in desc
    assert "u:***@h" in desc


# --- supervisor reachability probe follows the same precedence ----------------

def test_supervisor_probe_reads_config_file(config_dir, monkeypatch):
    import process_supervisor
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _write_config(config_dir, {"host": "probehost", "port": 6543, "database": "d",
                               "user": "u", "password": "p"})
    assert process_supervisor._database_endpoint() == ("probehost", 6543)


def test_supervisor_probe_still_none_when_nothing_configured(config_dir, monkeypatch):
    import process_supervisor
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # No env, no file: the probe must keep treating this as nothing to probe
    # (it has never probed the built-in default).
    assert process_supervisor._database_endpoint() is None
