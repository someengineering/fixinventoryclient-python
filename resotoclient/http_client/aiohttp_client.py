from resotoclient.http_client import AsyncHttpClient
from resotoclient.http_client import HttpResponse
from typing import Dict, Optional, Callable, Union, AsyncIterator
from resotoclient.models import JsValue
from resotoclient.jwt_utils import encode_jwt_to_headers
import aiohttp
import ssl
from yarl import URL


class AioHttpClient(AsyncHttpClient):
    def __init__(
        self, url: str, psk: Optional[str], session_id: str, get_ca_cert_path: Optional[Callable[[], str]] = None
    ):

        default_headers = {"Content-type": "application/json", "Accept": "application/json"}

        if psk:
            encode_jwt_to_headers(default_headers, {}, psk)

        self.session = aiohttp.ClientSession(headers=default_headers)
        self.url = url
        self.psk = psk
        self.get_ca_cert_path = get_ca_cert_path
        self.session_id = session_id

    def _ssl_context(self) -> Union[ssl.SSLContext, bool]:
        if self.get_ca_cert_path:
            return ssl.create_default_context(cafile=self.get_ca_cert_path())
        else:
            return False

    def _default_query_params(self) -> Dict[str, str]:
        return {"session_id": self.session_id}

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        """
        Make a GET request to the server.

        Args:
            path: The path to the resource.
            params: The query parameters to add to the request.
            headers: The headers to add to the request.
            stream: Whether to stream the response body.

        If a streamed respones was requested, you MUST consume the whole response body
        or call release to return the connecton back into the pool.
        """

        query_params = self._default_query_params().update(params or {})
        url = URL(self.url).with_path(path).with_query(query_params)
        if stream:
            headers = (headers or {}).update({"Accept": "application/x-ndjson"})
        resp = await self.session.get(url, ssl=self._ssl_context(), headers=headers)

        async def lines(response: aiohttp.ClientResponse) -> AsyncIterator[bytes]:
            async for line in response.content:
                yield line

        return HttpResponse(
            status_code=resp.status,
            headers=resp.headers,
            text=resp.text,
            json=resp.json,
            async_iter_lines=lambda: lines(resp),
            release=resp.release,
        )

    async def post(
        self,
        path: str,
        json: Optional[JsValue] = None,
        data: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        """
        Make a POST request to the server.

        Args:
            path: The path to the resource.
            json: The json body to send with the request.
            data: The data body to send with the request.
            params: The query parameters to add to the request.
            headers: The headers to add to the request.
            stream: Whether to stream the response body.

        If a streamed respones was requested, you MUST consume the whole response body
        or call release to return the connecton back into the pool.
        """

        query_params = self._default_query_params().update(params or {})
        url = URL(self.url).with_path(path).with_query(query_params)
        if stream:
            headers = (headers or {}).update({"Accept": "application/x-ndjson"})
        resp = await self.session.post(url, ssl=self._ssl_context(), headers=headers, json=json, data=data)

        async def lines(response: aiohttp.ClientResponse) -> AsyncIterator[bytes]:
            async for line in response.content:
                yield line

        return HttpResponse(
            status_code=resp.status,
            headers=resp.headers,
            text=resp.text,
            json=resp.json,
            async_iter_lines=lambda: lines(resp),
            release=resp.release,
        )

    async def put(self, path: str, json: JsValue, params: Optional[Dict[str, str]] = None) -> HttpResponse:
        pass

    async def patch(self, path: str, json: JsValue) -> HttpResponse:
        pass

    async def delete(self, path: str, params: Optional[Dict[str, str]]) -> HttpResponse:
        pass
