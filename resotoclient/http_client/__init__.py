from abc import ABC, abstractmethod
from typing import Dict, Optional, AsyncIterator, Callable, Awaitable, Mapping
from attrs import define
from resotoclient.models import JsValue, JsObject


@define
class HttpResponse:
    """
    An abstraction of an HTTP response to hide the underlying HTTP client implementation.

    Attributes:
        status_code: The HTTP status code of the response.
        headers: The HTTP headers of the response.
        text: A function that returns response body as a string.
        json: A function that returns response body as a JSON object.
        async_iter_lines: A function that returns the async iterator of the response body, present if streaming was requested in a async client.
        release: Release the resources associated with the response if it is no longer needed, e.g. during streaming a streamed.
    """

    status_code: int
    headers: Mapping[str, str]
    text: Callable[[], Awaitable[str]]
    json: Callable[[], Awaitable[JsObject]]
    async_iter_lines: Callable[[], AsyncIterator[bytes]]
    release: Callable[[], None]


class AsyncHttpClient(ABC):
    """
    An abstract class for an HTTP client that can make async requests.

    The implementation will differ depending on the runtime, e.g. JS fetch API in Pyodide
    and aiohttp in CPython environments.
    """

    @abstractmethod
    async def get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        pass

    @abstractmethod
    async def post(
        self,
        path: str,
        json: Optional[JsValue] = None,
        data: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        pass

    @abstractmethod
    async def put(
        self, path: str, json: JsValue, params: Optional[Dict[str, str]] = None
    ) -> HttpResponse:
        pass

    @abstractmethod
    async def patch(self, path: str, json: JsValue) -> HttpResponse:
        pass

    @abstractmethod
    async def delete(self, path: str, params: Optional[Dict[str, str]]) -> HttpResponse:
        pass