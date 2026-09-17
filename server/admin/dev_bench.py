# -*- coding: utf-8 -*-
"""S-192. Run a mapper or a parser on a sample and see what comes out. No writes.

Owner 2026-09-12: 「체인 맵퍼·인제션 파서 개발용 시험 환경 — 샘플 인풋과 핵심 로직 아웃풋만」.

🔴 BOTH SEAMS ALREADY EXISTED; WHAT WAS MISSING WAS A PLACE TO STAND. A mapper is
`(df, db) -> df` under `mapper_sdk.mapper`, and a parser is
`pipeline_base.parse(file_path) -> list[dict]`. Neither needed inventing. What did not exist
was running either one WITHOUT writing to the database, and a shape where the sample and the
expectation are just files.

⚠️ THE db IS READ-ONLY BECAUSE THE SERVER SAYS SO, NOT BECAUSE THIS MODULE IS CAREFUL
(판정 301). The first draft wrapped the call in a transaction and rolled back -- and `conftest`
already records why that is not enough: 「the code under test COMMITS」, so a rollback is void
wherever anything commits. `db_safety.open_readonly_connection` + `assert_readonly` make
PostgreSQL refuse the write, and `db_safety` even records that the obvious setting
(`default_transaction_read_only`) is not the one the server enforces.

🔴 A PARSER IS CHOSEN THE WAY PRODUCTION CHOOSES ONE -- BY CLAIM, NOT BY NAME (판정 301).
`scan_workspace_pipeline_parsers` walks the workspace, asks each class `match(path)`, and the
first one that says yes takes the file. There is no name to look a parser up by, and adding
one would have built a bench that exercises a path production never takes. `force=` exists
for the real development case: a parser whose `match()` does not claim the file YET.
"""
from __future__ import annotations

import csv
import io
import json
import os

MAPPER = "mapper"
PARSER = "parser"
KINDS = (MAPPER, PARSER)


def read_sample(path):
    """A sample file as rows. CSV/TSV by delimiter, JSON as a list of objects."""
    if path.lower().endswith(".json"):
        with io.open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, list) else [loaded]
    delimiter = "\t" if path.lower().endswith((".tsv", ".tab")) else ","
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def as_payloads(rows):
    """Sample rows in the payload shape the worker BUILDS.

    ⚠️ [판정 591] THE SHAPE IS PRODUCTION'S; THE HANDING IS NOT. This said 「the shape the
    worker hands a mapper」 and the three ways the bench's handing differs are listed on
    `input_for_mapper`, which is the seat that promises fidelity.

    🔴 THE ENVELOPE IS `{"row_id": …, "data": {col: {"value": x}}}` — THE CELLS SIT UNDER
    `data`, not at the top level. `payloads_to_df`'s docstring says 「the cell shape is
    `{col: {"value": x}}`」 and that sentence describes the contents of `data`; read as the
    whole payload it produced a frame with ONE column, `row_id`, and the sample mapper died on
    `None of [Index(['wafer'])] are in the [columns]`. Measured, not reasoned: the first
    version of this function wrapped at the top level.

    ⚠️ A row already carrying `data` is passed through, so a sample captured from a real
    outbox payload works unchanged.
    """
    out = []
    for index, row in enumerate(rows):
        if isinstance(row.get("data"), dict):
            out.append(row)
            continue
        cells = {k: {"value": v} for k, v in row.items() if k != "row_id"}
        out.append({"row_id": row.get("row_id") or "sample-%d" % index, "data": cells})
    return out


def rows_to_tsv(rows):
    """The ONE text form of a result, shared by the CLI and the pytest fixture.

    🔴 IT GOES THROUGH `wire_text` (S-190), so a cell here reads exactly as the grid and the
    CSV export read it. A bench that spelled a JSON cell its own way would let an author
    match an expectation the product never produces.
    """
    from utils.wire_format import wire_text

    rows = list(rows or ())
    columns = []
    for row in rows:
        for name in row:
            if name not in columns:
                columns.append(str(name))
    lines = ["\t".join(columns)]
    for row in rows:
        cells = []
        for name in columns:
            value = row.get(name)
            if value is None:
                cells.append("")
                continue
            text = str(wire_text(value))
            cells.append(text.replace("\t", " ").replace("\r", " ").replace("\n", " "))
        lines.append("\t".join(cells))
    return "\n".join(lines) + "\n"


def _frame_rows(frame):
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    return list(frame)


# ---------------------------------------------------------------------------
# the read-only footing
# ---------------------------------------------------------------------------

def _readonly_session():
    """A Session the SERVER refuses writes on, plus its teardown.

    ⚠️ A MAPPER THAT NEVER TOUCHES `db` MUST STILL RUN. Most do not, and requiring a live
    PostgreSQL to try one would make the bench useless in exactly the case it is best at --
    so a database that cannot be opened yields `None` and the mapper is handed that.
    """
    try:
        import db_safety
        from sqlalchemy.orm import Session

        engine = db_safety.open_readonly_engine()
        conn = db_safety.open_readonly_connection(engine)
        db_safety.assert_readonly(conn)
        session = Session(bind=conn)

        def closer():
            try:
                session.close()
            finally:
                db_safety.close_readonly_connection(conn)
                engine.dispose()

        return session, closer
    except Exception:
        return None, lambda: None


#: The declaration the bench lends an undeclared target, so `df_to_updates` has a business
#: key to read. One column, and `row_id` is the key — nothing domain-shaped, because the
#: bench must not teach a mapper anything its own target would not.
BENCH_TARGET_DECLARATION = {"business_key": "row_id",
                            "column_types": {"row_id": "string"}}


