import requests
from resotoclient.jwt_utils import encode_jwt_to_headers
from io import StringIO
from typing import Any, Dict, Set, Optional, List, Tuple, Union, Sequence, Any, Mapping
from enum import Enum
import jsons
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass
class Kind:
    fqn: str
    runtime_kind: Optional[str]


@dataclass
class Model:
    kinds: List[Kind]


@dataclass
class GraphUpdate:
    nodes_created: int
    nodes_updates: int
    nodes_deleted: int
    edges_created: int
    edges_updated: int
    edges_deleted: int


class EstimatedQueryCostRating(Enum):
    simple = 1
    complex = 2
    bad = 3


@dataclass
class EstimatedSearchCost:
    # Absolute number that shows the cost of this query. See rating for an interpreted number.
    estimated_cost: int
    # This is the estimated number of items returned for this query.
    # Please note: it is computed based on query statistics and heuristics and does not reflect the real number.
    estimated_nr_items: int
    # This is the number of available nodes in the graph.
    available_nr_items: int
    # Indicates, if a full collection scan is required.
    # This means, that the query does not take advantage of any indexes!
    full_collection_scan: bool
    # The rating of this query
    rating: EstimatedQueryCostRating


@dataclass
class Subscription:
    message_type: str
    wait_for_completion: bool = field(default=True)
    timeout: timedelta = field(default=timedelta(seconds=60))


@dataclass
class Subscriber:
    id: str
    subscriptions: Dict[str, Subscription] = field(default_factory=dict)


@dataclass
class ParsedCommand:
    cmd: str
    args: Optional[str] = None


Json = Dict[str, Any]
JsonElement = Union[str, int, float, bool, None, Mapping[str, Any], Sequence[Any]]


@dataclass
class ParsedCommands:
    commands: List[ParsedCommand]
    env: Json = field(default_factory=dict)


class ConfigValidation:
    id: str
    external_validation: bool = False


