"""표준 파서(Std Parser) 폴백 + 워크스페이스 자동 생성 검증.

- 커스텀 파이프라인 디스커버리 우선(하위호환) / 무매칭 시에만 std 폴백
- 인코딩(utf-8-sig → cp949), 구분자(csv/tsv 고정, txt sniff)
- 헤더 검증: column_types 대조, 미지 컬럼 무시, business_key(또는 composite 전체) 누락 시 거부
- 빈 파일/헤더만 있는 파일 안전 처리, 옵트아웃(std_parse: false)
- [F1] 키 컬럼 공백 행 스킵+카운트+완료 메시지 반영, 재드롭 멱등(고아 행 미생성)
- [F5] 헤더 검증 기준 = 적재 필터(display_columns)와 동일 집합
- WorkspaceWatcher: table_config 기반 워크스페이스 자동 보충(기존 파일·설정 변경 없음·제외 목록)
- [F2] sync_new_workspaces 직렬화(동시 reload 이중 schedule 방지), [F3] 0-watch 기동 후 런타임 observer 기동
"""

import json
import os
import sys

import pytest

# Ensure server/parsers is in python path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher
from directory_watcher import IngestionHandler, WorkspaceWatcher
from std_parser import parse_std_file, is_std_supported


INVENTORY_INFO = {
    "business_key": "part_no",
    "column_types": {
        "part_no": "string",
        "category": "string",
        "stock_qty": "number",
    },
    "display_columns": ["part_no", "category", "stock_qty"],
}

COMPOSITE_INFO = {
    "business_key": "pkg_id",
    "composite_key_source": ["base", "x", "y"],
    "composite_key_separator": "_",
    "column_types": {
        "pkg_id": "string",
        "base": "string",
        "x": "number",
        "y": "number",
        "leg": "string",
    },
    "display_columns": ["pkg_id", "base", "x", "y", "leg"],
}


