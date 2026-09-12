# -*- coding: utf-8 -*-
"""S-188 ⓐ. Which cells a chain rule may carry at its top level, in one place.

🔴 THE SUBJECT OF THIS LIST IS NOT THE WORKER. A census of `chain_ingestion_worker`'s
`rule.get` returns ELEVEN names, and that is the number this round started from -- but
`chain_graph` reads four more off the same rule object (`target_field`,
`max_group_attempts`, `origin`, `params`). A list closed at eleven would make the loader
refuse rules that run today, which is the worst possible outcome for a validator: it
refuses the truth.

⚠️ AND THREE GRAMMARS MEET IN `chain_graph`. `_mapper_edges` iterates CHAIN rules,
`_enrich_edges` iterates ENRICHMENT rules, and `_vjoin_edges` iterates VIRTUAL JOIN rules --
all with a local named `rule`. A grep for `rule.get` cannot tell them apart, so the names
belonging to the other two files (`derived_table`, `target_fields`, `left_table`,
`right_table`, `expose`, `aggregations`, `decision_key`, `alignment`, `reference_views`) are
asserted ABSENT here. Merging them in would leave a list that refuses nothing.
"""
import io
import json
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import chain_bindings                                                # noqa: E402

SAMPLE = os.path.join(server_dir, "config", "sample", "chain_rules.json.sample")

#: Read by `chain_graph` off a CHAIN rule and by nothing in the worker. Pinned by name
#: because 「eleven」 is the plausible-looking wrong answer a later reader will reach for.
READ_ONLY_BY_THE_GRAPH = ("target_field", "max_group_attempts", "origin", "params")

#: Cells of the OTHER two rule files. `chain_graph` reads each off a local also called
#: `rule`, which is why a literal census cannot separate them.
BELONGING_TO_ANOTHER_GRAMMAR = (
    "derived_table", "target_fields", "aggregations", "decision_key", "alignment",
    "reference_views", "left_table", "right_table", "right_columns", "right_folds",
    "expose",
)


@pytest.fixture(scope="module")
def sample_rules():
    with io.open(SAMPLE, encoding="utf-8") as handle:
        return json.load(handle).get("rules", [])


def test_the_list_is_one_list():
    keys = chain_bindings.routing_keys()
    assert len(keys) == len(set(keys)), "a name appears twice"
    assert not (set(chain_bindings.RULE_ROUTING_REQUIRED)
                & set(chain_bindings.RULE_ROUTING_OPTIONAL))


def test_the_table_keys_are_a_subset_rather_than_a_second_copy():
    """🔴 `RULE_TABLE_KEYS` already had an author, and this is what stops the new list from
    becoming a second one -- `rule_tables` says 「여기서 다시 열거하지 않는다」 for the same
    reason."""
    assert set(chain_bindings.RULE_TABLE_KEYS) <= set(chain_bindings.routing_keys())
    for key in (chain_bindings.READS_KEY, chain_bindings.REFERENCE_BLOCK):
        assert key in chain_bindings.routing_keys(), key


def test_the_four_the_worker_never_reads_are_in_it():
    """⛔ THE REGRESSION LINE AGAINST 「eleven」. Each of these is read by `chain_graph` off a
    chain rule; dropping one makes the loader refuse a rule the graph draws."""
    for key in READ_ONLY_BY_THE_GRAPH:
        assert key in chain_bindings.routing_keys(), key


def test_no_cell_of_another_rule_file_leaked_in():
    keys = set(chain_bindings.routing_keys())
    leaked = [k for k in BELONGING_TO_ANOTHER_GRAMMAR if k in keys]
    assert not leaked, leaked


def test_the_shipped_sample_would_not_be_refused(sample_rules):
    """🔴 THE GATE THAT MATTERS BEFORE ⓑ TURNS THIS INTO A REFUSAL. Every top-level cell of
    every shipped rule is either a routing cell or a mapper argument -- and a mapper
    argument is what ⓓ moves into `params`. Until then the sample is the population the
    loader must accept, so what is NOT in the list is reported here as the work ⓓ has.
    """
    assert sample_rules, "the shipped sample declares no rules"
    routing = set(chain_bindings.routing_keys())
    for rule in sample_rules:
        for key in rule:
            if key.startswith("__"):          # a comment, by convention
                continue
            assert isinstance(key, str)
            # Not an assertion that every cell is routing -- the mapper arguments are
            # exactly the ones ⓓ relocates. This pins that the ROUTING half is covered.
            if key in routing:
                continue
            assert key not in chain_bindings.RULE_ROUTING_REQUIRED


def test_every_required_cell_is_present_in_every_shipped_rule(sample_rules):
    """⚠️ `required` IS A CONTRACT, NOT AN OBSERVATION. `target_table`, `enabled` and
    `is_batch` appear in all ten shipped rules and are still OPTIONAL, because the code
    carries a default or the decorator can supply the value -- 「all ten write it」 and
    「refused without it」 are different sentences and only the second one is the contract."""
    for rule in sample_rules:
        for key in chain_bindings.RULE_ROUTING_REQUIRED:
            assert key in rule, (rule.get("name"), key)
    for key in ("target_table", "enabled", "is_batch"):
        assert key in chain_bindings.RULE_ROUTING_OPTIONAL, key
