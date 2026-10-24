"""The AI report's loop - one rule runs one report to its end (owner 10-22 ㄱ): at most `loop.steps` steps, `loop.seconds`,
and a context under `loop.context_tokens`. Each step hands the model [1]..[7] (guide `ai_report_tables.md` «에이전트
문맥») and reads one JSON object back: a call to one of the reads (`report_reads.Report`), or done - read enough.
Then one write call (owner 10-23 ㄱ) hands it every table read and takes the texts - also when a step or time cap
ended the reading, so the report says what was read. Nothing here writes - `run` answers what the mapper keeps.

  [1] instructions   prompts.role · rules · functions.<read>.about (blank: the text below) + the answer's form, the
                     reads and their arguments, the step cap and this step
  [2] prompts        select · style · compare, as written
  [3] this request   evaluation · compare sets · note
  [4] conditions     the condition table folded - value -> wafers
  [5] earlier steps  one line each
  [6] last result    the previous step's result as the read summed it up (`context`), never its whole table
  [7] budget         «used ~N of B tokens, K steps left»

Over budget: [6]'s rows are cut, then [4]'s; still over, the report stops «context over budget». The tokens are
reckoned from characters and corrected, call by call, by what the gateway said it counted (lead 10-22 ruling 3)."""
from __future__ import annotations

import json
import logging
import math
import os
import time

from chain import report_reads, report_shape

logger = logging.getLogger("Chain")

DEFAULT_LOOP = {"steps": 8, "seconds": 300, "context_tokens": 16000}
#: Characters a token is reckoned at before a gateway has said how many it counted.
CHARS_PER_TOKEN = 4.0
#: The product's text for a prompt cell the declaration leaves blank.
ROLE = ("You write a short report on a test evaluation from the reads below. Every number comes from a read; "
        "you never compute or invent one.")
RULES = ("Pick the wafers by their conditions. Call one read per step. When you have read what the report needs, "
         "answer done. A unit is named by its key columns; a units line lists one report unit and its parts - "
         "write about it as one.")
#: The write call's own line: what it is for and the answer's form.
WRITE = ("Write the report from the tables read below - every number as a table says it. Answer one JSON object: "
         '{"done": {%s}}')
STOP_NO_TEXT = "the write call answered no text"
ABOUT = {
    "conditions": "the wafers whose conditions hold a keyword, or every condition value with its wafer count",
    "yield_by": "the summary table - items down, wafers across, each cell x% (F/N); by: a condition whose values "
                "become the columns; rows: the condition rows to show (a name keeps the names under it), all if none",
    "pareto": "the items by fail chips over the wafers, with the cumulative share",
    "trend": "each item's share wafer by wafer in time order - first, last, least, most",
    "images": "defect images of this evaluation's wafers where the item occurred, put in the report",
    "candidates": "the recent evaluations compare wafers may come from - name, date, wafers, conditions",
    "compare": "the compare sets' wafers (sets), or compare wafers from the recent evaluations (evaluations, wafers), "
               "read beside this evaluation's in every table after it; why: the candidates you took and why",
}
ARGS = {"conditions": ("keyword",), "yield_by": ("wafers", "by", "rows"), "pareto": ("wafers",), "trend": ("wafers", "items"),
        "images": ("wafers", "items"), "candidates": (), "compare": ("sets", "evaluations", "wafers")}
WAFERS_SAID = 'wafers: a list of wafer names, "all", or {"where": {"<condition>": "<value>"}}'

STOP_STEPS = "step cap %d"
STOP_SECONDS = "time cap %d s"
STOP_CONTEXT = "context over budget"
STOP_MODEL = "the language model call was refused: %s"
DONE, STOPPED = "done", "stopped"
#: What is still to send: a marker beside a done report whose rule has `send_to` - {"rule", "tries"} - and one the
#: address would not take, {"rule", "why"} (`send_waiting`; owner 10-23: no state column, no table).
SEND_MARK, SEND_FAILED_MARK = ".send", ".send_failed"
#: A file is POSTed at most this many times, one try a sweep (owner 10-23 «3 번 다시»).
SEND_TRIES = 3
SEND_TIMEOUT_SECONDS = 60
#: Files one sweep sends at most a rule - the rest wait for the next.
SEND_PAGE = 20


def limits(spec) -> dict:
    """The loop's three caps - the declaration's, or the product's."""
    written = (spec or {}).get("loop") or {}
    return {cell: written.get(cell) or DEFAULT_LOOP[cell] for cell in DEFAULT_LOOP}


