# -*- coding: utf-8 -*-
"""The admin help (소유자 10-23 「추천대로」, 총괄 423af9e68 · e33713863): a question in the operator's words -> ONE tool of
the catalog (`retroactive.OPERATIONS` not retired, and `retroactive.DOORS_OUTSIDE`), its fields filled, and that
tool's own count. It never runs anything: the operator runs it from the form, which carries `help_id` back so the
run is written on its ask (`mark_run`).

One ask over the whole catalog. The answer is judged by the tool's own `retroactive.validate` - the form's judgement,
no copy - and asked once more with the refusal; still refused -> «not sure» and up to three tools of the list it
named near. Every ask is a row of `admin_help_asks`: an operations record, not source data - nothing reads it into the
ledger."""
import json
import logging
import time
import uuid

from admin import retroactive
from error_said import told

logger = logging.getLogger(__name__)

#: Asks of the model per question: the first, and one more with the refusal.
TRIES = 2
#: Tools named «near» when none fits.
SIMILAR = 3
#: Choices spelled into the prompt per field - a field fetching more (tables) says how many it left out.
CHOICES_SHOWN = 40

SYSTEM = ("You route an operator's question to ONE maintenance tool of the list below, or to none. Answer one JSON "
          'object: {"op": the tool name from the list or null, "params": {field: value} using only that tool\'s '
          'fields - leave a field out when the question does not say it, "why": one short English sentence, '
          '"similar": up to three other tool names from the list}. Never name a tool or a field that is not in the '
          "list.")


def catalog():
    """{name: spec} - the retroactive tools not retired, and the upkeep doors outside the tab."""
    return {**{op: spec for op, spec in retroactive.OPERATIONS.items() if not spec.get("retired")},
            **retroactive.DOORS_OUTSIDE}


def _field(param):
    choices = retroactive._resolved_choices(param)
    said = "%s (%s, %s)" % (param["name"], param["type"], "required" if param["required"] else "optional")
    if choices:
        values = [str(c["value"]) if isinstance(c, dict) else str(c) for c in choices]
        said += " one of " + " | ".join(values[:CHOICES_SHOWN]) + (
            " | ... %d more" % (len(values) - CHOICES_SHOWN) if len(values) > CHOICES_SHOWN else "")
    return said + (" - " + param["help"] if param.get("help") else "")


def prompt_of(question, refused=None):
    """The catalog, every tool's line and questions and fields, then the question (and the last refusal)."""
    lines = []
    for name, spec in catalog().items():
        lines.append("- %s: %s - for when %s" % (name, spec["label"], spec["what_is_missing"]))
        lines.append("  asked as: " + " / ".join(spec["examples"]))
        if "doors" in spec:
            lines.append("  outside this tab: " + " / ".join("%s: %s" % (d["name"], d["how"]) for d in spec["doors"]))
        for param in spec.get("params", ()):
            if param.get("form", True):
                lines.append("  field " + _field(param))
        if spec["next"]:
            lines.append("  afterwards: " + " / ".join(spec["next"]))
    text = "Tools:\n" + "\n".join(lines) + "\n\nQuestion: " + question
    if refused:
        text += "\n\nYour last answer was refused: %s\nAnswer again." % refused
    return text


def pick(question, ask_json=None):
    """-> {"op", "params", "why", "similar", "refused", "tries", "seconds"} - the tool the model named and the fields
    as its `validate` normalized them; op None when no answer passed. `seconds` the gateway's time per ask. Refused
    by name (`LlmRefused`) when the model cannot be asked."""
    from utils import llm

    ask_json = ask_json or llm.ask_json
    tools, refused, seconds, answer = catalog(), None, [], {}
    for tries in range(1, TRIES + 1):
        began = time.monotonic()
        answer = ask_json(prompt_of(question, refused), system=SYSTEM)
        seconds.append(round(time.monotonic() - began, 3))
        op = answer.get("op")
        params = answer.get("params") if isinstance(answer.get("params"), dict) else {}
        if op not in tools:
            refused = "%r is not a tool in the list" % (op,)
            continue
        if op in retroactive.DOORS_OUTSIDE:
            params = {}
        else:
            try:
                params = retroactive.validate(op, params)
            except retroactive.RetroactiveRefused as e:
                refused = str(e)
                continue
        return {"op": op, "params": params, "why": answer.get("why"), "similar": [], "refused": None,
                "tries": tries, "seconds": seconds}
    near = answer.get("similar") if isinstance(answer.get("similar"), list) else []
    return {"op": None, "params": {}, "why": answer.get("why"), "refused": refused, "tries": TRIES,
            "similar": [name for name in dict.fromkeys(near) if name in tools][:SIMILAR], "seconds": seconds}


def ask(db, question, asked_by=None, ask_json=None):
    """The help's answer: `pick`, then the tool's own count (`retroactive.count`), written as one `admin_help_asks`
    row. -> the answer with `help_id`, `label`, `count` (the count's answer, or None) and `count_refused`."""
    from database import models
    from utils.llm import LlmRefused

    question = str(question or "").strip()
    if not question:
        raise retroactive.RetroactiveRefused("write what you want to do")
    try:
        got = pick(question, ask_json)
    except LlmRefused as e:
        got = {"op": None, "params": {}, "why": None, "similar": [], "refused": str(e), "tries": 0, "seconds": []}
    got.update(help_id=uuid.uuid4().hex[:12], count=None, count_refused=None,
               label=catalog()[got["op"]]["label"] if got["op"] else None)
    if got["op"] in retroactive.OPERATIONS:
        try:
            got["count"] = retroactive.count(db, got["op"], got["params"])
        except Exception as e:                                       # noqa: BLE001 - said on the answer
            db.rollback()
            got["count_refused"] = "The count for this operation cannot be computed: %s" % told(e)
    affected = (got["count"] or {}).get("affected")
    db.add(models.AdminHelpAsk(id=got["help_id"], asked_by=asked_by or None, question=question, op=got["op"],
                               params=json.dumps(got["params"], default=str), why=got["why"],
                               affected=affected if isinstance(affected, int) else None,
                               refused=got["refused"] or got["count_refused"], tries=got["tries"]))
    db.commit()
    return got


def mark_run(db, help_id, queued):
    """The run the form opened from an answer is written on that answer's row (`help_id`). No help_id - nothing.
    The run is already queued: a failure here is said, not raised."""
    if not help_id or not isinstance(queued, dict):
        return
    from database import models

    try:
        (db.query(models.AdminHelpAsk).filter(models.AdminHelpAsk.id == str(help_id))
         .update({models.AdminHelpAsk.run_id: queued.get("run_id")}, synchronize_session=False))
        db.commit()
    except Exception as e:                                           # noqa: BLE001 - the run stands
        db.rollback()
        logger.warning("[Help] run %s was not written on help %s: %s", queued.get("run_id"), help_id, told(e),
                       exc_info=e)
