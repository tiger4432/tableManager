# -*- coding: utf-8 -*-
"""The plan the ledger declaration form draws for the sample's `dt_job` source, as GET /authoring/plan
serves it for `source_plan|dt_job` - two of its roles inherit the source's attributes.

Regenerate (conda env assy_manager), from the repository root:
    python client2/tests/fixtures/capture_authoring_inherited_plan.py

Reads only committed files - the sample ledger_config and the sample table_config - so this is the
server's answer on any box. Writes authoring_inherited_plan.json beside this file.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from ledger.config_authoring import authoring_plan  # noqa: E402
from ledger.config_explorer_service import OntologyExplorerService  # noqa: E402
from ledger.setup import load_physical_catalog  # noqa: E402

SAMPLE = os.path.join(ROOT, "server", "config", "sample")

if __name__ == "__main__":
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as f:
        bundle = json.load(f)
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    prefix = OntologyExplorerService.authoring_prefix("source_plan|dt_job")
    plan = authoring_plan(bundle, catalog, selection_prefix=prefix)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    out = {"captured_by": "client2/tests/fixtures/capture_authoring_inherited_plan.py", "server_at": commit,
           "base": prefix, "fields": plan["fields"]}
    path = os.path.join(HERE, "authoring_inherited_plan.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    inherited = [row["path"] for row in plan["fields"]
                 if (row.get("ground") or {}).get("rule") == "inherited_from_source"]
    print(len(plan["fields"]), "rows,", len(inherited), "inherited ->", path)
