"""GET /tables/{t}/schema announces the columns a VERIFIED virtual join adds.

The payload has carried joined columns since `d70a33d`, but `/schema` never mentioned
them, so a `virtual_only` column could not be rendered: the operator who declared the
expose got neither the column nor a reason. This file is the declaration side catching up.

WHAT IS BEING FIXED IN PLACE HERE - three properties, each with its own red:

  1. A `virtual_only` column IS announced, marked `editable: false`.
  2. A `collide` column is NOT announced. It is a real stored column that the join also
     fills, so it is already in `columns`; announcing it again gives two answers to "is
     this column stored?". `test_a_collide_only_declaration_leaves_the_response_byte_
     identical` compares the WHOLE RESPONSE BODY, not a field.
  3. The announcement matches what the payload actually gains - `test_the_announced_set_
     is_exactly_what_the_payload_gains` diffs the real `/data` payload with the join off
     and on. Announcement and payload drifting apart is the same defect with its sign
     flipped, so a set comparison is the only assertion that holds both ends.

🔴 THE ANNOUNCEMENT IS NOT WHAT REFUSES A WRITE. `crud.refuse_virtual_join_columns` does,
at the single funnel. `test_the_write_refusal_does_not_depend_on_the_announcement` blanks
the announcement and shows the write is still 400 - if that test ever goes green only
because of `editable: false`, the read-only has become cosmetic.

[Isolation] Table names are `vjs_test_` prefixed - they cannot exist in the user's
gitignored config. A collision lets import-time `init_dynamic_models` pin a real schema in
the shared sqlite and `create_all(checkfirst)` skips ours (server-pm memory: the
`bonding_log` trap).

[Why `unique_index_covering` is faked] Approval comes from `pg_index` and this suite runs
on sqlite, where the real function always returns None ("do not know" = refuse). Left
alone, every test here would observe zero joins and pass while executing nothing. Only
approval is doubled; `test_a_refused_declaration_announces_nothing` deliberately runs
WITHOUT the double.
"""
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

JOIN_TABLES = {
    # Left - log shaped. Many rows per key is normal and is the point of the join.
    "vjs_test_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string", "core_slot": "string",
            # 🔴 the collide column: the right table has this name too.
            "wafer_id": "string",
        },
    },
    # Right - wafer master, unique on (core_lot, core_slot).
    "vjs_test_wafer": {
        "business_key": "wafer_key",
        "composite_key_source": ["core_lot", "core_slot"],
        "column_types": {
            "wafer_key": "string", "core_lot": "string", "core_slot": "string",
            "wafer_id": "string", "fab_site": "string",
            # Declared `number` on the right and absent from the left: this is the one
            # that proves the announced type is READ from the right table's declaration
            # rather than assumed.
            "die_count": "number",
        },
    },
}

KEY_PAIRS = [{"left": "core_lot", "right": "core_lot"},
             {"left": "core_slot", "right": "core_slot"}]


def _decl(expose, **extra):
    d = {"left_table": "vjs_test_log", "right_table": "vjs_test_wafer",
         "join_key": [dict(p) for p in KEY_PAIRS], "expose": list(expose)}
    d.update(extra)
    return d


def _write_rules(monkeypatch, tmp_path, decls, filename="virtual_join_rules.json"):
    p = tmp_path / filename
    p.write_text(json.dumps(decls, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    vjx.reset_cache()
    return p


def _seed(db, table, rows, source_name="pipeline_parser"):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"seed_{table}", silent=True))


@pytest.fixture()
def join_env(db_session, tmp_path, monkeypatch):
    """The two tables registered, no declaration file yet (each test writes its own)."""
    models.init_dynamic_models(JOIN_TABLES)
    crud.TABLE_CONFIG.update(JOIN_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(tmp_path / "absent.json"))
    vjx.reset_cache()
    yield db_session
    vjx.reset_cache()


