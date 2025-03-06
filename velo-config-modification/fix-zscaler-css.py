import asyncio
from typing import Any
import aiohttp
import dotenv

from veloapi.api import get_edge_configuration_stack, get_enterprise_segments, update_configuration_module
from veloapi.models import CommonData, ConfigurationProfile
from veloapi.util import read_env


def transform_css_provider_ref(provider_ref: dict[str, Any], provider_id: int, provider_logical_id: str) -> dict[str, Any]:
    """
    Generate a new provider ref with given provider ID & logical IDs.
    These should be inserted into an array at refs["deviceSettings:css:provider"].
    """
    return {
        "enterpriseObjectId": provider_id,
        "logicalId": provider_logical_id,
        "ref": "deviceSettings:css:provider",
        "configurationId": provider_ref["configurationId"],
        "moduleId": provider_ref["moduleId"],
        "segmentLogicalId": provider_ref["segmentLogicalId"],
        "segmentObjectId": provider_ref["segmentObjectId"]
    }


def build_segment_css_override_config(provider_logical_id: str) -> dict[str, Any]:
    """
    Insert at data.segments[].css
    """
    return {
        "enabled": True,
        "provider": {
            "logicalId": provider_logical_id,
            "ref": "deviceSettings:css:provider"
        },
        "config": {
            "authenticationAlgorithm": "SHA_1",
            "encryptionAlgorithm": "none",
            "redirect": "policy",
            "IPSECPROP": {
                "lifeTimeSeconds": 28800
            },
            "IKEPROP": {
                "DHGroup": 2,
                "PFS": 0,
                "authenticationAlgorithm": "Any",
                "authenticationMethod": "PSK",
                "encryptionAlgorithm": "Any",
                "idProtect": False,
                "lifeTimeSeconds": 86400,
                "protocolVersion": 2
            }
        },
        "sites": [],
        "override": True
    }


def build_zscaler_config(cloud_name: str, iaas_provider_logical_id: str) -> dict[str, Any]:
    """
    WIP. This would be used to modify the ZScaler sub-location configs.
    """
    return {
        "config": {
            "cloud": cloud_name,
            "enabled": True,
            "location": {
                "name": None
            },
            "override": True,
            "provider": {
                "logicalId": iaas_provider_logical_id,
                "ref": None
            },
            "subLocations": [],
            "vendor": "zscaler"
        },
        "deployment": {
            "location": {},
            "mtgreSite": {},
            "subLocations": []
        }
    }


def patch_refs(refs: dict[str, list[Any] | dict[Any, Any]], new_id: int, new_log_id: str):
    css_prov_refs: list[dict[str, Any]] = []
    if isinstance(refs["deviceSettings:css:provider"], list):
        css_prov_refs = refs["deviceSettings:css:provider"]
    elif isinstance(refs["deviceSettings:css:provider"], dict):
        css_prov_refs = [refs["deviceSettings:css:provider"]]
    else:
        raise ValueError("css refs are neither dict nor list!")

    for p in css_prov_refs:
        new_p = transform_css_provider_ref(p, new_id, new_log_id)
        p.clear()
        p.update(new_p)

    refs["deviceSettings:css:provider"] = css_prov_refs


async def enable_css_overrides(common: CommonData, segments: dict[int, Any], edge_id: int, css_id: int, css_logical_id: str):
    config_stack = await get_edge_configuration_stack(common, edge_id)
    edge_config_profile = ConfigurationProfile(config_stack[0])
    edge_ds_module = edge_config_profile.device_settings

    device_settings_data = edge_ds_module.data
    device_settings_refs = edge_ds_module.refs

    # patch CSS provider w/ the temp provider
    patch_refs(device_settings_refs, css_id, css_logical_id)

    # patch segment CSS configs to reference temp provider as override
    css_provider_refs = device_settings_refs["deviceSettings:css:provider"]
    for segment in device_settings_data["segments"]:
        # insert CSS override config in the segment if segment present in refs
        # need to check against get segments result since we don't always include segment logical ID here...
        segment_obj = segment["segment"]
        segment_small_id = segment_obj["segmentId"]

        segment_logical_id = segments[segment_small_id]["logicalId"]

        for p in css_provider_refs:
            if p["segmentLogicalId"] == segment_logical_id:
                segment["css"] = build_segment_css_override_config(css_logical_id)

    # clear data.zscaler
    #if "zscaler" in device_settings_data:
    #    del device_settings_data["zscaler"]

    await update_configuration_module(common, edge_ds_module.id, device_settings_data, device_settings_refs)


async def disable_css_overrides(common: CommonData, edge_id: int, css_id: int, css_logical_id: str):
    config_stack = await get_edge_configuration_stack(common, edge_id)
    edge_config_profile = ConfigurationProfile(config_stack[0])
    edge_ds_module = edge_config_profile.device_settings

    device_settings_data = edge_ds_module.data
    device_settings_refs = edge_ds_module.refs

    # replace real css provider ref
    patch_refs(device_settings_refs, css_id, css_logical_id)

    # patch segment CSS configs to use profile configs
    for segment in device_settings_data["segments"]:
        if "css" in segment:
            del segment["css"]

    # clear zscaler sub-location config from data
    #if "zscaler" in device_settings_data:
    #    del device_settings_data["zscaler"]

    await update_configuration_module(common, edge_ds_module.id, device_settings_data, device_settings_refs)


async def main(common: CommonData):
    edge_id = 36701

    # these could also be discovered using get_services API + some filtering
    real_css_provider_id = 88714
    real_css_provider_logical_id = "148475af-3556-4cc6-be81-d3513593a351"

    temp_css_provider_id = 93481
    temp_css_provider_logical_id = "97329d7e-7e9a-4969-8c1a-97896433c55d"

    segments = {s["data"]["segmentId"]: s for s in await get_enterprise_segments(common)}

    await enable_css_overrides(common, segments, edge_id, temp_css_provider_id, temp_css_provider_logical_id)

    # VCO needs time to delete ZS objects
    # could also poll VCO event log w/ a ZScaler API filter to see when completed
    await asyncio.sleep(60)

    await disable_css_overrides(common, edge_id, real_css_provider_id, real_css_provider_logical_id)

    # wait for edge to apply, then re-add sub-locations
    # await asyncio.sleep(60)


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
