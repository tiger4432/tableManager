"""Run board_fixed.py with the assy_test URL in the env (built here from database.json, never printed); lines to
board.out. usage: [BOARD_WT=<worktree>] [BOARD_RUNS=<dir>] [BOARD_OUT=<file>] run_board.py [board ...]"""
import json
import os
import subprocess
import sys

from sqlalchemy.engine import make_url

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(r"C:/Users/kk980/Developments/assyManager/server/config/database.json", encoding="utf-8"))
url = make_url(cfg["url"]).set(database=os.environ.get("BOARD_DB", "assy_test")).render_as_string(hide_password=False)
env = dict(os.environ, ASSY_PG_TEST_DATABASE_URL=url, PYTHONIOENCODING="utf-8")
with open(os.environ.get("BOARD_OUT") or os.path.join(HERE, "board.out"), "w", encoding="utf-8") as out:
    code = subprocess.run([sys.executable, os.path.join(HERE, os.environ.get("BOARD_SCRIPT", "board_fixed.py")), os.environ.get("BOARD_WT", "C:/wt-app-board"),
                           os.environ.get("BOARD_RUNS") or os.path.join(HERE, "runs")] + sys.argv[1:], cwd=os.path.dirname(HERE), env=env,
                          stdout=out, stderr=subprocess.STDOUT).returncode
print("exit", code)
