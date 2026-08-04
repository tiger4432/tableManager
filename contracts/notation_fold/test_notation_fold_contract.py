"""NOTATION FOLD -- the Python fold and the SQL fold, scored against ONE recorded answer.

The file being scored is `contracts/notation_fold/vectors.json`. Nothing here hardcodes an
expected value: every verdict comes out of that file, so deleting a case removes coverage
LOUDLY (`test_every_contract_case_is_consumed`).

    conda run -n assy_manager python -m pytest contracts/notation_fold/ -q -rs

`-rs` IS PART OF THE COMMAND. The axis that matters most -- the SQL fold on the dialect
production actually runs -- is an opt-in skip, because SQLite has neither `regexp_replace`
nor `translate` and cannot evaluate the expression at all. Bare `-q` reports "N skipped",
which says something is unscored but not what, whose, or what it blocks. `-rs` prints the
reasons, which carry all three.

    ASSY_CONTRACT_PG_URL=postgresql://... conda run -n assy_manager python -m pytest \
        contracts/notation_fold/ -q -rs

HOW IT REACHES THE DEFAULT SUITE
    `server/tests/test_notation_fold_contract.py` re-exports every test here -- same shim
    shape and same reason as blank_predicate, map_seam and config_resolve_report:
    `testpaths` is ignored whenever paths are given on the command line, and every
    documented command in this repo passes `server/tests/` explicitly.

WHAT THIS FILE SCORES
    Two spellings of "normalize" is the exact defect class this repository keeps paying
    for. It is why `notation_norm` layered its fold on `map_overlay.canonical_key_value`
    instead of writing a second one beside it. THIS FILE IS THAT RULE, ONE LAYER DOWN: the
    fold now has to exist in Python (the reference) and in SQL (what a virtual join's ON
    clause and a functional UNIQUE index actually evaluate), and those two have to agree
    BYTE FOR BYTE or a join silently stops using its index and stops meaning what the
    approval gate verified.

WHY THE EXPECTATION IS RECORDED AND NOT JUST CROSS-COMPARED
    Engine-vs-engine alone stays green when BOTH sides drift the same wrong way -- and
    they are built from shared constants, which makes drifting together the EASY mistake.
    So `expected` in vectors.json is the contract, and each engine is scored against it
    separately as well as against the other.

🔴 A CONTRACT THAT HAS NEVER BEEN SHOWN TO GO RED PROVES NOTHING
    `test_the_contract_goes_red_when_the_sql_side_is_perturbed` is not decoration. It
    evaluates two DELIBERATELY WRONG SQL spellings -- `upper()` in place of `translate()`,
    and `regexp_replace` without the 'g' flag -- against the same corpus and asserts each
    is CAUGHT. Both are real regressions somebody would write; if the corpus ever stops
    catching them, the corpus stopped covering the thing it exists for.

WHAT THIS FILE DOES NOT DO
    It does not decide. Where the two sides disagree the disagreement is RECORDED
    (`declared_divergences`) with both answers and reported to the Lead PM.
"""
import json
import os
import pathlib
import sys
import unicodedata

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
_SERVER = _ROOT / "server"

# [Isolation] Same pin, for the same reason, as server/tests/conftest.py and
# contracts/blank_predicate: with DATABASE_URL unset, `database.py` resolves to
# DEFAULT_PG_URL -- the LIVE production database. Nothing here connects through
# SQLAlchemy, but a contract that leaves a production URL configured in the process is one
# edit away from using it.
os.environ["DATABASE_URL"] = os.environ.get("ASSY_TEST_DATABASE_URL", "sqlite:///:memory:")

if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

import notation_norm as nn                          # noqa: E402

VECTORS = json.loads((_HERE / "vectors.json").read_text(encoding="utf-8"))
CASES = VECTORS["corpus"]["cases"]
COMBOS = {
    "none": {},
    "sep_only": {nn.RULE_SEPARATOR: True},
    "case_only": {nn.RULE_CASE: True},
    "both": {nn.RULE_SEPARATOR: True, nn.RULE_CASE: True},
}

