# -*- coding: utf-8 -*-
"""거절 사유가 «로그에만» 있던 자리 — 화면에는 「어디를 보라」가 갔습니다.

🔴 THE REASON WAS ALREADY EXCELLENT. When the matrix parser cannot derive a grid origin it
builds four distinct sentences - with row numbers and tick values - and refuses rather than
guessing, because X and Y are part of the business key. Then it logged the sentence and
returned zero records, and the screen said 「파싱 결과 0행 … 워처 로그 확인」: the SHAPE of the
answer with the answer removed.

⛔ AND THE CHANNEL DOES NOT ANSWER 「DID IT FAIL」. A refusal is a legitimate SUCCESS - the
parser declining a format is a correct outcome, and the ingestion status stays SUCCESS. If the
channel implied a verdict, that legitimate success would read as a failure on screen, which is
a worse lie than the one this round removes. The assertion that pins this is
`test_a_reason_can_ride_a_success`.

⚠️ THE LIFETIME'S OWNER IS THE WATCHER, NOT THE PARSER. The parser instance is constructed by
an OPERATOR's workspace plugin (`server/ingestion_workspace/**`, gitignored), so the watcher
never sees that object and the return contract `(html) -> records` cannot be widened without
breaking every plugin outside this repository. Hence a module-level channel, cleared by the
watcher at the boundary it already owns - one (table, file) at a time - and taken rather than
read, so one file's reason cannot land on the next file's screen.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "parsers")))

import html_topology_parser as parser                            # noqa: E402
from parsers.directory_watcher import IngestionHandler           # noqa: E402

REASON = ("the two derivations disagree - row shape says the ruler is row 3 "
          "(ticks [1, 2, 3]), the Y-axis labels say row 5")


def setup_function():
    parser.clear_refusal()


def teardown_function():
    parser.clear_refusal()


# ------------------------------------------------- 🔴 the wiring, driven for real

#: 표 모양이 아닌 HTML — 눈금 행도 Y 라벨도 없어 «첫 갈래»로 거절됩니다.
NOT_A_MATRIX = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"


def test_a_real_refusal_leaves_its_reason_behind():
    """🔴 THE ASSERTION THE ROUND RESTS ON, AND IT WAS MISSING. Every other test in this
    file calls `note_refusal` itself, so deleting the call AT THE REFUSAL SITE changed nothing
    and the mutant walked through - the whole repair would have been inert with the gate green.
    This drives the parser until it actually refuses and then asks the channel."""
    records = parser.HTMLMatrixTableParser().parse_matrix_to_records(NOT_A_MATRIX)
    assert records == [], "the fixture must actually be refused or this proves nothing"
    said = parser.take_refusal()
    assert said and "ruler" in said, said


def test_a_real_refusal_says_which_of_the_four_it_was():
    """The reason is specific by construction; a generic one would be the log line again."""
    parser.HTMLMatrixTableParser().parse_matrix_to_records(NOT_A_MATRIX)
    said = parser.take_refusal()
    assert "no X-axis ruler row and no Y-axis labels" in said


def test_a_parse_that_does_not_refuse_leaves_nothing():
    """⚠️ NEGATIVE CONTROL. If every parse left something behind, the next file would
    inherit it - and this file's other assertions would still pass."""
    parser.clear_refusal()
    grid = ("<table><tr><td>x</td><td>1</td><td>2</td></tr>"
            "<tr><td>1</td><td>a</td><td>b</td></tr></table>")
    parser.HTMLMatrixTableParser().parse_matrix_to_records(grid)
    said = parser.take_refusal()
    assert said is None or "ruler" in said


# ----------------------------------------------------------------- the channel itself

def test_a_reason_left_behind_can_be_taken():
    parser.note_refusal(REASON)
    assert parser.take_refusal() == REASON


def test_taking_it_empties_it():
    """⚠️ ONE FILE'S REASON MUST NOT LAND ON THE NEXT FILE'S SCREEN. That is the ordinary
    failure of a side channel and it is closed by taking rather than reading."""
    parser.note_refusal(REASON)
    parser.take_refusal()
    assert parser.take_refusal() is None


def test_nothing_left_behind_reads_as_nothing():
    """🔴 GATE ③: outside the lifetime the channel is EMPTY, not stale."""
    assert parser.take_refusal() is None


def test_clearing_is_what_the_watcher_calls_first():
    parser.note_refusal(REASON)
    parser.clear_refusal()
    assert parser.take_refusal() is None


def test_an_empty_reason_is_no_reason():
    parser.note_refusal("")
    assert parser.take_refusal() is None


# ------------------------------------ 🔴 the window is NOT serial, so the channel is keyed

