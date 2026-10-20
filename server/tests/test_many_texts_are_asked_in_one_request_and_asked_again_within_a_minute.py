# -*- coding: utf-8 -*-
"""총괄 f7a79b242 (소유자 10-13 「체인 배치로 받아서 문장 잘 합쳐서 지시문 구성해서 요청 날려」): `ask_links` takes many
texts in one request; the one LLM seat (`utils.llm.ask_json`) keeps no limit of its own (소유자 「어차피 서버가 거절함」)
and asks again what got no answer, a 429 too, within a minute of the first failure (총괄 10-13 ④). A fake model -
`llm.ask_json` replaced by one that answers each [id] of the prompt - except where the seat itself is measured.

  one text (a str)                    the rows today's code gave, byte for byte (67 recorded calls)
  n texts of one length, cap c        ceil(n x length / c) requests · `requests` says it
  a text's rows in a batch            == that text asked alone
  a link quoting another text         dropped in its text, one line - the text's other links kept
  an id the answer leaves out         asked again alone once · then refused: no rows, its reason
  a whole answer refused              each text asked alone · a call that failed: the batch fails at once (one request)
  a text alone in its request         not asked again
  every text refused                  LlmRefused, the first text's reason
  the same id twice                   ValueError before any request
  the prompt                          snapshot below
  no answer · a 429                   asked again after 5 · 10 · 20 · 20 s (a 429 after its Retry-After) while the next
                                      try starts within 60 s of the first failure - back within ~55 s passes
  a Retry-After over 60 s             not waited for: LlmCallFailed at once
  a key refused · a 4xx · own errors  not asked again (4xx: text by text)
  a pause during a wait               ChainPaused in a chain group - rewound, not failed
  number cells                        defaults · a bad value refused by name
"""
import json
import logging
import math
import os
import re
import sys
import threading
import time
import types

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from utils import llm, text_links                                     # noqa: E402
from test_a_text_is_read_by_a_language_model import (                   # noqa: E402,F401 - the fixtures are used
    CELLS, NAMES, _declare, _log_lines, fixture_answer, fixture_root)

RECORDED = os.path.join(os.path.dirname(__file__), "samples", "text_links", "ask_links_one_text_before_batching.json")
TEXTS_HEADING = "Texts, each after its [id] line:\n"
_ITEM = re.compile(r"\[([^\]\n]+)\]\n(.*?)(?=\n\n\[[^\]\n]+\]\n|\Z)", re.S)


def _asked_texts(prompt):
    """[(id, text)] of a prompt, as the model reads them."""
    return _ITEM.findall(prompt.split(TEXTS_HEADING, 1)[1])


class Model:
    """A fake model: each text of a request gets `links[text]` (none listed: []). `leave_out(id, number)`
    says whether request `number` (from 1) leaves that id out; `whole(number)` may give a whole answer."""

    def __init__(self, links=None, leave_out=None, whole=None):
        self.links, self.leave_out, self.whole = links or {}, leave_out, whole
        self.prompts = []

    def __call__(self, prompt, **_kwargs):
        self.prompts.append(prompt)
        number = len(self.prompts)
        if self.whole and self.whole(number) is not None:
            return self.whole(number)
        return {"texts": [{"id": ident, "links": self.links.get(text, [])} for ident, text in _asked_texts(prompt)
                          if not (self.leave_out and self.leave_out(ident, number))]}


@pytest.fixture(name="model")
def fixture_model(root, monkeypatch):
    """`model(**kwargs)` installs a `Model` as the seat; config holds CELLS and `cells`."""
    def install(cells=None, **kwargs):
        _declare(root, **CELLS, **(cells or {}))
        fake = Model(**kwargs)
        monkeypatch.setattr(llm, "ask_json", fake)
        return fake
    return install


