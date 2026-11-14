"""Rows for the bonding -> core -> process list -> recipe walk at ops-like row counts (owner 11-14 «천만행 테이블에서도
걷기 하나») - written by COPY into the TABLES only. No ledger write: the declared sources read these rows.

Shape (defaults = the lead's 11-14 counts; a map is 20x20, CLAUDE.md):
    wafers          lots x slots                      4,000 x 25 = 100,000
    wafer_process   wafers x steps, 2 recipes a step  100,000 x 100 = 10,000,000 rows, 200 recipes
    core_wafer_map  core wafers x side^2              5,000 x 400 = 2,000,000 rows (core_slot spelled «01»)
    bonding_log     base wafers x side^2              5,000 x 400 = 2,000,000 rows - base die i of base wafer k is
                                                      bonded from die i of core wafer k (core_slot a number: «1»)
The core and base wafers are the first wafers of the lot list, so every core wafer has a process list.

Row identity is the product's: row_id a uuid, business_key_val by `crud.compose_business_key` (the table's
declared parts and separator) - so the chain's self-joins and the walk find these rows as they find any other.

Run from server/ with ASSY_DATA_ROOT on a scenario root and DATABASE_URL on a throwaway database:
    python scripts/seed_walk_ops.py                     # the full shape
    python scripts/seed_walk_ops.py --lots 2 --slots 5 --steps 4 --side 2 --bonded 3
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import os
import sys
import time
import uuid

_SERVER = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

START = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
TABLES = ("wafer_process", "core_wafer_map", "bonding_log")


def wafers(lots: int, slots: int):
    """[(lot, slot «01», wafer id)] in lot order."""
    return [(f"WL{lot:04d}", f"{slot:02d}", f"WL{lot:04d}-{slot:02d}")
            for lot in range(1, lots + 1) for slot in range(1, slots + 1)]


def process_rows(listed, steps: int):
    for index, (lot, slot, wafer) in enumerate(listed):
        for step in range(1, steps + 1):
            at = START + datetime.timedelta(hours=step, minutes=index % 1440)
            yield {"proc_id": f"P-{wafer}-{step:03d}", "wafer_id": wafer, "lot": lot, "slot": slot,
                   "step": f"S{step:03d}", "eqp_id": f"EQ-{step % 20:02d}",
                   "recipe_id": f"RCP-{step:03d}-{(index + step) % 2}", "result": "OK", "eventtime": at}


def core_map_rows(listed, side: int):
    for lot, slot, wafer in listed:
        for x in range(side):
            for y in range(side):
                yield {"core_lot": lot, "core_slot": slot, "core_x": x, "core_y": y, "wafer_id": wafer,
                       "c_bn": "1", "event_time": START.isoformat()}


def bonding_rows(bases, cores, side: int):
    for k, ((_lot, _slot, base), (core_lot, core_slot, _wafer)) in enumerate(zip(bases, cores)):
        at = START + datetime.timedelta(days=10, minutes=k)
        for x in range(side):
            for y in range(side):
                yield {"base_id": base, "bx": x, "by": y, "core_lot": core_lot, "core_slot": int(core_slot),
                       "cx": x, "cy": y, "dt_lot": f"DT{k // 25:04d}", "dt_slot": k % 25 + 1,
                       "dt_x": x, "dt_y": y, "event_time": at}


class _Lines(io.RawIOBase):
    """The rows as CSV text, read by COPY a buffer at a time - ten million rows never sit in memory."""

    def __init__(self, rows, columns):
        self._rows, self._columns, self._left = rows, columns, b""

    def readable(self):
        return True

    def readinto(self, buffer):
        while len(self._left) < len(buffer):
            chunk = io.StringIO()
            writer = csv.writer(chunk, lineterminator="\n")
            for _ in range(2000):
                row = next(self._rows, None)
                if row is None:
                    break
                writer.writerow(["" if row[c] is None else row[c] for c in self._columns])
            text = chunk.getvalue().encode("utf-8")
            if not text:
                break
            self._left += text
        size = min(len(buffer), len(self._left))
        buffer[:size], self._left = self._left[:size], self._left[size:]
        return size


def keyed(table: str, rows):
    """Each row with the product's identity cells: row_id, business_key_val, the table's own key column."""
    from database import crud

    config = crud.TABLE_CONFIG[table]
    parts = config.get("composite_key_source") or ()
    own = config.get("business_key")
    now = datetime.datetime.now(datetime.timezone.utc)
    for row in rows:
        key = crud.compose_business_key(table, [row[c] for c in parts], parts) if parts else row[own]
        if own and own not in row:
            row[own] = key
        row.update(row_id=str(uuid.uuid4()), business_key_val=key, created_at=now, updated_at=now)
        yield row


def copy(engine, table: str, rows, log=print) -> int:
    """COPY the rows into the table; -> rows the table holds after."""
    first = next(rows)
    columns = list(first)

    def again():
        yield first
        yield from rows

    started = time.perf_counter()
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.copy_expert(f'COPY "{table}" ({", ".join(chr(34) + c + chr(34) for c in columns)}) '
                               "FROM STDIN WITH (FORMAT csv)", io.BufferedReader(_Lines(again(), columns)))
            cursor.execute(f'ANALYZE "{table}"')
            cursor.execute(f'SELECT count(*) FROM "{table}"')
            held = cursor.fetchone()[0]
        raw.commit()
    finally:
        raw.close()
    log(f"[seed_walk_ops] {table}: {held} rows in {time.perf_counter() - started:.1f} s")
    return held


def seed(engine, *, lots=4000, slots=25, steps=100, side=20, bonded=5000, log=print) -> dict:
    listed = wafers(lots, slots)
    if 2 * bonded > len(listed):
        raise ValueError(f"{bonded} core and {bonded} base wafers need {2 * bonded} wafers - there are {len(listed)}")
    cores, bases = listed[:bonded], listed[bonded:2 * bonded]
    return {"wafer_process": copy(engine, "wafer_process", keyed("wafer_process", process_rows(listed, steps)), log),
            "core_wafer_map": copy(engine, "core_wafer_map", keyed("core_wafer_map", core_map_rows(cores, side)), log),
            "bonding_log": copy(engine, "bonding_log", keyed("bonding_log", bonding_rows(bases, cores, side)), log)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lots", type=int, default=4000)
    ap.add_argument("--slots", type=int, default=25)
    ap.add_argument("--steps", type=int, default=100)
    ap.add_argument("--side", type=int, default=20, help="a map is side x side dies")
    ap.add_argument("--bonded", type=int, default=5000, help="core wafers, and as many bonded base wafers")
    args = ap.parse_args(argv)
    import paths
    if not paths.IS_ISOLATED:
        print("[seed_walk_ops] refused: ASSY_DATA_ROOT is not set - this writes millions of rows; point it at a "
              "scenario root and DATABASE_URL at a throwaway database", file=sys.stderr)
        return 2
    from database.database import engine
    print(f"[seed_walk_ops] {paths.describe_isolation() if hasattr(paths, 'describe_isolation') else paths.DATA_ROOT}")
    seed(engine, lots=args.lots, slots=args.slots, steps=args.steps, side=args.side, bonded=args.bonded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
