"""Move a stored v2 cursor from the OLD global snapshot hash to its per-source fingerprint.

WHY THIS EXISTS
---------------
Until 2026-08-21 every source's cursor was compared against the ONE global
`snapshot_sha256`, so editing `lot_event`'s bindings refused `dt_job`'s backfill with
`cursor_snapshot_reset_required` for a change that could not alter a single `dt_job` atom.
The compared value is now `setup_registry.cursor_translator_version` -- the fingerprint of
the material that actually reaches that source. Cursors written before that change still
carry the old global string and must be re-stamped once.

🔴 THIS IS NOT A RESET AND MUST NEVER BECOME ONE. `source_translator_ver` is part of
`uq_ledger_atom`, so a cursor that is rewound (or deleted and recreated) re-reads rows
that are already in the ledger, and they land AGAIN under the new fingerprint instead of
deduping against the old ones. The statement under this therefore changes the fingerprint
string and NOTHING else: not the position, not the counters, not one atom. Rows already
stored keep the fingerprint they were written under -- a ledger appends.

    conda run -n assy_manager python scripts/ledger_restamp_cursor.py            # report
    conda run -n assy_manager python scripts/ledger_restamp_cursor.py --apply    # write

Reports by default; `--apply` is the only thing that writes.

Runs on a config that does not compile whole: a source being authored is dropped, named on
stdout, and the sources that DO compile are re-stamped anyway. There is no bypass flag --
a dropped source has no fingerprint to want and no cursor to move.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)


def main(argv=None):
    from database.database import engine
    from ledger.config_explorer import load_resolved_setup
    from ledger.setup import (
        DEFAULT_ONTOLOGY_ROOT, live_physical_catalog, load_setup,
        setup_from_document,
    )
    from ledger.setup_registry import cursor_translator_version
    from ledger.store import LedgerStore

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=None,
                        help="one source id; default is every declared source")
    parser.add_argument("--apply", action="store_true",
                        help="write the new fingerprint (otherwise report only)")
    parser.add_argument("--ontology-root", default=str(DEFAULT_ONTOLOGY_ROOT))
    args = parser.parse_args(argv)

    # 🔴 A HALF-BUILT SOURCE MUST NOT BLOCK AN OPERATIONAL COMMAND.  `load_setup` refuses
    # the WHOLE bundle when any one declaration does not compile, and a half-written source
    # is the normal state of the authoring screen while somebody is using it -- so this
    # command was unrunnable exactly when a cursor most needed re-stamping.  Measured
    # 2026-08-22: `bundle.sources.transter_event.bind.mappings` raised here, before the
    # script reached a single cursor.
    #
    # The resolver below is `OntologyExplorerService._resolution`'s, copied rather than
    # reinvented: the whole-config load is tried FIRST and takes exactly the path it always
    # took, and the tolerant read runs only when that refuses.  A source that cannot compile
    # has no plan, therefore no fingerprint to want, and in practice no cursor either --
    # nothing has ever run it.  It is named on stdout rather than skipped, because an
    # operator reading "2 sources" needs to know whether that was 2 of 2 or 2 of 3.
    root = args.ontology_root
    try:
        setup = load_setup(root)
        dropped = {}
    except Exception as exc:                                     # noqa: BLE001
        catalog = live_physical_catalog()
        resolved = load_resolved_setup(
            root, catalog=catalog,
            setup_from_document=lambda doc: setup_from_document(
                doc, config_root=root, catalog=catalog))
        setup = resolved["setup"]
        dropped = resolved["invalid"]
        print(f"config does not compile whole ({exc}); "
              f"reading what resolves and naming what does not")
    for key in sorted(dropped):
        reasons = dropped[key].get("reasons") or []
        first = reasons[0].get("path") if reasons else "?"
        print(f"  DROPPED {key.partition('|')[2] or key} -- not compiled, "
              f"no fingerprint to re-stamp ({first})")
    sources = ([args.source] if args.source
               else sorted(setup.snapshot.source_plans))
    # Only reachable through `--source`: the default list IS `source_plans`, so it cannot
    # name something absent from it.  Named-and-dropped therefore leaves nothing to do.
    unknown = [s for s in sources if s not in setup.snapshot.source_plans]
    if unknown:
        print(f"{', '.join(unknown)}: REFUSED -- not among the sources that compiled; "
              f"finish the declaration first")
        return 1
    store = LedgerStore(engine)
    read = store.connection()
    try:
        rows = {source: store.read_cursor(read, source) for source in sources}
    finally:
        read.close()

    exit_code = 0
    for source in sources:
        wanted = cursor_translator_version(setup.snapshot, source)
        existing = rows[source]
        if existing is None:
            print(f"{source}: no cursor row -- nothing to re-stamp "
                  f"(a first run writes {wanted})")
            continue
        stored = existing.get("translator_ver")
        if stored == wanted:
            print(f"{source}: already {wanted}")
            continue
        if not str(stored or "").startswith("ledger-v2:"):
            # A v1-shaped cursor is a DIFFERENT problem and a different gate
            # (`legacy_cursor_reset_required`, on `cursor_value`'s shape). Re-stamping it
            # would hide that gate behind a v2-looking string while the position stays
            # v1-shaped, so it is refused by name instead.
            print(f"{source}: REFUSED -- stored cursor is not a v2 cursor "
                  f"({stored!r}); its shape gate is a separate decision")
            exit_code = 1
            continue
        print(f"{source}: {stored}\n{'':>{len(source) + 2}}-> {wanted}")
        print(f"{'':>{len(source) + 2}}position stays {existing.get('cursor_value')!r}")
        if args.apply:
            moved = store.restamp_cursor(
                source, expect=stored, translator_ver=wanted)
            print(f"{'':>{len(source) + 2}}"
                  f"{'re-stamped' if moved else 'NOT re-stamped (row changed under us)'}")
            if not moved:
                exit_code = 1
    if not args.apply:
        print("\n(report only -- pass --apply to write)")
    return exit_code


if __name__ == "__main__":                                       # pragma: no cover
    sys.exit(main())
