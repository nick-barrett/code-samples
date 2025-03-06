import asyncio
import datetime
from aiohttp import ClientSession
import dotenv
from veloapi.api import (
    get_aggregate_edge_link_metrics,
    get_edge_flow_visibility_metrics,
)
from veloapi.models import CommonData
from veloapi.util import read_env

import pandas as pd
import duckdb


def create_link_metrics_table(con: duckdb.DuckDBPyConnection):
    con.sql(
        """
create table link_metrics
(
    enterpriseId int,
    enterpriseName varchar,
    edgeId int, 
    edgeName varchar,
    bytesRx ubigint, 
    bytesTx ubigint, 
    bytesTotal ubigint, 
    packetsRx ubigint, 
    packetsTx ubigint
    packetsTotal ubigint, 
)
"""
    )

def create_flow_metrics_table(con: duckdb.DuckDBPyConnection):
    con.sql("""
create table flow_metrics (
    edgeId int,
    startTime timestamp with time zone,
    endTime timestamp with time zone,
    application int,
    category int,
    bytesRx ubigint,
    bytesTx ubigint,
    flowCount int,
    businessPolicyName varchar,
    firewallRuleName varchar,
    segmentId int,
    hostName varchar,
    sourceIp inet,
    destIp inet,
    destPort int,
    transport int,
    destDomain varchar,
    destFQDN varchar,
    isp varchar,
    linkId int,
    linkName varchar,
    nextHop varchar,
    route varchar,
    packetsRx ubigint,
    packetsTx ubigint,
    totalBytes ubigint,
    totalPackets ubigint
)
""")


async def fetch_flows_main(session: ClientSession, con: duckdb.DuckDBPyConnection):
    common = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    create_flow_metrics_table(con)

    edge_ids = [
        1, 2, 3
    ]

    delta = datetime.timedelta(days=2)

    for edge_id in edge_ids:
        data = {
            "edgeId": [],
            "startTime": [],
            "endTime": [],
            "application": [],
            "category": [],
            "bytesRx": [],
            "bytesTx": [],
            "flowCount": [],
            "businessPolicyName": [],
            "firewallRuleName": [],
            "segmentId": [],
            "hostName": [],
            "sourceIp": [],
            "destIp": [],
            "destPort": [],
            "transport": [],
            "destDomain": [],
            "destFQDN": [],
            "isp": [],
            "linkId": [],
            "linkName": [],
            "nextHop": [],
            "route": [],
            "packetsRx": [],
            "packetsTx": [],
            "totalBytes": [],
            "totalPackets": [],
        }

        async for flow in get_edge_flow_visibility_metrics(
            common,
            edge_id,
            datetime.datetime.now() - delta,
            datetime.datetime.now(),
        ):
            data["edgeId"].append(edge_id)
            data["startTime"].append(flow.start_time)
            data["endTime"].append(flow.end_time)
            data["application"].append(flow.application)
            data["category"].append(flow.category)
            data["bytesRx"].append(flow.bytes_rx)
            data["bytesTx"].append(flow.bytes_tx)
            data["flowCount"].append(flow.flow_count)
            data["businessPolicyName"].append(flow.business_policy_name)
            data["firewallRuleName"].append(flow.firewall_rule_name)
            data["segmentId"].append(flow.segment_id)
            data["hostName"].append(flow.client_hostname)
            data["sourceIp"].append(flow.source_ip)
            data["destIp"].append(flow.dest_ip)
            data["destPort"].append(flow.dest_port)
            data["transport"].append(flow.transport)
            data["destDomain"].append(flow.dest_domain)
            data["destFQDN"].append(flow.dest_fqdn)
            data["isp"].append(flow.isp)
            data["linkId"].append(flow.link_id)
            data["linkName"].append(flow.link_name)
            data["nextHop"].append(flow.next_hop)
            data["route"].append(flow.route)
            data["packetsRx"].append(flow.packets_rx)
            data["packetsTx"].append(flow.packets_tx)
            data["totalBytes"].append(flow.total_bytes)
            data["totalPackets"].append(flow.total_packets)

        flow_metrics_df = pd.DataFrame.from_dict(data)
        flow_metrics_df_sorted = flow_metrics_df.sort_values(by="startTime")

        con.sql("INSERT INTO flow_metrics SELECT * FROM flow_metrics_df_sorted")


async def fetch_links_main(session: ClientSession, con: duckdb.DuckDBPyConnection):
    common = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    # create_table(con)

    # see veloapi/api.py#get_edge_flow_visibility_metrics_fast for an example of using ijson
    # it would improve this performance
    link_metrics = await get_aggregate_edge_link_metrics(
        common,
        datetime.datetime.now() - datetime.timedelta(days=1),
        True,
        ["bytesRx", "bytesTx", "totalBytes", "totalPackets", "packetsRx", "packetsTx"],
    )

    data = {
        "enterpriseId": [],
        "enterpriseName": [],
        "edgeId": [],
        "edgeName": [],
        "bytesRx": [],
        "bytesTx": [],
        "bytesTotal": [],
        "packetsRx": [],
        "packetsTx": [],
        "packetsTotal": [],
    }

    for link in link_metrics:
        detail = link.get("link", {})

        data["enterpriseId"].append(detail.get("enterpriseId", None))
        data["enterpriseName"].append(detail.get("enterpriseName", None))
        data["edgeId"].append(detail.get("edgeId", None))
        data["edgeName"].append(detail.get("edgeName", None))
        data["bytesRx"].append(link.get("bytesRx", 0))
        data["bytesTx"].append(link.get("bytesTx", 0))
        data["bytesTotal"].append(link.get("totalBytes", 0))
        data["packetsRx"].append(link.get("packetsRx", 0))
        data["packetsTx"].append(link.get("packetsTx", 0))
        data["packetsTotal"].append(link.get("totalPackets", 0))

    link_metrics_df = pd.DataFrame.from_dict(data)

    con.sql("CREATE TABLE link_metrics AS SELECT * FROM link_metrics_df")


async def async_main():
    async with ClientSession() as session:
        with duckdb.connect("data/top-talkers.db") as con:
            #await fetch_links_main(session, con)
            await fetch_flows_main(session, con)


if __name__ == "__main__":
    dotenv.load_dotenv("env/.env", override=True)

    asyncio.run(async_main())
