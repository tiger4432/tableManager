"""Baseline atom snapshot for the live ledger config. No DB, no gate, no cursor write.

The entry point is resolved by search rather than by a fixed import: the module is
being renamed out of its cutover-era name while this harness is the gate on that very
refactor.  A hard import would make the gate disappear exactly when it matters, and a
silent skip would read as "nothing changed" -- so a miss aborts loudly and names what
it looked for.
"""
import sys, json, importlib
from dataclasses import replace
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"C:\Users\kk980\Developments\assyManager\server")
import pandas as pd
from ledger.source_preparation import VerifiedJoinBatchReader

_MODULES = ("ledger.setup", "ledger.cutover_v2", "ledger.setup_boundary")
_LOADERS = ("load_setup", "load_cutover_setup", "load_ledger_setup")
_PREVIEWS = ("preview_selected_cursor_batch", "preview_selected_batch")


def _resolve():
    tried = []
    for name in _MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError:
            tried.append(f"{name} (absent)")
            continue
        load = next((getattr(module, n) for n in _LOADERS if hasattr(module, n)), None)
        preview = next((getattr(module, n) for n in _PREVIEWS if hasattr(module, n)), None)
        if load and preview:
            return name, load, preview
        tried.append(f"{name} (loader={bool(load)} preview={bool(preview)})")
    raise SystemExit(
        "BASELINE HARNESS BROKEN: no setup loader + preview entry point found.\n"
        f"  looked in: {tried}\n"
        f"  loader names: {_LOADERS}\n  preview names: {_PREVIEWS}\n"
        "Fix this harness before reading any diff as a pass -- a harness that cannot "
        "run is not a zero diff.")


_MODULE, load_cutover_setup, preview_selected_cursor_batch = _resolve()

# argv[2] optionally points at a DIFFERENT setup root. The default is unchanged, so a
# caller passing only a destination measures the live root exactly as before. It exists
# because the single-file transition must be measured on the CONVERTED content before the
# operator's root is overwritten -- and the operator is hand-editing that file today.
_LIVE_ROOT = r"C:\Users\kk980\Developments\assyManager\server\config\ontology"
ROOT = sys.argv[2] if len(sys.argv) > 2 else _LIVE_ROOT
T = lambda s: pd.Timestamp(s, tz="Asia/Seoul")

class NoJoin(VerifiedJoinBatchReader):
    def read_chunk(self, descriptor, keys):
        raise AssertionError("no joins expected")

# --- what each case is measured against ----------------------------------------------
# `(setup_key, source_id)`.  Until 2026-08-19 every case ran `lot_event`, whose time is a
# declared world-time COLUMN -- so the whole baseline traversed one of the two time
# declarations and ten green runs said nothing about the other.  `basis` ("the row's
# ingestion time") reached production on `dt_job` and split single jobs into two atoms
# carrying ingestion batch sizes; a gate that cannot see a path cannot hold it.
LIVE = "live"
#: The live `dt_job` plan with ONE field changed: its time re-declared as a world-time
#: column instead of a basis.  There is no live source that can hold this case -- the only
#: `column` source is `lot_event`, whose group key EMBEDS `event_time`, so two world times
#: can never share one of its groups -- and without it a later "simplification" could drop
#: the refusal and every case here would stay green.  It is the same rows as the straddle
#: case above it: the two differ ONLY in the declaration, which is what makes the pair
#: decide anything.
WORLD_TIME_VARIANT = "dt_job_as_world_time"

