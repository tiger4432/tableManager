# -*- coding: utf-8 -*-
"""S-188 ⓔ. The chain skeleton and the loader name the same cells — counted, both ways.

🔴 WHY THIS EXISTS, in the words `test_ledger_skeleton` already uses: a skeleton is 「a SECOND
statement of a contract whose first author is the validator」, and two authors of one contract
drift in silence. The ledger paid for that concretely — its hand-written form offered
`emit.object` fields the validator had never allowed, and the owner's own live pack could not
be expressed through the form with nothing red anywhere.

⚠️ SO THE FILE IS GENERATED AND THIS TEST SCORES THE FILE AGAINST THE SYMBOLS. Not against a
list retyped here: the field names come from `chain_bindings.routing_keys()` and the required
set from `RULE_ROUTING_REQUIRED`, so this test cannot agree with a skeleton that is wrong.

🔴 AND IT PINS THAT NO NEW NODE KIND WAS INVENTED. The form renderer knows the ledger
skeleton's vocabulary — kinds `record`/`map`/`leaf`, hints `choice`/`free`/`ref`/`number`/
`flag`. A kind outside it draws NOTHING, which is how 「a contract adopted before its material
blanks the screen」 happened here before, so the vocabulary is read out of the LEDGER skeleton
and the chain one is required to stay inside it.
"""
import io
import json
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import chain_bindings                                                 # noqa: E402

CHAIN_SKELETON = os.path.join(server_dir, "chain_skeleton.json")
LEDGER_SKELETON = os.path.join(server_dir, "ledger", "ledger_skeleton.json")


def _load(path):
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _vocabulary(document):
    kinds, hints = set(), set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("kind"), str):
                kinds.add(node["kind"])
            if isinstance(node.get("hint"), str):
                hints.add(node["hint"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    return kinds, hints


def test_the_file_on_disk_is_what_the_code_generates():
    """🔴 THE DRIFT GATE. Add a routing cell and this goes red until the file is regenerated:

        python -c "import io,json,chain_bindings as cb; io.open('chain_skeleton.json','w',
            encoding='utf-8',newline='').write(json.dumps(cb.skeleton(),ensure_ascii=False,
            indent=2)+chr(10))"
    """
    assert _load(CHAIN_SKELETON) == chain_bindings.skeleton()


def test_the_skeleton_names_exactly_the_routing_cells():
    """Both directions. A cell in the skeleton the loader does not accept would offer an
    operator a box whose value is then refused; a cell the loader accepts but the skeleton
    omits is a field no form can ever fill."""
    fields = [f["key"] for f in _load(CHAIN_SKELETON)["root"]["fields"]]
    assert fields == list(chain_bindings.routing_keys())
    assert len(fields) == len(set(fields))


def test_required_means_what_the_loader_refuses_without():
    """⚠️ `required` HERE MUST BE THE LOADER'S `required`, not a form author's opinion about
    which boxes matter. `target_table`, `enabled` and `is_batch` are written by all ten
    shipped rules and are still OPTIONAL, because the code carries a default or the decorator
    can supply the value."""
    fields = _load(CHAIN_SKELETON)["root"]["fields"]
    marked = {f["key"] for f in fields if f["required"]}
    assert marked == set(chain_bindings.RULE_ROUTING_REQUIRED)
    for key in ("target_table", "enabled", "is_batch"):
        assert key not in marked, key


def test_no_node_kind_the_form_has_never_seen():
    """⛔ THE VOCABULARY IS READ OUT OF THE LEDGER SKELETON, not listed here — a list here
    would be a third statement of the same contract, which is the defect this file is about.
    """
    allowed_kinds, allowed_hints = _vocabulary(_load(LEDGER_SKELETON))
    kinds, hints = _vocabulary(_load(CHAIN_SKELETON))
    assert kinds <= allowed_kinds, sorted(kinds - allowed_kinds)
    assert hints <= allowed_hints, sorted(hints - allowed_hints)


def test_the_params_block_does_not_pretend_to_know_the_argument_names():
    """🔴 WHAT NAMES ARE LEGAL UNDER `params` IS THE MAPPER'S TO DECLARE (`@mapper(params=…)`),
    and `server/mappers/**` is the owner's and gitignored. A skeleton that enumerated them
    would be guessing at files the repository cannot read, and would go stale the first time
    an author added an argument."""
    params = [f for f in _load(CHAIN_SKELETON)["root"]["fields"]
              if f["key"] == chain_bindings.PARAMS_KEY]
    assert len(params) == 1
    node = params[0]["node"]
    assert node["kind"] == "map", "an open set of names is a map, not a record"
    assert "fields" not in node, "enumerating the argument names would be a guess"
