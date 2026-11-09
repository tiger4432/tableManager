"""The server's expression calculator (lead 5667ea0fe, owner 93b0c7a4b): Spotfire's expression language over rows.

The screen's twin is client2/src/expression.js; both are scored by contracts/expression/vectors.json
(tests/test_the_server_calculator_solves_the_shared_vectors.py). A text is read into a tree once (`compile`), then
answered over rows (`run`). One grammar, one function table, no eval.

Rows: dicts ({"x": 1, "$at": "2026-...Z"}) - a value may be a list (a fold counts its items, a row-by-row use needs one
value). `types` ({column: "datetime"}, the words of table_config's column_types): Min and Max over a datetime column
compare instants and answer the row's value as it is (lead 10-13).
Refused by name here: Marked (the page's markings are the screen's) and ways - a name holding «.» or «~» ([a.b~.x])
is a walk from the row, not read on the server yet.
Dates (lead fe2ba4b1f): a time is cut into its date and parts on the wall clock of `zone` - run's argument, else
ingestion_settings "expression_time_zone" (Asia/Seoul, owner «ㅇㅇ kst»). A time with an offset is moved there; one
without is read as that wall clock. Date · DateTime answer a time text («2026-10-14T00:00:00+09:00», «Z» at offset 0).
ParseDateTime(text, format) reads a text by a format in Spotfire's .NET spelling (owner 11-07 «2»: yyMMdd_HHmmss) - a
closed token set (`NET_TOKENS`), refused when read outside it; the reader is `utils.time_format.parse_occurred_at`.
The same zone and the same reader (`_wall`) spell a datetime key part, its join and «did this cell change» (599fc1988).
The function table's grammar (names · kinds · args), the names refused and every refusal sentence are written HERE and
nowhere else: `catalogue()` is contracts/expression/catalogue.json (`python server/expression.py` writes it), the file
the screen's calculator and formula inputs import (owner 11-09 «ㄴ»).
"""
import json
import math
import os
import re
from functools import cmp_to_key, lru_cache

from utils.time_format import NET_EXAMPLE, NET_LETTERS, NET_TOKENS


class ExpressionError(Exception):
    """A refusal in words - what the declaration is told."""


class SeveralValues(Exception):
    """A row-by-row use of a value the row holds several of."""


#: Every refusal either calculator says, by key - `{name}` fills in. The screen's own (a sheet, markings, node
#: constructors) are here too: one author for both (owner 11-09 «ㄴ»).
SENTENCES = {
    "text_open": "A text opened at {at} does not close",
    "name_open": "A name opened at {at} does not close",
    "stray": "«{ch}» at {at} is not part of an expression",
    "expected": "{what} expected {where}",
    "at_end": "at the end",
    "at": "at {at}",
    "want_null": "«null»",
    "want_close": "«)»",
    "want_open_after": "«(» after {name}",
    "want_close_of": "«)» closing {name}",
    "want_when": "«when»",
    "want_then": "«then»",
    "want_end": "«end»",
    "ends_soon": "The expression ends too soon",
    "unexpected": "«{snippet}» {where} is not expected",
    "not_in_edition": "{name} is not in this edition",
    "unsettled": "{name} is not settled - Spotfire's pages give no result to build it by",
    "takes": "{name} takes {want} argument{s} - got {n}",
    "distinct": "distinct goes in a one-column aggregation, not {name}",
    "row_value": "[{name}] is a row's value - fold it (Avg([{name}])) or use it row by row",
    "not_zone": "«{zone}» is not a time zone",
    "screen_marks": "{name} is the screen's - it reads the page's markings",
    "screen_sheet": "{name} is the screen's - a sheet's cells (A1, B1:B9)",
    "screen_way": "[{name}] is a way from the row - ways are not read on the server yet",
    "screen_constructor": "{name} is not a function here - node constructors (type(\"key\")) are the screen's",
    "no_function": "No function named {name}",
    "type_keys": "{type} takes {n} key{s} ({keys}) - got {got}",
    "cannot_answer": "Cannot answer {t}",
    "marked_row": "Marked is a row's - use it row by row",
    "marked_way": "Marked takes a way in brackets second - Marked(\"B\", [in_container])",
    "cell_sheet": "Cell references are the sheet's - {at} reads a sheet's cell",
    "key_and_value": "[{name}] is both a key and a value of {type}",
    "node_and_edge": "[{name}] is both a value of the node it reaches and of its edge",
    "datepart_other": "DatePart «{part}» is not in this edition",
    "datepart_name": "DatePart takes a part name (year · quarter · month · day · week · day of week · hour) - got {got}",
    "net_spelling": "ParseDateTime: use .NET spelling, e.g. " + NET_EXAMPLE + " - got «{fmt}»",
    "net_quote": "ParseDateTime: the quote at {at} is not closed - got «{fmt}»",
    "net_reads": "ParseDateTime reads yyyy yy MM dd HH mm ss fff and quoted text - got «{token}»",
    "net_again": "ParseDateTime: «{token}» reads the {unit} again - got «{fmt}»",
    "net_needs": "ParseDateTime needs the year, month and day (yyyy or yy, MM, dd) - got «{fmt}»",
    "net_quoted": "ParseDateTime takes its format in quotes, e.g. \"" + NET_EXAMPLE + "\"",
    "quoted": "{name} takes its {what} in quotes",
    "pattern_part": "{name} does not read «{part}» in a pattern",
    "pattern_bad": "{name}: «{pattern}» is not a pattern",
    "replacement_part": "{name} does not read «{part}» in a replacement",
    "options": "{name} takes its options from g i s - got «{got}»",
}


def say(key, **fill):
    """The sentence `key` with its blanks filled - the one way a refusal is worded."""
    return SENTENCES[key].format(**fill)


