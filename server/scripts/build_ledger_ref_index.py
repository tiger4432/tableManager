"""Build the ledger's ref index without blocking a write - what a withdrawal aims with.

    conda run -n assy_manager python server/scripts/build_ledger_ref_index.py              (what it would do)
    conda run -n assy_manager python server/scripts/build_ledger_ref_index.py --apply      (build it)
    ... --world <name>                                                                       (a ledger branch)

`source_who = %s AND source_raw_ref = ANY(%s)` - the statement every withdrawal page issues - read
the whole ledger once a page; with this hash index on `source_raw_ref` it reads the refs it names
(총괄 10-09). The parent gets a metadata-only index, each partition is built CONCURRENTLY and attached;
a partition that already has it is left alone, so a second run builds nothing. One line a partition.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None, connection=None, say=print) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--world", default=None, help="a ledger world (branch); none = the operating one")
    parser.add_argument("--apply", action="store_true", help="build it; without this nothing is written")
    args = parser.parse_args(argv)

    from ledger import schema

    names = schema.require_world(args.world)
    own = connection is None
    if own:
        from database.database import engine
        connection = engine.raw_connection()
    try:
        done = schema.build_partitioned_index(connection, names, schema.REF_INDEX, schema.REF_INDEX_COLUMNS,
                                              apply=args.apply, say=say, child_name=schema.REF_INDEX_CHILD)
    finally:
        if own:
            connection.close()
    say("%s: %d partition(s) built, %d attached as they were, %d already had it%s - the parent index is %s"
        % (names.ledger, done["built"], done["attached"], done["already"],
           ", %d would be built, %d attached as they are (add --apply)" % (done["would_build"], done["would_attach"])
           if done["would_build"] or done["would_attach"] else "",
           "valid" if done["parent_valid"] else "not valid yet"))
    return done


if __name__ == "__main__":
    main()