def _declare_bench_target(table_name):
    """Lend `table_name` a declaration for the length of one run. Returns the undo.

    🔴 THE MAPPER CONTRACT REFUSES AN UNDECLARED TARGET, AND THAT REFUSAL IS RIGHT:
    `df_to_updates` reads the business key from the declaration, and emitting without one
    lands rows that the upsert can never find again. So a bench that wants to see a
    decorated mapper's output has to supply the declaration, exactly as it supplies a
    session — measured, by running the sample and reading the refusal.

    ⚠️ AND IT IS PUT BACK IN A `finally`. `crud.TABLE_CONFIG` is a process-wide singleton;
    leaving a name behind is the same class of defect as a dynamic model left in
    `Base.metadata`, which cost five sibling errors earlier today. A target that is ALREADY
    declared is left completely alone.
    """
    try:
        from database import crud
    except Exception:
        return lambda: None
    if table_name in crud.TABLE_CONFIG:
        return lambda: None
    crud.TABLE_CONFIG[table_name] = dict(BENCH_TARGET_DECLARATION)

    def restore():
        crud.TABLE_CONFIG.pop(table_name, None)

    return restore


# ---------------------------------------------------------------------------
# the mapper
# ---------------------------------------------------------------------------

def _unknown_name(name, detail=None):
    """「이 이름으로는 아무것도 못 돌립니다」 — 양쪽 점호를 달아서. 판정 541.

    🔴 THE OPERATOR USED TO GET A PYTHON IMPORT ERROR. A mistyped `builtin:jion` fell
    into the `module:function` arm, where `rpartition(":")` made the module 「builtin」 and the
    bench handed back `ModuleNotFoundError: No module named 'builtin'`. That names a Python
    fact, not a place to fix: the operator's next move is to correct a NAME, and nothing in
    that sentence tells them what names exist. 「거절은 «이름»으로 온다」 is this round's ⑥.

    ⛔ AND IT DOES NOT BRANCH ON `"builtin:"`. Spelling the prefix here would put a domain
    word in code and give the rosters a second author; `rule_run` already reads both tables
    and `chain.synthesis` owns what the product builds.

    ⚠️ `detail` RIDES AT THE END, never as the message. What went wrong technically can
    matter to whoever is debugging a real module, but it is not what the sentence is for.
    """
    import mapper_sdk
    from chain import synthesis

    # 🔴 [판정 562] ONE REGISTRY. The refusal listed the kind table, which no longer
    #   exists - and the names it used to hold are in this one, under the same spelling.
    kinds = ", ".join(sorted(mapper_sdk.MAPPER_REGISTRY)) or "none registered"
    registered = ", ".join(sorted(mapper_sdk.MAPPER_REGISTRY)) or "none"
    said = ("%r is neither a registered kind nor a mapper this product can find. "
            "Registered kinds: %s. Mapper names: %s. A file mapper may also be given as "
            "module:function." % (name, kinds, registered))
    if detail:
        said += " (%s)" % detail
    return {"who": name, "rows": [], "refusal": said}


