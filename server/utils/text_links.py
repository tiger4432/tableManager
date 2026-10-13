# -*- coding: utf-8 -*-
"""Cause -> phenomenon candidates read out of free text with the caller's own dictionaries
(lead 15a4d8e43 · 9f301f9bc). Every word comes from the rows passed in. `find_links` and
`unknown_words` are pure; `ask_links` asks a language model (`utils.llm`) for the same rows.

    names  {node_type, node_key, phrase}   what a node is called in the text
    links  {phrase, meaning, side}         meaning: cause · and · negation · suspected · confirmed
                                           side: before / after - where the cause sits, cause rows only
    The same phrase on two link rows carries both meanings.

Pairing, per sentence:
  1. for each cause phrase, the nearest node on its side is a cause, and so is every node joined
     to that one only by «and» phrases and spaces
  2. every other node in the sentence is a phenomenon - one candidate per cause x phenomenon.
     Negation and certainty belong to the sentence; suspected beats confirmed.

Matching ignores spaces and ASCII case (notation_norm's case rule); overlapping phrases from
both dictionaries go to the longest, leftmost first; a phrase that starts or ends with an ASCII
letter or digit only matches where the text does not continue that word (void is not in avoid).
"""
import logging
import math
import re
from collections import Counter

logger = logging.getLogger(__name__)

CAUSE, AND, NEGATION, SUSPECTED, CONFIRMED = "cause", "and", "negation", "suspected", "confirmed"
MEANINGS = (CAUSE, AND, NEGATION, SUSPECTED, CONFIRMED)
SIDES = ("before", "after")
ASSERTED, NEGATED, STATED = "asserted", "negated", "stated"
#: A sentence ends at . ! ? 。 followed by whitespace (a line break too) - so 1.5 stays whole - or
#: at a blank line. One line break alone does not end it: text pasted from slides and sheets wraps
#: a sentence over lines (소유자 10-11 「LLM 문장 왜 잘라서 읽어?」 ㄴ).
SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|\n\s*\n\s*")
_ASCII_WORD = re.compile(r"[A-Za-z0-9]")
_WORD = re.compile(r"\w+")


def _fold(text):
    """(text without spaces, case folded; the original index of each kept character)."""
    import notation_norm

    kept = [(i, ch) for i, ch in enumerate(text) if not ch.isspace()]
    folded = notation_norm.fold_notation("".join(ch for _i, ch in kept),
                                         {notation_norm.RULE_CASE: True})
    return folded, [i for i, _ch in kept]


def _dictionary(names, links):
    """{first folded character: [(folded phrase, [(kind, row), ...]), ...] longest first}."""
    from chain.mapper_call import without_missing
    from database import crud

    by_phrase = {}
    for kind, rows in (("node", names), ("link", links)):
        for number, row in enumerate(rows or ()):
            row = without_missing(dict(row))
            if crud.is_blank_value(row.get("phrase")):
                continue
            if kind == "link":
                meaning = crud.clean_str_value(row.get("meaning"))
                if meaning not in MEANINGS:
                    raise ValueError("link row %d (%r): meaning %r is not one of %s"
                                     % (number, row.get("phrase"), meaning, ", ".join(MEANINGS)))
                if meaning == CAUSE and crud.clean_str_value(row.get("side")) not in SIDES:
                    raise ValueError("link row %d (%r): a cause row needs side %s, got %r"
                                     % (number, row.get("phrase"), " or ".join(SIDES),
                                        row.get("side")))
                row = dict(row, meaning=meaning, side=crud.clean_str_value(row.get("side")))
            by_phrase.setdefault(_fold(str(row["phrase"]))[0], []).append((kind, row))
    index = {}
    for phrase in sorted(by_phrase, key=len, reverse=True):
        index.setdefault(phrase[0], []).append((phrase, by_phrase[phrase]))
    return index


def _matches(sentence, index):
    """[(start, end, the words as written, [(kind, row), ...])], leftmost-longest, no overlap."""
    folded, where = _fold(sentence)
    out, i = [], 0
    while i < len(folded):
        for phrase, rows in index.get(folded[i], ()):
            if not folded.startswith(phrase, i):
                continue
            start, end = where[i], where[i + len(phrase) - 1] + 1
            if _ASCII_WORD.match(phrase[0]) and start and _ASCII_WORD.match(sentence[start - 1]):
                continue
            if (_ASCII_WORD.match(phrase[-1]) and end < len(sentence)
                    and _ASCII_WORD.match(sentence[end])):
                continue
            out.append((start, end, sentence[start:end], rows))
            i += len(phrase)
            break
        else:
            i += 1
    return out


