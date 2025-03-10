"""
Minimal example of running remote diagnostic using the Velo API.
"""

import json
import asyncio
from typing import Any, Dict
import aiohttp
import websockets
import dotenv

from veloapi.models import CommonData
from veloapi.util import read_env

async def run_gw_route_dump(c: CommonData, enterprise_logical_id: str, gw_logical_id: str, segment_id: int) -> Dict[str, Any]:
    async with websockets.connect(
        f"wss://{c.vco}/ws/",
        extra_headers={
            "Authorization": f"Token {c.token}",
        },
    ) as ws:
        # wait for noop with token
        token_msg = json.loads(await ws.recv())
        token: str = token_msg["token"]

        await ws.send(
            json.dumps(
                {
                    "action": "getGwRouteTable",
                    "data": {
                        "segmentId": segment_id,
                        "logicalId": gw_logical_id,
                        "enterpriseLogicalId": enterprise_logical_id,
                    },
                    "token": token,
                }
            )
        )

        return json.loads(await asyncio.wait_for(ws.recv(), 60))


async def run_edge_remote_diagnostic(c: CommonData, edge_logical_id: str) -> Dict[str, Any]:
    async with websockets.connect(
        f"wss://{c.vco}/ws/",
        extra_headers={
            "Authorization": f"Token {c.token}",
        },
    ) as ws:
        # wait for noop with token
        token_msg = json.loads(await ws.recv())
        token: str = token_msg["token"]

        await ws.send(
            json.dumps(
                {
                    "action": "runDiagnostics",
                    "data": {
                        "logicalId": edge_logical_id,
                        "test": "INTERFACE_STATUS",
                    },
                    "token": token,
                }
            )
        )

        return json.loads(await asyncio.wait_for(ws.recv(), 60))


async def main(session: aiohttp.ClientSession):
    common = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    edge_logical_id = "abcd-1234-efgh-5678"
    resp = await run_edge_remote_diagnostic(common, edge_logical_id)

    print(json.dumps(resp, indent=2))


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    dotenv.load_dotenv(".env", verbose=True, override=True)
    asyncio.run(main_wrapper())
