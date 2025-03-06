from collections import deque
import time
import datetime
import asyncio
import logging
import aiohttp
import dotenv
import duckdb
import polars as pl

from veloapi.api import (
    FlowStatsFilter,
    get_enterprise_flow_metrics,
    get_routable_applications,
)
from veloapi.models import CommonData
from veloapi.util import read_env


def floor_datetime_to_start_of_day(dt: datetime.datetime):
    return dt - datetime.timedelta(
        hours=dt.hour, minutes=dt.minute, seconds=dt.second, microseconds=dt.microsecond
    )


def build_ent_flow_metrics_df(
    metric_rows: list[dict[str, int | str]],
    start_time: datetime.datetime,
    view_by: str,
    additional_fields: None | dict[str, int | str | datetime.datetime] = None,
) -> pl.DataFrame:
    dataframe_dict = {
        "startTime": [start_time] * len(metric_rows),
        view_by: [row[view_by] for row in metric_rows],
        "bytesRx": [row["bytesRx"] for row in metric_rows],
        "bytesTx": [row["bytesTx"] for row in metric_rows],
        "totalBytes": [row["bytesRx"] + row["bytesTx"] for row in metric_rows],
        "packetsRx": [row["packetsRx"] for row in metric_rows],
        "packetsTx": [row["packetsTx"] for row in metric_rows],
        "totalPackets": [row["packetsRx"] + row["packetsTx"] for row in metric_rows],
    }

    if additional_fields is not None:
        for k, v in additional_fields.items():
            dataframe_dict[k] = [v] * len(metric_rows)

    return pl.DataFrame(dataframe_dict)


async def fetch_enterprise_traffic_data(
    data: CommonData,
    db: duckdb.DuckDBPyConnection,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
):
    start_time = floor_datetime_to_start_of_day(start_time)
    end_time = floor_datetime_to_start_of_day(end_time)
    if start_time == end_time:
        end_time += datetime.timedelta(days=1)

    logging.info(f"Fetching enterprise traffic data from {start_time} to {end_time}")

    current_interval_start = start_time
    while current_interval_start < end_time:
        current_interval_end = current_interval_start + datetime.timedelta(hours=1)

        start_time_int = int(1000 * current_interval_start.timestamp())
        end_time_int = int(1000 * current_interval_end.timestamp())

        logging.info(
            "Fetching enterprise flow metrics for interval %s to %s",
            current_interval_start,
            current_interval_end,
        )

        start_ts = time.time()
        apps_global = await get_enterprise_flow_metrics(
            data,
            "application",
            start_time_int,
            end_time_int,
            16,
            "bytesRx",
            [
                FlowStatsFilter(field="application", op="!=", value=4095),
            ],
        )
        logging.info(f"Got app metrics in {time.time() - start_ts:.2f}s")
        # insert into DB
        apps_df = build_ent_flow_metrics_df(
            apps_global, current_interval_start, "application"
        )

        db.execute(
            "INSERT INTO app_stats ( {0} ) SELECT {0} FROM apps_df".format(
                ", ".join(apps_df.columns)
            )
        )

        job_queue = deque(apps_global)
        active_queries = set()
        max_concurrency = 4

        async def per_app_task(app):
            app_id = app["application"]
            start_ts = time.time()
            app_edges = await get_enterprise_flow_metrics(
                data,
                "edgeLogicalId",
                start_time_int,
                end_time_int,
                None,
                None,
                [FlowStatsFilter(field="application", op="=", value=app_id)],
            )
            logging.info(f"Got per-edge app metrics in {time.time() - start_ts:.2f}s")
            app_edges_df = build_ent_flow_metrics_df(
                app_edges,
                current_interval_start,
                "edgeLogicalId",
                {"application": app_id},
            )
            db.execute(
                "INSERT INTO app_edge_stats ( {0} ) SELECT {0} FROM app_edges_df".format(
                    ", ".join(app_edges_df.columns)
                )
            )

            start_ts = time.time()
            app_clients = await get_enterprise_flow_metrics(
                data,
                "sourceIp",
                start_time_int,
                end_time_int,
                128,
                "packetsRx",
                [FlowStatsFilter(field="application", op="=", value=app_id)],
            )
            logging.info(f"Got per-client app metrics in {time.time() - start_ts:.2f}s")

            app_clients_df = build_ent_flow_metrics_df(
                app_clients, current_interval_start, "sourceIp", {"application": app_id}
            )
            db.execute(
                "INSERT INTO app_client_stats ( {0} ) SELECT {0} FROM app_clients_df".format(
                    ", ".join(app_clients_df.columns)
                )
            )

        while len(job_queue) > 0 or len(active_queries) > 0:
            while len(active_queries) < max_concurrency and len(job_queue) > 0:
                app = job_queue.popleft()
                active_queries.add(asyncio.create_task(per_app_task(app)))

            done_queries, _ = await asyncio.wait(active_queries, return_when=asyncio.FIRST_COMPLETED)
            active_queries = active_queries.difference(done_queries)

        current_interval_start = current_interval_end

    routable_apps = await get_routable_applications(data)
    all_apps_df = pl.DataFrame(
        {"id": list(routable_apps.keys()), "name": list(routable_apps.values())}
    )

    db.execute(
        "INSERT OR REPLACE INTO app_names ( {0} ) SELECT {0} FROM all_apps_df".format(
            ", ".join(all_apps_df.columns)
        )
    )


