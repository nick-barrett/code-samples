import asyncio
from io import TextIOWrapper
from typing import Optional
from dataclasses import dataclass, field
import copy
from aiohttp import ClientSession
import json

import dotenv

from veloapi.models import CommonData
from veloapi.util import read_env, extract_module
from veloapi.api import (
    get_enterprise_configuration_profile,
    get_enterprise_services,
    get_object_groups,
    update_configuration_module,
    enable_edge_for_edge_hub,
    disable_edge_for_edge_hub,
    enable_edge_for_backhaul,
    enable_cluster_for_edge_hub,
    disable_cluster_for_edge_hub,
    enable_cluster_for_backhaul,
    enable_cluster_for_edge_to_edge_bridge,
    enable_edge_for_edge_to_edge_bridge,
    get_edge_hubs,
)

"""

Input:
- Source VCO FQDN
- Source VCO Token
- Source Enterprise ID
- Destination VCO FQDN
- Destination VCO Token
- Destination VCO Enterprise ID

Read all configurations from source VCO
Generate directed acyclic graph of all objects
Traverse using topo sort on DAG
Replicate each object into destination VCO

Maintain mapping of objects between source and dest VCO.

"""


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
        self.refs = self.raw["refs"]


@dataclass
class ProfileConfig:
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


async def get_profile_config(shared: CommonData, profile_id: int) -> ProfileConfig:
    return ProfileConfig(await get_enterprise_configuration_profile(shared, profile_id))


def remove_rule_logical_ids(data: dict):
    if isinstance(data, dict):
        for key in list(data.keys()):
            if key == "ruleLogicalId":
                del data[key]
            else:
                remove_rule_logical_ids(data[key])
    elif isinstance(data, list):
        for i in reversed(range(len(data))):
            remove_rule_logical_ids(data[i])
    else:
        pass


def get_segment_by_segment_id(
    cfg: ProfileConfig, segment_id: int
) -> Optional[dict[str, list | dict]]:
    return next(
        iter(
            [
                s
                for s in cfg.device_settings.data["segments"]
                if s["segment"]["segmentId"] == segment_id
            ]
        ),
        None,
    )


def get_matching_refs(
    refs: list[dict], logical_id: str, segment_object_id: int
) -> list[dict]:
    return [
        r
        for r in refs
        if r["logicalId"] == logical_id and r["segmentObjectId"] == segment_object_id
    ]


def clone_generic_ref(dst_cfg: ProfileConfig, src_ref: dict) -> dict:
    ref_cloned_keys = [
        "enterpriseObjectId",
        "segmentObjectId",
        "segmentLogicalId",
        "ref",
        "logicalId",
    ]
    new_ref = {k: src_ref[k] for k in ref_cloned_keys if k in src_ref}
    new_ref["configurationId"] = dst_cfg.id
    new_ref["moduleId"] = dst_cfg.device_settings.id
    return new_ref


async def clone_edge_hub_cluster_ref(
    shared: CommonData,
    dst_cfg: ProfileConfig,
    src_ref: dict,
) -> dict:
    src_configuration_id = src_ref["configurationId"]
    src_ref_roles = src_ref["data"][str(src_configuration_id)]["0"]["roles"]
    edge_hub_cluster_object_id = src_ref["enterpriseObjectId"]

    await enable_cluster_for_edge_hub(
        shared,
        dst_cfg.id,
        edge_hub_cluster_object_id,
        dst_cfg.device_settings.id,
        src_ref["segmentObjectId"],
    )
    if src_ref_roles["backHaulEdge"] == True:
        await enable_cluster_for_backhaul(
            shared,
            dst_cfg.id,
            edge_hub_cluster_object_id,
            dst_cfg.device_settings.id,
            src_ref["segmentObjectId"],
        )
    if src_ref_roles["edgeToEdgeBridge"] == True:
        await enable_cluster_for_edge_to_edge_bridge(
            shared,
            dst_cfg.id,
            edge_hub_cluster_object_id,
            dst_cfg.device_settings.id,
            src_ref["segmentObjectId"],
        )

    ref_cloned_keys = [
        "enterpriseObjectId",
        "segmentObjectId",
        "segmentLogicalId",
        "ref",
        "logicalId",
    ]
    new_ref = {k: src_ref[k] for k in ref_cloned_keys}
    new_ref["configurationId"] = dst_cfg.id
    new_ref["moduleId"] = dst_cfg.device_settings.id
    new_ref["data"] = {}
    return new_ref


