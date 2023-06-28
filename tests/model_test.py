from resotoclient.json_utils import json_dump, json_load
from resotoclient.models import Property, Kind


def test_prop_js_roundtrip() -> None:
    prop = Property(name="foo", kind="string", required=True, metadata={"foo": "bar", "test": 42, "a": [1, 2, "test"]})
    kind = Kind("test", "test", [prop], ["test"], True, {"foo": ["bar"]}, {"a": 32, "b": "cde", "f": True, "g": None})
    again = json_load(json_dump(kind, Kind), Kind)
    assert kind == again