def create_table(db):
    db.sql(
        """
CREATE TABLE IF NOT EXISTS flow_stats (
    edgeId INTEGER,
    sourceIp TEXT,
    destIp TEXT,
    transport INTEGER,
    destPort INTEGER,
    linkId INTEGER,
    startTime TIMESTAMP,
    application INTEGER,
    category INTEGER,
    destFQDN TEXT,
    destDomain TEXT,
    segmentId INTEGER,
    endTime TIMESTAMP,
    nextHop TEXT,
    route TEXT,
    packetsReceived UBIGINT,
    packetsSent UBIGINT,
    hostName TEXT,
    businessRuleName TEXT,
    firewallRuleName TEXT,
    bytesRx UBIGINT,
    bytesTx UBIGINT,
    totalBytes UBIGINT,
    packetsRx UBIGINT,
    packetsTx UBIGINT,
    totalPackets UBIGINT,
    flowCount UINTEGER,
    linkName TEXT,
    isp TEXT
)
"""
    )

    db.sql(
        """
CREATE TABLE IF NOT EXISTS app_stats (
    startTime TIMESTAMP,
    application INTEGER,
    bytesRx UBIGINT,
    bytesTx UBIGINT,
    totalBytes UBIGINT,
    packetsRx UBIGINT,
    packetsTx UBIGINT,
    totalPackets UBIGINT
)
"""
    )

    db.sql(
        """
CREATE TABLE IF NOT EXISTS app_edge_stats (
    startTime TIMESTAMP,
    application INTEGER,
    edgeLogicalId UUID,
    bytesRx UBIGINT,
    bytesTx UBIGINT,
    totalBytes UBIGINT,
    packetsRx UBIGINT,
    packetsTx UBIGINT,
    totalPackets UBIGINT
)
"""
    )

    db.sql(
        """
CREATE TABLE IF NOT EXISTS app_client_stats (
    startTime TIMESTAMP,
    application INTEGER,
    sourceIp TEXT,
    bytesRx UBIGINT,
    bytesTx UBIGINT,
    totalBytes UBIGINT,
    packetsRx UBIGINT,
    packetsTx UBIGINT,
    totalPackets UBIGINT
)
"""
    )

    db.sql(
        """
CREATE TABLE IF NOT EXISTS app_names (
    id INTEGER PRIMARY KEY,
    name TEXT
)
"""
    )


async def main(session: aiohttp.ClientSession):
    data = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    db = duckdb.connect("data/vco-analysis.db")
    create_table(db)

    start_time = datetime.datetime.now() - datetime.timedelta(days=3)
    end_time = datetime.datetime.now() - datetime.timedelta(days=2)
    await fetch_enterprise_traffic_data(data, db, start_time, end_time)

    db.close()


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(main_wrapper())
