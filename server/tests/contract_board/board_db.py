"""C's throwaway board database (lead 10-21: the full board off assy_test, in a DB of its own whose name says c_board).
usage: board_db.py create | drop | public-count <out.json> | public-diff <before.json>
The password is read from database.json and never printed. Every connection is closed explicitly (a `with` block of
psycopg2 does not close it - and DROP DATABASE then fails)."""
import json
import os
import sys

import psycopg2
from sqlalchemy.engine import make_url

NAME = os.environ.get("BOARD_DB_NAME", "assy_c_board_1022")
cfg = json.load(open(r"C:/Users/kk980/Developments/assyManager/server/config/database.json", encoding="utf-8"))
URL = make_url(cfg["url"])


def connect(database):
    c = psycopg2.connect(host=URL.host, port=URL.port, user=URL.username, password=URL.password, dbname=database)
    c.autocommit = True
    return c


def counts(database):
    c = connect(database)
    try:
        cur = c.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
        out = {}
        for (t,) in cur.fetchall():
            cur.execute('SELECT count(*) FROM public."%s"' % t)
            out[t] = cur.fetchone()[0]
        return out
    finally:
        c.close()


cmd = sys.argv[1]
if cmd == "create":
    c = connect("postgres")
    try:
        c.cursor().execute('CREATE DATABASE "%s"' % NAME)
    finally:
        c.close()
    print("created", NAME)
elif cmd == "drop":
    c = connect("postgres")
    try:
        cur = c.cursor()
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (NAME,))
        print("connections still on it", cur.fetchone()[0])
        cur.execute('DROP DATABASE IF EXISTS "%s"' % NAME)
    finally:
        c.close()
    print("dropped", NAME)
elif cmd == "public-count":
    got = counts("assy_test")
    json.dump(got, open(sys.argv[2], "w"))
    print("assy_test public tables", len(got), "rows", sum(got.values()))
elif cmd == "public-diff":
    before, after = json.load(open(sys.argv[2])), counts("assy_test")
    moved = {t: (before.get(t), after.get(t)) for t in set(before) | set(after) if before.get(t) != after.get(t)}
    print("assy_test public tables", len(after), "rows", sum(after.values()), "changed", moved or "none")
