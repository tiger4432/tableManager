# -*- coding: utf-8 -*-
"""S-177 ②: one typo stops ONE source, not the whole ledger.

판정 278·280.  A single declaration's fault refused the whole bundle, and a refused bundle
is a stopped ledger: the follow-up logged `batch failed` every lap and nothing translated.
In production that is one operator's typo standing fourteen ledgers up.

🔴 THE MECHANISM IS NOT NEW AND THIS FILE DOES NOT PIN A NEW ONE.
`config_explorer.resolve_declarations` has computed exactly this since it was built -- a
FIXPOINT over the validator we already have: drop what a problem blames, validate again,
and the cascade falls out because a dangling reference is reported on the REFERRER's own
path.  What was missing is that the LEDGER'S OWN LOADER never called it.  So what is pinned
here is the wiring and its consequences:

  * the healthy path is untouched and pays nothing;
  * a broken declaration falls ALONE and BY NAME, and the sources that named it fall with
    it -- that closure is the fixpoint's, not a second edge walk;
  * a refused source is REGISTERED rather than absent, because a source that vanishes
    reads to every screen as one the operator deleted;
  * `planned` is not `status` -- 「the operator retired it」 and 「the loader could not plan
    it」 must not render as the same pixel;
  * a healthy source's CURSOR FINGERPRINT does not move because a neighbour broke.  That
    one is the point of the whole round: a moved fingerprint stops that source's cursor,
    which is the disease being cured.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

# ⚠️ NOT `as setup_module`: pytest's xunit discovery calls a module-level name
# `setup_module(module)` as a fixture hook, and binding a MODULE to it fails with
# 「module has no attribute '__code__'」 on every test in the file.
from ledger import setup as ledger_setup                            # noqa: E402
from ledger.setup import LedgerSetupError, load_setup               # noqa: E402
from ledger.setup_registry import source_cursor_fingerprint         # noqa: E402

from test_ledger_setup_bundle import DEFAULT_CATALOG, logical_bundle  # noqa: E402
from test_ledger_setup_registry import trusted_implementations       # noqa: E402


HEALTHY = "input_rows"
BROKEN = "dt_log"


def two_source_document():
    """One plant, two sources reading two relations.  Both sound to start with.

    The plant's virtual join is switched OFF and neither source inherits it: an enabled
    rule demands a physical verification descriptor, which is a question about an index
    and says nothing about the declaration isolation under test here.
    """
    raw = copy.deepcopy(logical_bundle())
    raw["sources"][BROKEN] = copy.deepcopy(
        logical_bundle(source_name=BROKEN))["sources"][BROKEN]
    raw["virtual_joins"]["input_to_reference"]["enabled"] = False
    for source in raw["sources"].values():
        source["prepare"]["inherit_virtual_join_rules"] = []
    return raw


def write_root(tmp_path, document):
    root = tmp_path / "draft"
    root.mkdir(parents=True)
    (root / "ledger_config.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return root


@pytest.fixture(name="catalog", autouse=True)
def fixture_catalog(monkeypatch):
    """The fixture plant's physical and implementation halves, through the doors
    production reads.  Both are things a caller states rather than things this module
    discovers, which is why they are parameters in production too."""
    monkeypatch.setattr(ledger_setup, "live_physical_catalog", lambda: DEFAULT_CATALOG)
    monkeypatch.setattr(ledger_setup, "trusted_implementations", trusted_implementations)
    return DEFAULT_CATALOG


# ---------------------------------------------------------------------------
# 1. The healthy path is untouched
# ---------------------------------------------------------------------------

def test_a_sound_config_plans_every_source(tmp_path):
    setup = load_setup(write_root(tmp_path, two_source_document()))
    assert sorted(setup.snapshot.source_plans) == sorted([HEALTHY, BROKEN])
    assert all(plan.planned and plan.refusal is None
               for plan in setup.snapshot.source_plans.values())


# ---------------------------------------------------------------------------
# 2. One broken source falls alone
# ---------------------------------------------------------------------------

def broken_document():
    """`dt_log` names a column its relation does not have.  Nothing else is touched."""
    document = two_source_document()
    document["sources"][BROKEN]["read"]["order_by"] = ["no_such_column"]
    return document


def test_the_broken_source_falls_and_the_other_is_planned(tmp_path):
    setup = load_setup(write_root(tmp_path, broken_document()))

    assert sorted(setup.snapshot.source_plans) == sorted([HEALTHY, BROKEN]), (
        "a refused source must stay REGISTERED; vanishing reads as 'deleted'")
    healthy = setup.snapshot.source_plans[HEALTHY]
    assert healthy.planned is True and healthy.driver is not None

    broken = setup.snapshot.source_plans[BROKEN]
    assert broken.planned is False
    assert broken.driver is None and broken.profile is None
    # NAMED, not merely counted: the operator has to be sent to a place in the file.
    assert broken.refusal["path"].startswith("bundle.sources.%s" % BROKEN), broken.refusal
    assert broken.refusal["code"] and broken.refusal["message"]
    # 🔴 AND `status` IS STILL WHAT THE OPERATOR WROTE. Folding this into `status` would
    # tell every screen they retired it.
    assert broken.status == "active"
    # The relation survives, because 「which table did this stop reading」 is the first
    # question asked about a source that is not running.
    assert broken.relation == BROKEN


def test_nothing_runs_the_refused_source(tmp_path):
    """`runs` is the one predicate, and it has to answer for BOTH ways a source stops."""
    setup = load_setup(write_root(tmp_path, broken_document()))
    assert setup.snapshot.source_plans[HEALTHY].runs is True
    assert setup.snapshot.source_plans[BROKEN].runs is False
    with pytest.raises(LedgerSetupError) as refused:
        ledger_setup._require_declared_source(setup, BROKEN)
    assert refused.value.code == "source_refused"


# ---------------------------------------------------------------------------
# 3. 🔴 The neighbour's cursor does not move.  This is the point of the round.
# ---------------------------------------------------------------------------

def test_the_healthy_sources_fingerprint_is_unchanged_by_the_neighbours_fault(tmp_path):
    """A moved fingerprint stops that source's cursor. If breaking `dt_log` moved
    `input_rows`' fingerprint, this round would have replaced one stop with another."""
    before = load_setup(write_root(tmp_path / "a", two_source_document()))
    after = load_setup(write_root(tmp_path / "b", broken_document()))

    assert (source_cursor_fingerprint(before.snapshot, HEALTHY)
            == source_cursor_fingerprint(after.snapshot, HEALTHY))


