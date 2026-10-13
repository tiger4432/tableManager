# -*- coding: utf-8 -*-
"""S-274 1단계 · 판정 415. A borrowed session is never rolled back — it is rolled back TO
a savepoint of its own.

🔴 THE PROTOTYPE. `enrichment.analysis.run_auto_confirm_sweep(apply=False)` ended with
`db.rollback()  # belt and braces: a dry-run holds no writes, make it structural`. Inside
the seat that is right; outside it is destructive. The session belongs to the CALLER, and
`admin/retroactive._count_chain_replay`, `_run_chain_replay` and the dry-run route all
reach this arm - any uncommitted work they were holding went with it.

⚠️ AND THE REPOSITORY HAD ALREADY PAID FOR THE SHAPE ONCE. `enrichment/config
._isolated_execute`'s docstring records a poisoned session escaping into
`process_pending_groups`, whose `processed_chain=True` commit was quietly turned into a
rollback: the group was never marked, so the batch loop re-ran it forever.

🔴 THE ANSWER IS NOT 「DELETE THE ROLLBACK」 — a dry run really must leave nothing. It is
「own the scope you undo」: `session_contract.discarding` was that seat, and it retired when the sweep
moved its pages onto a session of its own (총괄 3eca39091 · 59c0bfb8c 7) - this file keeps the symptom.
"""
import os
import sys


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)



# ---------------------------------------------------------------------------
# 🔴 ⓑ — the prototype seat, against a real transaction
# ---------------------------------------------------------------------------

def test_the_sweep_never_ends_the_session_it_was_handed(monkeypatch):
    """🔴 THE RED THIS ROUND HAD TO SEE FIRST (판정 415). The caller holds uncommitted work; the dry
    run must leave it standing. With `db.rollback()` in that seat it disappeared; then one SAVEPOINT
    of the caller's session held every key of the queue (총괄 3eca39091: 450 s at 1M). The loop runs
    on a session of its own and ends that one's transaction at each page - the handed session gives
    its bind and nothing else.

    ⚠️ `confirm_keys` is replaced by a double, because the property is 「which session the work is
    done on and how its page ends」 and the real one needs a populated catalogue.
    """
    from sqlalchemy.orm import Session as Own

    from chain.enrichment import analysis
    from chain import enrichment

    class Handed:
        def __init__(self):
            self.rows = ["CALLER'S OWN UNCOMMITTED WORK"]
            self.touched = []

        def get_bind(self):
            return None

        def __getattr__(self, name):
            self.touched.append(name)
            raise AttributeError(name)

    db, worked_on, ends = Handed(), [], []
    monkeypatch.setattr(Own, "rollback", lambda self: ends.append("rollback"))
    monkeypatch.setattr(analysis, "derived_pages", lambda *a, **k: iter([[
        {"row_id": "r0", "business_key_val": None, "keys": {}, "targets": {}}]]))
    monkeypatch.setattr(enrichment.candidates, "candidate_target_fields", lambda rule: ["t"])
    monkeypatch.setattr(enrichment.candidates, "confirm_keys", lambda own, *a, **k: worked_on.append(own) or {})
    monkeypatch.setattr(enrichment.candidates, "log_stats", lambda *a, **k: None)

    analysis.run_auto_confirm_sweep(
        db, {"name": "s274", "target_fields": ["t"]}, apply=False, log=lambda *a: None)

    assert db.rows == ["CALLER'S OWN UNCOMMITTED WORK"] and db.touched == [], (
        "the dry run reached into the session it was handed")
    assert len(worked_on) == 1 and isinstance(worked_on[0], Own) and ends == ["rollback"], (
        "a dry page is worked on the sweep's own session and its end rolls that back")
