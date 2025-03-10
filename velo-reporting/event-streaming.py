"""
Demonstrate continuously streaming events from the VCO into a Python app.
This script needs to be updated to account for id -> logicalId change in VCO 6.2.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import AsyncGenerator, cast
import aiohttp
import dotenv

from veloapi.api import get_enterprise_events_raw
from veloapi.models import CommonData
from veloapi.util import read_env

vco_fqdn = "vco.velocloud.net"
vco_api_token = ""
enterprise_id = 123


@dataclass
class EnterpriseEvent:
    id: int | None
    timestamp: datetime
    event: str
    category: str
    severity: str
    message: str
    detail: str
    username: str | None
    edge_name: str | None


async def get_enterprise_events_stream(
    c: CommonData, start_time: datetime, poll_interval: timedelta
) -> AsyncGenerator[EnterpriseEvent, None]:
    next_id = 0
    interval_seconds = poll_interval.total_seconds()

    while True:
        poll_start_time = datetime.now()
        next_page = None
        more = True

        while more:
            resp = await get_enterprise_events_raw(c, start_time, next_id, next_page)
            meta: dict[str, dict] = cast(dict[str, dict], resp.get("metaData", {}))
            more = meta.get("more", False)
            next_page = cast(str | None, meta.get("nextPageLink", None))

            data = resp.get("data", [])
            for d in data:
                event_id = d.get("id", None)
                next_id = (event_id + 1) if event_id >= next_id else next_id

                event_time_epoch = d.get("eventTime", None)
                event_time_datetime = (
                    datetime.fromisoformat(event_time_epoch)
                    if event_time_epoch
                    else datetime.now()
                )
                yield EnterpriseEvent(
                    event_id,
                    event_time_datetime,
                    d.get("event", ""),
                    d.get("category", ""),
                    d.get("severity", ""),
                    d.get("message", ""),
                    d.get("detail", ""),
                    d.get("enterpriseUsername", None),
                    d.get("edgeName", None),
                )

        elapsed_seconds = (datetime.now() - poll_start_time).total_seconds()
        # 0.5 < interval remaining seconds < interval total seconds
        sleep_time = min(max(0.5, interval_seconds - elapsed_seconds), interval_seconds)

        await asyncio.sleep(sleep_time)


async def main(session: aiohttp.ClientSession):
    common = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    start_time = datetime.now() - timedelta(minutes=5)

    async for e in get_enterprise_events_stream(
        common, start_time, timedelta(seconds=5)
    ):
        # do something with the event - submit to webhook server, insert into DB, etc.
        print(e)


async def async_main():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(async_main())
