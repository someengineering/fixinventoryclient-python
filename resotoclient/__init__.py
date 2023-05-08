import logging
from typing import (
    Any,
    Dict,
    Iterator,
    Set,
    Optional,
    List,
    Tuple,
    Sequence,
    Mapping,
    Type,
    AsyncIterator,
    TypeVar,
    Awaitable,
    Callable,
    cast,
)
from types import TracebackType
from resotoclient.models import (
    Subscriber,
    Subscription,
    ParsedCommands,
    GraphUpdate,
    EstimatedSearchCost,
    ConfigValidation,
    JsObject,
    JsValue,
    Model,
    Kind,
)
from resotoclient.async_client import ResotoClient as AsyncResotoClient
from resotoclient.http_client.event_loop_thread import EventLoopThread
import random
import string
from datetime import timedelta
import atexit
import threading
import sys
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict
from attrs import define

try:
    from pandas import DataFrame  # type: ignore
    import pandas as pd  # type: ignore
except ImportError:
    DataFrame = None
try:
    from graphviz import Digraph  # type: ignore
except ImportError:
    Digraph = None


FilenameLookup = Dict[str, str]

log: logging.Logger = logging.getLogger("resotoclient")


@define
class HttpResponse:
    """
    An abstraction of an HTTP response to hide the underlying HTTP client implementation.

    Attributes:
        status_code: The HTTP status code of the response.
        headers: The HTTP headers of the response.
        text: A function that returns response body as a string.
        json: A function that returns response body as a JSON object.
        payload_bytes: A function that returns response body as a byte array.
        iter_lines: A function that returns the iterator of the response body, present if streaming was requested in a async client.
        release: Release the resources associated with the response if it is no longer needed, e.g. during streaming a streamed.
    """

    status_code: int
    headers: Mapping[str, str]
    text: Callable[[], str]
    json: Callable[[], Any]
    payload_bytes: Callable[[], bytes]
    iter_lines: Callable[[], Iterator[bytes]]
    release: Callable[[], None]

    def __enter__(self) -> "HttpResponse":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.release()


class ClientState(Enum):
    INITIALIZED = 0
    STARTED = 1
    STOPPED = 2


T = TypeVar("T")


