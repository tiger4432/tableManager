"""Single override point for the server's **data root**.

`DATABASE_URL` already makes the database swappable. This module does the same
for the two user-owned data trees that live on disk:

    server/config/**                -> paths.CONFIG_DIR
    server/ingestion_workspace/**   -> paths.WORKSPACE_DIR

Set ``ASSY_DATA_ROOT`` to relocate both. Unset (the default) resolves to
``server/`` so production behaviour is byte-for-byte unchanged.

    ASSY_DATA_ROOT=C:/repo/dev_env
      -> CONFIG_DIR    = C:/repo/dev_env/config
      -> WORKSPACE_DIR = C:/repo/dev_env/ingestion_workspace

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
import os

# Location of this file == the server package directory.
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

# The overridable root. Empty/unset -> production layout.
DATA_ROOT = os.path.abspath(os.environ.get("ASSY_DATA_ROOT") or SERVER_DIR)

CONFIG_DIR = os.path.join(DATA_ROOT, "config")
WORKSPACE_DIR = os.path.join(DATA_ROOT, "ingestion_workspace")

# True when running against an isolated data root (dev/QA), False in production.
IS_ISOLATED = os.path.normcase(DATA_ROOT) != os.path.normcase(SERVER_DIR)


def config_path(*parts):
    """Path inside the (possibly relocated) config directory."""
    return os.path.join(CONFIG_DIR, *parts)


def workspace_path(*parts):
    """Path inside the (possibly relocated) ingestion workspace."""
    return os.path.join(WORKSPACE_DIR, *parts)


def describe():
    return (f"data_root={DATA_ROOT} isolated={IS_ISOLATED} "
            f"db={os.environ.get('DATABASE_URL', '<default:production>')}")
