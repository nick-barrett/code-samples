import uuid
import json
import asyncio
import dataclasses
import logging
from typing import Any, Literal
import dataclasses_json
import dotenv
import aiohttp
import yaml
from copy import deepcopy

from veloapi.models import CommonData, EdgeProvisionParams
from veloapi.util import extract_module, read_env
from veloapi.api import (
    edge_provision,
    get_enterprise_edge_list_full_dict,
    get_edge_configuration_stack,
    insert_configuration_module,
    update_configuration_module,
)

model_data = {}
vnf_models = set(
    ["edge5X0", "edge6X0", "edge840", "edge1000qat", "edge3X00", "edge3X10"]
)

@dataclasses.dataclass
class ConfigModule:
    raw: dict
    id: int = dataclasses.field(init=False)
    name: str = dataclasses.field(init=False)
    data: dict[str, list | dict] = dataclasses.field(init=False)
    refs: dict[str, list | dict] = dataclasses.field(init=False)

    def __post_init__(self):
        self.id = self.raw["id"]
        self.name = self.raw["name"]
        self.data = self.raw["data"]
        self.refs = self.raw["refs"] if "refs" in self.raw else {}


@dataclasses.dataclass
class ConfigProfile:
    raw: dict
    id: int = dataclasses.field(init=False)
    name: str = dataclasses.field(init=False)
    device_settings: ConfigModule = dataclasses.field(init=False)
    qos: ConfigModule | None = dataclasses.field(init=False)
    firewall: ConfigModule | None = dataclasses.field(init=False)

    def __post_init__(self):
        self.id = self.raw["id"]
        self.name = self.raw["name"]

        device_settings = extract_module(self.raw["modules"], "deviceSettings")
        if device_settings is None:
            raise ValueError("deviceSettings is None")
        self.device_settings = ConfigModule(device_settings)

        qos = extract_module(self.raw["modules"], "QOS")
        if qos is not None:
            self.qos = ConfigModule(qos)

        firewall = extract_module(self.raw["modules"], "firewall")
        if firewall is not None:
            self.firewall = ConfigModule(firewall)


type EdgeModelName = str
type InterfaceName = str
type InterfaceMap = dict[InterfaceName, InterfaceName]
type EdgeName = str
type MapName = str


@dataclasses.dataclass
class DeviceMap:
    name: MapName
    source_model: EdgeModelName
    target_model: EdgeModelName
    interface_map: InterfaceMap


@dataclasses.dataclass
class EdgeEntry:
    name: EdgeName
    device_map: DeviceMap

    profile_config: ConfigProfile | None = None

    source_edge_data: dict[str, Any] | None = None
    source_edge_config: ConfigProfile | None = None

    target_edge_data: dict[str, Any] | None = None
    target_edge_config: ConfigProfile | None = None


@dataclasses.dataclass
class Config:
    device_maps: list[DeviceMap]
    edge_entries: list[EdgeEntry]
    device_maps_dict: dict[MapName, DeviceMap] = dataclasses.field(
        init=False, default_factory=dict
    )
    edge_entries_dict: dict[EdgeName, EdgeEntry] = dataclasses.field(
        init=False, default_factory=dict
    )

    def __post_init__(self):
        self.device_maps_dict = {m.name: m for m in self.device_maps}
        self.edge_entries_dict = {e.name: e for e in self.edge_entries}


def load_model_data(raw_model_data: Any):
    model_data.update(raw_model_data)

def load_config(raw_cfg: Any) -> Config:

    device_maps: list[DeviceMap] = []
    for raw_dm in raw_cfg["device_maps"]:
        dm = DeviceMap(
            raw_dm["name"],
            raw_dm["source_model"],
            raw_dm["target_model"],
            raw_dm["interface_map"],
        )
        device_maps.append(dm)

    c = Config(device_maps, [])

    edge_entries: list[EdgeEntry] = []

    for raw_edge in raw_cfg["edges"]:
        dm_name = raw_edge["device_map"]
        edge = EdgeEntry(raw_edge["name"], c.device_maps_dict[dm_name])
        edge_entries.append(edge)

    c = Config(device_maps, edge_entries)

    return c


