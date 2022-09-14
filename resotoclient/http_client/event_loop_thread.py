import asyncio
import threading
from typing import Awaitable, TypeVar, Any, Dict

T = TypeVar("T")


class EventLoopThread(threading.Thread):
    """
    A thread that runs an asyncio event loop.

    This is useful for running async code in a synchronous context,
    without creating an event loop every time a result from an async function is needed.

    Start the thread before making async calls, and stop it when you're done.

    Example:

    >>> from resotoclient.event_loop_thread import EventLoopThread
    thread = EventLoopThread()
    thread.start()
    thread.run_coroutine(async_function())
    thread.stop()
    """

    def __init__(self, *args: Any, **kwargs: Dict[str, Any]):
        super().__init__(*args, **kwargs)
        self.loop = asyncio.new_event_loop()
        self.running = False

    def run(self):
        self.running = True
        self.loop.run_forever()

    def run_coroutine(self, coroutine: Awaitable[T]) -> T:
        """
        Run a coroutine in the event loop thread, block till completeion and return the result.
        """
        return asyncio.run_coroutine_threadsafe(coroutine, loop=self.loop).result()

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.join()
        self.running = False
