import asyncio
from dataclasses import dataclass, field
import aiohttp

import dotenv

from veloapi.util import read_env, extract_module
from veloapi.models import CommonData, ConfigModule, ConfigProfile
from veloapi.api import (
    get_edge_configuration_stack,
    update_configuration_module,
)


async def process_bizpol(shared: CommonData, cfg: ConfigModule):
    rules = cfg.data["segments"][0]["rules"]

    # display existing rules
    for rule in rules:
        print("biz pol: [[ {} ]]".format(rule["name"]))

    new_data = cfg.data

    # construct a new rule
    # match source VLAN-10
    # set low/bulk priority
    # routing direct to internet
    new_rules = [
        {
            "name": "VLAN-10",
            "match": {
                "appid": -1,
                "classid": -1,
                "dip": "any",
                "dsm": "any",
                "proto": -1,
                "sip": "any",
                "ssm": "any",
                "os_version": -1,
                "sport_low": -1,
                "sport_high": -1,
                "dport_low": -1,
                "dport_high": -1,
                "dscp": -1,
                "svlan": 10,
                "hostname": "",
                "dvlan": -1,
                "ipVersion": "IPv4v6",
                "sipV6": "any",
                "dipV6": "any",
            },
            "action": {
                "routePolicy": "auto",
                "routeType": "edge2Any",
                "QoS": {
                    "rxScheduler": {
                        "priority": "low",
                        "bandwidthCapPct": -1,
                        "bandwidth": -1,
                        "queueLen": -1,
                        "burst": -1,
                        "latency": -1,
                    },
                    "txScheduler": {
                        "priority": "low",
                        "bandwidthCapPct": -1,
                        "bandwidth": -1,
                        "queueLen": -1,
                        "burst": -1,
                        "latency": -1,
                    },
                    "type": "bulk",
                },
                "edge2EdgeRouteAction": {
                    "interface": "auto",
                    "linkInternalLogicalId": "auto",
                    "linkPolicy": "auto",
                    "routeCfg": {},
                    "routePolicy": "gateway",
                    "serviceGroup": "ALL",
                    "vlanId": -1,
                    "wanlink": "auto",
                },
                "edge2DataCenterRouteAction": {
                    "interface": "auto",
                    "linkInternalLogicalId": "auto",
                    "linkPolicy": "auto",
                    "routeCfg": {},
                    "routePolicy": "gateway",
                    "serviceGroup": "ALL",
                    "vlanId": -1,
                    "wanlink": "auto",
                },
                "edge2CloudRouteAction": {
                    "interface": "auto",
                    "linkInternalLogicalId": "auto",
                    "linkPolicy": "auto",
                    "routeCfg": {},
                    "routePolicy": "direct",
                    "serviceGroup": "ALL",
                    "vlanId": -1,
                    "wanlink": "auto",
                },
            },
        }
    ]

    new_data["segments"][0]["rules"] = new_rules

    await update_configuration_module(shared, cfg.id, new_data)


async def process_firewall(shared: CommonData, cfg: ConfigModule):
    rules = cfg.data["segments"][0]["outbound"]

    # display existing rules
    for rule in rules:
        print("FW rule: [[ {} ]]".format(rule["name"]))

    # add a new rule
    new_data = cfg.data

    # construct a rule to deny the Box.com app
    new_rules = [
        {
            "name": "Deny Box",
            "match": {
                "appid": 767,
                "classid": -1,
                "dscp": -1,
                "sip": "any",
                "sport_high": -1,
                "sport_low": -1,
                "ssm": "any",
                "svlan": -1,
                "os_version": -1,
                "hostname": "",
                "dip": "any",
                "dport_low": -1,
                "dport_high": -1,
                "dsm": "any",
                "dvlan": -1,
                "proto": -1,
                "ipVersion": "IPv4v6",
                "sipV6": "any",
                "dipV6": "any",
            },
            "action": {"allow_or_deny": "deny"},
        }
    ]

    # apply it to the configuration data
    # this will replace existing rules
    new_data["segments"][0]["outbound"] = new_rules

    # push to API
    await update_configuration_module(shared, cfg.id, new_data)


async def main(shared: CommonData):
    edge_id = 36701

    edge_stack = await get_edge_configuration_stack(shared, edge_id)

    try:
        edge_cfg = ConfigProfile(edge_stack[0])

        bizpol_cfg = edge_cfg.qos
        if bizpol_cfg:
            await process_bizpol(shared, bizpol_cfg)

        firewall_cfg = edge_cfg.firewall
        if firewall_cfg:
            await process_firewall(shared, firewall_cfg)

    except Exception as e:
        print(e)


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
