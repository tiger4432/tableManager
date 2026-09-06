# -*- coding: utf-8 -*-
"""목록 라우트 «넷»이 「없다」와 「빔」을 가르는가, 그리고 «한 자리»에서 그러는가.

🔴 이 파일의 값은 마지막 시험에 있다 — 그 «한 자리»의 나르기를 지우면 «여럿»이 표지를
잃어야 한다. 하나만 잃으면 그건 한 자리가 아니라 사본이 넷인 것이다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main                                                   # noqa: E402
from listing_absence import LISTING_ABSENT, absent_listing     # noqa: E402


#: (부르는 것, 못 찾았을 때 이름 대야 할 경로의 «조각»)
#: 🔴 경로 «전문»을 안 적는다 — 이 상자의 절대경로가 되어 다른 설치에서 거짓이 된다.
LISTINGS = [
    (main.get_ingestion_workspaces, "workspace"),
    (main.get_chain_rules, "chain_rules.json"),
    (main.get_mappers, "mappers"),
]


@pytest.fixture
def nothing_exists(monkeypatch):
    """어떤 경로도 없다 — 라우트들의 «부재 갈래»를 태운다."""
    monkeypatch.setattr(os.path, "exists", lambda _p: False)


@pytest.mark.parametrize("call,fragment", LISTINGS)
def test_an_absent_listing_says_it_is_absent_and_names_the_path(
        call, fragment, nothing_exists):
    body = call()

    assert body["data"] == [], "부재 갈래는 목록을 «비워» 두는 것이 맞다"
    assert body["state"] == LISTING_ABSENT, (
        "「없다」가 「빔」과 «같은 답»으로 나가고 있다")
    assert fragment in body["absent_path"], (
        "무엇이 없는지 «이름»을 대야 한다: %r" % (body.get("absent_path"),))


@pytest.mark.parametrize("call,_fragment", LISTINGS)
def test_the_status_field_does_not_move(call, _fragment, nothing_exists):
    """🔴 무회귀. `data` 만 읽는 독자가 «전과 똑같이» 돌아야 한다."""
    assert call()["status"] == "success", (
        "`status` 를 바꾸면 이 답을 읽는 «모든» 화면이 같이 움직인다 — 이번엔 «더하기»만 한다")


def test_a_present_source_is_not_called_absent(monkeypatch):
    """있을 때는 «오늘과 동일» — 부재 표지가 «안 붙는다»."""
    monkeypatch.setattr(os.path, "exists", lambda _p: True)
    monkeypatch.setattr(os, "listdir", lambda _p: [])

    body = main.get_ingestion_workspaces()

    assert body.get("state") != LISTING_ABSENT, (
        "있는데 «없다»고 말하면 이 수리가 새 거짓을 심은 것이다")


def test_the_async_listing_is_covered_too(nothing_exists):
    """넷째 자리는 «비동기»라 위 목록에 못 들어간다 — 그래서 여기서 따로 태운다.

    🔴 빼 두면 「셋을 쟀다」가 「넷을 쟀다」로 읽힌다.
    """
    import asyncio

    body = asyncio.run(main.get_auto_update_status())

    assert body["state"] == LISTING_ABSENT
    assert "scheduler_status.json" in body["absent_path"]
    assert body["last_updated"] is None, "그 라우트의 계약은 «그대로» 있어야 한다"
    assert body["status"] == "success", "무회귀 — `status` 는 안 움직인다"


def test_the_route_with_its_own_field_keeps_it_and_the_others_do_not():
    """갈라진 필드의 판정: `last_updated` 는 «그 라우트의» 것이라 «호출자가» 얹는다.

    공용 모양이 넷 다 실으면 나머지 셋에 뜻 없는 칸이 생기고, 아무도 안 실으면 그
    라우트가 자기 계약을 잃는다.
    """
    assert absent_listing("/nowhere", last_updated=None)["last_updated"] is None
    assert "last_updated" not in absent_listing("/nowhere")


def test_removing_the_carrying_from_the_one_place_costs_more_than_one_route(
        monkeypatch, nothing_exists):
    """🔴 «한 자리»인가를 재는 시험.

    네 호출부가 «공유하는 그 이름»을 나르기 없는 판으로 갈아 끼우고, 표지를 잃는
    라우트를 «센다». 사본이 넷이었다면 이 교체로 잃는 라우트가 «0» 이다.

    ⚠️ 변이를 «파일에» 안 넣는다 — 공유 트리에서 되돌릴 편집은 복원이 도달 못 할 수
    있다(2026-09-07 실측). monkeypatch 가 그 창을 이 시험 안으로 닫는다.
    """
    monkeypatch.setattr(main, "absent_listing",
                        lambda path, **extra: {"status": "success", "data": [], **extra})

    lost = [call.__name__ for call, _ in LISTINGS
            if "state" not in call()]

    assert len(lost) >= 2, (
        "나르기를 지웠는데 표지를 잃은 라우트가 %d 개다 — 한 자리가 아니라 사본이라는 뜻이다: %r"
        % (len(lost), lost))
