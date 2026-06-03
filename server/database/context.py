import contextvars

request_user = contextvars.ContextVar("request_user", default="system")
request_transaction_id = contextvars.ContextVar("request_transaction_id", default=None)
request_source = contextvars.ContextVar("request_source", default="user")
