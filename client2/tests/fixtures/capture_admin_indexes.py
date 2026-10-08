# -*- coding: utf-8 -*-
"""GET /admin/indexes as the server answers it - `models.index_states(engine)`, the one function the route
returns - the fixture index_table_panel_harness reads (lead d71f931c7).

Regenerate (conda env assy_manager), from the repository root, on a box with its PostgreSQL:
    ASSY_DATA_ROOT=<the running server's server/ dir> python client2/tests/fixtures/capture_admin_indexes.py

Read only: the function reads the PostgreSQL catalogue and its statistics, and writes nothing. The route is
behind the admin token, so the function is called directly with the server's own engine. Writes
admin_indexes.json and prints the states it found and how long the read took.
"""
import collections
import json
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from database import models  # noqa: E402
from database.database import engine  # noqa: E402

if __name__ == "__main__":
    if engine.dialect.name != "postgresql":
        raise SystemExit("not PostgreSQL (%s) - every state would be unknown" % engine.dialect.name)
    started = time.perf_counter()
    body = models.index_states(engine)
    took = time.perf_counter() - started
    with open(os.path.join(HERE, "admin_indexes.json"), "w", encoding="utf-8") as f:
        json.dump({"_what": "REAL server output: models.index_states(engine) - what GET /admin/indexes returns - "
                            "on the box PostgreSQL, captured %s by capture_admin_indexes.py."
                            % datetime.now(timezone.utc).isoformat(), **body}, f, ensure_ascii=False, indent=1)
    print("declared", len(body["declared"]), dict(collections.Counter(r["state"] for r in body["declared"])),
          "outside", len(body["outside"]), "read %.3f s" % took)
