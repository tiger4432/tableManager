# -*- coding: utf-8 -*-
"""The form stops offering `references`, and the grammar keeps accepting it.

`references` has no reader - CODE_MAP records that across five layers, so there was
nothing left to measure. Offering it in the authoring form asks an operator to fill a
square that changes nothing, which is the standing ruling from 2026-08-20: a declaration
nothing can reach is not a contract, it is a copy.

⛔ THE GRAMMAR STAYS. Retiring the syntax is a bigger, separate change - every config
written with a `references` block would start failing validation - and the point here is
only to stop RECOMMENDING it. This test holds both halves apart, because doing one and
calling it the other is how a form fix turns into a broken deployment.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config_authoring, setup_bundle                # noqa: E402


def has_field(node, key):
    if isinstance(node, dict):
        if node.get("key") == key:
            return True
        return any(has_field(v, key) for v in node.values())
    if isinstance(node, list):
        return any(has_field(v, key) for v in node)
    return False


def test_the_form_no_longer_offers_references():
    assert not has_field(config_authoring.skeleton(), "references")


def test_the_neighbouring_field_survived():
    """The excision was surgical: `class` sits beside it in the same record and must not
    have gone with it."""
    assert has_field(config_authoring.skeleton(), "class")


def test_the_skeleton_is_still_whole():
    """A JSON file edited by hand is a JSON file that can stop parsing."""
    sk = config_authoring.skeleton()
    assert isinstance(sk, dict) and sk
    for key in ("entity_type", "keys", "vocabulary"):
        assert has_field(sk, key), "the skeleton lost %s" % key


def test_the_validator_still_knows_the_word():
    """⛔ NOT RETIRED. A config carrying `references` must still validate - the field is
    accepted where entities are checked, and the checker for it is still called."""
    import inspect

    src = inspect.getsource(setup_bundle)
    assert '"references"' in src, "the grammar stopped naming references"
    assert "_validate_references" in src, "the checker for references is gone"