def test_the_refused_source_has_no_fingerprint_and_says_so(tmp_path):
    """⛔ NOT A HASH OF NOTHING, and not an `AttributeError` in whichever loop asked."""
    from ledger.setup_bundle import LedgerSetupValidationError

    setup = load_setup(write_root(tmp_path, broken_document()))
    with pytest.raises(LedgerSetupValidationError) as refused:
        source_cursor_fingerprint(setup.snapshot, BROKEN)
    assert refused.value.code == "source_refused"


# ---------------------------------------------------------------------------
# 4. The closure: a broken PREDICATE takes the sources that name it
# ---------------------------------------------------------------------------

def test_a_broken_predicate_takes_only_the_sources_that_name_it(tmp_path):
    """The cascade is the fixpoint's -- drop the predicate, validate again, and the source
    that binds it is blamed on ITS OWN path in the next round."""
    document = two_source_document()
    document["vocabulary"]["moves_to@1"]["colour"] = "blue"     # unknown field
    # Give the healthy source a predicate of its own so the two do not share one.
    document["vocabulary"]["stays_at@1"] = copy.deepcopy(
        document["vocabulary"]["moves_to@1"])
    document["vocabulary"]["stays_at@1"].pop("colour")
    for mapping in document["sources"][HEALTHY]["bind"]["mappings"].values():
        mapping["predicate"] = "stays_at@1"

    setup = load_setup(write_root(tmp_path, document))
    assert setup.snapshot.source_plans[HEALTHY].planned is True
    assert setup.snapshot.source_plans[BROKEN].planned is False
    # The reason points at the PREDICATE or at the sentence that names it -- either way it
    # is a place in the file, never a bare 「could not load」.
    assert setup.snapshot.source_plans[BROKEN].refusal["path"]


# ---------------------------------------------------------------------------
# 5. Nothing left to read is a refusal, not an empty load
# ---------------------------------------------------------------------------

def test_a_config_whose_every_source_falls_is_refused_by_name(tmp_path):
    """⛔ ZERO PLANS IS NOT A LOAD (판정 280 ⓒ). An empty ledger that compiled cleanly is
    a ledger standing still with nothing saying why."""
    document = two_source_document()
    for source_id in (HEALTHY, BROKEN):
        document["sources"][source_id]["read"]["order_by"] = ["no_such_column"]

    with pytest.raises(LedgerSetupError) as refused:
        load_setup(write_root(tmp_path, document))
    assert refused.value.code == "every_source_refused"
    # Each source's OWN reason, because they are fixed one at a time.
    for source_id in (HEALTHY, BROKEN):
        assert source_id in refused.value.message


# ---------------------------------------------------------------------------
# 6. The mutation: put the all-or-nothing back and this goes red
# ---------------------------------------------------------------------------

