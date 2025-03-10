"""
Run remote diagnostics across many edges.
"""

from dataclasses import dataclass
import datetime
import json
import asyncio
import aiostream
from typing import Any, Dict, List
import aiohttp
import websockets
import dotenv

from veloapi.api import get_enterprise_edge_list_full
from veloapi.models import CommonData, EnterpriseEdgeListEdge
from veloapi.util import read_env


@dataclass
class EdgeEntry:
    name: str
    logical_id: str


@dataclass
class EdgeDiagnosticResult:
    name: str
    logical_id: str
    timeout_at: datetime.datetime
    result: Any


async def run_bulk_diagnostics(
    c: CommonData,
    edges: List[EdgeEntry],
    res_format: str,
    test_name: str,
    parameters: Dict[str, Any],
    max_active_edges: int = 15,
    edge_action_timeout_seconds: int = 60,
) -> List[EdgeDiagnosticResult]:
    timeout_at = datetime.datetime.now() + datetime.timedelta(minutes=2)
    queued = list(
        [EdgeDiagnosticResult(e.name, e.logical_id, timeout_at, None) for e in edges]
    )
    num_active = 0
    waiting_for_action: dict[str, EdgeDiagnosticResult] = dict()
    finished: dict[str, EdgeDiagnosticResult] = dict()

    async with websockets.connect(
        f"wss://{c.vco}/ws/",
        extra_headers={
            "Authorization": f"Token {c.token}",
        },
    ) as ws:
        # wait for noop with token
        token_msg = json.loads(await ws.recv())
        token: str = token_msg["token"]
        total_done = 0

        # main loop for working thru the task set
        while len(queued) > 0 or num_active > 0:
            print(
                "{} queued, {} waiting_for_action, {} done".format(
                    len(queued),
                    len(waiting_for_action),
                    len(finished),
                )
            )
            # add more active edges if possible
            new_tasks = set()
            while num_active < max_active_edges and len(queued) > 0:
                edge = queued.pop()
                new_tasks.add(
                    ws.send(
                        json.dumps(
                            {
                                "action": "runDiagnostics",
                                "data": {
                                    "logicalId": edge.logical_id,
                                    "resformat": res_format,
                                    "test": test_name,
                                    "parameters": parameters,
                                },
                                "token": token,
                            }
                        )
                    )
                )
                edge.timeout_at = datetime.datetime.now() + datetime.timedelta(
                    seconds=edge_action_timeout_seconds
                )
                waiting_for_action[edge.logical_id] = edge
                num_active += 1
            if len(new_tasks) > 0:
                await asyncio.gather(*new_tasks)

            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), 5))

                action: str | None = m.get("action", None)
                logicalId: str = m.get("data", {}).get("logicalId", "")
                if action == "runDiagnostics":
                    e = waiting_for_action.get(logicalId, None)
                    if e:
                        del waiting_for_action[logicalId]
                        num_active -= 1

                        output = (
                            m.get("data", {}).get("results", {}).get("output", None)
                        )
                        if output:
                            if res_format == "JSON":
                                output = json.loads(output)
                            e.result = output
                            finished[logicalId] = e
                            total_done += 1
                        else:
                            pass
                else:
                    print(m)
            except TimeoutError as e:
                print("timed out waiting for recv")

            now = datetime.datetime.now()
            for id, e in waiting_for_action.items():
                if now > e.timeout_at:
                    del waiting_for_action[id]
                    print("edge {} timed out waiting for action".format(e.name))
                    num_active -= 1

    return list(finished.values())


async def main(session: aiohttp.ClientSession):
    common = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    # stream all edges using paginated API, excluding those which are not CONNECTED
    def edge_filter(e: EnterpriseEdgeListEdge) -> bool: return e.edge_state == "CONNECTED"

    chunk_stream = (
        aiostream.stream.iterate(get_enterprise_edge_list_full(common, None, None))
        | aiostream.pipe.filter(edge_filter)
        | aiostream.pipe.chunks(250)
    )

    full_result = []

    async with chunk_stream.stream() as s:
        async for edge_batch in s:
            try:
                edges = [
                    EdgeEntry(e.name if e.name else "", e.logical_id)
                    for e in edge_batch
                    if e.logical_id
                ]

                results = await run_bulk_diagnostics(
                    common,
                    edges,
                    test_name="ARP_DUMP",
                    res_format="JSON",
                    parameters={"count": 100},
                )

                for r in results:
                    full_result.append(
                        {
                            "name": r.name,
                            "data": r.result,
                        }
                    )

            except Exception as e:
                print(e)

    with open("diagnostics_results.json", "w") as f:
        json.dump(full_result, f, indent=2)


async def main_wrapper():
    async with aiohttp.ClientSession() as session:
        await main(session)


if __name__ == "__main__":
    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(main_wrapper())
