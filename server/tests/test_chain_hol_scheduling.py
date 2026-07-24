"""[Latency Fix #5] 실패 그룹 head-of-line 블로킹 제거 + 순서 보존 가드 검증.

process_pending_groups 가 한 배치 안에서:
  - 실패 그룹을 만나도 배치를 중단(break)하지 않고 뒤의 서로 다른 target 그룹을 계속 처리하는지,
  - 실패 그룹과 동일 target_table 을 건드리는 후속 그룹만 보류(순서 보존)하는지,
  - 실패 그룹은 커밋되지 않고(processed_chain=False) 재시도 카운트만 증가하는지
를 확인한다.
"""
import pytest
import chain_ingestion_worker as ciw


class FakeEvent:
    def __init__(self, event_uuid, table_name, tx_id, event_type="CREATE", source_name="user"):
        self.event_uuid = event_uuid
        self.table_name = table_name
        self.event_type = event_type
        self.retry_count = 0
        self.status = "PENDING"
        self.processed_chain = False
        payload = {"transaction_id": tx_id, "source_name": source_name}
        self.payload = payload
        self._parsed_payload = payload


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


# 규칙: 트리거 tblA_src -> target table_A, 트리거 tblB_src -> target table_B
RULES = [
    {"name": "rA", "trigger_table": "tblA_src", "target_table": "table_A", "enabled": True},
    {"name": "rB", "trigger_table": "tblB_src", "target_table": "table_B", "enabled": True},
]


def _make_groups(spec):
    """spec: list[(tx_id, trigger_table)] -> (group_order, groups dict)."""
    group_order = []
    groups = {}
    for i, (tx_id, trig) in enumerate(spec):
        ev = FakeEvent(f"uuid_{i}", trig, tx_id)
        if tx_id not in groups:
            groups[tx_id] = []
            group_order.append(tx_id)
        groups[tx_id].append(ev)
    return group_order, groups


def _patch_processor(monkeypatch, failing_tx_ids):
    """process_chain_transaction_group 를 대체하여 지정 tx만 실패로 만들고 호출 tx를 기록한다."""
    called = []

    async def fake_process(tx_id, events, db, rules):
        called.append(tx_id)
        if tx_id in failing_tx_ids:
            return False, f"boom:{tx_id}", []
        return True, None, []

    monkeypatch.setattr(ciw, "process_chain_transaction_group", fake_process)
    return called


@pytest.mark.anyio
async def test_failed_head_does_not_block_different_target(monkeypatch):
    """선두 실패 그룹(target_A) 뒤의 정상 그룹(target_B)이 같은 배치에서 처리되어야 한다."""
    group_order, groups = _make_groups([("txF", "tblA_src"), ("txN", "tblB_src")])
    called = _patch_processor(monkeypatch, failing_tx_ids={"txF"})
    db = FakeDB()

    failed_any = await ciw.process_pending_groups(db, group_order, groups, RULES)

    assert failed_any is True
    # 두 그룹 모두 시도되었다(break 없음).
    assert called == ["txF", "txN"]
    # 정상 그룹은 커밋 처리(성공).
    assert groups["txN"][0].processed_chain is True
    assert groups["txN"][0].status == "SUCCESS"
    # 실패 그룹은 미커밋 상태로 남고 retry 카운트만 증가.
    assert groups["txF"][0].processed_chain is False
    assert groups["txF"][0].retry_count == 1
    assert groups["txF"][0].status == "RETRYING"
    assert db.rollbacks == 1  # 실패 그룹만 rollback


@pytest.mark.anyio
async def test_failed_group_defers_same_target_follower(monkeypatch):
    """선두 실패 그룹(target_A) 뒤의 동일 target(target_A) 그룹은 순서 보존을 위해 보류되어야 한다."""
    group_order, groups = _make_groups([("txF", "tblA_src"), ("txSame", "tblA_src")])
    called = _patch_processor(monkeypatch, failing_tx_ids={"txF"})
    db = FakeDB()

    failed_any = await ciw.process_pending_groups(db, group_order, groups, RULES)

    assert failed_any is True
    # 동일 target 후속 그룹은 시도되지 않고 보류된다.
    assert called == ["txF"]
    assert "txSame" not in called
    # 보류 그룹은 미처리·retry 미증가로 다음 배치에서 blocker 뒤에 재시도된다.
    assert groups["txSame"][0].processed_chain is False
    assert groups["txSame"][0].retry_count == 0
    assert groups["txSame"][0].status == "PENDING"


@pytest.mark.anyio
async def test_same_target_blocked_but_other_target_proceeds(monkeypatch):
    """실패(A) → 동일 target(A, 보류) → 다른 target(B, 처리)의 혼합 순서 검증."""
    group_order, groups = _make_groups([
        ("txF", "tblA_src"),
        ("txSame", "tblA_src"),
        ("txOther", "tblB_src"),
    ])
    called = _patch_processor(monkeypatch, failing_tx_ids={"txF"})
    db = FakeDB()

    failed_any = await ciw.process_pending_groups(db, group_order, groups, RULES)

    assert failed_any is True
    assert called == ["txF", "txOther"]  # txSame 보류, txOther 처리
    assert groups["txOther"][0].processed_chain is True
    assert groups["txSame"][0].processed_chain is False


def test_group_target_tables_derivation():
    """_group_target_tables: 규칙 기반 target 추정 + 순환/이벤트타입 필터."""
    # CREATE(user) trigger tblA_src -> {table_A}
    e_user = FakeEvent("u1", "tblA_src", "tx1", event_type="CREATE", source_name="user")
    assert ciw._group_target_tables([e_user], RULES) == {"table_A"}

    # chain_ingestion 소스는 제외 → no-op
    e_chain = FakeEvent("u2", "tblA_src", "tx2", event_type="CREATE", source_name="chain_ingestion")
    assert ciw._group_target_tables([e_chain], RULES) == set()

    # DELETE 이벤트는 트리거 대상이 아님(CREATE/EDIT만)
    e_del = FakeEvent("u3", "tblA_src", "tx3", event_type="DELETE", source_name="user")
    assert ciw._group_target_tables([e_del], RULES) == set()

    # 규칙 없는 트리거 테이블 → 빈 집합
    e_norule = FakeEvent("u4", "unknown_src", "tx4", event_type="CREATE", source_name="user")
    assert ciw._group_target_tables([e_norule], RULES) == set()