_CONSUMED = set()


# ---------------------------------------------------------------------------
# Decoding the corpus. Inputs are codepoint arrays on purpose -- half of this
# corpus is characters no editor renders distinguishably, and a literal ' '
# in a JSON file is indistinguishable from a space in review.
# ---------------------------------------------------------------------------

def _decode(spec):
    assert spec["type"] == "text", f"unknown value spec type {spec['type']!r}"
    return "".join(chr(cp) for cp in spec["cp"])


def _show(v):
    """A console-safe rendering. Every non-printing or non-ASCII character comes out as
    U+XXXX -- the console on this machine is CP949, and a character it cannot encode takes
    the WHOLE LINE with it, so the one assertion the reader needs is the one that vanishes.
    """
    if v is None:
        return "NULL"
    out = []
    for ch in v:
        if ch.isprintable() and ch.isascii():
            out.append(ch)
        else:
            try:
                name = unicodedata.name(ch)
            except ValueError:
                name = "?"
            out.append(f"<U+{ord(ch):04X} {name}>")
    return "'" + "".join(out) + "'"


def _corpus():
    """(id, raw, {combo: expected}) for every case, marking it consumed."""
    for case in CASES:
        _CONSUMED.add(case["id"])
        yield (case["id"], _decode(case["input"]),
               {k: _decode(v) for k, v in case["expected"].items()})


# ---------------------------------------------------------------------------
# The Python half
# ---------------------------------------------------------------------------

def test_python_fold_matches_the_recorded_expectation():
    """`fold_notation` against the contract, every case x every rule combination."""
    wrong = []
    for cid, raw, expected in _corpus():
        for combo, rules in COMBOS.items():
            got = nn.fold_notation(raw, rules)
            if got != expected[combo]:
                wrong.append(f"  {cid}[{combo}]: in={_show(raw)} "
                             f"recorded={_show(expected[combo])} python={_show(got)}")
    assert not wrong, (
        "the Python fold no longer answers what vectors.json records:\n" + "\n".join(wrong)
        + "\n\nIf the CHANGE is intended, re-record the vectors AND re-run the Postgres "
          "axis -- a recorded answer only one engine was measured against is not a "
          "contract.")


def test_the_identity_combination_is_actually_the_identity():
    """`none` must return the input unchanged for every case.

    Cheap, and it is what makes "prove each rule toggles alone" mean something: if the
    fold did anything unconditionally, every other assertion here would be measuring that
    hidden step instead of the rule under test.
    """
    for cid, raw, expected in _corpus():
        assert expected["none"] == raw, f"{cid}: vectors.json records a non-identity 'none'"
        assert nn.fold_notation(raw, {}) == raw, f"{cid}"


def test_the_fold_is_idempotent():
    """Folding a folded value is a no-op - the property that lets both sides be folded
    when only one of them is dirty. Without it, folding the already-clean side of a join
    would MOVE it and the match would be lost."""
    wrong = []
    for cid, raw, expected in _corpus():
        for combo, rules in COMBOS.items():
            once = expected[combo]
            twice = nn.fold_notation(once, rules)
            if twice != once:
                wrong.append(f"  {cid}[{combo}]: {_show(once)} -> {_show(twice)}")
    assert not wrong, ("the fold is not idempotent, so folding an already-clean join key "
                       "moves it:\n" + "\n".join(wrong))


# ---------------------------------------------------------------------------
# Structural: one spelling, shared - not two copies that happen to match today
# ---------------------------------------------------------------------------

