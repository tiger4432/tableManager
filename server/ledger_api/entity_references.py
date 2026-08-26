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
          "from": { "key": "mat_id", "when": { "mat_type": "Wafer" } },
          "to":   { "entity": "wafer@1", "key": "wafer" } }
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
    global _cache
    with _lock:
        if _cache is not None and not force_reload:
            return _cache
        path = _config_path()
        table = {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            for name, spec in (raw.get("entities") or {}).items():
                refs = (spec or {}).get("references")
                if isinstance(refs, list) and refs:
                    table[_bare(name)] = [r for r in refs if isinstance(r, dict)]
        except FileNotFoundError:
            pass
        except Exception as exc:                                  # pragma: no cover
            logger.error("entity references unreadable at %s: %s", path, exc)
        _cache = table
        return _cache


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
        edge = ref.get("edge")
        key, entity, target_key = source.get("key"), target.get("entity"), target.get("key")
        if not (edge and key and entity and target_key):
            continue
        when = source.get("when") or {}
        if any(str(keys.get(k)) != str(v) for k, v in when.items()):
            continue
        value = keys.get(key)
        if value in (None, ""):
            continue
        out.append((str(edge), _bare(entity), {str(target_key): value}))
    return out
