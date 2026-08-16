"""Single override point for the server's **data root**.

`DATABASE_URL` already makes the database swappable. This module does the same
for the user-owned trees that live on disk:

    server/config/**                -> paths.CONFIG_DIR
    server/ingestion_workspace/**   -> paths.WORKSPACE_DIR
    server/<process>.log            -> paths.log_path(...)

Set ``ASSY_DATA_ROOT`` to relocate them. Unset (the default) resolves to
``server/`` so production behaviour is byte-for-byte unchanged.

    ASSY_DATA_ROOT=C:/repo/dev_env
      -> CONFIG_DIR         = C:/repo/dev_env/config
      -> WORKSPACE_DIR      = C:/repo/dev_env/ingestion_workspace
      -> log_path("x.log")  = C:/repo/dev_env/x.log

Why one module instead of an env var per file: ~17 modules build these paths
independently from ``os.path.dirname(__file__)``. Each now reads from here, so
there is exactly one place that decides where data lives.

Deliberately NOT covered (they are code, not data, and are resolved through
``sys.path`` as the ``mappers`` package):
    server/mappers/**

Import convention follows ``event_constants.py``: ``server/`` is on ``sys.path``
in every entry point, so ``import paths`` resolves. Callers that may be imported
without ``server/`` on the path use the same try/except fallback crud.py uses.
"""
import json
import logging
import os
import re

# Location of this file == the server package directory.
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

# The overridable root. Empty/unset -> production layout.
DATA_ROOT = os.path.abspath(os.environ.get("ASSY_DATA_ROOT") or SERVER_DIR)

CONFIG_DIR = os.path.join(DATA_ROOT, "config")
WORKSPACE_DIR = os.path.join(DATA_ROOT, "ingestion_workspace")

CONFIG_BACKUP_DIRNAME = "backup"
CONFIG_SAMPLE_DIRNAME = "sample"

# True when running against an isolated data root (dev/QA), False in production.
IS_ISOLATED = os.path.normcase(DATA_ROOT) != os.path.normcase(SERVER_DIR)


def config_path(*parts):
    """Path inside the (possibly relocated) config directory."""
    return os.path.join(CONFIG_DIR, *parts)


def config_backup_path(*parts):
    """Path inside the config backup directory."""
    return config_path(CONFIG_BACKUP_DIRNAME, *parts)


def config_sample_path(filename):
    """Tracked sample path; filenames keep the explicit ``.sample`` suffix."""
    name = filename if str(filename).endswith(".sample") else f"{filename}.sample"
    return config_path(CONFIG_SAMPLE_DIRNAME, name)


def sample_for_config(path):
    """Sample counterpart of an active config path, including isolated roots."""
    absolute = os.path.abspath(path)
    name = os.path.basename(absolute)
    if not name.endswith(".sample"):
        name += ".sample"
    return os.path.join(os.path.dirname(absolute), CONFIG_SAMPLE_DIRNAME, name)


def workspace_path(*parts):
    """Path inside the (possibly relocated) ingestion workspace."""
    return os.path.join(WORKSPACE_DIR, *parts)


def log_path(filename):
    """Path of a process log file inside the (possibly relocated) data root.

    Process logs sit directly at the data root, exactly where they sat before
    (``server/server.log``, ``server/watcher.log``, ...), so an unset
    ``ASSY_DATA_ROOT`` keeps production's layout byte-for-byte. An isolated
    process writes ``<ASSY_DATA_ROOT>/server.log`` instead of appending to the
    user's live log - the file a reviewer reads to reconstruct an incident must
    not carry a drill's lines.
    """
    return os.path.join(DATA_ROOT, filename)


def describe():
    db_env = os.environ.get("DATABASE_URL")
    # Masked on purpose: this line goes to server.log. Never print the raw URL.
    db = mask_db_password(db_env) if db_env else "<no env override>"
    return (f"data_root={DATA_ROOT} isolated={IS_ISOLATED} db_env={db}")


# --- Database URL resolution -------------------------------------------------
#
# Lives here (stdlib-only) rather than in database/database.py so that
# process_supervisor.py - which must survive sqlalchemy itself being
# unimportable after a bad deploy - can resolve the same URL for its
# reachability probe. database/database.py consumes this at import time.

DB_CONFIG_FILENAME = "database.json"


def mask_db_password(url):
    """``postgresql://user:secret@host/db`` -> ``postgresql://user:***@host/db``.

    Safe to log. A URL without a password is returned unchanged.
    """
    if not url:
        return url
    return re.sub(r"://([^:/@]*):[^@]*@", r"://\1:***@", url)


def _database_url_from_config(path):
    """URL from ``config/database.json``, or None (missing/unusable file).

    Accepted shapes (``url`` wins when both are present):
      {"url": "postgresql://user:pw@host:5432/dbname"}
      {"host": ..., "port": ..., "database": ..., "user": ..., "password": ...}

    A present-but-broken file is an ERROR that falls through to the next
    precedence level: an optional file must not crash boot, but silently
    ignoring an operator's connection config is how you write to the wrong
    database without noticing.
    """
    if not os.path.exists(path):
        return None
    log = logging.getLogger("paths")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("top-level JSON value must be an object")
    except Exception as exc:
        log.error(
            "Ignoring unusable database config %s (%s: %s) - falling back to "
            "the next DB URL source", path, type(exc).__name__, exc)
        return None

    url = cfg.get("url")
    if url:
        return str(url)

    if not any(k in cfg for k in ("host", "port", "database", "user", "password")):
        log.error(
            "Ignoring database config %s: neither 'url' nor split fields "
            "(host/port/database/user/password) present - falling back to "
            "the next DB URL source", path)
        return None

    from urllib.parse import quote_plus
    # quote_plus so special characters in credentials survive URL composition.
    user = quote_plus(str(cfg.get("user", "postgres")))
    password = quote_plus(str(cfg.get("password", "")))
    host = str(cfg.get("host", "localhost"))
    port = str(cfg.get("port", 5432))
    database = str(cfg.get("database", "assy_manager"))
    auth = f"{user}:{password}" if password else user
    return f"postgresql://{auth}@{host}:{port}/{database}"


def resolve_database_url(default=None):
    """``(url, source)`` - the DB connection URL and which source won.

    Precedence (do NOT reorder): env ``DATABASE_URL`` > ``config/database.json``
    > ``default``. The env var MUST outrank the file: the isolated dev stack
    redirects its DB via the env var, while ``devenv.py bootstrap`` copies the
    config tree - including a production-pointing ``database.json`` - into the
    isolated root. If the file won, an isolated stack would silently write to
    the production database.

    ``source`` is one of ``"env"`` / ``"config file"`` / ``"default"``. An
    empty env value counts as unset.
    """
    env_url = os.environ.get("DATABASE_URL") or None
    if env_url:
        return env_url, "env"
    file_url = _database_url_from_config(config_path(DB_CONFIG_FILENAME))
    if file_url:
        return file_url, "config file"
    return default, "default"
