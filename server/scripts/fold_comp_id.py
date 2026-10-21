"""Fold one table's comp_id into its declared spelling in one transaction - `fold_comp_id.bat <table>`.

Runs `scripts/sql/notation_fold_comp_id.sql` (history, layers, shown value) on the server's own
database: the three checks first, then how many rows will move, one «y», then the fold. Refuses
while a retroactive run holds the queue (stop it with stop_retroactive.bat) or a check is not 0.
"""
import os
import re
import sys
import time

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

SQL_FILE = os.path.join(SERVER_DIR, "scripts", "sql", "notation_fold_comp_id.sql")


def statements(table):
    """The file's statements for `table`, comments dropped, BEGIN/COMMIT left to the caller."""
    text = open(SQL_FILE, encoding="ascii").read().replace("<T>", table)
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip() and s.strip().upper() not in ("BEGIN", "COMMIT")]


def fold(conn, table, ask=input, say=print) -> int:
    """`conn` is a SQLAlchemy connection with no transaction open."""
    from sqlalchemy import text

    if not re.fullmatch(r"[A-Za-z0-9_]+", table or ""):
        say("Not a table name: %r" % table)
        return 2
    say("Connected. Checking the retroactive queue ...")
    # the gate every retroactive run passes - not a copy of it (총괄 1ff4dcc6c ②)
    from sqlalchemy.orm import Session
    from admin import retroactive

    with Session(bind=conn) as session:
        busy = retroactive.gate_refusal(session)
    if busy:
        say("A retroactive run holds the queue: %s - stop it first with stop_retroactive.bat" % busy)
        return 1
    checks, moves, writes = [], None, []
    for stmt in statements(table):
        if stmt.upper().startswith("SELECT"):
            name = re.search(r"\bAS\s+(\w+)", stmt).group(1)
            say("Counting %s ..." % name)
            begun = time.monotonic()
            value = conn.execute(text(stmt)).scalar()
            say("  = %s  (%.0f s)" % (value, time.monotonic() - begun))
            if name == "rows_to_fold":
                moves = value
            else:
                checks.append((name, value))
        else:
            writes.append(stmt)
    conn.rollback()
    for name, value in checks:
        say("%-40s %s" % (name, value))
    if any(value for _name, value in checks):
        say("A check is not 0 - nothing folded. Send these numbers to the lead.")
        return 1
    say("%s rows of %s will have comp_id folded." % (moves, table))
    if not moves:
        return 0
    if ask("Fold them now? [y/N] ").strip().lower() != "y":
        say("Nothing folded.")
        return 1
    started = time.monotonic()
    steps = ("history lines", "cell layers", "shown values")
    with conn.begin():
        for number, stmt in enumerate(writes):
            say("Writing %d/%d %s ..." % (number + 1, len(writes), steps[number] if number < len(steps) else ""))
            conn.execute(text(stmt))
            say("  done - %.0f s so far" % (time.monotonic() - started))
        say("Committing ...")
    say("Done: %s rows folded in %.0f s." % (moves, time.monotonic() - started))
    return 0


def main(argv) -> int:
    print("Connecting to the server's database ...", flush=True)
    from database.database import engine

    print("Ready.", flush=True)
    table = next((a for a in argv if not a.startswith("--")), None) or input("Table name: ").strip()
    print("Opening a connection for %s ..." % table, flush=True)
    with engine.connect() as conn:
        return fold(conn, table, ask=(lambda _q: "y") if "--yes" in argv else input,
                    say=lambda line: print(line, flush=True))


if __name__ == "__main__":
    os.chdir(SERVER_DIR)
    sys.exit(main(sys.argv[1:]))
