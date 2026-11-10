"""A named stage of the work in hand - one clock, said on every line open around it (lead 11-10: the retroactive run's
step line, the chain group's line and the request's slow line called three copies of this; only the line differs).

`stage(name, rows=None, said=None)` times the block once and hands it to each receiver open in this context: a
retroactive run (`RunControl`), a chain group or a watcher chunk (`alignment_batch_counts.counting_group`), a request
(`request_timing.begin`), a lap table (`Seconds`). A receiver opens with `receiving` or `opened` / `closed`.
A receiver has `enter(name, rows, said) -> entry` and `leave(entry, seconds, told)`; `outer_only` = it takes a stage
only when no stage is open around it here (a line that sums its stages must not count one twice).
"""
import contextlib
import contextvars
import time

#: The receivers open in this context, outermost first - a tuple, rebound and never changed in place: a thread started
#: with this context (`asyncio.to_thread`) shares the receivers but not what it opens.
_RECEIVERS = contextvars.ContextVar("stage_receivers", default=())
#: The receivers a stage is already open for in this context - a stage inside it is not an outer one to them.
_INSIDE = contextvars.ContextVar("stage_inside", default=())


def opened(receiver):
    """`receiver` takes the stages below in this context - the token `closed` takes."""
    return _RECEIVERS.set(_RECEIVERS.get() + (receiver,))


def closed(token):
    _RECEIVERS.reset(token)


@contextlib.contextmanager
def receiving(receiver):
    token = opened(receiver)
    try:
        yield receiver
    finally:
        closed(token)


@contextlib.contextmanager
def stage(name, rows=None, said=None):
    """This block as the stage `name` on every line open around it. `rows` - what it works through; `said` - what a beat
    says beyond the name. Yields a dict: a `note` there ends a step line, a `rows` there replaces the one given."""
    inside = _INSIDE.get()
    takers = [receiver for receiver in _RECEIVERS.get()
              if not (receiver.outer_only and any(receiver is one for one in inside))]
    told = {}
    if not takers:
        yield told
        return
    entries, started = [], None
    try:
        for receiver in takers:                    # an `enter` that raises (a group asked to stop) ends the stage here
            entries.append((receiver, receiver.enter(name, rows, said)))
        token, started = _INSIDE.set(inside + tuple(takers)), time.perf_counter()
        try:
            yield told
        finally:
            _INSIDE.reset(token)
    finally:
        seconds = 0.0 if started is None else time.perf_counter() - started
        for receiver, entry in reversed(entries):
            receiver.leave(entry, seconds, told)


class Seconds(dict):
    """A receiver: {stage name: seconds} - each outer stage's seconds added under its name."""

    outer_only = True

    def enter(self, name, rows, said):
        return name

    def leave(self, name, seconds, told):
        self[name] = self.get(name, 0.0) + seconds