def test_one_text_gives_the_rows_todays_code_gave_byte_for_byte(model, monkeypatch):
    """The 67 calls the two LLM test files made on eb1ae8c9f, before batching (cec861e5f): each answer's
    links handed back under the one text's id."""
    with open(RECORDED, encoding="utf-8") as handle:
        recorded = json.load(handle)
    assert len(recorded) == 67
    for case in recorded:
        fake = model(whole=lambda _n, case=case: {"texts": [{"id": text_links.ONE_TEXT_ID,
                                                             "links": case["answer"]["links"]}]})
        rows = text_links.ask_links(case["text"], case["names"], instruction=case["instruction"],
                                    match_at=case["match_at"])
        assert json.dumps(rows, ensure_ascii=False) == case["rows"], case["text"][:60]
        assert type(rows) is text_links.AskedLinks and isinstance(rows, list)
        assert (rows.requests, rows.texts, rows.refused, len(fake.prompts)) == (1, 1, [], 1)


TEN = ["Text %d %s" % (n, "x" * (100 - len("Text %d " % n))) for n in range(10)]


@pytest.mark.parametrize("cap", [100, 300, 500, 1000, 5000])
def test_n_texts_of_one_length_take_ceil_of_their_characters_over_the_cap_requests(model, cap):
    assert {len(text) for text in TEN} == {100}, "one length - the count is exact only so"
    fake = model(cells={"batch_chars": cap})
    found = text_links.ask_links([{"id": n, "text": text} for n, text in enumerate(TEN)], NAMES)
    assert len(fake.prompts) == found.requests == math.ceil(len(TEN) * 100 / cap)
    assert found.texts == 10 and found == []
    assert [ident for prompt in fake.prompts for ident, _text in _asked_texts(prompt)] == [str(n) for n in range(10)]


A = "The bond temperature was high. It caused a void, we suspect."
B = "Humidity rose overnight. The void came from humidity."
C = "Nothing happened here."
LINKS = {
    A: [{"cause": "bond temperature", "effect": "void", "evidence": "It caused a void, we suspect."},
        {"cause": "humidity", "effect": "void", "evidence": "The void came from humidity."}],   # B's sentence
    B: [{"cause": "humidity", "effect": "void", "cause_direction": "up", "evidence": "The void came from humidity."}],
    C: [],
}
BATCH = [{"id": "a", "text": A}, {"id": 7, "text": B}, {"id": "c", "text": C}]


def test_a_texts_rows_in_a_batch_are_its_rows_asked_alone(model):
    fake = model(links=LINKS)
    batched = text_links.ask_links(BATCH, NAMES)
    assert len(fake.prompts) == batched.requests == 1
    for item in BATCH:
        alone = text_links.ask_links(item["text"], NAMES)
        assert [{k: v for k, v in row.items() if k != "text_id"} for row in batched
                if row["text_id"] == item["id"]] == list(alone)
    assert [row["text_id"] for row in batched] == ["a", 7], "text_id first, as handed in, texts in order"
    assert list(batched[0])[0] == "text_id"


def test_a_link_quoting_another_texts_sentence_is_dropped_in_its_text(model, caplog):
    model(links=LINKS)
    caplog.set_level(logging.WARNING)
    found = text_links.ask_links(BATCH, NAMES)
    assert [(row["text_id"], row["cause_phrase"]) for row in found] == [("a", "bond temperature"), (7, "humidity")]
    assert [r.getMessage() for r in caplog.records if r.name == "utils.text_links"] == [
        "[LLM] link 2 of 2 quotes evidence the text does not hold - dropped (llm:m-1): 'The void came from humidity.'"]
    assert found.refused == []


def test_an_id_the_answer_leaves_out_is_asked_again_alone(model, caplog):
    fake = model(links=LINKS, leave_out=lambda ident, number: ident == "7" and number == 1)
    caplog.set_level(logging.WARNING)
    found = text_links.ask_links(BATCH, NAMES)
    assert (found.requests, len(fake.prompts), found.refused) == (2, 2, [])
    assert [ident for ident, _text in _asked_texts(fake.prompts[1])] == ["7"]
    assert [row["text_id"] for row in found] == ["a", 7]
    assert [r.getMessage() for r in caplog.records if r.name == "utils.text_links"][-1] == (
        "[LLM] a request of 3 texts left 1 unread - each asked alone: 7: the answer has no item for text 7")