def model_contains_intf(model: EdgeModelName, intf: InterfaceName) -> bool:
    in_routed = intf in model_data.get(model, {}).get("routedInterfaces", [])
    in_switched = intf in map(
        lambda x: x["name"],
        model_data.get(model, {}).get("lan", {}).get("interfaces", []),
    )

    return in_routed or in_switched


def validate_config(config: Config) -> bool:
    for map in config.device_maps:
        if map.source_model not in model_data:
            logging.error(f"Model {map.source_model} not known")
            return False
        if map.target_model not in model_data:
            logging.error(f"Model {map.target_model} not known")
            return False
        for source_intf, dest_intf in map.interface_map.items():
            if not model_contains_intf(map.source_model, source_intf):
                logging.error(
                    f"Interface {source_intf} not found in model {map.source_model}"
                )
                return False
            if not model_contains_intf(map.target_model, dest_intf):
                logging.error(
                    f"Interface {dest_intf} not found in model {map.target_model}"
                )
                return False
        if len(set(map.interface_map.values())) != len(map.interface_map.keys()):
            logging.error(f"Duplicate target interfaces in map {map.name}")
            return False
    return True


def get_default_client_prefix_delegation() -> dict[str, Any]:
    return {"enabled": False, "tag": None, "tagLogicalId": None}


def get_default_v6_detail():
    return {
        "addressing": {
            "cidrPrefix": None,
            "netmask": None,
            "type": "DHCP_STATELESS",
            "gateway": None,
            "cidrIp": None,
            "interfaceAddress": None,
            "tag": None,
            "tagLogicalId": None,
        },
        "wanOverlay": "AUTO_DISCOVERED",
        "trusted": False,
        "natDirect": True,
        "rpf": "SPECIFIC",
        "ospf": get_default_routed_intf_ospf(),
        "clientPrefixDelegation": get_default_client_prefix_delegation(),
    }


def get_default_routed_intf_addressing(
    typ: Literal["DHCP", "STATIC", "PPPOE"]
) -> dict[str, Any]:
    addressing = {"type": typ}
    if typ == "DHCP":
        addressing["cidrPrefix"] = None
        addressing["cidrIp"] = None
        addressing["netmask"] = None
        addressing["gateway"] = None
    elif typ == "STATIC":
        addressing["cidrPrefix"] = None
        addressing["cidrIp"] = None
        addressing["netmask"] = None
        addressing["gateway"] = None
    elif typ == "PPPOE":
        addressing["cidrPrefix"] = None
        addressing["cidrIp"] = None
        addressing["netmask"] = None
        addressing["gateway"] = None
        addressing["username"] = None
        addressing["password"] = None
    return addressing


def get_default_routed_intf_ospf() -> dict[str, Any]:
    return {
        "enabled": False,
        "area": 0,
        "authentication": False,
        "authId": 0,
        "authPassphrase": "",
        "helloTimer": 10,
        "deadTimer": 40,
        "mode": "BCAST",
        "enableBfd": False,
        "md5Authentication": False,
        "cost": 1,
        "MTU": 1380,
        "passive": False,
        "exclusionRoutes": [],
        "inboundRouteLearning": {"defaultAction": "LEARN", "filters": []},
        "outboundRouteAdvertisement": {"defaultAction": "IGNORE", "filters": []},
    }


def get_default_routed_intf_multicast() -> dict[str, Any]:
    return {
        "igmp": {
            "enabled": False,
            "type": "IGMP_V2",
        },
        "pim": {
            "enabled": False,
            "type": "PIM_SM",
        },
        "pimHelloTimerSeconds": None,
        "pimKeepAliveTimerSeconds": None,
        "pimPruneIntervalSeconds": None,
        "igmpHostQueryIntervalSeconds": None,
        "igmpMaxQueryResponse": None,
    }


