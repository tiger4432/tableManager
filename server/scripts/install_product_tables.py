"""Install the product-owned table declarations into a site's table_config.json.

Why this exists
---------------
Deploying to a new site used to mean hand-copying four table declarations out of
``table_config.json.sample``. Those four are **product-owned** — assyManager
defines their names and their columns — so the product should install them. The
operator's job is the *site-owned* tables (their factory's log/map tables), whose
names differ per deployment and which this script never touches.

The declarations live in exactly one place: ``server/product_tables.py``. The
tracked ``table_config.json.sample`` is generated from that same module by this
same script (``--sample --apply``), so there is no second list to drift.

What it protects
----------------
The target is the operator's **live ``table_config.json``, a gitignored user
asset**. Every rule below exists to keep that file safe:

* Site-owned entries are never re-serialised. Edits are byte-level splices into
  the original text, so anything this script did not add comes out byte-identical
  — key order, indentation, spacing and line endings included.
* Absent product entry -> added. Present and identical -> no write at all.
* Present but different -> reported as drift and left alone. Changing it needs
  ``--overwrite-drift``.
* Dry run is the default; writing needs ``--apply``.
* ``--apply`` writes a timestamped backup first and prints where it went.
* After writing, the result is re-scanned and every untouched member is compared
  byte-for-byte against the original. A mismatch restores the backup.

What it does NOT do
-------------------
No DDL, no database connection, no server restart. Declaring a table only makes
the *physical* table appear through one of the reload paths — the script prints
which one applies to what it just changed.

Usage
-----
    python server/scripts/install_product_tables.py                  # dry run
    python server/scripts/install_product_tables.py --apply
    python server/scripts/install_product_tables.py --apply --overwrite-drift
    python server/scripts/install_product_tables.py --config <path>  # explicit target
    python server/scripts/install_product_tables.py --sample --apply # regenerate the template

Exit codes: 0 nothing left to do | 1 action required | 2 error.
"""
import argparse
import codecs
import json
import os
import sys
from collections import namedtuple
from datetime import datetime

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths  # noqa: E402
import product_tables  # noqa: E402

SAMPLE_PATH = os.path.join(SERVER_DIR, "config", "table_config.json.sample")


class ConfigFormatError(Exception):
    """The target file is not a shape this script is willing to splice."""


# ---------------------------------------------------------------------------
# Byte-span scanner
#
# json.load/json.dump would round-trip the whole file and reformat entries this
# script must not touch. So: parse once with the stdlib for correctness, then
# locate the byte span of each top-level member so edits can be surgical. Only
# the top level is scanned — table_config.json is always {"table": {...}, ...}.
# ---------------------------------------------------------------------------

Member = namedtuple("Member", "key key_start value_start value_end")
Scan = namedtuple("Scan", "parsed members obj_open obj_close")
Style = namedtuple("Style", "newline indent")


def _skip_ws(text, i):
    n = len(text)
    while i < n and text[i] in " \t\r\n":
        i += 1
    return i


def _read_json_string(text, i):
    """text[i] must be '"'. Returns (decoded_value, index_past_closing_quote)."""
    n = len(text)
    j = i + 1
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return json.loads(text[i:j + 1]), j + 1
        j += 1
    raise ConfigFormatError(f"unterminated string starting at offset {i}")


def _skip_container(text, i):
    """text[i] must be '{' or '['. Returns the index just past its match."""
    n = len(text)
    depth = 0
    j = i
    while j < n:
        c = text[j]
        if c == '"':
            _, j = _read_json_string(text, j)
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    raise ConfigFormatError(f"unterminated container starting at offset {i}")


def _skip_value(text, i):
    c = text[i]
    if c == '"':
        _, j = _read_json_string(text, i)
        return j
    if c in "{[":
        return _skip_container(text, i)
    j = i
    n = len(text)
    while j < n and text[j] not in ",}]" and text[j] not in " \t\r\n":
        j += 1
    if j == i:
        raise ConfigFormatError(f"expected a value at offset {i}")
    return j