def _sentence_spans(text):
    """[(start, end)] of each non-blank sentence of `text` - the pieces between SENTENCE_END runs."""
    spans, start = [], 0
    for end in SENTENCE_END.finditer(text):
        spans.append((start, end.start()))
        start = end.end()
    spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _sentences(text):
    text = str(text or "")
    return [text[s:e] for s, e in _sentence_spans(text)]


def _joined(sentence, found, a, b, joins):
    """Only «and» phrases and spaces between matches a and b."""
    lo, hi = sorted((a, b))
    if any(k not in joins for k in range(lo + 1, hi)):
        return False
    gap = "".join(ch for i, ch in enumerate(sentence[found[lo][1]:found[hi][0]], found[lo][1])
                  if not any(found[k][0] <= i < found[k][1] for k in range(lo + 1, hi)))
    return not gap.strip()


def _pairs(sentence, found):
    """[(cause match, phenomenon match, cause phrase match)] for one sentence."""
    nodes = [(k, row) for k, (_s, _e, _w, rows) in enumerate(found)
             for kind, row in rows if kind == "node"]
    joins = {k for k, (_s, _e, _w, rows) in enumerate(found)
             if any(kind == "link" and row["meaning"] == AND for kind, row in rows)}
    seen, out = set(), []
    for k, (_s, _e, _w, rows) in enumerate(found):
        for kind, link in rows:
            if kind != "link" or link["meaning"] != CAUSE:
                continue
            step = -1 if link["side"] == "before" else 1
            side = sorted((n for n in nodes if (n[0] - k) * step > 0), key=lambda n: n[0] * step)
            if not side:
                continue
            causes = [side[0]]
            for node in side[1:]:
                if not _joined(sentence, found, causes[-1][0], node[0], joins):
                    break
                causes.append(node)
            named = {(c[1]["node_type"], c[1]["node_key"]) for c in causes}
            for cause in causes:
                for effect in nodes:
                    pair = ((cause[1]["node_type"], cause[1]["node_key"]),
                            (effect[1]["node_type"], effect[1]["node_key"]))
                    if pair[1] in named or pair in seen:
                        continue
                    seen.add(pair)
                    out.append((cause, effect, k))
    return out


RULES_EXTRACTOR = "rules"


def _signed(row):
    """The row with `dir` (소유자 10-11 «같이 움직이나 / 반대로»): "+" when cause_direction and
    phenomenon_direction are both said and equal, "-" when both said and different, else None."""
    cause, effect = row["cause_direction"], row["phenomenon_direction"]
    row["dir"] = None if cause is None or effect is None else "+" if cause == effect else "-"
    return row


def find_links(text, names, links):
    """One row per candidate: sentence_no (from 1) · sentence · cause_type · cause_key ·
    cause_phrase · cause_direction · phenomenon_type · phenomenon_key · phenomenon_phrase ·
    phenomenon_direction · link · polarity · certainty · extractor · evidence · dir (`_signed`).
    The *_phrase cells and `link` are the words as the text wrote them; `extractor` is 'rules'
    and `evidence` the sentence. The *_direction cells and so `dir` are `ask_links`' - None here."""
    index = _dictionary(names, links)
    out = []
    for number, sentence in enumerate(_sentences(text), 1):
        found = _matches(sentence, index)
        said = {row["meaning"] for _s, _e, _w, rows in found for kind, row in rows if kind == "link"}
        polarity = NEGATED if NEGATION in said else ASSERTED
        certainty = (SUSPECTED if SUSPECTED in said else CONFIRMED if CONFIRMED in said
                     else STATED)
        for (ck, cause), (ek, effect), lk in _pairs(sentence, found):
            out.append(_signed({"sentence_no": number, "sentence": sentence,
                        "cause_type": cause["node_type"], "cause_key": cause["node_key"],
                        "cause_phrase": found[ck][2], "cause_direction": None,
                        "phenomenon_type": effect["node_type"],
                        "phenomenon_key": effect["node_key"], "phenomenon_phrase": found[ek][2],
                        "phenomenon_direction": None,
                        "link": found[lk][2], "polarity": polarity, "certainty": certainty,
                        "extractor": RULES_EXTRACTOR, "evidence": sentence}))
    return out


