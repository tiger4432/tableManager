# -*- coding: utf-8 -*-
"""Shipped and built is still not delivered if the browser never asks for it.

Vite names every bundle after its content (`walk-eV9dpnRJ.js`), so an asset may be cached
forever - a new build simply asks for a new name. The html is the one file whose name
never changes, and it is the file that HOLDS those names. A cached copy therefore points
a fresh browser at the PREVIOUS build, and "the bundle is in dist" stops meaning "the
user has it".

Measured 2026-09-06: page responses carried `last-modified` and `etag` and no
`cache-control` at all. Four handlers spelled a no-cache dict out by hand and the SPA
catch-all - which serves every page WITHOUT its own route, `walk.html` among them -
spelled none, so the most recently added pages were exactly the ones missing it.

⛔ THE ASSETS ARE DELIBERATELY UNTOUCHED. Content-hashed names are what make a permanent
asset cache safe, and adding no-cache there would throw that away for nothing.
"""
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                       # noqa: E402


def test_the_header_says_do_not_reuse():
    """`no-cache` revalidates rather than reusing; `no-store` refuses to keep it at all.
    Either satisfies the requirement, and this pins that one of them is stated."""
    value = main.HTML_NO_CACHE_HEADERS["Cache-Control"]
    assert "no-cache" in value or "no-store" in value
    assert "max-age=0" in value


def test_there_is_one_spelling_of_it():
    """🔴 FOUR HANDLERS WROTE THIS DICT OUT, AND THE ONE THAT MATTERED WROTE NONE. That is
    how a page added later ends up without the header nobody remembered was per-handler."""
    body = inspect.getsource(main)
    hand_written = body.count('"Cache-Control": "no-store, no-cache, must-revalidate')
    assert hand_written == 1, (
        "%d hand-written copies of the header remain; one of them will drift" % hand_written)


def test_the_catch_all_gives_html_the_header():
    """🔴 THE REPAIR. This route is what serves `walk.html` and every page added after it,
    because those pages have no route of their own."""
    body = inspect.getsource(main)
    tail = body.split("def serve_spa", 1)[-1] if "def serve_spa" in body else body
    assert "FileResponse(target_path, headers=HTML_NO_CACHE_HEADERS)" in tail
    assert "FileResponse(index_file, headers=HTML_NO_CACHE_HEADERS)" in tail


def test_a_non_html_file_from_the_dist_root_is_left_alone():
    """⛔ ONLY THE HTML. A hashed asset must stay cacheable, and this keeps the branch
    that decides so from quietly widening."""
    body = inspect.getsource(main)
    assert '.lower().endswith(".html")' in body
    assert "return FileResponse(target_path)\n" in body, \
        "the non-html arm disappeared - every dist file now gets no-cache"


def test_the_asset_mount_is_untouched():
    """The assets are served by a StaticFiles mount, which this change does not wrap.
    Wrapping it would be a different radius and was not asked for."""
    body = inspect.getsource(main)
    assert 'app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")' in body


def test_every_page_handler_uses_the_one_constant():
    """The four named pages must not drift away from the catch-all's answer."""
    body = inspect.getsource(main)
    assert body.count("no_cache_headers = HTML_NO_CACHE_HEADERS") == 4
