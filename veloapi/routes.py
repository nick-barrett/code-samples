
import asyncio
import dataclasses
import datetime
import json
import logging
from typing import Any, cast
import websockets

from veloapi.api import get_edge_sdwan_peers
from veloapi.models import CommonData, EdgeRouteEntry, EnterpriseEdgeListEdge, GatewayRouteEntry

type EdgeId = str
type EdgeLogicalId = str
type GwLogicalId = str
type Route = tuple[str, str]
type EdgeName = str

@dataclasses.dataclass
class EdgeRouteRequestState:
    logical_id: EdgeLogicalId
    timeout_at: datetime.datetime
    timeout_sec: int
    attempt_count: int = 1


@dataclasses.dataclass
class GatewayRouteRequestState:
    gateway_logical_id: GwLogicalId
    enterprise_logical_id: str
    segment_id: int
    timeout_at: datetime.datetime
    timeout_sec: int
    attempt_count: int = 1

async def get_relevant_gateways_for_edge(
    c: CommonData, hubs: list[EnterpriseEdgeListEdge]
) -> dict[str, set[str]]:
    relevant_peers: dict[str, set[str]] = dict()

    filters = [{"field": "peerType", "operator": "is", "value": "GATEWAY"}]
    for hub in hubs:
        hub_peers = set()

        resp = await get_edge_sdwan_peers(c, hub.id, None, None, "and", filters)
        peers = resp["data"]

        for peer in peers:
            gw_logical_id = "gateway{}".format(peer["deviceLogicalId"])
            hub_peers.add(gw_logical_id)

        relevant_peers[hub.logical_id] = hub_peers

    return relevant_peers


