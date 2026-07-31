"""`/schema`'s `join_resolved_columns` ― "which columns' values come from a join?"

[The defect]
`announced_columns` answers the NARROWER question ("what must /schema ADD?"), so it omits
**collide** columns. A collide column is a real stored column that a join also fills: it is
already in `columns`, absent from `virtual_columns`, and therefore looks perfectly ordinary
to the grid. Its AG-Grid **Blank** filter then matches nothing and **Not blank** matches
everything, because the value the operator sees COALESCEs to a non-empty label. The client
cannot know that without being told.

[Obligations carried here]
`agent_workspace/reports/Contract_join_resolved_columns.md` lists ten. contract-keeper is
not re-creating its vector this week, so S1-S10 are carried by this file. Its C1/C2 (client)
halves are client-pm's.

  S1  additive - `columns`/`virtual_columns` byte-identical
  S2  key present on EVERY table, `[]` where there is no join
  S3  the set equals `exposed_columns()`, scored BOTH directions
  S4  `kind` stated per entry, both values occur
  S5  `unresolved_label` per entry, following the declaration
  S6  every entry names its `rule` and `right_table`
  S7  a collide-only declaration still leaves `virtual_columns` empty
  S8  🔴 **the marker is NOT the write guard** - behavioural AND structural
  S9  a collide column stays writable
  S10 no name appears in both `columns` and `virtual_columns`

[Fixture decisions that carry weight - from the design note, kept deliberately]
 1. `wafer_id` is BOTH stored and exposed. A fixture where every exposed column is
    virtual_only would pass against an implementation wired to `announced_columns` -
    i.e. against the bug.
 2. Two declarations on one table with DIFFERENT labels, NEITHER equal to
    `virtual_join_config.DEFAULT_UNRESOLVED_LABEL`. A fixture using the default would pass
    against a server emitting the constant AND a client hardcoding it - both sides sharing
    one wrong assumption is a vector worth zero. Asserted below so the axis cannot decay.
 3. `jrc_test_collide_only` exists separately: it is the ONLY case proving the two keys
    answer different questions (`virtual_columns` == [] while this key has one entry).

[격리] `jrc_test_` 접두 ― 사용자 gitignored config에 실존할 수 없다.
[승인 대역 + vacuity guard] sqlite에서 `unique_index_covering`은 항상 None이라 대역이
없으면 승인 규칙이 0건이고 모든 단언이 헛통과한다. 대역을 세우고, 픽스처가 실제로 규칙을
갖는지 먼저 단언한다.
"""
import ast
import inspect
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

JRC_TABLES = {
    "jrc_test_log": {
        "business_key": "log_id",
        "column_types": {"log_id": "string", "jk": "string", "wafer_id": "string"},
    },
    "jrc_test_wafer": {
        "business_key": "wafer_key",
        "column_types": {"wafer_key": "string", "jk": "string",
                         "wafer_id": "string", "fab_site": "string"},
    },
    "jrc_test_site": {
        "business_key": "site_key",
        "column_types": {"site_key": "string", "jk": "string", "line_code": "string"},
    },
    "jrc_test_collide_only": {
        "business_key": "co_id",
        "column_types": {"co_id": "string", "jk": "string", "wafer_id": "string"},
    },
    "jrc_test_plain": {
        "business_key": "p_id",
        "column_types": {"p_id": "string", "note": "string"},
    },
}

# Neither label is `virtual_join_config.DEFAULT_UNRESOLVED_LABEL` - see fixture note 2.
LABEL_WAFER = "NO-WAFER"
LABEL_LINE = "라인미지정"

JRC_RULES = {
    "jrc_rule_wafer": {
        "left_table": "jrc_test_log", "right_table": "jrc_test_wafer",
        "join_key": [{"left": "jk", "right": "jk"}],
        "expose": ["wafer_id", "fab_site"], "unresolved_label": LABEL_WAFER,
    },
    "jrc_rule_line": {
        "left_table": "jrc_test_log", "right_table": "jrc_test_site",
        "join_key": [{"left": "jk", "right": "jk"}],
        "expose": ["line_code"], "unresolved_label": LABEL_LINE,
    },
    "jrc_rule_collide_only": {
        "left_table": "jrc_test_collide_only", "right_table": "jrc_test_wafer",
        "join_key": [{"left": "jk", "right": "jk"}],
        "expose": ["wafer_id"], "unresolved_label": LABEL_WAFER,
    },
}

RIGHT_TABLES = {"jrc_test_wafer", "jrc_test_site"}