@pytest.fixture()
def approved(monkeypatch):
    """Stand-in for the `pg_index` approval (see module docstring)."""
    def _covering(db, table, columns):
        if table == "vjs_test_wafer" and set(columns) <= {"core_lot", "core_slot"}:
            return "uq_vjoin_vjs_test_wafer_core_lot_core_slot"
        return None
    monkeypatch.setattr(vjc, "unique_index_covering", _covering)
    vjx.reset_cache()
    return _covering


class _join_off:
    """Point the loader at a file that does not exist - the feature is then OFF.

    This is how a baseline is taken INSIDE one test, so the comparison is against this
    same process, this same config, this same session. A hand-written expected dict would
    drift the moment an unrelated field joins the schema contract.
    """

    def __enter__(self):
        self._path = vjc.VIRTUAL_JOIN_RULES_PATH
        vjc.VIRTUAL_JOIN_RULES_PATH = str(self._path) + ".absent"
        vjx.reset_cache()
        return self

    def __exit__(self, *exc):
        vjc.VIRTUAL_JOIN_RULES_PATH = self._path
        vjx.reset_cache()
        return False


def _schema(client, table="vjs_test_log"):
    res = client.get(f"/tables/{table}/schema")
    assert res.status_code == 200
    return res


def _payload_columns(client, table="vjs_test_log"):
    """The set of cell keys the real read path puts in the payload."""
    res = client.get(f"/tables/{table}/data")
    assert res.status_code == 200
    keys = set()
    for row in res.json()["data"]:
        keys |= set(row["data"].keys())
    return keys


# ---------------------------------------------------------------------------
# The announcement itself
# ---------------------------------------------------------------------------

def test_a_virtual_only_column_is_announced(join_env, approved, client, tmp_path,
                                            monkeypatch):
    """🔴 The defect this round fixes: an exposed column the left table does not have.

    Injection check (ran it): make `announced_columns` return `[]` and this goes red.
    """
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["fab_site"])})
    body = _schema(client).json()

    assert [c["name"] for c in body["virtual_columns"]] == ["fab_site"]
    entry = body["virtual_columns"][0]
    assert entry["editable"] is False, "the grid must not offer an edit that would 400"
    assert entry["right_table"] == "vjs_test_wafer", "where the user must go to fix it"
    assert entry["rule"] == "vjs_rule", "the bridge to /admin/config/virtual-join/verify"
    assert entry["unresolved_label"] == "미상"
    # And it is NOT smuggled into the stored-column list.
    assert "fab_site" not in body["columns"]
    assert "fab_site" not in body["column_types"]


def test_the_stored_column_contract_is_untouched(join_env, approved, client, tmp_path,
                                                 monkeypatch):
    """Everything except the announcement keys is identical with the join on and off.

    A client that ignores them must behave EXACTLY as it did before they existed - same
    grid columns, same push-gate arithmetic, same paste targets. That is only true if
    `columns`/`column_types` describe stored columns and nothing else.

    ⚠️ **`join_resolved_columns` joined `virtual_columns` in the exempt set on
    2026-07-31.** Both are additive announcements; neither may move a stored-column fact.
    The assertion below is stated as "the ONLY differing keys are these two", which is
    stronger than popping them: it also catches a third key appearing.
    """
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["fab_site", "die_count"])})
    with _join_off():
        before = _schema(client).json()
    after = _schema(client).json()

    assert after["virtual_columns"], "the join must actually be in effect here"
    assert after["join_resolved_columns"], "the join must actually be in effect here"
    differing = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert differing == {"virtual_columns", "join_resolved_columns"}, (
        f"turning the join on moved something other than the announcements: "
        f"{differing - {'virtual_columns', 'join_resolved_columns'}}")


def test_the_announced_type_comes_from_the_right_table_declaration(join_env, approved,
                                                                   client, tmp_path,
                                                                   monkeypatch):
    """The value comes from the right table, so its declared type does too.

    Injection check: hardcode `"type": "string"` and this goes red on `die_count`.
    """
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["fab_site", "die_count"])})
    types = {c["name"]: c["type"] for c in _schema(client).json()["virtual_columns"]}
    assert types == {"fab_site": "string", "die_count": "number"}