def test_an_id_left_out_again_is_refused_with_its_reason_and_the_others_kept(model, caplog):
    fake = model(links=LINKS, leave_out=lambda ident, _number: ident == "7")
    caplog.set_level(logging.WARNING)
    found = text_links.ask_links(BATCH, NAMES)
    assert (found.requests, found.texts) == (2, 3) and len(fake.prompts) == 2
    assert found.refused == [{"id": 7, "reason": "the answer has no item for text 7"}]
    assert [row["text_id"] for row in found] == ["a"]
    assert [r.getMessage() for r in caplog.records if r.name == "utils.text_links"][-1] == (
        "[LLM] text 7 refused - no rows (llm:m-1): the answer has no item for text 7")


@pytest.mark.parametrize("whole", [{"rows": []}, llm.LlmRefused("the answer is not JSON: nope")],
                         ids=["no-texts-list", "not-json"])
def test_a_whole_answer_refused_asks_each_text_alone(model, monkeypatch, whole):
    def first(number):
        if number != 1:
            return None
        if isinstance(whole, Exception):
            raise whole
        return whole
    fake = model(links=LINKS, whole=first)
    found = text_links.ask_links(BATCH, NAMES)
    assert (found.requests, len(fake.prompts), found.refused) == (4, 4, [])
    assert [[ident for ident, _t in _asked_texts(p)] for p in fake.prompts[1:]] == [["a"], ["7"], ["c"]]


def test_a_text_alone_in_its_request_is_not_asked_again(model):
    fake = model(cells={"batch_chars": 10}, links=LINKS, leave_out=lambda ident, _number: ident == "7")
    found = text_links.ask_links(BATCH, NAMES)
    assert (found.requests, len(fake.prompts)) == (3, 3)
    assert found.refused == [{"id": 7, "reason": "the answer has no item for text 7"}]


def test_every_text_refused_is_refused_by_name(model):
    model(links=LINKS, leave_out=lambda _ident, _number: True)
    with pytest.raises(llm.LlmRefused) as refused:
        text_links.ask_links(BATCH, NAMES)
    assert str(refused.value) == "every text (3) was refused - text 'a': the answer has no item for text 'a'"


def test_an_item_without_a_links_list_is_that_text_s_reason(model):
    model(whole=lambda number: {"texts": [{"id": 1, "rows": []}]})
    with pytest.raises(llm.LlmRefused) as refused:
        text_links.ask_links(A, NAMES)
    assert str(refused.value) == "the answer's item for text 1 has no 'links' list: ['id', 'rows']"


def test_the_same_id_twice_is_refused_before_any_request(model):
    fake = model()
    with pytest.raises(ValueError, match="text ids must be unique - '7' given twice"):
        text_links.ask_links([{"id": 7, "text": A}, {"id": "7", "text": B}], NAMES)
    assert fake.prompts == []


def test_no_texts_ask_nothing(model):
    fake = model()
    assert text_links.ask_links([], NAMES) == [] and fake.prompts == []


