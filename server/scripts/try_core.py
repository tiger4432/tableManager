# -*- coding: utf-8 -*-
"""S-192 shell ①. Run a mapper or a parser from the command line, print the TSV.

    python scripts/try_core.py mapper  <name> <sample.csv>
    python scripts/try_core.py parser  <file> [--force File.py::Class] [--scripts DIR]
    python scripts/try_core.py folder  tests/samples/parser/void_lines

🔴 IT ASSEMBLES NOTHING ITSELF. Every form goes through `dev_bench`, and the `folder` form
goes through the SAME `run_sample_folder` the pytest fixture uses -- so 「it works from the
command line」 and 「the test passes」 cannot become different facts about one mapper.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dev_bench                                                     # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(prog="try_core", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="kind", required=True)

    one = sub.add_parser(dev_bench.MAPPER, help="run a mapper over a sample")
    one.add_argument("name", help="a registered mapper name, or module:function")
    one.add_argument("sample", help="input .csv / .tsv / .json")

    two = sub.add_parser(dev_bench.PARSER, help="parse one file the way production would")
    two.add_argument("file")
    two.add_argument("--force", default=None,
                     help="run this parser even if its match() does not claim the file")
    two.add_argument("--scripts", default=None, help="parser workspace directory")

    three = sub.add_parser("folder", help="run a sample folder (the pytest unit)")
    three.add_argument("folder")

    args = parser.parse_args(argv)
    if args.kind == dev_bench.MAPPER:
        result = dev_bench.try_mapper(args.name, args.sample)
    elif args.kind == dev_bench.PARSER:
        result = dev_bench.try_parser(args.file, force=args.force,
                                      scripts_path=args.scripts)
    else:
        result = dev_bench.run_sample_folder(args.folder)

    if result["refusal"]:
        # ⚠️ TO stderr AND A NON-ZERO EXIT, so a shell loop or CI notices. A refusal printed
        # to stdout would be indistinguishable from a result with no rows.
        sys.stderr.write("REFUSED (%s): %s\n" % (result["who"], result["refusal"]))
        return 2
    sys.stderr.write("%s: %s -> %d row(s)\n"
                     % (args.kind, result["who"], len(result["rows"])))
    sys.stdout.write(dev_bench.rows_to_tsv(result["rows"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
