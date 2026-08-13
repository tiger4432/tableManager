"""The canonical ledger - `ledger_events` and the translators that feed it.

Slice 1 of `docs/process/LEDGER_SLICE_1_BRIEF.md`: the table, and one translator for
`lot_event`. Design: `docs/architecture/CANONICAL_LEDGER_DESIGN.md`.

🔴 THE SAFETY PROPERTY OF THIS PACKAGE, STATED WHERE IT CANNOT BE MISSED
------------------------------------------------------------------------
**If the ledger dies, the current system notices nothing.** Nothing in `server/` imports
this package; it imports `database.database` for a guarded engine and `utils.heartbeat`
for a beat, and that is the whole of its coupling. `crud.py`, `apply_batch_updates`,
`cell_sources`, the chain worker, the graph, the reference views, the official map path
and every existing table schema are untouched - the brief's §6 list, and the reason this
lane's file intersection with every other lane is empty.

The ledger is born as a CONSUMER of the existing system (design §10, first principle:
"쓰기 경로는 한 줄도 안 바꾼다"). It reads `lot_event`; it writes only its own two tables.

Reading order for someone new:
    vocabulary.py     what may be said at all (the closed vocabulary, with signatures)
    envelope.py       the shape of one claim (design §3's seven fields)
    gate.py           what is refused at the door, and counted
    schema.py         the physical table, partitioned from day one
    config.py         what the operator declares per source
    lot_event_translator.py   the first source, and the one judgement call in it
    backfill.py       the cursor loop that never cuts a molecule in half
    observability.py  refusal counts and lag, on day one rather than later
"""
