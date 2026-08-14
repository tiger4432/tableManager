"""`ledger_config.json` - the translator declarations, loaded and VALIDATED.

Every source the ledger reads gets one declaration here (design §1: "번역기 config -
소스마다 한 장"). What is declared, and why each item is a declaration rather than code:

  * `occurred_at_column` + `occurred_at_timezone` - risk control #2 of §10 and risk #2 of
    the brief. **A source with no declared time column is refused, not defaulted.** The
    failure this prevents is silent: substituting arrival time makes every atom look
    plausible and re-ordering a reload changes history.
  * `subject_types` - the EXTENSION of this source's translator: the entity types its
    atoms are allowed to be about. 🔴 It is a plural allow-list and it BITES - `gate`
    refuses an atom whose `subject_type` is outside it by name
    (`undeclared_subject_type`). Ruling R-2026-08-13-D is why both halves of that
    sentence are here: the field used to be singular `subject_type`, it was assigned once
    in the translator and read NOWHERE (every call site passes a literal), so
    `validate()` was checking a value that reached no atom - a declaration teaching the
    reader a contract nothing enforced. The literals stay in code, because the code owns
    the FACT of each atom; this declaration owns the allowed RANGE of those facts, and a
    translator that quietly starts minting a new type is now a counted refusal instead of
    a discovery. **The standing rule it promoted: a declaration field has an enforcement
    point, or it does not exist.**
  * `vocabulary` - which source `event_type`s are understood, and what each one produces.
    An `event_type` absent from this map is refused and counted; it is NOT skipped.
  * `slot_pairing` - 🔴 THE JUDGEMENT CALL OF THIS SLICE, and it is config precisely so
    that it is a judgement somebody made rather than one the translator made:

      - `shared_wafer` - emit `slot_map` only where the SAME wafer id is uttered on both
        rows of the molecule. Zero inference. On `lot_event` this yields atoms for
        merges (the source lot's row is a pre-move snapshot, so the moved wafers appear
        on both sides) and NOTHING for splits (the child's wafers have already left the
        parent's row, so the parent never says where they sat).
      - `slot_preserving` - the operator declares "this source's splits keep slot
        numbers", so each (slot, wafer) on the child row yields `from == to`. That
        convention is the product owner's own statement, not a pattern this translator
        found in the data; declaring it here is what keeps atomicity check ③ honest,
        because the declaration is hashed into `source_translator_ver` and every atom
        therefore carries which convention produced it. If the convention is ever found
        false, `source_raw_ref` re-utters the source rows and the atoms are re-derived.
      - `none` - this event type produces no slot map.

  * `molecules_per_transaction` - how many WHOLE source events share a transaction. Never
    a fraction of one (see `backfill.py`).

🔴 `kind` - WHICH GRAMMAR A SOURCE SPEAKS (ruling R-2026-08-14-D)
------------------------------------------------------------------
`lot_event` is a LINEAGE source: two rows make one event, and its columns are lots, slots
and parent/child. `void_obs` is an OBSERVATION source: one row IS one utterance, its
columns are a finding's position and extent, and its world time is not even on the row -
it belongs to the inspection run that produced it. Validating the second against the
first's required column list would have refused it for not having a `parent_lot`.

So `kind` names the grammar and the validation dispatches on it. It DEFAULTS to `lineage`,
which is what keeps every declaration written before this ruling valid unchanged - and the
default is a fact about history, not a preference: a source that does not say is the one
shape this file already knew.

An observation source additionally declares its RUN - the inspection execution that
produced the finding:

    "run": {"relation": "inspection_run", "key_column": "run_uid",
            "method_column": "method"}

and its `occurred_at_column` is read from THAT relation, not from the observation row.
That is not a convenience: a finding has no time of its own, it has the time of the look
that found it, and inventing one from `created_at` would be arrival time wearing a
world-time hat - risk 1 of design §10, one table over.

🔴 `watermark` - WHERE AN OBSERVATION SOURCE'S CURSOR LIVES
------------------------------------------------------------
A lineage source's cursor is its world time. An observation source's cannot be: every row
of a bulk load shares one `updated_at` (measured on this box: 91,756 `void_obs` rows across
92 distinct values), so a time cursor would put a whole load in one indivisible group. The
declared watermark is therefore a KEYSET - `(updated_at, row_id)` - which is unique,
monotone under both insert and edit, and index-backed (`idx_void_obs_updated`). Declaring
the columns rather than assuming them is what lets a source whose editor stamps a
different column say so.

RELOAD POLICY
-------------
Read once per RUN, not per row. `crud`'s own hard-won rule (QA D1/F4): re-reading config
per access makes the snapshot shift mid-job and can turn a 0-row write into a SUCCESS,
while caching it forever kills hot reload. A backfill run is the job boundary here, so
the snapshot is taken at the top of the run and passed down as an argument.
"""
from __future__ import annotations

