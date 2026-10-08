import contextvars
import sys

# 중복 임포트로 인한 ContextVar 분리 현상을 방지하기 위해 sys 모듈 레벨에서 싱글톤 캐시합니다.
if not hasattr(sys, "_context_vars_cache"):
    sys._context_vars_cache = {
        "request_user": contextvars.ContextVar("request_user", default="system"),
        "request_transaction_id": contextvars.ContextVar("request_transaction_id", default=None),
        "request_source": contextvars.ContextVar("request_source", default="user"),
        # [OUTBOX-4] Per-row vs collapsed outbox staging. DEFAULTS TO per_row, so
        # every caller that does not opt in keeps today's behaviour and the safe
        # direction is the one you get by doing nothing. Three write paths opt IN
        # explicitly: ingestion, the chain worker, and the product door (S-82).
        #
        # Why an explicit channel and not an inference: `request_source` is a
        # FILENAME on the ingestion path (directory_watcher derives it from the
        # file's basename), not a channel; and row count says nothing about which
        # caller is writing - inferring from either is how a path would collapse
        # without anyone having decided that it should.
        "request_outbox_mode": contextvars.ContextVar("request_outbox_mode",
                                                      default="per_row"),
        # [DEPTH] How many chain hops produced the write being staged. `None` means
        # "not written by the chain" and is NOT the same as 0 - an event with no depth
        # came from outside the chain and must never be refused for being too deep,
        # while a 0 would be a chain write that forgot to count. Folding the two would
        # make them indistinguishable exactly when it matters.
        "request_chain_depth": contextvars.ContextVar("request_chain_depth", default=None),
    }

request_user = sys._context_vars_cache["request_user"]
request_transaction_id = sys._context_vars_cache["request_transaction_id"]
request_source = sys._context_vars_cache["request_source"]
# [OUTBOX-4] Value is one of event_constants.OUTBOX_MODE_*. The literal default
# above is spelled out rather than imported because this module is imported from
# contexts where `server/` is not yet on sys.path; the two are pinned equal by
# test_outbox_collapse.test_default_mode_is_per_row.
request_outbox_mode = sys._context_vars_cache["request_outbox_mode"]
#: [DEPTH] Set by the chain worker for the span of its writes; read by `_outbox_envelope`.
request_chain_depth = sys._context_vars_cache["request_chain_depth"]
#: [CHANNEL] Who caused the write - one of `event_constants.CHANNEL_*`, set by the door (the
#: chain, the HTTP door, the watcher, a retroactive run). `None` = no door said. Beside the
#: depth and for the same reason: `crud.transaction_context` re-sets `request_source` to the
#: item's LAYER, and never touches this (총괄 5676b8bc6 ⓪, 판정 425 · S-280).
request_channel = sys._context_vars_cache.setdefault(
    "request_channel", contextvars.ContextVar("request_channel", default=None))
#: [CASCADE] True while a replay that asked to cascade stages its trigger events, and while the
#: chain writes what those woke (총괄 146b208cb).
request_cascade = sys._context_vars_cache.setdefault(
    "request_cascade", contextvars.ContextVar("request_cascade", default=False))
#: [WRITTEN-BY] The declarations whose rules are writing, while the chain writes (총괄 ebefd20e8).
request_written_by = sys._context_vars_cache.setdefault(
    "request_written_by", contextvars.ContextVar("request_written_by", default=None))
#: [RUN] The retroactive run (`retroactive_runs.run_id`) whose work this write is - set where every
#: run ends (`admin.retroactive._run_to_the_end`) and carried by the chain into what that run's
#: events woke (총괄 b3a4334db). `None` = no run: the write is its own transaction's.
request_run_id = sys._context_vars_cache.setdefault(
    "request_run_id", contextvars.ContextVar("request_run_id", default=None))
#: [CHAIN GROUP] True while a chain group runs - whatever channel its writes go out on - so its
#: transactions take the chain's statement limit (소유자 10-08 「체인 타임아웃 걸어」).
request_chain_group = sys._context_vars_cache.setdefault(
    "request_chain_group", contextvars.ContextVar("request_chain_group", default=False))


def _for_the_block(var, value):
    import contextlib

    @contextlib.contextmanager
    def _cm():
        token = var.set(value)
        try:
            yield
        finally:
            var.reset(token)

    return _cm()


def channel(value: str):
    """Context manager: the writes inside go out on channel `value` - the door's word for
    who caused them. Same shape as `outbox_mode`, and like it untouched by
    `crud.transaction_context`."""
    return _for_the_block(request_channel, value)


def cascade(value: bool):
    """Context manager: the writes inside say their replay asked to cascade."""
    return _for_the_block(request_cascade, bool(value))


def written_by(declarations):
    """Context manager: the writes inside say which declarations made them (총괄 ebefd20e8)."""
    return _for_the_block(request_written_by, tuple(sorted(declarations)) or None)


def retroactive_run(run_id):
    """Context manager: the writes inside are retroactive run `run_id`'s work (총괄 b3a4334db)."""
    return _for_the_block(request_run_id, run_id or None)


def chain_group():
    """Context manager: the transactions begun inside are a chain group's (소유자 10-08)."""
    return _for_the_block(request_chain_group, True)


def outbox_mode(mode: str):
    """Context manager selecting the outbox staging mode for a bulk write.

    Nests OUTSIDE `crud.transaction_context` (which sets user/tx/source and does
    not touch this var), so a caller wraps its whole file loop once.
    """
    import contextlib

    @contextlib.contextmanager
    def _cm():
        token = request_outbox_mode.set(mode)
        try:
            yield
        finally:
            request_outbox_mode.reset(token)

    return _cm()
