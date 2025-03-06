import asyncio
import aiohttp
import dotenv

from veloapi.api import get_edge_configuration_stack, update_configuration_module
from veloapi.models import CommonData, ConfigProfile
from veloapi.util import read_env


async def main(cfg: CommonData):
    edge_id = 123

    # read existing config
    edge_config_stack = get_edge_configuration_stack(cfg, edge_id)
    config_profile = ConfigProfile(edge_config_stack[0])

    # modify module_data here - e.g. set GE2 to disabled
    ge2 = [intf for intf in config_profile.device_settings.data["routedInterfaces"] if intf["name"] == "GE2"][0]
    ge2["disabled"] = True

    # write back the modified config
    update_configuration_module(cfg, config_profile.device_settings.id, config_profile.device_settings.data)


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
