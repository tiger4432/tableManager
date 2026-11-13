"""The AI report's loop - one rule runs one report to its end (owner 10-22 ㄱ): at most `loop.steps` steps, `loop.seconds`,
and a context under `loop.context_tokens`. Each step hands the model [1]..[7] (guide `ai_report_tables.md` «에이전트
문맥») and reads one JSON object back: a call to one of the reads (`report_reads.Report`), or done - read enough.
Then one write call (owner 10-23 ㄱ) hands it every table read and takes the texts - also when a step or time cap
ended the reading, so the report says what was read. Nothing here writes - `run` answers what the mapper keeps.
With `derive.report.causes` (owner 10-25), before the write: the model picks seeds from the declared type's nodes by the
tables read, the product walks the static layer from them, and the candidates go to the write call with the tables;
then the model relates them to the report's conditions, those stand as yield_by rows, and each candidate is said
with its conditions' values per column - or as to be filled when none has a value on the report's wafers.

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
WRITE = ("Write the report from the tables read below - every number as a table says it; candidate factors walked from "
         "the seeds, when given, ground the detailed analysis. Answer one JSON object: "
         '{"done": {%s}}')
STOP_NO_TEXT = "the write call answered no text"
#: The seed call's line, over the nodes it picks from (`report_reads.Report.seed_nodes`).
SEEDS = ("Pick the seed node(s) of a cause walk from the %s nodes below, by the tables read below. Answer one JSON "
         'object: {"seeds": ["<name>", ...], "why": "..."}')
#: The relate call's line, over the report's condition names (`report_reads.Report.condition_names`).
RELATE = ("Relate each candidate factor below to the report's conditions that are it or set it - names from the list, "
          'none if none. Answer one JSON object: {"conditions": {"<candidate>": ["<condition>", ...]}, "why": "..."}')
RELATED_CALL = "candidate conditions"
#: the Evidence step of the quantities' measured values (causes.values, lead 10-27)
VALUES_CALL = "quantity values"
ABOUT = {
    "conditions": "the wafers whose conditions hold a keyword, or every condition value with its wafer count",
    "yield_by": "the summary table - items down, wafers across, each cell x% (F/N); by: one condition name exactly as "
                "conditions() lists it - leave by out for a column a wafer; rows: the condition rows to put first, the ones most related to the "
                "wafers' titles first (a name keeps the names under it) - the other differing rows follow",
    "pareto": "the items by fail chips over the wafers, with the cumulative share",
    "trend": "each item's share wafer by wafer in time order - first, last, least, most",
    "images": "defect images of this evaluation's wafers where the item occurred, put in the report",
    "candidates": "the recent evaluations compare wafers may come from - name, date, wafers, conditions",
    "compare": "the compare sets' wafers (sets), or compare wafers from the recent evaluations (evaluations, wafers), "
               "read beside this evaluation's in every table after it; why: the candidates you took and why; take enough for a trend",
}
ARGS = {"conditions": ("keyword",), "yield_by": ("wafers", "by", "rows"), "pareto": ("wafers",), "trend": ("wafers", "items"),
        "images": ("wafers", "items"), "candidates": (), "compare": ("sets", "evaluations", "wafers")}
#: conditions.most said on the read that takes `rows` (owner 10-26)
ROWS_MOST = "; rows: %d at most"
WAFERS_SAID = 'wafers: a list of wafer names, "all", or {"where": {"<a condition name as conditions() lists it>": "<value>"}}'

STOP_STEPS = "step cap %d"
STOP_SECONDS = "time cap %d s"
STOP_CONTEXT = "context over budget"
STOP_MODEL = "the language model call was refused: %s"
#: an answer that held no JSON object, asked once more with it (owner 10-26 «응답이 json 이 아니어서 멈추는 경우» 안 ㄱ)
AGAIN_JSON = "\n\nYour last answer was not one JSON object: %s. Answer one JSON object only."
#: still none: the reading ends there and what was read is written, as at the step cap
STOP_NO_JSON = "the model answered no JSON at step %d: %s"
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


text_slots = report_shape.text_slots


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


def step_line(rule, wafer, s, cap):
    """A step's one sentence - the chain log's line the moment the step ends (lead 11-05): its read and why, then the
    first line of what it read or why it was refused, and its seconds. `cap`: the step cap while the model reads, None
    for the product's steps after it."""
    said = ("refused: " + s["refused"]) if s.get("refused") else (s.get("summary") or "")
    return "[Report] %s wafer %s step %s %s - why %s -> %s (%.1f s)" % (
        rule, wafer, ("%d/%d" % (s["step"], cap)) if cap else s["step"], s["call"], s.get("why") or "-",
        said.splitlines()[0] if said else "", s.get("seconds") or 0)


