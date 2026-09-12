# -*- coding: utf-8 -*-
"""S-147-a. 「이 술어가 «안 보이는» 것이 무슨 뜻인가」 — a cell A1 had and A2 did not.

🔴 THE SUB-AXIS WAS MISSING, NOT THE CELL. A1 carries 「부재의 뜻」 for node keys — `allow_null`
says whether an absent key means 「원자 없음」 or 「null 목적어」 — and A2 had no counterpart at
all. A predicate declared `status`, `subjects`, `object` and `cardinality`, and nothing about
what its silence meant.

🔴 THE VALUE IS ANOTHER PREDICATE'S NAME, AND THAT IS FORCED RATHER THAN CHOSEN. 「안 봤다」 and
「보고 없었다」 are separated by THE EXISTENCE OF A DIFFERENT ATOM, so no self-contained word
(`absence: none|unknown`) can carry it — the fact lives outside this predicate.

⚠️ WHICH PREDICATE IS AN EXAMINATION IS A DOMAIN FACT. Code that knew `inspected` by name
would break 「코드에 도메인 낱말이 «없다»」, and the next installation spells it differently.

⛔ A TYPO IS REFUSED. An unresolvable name would make S-147-b's denominator read 0 with nothing
said — 「봤는데 없음」 counted as 「안 봤음」 — and that is a WRONG number, not a missing one.
"""
import json
import os
import shutil
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import validation                                                  # noqa: E402
from ledger import setup_bundle                                    # noqa: E402

PREDICATE = {"status": "active", "subjects": ["wafer@1"],
             "object": {"kind": "none", "qualifiers": {"required": [], "optional": []}}}


def _score(section):
    problems = validation.Problems()
    setup_bundle._validate_vocabulary(section, problems)
    return [issue.to_mapping() for issue in problems.finish()]


def _about(section, predicate="observed@1"):
    """Only the issues about THIS cell — the fixture's other squares are not the subject."""
    where = "bundle.vocabulary.%s.absence_confirmed_by" % predicate
    return [issue for issue in _score(section) if issue["path"] == where]


# ---------------------------------------------------------------------------
# the cell
# ---------------------------------------------------------------------------

def test_a_predicate_may_name_the_one_that_confirms_its_absence():
    assert _about({
        "inspected@1": dict(PREDICATE),
        "observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1"),
    }) == []


def test_absence_of_the_cell_is_todays_behaviour():
    """⚠️ WRITTEN ONLY WHERE IT CHANGES SOMETHING. Every declaration on disk means 「모름」,
    which is what an absent cell means — so 「declared unknown」 and 「never said」 are the same
    answer here and a default is safe, exactly as with `allow_null`."""
    assert _about({"observed@1": dict(PREDICATE)}) == []


def test_a_name_no_predicate_answers_to_is_REFUSED_not_swallowed():
    """⛔ THE WHOLE REASON THIS REFUSES. A silent miss would make the denominator 0 and read
    as 「봤는데 없음이 하나도 없다」, which is a number rather than a gap."""
    issues = _about({"observed@1": dict(PREDICATE, absence_confirmed_by="inspcted@1")})

    assert [issue["code"] for issue in issues] == ["unknown_id"]
    assert "inspcted@1" in issues[0]["message"]
    assert "observed@1" in issues[0]["message"], "the refusal lists what IS declared"


def test_a_predicate_cannot_confirm_its_own_absence():
    """⚠️ IF IT IS MISSING, SO IS THE EVIDENCE THAT IT WAS LOOKED FOR. Allowing this would
    let a declaration state a circular fact that can never be true."""
    issues = _about({"observed@1": dict(PREDICATE, absence_confirmed_by="observed@1")})
    assert [issue["code"] for issue in issues] == ["invalid_predicate"]


def test_a_retired_predicate_cannot_confirm_anything_about_today():
    """⚠️ THE WORD `status` ALREADY CARRIES, rather than a second retirement rule. A retired
    examination stopped being written, so its absence says nothing about a fresh subject."""
    issues = _about({
        "inspected@1": dict(PREDICATE, status="retired"),
        "observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1"),
    })
    assert [issue["code"] for issue in issues] == ["invalid_predicate"]
    assert "retired" in issues[0]["message"]


@pytest.mark.parametrize("value", ["", "   ", 3, None, ["inspected@1"]])
def test_the_value_must_be_a_name(value):
    assert _about({"observed@1": dict(PREDICATE, absence_confirmed_by=value)})


