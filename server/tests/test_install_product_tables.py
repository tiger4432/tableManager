"""Verification for server/scripts/install_product_tables.py.

The script writes to the operator's live ``table_config.json`` -- a gitignored
user asset. Every test here works on a copy under pytest's ``tmp_path``; nothing
in this file reads or writes ``server/config/table_config.json``.

Each branch of the merge gets a case that actually reaches it:

  * absent product entries          -> added
  * already correct                 -> byte-identical, no backup, exit 0
  * unusual site-owned declaration  -> byte-identical
  * operator-modified product entry -> drift, not overwritten without the flag
  * run twice                       -> second run writes nothing

Preservation and no-op are proved by comparing bytes, not by eyeballing JSON.
"""
import io
import json
import os
import re
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(SERVER_DIR, "scripts")
for _p in (SERVER_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import install_product_tables as ipt  # noqa: E402
import product_tables  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def write(path, text, encoding="utf-8", bom=False):
    payload = text.encode(encoding)
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    with open(path, "wb") as f:
        f.write(payload)
    return path


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def run(path, **kw):
    """Invoke the script and return (exit_code, report_text)."""
    buf = io.StringIO()
    code = ipt.run(str(path), out=buf, **kw)
    return code, buf.getvalue()


def backups(tmp_path):
    root = tmp_path / "backup"
    if not root.is_dir():
        return []
    return sorted(str(p.relative_to(tmp_path)) for p in root.iterdir()
                  if ".bak." in p.name)


# A site-owned declaration that is deliberately awkward: keys in a non-standard
# order, an extra key the product knows nothing about, its own comment key,
# 4-space indent inside a 2-space file, a one-line array, and slack whitespace
# around the colons. None of it may change.
UNUSUAL_SITE_ENTRY = '''  "pti_site_log" :  {
        "display_columns": ["lot_id","slot","result"],
        "__note": "site-owned; hand-edited on purpose",
        "business_key"    : "lot_id",
        "harvest_window_days": 30,
        "column_types": {
            "lot_id": "string",
            "slot"  : "number",
            "result": "string"
        }
    }'''


def config_with_site_only(tmp_path, name="table_config.json", newline="\r\n"):
    text = "{" + newline + UNUSUAL_SITE_ENTRY.replace("\n", newline) + newline + "}" + newline
    return write(tmp_path / name, text)


# ---------------------------------------------------------------------------
# 1. fresh config, no product entries -> every declared table added
#
# [2026-08-13] The single-entry fixtures below used to poke `map_doe`; that table
# and `map_doe_source` were dropped, so they now poke `map_split_registry` and
# `valid_die_ref`. Nothing about what is being verified changed -- these tests
# need *a* product entry, not that particular one. The set-level assertions
# (`test_empty_object_gets_every_product_table`) are keyed off PRODUCT_TABLES and
# so followed the retirement on their own; they are the ones that pin "the
# installer creates exactly the declared set" and they are kept, not weakened.
# ---------------------------------------------------------------------------

class TestFreshConfig:
    def test_empty_object_gets_every_product_table(self, tmp_path):
        path = write(tmp_path / "table_config.json", "{}\n")
        code, report = run(path, apply_mode=True)

        assert code == 0, report
        parsed = json.loads(read_bytes(path).decode("utf-8"))
        assert list(parsed.keys()) == list(product_tables.PRODUCT_TABLES.keys())
        for name, entry in product_tables.PRODUCT_TABLES.items():
            assert parsed[name] == entry

    def test_site_only_config_gains_product_tables_and_keeps_the_site_entry(self, tmp_path):
        path = config_with_site_only(tmp_path)
        before = read_bytes(path)

        code, report = run(path, apply_mode=True)
        assert code == 0, report

        after = read_bytes(path)
        parsed = json.loads(after.decode("utf-8"))
        assert set(parsed) == {"pti_site_log"} | set(product_tables.PRODUCT_TABLES)
        # the site entry's own bytes survived verbatim
        assert UNUSUAL_SITE_ENTRY.replace("\n", "\r\n") in after.decode("utf-8")
        # and it is still the first member, in its original position
        assert after.decode("utf-8").index("pti_site_log") < after.decode("utf-8").index("wafer_map_metadata")
        assert len(after) > len(before)

    def test_dry_run_is_the_default_and_writes_nothing(self, tmp_path):
        path = write(tmp_path / "table_config.json", "{}\n")
        before = read_bytes(path)

        code, report = run(path)
        assert code == 1, "pending additions must be reported as action-required"
        assert read_bytes(path) == before
        assert backups(tmp_path) == []
        assert "DRY RUN" in report

    def test_added_declaration_uses_the_file_line_ending(self, tmp_path):
        crlf = config_with_site_only(tmp_path, newline="\r\n")
        run(crlf, apply_mode=True)
        body = read_bytes(crlf)
        assert b"\n" in body and body.count(b"\r\n") == body.count(b"\n"), "must stay pure CRLF"

        lf = config_with_site_only(tmp_path, name="lf.json", newline="\n")
        run(lf, apply_mode=True)
        assert b"\r" not in read_bytes(lf), "must stay pure LF"

    def test_indent_unit_is_taken_from_the_file(self, tmp_path):
        text = '{\n    "pti_site_log": {\n        "business_key": "lot_id"\n    }\n}\n'
        path = write(tmp_path / "table_config.json", text)
        run(path, apply_mode=True)
        body = read_bytes(path).decode("utf-8")
        assert '\n    "map_split_registry": {\n' in body
        assert '\n        "business_key": "split_key",\n' in body

    def test_missing_file_is_an_error_and_creates_nothing(self, tmp_path):
        path = tmp_path / "nope.json"
        code, report = run(path, apply_mode=True)
        assert code == 2
        assert not path.exists()
        assert "does not exist" in report


# ---------------------------------------------------------------------------
# 2. already correct -> byte-identical, exit clean
# 3. unusual site-owned entry -> byte-identical
# 5. run twice -> second run is a no-op
# ---------------------------------------------------------------------------

class TestNoOpAndPreservation:
    @pytest.fixture
    def installed(self, tmp_path):
        path = config_with_site_only(tmp_path)
        code, _ = run(path, apply_mode=True)
        assert code == 0
        for b in backups(tmp_path):
            os.remove(tmp_path / b)
        return path

    def test_apply_on_a_correct_config_is_byte_identical(self, installed, tmp_path):
        before = read_bytes(installed)
        code, report = run(installed, apply_mode=True)

        assert code == 0, report
        assert read_bytes(installed) == before, "a no-op run must not change one byte"
        assert backups(tmp_path) == [], "a no-op run must not leave a backup"
        assert "nothing to write" in report

    def test_running_twice_changes_nothing_the_second_time(self, tmp_path):
        path = config_with_site_only(tmp_path)
        run(path, apply_mode=True)
        after_first = read_bytes(path)

        code, _ = run(path, apply_mode=True)
        assert code == 0
        assert read_bytes(path) == after_first

    def test_unusual_site_entry_survives_byte_for_byte(self, tmp_path):
        path = config_with_site_only(tmp_path)
        original = read_bytes(path).decode("utf-8")
        site_span = original[original.index('  "pti_site_log"'):original.rindex("\r\n}")]

        code, report = run(path, apply_mode=True)

        # The exit code matters as much as the bytes: the post-write guard
        # restores the original on a reformat, so a merge that mangles the file
        # would still leave the site entry intact here and pass vacuously.
        assert code == 0, report
        after = read_bytes(path).decode("utf-8")

        assert site_span in after, "the site-owned entry was reformatted"
        parsed = json.loads(after)
        assert parsed["pti_site_log"]["harvest_window_days"] == 30
        assert parsed["pti_site_log"]["__note"] == "site-owned; hand-edited on purpose"
        assert list(parsed["pti_site_log"].keys()) == [
            "display_columns", "__note", "business_key", "harvest_window_days", "column_types"
        ], "site key order must not be normalised"

    def test_utf8_bom_is_preserved(self, tmp_path):
        path = write(tmp_path / "table_config.json", "{}\r\n", bom=True)
        code, report = run(path, apply_mode=True)
        assert code == 0, report
        body = read_bytes(path)
        assert body.startswith(b"\xef\xbb\xbf")
        assert (json.loads(body.decode("utf-8-sig"))["map_split_registry"]
                == product_tables.PRODUCT_TABLES["map_split_registry"])

    def test_comment_reworded_in_config_is_not_drift(self, tmp_path):
        """Annotations cannot change behaviour, so they must not flag an operator."""
        cfg = {name: dict(entry) for name, entry in product_tables.PRODUCT_TABLES.items()}
        cfg["map_split_registry"]["__comment"] = "our own note"
        del cfg["valid_die_ref"]["__comment"]
        path = write(tmp_path / "table_config.json", json.dumps(cfg, indent=2, ensure_ascii=False))

        code, report = run(path, apply_mode=True)
        assert code == 0, report
        assert "DRIFT" not in report
        assert (json.loads(read_bytes(path).decode("utf-8"))["map_split_registry"]["__comment"]
                == "our own note")

    def test_sync_comments_makes_a_stale_comment_actionable(self, tmp_path):
        """A comment cannot change behaviour, but it can actively mislead.

        The case this was written for: `map_doe`'s live comment still told an operator
        that `plan_store.doe` points at it, months after that binding was retired.
        (That table has since been dropped, so the fixture below uses a live one --
        the hazard is the stale text, not the table.) Ignoring comment drift is right
        by default -- the operator may have annotated it -- but there has to be a way
        to refresh one, and it has to be opt-in and visible in the report.
        """
        cfg = {name: dict(entry) for name, entry in product_tables.PRODUCT_TABLES.items()}
        cfg["map_split_registry"]["__comment"] = "stale: plan_store.doe points here"
        path = write(tmp_path / "table_config.json", json.dumps(cfg, indent=2, ensure_ascii=False))

        def live_comment():
            return json.loads(read_bytes(path).decode("utf-8"))["map_split_registry"]["__comment"]

        # default: invisible, and nothing is written
        code, report = run(path, apply_mode=True, overwrite_drift=True)
        assert code == 0 and "DRIFT" not in report
        assert live_comment().startswith("stale")

        # opt-in: reported as drift, and still not written without --overwrite-drift
        code, report = run(path, strict=True)
        assert code == 1 and "DRIFT" in report and "__comment" in report
        assert live_comment().startswith("stale")

        # opt-in + overwrite: replaced with the product text
        code, report = run(path, apply_mode=True, overwrite_drift=True, strict=True)
        assert code == 0, report
        assert live_comment() == product_tables.PRODUCT_TABLES["map_split_registry"]["__comment"]

    def test_sync_comments_leaves_site_entries_byte_identical(self, tmp_path):
        """The comment path must not become a licence to reformat the operator's file."""
        cfg = {"pti_site_log": {"business_key": "lot_id", "column_types": {"lot_id": "string"}}}
        for name, entry in product_tables.PRODUCT_TABLES.items():
            cfg[name] = dict(entry)
        cfg["map_split_registry"]["__comment"] = "stale"
        path = write(tmp_path / "table_config.json", json.dumps(cfg, indent=2, ensure_ascii=False))
        before = read_bytes(path).decode("utf-8")
        site_span = before[before.index('"pti_site_log"'):before.index('"wafer_map_metadata"')]

        code, _ = run(path, apply_mode=True, overwrite_drift=True, strict=True)
        assert code == 0
        after = read_bytes(path).decode("utf-8")
        assert site_span in after


# ---------------------------------------------------------------------------
# 4. operator-modified product entry -> drift
# ---------------------------------------------------------------------------

def _config_with_modified_product_entry(tmp_path, mutate):
    cfg = {"pti_site_log": {"business_key": "lot_id"}}
    for name, entry in product_tables.PRODUCT_TABLES.items():
        cfg[name] = json.loads(json.dumps(entry))
    mutate(cfg)
    return write(tmp_path / "table_config.json", json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


class TestDrift:
    def test_changed_separator_is_blocking_drift_and_is_not_overwritten(self, tmp_path):
        def mutate(cfg):
            cfg["map_split_registry"]["composite_key_separator"] = "_"
        path = _config_with_modified_product_entry(tmp_path, mutate)
        before = read_bytes(path)

        code, report = run(path, apply_mode=True)

        assert code == 1, "a blocking drift leaves work outstanding"
        assert read_bytes(path) == before, "drift must not be touched without the flag"
        assert backups(tmp_path) == []
        assert "DRIFT" in report and "BLOCKING" in report
        assert "composite_key_separator" in report
        assert '"_"' in report and '"|"' in report, "the report must show both values"

    def test_dropped_column_is_blocking_drift(self, tmp_path):
        def mutate(cfg):
            del cfg["map_split_registry"]["column_types"]["stack"]
        path = _config_with_modified_product_entry(tmp_path, mutate)

        code, report = run(path, apply_mode=True)
        assert code == 1
        assert "missing  column_types.stack" in report

    def test_operator_added_column_is_additive_not_blocking(self, tmp_path):
        """A superset must never be reported as blocking.

        If it were, operators would learn to reach for --overwrite-drift, and
        that flag would then delete the columns they added.
        """
        def mutate(cfg):
            cfg["map_split_registry"]["column_types"]["site_tag"] = "string"
            cfg["map_split_registry"]["display_columns"].append("site_tag")
        path = _config_with_modified_product_entry(tmp_path, mutate)
        before = read_bytes(path)

        code, report = run(path, apply_mode=True)

        assert code == 0, "additive drift is not an outstanding action"
        assert read_bytes(path) == before
        assert "additive" in report
        assert "BLOCKING" not in report
        assert "extra    column_types.site_tag" in report

    def test_reordered_display_columns_is_blocking(self, tmp_path):
        """Order carries meaning; only an in-order superset counts as additive."""
        def mutate(cfg):
            cfg["map_split_registry"]["display_columns"].reverse()
        path = _config_with_modified_product_entry(tmp_path, mutate)

        code, report = run(path, apply_mode=True)
        assert code == 1
        assert "changed  display_columns" in report

    def test_extra_component_in_composite_key_is_blocking(self, tmp_path):
        """composite_key_source is the business key -- appending is not additive."""
        def mutate(cfg):
            cfg["map_split_registry"]["composite_key_source"].append("split_desc")
        path = _config_with_modified_product_entry(tmp_path, mutate)

        code, report = run(path, apply_mode=True)
        assert code == 1, "a business-key change must never be classed as additive"
        assert "changed  composite_key_source" in report

    def test_overwrite_drift_flag_replaces_the_entry(self, tmp_path):
        def mutate(cfg):
            cfg["map_split_registry"]["composite_key_separator"] = "_"
            cfg["map_split_registry"]["column_types"]["site_tag"] = "string"
        path = _config_with_modified_product_entry(tmp_path, mutate)

        code, report = run(path, apply_mode=True, overwrite_drift=True)

        assert code == 0, report
        parsed = json.loads(read_bytes(path).decode("utf-8"))
        assert parsed["map_split_registry"] == product_tables.PRODUCT_TABLES["map_split_registry"]
        assert ("site_tag" not in parsed["map_split_registry"]["column_types"]), \
            "a full replacement drops extras"
        assert parsed["pti_site_log"] == {"business_key": "lot_id"}, "site entry untouched"
        assert len(backups(tmp_path)) == 1

    def test_overwrite_drift_leaves_site_entries_byte_identical(self, tmp_path):
        path = config_with_site_only(tmp_path)
        run(path, apply_mode=True)
        for b in backups(tmp_path):
            os.remove(tmp_path / b)

        text = read_bytes(path).decode("utf-8")
        site_span = text[text.index('  "pti_site_log"'):text.index('  "wafer_map_metadata"')]
        # now drift one product entry and repair it
        parsed = json.loads(text)
        parsed["map_split_registry"]["business_key"] = "hacked"
        write(path, json.dumps(parsed, indent=2, ensure_ascii=False))
        rewritten = read_bytes(path).decode("utf-8")
        site_span2 = rewritten[rewritten.index('  "pti_site_log"'):rewritten.index('  "wafer_map_metadata"')]

        code, _ = run(path, apply_mode=True, overwrite_drift=True)
        assert code == 0
        final = read_bytes(path).decode("utf-8")
        assert site_span2 in final, "repairing a product entry must not disturb its neighbours"
        assert json.loads(final)["map_split_registry"] == product_tables.PRODUCT_TABLES["map_split_registry"]
        assert site_span  # sanity: the pre-drift span was captured


# ---------------------------------------------------------------------------
# backup / write mechanics
# ---------------------------------------------------------------------------

class TestWriteMechanics:
    def test_backup_holds_the_original_bytes(self, tmp_path):
        path = config_with_site_only(tmp_path)
        before = read_bytes(path)

        code, report = run(path, apply_mode=True)
        assert code == 0

        names = backups(tmp_path)
        assert len(names) == 1
        assert read_bytes(tmp_path / names[0]) == before
        assert names[0] in report, "the operator must be told where the backup went"

    def test_write_is_in_place_not_temp_plus_rename(self, tmp_path, monkeypatch):
        """The config watcher only handles on_modified.

        An atomic temp+rename does not raise that event, which is exactly how
        runtime ALTERs get silently skipped (CONFIG_GUIDE 6.B). Blowing up
        os.replace/os.rename proves this writer does not take that route.
        """
        def boom(*a, **kw):
            raise AssertionError("writer used an atomic rename; the config watcher would not fire")

        monkeypatch.setattr(os, "replace", boom)
        monkeypatch.setattr(os, "rename", boom)

        path = config_with_site_only(tmp_path)
        code, _ = run(path, apply_mode=True)
        assert code == 0
        assert json.loads(read_bytes(path).decode("utf-8"))["map_split_registry"]

    def test_no_stray_files_beyond_the_backup(self, tmp_path):
        path = config_with_site_only(tmp_path)
        code, report = run(path, apply_mode=True)
        assert code == 0, report
        assert set(os.listdir(tmp_path)) == {"table_config.json", "backup"}
        assert len(backups(tmp_path)) == 1

    def test_the_script_opens_no_database(self):
        """A config installer that issued DDL as a side effect would be a hazard.

        Checked on the import graph, not on substrings: the script's own text
        mentions CREATE/ALTER when telling the operator what to do next.
        """
        import ast
        tree = ast.parse(io.open(ipt.__file__, encoding="utf-8").read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported <= {"argparse", "codecs", "json", "os", "sys", "collections",
                            "datetime", "paths", "config_backup", "product_tables"}, \
            sorted(imported)


class TestMalformedInput:
    def test_invalid_json_is_refused_and_the_file_is_untouched(self, tmp_path):
        path = write(tmp_path / "table_config.json", '{"a": {,}}')
        before = read_bytes(path)

        code, report = run(path, apply_mode=True)
        assert code == 2
        assert read_bytes(path) == before
        assert backups(tmp_path) == []
        assert "cannot read" in report

    def test_duplicate_top_level_key_is_refused(self, tmp_path):
        path = write(tmp_path / "table_config.json", '{\n  "a": {"x": 1},\n  "a": {"x": 2}\n}\n')
        before = read_bytes(path)

        code, report = run(path, apply_mode=True)
        assert code == 2
        assert read_bytes(path) == before
        assert "duplicate" in report

    def test_top_level_array_is_refused(self, tmp_path):
        path = write(tmp_path / "table_config.json", "[]")
        code, report = run(path, apply_mode=True)
        assert code == 2
        assert "JSON object" in report


# ---------------------------------------------------------------------------
# the single-definition guarantee
# ---------------------------------------------------------------------------

class TestSingleDefinition:
    """server/product_tables.py is the one list; the sample is derived from it.

    If this fails, regenerate the template:
        python server/scripts/install_product_tables.py --sample --apply --overwrite-drift
    """

    def test_sample_product_section_equals_the_module(self):
        with io.open(ipt.SAMPLE_PATH, encoding="utf-8") as f:
            sample = json.load(f)
        for name, entry in product_tables.PRODUCT_TABLES.items():
            assert name in sample, f"{name} missing from table_config.json.sample"
            assert sample[name] == entry, f"{name} in the sample has drifted from product_tables.py"

    def test_sample_needs_no_changes(self):
        code, report = run(ipt.SAMPLE_PATH, strict=True)
        assert code == 0, report

    def test_no_other_module_hard_codes_these_declarations(self):
        """A second copy of the list is the defect this design exists to prevent."""
        offenders = []
        for root, dirs, files in os.walk(SERVER_DIR):
            dirs[:] = [d for d in dirs
                       if d not in {"__pycache__", "config", "ingestion_workspace", "tests", "scratch", "archive"}]
            for fn in files:
                if not fn.endswith(".py") or fn in ("product_tables.py", "install_product_tables.py"):
                    continue
                full = os.path.join(root, fn)
                try:
                    body = io.open(full, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                # a real second declaration pairs the table name with its business key
                for name, entry in product_tables.PRODUCT_TABLES.items():
                    if f'"{name}"' in body and f'"{entry["business_key"]}"' in body \
                            and '"composite_key_source"' in body:
                        offenders.append(f"{full} redeclares {name}")
        assert not offenders, offenders


CLIENT_SRC = os.path.abspath(os.path.join(SERVER_DIR, "..", "client2", "src"))


_IDENT_START = re.compile(r"[A-Za-z_$]")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def _scan_js(text, i, stop_at_depth_zero_close=False):
    """Walk JS source from ``i``, yielding (index, char, depth, is_code).

    Handles single/double/template quotes and both comment styles, so a brace
    inside a string or a comment cannot be mistaken for structure.
    """
    depth, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            quote, i = c, i + 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    break
                i += 1
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.find("\n", i)
            if i == -1:
                return
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if c in "{[(":
            depth += 1
            yield i, c, depth, True
            i += 1
            continue
        if c in "}])":
            yield i, c, depth, True
            depth -= 1
            if stop_at_depth_zero_close and depth == 0:
                return
            i += 1
            continue
        yield i, c, depth, True
        i += 1


def _extract_updates_literals(text):
    """Every ``updates: { ... }`` object literal in a JS source, as key lists.

    Hand-written rather than a JS parser because the shape needed is narrow.
    Two things it must NOT assume, both learned the hard way:

    * **one key per line** -- ``updated_by: CURRENT_USER, eventtime: nowStr,``
      is real code in transfer_plan.js. A line-anchored regex sees only the
      first key and silently under-reports, which makes the guard look green
      while missing exactly the column that was wrong.
    * **that any identifier before a colon is a key** -- a ternary value
      (``a ? b : c``) would produce a phantom one. A key is an identifier whose
      previous significant character is ``{`` or ``,``.
    """
    out = []
    marker = "updates: {"
    idx = text.find(marker)
    while idx != -1:
        brace = idx + len(marker) - 1
        keys, prev_significant, end = [], "{", len(text)
        for i, c, depth, _ in _scan_js(text, brace, stop_at_depth_zero_close=True):
            if c in "}])" and depth == 1 and c == "}":
                end = i
                break
            if depth == 1 and _IDENT_START.match(c) and prev_significant in "{,":
                m = _IDENT.match(text, i)
                after = text[m.end():]
                if after.lstrip()[:1] == ":" and after.lstrip()[:2] != "::":
                    keys.append(m.group(0))
                    prev_significant = "i"
                    continue
            if not c.isspace():
                prev_significant = c
        out.append(keys)
        idx = text.find(marker, end)
    return out


class TestUpdatesLiteralExtractor:
    """The write-path guard is only as good as this parser, so test it directly."""

    def test_extracts_top_level_keys_past_nesting_and_template_strings(self):
        src = """
        payload.push({
          business_key_val: k,
          updates: {
            doe_key: k,
            label: `band ${a} end`,
            nested: { inner_a: 1, inner_b: 2 },
            fn: JSON.stringify(obj),   // comment with an unbalanced { brace
            note: '',
            eventtime: nowStr,
          },
          source_name: 'user',
        });
        """
        literals = _extract_updates_literals(src)
        assert len(literals) == 1
        keys = literals[0]
        assert "doe_key" in keys and "eventtime" in keys and "note" in keys
        assert "inner_a" not in keys, "nested keys must not be treated as columns"
        assert "source_name" not in keys, "the envelope is not part of the payload"

    def test_two_keys_on_one_line_are_both_found(self):
        """The exact shape at transfer_plan.js:1016.

        A line-anchored key regex reports only `updated_by` here and silently
        drops `eventtime` -- which is how the guard first passed while missing
        the column that was actually wrong.
        """
        src = "push({updates: {\n  note: '',\n  updated_by: CURRENT_USER, eventtime: nowStr,\n}});"
        keys = _extract_updates_literals(src)[0]
        assert keys == ["note", "updated_by", "eventtime"]

    def test_a_ternary_value_does_not_produce_a_phantom_key(self):
        src = "push({updates: {\n  qty: cond ? alpha : beta,\n  note: '',\n}});"
        assert _extract_updates_literals(src)[0] == ["qty", "note"]

    def test_finds_every_literal_not_just_the_first(self):
        src = "a({updates: {x_key: 1}}); b({updates: {y_key: 2}});"
        assert [k for lit in _extract_updates_literals(src) for k in lit] == ["x_key", "y_key"]

    def test_reports_nothing_when_there_is_no_payload(self):
        assert _extract_updates_literals("const updates = 5; foo({a: 1});") == []


class TestProductWritePathsAreDeclared:
    """Every column the product writes must be declared, or it is silently lost.

    ``crud.py`` drops any column absent from ``column_types``::

        col_types = config.get("column_types", {})
        if col_name not in col_types:
            continue

    No error, no warning -- the request still returns 200. So an undeclared
    column is not a cosmetic omission: it is a feature that stops working in a
    fresh environment with nothing on the wire to say why. This test is the
    guard that a config-vs-config diff cannot give you, because it compares the
    declaration against the *code*, not against another declaration.
    """

    # The business key column identifies a write payload without depending on
    # line numbers or on the table name appearing in the same literal.
    #
    # M2.6 retarget (2026-07-27): map_doe / map_doe_source have no writer any
    # more - the DOE collapsed into the map_split_registry row (knobs + bands),
    # which map_editor.js writes. This was the retarget the docstring asks for,
    # NOT a deletion: map_split_registry below covers every column the product
    # writes for a DOE. (2026-08-13: those two tables were dropped outright -
    # declaration, indexes and physical table - so there is nothing left to
    # retarget from.)
    #
    # 2026-08-04: the map_split_registry write payload moved out of map_editor.js
    # into client2/src/split_registry_row.js (``buildLegendRegistryUpdates``) when
    # the row normal form was extracted. Nothing about the payload changed -- only
    # the file it is spelled in. NOTE the ``pytest.skip`` below: a WRONG filename
    # here makes this test SKIP, which reads exactly like a pass, so the name must
    # be checked against the tree rather than assumed.
    WRITERS = {
        "wafer_map_metadata": ("map_editor.js", "map_pk"),
        "map_split_registry": ("split_registry_row.js", "split_key"),
    }

    @pytest.mark.parametrize("table", sorted(WRITERS))
    def test_written_columns_are_all_declared(self, table):
        filename, anchor_col = self.WRITERS[table]
        path = os.path.join(CLIENT_SRC, filename)
        if not os.path.exists(path):
            pytest.skip(f"{filename} not present")
        with io.open(path, encoding="utf-8") as f:
            literals = _extract_updates_literals(f.read())

        payloads = [keys for keys in literals if anchor_col in keys]
        assert payloads, (
            f"no write payload found for {table}: no 'updates:' literal in {filename} "
            f"sets '{anchor_col}'. If the write path moved, retarget this test -- do not "
            f"delete it; it is the only check that the declaration matches the code."
        )

        declared = set(product_tables.PRODUCT_TABLES[table]["column_types"])
        for keys in payloads:
            undeclared = [k for k in keys if k not in declared]
            assert not undeclared, (
                f"{table}: client writes {undeclared} but product_tables.py does not declare "
                f"them. crud.py drops undeclared columns silently (200, data gone)."
            )


class TestPathResolution:
    def test_default_target_follows_assy_data_root(self, tmp_path):
        """The isolated dev env must be reachable without editing the script."""
        import paths
        assert ipt.paths is paths
        assert os.path.basename(paths.config_path("table_config.json")) == "table_config.json"
        assert paths.config_path("table_config.json").startswith(paths.CONFIG_DIR)

    def test_sample_path_is_the_tracked_template(self):
        assert ipt.SAMPLE_PATH.endswith(os.path.join(
            "config", "sample", "table_config.json.sample"))
        assert os.path.exists(ipt.SAMPLE_PATH)
