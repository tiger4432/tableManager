# -*- coding: utf-8 -*-
"""S-143. A draft preview states what activating it would make re-run — 「소급이 비싸다」.

🔴 THE OWNER'S CORE CONSTRAINT IS THE COST OF CHANGE. 「운영에서는 소급이 매우 비싸기 때문에
원장 선언도 매우 신중해야 하고 … 이것을 싸게 만드는 게 기술이고 운영의 핵심」. The counting
machinery all existed — six retroactive ops, each with its own dry-run — and nothing asked it
from a DECLARATION change, which is the moment an operator is deciding.

🔴 `count` IS THE COUNTER'S ANSWER VERBATIM (판정 323). Not picked, not renamed, extra keys
carried. `/admin/retroactive/{op}/count` already taught the screen these names, and a second
spelling here would make one number answer to two.

⚠️ AND A WORD IS NOT COUNTED ON PURPOSE. A word's sources are the running sources whose cursor
stamp the draft moves (총괄 03bc94b6b); counting them is one dry-run PER SOURCE on a request path.
The sources are named and `absence` says so, because 「cannot be counted」 sends an operator nowhere
while 「not counted here」 tells them the count is still on the retroactive route.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from admin import retroactive                                                    # noqa: E402
from ledger import config_drafts                                      # noqa: E402

#: What the counter would answer. 🔴 A SENTINEL OBJECT, so "verbatim" can be asserted by
#: IDENTITY - a test comparing field by field would pass on a copy that renamed nothing today
#: and something tomorrow.
@pytest.fixture(autouse=True)
def _shipped_declaration(monkeypatch, tmp_path_factory):
    """The repository's declaration and catalogue, not the box's gitignored files - a fresh checkout has none (총괄 10-14)."""
    from tests.support.declaration import use_committed_declaration

    use_committed_declaration(monkeypatch, tmp_path_factory.mktemp("shipped"))


COUNTER_ANSWER = {"op": "ledger_backfill", "affected": 1234,
                  "affected_label": "아직 번역되지 않은 행", "absence": None,
                  "scan_limit": None, "blocked_reason": None,
                  "a_key_this_test_never_heard_of": "rides along"}


def _node(kind, canonical_id):
    return SimpleNamespace(kind=kind, canonical_id=canonical_id)


def _setup(cfg, vocabulary=None):
    return SimpleNamespace(bundle=SimpleNamespace(to_mapping=lambda: cfg),
                           snapshot=SimpleNamespace(vocabulary=vocabulary or {}))


CFG = {"sources": {
    "s_utters": {"bind": {"mappings": {"m": {"predicate": "measures@1", "bind": {}}}}},
    "s_quiet": {"bind": {"mappings": {}}},
}}


# ---------------------------------------------------------------------------
# nobody asked
# ---------------------------------------------------------------------------

def test_without_a_session_there_is_no_cost_and_that_is_not_a_zero():
    """⛔ `None` MEANS THE QUESTION WAS NOT ASKED. A CLI or a test builds a preview with no
    request behind it; answering 「nothing re-runs」 there would be a statement nobody made."""
    assert config_drafts._redo_for(_setup(CFG), _node("source_plan", "s_utters"), None, None) is None


def test_the_existing_callers_still_get_a_preview_without_one():
    """⚠️ THE SIZE OF THE CONTRACT CHANGE. A cost is a question only a REQUEST asks, so every
    other caller — the CLI, the tests — passes no session and still gets a preview; `redo` is
    simply `None` for them.

    ⚰️ THIS USED TO ASSERT ON `DraftContext.db`, which S-208 folded away with the document
    seam. The fact it was really pinning is the one below and it is unchanged: the seat that
    takes the session takes it OPTIONALLY."""
    import inspect

    signature = inspect.signature(config_drafts.OntologyDraftStore.preview)

    assert signature.parameters["db"].default is None


# ---------------------------------------------------------------------------
# 🔴 one source: the counter's answer, verbatim
# ---------------------------------------------------------------------------

def test_a_source_node_carries_the_counters_answer_unchanged(monkeypatch):
    """🔴 ASSERTED BY IDENTITY. `redo["count"]` must BE what the counter returned - a test
    that compared chosen fields would stay green on the day somebody renamed one."""
    seen = {}

    def fake_count(db, op, params, **kw):
        seen.update(db=db, op=op, params=params)
        return COUNTER_ANSWER

    monkeypatch.setattr(retroactive, "count", fake_count)
    redo = config_drafts._redo_for(_setup(CFG), _node("source_plan", "dt_transfer"), "SESSION", None)

    assert redo["count"] is COUNTER_ANSWER
    assert redo["op"] == "ledger_backfill"
    assert redo["params"] == {"source": "dt_transfer"}
    assert redo["sources"] == ["dt_transfer"]
    assert seen == {"db": "SESSION", "op": "ledger_backfill",
                    "params": {"source": "dt_transfer"}}


def test_the_op_is_the_whole_source_one_and_not_the_scoped_one(monkeypatch):
    """🔴 `ledger_rescope` NEEDS A SCOPE COLUMN AND VALUES, and a declaration edit has none -
    it changes what the source means for every row it reads. Measured before wiring (판정 320);
    the first ruling named the scoped counter and it could not have been called."""
    monkeypatch.setattr(retroactive, "count", lambda db, op, params, **kw: {"op": op})
    redo = config_drafts._redo_for(_setup(CFG), _node("source_plan", "x"), "SESSION", None)
    assert redo["op"] == "ledger_backfill"
    assert "scope_column" not in redo["params"]


# ---------------------------------------------------------------------------
# 🔴 a word: the sources whose cursor stamp the draft moves, named, not counted (총괄 03bc94b6b)
# ---------------------------------------------------------------------------

SAMPLE = os.path.join(server_dir, "config", "sample")


@pytest.fixture(scope="module")
def sample_setup():
    """The shipped sample, loaded the way the explorer loads its root - never the box's."""
    from ledger import setup_bundle
    from ledger.setup import load_setup

    catalog = setup_bundle.load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    root = tempfile.mkdtemp(prefix="redo_")
    try:
        shutil.copy(os.path.join(SAMPLE, "ledger_config.json.sample"),
                    os.path.join(root, "ledger_config.json"))
        yield load_setup(root, catalog=catalog)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _word_redo(setup, key, edit, monkeypatch):
    """The cost a real preview states for this draft; counting a word is the drift gate."""
    from ledger.config_explorer import build_explorer_index

    monkeypatch.setattr(retroactive, "count", lambda *a, **k: pytest.fail("a word is not counted"))
    node = build_explorer_index(setup).nodes[key]
    preview = config_drafts.compile_draft_preview(
        setup, node, edit(copy.deepcopy(dict(node.raw))), db="SESSION")
    assert preview.valid, preview.errors
    return preview.redo