def get_default_intf_l2(
    model: str, addressing: Literal["DHCP", "STATIC", "PPPOE"]
) -> dict[str, Any]:
    is_pppoe = addressing == "PPPOE"

    l2 = {}
    if model == "edge500":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge5X0":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge510" or model == "edge510lte":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge6X0" or model == "edge610lte":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge710":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge7105g":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge7X0":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge840":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge1000":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge1000qat":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge3X00":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge3X10":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge4100":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "edge5100":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    elif model == "virtual":
        l2 = {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1492 if is_pppoe else 1500,
            "losDetection": False,
            "probeInterval": "3",
        }
    return l2


def get_default_cellular(name: str) -> dict[str, Any] | None:
    return (
        {
            "simPin": "",
            "network": "",
            "apn": "",
            "iptype": "IPv4v6",
            "username": "",
            "password": "",
        }
        if name.startswith("CELL")
        else None
    )


def get_default_routed_interface(name: str, model: str) -> dict[str, Any]:
    intf = {
        "name": name,
        "disableV4": False,
        "disableV6": True,
        "overlayPreference": "IPv4",
        "v6Detail": get_default_v6_detail(),
        "disabled": False,
        "addressing": get_default_routed_intf_addressing("DHCP"),
        "wanOverlay": "AUTO_DISCOVERED",
        "encryptOverlay": True,
        "radiusAuthentication": {"enabled": False, "macBypass": [], "aclCheck": False},
        "advertise": False,
        "natDirect": True,
        "pingResponse": True,
        "evdslModemAttached": False,
        "trusted": False,
        "rpf": "SPECIFIC",
        "ospf": get_default_routed_intf_ospf(),
        "multicast": get_default_routed_intf_multicast(),
        "vlanId": None,
        "underlayAccounting": True,
        "segmentId": -1,
        "l2": get_default_intf_l2(model, "DHCP"),
    }

    cell = get_default_cellular(name)
    if cell is not None:
        intf["cellular"] = cell

    return intf


def get_default_wireless_interface(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": "wireless",
        "ssid": "vc-wifi",
        "broadcastSsid": True,
        "securityMode": "WPA2Personal",
        "cwp": False,
        "passphrase": "vcsecret",
        "vlanIds": [1],
        "disabled": True,
        "l2": {
            "autonegotiation": True,
            "speed": "100M",
            "duplex": "FULL",
            "MTU": 1500,
            "losDetection": False,
            "probeInterval": "3",
        },
        "macAllowlist": {
            "enabled": False,
            "enableMACFilteringForAPProbes": True,
            "allowedMacs": [],
        },
        "radiusAclCheck": False,
    }


def get_default_model_config(edge: EdgeEntry, model: EdgeModelName) -> dict[str, Any]:
    return {
        "routedInterfaces": [
            get_default_routed_interface(name, model)
            for name in model_data[model]["routedInterfaces"]
        ],
        "lan": model_data[model]["lan"],
    }


def find_switched(cfg: dict[str, Any], name: str) -> int | None:
    if "lan" in cfg and "interfaces" in cfg["lan"]:
        for index, intf in enumerate(cfg["lan"]["interfaces"]):
            if intf["name"] == name:
                return index
    return None


def find_routed(cfg: dict[str, Any], name: str) -> int | None:
    for index, intf in enumerate(cfg["routedInterfaces"]):
        if intf["name"] == name:
            return index
    return None


