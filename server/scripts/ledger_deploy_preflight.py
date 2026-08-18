"""Read-only preflight: what happens to THIS box when the v2 ledger lands.

Today's change removed the legacy execution path and made the old five-file setup
unloadable.  Whether that is harmless or a stoppage depends on what this box is
standing on, and that cannot be answered from a developer machine.  Run this here,
on the box you are about to deploy to, and it will say which case it is.

Reads only.  It opens config files, asks the database for table and cursor rows, and
writes nothing.  It does not import the ledger, so it is safe to run BEFORE the new
code is deployed as well as after.

    conda run -n assy_manager python scripts/ledger_deploy_preflight.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
CONFIG = os.path.join(SERVER, "config")
ONTOLOGY = os.path.join(CONFIG, "ontology")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _database_url():
    env = os.environ.get("DATABASE_URL")
    if env:
        return env, "env DATABASE_URL"
    doc = _read_json(os.path.join(CONFIG, "database.json")) or {}
    if doc.get("url"):
        return doc["url"], "config/database.json"
    host = doc.get("host", "localhost")
    port = doc.get("port", 5432)
    name = doc.get("database", "assy_manager")
    user = doc.get("user", "postgres")
    pw = doc.get("password")
    auth = f"{user}:{pw}@" if pw else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{name}", "config/database.json (분리 필드)"


def inspect_config():
    """Which of the three shapes is this box's ledger setup in?"""
    legacy = os.path.join(CONFIG, "ledger_config.json")
    has_legacy = os.path.exists(legacy)
    has_root = os.path.isdir(ONTOLOGY)
    jsons = []
    if has_root:
        for base, _dirs, files in os.walk(ONTOLOGY):
            for name in files:
                if name.endswith(".json"):
                    jsons.append(os.path.relpath(os.path.join(base, name), ONTOLOGY)
                                 .replace("\\", "/"))
    jsons.sort()
    single = jsons == ["ledger_config.json"]
    return {
        "legacy_config_present": has_legacy,
        "legacy_sources": sorted((_read_json(legacy) or {}).get("sources", {}))
                          if has_legacy else [],
        "ontology_root_present": has_root,
        "ontology_json_files": jsons,
        "is_single_file": single,
    }


def inspect_database():
    try:
        import psycopg2
    except ImportError:
        return {"error": "psycopg2 미설치 - DB 확인 생략"}
    url, source = _database_url()
    shown = url.split("@")[-1] if "@" in url else url
    out = {"target": shown, "url_source": source}
    try:
        conn = psycopg2.connect(url)
    except Exception as exc:                                  # noqa: BLE001
        out["error"] = f"접속 실패: {type(exc).__name__}"
        return out
    try:
        cur = conn.cursor()
        cur.execute("SET statement_timeout='20s'")
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'")
        tables = {r[0] for r in cur.fetchall()}
        out["table_count"] = len(tables)
        out["has_ledger_events"] = "ledger_events" in tables
        if "ledger_translator_cursor" in tables:
            cur.execute("SELECT source, translator_ver FROM ledger_translator_cursor "
                        "ORDER BY source")
            rows = cur.fetchall()
            out["cursors"] = [
                {"source": s, "translator_ver": v,
                 "shape": "v2" if str(v).startswith("ledger-v2:") else "v1"}
                for s, v in rows]
        else:
            out["cursors"] = []
        if "file_ingestion_checkpoints" in tables:
            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' "
                        "AND table_name='file_ingestion_checkpoints' "
                        "AND column_name IN ('file_mtime','file_size')")
            out["ingestion_path_stat_columns"] = sorted(r[0] for r in cur.fetchall())
        else:
            out["ingestion_path_stat_columns"] = None
    finally:
        conn.close()
    return out


def verdict(cfg, db):
    lines = []
    if cfg["ontology_root_present"] and not cfg["is_single_file"]:
        lines.append(
            "🔴 경우 B — v2 설정이 «옛 여러 파일» 모양입니다: "
            f"{cfg['ontology_json_files']}\n"
            "     배포하면 config 로드가 unlisted_config_file 로 거절됩니다.\n"
            "     배포와 같은 시점에 변환기를 돌리고, 옛 파일은 config root «밖»으로 옮기십시오:\n"
            "       python scripts/convert_ontology_to_single_file.py "
            "--root <root> --out <새 파일>")
    elif cfg["is_single_file"]:
        lines.append("🟢 v2 설정이 이미 단일 파일입니다. config 쪽은 배포로 멈추지 않습니다.")
    elif cfg["legacy_config_present"]:
        lines.append(
            "🔴 경우 A — v2 설정이 없고 legacy 선언만 있습니다: "
            f"sources={cfg['legacy_sources']}\n"
            "     legacy 실행 경로는 제거됐으므로 배포하면 그 소스들의 원장 적재가 멈춥니다.\n"
            "     배포 전에 v2 셋업을 세우고 등가를 확인하십시오.")
    else:
        lines.append(
            "🟢 경우 C — 원장 설정이 아예 없습니다. 배포로 멈출 것이 없고, "
            "셋업을 처음부터 세우면 됩니다.")

    v1 = [c for c in db.get("cursors") or [] if c["shape"] == "v1"]
    if v1:
        lines.append(
            "🟠 v1 모양 커서가 있습니다: "
            + ", ".join(c["source"] for c in v1) + "\n"
            "     해당 소스의 v2 백필은 legacy_cursor_reset_required 로 거절됩니다(의도된 안전장치).\n"
            "     전환 판정 전까지 백필을 돌리지 마십시오. 시연은 «다른 source_id»로 선언하면 "
            "커서 없이 바로 됩니다.")
    elif db.get("cursors") is not None and not db.get("error"):
        lines.append("🟢 v1 모양 커서가 없습니다.")

    cols = db.get("ingestion_path_stat_columns")
    if cols is None:
        lines.append("⚪ file_ingestion_checkpoints 표가 없습니다(파일 인제션 미사용?).")
    elif sorted(cols) != ["file_mtime", "file_size"]:
        lines.append(
            "🔴 file_ingestion_checkpoints 에 file_mtime/file_size 가 없습니다"
            f"(있는 것: {cols or '없음'}).\n"
            "     지금 체크포인트가 꺼진 채 «매 스윕마다 전량 재적재» 중입니다. 원장과 무관하게 급합니다:\n"
            "       server/migrations/add_ingestion_ledger_path_stat.sql")
    else:
        lines.append("🟢 파일 인제션 원장 컬럼이 있습니다.")
    return lines


def main() -> int:
    cfg = inspect_config()
    db = inspect_database()
    print("=" * 72)
    print("Ledger v2 배포 전 점검 — 읽기만 합니다")
    print("=" * 72)
    print(f"config root      : {ONTOLOGY}")
    print(f"  v2 json 파일   : {cfg['ontology_json_files'] or '없음'}")
    print(f"  legacy 선언    : {'있음 ' + str(cfg['legacy_sources']) if cfg['legacy_config_present'] else '없음'}")
    print(f"database         : {db.get('target', '-')}  ({db.get('url_source', '-')})")
    if db.get("error"):
        print(f"  ⚠️ {db['error']}")
    else:
        print(f"  표 {db.get('table_count', '?')}개 · ledger_events "
              f"{'있음' if db.get('has_ledger_events') else '없음'}")
        for c in db.get("cursors") or []:
            print(f"  커서 {c['source']:24s} {c['shape']:3s} {c['translator_ver']}")
    print()
    for line in verdict(cfg, db):
        print(line)
    print()
    print("이 점검은 아무것도 쓰지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