class ResotoClient:
    """
    The ApiClient interacts with a running core instance via the REST interface.
    """

    def __init__(self, url: str, psk: str):
        self.base_url = url
        self.psk = psk

    def _headers(self) -> str:

        headers = {"Content-type": "application/json", "Accept": "application/json"}

        if self.psk:
            encode_jwt_to_headers(headers, {}, self.psk)

        return headers

    def model(self) -> Model:
        response = requests.get(self.base_url + "/model", headers=self._headers())
        return jsons.load(response.json(), Model)

    def update_model(self, update: List[Kind]) -> Model:
        response = requests.get(
            self.base_url + "/model", data=jsons.dump(update), headers=self._headers()
        )
        model_json = response.json()
        model = jsons.load(model_json, Model)
        return model

    def list_graphs(self) -> Set[str]:
        response = requests.get(self.base_url + f"/graph", headers=self._headers())
        return set(response.json())

    def get_graph(self, name: str) -> Optional[Json]:
        response = requests.get(
            self.base_url + f"/graph/{name}", headers=self._headers()
        )
        return response.json() if response.status_code_code == 200 else None

    def create_graph(self, name: str) -> Json:
        response = requests.get(
            self.base_url + f"/graph/{name}", headers=self._headers()
        )
        # root node
        return response.json()

    def delete_graph(self, name: str, truncate: bool = False) -> str:
        props = {"truncate": "true"} if truncate else {}
        response = requests.get(
            self.base_url + f"/graph/{name}", params=props, headers=self._headers()
        )
        # root node
        return response.text()

    def create_node(
        self, graph: str, parent_node_id: str, node_id: str, node: Json
    ) -> Json:
        response = requests.post(
            self.base_url + f"/graph/{graph}/node/{node_id}/under/{parent_node_id}",
            json=node,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def patch_node(
        self, graph: str, node_id: str, node: Json, section: Optional[str] = None
    ) -> Json:
        section_path = f"/section/{section}" if section else ""
        response = requests.patch(
            self.base_url + f"/graph/{graph}/node/{node_id}{section_path}",
            json=node,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def get_node(self, graph: str, node_id: str) -> Json:
        response = requests.get(
            self.base_url + f"/graph/{graph}/node/{node_id}", headers=self._headers()
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def delete_node(self, graph: str, node_id: str) -> None:
        response = requests.get(
            self.base_url + f"/graph/{graph}/node/{node_id}", headers=self._headers()
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text())

    def patch_nodes(self, graph: str, nodes: List[Json]) -> List[Json]:
        response = requests.get(
            self.base_url + f"/graph/{graph}/nodes",
            json=nodes,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def merge_graph(self, graph: str, update: List[Json]) -> GraphUpdate:
        js = self.graph_to_json(update)
        response = requests.get(
            self.base_url + f"/graph/{graph}/merge", json=js, headers=self._headers()
        )
        if response.status_code == 200:
            return jsons.load(response.json(), GraphUpdate)
        else:
            raise AttributeError(response.text)

    def add_to_batch(
        self, graph: str, update: List[Json], batch_id: Optional[str] = None
    ) -> Tuple[str, GraphUpdate]:
        js = self.graph_to_json(update)
        props = {"batch_id": batch_id} if batch_id else None
        response = requests.post(
            self.base_url + f"/graph/{graph}/batch/merge",
            json=js,
            params=props,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.headers["BatchId"], jsons.load(response.json(), GraphUpdate)
        else:
            raise AttributeError(response.text)

    def list_batches(self, graph: str) -> List[Json]:
        response = requests.get(
            self.base_url + f"/graph/{graph}/batch", headers=self._headers()
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def commit_batch(self, graph: str, batch_id: str) -> None:
        response = requests.get(
            self.base_url + f"/graph/{graph}/batch/{batch_id}", headers=self._headers()
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(response.text)

    def abort_batch(self, graph: str, batch_id: str) -> None:
        response = requests.get(
            self.base_url + f"/graph/{graph}/batch/{batch_id}", headers=self._headers()
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(response.text)

    def search_graph_raw(self, graph: str, search: str) -> Json:
        response = requests.post(
            self.base_url + f"/graph/{graph}/search/raw",
            data=search,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def search_graph_explain(self, graph: str, search: str) -> EstimatedSearchCost:
        response = requests.post(
            self.base_url + f"/graph/{graph}/search/explain",
            data=search,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return jsons.load(response.json(), EstimatedSearchCost)
        else:
            raise AttributeError(response.text)

    def search_list(self, graph: str, search: str) -> List[Json]:
        response = requests.post(
            self.base_url + f"/graph/{graph}/search/list",
            data=search,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def search_graph(self, graph: str, search: str) -> List[Json]:
        response = requests.post(
            self.base_url + f"/graph/{graph}/search/graph",
            data=search,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def search_aggregate(self, graph: str, search: str) -> List[Json]:
        response = requests.post(
            self.base_url + f"/graph/{graph}/search/aggregate",
            data=search,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def subscribers(self) -> List[Subscriber]:
        response = requests.get(
            self.base_url + f"/subscribers", headers=self._headers()
        )
        if response.status_code == 200:
            return jsons.load(response.json(), List[Subscriber])
        else:
            raise AttributeError(response.text)

    def subscribers_for_event(self, event_type: str) -> List[Subscriber]:
        response = requests.get(
            self.base_url + f"/subscribers/for/{event_type}", headers=self._headers()
        )
        if response.status_code == 200:
            return jsons.load(response.json(), List[Subscriber])
        else:
            raise AttributeError(response.text)

    def subscriber(self, uid: str) -> Optional[Subscriber]:
        response = requests.get(
            self.base_url + f"/subscriber/{uid}", headers=self._headers()
        )
        if response.status_code == 200:
            return jsons.load(response.json(), Subscriber)
        else:
            return None

    def update_subscriber(
        self, uid: str, subscriptions: List[Subscription]
    ) -> Optional[Subscriber]:
        response = requests.put(
            self.base_url + f"/subscriber/{uid}",
            json=jsons.dump(subscriptions),
            headers=self._headers(),
        )
        if response.status_code == 200:
            return jsons.load(response.json(), Subscriber)
        else:
            raise AttributeError(response.text)

    def add_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        props = {
            "timeout": str(int(subscription.timeout.total_seconds())),
            "wait_for_completion": str(subscription.wait_for_completion),
        }
        response = requests.post(
            self.base_url + f"/subscriber/{uid}/{subscription.message_type}",
            params=props,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return jsons.load(response.json(), Subscriber)
        else:
            raise AttributeError(response.text)

    def delete_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        response = requests.delete(
            self.base_url + f"/subscriber/{uid}/{subscription.message_type}",
            headers=self._headers(),
        )
        if response.status_code == 200:
            return jsons.load(response.json(), Subscriber)
        else:
            raise AttributeError(response.text)

    def delete_subscriber(self, uid: str) -> None:
        response = requests.get(
            self.base_url + f"/subscriber/{uid}", headers=self._headers()
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text)

    def cli_evaluate(
        self, graph: str, command: str, **env: str
    ) -> List[Tuple[ParsedCommands, List[Json]]]:
        props = {"graph": graph, "section": "reported", **env}
        response = requests.post(
            self.base_url + f"/cli/evaluate",
            data=command,
            params=props,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return [
                (
                    ParsedCommands(
                        jsons.load(json["parsed"], List[ParsedCommand]), json["env"]
                    ),
                    json["execute"],
                )
                for json in response.json()
            ]
        else:
            raise AttributeError(response.text)

    def cli_execute(self, graph: str, command: str, **env: str) -> List[JsonElement]:
        props = {"graph": graph, "section": "reported", **env}
        headers = self._headers()
        headers["Content-Type"] = "text/plain"
        response = requests.post(
            self.base_url + f"/cli/execute",
            data=command,
            params=props,
            headers=headers,
        )
        if response.status_code == 200:
            return response.json()  # type: ignore
        else:
            raise AttributeError(response.text)

    def cli_info(self) -> Json:
        response = requests.get(self.base_url + f"/cli/info", headers=self._headers())
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def configs(self) -> List[str]:
        response = requests.get(self.base_url + f"/configs", headers=self._headers())
        if response.status_code == 200:
            return AccessJson.wrap_list(response.json())  # type: ignore
        else:
            raise AttributeError(response.text)

    def config(self, config_id: str) -> Json:
        response = requests.get(
            self.base_url + f"/config/{config_id}", headers=self._headers()
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def put_config(self, config_id: str, json: Json, validate: bool = True) -> Json:
        params = {"validate": "true" if validate else "false"}
        response = requests.put(
            self.base_url + f"/config/{config_id}",
            json=json,
            params=params,
            headers=self._headers(),
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def patch_config(self, config_id: str, json: Json) -> Json:
        response = requests.get(
            self.base_url + f"/config/{config_id}", json=json, headers=self._headers()
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def delete_config(self, config_id: str) -> None:
        response = requests.get(
            self.base_url + f"/config/{config_id}", headers=self._headers()
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text)

    def get_configs_model(self) -> Model:
        response = requests.get(
            self.base_url + f"/configs/model", headers=self._headers()
        )
        if response.status_code == 200:
            model_json = response.json()
            model = jsons.load(model_json, Model)
            return model
        else:
            raise AttributeError(response.text)

    def update_configs_model(self, update: List[Kind]) -> Model:
        response = requests.patch(
            self.base_url + "/configs/model",
            json=jsons.dump(update),
            headers=self._headers(),
        )
        model_json = response.json()
        model = jsons.load(model_json, Model)
        return model

    def list_configs_validation(self) -> List[str]:
        response = requests.get(
            self.base_url + "/configs/validation", headers=self._headers()
        )
        return response.json()  # type: ignore

    def get_config_validation(self, cfg_id: str) -> Optional[ConfigValidation]:
        response = requests.get(
            self.base_url + f"/config/{cfg_id}/validation", headers=self._headers()
        )
        return jsons.load(response.json(), ConfigValidation)

    def put_config_validation(self, cfg: ConfigValidation) -> ConfigValidation:
        response = requests.put(
            self.base_url + f"/config/{cfg.id}/validation",
            json=jsons.dump(cfg),
            headers=self._headers(),
        )
        return jsons.load(response.json(), ConfigValidation)

    def ping(self) -> str:
        response = requests.get(
            self.base_url + f"/system/ping", headers=self._headers()
        )
        if response.status_code == 200:
            return response.text
        else:
            raise AttributeError(response.text)

    def ready(self) -> str:
        response = requests.get(
            self.base_url + f"/system/ready", headers=self._headers()
        )
        if response.status_code == 200:
            return response.text
        else:
            raise AttributeError(response.text)