def fix_profile_model_intf(
    source_cfg: dict[str, Any],
    source_intf: str,
    dest_cfg: dict[str, Any],
    dest_intf: str,
):
    source_switched_index = find_switched(source_cfg, source_intf)
    source_routed_index = (
        find_routed(source_cfg, source_intf) if source_switched_index is None else None
    )

    dest_switched_index = find_switched(dest_cfg, dest_intf)
    dest_routed_index = (
        find_routed(dest_cfg, dest_intf) if dest_switched_index is None else None
    )

    if source_switched_index is not None and dest_routed_index is not None:
        dest_cfg["routedInterfaces"].pop(dest_routed_index)
        new_sw_intf = deepcopy(source_cfg["lan"]["interfaces"][source_switched_index])
        new_sw_intf["name"] = dest_intf
        dest_cfg["lan"]["interfaces"].append(new_sw_intf)
    elif source_routed_index is not None and dest_switched_index is not None:
        dest_cfg["lan"]["interfaces"].pop(dest_switched_index)
        new_routed_intf = deepcopy(source_cfg["routedInterfaces"][source_routed_index])
        new_routed_intf["name"] = dest_intf
        dest_cfg["routedInterfaces"].append(new_routed_intf)
    elif source_switched_index is not None and dest_switched_index is not None:
        sw_intf = deepcopy(source_cfg["lan"]["interfaces"][source_switched_index])
        sw_intf["name"] = dest_intf
        dest_cfg["lan"]["interfaces"][dest_switched_index] = sw_intf
    elif source_routed_index is not None and dest_routed_index is not None:
        routed_intf = deepcopy(source_cfg["routedInterfaces"][source_routed_index])
        routed_intf["name"] = dest_intf
        dest_cfg["routedInterfaces"][dest_routed_index] = routed_intf


async def fix_profile(common: CommonData, edge: EdgeEntry):
    device_settings = edge.profile_config.device_settings
    models = device_settings.data["models"]

    if edge.device_map.target_model in models:
        # don't change the model - it may be in use by other edges
        return

    cfg = get_default_model_config(edge, edge.device_map.target_model)

    networks = device_settings.data["lan"]["networks"]
    vlan_id = next(iter(networks), {}).get("vlanId", None)

    sw_intfs = cfg["lan"]["interfaces"]

    if vlan_id is not None:
        for intf in sw_intfs:
            intf["vlanIds"] = [vlan_id]
    else:
        logging.info(
            "No switched VLAN found in profile, converting default switched interfaces to routed so that validation passes."
        )
        cfg["lan"]["interfaces"] = []
        new_routed_intfs = [
            get_default_routed_interface(
                intf["name"], edge.device_map.target_model
            )
            for intf in sw_intfs
        ]
        new_routed_intfs.extend(cfg["routedInterfaces"])
        cfg["routedInterfaces"] = new_routed_intfs

    models[edge.device_map.target_model] = cfg

    source_cfg = device_settings.data["models"][edge.device_map.source_model]

    for source_intf, dest_intf in edge.device_map.interface_map.items():
        fix_profile_model_intf(source_cfg, source_intf, cfg, dest_intf)

    cfg["routedInterfaces"] = sorted(cfg["routedInterfaces"], key=lambda x: x["name"])
    cfg["lan"]["interfaces"] = sorted(cfg["lan"]["interfaces"], key=lambda x: x["name"])

    await update_configuration_module(common, device_settings.id, device_settings.data, None)


async def create_target_edge(common: CommonData, edge: EdgeEntry) -> int:
    license_id = edge.source_edge_data["licenses"][0]["id"]
    contact_email = edge.source_edge_data["site"]["contactEmail"]
    contact_name = edge.source_edge_data["site"]["contactName"]

    provision_params = EdgeProvisionParams(
        f"{edge.name} (migrated to {edge.device_map.target_model})",
        edge.device_map.target_model,
        edge.profile_config.id,
        license_id,
        contact_email,
        contact_name,
        False,
    )

    rv = await edge_provision(common, provision_params)

    return rv["id"]


