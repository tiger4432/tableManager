# -*- coding: utf-8 -*-
"""A rule that ran must say so, in one vocabulary, whichever way it names its code.

Owner, 2026-09-04: 「진짜 맵퍼 함수가 돌 때 로그 띄워줘 확인하게」. What was behind the
request is the day he had just lost: he put a `print` inside a mapper, watched the server
log, saw nothing, and read that as "the mapper did not run". It had run. Mappers execute
in the CHAIN WORKER process, whose lines go to `chain_worker.log`, and the server log he
was reading belongs to a different process entirely.

⚰️ [판정 498 ③] AND THE ANSWER USED TO BE SPELLED TWICE. A file mapper's run said
START / END / RAISED under `[mapper@<logfile>]` with `rows_out=`; a `builtin:` kind's run said
one `[ChainRule]` line with `written=` and NOTHING at all when it threw. Same event, two
vocabularies, and an operator grepping 「did this rule run」 had to know which kind of rule it
was before they could choose the words. There is one line now, and this file scores it.

🔴 WHAT FOLDING THEM WAS NOT ALLOWED TO COST. Two things the mapper tag did:
  ① it distinguished a throw from `rows_out=0` — kept, as the `error=` cell (the seat logs in
    `finally`, so a rule that threw still speaks);
  ② it counted the shape that answers in `batches` rather than `updates` — kept, because the
    line prints what `run.produced` was told, which is the one counting function.
The third thing — naming the log FILE — is deliberately NOT here, and it is not a loss: a tag
inside a file 「is only visible to somebody who already opened the right file - it cannot help
you choose one」 (`test_queue_says_which_log_to_open.py`, whose subject is the durable answer:
`GET /admin/chain/queue` publishes `log_filename` read off the live logger).

⛔ AND THE LINE MUST NOT CARRY THE PAYLOAD. Group sizes and names are safe to log;
operator row content is not, and a log that quietly becomes a data export is a different
incident. Asserted with a value that would be unmistakable if it leaked.
"""
import logging
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                          # noqa: E402
from chain import rule_run                                            # noqa: E402

RULE = {"name": "some_rule", "target_table": "some_target"}
SECRET = "PAYLOAD-BODY-MUST-NOT-BE-LOGGED"


def install(monkeypatch, fn, name="fake_mapper_module"):
    """A real importable module, so the seat takes its own import path.

    The seat resolves a rule's mapper with `importlib.import_module` and `getattr`; handing
    it a module through `sys.modules` exercises that resolution instead of replacing it.
    """
    module = types.ModuleType(name)
    module.run = fn
    monkeypatch.setitem(sys.modules, name, module)
    return name, "run"


def _rule(module_name, function_name, **kw):
    out = dict(RULE, mapper_module=module_name, mapper_function=function_name)
    out.update(kw)
    return out


def payloads(n=3):
    return [{"row_id": "r%d" % i, "data": {"col": {"value": SECRET}}} for i in range(n)]


def lines(caplog):
    """Every line the ONE vocabulary wrote. ⚠️ There is no `marker` argument any more -
    START/END/RAISED were the second vocabulary, and a helper that still took one would quietly
    read `[]` for every case and pass whatever asserted absence."""
    tag = "[%s]" % rule_run.RULE_LOG_TAG
    return [r.getMessage() for r in caplog.records if tag in r.getMessage()]


# ------------------------------------------------------------------ it ran, and it said so

def test_a_rule_that_runs_logs_exactly_one_line(monkeypatch, caplog):
    mod, fn = install(monkeypatch, lambda db, p: {"updates": [{"updates": {"a": 1}}]})
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, _rule(mod, fn, is_batch=True), payloads=payloads(3))

    said = lines(caplog)
    assert len(said) == 1, "one line per group, not per row and not one per stage"
    assert "some_rule" in said[0] and "some_target" in said[0] and mod in said[0]
    assert "rows_in=3" in said[0]
    assert "rows_out=1" in said[0]
    assert "elapsed=" in said[0]


def test_the_line_names_the_code_it_ran_whichever_way_the_rule_named_it(monkeypatch, caplog):
    """🔴 ONE CELL, TWO SPELLINGS OF ONE FACT. `kind=` carries a module.function for a file
    mapper and `builtin:<kind>` for a registered kind - the same cell either way, so 「which of
    my rules is this」 is readable off one column instead of inferred from which words the line
    happens to use."""
    import mapper_sdk

    mod, fn = install(monkeypatch, lambda db, p: {"updates": []})
    # ⚰️ [판정 562 · 509] FAKING A KIND USED TO MEAN THREE TABLES - the body, how it is
    #   called, and whether it writes for itself. There is one registry and one convention,
    #   so it means putting a callable under a name; 「writes for itself」 is no longer asked
    #   in advance - the mapper says it in `written`, which this stub does.
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "declared:s498_log_probe",
                        lambda db, payload, rule=None: {"written": 2})
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, _rule(mod, fn, is_batch=True), payloads=payloads(1))
        # ⚠️ `is_batch` IS DECLARED, because the retired kind table used to hand every
        #   builtin the whole row list and the rule now has to say so itself (판정 506).
        #   Without it the seat fans out per row and one stub answer is counted twice.
        rule_run.run_rule(None, dict(RULE, mapper="declared:s498_log_probe",
                                     is_batch=True),
                          row_ids=["r1", "r2"])

    said = lines(caplog)
    assert len(said) == 2
    assert "kind=fake_mapper_module.run" in said[0]
    assert "kind=declared:s498_log_probe" in said[1]
    # 🔴 AND THE TWO ARMS ARE TOLD APART BY A VALUE, NOT BY A VOCABULARY. A proposing rule
    # never fills `written`; a self-writing one reports it, and both report `rows_out`.
    assert "written=None" in said[0]
    assert "rows_out=2 written=2" in said[1]


