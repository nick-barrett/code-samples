import asyncio
import aiohttp
import json
import dotenv

from veloapi.api import get_enterprise_edge_list_full
from veloapi.models import CommonData
from veloapi.util import read_env


async def main(common: CommonData):
    css_locations: dict[str, set[str]] = dict()
    async for edge in get_enterprise_edge_list_full(common, ["cloudServices"], None):
        for css in edge.cloud_services:
            data_centers = css.site.data.data_centers
            dc_meta = [
                data_centers.primary_meta,
                data_centers.secondary_meta,
                #data_centers.tertiary_meta,
            ]

            for meta in dc_meta:
                if edge.name is None:
                    continue

                if meta.city in css_locations:
                    css_locations[meta.city].add(edge.name)
                else:
                    css_locations[meta.city] = set([edge.name])


    with open("outputs/zs-locations.json", "w") as f:
        json.dump({k: list(v) for k, v in css_locations.items()}, f, indent=2)  # type: ignore


async def async_main(env_file: str | None):
    if env_file:
        dotenv.load_dotenv(env_file, verbose=True, override=True)

    async with aiohttp.ClientSession() as session:
        await main(
            CommonData(
                read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
            )
        )


if __name__ == "__main__":
    asyncio.run(async_main("env/.env"))