def test_a_label_only_draft_re_runs_no_source(sample_setup, monkeypatch):
    """A label is compiled into no source's material: nothing re-runs, truly none."""
    running = {s for s, plan in sample_setup.snapshot.source_plans.items() if plan.runs}
    assert "die_inspection" in running                     # canary: a running source says `die`
    redo = _word_redo(sample_setup, "entity|die",
                      lambda raw: dict(raw, label=["mat_id", "x"]), monkeypatch)
    assert redo == {"op": None, "params": None, "sources": [],
                    "count": {"absence": retroactive.ABSENCE_TRULY_NONE}}


def test_a_draft_that_reorders_the_keys_names_the_sources_it_moves(sample_setup, monkeypatch):
    redo = _word_redo(sample_setup, "entity|die",
                      lambda raw: dict(raw, keys=list(reversed(raw["keys"]))), monkeypatch)
    assert redo == {"op": None, "params": None,
                    "sources": ["die_inspection", "transfer_event"],
                    "count": {"absence": retroactive.ABSENCE_NOT_COUNTED_HERE}}


def test_an_inverse_only_predicate_draft_re_runs_no_source(sample_setup, monkeypatch):
    """`inverse_of` is walk-only, like a label (WALK.md): the sources uttering it stay put."""
    redo = _word_redo(sample_setup, "predicate|inspected",
                      lambda raw: dict(raw, inverse_of="in_container@1"), monkeypatch)
    assert redo["sources"] == []
    assert redo["count"] == {"absence": retroactive.ABSENCE_TRULY_NONE}


