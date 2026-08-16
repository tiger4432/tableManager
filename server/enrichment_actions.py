"""Project open Enrichment work into bounded, walkable ontology action nodes.

An Enrich Action is not a domain entity and is not an append-only ledger fact.  It is a
recomputable projection of one validated Enrichment rule plus its current derived row.
The projection deliberately reuses Enrichment's decision key, target fields and declared
reference sources; it never invents a second definition of "missing" or probes candidate
SQL while an evidence graph is being drawn.

Two action grains exist:

* ``claim_resolution`` -- one decision key whose sourced target slot is still blank.
* ``source_contract`` -- one rule-level meta action when a required target has no declared
  supply source.  It is intentionally NOT repeated for every affected decision key.

The evidence graph supplies the anchor Claim.  This module only matches declarations,
does bounded indexed reads of already-materialized derived rows, and returns projections.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass


ACTION_PREFIX = "ledger-enrich-action:v1:"
ACTION_SCOPE_RESOLVE = "claim_resolution"
ACTION_SCOPE_SOURCE = "source_contract"
ACTION_SCOPES = frozenset({ACTION_SCOPE_RESOLVE, ACTION_SCOPE_SOURCE})


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _token(value):
    return base64.urlsafe_b64encode(
        _canonical(value).encode("utf-8")).decode("ascii").rstrip("=")


def _untoken(value):
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("enrich action id is not valid canonical UTF-8 JSON") from exc


def enrich_action_node_id(rule_name, version, scope, decision_key=None):
    """Stable projection identity; no mutable state or row id is encoded."""
    if scope not in ACTION_SCOPES:
        raise ValueError(f"unknown enrich action scope: {scope}")
    keys = None if scope == ACTION_SCOPE_SOURCE else dict(decision_key or {})
    return ACTION_PREFIX + _token([str(rule_name), int(version), scope, keys])


def decode_enrich_action_id(value):
    text = str(value or "").strip()
    if not text.startswith(ACTION_PREFIX):
        raise ValueError("node id is not an Enrich Action id")
    payload = _untoken(text[len(ACTION_PREFIX):])
    if not isinstance(payload, list) or len(payload) != 4:
        raise ValueError("enrich action id has the wrong shape")
    rule_name, version, scope, decision_key = payload
    if not isinstance(rule_name, str) or not rule_name.strip():
        raise ValueError("enrich action id has no rule name")
    if not isinstance(version, int) or version < 1:
        raise ValueError("enrich action id has an invalid contract version")
    if scope not in ACTION_SCOPES:
        raise ValueError("enrich action id has an unknown scope")
    if scope == ACTION_SCOPE_SOURCE:
        if decision_key is not None:
            raise ValueError("source-contract action id must not carry a decision key")
    elif not isinstance(decision_key, dict) or not decision_key:
        raise ValueError("claim-resolution action id needs a decision key")
    canonical = enrich_action_node_id(rule_name, version, scope, decision_key)
    if canonical != text:
        raise ValueError("node id is not in canonical spelling")
    return {
        "kind": "action", "rule_name": rule_name, "version": version,
        "scope": scope, "decision_key": decision_key, "id": text,
        "expandable": True,
    }


@dataclass(frozen=True)
class EnrichAction:
    rule_name: str
    contract_version: int
    scope: str
    label: str
    state: str
    action_kind: str
    decision_key: dict | None
    derived_table: str
    missing_targets: tuple
    expected_claims: tuple
    supply_sources: tuple
    suggested_action: str

    @property
    def id(self):
        return enrich_action_node_id(
            self.rule_name, self.contract_version, self.scope, self.decision_key)


def action_node(action: EnrichAction):
    """Public graph projection.  SQL and hidden reference-view limits never leak."""
    return {
        "id": action.id,
        "type": "Enrich Action",
        "node_kind": "action",
        "schema_kind": "enrich_action_projection",
        "label": action.label,
        "keys": {
            "rule": action.rule_name,
            "contract_version": action.contract_version,
            "scope": action.scope,
            "decision_key": action.decision_key,
        },
        "state": action.state,
        "action_kind": action.action_kind,
        "derived_table": action.derived_table,
        "missing_targets": list(action.missing_targets),
        "expected_claims": list(action.expected_claims),
        "supply_sources": list(action.supply_sources),
        "suggested_action": action.suggested_action,
        "projection": True,
        "terminal_in_automatic_walk": True,
        "claim_count": 0,
        "predicates": [{"predicate": "needs_enrichment", "count": 1}],
    }


def _path(value, dotted):
    current = value
    for part in str(dotted or "").split("."):
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _anchor_keys(atom, contract):
    anchor = contract["anchor"]
    if atom.predicate != anchor["predicate"]:
        return None
    container = _path(atom.object_payload or {}, anchor["payload_path"])
    if not isinstance(container, dict) or container.get("type") != anchor["object_type"]:
        return None
    source_keys = container.get("keys") or {}
    if not isinstance(source_keys, dict):
        return None
    keys = {}
    for decision_col, source_col in anchor["decision_key_map"].items():
        value = source_keys.get(source_col)
        if value is None or str(value).strip() == "":
            return None
        keys[decision_col] = value
    return keys


def _source_targets(contract):
    targets = set()
    for source in contract.get("sources") or []:
        targets.update(source.get("targets") or [])
    return targets


def _expected(contract, targets):
    wanted = set(targets)
    return tuple({
        "target_field": slot["target_field"],
        "predicate": slot["predicate"],
        "payload_path": slot["payload_path"],
    } for slot in contract["slots"] if slot["target_field"] in wanted)


def _source_public(contract, targets):
    wanted = set(targets)
    return tuple({
        key: value for key, value in source.items()
        if key in {"kind", "view_index", "authority", "targets", "source"}
    } for source in contract.get("sources") or []
      if wanted.intersection(source.get("targets") or []))


class EnrichmentActionLookup:
    """Rule matcher with a pluggable bounded derived-row reader."""

    def __init__(self, rules, blocked_rules=None):
        self.rules = {
            rule["name"]: rule for rule in (rules or [])
            if rule.get("claim_contract")
        }
        self.blocked_rules = set(blocked_rules or ()).intersection(self.rules)

    def _rows_for(self, rule, decision_keys):
        """Return ``{canonical decision key: {target: value}}``.  Subclasses own I/O."""
        raise NotImplementedError

    def _missing(self, rule, row):
        from database import crud
        return tuple(target for target in rule["target_fields"]
                     if row is None or crud.is_blank_value(row.get(target)))

    def _source_action(self, rule):
        contract = rule["claim_contract"]
        unsourced = set(rule["target_fields"]) - _source_targets(contract)
        label = contract["label_ko"]
        return EnrichAction(
            rule_name=rule["name"], contract_version=contract["version"],
            scope=ACTION_SCOPE_SOURCE,
            label=f"{label} · 공급 경로 정의",
            state="undeclared_claim_source", action_kind="declare_claim_source",
            decision_key=None, derived_table=rule["derived_table"],
            missing_targets=tuple(sorted(unsourced)),
            expected_claims=_expected(contract, unsourced), supply_sources=(),
            suggested_action="Claim의 관측 소스·coverage·translator·확정 권한을 선언",
        )

    def _deployment_action(self, rule):
        contract = rule["claim_contract"]
        return EnrichAction(
            rule_name=rule["name"], contract_version=contract["version"],
            scope=ACTION_SCOPE_SOURCE,
            label=f"{contract['label_ko']} · Enrichment 계약 복구",
            state="enrichment_contract_not_deployed",
            action_kind="repair_enrichment_contract",
            decision_key=None, derived_table=rule["derived_table"],
            missing_targets=tuple(rule["target_fields"]),
            expected_claims=_expected(contract, rule["target_fields"]),
            supply_sources=(),
            suggested_action=(
                "source/derived table 선언과 모델을 복구한 뒤 Enrichment rule을 재검증"),
        )

    def _resolve_action(self, rule, keys, missing):
        contract = rule["claim_contract"]
        return EnrichAction(
            rule_name=rule["name"], contract_version=contract["version"],
            scope=ACTION_SCOPE_RESOLVE,
            label=f"{contract['label_ko']} · 값 확인",
            state="missing_claim", action_kind="resolve_claim",
            decision_key=dict(keys), derived_table=rule["derived_table"],
            missing_targets=tuple(sorted(missing)),
            expected_claims=_expected(contract, missing),
            supply_sources=_source_public(contract, missing),
            suggested_action="선언된 근거에서 후보를 확인하고 Claim을 발행",
        )

    def actions_for_claims(self, atoms, limit):
        """Return ``[(action, anchor_claim_node_id)]`` with one bounded read per rule."""
        limit = max(0, int(limit))
        if not atoms or not self.rules or limit == 0:
            return [], False
        matches = {}
        for rule in self.rules.values():
            contract = rule["claim_contract"]
            for atom in atoms:
                keys = _anchor_keys(atom, contract)
                if keys is None:
                    continue
                matches.setdefault(rule["name"], {}).setdefault(
                    _canonical(keys), {"keys": keys, "claims": set()})["claims"].add(
                        atom.claim_node_id)
        out = []
        seen = set()
        cut = False
        for rule_name in sorted(matches):
            rule = self.rules[rule_name]
            buckets = matches[rule_name]
            if rule_name in self.blocked_rules:
                action = self._deployment_action(rule)
                for canonical_key in sorted(buckets):
                    for claim_id in sorted(buckets[canonical_key]["claims"]):
                        pair = (action.id, claim_id)
                        if pair in seen:
                            continue
                        if len(out) >= limit:
                            return out, True
                        seen.add(pair)
                        out.append((action, claim_id))
                continue
            rows = self._rows_for(rule, [item["keys"] for item in buckets.values()])
            sourced = _source_targets(rule["claim_contract"])
            for canonical_key in sorted(buckets):
                item = buckets[canonical_key]
                missing = set(self._missing(rule, rows.get(canonical_key)))
                if not missing:
                    continue
                actions = []
                unsourced = missing - sourced
                resolvable = missing & sourced
                if unsourced:
                    # The identity is rule-level, so its payload must also be rule-level
                    # and independent of which decision-key row happened to be visited
                    # first.  Report every unsourced slot in the contract, not merely
                    # the blank subset of the current row.
                    actions.append(self._source_action(rule))
                if resolvable:
                    actions.append(self._resolve_action(rule, item["keys"], resolvable))
                for action in actions:
                    for claim_id in sorted(item["claims"]):
                        pair = (action.id, claim_id)
                        if pair in seen:
                            continue
                        if len(out) >= limit:
                            cut = True
                            return out, cut
                        seen.add(pair)
                        out.append((action, claim_id))
        return out, cut

    def action_for_ref(self, ref):
        rule = self.rules.get(ref["rule_name"])
        if rule is None:
            return None
        contract = rule["claim_contract"]
        if contract["version"] != ref["version"]:
            return None
        if rule["name"] in self.blocked_rules:
            return (self._deployment_action(rule)
                    if ref["scope"] == ACTION_SCOPE_SOURCE else None)
        if ref["scope"] == ACTION_SCOPE_SOURCE:
            unsourced = set(rule["target_fields"]) - _source_targets(contract)
            return self._source_action(rule) if unsourced else None
        keys = ref.get("decision_key") or {}
        rows = self._rows_for(rule, [keys])
        missing = set(self._missing(rule, rows.get(_canonical(keys))))
        sourced = missing & _source_targets(contract)
        return self._resolve_action(rule, keys, sourced) if sourced else None


class InMemoryEnrichmentActionLookup(EnrichmentActionLookup):
    def __init__(self, rules, rows=None):
        super().__init__(rules)
        self.rows = dict(rows or {})

    def _rows_for(self, rule, decision_keys):
        table_rows = self.rows.get(rule["derived_table"], {})
        return {_canonical(keys): table_rows.get(_canonical(keys))
                for keys in decision_keys}


class SqlEnrichmentActionLookup(EnrichmentActionLookup):
    """Request-scoped adapter; all row probes use indexed ``business_key_val IN``."""

    def __init__(self, db, rules=None):
        from database import crud
        import enrichment_config
        self.db = db
        self.table_config = crud.TABLE_CONFIG
        if rules is not None:
            loaded = list(rules)
            blocked = set()
        else:
            # A syntactically valid rule whose tables are not deployed is itself the
            # earliest meta action.  We may use it ONLY to name that configuration gap;
            # no row read, missing-value claim, or candidate query is allowed until the
            # same rule passes known-table validation.
            declared = enrichment_config.load_enrichment_rules(known_tables=None)
            if self.table_config:
                loaded = enrichment_config.load_enrichment_rules(
                    known_tables=self.table_config)
                validated = {rule["name"] for rule in loaded}
            else:
                loaded = []
                validated = set()
            blocked = {rule["name"] for rule in declared} - validated
            loaded.extend(rule for rule in declared if rule["name"] in blocked)
        super().__init__(loaded, blocked_rules=blocked)

    def _business_key(self, rule, keys):
        from database import crud
        cfg = self.table_config[rule["derived_table"]]
        components = cfg.get("composite_key_source")
        if components:
            separator = cfg.get("composite_key_separator", "_")
            return separator.join(crud.clean_str_value(keys.get(col))
                                  for col in components)
        return crud.clean_str_value(keys.get(cfg.get("business_key")))

    def _rows_for(self, rule, decision_keys):
        from database import models
        if not decision_keys:
            return {}
        model = models.DYNAMIC_TABLES.get(rule["derived_table"])
        if model is None:
            return {}
        by_business_key = {}
        for keys in decision_keys:
            business_key = self._business_key(rule, keys)
            if business_key:
                # Enrichment deliberately permits a derived-table business key to be
                # a proper subset of the decision key.  Several decision contexts can
                # therefore share one materialized row; all must inherit its target
                # state rather than the last key silently winning this dictionary.
                by_business_key.setdefault(business_key, []).append(keys)
        if not by_business_key:
            return {}
        columns = [model.business_key_val]
        columns.extend(getattr(model, target) for target in rule["target_fields"])
        rows = self.db.query(*columns).filter(
            model.business_key_val.in_(list(by_business_key))).all()
        out = {}
        for row in rows:
            key_groups = by_business_key.get(str(row[0]))
            if key_groups is None:
                continue
            values = {target: row[index + 1]
                      for index, target in enumerate(rule["target_fields"])}
            for key_values in key_groups:
                out[_canonical(key_values)] = dict(values)
        return out