async def update_edge_firewall(common: CommonData, edge: EdgeEntry):
    if edge.source_edge_config.firewall is None:
        return

    target_fw = edge.target_edge_config.firewall
    new_fw = deepcopy(edge.source_edge_config.firewall)

    for seg in new_fw.data["segments"]:
        for rule in seg["outbound"]:
            match = rule["match"]
            s_intf = match.get("sInterface", None)
            d_intf = match.get("dInterface", None)
            match["sInterface"] = edge.device_map.interface_map.get(s_intf, s_intf)
            match["dInterface"] = edge.device_map.interface_map.get(d_intf, d_intf)

            if "ruleLogicalId" in rule:
                del rule["ruleLogicalId"]

    for rule in new_fw.data["inbound"]:
        if "ruleLogicalId" in rule:
            del rule["ruleLogicalId"]

        action = rule["action"]
        intf = action["interface"]
        action["interface"] = edge.device_map.interface_map.get(intf, intf)

    await update_configuration_module(common, target_fw.id, new_fw.data)


async def update_edge_qos(common: CommonData, edge: EdgeEntry):
    # QOS module is never created during edge provision
    source_qos = deepcopy(edge.source_edge_config.qos)
    if source_qos is None:
        return

    source_ds_data = edge.source_edge_config.device_settings
    target_ds_data = edge.target_edge_config.device_settings

    # translate interface references
    for seg in source_qos.data["segments"]:
        segment_id = seg["segment"]["segmentId"]
        for rule in seg["rules"]:
            if "ruleLogicalId" in rule:
                del rule["ruleLogicalId"]

            # translate match clause
            match = rule["match"]
            s_intf = match.get("sInterface", None)
            d_intf = match.get("dInterface", None)
            if s_intf in edge.device_map.interface_map:
                match["sInterface"] = edge.device_map.interface_map[s_intf]
            if d_intf in edge.device_map.interface_map:
                match["dInterface"] = edge.device_map.interface_map[d_intf]

            # translate action clause
            action = rule["action"]
            flow_paths = [
                "edge2CloudRouteAction",
                "edge2DataCenterRouteAction",
                "edge2EdgeRouteAction",
            ]

            logged_cos = False
            logged_wanlink = False

            for fp_name in flow_paths:
                fp = action.get(fp_name, None)
                intf = fp.get("interface", None)
                if intf is not None and intf != "auto":
                    if intf in edge.device_map.interface_map:
                        fp["interface"] = edge.device_map.interface_map[intf]

                icmp_logical_id = fp.get("icmpLogicalId", None)
                if icmp_logical_id is not None:
                    # get probe name from source device settings
                    source_seg = next(
                        iter(
                            [
                                s
                                for s in source_ds_data["segments"]
                                if s["segmentId"] == segment_id
                            ]
                        ),
                        {},
                    )
                    source_probe = next(
                        iter(
                            [
                                probe
                                for probe in source_seg.get("routes", {}).get(
                                    "icmpProbes", []
                                )
                                if probe["logicalId"] == icmp_logical_id
                            ]
                        ),
                        None,
                    )
                    probe_name = (
                        source_probe["name"] if source_probe is not None else None
                    )

                    # get probe from target device settings
                    target_seg = next(
                        iter(
                            [
                                s
                                for s in target_ds_data["segments"]
                                if s["segmentId"] == segment_id
                            ]
                        ),
                        {},
                    )
                    target_probe = next(
                        iter(
                            [
                                probe
                                for probe in target_seg.get("routes", {}).get(
                                    "icmpProbes", []
                                )
                                if probe["name"] == probe_name
                            ]
                        ),
                        None,
                    )
                    probe_logical_id = (
                        target_probe["logicalId"] if target_probe is not None else None
                    )

                    # update with target probe logical ID
                    fp["icmpLogicalId"] = probe_logical_id

                link_cos_logical_id = fp.get("linkCosLogicalId", None)
                if link_cos_logical_id is not None:
                    if not logged_cos:
                        logging.warning(
                            "business policy link COS actions are not implemented"
                        )
                        logged_cos = True
                    fp["linkCosLogicalId"] = None

                wan_link_name = fp.get("wanLinkName", None)
                if wan_link_name is not None and wan_link_name != "":
                    if not logged_wanlink:
                        logging.warning(
                            "business policy WAN link steering actions are not implemented. Check policy names to resolve steering once WAN links are created."
                        )
                        rule["name"] = (
                            f"{rule["name"]} - steer {fp["linkPolicy"]} {wan_link_name}"
                        )
                        logged_wanlink = True
                    fp["wanLinkName"] = ""
                    fp["linkPolicy"] = "auto"

                link_internal_logical_id = fp.get("linkInternalLogicalId", None)
                if (
                    link_internal_logical_id is not None
                    and link_internal_logical_id != "auto"
                ):
                    if not logged_wanlink:
                        logging.warning(
                            "business policy WAN link steering actions are not implemented"
                        )
                        logged_wanlink = True
                    fp["linkInternalLogicalId"] = "auto"
                    fp["linkPolicy"] = "auto"

                wan_link = fp.get("wanlink", None)
                if wan_link is not None and wan_link != "auto":
                    if not logged_wanlink:
                        logging.warning(
                            "business policy WAN link steering actions are not implemented"
                        )
                        logged_wanlink = True
                    fp["wanlink"] = "auto"
                    fp["linkPolicy"] = "auto"

    new_qos_module = await insert_configuration_module(
        common, edge.target_edge_config.id, "QOS", source_qos.data, True
    )
    edge.target_edge_config.qos = ConfigModule(new_qos_module)


