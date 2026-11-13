"""One seat enumerates the catalogue's tables - lines.base_tables (lead 11-12): a line table carries t's columns, so a
seat that listed tables by catalogue or by a column took t__lines for a main table (the business key picker built a
UNIQUE on it). A product function enumerates when it calls .get_table_names( or holds a catalogue query naming
information_schema.tables/columns, pg_tables or pg_stat_user_tables with no filter to named tables. TO_MOVE only
shrinks: a seat in it that no longer enumerates is red too, so a moved seat leaves it in the same commit."""
import ast
import pathlib
import re
import subprocess

SERVER = pathlib.Path(__file__).resolve().parents[1]
SOURCE = re.compile(r"information_schema\.(tables|columns)|\bpg_tables\b|\bpg_stat_user_tables\b", re.I)
NAMED = re.compile(r"\b(table_name|relname|tablename)\s*(=\s*(ANY\s*\(|:|%s|%\(\w+\)s|')|IN\s*[:(])", re.I)
THE_SEAT = "database/lines.py:base_tables"
#: enumerators not moved yet - the next round's list (target 0), each with why it is not wrong today
TO_MOVE = {
    "chain/ingestion_worker.py:_analyze_stale_tables_sync": "boot ANALYZE - should take line tables too",
    "chain/ingestion_worker.py:<module>": "layer table health report - line tables wanted",
    "scripts/diagnose_db_health.py:<module>": "bloat report - line tables wanted",
    "scripts/diagnose_slow_after_ingest.py:section_autovacuum": "autovacuum report - line tables wanted",
    "scripts/diagnose_slow_after_ingest.py:section_sizes": "seq scan report - line tables wanted",
    "scripts/ledger_deploy_preflight.py:inspect_database": "a table count, read only",
}


def _seats():
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=SERVER, capture_output=True, text=True,
                           check=True).stdout.split()
    found = set()
    for f in files:
        if f.startswith("tests/") or "/tests/" in f:
            continue
        tree = ast.parse((SERVER / f).read_text(encoding="utf-8"), f)
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        inner = {id(m) for n in funcs for m in ast.walk(n)
                 if m is not n and isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
        scopes = [(n.name, list(ast.walk(n))) for n in funcs if id(n) not in inner]
        scopes.append(("<module>", [m for s in tree.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                                                ast.ClassDef)) for m in ast.walk(s)]))
        for name, nodes in scopes:
            queries = [m.value for m in nodes if isinstance(m, ast.Constant) and isinstance(m.value, str)
                       and SOURCE.search(m.value) and re.search(r"\bSELECT\b", m.value, re.I)]
            if any(isinstance(m, ast.Attribute) and m.attr == "get_table_names" for m in nodes) or \
                    any(not NAMED.search(q) for q in queries):
                found.add("%s:%s" % (f, name))
    return found


def test_only_base_tables_enumerates_the_catalogue():
    found = _seats()
    assert THE_SEAT in found, "canary: the census must see base_tables itself"
    assert "migrations/add_business_key_unique_index.py:tables_with_business_key" not in found, \
        "canary: the business key picker asks named tables now"
    assert found - {THE_SEAT} - set(TO_MOVE) == set(), "a new seat enumerates the catalogue - call lines.base_tables"
    assert set(TO_MOVE) - found == set(), "moved or gone - take it out of TO_MOVE"
