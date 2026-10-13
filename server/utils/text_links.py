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


def _listing(names):
    """({identifier: (node_type, node_key)}, the dictionary as the model sees it - one line per node,
    «<identifier> (<type>): <phrase> / <phrase>»; the identifier is the key, `<type>:<key>` for a
    key two types share)."""
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
    return by_id, "\n".join("%s (%s): %s" % (ident, node[0], " / ".join(phrases[node]))
                            for ident, node in by_id.items())


class AskedLinks(list):
    """`ask_links`' rows - a list - and what it took: `requests` (calls made, a text asked again alone
    counted) · `texts` (handed in) · `refused` ([{id, reason}] of the texts no rows came back for)."""

    def __init__(self, rows=(), *, requests=0, texts=0, refused=()):
        super().__init__(rows)
        self.requests, self.texts, self.refused = requests, texts, list(refused)


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
    read by `read(text, links)`. A call or an answer refused whole gives every text its sentence."""
    from database import crud
    from utils import llm

    try:
        answer = llm.ask_json(prompt_of(request))
        items = answer.get("texts")
        if not isinstance(items, list):
            raise llm.LlmRefused("the answer has no 'texts' list: %s" % sorted(answer)[:10])
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


def ask_links(text, names, instruction=None, match_at=None):
    """`find_links`' rows, read by the language model `mapper_sdk.ask_json` reaches. `text` is one text
    (a str) or many - [{"id": <row key>, "text": <text>}], ids unique; each row of many carries its
    text's `text_id` first. Either way an `AskedLinks` comes back: the rows, the texts in their order,
    and what it took.

    One request holds the dictionary and the instruction once and the texts, each after its «[id]»
    line, up to `batch_chars` characters of text (llm_config.json; a str is one text under id
    ONE_TEXT_ID). The answer gives each id its links. A text the answer has no item for, or an item
    that is not read (no links list, a link without cause, effect or evidence, every link's evidence
    outside that text), is asked again alone once - one warning line says which, for the request -
    then refused with its sentence: no rows, one warning line, `refused`. A text alone in its request
    is not asked again. Every text refused raises `LlmRefused` (a single text: its own sentence).

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
    cells = llm.settings()
    names = list(names or ())
    by_id, dictionary = _listing(names)
    extractor = LLM_EXTRACTOR % llm.model()
    instructed = ("%s\n%s" % (INSTRUCTION_HEADING, instruction)
                  if not crud.is_blank_value(instruction) else "")

    def prompt_of(request):
        return (ASK_LINKS_PROMPT
                .replace("<<dictionary>>", dictionary)
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
                      refused=[{"id": ident, "reason": said} for ident, said in why.items()])


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
