"""로더가 «새 문법»을 실제로 읽는가 — 파일에서, 진짜 `load_chain_rules` 로 (S-234 2단계 ③).

🔴 왜 이 파일이 따로 있나. 2026-09-14 에 「칸은 있는데 읽는 쪽이 없다」로 하루를 썼고, 그 전날엔
하니스가 선언을 «직접 주입»해 초록인데 화면은 빈 폼이었다. 그러므로 새 문법의 증거는 어댑터
단위시험이 아니라 «파일에 적어 두고 로더가 읽는 것»이어야 한다.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chain import ingestion_worker as worker  # noqa: E402


@pytest.fixture()
def load(tmp_path, monkeypatch):
    """진짜 로더를 우리가 쓴 파일 위로 돌린다.

    ⛔ 합성 규칙은 «막는다» — 그것들은 이 박스의 라이브 enrichment 선언에서 오므로, 두면
    이 파일의 주어가 로더가 아니라 «박스의 설정»이 된다."""
    import mapper_sdk
    from chain import synthesis

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "unified_mapper",
                        lambda db, payloads, rule=None: {"updates": []})
    monkeypatch.setattr(synthesis, "synthesize_chain_rules", lambda **kwargs: [])

    def run(rules):
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        return {rule.get("name"): rule for rule in worker.load_chain_rules()}

    return run


OLD = {"name": "old_spelling", "trigger_table": "dt_log", "trigger_columns": ["b_wx"],
       "target_table": "dt_inventory", "mapper": "unified_mapper",
       "max_group_rows": 500}

NEW = {"name": "new_spelling",
       "on": {"table": "dt_log", "columns": ["b_wx"]},
       "derive": {"kind": "mapper", "mapper": {"mapper": "unified_mapper"}},
       "into": {"table": "dt_inventory"},
       "limits": {"max_group_rows": 500}}


def test_a_rule_written_in_the_new_grammar_is_loaded(load):
    """🔴 이것이 「읽는 쪽이 있다」의 정의다 — 파일에 적힌 새 모양이 «규칙으로 선다»."""
    loaded = load([NEW])

    assert "new_spelling" in loaded, "새 문법 규칙이 적재에서 사라졌다"
    rule = loaded["new_spelling"]
    assert rule["trigger_table"] == "dt_log"
    assert rule["target_table"] == "dt_inventory"
    assert rule["trigger_columns"] == ["b_wx"]
    assert rule["max_group_rows"] == 500


def test_the_two_spellings_load_to_the_same_rule(load):
    """🔴 통합의 «본문» — 같은 뜻을 두 문법으로 적으면 제품 안에서 «같은 것»이 되어야 한다.
    이름만 빼고 모든 칸이 같아야 하고, 다르면 그것이 번역의 결함이다."""
    loaded = load([OLD, NEW])
    assert set(loaded) == {"old_spelling", "new_spelling"}

    old = dict(loaded["old_spelling"]); old.pop("name")
    new = dict(loaded["new_spelling"]); new.pop("name")
    assert old == new, (old, new)


def test_an_old_rule_is_untouched_by_the_new_reader(load):
    """⚠️ 동작 0 의 단언. 새 문법을 «읽을 수 있게» 된 것이 옛 선언을 바꾸면 안 된다."""
    loaded = load([OLD])
    assert loaded["old_spelling"] == OLD


def test_a_cell_named_on_is_not_mistaken_for_the_new_grammar(load):
    """🔴 감지를 «넓히지 않은» 이유. `on` 이나 `into` 로 갈랐으면, 그 이름을 맵퍼 인자로
    쓰던 선언이 오늘부터 «다른 뜻»이 된다 — 2026-09-14 에 운영 선언을 삭제한 것과 같은 부류다."""
    odd = {"name": "has_on_cell", "trigger_table": "dt_log", "target_table": "dt_inventory",
           "mapper": "unified_mapper", "on": "이건 맵퍼가 읽는 값", "into": 7}
    loaded = load([odd])
    assert loaded["has_on_cell"] == odd
