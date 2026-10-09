# -*- coding: utf-8 -*-
"""The GET answers screen_layout_harness serves to the built pages - each one as the server answers it: the server
code of this tree, called in this process (TestClient, startup not run), on the box's database.

Regenerate (conda env assy_manager), from the repository root:
    ASSY_DATA_ROOT=<the running server's server/ dir> python client2/tests/fixtures/capture_screens.py <urls.txt>
<urls.txt> holds one path?query per line - the harness's «no answer» lines say which. Answers already in
screens_answers.json are kept; the listed ones are fetched again. GET only: any other line is refused.
"""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))
OUT = os.path.join(HERE, "screens_answers.json")
ROWS = 100

from fastapi.testclient import TestClient  # noqa: E402
from admin.auth import require_admin_token, require_admin_token_strict  # noqa: E402
from main import app  # noqa: E402

# The admin reads are behind the token; like capture_admin_indexes.py calling the route's function directly, the
# gate is lifted in this process only - the way server/tests/support/ontology_explorer_browser_app.py does - and no
# token is read or sent. The running server and its token are not touched. GET only.
app.dependency_overrides[require_admin_token] = lambda: None
app.dependency_overrides[require_admin_token_strict] = lambda: None

if __name__ == "__main__":
    urls = [u.strip() for u in open(sys.argv[1], encoding="utf-8") if u.strip()]
    assert all(u.startswith("/") for u in urls), [u for u in urls if not u.startswith("/")]
    answers = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {"_what": "", "answers": {}}
    client = TestClient(app, raise_server_exceptions=False)
    for url in urls:
        r = client.get(url)
        ctype = r.headers.get("content-type", "")
        body = r.json() if "json" in ctype else r.text
        # A table page keeps its first ROWS rows: a 950 px screen draws about thirty.
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            body["data"] = body["data"][:ROWS]
        answers["answers"][url] = {"status": r.status_code, "type": ctype.split(";")[0], "body": body}
        print(r.status_code, len(r.content), url)
    # An answer the same as one before it is written once; the harness reads «same_as».
    first = {}
    for url in sorted(answers["answers"]):
        a = answers["answers"][url]
        if "same_as" in a:
            continue
        key = json.dumps(a, sort_keys=True)
        if key in first:
            answers["answers"][url] = {"same_as": first[key]}
        else:
            first[key] = url
    answers["_what"] = ("REAL server output: GET answers of this tree's server code (TestClient, startup not run) on "
                        "the box database, last captured %s by capture_screens.py." % datetime.now(timezone.utc).isoformat())
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False, indent=0, sort_keys=True, separators=(",", ":"))
    print("answers", len(answers["answers"]), "bytes", os.path.getsize(OUT))
