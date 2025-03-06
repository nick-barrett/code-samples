import asyncio
import os
from typing import Optional

import aiohttp
import dotenv
import jsonpatch

from veloapi.api import get_edge_configuration_stack, update_configuration_module
from veloapi.models import CommonData, ConfigProfile
from veloapi.util import read_env


def get_netmask(pfx_len: int) -> str:
    return ".".join(
        [str((0xFFFFFFFF << (32 - pfx_len) >> i) & 0xFF) for i in [24, 16, 8, 0]]
    )


def build_vlan_prefix_patch(edge_ds_data: dict, vlan_id: int, new_prefix_length: int):
    networks = edge_ds_data["lan"]["networks"]

    vlan_index = [
        index
        for index, vlan_data in enumerate(networks)
        if int(vlan_data["vlanId"]) == vlan_id
    ][0]

    return [
        {
            "op": "replace",
            "path": f"/lan/networks/{vlan_index}/numDhcpAddr",
            "value": 3,
        },
        {
            "op": "replace",
            "path": f"/lan/networks/{vlan_index}/cidrPrefix",
            "value": new_prefix_length,
        },
        {
            "op": "replace",
            "path": f"/lan/networks/{vlan_index}/netmask",
            "value": get_netmask(new_prefix_length),
        },
    ]


def vlan_prefix_edit(
    common: CommonData, edge_id: int, vlan_id: int, new_prefix_len: int
):
    edge_config_stack = get_edge_configuration_stack(common, edge_id)
    config_profile = ConfigProfile(edge_config_stack[0])

    vlan_patch = build_vlan_prefix_patch(config_profile.device_settings.data, vlan_id, new_prefix_len)

    patch_set = jsonpatch.JsonPatch(vlan_patch)
    patch_set.apply(config_profile.device_settings.data, in_place=True)

    update_configuration_module(common, config_profile.device_settings.id, config_profile.device_settings.data)


async def main(common: CommonData):
    edge_id = 34233
    vlan_id = 12
    new_vlan_prefix_length = 26

    vlan_prefix_edit(common, edge_id, vlan_id, new_vlan_prefix_length)

async def async_main():
    async with aiohttp.ClientSession() as session:
        await main(
            CommonData(
                read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
            )
        )


if __name__ == "__main__":
    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(async_main())
