import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone

from aiohttp import WSMsgType

from resotoclient.http_client import AsyncHttpClient
from resotoclient.http_client import HttpResponse
from typing import Dict, Optional, Callable, Union, AsyncIterator, Awaitable, Any
from resotoclient.models import JsValue, JsObject
from resotoclient.jwt_utils import encode_jwt_to_headers, jwt_expiration
import aiohttp
import ssl
from yarl import URL
from asyncio import AbstractEventLoop, Queue
from multidict import CIMultiDict

log = logging.getLogger(__name__)


# The receiver of a poison pill is sentenced to die
class PoisonPill:
    pass


class AioHttpClient(AsyncHttpClient):
    def __init__(
        self,
        url: str,
        *,
        psk: Optional[str],
        additional_headers: Optional[Dict[str, str]] = None,
        session_id: str,
        renew_auth_token_before: timedelta,
        get_ssl_context: Optional[Callable[[], Awaitable[ssl.SSLContext]]] = None,
        loop: Optional[AbstractEventLoop] = None,
    ):
        self.session = aiohttp.ClientSession(loop=loop)
        self.url = url
        self.psk = psk
        self.get_ssl_context = get_ssl_context
        self.session_id = session_id
        self.renew_auth_token_before = renew_auth_token_before
        self.additional_headers = additional_headers or {}
        self.renew_auth_task: Optional[asyncio.Task[Any]] = None

    async def start(self) -> None:
        if "Authorization" in self.additional_headers:
            self.renew_auth_task = asyncio.create_task(self.__schedule_renew_auth_token())

    async def shutdown(self) -> None:
        await self.close()
        if self.renew_auth_task is not None:
            self.renew_auth_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.renew_auth_task

    async def __schedule_renew_auth_token(self) -> None:
        while True:
            # get the expiration time of the current token, fallback to now
            exp = jwt_expiration(self.additional_headers.get("Authorization", "")) or datetime.now(timezone.utc)
            # next run is shortly before expiration, but at least 10 seconds away
            next_run_in = max((exp - self.renew_auth_token_before) - datetime.now(timezone.utc), timedelta(seconds=10))
            log.debug(f"Renew auth token in {next_run_in}. Going to sleep.")
            # wait until the token should be renewed
            await asyncio.sleep(next_run_in.total_seconds())
            # renew the token
            try:
                response = await self.get("/authorization/renew")
                if response.status_code == 200 and "Authorization" in response.headers:
                    log.debug("Successfully renewed auth token. Replace Authorization header.")
                    self.additional_headers["Authorization"] = response.headers["Authorization"]
                else:
                    # will be retried in 10 seconds. By default, we start 5 minutes before expiration - 12 attempts.
                    log.error(f"Failed to renew auth token: {response.status_code} {await response.text()}")
            except Exception as e:
                log.error(f"Failed to renew auth token: {e}")

    async def _ssl_context(self) -> Union[ssl.SSLContext, bool]:
        if self.get_ssl_context:
            return await self.get_ssl_context()
        else:
            return False

    async def close(self) -> None:
        await self.session.close()

    def _default_query_params(self) -> Dict[str, str]:
        return {"session_id": self.session_id}

    def _default_headers(self) -> CIMultiDict[str]:
        # default headers sent for every request
        default_headers = {
            "Content-type": "application/json",
            "Accept": "application/json",
        }
        # add auth header if psk is set
        if self.psk:
            encode_jwt_to_headers(default_headers, {}, self.psk)
        # set all user defined headers
        default_headers.update(self.additional_headers)
        return CIMultiDict(default_headers)

    async def lines(self, response: aiohttp.ClientResponse) -> AsyncIterator[bytes]:
        async for line in response.content:
            # aiohttp keeps the newline separator when iterating over the content
            # we should strip the newline as it was done in the old http client
            yield line.rstrip(b"\n")

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

        query_params = self._default_query_params()
        query_params.update(params or {})
        url = URL(self.url).with_path(path).with_query(query_params)
        request_headers = self._default_headers()
        if stream:
            request_headers.update({"Accept": "application/x-ndjson"})
        request_headers.update(headers or {})
        resp = await self.session.get(
            url, ssl=await self._ssl_context(), headers=request_headers, allow_redirects=False
        )

        return HttpResponse(
            status_code=resp.status,
            headers=resp.headers,
            text=resp.text,
            json=resp.json,
            payload_bytes=resp.read,
            async_iter_lines=lambda: self.lines(resp),
            release=resp.release,
            undrelying=resp,
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

        query_params = self._default_query_params()
        query_params.update(params or {})
        url = URL(self.url).with_path(path).with_query(query_params)
        request_headers = self._default_headers()
        if stream:
            request_headers.update({"Accept": "application/x-ndjson"})
        request_headers.update(headers or {})
        resp = await self.session.post(
            url,
            ssl=await self._ssl_context(),
            headers=request_headers,
            json=json,
            data=data,
            allow_redirects=False,
        )

        return HttpResponse(
            status_code=resp.status,
            headers=resp.headers,
            text=resp.text,
            json=resp.json,
            payload_bytes=resp.read,
            async_iter_lines=lambda: self.lines(resp),
            release=resp.release,
            undrelying=resp,
        )

    async def put(self, path: str, json: JsValue, params: Optional[Dict[str, str]] = None) -> HttpResponse:
        """
        Make a PUT request to the server.

        Args:
            path: The path to the resource.
            json: The json body to send with the request.
            params: The query parameters to add to the request.

        """

        query_params = self._default_query_params()
        query_params.update(params or {})
        url = URL(self.url).with_path(path).with_query(query_params)
        request_headers = self._default_headers()
        resp = await self.session.put(
            url, ssl=await self._ssl_context(), headers=request_headers, json=json, allow_redirects=False
        )

        return HttpResponse(
            status_code=resp.status,
            headers=resp.headers,
            text=resp.text,
            json=resp.json,
            payload_bytes=resp.read,
            async_iter_lines=lambda: self.lines(resp),
            release=resp.release,
            undrelying=resp,
        )

    async def patch(self, path: str, json: JsValue) -> HttpResponse:
        """

        Args:
            path: The path to the resource.
            json: The json body to send with the request.

        """

        url = URL(self.url).with_path(path)

        request_headers = self._default_headers()

        resp = await self.session.patch(
            url, ssl=await self._ssl_context(), headers=request_headers, json=json, allow_redirects=False
        )

        return HttpResponse(
            status_code=resp.status,
            headers=resp.headers,
            text=resp.text,
            json=resp.json,
            payload_bytes=resp.read,
            async_iter_lines=lambda: self.lines(resp),
            release=resp.release,
            undrelying=resp,
        )

    async def delete(self, path: str, params: Optional[Dict[str, str]]) -> HttpResponse:
        """

        Args:
            path: The path to the resource.
            params: The query parameters to add to the request.

        """

        query_params = self._default_query_params()
        query_params.update(params or {})
        url = URL(self.url).with_path(path).with_query(query_params)
        request_headers = self._default_headers()
        resp = await self.session.delete(
            url, ssl=await self._ssl_context(), headers=request_headers, allow_redirects=False
        )

        return HttpResponse(
            status_code=resp.status,
            headers=resp.headers,
            text=resp.text,
            json=resp.json,
            payload_bytes=resp.read,
            async_iter_lines=lambda: self.lines(resp),
            release=resp.release,
            undrelying=resp,
        )

    @asynccontextmanager
    async def websocket(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        send_queue: Optional[Queue[Union[str, JsObject]]] = None,
    ) -> AsyncIterator[Queue[Union[str, PoisonPill]]]:
        async with self.session.ws_connect(  # type: ignore
            URL(self.url).with_path(path).with_query(params or {}),
            headers=self._default_headers(),
            ssl=await self._ssl_context(),
        ) as ws:
            out_queue: Queue[Union[str, PoisonPill]] = Queue()

            async def receive() -> None:
                try:
                    async for msg in ws:
                        if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED):  # type: ignore
                            break
                        elif msg.type == WSMsgType.TEXT and len(msg.data.strip()) > 0:  # type: ignore
                            await out_queue.put(msg.data)  # type: ignore
                except Exception as ex:
                    # do not allow any exception - it will destroy the async fiber and cleanup
                    log.info(f"Receive: Exception during receive: {ex}. Hang up.")
                finally:
                    await close_ws()

            async def send(queue: Queue[Union[str, JsObject]]) -> None:
                try:
                    while True:
                        elem = await queue.get()
                        str_elem = json.dumps(elem) if isinstance(elem, dict) else elem
                        await ws.send_str(str_elem + "\n")  # type: ignore
                except Exception as ex:
                    # do not allow any exception - it will destroy the async fiber and cleanup
                    log.info(f"Send: Exception during send: {ex}. Hang up.")
                finally:
                    await close_ws()

            rt = asyncio.create_task(receive())
            to_wait = asyncio.gather(rt, asyncio.create_task(send(send_queue))) if send_queue is not None else rt

            async def close_ws() -> None:
                await out_queue.put(PoisonPill())
                if not to_wait.cancelled():
                    to_wait.cancel()
                if not ws.closed:
                    await ws.close()
                with suppress(Exception):
                    await to_wait

            try:
                yield out_queue
            finally:
                await close_ws()
