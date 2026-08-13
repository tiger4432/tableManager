"""Monotonic UUIDv7 (RFC 9562 §5.7) - the ledger's `id`, and therefore its watermark.

WHY THIS FILE EXISTS RATHER THAN `uuid.uuid4()` OR `uuid.uuid7()`
-----------------------------------------------------------------
`id` is not decoration. `CANONICAL_LEDGER_DESIGN.md` §3 makes it carry TWO jobs that a
random uuid cannot do:

  * **the watermark** - a consumer's cursor is "the largest id I have processed", and
    `WHERE id > :cursor ORDER BY id` is only a correct scan if ids increase with
    insertion. A uuid4 cursor would silently skip rows forever.
  * **the record time** - the design deliberately spends no column on `recorded_at`
    because a v7 uuid embeds a 48-bit millisecond timestamp. Take that away and the
    envelope loses a field it says it has.

The stdlib gained `uuid.uuid7()` only in Python 3.14, and even there the guarantee is
per-process and unspecified across implementations. This box runs an older interpreter
(the `assy_manager` env), so the generator has to be here.

🔴 THE FAILURE THIS GUARDS AGAINST IS ALREADY ON THE RECORD
-----------------------------------------------------------
2026-08-11, this project: a fixture key generator that WRAPPED was used to size an index.
The keys looked fine one at a time and the whole measurement was fiction, because the
drift only shows at the large end. A ledger id generator that goes backwards - clock
adjustment, NTP step, two calls in the same millisecond - produces exactly that failure
in production instead of in a fixture: the cursor stops advancing past a value it has
already seen, and the rows behind it are never translated.

So this generator is monotonic by CONSTRUCTION, not by hope:

  * the 12 bits of `rand_a` are used as a **sub-millisecond counter** (the "Replace
    Leftmost Random Bits with Increased Clock Precision" method the RFC names), so up
    to 4,096 ids inside one millisecond still increase;
  * if that counter would overflow, the generator **borrows from the future** - it
    advances its own millisecond by one and resets the counter, rather than emitting a
    duplicate or a smaller value;
  * if the wall clock moves BACKWARDS, the generator keeps its previous millisecond.
    Time going backwards is a machine problem; a non-monotonic ledger is a data problem,
    and this trade is deliberate.

`assert_monotonic` exists so a test can prove the property instead of assuming it, and
so the fault-injection round has something to break.
"""
from __future__ import annotations

import os
import threading
import time
import uuid

# 12 bits of `rand_a` are spent on the intra-millisecond counter.
_COUNTER_BITS = 12
_COUNTER_MAX = (1 << _COUNTER_BITS) - 1

_lock = threading.Lock()
_last_ms = -1
_counter = 0


def uuid7() -> uuid.UUID:
    """A UUIDv7 that is strictly greater than every UUIDv7 this process returned before.

    Thread-safe. The lock is held for a few arithmetic operations only; the random
    bits are drawn inside it too, because drawing them outside would let two threads
    interleave and produce equal (ms, counter) prefixes with an arbitrary tail order.
    """
    global _last_ms, _counter
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms = now_ms
            _counter = 0
        else:
            # Same millisecond, or the clock went backwards. Both are handled by
            # holding `_last_ms` and stepping the counter - never by emitting a
            # value that is not larger than the previous one.
            _counter += 1
            if _counter > _COUNTER_MAX:
                _last_ms += 1
                _counter = 0
        ms = _last_ms
        counter = _counter
        rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)

    value = (
        (ms & ((1 << 48) - 1)) << 80
        | 0x7 << 76                      # version 7
        | (counter & _COUNTER_MAX) << 64
        | 0b10 << 62                     # RFC 9562 variant
        | rand_b
    )
    return uuid.UUID(int=value)


def timestamp_ms(value) -> int:
    """The 48-bit millisecond stamp embedded in a UUIDv7. The record time, decoded.

    Accepts a `uuid.UUID` or its string form so an operator can read a record time
    straight out of a row without the ledger having to store one.
    """
    if not isinstance(value, uuid.UUID):
        value = uuid.UUID(str(value))
    return value.int >> 80


def assert_monotonic(values) -> int:
    """Raise unless `values` is strictly increasing. Returns how many it checked.

    🔴 The return value is not garnish. A guard that iterates an EMPTY sequence
    "passes" vacuously, and this session has already shipped one harness where every
    injection reported green for exactly that reason. A caller that asserts on the
    COUNT cannot be fooled that way.
    """
    previous = None
    checked = 0
    for value in values:
        current = value.int if isinstance(value, uuid.UUID) else uuid.UUID(str(value)).int
        if previous is not None and current <= previous:
            raise AssertionError(
                f"uuid7 is not monotonic: {uuid.UUID(int=current)} does not come after "
                f"{uuid.UUID(int=previous)} (element {checked})")
        previous = current
        checked += 1
    return checked
