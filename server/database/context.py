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
