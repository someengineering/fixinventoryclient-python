import time
from asyncio import Queue
from typing import List, AsyncIterator

from pytest import fixture, mark

from resotoclient import JsObject
from resotoclient.async_client import ResotoClient


@fixture
async def core_client() -> AsyncIterator[ResotoClient]:
    """
    Note: adding this fixture to a test: a complete resotocore process is started.
          The fixture ensures that the underlying process has entered the ready state.
          It also ensures to clean up the process, when the test is done.
    """

    # wipe and cleanly import the test model
    client = ResotoClient("https://localhost:8900", psk="changeme")

    count = 10
    ready = False
    while not ready:
        time.sleep(0.5)
        try:
            ready = await client.ready()
        except Exception as e:
            print("failed to connect", e)
            count -= 1
            if count == 0:
                raise AssertionError("Resotocore does not came up as expected")

    yield client
    await client.shutdown()


@mark.asyncio
async def test_listen_to_events(core_client: ResotoClient) -> None:
    received: List[JsObject] = []
    send_queue: Queue[JsObject] = Queue()
    messages: List[JsObject] = [dict(kind="event", message_type="test", data={"foo": i}) for i in range(5)]
    for msg in messages:
        # add some messages that should be ignored - we are only listening for test events
        await send_queue.put(dict(kind="event", message_type="ignore_me"))
        await send_queue.put(msg)
    async for event in core_client.events({"test"}, send_queue):
        event["data"].pop("received_at", None)  # type: ignore
        received.append(event)
        if len(received) == len(messages):
            break
    assert received == messages