#: What the model is asked (총괄 b5b335f2e ②) - one request, any number of texts (총괄 f7a79b242). It holds
#: no word of any domain: the words come from the dictionary rows, the operator's instruction and the
#: texts, put where the <<...>> marks stand.
ASK_LINKS_PROMPT = """Read each text below and list every statement in it that one thing causes another.
When one sentence names several causes or effects, list one link for each cause and effect pair - separate items, which may quote the same evidence.
Answer with one JSON object and nothing else - one item for each text, its id as its [id] line writes it:
{"texts": [{"id": "...", "links": [{"cause": "...", "cause_key": null, "cause_direction": null, "effect": "...", "effect_key": null, "effect_direction": null, "link": "...", "evidence": "...", "negated": false, "certainty": null}]}]}
- cause, effect: the shortest noun phrase of the text that names the thing, copied from the text - a few words, never a clause or a whole sentence (the whole sentence goes in evidence)
- cause_key, effect_key: the identifier of the dictionary node the cause or the effect is, written exactly as listed; null when no listed node fits
- cause_direction, effect_direction: "up" when the text says that thing increases, rises or grows, "down" when it says it decreases, falls or shrinks, null when it says neither
- link: the words of the text that join the cause to the effect
- evidence: the sentence of the text that says it, copied exactly from that same text
- negated: true when the text says the cause does not lead to the effect
- certainty: "confirmed" when the text says it is confirmed, "suspected" when it says it is suspected, null when it says neither
Dictionary, one node per line - identifier (node type): the phrases that name it
<<dictionary>>
<<instruction>>
Texts, each after its [id] line:
<<texts>>"""
INSTRUCTION_HEADING = "Instruction from the operator:"
#: The id a single text (a str) is asked under.
ONE_TEXT_ID = 1
LLM_EXTRACTOR = "llm:%s"
#: The only *_direction answers kept, spelled exactly (소유자 10-11 「증감 방향」).
DIRECTIONS = ("up", "down")
#: Not compared in evidence, on either side - the model adds, drops or changes them (소유자 10-11).
EVIDENCE_MARKS = "\"'“”‘’«»「」『』…"
ELLIPSIS = "..."


def _evidence(text):
    """`_fold` without EVIDENCE_MARKS and "..." -> (folded, the original index of each kept
    character). The one place an answer's evidence is compared with the text."""
    folded, where = _fold(text)
    kept, i = [], 0
    while i < len(folded):
        if folded.startswith(ELLIPSIS, i):
            i += len(ELLIPSIS)
            continue
        if folded[i] not in EVIDENCE_MARKS:
            kept.append(i)
        i += 1
    return "".join(folded[i] for i in kept), [where[i] for i in kept]


def one_of(answer, listed):
    """(kept, unlisted) of an answer that must be one of `listed`: kept is the answer as written
    (spaces trimmed, case kept) when listed, else None; unlisted is that answer when it is neither
    blank nor listed, else None - each caller says it in its own warning line."""
    from database import crud

    answer = answer.strip() if isinstance(answer, str) else answer
    kept = answer if answer in listed else None
    return kept, (answer if kept is None and not crud.is_blank_value(answer) else None)


def _node_lines(names):
    """({identifier: (node_type, node_key)}, {node: its dictionary line}) - one line per node,
    «<identifier> (<type>): <phrase> / <phrase>»; the identifier is the key, `<type>:<key>` for a
    key two types share. Both in the order the nodes first appear."""
    from chain.mapper_call import without_missing
    from database import crud

    phrases = {}
    for row in names or ():
        row = without_missing(dict(row))
        if not crud.is_blank_value(row.get("phrase")):
            phrases.setdefault((row.get("node_type"), row.get("node_key")), []).append(str(row["phrase"]))
    shared = Counter(str(key) for _type, key in phrases)
    by_id = {(str(key) if shared[str(key)] == 1 else "%s:%s" % (node_type, key)): (node_type, key)
             for node_type, key in phrases}
    return by_id, {node: "%s (%s): %s" % (ident, node[0], " / ".join(phrases[node])) for ident, node in by_id.items()}