class RouteDiag:
    def __init__(self, ws: websockets.WebSocketClientProtocol, data: CommonData, max_tries: int = 5):
        self.ws = ws
        self.data = data
        self.max_tries = max_tries
        self.token = None
        self.tasks = set()

        self.pending_gateways: dict[GwLogicalId, GatewayRouteRequestState] = {}
        self.pending_edges: dict[EdgeLogicalId, EdgeRouteRequestState] = {}

        self.gateway_routes: dict[GwLogicalId, list[GatewayRouteEntry]] = {}
        self.edge_routes: dict[EdgeLogicalId, list[EdgeRouteEntry]] = {}
        self.gateway_edges: dict[GwLogicalId, set[EdgeLogicalId]] = {}
        self.edge_gateways: dict[EdgeLogicalId, set[GwLogicalId]] = {}

    def _handle_edge_routes(self, logical_id: EdgeLogicalId, routes: list[dict]):
        if logical_id in self.pending_edges:
            logging.info(f"Removed edge {logical_id} from pending list")
            del self.pending_edges[logical_id]
        else:
            logging.error(f"Edge {logical_id} not in pending list")

        logging.info(f"Begin processing routes for edge {logical_id}")

        if logical_id in self.edge_routes:
            self.edge_routes[logical_id].clear()
        else:
            self.edge_routes[logical_id] = []

        for route in routes:
            r = EdgeRouteEntry.from_dict(route)
            if r.route_type == "Edge":
                self.edge_routes[logical_id].append(r)

        logging.info(
            f"Received {len(self.edge_routes[logical_id])} routes for edge {logical_id}"
        )

    def _handle_edge_response(self, logical_id: str, test_name: str, response: dict):
        if test_name == "ROUTE_DUMP":
            routes = response.get("ROUTE_DUMP", {}).get("result", [[]])[0]

            if len(routes) > 0:
                self._handle_edge_routes(logical_id, routes)
            else:
                logging.info(f"No routes in response for edge {logical_id}")

    def _handle_gw_routes(self, logical_id: str, routes: list[dict]):
        if logical_id in self.pending_gateways:
            logging.info(f"Removed gateway {logical_id} from pending list")
            del self.pending_gateways[logical_id]
        else:
            logging.error(f"Gateway {logical_id} not in pending list")

        if logical_id in self.gateway_routes:
            self.gateway_routes[logical_id].clear()
        else:
            self.gateway_routes[logical_id] = []

        logging.info(f"Begin processing routes for gateway {logical_id}")

        for route in routes:
            r = GatewayRouteEntry.from_dict(route)
            if (
                r.type == "edge2edge"
            ):
                self.gateway_routes[logical_id].append(r)

        logging.info(
            f"Received {len(self.gateway_routes[logical_id])} routes for gateway {logical_id}"
        )

    def handle_message(self, msg: Any) -> bool:
        logging.info("Received message")

        m = json.loads(msg)

        action: str | None = m.get("action", None)

        m_data = m.get("data", {})
        if not isinstance(m_data, dict):
            logging.info(f"Invalid message data: {json.dumps(m)}")
            return True

        logical_id: str = m_data.get("logicalId", "")
        if action == "runDiagnostics":
            test_name = m.get("data", {}).get("test", "")

            results = m.get("data", {}).get("results", {}).get("output", None)
            results_dict = json.loads(results) if results else None

            if results_dict is not None:
                logging.info(f"Received diagnostics response for edge {logical_id}")
                self._handle_edge_response(logical_id, test_name, results_dict)

                return True

        elif action == "getGwRouteTable":
            logging.info(f"Received a gateway route table for gateway {logical_id}")

            result = cast(list[dict], m.get("data", {}).get("result", []))
            self._handle_gw_routes(logical_id, result)

            return True

        elif action == "noop":
            self.token = m.get("token", None)
            logging.info("Received remote diagnostics token")
            return True
        else:
            logging.error(f"Unknown msg: {json.dumps(m)}")

        return False

    def request_gateway_routes(
        self,
        segment_id: int,
        gateway_logical_id: GwLogicalId,
        enterprise_logical_id: str,
        timeout_sec: int = 20,
    ):
        self.tasks.add(
            self.ws.send(
                json.dumps(
                    {
                        "action": "getGwRouteTable",
                        "data": {
                            "segmentId": segment_id,
                            "logicalId": gateway_logical_id,
                            "enterpriseLogicalId": enterprise_logical_id,
                        },
                        "token": self.token,
                    }
                )
            )
        )
        request_timeout = datetime.datetime.now() + datetime.timedelta(
            seconds=timeout_sec
        )
        state = GatewayRouteRequestState(
            gateway_logical_id,
            enterprise_logical_id,
            segment_id,
            request_timeout,
            timeout_sec,
        )
        self.pending_gateways[gateway_logical_id] = state
        logging.info(f"Requesting routes for gateway {gateway_logical_id}")
        return state

    def request_edge_routes(self, edge_logical_id: EdgeLogicalId, timeout_sec: int = 30):
        self.tasks.add(
            self.ws.send(
                json.dumps(
                    {
                        "action": "runDiagnostics",
                        "data": {
                            "logicalId": edge_logical_id,
                            "test": "ROUTE_DUMP",
                            "parameters": {
                                "segment": "all",
                                "prefix": "",
                                "routes": "all",
                            },
                            "resformat": "JSON",
                        },
                        "token": self.token,
                    }
                )
            )
        )

        request_timeout = datetime.datetime.now() + datetime.timedelta(
            seconds=timeout_sec
        )
        state = EdgeRouteRequestState(edge_logical_id, request_timeout, timeout_sec)
        self.pending_edges[edge_logical_id] = state
        logging.info(f"Requesting routes for edge {edge_logical_id}")
        return state

    async def flush_requests(self):
        await asyncio.gather(*self.tasks)
        self.tasks.clear()

    def handle_request_timeouts(self) -> int:
        now = datetime.datetime.now()

        requeue_count: int = 0

        timed_out_edges = {
            logical_id: edge
            for logical_id, edge in self.pending_edges.items()
            if now > edge.timeout_at
        }
        for logical_id, edge in timed_out_edges.items():
            del self.pending_edges[logical_id]

            if edge.attempt_count < self.max_tries:
                s = self.request_edge_routes(logical_id, edge.timeout_sec)
                s.attempt_count += 1

                requeue_count += 1
            else:
                logging.error(
                    f"Edge {logical_id} timed out after {edge.attempt_count} attempts"
                )

        timed_out_gateways = {
            logical_id: gw
            for logical_id, gw in self.pending_gateways.items()
            if now > gw.timeout_at
        }
        for logical_id, gw in timed_out_gateways.items():
            del self.pending_gateways[logical_id]

            if gw.attempt_count < self.max_tries:
                s = self.request_gateway_routes(
                    gw.segment_id, logical_id, gw.enterprise_logical_id, gw.timeout_sec
                )
                s.attempt_count += 1

                requeue_count += 1
            else:
                logging.error(
                    f"Gateway {logical_id} timed out after {gw.attempt_count} attempts"
                )

        return requeue_count

    def get_pending_count(self) -> int:
        logging.info(f"Pending edge count: {len(self.pending_edges)}")
        logging.info(f"Pending gateway count: {len(self.pending_gateways)}")
        return len(self.pending_edges) + len(self.pending_gateways)

    def _compute_gateway_edges(
        self, relevant_gateways: dict[EdgeLogicalId, set[GwLogicalId]]
    ):
        self.gateway_edges.clear()

        for edge_logical_id, gateways in relevant_gateways.items():
            for gw_logical_id in gateways:
                if gw_logical_id not in self.gateway_edges:
                    self.gateway_edges[gw_logical_id] = set([edge_logical_id])
                else:
                    self.gateway_edges[gw_logical_id].add(edge_logical_id)

    def _edge_uses_gateway(
        self, edge_logical_id: EdgeLogicalId, gateway_logical_id: GwLogicalId
    ) -> bool:
        return edge_logical_id in self.gateway_edges.get(gateway_logical_id, set())
