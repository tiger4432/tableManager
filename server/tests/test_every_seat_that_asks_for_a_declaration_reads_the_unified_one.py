# -*- coding: utf-8 -*-
"""판정 636 (소유자 컨펌) — 「선언을 «묻는» 자리」를 한 좌석으로.

> 소유자: 「너의 목표는 기존 선언들 «없이도» 파생·자동 확정이 서게 하는 것.
>          이 박스는 단순 실험체에 불과해」

🔴 THE FIXTURE REMOVES THE FLAT FILE. Every row below runs with
`ENRICHMENT_RULES_PATH` pointing at an EMPTY document and one `derive.decide` declaration in
`chain_rules.json`. That is the whole question: before 636 each of these seats opened the
flat file and only the flat file, so a declaration written in the unified grammar was stood
by the loader, ran, wrote rows - and was invisible to every screen that asked about it.

⚠️ THE ROWS ARE THE SEATS, NOT THE SEAT. Asserting `enrich_declarations.find` works would be
vacuous here: that is its own file's job
(`test_a_reference_view_is_reachable_whichever_grammar_declared_it.py`, whose control group -
「the old lookup still cannot see the unified one」 - is what proves this seat is the reason).
What this file asks is whether each CALLER reaches it, and it asks by running the caller.

⚠️ AND THE FOUR ROUTES ARE ASKED THE WAY A ROUTE CAN BE ASKED WITHOUT AN APP. Each is called
with a spy in the seat's place; the row asserts THE SPY WAS CALLED WITH THE RULE NAME, which
is a run-time fact, and then lets the route fail on the database work that follows. It is not
`inspect.getsource` - 判 636 asks for 「돈다」 and a source match would answer 「간다」.
"""
import io
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import enrich_declarations                                # noqa: E402
from chain import graph as chain_graph                               # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402
from chain.enrichment import config as enrichment_config             # noqa: E402
from database import crud                                            # noqa: E402

NAME = "s636_unified_only"
SRC = "s636_src"
DST = "s636_derived"

UNIFIED = {
    "name": NAME,
    "on": {"table": SRC},
    "into": {"table": DST},
    "derive": {"kind": "decide", "decide": {
        "key": ["job"], "fields": ["grade"], "auto_confirm": True,
        # ⚠️ `alignment` 은 정렬 자리가 «찾은 뒤» 묻는 둘째 검사다. 없으면 그 자리는
        #    「찾았지만 정렬 규칙이 아니다」로 거절하고, 그 행은 조회를 못 잰다.
        "alignment": True,
        "reference_views": [{
            "label": "후보",
            "query": "SELECT lot AS grade FROM %s WHERE job = :job" % DST,
            "candidate_for": {"grade": "grade"}}]}},
}

TABLES = {
    SRC: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string"}, "display_columns": ["job"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "grade": "string"},
          "display_columns": ["job", "lot", "grade"]},
}


@pytest.fixture(name="unified_only")
def fixture_unified_only(tmp_path, monkeypatch):
    """평면 파일은 «비었고», 통합 선언 하나가 서 있다."""
    flat = tmp_path / "enrichment_rules.json"
    flat.write_text(json.dumps({}), encoding="utf-8")
    chain_file = tmp_path / "chain_rules.json"
    chain_file.write_text(json.dumps({"rules": [UNIFIED]}), encoding="utf-8")

    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(flat))
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))
    # 로더 메모는 «경로»로 키가 잡히지만, 같은 tmp 경로가 재사용될 수 있어 비운다
    enrichment_config._RULES_MEMO.clear()
    crud.TABLE_CONFIG.update(TABLES)
    try:
        yield
    finally:
        enrichment_config._RULES_MEMO.clear()
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _spy(monkeypatch):
    """좌석의 `find` 자리에 두는 염탐꾼 — «불렸나»가 이 행의 단언이다."""
    seen = []

    def fake_find(rule_name, **kwargs):
        seen.append(rule_name)
        return enrich_declarations.declarations(**kwargs) and next(
            (r for r in enrich_declarations.declarations(**kwargs)
             if r.get("name") == rule_name), None)

    monkeypatch.setattr(enrich_declarations, "find", fake_find)
    return seen


# ---------------------------------------------------------------------------
# ⓐ 좌석이 그 선언을 «세운다» — 나머지 행이 공허하지 않기 위한 전제
# ---------------------------------------------------------------------------

def test_the_declaration_stands_with_no_flat_file_at_all(unified_only):
    """🔴 이 행이 빨개지면 아래 전부가 «측정되지 않은 채» 초록이 된다."""
    stood = enrich_declarations.declarations(known_tables=crud.TABLE_CONFIG)

    assert [r["name"] for r in stood] == [NAME]
    assert enrichment_config.load_enrichment_rules(
        known_tables=crud.TABLE_CONFIG) == [], "평면 파일은 «비어» 있어야 한다"


# ---------------------------------------------------------------------------
# ⓑ 「이 이름의 선언을 다오」 — 부를 수 있는 자리는 «불러서» 잰다
# ---------------------------------------------------------------------------

def test_the_alignment_view_service_finds_it_and_does_not_refuse(unified_only):
    import alignment_view_service as avs

    decl = avs.declared_alignment_rule(NAME)

    assert decl["name"] == NAME
    with pytest.raises(avs.AlignmentViewRequestError):
        avs.declared_alignment_rule("nothing_declares_this")