EXPECTED_LOG = {
    "wafer_id":  {"kind": "collide",      "rule": "jrc_rule_wafer",
                  "right_table": "jrc_test_wafer", "unresolved_label": LABEL_WAFER},
    "fab_site":  {"kind": "virtual_only", "rule": "jrc_rule_wafer",
                  "right_table": "jrc_test_wafer", "unresolved_label": LABEL_WAFER},
    "line_code": {"kind": "virtual_only", "rule": "jrc_rule_line",
                  "right_table": "jrc_test_site", "unresolved_label": LABEL_LINE},
}


@pytest.fixture()
def jrc_env(db_session, client, tmp_path, monkeypatch):
    models.init_dynamic_models(JRC_TABLES)
    crud.TABLE_CONFIG.update(JRC_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    p = tmp_path / "virtual_join_rules.json"
    p.write_text(json.dumps(JRC_RULES, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, cols: "uq_stub" if table in RIGHT_TABLES else None)
    vjx.reset_cache()

    # 🔴 VACUITY GUARD. Without the stand-in above, sqlite yields ZERO verified rules and
    # every assertion in this file passes while observing nothing.
    assert len(vjx.rules_for(db_session, "jrc_test_log")) == 2, (
        "the fixture has no verified rules; every assertion below would pass vacuously")
    assert len(vjx.rules_for(db_session, "jrc_test_collide_only")) == 1

    yield client

    vjx.reset_cache()
    # Restoring TABLE_CONFIG is NOT enough: `init_dynamic_models` also writes
    # `models.DYNAMIC_TABLES` and `Base.metadata`, and leaving scratch tables there made a
    # DIFFERENT file fail in full-suite order only, earlier this session.
    for t in JRC_TABLES:
        crud.TABLE_CONFIG.pop(t, None)
        models.DYNAMIC_TABLES.pop(t, None)
        tbl = Base.metadata.tables.get(t)
        if tbl is not None:
            Base.metadata.remove(tbl)


def _schema(client, table):
    r = client.get(f"/tables/{table}/schema")
    assert r.status_code == 200, r.text
    return r.json()


def _by_name(entries):
    return {e["name"]: e for e in entries}


# ---------------------------------------------------------------------------
# The fixture's own axes must stay alive
# ---------------------------------------------------------------------------

def test_the_fixture_labels_are_not_the_module_default():
    """Fixture note 2. If a label ever equals the default, S5 stops asserting anything -
    a server emitting the constant and a client hardcoding it would both pass."""
    assert LABEL_WAFER != vjc.DEFAULT_UNRESOLVED_LABEL
    assert LABEL_LINE != vjc.DEFAULT_UNRESOLVED_LABEL
    assert LABEL_WAFER != LABEL_LINE, "two labels that are equal cannot show they ride per entry"


# ---------------------------------------------------------------------------
# S2 / S3 / S4 / S5 / S6 - the announcement itself
# ---------------------------------------------------------------------------

def test_S2_the_key_is_present_on_every_table(jrc_env):
    """`[]`, never absent. An absent key makes the client tell "no joins here" apart from
    "this server predates the key" - a version check wearing a data field."""
    for table in JRC_TABLES:
        body = _schema(jrc_env, table)
        assert "join_resolved_columns" in body, f"key missing entirely on '{table}'"
        assert isinstance(body["join_resolved_columns"], list)
    assert _schema(jrc_env, "jrc_test_plain")["join_resolved_columns"] == []
    assert _schema(jrc_env, "jrc_test_wafer")["join_resolved_columns"] == []


def test_S3_the_set_equals_exposed_columns_both_directions(jrc_env, db_session):
    """🔴 Scored BOTH directions, and against an INDEPENDENT oracle.

    ⚠️ Comparing the key against `vjx.exposed_columns` alone would be TAUTOLOGICAL in this
    implementation: `exposed_columns` is *derived* from `resolved_column_announcements`, so
    the two move together and a defect in the shared source is invisible to that
    comparison. (Confirmed by injection: making the announcement omit collide columns left
    that comparison green while six other assertions went red.) Self-comparison of one
    function cannot detect a uniform error in it.

    So the expected set is recomputed here straight from `rules_for` - the union of every
    verified declaration's `expose` - which is the definition the whole feature rests on
    and shares no code with the function under test.
    """
    for table in JRC_TABLES:
        announced = {e["name"] for e in _schema(jrc_env, table)["join_resolved_columns"]}
        oracle = set()
        for rule in vjx.rules_for(db_session, table):
            oracle.update(rule["expose"])

        assert announced <= oracle, (
            f"{table}: announced a column no verified declaration exposes: "
            f"{announced - oracle}")
        assert oracle <= announced, (
            f"{table}: a verified declaration exposes a column that was never announced: "
            f"{oracle - announced}. Wiring this key to `announced_columns` loses exactly "
            f"the collide columns, which is the defect this round exists to close.")

        # And the search path must resolve precisely what was announced - stated as its
        # own assertion so that if the derivation is ever broken apart, this still holds.
        assert vjx.exposed_columns(db_session, table) == announced


def test_S3b_the_whole_expected_map_is_scored(jrc_env):
    """The full expected shape, compared as a set keyed by name (order is not asserted -
    declaration order is the route's business)."""
    got = _by_name(_schema(jrc_env, "jrc_test_log")["join_resolved_columns"])
    assert set(got) == set(EXPECTED_LOG)
    for name, exp in EXPECTED_LOG.items():
        for field, value in exp.items():
            assert got[name][field] == value, (
                f"jrc_test_log.{name}.{field}: expected {value!r}, got {got[name][field]!r}")


def test_S4_kind_is_stated_and_both_values_occur(jrc_env):
    """`kind` must be STATED, and the fixture must exercise both values - a key where
    `kind` is a constant would pass against an implementation that omitted it."""
    entries = _schema(jrc_env, "jrc_test_log")["join_resolved_columns"]
    kinds = {e["name"]: e["kind"] for e in entries}
    assert set(kinds.values()) == {"collide", "virtual_only"}, (
        f"both kinds must occur or the axis is a constant: {kinds}")
    assert kinds["wafer_id"] == "collide", (
        "wafer_id is declared in jrc_test_log.column_types - it IS stored, and calling it "
        "virtual_only is the misclassification this key exists to prevent")


def test_S4b_the_client_never_needs_set_arithmetic(jrc_env):
    """The collide entry is NOT in `virtual_columns`, so `columns - virtual_columns` would
    classify it as an ordinary stored column. That is why `kind` is stated."""
    body = _schema(jrc_env, "jrc_test_log")
    virtual_names = {c["name"] for c in body["virtual_columns"]}
    assert "wafer_id" not in virtual_names
    assert "wafer_id" in body["columns"]
    assert _by_name(body["join_resolved_columns"])["wafer_id"]["kind"] == "collide"


def test_S5_the_label_rides_per_entry_and_follows_the_declaration(jrc_env):
    got = _by_name(_schema(jrc_env, "jrc_test_log")["join_resolved_columns"])
    assert got["wafer_id"]["unresolved_label"] == LABEL_WAFER
    assert got["line_code"]["unresolved_label"] == LABEL_LINE
    assert got["wafer_id"]["unresolved_label"] != got["line_code"]["unresolved_label"], (
        "two declarations on one table carry different labels; a single value here means "
        "a client could hardcode one")


def test_S6_every_entry_names_its_rule_and_right_table(jrc_env):
    """"Where do I go to fix this value" must be answerable. The write refusal says "fix it
    in the join source" without naming the table; this is where that answer lives."""
    for table in JRC_TABLES:
        for e in _schema(jrc_env, table)["join_resolved_columns"]:
            assert e.get("rule"), f"{table}.{e['name']} has no rule"
            assert e.get("right_table"), f"{table}.{e['name']} has no right_table"
            assert e["right_table"] in JRC_TABLES


# ---------------------------------------------------------------------------
# S1 / S7 / S10 - additive, and the two keys stay distinct
# ---------------------------------------------------------------------------

def test_S1_columns_and_virtual_columns_are_unchanged(jrc_env, db_session, monkeypatch):
    """🔴 Additive. Baseline captured with the announcement SUPPRESSED, then compared.

    Same discipline as `9200f20` putting virtual columns in a new key: a consumer that
    ignores this key must behave exactly as it did before the key existed.
    """
    after = {t: _schema(jrc_env, t) for t in JRC_TABLES}
    monkeypatch.setattr(vjx, "resolved_column_announcements", lambda db, t: [])
    before = {t: _schema(jrc_env, t) for t in JRC_TABLES}
    for t in JRC_TABLES:
        assert before[t]["columns"] == after[t]["columns"], f"{t}: `columns` moved"
        assert before[t]["virtual_columns"] == after[t]["virtual_columns"], (
            f"{t}: `virtual_columns` moved")
        assert before[t]["column_types"] == after[t]["column_types"]


def test_S7_a_collide_only_declaration_leaves_virtual_columns_empty(jrc_env):
    """🔴 The case that proves the two keys answer DIFFERENT questions.

    `jrc_test_collide_only` exposes exactly one column and that column is stored. So
    `virtual_columns` must stay empty while `join_resolved_columns` has one entry. The lazy
    fix - pointing `virtual_columns` at `exposed_columns` - dies here.
    """
    body = _schema(jrc_env, "jrc_test_collide_only")
    assert body["virtual_columns"] == []
    entries = body["join_resolved_columns"]
    assert len(entries) == 1
    assert entries[0]["name"] == "wafer_id"
    assert entries[0]["kind"] == "collide"


def test_S10_no_name_is_in_both_columns_and_virtual_columns(jrc_env):
    for table in JRC_TABLES:
        body = _schema(jrc_env, table)
        overlap = {c["name"] for c in body["virtual_columns"]} & set(body["columns"])
        assert not overlap, f"{table}: announced twice - {overlap}"


# ---------------------------------------------------------------------------
# S8 / S9 - 🔴 THE NO-GO DETECTOR
# ---------------------------------------------------------------------------

def _write(db, table, updates):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=dict(updates), source_name="user",
                                           updated_by="test")],
        transaction_id="jrc_write", silent=True))


