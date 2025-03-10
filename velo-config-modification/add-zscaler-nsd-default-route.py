import json
import asyncio
import aiohttp

from veloapi.api import (
    decode_enterprise_key,
    get_enterprise_services,
    update_enterprise_service,
)
from veloapi.models import CommonData


# INPUTS
vco_fqdn = "vco.velocloud.net"
vco_api_token = ""
enterprise_id = 123
nsd_name = "ZS-NSD-Name"

async def get_datacenters(c: CommonData) -> list[dict]:
    return await get_enterprise_services(c, "dataCenter")


async def main(session: aiohttp.ClientSession):
    c = CommonData(vco_fqdn, vco_api_token, enterprise_id, session)

    dc_services = await get_datacenters(c)
    zs_dc = next(iter([d for d in dc_services if d["name"] == nsd_name]))

    dc_id: int = zs_dc["id"]
    dc_name: str = zs_dc["name"]
    dc_type: str = zs_dc["type"]
    dc_data: dict = zs_dc["data"]

    # custom site subnet to send default route on ZScaler template
    dc_data["subnets"] = [
        {
            "name": "",
            "cidrIp": "0.0.0.0",
            "cidrPrefix": 0,
            "netMask": "0.0.0.0",
            "cidrIpStart": "0.0.0.0",
            "cidrIpEnd": "0.0.0.0",
            "nextHop": [],
        }
    ]

    # insert correct PSKs back in
    for gw in dc_data["vpnGateways"]:
        encrypted_key = gw["IKESA"]["sharedKey"]
        key = await decode_enterprise_key(c, encrypted_key)
        gw["IKESA"]["sharedKey"] = key

        if (
            (r := gw.get("redundant", None))
            and (ikesa := r.get("IKESA", None))
            and (encrypted_key := ikesa.get("sharedKey", None))
        ):
            key = await decode_enterprise_key(c, encrypted_key)
            ikesa["sharedKey"] = key

    resp = await update_enterprise_service(
        c,
        dc_id,
        {
            "name": dc_name,
            "type": dc_type,
            "data": dc_data,
        },
    )

    # should indicate that 1 row was updated
    print(json.dumps(resp, indent=2))


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    asyncio.run(main_wrapper())