def _listing(names, only=None):
    """({identifier: node}, the dictionary as the model sees it) - every node's line, or `only` those
    nodes' (identifiers stay the whole dictionary's)."""
    by_id, lines = _node_lines(names)
    return by_id, "\n".join(line for node, line in lines.items() if only is None or node in only)


class AskedLinks(list):
    """`ask_links`' rows - a list - and what it took: `requests` (calls made, a text asked again alone
    counted) · `texts` (handed in) · `refused` ([{id, reason}] of the texts no rows came back for) ·
    `known` (with `known` handed: per request {texts, seeds, links, kept, nodes, listed} - k of n links,
    j of m dictionary nodes)."""

    def __init__(self, rows=(), *, requests=0, texts=0, refused=(), known=()):
        super().__init__(rows)
        self.requests, self.texts, self.refused, self.known = requests, texts, list(refused), list(known)


def _requests(texts, cap):
    """`texts` [(id, text)] in order, cut into requests of at most `cap` characters of text - a text
    longer than `cap` goes alone."""
    out, size = [], 0
    for item in texts:
        if out and out[-1] and size + len(item[1]) <= cap:
            out[-1].append(item)
            size += len(item[1])
        else:
            out.append([item])
            size = len(item[1])
    return out


def _read(text, links, names, by_id, match_at, extractor):
    """The rows of one text's answered `links` - every check below, for this text alone. Refused by name
    (`LlmRefused`) when a link has not the shape, or every link quotes evidence the text does not hold."""
    from database import crud
    from utils import llm, phrase_bag

    whole, where = _evidence(text)
    spans = _sentence_spans(text)
    out, dropped = [], []
    for number, item in enumerate(links, 1):
        said = {name: (item.get(name) if isinstance(item, dict) else None)
                for name in ("cause", "effect", "evidence")}
        empty = [name for name, value in said.items()
                 if not isinstance(value, str) or not value.strip()]
        if empty:
            raise llm.LlmRefused("link %d of the answer has no %s" % (number, " or ".join(empty)))
        quoted = _evidence(said["evidence"])[0]
        at = whole.find(quoted) if quoted else -1          # all marks is no evidence
        if at < 0:
            dropped.append(number)
            logger.warning("[LLM] link %d of %d quotes evidence the text does not hold - dropped (%s): %r",
                           number, len(links), extractor, said["evidence"][:120])
            continue
        (sentence_no, (start, _end)), (_last_no, (_start, end)) = [   # the sentences it starts and ends in
            next((no, span) for no, span in enumerate(spans, 1) if i < span[1])
            for i in (where[at], where[at + len(quoted) - 1])]
        sentence = text[start:end]
        node, direction = {}, {}
        for side in ("cause", "effect"):
            direction[side], turned = one_of(item.get(side + "_direction"), DIRECTIONS)
            if turned is not None:
                logger.warning("[LLM] link %d of %d answers %s_direction %r, which is not %s"
                               " - kept without it (%s): %r", number, len(links), side, turned,
                               " or ".join(DIRECTIONS), extractor, said[side][:120])
            answered = item.get(side + "_key")
            if crud.is_blank_value(answered):
                found = phrase_bag.match_phrase(said[side], names, match_at) or {}
                node[side] = (found.get("node_type"), found.get("node_key"))
            else:
                listed, unlisted = one_of(answered if isinstance(answered, str) else str(answered), by_id)
                node[side] = by_id[listed] if listed is not None else (None, None)
                if unlisted is not None:
                    logger.warning("[LLM] link %d of %d answers %s_key %r, which the dictionary does not list"
                                   " - kept with its words only (%s): %r",
                                   number, len(links), side, unlisted, extractor, said[side][:120])
        (cause_type, cause_key), (effect_type, effect_key) = node["cause"], node["effect"]
        certainty, unsure = one_of(item.get("certainty"), (CONFIRMED, SUSPECTED))
        if unsure is not None:
            logger.warning("[LLM] link %d of %d answers certainty %r, which is not %s or %s - kept as %s (%s): %r",
                           number, len(links), unsure, CONFIRMED, SUSPECTED, SUSPECTED, extractor,
                           said["evidence"][:120])
        out.append(_signed({"sentence_no": sentence_no, "sentence": sentence,
                    "cause_type": cause_type, "cause_key": cause_key,
                    "cause_phrase": said["cause"].strip(), "cause_direction": direction["cause"],
                    "phenomenon_type": effect_type, "phenomenon_key": effect_key,
                    "phenomenon_phrase": said["effect"].strip(),
                    "phenomenon_direction": direction["effect"],
                    "link": item.get("link") if isinstance(item.get("link"), str) else None,
                    "polarity": NEGATED if item.get("negated") is True else ASSERTED,
                    "certainty": CONFIRMED if certainty == CONFIRMED else SUSPECTED,
                    "extractor": extractor, "evidence": said["evidence"]}))
    if dropped and not out:
        raise llm.LlmRefused("every link of the answer (%d) quotes evidence the text does not hold"
                             " - link %d: %r" % (len(dropped), dropped[0],
                                                 links[dropped[0] - 1]["evidence"][:120]))
    return out