#: How many of the wafers waiting behind the one building are named on the claim - the rest only counted
#: (`queued_more`): the claim is rewritten each step and /health reads it every 2 s (C 11-05: 13.7 KB a 1,000-row batch
#: when every waiting wafer's row ids rode it).
QUEUED_SHOWN = 200


def _key_of(row, keys):
    """{key column: the row's own value} - as the grid's read carries it, so a screen finds the row by it (a number a
    number, a text a text; anything else as its text)."""
    return {column: value if value is None or isinstance(value, (str, int, float, bool)) else str(value)
            for column, value in ((c, getattr(row, c)) for c in keys)}


def _tell(live):
    """The report building now on this thread's chain group claim (`heartbeat.note_work`, written at once) - /health's
    chain state says it (`runtime.running.work_facts`); None: none. A copy each time, or the claim holds the same
    dict and sees no change. Never raises - the report goes on unseen."""
    from utils import heartbeat

    try:
        heartbeat.note_work(report=None if live is None else dict(live, steps=list(live.get("steps") or ())))
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("[Report] the report's progress was not put on its group's beat - /health does not show it: "
                       "%s", told(exc))


def _doing(live, what, step=None):
    """The report is now `what` (asking the model, reading a call, writing) - said on the claim."""
    if live is not None:
        live.update(doing=what, **({} if step is None else {"step": step}))
        _tell(live)


class _Steps(list):
    """A report's steps - each one appended (the model's reads, the product's, the write call) is logged as it ends and
    said on the claim (`step_line`, `_tell`): every step seat appends here, so none is missed. `cap`: the step cap
    while the model reads, None after."""

    def __init__(self, live, cap):
        super().__init__()
        self.live, self.cap = live, cap

    def append(self, s):
        super().append(s)
        said = ("refused: " + s["refused"]) if s.get("refused") else (s.get("summary") or "")
        self.live["steps"] = self.live.get("steps", []) + [{
            "n": s["step"], "call": s["call"], "why": s.get("why"), "result": said.splitlines()[0] if said else "",
            "seconds": round(s.get("seconds") or 0, 1), "refused": bool(s.get("refused"))}]
        self.live["tokens"] = s.get("tokens") or self.live.get("tokens")
        logger.info(step_line(self.live["rule"], self.live["wafer"], s, self.cap))
        _tell(self.live)


def _instructions(spec, step, cap):
    prompts = (spec or {}).get("prompts") or {}
    functions = prompts.get(report_shape.FUNCTIONS_CELL) or {}
    lines = [prompts.get("role") or ROLE, prompts.get("rules") or RULES, "Reads:"]
    for read in report_shape.READS:
        about = (functions.get(read) or {}).get(report_shape.ABOUT_CELL) or ABOUT[read]
        most = ((spec or {}).get("conditions") or {}).get(report_shape.CONDITION_MOST) if "rows" in ARGS[read] else None
        lines.append("  %s(%s) - %s%s" % (read, ", ".join(ARGS[read]), about, ROWS_MOST % most if most else ""))
    lines.append("  " + WAFERS_SAID)
    lines.append('Answer one JSON object: {"call": "<read>", "args": {...}, "why": "..."} or {"done": {}} when you have read enough')
    lines.append("This is step %d of %d." % (step, cap))
    return lines


def _prompts(spec, cells=("select", "style", "compare", "control")):
    prompts = (spec or {}).get("prompts") or {}
    said = ["%s: %s" % (cell.capitalize(), prompts[cell]) for cell in cells if prompts.get(cell)]
    # the analyst's words win over the product's rules (owner 10-24 «select 프롬프트 내가 쓴 게 전혀 안 들어먹는데 ·
    # 너가 너무 강하게 적어 넣은 듯»)
    return ["Analyst (wins over the rules):"] + said if said else []


