"""A log line the terminal cannot encode must DEGRADE, not die.

THE FAILURE THIS CLOSES
-----------------------
The operator's terminal is cp949. `run_watcher.py` printed a `--- Logging error
---` traceback instead of a deprecation warning naming a workspace config file:
one U+2014 in an otherwise useful sentence destroyed the whole line and replaced
it with noise the operator could not act on.

WHY THE FIX IS NOT "STOP TYPING EM DASHES"
------------------------------------------
U+2014 reaches a console from 72 measured call sites and from every future one
nobody has typed yet, and the same class covers en dash and emoji. The defect is
that the logging chain loses a whole line over one character, so the fix is in
the handler.

WHY THE FIX IS NOT THE HANDLER THAT WAS ALREADY THERE
-----------------------------------------------------
`server/map_alignment.py` carried a `_ConsoleSafeHandler` that wrapped
`super().emit(record)` in `except UnicodeEncodeError`. That branch is
UNREACHABLE - `logging.StreamHandler.emit` catches the error itself and routes it
to `handleError`, so nothing propagates to the caller. Measured before the fix
against a cp949 stream: the stock handler wrote 0 bytes and produced 819
characters of stderr traceback, and that `_ConsoleSafeHandler` wrote 0 bytes and
produced 1590. `test_the_old_shape_does_not_work` pins that, because a fixture
that is already green proves nothing and this one was.

WHAT IS DELIBERATELY NOT DONE
-----------------------------
The stream is not forced to utf-8. utf-8 bytes at a cp949 console would garble
every Korean sentence in the log - one lost line traded for all of them.
Re-encoding with `errors="replace"` loses the one character the terminal cannot
draw and keeps the sentence. The FILE half is opened utf-8 and keeps the
character intact; `test_file_half_keeps_the_character` holds that line.
"""
import io
import os
import sys
import json
import logging
import subprocess

import pytest

SERVER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from utils.logger import ConsoleSafeHandler, make_console_safe  # noqa: E402

EM_DASH_MSG = "legacy workspace config — use paths.py (설정 이전)"


