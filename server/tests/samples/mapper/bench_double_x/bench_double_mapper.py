# -*- coding: utf-8 -*-
"""A mapper that ships beside its own sample (판정 13:30), like the parser sample.

🔴 IT IS THE FIRST THING TO ACTUALLY TRAVERSE THE ONE-CELL PATH. `@mapper` registers it
(S-188 ⓒ), `rule.json` names it with the single `mapper` cell (S-188 ⓓ), and
`dev_bench.try_mapper` resolves it through the registry -- so this folder exercises the
mechanism rather than describing it.

⚠️ IT TOUCHES NO DATABASE, on purpose. A sample that queried would skip wherever there is no
PostgreSQL, and a gate that skips reports nothing.
"""
from mapper_sdk import mapper


@mapper(target_table="bench_target", params=("x_col",))
def bench_double_x(df, db):
    """Doubles the declared column. `db` is unused and that is the point."""
    out = df[["row_id", "wafer"]].copy()
    out["x_doubled"] = df["x"].astype(int) * 2
    return out
