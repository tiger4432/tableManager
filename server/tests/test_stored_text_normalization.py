"""THE WRITE BOUNDARY ― storage is canonical, so SQL and Python agree by construction.

[What this file is defending]
`crud.clean_str_value` strips with Python's `str.strip()`, which removes 29 Unicode
whitespace codepoints. Postgres `btrim(x)` with no second argument strips exactly ONE of
them (U+0020). So a stored `"\\t"` would be EMPTY to every Python reader in this system
and NON-EMPTY to any pushed-down SQL predicate ― and a row displaying `미상` would be
excluded from a `미상` search while `Matches:` said otherwise.

The answer is NOT to teach SQL Python's whitespace table. That is a second spelling, and
a second spelling is a thing that drifts. The answer is that the divergent input never
reaches storage (`crud.normalize_stored_text`), after which
`crud.blank_sql_condition` (NULL-or-'') and `crud.is_blank_value` are the same predicate
and there is nothing to keep in sync.

[Which assertions were RED before the change ― measured by defect injection, not guessed]
A test that asserts its own powerlessness passes forever, so both injections below were
actually run and their output is what this list says.

  Injection A ― `cast_value_by_type` returns `sanitize_to_utf8(value)` (this round's
  change reverted).  3 RED:
      test_surrounding_whitespace_never_reaches_storage            '\tWF-1 ' != 'WF-1'
      test_interior_whitespace_is_never_touched                    edges kept
      test_business_key_and_column_agree_after_normalization       '  K1  ' != 'K1'

  Injection B ― the whitespace-only-to-NULL line weakened to `value == ""` (the
  PRE-EXISTING half, to check the corpus test can see anything at all).  5 RED, including:
      test_a_whitespace_only_value_is_stored_as_null               U+0009 reached storage
      test_no_write_can_produce_a_value_the_two_spellings_disagree_on
          -> "C001: stored '\\t' - Python says blank=True, SQL says blank=False.
              Storage is no longer canonical."

🔴 **The corpus test is GREEN under injection A, and that is not a flaw ― it is the
shape of the problem.** Padding changes a value's EQUALITY, not its BLANKNESS: `' WF-1'`
is non-blank to both spellings. So blankness-agreement cannot detect a missing strip;
only the byte-level assertions above can. Stating the opposite (as an earlier draft of
this docstring did) would have claimed a coverage this file does not have.

  GREEN before, and pinned anyway: `test_a_whitespace_only_value_is_stored_as_null`.
  `cast_value_by_type` has mapped `str(v).strip() == ""` to NULL since long before this
  round ― which is precisely why the live-data measurement of the divergent set came
  back 0 on every column of every table. It is pinned because it is now LOAD-BEARING for
  `blank_sql_condition`, not because it is new.

[격리] 테이블명 접두 `wsnorm_test_` ― 사용자 gitignored config에 실존할 수 없다
(server-pm 교훈: `bonding_log` 함정).
"""
import pytest

from database import crud, models, schemas

NORM_TABLES = {
    "wsnorm_test_rows": {
        "business_key": "row_key",
        "column_types": {
            "row_key": "string",
            "text_col": "string",
            "num_col": "number",
            # Declared string on purpose ― the `stack` precedent: an unreadable height
            # like '0x10' has to SURVIVE the round trip, so the column cannot be numeric.
            "raw_text_col": "string",
        },
    },
}

# Every codepoint Python's str.strip() removes. Built, not typed out ― a hand-written
# list is a 29th chance to be wrong.
PY_WHITESPACE = "".join(chr(c) for c in range(0x110000) if chr(c).isspace())
# The 28 that Postgres btrim(x) does NOT strip. These are the divergence.
DIVERGENT_WHITESPACE = [c for c in PY_WHITESPACE if c != " "]


