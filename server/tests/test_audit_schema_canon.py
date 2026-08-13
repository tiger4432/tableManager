"""The canon detector must be able to SEE a violation before its zeros mean anything.

WHY THIS FILE IS MOSTLY ONE TEST
--------------------------------
`audit_schema_canon.py` carries its own fault injection (`--self-test`): every rule gets a
clean synthetic snapshot and the same snapshot with a violation planted, and the detector
has to be silent on the first and loud on the second. That harness is the real assertion,
so this file's job is to make sure **the harness itself runs on every suite pass** rather
than only when somebody remembers to type the flag - a self-check nobody executes is the
same as no self-check.

The rest of the file pins the three properties that a future edit is most likely to break
quietly, each of which has already cost this project a round somewhere else:

  * READ-ONLY IS STRUCTURAL, NOT A PROMISE. The audit is pointed at development
    databases whose sibling holds 13.9 GB of real-shaped data. `test_no_write_verbs`
    reads the module's own source and refuses any DDL/DML verb, so "read-only" survives
    an edit by someone who never read the docstring.
  * THE COUNTER-CASES ARE PART OF THE ALARM. A detector that flags every candidate passes
    a one-sided fault injection perfectly and is worthless. `--self-test` asserts both
    directions and this file asserts that it did.
  * EMPTY BUCKETS STILL GET PRINTED. The whole method rests on reporting the buckets you
    expected to be empty; a "tidy-up" that hides them turns the report back into a filter
    written from a hypothesis.

    PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest \
        server/tests/test_audit_schema_canon.py -q
"""
import io
import os
import re
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import audit_schema_canon as canon  # noqa: E402


def test_every_detector_fires_on_a_planted_violation():
    """The deliverable's own fault injection, run as part of the suite.

    `self_test` returns the list of detectors that stayed blind. Empty means every rule
    was shown to distinguish a violation from silence - which is the only condition under
    which the zeros in a live report mean anything at all.
    """
    blind = canon.self_test(verbose=False)
    assert blind == [], (
        f"these detectors did NOT react to a violation planted in front of them: {blind}. "
        f"Until they do, any zero they report is unproven.")


def test_self_test_covers_every_rule_the_canon_states():
    """R1..R8 and the mismatch section must each be exercised by the injection harness.

    Guards against the quiet failure mode of adding a rule and forgetting its fault case,
    which leaves a detector that has never been rung shipping green forever.
    """
    src = io.open(canon.__file__, encoding="utf-8").read()
    body = src[src.index("def self_test("):]
    for rule in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "MISMATCH"):
        assert re.search(r'\("%s[-"]' % rule, body), (
            f"{rule} has a detector but no fault injection case in self_test()")


def test_the_harness_asserts_silence_as_well_as_noise():
    """Both halves, or the alarm proves nothing.

    A detector that reported every candidate as a violation would sail through an
    injection test that only checks the faulted input. The counter-cases are what
    distinguish a real predicate from a rubber stamp, so their presence is pinned here
    rather than left to be trimmed by a later cleanup.
    """
    src = io.open(canon.__file__, encoding="utf-8").read()
    for name in ("R1-counter", "R6-counter", "R5-counter", "R7-counter",
                 "MISMATCH-cnt"):
        assert name in src, f"the counter-case `{name}` is gone; the alarm is now one-sided"


# Every verb that changes something.
_WRITE_VERBS = re.compile(
    r"\b(insert\s+into|update\s+\w+\s+set|delete\s+from|truncate|"
    r"create\s+(unique\s+)?(index|table|schema)|drop\s+(index|table|column)|"
    r"alter\s+table|grant|revoke|vacuum|reindex)\b", re.I)


def _executed_strings(src):
    """Every string literal this module could hand to the database.

    🔴 Grepping the WHOLE file for write verbs is the wrong check and it fails honestly:
    the module's docstrings have to quote `CREATE TABLE` in order to explain the measured
    read-only failure they exist to warn about, and a test that forbids describing a
    hazard pressures the next author to delete the description rather than the hazard.
    What actually matters is narrower and exact - a write can only reach PostgreSQL
    through a string that gets executed - so only those strings are examined.
    """
    import ast
    out = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        name = (getattr(node.func, "attr", None)
                or getattr(node.func, "id", None) or "")
        if name not in ("text", "execute", "exec_driver_sql"):
            continue
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append(sub.value)
    return out