#: The prompt of two texts, a dictionary of two nodes and an instruction - written out, not built.
SNAPSHOT = """Read each text below and list every statement in it that one thing causes another.
When one sentence names several causes or effects, list one link for each cause and effect pair - separate items, which may quote the same evidence.
Answer with one JSON object and nothing else - one item for each text, its id as written between the brackets of its [id] line, without the brackets:
{"texts": [{"id": "...", "links": [{"cause": "...", "cause_key": null, "cause_direction": null, "effect": "...", "effect_key": null, "effect_direction": null, "link": "...", "evidence": "...", "negated": false, "certainty": null}]}]}
- cause, effect: the shortest noun phrase of the text that names the thing, copied from the text - a few words, never a clause or a whole sentence (the whole sentence goes in evidence)
- cause_key, effect_key: the identifier of the dictionary node the cause or the effect is, written exactly as listed; null when no listed node fits
- cause_direction, effect_direction: "up" when the text says that thing increases, rises or grows, "down" when it says it decreases, falls or shrinks, null when it says neither
- link: the words of the text that join the cause to the effect
- evidence: the sentence of the text that says it, copied exactly from that same text
- negated: true when the text says the cause does not lead to the effect
- certainty: "confirmed" when the text says it is confirmed, "suspected" when it says it is suspected, null when it says neither
Dictionary, one node per line - identifier (node type): the phrases that name it
q-temp (quantity): bond temperature
d-void (defect_kind): void
Instruction from the operator:
only the cause of voids
Texts, each after its [id] line:
[a]
The bond temperature was high. It caused a void, we suspect.

[7]
Humidity rose overnight. The void came from humidity."""


def test_the_prompt_of_a_batch(model):
    fake = model()
    text_links.ask_links(BATCH[:2], NAMES, instruction="only the cause of voids")
    assert fake.prompts == [SNAPSHOT]


# ---------------------------------------------------------------------------- the seat: asking again


@pytest.fixture(name="clock")
def fixture_clock(monkeypatch):
    """The seat's clocks stand still unless a wait moves them; `clock.waits` are the waits asked - whole, the
    slice set past any wait (`test_a_pause_during_a_wait_*` slices them)."""
    clock = types.SimpleNamespace(now=1000.0, waits=[])

    def sleep(seconds):
        clock.waits.append(seconds)
        clock.now += seconds
    monkeypatch.setattr(llm, "_steady", lambda: clock.now)
    monkeypatch.setattr(llm, "_sleep", sleep)
    monkeypatch.setattr(llm, "WAIT_SLICE_S", 1e9)
    return clock


class TooMany(Exception):
    status_code = 429

    def __init__(self, retry_after=None):
        super().__init__("Error code: 429 - too many requests")
        self.response = types.SimpleNamespace(headers={} if retry_after is None else {"retry-after": retry_after})


def _client_saying(monkeypatch, *said):
    """The seat's client answers `said` in turn - an exception is raised, a string is the content.
    -> the list each call appends to."""
    calls, said = [], iter(said)

    class Client:
        base_url, default_headers = "http://llm.test/v1/", {}

        def __init__(self):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                with_raw_response=types.SimpleNamespace(create=self.create)))

        def create(self, **_payload):
            calls.append(1)
            got = next(said)
            if isinstance(got, Exception):
                raise got
            return types.SimpleNamespace(status_code=200, text=got, parse=lambda: types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=got))]))
    monkeypatch.setattr(llm, "_client", lambda cells: Client())
    return calls


TOO_MANY = "TooMany: Error code: 429 - too many requests · proxy: none (direct)"


def test_a_429_is_asked_again_after_its_retry_after(retrying, monkeypatch, caplog, root):
    """A 429 waits what it asks (7 s); without a Retry-After, the next step of the ladder (10 s)."""
    calls = _client_saying(monkeypatch, TooMany("7"), TooMany(), '{"ok": 1}')
    caplog.set_level(logging.WARNING)
    assert llm.ask_json("anything") == {"ok": 1}
    assert len(calls) == 3 and retrying.waits == [7.0, 10]
    assert [line.get("status") for line in _log_lines(root) if "received" in line] == [429, 429, 200]
    assert [r.getMessage() for r in caplog.records if r.name == "utils.llm"] == [
        "[LLM] call failed (%s) - retrying in 7 s (1 of 4)" % TOO_MANY,
        "[LLM] call failed (%s) - retrying in 10 s (2 of 4)" % TOO_MANY]


