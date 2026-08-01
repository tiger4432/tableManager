# -*- coding: utf-8 -*-
"""Scores an answer set against the oracle.

[The rule that shapes this whole module]

`truth_ambiguous.csv` exists because for those cases the correct answer is "I do not
know". A scorer that counted 미상 as a miss would rank a confident wrong answer above
an honest one -- and a confident wrong answer is the exact failure this system refuses,
because it does not look like a failure. So:

  * an unresolved case answered UNRESOLVED counts as CORRECT
  * an unresolved case answered with a VALUE is counted separately as
    `false_confidence`, and it is the number to look at first
  * a resolvable case answered UNRESOLVED is not scored as a lie; it is
    `honest_miss` -- worse than getting it right, better than getting it wrong

Nothing here rewards guessing.
"""

import csv
import os

UNRESOLVED_TOKENS = {"미상", "unresolved", "unknown", "none", "null", "", "-"}


def is_unresolved(value):
    return str(value if value is not None else "").strip().lower() in UNRESOLVED_TOKENS


def norm(value):
    """Compare like the database does, not like Python's `str` does.

    A coordinate declared `number` comes back from PostgreSQL as `11.0`; the oracle CSV
    holds `11`. Comparing `str(11.0) == "11"` is False, and the first run of this
    scorer reported **0% recall on all 5,296 rows** for exactly that reason -- a
    formatting mismatch wearing the costume of a total failure. Fold integral floats,
    the same normalization `crud.clean_str_value` applies on the write path.
    """
    if value is None:
        return ""
    s = str(value).strip()
    try:
        f = float(s)
    except (TypeError, ValueError):
        return s
    return str(int(f)) if f == int(f) else s


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_oracle(oracle_dir):
    return {n: _read(os.path.join(oracle_dir, n + ".csv")) for n in (
        "truth_wafer_position", "truth_die_lineage", "truth_frame",
        "truth_ambiguous", "truth_missing")}


def _ambiguous_index(truth_ambiguous):
    """(subject, question) pairs whose honest answer is 'unresolved'."""
    return {(r["subject"], r["question"]) for r in truth_ambiguous}


def score_frames(oracle, answers):
    """answers: rows of {space, scope, frame}."""
    amb = _ambiguous_index(oracle["truth_ambiguous"])
    by_scope = {(r["space"], r["scope"]): r for r in oracle["truth_frame"]}
    given = {(r.get("space"), r.get("scope")): r.get("frame") for r in answers}
    res = {"total": len(by_scope), "correct": 0, "wrong": 0,
           "false_confidence": 0, "honest_miss": 0, "unanswered": 0,
           "correct_by_honesty": 0}
    for key, truth in by_scope.items():
        space, scope = key
        question = space + "_frame" if space in ("core", "dt") else "frame"
        expected_unresolved = (scope, question) in amb or (scope, "dt_frame") in amb
        if key not in given:
            res["unanswered"] += 1
            continue
        ans = given[key]
        if expected_unresolved:
            if is_unresolved(ans):
                res["correct"] += 1
                res["correct_by_honesty"] += 1
            else:
                # The failure mode this fixture exists to catch: a plausible value
                # where the data cannot support one.
                res["false_confidence"] += 1
        elif is_unresolved(ans):
            res["honest_miss"] += 1
        elif ans == truth["true_frame"]:
            res["correct"] += 1
        else:
            res["wrong"] += 1
    return res


def score_die_lineage(oracle, answers):
    """answers: rows of {bond_lot, bond_slot, bond_x, bond_y, core_wafer, core_x, core_y}.

    Recall against truth, plus a separate count of answers that are confidently wrong.
    A 'core_wafer' of 미상 is an honest miss, not a wrong answer.
    """
    def key(lot, slot, x, y):
        return (norm(lot), norm(slot), norm(x), norm(y))

    truth = {}
    for r in oracle["truth_die_lineage"]:
        truth[key(r["bond_lot"], r["bond_slot"],
                  r["bond_x_true"], r["bond_y_true"])] = r
    given = {}
    for r in answers:
        given[key(r.get("bond_lot"), r.get("bond_slot"),
                  r.get("bond_x"), r.get("bond_y"))] = r
    res = {"total": len(truth), "correct": 0, "wrong": 0,
           "honest_miss": 0, "unanswered": 0,
           "wafer_right_coords_wrong": 0}
    for k, t in truth.items():
        a = given.get(k)
        if a is None:
            res["unanswered"] += 1
            continue
        if is_unresolved(a.get("core_wafer")):
            res["honest_miss"] += 1
            continue
        wafer_ok = norm(a.get("core_wafer")) == norm(t["core_wafer"])
        coord_ok = (norm(a.get("core_x")) == norm(t["core_x_true"])
                    and norm(a.get("core_y")) == norm(t["core_y_true"]))
        if wafer_ok and coord_ok:
            res["correct"] += 1
        else:
            res["wrong"] += 1
            # Reported separately because the two halves fail for different reasons:
            # the wafer comes from the lineage walk, the coordinates from the frame.
            # One number hides which of the two is actually broken.
            if wafer_ok and not coord_ok:
                res["wafer_right_coords_wrong"] += 1
    return res


def score_missing(oracle, answers):
    """answers: rows of {table, business_key_val, column, value, kind}.

    Two independent numbers: did it recover the VALUE, and did it classify the KIND
    (never existed vs pipeline dropped) -- the second is board item 4 and it is the
    one the data alone cannot answer.
    """
    truth = {(r["table"], r["business_key_val"], r["column"]): r
             for r in oracle["truth_missing"]}
    given = {(r.get("table"), r.get("business_key_val"), r.get("column")): r
             for r in answers}
    res = {"total": len(truth), "value_correct": 0, "value_wrong": 0,
           "kind_correct": 0, "kind_wrong": 0, "unanswered": 0}
    for key, t in truth.items():
        a = given.get(key)
        if a is None:
            res["unanswered"] += 1
            continue
        if not is_unresolved(a.get("value")):
            res["value_correct" if a.get("value") == t["true_value"]
                else "value_wrong"] += 1
        if not is_unresolved(a.get("kind")):
            res["kind_correct" if a.get("kind") == t["kind"] else "kind_wrong"] += 1
    return res


def score_ambiguous(oracle, all_answers):
    """Explicit honesty check across every ambiguous case, whatever it is about.

    all_answers: {(subject, question): answer_value}
    """
    res = {"total": len(oracle["truth_ambiguous"]), "answered_unresolved": 0,
           "answered_with_value": 0, "unanswered": 0, "subjects": []}
    for r in oracle["truth_ambiguous"]:
        key = (r["subject"], r["question"])
        if key not in all_answers:
            res["unanswered"] += 1
            continue
        if is_unresolved(all_answers[key]):
            res["answered_unresolved"] += 1
        else:
            res["answered_with_value"] += 1
            res["subjects"].append(r["subject"])
    return res


def summarise(report):
    lines = []
    for section, res in report.items():
        lines.append("-- %s" % section)
        for k, v in res.items():
            if k == "subjects":
                if v:
                    lines.append("     false-confidence subjects: %s"
                                 % ", ".join(map(str, v[:10])))
                continue
            lines.append("     %-20s %s" % (k, v))
    return "\n".join(lines)
