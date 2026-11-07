# -*- coding: utf-8 -*-
"""Fake pages the browser collector is tried on (lead 11-07) - stdlib only, http://127.0.0.1:8095

    /webmail.html      one screen: a list that loads more as it scrolls, a reading pane that opens in place
                       0.2-2 s after a click (the URL never changes); every 11th item from the 8th never loads;
                       the pane is in the DOM, hidden, from the start, and a hidden pane keeps the last body
    /board?page=N      a list of links, one page each; a post opens on its own URL; Next is a button
    /board/post/<id>

    python tools/browser_bench/serve.py [port]
"""
import html
import http.server
import os
import random
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8095
PAGES, PER_PAGE = 5, 20
AUTHORS = ("Kim", "Lee", "Park", "Choi", "Jung")
WORDS = ("wafer", "lot", "yield", "map", "tool", "chamber", "recipe", "shift", "review", "hold", "release", "die")


def _post(post_id):
    rand = random.Random(post_id)
    title = " ".join(rand.choice(WORDS) for _ in range(3)).capitalize() + " #%d" % post_id
    body = " ".join(rand.choice(WORDS) for _ in range(40))
    return title, AUTHORS[post_id % len(AUTHORS)], "2026-11-%02d" % (1 + post_id % 28), body


def _page(title, body):
    return ("<!doctype html><html><head><meta charset='utf-8'><title>%s</title>"
            "<link rel='stylesheet' href='/bench.css'></head><body>%s</body></html>" % (html.escape(title), body))


def board(page):
    page = min(max(page, 1), PAGES)
    first = (page - 1) * PER_PAGE + 1
    rows = "".join("<tr class='post-row'><td class='post-no'>%d</td><td class='post-title'><a href='/board/post/%d'>%s</a>"
                   "</td><td class='post-author'>%s</td><td class='post-date'>%s</td></tr>"
                   % ((i,) + (i,) + tuple(html.escape(c) for c in _post(i)[:3]))
                   for i in range(first, first + PER_PAGE))
    nav = ("<button id='next-page' onclick=\"location.href='/board?page=%d'\">Next</button>" % (page + 1)
           if page < PAGES else "")
    return _page("Board %d" % page, "<h1>Board</h1><p id='page-no'>Page %d of %d</p><table id='post-list'><thead><tr>"
                 "<th>No</th><th>Title</th><th>Author</th><th>Date</th></tr></thead><tbody>%s</tbody></table>%s"
                 % (page, PAGES, rows, nav))


def post(post_id):
    title, author, date, body = (html.escape(c) for c in _post(post_id))
    return _page(title, "<article id='post'><h1 class='post-title'>%s</h1><p class='post-meta'>"
                 "<span class='post-author'>%s</span> <span class='post-date'>%s</span> <span class='post-no'>%d</span>"
                 "</p><div class='post-body'>%s</div></article><a href='/board'>List</a>"
                 % (title, author, date, post_id, body))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/board":
            page = urllib.parse.parse_qs(url.query).get("page", ["1"])[0]
            return self._send(board(int(page) if page.isdigit() else 1))
        if url.path.startswith("/board/post/") and url.path.rsplit("/", 1)[1].isdigit():
            post_id = int(url.path.rsplit("/", 1)[1])
            if 1 <= post_id <= PAGES * PER_PAGE:
                return self._send(post(post_id))
        if url.path == "/":
            return self._send(_page("Browser bench", "<a href='/webmail.html'>Webmail</a> <a href='/board'>Board</a>"))
        return super().do_GET()

    def _send(self, text):
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print("browser bench on http://127.0.0.1:%d" % PORT, flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
