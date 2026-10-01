# -*- coding: utf-8 -*-
"""Cause -> phenomenon candidates read out of free text with the caller's own dictionaries
(lead 15a4d8e43 · 9f301f9bc). Pure functions: every word comes from the rows passed in.

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
import re
from collections import Counter

CAUSE, AND, NEGATION, SUSPECTED, CONFIRMED = "cause", "and", "negation", "suspected", "confirmed"
MEANINGS = (CAUSE, AND, NEGATION, SUSPECTED, CONFIRMED)
SIDES = ("before", "after")
ASSERTED, NEGATED, STATED = "asserted", "negated", "stated"
#: A sentence ends at a line break, or at . ! ? 。 followed by space - so 1.5 stays whole.
SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|\n+")
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


def _sentences(text):
    return [s for s in SENTENCE_END.split(str(text or "")) if s.strip()]


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


def find_links(text, names, links):
    """One row per candidate: sentence_no (from 1) · sentence · cause_type · cause_key ·
    cause_phrase · phenomenon_type · phenomenon_key · phenomenon_phrase · link · polarity ·
    certainty. The *_phrase cells and `link` are the words as the text wrote them."""
    index = _dictionary(names, links)
    out = []
    for number, sentence in enumerate(_sentences(text), 1):
        found = _matches(sentence, index)
        said = {row["meaning"] for _s, _e, _w, rows in found for kind, row in rows if kind == "link"}
        polarity = NEGATED if NEGATION in said else ASSERTED
        certainty = (SUSPECTED if SUSPECTED in said else CONFIRMED if CONFIRMED in said
                     else STATED)
        for (ck, cause), (ek, effect), lk in _pairs(sentence, found):
            out.append({"sentence_no": number, "sentence": sentence,
                        "cause_type": cause["node_type"], "cause_key": cause["node_key"],
                        "cause_phrase": found[ck][2],
                        "phenomenon_type": effect["node_type"],
                        "phenomenon_key": effect["node_key"], "phenomenon_phrase": found[ek][2],
                        "link": found[lk][2], "polarity": polarity, "certainty": certainty})
    return out


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
