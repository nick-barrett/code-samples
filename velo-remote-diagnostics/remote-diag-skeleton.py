from dataclasses import dataclass
import os
import json
import asyncio
from typing import Any, Dict
import aiohttp
import websockets
import dotenv


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
        self.validate()

        self.session.headers.update({"Authorization": f"Token {self.token}"})

    def validate(self):
        if any(
            missing_inputs := [
                v is None for v in [self.vco, self.token, self.enterprise_id]
            ]
        ):
            raise ValueError(f"missing input data: {missing_inputs}")


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


async def run_remote_diagnostic(c: CommonData, edge_logical_id: str) -> Dict[str, Any]:
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
    resp = await run_remote_diagnostic(common, edge_logical_id)

    print(json.dumps(resp, indent=2))


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    dotenv.load_dotenv(".env", verbose=True, override=True)
    asyncio.run(main_wrapper())
