"""Contract board mappers (scratch package, never in the repo). A frame-through mapper: it hands the target the trigger
rows' own columns, the key included - the shape that left shells on the box (owner 10-21 «회수된 게 키이긴 함»)."""
from mapper_sdk import mapper


@mapper()
def board_copy(df, db):
    keep = [c for c in ("k", "m", "v", "__origin_row_id") if c in df.columns]   # the origin mark: what a deleted row fed
    return df[keep].copy()


@mapper()
def board_pick_columns(df, db):
    """The common author's shape (lead 10-21 ①): pick the columns, the origin mark goes with the rest - kept as a
    fixed board that must be RED until the product carries the origin itself."""
    return df[["k", "m", "v"]].copy()


@mapper()
def board_count_map(df, db):
    """The «fetch» column's group_by board (10-22): rows per map into bd_dec (m, n) - right only when it is handed every
    row of each map its rows are in."""
    if df.empty or "m" not in df.columns:
        return df.iloc[0:0]
    out = df.groupby("m").size().reset_index(name="n")
    out["n"] = out["n"].astype(str)
    return out[["m", "n"]]


@mapper()
def board_sql_copy(df, db):
    """The «fetch» column's own-read board: a copy that also reads the trigger table itself with sql() - the read the
    fetch seat does not cover, which must stay and be said once («reads outside the fetch»)."""
    from mapper_sdk import sql
    sql(db, "SELECT count(*) AS n FROM bd_src")
    keep = [c for c in ("k", "m", "v", "__origin_row_id") if c in df.columns]
    return df[keep].copy()
