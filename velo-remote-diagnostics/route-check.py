import dataclasses
import datetime
import time
import logging
import csv
import json
import asyncio

import dotenv
import aiohttp
import websockets

from veloapi.api import (
    get_enterprise,
    get_enterprise_edge_list_full,
)
from veloapi.models import (
    CommonData,
    EnterpriseEdgeListEdge,
    GatewayRouteEntry,
)
from veloapi.routes import RouteDiag, get_relevant_gateways_for_edge
from veloapi.util import read_env

# maximum number of times to try getting routes from edge/gateway
max_tries = 5
# set to True to include a full route-dump for the hubs
dump_all_routes = True


class DataclassEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


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
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    cache_hubs = cache.get(ent_id_str, {}).get("hubs", [])

    if len(cache_hubs) > 0:
        return cache_hubs
    else:
        hubs = []
        async for edge in get_enterprise_edge_list_full(c, ["ha"], None):
            if edge.is_hub:
                hubs.append(edge)

        cache.setdefault(ent_id_str, {})["hubs"] = hubs

        with open("route-check-cache.json", "w") as f:
            json.dump(cache, f, cls=DataclassEncoder)

        return hubs

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


class CustomRouteDiag(RouteDiag):
    def __init__(self):
        self.gateway_hubs: dict[GwLogicalId, set[HubLogicalId]] = {}
        super().__init__()

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

            logging.info(
                f"Hub {hub_id} has {len(this_hubs_routes)} routes, expected {len(expected_routes)} routes"
            )

            if dump_all_routes:
                routes_dump = {
                    hub_id: {
                        "expected": [
                            "{}/{}".format(r[0], r[1]) for r in expected_routes.keys()
                        ],
                        "actual": [
                            "{}/{}".format(r[0], r[1]) for r in this_hubs_routes
                        ],
                    }
                    for hub_id, expected_routes in expected_hub_routes.items()
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

    hubs = await get_all_hubs(data)

    hub_name_map: dict[HubLogicalId, EdgeName] = {}
    for hub in hubs:
        logging.info(f"Hub: [{hub.logical_id}] {hub.name}")
        hub_name_map[hub.logical_id] = hub.name

    relevant_gateways: dict[HubLogicalId, set[GwLogicalId]] = (
        await get_relevant_gateways_for_edge(data, hubs)
    )

    relevant_gateways_set: set[GwLogicalId] = set()
    for gateways in relevant_gateways.values():
        relevant_gateways_set.update(gateways)

    # list of de-duplicated gateways which are used by any hubs
    gateways = list(relevant_gateways_set)

    async with websockets.connect(
        f"wss://{data.vco}/ws/",
        extra_headers={
            "Authorization": f"Token {data.token}",
        },
    ) as ws:
        try:
            diag = CustomRouteDiag(ws)

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
    async with aiohttp.ClientSession() as session:
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
