import asyncio
from collections import defaultdict
import functools
from contextlib import asynccontextmanager
import datetime
from typing import Any, AsyncGenerator, NewType
import uuid
from fastapi import FastAPI, WebSocket
from sqlmodel import Session

from .models import (
    BackendControlMessage,
    ClientNode,
    FrontendMessage,
    BackendRegisterClientNode,
    BackendRegisterServerNode,
    BackendRegisterWanNode,
    BackendSessionEnded,
    BackendSessionMetric,
    ServerNode,
    SessionEndedEvent,
    SessionMetricPoint,
    SessionMetricSubscribeRequest,
    SessionMetricUnsubscribeRequest,
    WanMetric,
    WanNode,
)

from .db import sqlite_engine, db_create_all

UserConnection = NewType("UserConnection", WebSocket)

BackendConnection = NewType("BackendConnection", WebSocket)
ClientConnection = NewType("ClientConnection", BackendConnection)
ServerConnection = NewType("ServerConnection", BackendConnection)
WanConnection = NewType("WanConnection", BackendConnection)

NodeId = NewType("NodeId", uuid.UUID)
ClientId = NewType("ClientId", NodeId)
ServerId = NewType("ServerId", NodeId)
WanId = NewType("WanId", NodeId)

SessionId = NewType("SessionId", uuid.UUID)


