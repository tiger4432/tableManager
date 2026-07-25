"""워크스페이스 config.json 폐지(2026-07-25) 검증.

- ① 별칭 테이블 인제션: table_config 항목의 `workspace_name`(폴더명↔테이블명 별칭) 기반 동작
- ② std_parse=false 옵트아웃: table_config 항목의 `std_parse` 기반 + 핫리로드(F4 해소)
- ③ 레거시 config.json 하위호환: 구식 워크스페이스 그대로 동작 + deprecation 경고 1회
- ④ 자동 생성(auto-provision) 시 config.json 미생성
- 우선순위 규칙: 두 원천 충돌 시 table_config.json 승리

테스트 테이블명은 `wscfg_test_*` 접두(사용자 실 config와 충돌 불가 이름)만 사용한다.
"""

import json
import logging
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher
from directory_watcher import (
    IngestionHandler,
    WorkspaceWatcher,
    find_workspace_alias,
    resolve_workspace_root,
)


TABLE_INFO = {
    "business_key": "part_no",
    "column_types": {
        "part_no": "string",
        "category": "string",
        "stock_qty": "number",
    },
    "display_columns": ["part_no", "category", "stock_qty"],
}

WATCHER_LOGGER = "Watcher.DirectoryWatcher"


class _FakeDB:
    def add(self, obj):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _install_fake_crud(monkeypatch, applied):
    def fake_apply_batch_updates(db, table_name, batch_obj):
        applied.append((table_name, batch_obj))
        n = len(batch_obj.updates)
        return [], [(f"r{i}", "c") for i in range(n)], [], []

    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: _FakeDB())
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", fake_apply_batch_updates)


def _make_bare_workspace(base, folder_name):
    """config.json 없는 신식(post-deprecation) 워크스페이스."""
    ws = base / folder_name
    for sub in ("raws", "archives", "err", "config"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    return ws


def _write_csv(ws, name="drop.csv", body="part_no,category,stock_qty\nP-1,Cap,1\nP-2,Res,2\n"):
    p = ws / "raws" / name
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    return str(p)


# ---------------------------------------------------------------------------
# ① workspace_name 별칭 — table_config 단일 원천으로 폴더≠테이블명 인제션 동작
# ---------------------------------------------------------------------------

def test_alias_table_name_resolution(tmp_path, monkeypatch):
    fake = {"wscfg_test_alias_tbl": dict(TABLE_INFO, workspace_name="wscfg_test_folder")}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws = _make_bare_workspace(tmp_path, "wscfg_test_folder")
    handler = IngestionHandler(
        workspace_path=str(ws),
        config_path=None,
        archives_path=str(ws / "archives"),
        default_table_name=None,
    )
    assert handler.table_name == "wscfg_test_alias_tbl"


def test_alias_workspace_registered_and_ingested(tmp_path, monkeypatch):
    """discover_and_watch가 별칭 워크스페이스를 감시 대상으로 편입하고,
    파일 드롭 처리 결과가 별칭 대상 테이블(table_config 키)로 업서트된다."""
    fake = {"wscfg_test_alias_tbl": dict(TABLE_INFO, workspace_name="wscfg_test_folder")}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)
    applied = []
    _install_fake_crud(monkeypatch, applied)

    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()

    # 자동 생성 폴더명은 workspace_name 별칭을 따른다 (테이블명 폴더가 아니라)
    raws_path = os.path.abspath(str(base / "wscfg_test_folder" / "raws"))
    assert raws_path in watcher.watched_raw_paths
    assert not (base / "wscfg_test_alias_tbl").exists()

    handler = watcher.handlers_by_raw_path[raws_path]
    assert handler.table_name == "wscfg_test_alias_tbl"

    p = _write_csv(base / "wscfg_test_folder")
    handler.process_with_retry(p, uploader="tester", delay=0.01)

    assert len(applied) == 1
    table_name, batch_obj = applied[0]
    assert table_name == "wscfg_test_alias_tbl"
    assert [u.business_key_val for u in batch_obj.updates] == ["P-1", "P-2"]
    # 원본은 archives/로 이동 (성공 경로)
    assert os.path.exists(str(base / "wscfg_test_folder" / "archives" / "drop.csv"))


# ---------------------------------------------------------------------------
# ② std_parse 옵트아웃 — table_config 기반 + 핫리로드(F4 해소)
# ---------------------------------------------------------------------------

