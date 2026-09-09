# -*- coding: utf-8 -*-
"""운영에서는 `python -m ledger <도구>` 하나만 외우면 됩니다 -- 스크립트 파일 이름은 몰라도 됩니다.

    python -m ledger                 어떤 도구가 있는지
    python -m ledger backfill --help 그 도구의 설명서 (각 도구가 자기 것을 답합니다)
    python -m ledger restamp --apply

🔴 THIS ENTRY POINT IMPLEMENTS NOTHING (S-109). Every subcommand below RESOLVES to a module
that already exists and CALLS its `main(argv)`, passing the rest of the command line through
untouched. A door that re-parsed the arguments would be a second spelling of every tool's
contract, and the day one of them grew a flag the door would silently drop it.

⚠️ SO `--help` AFTER A SUBCOMMAND IS THE TOOL'S OWN HELP, not a summary written here. That is
the point: the operator manual is the tool, and a summary here would go stale the first time
one of them changed.

⛔ AND A TOOL WITH NO ENTRY POINT IS NAMED RATHER THAN WRAPPED. `scripts/product_door.py` is a
library of helpers with no `main`, so it is not a subcommand: inventing one would mean writing
a CLI here that exists nowhere else, which is exactly the second spelling this door avoids.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)


#: `<name>: (<module>, <one line an operator can choose from>)`.
#:
#: The module is imported and its `main(argv)` called. Nothing here knows what any tool's
#: arguments are, and nothing here should ever learn.
TOOLS = {
    "backfill": ("ledger.backfill",
                 "소스를 읽어 원장에 싣기 · 범위 재번역(rescope) · 색인"),
    "restamp": ("scripts.ledger_restamp_cursor",
                "선언이 안 바뀐 커서의 지문 문자열만 옮기기 (위치는 그대로)"),
    "census": ("ledger.census_cli",
               "소스마다 표 행 수 · 색인된 행 수 · 남은 수를 재서 저장"),
}


def _usage(out=None) -> None:
    # ⛔ RESOLVED HERE, NOT IN THE SIGNATURE. A default of `sys.stdout` binds the stream
    # this module was IMPORTED with, so anything that replaces it later - a test harness, a
    # supervisor capturing output - would be written past.
    out = sys.stdout if out is None else out
    print("python -m ledger <도구> [옵션]\n", file=out)
    width = max(len(name) for name in TOOLS)
    for name in sorted(TOOLS):
        print(f"  {name:<{width}}  {TOOLS[name][1]}", file=out)
    print("\n각 도구의 설명서는 그 도구가 답합니다: "
          "python -m ledger <도구> --help", file=out)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        _usage()
        return 0
    name, rest = argv[0], argv[1:]
    if name not in TOOLS:
        # ⛔ NAMED, NOT GUESSED. A door that picked the closest match would run a different
        # tool than the operator typed, and two of these write.
        print(f"'{name}' 은 이 문의 도구가 아닙니다.\n", file=sys.stderr)
        _usage(sys.stderr)
        return 2
    module = importlib.import_module(TOOLS[name][0])
    return module.main(rest) or 0


if __name__ == "__main__":
    raise SystemExit(main())
