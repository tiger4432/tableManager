# -*- coding: utf-8 -*-
"""S-190. One spelling of 「a declared cell as it goes over the wire」.

🔴 MEASURED ON THE OWNER'S GRID: `ledger_events` rendered `subject_keys` and
`object_payload` as 「[object Object]」. Those columns are physically JSONB, psycopg2 hands
them back as a `dict`, the route passed the dict through untouched, and the grid — which
takes every cell as text — called `String(...)` on an object.

⚠️ THE DECLARATION ALREADY SAID WHAT THEY ARE. The catalogue declares both columns
`string`, and the catalogue's whole type vocabulary is number/datetime/string — so a `dict`
or a `list` can only ever arrive on a column declared `string`. That is why this takes the
VALUE alone and needs no type argument: the shape of the value already decides, and a
second parameter would be a second chance to disagree with the declaration.

🔴 AND THE SPELLING IS FIXED, BECAUSE TWO READERS COMPARE THESE STRINGS. `sort_keys` so the
same object is the same text on every request (a dict's insertion order is not the
declaration's), `ensure_ascii=False` so Korean keys stay readable rather than becoming
`a numeric escape`, and the tight separators so the grid and the TSV export of one value are the
SAME bytes. `str(value)` — which is what the rows TSV did — is Python's repr: single
quotes, `True`, `None`. That is not JSON, and nothing downstream can parse it.
"""
import json


def wire_text(value):
    """`value` as the wire carries it: a JSON object/array becomes JSON TEXT, else as-is.

    ⚠️ EVERY OTHER TYPE PASSES THROUGH UNTOUCHED, on purpose. Numbers must stay numbers for
    the grid to sort them, `None` must stay absent rather than become `"null"`, and a string
    must come out byte-identical — this function may not be the reason a cell changes.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    return value