def _write(path, text, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(text)
    return str(path)


# ---------------------------------------------------------------------------
# parse_std_file 단위 검증
# ---------------------------------------------------------------------------

def test_std_supported_extensions():
    assert is_std_supported("a.csv") and is_std_supported("B.TXT") and is_std_supported("c.tsv")
    assert not is_std_supported("a.xlsx") and not is_std_supported("a.html")


def test_normal_csv(tmp_path):
    p = _write(tmp_path / "inv.csv", "part_no,category,stock_qty\nP-1,CapA,10\nP-2,CapB,\n")
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    rows = list(rows_iter)
    assert total == 2 and len(rows) == 2
    assert rows[0] == {"part_no": "P-1", "category": "CapA", "stock_qty": "10"}
    # 빈 셀은 None으로 정규화 (crud.cast_value_by_type가 최종 캐스팅 담당)
    assert rows[1]["stock_qty"] is None


def test_cp949_fallback(tmp_path):
    p = _write(tmp_path / "inv_kr.csv", "part_no,category,stock_qty\nP-1,콘덴서,5\n", encoding="cp949")
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    rows = list(rows_iter)
    assert total == 1
    assert rows[0]["category"] == "콘덴서"


def test_utf8_bom(tmp_path):
    p = _write(tmp_path / "inv_bom.csv", "﻿part_no,category,stock_qty\nP-9,Res,1\n")
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    assert total == 1
    assert list(rows_iter)[0]["part_no"] == "P-9"


def test_tsv_delimiter(tmp_path):
    p = _write(tmp_path / "inv.tsv", "part_no\tcategory\tstock_qty\nP-1\tCap\t3\n")
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    assert total == 1
    assert list(rows_iter)[0] == {"part_no": "P-1", "category": "Cap", "stock_qty": "3"}


def test_txt_sniff_tab_and_comma(tmp_path):
    p_tab = _write(tmp_path / "inv_tab.txt", "part_no\tcategory\tstock_qty\nP-1\tCap\t3\n")
    rows_iter, total, skipped = parse_std_file(p_tab, INVENTORY_INFO, "inventory_master")
    assert total == 1 and list(rows_iter)[0]["category"] == "Cap"

    p_comma = _write(tmp_path / "inv_comma.txt", "part_no,category,stock_qty\nP-2,Res,4\n")
    rows_iter, total, skipped = parse_std_file(p_comma, INVENTORY_INFO, "inventory_master")
    assert total == 1 and list(rows_iter)[0]["part_no"] == "P-2"


def test_unknown_columns_ignored(tmp_path):
    p = _write(tmp_path / "inv.csv", "part_no,MYSTERY_COL,category\nP-1,zzz,Cap\n")
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    rows = list(rows_iter)
    assert total == 1
    assert "MYSTERY_COL" not in rows[0]
    assert rows[0] == {"part_no": "P-1", "category": "Cap"}


def test_header_case_insensitive(tmp_path):
    p = _write(tmp_path / "inv.csv", "PART_NO,Category\nP-1,Cap\n")
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    rows = list(rows_iter)
    # canonical 컬럼명으로 정규화되어야 함
    assert rows[0] == {"part_no": "P-1", "category": "Cap"}


def test_reject_missing_business_key(tmp_path):
    p = _write(tmp_path / "inv.csv", "category,stock_qty\nCap,3\n")
    with pytest.raises(ValueError) as excinfo:
        parse_std_file(p, INVENTORY_INFO, "inventory_master")
    assert "part_no" in str(excinfo.value)
    assert "required key column" in str(excinfo.value)


def test_reject_no_known_columns(tmp_path):
    p = _write(tmp_path / "inv.csv", "foo,bar\n1,2\n")
    with pytest.raises(ValueError) as excinfo:
        parse_std_file(p, INVENTORY_INFO, "inventory_master")
    assert "no header column matches" in str(excinfo.value)


def test_composite_key_accepts_sources_without_bk(tmp_path):
    # bk(pkg_id)가 없어도 composite_key_source 전체가 있으면 허용 (crud가 키를 조립)
    p = _write(tmp_path / "map.csv", "base,x,y,leg\nB1,1,2,L\n")
    rows_iter, total, skipped = parse_std_file(p, COMPOSITE_INFO, "bonding_map")
    assert total == 1


def test_composite_key_rejects_partial_sources(tmp_path):
    # composite 소스 일부 누락 + bk도 없음 → 거부
    p = _write(tmp_path / "map.csv", "base,x,leg\nB1,1,L\n")
    with pytest.raises(ValueError):
        parse_std_file(p, COMPOSITE_INFO, "bonding_map")


def test_empty_and_header_only_files(tmp_path):
    p_empty = _write(tmp_path / "empty.csv", "")
    rows_iter, total, skipped = parse_std_file(p_empty, INVENTORY_INFO, "inventory_master")
    assert total == 0 and list(rows_iter) == []

    p_header = _write(tmp_path / "header_only.csv", "part_no,category,stock_qty\n")
    rows_iter, total, skipped = parse_std_file(p_header, INVENTORY_INFO, "inventory_master")
    assert total == 0 and list(rows_iter) == []


def test_blank_lines_skipped(tmp_path):
    p = _write(tmp_path / "inv.csv", "part_no,category\nP-1,Cap\n\n,,\nP-2,Res\n")
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    rows = list(rows_iter)
    assert total == 2 and len(rows) == 2


# ---------------------------------------------------------------------------
# [F1] 키 컬럼 공백 행 스킵 — 고아 행(업서트 불가 신규 행) 누적 방지
# ---------------------------------------------------------------------------

def test_blank_business_key_rows_skipped_and_counted(tmp_path):
    """단일 bk 값이 공백/결측인 행은 적재에서 제외되고 카운트된다."""
    p = _write(
        tmp_path / "inv.csv",
        "part_no,category,stock_qty\nP-1,Cap,1\n,Subtotal,99\n ,Note,3\nP-2,Res,2\n",
    )
    rows_iter, total, skipped = parse_std_file(p, INVENTORY_INFO, "inventory_master")
    rows = list(rows_iter)
    assert total == 2 and skipped == 2
    assert [r["part_no"] for r in rows] == ["P-1", "P-2"]


def test_composite_partial_blank_source_rows_skipped(tmp_path):
    """composite 소스 중 하나만 공백이어도 키 조립이 불가하므로 스킵된다."""
    p = _write(tmp_path / "map.csv", "base,x,y,leg\nB1,1,2,L\nB2,,3,L\n")
    rows_iter, total, skipped = parse_std_file(p, COMPOSITE_INFO, "bonding_map")
    rows = list(rows_iter)
    assert total == 1 and skipped == 1
    assert rows[0]["base"] == "B1"


def test_key_groups_bk_or_composite_either_suffices(tmp_path):
    """bk와 composite 소스가 함께 있으면 둘 중 한 그룹만 완전해도 keyed로 판정한다."""
    p = _write(
        tmp_path / "map.csv",
        "pkg_id,base,x,y\n,B1,1,2\nPK9,B2,,4\n,,5,6\n",
    )
    # 1행: bk 공백이지만 composite 전체 존재 → 유지 (crud가 키 조립)
    # 2행: composite 일부(x) 공백이지만 bk 존재 → 유지
    # 3행: bk 공백 + composite 일부(base) 공백 → 스킵
    rows_iter, total, skipped = parse_std_file(p, COMPOSITE_INFO, "bonding_map")
    rows = list(rows_iter)
    assert total == 2 and skipped == 1
    assert rows[0]["base"] == "B1" and rows[1]["pkg_id"] == "PK9"


# ---------------------------------------------------------------------------
# [F5] 헤더 검증 기준 = 적재 필터(display_columns)와 동일 집합
# ---------------------------------------------------------------------------

def test_header_validation_uses_display_columns(tmp_path):
    """column_types에만 있고 display_columns에 없는 컬럼은 미지 컬럼 취급(무음 탈락 방지)."""
    info = dict(INVENTORY_INFO)
    info["column_types"] = dict(INVENTORY_INFO["column_types"], internal_note="string")
    # display_columns는 그대로 → internal_note는 적재 불가 컬럼
    p = _write(tmp_path / "inv.csv", "part_no,internal_note,category\nP-1,secret,Cap\n")
    rows_iter, total, skipped = parse_std_file(p, info, "inventory_master")
    rows = list(rows_iter)
    assert total == 1
    assert rows[0] == {"part_no": "P-1", "category": "Cap"}
    assert "internal_note" not in rows[0]


# ---------------------------------------------------------------------------
# IngestionHandler 폴백 순서 / 옵트아웃
# ---------------------------------------------------------------------------

def _make_workspace(tmp_path, table_name="inventory_master", config_extra=None, script_body=None):
    ws = tmp_path / f"ws_{table_name}"
    (ws / "raws").mkdir(parents=True)
    (ws / "archives").mkdir()
    (ws / "config").mkdir()
    cfg = {"table_name": table_name, "columns": list(INVENTORY_INFO["column_types"].keys())}
    if config_extra:
        cfg.update(config_extra)
    config_path = ws / "config" / "config.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    if script_body is not None:
        (ws / "scripts").mkdir()
        (ws / "scripts" / "custom.py").write_text(script_body, encoding="utf-8")
    handler = IngestionHandler(
        workspace_path=str(ws),
        config_path=str(config_path),
        archives_path=str(ws / "archives"),
        default_table_name=table_name,
    )
    return ws, handler


@pytest.fixture
def fake_table_config(monkeypatch):
    fake = {"inventory_master": dict(INVENTORY_INFO), "bonding_map": dict(COMPOSITE_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)
    return fake


def test_custom_script_takes_priority_over_std(tmp_path, fake_table_config):
    """스크립트가 파일을 처리하면 std 폴백은 발동하지 않아야 한다."""
    script = """
from pipeline_base import BasePipelineParser

class AlwaysMatchParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        return True

    def parse(self, file_path: str):
        return [{"part_no": "FROM_CUSTOM_SCRIPT"}]
"""
    ws, handler = _make_workspace(tmp_path, script_body=script)
    p = _write(ws / "raws" / "data.csv", "part_no,category\nP-1,Cap\n")

    rows, total, skipped = handler._resolve_rows(p)
    assert total is None  # 커스텀 경로는 total_rows=None (기존 계약)
    assert rows == [{"part_no": "FROM_CUSTOM_SCRIPT"}]


def test_std_fallback_when_no_script(tmp_path, fake_table_config):
    ws, handler = _make_workspace(tmp_path)  # scripts 폴더 없음
    p = _write(ws / "raws" / "data.csv", "part_no,category\nP-1,Cap\nP-2,Res\n")

    rows, total, skipped = handler._resolve_rows(p)
    assert total == 2
    assert [r["part_no"] for r in rows] == ["P-1", "P-2"]


def test_std_fallback_when_script_matches_nothing(tmp_path, fake_table_config):
    script = """
from pipeline_base import BasePipelineParser

class NeverMatchParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        return False
"""
    ws, handler = _make_workspace(tmp_path, script_body=script)
    p = _write(ws / "raws" / "data.csv", "part_no,category\nP-1,Cap\n")

    rows, total, skipped = handler._resolve_rows(p)
    assert total == 1


def test_std_opt_out_via_config(tmp_path, fake_table_config):
    ws, handler = _make_workspace(tmp_path, config_extra={"std_parse": False})
    p = _write(ws / "raws" / "data.csv", "part_no,category\nP-1,Cap\n")

    with pytest.raises(ValueError) as excinfo:
        handler._resolve_rows(p)
    assert "No custom pipeline parser matched" in str(excinfo.value)


def test_std_skipped_for_unknown_table(tmp_path, monkeypatch):
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {})
    ws, handler = _make_workspace(tmp_path)
    p = _write(ws / "raws" / "data.csv", "part_no,category\nP-1,Cap\n")

    with pytest.raises(ValueError):
        handler._resolve_rows(p)


def test_std_unsupported_extension_not_parsed(tmp_path, fake_table_config):
    ws, handler = _make_workspace(tmp_path)
    p = _write(ws / "raws" / "data.xlsx", "not really excel")

    with pytest.raises(ValueError):
        handler._resolve_rows(p)


# ---------------------------------------------------------------------------
# 전체 처리 경로 (process_with_retry) — 가짜 DB/crud로 통합 흐름 검증
# ---------------------------------------------------------------------------

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
        changed = [(f"r{i}", "c") for i in range(n)]
        return [], changed, [], []

    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: _FakeDB())
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", fake_apply_batch_updates)


