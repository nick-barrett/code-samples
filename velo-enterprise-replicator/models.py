from typing import Any
from uuid import UUID
from pydantic import BaseModel

from veloapi.models import ConfigProfile


class SourceEdgeData(BaseModel):
    name: str
    id: int
    destination_id: int | None
    logical_id: UUID
    destination_logical_id: UUID | None
    data: dict[str, Any]
    configuration: ConfigProfile
    profile_id: int

class SourceProfileData(BaseModel):
    name: str
    id: int
    destination_id: int | None
    logical_id: UUID
    destination_logical_id: UUID | None
    data: dict[str, Any]
    configuration: ConfigProfile
    destination_configuration_id: int | None


class SourceNetworkServiceData(BaseModel):
    name: str
    id: int
    destination_id: int | None
    logical_id: UUID
    destination_logical_id: UUID | None
    data: dict[str, Any]


class SourceVCOData(BaseModel):
    edges: list[SourceEdgeData]
    profiles: list[SourceProfileData]
    network_services: list[SourceNetworkServiceData]
    object_groups: list[dict]
    segments: list[dict]
    edge_hubs: list[dict]
