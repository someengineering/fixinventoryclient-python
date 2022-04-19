from tkinter.tix import Tree
import requests
from resotoclient.jwt_utils import encode_jwt_to_headers
from typing import Any, Dict, Iterator, Set, Optional, List, Tuple
import jsons
from resotoclient import ca
from resotoclient.models import *


class ResotoClient:
    """
    The ApiClient interacts with a running core instance via the REST interface.
    """

    def __init__(self, url: str, psk: Optional[str]):
        self.base_url = url
        self.psk = psk
        self.ca_cert_path = None
        if url.startswith("https"):
            self.ca_cert_path = ca.load_ca_cert(resotocore_uri=url, psk=psk)

    def _headers(self) -> str:

        headers = {"Content-type": "application/json", "Accept": "application/json"}

        if self.psk:
            encode_jwt_to_headers(headers, {}, self.psk)

        return headers

    def _prepare_session(self, session: requests.Session):
        if self.ca_cert_path:
            session.verify = self.ca_cert_path
        session.headers = self._headers()

    def _get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            s.headers.update(headers or {})
            if stream:
                s.stream = True
                s.headers.update({"Accept": "application/x-ndjson"})
            return s.get(self.base_url + path, params=params)

    def _post(
        self,
        path: str,
        json: Optional[JsObject] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            s.headers.update(headers or {})
            if stream:
                s.stream = True
                s.headers.update({"Accept": "application/x-ndjson"})
            return s.post(self.base_url + path, data=data, json=json, params=params)

    def _put(
        self, path: str, json: JsObject, params: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            return s.put(self.base_url + path, json=json, params=params)

    def _patch(self, path: str, json: JsObject) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            return s.patch(self.base_url + path, json=json)

    def _delete(self, path: str) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            return s.delete(self.base_url + path)

    def model(self) -> Model:
        response = self._get("/model")
        return jsons.load(response.json(), Model)

    def update_model(self, update: List[Kind]) -> Model:
        response = self._get("/model", data=jsons.dump(update))
        model_json = response.json()
        model = jsons.load(model_json, Model)
        return model

    def list_graphs(self) -> Set[str]:
        response = self._get(f"/graph")
        return set(response.json())

    def get_graph(self, name: str) -> Optional[JsObject]:
        response = self._get(f"/graph/{name}")
        return response.json() if response.status_code == 200 else None

    def create_graph(self, name: str) -> JsObject:
        response = self._get(f"/graph/{name}")
        # root node
        return response.json()

    def delete_graph(self, name: str, truncate: bool = False) -> str:
        props = {"truncate": "true"} if truncate else {}
        response = self._get(f"/graph/{name}", params=props)
        # root node
        return response.text()

    def create_node(
        self, graph: str, parent_node_id: str, node_id: str, node: JsObject
    ) -> JsObject:
        response = self._post(
            f"/graph/{graph}/node/{node_id}/under/{parent_node_id}",
            json=node,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def patch_node(
        self, graph: str, node_id: str, node: JsObject, section: Optional[str] = None
    ) -> JsObject:
        section_path = f"/section/{section}" if section else ""
        response = self._patch(
            f"/graph/{graph}/node/{node_id}{section_path}",
            json=node,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def get_node(self, graph: str, node_id: str) -> JsObject:
        response = self._get(f"/graph/{graph}/node/{node_id}")
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def delete_node(self, graph: str, node_id: str) -> None:
        response = self._get(f"/graph/{graph}/node/{node_id}")
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text())

    def patch_nodes(self, graph: str, nodes: List[JsObject]) -> List[JsObject]:
        response = self._get(
            f"/graph/{graph}/nodes",
            json=nodes,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text())

    def merge_graph(self, graph: str, update: List[JsObject]) -> GraphUpdate:
        js = self.graph_to_json(update)
        response = self._get(
            f"/graph/{graph}/merge",
            json=js,
        )
        if response.status_code == 200:
            return jsons.load(response.json(), GraphUpdate)
        else:
            raise AttributeError(response.text)

    def add_to_batch(
        self, graph: str, update: List[JsObject], batch_id: Optional[str] = None
    ) -> Tuple[str, GraphUpdate]:
        js = self.graph_to_json(update)
        props = {"batch_id": batch_id} if batch_id else None
        response = self._post(
            f"/graph/{graph}/batch/merge",
            json=js,
            params=props,
        )
        if response.status_code == 200:
            return response.headers["BatchId"], jsons.load(response.json(), GraphUpdate)
        else:
            raise AttributeError(response.text)

    def list_batches(self, graph: str) -> List[JsObject]:
        response = self._get(
            f"/graph/{graph}/batch",
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def commit_batch(self, graph: str, batch_id: str) -> None:
        response = self._get(
            f"/graph/{graph}/batch/{batch_id}",
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(response.text)

    def abort_batch(self, graph: str, batch_id: str) -> None:
        response = self._get(
            f"/graph/{graph}/batch/{batch_id}",
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(response.text)

    def search_graph_raw(self, graph: str, search: str) -> JsObject:
        response = self._post(
            f"/graph/{graph}/search/raw",
            data=search,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def search_graph_explain(self, graph: str, search: str) -> EstimatedSearchCost:
        response = self._post(
            f"/graph/{graph}/search/explain",
            data=search,
        )
        if response.status_code == 200:
            return jsons.load(response.json(), EstimatedSearchCost)
        else:
            raise AttributeError(response.text)

    def search_list(self, graph: str, search: str) -> Iterator[JsObject]:
        response = self._post(f"/graph/{graph}/search/list", data=search, stream=True)
        if response.status_code == 200:
            return map(jsons.loadb, response.iter_lines())
        else:
            raise AttributeError(response.text)

    def search_graph(self, graph: str, search: str) -> Iterator[JsObject]:
        response = self._post(f"/graph/{graph}/search/graph", data=search, stream=True)
        if response.status_code == 200:
            return map(jsons.loadb, response.iter_lines())
        else:
            raise AttributeError(response.text)

    def search_aggregate(self, graph: str, search: str) -> Iterator[JsObject]:
        response = self._post(
            f"/graph/{graph}/search/aggregate", data=search, stream=True
        )
        if response.status_code == 200:
            return map(jsons.loadb, response.iter_lines())
        else:
            raise AttributeError(response.text)

    def subscribers(self) -> List[Subscriber]:
        response = self._get(f"/subscribers")
        if response.status_code == 200:
            return jsons.load(response.json(), List[Subscriber])
        else:
            raise AttributeError(response.text)

    def subscribers_for_event(self, event_type: str) -> List[Subscriber]:
        response = self._get(
            f"/subscribers/for/{event_type}",
        )
        if response.status_code == 200:
            return jsons.load(response.json(), List[Subscriber])
        else:
            raise AttributeError(response.text)

    def subscriber(self, uid: str) -> Optional[Subscriber]:
        response = self._get(
            f"/subscriber/{uid}",
        )
        if response.status_code == 200:
            return jsons.load(response.json(), Subscriber)
        else:
            return None

    def update_subscriber(
        self, uid: str, subscriptions: List[Subscription]
    ) -> Optional[Subscriber]:
        response = self._put(
            f"/subscriber/{uid}",
            json=jsons.dump(subscriptions),
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
        response = self._post(
            f"/subscriber/{uid}/{subscription.message_type}",
            params=props,
        )
        if response.status_code == 200:
            return jsons.load(response.json(), Subscriber)
        else:
            raise AttributeError(response.text)

    def delete_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        response = self._delete(
            f"/subscriber/{uid}/{subscription.message_type}",
        )
        if response.status_code == 200:
            return jsons.load(response.json(), Subscriber)
        else:
            raise AttributeError(response.text)

    def delete_subscriber(self, uid: str) -> None:
        response = self._get(
            f"/subscriber/{uid}",
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text)

    def cli_evaluate(
        self, graph: str, command: str, **env: str
    ) -> List[Tuple[ParsedCommands, List[JsObject]]]:
        props = {"graph": graph, "section": "reported", **env}
        response = self._post(
            f"/cli/evaluate",
            data=command,
            params=props,
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

    def cli_execute(self, graph: str, command: str, **env: str) -> Iterator[JsValue]:
        props = {"graph": graph, "section": "reported", **env}

        response = self._post(
            f"/cli/execute",
            data=command,
            params=props,
            headers={"Content-Type": "text/plain"},
            stream=True,
        )
        if response.status_code == 200:
            return map(jsons.loadb, response.iter_lines())
        else:
            raise AttributeError(response.text)

    def cli_info(self) -> JsObject:
        response = self._get(f"/cli/info")
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def configs(self) -> Iterator[str]:
        response = self._get(f"/configs", stream=True)
        if response.status_code == 200:
            return map(jsons.loadb, response.iter_lines())
        else:
            raise AttributeError(response.text)

    def config(self, config_id: str) -> JsObject:
        response = self._get(
            f"/config/{config_id}",
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def put_config(
        self, config_id: str, json: JsObject, validate: bool = True
    ) -> JsObject:
        params = {"validate": "true" if validate else "false"}
        response = self._put(
            f"/config/{config_id}",
            json=json,
            params=params,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def patch_config(self, config_id: str, json: JsObject) -> JsObject:
        response = self._get(
            f"/config/{config_id}",
            json=json,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def delete_config(self, config_id: str) -> None:
        response = self._get(
            f"/config/{config_id}",
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text)

    def get_configs_model(self) -> Model:
        response = self._get(f"/configs/model")
        if response.status_code == 200:
            model_json = response.json()
            model = jsons.load(model_json, Model)
            return model
        else:
            raise AttributeError(response.text)

    def update_configs_model(self, update: List[Kind]) -> Model:
        response = self._patch(
            "/configs/model",
            json=jsons.dump(update),
        )
        model_json = response.json()
        model = jsons.load(model_json, Model)
        return model

    def list_configs_validation(self) -> Iterator[str]:
        response = self._get(
            "/configs/validation",
            stream=True,
        )
        return map(jsons.loadb, response.iter_lines())

    def get_config_validation(self, cfg_id: str) -> Optional[ConfigValidation]:
        response = self._get(
            f"/config/{cfg_id}/validation",
        )
        return jsons.load(response.json(), ConfigValidation)

    def put_config_validation(self, cfg: ConfigValidation) -> ConfigValidation:
        response = self._put(
            f"/config/{cfg.id}/validation",
            json=jsons.dump(cfg),
        )
        return jsons.load(response.json(), ConfigValidation)

    def ping(self) -> str:
        response = self._get(f"/system/ping")
        if response.status_code == 200:
            return response.text
        else:
            raise AttributeError(response.text)

    def ready(self) -> str:
        response = self._get(f"/system/ready", headers={"Accept": "text/plain"})
        if response.status_code == 200:
            return response.text
        else:
            raise AttributeError(response.text)
