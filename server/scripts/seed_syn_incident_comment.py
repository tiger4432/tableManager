# -*- coding: utf-8 -*-
"""Seed synthetic tool events (incident + PM) and lot/wafer comments -- the first data of
either kind.

WHY THIS EXISTS.  The R&D screen's candidate kinds grew to five and two of them had **no
data at all**.  Measured 2026-08-23 against `ledger_events`: the eleven predicates that
carry atoms are `observed`, `transferred`, `processed_with`, `register`, `has_wafer`,
`transfer`, `slot_map`, `has_netdie`, `measured`, `derived_from`, `has_param`.  Incident
history is in none of them and in no source table, and neither are comments
(`file_ingestion_checkpoints.note` is for ingestion, `audit_logs` is a system log; neither
is a process fact).  The owner asked for synthetic data so the screen has something to
walk into.

🔴 THE FIRST REQUIREMENT: THIS MUST NOT BECOME AN ISLAND.
The die-transfer fixture of 2026-08-22 landed 1,405 atoms nobody could reach, for exactly
one reason -- its names (`SYN-XFER-*`) shared not one character with a registered entity.
So every name below is one this database ALREADY holds, and this script does not take that
on trust: `verify_names` counts each one in `ledger_events` and REFUSES the run if any
count is zero.  A name that looks right and is absent is precisely how the island happened,
so absence has to stop the run rather than produce a row.

🔴 THE INTERVALS ARE FITTED TO REAL RUNS, NOT INVENTED.
An event here carries a SPAN (`started_at` .. `ended_at`) rather than an instant, because
overlap with a wafer's step time is the only question either sort is asked, and an instant
overlaps nothing.  The two sorts earn their span in opposite ways, and both are checked:

    incident   its interval must CONTAIN at least one real run on that equipment (and on
               that chamber when the incident is chamber-scoped).  An incident overlapping
               nothing is a row no walk can ever reach.

    pm         its window must sit in a GAP: no run inside it, and real runs on BOTH
               sides.  This is the owner's question -- 「설비 PM 이전/이후 차이도 걷기로
               추적되나」 -- and a PM with wafers on only one side compares nothing, so it
               is refused rather than written.

THE RUN DISTRIBUTION THOSE WINDOWS ARE PLACED AGAINST (read 2026-08-23, read-only, from
`processed_with.occurred_at` grouped by `object_payload->>'eqp'`):

    SYN-BD-01..04, SYN-BD-EXC   120 distinct times in TWO clusters
                                2026-08-10 01:00..01:59  and  2026-08-12 01:00..01:59
                                -> one 47.0 h gap between them
    SYN-MLD-01..04              120 distinct times in TWO clusters
                                2026-08-10 02:00..02:59  and  2026-08-12 02:00..02:59
                                -> one 47.0 h gap between them
    SYN-PC-01..03               2 times, 2026-08-09 00:20 and 01:05 -> one 0.8 h gap
    SYN-FE-01..08               15-16 times on 2026-08-07 in 5 clusters -> four ~1.2 h gaps
    SYN-DIF-01, SYN-DTQ-*       one cluster only -- NO gap, so no PM can be placed there
    SYN-STK-A/B, SYN-MI-01/02   a single instant each -- no gap either

Every PM below sits in one of those measured gaps.  The 47 h bonding/molding gap is the
useful one: real wafers ran on 08-10 before it and on 08-12 after it, on the same tool, so
a before/after contrast across it is a comparison of two real populations.

🔴 THE WORKED EXAMPLE, AND WHAT THE DESIGN GOT WRONG ABOUT IT.
The R&D design uses this chain as its worked example:

    PLASMA_CLEAN · CH-B (unlike its peers) -> surface_oxidation -> wetting_deficit -> void 199

Two halves of that do not exist in the live data, measured before anything was written:

  * `SYN-BW-103-11` has **zero** `PLASMA_CLEAN` atoms, and **zero** atoms on `CH-B`.  Its
    four BONDING atoms are all `CH-A`:
        2026-08-10 01:00:00+09:00  SYN-BD-EXC  CH-A   (who=syn_eqp_log)
        2026-08-10 01:40:00+09:00  SYN-BD-04   CH-A   (who=syn_eqp_log)
        2026-08-12 01:00:00+09:00  SYN-BD-EXC  CH-A   (who=syn_recipe_book)
        2026-08-12 01:40:00+09:00  SYN-BD-04   CH-A   (who=syn_recipe_book)
  * `PLASMA_CLEAN` carries **no chamber at all** anywhere -- all 2,600 of its atoms are on
    `SYN-PC-01/02/03` with `chamber` absent.  So "PLASMA_CLEAN · CH-B" names a pair that is
    not in this database, on this wafer or any other.

The instruction was to fit the interval to a timestamp READ from an existing atom, and to
name both wafers if the named one has no such atom.  So:

    WORKED_EXAMPLE_INCIDENT  is fitted to `SYN-BW-103-11`'s OWN atom -- the one at
        2026-08-10 01:40:00+09:00 on SYN-BD-04 / CH-A -- and spans 01:20..02:10 around it.
        That is the wafer the design names, on the equipment and chamber it really used.

    WORKED_EXAMPLE_CHB       is the CH-B half the chain asks for, and since 103-11 has no
        CH-B atom it is fitted to the NEAREST wafer that does: `SYN-BW-103-09` at
        2026-08-10 01:38:00+09:00 on SYN-BD-04 / CH-B -- two minutes before 103-11's own
        pass.  Its span 01:30..01:50 also covers 103-01 (01:30), 103-05 (01:34),
        103-07 (01:36) and 103-15 (01:44), the other SYN-BW-103-* wafers that took CH-B.

DETERMINISM.  Every row is a declared constant below -- nothing is drawn, nothing is
random -- so the row totals are arithmetic and need no execution to state:
INCIDENTS 12 + PM 12 = 24 rows in `eqp_event`, and 24 rows in `entity_comment`.
Only `commented_at` is computed, and it is READ (the target's last atom + 30 minutes)
rather than invented.

IDEMPOTENCY.  Both tables declare a `business_key` (`event_uid`, `comment_uid`) and every
row is written with its own key as the batch business key, so `apply_batch_updates`
resolves a second run onto the SAME rows and updates them in place.  Running twice cannot
double the rows.

INDEX.  Unlike `dt_transfer_log`, these two did not arrive with a non-unique index and stay
that way.  The declaration path only ever builds a plain index on `business_key_val`, so
the unique one was built at creation time, before any row existed:

    python migrations/add_business_key_unique_index.py --apply --table eqp_event
    python migrations/add_business_key_unique_index.py --apply --table entity_comment

⚠️ NEVER pass `--drop-redundant` to that script: section 2 drags a 692 MB database-wide
index cleanup along with it, which is a separate decision.

WRITES NOTHING WITHOUT --apply, same contract as `seed_syn_die_transfer`.  This script only
ever ADDS or UPDATES its own 48 rows; it has no delete path at all.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

EVENT_TABLE = "eqp_event"
COMMENT_TABLE = "entity_comment"

SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_syn_incident_comment"

CHUNK = 1000

KST = timezone(timedelta(hours=9))


def _t(year, month, day, hour, minute):
    """A wall clock in KST.  The live atoms are stored `+09:00`, so this matches them."""
    return datetime(year, month, day, hour, minute, tzinfo=KST)


#: --- INCIDENTS -------------------------------------------------------------------------
#: `chamber` None means the incident is tool-wide.  Every interval below was placed inside
#: a measured run cluster; `verify_events` re-measures that at run time and refuses if an
#: interval covers no run, so this table cannot silently drift into decoration.
INCIDENTS = (
    # 🔴 THE WORKED EXAMPLE.  Fitted to SYN-BW-103-11's own BONDING atom at
    #    2026-08-10 01:40:00+09:00 on SYN-BD-04 / CH-A -- read, not invented.
    ("SYN-EVT-I01", "SYN-BD-04", "CH-A", _t(2026, 8, 10, 1, 20), _t(2026, 8, 10, 2, 10),
     "MAJOR", "본딩 헤드 가압 불안정 — 상한 초과 3회", "김선호"),
    # 🔴 The CH-B half of the design's chain, fitted to the NEAREST wafer that has a CH-B
    #    atom: SYN-BW-103-09 at 2026-08-10 01:38:00+09:00.
    ("SYN-EVT-I02", "SYN-BD-04", "CH-B", _t(2026, 8, 10, 1, 30), _t(2026, 8, 10, 1, 50),
     "CRITICAL", "CH-B 진공도 저하 — 또래 챔버 대비 이상", "김선호"),
    ("SYN-EVT-I03", "SYN-BD-01", "CH-A", _t(2026, 8, 12, 1, 5), _t(2026, 8, 12, 1, 35),
     "MINOR", "스테이지 파티클 카운트 상승", "박지훈"),
    ("SYN-EVT-I04", "SYN-BD-01", None, _t(2026, 8, 10, 1, 10), _t(2026, 8, 10, 1, 25),
     "MAJOR", "도어 센서 오동작으로 설비 인터락", "박지훈"),
    ("SYN-EVT-I05", "SYN-BD-02", "CH-B", _t(2026, 8, 10, 1, 0), _t(2026, 8, 10, 1, 20),
     "MAJOR", "히터 온도 편차 ±8도", "이하늘"),
    ("SYN-EVT-I06", "SYN-BD-03", "CH-A", _t(2026, 8, 12, 1, 35), _t(2026, 8, 12, 2, 5),
     "MINOR", "얼라인 카메라 포커스 드리프트", "이하늘"),
    ("SYN-EVT-I07", "SYN-BD-03", None, _t(2026, 8, 10, 1, 45), _t(2026, 8, 10, 2, 5),
     "CRITICAL", "반송 로봇 정지 — 웨이퍼 1매 챔버 대기", "정우진"),
    ("SYN-EVT-I08", "SYN-MLD-03", "CH-B", _t(2026, 8, 10, 2, 15), _t(2026, 8, 10, 2, 45),
     "MAJOR", "몰드 컴파운드 미충전 의심", "정우진"),
    ("SYN-EVT-I09", "SYN-MLD-04", "CH-A", _t(2026, 8, 12, 2, 20), _t(2026, 8, 12, 2, 50),
     "MINOR", "금형 승온 지연 — 사이클 타임 초과", "최민서"),
    ("SYN-EVT-I10", "SYN-DIF-01", "CH-B", _t(2026, 8, 12, 0, 10), _t(2026, 8, 12, 0, 40),
     "MAJOR", "가스 유량 편차 — MFC 재교정 필요", "최민서"),
    ("SYN-EVT-I11", "SYN-STK-B", None, _t(2026, 8, 11, 0, 15), _t(2026, 8, 11, 0, 45),
     "MINOR", "스토커 슬롯 맵 불일치 — 재스캔", "한지우"),
    ("SYN-EVT-I12", "SYN-MI-01", None, _t(2026, 8, 11, 1, 15), _t(2026, 8, 11, 1, 45),
     "MAJOR", "두께 게이지 기준편 이탈", "한지우"),
)

#: --- PM --------------------------------------------------------------------------------
#: All tool-wide (a PM takes the tool down, not one chamber) and therefore no severity.
#: Every window sits inside a gap listed in the module docstring, with real runs on BOTH
#: sides; `verify_events` re-measures all three conditions and refuses otherwise.
PMS = (
    ("SYN-EVT-P01", "SYN-BD-01", _t(2026, 8, 10, 3, 0), _t(2026, 8, 11, 15, 0),
     "정기 PM — 본딩 헤드 교체 및 가압 캘리브레이션", "설비1팀 박지훈"),
    ("SYN-EVT-P02", "SYN-BD-02", _t(2026, 8, 10, 4, 0), _t(2026, 8, 11, 16, 0),
     "정기 PM — 챔버 클리닝, O링 교체", "설비1팀 박지훈"),
    ("SYN-EVT-P03", "SYN-BD-03", _t(2026, 8, 10, 5, 0), _t(2026, 8, 11, 17, 0),
     "정기 PM — 반송 로봇 티칭 재조정", "설비1팀 이하늘"),
    # The worked example's tool.  A PM here is what a before/after contrast on SYN-BD-04
    # would be measured across.
    ("SYN-EVT-P04", "SYN-BD-04", _t(2026, 8, 10, 6, 0), _t(2026, 8, 11, 18, 0),
     "정기 PM — 히터 존 교체, CH-B 진공 라인 점검", "설비1팀 이하늘"),
    ("SYN-EVT-P05", "SYN-MLD-01", _t(2026, 8, 10, 4, 0), _t(2026, 8, 11, 19, 0),
     "정기 PM — 금형 세정 및 이형제 도포", "설비2팀 정우진"),
    ("SYN-EVT-P06", "SYN-MLD-02", _t(2026, 8, 10, 5, 0), _t(2026, 8, 11, 20, 0),
     "정기 PM — 플런저 마모 점검", "설비2팀 정우진"),
    ("SYN-EVT-P07", "SYN-MLD-03", _t(2026, 8, 10, 6, 0), _t(2026, 8, 11, 21, 0),
     "정기 PM — 컴파운드 공급 라인 교체", "설비2팀 최민서"),
    ("SYN-EVT-P08", "SYN-MLD-04", _t(2026, 8, 10, 7, 0), _t(2026, 8, 11, 22, 0),
     "정기 PM — 금형 온도 센서 교정", "설비2팀 최민서"),
    ("SYN-EVT-P09", "SYN-PC-01", _t(2026, 8, 9, 0, 30), _t(2026, 8, 9, 0, 55),
     "단시간 PM — RF 매칭 박스 점검", "설비3팀 한지우"),
    ("SYN-EVT-P10", "SYN-PC-02", _t(2026, 8, 9, 0, 30), _t(2026, 8, 9, 0, 55),
     "단시간 PM — 전극 세정", "설비3팀 한지우"),
    ("SYN-EVT-P11", "SYN-FE-01", _t(2026, 8, 7, 0, 40), _t(2026, 8, 7, 1, 20),
     "단시간 PM — 척 표면 파티클 제거", "설비3팀 김선호"),
    ("SYN-EVT-P12", "SYN-FE-05", _t(2026, 8, 7, 0, 35), _t(2026, 8, 7, 1, 15),
     "단시간 PM — 배기 라인 필터 교체", "설비3팀 김선호"),
)

#: --- COMMENTS --------------------------------------------------------------------------
#: `Wafer` targets are SYN-BW-103-* (each verified to carry atoms); `Lot` targets are real
#: lots taken from `lot_event` / `has_wafer`.  One comment per target, so no two comments
#: land on the same `commented_at`.
COMMENTS = (
    ("SYN-CMT-01", "Wafer", "SYN-BW-103-11", "김선호", "본딩 직후 육안 확인. 엣지 3시 방향 얼룩, 재세정 후 통과"),
    ("SYN-CMT-02", "Wafer", "SYN-BW-103-09", "김선호", "CH-B 로 들어간 건 이 장만. 또래랑 비교 필요"),
    ("SYN-CMT-03", "Wafer", "SYN-BW-103-01", "박지훈", "가압 이상 구간에 걸침. 보이드 재측정 요청함"),
    ("SYN-CMT-04", "Wafer", "SYN-BW-103-03", "박지훈", "특이사항 없음"),
    ("SYN-CMT-05", "Wafer", "SYN-BW-103-05", "이하늘", "슬롯 5 반송 중 알람, 수동 복구함"),
    ("SYN-CMT-06", "Wafer", "SYN-BW-103-07", "이하늘", "두께 편차 상한 근처. 다음 랏에서 추이 볼 것"),
    ("SYN-CMT-07", "Wafer", "SYN-BW-103-12", "정우진", "재작업 1회. 원인은 얼라인 오차"),
    ("SYN-CMT-08", "Wafer", "SYN-BW-103-15", "정우진", "PM 직후 첫 장. 기준으로 쓰기 좋음"),
    ("SYN-CMT-09", "Wafer", "SYN-BW-103-16", "최민서", "몰딩 후 표면 광택 차이 있음, 사진 첨부함"),
    ("SYN-CMT-10", "Wafer", "SYN-BW-103-21", "최민서", "홀드 걸었다가 해제. 판정 문제 없었음"),
    ("SYN-CMT-11", "Wafer", "SYN-BW-103-02", "한지우", "계측 재현성 확인용으로 2회 측정"),
    ("SYN-CMT-12", "Wafer", "SYN-BW-103-04", "한지우", "특이사항 없음"),
    ("SYN-CMT-13", "Wafer", "SYN-BW-103-06", "김선호", "스토커 대기 길었음. 큐 타임 영향 볼 것"),
    ("SYN-CMT-14", "Wafer", "SYN-BW-103-08", "박지훈", "엣지 다이 제외하고 판정함"),
    ("SYN-CMT-15", "Lot", "NAB539", "정우진", "이 랏 재작업 1회"),
    ("SYN-CMT-16", "Lot", "NAB163", "정우진", "슬롯 12, 13 빠짐. 현품표와 대조 완료"),
    ("SYN-CMT-17", "Lot", "NAB122", "최민서", "고객 요청으로 우선 처리"),
    ("SYN-CMT-18", "Lot", "NAB123", "최민서", "분할 이력 있음. 자식 랏 같이 볼 것"),
    ("SYN-CMT-19", "Lot", "NAB115", "한지우", "특이사항 없음"),
    ("SYN-CMT-20", "Lot", "DT-2601-004", "한지우", "DT 수율 낮게 나옴. 코어 쪽 확인 요청"),
    ("SYN-CMT-21", "Lot", "DT-2601-003", "김선호", "전 랏과 동일 조건. 비교군으로 사용"),
    ("SYN-CMT-22", "Lot", "CL-2601-005", "김선호", "클린 공정에서 홀드. 다음날 해제"),
    ("SYN-CMT-23", "Lot", "SYN-SPL-400", "박지훈", "분할 직후 슬롯 맵 재확인함"),
    ("SYN-CMT-24", "Lot", "SYN-MRG-400", "이하늘", "병합 랏. 원 랏 두 개 이력 같이 봐야 함"),
)

#: How long after a target's LAST atom its comment is dated.  A comment is written after
#: the thing it comments on, and the base is read from the database rather than invented.
COMMENT_OFFSET = timedelta(minutes=30)


# ---------------------------------------------------------------------------------------
# Measurement.  Nothing below writes.
# ---------------------------------------------------------------------------------------

def _atoms_on(db, eqp, chamber=None, start=None, end=None, before=None, after=None):
    """Count `processed_with` atoms on one tool, optionally narrowed by chamber and time."""
    from sqlalchemy import text

    sql = ["SELECT count(*) FROM ledger_events",
           "WHERE predicate='processed_with' AND object_payload->>'eqp' = :eqp"]
    params = {"eqp": eqp}
    if chamber is not None:
        sql.append("AND object_payload->>'chamber' = :chamber")
        params["chamber"] = chamber
    if start is not None:
        sql.append("AND occurred_at >= :start")
        params["start"] = start
    if end is not None:
        sql.append("AND occurred_at <= :end")
        params["end"] = end
    if before is not None:
        sql.append("AND occurred_at < :before")
        params["before"] = before
    if after is not None:
        sql.append("AND occurred_at > :after")
        params["after"] = after
    return int(db.execute(text(" ".join(sql)), params).scalar() or 0)


def _neighbour_runs(db, eqp, start, end):
    """The run immediately BEFORE and immediately AFTER a window, on that tool.

    This is the evidence a PM window is real rather than decorative: a window with nothing
    on one side of it names no step in any trend.
    """
    from sqlalchemy import text

    prev = db.execute(text(
        "SELECT max(occurred_at) FROM ledger_events WHERE predicate='processed_with' "
        "AND object_payload->>'eqp' = :eqp AND occurred_at < :start"),
        {"eqp": eqp, "start": start}).scalar()
    nxt = db.execute(text(
        "SELECT min(occurred_at) FROM ledger_events WHERE predicate='processed_with' "
        "AND object_payload->>'eqp' = :eqp AND occurred_at > :end"),
        {"eqp": eqp, "end": end}).scalar()
    return prev, nxt


def _entity_atoms(db, target_type, target_id):
    """(count, last occurred_at) for one lot or wafer across every predicate."""
    from sqlalchemy import text

    key = "wafer" if target_type == "Wafer" else "lot"
    row = db.execute(text(
        "SELECT count(*), max(occurred_at) FROM ledger_events "
        "WHERE subject_keys->>:key = :val"), {"key": key, "val": target_id}).first()
    return int(row[0] or 0), row[1]


def verify_names(db):
    """🔴 REFUSE unless every name this fixture points at already carries atoms.

    This is the check that decides whether the fixture is reachable.  It is not a
    formality: the 2026-08-22 transfer fixture passed every test it had and was still
    unreachable, because nothing ever asked whether its names existed.
    """
    problems = []
    proof = []

    tools = {}
    for _, eqp, chamber, _, _, _, _, _ in INCIDENTS:
        tools.setdefault((eqp, chamber), 0)
    for _, eqp, _, _, _, _ in PMS:
        tools.setdefault((eqp, None), 0)
    for eqp, chamber in sorted(tools, key=lambda p: (p[0], p[1] or "")):
        n = _atoms_on(db, eqp, chamber)
        tools[(eqp, chamber)] = n
        label = eqp if chamber is None else "%s / %s" % (eqp, chamber)
        if n == 0:
            problems.append("no processed_with atom names %s" % label)
        else:
            proof.append(("equipment", label, n, "processed_with.object_payload"))

    for _, target_type, target_id, _, _ in COMMENTS:
        n, _ = _entity_atoms(db, target_type, target_id)
        if n == 0:
            problems.append("no atom names %s %s" % (target_type, target_id))
        else:
            proof.append((target_type.lower(), target_id, n,
                          "ledger_events.subject_keys"))

    if problems:
        raise SystemExit(
            "REFUSED: %d name(s) this fixture points at carry no atoms:\n  %s\n"
            "A fixture whose names nobody else uses is an island -- that is exactly how "
            "the 2026-08-22 die-transfer rows became unreachable.  Nothing was written."
            % (len(problems), "\n  ".join(problems)))
    return proof


def verify_events(db):
    """🔴 REFUSE unless every span means something against the real run distribution.

    incident -> must COVER a run.  pm -> must sit in a GAP with runs on BOTH sides.
    """
    problems = []
    covered = {}
    windows = {}

    for uid, eqp, chamber, start, end, _, _, _ in INCIDENTS:
        n = _atoms_on(db, eqp, chamber, start=start, end=end)
        covered[uid] = n
        if n == 0:
            label = eqp if chamber is None else "%s / %s" % (eqp, chamber)
            problems.append(
                "%s covers no run on %s between %s and %s -- an incident that overlaps "
                "nothing can never be reached by a walk" % (uid, label, start, end))

    for uid, eqp, start, end, _, _ in PMS:
        inside = _atoms_on(db, eqp, start=start, end=end)
        prior = _atoms_on(db, eqp, before=start)
        later = _atoms_on(db, eqp, after=end)
        prev_at, next_at = _neighbour_runs(db, eqp, start, end)
        windows[uid] = (inside, prior, later, prev_at, next_at)
        if inside:
            problems.append(
                "%s (%s) has %d run(s) INSIDE the PM window -- it is not a gap"
                % (uid, eqp, inside))
        if not prior or not later:
            problems.append(
                "%s (%s) has runs before=%d after=%d -- a PM with wafers on only one "
                "side compares nothing" % (uid, eqp, prior, later))

    if problems:
        raise SystemExit(
            "REFUSED: %d span(s) do not sit against the real run distribution:\n  %s\n"
            "Nothing was written." % (len(problems), "\n  ".join(problems)))
    return covered, windows


# ---------------------------------------------------------------------------------------
# Row building.
# ---------------------------------------------------------------------------------------

def build_event_rows():
    """The 24 `eqp_event` rows.  Pure -- no database is touched here."""
    rows = []
    for uid, eqp, chamber, start, end, severity, summary, operator in INCIDENTS:
        rows.append({
            "event_uid": uid,
            "kind": "incident",
            "target_type": "chamber" if chamber else "equipment",
            "eqp_id": eqp,
            "chamber_id": chamber,
            "started_at": start,
            "ended_at": end,
            "severity": severity,
            "summary": summary,
            "operator": operator,
        })
    for uid, eqp, start, end, summary, operator in PMS:
        rows.append({
            "event_uid": uid,
            "kind": "pm",
            "target_type": "equipment",
            "eqp_id": eqp,
            "chamber_id": None,
            "started_at": start,
            "ended_at": end,
            # A PM is planned work, not a fault, so it carries no severity.  None rather
            # than a filler string: `crud` treats a blank key column as NULL and a made-up
            # level would be read as a real one.
            "severity": None,
            "summary": summary,
            "operator": operator,
        })
    keys = [row["event_uid"] for row in rows]
    if len(set(keys)) != len(keys):
        raise SystemExit("REFUSED: event_uid is not unique across the planned rows.")
    return rows


def build_comment_rows(db):
    """The 24 `entity_comment` rows.  `commented_at` is READ from the target's last atom."""
    rows = []
    for uid, target_type, target_id, author, body in COMMENTS:
        _, last_at = _entity_atoms(db, target_type, target_id)
        if last_at is None:
            raise SystemExit(
                "REFUSED: %s %s has no atom to date a comment against." % (target_type,
                                                                           target_id))
        rows.append({
            "comment_uid": uid,
            "target_type": target_type,
            "target_id": target_id,
            "author": author,
            "commented_at": last_at + COMMENT_OFFSET,
            "body": body,
        })
    keys = [row["comment_uid"] for row in rows]
    if len(set(keys)) != len(keys):
        raise SystemExit("REFUSED: comment_uid is not unique across the planned rows.")
    return rows


