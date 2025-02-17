from dataclasses import dataclass, field
from dataclasses_json import LetterCase
import dataclasses_json
from typing import NamedTuple, Optional
from datetime import datetime
from aiohttp import ClientSession

from veloapi.util import extract_module


@dataclass
class CommonData:
    vco: str
    token: str
    enterprise_id: int
    session: ClientSession

    def __post_init__(self):
        self.validate()

        self.session.headers.update({"Authorization": f"Token {self.token}"})

    def validate(self):
        if any(
            missing_inputs := [
                v is None for v in [self.vco, self.token, self.enterprise_id]
            ]
        ):
            raise ValueError(f"missing input data: {missing_inputs}")


@dataclass
class EdgeProvisionParams:
    name: str
    model_number: str
    configuration_id: int
    license_id: int
    contact_email: str
    contact_name: str
    ha_enabled: bool = False
    serial_number: str | None = None
    endpoint_pki_mode: str = "CERTIFICATE_OPTIONAL"
    analytics_mode: str = "SDWAN_ONLY"
    custom_info: str = ""
    description: str = ""

@dataclass
class Edge:
    id: int
    name: str
    lat: float
    lon: float
    profile_id: int
    profile_name: str
    primary_pop_name: Optional[str]
    primary_gw_name: Optional[str]


@dataclass
class EdgeLink:
    edge_name: str
    display_name: str
    interface_name: str
    internal_id: str
    logical_id: str


@dataclass
class EdgeLinkMetrics:
    edge_name: str
    display_name: str
    interface_name: str
    internal_id: str
    logical_id: str


@dataclass
class Gateway:
    name: str
    lat: float
    lon: float
    pop: str
    edge_ids: list[int]


@dataclass
class PopGateway:
    name: str


@dataclass
class Pop:
    name: str
    lat: float
    lon: float
    gateways: list[PopGateway]


@dataclass
class EdgeAssn:
    id: int
    name: str
    current_profile_id: int
    current_profile_name: str
    current_primary_pop: Optional[str] = None
    current_primary_gw: Optional[str] = None
    new_profile_id: Optional[int] = None
    new_profile_name: Optional[str] = None
    new_primary_pop: Optional[str] = None
    new_primary_gw: Optional[str] = None


@dataclass
class Profile:
    id: int
    name: str
    primary_gw: str
    # secondary_gw: Optional[str]


@dataclass
class LinkData:
    edge_id: int
    edge_name: str
    link_name: str
    latency_tx: float
    latency_rx: float
    loss_tx: float
    loss_rx: float
    jitter_tx: float
    jitter_rx: float


@dataclass
class EnterpriseEvent:
    timestamp: datetime
    event: str
    message: str
    detail: str
    edge_id: int | None = None
    edge_name: str | None = None


@dataclass
class EnterpriseEventV2:
    id: int | None
    timestamp: datetime
    event: str
    category: str
    severity: str
    message: str
    detail: str
    username: str | None
    edge_name: str | None


@dataclass
class EdgeFlowVisibilityRecord:
    start_time: datetime
    end_time: datetime
    application: int
    category: int
    bytes_rx: int
    bytes_tx: int
    flow_count: int
    business_policy_name: str
    firewall_rule_name: str
    segment_id: int
    client_hostname: str
    source_ip: str
    dest_ip: str
    dest_port: int
    transport: int
    dest_domain: str
    dest_fqdn: str
    isp: str
    link_id: int
    link_name: str
    next_hop: str
    route: str
    packets_rx: int
    packets_tx: int
    total_bytes: int
    total_packets: int

class EdgeFlowVisibilityNamedTuple(NamedTuple):
    start_time: datetime
    application: int
    category: int
    bytes_rx: int
    bytes_tx: int
    flow_count: int
    business_policy_name: str
    firewall_rule_name: str
    segment_id: int
    client_hostname: str
    source_ip: str
    dest_ip: str
    dest_port: int
    transport: int
    dest_domain: str
    dest_fqdn: str
    isp: str
    link_id: int
    link_name: str
    next_hop: str
    route: str
    packets_rx: int
    packets_tx: int
    total_bytes: int
    total_packets: int

@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseEdgeListCloudServiceSiteDataDataCentersMeta:
    region: str
    country: str
    city: str
    dc_name: str


