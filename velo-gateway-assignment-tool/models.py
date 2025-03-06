from dataclasses import dataclass


@dataclass
class PopLocation:
    name: str
    lat: float
    lon: float


@dataclass
class EdgeLocation:
    name: str
    lat: float
    lon: float


@dataclass
class EdgeLocationPop:
    name: str
    distance: float


@dataclass
class EdgeLocationFull:
    name: str
    lat: float
    lon: float
    pops: list[EdgeLocationPop]


@dataclass
class PopPair:
    pri: str
    sec: str
    edges: list[EdgeLocation]


@dataclass
class PopTotal:
    name: str
    edge_count: int
    tunnel_count: int = 0
    gateway_count: int = 0


@dataclass
class Edge:
    name: str
    primary_gw: int
    secondary_gw: int


@dataclass
class Gateway:
    index: int
    pop: str
    edge_count: int


@dataclass
class Pop:
    name: str
    gateway_count: int
    gateways: list[int]


@dataclass
class NetworkPartition:
    name: str
    pops: dict[str, Pop]
    gateways: dict[int, Gateway]
    gateway_count: int
    edge_count: int
    edges: dict[str, Edge]


@dataclass
class GatewayOutput:
    name: str
    edge_count: int


@dataclass
class PopOutput:
    name: str
    gateway_count: int


@dataclass
class EdgeOutput:
    name: str
    pri_gw: str
    sec_gw: str


@dataclass
class NetworkPartitionOutput:
    name: str
    pops: list[PopOutput]
    gateways: list[GatewayOutput]
    gateway_count: int
    edge_count: int
    edges: list[EdgeOutput]
