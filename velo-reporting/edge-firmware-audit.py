import logging
import json
import asyncio
from typing import Any

import dotenv
import aiohttp

from veloapi.api import get_enterprise_edge_list_full_dict
from veloapi.models import CommonData
from veloapi.util import read_env


async def main(session: aiohttp.ClientSession):
    data = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    edges: list[dict[str, Any]] = []

    keys = [
        "id",
        "name",
        "modelNumber",
        "serialNumber",
        "softwareVersion",
        "buildNumber",
        "platformFirmwareVersion",
        "platformBuildNumber",
        "factorySoftwareVersion",
        "factoryBuildNumber",
    ]

    async for edge in get_enterprise_edge_list_full_dict(data, None, None):
        edges.append({key: edge.get(key, "") for key in keys})
        if len(edges) % 100 == 0:
            logging.info(f"Processed {len(edges)} edges so far...")

    platform_builds = list(set([edge["platformBuildNumber"] for edge in edges]))
    factory_builds = list(set([edge["factoryBuildNumber"] for edge in edges]))

    edge_platforms = {
        v: [e for e in edges if e["platformBuildNumber"] == v] for v in platform_builds
    }
    edge_factories = {
        v: [e for e in edges if e["factoryBuildNumber"] == v] for v in factory_builds
    }

    with open("edge-versions.json", "w") as f:
        edge_versions = {
            "platform": edge_platforms,
            "factory": edge_factories,
        }
        json.dump(edge_versions, f, indent=2)


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        filename="version-audit.log",
        filemode="a",
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logging.info("Starting version audit...")

    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(main_wrapper())
