from typing import Any

import jsons

from resotoclient.json_utils import json_dump, json_load
from resotoclient.models import Property, Kind, JsValue


def __identity(obj: JsValue, *args: Any, **kwargs: Any) -> JsValue:
    return obj


jsons.set_serializer(__identity, JsValue)  # type: ignore
jsons.set_deserializer(__identity, JsValue)  # type: ignore


def test_prop_js_roundtrip() -> None:
    prop = Property(name="foo", kind="string", required=True, metadata={"foo": "bar", "test": 42, "a": [1, 2, "test"]})
    kind = Kind("test", "test", [prop], ["test"], True, {"foo": ["bar"]}, {"a": 32, "b": "cde", "f": True, "g": None})
    again = json_load(json_dump(kind, Kind), Kind)
    assert kind == again
