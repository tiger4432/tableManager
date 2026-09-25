"""The scheduler's child for one retroactive run (총괄 7d2c5845b · 811ff7f06 · f453968fe).

    python -m admin.retroactive_run <run_id>

Runs a row the scheduler already claimed, in this process, through the function a CLI's
run goes through (`retroactive.run_claimed`). Logs to retroactive.log.
Exit 0 done · 2 cancelled or refused · 1 failed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_process_logger  # noqa: E402

LOG_FILENAME = "retroactive.log"
logger = get_process_logger("Retroactive", LOG_FILENAME)


def main(argv=None):
    from admin import retroactive

    args = sys.argv[1:] if argv is None else argv
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


if __name__ == "__main__":
    sys.exit(main())