def test_S8_suppressing_the_announcement_does_not_make_a_write_succeed(jrc_env, db_session,
                                                                       monkeypatch):
    """🔴 **NO-GO DETECTOR.** If this fails, the DESIGN is wrong - stop the round.

    The refusal belongs to `crud.refuse_virtual_join_columns`, on the funnel every write
    path converges on. This key only stops the UI PROPOSING an impossible edit. If a write
    ever succeeds because the announcement was absent, the key has become the defence - and
    a defence that lives in a READ response is no defence at all: any client that never
    calls `/schema` writes freely.

    Behavioural half: suppress EVERY nameable producer of the announcement, then write.
    `virtual_only_columns` - the guard's real input - is deliberately left alone.
    """
    # Sanity: the write is refused under normal conditions, or this proves nothing.
    with pytest.raises(ValueError):
        _write(db_session, "jrc_test_log", {"log_id": "W1", "fab_site": "SHOULD-REFUSE"})

    monkeypatch.setattr(vjx, "resolved_column_announcements", lambda db, t: [])
    monkeypatch.setattr(vjx, "announced_columns", lambda db, t: [])
    assert _schema(jrc_env, "jrc_test_log")["join_resolved_columns"] == [], (
        "the announcement was not actually suppressed; the test below would pass for the "
        "wrong reason")

    try:
        _write(db_session, "jrc_test_log", {"log_id": "W2", "line_code": "L-9"})
    except ValueError:
        return  # refused, as it must be
    pytest.fail(
        "🔴 NO-GO CONDITION MET.\n"
        "  A write to the virtual_only column 'line_code' SUCCEEDED while the announcement\n"
        "  was suppressed. The marker has become the write guard. A defence that lives in a\n"
        "  read response is no defence -- any client that never calls /schema can write\n"
        "  anything.\n"
        "  Take this to the Lead PM before anything else in this round proceeds.")