def _ask(request, prompt_of, read):
    """One request -> ({id: rows}, {id: why}) for its texts [(id, text)]: the answer's item of each id,
    read by `read(text, links)`. An answer refused whole gives every text its sentence; a call that
    failed (`LlmCallFailed`) is raised - the whole batch fails and the chain asks it again later."""
    from database import crud
    from utils import llm

    try:
        answer = llm.ask_json(prompt_of(request))
        items = answer.get("texts")
        if not isinstance(items, list):
            raise llm.LlmRefused("the answer has no 'texts' list: %s" % sorted(answer)[:10])
    except llm.LlmCallFailed:
        raise
    except llm.LlmRefused as exc:
        return {}, {ident: str(exc) for ident, _text in request}
    by_id = {}
    for item in items:
        if isinstance(item, dict):
            by_id.setdefault(crud.clean_str_value(item.get("id")), item)
    rows, why = {}, {}
    for ident, text in request:
        item = by_id.get(crud.clean_str_value(ident))
        if item is None:
            why[ident] = "the answer has no item for text %r" % (ident,)
        elif not isinstance(item.get("links"), list):
            why[ident] = "the answer's item for text %r has no 'links' list: %s" % (ident, sorted(item)[:10])
        else:
            try:
                rows[ident] = read(text, item["links"])
            except llm.LlmRefused as exc:
                why[ident] = str(exc)
    return rows, why


#: What `known` adds under the dictionary (총괄 d7a27a758 · 423599fe9, 소유자 「모델링이 서로 연결이 되어야」):
#: the links already known among the request's nodes, and three asks - no word of any domain.
KNOWN_HEADING = "Known links, one per line: <cause id> -> <effect id>, <effect id> (<predicate>)"
KNOWN_ASKS = (
    "Where a node of the dictionary or of the known links is what a text names, link to that node - a new"
    " node only when none fits.",
    "When a text names a step between the two ends of a known link, link that step: one link into it and one"
    " out of it.",
    "When A causes B and B causes C, answer A -> B and B -> C as two links, and give one thing the same"
    " identifier or the same words in every text of this request.",
)
#: The qualifier a known link is confirmed by - the cell `ask_links` rows carry, bound to the ledger as such.
CERTAINTY = "certainty"


def _walked(seeds, follow, hops):
    """The operating world's walk from `seeds` [(node_type, node_key)] along `follow`, `hops` steps - the
    screen's own walk (`trace_router._evidence_graph`, no bundles), called directly on a connection of its
    own. A seed of a type that does not declare exactly one key has no id from one node_key - left out,
    one line."""
    from database import database
    from declaration_names import bare_name
    from ledger import explorer, trace_router
    from ledger_api import ledger_subgraph

    ids, left = [], []
    for node_type, key in seeds:
        bare = bare_name(str(node_type))
        order = ledger_subgraph._declared_key_order(bare) or ()
        if len(order) == 1:
            ids.append(explorer.entity_id(bare, {order[0]: key}))
        else:
            left.append(bare)
    if left:
        logger.warning("[LLM] known links: %d seed(s) not walked - type(s) %s do not declare exactly one key",
                       len(left), ", ".join(sorted(set(left))))
    if not ids:
        return {"nodes": [], "edges": []}
    with database.engine.connect() as connection:
        return trace_router._evidence_graph(
            connection, node_id={"positive": ids, "negative": []}, hops=hops, direction="both",
            node_limit=ledger_subgraph.DEFAULT_NODE_LIMIT, edge_limit=ledger_subgraph.DEFAULT_EDGE_LIMIT,
            follow=list(follow))


