import contextvars
import sys

# 중복 임포트로 인한 ContextVar 분리 현상을 방지하기 위해 sys 모듈 레벨에서 싱글톤 캐시합니다.
if not hasattr(sys, "_context_vars_cache"):
    sys._context_vars_cache = {
        "request_user": contextvars.ContextVar("request_user", default="system"),
        "request_transaction_id": contextvars.ContextVar("request_transaction_id", default=None),
        "request_source": contextvars.ContextVar("request_source", default="user")
    }

request_user = sys._context_vars_cache["request_user"]
request_transaction_id = sys._context_vars_cache["request_transaction_id"]
request_source = sys._context_vars_cache["request_source"]
