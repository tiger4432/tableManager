"""One-shot: fold a five-file ontology root into one ``ledger_config.json``.

    conda run -n assy_manager python server/scripts/convert_ontology_to_single_file.py \
        --root server/config/ontology --out /somewhere/ledger_config.json

🔴 IT NEVER DELETES ANYTHING. It reads the old root, writes ONE new file wherever you point
it, and prints what moved where. The originals are still there afterwards, which is
deliberate: the swap is the operator's move to make after the atom diff is checked, not the
converter's. Note that this means the OLD ROOT DOES NOT LOAD while both exist -- the new
loader refuses a root holding any JSON but the one file, by name (`unlisted_config_file`).
That refusal is the single-file promise doing its job, not a failure of this script; write
the output to a fresh directory and point the loader there.

🔴 IT REFUSES RATHER THAN DROPS. Three sections have no home in the target shape. If any of
them holds something, this script names it and stops instead of quietly leaving it behind.
The retiring execution selector is the one exception, and only in its retiring form: a
selector that says `mode: "v2"` is saying what the target shape says by default, so folding
it away changes nothing. A selector saying anything ELSE is a decision somebody made that
would silently invert -- a source marked `legacy` would START RUNNING the moment the switch
disappears, because declaration becomes activation. That is refused.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SETUP_VERSION = 3
RETIRING_SELECTOR = "ledger_v2_execution"

#: target section -> (old file, key inside it)
MOVES = (
    ("tables", "catalog/tables.json", "tables"),
    ("vocabulary", "ledger_config.json", "vocabulary"),
    ("entities", "ledger_config.json", "entities"),
    ("packs", "ledger_config.json", "packs"),
    ("source_preparers", "ledger_config.json", "source_preparers"),
    ("mappers", "ledger_config.json", "mappers"),
    ("profiles", "ledger_config.json", "profiles"),
    ("sources", "ledger_config.json", "sources"),
)


class Refused(SystemExit):
    def __init__(self, what: str, detail: str):
        super().__init__(f"REFUSED: {what}\n  {detail}\n"
                         f"  Nothing was written. Decide what happens to it first.")


def _read(root: Path, relative: str) -> dict:
    path = root / relative
    if not path.exists():
        raise Refused(f"{relative} is missing",
                      f"expected it under {root}; this converter reads a five-file root")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_retiring_selector(chains: dict, report: list) -> None:
    declarations = {k: v for k, v in chains.items() if k != RETIRING_SELECTOR}
    if declarations:
        raise Refused(
            f"dataflows/chains.json declares {sorted(declarations)}",
            "only the retiring execution selector can be folded away; these are "
            "something else and the target shape has no section for them")
    selector = chains.get(RETIRING_SELECTOR) or {}
    for source_id, item in sorted((selector.get("sources") or {}).items()):
        mode = (item or {}).get("mode")
        if mode != "v2":
            raise Refused(
                f"source {source_id!r} is selected as mode={mode!r}, not 'v2'",
                "declaration becomes activation, so dropping the selector would START "
                "this source rather than leave it off. Remove it from `sources`, or "
                "decide explicitly that it should run.")
        report.append((f"chains.{RETIRING_SELECTOR}.sources.{source_id}",
                       "(dropped)", f"mode={mode}, parity={item.get('parity_status')!r}"))


def convert(root: Path, out: Path, *, force: bool) -> dict:
    ledger = _read(root, "ledger_config.json")
    tables = _read(root, "catalog/tables.json")
    joins = _read(root, "catalog/virtual_joins.json")
    chains = _read(root, "dataflows/chains.json")
    enrichments = _read(root, "dataflows/enrichments.json")

    report: list[tuple[str, str, str]] = []

    if enrichments.get("enrichments"):
        raise Refused(
            f"dataflows/enrichments.json declares "
            f"{sorted(enrichments['enrichments'])}",
            "the target shape has no enrichments section and nothing consumed it")
    report.append(("dataflows/enrichments.json", "(dropped)", "empty"))

    _check_retiring_selector(chains.get("chains") or {}, report)

    document: dict = {"setup_version": SETUP_VERSION}
    for section, source_file, key in MOVES:
        source = ledger if source_file == "ledger_config.json" else tables
        if key not in source:
            raise Refused(f"{source_file} has no {key!r}",
                          "the source root is not the shape this converter reads")
        document[section] = source[key]
        report.append((f"{source_file}:{key}", f"{section}", f"{len(source[key])} item(s)"))

    # `virtual_joins` is CARRIED, not dropped, when it holds anything. The refuse-rather-
    # than-drop rule exists to stop silent loss, and the loader keeps an optional section
    # for exactly this -- so carrying it forward loses nothing and needs no ruling.
    rules = joins.get("rules") or {}
    if rules:
        document["virtual_joins"] = rules
        report.append(("catalog/virtual_joins.json:rules", "virtual_joins",
                       f"{len(rules)} rule(s) CARRIED (optional section)"))
    else:
        report.append(("catalog/virtual_joins.json", "(dropped)", "empty"))

    for name in ("schema_version",):
        if name in ledger:
            report.append((f"ledger_config.json:{name}", "(dropped)",
                           f"{ledger[name]!r} -> setup_version {SETUP_VERSION}"))

    if out.exists() and not force:
        raise Refused(f"{out} already exists",
                      "pass --force only if you are sure you want to overwrite it")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"document": document, "report": report}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="existing five-file ontology root")
    parser.add_argument("--out", required=True, help="path of the NEW single file")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve(strict=True)
    out = Path(args.out).resolve()
    result = convert(root, out, force=args.force)

    width = max(len(row[0]) for row in result["report"])
    print(f"read : {root}")
    print(f"wrote: {out}   (originals left in place)")
    print()
    print(f"{'FROM'.ljust(width)}  ->  {'TO'.ljust(18)}  NOTE")
    print(f"{'-' * width}  --  {'-' * 18}  {'-' * 30}")
    for source, target, note in result["report"]:
        print(f"{source.ljust(width)}  ->  {target.ljust(18)}  {note}")
    print()
    print(f"sections written: {len(result['document']) - 1} + setup_version")
    print("The old root does NOT load while its other JSON files remain -- that is the "
          "single-file rule, not a fault. Point the loader at the new file's directory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
