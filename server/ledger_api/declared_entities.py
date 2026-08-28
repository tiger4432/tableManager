"""선언된 «개체 타입»과 그 «신원 키» — 오직 선언에서 읽는다.

🔴 이 파일이 답하는 것은 하나다: 「이 배포가 아는 개체 타입은 무엇이고, 각각을 무엇으로
이름 붙이나」. 답은 `config/ontology/ledger_config.json` 의 `entities` 에만 있고, 여기서는
읽기만 한다 — 그 규칙을 코드에 적으면 소유자의 완성 조건(「다른 스키마 운영 환경에서 코드 0줄」)이
깨진다.

    "die@1": { "keys": ["mat_id", "x", "y", "mat_type"] }
    -> declared_types() 에 `die`,  identity_keys("die") 에 그 넷

🔴 «참조 엣지» 절반은 2026-08-28 에 나갔다. 선언에서 `references` 가 빠지면서 합성 엣지가
0 이 됐고(실측), 마지막 호출자였던 walk 의 컨테이너 합성도 같은 밤에 사라졌다 —
`reference_edges` · `reference_edge_names` · `targets_for` 는 호출자가 «0» 이었다.
그 문법을 선언 검증기에서 걷어내는 것은 별도 레인의 몫이다.

⚠️ 읽기는 «한 번·캐시»이고 «절대 예외를 올리지 않는다». 선언이 없거나 깨져도 목록이 비는 것이지
   부르는 쪽이 같이 죽지 않는다 — 없는 것과 고장 난 것은 다른 답이다.
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
    """`{entity type: [identity key, …]}`, 캐시. 없거나 깨진 파일은 «답»이다.

    선언이 없는 박스는 아는 타입이 «없는» 것이고, 그것이 이 함수의 정답이다.
    """
    global _cache, _keys
    with _lock:
        if _cache is not None and not force_reload:
            return _cache
        path = _config_path()
        keys = {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            for name, spec in (raw.get("entities") or {}).items():
                declared = (spec or {}).get("keys")
                if isinstance(declared, list):
                    keys[_bare(name)] = [str(k) for k in declared if isinstance(k, str)]
        except FileNotFoundError:
            pass
        except Exception as exc:                                  # pragma: no cover
            logger.error("declared entities unreadable at %s: %s", path, exc)
        _keys = keys
        _cache = keys
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


