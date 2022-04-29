import requests
from requests.structures import CaseInsensitiveDict
from resotoclient.jwt_utils import encode_jwt_to_headers
from typing import (
    Any,
    Dict,
    Iterator,
    Set,
    Optional,
    List,
    Tuple,
    Sequence,
)
from resotoclient.json_utils import json_load, json_loadb, json_dump
from resotoclient import ca
from resotoclient.models import (
    Subscriber,
    Subscription,
    ParsedCommand,
    ParsedCommands,
    GraphUpdate,
    EstimatedSearchCost,
    ConfigValidation,
    JsObject,
    JsValue,
    Model,
    Kind,
)
from requests_toolbelt import MultipartDecoder, MultipartEncoder  # type: ignore
import random
import string


FilenameLookup = Dict[str, str]


class ResotoClient:
    """
    The ApiClient interacts with a running core instance via the REST interface.
    """

    def __init__(
        self,
        url: str,
        psk: Optional[str],
        custom_ca_cert_path: Optional[str] = None,
        verify: bool = True,
    ):
        self.base_url = url
        self.psk = psk
        self.ca_cert_path = None
        if custom_ca_cert_path:
            self.ca_cert_path = custom_ca_cert_path
        elif url.startswith("https"):
            self.ca_cert_path = ca.load_ca_cert(resotocore_uri=url, psk=psk)
        self.session_id = rnd_str()
        self.verify = verify

    def _headers(self) -> Dict[str, str]:

        headers = {"Content-type": "application/json", "Accept": "application/json"}

        if self.psk:
            encode_jwt_to_headers(headers, {}, self.psk)

        return headers

    def _prepare_session(self, session: requests.Session) -> None:
        if self.ca_cert_path and self.verify:
            session.verify = self.ca_cert_path
        else:
            session.verify = False
        session.headers = CaseInsensitiveDict(self._headers())
        params: Dict[str, str] = {}
        params["session_id"] = self.session_id
        session.params = params

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
        json: Optional[JsValue] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            if stream:
                s.stream = True
                s.headers.update({"Accept": "application/ndjson"})
            if headers:
                headers.update(headers)
            return s.post(
                self.base_url + path,
                data=data,
                json=json,
                params=params,
                headers=headers,
            )

    def _put(
        self, path: str, json: JsValue, params: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            return s.put(self.base_url + path, json=json, params=params)

    def _patch(self, path: str, json: JsValue) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            return s.patch(self.base_url + path, json=json)

    def _delete(
        self, path: str, params: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        with requests.Session() as s:
            self._prepare_session(s)
            return s.delete(self.base_url + path, params=params)

    def model(self) -> Model:
        response = self._get("/model")
        return json_load(response.json(), Model)

    def update_model(self, update: List[Kind]) -> Model:
        response = self._patch("/model", json=json_dump(update, List[Kind]))
        model_json = response.json()
        model = json_load(model_json, Model)
        return model

    def list_graphs(self) -> Set[str]:
        response = self._get(f"/graph")
        return set(response.json())

    def get_graph(self, name: str) -> Optional[JsObject]:
        response = self._get(f"/graph/{name}")
        return response.json() if response.status_code == 200 else None

    def create_graph(self, name: str) -> JsObject:
        response = self._post(f"/graph/{name}")
        # root node
        return response.json()

    def delete_graph(self, name: str, truncate: bool = False) -> str:
        props = {"truncate": "true"} if truncate else {}
        response = self._delete(f"/graph/{name}", params=props)
        # root node
        return response.text

    def create_node(
        self, parent_node_id: str, node_id: str, node: JsObject, graph: str = "resoto"
    ) -> JsObject:
        response = self._post(
            f"/graph/{graph}/node/{node_id}/under/{parent_node_id}",
            json=node,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def patch_node(
        self,
        node_id: str,
        node: JsObject,
        section: Optional[str] = None,
        graph: str = "resoto",
    ) -> JsObject:
        section_path = f"/section/{section}" if section else ""
        response = self._patch(
            f"/graph/{graph}/node/{node_id}{section_path}",
            json=node,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def get_node(self, node_id: str, graph: str = "resoto") -> JsObject:
        response = self._get(f"/graph/{graph}/node/{node_id}")
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def delete_node(self, node_id: str, graph: str = "resoto") -> None:
        response = self._delete(f"/graph/{graph}/node/{node_id}")
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text)

    def patch_nodes(
        self, nodes: Sequence[JsObject], graph: str = "resoto"
    ) -> List[JsObject]:
        response = self._patch(
            f"/graph/{graph}/nodes",
            json=nodes,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def merge_graph(self, update: List[JsObject], graph: str = "resoto") -> GraphUpdate:
        response = self._post(
            f"/graph/{graph}/merge",
            json=update,
        )
        if response.status_code == 200:
            return json_load(response.json(), GraphUpdate)
        else:
            raise AttributeError(response.text)

    def add_to_batch(
        self,
        update: List[JsObject],
        batch_id: Optional[str] = None,
        graph: str = "resoto",
    ) -> Tuple[str, GraphUpdate]:
        props = {"batch_id": batch_id} if batch_id else None
        response = self._post(
            f"/graph/{graph}/batch/merge",
            json=update,
            params=props,
        )
        if response.status_code == 200:
            return response.headers["BatchId"], json_load(response.json(), GraphUpdate)
        else:
            raise AttributeError(response.text)

    def list_batches(self, graph: str = "resoto") -> List[JsObject]:
        response = self._get(
            f"/graph/{graph}/batch",
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def commit_batch(self, batch_id: str, graph: str = "resoto") -> None:
        response = self._post(
            f"/graph/{graph}/batch/{batch_id}",
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(response.text)

    def abort_batch(self, batch_id: str, graph: str = "resoto") -> None:
        response = self._delete(
            f"/graph/{graph}/batch/{batch_id}",
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(response.text)

    def search_graph_raw(self, search: str, graph: str = "resoto") -> JsObject:
        response = self._post(
            f"/graph/{graph}/search/raw",
            data=search,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def search_graph_explain(
        self, search: str, graph: str = "resoto"
    ) -> EstimatedSearchCost:
        response = self._post(
            f"/graph/{graph}/search/explain",
            data=search,
        )
        if response.status_code == 200:
            return json_load(response.json(), EstimatedSearchCost)
        else:
            raise AttributeError(response.text)

    def search_list(self, search: str, section: Optional[str] = None, graph: str = "resoto") -> Iterator[JsObject]:
        params = {}
        if section:
            params["section"] = section
        
        response = self._post(f"/graph/{graph}/search/list", params=params, data=search, stream=True)
        if response.status_code == 200:
            return map(lambda line: json_loadb(line), response.iter_lines())
        else:
            raise AttributeError(response.text)

    def search_graph(self, search: str, section: Optional[str] = None, graph: str = "resoto") -> Iterator[JsObject]:
        params = {}
        if section:
            params["section"] = section
        response = self._post(f"/graph/{graph}/search/graph", params=params, data=search, stream=True)
        if response.status_code == 200:
            return map(lambda line: json_loadb(line), response.iter_lines())
        else:
            raise AttributeError(response.text)

    def search_aggregate(
        self, search: str, graph: str = "resoto"
    ) -> Iterator[JsObject]:
        response = self._post(
            f"/graph/{graph}/search/aggregate", data=search, stream=True
        )
        if response.status_code == 200:
            return map(lambda line: json_loadb(line), response.iter_lines())
        else:
            raise AttributeError(response.text)

    def subscribers(self) -> List[Subscriber]:
        response = self._get(f"/subscribers")
        if response.status_code == 200:
            return json_load(response.json(), List[Subscriber])
        else:
            raise AttributeError(response.text)

    def subscribers_for_event(self, event_type: str) -> List[Subscriber]:
        response = self._get(
            f"/subscribers/for/{event_type}",
        )
        if response.status_code == 200:
            return json_load(response.json(), List[Subscriber])
        else:
            raise AttributeError(response.text)

    def subscriber(self, uid: str) -> Optional[Subscriber]:
        response = self._get(
            f"/subscriber/{uid}",
        )
        if response.status_code == 200:
            return json_load(response.json(), Subscriber)
        else:
            return None

    def update_subscriber(
        self, uid: str, subscriptions: List[Subscription]
    ) -> Optional[Subscriber]:
        response = self._put(
            f"/subscriber/{uid}",
            json=json_dump(subscriptions),
        )
        if response.status_code == 200:
            return json_load(response.json(), Subscriber)
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
            return json_load(response.json(), Subscriber)
        else:
            raise AttributeError(response.text)

    def delete_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        response = self._delete(
            f"/subscriber/{uid}/{subscription.message_type}",
        )
        if response.status_code == 200:
            return json_load(response.json(), Subscriber)
        else:
            raise AttributeError(response.text)

    def delete_subscriber(self, uid: str) -> None:
        response = self._delete(
            f"/subscriber/{uid}",
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(response.text)

    def cli_evaluate(
        self, command: str, graph: str = "resoto", **env: str
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
                        json_load(json["parsed"], List[ParsedCommand]), json["env"]
                    ),
                    json["execute"],
                )
                for json in response.json()
            ]
        else:
            raise AttributeError(response.text)

    def cli_execute_raw(
        self,
        command: str,
        graph: Optional[str] = "resoto",
        section: Optional[str] = "reported",
        headers: Optional[Dict[str, str]] = None,
        files: Optional[FilenameLookup] = None,
        **env: str,
    ) -> requests.Response:
        props: Dict[str, str] = {}
        if graph:
            props["graph"] = graph
        if section:
            props["section"] = section

        body: Optional[Any] = None
        headers = headers or {}
        if not files:
            headers["Content-Type"] = "text/plain"
            body = command
        else:
            headers["Resoto-Shell-Command"] = command
            headers["Content-Type"] = "multipart/form-data; boundary=file-upload"
            parts = {
                name: (name, open(path, "rb"), "application/octet-stream")
                for name, path in files.items()
            }
            body = MultipartEncoder(parts, "file-upload")

        response = self._post(
            f"/cli/execute",
            data=body,
            params=props,
            headers=headers,
            stream=True,
        )
        return response

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

        response = self.cli_execute_raw(
            command=command,
            graph=graph,
            section=section,
            headers=headers,
            files=files,
            **env,
        )

        if response.status_code == 200:
            content_type = response.headers.get("Content-Type")
            if content_type == "text/plain":
                return iter([response.text])
            elif content_type == "application/json":
                return iter([response.json()])
            elif content_type == "application/x-ndjson":
                return map(lambda line: json_loadb(line), response.iter_lines())
            else:
                raise NotImplementedError(
                    f"Unsupported content type: {content_type}. Use cli_execute_raw instead."
                )
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
            return map(lambda l: json_loadb(l), response.iter_lines())
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
        response = self._patch(
            f"/config/{config_id}",
            json=json,
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise AttributeError(response.text)

    def delete_config(self, config_id: str) -> None:
        response = self._delete(
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
            model = json_load(model_json, Model)
            return model
        else:
            raise AttributeError(response.text)

    def update_configs_model(self, update: List[Kind]) -> Model:
        response = self._patch(
            "/configs/model",
            json=json_dump(update),
        )
        model_json = response.json()
        model = json_load(model_json, Model)
        return model

    def list_configs_validation(self) -> Iterator[str]:
        response = self._get(
            "/configs/validation",
            stream=True,
        )
        return map(lambda l: json_loadb(l), response.iter_lines())

    def get_config_validation(self, cfg_id: str) -> Optional[ConfigValidation]:
        response = self._get(
            f"/config/{cfg_id}/validation",
        )
        return json_load(response.json(), ConfigValidation)

    def put_config_validation(self, cfg: ConfigValidation) -> ConfigValidation:
        response = self._put(
            f"/config/{cfg.id}/validation",
            json=json_dump(cfg),
        )
        return json_load(response.json(), ConfigValidation)

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


def rnd_str(str_len: int = 10) -> str:
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(str_len)
    )