def test_process_with_retry_std_success_archives_file(tmp_path, fake_table_config, monkeypatch):
    applied = []
    _install_fake_crud(monkeypatch, applied)

    events = {"progress": [], "processed": [], "refresh": []}
    ws, handler = _make_workspace(tmp_path)
    handler.on_progress_callback = lambda t, f, pct, done, total: events["progress"].append((pct, done, total))
    handler.on_file_processed_callback = lambda t, f, status, err: events["processed"].append((f, status, err))
    handler.on_refresh_callback = lambda t, count, logs, total_logs: events["refresh"].append((t, count))

    p = _write(ws / "raws" / "drop.csv", "part_no,category,stock_qty\nP-1,Cap,1\nP-2,Res,2\nP-3,Ind,3\n")
    handler.process_with_retry(p, uploader="tester", delay=0.01)

    # 1) 업서트가 기존 통합 경로로 흘렀는가
    assert len(applied) == 1
    table_name, batch_obj = applied[0]
    assert table_name == "inventory_master"
    assert len(batch_obj.updates) == 3
    assert batch_obj.updates[0].business_key_val == "P-1"
    # source_name은 기존 파이프라인 경로와 동일하게 원본 파일명 기반
    assert batch_obj.updates[0].source_name == "drop.csv"

    # 2) 진행/완료 이벤트 (기존 콜백 계약 그대로)
    assert events["progress"][-1] == (100, 3, 3)
    assert events["processed"] == [("drop.csv", "SUCCESS", None)]
    assert events["refresh"] and events["refresh"][0][0] == "inventory_master"

    # 3) 원본은 archives/로 이동
    assert not os.path.exists(p)
    assert os.path.exists(str(ws / "archives" / "drop.csv"))


