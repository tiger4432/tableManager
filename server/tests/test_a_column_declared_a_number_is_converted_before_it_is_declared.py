# -*- coding: utf-8 -*-
"""Lead aa8ff1af5 ㄱ (owner 10-21 «문자 타입에서 숫자 타입으로 테이블 선언 바꾸니 numeric pg 에러»): a declared type the
database does not hold yet is held in the file and converted on the retroactive queue - one judgment, and the model the
conversion builds its index statements from changes that one cell and nothing else."""
import pytest

from admin import retype


@pytest.mark.parametrize("declared, physical, values, expected", [
    ("number", "text", None, retype.CONVERT),               # the save: types only
    ("number", "text", (0, []), retype.CONVERT),            # the conversion: every value read as a number
    ("number", "text", (2, ["a", "b"]), "refused"),
    ("number", "number", None, retype.NONE),
    ("string", "number", None, retype.NONE),                # widening: works today, nothing to convert
    ("string", "text", None, retype.NONE),
    ("number", None, None, retype.NONE),                    # no column yet: the schema sync adds it
    ("datetime", "text", None, retype.NOT_DONE),            # not converted - said
])
def test_one_judgment_over_the_declared_type_the_column_and_its_values(declared, physical, values, expected):
    do, said = retype.verdict(declared, physical, values)
    assert do == expected
    if expected == "refused":
        assert "2 value(s) are not numbers, e.g. 'a', 'b'" in said and "then save the declaration" in said
    if expected == retype.NOT_DONE:
        assert "datetime" in said


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