import hashlib
import json
import os

CONFIG_FILENAME = "ledger_config.json"

#: The pairing strategies this translator implements. A config naming anything else is a
#: startup error rather than a runtime surprise - a misspelled strategy that silently
#: fell back to "none" would produce a ledger with no slot chain and no complaint.
SLOT_PAIRING_STRATEGIES = frozenset({"shared_wafer", "slot_preserving", "none"})
LINEAGE_STRATEGIES = frozenset({"parent_child", "none"})

#: The grammars a source may declare. `lineage` is the default and the one every
#: declaration written before ruling R-2026-08-14-D speaks.
SOURCE_KIND_LINEAGE = "lineage"
SOURCE_KIND_OBSERVATION = "observation"
SOURCE_KINDS = frozenset({SOURCE_KIND_LINEAGE, SOURCE_KIND_OBSERVATION})

#: Columns a LINEAGE source must map. Named here rather than inline so the observation
#: list beside it is visibly a different list rather than an exception to this one.
LINEAGE_REQUIRED_COLUMNS = ("lot", "event_type", "slots", "wafers", "parent_lot",
                            "child_lot", "row_identity")

#: Columns an OBSERVATION source must map. Everything else about a finding - where on the
#: chip, how big, which class - is OPTIONAL, because a source that does not utter a thing
#: must be able to say so by leaving it out rather than by declaring a column that does
#: not exist. These three are the ones without which there is no atom at all: the route
#: back to the row, the subject it is about, and the run that makes it countable.
OBSERVATION_REQUIRED_COLUMNS = ("row_identity", "wafer", "run_key")

#: The optional ones, listed so a typo in a declaration is caught rather than silently
#: producing an atom with a field missing. Add-only; a name absent from here is refused.
OBSERVATION_OPTIONAL_COLUMNS = ("die_x", "die_y", "die_gate", "inchip_x", "inchip_y",
                                "extent_x", "extent_y", "unit", "class")

#: The derivation an observation atom carries: ONE source row, uttered as it stands.
DERIVATION_OBSERVATION_ROW = "observation_row"

#: 🔴 The predicate an observation source's translator emits. ONE SPELLING, because two
#: modules need it: the translator that writes it and `ledger_kinds`, which answers「이
#: 종류가 원장에 있는가」by asking which declaration carries which kind under which word.
#: A literal in each would be a linkage that agrees on the day it is written and silently
#: stops agreeing the day the word changes.
OBSERVATION_PREDICATE = "observed"

#: The shape a source's timestamps are read in when the source declares no
#: `occurred_at_format`. Product owner ruling 2026-08-13: fab timestamps are ISO 8601
#: with the `T` separator (`2026-08-13T13:45:00`), so the default names what production
#: actually emits. `store._candidate_formats` reads the RFC 3339 space spelling of this
#: same shape as well, which is why a development box holding `2026-08-13 13:45:00` is
#: not a second format.
#:
#: One constant rather than one literal per caller: the translator and the lag report
#: both fall back to it, and two copies of a default are two things that drift apart
#: silently - the reader would then disagree with the lag report about what the cursor
#: position means.
DEFAULT_OCCURRED_AT_FORMAT = "%Y-%m-%dT%H:%M:%S"


class LedgerConfigError(ValueError):
    """The declaration is missing or self-contradictory. Raised at load, never later."""


def _config_dir():
    try:
        import paths
        return paths.CONFIG_DIR
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config")


def config_path(filename: str = CONFIG_FILENAME) -> str:
    return os.path.join(_config_dir(), filename)