def test_the_absence_word_lives_in_the_counters_vocabulary():
    """⚠️ ONE PLACE FOR THE CLIENT TO LEARN IT. A word invented beside the report would be a
    second vocabulary for the same idea."""
    assert retroactive.ABSENCE_NOT_COUNTED_HERE in retroactive.ABSENCE_WORDS
    assert retroactive.ABSENCE_TRULY_NONE in retroactive.ABSENCE_WORDS


# ---------------------------------------------------------------------------
# the shape is one shape
# ---------------------------------------------------------------------------

def test_the_outer_keys_are_the_same_four_for_a_source_and_a_word(sample_setup, monkeypatch):
    """🔴 A FIXED KEY SET IS WHY THIS IS NOT 「두 상태 한 응답」. That defect comes from mixing
    key-absent, value-null and value-zero; fixing the keys removes the mix, and the difference
    lives in `count` where a reader already knows to look. ⛔ `absence` sits in `count` only
    (판정 323) - an outer copy would let the two disagree."""
    word = _word_redo(sample_setup, "entity|die",
                      lambda raw: dict(raw, keys=list(reversed(raw["keys"]))), monkeypatch)
    monkeypatch.setattr(retroactive, "count", lambda *a, **k: COUNTER_ANSWER)
    source = config_drafts._redo_for(_setup(CFG), _node("source_plan", "s"), "SESSION", None)
    assert set(word) == set(source) == {"op", "params", "sources", "count"}


# ---------------------------------------------------------------------------
# 🔴 the route, actually called
# ---------------------------------------------------------------------------

def test_the_view_route_takes_the_request_session_and_opens_no_second_one():
    """🔴 THE SEAT, SCORED WHERE IT LIVES. `redo` is only ever filled when a REQUEST asks, so
    the route has to hand its own Session down - and it must be the one FastAPI already holds
    (`Depends(get_db)`), never a connection opened here. A second connection on a preview
    path is the quiet cost 「성능 마진 넉넉하게」 forbids."""
    import inspect

    from ledger_api import ontology_config_explorer_router as router

    source = inspect.getsource(router.explorer_view)
    assert "Depends(get_db)" in source
    assert "db=db" in source, "the session must reach the service"
    for opened in ("create_engine", "open_readonly", "sessionmaker"):
        assert opened not in source, opened


def test_the_route_still_answers_after_gaining_the_dependency(client, monkeypatch):
    """⚠️ CALLED FOR REAL, not asserted about. Adding `Depends(get_db)` to a handler is
    exactly the change that 422s every request when it goes wrong - a decorator binding to
    the wrong callable, a parameter read as a required query field - and none of that shows
    up in a source assertion.

    ⚠️ THE TOKEN HALF IS NOT ASSERTED HERE. `test_admin_auth.py` parametrises over EVERY
    gated `/admin/*` route, so a second copy would be a second answer to 「is this route
    gated」 - and the one that drifts is the copy. Measured while writing this: the route
    answers 200 unauthenticated in a test env with no token configured, which is that
    suite's contract and not this one's to restate.
    """
    import paths
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger_api import ontology_config_explorer_router as explorer_router

    # the router's default explorer was built at import, on the box's root - this test's is the shipped one
    monkeypatch.setitem(explorer_router._services, None,
                        OntologyExplorerService(config_root=paths.config_path("ontology")))
    answer = client.get("/admin/ontology-explorer/view")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert "snapshot_hash" in body, "the handler ran rather than being refused by FastAPI"


# ---------------------------------------------------------------------------
# 🔴 S-143 correction — the number has to REACH somebody
# ---------------------------------------------------------------------------

def _copied_ontology(tmp_path):
    """A private copy of the ontology root (the shipped one, `_shipped_declaration`).

    ⛔ NEVER THE LIVE ONE. A draft written into the owner's config directory is the
    「내 시험이 소유자의 파일에 썼다」 failure, and this test creates one.
    """
    import shutil

    import paths

    target = tmp_path / "ontology"
    shutil.copytree(paths.config_path("ontology"), target)
    return target