def test_retroactive_takes_it_as_a_target(unified_only):
    from admin import retroactive

    rule = retroactive._enrichment_rule(NAME)

    assert rule["name"] == NAME


def test_retroactives_refusal_lists_what_it_can_actually_see(unified_only):
    """⚠️ 「없다」와 「무엇이 있나」가 «같은 목록»에서 나와야 한다. 한쪽만 넓히면 거절
    문구가 자기가 안 본 것을 근거로 「없다」고 말한다."""
    from admin import retroactive

    with pytest.raises(retroactive.RetroactiveRefused) as refusal:
        retroactive._enrichment_rule("nothing_declares_this")

    assert NAME in str(refusal.value), str(refusal.value)


@pytest.mark.parametrize("entry,kwargs", [
    ("apply_enrichment_queue_predicate",
     {"query": None, "table_model": None, "table_name": DST,
      "rule_name": NAME, "scope": None}),
    ("get_map_alignment_worklist",
     {"rule": NAME, "map_table": None, "params": None, "q": None,
      "sort": None, "order": None, "limit": 1, "offset": 0, "db": None}),
    ("get_enrichment_auto_confirm_dry_run", {"rule": NAME, "limit": 1, "db": None}),
    ("get_enrichment_reference",
     {"rule_name": NAME, "index": 0, "params": None, "db": None}),
])
def test_a_route_that_asks_by_name_reaches_the_seat(unified_only, monkeypatch,
                                                    entry, kwargs):
    """🔴 「돈다」로 잰다 — 염탐꾼이 «호출됐나»가 런타임 사실이다. 그 뒤 라우트가 DB 일에서
    죽는 것은 이 행의 주제가 아니라서 삼킨다."""
    import main

    seen = _spy(monkeypatch)
    try:
        getattr(main, entry)(**kwargs)
    except Exception:                                                  # noqa: BLE001
        pass

    assert seen == [NAME], "%s: 좌석에 이름이 안 닿았습니다 (%s)" % (entry, seen)


def test_the_alignment_confirm_route_reaches_the_seat(unified_only, monkeypatch):
    """확정 요청은 payload 를 받으므로 한 행을 따로 쓴다."""
    import main

    seen = _spy(monkeypatch)
    try:
        main.confirm_map_alignment({"rule": NAME}, None)
    except Exception:                                                  # noqa: BLE001
        pass

    assert NAME in seen, seen


# ---------------------------------------------------------------------------
# ⓒ 「선언 전부를 다오」
# ---------------------------------------------------------------------------

def test_the_candidate_prober_builds_itself_from_the_unified_declaration(unified_only):
    """폴백 — `rules=None` 로 지어도 «켜져» 있어야 한다. 평면 파일이 비었으므로, 켜져
    있다는 것은 통합 선언을 봤다는 뜻 말고는 설명이 없다."""
    from chain.enrichment import candidates

    collector = candidates.AutoConfirmCollector(DST, rules=None)

    assert collector.active, "통합 선언만 있는 표에서 자동확정이 꺼져 보입니다"


def test_the_graph_draws_it(unified_only, monkeypatch):
    seen = {}

    def fake_quarter(name, load, counts, unread, catalogue):
        rows = load([])
        seen[name] = [r.get("name") for r in rows or []]
        return rows or []

    monkeypatch.setattr(chain_graph, "_quarter", fake_quarter)
    try:
        chain_graph.chain_graph(None)
    except Exception:                                                  # noqa: BLE001
        pass

    assert NAME in (seen.get("enrichment_rules") or []), seen


def test_the_resolve_report_counts_it(unified_only):
    """🔴 «돌려서» 잰다 — 보고의 인리치 절을 실제로 지어 그 이름이 «세어졌나»를 본다.
    종전 이 행은 소스에 좌석 이름이 있나를 봤고, 그건 636 이 금지한 「간다」였다."""
    import config_resolve_report as report

    section = report._resolve_enrichment()

    names = json.dumps(section, ensure_ascii=False, default=str)
    assert NAME in names, "보고의 인리치 절에 통합 선언이 안 나옵니다: %s" % names[:300]


# ---------------------------------------------------------------------------
# 🔴 ⓓ 대조군 — 새 자리가 «조용히» 평면 파일로 돌아가지 못한다
# ---------------------------------------------------------------------------

def test_no_seat_outside_the_two_allowed_reads_the_flat_file():
    """⚰️ 이 라운드 «전»에는 13 자리가 평면 파일을 직접 열었습니다. 남아도 되는 것은 둘뿐:
    좌석 자신(평면 반쪽을 부른다)과 체인 로더의 합성 반쪽(`load_enrichment_chain_rules`).
    셋째가 생기면 그것이 「옆에 또 만든」 자리입니다."""
    import ast
    import subprocess

    files = [p for p in subprocess.check_output(
        ["git", "ls-files", "*.py"], text=True, cwd=SERVER_DIR).split()
        if not p.startswith("tests/") and os.path.exists(os.path.join(SERVER_DIR, p))]

    callers = set()
    for rel in files:
        tree = ast.parse(io.open(os.path.join(SERVER_DIR, rel), encoding="utf-8").read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", getattr(node.func, "id", None))
                    == "load_enrichment_rules"):
                callers.add(rel)

    assert callers == {"chain/enrich_declarations.py", "chain/enrichment/config.py"}, (
        "평면 파일을 직접 여는 자리: %s — 좌석(chain/enrich_declarations)을 지나게 "
        "하거나, 왜 지날 수 없는지를 그 자리에 적으십시오" % sorted(callers))
