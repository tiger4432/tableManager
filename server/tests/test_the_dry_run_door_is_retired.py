# -*- coding: utf-8 -*-
"""S-203. A door that only ever refused is gone, and the prose that described it was false.

🔴 BOTH HALVES WERE REFUSALS. `POST /admin/ledger/dry-run` raised `DryRunUnavailable` for
every source from 2026-08-18, when the four v1 translator classes left, and its
`target: "predicate"` half refused from 2026-08-27. Client callers: zero.

🔴 THE PROSE SAID OTHERWISE, IN THREE PLACES, AND TWO OF THEM CITED A FUNCTION THAT DOES NOT
EXIST — `main._ledger_predicate_dry_run`, definitions and calls both zero. Reading one of
them is what nearly had this recorded as half-alive.

⚠️ `begin_read_only` STAYS. Its own tests assert that PostgreSQL refuses the write, which is
the structural guarantee a restored preview has to be built on, and its test file says in
so many words not to inline it away.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_the_route_is_gone_from_the_application():
    """🔴 SCORED ON THE MOUNTED APP, not on the source. A route removed from a file but
    still registered somewhere else is exactly the shape a grep cannot see."""
    import main

    paths = {getattr(route, "path", None) for route in main.app.routes}
    assert "/admin/ledger/dry-run" not in paths


def test_calling_it_no_longer_reaches_a_handler(client):
    """⚠️ 405, NOT 404, AND THAT IS MEASURED RATHER THAN CHOSEN. The route object is gone --
    the test above scores that on the mounted app -- but this path still matches the SPA
    catch-all for GET, so a POST to it is 「method not allowed」. Asserting 404 would be
    asserting something this application does not do, and the difference says nothing about
    whether the door is shut.

    🔴 WHAT MATTERS IS THAT NO HANDLER ANSWERS: the reply carries no dry-run payload."""
    answer = client.post("/admin/ledger/dry-run", json={"target": "source"})

    assert answer.status_code >= 400, answer.text
    assert "atoms" not in answer.text and "declaration_token" not in answer.text


def test_the_module_keeps_only_the_guarantee():
    """⛔ DELETED BY NAME, NOT BY RANGE. What survives is the one thing with a consumer."""
    from ledger import dry_run

    public = {name for name in dir(dry_run) if not name.startswith("_")}
    assert "begin_read_only" in public
    for gone in ("preview", "DryRunUnavailable", "envelope_of", "DEFAULT_ROWS",
                 "MAX_ROWS", "MAX_ATOMS_RENDERED"):
        assert gone not in public, gone


def test_the_kept_guarantee_still_has_its_tests():
    """🔴 THE REASON IT STAYED. Retiring the asserted half and keeping the assertion would
    leave a function nothing scores — which is how the retired half got here."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "test_ledger_dry_run_pg.py"), encoding="utf-8") as handle:
        source = handle.read()

    assert "begin_read_only" in source


@pytest.mark.parametrize("symbol", ["_ledger_predicate_dry_run", "DryRunUnavailable"])
def test_no_prose_cites_what_is_not_there(symbol):
    """⛔ A COMMENT IS EVIDENCE OF INTENT, NOT OF BEHAVIOUR — and these two cited a function
    that never existed. The retirement takes the sentences with it, or the next reader
    re-derives the same wrong conclusion from them."""
    import subprocess

    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out = subprocess.run(["git", "grep", "-l", symbol, "--", ".", ":!tests"],
                         cwd=server_dir, capture_output=True, text=True)
    assert out.returncode in (0, 1), out.stderr

    survivors = {line for line in out.stdout.split("\n") if line.strip()}
    # 🔴 TWO TOMBSTONES ARE ALLOWED AND NOTHING ELSE IS. Both say the same thing -- that
    # this retired and that the old claim was false -- at the two places a reader arrives
    # from. What is forbidden is a LIVE sentence describing behaviour that is gone, which
    # is what the three removed ones were.
    assert survivors <= {"main.py", "ledger/dry_run.py"}, survivors
    here = os.path.dirname(os.path.abspath(__file__))
    for path in survivors:
        with open(os.path.join(here, "..", path), encoding="utf-8") as handle:
            body = handle.read()
        assert "RETIRED" in body or "retired" in body, (
            "%s mentions %s without saying it is gone" % (path, symbol))
