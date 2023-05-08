import json
import logging
from resotoclient.jwt_utils import encode_jwt_to_headers
from typing import (
    Any,
    Dict,
    AsyncIterator,
    Set,
    Optional,
    List,
    Tuple,
    Sequence,
    Type,
)
from types import TracebackType
from resotoclient.json_utils import json_load, json_loadb, json_dump
from resotoclient.ca import CertificatesHolder
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
from resotoclient.http_client.aiohttp_client import AioHttpClient, HttpResponse, PoisonPill
import random
import string
from datetime import timedelta
from asyncio import AbstractEventLoop, Queue
from aiohttp import MultipartWriter

FilenameLookup = Dict[str, str]

log: logging.Logger = logging.getLogger("resotoclient")


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
        loop: Optional[AbstractEventLoop] = None,
    ):
        """
        Create a new resoto client instance.
        :param url: the url of the resotocore instance.
        :param psk: the optional pre-shared key to use for authentication. The PSK is used to authenticate the client. If you do not have access to the PSK, you can use the auth_header parameter to authenticate with a JWT token.
        :param additional_headers: additional headers to send with each request.
        :param custom_ca_cert_path: path to a custom CA certificate to use for verifying the server certificate.
        :param verify: whether to verify the server certificate.
        :param renew_certificate_before: how long before the certificate expires to renew it.
        :param renew_auth_token_before: how long before the auth token expires to renew it.
        :param loop: the event loop to use.
        """
        self.resotocore_url = url
        self.psk = psk
        self.verify = verify
        self.session_id = rnd_str()
        self.holder = CertificatesHolder(
            resotocore_url=url,
            psk=psk,
            custom_ca_cert_path=custom_ca_cert_path,
            renew_before=renew_certificate_before,
        )
        self.http_client = AioHttpClient(
            url=url,
            psk=psk,
            session_id=self.session_id,
            get_ssl_context=self.holder.ssl_context if verify else None,
            additional_headers=additional_headers,
            renew_auth_token_before=renew_auth_token_before,
            loop=loop,
        )

    async def __aenter__(self) -> "ResotoClient":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.shutdown()

    async def start(self) -> None:
        await self.http_client.start()
        await self.holder.start()

    async def shutdown(self) -> None:
        await self.http_client.shutdown()
        self.holder.shutdown()

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-type": "application/json", "Accept": "application/json"}

        if self.psk:
            encode_jwt_to_headers(headers, {}, self.psk)

        return headers

    async def _get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        return await self.http_client.get(path, params, headers, stream)

    async def _post(
        self,
        path: str,
        json: Optional[JsValue] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> HttpResponse:
        return await self.http_client.post(path, json, data, params, headers, stream)

    async def _put(self, path: str, json: JsValue, params: Optional[Dict[str, str]] = None) -> HttpResponse:
        return await self.http_client.put(path, json, params)

    async def _patch(self, path: str, json: JsValue) -> HttpResponse:
        return await self.http_client.patch(path, json)

    async def _delete(self, path: str, params: Optional[Dict[str, str]] = None) -> HttpResponse:
        return await self.http_client.delete(path, params)

    async def model(self) -> Model:
        response: JsValue = await (await self._get("/model")).json()
        # ResotoClient <= 2.2 returns a model dict fqn: kind.
        if isinstance(response, dict):
            return json_load(response, Model)
        # ResotoClient > 2.2 returns a list of kinds.
        elif isinstance(response, list):
            kinds = {kd.fqn: kd for k in response if (kd := json_load(k, Kind))}
            return Model(kinds)
        else:
            raise ValueError(f"Can not map to model. Unexpected response: {response}")

    async def update_model(self, update: List[Kind]) -> Model:
        response = await self._patch("/model", json=json_dump(update, List[Kind]))
        model_json = await response.json()
        model = json_load(model_json, Model)
        return model

    async def list_graphs(self) -> Set[str]:
        response = await self._get("/graph")
        return set(await response.json())

    async def get_graph(self, name: str) -> Optional[JsObject]:
        response = await self._get(f"/graph/{name}")
        return await response.json() if response.status_code == 200 else None

    async def create_graph(self, name: str) -> JsObject:
        response = await self._post(f"/graph/{name}")
        # root node
        return await response.json()

    async def delete_graph(self, name: str, truncate: bool = False) -> str:
        props = {"truncate": "true"} if truncate else {}
        response = await self._delete(f"/graph/{name}", params=props)
        # root node
        return await response.text()

    async def create_node(self, parent_node_id: str, node_id: str, node: JsObject, graph: str = "resoto") -> JsObject:
        response = await self._post(
            f"/graph/{graph}/node/{node_id}/under/{parent_node_id}",
            json=node,
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def patch_node(
        self,
        node_id: str,
        node: JsObject,
        section: Optional[str] = None,
        graph: str = "resoto",
    ) -> JsObject:
        section_path = f"/section/{section}" if section else ""
        response = await self._patch(
            f"/graph/{graph}/node/{node_id}{section_path}",
            json=node,
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def get_node(self, node_id: str, graph: str = "resoto") -> JsObject:
        response = await self._get(f"/graph/{graph}/node/{node_id}")
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def delete_node(self, node_id: str, graph: str = "resoto") -> None:
        response = await self._delete(f"/graph/{graph}/node/{node_id}")
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(await response.text())

    async def patch_nodes(self, nodes: Sequence[JsObject], graph: str = "resoto") -> List[JsObject]:
        response = await self._patch(
            f"/graph/{graph}/nodes",
            json=nodes,
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def merge_graph(self, update: List[JsObject], graph: str = "resoto") -> GraphUpdate:
        response = await self._post(
            f"/graph/{graph}/merge",
            json=update,
        )
        if response.status_code == 200:
            return json_load(await response.json(), GraphUpdate)
        else:
            raise AttributeError(await response.text())

    async def add_to_batch(
        self,
        update: List[JsObject],
        batch_id: Optional[str] = None,
        graph: str = "resoto",
    ) -> Tuple[str, GraphUpdate]:
        props = {"batch_id": batch_id} if batch_id else None
        response = await self._post(
            f"/graph/{graph}/batch/merge",
            json=update,
            params=props,
        )
        if response.status_code == 200:
            return response.headers["BatchId"], json_load(await response.json(), GraphUpdate)
        else:
            raise AttributeError(await response.text())

    async def list_batches(self, graph: str = "resoto") -> List[JsObject]:
        response = await self._get(
            f"/graph/{graph}/batch",
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def commit_batch(self, batch_id: str, graph: str = "resoto") -> None:
        response = await self._post(
            f"/graph/{graph}/batch/{batch_id}",
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(await response.text())

    async def abort_batch(self, batch_id: str, graph: str = "resoto") -> None:
        response = await self._delete(
            f"/graph/{graph}/batch/{batch_id}",
        )
        if response.status_code == 200:
            return None
        else:
            raise AttributeError(await response.text())

    async def search_graph_raw(self, search: str, graph: str = "resoto") -> JsObject:
        response = await self._post(
            f"/graph/{graph}/search/raw",
            data=search,
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def search_graph_explain(self, search: str, graph: str = "resoto") -> EstimatedSearchCost:
        response = await self._post(
            f"/graph/{graph}/search/explain",
            data=search,
        )
        if response.status_code == 200:
            return json_load(await response.json(), EstimatedSearchCost)
        else:
            raise AttributeError(await response.text())

    async def search_list(
        self, search: str, section: Optional[str] = "reported", graph: str = "resoto"
    ) -> AsyncIterator[JsObject]:
        params = {}
        if section:
            params["section"] = section

        response = await self._post(f"/graph/{graph}/search/list", params=params, data=search, stream=True)
        if response.status_code == 200:
            async for line in response.async_iter_lines():
                yield json_loadb(line)
        else:
            raise AttributeError(await response.text())

    async def search_graph(
        self, search: str, section: Optional[str] = "reported", graph: str = "resoto"
    ) -> AsyncIterator[JsObject]:
        params = {}
        if section:
            params["section"] = section
        response = await self._post(f"/graph/{graph}/search/graph", params=params, data=search, stream=True)
        if response.status_code == 200:
            async for line in response.async_iter_lines():
                yield json_loadb(line)
        else:
            raise AttributeError(await response.text())

    async def search_aggregate(
        self, search: str, section: Optional[str] = "reported", graph: str = "resoto"
    ) -> AsyncIterator[JsObject]:
        params = {}
        if section:
            params["section"] = section
        response = await self._post(f"/graph/{graph}/search/aggregate", params=params, data=search, stream=True)
        if response.status_code == 200:
            async for line in response.async_iter_lines():
                yield json_loadb(line)
        else:
            raise AttributeError(await response.text())

    async def subscribers(self) -> List[Subscriber]:
        response = await self._get("/subscribers")
        if response.status_code == 200:
            return json_load(await response.json(), List[Subscriber])
        else:
            raise AttributeError(await response.text())

    async def subscribers_for_event(self, event_type: str) -> List[Subscriber]:
        response = await self._get(
            f"/subscribers/for/{event_type}",
        )
        if response.status_code == 200:
            return json_load(await response.json(), List[Subscriber])
        else:
            raise AttributeError(await response.text())

    async def subscriber(self, uid: str) -> Optional[Subscriber]:
        response = await self._get(
            f"/subscriber/{uid}",
        )
        if response.status_code == 200:
            return json_load(await response.json(), Subscriber)
        else:
            return None

    async def update_subscriber(self, uid: str, subscriptions: List[Subscription]) -> Optional[Subscriber]:
        response = await self._put(
            f"/subscriber/{uid}",
            json=json_dump(subscriptions),
        )
        if response.status_code == 200:
            return json_load(await response.json(), Subscriber)
        else:
            raise AttributeError(await response.text())

    async def add_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        props = {
            "timeout": str(int(subscription.timeout.total_seconds())),
            "wait_for_completion": str(subscription.wait_for_completion),
        }
        response = await self._post(
            f"/subscriber/{uid}/{subscription.message_type}",
            params=props,
        )
        if response.status_code == 200:
            return json_load(await response.json(), Subscriber)
        else:
            raise AttributeError(await response.text())

    async def delete_subscription(self, uid: str, subscription: Subscription) -> Subscriber:
        response = await self._delete(
            f"/subscriber/{uid}/{subscription.message_type}",
        )
        if response.status_code == 200:
            return json_load(await response.json(), Subscriber)
        else:
            raise AttributeError(await response.text())

    async def delete_subscriber(self, uid: str) -> None:
        response = await self._delete(
            f"/subscriber/{uid}",
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(await response.text())

    async def cli_evaluate(
        self, command: str, graph: str = "resoto", **env: str
    ) -> List[Tuple[ParsedCommands, List[JsObject]]]:
        props = {"graph": graph, "section": "reported", **env}
        response = await self._post(
            "/cli/evaluate",
            data=command,
            params=props,
        )
        if response.status_code == 200:
            return [
                (
                    ParsedCommands(json_load(json["parsed"], List[ParsedCommand]), json["env"]),
                    json["execute"],
                )
                for json in await response.json()
            ]
        else:
            raise AttributeError(await response.text())

    async def cli_execute_raw(
        self,
        command: str,
        graph: Optional[str] = "resoto",
        section: Optional[str] = "reported",
        headers: Optional[Dict[str, str]] = None,
        files: Optional[FilenameLookup] = None,
        **env: str,
    ) -> HttpResponse:
        props: Dict[str, str] = {}
        if graph:
            props["graph"] = graph
        if section:
            props["section"] = section

        body: Optional[Any] = None
        headers = headers or {}
        if not files:
            headers["Content-Type"] = "text/plain"
            body = command.encode("utf-8")
            response = await self._post(
                "/cli/execute",
                data=body,
                params=props,
                headers=headers,
                stream=True,
            )
            return response
        else:
            headers["Resoto-Shell-Command"] = command
            headers["Content-Type"] = "multipart/form-data; boundary=file-upload"

            with MultipartWriter(boundary="file-upload") as mpwriter:
                for name, path in files.items():
                    part = mpwriter.append(open(path, "rb"))
                    part.set_content_disposition("form-data", name=name)

                response = await self._post(
                    "/cli/execute",
                    data=mpwriter,
                    params=props,
                    headers=headers,
                    stream=True,
                )
                return response

    async def cli_execute(
        self,
        command: str,
        graph: Optional[str] = "resoto",
        section: Optional[str] = "reported",
        headers: Optional[Dict[str, str]] = None,
        files: Optional[FilenameLookup] = None,
        **env: str,
    ) -> AsyncIterator[JsValue]:
        """
        Execute a CLI command and return the result as a stream of text or JSON objects.

        Binary or multi-part responses will trigger an exception.
        """

        response = await self.cli_execute_raw(
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
                yield await response.text()
            elif content_type == "application/json":
                yield await response.json()
            elif content_type == "application/x-ndjson":
                async for line in response.async_iter_lines():
                    yield json_loadb(line)
            else:
                raise NotImplementedError(f"Unsupported content type: {content_type}. Use cli_execute_raw instead.")
        else:
            text = await response.text()
            raise AttributeError(text)

    async def cli_info(self) -> JsObject:
        response = await self._get("/cli/info")
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def configs(self) -> AsyncIterator[str]:
        response = await self._get("/configs", stream=True)
        if response.status_code == 200:
            async for line in response.async_iter_lines():
                yield json_loadb(line)
        else:
            raise AttributeError(await response.text())

    async def config(self, config_id: str) -> JsObject:
        response = await self._get(
            f"/config/{config_id}",
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def put_config(self, config_id: str, json: JsObject, validate: bool = True) -> JsObject:
        params = {"validate": "true" if validate else "false"}
        response = await self._put(
            f"/config/{config_id}",
            json=json,
            params=params,
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def patch_config(self, config_id: str, json: JsObject) -> JsObject:
        response = await self._patch(
            f"/config/{config_id}",
            json=json,
        )
        if response.status_code == 200:
            return await response.json()
        else:
            raise AttributeError(await response.text())

    async def delete_config(self, config_id: str) -> None:
        response = await self._delete(
            f"/config/{config_id}",
        )
        if response.status_code == 204:
            return None
        else:
            raise AttributeError(await response.text())

    async def get_configs_model(self) -> Model:
        response = await self._get("/configs/model")
        if response.status_code == 200:
            model_json = await response.json()
            model = json_load(model_json, Model)
            return model
        else:
            raise AttributeError(await response.text())

    async def update_configs_model(self, update: List[Kind]) -> Model:
        response = await self._patch(
            "/configs/model",
            json=json_dump(update),
        )
        model_json = await response.json()
        model = json_load(model_json, Model)
        return model

    async def list_configs_validation(self) -> AsyncIterator[str]:
        response = await self._get(
            "/configs/validation",
            stream=True,
        )
        async for line in response.async_iter_lines():
            yield json_loadb(line)

    async def get_config_validation(self, cfg_id: str) -> Optional[ConfigValidation]:
        response = await self._get(
            f"/config/{cfg_id}/validation",
        )
        return json_load(await response.json(), ConfigValidation)

    async def put_config_validation(self, cfg: ConfigValidation) -> ConfigValidation:
        response = await self._put(
            f"/config/{cfg.id}/validation",
            json=json_dump(cfg),
        )
        return json_load(await response.json(), ConfigValidation)

    async def ping(self) -> str:
        response = await self._get("/system/ping")
        if response.status_code == 200:
            return await response.text()
        else:
            raise AttributeError(await response.text())

    async def ready(self) -> str:
        response = await self._get("/system/ready", headers={"Accept": "text/plain"})
        if response.status_code == 200:
            return await response.text()
        else:
            raise AttributeError(await response.text())

    async def events(
        self, event_types: Optional[Set[str]] = None, send_events: Optional[Queue[JsObject]] = None
    ) -> AsyncIterator[JsObject]:
        params = {"show": ",".join(event_types)} if event_types else None
        async with self.http_client.websocket("/events", params, send_events) as incoming:  # type: ignore
            flag = True
            while flag:
                event = await incoming.get()
                if isinstance(event, PoisonPill):
                    flag = False
                else:
                    yield json.loads(event)


def rnd_str(str_len: int = 10) -> str:
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(str_len))