def test_the_sql_text_carries_the_shared_constants_verbatim():
    """🔴 The SQL must be BUILT from the same constants, not written to match them.

    A hand-typed copy of the pattern in `fold_sql_text` would pass every value test on the
    day it was written and drift the first time a codepoint is added to the tuple.
    """
    sql = nn.fold_sql_text("COL", {nn.RULE_SEPARATOR: True, nn.RULE_CASE: True})
    assert nn.SEPARATOR_PATTERN in sql, "the SQL does not use SEPARATOR_PATTERN"
    assert nn.CASE_SOURCE_ALPHABET in sql and nn.CASE_TARGET_ALPHABET in sql
    # ...and the pattern is DERIVED from the codepoint tuple, so the tuple is the source.
    rebuilt = "[" + "".join("\\u%04x" % cp for cp in nn.SEPARATOR_CODEPOINTS) + "-]+"
    assert nn.SEPARATOR_PATTERN == rebuilt, (
        "SEPARATOR_PATTERN is no longer derived from SEPARATOR_CODEPOINTS. The two would "
        "then be two spellings of the separator class, which is this contract's subject.")


def test_the_g_flag_is_in_the_generated_sql():
    """Without 'g', PostgreSQL replaces only the FIRST run (measured: 'WF.A_B 01' ->
    'WF-A_B 01'), so 'WF.A_B' and 'WF-A-B' stay two values and the join keeps splitting
    the lot it was supposed to join."""
    sql = nn.fold_sql_text("COL", {nn.RULE_SEPARATOR: True})
    assert "'g'" in sql, f"the global flag is missing from: {sql}"


def test_the_case_rule_never_reaches_for_upper():
    """`upper()` is locale- and Unicode-dependent and was MEASURED to disagree with
    `str.upper()` (see `measurements.upper_vs_str_upper`). `translate` over an ASCII pair
    is the only spelling both engines can hold."""
    sql = nn.fold_sql_text("COL", {nn.RULE_CASE: True})
    assert "translate(" in sql
    assert "upper(" not in sql.lower(), (
        "the case rule went back to upper(); the eszett case in this corpus records what "
        "that costs")


def test_no_rule_enabled_produces_no_sql_wrapper():
    """A declaration with everything off must cost nothing, in SQL as in Python."""
    assert nn.fold_sql_text("COL", {}) == "COL"


# ---------------------------------------------------------------------------
# The SQL half, on the dialect production actually runs
# ---------------------------------------------------------------------------

_PG_SKIP = (
    "PENDING AXIS -- the SQL fold is UNSCORED on this run. It cannot be scored on the "
    "suite dialect: SQLite has neither `regexp_replace` nor `translate`, so "
    "`fold_notation_sql` compiles there to a scalar function whose body IS "
    "`fold_notation` -- the two halves are the same code and comparing them proves "
    "nothing. Blocks: EVERY value assertion about the SQL fold, and with it the claim "
    "that a virtual join's ON clause and its functional UNIQUE index agree. "
    "Owner: whoever runs the suite. Run with ASSY_CONTRACT_PG_URL=postgresql://... to "
    "score it. Recorded measurement (2026-08-04, PostgreSQL 18.3): all 43 corpus cases "
    "x 4 rule combinations agree byte-for-byte with the recorded expectation.")


def _pg_connect():
    url = os.environ.get("ASSY_CONTRACT_PG_URL")
    if not url:
        pytest.skip(_PG_SKIP)
    import psycopg2
    conn = psycopg2.connect(url, connect_timeout=5)
    # READ ONLY and scalar-only: no table is named and no row is read. The fold is a pure
    # expression, so this axis never needs to touch the operator's data.
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _pg_fold(cur, raw, sql_builder, rules):
    cur.execute("select " + sql_builder("%s::text", rules), (raw,))
    return cur.fetchone()[0]