def _emit(handler_factory, text, encoding="cp949"):
    """Push one record through a real handler chain against a real codec.

    Returns (bytes the console received, text logging dumped on stderr). An empty
    first element with a non-empty second is exactly the reported failure.
    """
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding=encoding, errors="strict", newline="")
    handler = handler_factory(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    lg = logging.getLogger("console_safe_probe.%d" % id(handler))
    lg.handlers[:] = [handler]
    lg.propagate = False
    lg.setLevel(logging.INFO)
    captured, real_stderr = io.StringIO(), sys.stderr
    sys.stderr = captured
    try:
        lg.warning(text)
    finally:
        sys.stderr = real_stderr
        lg.handlers[:] = []
    stream.flush()
    return buf.getvalue(), captured.getvalue()


# --------------------------------------------------------------------------
# The defect, asserted before the cure.
# --------------------------------------------------------------------------

def test_stock_handler_loses_the_whole_line():
    """The reported failure, reproduced: nothing printed, a traceback instead."""
    written, noise = _emit(logging.StreamHandler, EM_DASH_MSG)
    assert written == b"", "cp949 is supposed to be unable to encode U+2014"
    assert "--- Logging error ---" in noise
    assert "UnicodeEncodeError" in noise


def test_the_old_shape_does_not_work():
    """`except UnicodeEncodeError` around `super().emit()` never fires.

    Pinned as a test so nobody re-derives that shape believing it is the fix. If
    a future CPython ever lets the error escape `StreamHandler.emit`, this test
    turns red and is the place to read why the extra spelling was removed.
    """
    class OldShape(logging.StreamHandler):
        def emit(self, record):
            try:
                super().emit(record)
            except UnicodeEncodeError:  # pragma: no cover - unreachable, that is the point
                enc = getattr(self.stream, "encoding", None) or "ascii"
                self.stream.write(
                    self.format(record).encode(enc, "replace").decode(enc)
                    + self.terminator)
                self.flush()

    written, noise = _emit(OldShape, EM_DASH_MSG)
    assert written == b"", "the old shape rescued nothing; it only looked like it did"
    assert "--- Logging error ---" in noise


# --------------------------------------------------------------------------
# The cure.
# --------------------------------------------------------------------------

def test_console_safe_handler_keeps_the_sentence():
    written, noise = _emit(ConsoleSafeHandler, EM_DASH_MSG)
    assert noise == "", "a rescued line must not also dump a traceback"
    text = written.decode("cp949")
    assert "legacy workspace config" in text
    assert "use paths.py" in text
    assert "설정 이전" in text, "Korean must survive intact, not be transliterated"
    assert "—" not in text
    assert "?" in text, "the character the terminal cannot draw degrades to a replacement"


@pytest.mark.parametrize("label,char", [
    ("em dash", "—"),
    ("en dash", "–"),
    ("emoji", "\U0001F534"),
    ("bullet", "•"),
])
def test_the_whole_class_of_unencodable_characters(label, char):
    """The neighbours, not just the one that was reported.

    Membership is MEASURED, not guessed - cp949 is a large set and intuition is
    wrong about it. On this box: U+2014 em dash, U+2013 en dash, U+2022 bullet
    and emoji are unencodable and rescued here; U+2026 ellipsis, U+2192 arrow and
    U+2019 curly quote are ENCODABLE and were never defects, so asserting a
    rescue for them would assert a fiction. `test_encodable_output_is_byte_
    identical_to_stock` covers that second group instead.
    """
    msg = "ingestion %s failed (실패)" % char
    stock, stock_noise = _emit(logging.StreamHandler, msg)
    safe, safe_noise = _emit(ConsoleSafeHandler, msg)
    assert stock == b"" and stock_noise, "%s must actually be unencodable in cp949" % label
    assert safe and not safe_noise
    assert "ingestion" in safe.decode("cp949") and "실패" in safe.decode("cp949")


def test_encodable_output_is_byte_identical_to_stock():
    """The rescue must be invisible when there is nothing to rescue."""
    for msg in ("plain ascii line",
                "설정 파일을 찾지 못했습니다",
                "loading… (cp949 encodes U+2026)",
                "a → b (cp949 encodes U+2192)",
                "the operator's box (cp949 encodes U+2019)"):
        stock, stock_noise = _emit(logging.StreamHandler, msg)
        safe, safe_noise = _emit(ConsoleSafeHandler, msg)
        assert stock_noise == "" and safe_noise == ""
        assert safe == stock and safe != b""


def test_utf8_console_is_untouched():
    """No forcing of encodings: a utf-8 terminal keeps every character."""
    written, noise = _emit(ConsoleSafeHandler, EM_DASH_MSG, encoding="utf-8")
    assert noise == ""
    assert "—" in written.decode("utf-8")


# --------------------------------------------------------------------------
# The in-place path, for handlers this codebase did not construct.
# --------------------------------------------------------------------------

def test_make_console_safe_rescues_a_foreign_handler():
    """uvicorn's shape: a plain StreamHandler installed by somebody else."""
    written, noise = _emit(
        lambda s: make_console_safe(logging.StreamHandler(s)), EM_DASH_MSG)
    assert noise == ""
    assert "use paths.py" in written.decode("cp949")


def test_make_console_safe_keeps_the_formatter_and_the_object():
    handler = logging.StreamHandler(io.StringIO())
    fmt = logging.Formatter("custom %(message)s")
    handler.setFormatter(fmt)
    handler.addFilter(logging.Filter("keep.me"))
    same = make_console_safe(handler)
    assert same is handler, "the owner's handler object must survive"
    assert handler.formatter is fmt
    assert handler.filters, "filters the owner attached must survive"


def test_make_console_safe_leaves_file_handlers_alone(tmp_path):
    """`logging.FileHandler` IS a `StreamHandler`, and its utf-8 stream is fine."""
    path = tmp_path / "probe.log"
    fh = logging.FileHandler(str(path), encoding="utf-8")
    try:
        assert make_console_safe(fh) is fh
        assert "emit" not in fh.__dict__, "a file handler must not be rewired"
    finally:
        fh.close()


def test_make_console_safe_is_idempotent():
    handler = ConsoleSafeHandler(io.StringIO())
    make_console_safe(handler)
    assert "emit" not in handler.__dict__
    plain = logging.StreamHandler(io.StringIO())
    make_console_safe(plain)
    first = plain.emit
    make_console_safe(plain)
    assert plain.emit.__func__ is first.__func__


def test_non_stream_handlers_pass_through():
    class Odd(logging.Handler):
        def emit(self, record):  # pragma: no cover - never called
            pass
    h = Odd()
    assert make_console_safe(h) is h
    assert "emit" not in h.__dict__


# --------------------------------------------------------------------------
# The one implementation, and the process wiring that uses it.
# --------------------------------------------------------------------------

def test_map_alignment_reuses_the_shared_class():
    """One implementation, not two spellings that can drift apart."""
    import map_alignment
    assert map_alignment._ConsoleSafeHandler is ConsoleSafeHandler


# `get_process_logger` reconfigures the ROOT logger of whatever process calls it,
# so it runs in its own interpreter for the same reason test_process_logging.py
# does: calling it inside pytest would rip the handlers out from under pytest's
# capture for every later test in the session.
_PROBE = r"""
import io, os, sys, json, logging
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
from utils.logger import get_process_logger, ConsoleSafeHandler

buf = io.BytesIO()
console = io.TextIOWrapper(buf, encoding="cp949", errors="strict", newline="")
real_stdout = sys.stdout
sys.stdout = console
try:
    lg = get_process_logger("Watcher", os.environ["PROBE_LOG_NAME"])
finally:
    sys.stdout = real_stdout

noise, real_stderr = io.StringIO(), sys.stderr
sys.stderr = noise
try:
    lg.warning(%r)
finally:
    sys.stderr = real_stderr

for h in logging.getLogger().handlers:
    h.flush()
console.flush()

file_handlers = [h for h in logging.getLogger().handlers
                 if isinstance(h, logging.FileHandler)]
console_handlers = [h for h in logging.getLogger().handlers
                    if isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)]
result = {
    "console_bytes": len(buf.getvalue()),
    "console_text": buf.getvalue().decode("cp949"),
    "stderr_noise": noise.getvalue(),
    "console_is_safe": all(isinstance(h, ConsoleSafeHandler) for h in console_handlers),
    "console_handler_count": len(console_handlers),
    "file_encodings": [h.encoding for h in file_handlers],
    "file_paths": [h.baseFilename for h in file_handlers],
}
real_stdout.write("PROBE_RESULT" + json.dumps(result))
""" % (EM_DASH_MSG,)


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    root = tmp_path_factory.mktemp("console_safe_root")
    env = dict(os.environ)
    env["ASSY_DATA_ROOT"] = str(root)
    env["PROBE_SERVER_DIR"] = SERVER_DIR
    env["PROBE_LOG_NAME"] = "console_safe_probe.log"
    out = subprocess.run([sys.executable, "-c", _PROBE], env=env,
                         capture_output=True, text=True, encoding="utf-8")
    assert "PROBE_RESULT" in out.stdout, (out.stdout, out.stderr)
    return json.loads(out.stdout.split("PROBE_RESULT", 1)[1])


def test_every_process_console_is_safe(probe):
    """One edit covers all six children: they all build their console here."""
    assert probe["console_handler_count"] == 1
    assert probe["console_is_safe"]


def test_process_console_survives_the_reported_line(probe):
    assert probe["stderr_noise"] == "", probe["stderr_noise"]
    assert probe["console_bytes"] > 0
    assert "use paths.py" in probe["console_text"]
    assert "설정 이전" in probe["console_text"]
    assert "—" not in probe["console_text"]


def test_file_half_keeps_the_character(probe):
    """Confirmed, not assumed: the file is utf-8 and loses nothing."""
    assert probe["file_encodings"] == ["utf-8"]
    with open(probe["file_paths"][0], "rb") as f:
        raw = f.read()
    assert b"\xe2\x80\x94" in raw, "the em dash must reach the file as utf-8 bytes"
    text = raw.decode("utf-8")
    assert "—" in text and "설정 이전" in text