def try_mapper(name, sample, *, rule=None, target_table="bench_target"):
    """Run one mapper over `sample`. Returns `{who, rows, refusal}`; never writes.

    `name` resolves through the decorator's registry (S-188 ⓒ) and falls back to
    `module:function`, because the registry is empty wherever no mapper file uses the
    decorator yet -- measured zero on this box.
    """
    import mapper_sdk

    rows = sample if isinstance(sample, list) else read_sample(sample)
    payloads = as_payloads(rows)

    # 🪦 [판정 498 ①] THE REGISTRY LOOKUP IS THE SEAT'S. The import fallback below is
    # this bench's own - it accepts a name a rule never declared - but 「is this a registered
    # mapper」 is the same question the chain asks, and it had two answers.
    from chain import rule_run

    # [501 b] REFUSED BY NAME, NOT RUN. `runnable` answers for BOTH tables, so widening this
    #   line to the seat's question quietly widened what the bench would CALL - and a
    #   registered kind takes `(db, rule, row_ids=)` while the line below calls
    #   `(db, payloads, rule=)`. Measured: `builtin:auto_confirm` came back
    #   `{'rows': 0, 'refusal': None}` - a success shape - and the join kinds threw
    #   AttributeError. `try_core.py`'s own note says a refusal printed as rows is
    #   indistinguishable from 「no rows」, and that is exactly what it became.
    #
    # 🔴 [판정 503] AND THE PREDICATE IS THE CALLING SHAPE, NOT 「does it write its own rows」.
    #   ⚰️ My first repair asked `self_writing_name`, and the ontology lane caught that it is a
    #   CORRELATION rather than the property: 「writes its own rows」 decides what happens AFTER
    #   a call, and what the bench needs to know is whether this thing takes a sample file as
    #   its INPUT. The two agree today only because all three registered kinds happen to write
    #   for themselves - 「가드와 행동이 다른 집합을 본다」, and the day a kind registers
    #   `writes_itself=False` they part.
    #   `Resolved.hands` IS that fact: it is what the seat itself uses to decide between
    #   `(db, rule, row_ids=)` and `(db, payload)`.
    #   ⚰ THIS PARAGRAPH SAID 「registered this round」 WHEN IT WAS NOT. 503 landed `hands` as
    #   `HANDS_ROW_IDS if builtin_kind(rule) is not None` - the address question one level
    #   down - so this file and `rule_run.hands`'s own docstring said different things inside
    #   ONE landing, and the docstring was the honest one. The ontology lane read both and
    #   named the class: 「수리가 대리를 «없앤» 것이 아니라 «한 층 내린» 것」 (판정 508).
    #   `register_builtin(..., hands=)` states it now, so the sentence above is true.
    #
    # ⚠️ AND THE NAME IS RESOLVED ONCE. It used to be resolved here and AGAIN below, which is
    #   two answers to 「what does this name run as」 waiting to disagree.
    try:
        bound = rule_run.resolve({"name": "bench", "mapper": name})
    except rule_run.UnresolvableRule:
        # Not a name the product can run. The bench accepts `module:function` spellings no
        # rule ever declared, so its own fallback below gets its turn before it refuses.
        bound = None

    # ⚰️ A REFUSAL STOOD HERE: 「this is a registered kind, not a file mapper - it resolves
    #   its own rows, so a sample file is not an input it takes」. It was reachable only
    #   because a kind was called with row ids instead of a payload. Every mapper takes a
    #   payload now, so the bench can feed a sample to any of them and the sentence would
    #   be refusing something that works (판정 562).

    fn = bound.call if bound is not None else None
    who = bound.who if bound is not None else name
    if fn is None and (":" in name or "." in name):
        import importlib

        separator = ":" if ":" in name else "."
        module_name, _, function_name = name.rpartition(separator)
        try:
            fn = getattr(importlib.import_module(module_name), function_name)
            who = "%s.%s" % (module_name, function_name)
        except Exception as exc:
            return _unknown_name(name, detail="%s: %s" % (type(exc).__name__, exc))
    if fn is None:
        return _unknown_name(name)

    effective_rule = dict(rule or {})
    effective_rule.setdefault("name", "bench")
    effective_rule.setdefault("target_table", target_table)

    session, closer = _readonly_session()
    restore_target = _declare_bench_target(effective_rule["target_table"])
    try:
        try:
            # ⚠️ [판정 591] THIS IS WHERE THE BENCH AND THE SEAT PART. `rule_run` fans out
            #   on `is_batch` and folds both the payload and the answer through
            #   `without_missing`; this line does neither. `input_for_mapper` lists all
            #   three. Do not "fix" it here - a copy of the seat's behaviour is the thing
            #   being removed, not added.
            out = fn(session, payloads, rule=effective_rule)
        except TypeError as exc:
            # ⚠️ A mapper that never declared `rule` is called the old way by the worker too,
            # so the bench must not be stricter than production. The message is checked so a
            # genuine TypeError INSIDE the mapper is not swallowed as a signature mismatch.
            if "rule" not in str(exc):
                raise
            out = fn(session, payloads)
    except Exception as exc:
        return {"who": who, "rows": [], "refusal": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        closer()
        restore_target()

    if isinstance(out, dict):
        return {"who": who, "rows": list(out.get("updates") or ()), "refusal": None}
    return {"who": who, "rows": _frame_rows(out), "refusal": None}


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------

def try_parser(file_path, *, force=None, scripts_path=None):
    """Parse one file the way production would. Returns `{who, rows, refusal}`. No database.

    🔴 SELECTION IS BY CLAIM. Each parser class is offered the path and answers `match()`;
    the first yes takes it, and 「nobody claimed it」 is an ANSWER rather than an error --
    `directory_watcher` already distinguishes those two. `force="File.py::Class"` (or just the
    class name) runs a parser whose `match()` has not been written yet.
    """
    from parsers.directory_watcher import (SCAN_UNAVAILABLE,
                                           scan_workspace_pipeline_parsers)

    scripts_path = scripts_path or _default_scripts_path()
    load_errors = {}
    offered = []

    def visit(filename, obj):
        label = "%s::%s" % (filename, obj.__name__)
        offered.append(label)
        if force:
            if force not in (label, obj.__name__):
                return None
        else:
            try:
                if not obj.match(file_path):
                    return None
            except Exception as exc:
                load_errors[label] = "match(): %s: %s" % (type(exc).__name__, exc)
                return None
        instance = obj()
        # The watcher hands the path in as an ATTRIBUTE for the same reason: `parse(path)` is
        # a contract user scripts already subclass.
        instance.rel_path = os.path.basename(file_path)
        return (label, instance.parse(file_path))

    try:
        claim = scan_workspace_pipeline_parsers(scripts_path, visit, load_errors)
    except Exception as exc:
        return {"who": None, "rows": [], "refusal": "%s: %s" % (type(exc).__name__, exc)}

    if claim is SCAN_UNAVAILABLE:
        return {"who": None, "rows": [],
                "refusal": "the parser workspace is unavailable at %s" % scripts_path}
    if claim is None:
        detail = "; ".join("%s -> %s" % (k, v) for k, v in sorted(load_errors.items()))
        return {"who": None, "rows": [],
                "refusal": "no parser claimed this file (offered: %s)%s"
                           % (", ".join(offered) or "none",
                              "; " + detail if detail else "")}
    who, rows = claim
    return {"who": who, "rows": list(rows or ()), "refusal": None}


def _default_scripts_path():
    try:
        import paths

        return os.path.join(paths.workspace_path(), "scripts")
    except Exception:
        return os.path.join(paths.SERVER_DIR, "scripts")


# ---------------------------------------------------------------------------
# ① the input — 「이름을 적으면 입력이 온다」 (S-197)
# ---------------------------------------------------------------------------

#: How many rows a table hands back when the caller names no window. A notebook cell that
#: SELECTed a production-shaped table unbounded would hang the kernel on the one input the
#: author most wants to look at, and 「성능 마진은 넉넉하게」 says not to wait to find out.
DEFAULT_INPUT_ROWS = 200


def _ensure_dynamic_models():
    """Make `DYNAMIC_TABLES` answer, the way the boot path fills it.

    ⚠️ A NOTEBOOK IS NOT THE SERVER — nothing has called `init_dynamic_models` in this
    process. Loading the declaration through `crud.load_table_config` rather than reading the
    file here keeps 「which declaration is live」 one question.
    """
    from database import crud, models

    if models.DYNAMIC_TABLES:
        return
    config = crud.load_table_config() or {}
    if config:
        models.init_dynamic_models(config)


def input_for_mapper(table_or_sample, *, rows=None, row_ids=None, where=None):
    """A DataFrame built the way the worker BUILDS a mapper's payloads. Reads only.

    🔴 [판정 591] THE CONSTRUCTION IS PRODUCTION'S AND THE HANDING IS NOT, AND THIS
    DOCSTRING USED TO PROMISE BOTH - 「EXACTLY the shape the worker hands a mapper」. Measured
    2026-09-17 by the application lane and confirmed at both seats: the bench calls
    `fn(session, payloads, rule=...)` while `chain.rule_run` wraps the same call three ways.
    So the author gets production's FRAME and not production's CALL, and the three
    differences are:
        ① fan-out    the seat hands ONE payload per call unless the rule declares
                      `is_batch`; the bench always hands the whole list
                      (`rule_run.py` 467-469)
        ② input     the seat passes it through `mapper_call.without_missing`, which folds
                      missing markers (NaN, inf, the parser's sentinels) to None; the bench
                      does not, so a sample can carry a marker production never delivers
        ③ answer    the seat folds the mapper's RESULT the same way; the bench reports the
                      result raw (`rule_run.py` 473-476)
    ⚠️ NOT REPAIRED HERE ON PURPOSE. Calling `without_missing` from the bench would be the
    seat's behaviour written down a SECOND time, which is the defect 562 spent a day
    removing. The repair is the bench going THROUGH the seat, and whether it wants the seat's
    logging, activity registration and refusals with it is the question that has to be
    answered first.

    🔴 THE CONSTRUCTION, THOUGH, IS NOT A LOOKALIKE. A table name goes through
    `outbox_expand._data_columns` and `_synthesize_payload` — the same two functions the
    worker uses when it reads a collapsed event's rows back into payloads — and then through
    `mapper_sdk.payloads_to_df`. A bench that assembled its own envelope would hand the
    author a frame production never produces, and the mapper written against it would fail on
    the first real batch. That reasoning is why the construction is shared, and it is also
    why ①②③ above are worth writing down rather than leaving to be rediscovered. (`_synthesize_payload` is underscored and called anyway; that is
    the point. Spelling it again here is the defect this argument exists to avoid.)

    ⚠️ A FILE PATH IS ACCEPTED TOO and goes through `read_sample` + `as_payloads`, so the
    sample folders that are already tests are also inputs here — one shape, two sources.

    Window: `rows=N` (default `DEFAULT_INPUT_ROWS`), `row_ids=[...]`, or `where="col = 'x'"`.
    """
    import mapper_sdk

    if os.path.isfile(str(table_or_sample)):
        return mapper_sdk.payloads_to_df(as_payloads(read_sample(str(table_or_sample))))

    table_name = str(table_or_sample)
    _ensure_dynamic_models()
    from database.models import DYNAMIC_TABLES

    model = DYNAMIC_TABLES.get(table_name)
    if model is None:
        raise LookupError(
            "no declared table %r; declared: %s (or give a sample file path)"
            % (table_name, ", ".join(sorted(DYNAMIC_TABLES)) or "none"))

    session, closer = _readonly_session()
    if session is None:
        raise RuntimeError(
            "a table input needs the database, and the read-only connection did not open; "
            "give a sample file path instead")
    try:
        import outbox_expand
        from sqlalchemy import text

        query = session.query(model)
        if row_ids:
            query = query.filter(model.row_id.in_(list(row_ids)))
        if where:
            query = query.filter(text(where))
        if not row_ids:
            query = query.limit(int(rows or DEFAULT_INPUT_ROWS))
        found = query.all()
        columns = outbox_expand._data_columns(model)
        payloads = [outbox_expand._synthesize_payload(row, columns, {}) for row in found]
    finally:
        closer()
    return mapper_sdk.payloads_to_df(payloads)


#: The value `raw_for_parser` puts where the frame would be. 🔴 A VALUE, NOT AN EXCEPTION —
#: 「운영이 읽기를 못 하는 포맷」 is the whole reason the author is opening the notebook, so a
#: first cell that raises on it locks them out of the case they came to solve.
UNREADABLE = "DataFrame 으로 못 읽음"

#: Tried in order against the head of the file, first one that decodes wins. Display only —
#: production has no detection step, and inventing one here would teach the author a
#: behaviour their parser will not get.
ENCODING_LADDER = ("utf-8-sig", "utf-8", "cp949", "latin-1")


def raw_for_parser(file_path, *, lines=20, head_bytes=65536):
    """What is actually IN the file, plus production's default read if it survives it.

    Returns `{path, size_bytes, encoding, lines, df, read_refusal}`.

    🔴 `read_refusal` IS A NORMAL STATE. `_read_file_to_dataframe` is `pd.read_csv` /
    `pd.read_excel` by extension; a fixed-width instrument dump or a two-header-row export
    makes it throw, and that throw is the REASON the author is writing a read override. So
    the frame comes back `None` with the reason beside it, and the bytes and decoded lines
    are there either way — those are what a read override is written from.
    """
    path = str(file_path)
    size = os.path.getsize(path) if os.path.exists(path) else None
    with io.open(path, "rb") as handle:
        head = handle.read(head_bytes)

    encoding, text_lines = None, []
    for candidate in ENCODING_LADDER:
        try:
            decoded = head.decode(candidate)
        except Exception:
            continue
        encoding = candidate
        text_lines = decoded.splitlines()[:lines]
        break

    frame, refusal = None, None
    try:
        from parsers.pipeline_base import BasePipelineParser

        frame = BasePipelineParser()._read_file_to_dataframe(path)
    except Exception as exc:
        refusal = "%s: %s: %s" % (UNREADABLE, type(exc).__name__, exc)

    return {"path": path, "size_bytes": size, "encoding": encoding,
            "lines": text_lines, "df": frame, "read_refusal": refusal}


# ---------------------------------------------------------------------------
# 🔴 what the notebook showed better than the bench did — promoted, not copied
# ---------------------------------------------------------------------------

def claimers(file_path, *, scripts_path=None):
    """EVERY parser's answer to `match(file_path)`, claiming nothing.

    🔴 `try_parser` ANSWERS 「who gets this file」; THIS ANSWERS 「who WANTS it」. They are
    different questions and the second one is the one that finds the defect: production takes
    the FIRST class that says yes, so two parsers claiming one file looks exactly like one
    parser claiming it until somebody's rows land in somebody else's table.

    Returns `{rows, load_errors, winners}`; `rows` carries
    `{script, class, match, error, cls}`.
    """
    from parsers.directory_watcher import (SCAN_UNAVAILABLE,
                                           scan_workspace_pipeline_parsers)

    scripts_path = scripts_path or _default_scripts_path()
    rows, load_errors = [], {}

    def visit(filename, obj):
        try:
            hit, error = bool(obj.match(str(file_path))), None
        except Exception as exc:
            hit, error = None, "%s: %s" % (type(exc).__name__, exc)
        rows.append({"script": filename, "class": obj.__name__, "match": hit,
                     "error": error, "cls": obj})
        return None                    # never claims - that is what makes it a survey

    out = scan_workspace_pipeline_parsers(scripts_path, visit, load_errors)
    if out is SCAN_UNAVAILABLE:
        raise FileNotFoundError("the parser workspace is unavailable at %s" % scripts_path)
    return {"rows": rows, "load_errors": load_errors,
            "winners": [r for r in rows if r["match"]]}


def run_stages(parser_cls, file_path, *, rel_path=None, source_root=None):
    """read -> process -> clean, kept APART. Returns `{parser, raw, processed, records}`.

    🔴 THE THREE ARE PRODUCTION'S OWN METHODS IN PRODUCTION'S ORDER, and the two
    attributes the watcher attaches before `parse()` (`rel_path`, `source_root`) are attached
    here too — a parser that reads them must not behave differently on the bench than in the
    pipeline.

    ⚠️ SPLIT BECAUSE `parse()` ANSWERS ONLY 「did it work」. When it does not, the author needs
    to know WHICH of the three broke the assumption, and one return value cannot say.
    """
    from types import SimpleNamespace

    instance = parser_cls()
    instance.rel_path = (rel_path if rel_path is not None
                         else os.path.basename(str(file_path)))
    instance.source_root = source_root
    raw = instance._read_file_to_dataframe(str(file_path))
    processed = instance.process_dataframe(raw.copy(deep=True))
    records = instance.clean_for_postgres(processed)
    return SimpleNamespace(parser=instance, raw=raw, processed=processed, records=records)


def frame_delta(before, after):
    """What the gap between two frames actually IS: columns added, removed, retyped, rows.

    🔴 「돌았다」 IS NOT AN ANSWER WHEN AN ASSUMPTION BROKE. A processing step that silently
    dropped a column, or turned one from a number into a string, produces a frame that looks
    fine and lands wrong — and a shape printed as `(1000, 12) -> (1000, 12)` says nothing
    about which twelve.

    ⚠️ ROW COUNT IS REPORTED, NEVER JUDGED. A step that drops rows is ordinary (a filter) and
    a step that adds them is ordinary (an explode); only the author knows which was meant.

    Returns `{added, removed, retyped, rows_before, rows_after}`.
    """
    # ⚠️ NO `or ()` HERE. A pandas `Index` raises on truthiness, so the idiom that reads as
    # 「default when missing」 turns an ordinary empty frame into a ValueError.
    before_cols = list(getattr(before, "columns", ()))
    after_cols = list(getattr(after, "columns", ()))
    retyped = []
    for name in before_cols:
        if name not in after_cols:
            continue
        was, now = str(before[name].dtype), str(after[name].dtype)
        if was != now:
            retyped.append((str(name), was, now))
    return {"added": [str(c) for c in after_cols if c not in before_cols],
            "removed": [str(c) for c in before_cols if c not in after_cols],
            "retyped": retyped,
            "rows_before": len(before) if before is not None else 0,
            "rows_after": len(after) if after is not None else 0}


#: What the census treats as ordinary in a record on its way to the database.
#: ⚠️ THIS IS THE BENCH'S JUDGEMENT, NOT PRODUCTION'S PREDICATE — say so wherever it is
#: shown. `clean_for_postgres` folds NaN / NaT / Inf to `None` and nothing else, so a
#: `Decimal` or a `set` reaches the driver exactly as the parser produced it. The list is
#: here, named, so it can be argued with rather than being buried in a notebook cell.
JSON_SAFE_TYPES = ("str", "int", "float", "bool", "NoneType",
                   "Timestamp", "datetime", "date")


def value_types(rows, *, sample=2000):
    """The census of Python types in the records, and which of them are not ordinary.

    🔴 THE TYPE THAT ARRIVES IS THE TYPE THAT IS STORED. `clean_for_postgres` repairs NaN,
    NaT and Inf; it does not repair a `Decimal`, a `set`, or a numpy scalar, and those reach
    the driver as the parser made them. Casting belongs in `process_dataframe`, and this is
    where an author finds out that it is needed.

    ⚠️ `sample` BOUNDS THE WALK, and the returned `counted` says how many rows it read — a
    census over 2,000 of 400,000 rows is a sample and must not be shown as a total.
    """
    import collections

    rows = list(rows or ())[:sample]
    counts = collections.Counter(type(value).__name__
                                 for row in rows for value in dict(row).values())
    unknown = sorted(set(counts) - set(JSON_SAFE_TYPES))
    return {"counts": dict(counts), "unknown": unknown, "counted": len(rows)}


def sweep_claims(folder, *, scripts_path=None):
    """`match()` over EVERY file in `folder`, so 「too wide」 and 「too narrow」 are visible.

    🔴 THIS IS WHERE A PARSER FAILS QUIETLY. Too wide and it takes somebody else's file into
    this table; too narrow and its own file leaks to the std parser. Neither shows up until a
    row is sitting under the wrong name, and neither is visible from ONE file — which is all
    `claimers` can answer.

    ⚠️ THE CLASSES ARE LOADED ONCE AND THEN ASKED PER FILE. `claimers` re-walks the
    workspace and re-imports every script on each call, so calling it per file would be a
    folder-sized number of module loads. What is asked per file is `match()` itself —
    production's own predicate, not a copy of it.

    Returns `{files, unclaimed, contested, load_errors}`; `files` carries
    `{file, claimed_by}`.
    """
    found = []
    for root, _dirs, names in os.walk(str(folder)):
        for name in sorted(names):
            found.append(os.path.join(root, name))
    found.sort()
    if not found:
        return {"files": [], "unclaimed": [], "contested": [], "load_errors": {}}

    survey = claimers(found[0], scripts_path=scripts_path)
    classes = [(row["script"], row["cls"]) for row in survey["rows"]]

    files = []
    for path in found:
        hits = []
        for _script, cls in classes:
            try:
                if cls.match(path):
                    hits.append(cls.__name__)
            except Exception as exc:
                # ⚠️ A `match()` THAT THROWS IS NOT A `match()` THAT SAID NO. Production
                # treats it as a decline, but the author has to see which one it was.
                hits.append("%s!%s" % (cls.__name__, type(exc).__name__))
        files.append({"file": path, "claimed_by": hits})

    return {"files": files,
            "unclaimed": [f["file"] for f in files if not f["claimed_by"]],
            "contested": [f for f in files if len(f["claimed_by"]) > 1],
            "load_errors": survey["load_errors"]}


def check_output_columns(rows_or_frame, table_name):
    """Which produced keys the target table does not declare — production's own predicate.

    🔴 `table.c.get(key) is None` IS THE UPSERT'S OWN TEST, verbatim (`crud.py`, the
    `unknown_column` decline). One key the table does not have and the whole fast path
    declines for the whole batch — found here it costs a minute, found in production it
    costs a round trip.

    ⚠️ NO DATABASE IS NEEDED. `init_dynamic_models` builds the real `Table` objects from the
    declaration, so this answers off the declaration the server boots from.

    Returns `{declared, produced, unknown, never_filled}`. `never_filled` is a QUESTION, not
    a fault — a parser that fills half a table is ordinary — and the framework's own columns
    are left out of it by `models.FRAMEWORK_COLUMNS` rather than by a list spelled here.
    """
    _ensure_dynamic_models()
    from database import models

    model = models.DYNAMIC_TABLES.get(table_name)
    if model is None:
        raise LookupError("no declared table %r; declared: %s"
                          % (table_name, ", ".join(sorted(models.DYNAMIC_TABLES)) or "none"))
    table = model.__table__

    produced = []
    for row in _frame_rows(rows_or_frame):
        for key in row:
            if key not in produced:
                produced.append(str(key))

    declared = [c.name for c in table.c]
    unknown = [k for k in produced if table.c.get(k) is None]
    never_filled = sorted(set(declared) - set(produced) - set(models.FRAMEWORK_COLUMNS))
    return {"declared": declared, "produced": produced,
            "unknown": unknown, "never_filled": never_filled}


# ---------------------------------------------------------------------------
# ③ publishing — 「되면 발행 셀이 함수 파일을 만든다」 (S-197)
# ---------------------------------------------------------------------------

class PublishRefused(Exception):
    """⛔ REFUSED BY NAME, AND THE FILE DOES NOT SURVIVE THE REFUSAL. A published file that
    disagrees with the cell it came from is worse than no file: it sits in a folder
    production watches, claims real inputs, and produces something nobody has looked at."""


def _publish_target(directory, name):
    if not str(name).isidentifier():
        raise PublishRefused("%r is not a usable module name" % (name,))
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "%s.py" % name)
    if os.path.exists(target):
        raise PublishRefused(
            "%s already exists; publishing would overwrite a file somebody is running. "
            "Choose another name, or delete that file yourself." % target)
    return target