def test_process_with_retry_rejects_missing_bk_to_err(tmp_path, fake_table_config, monkeypatch):
    applied = []
    _install_fake_crud(monkeypatch, applied)

    events = {"processed": []}
    ws, handler = _make_workspace(tmp_path)
    handler.on_file_processed_callback = lambda t, f, status, err: events["processed"].append((f, status))

    p = _write(ws / "raws" / "no_bk.csv", "category,stock_qty\nCap,1\n")
    handler.process_with_retry(p, uploader="tester", delay=0.01)

    assert applied == []  # 적재 시도 자체가 없어야 함
    assert events["processed"] == [("no_bk.csv", "FAILED")]
    assert not os.path.exists(p)
    assert os.path.exists(str(ws / "err" / "no_bk.csv"))


def test_process_with_retry_empty_file_archives_without_upsert(tmp_path, fake_table_config, monkeypatch):
    applied = []
    _install_fake_crud(monkeypatch, applied)

    events = {"processed": []}
    ws, handler = _make_workspace(tmp_path)
    handler.on_file_processed_callback = lambda t, f, status, err: events["processed"].append((f, status))

    p = _write(ws / "raws" / "empty.csv", "")
    handler.process_with_retry(p, uploader="tester", delay=0.01)

    assert applied == []
    assert events["processed"] == [("empty.csv", "SUCCESS")]
    assert os.path.exists(str(ws / "archives" / "empty.csv"))


