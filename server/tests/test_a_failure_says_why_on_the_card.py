# -*- coding: utf-8 -*-
"""실패 카드가 «언제나» 같은 문장이던 이유 — 사유가 «칸»으로 안 나갔다.

🔴 THE READER WAS ALIVE AND SHIPPED THE WHOLE TIME. `client2/src/utils.js`
`finishIngestionProgress(table, file, status, errorMsg)` has always drawn `errorMsg` on the
failure card and fallen back to 「처리 중 예외 발생」 when it is absent, and
`websocket.js` has always passed `msg.error_msg` into it. Nothing was missing on the
receiving side.

🔴 WHAT WAS MISSING IS THAT NOBODY SENT THE FIELD. Three senders each built the broadcast by
hand, each APPENDED the reason to `message`, and none put `error_msg` in the payload. So the
toast said why and the card said the same sentence for every failure — 실측 2026-09-07:
보내는 자리 «셋» · 그 칸을 싣는 자리 «0».

⚠️ AND THE REASON REACHED THE DOOR. `run_watcher.trigger_ws_file_processed` already sets
`payload["error_msg"]` on the internal POST, and the relay route already binds it as a
parameter. It was dropped in the one step between receiving it and broadcasting it — which
is why this round is 「나르기」 and not 「만들기」.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                            # noqa: E402

TABLE = "dt_map"
FILE = "lot.csv"


def built(status, error_msg=None):
    return event_constants.file_ingestion_completed_message(TABLE, FILE, status, error_msg)


# ------------------------------------------------------------- the field reaches the wire

def test_a_failure_carries_its_reason_as_a_field():
    """🔴 THE GATE. Not 「the sentence mentions it」 — the CARD reads the field."""
    msg = built("FAILED", "UnicodeDecodeError: cp949 codec")
    assert msg["error_msg"] == "UnicodeDecodeError: cp949 codec"


def test_two_different_failures_are_two_different_payloads():
    """⚠️ THE POINT OF THE LINE, ASSERTED DIRECTLY. Before this, every failure produced the
    same card because the differing part never left the server."""
    one = built("FAILED", "cp949 codec")
    two = built("FAILED", "no such column: wafer")
    assert one["error_msg"] != two["error_msg"]


def test_a_failure_with_no_reason_omits_the_field_rather_than_sending_a_blank():
    """⚠️ ABSENT IS NOT EMPTY. A blank string would tell the card 「사유가 있고 그것은 빈
    문자열이다」 and it would paint an empty line; an absent key lets the card say the one
    honest thing it has always said."""
    msg = built("FAILED")
    assert "error_msg" not in msg


def test_the_sentence_still_says_it_too():
    """No-regression: the toast reads `message`, and it carried the reason before this round.
    Moving the field must not take the sentence away."""
    msg = built("FAILED", "cp949 codec")
    assert "실패" in msg["message"] and "cp949 codec" in msg["message"]


def test_success_keeps_its_own_sentence():
    msg = built("SUCCESS")
    assert "처리되었습니다" in msg["message"] and msg["status"] == "SUCCESS"


def test_a_success_detail_is_carried_too_rather_than_dropped_here():
    """⚠️ THE SLOT MEANS 「detail」 ON SUCCESS (「키 결측으로 N행 스킵」). Dropping it here
    would leave the screen no way to reach that fact at all. Whether the card READS it on the
    success branch is a different open line (F-6) and is deliberately not decided here."""
    msg = built("SUCCESS", "키 결측으로 3행 스킵")
    assert msg["error_msg"] == "키 결측으로 3행 스킵"


def test_the_field_is_capped_and_the_sentence_is_capped_shorter():
    """🔴 TWO CAPS, ON PURPOSE. The sentence is a toast line; the field is what the card
    trims to its own width. Pre-trimming the field on the server would make the card trim an
    already-trimmed string and the operator would lose the tail twice."""
    long_reason = "x" * 900
    msg = built("FAILED", long_reason)
    assert len(msg["error_msg"]) == event_constants.MAX_INGESTION_ERROR_CHARS
    assert len(msg["error_msg"]) > 100, "the field must not be cut to the sentence's length"


def test_a_non_string_reason_does_not_break_the_payload():
    """Exceptions arrive as objects at two of the three senders (`str(e)` is the caller's
    habit, not a guarantee). A payload that cannot be serialised would lose the whole
    notification, not just its reason."""
    msg = built("FAILED", ValueError("bad row"))
    assert msg["error_msg"] == "bad row"


# ------------------------------------------------------------------ one place, three callers

def test_every_sender_goes_through_the_one_builder():
    """🔴 ASSERTED ON THE CODE, BECAUSE SHARING IS THE PROPERTY. A behaviour test would pass
    just as well if the block had been copied a fourth time — which is precisely how this
    defect was born (three hand-written payloads, three chances to forget one key) and how
    `_bare` became four bodies under one name.
    """
    import io

    main_src = io.open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
                       encoding="utf-8").read()
    assert main_src.count("file_ingestion_completed_message(") == 3, \
        "the three senders no longer all go through the one builder"
    assert '"event": "file_ingestion_completed"' not in main_src, \
        "a sender is spelling the payload by hand again"


def test_the_builder_is_where_the_other_one_lives():
    """The precedent is in the same module: `batch_refresh_message` collected nine senders
    for the same reason. Two payload builders in two homes would be the next split."""
    assert hasattr(event_constants, "batch_refresh_message")
    assert hasattr(event_constants, "file_ingestion_completed_message")