@pytest.fixture()
def norm_env(db_session):
    models.init_dynamic_models(NORM_TABLES)
    crud.TABLE_CONFIG.update(NORM_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    yield db_session


def _write(db, rows, source_name="pipeline_parser"):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, "wsnorm_test_rows", schemas.GeneralUpdateBatch(
        updates=items, transaction_id="wsnorm_tx", silent=True))
    db.flush()


def _stored(db, key, col="text_col"):
    model = models.DYNAMIC_TABLES["wsnorm_test_rows"]
    row = db.query(model).filter(model.business_key_val == key).one()
    return getattr(row, col)


# ---------------------------------------------------------------------------
# The ruling: "그냥 \t 같은데 안들어가게 막아"
# ---------------------------------------------------------------------------

def test_a_whitespace_only_value_is_stored_as_null(norm_env):
    """A value made only of whitespace ― in ANY of the 29 flavours ― lands as NULL.

    ⚠️ GREEN BEFORE THIS ROUND. `cast_value_by_type` has done this since long before,
    which is exactly why the live-data measurement of the divergent set was 0. It is
    pinned here because `crud.blank_sql_condition` now DEPENDS on it: the moment a bare
    tab can be stored, `col = ''` stops meaning `clean_str_value(col) == ""`.
    """
    db = norm_env
    for i, ws in enumerate(DIVERGENT_WHITESPACE):
        key = f"WS{i:03d}"
        _write(db, [{"row_key": key, "text_col": ws}])
        assert _stored(db, key) is None, (
            f"U+{ord(ws):04X} reached storage; Python calls it empty and "
            f"btrim() does not, so every pushed-down predicate would disagree "
            f"with the payload")


def test_surrounding_whitespace_never_reaches_storage(norm_env):
    """🔴 **RED before this round.** A NON-empty value keeps its text and loses its edges.

    The previously-uncovered half: `cast_value_by_type` mapped whitespace-ONLY to NULL,
    but returned `"  WF-1  "` verbatim. Then `clean_str_value` said `"WF-1"` while
    `col::text` said `"  WF-1  "` ― the same divergence, one step further along.

    Defect-injection check (actually run): restore `return sanitize_to_utf8(value)` in
    `cast_value_by_type` and this fails with `'\\tWF-1 '`.
    """
    db = norm_env
    _write(db, [{"row_key": "PAD", "text_col": "\tWF-1 "}])
    assert _stored(db, "PAD") == "WF-1"


def test_no_write_can_produce_a_value_the_two_spellings_disagree_on(norm_env):
    """The corpus test ― Python's answer and the database's answer on the same bytes.

    ⚠️ **Green under injection A** (see the module docstring): blankness-agreement cannot
    see a missing strip, because padding changes equality and not blankness. What it DOES
    see is injection B ― the moment a whitespace-only value can be stored, this reports
    `stored '\\t' - Python says blank=True, SQL says blank=False`.

    For every input, the value that LANDS must satisfy:
        crud.is_blank_value(stored)  ==  <what blank_sql_condition returns for that row>
    Python's answer and the database's answer, on the same stored bytes, from the two
    spellings that are supposed to be one predicate.

    This is the assertion that would catch a future `cast_value_by_type` that stopped
    normalizing, or a `blank_sql_condition` that grew a `btrim`.
    """
    db = norm_env
    model = models.DYNAMIC_TABLES["wsnorm_test_rows"]

    corpus = ([""] + list(DIVERGENT_WHITESPACE)
              + [" ", "   ", "\t\n ", " 　"]          # blank in Python
              + ["WF-1", " WF-1", "WF-1 ", "\tWF-1\t", "0x10", "7.5", "  0  ", "0"])
    for i, raw in enumerate(corpus):
        key = f"C{i:03d}"
        _write(db, [{"row_key": key, "text_col": raw}])

    rows = {r.business_key_val: r for r in db.query(model).all()}
    # The database's own answer, computed by the SQL spelling.
    blank_per_sql = {
        r.business_key_val for r in
        db.query(model).filter(crud.blank_sql_condition(model.text_col)).all()}
    # And the mirror predicate, so a condition that matched EVERYTHING would not pass.
    notblank_per_sql = {
        r.business_key_val for r in
        db.query(model).filter(crud.not_blank_sql_condition(model.text_col)).all()}

    assert blank_per_sql & notblank_per_sql == set(), "the two SQL spellings overlap"
    assert blank_per_sql | notblank_per_sql == set(rows), "some row answered neither"

    for key, row in rows.items():
        py = crud.is_blank_value(row.text_col)
        sql = key in blank_per_sql
        assert py == sql, (
            f"{key}: stored {row.text_col!r} ― Python says blank={py}, "
            f"SQL says blank={sql}. Storage is no longer canonical.")


