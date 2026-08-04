"""Command-line parsing for ``run_decoupled_app.py`` - the refusal half.

THE FAILURE THIS REPLACES
-------------------------
Every flag used to be a membership test against ``sys.argv``::

    server_only = "--no-client" in sys.argv or "--server-only" in sys.argv
    if "--reload" in sys.argv: ...
    if "--preflight-only" in sys.argv: ...

An argument the launcher did not recognise was therefore not an error - it was
nothing. Measured on the real launcher before this module existed, with
``subprocess.Popen`` neutered so nothing could actually start::

    --server_only  -> planned children: Backend | Watcher | Graph | Chain |
                      Scheduler | Desktop Client UI       (six - full stack)
    --server-only  -> planned children: Backend | Watcher | Graph | Chain |
                      Scheduler                            (five)

That one-character difference is the whole incident. The operator asked for
server-only, got the full stack including the desktop window, and - because a
stack was already running - the two port binders could not bind and went into
the correlated-backoff loop. From the console it read as "the socket is dead"
plus "why is the desktop client running". ``--help`` did not exist either, so
the correct spelling was not discoverable short of reading the source.

THE TWO PROPERTIES THAT WERE MISSING
------------------------------------
1. An unrecognised argument is a REFUSAL, not a no-op. Non-zero exit, the
   argument named, and the closest valid flag suggested - because the failure
   mode here is a near-miss spelling, not an invented one. Nothing starts.
2. ``--help`` exists and lists every flag.

WHAT IS DELIBERATELY UNCHANGED
------------------------------
Every working spelling keeps working, ``--no-client`` and ``--server-only``
included as synonyms. This is a launcher an operator has muscle memory for;
changing what the working spellings do would be a worse defect than the one
being fixed. Order still does not matter, and flags may be combined as before.

A near-miss is refused, never silently accepted. ``--server_only`` does not
become ``--server-only``: a launcher that guesses is a launcher that will one
day guess wrong on the flag that decides whether a desktop window opens.

WHY A SEPARATE MODULE, AND WHY NOT argparse
-------------------------------------------
Separate module: importing ``run_decoupled_app.py`` opens the LIVE
``server/launcher.log`` and resets the root logger (see the comment in
``tests/test_duplicate_launcher.py``). Parsing lives here so the suite can call
it as a plain function with no side effects at all.

Not argparse: on Python 3.12 it prints ``unrecognized arguments: --server_only``
in English to stderr with no suggestion (``suggest_on_error`` is 3.14), and its
``allow_abbrev`` default would quietly accept ``--server`` as ``--server-only``
- guessing, which is the one behaviour this module exists to refuse. The output
also has to be Korean-first and cp949-safe, which argparse does not own.
"""
import difflib

#: Exit code for a refused command line. Distinct from the port guard's 1 so a
#: wrapper script can tell "you typed something wrong" from "the ports are busy".
EXIT_BAD_ARGUMENT = 2

#: Every accepted spelling, with the one line ``--help`` prints for it. This
#: tuple is the single source of truth: what is parsed, what is suggested, and
#: what is documented cannot drift apart because they are the same list.
FLAGS = (
    ("--server-only", "데스크톱 클라이언트 없이 서버 프로세스만 기동합니다."),
    ("--no-client", "--server-only 와 같습니다 (기존 철자 유지)."),
    ("--reload", "uvicorn 을 --reload 로 기동합니다 (개발용)."),
    ("--preflight-only", "포트 점검만 하고 아무것도 기동하지 않습니다."),
    ("--help", "이 도움말을 출력하고 종료합니다."),
    ("-h", "--help 와 같습니다."),
)

KNOWN_FLAGS = tuple(name for name, _ in FLAGS)

#: What a near-miss is measured against. ``-h`` is excluded because a two-
#: character flag scores badly against every long typo and would only ever be
#: offered as noise.
_SUGGESTABLE = tuple(f for f in KNOWN_FLAGS if len(f) > 2)

#: difflib's own default. Loose enough for the near-misses that actually happen
#: (``--server_only`` 0.92, ``--serveronly`` 0.96, ``--preflight-onlyy`` 0.97),
#: tight enough that an invented argument gets no suggestion at all rather than
#: a confidently wrong one.
_SUGGESTION_CUTOFF = 0.6

_RULE = "=" * 68