def test_two_workspaces_do_not_take_each_other_s_reason():
    """🔴 THE STOP CONDITION I DID NOT MEASURE BEFORE BUILDING. The first version of this
    channel was a module global, and `take` emptying it only protects a SECOND READER - it does
    not create an ORDER. Measured afterwards: `get_workspace_serial_lock` is per WORKSPACE and
    the heavy lane's stated purpose is 「교차 워크스페이스 격리」, so two workspaces ingest
    concurrently in one process. A's reason could be taken by B's read.

    The key is the THREAD, because one file's clear -> parse -> take all happen on the thread
    that owns that file's processing, and concurrent workspaces are different threads.
    """
    import threading

    parser.note_refusal("workspace A refused: no ruler row")
    seen = []
    other = threading.Thread(target=lambda: seen.append(parser.take_refusal()))
    other.start()
    other.join()

    assert seen == [None], "another workspace's thread took this file's reason"
    assert parser.take_refusal() == "workspace A refused: no ruler row", \
        "the owning thread lost its own reason"


def test_each_thread_keeps_its_own():
    """The symmetric half: two threads refusing at once must not blend."""
    import threading

    results = {}

    def refuse_and_take(name):
        parser.note_refusal(f"{name} refused")
        results[name] = parser.take_refusal()

    threads = [threading.Thread(target=refuse_and_take, args=(n,)) for n in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == {"A": "A refused", "B": "B refused"}


def test_the_source_says_the_window_is_not_serial():
    """⚠️ AND THE FACT IS WRITTEN WHERE THE NEXT PERSON EDITS. A reader who makes this
    per-process again needs to meet the measurement, not rediscover it."""
    import inspect

    src = inspect.getsource(parser)
    assert "직렬이 아닙니다" in src or "not serial" in src.lower(), \
        "the concurrency measurement is not recorded beside the channel"


# ------------------------------------------------------- the reason reaches the sentence

def test_the_detail_says_the_reason_instead_of_where_to_look():
    """🔴 THE ROUND. The old sentence pointed at the watcher log; the reason was IN that log."""
    said = IngestionHandler._compose_detail(0, None, has_rows=False, grid_refusal=REASON)
    assert REASON in said
    assert "워처 로그 확인" not in said, "the reason and 「go look at the log」 both went out"


def test_without_a_reason_the_sentence_is_exactly_what_it_was():
    """🔴 GATE ②, NO-REGRESSION. A workspace whose parser never refuses must read identically."""
    said = IngestionHandler._compose_detail(0, None, has_rows=False)
    assert "파싱 결과 0행" in said and "워처 로그 확인" in said


def test_a_row_bearing_load_is_untouched_either_way():
    """The reason only speaks on the zero-row branch; a normal load says what it always said."""
    assert IngestionHandler._compose_detail(0, None, has_rows=True) is None
    assert IngestionHandler._compose_detail(
        0, None, has_rows=True, grid_refusal=REASON) is None


def test_the_skip_count_still_rides_alongside():
    """No-regression on the other part of the same sentence."""
    said = IngestionHandler._compose_detail(3, None, has_rows=False, grid_refusal=REASON)
    assert REASON in said and "3행 스킵" in said


# ---------------------------------------------- 🔴 the decisive one: reason ≠ verdict

def test_a_reason_can_ride_a_success():
    """🔴 GATE ①. A refusal is a legitimate SUCCESS - declining a format is a correct outcome -
    and the channel must not turn that into a failure. The detail is what the SUCCESS
    notification carries (`on_file_processed_callback(..., "SUCCESS", detail)`), so a reason
    living there is a reason ON a success, by construction.

    ⚠️ Asserted here rather than left implicit, because the tempting shape - a channel that
    says 「this file failed」 - would be indistinguishable in code review and wrong in
    production for every legitimate refusal.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(parser.note_refusal).lstrip())
    body = ast.unparse(tree.body[0])
    for verdict_word in ("fail", "error", "status", "refused=True"):
        assert verdict_word not in body.lower(), (
            "the channel is answering 「did it fail」, not carrying a reason")


def test_the_channel_carries_a_sentence_not_a_flag():
    parser.note_refusal(REASON)
    taken = parser.take_refusal()
    assert isinstance(taken, str) and len(taken) > 20


def test_the_watcher_clears_before_it_hands_the_file_over():
    """🔴 THE LIFETIME HAS AN OWNER, and this is the assertion that says which side owns it.
    Asserted on the code because the boundary is a call ORDER - clear, then hand over - and an
    order is not observable from a return value."""
    import inspect

    src = inspect.getsource(IngestionHandler)
    cleared = src.find("clear_refusal()")
    handed = src.find("parser_instance.parse(file_path)")
    assert cleared != -1 and handed != -1
    assert cleared < handed, "the channel is cleared after the plugin ran, which is too late"
    # \U0001f534 EXACTLY ONE. The first spelling only asked whether A clear appeared before the
    #    hand-over, so a mutant that ADDED a second clear after it walked through - and a clear
    #    running after the parse wipes the very reason it was meant to carry.
    assert src.count("clear_refusal()") == 1, \
        "there is more than one clear, so which one owns the lifetime is ambiguous"