@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseEdgeListCloudServiceSiteDataDataCenters:
    primary_meta: EnterpriseEdgeListCloudServiceSiteDataDataCentersMeta
    secondary_meta: EnterpriseEdgeListCloudServiceSiteDataDataCentersMeta
    tertiary_meta: EnterpriseEdgeListCloudServiceSiteDataDataCentersMeta


@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseEdgeListCloudServiceSiteData:
    data_centers: EnterpriseEdgeListCloudServiceSiteDataDataCenters


@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseEdgeListCloudServiceSite:
    data: EnterpriseEdgeListCloudServiceSiteData


@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseEdgeListCloudService:
    state: str
    site: EnterpriseEdgeListCloudServiceSite
    interface: str
    segment_name: str

@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ListEdgeHaData:
    cluster_id: int | None = None
    cluster_name: str | None = None

@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ListEdgeHa:
    data: ListEdgeHaData | None = None
    type: str | None = None

@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass()
class EnterpriseEdgeListEdge:
    id: int | None
    logical_id: str | None
    name: str | None
    edge_state: str | None
    activation_state: str | None
    is_hub: bool | None
    ha: ListEdgeHa | None = None
    # configuration: dict | None
    # cloud_services: list[EnterpriseEdgeListCloudService] | None


@dataclass
class VpnEdgeActionStatus:
    id: int


@dataclass
class ConfigModule:
    raw: dict
    id: int = field(init=False)
    name: str = field(init=False)
    data: dict[str, list | dict] = field(init=False)
    refs: dict[str, list | dict] = field(init=False)

    def __post_init__(self):
        self.id = self.raw["id"]
        self.name = self.raw["name"]
        self.data = self.raw["data"]
        self.refs = self.raw.get("refs", {})


@dataclass
class ConfigurationProfile:
    raw: dict
    id: int = field(init=False)
    name: str = field(init=False)
    device_settings: ConfigModule = field(init=False)
    qos: ConfigModule = field(init=False)
    firewall: ConfigModule = field(init=False)

    def __post_init__(self):
        self.id = self.raw["id"]
        self.name = self.raw["name"]

        device_settings = extract_module(self.raw["modules"], "deviceSettings")
        if device_settings is None:
            raise ValueError("deviceSettings is None")
        self.device_settings = ConfigModule(device_settings)

        qos = extract_module(self.raw["modules"], "QOS")
        if qos is None:
            raise ValueError("QOS is None")
        self.qos = ConfigModule(qos)

        firewall = extract_module(self.raw["modules"], "firewall")
        if firewall is None:
            raise ValueError("firewall is None")
        self.firewall = ConfigModule(firewall)


@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseGatewayConfigGateway:
    logical_id: str
    name: str
    software_version: str


@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseGatewayConfigSegment:
    name: str
    segment_id: int


@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class EnterpriseGatewayConfigResult:
    gateways: list[EnterpriseGatewayConfigGateway]
    segments: list[EnterpriseGatewayConfigSegment]

@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class GatewayRouteEntry:
    network_addr: str
    network_mask: str
    type: str
    peer_name: str
    reachable: bool
    metric: int
    preference: int
    flags: str
    age: int
    c_tag: int
    s_tag: int
    handoff: str
    mode: str
    lost_reason: str

@dataclasses_json.dataclass_json
@dataclass
class EdgeRouteEntry:
    route_type: str
    route_address: str
    route_netmask: str

@dataclasses_json.dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class GetEnterpriseResult:
    id: int
    created: str
    modified: str
    network_id: int
    gateway_pool_id: int
    alerts_enabled: int
    operator_alerts_enabled: int
    endpoint_pki_mode: str
    name: str
    domain: str
    prefix: str | None
    logical_id: str
    account_number: str
    """
    description": null,
    contactName": "Nick",
    contactPhone": null,
    contactMobile": "+1",
    contactEmail": "nick.barrett@broadcom.com",
    streetAddress": null,
    streetAddress2": null,
    city": null,
    state": null,
    postalCode": null,
    country": null,
    lat": 37.402866,
    lon": -122.117332,
    timezone": "America/Los_Angeles",
    locale": "en-US",
    bastionState": "UNCONFIGURED",
    """