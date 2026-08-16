"""Snapshot, list, check and restore ``server/config/`` backups.

The weekly snapshot runs by itself inside the auto-update scheduler process
(``run_auto_update.py``). This is the operator's door to the same code: take one
by hand before a risky change, see what exists, and restore one during a rollback.

    conda run -n assy_manager python server/scripts/backup_config.py list
    conda run -n assy_manager python server/scripts/backup_config.py check
    conda run -n assy_manager python server/scripts/backup_config.py snapshot
    conda run -n assy_manager python server/scripts/backup_config.py restore table_config_260728.json.bak

Honours ``ASSY_DATA_ROOT`` like every other entry point, so pointing it at the
isolated environment is a matter of environment, not of flags.

WHY ``restore`` IS A VERB AND NOT JUST ``cp``
--------------------------------------------
Copying the file back is genuinely one command, but there is one way to do it that
fails **silently**: an atomic write (``mv``, ``os.replace``, most editors' save)
does not fire the config watcher's ``on_modified``, so a restored
``table_config.json`` is never re-read and the operator sees no error at all
(issue #9). This verb always writes in place, and always leaves a
``config/backup/*.prerollback`` copy of what it overwrote — because a rollback that goes wrong
needs somewhere to come back to, and the broken config is the evidence.

Exit codes: ``0`` ok | ``1`` backups missing or stale (``check``) | ``2`` error.
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

import paths  # noqa: E402
import config_backup  # noqa: E402


def cmd_list(args):
    grouped = config_backup.list_snapshots()
    print(f"config dir: {paths.CONFIG_DIR}")
    print(f"backups   : {config_backup.backup_dir()}")
    if not grouped:
        print("\n  (no snapshots)")
        return 0
    print("\nnewest is last in each group; the date in the NAME is the ordering,\n"
          "not the mtime.\n")
    for stem in sorted(grouped):
        print(f"  {stem}.json")
        for when, seq, fname in grouped[stem]:
            age = (datetime.now() - when).days
            mark = "  <- newest" if (when, seq, fname) == grouped[stem][-1] else ""
            print(f"      {fname:<48} {age:>3}d old{mark}")
    return 0


def cmd_check(args):
    status = config_backup.probe()
    print(f"config dir : {status['config_dir']}")
    print(f"status     : {status['status']}")
    if status.get("newest"):
        print(f"newest     : {status['newest']}  ({status['newest_date']}, "
              f"{status['age_days']}d old)")
        print(f"covering   : {status.get('configs_covered')} config files, "
              f"{status.get('files')} snapshot files")
    if status.get("detail"):
        print(f"detail     : {status['detail']}")
    if status.get("error"):
        print(f"error      : {status['error']}")
    return 0 if status["status"] == "ok" else 1


def cmd_snapshot(args):
    result = config_backup.take_snapshot()
    print(f"config dir: {result['config_dir']}   taken at: {result['taken_at']}")
    print(f"snapshots : {result['snapshot_dir']}")
    for name in result["created"]:
        print(f"  created  {name}")
    for name in result["skipped"]:
        print(f"  skipped  {name}  (identical to today's snapshot)")
    for name in result["pruned"]:
        print(f"  pruned   {name}  (outside the "
              f"{config_backup.RETENTION_DAYS}-day retention window)")
    for err in result["errors"]:
        print(f"  ERROR    {err}")
    if not result["created"] and not result["skipped"]:
        print("  (nothing to snapshot)")
    return 2 if result["errors"] else 0


def cmd_restore(args):
    parsed = config_backup._parse(args.snapshot)
    if not parsed:
        print(f"not a config snapshot filename: {args.snapshot}", file=sys.stderr)
        print("expected the form <config>_<yymmdd>.json.bak - run `list` to see "
              "what exists.", file=sys.stderr)
        return 2

    stem, when, seq, fname = parsed
    src = config_backup.snapshot_path(fname)
    dest = os.path.join(paths.CONFIG_DIR, f"{stem}.json")
    if not os.path.isfile(src):
        print(f"no such snapshot: {src}", file=sys.stderr)
        return 2

    age = (datetime.now() - when).days
    print(f"restore  {fname}  ({when:%Y-%m-%d}, {age}d old)")
    print(f"     ->  {stem}.json")

    if os.path.isfile(dest):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        keep_dir = config_backup.backup_dir()
        os.makedirs(keep_dir, exist_ok=True)
        keep = os.path.join(
            keep_dir, f"{os.path.basename(dest)}.prerollback.{stamp}")
        shutil.copy(dest, keep)
        print(f"  current file kept as {keep}")
        if config_backup._same_bytes(src, dest):
            print("  NOTE: the snapshot is byte-identical to the current file - "
                  "restoring it changes nothing.")

    if not args.yes:
        print("\nre-run with --yes to actually write it.")
        return 0

    # In place, never a rename: an atomic write does not fire the config watcher,
    # so table_config.json would be restored on disk and never reloaded.
    with open(src, "rb") as fsrc, open(dest, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst)
        fdst.flush()
        os.fsync(fdst.fileno())
    print(f"  written in place: {dest}")
    if stem == "table_config":
        print("  the config watcher should pick this up within ~5s "
              "(look for 'Physical database schema synced successfully.').")
        print("  NOTE: reverting a declaration does NOT drop tables or columns "
              "that were already created - see ROLLBACK_PROCEDURE section 5.")
    else:
        print("  plan-family config is re-read on the next request; no restart.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="show every snapshot, oldest first")
    sub.add_parser("check", help="is the newest snapshot fresh? (exit 1 if not)")
    sub.add_parser("snapshot", help="take one now")
    r = sub.add_parser("restore", help="copy a snapshot back over the live config")
    r.add_argument("snapshot", help="snapshot filename, e.g. table_config_260728.json.bak")
    r.add_argument("--yes", action="store_true", help="actually write (default: dry run)")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        return {"list": cmd_list, "check": cmd_check,
                "snapshot": cmd_snapshot, "restore": cmd_restore}[args.cmd](args)
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