# ---------------------------------------------------------------------------
# Collide - the response must not move by one byte
# ---------------------------------------------------------------------------

def test_a_collide_only_declaration_adds_only_the_join_resolved_entry(join_env, approved,
                                                                      client, tmp_path,
                                                                      monkeypatch):
    """`wafer_id` exists on the left. It is a real stored column that the join happens to
    fill, already described by `columns`/`column_types`, and still writable. Announcing it
    in `virtual_columns` would make one response give two answers to "is this stored?".

    ⚠️ **CORRECTION 2026-07-31 - the previous docstring's injection claim was FALSE.**
    It said "drop the `virtual_only` filter and this goes red". Measured: it does NOT.
    TWO independent layers each suppress a collide announcement, and removing either one
    alone leaves this green:
      1. `virtual_join_executor.announced_columns` iterates `rule["virtual_only"]`;
      2. `get_table_schema` filters the announced list against `known = set(columns)`.
    Injected each separately - green both times (a different test caught each). Injected
    BOTH together - red, with the message below. Defence in depth is a good property, but
    a docstring that names one falsifier when there are two teaches the next reader that
    removing that one layer is safe.
    See `Contract_join_resolved_columns.md` §6, which predicted exactly this for its S7.
    `test_the_schema_route_still_dedupes_against_columns` below pins layer 2 structurally,
    since no behavioural test can reach it while layer 1 stands.

    ⚠️ **THIS TEST WAS NARROWED ON 2026-07-31, and that is a deliberate contract change,
    not a test bent to fit code.** It used to assert the whole body was BYTE-IDENTICAL for
    a collide-only declaration. The `join_resolved_columns` round supersedes that: a
    collide column IS resolved through a join, the client cannot know it without being
    told, and the consequence of not telling it was measured - AG-Grid `Blank` matched 0
    rows on a column where the operator saw values, because the displayed value COALESCEs
    to a non-empty label.

    What the original assertion was PROTECTING is kept intact and is still asserted below:
      - `virtual_columns` must stay EMPTY (that is the "two answers" defect), and
      - `columns`/`column_types` must not move.
    What changed is only that the response is now allowed to differ in exactly one key.
    `join_resolved_columns` cannot reintroduce the ambiguity because it carries NO
    writability field - editability still lives only in `columns[].editable` and
    `virtual_columns[].editable`.

    """
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["wafer_id"])})
    with _join_off():
        before = _schema(client).json()
    after = _schema(client).json()

    # The defect the original test existed to catch, asserted directly.
    assert after["virtual_columns"] == [], (
        "a collide column was announced as virtual - one response now gives two answers "
        "about whether it is stored")
    # ...and nothing else moved except the one new key.
    differing = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert differing == {"join_resolved_columns"}, (
        f"a collide-only declaration moved more than the join announcement: {differing}")
    assert [e["name"] for e in after["join_resolved_columns"]] == ["wafer_id"]
    assert after["join_resolved_columns"][0]["kind"] == "collide"
    # ...and the declaration really was in force - it is filling the collide column.
    assert vjx.rules_for(join_env, "vjs_test_log"), "the rule must be verified here"


