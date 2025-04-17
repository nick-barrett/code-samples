from typing import Annotated, Any, Dict, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Discriminator, Field, RootModel

from veloapi.configmodules.edge_analytics import EdgeAnalyticsModule
from veloapi.configmodules.edge_atp import EdgeAtpModule
from veloapi.configmodules.edge_control import EdgeControlModule
from veloapi.configmodules.edge_device_settings import EdgeDeviceSettingsModule
from veloapi.configmodules.edge_firewall import EdgeFirewallModule
from veloapi.configmodules.edge_qos import EdgeQosModule
from veloapi.configmodules.edge_wan import EdgeWanModule
from veloapi.configmodules.profile_analytics import ProfileAnalyticsModule
from veloapi.configmodules.profile_atp import ProfileAtpModule
from veloapi.configmodules.profile_device_settings import ProfileDeviceSettingsModule
from veloapi.configmodules.profile_firewall import ProfileFirewallModule
from veloapi.configmodules.profile_qos import ProfileQosModule
from veloapi.configmodules.profile_wan import ProfileWanModule
from veloapi.pydantic_shared import (
    VcoDatetime,
    OptVcoDatetime,
    CamelModel,
    VcoVersion,
)

"""
from pydantic import BaseModel

# Example of how required/nullable fields are handled in Pydantic

class MyModel(BaseModel):
    not_required_and_nullable: str | None = None
    not_required_not_nullable: str = None
    required_but_nullable: str | None
    required_not_nullable: str

"""


JsonRpcRequestId = str | int


class JsonRpcRequest(BaseModel):
    id: JsonRpcRequestId = 1
    jsonrpc: Literal["2.0"] = Field(default="2.0")
    method: str
    params: dict[str, Any] | list[Any] = Field(default_factory=lambda: {})

    model_config = ConfigDict(extra="allow")


class JsonRpcErrorData(BaseModel):
    code: int
    message: str
    data: Any = None

    def __str__(self) -> str:
        if self.data is not None:
            return f"{self.code}: {self.message}\n{self.data}"
        else:
            return f"{self.code}: {self.message}"


class JsonRpcSuccess(BaseModel):
    id: JsonRpcRequestId
    jsonrpc: Literal["2.0"]
    result: dict[str, Any] | list[Any]

    model_config = ConfigDict(extra="allow")


class JsonRpcError(BaseModel):
    jsonrpc: Literal["2.0"]
    error: JsonRpcErrorData
    id: JsonRpcRequestId

    model_config = ConfigDict(extra="allow")


JsonRpcMessage = RootModel[JsonRpcRequest | JsonRpcSuccess | JsonRpcError]
JsonRpcResponse = RootModel[JsonRpcSuccess | JsonRpcError]


class EnterpriseObjectBase(CamelModel):
    id: int
    created: VcoDatetime
    operator_id: int | None
    network_id: int | None
    enterprise_id: int
    edge_id: int | None
    gateway_id: int | None
    parent_group_id: int | None
    description: str | None
    name: str
    logical_id: UUID
    alerts_enabled: int
    operator_alerts_enabled: int
    status: str | None  # Coerce to str?
    status_modified: OptVcoDatetime
    previous_data: Any
    previous_created: OptVcoDatetime
    last_contact: OptVcoDatetime
    version: VcoVersion
    modified: OptVcoDatetime


class NetworkSegmentBase(EnterpriseObjectBase):
    object: Literal["NETWORK_SEGMENT"]
    data: dict[str, Any]


class RegularNetworkSegment(NetworkSegmentBase):
    type: Literal["REGULAR"]
    data: dict[str, Any]


class CdeNetworkSegment(NetworkSegmentBase):
    type: Literal["CDE"]
    data: dict[str, Any]


class PrivateNetworkSegment(EnterpriseObjectBase):
    type: Literal["PRIVATE"]
    data: dict[str, Any]


NetworkSegment = Annotated[
    Union[RegularNetworkSegment, CdeNetworkSegment, PrivateNetworkSegment],
    Discriminator("type"),
]

NetworkServiceType = Literal[
    "dns",
    "cloudToCloudInterConnect",
    "netflowCollector",
    "netflowFilter",
    "prefixTag",
    "authentication",
    "edgeHub",
    "dataCenter",
    "nvsViaEdgeService",
    "cloudSecurityService",
    "iaasSubscription",
    "wssIntegration",
    "wssLocation",
]


class NetworkServiceBase(EnterpriseObjectBase):
    object: Literal["NETWORK_SERVICE"]
    data: Dict[str, Any]


class DnsNS(NetworkServiceBase):
    type: Literal["dns"]
    data: dict[str, Any]


class CloudToCloudInterConnectNS(NetworkServiceBase):
    type: Literal["cloudToCloudInterConnect"]
    data: dict[str, Any]


