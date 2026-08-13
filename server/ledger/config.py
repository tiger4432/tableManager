"""`ledger_config.json` - the translator declarations, loaded and VALIDATED.

Every source the ledger reads gets one declaration here (design §1: "번역기 config -
소스마다 한 장"). What is declared, and why each item is a declaration rather than code:

  * `occurred_at_column` + `occurred_at_timezone` - risk control #2 of §10 and risk #2 of
    the brief. **A source with no declared time column is refused, not defaulted.** The
    failure this prevents is silent: substituting arrival time makes every atom look
    plausible and re-ordering a reload changes history.
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

        subject_type = source.get("subject_type")
        from . import vocabulary
        if subject_type not in vocabulary.ENTITY_TYPES:
            raise LedgerConfigError(
                f"{where}.subject_type {subject_type!r} is not a declared entity type "
                f"({', '.join(sorted(vocabulary.ENTITY_TYPES))})")

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
        for required in ("lot", "event_type", "slots", "wafers", "parent_lot",
                         "child_lot", "row_identity"):
            if not str(columns.get(required) or "").strip():
                raise LedgerConfigError(f"{where}.columns.{required} is not declared")

    batch = cfg.get("batch") or {}
    size = int(batch.get("molecules_per_transaction", 200))
    if size < 1:
        raise LedgerConfigError(f"{origin}: batch.molecules_per_transaction must be >= 1")
    return cfg


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


def declared_derivations(cfg: dict, source: str) -> frozenset:
    """The derivation names atoms from this source are allowed to carry.

    Assembled FROM the declaration rather than listed beside it: adding a rule to the
    config is what makes its derivation legal, so a translator cannot emit an atom under
    a rule the operator did not turn on.
    """
    source_cfg = source_config(cfg, source) or {}
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
