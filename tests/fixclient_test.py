from contextlib import suppress
from typing import List, AsyncIterator

import pytest
from pytest import fixture

from aiohttp import ClientSession
import time

# noinspection PyUnresolvedReferences
from tests import foo_kinds, create_graph, rnd_str
from fixclient import FixInventoryClient
from fixclient import models as rc
from networkx import MultiDiGraph


def graph_to_json(graph: MultiDiGraph) -> List[rc.JsObject]:
    ga: List[rc.JsObject] = [{**node, "type": "node"} for _, node in graph.nodes(data=True)]
    for from_node, to_node, data in graph.edges(data=True):
        ga.append(
            {
                "type": "edge",
                "from": from_node,
                "to": to_node,
                "edge_type": data["edge_type"],
            }
        )
    return ga


@fixture
async def core_client(foo_kinds: List[rc.Kind]) -> AsyncIterator[FixInventoryClient]:
    """
    Note: adding this fixture to a test: a complete fixcore process is started.
          The fixture ensures that the underlying process has entered the ready state.
          It also ensures to clean up the process, when the test is done.
    """

    async def core_ready() -> bool:
        async with ClientSession() as session:
            async with session.get("https://localhost:8900/system/ready", ssl=False) as resp:
                return resp.status == 200

    # test_db.collection("model").truncate()
    # to_insert = [{"_key": elem.fqn, **to_js(elem)} for elem in foo_kinds]
    # test_db.collection("model").insert_many(to_insert)
    # {'_key': 'child', 'allow_unknown_props': False, 'bases': ['foo'], 'fqn': 'child', 'properties': []}
    # {'_key': 'child', 'bases': ['foo'], 'fqn': 'child', 'properties': [], 'runtime_kind': None}
    count = 10
    ready = False
    while not ready:
        time.sleep(0.5)
        try:
            ready = await core_ready()
        except Exception:
            count -= 1
            if count == 0:
                raise AssertionError("Fixcore does not came up as expected")

    # wipe and cleanly import the test model
    client = FixInventoryClient("https://localhost:8900", psk="changeme")

    # chech that connection is possible
    list(client.cli_execute("system info"))

    # fix is the default name of the graph for many calls
    # let's create it first
    client.create_graph("fix")
    client.update_model(foo_kinds)
    # graphtest needs to have the model too.
    client.create_graph(g)
    client.update_model(foo_kinds, g)

    yield client

    client.shutdown()


g = "graphtest"


def test_system_api(core_client: FixInventoryClient) -> None:
    assert core_client.ping() == "pong"
    assert core_client.ready() == "ok"
    # make sure we get redirected to the api docs


def test_model_api(core_client: FixInventoryClient) -> None:
    # PATCH /model
    string_kind: rc.Kind = rc.Kind(fqn="only_three", runtime_kind="string", properties=None, bases=None)
    setattr(string_kind, "min_length", 3)
    setattr(string_kind, "max_length", 3)

    prop = rc.Property(name="ot", kind="only_three", required=False)
    complex_kind: rc.Kind = rc.Kind(fqn="test_cpl", runtime_kind=None, properties=[prop], bases=None)
    setattr(complex_kind, "allow_unknown_props", False)

    update = core_client.update_model([string_kind, complex_kind])
    none_kind = rc.Kind(fqn="none", runtime_kind=None, properties=None, bases=None)
    assert (update.kinds.get("only_three") or none_kind).runtime_kind == "string"