def _known_links(walk, node_of, follow):
    """The walk's edges along `follow` both ends of which are dictionary nodes, as
    {cause, effect, predicate, confirmed, support} - support = the edge's records, confirmed = a record
    says certainty confirmed (the qualifier `ask_links` rows carry)."""
    from declaration_names import bare_name
    from ledger_api import ledger_subgraph

    wanted = {bare_name(str(name)) for name in follow}
    by_ref = {(bare_name(str(node[0])), str(node[1])): node for node in node_of}

    def node(node_id):
        try:
            found = ledger_subgraph.decode_node_id(node_id)
        except ValueError:
            return None
        keys = list((found.get("keys") or {}).values())
        return by_ref.get((bare_name(str(found["type"])), str(keys[0]))) if len(keys) == 1 else None

    out = {}
    for edge in walk.get("edges") or ():
        predicate = bare_name(str(edge.get("predicate")))
        cause, effect = node(edge.get("source")), node(edge.get("target"))
        if predicate not in wanted or cause is None or effect is None:
            continue
        records = list(edge.get("records") or ())
        link = out.setdefault((cause, effect, predicate), {"cause": cause, "effect": effect, "predicate": predicate,
                                                           "confirmed": False, "support": 0})
        link["support"] = max(link["support"], len(records) + int(edge.get("records_more") or 0))
        link["confirmed"] = link["confirmed"] or any(
            (said.get("qualifiers") or {}).get(CERTAINTY) == CONFIRMED for said in [edge, *records])
    return list(out.values())


def _chosen(seeds, links, per_seed, node_of):
    """`links` in the order they go in (총괄 423599fe9): bridges - on a shortest way between two seeds -
    first; then by steps from the nearest seed (1, 2, ...), the seeds taking turns, at most `per_seed`
    each (bridges not counted); within each, confirmed first, more records, then the identifiers. The
    ways are the links' own, read both ways. A link no seed reaches through them is left out."""
    from collections import deque

    def order(link):
        return (not link["confirmed"], -link["support"],
                node_of[link["cause"]], node_of[link["effect"]], link["predicate"])

    near = {}
    for link in links:
        near.setdefault(link["cause"], set()).add(link["effect"])
        near.setdefault(link["effect"], set()).add(link["cause"])
    far = {}
    for seed in seeds:
        far[seed], queue = {seed: 0}, deque([seed])
        while queue:
            at = queue.popleft()
            for step in sorted(near.get(at, ()), key=node_of.__getitem__):
                if step not in far[seed]:
                    far[seed][step] = far[seed][at] + 1
                    queue.append(step)

    def bridges(link):
        a, b = link["cause"], link["effect"]
        return any(s != t and t in far[s] and (
            (a in far[s] and b in far[t] and far[s][a] + 1 + far[t][b] == far[s][t])
            or (b in far[s] and a in far[t] and far[s][b] + 1 + far[t][a] == far[s][t]))
            for s in seeds for t in seeds)

    out = sorted((link for link in links if bridges(link)), key=order)
    bridged = {id(link) for link in out}
    by_step = {}
    for link in links:
        if id(link) in bridged:
            continue
        reach = [(min(far[s].get(link["cause"], math.inf), far[s].get(link["effect"], math.inf)), n)
                 for n, s in enumerate(seeds)]
        steps, owner = min(reach) if reach else (math.inf, None)
        if steps != math.inf:
            by_step.setdefault(steps + 1, {}).setdefault(seeds[owner], []).append(link)
    taken = Counter()
    for step in sorted(by_step):
        queues = {seed: deque(sorted(by_step[step].get(seed, ()), key=order)) for seed in seeds}
        while True:
            moved = False
            for seed in seeds:
                if queues[seed] and taken[seed] < per_seed:
                    out.append(queues[seed].popleft())
                    taken[seed] += 1
                    moved = True
            if not moved:
                break
    return out


def _known_lines(kept, node_of):
    """«<cause id> -> <effect id>, <effect id> (<predicate>)» - one line per cause and predicate, in the
    order the links were kept."""
    grouped = {}
    for link in kept:
        grouped.setdefault((link["cause"], link["predicate"]), []).append(link["effect"])
    return ["%s -> %s (%s)" % (node_of[cause], ", ".join(node_of[effect] for effect in effects), predicate)
            for (cause, predicate), effects in grouped.items()]