def clean_ref(name: str, ref: dict, config_id: int, module_id: int) -> dict:
    keep_keys = [
        "enterpriseObjectId",
        "segmentObjectId",
        "segmentLogicalId",
        "ref",
        "logicalId",
    ]
    new_ref = {k: ref[k] for k in keep_keys if k in ref}
    new_ref["configurationId"] = config_id
    new_ref["moduleId"] = module_id
    return new_ref


async def update_edge_device_settings(common: CommonData, edge: EdgeEntry):
    target_ds = edge.target_edge_config.device_settings

    new_ds = deepcopy(edge.source_edge_config.device_settings)

    r_intf_to_delete = []
    sw_intf_to_delete = []

    # mark interfaces for deletion if they're not in the device map
    # apply name translation to interfaces which are in the device map
    for index, r_intf in enumerate(new_ds.data["routedInterfaces"]):
        source_name = r_intf["name"]
        if source_name not in edge.device_map.interface_map:
            r_intf_to_delete.append(index)
        else:
            r_intf["name"] = edge.device_map.interface_map[source_name]
    for index, sw_intf in enumerate(new_ds.data["lan"]["interfaces"]):
        source_name = sw_intf["name"]
        if source_name not in edge.device_map.interface_map:
            sw_intf_to_delete.append(index)
        else:
            sw_intf["name"] = edge.device_map.interface_map[source_name]

    for index in reversed(r_intf_to_delete):
        new_ds.data["routedInterfaces"].pop(index)

    for index in reversed(sw_intf_to_delete):
        new_ds.data["lan"]["interfaces"].pop(index)

    # get list of interfaces in the target device model
    target_model_intfs = []

    target_model_intfs.extend(
        model_data[edge.device_map.target_model]["routedInterfaces"]
    )
    target_model_intfs.extend(
        [
            intf["name"]
            for intf in model_data[edge.device_map.target_model]["lan"][
                "interfaces"
            ]
        ]
    )

    for model_intf in target_model_intfs:
        if model_intf not in edge.device_map.interface_map.values():
            target_routed = find_routed(target_ds.data, model_intf)
            target_switched = find_switched(target_ds.data, model_intf)

            if target_routed is not None:
                new_ds.data["routedInterfaces"].append(
                    target_ds.data["routedInterfaces"][target_routed]
                )
            elif target_switched is not None:
                new_ds.data["lan"]["interfaces"].append(
                    target_ds.data["lan"]["interfaces"][target_switched]
                )
            else:
                logging.error(
                    f"Unknown interface {model_intf} in target model {edge.device_map.target_model}"
                )

    # re-sort routed & lan interfaces
    new_ds.data["routedInterfaces"] = sorted(
        new_ds.data["routedInterfaces"], key=lambda x: x["name"]
    )
    new_ds.data["lan"]["interfaces"] = sorted(
        new_ds.data["lan"]["interfaces"], key=lambda x: x["name"]
    )

    management_intf = (
        new_ds.data.get("lan", {})
        .get("managementTraffic", {})
        .get("sourceInterface", None)
    )
    if management_intf is not None:
        s_intf, sep, sub_intf = management_intf.partition(":")
        new_ds.data["lan"]["managementTraffic"]["sourceInterface"] = "{}{}{}".format(
            edge.device_map.interface_map.get(s_intf, s_intf), sep, sub_intf
        )

    if "vnfs" in new_ds.data:
        del new_ds.data["vnfs"]

    if "ntp" in new_ds.data:
        ntp = new_ds.data["ntp"]
        s_intf = ntp.get("sourceInterface", None)
        if s_intf is not None:
            s_intf, sep, sub_intf = s_intf.partition(":")
            ntp["sourceInterface"] = "{}{}{}".format(
                edge.device_map.interface_map.get(s_intf, s_intf), sep, sub_intf
            )

    for seg in new_ds.data["segments"]:
        probe_map = {}
        routes = seg.get("routes", {})

        for probe in routes.get("icmpProbes", []):
            new_logical_id = str(uuid.uuid4())
            old_logical_id = probe.get("logicalId", new_logical_id)

            probe["logicalId"] = new_logical_id
            probe_map[old_logical_id] = new_logical_id

        for responder in routes.get("icmpResponders", []):
            responder["logicalId"] = str(uuid.uuid4())

        if "nsd" in routes:
            routes["nsd"] = []

        if "nsdV6" in routes:
            routes["nsdV6"] = []

        for static_rt in routes.get("static", []):
            if "icmpProbeLogicalId" in static_rt:
                static_rt["icmpProbeLogicalId"] = probe_map.get(
                    static_rt["icmpProbeLogicalId"], None
                )
            if "wanInterface" in static_rt:
                static_rt["wanInterface"] = edge.device_map.interface_map.get(
                    static_rt["wanInterface"], static_rt["wanInterface"]
                )

        for static_rt in routes.get("staticV6", []):
            if "icmpProbeLogicalId" in static_rt:
                static_rt["icmpProbeLogicalId"] = probe_map.get(
                    static_rt["icmpProbeLogicalId"], None
                )
            if "wanInterface" in static_rt:
                static_rt["wanInterface"] = edge.device_map.interface_map.get(
                    static_rt["wanInterface"], static_rt["wanInterface"]
                )

        bgp = seg.get("bgp", None)
        if bgp is not None:
            filter_map = {}
            for filter in bgp["filters"]:
                old_logical_id = filter["id"]
                new_logical_id = str(uuid.uuid4())
                filter_map[old_logical_id] = new_logical_id
                filter["id"] = new_logical_id

            for neighbor in bgp["neighbors"]:
                neighbor["id"] = str(uuid.uuid4())

                inbound_filters = neighbor["inboundFilter"].get("ids", [])
                neighbor["inboundFilter"]["ids"] = [
                    filter_map.get(f, f) for f in inbound_filters
                ]

                outbound_filters = neighbor["outboundFilter"].get("ids", [])
                neighbor["outboundFilter"]["ids"] = [
                    filter_map.get(f, f) for f in outbound_filters
                ]

            for neighbor in bgp.get("v6Detail", {}).get("neighbors", []):
                neighbor["id"] = str(uuid.uuid4())

                inbound_filters = neighbor["inboundFilter"].get("ids", [])
                neighbor["inboundFilter"]["ids"] = [
                    filter_map.get(f, f) for f in inbound_filters
                ]

                outbound_filters = neighbor["outboundFilter"].get("ids", [])
                neighbor["outboundFilter"]["ids"] = [
                    filter_map.get(f, f) for f in outbound_filters
                ]

        if (edge_direct := seg.get("edgeDirect", None)) is not None:
            for provider in edge_direct.get("providers", []):
                if len(provider.get("sites", [])) > 0:
                    logging.warning(
                        "NSD via edge site provisioning must be done after WAN links are created"
                    )
                    provider["sites"] = []
            if (provider := edge_direct.get("provider", None)) is not None:
                if len(provider.get("sites", [])) > 0:
                    logging.warning(
                        "NSD via edge site provisioning must be done after WAN links are created"
                    )
                if "sites" in provider:
                    del provider["sites"]

        for collector in seg.get("netflow", {}).get("collectors", []):
            s_intf = collector.get("sourceInterface", None)
            if s_intf is not None:
                s_intf, sep, sub_intf = s_intf.partition(":")
                collector["sourceInterface"] = "{}{}{}".format(
                    edge.device_map.interface_map.get(s_intf, s_intf),
                    sep,
                    sub_intf,
                )

        for collector in seg.get("syslog", {}).get("collectors", []):
            s_intf = collector.get("sourceInterface", None)
            if s_intf is not None:
                s_intf, sep, sub_intf = s_intf.partition(":")
                collector["sourceInterface"] = "{}{}{}".format(
                    edge.device_map.interface_map.get(s_intf, s_intf),
                    sep,
                    sub_intf,
                )

        auth_s_intf = seg.get("authentication", {}).get("sourceInterface", None)
        if auth_s_intf is not None:
            s_intf, sep, sub_intf = auth_s_intf.partition(":")
            seg["authentication"]["sourceInterface"] = "{}{}{}".format(
                edge.device_map.interface_map.get(s_intf, s_intf), sep, sub_intf
            )

    # TODO: write common function for these sub-interface renames

    new_ds_refs_clean = {}
    for name, ref in new_ds.refs.items():
        if isinstance(ref, list):
            new_ds_refs_clean[name] = [
                clean_ref(name, r, edge.target_edge_config.id, target_ds.id)
                for r in ref
            ]
        else:
            new_ds_refs_clean[name] = clean_ref(
                name, ref, edge.target_edge_config.id, target_ds.id
            )

    await update_configuration_module(
        common, target_ds.id, new_ds.data, new_ds_refs_clean
    )


