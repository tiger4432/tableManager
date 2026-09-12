# -*- coding: utf-8 -*-
"""A parser that ships beside its own sample, so the repository sample needs no workspace.

⚠️ IT IS A SAMPLE, NOT A PRODUCTION PARSER. It exists so `dev_bench.try_parser` has something
to CLAIM in a checkout: the real parsers live in the operator's gitignored workspace, so a
sample that pointed at one would pass on one machine and skip on every other.

🔴 IT SUBCLASSES `BasePipelineParser` AND IMPLEMENTS `process_dataframe`, which is the
production contract -- `scan_workspace_pipeline_parsers` offers only subclasses, and a sample
that faked the shape would let the bench pass on a parser the watcher would never load.
"""
import os

from parsers.pipeline_base import BasePipelineParser


class BenchVoidParser(BasePipelineParser):
    """Claims `input.txt` beside it and keeps the four columns it declares."""

    @classmethod
    def match(cls, file_path):
        return os.path.basename(file_path) == "input.txt"

    def process_dataframe(self, df):
        df = df.rename(columns={c: c.strip() for c in df.columns})
        return df[["wafer", "x", "y", "kind"]]
