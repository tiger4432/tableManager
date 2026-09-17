# -*- coding: utf-8 -*-
"""인리치 — 체인 선언의 «한 종류»다. 그래서 `chain/` 안에 산다.

> 소유자 2026-09-17: 「모든 체인은 server/chain 안에서만 코드 존재」

🔴 THE SUBMODULES ARE BOUND LAZILY, AND THAT IS NOT DECORATION. Callers write
`from chain import enrichment` and then `enrichment.config.…`, which only resolves if the
submodule has been imported by somebody - a load ORDER nobody states and nothing enforces.
Importing them eagerly here would fix that and open a cycle instead: `config` reaches for
`chain.rule_shape`, which reaches back for this package. PEP 562's `__getattr__` binds on
first use, so the name works from any caller and the import graph stays the shape it was
before the move.

⚠️ THE MOVE KEPT THE SPELLING OF EVERY CALL SITE. 444 of them say `enrichment.config.…` and
`enrichment.candidates.…`; only the 93 import lines changed. A rename on top of a move would
have made the diff unreadable and the round unreviewable.
"""

_SUBMODULES = ("analysis", "backfill", "candidates", "config", "mapper")


def __getattr__(name):
    if name in _SUBMODULES:
        import importlib

        module = importlib.import_module("." + name, __name__)
        globals()[name] = module
        return module
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(set(globals()) | set(_SUBMODULES))
