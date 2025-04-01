import datetime
from enum import Enum
import uuid
from typing import Annotated, List, Literal, Optional, TypedDict, Union

from sqlmodel import Relationship, SQLModel, Field
from pydantic import BaseModel, UrlConstraints
from pydantic_core import Url
import sqlmodel

# Common types


class TransportType(str, Enum):
    TCP = "tcp"
    UDP = "udp"


ServerNodeServiceUrl = Annotated[
    Url,
    UrlConstraints(
        allowed_schemes=["tcp", "udp"], host_required=True, default_port=11000
    ),
]


# User API models


class ServerService(BaseModel):
    id: uuid.UUID = Field(primary_key=True)
    url: str


class ServerNodeBase(SQLModel):
    id: uuid.UUID = Field(primary_key=True)
    name: str


class ServerNode(ServerNodeBase, table=True):
    last_contact: Optional[datetime.datetime] = Field(
        default=None,
        sa_column_kwargs={
            "server_default": sqlmodel.text("CURRENT_TIMESTAMP"),
            "onupdate": sqlmodel.func.now(),
        },
    )


class ServerNodeCreate(ServerNodeBase):
    services: List[ServerService]


class ClientNodeBase(SQLModel):
    id: uuid.UUID = Field(primary_key=True)
    name: str


class ClientNode(ClientNodeBase, table=True):
    last_contact: Optional[datetime.datetime] = Field(
        default=None,
        sa_column_kwargs={
            "server_default": sqlmodel.text("CURRENT_TIMESTAMP"),
            "onupdate": sqlmodel.func.now(),
        },
    )


class ClientNodeCreate(ClientNodeBase):
    pass


class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    headquarters: str


class Hero(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    secret_name: str
    age: int | None = Field(default=None, index=True)

    team_id: int | None = Field(default=None, foreign_key="team.id")

class WanDirection(str, Enum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


class WanMetric(str, Enum):
    RATE = "rate"
    LOSS = "loss"
    LATENCY = "latency"
    JITTER = "jitter"


class WanSettingBase(SQLModel):
    direction: WanDirection
    metric: WanMetric
    value: Annotated[float, Field(ge=0)]

class WanSetting(WanSettingBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: Optional[datetime.datetime] = Field(default_factory=sqlmodel.func.now)


class WanSettingCreate(WanSettingBase):
    pass


class WanNodeBase(SQLModel):
    name: str


class WanNode(WanNodeBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    last_contact: Optional[datetime.datetime] = Field(
        default=None,
        sa_column_kwargs={
            "server_default": sqlmodel.text("CURRENT_TIMESTAMP"),
            "onupdate": sqlmodel.func.now,
        },
    )


class WanNodeCreate(WanNodeBase):
    pass


class TrafficSessionBase(SQLModel):
    client_id: uuid.UUID
    service_id: uuid.UUID


class TrafficSession(TrafficSessionBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    stopped: bool = Field(default=False)
    created_at: Optional[datetime.datetime] = Field(
        default=None,
        sa_column_kwargs={"server_default": sqlmodel.text("CURRENT_TIMESTAMP")},
    )
    finish_time: datetime.datetime


class TrafficSessionCreate(TrafficSessionBase):
    duration: datetime.timedelta


class SessionMetricPoint(SQLModel, table=True):
    session_id: uuid.UUID = Field(foreign_key="trafficsession.id", primary_key=True)
    timestamp: datetime.datetime = Field(primary_key=True)
    metric: WanMetric = Field(primary_key=True)
    value: Annotated[float, Field(ge=0)]

"""
Backend WS message models
- Node registration (client, server, WAN)
- Session lifecycle management
    - Create
    - Metrics (TCP/UDP metrics)
    - Destroy
- Sending WAN configuration to WAN nodes

These messages are all targeted so client/server IDs are not provided.
"""


class BackendRegisterClientNode(ClientNodeCreate):
    msg_type: Literal["register_client"] = Field(default="register_client")


class BackendRegisterServerNode(ServerNodeCreate):
    msg_type: Literal["register_server"] = Field(default="register_server")


class BackendRegisterWanNode(WanNodeCreate):
    msg_type: Literal["register_wan"] = Field(default="register_wan")


class BackendSessionCreate(BaseModel):
    msg_type: Literal["session_create"] = Field(default="session_create")
    session_id: uuid.UUID
    target_service: ServerNodeServiceUrl 
    duration: datetime.timedelta


class BackendSessionDestroy(BaseModel):
    msg_type: Literal["session_destroy"] = Field(default="session_destroy")
    session_id: uuid.UUID


class BackendSessionEnded(BaseModel):
    msg_type: Literal["session_ended"] = Field(default="session_ended")
    session_id: uuid.UUID


class TcpMetricPoint(BaseModel):
    timestamp: datetime.datetime
    rate: float


class UdpMetricPoint(BaseModel):
    timestamp: datetime.datetime
    loss: float
    latency: float


class SessionMetricUdp(BaseModel):
    transport: Literal["udp"] = Field(default="udp")
    pt: UdpMetricPoint


class SessionMetricTcp(BaseModel):
    transport: Literal["tcp"] = Field(default="tcp")
    pt: TcpMetricPoint


class BackendSessionMetric(BaseModel):
    msg_type: Literal["session_metric"] = Field(default="session_metric")
    session_id: uuid.UUID
    data: Union[SessionMetricUdp, SessionMetricTcp] = Field(discriminator="transport")


class BackendControlMessage(BaseModel):
    data: Union[
        BackendRegisterClientNode,
        BackendRegisterServerNode,
        BackendRegisterWanNode,
        BackendSessionCreate,
        BackendSessionMetric,
        BackendSessionDestroy,
        BackendSessionEnded,
    ] = Field(discriminator="msg_type")


"""
User WS message models
- Session lifecycle management
    - Creation events
    - Metrics stream (TCP/UDP metrics)
    - Destruction events
"""


class SessionAddEvent(BaseModel):
    msg_type: Literal["session_add"] = Field(default="session_add")
    session: TrafficSession


class SessionEndedEvent(BaseModel):
    msg_type: Literal["session_destroy"] = Field(default="session_destroy")
    session_id: uuid.UUID


class SessionMetricSubscribeRequest(BaseModel):
    msg_type: Literal["session_metric_subscribe"] = Field(
        default="session_metric_subscribe"
    )
    session_id: uuid.UUID


class SessionMetricUnsubscribeRequest(BaseModel):
    msg_type: Literal["session_metric_unsubscribe"] = Field(
        default="session_metric_unsubscribe"
    )
    session_id: uuid.UUID


class SessionMetricEvent(BackendSessionMetric):
    pass


class FrontendMessage(BaseModel):
    msg: Union[
        SessionAddEvent,
        SessionEndedEvent,
        SessionMetricSubscribeRequest,
        SessionMetricUnsubscribeRequest,
        SessionMetricEvent,
    ] = Field(discriminator="msg_type")
