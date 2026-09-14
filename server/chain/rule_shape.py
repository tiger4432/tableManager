"""세 문법을 담는 «내부 규칙» 하나와, 오늘의 소비자에게 돌려주는 어댑터 둘 (S-234 2단계 ①②).

🔴 아직 «아무도 안 쓴다». 그것이 이 단계의 전부다 — 통합의 위험은 새 모양이 아니라 «소비자를
같이 옮기는 것»에 있고, 2026-09-14 의 사고 넷은 전부 그 부류(한 번에 엄해진 변경)였다.

[계약] `from_* -> as_*` 는 **원본과 같은 dict** 를 돌려준다. 그래야 다음 단계(로더가 내부 객체를
만들고 소비자에게는 어댑터를 통과한 오늘의 dict 를 주는 것)가 «희망»이 아니라 «정의상» 동작 0 이다.

[그래서 `extra` 가 있다] 이 모듈이 «아는» 칸만 모양으로 접고, 나머지는 순서까지 그대로 나른다.
   ⛔ 아는 척하고 버리면 왕복이 깨지고, 왕복이 깨지면 이 파일은 위험을 «옮기기만» 한 것이다.
   ⚠️ `extra` 가 큰 것은 흠이 아니라 «오늘의 정직한 크기»다 — 단계가 갈수록 줄어든다.
"""
from __future__ import annotations

#: 체인 문법에서 «모양으로 접히는» 칸. 나머지는 전부 `extra` 로 간다.
CHAIN_MODELLED = ("name", "enabled", "trigger_table", "trigger_columns",
                  "target_table", "mapper", "mapper_module", "mapper_function",
                  "params", "group_by", "max_group_rows", "max_group_attempts",
                  "idempotent")

#: 조인 문법에서 접히는 칸. `materialize` 는 «일부러» 여기 없다 — 8.5 ③ 의 판단 대기 항목이라
#: 지금 접으면 아직 안 받은 판정을 코드가 «먼저» 내려 버린다.
JOIN_MODELLED = ("left_table", "right_table", "left_columns", "right_columns",
                 "right_folds")

_LIMIT_KEYS = ("group_by", "max_group_rows", "max_group_attempts", "idempotent")


def _present(raw: dict, keys) -> dict:
    """선언에 «있는» 칸만. 없는 칸을 None 으로 채우면 왕복이 원본에 없던 키를 만든다."""
    return {key: raw[key] for key in keys if key in raw}


def from_chain_rule(raw: dict, origin: str = "declared") -> dict:
    """오늘의 체인 규칙 dict -> 내부 규칙."""
    raw = raw if isinstance(raw, dict) else {}
    mapper = _present(raw, ("mapper", "mapper_module", "mapper_function", "params"))
    return {
        "name": raw.get("name"),
        "enabled": raw.get("enabled", True),
        # ⚠️ 「안 적음」과 「true 라고 적음」은 «다른 선언»이다. 값만 들고 있으면 왕복이
        #    원본에 없던 칸을 만들어 내고, 그러면 census 가 매 적재마다 「바뀜」이라 말한다.
        "enabled_written": "enabled" in raw,
        "on": _rename(_present(raw, ("trigger_table", "trigger_columns")),
                      {"trigger_table": "table", "trigger_columns": "columns"}),
        "derive": {"kind": "mapper", "mapper": mapper},
        "into": ({"table": raw["target_table"]} if "target_table" in raw else {}),
        "limits": _present(raw, _LIMIT_KEYS),
        "origin": origin,
        "grammar": "chain",
        "extra": {key: value for key, value in raw.items()
                  if key not in CHAIN_MODELLED},
    }