def test_without_the_resolver_one_typo_refuses_the_whole_bundle(tmp_path, monkeypatch):
    """Substituted through `import`, and the substitution is asserted."""
    from ledger.setup_bundle import LedgerSetupValidationError

    def _all_or_nothing(root_path, catalog, first):
        raise first

    monkeypatch.setattr(ledger_setup, "_resolve_refused_declarations", _all_or_nothing)
    with pytest.raises(LedgerSetupValidationError):
        ledger_setup._resolve_refused_declarations(
            None, None, LedgerSetupValidationError("x", "y", "z"))

    with pytest.raises(LedgerSetupValidationError):
        load_setup(write_root(tmp_path, broken_document()))


def test_a_root_document_fault_is_still_refused_whole(tmp_path):
    """⚠️ THE NARROW DOOR. Only a DECLARATION-level failure is resolved; a fault the root
    checks raise blames no declaration, and dropping things can never clear it."""
    root = tmp_path / "draft"
    root.mkdir(parents=True)
    (root / "ledger_config.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(Exception) as refused:
        load_setup(root)
    assert "every_source_refused" not in str(refused.value)


# ---------------------------------------------------------------------------
# 7. A broken VIRTUAL JOIN RULE, and the sources that inherit it
# ---------------------------------------------------------------------------

def bundle_with_a_broken_join_rule():
    """The rule `input_to_reference` is broken; `input_rows` inherits it, `dt_log` does not.

    판정, 2026-09-11: the unit rule already makes `bundle.virtual_joins.<rule>` a path root,
    so a fixpoint that blames the rule should take the rule and its inheritors and leave the
    unrelated source running. This test is the confirmation the ruling asked for -- it is
    not a new mechanism, and if the answer is no, the answer is the finding.
    """
    raw = two_source_document()
    raw["virtual_joins"]["input_to_reference"]["enabled"] = True
    raw["virtual_joins"]["input_to_reference"]["colour"] = "blue"   # unknown field
    raw["sources"][HEALTHY]["prepare"]["inherit_virtual_join_rules"] = [
        "input_to_reference"]
    return raw


def test_a_broken_join_rule_takes_only_the_sources_that_inherit_it(tmp_path):
    """판정 281. A broken rule falls WITH its inheritors, and the bundle survives.

    ⚰️ THIS TEST ASSERTED THE OPPOSITE ONE COMMIT AGO, and the reversal is the point.
    Measured then: `resolve_declarations` blamed through `ground_node_key`, which reads
    the AUTHORING map -- vocabulary, entities, sources -- so a broken join rule blamed
    NOTHING, landed in the config-level list, and refused the whole bundle. The ruling
    split the maps rather than widening the authoring one, and this is the same fixture
    reading the same way with the answer it should always have had.
    """
    document = bundle_with_a_broken_join_rule()
    setup = load_setup(write_root(tmp_path, document))

    # The bundle LOADS. That is the whole of it: one typo in one rule used to stop every
    # ledger on the deployment.
    inheritor = setup.snapshot.source_plans[HEALTHY]
    bystander = setup.snapshot.source_plans[BROKEN]

    assert inheritor.planned is False, (
        "a source whose declared join rule is gone cannot keep its own declaration")
    assert "input_to_reference" in str(inheritor.refusal), inheritor.refusal
    assert bystander.planned is True, (
        "the source that never named the rule is nobody's casualty")


def test_the_loader_isolates_a_join_rule_and_the_screen_still_does_not_author_one():
    """The two maps, side by side, because they answer two questions (판정 281).

    Widening the AUTHORING map would have put a new declaration kind on the explorer's
    surface -- an operator could then create and delete join rules from a screen that was
    never designed to. The loading map is the one that had to grow.
    """
    from ledger.config_authoring import ground_node_key, isolation_key
    from ledger.config_explorer import AUTHORABLE_SECTION_NAMES, ISOLATION_ROOTS

    rule_path = "bundle.virtual_joins.input_to_reference.join_key"
    assert isolation_key(rule_path) == "virtual_join|input_to_reference"
    # 🔴 UNCHANGED, and asserted rather than assumed: the screen's surface did not move.
    assert ground_node_key(rule_path) is None
    assert "virtual_joins" not in AUTHORABLE_SECTION_NAMES
    assert "virtual_joins" in ISOLATION_ROOTS
    assert AUTHORABLE_SECTION_NAMES < ISOLATION_ROOTS, (
        "the loading map must stay a strict superset, or a section becomes authorable "
        "without becoming isolatable")

    # The three that were already isolatable still are, and read the same on both maps.
    for path, key in (
        ("bundle.sources.dt_log.read", "source_plan|dt_log"),
        ("bundle.vocabulary.moves_to@1.object", "predicate|moves_to@1"),
        ("bundle.entities.InputEntity@1.keys", "entity|InputEntity@1"),
    ):
        assert isolation_key(path) == key
        assert ground_node_key(path) == key

    # And neither map blames something that is not a declaration at all.
    assert isolation_key("bundle.setup_version") is None
