# -*- coding: utf-8 -*-
"""운영에서는 `python -m ledger census` 로 소스마다 「표 행 · 색인된 행 · 남은 수」를 잽니다.

🔴 IT MEASURES AND STORES WHAT THE PACED JOB ALREADY MEASURES AND STORES (S-109). The row
census runs on a schedule inside the chain daemon; this is the same call for an operator who
wants the number NOW - after a load, or when the screen looks stale - without waiting for the
next tick and without a second definition of what the census is.

⛔ SO IT COMPUTES NOTHING OF ITS OWN. `backfill.measure_every_source` does the work and writes
the result exactly as the job does. Everything here is argument parsing and printing.

⚠️ IT IS A SCAN, and the census's own docstring says why that makes it a JOB rather than a
request: `count(*)` on a relation that may hold ten million rows. Running it by hand is a
decision to pay that, which is why it is a command an operator types rather than something
this door does on the way past.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ledger census",
        description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source", default=None,
        help="이 소스 하나만. 없으면 선언된 소스 전부")
    parser.add_argument(
        "--json", action="store_true",
        help="사람 대신 기계가 읽을 모양으로")
    args = parser.parse_args(argv)

    from database.database import engine
    from ledger import backfill
    from ledger.setup import load_setup
    from ledger.store import LedgerStore

    setup = load_setup()
    if args.source is not None and args.source not in setup.snapshot.source_plans:
        # A typo answered with "0 rows" reads as "nothing to measure here", which is the
        # silent-zero shape every refusal in this family exists to stop.
        print(f"{args.source}: 선언에 없는 소스입니다. 선언된 것: "
              f"{', '.join(sorted(setup.snapshot.source_plans))}", file=sys.stderr)
        return 2

    class _Recording:
        """The real store, plus a note of what was written.

        🔴 THE NUMBERS COME FROM THE WRITE ITSELF, not from a second measurement.
        `measure_every_source` measures and stores in one pass and returns only the names it
        did; re-reading afterwards would need a reader that does not exist, and re-measuring
        would run every `count(*)` twice and could print numbers that differ from the ones
        just stored. Wrapping the writer keeps ONE measurement and one loop - the job's.
        """

        def __init__(self, inner):
            self._inner = inner
            self.written = {}

        def write_row_census(self, source, census, **kwargs):
            self.written[source] = census
            return self._inner.write_row_census(source, census, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    store = _Recording(LedgerStore(engine))
    if args.source is None:
        backfill.measure_every_source(engine, setup, store=store)
    else:
        backfill.measure_and_store(engine, setup, args.source, store)
    measured = store.written

    if args.json:
        print(json.dumps(measured, ensure_ascii=False, indent=1, default=str))
        return 0
    for source in sorted(measured):
        census = measured[source] or {}
        if census.get("refused"):
            print(f"{source}: 셀 수 없음 -- {census['refused']}")
            continue
        rows = (census.get("relation_rows") or {}).get("estimate")
        indexed = (census.get("indexed_rows") or {}).get("estimate")
        not_yet = (census.get("not_yet") or {}).get("estimate")
        # 「셀 수 없다」와 「한 것이 없다」는 다른 문장이므로 빈 칸은 빈 칸으로 둔다.
        tail = "" if not_yet is None else f" · 남은 {not_yet}"
        print(f"{source}: 표 {rows} · 색인 {indexed}{tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