def as_chain_rule(internal: dict) -> dict:
    """내부 규칙 -> 오늘의 체인 규칙 dict. `from_chain_rule` 의 역이다."""
    out = {}
    if internal.get("name") is not None or "name" in internal:
        out["name"] = internal.get("name")
    on = internal.get("on") or {}
    if "table" in on:
        out["trigger_table"] = on["table"]
    if "columns" in on:
        out["trigger_columns"] = on["columns"]
    into = internal.get("into") or {}
    if "table" in into:
        out["target_table"] = into["table"]
    out.update((internal.get("derive") or {}).get("mapper") or {})
    out.update(internal.get("limits") or {})
    out.update(internal.get("extra") or {})
    # `enabled` 는 «생략된 것»과 «적힌 것»이 다른 문장이므로 «적혀 있었을 때만» 되돌린다
    if internal.get("enabled_written"):
        out["enabled"] = internal.get("enabled")
    return out


def from_join_rule(name: str, raw: dict, origin: str = "declared") -> dict:
    """오늘의 가상 조인 선언 -> 내부 규칙. 읽기 시점에 앉으므로 `into.read`."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "name": name,
        "enabled": raw.get("enabled", True),
        "enabled_written": "enabled" in raw,
        "on": ({"table": raw["left_table"]} if "left_table" in raw else {}),
        "derive": {"kind": "join",
                   "join": _present(raw, JOIN_MODELLED[1:])},
        "into": {"read": True},
        "limits": {},
        "origin": origin,
        "grammar": "join",
        "extra": {key: value for key, value in raw.items()
                  if key not in JOIN_MODELLED},
    }


def as_join_rule(internal: dict) -> dict:
    """내부 규칙 -> 오늘의 가상 조인 선언 dict."""
    out = {}
    on = internal.get("on") or {}
    if "table" in on:
        out["left_table"] = on["table"]
    out.update((internal.get("derive") or {}).get("join") or {})
    out.update(internal.get("extra") or {})
    return out


def _rename(source: dict, mapping: dict) -> dict:
    return {mapping[key]: value for key, value in source.items() if key in mapping}


# ---------------------------------------------------------------------------
# 새 문법 — 내부 객체를 «적는» 모양 (S-234 §2). 읽기와 쓰기가 한 쌍이다.
# ---------------------------------------------------------------------------

def to_declaration(internal: dict) -> dict:
    """내부 규칙 -> 새 문법 dict. 「사람이 적는 모양」이므로 «빈 칸을 만들지 않는다».

    ⚠️ 빈 `limits: {}` 나 `on: {}` 를 적어 두면 선언이 「무언가 설정됐다」고 읽힌다 —
    운영자에게 «없는 것»과 «비어 있게 정한 것»은 다른 문장이다.
    """
    out = {"name": internal.get("name")}
    if internal.get("enabled_written"):
        out["enabled"] = internal.get("enabled")
    for key in ("on", "derive", "into", "limits"):
        value = internal.get(key)
        if value:
            out[key] = value
    if internal.get("extra"):
        # 🔴 제품이 뜻을 모르는 칸은 «한 자리»에 모아 둔다 — 흩어 두면 새 문법의 칸과
        #    구별이 안 되고, 그러면 다음 사람이 그것을 문법이라 읽는다.
        out["extra"] = internal["extra"]
    return out


def from_declaration(raw: dict, origin: str = "declared") -> dict:
    """새 문법 dict -> 내부 규칙. `to_declaration` 의 역이다."""
    raw = raw if isinstance(raw, dict) else {}
    derive = raw.get("derive") or {}
    kind = derive.get("kind")
    if not kind:
        for name in ("mapper", "join", "decide"):
            if name in derive:
                kind = name
                break
    return {
        "name": raw.get("name"),
        "enabled": raw.get("enabled", True),
        "enabled_written": "enabled" in raw,
        "on": dict(raw.get("on") or {}),
        "derive": dict(derive, kind=kind or "unknown"),
        "into": dict(raw.get("into") or {}),
        "limits": dict(raw.get("limits") or {}),
        "origin": origin,
        "grammar": "unified",
        "extra": dict(raw.get("extra") or {}),
    }