# ---------------------------------------------------------------------------
# What must NOT change ― the paths that deliberately round-trip raw text
# ---------------------------------------------------------------------------

def test_unreadable_text_still_survives_the_round_trip(norm_env):
    """The `stack` precedent: `'0x10'` and `'7.5'` come back byte-identical.

    `test_transfer_plan.test_unreadable_stack_text_survives_the_round_trip` is the
    canonical version. Stripping only touches the EDGES, so neither of these moves ―
    stated as an assertion rather than as a claim, because "it obviously doesn't apply"
    is how the last silent repair got in.
    """
    db = norm_env
    for i, raw in enumerate(["0x10", "7.5", "nope", "1.0", "01", "a b  c"]):
        key = f"RAW{i}"
        _write(db, [{"row_key": key, "raw_text_col": raw}])
        assert _stored(db, key, "raw_text_col") == raw


def test_interior_whitespace_is_never_touched(norm_env):
    """Only the edges. A path carried as a value keeps every separator it had.

    The folder-structure-preserving ingestion carries `rel_path` as the identifying
    string; a normalizer that collapsed interior runs would rewrite an operator's
    directory layout. It strips, it does not squeeze.
    """
    db = norm_env
    _write(db, [{"row_key": "PATH", "raw_text_col": " sub dir/a  b/c.csv "}])
    assert _stored(db, "PATH", "raw_text_col") == "sub dir/a  b/c.csv"


def test_a_list_value_is_returned_untouched(norm_env):
    """JSON columns are containers, not text ― `map_doe.mat_*` where the token IS the id.

    `normalize_stored_text` only strips `str`. If it recursed into lists it would rewrite
    material tokens, and `product_tables` records what happened the last time a token's
    text was assumed to be reformattable.
    """
    tokens = [" MID1:1", "MID3:1 "]
    assert crud.normalize_stored_text(list(tokens)) == tokens
    assert crud.normalize_stored_text({"k": " v "}) == {"k": " v "}
    assert crud.normalize_stored_text(7.0) == 7.0
    assert crud.normalize_stored_text(None) is None


def test_the_number_branch_is_unchanged(norm_env):
    """Numbers already stripped before parsing; that path must be byte-identical."""
    db = norm_env
    _write(db, [{"row_key": "N1", "num_col": " 42 "}])
    assert _stored(db, "N1", "num_col") == 42
    with pytest.raises(ValueError):
        crud.cast_value_by_type(" nope ", "number", "num_col")


def test_business_key_and_column_agree_after_normalization(norm_env):
    """`business_key_val` was ALREADY stripped on write; the column now matches it.

    Before this round a padded key produced `business_key_val='K1'` and
    `row_key='  K1  '` ― the same identity spelled two ways in one row, which is how a
    lookup by column silently misses a row that a lookup by key finds.
    """
    db = norm_env
    _write(db, [{"row_key": "  K1  ", "text_col": "v"}])
    model = models.DYNAMIC_TABLES["wsnorm_test_rows"]
    row = db.query(model).filter(model.business_key_val == "K1").one()
    assert row.row_key == "K1" == row.business_key_val
