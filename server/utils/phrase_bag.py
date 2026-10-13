# -*- coding: utf-8 -*-
"""The node a phrase names, by the bag of its character bigrams (소유자 10-11 「단어로 맞추기가 쉽지
않네 너무 다양해」 · 「자꾸 수식어 붙여」 · 「워드백 느낌으로」).

    bag    the set of character bigrams of the text folded as `text_links._evidence` folds it -
           spaces, case, quote marks and ellipsis out; a one-character text's bag is that character
    score  of a node for an answer = max over its phrases of |phrase bag & answer bag| / |phrase bag| -
           how much of the NODE's phrase the answer holds, so the words around it do not lower it
    pick   the node with the top score >= match_at. At the top, a phrase whose bag is inside another
           node's phrase's bag drops (the longer wins); two different nodes left -> no node

`names` rows are text_links' {node_type, node_key, phrase}.
"""
from collections import Counter

from utils import text_links

#: The whole node phrase is in the answer.
MATCH_AT = 1.0
SIDES = ("cause", "phenomenon")


def _bag(text):
    from chain.mapper_call import without_missing
    from database import crud

    text = without_missing(text)
    if crud.is_blank_value(text):
        return set()
    folded = text_links._evidence(str(text))[0]
    return {folded} if len(folded) == 1 else {folded[i:i + 2] for i in range(len(folded) - 1)}


def _index(names):
    """([(node, phrase, bag)], {bigram: [position, ...]}) of the rows whose phrase has a bag."""
    from chain.mapper_call import without_missing

    phrases, by_gram = [], {}
    for row in names or ():
        row = without_missing(dict(row))
        bag = _bag(row.get("phrase"))
        if not bag:
            continue
        for gram in bag:
            by_gram.setdefault(gram, []).append(len(phrases))
        phrases.append(((row.get("node_type"), row.get("node_key")), str(row["phrase"]), bag))
    return phrases, by_gram


def _scored(answer, index, match_at):
    """[(score, position)] of the phrases scoring `match_at` (None: MATCH_AT) or more, in dictionary order."""
    phrases, by_gram = index
    at = MATCH_AT if match_at is None else float(match_at)
    hits = Counter(position for gram in _bag(answer) for position in by_gram.get(gram, ()))
    scored = [(hits[p] / len(phrases[p][2]), p) for p in sorted(hits)]
    return [(score, p) for score, p in scored if score >= at]


def _pick(answer, index, match_at):
    phrases = index[0]
    scored = _scored(answer, index, match_at)
    if not scored:
        return None
    top = max(score for score, _p in scored)
    held = [p for score, p in scored if score == top]
    # nested: a phrase inside another node's phrase drops - the longer wins, as in find_links
    kept = [p for p in held if not any(phrases[q][0] != phrases[p][0] and phrases[p][2] < phrases[q][2]
                                       for q in held)]
    nodes = list(dict.fromkeys(phrases[p][0] for p in kept))
    if len(nodes) > 1:
        return {"node_type": None, "node_key": None, "score": top, "phrase": None,
                "ambiguous": [{"node_type": t, "node_key": k} for t, k in nodes]}
    return {"node_type": nodes[0][0], "node_key": nodes[0][1], "score": top,
            "phrase": phrases[kept[0]][1], "ambiguous": []}


def match_phrase(answer, names, match_at=MATCH_AT):
    """{node_type, node_key, score, phrase, ambiguous} of the node `answer` names - `phrase` is the
    dictionary phrase that scored. Two different nodes left at the top: node_type · node_key ·
    phrase are None and `ambiguous` holds them. None when no node reaches `match_at` (None: MATCH_AT)."""
    names = list(names or ())
    return _pick(answer, _index(names), match_at)


def held_nodes(texts, names, match_at=None):
    """[(node_type, node_key)] of every node one of `texts` holds a phrase of, scored as `match_phrase`
    scores, in the dictionary's order - `text_links.ask_links`' seeds. Every node at `match_at` or above,
    not the top one: a text names many."""
    index = _index(list(names or ()))
    held = sorted({p for text in texts or () for _score, p in _scored(text, index, match_at)})
    return list(dict.fromkeys(index[0][p][0] for p in held))


def rematch_rows(rows, names, match_at=None):
    """Candidate rows (`<side>_phrase` · `<side>_type` · `<side>_key` for cause and phenomenon) with
    only a blank key filled, and its type when blank, where the bag names a node. A filled key is
    never written, nor a side whose filled type is not the found node's. Each row comes back as a
    shallow copy, so one nothing was filled in is equal to the one handed in (NaN cells too)."""
    from chain.mapper_call import without_missing
    from database import crud

    names = list(names or ())
    index = _index(names)
    out = []
    for row in rows or ():
        row = dict(row)
        seen = without_missing(dict(row))
        for side in SIDES:
            type_cell, key_cell = side + "_type", side + "_key"
            if not crud.is_blank_value(seen.get(key_cell)):
                continue
            found = _pick(seen.get(side + "_phrase"), index, match_at)
            if not found or found["node_key"] is None:
                continue
            if not crud.is_blank_value(seen.get(type_cell)) and (
                    crud.clean_str_value(seen[type_cell]) != crud.clean_str_value(found["node_type"])):
                continue
            row[type_cell], row[key_cell] = found["node_type"], found["node_key"]
        out.append(row)
    return out
