import asyncio
import functools
from contextlib import asynccontextmanager
import datetime
from typing import AsyncGenerator, Dict, List, NewType, Set
import uuid
from fastapi import FastAPI, WebSocket
from sqlmodel import Session

from models import (
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
    SessionMetricSubscribeRequest,
    SessionMetricUnsubscribeRequest,
    WanNode,
)

from db import engine, SQLModel

UserConnection = NewType("UserConnection", WebSocket)
BackendConnection = NewType("BackendConnection", WebSocket)

ClientConnection = NewType("ClientConnection", BackendConnection)
ServerConnection = NewType("ServerConnection", BackendConnection)
WanConnection = NewType("WanConnection", BackendConnection)

ClientId = NewType("ClientId", uuid.UUID)
ServerId = NewType("ServerId", uuid.UUID)
WanId = NewType("WanId", uuid.UUID)

SessionId = NewType("SessionId", uuid.UUID)


class WsManager:
    def __init__(self):
        self.user_connections: Set[UserConnection] = set()
        self.backend_connections: Dict[BackendConnection, datetime.datetime] = dict()

        # frontend WS -> session IDs
        self.user_subscriptions: Dict[UserConnection, Set[SessionId]] = {}
        # session ID -> frontend WS
        self.session_subscribed_users: Dict[SessionId, Set[UserConnection]] = {}

        # backend WS -> node ID
        self.connection_clients: Dict[ClientConnection, ClientId] = {}
        self.connection_servers: Dict[ServerConnection, ServerId] = {}
        self.connection_wans: Dict[WanConnection, WanId] = {}

        # node ID -> backend WS
        self.client_connections: Dict[ClientId, ClientConnection] = {}
        self.server_connections: Dict[ServerId, ServerConnection] = {}
        self.wan_connections: Dict[WanId, WanConnection] = {}

        # session ID -> client node WS
        self.session_client: Dict[SessionId, ClientConnection] = {}

        # store session metrics in memory and periodically flush to DB
        self.session_metric_cache: Dict[SessionId, List[BackendSessionMetric]] = {}

    async def connect_frontend(self, ws: WebSocket):
        await ws.accept()
        self.user_connections.add(UserConnection(ws))

    async def connect_backend(self, ws: WebSocket):
        await ws.accept()
        self.backend_connections[BackendConnection(ws)] = datetime.datetime.now()

    def disconnect_frontend(self, ws: WebSocket):
        this_user = UserConnection(ws)

        self.user_connections.discard(this_user)

        # unsubscribe the socket from all sessions
        sessions = self.user_subscriptions.pop(this_user, set())

        for session in sessions:
            self.session_subscribed_users[session].discard(this_user)

    def remove_backend_connection(self, ws: WebSocket):
        this_connection = BackendConnection(ws)
        self.backend_connections.pop(this_connection, None)

    @functools.singledispatchmethod
    async def handle_message(self, msg, socket: WebSocket):
        pass

    @handle_message.register
    async def _(self, msg: FrontendMessage, socket: WebSocket):
        this_user = UserConnection(socket)

        if this_user in self.user_connections:
            await self.handle_message(msg.msg, socket)

    @handle_message.register
    async def _(self, msg: SessionMetricSubscribeRequest, socket: WebSocket):
        this_session = SessionId(msg.session_id)
        this_user = UserConnection(socket)

        with Session(engine) as db_session:
            if db_session.get(Session, this_session) is None:
                return

        self.user_subscriptions.setdefault(this_user, set()).add(this_session)
        self.session_subscribed_users.setdefault(this_session, set()).add(this_user)

    @handle_message.register
    async def _(self, msg: SessionMetricUnsubscribeRequest, socket: WebSocket):
        this_session = SessionId(msg.session_id)
        this_user = UserConnection(socket)

        if users := self.session_subscribed_users.get(this_session, None):
            users.discard(this_user)
            if len(users) == 0:
                del self.session_subscribed_users[this_session]

        if subscriptions := self.user_subscriptions.get(this_user, None):
            subscriptions.discard(this_session)
            if len(subscriptions) == 0:
                del self.user_subscriptions[this_user]

    @handle_message.register
    async def _(self, msg: BackendControlMessage, socket: WebSocket):
        this_backend_connection = BackendConnection(socket)

        if this_backend_connection in self.backend_connections:
            await self.handle_message(msg.data, socket)

    @handle_message.register
    async def _(self, msg: BackendRegisterClientNode, socket: WebSocket):
        with Session(engine) as session:
            input_client_node = ClientNode.model_validate(msg)

            if (
                db_client_node := session.get(ClientNode, input_client_node.id)
            ) is not None:
                db_client_node.sqlmodel_update(input_client_node)
                session.add(db_client_node)
            else:
                session.add(input_client_node)

            session.commit()

            this_connection = ClientConnection(socket)
            this_id = ClientId(db_client_node.id)

            self.remove_backend_connection(socket)

            self.client_connections[this_id] = this_connection
            self.connection_clients[this_connection] = this_id

    @handle_message.register
    async def _(self, msg: BackendRegisterServerNode, socket: WebSocket):
        with Session(engine) as session:
            input_server_node = ServerNode.model_validate(msg)

            if (
                db_server_node := session.get(ServerNode, input_server_node.id)
            ) is not None:
                db_server_node.sqlmodel_update(input_server_node)
                session.add(db_server_node)
            else:
                session.add(input_server_node)

            session.commit()

            this_connection = ServerConnection(socket)
            this_id = ServerId(db_server_node.id)

            self.remove_backend_connection(socket)

            self.server_connections[this_id] = this_connection
            self.connection_servers[this_connection] = this_id

    @handle_message.register
    async def _(self, msg: BackendRegisterWanNode, socket: WebSocket):
        with Session(engine) as session:
            input_wan_node = WanNode.model_validate(msg)

            if (db_wan_node := session.get(WanNode, input_wan_node.id)) is not None:
                db_wan_node.sqlmodel_update(input_wan_node)
                session.add(db_wan_node)
            else:
                session.add(input_wan_node)

            session.commit()

            this_connection = WanConnection(socket)
            this_id = WanId(db_wan_node.id)

            self.remove_backend_connection(socket)

            self.wan_connections[this_id] = this_connection
            self.connection_wans[this_connection] = this_id

    @handle_message.register
    async def _(self, msg: BackendSessionEnded, socket: WebSocket):
        this_session = SessionId(msg.session_id)

        subscribers = self.session_subscribed_users.pop(this_session, set())
        self.session_client.pop(this_session, None)

        if len(subscribers) > 0:
            msg = FrontendMessage(
                msg=SessionEndedEvent(session_id=this_session)
            ).model_dump_json()

            # TODO: per-client timeouts
            await asyncio.gather(*[socket.send_text(msg) for socket in subscribers])

    @handle_message.register
    async def _(self, msg: BackendSessionMetric, socket: WebSocket):
        this_session = SessionId(msg.session_id)

        # store in session metrics cache
        self.session_metric_cache.setdefault(this_session, []).append(msg)

        # forward to subscribed frontend clients
        subscribers = self.session_subscribed_users.get(this_session, set())

        if len(subscribers) > 0:
            msg = FrontendMessage(msg=msg).model_dump_json()

            # TODO: per-client timeouts
            await asyncio.gather(*[socket.send_text(msg) for socket in subscribers])

    async def broadcast_frontend(sockets: Set[WebSocket], msg: FrontendMessage):
        pass

    async def tick(self) -> AsyncGenerator[None, None]:
        while True:
            # TBD what this should do
            yield


ws_manager = WsManager()


async def ws_tick():
    async for _ in ws_manager.tick():
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    ws_tick_task = asyncio.create_task(ws_tick())
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
        ws_manager.remove_backend_connection(websocket)
