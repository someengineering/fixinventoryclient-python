from typing import Optional, Type, TypeVar, Any
import jsons
import json

from resotoclient.models import JsValue

T = TypeVar("T")

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false


def json_load(json_obj: object, cls: Type[T]) -> T:
    return jsons.load(json_obj, cls)  # type: ignore


def json_loadb(
    json_obj: bytes,
    cls: Optional[Type[T]] = None,
) -> T:
    # jsons tries to be clever reading strings into datetime objects
    return json.loads(json_obj) if cls is None else jsons.loadb(json_obj, cls)  # type: ignore


def json_dump(
    obj: object,
    cls: Optional[type] = None,
) -> JsValue:
    return jsons.dump(obj, cls)  # type: ignore


def __identity(obj: JsValue, *args: Any, **kwargs: Any) -> JsValue:
    return obj


jsons.set_serializer(__identity, JsValue)
jsons.set_deserializer(__identity, JsValue)
