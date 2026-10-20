# -*- coding: utf-8 -*-
"""`table_cells.TABLE_CELLS` - the table form's skeleton - is exactly the keys the product reads off a table's entry
(총괄 f3639d4a2). Both ways: a cell the product reads and the list lacks is a field no form can fill; a cell the list
offers and nothing reads is a box whose value does nothing. Counted by `tests/support/table_config_reads.py` (AST);
⚠️ a key spelled at run time (an f-string, a joined name) is not counted - see its docstring.
"""
import io
import json
import os
import sys

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

import table_cells                                                    # noqa: E402
from tests.support import table_config_reads                          # noqa: E402

#: Read by the product and stated by the census's first run (10-20) - a count that misses one of these counts nothing.
CANARIES = ("column_types", "business_key", "display_columns", "composite_key_source", "indexes", "search_columns",
            "allow_replace_map")


def test_the_list_is_the_keys_the_product_reads():
    read = table_config_reads.keys_read(SERVER)
    assert set(CANARIES) <= set(read), sorted(set(CANARIES) - set(read))
    listed = [cell for cell, _node in table_cells.TABLE_CELLS]
    assert len(listed) == len(set(listed)), listed
    assert sorted(set(read) - set(listed)) == [], "read and not in TABLE_CELLS (where: %s)" % {
        key: sorted(read[key])[:2] for key in sorted(set(read) - set(listed))}
    assert sorted(set(listed) - set(read)) == [], "in TABLE_CELLS and read by nothing"


def test_the_shipped_sample_writes_only_cells_the_list_has():
    sample = json.load(io.open(os.path.join(SERVER, "config", "sample", "table_config.json.sample"), encoding="utf-8"))
    written = {key for entry in sample.values() if isinstance(entry, dict) for key in entry if not key.startswith("__")}
    assert written and written <= {cell for cell, _node in table_cells.TABLE_CELLS}, sorted(written)
