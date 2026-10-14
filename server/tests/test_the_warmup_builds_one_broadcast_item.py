"""총괄 10-14: a chain slot's first group paid 0.31 s in «broadcast build» - `event_constants.upsert_item` imports its
encoder on the first call. The worker's warm-up (`ingestion_worker.warmup_worker`, run when a slot starts and after a
reload) builds one item, so that cost lands before the first group."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                                # noqa: E402
from chain import ingestion_worker                                    # noqa: E402


def test_the_warmup_builds_one_broadcast_item(monkeypatch):
    built = []
    real = event_constants.upsert_item
    monkeypatch.setattr(event_constants, "upsert_item", lambda *a, **k: built.append(a) or real(*a, **k))
    ingestion_worker.warmup_worker([])
    assert len(built) == 1, built