class ResotoClient:
    """
    The ApiClient interacts with a running core instance via the REST interface.
    """

    def __init__(
        self,
        url: str,
        *,
        psk: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
        custom_ca_cert_path: Optional[str] = None,
        verify: bool = True,
        renew_certificate_before: timedelta = timedelta(days=1),
        renew_auth_token_before: timedelta = timedelta(minutes=5),
    ):
        self.resotocore_url = url
        self.psk = psk
        self.additional_headers = additional_headers
        self.custom_ca_cert_path = custom_ca_cert_path
        self.verify = verify
        self.renew_certificate_before = renew_certificate_before
        self.renew_auth_token_before = renew_auth_token_before
        self.event_loop_thread = EventLoopThread()
        self.event_loop_thread.daemon = True
        atexit.register(self.shutdown)

        self.state_lock = threading.Lock()
        self.client_state = ClientState.INITIALIZED

        self.async_client = None

    def __enter__(self) -> "ResotoClient":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.shutdown()

    def start(self) -> None:
        with self.state_lock:
            if self.client_state != ClientState.INITIALIZED:
                return

            self.event_loop_thread.start()
            import time

            while not self.event_loop_thread.running:
                time.sleep(0.05)

            self.async_client = AsyncResotoClient(
                url=self.resotocore_url,
                psk=self.psk,
                additional_headers=self.additional_headers,
                custom_ca_cert_path=self.custom_ca_cert_path,
                verify=self.verify,
                renew_certificate_before=self.renew_certificate_before,
                renew_auth_token_before=self.renew_auth_token_before,
                loop=self.event_loop_thread.loop,
            )

            self.event_loop_thread.run_coroutine(self.async_client.start())

            self.client_state = ClientState.STARTED

    def shutdown(self) -> None:
        with self.state_lock:
            if self.client_state != ClientState.STARTED:
                return

            if self.async_client:
                self.event_loop_thread.run_coroutine(self.async_client.shutdown())

            self.event_loop_thread.stop()
            self.client_state = ClientState.STOPPED

    def _asynciter_to_iter(self, async_iter: AsyncIterator[T]) -> Iterator[T]:
        while True:
            try:
                yield self.event_loop_thread.run_coroutine(async_iter.__anext__())
            except StopAsyncIteration:
                break

    def _await(self, awaitable: Callable[[AsyncResotoClient], Awaitable[T]]) -> T:
        # a cheap check to not invoke the state lock
        if self.client_state == ClientState.INITIALIZED:
            self.start()

        if self.async_client:
            return self.event_loop_thread.run_coroutine(awaitable(self.async_client))
        else:
            raise RuntimeError("Client was not found")

    def _iterator(self, async_iter: Callable[[AsyncResotoClient], AsyncIterator[T]]) -> Iterator[T]:
        # a cheap check to not invoke the state lock
        if self.client_state == ClientState.INITIALIZED:
            self.start()

        if self.async_client:
            return self._asynciter_to_iter(async_iter(self.async_client))
        else:
            raise RuntimeError("Client was not found")

    def model(self) -> Model:
        return self._await(lambda c: c.model())

    def update_model(self, update: List[Kind]) -> Model:
        return self._await(lambda c: c.update_model(update))

    def list_graphs(self) -> Set[str]:
        return self._await(lambda c: c.list_graphs())

    def get_graph(self, name: str) -> Optional[JsObject]:
        return self._await(lambda c: c.get_graph(name))

    def create_graph(self, name: str) -> JsObject:
        return self._await(lambda c: c.create_graph(name))

    def delete_graph(self, name: str, truncate: bool = False) -> str:
        return self._await(lambda c: c.delete_graph(name, truncate))

    def create_node(self, parent_node_id: str, node_id: str, node: JsObject, graph: str = "resoto") -> JsObject:
        return self._await(lambda c: c.create_node(parent_node_id, node_id, node, graph))

    def patch_node(
        self,
        node_id: str,
        node: JsObject,
        section: Optional[str] = None,
        graph: str = "resoto",
    ) -> JsObject:
        return self._await(lambda c: c.patch_node(node_id, node, section, graph))

    def get_node(self, node_id: str, graph: str = "resoto") -> JsObject:
        return self._await(lambda c: c.get_node(node_id, graph))

    def delete_node(self, node_id: str, graph: str = "resoto") -> None:
        return self._await(lambda c: c.delete_node(node_id, graph))

    def patch_nodes(self, nodes: Sequence[JsObject], graph: str = "resoto") -> List[JsObject]:
        return self._await(lambda c: c.patch_nodes(nodes, graph))

    def merge_graph(self, update: List[JsObject], graph: str = "resoto") -> GraphUpdate:
        return self._await(lambda c: c.merge_graph(update, graph))

    def add_to_batch(
        self,
        update: List[JsObject],
        batch_id: Optional[str] = None,
        graph: str = "resoto",
    ) -> Tuple[str, GraphUpdate]:
        return self._await(lambda c: c.add_to_batch(update, batch_id, graph))

    def list_batches(self, graph: str = "resoto") -> List[JsObject]:
        return self._await(lambda c: c.list_batches(graph))

    def commit_batch(self, batch_id: str, graph: str = "resoto") -> None:
        return self._await(lambda c: c.commit_batch(batch_id, graph))

    def abort_batch(self, batch_id: str, graph: str = "resoto") -> None:
        return self._await(lambda c: c.abort_batch(batch_id, graph))

    def search_graph_raw(self, search: str, graph: str = "resoto") -> JsObject:
        return self._await(lambda c: c.search_graph_raw(search, graph))

    def search_graph_explain(self, search: str, graph: str = "resoto") -> EstimatedSearchCost:
        return self._await(lambda c: c.search_graph_explain(search, graph))

    def search_list(
        self, search: str, section: Optional[str] = "reported", graph: str = "resoto"
    ) -> Iterator[JsObject]:
        return self._iterator(lambda c: c.search_list(search, section, graph))

    def search_graph(
        self, search: str, section: Optional[str] = "reported", graph: str = "resoto"
    ) -> Iterator[JsObject]:
        return self._iterator(lambda c: c.search_graph(search, section, graph))

    def search_aggregate(
        self, search: str, section: Optional[str] = "reported", graph: str = "resoto"
    ) -> Iterator[JsObject]:
        return self._iterator(lambda c: c.search_aggregate(search, section, graph))

    def subscribers(self) -> List[Subscriber]:
        return self._await(lambda c: c.subscribers())

    def subscribers_for_event(self, event_type: str) -> List[Subscriber]:
        return self._await(lambda c: c.subscribers_for_event(event_type))

    def subscriber(self, uid: str) -> Optional[Subscriber]:
        return self._await(lambda c: c.subscriber(uid))

    def update_subscriber(self, uid: str, subscriptions: List[Subscription]) -> Optional[Subscriber]:
        return self._await(lambda c: c.update_subscriber(uid, subscriptions))

    def add_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        return self._await(lambda c: c.add_subscription(uid, subscription))

    def delete_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        return self._await(lambda c: c.delete_subscription(uid, subscription))

    def delete_subscriber(self, uid: str) -> None:
        return self._await(lambda c: c.delete_subscriber(uid))

    def cli_evaluate(
        self, command: str, graph: str = "resoto", **env: str
    ) -> List[Tuple[ParsedCommands, List[JsObject]]]:
        return self._await(lambda c: c.cli_evaluate(command, graph, **env))

    def cli_execute_raw(
        self,
        command: str,
        graph: Optional[str] = "resoto",
        section: Optional[str] = "reported",
        headers: Optional[Dict[str, str]] = None,
        files: Optional[FilenameLookup] = None,
        **env: str,
    ) -> HttpResponse:
        resp = self._await(lambda c: c.cli_execute_raw(command, graph, section, headers, files, **env))
        return HttpResponse(
            status_code=resp.status_code,
            headers=resp.headers,
            text=lambda: self.event_loop_thread.run_coroutine(resp.text()),
            json=lambda: self.event_loop_thread.run_coroutine(resp.json()),
            payload_bytes=lambda: self.event_loop_thread.run_coroutine(resp.payload_bytes()),
            iter_lines=lambda: self._asynciter_to_iter(resp.async_iter_lines()),
            release=resp.release,
        )

    def cli_execute(
        self,
        command: str,
        graph: Optional[str] = "resoto",
        section: Optional[str] = "reported",
        headers: Optional[Dict[str, str]] = None,
        files: Optional[FilenameLookup] = None,
        **env: str,
    ) -> Iterator[JsValue]:
        """
        Execute a CLI command and return the result as a stream of text or JSON objects.

        Binary or multi-part responses will trigger an exception.
        """
        return self._iterator(lambda c: c.cli_execute(command, graph, section, headers, files, **env))

    def cli_info(self) -> JsObject:
        return self._await(lambda c: c.cli_info())

    def configs(self) -> Iterator[str]:
        return self._iterator(lambda c: c.configs())

    def config(self, config_id: str) -> JsObject:
        return self._await(lambda c: c.config(config_id))

    def put_config(self, config_id: str, json: JsObject, validate: bool = True) -> JsObject:
        return self._await(lambda c: c.put_config(config_id, json, validate))

    def patch_config(self, config_id: str, json: JsObject) -> JsObject:
        return self._await(lambda c: c.patch_config(config_id, json))

    def delete_config(self, config_id: str) -> None:
        return self._await(lambda c: c.delete_config(config_id))

    def get_configs_model(self) -> Model:
        return self._await(lambda c: c.get_configs_model())

    def update_configs_model(self, update: List[Kind]) -> Model:
        return self._await(lambda c: c.update_configs_model(update))

    def list_configs_validation(self) -> Iterator[str]:
        return self._iterator(lambda c: c.list_configs_validation())

    def get_config_validation(self, cfg_id: str) -> Optional[ConfigValidation]:
        return self._await(lambda c: c.get_config_validation(cfg_id))

    def put_config_validation(self, cfg: ConfigValidation) -> ConfigValidation:
        return self._await(lambda c: c.put_config_validation(cfg))

    def ping(self) -> str:
        return self._await(lambda c: c.ping())

    def ready(self) -> str:
        return self._await(lambda c: c.ready())

    def dataframe(self, search: str, section: Optional[str] = "reported", graph: str = "resoto", flatten: bool = True) -> DataFrame:  # type: ignore
        if DataFrame is None:
            raise ImportError("Python package resotoclient[extras] is not installed")
        aggregate_search = False

        if search.startswith("aggregate"):
            aggregate_search = True
            iter = self.search_aggregate(search=search, section=section, graph=graph)
        else:
            iter = self.search_list(search=search, section=section, graph=graph)

        def extract_node(node: JsObject) -> Optional[JsObject]:
            node_data = node
            if not isinstance(node_data, dict):
                return None
            if aggregate_search:
                if flatten and "group" in node_data and isinstance(node_data["group"], dict):
                    group = node_data["group"]
                    del node_data["group"]
                    for k, v in group.items():
                        node_data[k] = v
            else:
                if flatten:
                    if not "reported" in node or not isinstance(node["reported"], dict):
                        return None
                    node_data = cast(Dict[str, Any], node["reported"])
                    for k, v in node.items():
                        if isinstance(v, dict) and k != "reported":
                            node_data[k] = v
                    node_data["cloud_id"] = js_find(
                        node,
                        ["ancestors", "cloud", "reported", "id"],
                    )
                    node_data["cloud_name"] = js_find(
                        node,
                        ["ancestors", "cloud", "reported", "name"],
                    )
                    node_data["account_id"] = js_find(
                        node,
                        ["ancestors", "account", "reported", "id"],
                    )
                    node_data["account_name"] = js_find(
                        node,
                        ["ancestors", "account", "reported", "name"],
                    )
                    node_data["region_id"] = js_find(
                        node,
                        ["ancestors", "region", "reported", "id"],
                    )
                    node_data["region_name"] = js_find(
                        node,
                        ["ancestors", "region", "reported", "name"],
                    )
                    node_data["zone_id"] = js_find(
                        node,
                        ["ancestors", "zone", "reported", "id"],
                    )
                    node_data["zone_name"] = js_find(
                        node,
                        ["ancestors", "zone", "reported", "name"],
                    )
            return node_data

        nodes = [extract_node(node) for node in iter]
        return pd.json_normalize(nodes)  # type: ignore

    def graphviz(
        self,
        search: str,
        section: Optional[str] = "reported",
        graph: str = "resoto",
        engine: str = "sfdp",
        format: str = "svg",
    ) -> Digraph:  # type: ignore
        if Digraph is None:
            raise ImportError("Python package resotoclient[extras] is not installed")

        digraph = Digraph(comment=search)  # type: ignore
        digraph.format = format
        digraph.engine = engine
        digraph.graph_attr = {"rankdir": "LR", "splines": "true", "overlap": "false"}  # type: ignore
        digraph.node_attr = {  # type: ignore
            "shape": "plain",
            "colorscheme": "paired12",
        }
        cit = iter(range(0, sys.maxsize))
        colors: Dict[str, int] = defaultdict(lambda: (next(cit) % 12) + 1)

        results = self.search_graph(search=search, section=section, graph=graph)

        for elem in results:
            if elem.get("type") == "node":
                kind = js_get(elem, ["reported", "kind"])
                color = colors[kind]
                rd = ResourceDescription(
                    id=js_get(elem, ["reported", "id"]),
                    name=js_get(elem, ["reported", "name"]),
                    uid=js_get(elem, ["id"]),
                    kind=parse_kind(kind),
                    kind_name=kind,
                )
                digraph.node(  # type: ignore
                    name=js_get(elem, ["id"]),
                    # label=rd.name,
                    label=render_resource(rd, color),
                    shape="plain",
                )
            elif elem.get("type") == "edge":
                digraph.edge(js_get(elem, ["from"]), js_get(elem, ["to"]))  # type: ignore

        return digraph  # type: ignore