def test_process_with_retry_skip_count_in_completion_detail(tmp_path, fake_table_config, monkeypatch):
    """[F1] 키 결측 스킵 수가 완료 콜백 detail(→ file_ingestion_completed 메시지)에 반영된다."""
    applied = []
    _install_fake_crud(monkeypatch, applied)

    events = {"processed": []}
    ws, handler = _make_workspace(tmp_path)
    handler.on_file_processed_callback = lambda t, f, status, detail: events["processed"].append((f, status, detail))

    p = _write(ws / "raws" / "mix.csv", "part_no,category\nP-1,Cap\n,Subtotal\n,Note\n")
    handler.process_with_retry(p, uploader="tester", delay=0.01)

    # 파일 전체는 성공(정상 행은 적재), 스킵 사실이 detail로 노출
    assert events["processed"] == [("mix.csv", "SUCCESS", "키 결측으로 2행 스킵")]
    assert len(applied) == 1
    _, batch_obj = applied[0]
    assert len(batch_obj.updates) == 1
    assert batch_obj.updates[0].business_key_val == "P-1"
    assert os.path.exists(str(ws / "archives" / "mix.csv"))


def test_redrop_idempotent_no_orphan_key_items(tmp_path, fake_table_config, monkeypatch):
    """[F1] 같은 파일을 재드롭해도 키 없는 항목(business_key_val=None)이 crud로 전달되지 않는다
    — _get_or_create_row가 매번 신규 행을 만드는 고아 행 누적 경로 원천 차단."""
    applied = []
    _install_fake_crud(monkeypatch, applied)

    ws, handler = _make_workspace(tmp_path)
    content = "part_no,category\nP-1,Cap\n,Orphan1\n,Orphan2\n"
    for _ in range(2):  # 재드롭
        p = _write(ws / "raws" / "redrop.csv", content)
        handler.process_with_retry(p, uploader="tester", delay=0.01)

    all_items = [item for _, batch in applied for item in batch.updates]
    # 드롭 2회 × 키 있는 행 1건 — 키 결측 행은 어느 드롭에서도 전달되지 않는다
    assert len(all_items) == 2
    assert all(item.business_key_val == "P-1" for item in all_items)


def test_send_to_upsert_iterator_chunks_and_progress(tmp_path, fake_table_config, monkeypatch):
    """이터레이터 + total_rows 경로: 1000행 청킹과 진행률이 정확해야 한다."""
    applied = []
    _install_fake_crud(monkeypatch, applied)

    progress = []
    ws, handler = _make_workspace(tmp_path)
    handler.on_progress_callback = lambda t, f, pct, done, total: progress.append((pct, done, total))
    handler.on_refresh_callback = lambda *a: None

    total = 2500
    row_gen = ({"part_no": f"P-{i}", "category": "c"} for i in range(total))
    handler._send_to_upsert(row_gen, uploader="t", filename="big.csv", total_rows=total)

    assert [len(b.updates) for _, b in applied] == [1000, 1000, 500]
    assert progress == [(40, 1000, 2500), (80, 2000, 2500), (100, 2500, 2500)]


# ---------------------------------------------------------------------------
# WorkspaceWatcher: 워크스페이스 자동 생성 + 런타임 감시 등록
# ---------------------------------------------------------------------------

def test_provision_creates_missing_workspaces(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    fake = {
        "new_table": dict(INVENTORY_INFO),
        "wafer_map_metadata": dict(INVENTORY_INFO),  # 제외 목록
    }
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: fake)

    watcher = WorkspaceWatcher(str(base))
    provisioned = watcher._provision_workspaces()

    assert "new_table" in provisioned
    for sub in ("raws", "archives", "err", "auto_update", "scripts", "config"):
        assert (base / "new_table" / sub).is_dir()
    # [Deprecation 2026-07-25] 워크스페이스 config.json은 더 이상 자동 생성하지 않는다
    assert not (base / "new_table" / "config" / "config.json").exists()
    # 시스템 내부 테이블은 생성하지 않는다
    assert not (base / "wafer_map_metadata").exists()


