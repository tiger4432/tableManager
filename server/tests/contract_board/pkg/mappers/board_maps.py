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