def test_the_schema_route_still_dedupes_against_columns():
    """Layer 2 of the collide defence, pinned STRUCTURALLY because behaviour cannot reach it.

    While `announced_columns` filters to `virtual_only` (layer 1), no fixture can make the
    route's `known = set(columns)` filter matter - so a purely behavioural suite would let
    someone delete it and stay green, leaving one layer where the comment above promises
    two. That filter is also the ONLY thing stopping a right table that declares a system
    tail name (`created_at`, the graph flags) from being announced on top of a column that
    is already there: those names are in `columns` but belong to no config, so `collide`
    never sees them.

    An AST walk, not a substring search: `known` could be renamed and the intent kept.
    What is asserted is that the comprehension iterating **`announced`** carries an
    `if ... not in ...` test.

    ⚠️ The first version of this assertion accepted ANY list comprehension with a
    `not in` test, and `get_table_schema` contains others (the `columns` fallback filters
    system names the same way). It therefore passed with the filter deleted - a test
    asserting its own powerlessness. Injected the deletion, saw it stay green, and
    tightened it to name the iterable. It goes red now.
    """
    import ast
    import inspect
    import main

    src = inspect.getsource(main.get_table_schema)
    tree = ast.parse(src.lstrip())

    def _iterates_announced(comp):
        return any(isinstance(g.iter, ast.Name) and g.iter.id == "announced"
                   for g in comp.generators)

    over_announced = [n for n in ast.walk(tree)
                      if isinstance(n, ast.ListComp) and _iterates_announced(n)]
    assert over_announced, (
        "no list comprehension in `get_table_schema` iterates `announced` any more - "
        "this test can no longer see the filter it exists to pin. Re-point it.")

    guarded = [
        n for n in over_announced
        if any(g.ifs and any(isinstance(t, ast.Compare)
                             and any(isinstance(op, ast.NotIn) for op in t.ops)
                             for t in g.ifs)
               for g in n.generators)
    ]
    assert guarded, (
        "`get_table_schema` no longer filters the announced columns against the names "
        "already in `columns`. A right table declaring `created_at` - or any collide name "
        "that reaches `virtual_only` - would now be announced on top of a stored column, "
        "and one response would give two answers about whether it is stored.")


def test_a_system_tail_name_is_not_announced_either(join_env, approved, client, tmp_path,
                                                    monkeypatch):
    """The other way a name can already be in `columns` - and `collide` does not see it.

    `collide` is computed against the left table's `column_types`, but `columns` also
    carries a system tail (`created_at`, the graph flags) that belongs to no config and is
    appended unconditionally. A right table declaring one of those names lands in
    `virtual_only` and would be announced on top of a column that is already there.

    Injection check (ran it): drop the `known = set(columns)` filter in `get_table_schema`
    and `created_at` appears in BOTH lists.
    """
    crud.TABLE_CONFIG["vjs_test_wafer"]["column_types"]["created_at"] = "datetime"
    try:
        _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["created_at"])})
        body = _schema(client).json()
        assert vjx.rules_for(join_env, "vjs_test_log"), "the rule must be verified here"
        assert [c["name"] for c in vjx.announced_columns(join_env, "vjs_test_log")] == \
            ["created_at"], "the executor cannot see the tail - that is why the route filters"
        assert body["virtual_columns"] == []
        assert body["columns"].count("created_at") == 1
    finally:
        crud.TABLE_CONFIG["vjs_test_wafer"]["column_types"].pop("created_at", None)


def test_a_mixed_declaration_announces_only_the_virtual_half(join_env, approved, client,
                                                             tmp_path, monkeypatch):
    """One declaration, one collide column and one virtual-only column."""
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["wafer_id", "fab_site"])})
    body = _schema(client).json()

    assert [c["name"] for c in body["virtual_columns"]] == ["fab_site"]
    assert "wafer_id" in body["columns"], "the collide column keeps its stored identity"
    assert body["columns"].count("wafer_id") == 1


# ---------------------------------------------------------------------------
# Only verified rules - a refused declaration must not produce a phantom column
# ---------------------------------------------------------------------------

def test_a_refused_declaration_announces_nothing(join_env, client, tmp_path, monkeypatch):
    """🔴 NO `approved` fixture here - this is the one test that runs the real gate.

    On sqlite `unique_index_covering` returns None, so the declaration is refused exactly
    as it would be in production without the UNIQUE index. A refused declaration attaches
    nothing to the payload; if it announced a column anyway, the grid would render an
    always-empty column that no data can ever reach.

    Injection check (ran it): point `_verified_by_left_table` at
    `load_virtual_join_rules` (shape-only) and this goes red.
    """
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["fab_site"])})
    assert _schema(client).json()["virtual_columns"] == []
    # The declaration is well-formed; it is the uniqueness gate that stops it.
    assert vjc.load_virtual_join_rules(known_tables=crud.TABLE_CONFIG), "shape is valid"
    assert vjx.rules_for(join_env, "vjs_test_log") == []