def load(path: str = None) -> dict:
    """Load and validate. Falls back to `<name>.sample` when the live file is absent.

    The `.sample` fallback is this project's convention for gitignored operator config
    (`server/config/*.json` is the operator's, `*.json.sample` is what ships). Without it
    a fresh checkout could not run the backfill at all, and "it works on the box that has
    the untracked file" is not a deployable state.
    """
    path = path or config_path()
    if not os.path.exists(path):
        sample = path + ".sample"
        if os.path.exists(sample):
            path = sample
        else:
            raise LedgerConfigError(
                f"no ledger configuration at {path} (and no .sample beside it). The "
                f"translator refuses to run rather than guess a time column.")
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    validate(raw, origin=path)
    raw["__origin__"] = path
    return raw


def validate(cfg: dict, origin: str = "<memory>"):
    """Raise `LedgerConfigError` on anything the translator would otherwise have to
    guess about. Returns `cfg` so it can be used inline."""
    if not isinstance(cfg, dict):
        raise LedgerConfigError(f"{origin}: the configuration must be an object")
    sources = cfg.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise LedgerConfigError(f"{origin}: 'sources' must declare at least one source")

    for name, source in sources.items():
        where = f"{origin}: sources.{name}"
        if not isinstance(source, dict):
            raise LedgerConfigError(f"{where} must be an object")

        if not str(source.get("occurred_at_column") or "").strip():
            raise LedgerConfigError(
                f"{where}.occurred_at_column is not declared. Design §10 risk 1 and the "
                f"brief's risk 2: the world time must come from a named source column, "
                f"and arrival time may never stand in for it. Declare the column or "
                f"remove the source.")
        if not str(source.get("occurred_at_timezone") or "").strip():
            raise LedgerConfigError(
                f"{where}.occurred_at_timezone is not declared. The source's timestamps "
                f"are naive text; without a declared zone the stored instant would be "
                f"whatever the translating machine happened to be set to.")

        from . import vocabulary
        if "subject_type" in source:
            # The retired singular. Errors rather than being ignored, and the message
            # carries the fix: a config that silently means nothing is the defect ruling
            # R-2026-08-13-D exists to end, so the one thing this must NOT do is accept
            # the old key and quietly do something else with it.
            raise LedgerConfigError(
                f"{where}.subject_type (singular) was retired by ruling R-2026-08-13-D. "
                f"It reached no atom - the translator names each atom's type as a literal "
                f"- so it declared a contract nothing enforced. Rename it to "
                f"'subject_types' and give it the LIST of every entity type this source "
                f"may speak about, e.g. \"subject_types\": [\"Lot\", \"Wafer\"]. That list "
                f"is enforced: an atom outside it is refused by name "
                f"('undeclared_subject_type').")

        subject_types = source.get("subject_types")
        if not isinstance(subject_types, list) or not subject_types:
            raise LedgerConfigError(
                f"{where}.subject_types must be a non-empty LIST of the entity types this "
                f"source's atoms may be about ({', '.join(sorted(vocabulary.ENTITY_TYPES))}"
                f"). It is the translator's declared extension and the gate refuses "
                f"anything outside it, so an absent list would refuse every atom.")
        for member in subject_types:
            if member not in vocabulary.ENTITY_TYPES:
                raise LedgerConfigError(
                    f"{where}.subject_types names {member!r}, which is not a declared "
                    f"entity type ({', '.join(sorted(vocabulary.ENTITY_TYPES))}). Adding "
                    f"an entity type is a vocabulary decision, not a config one.")

        kind = source.get("kind", SOURCE_KIND_LINEAGE)
        if kind not in SOURCE_KINDS:
            raise LedgerConfigError(
                f"{where}.kind {kind!r} is not one of {sorted(SOURCE_KINDS)}. The kind "
                f"selects which grammar this source's translator speaks, so a misspelling "
                f"would validate the declaration against the wrong required columns.")
        if kind == SOURCE_KIND_OBSERVATION:
            _validate_observation_source(source, where)
            continue

        vocab = source.get("vocabulary")
        if not isinstance(vocab, dict) or not vocab:
            raise LedgerConfigError(
                f"{where}.vocabulary must map at least one source event type to a rule. "
                f"An empty map means every event is refused, which is legal but is never "
                f"what somebody meant to write.")
        for event_type, rule in vocab.items():
            rule_where = f"{where}.vocabulary.{event_type}"
            if not isinstance(rule, dict):
                raise LedgerConfigError(f"{rule_where} must be an object")
            lineage = rule.get("lineage", "none")
            if lineage not in LINEAGE_STRATEGIES:
                raise LedgerConfigError(
                    f"{rule_where}.lineage {lineage!r} is not one of "
                    f"{sorted(LINEAGE_STRATEGIES)}")
            pairing = rule.get("slot_pairing", "none")
            if pairing not in SLOT_PAIRING_STRATEGIES:
                raise LedgerConfigError(
                    f"{rule_where}.slot_pairing {pairing!r} is not one of "
                    f"{sorted(SLOT_PAIRING_STRATEGIES)}. A misspelling here would "
                    f"silently produce a ledger with no slot chain.")
            if pairing != "none" and lineage == "none":
                raise LedgerConfigError(
                    f"{rule_where}: slot_pairing {pairing!r} needs a parent/child pair, "
                    f"but lineage is 'none' - there would be no two lots to map between")

        columns = source.get("columns")
        if not isinstance(columns, dict):
            raise LedgerConfigError(f"{where}.columns must map logical names to source "
                                    f"columns")
        for required in LINEAGE_REQUIRED_COLUMNS:
            if not str(columns.get(required) or "").strip():
                raise LedgerConfigError(f"{where}.columns.{required} is not declared")

    batch = cfg.get("batch") or {}
    size = int(batch.get("molecules_per_transaction", 200))
    if size < 1:
        raise LedgerConfigError(f"{origin}: batch.molecules_per_transaction must be >= 1")
    return cfg