def test_the_cost_reaches_the_wire_rather_than_being_computed_and_dropped(tmp_path,
                                                                         monkeypatch):
    """🔴 S-143 LANDED A NUMBER NOBODY COULD READ — 「착지는 배선이 아니다」.

    `public()` is a whitelist over the draft RECORD and `redo` is not a record field: it is
    a fact about the session THIS request carries. So the only seat that can put it on the
    wire is the one holding both the preview and the db, and it did not. Measured before
    this test existed: `redo` appeared exactly once outside the tests — the dataclass field
    that declares it.

    ⚠️ ASSERTED BY IDENTITY, for the same reason the counter's answer is: a test comparing
    fields would stay green on a seat that rebuilt the mapping and dropped a key.
    """
    from ledger.config_drafts import DraftPreview
    from ledger.config_explorer_service import OntologyExplorerService

    service = OntologyExplorerService(
        config_root=_copied_ontology(tmp_path), draft_root=tmp_path / "drafts")
    _setup, index, *_rest = service.active()
    key = next(name for name, node in index.nodes.items()
               if node.config_file == "ledger_config.json")
    draft = service.create_draft(target_key=key, base_snapshot_hash=index.snapshot_hash)

    cost = {"op": "ledger_backfill", "params": {"source": "s"}, "sources": ["s"],
            "count": {"affected": 7}}
    monkeypatch.setattr(service.draft_store, "preview",
                        lambda *a, **k: DraftPreview(True, None, None, (), cost))

    payload = service.view(draft_id=draft["draft_id"], db="SESSION")
    assert payload["draft"]["redo"] is cost


def test_a_view_with_no_draft_carries_no_cost_key_at_all(tmp_path):
    """⚠️ THE KEY BELONGS TO A DRAFT, NOT TO THE SCREEN. With no draft open there is no
    text whose activation could cost anything, and `payload["draft"]` is `None` — inventing
    a null cost beside it would be a third empty for a reader to tell apart."""
    from ledger.config_explorer_service import OntologyExplorerService

    service = OntologyExplorerService(
        config_root=_copied_ontology(tmp_path), draft_root=tmp_path / "drafts")
    assert service.view(db="SESSION")["draft"] is None


# ---------------------------------------------------------------------------
# 🔴 a source the counter's declaration does not hold (owner 10-12)
# ---------------------------------------------------------------------------

FOUR = ["physical_object", "physical_process", "physical_quantity", "defect_kind"]


def _modeling_world(tmp_path, monkeypatch):
    """The owner's modeling declaration over a private config dir (the counter reads worlds
    through `paths`): the operating world's file without the source, and the source."""
    import paths

    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        ledger = json.load(fh)
    with open(os.path.join(SAMPLE, "table_config.json.sample"), encoding="utf-8") as fh:
        tables = json.load(fh)
    ledger["entities"].pop("defect_kind@1")
    ledger["entities"].update({name: {"keys": [name], "class": "static"} for name in FOUR})
    ledger["vocabulary"].pop("leads_to@1")
    ledger["vocabulary"]["leads_to"] = {"status": "active", "subjects": FOUR, "object": {
        "kind": "entity_ref", "types": FOUR,
        "qualifiers": {"required": [], "optional": ["certainty", "dir"]}}}
    columns = ["candidate_id", "cause_type", "cause_key", "phenomenon_type", "phenomenon_key",
               "certainty", "dir", "confirmed"]
    tables["link_candidates"] = {"business_key": "candidate_id",
                                 "column_types": {name: "string" for name in columns}}
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(ledger), encoding="utf-8")
    (config / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))

    def role(type_column, key_column):
        return {"kind": "entity", "entity_type": {"kind": "column", "column": type_column},
                "keys": {name: {"kind": "column", "column": key_column} for name in FOUR}}

    source = {"relation": "link_candidates",
              "read": {"unit": "row", "identity": ["row_id"], "order_by": ["row_id"],
                       "occurred_at": {"basis": "ingested", "timezone": "Asia/Seoul"},
                       "exclude_when": [{"column": "confirmed", "blank": True}]},
              "map": {"implementation_id": "declarative-role", "implementation_version": 1,
                      "unit": {"kind": "row"}},
              "bind": {"mappings": {"leads": {"predicate": "leads_to", "bind": {
                  "subject": role("cause_type", "cause_key"),
                  "target": role("phenomenon_type", "phenomenon_key"),
                  "certainty": {"kind": "column", "column": "certainty"},
                  "dir": {"kind": "column", "column": "dir"}}}}}}
    return config, ledger, source


