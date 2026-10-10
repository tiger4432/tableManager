# -*- coding: utf-8 -*-
"""The GET answers screen_layout_harness serves to the built pages - each one as the server answers it: the server
code of this tree, called in this process (TestClient, startup not run), on the box's database.

Regenerate (conda env assy_manager), from the repository root:
    ASSY_DATA_ROOT=<the running server's server/ dir> python client2/tests/fixtures/capture_screens.py <urls.txt>
<urls.txt> holds one path?query per line - the harness's «no answer» lines say which. Answers already in
screens_answers.json.gz are kept; the listed ones are fetched again, each stamped with when and with which commit's
server code. GET only: the client stops on any other method. An answer carrying an email, a password, a secret, a
key or a credential in a URL is not written - the run stops and names it.
"""
import gzip
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))
# Gzipped (lead 348310aee), written with no time in it: a capture again changes only the answers it fetched.
OUT = os.path.join(HERE, "screens_answers.json.gz")
ROWS = 100
SECRET = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'        # an email
                    r'|[a-z]+://[^/\s:"]+:[^@\s"]+@'                          # a credential in a URL
                    r'|(?i:bearer\s+[A-Za-z0-9._-]{10,})'
                    r'|(?i:"[^"]*(password|passwd|secret|api_?key|authorization|cookie)[^"]*"\s*:\s*"[^"]+")')

from fastapi.testclient import TestClient  # noqa: E402
from admin.auth import require_admin_token, require_admin_token_strict  # noqa: E402
from main import app  # noqa: E402

# The admin reads are behind the token. The gate is lifted for the app in this process only, the way the committed
# server/tests/support/ontology_explorer_browser_app.py does (lead 10-09: the test app's shape, not a way round);
# no token is read or sent, and the running server, its token and the config files are not touched.
app.dependency_overrides[require_admin_token] = lambda: None
app.dependency_overrides[require_admin_token_strict] = lambda: None


def get_only_client():
    """A TestClient that stops on any method but GET."""
    client = TestClient(app, raise_server_exceptions=False)
    request = client.request

    def get_only(method, url, *args, **kwargs):
        assert str(method).upper() == "GET", "capture_screens sends GET only, not %s %s" % (method, url)
        return request(method, url, *args, **kwargs)

    client.request = get_only
    return client


def server_commit():
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = git("status", "--porcelain", "--", "server")
    return git("rev-parse", "--short=9", "HEAD") + (" + uncommitted server changes" if dirty else "")


if __name__ == "__main__":
    urls = [u.strip() for u in open(sys.argv[1], encoding="utf-8") if u.strip()]
    assert all(u.startswith("/") for u in urls), [u for u in urls if not u.startswith("/")]
    answers = json.loads(gzip.decompress(open(OUT, "rb").read()).decode("utf-8")) if os.path.exists(OUT) else {"_what": "", "answers": {}}
    client = get_only_client()
    stamp = "%s · server code %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), server_commit())
    for url in urls:
        r = client.get(url)
        ctype = r.headers.get("content-type", "")
        body = r.json() if "json" in ctype else r.text
        # A table page keeps its first ROWS rows: a 950 px screen draws about thirty.
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            body["data"] = body["data"][:ROWS]
        found = SECRET.search(json.dumps(body, ensure_ascii=False))
        if found:
            raise SystemExit("not written: %s carries %r" % (url, found.group(0)[:60]))
        answers["answers"][url] = {"status": r.status_code, "type": ctype.split(";")[0], "body": body, "captured": stamp}
        print(r.status_code, len(r.content), url)
    # An answer the same as one before it is written once; the harness reads «same_as».
    first = {}
    for url in sorted(answers["answers"]):
        a = answers["answers"][url]
        if "same_as" in a:
            continue
        key = json.dumps({k: v for k, v in a.items() if k != "captured"}, sort_keys=True)
        if key in first:
            answers["answers"][url] = {"same_as": first[key]}
        else:
            first[key] = url
    answers["_what"] = ("REAL server output: GET answers of this tree's server code (TestClient, startup not run) on the "
                        "box database by capture_screens.py; each answer says when and with which commit («captured»).")
    text = json.dumps(answers, ensure_ascii=False, indent=0, sort_keys=True, separators=(",", ":"))
    with open(OUT, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as z:
            z.write(text.encode("utf-8"))
    print("answers", len(answers["answers"]), "bytes", os.path.getsize(OUT))