def test_a_shape_only_rule_announces_nothing_but_is_still_refused_a_write(join_env,
                                                                          monkeypatch):
    """`virtual_only is None` - the two guards lean OPPOSITE ways, deliberately.

    A rule verified without `table_config` does not know which exposed names exist on the
    left. The write guard refuses ALL of them (do not know -> block: a write to a column
    that does not exist is worse than a refused edit). The announcement does the reverse
    (do not know -> say nothing: announcing a collide column would double-announce a real
    stored column). Both lean toward "no phantom column, no phantom write".

    This state cannot arise on the executor's normal path, which always passes
    `crud.TABLE_CONFIG` - so the branch is reached here through the real loader.
    """
    shape_only = vjc.validate_virtual_join_rules({"vjs_rule": _decl(["wafer_id",
                                                                    "fab_site"])},
                                                 known_tables=None)
    assert shape_only[0]["virtual_only"] is None, "the fixture must activate the branch"
    monkeypatch.setattr(vjx, "rules_for", lambda db, t: list(shape_only))

    assert vjx.announced_columns(join_env, "vjs_test_log") == []
    assert vjx.virtual_only_columns(join_env, "vjs_test_log") == {"wafer_id", "fab_site"}


# ---------------------------------------------------------------------------
# The announcement and the payload are the same set - both derive from `rules_for`
# ---------------------------------------------------------------------------

def test_the_announced_set_is_exactly_what_the_payload_gains(join_env, approved, client,
                                                             tmp_path, monkeypatch):
    """🔴 The anti-drift test: `/schema` and `/data` are read by the same client.

    Announced-but-absent renders an empty column forever; present-but-unannounced is the
    defect this round exists to fix. Comparing SETS holds both ends at once, and it is
    measured on the real endpoints rather than on the two functions' return values (which
    would compare the implementation with itself).

    Injection check (ran it): return `[]` from `announced_columns` and the set difference
    `{fab_site, die_count}` fails to match; announce `expose` instead of `virtual_only`
    and `wafer_id` shows up on the announced side but not on the gained side.
    """
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["wafer_id", "fab_site",
                                                            "die_count"])})
    _seed(join_env, "vjs_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                        "core_slot": "01", "wafer_id": "WF-1",
                                        "fab_site": "M1", "die_count": 42}])
    _seed(join_env, "vjs_test_log", [
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"},
        {"log_id": "L2", "core_lot": "NO-SUCH", "core_slot": "99"},
    ])

    with _join_off():
        stored = _payload_columns(client)
    gained = _payload_columns(client) - stored

    announced = {c["name"] for c in _schema(client).json()["virtual_columns"]}
    assert announced == gained == {"fab_site", "die_count"}
    # The collide column is in both payloads, which is why it is in neither set.
    assert "wafer_id" in stored


def test_the_announced_label_is_the_one_the_cells_actually_carry(join_env, approved,
                                                                 client, tmp_path,
                                                                 monkeypatch):
    """The label is per declaration, so announcing a constant would be a lie.

    A client that styles the unresolved sentinel must read it from here; hardcoding "미상"
    would ignore the declaration, which is the configuration-takes-no-effect defect again.

    Injection check (ran it): announce `vjc.DEFAULT_UNRESOLVED_LABEL` instead of
    `rule["unresolved_label"]` and this goes red.
    """
    _write_rules(monkeypatch, tmp_path,
                 {"vjs_rule": _decl(["fab_site"], unresolved_label="UNKNOWN")})
    _seed(join_env, "vjs_test_log", [{"log_id": "L1", "core_lot": "NO", "core_slot": "NO"}])

    announced = _schema(client).json()["virtual_columns"][0]
    cell = client.get("/tables/vjs_test_log/data").json()["data"][0]["data"]["fab_site"]
    assert announced["unresolved_label"] == "UNKNOWN" == cell["value"]


