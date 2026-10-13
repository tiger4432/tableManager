"""총괄 10-14 ㄴ: an edit's event carries the old value of every column it changed - also on a row a commit expired and
the writer set without reading (`database._old` used to leave that value out: the old key and the row gates read it as
unknown). Every dynamic table column is mapped with active_history (`models._mapped`), on the first mapping and on a
column added to a live table."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest                                                         # noqa: E402

import event_constants                                                # noqa: E402
from database import models                                           # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

T = "ahist_rows"


@pytest.mark.parametrize("column", ["v", "added"], ids=["first mapping", "column added later"])
def test_an_expired_row_written_without_a_read_says_what_it_was(db_session, column):
    from database.database import Base
    from database.models import DatabaseOutbox

    models.init_dynamic_models({T: {"business_key": "k", "column_types": {"k": "string", "v": "string"}}})
    models.init_dynamic_models({T: {"business_key": "k", "column_types": {"k": "string", "v": "string",
                                                                          "added": "string"}}})
    Base.metadata.create_all(bind=db_session.get_bind())
    model = models.DYNAMIC_TABLES[T]
    db_session.add(model(row_id="r1", business_key_val="a", k="a", **{column: "before"}))
    db_session.commit()
    row = db_session.get(model, "r1")
    db_session.commit()                       # the row is expired - nothing below reads it
    setattr(row, column, "after")
    db_session.commit()

    edits = [get_payload_dict(e) for e in db_session.query(DatabaseOutbox).filter_by(table_name=T, event_type="EDIT")]
    assert [event_constants.old_values_of(p) for p in edits] == [{column: "before"}]