async def clone_edge_hub_edge_ref(
    shared: CommonData,
    edge_hub_services: list[dict],
    dst_cfg: ProfileConfig,
    src_ref: dict,
) -> dict:
    src_ref_roles = src_ref["data"]["roles"]
    edge_hub_object_id = src_ref["enterpriseObjectId"]
    hub_edge_id = list(
        [o["edgeId"] for o in edge_hub_services if o["id"] == edge_hub_object_id]
    )[0]
    await enable_edge_for_edge_hub(
        shared,
        dst_cfg.id,
        hub_edge_id,
        dst_cfg.device_settings.id,
        src_ref["segmentObjectId"],
    )
    if src_ref_roles["backHaulEdge"] == True:
        await enable_edge_for_backhaul(
            shared,
            dst_cfg.id,
            hub_edge_id,
            dst_cfg.device_settings.id,
            src_ref["segmentObjectId"],
        )
    if src_ref_roles["edgeToEdgeBridge"] == True:
        await enable_edge_for_edge_to_edge_bridge(
            shared,
            dst_cfg.id,
            hub_edge_id,
            dst_cfg.device_settings.id,
            src_ref["segmentObjectId"],
        )
    ref_cloned_keys = [
        "data",
        "enterpriseObjectId",
        "segmentObjectId",
        "segmentLogicalId",
        "ref",
        "logicalId",
    ]
    new_ref = {k: src_ref[k] for k in ref_cloned_keys}
    new_ref["configurationId"] = dst_cfg.id
    new_ref["moduleId"] = dst_cfg.device_settings.id
    return new_ref


async def handle_vpn_edge_hub_refs(
    shared: CommonData,
    edge_hub_services: list[dict],
    src_cfg: ProfileConfig,
    dst_cfg: ProfileConfig,
):
    src_refs: dict = src_cfg.device_settings.refs
    dst_refs: dict = dst_cfg.device_settings.refs

    ref_name = "deviceSettings:vpn:edgeHub"
    if ref_name in src_refs:
        src_vpn_ref = src_refs[ref_name]
        src_vpn_refs = src_vpn_ref if isinstance(src_vpn_ref, list) else [src_vpn_ref]

        if ref_name in dst_refs:
            dst_vpn_ref = dst_refs[ref_name]
            dst_vpn_refs = (
                dst_vpn_ref if isinstance(dst_vpn_ref, list) else [dst_vpn_ref]
            )

            # call API to remove each edgehub
            for removed in [
                r
                for r in dst_vpn_refs
                if not get_matching_refs(
                    src_vpn_refs, r["logicalId"], r["segmentObjectId"]
                )
            ]:
                edge_hub_object_id = removed["enterpriseObjectId"]
                hub_edge_id = list(
                    [
                        o["edgeId"]
                        for o in edge_hub_services
                        if o["id"] == edge_hub_object_id
                    ]
                )[0]
                await disable_edge_for_edge_hub(
                    shared,
                    dst_cfg.id,
                    hub_edge_id,
                    removed["moduleId"],
                    removed["segmentObjectId"],
                )

            # remove vpn ref from dst if no corresponding vpn ref is in src
            dst_vpn_refs = [
                r
                for r in dst_vpn_refs
                if get_matching_refs(src_vpn_refs, r["logicalId"], r["segmentObjectId"])
            ]
            # add any new necessary refs
            for src_ref in src_vpn_refs:
                # if (logicalId,segmentObjectId) not found in dst vpn refs....
                if not get_matching_refs(
                    dst_vpn_refs, src_ref["logicalId"], src_ref["segmentObjectId"]
                ):
                    # clone one and add it to dst refs
                    dst_vpn_refs.append(
                        clone_edge_hub_edge_ref(
                            shared, edge_hub_services, dst_cfg, src_ref
                        )
                    )

            # write back to the original dst refs object
            dst_refs[ref_name] = dst_vpn_refs

        else:
            # clone all src refs it there is none in dst
            dst_refs[ref_name] = list(
                [
                    clone_edge_hub_edge_ref(shared, edge_hub_services, dst_cfg, src_ref)
                    for src_ref in src_vpn_refs
                ]
            )
    elif ref_name in dst_refs:
        # remove refs from dst if none in src
        old_refs = dst_refs[ref_name]
        del dst_refs[ref_name]

        for removed in old_refs:
            edge_hub_object_id = removed["enterpriseObjectId"]
            hub_edge_id = list(
                [
                    o["edgeId"]
                    for o in edge_hub_services
                    if o["id"] == edge_hub_object_id
                ]
            )[0]
            await disable_edge_for_edge_hub(
                shared,
                dst_cfg.id,
                hub_edge_id,
                removed["moduleId"],
                removed["segmentObjectId"],
            )