def _indent(body, spaces):
    """The author's cell body, moved into a function body. Blank lines stay blank."""
    import textwrap

    pad = " " * spaces
    lines = textwrap.dedent(str(body or "").rstrip("\n")).split("\n")
    return "\n".join(pad + line if line.strip() else "" for line in lines)


def _import_published(path, module_name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _discard(path, registered_name=None):
    """Undo a publish. 🔴 THE REGISTRY ENTRY GOES TOO — a name left claimed by a file that no
    longer exists makes the NEXT publish of that name fail for the wrong reason."""
    try:
        os.remove(path)
    except OSError:
        pass
    if registered_name:
        try:
            import mapper_sdk

            mapper_sdk.MAPPER_REGISTRY.pop(registered_name, None)
            getattr(mapper_sdk, "MAPPER_PARAMS", {}).pop(registered_name, None)
        except Exception:
            pass


def cell_body(fn):
    """The BODY of a function the author defined in a free-form cell, at column 0.

    🔴 ONE SEAT MOVES A CELL INTO A FILE, so the author never copies anything. Copying is
    where 「what I ran」 and 「what I shipped」 come apart, and the publisher's comparison exists
    because that is not a hypothetical.

    ⚠️ `inspect.getsource` GIVES THE CELL AS IT WAS LAST **EXECUTED**, not as it is on the
    screen. That is unavoidable and it is precisely why `publish_mapper`/`publish_parser`
    re-run the published file and refuse on disagreement — this function is allowed to be
    stale, and the publish is not.
    """
    import inspect
    import textwrap

    try:
        source = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError) as exc:
        # ⚠️ 「could not get source code」 IS THE ORDINARY WAY THIS FAILS, and on its own it
        # sends the author looking for a bug in their cell. It means the function did not
        # come from a cell or a file at all - a builtin, or something `exec`-ed.
        raise ValueError("cannot read the source of %r; `cell_body` takes a function you "
                         "wrote in a cell: %s" % (fn, exc))
    lines = source.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") and stripped.rstrip().endswith(":"):
            body = "\n".join(lines[index + 1:])
            break
    else:
        raise ValueError("%r does not look like a plain `def` written in a cell" % (fn,))

    body = textwrap.dedent(body).strip("\n")
    if not body.strip():
        raise ValueError("%s has an empty body" % getattr(fn, "__name__", fn))
    # A docstring belongs to the cell, not to the published file, which writes its own.
    return body