def test_the_payload_body_never_reaches_the_log(monkeypatch, caplog):
    """Names and counts, never content."""
    mod, fn = install(monkeypatch, lambda db, p: {"updates": [{"updates": {"a": SECRET}}]})
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, _rule(mod, fn, is_batch=True), payloads=payloads(2))
    assert SECRET not in "\n".join(r.getMessage() for r in caplog.records)


# ------------------------------------------------------------------ it did not run

def test_a_rule_that_raises_still_logs_and_still_raises(monkeypatch, caplog):
    """`rows_out=0` and "it threw" must not read the same.

    A mapper with nothing to do legitimately returns nothing, so a line that could not tell
    the two apart would be exactly the confusion this instrument exists to remove.

    🔴 THE LINE IS WRITTEN IN `finally`, WHICH IS THE WHOLE OF WHY THIS STILL PASSES. The
    surviving vocabulary (`[ChainRule]`) logged AFTER the call and therefore said nothing at
    all when a rule threw - so folding the two by keeping the survivor would have deleted this
    case, and 「I grepped and found no line」 reading as 「it did not run」 is the day this
    logging exists because of.
    """
    def boom(db, p):
        raise ValueError("refused by name")

    mod, fn = install(monkeypatch, boom)
    with caplog.at_level(logging.INFO):
        with pytest.raises(ValueError):
            rule_run.run_rule(None, _rule(mod, fn, is_batch=True), payloads=payloads(2))

    said = lines(caplog)
    assert len(said) == 1
    assert "ValueError" in said[0] and "refused by name" in said[0]
    assert "some_rule" in said[0] and "rows_in=2" in said[0]
    assert "rows_out=None" in said[0], "a throw produced nothing, and it did not produce zero"


def test_a_mapper_with_nothing_to_do_says_zero_rather_than_going_quiet(monkeypatch, caplog):
    mod, fn = install(monkeypatch, lambda db, p: {"updates": []})
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, _rule(mod, fn, is_batch=True), payloads=payloads(4))
    assert "rows_out=0" in lines(caplog)[0]
    assert "error=None" in lines(caplog)[0]


# ------------------------------------------------------------------ the count is honest

def test_the_batch_shape_is_counted_and_not_reported_as_zero(monkeypatch, caplog):
    """🔴 THE SHAPE THAT WOULD HAVE LIED. `dt_standard_map_mapper` returns `batches`,
    not `updates`, and a counter that read only `updates` would report a whole map's
    worth of cells as `rows_out=0` - the very number the operator is trying to tell
    apart from "did not run".

    ⚠️ AND THAT IS WHY THE LINE PRINTS WHAT `run.produced` WAS TOLD. The first fold of the two
    vocabularies logged `len(updates)`, which is this lie with the tag removed; the number in
    the line and the number in the queue view are now the same number from the same function.
    """
    result = {"map_metadata_updates": [{"updates": {"map_id": "m"}}],
              "batches": [{"updates": [{"updates": {}}] * 7},
                          {"updates": [{"updates": {}}] * 5}]}
    mod, fn = install(monkeypatch, lambda db, p: result)
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, _rule(mod, fn, is_batch=True), payloads=payloads(1))
    assert "rows_out=13" in lines(caplog)[0]              # 7 + 5 + 1 metadata


def test_a_per_row_rule_counts_every_row_it_was_handed(monkeypatch, caplog):
    """⚠️ ONE LINE FOR THE GROUP, NOT ONE PER CALL. A non-batch rule is called once per row -
    the fan-out lives in the seat - and `rows_in` is what the GROUP was handed, so a thousand
    rows do not become a thousand lines (소유자 「한 행당 로그 하나」)."""
    calls = []
    mod, fn = install(monkeypatch,
                      lambda db, p: calls.append(p) or {"updates": [{"updates": {}}]})
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, _rule(mod, fn), payloads=payloads(3))

    assert len(calls) == 3, "the seat did not fan out per row"
    said = lines(caplog)
    assert len(said) == 1 and "rows_in=3" in said[0] and "rows_out=3" in said[0]


def test_a_rule_that_names_nothing_still_logs(monkeypatch, caplog):
    """The identity fields are read off the rule, and a rule may arrive without a name. An
    instrument that only works when its context is complete is not one."""
    mod, fn = install(monkeypatch, lambda db, p: {"updates": []})
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, {"mapper_module": mod, "mapper_function": fn,
                                 "is_batch": True},
                          payloads=payloads(1))
    said = lines(caplog)
    assert len(said) == 1
    assert "rule=<unnamed rule>" in said[0] and "target=<none>" in said[0]


def test_the_worker_still_names_the_file_this_process_writes():
    """⚠️ WHAT THE RETIRED TAG WAS FOR, AND WHERE IT LIVES NOW. `MAPPER_LOG_TAG` was built out
    of the ACTIVE log filename so a line would never claim `chain_worker.log` while landing in
    `server.log`. That fact is still published - by the queue response, which is the surface
    that can actually tell an operator which file to open - and `LOG_FILENAME` is still what
    this process asks for when it is the first to open one."""
    from utils import logger as process_logging

    assert worker.LOG_FILENAME == "chain_worker.log"
    assert process_logging.active_log_filename() is None or isinstance(
        process_logging.active_log_filename(), str)
