# -*- coding: utf-8 -*-
"""기본 DB URL 이 «다섯 벌»로 적혀 있었다 — 그리고 한 사본은 자기 주석으로 «약속»을 했다.

```
정본        `paths.DEFAULT_PG_URL` (해석기 `resolve_database_url` «바로 옆»)
사본 다섯   scratch 마이그레이션 · dev_env manifest · dev_env snapshot ·
           diagnose_slow_after_ingest · diagnose_wal_headroom
```
🔴 `diagnose_slow_after_ingest` 의 주석은 「이 스크립트와 서버가 «다른 데이터베이스»를 볼 수
없다」고 적어 두었는데, 값이 «사본»이라 정본이 바뀌는 날 그 문장이 조용히 거짓이 된다.
그리고 scratch 사본은 «순서»까지 달랐다 — `env > 기본값` 만 따르고 «`database.json` 을 건너뛰어»,
설정 파일로 DB 를 옮긴 설치에서 «다른 DB» 를 고쳤을 것이다.

⛔ `assy_qa` 를 가리키는 자리들은 «다른 데이터베이스»라 접지 않는다 — 값이 같아 보이는 것과
같은 사실인 것은 다르다.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                     # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LITERAL = "postgresql://postgres:admin@localhost:5432/assy_manager"


def _tracked_python():
    out = subprocess.run(["git", "ls-files", "server"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p.endswith(".py")]


def test_only_the_home_and_its_own_test_spell_the_default():
    """🔴 사본이 돌아오면 여기서 말한다 — 다음 스크립트가 그 줄을 손으로 적는 날."""
    carriers = []
    for rel in _tracked_python():
        try:
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        except OSError:
            continue
        if LITERAL in src:
            carriers.append(rel.replace("\\", "/"))
    assert sorted(carriers) == ["server/paths.py",
                                "server/tests/test_database_url_config.py"], carriers


def test_the_home_is_beside_the_resolver():
    """값과 «순서»가 한 자리에서 읽혀야 한다 — scratch 사본이 어긋난 것이 순서였다."""
    assert paths.DEFAULT_PG_URL == LITERAL
    assert hasattr(paths, "resolve_database_url")


def test_the_old_import_still_works():
    """⚠️ 집을 옮기면서 «부르던 이름»을 깨지 않았다 — `main` 이 그 이름으로 부른다."""
    from database.database import DEFAULT_PG_URL
    assert DEFAULT_PG_URL is paths.DEFAULT_PG_URL


def test_the_home_module_creates_no_engine():
    """⛔ 진단 스크립트가 «부작용 없이» 부를 수 있어야 한다 — 그래서 값이 `database` 가
    아니라 `paths` 에 산다."""
    src = open(os.path.join(ROOT, "server", "paths.py"), encoding="utf-8").read()
    assert "create_engine" not in src
    assert not re.search(r"^\s*import sqlalchemy", src, re.M)
