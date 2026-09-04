# -*- coding: utf-8 -*-
"""A refused declaration must keep the ADDRESS of each issue, and never cut silently.

Every v5 validation issue already carries `(code, path, message)`, and the path is the
authoring box an operator has to open. `_validate_for_version` used to join the FIRST
THREE into one sentence, so what reached the screen was prose with no code, no path, and
no sign that anything had been dropped.

🔴 That is the same silent-truncation class this repository fixed four times on
2026-09-04 - the dashboard, the schema sync, the chain loop and the test run - and this
one sits on the operator's own path: the admin screen reads the declaration through
`ledger_config.load()`.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.config import LedgerConfigError, _validate_for_version   # noqa: E402
from ledger.setup_bundle import LedgerSetupValidationError           # noqa: E402


@pytest.fixture
def five_issues(monkeypatch):
    from ledger import setup_bundle, setup as ledger_setup

    issues = tuple(
        LedgerSetupValidationError(f"code_{i}", f"bundle.sources.s{i}.read", f"issue {i}")
        for i in range(5)
    )
    monkeypatch.setattr(setup_bundle, "validate_bundle_errors",
                        lambda raw, catalog=None: issues)
    monkeypatch.setattr(ledger_setup, "live_physical_catalog", lambda: {})
    return issues


def test_every_issue_survives_with_its_code_and_path(five_issues):
    """🔴 THE ADDRESSES. Five went in; five come out, each with the box it belongs to."""
    with pytest.raises(LedgerConfigError) as raised:
        _validate_for_version({"setup_version": 5}, "probe.json")

    carried = raised.value.errors
    assert len(carried) == 5, carried
    assert [e["code"] for e in carried] == [f"code_{i}" for i in range(5)]
    assert all(e["path"].startswith("bundle.sources.") for e in carried), carried


def test_nothing_is_dropped_and_the_count_is_stated(five_issues):
    """⛔ The old boundary kept three of five and said nothing about the other two. A
    short list reads as "that is all of them", which is how an operator fixes three
    things and is refused again."""
    with pytest.raises(LedgerConfigError) as raised:
        _validate_for_version({"setup_version": 5}, "probe.json")

    said = str(raised.value)
    assert "5 issue(s)" in said, said
    for i in range(5):
        assert f"issue {i}" in said, (i, said)


def test_a_message_only_refusal_still_works(five_issues):
    """⚠️ Every other raise site in this module passes a message alone. `errors` is
    optional and defaults to empty, so none of them had to change - and a caller reading
    `.errors` gets an empty tuple rather than an attribute error."""
    err = LedgerConfigError("plain message")
    assert err.errors == ()
    assert str(err) == "plain message"


def test_a_v3_declaration_takes_the_old_path_untouched(monkeypatch):
    """No regression: only version 5 and above reaches the v5 validator."""
    from ledger import config as ledger_config

    called = []
    monkeypatch.setattr(ledger_config, "validate",
                        lambda raw, origin=None: called.append(origin))
    _validate_for_version({"setup_version": 3}, "probe.json")
    assert called == ["probe.json"]
