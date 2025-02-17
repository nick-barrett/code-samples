import ijson
import json
import asyncio
import time
from aiohttp import ClientResponse, StreamReader
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Generator,
    Literal,
    NamedTuple,
    Optional,
    TypedDict,
    cast,
    List,
)
from datetime import datetime, timedelta

from .models import (
    EdgeFlowVisibilityNamedTuple,
    EdgeFlowVisibilityRecord,
    EdgeLinkMetrics,
    EdgeProvisionParams,
    EnterpriseEventV2,
    EnterpriseGatewayConfigResult,
    GetEnterpriseResult,
    VpnEdgeActionStatus,
    EnterpriseEdgeListEdge,
    LinkData,
    EnterpriseEvent,
    CommonData,
    EdgeLink,
)
from .patch import *


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
        # resp_text = await req.text()
        # resp = json.loads(resp_text)
        resp = await req.json()
        if "result" not in resp:
            raise ValueError(json.dumps(resp, indent=2))
        return resp["result"]


async def do_portal_noparse(c: CommonData, method: str, params: dict) -> ClientResponse:
    req = await c.session.post(
        f"https://{c.vco}/portal/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        },
    )

    return req


async def get_async(c: CommonData, async_token: str):
    return await do_portal(
        c,
        "async/getStatus",
        {
            "apiToken": async_token,
        },
    )


async def get_enterprise_edges_v1(c: CommonData) -> list[dict]:
    return await do_portal(
        c,
        "enterprise/getEnterpriseEdges",
        {
            "enterpriseId": c.enterprise_id,
            "with": [
                # "configuration",
                "site"
            ],
        },
    )


async def get_enterprise_edge_list(c: CommonData, with_params: list[str]) -> list[dict]:
    return await do_portal(
        c,
        "enterprise/getEnterpriseEdgeList",
        {"enterpriseId": c.enterprise_id, "with": with_params},
    )


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


async def get_enterprise_edge_list_full_dict(
    c: CommonData, with_params: list[str] | None, filters: dict | None
) -> AsyncGenerator[Dict[Any, Any], None]:
    next_page = None
    more = True

    while more:
        resp = await get_enterprise_edge_list_raw(c, with_params, filters, next_page)

        meta: Dict[str, Dict] = cast(Dict[str, Dict], resp.get("metaData", {}))
        more = meta.get("more", False)
        next_page = cast(str | None, meta.get("nextPageLink", None))

        data: List[Dict[str, Any]] = cast(List[Dict[str, Any]], resp.get("data", []))
        for d in data:
            yield d


async def get_enterprise(c: CommonData) -> GetEnterpriseResult:
    res = await do_portal(c, "enterprise/getEnterprise", {"id": c.enterprise_id})

    return GetEnterpriseResult.from_dict(res)


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
        payload["interval"]["start"] = start_time

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


async def get_configuration_modules(
    c: CommonData,
    configuration_id: int,
    modules: Optional[List[str]] = None,
    no_data=False,
    raw_data=False,
) -> List[Dict]:
    params: Dict[str, Any] = {
        "id": configuration_id,
    }

    if modules is not None:
        params["modules"] = modules

    if no_data:
        params["noData"] = True
    elif raw_data:
        params["rawData"] = True

    return await do_portal(c, "configuration/getConfigurationModules", params)


async def get_edge_configuration_modules(
    c: CommonData, edge_id: int, modules: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "edgeId": edge_id,
        "enterpriseId": c.enterprise_id,
    }

    if modules is not None:
        params["modules"] = modules

    return await do_portal(
        c,
        "edge/getConfigurationModules",
        params,
    )


async def get_edge_configuration_stack(
    shared: CommonData, edge_id: int
) -> list[dict[str, Any]]:
    return await do_portal(
        shared, "edge/getEdgeConfigurationStack", params={"edgeId": edge_id}
    )