async def handle_vpn_edge_hub_cluster_refs(
    shared: CommonData,
    src_cfg: ProfileConfig,
    dst_cfg: ProfileConfig,
):
    src_refs: dict = src_cfg.device_settings.refs
    dst_refs: dict = dst_cfg.device_settings.refs

    ref_name = "deviceSettings:vpn:edgeHubCluster"
    if ref_name in src_refs:
        src_vpn_ref = src_refs[ref_name]
        src_vpn_refs = src_vpn_ref if isinstance(src_vpn_ref, list) else [src_vpn_ref]

        if ref_name in dst_refs:
            dst_vpn_ref = dst_refs[ref_name]
            dst_vpn_refs = (
                dst_vpn_ref if isinstance(dst_vpn_ref, list) else [dst_vpn_ref]
            )
            # remove vpn ref from dst if no corresponding vpn ref is in src
            for removed in [
                r
                for r in dst_vpn_refs
                if not get_matching_refs(
                    src_vpn_refs, r["logicalId"], r["segmentObjectId"]
                )
            ]:
                edge_hub_object_id = removed["enterpriseObjectId"]
                await disable_cluster_for_edge_hub(
                    shared,
                    dst_cfg.id,
                    edge_hub_object_id,
                    removed["moduleId"],
                    removed["segmentObjectId"],
                )

            dst_vpn_refs = [
                r
                for r in dst_vpn_refs
                if get_matching_refs(src_vpn_refs, r["logicalId"], r["segmentObjectId"])
            ]
            # add any missing refs
            for src_ref in src_vpn_refs:
                if not get_matching_refs(
                    dst_vpn_refs, src_ref["logicalId"], src_ref["segmentObjectId"]
                ):
                    # clone one and add it to dst refs
                    dst_vpn_refs.append(
                        clone_edge_hub_cluster_ref(shared, dst_cfg, src_ref)
                    )

            # write back to the original dst refs object
            dst_refs[ref_name] = dst_vpn_refs

        else:
            # clone all src refs it there is none in dst
            dst_refs[ref_name] = list(
                [
                    clone_edge_hub_cluster_ref(shared, dst_cfg, css_ref)
                    for css_ref in src_vpn_refs
                ]
            )
    elif ref_name in dst_refs:
        # remove refs from dst if none in src
        old_refs = dst_refs[ref_name]
        del dst_refs[ref_name]

        for removed in old_refs:
            await disable_cluster_for_edge_hub(
                shared,
                dst_cfg.id,
                removed["enterpriseObjectId"],
                removed["moduleId"],
                removed["segmentObjectId"],
            )


async def handle_vpn_hub_refs(
    shared: CommonData, src_cfg: ProfileConfig, dst_cfg: ProfileConfig
):
    edge_hub_services = await get_edge_hubs(shared)

    await handle_vpn_edge_hub_refs(shared, edge_hub_services, src_cfg, dst_cfg)
    await handle_vpn_edge_hub_cluster_refs(shared, src_cfg, dst_cfg)


def handle_generic_refs(src_cfg: ProfileConfig, dst_cfg: ProfileConfig, ref_name: str):
    src_refs_full: dict = src_cfg.device_settings.refs
    dst_refs_full: dict = dst_cfg.device_settings.refs

    if ref_name in src_refs_full:
        src_ref = src_refs_full[ref_name]
        src_refs = src_ref if isinstance(src_ref, list) else [src_ref]

        if ref_name in dst_refs_full:
            dst_ref = dst_refs_full[ref_name]
            dst_refs = dst_ref if isinstance(dst_ref, list) else [dst_ref]
            # remove ref from dst if no corresponding ref is in src
            dst_refs = [
                r
                for r in dst_refs
                if get_matching_refs(src_refs, r["logicalId"], r["segmentObjectId"])
            ]
            # add any new necessary refs
            for src_ref in src_refs:
                if not get_matching_refs(
                    dst_refs, src_ref["logicalId"], src_ref["segmentObjectId"]
                ):
                    # clone one and add it to dst refs
                    dst_refs.append(clone_generic_ref(dst_cfg, src_ref))

            # write back to the original dst refs object
            dst_refs_full[ref_name] = dst_refs

        else:
            # clone all src refs it there is none in dst
            dst_refs_full[ref_name] = list(
                [clone_generic_ref(dst_cfg, src_ref) for src_ref in src_refs]
            )
    else:
        # remove refs from dst if none in src
        dst_refs_full.pop(ref_name, None)


