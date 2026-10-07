"""The one read of ingestion_settings.json (총괄 10-07): the watcher, the enrichment config and
candidates, and the retry poller all call it, so the file is opened in one place and read one way -
as table_config is (a BOM is read). Light on purpose: the chain worker imports it without watchdog."""
import json
import logging
import os

import paths
from database.crud import _decode_config_text

logger = logging.getLogger(__name__)

INGESTION_SETTINGS_PATH = paths.config_path("ingestion_settings.json")


def read_ingestion_settings(path=None) -> dict:
    """The settings as a dict, or `{}` (every value its default) when the file is absent or
    unreadable - which says so in one line. `path`: a caller's own copy of the path."""
    path = INGESTION_SETTINGS_PATH if path is None else path
    try:
        if os.path.exists(path):
            with open(path, "rb") as handle:
                loaded = json.loads(_decode_config_text(handle.read()))
            if isinstance(loaded, dict):
                return loaded
    except Exception as e:                                          # noqa: BLE001
        logger.warning("Could not load ingestion settings (%s): %s", path, e)
    return {}