def _request(request):
    return ["Evaluation: %s" % request.get("evaluation"),
            "Compare sets: %s" % (", ".join(request.get("sets") or ()) or "the declaration's default"),
            "Note: %s" % (request.get("note") or "none")] + (
        ["Reviewer comment: %s" % request["comment"]] if request.get("comment") else []) + (
        [request["memo"]] if request.get("memo") else []) + ([request["memory"]] if request.get("memory") else [])


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
        said = _cut_line([(name, cut[n], whole) for n, name, whole in (
            ("6", "last result", len(previous)), ("4", "conditions", len(conditions))) if n in cut])
        text = "\n".join(body + ([said] if said else []))
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


def compose_write(spec, request, reads, budget, line=None):
    """The write call's prompt - role · rules · the write line (`line`: the seed call's) · style · compare · control ·
    the request · every table read (`reads`: [(step, call, lines)]) - and what was cut, or (None, cut) when the tables
    at no rows do not fit. Over budget a read loses half its rows, the cause walk's reads first and the report's own
    tables last, the oldest first in each (lead 10-23, owner 10-27 «ㅇㅇ»); what was cut is said in a line."""
    prompts = (spec or {}).get("prompts") or {}
    slots = ", ".join('"%s": "<text>"' % slot for slot in text_slots(spec))
    head = ([prompts.get("role") or ROLE] + ([prompts["rules"]] if prompts.get("rules") else []) + [line or WRITE % slots]
            + _prompts(spec, ("style", "compare", "control")) + _request(request) + ["Tables read:"])
    kept = [list(lines) for _step, _call, lines in reads]
    order = sorted(range(len(reads)), key=lambda n: not _walked(reads[n][1]))
    cut = {}
    while True:
        body = list(head)
        for (step, call, _lines), lines in zip(reads, kept):
            body += ["step %d: %s" % (step, call)] + lines
        said = _cut_line([("step %d %s" % (step, call), len(lines), len(whole))
                          for (step, call, whole), lines in zip(reads, kept) if len(lines) < len(whole)])
        text = "\n".join(body + ([said] if said else []))
        if budget.tokens(text) <= budget.cap:
            return text, cut
        at = next((n for n in order if kept[n]), None)
        if at is None:
            return None, cut
        kept[at] = kept[at][:len(kept[at]) // 2]
        cut["step %d %s" % (reads[at][0], reads[at][1])] = len(kept[at])


def _walked(call):
    """A read the cause walk made (`_causes`) - cut before the report's own tables."""
    return call.startswith("causes(") or call in (VALUES_CALL, RELATED_CALL)


def _cut_line(said):
    """THE ONE LINE a prompt says what the budget cut in - «Rows cut to fit the context: <read> N of M, ...»; nothing
    cut: none. `said`: [(read, rows kept, rows read)]."""
    return ("Rows cut to fit the context: " + ", ".join("%s %d of %d" % item for item in said)) if said else None


def _ask(prompt, ask):
    """-> (the answer, the prompt tokens the gateway counted or None). An answer with no JSON object is asked once more,
    told what it said (`AGAIN_JSON`); a call that failed is not."""
    from utils import llm

    usage = {}
    try:
        said = ask(prompt, usage=usage)
    except llm.LlmNotAnObject as refused:
        logger.warning("[Report] the answer held no JSON object - asked once more: %s", refused)
        usage = {}
        said = ask(prompt + AGAIN_JSON % refused.answer, usage=usage)
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
        logger.warning("[Report] %s(%s) refused: %s", call, args, refused, exc_info=refused)
        return None, str(refused)
    except Exception as exc:                                        # noqa: BLE001 - one read's data, said to the model
        logger.error("[Report] %s failed: %s: %s", call, type(exc).__name__, exc, exc_info=exc)
        return None, "the read failed: %s: %s" % (type(exc).__name__, exc)


def run(report, spec, request, ask=None, clock=time.monotonic, live=None):
    """One report's steps -> {"state", "reason", "steps", "texts", "tables"}. `request`: evaluation · sets (blank:
    the declaration's default) · note. `ask(prompt, usage=)`: the model (`utils.llm.ask_json`). `live`: the report
    building now (`answer`) - its steps logged and said on the claim as they end."""
    from utils import heartbeat, llm

    ask = ask or llm.ask_json
    caps = limits(spec)
    budget = Budget(caps["context_tokens"])
    started = clock()
    if request.get("sets") or (report_shape.sets_role(spec) or {}).get(report_shape.SETS_DEFAULT):
        report.compare(request.get("sets"))
    conditions = report.conditions()["context"].splitlines()
    previous, seen, tables = [], {}, {}
    steps = [] if live is None else _Steps(live, caps["steps"])
    if live is not None:
        live.update(cap=caps["steps"], seconds_cap=caps["seconds"], tokens_cap=caps["context_tokens"], steps=[],
                    tokens=None)
    reads = [(0, "conditions()", conditions)]                # what the write call is handed - the folded conditions first
    out = {"state": STOPPED, "reason": STOP_STEPS % caps["steps"], "steps": steps, "texts": {}, "tables": tables}
    no_json = None
    for step in range(1, caps["steps"] + 1):
        if clock() - started >= caps["seconds"]:
            out["reason"] = STOP_SECONDS % caps["seconds"]
            break
        heartbeat.progress("report step %d" % step)
        _doing(live, "asking the model", step)
        prompt, cut = compose(spec, request, conditions, steps, previous, budget, step, caps["steps"])
        if prompt is None:
            out["reason"] = STOP_CONTEXT
            break
        began = clock()
        try:
            said, counted = _ask(prompt, ask)
        except llm.LlmNotAnObject as refused:
            out["reason"] = no_json = STOP_NO_JSON % (step, refused.answer)
            steps.append({"step": step, "tokens": budget.tokens(prompt), "cut": cut, "call": "answer",
                          "seconds": clock() - began, "refused": no_json, "why": None, "summary": "", "read": []})
            break
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
        _doing(live, "reading " + _said(said.get("call"), said.get("args")))
        answer, refused = _call(report, said, seen)
        record.update(call=_said(said.get("call"), said.get("args")), seconds=clock() - began, refused=refused,
                      why=str(said.get("why") or "").strip() or None)
        if refused is None:
            seen[record["call"]] = step
            # the model's reads are its own - the file's tables are the product's, drawn after the loop with every
            # group (owner 10-24 «컨디션도 안 나와 · 이상한 아이템 헤더로 들어가 있고»: a yield_by by a condition
            # the model read became the file's table)
            previous = answer["context"].splitlines()
            reads.append((step, record["call"], previous))
        else:
            previous = ["refused: " + refused]
        record["summary"] = (previous[0] if previous else "")[:200]
        record["read"] = previous[1:]                       # the Evidence's lines under it (lead 10-23)
        steps.append(record)
        if refused is None and said.get("call") in report_shape.TABLE_FILLS:
            # what the model selected (prompts.select) is the file's table too - its wafers, rows, items; only `by`
            # stays the model's own, the heads stay date > wafer > leg (owner 10-24 «select 프롬프트 내가 쓴 게 전혀
            # 안 들어먹는데»: 3b02c7efe drew every table with no args)
            report.__dict__.setdefault("chosen", {})[said["call"]] = {
                k: v for k, v in (said.get("args") or {}).items() if k != "by"}
        if refused is None and said.get("call") == "yield_by":   # the condition rows the model kept, for the file's
            rows = (said.get("args") or {}).get("rows")
            report.kept_rows = list(dict.fromkeys(getattr(report, "kept_rows", []) +
                                                  ([rows] if isinstance(rows, str) else list(rows or []))))
    _doing(live, "writing the report")
    if live is not None:
        steps.cap = None                                       # the model's reading is over - the product's steps
    _product_reads(report, spec, tables, reads, steps, clock)
    if out["state"] == DONE or out["reason"] in (STOP_STEPS % caps["steps"], STOP_SECONDS % caps["seconds"], no_json):
        if (spec or {}).get(report_shape.CAUSES) is not None:
            _causes(report, spec, request, reads, budget, ask, clock, out["steps"], tables)
        _write(spec, request, reads, budget, ask, clock, out)
        # the conditions the texts name stand in the table too (owner 10-24 «리포트에 글로 명시한 조건값이 표에는 반영
        # 안 되어 있음 · 동기화되게») - the yield_by table drawn again with them
        written = " ".join(out["texts"].values())
        named = [n for n in getattr(report, "condition_names", list)() if str(n).strip() and str(n).strip() in written]
        also = list(getattr(report, "written_rows", None) or ())        # the candidates' conditions, when related
        if "yield_by" in tables and any(n not in getattr(report, "kept_rows", []) + also for n in named):
            report.written_rows = list(dict.fromkeys(also + named))
            try:
                tables["yield_by"] = report.yield_by(**_args(report, "yield_by"))["html"]
            except report_reads.ReadRefused as said:
                logger.warning("[Report] yield_by with the written conditions refused: %s", said, exc_info=said)
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


def _args(report, call):
    """The args the file's table is drawn with - the model's selection for it (no `by`), the yield_by rows with every
    condition kept or written."""
    args = dict(report.__dict__.get("chosen", {}).get(call) or {})
    if call == "yield_by" and getattr(report, "kept_rows", None):
        args["rows"] = report.kept_rows
    if call == "yield_by" and getattr(report, "written_rows", None):
        args["also"] = report.written_rows
    return args


def _product_reads(report, spec, tables, reads, steps, clock):
    """The file's tables and images the model did not read, read by the product with no arguments - this evaluation's
    wafers and every group beside them (owner: AI makes rules, the product does the work; lead 10-24 - the model
    writes only the text slots). A step each in the Evidence, «product <read>()», and the write call reads them."""
    fills, image = filled_slots(spec)
    calls = [fill for fill in dict.fromkeys(fills) if fill not in tables]
    if image and not report.embedded and (spec or {}).get("images"):
        calls.append("images")
    alone = False
    if len(report.groups) == 1:          # the model compared nothing - the declaration's comparison, tables drawn
        # or not (owner 10-24 «표 여전한데 전처럼 왜 안 돼»: a model that drew every table skipped it)
        began = clock()
        try:
            lines, refused = report.declared_compare(), None
        except report_reads.ReadRefused as said:
            logger.warning("[Report] compare() refused: %s", said, exc_info=said)
            lines, refused, alone = ["refused: %s" % said], str(said), True
        reads.append((len(steps) + 1, "product compare()", lines))
        steps.append({"step": len(steps) + 1, "tokens": 0, "cut": {}, "call": "product compare()",
                      "seconds": clock() - began, "refused": refused, "summary": lines[0][:200] if lines else "",
                      "read": lines[1:]})
    for call in calls:
        began = clock()
        try:
            answer, refused = getattr(report, call)(**_args(report, call)), None
        except report_reads.ReadRefused as said:
            logger.warning("[Report] %s() refused: %s", call, said, exc_info=said)
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


def _causes(report, spec, request, reads, budget, ask, clock, steps, tables):
    """The cause walk before the write: the declared type's nodes and the tables read -> the model's seeds and why ->
    the product's static walk from them -> its candidates, a read the write call is handed. A refusal on the way is a
    step's, and the report is written without the candidates."""
    from utils import llm

    def step(call, began, lines, refused=None, **more):
        steps.append(dict({"step": len(steps) + 1, "tokens": 0, "cut": {}, "call": call, "seconds": clock() - began,
                           "refused": refused, "summary": (lines[0] if lines else "")[:200], "read": lines[1:]}, **more))

    began = clock()
    try:
        kinds = report.seed_nodes()["context"].splitlines()
    except report_reads.ReadRefused as said:
        logger.warning("[Report] seed_nodes() refused: %s", said, exc_info=said)
        return step("product seed_nodes()", began, [], str(said))
    step("product seed_nodes()", began, kinds)
    tables_read = [read for read in reads if read[1].replace("product ", "").split("(")[0] in report_shape.TABLE_FILLS]
    line = "\n".join([SEEDS % spec[report_shape.CAUSES]["seed_type"]] + kinds[1:])
    began = clock()
    prompt, cut = compose_write(spec, request, tables_read, budget, line=line)
    if prompt is None:
        return step("causes()", began, [], STOP_CONTEXT, cut=cut)
    try:
        said, counted = _ask(prompt, ask)
    except llm.LlmRefused as refused:
        return step("causes()", began, [], STOP_MODEL % refused)
    budget.correct(prompt, counted)
    seeds = said.get("seeds")
    seeds = [seeds] if isinstance(seeds, str) else [str(s) for s in seeds or () if str(s).strip()]
    why = str(said.get("why") or "").strip() or None
    logger.warning("[Report] causes seeds %s - %s", ", ".join(seeds) or "none", why or "no why given")
    call = _said("causes", {"seeds": seeds})
    try:
        walked, refused = report.causes(seeds), None
    except report_reads.ReadRefused as refused_:
        logger.warning("[Report] %s refused: %s", call, refused_, exc_info=refused_)
        walked, refused = None, str(refused_)
    except Exception as exc:                                    # noqa: BLE001 - this step stops, the report is written
        logger.error("[Report] %s failed: %s: %s", call, type(exc).__name__, exc, exc_info=exc)
        walked, refused = None, "the read failed: %s: %s" % (type(exc).__name__, exc)
    lines = walked["context"].splitlines() if walked else []
    step(call, began, lines, refused, tokens=counted or budget.tokens(prompt), cut=cut, why=why)
    if refused is None:
        reads.append((steps[-1]["step"], call, lines))
        first = len(reads) - 1
        said = None
        if walked["candidates"] and report_shape.VALUES in spec[report_shape.CAUSES]:
            said = _values(report, clock, steps, reads, tables, walked["candidates"])
        if walked["candidates"]:
            _related(report, spec, request, budget, ask, clock, steps, reads, tables, walked["candidates"], first,
                     said["to_fill"] if said else None)


def _values(report, clock, steps, reads, tables, candidates):
    """The quantities' measured values (`report.values`): a step of its own, its read handed on; the quantities stand
    as yield_by rows as the candidates' conditions do (`written_rows`). A refusal stops this step alone. -> its
    answer, None refused."""
    began = clock()
    try:
        said, refused = report.values(candidates), None
    except report_reads.ReadRefused as refused_:
        logger.warning("[Report] %s refused: %s", VALUES_CALL, refused_, exc_info=refused_)
        said, refused = None, str(refused_)
    except Exception as exc:                                    # noqa: BLE001 - this step stops, the report is written
        logger.error("[Report] %s failed: %s: %s", VALUES_CALL, type(exc).__name__, exc, exc_info=exc)
        said, refused = None, "the read failed: %s: %s" % (type(exc).__name__, exc)
    lines = said["context"].splitlines() if said else []
    steps.append({"step": len(steps) + 1, "tokens": 0, "cut": {}, "call": VALUES_CALL, "seconds": clock() - began,
                  "refused": refused, "summary": (lines[0] if lines else "")[:200], "read": lines[1:]})
    if said is None:
        return None
    reads.append((steps[-1]["step"], VALUES_CALL, lines))
    if said["to_fill"]:
        logger.warning("[Report] quantity values to fill: %s", ", ".join(said["to_fill"]))
    if said["labels"]:
        report.written_rows = list(dict.fromkeys(list(getattr(report, "written_rows", None) or ()) + said["labels"]))
        _redraw_yield_by(report, tables, VALUES_CALL)
    return said


def _redraw_yield_by(report, tables, why):
    """The yield_by table drawn again with the rows written since (`_args`) - {cell: [text, ...]} of its info rows."""
    try:
        table = report.yield_by(**_args(report, "yield_by"))["html"]
    except report_reads.ReadRefused as said:
        logger.warning("[Report] yield_by with the %s refused: %s", why, said, exc_info=said)
        return {}
    if "yield_by" in tables:
        tables["yield_by"] = table
    return {label: [cell["text"] for cell in cells] for label, cells in table.get("info") or ()}


def _related(report, spec, request, budget, ask, clock, steps, reads, tables, candidates, first=-1,
             values_to_fill=None):
    """The candidates' conditions (owner 10-25 «조건표에서 디펙 카인드와 연관된 인자를 찾아서 언급하거나 표에 추가»): one
    model call over the walk's read and the report's condition names - the ledger links no candidate to a condition
    (the conditions are the report's tables, not the ledger's), so there is no walk to it; a name not a condition is
    dropped and said. The related conditions stand as yield_by rows (`written_rows` -> `also`; a constant one still
    drops) and each candidate is said with its conditions' values per column, or as to be filled when none has a value
    on the report's wafers (owner 10-25 «값이 없으면 채워야 한다는 코멘트»). One related to none: when the quantity
    values step answered (`values_to_fill`, its own to_fill), to be filled only if that step says so - a value it gave
    or a candidate no value lands on is that step's line or none (lead 10-28); with no values step, to be filled."""
    from utils import llm

    def step(lines, refused=None, **more):
        steps.append(dict({"step": len(steps) + 1, "tokens": 0, "cut": {}, "call": RELATED_CALL,
                           "seconds": clock() - began, "refused": refused, "summary": (lines[0] if lines else "")[:200],
                           "read": lines[1:]}, **more))

    names = [str(n) for n in report.condition_names()]
    labels = list(dict.fromkeys(str(c["label"]) for c in candidates))
    began = clock()
    prompt, cut = compose_write(spec, request, reads[first:], budget,
                                line="\n".join([RELATE, "Conditions: " + (", ".join(names) or "none")]))
    if prompt is None:
        return step([], STOP_CONTEXT, cut=cut)
    try:
        said, counted = _ask(prompt, ask)
    except llm.LlmRefused as refused:
        return step([], STOP_MODEL % refused)
    budget.correct(prompt, counted)
    why = str(said.get("why") or "").strip() or None
    related, dropped = {}, []
    picked = said.get("conditions") if isinstance(said.get("conditions"), dict) else {}
    for label, conditions in picked.items():
        if str(label) not in labels:
            dropped.append(str(label))
            continue
        for name in [conditions] if isinstance(conditions, str) else conditions or ():
            try:
                related.setdefault(str(label), []).append(report._condition(str(name)))
            except report_reads.ReadRefused:
                dropped.append(str(name))
    rows = list(dict.fromkeys(name for label in labels for name in related.get(label, ())))
    drawn = {}
    if rows:
        report.written_rows = list(dict.fromkeys(list(getattr(report, "written_rows", None) or ()) + rows))
        drawn = _redraw_yield_by(report, tables, "candidates' conditions")
    to_fill = report_shape.word(spec, "to_fill")
    lines, unfilled = ["%d of %d candidate(s) related to the conditions%s" % (
        len([label for label in labels if related.get(label)]), len(labels),
        " - not conditions, dropped: %s" % ", ".join(dropped) if dropped else "")], []
    for label in labels:
        valued = False
        for name in dict.fromkeys(related.get(label, ())):
            values = report.values_here(name)
            cells = " | ".join(drawn.get(report.condition_label(name)) or ())
            valued = valued or bool(values)
            lines.append("%s -> %s: %s" % (label, name, (cells or "%s in every column" % " / ".join(values)) if values
                                           else to_fill + (" - the other columns: %s" % cells if cells else "")))
        if not related.get(label):
            if values_to_fill is not None and label not in values_to_fill:
                continue                                  # the quantity values step said it: its value, or none lands
            lines.append("%s: %s" % (label, to_fill))
        if not valued:
            unfilled.append(label)
    logger.warning("[Report] causes conditions: %s%s", "; ".join(
        "%s -> %s" % (label, ", ".join(related[label])) for label in labels if related.get(label)) or "none",
        " (dropped %s)" % ", ".join(dropped) if dropped else "")
    if unfilled:
        logger.warning("[Report] causes to fill: %s", ", ".join(unfilled))
    step(lines, tokens=counted or budget.tokens(prompt), cut=cut, why=why)
    reads.append((steps[-1]["step"], RELATED_CALL, lines))


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
    from chain import ask_rule
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(str(rule.get("trigger_table") or ""))
    if model is None or not row_ids:
        return {"updates": [], "refusal": "no report table row reached this mapper"}
    spec = rule.get("params") or {}
    name = str(rule.get("name") or "")
    keys = report_shape.report_key(spec, rule.get("trigger_table"))
    written = report_shape.result_cells(spec)                 # the file's column, then each named text's
    comment = ask_rule.comment_column(spec)                   # a person's comment on the wafer's row (owner 10-29)
    by_wafer, comments, key_of, situations = {}, {}, {}, {}
    situated = ask_rule.situation_columns(spec, rule.get("trigger_table"))
    for row in db.query(model).filter(model.row_id.in_(list(row_ids))).all():
        wafer = report_reads._parts(getattr(row, c) for c in keys)
        if not all(crud.is_blank_value(part) for part in wafer):
            by_wafer.setdefault(wafer, []).append(row.row_id)
            key_of.setdefault(wafer, _key_of(row, keys))
            situations.setdefault(wafer, {c: getattr(row, c, None) for c in situated})
            said = getattr(row, comment, None) if comment else None
            if not crud.is_blank_value(said):
                comments.setdefault(wafer, {})[str(said).strip()] = None
    updates = []
    wafers = sorted(by_wafer.items(), key=lambda pair: report_reads.label(pair[0]))
    try:
        for n, (wafer, rows) in enumerate(wafers):
            waiting = wafers[n + 1:]
            updates += _one_wafer(db, rule, spec, name, keys, written, comments, situations[wafer], wafer, rows,
                                  ask, clock, live={
                "rule": name, "table": rule.get("trigger_table"), "wafer": report_reads.label(wafer), "keys": keys,
                "wafer_key": key_of[wafer],
                "queued": [key_of[w] for w, _r in waiting[:QUEUED_SHOWN]],
                "queued_more": max(0, len(waiting) - QUEUED_SHOWN),
                "started": time.time(), "step": None, "doing": None})
    finally:
        _tell(None)                                             # the batch is over: no report building
    return {"updates": updates}


def _one_wafer(db, rule, spec, name, keys, written, comments, situation, wafer, rows, ask, clock, live):
    """One wafer's report (`answer`): run, its page kept, the updates of its rows. `situation`: its row's
    (`ask_rule.situation_columns`) - what its memory and its memo are read by."""
    import datetime

    from chain import ask_rule, report_html, rule_shape
    from database import crud

    said, report, updates = report_reads.label(wafer), None, []
    read = report_reads.fresh_reading()                    # the tables this wafer's report reads, named by keep
    try:
        report, evaluation = _this_wafer(db, spec, dict(zip(keys, wafer)))
        memory = ask_rule.memory_lines(db, spec, rule_shape.declaration_of(rule), situation,
                                       " / ".join(comments.get(wafer) or ()))   # the reviewer's words: the nearest
        _tell(live)
        out = run(report, spec, {"evaluation": evaluation, "note": None, "sets": [], "memory": memory,
                                 "memo": ask_rule._memo(db, spec, situation),
                                 "comment": " / ".join(comments.get(wafer) or ())}, ask=ask, clock=clock,
                  live=live)
    except report_reads.ReadRefused as refused:
        logger.error("[Report] %s wafer %s stopped: %s", name, said, refused, exc_info=refused)
        out = {"state": STOPPED, "reason": str(refused), "steps": [], "texts": {}, "tables": {}}
    except Exception as exc:                                    # noqa: BLE001 - this wafer stops, the others go on
        logger.error("[Report] %s wafer %s failed: %s: %s", name, said, type(exc).__name__, exc, exc_info=exc)
        out = {"state": STOPPED, "reason": "%s: %s" % (type(exc).__name__, exc), "steps": [], "texts": {},
               "tables": {}}
    cells = {column: None for _cell, column in written}
    if report is not None:
        try:
            made = datetime.datetime.now().astimezone()
            refs = report_html.link_pictures(report_html.file_name(said), out["tables"], report.embedded)
            page = report_html.page("%s %s" % (said, report_shape.word(spec, "report")), "%s · %s" % (
                name, made.isoformat(timespec="seconds")), spec, out["tables"], report.embedded, out["texts"],
                evidence=_steps_text(out, report).splitlines())
            kept, _sha = report_html.keep(said, page, refs, tables=read)
            # the cell holds the file's signed-in link (owner 11-04); send_to and its mark keep the path
            wrote = dict(out["texts"], file=report_html.link_of(kept))   # a text the report did not write is withdrawn
            cells = {column: wrote.get(cell) or None for cell, column in written}
            _mark(kept, name if out["state"] == DONE and spec.get(report_shape.SEND_TO) else None)
        except Exception as exc:                                # noqa: BLE001 - this wafer's page, the others go on
            logger.error("[Report] %s wafer %s page failed: %s: %s", name, said, type(exc).__name__, exc,
                         exc_info=exc)
            cells = {column: None for _cell, column in written}
            out = dict(out, state=STOPPED, reason="the page failed: %s: %s" % (type(exc).__name__, exc))
    logger.info("[Report] %s wafer %s: %s%s", name, said, out["state"], " - %s" % out["reason"] if out["reason"] else "")
    for row_id in rows:
        updates.append({"row_id": row_id, "source_name": crud.CHAIN_SOURCE, "updated_by": name,
                        "origin_row_id": row_id,
                        "updates": {c: v for c, v in cells.items() if not crud.is_blank_value(v)}})
    return updates


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