def _known(texts, names, known, cells, match_at):
    """(the dictionary as this request lists it, the block under it, what was cut) for `known`: the seeds
    are the nodes a phrase of which a text holds (`phrase_bag.held_nodes`), in identifier order; the walk
    from them gives the known links, `_chosen` their order. Within `known_chars` - the dictionary lines and
    the known-link lines together - the seeds go first, then the links in order, each with its nodes; the
    first that does not fit ends it. The dictionary lists those nodes only."""
    from utils import phrase_bag

    by_id, lines = _node_lines(names)
    node_of = {node: ident for ident, node in by_id.items()}
    seeds = sorted(phrase_bag.held_nodes(texts, names, match_at), key=node_of.__getitem__)
    links = _known_links(_walked(seeds, known["follow"], known["hops"]), node_of, known["follow"]) if seeds else []
    cap = cells["known_chars"]

    def size(listed, kept):
        said = [lines[node] for node in listed] + ([KNOWN_HEADING] + _known_lines(kept, node_of) if kept else [])
        return len("\n".join(said))

    listed, kept = [], []
    for seed in seeds:
        if size(listed + [seed], kept) > cap:
            break
        listed.append(seed)
    for link in _chosen(seeds, links, cells["known_per_seed"], node_of) if len(listed) == len(seeds) else ():
        more = [node for node in dict.fromkeys((link["cause"], link["effect"])) if node not in listed]
        if size(listed + more, kept + [link]) > cap:
            break
        listed += more
        kept.append(link)
    block = ([KNOWN_HEADING] + _known_lines(kept, node_of) if kept else []) + list(KNOWN_ASKS)
    said = {"seeds": len(seeds), "links": len(links), "kept": len(kept), "nodes": len(by_id), "listed": len(listed)}
    return "\n".join(line for node, line in lines.items() if node in listed), "\n".join(block), said


