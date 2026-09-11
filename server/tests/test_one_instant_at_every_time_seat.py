# -*- coding: utf-8 -*-
"""S-182 ⓐ. A world time means ONE instant, and the seats stop answering differently.

SCHEMA_CANON R5 already ruled this axis — 「시각은 timestamptz 이고, 세상 시각은 «소스별로
선언»한다 · 선언이 없으면 «번역을 거절»한다 · naive datetime 금지」 — and
`occurred_at_timezone` implements it for ledger sources. 🔴 SO NO SECOND CELL IS ADDED
(판정 289). Measured before proposing one: this axis already carried three declared names
(`occurred_at_timezone`, the v2 bind `timezone`, `display_timezone`), and a fourth would be
the exact opposite of 「한 축은 한 칸」.

What was missing was never the answer. It was the ENFORCEMENT: nothing checked that a
parser had actually emitted an offset, so PostgreSQL's session TimeZone quietly decided,
and two processes configured differently disagreed about the same row.

⚠️ ROUND ⓐ DOES NOT REFUSE. Refusing an undeclared source is R5's own answer and is
already live for ledger sources, but switching it on for ordinary tables today would stop
every running load at once. So this round COUNTS and leaves the value alone — which is
what `test_an_undeclared_table_is_not_one_character_different` pins — and 판정 289's round
ⓑ turns the count into a refusal once the owner has declared.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database import crud                                             # noqa: E402
from utils import time_format as tf                                   # noqa: E402

NAIVE = datetime(2026, 8, 13, 4, 12, 7)
SEOUL_INSTANT = datetime(2026, 8, 12, 19, 12, 7, tzinfo=timezone.utc)
NAIVE_TEXT = "2026-08-13 04:12:07"
OFFSET_TEXT = "2026-08-13T04:12:07+09:00"


@pytest.fixture(autouse=True)
def _clean_counts():
    tf._NAIVE_TIME_COUNTS.clear()
    yield
    tf._NAIVE_TIME_COUNTS.clear()


# ---------------------------------------------------------------------------
# Gate A — one declared zone, one instant
# ---------------------------------------------------------------------------

def test_a_declared_zone_gives_one_instant():
    folded = tf.fold_time_value(NAIVE, zone="Asia/Seoul")
    assert folded.utcoffset().total_seconds() == 9 * 3600
    # THE ASSERTION IS THE INSTANT, not the wall text: two renderings of one instant are
    # the same fact, and pinning the text would pass a fold that kept the wrong offset.
    assert folded == SEOUL_INSTANT


def test_the_same_naive_value_under_two_zones_is_two_instants():
    """The sensitivity control. A fold that ignored its zone argument would satisfy every
    other assertion here while changing nothing."""
    assert (tf.fold_time_value(NAIVE, zone="Asia/Seoul")
            != tf.fold_time_value(NAIVE, zone="UTC"))


# ---------------------------------------------------------------------------
# Gate B — the source outranks the declaration
# ---------------------------------------------------------------------------

def test_a_value_that_carries_its_own_offset_is_untouched():
    """🔴 NOT 「the declaration wins」. A source that said which zone it meant has answered
    the question, and re-reading it under a declared zone would move an instant that was
    never ambiguous. This rule is not invented here — `void_sat_format.declare_offset`
    already carries it."""
    aware = NAIVE.replace(tzinfo=timezone.utc)
    assert tf.fold_time_value(aware, zone="Asia/Seoul") is aware
    assert crud._time_is_naive(OFFSET_TEXT) is False
    assert crud._time_is_naive("2026-08-13T04:12:07Z") is False


def test_an_unusable_zone_is_not_silently_defaulted():
    """An undeclarable zone must not fall back to UTC — that would be a guess presented as
    a declaration. It returns None, which means 「today's behaviour」, and the counter
    still names the seat."""
    assert tf.fold_time_value(NAIVE, zone="Nowhere/Nowhere") is None


# ---------------------------------------------------------------------------
# Gate D — 🔴 THE REGRESSION LINE, which is what makes this safe to deploy
# ---------------------------------------------------------------------------

def test_an_undeclared_table_is_not_one_character_different():
    """Round ⓐ counts; it does not change a value. If this ever goes red, the round has
    become the refusal that was deliberately deferred to ⓑ."""
    for value in (NAIVE_TEXT, OFFSET_TEXT, "not a time at all"):
        assert crud.cast_value_by_type(
            value, "datetime", "observed_at", "s182_table") == value
    # ⚠️ A BLANK STILL FOLDS TO `None`, and that is S-181's rule (판정 284), not this
    # round's. The blank branch sits BEFORE the datetime arm, so measuring it here is how
    # this test proves the new arm was inserted without stepping in front of the old one.
    for blank in ("", None, "   "):
        assert crud.cast_value_by_type(
            blank, "datetime", "observed_at", "s182_table") is None


def test_a_naive_world_time_is_counted_by_table_and_column():
    crud.cast_value_by_type(NAIVE_TEXT, "datetime", "observed_at", "s182_table")
    crud.cast_value_by_type(NAIVE_TEXT, "datetime", "observed_at", "s182_table")
    crud.cast_value_by_type(OFFSET_TEXT, "datetime", "observed_at", "s182_table")
    assert tf.naive_time_counts() == {"s182_table.observed_at": 2}
    assert "timezone_naive: s182_table.observed_at 2" == tf.naive_time_note()


def test_nothing_naive_says_nothing():
    """An empty string, not a cheerful zero — a healthy deployment stays quiet and the
    line it rides on does not grow a permanent passenger."""
    assert tf.naive_time_note() == ""


def test_a_non_datetime_column_is_never_counted():
    crud.cast_value_by_type(NAIVE_TEXT, "string", "note", "s182_table")
    assert tf.naive_time_counts() == {}


# ---------------------------------------------------------------------------
# Gate E — ⑥ the dead arm
# ---------------------------------------------------------------------------

def test_a_naive_datetime_cannot_reach_the_ledger_payload():
    """⚰️ BOTH ARMS USED TO BE `return value.isoformat()`, identical to the character — so
    nine sibling seats refused a naive datetime and the serializer that writes the payload
    let one through. R5 forbids the value; a payload is the last place to catch it."""
    from ledger import runtime_v2

    with pytest.raises(TypeError, match="naive datetime"):
        runtime_v2._json_scalar(NAIVE)
    assert runtime_v2._json_scalar(SEOUL_INSTANT) == SEOUL_INSTANT.isoformat()


def test_the_three_serializers_refuse_with_ONE_sentence():
    """Three seats, one spelling. Three wordings would be three rules that drift."""
    from ledger import roleframe, runtime_v2, source_preparation

    said = set()
    for call in (lambda: runtime_v2._json_scalar(NAIVE),
                 lambda: roleframe._plain(NAIVE),
                 lambda: source_preparation._plain(NAIVE)):
        with pytest.raises(TypeError) as caught:
            call()
        said.add(str(caught.value))
    assert said == {"naive datetime has no deterministic instant"}, said


# ---------------------------------------------------------------------------
# Gate F — the machine's ambient zone is gone
# ---------------------------------------------------------------------------

def test_no_module_still_renders_in_the_machines_zone():
    """`ledger_trace.DISPLAY_TIMEZONE_RULING` named this defect before S-182 measured it:
    the ambient zone of whatever host the process started on, resolved at import, with
    nothing declared anywhere. Asserted on the MODULES rather than on the source text, so
    a re-import under a different name still fails."""
    from database import schemas

    assert not hasattr(tf, "LOCAL_TIMEZONE")
    assert not hasattr(schemas, "LOCAL_TIMEZONE")


def test_the_rendered_string_carries_its_own_offset():
    assert tf.to_local_str(SEOUL_INSTANT).endswith("+00:00")
    assert tf.to_local_str(NAIVE).endswith("+00:00")
    assert tf.to_local_str(None) == ""


def test_two_spellings_of_one_instant_render_identically():
    """🔴 THE MEMO'S SOUNDNESS PROOF. `_LOCAL_STR_MEMO` is keyed on the argument, and two
    aware datetimes that are `==` share a slot — so if the render were `isoformat()` on the
    value as given, `+09:00` and `+00:00` spellings of one instant would collide and the
    second caller would receive the first one's string. Converting to UTC first is what
    keeps the equivalence class and the output in step."""
    seoul_spelling = SEOUL_INSTANT.astimezone(
        __import__("zoneinfo").ZoneInfo("Asia/Seoul"))
    assert seoul_spelling == SEOUL_INSTANT
    assert tf.to_local_str(seoul_spelling) == tf.to_local_str(SEOUL_INSTANT)