MAPPER_TEMPLATE = '''# -*- coding: utf-8 -*-
"""%(name)s - published from the mapper workbench.

The body below is the cell that was RUN. `dev_bench.publish_mapper` re-ran it FROM THIS FILE
against the same frame and compared the result before leaving the file here, so the notebook
and the deployment are the same bytes by construction rather than by somebody remembering to
copy carefully.
"""
import pandas as pd

from mapper_sdk import mapper


@mapper(params=%(params)r)
def %(name)s(df, db):
%(body)s
'''


def publish_mapper(name, params, body_source, *, frame, expected, directory=None):
    """Write the free-form cell out as a decorated mapper, then PROVE it still agrees.

    🔴 THE COMPARISON IS THE POINT, NOT THE FILE. `inspect.getsource` and copy-paste both
    ship 「the cell as it was last executed」, which is not always 「the cell on the screen」 —
    so the published file is imported back, run on the SAME frame the notebook ran on, and
    survives only if it produces the same rows. A disagreement deletes it and refuses by name.

    ⚠️ `frame` IS PASSED, NOT RE-DERIVED. Re-deriving it from a table would re-run the window
    (`rows=` / `where=`), and a different window is a different answer — the comparison would
    then fail for a reason that has nothing to do with the body.

    Returns `{path, who, rows}`; raises `PublishRefused` and leaves nothing behind otherwise.
    """
    directory = directory or os.path.join(paths.SERVER_DIR, "mappers")
    target = _publish_target(directory, name)

    source = MAPPER_TEMPLATE % {"name": name, "params": tuple(params or ()),
                                "body": _indent(body_source, 4)}
    io.open(target, "w", encoding="utf-8").write(source)

    try:
        module = _import_published(target, "bench_published_%s" % name)
        published = getattr(module, name)
    except Exception as exc:
        _discard(target)
        raise PublishRefused("the published file does not import: %s: %s"
                             % (type(exc).__name__, exc))

    inner = getattr(published, "__wrapped__", published)
    session, closer = _readonly_session()
    try:
        got = inner(frame, session)
    except Exception as exc:
        _discard(target, name)
        raise PublishRefused("the published body raised on the same frame: %s: %s"
                             % (type(exc).__name__, exc))
    finally:
        closer()

    mine, theirs = rows_to_tsv(_frame_rows(got)), rows_to_tsv(_frame_rows(expected))
    if mine != theirs:
        _discard(target, name)
        raise PublishRefused(
            "%s produces different rows from the cell it came from, so it was not kept. "
            "Re-run the free-form cell and publish again." % name)
    return {"path": target, "who": name, "rows": _frame_rows(got)}


