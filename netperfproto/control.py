
from asyncio import Event, Protocol, Queue, QueueFull
import asyncio
import datetime
from typing import Optional
import uuid
from loguru import logger
import websockets

from netperfbackend.models import BackendControlMessage, BackendSessionCreate, BackendSessionDestroy

class ControlProtocol(Protocol):
    stop_event: Event
    conn_established_event: Event = Event()
    msg_rx: Queue[BackendControlMessage] = Queue(32)
    msg_tx: Queue[BackendControlMessage] = Queue(32)

    async def recv_message(self) -> BackendControlMessage:
        return await self.msg_rx.get()

    async def send_message(self, msg: BackendControlMessage):
        await self.msg_tx.put(msg)

    def send_message_nowait(self, msg: BackendControlMessage) -> bool:
        try:
            self.msg_tx.put_nowait(msg)
        except QueueFull:
            return False
        
        return True

    async def wait_for_conn_established(self):
        await self.conn_established_event.wait()

    def clear_conn_established(self):
        self.conn_established_event.clear()

    def run(self):
        ...

    async def wait(self):
        ...


class MockControlProtocol(ControlProtocol):
    def __init__(self, stop_event: Event):
        self.task: Optional[asyncio.Task] = None
        self.stop_event = stop_event

    def run(self):
        async def runner(stop_event: Event, conn_est_event: Event):
            async def msg_tx_printer():
                while True:
                    msg = await self.msg_tx.get()
                    logger.info(f"TX {msg}")

            tx_printer_task = asyncio.create_task(msg_tx_printer())

            conn_est_event.set()

            await asyncio.sleep(1)

            tcp_session_id = uuid.uuid4()
            await self.msg_rx.put(BackendControlMessage(data=BackendSessionCreate(session_id=tcp_session_id, target_service="tcp://localhost:10500", duration=datetime.timedelta(seconds=10))))
            udp_session_id = uuid.uuid4()
            await self.msg_rx.put(BackendControlMessage(data=BackendSessionCreate(session_id=udp_session_id, target_service="udp://localhost:10500", duration=datetime.timedelta(seconds=10))))

            await asyncio.sleep(3)

            await self.msg_rx.put(BackendControlMessage(data=BackendSessionDestroy(session_id=tcp_session_id)))

            await asyncio.sleep(1)

            await self.msg_rx.put(BackendControlMessage(data=BackendSessionDestroy(session_id=udp_session_id)))

            await stop_event.wait()

            tx_printer_task.cancel()

        self.task = asyncio.create_task(runner(self.stop_event, self.conn_established_event))

    async def wait(self):
        if self.task:
            if self.task.cancelling() == 0:
                self.task.cancel()
            await self.task

class WsControlProtocol(ControlProtocol):
    def __init__(self, uri: str, stop_event: Event):
        self.uri = uri
        self.stop_event = stop_event

        self.task: Optional[asyncio.Task] = None

    def run(self):
        async def runner(
            uri: str,
            message_tx: Queue[BackendControlMessage],
            message_rx: Queue[BackendControlMessage],
            stop_event: Event,
            conn_established_event: Event,
        ):
            never_future = asyncio.get_running_loop().create_future()

            stop_recv = asyncio.create_task(stop_event.wait())
            msg_tx = asyncio.create_task(message_tx.get())
            ws_conn = websockets.connect(uri)
            ws_recv = never_future

            ws: Optional[websockets.WebSocketClientProtocol] = None

            fut_set = set((stop_recv, msg_tx, ws_conn, ws_recv))

            while True:
                done, pending = await asyncio.wait(
                    fut_set, return_when=asyncio.FIRST_COMPLETED
                )

                for f in done:
                    if f == stop_recv:
                        # TODO: cancellations
                        return
                    elif f == ws_conn:
                        # TODO: exception handling
                        """
                            InvalidURI: If uri isn't a valid WebSocket URI.
                            OSError: If the TCP connection fails.
                            InvalidHandshake: If the opening handshake fails.
                            ~asyncio.TimeoutError: If the opening handshake times out.
                        """
                        ws = await ws_conn

                        old_ws_recv = ws_recv
                        if old_ws_recv in pending:
                            pending.remove(old_ws_recv)

                        ws_recv = ws.recv()
                        pending.add(ws_recv)

                        conn_established_event.set()
                    elif f == ws_recv:
                        try:
                            msg = await ws_recv

                            try:
                                validated_msg = BackendControlMessage.model_validate_json(msg)

                                await message_rx.put(validated_msg)
                            except ValueError:
                                pass

                            ws_recv = ws.recv()
                            pending.add(ws_recv)

                        except websockets.ConnectionClosed:
                            logger.error("websocket connection lost - reconnecting...")

                            ws = None
                            ws_recv = never_future

                            # websockets.connect() provides an async iterator
                            # we can just await it again (I think)
                            pending.add(ws_conn)
                    elif f == msg_tx:
                        msg = await msg_tx

                        await ws.send(msg.model_dump_json())

                        msg_tx = asyncio.create_task(message_tx.get())
                        pending.add(msg_tx)

                fut_set = pending

                if stop_event.is_set():
                    return

        self.task = asyncio.create_task(
            runner(self.uri, self.msg_tx, self.msg_rx, self.stop_event, self.conn_established_event)
        )

    async def wait(self):
        if self.task:
            await self.task

