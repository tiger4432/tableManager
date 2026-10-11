# -*- coding: utf-8 -*-
"""Dictionary rows suggested for the phrases no node took (소유자 10-11 ㄱ). One language model call
(`utils.llm`) per call; nothing is written here - a person confirms, a chain rule writes."""
import logging

from utils import text_links

logger = logging.getLogger(__name__)

#: No word of any domain: the words come from the dictionary rows, the phrases and the operator.
ASK_DICTIONARY_PROMPT = """Each numbered phrase below was read from a text, and no dictionary node was found for it.
For each phrase, say which dictionary node it names, or name a new node when no listed node fits.
Answer with one JSON object and nothing else:
{"phrases": [{"number": 1, "node": null, "new_node": "...", "reason": "..."}]}
- number: the number of the phrase as listed
- node: the identifier of the dictionary node the phrase names, written exactly as listed; null when no listed node fits
- new_node: when node is null, a short noun phrase that names the new node; null otherwise
- reason: one line that says why
Dictionary, one node per line - identifier (node type): the phrases that name it
<<dictionary>>
<<instruction>>
Phrases, one per line - number: phrase
<<phrases>>"""


def _said(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def ask_dictionary(phrases, names, instruction=None):
    """One row per phrase the model answered: phrase · count (as handed in) · suggested_node_type ·
    suggested_node_key · new_node_name · reason · extractor `llm:<model>`. `phrases` are rows
    {phrase, count}; a blank phrase is skipped, and none left asks nothing. A node identifier the
    dictionary does not list gives no node and one warning line, as `ask_links`; a phrase the
    answer skips gives no row and one warning line. Refused by name (`LlmRefused`) when the
    answer has no 'phrases' list."""
    from chain.mapper_call import without_missing
    from database import crud
    from utils import llm

    names = list(names or ())
    asked = [row for row in (without_missing(dict(row)) for row in phrases or ())
             if not crud.is_blank_value(row.get("phrase"))]
    if not asked:
        return []
    by_id, dictionary = text_links._listing(names)
    prompt = (ASK_DICTIONARY_PROMPT
              .replace("<<dictionary>>", dictionary)
              .replace("<<instruction>>", "%s\n%s" % (text_links.INSTRUCTION_HEADING, instruction)
                       if not crud.is_blank_value(instruction) else "")
              .replace("<<phrases>>", "\n".join("%d: %s" % (number, row["phrase"])
                                                for number, row in enumerate(asked, 1))))
    answer = llm.ask_json(prompt)
    items = answer.get("phrases")
    if not isinstance(items, list):
        raise llm.LlmRefused("the answer has no 'phrases' list: %s" % sorted(answer)[:10])
    by_number = {}
    for item in items:
        if isinstance(item, dict):
            by_number.setdefault(crud.clean_str_value(item.get("number")), item)
    extractor = text_links.LLM_EXTRACTOR % llm.model()
    out = []
    for number, row in enumerate(asked, 1):
        item = by_number.get(str(number))
        if item is None:
            logger.warning("[LLM] phrase %d of %d has no answer - no suggestion (%s): %r",
                           number, len(asked), extractor, str(row["phrase"])[:120])
            continue
        node = (None, None)
        if not crud.is_blank_value(item.get("node")):
            if str(item["node"]) in by_id:
                node = by_id[str(item["node"])]
            else:
                logger.warning("[LLM] phrase %d of %d answers node %r, which the dictionary does not list"
                               " - suggested without a node (%s): %r",
                               number, len(asked), item["node"], extractor, str(row["phrase"])[:120])
        out.append({"phrase": row["phrase"], "count": row.get("count"),
                    "suggested_node_type": node[0], "suggested_node_key": node[1],
                    "new_node_name": _said(item.get("new_node")), "reason": _said(item.get("reason")),
                    "extractor": extractor})
    return out
