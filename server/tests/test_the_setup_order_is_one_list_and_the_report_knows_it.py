# -*- coding: utf-8 -*-
"""S-180 ⓒ. The setup order lives in CODE, and the report answers 「what is first」.

🔴 THE DOCUMENT WROTE DOWN ITS OWN DEFECT. `docs/guide/SETUP_ORDER.md` §「지금 없는 것」 said:
「S-180 이 순서를 «읽어 주는 화면»이 없다. 그래서 지금은 «문서»가 순서를 안다 — 사람이 이 장을
열어야만 「무엇이 먼저인가」를 알 수 있고, 그것이 결함이다」. An order only a document knows is
an order no screen can answer, and the operator has to open six files to find the empty one.

⚠️ `SETUP_STEPS` IS THE CANON AND THE DOCUMENT IS ITS DESCRIPTION — that direction, not the
other. A second list in the prose would drift from this one and neither copy would error.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import config_resolve_report as crr                                   # noqa: E402


def _domain(report, name):
    return next((d for d in report["domains"] if d["domain"] == name), None)


# ---------------------------------------------------------------------------
# the order itself
# ---------------------------------------------------------------------------

def test_the_prerequisites_are_a_ROOTED_TREE_and_not_a_line():
    """🔴 PINNED AS VALUES, because I first wrote this as a LINE and it produced a FALSE
    BLOCK (판정 317). Each step depending on the previous one made the ledger `blocked_by: 4`,
    so an installation with no virtual joins - which is legitimate - would show the ledger
    permanently blocked. The document's own 「앞」 lines are the canon and they branch from ①.

    ⚠️ ④'s prerequisite is NOT A STEP. It is the right-hand table's UNIQUE index, a DB state,
    and its absence makes that step refuse itself with `no_unique_index`. Writing it as a
    step would invent a dependency that does not exist.
    """
    assert {s["step"]: s["after"] for s in crr.SETUP_STEPS} == {
        1: None, 2: 1, 3: 1, 4: 1, 5: 1, 6: 5}
    assert [s["step"] for s in crr.SETUP_STEPS] == [1, 2, 3, 4, 5, 6]


def test_every_step_names_a_domain_and_no_domain_takes_two_steps():
    names = [s["domain"] for s in crr.SETUP_STEPS]
    assert len(names) == len(set(names)), names
    assert crr.DOMAIN_CATALOG == names[0], "the catalogue is what everything else points at"


def test_the_order_travels_with_the_report_as_vocabulary():
    """🔴 THE SCREEN MUST NOT SPELL THE STEP NAMES ITSELF. A client that held its own copy
    would drift from this list, and the drift would not error — it would just label a step
    wrongly, which is the failure this whole report exists to avoid."""
    vocabulary = crr.resolve_report([crr.DOMAIN_CATALOG])["vocabulary"]
    assert [s["step"] for s in vocabulary["setup_steps"]] == [1, 2, 3, 4, 5, 6]
    assert all(s["name"] for s in vocabulary["setup_steps"])


# ---------------------------------------------------------------------------
# what the report says about it
# ---------------------------------------------------------------------------

def test_a_domain_outside_the_order_says_so_rather_than_hiding():
    """⚠️ `notation` AND `binding` ARE NOT STEPS, and `step: null` is how that is said. Hiding
    them would leave the screen holding domains this order has never heard of."""
    report = crr.resolve_report()
    for name in (crr.DOMAIN_NOTATION, crr.DOMAIN_BINDING):
        domain = _domain(report, name)
        assert domain is not None and domain["step"] is None, name


def test_every_domain_in_the_report_carries_both_new_fields():
    report = crr.resolve_report()
    for domain in report["domains"]:
        assert "step" in domain and "blocked_by" in domain, domain["domain"]


def test_a_step_whose_predecessor_stands_is_not_blocked(monkeypatch):
    from database import crud

    monkeypatch.setattr(crud, "load_table_config_or_raise",
                        lambda: {"t_ok": {"column_types": {"a": "string"}}})
    report = crr.resolve_report([crr.DOMAIN_CATALOG, crr.DOMAIN_CHAIN])
    assert _domain(report, crr.DOMAIN_CATALOG)["counts"]["effective"] == 1
    assert _domain(report, crr.DOMAIN_CHAIN)["blocked_by"] is None


def test_the_ledger_is_not_blocked_by_a_virtual_join_it_does_not_need():
    """🔴 THE FALSE BLOCK THIS LIST FIRST PRODUCED (판정 317). Virtual join is not the
    ledger's prerequisite - the catalogue is - so a box that declares no materialised join
    must not show the ledger as blocked. Its OWN refusals stay in its own populations, which
    is where an operator should read them."""
    report = crr.resolve_report()
    ledger = _domain(report, crr.DOMAIN_LEDGER)
    assert ledger is not None
    assert ledger["blocked_by"] is None, (
        "the ledger is blocked by %r; only step 1 can block it" % ledger["blocked_by"])


def test_a_step_is_blocked_by_the_NUMBER_of_the_step_that_did_not_stand(monkeypatch):
    """🔴 THE POINT OF THE ORDER. An empty step is not just empty — everything after it has
    nothing to point at, and saying WHICH step is what turns 「something is wrong」 into 「go
    and write step 1」."""
    from database import crud

    monkeypatch.setattr(crud, "load_table_config_or_raise", dict)
    monkeypatch.setattr(crud, "load_table_config", dict)
    report = crr.resolve_report([crr.DOMAIN_CATALOG, crr.DOMAIN_CHAIN])

    assert _domain(report, crr.DOMAIN_CATALOG)["counts"]["effective"] == 0
    assert _domain(report, crr.DOMAIN_CHAIN)["blocked_by"] == 1


def test_a_predecessor_that_is_not_in_this_report_is_unknown_not_unblocked():
    """⚠️ ASKING FOR ONE DOMAIN CANNOT ANSWER 「am I blocked」 — the step before it was never
    resolved. `None` here means 「this report does not know」, and that is why there is no
    `blocked: false` field to read as an answer."""
    report = crr.resolve_report([crr.DOMAIN_LEDGER])
    assert _domain(report, crr.DOMAIN_LEDGER)["blocked_by"] is None


def test_standing_needs_an_effect_and_not_merely_the_absence_of_refusals():
    """🔴 「거절이 0」 IS NOT 「섰다」. A step nobody has written declares nothing for the next
    one to point at, so effect 0 blocks exactly as a refusal does — while the two stay
    different states in that step's own populations."""
    assert not crr._step_is_standing({"counts": {"effective": 0, "rejected": 0}})
    assert not crr._step_is_standing({"counts": {"effective": 3, "rejected": 1}})
    assert crr._step_is_standing({"counts": {"effective": 1, "rejected": 0}})


# ---------------------------------------------------------------------------
# 🔴 the document is the description, not the canon
# ---------------------------------------------------------------------------

SETUP_ORDER_DOC = os.path.join(server_dir, "..", "docs", "guide", "SETUP_ORDER.md")


def test_the_document_no_longer_claims_the_order_is_unreadable():
    """⛔ THE DOC WROTE ITS OWN DEFECT DOWN AND THE DEFECT IS CLOSED, so the sentence has to
    go — a file loaded by every reader that still says 「this does not exist」 teaches that
    every session. Same class as the tombstone rule in CLAUDE.md."""
    with open(SETUP_ORDER_DOC, encoding="utf-8") as handle:
        text = handle.read()
    assert "읽어 주는 화면»이 없다" not in text, (
        "SETUP_ORDER.md still says nothing reads the order out; S-180 ⓒ built it")
    assert "config_resolve_report" in text, (
        "the document must point at the list that is now the canon")