PARSER_TEMPLATE = '''# -*- coding: utf-8 -*-
"""%(cls)s - published from the parser workbench.

Both bodies below are the cells that were RUN. `dev_bench.publish_parser` re-ran this file
through the production claim -> parse path on the same file and compared the records before
leaving it here.

WARNING: `match()` IS A DRAFT. It claims by filename pattern and nothing else. Narrow it
before this file sits in a folder production watches: the first class that says yes takes the
file, so a wide pattern quietly takes somebody else's input into this table.
"""
import pandas as pd

from pipeline_base import BasePipelineParser


class %(cls)s(BasePipelineParser):

    MATCH_PATTERN = %(pattern)r

    @classmethod
    def match(cls, file_path: str) -> bool:
        import fnmatch

        name = BasePipelineParser.get_basename(file_path).lower()
        return fnmatch.fnmatch(name, cls.MATCH_PATTERN.lower())

    def _read_file_to_dataframe(self, file_path: str) -> pd.DataFrame:
%(read)s

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
%(process)s
'''


def publish_parser(name, read_body, process_body, *, file, expected,
                   match_pattern=None, scripts_path=None):
    """Write the two free-form cells out as a parser, then run the PRODUCTION path on it.

    🔴 THE READ OVERRIDE IS PUBLISHED TOO, and that is the owner's correction: a format
    production's default reader cannot open is the ordinary case, so the notebook authors
    `read_df` as well as `process`, and both land — `_read_file_to_dataframe` and
    `process_dataframe`. (The read method is underscored and is a public extension point;
    `pipeline_base` says so in its own docstring, and renaming it would silently drop every
    workspace override.)

    🔴 AND THE CHECK GOES THROUGH `try_parser`, i.e. claim -> parse. Calling the class
    directly would skip the one thing publishing actually risks: that some OTHER parser in
    the same folder already claims this file, so production would never reach this one.

    Returns `{path, who, rows}`; raises `PublishRefused` and leaves nothing behind otherwise.
    """
    scripts_path = scripts_path or _default_scripts_path()
    target = _publish_target(scripts_path, name)
    class_name = "".join(part[:1].upper() + part[1:] for part in str(name).split("_"))
    pattern = match_pattern or ("*" + os.path.splitext(str(file))[1].lower())

    source = PARSER_TEMPLATE % {"cls": class_name, "pattern": pattern,
                                "read": _indent(read_body, 8),
                                "process": _indent(process_body, 8)}
    io.open(target, "w", encoding="utf-8").write(source)

    result = try_parser(str(file), scripts_path=scripts_path)
    if result["refusal"]:
        _discard(target)
        raise PublishRefused("the published parser did not run: %s" % result["refusal"])
    if not str(result["who"] or "").startswith(os.path.basename(target)):
        claimed_by = result["who"]
        _discard(target)
        raise PublishRefused(
            "%s claims this file first, so the published parser would never see it in "
            "production. Narrow one of the two match() patterns." % claimed_by)

    from parsers.pipeline_base import BasePipelineParser

    theirs = rows_to_tsv(BasePipelineParser().clean_for_postgres(expected))
    if rows_to_tsv(result["rows"]) != theirs:
        _discard(target)
        raise PublishRefused(
            "%s produces different records from the cells it came from, so it was not kept. "
            "Re-run the free-form cells and publish again." % class_name)
    return {"path": target, "who": result["who"], "rows": result["rows"]}


