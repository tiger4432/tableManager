# -*- coding: utf-8 -*-
"""What the company sign-in routes answer, as the screen reads them (lead 2095014ee: the screen harness runs on the
server's own spelling).

Regenerate (conda env assy_manager), from the repository root:
    python client2/tests/fixtures/capture_sso_spelling.py

The real routes, driven through the sign-in suite's fake issuer and the suite's in-memory database
(server/tests/test_company_sign_in_decides_who_is_asking.py) - nothing is written outside them. The probe is put into
server/tests for the run and removed after it. The new key's secret is replaced by a placeholder. Writes
sso_spelling.json beside this file.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROBE = os.path.join(ROOT, "server", "tests", "test_zz_capture_sso_spelling.py")

PROBE_TEXT = '''import json
import os
import threading

from starlette.websockets import WebSocketDisconnect

from admin import auth
from test_company_sign_in_decides_who_is_asking import RETURNS, _client, _setup, _sign_in
from test_company_sign_in_decides_who_is_asking import off  # noqa: F401  (fixture)


def _answer(res):
    body = None
    if res.content:
        try:
            body = res.json()
        except ValueError:
            body = None
    return {"status": res.status_code, "body": body, "challenge": res.headers.get(auth.GATE_CHALLENGE_HEADER)}


def test_capture(monkeypatch, tmp_path, off):  # noqa: F811
    out = {}
    with _client() as client:
        out["me_off"] = _answer(client.get("/auth/me"))
        out["keys_off"] = _answer(client.get("/auth/keys"))
    fake = _setup(monkeypatch, tmp_path, RETURNS[0])
    client = _client()
    out["me_signed_out"] = _answer(client.get("/auth/me"))
    out["api_signed_out"] = _answer(client.get("/tables"))
    heard = {"closed": False}

    def listen(socket):
        try:
            socket.receive_text()
        except WebSocketDisconnect as exc:
            heard.update(closed=True, code=exc.code, reason=exc.reason)
    with client.websocket_connect("/ws") as socket:
        listener = threading.Thread(target=listen, args=(socket,), daemon=True)
        listener.start()
        listener.join(5)
    out["ws_signed_out"] = heard
    _sign_in(client, fake)
    out["me_signed_in"] = _answer(client.get("/auth/me"))
    out["admin_not_listed"] = _answer(client.get("/admin/chain/pause"))
    made = client.post("/auth/keys", json={"name": "nightly"})
    out["key_made"] = _answer(made)
    out["key_made"]["body"] = dict(out["key_made"]["body"], key="<the key>")
    out["keys_listed"] = _answer(client.get("/auth/keys"))
    out["key_name_taken"] = _answer(client.post("/auth/keys", json={"name": "nightly"}))
    out["key_name_required"] = _answer(client.post("/auth/keys", json={"name": "  "}))
    out["key_deleted"] = _answer(client.delete("/auth/keys/" + made.json()["id"]))
    out["logout"] = _answer(client.post("/auth/logout"))
    out["me_after_logout"] = _answer(client.get("/auth/me"))
    with open(os.environ["SSO_SPELLING_OUT"], "w", encoding="utf-8") as fh:
        json.dump(out, fh)
'''

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "answers.json")
        with open(PROBE, "w", encoding="utf-8", newline="\n") as f:
            f.write(PROBE_TEXT)
        try:
            run = subprocess.run([sys.executable, "-m", "pytest", PROBE, "-q", "-p", "no:cacheprovider"],
                                 cwd=os.path.join(ROOT, "server"), env=dict(os.environ, SSO_SPELLING_OUT=raw))
        finally:
            os.remove(PROBE)
        if run.returncode != 0:
            sys.exit("the capture run failed - nothing written")
        with open(raw, encoding="utf-8") as f:
            answers = json.load(f)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    out = {"captured_by": "client2/tests/fixtures/capture_sso_spelling.py", "server_at": commit, **answers}
    path = os.path.join(HERE, "sso_spelling.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("wrote", path)