def scan_top_level_members(text):
    """Locate every top-level member's byte span.

    The stdlib parse runs first, so the scanner only ever walks well-formed JSON.
    Afterwards the spans are checked back against the parsed object: if the two
    disagree (duplicate keys, or a scanner bug) this raises rather than splicing
    into a position it does not understand.
    """
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ConfigFormatError("table_config must be a JSON object at the top level")

    n = len(text)
    i = _skip_ws(text, 0)
    if i >= n or text[i] != "{":
        raise ConfigFormatError("expected '{' at the start of the document")
    obj_open = i
    i += 1

    members = []
    obj_close = None
    while True:
        i = _skip_ws(text, i)
        if i >= n:
            raise ConfigFormatError("unterminated top-level object")
        c = text[i]
        if c == "}":
            obj_close = i
            break
        if c == ",":
            i += 1
            continue
        if c != '"':
            raise ConfigFormatError(f"unexpected character {c!r} at offset {i}")
        key_start = i
        key, i = _read_json_string(text, i)
        i = _skip_ws(text, i)
        if i >= n or text[i] != ":":
            raise ConfigFormatError(f"expected ':' after key '{key}'")
        i += 1
        i = _skip_ws(text, i)
        value_start = i
        i = _skip_value(text, i)
        members.append(Member(key, key_start, value_start, i))

    if [m.key for m in members] != list(parsed.keys()):
        raise ConfigFormatError(
            "span scan disagrees with the JSON parser (duplicate top-level keys?) -- refusing to edit"
        )
    for m in members:
        if json.loads(text[m.value_start:m.value_end]) != parsed[m.key]:
            raise ConfigFormatError(f"span scan produced a wrong value span for '{m.key}' -- refusing to edit")

    return Scan(parsed, members, obj_open, obj_close)


def detect_style(text, members):
    """Line ending and one indent unit, taken from the file itself."""
    newline = "\r\n" if "\r\n" in text else "\n"
    indent = "  "
    if members:
        first = members[0].key_start
        line_start = text.rfind("\n", 0, first) + 1
        prefix = text[line_start:first]
        if prefix and not prefix.strip():
            indent = prefix
    return Style(newline, indent)


def render_entry_value(value, style):
    """Serialise one table declaration at member depth, in the file's own style."""
    raw = json.dumps(value, indent=style.indent, ensure_ascii=False)
    lines = raw.split("\n")
    return style.newline.join([lines[0]] + [style.indent + ln for ln in lines[1:]])


def render_member(name, value, style):
    return json.dumps(name, ensure_ascii=False) + ": " + render_entry_value(value, style)


def apply_edits(text, edits):
    """Apply (start, end, replacement) splices. Descending order keeps offsets valid."""
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

Difference = namedtuple("Difference", "kind path product config")
TableStatus = namedtuple("TableStatus", "name state diffs comment_differs")

STATE_ADD = "add"
STATE_MATCH = "match"
STATE_DRIFT = "drift"

BLOCKING_KINDS = ("missing", "changed")

# Lists where the site appending its own items is presentation-only and cannot
# break the product, so a superset counts as `extra` rather than `changed`.
#
# This exception is deliberately narrow. `composite_key_source` must NOT be in
# here: appending a component there rewrites every business key in the table.
# Getting this wrong is worse than noise -- a benign append reported as BLOCKING
# teaches operators to reach for --overwrite-drift, which would then delete the
# columns they added.
ADDITIVE_LIST_PATHS = ("display_columns",)


def _is_ordered_superset(product_list, config_list):
    """True when every product item appears in config, in the product's order."""
    it = iter(config_list)
    return all(any(item == c for c in it) for item in product_list)


def diff_declaration(product, config, path=""):
    """Recursive difference list between the product definition and a config entry.

    ``missing``/``changed`` mean the site's entry no longer says what the product
    needs. ``extra`` means the site added something on top -- additive, and the
    product keeps working.
    """
    if not isinstance(config, dict) or not isinstance(product, dict):
        if product == config:
            return []
        return [Difference("changed", path or "<entry>", product, config)]

    diffs = []
    for k in product:
        p = f"{path}.{k}" if path else k
        if k not in config:
            diffs.append(Difference("missing", p, product[k], None))
        elif product[k] != config[k]:
            if isinstance(product[k], dict) and isinstance(config[k], dict):
                diffs.extend(diff_declaration(product[k], config[k], p))
            elif (
                p in ADDITIVE_LIST_PATHS
                and isinstance(product[k], list)
                and isinstance(config[k], list)
                and _is_ordered_superset(product[k], config[k])
            ):
                added = [x for x in config[k] if x not in product[k]]
                diffs.append(Difference("extra", p, None, added))
            else:
                diffs.append(Difference("changed", p, product[k], config[k]))
    for k in config:
        if k not in product:
            p = f"{path}.{k}" if path else k
            diffs.append(Difference("extra", p, None, config[k]))
    return diffs


