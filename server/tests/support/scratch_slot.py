"""A chain slot process on a test's scratch schema - the real `chain.slots` body, its database
pointed at the isolated test database before anything opens a connection.

    python -m tests.support.scratch_slot <index>

Environment: ASSY_DATA_ROOT (the test's own config, rules and heartbeats), PYTHONPATH (its
mappers), ASSY_PG_TEST_DATABASE_URL (the isolated database) and ASSY_SLOT_TEST_SCHEMA (the
scratch schema the test's tables live in).
"""
import os
import sys

from sqlalchemy import create_engine

import database.database as database
from tests.support.isolated_pg import PG_TEST_URL_ENV, scratch_connect_args

# the pool a real slot gets (`chain.slots.SLOT_POOL`, in this process's environment)
database.engine = create_engine(os.environ[PG_TEST_URL_ENV],
                                pool_size=int(os.environ.get("ASSY_DB_POOL_SIZE") or 20),
                                max_overflow=int(os.environ.get("ASSY_DB_MAX_OVERFLOW") or 10),
                                connect_args=scratch_connect_args(os.environ["ASSY_SLOT_TEST_SCHEMA"]))
database.SessionLocal.configure(bind=database.engine)

from chain import slots  # noqa: E402

if __name__ == "__main__":
    slots.main(sys.argv[1:])
