# -*- coding: utf-8 -*-
"""기본 DB URL 이 «다섯 벌»로 적혀 있었다 — 그리고 한 사본은 자기 주석으로 «약속»을 했다.

```
정본        `paths.DEFAULT_PG_URL` (해석기 `resolve_database_url` «바로 옆»)
사본 다섯   scratch 마이그레이션 · dev_env manifest · dev_env snapshot ·
           diagnose_slow_after_ingest · diagnose_wal_headroom
오늘 넷     🪦 [2026-09-13, S-210 판정 353] scratch 사본은 «파일째» 사라졌다 —
           `server/scratch/` 가 삭제됐고, 이 게이트의 나르개도 다섯에서 넷이 됐다.
           둘째 사본을 «묶어 두는 것»보다 «없애는 것»이 낫다는 판정이고, 그래서 아래
           CARRIERS 에서 그 행이 빠졌다. 아래 본문의 scratch 서술은 «그때 있었던 일»이다
```
🔴 `diagnose_slow_after_ingest` 의 주석은 「이 스크립트와 서버가 «다른 데이터베이스»를 볼 수
없다」고 적어 두었는데, 값이 «사본»이라 정본이 바뀌는 날 그 문장이 조용히 거짓이 된다.
그리고 scratch 사본은 «순서»까지 달랐다 — `env > 기본값` 만 따르고 «`database.json` 을 건너뛰어»,
설정 파일로 DB 를 옮긴 설치에서 «다른 DB» 를 고쳤을 것이다.

⛔ `assy_qa` 를 가리키는 자리들은 «다른 데이터베이스»라 접지 않는다 — 값이 같아 보이는 것과
같은 사실인 것은 다르다.
"""
import importlib
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                     # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
#: 🔴 게이트가 그 문자열을 «자기 손으로» 적지 않는다. 두 가지가 걸려 있다:
#:  ① 이 파일도 «추적 모집단» 안이라, 적으면 게이트가 «자기 자신»을 사본으로 센다
#:     (커밋 «전»에 돌리면 미추적이라 안 보이고, 커밋한 순간 빨개진다 —
#:      「스테이지된 것이 담긴 것은 아니다」의 «게이트 판»이고 제가 그 구멍에 빠졌다)
#:  ② 집의 «값»이 바뀌는 날, 손으로 적은 게이트는 «옛 값»을 찾아 조용히 초록이 된다
LITERAL = paths.DEFAULT_PG_URL


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


#: 🔴 [판정 89] 글자 조사(위)는 «사본이 돌아오는 것»을 잡는다. 그것이 못 잡는 것이
#: «부르기만 하고 배선이 없는 것»이다 — 나르개가 리터럴을 «안 들고» 이름을 «부르니»
#: 위의 단언은 초록인데 그 파일은 import 에서 죽는다. 그래서 «행동»을 나란히 잰다.
CARRIERS = [
    ("scripts.dev_env.manifest",           "server/scripts/dev_env/manifest.py"),
    ("scripts.dev_env.snapshot_db",        "server/scripts/dev_env/snapshot_db.py"),
    ("scripts.diagnose_slow_after_ingest", "server/scripts/diagnose_slow_after_ingest.py"),
    ("scripts.diagnose_wal_headroom",      "server/scripts/diagnose_wal_headroom.py"),
]

#: `__main__` 으로 «돌리지 않는다» — 나르개 중에는 argparse 없이 곧장 ALTER TABLE 을 치는 것이
#: 있었다(삭제된 scratch 사본이 그랬다). `sys.path[0]` 을 스크립트 자기 디렉터리로 바꾸는 것이
#: `python <script>` 와 같은 조건이다.
_START = ("import runpy, sys; sys.path[0] = sys.argv[1]; "
          "runpy.run_path(sys.argv[2], run_name='__not_main__')")


def _clean_env():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


@pytest.mark.parametrize("dotted,rel", CARRIERS, ids=[c[0] for c in CARRIERS])
def test_every_carrier_imports(dotted, rel):
    """정본을 «부르는» 파일은 import 가 된다 — 이름을 부르는데 안 실은 것이 있으면 여기서 죽는다."""
    importlib.import_module(dotted)


@pytest.mark.parametrize("dotted,rel", CARRIERS, ids=[c[0] for c in CARRIERS])
def test_every_carrier_starts_as_a_script(dotted, rel):
    """🔴 위 단언과 «다른 성질»이다. 위는 「server 가 sys.path 에 있을 때」를 재고, 이것은
    운영자가 실제로 치는 `python <script>` 를 잰다.

    `manifest.py` 가 그 둘을 갈랐다 — `import paths` 가 sys.path 배선 «위»에 있어서
    pytest 에서는 초록, 스크립트로는 ModuleNotFoundError 였다. 하나만 걸었으면 못 봤다.
    """
    p = subprocess.run([sys.executable, "-c", _START,
                        os.path.dirname(os.path.join(ROOT, rel)),
                        os.path.join(ROOT, rel)],
                       cwd=ROOT, capture_output=True, text=True, env=_clean_env())
    assert p.returncode == 0, rel + "\n" + p.stderr[-2000:]