def test_no_executed_string_can_write():
    """READ-ONLY, checked against what is executed rather than believed.

    The audit gets pointed at whatever `--url` says. The canon explicitly wants production
    auditable, so somebody will eventually aim it there, and at that moment the only thing
    between a report and an incident is that nothing this file executes writes.
    """
    src = io.open(canon.__file__, encoding="utf-8").read()
    executed = _executed_strings(src)
    assert executed, "the extractor found no executed strings - it has stopped working"
    hits = [(s[:70], m.group(0)) for s in executed
            for m in [_WRITE_VERBS.search(s)] if m]
    assert not hits, f"a write statement is executed by a read-only audit: {hits}"


def test_the_write_verb_extractor_would_catch_a_write():
    """Fault-inject the safety test itself. An unexercised guard is not a guard."""
    planted = 'from sqlalchemy import text\nx = conn.execute(text("DROP TABLE t"))\n'
    found = _executed_strings(planted)
    assert found and any(_WRITE_VERBS.search(s) for s in found), (
        "the extractor cannot see a DROP handed straight to execute()")


def test_there_is_no_apply_mode():
    """No `--apply` switch and nothing that reads one.

    The prose is allowed to SAY there is no apply mode - that sentence is the promise
    being kept. What must not exist is an argument declaration or a code path that acts
    on one, so the check is for the wiring rather than for the string.
    """
    src = io.open(canon.__file__, encoding="utf-8").read()
    assert 'add_argument("--apply"' not in src
    assert "args.apply" not in src
    assert 'add_argument("--url"' in src, "the target must stay explicit and maskable"


def test_every_connection_goes_through_the_verified_readonly_helper():
    """No raw `engine.connect()` anywhere - and the helper checks that it worked.

    🔴 Measured on both development databases on this box: the obvious spelling,
    `SET SESSION default_transaction_read_only = on`, leaves the session WRITABLE.
    `default_transaction_read_only` reads `on` while `transaction_read_only` reads `off`
    and `CREATE TABLE` succeeds, because the SET itself opens the implicit transaction and
    that transaction keeps the old default. A guard that reports itself as armed and is
    not is worse than no guard, so the pin is `postgresql_readonly=True` and the helper
    READS BACK `transaction_read_only` before returning the connection.
    """
    src = io.open(canon.__file__, encoding="utf-8").read()
    body = src[src.index("def readonly_connection("):]
    body = body[:body.index("\ndef ", 10)]
    assert "postgresql_readonly=True" in body
    assert "SHOW transaction_read_only" in body, (
        "the helper trusts the pin instead of reading it back")
    assert "raise RuntimeError" in body, "an unarmed session must refuse, not warn"

    for fn in ("def load_physical(", "def probe_numeric_fill("):
        fbody = src[src.index(fn):]
        fbody = fbody[:fbody.index("\ndef ", 10)]
        assert "readonly_connection(engine)" in fbody, f"{fn} opens its own connection"
        assert "finally:" in fbody and "invalidate()" in fbody, (
            f"{fn} does not discard its connection in a finally block")

    # `engine.connect()` may appear only inside the helper and in the reachability ping.
    assert src.count("engine.connect()") <= 2, (
        "a connection is being opened outside `readonly_connection`")


def test_empty_buckets_are_still_reported():
    """A bucket with no members must still appear, with its count and its reason.

    This is the method, not a formatting preference: the recurring failure this audit was
    built against is a filter written from a hypothesis, and a bucket that is only printed
    when it is non-empty is exactly that filter wearing a report's clothes.
    """
    res = canon.rule_r3(canon._clean_decl())
    empty = [b for b in res.buckets if len(b) == 0]
    assert empty, "the clean fixture should leave at least one bucket empty"
    printed = []
    for b in sorted(res.buckets, key=lambda x: x.key):
        printed.append((b.key, b.verdict, len(b), bool(b.why)))
    for key, verdict, count, has_why in printed:
        assert verdict in (canon.VIOLATION, canon.LEGITIMATE, canon.INFO,
                           canon.UNCLASSIFIED)
        assert has_why, f"bucket {key} carries no explanation of what it means"


def test_every_bucket_a_rule_declares_can_actually_be_reached():
    """A bucket no input can populate is worse than no bucket - it reads as a proven zero.

    Caught for real during construction: R1 shipped an `unclassified` bucket that every
    code path routed around, so it printed `0` forever and looked like evidence. The
    injection harness populates the interesting ones; this test pins the weaker property
    that no bucket key is declared twice or left unwired in the returned list.
    """
    results = [canon.rule_r1(canon._clean_decl(), canon._clean_phys(), {}),
               canon.rule_r2(canon._clean_decl(), canon._clean_phys()),
               canon.rule_r3(canon._clean_decl()),
               canon.rule_r4({}, canon._clean_decl()),
               canon.rule_r5(canon._clean_decl(), canon._clean_phys()),
               canon.rule_r6(canon._clean_decl(), canon._clean_phys()),
               canon.rule_r8(canon._clean_decl(), canon._clean_phys()),
               canon.rule_mismatch(canon._clean_decl(), canon._clean_phys())]
    for res in results:
        keys = [b.key for b in res.buckets]
        assert len(keys) == len(set(keys)), f"{res.rule} declares a bucket key twice: {keys}"
        assert res.uncovered, (
            f"{res.rule} claims full coverage. Every rule here is partial in some "
            f"direction and saying so is the point.")


