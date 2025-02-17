# Developed on Python 3.12.4 - may need to be modified for lesser versions

# built-in packages
import ssl
from typing import Any, AsyncGenerator, Literal, cast
import dataclasses
import datetime
import time
import os
import logging
import csv
import json
import asyncio

# third-party packages
import dataclasses_json
import dotenv
import aiohttp
import websockets

# maximum number of times to try getting routes from edge/gateway
max_tries = 5
# set to True to include a full route-dump for the hubs
dump_all_routes = True

class DataclassEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


def read_env(name: str) -> str:
    value = os.getenv(name)
    assert value is not None, f"missing environment var {name}"
    return value


@dataclasses.dataclass
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


@dataclasses_json.dataclass_json(letter_case=dataclasses_json.LetterCase.CAMEL)
@dataclasses.dataclass
class GetEnterpriseResult:
    id: int
    created: str
    modified: str
    network_id: int
    gateway_pool_id: int
    alerts_enabled: int
    operator_alerts_enabled: int
    endpoint_pki_mode: str
    name: str
    domain: str
    prefix: str | None
    logical_id: str
    account_number: str


@dataclasses_json.dataclass_json(letter_case=dataclasses_json.LetterCase.CAMEL)
@dataclasses.dataclass
class ListEdgeHaData:
    cluster_id: int | None = None
    cluster_name: str | None = None


@dataclasses_json.dataclass_json(letter_case=dataclasses_json.LetterCase.CAMEL)
@dataclasses.dataclass
class ListEdgeHa:
    data: ListEdgeHaData | None = None
    type: str | None = None


@dataclasses_json.dataclass_json(letter_case=dataclasses_json.LetterCase.CAMEL)
@dataclasses.dataclass
class EnterpriseEdgeListEdge:
    id: int | None
    logical_id: str | None
    name: str | None
    edge_state: str | None
    activation_state: str | None
    is_hub: bool | None
    ha: ListEdgeHa | None = None


@dataclasses_json.dataclass_json(letter_case=dataclasses_json.LetterCase.CAMEL)
@dataclasses.dataclass
class GatewayRouteEntry:
    network_addr: str
    network_mask: str
    type: str
    peer_name: str
    reachable: bool
    metric: int
    preference: int
    flags: str
    age: int
    c_tag: int
    s_tag: int
    handoff: str
    mode: str
    lost_reason: str


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class EdgeRouteEntry:
    route_type: str
    route_address: str
    route_netmask: str


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


async def get_enterprise(c: CommonData) -> GetEnterpriseResult:
    res = await do_portal(c, "enterprise/getEnterprise", {"id": c.enterprise_id})

    return GetEnterpriseResult.from_dict(res)


async def get_enterprise_edge_list_raw(
    c: CommonData,
    with_params: list[str] | None,
    filters: dict | None,
    next_page: str | None = None,
) -> dict[str, list | dict]:
    params_object: dict[str, Any] = {
        "enterpriseId": c.enterprise_id,
        "limit": 500,
        "sortBy": [{"attribute": "edgeState", "type": "ASC"}],
    }

    if with_params:
        params_object["with"] = with_params

    if filters:
        params_object["filters"] = filters
    else:
        params_object["_filterSpec"] = True

    if next_page:
        params_object["nextPageLink"] = next_page

    return await do_portal(c, "enterprise/getEnterpriseEdges", params_object)


async def get_enterprise_edge_list_full(
    c: CommonData, with_params: list[str] | None, filters: dict | None
) -> AsyncGenerator[EnterpriseEdgeListEdge, None]:
    next_page = None
    more = True

    while more:
        resp = await get_enterprise_edge_list_raw(c, with_params, filters, next_page)

        meta: dict[str, dict] = cast(dict[str, dict], resp.get("metaData", {}))
        more = meta.get("more", False)
        next_page = cast(str | None, meta.get("nextPageLink", None))

        data: list[dict[str, Any]] = cast(list[dict[str, Any]], resp.get("data", []))
        for d in data:
            yield EnterpriseEdgeListEdge.from_dict(d)  # type: ignore


AndFilter = Literal["and"]
OrFilter = Literal["or"]


