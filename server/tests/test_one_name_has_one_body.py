# -*- coding: utf-8 -*-
"""`_bare` 가 «한 이름에 네 본체»였던 자리 — 그리고 그것이 다시 자라지 못하게.

🔴 넷은 «같은 이름 · 같은 설명 · 다른 답»이었다. 각자의 docstring 이 전부
「버전은 선언의 것이지 이름의 것이 아니다」를 말하는데, 본체는 공백·대소문자·`None` 에서 갈렸다:

    ledger/gaps.py                   str(name).split("@")[0]
    ledger_api/ledger_subgraph.py    str(name or "").split("@", 1)[0]
    ledger_admin.py                  str(name or "").split("@", 1)[0].strip()
    ledger_api/declared_entities.py  str(...).split("@", 1)[0].strip().lower()

⚠️ 그리고 그 오독이 «읽는 사람 쪽»에서 실제로 일어났다 — 이 부류가 지시서에 「모듈 둘」로
적혔다. 이름으로 세면 둘이고 본체로 세면 넷이다. 오늘 안 갈려 있다는 것은 «안 갈린다»는 뜻이
아니라 오늘 그 입력이 안 왔다는 뜻이다.

🔵 이 라운드는 «회차 1**이다. 이름 붙은 넷을 한 몸통으로 접었고, 손으로 철자한 스물여덟은
그대로 있다 — 천장을 내리는 순서이지 한 번에 서른둘을 고치는 것이 아니다.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import declaration_names                                          # noqa: E402


# ------------------------------------------------------------------ the body itself

def test_the_version_is_dropped_not_used():
    assert declaration_names.bare_name("of_kind@1") == "of_kind"
    assert declaration_names.bare_name("wafer@1") == "wafer"


def test_a_name_without_a_version_is_unchanged():
    assert declaration_names.bare_name("wafer") == "wafer"


def test_none_is_an_empty_name_not_the_word_none():
    """🔴 THE ONE BEHAVIOUR THIS ROUND CHANGED, AND IT IS A REPAIR. `gaps.py`'s body ran
    `str(None)`, so a missing name became the string `"None"` — a name that exists in neither
    the declaration nor the ledger, and therefore matches nothing SILENTLY. An empty name at
    least reads as empty."""
    assert declaration_names.bare_name(None) == ""
    assert declaration_names.bare_name("") == ""


def test_surrounding_space_is_dropped():
    """Two of the four already did this; the two that did not were leaning on 「선언 파일이
    공백을 안 낳는다」, which stops being true the day a person edits one."""
    assert declaration_names.bare_name("  of_kind@1  ") == "of_kind"


def test_the_shared_body_does_not_fold_case():
    """🔴 THE OTHER THREE DEPEND ON CASE SURVIVING, and nothing said so until a mutant
    lifted `declared_entities`'s fold into the shared body and NOTHING went red. The
    declaration spells entity types with capitals in places (`Lot`, `Wafer`) and the walk
    compares them to what the ledger wrote; folding here would change three answers to fix
    one module's habit."""
    assert declaration_names.bare_name("Wafer@1") == "Wafer"
    assert declaration_names.bare_name("Lot") == "Lot"


def test_only_the_first_at_is_a_separator():
    """A second `@` belongs to the name, not to a second version."""
    assert declaration_names.bare_name("a@b@c") == "a"


# ------------------------------------------------------- one name, and now one body

def test_the_three_common_callers_share_one_function():
    """🔴 IDENTITY, NOT EQUALITY. Two functions that agree today are exactly what this file
    exists about; asserting `is` is what makes a re-copied body fail here."""
    import ledger_admin
    from ledger import gaps
    from ledger_api import ledger_subgraph

    assert gaps._bare is declaration_names.bare_name
    assert ledger_subgraph._bare is declaration_names.bare_name
    assert ledger_admin._bare is declaration_names.bare_name


def test_the_fourth_keeps_its_own_extra_and_only_that():
    """⚠️ `declared_entities` folds case as well, and that stays ITS extra. Lifting it into the
    shared body would quietly change the other three; leaving it as a fourth copy would leave
    the defect. It calls the shared body and adds one thing."""
    from ledger_api import declared_entities

    assert declared_entities._bare is not declaration_names.bare_name
    assert declared_entities._bare(" WAFER@1 ") == "wafer"
    # and the only difference is the case fold
    for spelling in ("Wafer@1", "of_kind@1", "", "a@b@c", "  LOT@2  "):
        assert (declared_entities._bare(spelling)
                == declaration_names.bare_name(spelling).lower())


def test_no_module_spells_the_body_under_this_name_again():
    """🔴 THE CEILING. A fifth `def _bare` is how this class was born; the count of them is
    the number this round lowered, and it must not rise."""
    import io
    import re

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    spelled = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "_archive", "tests",
                                                "scripts", ".tmp")]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            try:
                src = io.open(path, encoding="utf-8").read()
            except Exception:
                continue
            for match in re.finditer(r"^def _bare\b", src, re.M):
                spelled.append(os.path.relpath(path, root).replace("\\", "/"))
    # `declared_entities` is the one legitimate `def` — it adds the case fold.
    assert spelled == ["ledger_api/declared_entities.py"], spelled