def _require_declared(table):
    """Refuse clearly if the table is absent, rather than half-working.

    The table is created by DECLARING it in `table_config.json`; if that has not happened
    the right answer is to say so by name, not to write half a fixture.
    """
    from database import models

    if models.DYNAMIC_TABLES.get(table) is None:
        raise SystemExit(
            "REFUSED: table '%s' is not declared in table_config.json, so it does not "
            "exist.  Declare it first -- the catalogue entry is what creates the table.  "
            "Nothing was written." % table)


def _verify_unowned(db, table, key_column, expected):
    """Refuse if something already wears this fixture's keys but is not ours."""
    from sqlalchemy import text

    found = {r[0] for r in db.execute(text(
        'SELECT DISTINCT %s FROM "%s" WHERE %s LIKE :prefix'
        % (key_column, table, key_column)), {"prefix": "SYN-EVT-%"
                                             if table == EVENT_TABLE else "SYN-CMT-%"})
             if r[0] is not None}
    stray = sorted(found - set(expected))
    if stray:
        raise SystemExit(
            "REFUSED: %s already holds rows under this fixture's prefix that this run "
            "does not own: %s" % (table, stray[:5]))


def _write(db, table, rows, key_column):
    from database import crud, schemas

    changed = 0
    for start in range(0, len(rows), CHUNK):
        part = rows[start:start + CHUNK]
        batch = schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(
                updates=row,
                source_name=SOURCE_NAME,
                updated_by=UPDATED_BY,
                # Supplying the declared key is what makes a second run resolve onto the
                # same rows instead of inserting new ones.
                business_key_val=row[key_column],
            )
            for row in part
        ])
        _, cells, _, _ = crud.apply_batch_updates(db, table, batch)
        changed += len(cells or ())
    return changed


