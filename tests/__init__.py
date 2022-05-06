"""Test suite for the resotoclient package."""
from abc import ABC
from datetime import date, datetime
from typing import List, Optional

import pytest
from arango import ArangoClient
from arango.database import StandardDatabase
from arango.typings import Json
from networkx import MultiDiGraph

from resotocore.db.graphdb import GraphDB

from resotocore.db.model import QueryModel
from resotocore.model.graph_access import GraphAccess, EdgeType
from resotocore.model.model import Model, ComplexKind, Property, Kind, SyntheticProperty
from resotocore.model.typed_model import from_js, to_js
from resotocore.query.model import Query, P, Navigation
from resotocore.util import utc


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


def create_graph(bla_text: str, width: int = 10) -> MultiDiGraph:
    graph = MultiDiGraph()

    def add_edge(
        from_node: str, to_node: str, edge_type: str = EdgeType.default
    ) -> None:
        key = GraphAccess.edge_key(from_node, to_node, edge_type)
        graph.add_edge(from_node, to_node, key, edge_type=edge_type)  # type: ignore

    def add_node(
        uid: str, kind: str, node: Optional[Json] = None, replace: bool = False
    ) -> None:
        reported = {**(node if node else to_json(Foo(uid))), "kind": kind}
        graph.add_node(  # type: ignore
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

    def add_edge(
        from_node: str, to_node: str, edge_type: str = EdgeType.default
    ) -> None:
        key = GraphAccess.edge_key(from_node, to_node, edge_type)
        graph.add_edge(from_node, to_node, key, edge_type=edge_type)  # type: ignore

    def add_node(node_id: str, kind: str, replace: bool = False) -> str:
        reported = {
            **to_json(Foo(node_id)),
            "id": node_id,
            "name": node_id,
            "kind": kind,
        }
        graph.add_node(  # type: ignore
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
    base = ComplexKind(
        "base",
        [],
        [
            Property("identifier", "string", required=True),
            Property("kind", "string", required=True),
            Property("ctime", "datetime"),
        ],
    )
    foo = ComplexKind(
        "foo",
        ["base"],
        [
            Property("name", "string"),
            Property("some_int", "int32"),
            Property("some_string", "string"),
            Property("now_is", "datetime"),
            Property("ctime", "datetime"),
            Property(
                "age", "trafo.duration_to_datetime", False, SyntheticProperty(["ctime"])
            ),
        ],
    )
    bla = ComplexKind(
        "bla",
        ["base"],
        [
            Property("name", "string"),
            Property("now", "date"),
            Property("f", "int32"),
            Property("g", "int32[]"),
        ],
    )
    cloud = ComplexKind("cloud", ["foo"], [])
    account = ComplexKind("account", ["foo"], [])
    region = ComplexKind("region", ["foo"], [])
    parent = ComplexKind("parent", ["foo"], [])
    child = ComplexKind("child", ["foo"], [])
    return [base, foo, bla, cloud, account, region, parent, child]


@pytest.fixture
def foo_model(foo_kinds: List[Kind]) -> Model:
    return Model.from_kinds(foo_kinds)


@pytest.fixture
def local_client() -> ArangoClient:
    return ArangoClient(hosts="http://localhost:8529")


@pytest.fixture
def system_db(local_client: ArangoClient) -> StandardDatabase:
    return local_client.db()


@pytest.fixture
def test_db(
    local_client: ArangoClient, system_db: StandardDatabase
) -> StandardDatabase:
    if not system_db.has_user("test"):
        system_db.create_user("test", "test", True)

    if not system_db.has_database("test"):
        system_db.create_database(
            "test", [{"username": "test", "password": "test", "active": True}]
        )

    # Connect to "test" database as "test" user.
    return local_client.db("test", username="test", password="test")


async def load_graph(
    db: GraphDB, model: Model, base_id: str = "sub_root"
) -> MultiDiGraph:
    blas = Query.by("foo", P("identifier") == base_id).traverse_out(0, Navigation.Max)
    return await db.search_graph(QueryModel(blas.on_section("reported"), model))


def to_json(obj: BaseResource) -> Json:
    return {"kind": obj.kind(), **to_js(obj)}


def to_bla(json: Json) -> Bla:
    return from_js(json["reported"], Bla)


def to_foo(json: Json) -> Foo:
    return from_js(json["reported"], Foo)
