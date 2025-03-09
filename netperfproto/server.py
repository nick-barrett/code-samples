import asyncio
import signal
from typing import Callable, List, Optional
import uuid
import socket
import os

import websockets
from loguru import logger

from netperfbackend.models import (
    BackendControlMessage,
    BackendRegisterServerNode,
    ServerService,
)
from tcp import tcp_server
from udp import udp_server


def get_ip() -> Optional[str]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(("9.9.9.9", 53))
        ip = s.getsockname()[0]
    except Exception:
        ip = None
    finally:
        s.close()

    return ip


async def ws_process(uri: str, id: uuid.UUID, name: str, services: List[str]):
    async for ws in websockets.connect(uri):
        try:
            while True:
                await ws.send(
                    BackendControlMessage(
                        data=BackendRegisterServerNode(
                            id=id,
                            name=name,
                            services=[ServerService(s, uuid.uuid4()) for s in services],
                        )
                    )
                )

                await asyncio.sleep(5)
        except websockets.ConnectionClosed:
            continue


def mapped[T, U](val: Optional[T], fn: Callable[[T], U]) -> Optional[U]:
    return fn(val) if val is not None else None


async def main():
    if (WS_ENDPOINT := os.getenv("WS_ENDPOINT")) is None:
        logger.error("WS_ENDPOINT environment variable not set. Exiting...")
        return
    if (TCP_PORT := mapped(os.getenv("TCP_PORT"), int)) is None:
        logger.error("TCP_PORT environment variable not set. Exiting...")
        return
    if (UDP_PORT := mapped(os.getenv("UDP_PORT"), int)) is None:
        logger.error("UDP_PORT environment variable not set. Exiting...")
        return
    if (SERVER_NAME := os.getenv("SERVER_NAME")) is None:
        logger.error("SERVER_NAME environment variable not set. Exiting...")
        return

    id = uuid.uuid4()

    server_ip: Optional[str] = get_ip()
    if server_ip is None:
        logger.error("Could not determine server IP address. Exiting...")
        return

    services = [
        f"tcp://{server_ip}:{TCP_PORT}",
        f"udp://{server_ip}:{UDP_PORT}",
    ]

    loop = asyncio.get_running_loop()

    stop_everything = asyncio.Event()
    stop_everything_task = loop.create_task(stop_everything.wait())

    tcp_factory = lambda: asyncio.create_task(tcp_server(TCP_PORT))
    udp_factory = lambda: asyncio.create_task(udp_server(UDP_PORT))
    ws_factory = lambda: asyncio.create_task(
        ws_process(WS_ENDPOINT, id, SERVER_NAME, services)
    )

    def shutdown():
        logger.info("Exit signal received. Triggering shutdown...")
        stop_everything.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    tcp_task = tcp_factory()
    udp_task = udp_factory()
    ws_task = ws_factory()

    tasks = set([tcp_task, udp_task, ws_task, stop_everything_task])

    while len(tasks) > 0:
        done, pending = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")
        for t in done:
            if t == stop_everything_task:
                logger.info("Stopping tasks...")
                tcp_task.cancel()
                udp_task.cancel()
                ws_task.cancel()
            elif t == udp_task and not udp_task.cancelled():
                logger.info("UDP server exited. Restarting...")
                udp_task = udp_factory()
                pending.add(udp_task)
            elif t == tcp_task and not tcp_task.cancelled():
                logger.info("TCP server exited. Restarting...")
                tcp_task = tcp_factory()
                pending.add(tcp_task)
            elif t == ws_task and not ws_task.cancelled():
                logger.info("Websocket task exited. Restarting...")
                ws_task = ws_factory()
                pending.add(ws_task)

        tasks = pending

    logger.info("Exiting...")


if __name__ == "__main__":
    asyncio.run(main())
