# -*- coding: utf-8 -*-
"""S-194 ①. The draft lifecycle stops being the ledger's private property.

🔴 THE LIFECYCLE WAS NEVER THE LEDGER'S. Nine of `OntologyDraftStore`'s methods already owed
the document nothing — draft, review, revise, discard, the record IO, the revision check.
Draft/review/activate with optimistic locking and a snapshot compare-and-swap is a STATE
MACHINE, and the builder needs that machine, not a second copy of it (판정 303 forbade the
copy: 「합칠 사람이 없다」).

⚠️ 「ONE BUNDLE ARGUMENT」 WOULD NOT HAVE OPENED IT, which is what the S-194 design measured
and reported back. The coupling is to the explorer's navigation model — `ExplorerIndex` and
`ExplorerNode` — plus a hardcoded filename. A chain rule has no `ExplorerNode`, so the seam
had to be the QUESTIONS, not the bundle.

🔴 AND THE GATE 판정 303 ASKED FOR IS THAT NOTHING MOVED. The ledger path must come out
byte-identical, so `LedgerDocument` holds today's code and decides nothing differently. The
population that proves it is the draft-lifecycle suite, measured 129 passed / 2 failed both
before and after — the two being the pair queued as S-196.

⛔ THAT POPULATION WAS 25% BLIND UNTIL AN HOUR AGO. Twelve of the explorer suite's tests
could not run because a fixture catalogue said `event_at` where the declaration said
`event_time`, and those twelve sat behind 「기존 12」 all day. A refactor gated on a net with a
hole that size is not gated.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from ledger import config_drafts                                      # noqa: E402
from ledger.config_drafts import (DraftContext, LedgerDocument,       # noqa: E402
                                  OntologyDraftStore)


# ---------------------------------------------------------------------------
# the ledger keeps what it had
# ---------------------------------------------------------------------------

def test_the_store_defaults_to_the_document_it_has_always_edited(tmp_path):
    """⚠️ EVERY EXISTING CALLER PASSES NO DOCUMENT, and must keep working — that is what gives
    the byte-identical gate something to be identical to."""
    store = OntologyDraftStore(tmp_path)
    assert isinstance(store._document, LedgerDocument)


def test_the_ledger_document_answers_exactly_what_the_constants_said():
    """🔴 NOT A NEW DECISION, A MOVED ONE. If this class chose differently the gate would be
    measuring the wrong thing and passing anyway."""
    assert LedgerDocument.editable_file == config_drafts._EDITABLE_FILE == "ledger_config.json"


def test_the_ledger_document_delegates_to_the_functions_that_already_existed():
    """⛔ SCORED ON THE SOURCE, because the defect would be a REIMPLEMENTATION that happens to
    agree today — the same reason the materialising join calls `execute_rule` rather than
    composing its own SELECT."""
    import inspect

    assert "draft_target(" in inspect.getsource(LedgerDocument.target_of)
    assert "_filled_declaration(" in inspect.getsource(LedgerDocument.fill)
    assert "compile_draft_preview(" in inspect.getsource(LedgerDocument.preview)
    assert "index.node(" in inspect.getsource(LedgerDocument.node_of)


# ---------------------------------------------------------------------------
# 🔴 the seam is LIVE, not decorative
# ---------------------------------------------------------------------------

class _Recording:
    """A second document. It answers nothing useful — it only records being asked."""

    editable_file = "chain_rules.json"

    def __init__(self):
        self.asked = []

    def node_of(self, context, target_key):
        self.asked.append(("node_of", target_key))
        raise AssertionError("stop here: being asked is the whole assertion")

    def has_node(self, context, target_key):
        self.asked.append(("has_node", target_key))
        return False

    def snapshot_hash(self, context):
        self.asked.append(("snapshot_hash",))
        return "hash-from-the-document"

    def target_of(self, record, context):
        self.asked.append(("target_of",))
        raise AssertionError("stop here")

    def fill(self, context, node, raw):
        self.asked.append(("fill",))
        return raw

    def preview(self, context, node, raw):
        self.asked.append(("preview",))
        raise AssertionError("stop here")

    def config_root(self, context):
        self.asked.append(("config_root",))
        raise AssertionError("stop here")


def test_a_substituted_document_is_actually_consulted(tmp_path):
    """🔴 THE ASSERTION THAT MAKES THIS A SEAM. A refactor can name an adapter, default it to
    today's behaviour, and still read the module globals everywhere — every test would pass
    and the builder would be no closer. So a SECOND document is passed and the store must ask
    IT.
    """
    document = _Recording()
    store = OntologyDraftStore(tmp_path, document=document)
    assert store._document is document

    with pytest.raises(AssertionError):
        store.create(object(), object(), "some-target")
    assert ("node_of", "some-target") in document.asked, (
        "the store went to the module instead of the document it was given")


def test_the_document_decides_which_file_is_editable(tmp_path):
    """⚠️ THE FILENAME WAS A MODULE CONSTANT, and a second document edits a different file —
    so the refusal that used to compare against that constant must compare against the
    DOCUMENT's answer or a chain draft could never be created."""
    import inspect

    body = inspect.getsource(OntologyDraftStore.create)
    assert "self._document.editable_file" in body
    assert "_EDITABLE_FILE" not in body, "the module constant is read again"