def test_a_429_past_its_retries_is_a_call_that_failed(retrying, monkeypatch):
    calls = _client_saying(monkeypatch, *[TooMany("1")] * 5)
    with pytest.raises(llm.LlmCallFailed, match="the language model call failed: TooMany: Error code: 429"):
        llm.ask_json("anything")
    assert len(calls) == 5 and retrying.waits == [1.0] * 4


def test_a_429_whose_wait_ends_past_the_minute_is_not_waited(retrying, monkeypatch):
    """Retry-After 40 after 30 s of 429s: the next try would start 70 s after the first failure."""
    calls = _client_saying(monkeypatch, TooMany("30"), TooMany("40"), '{"ok": 1}')
    with pytest.raises(llm.LlmCallFailed):
        llm.ask_json("anything")
    assert len(calls) == 2 and retrying.waits == [30.0]


@pytest.mark.parametrize("failure", [TypeError("bad header value"), UnicodeEncodeError("ascii", "é", 0, 1, "x")],
                         ids=["TypeError", "UnicodeEncodeError"])
def test_another_failure_is_not_asked_again(retrying, monkeypatch, failure):
    """최종 검수 6: only no answer (connection, time limit, 5xx, 408) is asked again - an error of the call's own
    making, with no status, fails at once (a 503 is asked again: `test_no_answer_*`)."""
    calls = _client_saying(monkeypatch, failure)
    with pytest.raises(llm.LlmCallFailed):
        llm.ask_json("anything")
    assert len(calls) == 1 and retrying.waits == []


def test_the_number_cells_default_and_a_bad_one_is_refused(root):
    from database import config_watcher

    _declare(root, **CELLS)
    cells = llm.settings()
    assert {name: cells[name] for name in llm.NUMBER_CELLS} == {
        "timeout_s": 60.0, "batch_chars": 4000, "known_chars": 4000, "known_per_seed": 5}
    for name, bad in (("batch_chars", 0), ("batch_chars", 1.5), ("known_chars", "9"), ("known_per_seed", True)):
        _declare(root, **CELLS)
        llm.settings()
        _declare(root, **CELLS, **{name: bad})
        assert llm.settings() == cells, "a process that read the file keeps what it read (e6a0bdbbd ③)"
        config_watcher._HELD.clear()            # one that read none refuses it
        with pytest.raises(llm.LlmRefused, match="%s in config/llm_config.json is not a whole number" % name):
            llm.settings()


def _failing(at, failure):
    """A `whole` that raises `failure` on request `at` and leaves the others to the model."""
    def whole(number):
        if number == at:
            raise failure
        return None
    return whole


def test_a_call_that_failed_fails_the_batch_at_once(model):
    """총괄 10-13 ②: no answer came - asking each text alone would ask a gateway that is not answering."""
    failure = llm.LlmCallFailed("the language model call failed: ConnectError: refused · proxy: none (direct)")
    fake = model(links=LINKS, whole=_failing(1, failure))
    with pytest.raises(llm.LlmCallFailed) as refused:
        text_links.ask_links(BATCH, NAMES)
    assert refused.value is failure and len(fake.prompts) == 1


def test_a_call_that_failed_while_a_text_is_asked_alone_fails_the_batch(model):
    fake = model(links=LINKS, leave_out=lambda ident, number: ident == "7",
                 whole=_failing(2, llm.LlmCallFailed("the language model call failed: ReadTimeout: timed out")))
    with pytest.raises(llm.LlmCallFailed):
        text_links.ask_links(BATCH, NAMES)
    assert len(fake.prompts) == 2


REAL_WAITS = llm.CALL_RETRY_WAITS          # read before `root` turns the retries off for its one-try tests
DOWN = "ConnectionError: connection refused · proxy: none (direct)"