# ── values ──────────────────────────────────────────────────────────────────────────────────────────────────────────
#: Python's whitespace (str.isspace) - the screen's absent.js SPACE is the same 29 codepoints.
NUMERAL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_blank(v):
    """Empty - `crud.is_blank_value(containers=True)`: blank, and a list of only empties, a dict with no keys. 0 and
    False are values; a NaN is blank (owner 11-08 3ㄱ)."""
    from database import crud

    return crud.is_blank_value(v, containers=True)


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
    return None if is_blank(v) else _wall(v, time_zone())


# ── dates ───────────────────────────────────────────────────────────────────────────────────────────────────────────
#: ingestion_settings.json - the zone a time is cut into its date and parts in (lead fe2ba4b1f, owner «ㅇㅇ kst»).
#: A key, a join and a comparison read a time without an offset in it too (lead 599fc1988, owner «한국시간»).
ZONE_SETTING, ZONE_DEFAULT = "expression_time_zone", "Asia/Seoul"
#: The one shape a time is read in - the screen's TIME (expression.js) is the same pattern.
#: [0-9], not \d: \d also reads fullwidth digits, which the screen and PostgreSQL (`notation_norm.KEY_INSTANT_SQL`) do not.
TIME = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{1,6}))?)?)?\s*"
                  r"(Z|[+-][0-9]{2}:?[0-9]{2})?$")
#: DatePart's part names (Date and Time «DatePart») this edition answers - the others are refused by name.
PARTS = {**dict.fromkeys(("year", "yy"), "Year"), **dict.fromkeys(("quarter", "qq"), "Quarter"),
         **dict.fromkeys(("month", "mm"), "Month"),
         **dict.fromkeys(("day", "day of month", "dayofmonth", "dd"), "Day"),
         **dict.fromkeys(("week", "wk"), "Week"),
         **dict.fromkeys(("day of week", "dayofweek", "weekday", "dw"), "DayOfWeek"),
         **dict.fromkeys(("hour", "hh"), "Hour")}
#: Spotfire's other part names - not in this edition.
OTHER_PARTS = {"minute", "mi", "second", "ss", "millisecond", "ms", "day of year", "dayofyear", "dy", "year and week",
               "yearandweek", "yywk", "isoyear", "isoweek"}


#: The names already said to be no zone - each once a process.
_ZONE_REFUSED = set()


def time_zone():
    """`expression_time_zone` (an IANA name), or the default - one that does not name a zone is said (once a process)
    and read as it. Read again only once the settings file changed (`config_watcher.held`)."""
    from database import config_watcher
    from ingestion.settings import INGESTION_SETTINGS_PATH

    return config_watcher.held(config_watcher.names_of([INGESTION_SETTINGS_PATH]), "expression.time_zone", _read_zone)


def _read_zone():
    from zoneinfo import ZoneInfo

    from ingestion.settings import read_ingestion_settings

    name = read_ingestion_settings().get(ZONE_SETTING, ZONE_DEFAULT)
    try:
        return ZoneInfo(str(name))
    except (ValueError, KeyError, OSError):
        if str(name) not in _ZONE_REFUSED:
            _ZONE_REFUSED.add(str(name))
            import logging

            logging.getLogger("Expression").warning("ingestion_settings.json: %s is %r - not a time zone; read as %s",
                                                    ZONE_SETTING, name, ZONE_DEFAULT)
        return ZoneInfo(ZONE_DEFAULT)


def _wall(v, zone):
    """`v` on `zone`'s wall clock (an aware datetime), or None - empty, or not a time (`TIME`, a real day).
    A datetime as the database hands it is the same instant: one without a zone is `zone`'s wall clock, a date its
    midnight. Microseconds kept - a key told apart by them stays two keys."""
    from datetime import date, datetime, timedelta, timezone

    if isinstance(v, datetime):
        return v.replace(tzinfo=zone) if v.tzinfo is None else v.astimezone(zone)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=zone)
    if is_blank(v) or not isinstance(v, str):
        return None
    m = TIME.match(v.strip())
    if not m:
        return None
    y, mo, d, h, mi, s, frac, off = m.groups()
    try:
        moment = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0),
                          int((frac or "0").ljust(6, "0")))
        if off is None:
            return moment.replace(tzinfo=zone)          # fold 0: a wall clock the zone skips or repeats - the offset before
        digits = "0000" if off == "Z" else off[1:].replace(":", "")
        if int(digits[:2]) > 23 or int(digits[2:]) > 59:
            return None
        sign = -1 if off[0] == "-" else 1
        return moment.replace(tzinfo=timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:])))
                              ).astimezone(zone)
    except (ValueError, OverflowError):                 # not a real day, or moved outside the years 1 to 9999
        return None


