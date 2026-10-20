"""The one read of ingestion_settings.json (총괄 10-07): the watcher, the enrichment config and
candidates, and the retry poller all call it, so the file is opened in one place and read one way -
as table_config is (a BOM is read). Light on purpose: the chain worker imports it without watchdog."""
import copy
import json
import os

import paths
from database.crud import _decode_config_text


INGESTION_SETTINGS_PATH = paths.config_path("ingestion_settings.json")


def read_ingestion_settings(path=None) -> dict:
    """The settings as a dict, or `{}` (every value its default) when the file is absent - held until the file
    changes (`config_watcher.held`, e6a0bdbbd; read per call before). One that does not read is said in one line and
    read as `{}`, or as what it said before if it read before. `path`: a caller's own copy of the path."""
    from database import config_watcher

    path = INGESTION_SETTINGS_PATH if path is None else path
    # a copy each call, as it was a fresh dict per call: a caller that edits its settings edits only its own
    return copy.deepcopy(config_watcher.held(config_watcher.names_of([path]), ("ingestion_settings", path),
                                             lambda: _read(path), fallback={}))


def _read(path):
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as handle:
        loaded = json.loads(_decode_config_text(handle.read()))
    if not isinstance(loaded, dict):
        raise ValueError("the file is %s, not an object" % type(loaded).__name__)
    return loaded