def test_S8b_the_write_guard_does_not_read_the_announcement_structurally(jrc_env):
    """🔴 The structural half, and it is NOT redundant with the behavioural one.

    Behaviour can be right by accident - a call graph cannot. The failure this guards
    against is a refactor that rewires the guard's input to the announcement while the
    tests still pass because the two sets happen to coincide on the fixture.
    """
    src = inspect.getsource(crud.refuse_virtual_join_columns)
    tree = ast.parse(src.lstrip())
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                called.add(f.attr)
            elif isinstance(f, ast.Name):
                called.add(f.id)

    forbidden = {"resolved_column_announcements", "announced_columns", "get_table_schema"}
    assert not (called & forbidden), (
        f"🔴 the write guard now reads the ANNOUNCEMENT: {called & forbidden}. "
        f"The marker has become the write guard.")
    assert "virtual_only_columns" in called, (
        "the write guard no longer calls `virtual_join_executor.virtual_only_columns` - "
        "its real input. Whatever it reads now, it is not the set of columns that do not "
        "exist on this table.")


def test_S9_a_collide_column_stays_writable(jrc_env, db_session):
    """🔴 A guard refusing everything in the NEW key would delete the only way to override
    a joined value.

    Writing the left column IS the absent-only rule's "left has a value" arm. Refusing it
    because "it is announced now" would look like tidiness and would leave the user no way
    to correct a joined cell.
    """
    entry = _by_name(_schema(jrc_env, "jrc_test_log")["join_resolved_columns"])["wafer_id"]
    assert entry["kind"] == "collide"
    _write(db_session, "jrc_test_log", {"log_id": "W3", "wafer_id": "WF-OVERRIDE"})
    db_session.flush()
    model = models.DYNAMIC_TABLES["jrc_test_log"]
    row = db_session.query(model).filter(model.business_key_val == "W3").one()
    assert row.wafer_id == "WF-OVERRIDE", (
        "the collide column was refused or dropped - the user can no longer override a "
        "joined value")


def test_S9b_a_virtual_only_column_is_still_refused(jrc_env, db_session):
    """The other side of S9: widening the guard is a bug, and so is narrowing it."""
    with pytest.raises(ValueError) as ei:
        _write(db_session, "jrc_test_log", {"log_id": "W4", "fab_site": "M9"})
    assert "fab_site" in str(ei.value)