CASES = {
    "split_complete": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-006", "event_type": "split", "slotnumbers": "1:2",
         "waferids": "W01:W02", "parent_lot": "", "child_lot": "CL-2601-006-A1",
         "txn_seq": "1001", "event_time": T("2026-08-01T10:00:00")},
        {"lot_id": "CL-2601-006-A1", "event_type": "split", "slotnumbers": "1",
         "waferids": "W01", "parent_lot": "CL-2601-006", "child_lot": "",
         "txn_seq": "1002", "event_time": T("2026-08-01T10:00:00")},
    ]),
    "split_incomplete_child_missing": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-007", "event_type": "split", "slotnumbers": "1:2",
         "waferids": "W11:W12", "parent_lot": "", "child_lot": "CL-2601-007-A1",
         "txn_seq": "2001", "event_time": T("2026-08-02T10:00:00")},
    ]),
    "merge_complete": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-008", "event_type": "merge", "slotnumbers": "1:2",
         "waferids": "W21:W22", "parent_lot": "", "child_lot": "CL-2601-008-M",
         "txn_seq": "3001", "event_time": T("2026-08-03T10:00:00")},
        {"lot_id": "CL-2601-008-M", "event_type": "merge", "slotnumbers": "5:6",
         "waferids": "W21:W22", "parent_lot": "CL-2601-008", "child_lot": "",
         "txn_seq": "3002", "event_time": T("2026-08-03T10:00:00")},
    ]),
    "track_in": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-009", "event_type": "track_in", "slotnumbers": "1:2:3",
         "waferids": "W31:W32:W33", "parent_lot": "", "child_lot": "",
         "txn_seq": "4001", "event_time": T("2026-08-04T10:00:00")},
    ]),
    # --- 거절이 정답인 표본 (조용히 통과하기 시작하면 그것이 회귀다) --------------
    "refuse_ambiguous_row": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-010", "event_type": "split", "slotnumbers": "1",
         "waferids": "W41", "parent_lot": "CL-2601-010-P", "child_lot": "CL-2601-010-C",
         "txn_seq": "5001", "event_time": T("2026-08-05T10:00:00")},
    ]),
    "refuse_unknown_event_type": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-011", "event_type": "TRACK_IN", "slotnumbers": "1",
         "waferids": "W51", "parent_lot": "", "child_lot": "",
         "txn_seq": "6001", "event_time": T("2026-08-06T10:00:00")},
    ]),
    "refuse_slot_wafer_length_mismatch": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-012", "event_type": "track_in", "slotnumbers": "1:2:3",
         "waferids": "W61:W62", "parent_lot": "", "child_lot": "",
         "txn_seq": "7001", "event_time": T("2026-08-07T10:00:00")},
    ]),
    "refuse_naive_timestamp": (LIVE, "lot_event", [
        {"lot_id": "CL-2601-013", "event_type": "track_in", "slotnumbers": "1",
         "waferids": "W71", "parent_lot": "", "child_lot": "",
         "txn_seq": "8001", "event_time": pd.Timestamp("2026-08-08T10:00:00")},
    ]),
    # --- basis 경로: 그룹의 적재 시각 (2026-08-19 판정) ---------------------------
    # `dt_job`은 여러 행이 한 사건인 소스이고, 그 행들이 한 인제션 배치에 다 들어온다는
    # 보장이 없다. 세 케이스는 함께 읽어야 한다: 1은 「쪼갤 것이 없을 때」, 2는 「쪼갤 수
    # 있을 때 min으로 접는다」, 3은 「같은 입력이라도 world time 선언이면 여전히 거절」.
    "dtjob_group_one_ingest_time": (LIVE, "dt_job", [
        {"dt_job": "BASE-J1", "dt_cell_key": "0001", "dt_index": 1,
         "event_time": "2026-08-01 09:00:00", "created_at": T("2026-08-01T09:30:00")},
        {"dt_job": "BASE-J1", "dt_cell_key": "0002", "dt_index": 2,
         "event_time": "2026-08-01 09:00:00", "created_at": T("2026-08-01T09:30:00")},
        {"dt_job": "BASE-J1", "dt_cell_key": "0003", "dt_index": 3,
         "event_time": "2026-08-01 09:00:00", "created_at": T("2026-08-01T09:30:00")},
    ]),
    # 세 행이 두 적재 시각에 걸친다. 사건은 ONE, 시각은 가장 이른 09:30 -- 두 개로 쪼개져
    # 「3개」가 「1개 + 2개」가 되면 그것이 원장에 이미 들어간 12건과 같은 결함이다.
    # 늦게 온 조각(11:00)이 시각을 끌고 가지 않는 것이 재적재 안정성의 전부다.
    "dtjob_group_straddles_two_ingest_times": (LIVE, "dt_job", [
        {"dt_job": "BASE-J2", "dt_cell_key": "0001", "dt_index": 1,
         "event_time": "2026-08-02 09:00:00", "created_at": T("2026-08-02T11:00:00")},
        {"dt_job": "BASE-J2", "dt_cell_key": "0002", "dt_index": 2,
         "event_time": "2026-08-02 09:00:00", "created_at": T("2026-08-02T09:30:00")},
        {"dt_job": "BASE-J2", "dt_cell_key": "0003", "dt_index": 3,
         "event_time": "2026-08-02 09:00:00", "created_at": T("2026-08-02T11:00:00")},
    ]),
    # 바로 위와 행이 같다. 다른 것은 선언 하나뿐 -- 이 시각이 world time이라면 두 시각은
    # 「그룹이 틀렸다」는 뜻이고, 접는 것이 아니라 거절이 정답이다.
    "refuse_two_world_times_in_one_group": (WORLD_TIME_VARIANT, "dt_job", [
        {"dt_job": "BASE-J3", "dt_cell_key": "0001", "dt_index": 1,
         "event_time": "2026-08-03 09:00:00", "created_at": T("2026-08-03T11:00:00")},
        {"dt_job": "BASE-J3", "dt_cell_key": "0002", "dt_index": 2,
         "event_time": "2026-08-03 09:00:00", "created_at": T("2026-08-03T09:30:00")},
        {"dt_job": "BASE-J3", "dt_cell_key": "0003", "dt_index": 3,
         "event_time": "2026-08-03 09:00:00", "created_at": T("2026-08-03T11:00:00")},
    ]),
}