def ask_links(text, names, instruction=None, match_at=None, known=None):
    """`find_links`' rows, read by the language model `mapper_sdk.ask_json` reaches. `text` is one text
    (a str) or many - [{"id": <row key>, "text": <text>}], ids unique; each row of many carries its
    text's `text_id` first. Either way an `AskedLinks` comes back: the rows, the texts in their order,
    and what it took.

    `known` - {"follow": [<predicate>, ...], "hops": n}, the mapper's - puts the links already known
    among a request's nodes under its dictionary, and the dictionary becomes those nodes only (`_known`);
    `AskedLinks.known` says per request what was cut. Absent, the prompt is as without it.

    One request holds the dictionary and the instruction once and the texts, each after its «[id]»
    line, up to `batch_chars` characters of text (llm_config.json; a str is one text under id
    ONE_TEXT_ID). The answer gives each id its links. A text the answer has no item for, or an item
    that is not read (no links list, a link without cause, effect or evidence, every link's evidence
    outside that text), is asked again alone once - one warning line says which, for the request -
    then refused with its sentence: no rows, one warning line, `refused` - a mapper hands those ids on
    as `mapper_sdk.UNREAD_JOBS` so their old rows are not retracted. A text alone in its request is not
    asked again. Every text refused raises `LlmRefused` (a single text: its own sentence). A call that
    failed (`LlmCallFailed`) is not asked again text by text: it is raised at once.

    Each text's links are read in that text alone, as one text always was. The model sees `names`
    one node per line - its identifier (the key; `<type>:<key>` for a key two types share) and all its
    phrases - and answers a node's identifier or null for a cause and an effect, with the text's own
    words. A listed identifier gives that node's type and key; null gives the node whose phrase its
    words hold (`phrase_bag`); an identifier not listed gives none and is said in one warning line.
    *_phrase is always the words. `certainty` is what the text says, `suspected` when it says nothing -
    nothing becomes a fact before a person confirms it. Every «one of the listed» answer - an
    identifier, a direction, the certainty - is read by `one_of` (spaces trimmed, case kept); an
    answer outside the list is said in one warning line. `cause_direction` / `phenomenon_direction`
    is the answer when it is one of DIRECTIONS as written, else None. `dir` is their sign (`_signed`).

    A link's evidence is looked for in the whole of its text (`_evidence`); its sentence runs from the
    start of the sentence the quote starts in to the end of the one it ends in, and sentence_no is the
    first's. A link whose evidence its text does not hold is dropped and said in one warning line."""
    from database import crud
    from utils import llm

    many = isinstance(text, (list, tuple))
    texts = ([(item["id"], str(item.get("text") or "")) for item in text] if many
             else [(ONE_TEXT_ID, str(text or ""))])
    if not texts:
        return AskedLinks()
    seen = Counter(crud.clean_str_value(ident) for ident, _text in texts)
    twice = sorted(ident for ident, count in seen.items() if count > 1)
    if twice:
        raise ValueError("ask_links: text ids must be unique - %s given twice" % ", ".join(map(repr, twice[:5])))
    if known is not None and not (
            isinstance(known, dict) and known.get("follow") and not isinstance(known["follow"], str)
            and isinstance(known.get("hops"), int) and not isinstance(known["hops"], bool) and known["hops"] > 0):
        raise ValueError("ask_links: known is {'follow': [<predicate>, ...], 'hops': <steps above 0>}, got %r" % (known,))
    cells = llm.settings()
    names = list(names or ())
    by_id, dictionary = _listing(names)
    extractor = LLM_EXTRACTOR % llm.model()
    instructed = ("%s\n%s" % (INSTRUCTION_HEADING, instruction)
                  if not crud.is_blank_value(instruction) else "")
    cut = []

    def prompt_of(request):
        listed = dictionary
        if known is not None:
            listed, block, said = _known([one for _ident, one in request], names, known, cells, match_at)
            listed += "\n" + block
            cut.append(dict(said, texts=[ident for ident, _one in request]))
            logger.info("[LLM] known links for %d text(s): %d seed(s), %d of %d link(s), dictionary %d of %d node(s)",
                        len(request), said["seeds"], said["kept"], said["links"], said["listed"], said["nodes"])
        return (ASK_LINKS_PROMPT
                .replace("<<dictionary>>", listed)
                .replace("<<instruction>>", instructed)
                .replace("<<texts>>", "\n\n".join("[%s]\n%s" % pair for pair in request)))

    def read(one, links):
        return _read(one, links, names, by_id, match_at, extractor)

    rows, why, asked = {}, {}, 0
    for request in _requests(texts, cells["batch_chars"]):
        got, failed = _ask(request, prompt_of, read)
        asked += 1
        rows.update(got)
        if failed and len(request) > 1:
            logger.warning("[LLM] a request of %d texts left %d unread - each asked alone: %s", len(request),
                           len(failed), "; ".join("%r: %s" % (ident, said[:160]) for ident, said in failed.items()))
            for ident, one in request:
                if ident in failed:
                    got, failed_alone = _ask([(ident, one)], prompt_of, read)
                    asked += 1
                    rows.update(got)
                    why.update(failed_alone)
        else:
            why.update(failed)
    if not rows:
        first, said = next(iter(why.items()))
        raise llm.LlmRefused(said if not many else "every text (%d) was refused - text %r: %s"
                             % (len(texts), first, said))
    for ident, said in why.items():
        logger.warning("[LLM] text %r refused - no rows (%s): %s", ident, extractor, said[:300])
    logger.info("[LLM] ask_links: %d text(s) in %d request(s) - %d row(s), %d text(s) refused",
                len(texts), asked, sum(len(found) for found in rows.values()), len(why))
    return AskedLinks([{"text_id": ident, **row} if many else row
                       for ident, _text in texts for row in rows.get(ident, ())],
                      requests=asked, texts=len(texts),
                      refused=[{"id": ident, "reason": said} for ident, said in why.items()], known=cut)


def unknown_words(texts, names, links):
    """[{word, count}] most frequent first: the words of these texts that no dictionary phrase
    covered - where a dictionary grows. Counted as written; filtering is the caller's."""
    index = _dictionary(names, links)
    counts = Counter()
    for text in texts or ():
        for sentence in _sentences(text):
            spans = [(s, e) for s, e, _w, _r in _matches(sentence, index)]
            rest = "".join(" " if any(s <= i < e for s, e in spans) else ch
                           for i, ch in enumerate(sentence))
            counts.update(_WORD.findall(rest))
    return [{"word": word, "count": count} for word, count in counts.most_common()]
