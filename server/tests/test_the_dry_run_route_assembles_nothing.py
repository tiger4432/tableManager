# -*- coding: utf-8 -*-
"""The chain dry-run route assembles nothing of its own.

⚰️ THIS FILE USED TO SCORE A DOCUMENT SEAM AS WELL (S-194 ①). `OntologyDraftStore` took a
`document=` so a second document could sit in one lifecycle; 판정 325 then put the chain
rule's door at the chain tab's raw route, `ChainRuleDocument` retired with S-205 having
never gained a product caller, and S-208 folded the layer left with one implementation.
Those tests went with it — 「테스트는 자기가 재던 코드와 같은 커밋에서 죽는다」 — and what
remains is the dry-run route, which was always a separate subject.

🔴 WHAT THE ROUTE MAY NOT DO. The defect would be a route that rebuilt the resolution, the
payload folding or the refusal text — then the CLI, the pytest fixture and this endpoint
become three answers to one question.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)


# ---------------------------------------------------------------------------
# the dry-run route
# ---------------------------------------------------------------------------

def test_the_dry_run_route_calls_the_bench_and_assembles_nothing():
    """⛔ SCORED ON THE SOURCE. The defect would be a route that rebuilt the resolution, the
    payload folding or the refusal text — then the CLI, the pytest fixture and this endpoint
    become three answers to one question."""
    import inspect

    import main

    body = inspect.getsource(main.chain_dry_run)
    assert "dev_bench.try_mapper(" in body
    for rebuilt in ("payloads_to_df", "MAPPER_REGISTRY", "open_readonly", "importlib"):
        assert rebuilt not in body, ("the route rebuilt %s" % rebuilt)


def test_the_dry_run_route_logs_no_row_body():
    """⛔ 「payload 본문 로그 금지」. The trigger row is operator data: it goes back to the caller
    who sent it, and the log carries the rule name, the count and whether it was refused."""
    import inspect

    import main

    log_lines = [l for l in inspect.getsource(main.chain_dry_run).splitlines()
                 if "logger." in l or "rows_in" in l]
    assert log_lines, "it must say something"
    for line in log_lines:
        assert "row" not in line or "rows_in" in line or "rows_out" in line, line
    assert "payload" not in " ".join(log_lines)


def test_the_dry_run_route_refuses_a_rule_naming_no_mapper():
    """⚠️ BOTH SPELLINGS ARE ACCEPTED, because the registry is empty wherever no mapper file
    uses the decorator yet — so a rule with neither is the only unrunnable case, and it is
    named rather than passed to the bench to fail there."""
    import chain_bindings

    assert chain_bindings.mapper_cells({"mapper": "m"})[0] == "m"
    assert chain_bindings.mapper_cells(
        {"mapper_module": "a", "mapper_function": "b"})[1:] == ("a", "b")
    assert chain_bindings.mapper_cells({}) == (None, None, None)