@pytest.fixture(name="retrying")
def fixture_retrying(root, clock, monkeypatch):
    """The seat's retries on no answer, as shipped, on the stopped clock."""
    _declare(root, **CELLS)
    monkeypatch.setattr(llm, "CALL_RETRY_WAITS", REAL_WAITS)
    return clock


def _gateway_down_until(monkeypatch, clock, until, per_try=0.0):
    """A gateway that refuses connections until the clock reaches `until`, then answers text 1; a try takes
    `per_try` seconds. -> the instants the tries began."""
    began, content = [], json.dumps({"texts": [{"id": 1, "links": LINKS[A][:1]}]})

    class Client:
        base_url, default_headers = "http://llm.test/v1/", {}

        def __init__(self):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                with_raw_response=types.SimpleNamespace(create=self.create)))

        def create(self, **_payload):
            began.append(clock.now)
            clock.now += per_try
            if clock.now < until:
                raise ConnectionError("connection refused")
            return types.SimpleNamespace(status_code=200, text=content, parse=lambda: types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))]))
    monkeypatch.setattr(llm, "_client", lambda cells: Client())
    return began


TRIES = [1000.0, 1005.0, 1015.0, 1035.0, 1055.0]


@pytest.mark.parametrize("down,tries", [(30, 4), (36, 5), (50, 5)])
def test_a_gateway_back_within_55_s_is_waited_out_and_the_batch_reads(retrying, monkeypatch, caplog, down, tries):
    """총괄 10-13 ④ · 최종 검수 1: no answer is asked again after 5, 10, 20, 20 s - tries at 0 · 5 · 15 · 35 · 55 s."""
    began = _gateway_down_until(monkeypatch, retrying, until=1000 + down)
    caplog.set_level(logging.WARNING)
    rows = text_links.ask_links(A, NAMES)
    assert [row["cause_phrase"] for row in rows] == ["bond temperature"] and rows.requests == 1
    assert began == TRIES[:tries] and retrying.waits == [5, 10, 20, 20][:tries - 1]
    assert [r.getMessage() for r in caplog.records if r.name == "utils.llm"] == [
        "[LLM] call failed (%s) - retrying in %d s (%d of 4)" % (DOWN, wait, n)
        for n, wait in enumerate((5, 10, 20, 20)[:tries - 1], 1)]


@pytest.mark.parametrize("down", [59, 90])
def test_a_gateway_down_past_55_s_fails_the_batch_once(retrying, monkeypatch, down):
    began = _gateway_down_until(monkeypatch, retrying, until=1000 + down)
    with pytest.raises(llm.LlmCallFailed) as refused:
        text_links.ask_links(BATCH, NAMES)
    assert str(refused.value) == "the language model call failed: " + DOWN
    assert began == TRIES and retrying.waits == [5, 10, 20, 20]


def test_a_pause_during_a_wait_rewinds_the_group_and_is_not_a_failure(retrying, monkeypatch):
    """최종 검수 3: the wait is slept in slices; in a chain group each asks the pause - paused, `ChainPaused` (the
    group is rewound at that boundary, not failed), and nothing more is asked. Each slice is progress."""
    from chain import control
    from database.context import chain_group
    from utils import heartbeat

    monkeypatch.setattr(llm, "WAIT_SLICE_S", 1.0)
    began = _gateway_down_until(monkeypatch, retrying, until=2000)
    monkeypatch.setattr(control, "paused", lambda: {"by": "t"} if retrying.now >= 1003 else None)
    slices = []
    monkeypatch.setattr(heartbeat, "progress", lambda stage: slices.append(stage))
    with chain_group(), pytest.raises(control.ChainPaused):
        text_links.ask_links(BATCH, NAMES)                      # the batch's path: not caught as a refusal
    assert began == [1000.0] and retrying.waits == [1.0, 1.0, 1.0] and slices == [None] * 3


