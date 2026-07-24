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
        self.id = event_uuid  # [Reliability F1] 통지 누적 시 event id 캡처 대상(실 DB에선 정수 PK).
        self.event_uuid = event_uuid
        self.table_name = table_name
        self.event_type = event_type
        self.retry_count = 0
        self.status = "PENDING"
        self.processed_chain = False
        self.broadcast_at = None  # [Reliability F1] 전달 확정 스탬프 필드.
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

    failed_any = await ciw.process_pending_groups(db, group_order, groups, RULES, lambda: FakeDB())

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

    failed_any = await ciw.process_pending_groups(db, group_order, groups, RULES, lambda: FakeDB())

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

    failed_any = await ciw.process_pending_groups(db, group_order, groups, RULES, lambda: FakeDB())

    assert failed_any is True
    assert called == ["txF", "txOther"]  # txSame 보류, txOther 처리
    assert groups["txOther"][0].processed_chain is True
    assert groups["txSame"][0].processed_chain is False


def _patch_processor_with_messages(monkeypatch, messages_by_tx, failing_tx_ids=None):
    """process_chain_transaction_group 를 대체하여 tx별 브로드캐스트 메시지를 반환하게 한다(실패 tx도 지정 가능)."""
    failing_tx_ids = failing_tx_ids or set()
    called = []

    async def fake_process(tx_id, events, db, rules):
        called.append(tx_id)
        if tx_id in failing_tx_ids:
            return False, f"boom:{tx_id}", []
        return True, None, list(messages_by_tx.get(tx_id, []))

    monkeypatch.setattr(ciw, "process_chain_transaction_group", fake_process)
    return called


def _patch_dispatch_capture(monkeypatch):
    """_dispatch_broadcasts 를 대체하여 인라인 발사 시점에 누적된 pending 목록을 캡처한다."""
    captured = {}

    async def fake_dispatch(pending, factory):
        captured["pending"] = pending

    monkeypatch.setattr(ciw, "_dispatch_broadcasts", fake_dispatch)
    return captured


@pytest.mark.anyio
async def test_broadcasts_dispatched_once_in_group_order(monkeypatch):
    """[Reliability F2] 성공 그룹 통지가 그룹마다 독립 발사되지 않고 group_order 순서로 단일 발사에 누적된다."""
    group_order, groups = _make_groups([("tx1", "tblA_src"), ("tx2", "tblA_src")])
    msgs = {
        "tx1": [{"event": "batch_row_upsert", "table_name": "table_A", "items": [1]}],
        "tx2": [{"event": "batch_row_upsert", "table_name": "table_A", "items": [2]}],
    }
    _patch_processor_with_messages(monkeypatch, msgs)
    captured = _patch_dispatch_capture(monkeypatch)

    db = FakeDB()
    await ciw.process_pending_groups(db, group_order, groups, RULES, lambda: FakeDB())

    pending = captured["pending"]
    # 단일 발사에 두 그룹이 group_order 순서로 누적(그룹마다 독립 태스크 발사 아님 → 도착 역전 방지).
    assert [ids for ids, _, _ in pending] == [
        [e.id for e in groups["tx1"]],
        [e.id for e in groups["tx2"]],
    ]
    assert [m for _, m, _ in pending] == [msgs["tx1"], msgs["tx2"]]
    # [Latency SLO] 각 그룹에 계측 timing 이 채워진다(tx 라벨 + 구간 ms).
    for _, _, timing in pending:
        assert timing["tx"] in ("tx1", "tx2")
        assert "mapper_ms" in timing and "commit_ms" in timing and "commit_done_ts" in timing


@pytest.mark.anyio
async def test_noop_group_stamped_and_message_group_deferred(monkeypatch):
    """[Reliability F1] 통지 없는 no-op 성공 그룹은 즉시 broadcast_at 확정(스윕 제외),
    통지 있는 그룹은 커밋 시 미확정(NULL) 유지 + 발사 누적(통지 성공 시에만 스탬프)."""
    group_order, groups = _make_groups([("txNoop", "tblA_src"), ("txMsg", "tblB_src")])
    msgs = {"txMsg": [{"event": "batch_row_upsert", "table_name": "table_B", "items": [1]}]}
    _patch_processor_with_messages(monkeypatch, msgs)
    captured = _patch_dispatch_capture(monkeypatch)

    db = FakeDB()
    await ciw.process_pending_groups(db, group_order, groups, RULES, lambda: FakeDB())

    # no-op 그룹: 전달할 것이 없으므로 즉시 확정(broadcast_at 설정됨) → 스윕 대상 아님.
    assert groups["txNoop"][0].broadcast_at is not None
    # 통지 그룹: 커밋 시 broadcast_at 미설정(NULL 유지) → 통지 성공 시 _dispatch_broadcasts 가 스탬프.
    assert groups["txMsg"][0].broadcast_at is None
    # 발사 누적엔 통지 그룹만 포함.
    assert [ids for ids, _, _ in captured["pending"]] == [[e.id for e in groups["txMsg"]]]


@pytest.mark.anyio
async def test_broadcasts_fired_inline_before_return(monkeypatch):
    """[Latency SLO 기아 회귀 방지] 통지가 배경 태스크 예약이 아니라 process_pending_groups 반환 **이전에**
    인라인으로 POST·스탬프까지 완료되어야 한다(이벤트 루프 블로킹에 의한 통지 기아 재발 방지)."""
    group_order, groups = _make_groups([("tx1", "tblA_src")])
    msgs = {"tx1": [{"event": "batch_row_upsert", "table_name": "table_A", "items": [1]}]}
    _patch_processor_with_messages(monkeypatch, msgs)

    posted = []

    async def fake_post(endpoint, payload):
        posted.append((endpoint, payload))
        return True

    monkeypatch.setattr(ciw, "post_event_async", fake_post)

    stamped = []
    monkeypatch.setattr(ciw, "_stamp_broadcast_at_sync",
                        lambda factory, ids: stamped.append(list(ids)))

    db = FakeDB()
    await ciw.process_pending_groups(db, group_order, groups, RULES, lambda: FakeDB())

    # 반환 시점에 이미 POST 완료(create_task 예약이었다면 아직 실행 전이라 posted 가 비어 있다).
    assert posted == [("/internal/events/broadcast", msgs["tx1"][0])]
    # 전달 확정 스탬프도 인라인 경로에서 완료.
    assert stamped == [[e.id for e in groups["tx1"]]]


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
