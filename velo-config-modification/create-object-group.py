import aiohttp
import asyncio
import dotenv
import json

from veloapi.api import get_address_groups, get_port_groups, insert_address_group, insert_port_group
from veloapi.models import CommonData
from veloapi.util import read_env


async def get_groups(common: CommonData):
    addr_grps = get_address_groups(common)
    port_grps = get_port_groups(common)

    with open("addr-groups.json", "w") as f:
        json.dump(await addr_grps, f)
    with open("port-groups.json", "w") as f:
        json.dump(await port_grps, f)


async def create_groups(common: CommonData):
    addr_groups = None
    port_groups = None

    with open("addr-groups.json", "r") as f:
        addr_groups = json.load(f)

    with open("port-groups.json", "r") as f:
        port_groups = json.load(f)

    for ag in addr_groups:
        name = ag["name"]
        descr = ag["description"]
        data = ag["data"]

        await insert_address_group(common, name, descr, data)

    for pg in port_groups:
        name = pg["name"]
        descr = pg["description"]
        data = pg["data"]

        await insert_port_group(common, name, descr, data)


async def main(
    env_file: str | None,
    session: aiohttp.ClientSession,
):
    if env_file:
        dotenv.load_dotenv(env_file, verbose=True, override=True)

    common = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    await create_groups(common)


async def async_main(env_file: str | None):
    async with aiohttp.ClientSession() as session:
        await main(env_file, session)


if __name__ == "__main__":
    asyncio.run(async_main("env/.env"))