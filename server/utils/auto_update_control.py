# -*- coding: utf-8 -*-
"""
Auto Update 수집기 active 상태 제어 파일(auto_update_control.json)의 공용 IO 모듈.

- 제어 파일 위치: server/config/auto_update_control.json (gitignored 사용자 config 관례)
- 형식: {"disabled": ["<workspace>/<script.py>", ...]}
- 파일이 없거나 손상된 경우 => 전부 active (fail-open).
- 웹서버(main.py)의 toggle 엔드포인트가 쓰고, 스케줄러(run_auto_update.py)가 매 사이클 읽는다.
  (쓰기는 tmp + os.replace 원자적 교체 — 프로세스 간 부분 읽기 없음)
- run-now(수동 실행)는 active 여부와 무관하게 항상 실행된다 (수동 실행은 명시적 의도).
"""
import os
import re
import json
import logging
import threading

logger = logging.getLogger("AutoUpdateControl")

# Base directory for config/ and ingestion_workspace/. Historically this was the
# server/ directory itself; it now resolves through the single override point
# (server/paths.py, ASSY_DATA_ROOT) so an isolated data root relocates both trees.
# Name kept as SERVER_DIR: callers and tests monkeypatch this exact symbol.
try:
    from paths import DATA_ROOT as SERVER_DIR
except ImportError:  # pragma: no cover - defensive fallback
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from paths import DATA_ROOT as SERVER_DIR
CONTROL_FILENAME = "auto_update_control.json"

# "<workspace>/<script.py>" — 경로 구분자·상위 탐색 문자 금지
# 파일명은 공백·한글 등 실존 가능한 문자를 허용하되 경로 구분자만 금지 —
# 실사용 파일명(예: "fetch_data copy.py")이 검증에 막히던 결함 수정(2026-07-25).
# 경로 탈출은 구분자 금지 + validate_script_key의 ".." 검사로 차단.
SCRIPT_KEY_RE = re.compile(r"^[^/\\]+/[^/\\]+\.py$")

_write_lock = threading.Lock()


def get_control_path(base_dir: str = None) -> str:
    """제어 파일의 절대 경로를 반환합니다."""
    return os.path.join(base_dir or SERVER_DIR, "config", CONTROL_FILENAME)


def validate_script_key(script_key) -> bool:
    """스크립트 키가 '<workspace>/<script.py>' 형식이고 경로 탈출이 없는지 검증합니다."""
    if not isinstance(script_key, str):
        return False
    if ".." in script_key:
        return False
    return bool(SCRIPT_KEY_RE.fullmatch(script_key))


def read_disabled_scripts(base_dir: str = None) -> set:
    """
    제어 파일에서 disabled 스크립트 키 집합을 읽어 반환합니다.
    파일 부재/손상 시 빈 집합(=전부 active)을 반환합니다 (fail-open).
    """
    path = get_control_path(base_dir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        disabled = data.get("disabled", [])
        if isinstance(disabled, list):
            return {s for s in disabled if isinstance(s, str)}
        logger.warning(f"Control file 'disabled' field is not a list; treating all scripts as active: {path}")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Failed to read auto update control file '{path}': {e}. Treating all scripts as active.")
    return set()


def set_script_active(script_key: str, active: bool, base_dir: str = None) -> None:
    """
    스크립트의 active 상태를 제어 파일에 영속화합니다 (원자적 쓰기: tmp + os.replace).
    active=True 이면 disabled 목록에서 제거, False 이면 추가합니다.
    """
    with _write_lock:
        disabled = read_disabled_scripts(base_dir)
        if active:
            disabled.discard(script_key)
        else:
            disabled.add(script_key)

        path = get_control_path(base_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"disabled": sorted(disabled)}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)


def resolve_script_file(script_key: str, base_dir: str = None) -> str:
    """스크립트 키를 실제 파일 경로(server/ingestion_workspace/<ws>/auto_update/<script.py>)로 변환합니다."""
    workspace, script_name = script_key.split("/", 1)
    return os.path.join(
        base_dir or SERVER_DIR, "ingestion_workspace", workspace, "auto_update", script_name
    )
