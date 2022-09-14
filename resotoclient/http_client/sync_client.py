from resotoclient.http_client.event_loop_thread import EventLoopThread
from resotoclient.http_client import AsyncHttpClient, HttpResponse
from typing import Dict, Optional
from resotoclient.models import JsValue


class SyncHttpClient:
    """
    A syncronous HTTP client that wraps an async client.

    This is useful for when you want to use an async HTTP client in a syncronous context.

    Be sure to call start() before using the client and stop() when you are done.
    """

    def __init__(self, async_client: AsyncHttpClient):
        self.async_client = async_client
        self.event_loop_thread = EventLoopThread()
        self.running = False

    def start(self):
        self.event_loop_thread.start()
        self.running = True

    def stop(self):
        self.event_loop_thread.stop()
        self.running = False

    def get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        if not self.running:
            raise Exception("EventLoop thread is not running. Call start() before using the client.")
        return self.event_loop_thread.run_coroutine(self.async_client.get(path, params, headers, stream))

    def post(
        self,
        path: str,
        json: Optional[JsValue] = None,
        data: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        if not self.running:
            raise Exception("EventLoop thread is not running. Call start() before using the client.")
        return self.event_loop_thread.run_coroutine(self.async_client.post(path, json, data, params, headers, stream))

    def put(self, path: str, json: JsValue, params: Optional[Dict[str, str]] = None) -> HttpResponse:
        if not self.running:
            raise Exception("EventLoop thread is not running. Call start() before using the client.")
        return self.event_loop_thread.run_coroutine(self.async_client.put(path, json, params))

    def patch(self, path: str, json: JsValue) -> HttpResponse:
        if not self.running:
            raise Exception("EventLoop thread is not running. Call start() before using the client.")
        return self.event_loop_thread.run_coroutine(self.async_client.patch(path, json))

    def delete(self, path: str, params: Optional[Dict[str, str]]) -> HttpResponse:
        if not self.running:
            raise Exception("EventLoop thread is not running. Call start() before using the client.")
        return self.event_loop_thread.run_coroutine(self.async_client.delete(path, params))