def test_postgres_fold_matches_the_recorded_expectation():
    """🔴 THE LOAD-BEARING ASSERTION OF THIS CONTRACT.

    Every corpus case x every rule combination, evaluated by PostgreSQL through
    `notation_norm.fold_sql_text` -- the SAME function that writes the functional index
    DDL -- and compared BYTE FOR BYTE against the recorded expectation and against Python.
    """
    conn = _pg_connect()
    try:
        cur = conn.cursor()
        wrong = []
        for cid, raw, expected in _corpus():
            for combo, rules in COMBOS.items():
                got = _pg_fold(cur, raw, nn.fold_sql_text, rules)
                want = expected[combo]
                if got != want:
                    wrong.append(f"  {cid}[{combo}] vs RECORDED: in={_show(raw)} "
                                 f"recorded={_show(want)} postgres={_show(got)}")
                py = nn.fold_notation(raw, rules)
                if got != py:
                    wrong.append(f"  {cid}[{combo}] vs PYTHON:   in={_show(raw)} "
                                 f"python={_show(py)} postgres={_show(got)}")
        assert not wrong, (
            "the SQL fold and the contract disagree:\n" + "\n".join(wrong)
            + "\n\nThis is the seam. A join's ON clause and the functional UNIQUE index "
              "that approved it are both built from `fold_sql_text`; a divergence here "
              "means the index PostgreSQL was told to use is not the expression the query "
              "evaluates, and neither half reports an error.")
    finally:
        conn.close()


def test_the_contract_goes_red_when_the_sql_side_is_perturbed():
    """🔴 PROOF THAT THE CORPUS CAN CATCH A REGRESSION, by perturbation not by assertion.

    Three deliberately wrong SQL spellings, all of which a real author would write:

      DROPPED_G     `regexp_replace` without the global flag. Reads correct, folds only
                    the FIRST run, and every single-separator value in a casual test
                    still passes. (Measured 2026-08-04: caught by 8 of 172 comparisons.)
      UPPER         `upper()` in place of `translate()`. Reads MORE correct than the real
                    one, and is wrong for every non-ASCII letter - differently on every
                    database ctype. (Caught by 4 of 172.)
      POSIX_SPACE   The separator class written as the SHORTHAND `[._[:space:]-]` instead
                    of enumerated. This is the likeliest regression of the three, because
                    the enumerated pattern is 190 characters and looks like something to
                    tidy up. (Caught by 6 of 172 - and by nothing else in this repository.)

    Each must be CAUGHT by at least one corpus case. If a perturbation passes, the corpus
    lost the class of case that covers it and this test says which. The real
    `fold_sql_text` scores 0 of 172 on the same loop, which is what makes these numbers
    mean something.
    """
    conn = _pg_connect()

    def dropped_g(inner, rules):
        out = inner
        if rules.get(nn.RULE_SEPARATOR):
            out = "regexp_replace(%s, '%s', '%s')" % (out, nn.SEPARATOR_PATTERN,
                                                      nn.SEPARATOR_TARGET)
        if rules.get(nn.RULE_CASE):
            out = "translate(%s, '%s', '%s')" % (out, nn.CASE_SOURCE_ALPHABET,
                                                 nn.CASE_TARGET_ALPHABET)
        return out

    def upper_instead_of_translate(inner, rules):
        out = inner
        if rules.get(nn.RULE_SEPARATOR):
            out = "regexp_replace(%s, '%s', '%s', 'g')" % (out, nn.SEPARATOR_PATTERN,
                                                           nn.SEPARATOR_TARGET)
        if rules.get(nn.RULE_CASE):
            out = "upper(%s)" % out
        return out

    def posix_space_class(inner, rules):
        out = inner
        if rules.get(nn.RULE_SEPARATOR):
            out = "regexp_replace(%s, '%s', '%s', 'g')" % (
                out, "[._[:space:]-]+", nn.SEPARATOR_TARGET)
        if rules.get(nn.RULE_CASE):
            out = "translate(%s, '%s', '%s')" % (out, nn.CASE_SOURCE_ALPHABET,
                                                 nn.CASE_TARGET_ALPHABET)
        return out

    try:
        cur = conn.cursor()
        for label, builder in (("DROPPED_G", dropped_g),
                               ("UPPER", upper_instead_of_translate),
                               ("POSIX_SPACE", posix_space_class)):
            caught = []
            for cid, raw, expected in _corpus():
                for combo, rules in COMBOS.items():
                    if _pg_fold(cur, raw, builder, rules) != expected[combo]:
                        caught.append(f"{cid}[{combo}]")
            assert caught, (
                f"perturbation {label} was NOT caught by any corpus case. The corpus does "
                f"not cover the class of defect it exists for -- add a case before "
                f"trusting a green run of this file.")
    finally:
        conn.close()