def test_the_cell_is_optional_in_the_grammar_rather_than_tolerated():
    """⛔ AN UNKNOWN KEY IS REFUSED BY `exact`, so a cell that merely 「went through」 would be
    one the validator never saw. This pins that the grammar NAMES it."""
    assert not _score({"observed@1": dict(PREDICATE, absence_confirmed_by="observed@1",
                                          typo_cell="x")}) == []
    unknown = [i for i in _score({"observed@1": dict(PREDICATE, typo_cell="x")})
               if "typo_cell" in i["path"]]
    assert unknown, "the vocabulary grammar is exact, which is what makes the new key a cell"


# ---------------------------------------------------------------------------
# 🔴 the authoring form learns it in the same commit
# ---------------------------------------------------------------------------

def test_the_form_offers_the_cell_and_points_it_at_the_vocabulary():
    """🔴 A CELL THE FORM DOES NOT KNOW IS A CELL NOBODY CAN WRITE. `test_ledger_skeleton`
    counts the two against each other; this pins that the square is a REFERENCE to another
    predicate rather than free text, which is what the validator refuses."""
    import io as _io

    from ledger.setup import DEFAULT_ONTOLOGY_ROOT          # noqa: F401  (path shape only)

    path = os.path.join(os.path.dirname(os.path.abspath(setup_bundle.__file__)),
                        "ledger_skeleton.json")
    with _io.open(path, encoding="utf-8") as handle:
        skeleton = json.load(handle)

    vocabulary = next(
        field["node"]["of"]["fields"] for field in skeleton["root"]["fields"]
        if isinstance(field.get("node"), dict)
        and isinstance(field["node"].get("of"), dict)
        and any(cell.get("key") == "cardinality"
                for cell in field["node"]["of"].get("fields", [])))
    cell = next(c for c in vocabulary if c["key"] == "absence_confirmed_by")

    assert cell["required"] is False
    assert cell["node"] == {"kind": "leaf", "hint": "ref", "section": "vocabulary"}


# ---------------------------------------------------------------------------
# 🔴 through the route an operator actually uses (판정 333)
# ---------------------------------------------------------------------------

def test_the_explorer_refuses_an_undeclared_name_by_NAME(tmp_path):
    """🔴 CALLED FOR REAL. A validator that refuses in isolation and a screen that saves
    anyway are the shape this repo has been bitten by; the refusal is only worth anything
    if it reaches the person editing the declaration.

    ⛔ A COPY OF THE ONTOLOGY, never the live one — a draft written into the owner's config
    directory is the 「내 시험이 소유자의 파일에 썼다」 failure.
    """
    from admin_auth import require_admin_token, require_admin_token_strict
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger.setup import DEFAULT_ONTOLOGY_ROOT
    from ledger_api import ontology_config_explorer_router as explorer_router

    root = tmp_path / "ontology"
    shutil.copytree(DEFAULT_ONTOLOGY_ROOT, root)
    service = OntologyExplorerService(config_root=root, draft_root=tmp_path / "drafts")
    saved_service = explorer_router._service
    explorer_router.configure_service(service)
    try:
        app = FastAPI()
        app.dependency_overrides[require_admin_token] = lambda: None
        app.dependency_overrides[require_admin_token_strict] = lambda: None
        app.include_router(explorer_router.router)
        client = TestClient(app)

        _setup, index, *_rest = service.active()
        key = next(name for name, node in index.nodes.items()
                   if node.kind == "predicate")
        created = client.post("/admin/ontology-explorer/drafts", json={
            "target_key": key, "base_snapshot_hash": index.snapshot_hash})
        assert created.status_code == 200, created.text
        draft = created.json()

        raw = dict(draft["raw"])
        raw["absence_confirmed_by"] = "no_such_predicate@1"
        saved = client.put(f"/admin/ontology-explorer/drafts/{draft['draft_id']}",
                           json={"expected_revision": 0, "raw": json.dumps(raw)})

        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["preview_valid"] is False, "the preview accepted an unresolvable name"
        named = [issue for issue in body["validation_errors"]
                 if "absence_confirmed_by" in str(issue.get("path"))]
        assert named, body["validation_errors"]
        assert "no_such_predicate@1" in named[0]["message"]
    finally:
        explorer_router.configure_service(saved_service)
