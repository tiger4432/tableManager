# -*- coding: utf-8 -*-
"""총괄 126ea5656 — the watcher sizes a file ONCE, the moment it appears in raws/, to pick its
lane. The upload route wrote in place, so an upload appeared before its bytes did and an 11 MB
file took the inline lane. It now writes beside raws/ and moves the whole file in: the first
instant the file exists in raws/, it has every byte."""
import os

import paths

BODY = b"plan_id,target_qty\r\n" + b"P-1,1\r\n" * 5000


def test_an_upload_appears_in_raws_only_whole(client, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "workspace_path",
                        lambda *parts: str(tmp_path.joinpath("ws", *parts)))
    raws = tmp_path / "ws" / "production_plan" / "raws"
    moves = []
    real_replace = os.replace

    def watched_replace(src, dst):
        moves.append({"from_raws": os.path.dirname(os.path.abspath(src)) == str(raws),
                      "size": os.path.getsize(src), "into": os.path.dirname(dst),
                      "raws_before": sorted(os.listdir(raws))})
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", watched_replace)
    r = client.post("/tables/production_plan/upload", params={"user": "kim"},
                    files={"file": ("plan.csv", BODY, "text/csv")})

    assert r.status_code == 200, r.text
    assert len(moves) == 1, "the file must arrive in raws/ by one move"
    assert moves[0]["size"] == len(BODY) and not moves[0]["from_raws"], moves
    assert moves[0]["raws_before"] == [], "nothing of the upload may be in raws/ before the move"
    assert [p.read_bytes() for p in raws.iterdir()] == [BODY]
    assert not [p for p in raws.parent.iterdir() if p.name.startswith(".upload.")], \
        "the temporary must not outlive the upload"