def text_slots(spec) -> list:
    return [str(slot["slot"]) for slot in report_shape.layout(spec) if slot.get("kind") == "text"]


def reckon(text) -> float:
    """Tokens before a gateway counts: ASCII at CHARS_PER_TOKEN a token, any other character a token of its own
    (lead 10-23: Korean reckoned at 4 a token came out under the English of the same sense)."""
    wide = sum(1 for ch in text if ord(ch) > 127)
    return (len(text) - wide) / CHARS_PER_TOKEN + wide


class Budget:
    """Tokens reckoned from characters, the ratio corrected by each call's counted prompt tokens."""

    def __init__(self, cap):
        self.cap, self.ratio = cap, 1.0

    def tokens(self, text) -> int:
        return int(math.ceil(reckon(text) * self.ratio))

    def correct(self, text, counted):
        reckoned = reckon(text)
        if counted and reckoned:
            self.ratio = counted / reckoned


def _instructions(spec, step, cap):
    prompts = (spec or {}).get("prompts") or {}
    functions = prompts.get(report_shape.FUNCTIONS_CELL) or {}
    lines = [prompts.get("role") or ROLE, prompts.get("rules") or RULES, "Reads:"]
    for read in report_shape.READS:
        about = (functions.get(read) or {}).get(report_shape.ABOUT_CELL) or ABOUT[read]
        lines.append("  %s(%s) - %s" % (read, ", ".join(ARGS[read]), about))
    lines.append("  " + WAFERS_SAID)
    lines.append('Answer one JSON object: {"call": "<read>", "args": {...}, "why": "..."} or {"done": {}} when you have read enough')
    lines.append("This is step %d of %d." % (step, cap))
    return lines


def _prompts(spec, cells=("select", "style", "compare", "control")):
    prompts = (spec or {}).get("prompts") or {}
    return ["%s: %s" % (cell.capitalize(), prompts[cell]) for cell in cells if prompts.get(cell)]


def _request(request):
    return ["Evaluation: %s" % request.get("evaluation"),
            "Compare sets: %s" % (", ".join(request.get("sets") or ()) or "the declaration's default"),
            "Note: %s" % (request.get("note") or "none")]


def _said(call, args):
    return "%s(%s)" % (call, json.dumps(args, ensure_ascii=False, sort_keys=True) if args else "")