async def get_edge_sdwan_peers(
    c: CommonData,
    edge_id: int,
    start_time: int | None = None,
    end_time: int | None = None,
    filter_type: AndFilter | OrFilter | None = None,
    filters: list[dict[str, Any]] | None = None,
) -> list[dict]:
    payload = {
        "edgeId": edge_id,
        "enterpriseId": c.enterprise_id,
    }

    if start_time is not None:
        payload.setdefault("interval", {})["start"] = start_time

        if end_time is not None:
            payload["interval"]["end"] = end_time

    if filter_type is not None and filters is not None:
        payload["filters"] = {
            filter_type: filters,
        }

        payload["_filterSpec"] = True

    return await do_portal(
        c,
        "edge/getEdgeSDWANPeers",
        payload,
    )


async def get_enterprise_logical_id(c: CommonData) -> str:
    e = await get_enterprise(c)
    return e.logical_id


async def get_all_hubs(c: CommonData) -> list[EnterpriseEdgeListEdge]:
    ent_id_str = str(c.enterprise_id)

    try:
        with open("route-check-cache.json", "r") as f:
            cache = {}
            cache_json = json.load(f)
            for ent_id, ent_data in cache_json.items():
                cache[ent_id] = {
                    "hubs": [
                        EnterpriseEdgeListEdge.from_dict(e)
                        for e in ent_data.get("hubs", [])
                    ]
                }
    except:
        cache = {}

    cache_hubs = cache.get(ent_id_str, {}).get("hubs", [])

    if len(cache_hubs) > 0:
        return cache_hubs
    else:
        hubs = []
        async for l in get_enterprise_edge_list_full(c, ["ha"], None):
            if l.is_hub:
                hubs.append(l)

        cache.setdefault(ent_id_str, {})["hubs"] = hubs

        with open("route-check-cache.json", "w") as f:
            json.dump(cache, f, cls=DataclassEncoder)

        return hubs


