"""A chain slot process on a test's scratch schema - the real `chain.slots` body, its database
pointed at the isolated test database before anything opens a connection.

    python -m tests.support.scratch_slot <index>

Environment: ASSY_DATA_ROOT (the test's own config, rules and heartbeats), PYTHONPATH (its
mappers), ASSY_PG_TEST_DATABASE_URL (the isolated database), ASSY_SLOT_TEST_SCHEMA (the
scratch schema the test's tables live in) and ASSY_SLOT_TEST_RUN (this test run's key).
"""
import os
import sys

#: This test run's key - in the slot's process name, so its connections' name.
RUN_ENV = "ASSY_SLOT_TEST_RUN"


def process_name(index, run):
    """A test slot's process name: the product's (`chain.slots.process_name`) and the run's key.
    Two runs share the one test database, and a dispatcher ends a dead slot's connections BY
    NAME (`chain.slots.end_connections`) - with one name, one run ended the other's slots."""
    return "ChainSlot%s_%s" % (index, run)


def main(argv):
    from sqlalchemy import create_engine

    import database.database as database
    from tests.support.isolated_pg import PG_TEST_URL_ENV, scratch_connect_args

    # the pool a real slot gets (`chain.slots.SLOT_POOL`, in this process's environment)
    database.engine = create_engine(os.environ[PG_TEST_URL_ENV],
                                    pool_size=int(os.environ.get("ASSY_DB_POOL_SIZE") or 20),
                                    max_overflow=int(os.environ.get("ASSY_DB_MAX_OVERFLOW") or 10),
                                    connect_args=scratch_connect_args(os.environ["ASSY_SLOT_TEST_SCHEMA"]))
    database.SessionLocal.configure(bind=database.engine)

    from chain import slots

    run = os.environ[RUN_ENV]
    slots.process_name = lambda index: process_name(index, run)
    slots.main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