def test_outside_a_group_a_wait_does_not_ask_the_pause(retrying, monkeypatch):
    from chain import control

    monkeypatch.setattr(llm, "WAIT_SLICE_S", 1.0)
    began = _gateway_down_until(monkeypatch, retrying, until=1004)
    monkeypatch.setattr(control, "paused", lambda: {"by": "t"})
    assert llm.ask_json("anything") == {"texts": [{"id": 1, "links": LINKS[A][:1]}]}
    assert began == [1000.0, 1005.0] and retrying.waits == [1.0] * 5


def test_tries_that_take_long_stop_at_the_minute(retrying, monkeypatch):
    """The window counts from the first failure: tries of 25 s each fail at 1025, 1055 and 1090; the next would
    start at 1110, past 1025 + 60, so the third try is the last."""
    began = _gateway_down_until(monkeypatch, retrying, until=10_000, per_try=25)
    with pytest.raises(llm.LlmCallFailed):
        llm.ask_json("anything")
    assert began == [1000.0, 1030.0, 1065.0] and retrying.waits == [5, 10]


# ---------------------------------------------------------------------------- 총괄 검수 10-13: 1 · 3 · 5 · 7 · 8 · M4


class Status(Exception):
    """What the client raises for an answer of that status."""

    def __init__(self, status):
        super().__init__("Error code: %d" % status)
        self.status_code = status


def test_a_retry_after_past_one_window_is_a_call_that_failed_not_a_wait(retrying, monkeypatch):
    """1: a gateway asking 3600 s would hold the group (and its tables) for hours - refused at once."""
    calls = _client_saying(monkeypatch, TooMany("3600"), '{"ok": 1}')
    with pytest.raises(llm.LlmCallFailed) as refused:
        llm.ask_json("anything")
    assert len(calls) == 1 and retrying.waits == []
    assert str(refused.value).endswith(" - it asked to wait 3600 s (Retry-After), more than 60 s")


def test_a_retry_after_of_one_window_is_waited(retrying, monkeypatch):
    calls = _client_saying(monkeypatch, TooMany("60"), '{"ok": 1}')
    assert llm.ask_json("anything") == {"ok": 1} and len(calls) == 2 and retrying.waits == [60.0]


def test_the_client_makes_no_request_of_its_own(answer):
    """5: the SDK's own retries were a second ladder beside the seat's - every request is the seat's."""
    answer('{"ok": 1}')
    llm.ask_json("anything")
    assert [made["max_retries"] for made in answer.made] == [0]


def _one(ident):
    return json.dumps({"texts": [{"id": ident, "links": []}]})


@pytest.mark.parametrize("status", [400, 413, 404, 422])
def test_a_request_refused_as_too_large_or_bad_is_asked_text_by_text(retrying, monkeypatch, status):
    """8: a 4xx other than the key's is the request's - not asked again as no answer, each text alone once."""
    calls = _client_saying(monkeypatch, Status(status), _one("a"), _one("7"), _one("c"))
    found = text_links.ask_links(BATCH, NAMES)
    assert (len(calls), found.requests, found.refused, retrying.waits) == (4, 4, [], [])


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_says_to_check_it(root, clock, monkeypatch, status):
    _declare(root, **CELLS)
    _client_saying(monkeypatch, Status(status))
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert not isinstance(refused.value, llm.LlmCallFailed)
    assert str(refused.value) == ("the gateway refused the key (%d) - check api_key and headers in"
                                  " config/llm_config.json: Status: Error code: %d · proxy: none (direct)" % (status, status))


NO_ANSWER_WAITS = [5, 10, 20, 20]


@pytest.mark.parametrize("failure,tries,waits", [
    (Status(500), 5, NO_ANSWER_WAITS), (Status(503), 5, NO_ANSWER_WAITS), (Status(408), 5, NO_ANSWER_WAITS),
    (TimeoutError("timed out"), 5, NO_ANSWER_WAITS), (ConnectionError("reset"), 5, NO_ANSWER_WAITS),
    (TooMany("1"), 5, [1.0] * 4)], ids=["500", "503", "408", "timeout", "connection", "429-past-its-retries"])