# ---------------------------------------------------------------------------
# the shells read THIS, so a folder is a test
# ---------------------------------------------------------------------------

def run_sample_folder(folder):
    """`<kind>/<name>/input.* (+ rule.json | force.txt)` -> the same result dict.

    🔴 THE CLI AND THE PYTEST FIXTURE BOTH COME HERE. Two entry points that each assembled
    the call would drift, and then 「it works from the command line」 and 「the test passes」
    would be different facts about one mapper.
    """
    folder = os.path.abspath(folder)
    kind = os.path.basename(os.path.dirname(folder))
    name = os.path.basename(folder)
    inputs = sorted(f for f in os.listdir(folder) if f.startswith("input."))
    if not inputs:
        return {"who": None, "rows": [], "refusal": "no input.* in %s" % folder}
    target = os.path.join(folder, inputs[0])

    if kind == PARSER:
        force_file = os.path.join(folder, "force.txt")
        force = None
        if os.path.exists(force_file):
            force = io.open(force_file, encoding="utf-8").read().strip() or None
        # ⚠️ The parser's own folder is the workspace: the sample ships its parser beside its
        # input, so a repository sample needs nothing from the operator's workspace.
        return try_parser(target, force=force, scripts_path=folder)

    # 🔴 THE MAPPER SHIPS BESIDE ITS SAMPLE, exactly as the parser does (판정 13:30), so the
    # folder is self-contained: nothing is needed from the operator's gitignored workspace.
    # Importing it here is what makes `@mapper` run, which is what puts the name in the
    # registry — so this folder is also the first place the one-cell `mapper` path is
    # actually traversed rather than described.
    load_folder_mappers(folder)

    rule_file = os.path.join(folder, "rule.json")
    rule = None
    if os.path.exists(rule_file):
        rule = json.load(io.open(rule_file, encoding="utf-8"))
    mapper_name = (rule or {}).get("mapper") or name
    return try_mapper(mapper_name, target, rule=rule)


def load_folder_mappers(folder):
    """Import every `*.py` beside a sample so its decorators register. Returns refusals.

    ⚠️ PER MODULE, like `mapper_sdk.discover` and for the same reason: one broken sample must
    not cost the others. The module name is prefixed so a sample cannot collide with a real
    module in `sys.modules`.
    """
    import importlib.util

    refusals = {}
    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".py"):
            continue
        module_name = "bench_sample_%s_%s" % (os.path.basename(folder), filename[:-3])
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, os.path.join(folder, filename))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:
            refusals[filename] = "%s: %s" % (type(exc).__name__, exc)
    return refusals


def expected_path(folder):
    return os.path.join(folder, "expected.tsv")


def sample_folders(root, kind=None):
    """Every `<root>/<kind>/<name>/` that has an `input.*`. A folder IS a test."""
    found = []
    for one in (KINDS if kind is None else (kind,)):
        base = os.path.join(root, one)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            if os.path.isdir(folder) and any(
                    f.startswith("input.") for f in os.listdir(folder)):
                found.append(folder)
    return found
