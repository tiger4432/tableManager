"""[Warmup] 체인 워커 콜드 스타트 웜업 검증.

warmup_worker 가:
  - 활성 규칙의 mapper_module 을 선(先)import 해 sys.modules 캐시를 덥히는지(비활성 규칙 제외),
  - 존재하지 않는 모듈이어도 예외를 올리지 않고 계속 진행하는지(웜업 실패는 치명 아님),
  - db_session_factory 가 주어지면 세션 1개로 SELECT 1 프라임 후 close 하는지,
  - db_session_factory=None(리로드 경로)이면 DB 를 건드리지 않는지
를 확인한다. 실 Postgres/psycopg2 불필요(FakeDB).
"""
import sys

import chain_ingestion_worker as ciw


DUMMY_MODULE = "warmup_dummy_mapper_mod"


def _write_dummy_module(tmp_path):
    (tmp_path / f"{DUMMY_MODULE}.py").write_text("VALUE = 42\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))


def _cleanup_dummy_module(tmp_path):
    sys.modules.pop(DUMMY_MODULE, None)
    try:
        sys.path.remove(str(tmp_path))
    except ValueError:
        pass


class FakeDB:
    def __init__(self):
        self.executed = []
        self.closed = False

    def execute(self, stmt):
        self.executed.append(str(stmt))

    def close(self):
        self.closed = True


def test_warmup_preimports_enabled_mapper_modules(tmp_path):
    """활성 규칙의 매퍼 모듈이 sys.modules 에 선재(캐시 웜)되어야 한다."""
    _write_dummy_module(tmp_path)
    try:
        assert DUMMY_MODULE not in sys.modules
        rules = [{"name": "r1", "mapper_module": DUMMY_MODULE, "enabled": True}]
        ciw.warmup_worker(rules)
        assert DUMMY_MODULE in sys.modules
    finally:
        _cleanup_dummy_module(tmp_path)


def test_warmup_skips_disabled_rules(tmp_path):
    """enabled=False 규칙의 매퍼는 import 하지 않는다."""
    _write_dummy_module(tmp_path)
    try:
        rules = [{"name": "r1", "mapper_module": DUMMY_MODULE, "enabled": False}]
        ciw.warmup_worker(rules)
        assert DUMMY_MODULE not in sys.modules
    finally:
        _cleanup_dummy_module(tmp_path)


def test_warmup_tolerates_missing_module_and_bad_rule():
    """존재하지 않는 모듈/mapper_module 없는 규칙이 섞여도 예외 없이 완료한다(치명 아님)."""
    rules = [
        {"name": "broken", "mapper_module": "no_such_module_xyz_123", "enabled": True},
        {"name": "no_module_key", "enabled": True},
    ]
    ciw.warmup_worker(rules)  # 예외가 올라오면 테스트 실패


def test_warmup_primes_db_connection_when_factory_given():
    """기동 경로: 세션 1개 열어 가벼운 쿼리 1회 실행 후 반드시 close(풀 반납)."""
    db = FakeDB()
    ciw.warmup_worker([], db_session_factory=lambda: db)
    assert len(db.executed) == 1
    assert "SELECT 1" in db.executed[0]
    assert db.closed is True


def test_warmup_tolerates_db_prime_failure():
    """DB 프라임 실패(커넥션 불가 등)도 예외 없이 로깅 후 계속 기동한다(치명 아님)."""

    def broken_factory():
        raise RuntimeError("db down")

    ciw.warmup_worker([], db_session_factory=broken_factory)  # 예외가 올라오면 테스트 실패