def main():
    parser = argparse.ArgumentParser(
        description=("Seed synthetic tool events (incident + PM) into eqp_event and "
                     "lot/wafer comments into entity_comment.  Adds and updates its own "
                     "rows; never deletes."))
    parser.add_argument("--apply", action="store_true",
                        help="write; default is a dry run that touches nothing")
    parser.add_argument("--show", action="store_true",
                        help="print every planned row and the runs each span sits against")
    parser.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                        dest="accepted")
    args = parser.parse_args()
    if args.apply and not args.accepted:
        raise SystemExit("REFUSED: --apply needs --i-accept-writing-to-owner-database.")

    from database.database import SessionLocal
    from database import crud, models

    models.init_dynamic_models(crud.TABLE_CONFIG)
    _require_declared(EVENT_TABLE)
    _require_declared(COMMENT_TABLE)

    db = SessionLocal()
    try:
        proof = verify_names(db)
        covered, windows = verify_events(db)
        event_rows = build_event_rows()
        comment_rows = build_comment_rows(db)
        _verify_unowned(db, EVENT_TABLE, "event_uid",
                        [r["event_uid"] for r in event_rows])
        _verify_unowned(db, COMMENT_TABLE, "comment_uid",
                        [r["comment_uid"] for r in comment_rows])

        changed = 0
        if args.apply:
            changed += _write(db, EVENT_TABLE, event_rows, "event_uid")
            changed += _write(db, COMMENT_TABLE, comment_rows, "comment_uid")
    finally:
        db.close()

    incidents = [r for r in event_rows if r["kind"] == "incident"]
    pms = [r for r in event_rows if r["kind"] == "pm"]
    print("names verified against live atoms : %d" % len(proof))
    print("%-22s : %d rows  (incident %d + pm %d)"
          % (EVENT_TABLE, len(event_rows), len(incidents), len(pms)))
    print("%-22s : %d rows" % (COMMENT_TABLE, len(comment_rows)))
    print()
    print("WORKED EXAMPLE")
    worked = INCIDENTS[0]
    print("  read atom  : SYN-BW-103-11 BONDING 2026-08-10 01:40:00+09:00 "
          "on SYN-BD-04 / CH-A")
    print("  incident   : %s  %s .. %s  (covers %d run(s))"
          % (worked[0], worked[3], worked[4], covered[worked[0]]))
    chb = INCIDENTS[1]
    print("  read atom  : SYN-BW-103-09 BONDING 2026-08-10 01:38:00+09:00 "
          "on SYN-BD-04 / CH-B   (103-11 has NO CH-B atom)")
    print("  incident   : %s  %s .. %s  (covers %d run(s))"
          % (chb[0], chb[3], chb[4], covered[chb[0]]))

    if args.show:
        print()
        print("INCIDENTS -- each covers real runs")
        for uid, eqp, chamber, start, end, severity, summary, _ in INCIDENTS:
            print("  %-12s %-11s %-5s %s .. %s  %-8s covers=%-4d %s"
                  % (uid, eqp, chamber or "-", start.strftime("%m-%d %H:%M"),
                     end.strftime("%m-%d %H:%M"), severity, covered[uid], summary))
        print()
        print("PM -- each sits in a gap, runs on BOTH sides")
        for uid, eqp, start, end, summary, _ in PMS:
            inside, prior, later, prev_at, next_at = windows[uid]
            print("  %-12s %-11s %s .. %s  inside=%d before=%d after=%d"
                  % (uid, eqp, start.strftime("%m-%d %H:%M"),
                     end.strftime("%m-%d %H:%M"), inside, prior, later))
            print("               last run before %s | first run after %s" % (prev_at, next_at))
        print()
        print("COMMENTS")
        for row in comment_rows:
            print("  %-12s %-6s %-22s %s  %s"
                  % (row["comment_uid"], row["target_type"], row["target_id"],
                     row["commented_at"], row["body"]))

    if args.apply:
        print()
        print("cells changed          : %d" % changed)
        print("WROTE synthetic tool events and comments. Nothing was deleted.")
    else:
        print()
        print("DRY RUN, nothing written.")


if __name__ == "__main__":
    main()
