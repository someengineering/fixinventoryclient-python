from dataclasses import dataclass, field
from typing import List, Optional, Mapping, Sequence, Union, Dict
from datetime import timedelta
from enum import Enum


@dataclass
class Kind:
    fqn: str
    runtime_kind: Optional[str]


@dataclass
class Model:
    kinds: Mapping[str, Kind]


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


JsValue = Union[
    str, int, float, bool, None, Mapping[str, "JsValue"], Sequence["JsValue"]
]

JsObject = Mapping[str, JsValue]


@dataclass
class ParsedCommands:
    commands: List[ParsedCommand]
    env: JsObject = field(default_factory=dict)


class ConfigValidation:
    id: str
    external_validation: bool = False