def generate_device_settings_data(
    src_cfg: ProfileConfig, dst_cfg: ProfileConfig
) -> dict:
    # deep copy to preserve source objects in case they're used elsewhere
    result = copy.deepcopy(src_cfg.device_settings.data)

    for seg in result["segments"]:
        segment_id = seg["segment"]["segmentId"]
        dst_seg = get_segment_by_segment_id(dst_cfg, segment_id)
        assert dst_seg is not None

        # maintain handOffGateways from destination profile
        if "handOffGateways" in dst_seg:
            seg["handOffGateways"] = dst_seg["handOffGateways"]

    return result


async def sync_profile(shared: CommonData, source_id: int, dest_id: int):
    src_cfg = await get_profile_config(shared, source_id)
    dst_cfg = await get_profile_config(shared, dest_id)

    # hub vpn is special..
    await handle_vpn_hub_refs(shared, src_cfg, dst_cfg)

    # any others ?
    generic_ref_names = [
        "deviceSettings:dns:privateProviders",
        "deviceSettings:dns:primaryProvider",
        "deviceSettings:segment:netflowFilters",
        "deviceSettings:segment:netflowCollectors",
        "deviceSettings:authentication",
        "deviceSettings:vpn:dataCenter",
        "deviceSettings:edgeDirectNvs:provider",
        "deviceSettings:css:provider",
    ]
    for ref_name in generic_ref_names:
        handle_generic_refs(src_cfg, dst_cfg, ref_name)

    # TODO: WLAN PSK handling ?
    device_settings_data = generate_device_settings_data(src_cfg, dst_cfg)

    qos_data = copy.deepcopy(src_cfg.qos.data)
    remove_rule_logical_ids(qos_data)

    firewall_data = copy.deepcopy(src_cfg.firewall.data)
    remove_rule_logical_ids(firewall_data)

    try:
        await update_configuration_module(
            shared,
            dst_cfg.device_settings.id,
            device_settings_data,
            dst_cfg.device_settings.refs,
        )
        print("deviceSettings done")
    except ValueError as e:
        print("deviceSettings failed")
        print(e)

    try:
        await update_configuration_module(
            shared, dst_cfg.qos.id, src_cfg.qos.data, None
        )
        print("QOS done")
    except ValueError as e:
        print("QOS failed")
        print(e)

    try:
        await update_configuration_module(
            shared, dst_cfg.firewall.id, src_cfg.firewall.data, None
        )
        print("firewall done")
    except ValueError as e:
        print("firewall failed")
        print(e)


async def clone_enterprise(shared_src: CommonData, shared_dst: CommonData):
    # create object groups
    # create dummy profile
    # provision all edges w/ dummy profile
    # create network services
    # create profiles
    # assign profiles to edges
    # update edge configuration modules

    pass


async def read_enterprise_to_file(src: CommonData, f: TextIOWrapper):
    object_groups = await get_object_groups(src)
    network_services = await get_enterprise_services(src)
    # profiles
    # edges

    json.dump(
        {
            "object_groups": object_groups,
            "network_services": network_services,
        },
        f,
    )


async def main(src_session: ClientSession, dst_session: ClientSession):
    with open("enterprise-data.json", "w") as f:
        await read_enterprise_to_file(
            CommonData(
                read_env("VCO"),
                read_env("VCO_TOKEN"),
                int(read_env("ENT_ID")),
                src_session,
            ),
            f,
        )


async def async_main():
    async with ClientSession() as src_session:
        async with ClientSession() as dst_session:
            await main(src_session, dst_session)


if __name__ == "__main__":
    dotenv.load_dotenv("env/.env", override=True)

    asyncio.run(async_main())
