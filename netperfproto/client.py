from asyncio import Event
import asyncio
import os
import signal

from loguru import logger

from control import WsControlProtocol
from session import SessionManager


async def main():
    if (WS_ENDPOINT := os.getenv("WS_ENDPOINT")) is None:
        logger.error("WS_ENDPOINT environment variable not set. Exiting...")
        return
    if (CLIENT_NAME := os.getenv("CLIENT_NAME")) is None:
        logger.error("CLIENT_NAME environment variable not set. Exiting...")
        return

    stop_everything = Event()

    loop = asyncio.get_running_loop()

    def shutdown():
        logger.info("Exit signal received. Triggering shutdown...")
        stop_everything.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    control = WsControlProtocol(WS_ENDPOINT, stop_everything)
    control.run()

    session_manager = SessionManager(CLIENT_NAME, control, stop_everything)
    session_manager.run()

    logger.info("All systems running...")

    await stop_everything.wait()
    logger.info("Shutting down...")

    await asyncio.gather(control.wait(), session_manager.wait(), return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
