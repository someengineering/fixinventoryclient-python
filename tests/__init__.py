"""Test suite for the fixclient package."""
from abc import ABC
from datetime import date, datetime
from typing import List, Optional, Set, Any, Dict
from collections import namedtuple

import pytest
from networkx import MultiDiGraph
from fixclient.models import Kind, Property, JsObject

import random
import string
import jsons


def utc() -> datetime:
    return datetime.utcnow()


class EdgeType:
    # This edge type defines the default relationship between resources.
    # It is the main edge type and is assumed, if no edge type is given.
    # The related graph is also used as source of truth for graph updates.
    default: str = "default"

    # This edge type defines the order of delete operations.
    # A resource can be deleted, if all outgoing resources are deleted.
    delete: str = "delete"

    # The set of all allowed edge types.
    # Note: the database schema has to be adapted to support additional edge types.
    all: Set[str] = {default, delete}


class BaseResource(ABC):
    def __init__(
        self,
        identifier: str,
    ) -> None:
        self.identifier = str(identifier)

    # this method should be defined in all resources
    def kind(self) -> str:
        return ""


class Foo(BaseResource):
    def __init__(
        self,
        identifier: str,
        name: Optional[str] = None,
        some_int: int = 0,
        some_string: str = "hello",
        now_is: datetime = utc(),
        ctime: Optional[datetime] = None,
    ) -> None:
        super().__init__(identifier)
        self.name = name
        self.some_int = some_int
        self.some_string = some_string
        self.now_is = now_is
        self.ctime = ctime

    def kind(self) -> str:
        return "foo"


class Bla(BaseResource):
    def __init__(
        self,
        identifier: str,
        name: Optional[str] = None,
        now: date = date.today(),
        f: int = 23,
        g: Optional[List[int]] = None,
    ) -> None:
        super().__init__(identifier)
        self.name = name
        self.now = now
        self.f = f
        self.g = g if g is not None else list(range(0, 5))

    def kind(self) -> str:
        return "bla"


def to_js(node: Any, **kwargs: Any) -> JsObject:
    # shortcut: assume a dict is already a json value
    if isinstance(node, dict) and not kwargs.get("force_dict", False):
        return node
    return jsons.dump(  # type: ignore
        node,
        strip_privates=True,
        strip_microseconds=True,
        strip_class_variables=True,
        **kwargs,
    )


EdgeKey = namedtuple("EdgeKey", ["from_node", "to_node", "edge_type"])


def edge_key(from_node: object, to_node: object, edge_type: str) -> EdgeKey:
    return EdgeKey(from_node, to_node, edge_type)


def create_graph(bla_text: str, width: int = 10) -> MultiDiGraph:
    graph = MultiDiGraph()

    def add_edge(from_node: str, to_node: str, edge_type: str = EdgeType.default) -> None:
        key = edge_key(from_node, to_node, edge_type)
        graph.add_edge(from_node, to_node, key, edge_type=edge_type)

    def add_node(uid: str, kind: str, node: Optional[JsObject] = None, replace: bool = False) -> None:
        reported = {**(node if node else to_json(Foo(uid))), "kind": kind}
        graph.add_node(
            uid,
            id=uid,
            kinds=[kind],
            reported=reported,
            desired={"node_id": uid},
            metadata={"node_id": uid},
            replace=replace,
        )

    # root -> collector -> sub_root -> **rest
    add_node("root", "graph_root")
    add_node("collector", "cloud", replace=True)
    add_node("sub_root", "foo")
    add_edge("root", "collector")
    add_edge("collector", "sub_root")

    for o in range(0, width):
        oid = str(o)
        add_node(oid, "foo")
        add_edge("sub_root", oid)
        for i in range(0, width):
            iid = f"{o}_{i}"
            add_node(iid, "bla", node=to_json(Bla(iid, name=bla_text)))
            add_edge(oid, iid)
            add_edge(iid, oid, EdgeType.delete)
    return graph


def create_multi_collector_graph(width: int = 3) -> MultiDiGraph:
    graph = MultiDiGraph()

    def add_edge(from_node: str, to_node: str, edge_type: str = EdgeType.default) -> None:
        key = edge_key(from_node, to_node, edge_type)
        graph.add_edge(from_node, to_node, key, edge_type=edge_type)

    def add_node(node_id: str, kind: str, replace: bool = False) -> str:
        reported = {
            **to_json(Foo(node_id)),
            "id": node_id,
            "name": node_id,
            "kind": kind,
        }
        graph.add_node(
            node_id,
            id=node_id,
            reported=reported,
            desired={},
            metadata={},
            hash="123",
            replace=replace,
            kind=kind,
            kinds=[kind],
            kinds_set={kind},
        )
        return node_id

    root = add_node("root", "graph_root")
    for cloud_num in range(0, 2):
        cloud = add_node(f"cloud_{cloud_num}", "cloud")
        add_edge(root, cloud)
        for account_num in range(0, 2):
            aid = f"{cloud_num}:{account_num}"
            account = add_node(f"account_{aid}", "account")
            add_edge(cloud, account)
            add_edge(account, cloud, EdgeType.delete)
            for region_num in range(0, 2):
                rid = f"{aid}:{region_num}"
                region = add_node(f"region_{rid}", "region", replace=True)
                add_edge(account, region)
                add_edge(region, account, EdgeType.delete)
                for parent_num in range(0, width):
                    pid = f"{rid}:{parent_num}"
                    parent = add_node(f"parent_{pid}", "parent")
                    add_edge(region, parent)
                    add_edge(parent, region, EdgeType.delete)
                    for child_num in range(0, width):
                        cid = f"{pid}:{child_num}"
                        child = add_node(f"child_{cid}", "child")
                        add_edge(parent, child)
                        add_edge(child, parent, EdgeType.delete)

    return graph


@pytest.fixture
def foo_kinds() -> List[Kind]:
    base = Kind(
        fqn="base",
        runtime_kind=None,
        bases=[],
        properties=[
            Property("identifier", "string", required=True),
            Property("kind", "string", required=True),
            Property("ctime", "datetime"),
        ],
    )
    foo = Kind(
        fqn="foo",
        aggregate_root=True,
        runtime_kind=None,
        bases=["base"],
        properties=[
            Property("name", "string"),
            Property("some_int", "int32"),
            Property("some_string", "string"),
            Property("now_is", "datetime"),
            Property("ctime", "datetime"),
            Property("age", "trafo.duration_to_datetime", False),
        ],
    )
    bla = Kind(
        fqn="bla",
        aggregate_root=True,
        runtime_kind=None,
        bases=["base"],
        properties=[
            Property("name", "string"),
            Property("now", "date"),
            Property("f", "int32"),
            Property("g", "int32[]"),
        ],
    )
    cloud = Kind(fqn="cloud", runtime_kind=None, bases=["foo"], properties=[], aggregate_root=True)
    account = Kind(fqn="account", runtime_kind=None, bases=["foo"], properties=[], aggregate_root=True)
    region = Kind(fqn="region", runtime_kind=None, bases=["foo"], properties=[], aggregate_root=True)
    parent = Kind(fqn="parent", runtime_kind=None, bases=["foo"], properties=[], aggregate_root=True)
    child = Kind(fqn="child", runtime_kind=None, bases=["foo"], properties=[], aggregate_root=True)
    return [base, foo, bla, cloud, account, region, parent, child]


def to_json(obj: BaseResource) -> Dict[str, Any]:
    return {"kind": obj.kind(), **to_js(obj)}


def rnd_str(str_len: int = 10) -> str:
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(str_len))