def _time_text(moment):
    """A time as both calculators spell it: its wall clock and offset, «Z» at offset 0, milliseconds when not 0."""
    text = "%04d-%02d-%02dT%02d:%02d:%02d" % (moment.year, moment.month, moment.day, moment.hour, moment.minute,
                                               moment.second) + (".%03d" % (moment.microsecond // 1000)
                                                                 if moment.microsecond else "")
    minutes = int(moment.utcoffset().total_seconds() // 60)                 # an old local mean time's seconds dropped
    return text + ("Z" if minutes == 0 else "%s%02d:%02d" % ("-" if minutes < 0 else "+", abs(minutes) // 60,
                                                            abs(minutes) % 60))


def _week(moment):
    """The week of the year, weeks starting on Sunday and the first holding January 1 - Spotfire's «first week of year
    is dependent on the regional settings», read for the owner's (Korean) ones; 1 to 54."""
    jan1 = moment.replace(month=1, day=1)
    return (moment.timetuple().tm_yday - 1 + (jan1.weekday() + 1) % 7) // 7 + 1


PART_OF = {"Year": lambda t: t.year, "Quarter": lambda t: (t.month - 1) // 3 + 1, "Month": lambda t: t.month,
           "Day": lambda t: t.day, "Hour": lambda t: t.hour, "Week": _week,
           "DayOfWeek": lambda t: (t.weekday() + 1) % 7}


def _dated(f):
    """A function of one time: the time on the zone's wall clock, else empty - a value that is not a time is counted
    (the run's not_time), an empty one is not."""
    def one(v, ctx):
        moment = _wall(v, ctx.zone())
        if moment is None:
            if not is_blank(v):
                ctx.not_time.add(id(ctx.row))
            return None
        return f(moment)
    return {"kind": "row", "arity": 1, "args": ["value"], "fn": one, "zoned": True}


def _date_part(part, v, ctx):
    name = PARTS.get(str(part).strip().lower()) if isinstance(part, str) else None
    if name is None:
        said = str(part).strip().lower() if isinstance(part, str) else part
        raise ExpressionError(say("datepart_other", part=said) if said in OTHER_PARTS
                              else say("datepart_name", got=_text(part)))
    return _dated(PART_OF[name])["fn"](v, ctx)


# ── ParseDateTime (owner 11-07 «2»: Spotfire's .NET spelling) ─────────────────────────────────────────────────────────
#: The tokens it reads live with the time reader (`utils.time_format.NET_TOKENS`) - the ledger's validator names a
#: ParseDateTime format from the same table. yy is .NET's window (TwoDigitYearMax 2029): 00-29 is 20xx, 30-99 is 19xx.
NET_UNITS = {"y": "year", "M": "month", "d": "day", "H": "hour", "m": "minute", "s": "second", "f": "fraction"}


@lru_cache(maxsize=64)
def _net_format(fmt):
    """`fmt` in .NET's spelling -> (the strptime format, the text's exact shape), or refused naming what it reads."""
    if "%" in fmt:
        raise ExpressionError(say("net_spelling", fmt=fmt))
    strp, shape, units, i = [], [], set(), 0
    while i < len(fmt):
        ch = fmt[i]
        if ch in "'\"":
            end = fmt.find(ch, i + 1)
            if end < 0:
                raise ExpressionError(say("net_quote", at=i + 1, fmt=fmt))
            literal, i = fmt[i + 1:end], end + 1
        elif ch == "\\" and i + 1 < len(fmt):
            literal, i = fmt[i + 1], i + 2
        elif ch in NET_LETTERS:
            j = i
            while j < len(fmt) and fmt[j] == ch:
                j += 1
            token, i = fmt[i:j], j
            if token not in NET_TOKENS:
                raise ExpressionError(say("net_reads", token=token))
            if ch in units:
                raise ExpressionError(say("net_again", token=token, unit=NET_UNITS[ch], fmt=fmt))
            units.add(ch)
            strp.append(NET_TOKENS[token][1])
            shape.append("[0-9]{%d}" % NET_TOKENS[token][0])
            continue
        else:
            literal, i = ch, i + 1
        strp.append(literal)
        shape.append(re.escape(literal))
    if not {"y", "M", "d"} <= units:
        raise ExpressionError(say("net_needs", fmt=fmt))
    return "".join(strp), re.compile("".join(shape))


def _net_format_given(args):
    """ParseDateTime's format is read with the expression: a text in quotes, in the closed set."""
    if args[1]["t"] != "lit" or not isinstance(args[1]["v"], str):
        raise ExpressionError(say("net_quoted"))
    _net_format(args[1]["v"])


def _parse_date_time(v, fmt, ctx):
    """`v` read by `fmt` on the zone's wall clock, as DateTime spells a time - else empty: a text that is not that
    shape or not a real time is counted (the run's not_time), an empty one is not."""
    if is_blank(v):
        return None
    strp, shape = _net_format(fmt)
    moment = None
    if isinstance(v, str) and shape.fullmatch(v):
        from utils import time_format

        moment = time_format.parse_occurred_at(v, strp, ctx.zone().key)
    if moment is None:
        ctx.not_time.add(id(ctx.row))
        return None
    if "%y" in strp and 2030 <= moment.year <= 2068:     # strptime's window turns at 69, .NET's at 30
        moment = moment.replace(year=moment.year - 100)
    return _time_text(moment)


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
    return {"kind": "fold", "fn": fn, "args": ["column"], **more}


def _row(arity, fn, args):
    def safe(*args):
        try:
            return fn(*args)
        except (OverflowError, ZeroDivisionError, ValueError):
            return None                         # JavaScript's Infinity or NaN - an empty answer
    return {"kind": "row", "arity": arity, "args": args, "fn": safe}


def _num1(f):
    def one(a):
        x = number_of(a)
        return None if x is None else f(x)
    return _row(1, one, ["value"])


def _num2(f, args):
    def two(a, b):
        x, y = number_of(a), number_of(b)
        return None if x is None or y is None else f(x, y)
    return _row(2, two, args)


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

# ── text (owner 11-09 «ㄴ»: Spotfire's Text functions) ─────────────────────────────────────────────────────────────────
#: What a fold of texts writes between them - UniqueConcatenate and a one-column Concatenate (lead 11-09 ②).
JOINER = ", "


def _whole(v):
    """A count's integer part (Text «Left»: 3.99 is 3), else None."""
    x = number_of(v)
    return None if x is None else math.trunc(x)


def _texts(f):
    """A row function of texts: an empty argument is an empty answer. A text of spaces in quotes is a text - a
    row's empty value is None already (`_one_of`)."""
    def one(*vs):
        return None if any(v is None for v in vs) else f(*vs)
    return one


def _left(s, n):
    k, s = _whole(n), _text(s)
    if k is None:
        return None
    return s[:k] if k >= 0 else s[:max(len(s) + k, 0)]       # a negative count takes that many off the right


def _right(s, n):
    k, s = _whole(n), _text(s)
    if k is None:
        return None
    return s[max(len(s) - k, 0):] if k >= 0 else s[min(-k, len(s)):]


def _mid(s, start, length):
    st, ln, s = _whole(start), _whole(length), _text(s)
    if st is None or ln is None or st < 1 or ln < 0:
        return None                             # Text «Mid»: a start below 1 or a negative length is an error
    return s[st - 1:st - 1 + ln]


def _find(needle, within, nth=1):
    if needle is None or within is None or nth is None:
        return None
    k, a, b = _whole(nth), _text(needle), _text(within)
    if k is None:
        return None
    if a == "" or k < 1 or k > len(b):
        return 0
    at = -1
    for _ in range(k):                          # the k-th, each looked for one past the last
        at = b.find(a, at + 1)
        if at < 0:
            return 0
    return at + 1


def _repeat(s, n):
    k = _whole(n)
    return None if k is None or k < 0 else _text(s) * k


def _split(s, sep, n):
    k = _whole(n)
    if k is None or k == 0 or _text(sep) == "":
        return None
    parts = _text(s).split(_text(sep))
    if abs(k) > len(parts):
        return None
    return parts[k - 1] if k > 0 else parts[k]   # a negative count from the end


def _substitute(s, old, new):
    if s is None:
        return None
    s = _text(s)
    if old is None or _text(old) == "":
        return s
    return s.replace(_text(old), "" if new is None else _text(new))


def _joined(items, _params=None):
    return {"value": JOINER.join(_text(it["value"]) for it in items) if items else None}


def _concatenated(values):
    """Concatenate's arguments in one row: empty ones left out (Text «Concatenate»: null + "Ape" is "Ape")."""
    kept = [_text(v) for v in values if v is not None]
    return "".join(kept) if kept else None


# ── patterns (RXExtract · RXReplace · ~=): only what Python's re, JavaScript's RegExp and .NET read alike ────────────
# A pattern is read once into the one text both calculators compile: classes spelled out (\d is [0-9], ASCII as
# JavaScript's), «.» not a newline, «$» the end or before a last newline (.NET's and Python's) - anything else is
# refused by name. task/SPOTFIRE_FUNCTIONS.md «Patterns» is the table of what differs from .NET.
WORDISH = "[A-Za-z0-9_]"
_OUTSIDE = {"d": "[0-9]", "D": "[^0-9]", "w": WORDISH, "W": "[^A-Za-z0-9_]", "s": "[\\t\\n\\v\\f\\r ]",
            "S": "[^\\t\\n\\v\\f\\r ]", "t": "\\t", "n": "\\n", "r": "\\r", "f": "\\f", "v": "\\v",
            "b": "(?:(?<=%s)(?!%s)|(?<!%s)(?=%s))" % ((WORDISH,) * 4),
            "B": "(?:(?<=%s)(?=%s)|(?<!%s)(?!%s))" % ((WORDISH,) * 4)}
_INSIDE = {"d": "0-9", "w": "A-Za-z0-9_", "s": "\\t\\n\\v\\f\\r ", "t": "\\t", "n": "\\n", "r": "\\r", "f": "\\f",
           "v": "\\v"}
_COUNT = re.compile(r"\{[0-9]+(,[0-9]*)?\}")
_GROUP_HEADS = ("(?:", "(?=", "(?!")


def _lit(ch):
    """One character as itself in both engines' pattern grammar."""
    return ch if ch.isascii() and ch.isalnum() else "\\u%04X" % ord(ch) if ord(ch) < 0x10000 else ch


def _translated(name, pattern, dotall):
    """`pattern` -> (the text both compile, its group count), or refused naming the part."""
    def part(k):
        raise ExpressionError(say("pattern_part", name=name, part=k))

    def bad():
        raise ExpressionError(say("pattern_bad", name=name, pattern=pattern))

    def item(i):                                # one member of a [ ] -> (its text, one character?, the index after)
        ch = pattern[i]
        if ch != "\\":
            return _lit(ch), True, i + 1
        if i + 1 >= len(pattern):
            bad()
        e = pattern[i + 1]
        if e in _INSIDE:
            return _INSIDE[e], e not in "dws", i + 2
        if not (e.isascii() and e.isalnum()):
            return _lit(e), True, i + 2
        part("\\" + e)

    out, i, groups, opened, repeat = [], 0, 0, [], False
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            if i + 1 >= len(pattern):
                bad()
            e = pattern[i + 1]
            if e in _OUTSIDE:
                out.append(_OUTSIDE[e])
                repeat = e not in "bB"
            elif not (e.isascii() and e.isalnum()):
                out.append(_lit(e))
                repeat = True
            else:
                part("\\" + e)
            i += 2
        elif ch == "[":
            body, i = ["["], i + 1
            if pattern.startswith("^", i):
                body.append("^")
                i += 1
            first = True
            while True:
                if i >= len(pattern):
                    bad()
                if pattern[i] == "]" and not first:
                    break
                if pattern.startswith("-[", i):
                    part("-[")                  # .NET's class subtraction
                first = False
                text, single, i = item(i)
                if pattern.startswith("-", i) and i + 1 < len(pattern) and pattern[i + 1] != "]":
                    if not single or pattern[i + 1] == "[":
                        part(pattern[i:i + 2] if single else "-")
                    high, high_single, i = item(i + 1)
                    if not high_single:
                        part("-")
                    text = text + "-" + high
                body.append(text)
            out.append("".join(body) + "]")
            i += 1
            repeat = True
        elif ch == "(":
            head = next((h for h in _GROUP_HEADS if pattern.startswith(h, i)), None)
            if head is None and pattern.startswith("(?", i):
                part(pattern[i:i + 3])
            if head is None:
                head = "("
                groups += 1
            out.append(head)
            opened.append(head)
            i += len(head)
            repeat = False
        elif ch == ")":
            if not opened:
                bad()
            repeat = opened.pop() in ("(", "(?:")
            out.append(")")
            i += 1
        elif ch in "*+?" or (ch == "{" and _COUNT.match(pattern, i)):
            q = _COUNT.match(pattern, i).group(0) if ch == "{" else ch
            if not repeat:
                part(q)                         # nothing before it to repeat
            i += len(q)
            if pattern.startswith("+", i):
                part(q + "+")                   # .NET has no possessive
            if pattern.startswith("?", i):
                q += "?"
                i += 1
            out.append(q)
            repeat = False
        else:
            out.append({".": "[\\s\\S]" if dotall else "[^\\n]", "^": "^", "$": "(?=\\n?(?![\\s\\S]))",
                        "|": "|"}.get(ch) or _lit(ch))
            repeat = ch not in "^$|"
            i += 1
    if opened:
        bad()
    return "".join(out), groups


@lru_cache(maxsize=256)
def _rx(name, pattern, options):
    """A pattern with its options (g all · i no case · s «.» takes a newline too) -> (compiled, group count)."""
    if any(ch not in "gis" for ch in options):
        raise ExpressionError(say("options", name=name, got=options))
    text, groups = _translated(name, pattern, "s" in options)
    try:
        return re.compile(text, re.IGNORECASE if "i" in options else 0), groups
    except re.error:
        raise ExpressionError(say("pattern_bad", name=name, pattern=pattern)) from None


def _replacement(name, text, groups):
    """`$1` `${1}` `$0` (the match) `$$` -> parts: texts and group numbers; a number past the groups is its own text;
    .NET's other $ forms are refused by name."""
    parts, i = [], 0
    while i < len(text):
        m = re.match(r"\$([0-9]+)|\$\{([0-9]+)\}", text[i:])
        if m:
            k = int(m.group(1) or m.group(2))
            parts.append(k if k <= groups else m.group(0))
            i += len(m.group(0))
        elif text.startswith("$$", i):
            parts.append("$")
            i += 2
        elif text[i] == "$" and text[i + 1:i + 2] in ("&", "`", "'", "+", "_", "{"):
            raise ExpressionError(say("replacement_part", name=name, part=text[i:i + 2]))
        else:
            parts.append(text[i])
            i += 1
    return tuple(parts)


def _matches(compiled, s):
    """Each match left to right, an empty one stepped past by one character - the same walk as the screen's."""
    at = 0
    while at <= len(s):
        m = compiled.search(s, at)
        if not m:
            return
        yield m
        at = m.end() if m.end() > m.start() else m.end() + 1


def _quoted(name, args, at, what):
    a = args[at]
    if a["t"] != "lit" or not isinstance(a["v"], str):
        raise ExpressionError(say("quoted", name=name, what=what))
    return a["v"]


def _rx_given(name, replacement=False, options=False):
    """The pattern (and a replacement · options) are read with the expression: texts in quotes, read once."""
    def check(args):
        pattern = _quoted(name, args, 1, "pattern")
        said = _quoted(name, args, 2, "replacement") if replacement else None
        flags = _quoted(name, args, 3, "options") if options else ""
        _, groups = _rx(name, pattern, flags)
        if said is not None:
            _replacement(name, said, groups)
    return check


def _rx_extract(s, pattern, nth):
    k = _whole(nth)
    if k is None or k < 1:
        return None
    for m in _matches(_rx("RXExtract", pattern, "")[0], _text(s)):
        k -= 1
        if k == 0:
            return m.group(0)
    return None


def _rx_replace(s, pattern, replacement, options):
    compiled, groups = _rx("RXReplace", pattern, options)
    parts, s, out, last = _replacement("RXReplace", replacement, groups), _text(s), [], 0
    for m in _matches(compiled, s):
        out += [s[last:m.start()]] + [p if isinstance(p, str) else m.group(p) or "" for p in parts]
        last = m.end()
        if "g" not in options:
            break
    return "".join(out) + s[last:]


def _text_row(arity, f, args, **more):
    return {**_row(arity, _texts(f), args), **more}


#: `args`: each argument's name, as the formula's signature line says it (lead 11-07) - a fold's column «...» more
#: (rowwise) or none at all (none) is read from those keys, not written here: the count has one answer.
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
    "UniqueConcatenate": _fold(lambda items, _p=None: {"value": JOINER.join(
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
    "Percentile": _fold(_numeric(lambda xs, p: None if p[0] is None else _pct(xs, p[0] / 100)), params=1,
                        args=["column", "percent"]),
    "Percent": _fold(_numeric(lambda xs, p: None if p[0] is None
                              else min(xs) + (p[0] / 100) * (max(xs) - min(xs))), params=1, args=["column", "percent"]),
    "LIF": _fold(_numeric(lambda xs, _p: _q1(xs) - 1.5 * _iqr(xs))),
    "UIF": _fold(_numeric(lambda xs, _p: _q3(xs) + 1.5 * _iqr(xs))),
    "LOF": _fold(_numeric(lambda xs, _p: _q1(xs) - 3 * _iqr(xs))),
    "UOF": _fold(_numeric(lambda xs, _p: _q3(xs) + 3 * _iqr(xs))),
    "LAV": _fold(_numeric(lambda xs, _p: _lav(xs))),
    "UAV": _fold(_numeric(lambda xs, _p: _uav(xs))),
    "Outliers": _fold(_numeric(lambda xs, _p: _outliers(xs))),
    "PctOutliers": _fold(_numeric(lambda xs, _p: 100 * _outliers(xs) / len(xs))),
    "GeometricMean": _fold(_numeric(_geometric)),
    "TrimmedMean": _fold(_numeric(_trimmed), params=1, args=["column", "percent"]),
    "NthLargest": _fold(_numeric(_nth(True)), params=1, args=["column", "n"]),
    "NthSmallest": _fold(_numeric(_nth(False)), params=1, args=["column", "n"]),
    "L95": _fold(_numeric(lambda xs, _p: None if len(xs) < 2 else _mean(xs) - T95 * _sd(xs) / math.sqrt(len(xs)))),
    "U95": _fold(_numeric(lambda xs, _p: None if len(xs) < 2 else _mean(xs) + T95 * _sd(xs) / math.sqrt(len(xs)))),
    # two columns: a row with either side empty is left out (lead 10-13)
    "WeightedAverage": _fold(_weighted, pair=True, args=["weight", "value"]),
    "Covariance": _fold(_covariance, pair=True, args=["x", "y"]),
    "ValueForMax": _fold(_value_for(max, False), pair=True, args=["by", "value"]),
    "ValueForMin": _fold(_value_for(min, False), pair=True, args=["by", "value"]),
    "LastValueForMax": _fold(_value_for(max, True), pair=True, args=["by", "value"]),
    "LastValueForMin": _fold(_value_for(min, True), pair=True, args=["by", "value"]),
    # values
    "Abs": _num1(abs),
    "Ceiling": _num1(math.ceil),
    "Floor": _num1(math.floor),
    "Round": _num2(_round, ["value", "digits"]),
    "Sqrt": _num1(lambda x: None if x < 0 else math.sqrt(x)),
    "Exp": _num1(math.exp),
    "Ln": _num1(lambda x: None if x <= 0 else math.log(x)),
    "Log10": _num1(lambda x: None if x <= 0 else math.log10(x)),
    "Log": _num2(lambda x, b: None if x <= 0 or b <= 0 or b == 1 else math.log(x) / math.log(b), ["value", "base"]),
    "Mod": _num2(lambda a, b: None if b == 0 else a - b * math.floor(a / b), ["dividend", "divisor"]),
    "Power": _num2(math.pow, ["base", "exponent"]),
    "PI": _row(0, lambda: math.pi, []),
    "Sin": _num1(math.sin),
    "Cos": _num1(math.cos),
    "Tan": _num1(math.tan),
    "ASin": _num1(lambda x: None if abs(x) > 1 else math.asin(x)),
    "ACos": _num1(lambda x: None if abs(x) > 1 else math.acos(x)),
    "ATan": _num1(math.atan),
    "ATan2": _num2(math.atan2, ["y", "x"]),
    "If": {"kind": "if", "args": ["condition", "then", "else"]},
    # dates (lead fe2ba4b1f) - on the zone's wall clock
    "Date": _dated(lambda t: _time_text(t.replace(hour=0, minute=0, second=0, microsecond=0))),
    "DateTime": _dated(_time_text),
    **{name: _dated(f) for name, f in PART_OF.items()},
    "DatePart": {"kind": "row", "arity": 2, "args": ["part", "value"], "fn": _date_part, "zoned": True},
    "ParseDateTime": {"kind": "row", "arity": 2, "args": ["text", "format"], "fn": _parse_date_time, "zoned": True,
                      "check": _net_format_given},
    # text (owner 11-09 «ㄴ») - a number or a boolean read as its text; counts by their integer part
    "Concatenate": _fold(_joined, rowwise=True, within=_concatenated, args=["text"]),
    "Find": {**_row(3, _find, ["text", "within", "nth"]), "least": 2},
    "Left": _text_row(2, _left, ["text", "count"]),
    "Len": _text_row(1, lambda s: len(_text(s)), ["text"]),
    "Lower": _text_row(1, lambda s: _text(s).lower(), ["text"]),
    "Mid": _text_row(3, _mid, ["text", "start", "count"]),
    "Repeat": _text_row(2, _repeat, ["text", "count"]),
    "Right": _text_row(2, _right, ["text", "count"]),
    "RXExtract": _text_row(3, _rx_extract, ["text", "pattern", "nth"], check=_rx_given("RXExtract")),
    "RXReplace": _text_row(4, _rx_replace, ["text", "pattern", "replacement", "options"],
                           check=_rx_given("RXReplace", replacement=True, options=True)),
    "Split": _text_row(3, _split, ["text", "separator", "nth"]),
    "Substitute": _row(3, _substitute, ["text", "old", "new"]),
    "Substring": _text_row(3, _mid, ["text", "start", "count"]),
    "Trim": _text_row(1, lambda s: _text(s).strip(), ["text"]),
    "Upper": _text_row(1, lambda s: _text(s).upper(), ["text"]),
}
_BY_NAME = {name.lower(): name for name in FUNCTIONS}
#: The screen's alone - the page's markings.
SCREEN_ONLY = {"Marked": {"kind": "mark"}}
_SCREEN_BY_NAME = {name.lower(): name for name in SCREEN_ONLY}
#: Names not built, refused by name with the sentence each says: task/SPOTFIRE_FUNCTIONS.md's not in this edition (the
#: vectors' out_of_edition), and NameEncode · NameDecode, which no page gives a result for (lead 11-09 ③).
NOT_YET = {**{name: "not_in_edition" for name in ("normdist", "norminv", "tdist", "tinv", "chidist", "chiinv", "fdist",
                                                  "finv", "lag", "lead", "rand", "randbetween", "reach")},
           "nameencode": "unsettled", "namedecode": "unsettled"}
#: A sheet's cell (A1) or range (B1:B9) - the screen's Sheet (lead 10-14, owner 3b97fcfb9).
CELL = re.compile(r"^[A-Za-z]+[0-9]+$")
#: A name holding one of these is a way from the row ([a.b~.x]) - not read on the server yet (lead 5667ea0fe).
WAY_MARKS = (".", "~")

# ── reading the text ────────────────────────────────────────────────────────────────────────────────────────────────
KEYWORDS = {"and", "or", "xor", "not", "case", "when", "then", "else", "end", "is", "null", "true", "false", "distinct"}
OPS = ["<=>", "<=", ">=", "<>", "!=", "~=", "<", ">", "=", "+", "-", "*", "/", "%", "^", "&", "(", ")", ",", ":"]
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
        if ch in "\"'":                          # \\ \" \' are the character (lead 11-09 ①); any other \x is itself
            j, said = i + 1, []
            while j < len(text) and text[j] != ch:
                if text[j] == "\\" and text[j + 1:j + 2] in ("\\", "\"", "'"):
                    j += 1
                said.append(text[j])
                j += 1
            if j >= len(text):
                raise ExpressionError(say("text_open", at=at + 1))
            out.append(("str", "".join(said), at))
            i = j + 1
            continue
        if ch == "[":                            # «]]» is a «]» inside a name (Spotfire's escape)
            j, name = i + 1, ""
            while j < len(text) and not (text[j] == "]" and text[j + 1:j + 2] != "]"):
                name += text[j]
                j += 2 if text[j] == "]" else 1
            if j >= len(text):
                raise ExpressionError(say("name_open", at=at + 1))
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
        raise ExpressionError(say("stray", ch=ch, at=at + 1))
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
        return say("at_end") if tk()[0] == "end" else say("at", at=tk()[2] + 1)

    def need(test, what):
        if not test():
            raise ExpressionError(say("expected", what=what, where=where()))
        p[0] += 1

    def snippet():
        return text[tk()[2]:tk()[2] + 12]

    # lowest first: or · xor · and · not · = <> <=> ~= · < > <= >= · Is Null · & · + - · * / % · unary - + · ^
    # (lead 10-13; & and ~= Ops · Prec, owner 11-09)
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
        while any(op(o) for o in ("=", "<>", "!=", "<=>", "~=")):
            o = tk()[1]
            p[0] += 1
            if o == "~=":
                pattern = relational()
                if pattern["t"] != "lit" or not isinstance(pattern["v"], str):
                    raise ExpressionError(say("quoted", name="«~=»", what="pattern"))
                _rx("«~=»", pattern["v"], "")
                a = {"t": "match", "a": a, "pattern": pattern["v"]}
                continue
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
        a = concat()
        if not kw("is"):
            return a
        p[0] += 1
        negate = kw("not")
        if negate:
            p[0] += 1
        need(lambda: kw("null"), say("want_null"))
        return {"t": "isnull", "a": a, "negate": negate}

    def concat():
        a = additive()
        while op("&"):
            p[0] += 1
            a = {"t": "concat", "a": a, "b": additive()}
        return a

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
                raise ExpressionError(say("screen_way", name=v))
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
            need(lambda: op(")"), say("want_close"))
            return e
        if kind == "id" and CELL.match(v) and not (ts[p[0] + 1][0] == "op" and ts[p[0] + 1][1] == "("):
            raise ExpressionError(say("screen_sheet", name=v))
        if kind == "id":
            return call()
        raise ExpressionError(say("ends_soon") if kind == "end" else say("unexpected", snippet=snippet(), where=where()))

    def call():
        word = tk()[1]
        p[0] += 1
        lw = word.lower()
        if lw in _SCREEN_BY_NAME:
            raise ExpressionError(say("screen_marks", name=_SCREEN_BY_NAME[lw]))
        name = _BY_NAME.get(lw)
        if not name:
            raise ExpressionError(say(NOT_YET.get(lw, "screen_constructor"), name=word))
        need(lambda: op("("), say("want_open_after", name=name))
        distinct = kw("distinct")
        if distinct:
            p[0] += 1
        args = []
        if not op(")"):
            args.append(or_())
            while op(","):
                p[0] += 1
                args.append(or_())
        need(lambda: op(")"), say("want_close_of", name=name))
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
            need(lambda: kw("then"), say("want_then"))
            whens.append({"when": when, "then": or_()})
        if not whens:
            raise ExpressionError(say("expected", what=say("want_when"), where=where()))
        otherwise = None
        if kw("else"):
            p[0] += 1
            otherwise = or_()
        need(lambda: kw("end"), say("want_end"))
        return {"t": "case", "subject": subject, "whens": whens, "otherwise": otherwise}

    tree = or_()
    if tk()[0] != "end":
        raise ExpressionError(say("unexpected", snippet=snippet(), where=where()))
    return tree


def _arity(node):
    fn, n, name = node["fn"], len(node["args"]), node["name"]
    kind = fn["kind"]
    if kind == "if":
        fits, want = n == 3, "3"
    elif kind == "row":
        least = fn.get("least", fn["arity"])
        fits, want = least <= n <= fn["arity"], " or ".join(str(k) for k in range(least, fn["arity"] + 1))
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
        raise ExpressionError(say("takes", name=name, want=want, s="" if want == "1" else "s", n=n))
    if fn.get("check"):
        fn["check"](node["args"])
    if node["distinct"] and (kind != "fold" or fn.get("pair") or (fn.get("rowwise") and n > 1)):
        raise ExpressionError(say("distinct", name=name))


def _children(node):
    out = [node.get(k) for k in ("a", "b", "subject", "otherwise")] + list(node.get("args") or [])
    for w in node.get("whens") or []:
        out += [w["when"], w["then"]]
    return [c for c in out if c]


def _row_level(node):
    """Does `node` read a row's value outside any fold - then the answer is one per row."""
    if node["t"] == "ref":
        return True
    if node["t"] == "call" and node["fn"]["kind"] == "fold":       # several arguments fold within the row
        return bool(node["fn"].get("rowwise")) and len(node["args"]) > 1 and any(map(_row_level, node["args"]))
    return any(_row_level(c) for c in _children(node))


def _names_of(node, out, t="ref", key="name"):
    if node["t"] == t:
        out.append(node[key])
    for c in _children(node):
        _names_of(c, out, t, key)
    return out


def compile(text):                              # noqa: A001 - the screen's name for the same step
    """A text read once: {"ok": True, "tree", "per_row", "names" (the columns it reads), "calls" (the functions it
    calls)} or {"ok": False, "why"}."""
    try:
        tree = _parse(str(text or ""))
    except ExpressionError as exc:
        return {"ok": False, "why": str(exc)}
    return {"ok": True, "tree": tree, "per_row": _row_level(tree),
            "names": list(dict.fromkeys(_names_of(tree, []))), "calls": list(dict.fromkeys(_names_of(tree, [], "call")))}


# ── answering ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _time_of_row(row):
    at = row.get("$at") if isinstance(row, dict) else None
    if _is_num(at):
        return at
    moment = _instant(at) if isinstance(at, str) else None
    return moment.timestamp() * 1000 if moment else None


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
    def __init__(self, rows, types, row=None, memo=None, not_number=None, not_time=None, zones=None):
        self.rows, self.types, self.row = rows, types, row
        self.memo = {} if memo is None else memo
        self.not_number = set() if not_number is None else not_number
        self.not_time = set() if not_time is None else not_time
        self.zones = zones                       # [zone or None] - one per run, the setting read once when asked

    def at(self, row=None, rows=None):
        return _Ctx(self.rows if rows is None else rows, self.types, row, self.memo, self.not_number, self.not_time,
                    self.zones)

    def zone(self):
        if self.zones[0] is None:
            self.zones[0] = time_zone()
        return self.zones[0]


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
            raise ExpressionError(say("row_value", name=node["name"]))
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
    if t == "concat":
        a, b = _value(node["a"], ctx), _value(node["b"], ctx)
        return None if a is None or b is None else _text(a) + _text(b)
    if t == "match":
        a = _value(node["a"], ctx)
        return None if a is None else _rx("«~=»", node["pattern"], "")[0].search(_text(a)) is not None
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
        return _finite(node["fn"]["fn"](*[_value(a, ctx) for a in node["args"]],
                                        *([ctx] if node["fn"].get("zoned") else [])))
    return _finite(_fold_value(node, ctx))


def _fold_value(node, ctx):
    fn, args = node["fn"], node["args"]
    if fn.get("none") and not args:
        return len(ctx.rows)                    # Count(): the rows
    if fn.get("rowwise") and len(args) > 1 and fn.get("within"):
        return fn["within"]([_value(a, ctx) for a in args])
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


def run(compiled, rows, types=None, zone=None):
    """Answer a compiled expression over rows: {"value"} once, or {"values"} one per row when it reads a row's value
    outside a fold - each with "not_number" (the rows an operator met a text that is not a number on) and "not_time"
    (the rows a date function met a value that is not a time on); or {"several": name} · {"why": sentence}. `zone`: an
    IANA name the dates are cut in, else the setting (`time_zone`)."""
    if not compiled["ok"]:
        return {"why": compiled["why"]}
    zones = [None]
    if zone is not None:
        from zoneinfo import ZoneInfo

        try:
            zones[0] = ZoneInfo(str(zone))
        except (ValueError, KeyError, OSError):
            return {"why": say("not_zone", zone=zone)}
    ctx = _Ctx(list(rows or []), types or {}, zones=zones)
    try:
        if not compiled["per_row"]:
            value = _finite(_value(compiled["tree"], ctx))
            return {"value": value, "not_number": len(ctx.not_number), "not_time": len(ctx.not_time)}
        values = [_finite(_value(compiled["tree"], ctx.at(row=r))) for r in ctx.rows]
        return {"values": values, "not_number": len(ctx.not_number), "not_time": len(ctx.not_time)}
    except SeveralValues as exc:
        return {"several": str(exc)}
    except ExpressionError as exc:
        return {"why": str(exc)}


# ── the catalogue: what the screen reads of this table (owner 11-09 «ㄴ») ──────────────────────────────────────────────
#: A function's grammar - what the catalogue carries. The rest (fn · zoned · check · within) is how a calculator answers.
GRAMMAR = ("kind", "args", "arity", "least", "none", "rowwise", "params", "pair")
CATALOGUE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "contracts", "expression",
                              "catalogue.json")


def _says(fn):
    """The signature line's words (lead 11-07): a column that may be left out and an argument after `least` in [ ], a
    fold of more columns ends in «...»."""
    args = fn.get("args", [])
    if fn.get("none"):
        return ["[%s]" % a for a in args]
    if fn.get("rowwise"):
        return args + ["..."]
    least = fn.get("least", len(args))
    return args[:least] + ["[%s]" % a for a in args[least:]]


def catalogue():
    return {
        "$comment": ["GENERATED from server/expression.py (python server/expression.py) - edit the table there.",
                     "The function table's grammar, the names refused and every refusal sentence: the screen's",
                     "calculator and formula inputs import this file (owner 11-09). A test holds it to the table."],
        "joiner": JOINER,
        "functions": {name: {**{k: fn[k] for k in GRAMMAR if k in fn}, "says": _says(fn)} for name, fn in FUNCTIONS.items()},
        "screen_only": SCREEN_ONLY,
        "not_yet": NOT_YET,
        "sentences": SENTENCES,
    }


def catalogue_text():
    """The file's text: one line an entry, so a change to the table is a change to its line."""
    def one(v):
        return json.dumps(v, ensure_ascii=False)

    def section(v):
        if not isinstance(v, dict):
            return one(v)
        return "{\n" + ",\n".join("  %s: %s" % (one(k), one(x)) for k, x in v.items()) + "\n }"
    return "{\n" + ",\n".join(" %s: %s" % (one(k), section(v)) for k, v in catalogue().items()) + "\n}\n"


if __name__ == "__main__":
    with open(CATALOGUE_PATH, "w", encoding="utf-8", newline="\n") as out:
        out.write(catalogue_text())
    print("wrote", os.path.normpath(CATALOGUE_PATH))
