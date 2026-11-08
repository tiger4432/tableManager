"""Owner 11-09: «한 배치 5 초» does not cover the run's one-off start. The start - the boundary reload's first read,
its import of the chain worker with it - runs before the first page and is said once, `[<op>] Starting: <s> s`, in
the phase the run already shows («Starting»); the first page's line counts from its end."""
from admin import retroactive
from chain import ingestion_worker as ciw
from runtime import system_reload


def test_the_start_is_said_once_before_the_first_page_and_left_out_of_its_seconds(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(retroactive.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(system_reload, "reload_mark", lambda: 5)
    asked = []

    def boundary(reader, seen):
        asked.append(seen)
        clock[0] += 2.0                                     # a read takes 2 s
        return False, seen

    monkeypatch.setattr(ciw, "reload_at_boundary", boundary)
    lines = []
    control = retroactive.RunControl(None, op="op", log=lines.append)
    hook = retroactive._checkpoint(control)
    assert asked == [5] and lines == ["[op] Starting: 2.00 s"] and control._phase[0] == "Starting"

    clock[0] += 1.0                                         # the first page's own work
    hook(10)
    assert asked == [5, 5] and lines[1].startswith("[op] page 1: 10 rows · 1.0 s · "), lines
    assert sum("Starting" in line for line in lines) == 1
