import asyncio
import aiohttp
import dotenv
import jsonpatch
import uuid

from models import BranchData, CommonData, CustomCommonData, WanData
from util import calculate_lat_lon, ipv4_address, ipv4_network

from veloapi.api import (
    edge_provision,
    get_edge_configuration_stack,
    update_configuration_module,
)
from veloapi.models import ConfigProfile, EdgeProvisionParams
from veloapi.util import read_env


def generate_wan_overlay(wan_data: tuple[WanData, WanData]):
    val = {
        "links": [
            {
                "MTU": 1500,
                "addressingVersion": "IPv4",
                "backupOnly": wan.standby,
                "bwMeasurement": "USER_DEFINED",
                "classesOfService": {"classId": None, "classesOfService": []},
                "classesOfServiceEnabled": False,
                "customVlanId": False,
                "description": "",
                "discovery": "USER_DEFINED",
                "downstreamMbps": str(wan.mpbs_downstream),
                "dscpTag": "",
                "dynamicBwAdjustmentEnabled": False,
                "enable8021P": False,
                "encryptOverlay": True,
                "hotStandby": False,
                "internalId": str(uuid.uuid4()),
                "logicalId": str(uuid.uuid4()),
                "isp": "",
                "lastActive": "",
                "minActiveLinks": 1,
                "mode": "PUBLIC",
                "name": wan.name,
                "nextHopIpAddress": "",
                "overheadBytes": 0,
                "pmtudDisabled": False,
                "priority8021P": 0,
                "privateNetwork": None,
                "publicIpAddress": "",
                "sourceIpAddress": "",
                "staticSLA": {"jitterMs": "0", "latencyMs": "0", "lossPct": "0"},
                "staticSlaEnabled": False,
                "strictIpPrecedence": False,
                "type": "WIRED",
                "udpHolePunching": False,
                "upstreamMbps": str(wan.mpbs_upstream),
                "virtualIpAddress": "",
                "vlanId": 2,
            }
            for wan in wan_data
        ]
    }
    val["links"][0]["interfaces"] = ["GE3"]
    val["links"][1]["interfaces"] = ["GE4"]
    return val


def build_static_routes_patch(branch: BranchData) -> list[dict]:
    return [
        {
            "op": "add",
            "path": "/segments/0/routes/static/-",
            "value": {
                "advertise": True,
                "cidrPrefix": str(n.prefixlen),
                "cost": 0,
                "description": "",
                "destination": str(n.network_address),
                "gateway": str(branch.transit_net[2]),
                "icmpProbeLogicalId": None,
                "netmask": str(n.netmask),
                "preferred": True,
                "sourceIp": None,
                "subinterfaceId": -1,
                "vlanId": None,
                "wanInterface": "GE2",
            },
        }
        for n in branch.corporate_nets
    ]


def build_vlan_999_patch() -> list[dict]:
    return [
        {
            "op": "add",
            "path": "/lan/networks/0/cidrIp",
            "value": "169.254.255.255",
        },
        {
            "op": "add",
            "path": "/lan/networks/0/netmask",
            "value": "255.255.255.255",
        },
        {
            "op": "add",
            "path": "/lan/networks/0/cidrPrefix",
            "value": "32",
        },
    ]


def build_wan_patch(wan: WanData, interface_name: str, current_ds: dict) -> list[dict]:
    interface_index = next(
        (
            i
            for i, e in enumerate(current_ds["routedInterfaces"])
            if e["name"] == interface_name
        ),
        None,
    )

    if interface_index is None:
        raise ValueError(f"{interface_name} was not found in routedInterfaces")

    return [
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/cidrIp",
            "value": str(wan.local),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/cidrPrefix",
            "value": wan.network.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/netmask",
            "value": str(wan.network.netmask),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/addressing/gateway",
            "value": str(wan.gateway),
        },
        {
            "op": "replace",
            "path": f"/routedInterfaces/{interface_index}/l2/probeInterval",
            "value": "5",
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/l2/losDetection",
            "value": False,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{interface_index}/override",
            "value": True,
        },
    ]


