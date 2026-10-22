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
import math
import time

from chain import report_reads, report_shape

DEFAULT_LOOP = {"steps": 8, "seconds": 300, "context_tokens": 16000}
#: Characters a token is reckoned at before a gateway has said how many it counted.
CHARS_PER_TOKEN = 4.0
#: The product's text for a prompt cell the declaration leaves blank.
ROLE = ("You write a short report on a test evaluation from the reads below. Every number comes from a read; "
        "you never compute or invent one.")
RULES = ("Pick the wafers by their conditions. Call one read per step. When you have read what the report needs, "
         "answer done.")
#: The write call's own line: what it is for and the answer's form.
WRITE = ("Write the report from the tables read below - every number as a table says it. Answer one JSON object: "
         '{"done": {%s}}')
STOP_NO_TEXT = "the write call answered no text"
ABOUT = {
    "conditions": "the wafers whose conditions hold a keyword, or every condition value with its wafer count",
    "yield_by": "the summary table - items down, wafers across by time, each cell x% (F/N); by: a condition whose "
                "values become the columns",
    "pareto": "the items by fail chips over the wafers, with the cumulative share",
    "trend": "each item's share wafer by wafer in time order - first, last, least, most",
    "images": "defect images of this evaluation's wafers where the item occurred, put in the report",
    "candidates": "the recent evaluations a control group may come from - name, date, wafers, conditions",
    "compare": "the compare sets' wafers (sets), or a control group from the recent evaluations (evaluations, wafers), "
               "read beside this evaluation's in every table after it",
}
ARGS = {"conditions": ("keyword",), "yield_by": ("wafers", "by"), "pareto": ("wafers",), "trend": ("wafers", "items"),
        "images": ("wafers", "items"), "candidates": (), "compare": ("sets", "evaluations", "wafers")}
WAFERS_SAID = 'wafers: a list of wafer names, "all", or {"where": {"<condition>": "<value>"}}'

STOP_STEPS = "step cap %d"
STOP_SECONDS = "time cap %d s"
STOP_CONTEXT = "context over budget"
STOP_MODEL = "the language model call was refused: %s"
DONE, STOPPED = "done", "stopped"


def limits(spec) -> dict:
    """The loop's three caps - the declaration's, or the product's."""
    written = (spec or {}).get("loop") or {}
    return {cell: written.get(cell) or DEFAULT_LOOP[cell] for cell in DEFAULT_LOOP}


def text_slots(spec) -> list:
    return [str(slot["slot"]) for slot in (spec or {}).get("layout") or () if slot.get("kind") == "text"]


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
    lines.append('Answer one JSON object: {"call": "<read>", "args": {...}} or {"done": {}} when you have read enough')
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
        return None, str(refused)


def run(report, spec, request, ask=None, clock=time.monotonic):
    """One report's steps -> {"state", "reason", "steps", "texts", "tables"}. `request`: evaluation · sets (blank:
    the declaration's default) · note. `ask(prompt, usage=)`: the model (`utils.llm.ask_json`)."""
    from utils import heartbeat, llm

    ask = ask or llm.ask_json
    caps = limits(spec)
    budget = Budget(caps["context_tokens"])
    started = clock()
    if request.get("sets") or ((spec or {}).get("sets") or {}).get(report_shape.SETS_DEFAULT):
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
        record.update(call=_said(said.get("call"), said.get("args")), seconds=clock() - began, refused=refused)
        if refused is None:
            seen[record["call"]] = step
            if said["call"] in report_shape.TABLE_FILLS:
                tables[said["call"]] = answer["html"]
            previous = answer["context"].splitlines()
            reads.append((step, record["call"], previous))
        else:
            previous = ["refused: " + refused]
        record["summary"] = (previous[0] if previous else "")[:200]
        steps.append(record)
    if out["state"] == DONE or out["reason"] in (STOP_STEPS % caps["steps"], STOP_SECONDS % caps["seconds"]):
        _write(spec, request, reads, budget, ask, clock, out)
    return out


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
    lines = ["%d %s - %s" % (s["step"], s["call"], s.get("refused") or s["summary"]) for s in out["steps"]]
    if report.overlaps:
        lines.append("names two wafers share: %s" % ", ".join(sorted(report.overlaps)))
    return "\n".join(lines)


def answer(db, rule, row_ids, ask=None, clock=time.monotonic):
    """The report rule's mapper: each request row handed -> its report row (the rule's target) and, into the tables
    its writes cell names, its step rows and the wafers it used - each replaced by request, so a remake that names
    fewer leaves no old row (lead 10-22). The HTML file is kept before anything is proposed."""
    import datetime

    import product_tables
    from chain import report_html
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(str(rule.get("trigger_table") or ""))
    if model is None or not row_ids:
        return {"updates": [], "refusal": "no report request reached this mapper"}
    spec = rule.get("params") or {}
    name = str(rule.get("name") or "")
    updates, steps, wafers = [], [], []

    def item(row, cells):
        return {"updates": cells, "source_name": crud.CHAIN_SOURCE, "updated_by": name, "origin_row_id": row.row_id}

    for request in db.query(model).filter(model.row_id.in_(list(row_ids))).all():
        if crud.is_blank_value(request.request_id):
            continue
        asked = {"evaluation": request.eval_id, "note": request.note,
                 "sets": [s.strip() for s in str(request.compare_sets or "").split(",") if s.strip()]}
        try:
            report = report_reads.Report(db, spec, str(request.eval_id))
            out = run(report, spec, asked, ask=ask, clock=clock)
        except report_reads.ReadRefused as refused:
            report, out = None, {"state": STOPPED, "reason": str(refused), "steps": [], "texts": {}, "tables": {}}
        made = datetime.datetime.now().astimezone()
        cells = {"request_id": request.request_id, "setting": request.setting, "state": out["state"],
                 "reason": out["reason"], "made_at": made.isoformat()}
        if report is not None:
            page = report_html.build("%s %s" % (request.eval_id, report_shape.word(spec, "report")), "%s · %s · %s" % (
                request.request_id, name, made.isoformat(timespec="seconds")), spec, out["tables"], report.embedded,
                out["texts"])
            cells["file_path"], cells["file_hash"] = report_html.keep(str(request.request_id), page)
            cells["steps"] = _steps_text(out, report)
            for seq, wafer in enumerate(report._ordered(list(report.used)), 1):
                keys = dict(zip(product_tables.REPORT_WAFER_KEYS, wafer))
                wafers.append((request, dict(keys, request_id=request.request_id, seq=seq,
                                             set_name=report.used[wafer])))
        for s in out["steps"]:
            steps.append((request, {"request_id": request.request_id, "step": s["step"], "call": s["call"],
                                    "summary": s["summary"], "tokens": s["tokens"], "seconds": round(s["seconds"], 3),
                                    "refused": s["refused"]}))
        updates.append(item(request, cells))
    batches = []
    for table, rows in ((product_tables.REPORT_STEP_TABLE, steps), (product_tables.REPORT_WAFER_TABLE, wafers)):
        by_request = {}
        for request, cells in rows:
            by_request.setdefault(request.request_id, []).append(item(request, cells))
        for done in updates:
            rid = done["updates"]["request_id"]
            batches.append({"target_table": table, "replace_map": True, "scope": {"request_id": rid},
                            "updates": by_request.get(rid, [])})
    return {"updates": updates, "batches": batches}
