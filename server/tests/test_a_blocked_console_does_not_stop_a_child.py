# -*- coding: utf-8 -*-
"""Owner 10-20, lead cc6840513: a console that takes no writes (a Windows console in selection mode) must not stop a
child. The reader of a child's output writes the file and hands the console line to a queue a console thread drains;
past CONSOLE_QUEUE_LINES a line is dropped and counted, and the count is said once when the console takes lines again.
A real child writes more lines than the pipe and the queue hold, into a console that blocks until released."""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from runtime.process_supervisor import CONSOLE_QUEUE_LINES, ChildSpec, Supervisor   # noqa: E402

LINES = 3 * CONSOLE_QUEUE_LINES


class _BlockedConsole:
    """A console whose every write waits until `release` is set - what a Windows console in selection mode does."""

    def __init__(self):
        self.release = threading.Event()
        self.lines = []

    def write(self, data):
        self.release.wait()
        self.lines.append(bytes(data))
        return len(data)

    def flush(self):
        pass


class _Stdout:
    def __init__(self, buffer):
        self.buffer = buffer

    def write(self, text):
        return len(text)

    def flush(self):
        pass


def test_a_child_writing_into_a_blocked_console_ends_and_its_file_keeps_every_line(tmp_path, monkeypatch):
    console = _BlockedConsole()
    monkeypatch.setattr(sys, "stdout", _Stdout(console))
    script = tmp_path / "writer.py"
    script.write_text("import sys\nfor n in range(%d):\n    sys.stdout.write('line %%06d %%s\\n' %% (n, 'x' * 60))\n"
                      % LINES, encoding="utf-8")
    log_file = str(tmp_path / "writer_stdout.log")
    sup = Supervisor([ChildSpec("writer", [sys.executable, str(script)], str(tmp_path), log_file=log_file)],
                     status_file=str(tmp_path / "status.json"))
    sup.start_all()
    child = sup.children[0]
    try:
        child.proc.wait(timeout=60)                    # before cc6840513: the pipe filled and the child stopped here
        child.log_pump.join(timeout=30)
        assert not child.log_pump.is_alive(), "the reader is still waiting"
        with open(log_file, "rb") as handle:
            kept = [line for line in handle.read().splitlines() if line.startswith(b"line ")]
        assert len(kept) == LINES, len(kept)
    finally:
        console.release.set()
        sup.stop_all(timeout=3.0)
    said = []
    for _ in range(300):
        said = [line for line in console.lines if line.startswith(b"[Supervisor] writer: ")]
        shown = [line for line in console.lines if line.startswith(b"line ")]
        dropped = int(said[0].split()[2]) if said else 0
        if said and len(shown) + dropped == LINES:
            break
        time.sleep(0.1)
    assert len(said) == 1 and said[0].endswith(b"console line(s) dropped while the console was blocked\n"), said
    assert dropped > 0 and len(shown) + dropped == LINES, (len(shown), dropped)