def test_r1_does_not_decide_identity_from_the_column_name():
    """The predicate must come from declarations, never from spelling.

    R1's incident is a column that LOOKS like an id and was typed like a number; the
    inverse mistake - calling something an identifier because it is spelled like one -
    would flag every coordinate in the schema. So identity comes only from config
    evidence, and a column nothing declares stays out of the population entirely.
    """
    decl = canon.Declarations(
        tables={"dt_probe": {"column_types": {"lot_id": "number", "slot": "number"}}})
    ev = canon.identifier_evidence(decl)
    assert ev == {}, (
        f"`lot_id`/`slot` were treated as identifiers on the strength of their names: {ev}")
    res = canon.rule_r1(decl, None, {})
    assert not [m for b in res.buckets if b.verdict == canon.VIOLATION for m in b.members]


@pytest.mark.parametrize("name,expected", [
    ("event_time", True), ("eventtime", True), ("ingested_at", True), ("due_date", True),
    ("updated_by", False), ("event_type", False), ("map_id", False), ("time_zone", False),
])
def test_r5_name_heuristic_boundaries(name, expected):
    """The one name-based predicate in the audit, pinned at its edges.

    It earns its place because this schema stores world time as TEXT, which no type scan
    can see - but it cried wolf on `updated_by` (the word "date" hides inside "updated")
    until the test below existed, and a bucket that is wrong twice gets ignored the third
    time, when it is right.
    """
    decl = canon.Declarations(tables={"t_probe": {"column_types": {name: "string"}}})
    res = canon.rule_r5(decl, None)
    flagged = [b for b in res.buckets if b.key == "world_time_column_declared_string"][0]
    assert bool(len(flagged)) is expected, (
        f"{name}: expected flagged={expected}, got members {flagged.members}")


def test_r7_scan_ignores_prose_and_reads_real_sql():
    """The scanner must not accuse an English sentence containing the word "limit".

    It did: three hits inside the audit's own docstrings, which is an instrument reporting
    its own reflection. A raw-SQL string is only judged when it also looks like a query.
    """
    prose = 'def f():\n    """PostgreSQL has a 63-byte identifier limit."""\n    return 1\n'
    assert canon._scan_source_text(prose) == []

    # The harder one, taken from `value_suggest.py`: an English docstring in which the
    # words select, from and limit all appear, thousands of characters apart, in three
    # unrelated sentences. Word presence cannot separate this from a query; a line that
    # STARTS with a SQL verb can.
    essay = ('def f():\n    """Why it is not SELECT DISTINCT.\n\n'
             '    The naive query ranges from 0.3 ms upward.\n\n'
             '    Every path that stops early - limit reached - sets truncated.\n    """\n'
             '    return 1\n')
    assert canon._scan_source_text(essay) == []

    sql = 'def f(c):\n    return c.execute("SELECT a FROM t LIMIT 10")\n'
    found = canon._scan_source_text(sql)
    assert len(found) == 1 and found[0]["tier"] == "none"

    ordered = 'def f(c):\n    return c.execute("SELECT a FROM t ORDER BY row_id LIMIT 10")\n'
    found = canon._scan_source_text(ordered)
    assert len(found) == 1 and found[0]["tier"] == "same_chain" and found[0]["tiebreak"]


def test_r2_reuses_the_migration_predicate_rather_than_respelling_it():
    """"Is this column really uniquely indexed" has one implementation, and it is not here.

    `add_business_key_unique_index.existing_unique_index` encodes three exclusions -
    partial, expression, multi-column - that separate an index which enforces identity
    from one that merely mentions the column. A second spelling in this file would be a
    second thing to keep in step, and the two would disagree on the day it mattered.
    """
    src = io.open(canon.__file__, encoding="utf-8").read()
    assert "from migrations.add_business_key_unique_index import" in src
    assert "existing_unique_index" in src
    assert "indisunique" not in src, (
        "the uniqueness predicate has been re-spelled here instead of imported")