# ---------------------------------------------------------------------------
# what stayed document-agnostic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["get", "request_review", "revise", "discard"])
def test_the_state_machine_asks_no_document(method):
    """🔴 THIS IS WHY ONE LIFECYCLE CAN SERVE TWO DOCUMENTS. Revisions, review, discard and
    the record IO never needed to know what was being edited — if they had, the seam would
    have been a rewrite instead of a handful of questions."""
    import inspect

    body = inspect.getsource(getattr(OntologyDraftStore, method))
    assert "_document" not in body, (method, "grew a document dependency")
    for leaked in ("active_setup", "active_index", "ExplorerIndex"):
        assert leaked not in body, (method, leaked)


def test_the_context_keeps_the_two_halves_apart():
    """⚠️ A PAIR, NOT A MERGE. The setup is what compiled; the index is how it is navigated.
    Collapsing them would hide which half a document actually reads."""
    context = DraftContext("setup", "index")
    assert context.setup == "setup" and context.index == "index"
    with pytest.raises(AttributeError):
        context.anything_else = 1          # __slots__: the pair is the whole of it


# ---------------------------------------------------------------------------
# S-194 ① second commit — the chain's document, in the same seat
# ---------------------------------------------------------------------------

def test_the_chain_document_answers_the_same_seven_questions():
    """🔴 THE POINT OF THE SEAM. Two documents, one lifecycle — so the chain's answers must
    cover exactly what the ledger's does, or the store would work for one and break for the
    other at whichever question was missing."""
    import chain_bindings

    ledger, chain = LedgerDocument, chain_bindings.ChainRuleDocument
    asked = ("editable_file", "node_of", "has_node", "snapshot_hash",
             "target_of", "fill", "preview", "config_root")
    for name in asked:
        assert hasattr(ledger, name), name
        assert hasattr(chain, name), ("the chain document cannot sit in the seat", name)


def test_the_chain_index_refuses_a_key_it_never_saw():
    """⛔ AS THE EXPLORER'S INDEX DOES. A key the loader never saw is a typo or a removed rule,
    and resolving it would put a draft on a target that cannot be written back."""
    import chain_bindings

    index = chain_bindings.ChainRuleIndex([{"name": "r1", "trigger_table": "t"}])
    assert index.node("r1").config_file == "chain_rules.json"
    assert index.node("r1").bundle_path == ("rules", 0)
    with pytest.raises(KeyError) as caught:
        index.node("typo")
    assert "r1" in str(caught.value), "the refusal must say what IS declared"


def test_the_snapshot_hash_is_over_the_rules_not_the_bytes():
    """🔴 A REFORMAT IS NOT A CHANGE. Two files differing only in whitespace describe the same
    rules, and rejecting a draft for that would teach an operator the lock is noise."""
    import chain_bindings

    one = chain_bindings.ChainRuleIndex([{"name": "r", "trigger_table": "t"}])
    same = chain_bindings.ChainRuleIndex([{"trigger_table": "t", "name": "r"}])
    other = chain_bindings.ChainRuleIndex([{"name": "r", "trigger_table": "other"}])
    assert one.snapshot_hash == same.snapshot_hash
    assert one.snapshot_hash != other.snapshot_hash


def test_the_chain_preview_is_the_loaders_judgement_not_a_second_one():
    """⚠️ A DRAFT THE SCREEN CALLS GOOD MUST NOT BE A RULE THE LOADER REFUSES. The preview
    scores with the same `validation.Problems` + `routing_keys()` the loader uses (S-188 ⓐⓑ)."""
    import chain_bindings

    document = chain_bindings.ChainRuleDocument()
    context = DraftContext(None, chain_bindings.ChainRuleIndex([]))

    missing = document.preview(context, None, {"trigger_table": "t"})
    assert not missing.ok
    assert [i["path"] for i in missing.issues] == ["rule.name"]

    good = document.preview(context, None, {"name": "r", "trigger_table": "t"})
    assert good.ok and good.issues == []


def test_the_chain_preview_warns_by_name_where_the_loader_warns():
    """🔴 THE SCREEN MUST NOT BE BLINDER THAN THE LOG. The loader ACCEPTS an unknown top-level
    cell — it is a mapper argument still written flat — and names it so the operator knows what
    to move. A preview reporting only refusals would let an author leave the file in the state
    the boot line complains about every morning, with the screen calling it good."""
    import chain_bindings

    document = chain_bindings.ChainRuleDocument()
    context = DraftContext(None, chain_bindings.ChainRuleIndex([]))
    preview = document.preview(context, None, {
        "name": "r", "trigger_table": "t", "x_col": "X", "__comment": "prose"})
    assert preview.ok, "a flat cell is accepted, exactly as the loader accepts it"
    assert [w["path"] for w in preview.warnings] == ["rule.x_col"]


def test_the_chain_document_fills_nothing_in():
    """⚠️ THE LEDGER FILLS A PARTLY WRITTEN NODE so it still compiles; a chain rule is flat and
    the loader's required cells are two. Inventing defaults would put values in the operator's
    file that the operator never wrote."""
    import chain_bindings

    raw = {"name": "r"}
    assert chain_bindings.ChainRuleDocument().fill(None, None, raw) is raw


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