def compose(spec, request, conditions, steps, previous, budget, step, cap):
    """The step's prompt and what was cut to fit it, or (None, cut) when even [4] and [6] at their least do not."""
    head = _instructions(spec, step, cap) + _prompts(spec) + _request(request)
    earlier = ["step %d: %s -> %s" % (s["step"], s["call"], s["summary"]) for s in steps[:-1]]
    last_head = (["Last result, step %d: %s" % (steps[-1]["step"], steps[-1]["call"])] if steps else [])
    rows6, rows4 = list(previous), list(conditions)
    cut = {}
    while True:
        body = head + ["Conditions:"] + rows4 + (["Earlier steps:"] + earlier if earlier else []) + last_head + rows6
        text = "\n".join(body)
        used = budget.tokens(text + "\nused ~%d of %d tokens, %d steps left" % (budget.cap, budget.cap, cap))
        if used <= budget.cap:
            return text + "\nused ~%d of %d tokens, %d steps left" % (used, budget.cap, cap - step), cut
        if rows6:
            rows6 = rows6[:len(rows6) // 2]
            cut["6"] = len(rows6)
        elif len(rows4) > 1:
            rows4 = rows4[:max(1, len(rows4) // 2)]
            cut["4"] = len(rows4)
        else:
            return None, cut


def compose_write(spec, request, reads, budget):
    """The write call's prompt - role · rules · the write line · style · compare · control · the request · every table
    read (`reads`: [(step, call, lines)]) - and what was cut, or (None, cut) when the tables at no rows do not fit.
    Over budget the oldest read loses half its rows first (lead 10-23)."""
    prompts = (spec or {}).get("prompts") or {}
    slots = ", ".join('"%s": "<text>"' % slot for slot in text_slots(spec))
    head = ([prompts.get("role") or ROLE] + ([prompts["rules"]] if prompts.get("rules") else []) + [WRITE % slots]
            + _prompts(spec, ("style", "compare", "control")) + _request(request) + ["Tables read:"])
    kept = [list(lines) for _step, _call, lines in reads]
    cut = {}
    while True:
        body = list(head)
        for (step, call, _lines), lines in zip(reads, kept):
            body += ["step %d: %s" % (step, call)] + lines
        text = "\n".join(body)
        if budget.tokens(text) <= budget.cap:
            return text, cut
        at = next((n for n, lines in enumerate(kept) if lines), None)
        if at is None:
            return None, cut
        kept[at] = kept[at][:len(kept[at]) // 2]
        cut["step %d %s" % (reads[at][0], reads[at][1])] = len(kept[at])


def _ask(prompt, ask):
    """-> (the answer, the prompt tokens the gateway counted or None)."""
    usage = {}
    said = ask(prompt, usage=usage)
    return said, usage.get("prompt_tokens")


def _call(report, said, seen):
    """One answer -> (the read's answer, or None, why it was refused)."""
    call, args = said.get("call"), said.get("args") or {}
    if call not in report_shape.READS:
        return None, "%r is not a read - one of %s" % (call, ", ".join(report_shape.READS))
    if not isinstance(args, dict):
        return None, "args is an object of %s" % ", ".join(ARGS[call])
    unknown = sorted(set(args) - set(ARGS[call]))
    if unknown:
        return None, "%s is not an argument of %s - one of %s" % (unknown[0], call, ", ".join(ARGS[call]))
    key = _said(call, args)
    if key in seen:
        return None, "the same call as step %d - its result is above; call another read or answer done" % seen[key]
    try:
        return getattr(report, call)(**args), None
    except report_reads.ReadRefused as refused:
        logger.warning("[report] %s(%s) refused: %s", call, args, refused, exc_info=refused)
        return None, str(refused)
    except Exception as exc:                                        # noqa: BLE001 - one read's data, said to the model
        logger.error("[Report] %s failed: %s: %s", call, type(exc).__name__, exc, exc_info=exc)
        return None, "the read failed: %s: %s" % (type(exc).__name__, exc)


def run(report, spec, request, ask=None, clock=time.monotonic):
    """One report's steps -> {"state", "reason", "steps", "texts", "tables"}. `request`: evaluation · sets (blank:
    the declaration's default) · note. `ask(prompt, usage=)`: the model (`utils.llm.ask_json`)."""
    from utils import heartbeat, llm

    ask = ask or llm.ask_json
    caps = limits(spec)
    budget = Budget(caps["context_tokens"])
    started = clock()
    if request.get("sets") or (report_shape.sets_role(spec) or {}).get(report_shape.SETS_DEFAULT):
        report.compare(request.get("sets"))
    conditions = report.conditions()["context"].splitlines()
    steps, previous, seen, tables = [], [], {}, {}
    reads = [(0, "conditions()", conditions)]                # what the write call is handed - the folded conditions first
    out = {"state": STOPPED, "reason": STOP_STEPS % caps["steps"], "steps": steps, "texts": {}, "tables": tables}
    for step in range(1, caps["steps"] + 1):
        if clock() - started >= caps["seconds"]:
            out["reason"] = STOP_SECONDS % caps["seconds"]
            break
        heartbeat.progress("report step %d" % step)
        prompt, cut = compose(spec, request, conditions, steps, previous, budget, step, caps["steps"])
        if prompt is None:
            out["reason"] = STOP_CONTEXT
            break
        began = clock()
        try:
            said, counted = _ask(prompt, ask)
        except llm.LlmRefused as refused:
            out["reason"] = STOP_MODEL % refused
            break
        budget.correct(prompt, counted)
        record = {"step": step, "tokens": counted or budget.tokens(prompt), "cut": cut}
        if isinstance(said.get("done"), dict):
            record.update(call="done", summary="done", seconds=clock() - began, refused=None)
            steps.append(record)
            out.update(state=DONE, reason=None)
            break
        answer, refused = _call(report, said, seen)
        record.update(call=_said(said.get("call"), said.get("args")), seconds=clock() - began, refused=refused,
                      why=str(said.get("why") or "").strip() or None)
        if refused is None:
            seen[record["call"]] = step
            if said["call"] in report_shape.TABLE_FILLS:
                tables[said["call"]] = answer["html"]
            previous = answer["context"].splitlines()
            reads.append((step, record["call"], previous))
        else:
            previous = ["refused: " + refused]
        record["summary"] = (previous[0] if previous else "")[:200]
        record["read"] = previous[1:]                       # the Evidence's lines under it (lead 10-23)
        steps.append(record)
    _product_reads(report, spec, tables, reads, steps, clock)
    if out["state"] == DONE or out["reason"] in (STOP_STEPS % caps["steps"], STOP_SECONDS % caps["seconds"]):
        _write(spec, request, reads, budget, ask, clock, out)
    return out


def filled_slots(spec) -> tuple:
    """(the table reads, whether the images) the file shows - the layout's slots, or a template's marks."""
    from chain import report_template

    template = (spec or {}).get("template")
    if isinstance(template, str) and template.strip():
        marks = {name for _s, _e, name in report_template.read(template).slots}
        return ([fill for fill in report_shape.TABLE_FILLS if report_template.TABLE_PREFIX + fill in marks],
                "images" in marks)
    slots = report_shape.layout(spec)
    return ([slot.get("fill") for slot in slots if slot.get("kind") == "table"],
            any(slot.get("kind") == "image" for slot in slots))


def _product_reads(report, spec, tables, reads, steps, clock):
    """The file's tables and images the model did not read, read by the product with no arguments - this evaluation's
    wafers and every group beside them (owner: AI makes rules, the product does the work; lead 10-24 - the model
    writes only the text slots). A step each in the Evidence, «product <read>()», and the write call reads them."""
    fills, image = filled_slots(spec)
    calls = [fill for fill in dict.fromkeys(fills) if fill not in tables]
    if image and not report.embedded and (spec or {}).get("images"):
        calls.append("images")
    alone = False
    if calls and len(report.groups) == 1:                  # the model compared nothing - the declaration's comparison
        began = clock()
        try:
            lines, refused = report.declared_compare(), None
        except report_reads.ReadRefused as said:
            logger.warning("[report] compare() refused: %s", said, exc_info=said)
            lines, refused, alone = ["refused: %s" % said], str(said), True
        reads.append((len(steps) + 1, "product compare()", lines))
        steps.append({"step": len(steps) + 1, "tokens": 0, "cut": {}, "call": "product compare()",
                      "seconds": clock() - began, "refused": refused, "summary": lines[0][:200] if lines else "",
                      "read": lines[1:]})
    for call in calls:
        began = clock()
        try:
            answer, refused = getattr(report, call)(), None
        except report_reads.ReadRefused as said:
            logger.warning("[report] %s() refused: %s", call, said, exc_info=said)
            answer, refused = None, str(said)
        lines = answer["context"].splitlines() if answer else ["refused: " + refused]
        name = "product %s()" % call
        if answer:
            if call in report_shape.TABLE_FILLS:
                tables[call] = dict(answer["html"], note=report_shape.word(spec, "no_control")) if alone and \
                    isinstance(answer["html"], dict) else answer["html"]
            reads.append((len(steps) + 1, name, lines))
        steps.append({"step": len(steps) + 1, "tokens": 0, "cut": {}, "call": name, "seconds": clock() - began,
                      "refused": refused, "summary": (lines[0] if lines else "")[:200], "read": lines[1:]})


def _write(spec, request, reads, budget, ask, clock, out):
    """The one write call: every table read -> the texts. A cap that ended the reading stays the reason."""
    from utils import llm

    prompt, cut = compose_write(spec, request, reads, budget)
    if prompt is None:
        out.update(state=STOPPED, reason=STOP_CONTEXT)
        return
    began = clock()
    try:
        said, counted = _ask(prompt, ask)
    except llm.LlmRefused as refused:
        out.update(state=STOPPED, reason=STOP_MODEL % refused)
        return
    budget.correct(prompt, counted)
    texts = said.get("done") if isinstance(said.get("done"), dict) else None
    out["steps"].append({"step": len(out["steps"]) + 1, "tokens": counted or budget.tokens(prompt), "cut": cut,
                         "call": "write", "seconds": clock() - began, "refused": None if texts else STOP_NO_TEXT,
                         "summary": "%d text(s) from %d table(s) read" % (len(texts or {}), len(reads))})
    if texts is None:
        if out["state"] == DONE:
            out.update(state=STOPPED, reason=STOP_NO_TEXT)
        return
    out["texts"] = {slot: str(texts.get(slot) or "") for slot in text_slots(spec)}


def _steps_text(out, report):
    """The Evidence: the report's state and why first (no column holds them, owner 10-23), then each step - its first
    line, and what else it read under it (lead 10-23: the candidates were there, the Evidence said only the head)."""
    lines = [out["state"] + (" - %s" % out["reason"] if out["reason"] else "")]
    for s in out["steps"]:
        lines.append("%d %s - %s" % (s["step"], s["call"], s.get("refused") or s["summary"]))
        if s.get("why"):                   # the model's reason for the call (owner 10-24 «웨이퍼 리스트 뽑은 근거 대라고 해»)
            lines.append("    why: " + s["why"])
        lines += ["    " + line for line in s.get("read") or ()]
    if report.overlaps:
        lines.append("names two wafers share: %s" % ", ".join(sorted(report.overlaps)))
    lines += report.pick_basis()
    return "\n".join(lines)


def _this_wafer(db, spec, wafer):
    """The wafer ({column: value}, its report table's wafer columns) in this report's own group, its evaluation the one
    a control group leaves out (owner 10-23
    «최근 평가인데 스플릿 테이블 보고 고르게»: the recent evaluations' split summaries, `control.same` narrowing them).
    -> (the reads, that evaluation)."""
    report = report_reads.Report(db, spec, None, only=wafer)
    return report, report.evaluation


def answer(db, rule, row_ids, ask=None, clock=time.monotonic):
    """The report rule's mapper: its report table's rows handed, by wafer (`report_shape.report_key`) -> one report a
    wafer, its file path written on that wafer's row (`results.file`, owner 10-23 «리포트용 표가 따로» · «wafer, 보고서
    파일 경로 이 두 개가 최종 출력»; the summary table is only read). The file is kept before anything is proposed; its
    state, why and steps are its Evidence and a chain log line each. A done report with `send_to` leaves its marker
    (`SEND_MARK`) - the chain worker's upkeep POSTs it (`send_waiting`)."""
    import datetime

    from chain import report_html
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(str(rule.get("trigger_table") or ""))
    if model is None or not row_ids:
        return {"updates": [], "refusal": "no report table row reached this mapper"}
    spec = rule.get("params") or {}
    name = str(rule.get("name") or "")
    keys = report_shape.report_key(spec, rule.get("trigger_table"))
    results = spec[report_shape.RESULTS_CELL]
    by_wafer = {}
    for row in db.query(model).filter(model.row_id.in_(list(row_ids))).all():
        wafer = report_reads._parts(getattr(row, c) for c in keys)
        if not all(crud.is_blank_value(part) for part in wafer):
            by_wafer.setdefault(wafer, []).append(row.row_id)
    updates = []
    for wafer, rows in sorted(by_wafer.items(), key=lambda pair: report_reads.label(pair[0])):
        said, report = report_reads.label(wafer), None
        try:
            report, evaluation = _this_wafer(db, spec, dict(zip(keys, wafer)))
            out = run(report, spec, {"evaluation": evaluation, "note": None, "sets": []}, ask=ask, clock=clock)
        except report_reads.ReadRefused as refused:
            logger.error("[Report] %s wafer %s stopped: %s", name, said, refused, exc_info=refused)
            out = {"state": STOPPED, "reason": str(refused), "steps": [], "texts": {}, "tables": {}}
        except Exception as exc:                                    # noqa: BLE001 - this wafer stops, the others go on
            logger.error("[Report] %s wafer %s failed: %s: %s", name, said, type(exc).__name__, exc, exc_info=exc)
            out = {"state": STOPPED, "reason": "%s: %s" % (type(exc).__name__, exc), "steps": [], "texts": {},
                   "tables": {}}
        for s in out["steps"]:
            logger.info("[Report] %s wafer %s step %d %s - %s", name, said, s["step"], s["call"],
                        s.get("refused") or s["summary"])
        cells = {results["file"]: None}
        if report is not None:
            try:
                made = datetime.datetime.now().astimezone()
                page = report_html.page("%s %s" % (said, report_shape.word(spec, "report")), "%s · %s" % (
                    name, made.isoformat(timespec="seconds")), spec, out["tables"], report.embedded, out["texts"],
                    evidence=_steps_text(out, report).splitlines())
                cells[results["file"]], _sha = report_html.keep(said, page)
                _mark(cells[results["file"]], name if out["state"] == DONE and spec.get(report_shape.SEND_TO) else None)
            except Exception as exc:                                # noqa: BLE001 - this wafer's page, the others go on
                logger.error("[Report] %s wafer %s page failed: %s: %s", name, said, type(exc).__name__, exc,
                             exc_info=exc)
                cells = {results["file"]: None}
                out = dict(out, state=STOPPED, reason="the page failed: %s: %s" % (type(exc).__name__, exc))
        logger.info("[Report] %s wafer %s: %s%s", name, said, out["state"], " - %s" % out["reason"] if out["reason"] else "")
        for row_id in rows:
            updates.append({"row_id": row_id, "source_name": crud.CHAIN_SOURCE, "updated_by": name,
                            "origin_row_id": row_id,
                            "updates": {c: v for c, v in cells.items() if not crud.is_blank_value(v)},
                            "withdraw": sorted(c for c, v in cells.items() if crud.is_blank_value(v))})
    return {"updates": updates}


def _post(send_to, path):
    """One POST of a report's file to `<send_to>/<file name>` (tools/report_receiver/receive.py) -> None, or why not.
    Straight to the address - the receiver is on the site's own network, not behind the server's proxy."""
    import urllib.error
    import urllib.request

    from error_said import told

    url = "%s/%s" % (send_to.rstrip("/"), os.path.basename(path))
    try:
        with open(path, "rb") as handle:
            body = handle.read()
        request = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "text/html; charset=utf-8"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=SEND_TIMEOUT_SECONDS) as answer_:
            return None if 200 <= answer_.status < 300 else "%s answered %d" % (url, answer_.status)
    except urllib.error.HTTPError as refused:
        return "%s answered %d: %s" % (url, refused.code, refused.read()[:200].decode("utf-8", "replace"))
    except Exception as exc:                                       # noqa: BLE001 - a send that failed is said, not raised
        return "%s: %s" % (url, told(exc))


def _mark(path, rule):
    """A made report's send marker: `rule` - to send for that rule, tries 0 (a remade report sends again, an earlier
    failure taken away); None - nothing to send."""
    import json

    for stale in (path + SEND_MARK, path + SEND_FAILED_MARK):
        if os.path.exists(stale):
            os.remove(stale)
    if rule:
        with open(path + SEND_MARK, "w", encoding="utf-8") as handle:
            json.dump({"rule": rule, "tries": 0}, handle)


def send_waiting(rules, post=None):
    """The made reports a rule's `send_to` has not taken yet (their `SEND_MARK`), POSTed - off the chain's slots, from
    the chain worker's upkeep beside the undelivered-broadcast sweep (lead 10-23 ㄱ). Sent -> its marker goes; a try
    that failed is tried again the next sweep, SEND_TRIES in all (the marker counts), then `SEND_FAILED_MARK` and why.
    SEND_PAGE files a rule a sweep. -> (files sent, files failed)."""
    import glob
    import json

    import paths
    from chain import report_html

    post = post or _post
    marks = {}
    for mark in sorted(glob.glob(os.path.join(paths.DATA_ROOT, report_html.REPORTS_DIRNAME, "*" + SEND_MARK))):
        try:
            with open(mark, encoding="utf-8") as handle:
                said = json.load(handle)
        except (OSError, ValueError):
            continue
        marks.setdefault(str(said.get("rule") or ""), []).append((mark, int(said.get("tries") or 0)))
    sent = failed = 0
    for rule in rules or ():
        spec = rule.get("params") or {}
        name = str(rule.get("name") or "")
        if rule.get("mapper") != report_shape.REPORT_MAPPER or not spec.get(report_shape.SEND_TO):
            continue
        for mark, tries in marks.get(name, [])[:SEND_PAGE]:
            path = mark[:-len(SEND_MARK)]
            why = post(spec[report_shape.SEND_TO], path)
            if why is None:
                os.remove(mark)
                sent += 1
                logger.info("[Report] %s sent %s", name, path)
                continue
            tries += 1
            logger.warning("[Report] %s send %s, try %d of %d: %s", name, path, tries, SEND_TRIES, why)
            if tries < SEND_TRIES:
                with open(mark, "w", encoding="utf-8") as handle:
                    json.dump({"rule": name, "tries": tries}, handle)
                continue
            with open(path + SEND_FAILED_MARK, "w", encoding="utf-8") as handle:
                json.dump({"rule": name, "why": why}, handle)
            os.remove(mark)
            failed += 1
            logger.warning("[Report] %s send failed %s: %s - replay the wafer to make and send it again", name, path, why)
    return sent, failed