def test_provision_never_touches_existing_files(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    ws = base / "existing_table"
    (ws / "raws").mkdir(parents=True)
    (ws / "config").mkdir()
    # 사용자 커스텀 config(비표준 파일명) + raws 내 파일
    (ws / "config" / "my_custom.json").write_text('{"table_name": "existing_table", "std_parse": false}', encoding="utf-8")
    (ws / "raws" / "pending.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {"existing_table": dict(INVENTORY_INFO)})

    watcher = WorkspaceWatcher(str(base))
    watcher._provision_workspaces()

    # 누락 폴더는 보충되지만
    assert (ws / "err").is_dir() and (ws / "archives").is_dir()
    # 기존 config는 덮어쓰지 않고, json이 이미 있으므로 config.json도 추가 생성하지 않는다
    assert not (ws / "config" / "config.json").exists()
    assert json.loads((ws / "config" / "my_custom.json").read_text(encoding="utf-8"))["std_parse"] is False
    # 기존 파일 무접촉
    assert (ws / "raws" / "pending.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_discover_and_watch_provisions_and_registers(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {"auto_table": dict(INVENTORY_INFO)})

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()

    assert watcher.watch_count == 1
    raws_path = os.path.abspath(str(base / "auto_table" / "raws"))
    assert raws_path in watcher.watched_raw_paths


def test_sync_new_workspaces_registers_only_new(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {"table_a": dict(INVENTORY_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()
    assert watcher.watch_count == 1

    # 멱등성: 변화 없으면 재등록 0
    assert watcher.sync_new_workspaces() == 0
    assert watcher.watch_count == 1

    # 신규 테이블이 config에 추가되면 런타임 동기화로 감시 편입
    config["table_b"] = dict(INVENTORY_INFO)
    assert watcher.sync_new_workspaces() == 1
    assert watcher.watch_count == 2
    assert os.path.abspath(str(base / "table_b" / "raws")) in watcher.watched_raw_paths


def test_folder_name_convention_without_config(tmp_path, monkeypatch):
    """config.json이 없어도 폴더명=테이블명 규약으로 감시 대상에 포함되어야 한다."""
    base = tmp_path / "ingestion_workspace"
    ws = base / "known_table"
    (ws / "raws").mkdir(parents=True)  # config도 scripts도 없음

    # provisioning이 config를 만들어버리면 규약 자체를 검증할 수 없으므로 미등록 테이블로 우회:
    # provisioning 대상 config는 비우고, 등록 판단용 config에만 known_table을 넣는다.
    monkeypatch.setattr(directory_watcher.WorkspaceWatcher, "_provision_workspaces", lambda self: [])
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {"known_table": dict(INVENTORY_INFO)})

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()
    assert watcher.watch_count == 1

    # 미등록 테이블 폴더는 여전히 스킵
    ws2 = base / "unknown_folder"
    (ws2 / "raws").mkdir(parents=True)
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {})
    assert watcher.sync_new_workspaces() == 0


# ---------------------------------------------------------------------------
# [F2] 동시 reload 시 sync_new_workspaces 직렬화 (이중 schedule 레이스 방지)
# ---------------------------------------------------------------------------

class _SlowFakeObserver:
    """schedule()을 느리게 만들어 check-then-add 레이스 윈도를 확실히 벌린다."""

    def __init__(self):
        self.scheduled = []

    def schedule(self, handler, path, recursive=False):
        import time as _time
        _time.sleep(0.05)
        self.scheduled.append(os.path.abspath(path))

    def is_alive(self):
        return True


def test_sync_new_workspaces_concurrent_no_duplicate_schedule(tmp_path, monkeypatch):
    import threading

    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {"table_x": dict(INVENTORY_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)

    watcher = WorkspaceWatcher(str(base))
    assert hasattr(watcher, "_sync_lock"), "[F2] sync 직렬화 락이 있어야 한다"
    watcher.observer = _SlowFakeObserver()

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(watcher.sync_new_workspaces()))
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    raws = os.path.abspath(str(base / "table_x" / "raws"))
    # 락이 없으면 두 스레드 모두 멤버십 검사를 통과해 schedule이 2회 호출된다
    assert watcher.observer.scheduled.count(raws) == 1
    assert sorted(results) == [0, 1]
    assert watcher.watch_count == 1


# ---------------------------------------------------------------------------
# [F3] 기동 시 watch 0건 → 런타임 등록 시 observer 자동 기동
# ---------------------------------------------------------------------------

def test_sync_starts_observer_when_boot_had_zero_watches(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()
    watcher.start(blocking=False)  # watch 0건 → observer 미기동 (기존 동작)
    assert not watcher.observer.is_alive()

    try:
        # 런타임에 신규 테이블 등록 → 감시 편입과 함께 observer가 기동되어야 이벤트가 발화한다
        config["late_table"] = dict(INVENTORY_INFO)
        assert watcher.sync_new_workspaces() == 1
        assert watcher.observer.is_alive(), "[F3] 런타임 등록 시 observer가 기동되어야 한다"
    finally:
        if watcher.observer.is_alive():
            watcher.stop()