def evaluate(parsed, definitions=None, strict=False):
    """Status of every product table against the parsed config object.

    ``strict=False`` (a live site config): annotations are stripped before
    comparing, so rewording a ``__comment`` never flags an operator's file.
    ``strict=True`` (the tracked ``.sample``): compare the entry whole. The
    sample is a generated product artifact, not a user asset, so any difference
    from ``product_tables.py`` -- comments included -- is drift to regenerate.
    """
    definitions = definitions if definitions is not None else product_tables.PRODUCT_TABLES
    prepare = (lambda e: e) if strict else product_tables.effective_declaration
    out = []
    for name, product_entry in definitions.items():
        if name not in parsed:
            out.append(TableStatus(name, STATE_ADD, [], False))
            continue
        config_entry = parsed[name]
        diffs = diff_declaration(prepare(product_entry), prepare(config_entry))
        comment_differs = (
            isinstance(config_entry, dict)
            and config_entry.get("__comment") != product_entry.get("__comment")
        )
        state = STATE_MATCH if not diffs else STATE_DRIFT
        out.append(TableStatus(name, state, diffs, comment_differs))
    return out


def is_blocking(status):
    return any(d.kind in BLOCKING_KINDS for d in status.diffs)


# ---------------------------------------------------------------------------
# Plan / render / write
# ---------------------------------------------------------------------------

def build_edits(text, scan, statuses, overwrite_drift, definitions=None):
    """Byte splices for the requested changes. Empty list == nothing to write."""
    definitions = definitions if definitions is not None else product_tables.PRODUCT_TABLES
    style = detect_style(text, scan.members)
    by_key = {m.key: m for m in scan.members}
    edits = []

    if overwrite_drift:
        for st in statuses:
            if st.state == STATE_DRIFT:
                m = by_key[st.name]
                edits.append((m.value_start, m.value_end, render_entry_value(definitions[st.name], style)))

    to_add = [st.name for st in statuses if st.state == STATE_ADD]
    if to_add:
        rendered = [render_member(name, definitions[name], style) for name in to_add]
        if scan.members:
            anchor = scan.members[-1].value_end
            chunk = "".join("," + style.newline + style.indent + r for r in rendered)
            edits.append((anchor, anchor, chunk))
        else:
            # Empty object: only whitespace sits between the braces, so replacing
            # that span cannot destroy anything the operator wrote.
            joiner = "," + style.newline + style.indent
            chunk = style.newline + style.indent + joiner.join(rendered) + style.newline
            edits.append((scan.obj_open + 1, scan.obj_close, chunk))

    return edits