def test_std_parse_optout_via_table_config(tmp_path, monkeypatch):
    fake = {"wscfg_test_std": dict(TABLE_INFO, std_parse=False)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws = _make_bare_workspace(tmp_path, "wscfg_test_std")
    handler = IngestionHandler(str(ws), None, str(ws / "archives"), default_table_name="wscfg_test_std")

    assert handler.std_parse_enabled is False
    p = _write_csv(ws)
    with pytest.raises(ValueError) as excinfo:
        handler._resolve_rows(p)
    assert "No custom pipeline parser matched" in str(excinfo.value)


def test_std_parse_optout_is_hot_reloadable(tmp_path, monkeypatch):
    """[F4 해소] 핸들러 재생성/재기동 없이 table_config 변경이 **파일 경계에서** 반영된다
    (처리 중인 파일은 시작 시점 스냅샷으로 완결 — D1)."""
    fake = {"wscfg_test_std": dict(TABLE_INFO, std_parse=False)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws = _make_bare_workspace(tmp_path, "wscfg_test_std")
    handler = IngestionHandler(str(ws), None, str(ws / "archives"), default_table_name="wscfg_test_std")
    assert handler.std_parse_enabled is False

    # 핫리로드 시뮬레이션: 같은 핸들러 인스턴스 그대로 config만 갱신
    fake["wscfg_test_std"] = dict(TABLE_INFO, std_parse=True)
    assert handler.std_parse_enabled is True

    p = _write_csv(ws)
    rows, total, skipped = handler._resolve_rows(p)
    assert total == 2

    # 다시 옵트아웃 — 역방향도 즉시 반영
    fake["wscfg_test_std"] = dict(TABLE_INFO, std_parse=False)
    assert handler.std_parse_enabled is False


def test_std_parse_default_true_when_absent(tmp_path, monkeypatch):
    fake = {"wscfg_test_std": dict(TABLE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws = _make_bare_workspace(tmp_path, "wscfg_test_std")
    handler = IngestionHandler(str(ws), None, str(ws / "archives"), default_table_name="wscfg_test_std")
    assert handler.std_parse_enabled is True


# ---------------------------------------------------------------------------
# ③ 레거시 config.json 하위호환 + deprecation 경고
# ---------------------------------------------------------------------------

def _make_legacy_workspace(base, folder_name, legacy_cfg):
    ws = _make_bare_workspace(base, folder_name)
    config_path = ws / "config" / "config.json"
    config_path.write_text(json.dumps(legacy_cfg), encoding="utf-8")
    return ws, config_path


def test_legacy_config_still_works_with_warning(tmp_path, monkeypatch, caplog):
    """구식 워크스페이스(config.json의 table_name/std_parse)는 그대로 동작하되 경고가 1회 남는다."""
    fake = {"wscfg_test_legacy_tbl": dict(TABLE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws, config_path = _make_legacy_workspace(
        tmp_path, "wscfg_test_legacy_folder",
        {"table_name": "wscfg_test_legacy_tbl", "std_parse": False},
    )
    handler = IngestionHandler(str(ws), str(config_path), str(ws / "archives"))

    with caplog.at_level(logging.WARNING, logger=WATCHER_LOGGER):
        # 반복 접근해도 경고는 경로당 1회만
        assert handler.table_name == "wscfg_test_legacy_tbl"
        assert handler.table_name == "wscfg_test_legacy_tbl"
        assert handler.std_parse_enabled is False

    dep_warnings = [r for r in caplog.records if "[DEPRECATED]" in r.getMessage()]
    assert len(dep_warnings) == 1
    assert "table_config.json" in dep_warnings[0].getMessage()


def test_register_workspace_warns_on_startup(tmp_path, monkeypatch, caplog):
    """기동(discover_and_watch) 시 레거시 config 보유 워크스페이스에 경고가 남는다."""
    fake = {"wscfg_test_boot_tbl": dict(TABLE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)
    # provisioning이 다른 폴더를 만들지 않도록 차단하고 등록 경로만 검증
    monkeypatch.setattr(WorkspaceWatcher, "_provision_workspaces", lambda self: [])

    base = tmp_path / "ingestion_workspace"
    ws, _ = _make_legacy_workspace(base, "wscfg_test_boot_folder", {"table_name": "wscfg_test_boot_tbl"})

    watcher = WorkspaceWatcher(str(base))
    with caplog.at_level(logging.WARNING, logger=WATCHER_LOGGER):
        watcher.discover_and_watch()

    assert watcher.watch_count == 1
    assert any("[DEPRECATED]" in r.getMessage() for r in caplog.records)


def test_no_false_deprecation_for_non_config_json(tmp_path, monkeypatch, caplog):
    """[D4] 커스텀 규칙 파일(비 config.json, 소비 필드 없음)은 등록 시 [DEPRECATED] 미발화."""
    fake = {"wscfg_test_rules": dict(TABLE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)
    monkeypatch.setattr(WorkspaceWatcher, "_provision_workspaces", lambda self: [])

    base = tmp_path / "ingestion_workspace"
    ws = _make_bare_workspace(base, "wscfg_test_rules")
    (ws / "config" / "wscfg_rules.json").write_text('{"rules": []}', encoding="utf-8")

    watcher = WorkspaceWatcher(str(base))
    with caplog.at_level(logging.WARNING, logger=WATCHER_LOGGER):
        watcher.discover_and_watch()

    assert watcher.watch_count == 1
    assert not any("[DEPRECATED]" in r.getMessage() for r in caplog.records)


def test_table_config_wins_over_legacy_config(tmp_path, monkeypatch):
    """우선순위 규칙: 두 원천 충돌 시 table_config.json이 승리한다."""
    folder = "wscfg_test_conflict_folder"
    fake = {"wscfg_test_new_tbl": dict(TABLE_INFO, workspace_name=folder, std_parse=True)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    # 레거시는 다른 테이블명 + 옵트아웃을 주장하지만 글로벌이 이긴다
    ws, config_path = _make_legacy_workspace(
        tmp_path, folder, {"table_name": "wscfg_test_old_tbl", "std_parse": False}
    )
    handler = IngestionHandler(str(ws), str(config_path), str(ws / "archives"))

    assert handler.table_name == "wscfg_test_new_tbl"
    assert handler.std_parse_enabled is True


def test_legacy_fallback_when_global_has_no_fields(tmp_path, monkeypatch):
    """글로벌 항목에 workspace_name/std_parse가 없으면 레거시 값이 폴백으로 유지된다."""
    fake = {"wscfg_test_fb_tbl": dict(TABLE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws, config_path = _make_legacy_workspace(
        tmp_path, "wscfg_test_fb_folder", {"table_name": "wscfg_test_fb_tbl", "std_parse": False}
    )
    handler = IngestionHandler(str(ws), str(config_path), str(ws / "archives"))

    assert handler.table_name == "wscfg_test_fb_tbl"
    assert handler.std_parse_enabled is False


# ---------------------------------------------------------------------------
# ④ 자동 생성 시 config.json 미생성
# ---------------------------------------------------------------------------

def test_auto_provision_creates_no_config_json(tmp_path, monkeypatch):
    fake = {"wscfg_test_auto": dict(TABLE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    watcher = WorkspaceWatcher(str(base))
    provisioned = watcher._provision_workspaces()

    assert provisioned == ["wscfg_test_auto"]
    for sub in ("raws", "archives", "err", "auto_update", "scripts", "config"):
        assert (base / "wscfg_test_auto" / sub).is_dir()
    assert list((base / "wscfg_test_auto" / "config").iterdir()) == []

    # 멱등: 재실행 시 아무것도 만들지 않는다
    assert watcher._provision_workspaces() == []


def test_auto_provision_without_config_still_registers(tmp_path, monkeypatch):
    """config.json 없이도 폴더명=테이블명 규약으로 즉시 감시·인제션 가능해야 한다."""
    fake = {"wscfg_test_auto": dict(TABLE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)
    applied = []
    _install_fake_crud(monkeypatch, applied)

    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()
    assert watcher.watch_count == 1

    raws_path = os.path.abspath(str(base / "wscfg_test_auto" / "raws"))
    handler = watcher.handlers_by_raw_path[raws_path]
    assert handler.table_name == "wscfg_test_auto"

    p = _write_csv(base / "wscfg_test_auto")
    handler.process_with_retry(p, uploader="tester", delay=0.01)
    assert len(applied) == 1 and applied[0][0] == "wscfg_test_auto"


def test_unsafe_workspace_name_ignored(tmp_path, monkeypatch, caplog):
    """상대경로 탈출형 workspace_name은 무시하고 테이블명 폴더로 생성한다 (경로 탈출 방지)."""
    fake = {"wscfg_test_evil": dict(TABLE_INFO, workspace_name="../wscfg_escape")}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    watcher = WorkspaceWatcher(str(base))
    with caplog.at_level(logging.WARNING, logger=WATCHER_LOGGER):
        watcher._provision_workspaces()

    assert (base / "wscfg_test_evil" / "raws").is_dir()
    assert not (tmp_path / "wscfg_escape").exists()
    assert any("unsafe workspace_name" in r.getMessage() for r in caplog.records)


def test_drive_relative_alias_escape_blocked(tmp_path, monkeypatch, caplog):
    """[D2] Windows 드라이브 상대경로(`C:evil`) 별칭 — join이 base를 폐기/변형하는
    탈출 경로를 결과 기반 검사로 차단하고 테이블명 폴더로 폴백한다."""
    fake = {"wscfg_test_drive": dict(TABLE_INFO, workspace_name="C:wscfg_evil")}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    watcher = WorkspaceWatcher(str(base))
    with caplog.at_level(logging.WARNING, logger=WATCHER_LOGGER):
        watcher._provision_workspaces()

    assert (base / "wscfg_test_drive" / "raws").is_dir()
    assert not (base / "wscfg_evil").exists()  # 동일 드라이브 변형 통과도 불가
    assert any("unsafe workspace_name" in r.getMessage() for r in caplog.records)


def test_dotted_but_safe_alias_allowed(tmp_path, monkeypatch):
    """[D2 부수] `..` 부분문자열이 든 안전한 이름(`..wscfg_dots`)은 오차단하지 않는다
    (구식 문자 블랙리스트의 false positive 해소 — 결과 기반 검사)."""
    fake = {"wscfg_test_dots": dict(TABLE_INFO, workspace_name="..wscfg_dots")}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    watcher = WorkspaceWatcher(str(base))
    watcher._provision_workspaces()

    assert (base / "..wscfg_dots" / "raws").is_dir()
    assert not (base / "wscfg_test_dots").exists()


# ---------------------------------------------------------------------------
# [D1] 파일 처리 도중 config 변경 — 파일당 1회 스냅샷 정합
# ---------------------------------------------------------------------------

def test_snapshot_consistency_under_mid_file_config_change(tmp_path, monkeypatch):
    """[D1] 스냅샷(첫 로드) 이후 config가 바뀌어도(별칭 탈취·항목 소실) 처리 중인
    파일은 시작 시점 테이블/스키마로 완결된다 — 오배송·무음 0행 업서트 차단."""
    applied = []
    _install_fake_crud(monkeypatch, applied)

    cfg_initial = {"wscfg_test_snap": dict(TABLE_INFO)}
    # 스냅샷 이후 상태: 원 테이블 소실 + 다른 테이블이 이 폴더를 별칭으로 탈취
    cfg_flipped = {"wscfg_test_snap_x": dict(TABLE_INFO, workspace_name="wscfg_test_snap")}
    calls = {"n": 0}

    def flapping_config():
        calls["n"] += 1
        return cfg_initial if calls["n"] <= 1 else cfg_flipped

    monkeypatch.setattr(directory_watcher, "load_global_table_config", flapping_config)

    ws = _make_bare_workspace(tmp_path, "wscfg_test_snap")
    handler = IngestionHandler(str(ws), None, str(ws / "archives"), default_table_name=None)
    p = _write_csv(ws)
    handler.process_with_retry(p, uploader="tester", delay=0.01)

    # 구현이 재조회로 회귀하면: 별칭 탈취로 t=wscfg_test_snap_x(오배송) 또는
    # table_info 소실로 applied가 비게 된다(무음 0행 SUCCESS).
    assert len(applied) == 1
    t_name, batch_obj = applied[0]
    assert t_name == "wscfg_test_snap"
    assert len(batch_obj.updates) == 2
    assert os.path.exists(str(ws / "archives" / "drop.csv"))


# ---------------------------------------------------------------------------
# [D3] 별칭 충돌 — 섀도잉·중복 무효화(+ERROR 1회) 및 재시도 역조회
# ---------------------------------------------------------------------------

def test_alias_colliding_with_table_name_ignored(tmp_path, monkeypatch, caplog):
    """[D3-①] 별칭이 다른 실존 테이블명과 동명이면 무시(ERROR 1회) — 섀도잉 차단."""
    fake = {
        "wscfg_test_real": dict(TABLE_INFO),
        "wscfg_test_shadow": dict(TABLE_INFO, workspace_name="wscfg_test_real"),
    }
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws = _make_bare_workspace(tmp_path, "wscfg_test_real")
    handler = IngestionHandler(str(ws), None, str(ws / "archives"), default_table_name=None)

    with caplog.at_level(logging.ERROR, logger=WATCHER_LOGGER):
        # 반복 접근해도 [D5] ERROR는 1회만
        assert handler.table_name == "wscfg_test_real"
        assert handler.table_name == "wscfg_test_real"

    errs = [r for r in caplog.records if "collides with an existing table name" in r.getMessage()]
    assert len(errs) == 1


def test_duplicate_alias_all_ignored_with_error(caplog):
    """[D3-②] 동일 별칭 복수 선언은 전부 무효(ERROR 1회) — 어느 쪽도 폴더를 갖지 못한다."""
    folder = "wscfg_test_dup_folder"
    cfg = {
        "wscfg_test_dup_a": dict(TABLE_INFO, workspace_name=folder),
        "wscfg_test_dup_b": dict(TABLE_INFO, workspace_name=folder),
    }
    with caplog.at_level(logging.ERROR, logger=WATCHER_LOGGER):
        assert find_workspace_alias(folder, cfg) is None
        assert find_workspace_alias(folder, cfg) is None  # [D5] dedup

    errs = [r for r in caplog.records if "Duplicate workspace_name alias" in r.getMessage()]
    assert len(errs) == 1


def test_self_alias_is_allowed():
    """자기 테이블명을 별칭으로 쓴 자기-별칭은 충돌이 아니다."""
    cfg = {"wscfg_test_self": dict(TABLE_INFO, workspace_name="wscfg_test_self")}
    assert find_workspace_alias("wscfg_test_self", cfg) == "wscfg_test_self"


def test_resolve_workspace_root_reverse_alias(tmp_path):
    """[D3] 재시도 경로용 테이블→워크스페이스 역조회 — 유효 별칭은 별칭 폴더,
    충돌 무효 별칭·별칭 부재는 테이블명 폴더."""
    base = str(tmp_path / "iw")

    cfg = {"wscfg_test_a": dict(TABLE_INFO, workspace_name="wscfg_test_a_folder")}
    assert resolve_workspace_root(base, "wscfg_test_a", cfg) == os.path.abspath(
        os.path.join(base, "wscfg_test_a_folder")
    )

    # 충돌(다른 실존 테이블명과 동명)로 무효화된 별칭 → 테이블명 폴백 (정방향과 대칭)
    cfg2 = {
        "wscfg_test_b": dict(TABLE_INFO),
        "wscfg_test_c": dict(TABLE_INFO, workspace_name="wscfg_test_b"),
    }
    assert resolve_workspace_root(base, "wscfg_test_c", cfg2) == os.path.abspath(
        os.path.join(base, "wscfg_test_c")
    )

    # 별칭 없음 → 테이블명
    assert resolve_workspace_root(base, "wscfg_test_plain", {}) == os.path.abspath(
        os.path.join(base, "wscfg_test_plain")
    )


# ---------------------------------------------------------------------------
# [D6] std_parse 타입 검증 — 문자열 "false"는 옵트아웃이 아니다 (경고 1회)
# ---------------------------------------------------------------------------

def test_string_false_std_parse_warns_and_stays_enabled(tmp_path, monkeypatch, caplog):
    fake = {"wscfg_test_d6": dict(TABLE_INFO, std_parse="false")}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    ws = _make_bare_workspace(tmp_path, "wscfg_test_d6")
    handler = IngestionHandler(str(ws), None, str(ws / "archives"), default_table_name="wscfg_test_d6")

    with caplog.at_level(logging.WARNING, logger=WATCHER_LOGGER):
        assert handler.std_parse_enabled is True  # 무효 값 → 기본 활성 유지
        assert handler.std_parse_enabled is True  # 반복 접근에도 경고 1회

    warns = [r for r in caplog.records if "non-boolean 'std_parse'" in r.getMessage()]
    assert len(warns) == 1