def test_null_propagates_identically_on_both_sides():
    """A NULL join key must not match, exactly as it did before this feature existed."""
    conn = _pg_connect()
    try:
        cur = conn.cursor()
        for combo, rules in COMBOS.items():
            cur.execute("select " + nn.fold_sql_text("NULL::text", rules))
            assert cur.fetchone()[0] is None, f"{combo}: SQL turned NULL into a value"
            assert nn.fold_notation(None, rules) is None, combo
    finally:
        conn.close()


def test_the_measurements_this_design_rests_on_still_hold():
    """The facts in `measurements` were the ARGUMENT for the design. Re-derived, not
    trusted: if PostgreSQL's own answers change, the reasoning has to be revisited before
    the code is."""
    conn = _pg_connect()
    try:
        cur = conn.cursor()
        m = VECTORS["measurements"]
        cur.execute("select regexp_replace(%s, %s, %s)",
                    (m["regexp_replace_without_g"]["input"], nn.SEPARATOR_PATTERN,
                     nn.SEPARATOR_TARGET))
        assert cur.fetchone()[0] == m["regexp_replace_without_g"]["output"], (
            "the no-'g' behaviour changed; `test_the_g_flag_is_in_the_generated_sql` "
            "rests on this measurement")
        # `upper()` still disagrees with `str.upper()` -- the reason the case rule is
        # ASCII-only. If this ever became false the narrowing could be revisited.
        cur.execute("select upper(%s)", ("straße",))
        assert cur.fetchone()[0] != "straße".upper(), (
            "PostgreSQL's upper() now agrees with Python's on the eszett. The ASCII-only "
            "narrowing was justified by this disagreement -- re-open the decision rather "
            "than leaving a narrowing whose reason has expired.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Coverage of the contract itself
# ---------------------------------------------------------------------------

def test_every_contract_case_is_consumed():
    """A case nobody reads is a case that can be deleted without anything going red."""
    declared = {c["id"] for c in CASES}
    unused = sorted(declared - _CONSUMED)
    assert not unused, (
        "these corpus cases were never scored by any test in this file:\n  "
        + "\n  ".join(unused)
        + "\n\nEither wire them in or delete them -- an unread vector is a comment that "
          "looks like coverage.")


def test_the_corpus_covers_the_classes_the_brief_requires():
    """Separators of every kind and run length, mixed case, unicode, empty,
    whitespace-only, and values that are already folded. Asserted rather than trusted to
    review, plus the two MEASURED divergence points in both directions."""
    ids = {c["id"] for c in CASES}
    required = {
        "empty", "single_space", "only_separators",           # empty / whitespace-only
        "dot", "hyphen", "underscore", "space",               # every separator kind
        "run_double_hyphen", "run_mixed", "run_long",         # run length + mixed run
        "lower_space", "mixed_case_ascii",                    # mixed case
        "already_folded",                                     # already folded
        "nbsp", "ideographic_space", "korean", "fullwidth_a", # unicode
        "file_separator", "unit_separator",                   # python-only whitespace
        "mongolian_vowel_separator",                          # postgres-only whitespace
        "eszett", "dotless_i", "ligature_fi", "sigma",        # case-fold divergence
        "padded_zero",                                        # zero_pad is NOT implemented
    }
    assert required <= ids, f"the corpus lost required classes: {sorted(required - ids)}"