def rnd_str(str_len: int = 10) -> str:
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(str_len))


def js_find(node: JsObject, path: List[str]) -> Optional[str]:
    """
    Get a value in a nested dict.
    """
    if len(path) == 0:
        return None
    else:
        value = node.get(path[0])
        if len(path) == 1:
            return value if isinstance(value, str) else None
        if not isinstance(value, dict):
            return None
        return js_find(value, path[1:])


def js_get(node: JsObject, path: List[str]) -> str:
    result = js_find(node, path)
    if result is None:
        raise ValueError(f"Path {path} not found in {node}")
    return result


class ResourceKind(Enum):
    UNKNOWN = 1
    INSTANCE = 2
    VOLUME = 3
    IMAGE = 4
    FIREWALL = 5
    K8S_CLUSER = 6
    NETWORK = 7
    LOAD_BALANCER = 8
    CLOUD = 9


do_kinds = {
    "droplet": ResourceKind.INSTANCE,
    "volume": ResourceKind.VOLUME,
    "image": ResourceKind.IMAGE,
    "firewall": ResourceKind.FIREWALL,
    "kubernetes_cluster": ResourceKind.K8S_CLUSER,
    "network": ResourceKind.NETWORK,
    "load_balancer": ResourceKind.LOAD_BALANCER,
}


