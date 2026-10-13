# -*- coding: utf-8 -*-
"""TEXT_LINKS_GUIDE §6 and §6-2 teach the batch mapper; this reads the guide's own python blocks - the text is
the subject - fills the placeholders, loads them with the product's loader (`mapper_sdk.discover`) and runs them
through the registered wrapper, as a rule seat calls it (총괄 검수 10-13: «가이드 예시를 고정하는 시험»).
A fake model leaves one text unread; the walk of §6-2 is the in-memory one.

  §6 · §6-2   loads · one request for two texts · the read text's retract batch · the unread text gets none
              and the line «kept old cells of 1 job(s) the mapper could not read» · §6-2's prompt has known links
"""
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                           # noqa: E402
from database import crud                                                   # noqa: E402
from ledger import explorer                                                 # noqa: E402
from ledger_api import ledger_subgraph                                      # noqa: E402
from utils import llm, text_links                                           # noqa: E402

GUIDE = os.path.join(os.path.dirname(SERVER_DIR), "docs", "guide", "TEXT_LINKS_GUIDE.md")
SAMPLE = os.path.join(SERVER_DIR, "config", "sample", "table_config.json.sample")
PLACES = {"<타입 칸>": "node_type", "<키 칸>": "node_key", "<말 칸>": "phrase", "<부르는 말 표>": "text_name",
          "<글 id 칸>": "doc_id", "<글 칸>": "body", "<규칙 이름>": "guide_llm_rule", "<글 표>": "text_doc",
          "<후보 표>": "text_cause_candidate", "<인과 술어>": "leads_to"}
NAME = "text_cause_links_llm"
DOCS = {"D1": "The bond temperature was high. It caused a void, we suspect.",
        "D2": "Humidity rose overnight. The void came from humidity."}
ITEM = re.compile(r"\[([^\]\n]+)\]\n(.*?)(?=\n\n\[[^\]\n]+\]\n|\Z)", re.S)


def _filled(text):
    for place, value in PLACES.items():
        text = text.replace(place, value)
    assert "<" not in text.replace("<cause", "").replace("<effect", ""), text
    return text


def _section(heading):
    guide = open(GUIDE, encoding="utf-8").read()
    start = guide.index(heading)
    end = guide.find("\n## ", start + 1)
    nxt = guide.find("\n### ", start + 1)
    return guide[start:min(i for i in (end, nxt, len(guide)) if i > 0)], guide


@pytest.fixture(name="seat")
def fixture_seat(tmp_path, monkeypatch):
    """The sample's text tables declared (the candidate keyed by phrases, §6), the fake model, a SQLite session
    holding the dictionary, and the guide's mapper loaded from `heading` -> (run, prompts)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    sample = json.load(open(SAMPLE, encoding="utf-8"))
    tables = {name: dict(sample[name]) for name in ("text_doc", "text_name", "text_cause_candidate")}
    tables["text_cause_candidate"]["composite_key_source"] = ["doc_id", "sentence_no", "cause_phrase", "phenomenon_phrase"]
    for name, declared in tables.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, declared)
    monkeypatch.setattr(llm, "settings", lambda: {"batch_chars": 4000, "known_chars": 4000, "known_per_seed": 5})
    monkeypatch.setattr(llm, "model", lambda: "fake")
    prompts = []

    def ask_json(prompt, **_kwargs):
        prompts.append(prompt)
        asked = ITEM.findall(prompt.split("Texts, each after its [id] line:\n", 1)[1])
        return {"texts": [{"id": ident, "links": [{"cause": "bond temperature", "effect": "void",
                                                   "evidence": "It caused a void, we suspect."}]}
                          for ident, _text in asked if ident == "D1"]}         # D2 is never read
    monkeypatch.setattr(llm, "ask_json", ask_json)

    def walked(seeds, follow, hops):
        atom = ledger_subgraph.EvidenceAtom(
            id=str(uuid.UUID(int=1)), subject_type="quantity", subject_keys={"key": "q-temp"}, predicate="leads_to",
            object_kind="entity_ref", object_payload={"type": "defect_kind", "keys": {"key": "d-void"}, "qualifiers": {}},
            occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc), source_who="t", source_translator_ver="v1",
            source_raw_ref="r1", supersedes=None, source_event_id=str(uuid.UUID(int=2)), source_event_state="source_molecule")
        return ledger_subgraph.subgraph({"positive": [explorer.entity_id(t, {"key": k}) for t, k in seeds]},
                                        ledger_subgraph.InMemoryEvidenceLookup([atom]), hops=hops,
                                        follow=list(follow), direction="both")
    monkeypatch.setattr(text_links, "_walked", walked)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE text_name (node_type TEXT, node_key TEXT, phrase TEXT)"))
        conn.execute(text("INSERT INTO text_name VALUES ('quantity','q-temp','bond temperature'),"
                          "('defect_kind','d-void','void'),('quantity','q-hum','humidity')"))
    db = sessionmaker(bind=engine)()
    package = "guide_example_mappers_%s" % uuid.uuid4().hex[:8]
    (tmp_path / package).mkdir()
    (tmp_path / package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    def load(heading):
        section, guide = _section(heading)
        code = next(block for block in re.findall(r"```python\n(.*?)```", section, re.S) if "def %s(" % NAME in block)
        rule = next(block for block in re.findall(r"```json\n(.*?)```", guide, re.S) if '"%s"' % NAME in block)
        (tmp_path / package / "example.py").write_text(_filled(code), encoding="utf-8")
        mapper_sdk.MAPPER_REGISTRY.pop(NAME, None)
        registered, refusals = mapper_sdk.discover(package)
        assert NAME in registered and not [r for r in refusals if package in r], refusals
        rule = json.loads(_filled(rule))
        payloads = [{"row_id": n, "data": {"doc_id": {"value": k}, "body": {"value": v}}}
                    for n, (k, v) in enumerate(DOCS.items(), 1)]
        return mapper_sdk.MAPPER_REGISTRY[NAME](db, payloads, rule=rule), rule
    yield load, prompts
    mapper_sdk.MAPPER_REGISTRY.pop(NAME, None)
    getattr(mapper_sdk, "MAPPER_PARAMS", {}).pop(NAME, None)


@pytest.mark.parametrize("heading", ["## 6. LLM", "### 6-2."])
def test_the_guides_mapper_loads_and_keeps_the_unread_texts_old_rows(seat, heading, caplog):
    load, prompts = seat
    with caplog.at_level(logging.INFO):
        envelope, rule = load(heading)
    assert rule["allow_retraction"] is True and rule["rows_per_run"] == 20
    assert [b["retract"]["source_value"] for b in envelope["batches"]] == ["D1"]
    assert [u["updates"]["doc_id"] for u in envelope["batches"][0]["updates"]] == ["D1"]
    assert "[Chain] guide_llm_rule: kept old cells of 1 job(s) the mapper could not read - D2" in [
        r.getMessage() for r in caplog.records if r.name == "mapper_sdk"]
    assert len(prompts) == 2, "the batch, then the unread text alone"
    assert ("Known links, one per line" in prompts[0]) is (heading == "### 6-2.")