def build_ge2_patch(branch: BranchData, current_ds: dict) -> list[dict]:
    ge2_index = next(
        (i for i, e in enumerate(current_ds["routedInterfaces"]) if e["name"] == "GE2"),
        None,
    )
    ge2_11_index = 0
    ge2_12_index = 1

    if ge2_index is None:
        raise ValueError("GE2 was not found in routedInterfaces")

    return [
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/addressing/cidrIp",
            "value": str(branch.transit_net[1]),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/addressing/cidrPrefix",
            "value": branch.transit_net.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/addressing/netmask",
            "value": str(branch.transit_net.netmask),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_11_index}/addressing/cidrIp",
            "value": str(branch.byod_net[1]),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_11_index}/addressing/cidrPrefix",
            "value": branch.byod_net.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_11_index}/addressing/netmask",
            "value": str(branch.byod_net.netmask),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_12_index}/addressing/cidrIp",
            "value": str(branch.guest_net[1]),
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_12_index}/addressing/cidrPrefix",
            "value": branch.guest_net.prefixlen,
        },
        {
            "op": "add",
            "path": f"/routedInterfaces/{ge2_index}/subinterfaces/{ge2_12_index}/addressing/netmask",
            "value": str(branch.guest_net.netmask),
        },
        {
            "op": "replace",
            "path": f"/routedInterfaces/{ge2_index}/l2/probeInterval",
            "value": "3",
        },
        {
            "op": "move",
            "from": f"/routedInterfaces/{ge2_index}",
            "path": "/routedInterfaces/0",
        },
        {
            "op": "remove",
            "path": "/routedInterfaces/0/cellular",
        },
    ]


# pre-provisioning of ZS is limited
# VCO will auto-populate some fields once the edge activates
# - refs/deviceSettings:css:site, refs/deviceSettings:zscaler:location
# - data/segments/0/css/sites (1 created per WAN), data/zscaler/deployment/location (only 1 created)
# - notably, data/zscaler/config is a bare template
# Once these configurations are populated, it will take the VCE 10-30 minutes for tunnels to establish
# - This is because ZScaler takes a long time to provision the VPN. You can see in the logs that IKE is failing.
# sub-locations may be added after activation is complete
# - ideally after the tunnels are up
# this is done using a single deviceSettings update
# - in data, /zscaler/deployment is un-touched
# - in data, /zscaler/config is modified to include
# - remove old css:site & zscaler:location refs, they must be re-created. VCO will do this.


def build_zscaler_data_patch(
    branch_data: BranchData, shared: CommonData, current_data: dict
) -> list[dict]:
    # TODO: pull sublocations from branch_data
    sublocations = [
        {
            "gwProperties": {
                "aupEnabled": False,
                "authRequired": True,
                "cautionEnabled": False,
                "dnBandwidth": 5000,
                "ipsControl": True,
                "ofwEnabled": True,
                "surrogateIP": False,
                "surrogateIPEnforcedForKnownBrowsers": False,
                "upBandwidth": 5000,
            },
            "includeAllLanInterfaces": True,
            "includeAllVlans": True,
            "internalId": "",
            "ipAddresses": ["10.0.0.0/30"],
            "ipAddressSelectionManual": True,
            "lanRoutedInterfaces": ["GE2"],
            "name": "CorpNets",
            "ruleId": "",
            "vlans": [],
        },
    ]
    return [
        {
            "op": "replace",
            "path": "/zscaler/config/cloud",
            "value": "zscalerthree.net",  # TODO: parameterize
        },
        {
            "op": "replace",
            "path": "/zscaler/config/enabled",
            "value": True,
        },
        {
            "op": "replace",
            "path": "/zscaler/config/provider",
            "value": {
                "logicalId": shared.zscaler_cloud_subscription_logical_id,
                "ref": "deviceSettings:zscaler:iaasSubscription",
            },
        },
        {
            "op": "replace",
            "path": "/zscaler/config/sublocations",
            "value": sublocations,
        },
    ]


def build_zscaler_refs_patch(branch_data: BranchData) -> list[dict]:
    return [
        {
            "op": "remove",
            "path": "/deviceSettings:css:site",
        },
        {
            "op": "remove",
            "path": "/deviceSettings:zscaler:location",
        },
    ]


