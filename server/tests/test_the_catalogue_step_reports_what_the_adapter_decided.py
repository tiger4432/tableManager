# -*- coding: utf-8 -*-
"""S-180 ⓐ. The setup order's first step, judged by the catalogue adapter and nobody else.

🔴 THE WHOLE POINT IS THAT THIS DOMAIN DECIDES NOTHING. `_adapt_physical_catalog` already
answers three ways for a relation — it returns one, it raises `invalid_catalog`, or it
silently skips it — and those three ARE the three populations. A resolver that re-spelled
「what makes a catalogue entry usable」 would be a second judge, and on the day the two
disagreed both would look right. 판정 313: 「등록기 안에 거절 조건 «재작성 0»」.

⚠️ AND A SKIPPED RELATION IS `ineffective`, NOT `rejected`. The adapter passes over a table
with no `column_types` without complaint: the operator wrote a name and nothing the reader
can use. 「안 적은 것과 틀린 것은 다르다」 — one is a next step, the other is a mistake, and an
operator does something different about each.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import config_resolve_report as crr                                   # noqa: E402

#: One bundle carrying all three answers, because a fixture that only shows the happy one
#: cannot tell a working resolver from one that never refuses.
BUNDLE = {
    "__comment": "annotation keys are skipped, and that is not a state",
    "s180_ok": {"column_types": {"a": "string", "b": "number"},
                "composite_key_source": ["a"]},
    "s180_no_columns": {"column_types": {}},
    "s180_bad_kind": {"column_types": {"a": "string"}, "kind": "veiw"},
}


@pytest.fixture()
def report(monkeypatch):
    from database import crud

    monkeypatch.setattr(crud, "load_table_config_or_raise", lambda: dict(BUNDLE))
    return crr.resolve_report([crr.DOMAIN_CATALOG])["domains"][0]


def _subjects(domain, population):
    return [e["subject"] for e in domain[population]]


def _code_of(fn):
    """The function's CODE, with its docstring removed.

    ⚠️ A DRIFT ORACLE THAT READS THE PROSE SCORES THE PROSE. The first version of the
    two assertions below went red on this function's own docstring, which NAMES `open(` and
    `invalid_catalog` in order to say they must not appear - so the note explaining the rule
    was read as breaking it. Measured, not foreseen.
    """
    import inspect

    source = inspect.getsource(fn)
    doc = inspect.getdoc(fn)
    if doc:
        for line in doc.splitlines():
            source = source.replace(line, "")
    return source


# ---------------------------------------------------------------------------
# the three answers
# ---------------------------------------------------------------------------

def test_all_three_states_appear_in_one_bundle(report):
    """🔴 THE GATE (판정 313). Three populations, three relations, one file."""
    assert _subjects(report, "effective") == ["s180_ok"]
    assert _subjects(report, "ineffective") == ["s180_no_columns"]
    assert _subjects(report, "rejected") == ["s180_bad_kind"]
    assert report["counts"] == {"effective": 1, "ineffective": 1, "rejected": 1}


def test_the_refusal_carries_the_adapters_own_words(report):
    """🔴 THE SECOND SPELLING OF A REFUSAL IS THE DEFECT. The detail quotes the path and the
    message the adapter raised, and `fields` carries them structurally, so this file can
    never start explaining a refusal in its own words."""
    refused = report["rejected"][0]
    assert refused["fields"]["code"] == "invalid_catalog"
    assert refused["fields"]["path"] == "s180_bad_kind.kind"
    assert "table" in refused["fields"]["message"] and "view" in refused["fields"]["message"]
    assert refused["fields"]["message"] in refused["detail"]


def test_a_relation_with_no_columns_is_ineffective_and_not_a_defect(report):
    """⚠️ 「안 적은 것」 AND 「틀린 것」 MUST NOT LAND IN THE SAME BUCKET — the operator's next
    move differs, and the whole setup order exists to tell them apart."""
    skipped = report["ineffective"][0]
    assert skipped["reason"] == crr.REASON_NOT_DECLARED
    assert skipped["reason"] != crr.REASON_MAPPING_UNAVAILABLE


def test_an_annotation_key_is_not_a_relation(report):
    """⛔ `__comment` IS DOCUMENTATION. Counting it would make every catalogue report one
    phantom relation that no step can ever satisfy."""
    for population in crr.POPULATIONS:
        assert "__comment" not in _subjects(report, population)


def test_a_catalogue_that_cannot_be_read_refuses_by_file_and_says_what_it_costs(monkeypatch):
    """⚠️ THE FILE-LEVEL FAILURE IS NOT A RELATION-LEVEL ONE. If the catalogue will not load,
    the answer is not 「zero relations」 — it is 「the next five steps have nothing to point
    at」, and reporting an empty effective list would read as the first."""
    from database import crud

    def boom():
        raise ValueError("unterminated string at line 3")

    monkeypatch.setattr(crud, "load_table_config_or_raise", boom)
    report = crr.resolve_report([crr.DOMAIN_CATALOG])["domains"][0]

    assert report["counts"] == {"effective": 0, "ineffective": 0, "rejected": 1}
    refused = report["rejected"][0]
    assert refused["scope"] == crr.SCOPE_FILE
    assert refused["reason"] == crr.REASON_MAPPING_UNAVAILABLE
    assert "unterminated string" in refused["detail"]
    assert report["sources"][0]["status"] == "degraded"


# ---------------------------------------------------------------------------
# 🔴 it judges nothing itself
# ---------------------------------------------------------------------------

def test_the_registrar_opens_no_file_of_its_own():
    """🔴 THE DRIFT ASSERTION (판정 313). Reading `table_config.json` here would be a second
    reader of the same file, free to disagree with the loader about what is in it — and the
    loader is the one production boots from."""
    body = _code_of(crr._resolve_catalog)
    for spelled in ("open(", "json.load", "read_text"):
        assert spelled not in body, spelled
    assert "load_table_config_or_raise" in body


def test_the_registrar_rewrites_no_refusal_condition():
    """🔴 SCORED ON THE SOURCE, because a condition copied here would agree with the adapter
    on the day it was copied and drift silently afterwards."""
    body = _code_of(crr._resolve_catalog)
    assert "_adapt_physical_catalog" in body
    for rebuilt in ("CATALOG_KINDS", '"view"', "'view'", "kind ==", "invalid_catalog"):
        assert rebuilt not in body, (
            "the catalogue registrar decides for itself again: %s" % rebuilt)


def test_the_domain_is_registered_and_is_not_found_by_position():
    """⚠️ S-180 ⓐ-0 made the contract harnesses select by name; this pins that the new domain
    is reachable by name here too, which is how every other reader must find it."""
    names = [d["domain"] for d in crr.resolve_report()["domains"]]
    assert crr.DOMAIN_CATALOG in names
    assert len(names) == len(set(names)), names
