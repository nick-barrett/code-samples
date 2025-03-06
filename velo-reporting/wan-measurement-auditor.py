import asyncio
from dataclasses import dataclass
import datetime
from typing import cast
import aiohttp
import dotenv
import json
import os
import pandas as pd
from requests import Session, session
import time

from veloapi.api import get_aggregate_edge_link_metrics, get_edge_configuration_stack, update_configuration_module
from veloapi.models import CommonData, ConfigProfile
from veloapi.util import read_env

@dataclass
class LinkData:
    edge_id: int
    edge_name: str
    link_internal_id: str
    link_name: str
    isp: str
    upstream_mbps: float
    downstream_mbps: float


async def get_link_data(shared: CommonData) -> list[LinkData]:
    start_time = datetime.datetime.now() - datetime.timedelta(minutes=30)
    resp = await get_aggregate_edge_link_metrics(
        shared, start_time, True, ["bpsOfBestPathRx", "bpsOfBestPathTx"]
    )

    return [
        LinkData(
            l["link"]["edgeId"],
            l["link"]["edgeName"],
            l["link"]["internalId"],
            l["link"]["displayName"],
            l["link"]["isp"],
            l["bpsOfBestPathTx"] / 1000000,
            l["bpsOfBestPathRx"] / 1000000,
        )
        for l in resp
    ]


async def audit_links(shared: CommonData, apply_changes=False):
    # fetch the link metrics and build pandas frame
    links_df = pd.DataFrame(await get_link_data(shared))

    if len(links_df) == 0:
        print("no links found")
        return

    # select any link which measured 200 > downstream > 175 while having upstream < 175
    # these are candidates for when burst mode should have been enabled
    affected_links = links_df[
        (links_df["downstream_mbps"] < 200.0)
        & (links_df["downstream_mbps"] > 175.0)
        & (links_df["upstream_mbps"] < 175.0)
    ]

    affected_edges = affected_links.groupby("edge_id")

    print(
        f"{len(affected_links)} potentially affected link(s) found on {len(affected_edges)} edge(s)"
    )
    print("checking configuration on those edges to confirm...")
    if not apply_changes:
        print("- not applying configuration changes due to audit-only mode")

    affected_links_output = None
    affected_links_output_list = []

    for edge_id, df in affected_edges:
        # don't spam getEdgeConfigurationStack
        time.sleep(1)

        edge_stack = await get_edge_configuration_stack(shared, cast(int, edge_id))
        cfg_profile = ConfigProfile(edge_stack[0])

        if cfg_profile.wan is None:
            continue

        # retrieve edge_name scalar from first row
        edge_name = df["edge_name"].head(1).item()

        wan_id = cfg_profile.wan.data["id"]
        wan_data = cfg_profile.wan.data["data"]
        wan_links = cfg_profile.wan.data["links"]

        # array to track affected link names
        confirmed_affected_link_names = []

        affected_link_was_found = False
        for wan_link in wan_links:
            if wan_link["bwMeasurement"] != "SLOW_START":
                continue

            link_internal_id = wan_link["internalId"]

            # check if this link exists in the candidate list
            id_series = df["link_internal_id"]
            if len(id_series.where(id_series == link_internal_id)) > 0:
                # get the dataframe for this link
                link_row = df.loc[df["link_internal_id"] == link_internal_id]
                affected_links_output_list.append(link_row)

                # save link name to display later
                confirmed_affected_link_names.append(wan_link["name"])

                # STATIC means burst mode
                wan_link["bwMeasurement"] = "STATIC"

                # set flag to update the module once done iterating over links
                affected_link_was_found = True

        if affected_link_was_found:
            updated_links_text = ", ".join(confirmed_affected_link_names)
            print(
                f"confirmed as affected - edge [{edge_name}] - link(s) [{updated_links_text}]"
            )
            if apply_changes:
                print("- applying fix to WAN module")
                update_configuration_module(shared, wan_id, wan_data)

    affected_links_output = pd.concat(affected_links_output_list)
    affected_links_output.to_csv("affected_links.csv")


async def main(shared: CommonData):
    audit_links(shared, apply_changes=False)


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
    asyncio.run(async_main(".env"))
