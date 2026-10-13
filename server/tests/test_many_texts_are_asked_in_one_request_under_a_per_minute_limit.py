# -*- coding: utf-8 -*-
"""총괄 f7a79b242 · ded29a831 (소유자 10-13 「체인 배치로 받아서 문장 잘 합쳐서 지시문 구성해서 요청 날려」 ·
「분당 20 회 제한 있음」): `ask_links` takes many texts in one request, and every call of the one LLM
seat (`utils.llm.ask_json`) waits for room under a per-minute limit. A fake model - `llm.ask_json`
replaced by one that answers each [id] of the prompt - except where the seat itself is measured.

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
  the per-minute limit                the 21st call of a minute waits for the oldest to leave
  a 429                               asked again after its Retry-After, RATE_LIMITED_TRIES times
  number cells                        defaults · a bad value refused by name
  two processes (PostgreSQL)          one limit: `llm_calls` under the advisory lock · no table: refused with the fix
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


# ---------------------------------------------------------------------------- the seat: per-minute limit · 429


@pytest.fixture(name="clock")
def fixture_clock(monkeypatch):
    """The seat's clock stands still unless a wait moves it; `clock.waits` are the waits asked."""
    clock = types.SimpleNamespace(now=1000.0, waits=[])

    def sleep(seconds):
        clock.waits.append(seconds)
        clock.now += seconds
    monkeypatch.setattr(llm, "_clock", lambda: clock.now)
    monkeypatch.setattr(llm, "_sleep", sleep)
    return clock


def test_the_21st_call_of_a_minute_waits_for_the_oldest_to_leave(answer, clock, caplog):
    answer('{"ok": 1}')
    caplog.set_level(logging.INFO)
    for n in range(20):
        llm.ask_json("call %d" % n)
        clock.now += 1.0                       # one call a second: the first left at 1000
    assert clock.waits == []
    llm.ask_json("the 21st")
    assert clock.waits == [40.0], "the oldest (1000) leaves the window at 1060; the 21st came at 1020"
    assert "[LLM] per-minute limit - waiting 40 s (20 requests a minute)" in [
        r.getMessage() for r in caplog.records if r.name == "utils.llm"]


def test_the_limit_is_the_files_cell(answer, root, clock):
    _declare(root, **CELLS, requests_per_minute=2)
    answer('{"ok": 1}')
    for _n in range(3):
        llm.ask_json("call")
    assert clock.waits == [60.0]


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


def test_a_429_is_asked_again_after_its_retry_after(root, clock, monkeypatch, caplog):
    _declare(root, **CELLS)
    calls = _client_saying(monkeypatch, TooMany("7"), TooMany(), '{"ok": 1}')
    caplog.set_level(logging.WARNING)
    assert llm.ask_json("anything") == {"ok": 1}
    assert len(calls) == 3 and clock.waits == [7.0, 60.0]
    assert [line.get("status") for line in _log_lines(root) if "received" in line] == [429, 429, 200]
    assert [r.getMessage() for r in caplog.records if r.name == "utils.llm"] == [
        "[LLM] the gateway answered 429 (too many requests) - waiting 7 s, then try 2 of 4",
        "[LLM] the gateway answered 429 (too many requests) - waiting 60 s, then try 3 of 4"]


def test_a_429_past_the_tries_is_refused(root, clock, monkeypatch):
    _declare(root, **CELLS)
    calls = _client_saying(monkeypatch, *[TooMany("1")] * (llm.RATE_LIMITED_TRIES + 1))
    with pytest.raises(llm.LlmRefused, match="the language model call failed: TooMany: Error code: 429"):
        llm.ask_json("anything")
    assert len(calls) == llm.RATE_LIMITED_TRIES + 1 and clock.waits == [1.0] * llm.RATE_LIMITED_TRIES


def test_another_failure_is_not_asked_again(root, clock, monkeypatch):
    failure = RuntimeError("upstream said no")
    failure.status_code = 503
    _declare(root, **CELLS)
    calls = _client_saying(monkeypatch, failure)
    with pytest.raises(llm.LlmRefused, match="503|upstream said no"):
        llm.ask_json("anything")
    assert len(calls) == 1 and clock.waits == []


def test_the_number_cells_default_and_a_bad_one_is_refused(root):
    _declare(root, **CELLS)
    cells = llm.settings()
    assert {name: cells[name] for name in llm.NUMBER_CELLS} == {
        "timeout_s": 60.0, "requests_per_minute": 20, "batch_chars": 4000, "known_chars": 4000, "known_per_seed": 5}
    for name, bad in (("requests_per_minute", 0), ("batch_chars", 1.5), ("known_chars", "9"), ("known_per_seed", True)):
        _declare(root, **CELLS, **{name: bad})
        with pytest.raises(llm.LlmRefused, match="%s in config/llm_config.json is not a whole number" % name):
            llm.settings()


# ---------------------------------------------------------------------------- PostgreSQL: one limit, many processes


