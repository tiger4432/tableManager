# -*- coding: utf-8 -*-
"""The Help panel's Guide (owner 11-06): the guides the answer reads (`help_guides.GUIDES`), cut at their headings
as written - what the answer's `cut` takes out (the retired sentences, the Status line) stays for the reader.

    seat                  gate
    sections              every heading a section, in order; the sections' text is the guide's text less its headings
    reader                every guide, with its tabs from GUIDE_TABS; a retired sentence the reader keeps and cut drops
    /admin/help/guides    the guides; a missing one 404 by name
"""
import os
import shutil

import pytest

import paths
from admin import help_guides

_FENCE = "```"


@pytest.fixture(name="guides")
def fixture_guides(tmp_path, monkeypatch):
    for guide in help_guides.GUIDES:
        os.makedirs(tmp_path / os.path.dirname(guide), exist_ok=True)
        shutil.copyfile(os.path.join(paths.REPO_ROOT, guide), tmp_path / guide)
    monkeypatch.setattr(paths, "REPO_ROOT", str(tmp_path))
    return tmp_path


def _headings_and_body(text):
    """(heading lines, the lines under the first heading that are not headings) - a fence hides a heading."""
    heads, body, fence = [], [], False
    for line in text.split("\n"):
        if line.startswith(_FENCE):
            fence = not fence
        if not fence and help_guides._HEADING.match(line):
            heads.append(line)
        elif heads:
            body.append(line)
    return heads, body


def test_every_guide_is_read_whole_in_heading_order(guides):
    read = help_guides.reader()
    assert [g["path"] for g in read] == list(help_guides.GUIDES)
    for g in read:
        assert g["tabs"] == list(help_guides.GUIDE_TABS[g["path"]])
        with open(guides / g["path"], encoding="utf-8") as f:
            heads, body = _headings_and_body(f.read())
        assert len(heads) > 3, "canary: %s has headings" % g["file"]
        assert [s["path"][-1] for s in g["sections"]] == [help_guides._HEADING.match(h).group(2).strip() for h in heads]
        assert "\n".join(s["text"] for s in g["sections"]).split("\n") == body


def test_the_reader_keeps_the_retired_sentences_the_answer_drops(guides):
    kept = [s["text"] for g in help_guides.reader() for s in g["sections"] if help_guides._RETIRED.search(s["text"])]
    assert kept, "canary: the committed guides carry a retired mark"
    pieces = [p for guide in help_guides.GUIDES
              for p in help_guides.cut(guide, (guides / guide).read_text(encoding="utf-8"))]
    assert pieces and not [p for p in pieces if help_guides._RETIRED.search(p["text"])]


def test_the_route_reads_the_guides_and_names_a_missing_one(client, guides):
    got = client.get("/admin/help/guides")
    assert got.status_code == 200
    assert [g["file"] for g in got.json()["guides"]] == [os.path.basename(g) for g in help_guides.GUIDES]
    os.remove(guides / help_guides.GUIDES[2])
    gone = client.get("/admin/help/guides")
    assert gone.status_code == 404 and os.path.basename(help_guides.GUIDES[2]) in gone.json()["detail"]
