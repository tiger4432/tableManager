# -*- coding: utf-8 -*-
"""총괄 12cc7dd1f ① — 역할이 entity 이고 자기 attributes 를 안 적었으면, 계획이 그 자리에 «물려받음» 행을
낸다: 값은 번역이 실제로 묶는 속성(setup_registry.with_source_attributes), 근거는 소스의
bind.entities.<타입>.attributes. 역할이 자기 attributes 를 적으면 행이 없고, 저장의 채움은 그 행을
역할에 «안 쓴다»(쓰면 덮어씀이 되어 소스 쪽 고침이 안 따라간다). 표본 dt_job(dtjob@1.dt_eqp)으로 잰다.
"""
import copy
import json
import shutil
from pathlib import Path

import pytest

from ledger.config_authoring import authoring_plan, filled_declaration
from ledger.setup import load_setup
from ledger.setup_bundle import load_physical_catalog

SHIPPED = Path(__file__).resolve().parent.parent / "config" / "sample"
SOURCE, TYPE = "dt_job", "dtjob"          # the plan names it bare (4eb1fe98f)
BASE = "bundle.sources.%s.bind" % SOURCE
SAMPLE = json.loads((SHIPPED / "ledger_config.json.sample").read_text(encoding="utf-8"))
CATALOG = load_physical_catalog(SHIPPED / "table_config.json.sample")


def _plain(value):
    return json.loads(json.dumps(value, default=dict))


def _inherited(doc):
    return {row["path"]: row for row in authoring_plan(doc, CATALOG)["fields"]
            if row["path"].startswith(BASE + ".mappings.")
            and (row["ground"] or {}).get("rule") == "inherited_from_source"}


def _compiled(doc, tmp_path):
    (tmp_path / "ledger_config.json").write_text(json.dumps(doc), encoding="utf-8")
    return load_setup(tmp_path, catalog=CATALOG).snapshot.profiles[SOURCE].mappings


def test_an_entity_role_without_its_own_attributes_shows_what_translation_binds(tmp_path):
    rows = _inherited(SAMPLE)
    compiled = _compiled(SAMPLE, tmp_path)
    sentences = SAMPLE["sources"][SOURCE]["bind"]["mappings"]

    assert sorted(rows) == sorted("%s.mappings.%s.bind.subject.attributes" % (BASE, s)
                                  for s in sentences)
    for sentence in sentences:
        row = rows["%s.mappings.%s.bind.subject.attributes" % (BASE, sentence)]
        assert row["value"] == _plain(compiled[sentence].bindings["subject"]["attributes"])
        assert (row["state"], row["disposition"], row["ground"]["rule"]) == (
            "derived", "shape", "inherited_from_source")
        assert row["ground"]["from_paths"] == ["%s.entities.%s.attributes" % (BASE, TYPE)]


def test_a_role_that_says_its_own_attributes_has_no_inherited_row(tmp_path):
    doc = copy.deepcopy(SAMPLE)
    own = {"dt_eqp": {"kind": "constant", "value": "EQ1"}}
    doc["sources"][SOURCE]["bind"]["mappings"]["register"]["bind"]["subject"]["attributes"] = own

    rows = _inherited(doc)

    assert sorted(rows) == ["%s.mappings.counted.bind.subject.attributes" % BASE]
    assert _plain(_compiled(doc, tmp_path)["register"].bindings["subject"]["attributes"]) == own


def test_the_save_does_not_copy_an_inherited_row_into_the_role():
    raw = SAMPLE["sources"][SOURCE]
    body, dropped = filled_declaration(SAMPLE, CATALOG, ("sources", SOURCE), raw)

    assert dropped == []
    for mapping in body["bind"]["mappings"].values():
        assert "attributes" not in mapping["bind"]["subject"]
