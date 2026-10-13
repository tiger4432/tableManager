"""The scheduler's child for one retroactive run (총괄 7d2c5845b · 811ff7f06 · f453968fe).

    python -m admin.retroactive_run <run_id>
    python -m admin.retroactive_run --slice <k>/<N> <run_id>

Runs a row the scheduler already claimed, in this process, through the function a CLI's
run goes through (`retroactive.run_claimed`). Logs to retroactive.log.
Exit 0 done · 2 cancelled or refused · 1 failed.
`--slice`: one slice of that run's re-translate, started by the run's own process (`retroactive.run_slice`) - its range
on stdin, its answers on stdout, its lines up stderr into the run's log. Exit 0 answered · 1 failed · 2 usage.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import answers_on_stdout, get_process_logger  # noqa: E402

LOG_FILENAME = "retroactive.log"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["--slice"]:
        return _slice(args[1:])
    # the process's name before anything opens a log of its own - the first caller names it
    logger = get_process_logger("Retroactive", LOG_FILENAME)
    from admin import retroactive

    if len(args) != 1:
        logger.error("usage: python -m admin.retroactive_run <run_id>")
        return 2
    try:
        retroactive.run_claimed(args[0], log=logger.info)
        return 0
    except (retroactive.RetroactiveRefused, retroactive.RunCancelled) as exc:
        logger.warning("[Retroactive] run_id=%s %s", args[0], exc)
        return 2
    except Exception:                                            # noqa: BLE001
        logger.exception("[Retroactive] run_id=%s failed", args[0])
        return 1


def _slice(args):
    # the answers keep stdout; anything else printed goes up stderr with the lines (`chain.slots.main`'s way). A name of
    # its own: its connections are its own in pg_stat_activity, and its beat reads only them.
    answers = answers_on_stdout()
    logger = get_process_logger("Retroactive_slice" + (args[0].split("/")[0] if args else ""), LOG_FILENAME,
                                relay=sys.stderr)
    if len(args) != 2:
        logger.error("usage: python -m admin.retroactive_run --slice <k>/<N> <run_id>")
        return 2
    from admin import retroactive

    try:
        retroactive.run_slice(args[1], sys.stdin, lambda said: answers.write(json.dumps(said, default=str) + "\n"),
                              logger.info)
        return 0
    except Exception:                                            # noqa: BLE001
        logger.exception("[Retroactive] run_id=%s slice %s failed", args[1], args[0])
        return 1


if __name__ == "__main__":
    sys.exit(main())
