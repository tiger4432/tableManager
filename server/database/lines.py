"""The cell-source overhaul's table shape - ONE author (docs/design/CELL_SOURCE_OVERHAUL.md).

Every declared table t is two plain tables: `t__now` (one current line per entity, merged at write time) and
`t__lines` (one line per write - the history). The name t is a view over `t__now` that refuses writes. Names, the
column -> bit map and every DDL on the three go through here; nothing else spells «__now» or «__lines».
"""

MAX_NAME_BYTES = 63                                  # PostgreSQL's identifier limit
NOW_SUFFIX, LINES_SUFFIX = "__now", "__lines"


def _checked(name: str) -> str:
    if len(name.encode("utf-8")) > MAX_NAME_BYTES:
        raise ValueError(f"relation name {name!r} is longer than {MAX_NAME_BYTES} bytes")
    return name


def now_relation(table_name: str) -> str:
    """The physical table holding t's current lines - what a catalogue, plan or index question names."""
    return _checked(table_name + NOW_SUFFIX)


def lines_relation(table_name: str) -> str:
    """The physical table holding t's lines."""
    return _checked(table_name + LINES_SUFFIX)