setup = load_cutover_setup(ROOT)


def _world_time_setup(live):
    """The live setup with `dt_job`'s time re-declared as a world-time column.

    Built by `replace` on the COMPILED plan rather than by a second config file: the one
    thing that may differ from the live declaration is the field under test, so the case
    above it and this one cannot drift apart. The registry class is taken from the live
    object instead of imported, so renaming it does not silently drop this case.
    """
    plan = live.snapshot.source_plans["dt_job"]
    world = replace(plan.driver.occurred_at, basis=None)
    if world.column != plan.driver.occurred_at.column or world.basis is not None:
        raise SystemExit("world-time variant changed more than the declaration")
    plans = dict(live.snapshot.source_plans)
    plans["dt_job"] = replace(plan, driver=replace(plan.driver, occurred_at=world))
    registry = type(live.snapshot.source_plans)(plans)
    return replace(live, snapshot=replace(live.snapshot, source_plans=registry))


SETUPS = {LIVE: setup, WORLD_TIME_VARIANT: _world_time_setup(setup)}
out = {"snapshot_sha256": setup.snapshot.snapshot_sha256, "cases": {}}
print("snapshot:", setup.snapshot.snapshot_sha256)

for name, (setup_key, source_id, records) in CASES.items():
    case_setup = SETUPS[setup_key]
    rows = pd.DataFrame(records)
    # The cursor is the source's OWN declared keyset, so adding a source does not mean
    # adding a hand-written cursor shape that could disagree with the declaration.
    cursor = {
        column: rows.iloc[-1][column]
        for column in case_setup.snapshot.source_plans[source_id].driver.cursor_columns
    }
    try:
        preview = preview_selected_cursor_batch(
            case_setup, source_id, rows, cursor, NoJoin(), known_registrations=())
        atoms = [
            {"subject_type": a["subject_type"],
             "subject_keys": a["subject_keys"],
             "predicate": a["predicate"],
             "object_kind": a["object_kind"],
             "object_payload": a["object_payload"]}
            for a in preview.candidate_semantics
        ]
        out["cases"][name] = {
            "rows": len(records), "molecules": preview.molecule_count,
            "atoms": preview.atom_count, "incomplete": preview.incomplete_count,
            "semantics": atoms,
        }
        # WHICH instant the atoms carry, recorded only where the declaration makes that a
        # question. `molecules=1` alone would stay green if the group collapsed to its
        # LATEST read instead of its earliest -- and "latest" is the answer that re-mints
        # the same event under a new id every time a late row arrives, so a guard that
        # cannot tell the two apart is not guarding the ruling. The `column` cases keep the
        # shape their existing baseline pinned; there the instant is not in question.
        if case_setup.snapshot.source_plans[source_id].driver.occurred_at.basis:
            out["cases"][name]["occurred_at"] = sorted({
                str(value)
                for result in preview.event_results
                for value in result.ledger_frame["occurred_at"].tolist()
            })
        print(f"{name:32s} molecules={preview.molecule_count} atoms={preview.atom_count} "
              f"incomplete={preview.incomplete_count} "
              f"{out['cases'][name].get('occurred_at', '')}")
    except Exception as exc:
        code = getattr(exc, "code", None)
        path = getattr(exc, "path", None)
        out["cases"][name] = {
            "rows": len(records), "refused": True,
            "error_type": type(exc).__name__, "code": code, "path": path,
            "message": getattr(exc, "message", str(exc)),
        }
        print(f"{name:34s} REFUSED {code or type(exc).__name__} @ {path or '-'}")

dest = sys.argv[1]
with open(dest, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    fh.write("\n")
print("written:", dest)
