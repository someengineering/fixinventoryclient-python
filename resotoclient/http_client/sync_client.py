from resotoclient.http_client.event_loop_thread import EventLoopThread
from resotoclient.http_client.aiohttp_client import AioHttpClient
from typing import Dict, Optional, Callable, Mapping, Iterator, AsyncIterator, Any, Awaitable
from resotoclient.models import JsValue
import aiohttp
from attrs import define
from ssl import SSLContext

@define
class HttpResponse:
    """
    An abstraction of an HTTP response to hide the underlying HTTP client implementation.

    Attributes:
        status_code: The HTTP status code of the response.
        headers: The HTTP headers of the response.
        text: A function that returns response body as a string.
        json: A function that returns response body as a JSON object.
        iter_lines: A function that returns the iterator of the response body, present if streaming was requested in a async client.
        release: Release the resources associated with the response if it is no longer needed, e.g. during streaming a streamed.
    """

    status_code: int
    headers: Mapping[str, str]
    text: Callable[[], str]
    json: Callable[[], Any]
    iter_lines: Callable[[], Iterator[bytes]]
    release: Callable[[], None]


class SyncHttpClient:
    """
    A syncronous HTTP client that wraps an async client.

    This is useful for when you want to use an async HTTP client in a syncronous context.

    Be sure to call start() before using the client and stop() when you are done.
    """

    def __init__(
        self,
        url: str,
        psk: Optional[str],
        session_id: str,
        get_ssl_context: Optional[Callable[[], Awaitable[SSLContext]]] = None,
    ):
        self.event_loop_thread = EventLoopThread()
        self.event_loop_thread.daemon = True
        self.url = url
        self.psk = psk
        self.get_ssl_context = get_ssl_context
        self.session_id = session_id
        self.async_client = None

    def running(self) -> bool:
        return self.async_client is not None

    def ensure_running(self):
        if not self.running():
            self.start()

    def start(self):
        self.event_loop_thread.start()
        import time

        while not self.event_loop_thread.running:
            time.sleep(0.1)
        client_session = aiohttp.ClientSession(loop=self.event_loop_thread.loop)
        self.async_client = AioHttpClient(
            self.url, self.psk, self.session_id, self.get_ssl_context, client_session
        )

    def stop(self):
        if self.async_client:
            self.event_loop_thread.run_coroutine(self.async_client.session.close())
        self.event_loop_thread.stop()

    def _asynciter_to_iter(self, async_iter: AsyncIterator[bytes]) -> Iterator[bytes]:
        while True:
            try:
                yield self.event_loop_thread.run_coroutine(async_iter.__anext__())
            except StopAsyncIteration:
                break

    def get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        if not self.async_client:
            raise Exception(
                "EventLoop thread is not running. Call start() before using the client."
            )
        resp = self.event_loop_thread.run_coroutine(
            self.async_client.get(path, params, headers, stream)
        )

        return HttpResponse(
            status_code=resp.status_code,
            headers=resp.headers,
            text=lambda: self.event_loop_thread.run_coroutine(resp.text()),
            json=lambda: self.event_loop_thread.run_coroutine(resp.json()),
            iter_lines=lambda: self._asynciter_to_iter(resp.async_iter_lines()),
            release=resp.release,
        )

    def post(
        self,
        path: str,
        json: Optional[JsValue] = None,
        data: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        if not self.async_client:
            raise Exception(
                "EventLoop thread is not running. Call start() before using the client."
            )
        resp = self.event_loop_thread.run_coroutine(
            self.async_client.post(path, json, data, params, headers, stream)
        )
        return HttpResponse(
            status_code=resp.status_code,
            headers=resp.headers,
            text=lambda: self.event_loop_thread.run_coroutine(resp.text()),
            json=lambda: self.event_loop_thread.run_coroutine(resp.json()),
            iter_lines=lambda: self._asynciter_to_iter(resp.async_iter_lines()),
            release=resp.release,
        )

    def put(
        self, path: str, json: JsValue, params: Optional[Dict[str, str]] = None
    ) -> HttpResponse:
        if not self.async_client:
            raise Exception(
                "EventLoop thread is not running. Call start() before using the client."
            )
        resp = self.event_loop_thread.run_coroutine(
            self.async_client.put(path, json, params)
        )
        return HttpResponse(
            status_code=resp.status_code,
            headers=resp.headers,
            text=lambda: self.event_loop_thread.run_coroutine(resp.text()),
            json=lambda: self.event_loop_thread.run_coroutine(resp.json()),
            iter_lines=lambda: self._asynciter_to_iter(resp.async_iter_lines()),
            release=resp.release,
        )

    def patch(self, path: str, json: JsValue) -> HttpResponse:
        if not self.async_client:
            raise Exception(
                "EventLoop thread is not running. Call start() before using the client."
            )
        resp = self.event_loop_thread.run_coroutine(self.async_client.patch(path, json))
        return HttpResponse(
            status_code=resp.status_code,
            headers=resp.headers,
            text=lambda: self.event_loop_thread.run_coroutine(resp.text()),
            json=lambda: self.event_loop_thread.run_coroutine(resp.json()),
            iter_lines=lambda: self._asynciter_to_iter(resp.async_iter_lines()),
            release=resp.release,
        )

    def delete(self, path: str, params: Optional[Dict[str, str]]) -> HttpResponse:
        if not self.async_client:
            raise Exception(
                "EventLoop thread is not running. Call start() before using the client."
            )
        resp = self.event_loop_thread.run_coroutine(
            self.async_client.delete(path, params)
        )
        return HttpResponse(
            status_code=resp.status_code,
            headers=resp.headers,
            text=lambda: self.event_loop_thread.run_coroutine(resp.text()),
            json=lambda: self.event_loop_thread.run_coroutine(resp.json()),
            iter_lines=lambda: self._asynciter_to_iter(resp.async_iter_lines()),
            release=resp.release,
        )