def _explorer_client(session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from admin.auth import require_admin_token, require_admin_token_strict
    from database.database import get_db
    from ledger_api import ontology_config_explorer_router as explorer_router

    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[require_admin_token_strict] = lambda: None
    app.dependency_overrides[get_db] = lambda: session
    app.include_router(explorer_router.router)
    return TestClient(app)


def test_a_draft_of_a_source_the_active_file_lacks_opens_with_the_counters_refusal(
        tmp_path, monkeypatch):
    """The owner's modeling declaration, authored as a new source: the counter's judge refused
    it and `/view` answered 500 for the whole window. A non-unique order_by never got there -
    the draft failed validation first - which is why only a unique identity broke."""
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger_api import ontology_config_explorer_router as explorer_router

    config, _ledger, source = _modeling_world(tmp_path, monkeypatch)
    explorer_router.configure_service(OntologyExplorerService(
        config_root=config / "ontology", draft_root=tmp_path / "drafts"))
    client = _explorer_client(SimpleNamespace(
        get_bind=lambda: pytest.fail("the judge refuses before any read"), rollback=lambda: None))

    base = client.get("/admin/ontology-explorer/view").json()["snapshot_hash"]
    draft = client.post("/admin/ontology-explorer/drafts/new", json={
        "kind": "source_plan", "canonical_id": "link_candidates",
        "base_snapshot_hash": base}).json()
    saved = client.put(f"/admin/ontology-explorer/drafts/{draft['draft_id']}", json={
        "expected_revision": 0, "raw": json.dumps(source)})
    assert saved.json()["validation_errors"] == []                # canary: the draft compiles
    opened = client.get("/admin/ontology-explorer/view", params={
        "draft_id": draft["draft_id"], "revision": 1, "view_mode": "draft_preview"})

    assert opened.status_code == 200, opened.text
    count = opened.json()["draft"]["redo"]["count"]
    assert count["absence"] == retroactive.ABSENCE_NOT_APPLICABLE
    assert "link_candidates" in count["detail"]


def test_a_branch_draft_is_counted_in_the_branch(tmp_path, monkeypatch):
    """A source only a branch declares: its draft's redo count reads the BRANCH's declaration
    and row index. Asked with no world, the counter read the operating world's - refused there,
    or, with a same-named source, the operating world's rows shown as the branch's cost."""
    from ledger import backfill
    from ledger_api import ontology_config_explorer_router as explorer_router

    config, ledger, source = _modeling_world(tmp_path, monkeypatch)
    branch = config / "ontology_worlds" / "modeling"
    branch.mkdir(parents=True)
    ledger["sources"]["link_candidates"] = source
    (branch / "ledger_config.json").write_text(json.dumps(ledger), encoding="utf-8")
    monkeypatch.setattr(explorer_router, "_services", {})    # each world's explorer, made fresh
    asked = []

    def census(engine, setup, source_id, *, exact_rows=True, world=None):
        asked.append((world, source_id in setup.snapshot.source_plans))
        return {"relation_rows": 7, "indexed_rows": 0, "counts": "rows"}

    monkeypatch.setattr(backfill, "rows_not_yet_translated", census)
    monkeypatch.setattr(backfill, "rows_to_catch_up", lambda *a, **k: {
        "rows_new": 7, "rows_drifted": 0, "rows_gone": 0, "rows_unprinted": 0})
    client = _explorer_client(SimpleNamespace(get_bind=lambda: "ENGINE", rollback=lambda: None))

    base = client.get("/admin/ontology-explorer/view", params={"world": "modeling"}).json()
    draft = client.post("/admin/ontology-explorer/drafts", params={"world": "modeling"}, json={
        "target_key": "source_plan|link_candidates",
        "base_snapshot_hash": base["snapshot_hash"]}).json()
    opened = client.get("/admin/ontology-explorer/view", params={
        "world": "modeling", "draft_id": draft["draft_id"], "revision": 0,
        "view_mode": "draft_preview"})

    assert opened.status_code == 200, opened.text
    redo = opened.json()["draft"]["redo"]
    assert redo["params"] == {"source": "link_candidates", "world": "modeling"}
    assert asked == [("modeling", True)]
    assert redo["count"]["affected"] == 7
