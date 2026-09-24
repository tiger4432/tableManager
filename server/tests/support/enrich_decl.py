# -*- coding: utf-8 -*-
"""An enrich declaration, written the ONE way the product reads it.

소유자 2026-09-23 「enrich.json 아예 삭제라운드 만들어」 — `enrichment_rules.json` is retired and
an enrich declaration lives only in `chain_rules.json` as a `derive.decide` block. Many tests
still think in the flat cells (`source_table` · `derived_table` · `decision_key` · ...), because
those are also the names of the NORMALIZED declaration every consumer reads. This turns those
cells into the declaration an operator would write, so the files that need it do not each
carry a copy of the spelling.

Every flat cell has a home (measured 2026-09-24 against `rule_shape.DECIDE_CELLS`):
    source_table · derived_table     -> on.table · into.table
    decision_key · target_fields     -> decide.key · decide.fields
    enabled                          -> the declaration's own top level
    everything else                  -> decide, under the same name
"""
import json

#: The two cells the unified grammar spells differently - the inverse of
#: `rule_shape._DECIDE_TO_ENRICHMENT`, which is the product's own table.
_TO_DECIDE = {"decision_key": "key", "target_fields": "fields"}


def as_declaration(name: str, flat: dict) -> dict:
    """`{source_table, derived_table, decision_key, ...}` -> one `derive.decide` declaration."""
    cells = dict(flat)
    decl = {"name": name}
    # ⚠️ A MISSING TABLE STAYS MISSING. Some fixtures leave one out on purpose to watch the
    #    loader refuse with its reason; filling it in here would make that test pass for a
    #    declaration it never wrote.
    source, derived = cells.pop("source_table", None), cells.pop("derived_table", None)
    if source is not None:
        decl["on"] = {"table": source}
    if derived is not None:
        decl["into"] = {"table": derived}
    if "enabled" in cells:
        decl["enabled"] = cells.pop("enabled")
    decl["derive"] = {"kind": "decide",
                      "decide": {_TO_DECIDE.get(k, k): v for k, v in cells.items()}}
    return decl


def write_rules(tmp_path, monkeypatch, flat_rules: dict, filename: str = "chain_rules.json"):
    """`{name: flat cells}` -> a `chain_rules.json` the loader and every seat will read.

    The redirect is the one the rest of the suite already uses
    (`test_the_loader_reads_the_unified_grammar`): `ingestion_worker.RULES_PATH`.
    """
    from chain import ingestion_worker as worker

    path = rewrite_rules(tmp_path / filename, flat_rules)
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    return path


def rewrite_rules(path, flat_rules: dict):
    """Overwrite a rules file a fixture already redirected to - a test that turns a knob on
    mid-way. Written in the one grammar, or the seat reads an empty file and finds nothing."""
    path.write_text(json.dumps(
        {"rules": [as_declaration(n, r) for n, r in flat_rules.items()]}), encoding="utf-8")
    return path


def enrich_chain_rules(known_tables: dict = None) -> list:
    """The chain rules the loader stands for every `derive.decide` in `chain_rules.json`.

    What `load_enrichment_chain_rules` used to return for the flat file - per declaration, its
    dedup half then its auto-confirm half - now produced the way the loader produces it, through
    `rule_shape.expand_declaration`. A test that needs 「the enrich rules」 asks here instead of
    re-spelling the expansion.
    """
    from chain import ingestion_worker as worker, rule_shape

    out = []
    for raw in (worker.read_rules_document().get("rules") or ()):
        if isinstance(raw, dict) and isinstance(raw.get("derive"), dict) \
                and raw["derive"].get("kind") == "decide":
            stood, _refusal, _notes = rule_shape.expand_declaration(raw, known_tables)
            out.extend(stood)
    return out


def validate_rules(flat_config, known_tables: dict = None, rejections: list = None,
                   caps: dict = None) -> list:
    """`{name: flat cells}` -> the normalized declarations `_validate_rule` accepts.

    ⚰️ This was `enrichment.config.validate_enrichment_rules`, the flat file's loop. The loop
    retired with the file (2026-09-24); the validator it looped over did not - the unified
    grammar reaches `_validate_rule` with these same cell names through
    `chain_rules_from_cells`. Kept here, verbatim in behaviour, so the tests that pin WHAT the
    validator accepts keep pinning the function that runs.
    """
    from chain.enrichment import config as ec

    rules = []
    caps = caps if caps is not None else ec.load_read_caps()
    if not isinstance(flat_config, dict):
        return rules
    for name, raw in flat_config.items():
        if not isinstance(name, str) or not name.strip():
            continue
        normalized, err = ec._validate_rule(name, raw, known_tables, rejections=rejections,
                                            caps=caps)
        if err is None and normalized is not None:
            rules.append(normalized)
    return rules
