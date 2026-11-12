# -*- coding: utf-8 -*-
"""A mail client blocks a report's scripts (owner 11-10): with them taken out, the file still shows every layer of a
chip, each with its layer as caption - nothing in the file is hidden. Where a script runs it folds the strip to one
picture the wheel turns (owner 10-24); one drawing, two readers."""
import re

from chain import report_html


def _page():
    layers = [{"src": "data:image/png;base64,%s" % n, "layer": n} for n in ("L1", "L2", "L3")]
    embedded = {"void": [{"wafer": "W1", "layers": layers, **layers[0]},
                         {"src": "data:image/png;base64,W2", "wafer": "W2"}]}
    return report_html.page("W1 report", "R", {"layout": [{"kind": "image"}]}, {}, embedded, {})


def _without_scripts(page):
    return re.sub(r"<script>.*?</script>", "", page, flags=re.S)


def test_without_its_script_the_file_shows_as_many_pictures_as_layers():
    page = _page()
    assert "STACK" not in page and "<script>" in page, "the folding script is still written for the server's page"
    stack = re.search(r'<figure class="stack".*?</figure></div><figcaption>.*?</figcaption></figure>',
                      _without_scripts(page), flags=re.S).group(0)
    images = re.findall(r"<img[^>]*>", stack)
    assert len(images) == 3 and not [i for i in images if re.search(r"\shidden\b", i)], images
    assert re.findall(r"<figcaption>(L\d)</figcaption>", stack) == ["L1", "L2", "L3"], stack


def test_nothing_in_the_file_is_hidden():
    assert not re.search(r"<[^>]*\shidden\b", _without_scripts(_page()))