async def provision_branch(common: CustomCommonData, branch: BranchData):
    lat_lon = calculate_lat_lon(
        common.google_maps_api_key, branch.postal_code, branch.country
    )
    if lat_lon is None:
        raise LookupError("failed to retrieve lat/lon")

    edge_prov_params = EdgeProvisionParams(
        branch.name,
        "edge6X0",
        common.branch_profile_id,
        common.branch_license_id,
        branch.contact_email,
        branch.contact_name,
        True,
    )

    rv = await edge_provision(common, edge_prov_params)

    edge_id = rv["id"]

    try:
        edge_config_stack = await get_edge_configuration_stack(common, edge_id)
        cfg_profile = ConfigProfile(edge_config_stack[0])

        static_routes_patch = build_static_routes_patch(branch)
        vlan_999_patch = build_vlan_999_patch()
        ge3_patch = build_wan_patch(
            branch.wans[0], "GE3", cfg_profile.device_settings.data
        )
        ge4_patch = build_wan_patch(
            branch.wans[1], "GE4", cfg_profile.device_settings.data
        )
        ge2_patch = build_ge2_patch(branch, cfg_profile.device_settings.data)

        # zscaler cannot be done until edge is activated
        patch_set = jsonpatch.JsonPatch(
            [
                *static_routes_patch,
                *vlan_999_patch,
                *ge3_patch,
                *ge4_patch,
                *ge2_patch,
            ]
        )
        patch_set.apply(cfg_profile.device_settings.data, in_place=True)

        await update_configuration_module(
            common, cfg_profile.device_settings.id, cfg_profile.device_settings.data
        )

        new_edge_wan_data = generate_wan_overlay(branch.wans)
        await update_configuration_module(common, cfg_profile.wan.id, new_edge_wan_data)

        quit_key = input(
            "pre-provisioning complete. press enter to exit, any other key to continue to ZScaler provisioning"
        )
        if quit_key == "":
            print("Exiting")
            return

        print("ZScaler not implemented yet")
        # return

        print("proceeding with ZScaler configuration...")

        # TODO: poll configuration stack repeatedly
        # wait for edge/modules/deviceSettings/data/segments/0/css to appear
        # this indicates that the VCO finished backend API to ZScaler
        # for now, just don't press enter unless the edge is activated and has the CSS provisioned

        edge_config_stack = await get_edge_configuration_stack(common, edge_id)
        cfg_profile = ConfigProfile(edge_config_stack[0])

        data_patch_set = jsonpatch.JsonPatch(
            build_zscaler_data_patch(branch, common, cfg_profile.device_settings.data)
        )
        refs_patch_set = jsonpatch.JsonPatch(build_zscaler_refs_patch(branch))
        data_patch_set.apply(cfg_profile.device_settings.data, in_place=True)
        refs_patch_set.apply(cfg_profile.device_settings.refs, in_place=True)

        await update_configuration_module(
            common,
            cfg_profile.device_settings.id,
            cfg_profile.device_settings.data,
            cfg_profile.device_settings.refs,
        )

    finally:
        return


branch_data = BranchData(
    "test edge 777",
    "US",
    "62269",
    "Nick Barrett",
    "nick.barrett@broadcom.com",
    ipv4_network("10.0.0.4/30"),
    [ipv4_network("172.16.11.0/24")],
    ipv4_network("192.168.202.0/24"),
    ipv4_network("192.168.203.0/24"),
    (
        WanData(
            "ISP-A",
            ipv4_network("172.16.0.0/30"),
            ipv4_address("172.16.0.2"),
            ipv4_address("172.16.0.1"),
            50,
            50,
        ),
        WanData(
            "ISP-B",
            ipv4_network("192.168.12.0/24"),
            ipv4_address("192.168.12.240"),
            ipv4_address("192.168.12.1"),
            50,
            50,
        ),
    ),
)


async def main(session: aiohttp.ClientSession):
    data = CustomCommonData(
        read_env("VCO"),
        read_env("VCO_TOKEN"),
        read_env("ENT_ID"),
        "",  # read_env("ZS_CLOUD_SUB_LOG_ID")
        read_env("BRANCH_PROF_ID"),
        read_env("BRANCH_LIC_ID"),
        read_env("GOOGLE_MAPS_API_KEY"),
    )

    await provision_branch(data, branch_data)


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(main_wrapper())