def _validate_observation_source(source: dict, where: str):
    """Ruling R-2026-08-14-D's declaration, checked. Every rule here has a consumer.

    🔴 The one that matters most is `run`. An observation with no inspection run is an
    observation with no denominator, and the `observed` signature makes `run_uid` a
    REQUIRED payload field precisely so that such an atom cannot be written. If the
    declaration did not have to name the run relation, the translator would have nothing
    to read it from and every atom would be refused at the gate for a reason that pointed
    at the wrong file.
    """
    finding_kind = str(source.get("finding_kind") or "").strip()
    if not finding_kind:
        raise LedgerConfigError(
            f"{where}.finding_kind is not declared. An observation source translates ONE "
            f"kind of finding (`server/finding_kinds.py` is the registry of what a kind "
            f"is), and the value lands in every atom's payload - guessing it from the "
            f"table name would put an unreviewed word in the ledger.")

    run = source.get("run")
    if not isinstance(run, dict):
        raise LedgerConfigError(
            f"{where}.run must declare the inspection run this source's findings belong "
            f"to: {{\"relation\": ..., \"key_column\": ..., \"method_column\": ...}}. "
            f"It is where `occurred_at` is read from (a finding has the time of the LOOK "
            f"that found it) and it is the denominator - `observed` requires `run_uid` in "
            f"its payload, so a source with no run declaration can produce no atoms.")
    for field in ("relation", "key_column"):
        if not str(run.get(field) or "").strip():
            raise LedgerConfigError(f"{where}.run.{field} is not declared")

    watermark = source.get("watermark")
    if not isinstance(watermark, dict) or not watermark.get("columns"):
        raise LedgerConfigError(
            f"{where}.watermark must declare the cursor columns, e.g. "
            f"{{\"columns\": [\"updated_at\", \"row_id\"]}}. An observation source cannot "
            f"use a world-time cursor: a bulk load stamps one `updated_at` on every row, "
            f"so the whole load would be one indivisible group. The declared keyset must "
            f"be UNIQUE and index-backed.")
    columns_declared = [str(c).strip() for c in watermark["columns"]]
    if not all(columns_declared):
        raise LedgerConfigError(f"{where}.watermark.columns holds a blank column name")

    columns = source.get("columns")
    if not isinstance(columns, dict):
        raise LedgerConfigError(f"{where}.columns must map logical names to source "
                                f"columns")
    for required in OBSERVATION_REQUIRED_COLUMNS:
        if not str(columns.get(required) or "").strip():
            raise LedgerConfigError(
                f"{where}.columns.{required} is not declared. An observation atom needs "
                f"the route back to its row, the wafer it is about, and the run that "
                f"makes it countable; the rest of a finding is optional because a source "
                f"that does not utter a thing must be able to stay silent about it.")
    known = set(OBSERVATION_REQUIRED_COLUMNS) | set(OBSERVATION_OPTIONAL_COLUMNS)
    # `__`-prefixed keys are this config file's comment convention (every block carries
    # them and `ledger_structure` already filters on the same prefix). They are not
    # mappings and must not be judged as ones.
    undeclared = sorted(name for name, value in columns.items()
                        if not name.startswith("__") and name not in known
                        and value is not None)
    if undeclared:
        raise LedgerConfigError(
            f"{where}.columns names {', '.join(undeclared)}, which this translator does "
            f"not read (known: {', '.join(sorted(known))}). A mapping nothing consumes is "
            f"a declaration that teaches the reader a contract nobody enforces - ruling "
            f"R-2026-08-13-D - and here it would usually be a typo for one that IS read.")
    if "vocabulary" in source:
        raise LedgerConfigError(
            f"{where}.vocabulary is a LINEAGE declaration (it maps source event types to "
            f"lineage rules) and an observation source has no event types - one row is one "
            f"utterance. Remove it, or set kind to '{SOURCE_KIND_LINEAGE}'.")