def test_two_declarations_exposing_one_column_announce_it_once(join_env, approved,
                                                               client, tmp_path,
                                                               monkeypatch):
    """One column, announced once, with the label the payload will actually use.

    `attach` resolves a doubly-exposed column with `labels.setdefault` - the first
    declaration's label wins. The announcement follows the same rule because the two must
    not disagree about the same cell.

    Injection check (ran it): drop the `seen` de-duplication and `fab_site` is announced
    twice; take the LAST label instead of the first and the label assertion goes red.
    """
    _write_rules(monkeypatch, tmp_path, {
        # Declaration order matters here: the first one is what `attach` will honour.
        "vjs_first": _decl(["fab_site"], unresolved_label="FIRST"),
        "vjs_second": _decl(["fab_site"], unresolved_label="SECOND"),
    })
    _seed(join_env, "vjs_test_log", [{"log_id": "L1", "core_lot": "NO", "core_slot": "NO"}])
    assert len(vjx.rules_for(join_env, "vjs_test_log")) == 2, "both must be verified"

    announced = _schema(client).json()["virtual_columns"]
    assert [c["name"] for c in announced] == ["fab_site"], "announced once, not twice"
    cell = client.get("/tables/vjs_test_log/data").json()["data"][0]["data"]["fab_site"]
    assert announced[0]["unresolved_label"] == "FIRST" == cell["value"]


# ---------------------------------------------------------------------------
# Read-only is structural. The flag only stops the OFFER
# ---------------------------------------------------------------------------

def test_the_write_refusal_does_not_depend_on_the_announcement(join_env, approved, client,
                                                               tmp_path, monkeypatch):
    """🔴 `editable: false` is a UI hint, NOT the enforcement.

    If this ever goes green only because the schema said `editable: false`, the read-only
    has become cosmetic - and every writer that does not read `/schema` (file ingestion,
    the chain worker, enrichment, replay, a curl) walks straight in. So the announcement
    is blanked and the same write is issued again.

    Injection check (ran it, both directions):
      - remove the `refuse_virtual_join_columns` call from `crud.apply_batch_updates`:
        this test goes red, together with the 5 write-refusal tests in
        `test_virtual_join_executor.py`.
      - flip the announcement to `"editable": True` instead: this test stays GREEN and
        only `test_a_virtual_only_column_is_announced` goes red.
    That asymmetry IS the claim - the flag can be wrong without a write getting through.
    """
    _write_rules(monkeypatch, tmp_path, {"vjs_rule": _decl(["fab_site"])})
    body = {"updates": [{"business_key_val": "L1", "updates": {"fab_site": "typed"},
                         "source_name": "user", "updated_by": "tester"}]}

    res = client.put("/tables/vjs_test_log/data/updates", json=body)
    assert res.status_code == 400 and "fab_site" in res.json()["detail"]

    # Now the schema says nothing at all about the column.
    monkeypatch.setattr(vjx, "announced_columns", lambda db, table: [])
    assert _schema(client).json()["virtual_columns"] == []

    res = client.put("/tables/vjs_test_log/data/updates", json=body)
    assert res.status_code == 400, ("the refusal is the crud funnel's, not the schema's; "
                                    "a client that never read /schema is still refused")
    assert join_env.query(models.DYNAMIC_TABLES["vjs_test_log"]).count() == 0


def test_a_table_with_no_join_announces_an_empty_list(join_env, approved, client):
    """The key is always present, so a client never has to ask whether it exists."""
    body = _schema(client, "vjs_test_wafer").json()
    assert body["virtual_columns"] == []
    assert _schema(client).json()["virtual_columns"] == [], "no declaration file loaded"