async def update_target_config(
    common: CommonData, edge: EdgeEntry, target_edge_id: int
):
    config_stack = await get_edge_configuration_stack(common, target_edge_id)
    edge.target_edge_config = ConfigProfile(config_stack[0])

    await update_edge_device_settings(common, edge)
    await update_edge_qos(common, edge)
    await update_edge_firewall(common, edge)


async def main(session: aiohttp.ClientSession):
    data = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    with open("model-data.json", "r") as f:
        load_model_data(json.load(f))

    with open("config-migration.yaml", "r") as f:
        config = load_config(yaml.safe_load(f))

    if not validate_config(config):
        logging.error("Config validation failed")
        return

    for dm in config.device_maps:
        print("device map {}".format(dm.name))
        print("  source model: {}".format(dm.source_model))
        print("  target model: {}".format(dm.target_model))
        print("  interface map:")
        for k, v in dm.interface_map.items():
            print("    {} -> {}".format(k, v))

    # 0. get edge list and ensure all edges exist
    async for edge in get_enterprise_edge_list_full_dict(
        data, ["licenses", "site"], None
    ):
        name = edge["name"]
        if name in config.edge_entries_dict:
            config.edge_entries_dict[name].source_edge_data = edge

    for edge in config.edge_entries_dict.values():
        if edge.source_edge_data is None:
            logging.error(f"Edge [ {edge.name} ] not found in VCO")
            return

    for edge in config.edge_entries_dict.values():
        config_stack = await get_edge_configuration_stack(
            data, edge.source_edge_data["id"]
        )
        edge.source_edge_config = ConfigProfile(config_stack[0])
        edge.profile_config = ConfigProfile(config_stack[1])

        await fix_profile(data, edge)

        target_edge_id = await create_target_edge(data, edge)

        await update_target_config(data, edge, target_edge_id)


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logging.info("Starting config migration")

    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(main_wrapper())
