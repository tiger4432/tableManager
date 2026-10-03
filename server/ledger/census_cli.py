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


#: How a person runs this - the parser's own `prog`, and what a census record names as its next
#: step when it was never counted by a person (`backfill.next_step`).
PROG = "python -m ledger census"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source", default=None,
        help="이 소스 하나만. 없으면 선언된 소스 전부")
    parser.add_argument(
        "--world", default=None,
        help="이 세상에서. 없으면 소스마다 그 소스를 말하는 세상(운영 세상의 사슬에서) — "
             "그 세상이 말하지 않는 소스는 이름 대어 거절")
    parser.add_argument(
        "--json", action="store_true",
        help="사람 대신 기계가 읽을 모양으로")
    args = parser.parse_args(argv)

    from database.database import engine
    from ledger import backfill, schema
    from ledger.setup import LedgerSetupError, load_setup
    from ledger.store import LedgerStore

    setup = load_setup()
    if args.source is not None and args.source not in setup.snapshot.source_plans:
        # A typo answered with "0 rows" reads as "nothing to measure here", which is the
        # silent-zero shape every refusal in this family exists to stop.
        print(f"{args.source}: 선언에 없는 소스입니다. 선언된 것: "
              f"{', '.join(sorted(setup.snapshot.source_plans))}", file=sys.stderr)
        return 2
    if args.source is not None and not setup.snapshot.source_plans[args.source].runs:
        # 은퇴했거나 «로더가 거절한» 소스는 「0 행」이 아니라 「세지 않는다」이다 (S-177 ①②).
        # 0 으로 답하면 표가 비었다는 뜻이 되고, 그건 다른 문장이다.
        plan = setup.snapshot.source_plans[args.source]
        why = ("로더가 거절한 소스입니다: %s" % (dict(plan.refusal or {}).get("message"),)
               if not plan.planned else "은퇴한 소스입니다 (내용 미검증).")
        print(f"{args.source}: {why} 세지 않습니다.", file=sys.stderr)
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

        def write_row_census(self, source, census, **kwargs):
            measured[source] = census
            return self._inner.write_row_census(source, census, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    # Each source in the world that speaks for it, as the paced job measures it (총괄 8b81e79a0).
    measured = {}
    if args.source is None:
        backfill.measure_every_source(
            engine, setup, store=lambda world: _Recording(LedgerStore(engine, world=world)),
            world=args.world)
    else:
        try:
            world = schema.speaking_world(engine, args.source, args.world)
        except LedgerSetupError as refused:
            print(f"{args.source}: {refused}", file=sys.stderr)
            return 2
        backfill.measure_and_store(
            engine, load_setup(schema.world_names(world).declaration_root), args.source,
            _Recording(LedgerStore(engine, world=world)))

    if args.json:
        print(json.dumps(measured, ensure_ascii=False, indent=1, default=str))
        return 0
    for source in sorted(measured):
        census = measured[source] or {}
        if census.get("refused"):
            print(f"{source} ({census.get('world')}): 셀 수 없음 -- {census['refused']}")
            continue
        rows = (census.get("relation_rows") or {}).get("estimate")
        indexed = (census.get("indexed_rows") or {}).get("estimate")
        not_yet = (census.get("not_yet") or {}).get("estimate")
        # 「셀 수 없다」와 「한 것이 없다」는 다른 문장이므로 빈 칸은 빈 칸으로 둔다.
        tail = "" if not_yet is None else f" · 남은 {not_yet}"
        if census.get("rows_drifted") is not None:
            tail += (f" · 수정 누락 {census['rows_drifted']['estimate']}"
                     f" · 지문 없음 {census['rows_unprinted']['estimate']}")
        print(f"{source} ({census.get('world')}): 표 {rows} · 색인 {indexed}{tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