def _public_calls(engine):
    from sqlalchemy import text
    with engine.connect() as conn:
        if conn.execute(text("SELECT to_regclass('public.llm_calls')")).scalar() is None:
            return None
        return conn.execute(text("SELECT count(*) FROM public.llm_calls")).scalar()


@pytest.fixture(name="two_processes")
def fixture_two_processes(pg_engine, monkeypatch):
    """Two engines on the scratch schema - two processes as the database sees them - and the seat's
    engine switched between them; public.llm_calls counted before and after."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from database import database
    from tests.conftest import PG_TEST_SCHEMA, scratch_connect_args

    other = create_engine(pg_engine.url, poolclass=NullPool, connect_args=scratch_connect_args(PG_TEST_SCHEMA))
    with pg_engine.begin() as conn:
        schema = conn.execute(text("SELECT current_schema()")).scalar()
        conn.execute(text("DELETE FROM llm_calls"))          # the scratch table: this test's calls only
    with other.connect() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == schema != "public"
    before = _public_calls(pg_engine)
    engines = {"A": pg_engine, "B": other}

    def be(name):
        monkeypatch.setattr(database, "engine", engines[name])
    yield be
    assert _public_calls(pg_engine) == before, "public.llm_calls untouched"
    other.dispose()


@pytest.mark.pg
def test_two_processes_share_one_limit(two_processes, clock):
    from sqlalchemy import text

    from database import database
    for name in "ABA":
        two_processes(name)
        llm._take_a_turn(3)
    assert clock.waits == []
    two_processes("B")
    llm._take_a_turn(3)
    assert clock.waits == [60.0], "B's first call is the fourth of the minute"
    with database.engine.connect() as conn:
        assert conn.execute(text("SELECT called_at FROM llm_calls")).scalars().all() == [1060.0], (
            "the three of 1000 left the window at 1060 and were deleted; B's call is the one row")


@pytest.mark.pg
def test_callers_at_one_instant_get_exactly_the_cap(two_processes, clock, monkeypatch):
    from sqlalchemy import text

    from database import database

    class Waited(Exception):
        pass

    def sleep(_seconds):
        raise Waited
    monkeypatch.setattr(llm, "_sleep", sleep)
    real_wait = llm._wait_s

    def slow_wait(times, now, cap):
        """Between the count and the write, so callers without the lock would all read the same count."""
        time.sleep(0.2)
        return real_wait(times, now, cap)
    monkeypatch.setattr(llm, "_wait_s", slow_wait)
    two_processes("A")
    engine = database.engine
    passed, waited = [], []

    def call():
        try:
            llm._take_a_turn(5)
            passed.append(1)
        except Waited:
            waited.append(1)
    threads = [threading.Thread(target=call) for _n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM llm_calls")).scalar() == 5
    assert (len(passed), len(waited)) == (5, 3)


@pytest.mark.pg
def test_a_database_without_the_table_is_refused_by_name(two_processes, clock, monkeypatch):
    """A slot that asks before the web server made `llm_calls`: the call is refused with the fix, not a raw
    database error. The table's place taken by one of its shape under a name nobody made - nothing dropped."""
    from sqlalchemy import Column, Float, Integer, MetaData, Table

    from database import models
    two_processes("A")
    absent = Table("llm_calls_never_made", MetaData(), Column("id", Integer, primary_key=True),
                   Column("called_at", Float, nullable=False))
    monkeypatch.setattr(models.LlmCall, "__table__", absent)
    with pytest.raises(llm.LlmCallFailed) as refused:
        llm._take_a_turn(3)
    said = str(refused.value)
    assert said.startswith("the per-minute limit could not use table llm_calls_never_made (ProgrammingError: ")
    assert said.endswith(" - it is made by the web server's boot (create_all): start it once on this code")
    assert clock.waits == []


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


def test_a_gateway_down_for_30_s_is_waited_out_and_the_batch_reads(retrying, monkeypatch, caplog):
    """총괄 10-13 ④: no answer is asked again after 5, 10, 20 s - each try a turn under the per-minute limit."""
    began = _gateway_down_until(monkeypatch, retrying, until=1030)
    caplog.set_level(logging.WARNING)
    rows = text_links.ask_links(A, NAMES)
    assert [row["cause_phrase"] for row in rows] == ["bond temperature"] and rows.requests == 1
    assert began == [1000.0, 1005.0, 1015.0, 1035.0] and retrying.waits == [5, 10, 20]
    assert len(llm._recent) == 4, "the limit counted every try"
    assert [r.getMessage() for r in caplog.records if r.name == "utils.llm"] == [
        "[LLM] call failed (%s) - retrying in %d s (%d of 3)" % (DOWN, wait, n)
        for n, wait in enumerate((5, 10, 20), 1)]