async def edge_provision(shared: CommonData, params: EdgeProvisionParams):
    return await do_portal(
        shared,
        "edge/edgeProvision",
        {
            "analyticsMode": params.analytics_mode,
            "configurationId": str(params.configuration_id),
            "customInfo": params.custom_info,
            "description": params.description,
            "licenseId": params.license_id,
            "endpointPkiMode": params.endpoint_pki_mode,
            "enterpriseId": shared.enterprise_id,
            "haEnabled": params.ha_enabled,
            "modelNumber": params.model_number,
            "name": params.name,
            "serialNumber": params.serial_number,
            "site": {
                "contactEmail": params.contact_email,
                "contactName": params.contact_name,
                "shippingSameAsLocation": 1,
            },
        },
    )


async def get_edge(
    shared: CommonData, edge_id: int, with_params: list[str] | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {"edgeId": edge_id, "enterpriseId": shared.enterprise_id}

    if with_params is not None:
        params["with"] = with_params

    return await do_portal(
        shared,
        "edge/getEdge",
        params,
    )


async def get_enterprise_gateway_config(
    shared: CommonData,
) -> EnterpriseGatewayConfigResult:
    resp = await do_portal(
        shared,
        "monitoring/getEnterpriseGatewayRouteTableConfig",
        params={"enterpriseId": shared.enterprise_id},
    )

    return EnterpriseGatewayConfigResult.from_dict(resp)


async def get_enterprise_segments(shared: CommonData) -> list[dict[str, Any]]:
    return await do_portal(shared, "enterprise/getEnterpriseNetworkSegments", params={})


async def get_object_groups(c: CommonData) -> list[dict[str, Any]]:
    resp = await do_portal(
        c,
        "enterprise/getObjectGroups",
        {"enterpriseId": c.enterprise_id},
    )
    return resp


async def get_address_groups(c: CommonData) -> list[dict[str, Any]]:
    resp = await do_portal(
        c,
        "enterprise/getObjectGroups",
        {"enterpriseId": c.enterprise_id, "type": "address_group"},
    )
    return resp


async def insert_address_group(
    c: CommonData, name: str, description: str, grp: list[dict[str, Any]]
):
    await do_portal(
        c,
        "enterprise/insertObjectGroup",
        {
            "name": name,
            "description": description,
            "data": grp,
            "enterpriseId": c.enterprise_id,
            "type": "address_group",
        },
    )


async def get_port_groups(c: CommonData) -> list[dict[str, Any]]:
    resp = await do_portal(
        c,
        "enterprise/getObjectGroups",
        {"enterpriseId": c.enterprise_id, "type": "port_group"},
    )
    return resp


async def insert_port_group(
    c: CommonData, name: str, description: str, grp: list[dict[str, Any]]
):
    await do_portal(
        c,
        "enterprise/insertObjectGroup",
        {
            "name": name,
            "description": description,
            "data": grp,
            "enterpriseId": c.enterprise_id,
            "type": "port_group",
        },
    )


async def get_edge_gateway_assignment(c: CommonData, edge_id: int) -> dict:
    return await do_portal(
        c,
        "edge/getEdgeGatewayAssignments",
        {"enterpriseId": c.enterprise_id, "id": edge_id},
    )


async def get_network_gateway_associations(c: CommonData) -> list:
    return await do_portal(
        c,
        "network/getNetworkGateways",
        {"with": ["enterpriseAssociations", "site"]},
    )


async def set_edge_enterprise_configuration(
    c: CommonData, edge_id: int, profile_id: int
):
    await do_portal(
        c,
        "edge/setEdgeEnterpriseConfiguration",
        {
            "configurationId": profile_id,
            "enterpriseId": c.enterprise_id,
            "edgeId": edge_id,
            "skipEdgeRoutingUpdates": False,
        },
    )


async def get_enterprise_configuration_profile(c: CommonData, profile_id: int):
    return await do_portal(
        c,
        "configuration/getConfiguration",
        {"id": profile_id, "enterpriseId": c.enterprise_id, "with": ["modules"]},
    )


async def insert_configuration_module(
    c: CommonData,
    configuration_id: int,
    module_name: str,
    data: dict[str, Any],
    return_data: bool = False,
) -> int | dict[str, Any]:
    params = {
        "enterpriseId": c.enterprise_id,
        "configurationId": configuration_id,
        "name": module_name,
        "data": data,
    }

    if return_data:
        params["returnData"] = True

    rv = await do_portal(c, "configuration/insertConfigurationModule", params)

    if not return_data:
        return rv["id"]
    else:
        return rv


async def update_configuration_module(
    c: CommonData,
    configuration_module_id: int,
    new_data: dict,
    new_refs: Optional[dict] = None,
):
    update = {"data": new_data}
    if new_refs is not None:
        update["refs"] = new_refs

    await do_portal(
        c,
        "configuration/updateConfigurationModule",
        params={
            "id": configuration_module_id,
            "enterpriseId": c.enterprise_id,
            "_update": update,
        },
    )


async def insert_diagnostic_bundle(
    c: CommonData, enterprise_id: int, edge_id: int, reason: str = ""
):
    await do_portal(
        c,
        "diagnosticBundle/insertDiagnosticBundle",
        {
            "edgeId": edge_id,
            "enterpriseId": enterprise_id,
            "options": {"type": "diagnosticDump"},
            "reason": reason,
        },
    )


async def enable_cluster_for_edge_hub(
    c: CommonData,
    configuration_id: int,
    edge_hub_cluster_id: int,  # network service `id`
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "enterprise/enableClusterForEdgeHub",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "id": edge_hub_cluster_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def disable_cluster_for_edge_hub(
    c: CommonData,
    configuration_id: int,
    edge_hub_cluster_id: int,  # network service `id`
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "enterprise/disableClusterForEdgeHub",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "id": edge_hub_cluster_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def enable_edge_for_edge_hub(
    c: CommonData,
    configuration_id: int,
    edge_id: int,
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "edge/enableEdgeForEdgeHub",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "edgeId": edge_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def disable_edge_for_edge_hub(
    c: CommonData,
    configuration_id: int,
    edge_id: int,
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "edge/disableEdgeForEdgeHub",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "edgeId": edge_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def enable_cluster_for_backhaul(
    c: CommonData,
    configuration_id: int,
    edge_hub_cluster_id: int,  # network service `id`
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "enterprise/enableClusterForBackHaul",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "id": edge_hub_cluster_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def enable_edge_for_backhaul(
    c: CommonData,
    configuration_id: int,
    edge_id: int,
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "edge/enableEdgeForBackHaul",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "edgeId": edge_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def enable_cluster_for_edge_to_edge_bridge(
    c: CommonData,
    configuration_id: int,
    edge_hub_cluster_id: int,  # network service `id`
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "enterprise/enableClusterForEdgeToEdgeBridge",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "id": edge_hub_cluster_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def enable_edge_for_edge_to_edge_bridge(
    c: CommonData,
    configuration_id: int,
    edge_id: int,
    configuration_module_id: int,
    segment_object_id: int,
):
    await do_portal(
        c,
        "edge/enableEdgeForEdgeToEdgeBridge",
        params={
            "enterpriseId": c.enterprise_id,
            "configurationId": configuration_id,
            "moduleId": configuration_module_id,
            "edgeId": edge_id,
            "segmentObjectId": segment_object_id,
        },
    )


async def get_enterprise_services(
    c: CommonData, type: Optional[str] = None
) -> list[dict]:
    p = {
        "enterpriseId": c.enterprise_id,
        "object": "NETWORK_SERVICE",
    }
    if type is not None:
        p["type"] = type

    return await do_portal(
        c,
        "enterprise/getEnterpriseServices",
        p,
    )


async def decode_enterprise_key(c: CommonData, key: str) -> str:
    return await do_portal(
        c,
        "enterprise/decodeEnterpriseKey",
        params={"enterpriseId": c.enterprise_id, "key": key},
    )


async def update_enterprise_service(c: CommonData, id: int, update: dict[str, Any]):
    return await do_portal(
        c,
        "enterprise/updateEnterpriseService",
        params={
            "enterpriseId": c.enterprise_id,
            "id": id,
            "_update": update,
        },
    )
    pass


async def get_datacenters(c: CommonData) -> list[dict]:
    return await get_enterprise_services(c, "dataCenter")


async def get_edge_hubs(c: CommonData) -> list[dict]:
    return await get_enterprise_services(c, "edgeHub")


async def get_edge_hub_clusters(c: CommonData) -> list[dict]:
    return await get_enterprise_services(c, "edgeHubCluster")


async def get_aggregate_edge_link_metrics(
    c: CommonData,
    start_time: datetime,
    all_enterprises: bool = False,
    metrics: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    start_time_timestamp = int(start_time.timestamp() * 1000)

    params: Dict[str, Any] = {
        "interval": {
            "start": start_time_timestamp,
        },
    }

    if not all_enterprises:
        params["enterprises"] = [c.enterprise_id]

    if metrics is not None:
        params["metrics"] = metrics

    return await do_portal(c, "monitoring/getAggregateEdgeLinkMetrics", params)


async def get_edge_link_metrics(
    c: CommonData, edge_id: int, edge_name: str, start_time: int, end_time: int
) -> list[LinkData]:
    resp = await do_portal(
        c,
        "metrics/getEdgeLinkMetrics",
        params={
            # comment out the following line to get all available metrics
            "edgeId": edge_id,
            "enterpriseId": c.enterprise_id,
            "metrics": [
                "bestJitterMsRx",
                "bestJitterMsTx",
                "bestLatencyMsRx",
                "bestLatencyMsTx",
                "bestLossPctRx",
                "bestLossPctTx",
            ],
            "interval": {"start": start_time, "end": end_time},
        },
    )

    return [
        LinkData(
            l["link"]["edgeId"],
            edge_name,
            l["link"]["displayName"],
            l["bestLatencyMsRx"],
            l["bestLatencyMsTx"],
            l["bestLossPctRx"],
            l["bestLossPctTx"],
            l["bestJitterMsRx"],
            l["bestJitterMsTx"],
        )
        for l in resp
    ]


async def enable_analytics_for_edges(
    c: CommonData, edge_ids: list[int], self_healing: bool = False
):
    await do_portal(
        c,
        "edge/updateAnalyticsSettingsForEdges",
        {
            "configData": {
                "analyticsMode": "SDWAN_ANALYTICS",
                "analyticsSelfHealing": self_healing,
            },
            "edgeId": edge_ids,
            "enterpriseId": c.enterprise_id,
        },
    )


async def disable_analytics_for_edges(c: CommonData, edge_ids: list[int]):
    await do_portal(
        c,
        "edge/updateAnalyticsSettingsForEdges",
        {
            "configData": {
                "analyticsMode": "SDWAN_ONLY",
                "analyticsSelfHealing": False,
            },
            "edgeId": edge_ids,
            "enterpriseId": c.enterprise_id,
        },
    )


async def get_enterprise_events_raw(
    c: CommonData,
    start_time: datetime | None,
    id: int | None,
    next_page: str | None = None,
) -> dict[str, dict | list]:
    interval_object = {
        "start": int(start_time.timestamp()) * 1000 if start_time else 0,
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


async def get_enterprise_events_list_raw(
    c: CommonData,
    filters: dict,
    start: int,
    stop: int | None = None,
    next_page: str | None = None,
) -> dict[str, dict | list]:
    interval_object = {
        "start": start,
        "type": "custom",
    }
    if stop:
        interval_object["end"] = stop

    params_object = {
        "enterpriseId": c.enterprise_id,
        "filters": filters,
        "interval": interval_object,
        "sortBy": [{"attribute": "eventTime", "type": "ASC"}],
    }

    if next_page:
        params_object["nextPageLink"] = next_page

    return await do_portal(
        c,
        "event/getEnterpriseEventsList",
        params_object,
    )


async def get_enterprise_events_list(
    c: CommonData,
    filters: dict,
    start: int,
    stop: int | None = None,
    next_page: str | None = None,
) -> Generator[EnterpriseEvent, None, None]:
    resp = await get_enterprise_events_list_raw(c, filters, start, stop, next_page)

    events: list[dict[str, Any]] = cast(list[dict[str, Any]], resp.get("data", []))

    return (
        EnterpriseEvent(
            datetime.fromisoformat(e["eventTime"]),
            e.get("event", ""),
            e.get("message", ""),
            e.get("detail", ""),
            e.get("edgeId", None),
            e.get("edgeName", None),
        )
        for e in events
    )


async def get_enterprise_events_list_full(
    c: CommonData, filters: dict, start: int, stop: int | None = None
) -> AsyncGenerator[EnterpriseEvent, None]:
    next_page = None
    more = True

    while more:
        resp = await get_enterprise_events_list_raw(c, filters, start, stop, next_page)
        meta: dict[str, dict] = cast(dict[str, dict], resp.get("metaData", {}))
        more = meta.get("more", False)
        next_page = cast(str | None, meta.get("nextPageLink", None))

        data = resp.get("data", [])
        for d in data:
            yield EnterpriseEvent(
                datetime.fromisoformat(d.get("eventTime", datetime.now())),
                d.get("event", ""),
                d.get("message", ""),
                d.get("detail", ""),
                d.get("edgeId", None),
                d.get("edgeName", None),
            )


async def get_enterprise_events_stream(
    c: CommonData, start_time: datetime, poll_interval: timedelta
) -> AsyncGenerator[EnterpriseEventV2, None]:
    first_run = True
    next_id = 0
    interval_seconds = poll_interval.total_seconds()

    while True:
        next_page = None
        more = True

        while more:
            resp = await get_enterprise_events_raw(
                c, start_time if first_run else None, next_id, next_page
            )
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

            if more:
                # be nice and wait half a second
                await asyncio.sleep(0.5)

        first_run = False
        await asyncio.sleep(interval_seconds)


type FlowStatsField = Literal[
    "endTime",
    "application",
    "category",
    "linkId",
    "linkLogicalId",
    "edgeLogicalId",
    "destLogicalId",
    "segmentId",
    "destFQDN",
    "destDomain",
    "sourceIp",
    "destIp",
    "destPort",
    "flowPath",
    "gatewayIp",
    "transport",
]

type FlowStatsBasicMetric = Literal[
    "packetsRx",
    "packetsTx",
    "totalPackets",
    "bytesRx",
    "bytesTx",
    "totalBytes",
    "flowCount",
]

FlowPathNames = [
    "FLOW_PATH_E2C_VIA_VCG",
    "FLOW_PATH_E2C_DIRECT",
    "FLOW_PATH_E2E_VIA_VCG",
    "FLOW_PATH_E2E_VIA_HUB",
    "FLOW_PATH_E2E_DIRECT",
    "FLOW_PATH_E2DC_DIRECT",
    "FLOW_PATH_E2DC_VIA_VCG",
    "FLOW_PATH_E2BH",  # backhaul
    "FLOW_PATH_E2PROXY",
    "FLOW_PATH_OPG",  # partner gateway
    "FLOW_PATH_ROUTED",
    "FLOW_PATH_E2C_VIA_CSS",
]

FlowPathIndices = {name: idx for idx, name in enumerate(FlowPathNames)}

type FilterOp = Literal[
    "=",
    "!=",
    "startsWith",
    "notStartsWith",
    "contains",
    "notContains",
    ">=",
    "<=",
]


class FlowStatsFilter(TypedDict):
    field: FlowStatsField
    op: FilterOp
    value: str


async def get_enterprise_flow_metrics(
    c: CommonData,
    view_by: FlowStatsField,
    start_time: int,
    end_time: int,
    limit: int | None = None,
    sort: FlowStatsBasicMetric | None = None,
    filter: list[FlowStatsFilter] | None = None,
) -> dict:
    param_obj = {
        "enterpriseId": c.enterprise_id,
        "interval": {"start": start_time, "end": end_time},
        "viewBy": view_by,
        "metrics": [
            "packetsRx",
            "packetsTx",
            "bytesRx",
            "bytesTx",
        ]
    }

    if limit is not None:
        param_obj["limit"] = limit

    if sort is not None:
        param_obj["sort"] = sort

    if filter is not None and len(filter) > 0:
        param_obj["filters"] = filter

    return await do_portal(
        c,
        "metrics/getEnterpriseFlowMetrics",
        param_obj,
    )


async def get_routable_applications(c: CommonData, edge_id: int | None = None) -> dict[int, str]:
    params_obj = {"enterpriseId": c.enterprise_id}

    if edge_id is not None:
        params_obj["edgeId"] = edge_id

    resp = await do_portal(c, "configuration/getRoutableApplications", params_obj)

    app_id_to_name: dict[int, str] = {}

    for app in resp["applications"]:
        app_id_to_name[app["id"]] = app["displayName"]

    return app_id_to_name


async def get_edge_flow_visibility_metrics_raw_fast(
    c: CommonData,
    edge_id: int,
    limit: int,
    start: int,
    stop: int,
    next_page: str | None = None,
) -> ClientResponse:
    interval_object = {
        "start": start,
        "end": stop,
    }
    if stop:
        interval_object["end"] = stop

    filters = {
        "and": [{"field": "sourceIp", "operator": "notContains", "value": "0.0.0.0"}]
    }

    params_object = {
        "enterpriseId": c.enterprise_id,
        "edgeId": edge_id,
        "filters": filters,
        "interval": interval_object,
        # "sortBy": [{"attribute": "sourceIp", "type": "ASC"}],
        "limit": limit,
        "_filterSpec": True,
    }

    if next_page:
        params_object["nextPageLink"] = next_page

    return await do_portal_noparse(
        c,
        "metrics/getEdgeFlowVisibilityMetrics",
        params_object,
    )


async def get_edge_flow_visibility_metrics_raw(
    c: CommonData,
    edge_id: int,
    limit: int,
    start: int,
    stop: int,
    next_page: str | None = None,
) -> dict[str, dict | list]:
    interval_object = {
        "start": start,
        "end": stop,
    }
    if stop:
        interval_object["end"] = stop

    filters = {
        "and": [{"field": "sourceIp", "operator": "notContains", "value": "0.0.0.0"}]
    }

    params_object = {
        "enterpriseId": c.enterprise_id,
        "edgeId": edge_id,
        "filters": filters,
        "interval": interval_object,
        "sortBy": [{"attribute": "sourceIp", "type": "ASC"}],
        "limit": limit,
        "_filterSpec": True,
    }

    if next_page:
        params_object["nextPageLink"] = next_page

    return await do_portal(
        c,
        "metrics/getEdgeFlowVisibilityMetrics",
        params_object,
    )


async def get_edge_flow_visibility_metrics_fast(
    c: CommonData, edge_id: int, start_time: datetime, end_time: datetime
) -> AsyncGenerator[tuple[tuple, list[tuple]], None]:
    next_page = None
    more = True

    batch_size = 60000
    start_time_timestamp = int(1000 * start_time.timestamp())
    end_time_timestamp = int(1000 * end_time.timestamp())

    value_events = frozenset(["number", "string", "boolean"])

    have_learned_fields = False
    flow_fields: tuple | None = None
    flow_field_indices: dict[str, int] = {}

    while more:
        more = False

        client_response = await get_edge_flow_visibility_metrics_raw_fast(
            c, edge_id, batch_size, start_time_timestamp, end_time_timestamp, next_page
        )

        next_page = None

        try:
            in_flow_record = False
            flow_record_keys = []
            flow_record_values = []
            need_sort = False

            flow_record_batch = []

            async for prefix, event, value in ijson.parse(client_response.content):
                if in_flow_record:
                    if event == "map_key":
                        flow_record_keys.append(value)
                    elif event in value_events:
                        flow_record_values.append(value)
                    elif prefix == "result.data.item.metrics" and event == "end_map":
                        # the last record in flow metrics is bogus, skip it
                        flow_record_keys = []
                        flow_record_values = []
                        in_flow_record = False

                    elif event == "end_map":
                        if have_learned_fields:
                            for i, v in enumerate(flow_record_keys):
                                if flow_fields[i] != v:
                                    need_sort = True
                                    break

                            if need_sort:
                                flow_record_sortable = zip(
                                    (flow_field_indices[k] for k in flow_record_keys),
                                    flow_record_values,
                                )
                                flow_record_sorted = [
                                    v[1]
                                    for v in sorted(
                                        flow_record_sortable, key=lambda x: x[0]
                                    )
                                ]

                                flow_record_keys = flow_fields
                                flow_record_values = flow_record_sorted

                                need_sort = False

                        else:
                            flow_fields = tuple(flow_record_keys)
                            flow_field_indices = {
                                key: idx for idx, key in enumerate(flow_fields)
                            }
                            have_learned_fields = True

                        flow_record_batch.append(tuple(flow_record_values))

                        flow_record_keys = []
                        flow_record_values = []

                        in_flow_record = False

                elif event == "start_map" and prefix == "result.data.item":
                    in_flow_record = True
                elif prefix == "result.metaData.more":
                    more = value
                elif prefix == "result.metaData.nextPageLink":
                    next_page = value
                elif prefix.startswith("error"):
                    break

            yield flow_fields, flow_record_batch
        finally:
            client_response.close()


async def get_edge_flow_visibility_metrics(
    c: CommonData, edge_id: int, start_time: datetime, end_time: datetime
) -> AsyncGenerator[EdgeFlowVisibilityRecord, None]:
    next_page = None
    more = True

    start_time_timestamp = int(1000 * start_time.timestamp())
    end_time_timestamp = int(1000 * end_time.timestamp())

    while more:
        resp = await get_edge_flow_visibility_metrics_raw(
            c, edge_id, 60000, start_time_timestamp, end_time_timestamp, next_page
        )
        meta: dict[str, dict] = cast(dict[str, dict], resp.get("metaData", {}))
        more = meta.get("more", False)
        next_page = cast(str | None, meta.get("nextPageLink", None))

        data = cast(list[dict[str, int | str]], resp.get("data", []))

        print("got {} flow records".format(len(data)))

        for d in data:
            flow_start_time = d.get("startTime", None)
            flow_end_time = d.get("endTime", None)
            if isinstance(flow_start_time, str) and isinstance(flow_end_time, str):
                yield EdgeFlowVisibilityRecord(
                    datetime.fromisoformat(flow_start_time),
                    datetime.fromisoformat(flow_end_time),
                    d.get("application", -1),  # type: ignore
                    d.get("category", -1),  # type: ignore
                    d.get("bytesRx", 0),  # type: ignore
                    d.get("bytesTx", 0),  # type: ignore
                    d.get("flowCount", 0),  # type: ignore
                    d.get("businessRuleName", ""),  # type: ignore
                    d.get("firewallRuleName", ""),  # type: ignore
                    d.get("segmentId", 0),  # type: ignore
                    d.get("hostName", ""),  # type: ignore
                    d.get("sourceIp", ""),  # type: ignore
                    d.get("destIp", ""),  # type: ignore
                    d.get("destPort", -1),  # type: ignore
                    d.get("transport", -1),  # type: ignore
                    d.get("destDomain", ""),  # type: ignore
                    d.get("destFQDN", ""),  # type: ignore
                    d.get("isp", ""),  # type: ignore
                    d.get("linkId", -1),  # type: ignore
                    d.get("linkName", ""),  # type: ignore
                    d.get("nextHop", ""),  # type: ignore
                    d.get("route", ""),  # type: ignore
                    d.get("packetsRx", 0),  # type: ignore
                    d.get("packetsTx", 0),  # type: ignore
                    d.get("totalBytes", 0),  # type: ignore
                    d.get("totalPackets", 0),  # type: ignore
                )  # type: ignore


async def get_vpn_edge_action_status_raw(
    c: CommonData,
    provider_object_id: int,
    filters: dict,
    start: int,
    stop: int | None = None,
    next_page: str | None = None,
) -> dict[str, dict | list]:
    raise NotImplementedError

    interval_object = {
        "start": start,
        "type": "custom",
    }
    if stop:
        interval_object["end"] = stop

    params_object = {
        "enterpriseId": c.enterprise_id,
        "providerObjectId": provider_object_id,
        "filters": filters,
        "interval": interval_object,
        "sortBy": [{"attribute": "eventTime", "type": "ASC"}],
    }

    if next_page:
        params_object["nextPageLink"] = next_page

    return await do_portal(
        c,
        "monitoring/getVPNEdgeActionStatus",
        params_object,
    )


async def get_vpn_edge_action_status_full(
    c: CommonData,
    provider_object_id: int,
    filters: dict,
    start: int,
    stop: int | None = None,
) -> AsyncGenerator[VpnEdgeActionStatus, None]:
    next_page = None
    more = True

    while more:
        resp = await get_vpn_edge_action_status_raw(
            c, provider_object_id, filters, start, stop, next_page
        )
        meta: dict[str, dict] = cast(dict[str, dict], resp.get("metaData", {}))
        more = meta.get("more", False)
        next_page = cast(str | None, meta.get("nextPageLink", None))

        data = resp.get("data", [])
        for d in data:
            yield VpnEdgeActionStatus(d.get("id", 0))


"""
APIv2 TODO:
- Implement status checking inside all async-handled API calls (PUT/PATCH)
- Wrap validation error results in a type
- Implement enumeration methods (get edges, get profiles) with pagination

- How to make working with device settings easier?
    - Helper methods for common operations?
    - Create a type? This is hard because of lack of validation.

- Implement GET/PUT -echo to find validation problems in edge & profiles

"""


async def _async_v2_wait(c: CommonData, response: ClientResponse) -> dict[Any, Any]:
    if response.status != 200 and response.status != 202:
        body = await response.json()
        raise Exception("validation error: {}".format(json.dumps(body, indent=2)))

    location = response.headers["location"]
    for _ in range(10):
        async with c.session.get(
            f"https://{c.vco}{location}",
        ) as async_resp:
            async_body: dict[str, Any] = await async_resp.json()
            status = async_body.get("status", None)

            if status == "DONE":
                # TODO: extract config body
                return async_body
            elif status == "ACCEPTED":
                await asyncio.sleep(1)
            elif status == "ERROR":
                print(
                    "error in async API:\n{}".format(json.dumps(async_body, indent=2))
                )
                break
            else:
                print("unknown status: {}".format(status))
                break

    raise Exception("failed to apply config")


async def get_edge_device_settings(
    c: CommonData, enterprise_logical_id: str, edge_logical_id: str
) -> dict:
    async with c.session.get(
        f"https://{c.vco}/api/sdwan/v2/enterprises/{enterprise_logical_id}/edges/{edge_logical_id}/deviceSettings",
    ) as req:
        return await req.json()


async def patch_edge_device_settings(
    c: CommonData,
    enterprise_logical_id: str,
    edge_logical_id: str,
    patch_set: PatchSet,
):
    async with c.session.patch(
        f"https://{c.vco}/api/sdwan/v2/enterprises/{enterprise_logical_id}/edges/{edge_logical_id}/deviceSettings",
        json=serialize_patch_set(patch_set),
    ) as req:
        resp = await req.json()
        return resp["operationId"]


async def put_edge_device_settings(
    c: CommonData,
    enterprise_logical_id: str,
    edge_logical_id: str,
    patch_set: PatchSet,
):
    async with c.session.put(
        f"https://{c.vco}/api/sdwan/v2/enterprises/{enterprise_logical_id}/edges/{edge_logical_id}/deviceSettings",
        json=serialize_patch_set(patch_set),
    ) as req:
        resp = await req.json()
        return resp["operationId"]


async def get_profile_device_settings(
    c: CommonData, enterprise: str, profile: str
) -> dict[Any, Any]:
    async with c.session.get(
        f"https://{c.vco}/api/sdwan/v2/enterprises/{enterprise}/profiles/{profile}/deviceSettings"
    ) as req:
        return await req.json()


async def put_profile_device_settings(
    c: CommonData, enterprise: str, profile: str, settings: dict[Any, Any]
) -> dict[Any, Any]:
    async with c.session.put(
        f"https://{c.vco}/api/sdwan/v2/enterprises/{enterprise}/profiles/{profile}/deviceSettings",
        json=settings,
    ) as resp:
        if resp.status != 200 and resp.status != 202:
            body = await resp.json()
            raise Exception("validation error: {}".format(json.dumps(body, indent=2)))

        location = resp.headers["location"]
        for _ in range(10):
            await asyncio.sleep(1)

            async with c.session.get(
                f"https://{c.vco}{location}",
            ) as resp_async:
                resp_async = await resp_async.json()
                status = resp_async["status"]

                if status == "DONE":
                    # TODO: extract config body
                    return resp_async
                elif status == "ACCEPTED":
                    continue
                else:
                    print("error:\n{}".format(json.dumps(resp_async, indent=2)))

        raise Exception("failed to apply config")
