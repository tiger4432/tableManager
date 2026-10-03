"""A frame as the cursor read hands it over (총괄 2a8d9073c): every column `base_select_columns`
names - every column of the relation - and NULL where a fixture row carries none. A hand-built
frame without them is one the read never produces, and the frame check refuses it."""
from ledger.backfill import _v2_frame
from ledger.event_frame import base_select_columns


def as_read(plan, rows):
    columns = base_select_columns(plan)
    return _v2_frame([{column: row.get(column) for column in columns} for row in rows])
