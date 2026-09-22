# -*- coding: utf-8 -*-
"""A mapper written with `@mapper` must be handed the rule the operator declared.

🔴 WHAT THIS PINS, AND WHY IT IS NOT AN INTERNAL DETAIL. The SDK reads `target_table` off
the rule; without the rule it raises 「has no target table」 and the operator sees a
contract error two frames away from the cause. Measured on the live box 2026-09-23: every
`@mapper` in `mappers/` failed this way, and every run of `chain_replay` that touched one
was recorded as `failed` in `retroactive_runs`.

⚠️ THE FAULT WAS IN THE MEASURING, NOT THE CALLING. `functools.wraps` leaves `__wrapped__`
on the wrapper and `inspect.signature` follows it by default, so the seat that asks 「does
this mapper take a rule」 was reading the AUTHOR's inner `(df, db)` instead of the wrapper's
own `(db, payloads, rule=None)`. Both halves are asserted below: the signature this seat
must read, and the end-to-end effect of reading the wrong one.
"""
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import mapper_sdk                                                    # noqa: E402
from chain.mapper_call import mapper_accepts_rule                    # noqa: E402

PAYLOADS = [{"row_id": "r1",
             "data": {"a_column": {"value": None}, "key_column": {"value": "K1"}}}]
RULE = {"name": "probe_rule", "target_table": "probe_table"}


def _decorated():
    @mapper_sdk.mapper(name="probe_decorated_mapper")
    def probe_decorated_mapper(df, db):
        df["a_column"] = "X"
        return df
    return probe_decorated_mapper


def test_a_decorated_mapper_reports_that_it_takes_a_rule():
    """⛔ THE REGRESSION LINE. Reading the wrapped function answers `False` here, and the
    whole failure follows from that one boolean."""
    assert mapper_accepts_rule(_decorated()) is True


def test_a_plain_mapper_without_a_rule_parameter_still_reports_false():
    """The old calling convention is unchanged - this is what `follow_wrapped` must not
    break."""
    def plain(db, payloads):
        return {"updates": []}

    assert mapper_accepts_rule(plain) is False


def test_a_plain_mapper_with_a_rule_parameter_reports_true():
    def plain_with_rule(db, payloads, rule=None):
        return {"updates": []}

    assert mapper_accepts_rule(plain_with_rule) is True


def test_the_rule_reaches_the_sdk_rather_than_stopping_at_the_seat():
    """🔴 THE HALF THAT IS NOT A SIGNATURE. Reading the wrapped function made the SDK
    raise 「the rule declares no 'target_table'」; with the rule it gets that far and fails
    for a DIFFERENT reason (this fixture's table is not declared here). The two refusals are
    what tell the seat's fault from the fixture's.

    ⚠️ WHAT THIS DOES NOT ASSERT: that the operator's column lands. That needs a DECLARED
    table, which is this box's configuration and not the grammar's - so it is measured on the
    running box, not here. (2026-09-23: measured by calling the registered wrapper with the
    loaded rule - `dt_x_base` came back as `X`. The worker's own end-to-end pass is a
    separate measurement and is recorded in the channel, not asserted here.)
    """
    import mapper_sdk as sdk

    try:
        _decorated()(None, PAYLOADS, rule=RULE)
    except sdk.MapperContractError as exc:
        assert "no 'target_table'" not in str(exc), (
            "the rule did not reach the SDK: %s" % exc)
