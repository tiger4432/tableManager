# -*- coding: utf-8 -*-
"""[지시 0cae5199] 통합 문 하나가 평면 문에 없는 «두 가지»를 하고 있었다. 둘 다 여기서 잰다.

대응표(`derive.decide` ↔ 평면 인리치)에서 「없음」은 0 이었다 — 칸은 전부 대응된다. 남은 것은
「대응은 됐는데 «하는 일»이 다르다」였고, 원인은 한 줄이었다:

    평면  _validate_rule(name, raw, known_tables, rejections=..., caps=...)
    통합  _validate_rule(name, raw, known_tables)          <- 인자 «둘»이 빠진다

🔴 이 파일은 «시그니처를 안 잰다». 인자가 넘어가는지가 아니라 «결과가 남는지»를 잰다 —
   ㉠ 운영자 목록에 떨어진 뷰의 «이름»이 있나   ㉡ 설정 파일을 «몇 번» 여나.
   인자를 도로 빼면 둘 다 빨개진다(변이 증명). 그게 아니면 이 파일이 거짓이다.
"""
import json
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import enrich_declarations                                     # noqa: E402
from chain.enrichment import config as enrichment_config                   # noqa: E402

GOOD = {"label": "선 뷰", "query": "SELECT a FROM t WHERE k = :k ORDER BY a",
        "candidate_for": {"f": "a"}}
#: `:nope` 는 이 선언이 «바인드할 수 없는» 이름이다(판단키는 `k` 하나). 뷰가 떨어진다.
DROPS = {"label": "떨어질 뷰", "query": "SELECT a FROM t WHERE k = :nope",
         "candidate_for": {"f": "a"}}


def _unified(name, views):
    return {"name": name, "on": {"table": "rv_src"}, "into": {"table": "rv_derived"},
            "derive": {"kind": "decide",
                       "decide": {"key": ["k"], "fields": ["f"],
                                  "reference_views": list(views)}}}


def _flat(name, views):
    return {name: {"source_table": "rv_src", "derived_table": "rv_derived",
                   "decision_key": ["k"], "target_fields": ["f"],
                   "reference_views": list(views)}}


def _declare(tmp_path, unified=None, flat=None):
    chain_path = tmp_path / "chain_rules.json"
    chain_path.write_text(json.dumps({"rules": [unified] if unified else []}),
                          encoding="utf-8")
    enrich_path = tmp_path / "enrichment_rules.json"
    enrich_path.write_text(json.dumps(flat or {}), encoding="utf-8")
    rejections = []
    rules = enrich_declarations.declarations(
        chain_rules_path=str(chain_path), enrichment_path=str(enrich_path),
        rejections=rejections)
    return rules, rejections


# ---------------------------------------------------------------------------
# ㉠ 떨어진 뷰의 «이름»이 운영자에게 가나
# ---------------------------------------------------------------------------

def test_the_unified_door_names_the_view_that_fell(tmp_path):
    """🔴 「조용하다」가 아니라 «거칠다»였다. 규칙이 서고 뷰 하나만 떨어지면, 전에는 운영자가
    받는 목록에 «아무것도» 안 남았다 — 규칙은 섰으니 최상위 거절도 없다. 선언에는 뷰가 둘인데
    화면에는 하나가 나오고, 왜 하나가 없는지 말하는 자리가 없었다."""
    rules, rejections = _declare(tmp_path, unified=_unified("u", [GOOD, DROPS]))

    assert [r["name"] for r in rules] == ["u"], "규칙은 «서야» 한다 — 뷰 하나만 떨어진다"
    assert [v["label"] for v in rules[0]["reference_views"]] == ["선 뷰"]

    dropped = [r for r in rejections if "떨어질 뷰" in str(r.get("subject"))]
    assert dropped, (
        "떨어진 뷰의 «이름»이 운영자 목록에 없다 — 받은 것: %r" % (rejections,))
    assert dropped[0]["scope"] == "reference_view"
    assert "dropped" in dropped[0]["detail"]