class NetflowCollectorNS(NetworkServiceBase):
    type: Literal["netflowCollector"]
    data: dict[str, Any]


class NetflowFilterNS(NetworkServiceBase):
    type: Literal["netflowFilter"]
    data: dict[str, Any]


class PrefixTagNS(NetworkServiceBase):
    type: Literal["prefixTag"]
    data: dict[str, Any]


class AuthenticationNS(NetworkServiceBase):
    type: Literal["authentication"]
    data: dict[str, Any]


class EdgeHubNS(NetworkServiceBase):
    type: Literal["edgeHub"]
    data: dict[str, Any]


class DataCenterNS(NetworkServiceBase):
    type: Literal["dataCenter"]
    data: dict[str, Any]


class NvsViaEdgeServiceNS(NetworkServiceBase):
    type: Literal["nvsViaEdgeService"]
    data: dict[str, Any]


class CloudSecurityServiceNS(NetworkServiceBase):
    type: Literal["cloudSecurityService"]
    data: dict[str, Any]


class IaasSubscriptionNS(NetworkServiceBase):
    type: Literal["iaasSubscription"]
    data: dict[str, Any]


class WssIntegrationNS(NetworkServiceBase):
    type: Literal["wssIntegration"]
    data: dict[str, Any]


NetworkService = Annotated[
    Union[
        DnsNS,
        CloudToCloudInterConnectNS,
        NetflowCollectorNS,
        NetflowFilterNS,
        PrefixTagNS,
        AuthenticationNS,
        EdgeHubNS,
        DataCenterNS,
        NvsViaEdgeServiceNS,
        CloudSecurityServiceNS,
        IaasSubscriptionNS,
        WssIntegrationNS,
    ],
    Discriminator("type"),
]

EnterprisePropertyType = Literal[
    "address_group",
    "port_group",
    "urlCategoryFiltering",
    "urlReputationFiltering",
    "maliciousIpFiltering",
    "idps",
    "securityServiceGroup",
]


class EnterprisePropertyBase(EnterpriseObjectBase):
    object: Literal["PROPERTY"]
    data: dict[str, Any]


class AddressGroup(EnterprisePropertyBase):
    type: Literal["address_group"]
    data: dict[str, Any]


class PortGroup(EnterprisePropertyBase):
    type: Literal["port_group"]
    data: dict[str, Any]


class UrlCatFiltering(EnterprisePropertyBase):
    type: Literal["urlCategoryFiltering"]
    data: dict[str, Any]


class UrlRepFiltering(EnterprisePropertyBase):
    type: Literal["urlReputationFiltering"]
    data: dict[str, Any]


class MaliciousIpFiltering(EnterprisePropertyBase):
    type: Literal["maliciousIpFiltering"]
    data: dict[str, Any]


class Idps(EnterprisePropertyBase):
    type: Literal["idps"]
    data: dict[str, Any]


class SecurityServiceGroup(EnterprisePropertyBase):
    type: Literal["securityServiceGroup"]
    data: dict[str, Any]


EnterpriseProperty = Annotated[
    Union[
        AddressGroup,
        PortGroup,
        UrlCatFiltering,
        UrlRepFiltering,
        MaliciousIpFiltering,
        Idps,
        SecurityServiceGroup,
    ],
    Discriminator("type"),
]


class PrivateNetwork(EnterpriseObjectBase):
    object: Literal["PRIVATE_NETWORK"]
    type: Literal[""]
    data: dict[str, Any]


EnterpriseObject = Annotated[
    Union[NetworkService, NetworkSegment, EnterpriseProperty, PrivateNetwork],
    Discriminator("object"),
]

type EndpointPkiMode = Literal[
    "CERTIFICATE_DISABLED", "CERTIFICATE_REQUIRED", "CERTIFICATE_OPTIONAL"
]

type BastionState = Literal[
    "UNCONFIGURED",
    "STAGE_REQUESTED",
    "UNSTAGE_REQUESTED",
    "STAGED",
    "UNSTAGED",
    "PROMOTION_REQUESTED",
    "PROMOTION_PENDING",
    "PROMOTED",
]

type ActivationState = Literal[
    "UNASSIGNED", "PENDING", "ACTIVATED", "REACTIVATION_PENDING"
]

type EdgeState = Literal[
    "NEVER_ACTIVATED", "DEGRADED", "OFFLINE", "DISABLED", "EXPIRED", "CONNECTED"
]

type ServiceState = Literal["IN_SERVICE", "OUT_OF_SERVICE", "PENDING_SERVICE"]

type HaState = Literal[
    "UNCONFIGURED",
    "PENDING_INIT",
    "PENDING_CONFIRMATION",
    "PENDING_CONFIRMED",
    "PENDING_DISSOCATION",
    "READY",
    "FAILED",
]