def source_kind(cfg: dict, source: str) -> str:
    """Which grammar a source speaks. Absent means `lineage` - see the module docstring."""
    return (source_config(cfg, source) or {}).get("kind", SOURCE_KIND_LINEAGE)


def source_config(cfg: dict, source: str) -> dict:
    """The declaration for one source, or `None`. `None` is a refusal, not a default."""
    return (cfg.get("sources") or {}).get(source)


def translator_version(cfg: dict, source: str) -> str:
    """`<source>/<config version>/rules:<8 hex>` - the value stamped into every atom.

    The hash covers the source's ENTIRE declaration, so two boxes running different
    `slot_pairing` rules produce atoms that are visibly different in provenance rather
    than invisibly different in meaning. That is what makes the `slot_preserving`
    judgement above auditable instead of merely documented: an atom carries which
    convention made it, and `source_raw_ref` carries how to redo it.
    """
    source_cfg = source_config(cfg, source) or {}
    material = json.dumps(source_cfg, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]
    return f"{source}/{cfg.get('version', 0)}/rules:{digest}"


def declared_subject_types(cfg: dict, source: str) -> frozenset:
    """The entity types atoms from this source are allowed to be about.

    Same shape and same direction as `declared_derivations` below: an undeclared source
    yields the EMPTY set, which refuses everything rather than allowing everything. A
    permissive default here would put the decoy back - the gate would hold a list that
    never says no, which is indistinguishable from having no list at all.
    """
    source_cfg = source_config(cfg, source) or {}
    return frozenset(source_cfg.get("subject_types") or ())


def declared_derivations(cfg: dict, source: str) -> frozenset:
    """The derivation names atoms from this source are allowed to carry.

    Assembled FROM the declaration rather than listed beside it: adding a rule to the
    config is what makes its derivation legal, so a translator cannot emit an atom under
    a rule the operator did not turn on.
    """
    source_cfg = source_config(cfg, source) or {}
    if source_cfg.get("kind") == SOURCE_KIND_OBSERVATION:
        # One row, uttered as it stands. There is no second rule here and that is the
        # point of the grammar: an observation source has nothing to infer, so a
        # translator that ever needed a second derivation would be doing something the
        # declaration never allowed.
        names = {DERIVATION_OBSERVATION_ROW}
        if source_cfg.get("register_entity_types"):
            names.add("first_sight")
        return frozenset(names)
    names = {"positional_row"}          # (slot[i], wafer[i]) on one row - always uttered
    for rule in (source_cfg.get("vocabulary") or {}).values():
        if rule.get("lineage") == "parent_child":
            names.add("pair_field")     # parent_lot / child_lot named on the row itself
        pairing = rule.get("slot_pairing", "none")
        if pairing != "none":
            names.add(pairing)
        if rule.get("emit_register", True):
            names.add("first_sight")    # register, on first appearance of an entity
    return frozenset(names)
