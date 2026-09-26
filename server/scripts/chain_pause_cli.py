"""Pause or resume the chain from a terminal - the admin buttons' own function (총괄 3840af307).

    conda run -n assy_manager python server/scripts/chain_pause_cli.py pause --reason "why"
    conda run -n assy_manager python server/scripts/chain_pause_cli.py resume
    conda run -n assy_manager python server/scripts/chain_pause_cli.py status
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import control as chain_control                           # noqa: E402
from database.database import SessionLocal                           # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pause").add_argument("--reason", default="")
    sub.add_parser("resume")
    sub.add_parser("status")
    args = p.parse_args(argv)
    if args.cmd == "pause":
        db = SessionLocal()
        try:
            print(chain_control.pause_now(db, "cli", args.reason))
        finally:
            db.close()
    elif args.cmd == "resume":
        chain_control.resume()
        print("resumed")
    else:
        print(chain_control.paused() or "running")
    return 0


if __name__ == "__main__":
    sys.exit(main())
