"""Locate the invariants that must survive the legacy retirement, by their own words.

A retirement round is judged by whether coverage MOVED or was LOST, and the two look
identical from a green suite.  Each entry below is an invariant that the eight
collection-broken test files were the sole home of (measured 2026-08-18); the marker is
a string that only a test asserting that invariant would contain.

Run before and after the round.  A marker that goes to zero files is coverage that left
and did not arrive.

Usage:  python ledger_invariant_locator.py [tests_dir]
"""
import sys, pathlib, collections

sys.stdout.reconfigure(encoding='utf-8')

# invariant -> (marker string, why it must survive)
INVARIANTS = {
    "v2: registration snapshot required":
        ("registration_context_required",
         "preview without known_registrations must refuse, and a replay must not re-register"),
    "v2: positional list checked before candidates":
        ("invalid_positional_list",
         "a slots/wafers length mismatch fails before any candidate is returned"),
    "v2: mapper import boundary":
        ("ledger_v2_lot_event_role_mapper",
         "the mapper file must not import database/gate/store/envelope/ledger_frame"),
    "v2: incomplete molecule accounting":
        ("incomplete_molecules",
         "incomplete is not refused - atoms land and the counter moves"),
    "v2: store write contract":
        ("unsupported_store_contract",
         "write_batch's reasons is keyword-only and undefaulted"),
    "v2: ledger frame validation":
        ("LedgerFrameError",
         "frame schema, structured identity/payload, source-event identity"),
    "backfill: group page boundary":
        ("walk_group_pages",
         "a group dropped at a page boundary is read on the next page"),
    "read: observed stays out of the walk":
        ("PROJECTION_ONLY_WORDS",
         "hop states are projection words; observed is never traversed"),
    "read: lineage vocabulary is derived":
        ("LINEAGE_PREDICATES",
         "the walk's predicate set is derived from the declaration, not literals"),
    "live: declared time rule":
        ("parse_occurred_at",
         "observability's lag probe reads it - naive text takes the declared zone"),
}


def main():
    tests = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                         else r"C:\Users\kk980\Developments\assyManager\server\tests")
    homes = collections.defaultdict(list)
    for path in sorted(tests.rglob("test_*.py")):
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        for name, (marker, _why) in INVARIANTS.items():
            if marker in text:
                homes[name].append(path.name)

    lost = 0
    for name, (marker, why) in INVARIANTS.items():
        where = homes.get(name, [])
        if not where:
            lost += 1
            print(f"  LOST  {name}\n        marker {marker!r} is in no test file\n"
                  f"        {why}")
        else:
            print(f"  ok    {name:42s} {', '.join(where)}")
    print()
    print("LOST INVARIANTS:", lost, "(0 이면 통과)")
    return 1 if lost else 0


if __name__ == "__main__":
    raise SystemExit(main())
