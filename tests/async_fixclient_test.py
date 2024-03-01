import time
from asyncio import Queue
from typing import List, AsyncIterator, Union

from pytest import fixture, mark

from fixclient import JsObject  # type: ignore
from fixclient.async_client import FixInventoryClient


@fixture
async def core_client() -> AsyncIterator[FixInventoryClient]:
    """
    Note: adding this fixture to a test: a complete fixcore process is started.
          The fixture ensures that the underlying process has entered the ready state.
          It also ensures to clean up the process, when the test is done.
    """

    # wipe and cleanly import the test model
    client = FixInventoryClient("https://localhost:8900", psk="changeme")

    count = 10
    ready: Union[bool, str] = False
    while not ready:
        time.sleep(0.5)
        try:
            ready = await client.ready()
        except Exception as e:
            print("failed to connect", e)
            count -= 1
            if count == 0:
                raise AssertionError("Fixcore does not came up as expected")

    yield client
    await client.shutdown()


@mark.asyncio
async def test_listen_to_events(core_client: FixInventoryClient) -> None:
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
