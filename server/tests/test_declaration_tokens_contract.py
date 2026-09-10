# -*- coding: utf-8 -*-
"""선언 토큰의 «서버 반쪽» — 서버가 정본이다 (S-135, 판정 18:16).

🔴 WHAT WAS ASYMMETRIC. The client froze these seven in `DECLARATION_TOKENS`
(`client2/src/map2/declaration.js`); the server had no name binding them at all - seven
constants scattered across `map_overlay.py` and nothing that said they were one vocabulary.
One side could add a token and the other would say nothing, which is the shape where two
answers about one map quietly diverge.

⛔ EQUALITY, NOT CONTAINMENT, AND THAT IS THE WHOLE POINT OF THE DIRECTION. The server is
canonical, so moving a token there must turn THIS red - the vectors are then updated
deliberately, in the same commit, by somebody who knows why. Containment would let the
server grow a token this file never learned and stay green, which is the drift the contract
exists to catch. The CLIENT measures itself against the same file as a subset, because a
client that has not learned a new token yet is behind rather than wrong.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import map_overlay                                                    # noqa: E402

_VECTORS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "contracts", "declaration_tokens",
    "vectors.json"))


def _vectors():
    return json.load(io.open(_VECTORS, encoding="utf-8"))


def test_the_vectors_are_exactly_what_the_server_declares():
    assert set(_vectors()["tokens"]) == set(map_overlay.GEOMETRY_TOKENS)


def test_there_are_seven_of_them_and_they_are_the_ones_the_client_froze():
    """⚠️ THE COUNT IS PINNED SEPARATELY FROM THE SET. An equality that both sides edit in
    one commit can drift as a pair; the number is what makes an accidental sixth or eighth
    visible in the diff."""
    tokens = set(map_overlay.GEOMETRY_TOKENS)

    assert len(tokens) == 7, sorted(tokens)
    assert tokens == {"declared", "auto_registered", "absent", "unparsable",
                      "indeterminate", "assumed", "confirmed"}


def test_the_set_is_built_from_the_constants_and_spells_nothing_twice():
    """🔴 NO NEW SPELLINGS. A token written as a literal inside the set would keep its OLD
    value if somebody moved the constant, and this contract would stay green while the two
    sides disagreed - `map_overlay` says as much beside `GEOMETRY_CONFIRMED`: moving that
    token moves what `map_alignment` trusts."""
    import inspect
    import re

    source = inspect.getsource(map_overlay)
    body = source[source.index("GEOMETRY_TOKENS = frozenset({"):]
    body = body[:body.index("})") + 2]

    assert not re.search(r'["\']', body), body
    for name in ("GEOMETRY_DECLARED", "GEOMETRY_AUTO_REGISTERED", "GEOMETRY_ABSENT",
                 "GEOMETRY_UNPARSABLE", "ORIENTATION_INDETERMINATE", "GEOMETRY_ASSUMED",
                 "GEOMETRY_CONFIRMED"):
        assert name in body, name


def test_it_is_a_frozenset_so_a_reader_cannot_edit_the_vocabulary():
    assert isinstance(map_overlay.GEOMETRY_TOKENS, frozenset)


def test_the_capture_command_is_recorded_where_the_next_person_will_look():
    """⚠️ THE VECTORS ARE CAPTURED, NEVER TYPED. A hand-edited contract file is a second
    spelling of the thing it exists to compare against, so the command that produces it
    lives in the file it produces."""
    comment = " ".join(_vectors()["$comment"])

    assert "GEOMETRY_TOKENS" in comment
    assert "CAPTURE" in comment
