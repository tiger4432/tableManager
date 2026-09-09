# -*- coding: utf-8 -*-
"""운영에서는 `python -m chain <도구>` 하나만 외우면 됩니다 -- 스크립트 이름은 몰라도 됩니다.

    python -m chain                어떤 도구가 있는지
    python -m chain replay --help  그 도구의 설명서 (도구가 자기 것을 답합니다)

🔴 THIS ENTRY POINT IMPLEMENTS NOTHING (S-109), exactly as `python -m ledger` does not: each
subcommand resolves to a module that already exists and calls its `main(argv)` with the rest
of the command line untouched. Two doors, one shape, and neither knows any tool's arguments.
"""
from __future__ import annotations

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

TOOLS = {
    "replay": ("scripts.chain_replay_cli",
               "규칙을 다시 적용(R1) · 낡은 소스를 걷기(R2). 기본은 보고, --apply 만 씀"),
}


def _usage(out=None) -> None:
    # ⛔ RESOLVED HERE, NOT IN THE SIGNATURE. A default of `sys.stdout` binds the stream
    # this module was IMPORTED with, so anything that replaces it later - a test harness, a
    # supervisor capturing output - would be written past.
    out = sys.stdout if out is None else out
    print("python -m chain <도구> [옵션]\n", file=out)
    width = max(len(name) for name in TOOLS)
    for name in sorted(TOOLS):
        print(f"  {name:<{width}}  {TOOLS[name][1]}", file=out)
    print("\n각 도구의 설명서는 그 도구가 답합니다: "
          "python -m chain <도구> --help", file=out)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        _usage()
        return 0
    name, rest = argv[0], argv[1:]
    if name not in TOOLS:
        print(f"'{name}' 은 이 문의 도구가 아닙니다.\n", file=sys.stderr)
        _usage(sys.stderr)
        return 2
    return importlib.import_module(TOOLS[name][0]).main(rest) or 0


if __name__ == "__main__":
    raise SystemExit(main())
