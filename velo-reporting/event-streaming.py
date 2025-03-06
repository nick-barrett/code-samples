import asyncio
from dataclasses import dataclass
from datetime import timedelta, datetime
import json
import os
from typing import AsyncGenerator, cast
import aiohttp
import dotenv

vco_fqdn = "vco.velocloud.net"
vco_api_token = ""
enterprise_id = 123


def read_env(name: str) -> str:
    value = os.getenv(name)
    assert value is not None, f"missing environment var {name}"
    return value


@dataclass
class CommonData:
    vco: str
    token: str
    enterprise_id: int
    session: aiohttp.ClientSession

    def __post_init__(self):
        self.session.headers.update({"Authorization": f"Token {self.token}"})


@dataclass
class EnterpriseEventV2:
    id: int | None
    timestamp: datetime
    event: str
    category: str
    severity: str
    message: str
    detail: str
    username: str | None
    edge_name: str | None


async def do_portal(c: CommonData, method: str, params: dict):
    async with c.session.post(
        f"https://{c.vco}/portal/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        },
    ) as req:
        resp = await req.json()
        if "result" not in resp:
            raise ValueError(json.dumps(resp, indent=2))
        return resp["result"]


async def get_enterprise_events_raw(
    c: CommonData, start_time: datetime, id: int | None, next_page: str | None = None
) -> dict[str, dict | list]:
    interval_object = {
        "start": int(start_time.timestamp() * 1000),
    }

    id = id if id else 0

    params_object = {
        "enterpriseId": c.enterprise_id,
        "filter": {"rules": [{"field": "id", "op": "greaterOrEquals", "values": [id]}]},
        "interval": interval_object,
    }

    if next_page:
        params_object["nextPageLink"] = next_page

    return await do_portal(
        c,
        "event/getEnterpriseEvents",
        params_object,
    )


async def get_enterprise_events_stream(
    c: CommonData, start_time: datetime, poll_interval: timedelta
) -> AsyncGenerator[EnterpriseEventV2, None]:
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
                yield EnterpriseEventV2(
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
