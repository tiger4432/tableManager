# -*- coding: utf-8 -*-
"""The skeleton the ledger declaration form is drawn from, as GET /authoring/schema serves it.

Regenerate (conda env assy_manager), from the repository root:
    python client2/tests/fixtures/capture_authoring_skeleton.py

`skeleton` and `authorable_kinds` come from the validator's own constants - no config file is read -
so this is the server's answer on any box. Writes authoring_skeleton.json beside this file.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from ledger.config_explorer_service import OntologyExplorerService  # noqa: E402

if __name__ == "__main__":
    schema = OntologyExplorerService().authoring_schema()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    out = {"captured_by": "client2/tests/fixtures/capture_authoring_skeleton.py", "server_at": commit,
           "authorable_kinds": schema["authorable_kinds"], "skeleton": schema["skeleton"]}
    path = os.path.join(HERE, "authoring_skeleton.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("kinds", [k["id"] for k in out["authorable_kinds"]], "->", path)