def suggest_flag(argument):
    """The closest valid flag to ``argument``, or None when nothing is close.

    None is a real answer, not a failure: offering ``--reload`` to somebody who
    typed ``--verbose`` wastes the one line the operator is going to read.
    """
    match = difflib.get_close_matches(argument, _SUGGESTABLE, n=1,
                                      cutoff=_SUGGESTION_CUTOFF)
    return match[0] if match else None


def help_lines():
    """``--help`` output, one line per flag. Plain list of strings, no printing."""
    lines = [
        "AssyManager 런처 ― python run_decoupled_app.py [옵션]",
        "AssyManager launcher ― python run_decoupled_app.py [options]",
        "",
    ]
    width = max(len(name) for name in KNOWN_FLAGS)
    for name, description in FLAGS:
        lines.append(f"  {name.ljust(width)}   {description}")
    lines += [
        "",
        " 옵션이 없으면 서버 프로세스 5개와 데스크톱 클라이언트를 모두 기동합니다.",
        " 인자는 순서와 무관하며, 알 수 없는 인자가 하나라도 있으면 기동을 거부합니다.",
    ]
    return lines


def refusal_lines(unknown):
    """The banner an operator sees for a bad command line.

    ``unknown`` is ``[(argument, suggestion_or_None), ...]``. Korean first,
    English second, matching what the port pre-flight guard already prints.

    Every character here must survive cp949: the production console is cp949
    (``run_app.bat`` sets no ``PYTHONIOENCODING``) and one character outside it
    makes the logging handler raise and DROP the line - which would leave an
    operator staring at a silent console during exactly the moment this message
    exists to end. ``―`` (U+2015) encodes; ``—`` (U+2014) does not.
    """
    lines = ["", _RULE,
             " 기동을 중단합니다: 알 수 없는 인자입니다.",
             " REFUSING TO START ― unrecognised argument.", ""]
    for argument, suggestion in unknown:
        lines.append(f"   알 수 없는 인자 / unrecognised: {argument}")
        if suggestion:
            lines.append(f"   이것을 쓰려던 것입니까? / did you mean:  {suggestion}")
        else:
            lines.append("   비슷한 인자를 찾지 못했습니다. / no similar flag found.")
    lines += [
        "",
        " 사용 가능한 인자 / valid arguments:",
        "     python run_decoupled_app.py --help",
        "",
        " (아무것도 기동하지 않았습니다. 기존 프로세스는 그대로 살아 있습니다.)",
        " Nothing was started. Nothing that is already running was touched.",
        _RULE, ""]
    return lines


class LauncherArgs(object):
    """Parsed command line. ``exit_code is None`` means "go ahead and start".

    ``lines`` is what the caller prints when there is an exit code, so the
    decision and the wording are both testable without running a launcher.
    """

    __slots__ = ("server_only", "reload", "preflight_only",
                 "exit_code", "lines", "is_refusal", "unknown")

    def __init__(self, server_only=False, reload=False, preflight_only=False,
                 exit_code=None, lines=(), is_refusal=False, unknown=()):
        self.server_only = server_only
        self.reload = reload
        self.preflight_only = preflight_only
        self.exit_code = exit_code
        self.lines = list(lines)
        self.is_refusal = is_refusal
        self.unknown = list(unknown)

    @property
    def should_start(self):
        return self.exit_code is None


def parse_launcher_args(argv):
    """``argv`` is the argument list WITHOUT the program name -> LauncherArgs.

    Never prints, never exits, never raises. The caller owns those, so a test
    can score the decision without a subprocess.
    """
    server_only = False
    reload_ = False
    preflight_only = False
    wants_help = False
    unknown = []

    for argument in argv:
        if argument in ("--server-only", "--no-client"):
            server_only = True
        elif argument == "--reload":
            reload_ = True
        elif argument == "--preflight-only":
            preflight_only = True
        elif argument in ("--help", "-h"):
            wants_help = True
        else:
            unknown.append((argument, suggest_flag(argument)))

    # Refusal outranks help. An operator who mistyped needs to be told the
    # command did not run; sending them a help page instead answers a question
    # they did not ask and hides the one fact that matters.
    if unknown:
        return LauncherArgs(exit_code=EXIT_BAD_ARGUMENT,
                            lines=refusal_lines(unknown),
                            is_refusal=True, unknown=[a for a, _ in unknown])
    if wants_help:
        return LauncherArgs(exit_code=0, lines=help_lines())
    return LauncherArgs(server_only=server_only, reload=reload_,
                        preflight_only=preflight_only)