def parse_kind(kind: str) -> ResourceKind:
    cloud, rest = kind.split("_")[0], "_".join(kind.split("_")[1:])
    if cloud == "digitalocean":
        return do_kinds.get(rest) or ResourceKind.UNKNOWN
    else:
        return ResourceKind.UNKNOWN


kind_colors = {
    ResourceKind.INSTANCE: "8",
    ResourceKind.VOLUME: "4",
    ResourceKind.IMAGE: "7",
    ResourceKind.FIREWALL: "6",
    ResourceKind.K8S_CLUSER: "5",
    ResourceKind.NETWORK: "10",
    ResourceKind.LOAD_BALANCER: "9",
    ResourceKind.CLOUD: "1",
}


@dataclass
class ResourceDescription:
    uid: str
    name: str
    id: str
    kind: ResourceKind
    kind_name: str


def render_resource(
    resource: ResourceDescription,
    color: int,
) -> str:
    return f"""\
<<TABLE STYLE="ROUNDED" COLOR="{color}" BORDER="3" CELLBORDER="1" CELLPADDING="5">
    <TR>
        <TD SIDES="B">{resource.kind_name}</TD>
    </TR>
    <TR>
        <TD SIDES="B">{resource.id}</TD>
    </TR>
    <TR>
        <TD BORDER="0">{resource.name}</TD>
    </TR>
</TABLE>>"""