def test_the_flat_door_says_the_same_thing_about_the_same_views(tmp_path):
    """⚠️ 대조군 — 이 줄이 이 파일의 «주어»를 고정한다. 두 문이 같은 선언에 같은 문장을 내야
    「문이 하나」가 참이다. 통합만 고치고 평면이 다른 말을 하면 그건 수리가 아니라 세 번째 답이다."""
    _rules, rejections = _declare(tmp_path, flat=_flat("f", [GOOD, DROPS]))

    dropped = [r for r in rejections if "떨어질 뷰" in str(r.get("subject"))]
    assert dropped, "평면 문이 뷰 이름을 안 낸다 — 대조군이 무너졌다: %r" % (rejections,)
    assert dropped[0]["scope"] == "reference_view"


# ---------------------------------------------------------------------------
# ㉡ 설정 파일을 «몇 번» 여나
# ---------------------------------------------------------------------------

def _count_settings_reads(monkeypatch):
    """`_load_ingestion_settings` 는 캐시가 «없다» — 부를 때마다 파일을 연다. 그래서 이 수가
    곧 「파일을 몇 번 열었나」이다."""
    calls = []
    real = enrichment_config._load_ingestion_settings

    def counting():
        calls.append(1)
        return real()

    monkeypatch.setattr(enrichment_config, "_load_ingestion_settings", counting)
    return calls


def _reads_for(tmp_path, monkeypatch, door, count):
    views = [dict(GOOD, label="뷰%d" % i) for i in range(count)]
    calls = _count_settings_reads(monkeypatch)
    rules, _rejections = _declare(tmp_path, **{door: (
        _unified("u", views) if door == "unified" else _flat("f", views))})
    assert len(rules[0]["reference_views"]) == count, "뷰가 다 서야 이 수가 뜻이 있다"
    return len(calls)


def test_the_caps_read_does_not_grow_with_the_number_of_views(tmp_path, monkeypatch):
    """🔴 [config.py 의 «자기» 금지] 「걷는 도중 설정을 다시 읽는 작업 단위는 두 뷰를 서로 다른
    상한으로 정규화할 수 있고, 그 어느 쪽도 파일이 말하는 것이 아니다」. `cap_value` 는 뷰마다
    «둘씩» 불리므로, 스냅샷이 없으면 뷰 N 개가 파일을 2N 번 연다.

    🔴 재는 것은 «수»가 아니라 «기울기»다. 박은 수로 적었다가 빨개졌고, 그게 맞았다 —
    이 좌석은 두 문을 «둘 다» 걷고 평면 로더도 자기 스냅샷을 하나 뜨므로 상수항이 1 더 있다.
    그 상수는 이 줄이 말하려는 것이 아니다. 「뷰를 늘려도 안 는다」가 성질이고, 상수는 자리다.

    ⚠️ 스냅샷은 «선언 단위»이지 작업 단위가 아니다 — 한 선언의 모든 뷰가 같은 상한을 쓴다는
    것까지가 이 줄이 잰다. 그 금지의 주어가 「두 뷰」이고 뷰는 선언 «안»에 산다."""
    few = _reads_for(tmp_path, monkeypatch, "unified", 1)
    many = _reads_for(tmp_path, monkeypatch, "unified", 5)

    assert few == many, (
        "뷰 1 개에 %d 번, 5 개에 %d 번 — 뷰마다 설정을 다시 읽고 있다" % (few, many))


def test_the_flat_door_does_not_grow_either(tmp_path, monkeypatch):
    """⚠️ 대조군. 평면은 «파일 하나»에 스냅샷 하나라 처음부터 안 늘었다. 두 문이 이 축에서
    갈라지지 않는다는 것을 같은 픽스처로 말한다 — 그리고 통합만 고쳐 놓고 평면이 다른 답을
    내면 그건 수리가 아니라 세 번째 답이라는 것을 여기서 안다."""
    few = _reads_for(tmp_path, monkeypatch, "flat", 1)
    many = _reads_for(tmp_path, monkeypatch, "flat", 5)

    assert few == many, "평면 문이 1 개에 %d 번, 5 개에 %d 번" % (few, many)
