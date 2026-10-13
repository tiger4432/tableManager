"""A test that makes the product engine or the data root its own runs the pooled route bodies here: a pool process
reads the server's engine and data root, not the test's (총괄 e570dcda5 ㄴ · 568388892 ②)."""


def bodies_here(monkeypatch):
    from runtime import process_pool

    monkeypatch.setattr(process_pool, "_settings", lambda: {"walk_processes": 0, "grid_processes": 0})