class Enterprise(CamelModel):
    id: int
    created: VcoDatetime
    network_id: int | None
    gateway_pool_id: int | None
    alerts_enabled: int
    operator_alerts_enabled: int
    endpoint_pki_mode: EndpointPkiMode
    name: str | None
    domain: str | None
    prefix: str | None
    logical_id: UUID
    account_number: str | None
    description: str | None
    contact_name: str | None
    contact_phone: str | None
    contact_mobile: str | None
    contact_email: str | None
    street_address: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    lat: float
    lon: float
    timezone: str
    bastion_state: BastionState
    modified: OptVcoDatetime


class Edge(CamelModel):
    id: int
    created: VcoDatetime
    enterprise_id: int
    enterprise_logical_id: UUID
    site_id: int | None
    activation_key: str | None
    activation_key_expires: OptVcoDatetime
    activation_state: ActivationState | None
    activation_time: OptVcoDatetime
    software_version: str
    build_number: str
    factory_software_version: str | None
    factory_build_number: str | None
    platform_firmware_version: str | None
    platform_firmware_build_number: str | None = None
    modem_firmware_version: str
    modem_build_number: str
    software_updated: OptVcoDatetime
    self_mac_address: str
    device_id: str | None
    logical_id: UUID | None
    serial_number: str | None
    model_number: str | None
    device_family: str | None
    lte_region: str | None
    name: str
    description: str | None
    alerts_enabled: int
    operator_alerts_enabled: int
    edge_state: EdgeState | None
    edge_state_time: OptVcoDatetime
    is_live: int
    system_up_since: OptVcoDatetime
    service_up_since: OptVcoDatetime
    last_contact: OptVcoDatetime
    service_state: ServiceState
    endpoint_pki_mode: EndpointPkiMode
    ha_state: HaState
    ha_previous_state: HaState
    ha_last_contact: OptVcoDatetime
    ha_serial_number: str | None
    bastion_state: BastionState
    modified: OptVcoDatetime
    custom_info: str | None
    ha_mode: str | None
    standby_system_up_since: OptVcoDatetime
    standby_service_up_since: OptVcoDatetime
    standby_software_version: str | None
    standby_factory_software_version: str | None
    standby_factory_build_number: str | None
    standby_build_number: str | None
    standby_model_number: str | None
    standby_device_id: str | None
    ha_wifi_capability_mismatch: int | None


class ProfileConfigurationPolicies(CamelModel):
    device_settings_enabled: bool
    biz_policy_enabled: bool
    firewall: Literal["enabled", "disabled"]


class EnterpriseConfigurationPolicy(CamelModel):
    id: int
    created: VcoDatetime
    name: str
    logical_id: UUID
    enterprise_logical_id: UUID
    version: VcoVersion
    description: str | None
    configuration_type: str
    bastion_state: BastionState
    schema_version: str
    effective: OptVcoDatetime
    modified: OptVcoDatetime
    is_staging: int
    edge_count: int
    policies: ProfileConfigurationPolicies
    has_quiesced_gateway_usage: bool | None = None


EdgeConfigurationModule = Annotated[
    Union[
        EdgeDeviceSettingsModule,
        EdgeWanModule,
        EdgeQosModule,
        EdgeFirewallModule,
        EdgeAnalyticsModule,
        EdgeAtpModule,
        EdgeControlModule,
    ],
    Discriminator("name"),
]


class EdgeConfigurationProfile(CamelModel):
    id: int
    created: VcoDatetime
    name: Literal["Edge Specific Profile"]
    logical_id: UUID
    enterprise_logical_id: UUID
    version: VcoVersion
    description: str | None
    configuration_type: str
    bastion_state: str
    schema_version: str
    effective: OptVcoDatetime
    modified: OptVcoDatetime
    modules: list[EdgeConfigurationModule]


EnterpriseConfigurationModule = Annotated[
    Union[
        ProfileDeviceSettingsModule,
        ProfileWanModule,
        ProfileQosModule,
        ProfileFirewallModule,
        ProfileAnalyticsModule,
        ProfileAtpModule,
    ],
    Discriminator("name"),
]


class EnterpriseConfigurationProfile(CamelModel):
    id: int
    created: VcoDatetime
    name: str
    logical_id: UUID
    enterprise_logical_id: UUID
    version: VcoVersion
    description: str | None
    configuration_type: str
    bastion_state: BastionState
    schema_version: str
    effective: OptVcoDatetime
    modified: OptVcoDatetime
    modules: list[EnterpriseConfigurationModule]


EdgeConfigurationStack = RootModel[
    tuple[EdgeConfigurationProfile, EnterpriseConfigurationProfile]
]