class WsManager:
    def __init__(self):
        self.users: set[UserConnection] = set()
        self.backend_connection_times: dict[BackendConnection, datetime.datetime] = {}

        self.connection_backend: dict[BackendConnection, NodeId] = {}
        self.connection_client: dict[ClientConnection, ClientId] = {}
        self.connection_server: dict[ServerConnection, ServerId] = {}
        self.connection_wan: dict[WanConnection, WanId] = {}

        self.client_connection: dict[ClientId, ClientConnection] = {}
        self.server_connection: dict[ServerId, ServerConnection] = {}
        self.wan_connection: dict[WanId, WanConnection] = {}

        self.user_sessions: defaultdict[UserConnection, set[SessionId]] = defaultdict(
            set
        )
        self.session_users: defaultdict[SessionId, set[UserConnection]] = defaultdict(
            set
        )

        self.session_client: dict[SessionId, ClientConnection] = {}
        self.client_sessions: dict[ClientId, set[SessionId]] = defaultdict(set)

        self.metric_cache: defaultdict[SessionId, list[BackendSessionMetric]] = (
            defaultdict(list)
        )

    async def connect_frontend(self, ws: WebSocket):
        await ws.accept()
        self.users.add(UserConnection(ws))

    async def connect_backend(self, ws: WebSocket):
        await ws.accept()
        self.backend_connection_times[BackendConnection(ws)] = datetime.datetime.now()

    def disconnect_frontend(self, ws: WebSocket):
        user = UserConnection(ws)

        self.users.discard(user)

        sessions = self.user_sessions.pop(user, set())

        for session in sessions:
            self.session_users[session].discard(user)

    async def disconnect_backend(self, ws: WebSocket):
        if (_ := self.connection_backend.get(BackendConnection(ws), None)) is not None:
            self.connection_backend.pop(BackendConnection(ws), None)
            self.backend_connection_times.pop(BackendConnection(ws), None)

        elif (
            client_id := self.connection_client.pop(ClientConnection(ws), None)
        ) is not None:
            sessions = self.client_sessions[client_id]

            async def on_session_ended_timeout(session_id: SessionId, timeout: int):
                try:
                    async with asyncio.timeout(timeout):
                        await self.on_session_ended(session_id)
                except asyncio.TimeoutError:
                    pass

            session_ended_tasks = [
                on_session_ended_timeout(session_id, 1) for session_id in sessions
            ]
            await asyncio.gather(*session_ended_tasks)

            self.client_sessions.pop(client_id, None)
            self.client_connection.pop(client_id, None)

        elif (
            server_id := self.connection_server.pop(ServerConnection(ws), None)
        ) is not None:
            self.server_connection.pop(server_id, None)

        elif (wan_id := self.connection_wan.pop(WanConnection(ws), None)) is not None:
            self.wan_connection.pop(wan_id, None)

        else:
            pass

    async def send_user_json_timeout(
        self, user: UserConnection, msg: Any, timeout: int = 1
    ):
        try:
            async with asyncio.timeout(timeout):
                await user.send_json(msg)
                return None
        except asyncio.TimeoutError:
            return user

    async def send_user_text_timeout(
        self, user: UserConnection, msg: str, timeout: int = 1
    ):
        try:
            async with asyncio.timeout(timeout):
                await user.send_text(msg)
                return None
        except asyncio.TimeoutError:
            return user

    async def on_session_ended(self, session_id: SessionId):
        users = self.session_users[session_id]

        if len(users) > 0:
            msg = FrontendMessage(
                msg=SessionEndedEvent(session_id=session_id)
            ).model_dump_json()

            send_tasks = [self.send_user_text_timeout(user, msg, 1) for user in users]
            user_timeouts = await asyncio.gather(*send_tasks)
            for user in user_timeouts:
                if user is not None:
                    # TODO: log? disconnect the user?
                    pass

        # clear session -> users mapping
        self.session_users.pop(session_id, None)

        # clear session -> client mapping
        self.session_client.pop(session_id, None)

        # TODO: metric_cache[session_id]
        # flush? clear? TBD

    def promote_backend_connection(
        self,
        connection: BackendConnection,
        promoted_type: ClientConnection | ServerConnection | WanConnection,
    ):
        # TODO: if encountered, should remove the WS connection everywhere
        if (node_id := self.connection_backend.pop(connection, None)) is None:
            raise ValueError("Backend connection ID not found")

        if (_ := self.backend_connection_times.pop(connection, None)) is None:
            raise ValueError("Backend connection time not found")

        if promoted_type == ClientConnection:
            node_id = ClientId(node_id)
            connection = ClientConnection(connection)

            self.client_connection[node_id] = connection
            self.connection_client[connection] = ClientId(node_id)
        elif promoted_type == ServerConnection:
            node_id = ServerId(node_id)
            connection = ServerConnection(connection)

            self.server_connection[node_id] = connection
            self.connection_server[connection] = ServerId(node_id)
        elif promoted_type == WanConnection:
            node_id = WanNode(node_id)
            connection = WanConnection(connection)

            self.wan_connection[node_id] = connection
            self.connection_wan[connection] = node_id
        else:
            raise ValueError("Invalid connection type")

    @functools.singledispatchmethod
    async def handle_message(self, msg, socket: WebSocket):
        pass

    @handle_message.register
    async def _(self, msg: FrontendMessage, socket: WebSocket):
        if UserConnection(socket) in self.users:
            await self.handle_message(msg.msg, socket)

    @handle_message.register
    async def _(self, msg: SessionMetricSubscribeRequest, socket: WebSocket):
        session_id = SessionId(msg.session_id)
        user = UserConnection(socket)

        with Session(sqlite_engine) as db_session:
            if db_session.get(Session, session_id) is None:
                return

        self.user_sessions[user].add(session_id)
        self.session_users[session_id].add(user)

    @handle_message.register
    async def _(self, msg: SessionMetricUnsubscribeRequest, socket: WebSocket):
        session_id = SessionId(msg.session_id)
        user = UserConnection(socket)

        users = self.session_users[session_id]
        users.discard(user)
        if len(users) == 0:
            del self.session_users[session_id]

        sessions = self.user_sessions[user]
        sessions.discard(session_id)
        if len(sessions) == 0:
            del self.user_sessions[user]

    @handle_message.register
    async def _(self, msg: BackendControlMessage, socket: WebSocket):
        await self.handle_message(msg.data, socket)

    @handle_message.register
    async def _(self, msg: BackendRegisterClientNode, socket: WebSocket):
        with Session(sqlite_engine) as session:
            input_client_node = ClientNode.model_validate(msg)

            if (
                db_client_node := session.get(ClientNode, input_client_node.id)
            ) is not None:
                session.add(db_client_node.sqlmodel_update(input_client_node))
            else:
                session.add(input_client_node)

            session.commit()

            self.promote_backend_connection(BackendConnection(socket), ClientConnection)

    @handle_message.register
    async def _(self, msg: BackendRegisterServerNode, socket: WebSocket):
        with Session(sqlite_engine) as session:
            input_server_node = ServerNode.model_validate(msg)

            if (
                db_server_node := session.get(ServerNode, input_server_node.id)
            ) is not None:
                db_server_node.sqlmodel_update(input_server_node)
                session.add(db_server_node)
            else:
                session.add(input_server_node)

            session.commit()

            self.promote_backend_connection(BackendConnection(socket), ServerConnection)

    @handle_message.register
    async def _(self, msg: BackendRegisterWanNode, socket: WebSocket):
        with Session(sqlite_engine) as session:
            input_wan_node = WanNode.model_validate(msg)

            if (db_wan_node := session.get(WanNode, input_wan_node.id)) is not None:
                db_wan_node.sqlmodel_update(input_wan_node)
                session.add(db_wan_node)
            else:
                session.add(input_wan_node)

            session.commit()

            self.promote_backend_connection(BackendConnection(socket), WanConnection)

    @handle_message.register
    async def _(self, msg: BackendSessionEnded, _: WebSocket):
        await self.on_session_ended(SessionId(msg.session_id))

    @handle_message.register
    async def _(self, msg: BackendSessionMetric, _: WebSocket):
        session_id = SessionId(msg.session_id)

        self.metric_cache[session_id].append(msg)

        users = self.session_users[session_id]

        if len(users) > 0:
            msg = FrontendMessage(msg=msg).model_dump_json()

            # TODO: per-client timeouts
            await asyncio.gather(*[socket.send_text(msg) for socket in users])

    async def tick(self) -> AsyncGenerator[None, None]:
        while True:
            with Session(sqlite_engine) as db_session:
                # flush session metrics cache to DB
                for session_id, metrics in self.metric_cache.items():
                    # TODO
                    for point in metrics:
                        if point.data.transport == "tcp":
                            tcp_point = point.data.pt
                            pt = SessionMetricPoint(
                                session_id=session_id,
                                timestamp=tcp_point.timestamp,
                                metric=WanMetric.RATE,
                                value=tcp_point.rate,
                            )
                            db_session.add(pt)
                        elif point.data.transport == "udp":
                            udp_point = point.data.pt
                            loss_pt = SessionMetricPoint(
                                session_id=session_id,
                                timestamp=udp_point.timestamp,
                                metric=WanMetric.LOSS,
                                value=udp_point.loss,
                            )
                            latency_pt = SessionMetricPoint(
                                session_id=session_id,
                                timestamp=udp_point.timestamp,
                                metric=WanMetric.LATENCY,
                                value=udp_point.latency,
                            )
                            db_session.add_all([loss_pt, latency_pt])

                    db_session.commit()
                    metrics.clear()

            # TODO: prune stale connections and sessions

            yield


ws_manager = WsManager()


async def tick_websocket_manager():
    async for _ in ws_manager.tick():
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_create_all()
    ws_tick_task = asyncio.create_task(tick_websocket_manager())
    yield
    ws_tick_task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/clients")
def clients():
    pass


@app.get("/servers")
def servers():
    pass


@app.get("/wans")
def wans():
    pass


@app.get("/sessions")
def sessions():
    pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect_frontend(websocket)
    try:
        while True:
            msg = FrontendMessage.model_validate(await websocket.receive_json())

            await ws_manager.handle_message(msg, websocket)
    except Exception:
        pass
    finally:
        ws_manager.disconnect_frontend(websocket)


@app.websocket("/ws_backend")
async def websocket_backend_endpoint(websocket: WebSocket):
    await ws_manager.connect_backend(websocket)
    try:
        while True:
            msg = BackendControlMessage.model_validate(await websocket.receive_json())

            await ws_manager.handle_message(msg, websocket)
    except Exception:
        pass
    finally:
        await ws_manager.disconnect_backend(websocket)
