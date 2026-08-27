"""「이 die 는 어느 통에 담겨 있나」 — read from the DECLARATION, never decided here.

🔴 WHY THIS FILE EXISTS AND WHY IT IS THIN. The walk needs an edge from a die to the thing that
holds it, or a chain that reaches a core die stops one hop short of the wafer whose recipe the
reader is after. The rule "a die whose `mat_type` is 'Wafer' names a wafer in `mat_id`" is TRUE
of this ontology and of no other, so putting it in code would break the owner's standing
definition of done -- 「다른 스키마 운영 환경에서 코드 0줄」. The declaration says it; this
module only reads what it says.

    "die@1": {
      "keys": ["mat_id", "x", "y", "mat_type"],
      "references": [
        { "edge": "in_container",
          "from": { "when": { "mat_type": "Wafer" } },
          "to":   { "entity": "wafer@1", "keys": { "wafer": { "key": "mat_id" } } } }
      ]
    }

🔴 THE EDGE'S NAME COMES FROM THE DECLARATION TOO (`edge`). Hard-coding it here would put the
ontology back in the code through a smaller door.

🔴 THE VOCABULARY IS NOT WHERE THIS LIVES, and that is deliberate. Every predicate in
`vocabulary` is one that ATOMS ARE WRITTEN UNDER; a reader who finds a name there is entitled to
go looking for its atoms. A synthesised edge has none. `has_findings` and `binding` are the
precedent -- both are drawn by the projection and neither appears in the vocabulary.

⚠️ THE WORDS ARE `from` / `edge` / `to`, NOT `subject` / `predicate` / `target`. A mapping emits
an atom; a reference composes an edge. Same words would promise the wrong thing.

🔴 `to.keys` IS PLURAL, AND THAT IS THE POINT (owner's ruling, 2026-08-26). A container can need
more than one key to be named -- a lot slot is (lot, slot) -- so a singular `to.key` would have
to be widened the day the DT tray arrives, and the reason given for plural was 「문법을 두 번
건드리지 않는다」. It is spelled the way `bind.…​.keys` already is, `{target key: binding}`, so the
same file reads one way throughout and a `{"value": …}` binding can join later without another
grammar change. `{"wafer": "mat_id"}` is accepted as shorthand for `{"wafer": {"key": "mat_id"}}`.
"""
from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "ledger_config.json"
CONFIG_SUBDIR = "ontology"

_cache = None
#: The identity keys of every declared entity, from the SAME parse as `_cache`. The
#: declaration is the only place that knows them, and two readers of one file would be two
#: chances to disagree about it.
_keys = None
_lock = threading.Lock()


def _config_path():
    try:
        import paths
        base = os.path.join(paths.CONFIG_DIR, CONFIG_SUBDIR)
    except Exception:                                            # pragma: no cover
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        base = os.path.join(server_dir, "config", CONFIG_SUBDIR)
    return os.path.join(base, CONFIG_FILENAME)


def load(force_reload=False):
    """`{entity_type: [reference, …]}`, cached. An absent or broken file is an ANSWER.

    A box with no declaration draws no synthesised edges, which is the same thing the walk did
    before this existed -- and it is what makes gate ⑤ meaningful: delete the declaration and
    the edges go, because nothing here knows their names.
    """
    global _cache, _keys
    with _lock:
        if _cache is not None and not force_reload:
            return _cache
        path = _config_path()
        table = {}
        keys = {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            for name, spec in (raw.get("entities") or {}).items():
                refs = (spec or {}).get("references")
                if isinstance(refs, list) and refs:
                    table[_bare(name)] = [r for r in refs if isinstance(r, dict)]
                declared = (spec or {}).get("keys")
                if isinstance(declared, list):
                    keys[_bare(name)] = [str(k) for k in declared if isinstance(k, str)]
        except FileNotFoundError:
            pass
        except Exception as exc:                                  # pragma: no cover
            logger.error("entity references unreadable at %s: %s", path, exc)
        _cache = table
        _keys = keys
        return _cache


def declared_types():
    """Every entity type the declaration names, bare and sorted. `[]` says the declaration
    names none -- an absent or broken file is an ANSWER here too."""
    load()
    return sorted(_keys or {})


def identity_keys(entity_type):
    """That entity's identity keys, in declared order. `[]` when it is not declared."""
    load()
    return list((_keys or {}).get(_bare(entity_type)) or ())


def _bare(entity_type):
    """`wafer@1` -> `wafer`. The ledger stores the bare type; the declaration versions it."""
    return str(entity_type or "").split("@", 1)[0].strip().lower()


def targets_for(entity_type, keys):
    """Every container this entity's keys point at, as `(edge, target_type, target_keys)`.

    Returns `[]` when the declaration says nothing, when the discriminating `when` does not
    hold, or when the naming key is empty -- three different silences that all mean "no edge",
    and none of which is an error.
    """
    out = []
    for ref in load().get(_bare(entity_type), ()):
        source = ref.get("from") or {}
        target = ref.get("to") or {}
        edge, entity = ref.get("edge"), target.get("entity")
        bindings = target.get("keys")
        if not (edge and entity and isinstance(bindings, dict) and bindings):
            continue
        when = source.get("when") or {}
        if any(str(keys.get(name)) != str(value) for name, value in when.items()):
            continue
        target_keys, complete = {}, True
        for target_key, binding in bindings.items():
            if isinstance(binding, str):
                binding = {"key": binding}
            if not isinstance(binding, dict):
                complete = False
                break
            if "value" in binding:
                value = binding["value"]
            else:
                value = keys.get(binding.get("key"))
            # 🔴 A PARTLY NAMED CONTAINER IS NOT A CONTAINER. One missing key would compose an
            # edge to an id built from a hole, which resolves to nothing and opens empty.
            if value in (None, ""):
                complete = False
                break
            target_keys[str(target_key)] = value
        if complete:
            out.append((str(edge), _bare(entity), target_keys))
    return out