async def get_relevant_gateways(
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


type HubId = str
type HubLogicalId = str
type GwLogicalId = str
type Route = tuple[str, str]
type EdgeName = str

type ExpectedHubRouteMap = dict[Route, set[EdgeName]]
type ExpectedRouteMap = dict[HubId, ExpectedHubRouteMap]

type HubRouteSet = set[tuple[str, str]]
type RouteSet = dict[HubId, HubRouteSet]


def add_expected_hub_routes(
    expected_routes_dst: ExpectedHubRouteMap,
    routes: list[GatewayRouteEntry],
):
    for route in routes:
        key = (route.network_addr, route.network_mask)
        if key in expected_routes_dst:
            expected_routes_dst[key].add(route.peer_name)
        else:
            expected_routes_dst[key] = set([route.peer_name])


@dataclasses.dataclass
class EdgeRouteRequestState:
    logical_id: HubLogicalId
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


class RouteDiag:
    def __init__(self, ws: websockets.WebSocketClientProtocol):
        self.ws = ws
        self.token = None
        self.tasks = set()

        self.pending_gateways: dict[GwLogicalId, GatewayRouteRequestState] = {}
        self.pending_edges: dict[HubLogicalId, EdgeRouteRequestState] = {}

        self.gateway_routes: dict[GwLogicalId, list[GatewayRouteEntry]] = {}
        self.edge_routes: dict[HubLogicalId, list[EdgeRouteEntry]] = {}
        self.gateway_hubs: dict[GwLogicalId, set[HubLogicalId]] = {}

    def _handle_edge_routes(self, logical_id: HubLogicalId, routes: list[dict]):
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
            lower_name = r.peer_name.lower()
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

    def request_edge_routes(self, edge_logical_id: HubLogicalId, timeout_sec: int = 30):
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
        """
        Await all request send tasks to ensure that the requests are sent over the websocket.
        """
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

            if edge.attempt_count < max_tries:
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

            if gw.attempt_count < max_tries:
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

    def _compute_gateway_hubs(
        self, relevant_gateways: dict[HubLogicalId, set[GwLogicalId]]
    ):
        self.gateway_hubs.clear()

        for hub_logical_id, gateways in relevant_gateways.items():
            for gw_logical_id in gateways:
                if gw_logical_id not in self.gateway_hubs:
                    self.gateway_hubs[gw_logical_id] = set([hub_logical_id])
                else:
                    self.gateway_hubs[gw_logical_id].add(hub_logical_id)

    def _compute_hub_id_redirect_map(
        self, hubs: list[EnterpriseEdgeListEdge]
    ) -> dict[HubLogicalId, HubId]:
        hub_redirects: dict[str, str] = {}

        for hub in hubs:
            if (
                hub.ha is not None
                and hub.ha.data is not None
                and hub.ha.data.cluster_name is not None
            ):
                cluster_name = hub.ha.data.cluster_name
                hub_redirects[hub.logical_id] = cluster_name
            else:
                hub_redirects[hub.logical_id] = hub.logical_id

        return hub_redirects

    def _hub_uses_gateway(
        self, hub_logical_id: HubLogicalId, gateway_logical_id: GwLogicalId
    ) -> bool:
        return hub_logical_id in self.gateway_hubs.get(gateway_logical_id, set())

    def _compute_expected_hub_routes(
        self,
        hub_redirects: dict[HubLogicalId, HubId],
        hubs: list[EnterpriseEdgeListEdge],
    ) -> ExpectedRouteMap:
        """
        Compute the expected routes for each hub-id.
        Returns a dict mapping hub-id to a dict of (route, mask) -> edge-name-set.
        """
        expected_hub_routes: ExpectedRouteMap = {}

        # populate expected route dicts for each hub-id
        for id in hub_redirects.values():
            expected_hub_routes[id] = {}

        # add all routes for each gateway to the relevant dict
        for gw_logical_id, routes in self.gateway_routes.items():
            for hub in hubs:
                if self._hub_uses_gateway(hub.logical_id, gw_logical_id):
                    hub_id = hub_redirects[hub.logical_id]
                    add_expected_hub_routes(expected_hub_routes[hub_id], routes)

        return expected_hub_routes

    def _compute_hub_routes(
        self,
        hub_redirects: dict[HubLogicalId, HubId],
        hubs: list[EnterpriseEdgeListEdge],
    ) -> RouteSet:
        """
        Compute the routes for each hub-id.
        Returns a dict mapping hub-id to a set of (route, mask).
        """

        hub_routes: RouteSet = dict()

        for hub in hubs:
            this_hubs_routes: HubRouteSet = {
                (route.route_address, route.route_netmask)
                for route in self.edge_routes[hub.logical_id]
            }

            hub_id = hub_redirects[hub.logical_id]
            hub_routes.setdefault(hub_id, set()).update(this_hubs_routes)

        return hub_routes

    def compute_route_deltas(
        self,
        relevant_gateways: dict[HubLogicalId, set[GwLogicalId]],
        hubs: list[EnterpriseEdgeListEdge],
    ) -> list[tuple[HubId, Route, list[EdgeName]]]:
        """
        Compute the route deltas for each hub.
        """
        # all individual hub logical ids will be redirected to their cluster name if it exists
        # that value is referred to as 'hub-id' below

        self._compute_gateway_hubs(relevant_gateways)

        # dict[hub-logical-id -> hub-id]
        hub_redirects: dict[HubLogicalId, HubId] = self._compute_hub_id_redirect_map(
            hubs
        )

        # dict[hub-id ->
        #   dict[(net, mask) ->
        #     set[edge name]
        #   ]
        # ]
        expected_hub_routes: ExpectedRouteMap = self._compute_expected_hub_routes(
            hub_redirects, hubs
        )

        # dict[hub-id ->
        #   set[(net, mask)]
        # ]
        hub_routes: RouteSet = self._compute_hub_routes(hub_redirects, hubs)

        results = []

        for hub_id, expected_routes in expected_hub_routes.items():
            this_hubs_routes = hub_routes.get(hub_id, set())

            logging.info(f"Hub {hub_id} has {len(this_hubs_routes)} routes, expected {len(expected_routes)} routes")

            if dump_all_routes:
                routes_dump = {
                    hub_id: {
                        "expected": ["{}/{}".format(r[0], r[1]) for r in expected_routes.keys()],
                        "actual": ["{}/{}".format(r[0], r[1]) for r in this_hubs_routes],
                    } for hub_id, expected_routes in expected_hub_routes.items()
                }
                with open("routes_dump.json", "w") as f:
                    json.dump(routes_dump, f, indent=2)

            missing_routes = {
                route: list(edges)
                for route, edges in expected_routes.items()
                if route not in this_hubs_routes
            }

            for route, edges in missing_routes.items():
                results.append((hub_id, route[0], edges))

        return results


async def main(session: aiohttp.ClientSession):
    data = CommonData(
        read_env("VCO"), read_env("VCO_TOKEN"), int(read_env("ENT_ID")), session
    )

    enterprise_logical_id = await get_enterprise_logical_id(data)
    logging.info(f"Enterprise logical ID: {enterprise_logical_id}")

    all_hubs = await get_all_hubs(data)
    hubs = [h for h in all_hubs if "vp-igbn" in h.name.lower()]

    hub_name_map: dict[HubLogicalId, EdgeName] = {}
    for hub in hubs:
        logging.info(f"Hub: [{hub.logical_id}] {hub.name}")
        hub_name_map[hub.logical_id] = hub.name

    relevant_gateways: dict[HubLogicalId, set[GwLogicalId]] = (
        await get_relevant_gateways(data, hubs)
    )

    relevant_gateways_set: set[GwLogicalId] = set()
    for gateways in relevant_gateways.values():
        relevant_gateways_set.update(gateways)

    # list of de-duplicated gateways which are used by any hubs
    gateways = list(relevant_gateways_set)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    async with websockets.connect(
        f"wss://{data.vco}/ws/",
        extra_headers={
            "Authorization": f"Token {data.token}",
        },
        ssl=ctx,
    ) as ws:
        try:
            diag = RouteDiag(ws)

            # wait for remote diagnostics token
            try:
                msg = await asyncio.wait_for(ws.recv(), 5)
                if not diag.handle_message(msg):
                    logging.error("failed to get remote diagnostics token")
                    return

            except asyncio.TimeoutError:
                logging.error("failed to get remote diagnostics token")
                return

            # request route table dump of all hub edges
            for hub in hubs:
                diag.request_edge_routes(hub.logical_id)

            await diag.flush_requests()

            # request route table dump of all gateways
            for gw in gateways:
                diag.request_gateway_routes(0, gw, enterprise_logical_id, 40)

            await diag.flush_requests()

            # loop until all pending requests complete
            while diag.get_pending_count() > 0:
                try:
                    # if any requests timed out, re-send them
                    if diag.handle_request_timeouts() > 0:
                        await diag.flush_requests()

                    # process all responses
                    msg = await asyncio.wait_for(ws.recv(), 5)
                    diag.handle_message(msg)

                except asyncio.TimeoutError:
                    continue

            result = diag.compute_route_deltas(relevant_gateways, hubs)

            missing_count = len(result)
            if missing_count == 0:
                logging.info("No missing routes found")
            else:
                logging.info(f"Found {missing_count} missing routes")

            cur_time = int(time.time())
            csv_filename = "missing_routes_{}.csv".format(cur_time)

            logging.info(f"Writing results to {csv_filename}")

            result_dicts = [
                {
                    "hub_id": (
                        hub_id if hub_id not in hub_name_map else hub_name_map[hub_id]
                    ),
                    "route": route,
                    "peers": "[{}]".format(" ".join(peers)),
                }
                for hub_id, route, peers in result
            ]
            keys = ["hub_id", "route", "peers"]

            with open(csv_filename, "a") as f:
                cw = csv.DictWriter(f, keys)

                cw.writeheader()
                cw.writerows(result_dicts)

        except websockets.ConnectionClosed:
            logging.error("websocket connection closed")


async def main_wrapper():
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        await main(session)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        filename="route-check.log",
        filemode="a",
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logging.info("Starting route check")

    dotenv.load_dotenv("env/.env", verbose=True, override=True)
    asyncio.run(main_wrapper())
