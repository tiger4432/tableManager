# -*- coding: utf-8 -*-
"""The MECHANISM gate — 「그 요인에서 이 불량으로 가는 경로가 선언돼 있는가」.

This is the M4 mechanism graph's **first consumer**. Until now the declaration existed
and nothing read it (`ledger_structure.mechanism_layer` says so in as many words, and its
`edge_state` for every edge is `declared_unconsumed`). The contrast's third gate is what
consumes it.

WHY A GRAPH AND NOT A LOOKUP
-----------------------------
An enriched factor is not an explanation. `recipe.rev = 6` being 6.8x more common among
the excursion lots says the two travel together; it says nothing about how a revision
number turns into a void. The mechanism graph is where somebody wrote down that
`bond_pressure -> interface_unfill -> void`, so a factor bound to `bond_pressure` has a
DECLARED path and one bound to `mold_temp_C` does not. The gate reports which.

🔴 FOUR VERDICTS, AND THE TWO THAT LOOK ALIKE ARE NOT
------------------------------------------------------
    pass             a declared path reaches a FORMATION model's target
    bias_candidate   a path reaches ONLY an observation-bias model's target
    fail             the quantity IS in this kind's model and NO path reaches the target
    unknown          nothing was asked or nothing could answer — NOT a failure

`bias_candidate` exists because `void_observation_bias` is deliberately a separate model:
a factor that only reaches `void_observed` explains why a void was SEEN, not why it
FORMED. Reporting that as a cause is how a scanner artefact becomes a process finding, and
the split is structural rather than a naming convention so that it cannot rot.

`unknown` vs `fail` is the other pair that must never render the same. A candidate with no
binding is unjudged — the modeller has not said what physical quantity that field measures
— while `fail` is the model having been asked and having answered no. Folding the first
into the second would report 「기전 없음」 for a factor nobody ever modelled, and the
console's whole job is to tell a measured absence from an unmeasured one.

🔴 A BINDING IS NOT AN ITEM LIST
---------------------------------
The contrast's candidate space is the walk (every predicate x payload field x value that
the ledger holds for the marked subjects) and NOTHING here narrows it. A binding says only
「이 필드는 이 물리량을 잰다」, which is knowledge the modeller has and the data does not.
An unbound candidate still appears in the contrast, still ranks, and simply carries
`unknown` in this column — so a newly translated predicate reaches the screen with zero
declarations, which is this round's acceptance assertion.

[SCALE] The graph is a config file with tens of nodes. It is loaded once, cached, and the
BFS is over that in-memory adjacency — no query, no per-row work that touches the database.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque

logger = logging.getLogger("Ledger.MechanismGate")

CONFIG_FILENAME = "mechanism_models.json"

#: Reserved top-level keys of the config. Everything else is a model.
KEY_DOC = "__doc"
KEY_BINDINGS = "bindings"

#: A model's declared role. `formation` models describe how the finding COMES TO BE;
#: `observation_bias` models describe how it comes to be SEEN. A model that declares
#: neither cannot be used by this gate, and says so rather than being guessed at.
ROLE_FORMATION = "formation"
ROLE_OBSERVATION_BIAS = "observation_bias"
ROLES = (ROLE_FORMATION, ROLE_OBSERVATION_BIAS)

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_UNKNOWN = "unknown"
VERDICT_BIAS = "bias_candidate"

#: Structured reasons. The client BRANCHES on these; the Korean beside them is for the
#: operator's eyes only (ruling R-2026-08-13-C).
REASON_NO_CONFIG = "no_mechanism_config"
REASON_UNREADABLE = "mechanism_config_unreadable"
REASON_NO_MODEL_FOR_KIND = "no_model_for_kind"
REASON_NO_BINDING = "no_binding_for_candidate"
REASON_NODE_ABSENT = "node_absent_from_model"
REASON_NO_PATH = "no_declared_path_to_finding"
REASON_BIAS_ONLY = "reaches_observation_bias_only"
REASON_REACHES = "declared_path"

VERDICT_MESSAGES = {
    REASON_NO_CONFIG: "기전 그래프 선언 파일 없음",
    REASON_UNREADABLE: "기전 그래프 선언을 읽을 수 없음",
    REASON_NO_MODEL_FOR_KIND: "이 관측 종류의 기전 모델 미선언",
    REASON_NO_BINDING: "이 필드가 어떤 물리량인지 선언 없음",
    REASON_NODE_ABSENT: "선언된 물리량이 이 종류의 모델에 없음",
    REASON_NO_PATH: "모델에 있으나 이 불량까지 가는 경로 없음",
    REASON_BIAS_ONLY: "관측 편향 모델에만 닿음 — 원인 아닌 편향 후보",
    REASON_REACHES: "선언된 경로 있음",
}

_lock = threading.Lock()
_cache = None


class MechanismConfigError(RuntimeError):
    """The declaration is unusable. Reported as a state, never as a 500."""


class Model:
    """One declared causal model: an adjacency, a role, and the finding it terminates in."""

    __slots__ = ("name", "role", "finding_kind", "target", "nodes", "adjacency",
                 "version", "validity", "usable", "reason")

    def __init__(self, name, raw):
        self.name = name
        self.role = raw.get("role")
        self.finding_kind = raw.get("finding_kind")
        self.target = raw.get("target")
        self.version = raw.get("version")
        self.validity = raw.get("validity")
        self.nodes = set(str(n) for n in (raw.get("nodes") or []))
        self.adjacency = {}
        for spec in raw.get("edges") or []:
            if not isinstance(spec, dict):
                continue
            head, tail = str(spec.get("from") or ""), str(spec.get("to") or "")
            if not head or not tail:
                continue
            self.adjacency.setdefault(head, []).append(
                {"to": tail, "dir": spec.get("dir")})
            self.nodes.add(head)
            self.nodes.add(tail)
        # 🔴 A model missing `role`, `finding_kind` or `target` is NOT silently repaired
        # by convention (a name ending in `_observation_bias`, a target equal to the kind).
        # Guessing here would decide, from a filename, whether a factor is a cause or an
        # artefact. It is marked unusable and the reason travels to the response.
        missing = [k for k in ("role", "finding_kind", "target")
                   if not getattr(self, k)]
        if missing:
            self.usable, self.reason = False, "missing:" + ",".join(missing)
        elif self.role not in ROLES:
            self.usable, self.reason = False, f"unknown_role:{self.role}"
        elif self.target not in self.nodes:
            self.usable, self.reason = False, f"target_not_a_node:{self.target}"
        else:
            self.usable, self.reason = True, None

    def reach(self, start):
        """Shortest declared path `start -> target`, or `None`. Plain BFS.

        Traversal never leaves this model. Two models sharing a node name is normal —
        `bond_pressure` feeds both `void_formation` and `delam_formation` — and hopping
        between them would splice two modellers' assertions into a third one that nobody
        made, which is exactly how a bias-only factor would acquire a formation path.
        """
        if start not in self.nodes:
            return None
        if start == self.target:
            return [{"node": start, "dir": None}]
        seen = {start}
        queue = deque([(start, [{"node": start, "dir": None}])])
        while queue:
            node, path = queue.popleft()
            for edge in self.adjacency.get(node, ()):
                nxt = edge["to"]
                if nxt in seen:
                    continue
                step = path + [{"node": nxt, "dir": edge["dir"]}]
                if nxt == self.target:
                    return step
                seen.add(nxt)
                queue.append((nxt, step))
        return None

    def as_dict(self):
        return {"model": self.name, "role": self.role,
                "finding_kind": self.finding_kind, "target": self.target,
                "version": self.version, "usable": self.usable,
                "unusable_reason": self.reason, "nodes": sorted(self.nodes)}


class MechanismGraph:
    """Every declared model plus the field->quantity bindings, loaded once."""

    __slots__ = ("models", "bindings", "path", "origin", "state", "reason", "message")

    def __init__(self, raw, path, origin):
        self.path, self.origin = path, origin
        self.state, self.reason, self.message = "declared", None, None
        self.models = []
        for name, spec in (raw or {}).items():
            if name.startswith("__") or name == KEY_BINDINGS:
                continue
            if isinstance(spec, dict):
                self.models.append(Model(name, spec))
        bindings = raw.get(KEY_BINDINGS) if isinstance(raw, dict) else None
        self.bindings = {}
        for key, nodes in (bindings or {}).items():
            if key.startswith("__"):
                continue
            if isinstance(nodes, str):
                nodes = [nodes]
            self.bindings[str(key)] = [str(n) for n in (nodes or [])]

    # -------------------------------------------------------------------- queries
    def models_for(self, kind):
        return [m for m in self.models if m.usable and m.finding_kind == kind]

    def nodes_for(self, candidate_key):
        """The physical quantities a candidate field is declared to measure.

        Two spellings are accepted and BOTH are looked up, most specific first:
        `<predicate>:<field path>` and the bare `<field path>`. The second is what lets
        one binding serve `params_actual.temp_C` and `params_setpoint.temp_C`'s
        predicate-qualified twins without the modeller writing the predicate twice.
        """
        for key in self._binding_keys(candidate_key):
            if key in self.bindings:
                return self.bindings[key], key
        return [], None

    @staticmethod
    def _binding_keys(candidate_key):
        yield candidate_key
        if ":" in candidate_key:
            yield candidate_key.split(":", 1)[1]

    def declaration(self):
        return {
            "state": self.state, "config": CONFIG_FILENAME, "origin": self.origin,
            "path": self.path, "reason": self.reason, "message": self.message,
            "models": [m.as_dict() for m in self.models],
            "binding_count": len(self.bindings),
        }


class _AbsentGraph(MechanismGraph):
    """No declaration a process can open. Every verdict is `unknown`, with the reason."""

    def __init__(self, path, origin, reason, message):
        super().__init__({}, path, origin)
        self.state, self.reason, self.message = "absent", reason, message


def _config_path():
    try:
        import paths
        base = paths.CONFIG_DIR
    except Exception:                                            # pragma: no cover
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
    path = os.path.join(base, CONFIG_FILENAME)
    if os.path.exists(path):
        return path, "config"
    if os.path.exists(path + ".sample"):
        return path + ".sample", "sample"
    return path, "absent"


def load(force_reload=False):
    """Read once, cached. An absent or broken declaration is a STATE, not an exception —
    the same rule the siblings and coverage routes follow, because a box with no mechanism
    file must still be able to answer 「실재✓ · 상류✓ · 기전 —」."""
    global _cache
    with _lock:
        if _cache is not None and not force_reload:
            return _cache
        path, origin = _config_path()
        if origin == "absent":
            _cache = _AbsentGraph(path, origin, REASON_NO_CONFIG,
                                  VERDICT_MESSAGES[REASON_NO_CONFIG])
            return _cache
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict):
                raise ValueError("최상위가 객체가 아님")
        except Exception as exc:
            logger.error("mechanism declaration unreadable at %s: %s", path, exc)
            _cache = _AbsentGraph(path, origin, REASON_UNREADABLE,
                                  f"{VERDICT_MESSAGES[REASON_UNREADABLE]}: {exc}")
            return _cache
        _cache = MechanismGraph(raw, path, origin)
        return _cache


def set_graph(config):
    """Install a graph for this process. Tests use it; nothing else should."""
    global _cache
    with _lock:
        if config is None:
            _cache = None
        elif isinstance(config, MechanismGraph):
            _cache = config
        else:
            _cache = MechanismGraph(config, "<memory>", "memory")
        return _cache


# ------------------------------------------------------------------------- the gate
def verdict(kind, candidate_key, graph=None):
    """The mechanism gate for ONE candidate. Pure — no connection, no query.

    `candidate_key` is `<predicate>:<field path>` as the walk names it, e.g.
    `processed_with:params_actual.pressure_MPa`.
    """
    graph = graph if graph is not None else load()
    out = {"verdict": VERDICT_UNKNOWN, "reason": None, "message": None,
           "basis": CONFIG_FILENAME, "quantity": None, "binding_key": None,
           "model": None, "role": None, "path": None, "hops": None,
           "bias_models": []}

    if graph.state != "declared":
        out["reason"] = graph.reason
        out["message"] = graph.message
        return out

    models = graph.models_for(kind)
    if not models:
        out["reason"] = REASON_NO_MODEL_FOR_KIND
        out["message"] = VERDICT_MESSAGES[REASON_NO_MODEL_FOR_KIND]
        return out

    quantities, binding_key = graph.nodes_for(candidate_key)
    if not quantities:
        out["reason"] = REASON_NO_BINDING
        out["message"] = VERDICT_MESSAGES[REASON_NO_BINDING]
        return out
    out["binding_key"] = binding_key

    bias_hits, known_but_unreached, absent_everywhere = [], False, True
    for quantity in quantities:
        for model in models:
            if quantity not in model.nodes:
                continue
            absent_everywhere = False
            path = model.reach(quantity)
            if path is None:
                known_but_unreached = True
                continue
            if model.role == ROLE_FORMATION:
                out.update({"verdict": VERDICT_PASS, "reason": REASON_REACHES,
                            "message": VERDICT_MESSAGES[REASON_REACHES],
                            "quantity": quantity, "model": model.name,
                            "role": model.role, "path": path,
                            "hops": len(path) - 1})
                return out
            bias_hits.append({"quantity": quantity, "model": model.name,
                              "path": path, "hops": len(path) - 1})

    if bias_hits:
        first = bias_hits[0]
        out.update({"verdict": VERDICT_BIAS, "reason": REASON_BIAS_ONLY,
                    "message": VERDICT_MESSAGES[REASON_BIAS_ONLY],
                    "quantity": first["quantity"], "model": first["model"],
                    "role": ROLE_OBSERVATION_BIAS, "path": first["path"],
                    "hops": first["hops"],
                    "bias_models": sorted({h["model"] for h in bias_hits})})
        return out
    if known_but_unreached:
        # 🔴 The ONE `fail` this gate issues: the quantity is in the model and the model
        # has no path from it to the finding. That is the modeller answering «no», which
        # is a different fact from nobody having been asked.
        out.update({"verdict": VERDICT_FAIL, "reason": REASON_NO_PATH,
                    "message": VERDICT_MESSAGES[REASON_NO_PATH],
                    "quantity": quantities[0]})
        return out
    if absent_everywhere:
        out.update({"reason": REASON_NODE_ABSENT,
                    "message": VERDICT_MESSAGES[REASON_NODE_ABSENT],
                    "quantity": quantities[0]})
    return out