def test_a_gateway_down_for_90_s_fails_the_batch_once(retrying, monkeypatch):
    began = _gateway_down_until(monkeypatch, retrying, until=1090)
    with pytest.raises(llm.LlmCallFailed) as refused:
        text_links.ask_links(BATCH, NAMES)
    assert str(refused.value) == "the language model call failed: " + DOWN
    assert began == [1000.0, 1005.0, 1015.0, 1035.0] and retrying.waits == [5, 10, 20]


def test_tries_that_take_long_stop_at_the_minute(retrying, monkeypatch):
    """The window counts from the first failure: tries of 25 s each fail at 1025 and 1055; a third wait (20 s)
    would end past 1025 + 60, so the third try is the last."""
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


def test_a_retry_after_past_one_window_is_a_call_that_failed_not_a_wait(root, clock, monkeypatch):
    """1: a gateway asking 3600 s would hold the group (and its tables) for hours - refused at once."""
    _declare(root, **CELLS)
    calls = _client_saying(monkeypatch, TooMany("3600"), '{"ok": 1}')
    with pytest.raises(llm.LlmCallFailed) as refused:
        llm.ask_json("anything")
    assert len(calls) == 1 and clock.waits == []
    assert str(refused.value).endswith(" - it asked to wait 3600 s (Retry-After), more than 60 s")


def test_a_retry_after_of_one_window_is_waited(root, clock, monkeypatch):
    _declare(root, **CELLS)
    calls = _client_saying(monkeypatch, TooMany("60"), '{"ok": 1}')
    assert llm.ask_json("anything") == {"ok": 1} and len(calls) == 2 and clock.waits == [60.0]


def test_the_client_makes_no_request_of_its_own(answer):
    """5: the SDK's own retries went around the per-minute limit - every request is the seat's."""
    answer('{"ok": 1}')
    llm.ask_json("anything")
    assert [made["max_retries"] for made in answer.made] == [0]


def _one(ident):
    return json.dumps({"texts": [{"id": ident, "links": []}]})


@pytest.mark.parametrize("status", [400, 413, 404, 422])
def test_a_request_refused_as_too_large_or_bad_is_asked_text_by_text(root, clock, monkeypatch, status):
    """8: a 4xx other than the key's is the request's - each text alone once."""
    _declare(root, **CELLS)
    calls = _client_saying(monkeypatch, Status(status), _one("a"), _one("7"), _one("c"))
    found = text_links.ask_links(BATCH, NAMES)
    assert (len(calls), found.requests, found.refused) == (4, 4, [])


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_says_to_check_it(root, clock, monkeypatch, status):
    _declare(root, **CELLS)
    _client_saying(monkeypatch, Status(status))
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert not isinstance(refused.value, llm.LlmCallFailed)
    assert str(refused.value) == ("the gateway refused the key (%d) - check api_key and headers in"
                                  " config/llm_config.json: Status: Error code: %d · proxy: none (direct)" % (status, status))


@pytest.mark.parametrize("failure,waits", [(Status(500), [5, 10, 20]), (Status(503), [5, 10, 20]),
                                           (TimeoutError("timed out"), [5, 10, 20]), (TooMany("1"), [1.0, 1.0, 1.0])],
                         ids=["500", "503", "timeout", "429-past-its-tries"])
def test_no_answer_fails_the_batch_once_after_its_tries(retrying, monkeypatch, failure, waits):
    """Text by text never: four tries of the batch's one request, then `LlmCallFailed` - a spent 429 by its own count."""
    calls = _client_saying(monkeypatch, *[failure] * 4)
    with pytest.raises(llm.LlmCallFailed):
        text_links.ask_links(BATCH, NAMES)
    assert len(calls) == 4 and retrying.waits == waits


def test_a_key_refused_or_a_request_refused_is_not_asked_again(retrying, monkeypatch):
    calls = _client_saying(monkeypatch, Status(401))
    with pytest.raises(llm.LlmRefused):
        llm.ask_json("anything")
    assert len(calls) == 1 and retrying.waits == []


def test_a_client_that_cannot_be_built_is_not_a_call_that_failed(root, clock, monkeypatch):
    _declare(root, **CELLS, proxy="http://user:p/w@proxy.test:8080")
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert not isinstance(refused.value, llm.LlmCallFailed)


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


@pytest.mark.pg
def test_a_table_the_limit_cannot_read_is_said_without_the_boot(two_processes, clock, monkeypatch):
    """9: only a missing table names the boot - a table of another shape says what the database said."""
    from sqlalchemy import Column, Float, Integer, MetaData, Table

    from database import models
    two_processes("A")
    # a table the scratch schema has, without the column: the statement fails at its column (42703), deletes nothing
    other = Table("database_outbox", MetaData(), Column("id", Integer, primary_key=True),
                  Column("called_at", Float, nullable=False))
    monkeypatch.setattr(models.LlmCall, "__table__", other)
    with pytest.raises(llm.LlmCallFailed) as refused:
        llm._take_a_turn(3)
    assert str(refused.value).startswith("the per-minute limit could not use table database_outbox (ProgrammingError: ")
    assert "boot" not in str(refused.value)