def _fmt(value, limit=140):
    s = json.dumps(value, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "... (truncated)"


def render_report(path, statuses, apply_mode, overwrite_drift, wrote, backup_path,
                  planned_adds=(), planned_overwrites=()):
    """Text report.

    ``statuses`` describe the file as it stands *now* (after a write, if there
    was one). ``planned_adds`` / ``planned_overwrites`` describe what this run
    set out to change -- they are what the follow-up instructions key off,
    because after a successful apply the statuses no longer show any pending
    work and would otherwise silence the guidance the operator needs.
    """
    lines = []
    head = "APPLY" if apply_mode else "DRY RUN -- nothing written"
    lines.append(f"assyManager -- product-owned table installer  [{head}]")
    lines.append("")
    lines.append(f"  target : {path}")
    lines.append(f"  source : server/product_tables.py  ({len(product_tables.PRODUCT_TABLES)} product tables)")
    lines.append("")

    width = max(len(s.name) for s in statuses)
    for st in statuses:
        if st.state == STATE_ADD:
            lines.append(f"  [ADD  ] {st.name.ljust(width)}  not declared -- will be added")
        elif st.state == STATE_MATCH:
            tag = "  (added by this run)" if st.name in planned_adds else ""
            if not tag and st.comment_differs:
                tag = "  (comment differs -- annotation only, ignored)"
            lines.append(f"  [ OK  ] {st.name.ljust(width)}  matches the product definition{tag}")
        else:
            kind = "BLOCKING" if is_blocking(st) else "additive"
            lines.append(
                f"  [DRIFT] {st.name.ljust(width)}  {len(st.diffs)} difference(s) vs the product definition  ({kind})"
            )
            for d in st.diffs:
                if d.kind == "missing":
                    lines.append(f"            missing  {d.path}  product wants {_fmt(d.product)}")
                elif d.kind == "extra":
                    lines.append(f"            extra    {d.path}  yours: {_fmt(d.config)}  (not in the product definition)")
                else:
                    lines.append(f"            changed  {d.path}")
                    lines.append(f"                       product: {_fmt(d.product)}")
                    lines.append(f"                       yours  : {_fmt(d.config)}")
            if is_blocking(st):
                lines.append("          -> the product expects this declaration; features reading it may misbehave.")
            else:
                lines.append("          -> additive only: the product works as-is. Nothing to do unless you")
                lines.append("             want the entry reset to the product definition.")

    if planned_overwrites and wrote:
        lines.append("")
        lines.append("  drift replaced with the product definition: " + ", ".join(sorted(planned_overwrites)))

    adds = [s for s in statuses if s.state == STATE_ADD]
    drifts = [s for s in statuses if s.state == STATE_DRIFT]
    blocking = [s for s in drifts if is_blocking(s)]
    lines.append("")
    lines.append(
        f"  summary: {len(adds)} to add, {len([s for s in statuses if s.state == STATE_MATCH])} matching, "
        f"{len(drifts)} drifted ({len(blocking)} blocking, {len(drifts) - len(blocking)} additive)"
    )
    lines.append("")

    if wrote:
        lines.append(f"  backup : {backup_path}")
        lines.append("  written: the file was rewritten in place (see 'what happens next').")
    elif apply_mode:
        lines.append("  nothing to write -- the file was not opened for writing and no backup was made.")
    elif adds or drifts:
        lines.append("  nothing was written. To act:")
        if adds:
            lines.append(f"    * --apply  (adds {len(adds)} table declaration(s))")
        if drifts:
            lines.append("    * --apply --overwrite-drift  (replaces the drifted entries with the product definition)")
    else:
        lines.append("  nothing to do -- the file already declares every product table.")

    if drifts and not overwrite_drift:
        lines.append("")
        lines.append("  drift is never overwritten silently. --overwrite-drift replaces the WHOLE entry")
        lines.append("  with the product definition, which drops the 'extra' items listed above from the")
        lines.append("  declaration (physical columns already in the database are NOT dropped -- they just")
        lines.append("  stop being declared, so they disappear from the grid and from ingestion).")

    if planned_adds or planned_overwrites:
        lines.append("")
        lines.extend(next_steps(bool(planned_adds), bool(planned_overwrites), wrote))
    return "\n".join(lines)


def next_steps(added_tables, changed_existing, wrote):
    """What the operator has to do for the declaration to become physical.

    Declaring a table is not inert: it leads to a physical CREATE TABLE through
    models.create_missing_dynamic_tables. The three routes differ in what they
    cover, and getting that wrong is a documented trap (CONFIG_GUIDE 6.C).
    """
    header = ("what happens next" if wrote else "what applying this would trigger")
    out = [f"  {header} (this script issues no DDL and opens no DB connection):"]
    if added_tables:
        out += [
            "    NEW tables -- the physical CREATE TABLE happens on any one of:",
            "      * the config watcher, which fires on in-place writes. This script writes in",
            "        place precisely for that reason (an atomic temp+rename would not fire it),",
            "        so on a running web server the tables are usually created within a second.",
            "      * POST /admin/reload-configs -- deterministic, covers every process.",
            "      * a server restart -- boot-time create_all.",
        ]
    if changed_existing:
        out += [
            "    CHANGED existing tables -- new columns need ALTER TABLE, and ONLY the config",
            "      watcher performs ALTER. /admin/reload-configs does not. If the watcher did",
            "      not fire, re-save the file in place or restart the web server.",
        ]
    out += [
        "    verify against the database, not the API: GET /tables/{t}/schema reads the config",
        "      singleton, so a 200 there is not evidence of a physical column. Query",
        "      information_schema.columns instead.",
    ]
    return out


def read_config_text(path):
    """Returns (text, had_bom). Binary I/O: no newline translation, no re-encoding."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8"), True
    return raw.decode("utf-8"), False


def write_config_text(path, text, had_bom):
    """In-place, non-atomic rewrite.

    Deliberately not temp+rename: the config watcher only handles on_modified,
    and an atomic rename does not raise it, which is how runtime ALTERs get
    silently skipped. A backup is taken before this is called, which is what
    covers the truncation window.
    """
    payload = text.encode("utf-8")
    if had_bom:
        payload = codecs.BOM_UTF8 + payload
    with open(path, "wb") as f:
        f.write(payload)


def make_backup(path, original_bytes):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak.{stamp}"
    suffix = 1
    while os.path.exists(backup_path):
        backup_path = f"{path}.bak.{stamp}.{suffix}"
        suffix += 1
    with open(backup_path, "wb") as f:
        f.write(original_bytes)
    return backup_path


def verify_untouched(old_text, new_text, changed_keys):
    """Every member that was not deliberately changed must be byte-identical.

    Runs against the text actually written back from disk, so it also catches an
    encoding or newline mistake in the writer, not only a bad splice.
    """
    old = scan_top_level_members(old_text)
    new = scan_top_level_members(new_text)
    new_by_key = {m.key: m for m in new.members}
    for m in old.members:
        if m.key in changed_keys:
            continue
        if m.key not in new_by_key:
            return f"member '{m.key}' disappeared from the file"
        n = new_by_key[m.key]
        if new_text[n.value_start:n.value_end] != old_text[m.value_start:m.value_end]:
            return f"member '{m.key}' was reformatted (must be byte-identical)"
    old_keys = [m.key for m in old.members]
    if [k for k in (m.key for m in new.members) if k in set(old_keys)] != old_keys:
        return "existing members were reordered"
    return None


def run(path, apply_mode=False, overwrite_drift=False, out=None, strict=False):
    out = out if out is not None else sys.stdout

    if not os.path.exists(path):
        print(f"error: {path} does not exist.", file=out)
        print("       Copy the template first:  cp server/config/table_config.json.sample "
              "server/config/table_config.json", file=out)
        print("       (this script refuses to create the file -- a missing table_config.json means", file=out)
        print("        the deployment has not been set up yet, and silently creating one hides that)", file=out)
        return 2

    with open(path, "rb") as f:
        original_bytes = f.read()
    try:
        text, had_bom = read_config_text(path)
        scan = scan_top_level_members(text)
    except (ValueError, ConfigFormatError, UnicodeDecodeError) as err:
        print(f"error: cannot read {path}: {err}", file=out)
        return 2

    statuses = evaluate(scan.parsed, strict=strict)
    edits = build_edits(text, scan, statuses, overwrite_drift) if apply_mode else []

    # What this run intends to change. Captured before any write, because after a
    # successful apply the statuses show everything as matching and the operator
    # would lose the CREATE-vs-ALTER instructions that depend on it.
    planned_adds = [s.name for s in statuses if s.state == STATE_ADD]
    planned_overwrites = [s.name for s in statuses if s.state == STATE_DRIFT] if overwrite_drift else []

    wrote = False
    backup_path = None
    if apply_mode and edits:
        changed_keys = set(planned_adds) | set(planned_overwrites)
        new_text = apply_edits(text, edits)

        try:
            json.loads(new_text)
        except ValueError as err:
            print(f"error: the merge produced invalid JSON ({err}); nothing was written.", file=out)
            return 2

        backup_path = make_backup(path, original_bytes)
        write_config_text(path, new_text, had_bom)
        wrote = True

        readback, _ = read_config_text(path)
        problem = verify_untouched(text, readback, changed_keys)
        if problem is None:
            reparsed = json.loads(readback)
            for name in changed_keys:
                if reparsed.get(name) != product_tables.PRODUCT_TABLES[name]:
                    problem = f"'{name}' did not land as the product definition"
                    break
        if problem is not None:
            with open(path, "wb") as f:
                f.write(original_bytes)
            print(f"error: post-write verification failed ({problem}).", file=out)
            print(f"       {path} has been restored from memory; the backup is at {backup_path}", file=out)
            return 2

        statuses = evaluate(json.loads(readback), strict=strict)

    print(
        render_report(path, statuses, apply_mode, overwrite_drift, wrote, backup_path,
                      planned_adds, planned_overwrites),
        file=out,
    )

    pending_add = [s for s in statuses if s.state == STATE_ADD]
    pending_blocking = [s for s in statuses if s.state == STATE_DRIFT and is_blocking(s)]
    return 1 if (pending_add or pending_blocking) else 0


def main(argv=None):
    # A Windows operator console is cp949 here. Every literal this script prints
    # is ASCII, but a drift report can echo config values that are not, and an
    # encode error mid-report would be a confusing way to lose a deploy step.
    # Only main() does this, so tests capturing to StringIO are unaffected.
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Install assyManager's product-owned table declarations into a table_config.json.",
    )
    parser.add_argument("--config", help="target file (default: the active config, honours ASSY_DATA_ROOT)")
    parser.add_argument("--sample", action="store_true",
                        help="target the tracked template server/config/table_config.json.sample "
                             "(compared strictly: it is a generated artifact, so comments count too)")
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    parser.add_argument("--overwrite-drift", action="store_true",
                        help="also replace entries that differ from the product definition")
    args = parser.parse_args(argv)

    if args.sample and args.config:
        parser.error("--sample and --config are mutually exclusive")
    if args.sample:
        target = SAMPLE_PATH
    elif args.config:
        target = os.path.abspath(args.config)
    else:
        target = paths.config_path("table_config.json")

    return run(target, apply_mode=args.apply, overwrite_drift=args.overwrite_drift,
               strict=args.sample)


if __name__ == "__main__":
    sys.exit(main())
