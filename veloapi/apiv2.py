from typing import Any, Callable
from veloapi.models import CommonData
from .pydantic import (
    EdgeConfigurationStack,
    Enterprise,
    Edge,
    EnterpriseConfigurationPolicy,
    JsonRpcRequest,
    JsonRpcSuccess,
    JsonRpcError,
    JsonRpcResponse,
)


async def _call_portal_raw(c: CommonData, request: JsonRpcRequest) -> JsonRpcResponse:
    async with c.session.post(
        f"https://{c.vco}/portal/",
        json=request.model_dump(),
    ) as req:
        resp = await req.text()
        return JsonRpcResponse.model_validate_json(resp)


async def _call_portal[T](
    c: CommonData, method: str, params: dict | None, validate: Callable[[Any], T]
) -> T:
    if params is not None:
        req = JsonRpcRequest(
            method=method,
            params=params,
        )
    else:
        req = JsonRpcRequest(
            method=method,
        )

    msg = await _call_portal_raw(c, req)

    match msg.root:
        case JsonRpcSuccess(result=result):
            return validate(result)
        case JsonRpcError(error=error):
            raise Exception(f"RPC error: {error}")
        case _:
            raise Exception(f"Unknown response type: {msg.__class__.__name__}")


async def _call_portal_single[T](
    c: CommonData, method: str, params: dict | None, validate: Callable[[Any], T]
) -> T:
    result = await _call_portal(c, method, params, validate)
    if isinstance(result, list):
        raise Exception(f"Expected single result, got list of {len(result)}")
    return result


async def _call_portal_list[T](
    c: CommonData, method: str, params: dict | None, validate: Callable[[Any], T]
) -> list[T]:
    return await _call_portal(c, method, params, lambda x: [validate(i) for i in x])


async def get_enterprise(c: CommonData) -> Enterprise:
    return await _call_portal_single(
        c,
        method="enterprise/getEnterprise",
        params={"enterpriseId": c.enterprise_id},
        validate=Enterprise.model_validate,
    )


async def get_enterprise_edges(c: CommonData) -> list[Edge]:
    return await _call_portal_list(
        c,
        method="enterprise/getEnterpriseEdges",
        params={"enterpriseId": c.enterprise_id},
        validate=Edge.model_validate,
    )


async def get_enterprise_configurations_policies(
    c: CommonData,
) -> list[EnterpriseConfigurationPolicy]:
    return await _call_portal_list(
        c,
        method="enterprise/getEnterpriseConfigurationsPolicies",
        params={"enterpriseId": c.enterprise_id},
        validate=EnterpriseConfigurationPolicy.model_validate,
    )


async def get_edge_configuration_stack(
    c: CommonData, edge_id: int
) -> EdgeConfigurationStack:
    return await _call_portal_single(
        c,
        method="edge/getEdgeConfigurationStack",
        params={
            "edgeId": edge_id,
            "enterpriseId": c.enterprise_id,
            "with": ["modules"],
        },
        validate=EdgeConfigurationStack.model_validate,
    )
