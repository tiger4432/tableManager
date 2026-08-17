"""Baseline atom snapshot for the live ledger config. No DB, no gate, no cursor write."""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"C:\Users\kk980\Developments\assyManager\server")
import pandas as pd
from ledger.cutover_v2 import load_cutover_setup, preview_selected_cursor_batch
from ledger.source_preparation import VerifiedJoinBatchReader

ROOT = r"C:\Users\kk980\Developments\assyManager\server\config\ontology"
T = lambda s: pd.Timestamp(s, tz="Asia/Seoul")

class NoJoin(VerifiedJoinBatchReader):
    def read_chunk(self, descriptor, keys):
        raise AssertionError("no joins expected")

CASES = {
    "split_complete": [
        {"lot_id": "CL-2601-006", "event_type": "split", "slotnumbers": "1:2",
         "waferids": "W01:W02", "parent_lot": "", "child_lot": "CL-2601-006-A1",
         "txn_seq": "1001", "event_time": T("2026-08-01T10:00:00")},
        {"lot_id": "CL-2601-006-A1", "event_type": "split", "slotnumbers": "1",
         "waferids": "W01", "parent_lot": "CL-2601-006", "child_lot": "",
         "txn_seq": "1002", "event_time": T("2026-08-01T10:00:00")},
    ],
    "split_incomplete_child_missing": [
        {"lot_id": "CL-2601-007", "event_type": "split", "slotnumbers": "1:2",
         "waferids": "W11:W12", "parent_lot": "", "child_lot": "CL-2601-007-A1",
         "txn_seq": "2001", "event_time": T("2026-08-02T10:00:00")},
    ],
    "merge_complete": [
        {"lot_id": "CL-2601-008", "event_type": "merge", "slotnumbers": "1:2",
         "waferids": "W21:W22", "parent_lot": "", "child_lot": "CL-2601-008-M",
         "txn_seq": "3001", "event_time": T("2026-08-03T10:00:00")},
        {"lot_id": "CL-2601-008-M", "event_type": "merge", "slotnumbers": "5:6",
         "waferids": "W21:W22", "parent_lot": "CL-2601-008", "child_lot": "",
         "txn_seq": "3002", "event_time": T("2026-08-03T10:00:00")},
    ],
    "track_in": [
        {"lot_id": "CL-2601-009", "event_type": "track_in", "slotnumbers": "1:2:3",
         "waferids": "W31:W32:W33", "parent_lot": "", "child_lot": "",
         "txn_seq": "4001", "event_time": T("2026-08-04T10:00:00")},
    ],
    # --- 거절이 정답인 표본 (조용히 통과하기 시작하면 그것이 회귀다) --------------
    "refuse_ambiguous_row": [
        {"lot_id": "CL-2601-010", "event_type": "split", "slotnumbers": "1",
         "waferids": "W41", "parent_lot": "CL-2601-010-P", "child_lot": "CL-2601-010-C",
         "txn_seq": "5001", "event_time": T("2026-08-05T10:00:00")},
    ],
    "refuse_unknown_event_type": [
        {"lot_id": "CL-2601-011", "event_type": "TRACK_IN", "slotnumbers": "1",
         "waferids": "W51", "parent_lot": "", "child_lot": "",
         "txn_seq": "6001", "event_time": T("2026-08-06T10:00:00")},
    ],
    "refuse_slot_wafer_length_mismatch": [
        {"lot_id": "CL-2601-012", "event_type": "track_in", "slotnumbers": "1:2:3",
         "waferids": "W61:W62", "parent_lot": "", "child_lot": "",
         "txn_seq": "7001", "event_time": T("2026-08-07T10:00:00")},
    ],
    "refuse_naive_timestamp": [
        {"lot_id": "CL-2601-013", "event_type": "track_in", "slotnumbers": "1",
         "waferids": "W71", "parent_lot": "", "child_lot": "",
         "txn_seq": "8001", "event_time": pd.Timestamp("2026-08-08T10:00:00")},
    ],
}

setup = load_cutover_setup(ROOT)
out = {"snapshot_sha256": setup.snapshot.snapshot_sha256, "cases": {}}
print("snapshot:", setup.snapshot.snapshot_sha256)

for name, records in CASES.items():
    rows = pd.DataFrame(records)
    cursor = {"event_time": rows.iloc[-1]["event_time"],
              "txn_seq": rows.iloc[-1]["txn_seq"]}
    try:
        preview = preview_selected_cursor_batch(
            setup, "lot_event", rows, cursor, NoJoin(), known_registrations=())
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
        print(f"{name:32s} molecules={preview.molecule_count} atoms={preview.atom_count} "
              f"incomplete={preview.incomplete_count}")
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
