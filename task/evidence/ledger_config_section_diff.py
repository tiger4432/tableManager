"""Compare a pre-conversion 5-file config root with the post-conversion single file.

The atom diff proves the ledger still SAYS the same thing.  This proves nothing was
DROPPED on the way -- a section that quietly disappears takes its declarations with it
and the atom diff stays green as long as the surviving sources still translate.

Usage:
  python ledger_config_section_diff.py <old_root_dir> <new_ledger_config.json>
"""
import json, sys, pathlib

sys.stdout.reconfigure(encoding='utf-8')

# logical section -> (relative file, key inside that file)
OLD_LAYOUT = {
    "vocabulary":       ("ledger_config.json", "vocabulary"),
    "entities":         ("ledger_config.json", "entities"),
    "source_preparers": ("ledger_config.json", "source_preparers"),
    "mappers":          ("ledger_config.json", "mappers"),
    "packs":            ("ledger_config.json", "packs"),
    "profiles":         ("ledger_config.json", "profiles"),
    "sources":          ("ledger_config.json", "sources"),
    "tables":           ("catalog/tables.json", "tables"),
    "virtual_joins":    ("catalog/virtual_joins.json", "rules"),
    "chains":           ("dataflows/chains.json", "chains"),
    "enrichments":      ("dataflows/enrichments.json", "enrichments"),
}
# Sections retired by the single-file transition.  `chains` is EXPECTED to hold the
# execution selector and to lose it -- that was the ruling, so its content is announced
# rather than counted as a fault.  The other two were measured empty and unusable; if
# either arrives carrying something, somebody wrote a declaration that is about to be
# thrown away silently, and that is a fault.
RETIRED = {"virtual_joins", "chains", "enrichments"}
EXPECTED_DROP = {"chains"}


def _load(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))


def main():
    old_root = pathlib.Path(sys.argv[1])
    new_file = pathlib.Path(sys.argv[2])
    new = _load(new_file)

    old = {}
    for section, (rel, key) in OLD_LAYOUT.items():
        path = old_root / rel
        if not path.exists():
            print(f"  ! old root is missing {rel} - cannot compare {section}")
            continue
        old[section] = _load(path).get(key, {})

    problems = 0
    print(f"old root : {old_root}")
    print(f"new file : {new_file}")
    print(f"new sections: {sorted(k for k in new if not k.startswith('_'))}")
    print()

    for section in sorted(OLD_LAYOUT):
        before = old.get(section)
        after = new.get(section)
        if section in RETIRED:
            if not before:
                state = "retired (old root was empty - nothing lost)"
            elif section in EXPECTED_DROP:
                state = f"retired BY RULING - dropped: {sorted(before)}"
            else:
                state = (f"RETIRED but the old root DECLARED {sorted(before)} "
                         "- refuse the conversion rather than drop these")
                problems += 1
            print(f"  {section:18s} {state}")
            continue
        if after is None:
            print(f"  {section:18s} MISSING from the new file "
                  f"(old had {len(before or {})})")
            problems += 1
            continue
        if before == after:
            print(f"  {section:18s} identical ({len(after)})")
            continue
        problems += 1
        lost = sorted(set(before or {}) - set(after or {}))
        gained = sorted(set(after or {}) - set(before or {}))
        changed = sorted(k for k in set(before or {}) & set(after or {})
                         if before[k] != after[k])
        print(f"  {section:18s} DIFFERS  lost={lost} gained={gained} changed={changed}")

    print()
    print("SECTION DIFF:", problems, "(0 이면 통과)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
