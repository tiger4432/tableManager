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
「own the scope you undo」, which is what `session_contract.discarding` is.

⚠️ pysqlite CANNOT SEE MOST OF THIS CLASS (it opens no transaction for a SELECT), so the
end-to-end proof is `@pytest.mark.pg`; the shape assertions run anywhere.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import session_contract                                               # noqa: E402


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the sibling: same body, one gesture different
# ---------------------------------------------------------------------------

class _Session:
    """A session that records the gestures made on it, and nothing else."""

    def __init__(self, open_already=True):
        self.open = open_already
        self.acts = []

    def in_transaction(self):
        return self.open

    def begin(self):
        self.open = True
        self.acts.append("begin")

    def begin_nested(self):
        self.acts.append("nested")
        acts = self.acts
        return type("Nested", (), {"commit": lambda s: acts.append("release"),
                                   "rollback": lambda s: acts.append("undo")})()

    def rollback(self):                       # ⛔ the gesture this round removes
        self.acts.append("SESSION-ROLLBACK")


def test_discarding_undoes_its_own_savepoint_and_never_the_session():
    """🔴 THE GATE. `undo` is the SAVEPOINT's; `SESSION-ROLLBACK` would be the caller's
    whole transaction, which is the defect."""
    db = _Session()

    answer = session_contract.discarding(db, "probe", lambda: "ANSWER")

    assert answer == "ANSWER"
    assert db.acts == ["nested", "undo"]
    assert "SESSION-ROLLBACK" not in db.acts


def test_the_two_siblings_differ_by_exactly_one_gesture():
    """⚠️ ONE BODY, SO THE 25P01 ARM CANNOT COME TO HAVE TWO SPELLINGS (ruling 415 ③).
    Asserted by driving both, because a claim about shared code that only reads the source
    would pass on two copies that happen to match today."""
    kept, dropped = _Session(), _Session()

    session_contract.in_savepoint(kept, "probe", lambda: None)
    session_contract.discarding(dropped, "probe", lambda: None)

    assert kept.acts == ["nested", "release"]
    assert dropped.acts == ["nested", "undo"]


def test_discarding_opens_a_transaction_when_the_caller_had_none():
    db = _Session(open_already=False)

    session_contract.discarding(db, "probe", lambda: None)

    assert db.acts == ["begin", "nested", "undo"]


def test_a_failure_inside_discarding_still_re_raises():
    """⚠️ CONTAINMENT IS NOT DEGRADATION. The savepoint is undone either way; what differs
    is that the caller hears about the failure."""
    db = _Session()

    with pytest.raises(ValueError):
        session_contract.discarding(db, "probe", lambda: (_ for _ in ()).throw(ValueError("x")))

    assert db.acts == ["nested", "undo"]
    assert "SESSION-ROLLBACK" not in db.acts


def test_an_unusable_session_is_refused_with_the_same_line_as_its_sibling(caplog):
    """🔴 RULING 415 ③, ASSERTED AS A PROPERTY OF BOTH. Two spellings of the refusal would
    be the new defect this round is supposed to avoid."""
    import logging

    class Poisoned(_Session):
        def begin_nested(self):
            orig = type("Orig", (Exception,), {"pgcode": session_contract.NO_ACTIVE_TRANSACTION})()
            raise type("InternalError", (Exception,), {"orig": orig})()

    lines = {}
    for name, call in (("keep", session_contract.in_savepoint),
                       ("drop", session_contract.discarding)):
        caplog.clear()
        with caplog.at_level(logging.ERROR):
            with pytest.raises(session_contract.SessionNotUsable):
                call(Poisoned(), "enrichment_sweep", lambda: None)
        lines[name] = [r.getMessage() for r in caplog.records]

    assert lines["keep"] == lines["drop"], lines
    assert lines["keep"] and "enrichment_sweep" in lines["keep"][0]


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the prototype seat, against a real transaction
# ---------------------------------------------------------------------------

def test_the_sweep_no_longer_rolls_back_the_session_it_was_handed(monkeypatch):
    """🔴 THE RED THIS ROUND HAD TO SEE FIRST. The caller holds uncommitted work; the dry
    run must leave it standing. With `db.rollback()` in that seat it disappeared - the
    assertion below fails on the previous build, which is the whole point of writing it
    against the SEAT rather than against the primitive.

    ⚠️ `confirm_keys` is replaced by a double that WRITES, because the property is 「what
    happens to the caller's work」 and the real one needs a populated catalogue. The write
    it makes is undone by `discarding`, which the second assertion pins.
    """
    from chain.enrichment import analysis
    from chain import enrichment

    class Session:
        def __init__(self):
            self.rows = []
            self.saved = None
            self.open = True

        def in_transaction(self):
            return self.open

        def begin(self):
            self.open = True

        def begin_nested(self):
            self.saved = list(self.rows)
            outer = self

            class Nested:
                def commit(self):
                    outer.saved = None

                def rollback(self):
                    outer.rows = list(outer.saved)
                    outer.saved = None

            return Nested()

        def rollback(self):
            self.rows = []          # ⛔ the caller's work goes too - the defect

    db = Session()
    db.rows.append("CALLER'S OWN UNCOMMITTED WORK")

    monkeypatch.setattr(analysis, "iter_derived_rows", lambda *a, **k: [])
    monkeypatch.setattr(enrichment.candidates, "candidate_target_fields", lambda rule: ["t"])
    monkeypatch.setattr(enrichment.candidates, "confirm_keys",
                        lambda *a, **k: db.rows.append("what the dry run wrote") or {})
    monkeypatch.setattr(enrichment.candidates, "log_stats", lambda *a, **k: None)

    analysis.run_auto_confirm_sweep(
        db, {"name": "s274", "target_fields": ["t"]}, apply=False, log=lambda *a: None)

    assert "CALLER'S OWN UNCOMMITTED WORK" in db.rows, (
        "the dry run discarded work it did not do")
    assert "what the dry run wrote" not in db.rows, (
        "a dry run must still leave nothing of its own behind")


@pytest.mark.pg
def test_against_real_postgres_the_callers_uncommitted_row_survives_a_discard(pg_engine):
    """🔴 THE SAME PROPERTY WHERE THE RULES ARE REAL. pysqlite does not open a transaction
    for a SELECT and treats much of this class as a no-op, so every assertion above is
    about gestures; this one is about what PostgreSQL actually keeps.

    ⛔ AND IT ASSERTS BOTH HALVES. A `discarding` that undid nothing would keep the
    caller's row too - the second assertion is what tells 「owned the scope」 from
    「stopped undoing」."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=pg_engine)()
    try:
        session.execute(text("DROP TABLE IF EXISTS s274_probe"))
        session.execute(text("CREATE TABLE s274_probe (who text)"))
        session.commit()

        # The CALLER's own uncommitted work, held open across the dry run.
        session.execute(text("INSERT INTO s274_probe (who) VALUES ('caller')"))

        session_contract.discarding(
            session, "enrichment_sweep",
            lambda: session.execute(
                text("INSERT INTO s274_probe (who) VALUES ('dry-run')")))

        held = {row[0] for row in session.execute(text("SELECT who FROM s274_probe"))}
        assert held == {"caller"}, held

        session.commit()
        after = {row[0] for row in session.execute(text("SELECT who FROM s274_probe"))}
        assert after == {"caller"}, after
    finally:
        session.rollback()
        session.execute(text("DROP TABLE IF EXISTS s274_probe"))
        session.commit()
        session.close()
