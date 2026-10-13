"""The server's expression calculator (lead 5667ea0fe, owner 93b0c7a4b): Spotfire's expression language over rows.

The screen's twin is client2/src/expression.js; both are scored by contracts/expression/vectors.json
(tests/test_the_server_calculator_solves_the_shared_vectors.py). A text is read into a tree once (`compile`), then
answered over rows (`run`). One grammar, one function table, no eval.

Rows: dicts ({"x": 1, "$at": "2026-...Z"}) - a value may be a list (a fold counts its items, a row-by-row use needs one
value). `types` ({column: "datetime"}, the words of table_config's column_types): Min and Max over a datetime column
compare instants and answer the row's value as it is (lead 10-13).
Refused by name here: Marked (the page's markings are the screen's) and ways - a name holding «.» or «~» ([a.b~.x])
is a walk from the row, not read on the server yet.
"""
import json
import math
import re
from functools import cmp_to_key


class ExpressionError(Exception):
    """A refusal in words - what the declaration is told."""


class SeveralValues(Exception):
    """A row-by-row use of a value the row holds several of."""


# ── values ──────────────────────────────────────────────────────────────────────────────────────────────────────────
#: Python's whitespace (str.isspace) - the screen's absent.js SPACE is the same 29 codepoints.
NUMERAL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_blank(v):
    """Empty: None, a text of only whitespace, a list of only empties, a dict with no keys. 0 · False · NaN are values."""
    if v is None:
        return True
    if isinstance(v, str):
        return all(ch.isspace() for ch in v)
    if isinstance(v, (list, tuple)):
        return all(is_blank(x) for x in v)
    if isinstance(v, dict):
        return not v
    return False


def number_of(v):
    """A number, or a text that is only sign · digits · point · exponent (trimmed) - else None."""
    if _is_num(v):
        return v if math.isfinite(v) else None
    if not isinstance(v, str) or not NUMERAL.match(v.strip()):
        return None
    n = float(v.strip())
    return n if math.isfinite(n) else None


def _finite(v):
    return None if _is_num(v) and not math.isfinite(v) else v


def _js_number(n):
    """A number as JavaScript's String() writes it - the screen's spelling, so distinct values and joins agree."""
    if isinstance(n, int):
        return str(n)
    if n.is_integer() and abs(n) < 1e21:
        return str(int(n))
    text = repr(n)
    if "e" in text:
        mantissa, exp = text.split("e")
        return "%se%s%d" % (mantissa, "+" if int(exp) > 0 else "-", abs(int(exp)))
    return text


def _text(v):
    if v is True or v is False:
        return "true" if v else "false"
    if _is_num(v):
        return _js_number(v)
    return str(v)


def _spelling(v):
    if v is None:
        return "null"
    if v is True or v is False or _is_num(v):
        return _text(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_spelling(x) for x in v) + "]"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return json.dumps(str(v), ensure_ascii=False)


def _order(a, b):
    """Text by character, numbers by size - the one order `<` and UniqueConcatenate keep."""
    if _is_num(a) and _is_num(b):
        return (a > b) - (a < b)
    x, y = _text(a), _text(b)
    return (x > y) - (x < y)


def _distinct(items):
    seen = {}
    for it in items:
        seen.setdefault(_spelling(it["value"]), it["value"])
    return list(seen.values())


def _instant(v):
    from utils.time_format import instant_key

    return None if is_blank(v) else instant_key(v)


# ── the function table ──────────────────────────────────────────────────────────────────────────────────────────────
def _nums(items):
    return [x for x in (number_of(it["value"]) for it in items) if x is not None]


def _numeric(f):
    def folded(items, params):
        xs = _nums(items)
        return {"value": f(xs, params) if xs else None}
    return folded


