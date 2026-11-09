"""The one seat where a route's answer becomes bytes - on the request's worker thread, not the event loop (총괄 3d1f25056,
소유자 「알아서해」 ②).

🔴 WHY. A sync route that returns a dict was turned into bytes by fastapi on the EVENT LOOP: `serialize_response`
runs `jsonable_encoder` over the whole answer and `JSONResponse.render` runs `json.dumps`, both in the loop thread. While
they ran, every other request waited - measured by the lead on a toy app (fastapi 0.135.3, this box): a 50 MB answer
stopped async pings, sync pings and static files alike for 7.9 s; turned into bytes inside the route, 0.71 s with a
0.63 s stop (json.dumps holds the GIL).

HOW. `OffLoopJSONRoute` is the route class of the app and of every APIRouter. For a sync endpoint with no response
model and no response class of its own, it wraps the endpoint: the answer is dumped right there, on the worker thread
the endpoint already runs on, with JSONResponse's own settings and `jsonable_encoder` for what json cannot take - the
same bytes, with two known differences: a dict key json cannot take (a date, a UUID, a Decimal, an Enum) is dumped
by a second pass over `jsonable_encoder(answer)`, as before; a key starting with `_sa` is no longer dropped (the
encoder's sqlalchemy_safe removed a name an operator wrote). The bytes go back as `_Encoded` (a str, so fastapi's encoder hands it through untouched) and
`_EncodedJSONResponse` renders them as they are. fastapi still builds the response: the decorator's status code, a
bodyless status, and headers a dependency set all stay its own.

GZIP (lead 11-09 ㄴ): gzipping is making bytes too, so it is done here and in the pool process (`process_pool._answer`),
never on the loop - one judgement, `gzipped`. Only JSON: a picture, a zip, a file pass as they are.

⚠️ NOT WRAPPED, so still turned into bytes on the loop: an async endpoint, a route that declares `response_model` (or
a return annotation fastapi reads as one) or its own `response_class`. An endpoint that returns a Response is wrapped
and its Response passes through as it is.
"""
import functools
import gzip
import inspect
import json

from fastapi.encoders import jsonable_encoder
from fastapi.datastructures import DefaultPlaceholder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.responses import Response

from database.context import request_accept_encoding

JSON = "application/json"
#: Below this a body goes as it is (lead 11-09 ㄴ: 1 KB, level 1 - a 4.5 MB grid page 36x smaller in 12 ms).
GZIP_MIN_BYTES = 1024
GZIP_LEVEL = 1


class _Encoded(str):
    """An answer already turned into bytes (`payload`), `gzipped` or not. A str, so `jsonable_encoder` returns it as it
    is."""
    gzipped = False


class _EncodedJSONResponse(JSONResponse):
    def __init__(self, content=None, *args, **kwargs):
        super().__init__(content, *args, **kwargs)
        if getattr(content, "gzipped", False):
            self.headers["content-encoding"] = "gzip"
            self.headers.add_vary_header("Accept-Encoding")

    def render(self, content) -> bytes:
        if isinstance(content, _Encoded):
            return content.payload
        return super().render(content)


_dumps = functools.partial(json.dumps, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":"))


def encode(answer) -> _Encoded:
    """`answer` as JSONResponse would write it, here - the request's «serialize» stage (`request_timing.stage`)."""
    from runtime import request_timing

    encoded = _Encoded("")
    with request_timing.stage("serialize"):
        try:
            text = _dumps(answer, default=jsonable_encoder)
        except TypeError:
            # json.dumps never asks `default` about a dict KEY - a date or a UUID key is the old path's whole pass
            text = _dumps(jsonable_encoder(answer))
        encoded.payload = text.encode("utf-8")
    return encoded


def gzipped(body, accepts, content_type=JSON):
    """THE one judgement «send these bytes gzipped?»: `body` gzipped when it is JSON, `GZIP_MIN_BYTES` or more, and
    `accepts` (the asker's Accept-Encoding) takes gzip - else None, sent as it is."""
    if (not str(content_type or "").startswith(JSON) or len(body) < GZIP_MIN_BYTES
            or "gzip" not in str(accepts or "").lower()):
        return None
    return gzip.compress(body, GZIP_LEVEL)


def gzip_response(response, accepts):
    """`response` gzipped in place when `gzipped` says so - one that carries its body (not a file or a stream) and is
    not encoded yet."""
    body = getattr(response, "body", None)
    if body is None or "content-encoding" in response.headers:
        return response
    packed = gzipped(body, accepts, response.headers.get("content-type"))
    if packed is not None:
        response.body = packed
        response.headers["content-encoding"] = "gzip"
        response.headers["content-length"] = str(len(packed))
        response.headers.add_vary_header("Accept-Encoding")
    return response


def _off_loop(endpoint):
    @functools.wraps(endpoint)
    def answered_as_bytes(*args, **kwargs):
        answer = endpoint(*args, **kwargs)
        accepts = request_accept_encoding.get()
        if isinstance(answer, Response):
            return gzip_response(answer, accepts)
        encoded = encode(answer)
        packed = gzipped(encoded.payload, accepts)
        if packed is not None:
            encoded.payload, encoded.gzipped = packed, True
        return encoded
    return answered_as_bytes


class OffLoopJSONRoute(APIRoute):
    def __init__(self, path, endpoint, **kwargs):
        model = kwargs.get("response_model")
        if (not inspect.iscoroutinefunction(endpoint)
                and (model is None or isinstance(model, DefaultPlaceholder) and model.value is None)
                and inspect.signature(endpoint).return_annotation is inspect.Signature.empty
                and isinstance(kwargs.get("response_class", DefaultPlaceholder(JSONResponse)), DefaultPlaceholder)):
            endpoint = _off_loop(endpoint)
            kwargs["response_class"] = _EncodedJSONResponse
        super().__init__(path, endpoint, **kwargs)