def test_graph_api(core_client: FixInventoryClient) -> None:
    # make sure we have a clean slate
    with suppress(Exception):
        core_client.delete_graph(g)

    # create a new graph
    graph = core_client.create_graph(g)
    assert graph["id"] == "root"
    assert graph["reported"]["kind"] == "graph_root"  # type: ignore

    # list all graphs
    graphs = core_client.list_graphs()
    assert g in graphs

    # get one specific graph
    graph = core_client.get_graph(g) or {}
    assert graph["id"] == "root"
    assert graph["reported"]["kind"] == "graph_root"  # type: ignore

    # wipe the data in the graph
    assert core_client.delete_graph(g, truncate=True) == "Graph truncated."
    assert g in core_client.list_graphs()

    # create a node in the graph
    uid = rnd_str()
    node = core_client.create_node("root", uid, {"identifier": uid, "kind": "child", "name": "max"}, g)

    assert node["id"] == uid
    assert node["reported"]["name"] == "max"  # type: ignore

    # update a node in the graph
    node = core_client.patch_node(uid, {"name": "moritz"}, "reported", g)
    assert node["id"] == uid
    assert node["reported"]["name"] == "moritz"  # type: ignore

    # get the node
    node = core_client.get_node(uid, g)
    assert node["id"] == uid
    assert node["reported"]["name"] == "moritz"  # type: ignore

    # delete the node
    core_client.delete_node(uid, g)
    with pytest.raises(AttributeError):
        # node can not be found
        core_client.get_node(uid, g)

    # merge a complete graph
    merged = core_client.merge_graph(graph_to_json(create_graph("test")), g)
    assert merged == rc.GraphUpdate(112, 1, 0, 212, 0, 0)

    # batch graph update and commit
    batch1_id, batch1_info = core_client.add_to_batch(graph_to_json(create_graph("hello")), "batch1", g)
    assert batch1_info == rc.GraphUpdate(0, 100, 0, 0, 0, 0)
    assert batch1_id == "batch1"
    batch_infos = core_client.list_batches(g)
    assert len(batch_infos) == 1
    # assert batch_infos[0].id == batch1_id
    assert batch_infos[0]["affected_nodes"] == ["collector"]  # replace node
    assert batch_infos[0]["is_batch"] is True
    core_client.commit_batch(batch1_id, g)

    # batch graph update and abort
    batch2_id, batch2_info = core_client.add_to_batch(graph_to_json(create_graph("bonjour")), "batch2", g)
    assert batch2_info == rc.GraphUpdate(0, 100, 0, 0, 0, 0)
    assert batch2_id == "batch2"
    core_client.abort_batch(batch2_id, g)

    # update nodes
    update: List[rc.JsObject] = [
        {"id": node["id"], "reported": {"name": "bruce"}} for _, node in create_graph("foo").nodes(data=True)
    ]
    updated_nodes = core_client.patch_nodes(update, g)
    assert len(updated_nodes) == 113
    for n in updated_nodes:
        assert n.get("reported", {}).get("name") == "bruce"  # type: ignore

    # estimate the search
    cost = core_client.search_graph_explain('id("3")', g)
    assert cost.full_collection_scan is False
    assert cost.rating == rc.EstimatedQueryCostRating.simple

    # search list
    result_list = list(core_client.search_list('id("3") -[0:]->', graph=g))
    assert len(result_list) == 11  # one parent node and 10 child nodes
    assert result_list[0].get("id") == "3"  # first node is the parent node

    # search graph
    result_graph = list(core_client.search_graph('id("3") -[0:]->', graph=g))
    assert len(result_graph) == 21  # 11 nodes + 10 edges
    assert result_list[0].get("id") == "3"  # first node is the parent node

    # aggregate
    result_aggregate = core_client.search_aggregate("aggregate(kind as kind: sum(1) as count): all", graph=g)
    assert {r["group"]["kind"]: r["count"] for r in result_aggregate} == {  # type: ignore
        "bla": 100,
        "cloud": 1,
        "foo": 11,
        "graph_root": 1,
    }

    # delete the graph
    assert core_client.delete_graph(g) == "Graph deleted."
    assert g not in core_client.list_graphs()


