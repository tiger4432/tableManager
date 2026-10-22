# -*- coding: utf-8 -*-
"""Lead aa8ff1af5 ㄱ · d706db3ed · afe3a1b47 (owner 10-21 «문자 타입에서 숫자 타입으로 테이블 선언 바꾸니 numeric pg
에러», 10-22 «테이블 컬럼 스트링으로 바꿨는데 아직도 시간으로 들어감»): a declared type the database does not hold yet
is held in the file and converted on the retroactive queue - one judgment over three cells, a key the conversion would
change refused, and the model the conversion builds its index statements from changes that one cell and nothing
else."""
import pytest

from admin import retype


@pytest.mark.parametrize("declared, physical, values, keys, expected", [
    ("number", "text", None, (), retype.CONVERT),               # the save: types only
    ("number", "text", (0, []), (), retype.CONVERT),            # the conversion: every value read as a number
    ("number", "text", (2, ["a", "b"]), (), retype.REFUSED),
    ("datetime", "text", None, (), retype.CONVERT),
    ("datetime", "text", (1, ["2026/10/03 12:00+09"]), (), retype.REFUSED),
    ("string", "datetime", None, (), retype.CONVERT),           # time -> text: the key's spelling
    ("string", "datetime", None, ("the row key",), retype.CONVERT),   # its key text does not change
    ("number", "text", None, ("the row key",), retype.REFUSED),
    ("datetime", "text", None, ("decide d1",), retype.REFUSED),
    ("number", "number", None, (), retype.NONE),
    ("string", "number", None, (), retype.NONE),                # widening the database takes as it is
    ("string", "text", None, (), retype.NONE),
    ("number", None, None, (), retype.NONE),                    # no column yet: the schema sync adds it
    ("number", "datetime", None, (), retype.NOT_DONE),          # not converted - said
])
def test_one_judgment_over_the_declared_type_the_column_its_keys_and_its_values(declared, physical, values, keys,
                                                                                 expected):
    do, said = retype.verdict(declared, physical, values, keys)
    assert do == expected
    if do == retype.REFUSED and keys:
        assert said.startswith("it is a key - %s - " % keys[0]) and "fill a new column through the chain" in said
    elif do == retype.REFUSED:
        assert ("value(s) are not %s, e.g. %r" % (retype.CELLS[(physical, declared)]["reads"], values[1][0])) in said
        assert "or declare the column string again" in said
    if do == retype.NOT_DONE:
        assert said == "a datetime column is not converted to number"


def test_the_conversion_s_model_changes_that_one_cell_and_nothing_else(monkeypatch):
    from database import crud

    catalogue = {"t": {"column_types": {"a": "string", "rev": "string"}, "business_key": "a"},
                 "u": {"column_types": {"x": "string"}}}
    monkeypatch.setattr(crud, "TABLE_CONFIG", catalogue)
    config = retype.model_config("t", "rev", "number")
    assert config["t"]["column_types"] == {"a": "string", "rev": "number"}
    config["t"]["column_types"]["rev"] = "string"
    assert config == catalogue and catalogue["t"]["column_types"]["rev"] == "string"


def test_the_save_holds_nothing_off_postgresql(tmp_path):
    from sqlalchemy import create_engine

    declaration = {"column_types": {"rev": "number"}}
    out, held = retype.hold(create_engine("sqlite:///" + (tmp_path / "x.db").as_posix()), "t", declaration)
    assert out is declaration and held == []