def test_no_answer_fails_the_batch_once_after_its_tries(retrying, monkeypatch, failure, tries, waits):
    """Text by text never: the batch's one request tried again, then `LlmCallFailed` - a 429 by the same ladder."""
    calls = _client_saying(monkeypatch, *[failure] * tries)
    with pytest.raises(llm.LlmCallFailed):
        text_links.ask_links(BATCH, NAMES)
    assert len(calls) == tries and retrying.waits == waits


@pytest.mark.parametrize("status", [401, 403])
def test_a_key_refused_is_not_asked_again(retrying, monkeypatch, status):
    calls = _client_saying(monkeypatch, Status(status))
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert len(calls) == 1 and retrying.waits == [] and not isinstance(refused.value, llm.LlmCallFailed)


def test_a_key_refused_in_a_batch_is_asked_text_by_text_never_again(retrying, monkeypatch):
    calls = _client_saying(monkeypatch, *[Status(401)] * 4)
    with pytest.raises(llm.LlmRefused) as refused:
        text_links.ask_links(BATCH, NAMES)
    assert len(calls) == 4 and retrying.waits == [] and "refused the key (401)" in str(refused.value)


def test_a_client_that_cannot_be_built_is_not_asked_again(retrying, root):
    _declare(root, **CELLS, proxy="http://user:p/w@proxy.test:8080")
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert not isinstance(refused.value, llm.LlmCallFailed) and retrying.waits == []
    assert len([line for line in _log_lines(root) if "received" in line]) == 1


def test_one_text_answered_the_one_text_way_is_read(model):
    """3: a request of one text answered {"links": [...]} - the old shape - is that text's answer."""
    fake = model(whole=lambda number: {"links": LINKS[B]})
    rows = text_links.ask_links([{"id": 7, "text": B}], NAMES)
    assert [(row["text_id"], row["cause_phrase"]) for row in rows] == [(7, "humidity")] and len(fake.prompts) == 1
    assert [row["cause_phrase"] for row in text_links.ask_links(B, NAMES)] == ["humidity"]


def test_many_texts_answered_the_one_text_way_are_asked_alone(model):
    fake = model(links=LINKS, whole=lambda number: {"links": LINKS[A]} if number == 1 else None)
    found = text_links.ask_links(BATCH, NAMES)
    assert (found.requests, len(fake.prompts), found.refused) == (4, 4, [])


@pytest.mark.parametrize("answered,handed,read", [
    ("[a]", "a", True), ("'7'", 7, True), ('"7"', "7", True), ("7", 7, True), (7, "7", True), (7.0, 7, True),
    ("[ c ]", "c", True), ("007", 7, False), ("a7", "a", False)])
def test_an_id_is_compared_as_its_text_without_brackets_or_quotes(model, answered, handed, read):
    """7: the model writes the id it saw - with or without its brackets and quotes; "007" is not 7."""
    text = {"a": A, "7": B, "c": C}[str(handed)]
    model(whole=lambda number: {"texts": [{"id": answered, "links": LINKS[text]}, {"id": "other", "links": []}]}
          if number == 1 else {"texts": []})
    found = text_links.ask_links([{"id": handed, "text": text}, {"id": "other", "text": C}], NAMES)
    assert (handed not in [item["id"] for item in found.refused]) is read


def test_the_first_item_of_an_id_is_its_answer(model):
    """M4: an answer that gives one id twice - the first item is read, the second is not."""
    model(whole=lambda number: {"texts": [{"id": "7", "links": LINKS[B]},
                                          {"id": "7", "links": [{"cause": "x", "effect": "y", "evidence": "nowhere"}]},
                                          {"id": "a", "links": []}, {"id": "c", "links": []}]})
    rows = text_links.ask_links(BATCH, NAMES)
    assert [(row["text_id"], row["cause_phrase"]) for row in rows] == [(7, "humidity")]