def test_subscribers(core_client: FixInventoryClient) -> None:
    # provide a clean slate
    for subscriber in core_client.subscribers():
        core_client.delete_subscriber(subscriber.id)

    sub_id = rnd_str()

    # add subscription
    subscriber = core_client.add_subscription(sub_id, rc.Subscription("test"))
    assert subscriber.id == sub_id
    assert len(subscriber.subscriptions) == 1
    assert subscriber.subscriptions["test"] is not None

    # delete subscription
    subscriber = core_client.delete_subscription(sub_id, rc.Subscription("test"))
    assert subscriber.id == sub_id
    assert len(subscriber.subscriptions) == 0

    # update subscriber
    updated = core_client.update_subscriber(sub_id, [rc.Subscription("test"), rc.Subscription("rest")])
    assert updated is not None
    assert updated.id == sub_id
    assert len(updated.subscriptions) == 2

    # subscriber for message type
    assert core_client.subscribers_for_event("test") == [updated]
    assert core_client.subscribers_for_event("rest") == [updated]
    assert core_client.subscribers_for_event("does_not_exist") == []

    # get subscriber
    sub = core_client.subscriber(sub_id)
    assert sub is not None


def test_cli(core_client: FixInventoryClient) -> None:
    # make sure we have a clean slate
    with suppress(Exception):
        core_client.delete_graph(g)
    core_client.create_graph(g)
    graph_update = graph_to_json(create_graph("test"))
    core_client.merge_graph(graph_update, g)

    # evaluate search with count
    result = core_client.cli_evaluate("search all | count kind", g)
    assert len(result) == 1
    parsed, to_execute = result[0]
    assert len(parsed.commands) == 2
    assert (parsed.commands[0].cmd, parsed.commands[1].cmd) == ("search", "count")
    assert len(to_execute) == 3
    assert (to_execute[0].get("cmd"), to_execute[1].get("cmd")) == (
        "execute_search",
        "aggregate_to_count",
    )

    # execute search with count
    executed = list(core_client.cli_execute("search is(foo) or is(bla) | count kind", g))
    assert executed == [
        "cloud: 1",
        "foo: 11",
        "bla: 100",
        "total matched: 112",
        "total unmatched: 0",
    ]

    # make sure non latin characters are handled correctly
    assert list(core_client.cli_execute('search is(foo) and id="我的第"', g)) == []


def test_config(core_client: FixInventoryClient, foo_kinds: List[rc.Kind]) -> None:
    # make sure we have a clean slate
    for config in core_client.configs():
        core_client.delete_config(config)

    # define a config model
    model = core_client.update_configs_model(foo_kinds)
    assert "foo" in model.kinds
    assert "bla" in model.kinds
    # get the config model again
    get_model = core_client.get_configs_model()
    assert len(model.kinds) == len(get_model.kinds)

    # define config validation
    validation = rc.ConfigValidation("external.validated.config", external_validation=True)
    assert core_client.put_config_validation(validation) == validation

    # get the config validation
    assert core_client.get_config_validation(validation.id) == validation

    # put config
    cfg_id = rnd_str()

    # put a config with schema that is violated
    with pytest.raises(AttributeError) as ex:
        core_client.put_config(cfg_id, {"foo": {"some_int": "abc"}})
    assert "Expected type int32 but got str" in str(ex.value)

    # put a config with schema that is violated, but turn validation off
    core_client.put_config(cfg_id, {"foo": {"some_int": "abc"}}, validate=False)

    # set a simple state
    assert core_client.put_config(cfg_id, {"a": 1}) == {"a": 1}

    # patch config
    assert core_client.patch_config(cfg_id, {"a": 1}) == {"a": 1}
    assert core_client.patch_config(cfg_id, {"b": 2}) == {"a": 1, "b": 2}
    assert core_client.patch_config(cfg_id, {"c": 3}) == {"a": 1, "b": 2, "c": 3}

    # get config
    assert core_client.config(cfg_id) == {"a": 1, "b": 2, "c": 3}

    # list configs
    assert list(core_client.configs()) == [cfg_id]

    # delete config
    core_client.delete_config(cfg_id)
    assert list(core_client.configs()) == []
