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
same bytes. The bytes go back as `_Encoded` (a str, so fastapi's encoder hands it through untouched) and
`_EncodedJSONResponse` renders them as they are. fastapi still builds the response: the decorator's status code, a
bodyless status, and headers a dependency set all stay its own.

⚠️ NOT WRAPPED: an async endpoint (its answer is the loop's anyway), a route that declares `response_model` (or a
return annotation fastapi reads as one) or its own `response_class`, and an endpoint that returns a Response.
"""
import functools
import inspect
import json

from fastapi.encoders import jsonable_encoder
from fastapi.datastructures import DefaultPlaceholder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.responses import Response


class _Encoded(str):
    """An answer already turned into bytes (`payload`). A str, so `jsonable_encoder` returns it as it is."""


class _EncodedJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        if isinstance(content, _Encoded):
            return content.payload
        return super().render(content)


def encode(answer) -> _Encoded:
    """`answer` as JSONResponse would write it, here."""
    encoded = _Encoded("")
    encoded.payload = json.dumps(answer, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":"),
                                 default=jsonable_encoder).encode("utf-8")
    return encoded


def _off_loop(endpoint):
    @functools.wraps(endpoint)
    def answered_as_bytes(*args, **kwargs):
        answer = endpoint(*args, **kwargs)
        return answer if isinstance(answer, Response) else encode(answer)
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
