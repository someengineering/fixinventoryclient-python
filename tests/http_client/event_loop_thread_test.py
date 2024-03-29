from fixclient.http_client.event_loop_thread import EventLoopThread
import asyncio


def test_event_loop_thread() -> None:
    async def foo() -> int:
        await asyncio.sleep(0.1)
        return 42

    thread = EventLoopThread()
    thread.start()
    assert thread.run_coroutine(foo()) == 42
    thread.stop()
    assert thread.running is False