def _mean(xs):
    return sum(xs) / len(xs)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[(n - 1) // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _var(xs):
    return None if len(xs) < 2 else sum((v - _mean(xs)) ** 2 for v in xs) / (len(xs) - 1)


def _sd(xs):
    return None if len(xs) < 2 else math.sqrt(_var(xs))


def _pct(xs, p):
    """7.0.1 «Percentiles and Quartiles»: interpolated between the values around p."""
    s = sorted(xs)
    h = (len(s) - 1) * p
    lo, hi = math.floor(h), math.ceil(h)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


def _q1(xs):
    return _pct(xs, 0.25)


def _q3(xs):
    return _pct(xs, 0.75)


def _iqr(xs):
    return _q3(xs) - _q1(xs)


def _uav(xs):
    inside = [v for v in xs if v <= _q3(xs) + 1.5 * _iqr(xs)]
    return max(_q3(xs), max(inside)) if inside else _q3(xs)


def _lav(xs):
    inside = [v for v in xs if v >= _q1(xs) - 1.5 * _iqr(xs)]
    return min(_q1(xs), min(inside)) if inside else _q1(xs)


def _outliers(xs):
    return len([v for v in xs if v > _uav(xs) or v < _lav(xs)])


T95 = 1.959964


def _latest(items, _params=None):
    """With any timed item the newest of those (an untimed item is no candidate); with none timed the value when there
    is one or all agree. Two different values at the newest time: none - no rule orders them (lead 10-13)."""
    if not items:
        return {"value": None}
    timed = [it for it in items if it["t"] is not None]
    if not timed:
        one = _distinct(items)
        return {"value": one[0] if len(one) == 1 else None}
    newest = max(it["t"] for it in timed)
    at = _distinct([it for it in timed if it["t"] == newest])
    return {"value": at[0] if len(at) == 1 else None}


def _most_common(items, _params=None):
    counts = {}
    for it in items:
        entry = counts.setdefault(_spelling(it["value"]), [it["value"], 0])
        entry[1] += 1
    best = None
    for entry in counts.values():              # a tie keeps the one met first
        if best is None or entry[1] > best[1]:
            best = entry
    return {"value": best[0] if best else None}


def _pair_nums(pairs):
    out = [(number_of(p[0]), number_of(p[1])) for p in pairs]
    return [(x, y) for x, y in out if x is not None and y is not None]


def _value_for(pick, last):
    def folded(pairs, _params=None):
        keyed = [(number_of(x), y) for x, y in pairs]
        keyed = [(k, y) for k, y in keyed if k is not None]
        if not keyed:
            return {"value": None}
        target = pick(k for k, _ in keyed)
        hits = [y for k, y in keyed if k == target]
        return {"value": hits[-1] if last else hits[0]}
    return folded


def _weighted(pairs, _params=None):
    ps = _pair_nums(pairs)
    w = sum(x for x, _ in ps)
    return {"value": sum(x * y for x, y in ps) / w if ps and w != 0 else None}


def _covariance(pairs, _params=None):
    ps = _pair_nums(pairs)
    if len(ps) < 2:
        return {"value": None}
    mx, my = _mean([x for x, _ in ps]), _mean([y for _, y in ps])
    return {"value": sum((x - mx) * (y - my) for x, y in ps) / (len(ps) - 1)}


def _trimmed(xs, params):
    p = params[0]
    if p is None:
        return None
    k = math.floor(len(xs) * p / 100 / 2)
    kept = sorted(xs)[k:len(xs) - k]
    return _mean(kept) if kept else None


def _nth(largest):
    def nth(xs, params):
        n = params[0]
        if n is None or n < 1:
            return None
        s = sorted(xs, reverse=largest)
        return s[min(math.floor(n), len(xs)) - 1]
    return nth


def _geometric(xs, _params):
    if any(v < 0 for v in xs):
        return None
    if any(v == 0 for v in xs):
        return 0
    return math.exp(_mean([math.log(v) for v in xs]))


def _fold(fn, **more):
    return dict(kind="fold", fn=fn, **more)


def _row(arity, fn):
    def safe(*args):
        try:
            return fn(*args)
        except (OverflowError, ZeroDivisionError, ValueError):
            return None                         # JavaScript's Infinity or NaN - an empty answer
    return {"kind": "row", "arity": arity, "fn": safe}


def _num1(f):
    def one(a):
        x = number_of(a)
        return None if x is None else f(x)
    return _row(1, one)


def _num2(f):
    def two(a, b):
        x, y = number_of(a), number_of(b)
        return None if x is None or y is None else f(x, y)
    return _row(2, two)


def _round(x, d):
    digits = math.trunc(d)                      # only Arg2's integer part (Math «Round»)

    def away(v):                                # 0.5 to the higher magnitude
        return math.copysign(math.floor(abs(v) + 0.5), v) if v else 0
    return away(x * 10 ** digits) / 10 ** digits if digits >= 0 else away(x / 10 ** -digits) * 10 ** -digits


def _times(f):
    """A fold over a datetime column (lead 10-13): instants compared, the row's value answered; a text that is not a
    time and an empty value are left out; the same instant twice - the one met first."""
    def folded(items, _params=None):
        timed = [(key, it["value"]) for key, it in ((_instant(it["value"]), it) for it in items) if key is not None]
        if not timed:
            return {"value": None}
        best = timed[0]
        for each in timed[1:]:
            if f(each[0], best[0]):
                best = each
        return {"value": best[1]}
    return folded


#: A fold whose argument is a datetime column answers by these instead (Min · Max, lead 10-13).
BY_TIME = {"Min": _times(lambda a, b: a < b), "Max": _times(lambda a, b: a > b)}

FUNCTIONS = {
    "Count": _fold(lambda items, _p=None: {"value": len(items)}, none=True),
    "CountBig": _fold(lambda items, _p=None: {"value": len(items)}, none=True),
    "UniqueCount": _fold(lambda items, _p=None: {"value": len(_distinct(items))}),
    "Sum": _fold(_numeric(lambda xs, _p: sum(xs)), rowwise=True),
    "Avg": _fold(_numeric(lambda xs, _p: _mean(xs)), rowwise=True),
    "Min": _fold(_numeric(lambda xs, _p: min(xs)), rowwise=True),
    "Max": _fold(_numeric(lambda xs, _p: max(xs)), rowwise=True),
    "Median": _fold(_numeric(lambda xs, _p: _median(xs)), rowwise=True),
    "Product": _fold(_numeric(lambda xs, _p: math.prod(xs)), rowwise=True),
    "MeanDeviation": _fold(_numeric(lambda xs, _p: _mean([abs(v - _mean(xs)) for v in xs])), rowwise=True),
    "MedianAbsoluteDeviation": _fold(_numeric(lambda xs, _p: _median([abs(v - _median(xs)) for v in xs])),
                                     rowwise=True),
    "First": _fold(lambda items, _p=None: {"value": items[0]["value"] if items else None}),
    "Last": _fold(lambda items, _p=None: {"value": items[-1]["value"] if items else None}),
    "Latest": _fold(_latest),
    "MostCommon": _fold(_most_common),
    "UniqueConcatenate": _fold(lambda items, _p=None: {"value": ", ".join(
        _text(v) for v in sorted(_distinct(items), key=cmp_to_key(_order))) if items else None}),
    "StdDev": _fold(_numeric(lambda xs, _p: _sd(xs))),
    "Var": _fold(_numeric(lambda xs, _p: _var(xs))),
    "StdErr": _fold(_numeric(lambda xs, _p: None if len(xs) < 2 else _sd(xs) / math.sqrt(len(xs)))),
    "Range": _fold(_numeric(lambda xs, _p: max(xs) - min(xs))),
    "Q1": _fold(_numeric(lambda xs, _p: _q1(xs))),
    "Q3": _fold(_numeric(lambda xs, _p: _q3(xs))),
    "IQR": _fold(_numeric(lambda xs, _p: _iqr(xs))),
    "P10": _fold(_numeric(lambda xs, _p: _pct(xs, 0.1))),
    "P90": _fold(_numeric(lambda xs, _p: _pct(xs, 0.9))),
    "Percentile": _fold(_numeric(lambda xs, p: None if p[0] is None else _pct(xs, p[0] / 100)), params=1),
    "Percent": _fold(_numeric(lambda xs, p: None if p[0] is None
                              else min(xs) + (p[0] / 100) * (max(xs) - min(xs))), params=1),
    "LIF": _fold(_numeric(lambda xs, _p: _q1(xs) - 1.5 * _iqr(xs))),
    "UIF": _fold(_numeric(lambda xs, _p: _q3(xs) + 1.5 * _iqr(xs))),
    "LOF": _fold(_numeric(lambda xs, _p: _q1(xs) - 3 * _iqr(xs))),
    "UOF": _fold(_numeric(lambda xs, _p: _q3(xs) + 3 * _iqr(xs))),
    "LAV": _fold(_numeric(lambda xs, _p: _lav(xs))),
    "UAV": _fold(_numeric(lambda xs, _p: _uav(xs))),
    "Outliers": _fold(_numeric(lambda xs, _p: _outliers(xs))),
    "PctOutliers": _fold(_numeric(lambda xs, _p: 100 * _outliers(xs) / len(xs))),
    "GeometricMean": _fold(_numeric(_geometric)),
    "TrimmedMean": _fold(_numeric(_trimmed), params=1),
    "NthLargest": _fold(_numeric(_nth(True)), params=1),
    "NthSmallest": _fold(_numeric(_nth(False)), params=1),
    "L95": _fold(_numeric(lambda xs, _p: None if len(xs) < 2 else _mean(xs) - T95 * _sd(xs) / math.sqrt(len(xs)))),
    "U95": _fold(_numeric(lambda xs, _p: None if len(xs) < 2 else _mean(xs) + T95 * _sd(xs) / math.sqrt(len(xs)))),
    # two columns: a row with either side empty is left out (lead 10-13)
    "WeightedAverage": _fold(_weighted, pair=True),
    "Covariance": _fold(_covariance, pair=True),
    "ValueForMax": _fold(_value_for(max, False), pair=True),
    "ValueForMin": _fold(_value_for(min, False), pair=True),
    "LastValueForMax": _fold(_value_for(max, True), pair=True),
    "LastValueForMin": _fold(_value_for(min, True), pair=True),
    # values
    "Abs": _num1(abs),
    "Ceiling": _num1(math.ceil),
    "Floor": _num1(math.floor),
    "Round": _num2(_round),
    "Sqrt": _num1(lambda x: None if x < 0 else math.sqrt(x)),
    "Exp": _num1(math.exp),
    "Ln": _num1(lambda x: None if x <= 0 else math.log(x)),
    "Log10": _num1(lambda x: None if x <= 0 else math.log10(x)),
    "Log": _num2(lambda x, b: None if x <= 0 or b <= 0 or b == 1 else math.log(x) / math.log(b)),
    "Mod": _num2(lambda a, b: None if b == 0 else a - b * math.floor(a / b)),
    "Power": _num2(math.pow),
    "PI": _row(0, lambda: math.pi),
    "Sin": _num1(math.sin),
    "Cos": _num1(math.cos),
    "Tan": _num1(math.tan),
    "ASin": _num1(lambda x: None if abs(x) > 1 else math.asin(x)),
    "ACos": _num1(lambda x: None if abs(x) > 1 else math.acos(x)),
    "ATan": _num1(math.atan),
    "ATan2": _num2(math.atan2),
    "If": {"kind": "if"},
}
_BY_NAME = {name.lower(): name for name in FUNCTIONS}
#: The screen's alone - the page's markings.
SCREEN_ONLY = {"marked": "Marked"}
#: task/SPOTFIRE_FUNCTIONS.md names this edition does not build (the vectors' out_of_edition) - refused by name.
NOT_YET = {"normdist", "norminv", "tdist", "tinv", "chidist", "chiinv", "fdist", "finv", "lag", "lead", "rand",
           "randbetween", "concatenate", "reach"}
#: A name holding one of these is a way from the row ([a.b~.x]) - not read on the server yet (lead 5667ea0fe).
WAY_MARKS = (".", "~")

# ── reading the text ────────────────────────────────────────────────────────────────────────────────────────────────
KEYWORDS = {"and", "or", "xor", "not", "case", "when", "then", "else", "end", "is", "null", "true", "false", "distinct"}
OPS = ["<=>", "<=", ">=", "<>", "!=", "<", ">", "=", "+", "-", "*", "/", "%", "^", "(", ")", ","]
NUMBER = re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokens(text):
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        at = i
        n = NUMBER.match(text, i)
        if n:
            out.append(("num", float(n.group(0)), at))
            i = n.end()
            continue
        if ch in "\"'":
            close = text.find(ch, i + 1)
            if close < 0:
                raise ExpressionError("A text opened at %d does not close" % (at + 1))
            out.append(("str", text[i + 1:close], at))
            i = close + 1
            continue
        if ch == "[":                            # «]]» is a «]» inside a name (Spotfire's escape)
            j, name = i + 1, ""
            while j < len(text) and not (text[j] == "]" and text[j + 1:j + 2] != "]"):
                name += text[j]
                j += 2 if text[j] == "]" else 1
            if j >= len(text):
                raise ExpressionError("A name opened at %d does not close" % (at + 1))
            out.append(("ref", name, at))
            i = j + 1
            continue
        word = WORD.match(text, i)
        if word:
            lw = word.group(0).lower()
            out.append(("kw", lw, at) if lw in KEYWORDS else ("id", word.group(0), at))
            i = word.end()
            continue
        op = next((o for o in OPS if text.startswith(o, i)), None)
        if op:
            out.append(("op", op, at))
            i += len(op)
            continue
        raise ExpressionError("«&» is not in this edition" if ch == "&"
                              else "«%s» at %d is not part of an expression" % (ch, at + 1))
    out.append(("end", None, len(text)))
    return out


def _parse(text):
    ts = _tokens(text)
    p = [0]

    def tk():
        return ts[p[0]]

    def op(v):
        return tk()[0] == "op" and tk()[1] == v

    def kw(v):
        return tk()[0] == "kw" and tk()[1] == v

    def where():
        return "at the end" if tk()[0] == "end" else "at %d" % (tk()[2] + 1)

    def need(test, what):
        if not test():
            raise ExpressionError("%s expected %s" % (what, where()))
        p[0] += 1

    def snippet():
        return text[tk()[2]:tk()[2] + 12]

    # lowest first: or · xor · and · not · = <> <=> · < > <= >= · Is Null · + - · * / % · unary - + · ^ (lead 10-13)
    def or_():
        a = xor()
        while kw("or"):
            p[0] += 1
            a = {"t": "or", "a": a, "b": xor()}
        return a

    def xor():
        a = and_()
        while kw("xor"):
            p[0] += 1
            a = {"t": "xor", "a": a, "b": and_()}
        return a

    def and_():
        a = not_()
        while kw("and"):
            p[0] += 1
            a = {"t": "and", "a": a, "b": not_()}
        return a

    def not_():
        if kw("not"):
            p[0] += 1
            return {"t": "not", "a": not_()}
        return equality()

    def equality():
        a = relational()
        while any(op(o) for o in ("=", "<>", "!=", "<=>")):
            o = tk()[1]
            p[0] += 1
            a = {"t": "cmp", "op": "<>" if o == "!=" else o, "a": a, "b": relational()}
        return a

    def relational():
        a = is_null()
        while any(op(o) for o in ("<", ">", "<=", ">=")):
            o = tk()[1]
            p[0] += 1
            a = {"t": "cmp", "op": o, "a": a, "b": is_null()}
        return a

    def is_null():
        a = additive()
        if not kw("is"):
            return a
        p[0] += 1
        negate = kw("not")
        if negate:
            p[0] += 1
        need(lambda: kw("null"), "«null»")
        return {"t": "isnull", "a": a, "negate": negate}

    def additive():
        a = multiplicative()
        while op("+") or op("-"):
            o = tk()[1]
            p[0] += 1
            a = {"t": "arith", "op": o, "a": a, "b": multiplicative()}
        return a

    def multiplicative():
        a = unary()
        while op("*") or op("/") or op("%"):
            o = tk()[1]
            p[0] += 1
            a = {"t": "arith", "op": o, "a": a, "b": unary()}
        return a

    def unary():
        if op("-") or op("+"):
            o = tk()[1]
            p[0] += 1
            a = unary()
            return {"t": "neg", "a": a} if o == "-" else a
        return power()

    def power():                                # ^ before unary minus and from the right (lead 10-13)
        a = primary()
        if op("^"):
            p[0] += 1
            return {"t": "arith", "op": "^", "a": a, "b": unary()}
        return a

    def primary():
        kind, v, _at = tk()
        if kind in ("num", "str"):
            p[0] += 1
            return {"t": "lit", "v": v}
        if kind == "ref":
            p[0] += 1
            if any(mark in v for mark in WAY_MARKS):
                raise ExpressionError("[%s] is a way from the row - ways are not read on the server yet" % v)
            return {"t": "ref", "name": v}
        if kw("null"):
            p[0] += 1
            return {"t": "lit", "v": None}
        if kw("true") or kw("false"):
            p[0] += 1
            return {"t": "lit", "v": v == "true"}
        if kw("case"):
            return case_of()
        if op("("):
            p[0] += 1
            e = or_()
            need(lambda: op(")"), "«)»")
            return e
        if kind == "id":
            return call()
        raise ExpressionError("The expression ends too soon" if kind == "end"
                              else "«%s» %s is not expected" % (snippet(), where()))

    def call():
        word = tk()[1]
        p[0] += 1
        lw = word.lower()
        if lw in SCREEN_ONLY:
            raise ExpressionError("%s is the screen's - it reads the page's markings" % SCREEN_ONLY[lw])
        name = _BY_NAME.get(lw)
        if not name:
            raise ExpressionError("%s is not in this edition" % word if lw in NOT_YET else "No function named %s" % word)
        need(lambda: op("("), "«(» after %s" % name)
        distinct = kw("distinct")
        if distinct:
            p[0] += 1
        args = []
        if not op(")"):
            args.append(or_())
            while op(","):
                p[0] += 1
                args.append(or_())
        need(lambda: op(")"), "«)» closing %s" % name)
        node = {"t": "call", "name": name, "fn": FUNCTIONS[name], "args": args, "distinct": distinct}
        _arity(node)
        return node

    def case_of():
        p[0] += 1
        subject = None if kw("when") else or_()
        whens = []
        while kw("when"):
            p[0] += 1
            when = or_()
            need(lambda: kw("then"), "«then»")
            whens.append({"when": when, "then": or_()})
        if not whens:
            raise ExpressionError("«when» expected %s" % where())
        otherwise = None
        if kw("else"):
            p[0] += 1
            otherwise = or_()
        need(lambda: kw("end"), "«end»")
        return {"t": "case", "subject": subject, "whens": whens, "otherwise": otherwise}

    tree = or_()
    if tk()[0] != "end":
        raise ExpressionError("«%s» %s is not expected" % (snippet(), where()))
    return tree


def _arity(node):
    fn, n, name = node["fn"], len(node["args"]), node["name"]
    kind = fn["kind"]
    if kind == "if":
        fits, want = n == 3, "3"
    elif kind == "row":
        fits, want = n == fn["arity"], str(fn["arity"])
    elif fn.get("pair"):
        fits, want = n == 2, "2"
    elif fn.get("params"):
        fits, want = n == 1 + fn["params"], str(1 + fn["params"])
    elif fn.get("rowwise"):
        fits, want = n >= 1, "1 or more"
    elif fn.get("none"):
        fits, want = n <= 1, "0 or 1"
    else:
        fits, want = n == 1, "1"
    if not fits:
        raise ExpressionError("%s takes %s argument%s - got %d" % (name, want, "" if want == "1" else "s", n))
    if node["distinct"] and (kind != "fold" or fn.get("pair") or (fn.get("rowwise") and n > 1)):
        raise ExpressionError("distinct goes in a one-column aggregation, not %s" % name)


def _children(node):
    out = [node.get(k) for k in ("a", "b", "subject", "otherwise")] + list(node.get("args") or [])
    for w in node.get("whens") or []:
        out += [w["when"], w["then"]]
    return [c for c in out if c]


def _row_level(node):
    """Does `node` read a row's value outside any fold - then the answer is one per row."""
    if node["t"] == "ref":
        return True
    if node["t"] == "call" and node["fn"]["kind"] == "fold":
        return False
    return any(_row_level(c) for c in _children(node))


def _names_of(node, out):
    if node["t"] == "ref":
        out.append(node["name"])
    for c in _children(node):
        _names_of(c, out)
    return out


def compile(text):                              # noqa: A001 - the screen's name for the same step
    """A text read once: {"ok": True, "tree", "per_row", "names"} or {"ok": False, "why"}."""
    try:
        tree = _parse(str(text or ""))
    except ExpressionError as exc:
        return {"ok": False, "why": str(exc)}
    return {"ok": True, "tree": tree, "per_row": _row_level(tree),
            "names": list(dict.fromkeys(_names_of(tree, [])))}


# ── answering ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _time_of_row(row):
    at = row.get("$at") if isinstance(row, dict) else None
    if _is_num(at):
        return at
    key = _instant(at) if isinstance(at, str) else None
    return key[1].timestamp() * 1000 if key and key[0] == "t" else None


def _items_of(v, t):
    """A value's items for a fold, with the row's time; a list counts as its items."""
    if isinstance(v, (list, tuple)):
        return [it for x in v for it in _items_of(x, t)]
    return [] if is_blank(v) else [{"value": v, "t": t}]


def _one_of(v, name):
    """A row's one value of a name - several distinct ones cannot be used row by row."""
    if not isinstance(v, (list, tuple)):
        return None if is_blank(v) else v
    values = _distinct(_items_of(v, None))
    if len(values) > 1:
        raise SeveralValues(name)
    return values[0] if values else None


def _bool(v):
    return v if v is True or v is False else None


def _not_number(v):
    """Not empty and not a number-text: an operator's row is empty and counted (lead 10-13 ①)."""
    return not is_blank(v) and number_of(v) is None


def _arith(o, a, b):
    x, y = number_of(a), number_of(b)
    if x is None or y is None:
        return None
    try:
        if o == "+":
            return x + y
        if o == "-":
            return x - y
        if o == "*":
            return x * y
        if o == "/":
            return None if y == 0 else x / y
        if o == "%":
            return None if y == 0 else x - y * math.floor(x / y)   # as Mod (lead 10-13)
        return math.pow(x, y)
    except (OverflowError, ZeroDivisionError, ValueError):
        return None


def _kind(v):
    return "number" if _is_num(v) else "boolean" if isinstance(v, bool) else "string" if isinstance(v, str) else "other"


def _compare(o, a, b):
    blank_a, blank_b = is_blank(a), is_blank(b)
    if o == "<=>":
        if blank_a or blank_b:
            return blank_a and blank_b
        o = "="
    if blank_a or blank_b:
        return None
    x, y = a, b
    if _kind(x) != _kind(y):
        x, y = number_of(a), number_of(b)
        if x is None or y is None:              # two kinds that are not both numbers
            return None
    c = _order(x, y)
    return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[o]


class _Ctx:
    def __init__(self, rows, types, row=None, memo=None, not_number=None):
        self.rows, self.types, self.row = rows, types, row
        self.memo = {} if memo is None else memo
        self.not_number = set() if not_number is None else not_number

    def at(self, row=None, rows=None):
        return _Ctx(self.rows if rows is None else rows, self.types, row, self.memo, self.not_number)


def _column_of(node, ctx, test):
    """The same column of a node over the same rows, worked once."""
    key = (id(node), id(ctx.rows))
    if key not in ctx.memo:
        ctx.memo[key] = (ctx.rows, [test(ctx.at(row=r)) for r in ctx.rows])     # rows kept: their id stays theirs
    return ctx.memo[key][1]


def _index_of_row(ctx):
    key = ("index", id(ctx.rows))
    if key not in ctx.memo:
        ctx.memo[key] = (ctx.rows, {id(r): i for i, r in enumerate(ctx.rows)})
    return ctx.memo[key][1][id(ctx.row)]


def _mark_not_number(ctx):
    ctx.not_number.add(id(ctx.row))


def _value(node, ctx):
    t = node["t"]
    if t == "lit":
        return node["v"]
    if t == "ref":
        if ctx.row is None:
            raise ExpressionError("[%s] is a row's value - fold it (Avg([%s])) or use it row by row"
                                  % (node["name"], node["name"]))
        return _one_of(ctx.row.get(node["name"]), node["name"])
    if t == "neg":
        a = _value(node["a"], ctx)
        if _not_number(a):
            _mark_not_number(ctx)
        x = number_of(a)
        return None if x is None else -x
    if t == "arith":
        a, b = _value(node["a"], ctx), _value(node["b"], ctx)
        if _not_number(a) or _not_number(b):
            _mark_not_number(ctx)
        return _finite(_arith(node["op"], a, b))
    if t == "cmp":
        return _compare(node["op"], _value(node["a"], ctx), _value(node["b"], ctx))
    if t == "not":
        a = _bool(_value(node["a"], ctx))
        return None if a is None else not a
    if t in ("and", "or", "xor"):
        a, b = _bool(_value(node["a"], ctx)), _bool(_value(node["b"], ctx))
        if t == "and":
            return False if a is False or b is False else True if a and b else None
        if t == "or":
            return True if a is True or b is True else False if a is False and b is False else None
        return None if a is None or b is None else a != b
    if t == "isnull":
        try:
            v = _value(node["a"], ctx)
        except SeveralValues:
            return node["negate"]
        return not is_blank(v) if node["negate"] else is_blank(v)
    if t == "case":
        return _case_value(node, ctx)
    kind = node["fn"]["kind"]
    if kind == "if":
        return _if_value(node, ctx)
    if kind == "row":
        return _finite(node["fn"]["fn"](*[_value(a, ctx) for a in node["args"]]))
    return _finite(_fold_value(node, ctx))


def _fold_value(node, ctx):
    fn, args = node["fn"], node["args"]
    if fn.get("none") and not args:
        return len(ctx.rows)                    # Count(): the rows
    if fn.get("rowwise") and len(args) > 1:
        return fn["fn"]([it for a in args for it in _items_of(_value(a, ctx), None)], [])["value"]

    def across(arg, r):
        return r.get(arg["name"]) if arg["t"] == "ref" else _value(arg, ctx.at(row=r))

    if fn.get("pair"):
        pairs = []
        for r in ctx.rows:
            x, y = _one_of(across(args[0], r), ""), _one_of(across(args[1], r), "")
            if not is_blank(x) and not is_blank(y):
                pairs.append((x, y))
        return fn["fn"](pairs)["value"]
    items = [it for r in ctx.rows for it in _items_of(across(args[0], r), _time_of_row(r))]
    if node["distinct"]:
        kept = {}
        for it in items:                        # the place of the first, the item of the last - as a Map keeps them
            kept[_spelling(it["value"])] = it
        items = list(kept.values())
    params = [number_of(_value(a, ctx.at(row=None))) for a in args[1:]]
    by_time = BY_TIME.get(node["name"])
    if by_time and args[0]["t"] == "ref" and (ctx.types or {}).get(args[0]["name"]) == "datetime":
        return by_time(items)["value"]
    return fn["fn"](items, params)["value"]


def _if_value(node, ctx):
    """An If's branches fold only the rows their condition sends them (Logic «More about using if»)."""
    c, a, b = node["args"]
    if ctx.row is None:
        cv = _bool(_value(c, ctx))
        return _value(a, ctx) if cv is True else _value(b, ctx) if cv is False else None
    conds = _column_of(c, ctx, lambda one: _bool(_value(c, one)))
    cv = conds[_index_of_row(ctx)]
    if cv is None:
        return None
    return _value(a if cv else b, ctx.at(row=ctx.row, rows=[r for r, k in zip(ctx.rows, conds) if k == cv]))


def _case_value(node, ctx):
    """A when is judged on the whole column; its then folds the rows it and no earlier when takes; a when that is not
    true goes on, and no else is empty (lead 10-13)."""
    def test(w, one):
        if node["subject"] is not None:
            return _compare("=", _value(node["subject"], one), _value(w, one)) is True
        return _bool(_value(w, one)) is True

    if ctx.row is None:
        hit = next((w for w in node["whens"] if test(w["when"], ctx)), None)
        if hit:
            return _value(hit["then"], ctx)
        return _value(node["otherwise"], ctx) if node["otherwise"] else None
    cols = [_column_of(w["when"], ctx, lambda one, w=w: test(w["when"], one)) for w in node["whens"]]
    first_true = [next((k for k, col in enumerate(cols) if col[i]), -1) for i in range(len(ctx.rows))]
    k = first_true[_index_of_row(ctx)]
    branch = node["whens"][k]["then"] if k >= 0 else node["otherwise"]
    if not branch:
        return None
    return _value(branch, ctx.at(row=ctx.row, rows=[r for r, f in zip(ctx.rows, first_true) if f == k]))


def run(compiled, rows, types=None):
    """Answer a compiled expression over rows: {"value"} once, or {"values"} one per row when it reads a row's value
    outside a fold - each with "not_number" (the rows an operator met a text that is not a number on); or
    {"several": name} · {"why": sentence}."""
    if not compiled["ok"]:
        return {"why": compiled["why"]}
    ctx = _Ctx(list(rows or []), types or {})
    try:
        if not compiled["per_row"]:
            value = _finite(_value(compiled["tree"], ctx))
            return {"value": value, "not_number": len(ctx.not_number)}
        values = [_finite(_value(compiled["tree"], ctx.at(row=r))) for r in ctx.rows]
        return {"values": values, "not_number": len(ctx.not_number)}
    except SeveralValues as exc:
        return {"several": str(exc)}
    except ExpressionError as exc:
        return {"why": str(exc)}
