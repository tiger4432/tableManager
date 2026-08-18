"""Read-only: does the watcher accept the external directories you declared?

An external source is refused one entry at a time, and the refusal lands in the watcher
log where it is easy to miss.  This runs the SAME validator the watcher runs
(`parsers.directory_watcher.validate_external_source_specs`) against the current
settings and says, per entry, accepted or refused and why -- without starting a watcher
and without touching the database or the files.

    conda run -n assy_manager python scripts/check_external_sources.py

Accepted here means the declaration is well-formed and the table is declared with a key.
It does not mean files have arrived; for that, look at the folder shape and the ledger
(`file_ingestion_checkpoints`).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
for path in (SERVER, os.path.join(SERVER, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> int:
    from parsers.directory_watcher import (
        load_global_table_config,
        load_ingestion_settings,
        validate_external_source_specs,
    )

    settings = load_ingestion_settings()
    declared = settings.get("external_sources") or []
    table_config = load_global_table_config()
    workspace = os.path.join(SERVER, "ingestion_workspace")

    print(f"선언된 external_sources : {len(declared)}개")
    print(f"table_config 선언 표     : {len(table_config)}개")
    print(f"관리 워크스페이스        : {workspace}")
    print()

    for index, raw in enumerate(declared):
        if not isinstance(raw, dict):
            print(f"  [{index}] (객체가 아님)")
            continue
        state = "enabled" if raw.get("enabled", True) else "disabled - 스윕 대상 아님"
        print(f"  [{index}] {raw.get('table_name')!r} ← {raw.get('path')!r}  ({state})")
        path = raw.get("path")
        if isinstance(path, str) and path.strip():
            expanded = os.path.expandvars(os.path.expanduser(path.strip()))
            print(f"        폴더 존재: {'예' if os.path.isdir(expanded) else '아니오'}")

    specs, errors = validate_external_source_specs(settings, table_config, workspace)

    print()
    print(f"=== 워처가 받아들인 것: {len(specs)}개 ===")
    for spec in specs:
        print(f"  ✔ {spec['table_name']:18s} {spec['root']}")
        print(f"      parser={spec['parser']}  recursive={spec['recursive']}  "
              f"options={spec['options']}")

    print()
    print(f"=== 거절된 것: {len(errors)}개 ===")
    for message in errors:
        print(f"  ✘ {message}")
    if not errors:
        print("  없음")

    print()
    if not specs and not errors:
        print("선언이 없거나 전부 disabled 입니다. enabled:true 로 두어야 스윕합니다.")
    elif errors:
        print("거절된 항목은 워처가 등록하지 않습니다 - 그 폴더는 감시되지 않습니다.")
    else:
        print("선언은 정상입니다. 반영은 /admin/reload-configs 로 하고, 기존 항목의 "
              "path/parser/options 를 바꾼 경우에는 프로세스 재기동이 필요합니다.")
    print("이 점검은 아무것도 쓰지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
